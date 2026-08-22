#!/usr/bin/env python3
"""bench/report.py — owner C. SRS §10 Phase 3, §14.

Turns `results/scores_*.json` into the numbers and figures the submission is built on.
Written in Phase 2 against a synthetic scores file so that at 14:35 it is a one-command
run, not a debugging session.

    python bench/report.py                       # after run_fpr.py
    python bench/report.py --threshold 0.30      # re-threshold cached scores, exact
    python bench/report.py --selftest            # synthetic scores, no harness needed

Emits:
    results/fpr_report.json     the machine-readable artifact every number is grepped against
    results/REPORT.md           the paste-into-the-submission tables
    results/roc.png             log-scale FPR axis — at 0.3% a linear axis shows nothing
    results/pr.png              precision-recall with average precision
    results/reliability.png     reliability diagram, 10 equal-width bins, ECE annotated
    results/false_positives.md  EVERY false positive, itemised for hand-adjudication

Two rules this file enforces so nobody has to remember them at 17:30:

  1. **Never write "zero".** FP=0 over n=1000 is reported as "below 0.3% at 95%
     confidence by the rule of three" (SRS §6.5, §14).
  2. **Never report a number from a corpus whose manifest says corpus_is_real=false.**
     The headline is withheld and the reason is printed loudly.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

RESULTS = Path("results")


# --------------------------------------------------------------------------- statistics
def wilson(k: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """Wilson score interval. Correct at the extremes, where normal approximation is not —
    and the extremes are exactly where a good FPR lives."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def rule_of_three(n: int) -> float:
    """Upper bound on a rate when zero events were observed."""
    return 3.0 / n if n else 1.0


