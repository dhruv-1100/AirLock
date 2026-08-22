# INTEGRATION-B.md — B's reconciliation against `main`

Written by **B** after merging `origin/main` (A's `DEV_A_VP` + C's `dev_C_DP`) into
`dev_B_RS` and running the client against the real `services/inspect/app.py`.

Companion to C's `INTEGRATION.md`. Same principle: **nothing here requires A or C to
change a file.** All six fixes landed in B's files.

Verified against a live `uvicorn services.inspect.app:app` with `MONGO_ENABLED=false`,
and against the vLLM container already running on `:8000`.

---

## 1. `/v1/decisions` backfill was silently dropping every row

**Severity: high — the console would have been empty on stage with no error anywhere.**

Two sources feed the console and they have different shapes:

| Source | Shape |
|---|---|
| `ws /v1/stream` → `ConsoleHub._frame()` | `{type:"decision", host:"chatgpt.com", action:"block", …}` — normalised |
| `GET /v1/decisions` → `mongo.recent_decisions()` | raw `decisions` documents: `{verdict:"BLOCK", origin:"https://chatgpt.com", …}` — **no `type`, no `host`, no `action`** |

B's `addRow()` opened with `if (d.type !== 'decision') return;`. Every backfill row
failed that test and was dropped without a log line. The live tail worked, so the
symptom would have been "history is missing" — and the first instinct would have been to
go looking at Mongo, which is fine.

**Fixed on B's side.** Both consoles now normalise: `verdict` → `action`, `origin` →
`host`, ISO or epoch `ts`, `_id` → `decision_id`, and a missing `type` is accepted while
`type:"metric"` is still rejected. Regression-tested against both real shapes.

Nothing needs to change in `stream.py` or `mongo.py`.

## 2. Nothing calls `ConsoleHub.set_metric()` — both KV gauges sat at "—"

**Severity: medium — the unified-memory proof rendered as UI was blank.**

`_metric_loop()` is guarded by `if self._metrics`, and `set_metric()` has no callers
anywhere in the tree. So `{"type":"metric"}` never goes out and both gauges show "—" for
the whole demo.

**Fixed on B's side.** `sw.js` and the standalone console now scrape
`http://127.0.0.1:8000/metrics` and `:8001/metrics` directly every 2 s while a console is
open. Read-only GETs over HTTP — B starts, stops and restarts nothing (NFR-S1).

The counter name is `vllm:kv_cache_usage_perc` on the build currently running on this box
(older vLLM called it `vllm:gpu_cache_usage_perc`); the regex accepts both, and was
checked against the live `:8000` output rather than against documentation.

**If A or C later wires `set_metric()` for real, it wins automatically** — a server
metric frame stands the scrape down for 6 s, so the two never fight.

## 3. `results/scores_benign.json` is still the bare-list shape

**Severity: high — this is INTEGRATION.md §3, not yet closed on disk.**

`INTEGRATION.md` §3 says `bench/run_fpr.py` now writes the agreed object. The file
currently committed at `results/scores_benign.json` is still a **bare list** of per-item
dicts from A's smoke run, every row `verdict:"BLOCK"`, `tier:"ERR"`,
`verdict_label:"airlock_unavailable"`, `p_block:1.0` — the harness ran against a service
whose classifier was not up.

Copying that over B's fixture would have shown FPR "—" (list has no `.benign`), or worse,
**100% FPR from 20 harness errors** once the shape was fixed.

**Fixed on B's side, defensively.** The loader now accepts all three shapes — `{benign:[…]}`,
`{items:[…]}`, and the bare list — mirroring what C did for `report.py`. Rows with
`tier:"ERR"` or `verdict_label:"airlock_unavailable"` are **excluded from the denominator
and counted separately**, and the count is displayed. A fail-closed BLOCK is not a
classifier decision and must never be reported as a false positive.

Both consoles refuse to drop the placeholder warning until they see
`corpus_is_real: true`. **The number on screen stays labelled PLACEHOLDER until the real
harness run lands.**

## 4. `/healthz` `mongo` and `/v1/decisions` `mongo` disagree

**Severity: low, but it points the wrong way.**

`app.py` sets `"mongo": _HAVE_MONGO`, which is *did the module import*. `console_api.py`
returns `"mongo": await M.healthy()`, which is *is it connected*. With
`MONGO_ENABLED=false` the first says `true` while the second says `false` — so the console
dot read green while there was no persistence at all.

**Fixed on B's side.** Both consoles prefer the `/v1/decisions` value when they have it,
and hold it as a flag so the 5 s `/healthz` tick does not overwrite it.

## 5. `/v1/answer` error frames were being swallowed

`app.py` yields an `airlock.error.v1` object inside a `data:` frame when `:8000` is
unreachable — no `choices` key. B's SSE parser skipped it as unparseable and then hit
`[DONE]`, so the answer panel stopped mid-sentence with nothing said. **Fixed:** an
`error` key is surfaced into the panel as text.

## 6. "Mark benign" claimed a write-back that had not happened

`/v1/feedback` returns `{ok:true, corpus_id:"stub_…", embedded:false}` on the no-Mongo
path. B's card said *"Written back to policy_corpus as an analyst override"* regardless —
a false claim on the one beat whose entire point is that the write-back is real.

**Fixed:** `embedded:false` now renders in amber as *"Override recorded, but NOT embedded
— nothing was written to policy_corpus."*

---

## Not a bug, checked and confirmed

`POST /v1/inspect` with `4242424242424242` returns `503 airlock_unavailable` rather than a
`PAYMENT_CARD` block. That is **correct**: it is Stripe's published test PAN and A's
`t1.scan()` excludes it by design (SRS §6.2), so the payload escalates to T2, the
classifier is not up, and the router fails closed. `4111111111111111` blocks at T1 with
`confidence:"HIGH"` as specified. A's detector is behaving to spec — do not "fix" this.

## Still open, owned elsewhere

- `set_metric()` has no caller. B is scraping instead, so this is no longer blocking, but
  the escalation-rate figure in the console still has no source and shows "—".
- `results/scores_benign.json` needs one real harness run against a live classifier
  before any FPR number is quoted anywhere. Both consoles will keep saying PLACEHOLDER
  until then, deliberately.
