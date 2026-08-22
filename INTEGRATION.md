# INTEGRATION.md — cross-branch findings

Written by **C** after diffing `dev_C_DP` against `origin/DEV_A_VP` and `origin/dev_B_RS`.

Everything below was found by reading the other branches, not by running the merged
system. Four of the five are things that would have looked like a broken detector or a
broken UI on stage, and would have sent someone debugging the wrong layer.

**Nothing here requires A or B to change a file.** All five fixes landed in C's files.

---

## 1. `/v1/decisions`, `/v1/policy` and `ws /v1/stream` had no implementation

**Severity: high — B's console was dead on all three.**

B's `sw.js` and `console.js` call:

| Call | A's `app.py` |
|---|---|
| `GET /v1/decisions?limit=50` | not implemented |
| `GET /v1/policy` | not implemented |
| `ws://127.0.0.1:8787/v1/stream` | not implemented |

All three are MongoDB- or policy-backed, so they are C's. They now live in
**`services/inspect/console_api.py`** as a mountable `APIRouter`.

### A — this is your one-line integration

```python
from .console_api import router as console_router
app.include_router(console_router)
```

That is the whole change. The module owns its own Mongo lifecycle (lazily, so it never
blocks your startup), returns an empty feed rather than a 500 when Mongo is down, and
never raises into your request path.

> **Note on `/v1/report`:** you already define it, reading `results/report.json` from
> disk. `console_api.py` also defines one, served live from the `benign_eval`
> aggregation. FastAPI lets the last-registered route win. **Yours is the default and
> that is fine** — `bench/run_fpr.py` now writes `results/report.json` in exactly your
> shape (see §3). Flagging it so two implementations disagreeing on stage is not a
> surprise.

---

## 2. `write_back_corpus()` — signature mismatch that breaks demo beat 4

**Severity: high — `TypeError` on the "detector learns" beat.**

`app.py:315` calls:

```python
corpus_id = await mongo.write_back_corpus(decision_id)      # one argument
```

C's original signature required three (`decision_id, payload, embedding`).

**Fixed in C's file.** `payload` and `embedding` are now optional and resolved
internally: the decision is read, its stored payload decrypted, and the embedding
computed on CPU. Your one-argument call is now the intended way to call it — you should
not have to know anything about embeddings at feedback time.

For this to recover the payload, `write_decision()` now accepts `payload_text=` in its
kwargs and stores it AES-GCM encrypted (same 0600 key as the evidence crop, capped at
8 KB). **If you pass it, beat 4 embeds the real paste. If you don't, it degrades to
embedding the verified evidence spans** — weaker, but still a real correction the
analyst can see rather than a silent no-op.

```python
await mongo.write_decision(verdict, payload_sha256, payload_text=text, chars=len(text))
```

---

## 3. `results/scores_benign.json` — three consumers, two incompatible shapes

**Severity: high — B's threshold slider would silently show "—" on real data.**

| Consumer | Expects |
|---|---|
| B `console.js` `sweep()` | `SCORES.benign.filter(p => p >= tau)` → `{benign: [floats]}` |
| A's `bench/run_fpr.py` | wrote a bare `[{...}, {...}]` list of dicts |
| C's `bench/report.py` | needs the rich per-item dicts |

B's bundled fixture is `{benign:[…]}`. A's harness output is a list. **The moment B
copied the real scores over the fixture, the slider would have read `SCORES.benign` as
`undefined`, shown "—" for FPR and recall, and looked like a UI bug** during the one
section of the demo the SRS says never to cut.

**Fixed.** `bench/run_fpr.py` now writes a single object that satisfies all three:

```json
{
  "benign":    [0.03, 0.11, ...],     ← B filters this, unchanged
  "sensitive": [0.91, 0.88, ...],
  "threshold_default": 0.55,
  "n": 1000,
  "corpus_is_real": true,
  "items":     [ { "_id": "...", "p_block": 0.03, "tier": "T1", ... } ]   ← report.py
}
```

