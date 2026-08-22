"""Tier 3 — image path (SRS §6.3, §6.4, Phase 2).

Transcribe, do not interpret: the VLM reads chrome text (title, axis labels,
legend, headers, footnotes, watermarks, filenames, tab titles) and never data
values off bars or lines — that routes around every documented VLM
chart-reading failure mode. Classification is then grounded: unless a temporal
marker, a confidentiality marker, or a T1 hit exists in the transcribed text,
the verdict is forced BENIGN with override:"no_grounded_marker".
"""

import json
import os

import httpx

from ..schemas import CLAUSE_IDS
from . import t1

VLM_BASE_URL = os.environ.get("AIRLOCK_VLM_URL", "http://127.0.0.1:8001/v1")
# Request model NAME (--served-model-name), never a weights path.
VLM_MODEL = os.environ.get("AIRLOCK_VLM_MODEL", "airlock-vision")

# The Nemotron chat template defaults enable_thinking=True, so the model emits a
# "Here's a thinking process:" preamble before any JSON. Measured on this box: 200
# tokens consumed entirely by reasoning, finish_reason="length", NO JSON produced, and
# 3.16 s per call against a 1.2 s budget — every T2 call 504s and the FPR comes back
# near-total. With it off: 8 tokens, clean JSON, 236 ms. Set AIRLOCK_ENABLE_THINKING=1
# to restore reasoning.
_THINKING = os.getenv("AIRLOCK_ENABLE_THINKING", "0") not in ("0", "false", "no")
_CHAT_TEMPLATE_KWARGS = {"enable_thinking": _THINKING}
# SRS §5.1 budgets the T3 call at 2.0 s, derived arithmetically against Holo1.5-7B —
# and §7.1 flags that number as "the single largest unverified number in the project".
# The vision model on this box is Nemotron-3-Nano-Omni-30B BF16, four times the size.
# Override with AIRLOCK_T3_TIMEOUT_S; measured value recorded in results/t3_latency.md.
T3_TIMEOUT_S = float(os.getenv("AIRLOCK_T3_TIMEOUT_S", "2.0"))

# Text schema minus GOV_ID / PAYMENT_CARD (SRS §5.4).
VISION_LABELS = ["BENIGN", "CREDENTIAL", "CUSTOMER_RECORD", "HEALTH_RECORD",
                 "FINANCIAL_NONPUBLIC", "PROPRIETARY_CODE", "LEGAL_HR"]

# Property order is load-bearing: transcription precedes the label so the
# label is conditioned on grounded text, not on the pixels directly.
VISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["image_type", "extracted_text", "org_markers",
                 "temporal_markers", "confidentiality_markers",
                 "evidence_spans", "rationale", "label", "severity",
                 "policy_clause_id", "confidence"],
    "properties": {
        "image_type": {"type": "string",
                       "enum": ["chart", "table", "screenshot", "document",
                                "photo", "diagram", "other"]},
        "extracted_text": {"type": "array", "maxItems": 30,
                           "items": {"type": "string", "maxLength": 100}},
        "org_markers": {"type": "array", "maxItems": 5,
                        "items": {"type": "string", "maxLength": 80}},
        "temporal_markers": {"type": "array", "maxItems": 5,
                             "items": {"type": "string", "maxLength": 80}},
        "confidentiality_markers": {"type": "array", "maxItems": 5,
                                    "items": {"type": "string", "maxLength": 80}},
        "evidence_spans": {"type": "array", "maxItems": 3,
                           "items": {"type": "string", "maxLength": 120}},
        "rationale": {"type": "string", "maxLength": 160},
        "label": {"type": "string", "enum": VISION_LABELS},
        "severity": {"type": "string", "enum": ["NONE", "LOW", "MEDIUM", "HIGH"]},
        "policy_clause_id": {"type": "string", "enum": CLAUSE_IDS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

VISION_PROMPT = """You are AIRLOCK, a local data-egress inspector examining an image an employee
is about to upload to an external AI service.

STEP 1 — TRANSCRIBE, DO NOT INTERPRET. Copy into extracted_text only the
chrome text you can literally read: title, axis labels, legend entries, column
headers, footnotes, watermarks, filenames, tab titles. Do NOT read data values
off bars, lines or points. Do NOT guess text you cannot read.

Then copy any of the transcribed items that are:
  org_markers            company names, logos text, internal system names
  temporal_markers       forward-looking periods: FY26, Q3 plan, forecast,
                         projection, target, pipeline
  confidentiality_markers  Internal, Confidential, Do Not Distribute, NDA,
                         Draft, Restricted

STEP 2 — CLASSIFY from the transcribed text only. DEFAULT TO "BENIGN".
FINANCIAL_NONPUBLIC requires BOTH financial vocabulary AND a forward-looking
or internal marker in the transcribed text. Public charts, textbook figures,
documentation screenshots and photos without sensitive text are BENIGN.
Every non-BENIGN verdict must quote its evidence_spans from extracted_text.
Output only the JSON object."""


async def classify_image(image_b64: str, mime: str,
                         client: httpx.AsyncClient = None):
    """Returns (verdict_dict, model_name). Raises on failure — the router
    converts any failure into the fail-closed shape. Never fails open."""
    # Same guided-JSON spelling ladder as T2 (SRS §5.4), for VISION_SCHEMA.
    spellings = [
        {"response_format": {"type": "json_schema",
                             "json_schema": {"name": "airlock_vision",
                                             "schema": VISION_SCHEMA}}},
        {"structured_outputs": {"json": VISION_SCHEMA}},
        {"guided_json": VISION_SCHEMA},
    ]
    base = {
        "chat_template_kwargs": _CHAT_TEMPLATE_KWARGS,
        "model": VLM_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": VISION_PROMPT},
            {"type": "image_url",
             "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ]}],
        "temperature": 0.0,
        "seed": 1337,
        "max_tokens": 700,
    }
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=T3_TIMEOUT_S)
    try:
        last_err = None
        for spelling in spellings:
            body = {**base, **spelling}
            try:
                resp = await client.post(f"{VLM_BASE_URL}/chat/completions",
                                         json=body, timeout=T3_TIMEOUT_S)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                last_err = e
                if e.response.status_code in (400, 422):
                    continue
                raise
            data = resp.json()
            verdict = json.loads(data["choices"][0]["message"]["content"])
            return verdict, data.get("model", VLM_MODEL)
        raise last_err or RuntimeError("no guided-JSON spelling accepted")
    finally:
        if own:
            await client.aclose()


def ground(verdict: dict) -> tuple[dict, str]:
    """Grounding post-process (SRS Phase 2 item 2). Returns (verdict, ocr_text).

    Re-runs t1.scan over the joined transcription; forces BENIGN with
    override:"no_grounded_marker" unless a temporal marker, a confidentiality
    marker, or a T1 hit is present.
    """
    ocr_text = " ".join(verdict.get("extracted_text") or [])
    if verdict.get("label", "BENIGN") == "BENIGN":
        return verdict, ocr_text
    t1_hit = t1.scan(ocr_text)
    grounded = (verdict.get("temporal_markers")
                or verdict.get("confidentiality_markers")
                or t1_hit.confidence is not None)
    if not grounded:
        return ({**verdict, "label": "BENIGN", "severity": "NONE",
                 "policy_clause_id": "NONE",
                 "override": "no_grounded_marker",
                 "reason": "no_grounded_marker"}, ocr_text)
    return verdict, ocr_text
