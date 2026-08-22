# RUN-DAY.md — the real FPR run, end to end

Follow top to bottom. **Do not skip a check.** Every check has a PASS criterion and a
what-to-do-if-not. Owner is marked on every step: `[C]` you, `[A]` engineer A.

> **NFR-S1 — only A starts, stops or restarts a GPU process.** C and B consume
> `:8000`/`:8001`/`:8787` over HTTP and nothing else. A concurrent launch by an unaware
> team-mate is the single most likely way to lose the whole day.

---

## 0 · [C] MongoDB — this blocks A

```bash
bash stack/up_mongo.sh
```

**PASS:** prints `MONGO HEAP VERIFIED`. **Say it out loud — A cannot launch until you do.**

**FAIL:** heap still uncapped → the script escalates. Run plain `mongo:8` without mongot
and export `AIRLOCK_RRF=client`. Retrieval falls back to client-side RRF, which emits an
identical `score`/`scoreDetails` shape, so B's UI does not change.

```bash
bash stack/seed.sh
```

**PASS:** `both search indexes READY and queryable`, then the corpus seed.

**FAIL:** if it says indexes not READY — check `queryable`, **not** the embeddings. A
`$vectorSearch` against a non-queryable index returns *empty results, not an error*.

---

## 1 · [A] Models — two servers, not three

```bash
bash stack/preflight.sh
```

**PASS:** driver reads **580.x**. If it reads 590.x → **hard stop**, Gate G0: CUDAGraph
deadlocks, demo hangs mid-paste with no error.

```bash
bash stack/launch_text.sh
```

```bash
bash stack/launch_vision.sh
```

**Whiteboard total must read 0.68** (text 0.40 + vision 0.28). Ceiling is 0.85.

> **Do NOT run `stack/launch_clf.sh`.** The two-server config is committed; T2 runs on
> the 35B at `:8000`. A's script already refuses without an explicit override — do not
> fight it. Exceeding the ceiling on this box does not OOM, it **freezes the host: no
> SSH, no ping.**

```bash
bash stack/warm.sh
```

**PASS:** both `/health` answer. **First call takes 25–57 s of torch.compile. That is not
a hang.** A cold first paste on stage is a lost demo.

---

## 2 · [C] Inspect service — the env is load-bearing

```bash
.venv/bin/pip install websockets motor pymongo cryptography pyyaml
```

Without `websockets` **at uvicorn start time**, `ws /v1/stream` 404s while every HTTP
route keeps working — it looks exactly like a broken change stream (INTEGRATION.md §7).

```bash
set -a; . stack/models.env; set +a && echo "CLF_URL=$AIRLOCK_CLF_URL"
```

**PASS:** prints `CLF_URL=http://127.0.0.1:8000/v1`.

> **This is the highest-consequence check on the page.** `t2.py` defaults to `:8002` —
> the server you did not launch. Start uvicorn without this and every paste that
> escalates to T2 hits a dead port, times out, and fail-closes to BLOCK. Your FPR comes
> back near-total and looks like a broken detector.

```bash
.venv/bin/uvicorn services.inspect.app:app --host 127.0.0.1 --port 8787
```

Leave it running. New terminal for everything below — **re-source `models.env` there too**
if you run anything that imports the tiers.

---

## 3 · [C] Smoke checks — all five must pass

```bash
curl -s localhost:8787/healthz | python3 -m json.tool
```

**PASS:** `clf:true, vlm:true, mongo:true`.
- `clf:false` → `models.env` did not load, or `:8000` is not up.
- `mongo:false` → Mongo died. It is a real ping now, not an import check.

```bash
curl -s localhost:8787/v1/policy | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['version'],len(d['clauses']),'clauses')"
```

**PASS:** `policy_v1 9 clauses`.

```bash
curl -s "localhost:8787/v1/decisions?limit=5" | python3 -c "import json,sys;d=json.load(sys.stdin);print('mongo:',d['mongo'],'rows:',len(d['decisions']))"
```

**PASS:** `mongo: True`. Zero rows is fine before any traffic.

```bash
curl -s -X POST localhost:8787/v1/inspect -H 'Content-Type: application/json' -d '{"schema":"airlock.inspect.v1","request_id":"r_s1","ts":1,"origin":"x","url":"x","text":"AWS_ACCESS_KEY_ID=AKIAQYLPMN5HXV7TR2WC and the secret is below","html":"","images":[],"mode":"balanced","threshold":null}' | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['action'],d['label'],d['tier'],d['policy_clause_id'],d['evidence_spans'],'bytes:',d['bytes_egressed'])"
```

**PASS:** `block CREDENTIAL T1 POL-001 ['AKIAQYLPMN5HXV7TR2WC'] bytes: 0` — T1 blocks with
no model call.