`bench/report.py` reads every historical shape (bare list, `{items:[...]}`, and a
floats-only fixture) so nothing breaks whichever file it is pointed at.

---

## 4. `bench/run_fpr.py` — written twice

**Severity: medium — a merge conflict, not a bug.**

Per SRS §9 the file is C's, but A needed it running by 13:00 and wrote one (138 lines).
C's is 326 lines and a strict superset. **Take C's at merge.** It keeps everything A's
version did, including the behaviours A added that C's did not originally have:

- **`data/smoke_20.jsonl` fallback** — adopted verbatim. The harness is never blocked on
  the corpus; proving it works on 20 pre-staged items at 13:00 beats waiting for 1000.
- **`results/report.json` in A's exact shape** — including the `note` field that reports
  0 FPs as a rule-of-three bound rather than "zero". A's `/v1/report` keeps working.

What C's adds on top:

- errors recorded as `verdict:"ERROR"` rather than dropped, so the denominator cannot
  silently shrink and flatter the FPR;
- a `corpus_is_real` guard that refuses to let placeholder text be reported;
- the sensitive split and per-class recall;
- `benign_eval` writes, with `--no-mongo` as the R4 bypass.

---

## 5. `CONTRACT.md` — written twice, and they agree

**Severity: none — this is the good news.**

B and C wrote it independently. Every JSON field name, status code, timeout and WS frame
type matches, checked field-by-field rather than eyeballed. C's is a superset: it adds
the port-ownership table and the NFR-S1 reminder. **Take C's at merge**; nothing in B's
is lost.

---

---

# Round 2 — found after the merge to `main`

Merged state verified end to end on C's machine: **52 tests green**, service boots,
`T0` allows, `T1` blocks a synthetic AWS key at `POL-001` with the span extracted and
`bytes_egressed: 0`, `/v1/policy` serves the nine clauses, `/v1/decisions` and
`ws /v1/stream` both live off C's router. A's integration of §1–§5 is complete and
correct — `include_router` mounted, `payload_text` passed on blocks, `get_by_hash` at
position zero.

Two new findings.

## 6. `/healthz` reports `"mongo": true` when Mongo is disabled or down

**Severity: medium — it disables the early-warning signal, and it is one line.**

`app.py:107` reports `_HAVE_MONGO`, which only means *the import succeeded*. It stays
`true` with `MONGO_ENABLED=false` and with `mongod` stopped. Observed on the merged tree:

```
/healthz        mongo: true      <- wrong
/v1/decisions   mongo: false     <- correct (C's router calls mongo.healthy())
MONGO_ENABLED=false              <- ground truth
```

Per SRS §5.2 the extension shows an **amber dot** when any `/healthz` field is false.
That signal is exactly how we would notice Mongo had died *before* walking on stage.
As written it can never fire for Mongo: the console would just be silently empty, the
`decision_id`s would be fakes, and beat 4 would do nothing.

**A — one line.** `mongo.healthy()` already exists and does a real ping:

```diff
-    return {"ok": True, "clf": clf, "vlm": vlm, "mongo": _HAVE_MONGO,
+    return {"ok": True, "clf": clf, "vlm": vlm,
+            "mongo": (await mongo.healthy()) if _HAVE_MONGO else False,
```

Left for A rather than patched by C: `app.py` is A's file per SRS §9, and a concurrent
edit to it is precisely the conflict that rule exists to prevent.

## 7. `ws /v1/stream` 404s if uvicorn starts without the `websockets` package

**Severity: medium — it looks exactly like a broken change stream.**

Not a code bug. If `websockets` (or `wsproto`) is not installed **at the moment uvicorn
starts**, uvicorn selects its no-op WebSocket implementation and every upgrade request
gets a plain `404` — while every HTTP route keeps working normally. C hit this: installed
the package, but the already-running server had bound without it.

Symptom on stage: the console renders, backfills 50 decisions over HTTP, and then never
updates. The instinct is to go debug the change stream, the resume token, or Mongo. All
three would be fine.

