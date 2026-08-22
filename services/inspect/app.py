"""airlock inspect-svc — FastAPI on 127.0.0.1:8787 (SRS §5, §6.4).

Router, not an AND-cascade:  CACHE → T0 → T1-HIGH → T2  (T3 for images).
Fail closed everywhere: any internal failure returns the policy_denied shape,
never an allow. CPU-only process — never imports torch, never touches a GPU
(NFR-S1).

Run:  uvicorn services.inspect.app:app --host 127.0.0.1 --port 8787
"""

import asyncio
import base64
import binascii
import hashlib
import json
import os
import time
import uuid

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from . import verify as verify_mod
from .calib import label_logits_from_logprobs, p_block_from_logprobs
from .schemas import (DEFAULT_MODE, LABEL_TO_CLAUSE, MODES, error_body,
                      verdict_body)
from .tiers import gate_img, t0, t1, t2, t3
from .verify import verify

MAX_BODY = 8 * 1024 * 1024
MAX_INFLIGHT = 32
TOTAL_BUDGET_S = 2.3

# Phase 3 ablation rows (SRS §10 Phase 3 item 5) — each row is a real run of
# the service under a different router config, driven by bench/run_ablation.py:
#   full         normal router (default)
#   t1_only      CACHE/T2 off; only T1-HIGH may block
#   t2_noverify  T0/T1-block/CACHE off; everything to T2, span verification OFF
#   t2_verify    same but span verification ON (row3 − row2 = the finding)
ABLATION = os.environ.get("AIRLOCK_ABLATION", "full")

# C owns mongo.py; the cache degrades to in-process when it is absent so A is
# never blocked on C (Phase-0 parallelism rule). mongo.py itself no-ops every
# call when MONGO_ENABLED=false or the server is unreachable.
try:
    from . import mongo
    _HAVE_MONGO = True
except ImportError:
    _HAVE_MONGO = False

app = FastAPI(title="airlock inspect-svc")

# C's console surface: GET /v1/decisions, GET /v1/policy, ws /v1/stream
# (INTEGRATION.md §1 — B's console is dead without this).
try:
    from .console_api import router as console_router
    app.include_router(console_router)
except ImportError:
    pass


@app.on_event("startup")
async def _connect_mongo():
    if _HAVE_MONGO:
        await mongo.connect()
_started = time.monotonic()
_inflight = asyncio.Semaphore(MAX_INFLIGHT)
_cache: dict[str, dict] = {}  # payload_sha256 → verdict body (instant re-block)

CLAUSES = {
    "POL-001": "Live credentials and secrets must never leave managed endpoints.",
    "POL-002": "Real payment card data must not be sent to external services.",
    "POL-003": "Government identifiers must not leave managed endpoints.",
    "POL-004": "Customer-identifying records must not leave managed endpoints.",
    "POL-005": "Patient-identifiable health information must never be shared externally.",
    "POL-006": "Unreleased financial information must not be disclosed before announcement.",
    "POL-007": "Internal source code and infrastructure configuration stay internal.",
    "POL-008": "NDA'd, litigation, and HR matters must not be shared externally.",
    "NONE": "",
}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Private-Network": "true",
    "Access-Control-Max-Age": "600",
}


@app.middleware("http")
async def cors(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=CORS_HEADERS)
    resp = await call_next(request)
    resp.headers.update(CORS_HEADERS)
    return resp


async def _probe(url):
    try:
        async with httpx.AsyncClient(timeout=0.3) as c:
            r = await c.get(url)
            return r.status_code == 200
    except httpx.HTTPError:
        return False


@app.get("/healthz")
async def healthz():
    clf, vlm = await asyncio.gather(
        _probe(t2.CLF_BASE_URL.rsplit("/v1", 1)[0] + "/health"),
        _probe(t3.VLM_BASE_URL.rsplit("/v1", 1)[0] + "/health"))
    return {"ok": True, "clf": clf, "vlm": vlm, "mongo": _HAVE_MONGO,
            "uptime_s": int(time.monotonic() - _started),
            "overrides": verify_mod.override_count,
            "img_gate": {"seen": gate_img.seen_count,
                         "fast_passed": gate_img.fast_pass_count}}


