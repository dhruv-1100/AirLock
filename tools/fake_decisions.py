#!/usr/bin/env python3
"""tools/fake_decisions.py — owner C, consumer B. SRS §10 Phase 1 dependency map.

**This file exists so B is never blocked.** B's live console has nothing to display
until A's real router starts writing verdicts. This inserts one plausible decision per
second into `decisions`, so B can build and style the console against a full-looking
stream from 11:00 — hours before the real detector produces traffic.

    python tools/fake_decisions.py                  # 1/sec forever
    python tools/fake_decisions.py --rate 5         # 5/sec
    python tools/fake_decisions.py --burst 900      # 900 rows fast, then exit
    python tools/fake_decisions.py --block-rate 0.4 # more blocks, for screenshotting

The 900-row burst is what B uses for the submission screenshot: "the live console
scrolled through hundreds of ALLOW lines" (SRS §14, three screenshots above the fold).

Writes ONLY to `decisions`. Never to `benign_eval` — that collection is the harness's,
and a burst there would roll the single-node oplog under the console's resume token (R11).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.inspect import mongo as M  # noqa: E402

HOSTS = [
    "https://chatgpt.com",
    "https://claude.ai",
    "https://gemini.google.com",
    "https://copilot.microsoft.com",
    "http://localhost:5173",
]

# (label, clause, severity, tier, reason) — weighted toward what the demo actually shows
BLOCK_KINDS = [
    ("CUSTOMER_RECORD", "POL-004", "HIGH", "T2", "12 rows of name,email,phone,plan,mrr"),
    ("CREDENTIAL", "POL-001", "HIGH", "T1", "provider-prefixed key with high entropy"),
    ("FINANCIAL_NONPUBLIC", "POL-006", "HIGH", "T3", "chart title reads FY26 Revenue Forecast"),
    ("PAYMENT_CARD", "POL-002", "HIGH", "T1", "issuer prefix + Luhn check passed"),
    ("GOV_ID", "POL-003", "HIGH", "T1", "SSN pattern with supporting keyword in context"),
    ("PROPRIETARY_CODE", "POL-007", "MEDIUM", "T2", "internal hostname in a config block"),
    ("HEALTH_RECORD", "POL-005", "HIGH", "T2", "diagnosis alongside a patient identifier"),
    ("LEGAL_HR", "POL-008", "HIGH", "T2", "contract text under an explicit NDA marking"),
]

SPANS = [
    "ana.ruiz@northwind.example,+1-415-555-0142,Pro,4200",
    "sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "Internal — Do Not Distribute",
    "FY26 Revenue Forecast",
    "postgres://svc_billing:••••@db-prod-01.internal:5432/billing",
]


def _decision(rng: random.Random, block_rate: float) -> dict:
    blocked = rng.random() < block_rate
    modality = "image" if rng.random() < 0.12 else "text"
    origin = rng.choice(HOSTS)

    if blocked:
        label, clause, sev, tier, reason = rng.choice(BLOCK_KINDS)
        if modality == "image":
            tier = "T3"
        p_block = round(rng.uniform(0.62, 0.99), 3)
        spans = [rng.choice(SPANS)]
    else:
        label, clause, sev, reason = "BENIGN", "NONE", "NONE", ""
        # Matches the real router's shape: most benign traffic never reaches a model.
        tier = rng.choices(["T0", "T1", "T2", "CACHE"], weights=[22, 58, 14, 6])[0]
        p_block = round(rng.uniform(0.001, 0.28), 3)
        spans = []

    latency = {
        "T0": rng.randint(1, 3),
        "T1": rng.randint(2, 14),
        "T2": rng.randint(190, 580),
        "T3": rng.randint(700, 1900),
        "CACHE": rng.randint(1, 6),
    }[tier]

    chars = rng.randint(40, 3800) if modality == "text" else rng.randint(0, 120)
    return {
        "ts": datetime.now(timezone.utc),
        "payload_sha256": hashlib.sha256(
            f"{time.time_ns()}{rng.random()}".encode()
        ).hexdigest(),
        "origin": origin,
        "modality": modality,
        "verdict": "BLOCK" if blocked else "ALLOW",
        "label": label,
        "clause_id": clause,
        "severity": sev,
        "tier": tier,
        "p_block": p_block,
        "threshold": 0.55,
        "evidence_spans": spans,
        "span_verified": bool(spans),
        "override_reason": None,
        "score_details": (
            {
                "value": round(rng.uniform(0.01, 0.05), 4),
                "description": "reciprocal rank fusion — synthetic, from tools/fake_decisions.py",
                "details": [
                    {"inputPipelineName": "semantic", "rank": 1, "weight": 0.7,
                     "contribution": round(rng.uniform(0.008, 0.012), 5)},
                    {"inputPipelineName": "lexical", "rank": 3, "weight": 0.3,
                     "contribution": round(rng.uniform(0.003, 0.006), 5)},
                ],
            }
            if blocked
            else None
        ),
        "latency_ms": latency,
        "chars": chars,
        "images": 1 if modality == "image" else 0,
        "_synthetic": True,  # so a real run is always distinguishable from demo filler
    }


async def run(rate: float, burst: int, block_rate: float, seed: int) -> int:
    rng = random.Random(seed)
    if not await M.connect():
        print("no mongo — start it with `bash stack/up_mongo.sh` first", file=sys.stderr)
        return 2

    coll = M._db["decisions"]

    if burst:
        docs = [_decision(rng, block_rate) for _ in range(burst)]
        # Backdate the burst so the console's ts-ordered backfill looks like a real day
        # rather than 900 rows sharing one timestamp.
        now = time.time()
        for i, d in enumerate(docs):
            d["ts"] = datetime.fromtimestamp(now - (burst - i) * 1.7, tz=timezone.utc)
        await coll.insert_many(docs)
        n_block = sum(1 for d in docs if d["verdict"] == "BLOCK")
        print(f"inserted {burst} decisions ({n_block} BLOCK, {burst - n_block} ALLOW)")
        return 0

    print(f"streaming ~{rate}/sec into `decisions` (ctrl-c to stop)")
    n = 0
    try:
        while True:
            await coll.insert_one(_decision(rng, block_rate))
            n += 1
            if n % 25 == 0:
                print(f"  {n} decisions written", flush=True)
            await asyncio.sleep(1.0 / rate)
    except KeyboardInterrupt:
        pass
    print(f"\nstopped after {n} decisions")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Synthetic decision stream for B's console.")
    ap.add_argument("--rate", type=float, default=1.0, help="decisions per second")
    ap.add_argument("--burst", type=int, default=0, help="insert N at once and exit")
    ap.add_argument("--block-rate", type=float, default=0.18, help="fraction blocked")
    ap.add_argument("--seed", type=int, default=1337)
    a = ap.parse_args()
    try:
        return asyncio.run(run(a.rate, a.burst, a.block_rate, a.seed))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
