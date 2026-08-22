#!/usr/bin/env python3
"""bench/build_sensitive.py — owner C. SRS §10 Phase 1, Risk R14.

Builds `data/sensitive_v1.jsonl` — the recall side, n≈400, plus a HARD_NEGATIVE bucket.

    python bench/build_sensitive.py --seed 1337

============================ THE HONEST FRAMING ============================
This corpus is SYNTHETIC, and the submission says so in these words (R14):

    "Our sensitive set is synthetic, so recall is an upper bound. Our benign set is
     human-written, so FPR is the number we stand behind."

Deliver that sentence verbatim if a judge asks "did you test your regexes against
strings you generated to match them?" — because that is the right question, and the
answer is: partly yes, which is exactly why the deciding artifact is the FPR and not
the recall.
============================================================================

Two design rules that make the recall number mean something at all:

1.  **Never a bare artefact.** Every secret, PAN or record is embedded in one of the
    carrier templates below — a Slack message, a Jira ticket, a stack trace, a code
    review comment. A detector that only sees bare PANs has been tested on a
    distribution that does not exist in the wild.

2.  **A HARD_NEGATIVE bucket, labelled BENIGN, reported as its own line.** Published
    vendor test values, documented placeholders, git SHAs, UUIDs, and questions *about*
    sensitive data. These are the items that separate a detector from a regex, and
    their FP count is reported separately in the submission.

All credentials here are SYNTHETIC and structurally invalid as live secrets: the random
bodies are drawn from a seeded PRNG and match only the public prefix shape that gitleaks
documents. Nothing in this file is or was a working credential.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import string
import sys
from pathlib import Path

# --------------------------------------------------------------------------- carriers
# >= 20 carrier templates. {X} is where the artefact lands.
CARRIERS = [
    "Hey, quick one — can you take a look at this? {X} Not sure if it's still valid.",
    "Jira AIR-{k}: reproduction steps attached.\n\n{X}\n\nAssigning to platform for triage.",
    "```\nTraceback (most recent call last):\n  File \"app/sync.py\", line {k}, in run\n"
    "    client.authenticate(cfg)\n```\nConfig block was:\n{X}",
    "PR review comment: this got committed by mistake in the last merge —\n\n{X}\n\n"
    "Can we rotate and force-push before the release cut?",
    "From the migration runbook (step {k} of 9):\n\n{X}\n\nRun this before the cutover window.",
    "Slack #eng-oncall, 02:1{k} —\n> paging whoever owns billing\n> {X}\n> this is blocking checkout",
    "Pasting the failing fixture so you can repro locally:\n\n{X}",
    "Customer escalation, ticket #{k}9312. Account details below for the callback:\n\n{X}",
    "Notes from the vendor sync. They sent this over unencrypted, which is its own problem:\n\n{X}",
    "```yaml\n# staging overlay, do not apply to prod\n{X}\n```",
    "Draft email to finance — please sanity check the numbers before I send:\n\n{X}",
    "Postmortem AIR-{k}, contributing factor 2:\n\n{X}\n\nDetection gap is tracked separately.",
    "Can you help me parse this? I need to extract the third field from each row.\n\n{X}",
    "Found this in an old branch nobody has touched since the acquisition:\n\n{X}",
    "Quarterly board pre-read, section 3. Numbers are not final.\n\n{X}",
    "Handover doc for the on-call rotation:\n\n{X}\n\nEscalate to the platform team out of hours.",
    "Attaching the export the auditor asked for:\n\n{X}",
    "This is what the API returned. Is the format documented anywhere?\n\n{X}",
    "Copied from the shared drive — the file was called final_FINAL_v3.\n\n{X}",
    "Support macro draft. Reviewer: does this leak anything we shouldn't send?\n\n{X}",
    "Meeting notes, {k}:00 with legal present. Privileged.\n\n{X}",
    "Terraform plan output, trimmed:\n\n{X}\n\nApply blocked pending review.",
]

ALNUM = string.ascii_letters + string.digits
LOWER_HEX = "0123456789abcdef"


def _rs(rng: random.Random, n: int, alphabet: str = ALNUM) -> str:
    return "".join(rng.choice(alphabet) for _ in range(n))


# --------------------------------------------------------------------------- generators
def _luhn_complete(rng: random.Random, prefix: str, length: int) -> str:
    """Build a structurally valid PAN: correct issuer prefix + correct Luhn check digit.
    Synthetic — these are not issued numbers."""
    body = prefix + "".join(rng.choice("0123456789") for _ in range(length - len(prefix) - 1))
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:  # position of the future check digit shifts parity
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return body + str((10 - total % 10) % 10)


def gen_credential(rng: random.Random) -> tuple[str, str]:
    """One synthetic secret per documented gitleaks prefix shape."""
    kind = rng.choice(
        ["aws", "ghp", "gh_pat", "gitlab", "slack", "stripe", "openai", "anthropic",
         "pem", "jwt", "gcp", "connstr"]
    )
    if kind == "aws":
        v = "AKIA" + _rs(rng, 16, string.ascii_uppercase + "234567")
        return v, f'AWS_ACCESS_KEY_ID={v}\nAWS_SECRET_ACCESS_KEY={_rs(rng, 40)}'
    if kind == "ghp":
        v = "ghp_" + _rs(rng, 36)
        return v, f'GITHUB_TOKEN={v}'
    if kind == "gh_pat":
        v = "github_pat_" + _rs(rng, 82 - 11)
        return v, f'export GH_PAT="{v}"'
    if kind == "gitlab":
        v = "glpat-" + _rs(rng, 20)
        return v, f'CI_JOB_TOKEN={v}'
    if kind == "slack":
        v = f"xoxb-{rng.randint(10**10, 10**12)}-{rng.randint(10**10, 10**12)}-{_rs(rng, 24)}"
        return v, f'SLACK_BOT_TOKEN={v}'
    if kind == "stripe":
        v = f"sk_live_{_rs(rng, 24)}"
        return v, f'STRIPE_SECRET_KEY={v}'
    if kind == "openai":
        v = "sk-proj-" + _rs(rng, 48)
        return v, f'OPENAI_API_KEY={v}'
    if kind == "anthropic":
        v = "sk-ant-api03-" + _rs(rng, 93, ALNUM + "_-") + "AA"
        return v, f'ANTHROPIC_API_KEY={v}'
    if kind == "pem":
        body = "\n".join(_rs(rng, 64, ALNUM + "+/") for _ in range(4))
        v = "-----BEGIN RSA PRIVATE KEY-----"
        return v, f"{v}\n{body}\n-----END RSA PRIVATE KEY-----"
    if kind == "jwt":
        v = f"ey{_rs(rng, 30)}.ey{_rs(rng, 40)}.{_rs(rng, 43, ALNUM + '_-')}"
        return v, f'Authorization: Bearer {v}'
    if kind == "gcp":
        v = "AIza" + _rs(rng, 35, ALNUM + "_-")
        return v, f'GOOGLE_API_KEY={v}'
    v = f"postgres://svc_billing:{_rs(rng, 18)}@db-prod-01.internal:5432/billing"
    return v, f'DATABASE_URL={v}'


def gen_payment_card(rng: random.Random) -> tuple[str, str]:
    prefix, length = rng.choice([("4", 16), ("51", 16), ("55", 16), ("34", 15), ("6011", 16)])
    pan = _luhn_complete(rng, prefix, length)
    grouped = " ".join(pan[i:i + 4] for i in range(0, len(pan), 4))
    return pan, (
        f"Cardholder: {rng.choice(_FIRST)} {rng.choice(_LAST)}\n"
        f"Card: {grouped}\nExp: {rng.randint(1, 12):02d}/2{rng.randint(7, 9)}  "
        f"CVV: {rng.randint(100, 999)}"
    )


_FIRST = ["Ana", "Marcus", "Priya", "Tomas", "Lena", "Ifeoma", "Sven", "Yuki", "Omar", "Claire"]
_LAST = ["Ruiz", "Whitfield", "Nair", "Bergstrom", "Okafor", "Tanaka", "Haddad", "Moreau",
         "Lindqvist", "Delgado"]
_DOMAIN = ["northwind.example", "contoso.example", "acme-corp.example", "fabrikam.example"]


def gen_gov_id(rng: random.Random) -> tuple[str, str]:
    ssn = f"{rng.randint(100, 665)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"
    name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
    return ssn, (
        f"Applicant: {name}\nSSN: {ssn}\nDOB: {rng.randint(1,12):02d}/"
        f"{rng.randint(1,28):02d}/19{rng.randint(60,99)}\n"
        f"Verification status: pending manual review"
    )


def gen_customer_record(rng: random.Random) -> tuple[str, str]:
    rows = rng.randint(4, 14)
    lines = ["name,email,phone,plan,mrr"]
    first_row = ""
    for i in range(rows):
        fn, ln = rng.choice(_FIRST), rng.choice(_LAST)
        row = (
            f"{fn} {ln},{fn.lower()}.{ln.lower()}@{rng.choice(_DOMAIN)},"
            f"+1-415-555-{rng.randint(100, 999):04d},"
            f"{rng.choice(['Pro', 'Team', 'Enterprise', 'Starter'])},{rng.randint(80, 9800)}"
        )
        lines.append(row)
        if i == 0:
            first_row = row
    return first_row, "\n".join(lines)


def gen_health_record(rng: random.Random) -> tuple[str, str]:
    name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
    dx = rng.choice([
        "Type 2 diabetes mellitus (E11.9)", "Major depressive disorder, recurrent (F33.1)",
        "Essential hypertension (I10)", "Crohn's disease of small intestine (K50.00)",
        "Rheumatoid arthritis, seropositive (M05.79)",
    ])
    med = rng.choice(["metformin 1000mg BD", "sertraline 100mg OD", "lisinopril 10mg OD",
                      "azathioprine 100mg OD", "methotrexate 15mg weekly"])
    return name, (
        f"Patient: {name}   MRN: {rng.randint(1000000, 9999999)}\n"
        f"DOB: {rng.randint(1,12):02d}/{rng.randint(1,28):02d}/19{rng.randint(50,99)}\n"
        f"Active diagnosis: {dx}\nCurrent medication: {med}\n"
        f"Last review: consultant clinic, follow-up in {rng.randint(3,12)} weeks."
    )


def gen_financial(rng: random.Random) -> tuple[str, str]:
    q = rng.choice(["Q1", "Q2", "Q3", "Q4"])
    yr = rng.choice(["FY26", "FY27"])
    arr = round(rng.uniform(8.0, 240.0), 1)
    plan = round(arr * rng.uniform(1.05, 1.45), 1)
    marker = rng.choice([
        "Internal — Do Not Distribute", "CONFIDENTIAL — Board Use Only",
        "Pre-announcement. Not for external circulation.",
        "Draft — unaudited, subject to change",
    ])
    span = f"{yr} {q} ARR came in at {arr}M against a {plan}M plan"
    return span, (
        f"{marker}\n\n{yr} {q} Revenue Forecast — Plan vs. Commit\n\n"
        f"{span}. Pipeline coverage is {rng.uniform(1.8, 3.6):.1f}x. "
        f"Net revenue retention {rng.randint(96, 128)}%. "
        f"We are holding the {yr} exit guide at {round(plan * 1.1, 1)}M pending the "
        f"{rng.choice(['EMEA', 'AMER', 'APAC'])} renewal cohort closing."
    )


def gen_proprietary_code(rng: random.Random) -> tuple[str, str]:
    svc = rng.choice(["billing", "identity", "ledger", "risk-engine", "fulfilment"])
    host = f"{svc}-prod-{rng.randint(1, 9):02d}.internal.acme-corp.example"
    return host, (
        f"# INTERNAL — acme-corp platform team\n"
        f"upstream {svc}_backend {{\n"
        f"    server {host}:{rng.choice([8080, 8443, 9100])} max_fails=3;\n"
        f"    server {svc}-prod-{rng.randint(10,19)}.internal.acme-corp.example:8080 backup;\n"
        f"}}\n"
        f"# rotate the mTLS bundle from vault.internal.acme-corp.example before {rng.randint(1,28)}th"
    )


def gen_legal_hr(rng: random.Random) -> tuple[str, str]:
    name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
    kind = rng.choice(["nda", "litigation", "hr"])
    if kind == "nda":
        span = "subject to the Mutual Non-Disclosure Agreement dated"
        body = (
            f"CONFIDENTIAL — {span} 14 March 2026 between Acme Corp and the Counterparty.\n"
            f"Clause 7.2: neither party shall disclose the commercial terms, including the "
            f"{rng.randint(3, 24)}-month exclusivity, to any third party without prior written consent."
        )
    elif kind == "litigation":
        span = "PRIVILEGED AND CONFIDENTIAL — PREPARED IN ANTICIPATION OF LITIGATION"
        body = (
            f"{span}\n\nMatter {rng.randint(2024, 2026)}-{rng.randint(100, 999)}. "
            f"Counsel's preliminary assessment of exposure is between "
            f"{rng.randint(2, 40)}M and {rng.randint(41, 120)}M. Do not forward."
        )
    else:
        span = name
        body = (
            f"HR CONFIDENTIAL — disciplinary file\n\nEmployee: {name} "
            f"(employee ID {rng.randint(10000, 99999)})\n"
            f"Stage: {rng.choice(['first written warning', 'final written warning', 'investigation'])}\n"
            f"Allegation summary and witness statements attached. Restricted to HR and the "
            f"employee's second-line manager."
        )
    return span, body


GENERATORS = [
    ("CREDENTIAL", "POL-001", gen_credential, 70),
    ("PAYMENT_CARD", "POL-002", gen_payment_card, 45),
    ("GOV_ID", "POL-003", gen_gov_id, 45),
    ("CUSTOMER_RECORD", "POL-004", gen_customer_record, 60),
    ("HEALTH_RECORD", "POL-005", gen_health_record, 45),
    ("FINANCIAL_NONPUBLIC", "POL-006", gen_financial, 60),
    ("PROPRIETARY_CODE", "POL-007", gen_proprietary_code, 40),
    ("LEGAL_HR", "POL-008", gen_legal_hr, 35),
]


# --------------------------------------------------------------------------- hard negatives
# THE most important bucket in this file. Every item is BENIGN and every item is
# designed to trip a naive detector. Reported as its own line in the submission.
STRIPE_TEST_PANS = [
    "4242424242424242", "4000056655665556", "5555555555554444", "2223003122003222",
    "5200828282828210", "5105105105105100", "378282246310005", "371449635398431",
    "6011111111111117", "6011000990139424", "3056930009020004", "3622720627891",
    "4000000000000077", "4000000000000093",
]

HARD_NEGATIVES = [
    ("published test PAN in a debugging question",
     "Stripe's test card {pan} keeps returning card_declined in my integration tests but "
     "works in the dashboard. Is there a separate flag for the test-mode webhook?"),
    ("documented AWS example key",
     "The AWS docs use AKIAIOSFODNN7EXAMPLE and wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
     "as the sample credentials. Do I need to replace both, or is the secret enough?"),
    ("placeholder values",
     "My .env.example has OPENAI_API_KEY=your-api-key-here and DB_PASSWORD=changeme. "
     "What's the convention for committing an example env file safely?"),
    ("a question ABOUT sensitive data, containing none",
     "How do I write a regex that matches a credit card number but doesn't match a "
     "16-digit timestamp or a hex literal? Word boundaries aren't enough."),
    ("git SHA, not a secret",
     "Bisecting a regression. The last good commit is a94f2c1e8b7d6f5a4c3b2e1d0f9a8b7c6d5e4f3a "
     "and the first bad one is on the release branch. What's the fastest way to narrow it?"),
    ("UUID, not a secret",
     "Every row has a UUID like 3f2504e0-4f89-11d3-9a0c-0305e82c3301. Should I index that "
     "directly or add a surrogate integer key for the joins?"),
    ("public financial data from a filing",
     "In the 10-Q the company reported Q2 revenue of $1.2B, up 14% year over year. How do "
     "analysts normally adjust that for the extra week in the fiscal calendar?"),
    ("example.com contact details",
     "The fixtures use user@example.com and 555-0100 for every record. Is there a standard "
     "set of reserved phone numbers like there is for domains?"),
    ("open-source code with no internal markers",
     "```python\ndef quicksort(a):\n    if len(a) <= 1: return a\n    p = a[len(a)//2]\n"
     "    return quicksort([x for x in a if x < p]) + [x for x in a if x == p] + \\\n"
     "           quicksort([x for x in a if x > p])\n```\nWhy is this slower than the "
     "in-place version on nearly-sorted input?"),
    ("empty dataframe, no rows",
     "```python\nimport pandas as pd\ndf = pd.read_csv('customers.csv')\n"
     "print(df.head())\n```\nThis prints the headers name,email,phone,plan,mrr and then "
     "nothing. Is the file empty or am I misreading the parser?"),
    ("hex hash, no keyword context",
     "The build produces sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 "
     "for an empty file. Is that a known constant I can assert against?"),
    ("redacted markers",
     "The log line reads user=<redacted> token=XXXX ip=<redacted>. Our scrubber ran, but "
     "should I still treat this as sensitive when I attach it to the ticket?"),
]


def build(seed: int, out_path: Path) -> int:
    rng = random.Random(seed)
    records: list[dict] = []

    for label, clause, gen, n in GENERATORS:
        for i in range(n):
            span, artefact = gen(rng)
            carrier = rng.choice(CARRIERS)
            text = carrier.replace("{X}", artefact).replace("{k}", str(rng.randint(1, 9)))
            records.append({
                "_id": f"sensitive:{label.lower()}:{i}",
                "source": "synthetic",
                "license": "generated by bench/build_sensitive.py",
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "char_len": len(text),
                "label": label,
                "clause_id": clause,
                "expected_span": span,
                "bucket": "SENSITIVE",
                "text": text,
                "synthetic": True,
            })

    # ---- HARD_NEGATIVE bucket — labelled BENIGN, reported as its own line ----
    hn = 0
    for name, template in HARD_NEGATIVES:
        for _ in range(3):
            text = template.replace("{pan}", rng.choice(STRIPE_TEST_PANS))
            records.append({
                "_id": f"hardneg:{hn}",
                "source": "hand-written hard negatives",
                "license": "generated by bench/build_sensitive.py",
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "char_len": len(text),
                "label": "BENIGN",
                "clause_id": "NONE",
                "expected_span": None,
                "bucket": "HARD_NEGATIVE",
                "trap": name,
                "text": text,
                "synthetic": True,
            })
            hn += 1

    rng.shuffle(records)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    counts: dict[str, int] = {}
    for r in records:
        k = r["bucket"] if r["bucket"] == "HARD_NEGATIVE" else r["label"]
        counts[k] = counts.get(k, 0) + 1

    manifest = {
        "corpus": out_path.name,
        "version": "sensitive_v1",
        "seed": seed,
        "n": len(records),
        "n_sensitive": sum(1 for r in records if r["bucket"] == "SENSITIVE"),
        "n_hard_negative": hn,
        "all_synthetic": True,
        "carriers": len(CARRIERS),
        "reproduce": f"python bench/build_sensitive.py --seed {seed} --out {out_path}",
        "counts": counts,
        "honest_framing": (
            "Our sensitive set is synthetic, so recall is an upper bound. Our benign set "
            "is human-written, so FPR is the number we stand behind."
        ),
        "notes": [
            "Every artefact is embedded in one of the carrier templates — never a bare PAN.",
            "All credentials are structurally shaped but synthetic; none is or was live.",
            "HARD_NEGATIVE items are labelled BENIGN and reported as their own line.",
        ],
    }
    out_path.with_name(out_path.stem + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"wrote {len(records)} records → {out_path}")
    for k, v in sorted(counts.items()):
        print(f"  {k:22s} {v}")
    print(f"\ncarrier templates: {len(CARRIERS)}")
    print(f"hard negatives:    {hn}  (labelled BENIGN, reported separately)")
    print("\nRecall from this corpus is an UPPER BOUND. Say so in the submission.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the sensitive + hard-negative corpus.")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--out", type=Path, default=Path("data/sensitive_v1.jsonl"))
    a = ap.parse_args()
    return build(a.seed, a.out)


if __name__ == "__main__":
    sys.exit(main())