def _err(code, label, reason, request_id):
    return JSONResponse(status_code=code,
                        content=error_body(code, label, reason, request_id))


@app.post("/v1/inspect")
async def inspect(request: Request):
    raw = await request.body()
    rid = "r_" + uuid.uuid4().hex[:6]
    if len(raw) > MAX_BODY:
        return _err(413, "body_too_large", "Body exceeds 8 MiB", rid)
    try:
        req = json.loads(raw)
    except json.JSONDecodeError:
        return _err(400, "malformed_json", "Body is not valid JSON", rid)
    if req.get("schema") != "airlock.inspect.v1":
        return _err(400, "bad_schema", "Missing or unknown schema", rid)
    rid = req.get("request_id", rid)
    images = req.get("images") or []
    if len(images) > 4:
        return _err(413, "too_many_images", "More than 4 images", rid)
    for im in images:
        try:
            base64.b64decode(im.get("b64", ""), validate=True)
        except (binascii.Error, ValueError):
            return _err(422, "image_decode_failure", "Invalid base64 image", rid)

    if _inflight.locked():
        return _err(429, "overloaded", "More than 32 requests in flight", rid)
    async with _inflight:
        try:
            return await asyncio.wait_for(_route(req, rid), TOTAL_BUDGET_S)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            return _err(504, "airlock_timeout",
                        "Upstream classifier exceeded budget — deny by default", rid)
        except Exception:
            return _err(503, "airlock_unavailable",
                        "Inspector unreachable — deny by default", rid)


def _respond(rid, *, action, label, severity, reason, spans, verified, p_block,
             threshold, tier, model, modality, t_start, score_details=None,
             clause_id=None):
    clause_id = clause_id or LABEL_TO_CLAUSE.get(label, "NONE")
    body = verdict_body(
        request_id=rid, action=action, label=label, severity=severity,
        clause_id=clause_id, clause_text=CLAUSES.get(clause_id, ""),
        reason=reason, evidence_spans=spans, evidence_verified=verified,
        p_block=round(p_block, 4), threshold=threshold, tier=tier, model=model,
        modality=modality, latency_ms=int((time.monotonic() - t_start) * 1000),
        decision_id=uuid.uuid4().hex[:24], score_details=score_details)
    return body


async def _finish(body, key, *, origin="", text="", n_images=0, cache=False):
    """Persist the decision (INTEGRATION.md §2: payload_text on blocks so
    write_back_corpus can embed the real paste on beat 4), then respond.
    write_decision never raises and returns a fake id in no-op mode."""
    if _HAVE_MONGO:
        body["decision_id"] = await mongo.write_decision(
            body, key, origin=origin, chars=len(text), images=n_images,
            payload_text=text if body["action"] in ("block", "warn") else None)
    if cache and body["action"] == "block" and ABLATION == "full":
        _cache[key] = body
    return JSONResponse(body)


