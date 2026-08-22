# NOTES — cross-owner log (SRS: file it here, never "quickly fix" another owner's surface)

## A → team

- **INTEGRATION.md §9 fixed (C's find, thank you):** `STRIPE_TEST_PANS` was
  missing `4000000000000077` and `...93`. Widened to 26 published cards
  (all Luhn-checked), and `tests/test_t1.py` now probes **every** entry plus
  cross-checks C's independent corpus list — no sampling, so this class of gap
  cannot recur silently. Verified: `bench/t1_offline.py` → **0/1000 T1-HIGH
  false positives** on the real benign corpus, 8.1% MEDIUM escalation.
- **One PAN left blocking on purpose — team call needed:** `4111111111111111`
  is widely published, but B verified it blocking at T1-HIGH "as specified"
  and may use it as a demo payload. Excluding it is a behaviour change across
  owners, so I flagged rather than made it. **B: do you rely on it? If not,
  I'll exclude it — a judge pasting the most famous test card in existence and
  getting a block is a live FP risk on stage.**
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
