"""Phase 3 dependency map: "B ← A (scores_benign.json): unblocked by A writing
a synthetic 1000-row scores file at 14:35 with the right shape, so B's slider
is finished before the real scores exist."

Emits results/scores_benign.json in the exact combined shape C's run_fpr.py
writes ({benign, sensitive, threshold_default, n, corpus_is_real, items}),
with corpus_is_real=false so nothing downstream can mistake it for a
reportable run. Deterministic under --seed.

Usage: python bench/make_synthetic_scores.py --n 1000
"""

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--n-sensitive", type=int, default=400)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--out", default=None,
                    help="output path (default results/scores_benign.json); "
                         "tests MUST pass this — never clobber the team file")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    bitems = []
    for i in range(args.n):
        # ~86% resolve deterministically at T0/T1 with p_block ≈ 0. The
        # escalated tail spreads across the T2 posterior, and ~2% of ALL items
        # land in 0.30–0.80 so the slider visibly trades FPR against recall as
        # it moves (INTEGRATION-B.md: perfectly-separated scores look inert).
        r = rng.random()
        if r < 0.86:
            p, tier, ms = rng.uniform(0.0, 0.05), rng.choice(["T0", "T1"]), rng.randint(1, 12)
        elif r < 0.98:
            p, tier, ms = min(0.999, rng.betavariate(1.2, 8)), "T2", rng.randint(180, 550)
        else:
            p, tier, ms = rng.uniform(0.30, 0.80), "T2", rng.randint(180, 550)
        bitems.append({"_id": f"synthetic:{i:04d}", "source": "SYNTHETIC",
                       "sha256": "", "char_len": rng.randint(200, 4000),
                       "label": "BENIGN",
                       "verdict": "BLOCK" if p >= args.threshold else "ALLOW",
                       "p_block": round(p, 4), "latency_ms": ms, "tier": tier,
                       "predicted_label": "BENIGN", "clause_id": "NONE",
                       "evidence_spans": [], "evidence_verified": True,
                       "override": None, "http_status": 200})

    sitems = []
    for i in range(args.n_sensitive):
        # ~8% of sensitive items score low (misses) so recall genuinely drops
        # as tau rises — a slider with nothing to trade demonstrates nothing.
        p = (rng.uniform(0.05, 0.50) if rng.random() < 0.08
             else max(0.0, min(0.999, rng.betavariate(8, 1.3))))
        sitems.append({"_id": f"synthetic-s:{i:04d}", "source": "SYNTHETIC",
                       "sha256": "", "char_len": rng.randint(200, 4000),
                       "label": "SENSITIVE",
                       "verdict": "BLOCK" if p >= args.threshold else "ALLOW",
                       "p_block": round(p, 4),
                       "latency_ms": rng.randint(180, 550),
                       "tier": rng.choice(["T1", "T2"]),
                       "predicted_label": "CREDENTIAL", "clause_id": "POL-001",
                       "evidence_spans": [], "evidence_verified": True,
                       "override": None, "http_status": 200})

    out = Path(args.out) if args.out else ROOT / "results" / "scores_benign.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "benign": [r["p_block"] for r in bitems],
        "sensitive": [r["p_block"] for r in sitems],
        "threshold_default": args.threshold,
        "n": len(bitems),
        "corpus_is_real": False,
        "_note": "SYNTHETIC — shape fixture for B's slider. NOT a reportable run.",
        "items": bitems}, indent=1))
    fp = sum(1 for r in bitems if r["verdict"] == "BLOCK")
    print(f"{out}: {len(bitems)} benign "
          f"({fp} above tau={args.threshold}), {len(sitems)} sensitive, "
          f"corpus_is_real=false")


if __name__ == "__main__":
    main()