async def _route(req, rid):
    t_start = time.monotonic()
    text = req.get("text") or ""
    origin = req.get("origin") or ""
    images = req.get("images") or []
    modality = "image" if images else "text"
    mode = req.get("mode") or DEFAULT_MODE
    threshold = req.get("threshold") or MODES.get(mode, MODES[DEFAULT_MODE])
    audit_only = mode == "audit"  # audit logs, never blocks (SRS §6.5)

    def block_action():
        return "warn" if audit_only else "block"

    # ---- CACHE — sha256 replay, ~1 ms: in-process first, then Mongo -------
    key = hashlib.sha256(
        (text + "".join(im.get("b64", "") for im in images)).encode()).hexdigest()
    hit = _cache.get(key) if ABLATION == "full" else None
    if hit:
        hit = dict(hit)
        hit.update(request_id=rid, tier="CACHE",
                   latency_ms=int((time.monotonic() - t_start) * 1000))
        return JSONResponse(hit)
    if _HAVE_MONGO and ABLATION == "full":
        # Mongo decisions doc → verdict body (fields differ; binaries dropped).
        doc = await mongo.get_by_hash(key)
        if doc:
            blocked = doc.get("verdict") == "BLOCK"
            clause_id = doc.get("clause_id", "NONE")
            body = _respond(
                rid,
                action=("warn" if (blocked and audit_only) else
                        "block" if blocked else "allow"),
                label=doc.get("label", "BENIGN"),
                severity="HIGH" if blocked else "NONE",
                reason="Instant re-block: identical payload previously decided",
                spans=doc.get("evidence_spans", []),
                verified=bool(doc.get("span_verified")),
                p_block=float(doc.get("p_block", 0.0)),
                threshold=threshold, tier="CACHE", model="cache",
                modality=modality, t_start=t_start,
                score_details=doc.get("score_details"),
                clause_id=clause_id)
            return await _finish(body, key, origin=origin,
                                 n_images=len(images))

    # ---- T3 — image path: cheap gate → VLM transcribe+classify → ground ---
    if images:
        im = images[0]
        gate = gate_img.inspect_image(im["b64"])
        if gate.fast_pass:
            # One-sided: the gate may only fast-pass, never block.
            body = _respond(
                rid, action="allow", label="BENIGN", severity="NONE",
                reason="Pre-VLM gate: natural image, no text-like structure",
                spans=[], verified=True, p_block=0.0, threshold=threshold,
                tier="T3", model="gate_img", modality="image", t_start=t_start)
            return await _finish(body, key, origin=origin, n_images=1)
        verdict, model = await t3.classify_image(im["b64"],
                                                 im.get("mime", "image/jpeg"))
        verdict, ocr_text = t3.ground(verdict)
        verdict = verify(verdict, ocr_text + "\n" + text)
        # §6.4: re-run T1 on the OCR text — a screenshotted credential or PAN
        # blocks deterministically even when the VLM classifies benign.
        t1_ocr = t1.scan(ocr_text)
        if verdict["label"] == "BENIGN" and t1_ocr.confidence == "HIGH":
            body = _respond(
                rid, action=block_action(), label=t1_ocr.label, severity="HIGH",
                reason=f"Deterministic detector on transcription: {t1_ocr.detector}",
                spans=t1_ocr.evidence_spans, verified=True, p_block=1.0,
                threshold=threshold, tier="T3", model="airlock-vision+t1",
                modality="image", t_start=t_start)
            return await _finish(body, key, origin=origin, text=ocr_text,
                                 n_images=1, cache=True)
        label = verdict["label"]
        p_block = (float(verdict.get("confidence", 0.5))
                   if label != "BENIGN" else 0.0)
        blocked = label != "BENIGN" and p_block >= threshold
        markers = (verdict.get("temporal_markers") or []) + \
                  (verdict.get("confidentiality_markers") or [])
        body = _respond(
            rid,
            action=(block_action() if blocked else "allow"),
            label=label if blocked else "BENIGN",
            severity=verdict.get("severity", "NONE") if blocked else "NONE",
            reason=(f"{verdict.get('rationale', '')} Markers: "
                    f"{', '.join(markers)}" if blocked
                    else verdict.get("reason", verdict.get("rationale", ""))),
            spans=verdict.get("evidence_spans", []) if blocked else [],
            verified="override" not in verdict,
            p_block=p_block, threshold=threshold, tier="T3",
            model=f"airlock-vision/{model}", modality="image",
            t_start=t_start,
            clause_id=verdict.get("policy_clause_id") if blocked else "NONE")
        return await _finish(body, key, origin=origin, text=ocr_text,
                             n_images=1, cache=True)

    # ---- T0 — trivial gate ------------------------------------------------
    if (modality == "text" and t0.is_trivial(text)
            and ABLATION not in ("t2_noverify", "t2_verify")):
        body = _respond(
            rid, action="allow", label="BENIGN", severity="NONE",
            reason="Trivial payload", spans=[], verified=True, p_block=0.0,
            threshold=threshold, tier="T0", model="none", modality=modality,
            t_start=t_start)
        return await _finish(body, key, origin=origin, text=text)

    # ---- T1 — deterministic scan ------------------------------------------
    scan = t1.scan(text)
    if scan.confidence == "HIGH" and ABLATION not in ("t2_noverify", "t2_verify"):
        body = _respond(
            rid, action=block_action(), label=scan.label, severity="HIGH",
            reason=f"Deterministic detector: {scan.detector}",
            spans=scan.evidence_spans, verified=True, p_block=1.0,
            threshold=threshold, tier="T1" if modality == "text" else "T3",
            model="none", modality=modality, t_start=t_start)
        return await _finish(body, key, origin=origin, text=text, cache=True)

    if ABLATION == "t1_only":
        # Row 1: no LLM. Whatever T1 could not block is an allow.
        body = _respond(
            rid, action="allow", label="BENIGN", severity="NONE",
            reason=f"T1-only ablation; hints suppressed: {scan.hints}",
            spans=[], verified=True, p_block=0.0, threshold=threshold,
            tier="T1", model="none", modality=modality, t_start=t_start)
        return await _finish(body, key, origin=origin, text=text)

    # ---- T2 — LLM classifier, guided JSON, span-verified ------------------
    verdict, logprobs, model = await t2.classify(text, hints=scan.hints or None)
    if ABLATION != "t2_noverify":  # row 2 measures the cost of skipping this
        verdict = verify(verdict, text)
    p_block = p_block_from_logprobs(logprobs, verdict)
    label = verdict["label"]
    blocked = label != "BENIGN" and p_block >= threshold

    body = _respond(
        rid,
        action=(block_action() if blocked else "allow"),
        label=label if blocked else "BENIGN",
        severity=verdict.get("severity", "NONE") if blocked else "NONE",
        reason=verdict.get("rationale", ""),
        spans=verdict.get("evidence_spans", []) if blocked else [],
        verified="override" not in verdict,
        p_block=p_block, threshold=threshold,
        tier="T2" if modality == "text" else "T3",
        model=f"airlock-clf/{model}", modality=modality, t_start=t_start,
        clause_id=verdict.get("policy_clause_id") if blocked else "NONE")
    if req.get("debug_label_logits"):
        # Harness-only (bench/fit_calibration.py): raw label logits so the
        # temperature sweep is offline. Never set by the extension.
        try:
            body["label_logits"] = label_logits_from_logprobs(logprobs)
        except (KeyError, ValueError, TypeError):
            body["label_logits"] = None
    return await _finish(body, key, origin=origin, text=text, cache=True)


