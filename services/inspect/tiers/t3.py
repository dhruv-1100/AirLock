"""Tier 3 — image path scaffold (SRS §6.3/§6.4): transcribe, do not interpret,
then re-run T1+T2 on the OCR text. Full implementation lands in Phase 2 after
the 10:45 vision-latency gate (G1); until the VLM is up, any image payload
resolves fail-closed at the router.
"""

import os

import httpx

VLM_BASE_URL = os.environ.get("AIRLOCK_VLM_URL", "http://127.0.0.1:8001/v1")
VLM_MODEL = os.environ.get("AIRLOCK_VLM_MODEL", "Hcompany/Holo1.5-7B")
T3_TIMEOUT_S = 2.0  # server internal budget for the T3 call (SRS §5.1)

# Transcribe-only prompt: title, axis labels, legend, column headers,
# footnotes, watermarks, filenames, tab titles — never data values off bars
# or lines. Routes around documented VLM chart-reading failure modes.
TRANSCRIBE_PROMPT = (
    "Transcribe only the chrome text visible in this image: title, axis "
    "labels, legend entries, column headers, footnotes, watermarks, filenames "
    "and tab titles. Do NOT read data values off bars, lines or points. "
    "Output one line per text element, nothing else."
)


async def transcribe(image_b64: str, mime: str,
                     client: httpx.AsyncClient = None) -> str:
    """OCR the image chrome via the vision server. Raises on any failure —
    the router converts that into the fail-closed shape."""
    body = {
        "model": VLM_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": TRANSCRIBE_PROMPT},
            {"type": "image_url",
             "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ]}],
        "temperature": 0.0,
        "seed": 1337,
        "max_tokens": 512,
    }
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=T3_TIMEOUT_S)
    try:
        resp = await client.post(f"{VLM_BASE_URL}/chat/completions",
                                 json=body, timeout=T3_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    finally:
        if own:
            await client.aclose()