**Check this first, before suspecting `stream.py`:**

```bash
pip install websockets
python -c "import websockets; print(websockets.__version__)"
# then RESTART uvicorn — installing it under a running server changes nothing
```

Added to `services/inspect/requirements.txt`. A healthy connect returns
`{"type":"hello","policy_version":"policy_v1","resume":null}` as the first frame.

---

## Merge order and conflict resolution

```bash
git checkout main
git merge origin/DEV_A_VP        # A's tiers, app.py, schemas, tests
git merge origin/dev_B_RS        # B's extension, console, replica
git merge dev_C_DP               # C's mongo, stream, corpora, harness, submission
```

Expected conflicts and the resolution:

| Path | Take | Why |
|---|---|---|
| `CONTRACT.md` | **C** | superset, contents agree (§5) |
| `bench/run_fpr.py` | **C** | superset, keeps A's smoke fallback and report.json shape (§4) |
| `.gitignore` | **union** | all three added entries |
| `tools/fixtures/verdict_*.json` | **A** | A owns the verdict shape |
| `results/scores_benign.json` | **regenerate** | do not merge a results file; re-run the harness |

After merging, A adds the two-line `include_router` from §1 and the whole surface is live.

---

## Post-merge smoke test

```bash
bash stack/up_mongo.sh            # wait for "MONGO HEAP VERIFIED"
bash stack/seed.sh                # blocks until search indexes are READY
python tools/fake_decisions.py --burst 200
curl -s localhost:8787/v1/policy    | head -c 200
curl -s 'localhost:8787/v1/decisions?limit=5' | head -c 300
python bench/report.py --selftest
```

If `/v1/decisions` 404s, the `include_router` line from §1 is missing.
If retrieval returns zero clauses, check `queryable`, **not** the embeddings — a
`$vectorSearch` against a non-READY index returns empty results rather than an error.

---

# Round 3 — closing INTEGRATION-B.md §2

## 8. `ConsoleHub.set_metric()` now has a caller (C's gap, found by B)

**Severity: medium — the unified-memory proof rendered as UI was blank.**

B was right: `_metric_loop()` is guarded by `if self._metrics`, and nothing anywhere in
the tree called `set_metric()`. So `{"type":"metric"}` was never broadcast and both KV
gauges read "—" for the entire demo.

**Closed server-side in `stream.py`.** `ConsoleHub._scrape_loop()` polls
`:8000/metrics` and `:8001/metrics` every 2 s while a console is attached, and reads
`escalation_rate` off `/healthz` so B has one source rather than two. Read-only GETs —
nothing is started, stopped or restarted (NFR-S1 is not in play).

Why server-side when B already had it working: one scraper for the box instead of one
per open console tab, and no browser→vLLM traffic at all. B's client already stands its
own scrape down for 6 s when a server metric frame arrives, so the two do not fight —
this wins automatically, exactly as B designed it.

The counter name regex accepts both `vllm:kv_cache_usage_perc` (current) and
`vllm:gpu_cache_usage_perc` (older), with and without labels, and rejects the
`_total` variant. Verified end to end against a stub `/metrics` on both ports:

```
{"type":"metric","kv":{"kv_cache_text":0.3142,"kv_cache_vision":0.1207,"escalation_rate":0.0}}
```

**B — you can drop the client-side scrape whenever you like, or leave it as the fallback
for when the gateway is restarting. Both work.**

## Not changed, deliberately

- **`/v1/decisions` returns raw documents while `ws /v1/stream` returns `_frame()`-shaped
  ones** (INTEGRATION-B.md §1). B normalised it client-side and said nothing needs to
  change server-side. Agreed — B's handler already accepts both shapes, so changing the
  server now would add risk during freeze for no visible gain. Worth tidying after the
  hackathon, not during it.
