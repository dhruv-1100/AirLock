#!/usr/bin/env python3
"""bench/t1_offline.py — owner C.

Scans a corpus with Tier 1 ONLY, in-process, with no service and no model running.

    python bench/t1_offline.py                       # benign corpus
    python bench/t1_offline.py --corpus data/sensitive_v1.jsonl

Why this exists, given `bench/run_fpr.py` already measures the full router:

1.  **It is ablation row 1** (T1-only) and it needs no GPU, so it is available hours
    before the vLLM servers are warm and it costs nothing to re-run.
2.  **T1-HIGH is the only tier permitted to block without a model.** Its false positives
    pass straight through to the reported total — no later stage can rescue them. That
    makes T1-HIGH FPR the single number most worth knowing early, and the one most
    embarrassing to discover late.
3.  It gives C the hand-adjudication list before the harness has run.

MEDIUM-confidence hits escalate to T2 and are NOT blocks (SRS §6.2: `generic-api-key` is
MEDIUM → escalate, never auto-block). They are reported separately here because they set
a floor under the escalation rate, which is the seats-per-box multiplier (NFR-T6).
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier-1-only offline scan.")
    ap.add_argument("--corpus", default="data/benign_v1.jsonl")
    ap.add_argument("--out", default="results/t1_offline.json")
    ap.add_argument("--show", type=int, default=10)
    a = ap.parse_args()

    from services.inspect.tiers import t1

    path = Path(a.corpus)
    if not path.exists():
        print(f"FATAL: {path} not found", file=sys.stderr)
        return 2
    rows = [json.loads(l) for l in path.open() if l.strip()]

    benign_corpus = "benign" in path.name
    by_conf: collections.Counter = collections.Counter()
    by_label: collections.Counter = collections.Counter()
    by_source: dict[str, dict] = {}
    high, medium = [], []

    for r in rows:
        src = by_source.setdefault(r.get("source", "?"), {"n": 0, "high": 0, "medium": 0})
        src["n"] += 1
        res = t1.scan(r.get("text", ""))
        label = getattr(res, "label", None)
        conf = getattr(res, "confidence", None)
        if not label or label == "BENIGN":
            continue
        by_conf[conf] += 1
        by_label[label] += 1
        item = {
            "_id": r.get("_id"), "source": r.get("source"), "label": label,
            "confidence": conf, "spans": list(getattr(res, "spans", []) or []),
            "excerpt": (r.get("text", "")[:200]),
        }
        if conf == "HIGH":
            high.append(item)
            src["high"] += 1
        else:
            medium.append(item)
            src["medium"] += 1

    n = len(rows)

    def wilson(k, nn, z=1.959963985):
        if nn == 0:
            return [0.0, 0.0]
        import math

        p = k / nn
        d = 1 + z * z / nn
        c = (p + z * z / (2 * nn)) / d
        h = z * math.sqrt(p * (1 - p) / nn + z * z / (4 * nn * nn)) / d
        return [max(0.0, c - h), min(1.0, c + h)]

    lo, hi = wilson(len(high), n)
    out = {
        "corpus": str(path),
        "n": n,
        "tier": "T1-only",
        "t1_high_blocks": len(high),
        "t1_medium_escalations": len(medium),
        "t1_high_rate": len(high) / n if n else None,
        "t1_high_ci95": [lo, hi],
        "escalation_floor": len(medium) / n if n else None,
        "by_confidence": dict(by_conf),
        "by_label": dict(by_label),
        "by_source": by_source,
        "high_items": high,
        "medium_items": medium[: a.show * 5],
    }
    Path("results").mkdir(exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))

    print(f"corpus            {path}  (n={n})")
    print(f"by confidence     {dict(by_conf) or '{}'}")
    print(f"by label          {dict(by_label) or '{}'}")
    print()
    if benign_corpus:
        if not high:
            print(f"  T1-HIGH false positives: 0 / {n}")
            print(f"  -> below {3 / n * 100:.2f}% at 95% confidence by the rule of three.")
            print("     NEVER write 'zero'.")
        else:
            print(f"  T1-HIGH false positives: {len(high)} / {n} "
                  f"= {len(high) / n * 100:.2f}% [{lo * 100:.2f}%, {hi * 100:.2f}%]")
            print("  These block with NO MODEL. No later tier can rescue them.")
        print(f"  T1-MEDIUM escalations to T2: {len(medium)} / {n} "
              f"= {len(medium) / n * 100:.1f}%  (a FLOOR under the escalation rate)")
    else:
        print(f"  T1-HIGH catches: {len(high)} / {n} = {len(high) / n * 100:.1f}% "
              f"(recall contribution with no model)")
        print(f"  T1-MEDIUM escalations: {len(medium)} / {n}")

    for item in high[: a.show]:
        print(f"\n  HIGH  {item['_id']}  {item['source']}  spans={item['spans']}")
        print(f"        {item['excerpt'][:140]}…")

    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
