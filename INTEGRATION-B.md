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
classifier is not up, and the router fails closed.

> **Correction, added later — this paragraph was misread as a sign-off and it was not
> one.** It originally ended by noting that `4111111111111111` blocks at T1 with
> `confidence:"HIGH"` "as specified". That sentence existed only as the *contrast* that
> proved the `4242…` exclusion was firing — it was a control in an experiment about
> `4242…`, not a judgement about `4111…`. A read it as B having signed off on `4111…`
> blocking and left the behaviour alone on that basis (`t1.py:53`, `NOTES.md:11`).
>
> **B does not rely on `4111111111111111` anywhere** — not in a demo payload, not in a
> fixture, not in a test. It should be excluded. See §14.

---

# Round 2 — after A's `71081bf`

A closed both of the items that were open above: `write_metric()` now has a caller in
`_finish()`, and `escalation_rate` + a `tiers` breakdown are exposed on `/healthz`.

## 8. The console read `escalation_rate` from the wrong place — fixed on B's side

A publishes it on `/healthz`. B's consoles were only looking for it inside a
`{"type":"metric"}` WebSocket frame, which nothing broadcasts — so the figure stayed "—"
even though the server had it. **Fixed:** both consoles now read `escalation_rate` (and
the `tiers` breakdown, as a tooltip) off the health poll, and the in-page console
re-polls every 5 s so the number moves as pastes come in rather than freezing at boot.

## 9. `escalation_rate` reads 0% while every paste is escalating — A's call

**Severity: low on stage, confusing during bring-up.**

`_tier_counts` is incremented in `_finish()`. The fail-closed path returns `_err(...)`
directly and never reaches `_finish()`, so a paste that escalates to a T2 that is not up
is not counted at all. Observed on the merged tree with the classifier down:

```
5 pastes: 2 resolved (T0, T1), 3 escalated and 503'd
/healthz  ->  tiers {"T0":1,"T1":1}   escalation_rate 0.0
```

Defensible either way — a 503 is not a completed decision — but during bring-up the
console will read **0% escalation while three of five pastes escalated**, which is the
opposite of the signal you want when you are trying to work out whether the classifier is
being reached. If A wants it counted, the increment belongs before the error return as
well as in `_finish()`. **Flagged, not patched: `app.py` is A's file.**

B's console renders whatever `/healthz` says and carries the tier breakdown in the
tooltip, so the discrepancy is at least visible rather than silent.

---

# Round 3 — after C's `6737dcf`

## §2 is closed server-side, and B's scrape stays as the fallback

C implemented `ConsoleHub._scrape_loop()`: one scraper for the box polling `:8000` and
`:8001` every 2 s while a console is attached, plus `escalation_rate` read off `/healthz`
and folded into the same frame. That is strictly better than B scraping once per open
console tab, and it removes browser→vLLM traffic entirely.

**Verified on the merged tree**, with the live vLLM on `:8000` and nothing on `:8001`:

```
hello
metric {"kv_cache_text": 0.0, "escalation_rate": 0.0}      <- server frame, 2 s cadence
metric {"kv_cache_text": 0.0, "escalation_rate": 0.0}
```

`kv_cache_vision` is correctly absent rather than stale — C drops the key when a server
goes away. In the browser: gauges paint from the server frame, `kvV` shows "—", and the
client-side scrape stands down (last server frame 881 ms ago, well inside the 6 s
window). The handoff works in both directions with no configuration.

**B is keeping the client-side scrape**, unchanged, as the fallback C offered:

- the standalone console at `:5174` is meant to survive the gateway being restarted, and
  during a restart the server-side scraper is gone while `:8000` is still up;
- it is also what makes the console work against `tools/stub_inspect.py`, which has no
  scrape loop of its own.

It costs one `setInterval` that returns immediately whenever server frames are arriving,
which is the normal case. Nothing to tune.

## Housekeeping

`.DS_Store` was committed in `3aca041`. Removed from tracking and added to `.gitignore`
(`.gitignore` is the one file the merge policy calls a union, so this is not a
cross-ownership edit).

