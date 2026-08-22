#!/usr/bin/env python3
"""bench/build_benign.py — owner C. SRS §10 Phase 0, §14, Risk R13.

Builds `data/benign_v1.jsonl` — 1000 benign pastes **we did not write**. This is the
denominator under the deciding artifact of the entire submission, so provenance is
tracked per record and the corpus is regenerable with one seeded command.

    python bench/build_benign.py --seed 1337 --out data/benign_v1.jsonl

Composition (SRS §10 / §13):
    400  WildChat-1M first turns      ODC-BY
    200  Stack Exchange question bodies  CC BY-SA 4.0
    100  MBPP prompts                 CC-BY-4.0
     80  HumanEval docstrings         MIT
    120  CFPB consumer narratives     US Gov / public domain
    100  Wikipedia paragraphs         CC BY-SA 4.0
   ----
   1000

Six independent sources, so no single licence challenge can sink the denominator (R13).
If a judge raises the Stack Exchange LLM-training terms, the pre-computed answer is:
drop SE to 100, raise WildChat to 500, re-run this command, re-report.

============================== INTEGRITY GUARD ==============================
The submission claims these are real, human-written pastes. If real dumps are not
present this script REFUSES to write a corpus unless you pass --allow-synthetic, and
in that mode EVERY record is stamped `"synthetic": true`, the manifest carries
`corpus_is_real: false`, and bench/report.py will refuse to emit a headline FPR.
Synthetic filler is for wiring the harness end-to-end before the dumps land. It is
NEVER the number we stand behind.
=============================================================================
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

MIN_CHARS, MAX_CHARS = 200, 4000

# Where a pre-staged dump is looked for. Any of these forms works:
#   <dir>/<name>.jsonl  |  <dir>/<name>.json  |  HuggingFace cache via `datasets`
DUMP_DIR = Path(os.getenv("AIRLOCK_DUMP_DIR", "data/dumps"))


@dataclass
class Source:
    name: str
    n: int
    license: str
    url: str
    hf: str | None = None           # HuggingFace dataset id, if loadable
    hf_split: str = "train"
    fields: tuple[str, ...] = ()    # candidate text fields, first match wins
    snapshot: str = ""
    notes: str = ""
    got: int = 0
    method: str = field(default="")  # "dump" | "hf" | "synthetic"


SOURCES = [
    Source(
        "WildChat-1M", 400, "ODC-BY",
        "https://huggingface.co/datasets/allenai/WildChat-1M",
        hf="allenai/WildChat-1M", fields=("conversation",),
        notes="first user turn only; toxic==False; PII-redaction flag unset",
    ),
    Source(
        "StackExchange", 200, "CC BY-SA 4.0",
        "https://archive.org/details/stackexchange",
        hf="HuggingFaceH4/stack-exchange-preferences", fields=("question", "body", "text"),
        notes="question bodies; post ids retained in ATTRIBUTION.md",
    ),
    Source(
        "MBPP", 100, "CC-BY-4.0",
        "https://huggingface.co/datasets/google-research-datasets/mbpp",
        hf="google-research-datasets/mbpp", fields=("text", "prompt"),
    ),
    Source(
        "HumanEval", 80, "MIT",
        "https://huggingface.co/datasets/openai/openai_humaneval",
        hf="openai/openai_humaneval", hf_split="test", fields=("prompt",),
    ),
    Source(
        "CFPB", 120, "US Government / public domain",
        "https://www.consumerfinance.gov/data-research/consumer-complaints/",
        fields=("Consumer complaint narrative", "complaint_what_happened", "narrative"),
        notes="consumer complaint narratives; snapshot date recorded in the manifest",
    ),
    Source(
        "Wikipedia", 100, "CC BY-SA 4.0",
        "https://dumps.wikimedia.org/",
        hf="wikimedia/wikipedia", fields=("text",),
        notes="lead paragraphs, one per article",
    ),
]


# --------------------------------------------------------------------------- loaders
def _clean(t: str) -> str:
    t = re.sub(r"\r\n?", "\n", str(t or ""))
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _usable(t: str) -> bool:
    return MIN_CHARS <= len(t) <= MAX_CHARS


def _from_dump(src: Source, rng: random.Random) -> list[tuple[str, str]]:
    """Load from a pre-staged local dump. Returns [(record_id, text)]."""
    stem = src.name.lower().replace(" ", "_")
    for ext in ("jsonl", "json"):
        p = DUMP_DIR / f"{stem}.{ext}"
        if not p.exists():
            continue
        rows: list[dict] = []
        try:
            if ext == "jsonl":
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            rows.append(json.loads(line))
            else:
                data = json.loads(p.read_text(encoding="utf-8"))
                rows = data if isinstance(data, list) else data.get("data", [])
        except Exception as e:  # noqa: BLE001
            print(f"  ! {src.name}: dump at {p} unreadable ({e})", file=sys.stderr)
            return []
        out = _extract(src, rows)
        if out:
            print(f"  · {src.name}: {len(out)} usable from dump {p}")
            src.method = "dump"
        return out
    return []


def _from_hf(src: Source, rng: random.Random) -> list[tuple[str, str]]:
    if not src.hf:
        return []
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        return []
    try:
        # streaming keeps this cheap and avoids a multi-GB materialisation
        ds = load_dataset(src.hf, split=src.hf_split, streaming=True)
        rows = []
        for i, row in enumerate(ds):
            rows.append(row)
            if i >= src.n * 40:      # generous over-sample; we filter hard below
                break
        out = _extract(src, rows)
        if out:
            print(f"  · {src.name}: {len(out)} usable from HuggingFace {src.hf}")
            src.method = "hf"
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  ! {src.name}: HF load failed ({e})", file=sys.stderr)
        return []


def _extract(src: Source, rows: list[dict]) -> list[tuple[str, str]]:
    """Pull the text field out of heterogeneous row shapes, applying per-source filters."""
    out: list[tuple[str, str]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            if isinstance(row, str) and _usable(_clean(row)):
                out.append((f"{src.name.lower()}:{i}", _clean(row)))
            continue

        # WildChat: first USER turn only, and honour the dataset's own safety flags.
        if src.name == "WildChat-1M":
            if row.get("toxic") is True:
                continue
            if row.get("redacted") is True:      # PII-redaction flag set → skip
                continue
            conv = row.get("conversation") or []
            text = ""
            for turn in conv if isinstance(conv, list) else []:
                if isinstance(turn, dict) and turn.get("role") == "user":
                    text = turn.get("content", "")
                    break
            rid = f"wildchat:{row.get('conversation_hash', i)}"
        else:
            text = ""
            for f in src.fields:
                if row.get(f):
                    text = row[f]
                    break
            if isinstance(text, list):  # some SE dumps nest
                text = text[0].get("text", "") if text and isinstance(text[0], dict) else ""
            rid = f"{src.name.lower()}:{row.get('id', row.get('task_id', i))}"

        text = _clean(text)
        if _usable(text):
            out.append((rid, text))
    return out


# --------------------------------------------------------------------------- synthetic filler
_SYN_TEMPLATES = [
    "How do I {v} a {n} in {lang} without using {lib}? I tried the obvious loop but it "
    "gets quadratic on large inputs and my tests time out at around {k} elements.",
    "Our team is debating whether to {v} the {n} layer before we scale up. What are the "
    "trade-offs, and is there a rule of thumb for when it stops being worth it?",
    "I keep getting a {n} error when I {v} the config in {lang}. The stack trace points "
    "at line {k} but that line looks fine to me. What am I misreading?",
    "Can someone explain the difference between a {n} and a {n2} in plain terms? Every "
    "explanation I find assumes I already know {lib} and I do not.",
    "Writing a short piece about {n} for a general audience. Is it accurate to say it "
    "{v}s the {n2} rather than replacing it, or is that too simplified?",
]
_V = ["reverse", "flatten", "memoise", "normalise", "batch", "parse", "cache", "index"]
_N = ["linked list", "binary tree", "hash map", "queue", "priority queue", "trie", "graph"]
_N2 = ["array", "set", "buffer", "stream", "matrix", "iterator"]
_LANG = ["Python", "Go", "Rust", "TypeScript", "Java", "C++"]
_LIB = ["itertools", "lodash", "numpy", "the standard library", "an external crate"]


def _synthetic(src: Source, rng: random.Random) -> list[tuple[str, str]]:
    out = []
    for i in range(src.n):
        body = " ".join(
            rng.choice(_SYN_TEMPLATES).format(
                v=rng.choice(_V), n=rng.choice(_N), n2=rng.choice(_N2),
                lang=rng.choice(_LANG), lib=rng.choice(_LIB), k=rng.randint(50, 90000),
            )
            for _ in range(rng.randint(2, 6))
        )
        if len(body) < MIN_CHARS:
            body += (
                " Additional context: this is placeholder text generated locally to "
                "exercise the harness end to end. It is not a real human paste and must "
                "not be reported as one."
            )
        out.append((f"synthetic:{src.name.lower()}:{i}", body[:MAX_CHARS]))
    src.method = "synthetic"
    return out


# --------------------------------------------------------------------------- build
def build(seed: int, out_path: Path, allow_synthetic: bool) -> int:
    rng = random.Random(seed)
    records: list[dict] = []
    any_synthetic = False

    print(f"building benign corpus (seed={seed})")
    print(f"looking for pre-staged dumps in: {DUMP_DIR.resolve()}")

    for src in SOURCES:
        pool = _from_dump(src, rng) or _from_hf(src, rng)

        if not pool:
            if not allow_synthetic:
                print(
                    f"\nFATAL: no data for {src.name}.\n"
                    f"  Stage a dump at {DUMP_DIR}/{src.name.lower().replace(' ', '_')}.jsonl\n"
                    f"  or `pip install datasets` to pull {src.hf or '(no HF id)'},\n"
                    f"  or re-run with --allow-synthetic to wire the harness against\n"
                    f"  clearly-labelled placeholder text.\n",
                    file=sys.stderr,
                )
                return 2
            print(f"  ! {src.name}: NO REAL DATA — generating labelled placeholder text")
            pool = _synthetic(src, rng)
            any_synthetic = True

        rng.shuffle(pool)
        # de-duplicate by content hash before truncating to n
        seen: set[str] = set()
        picked = []
        for rid, text in pool:
            h = hashlib.sha256(text.encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            picked.append((rid, text, h))
            if len(picked) >= src.n:
                break

        if len(picked) < src.n:
            print(f"  ! {src.name}: only {len(picked)}/{src.n} usable records", file=sys.stderr)
        src.got = len(picked)

        for rid, text, h in picked:
            records.append(
                {
                    "_id": rid,
                    "source": src.name,
                    "license": src.license,
                    "provenance_url": src.url,
                    "sha256": h,
                    "char_len": len(text),
                    "label": "BENIGN",
                    "text": text,
                    "synthetic": src.method == "synthetic",
                }
            )

    rng.shuffle(records)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest = {
        "corpus": out_path.name,
        "version": "benign_v1",
        "seed": seed,
        "n": len(records),
        "corpus_is_real": not any_synthetic,
        "n_synthetic": sum(1 for r in records if r["synthetic"]),
        "reproduce": f"python bench/build_benign.py --seed {seed} --out {out_path}",
        "min_chars": MIN_CHARS,
        "max_chars": MAX_CHARS,
        "sources": [
            {
                "name": s.name, "requested": s.n, "got": s.got, "method": s.method,
                "license": s.license, "url": s.url, "notes": s.notes,
            }
            for s in SOURCES
        ],
    }
    if any_synthetic:
        manifest["WARNING"] = (
            "THIS CORPUS CONTAINS SYNTHETIC PLACEHOLDER TEXT. It exists to wire the "
            "harness end to end. Do NOT report an FPR from it. bench/report.py will "
            "refuse to emit a headline number while corpus_is_real is false."
        )

    mpath = out_path.with_name(out_path.stem + ".manifest.json")
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _write_attribution(Path("data/ATTRIBUTION.md"), manifest)

    print(f"\nwrote {len(records)} records → {out_path}")
    print(f"wrote manifest        → {mpath}")
    print(f"wrote attribution     → data/ATTRIBUTION.md")
    if any_synthetic:
        print("\n*** CORPUS IS NOT REAL — corpus_is_real=false. Do not report an FPR. ***")
        return 1
    if len(records) != 1000:
        print(f"\n! n={len(records)}, expected 1000. The denominator must be 1000.")
        return 1
    print("\nn=1000 ✓  — this is the denominator under the deciding artifact.")
    return 0


def _write_attribution(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Corpus attribution — `benign_v1`",
        "",
        "Six independent sources, so no single licence challenge can sink the denominator.",
        "",
        f"Reproduce: `{manifest['reproduce']}`",
        "",
        "| Source | n | Licence | Method | URL |",
        "|---|---|---|---|---|",
    ]
    for s in manifest["sources"]:
        lines.append(
            f"| {s['name']} | {s['got']} | {s['license']} | {s['method'] or '—'} | {s['url']} |"
        )
    lines += [
        "",
        f"**Total: {manifest['n']}** · `corpus_is_real: {str(manifest['corpus_is_real']).lower()}`",
        "",
        "## Notes",
        "",
        "- WildChat records with `toxic == True` or the PII-redaction flag set are excluded.",
        "- Only the first user turn of a WildChat conversation is used.",
        "- Records are de-duplicated by SHA-256 of the text before sampling.",
        "- Length window: 200–4000 characters.",
        "",
        "## If a judge challenges the Stack Exchange terms",
        "",
        "Pre-computed answer: drop Stack Exchange to 100 and raise WildChat to 500",
        "(ODC-BY, no such condition), then re-run the single seeded command above and",
        "re-report. The corpus is regenerable; the number moves, the method does not.",
    ]
    if manifest.get("WARNING"):
        lines.insert(2, f"> **{manifest['WARNING']}**\n")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the benign evaluation corpus.")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--out", type=Path, default=Path("data/benign_v1.jsonl"))
    ap.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="permit clearly-labelled placeholder text when a real dump is missing",
    )
    a = ap.parse_args()
    return build(a.seed, a.out, a.allow_synthetic)


if __name__ == "__main__":
    sys.exit(main())
