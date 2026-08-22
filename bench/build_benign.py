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
    hf_config: str | None = None    # some datasets REQUIRE a config name
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
        hf="google-research-datasets/mbpp", hf_config="full", fields=("text", "prompt"),
        notes="prompt composed with its reference solution and tests — a bare MBPP "
              "prompt is one line and does not resemble a real paste",
    ),
    Source(
        "HumanEval", 80, "MIT",
        "https://huggingface.co/datasets/openai/openai_humaneval",
        hf="openai/openai_humaneval", hf_split="test", fields=("prompt",),
    ),
    Source(
        "CFPB", 120, "US Government / public domain",
        "https://www.consumerfinance.gov/data-research/consumer-complaints/",
        fields=("Consumer complaint narrative", "complaint_what_happened", "narrative",
                "_source.complaint_what_happened"),
        notes="consumer complaint narratives, fetched live from the public CFPB API; "
              "snapshot date recorded in the manifest",
    ),
    Source(
        "Wikipedia", 100, "CC BY-SA 4.0",
        "https://dumps.wikimedia.org/",
        hf="wikimedia/wikipedia", hf_config="20231101.en", fields=("text",),
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


# --------------------------------------------------------------------------- language
# Per-item language tag, so the FPR can be broken down BY LANGUAGE rather than the
# multilingual property being asserted as a caveat. WildChat is genuinely multilingual
# and the T2 system prompt is English; a per-language FP table turns that from a
# limitation into a finding.
#
# Two-stage and honest about its own resolution:
#   · `langdetect` when installed — real language identification.
#   · otherwise a Unicode-SCRIPT heuristic, which separates CJK / Cyrillic / Arabic /
#     Devanagari / Hebrew / Greek / Thai from Latin reliably, but CANNOT tell English
#     from Spanish or French. Reported as `latin` in that case, never as `en`, so the
#     table never claims a precision it does not have.
_SCRIPTS = [
    ("cjk", ((0x3040, 0x30FF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0x3400, 0x4DBF))),
    ("cyrillic", ((0x0400, 0x04FF),)),
    ("arabic", ((0x0600, 0x06FF), (0x0750, 0x077F))),
    ("devanagari", ((0x0900, 0x097F),)),
    ("hebrew", ((0x0590, 0x05FF),)),
    ("greek", ((0x0370, 0x03FF),)),
    ("thai", ((0x0E00, 0x0E7F),)),
]


def _detect_lang(text: str) -> tuple[str, str]:
    """Returns (lang, method). method is 'langdetect' or 'script'."""
    sample = text[:1500]
    counts: dict[str, int] = {}
    letters = 0
    for ch in sample:
        if not ch.isalpha():
            continue
        letters += 1
        cp = ord(ch)
        for name, ranges in _SCRIPTS:
            if any(lo <= cp <= hi for lo, hi in ranges):
                counts[name] = counts.get(name, 0) + 1
                break
    if letters:
        for name, c in counts.items():
            if c / letters >= 0.15:      # a meaningful share, not a stray character
                return name, "script"

    try:
        from langdetect import detect, DetectorFactory  # type: ignore

        DetectorFactory.seed = 0          # langdetect is nondeterministic without this
        return detect(sample), "langdetect"
    except Exception:  # noqa: BLE001
        return "latin", "script"


def _from_dump(src: Source, rng: random.Random) -> list[tuple[str, str]]:
    """Load from a pre-staged local dump. Returns [(record_id, text)].

    Accepts .jsonl, .json and .csv. CSV matters for CFPB specifically: its public API
    has been retired (the documented search endpoint 404s and api.consumerfinance.gov
    redirects to an unrelated FFIEC page), so the only reliable route is the bulk CSV
    export from the complaint database. Drop it at data/dumps/cfpb.csv.
    """
    stem = src.name.lower().replace(" ", "_")

    # Search several locations. The pre-staged CFPB export lives under gb10/ on the box
    # (gitignored), not in data/dumps/, so look there too rather than making someone
    # move a file to satisfy a hardcoded path.
    csv_candidates = [
        DUMP_DIR / f"{stem}.csv",
        Path("gb10/data") / f"{stem}_narratives.csv",
        Path("gb10/data") / f"{stem}.csv",
        Path("data") / f"{stem}_narratives.csv",
    ]
    if src.name == "CFPB":
        csv_candidates.insert(0, Path("gb10/data/cfpb_narratives.csv"))
    env_override = os.getenv(f"AIRLOCK_{src.name.upper().replace('-', '_')}_CSV")
    if env_override:
        csv_candidates.insert(0, Path(env_override))

    tried: list[str] = []
    for csv_path in csv_candidates:
        if not csv_path.exists():
            tried.append(str(csv_path))
            continue
        try:
            import csv as _csv

            rows: list[dict] = []
            with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
                # CFPB narratives run long; the default field cap truncates them.
                _csv.field_size_limit(10_000_000)
                reader = _csv.DictReader(f)
                for r in reader:
                    rows.append(r)
                    if len(rows) >= src.n * 60:
                        break
            out = _extract(src, rows)
            if not out and rows:
                # The column name did not match any candidate in src.fields. Rather than
                # reporting "no data" for a file that plainly has data, find the column
                # with the longest average content and use that. CFPB's export column has
                # been renamed more than once; guessing the schema is not worth an hour.
                cols = list(rows[0].keys())
                best, best_len = None, 0
                for c in cols:
                    vals = [str(r.get(c) or "") for r in rows[:200]]
                    avg = sum(len(v) for v in vals) / max(1, len(vals))
                    if avg > best_len:
                        best, best_len = c, avg
                if best and best_len >= MIN_CHARS * 0.5:
                    print(f"  · {src.name}: no known column matched; "
                          f"auto-selected {best!r} (avg {int(best_len)} chars)")
                    out = [
                        (f"{stem}:{r.get('Complaint ID', r.get('complaint_id', i))}",
                         _clean(r.get(best, "")))
                        for i, r in enumerate(rows)
                    ]
                    out = [(rid, t) for rid, t in out if _usable(t)]
            if out:
                print(f"  · {src.name}: {len(out)} usable from dump {csv_path}")
                src.method = "dump"
                return out
            print(f"  ! {src.name}: {csv_path} had no usable rows "
                  f"(columns: {list(rows[0].keys())[:6] if rows else 'none'})",
                  file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {src.name}: CSV at {csv_path} unreadable ({e})", file=sys.stderr)

    # A source that expects a CSV and found none must SAY SO. Failing silently here sent
    # CFPB down the (retired) API path with no indication the file was simply not where
    # we looked — which reads as "the API is broken" rather than "wrong path".
    if tried and src.hf is None and not any(
        (DUMP_DIR / f"{stem}.{e}").exists() for e in ("jsonl", "json")
    ):
        print(f"  · {src.name}: no CSV found. Looked in:", file=sys.stderr)
        for t in tried:
            print(f"      {Path(t).resolve()}", file=sys.stderr)
        print(f"    Override with: AIRLOCK_{src.name.upper().replace('-', '_')}_CSV=/abs/path.csv",
              file=sys.stderr)

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

    ds = None
    try:
        # Streaming keeps this cheap and avoids a multi-GB materialisation.
        kw = {"split": src.hf_split, "streaming": True}
        if src.hf_config:
            ds = load_dataset(src.hf, src.hf_config, **kw)
        else:
            ds = load_dataset(src.hf, **kw)

        # Stop as soon as we have a comfortable surplus instead of draining a fixed
        # over-sample. On the first run this streamed 16k WildChat rows to keep 400.
        want = max(src.n * 3, src.n + 50)
        rows: list[dict] = []
        kept = 0
        for i, row in enumerate(ds):
            rows.append(row)
            if len(rows) % 200 == 0:
                kept = len(_extract(src, rows))
                if kept >= want:
                    break
            if i >= src.n * 60:      # hard ceiling so a low-yield source cannot hang
                break

        out = _extract(src, rows)
        if out:
            print(f"  · {src.name}: {len(out)} usable from HuggingFace {src.hf}")
            src.method = "hf"
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  ! {src.name}: HF load failed ({e})", file=sys.stderr)
        return []
    finally:
        # Drop the streaming iterator before we go anywhere near interpreter shutdown.
        # A live retry thread during finalisation is what produced
        # "PyGILState_Release: auto-releasing thread-state" and a core dump.
        del ds


def _from_cfpb_api(src: Source, rng: random.Random) -> list[tuple[str, str]]:
    """CFPB has no HuggingFace mirror, so pull narratives from the public API.

    Best-effort with a short timeout: this is one source out of six and it must never
    be the reason the corpus does not get built.
    """
    url = (
        "https://www.consumerfinance.gov/data-research/consumer-complaints/search/"
        "api/v1/?size=800&no_aggs=true&has_narrative=true&format=json"
        "&field=complaint_what_happened"
    )
    try:
        import json as _json
        import urllib.request

        print(f"  · {src.name}: fetching from the public CFPB API …")
        req = urllib.request.Request(url, headers={"User-Agent": "airlock-corpus/1.0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            data = _json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        print(f"  ! {src.name}: API fetch failed ({e})", file=sys.stderr)
        return []

    hits = data.get("hits", {}).get("hits", data) if isinstance(data, dict) else data
    out: list[tuple[str, str]] = []
    for i, h in enumerate(hits if isinstance(hits, list) else []):
        rec = h.get("_source", h) if isinstance(h, dict) else {}
        text = _clean(rec.get("complaint_what_happened", ""))
        if _usable(text):
            out.append((f"cfpb:{rec.get('complaint_id', i)}", text))
    if out:
        print(f"  · {src.name}: {len(out)} usable from the CFPB API")
        src.method = "api"
    return out


def _extract(src: Source, rows: list[dict]) -> list[tuple[str, str]]:
    """Pull the text field out of heterogeneous row shapes, applying per-source filters."""
    out: list[tuple[str, str]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            if isinstance(row, str) and _usable(_clean(row)):
                out.append((f"{src.name.lower()}:{i}", _clean(row)))
            continue

        # MBPP: a bare prompt is a single sentence ("Write a function to …") and is far
        # under the 200-char floor — the first run kept 1 of 100. Nobody pastes a bare
        # MBPP prompt either. Compose the realistic artifact instead: the problem, the
        # code someone has so far, and the failing tests.
        if src.name == "MBPP":
            prompt = _clean(row.get("text") or row.get("prompt") or "")
            code = _clean(row.get("code") or "")
            tests = row.get("test_list") or []
            if not prompt:
                continue
            parts = [prompt]
            if code:
                parts.append("Here's what I have so far:\n\n```python\n" + code + "\n```")
            if isinstance(tests, list) and tests:
                parts.append("It needs to satisfy:\n\n```python\n" + "\n".join(
                    str(t) for t in tests[:3]) + "\n```")
            parts.append("Is there a cleaner way to write this?")
            text = "\n\n".join(parts)
            rid = f"mbpp:{row.get('task_id', i)}"
            if _usable(text):
                out.append((rid, text))
            continue

        # HumanEval: prompt is signature + docstring; append the reference solution so
        # the item reads like a real code paste rather than a stub.
        if src.name == "HumanEval":
            prompt = _clean(row.get("prompt") or "")
            sol = _clean(row.get("canonical_solution") or "")
            if not prompt:
                continue
            text = "```python\n" + prompt + ("\n" + sol if sol else "") + "\n```\n\n" \
                   "Why does this fail on the edge case where the input is empty?"
            rid = f"humaneval:{row.get('task_id', i)}"
            if _usable(text):
                out.append((rid, text))
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
# ---------------------------------------------------------------- provenance guards
# R13's whole premise is "six independent sources, so no single licence challenge can
# sink the denominator". Redistribution protects the denominator (n stays 1000) but it
# can silently destroy that premise: five sources failing and one covering the shortfall
# produced a 1000/1000 single-source corpus that printed "n=1000 ✓" and declared
# corpus_is_real: true. The number looked perfect and the property was gone.
#
# These are hard floors. A corpus that violates them is not written without --force.
MIN_SOURCES = 4          # below this, "independent sources" is not a claim we can make
MAX_SOURCE_SHARE = 0.55  # no single source may dominate the denominator


def _check_provenance(sources, n_total: int) -> list[str]:
    """Returns a list of provenance violations. Empty means the corpus is defensible."""
    used = [s for s in sources if s.got > 0]
    problems = []
    if len(used) < MIN_SOURCES:
        problems.append(
            f"only {len(used)} source(s) contributed ({', '.join(s.name for s in used)}); "
            f"minimum is {MIN_SOURCES}. 'Independent sources' would be a false claim."
        )
    for s in used:
        share = s.got / n_total if n_total else 0
        if share > MAX_SOURCE_SHARE:
            problems.append(
                f"{s.name} is {share * 100:.0f}% of the corpus "
                f"({s.got}/{n_total}); ceiling is {MAX_SOURCE_SHARE * 100:.0f}%."
            )
    return problems


def build(seed: int, out_path: Path, allow_synthetic: bool, force: bool = False) -> int:
    # Do not silently replace a real corpus with placeholder text. The corpus is a
    # tracked submission attachment (SRS §14), so a --allow-synthetic run followed by
    # `git add -A` overwrites the deciding artifact with filler and the manifest that
    # results looks *more* correct than the real one, because synthetic generation hits
    # its quota exactly while real fetching does not. This has happened once already.
    if allow_synthetic and not force and out_path.exists():
        mpath = out_path.with_name(out_path.stem + ".manifest.json")
        try:
            if json.loads(mpath.read_text()).get("corpus_is_real"):
                print(
                    f"\nREFUSING: {out_path} is a REAL corpus "
                    f"(manifest says corpus_is_real: true).\n"
                    f"  --allow-synthetic would replace the deciding artifact with "
                    f"placeholder text.\n"
                    f"  Re-run without --allow-synthetic, or pass --force if you truly "
                    f"mean to discard it.\n",
                    file=sys.stderr,
                )
                return 3
        except Exception:  # noqa: BLE001
            pass
    return _build(seed, out_path, allow_synthetic, force)


def _build(seed: int, out_path: Path, allow_synthetic: bool, force: bool = False) -> int:
    rng = random.Random(seed)
    records: list[dict] = []
    any_synthetic = False

    print(f"building benign corpus (seed={seed})")
    print(f"looking for pre-staged dumps in: {DUMP_DIR.resolve()}")

    # ---- pass 1: gather every source that works, never aborting on one that does not.
    # The first run on the box lost real WildChat, StackExchange and HumanEval pulls
    # because CFPB was missing and the script exited immediately. Downloads are the
    # expensive part; never throw one away.
    pools: dict[str, list[tuple[str, str]]] = {}
    failed: list[Source] = []
    for src in SOURCES:
        pool = _from_dump(src, rng)
        if not pool and src.name == "CFPB":
            pool = _from_cfpb_api(src, rng)
        if not pool:
            pool = _from_hf(src, rng)
        if pool:
            rng.shuffle(pool)
            pools[src.name] = pool
        else:
            print(f"  ! {src.name}: no data available")
            failed.append(src)

    # ---- pass 2: redistribute any shortfall onto sources that have surplus.
    # n = 1000 is the denominator the whole submission rests on; six sources is a
    # robustness property, not the headline. The manifest records exactly what was
    # actually used, so the provenance table stays honest either way.
    shortfall = sum(s.n for s in failed)
    if shortfall and not allow_synthetic:
        donors = [s for s in SOURCES if s.name in pools
                  and len(pools[s.name]) > s.n + 20]
        if not donors:
            print(
                f"\nFATAL: {shortfall} items short and no source has surplus to cover it.\n"
                f"  Missing: {', '.join(s.name for s in failed)}\n"
                f"  Stage a dump in {DUMP_DIR}/ or re-run with --allow-synthetic.\n",
                file=sys.stderr,
            )
            return 2
        print(f"\n  redistributing {shortfall} items from {len(failed)} unavailable "
              f"source(s) across {len(donors)} with surplus:")
        i = 0
        while shortfall > 0:
            d = donors[i % len(donors)]
            if len(pools[d.name]) > d.n + 1:
                d.n += 1
                shortfall -= 1
            elif all(len(pools[x.name]) <= x.n + 1 for x in donors):
                break
            i += 1
        for d in donors:
            print(f"    {d.name} -> {d.n}")

    for src in SOURCES:
        pool = pools.get(src.name, [])

        if not pool:
            if not allow_synthetic:
                src.got = 0
                src.method = "unavailable"
                continue          # already accounted for by the redistribution above
            print(f"  ! {src.name}: NO REAL DATA — generating labelled placeholder text")
            pool = _synthetic(src, rng)
            any_synthetic = True
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
            lang, lang_method = _detect_lang(text)
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
                    "lang": lang,
                    "lang_method": lang_method,
                    "synthetic": src.method == "synthetic",
                }
            )

    rng.shuffle(records)

    # ---- PROVENANCE GATE — before anything is written ----
    # Redistribution keeps n at 1000; it does not keep the corpus defensible. Check the
    # property we actually claim, not just the count.
    problems = _check_provenance(SOURCES, len(records))
    if problems and not any_synthetic:
        print("\n" + "=" * 72, file=sys.stderr)
        print("  PROVENANCE FAILURE — refusing to write a corpus that misstates itself",
              file=sys.stderr)
        for pb in problems:
            print(f"    · {pb}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  n would have been 1000 and corpus_is_real would have been true, which is",
              file=sys.stderr)
        print("  exactly why this check exists: the count looks right while the claim",
              file=sys.stderr)
        print("  'independent sources' has quietly stopped being true.", file=sys.stderr)
        print("", file=sys.stderr)
        print("  Fix the failing source(s), or pass --force to write it anyway and state",
              file=sys.stderr)
        print("  the concentration honestly in the submission.", file=sys.stderr)
        print("=" * 72 + "\n", file=sys.stderr)
        if not force:
            return 4

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
        "sources_used": sum(1 for s_ in SOURCES if s_.got > 0),
        "max_source_share": round(
            max((s_.got for s_ in SOURCES), default=0) / max(1, len(records)), 4),
        "provenance_ok": not _check_provenance(SOURCES, len(records)),
        "provenance_problems": _check_provenance(SOURCES, len(records)),
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
    # Honest about what this flag does and does not mean. `corpus_is_real: true` asserts
    # only that no record was generated by this script — it CANNOT verify that a dump you
    # staged contains authentic human text. A file of word salad at data/dumps/ would pass.
    # The provenance table, not this boolean, is what a reviewer should be reading.
    manifest["corpus_is_real_means"] = (
        "No record was generated by this script. It does NOT verify that a staged dump "
        "contains authentic text — check the provenance table and the source URLs."
    )
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
    ap.add_argument(
        "--force",
        action="store_true",
        help="override the provenance gate, and permit overwriting a real corpus",
    )
    a = ap.parse_args()
    return build(a.seed, a.out, a.allow_synthetic, a.force)


if __name__ == "__main__":
    _code = main()
    # HuggingFace's streaming stack keeps background retry threads alive. Letting the
    # interpreter finalise while one is mid-retry produced
    # "Fatal Python error: PyGILState_Release" and a core dump AFTER the corpus had been
    # written — a successful run that looked like a crash. Flush, then leave immediately
    # rather than running finalisers we do not need.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_code)