---

# Round 4 — after A's `a1cffb2`

A fixed both findings B raised. Both verified on the merged tree.

## §9 escalation undercount — closed

`ERR` is now counted as an escalation and incremented before the error return. Same
scenario B originally reported (5 pastes, 3 escalating to a classifier that is down):

```
before:  tiers {"T0":1,"T1":1}            escalation_rate 0.0    <- 0% while 60% escalated
after:   tiers {"T0":1,"T1":1,"ERR":3}    escalation_rate 0.6
```

The console renders 60% with `T0:1  T1:1  ERR:3` in the tooltip.

## Perfectly-separated slider — fixed, but the committed artifact was stale

A reshaped `make_synthetic_scores.py` so ~2% of benign items land in 0.30–0.80 and ~8%
of sensitive items score low, giving the slider something to trade. Correct fix.

The file committed alongside it was still generated at **n=50 / 20**, though, and at that
size a 2% near-threshold band yields **zero** benign items in range — top benign score
0.178, so FPR read 0.00% at every τ from 0.20 to 0.75. Recall moved; FPR did not. Half
the slider was still inert.

**Regenerated at the script's own documented defaults** (`--n 1000 --n-sensitive 400
--seed 1337`, no arguments needed) and copied into both consoles. `INTEGRATION.md` calls
`results/scores_benign.json` a regenerate-don't-merge artifact, so this is that, using
A's script unmodified:

```
tau=0.20  FPR=4.70% (47/1000)  recall=97.5%
tau=0.30  FPR=2.60% (26/1000)  recall=95.3%
tau=0.42  FPR=1.40% (14/1000)  recall=92.8%
tau=0.55  FPR=0.80% ( 8/1000)  recall=89.0%
tau=0.75  FPR=0.20% ( 2/1000)  recall=76.3%
```

n=1000 is also the denominator the SRS requires for a reportable FPR, so the placeholder
now rehearses the real thing at the real size. It still self-declares
`corpus_is_real: false` and both consoles still show the PLACEHOLDER label — **these are
demo-shaped numbers, not measurements, and nothing may quote them.**

---

# Round 5 — the pre-staged weights in `gb10/`

70 GB landed on the box. `gb10/` is in `.gitignore` — those are inputs to the run, not
artifacts of it, and one safetensors shard exceeds GitHub's hard file limit.

Mapping, in `stack/models.env` (source it; it sets only variables A's launch scripts and
tier modules already read — no launch flag, no tier logic, no GPU process touched):

| on disk | what it is | role |
|---|---|---|
| `models/lightning` 21 G | Nemotron-3.5-Lightning-30B-A3B-**NVFP4**, `NemotronHForCausalLM`, MoE | `airlock-text` :8000 — replaces Qwen3.6-35B-A3B-NVFP4 |
| `models/omni` 21 G | Nemotron-3-Nano-Omni-30B-A3B-Reasoning, **BF16**, multimodal | `airlock-vision` :8001 — replaces Holo1.5-7B |
| `models/embed` 997 M | Nemotron-3-Embed-1B, NVFP4, **2048-d** | **not wired in** — see §12 |
| `models/parakeet` 2.4 G | `ParakeetForTDT`, speech-to-text | no role — nothing in the SRS ingests audio |

## 10. One env var is doing two incompatible jobs — A's call

`AIRLOCK_TEXT_MODEL` is read by `launch_text.sh` as the **weights path** and by
`app.py:371` as the **request model name**. They cannot both be right: the launch script
passes `--served-model-name airlock-text`, and vLLM answers only to the served name.
Verified against the live `:8000` on the box:

```
{"model":"/models/lightning"}
  -> 404 {"message":"The model `/models/lightning` does not exist.",
          "type":"NotFoundError"}