TEXT_BASE_URL = os.environ.get("AIRLOCK_TEXT_URL", "http://127.0.0.1:8000/v1")
TEXT_MODEL = os.environ.get("AIRLOCK_TEXT_MODEL", "Qwen/Qwen3.6-35B-A3B")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                           "results", "report.json")


@app.post("/v1/answer")
async def answer(request: Request):
    """Sanctioned path (SRS §5.2): the blocked question, re-answered by the
    local model. SSE passthrough of :8000 in OpenAI chat delta shape."""
    req = await request.json()
    rid = "r_" + uuid.uuid4().hex[:6]
    prompt = req.get("prompt")
    if not prompt:
        return _err(400, "bad_request", "Missing prompt", rid)

    async def stream():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=3)) as c:
                async with c.stream(
                        "POST", f"{TEXT_BASE_URL}/chat/completions",
                        json={"model": TEXT_MODEL, "stream": True,
                              "messages": [{"role": "user", "content": prompt}]},
                ) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except httpx.HTTPError:
            err = json.dumps(error_body(503, "answer_unavailable",
                                        "Local model unreachable", rid))
            yield f"data: {err}\n\ndata: [DONE]\n\n".encode()

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/v1/feedback")
async def feedback(request: Request):
    """Analyst marks a decision benign → payload embedded back into
    policy_corpus (procedural memory). Real write-back is C's
    write_back_corpus(); a logged no-op until mongo.py lands."""
    req = await request.json()
    rid = "r_" + uuid.uuid4().hex[:6]
    decision_id = req.get("decision_id")
    if not decision_id:
        return _err(400, "bad_request", "Missing decision_id", rid)
    if _HAVE_MONGO and hasattr(mongo, "write_back_corpus"):
        corpus_id = await mongo.write_back_corpus(decision_id)
        return {"ok": True, "corpus_id": str(corpus_id), "embedded": True}
    return {"ok": True, "corpus_id": f"stub_{decision_id[:8]}", "embedded": False}


@app.get("/v1/report")
async def report():
    """FP-rate report (SRS §5.2) — served from bench/run_fpr.py output
    (results/report.json); the benign_eval aggregation replaces this file
    read when Mongo is up."""
    try:
        with open(REPORT_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={
            "error": "no_report", "reason": "bench/run_fpr.py has not run yet"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8787)))
