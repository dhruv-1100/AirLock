"""services/inspect/origins.py — which browser origins may call which routes.

The gateway used to answer every origin with `Access-Control-Allow-Origin: *` and
`Access-Control-Allow-Private-Network: true`, and checked no origin anywhere. A request
carrying `Origin: https://evil.example` could read `/v1/decisions` — whose rows carried
`evidence_spans`, the literal text Airlock had blocked — and POST `/v1/feedback` to mark
decisions benign and teach the detector to stop blocking a pattern. PLAN.md B1.

Two tiers:

  PUBLIC      any origin. Returns nothing beyond what the caller itself sent, or static
              policy text. `/v1/inspect` and `/healthz` must stay here: the extension's
              content-script fallback (`airlock.js` direct()) calls them from the page's
              own origin when the service worker is asleep.

  RESTRICTED  allowlisted origins only. Anything that returns other pastes' data,
              writes state, or spends model time.

A request with NO Origin header is allowed everywhere. Browsers always send Origin on
cross-origin requests, so a missing header means a non-browser client (curl, the FPR
harness) — which no web page can drive and which CORS never governed anyway.

Allowlist, overridable:
  AIRLOCK_EXTENSION_ID     pin the extension to one ID. Unset → any chrome-extension://
                           origin is accepted, because an unpacked extension without a
                           manifest "key" gets a path-derived ID that differs per machine.
                           Pin it on a real deployment.
  AIRLOCK_ALLOWED_ORIGINS  comma-separated extra origins.
"""

from __future__ import annotations

import os

PUBLIC_PATHS = ("/healthz", "/v1/inspect", "/v1/policy")

_LOCAL_PAGES = {
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in (5173, 5174, 5175)          # replica, projector console, overlay harness
}


def _extra() -> set[str]:
    raw = os.getenv("AIRLOCK_ALLOWED_ORIGINS", "")
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS


def origin_allowed(origin: str | None) -> bool:
    """True if this origin may call RESTRICTED routes."""
    if not origin:
        return True                          # non-browser client — see module docstring
    origin = origin.rstrip("/")
    if origin.startswith("chrome-extension://"):
        pinned = os.getenv("AIRLOCK_EXTENSION_ID")
        return (origin == f"chrome-extension://{pinned}") if pinned else True
    return origin in _LOCAL_PAGES or origin in _extra()


def cors_headers(origin: str | None, path: str) -> dict[str, str] | None:
    """CORS headers for this (origin, path), or None if the request must be refused.

    Echoes the specific origin rather than `*` on restricted routes, with `Vary: Origin`
    so a cache cannot hand one origin's grant to another.
    """
    base = {
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Private-Network": "true",
        "Access-Control-Max-Age": "600",
    }
    if is_public(path):
        return {**base, "Access-Control-Allow-Origin": "*"}
    if not origin_allowed(origin):
        return None
    return {**base, "Access-Control-Allow-Origin": origin or "*", "Vary": "Origin"}
