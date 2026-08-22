"""services/inspect/stream.py — owner C. SRS §4 (Console feed), §5.3, Risk R11.

The live console is PUSH, not poll. That is also the reason `decisions` cannot be a
time-series collection: time-series collections support neither change streams nor
Search nor CSFLE.

**The load-bearing detail in this file is the `invalidate` → `startAfter` transition.**
`resumeAfter` CANNOT resume past an `invalidate`, and an `invalidate` fires whenever the
watched collection is dropped. `stack/seed.js` drops and recreates `decisions` several
times over the build day. Without this transition the console dies permanently on the
first re-seed, and it dies *silently* — the socket stays open and no frames arrive, which
reads on stage as "the detector stopped working".

Public surface:
    tail_decisions(on_event)      raw change-stream tail with resume-token persistence
    ConsoleHub                    fan-out to N websockets + backfill + metric frames
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable

log = logging.getLogger("airlock.stream")

TOKEN_FILE = os.getenv("AIRLOCK_RESUME_TOKEN_FILE", ".airlock_resume_token")
METRIC_INTERVAL_S = 2.0
PING_INTERVAL_S = 15.0

# vLLM /metrics endpoints, scraped for the KV-cache gauges (SRS §5.3).
# READ-ONLY GETs. This starts, stops and restarts nothing — NFR-S1 is not in play.
TEXT_METRICS = os.getenv("AIRLOCK_TEXT_METRICS", "http://127.0.0.1:8000/metrics")
VISION_METRICS = os.getenv("AIRLOCK_VISION_METRICS", "http://127.0.0.1:8001/metrics")
HEALTHZ_URL = os.getenv("AIRLOCK_HEALTHZ", "http://127.0.0.1:8787/healthz")

# vLLM renamed this counter. Current builds emit `vllm:kv_cache_usage_perc`; older ones
# emit `vllm:gpu_cache_usage_perc`. Accept both rather than pinning to one and silently
# reading nothing on the other. Verified by B against the live :8000 output on the box.
_KV_RE = re.compile(
    r"^vllm:(?:kv_cache|gpu_cache)_usage_perc(?:\{[^}]*\})?\s+([0-9.eE+-]+)\s*$",
    re.MULTILINE,
)


# --------------------------------------------------------------------------- token persistence
def _save_token(token: dict | None) -> None:
    if not token:
        return
    try:
        with open(TOKEN_FILE, "w") as f:
            json.dump(token, f)
    except Exception as e:  # noqa: BLE001
        log.debug("resume token not persisted (non-fatal): %s", e)


def _load_token() -> dict | None:
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- the tail
async def tail_decisions(
    on_event: Callable[[dict], Awaitable[None]],
    coll: Any = None,
    token: dict | None = None,
    use_start_after: bool = False,
) -> None:
    """Tail `decisions` forever, surviving drops, reconnects and re-seeds.

    Verbatim in structure from SRS §4 — do not "tidy" the invalidate branch away.
    """
    from pymongo.errors import PyMongoError

    if coll is None:
        from . import mongo as _mongo  # local import keeps this module importable alone

        if _mongo._db is None:
            await _mongo.connect()
        if _mongo._db is None:
            log.error("no mongo — console tail not started")
            return
        coll = _mongo._db["decisions"]

    if token is None:
        token = _load_token()

    pipeline = [{"$match": {"operationType": {"$in": ["insert", "update", "invalidate"]}}}]

    while True:
        try:
            kwargs: dict[str, Any] = {"full_document": "updateLookup"}
            if token:
                # startAfter is the ONLY key that can cross an invalidate.
                kwargs["start_after" if use_start_after else "resume_after"] = token

            async with coll.watch(pipeline, **kwargs) as stream:
                log.info(
                    "change stream open (%s)",
                    "startAfter" if use_start_after else ("resumeAfter" if token else "fresh"),
                )
                async for change in stream:
                    token = change["_id"]  # persist EVERY event
                    _save_token(token)

                    if change["operationType"] == "invalidate":
                        # The collection was dropped — almost certainly a re-seed.
                        # resumeAfter cannot cross this boundary. Flip to startAfter and
                        # reopen. This is the line that keeps the console alive all day.
                        log.warning("invalidate — collection dropped; switching to startAfter")
                        use_start_after = True
                        break

                    use_start_after = False
                    doc = change.get("fullDocument")
                    if doc:
                        await on_event(doc)

                    # High-watermark token: keeps us from falling behind the oplog during
                    # a quiet period on a busy single-node replica set.
                    if stream.resume_token:
                        token = stream.resume_token
                        _save_token(token)

        except PyMongoError as e:
            log.warning("change stream error (%s) — retrying in 1s", e)
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("unexpected change stream failure: %s", e)
            await asyncio.sleep(1)


# --------------------------------------------------------------------------- websocket hub
class ConsoleHub:
    """Fan-out for `ws://127.0.0.1:8787/v1/stream`.

    Server→client only. Frame types per SRS §5.3: hello, decision, metric, ping.
    One JSON object per frame, newline-free.
    """

    def __init__(self, policy_version: str = "policy_v1") -> None:
        self._clients: set[Any] = set()
        self._policy_version = policy_version
        self._tasks: list[asyncio.Task] = []
        self._metrics: dict[str, float] = {}
        self._started = False

    # -- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._tasks = [
            asyncio.create_task(tail_decisions(self._on_decision)),
            asyncio.create_task(self._ping_loop()),
            asyncio.create_task(self._metric_loop()),
            asyncio.create_task(self._scrape_loop()),
        ]
        log.info("console hub started")

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self._tasks.clear()
        self._started = False

    # -- client registration ---------------------------------------------
    async def register(self, ws: Any) -> None:
        """Attach a websocket: send hello, backfill the last 50, then stream live."""
        self._clients.add(ws)
        await self._send(
            ws,
            {
                "type": "hello",
                "policy_version": self._policy_version,
                "resume": _load_token(),
            },
        )
        try:
            from . import mongo as _mongo

            # Backfill, THEN tail. Never point the console at benign_eval — the harness
            # writes 1000 docs there and it is not a decision stream.
            for d in reversed(await _mongo.recent_decisions(50)):
                await self._send(ws, self._frame(d))
        except Exception as e:  # noqa: BLE001
            log.debug("backfill skipped: %s", e)

    def unregister(self, ws: Any) -> None:
        self._clients.discard(ws)

    # -- outbound ---------------------------------------------------------
    @staticmethod
    def _frame(doc: dict) -> dict:
        origin = doc.get("origin", "") or ""
        host = origin.split("//")[-1].split("/")[0] if origin else "local"
        ts = doc.get("ts", 0)
        if hasattr(ts, "timestamp"):
            ts = int(ts.timestamp() * 1000)
        return {
            "type": "decision",
            "ts": ts,
            "decision_id": doc.get("decision_id") or str(doc.get("_id", "")),
            "host": host,
            "modality": doc.get("modality", "text"),
            "chars": doc.get("chars", 0),
            "action": str(doc.get("verdict", "ALLOW")).lower(),
            "label": doc.get("label", "BENIGN"),
            "p_block": doc.get("p_block", 0.0),
            "tier": doc.get("tier", "T1"),
            "latency_ms": doc.get("latency_ms", 0),
        }

    async def _on_decision(self, doc: dict) -> None:
        await self.broadcast(self._frame(doc))

    async def broadcast(self, frame: dict) -> None:
        if not self._clients:
            return
        dead = []
        for ws in list(self._clients):
            try:
                await self._send(ws, frame)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.unregister(ws)

    @staticmethod
    async def _send(ws: Any, frame: dict) -> None:
        # newline-free, one object per frame
        await ws.send_text(json.dumps(frame, separators=(",", ":"), default=str))

    # -- periodic frames ---------------------------------------------------
    async def _ping_loop(self) -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL_S)
            await self.broadcast({"type": "ping"})

    def set_metric(self, key: str, value: float) -> None:
        """A publishes KV-cache utilisation and escalation rate here; B renders the gauges.
        Two models' KV gauges moving on one screen is the unified-memory proof as UI."""
        self._metrics[key] = value

    async def _metric_loop(self) -> None:
        while True:
            await asyncio.sleep(METRIC_INTERVAL_S)
            if self._metrics and self._clients:
                await self.broadcast({"type": "metric", "kv": dict(self._metrics)})

    # -- vLLM /metrics scrape ---------------------------------------------
    async def _scrape_loop(self) -> None:
        """Populate the KV gauges from both vLLM servers (SRS §5.3).

        Closes INTEGRATION-B.md §2: `set_metric()` previously had no caller anywhere in
        the tree, so `{"type":"metric"}` was never broadcast and both gauges read "—" for
        the whole demo. B worked around it by scraping `:8000` and `:8001` from the
        browser; doing it here means one scraper for the whole box instead of one per
        open console tab, and no browser→vLLM traffic at all. B's client stands its own
        scrape down for 6 s whenever a server metric frame arrives, so the two do not fight.

        **Two models' KV gauges moving on one screen is the unified-memory proof rendered
        as UI** — that is what this exists for.

        Read-only GETs with a short timeout. Scrapes only while a console is attached, so
        it costs nothing when nobody is watching. Every failure is silent by design: both
        servers are down for most of the build day and a log line every 2 s would bury
        everything else.
        """
        try:
            import httpx
        except ImportError:
            log.info("httpx unavailable — KV gauges will stay empty")
            return

        async with httpx.AsyncClient(timeout=1.0) as client:
            while True:
                await asyncio.sleep(METRIC_INTERVAL_S)
                if not self._clients:
                    continue  # nobody watching; do not poll the box for nothing

                for key, url in (
                    ("kv_cache_text", TEXT_METRICS),
                    ("kv_cache_vision", VISION_METRICS),
                ):
                    try:
                        r = await client.get(url)
                        if r.status_code != 200:
                            continue
                        m = _KV_RE.search(r.text)
                        if m:
                            self.set_metric(key, round(float(m.group(1)), 4))
                    except Exception:  # noqa: BLE001
                        self._metrics.pop(key, None)  # server went away; drop the stale gauge

                # escalation_rate lives on A's /healthz (the router owns the counters).
                # Surfacing it in the same frame means B reads one source, not two.
                try:
                    r = await client.get(HEALTHZ_URL)
                    if r.status_code == 200:
                        h = r.json()
                        if isinstance(h.get("escalation_rate"), (int, float)):
                            self.set_metric("escalation_rate", round(h["escalation_rate"], 4))
                except Exception:  # noqa: BLE001
                    pass


# --------------------------------------------------------------------------- smoke test
if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    async def main():
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from inspect import mongo as _mongo  # type: ignore

        if not await _mongo.connect():
            print("no mongo — nothing to tail")
            return
        seen = 0

        async def on_event(doc):
            nonlocal seen
            seen += 1
            print(f"[{seen}] {ConsoleHub._frame(doc)}")

        print("tailing decisions — insert a doc to see it here (ctrl-c to stop)")
        await tail_decisions(on_event, coll=_mongo._db["decisions"])

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
