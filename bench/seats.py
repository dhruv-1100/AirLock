"""Phase 3 item 9 — seats-per-box arithmetic (NFR-T7). Refuses to invent.

    seats_vision = (R_img × 3600) / (P_hr × peak × f_img)
    seats_text   = (R_txt × 3600) / (P_hr × peak × (1 − f_img))
    seats/box    = min(seats_vision, seats_text), stating which binds

Assumptions, all on the slide: P = 40 pastes/employee/8h day (= 5/hour),
peak factor 4×, f_img = measured fraction of pastes that are images.
Every rate must come from a measured run — this script takes them as required
arguments and prints the full arithmetic so a judge can recompute it.

Usage:
    python bench/seats.py --r-img 1.8 --r-txt 42 --f-img 0.12 \
        --img-src "vision_sweep c=8 p95=2.1s" --txt-src "text_sweep c=64"
"""

import argparse
import json
from pathlib import Path

P_PER_HOUR = 40 / 8   # 40 pastes per employee per 8-hour day
PEAK = 4.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r-img", type=float, required=True,
                    help="measured images/sec at largest c with E2E p95 <= 2.5s")
    ap.add_argument("--r-txt", type=float, required=True,
                    help="measured text inspections/sec")
    ap.add_argument("--f-img", type=float, required=True,
                    help="measured fraction of pastes that are images")
    ap.add_argument("--img-src", required=True,
                    help="which run r-img came from (goes on the slide)")
    ap.add_argument("--txt-src", required=True,
                    help="which run r-txt came from")
    args = ap.parse_args()

    peak_rate = P_PER_HOUR * PEAK  # pastes/employee/hour at peak
    seats_vision = (args.r_img * 3600) / (peak_rate * args.f_img)
    seats_text = (args.r_txt * 3600) / (peak_rate * (1 - args.f_img))
    binds = "vision" if seats_vision < seats_text else "text"
    seats = min(seats_vision, seats_text)

    out = {
        "assumptions": {"pastes_per_employee_per_8h": 40,
                        "peak_factor": PEAK,
                        "f_img_measured": args.f_img},
        "inputs": {"r_img_per_s": args.r_img, "r_img_source": args.img_src,
                   "r_txt_per_s": args.r_txt, "r_txt_source": args.txt_src},
        "seats_vision": int(seats_vision),
        "seats_text": int(seats_text),
        "binding_path": binds,
        "seats_per_box": int(seats),
    }
    root = Path(__file__).resolve().parents[1]
    (root / "results").mkdir(exist_ok=True)
    (root / "results" / "seats.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print(f"\nseats/box = {int(seats)} ({binds} path binds)")
    print(f"  seats_vision = ({args.r_img} × 3600) / ({P_PER_HOUR} × {PEAK} × "
          f"{args.f_img}) = {seats_vision:.0f}")
    print(f"  seats_text   = ({args.r_txt} × 3600) / ({P_PER_HOUR} × {PEAK} × "
          f"{1 - args.f_img:.2f}) = {seats_text:.0f}")


if __name__ == "__main__":
    main()
