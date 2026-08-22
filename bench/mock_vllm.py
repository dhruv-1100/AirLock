"""A fake vLLM chat-completions server — DEV/CI ONLY, never part of the demo.

Exists so the Phase 3 measurement pipeline (fit_calibration.py, the two
t2_* ablation rows) can be exercised end to end without a GPU. Those paths
need a classifier that returns guided JSON *and* top_logprobs, so before this
they had never run at all — and finding a bug in them at 14:30 on the box,
with the harness queued behind them, is the expensive way to find it.

It fakes the shape, never the science: labels are derived from crude keyword
hits so calibration has real signal to fit against, but no number produced
against this server is reportable. Run it on :8002 and point the service at it.

    python bench/mock_vllm.py --port 8002
"""

import argparse
import json
import math
import os
import random
import re

from fastapi import FastAPI, Request
import uvicorn

app = FastAPI(title="mock-vllm")

# Fraction of non-BENIGN verdicts that cite evidence absent from the payload.
# Exercises the span-verification override path (SRS §6.4) so the ablation can
# be proven to detect it. Override with AIRLOCK_MOCK_HALLUCINATION.
HALLUCINATION_RATE = float(os.environ.get("AIRLOCK_MOCK_HALLUCINATION", "0.15"))

CUES = [
    (re.compile(r'(?i)\b(sk-|ghp_|AKIA|api[_ ]?key|password|secret|token)\b'),
     "CREDENTIAL", "POL-001"),
    (re.compile(r'(?i)\b(ssn|social security|passport)\b'), "GOV_ID", "POL-003"),
    (re.compile(r'(?i)\b(forecast|projection|unreleased|ARR|MRR|pipeline|cap table)\b'),
     "FINANCIAL_NONPUBLIC", "POL-006"),
    (re.compile(r'(?i)\b(patient|diagnosis|clinical)\b'), "HEALTH_RECORD", "POL-005"),
    (re.compile(r'(?i)\b(NDA|litigation|disciplinary|termination)\b'),
     "LEGAL_HR", "POL-008"),
    (re.compile(r'(?i)\b(internal[- ]only|do not distribute|confidential)\b'),
     "PROPRIETARY_CODE", "POL-007"),
]
# Hard negatives the real prompt is instructed to pass — the mock must too, or
# the calibration fit trains against a detector that disagrees with the spec.
BENIGN_CUES = re.compile(
    r'(?i)(example\.com|AKIAIOSFODNN7EXAMPLE|4242424242424242|555-0100|'
    r'your-api-key-here|changeme|10-Q|placeholder|tutorial|docs say)')


def _classify(payload, rng):
    if BENIGN_CUES.search(payload):
        return "BENIGN", "NONE", [], 0.05 + rng.random() * 0.15
    for rx, label, clause in CUES:
        m = rx.search(payload)
        if m:
            if rng.random() < HALLUCINATION_RATE:
                # Quote something that is NOT in the payload. Real models do
                # this, and it is precisely what span verification exists to
                # catch — without it here, ablation rows 2 and 3 come out
                # identical and the apparatus cannot demonstrate the very
                # effect the SRS calls the best finding in the project.
                return label, clause, ["[paraphrased evidence not in payload]"], \
                    0.55 + rng.random() * 0.42
            # Otherwise quote a literal substring, as a well-behaved model does.
            start = max(0, m.start() - 20)
            span = payload[start:m.end() + 40].strip()
            return label, clause, [span[:120]], 0.55 + rng.random() * 0.42
    return "BENIGN", "NONE", [], rng.random() * 0.25


def _logprob_tokens(content, label, p_label, rng):
    """Chop the JSON so the label value starts its own token, and attach
    top_logprobs there — the exact shape services/inspect/calib.py walks."""
    idx = content.find(f'"{label}"', content.find('"label"'))
    head, tail = content[:idx + 1], content[idx + 1:]
    toks = [{"token": head, "logprob": -0.01, "top_logprobs": []}]
    others = ["BENIGN", "CREDENTIAL", "PAYMENT_CARD", "GOV_ID", "CUSTOMER_RECORD",
              "HEALTH_RECORD", "FINANCIAL_NONPUBLIC", "PROPRIETARY_CODE", "LEGAL_HR"]
    remaining = max(1e-6, 1.0 - p_label)
    share = remaining / (len(others) - 1)
    top = []
    for lb in others:
        p = p_label if lb == label else share
        top.append({"token": lb[:4], "logprob": math.log(max(p, 1e-9))})
    toks.append({"token": label, "logprob": math.log(max(p_label, 1e-9)),
                 "top_logprobs": top})
    toks.append({"token": tail, "logprob": -0.01, "top_logprobs": []})
    return toks


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def models():
    return {"data": [{"id": "airlock-text"}, {"id": "airlock-clf"}]}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    # Accept any of the three guided-JSON spellings, like a real vLLM build.
    guided = ("response_format" in body or "structured_outputs" in body
              or "guided_json" in body)
    msgs = body.get("messages", [])
    payload = ""
    for m in reversed(msgs):
        if m.get("role") == "user":
            c = m["content"]
            payload = c if isinstance(c, str) else json.dumps(c)
            break
    # Strip the <<<PAYLOAD ... PAYLOAD>>> wrapper: a real model quotes the
    # payload itself, and wrapper text would fail span verification every
    # time — which would silently turn every T2 block into an override.
    mw = re.search(r"<<<PAYLOAD\n(.*?)\nPAYLOAD>>>", payload, re.S)
    if mw:
        payload = mw.group(1)

    rng = random.Random(body.get("seed", 1337) ^ (hash(payload) & 0xFFFF))
    if not guided:
        content = "I would classify this payload as sensitive."
        return {"id": "mock", "model": body.get("model", "mock"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}]}

    label, clause, spans, p = _classify(payload, rng)
    # p is "how sensitive"; p_label is the probability mass on the CHOSEN
    # label. For BENIGN those are complements — conflating them makes a benign
    # verdict report p_block ≈ 0.8.
    p_label = (1.0 - p) if label == "BENIGN" else p
    verdict = {"evidence_spans": spans,
               "rationale": f"mock classifier keyword route -> {label}",
               "label": label,
               "severity": "HIGH" if label != "BENIGN" else "NONE",
               "policy_clause_id": clause,
               "confidence": round(min(0.99, p + 0.1), 3)}  # deliberately
    # overconfident vs the true posterior, so temperature scaling has something
    # real to correct — verbalized confidence is biased upward in practice too.
    content = json.dumps(verdict)
    return {"id": "mock", "model": body.get("model", "mock"),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content},
                         "logprobs": {"content": _logprob_tokens(
                             content, label, p_label, rng)}}]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8002)
    a = ap.parse_args()
    print(f"MOCK vLLM on :{a.port} — shape only, no number from this is reportable")
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
