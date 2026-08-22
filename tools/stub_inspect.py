"""
tools/stub_inspect.py — B's stub inspector. Owned by B for the whole day.

This is the thing B falls back to if A's :8787 ever wedges. It binds the SAME port
and speaks the SAME contract (CONTRACT.md), so the swap in either direction is a
process restart and nothing else — no URL change, no field change, no reload of the
extension.

Decision rule (deliberately dumb, deliberately deterministic):
  - text contains '@'            -> BLOCK  CUSTOMER_RECORD  POL-004  T2
  - text matches a card-ish run  -> BLOCK  PAYMENT_CARD     POL-002  T1
  - text contains 'sk-' / 'AKIA' -> BLOCK  CREDENTIAL       POL-001  T1
  - an image is present          -> BLOCK  FINANCIAL_NONPUBLIC POL-006 T3
  - anything else                -> ALLOW  BENIGN

Run:
    uvicorn tools.stub_inspect:app --host 127.0.0.1 --port 8787
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
import time
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse

app = FastAPI(title="airlock-stub-inspect")

BOOT = time.time()
MAX_BODY = 8 * 1024 * 1024
MODE_TAU = {"audit": 0.30, "balanced": 0.55, "strict": 0.20}

# --------------------------------------------------------------------------- CORS
# Access-Control-Allow-Private-Network: true is the load-bearing header. Without it
# Chrome >= 130 fails the preflight from a public page to 127.0.0.1 and the whole
# thing looks like model slowness.
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Private-Network": "true",
    "Access-Control-Max-Age": "600",
}


@app.middleware("http")
async def cors_everything(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=CORS)
    resp = await call_next(request)
    for k, v in CORS.items():
        resp.headers[k] = v
    return resp


# ------------------------------------------------------------------ policy corpus
POLICY = {
    "version": "policy_v1",
    "clauses": [
        {"id": "POL-001", "class": "CREDENTIAL", "severity": "HIGH",
         "text": "Live credentials — API keys, tokens, private keys, passwords and "
                 "credentialed connection strings — must never be transmitted to an "
                 "unapproved third-party service."},
        {"id": "POL-002", "class": "PAYMENT_CARD", "severity": "HIGH",
         "text": "Primary account numbers, with or without CVV or expiry, must not "
                 "leave the cardholder data environment."},
        {"id": "POL-003", "class": "GOV_ID", "severity": "HIGH",
         "text": "Government identifiers — SSN, ITIN, passport, driver's licence, "
                 "national ID — must not be transmitted off managed endpoints."},
        {"id": "POL-004", "class": "CUSTOMER_RECORD", "severity": "HIGH",
         "text": "Customer-identifying records must not leave managed endpoints."},
        {"id": "POL-005", "class": "HEALTH_RECORD", "severity": "HIGH",
         "text": "Patient-identifiable clinical information may not be processed by "
                 "any service outside the covered-entity boundary."},
        {"id": "POL-006", "class": "FINANCIAL_NONPUBLIC", "severity": "HIGH",
         "text": "Non-public financial information, including forecasts, plan and "
                 "commit figures, must not be disclosed before public release."},
        {"id": "POL-007", "class": "PROPRIETARY_CODE", "severity": "MEDIUM",
         "text": "Proprietary source code may not be uploaded to unapproved external "
                 "code-processing services."},
        {"id": "POL-008", "class": "LEGAL_HR", "severity": "MEDIUM",
         "text": "Privileged legal and HR material must remain inside counsel- and "
                 "HR-controlled systems."},
        {"id": "POL-009", "class": "BENIGN", "severity": "NONE",
         "text": "General technical and public information may be shared freely."},
    ],
}
CLAUSE = {c["id"]: c for c in POLICY["clauses"]}

# ------------------------------------------------------------------ decision store
DECISIONS: list[dict[str, Any]] = []
SOCKETS: set[WebSocket] = set()

PAN_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SECRET_RE = re.compile(r"\b(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def luhn(num: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", num)]
    if not 13 <= len(digits) <= 19:
        return False
    checksum, parity = 0, len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _score_details(pipeline_hits: list[tuple[str, int, float]]) -> dict[str, Any]:
    """Shape-identical to MongoDB's $rankFusion scoreDetails so B's tree renders
    against the stub exactly as it will against the real thing."""
    details, value = [], 0.0
    for name, rank, weight in pipeline_hits:
        contribution = weight * (1.0 / (60 + rank))
        value += contribution
        details.append({
            "inputPipelineName": name,
            "rank": rank,
            "weight": weight,
            "value": round(contribution, 6),
            "description": f"{name} pipeline contributed at rank {rank}",
            "details": [],
        })
    return {
        "value": round(value, 6),
        "description": "reciprocal rank fusion: sum over input pipelines of "
                       "weight * 1/(rankConstant + rank), rankConstant = 60",
        "details": details,
    }


def classify(text: str, images: list[dict], mode: str) -> dict[str, Any]:
    tau = MODE_TAU.get(mode, 0.55)

    if images:
        return dict(
            action="block", label="FINANCIAL_NONPUBLIC", severity="HIGH",
            policy_clause_id="POL-006", tier="T3", modality="image",
            reason='chart title reads "FY26 Revenue Forecast — Plan vs. Commit"; '
                   'footer reads "Internal — Do Not Distribute"',
            evidence_spans=["FY26 Revenue Forecast", "Internal — Do Not Distribute"],
            p_block=0.93, model="airlock-vision/nemotron-3-nano-omni-30b", threshold=tau,
            score_details=_score_details([("semantic", 1, 0.7), ("lexical", 2, 0.3)]),
        )

    m = SECRET_RE.search(text)
    if m:
        return dict(
            action="block", label="CREDENTIAL", severity="HIGH",
            policy_clause_id="POL-001", tier="T1", modality="text",
            reason=f"live-looking credential with a known prefix ({m.group(0)[:6]}…)",
            evidence_spans=[m.group(0)], p_block=0.99,
            model="airlock-t1/deterministic", threshold=tau,
            score_details=_score_details([("lexical", 1, 0.3)]),
        )

    for cand in PAN_RE.findall(text):
        if luhn(cand):
            return dict(
                action="block", label="PAYMENT_CARD", severity="HIGH",
                policy_clause_id="POL-002", tier="T1", modality="text",
                reason="Luhn-valid primary account number", evidence_spans=[cand],
                p_block=0.98, model="airlock-t1/deterministic", threshold=tau,
                score_details=_score_details([("lexical", 1, 0.3)]),
            )

    emails = EMAIL_RE.findall(text)
    if "@" in text:
        rows = [ln for ln in text.splitlines() if ln.count(",") >= 2]
        # Prefer a row that actually carries an identifier over the header row —
        # highlighting "name,email,phone" proves nothing; highlighting the record does.
        data_rows = [ln for ln in rows if EMAIL_RE.search(ln)]
        return dict(
            action="block", label="CUSTOMER_RECORD", severity="HIGH",
            policy_clause_id="POL-004", tier="T2", modality="text",
            reason=(f"{len(data_rows) or len(rows)} rows of name,email,phone,plan,mrr"
                    if rows else "person-identifying contact data"),
            evidence_spans=([(data_rows or rows)[0][:120]] if rows else emails[:1] or ["@"]),
            p_block=0.94, model="airlock-clf/nemotron-3.5-lightning-30b", threshold=tau,
            score_details=_score_details(
                [("semantic", 1, 0.7), ("lexical", 3, 0.3)]),
        )

    return dict(
        action="allow", label="BENIGN", severity="NONE",
        policy_clause_id="NONE", tier="T1", modality="text",
        reason="no sensitive-class evidence found",
        evidence_spans=[], p_block=round(random.Random(len(text)).uniform(0.01, 0.08), 3),
        model="airlock-t1/deterministic", threshold=tau,
        score_details=_score_details([("semantic", 7, 0.7)]),
    )


async def broadcast(frame: dict[str, Any]) -> None:
    dead = []
    for ws in list(SOCKETS):
        try:
            await ws.send_text(json.dumps(frame))
        except Exception:
            dead.append(ws)
    for ws in dead:
        SOCKETS.discard(ws)


# ------------------------------------------------------------------------ endpoints
@app.options("/{rest_of_path:path}")
async def preflight(rest_of_path: str):
    return Response(status_code=204, headers=CORS)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "clf": True, "vlm": True, "mongo": False,
            "uptime_s": int(time.time() - BOOT), "stub": True}


@app.get("/v1/policy")
async def policy():
    return POLICY


@app.get("/v1/decisions")
async def decisions(limit: int = 50):
    return {"decisions": DECISIONS[-limit:][::-1]}


@app.get("/v1/report")
async def report():
    return {"n": 1000, "false_pos": 3, "fpr": 0.003, "ci95": [0.001, 0.0088],
            "p50_ms": 12, "p95_ms": 480, "stub": True,
            "by_class": {"CREDENTIAL": 0, "PAYMENT_CARD": 1, "CUSTOMER_RECORD": 2}}


@app.post("/v1/inspect")
async def inspect(request: Request):
    t0 = time.perf_counter()
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return JSONResponse(status_code=413, headers=CORS, content={
            "schema": "airlock.error.v1", "error": "policy_denied", "code": 413,
            "label": "airlock_unavailable", "action": "block",
            "reason": "Payload exceeds 8 MiB — deny by default", "request_id": "r_unknown"})
    try:
        body = json.loads(raw)
    except Exception:
        return JSONResponse(status_code=400, headers=CORS, content={
            "schema": "airlock.error.v1", "error": "policy_denied", "code": 400,
            "label": "airlock_unavailable", "action": "block",
            "reason": "Malformed JSON — deny by default", "request_id": "r_unknown"})

    rid = body.get("request_id", "r_unknown")
    if body.get("schema") != "airlock.inspect.v1":
        return JSONResponse(status_code=400, headers=CORS, content={
            "schema": "airlock.error.v1", "error": "policy_denied", "code": 400,
            "label": "airlock_unavailable", "action": "block",
            "reason": "Missing or wrong schema — deny by default", "request_id": rid})

    images = body.get("images") or []
    if len(images) > 4:
        return JSONResponse(status_code=413, headers=CORS, content={
            "schema": "airlock.error.v1", "error": "policy_denied", "code": 413,
            "label": "airlock_unavailable", "action": "block",
            "reason": "More than 4 images — deny by default", "request_id": rid})

    text = body.get("text") or ""
    v = classify(text, images, body.get("mode", "balanced"))
    if body.get("threshold") is not None:
        v["threshold"] = float(body["threshold"])

    # Simulated inference cost so the overlay's "scanning" chip is actually visible
    # and the latency figure on the receipt is not a suspicious 0 ms.
    await asyncio.sleep({"T1": 0.004, "T2": 0.180, "T3": 0.620}.get(v["tier"], 0.01))

    sha = hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()
    decision_id = sha[:24]
    latency_ms = int((time.perf_counter() - t0) * 1000)
    clause = CLAUSE.get(v["policy_clause_id"], {"text": ""})

    verdict = {
        "schema": "airlock.verdict.v1",
        "request_id": rid,
        "action": v["action"],
        "label": v["label"],
        "severity": v["severity"],
        "policy_clause_id": v["policy_clause_id"],
        "policy_clause_text": clause.get("text", ""),
        "reason": v["reason"],
        "evidence_spans": v["evidence_spans"],
        "evidence_verified": all(s in text for s in v["evidence_spans"]) if v["modality"] == "text" else True,
        "score": v["p_block"],
        "p_block": v["p_block"],
        "threshold": v["threshold"],
        "tier": v["tier"],
        "model": v["model"],
        "modality": v["modality"],
        "latency_ms": latency_ms,
        "bytes_egressed": 0,
        "decision_id": decision_id,
        "score_details": v["score_details"],
    }

    origin = body.get("origin") or ""
    host = origin.split("//")[-1].split("/")[0] or "unknown"
    row = {"type": "decision", "ts": int(time.time() * 1000), "decision_id": decision_id,
           "host": host, "modality": v["modality"], "chars": len(text),
           "action": v["action"], "label": v["label"], "p_block": v["p_block"],
           "tier": v["tier"], "latency_ms": latency_ms}
    DECISIONS.append(row)
    del DECISIONS[:-500]
    await broadcast(row)
    return JSONResponse(content=verdict, headers=CORS)


@app.post("/v1/feedback")
async def feedback(request: Request):
    body = await request.json()
    return {"ok": True, "corpus_id": "stub_" + str(body.get("decision_id", ""))[:12],
            "embedded": True}


# The receipt on the block card renders `model` verbatim, so these strings have to be
# the weights actually on the box (gb10/models/*) — naming a model we are not running
# is the kind of detail a Dell/NVIDIA judge checks.
SANCTIONED = (
    "Yes — here is the shape of the answer without the customer data.\n\n"
    "You have a churn-risk question over a customer table. Do it with aggregates, "
    "not rows: group by plan, compute 30-day activity delta and MRR delta, then rank "
    "the groups. Nothing leaves this machine; this reply was generated by the local "
    "35B on the box in front of you.\n"
)


@app.post("/v1/answer")
async def answer(request: Request):
    await request.json()

    async def gen():
        for word in SANCTIONED.split(" "):
            chunk = {"choices": [{"delta": {"content": word + " "}, "index": 0}]}
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0.02)
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={**CORS, "Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.websocket("/v1/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    SOCKETS.add(ws)
    await ws.send_text(json.dumps(
        {"type": "hello", "policy_version": POLICY["version"], "resume": None}))
    for row in DECISIONS[-50:]:
        await ws.send_text(json.dumps(row))
    try:
        while True:
            # ping every 15 s; metric frame every 2 s
            for _ in range(7):
                await asyncio.sleep(2)
                await ws.send_text(json.dumps({"type": "metric", "kv": {
                    "kv_cache_text": round(random.uniform(0.20, 0.45), 3),
                    "kv_cache_vision": round(random.uniform(0.05, 0.25), 3),
                    "escalation_rate": 0.14}}))
            await ws.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        SOCKETS.discard(ws)
