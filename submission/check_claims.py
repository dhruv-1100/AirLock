#!/usr/bin/env python3
"""submission/check_claims.py — owner C.

Every number in SUBMISSION.md that fill.py does not compute is written out by hand. This
checks each one against the artifact it cites, and fails if either side has drifted.

    python submission/check_claims.py

Exists because the previous draft described the system as planned, not as measured: it
named models that never ran, a throughput sweep that was never taken, and a recall figure
that was wrong. Hand-typed numbers with no tie to a source are how that happens.
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

DOC = Path("submission/SUBMISSION.md")


def _proof() -> str:
    logs = sorted(glob.glob("results/proof_*.log"))
    return Path(logs[-1]).read_text() if logs else ""


def _json(path: str, *keys):
    d = json.loads(Path(path).read_text())
    for k in keys:
        d = d[k]
    return d


def _rates():
    d = json.loads(Path("results/fpr_report.json").read_text())
    return d["recall"], d["fpr"]


def _fdr(pi):
    tpr, fpr = _rates()
    return f"{(1 - tpr * pi / (tpr * pi + fpr * (1 - pi))) * 100:.1f}%"


def _breakeven():
    tpr, fpr = _rates()
    lo, hi = 1e-4, 0.5
    for _ in range(60):
        m = (lo + hi) / 2
        f = 1 - tpr * m / (tpr * m + fpr * (1 - m))
        lo, hi = (m, hi) if f > 0.51 else (lo, m)
    return m


# (claim as written in the doc, where it must also appear, how to read that source)
CLAIMS = [
    # memory — proof.sh output
    ("47,847 MiB", lambda: "47847 MiB" in _proof()),
    ("35,325 MiB", lambda: "35325 MiB" in _proof()),
    ("910 MiB",    lambda: "910.5MiB" in _proof()),
    ("25.06 GB",   lambda: "25.06 GB" in _proof()),
    ("121.63 GB",  lambda: "121.63 GB" in _proof()),
    ("580.159.03", lambda: "580.159.03" in _proof()),
    # launch fractions
    ("| 0.40 |", lambda: "--gpu-memory-utilization 0.40" in Path("stack/launch_text.sh").read_text()),
    ("| 0.28 |", lambda: "--gpu-memory-utilization 0.28" in Path("stack/launch_vision.sh").read_text()),
    # T0 probe
    ("p50 4.8 ms", lambda: "p50 4.8 ms" in Path("results/t0_fastpath.md").read_text()),
    ("p95 6.7 ms", lambda: "p95 6.7 ms" in Path("results/t0_fastpath.md").read_text()),
    ("40 of 40",   lambda: "40/40" in Path("results/t0_fastpath.md").read_text()),
    # image path
    ("12,995 ms", lambda: "12,995 ms" in Path("results/t3_latency.md").read_text()),
    ("19,909 ms", lambda: "19,909 ms" in Path("results/t3_latency.md").read_text()),
    ("10,013 ms", lambda: "10,013 ms" in Path("results/t3_latency.md").read_text()),
    # T1 offline
    ("105 of the 400 sensitive", lambda: _json("results/t1_offline_sensitive.json", "t1_high_blocks") == 105),
    ("zero T1-HIGH blocks", lambda: _json("results/t1_offline.json", "t1_high_blocks") == 0),
    # adjudication
    ("38/1000 = 3.80% [2.78%, 5.17%]", lambda: "38/1000 = 3.80% [2.78%, 5.17%]" in Path("results/adjudication.md").read_text()),
    ("33/1000", lambda: "33/1000" in Path("results/adjudication.md").read_text()),
    ("12 of the 33", lambda: "12 of the 33" in Path("results/adjudication.md").read_text()),
    ("A further 13", lambda: "**13 are consumer credit-dispute letters" in Path("results/adjudication.md").read_text()),
    # score saturation and the B3 bug
    ("98.1% of the run's scores", lambda: abs(_json("results/fpr_report.json", "p_block_saturated_frac") - 0.981) < 0.0005),
    ("812 of 1000 benign scores",
     lambda: sum(1 for r in _json("results/scores_benign.json", "items") if r.get("p_block") == 0.0) == 812),
    # sandbox evidence
    ("OpenShell 0.0.44", lambda: "openshell 0.0.44" in Path("evidence/rule02-providers.txt").read_text()),
    ("4 requests, all to", lambda: "4 endpoint=http://172.17.0.1:8000/v1" in Path("evidence/rule02-providers.txt").read_text()),
    ("ignored-by-router", lambda: "ignored-by-router" in Path("evidence/rule02-providers.txt").read_text()),
    # design notes cited to code
    ("8 tokens, clean JSON, 236 ms", lambda: "8 tokens, clean JSON, 236 ms" in Path("services/inspect/tiers/t3.py").read_text()),
    ("mutually exclusive", lambda: "mutually exclusive" in Path("stack/launch_text.sh").read_text()),
    # share of wrong blocks by prevalence — recomputed from the report, not trusted
    *[(f"| {pi:.0%} | {v} |", (lambda pi=pi, v=v: _fdr(pi) == v))
      for pi, v in ((0.01, "80.1%"), (0.02, "66.6%"), (0.05, "43.6%"), (0.10, "26.8%"))],
    ("prevalence of about 3.8%", lambda: abs(_breakeven() - 0.038) < 0.0015),
    ("51% of DLP alerts are false\npositives", lambda: True),   # external source, cited by URL in the doc
    # corpus / hard negatives
    ("**50 hard negatives**",
     lambda: sum(1 for l in open("data/sensitive_v1.jsonl") if '"HARD_NEGATIVE"' in l) == 50),
    ("22 carrier templates", lambda: _json("data/sensitive_v1.manifest.json", "carriers") == 22),
]


def main() -> int:
    doc = DOC.read_text()
    bad = 0
    for text, check in CLAIMS:
        in_doc = text in doc
        try:
            ok_src = bool(check())
        except Exception as e:  # noqa: BLE001
            ok_src, text = False, f"{text}  ({e})"
        if in_doc and ok_src:
            print(f"  ok      {text}")
        else:
            bad += 1
            where = "not in SUBMISSION.md" if not in_doc else "source disagrees"
            print(f"  FAIL    {text}   <- {where}")

    # test count claim
    import subprocess
    out = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                         capture_output=True, text=True).stdout.strip().splitlines()[-1:]
    n = out[0].split(" passed")[0].split()[-1] if out and " passed" in out[0] else "?"
    if f"{n} tests" not in doc:
        bad += 1
        print(f"  FAIL    test count: suite has {n}, doc says otherwise")
    else:
        print(f"  ok      {n} tests")

    print(f"\n{len(CLAIMS) - bad if bad < len(CLAIMS) else 0} checks passed, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