```bash
curl -s -X POST localhost:8787/v1/inspect -H 'Content-Type: application/json' -d '{"schema":"airlock.inspect.v1","request_id":"r_s2","ts":1,"origin":"x","url":"x","text":"How do I reverse a linked list in Python without using recursion? My iterative version keeps losing the tail pointer.","html":"","images":[],"mode":"balanced","threshold":null}' | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['action'],d['label'],d['tier'],d['latency_ms'],'ms')"
```

**PASS:** `allow BENIGN` at **T2** — this is the one that proves the T2 path is genuinely
alive. If it says `block airlock_unavailable`, go back and re-check `AIRLOCK_CLF_URL`.

---

## 4 · [C] The real FPR run

Before running: **A must have added the two missing Stripe test PANs**
(`4000000000000077`, `4000000000000093`) to `STRIPE_TEST_PANS` in
`services/inspect/tiers/t1.py`, or you bake two known hard-negative false positives into
the reported number (INTEGRATION.md §9).

```bash
.venv/bin/python bench/t1_offline.py
```

**PASS:** `T1-HIGH false positives: 0 / 1000`. Two seconds, no GPU. This is ablation
row 1 and a baseline to compare the real run against.

```bash
.venv/bin/python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55
```

**PASS, all four:**
- `wall clock` under 900 s (`nfr_t5_pass: true`)
- `errors` is **0** — errors are recorded, never dropped, so a wall of them means
  transport trouble, not a clean run
- `benign n` is **1000**
- escalation rate lands roughly **8–20%**. My offline pass says T1 alone escalates 8.1%,
  so far outside that range means wiring, not detector.

**If Mongo is not producing documents:** re-run with `--no-mongo`. The JSON files are
authoritative either way and the aggregation stays in the writeup as the production path.

---

## 5 · [C] Report and submission

```bash
.venv/bin/python bench/report.py
```

```bash
.venv/bin/python -c "import json;d=json.load(open('results/fpr_report.json'));print('reportable:',d['reportable'],'| corpus_is_real:',d['corpus_is_real'],'| n:',d['n'],'| fpr:',d['fpr_statement'])"
```

**PASS:** `reportable: True`, `corpus_is_real: True`, `n: 1000`.
**If `reportable` is False, stop.** Nothing downstream may be quoted, shown, or pasted
into the deck. `fill.py` will refuse anyway.

```bash
.venv/bin/python submission/fill.py
```

**PASS:** `no placeholders remain — ready to submit`. It lists any hand-filled item with
its owner — work that list to zero.

```bash
grep -c '{{' submission/SUBMISSION.final.md
```

**PASS: `0`.** A literal `{{...}}` in a submitted document is unrecoverable.

---

## 6 · [C] Hand-adjudication — 30 minutes, disproportionate credibility

```bash
cat results/false_positives.md
```

Adjudicate **every** item: genuine FP / corpus contamination / borderline. With FPR under
1% that is fewer than ten. Report it verbatim in the submission, e.g. *"7 blocked; on
review 3 contained a genuine live-looking key the corpus author had pasted; corrected
FP = 4/1000."* This turns the corpus's weakness into a demonstration of rigour.

**Watch for non-English items.** The corpus is genuinely multilingual (WildChat) and the
T2 prompt is English. If the FP list skews that way, that is the explanation — state it
as a limitation, do not hide it.

---

## 7 · Rehearse only after §5 passes

```bash
.venv/bin/python tools/fake_decisions.py --burst 900
```

Backfills the console so it looks like a real day for the screenshot.

Then the seven demo checks: benign paste allows · customer list blocks · chart blocks ·
blocked prompt routes to the local answer · console updates live · `policy_denied` ·
offline proof with the cable out.

> **Do not rehearse the threshold slider against the current fixture** — it is perfectly
> separated, so it reads 0.00% FPR at every τ and looks inert. The real run from §4 fixes
> that.

> **Never unplug the ethernet while the `chatgpt.com` tab is focused** (R15). One
> accidental reload offline and that tab is gone.

---

## Fast triage

| Symptom | First thing to check | Not this |
|---|---|---|
| Everything blocks `airlock_unavailable` | `echo $AIRLOCK_CLF_URL` — must be `:8000/v1` | the detector |
| Console never updates | is `websockets` installed, and did uvicorn restart after? | the change stream |
| Console dies after a re-seed | `invalidate → startAfter` in `stream.py` | the socket |
| Retrieval returns nothing | `queryable` on the search index | the embeddings |
| KV gauges read "—" | both vLLM `/metrics` reachable | B's console |
| `mongosh` hangs | `directConnection=true` in the URI | the container |
| FPR looks impossibly high | §2 env, then `errors` in the run output | the corpus |
| FPR looks impossibly low | `reportable` and `corpus_is_real` in the JSON | nothing — verify it |
| Box unresponsive | say **"FREEZE"** out loud; A checks `MemAvailable` | anything else |
