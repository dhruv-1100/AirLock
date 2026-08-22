# NOTES — cross-owner log (SRS: file it here, never "quickly fix" another owner's surface)

## A → team

- **INTEGRATION.md §9 fixed (C's find, thank you):** `STRIPE_TEST_PANS` was
  missing `4000000000000077` and `...93`. Widened to 26 published cards
  (all Luhn-checked), and `tests/test_t1.py` now probes **every** entry plus
  cross-checks C's independent corpus list — no sampling, so this class of gap
  cannot recur silently. Verified: `bench/t1_offline.py` → **0/1000 T1-HIGH
  false positives** on the real benign corpus, 8.1% MEDIUM escalation.
- **`4111111111111111` now excluded** — B confirmed nothing depends on it
  blocking (no PAN appears in any B-owned file) and corrected the record: the
  INTEGRATION-B line was an experimental control, not a judgement. Verified
  live: it escalates to T2 instead of auto-blocking at T1-HIGH.
- **`tier_timings` shipped** in the verdict body, exactly the requested shape.
  Skipped stages are **absent**, never 0/null. Verified:
  `T0 → {CACHE:0.04, T0:0.01}` · `T1 → {CACHE, T0, T1}` · `CACHE replay →
  {CACHE}`. **One rendering note for B:** a stage that ran in under 10 µs
  serialises as `0.0` (it *did* run — presence means ran). Suggest rendering
  sub-0.01 as `<0.01 ms` rather than `0` so it doesn't read as skipped.
- **`extracted_text` shipped** on image verdicts (level 2 of B's ladder) — the
  VLM's verbatim transcript now reaches the client instead of staying
  server-side. **No `evidence_boxes`:** the T3 schema has no coordinates and I
  agree with B — a confidently-wrong box is fabricated evidence, which is the
  exact failure this product exists to prevent. If we ever add them they will
  be normalised 0–1 per B's note (the client downscales to 1024px, so pixel
  coords are wrong by the downscale ratio), and only after measuring whether
  Omni grounds text reliably. Not before the demo.
- C's multilingual-corpus point is fair and stands as a stated limitation: the
  T2 prompt is English. If the FP list skews non-English, that is the reason.

- **Path/name split fixed (INTEGRATION-B):** launch scripts now read
  `AIRLOCK_*_MODEL_PATH` (weights path) and auto-source `stack/models.env`;
  the service reads `AIRLOCK_*_MODEL` (request name, defaults
  `airlock-text|vision|clf`). The two jobs can no longer share a variable.
- **Memory budget re-cut for the pre-staged weights:** vision (Omni 30B,
  21 GB BF16) goes 0.24 → **0.28**; two-server demo total **0.68**
  (text 0.40 + vision 0.28, T2 on :8000). `launch_clf.sh` now refuses to run
  without an explicit `AIRLOCK_CLF_UTIL` — a second Lightning copy breaches
  the 0.85 ceiling.
- **Embed model — A concurs with B's models.env analysis:** keep bge-small on
  CPU. 2048-d vs the 384-d index means a rebuild we cannot afford (empty
  results, not errors, on a non-READY index), and NFR-S10 prohibits a third
  GPU process for embeddings. Not wiring it.
- `make_synthetic_scores.py` takes `--out`; the test writes to tmp — the team
  `results/scores_benign.json` (n=1000) can no longer be clobbered at n=50.
- **af-vllm 500 `EngineCore encountered an issue`** on chat completions: that
  container is mine to debug on the box — likely flags/backend, not client.

- **Day-of bring-up is now scripted** (all A-owned, NFR-S1 — B/C never run these):
  `stack/preflight.sh` (G0 driver gate + NFR-S2 ritual, blocks if mongo heap
  unverified) → `stack/launch_text.sh` (0.40) → `stack/launch_vision.sh` (0.24)
  → `stack/launch_clf.sh` (0.09) → `stack/warm.sh` (compile warm-up, re-run at
  16:30) → `python stack/day_probes.py` (tokenizer distinctness + guided-JSON
  spelling — record the winner below). `stack/memwatch.sh` runs in its own
  terminal all day (NFR-S13 watchdog).
- Set `AIRLOCK_TEXT_MODEL` to the pre-staged 35B NVFP4 weights path before
  `launch_text.sh` — the script refuses to guess it.

- `services/inspect` scaffold is up: `/healthz`, `OPTIONS`, `POST /v1/inspect`
  with the full CACHE → T0 → T1-HIGH → T2 router, span verification, and
  `p_block` from first-label-token logprobs (T=1.0 until Phase 3 calibration).
- **B:** kill `tools/stub_inspect.py` the moment `:8787` binds on the box —
  same port, same `airlock.verdict.v1` contract, nothing else changes.
- **VERIFY-ON-THE-DAY (10:45 gate):** which guided-JSON spelling the pinned
  vLLM accepts. `tiers/t2.py` tries, in order:
  1. `response_format={"type":"json_schema",...}`
  2. `extra_body={"structured_outputs":{"json":SCHEMA}}`
  3. `extra_body={"guided_json":SCHEMA}`
  and caches the winner. Record the winning spelling here: __________
- **VERIFY-ON-THE-DAY:** all nine labels first-token-distinct in the Qwen3-4B
  tokenizer (fallback: digit-prefixed labels, see `calib.py`).
- Classifier URL defaults to `http://127.0.0.1:8002/v1` (`AIRLOCK_CLF_URL`
  env to override; route to `:8000` if airlock-clf won't fit — costs latency,
  costs no memory).
- Mongo-backed CACHE/decision-writes hook in when C lands
  `services/inspect/mongo.py`; until then the cache is in-process and
  `/healthz` reports `mongo:false`.
