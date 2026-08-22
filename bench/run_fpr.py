"""FP-rate harness (SRS Phase 2 item 6, NFR-T5).

Reads a benign corpus JSONL, POSTs every item to /v1/inspect directly over
HTTP — no Chrome in the loop — and writes:
  results/scores_benign.json   per-item p_block (the slider re-thresholds these)
  results/report.json          n, false_pos, fpr, Wilson 95% CI, p50/p95, by_class

Falls back to data/smoke_20.jsonl when benign_v1.jsonl has not landed yet —
the harness is never blocked on the corpus.

Usage: python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55
"""

import argparse
import asyncio
import json
import math
import os
import random
import statistics
import sys
import time

import httpx

DEFAULT_URL = "http://127.0.0.1:8787/v1/inspect"


def wilson_ci(fp, n, z=1.96):
    if n == 0:
        return [0.0, 0.0]
    p = fp / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 6), round(centre + half, 6)]


def pct(values, q):
    if not values:
        return None
    return round(statistics.quantiles(values, n=100)[q - 1], 1) if len(values) > 1 else values[0]


async def run_item(client, sem, url, threshold, item):
    body = {"schema": "airlock.inspect.v1",
            "request_id": f"fpr_{item['id']}",
            "ts": int(time.time() * 1000),
            "origin": "bench://run_fpr", "url": "bench://run_fpr",
            "text": item["text"], "html": "", "images": [],
            "mode": "balanced", "threshold": threshold}
    async with sem:
        t0 = time.perf_counter()
        try:
            resp = await client.post(url, json=body, timeout=5.0)
            v = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            v = {"action": "block", "label": f"harness_error:{type(e).__name__}",
                 "p_block": 1.0, "tier": "ERR"}
        ms = (time.perf_counter() - t0) * 1000
    return {"id": item["id"], "source": item.get("source", "unknown"),
            "char_len": len(item["text"]), "label": "BENIGN",
            "verdict": v.get("action", "block").upper(),
            "verdict_label": v.get("label", ""),
            "p_block": v.get("p_block", 1.0),
            "tier": v.get("tier", "ERR"),
            "latency_ms": round(v.get("latency_ms", ms), 1),
            "wall_ms": round(ms, 1)}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--input", default=None)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = args.input
    if path is None:
        for cand in ("data/benign_v1.jsonl", "data/smoke_20.jsonl"):
            if os.path.exists(os.path.join(root, cand)):
                path = os.path.join(root, cand)
                break
    if path is None or not os.path.exists(path):
        sys.exit("no corpus found (data/benign_v1.jsonl or data/smoke_20.jsonl)")

    with open(path) as f:
        items = [json.loads(ln) for ln in f if ln.strip()]
    random.Random(args.seed).shuffle(items)
    items = items[:args.n]
    print(f"corpus={os.path.relpath(path, root)} n={len(items)} "
          f"threshold={args.threshold} seed={args.seed}")

    sem = asyncio.Semaphore(args.concurrency)
    t_start = time.perf_counter()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[
            run_item(client, sem, args.url, args.threshold, it) for it in items])
    wall_s = time.perf_counter() - t_start

    n = len(results)
    fps = [r for r in results if r["verdict"] == "BLOCK"]
    lat = sorted(r["latency_ms"] for r in results)
    by_class = {}
    for r in fps:
        by_class.setdefault(r["verdict_label"], 0)
        by_class[r["verdict_label"]] += 1

    report = {"n": n, "false_pos": len(fps),
              "fpr": round(len(fps) / n, 6) if n else None,
              "ci95": wilson_ci(len(fps), n),
              "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95),
              "by_class": by_class, "threshold": args.threshold,
              "seed": args.seed, "corpus": os.path.basename(path),
              "wall_clock_s": round(wall_s, 1),
              "note": ("0 FPs reported as 'below the rule-of-three bound', "
                       "never 'zero'" if not fps else None)}

    os.makedirs(os.path.join(root, "results"), exist_ok=True)
    with open(os.path.join(root, "results", "scores_benign.json"), "w") as f:
        json.dump(results, f, indent=1)
    with open(os.path.join(root, "results", "report.json"), "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    if fps:
        print("\nfalse positives:")
        for r in fps[:20]:
            print(f"  {r['id']}  {r['verdict_label']}  p={r['p_block']}  "
                  f"tier={r['tier']}")


if __name__ == "__main__":
    asyncio.run(main())