```

So setting `AIRLOCK_TEXT_MODEL` to the path — which `launch_text.sh` demands, with a
`:?` that refuses to start without it — breaks `/v1/answer` with a 404 that reads exactly
like the model server being down. Same collision on `AIRLOCK_VLM_MODEL` and
`AIRLOCK_CLF_MODEL`.

`models.env` works around it by splitting the two into separate blocks
(`AIRLOCK_*_MODEL_PATH` for the launch shell, `AIRLOCK_*_MODEL` for the service shell).
**The real fix is one line in each of A's three launch scripts** — read
`AIRLOCK_TEXT_MODEL_PATH` rather than `AIRLOCK_TEXT_MODEL`. Flagged, not patched:
`stack/launch_*.sh` and `app.py` are A's files.

## 11. The memory budget no longer matches the weights — A's call

SRS §7.3 sized the pool against Qwen3.6-35B-A3B-NVFP4 at 0.40 and **Holo1.5-7B** at 0.24.
The vision model is now a **30B BF16** multimodal, not a 7B. 21 GB of weights on disk
against a 0.24 ≈ 31 GB budget leaves very little for KV, multimodal caches and graphs,
and NFR-S3 caps the summed utilisation at 0.85 with 0.64 committed.

Not B's arithmetic to redo, and not something to discover at launch. **A should re-cut
§7.3 against the actual weights before the first `launch_vision.sh`**, and the whiteboard
total needs to reflect whatever comes out of that.

Separately: the running `af-vllm` container currently answers `/v1/models` with `omni`
and returns a 500 `EngineCore encountered an issue` on a chat completion. Presumably A
mid-debug — noting it so it is not mistaken for a client problem.

## 12. `models/embed` should stay unwired — C's call, but the reasons are hard

Nemotron-3-Embed-1B is a better retrieval model than bge-small. It is still wrong here:

1. **It is 2048-d.** `stack/seed.js:109` declares `numDimensions: 384` and
   `services/inspect/embed.py:24` hard-codes `EMBED_DIM = 384`. Swapping means dropping
   and rebuilding `airlock_vec` and re-embedding every exemplar — and a `$vectorSearch`
   against a non-READY index returns **empty results, not an error**, which presents as a
   dead detector. SRS §4 says a late index rebuild is not affordable.
2. **It is an NVFP4 GPU model.** NFR-S10 prohibits a third GPU process for embeddings;
   the architecture line is "Grace does retrieval, Blackwell does inference".

If the team wants it, it is a seed-time change and has to land **before** `policy_corpus`
is populated, not after.

## 13. CFPB is recoverable — C's call

`data/ATTRIBUTION.md` records CFPB as 0 of 120, method `unavailable`, which is why
`benign_v1` is five sources rather than the six the SRS specifies.
**`gb10/data/cfpb_narratives.csv` is on the box.** Pointing `bench/build_benign.py` at it
restores the sixth source and the intended mix.

## Fixed on B's side

`tools/stub_inspect.py` reported `airlock-clf/qwen3-4b` and `airlock-vision/holo1.5-7b`.
The block card renders `model` verbatim on the receipt, so the stub was naming weights we
do not have. Now `nemotron-3.5-lightning-30b` and `nemotron-3-nano-omni-30b`.

---

# Round 6 — answers to A's three questions

## 14. `4111111111111111` — **exclude it.** B does not rely on it.

Searched every B-owned file: `extension/**`, `web/**`, `tools/fixtures/**`,
`tools/harness/**`, `tools/stub_inspect.py`, and the demo payloads. **No PAN appears in
any of them at all.** The only occurrences of `4111111111111111` in the whole tree are
`t1.py:53`, `NOTES.md:11` and one prose line in this file.

**That prose line was misread as a sign-off, and the record is now corrected above.** It
read "`4111111111111111` blocks at T1 with `confidence:"HIGH"` as specified" — but that
sentence was the *control* in an experiment about `4242424242424242`. B was checking that
the Stripe exclusion fired on `4242…`, and cited `4111…` blocking as the contrast that
proved the exclusion was doing something. It was never a judgement that `4111…` *should*
block, and `t1.py:53` should not be carrying B's name as the reason it still does.

A's own reasoning is right and B agrees with all of it: it is the most widely published
test card in existence, T1-HIGH means no model call can rescue it, and it lands straight
in the reported FPR. A judge pasting it into an integration test is not an edge case,
it is the first thing anyone would try.

Checked before answering, so the exclusion cannot silently cost recall:
`bench/build_sensitive.py` builds its PAYMENT_CARD carriers from its own
`STRIPE_TEST_PANS` list, and `tests/test_t1.py:LIVE_SHAPED_PANS` uses `4556737586899855`
and `5425233430109903` — deliberately not Stripe cards. Nothing anywhere depends on
`4111…` blocking.

**Go ahead with the one-line exclusion.**

## 15. `tier_timings` — **yes. Already built against it; ship the field.**

Renders as a five-cell cascade strip in the block card, above the `scoreDetails` tree.
Verified in the harness at both `#cascade` and `#no-model`:

```
no model called:  CACHE 0.40ms[ran]  T0 0.01ms[ran]  T1 0.31ms[RESOLVED]  T2 not run  T3 not run
                  "No model was called. Resolved deterministically at T1 on CPU —
                   no GPU, no tokens, nothing queued behind another request."

escalated:        CACHE 0.40ms[ran]  T0 0.01ms[ran]  T1 0.42ms[ran]  T2 312ms[MODEL]  T3 not run
                  "Escalated to the text model — the deterministic tiers could not
                   resolve this one."
```

A is right that this is the invisible claim. The stage that *did not run* is the whole
argument, and a dimmed T2 next to a lit T1 makes it without anyone narrating it.

Exactly the shape proposed — `{"cache":0.4,"T0":0.01,"T1":0.3,"T2":312}` — works as-is:

- keys are matched case-sensitively against `cache`, `T0`, `T1`, `T2`, `T3`; anything
  else is ignored rather than breaking the strip;
- a key **present** means the stage ran, **absent** means it did not. Please omit skipped
  stages rather than sending `0` or `null` — `"T2": 0` would light T2 up as having run in
  no time, which is the opposite of the point;
- the deciding stage is taken from the existing `tier` field, not inferred from the
  timings, so `tier:"CACHE"` colours the cache cell green with no extra work;
- milliseconds as floats. Sub-10ms renders to 2 decimals so `0.01` stays visible.

**The renderer is already tolerant of the field being absent** — no cascade block is
emitted at all, verified. So ship it whenever; nothing on B's side needs to land first.

## 16. Image transcription overlay — **yes, and it is built. But boxes need coordinates.**

This is the right instinct and it is the image analogue of the evidence underline. One
hard constraint: **the T3 schema returns strings only.** `t3.py:33-47` requires
`image_type`, `extracted_text`, `org_markers`, `temporal_markers`,
`confidentiality_markers` — no coordinates anywhere. And `extracted_text` never reaches
the client: `app.py:291-306` folds the markers into `reason` and `evidence_spans`, and
`ocr_text` stays server-side.

So "boxed where they appear" cannot be done truthfully today. B will not draw a box at a
guessed position — inventing a location for a marker is fabricating evidence, which is
the exact failure this product exists to prevent.

Built instead: **one renderer, three fidelity levels, picked automatically by what the
verdict carries.** All three verified in the harness (`#image`, `#image-ocr`, `#image-box`):

| what the verdict carries | what renders | ask on A |
|---|---|---|
| today: `evidence_spans` only | the image, plus the marker strings as chips beneath it | nothing — **works now** |
| `+ extracted_text` | the image, plus the model's own transcript with the markers underlined in it | **one field, cheap** |
| `+ evidence_boxes` | red boxes drawn on the image at the model's coordinates, each labelled | schema change + a model that grounds |

**The ask, ranked.** Level 2 is the high-value / low-cost one: add `extracted_text` to the
verdict body for image modality. You already have it as `ocr_text`. That alone turns beat
3 from *"the model thought it looked internal"* into *"here is what the model read off
the chart, and here are the two phrases that made it a block"* — which is most of what A
is after.

Level 3 needs `evidence_boxes: [{text, x, y, w, h}]` with **x/y/w/h normalised 0–1**, not
pixels — the client downscales to a 1024px long edge before sending, so the model sees a
different pixel space than the overlay renders in. Normalised coordinates survive that;
pixel coordinates would be silently wrong by the downscale ratio. Only worth attempting
if Nemotron-Omni actually grounds text reliably; if it hallucinates positions, level 2 is
strictly better than a confidently-wrong box.

## Also fixed

The harness was serving a stale cached `overlay.js` across reloads — `python -m
http.server` sends `Last-Modified` and Chrome reuses it, which presents as "my change did
nothing". The two files under active development are now loaded with a cache-busting
query string.

---

# Round 7 — A shipped all three; verified live

`d352901`. Checked against a running `services/inspect/app.py`, not read.

**§14 `4111111111111111` — excluded, confirmed.** Now escalates instead of blocking at
T1-HIGH: `use test card 4111111111111111 in the sandbox integration test` →
`503 airlock_unavailable` (T2 unreachable, fail-closed), where it previously returned a
`PAYMENT_CARD` block. With the classifier up it will reach T2 like any other payload.

**§15 `tier_timings` — shipped, and the omit-don't-zero contract was honoured.** A's
`Stages` helper documents it in the class docstring. Real payloads off the box:

```
T0 allow    tier_timings {"CACHE":0.02,"T0":0.0}
T1 block    tier_timings {"CACHE":0.01,"T0":0.0,"T1":0.07}
```

T1/T2/T3 and T2/T3 respectively are **absent**, not zero. Exactly right.

### 17. Key-case mismatch — fixed on B's side, no action needed

B's proposal used `{"cache":…}` lowercase; A shipped `{"CACHE":…}` uppercase. B's strip
matched case-sensitively, so **the cache cell read "not run" on a decision that had in
fact hit it** — a silently wrong cell, which is worse than a missing one. B's fault for
writing the contract as an example rather than as a rule.

Fixed by case-folding the keys on read. Verified against both spellings and against A's
two real payloads:

```
A's T0 real   CACHE:0.02ms[ran]  T0:0ms[resolved]  T1:not run  T2:not run  T3:not run
A's T1 real   CACHE:0.01ms[ran]  T0:0ms[ran]  T1:0.07ms[resolved]  T2:not run  T3:not run
escalated     CACHE  T0  T1:0.42ms[ran]  T2:312ms[MODEL]  T3:not run
lowercase     CACHE:0.4ms[ran]  T0:0.01ms[ran]  T1:0.3ms[resolved]  …
```

Note `T0: 0.0` is a **legitimate** value — a sub-microsecond gate that rounds to zero. It
renders as `0.00 ms` with the stage lit, because it did run. Presence is what decides,
never the value.

**§16 `extracted_text` — shipped** (`app.py:221`, passed through on both the T3 and the
grounded-override paths). B's level-2 image renderer picks it up with no change: the
image, the model's own transcript beneath it, markers underlined in the transcript.
Cannot be exercised end to end until `:8001` is up — the harness covers it at
`#image-ocr` in the meantime.

---

## Still open, owned elsewhere

- `results/scores_benign.json` is the synthetic file from `bench/make_synthetic_scores.py`
  and self-declares `corpus_is_real: false`. C independently flagged the same thing in
  `INTEGRATION.md` round 3 — **do not rehearse the slider against it.** Both consoles will keep the PLACEHOLDER
  label until a real harness run flips it — deliberately.
- That synthetic set is **perfectly separated**: every benign row below 0.30, every
  sensitive row above. The slider therefore reads 0.00% FPR and 100% recall at every τ
  from 0.20 to 0.75, so it looks inert. Fine as a shape fixture; **not something to demo
  with.** One real harness run against a live classifier fixes it.
