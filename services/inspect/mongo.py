"""services/inspect/mongo.py — owner C. SRS §4.

The persistence and retrieval layer behind A's router. Three hard rules govern this file:

1.  **A's router must never block on Mongo.**  Set ``MONGO_ENABLED=false`` and every call
    here becomes a logged no-op returning a plausible fake ``decision_id``.  A wires
    against this from 10:45 and never waits for C.  It is also the on-stage safety net:
    if Mongo wedges at 19:58, one env var takes it out of the request path entirely and
    the detector keeps working, because T1 and T2 are stateless.

2.  **Never silently allow.**  If Mongo is down or the search index is not queryable,
    clause retrieval degrades to the static ``policy.yaml`` enum — never to an allow.
    A ``$vectorSearch`` against a non-queryable index returns EMPTY RESULTS, NOT AN ERROR
    (R10), so "no clauses" must be treated as "retrieval unavailable", not "nothing matched".

3.  **The server-side ``$rankFusion`` and the client-side RRF emit the identical
    ``score`` / ``scoreDetails`` shape.**  Swapping backends must never touch B's UI.

Environment:
    MONGO_ENABLED   "true" (default) | "false"  → no-op mode
    MONGO_URI       default mongodb://localhost:27017/?directConnection=true
    AIRLOCK_RRF     "server" (default) | "client"  → bypass mongot entirely
    AIRLOCK_KEY_FILE default ./.airlock_key  (0600, never leaves the box)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("airlock.mongo")

# --------------------------------------------------------------------------- config
MONGO_ENABLED = os.getenv("MONGO_ENABLED", "true").lower() not in ("false", "0", "no")
MONGO_URI = os.getenv(
    "MONGO_URI", "mongodb://localhost:27017/?directConnection=true"
)  # directConnection=true is MANDATORY — without it the driver does replica-set
# discovery, gets the container-internal hostname back, and hangs until the
# server-selection timeout. This is the single most common "Mongo is slow" red herring.
DB_NAME = os.getenv("MONGO_DB", "airlock")
RRF_MODE = os.getenv("AIRLOCK_RRF", "server").lower()
KEY_FILE = os.getenv("AIRLOCK_KEY_FILE", ".airlock_key")

TENANT = "acme"
VEC_INDEX = "airlock_vec"
TEXT_INDEX = "airlock_text"

_client: Any = None
_db: Any = None
_key: bytes | None = None


# --------------------------------------------------------------------------- helpers
def sha256_payload(text: str = "", images_b64: list[str] | None = None) -> str:
    """Cache key for the instant-block path. Stable across the text+image tuple."""
    h = hashlib.sha256()
    h.update((text or "").encode("utf-8", "replace"))
    for b in images_b64 or []:
        h.update(b"\x00")
        h.update(b.encode("ascii", "replace"))
    return h.hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fake_id() -> str:
    """A 24-hex string shaped like an ObjectId, so no-op mode is indistinguishable to B."""
    return hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:24]


# --------------------------------------------------------------------------- lifecycle
async def connect(timeout_ms: int = 2000) -> bool:
    """Connect and ping. Returns False rather than raising — Mongo is never fatal."""
    global _client, _db
    if not MONGO_ENABLED:
        log.warning("MONGO_ENABLED=false — persistence is a no-op for this process")
        return False
    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        _client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=timeout_ms)
        await _client.admin.command("ping")
        _db = _client[DB_NAME]
        log.info("mongo connected: %s", MONGO_URI)
        return True
    except Exception as e:  # noqa: BLE001 — deliberately broad, Mongo must never be fatal
        log.error("mongo connect failed (%s) — degrading, detector still runs", e)
        _client = _db = None
        return False


async def healthy() -> bool:
    """For GET /healthz. Any false still returns 200; the extension shows an amber dot."""
    if not MONGO_ENABLED or _db is None:
        return False
    try:
        await _client.admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


def _coll(name: str):
    return None if _db is None else _db[name]


# --------------------------------------------------------------------------- evidence crypto
def _load_key() -> bytes | None:
    """AES-GCM key from a 0600 file that never leaves the box.

    Honest boundary, stated in the submission: Queryable Encryption is the production
    path and is unavailable in Community. This is what we can actually ship today.
    """
    global _key
    if _key is not None:
        return _key
    try:
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, "rb") as f:
                _key = f.read()[:32]
        else:
            _key = os.urandom(32)
            fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(_key)
            log.info("generated new evidence key at %s (0600)", KEY_FILE)
        return _key
    except Exception as e:  # noqa: BLE001
        log.error("evidence key unavailable (%s) — evidence will not be persisted", e)
        return None


def encrypt_evidence(png_bytes: bytes) -> tuple[bytes, bytes] | None:
    """Returns (ciphertext, nonce) or None. Full-resolution originals are NEVER persisted —
    storing the data you just blocked from leaving is indefensible for a DLP product."""
    key = _load_key()
    if key is None or not png_bytes:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        return AESGCM(key).encrypt(nonce, png_bytes, None), nonce
    except Exception as e:  # noqa: BLE001
        log.error("evidence encryption failed: %s", e)
        return None


# --------------------------------------------------------------------------- decisions
async def write_decision(verdict: dict, payload_sha256: str, **extra) -> str:
    """Append one decision. Returns a decision_id, always — even in no-op mode.

    Called by A's router on every verdict. Must never raise and must never block the
    response: on any failure it logs and returns a fake id.
    """
    if not MONGO_ENABLED or _db is None:
        return _fake_id()

    doc = {
        "ts": _now(),
        "payload_sha256": payload_sha256,
        "origin": extra.get("origin", ""),
        "modality": verdict.get("modality", "text"),
        "verdict": str(verdict.get("action", "allow")).upper(),
        "label": verdict.get("label", "BENIGN"),
        "clause_id": verdict.get("policy_clause_id", "NONE"),
        "tier": verdict.get("tier", "T1"),
        "p_block": verdict.get("p_block", 0.0),
        "threshold": verdict.get("threshold", 0.55),
        "evidence_spans": verdict.get("evidence_spans", []),
        "span_verified": verdict.get("evidence_verified", False),
        "override_reason": verdict.get("override"),
        "score_details": verdict.get("score_details"),
        "latency_ms": verdict.get("latency_ms", 0),
        "chars": extra.get("chars", 0),
        "images": extra.get("images", 0),
    }

    png = extra.get("evidence_png")
    if png:
        enc = encrypt_evidence(png)
        if enc:
            from bson import Binary

            # BinData, not GridFS: crops are far under the 16 MB BSON limit, and GridFS
            # would cost two collections, a second round trip, and atomicity — the crop
            # and its verdict could not be written in one operation.
            doc["evidence_png"], doc["evidence_nonce"] = Binary(enc[0]), Binary(enc[1])

    # Encrypted payload text, capped. This exists for exactly one reason: /v1/feedback
    # receives only a decision_id, so write_back_corpus must be able to recover the text
    # it is embedding back into the corpus. Same AES-GCM key as the evidence crop, same
    # 0600 key file. Capped at 8 KB because we are storing it to re-embed it, not to
    # archive it — and a DLP product that hoards full copies of what it blocked has
    # rebuilt the problem it was sold to solve.
    ptext = extra.get("payload_text")
    if ptext:
        enc = encrypt_evidence(ptext[:8192].encode("utf-8", "replace"))
        if enc:
            from bson import Binary

            doc["payload_enc"], doc["payload_enc_nonce"] = Binary(enc[0]), Binary(enc[1])

    try:
        res = await _coll("decisions").insert_one(doc)
        return str(res.inserted_id)
    except Exception as e:  # noqa: BLE001
        log.error("write_decision failed: %s", e)
        return _fake_id()


async def get_by_hash(payload_sha256: str) -> dict | None:
    """Instant-block cache — position zero in A's router. Target ≤5 ms (NFR-L6).

    The semantic-cache pattern applied to security: the second identical paste blocks in
    about a millisecond with no model call at all.
    """
    if not MONGO_ENABLED or _db is None:
        return None
    try:
        return await _coll("decisions").find_one(
            {"payload_sha256": payload_sha256},
            {"evidence_png": 0, "evidence_nonce": 0},
            sort=[("ts", -1)],
        )
    except Exception as e:  # noqa: BLE001
        log.error("get_by_hash failed: %s", e)
        return None


async def recent_decisions(limit: int = 50) -> list[dict]:
    """Console backfill. Never point the console at benign_eval."""
    if not MONGO_ENABLED or _db is None:
        return []
    try:
        cur = _coll("decisions").aggregate(
            [{"$sort": {"ts": -1}}, {"$limit": limit}, {"$project": {"evidence_png": 0}}]
        )
        return [_jsonable(d) async for d in cur]
    except Exception as e:  # noqa: BLE001
        log.error("recent_decisions failed: %s", e)
        return []


def _jsonable(d: dict) -> dict:
    out = dict(d)
    if "_id" in out:
        out["decision_id"] = str(out.pop("_id"))
    if isinstance(out.get("ts"), datetime):
        out["ts"] = int(out["ts"].timestamp() * 1000)
    out.pop("evidence_png", None)
    out.pop("evidence_nonce", None)
    return out


# --------------------------------------------------------------------------- metrics
async def write_metric(
    model: str, modality: str, verdict: str, tier: str, latency_ms: int, **extra
) -> None:
    """Append-only telemetry into the time-series collection. Fire and forget."""
    if not MONGO_ENABLED or _db is None:
        return
    try:
        await _coll("inspect_metrics").insert_one(
            {
                "ts": _now(),
                "meta": {
                    "model": model,
                    "modality": modality,
                    "verdict": verdict,
                    "tier": tier,
                },
                "latency_ms": latency_ms,
                "prefill_tokens": extra.get("prefill_tokens", 0),
                "output_tokens": extra.get("output_tokens", 0),
                "image_px": extra.get("image_px", 0),
            }
        )
    except Exception as e:  # noqa: BLE001
        log.debug("write_metric failed (non-fatal): %s", e)


# --------------------------------------------------------------------------- retrieval
def rrf(ranked_lists: dict[str, list[dict]], weights: dict | None = None, k: int = 60):
    """Client-side reciprocal rank fusion — the mongot fallback.

    Emits the IDENTICAL score / scoreDetails shape as the server-side $rankFusion, so
    swapping the backend never touches B's UI. Verbatim from SRS §4.
    """
    weights = weights or {}
    scores: dict[Any, float] = {}
    docs: dict[Any, dict] = {}
    detail: dict[Any, list] = {}
    for name, ordered in ranked_lists.items():
        w = weights.get(name, 1.0)
        for rank0, doc in enumerate(ordered):
            rank = rank0 + 1
            _id = doc["_id"]
            contrib = w * (1.0 / (k + rank))
            scores[_id] = scores.get(_id, 0.0) + contrib
            docs.setdefault(_id, doc)
            detail.setdefault(_id, []).append(
                {
                    "inputPipelineName": name,
                    "rank": rank,
                    "weight": w,
                    "contribution": contrib,
                }
            )
    out = []
    for _id, s in sorted(scores.items(), key=lambda kv: -kv[1]):
        d = dict(docs[_id])
        d["score"] = s
        d["scoreDetails"] = {
            "value": s,
            "description": (
                "reciprocal rank fusion, client-side, k=60 — score is the weighted sum of "
                "1/(k+rank) across input pipelines"
            ),
            "details": detail[_id],
        }
        out.append(d)
    return out


async def rank_fusion_clauses(
    query_vector: list[float],
    query_text: str,
    modality: str = "text",
    limit: int = 5,
    exact: bool = False,
) -> list[dict]:
    """Hybrid retrieval over policy_corpus. The top-3 clause_ids become the constrained
    enum for the T2 classifier, so **the cited clause cannot be hallucinated**.

    ``exact=True`` forces ENN and is MANDATORY for the FP-rate harness: the corpus is a
    few thousand docs, ENN needs no numCandidates, and the number must be reproducible
    when a judge asks us to re-run it. ANN recall jitter would make the same benign paste
    block on one run and pass on the next.

    Returns [] on any failure. The caller MUST treat [] as "retrieval unavailable →
    fall back to the static policy.yaml enum", never as "nothing matched → allow".
    """
    if not MONGO_ENABLED or _db is None:
        return []

    coll = _coll("policy_corpus")
    vfilter = {"modality": modality, "kind": "exemplar", "tenant": TENANT}

    if RRF_MODE == "server" and not exact:
        try:
            # NOTE: the metadata keys are {$meta:"score"} and {$meta:"scoreDetails"}.
            # One MongoDB docs page shows `searchScoreDetails` in a $rankFusion example —
            # that is the $search-specific key and it SILENTLY RETURNS NOTHING here.
            pipeline = [
                {
                    "$rankFusion": {
                        "input": {
                            "pipelines": {
                                "semantic": [
                                    {
                                        "$vectorSearch": {
                                            "index": VEC_INDEX,
                                            "path": "embedding",
                                            "queryVector": query_vector,
                                            "numCandidates": 200,
                                            "limit": 20,
                                            "filter": vfilter,
                                        }
                                    }
                                ],
                                "lexical": [
                                    {
                                        "$search": {
                                            "index": TEXT_INDEX,
                                            "text": {"query": query_text, "path": "text"},
                                        }
                                    },
                                    {"$limit": 20},
                                ],
                            }
                        },
                        "combination": {"weights": {"semantic": 0.7, "lexical": 0.3}},
                        "scoreDetails": True,
                    }
                },
                {"$limit": limit},
                {
                    "$addFields": {
                        "score": {"$meta": "score"},
                        "scoreDetails": {"$meta": "scoreDetails"},
                    }
                },
                {"$project": {"text": 0, "embedding": 0}},
            ]
            out = [_jsonable(d) async for d in coll.aggregate(pipeline)]
            if out:
                return out
            log.warning("$rankFusion returned 0 docs — check index queryable, not embeddings")
        except Exception as e:  # noqa: BLE001
            log.warning("$rankFusion failed (%s) — falling back to client-side RRF", e)

    # ---- client-side fallback (also the unconditional path for exact=True) ----
    try:
        vs: dict = {
            "index": VEC_INDEX,
            "path": "embedding",
            "queryVector": query_vector,
            "limit": 20,
            "filter": vfilter,
        }
        if exact:
            vs["exact"] = True          # ENN — reproducible, no numCandidates
        else:
            vs["numCandidates"] = 200
        sem = [d async for d in coll.aggregate([{"$vectorSearch": vs}, {"$project": {"embedding": 0}}])]

        lex: list[dict] = []
        if query_text.strip():
            try:
                lex = [
                    d
                    async for d in coll.aggregate(
                        [
                            {"$search": {"index": TEXT_INDEX, "text": {"query": query_text, "path": "text"}}},
                            {"$limit": 20},
                            {"$project": {"embedding": 0}},
                        ]
                    )
                ]
            except Exception:  # noqa: BLE001
                lex = []  # lexical is the optional half; semantic alone still ranks

        fused = rrf({"semantic": sem, "lexical": lex}, {"semantic": 0.7, "lexical": 0.3})
        return [_jsonable(d) for d in fused[:limit]]
    except Exception as e:  # noqa: BLE001
        log.error("clause retrieval unavailable: %s", e)
        return []


# --------------------------------------------------------------------------- write-back
def decrypt_evidence(ct: bytes, nonce: bytes) -> bytes | None:
    key = _load_key()
    if key is None:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        return AESGCM(key).decrypt(bytes(nonce), bytes(ct), None)
    except Exception as e:  # noqa: BLE001
        log.error("evidence decryption failed: %s", e)
        return None


async def write_back_corpus(
    decision_id: str,
    payload: str | None = None,
    embedding: list[float] | None = None,
    analyst: str = "demo",
) -> str | None:
    """Procedural memory — demo beat 4.

    An analyst marks a false positive benign; the payload and its embedding are written
    back into policy_corpus; the next paste of that shape passes, while a near neighbour
    still blocks. **The detector learns without retraining a model.** Live, visible, and
    impossible with a regex.

    `payload` and `embedding` are OPTIONAL and are resolved here when omitted, because
    /v1/inspect's caller (A's app.py) has only a decision_id at feedback time and should
    not need to know anything about embeddings. Called as
    ``await write_back_corpus(decision_id)`` this reads the decision, decrypts its stored
    payload, embeds it on CPU, and writes it back.
    """
    if not MONGO_ENABLED or _db is None:
        return None
    try:
        from bson import ObjectId

        # ---- resolve the payload from the decision when not supplied ----
        if payload is None:
            try:
                oid = ObjectId(decision_id)
            except Exception:  # noqa: BLE001
                log.error("write_back_corpus: %r is not an ObjectId", decision_id)
                return None
            dec = await _coll("decisions").find_one({"_id": oid})
            if not dec:
                log.error("write_back_corpus: decision %s not found", decision_id)
                return None
            if dec.get("payload_enc") and dec.get("payload_enc_nonce"):
                pt = decrypt_evidence(dec["payload_enc"], dec["payload_enc_nonce"])
                payload = pt.decode("utf-8", "replace") if pt else None
            if not payload:
                # Fall back to the verified evidence spans. Weaker — it embeds the
                # offending fragment rather than the whole paste — but it is a real
                # correction rather than a silent no-op, and the analyst sees an effect.
                spans = dec.get("evidence_spans") or []
                payload = " ".join(spans) if spans else None
                if payload:
                    log.warning(
                        "write_back_corpus: no stored payload for %s — falling back to "
                        "evidence spans", decision_id
                    )
            if not payload:
                log.error("write_back_corpus: nothing to embed for %s", decision_id)
                return None

        if embedding is None:
            from . import embed as _embed

            embedding = _embed.encode_one(payload)
    except Exception as e:  # noqa: BLE001
        log.error("write_back_corpus resolve failed: %s", e)
        return None

    try:
        res = await _coll("policy_corpus").insert_one(
            {
                "kind": "exemplar",
                "clause_id": "NONE",
                "class": "benign",
                "tenant": TENANT,
                "modality": "text",
                "severity": "LOW",
                "text": payload,
                "snippet": payload[:200],
                "embedding": embedding,
                "origin": "analyst_override",
                "added_by": analyst,
                "source_decision_id": decision_id,
                "ts": _now(),
            }
        )
        log.info("wrote analyst override back to corpus: %s", res.inserted_id)
        return str(res.inserted_id)
    except Exception as e:  # noqa: BLE001
        log.error("write_back_corpus failed: %s", e)
        return None


# --------------------------------------------------------------------------- harness
async def write_benign_eval(doc: dict) -> None:
    """One doc per benign corpus item. Deliberately a SEPARATE collection from
    `decisions`: a 1000-doc burst would roll the single-node oplog and kill the live
    console's resume token (R11)."""
    if not MONGO_ENABLED or _db is None:
        return
    try:
        await _coll("benign_eval").replace_one({"_id": doc["_id"]}, doc, upsert=True)
    except Exception as e:  # noqa: BLE001
        log.error("write_benign_eval failed: %s", e)


