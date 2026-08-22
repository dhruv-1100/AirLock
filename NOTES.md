# NOTES — cross-owner log (SRS: file it here, never "quickly fix" another owner's surface)

## A → team

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
