"""Gate G1 (SRS Phase 0 item 7, 10:45): p50/p95 vision latency over the 20
pre-staged DISTINCT 1280×720 chart images in data/images/gate/.

Distinct images are mandatory — vLLM V1 hashes image content into
prefix-cache keys, so repeated identical images produce a fraudulent number.

Pass: p50 ≤ 1.5 s AND p95 ≤ 2.5 s. Fail → NFR-L4b fast mode
(max_pixels=401408, max_tokens=1 + logprobs). Fail again → swap weights to
nvidia/Qwen2.5-VL-7B-Instruct-NVFP4.
"""

import argparse
import base64
import glob
import os
import statistics
import sys
import time

import httpx

TRANSCRIBE_PROMPT = (
    "Transcribe only the chrome text visible in this image: title, axis "
    "labels, legend entries, column headers, footnotes, watermarks, filenames "
    "and tab titles. Do NOT read data values off bars, lines or points.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get(
        "AIRLOCK_VLM_URL", "http://127.0.0.1:8001/v1"))
    ap.add_argument("--model", default=os.environ.get(
        "AIRLOCK_VLM_MODEL", "Hcompany/Holo1.5-7B"))
    ap.add_argument("--images", default="data/images/gate")
    ap.add_argument("--max-tokens", type=int, default=8)
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.images, "*")))
    if len(paths) < 20:
        sys.exit(f"need 20 distinct gate images in {args.images}, "
                 f"found {len(paths)} — they are pre-staged on the USB")

    lat = []
    with httpx.Client(timeout=30) as client:
        for p in paths[:20]:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            mime = "image/png" if p.endswith(".png") else "image/jpeg"
            body = {"model": args.model, "temperature": 0.0,
                    "max_tokens": args.max_tokens,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": TRANSCRIBE_PROMPT},
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{b64}"}}]}]}
            t0 = time.perf_counter()
            r = client.post(f"{args.url}/chat/completions", json=body)
            r.raise_for_status()
            ms = (time.perf_counter() - t0) * 1000
            lat.append(ms)
            print(f"{os.path.basename(p):40s} {ms:8.0f} ms")

    lat.sort()
    p50 = statistics.median(lat)
    p95 = statistics.quantiles(lat, n=100)[94]
    print(f"\nG1: p50={p50:.0f} ms  p95={p95:.0f} ms  over {len(lat)} distinct images")
    ok = p50 <= 1500 and p95 <= 2500
    print("G1 PASS" if ok else "G1 FAIL → apply NFR-L4b fast mode "
          "(max_pixels=401408, max_tokens=1 + logprobs)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