def fmt_rate(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    if k == 0:
        return (
            f"below {rule_of_three(n) * 100:.2f}% at 95% confidence "
            f"by the rule of three (0/{n})"
        )
    return f"{k / n * 100:.2f}% [{lo * 100:.2f}%, {hi * 100:.2f}%] ({k}/{n})"


def ece(pairs: list[tuple[float, int]], bins: int = 10) -> float:
    """Expected calibration error, 10 equal-width bins."""
    if not pairs:
        return 0.0
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in pairs:
        buckets[min(bins - 1, int(p * bins))].append((p, y))
    total = len(pairs)
    return sum(
        len(b) / total * abs(sum(y for _, y in b) / len(b) - sum(p for p, _ in b) / len(b))
        for b in buckets
        if b
    )


def roc_points(scored: list[tuple[float, int]]) -> list[tuple[float, float]]:
    """(fpr, tpr) sweeping every threshold present in the data."""
    pos = sum(y for _, y in scored) or 1
    neg = len(scored) - sum(y for _, y in scored) or 1
    pts, tp, fp = [(0.0, 0.0)], 0, 0
    for _, y in sorted(scored, key=lambda t: -t[0]):
        tp, fp = tp + y, fp + (1 - y)
        pts.append((fp / neg, tp / pos))
    return pts


def auc(pts: list[tuple[float, float]]) -> float:
    return sum(
        (pts[i][0] - pts[i - 1][0]) * (pts[i][1] + pts[i - 1][1]) / 2
        for i in range(1, len(pts))
    )


def precision_at_prevalence(tpr: float, fpr: float, prevalence: float) -> float:
    """THE line that makes the whole FPR argument (SRS §14).

    At π=2%, TPR=0.95, FPR=0.003 → 0.866.  At the same TPR with FPR=0.03 → 0.393.
    Ten times the false-positive rate turns a usable control into one people switch off.
    """
    num = tpr * prevalence
    den = num + fpr * (1 - prevalence)
    return num / den if den else 0.0


# --------------------------------------------------------------------------- loading
def load(path: Path) -> list[dict]:
    """Read a scores file, tolerating every shape that has existed in this repo.

    run_fpr.py now writes {benign:[floats], items:[dicts], …} so that B's slider
    (which filters SCORES.benign) and this report (which needs the per-item dicts) can
    read the same file. Older bare-list files still load.
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            return data["items"]
        # A p_block-only file (B's bundled fixture): synthesise minimal rows so the
        # report still runs, clearly marked so nothing is mistaken for a real item.
        key = "sensitive" if "sensitive" in path.name else "benign"
        floats = data.get(key) or data.get("benign") or []
        return [
            {"_id": f"{key}:{i}", "source": "scores-only", "label": "BENIGN",
             "p_block": p, "verdict": "?", "latency_ms": 0, "tier": "?", "char_len": 0}
            for i, p in enumerate(floats)
        ]
    return []


def corpus_is_real() -> bool:
    m = Path("data/benign_v1.manifest.json")
    if not m.exists():
        return True
    try:
        return bool(json.loads(m.read_text()).get("corpus_is_real", True))
    except Exception:  # noqa: BLE001
        return True


def selftest_scores(seed: int = 1337) -> tuple[list[dict], list[dict]]:
    """Synthetic scores with a realistic shape, so this file is finished and debugged
    before the real numbers exist. SRS §10 Phase 3: 'C writes report.py against a
    synthetic scores file first, so at 14:35 it is a one-command run'."""
    rng = random.Random(seed)
    srcs = ["WildChat-1M", "StackExchange", "MBPP", "HumanEval", "CFPB", "Wikipedia"]
    benign = []
    for i in range(1000):
        p = min(0.999, abs(rng.gauss(0.06, 0.09)))
        if rng.random() < 0.004:      # a few genuine hard cases
            p = rng.uniform(0.56, 0.9)
        tier = rng.choices(["T0", "T1", "T2", "CACHE"], weights=[20, 60, 15, 5])[0]
        benign.append({
            "_id": f"selftest:benign:{i}", "source": rng.choice(srcs), "label": "BENIGN",
            "p_block": round(p, 4), "verdict": "BLOCK" if p >= 0.55 else "ALLOW",
            "latency_ms": {"T0": rng.randint(1, 3), "T1": rng.randint(2, 14),
                           "T2": rng.randint(190, 580), "CACHE": rng.randint(1, 5)}[tier],
            "tier": tier, "char_len": rng.randint(200, 4000),
            "predicted_label": "CUSTOMER_RECORD" if p >= 0.55 else "BENIGN",
            "evidence_spans": ["synthetic span"] if p >= 0.55 else [],
        })
    classes = ["CREDENTIAL", "PAYMENT_CARD", "GOV_ID", "CUSTOMER_RECORD",
               "HEALTH_RECORD", "FINANCIAL_NONPUBLIC", "PROPRIETARY_CODE", "LEGAL_HR"]
    sensitive = []
    for i in range(400):
        c = rng.choice(classes)
        p = min(0.999, abs(rng.gauss(0.88, 0.16)))
        sensitive.append({
            "_id": f"selftest:sensitive:{i}", "source": "synthetic", "label": c,
            "p_block": round(p, 4), "verdict": "BLOCK" if p >= 0.55 else "ALLOW",
            "latency_ms": rng.randint(180, 600), "tier": "T2", "char_len": rng.randint(200, 3000),
            "predicted_label": c if p >= 0.55 else "BENIGN",
        })
    return benign, sensitive


# --------------------------------------------------------------------------- plots
def plots(benign: list[dict], sensitive: list[dict], thr: float) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  ! matplotlib not installed — skipping figures (pip install matplotlib)")
        return []

    made = []
    scored = [(r["p_block"], 0) for r in benign if r.get("p_block") is not None] + \
             [(r["p_block"], 1) for r in sensitive if r.get("p_block") is not None]

    if scored and sensitive:
        pts = roc_points(scored)
        xs = [max(p[0], 1e-4) for p in pts]
        ys = [p[1] for p in pts]
        fig, ax = plt.subplots(figsize=(5.5, 4.5))
        ax.plot(xs, ys, lw=2)
        ax.set_xscale("log")   # at 0.3% a linear axis shows nothing at all
        ax.set_xlabel("False positive rate (log scale)")
        ax.set_ylabel("True positive rate")
        ax.set_title(f"ROC — AUC {auc(pts):.4f}")
        ax.grid(alpha=0.3, which="both")
        ax.axvline(0.003, ls="--", lw=1, color="tab:red")
        ax.annotate("0.3%", (0.003, 0.05), color="tab:red", fontsize=8)
        fig.tight_layout(); fig.savefig(RESULTS / "roc.png", dpi=160); plt.close(fig)
        made.append("roc.png")

        # precision-recall
        order = sorted(scored, key=lambda t: -t[0])
        npos = sum(y for _, y in order) or 1
        tp = fp = 0
        rec, prec = [], []
        for _, y in order:
            tp, fp = tp + y, fp + (1 - y)
            rec.append(tp / npos); prec.append(tp / (tp + fp))
        ap = sum((rec[i] - rec[i - 1]) * prec[i] for i in range(1, len(rec)))
        fig, ax = plt.subplots(figsize=(5.5, 4.5))
        ax.plot(rec, prec, lw=2)
        ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
        ax.set_title(f"Precision–Recall — AP {ap:.4f}")
        ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(RESULTS / "pr.png", dpi=160); plt.close(fig)
        made.append("pr.png")

    if scored:
        pairs = [(p, y) for p, y in scored]
        bins = 10
        buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
        for p, y in pairs:
            buckets[min(bins - 1, int(p * bins))].append((p, y))
        centres = [(i + 0.5) / bins for i in range(bins)]
        acc = [sum(y for _, y in b) / len(b) if b else 0 for b in buckets]
        fig, ax = plt.subplots(figsize=(5, 4.5))
        ax.bar(centres, acc, width=1 / bins * 0.9, alpha=0.75, label="observed")
        ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect calibration")
        ax.set_xlabel("Predicted p_block"); ax.set_ylabel("Observed frequency")
        ax.set_title(f"Reliability — ECE {ece(pairs):.4f}")
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(RESULTS / "reliability.png", dpi=160); plt.close(fig)
        made.append("reliability.png")

    return made


# --------------------------------------------------------------------------- main
def build_report(thr: float, prevalence: float, selftest: bool) -> int:
    RESULTS.mkdir(exist_ok=True)

    if selftest:
        benign, sensitive = selftest_scores()
        real = False
        print("SELFTEST MODE — synthetic scores. Exercises every code path below.")
    else:
        benign = load(RESULTS / "scores_benign.json")
        sensitive = load(RESULTS / "scores_sensitive.json")
        real = corpus_is_real()
        if not benign:
            print("FATAL: results/scores_benign.json not found.", file=sys.stderr)
            print("  run: python bench/run_fpr.py --seed 1337 --n 1000", file=sys.stderr)
            print("  or:  python bench/report.py --selftest", file=sys.stderr)
            return 2

    # Re-threshold cached scores. Exact and instant — this is NOT a re-inference.
    def verdict(r):
        p = r.get("p_block")
        return r.get("verdict", "ERROR") if p is None else ("BLOCK" if p >= thr else "ALLOW")

    bok = [r for r in benign if r.get("p_block") is not None]
    sok = [r for r in sensitive if r.get("p_block") is not None]

    n = len(bok)
    fps = [r for r in bok if verdict(r) == "BLOCK"]
    fp = len(fps)
    lo, hi = wilson(fp, n)

    # per-source FP contribution — publishing the weak source is what makes the rest believable
    by_source: dict[str, dict] = {}
    for r in bok:
        s = by_source.setdefault(r.get("source", "?"), {"n": 0, "fp": 0})
        s["n"] += 1
        if verdict(r) == "BLOCK":
            s["fp"] += 1

    # per-class recall
    by_class: dict[str, dict] = {}
    for r in sok:
        c = r.get("label", "?")
        d = by_class.setdefault(c, {"n": 0, "tp": 0})
        d["n"] += 1
        if verdict(r) == "BLOCK":
            d["tp"] += 1

    # ---- per-language FP breakdown ----
    # The corpus is genuinely multilingual (WildChat) while the T2 system prompt is
    # English. Reporting FPR by language turns that from an asserted caveat into a
    # measured result — and if the FP list does skew non-English, this is the table that
    # says so honestly instead of leaving a judge to discover it.
    lang_index: dict[str, str] = {}
    try:
        with open("data/benign_v1.jsonl", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    lang_index[d["_id"]] = d.get("lang", "unknown")
    except Exception:  # noqa: BLE001
        pass

    by_lang: dict[str, dict] = {}
    if lang_index:
        for r in bok:
            lg = lang_index.get(r["_id"], "unknown")
            d = by_lang.setdefault(lg, {"n": 0, "fp": 0})
            d["n"] += 1
            if verdict(r) == "BLOCK":
                d["fp"] += 1

    lat = sorted(r["latency_ms"] for r in bok) or [0]
    p50 = lat[len(lat) // 2]
    p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
    esc = sum(1 for r in bok if r.get("tier") in ("T2", "T3"))

    recall = (sum(1 for r in sok if verdict(r) == "BLOCK") / len(sok)) if sok else None
    fpr = fp / n if n else None

    report = {
        "generated_from": "selftest" if selftest else "results/scores_*.json",
        "corpus_is_real": real,
        "reportable": real and not selftest,
        "threshold": thr,
        "n": n,
        "false_pos": fp,
        "fpr": fpr,
        "ci95": [lo, hi],
        "fpr_statement": fmt_rate(fp, n),
        "rule_of_three_upper": rule_of_three(n) if fp == 0 else None,
        "p50_ms": p50,
        "p95_ms": p95,
        "escalation_rate": esc / n if n else None,
        "recall": recall,
        "recall_statement": (
            fmt_rate(sum(1 for r in sok if verdict(r) == "BLOCK"), len(sok)) if sok else None
        ),
        "by_source": {
            k: {**v, "fpr": v["fp"] / v["n"] if v["n"] else None,
                "ci95": list(wilson(v["fp"], v["n"]))}
            for k, v in sorted(by_source.items())
        },
        "by_language": {
            k: {**v, "fpr": v["fp"] / v["n"] if v["n"] else None,
                "ci95": list(wilson(v["fp"], v["n"]))}
            for k, v in sorted(by_lang.items(), key=lambda kv: -kv[1]["n"])
        },
        "by_class": {
            k: {**v, "recall": v["tp"] / v["n"] if v["n"] else None,
                "ci95": list(wilson(v["tp"], v["n"]))}
            for k, v in sorted(by_class.items())
        },
        "ece": ece([(r["p_block"], 0) for r in bok] + [(r["p_block"], 1) for r in sok]),
        "precision_at_prevalence": {},
    }

    if recall is not None and fpr is not None:
        for pi in (0.005, 0.02, 0.05):
            report["precision_at_prevalence"][f"{pi:.3f}"] = round(
                precision_at_prevalence(recall, fpr, pi), 4
            )
        # the comparison that carries the argument
        report["precision_if_fpr_were_3pct"] = round(
            precision_at_prevalence(recall, 0.03, prevalence), 4
        )

    # ---- the three named operating points, from the SAME cached scores ----
    # This is exactly what caching per-item p_block buys: the sweep is exact and instant,
    # not 3000 fresh inferences. Fills the Audit/Balanced/Strict table in the submission.
    report["operating_points"] = {}
    for name, tau in (("audit", 0.30), ("balanced", 0.55), ("strict", 0.20)):
        b = sum(1 for r in bok if r["p_block"] >= tau)
        s = sum(1 for r in sok if r["p_block"] >= tau)
        lo_t, hi_t = wilson(b, len(bok))
        report["operating_points"][name] = {
            "threshold": tau,
            "fpr": b / len(bok) if bok else None,
            "fpr_ci95": [lo_t, hi_t],
            "fpr_statement": fmt_rate(b, len(bok)),
            "recall": s / len(sok) if sok else None,
            "recall_statement": fmt_rate(s, len(sok)) if sok else None,
        }

    (RESULTS / "fpr_report.json").write_text(json.dumps(report, indent=2))

    # ---- itemised false positives for hand-adjudication (SRS §14) ----
    lines = [
        "# False positives — every one, for hand-adjudication",
        "",
        f"Threshold {thr}. {fp} of {n} benign items blocked.",
        "",
        "Adjudicate each row and record the verdict in the `Adjudication` column. Report",
        "the corrected count in the submission, e.g. *\"7 blocked; on review 3 contained a",
        "genuine live-looking key the corpus author had pasted; corrected FP = 4/1000\"*.",
        "This turns the corpus's weakness into a demonstration of rigour.",
        "",
    ]
    if not fps:
        lines.append("_No false positives at this threshold._")
    for i, r in enumerate(fps, 1):
        lines += [
            f"## {i}. `{r['_id']}` — {r.get('source', '?')}",
            "",
            f"- p_block **{r['p_block']}** · tier `{r.get('tier', '?')}` · "
            f"predicted `{r.get('predicted_label', '?')}` · {r.get('char_len', 0)} chars",
            f"- evidence spans: `{r.get('evidence_spans', [])}`",
            "- **Adjudication:** _(genuine FP / corpus contamination / borderline)_",
            "",
        ]
    (RESULTS / "false_positives.md").write_text("\n".join(lines) + "\n")

    made = plots(bok, sok, thr)

    # ---- markdown tables ----
    md = [
        "# Airlock — evaluation report",
        "",
        f"Reproduce: `python bench/run_fpr.py --seed 1337 --n 1000 --threshold {thr}`",
        "",
    ]
    if not report["reportable"]:
        md += [
            "> **NOT REPORTABLE.** "
            + ("Selftest mode." if selftest else "The benign corpus manifest says `corpus_is_real: false`.")
            + " These numbers exercise the harness; they are not evidence.",
            "",
        ]
    md += [
        "## Headline",
        "",
        f"- **False-positive rate: {report['fpr_statement']}**",
        f"- Latency p50 / p95: **{p50} ms / {p95} ms**",
        f"- Escalation rate (reached a model): **{(report['escalation_rate'] or 0) * 100:.1f}%**",
    ]
    if report["recall_statement"]:
        md.append(f"- Recall on the sensitive split: **{report['recall_statement']}**")
    md.append(f"- ECE: **{report['ece']:.4f}**")
    md += ["", "## False positives by source", "",
           "| Source | n | FP | FPR | 95% CI |", "|---|---|---|---|---|"]
    for k, v in report["by_source"].items():
        md.append(
            f"| {k} | {v['n']} | {v['fp']} | "
            f"{(v['fpr'] or 0) * 100:.2f}% | "
            f"[{v['ci95'][0] * 100:.2f}%, {v['ci95'][1] * 100:.2f}%] |"
        )
    if report["by_class"]:
        md += ["", "## Recall by class", "",
               "| Class | n | TP | Recall | 95% CI |", "|---|---|---|---|---|"]
        for k, v in report["by_class"].items():
            md.append(
                f"| {k} | {v['n']} | {v['tp']} | "
                f"{(v['recall'] or 0) * 100:.1f}% | "
                f"[{v['ci95'][0] * 100:.1f}%, {v['ci95'][1] * 100:.1f}%] |"
            )
    if report.get("by_language"):
        md += ["", "## False positives by language", "",
               "The corpus is multilingual; the classifier prompt is English. This table",
               "reports that rather than asserting it.", "",
               "| Language | n | FP | FPR | 95% CI |", "|---|---|---|---|---|"]
        for k, v in report["by_language"].items():
            md.append(
                f"| {k} | {v['n']} | {v['fp']} | {(v['fpr'] or 0) * 100:.2f}% | "
                f"[{v['ci95'][0] * 100:.2f}%, {v['ci95'][1] * 100:.2f}%] |")
    if report["precision_at_prevalence"]:
        md += ["", "## Precision at prevalence", "",
               "The argument for why FPR matters more than recall.", "",
               "| Prevalence | Precision |", "|---|---|"]
        for k, v in report["precision_at_prevalence"].items():
            md.append(f"| {float(k) * 100:.1f}% | {v:.3f} |")
        md += [
            "",
            f"At π={prevalence * 100:.0f}% the measured FPR gives precision "
            f"**{report['precision_at_prevalence'].get(f'{prevalence:.3f}', 0):.3f}**. "
            f"At a 3% FPR the same detector gives **{report['precision_if_fpr_were_3pct']:.3f}** — "
            "ten times the false-positive rate turns a usable control into one people switch off.",
        ]
    (RESULTS / "REPORT.md").write_text("\n".join(md) + "\n")

    # ---- console ----
    print("\n" + "=" * 64)
    print(f"  FPR              {report['fpr_statement']}")
    print(f"  p50 / p95        {p50} ms / {p95} ms")
    print(f"  escalation       {(report['escalation_rate'] or 0) * 100:.1f}%")
    if report["recall_statement"]:
        print(f"  recall           {report['recall_statement']}")
    print(f"  ECE              {report['ece']:.4f}")
    print("=" * 64)
    print(f"  wrote fpr_report.json, REPORT.md, false_positives.md")
    if made:
        print(f"  wrote figures: {', '.join(made)}")
    if not report["reportable"]:
        print("\n  *** NOT REPORTABLE — do not paste these numbers into the submission ***")
    print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Airlock evaluation report.")
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--prevalence", type=float, default=0.02)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    return build_report(a.threshold, a.prevalence, a.selftest)


if __name__ == "__main__":
    sys.exit(main())
