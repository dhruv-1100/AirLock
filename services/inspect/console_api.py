"""services/inspect/console_api.py — owner C.

The three endpoints B's console calls that A's `app.py` does not implement:

    GET  /v1/decisions?limit=50     console backfill        -> mongo.recent_decisions()
    GET  /v1/policy                 clause text for overlay -> policy.yaml
    WS   /v1/stream                 live decision feed      -> ConsoleHub / change stream

Found by diffing B's `sw.js` + `console.js` against A's route table: B calls all three,
A implements none. They are all MongoDB- or policy-backed, so they are C's.

------------------------------------------------------------------------------
A: mount this with ONE line in app.py, near the other route definitions:

    from .console_api import router as console_router
    app.include_router(console_router)

That is the whole integration. This module owns its own Mongo lifecycle, degrades to
an empty feed when Mongo is down, and never raises into your request path.
------------------------------------------------------------------------------

Nothing here edits `app.py` — per SRS §9, C may read A's service to write about it but
may not edit it.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from . import mongo as M
from .stream import ConsoleHub

log = logging.getLogger("airlock.console_api")

router = APIRouter()
hub = ConsoleHub()

_POLICY_CACHE: dict[str, Any] | None = None
_started = False


# --------------------------------------------------------------------------- policy
def _load_policy() -> dict:
    """Read services/inspect/policy.yaml. Falls back to a minimal built-in list so the
    overlay always has clause text to render — a block that cannot cite its clause is a
    worse failure than a slightly stale clause string."""
    global _POLICY_CACHE
    if _POLICY_CACHE is not None:
        return _POLICY_CACHE

    path = Path(__file__).with_name("policy.yaml")
    clauses: list[dict] = []
    version = "policy_v1"
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text())
        version = data.get("version", version)
        for c in data.get("clauses", []):
            clauses.append(
                {
                    "id": c["id"],
                    "class": c.get("class", ""),
                    "severity": c.get("severity", "MEDIUM"),
                    "text": " ".join(str(c.get("text", "")).split()),
                }
            )
    except Exception as e:  # noqa: BLE001
        log.warning("policy.yaml unreadable (%s) — using built-in clause list", e)
        clauses = [
            {"id": "POL-001", "class": "CREDENTIAL", "severity": "HIGH",
             "text": "Live authentication material must never leave a managed endpoint."},
            {"id": "POL-002", "class": "PAYMENT_CARD", "severity": "HIGH",
             "text": "Primary account numbers must not be transmitted to third-party services."},
            {"id": "POL-003", "class": "GOV_ID", "severity": "HIGH",
             "text": "Government-issued identifiers must not be shared with external processors."},
            {"id": "POL-004", "class": "CUSTOMER_RECORD", "severity": "HIGH",
             "text": "Customer-identifying records must not leave managed endpoints."},
            {"id": "POL-005", "class": "HEALTH_RECORD", "severity": "HIGH",
             "text": "Patient-identifiable clinical information must not be transmitted externally."},
            {"id": "POL-006", "class": "FINANCIAL_NONPUBLIC", "severity": "HIGH",
             "text": "Financial information not yet released publicly must not be disclosed."},
            {"id": "POL-007", "class": "PROPRIETARY_CODE", "severity": "MEDIUM",
             "text": "Internal source code and infrastructure configuration must not be pasted externally."},
            {"id": "POL-008", "class": "LEGAL_HR", "severity": "HIGH",
             "text": "Material under legal privilege or confidentiality obligation must not be shared."},
        ]
    _POLICY_CACHE = {"version": version, "clauses": clauses}
    return _POLICY_CACHE


@router.get("/v1/policy")
async def get_policy() -> dict:
    """Clause text for the block overlay. Static, cached, never fails."""
    return _load_policy()


# --------------------------------------------------------------------------- decisions
@router.get("/v1/decisions")
async def get_decisions(limit: int = Query(50, ge=1, le=500)) -> dict:
    """Console backfill. `evidence_png` is projected out server-side — the console never
    needs it and it is the only large field in the document.

    Returns an empty list rather than an error when Mongo is unavailable: a console with
    no history is a degraded console, but a 500 here would make B's panel look broken
    when the detector is in fact working fine.
    """
    await _ensure_started()
    return {"decisions": await M.recent_decisions(limit), "mongo": await M.healthy()}


# --------------------------------------------------------------------------- report
@router.get("/v1/report")
async def get_report() -> dict:
    """FP-rate report served from the `benign_eval` aggregation.

    A's app.py also defines /v1/report, reading results/report.json from disk. Whichever
    router is mounted last wins in FastAPI, so **A's file-backed version is the default
    and this is the live-from-Mongo alternative.** If you want this one, mount the router
    before A's route is declared, or rename this path. Documented rather than silently
    shadowing: two /v1/report implementations disagreeing on stage is a bad afternoon.
    """
    await _ensure_started()
    return await M.fpr_report()


# --------------------------------------------------------------------------- websocket
@router.websocket("/v1/stream")
async def stream(ws: WebSocket) -> None:
    """Live decision feed. Server→client only; the client sends at most one hello frame.

    Backed by a MongoDB change stream on `decisions` with the invalidate → startAfter
    transition, so it survives the several re-seeds that happen during the build day.
    """
    await ws.accept()
    await _ensure_started()
    await hub.register(ws)
    try:
        while True:
            # We do not act on client frames; this read exists to detect disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.debug("stream client dropped: %s", e)
    finally:
        hub.unregister(ws)


# --------------------------------------------------------------------------- lifecycle
async def _ensure_started() -> None:
    """Lazy start so importing this module never blocks A's app startup, and a Mongo that
    is not up yet at import time is not a permanent failure."""
    global _started
    if _started:
        return
    _started = True
    try:
        if M._db is None:
            await M.connect()
        await hub.start()
    except Exception as e:  # noqa: BLE001
        log.error("console hub failed to start (%s) — feed will be empty", e)


async def shutdown() -> None:
    await hub.stop()


__all__ = ["router", "hub", "shutdown"]