async def fpr_report() -> dict:
    """THE DECIDING ARTIFACT — false-positive rate with a denominator.

    Served straight to GET /v1/report. This aggregation is pasted in full in the
    submission per SRS §14.
    """
    if not MONGO_ENABLED or _db is None:
        return {"n": 0, "false_pos": 0, "fpr": None, "error": "mongo disabled"}
    try:
        cur = _coll("benign_eval").aggregate(
            [
                {
                    "$group": {
                        "_id": None,
                        "n": {"$sum": 1},
                        "false_pos": {
                            "$sum": {"$cond": [{"$eq": ["$verdict", "BLOCK"]}, 1, 0]}
                        },
                        "p50_latency": {
                            "$percentile": {
                                "input": "$latency_ms",
                                "p": [0.50],
                                "method": "approximate",
                            }
                        },
                        "p95_latency": {
                            "$percentile": {
                                "input": "$latency_ms",
                                "p": [0.95],
                                "method": "approximate",
                            }
                        },
                    }
                },
                {
                    "$set": {
                        "fpr": {"$divide": ["$false_pos", "$n"]},
                        "fpr_pct": {
                            "$round": [
                                {
                                    "$multiply": [
                                        {"$divide": ["$false_pos", "$n"]},
                                        100,
                                    ]
                                },
                                2,
                            ]
                        },
                    }
                },
            ]
        )
        rows = [d async for d in cur]
        if not rows:
            return {"n": 0, "false_pos": 0, "fpr": None}
        r = rows[0]
        r.pop("_id", None)
        for k in ("p50_latency", "p95_latency"):
            if isinstance(r.get(k), list) and r[k]:
                r[k] = r[k][0]
        return r
    except Exception as e:  # noqa: BLE001
        log.error("fpr_report failed: %s", e)
        return {"n": 0, "false_pos": 0, "fpr": None, "error": str(e)}


# --------------------------------------------------------------------------- smoke test
if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    async def main():
        connected = await connect()
        print(f"connected={connected}  enabled={MONGO_ENABLED}  rrf={RRF_MODE}")
        h = sha256_payload("hello world")
        did = await write_decision(
            {
                "action": "allow",
                "label": "BENIGN",
                "tier": "T0",
                "p_block": 0.01,
                "latency_ms": 1,
                "modality": "text",
            },
            h,
            chars=11,
        )
        print(f"decision_id={did}")
        print(f"cache hit  ={bool(await get_by_hash(h))}")
        print(f"recent     ={len(await recent_decisions(5))}")
        print(f"report     ={await fpr_report()}")

    asyncio.run(main())
