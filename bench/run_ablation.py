"""Phase 3 item 5 — THE ABLATION TABLE. Four rows, each a REAL run of the
service under a different router config (never simulated post-hoc):

  row 1  t1_only      deterministic detectors only, no LLM
  row 2  t2_noverify  everything through T2, span verification OFF
  row 3  t2_verify    everything through T2, span verification ON
  row 4  full         production router at tau=0.55

Row 3 minus row 2 is the single best finding in the project if it replicates.

Each row: spawn the inspect service on :8788 with AIRLOCK_ABLATION set and
MONGO_ENABLED=false (no cache, no persistence — nothing contaminates rows),
then drive C's bench/run_fpr.py against it, then collect the row's outputs
into results/ablation/<row>/. Emits results/ablation.json and a markdown
table with Wilson CIs.

Usage (on the box, ~4 × one harness pass):
    python bench/run_ablation.py --n 1000
Smoke (no models needed, proves the machinery):
    python bench/run_ablation.py --n 20 --benign data/smoke_20.jsonl --skip-sensitive
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.report import wilson  # noqa: E402

ROWS = ["t1_only", "t2_noverify", "t2_verify", "full"]
PORT = 8788
ROOT = Path(__file__).resolve().parents[1]


def _port_free():
    try:
        httpx.get(f"http://127.0.0.1:{PORT}/healthz", timeout=0.5)
        return False
    except httpx.HTTPError:
        return True


def start_service(row):
    # A stale server on the port would silently serve the WRONG ablation row —
    # every row's numbers would be the previous row's config.
    for _ in range(50):
        if _port_free():
            break
        time.sleep(0.2)
    else:
        raise RuntimeError(f"port {PORT} still occupied — kill the stale "
                           f"server before running row {row}")
    env = {**os.environ, "AIRLOCK_ABLATION": row, "MONGO_ENABLED": "false"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "services.inspect.app:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if proc.poll() is not None:
            raise RuntimeError(f"service exited early for row {row}")
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/healthz",
                         timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"service failed to start for row {row}")


def stop_service(proc):
    proc.terminate()
    proc.wait(timeout=10)
    for _ in range(50):
        if _port_free():
            return
        time.sleep(0.2)


def summarise(row_dir, threshold):
    scores = json.loads((row_dir / "scores_benign.json").read_text())
    bitems = scores.get("items", [])
    sitems = []
    sp = row_dir / "scores_sensitive.json"
    if sp.exists():
        sitems = json.loads(sp.read_text()).get("items", [])

    n = len(bitems)
    fp = sum(1 for r in bitems if r["verdict"] == "BLOCK")
    lo, hi = wilson(fp, n) if n else (0.0, 0.0)
    lat = sorted(r["latency_ms"] for r in bitems if r.get("latency_ms") is not None)

    def q(p):
        return lat[min(len(lat) - 1, int(p * len(lat)))] if lat else None

    llm = sum(1 for r in bitems + sitems if r.get("tier") in ("T2", "T3"))
    total = len(bitems) + len(sitems)
    out = {"n_benign": n, "false_pos": fp,
           "fpr": round(fp / n, 6) if n else None,
           "ci95": [round(lo, 6), round(hi, 6)],
           "p50_ms": q(0.50), "p95_ms": q(0.95),
           "pct_to_llm": round(llm / total, 4) if total else None,
           "errors": sum(1 for r in bitems + sitems if r["verdict"] == "ERROR")}
    if sitems:
        ns = len(sitems)
        tp = sum(1 for r in sitems if r["verdict"] == "BLOCK")
        rlo, rhi = wilson(tp, ns)
        out.update(n_sensitive=ns, recall=round(tp / ns, 4),
                   recall_ci95=[round(rlo, 6), round(rhi, 6)])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--benign", default="data/benign_v1.jsonl")
    ap.add_argument("--sensitive", default="data/sensitive_v1.jsonl")
    ap.add_argument("--skip-sensitive", action="store_true")
    ap.add_argument("--rows", nargs="*", default=ROWS, choices=ROWS)
    args = ap.parse_args()

    results = {}
    for row in args.rows:
        print(f"\n=== row: {row} ===")
        row_dir = ROOT / "results" / "ablation" / row
        row_dir.mkdir(parents=True, exist_ok=True)
        proc = start_service(row)
        try:
            cmd = [sys.executable, "bench/run_fpr.py",
                   "--url", f"http://127.0.0.1:{PORT}/v1/inspect",
                   "--n", str(args.n), "--threshold", str(args.threshold),
                   "--benign", args.benign, "--no-mongo"]
            if not args.skip_sensitive:
                cmd += ["--sensitive", args.sensitive]
            subprocess.run(cmd, cwd=ROOT, check=True)
        finally:
            stop_service(proc)
        for f in ("scores_benign.json", "scores_sensitive.json", "report.json",
                  "fpr_report.json"):
            src = ROOT / "results" / f
            if src.exists():
                shutil.move(src, row_dir / f)
        results[row] = summarise(row_dir, args.threshold)

    (ROOT / "results" / "ablation.json").write_text(json.dumps(results, indent=2))

    # Markdown table for the submission — C pastes this verbatim.
    hdr = ("| config | FPR (95% CI) | recall | p50 ms | p95 ms | %→LLM |\n"
           "|---|---|---|---|---|---|")
    lines = [hdr]
    for row in args.rows:
        r = results[row]
        ci = f"{r['fpr']:.2%} [{r['ci95'][0]:.2%}, {r['ci95'][1]:.2%}]" \
            if r["fpr"] is not None else "—"
        rec = f"{r['recall']:.1%}" if "recall" in r else "—"
        lines.append(f"| {row} | {ci} | {rec} | {r['p50_ms']} | {r['p95_ms']} | "
                     f"{r['pct_to_llm']:.0%} |" if r["pct_to_llm"] is not None
                     else f"| {row} | {ci} | {rec} | {r['p50_ms']} | {r['p95_ms']} | — |")
    table = "\n".join(lines)
    (ROOT / "results" / "ablation_table.md").write_text(table + "\n")
    print("\n" + table)
    print("\nresults/ablation.json + results/ablation_table.md written")


if __name__ == "__main__":
    main()
