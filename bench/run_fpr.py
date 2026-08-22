#!/usr/bin/env python3
"""bench/run_fpr.py — owner C, run by A from 13:00. SRS §10 Phase 2, NFR-T5, Risk R4.

THE DECIDING ARTIFACT. Everything else in this project is a demo; this is the evidence.

Reproduction command, verbatim in the submission (SRS §14):

    python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55

Runs **direct over HTTP with no browser in the loop** — Chrome is a demo surface, not a
measurement instrument. Must complete 1000 benign + 400 sensitive in ≤ 15 min (NFR-T5);
at the default concurrency it finishes in a small fraction of that even if every item
escalates to T2.

Outputs:
    results/scores_benign.json    per-item p_block — B's threshold slider re-thresholds
                                  THESE CACHED SCORES, so the sweep is exact and instant.
    results/scores_sensitive.json per-item p_block for the recall side
    benign_eval collection        one doc per benign item (bypassable, see below)

Risk R4 — if the Mongo write path is not producing documents by 14:30, pass --no-mongo.
The JSON files are the source of truth for bench/report.py either way; the aggregation
stays in the writeup as the production path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_URL = "http://127.0.0.1:8787/v1/inspect"


# --------------------------------------------------------------------------- io
def load_corpus(path: Path, n: int | None) -> list[dict]:
    if not path.exists():
        print(f"FATAL: corpus not found: {path}", file=sys.stderr)
        print("  run: python bench/build_benign.py --seed 1337", file=sys.stderr)
        sys.exit(2)
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:n] if n else rows


def check_corpus_real(path: Path) -> bool:
    """Guard: never let placeholder text be reported as a measured FPR."""
    m = path.with_name(path.stem + ".manifest.json")
    if not m.exists():
        return True
    try:
        return bool(json.loads(m.read_text()).get("corpus_is_real", True))
    except Exception:  # noqa: BLE001
        return True


# --------------------------------------------------------------------------- one item
async def inspect_one(session, url: str, item: dict, threshold: float, mode: str) -> dict:
    """POST one payload. Any transport failure is recorded as an ERROR, never silently
    dropped — a shrinking denominator is how an FPR gets accidentally flattered."""
    import aiohttp

    body = {
        "schema": "airlock.inspect.v1",
        "request_id": f"fpr_{item['_id']}",
        "ts": int(time.time() * 1000),
        "origin": "http://localhost:5173",
        "url": "http://localhost:5173/bench",
        "text": item.get("text", ""),
        "html": "",
        "images": [],
        "mode": mode,
        "threshold": threshold,
    }

    t0 = time.perf_counter()
    try:
        async with session.post(url, json=body) as r:
            elapsed = int((time.perf_counter() - t0) * 1000)
            try:
                v = await r.json()
            except Exception:  # noqa: BLE001
                v = {}
            if r.status != 200:
                # A non-200 is a fail-closed BLOCK by contract. It counts as a block.
                return {
                    "_id": item["_id"], "source": item.get("source", ""),
                    "sha256": item.get("sha256", ""), "char_len": item.get("char_len", 0),
                    "label": item.get("label", "BENIGN"), "verdict": "BLOCK",
                    "p_block": 1.0, "latency_ms": elapsed, "tier": v.get("tier", "ERR"),
                    "predicted_label": v.get("label", "airlock_unavailable"),
                    "http_status": r.status, "error": v.get("reason", f"HTTP {r.status}"),
                }
            return {
                "_id": item["_id"], "source": item.get("source", ""),
                "sha256": item.get("sha256", ""), "char_len": item.get("char_len", 0),
                "label": item.get("label", "BENIGN"),
                "verdict": str(v.get("action", "allow")).upper().replace("WARN", "ALLOW"),
                "p_block": float(v.get("p_block", 0.0)),
                "latency_ms": int(v.get("latency_ms", elapsed)),
                "tier": v.get("tier", "?"),
                "predicted_label": v.get("label", "BENIGN"),
                "clause_id": v.get("policy_clause_id", "NONE"),
                "evidence_spans": v.get("evidence_spans", []),
                "evidence_verified": v.get("evidence_verified", False),
                "override": v.get("override"),
                "http_status": 200,
            }
    except Exception as e:  # noqa: BLE001
        return {
            "_id": item["_id"], "source": item.get("source", ""),
            "sha256": item.get("sha256", ""), "char_len": item.get("char_len", 0),
            "label": item.get("label", "BENIGN"), "verdict": "ERROR",
            "p_block": None, "latency_ms": int((time.perf_counter() - t0) * 1000),
            "tier": "ERR", "predicted_label": None, "http_status": None, "error": str(e),
        }


# --------------------------------------------------------------------------- driver
async def run_split(
    items: list[dict], url: str, threshold: float, mode: str, concurrency: int, tag: str
) -> list[dict]:
    import aiohttp

    sem = asyncio.Semaphore(concurrency)
    results: list[dict] = []
    done = 0
    total = len(items)
    t0 = time.perf_counter()

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async def worker(it):
            nonlocal done
            async with sem:
                r = await inspect_one(session, url, it, threshold, mode)
            results.append(r)
            done += 1
            if done % 50 == 0 or done == total:
                rate = done / max(1e-9, time.perf_counter() - t0)
                eta = (total - done) / max(1e-9, rate)
                print(f"  {tag}: {done}/{total}  {rate:.1f}/s  eta {eta:5.1f}s", flush=True)

        await asyncio.gather(*(worker(i) for i in items))

    return results


async def write_mongo(rows: list[dict]) -> bool:
    try:
        from services.inspect import mongo as M

        if not await M.connect():
            return False
        for r in rows:
            await M.write_benign_eval(
                {
                    "_id": r["_id"], "source": r["source"], "license": r.get("license", ""),
                    "sha256": r["sha256"], "char_len": r["char_len"], "label": r["label"],
                    "verdict": r["verdict"], "p_block": r["p_block"],
                    "latency_ms": r["latency_ms"], "tier": r["tier"],
                }
            )
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  ! mongo write failed ({e}) — JSON files are still authoritative")
        return False


# --------------------------------------------------------------------------- summary
def summarise(rows: list[dict], threshold: float, is_benign: bool) -> dict:
    ok = [r for r in rows if r["verdict"] != "ERROR"]
    errs = len(rows) - len(ok)
    n = len(ok)
    blocked = sum(1 for r in ok if r["verdict"] == "BLOCK")
    lat = sorted(r["latency_ms"] for r in ok) or [0]

    def pct(p):
        return lat[min(len(lat) - 1, int(len(lat) * p))]

    out = {
        "n": n,
        "errors": errs,
        "blocked": blocked,
        "threshold": threshold,
        "p50_ms": pct(0.50),
        "p95_ms": pct(0.95),
        "mean_ms": round(statistics.mean(lat), 1),
        "by_tier": {},
    }
    for r in ok:
        out["by_tier"][r["tier"]] = out["by_tier"].get(r["tier"], 0) + 1
    if is_benign:
        out["false_pos"] = blocked
        out["fpr"] = blocked / n if n else None
    else:
        out["true_pos"] = blocked
        out["recall"] = blocked / n if n else None
    # % of traffic that ever reached a model — the seats-per-box multiplier (NFR-T6)
    esc = sum(1 for r in ok if r["tier"] in ("T2", "T3"))
    out["escalation_rate"] = esc / n if n else None
    return out


async def main_async(a) -> int:
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    benign_path = Path(a.benign)
    corpus_real = check_corpus_real(benign_path)
    if not corpus_real:
        print("\n" + "=" * 70)
        print("  WARNING: benign corpus manifest says corpus_is_real = false.")
        print("  This run exercises the harness. It is NOT a reportable FPR.")
        print("=" * 70 + "\n")

    benign = load_corpus(benign_path, a.n)
    print(f"benign corpus: {len(benign)} items from {benign_path}")

    sensitive = []
    if a.sensitive and Path(a.sensitive).exists():
        sensitive = load_corpus(Path(a.sensitive), None)
        print(f"sensitive corpus: {len(sensitive)} items from {a.sensitive}")

    # Fail fast and loudly rather than producing a corpus of 1000 connection errors.
    import aiohttp

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as s, s.get(a.url.replace("/v1/inspect", "/healthz")) as r:
            print(f"healthz: {r.status} {await r.text()}")
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: {a.url} unreachable ({e})", file=sys.stderr)
        print("  A must have /v1/inspect up. Ask before debugging it yourself.", file=sys.stderr)
        return 2

    t0 = time.perf_counter()

    print(f"\nrunning benign split (concurrency={a.concurrency})")
    brows = await run_split(benign, a.url, a.threshold, a.mode, a.concurrency, "benign")

    srows = []
    if sensitive:
        print(f"\nrunning sensitive split")
        srows = await run_split(sensitive, a.url, a.threshold, a.mode, a.concurrency, "sensitive")

    wall = time.perf_counter() - t0

    # ---- per-item scores. B's slider re-thresholds these CACHED scores: exact, instant,
    # and honestly labelled as cached — never implying 1000 fresh inferences.
    (results_dir / "scores_benign.json").write_text(json.dumps(brows, indent=1))
    if srows:
        (results_dir / "scores_sensitive.json").write_text(json.dumps(srows, indent=1))

    bsum = summarise(brows, a.threshold, is_benign=True)
    ssum = summarise(srows, a.threshold, is_benign=False) if srows else None

    report = {
        "reproduce": f"python bench/run_fpr.py --seed {a.seed} --n {a.n} --threshold {a.threshold}",
        "corpus_is_real": corpus_real,
        "wall_clock_s": round(wall, 1),
        "nfr_t5_pass": wall <= 900,
        "threshold": a.threshold,
        "mode": a.mode,
        "benign": bsum,
        "sensitive": ssum,
    }
    (results_dir / "fpr_raw.json").write_text(json.dumps(report, indent=2))

    if not a.no_mongo:
        print("\nwriting benign_eval …")
        report["mongo_written"] = await write_mongo(brows)

    # ---- console summary
    print("\n" + "=" * 62)
    print(f"  wall clock       {wall:.1f}s   (NFR-T5 ≤900s: {'PASS' if wall <= 900 else 'FAIL'})")
    print(f"  benign n         {bsum['n']}  (errors {bsum['errors']})")
    print(f"  false positives  {bsum['false_pos']}")
    if bsum["fpr"] is not None:
        print(f"  FPR              {bsum['fpr'] * 100:.2f}%")
    print(f"  p50 / p95        {bsum['p50_ms']} ms / {bsum['p95_ms']} ms")
    print(f"  escalation rate  {(bsum['escalation_rate'] or 0) * 100:.1f}%  (reached T2/T3)")
    print(f"  tier mix         {bsum['by_tier']}")
    if ssum:
        print(f"  sensitive n      {ssum['n']}")
        if ssum["recall"] is not None:
            print(f"  recall           {ssum['recall'] * 100:.1f}%")
    print("=" * 62)
    if not corpus_real:
        print("  corpus_is_real=false — DO NOT PUT THIS NUMBER IN THE SUBMISSION")
        print("=" * 62)
    print("\nnext: python bench/report.py   (Wilson CI, per-class tables, plots)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Airlock false-positive-rate harness.")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--mode", default="balanced", choices=["audit", "balanced", "strict"])
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--benign", default="data/benign_v1.jsonl")
    ap.add_argument("--sensitive", default="data/sensitive_v1.jsonl")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--no-mongo", action="store_true", help="R4 bypass: JSON files only")
    a = ap.parse_args()
    try:
        return asyncio.run(main_async(a))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
