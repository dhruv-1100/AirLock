#!/usr/bin/env python3
"""submission/fill.py — owner C. SRS §14 final read, check 2.

Substitutes every {{PLACEHOLDER}} in SUBMISSION.md from results/fpr_report.json.

    python submission/fill.py                 # -> submission/SUBMISSION.final.md
    python submission/fill.py --check         # list unfilled placeholders, fill nothing

The 17:30 check is "does any number in the prose disagree with fpr_report.json?"
This script makes that check vacuous **by construction**: no number is ever typed into
the prose by hand, so none can drift. Anything it cannot fill is listed loudly rather
than silently left as a literal `{{...}}` in a submitted document.

Placeholders it cannot compute (throughput, seats, stack versions) are the ones A and C
fill by hand from measurement — they are listed explicitly at the end of every run so
nobody discovers one at 17:44.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SRC = Path("submission/SUBMISSION.md")
OUT = Path("submission/SUBMISSION.final.md")
REPORT = Path("results/fpr_report.json")

# Filled by hand from A's measurements — listed, never silently blanked.
MANUAL = {
    "THROUGHPUT_TABLE": "A — text sweep c∈{1,8,64,256} and vision sweep c∈{1,2,4,8,16}, both columns",
    "IMAGES_PER_SEC": "A — images/sec at the largest c where E2E p95 ≤ 2.5 s",
    "SEATS_ARITHMETIC": "A — seats/box with every assumption shown",
    "SEATS": "A — min(seats_vision, seats_text)",
    "F_IMG": "A — measured image fraction",
    "HEADROOM": "A — MemAvailable at demo config",
    "RULE02_PROVIDERS": "C — jq output over the OCSF log",
    "STACK_PARAGRAPH": "C — §S7.1 with real version numbers substituted",
    "ABLATION_TABLE": "A — the four-row ablation",
    "INTER_RATER": "C — n reviewed, disagreements, Cohen's κ",
    "ADJUDICATION": "C — from results/false_positives.md, after hand review",
    "HARD_NEGATIVE_RESULT": "C — hard-negative bucket as its own line",
    "OVERRIDE_RATE": "A — span-verification override rate",
    "INTERRUPTIONS": "C — 200,000 × measured FPR",
}


def pct(x, places=2):
    return "n/a" if x is None else f"{x * 100:.{places}f}%"


def build_map(r: dict) -> dict[str, str]:
    n = r.get("n", 0)
    fpr = r.get("fpr")
    m: dict[str, str] = {
        "N": f"{n:,}",
        "THRESHOLD": str(r.get("threshold", 0.55)),
        "FPR_STATEMENT": r.get("fpr_statement", "n/a"),
        "FPR_HEADLINE": (
            f"below {r['rule_of_three_upper'] * 100:.2f}%"
            if r.get("false_pos") == 0 and r.get("rule_of_three_upper")
            else pct(fpr)
        ),
        "P50": str(r.get("p50_ms", "?")),
        "P95": str(r.get("p95_ms", "?")),
        "ESCALATION": pct(r.get("escalation_rate"), 1),
        "RECALL_STATEMENT": r.get("recall_statement") or "n/a",
    }

    prec = r.get("precision_at_prevalence", {})
    m["PRECISION_AT_2PCT"] = f"{prec['0.020']:.3f}" if "0.020" in prec else "n/a"
    m["PRECISION_AT_3PCT_FPR"] = (
        f"{r['precision_if_fpr_were_3pct']:.3f}"
        if r.get("precision_if_fpr_were_3pct") is not None else "n/a"
    )

    if fpr is not None:
        m["INTERRUPTIONS"] = f"{round(200_000 * fpr):,} wrong interruptions a week"

    # per-source table
    if r.get("by_source"):
        rows = ["| Source | n | FP | FPR | 95% CI |", "|---|---|---|---|---|"]
        for k, v in r["by_source"].items():
            rows.append(
                f"| {k} | {v['n']} | {v['fp']} | {pct(v.get('fpr'))} | "
                f"[{v['ci95'][0] * 100:.2f}%, {v['ci95'][1] * 100:.2f}%] |"
            )
        m["BY_SOURCE_TABLE"] = "\n".join(rows)

    # per-class table
    if r.get("by_class"):
        rows = ["| Class | n | TP | Recall | 95% CI |", "|---|---|---|---|---|"]
        for k, v in r["by_class"].items():
            rows.append(
                f"| {k} | {v['n']} | {v['tp']} | {pct(v.get('recall'), 1)} | "
                f"[{v['ci95'][0] * 100:.1f}%, {v['ci95'][1] * 100:.1f}%] |"
            )
        m["BY_CLASS_TABLE"] = "\n".join(rows)

    # operating points, if the per-threshold sweep was written alongside
    for name, key in (("AUDIT", "audit"), ("BALANCED", "balanced"), ("STRICT", "strict")):
        op = (r.get("operating_points") or {}).get(key)
        if op:
            m[f"FPR_{name}"] = pct(op.get("fpr"))
            m[f"RECALL_{name}"] = pct(op.get("recall"), 1)
    m.setdefault("FPR_BALANCED", m["FPR_STATEMENT"])
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    a = ap.parse_args()

    if not SRC.exists():
        print(f"FATAL: {SRC} not found", file=sys.stderr)
        return 2

    text = SRC.read_text(encoding="utf-8")
    found = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", text)))

    report = {}
    if REPORT.exists():
        report = json.loads(REPORT.read_text())
    else:
        print(f"! {REPORT} not found — run bench/report.py first. Nothing can be filled.")

    if report and not report.get("reportable", True):
        print("\n" + "=" * 66)
        print("  REFUSING TO FILL: fpr_report.json says reportable=false.")
        print("  The benign corpus is placeholder text, or this was a selftest run.")
        print("  Build the real corpus before generating a submission.")
        print("=" * 66 + "\n")
        return 3

    mapping = build_map(report) if report else {}

    filled, missing_auto, manual = [], [], []
    for k in found:
        if k in mapping and mapping[k] not in ("n/a", "?"):
            filled.append(k)
        elif k in MANUAL:
            manual.append(k)
        else:
            missing_auto.append(k)

    if not a.check:
        out = text
        for k, v in mapping.items():
            out = out.replace("{{" + k + "}}", v)
        OUT.write_text(out, encoding="utf-8")
        remaining = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", out)))
        print(f"wrote {OUT}")
    else:
        remaining = manual + missing_auto

    print(f"\nfilled automatically ({len(filled)}): {', '.join(filled) or '—'}")

    if manual:
        print(f"\nfill by hand ({len(manual)}) — owner and source:")
        for k in manual:
            print(f"  {{{{{k}}}}}".ljust(30) + MANUAL[k])
    if missing_auto:
        print(f"\nUNKNOWN placeholders ({len(missing_auto)}) — no source defined:")
        for k in missing_auto:
            print(f"  {{{{{k}}}}}")

    if remaining:
        print(f"\n*** {len(remaining)} placeholder(s) still unfilled. ***")
        print("    DO NOT SUBMIT with a literal {{...}} in the document.")
        return 1

    print("\nno placeholders remain — ready to submit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
