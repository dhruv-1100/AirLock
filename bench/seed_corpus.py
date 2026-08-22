#!/usr/bin/env python3
"""bench/seed_corpus.py — owner C. SRS §10 Phase 1 task 7.

Seeds `policy_corpus`: the nine clauses plus ~200 exemplars, each embedded with
bge-small-en-v1.5 (384-d).

    python bench/seed_corpus.py                 # seed clauses + exemplars
    python bench/seed_corpus.py --reset         # wipe seeded docs first (keeps overrides)

**NFR-S10 — this runs on the 20 Arm cores via ONNX Runtime. It is NOT a GPU process.**
bge-small is 67 MB fp16. A third vLLM process would cost a CUDA context (~300–500 MB),
its own compile warm-up, and SM time, for a 1.7 GB model. Grace does retrieval;
Blackwell does inference. Do not "optimise" this onto the GPU — that is an NFR-S1
violation and only A may start a GPU process anyway.

The exemplars are the point. `kind:"exemplar"` documents ARE the detector for classes
no regex can reach — this is semantic memory, not a demo of vector search. The nine
`kind:"clause"` documents are the policy text the block overlay renders and cites.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EMBED_DIM = 384
MODEL_ID = "BAAI/bge-small-en-v1.5"

# --------------------------------------------------------------------------- exemplars
# Short, characteristic phrasings of each class. These are what a paste gets compared
# against semantically. Deliberately varied in register: a spreadsheet header, a Slack
# message, a config fragment, a sentence of prose.
EXEMPLARS: dict[str, list[str]] = {
    "financial": [
        "Q3 ARR came in at 14.2M against a 16M plan, we are holding the exit guide",
        "FY26 Revenue Forecast — Plan vs. Commit, internal do not distribute",
        "pipeline coverage 2.4x, net revenue retention 118%, pre-announcement",
        "unreleased quarterly projections for the board pre-read, numbers not final",
        "cap table after the Series C, fully diluted ownership by holder",
        "compensation bands by level for the upcoming comp cycle, confidential",
        "we expect to miss consensus by roughly four million this quarter",
        "draft earnings release, embargoed until market close on the 14th",
        "churn forecast by cohort, unaudited, subject to change",
        "commit number for the EMEA renewal cohort ahead of the board meeting",
        "gross margin bridge for the restructuring, not yet disclosed",
        "bookings pacing versus plan, week 6 of the quarter, internal only",
    ],
    "pii": [
        "name,email,phone,plan,mrr followed by rows of customer contact details",
        "customer export with full names, email addresses and telephone numbers",
        "applicant social security number and date of birth for verification",
        "employee ID, home address, and personal mobile number for the directory",
        "patient list with medical record numbers and dates of birth",
        "passport number and nationality for the travel booking",
        "driver's licence number captured during onboarding",
        "spreadsheet of subscribers with billing address and account tier",
        "contact list exported from the CRM including deal value per account",
        "beneficiary details including national insurance number",
    ],
    "credentials": [
        "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in an environment file",
        "GITHUB_TOKEN set to a personal access token in the CI config",
        "-----BEGIN RSA PRIVATE KEY----- followed by base64 key material",
        "postgres connection string with an inline password to a production host",
        "bearer token in an Authorization header copied from a request",
        "Slack bot token xoxb pasted into a debugging thread",
        "Stripe live secret key committed to the repository by mistake",
        "service account JSON with a private key id and client email",
        "rotate the mTLS bundle from the internal vault before the cutover",
        "API key for the payments provider in a plaintext runbook",
    ],
    "source_code": [
        "internal nginx upstream block naming prod hosts on the internal domain",
        "terraform plan output referencing internal VPC and subnet identifiers",
        "kubernetes manifest for an internal service with cluster-local DNS names",
        "proprietary matching algorithm marked internal and confidential",
        "internal service mesh configuration with mTLS certificate paths",
        "database migration script against the production billing schema",
        "feature flag configuration for an unreleased internal product",
        "CI pipeline definition referencing the internal artifact registry",
    ],
    "legal_hr": [
        "mutual non-disclosure agreement with commercial terms and exclusivity clause",
        "privileged and confidential, prepared in anticipation of litigation",
        "HR disciplinary file with allegation summary and witness statements",
        "settlement terms under negotiation, subject to counsel review",
        "performance improvement plan for a named employee, restricted circulation",
        "counsel's preliminary assessment of exposure in the pending matter",
        "redundancy consultation list with individual selection scores",
    ],
    "health": [
        "patient name with active diagnosis and current medication list",
        "clinical note describing presenting complaint and treatment plan",
        "medical record number alongside date of birth and consultant clinic",
        "lab results with patient identifiers attached",
        "mental health assessment with named individual and risk rating",
        "prescription history for an identifiable patient",
    ],
    # BENIGN exemplars matter as much as the sensitive ones: they are what pulls a
    # borderline paste back toward ALLOW. A corpus with only sensitive exemplars is a
    # corpus that blocks everything that looks vaguely technical.
    "benign": [
        "how do I reverse a linked list in python without recursion",
        "explain the difference between a hash map and a binary search tree",
        "why is my regex matching a timestamp when I only want card numbers",
        "the AWS documentation uses AKIAIOSFODNN7EXAMPLE as the sample credential",
        "Stripe's test card 4242424242424242 keeps returning card_declined in tests",
        "reported Q2 revenue was 1.2 billion according to the published 10-Q filing",
        "my .env.example has your-api-key-here and changeme as placeholders",
        "quicksort implementation from the textbook, why is it slow on sorted input",
        "what is the standard set of reserved phone numbers like 555-0100",
        "bisecting a regression between two commit SHAs on the release branch",
        "should I index a UUID column directly or add a surrogate integer key",
        "writing a short article about vector databases for a general audience",
        "how do I parse the third field from each row of a CSV in pandas",
        "the sha256 of an empty file is a well known constant, can I assert on it",
        "difference between an iterator and a generator in python",
        "how does reciprocal rank fusion combine two ranked result lists",
    ],
}

CLASS_TO_CLAUSE = {
    "credentials": "POL-001",
    "pii": "POL-004",
    "health": "POL-005",
    "financial": "POL-006",
    "source_code": "POL-007",
    "legal_hr": "POL-008",
    "benign": "NONE",
}
CLASS_SEVERITY = {
    "credentials": "HIGH", "pii": "HIGH", "health": "HIGH", "financial": "HIGH",
    "source_code": "MEDIUM", "legal_hr": "HIGH", "benign": "LOW",
}


# --------------------------------------------------------------------------- embedder
class Embedder:
    """bge-small-en-v1.5 on CPU. Tries ONNX Runtime, then sentence-transformers, then
    a deterministic hash fallback so the pipeline is always exercisable."""

    def __init__(self) -> None:
        self.backend = "hash"
        self._st = None
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._st = SentenceTransformer(MODEL_ID, device="cpu")
            self.backend = "sentence-transformers(cpu)"
        except Exception:  # noqa: BLE001
            try:
                import onnxruntime  # noqa: F401  # type: ignore
                from transformers import AutoTokenizer  # noqa: F401  # type: ignore

                self.backend = "onnxruntime"  # wired on the box where the model is staged
            except Exception:  # noqa: BLE001
                pass
        print(f"embedder backend: {self.backend}")
        if self.backend == "hash":
            print(
                "  ! NO REAL EMBEDDING MODEL. Using a deterministic hash embedding so the\n"
                "    retrieval path is exercisable. Semantic recall will be meaningless.\n"
                "    Install: pip install sentence-transformers   (CPU only — NFR-S10)"
            )

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self._st is not None:
            # normalize_embeddings=True because the index is cosine and MongoDB does not
            # normalise for you.
            return [
                v.tolist()
                for v in self._st.encode(texts, normalize_embeddings=True, batch_size=32)
            ]
        return [self._hash_embed(t) for t in texts]

    @staticmethod
    def _hash_embed(text: str) -> list[float]:
        import hashlib
        import math

        vec = [0.0] * EMBED_DIM
        for tok in text.lower().split():
            h = int(hashlib.sha256(tok.encode()).hexdigest()[:16], 16)
            vec[h % EMBED_DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


# --------------------------------------------------------------------------- seeding
def load_clauses() -> list[dict]:
    p = Path("services/inspect/policy.yaml")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(p.read_text())["clauses"]
    except ImportError:
        # Minimal parser so a missing PyYAML never blocks the seed at 11:00.
        print("  ! PyYAML not installed — using the built-in clause list")
        return [
            {"id": "POL-001", "class": "CREDENTIAL", "severity": "HIGH",
             "text": "Live authentication material must never leave a managed endpoint."},
            {"id": "POL-002", "class": "PAYMENT_CARD", "severity": "HIGH",
             "text": "Primary account numbers must not be transmitted to third-party services."},
            {"id": "POL-003", "class": "GOV_ID", "severity": "HIGH",
             "text": "Government-issued identifiers must not be shared with external processors."},
            {"id": "POL-004", "class": "CUSTOMER_RECORD", "severity": "HIGH",
             "text": "Customer-identifying records must not leave managed endpoints."},
            {"id": "POL-005", "class": "HEALTH_RECORD", "severity": "HIGH",
             "text": "Patient-identifiable clinical information must not be transmitted externally."},
            {"id": "POL-006", "class": "FINANCIAL_NONPUBLIC", "severity": "HIGH",
             "text": "Financial information not yet released publicly must not be disclosed."},
            {"id": "POL-007", "class": "PROPRIETARY_CODE", "severity": "MEDIUM",
             "text": "Internal source code and infrastructure configuration must not be pasted externally."},
            {"id": "POL-008", "class": "LEGAL_HR", "severity": "HIGH",
             "text": "Material under legal privilege or confidentiality obligation must not be shared."},
            {"id": "POL-009", "class": "RESERVED", "severity": "LOW", "text": "Reserved."},
        ]


async def main_async(reset: bool) -> int:
    from services.inspect import mongo as M

    if not await M.connect():
        print("no mongo — run `bash stack/up_mongo.sh` first", file=sys.stderr)
        return 2

    coll = M._db["policy_corpus"]
    emb = Embedder()
    now = datetime.now(timezone.utc)

    if reset:
        # Never delete analyst_override docs — those are the procedural-memory beat and
        # re-seeding must not silently undo a correction made on stage.
        r = await coll.delete_many({"origin": "seed"})
        print(f"removed {r.deleted_count} seeded docs (analyst overrides preserved)")

    docs: list[dict] = []

    # ---- nine clauses ----
    clauses = load_clauses()
    ctexts = [c["text"] for c in clauses]
    for c, v in zip(clauses, emb.encode(ctexts)):
        docs.append({
            "kind": "clause", "clause_id": c["id"], "class": str(c["class"]).lower(),
            "tenant": M.TENANT, "modality": "text", "severity": c.get("severity", "MEDIUM"),
            "text": c["text"], "snippet": c["text"][:200], "embedding": v,
            "origin": "seed", "added_by": "seed", "ts": now,
        })

    # ---- exemplars ----
    flat = [(cls, t) for cls, texts in EXEMPLARS.items() for t in texts]
    for (cls, text), v in zip(flat, emb.encode([t for _, t in flat])):
        docs.append({
            "kind": "exemplar", "clause_id": CLASS_TO_CLAUSE.get(cls, "NONE"),
            "class": cls, "tenant": M.TENANT, "modality": "text",
            "severity": CLASS_SEVERITY.get(cls, "MEDIUM"),
            "text": text, "snippet": text[:200], "embedding": v,
            "origin": "seed", "added_by": "seed", "ts": now,
        })

    await coll.insert_many(docs)

    n_clause = sum(1 for d in docs if d["kind"] == "clause")
    n_ex = len(docs) - n_clause
    print(f"\nseeded {len(docs)} docs: {n_clause} clauses + {n_ex} exemplars")
    by_class: dict[str, int] = {}
    for d in docs:
        if d["kind"] == "exemplar":
            by_class[d["class"]] = by_class.get(d["class"], 0) + 1
    for k, v in sorted(by_class.items()):
        print(f"  {k:14s} {v}")

    # ---- verify retrieval actually returns something ----
    print("\nverifying retrieval …")
    qv = emb.encode(["our unreleased revenue forecast for next year"])[0]
    hits = await M.rank_fusion_clauses(qv, "unreleased revenue forecast", limit=3)
    if hits:
        print(f"  {len(hits)} hits — top class: {hits[0].get('class')} "
              f"clause: {hits[0].get('clause_id')} score: {hits[0].get('score')}")
    else:
        print("  ! ZERO HITS. Check `queryable`, NOT the embeddings (R10):")
        print("    db.policy_corpus.aggregate([{$listSearchIndexes:{}}])")
        print("    A $vectorSearch against a non-queryable index returns empty, not an error.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed policy_corpus with clauses + exemplars.")
    ap.add_argument("--reset", action="store_true", help="remove seeded docs first")
    a = ap.parse_args()
    return asyncio.run(main_async(a.reset))


if __name__ == "__main__":
    sys.exit(main())
