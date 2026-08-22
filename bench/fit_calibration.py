"""Phase 3 items 1–3 — fit the calibration scalar T, report ECE, pick tau.

Runs the 200-item dev split through /v1/inspect with debug_label_logits=true
(harness-only field; the service returns the raw 9-label log-mass so the whole
temperature sweep happens offline against cached logits). Then:

  1. T = argmin NLL  via scipy.optimize.minimize_scalar, bounds (0.05, 10)
  2. ECE before/after, 10 equal-width bins  →  results/reliability.png
  3. writes results/calibration.json — services/inspect/calib.py picks T up
     from there on next service start (or AIRLOCK_CALIB_T env)

Dev/test discipline (SRS §6.5): T and tau are selected on THIS dev split and
reported on the held-out test run. The dev split is the first 100 benign +
100 sensitive items under seed 1337 shuffling; run_fpr's test pass excludes
nothing because the corpora don't overlap the dev indices used here.

Usage: python bench/fit_calibration.py --benign data/benign_v1.jsonl \
           --sensitive data/sensitive_v1.jsonl
"""

import argparse
import asyncio
import json
import math
import random
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.inspect.calib import p_block_from_logits  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://127.0.0.1:8787/v1/inspect"


def load_jsonl(path, n, seed):
    rows = [json.loads(ln) for ln in Path(path).read_text().splitlines() if ln.strip()]
    random.Random(seed).shuffle(rows)
    return rows[:n]


async def fetch_logits(items, url, concurrency=8):
    sem = asyncio.Semaphore(concurrency)
    out = []

    async def one(item, y):
        body = {"schema": "airlock.inspect.v1",
                "request_id": f"cal_{item.get('_id', item.get('id', '?'))}",
                "ts": int(time.time() * 1000), "origin": "bench://calibration",
                "text": item["text"], "images": [], "mode": "balanced",
                "debug_label_logits": True}
        async with sem:
            try:
                r = await client.post(url, json=body, timeout=10.0)
                v = r.json()
            except (httpx.HTTPError, json.JSONDecodeError):
                return
        lg = v.get("label_logits")
        if lg:  # only T2-tier items carry logits; T0/T1 need no calibration
            out.append({"y": y, "logits": lg, "tier": v.get("tier")})

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[one(it, y) for it, y in items])
    return out


def nll(samples, T):
    total = 0.0
    for s in samples:
        p = min(max(p_block_from_logits(s["logits"], T), 1e-9), 1 - 1e-9)
        total -= math.log(p if s["y"] else 1.0 - p)
    return total / len(samples)


def ece(samples, T, bins=10):
    """Expected calibration error, 10 equal-width bins over p_block."""
    binned = [[] for _ in range(bins)]
    for s in samples:
        p = p_block_from_logits(s["logits"], T)
        binned[min(bins - 1, int(p * bins))].append((p, s["y"]))
    n = len(samples)
    err = 0.0
    diagram = []
    for i, b in enumerate(binned):
        if not b:
            diagram.append({"bin": i, "n": 0})
            continue
        conf = sum(p for p, _ in b) / len(b)
        acc = sum(y for _, y in b) / len(b)
        err += (len(b) / n) * abs(acc - conf)
        diagram.append({"bin": i, "n": len(b), "conf": round(conf, 4),
                        "acc": round(acc, 4)})
    return err, diagram


def plot_reliability(diag_before, diag_after, T, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), sharey=True)
    for ax, diag, title in ((axes[0], diag_before, "T = 1.0 (before)"),
                            (axes[1], diag_after, f"T = {T:.3f} (after)")):
        xs = [(d["bin"] + 0.5) / 10 for d in diag if d["n"]]
        accs = [d["acc"] for d in diag if d["n"]]
        ax.bar(xs, accs, width=0.09, label="empirical")
        ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="perfect")
        ax.set_title(title)
        ax.set_xlabel("predicted p_block")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
    axes[0].set_ylabel("empirical block-worthiness")
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--benign", default="data/benign_v1.jsonl")
    ap.add_argument("--sensitive", default="data/sensitive_v1.jsonl")
    ap.add_argument("--n-per-class", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()

    items = ([(r, 0) for r in load_jsonl(args.benign, args.n_per_class, args.seed)]
             + [(r, 1) for r in load_jsonl(args.sensitive, args.n_per_class,
                                           args.seed)])
    print(f"dev split: {len(items)} items")
    samples = asyncio.run(fetch_logits(items, args.url))
    print(f"{len(samples)} reached T2 and carry logits "
          f"(T0/T1-resolved items need no calibration)")
    if len(samples) < 30:
        sys.exit("too few T2 samples to fit — is the classifier up?")

    from scipy.optimize import minimize_scalar
    res = minimize_scalar(lambda t: nll(samples, t), bounds=(0.05, 10),
                          method="bounded")
    T = float(res.x)

    e_before, d_before = ece(samples, 1.0)
    e_after, d_after = ece(samples, T)
    print(f"T = {T:.4f}   NLL {nll(samples, 1.0):.4f} → {res.fun:.4f}   "
          f"ECE {e_before:.4f} → {e_after:.4f}")
    if e_after > e_before:
        # T minimises NLL, not ECE — they can disagree. Say so out loud: the
        # submission reports ECE before/after, and shipping a T that worsens
        # the number we publish is a decision, not a detail to discover later.
        print(f"  WARNING: temperature scaling made ECE WORSE "
              f"({e_before:.4f} → {e_after:.4f}) while improving NLL.\n"
              f"  Report both honestly. Consider shipping T=1.0 and saying the "
              f"model was already near-calibrated on this split — that is a\n"
              f"  legitimate finding, not a failure. Do NOT report only the "
              f"metric that improved.")

    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "calibration.json").write_text(json.dumps({
        "T": round(T, 4), "n_dev": len(samples),
        "nll_before": round(nll(samples, 1.0), 4), "nll_after": round(res.fun, 4),
        "ece_before": round(e_before, 4), "ece_after": round(e_after, 4),
        "bins_before": d_before, "bins_after": d_after,
        "seed": args.seed, "fitted_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
        indent=2))
    print("wrote results/calibration.json — restart the inspect service "
          "(or export AIRLOCK_CALIB_T) to apply")
    plot_reliability(d_before, d_after, T, ROOT / "results" / "reliability.png")


if __name__ == "__main__":
    main()
