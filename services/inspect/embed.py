"""services/inspect/embed.py — owner C.

One shared CPU embedder for bge-small-en-v1.5 (384-d), used by `mongo.write_back_corpus`
and `bench/seed_corpus.py`. Kept in one place so the corpus and the write-back path can
never drift onto different models — a write-back embedded by a different model than the
corpus lands in the wrong region of the space and the "detector learns" beat silently
does nothing.

**NFR-S10 — CPU only. This is not, and must never become, a GPU process.**
bge-small is 67 MB fp16 and runs on the 20 Arm cores via ONNX Runtime. A third vLLM
process would cost a CUDA context (~300–500 MB), its own compile warm-up and SM time.
Grace does retrieval; Blackwell does inference. Only A may start a GPU process anyway
(NFR-S1), so anything here touching CUDA is a bug by definition.
"""

from __future__ import annotations

import hashlib
import logging
import math

log = logging.getLogger("airlock.embed")

EMBED_DIM = 384
MODEL_ID = "BAAI/bge-small-en-v1.5"

_impl = None
_backend = "uninitialised"


def _init() -> None:
    global _impl, _backend
    if _impl is not None or _backend == "hash":
        return
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _impl = SentenceTransformer(MODEL_ID, device="cpu")
        _backend = "sentence-transformers(cpu)"
    except Exception:  # noqa: BLE001
        _backend = "hash"
        log.warning(
            "no embedding model available — using a deterministic hash embedding. "
            "Retrieval will run but semantic recall is meaningless. "
            "Install with: pip install sentence-transformers  (CPU only)"
        )
    log.info("embedder backend: %s", _backend)


def backend() -> str:
    _init()
    return _backend


def encode(texts: list[str]) -> list[list[float]]:
    """Returns unit-normalised 384-d vectors.

    Normalisation is not optional: the index is cosine and MongoDB does not normalise
    for you.
    """
    _init()
    if _impl is not None:
        return [
            v.tolist() for v in _impl.encode(texts, normalize_embeddings=True, batch_size=32)
        ]
    return [_hash_embed(t) for t in texts]


def encode_one(text: str) -> list[float]:
    return encode([text])[0]


def _hash_embed(text: str) -> list[float]:
    """Deterministic bag-of-words fallback. Exercises the retrieval plumbing end to end
    without pretending to be semantic."""
    vec = [0.0] * EMBED_DIM
    for tok in text.lower().split():
        h = int(hashlib.sha256(tok.encode()).hexdigest()[:16], 16)
        vec[h % EMBED_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