- **`results/scores_benign.json`** is now the agreed object shape on disk; B's §3 was
  closed by the merge. Still `corpus_is_real: false`, and still perfectly separated, so
  the slider reads 0.00% FPR at every τ. **Do not rehearse the slider against it** — one
  real harness run against a live classifier fixes both.

---

# Round 4 — the real corpus landed

`data/benign_v1.jsonl` is now real: **n=1000, `corpus_is_real: true`, zero synthetic**,
five of six sources pulled live from HuggingFace (WildChat 424, StackExchange 224,
MBPP 124, HumanEval 104, Wikipedia 124; CFPB redistributed — its API is retired).
1000 unique texts, no duplicates, 200–3995 chars. The MBPP composition fix took it from
1 usable to 124, and the `hf_config` fix made Wikipedia run at all.

## 9. Two published Stripe test PANs auto-block at T1-HIGH

**Severity: high — a false positive on stage that no model can rescue.**

Found by scanning the corpora with A's own `t1.scan()` offline, before any harness run.
`services/inspect/tiers/t1.py` `STRIPE_TEST_PANS` is missing two cards that Stripe
publishes:

```
4000000000000077   -> T1 PAYMENT_CARD / HIGH   (should be BENIGN by exclusion)
4000000000000093   -> T1 PAYMENT_CARD / HIGH   (should be BENIGN by exclusion)
```

They carry a valid issuer prefix and a valid Luhn digit, so `PAN_RE` + `luhn()` fire and
**T1-HIGH blocks with no model call** — meaning no later tier can rescue them and the
false positive goes straight to the reported total. SRS §6.2 is explicit that published
test PANs route to BENIGN by exclusion list.

Why this matters more than a two-line diff suggests: *"why does Stripe's test card
4000000000000077 return card_declined in my integration tests"* is a completely natural
question. A judge could ask it. It is precisely the beat-2 failure the runbook has a
recovery line for.

**A — two entries:**

```diff
 STRIPE_TEST_PANS = {
     "4242424242424242", "4000056655665556", "5555555555554444",
+    "4000000000000077", "4000000000000093",
```

Left for A: `t1.py` is A's file per SRS §9.

### The test that found it was flaky, and is now not

The hard-negative bucket sampled 3 PANs at random from the published set, so it caught
`4000000000000077` on one seed and missed it on the next — and a green run gets believed.
`build_sensitive.py` now emits **one probe per published PAN** (17 of them), tagged with
a `probe` field, so every card is exercised on every build regardless of seed.

`bench/build_sensitive.py` also keeps its PAN list **deliberately independent** of
`t1.py`'s. If the corpus only used PANs the detector already excludes, this bucket could
never detect a gap in that exclusion list. Two independent lists disagreeing is the
oracle working, not a bug to tidy away by sharing a constant.

## 10. T1-only ablation row, measured offline with no GPU

`bench/t1_offline.py` scans a corpus with Tier 1 alone, in-process, no service required.
Against the real benign corpus:

| | |
|---|---|
| **T1-HIGH false positives** | **0 / 1000** — below 0.30% at 95% confidence by the rule of three |
| T1-MEDIUM escalations to T2 | 81 / 1000 = **8.1%** — a floor under the escalation rate (NFR-T6) |
| T1-HIGH catches on the sensitive split | 106 / 436 = **24.3%** recall with no model call |

**That is ablation row 1, and it is available now** — hours before the servers are warm,
re-runnable in two seconds, and it needs no GPU. A: it should agree with your row 1 from
`run_ablation.py`; if it does not, one of us has a bug worth finding before 16:00.

`0/1000` on the tier that blocks without a model is a strong result and belongs in the
submission in those words — never as "zero".

## Also worth knowing about the corpus

**It is multilingual.** WildChat includes substantial non-English content (Chinese,
among others) — that is authentic real-world chat traffic, not a defect. But the T2
system prompt is English, and no one has measured whether classification behaves the same
on a Chinese paste. If the FP list comes back skewed toward non-English items, that is the
explanation, and it is an honest limitation to state rather than a bug to hide.
