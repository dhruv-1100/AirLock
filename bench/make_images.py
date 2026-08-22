#!/usr/bin/env python3
"""bench/make_images.py — owner C. SRS §10 Phase 2 tasks 1 and 2.

Produces the image assets the vision path is demonstrated and measured on.

    python bench/make_images.py --demo      # the beat-3 chart  (B is blocked on this by 13:15)
    python bench/make_images.py --gate      # 20 DISTINCT charts for A's G1 latency gate
    python bench/make_images.py --benign    # ~100 benign charts for the image FPR
    python bench/make_images.py --all

------------------------------------------------------------------------------
Why the demo chart is not cheating
------------------------------------------------------------------------------
The beat-3 chart is titled "FY26 Revenue Forecast — Plan vs. Commit" with a footer
reading "Internal — Do Not Distribute". That is what real internal decks look like, and
it is what makes the block reason quotable:

    "the chart title reads FY26 Revenue Forecast and the footer reads
     Internal — Do Not Distribute"

rather than the unfalsifiable

    "the model thought it looked internal."

The T3 prompt transcribes chrome — title, axis labels, legend, column headers,
footnotes, watermarks — and is explicitly forbidden from reading data values off bars.
That routes around every documented VLM chart failure mode (OCRBench v2 is 54.3 EN;
fine-grained value reading is not reliable, chrome text is). The chart is designed so
the signal is in the chrome, because the chrome is what actually determines
confidentiality in a real deck.

------------------------------------------------------------------------------
A's gate images MUST be distinct
------------------------------------------------------------------------------
vLLM V1 hashes image content into prefix-cache keys. Twenty copies of one image
produces a fraudulent latency number. Every gate image here differs in title, series
values, category count and colour.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

W, H, DPI = 1280, 720, 100

DEMO_DIR = Path("data/images/demo")
GATE_DIR = Path("data/images/gate")
BENIGN_DIR = Path("data/images/benign")

CONF_MARKERS = [
    "Internal — Do Not Distribute",
    "CONFIDENTIAL — Board Use Only",
    "Pre-announcement — not for external circulation",
    "Draft — unaudited, subject to change",
    "Restricted: Finance and Exec only",
]

INTERNAL_TITLES = [
    "FY26 Revenue Forecast — Plan vs. Commit",
    "FY27 Bookings Projection by Region",
    "Q4 Pipeline Coverage — Commit vs. Best Case",
    "ARR Bridge — Unreleased, FY26 Exit",
    "Net Revenue Retention Forecast by Cohort",
    "FY26 Headcount Plan vs. Approved Budget",
    "Renewal Cohort Risk — EMEA, Confidential",
    "Gross Margin Bridge — Restructuring Scenario",
    "Series C Cap Table — Fully Diluted",
    "Compensation Bands by Level — FY26 Cycle",
]

BENIGN_TITLES = [
    "Global Average Surface Temperature, 1880–2020",
    "Population by Continent, 2023",
    "Public Transit Ridership by Mode",
    "Annual Rainfall by Month — Lisbon",
    "Household Internet Access by Country (OECD)",
    "Renewable Share of Electricity Generation",
    "Life Expectancy at Birth by Region",
    "Reported Bicycle Journeys per Weekday",
    "Library Loans by Genre, Public Libraries",
    "Museum Visitor Numbers by Quarter",
    "Recycling Rate by Material Type",
    "Average Commute Time by City",
]


def _mpl():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ImportError:
        return None


def _bar_chart(plt, path: Path, title: str, footer: str | None, rng: random.Random,
               ylabel: str, legend: tuple[str, str] | None) -> None:
    n = rng.randint(4, 8)
    cats = [f"Q{i % 4 + 1} {2025 + i // 4}" for i in range(n)] if legend else \
           [f"Cat {chr(65 + i)}" for i in range(n)]
    a = [round(rng.uniform(20, 160), 1) for _ in range(n)]
    b = [round(v * rng.uniform(0.72, 1.28), 1) for v in a]

    fig, ax = plt.subplots(figsize=(W / DPI, H / DPI), dpi=DPI)
    x = range(n)
    if legend:
        wdt = 0.38
        ax.bar([i - wdt / 2 for i in x], a, wdt, label=legend[0])
        ax.bar([i + wdt / 2 for i in x], b, wdt, label=legend[1])
        ax.legend(loc="upper left", frameon=False)
    else:
        ax.bar(list(x), a, 0.62, color=rng.choice(
            ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#CCB974", "#64B5CD"]))

    ax.set_title(title, fontsize=17, fontweight="bold", pad=16)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats, fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)

    if footer:
        # The footer is the signal. Bottom-left, small, exactly where a real deck puts it.
        fig.text(0.012, 0.022, footer, fontsize=11, color="#B00020", fontweight="bold")

    fig.tight_layout(rect=(0, 0.045, 1, 1) if footer else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def _svg_fallback(path: Path, title: str, footer: str | None, rng: random.Random) -> None:
    """Dependency-free fallback so B is never blocked waiting on a pip install.

    Writes .svg beside the requested .png. A browser renders it; any screenshot of it is
    a usable stand-in while the real PNG pipeline is sorted out.
    """
    n = rng.randint(5, 7)
    vals = [rng.uniform(0.25, 1.0) for _ in range(n)]
    bw = 1100 / n
    bars = "".join(
        f'<rect x="{90 + i * bw + bw * 0.15:.0f}" y="{600 - v * 460:.0f}" '
        f'width="{bw * 0.7:.0f}" height="{v * 460:.0f}" fill="#4C72B0"/>'
        f'<text x="{90 + i * bw + bw * 0.5:.0f}" y="625" font-size="15" '
        f'text-anchor="middle" fill="#333">Q{i % 4 + 1}</text>'
        for i, v in enumerate(vals)
    )
    foot = (
        f'<text x="16" y="706" font-size="15" font-weight="bold" fill="#B00020">{footer}</text>'
        if footer else ""
    )
    path.with_suffix(".svg").parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="#fff"/>'
        f'<text x="{W//2}" y="52" font-size="26" font-weight="bold" text-anchor="middle" '
        f'fill="#111">{title}</text>'
        f'<text x="30" y="330" font-size="15" fill="#333" transform="rotate(-90 30 330)">'
        f'Revenue (USD, millions)</text>'
        f'<line x1="88" y1="600" x2="1200" y2="600" stroke="#333" stroke-width="2"/>'
        f'{bars}{foot}</svg>',
        encoding="utf-8",
    )


def build(demo: bool, gate: bool, benign: bool, seed: int) -> int:
    rng = random.Random(seed)
    plt = _mpl()
    if plt is None:
        print("! matplotlib not installed — writing SVG fallbacks instead of PNGs.")
        print("  On the box:  pip install matplotlib   (CPU only, no GPU process)")

    made = 0

    if demo:
        p = DEMO_DIR / "fy26_forecast.png"
        title = "FY26 Revenue Forecast — Plan vs. Commit"
        footer = "Internal — Do Not Distribute"
        if plt:
            _bar_chart(plt, p, title, footer, rng, "Revenue (USD, millions)", ("Plan", "Commit"))
        else:
            _svg_fallback(p, title, footer, rng)
        made += 1
        print(f"demo chart → {p if plt else p.with_suffix('.svg')}")
        print(f'  title  : "{title}"')
        print(f'  footer : "{footer}"')
        print("  beat 3 blocks by quoting BOTH of those strings back from the transcription.")

    if gate:
        # 20 DISTINCT images. Identical images hit the V1 prefix cache and produce a
        # fraudulent latency number — this is A's G1 gate and it must be honest.
        for i in range(20):
            t = f"{INTERNAL_TITLES[i % len(INTERNAL_TITLES)]} ({i + 1})"
            p = GATE_DIR / f"gate_{i:02d}.png"
            if plt:
                _bar_chart(plt, p, t, rng.choice(CONF_MARKERS), rng,
                           "Value (USD, millions)", ("Plan", "Commit"))
            else:
                _svg_fallback(p, t, rng.choice(CONF_MARKERS), rng)
            made += 1
        print(f"gate images → {GATE_DIR}  (20 distinct — required for an honest G1 number)")

    if benign:
        # Image FPR is reported SEPARATELY and never folded into the text denominator.
        for i in range(100):
            t = f"{BENIGN_TITLES[i % len(BENIGN_TITLES)]} — series {i // len(BENIGN_TITLES) + 1}"
            p = BENIGN_DIR / f"benign_{i:03d}.png"
            if plt:
                _bar_chart(plt, p, t, None, rng, "Value", None)
            else:
                _svg_fallback(p, t, None, rng)
            made += 1
        manifest = BENIGN_DIR / "MANIFEST.md"
        manifest.write_text(
            "# Benign image set\n\n"
            "100 charts with no confidentiality marker, no temporal marker and no\n"
            "internal vocabulary. Generated by `bench/make_images.py --benign --seed 1337`.\n\n"
            "**Image FPR is reported separately from text FPR and is never folded into the\n"
            "text denominator.** The two modalities have different base rates and different\n"
            "failure modes; averaging them would hide both.\n\n"
            "Any of these blocked is a false positive. The T3 grounding rule should force\n"
            "BENIGN on all of them: no temporal marker, no confidentiality marker, no T1 hit\n"
            "over the transcribed text means `override:\"no_grounded_marker\"`.\n",
            encoding="utf-8",
        )
        print(f"benign images → {BENIGN_DIR}  (100, image FPR reported separately)")

    print(f"\nwrote {made} images (seed={seed})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Airlock image assets.")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--benign", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=1337)
    a = ap.parse_args()
    if not any([a.demo, a.gate, a.benign, a.all]):
        ap.print_help()
        return 1
    return build(a.demo or a.all, a.gate or a.all, a.benign or a.all, a.seed)


if __name__ == "__main__":
    sys.exit(main())
