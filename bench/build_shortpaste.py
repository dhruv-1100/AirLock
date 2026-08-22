#!/usr/bin/env python3
"""bench/build_shortpaste.py — owner C.

Builds `data/shortpaste_v1.jsonl` — short benign pastes that exercise the **T0 fast path**.

    python bench/build_shortpaste.py --seed 1337

================================ WHY THIS EXISTS ================================
`data/benign_v1.jsonl` has a 200-character floor. T0's gate is `len < 40`. So T0
**cannot fire on the main corpus by construction** — measured on the box: 0 of 1000
items resolved at T0, and 100% escalated to T2.

Two consequences, and they pull in opposite directions:

  · GOOD for the headline. Every item reached the language model, so the false-positive
    rate is measured entirely on the hard subset with no fast-path trivia diluting it.
    That makes the FPR conservative.

  · BAD for throughput. Escalation rate, blended latency (NFR-L8) and seats-per-box
    (NFR-T7) all assume ~14% of pastes reach a model. Measured on that corpus they are
    not representative of any real paste distribution.

This set closes the second gap honestly: it demonstrates the T0 path **works**, rather
than us reporting a fast path we never exercised. It is reported as its **own line**,
never merged into the n=1000 denominator.
=================================================================================

**This is a FUNCTIONAL PROBE, not a second FPR.** The claim it supports is "T0 resolves
trivial pastes correctly and in under a millisecond", not "here is our false-positive
rate on short text". n is small and the items are simple by design — that is the point,
not a limitation being hidden.

Provenance: prefers real short first-turns pulled from WildChat; falls back to a
hand-authored set, stamped `authored: true` so the distinction is never lost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

MAX_CHARS = 39          # T0 fires strictly below 40
T0_FORBIDDEN = set("@:/=")

# Hand-authored fallback. Deliberately the shape of real short pastes: a question
# fragment, a lookup, a "what does X mean". Every one must satisfy T0's gate —
# len<40, no digit, none of @ : / = — which is asserted below, not assumed.
AUTHORED = [
    "what is a monad",
    "explain tail recursion",
    "difference between a set and a list",
    "how does quicksort work",
    "what does idempotent mean",
    "why use a message queue",
    "explain eventual consistency",
    "what is a race condition",
    "define cardinality",
    "how do generics work",
    "what is currying",
    "explain lazy evaluation",
    "when to use a linked list",
    "what is a memory barrier",
    "explain copy on write",
    "what does immutable mean",
    "how does garbage collection work",
    "what is a pure function",
    "explain the actor model",
    "what is backpressure",
    "define referential transparency",
    "how does hashing work",
    "what is a deadlock",
    "explain optimistic locking",
    "what is a bloom filter",
    "how does paging work",
    "what is a semaphore",
    "explain write amplification",
    "what does atomic mean here",
    "how do coroutines differ",
    "what is a trie used for",
    "explain branch prediction",
    "why is my build slow",
    "what is a flaky test",
    "explain blue green deploys",
    "what does idempotency buy me",
    "how does rate limiting work",
    "what is a circuit breaker",
    "explain the thundering herd",
    "what is cache invalidation",
]


def _t0_eligible(t: str) -> bool:
    """The exact T0 gate from SRS §6.4: len<40, no digit, none of {@ : / =}."""
    return len(t) < 40 and not any(c.isdigit() for c in t) and not (set(t) & T0_FORBIDDEN)


def _from_wildchat(n: int) -> list[tuple[str, str]]:
    """Real short first-turns. Needs `datasets` and network; silently returns [] if not."""
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        return []
    ds = None
    try:
        ds = load_dataset("allenai/WildChat-1M", split="train", streaming=True)
        out: list[tuple[str, str]] = []
        for i, row in enumerate(ds):
            if row.get("toxic") is True or row.get("redacted") is True:
                continue
            conv = row.get("conversation") or []
            text = ""
            for turn in conv if isinstance(conv, list) else []:
                if isinstance(turn, dict) and turn.get("role") == "user":
                    text = (turn.get("content") or "").strip()
                    break
            text = " ".join(text.split())
            if text and _t0_eligible(text):
                out.append((f"wildchat_short:{row.get('conversation_hash', i)}", text))
            if len(out) >= n or i > 200_000:
                break
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  ! WildChat short-turn pull failed ({e})", file=sys.stderr)
        return []
    finally:
        del ds


def build(seed: int, out_path: Path, n: int) -> int:
    real = _from_wildchat(n)
    if real:
        print(f"  · {len(real)} real short first-turns from WildChat-1M")
        items = [(rid, t, False) for rid, t in real]
        source, license_, url = (
            "WildChat-1M", "ODC-BY",
            "https://huggingface.co/datasets/allenai/WildChat-1M",
        )
    else:
        print("  ! no real short turns available — using the hand-authored probe set")
        print("    (stamped authored:true; this is a FUNCTIONAL PROBE, not an FPR)")
        items = [(f"authored:{i}", t, True) for i, t in enumerate(AUTHORED)]
        source, license_, url = ("hand-authored", "n/a — written by us", "")

    # Assert the gate rather than trusting it. A probe set that does not actually reach
    # T0 would silently measure nothing and we would report a working fast path anyway.
    bad = [t for _, t, _ in items if not _t0_eligible(t)]
    if bad:
        print(f"\nFATAL: {len(bad)} item(s) do not satisfy the T0 gate, e.g. {bad[0]!r}",
              file=sys.stderr)
        print("  A probe set that cannot reach T0 measures nothing.", file=sys.stderr)
        return 2

    records = [
        {
            "_id": rid,
            "source": source,
            "license": license_,
            "provenance_url": url,
            "sha256": hashlib.sha256(t.encode()).hexdigest(),
            "char_len": len(t),
            "label": "BENIGN",
            "text": t,
            "authored": authored,
            "expected_tier": "T0",
        }
        for rid, t, authored in items
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest = {
        "corpus": out_path.name,
        "version": "shortpaste_v1",
        "n": len(records),
        "purpose": "functional probe of the T0 fast path — NOT a second FPR denominator",
        "all_authored": all(r["authored"] for r in records),
        "source": source,
        "license": license_,
        "max_chars": MAX_CHARS,
        "t0_gate": "len < 40 and no digit and none of {@ : / =}",
        "reproduce": f"python bench/build_shortpaste.py --seed {seed}",
        "why": (
            "benign_v1 has a 200-char floor, so T0 cannot fire on it: measured 0/1000 "
            "resolved at T0 and 100% escalated to T2. This set demonstrates the fast "
            "path works rather than reporting one we never exercised. Report it as its "
            "own line; never merge it into the n=1000 denominator."
        ),
    }
    out_path.with_name(out_path.stem + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"\nwrote {len(records)} records → {out_path}")
    print(f"  all satisfy the T0 gate  ✓")
    print(f"  authored: {manifest['all_authored']}")
    print("\nRun against the service, then report SEPARATELY:")
    print(f"  python bench/run_fpr.py --benign {out_path} --n {len(records)} --no-mongo")
    print("Expect: tier=T0 on every item, latency ~1 ms, zero blocks.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the T0 short-paste probe set.")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--out", type=Path, default=Path("data/shortpaste_v1.jsonl"))
    a = ap.parse_args()
    return build(a.seed, a.out, a.n)


if __name__ == "__main__":
    sys.exit(main())
