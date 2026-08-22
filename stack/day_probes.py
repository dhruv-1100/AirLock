"""Phase 0 item 9 — the two VERIFY-ON-THE-DAY probes, run at the 10:45 gate.

  1. Label first-token distinctness: dump the classifier tokenizer's first
     token for each of the nine labels (vLLM /tokenize endpoint). If any two
     collide, the calib.py fallback is digit-prefixed labels 1_BENIGN…9_LEGAL_HR.
  2. Guided-JSON round-trip: try the three spellings from SRS §5.4 in order
     against the classifier and print the winner — RECORD IT IN NOTES.md.

Usage (on the box, after airlock-clf is warm):
    python stack/day_probes.py            # both probes against :8002
    python stack/day_probes.py --url http://127.0.0.1:8000/v1   # T2-on-35B fallback
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.inspect.schemas import CLASSIFIER_SCHEMA, LABELS  # noqa: E402

SPELLINGS = [
    ("response_format json_schema",
     {"response_format": {"type": "json_schema",
                          "json_schema": {"name": "airlock_verdict",
                                          "schema": CLASSIFIER_SCHEMA}}}),
    ("structured_outputs", {"structured_outputs": {"json": CLASSIFIER_SCHEMA}}),
    ("guided_json", {"guided_json": CLASSIFIER_SCHEMA}),
]


def probe_tokenizer(base, model):
    print("=== probe 1: label first-token distinctness ===")
    first = {}
    with httpx.Client(timeout=10) as c:
        for lb in LABELS:
            # Tokenize in value position — leading quote context matters.
            r = c.post(f"{base.rsplit('/v1', 1)[0]}/tokenize",
                       json={"model": model, "prompt": f'"{lb}"'})
            r.raise_for_status()
            toks = r.json().get("tokens", [])
            # tokens[0] is the opening quote for most BPEs; the label's first
            # own token is the first one after it.
            first[lb] = tuple(toks[:2])
            print(f"  {lb:22s} first tokens: {toks[:3]}")
    seen = {}
    collide = False
    for lb, key in first.items():
        if key in seen:
            print(f"  [COLLISION] {lb} vs {seen[key]} — apply the digit-prefix "
                  f"fallback (1_BENIGN…9_LEGAL_HR, strip in post)")
            collide = True
        seen[key] = lb
    if not collide:
        print("  [ok] all nine labels first-token-distinct — calib.py posterior is sound")
    return not collide


def probe_guided_json(base, model):
    print("\n=== probe 2: guided-JSON spelling round-trip ===")
    body_base = {
        "model": model,
        "messages": [{"role": "user", "content":
                      "Classify: 'hello world'. Output only the JSON object."}],
        "temperature": 0.0, "max_tokens": 200, "seed": 1337,
    }
    with httpx.Client(timeout=30) as c:
        for name, extra in SPELLINGS:
            try:
                r = c.post(f"{base}/chat/completions", json={**body_base, **extra})
                r.raise_for_status()
                out = json.loads(r.json()["choices"][0]["message"]["content"])
                assert "label" in out and "evidence_spans" in out
                print(f"  [WINNER] {name}")
                print(f"  → RECORD IN NOTES.md: guided-JSON spelling = {name}")
                return name
            except (httpx.HTTPError, json.JSONDecodeError, AssertionError,
                    KeyError) as e:
                print(f"  {name}: rejected ({type(e).__name__})")
    print("  [FAIL] no spelling accepted — check vLLM version/logs before 10:45 gate")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8002/v1")
    ap.add_argument("--model", default="airlock-clf")
    args = ap.parse_args()
    ok1 = probe_tokenizer(args.url, args.model)
    ok2 = probe_guided_json(args.url, args.model) is not None
    sys.exit(0 if (ok1 and ok2) else 1)


if __name__ == "__main__":
    main()
