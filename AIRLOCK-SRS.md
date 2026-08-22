# AIRLOCK — Software Requirements Specification

**Dell × NVIDIA GB10 Hackathon · 3 engineers · build window 10:00–18:00 · written submission closes 18:00**

Airlock intercepts the moment company data is about to leave a laptop for an unapproved cloud AI tool, inspects the payload locally on the GB10, blocks it if confidential, and re-routes the question to the local model so the employee still gets an answer.

**Owners:** **A** Inference · **B** Client & UI · **C** Stack, Data & Writeup

> Every command below is copy-pasteable. Items that could not be verified against primary docs this morning are tagged **VERIFY-ON-THE-DAY** and carry a stated fallback.

---

## 1. Purpose and Scope

Airlock is a fail-closed egress control for AI tools. It runs entirely on one Dell Pro Max with GB10, makes no network calls off the box, and proves that claim from the platform's own audit log rather than asserting it.

**In scope:** clipboard-payload interception (text and image), local classification, block/allow decision with a cited policy clause, sanctioned local answering, an audit ledger, a live console, and a measured false-positive rate.

**Out of scope, stated honestly:** fleet deployment, endpoint management, screen-photography threat vectors, and anything requiring synthetic input injection.

## 2. Definitions

| Term | Meaning |
|---|---|
| **Verdict** | `allow` / `block` / `redact` plus spans, confidence, and a cited policy clause |
| **Tier 0/1/2** | Cascade stages: deterministic detectors → text LLM → vision LLM |
| **Sanctioned path** | The blocked question, re-answered by the local agent |
| **Denial artifact** | OpenShell's `policy_denied` JSON, used as demo evidence |
| **Fast path** | Text payloads resolved without an LLM call |

---

## 3. System Architecture

All three models, MongoDB and the inspect service run on **one host**: the Dell Pro Max with GB10 (`airlock-box`, DGX OS 7 / Ubuntu 24.04.3 ARM64, driver **580.x** — VERIFY-ON-THE-DAY with `nvidia-smi --query-gpu=driver_version --format=csv`; 590.x deadlocks CUDAGraph and is a hard stop, not a warning).

```
┌─────────────────────────── CHROME (demo laptop = same box) ───────────────────────────┐
│  MV3 extension "Airlock"                                                              │
│   ├ airlock.js      content script, document_start, capture phase, all_frames         │
│   │                 paste/drop/change → preventDefault → downscale ≤1024px → SW       │
│   ├ sw.js           service worker; fetch() to 127.0.0.1:8787 (LNA-exempt path)       │
│   └ mainworld.js    MAIN world, patches window.fetch → synthetic 403 policy_denied    │
│  local replica page  http://localhost:5173   (beat 4, offline, loopback→loopback)     │
└───────────────────────────────────────────┬───────────────────────────────────────────┘
                                            │  POST /v1/inspect   (plain HTTP, JSON)
                                            ▼
┌──────────────────────────── HOST: airlock-box (128 GB unified) ───────────────────────┐
│                                                                                       │
│  ┌─ inspect-svc ─────────────────────────────── 127.0.0.1:8787 ── uvicorn, CPU ────┐  │
│  │  T0 trivial gate  ~0.01 ms      T1 regex+Luhn+entropy  ~0.3 ms                  │  │
│  │  bge-small-en-v1.5 (384d) + bge-reranker-base → ONNX Runtime on 20 Arm cores    │  │
│  │  <1.7 GB RSS. NO GPU process. Grace does retrieval, Blackwell does inference.   │  │
│  └───┬───────────────┬──────────────────┬──────────────────────┬───────────────────┘  │
│      │ T2 text       │ T3 image         │ sanctioned answer    │ pymongo/motor        │
│      ▼               ▼                  ▼                      ▼                      │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐   ┌────────────────────────────┐   │
│  │ airlock-clf│  │airlock-    │  │ airlock-text │   │ airlock-mongo (docker)     │   │
│  │ :8002      │  │vision :8001│  │ :8000        │   │ :27017                     │   │
│  │ vLLM       │  │ vLLM       │  │ vLLM         │   │ mongodb-atlas-local:8.3.8  │   │
│  │ Qwen3-4B-  │  │ Holo1.5-7B │  │ Qwen3.6-35B- │   │ mongod + mongot, 1-node RS │   │
│  │ Instruct-  │  │ BF16       │  │ A3B-NVFP4    │   │ --memory=6g --cpus=4       │   │
│  │ 2507       │  │ (Qwen2.5-VL│  │ FP8 KV, MTP  │   │ ⇒ JVM heap ≈1.5 GB         │   │
│  │ guided JSON│  │  arch)     │  │ spec-decode  │   │ arm64 digest 850b753b…     │   │
│  └────────────┘  └────────────┘  └──────────────┘   └────────────────────────────┘   │
│      0.09            0.24              0.40                    6 GB cgroup            │
│                                                                                       │
│  NemoClaw (host reference stack) → OpenShell (Rust sandbox: policy, inference          │
│  routing, deny-by-default egress, 5-endpoint allowlist, GitHub blocked) → OpenClaw     │
│  OpenShell routes text/* → :8000, image/* → :8001, and fronts https://inference.local  │
│  Denials emit {"error":"policy_denied",...} — the same JSON the extension renders.     │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Memory budget

`--gpu-memory-utilization` is a fraction of the **whole 128 GB shared pool**, not of a VRAM partition. Calibration anchor: 0.85→0.4 frees ~58 GB ⇒ **1.00 ≈ 129 GB**.

| Process | Port | Model | frac | ≈ GB |
|---|---|---|---|---|
| airlock-text | 8000 | Qwen3.6-35B-A3B-NVFP4 (w ~22 + FP8 KV ~26 + graphs ~3) | 0.40 | 51.6 |
| airlock-vision | 8001 | Holo1.5-7B BF16 (w ~16.5 + KV ~9 + MM caches ~2 + graphs ~3) | 0.24 | 31.0 |
| airlock-clf | 8002 | Qwen3-4B-Instruct-2507 BF16, `--max-model-len 8192` | 0.09 | 11.6 |
| **CUDA reserved** | | | **0.73** | **94.2** |
| airlock-mongo (mongod + mongot JVM) | 27017 | — | cgroup | 6.0 |
| inspect-svc + bge-small + reranker (CPU) | 8787 | — | — | 1.7 |
| OS + GNOME + docker + page cache | — | — | — | ~14 |
| **Total** | | | | **≈115.9** |

**Headroom: ~10.6 GB below the ~126.5 GB host-crash ceiling, and 0.73 against the established 0.85 `gpu-memory-utilization` ceiling.** If it gets tight, headless serving mode reclaims a further 10–15 GB from GNOME/display-manager in one command. Never exceed 0.85 summed: on this box unbounded allocation **hangs the whole host** (no SSH, no ping) instead of raising OOM (pytorch/pytorch#174358).

Mandatory pre-flight before either GPU server: `sudo swapoff -a` then `sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'`. OS page cache competes with CUDA for the same pool. Env on every vLLM container: `VLLM_MARLIN_USE_ATOMIC_ADD=1`, `VLLM_USE_FLASHINFER_MOE_FP4=0`, `CUTE_DSL_ARCH=sm_121a`; vision additionally `VLLM_MM_INPUT_CACHE_GIB=2` + `--mm-processor-cache-gb 1` (defaults are 8 GiB/4 GiB **per process**, live in "CPU RAM" which here is the same pool — 15–20 GB of invisible consumption otherwise). Vision image: `hellohal2064/vllm-dgx-spark-gb10` (SM121-patched); stock vLLM images fail `SM121 not supported` for VLMs.

**mongot JVM heap — the host-freeze risk.** Documented default: *25% of total system memory, capped at 32 GB, with 128 GB of system memory as the worked example.* Unconstrained, mongot targets **32 GB** of the same pool vLLM sized itself against. The control is the cgroup: `--memory=6g --memory-swap=6g` on `docker run` — JVMs have honoured `UseContainerSupport` since JDK 10, so "total system memory" resolves to the cgroup limit → **25% of 6 GB ≈ 1.5 GB heap**. VERIFY-ON-THE-DAY at 10:00, five minutes: `docker stats airlock-mongo` and `docker exec airlock-mongo grep -i -m5 -E 'Xmx|heap' /tmp/mongot.log`. Fallback if the cap does not take: `-e JAVA_TOOL_OPTIONS="-Xms1g -Xmx2g"` (undocumented on this image, honoured by most JVM launchers). Also pin `--cpus=4` so the JVM does not size GC threads off all 20 Arm cores.

```bash
docker run -d --name airlock-mongo --platform linux/arm64 \
  --memory=6g --memory-swap=6g --cpus=4 -p 27017:27017 \
  -v airlock_mongo_data:/data/db -e DO_NOT_TRACK=1 \
  -e MONGODB_INITDB_DATABASE=airlock mongodb/mongodb-atlas-local:8.3.8
until [ "$(docker inspect -f '{{.State.Health.Status}}' airlock-mongo)" = healthy ]; do sleep 2; done
```

`DO_NOT_TRACK=1` is not optional: the image phones home, and an unsolicited outbound call is precisely what our own demo claims to prevent — a judge running `tcpdump` during beat 4 would find it. Connection string is `mongodb://localhost:27017/?directConnection=true`; **`directConnection=true` is mandatory** or the driver does replica-set discovery, gets the container-internal hostname back and hangs until server-selection timeout.

**Fallbacks.** Vision weights ladder: Holo1.5-7B → `nvidia/Qwen2.5-VL-7B-Instruct-NVFP4` (NVIDIA-validated on Spark, same code path) → `Qwen/Qwen3-VL-8B-Instruct`. If airlock-clf will not fit or boot, route T2 to `:8000` — costs latency, costs no memory. Rejected and worth saying so: CUDA MPS (+10% throughput, TTFT 16.7 s → 27.1 s, measured on this chip), vLLM sleep mode (offloads to "CPU RAM" — the same DRAM), speculative decoding on the VLM (we emit ≤8 tokens).

## 4. Data Model (MongoDB)

**Time-series collections support NEITHER change streams NOR MongoDB Search/Vector Search NOR CSFLE.** No single collection can be searchable, watchable and time-series. Hence a deliberate three-way split by access pattern, plus an isolated harness collection.

| Collection | Type | Why it must be this type |
|---|---|---|
| `policy_corpus` | regular | needs `$search` + `$vectorSearch` — impossible on time-series |
| `decisions` | regular | needs **change streams** for the live console — impossible on time-series |
| `inspect_metrics` | **time-series** | append-only telemetry; columnar buckets, `$setWindowFields`, TTL |
| `benign_eval` | regular | 1000-doc burst would roll the single-node oplog and kill the console's resume token |

### Schemas

```javascript
// policy_corpus — semantic memory. kind:"exemplar" is the detector; kind:"clause" is the policy text.
{ _id: ObjectId, kind: "exemplar"|"clause", clause_id: "POL-006",
  class: "pii"|"financial"|"credentials"|"source_code"|"legal_hr"|"health"|"benign",
  tenant: "acme", modality: "text"|"image", severity: "LOW"|"MEDIUM"|"HIGH",
  text: "Q3 ARR came in at 14.2M against a 16M plan…",   // embedded + lexically indexed
  snippet: "…", embedding: [/* 384 floats, bge-small-en-v1.5 */],
  origin: "seed"|"analyst_override", added_by: "analyst@acme", ts: ISODate() }

// decisions — episodic memory + hash-keyed instant-block cache
{ _id: ObjectId, ts: ISODate(), payload_sha256: "…",       // cache key
  origin: "https://chatgpt.com", modality: "text"|"image",
  verdict: "BLOCK"|"ALLOW", label: "FINANCIAL_NONPUBLIC", clause_id: "POL-006",
  tier: "T1"|"T2"|"T3"|"CACHE", p_block: 0.91, threshold: 0.55,
  evidence_spans: ["FY26 Revenue Forecast","Internal — Do Not Distribute"],
  span_verified: true, override_reason: null,
  score_details: { /* $rankFusion tree, verbatim */ },
  evidence_png: BinData(0,"…"),        // AES-GCM ciphertext of the ≤1024px crop
  evidence_nonce: BinData(0,"…"), latency_ms: 412, chars: 1180, images: 1 }

// inspect_metrics — time-series
{ ts: ISODate(), meta: { model: "airlock-vision", modality: "image", verdict: "BLOCK", tier: "T3" },
  latency_ms: 412, prefill_tokens: 1376, output_tokens: 8, image_px: 921600 }

// benign_eval — one doc per benign corpus item
{ _id: "wildchat:8811", source: "WildChat-1M", license: "ODC-BY", sha256: "…",
  char_len: 812, label: "BENIGN", verdict: "ALLOW", p_block: 0.04, latency_ms: 3, tier: "T1" }
```

Evidence is stored as **`BinData`, not GridFS** — crops are far under the 16 MB BSON limit, GridFS costs two collections, a second round trip and atomicity (the crop and its verdict could not be written in one operation), and it fragments the "one document = one decision" story. AES-GCM via `cryptography`, key in a 0600 file that never leaves the box. State the boundary honestly: *Queryable Encryption is the production path and is unavailable in Community.*

### Indexes

```javascript
db.createCollection("inspect_metrics", { timeseries:{ timeField:"ts", metaField:"meta",
  granularity:"seconds" }, expireAfterSeconds: 86400 })

db.decisions.createIndex({ payload_sha256: 1 })          // instant-block cache lookup, ~1 ms
db.decisions.createIndex({ ts: -1 })                     // console backfill
db.benign_eval.createIndex({ verdict: 1 })

db.policy_corpus.createSearchIndex("airlock_vec", "vectorSearch", {
  fields: [
    { type: "vector", path: "embedding", numDimensions: 384, similarity: "cosine" },
    { type: "filter", path: "class" },
    { type: "filter", path: "tenant" },
    { type: "filter", path: "modality" },
    { type: "filter", path: "kind" }
  ]})
db.policy_corpus.createSearchIndex("airlock_text", "search",
  { mappings: { dynamic: false, fields: { text: { type: "string" },
                                          class: { type: "token" } } } })
```

`cosine`, because bge-small is trained for it and MongoDB does not normalise for you. Declare all four filter paths **now** — adding one later is an index rebuild you will not have time for after 16:00. Index builds are async and a query against a non-queryable index returns **empty results rather than an error**, which looks like a broken detector; block the seed script on both waits:

```javascript
db.policy_corpus.aggregate([{ $listSearchIndexes: {} }]).toArray()
  .map(i => ({ name: i.name, status: i.status, queryable: i.queryable }));  // want READY / true
```

### Runtime pipeline — hybrid retrieval (T2 clause grounding, and the block-overlay audit trail)

```javascript
db.policy_corpus.aggregate([
  { $rankFusion: {
      input: { pipelines: {
        semantic: [ { $vectorSearch: { index:"airlock_vec", path:"embedding",
                        queryVector: QVEC, numCandidates: 200, limit: 20,
                        filter: { modality: "text", kind: "exemplar" } } } ],
        lexical:  [ { $search: { index:"airlock_text",
                        text: { query: PASTE_TEXT, path: "text" } } }, { $limit: 20 } ]
      } },
      combination: { weights: { semantic: 0.7, lexical: 0.3 } },
      scoreDetails: true } },
  { $limit: 5 },
  { $addFields: { score: { $meta: "score" }, scoreDetails: { $meta: "scoreDetails" } } },
  { $project: { text:0, embedding:0 } }
])
```

The metadata keys are **`{$meta:"score"}` and `{$meta:"scoreDetails"}`** — one MongoDB docs page shows `searchScoreDetails` in a `$rankFusion` example; that is the `$search`-specific key and it silently returns nothing here. The top-3 `clause_id`s become the constrained enum for the T2 classifier, so the cited clause cannot be hallucinated. `scoreDetails` is rendered verbatim in the block overlay: rank, weight and per-pipeline contribution, with the server's own plain-English `description` of the RRF formula. That is an auditable explanation rather than a black-box BLOCK.

**Default: the server-side `$rankFusion`.** Use the client-side fallback only if mongot misbehaves — it emits the identical `score`/`scoreDetails` shape so B's UI never changes:

```python
def rrf(ranked_lists, weights=None, k=60):
    weights = weights or {}; scores, docs, detail = {}, {}, {}
    for name, ordered in ranked_lists.items():
        w = weights.get(name, 1.0)
        for rank0, doc in enumerate(ordered):
            rank = rank0 + 1; _id = doc["_id"]; contrib = w * (1.0 / (k + rank))
            scores[_id] = scores.get(_id, 0.0) + contrib
            docs.setdefault(_id, doc)
            detail.setdefault(_id, []).append(
                {"inputPipelineName": name, "rank": rank, "weight": w, "contribution": contrib})
    out = []
    for _id, s in sorted(scores.items(), key=lambda kv: -kv[1]):
        d = dict(docs[_id]); d["score"] = s; d["scoreDetails"] = detail[_id]; out.append(d)
    return out
```

For the **FP-rate harness use `exact: true` ENN unconditionally** — `{ $vectorSearch: { index:"airlock_vec", path:"embedding", queryVector: QVEC, limit: 10, exact: true } }`. The corpus is a few thousand docs, ENN needs no `numCandidates`, and the number must be reproducible when a judge asks us to re-run it. ANN recall jitter would make the same benign paste block on one run and pass on the next.

### Console feed

Backfill, then tail. Do **not** point the console at `benign_eval`.

```javascript
db.decisions.aggregate([ { $sort: { ts: -1 } }, { $limit: 50 },
  { $project: { evidence_png: 0 } } ])
```

```python
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

client = AsyncIOMotorClient("mongodb://localhost:27017/?directConnection=true")
coll = client.airlock.decisions

async def tail_decisions(on_event, token=None, use_start_after=False):
    pipeline = [{"$match": {"operationType": {"$in": ["insert", "update", "invalidate"]}}}]
    while True:
        try:
            kwargs = {"full_document": "updateLookup"}
            if token:
                kwargs["start_after" if use_start_after else "resume_after"] = token
            async with coll.watch(pipeline, **kwargs) as stream:
                async for change in stream:
                    token = change["_id"]                      # persist every event
                    if change["operationType"] == "invalidate":
                        use_start_after = True                 # resumeAfter CANNOT cross this
                        break
                    use_start_after = False
                    await on_event(change["fullDocument"])
                    if stream.resume_token:                    # high-watermark: don't fall behind
                        token = stream.resume_token
        except PyMongoError:
            await asyncio.sleep(1)
```

The seed script drops and recreates `decisions` several times today; without the `invalidate` → `startAfter` transition the console dies permanently on the first re-seed.

### Analytics

```javascript
// THE DECIDING ARTIFACT — false-positive rate with a denominator
db.benign_eval.aggregate([
  { $group: { _id: null, n: { $sum: 1 },
      false_pos: { $sum: { $cond: [ { $eq: ["$verdict","BLOCK"] }, 1, 0 ] } },
      p50_latency: { $percentile: { input:"$latency_ms", p:[0.50], method:"approximate" } },
      p95_latency: { $percentile: { input:"$latency_ms", p:[0.95], method:"approximate" } } } },
  { $set: { fpr: { $divide: ["$false_pos","$n"] },
            fpr_pct: { $round: [ { $multiply: [ { $divide: ["$false_pos","$n"] }, 100 ] }, 2 ] } } }
])

// live throughput / latency rollup on the time-series collection
db.inspect_metrics.aggregate([
  { $setWindowFields: { partitionBy: "$meta.modality", sortBy: { ts: 1 }, output: {
      pastes_per_min: { $count: {}, window: { range: [-60, 0], unit: "second" } },
      p95_latency: { $percentile: { input:"$latency_ms", p:[0.95], method:"approximate" },
                     window: { range: [-300, 0], unit: "second" } } } } }
])
```

### Why each MongoDB feature earns its place

- **Vector Search (`$vectorSearch`, 384-d cosine)** — semantic memory: exemplars of what "sensitive" looks like. This *is* the detector for classes no regex can reach, not a demo of one.
- **`$search` (lexical)** — recovers exact tokens (`FY26`, `Do Not Distribute`) that embeddings blur away.
- **`$rankFusion` + `scoreDetails`** — one server-side call fuses both signals *and* returns the per-signal audit trail we render as the block reason.
- **Change streams** — the live console is push, not poll; it is also why `decisions` cannot be time-series.
- **Time-series + `$setWindowFields` + TTL** — bucketed columnar telemetry with rate-over-time windows and automatic expiry, for free.
- **Unique-ish hash index on `decisions.payload_sha256`** — the semantic-cache pattern applied to security: the second identical paste blocks in ~1 ms with no model call.
- **Write-back to `policy_corpus`** — procedural memory. An analyst marks a false positive benign, its embedding is written back, the next paste of that shape passes, a near neighbour still blocks. **The detector learns without retraining a model** — live, visible, impossible with a regex.

Known non-production gap, stated rather than hidden: the container runs without auth on loopback. Disk: mongot goes read-only at 90% storage utilisation and fails **silently as an empty result set**; irrelevant at this corpus size, but it is the failure mode to recognise.

## 5. API Contracts

All services bind `127.0.0.1`. The Chrome extension talks only to `http://127.0.0.1:8787` (see MV3/LNA constraint: fetch from the **service worker**, never the content script). The gateway proxies internally to vLLM `:8000` (text answer), `:8001` (vision), `:8002`-or-CPU (classifier). `https://inference.local` is the *sandbox-side* name only; never put it in the extension.

### 5.1 `POST /v1/inspect` — the one hot endpoint

Request (`Content-Type: application/json`, max body 8 MiB):

```json
{
  "schema": "airlock.inspect.v1",
  "request_id": "r_9f3a2c",
  "ts": 1755772800123,
  "origin": "https://chatgpt.com",
  "url": "https://chatgpt.com/c/abc",
  "text": "…paste text, may be \"\"…",
  "html": "",
  "images": [ { "mime": "image/jpeg", "w": 1280, "h": 720, "b64": "/9j/4AAQ…" } ],
  "mode": "balanced",
  "threshold": null
}
```

Rules: `images` ≤ 1 (extension enforces; server rejects >4 with 413). `b64` is raw base64, no data-URI prefix. Client downscales long edge ≤ 1024 px **before** send.

Response `200`:

```json
{
  "schema": "airlock.verdict.v1",
  "request_id": "r_9f3a2c",
  "action": "block",
  "label": "CUSTOMER_RECORD",
  "severity": "HIGH",
  "policy_clause_id": "POL-004",
  "policy_clause_text": "Customer-identifying records must not leave managed endpoints.",
  "reason": "12 rows of name,email,phone,plan,mrr",
  "evidence_spans": ["ana.ruiz@northwind.example,+1-415-555-0142,Pro,4200"],
  "evidence_verified": true,
  "score": 0.94,
  "p_block": 0.94,
  "threshold": 0.55,
  "tier": "T2",
  "model": "airlock-clf/qwen3-4b",
  "modality": "text",
  "latency_ms": 312,
  "bytes_egressed": 0,
  "decision_id": "6712c0f1a3e94b2d8c5e1102",
  "score_details": { "value": 0.0306, "description": "reciprocal rank fusion…", "details": [] }
}
```

`action` ∈ `allow` | `block` | `warn`. `tier` ∈ `T0` | `T1` | `T2` | `T3` | `CACHE`. On `allow`, `label:"BENIGN"`, `evidence_spans: []`, `severity:"NONE"`.

Status codes: `200` verdict (including block — a block is not an HTTP error); `400` malformed JSON / missing `schema`; `413` body > 8 MiB or >4 images; `422` image decode failure; `429` >32 in-flight; `503` classifier not ready (model loading) — body carries the fail-closed shape below; `504` upstream vLLM exceeded 2000 ms.

Error shape (all non-200):

```json
{ "schema":"airlock.error.v1", "error":"policy_denied", "code":503,
  "label":"airlock_unavailable", "action":"block",
  "reason":"Inspector unreachable — deny by default", "request_id":"r_9f3a2c" }
```

The `"error":"policy_denied"` string is deliberate: it is byte-identical to OpenShell's egress-denial body, which is demo beat 5.

**Timeouts.** Client `AbortController` 2500 ms → renders fail-closed BLOCK. Server internal budget: T1 5 ms, T2 call 1200 ms, T3 call 2000 ms, hard total 2300 ms. Server never hangs; it returns `504` with the fail-closed body.

### 5.2 Supporting endpoints

| Method | Path | 200 body | Notes |
|---|---|---|---|
| `GET` | `/healthz` | `{"ok":true,"clf":true,"vlm":true,"mongo":true,"uptime_s":812}` | Any `false` ⇒ still `200`; extension shows amber dot. SW warms this on `onStartup`. |
| `GET` | `/v1/policy` | `{"version":"policy_v1","clauses":[{"id":"POL-001","class":"CREDENTIAL","severity":"HIGH","text":"…"}]}` | Renders clause text in the overlay; ids are the enum in §6.4. |
| `POST` | `/v1/answer` | SSE stream, OpenAI chat delta shape | Sanctioned path. Proxies `:8000` `airlock-text`. `{"prompt":"…","decision_id":"…"}`. |
| `POST` | `/v1/feedback` | `{"ok":true,"corpus_id":"…","embedded":true}` | `{"decision_id":"…","verdict":"benign","analyst":"demo"}`. Writes the payload + bge-small embedding back into `policy_corpus` → procedural-memory beat. |
| `GET` | `/v1/report` | `{"n":1000,"false_pos":3,"fpr":0.003,"ci95":[0.001,0.0088],"p50_ms":12,"p95_ms":480,"by_class":{…}}` | Served straight from the `benign_eval` aggregation. |
| `OPTIONS` | any | `204` | Headers: `Access-Control-Allow-Origin: *`, `-Methods: POST, GET, OPTIONS`, `-Headers: Content-Type`, `Access-Control-Allow-Private-Network: true`, `-Max-Age: 600`. Use with `credentials: 'omit'`. |

### 5.3 WebSocket console — `ws://127.0.0.1:8787/v1/stream`

Server→client only; client sends nothing but an optional `{"type":"hello","since":"<resume_token>"}` first frame. One JSON object per frame, newline-free.

```json
{"type":"decision","ts":1755772800123,"decision_id":"6712c0f1…","host":"chatgpt.com",
 "modality":"text","chars":412,"action":"allow","label":"BENIGN","p_block":0.02,
 "tier":"T1","latency_ms":188}
```

Other frame types: `{"type":"hello","policy_version":"policy_v1","resume":"<token>"}` on connect; `{"type":"metric","kv":{"kv_cache_text":0.31,"kv_cache_vision":0.12,"escalation_rate":0.14}}` every 2 s (scraped from both vLLM `/metrics`); `{"type":"ping"}` every 15 s (also keeps an MV3 SW alive if ever used there — the console page is a normal tab, so not needed). Backed by a MongoDB change stream on `decisions` with `full_document:"updateLookup"`; the resume token is persisted per event, and reconnect uses `startAfter` after an `invalidate` (the seed script drops `decisions`, so `resumeAfter` alone would die permanently). Client reconnects with exponential backoff 250 ms → 4 s.

### 5.4 Classifier strict output schema (guided decoding)

Sent to vLLM as `response_format={"type":"json_schema","json_schema":{"name":"airlock_verdict","schema":SCHEMA}}`. **VERIFY-ON-THE-DAY at the 10:45 gate** which spelling the pinned vLLM accepts; fallbacks in order: `extra_body={"structured_outputs":{"json":SCHEMA}}`, then `extra_body={"guided_json":SCHEMA}`. Property order is load-bearing — xgrammar emits in schema order, so evidence precedes label and the label is conditioned on it.

```json
{"type":"object","additionalProperties":false,
 "required":["evidence_spans","rationale","label","severity","policy_clause_id","confidence"],
 "properties":{
  "evidence_spans":{"type":"array","maxItems":3,"items":{"type":"string","maxLength":120}},
  "rationale":{"type":"string","maxLength":160},
  "label":{"type":"string","enum":["BENIGN","CREDENTIAL","PAYMENT_CARD","GOV_ID",
    "CUSTOMER_RECORD","HEALTH_RECORD","FINANCIAL_NONPUBLIC","PROPRIETARY_CODE","LEGAL_HR"]},
  "severity":{"type":"string","enum":["NONE","LOW","MEDIUM","HIGH"]},
  "policy_clause_id":{"type":"string","enum":["NONE","POL-001","POL-002","POL-003",
    "POL-004","POL-005","POL-006","POL-007","POL-008","POL-009"]},
  "confidence":{"type":"number","minimum":0,"maximum":1}}}
```

Call parameters, fixed: `temperature=0.0, seed=1337, max_tokens=200, logprobs=True, top_logprobs=20`. The vision schema (T3) is the same object prefixed by `image_type`, `extracted_text` (≤30 × 100 chars), `org_markers`, `temporal_markers`, `confidentiality_markers`, with `label` enum minus `GOV_ID`/`PAYMENT_CARD`.

### 5.5 gRPC / OpenShell middleware path

**Decision: no gRPC today.** OpenShell's inference router speaks HTTP; adding protobuf costs an hour and buys nothing. The middleware path reuses `POST /v1/inspect` verbatim over one of the five allowlisted endpoints. Denials from OpenShell arrive as `{"error":"policy_denied","rule":"<id>","endpoint":"<url>"}` — the gateway passes that body through unchanged with HTTP `403`. If a gRPC contract is demanded in Q&A, the answer is the equivalent service definition, unimplemented: `service Airlock { rpc Inspect(InspectRequest) returns (Verdict); }` with fields numbered in the JSON order above. Do not build it.

## 6. Classification Design

### 6.1 Taxonomy — 8 classes + BENIGN, one orthogonal severity axis

| ID | Class | Definition | Primary tier |
|---|---|---|---|
| POL-001 | `CREDENTIAL` | Live API keys, tokens, private keys, passwords, credentialed connection strings | T1 |
| POL-002 | `PAYMENT_CARD` | Real PANs, optionally with CVV/expiry | T1 (Luhn) |
| POL-003 | `GOV_ID` | SSN, ITIN, passport, driver's licence, national ID | T1 + context |
| POL-004 | `CUSTOMER_RECORD` | ≥3 rows of person-identifying tuples | T1 structural → T2 |
| POL-005 | `HEALTH_RECORD` | Patient-identifiable clinical information | T2 |
| POL-006 | `FINANCIAL_NONPUBLIC` | Unreleased forecasts, ARR/MRR, pipeline, cap tables, comp | T2 / T3 |
| POL-007 | `PROPRIETARY_CODE` | Internal source/infra config, internal hostnames, explicit internal marking | T2 |
| POL-008 | `LEGAL_HR` | NDA'd contracts, litigation, disciplinary/HR matters | T2 |
| POL-009 | reserved | (spare id so the enum never needs a schema change) | — |
| NONE | `BENIGN` | Everything else — **the default answer** | T0/T2 |

Severity `LOW|MEDIUM|HIGH` drives log / warn / block independently of class.

### 6.2 Tier 1 — deterministic detectors (tested, 14/14 TP, 0/7 FP on the PAN set)

```python
PAN_RE = re.compile(
    r'(?<![\w.\-])'
    r'(?:4\d{3}|5[1-5]\d{2}|2(?:2[2-9]\d|[3-6]\d{2}|7[01]\d|720)|3[47]\d{2}'
    r'|6(?:011|5\d{2}|4[4-9]\d|2\d{2})|3(?:0[0-5]|[68]\d)\d|35\d{2})'
    r'[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,7}(?![\w.\-])')

def luhn(s):
    d=[int(c) for c in re.sub(r'\D','',s)]
    if not 12<=len(d)<=19: return False
    t=0
    for i,x in enumerate(reversed(d)):
        if i%2:
            x*=2
            if x>9: x-=9
        t+=x
    return t%10==0
```

The `(?<![\w.\-])` boundary — **not `\b`** — is what kills hex literals, IPs and timestamp-shaped 16-digit runs.

Credential prefixes, verbatim from gitleaks `config/gitleaks.toml`, all HIGH-confidence auto-block: `\b((?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\b`, `ghp_[0-9a-zA-Z]{36}`, `github_pat_\w{82}`, `glpat-[\w-]{20}`, `xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*`, `\b((?:sk|rk)_(?:test|live|prod)_[a-zA-Z0-9]{10,99})`, `\b(sk-(?:proj|svcacct|admin)-)`, `\b(sk-ant-api03-[a-zA-Z0-9_\-]{93}AA)`, `(?i)-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY`, `\b(ey[a-zA-Z0-9]{17,}\.ey[a-zA-Z0-9\/\_-]{17,})`, `\b(AIza[\w-]{35})`, `([a-zA-Z0-9_~.]{3}\dQ~[a-zA-Z0-9_~.-]{31,34})`. `generic-api-key` is MEDIUM → escalate, never auto-block.

Others: `SSN = (?<!\d)(?!000|666|9\d\d)\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}(?!\d)` requiring a keyword within 100 chars; `IBAN = \b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b` + mod-97; `EMAIL`, `PHONE_US`, `PEM`, `CONNSTR = \b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:@]+:[^\s@]+@`, `AWS_ARN`.

Entropy is only ever applied to a candidate token, never to prose (measured: English prose H=4.39 > SHA-256 hex H=3.79):

```python
CAND = re.compile(r'[A-Za-z0-9+/_\-=]{20,}')
def looks_like_secret(tok):
    H = shannon(tok)
    cls = sum(bool(re.search(p,tok)) for p in (r'[a-z]',r'[A-Z]',r'\d',r'[+/_\-=]'))
    return H >= 3.7 and cls >= 3 and len(tok) >= 20
```

Bare 40-hex is a git SHA: flag only with `secret|token|key|password|apikey` within 40 chars. UUIDs whitelisted. Published test PANs (Stripe's 14) route to `BENIGN` by exclusion list — Purview does the same; say so.

Structural customer-list detector: consistent delimiter across ≥3 non-empty lines, first line ≥2 delimiters, ≤2 distinct arities, and `(n_email + n_phone)/rows ≥ 0.6` → score `min(1.0, 0.5 + 0.1*rows)`; ≥0.7 escalates to T2 with a hint.

### 6.3 Tier 2 prompt — verbatim

System prompt is fixed and byte-identical every request so vLLM prefix caching serves the prefill:

```
You are AIRLOCK, a local data-egress inspector. You classify a payload that an
employee is about to paste into an external AI service.

You have exactly one job: decide whether this payload contains information that
this company has not already made public.

DEFAULT TO "BENIGN". Blocking a benign paste costs an employee real time and
erodes trust in the control. Only depart from BENIGN when you can quote the
exact characters in the payload that make it sensitive.

BENIGN includes, and you must not block:
  - Questions about programming, tools, maths, writing, or general knowledge,
    even long ones, even ones containing code.
  - Open-source, tutorial, textbook, or documentation code and config.
  - Placeholder, dummy, example, redacted, or test data: "user@example.com",
    "555-0100", "AKIAIOSFODNN7EXAMPLE", "4242424242424242", "XXXX", "<redacted>",
    "your-api-key-here", "changeme", "hunter2", faker-generated names.
  - Information the payload itself shows is already public.
  - A QUESTION ABOUT sensitive data that does not itself contain any.
    "How do I write a regex for a credit card number?" is BENIGN.
  - Public financial data: reported historical earnings, stock prices, filings.

Classify as sensitive ONLY for:
  CREDENTIAL           live secrets: API keys, tokens, private keys, passwords,
                       connection strings with real credentials
  PAYMENT_CARD         real payment card numbers
  GOV_ID               SSN, passport, driver's licence, national ID
  CUSTOMER_RECORD      3+ records identifying real customers or employees
  HEALTH_RECORD        patient-identifiable clinical information
  FINANCIAL_NONPUBLIC  UNRELEASED financials: forecasts, projections, pipeline,
                       ARR/MRR, pre-announcement results, cap tables, compensation
  PROPRIETARY_CODE     internal source or infrastructure config, identifiable by
                       internal hostnames, internal service names, or an explicit
                       internal/confidential marking
  LEGAL_HR             contracts under NDA, litigation, disciplinary or HR matters

Rules:
1. Every non-BENIGN verdict MUST include at least one evidence_span copied
   character-for-character from the payload. If you cannot copy such a span,
   the answer is BENIGN.
2. confidence is the probability that a trained security reviewer would agree
   with your label. Use the full range. If you are unsure, say 0.5, not 0.9.
3. Output only the JSON object.
```

User turn: `<<<PAYLOAD\n{payload}\nPAYLOAD>>>`. Six few-shot exemplars follow the system block, four of them hard negatives: `AKIAIOSFODNN7EXAMPLE` in AWS docs → BENIGN; `4242 4242 4242 4242` in a Stripe debugging question → BENIGN; pandas reading `customers.csv` with no rows → BENIGN; "reported Q2 revenue was $1.2B (from the 10-Q)" → BENIGN; a real-shaped `sk-ant-api03-…` in a `.env` → CREDENTIAL/HIGH; a 12-row `name,email,phone,plan,mrr` block → CUSTOMER_RECORD/HIGH.

T3 (image) prompt: **transcribe, do not interpret** — title, axis labels, legend, column headers, footnotes, watermarks, filenames, tab titles; explicitly *do not read data values off bars or lines*. Then classify, where `FINANCIAL_NONPUBLIC` requires **both** financial vocabulary **and** a forward-looking or internal marker in the transcribed text. This routes around every documented VLM chart failure mode (OCRBench v2 is 54.3 EN — fine-grained reading is not reliable; chrome text is).

### 6.4 Cascade and routing

```
paste
 ├─ CACHE  sha256(payload) seen in `decisions` → replay verdict     (~1 ms)
 ├─ T0     len<40 and no digit and none of {@ : / =}      → ALLOW   (~0.01 ms)
 ├─ T1     deterministic scan                                       (~0.3 ms)
 │           HIGH (Luhn+context | PEM | provider-prefix+entropy) → BLOCK, no LLM
 │           LOW | structural | nothing ─────────────┐
 ├─ T2     Qwen3-4B, guided JSON, span-verified ◄────┘         (~200–400 ms)
 │           p_block ≥ τ → BLOCK  else ALLOW
 └─ T3     images: Qwen3-VL/Holo1.5 transcribe → re-run T1+T2 on OCR text (~0.9–1.6 s)
```

A router, not an AND-cascade: an AND-cascade would cap recall at T1's, which is ~0 for `FINANCIAL_NONPUBLIC`. T1-HIGH is the only tier permitted to block without a model, and it is therefore checksum-gated only — its FPs pass straight through to the total.

Span verification is the highest-leverage guard and runs on every non-BENIGN T2/T3 verdict:

```python
def verify(v, payload):
    if v["label"] == "BENIGN": return v
    spans = [s for s in v.get("evidence_spans", []) if s and s in payload]
    if not spans:
        norm = " ".join(payload.split()).casefold()
        spans = [s for s in v.get("evidence_spans", []) if " ".join(s.split()).casefold() in norm]
    if not spans:
        return {**v, "label":"BENIGN", "severity":"NONE", "policy_clause_id":"NONE",
                "override":"unverified_evidence"}
    return {**v, "evidence_spans": spans}
```

Log every override; report the override rate. For T3, additionally force BENIGN unless `temporal_markers` or `confidentiality_markers` or a T1 hit exists in the transcribed text (`reason:"no_grounded_marker"`).

### 6.5 Confidence and threshold

Do not ship the verbalized `confidence` raw — verbalized confidence is systematically biased upward (zero-shot ECE typically 0.06–0.20). Take the real posterior from `top_logprobs` over the first token of the `label` value, renormalised across the nine allowed labels (all nine are first-token-distinct — **VERIFY-ON-THE-DAY at the 10:45 gate** by dumping the tokenizer output; fallback if two collide is to prefix labels with distinct digits `1_BENIGN`…`9_LEGAL_HR` and strip in post). Then `p_block = 1 − p("BENIGN")`, temperature-scaled by one scalar `T` fitted on a 200-item dev split (`scipy.optimize.minimize_scalar`, bounds (0.05, 10), minimising NLL). Report ECE before/after, 10 equal-width bins, plus a reliability diagram.

Operating points, shipped as a dropdown and a live slider:

| Mode | τ | target recall | target FPR |
|---|---|---|---|
| Audit | 0.30 | ~0.98 | ~3–5% (log only, never block) |
| **Balanced** (default) | **0.55** | ~0.93 | **<1%** |
| Strict | 0.20 | ~0.99 | ~8% |

FPR = FP / N_benign with N = 1000, reported with a Wilson 95% CI (3/1000 → 0.30% [0.10%, 0.88%]; 0/1000 → "below 0.3%" by the rule of three, never "zero"). Threshold is selected on dev, reported on test, and the slider re-thresholds **cached** per-item `p_block` scores so the re-run is exact and instant — state that it is cached, do not imply 1000 fresh inferences.

## 7. Non-Functional Requirements

### 7.1 Latency budgets

All targets are **end-to-end from `preventDefault()` in the content script to verdict rendered in the overlay**, measured with `performance.now()` in `airlock.js` and logged to `inspect_metrics`. Every number ships as a tuple `(metric, percentile, concurrency, input_len, output_len, model, quantization, image resolution, container digest, driver version)`. Median of 3 runs, 2 warm-ups discarded, `--ignore-eos` where benchmarking.

| # | Path | Route | p50 target | p95 target | Hard timeout |
|---|---|---|---|---|---|
| NFR-L1 | **T0 trivial gate** — `len < 40`, no digit, none of `@ : / =` | in-process, no model | **≤ 1 ms** | ≤ 3 ms | n/a |
| NFR-L2 | **T1 text fast path** — regex + Luhn/mod-97 + entropy, HIGH-confidence block or clear | in-process Python, no model | **≤ 5 ms** | **≤ 15 ms** | n/a |
| NFR-L3 | **T2 text LLM path** — Qwen3-4B-Instruct-2507, guided JSON, ≤200 output tokens | vLLM :8002 | **≤ 350 ms** | **≤ 600 ms** | 2500 ms |
| NFR-L4 | **T3 image VLM path** — Holo1.5-7B, `max_pixels=1003520`, ≤8 output tokens | vLLM :8001 | **≤ 900 ms** | **≤ 1600 ms** | 2500 ms |
| NFR-L4b | T3 fast mode — `max_pixels=401408`, `max_tokens=1`+`logprobs` | vLLM :8001 | ≤ 450 ms | ≤ 900 ms | 2500 ms |
| NFR-L5 | **Cheap pre-VLM gate** — 64×64 histogram + Sobel edge density | in-process | ≤ 2 ms | ≤ 5 ms | n/a |
| NFR-L6 | **Instant-block cache hit** — sha256 of payload found in `decisions` | MongoDB point query | ≤ 5 ms | ≤ 20 ms | n/a |
| NFR-L7 | **Sanctioned answer** — Qwen3.6-35B-A3B-NVFP4, first token | vLLM :8000 | TTFT ≤ 1.2 s | TTFT ≤ 3.0 s | none (streamed) |
| NFR-L8 | Blended, at measured escalation rate (~14% reach T2/T3) | router | **≤ 60 ms** | **≤ 600 ms** | 2500 ms |

**10:45 gate pass criterion (NFR-L4 only): p50 ≤ 1.5 s AND p95 ≤ 2.5 s on 20 distinct 1280×720 chart images.** Fail → drop to NFR-L4b (`max_pixels=401408`, `max_tokens=1` + `logprobs=5`, read the logprob margin between the `BLOCK` and `SAFE` first tokens). Fail again → swap weights to `nvidia/Qwen2.5-VL-7B-Instruct-NVFP4` (same `Qwen2_5_VLForConditionalGeneration` code path, ~2× prefill).

**VERIFY-ON-THE-DAY.** NFR-L4 is derived arithmetic, not measurement: ViT encode ≈ 6.3 TFLOP + LLM prefill ≈ 20.9 TFLOP at 20–35% MFU on ~125 TFLOPS BF16 dense → 0.6–1.1 s prefill; decode is bandwidth-bound at 15.2 GB ÷ 273 GB/s ≈ 65–75 ms/token. **There is no first-party VLM image-throughput measurement on GB10 anywhere — this is the single largest unverified number in the project.** It is A's 10:45 gate and nothing downstream may assume it before A reports.

Mandatory latency hygiene:
- **Warm-up is not optional.** First request triggers torch.compile/inductor: **25–57 s**. A systemd-style warm loop fires a 1×1 px image with `max_tokens=3` at each server the moment `/health` returns 200, and again at 16:30 demo freeze. A cold first paste on stage is a lost demo.
- **CUDA graphs stay ON.** Never pass `--enforce-eager` on the interactive path. Requires driver **580.x**.
- **Prefix caching stays ON.** System prompt + 6 few-shot exemplars are byte-identical every call. But **benchmark with distinct images** — vLLM V1 hashes image content into prefix-cache keys, so repeated identical images produce a fraudulent number.
- **No speculative decoding on the VLM.** MTP amortises over long generations; we emit 1–8 tokens. Keep `{"method":"mtp","num_speculative_tokens":3}` on the 35B only.
- Client-side downscale to long edge ≤1024 px in `shrinkToB64()` before the payload crosses the wire. B tells A the exact max edge so the sweep uses the same input distribution.

### 7.2 Throughput

| # | Requirement |
|---|---|
| NFR-T1 | Text path sweep at `c ∈ {1, 8, 64, 256}`, `--num-prompts max(32, c×4)`, input 512 / output 256. Expect strong scaling (published GB10 precedent: 5.79 → 695 tok/s at c=256 = 120×). |
| NFR-T2 | Vision path sweep at `c ∈ {1, 2, 4, 8, 16}`, `--dataset-name random-mm --random-mm-bucket-config '{(720, 1280, 1): 1.0}'`, output 8. **Expect 1.5–2.5× from c=1 to c=8, then flat — vision is prefill-bound. State this on the slide before showing it.** Claiming linear vision scaling to a Dell/NVIDIA judge is instant credibility loss. |
| NFR-T3 | Images/sec = `num_prompts ÷ wall-clock` at the largest c where E2E p95 ≤ 2.5 s. Publish as *"First measured VLM image-inspection throughput on NVIDIA GB10."* |
| NFR-T4 | Run the vision sweep **twice**: once idle, once with the 35B under c=8 load. Publish both columns. Decode is bandwidth-bound and all processes share 273 GB/s; a benchmark that shows its own degradation is the most credible artifact in the submission. |
| NFR-T5 | FP-rate harness must complete **1000 benign + 400 sensitive items in ≤ 15 min wall-clock**, run direct over HTTP (curl/Python), never through Chrome. Running by 13:00. |
| NFR-T6 | Escalation rate (% of pastes reaching T2/T3) is instrumented and reported — it is the seats-per-box multiplier. |
| NFR-T7 | Seats per box = `min(seats_vision, seats_text)`, always stating which binds. `seats_vision = (R_img × 3600) / (20 × f_img)`; `seats_text = (R_txt × 3600) / (20 × (1 − f_img))`; P=40 pastes/employee/8h day, peak factor 4×. Every assumption on the slide. Bracketed values filled from A's run — **do not invent them**. |

### 7.3 Memory ceilings — the arithmetic

Calibration constant: `--gpu-memory-utilization` is a fraction of the **whole shared 128 GB pool**, not a VRAM partition. Anchor: 0.85 → 0.40 frees ~58 GB ⇒ **0.45 ≈ 58 GB ⇒ 1.00 ≈ 129 GB ⇒ 0.10 ≈ 12.9 GB.**

| Process | Setting | ≈ GB | Contents |
|---|---|---|---|
| vLLM text `:8000` Qwen3.6-35B-A3B-NVFP4 | `--gpu-memory-utilization 0.40` | 51.6 | weights ~22 + FP8 KV ~26 + graphs/act ~3 |
| vLLM vision `:8001` Holo1.5-7B BF16 | `--gpu-memory-utilization 0.24` | 31.0 | weights ~16.5 + KV ~9 + MM caches ~2 + graphs ~3 |
| vLLM classifier `:8002` Qwen3-4B-Instruct-2507 | `--gpu-memory-utilization 0.10` | 12.9 | weights ~8 + KV ~3 + graphs ~2 |
| **Sum reserved by CUDA** | **0.74** | **~95.5** | **hard ceiling 0.85** |
| MongoDB container | `--memory=6g --memory-swap=6g --cpus=4` | 6.0 | mongot JVM ≈ 25% of cgroup ≈ 1.5 GB heap |
| bge-small + bge-reranker (CPU, ONNX Runtime) | — | 1.7 | 20 Arm cores, **no GPU process** |
| OS + GNOME + docker + page cache | — | ~14 | ~5 in headless serving mode |
| **Total** | | **~117** | vs ~121 GiB CUDA-visible, **126.5 GB host crash ceiling** |

**Headroom is ~4 GB. That is too thin.** Two committed reductions, in order:

1. **Default config for the demo is two servers, not three** — `0.40 + 0.24 = 0.64` (~82.6 GB), total ~104 GB, **~17 GB free**. T2 classification runs on the 35B at `:8000` with the same guided-JSON schema. **Ship this.**
2. Only if A's 10:45 measurement shows the 35B classifier missing NFR-L3 p95 ≤ 600 ms, add `:8002` at 0.10 **and** drop text to 0.34 (43.9 GB), giving 0.34 + 0.24 + 0.10 = **0.68** (~87.7 GB). Never 0.74 with three servers plus Mongo.

Flex config for the throughput slide only, with no browser in the loop and Mongo stopped: `0.48 + 0.30 = 0.78`.

**Hidden allocation that is not reported as GPU memory** — the highest-value line in this section: vLLM's multimodal caches default to 4 GiB and 8 GiB and are **duplicated per API process and per engine-core process**. They live in "CPU RAM," which on a unified-memory box is *the same physical pool*. Left at defaults across two servers this silently eats 15–20 GB nobody accounts for. Therefore, mandatory on the vision server:

```
-e VLLM_MM_INPUT_CACHE_GIB=2 ... --mm-processor-cache-gb 1
```

MongoDB arithmetic: mongot documents *"up to 25% of total available system memory for the JVM heap, up to 32GB (with 128GB of system memory)"* — this box exactly. Unconstrained it targets **32 GB**. `--memory=6g` relies on JVM `UseContainerSupport` (default since JDK 10) resolving "total available system memory" to the cgroup limit → ~1.5 GB heap. **VERIFY-ON-THE-DAY, first thing at 10:00, five-minute check:** `docker stats airlock-mongo` and `docker exec airlock-mongo grep -i -E 'Xmx|heap' /tmp/mongot.log`. **Fallback if the cgroup cap does not take:** add `-e JAVA_TOOL_OPTIONS="-Xms1g -Xmx2g"` (undocumented on this image; most JVM launchers honour it) and re-verify. If neither works, run `mongo:8` without mongot and use the client-side RRF fallback for retrieval.

Non-GPU ceilings:
- Chrome content script: images downscaled to ≤1024 px long edge, JPEG q=0.82, before base64. `--limit-mm-per-prompt '{"image":1,"video":0}'` caps a hostile 40-image paste at the API boundary.
- `--limit-mm-per-prompt '{"image":0,"video":0}'` on the **text** server: a malformed request can never drag the 35B into a vision prefill.
- MV3 service worker holds no state; anything crossing a wake goes to `chrome.storage.session`.
- Evidence crops stored as `bson.Binary` in the decision doc, not GridFS, not base64. Full-resolution originals are **never** persisted — storing the data you just blocked from leaving is indefensible for a DLP product.

### 7.4 Failure behaviour

**The rule: every layer fails closed. Deny-by-default is the product, so it must also be the failure mode.**

| Failure | Behaviour | Rationale |
|---|---|---|
| `/v1/inspect` unreachable, non-200, or >2500 ms | **BLOCK**, `{action:'block', label:'airlock_unavailable', reason:'Inspector unreachable — deny by default'}` | Narratively identical to OpenShell's egress denial. A wedged backend on stage produces a block screen, not a dead demo. |
| vLLM cold / still loading | **BLOCK** (same path) | Reads as intentional. |
| MV3 `sendResponse` never fires (missing `return true`) | client timeout → **BLOCK** | Check `return true` in `sw.js` first, always — it is the #1 MV3 bug and it looks exactly like model slowness. |
| Extension context invalidated (extension reloaded under an open tab) | `chrome.runtime.id` guard → fall back to direct `fetch`; if that fails → **BLOCK** | |
| MAIN-world `fetch` patch: no reply in 3000 ms | **BLOCK** — synthetic `403 {"error":"policy_denied","by":"airlock"}` | Same JSON shape OpenShell emits. Beat 5 for free. |
| T2 returns a non-BENIGN label with no `evidence_span` present verbatim in the payload | **force BENIGN**, `override:"unverified_evidence"`, logged | **The one deliberate fail-open, and it is load-bearing.** The model could not point at anything real. Report the override rate — it is a mechanism, not a vibe, and no other team will have it. |
| T3 non-BENIGN with no `temporal_markers`, no `confidentiality_markers`, and no T1 hit over the OCR text | **force BENIGN**, `override:"no_grounded_marker"` | Same principle on the image path. |
| MongoDB down or search index not `queryable` | Detector still runs (T1 + T2 are stateless); the instant-block cache and clause retrieval degrade to `policy.yaml` static enum. **Never silently allow.** | A `$vectorSearch` against a non-queryable index returns **empty results, not an error** — poll `$listSearchIndexes` for `status:"READY"` as a blocking step in the seed script. |
| mongot misbehaves | Client-side RRF (k=60) emitting identical `score`/`scoreDetails` shape | Swap the backend, don't touch B's code. |
| Change stream `invalidate` after a re-seed | Reconnect with `startAfter`, not `resumeAfter` | `resumeAfter` cannot resume past an invalidate; the live console dies permanently otherwise. We re-seed several times today. |
| Everything above fails | `declarativeNetRequest` session rule blocking `||chatgpt.com/backend-api/conversation` | Enforced in the network stack — works with the SW asleep and the content script broken. A switch, not an inspector. This is the hard floor. |

Fail-**open** is permitted in exactly two places, both listed above (span verification, marker grounding), both logged, both reported as a rate. Nowhere else.

### 7.5 Host-freeze safety rules — normative

**On this box, OOM is not an exception. Unbounded allocation hangs the whole host — no SSH, no ping (pytorch/pytorch#174358). A freeze at 14:00 costs the hackathon.** These are hard constraints, not guidance.

| # | Rule |
|---|---|
| NFR-S1 | **Only engineer A may start, stop, or restart a GPU process.** B and C never run `docker run` with `--gpus`, never `vllm serve`, never a bare `python` that imports torch with CUDA. B and C consume `:8000`/`:8001` over HTTP only. Violations are the single most likely cause of a total loss of the day. |
| NFR-S2 | Before **every** vLLM launch, A runs the pre-flight, in this order: `sudo swapoff -a` → `sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'` → `nvidia-smi --query-gpu=driver_version --format=csv` (**must read 580.x — 590.x causes CUDAGraph deadlocks**) → `free -h` (record baseline available). |
| NFR-S3 | Summed `--gpu-memory-utilization` across all live vLLM processes **must never exceed 0.85**. Committed demo value is **0.64**. Community reports OOM after ~1 h at 0.90. A keeps a written running total on the whiteboard; it is updated *before* a launch, not after. |
| NFR-S4 | Every GPU process launches with an explicit `--gpu-memory-utilization`. A launch without it is forbidden — the default will not respect the co-resident process. |
| NFR-S5 | Mandatory env on every vLLM container: `VLLM_MARLIN_USE_ATOMIC_ADD=1`, `VLLM_USE_FLASHINFER_MOE_FP4=0`, `CUTE_DSL_ARCH=sm_121a`. `--moe-backend marlin` is mandatory on the NVFP4 MoE or it emits garbage on sm121. Vision uses `--attention-backend TRITON_ATTN` (FlashInfer lacks SM121) and the SM121-patched image `hellohal2064/vllm-dgx-spark-gb10`; stock images fail `"SM121 not supported"` for VLMs. |
| NFR-S6 | MongoDB starts with `--memory=6g --memory-swap=6g --cpus=4` **before** any model loads, and heap is verified per §7.3 before A launches server #1. |
| NFR-S7 | `--max-num-seqs` stays in **4–8**. Above ~4 concurrent decode streams, per-token bandwidth cost outweighs batching and TTFT spikes. |
| NFR-S8 | **CUDA MPS is prohibited.** Measured on this exact box: +10% aggregate throughput, **mean TTFT 16,726 ms → 27,142 ms (+62%)**. Airlock is a keystroke-path product. Cite the rejection in the writeup. |
| NFR-S9 | **vLLM sleep mode is prohibited.** Level 1 "offloads weights to CPU RAM" — on GB10 that is the same DRAM. You free nothing physical; you move a pointer. Architecturally meaningless here. |
| NFR-S10 | **No third GPU process for embeddings or reranking.** `bge-small` (67 MB fp16) and `bge-reranker-base` (560 MB fp16) run on the 20 Arm cores via ONNX Runtime. Each extra vLLM process costs a CUDA context (~300–500 MB), its own compile warm-up, and SM time — a bad trade for 1.7 GB. |
| NFR-S11 | Nothing large is loaded on the host outside a container after 16:00. Feature freeze is also an allocation freeze. |
| NFR-S12 | **`nvidia-smi` cannot show a memory bar on this box** — NVIDIA documents `Memory-Usage: Not Supported` for an iGPU with no framebuffer. Memory state is read from `nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv` plus `/proc/meminfo` `MemAvailable` and `SwapFree`. Any slide showing a VRAM bar loses the technical-execution axis in one second. |
| NFR-S13 | If `MemAvailable` drops below **8 GB**, A stops the vision server immediately. Recovery is `docker stop`, then `drop_caches`, then relaunch — not "wait and see". |
| NFR-S14 | Headless serving mode (stopping GNOME/display-manager/snap) reclaims **10–15 GB** and is the designated emergency lever if NFR-S13 fires twice. It is *not* pre-emptive: it costs the on-screen demo surface. |
---


## S1. How the stack maps onto Airlock

### S1.1 The thesis, in one sentence

Airlock is a policy-enforcement product. OpenShell is a policy engine. We are not putting a policy product *on top of* a policy engine as a compliance wrapper — we are making the same decision at two layers of the same stack, and letting the judges watch both layers deny in the same log tail.

> **OpenShell blocks bytes leaving the container. Airlock blocks meaning leaving the laptop. Same fail-closed posture, same deny-by-default default, two layers, one screen.**

The recursion is the differentiator: **the agent that polices egress is itself running under an egress policy it cannot escape, and it can read — but not rewrite — the rules it is bound by.** That last clause is not rhetoric; it is `nemoclaw <name> policy explain --json`, a redacted, agent-consumable view of the policy, refreshed automatically into `/sandbox/.openclaw/workspace/POLICY.md`, with rule bodies, credential metadata and binary allowlists deliberately withheld.

### S1.2 What each layer actually does — real work, not box-ticking

| Layer | Real work it does for Airlock | Would we still need it if we cut it? |
|---|---|---|
| **NemoClaw** (host, TS, Apache-2.0, alpha) | Brings the whole stack up in one command; validates provider+model **before** creating the sandbox; owns the OpenShell version pin; supplies the `local-inference` policy preset that authorises our second (vision) model on exactly one method and one path; supplies `shields` (config lock + time-boxed break-glass + audit trail); supplies `policy explain --json`, whose output we consume *inside our own verdict payload*; supplies `logs --follow`, which interleaves agent output and OpenShell policy denials in one stream. | Yes. Without it we hand-roll gateway bring-up, provider registration and image selection, and we lose `shields` and `policy explain` — which are two of our four best demo beats. |
| **OpenShell** (host daemon + sandbox, Rust, Apache-2.0, ALPHA) | Deny-by-default egress enforced at the proxy, not in application code; the `policy_denied` JSON artifact; OCSF v1.8.0 audit log including `class_uid: 6003` API:INFERENCE records that name the provider URL of **every** inference call; the single-live-inference-route constraint that makes `inference.local` a *whitelist of request shapes*, not just a hostname; hot-reloadable `network_policies` and (stretch) `network_middlewares`. | No. This is the load-bearing layer. It is what converts "we don't call the cloud" from a claim into a machine-checkable fact. |
| **OpenClaw** (in sandbox, TS, MIT, `openclaw@2026.7.1-2`, Node ≥22.22.3) | The **sanctioned answer** — the employee's blocked question gets answered by a local agent that has no network tools and cannot see the confidential payload; the verdict *explanation* skill; the `show_widget` verdict card; the automations ledger. | Partly. See §S3.4 — we are explicit about where OpenClaw is genuinely better than a FastAPI handler and where it is ceremony. We keep the ceremony thin rather than pretending. |

### S1.3 Host vs sandbox — the honest architecture

**This is the question a judge will ask, so we answer it before they do.**

The clipboard lives on the host. A Wayland/X11 paste event cannot be observed from inside an OpenShell sandbox, and we would not want it to be — that would mean the sandbox had display-server access. So:

- **Airlock's interceptor and classifier run on the host.** They must.
- **The agent runs in the sandbox.** It must.

That is not a compromise; it is the correct split, and it is the same split every real DLP product makes (agent on the endpoint, decision engine hardened). What makes it more than an assertion is that **the same classifier binary is called from two places**: once by the host-side clipboard hook, and once — via the OpenShell supervisor-middleware gRPC contract — on the sandbox's own HTTP request path. One classifier, two call sites, one verdict schema, one audit ledger.

```
════════════════════════════ HOST (DGX Spark GB10, 128 GB unified, sm_121, driver 580.x) ═════════════

  [B] airlock-clip                      [C] airlockd            ← ONE classifier core
  ┌────────────────────┐                ┌──────────────────────────────────────────────┐
  │ paste hook         │  POST /v1/     │  HTTP  :9100  (host clipboard call site)     │
  │ clipboardData:     │──inspect──────▶│  gRPC  :50051 (OpenShell middleware call site)│
  │  · text string     │   {payload}    │                                              │
  │  · image blob      │◀──verdict──────│  tier 0  size/type/regex + bge-small          │
  └────────────────────┘                │  tier 1  text  → :8000  (guided JSON)         │
        │                               │  tier 2  image → :8081  (VLM)                 │
        │ BLOCK → re-route question     │  → verdict{allow|block|redact, spans, cite}    │
        │         to sanctioned agent   │  → append to audit ledger (SQLite/Mongo)       │
        ▼                               └──────────────────────────────────────────────┘
  [B] Airlock UI (localhost)                          │                    │
                                                      ▼                    ▼
  [A] vLLM (docker, hellohal2064/vllm-dgx-spark-gb10 — SM121-patched)
      :8000  nvidia/Qwen3.6-35B-A3B-NVFP4   ~22 GB   ← NemoClaw MANAGED inference route
      :8081  Hcompany/Holo1.5-7B            ~16.5 GB ← authorised by `local-inference` preset
      (:8000 also serves BAAI/bge-small-en-v1.5 embeddings)

  nemoclaw CLI ──orchestrates──▶ openshell gateway ──isolates and runs──▶ ┐
                                 (127.0.0.1:18080)                        │
═══════════════════════════════════════════════════════════════════════════│══════════════════════════
                                                                           │  deny-by-default egress
                        ┌──────────────────────────────────────────────────▼───────────────────────┐
                        │  OpenShell sandbox  "airlock"        (--no-gpu, run_as_user: sandbox)    │
                        │  OpenClaw 2026.7.1-2 · Node 22 · /usr /lib /etc read-only                │
                        │                                                                          │
                        │   agent "answerer"   tools.allow: read, view_image, llm-task             │
                        │                      NO web_fetch · NO browser · NO message              │
                        │   skill  airlock-verdict-explainer   (SKILL.md, §S3.3)                   │
                        │   automation  airlock-ledger-sweep   (SQLite-backed, run history)        │
                        │   file  /sandbox/.openclaw/workspace/POLICY.md  ← policy explain --write │
                        │                                                                          │
                        │   ALLOWED EGRESS (the entire list):                                      │
                        │     inference.local:443           → host :8000, managed route            │
                        │     host.openshell.internal:8081  → POST /v1/chat/completions ONLY       │
                        │     clawhub.ai:443, registry.npmjs.org:443  (build-time; excluded later) │
                        │   EVERYTHING ELSE → 403 policy_denied                                    │
                        │     api.openai.com ✗  api.anthropic.com ✗  github.com ✗                  │
                        └──────────────────────────────────────────────────────────────────────────┘
```

**Why the sandbox does not get the GPU:** `--gpu` is experimental, the base image ships no CUDA libraries, and GPU sandboxes move `/proc` from read-only to read-write. vLLM is on the host; the agent container needs none of it. `--no-gpu` is the correct and defensible choice, and we say so.

---

## S2. OpenShell — policy as the product

### S2.1 The three policy artifacts we ship

All three are checked into the repo under `policy/` and are submission evidence.

**(1) `policy/airlock-egress.yaml`** — a NemoClaw custom policy preset. This is Airlock's egress contract as a reviewable object.

```yaml
preset:
  name: airlock-egress
  description: "Airlock inspection plane: host-local vision model only, one verb, one path."
network_policies:
  airlock_vlm:
    name: airlock_vlm
    endpoints:
      - host: host.openshell.internal
        port: 8081
        protocol: rest
        enforcement: enforce
        allowed_ips: [10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16]
        rules:
          - allow: { method: POST, path: "/v1/chat/completions" }
        deny_rules:
          - { method: "*", path: "/v1/models/**" }
    binaries:
      - { path: /usr/local/bin/openclaw }
      - { path: /usr/bin/python3 }
```

Authoring rules that bite: `preset.name` must be a lowercase RFC-1123 label; catch-alls (`*`, `0.0.0.0/0`, `::/0`) are rejected at load; wildcards are permitted **only in the first DNS label**; and **an endpoint with no matching `binaries` entry authorises nothing**. Get the real interpreter path first:

```bash
nemoclaw airlock exec -- which python3
nemoclaw airlock exec -- which openclaw
```

Apply, with the dry run shown to the room:

```bash
nemoclaw airlock policy add --from-file ./policy/airlock-egress.yaml --dry-run   # prints exact scope
nemoclaw airlock policy add --from-file ./policy/airlock-egress.yaml --yes
nemoclaw airlock policy list          # ours shows as [user-added]
```

Presets are recorded **with the sandbox**, content and all, and replayed on rebuild and snapshot-restore. That is a genuine reproducibility claim.

**(2) `policy/exclusions.md` + the exclusion commands** — the move almost nobody makes. Every other team will *add* egress. We *remove* NVIDIA's own baseline:

```bash
nemoclaw airlock policy list                       # VERIFY-AT-10:00 — read the exact rule names
nemoclaw airlock policy exclude <nvidia_api_rule> --dry-run
nemoclaw airlock policy exclude <nvidia_api_rule> --force
nemoclaw airlock policy exclude <npm_rule>        --force   # after skills are installed
```

`policy exclude` previews the egress *and the named supported features that will stop working*, refuses any entry lacking a reviewed feature-impact disclosure, binds a versioned exclusion record to the reviewed baseline content and active agent, and **replays it on every rebuild, failing closed if the baseline or agent changed**. `managed_inference` cannot be excluded — that is the `inference.local` route, and we want it.

> **VERIFY-AT-10:00:** the exact baseline rule *names* (the brief and the NemoClaw research disagree on whether the baseline is five endpoints or seven policy groups — the five-endpoint list is NemoClaw's, the larger list including `github.com` and `api.anthropic.com` is bare OpenShell's `sandboxes/base/policy.yaml`). Read them off `nemoclaw airlock policy list`, do not guess. **Fallback if `policy exclude` refuses**: leave the baseline intact and rely on the fact that `integrate.api.nvidia.com` is never called — then prove it from the OCSF log (§S2.4), which is evidence rather than configuration and is arguably stronger anyway.

**(3) `policy/openclaw-policy.jsonc` + `openclaw policy check --json`** — config-level attestation, hash-attested.

```bash
openclaw plugins enable policy
openclaw policy check --json --severity-min error | tee evidence/openclaw-policy-check.json
openclaw policy compare --baseline policy/openclaw-policy.jsonc --json
```

```jsonc
{
  "models":  { "providers": { "deny": ["openai","anthropic","openrouter","google","groq","deepseek","mistral"] } },
  "network": { "privateNetwork": { "allow": false } },
  "gateway": { "exposure": { "allowNonLoopbackBind": false, "allowTailscaleFunnel": false },
               "auth": { "requireAuth": true },
               "controlUi": { "allowInsecure": false },
               "remote": { "allow": false } },
  "dataHandling": { "sensitiveLogging": { "requireRedaction": true },
                    "telemetry": { "denyContentCapture": true },
                    "memory": { "denySessionTranscriptIndexing": true } },
  "tools":   { "elevated": { "allow": false },
               "exec": { "allowHosts": ["sandbox"] },
               "fs": { "requireWorkspaceOnly": true } }
}
```

A clean check emits policy, evidence, findings and **attestation hashes**. Cost: ~20 minutes. **Honest caveat we state on the slide:** this plugin verifies *config-level conformance only* — it does not enforce tool calls or rewrite runtime behaviour at request time. The runtime enforcement is OpenShell's proxy; the policy plugin is the attestation of the posture around it. Saying that ourselves is worth more than overclaiming and being caught.

### S2.2 Hot reload — what moves at runtime and what does not

Five top-level sections. **Static, locked at sandbox creation:** `filesystem_policy`, `landlock`, `process`. **Dynamic, hot-reloadable with no restart:** `network_policies`, `network_middlewares`.

```bash
# full replace — required for static sections and for network_middlewares
openshell policy set airlock --policy ./policy/full.yaml --wait

# incremental merge — network_policies only, atomic, one revision per command
openshell policy update airlock --add-endpoint api.github.com:443:read-only:rest:enforce \
                                --binary /usr/bin/curl --wait
openshell policy update airlock --add-deny 'api.github.com:443:POST:/admin/**' --wait
openshell policy update airlock --remove-rule airlock_vlm --wait
openshell policy update airlock --add-endpoint x.com:443 --dry-run    # preview, no gateway call

openshell policy get  airlock --full          # effective, including provider-composed
openshell policy get  airlock --base          # editable base only
openshell policy list airlock --limit 50      # revision history + load status
```

`--wait` exit codes: **0** loaded, **1** failed, **124** timeout (60 s default). `--wait` and `--dry-run` are mutually exclusive. Endpoint grammar: `host:port[:access[:protocol[:enforcement[:options]]]]`.

**The single highest-leverage flag in this whole section: `enforcement: audit`.** It logs the violation and lets traffic through. Run one endpoint in audit mode and you can show a live feed of everything Airlock *would* have blocked with zero risk of breaking the demo. That is the usefulness slide.

Inference route is also hot — credential and route changes refresh into running sandboxes in ~5 seconds, no recreate.

### S2.3 Triggering the denial artifact deliberately

Demo beat 4 is "a raw `policy_denied` JSON on screen". Here is exactly how to produce it.

**L4 denial (CONNECT tunnel):**

```bash
nemoclaw airlock exec -- curl -sS https://api.openai.com/v1/models
```
```
curl: (56) Received HTTP code 403 from proxy after CONNECT
```
```json
{
  "error": "policy_denied",
  "detail": "CONNECT api.openai.com:443 not permitted by policy",
  "reason": "no matching policy"
}
```

**L7 denial (REST-inspected — the prettier one, body reaches the client directly):**

```bash
nemoclaw airlock exec -- curl -sS -X POST https://host.openshell.internal:8081/v1/embeddings \
  -H 'Content-Type: application/json' -d '{"input":"x"}'
```
```json
{"error":"policy_denied","detail":"POST /v1/embeddings not permitted by policy"}
```

Full `error` enum: `policy_denied` · `middleware_denied` · `middleware_failed` · `ssrf_denied` · `upstream_unreachable` (502).
`status_detail` strings worth recognising on stage: `no matching policy` · `resolves to always-blocked address` · `port <n> is a blocked control-plane port` · `l7 deny`.

**Rehearse the OpenAI one.** `api.openai.com` denied, on screen, from the box that is running our agent, is the answer to "how do I know your agent isn't the leak?"

### S2.4 Tailing policy decisions into a live console

Two channels. Turn both on at 10:20.

```bash
# (a) shorthand, streamed over gRPC from the gateway
openshell logs airlock --tail --source sandbox
openshell logs airlock --tail --source sandbox --level warn
```
```
[1775014132.690] [sandbox] [OCSF] NET:OPEN [MED] DENIED /usr/bin/curl(64) -> api.openai.com:443 [policy:- engine:opa] [reason:no matching policy]
[1775014133.910] [sandbox] [OCSF] API:INFERENCE [INFO] Success nvidia/Qwen3.6-35B-A3B-NVFP4 via http://host.openshell.internal:8000/v1 701ms [POST /v1/chat/completions]
```

```bash
# (b) full OCSF v1.8.0 JSONL — the one for the projector and for the submission
openshell settings set --global --key ocsf_json_enabled --value true    # ~10s poll, no restart
nemoclaw airlock exec -- sh -c 'tail -f /var/log/openshell-ocsf.$(date +%F).log' \
  | jq -c 'select(.action=="Denied" or .class_uid==6003)'
```

Class UIDs: `4001` NET · `4002` HTTP · `1007` PROC · `2004` FINDING · `5019` CONFIG · `6002` LIFECYCLE · **`6003` API:INFERENCE**.

**And the single best one-command view, NemoClaw's:**

```bash
nemoclaw airlock logs --follow
```
> reads both agent gateway output **and OpenShell audit events, so policy denials appear alongside the gateway log stream.**

One pane, agent verdicts and policy denials interleaved. That is the project's thesis rendered as a log tail. **Left pane on the projector all day.**

The gateway's log buffer is in-memory and lost on restart; the in-sandbox files are the complete record. Copy them out before 17:30 for the submission.

### S2.5 ⭐ Making "no remote LLM calls" a POLICY-ENFORCED fact — the local-first axis

This is the highest-value item in the section. Rule 02 says *"no remote LLM/API calls in the agent runtime path."* Every other team will assert this in prose. We enforce it in four independent, stacking layers and hand the judges a log.

**Layer 1 — deny-by-default egress means no remote LLM host is reachable at all.** No allow rule names `api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com`, or `integrate.api.nvidia.com`. There is nothing to match, so the proxy returns 403 `no matching policy`. This is enforced at the proxy/kernel boundary, outside the sandbox, and **code inside the sandbox cannot rewrite it** — `network_policies` are gateway state, mutated only through the host CLI.

**Layer 2 — `inference.local` is a whitelist of request *shapes*, not a hostname.** The Privacy Router is a named first-class OpenShell component: *"Privacy-aware LLM routing that keeps sensitive context on sandbox compute."* It TLS-terminates, parses, matches known inference patterns, **strips sandbox-supplied credentials**, forwards only an allowlisted header set, injects the *gateway's* credentials, and rewrites the model. From `examples/local-inference/README.md`, verbatim: **"Non-inference requests are denied."** Matched patterns are exactly: `POST /v1/chat/completions`, `POST /v1/completions`, `POST /v1/responses`, `POST /v1/embeddings`, `GET /v1/models[/*]`.

**Layer 3 — the route is gateway-scoped and set from outside.** One provider + one model define inference for every sandbox on the gateway. The sandbox's own `model` and `api_key` fields are **discarded before anything leaves**. Even a fully compromised agent cannot repoint inference.

```bash
openshell provider create --name gb10-vllm --type openai \
  --credential OPENAI_API_KEY=unused \
  --config OPENAI_BASE_URL=http://host.openshell.internal:8000/v1

openshell inference set --provider gb10-vllm --model nvidia/Qwen3.6-35B-A3B-NVFP4 --timeout 300
openshell inference get
```

`--timeout` is seconds, default 60. **Set it to 300.** Vision prefill on the GB10 will exceed 60 s under load and you will lose the demo to a timeout rather than to a bug.

**Layer 4 — the evidence.** Every `inference.local` call emits OCSF **API Activity `class_uid: 6003`** with the `ai_operation` profile:

```json
{"class_uid":6003,"class_name":"API Activity","api":{"operation":"POST /v1/chat/completions"},
 "ai_model":{"name":"nvidia/Qwen3.6-35B-A3B-NVFP4","ai_provider":"http://host.openshell.internal:8000/v1"},
 "metadata":{"profiles":["container","host","ai_operation"]},"status":"Success","unmapped":{"latency_ms":701}}
```

```bash
# THE Rule 02 evidence command — run at 17:30, paste output into the submission
jq -r 'select(.class_uid==6003) | .ai_model.ai_provider' \
  evidence/openshell-ocsf.$(date +%F).log | sort | uniq -c
```

Expected output: one line, `host.openshell.internal`, count N. Zero other providers. Zero denied-egress events to any cloud LLM host. **That is machine-checkable evidence that no remote LLM was called — not an assertion in a slide.** It is the strongest single artifact available to any team in the room today.

**Honest limit, stated plainly:** layers 1–3 govern the *sandbox*. The host-side classifier calls vLLM on loopback and is outside OpenShell's enforcement scope entirely — no policy engine constrains a host process. Our honest claim there is architectural, not enforced: *the classifier binds only to `127.0.0.1`, links no cloud SDK, and the host runs with ethernet unplugged at 17:50 for the last demo beat.* The unplug **is** the host-side proof. Do not blur the two.

### S2.6 Stretch — Airlock as a supervisor middleware (Tier A)

If time allows, Airlock stops being a script that calls OpenShell and becomes an OpenShell policy component. Four gRPC RPCs on `service SupervisorMiddleware` (`proto/supervisor_middleware.proto`): `Describe`, `ValidateConfig`, `EvaluateHttpRequest` (the hot path), `EvaluateWebSocketSession`.

`EvaluateHttpRequest` hands us, per request: originating binary + PID + ancestors, target host/port/method/path, headers (credentials already stripped), and **`body` up to 4 MiB buffered** — a base64 PNG arrives intact. We return `DECISION_ALLOW` / `DECISION_DENY`, an optional replacement `body` (redact and forward), and `reason_code` (64 bytes, `^[a-z][a-z0-9_]*$`, **returned to the requester** — free-form `reason` is discarded).

```toml
# gateway TOML — static, requires gateway restart
[[openshell.supervisor.middleware]]
name = "airlock"
grpc_endpoint = "http://host.openshell.internal:50051"
allow_insecure_transport = true      # dev only
max_payload_bytes = 4194304
timeout = "30s"                      # DEFAULT IS 500ms — this line is mandatory
```

```yaml
network_middlewares:
  airlock-dlp:
    name: Airlock local DLP
    middleware: airlock
    order: 10
    config: { mode: deny, classifier: holo1.5-7b }
    on_error: fail_closed
    endpoints:
      include: ["**.openai.com", "claude.ai"]
      exclude: ["inference.local"]
```

Two hard operational rules: **start `airlockd` before the gateway** (the gateway calls `Describe` at startup and refuses to start if unreachable), and **restart the gateway after any registration change**.

> **VERIFY-AT-10:00 (hard gate):** the middleware docs are published against OpenShell *latest* (0.0.111), but NemoClaw's blueprint pins `min == max == 0.0.106`. **Do not run `uv tool install -U openshell`** — NemoClaw rejects a stable version above its maximum. Test support on a throwaway sandbox:
> ```bash
> nemoclaw airlock status --json | jq .openshellVersion
> printf 'version: 1\nnetwork_middlewares: {}\n' > /tmp/mw-probe.yaml
> openshell policy set <throwaway> --policy /tmp/mw-probe.yaml --wait   # INVALID_ARGUMENT ⇒ unsupported
> ```
> **Fallback:** drop Tier A entirely and stay on Tier B (§S2.1–S2.5). Tier B alone already beats every team that treats OpenShell as a compliance box. Decision gate: **13:00, no later.**

**The timeout trap** kills this if you ignore it: default 500 ms, max 30 s, and a 7B VLM prefill on an image will not finish in 500 ms. Mitigations in order: set `timeout = "30s"`; two-tier classify (sub-100 ms bge-small + regex + size heuristics decides most requests, escalate to the VLM only for images and near-threshold text); pre-warm the model and keep the vLLM connection hot; keep `on_error: fail_closed` so a timeout **blocks**, which is the correct failure for a DLP tool. If it fires on stage, say so out loud and call it the design.

---

## S3. OpenClaw — the agent that does real work

### S3.1 What OpenClaw does that a plain FastAPI service could not

Four things. We claim these four and no more.

1. **The sanctioned answer comes from an agent that structurally cannot leak.** `tools.allow` is enforced **before the model call** — "if policy removes a tool, the model does not receive that tool's schema for the turn." The answerer never sees a `web_fetch` or `browser` schema. A FastAPI service can *decline* to call out; an OpenClaw agent under tool policy *cannot be asked to*. That is a stronger claim and it is one config line.
2. **Two-agent isolation, declaratively.** The component that reads the confidential payload cannot speak; the component that speaks never sees it. In FastAPI that is a code-review promise. Here it is enforced config, per-agent, with separate workspaces and separate SQLite session histories.
3. **`llm-task` is a documented, enforced zero-tool inference primitive.** JSON-only output, schema-validated, **no tools** ("the selected runtime must expose a literal empty model-callable tool surface; OpenClaw rejects tool-shaped results instead of treating them as task output"), no session reuse, no channel delivery, **no provider fallback**, and it fails closed *before inference* if the harness cannot do isolated completion. Combined with `llm.allowedCompletionModels`, that is a machine-enforced statement of Rule 02 at the application layer.
4. **`show_widget` gives us an offline, themed, PNG-exportable verdict card for free.** Opaque origin, strict CSP, bundled icons, **"widget scripts cannot reach the Control UI, the Gateway, or the network."** It survives the ethernet unplug by construction, and it screenshots beautifully for the 18:00 submission.

### S3.2 Configuration — the exact blocks

```json5
{
  agents: {
    entries: {
      answerer: {
        default: true,
        skills: ["airlock-verdict-explainer"],
        experimental: { localModelLean: true },
        tools: { allow: ["read", "view_image", "llm-task", "memory_search", "show_widget"] }
      }
    }
  },
  llm: { allowedCompletionModels: ["local/nvidia/Qwen3.6-35B-A3B-NVFP4"] },
  plugins: { entries: { "llm-task": { enabled: true } } },
  tools:   { alsoAllow: ["llm-task"] },
  skills:  { workshop: { autonomous: { mode: "propose" } } },
  models: { mode: "merge", providers: { local: {
    baseUrl: "https://inference.local/v1",
    apiKey: "sk-local",
    api: "openai-completions",
    timeoutSeconds: 300,
    models: [{
      id: "nvidia/Qwen3.6-35B-A3B-NVFP4",
      name: "Airlock Local",
      input: ["text", "image"],          // ← WITHOUT THIS, DEMO BEAT 3 SILENTLY FAILS
      reasoning: false,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 32768, maxTokens: 4096
    }] } } }
}
```

Four traps encoded above, each of which costs an hour if missed:

- **`input: ["text","image"]`** — without it, image attachments are never injected into agent turns, with no error. Pair with `NEMOCLAW_INFERENCE_INPUTS=text,image` at onboard time (§S4.2); that one is **build-time** and fixing it later costs a full `--fresh --recreate-sandbox`.
- **`localModelLean` is not auto-enabled for vLLM** — only for verified `ollama`/`lmstudio` routes. Set it explicitly. It drops `browser`, `cron`, `message`, `image_generate`, `music_generate`, `video_generate`, `tts`, `pdf`; it keeps `exec`, `read`, `write`, `edit`, image understanding and memory. If we ever alert via the `message` tool, add `tools.alsoAllow: ["message"]`.
- **`skills.workshop.autonomous.mode: "propose"`** — self-learning defaults to `auto`. An unreviewed skill capture from a 35B model during a live demo is a real risk, and `propose` is *also* the better story ("policy changes require a human"). Set it before we present.
- **Context preflight hard-blocks below 10% remaining (4 k floor).** A large image payload on a 32 k `--max-model-len` will trip it. Tune `contextWindow` on the model entry or raise `--max-model-len` (A owns this).

Escalation ladder if the local model won't tool-call, in order, no skipping:
```bash
openclaw infer model run --local   --model local/nvidia/Qwen3.6-35B-A3B-NVFP4 --prompt "Reply with exactly: pong" --json
openclaw infer model run --gateway --model local/nvidia/Qwen3.6-35B-A3B-NVFP4 --prompt "Reply with exactly: pong" --json
```
then `experimental.localModelLean: true` → `compat.requiresStringContent: true` → `compat.strictMessageKeys: true` → bypass OpenClaw tool-calling and call vLLM's OpenAI endpoint directly with guided JSON. **A owns steps 1–2; C owns steps 3–5.**

### S3.3 The one skill we author — minimal, complete, installable

Path in repo: `skills/airlock-verdict-explainer/SKILL.md`. Path in sandbox: `/sandbox/.openclaw/workspace/skills/airlock-verdict-explainer/SKILL.md` (top-precedence root; note `~` in the sandbox expands to `/sandbox`, not the workspace — use `$OPENCLAW_WORKSPACE_DIR`).

```markdown
---
name: airlock-verdict-explainer
description: Explain an Airlock block to the employee and answer their question locally.
version: 0.1.0
user-invocable: true
metadata:
  openclaw:
    emoji: "🛑"
    requires:
      bins: ["cat"]
      config: ["models.providers.local"]
---

# Airlock verdict explainer

You are the sanctioned side of Airlock. A payload was blocked before it left this
laptop. You never receive the confidential payload itself — only the verdict record
and the employee's question.

## Inputs

- A verdict JSON object: `{verdict, categories, confidence, rationale, spans[]}`.
- The employee's question, with confidential spans already removed.
- `{baseDir}/references/POLICY.md` — a symlink to the platform-maintained
  `/sandbox/.openclaw/workspace/POLICY.md`, refreshed by `nemoclaw policy explain --write`.

## What to do

1. Read `POLICY.md` with the `read` tool. Cite the applied preset or host category
   that justifies the block. Never invent a rule; if `POLICY.md` does not cover it,
   say "the rule body is redacted from me by design" — that is the correct answer.
2. State the block in one sentence, naming the categories from the verdict record.
3. Answer the employee's question using only local knowledge. You have no network
   tools. Do not suggest pasting the content anywhere else.
4. Render the result with `show_widget`: a `.badge.danger` verdict chip, the matched
   category labels, the policy citation, and the answer body. Keep it under 120 lines
   of self-contained HTML. Do not fetch anything.

## What NOT to do

- Do not ask for the original payload.
- Do not offer a cloud alternative, a workaround, or a "if you really need to" path.
- Do not call `exec`.
```

```bash
nemoclaw airlock skill install ./skills/airlock-verdict-explainer/
nemoclaw airlock exec -- openclaw skills list
```

Skill hot-reload is real and demo-able: the watcher debounces **250 ms**, so a `SKILL.md` edit changes the agent's behaviour live on screen. `description` must stay under 160 chars — it is what the model sees for routing.

### S3.4 Where OpenClaw is genuinely better, and where it is ceremony

**Load-bearing — keep:**

- `tools.allow` on the answerer. One line, strong claim, enforced pre-model-call.
- `llm-task` + `llm.allowedCompletionModels` for any classification we do *inside* the agent.
- The `airlock-verdict-explainer` skill and `show_widget` card. Offline, themed, screenshot-ready.
- `input: ["text","image"]`. Non-negotiable for demo beat 3.

**Ceremony — keep thin or cut, and say so:**

- **The classification hot path must NOT go through OpenClaw.** `POST /hooks/agent` returns on **runner admission, not completion** (200 may take 15 s, 503 if not admitted within 15 s), and `openclaw agent exec` spins up and tears down state per invocation. Neither belongs between a paste and a verdict. **The clipboard verdict is a direct guided-JSON call from `airlockd` to vLLM.** OpenClaw earns its place for the *answer*, the *explanation* and the *ledger* — not the verdict. Anyone who routes the hot path through the Gateway will demo a laggy paste.
- **Plugins are cut.** The `message_sending` → `{cancel:true}` and `before_tool_call` → `{block:true}` hooks are the most seductive thing in the OpenClaw docs and they are genuinely the right shape for a DLP product — but inside a NemoClaw sandbox a plugin requires a **full custom image rebuild** matched exactly to the installed CLI version, 5–15 min per iteration, and `--from` supplies the *complete* image definition rather than a layer. Our demo beats are all clipboard-side; those hooks would police channels we are not demoing. **Decision gate 13:00:** if we somehow have four idle hours and chose bare OpenShell rather than NemoClaw, `openclaw plugins install --link ./airlock` works at runtime and we add them. Otherwise: cut, and say in the pitch *"we know where that hook is and why we didn't spend the image rebuild on it today."*
- **Heartbeat: one line of config, no more.** `agents.defaults.heartbeat: { every: "30m", lightContext: true, isolatedSession: true }` sweeping the blocked-payload ledger. It is a good line in the pitch ("an always-on agent that mostly shuts up — `HEARTBEAT_OK`") and thirty seconds of work. Do not build a monitoring product around it.
- **One automation, for visibility, not for the hot path:**
  ```bash
  openclaw automations add --name "Airlock ledger sweep" --every 30m \
    --session isolated --tools read,memory_search \
    --message "Summarise today's blocked-payload ledger. Flag repeat offenders. If nothing, say HEARTBEAT_OK."
  ```
  It gives us a SQLite-backed job with run history and an auto-disable backstop visible in the Control UI. If you POST verdicts to a local UI, note the **webhook SSRF guard refuses loopback by default** — `cron.webhookSsrfPolicy.allowedHostnames: ["127.0.0.1"]`.
- **Cut outright:** MCP registration, Honcho, Mongo-as-agent-memory (there is no supported Mongo memory backend — if we want Mongo, it is the *audit ledger*, an application datastore Airlock owns, and that split is easier to defend anyway), Lobster, Swarm, standing intents, self-learning as a demo beat.

**One 30-second win worth taking at 10:15:** `openclaw skills install xejrax/clipboard` (164 installs, `xclip`, **text only**; `clawhub.ai:443` is on the allowlist, `github.com` is not). It is our text baseline, it buys back an hour, and *the fact that the community skill stops at text is itself the argument for demo beat 3.* Rehearse the line: **"the existing community skill handles text. No regex catches a picture."**

Also know the prior art before a judge names it: `aporthq/aport-agent-guardrail` — *"local-first policy enforcement that checks tool calls against your passport."* The differentiator, rehearsed: **"APort asks 'may this tool run?' Airlock asks 'what is actually in this?' — and it can answer that for a PNG."**

---

## S4. NemoClaw — orchestration and the two-model problem

### S4.1 The two-model constraint, and the clean answer

**The constraint, verbatim from the docs:** *"OpenShell exposes one live inference route per gateway."* Every sandbox on the gateway shares it, and `inference set` refuses before mutating if any same-gateway sandbox's recorded route conflicts. **NemoClaw's managed route cannot serve both our VLM and our text LLM.**

**The answer is already built.** The built-in `local-inference` preset (`nemoclaw-blueprint/policies/presets/local-inference.yaml`) pre-authorises host-side inference on four ports over the `host.openshell.internal` bridge — and this is the *only* endpoint where user-authored `allowed_ips` is permitted, precisely because OpenShell's SSRF guard otherwise rejects private host-gateway addresses:

| port | grant |
|---|---|
| **8081** | `POST /v1/chat/completions` **only** |
| 8000 | `GET /**`, `POST /**` |
| 11434 / 11435 | `GET /**`, `POST /**` |

binaries allowlisted to `/usr/local/bin/openclaw`, `/usr/local/bin/node`, `/usr/bin/node`, `/usr/bin/curl`, `/usr/bin/python3`.

**Airlock's split:**

- **Text LLM → the managed route.** `nvidia/Qwen3.6-35B-A3B-NVFP4` on host `:8000`, reached in-sandbox as `https://inference.local/v1`. This is the route `nemoclaw status` probes and the one that satisfies Rule 02.
- **VLM → host `:8081`.** `Hcompany/Holo1.5-7B`, called directly at `http://host.openshell.internal:8081/v1/chat/completions`, authorised by one command.

```bash
nemoclaw airlock policy add local-inference --dry-run   # show the room the exact scope
nemoclaw airlock policy add local-inference --yes
```

Port 8081's rule is a single method on a single path — **the narrowest grant in the entire preset catalogue.** Use it: *"our vision model is reachable on exactly one verb and one path, and nothing else in that container can talk to it."*

Memory fits: the Spark managed-vLLM profile runs at **`--gpu-memory-utilization 0.4`**, leaving ~60% of the 121 GiB visible to CUDA for the second server. A owns confirming actual residency; **OOM freezes the whole host**, so A tests the pair together before 12:00, not at 16:00.

**Honest boundary we state rather than hide:** `--agents agents.yaml` gives per-agent `model:`, but *"the provider must match the onboard provider; cross-provider manifests are not supported."* Two vLLM servers on two ports are two providers, so `agents.yaml` **cannot** span them. Airlock's own code routes to the VLM directly. Knowing that boundary reads as more competent than pretending it isn't there.

### S4.2 Bring-up — the exact commands

```bash
# 10:00 — baseline, changes no state, exit 0 supported / 2 incompatible / 3 inconclusive
nemoclaw --version
nemoclaw host probe --json | tee evidence/airlock-host-probe.json
nemoclaw profiles list --json
nemoclaw agents list

# 10:10 — onboard. NOTE: NEMOCLAW_NO_EXPRESS=1 because Express bakes
# NEMOCLAW_INFERENCE_INPUTS at its default "text" and we need "text,image".
NEMOCLAW_NO_EXPRESS=1 \
NEMOCLAW_INFERENCE_INPUTS=text,image \
NEMOCLAW_AGENT=openclaw \
NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 \
nemoclaw onboard --name airlock --no-gpu --events=jsonl | tee evidence/onboard.jsonl

# 10:30 (after the 5–15 min image build)
nemoclaw airlock status --json | jq '{openshellVersion, openclawVersion, phase}'
nemoclaw airlock policy add local-inference --dry-run
nemoclaw airlock policy add local-inference --yes
nemoclaw airlock policy explain --json | tee evidence/airlock-policy.json
nemoclaw airlock policy explain --write        # refreshes /sandbox/.openclaw/workspace/POLICY.md
nemoclaw airlock dashboard-url                 # read the port off this; do not assume
```

**`NEMOCLAW_INFERENCE_INPUTS=text,image` is build-time.** Miss it on the first onboard and the fix is `nemoclaw onboard --fresh --name airlock --recreate-sandbox` — another 5–15 min image build. **This is the single most expensive mistake available today.** C says it out loud before pressing enter.

**Do not run `uv tool install -U openshell`.** The blueprint declares `min_openshell_version: "0.0.106"` **and** `max_openshell_version: "0.0.106"`; released latest is 0.0.111; NemoClaw rejects a known stable version above the maximum outside `NEMOCLAW_OPENSHELL_CHANNEL=dev`. Let the installer own the version.

**Do not select the `routed` profile.** Model Router's documented flow is `router:4000 → https://integrate.api.nvidia.com`, which would violate Rule 02.

> **VERIFY-AT-10:00:** the dashboard port. The brief says 18790; NemoClaw's docs only ever show 18789 plus `--control-ui-port <N>`. **Read it off `nemoclaw airlock dashboard-url --quiet` and never type a port from memory.** Treat that URL like a password — it carries a token fragment.

> **VERIFY-AT-10:00:** that the managed profile actually took `:8000` (`NEMOCLAW_VLLM_PORT` default) before A binds the VLM to `:8081`. The `local-inference` preset covers 8000/8081/11434/11435 either way, but our URLs change.

### S4.3 Should Airlock ship as a blueprint? **No.**

Authoring a blueprint means forking `NVIDIA/NemoClaw`, editing YAML the runner resolves from a *source checkout*, and rebuilding the digest-pinned sandbox image, 5–15 min per iteration. There is no public `nemoclaw blueprint apply ./my-blueprint.yaml`. In an 8-hour build that is a trap.

**Ship the data-only seams instead** — the custom policy preset (§S2.1), the policy exclusions, and the skill. They give 80% of the "we extended the blueprint" narrative at 5% of the risk. Then **quote the blueprint schema in the writeup** to show we read it, including the genuinely elegant detail worth naming: the top-level `digest:` field intentionally *mirrors* `components.sandbox.image`'s digest, with an in-file comment explaining that this lets a consumer verify the pinned image without parsing the components tree **and blocks the trivially-bypassable case where someone bumps the pinned image but forgets the top-level field.** Naming that detail costs one sentence and signals we read the source, not the marketing.

### S4.4 ⭐ Shields — the most on-theme feature in the stack

```bash
nemoclaw airlock shields up
nemoclaw airlock shields status
nemoclaw airlock shields down --timeout 2m --reason "live demo: widening policy"
```

`shields up` locks the sandbox config (DAC 444 root:root + `chattr +i`) and restores the captured restrictive policy. `shields down --timeout` opens a **time-boxed break-glass window with a recorded reason** and a detached timer that **auto-relocks at the deadline**. Every transition writes an audit entry. While up, `config set` and `inference set` are **refused**. Fail-closed throughout: if the permissive policy is rejected it stays up; if re-lock cannot be confirmed it records "durable containment" and blocks all further mutation.

**Demo beat, 40 seconds, and almost nobody will find it:** `shields status` → UP. Try `nemoclaw airlock inference set --model something-remote` → **refused**. `shields down --timeout 2m --reason "demo"` → make the change → keep talking → **it relocks itself on stage**. Airlock's pitch is "the bouncer can't be bribed." Shields is NVIDIA's own shipped mechanism saying exactly that.

### S4.5 Snapshot/restore — the 20-second DLP self-audit

```bash
nemoclaw airlock shields down --timeout 5m --reason "snapshot"
nemoclaw airlock snapshot create --name pre-demo
nemoclaw airlock snapshot list
nemoclaw airlock snapshot restore v1 --to airlock-clone --yes
```
Stored in `~/.nemoclaw/rebuild-backups/airlock/`. Requires shields down.

The stripping is more thoughtful than "regex out the secrets," which is exactly why it's a good beat. It strips recognised credential values from copied JSON/YAML/`.env`, but **preserves dependency lockfiles byte-for-byte** when they contain only dependency metadata — *because dependency names can collide with credential field names.* It **omits** any lockfile containing a credential field, a provider-shaped secret outside a dependency URL, URL userinfo, or a credential-bearing query param. It preserves OpenShell credential placeholders so rebuild can reattach. If it cannot sanitise, it omits; if it cannot remove the unsafe file, **snapshot creation fails closed.**

**On stage:** `snapshot create` → `grep -r 'sk-' ~/.nemoclaw/rebuild-backups/airlock/` → **nothing**, but `package-lock.json` is intact and byte-identical. Twenty seconds that say "we know the difference between redaction and destruction," on a product whose entire job is that distinction.

---

## S5. The Policy Advisor set piece

### S5.1 The conflict, resolved honestly

Two of this morning's research passes disagree. The OpenShell pass found a full, documented Policy Advisor at `docs.nvidia.com/openshell/latest/sandboxes/policy-advisor.md` — `policy.local`, `agent_guidance`, `openshell rule approve`, `404 feature_disabled`, disabled by default. The NemoClaw pass found **zero hits** for any of it across 1.4 MB of NemoClaw docs.

**Both are probably right.** The advisor is an *OpenShell* feature documented against *latest* (0.0.111); NemoClaw pins 0.0.106 and does not surface it. So the advisor is a coin-flip on our installed version, and **we plan the set piece so that the fallback is at least as good as the primary.**

### S5.2 The 10:00 check — three commands, ninety seconds

```bash
# C runs these at 10:35, immediately after onboard completes.

# 1. Try to enable it. If the settings key is unknown, this errors immediately.
openshell settings set --global --key agent_policy_proposals_enabled --value true --yes

# 2. Confirm scope resolution (prints: global | sandbox | unset)
openshell settings get airlock

# 3. Probe from inside the sandbox.
nemoclaw airlock exec -- curl -sS http://policy.local/v1/policy/current
```

**Decision:**
- Command 1 errors, or command 3 returns `404 feature_disabled` → **PATH B** (§S5.4).
- Command 3 returns policy YAML → **PATH A** (§S5.3). Set the flag **before** the sandbox is created if you can, so the first denial already carries `agent_guidance`; running sandboxes poll settings and can pick it up late.

Either way, **`nemoclaw airlock policy explain --json` works regardless.** It is a host-side command that does not depend on in-sandbox advisor routes and will never 404. Plan on it as the load-bearing piece and treat the advisor as garnish.

### S5.3 PATH A — the advisor loop (40 seconds on stage)

Split screen: **left** `nemoclaw airlock logs --follow`, **right** the agent session. Owner on stage: **C drives the terminal, A narrates.**

| t | Who | Action | Expected on screen |
|---|---|---|---|
| 0s | C (right) | `nemoclaw airlock exec -- gh api /repos/NVIDIA/OpenShell` | `curl: (56) Received HTTP code 403 from proxy after CONNECT` |
| 3s | — | left pane | `NET:OPEN [MED] DENIED /usr/bin/gh(64) -> api.github.com:443 [reason:no matching policy]` |
| 6s | A (narrate) | "the denial body carries `agent_guidance` — the platform tells the agent how to ask" | L7 body shows `layer`, `host`, `port`, `binary`, `method`, `path`, `rule_missing`, `next_steps`, `agent_guidance` |
| 10s | C (right) | `nemoclaw airlock exec -- curl -sS http://policy.local/v1/denials?last=5` | newest-first denied OCSF lines, query strings redacted |
| 15s | C (right) | agent POSTs a **narrowed** proposal | returns `accepted_chunk_ids` |
| 22s | C (**left, outside the sandbox**) | `openshell rule get airlock --status pending` | `Endpoints: api.github.com:443 [L7 rest, allow GET /repos/NVIDIA/OpenShell]` |
| 28s | C | `openshell rule approve airlock --chunk-id <id>` | `CONFIG:APPROVED` then `CONFIG:LOADED` in the left pane |
| 35s | C (right) | retry the same call | 200 |

The proposal body, exact shape:

```json
{
  "intent_summary": "Read-only access to the OpenShell repo metadata.",
  "operations": [{ "addRule": {
    "ruleName": "github_repo_read",
    "rule": {
      "name": "github_repo_read",
      "endpoints": [{ "host": "api.github.com", "port": 443,
        "protocol": "rest", "enforcement": "enforce",
        "rules": [{ "allow": { "method": "GET", "path": "/repos/NVIDIA/OpenShell" } }] }],
      "binaries": [{ "path": "/usr/bin/gh" }]
    }}}]
}
```

The line that lands: **the approval happens from outside the sandbox, on a rule the agent proposed but cannot grant itself.** Rejections carry a reason back through `policy.local` so the agent can revise and narrow. Keep `proposal_approval_mode` at its default `manual` — auto-approve only fires when the policy prover's delta is empty, and "a human approves policy changes" is the better story anyway.

Audit trail to point at, in order, in the left pane: `HTTP:* DENIED` → `CONFIG:PROPOSED` → `CONFIG:APPROVED` → `CONFIG:LOADED` → the retried allowed request.

### S5.4 PATH B — the fallback, which is arguably the better demo anyway

If the advisor is unavailable, use the **`openshell term` TUI**. Both research passes confirm this independently; it is the safest bet in the whole section.

```bash
openshell term
# j / k  select sandbox      Enter  open
# r      focus Network Rules
# a      approve selected pending rule   x  reject   A  approve-all (confirm y)
```

Blocked requests appear as pending entries showing **destination host and port, the binary that initiated the request, and HTTP method and path.** Approvals hot-reload into the running policy for that sandbox instance and reset to baseline on recreate — they are not written to the baseline file.

**The 40-second version:** split screen, agent right, `openshell term` Network Rules left. Agent attempts `api.openai.com`. It appears in the left pane — host, port, **and the binary that tried it**. C presses **`x`**. Denied, live, in two seconds.

That single keypress proves the entire thesis better than any slide, and it directly answers the inevitable *"how do I know your agent isn't the leak?"* **Rehearse it at 16:00. It is worth more than another feature.**

Free stagecraft: `NVIDIA/NemoClaw/scripts/walkthrough.sh` opens a split tmux session with the TUI on the left and the agent on the right. Requires tmux, a source checkout, and an onboarded sandbox. **VERIFY-AT-10:00** that it runs without `NVIDIA_INFERENCE_API_KEY` (it is documented as requiring one, which we deliberately do not have); **fallback:** two tmux panes by hand, 30 seconds.

---

## S6. Stack tasks by phase and owner

C owns the stack. A and B touch it at exactly six points, all marked ⚠️ — these are the coupling points where a miscommunication costs an hour.

| Phase | Time | Owner | Task — exact commands |
|---|---|---|---|
| **P0 Baseline** | 10:00–10:10 | **C** | `nemoclaw --version` · `nemoclaw host probe --json \| tee evidence/airlock-host-probe.json` · `nemoclaw profiles list --json` · `nemoclaw agents list` · confirm `nvidia-smi` driver is 580.x |
| | 10:00–10:10 | **A** | `docker images \| grep hellohal2064` — confirm the SM121-patched vLLM image is staged; confirm all three model weights present |
| | 10:00–10:10 | **B** | Scaffold `airlock-clip` + UI shell against a **stubbed** `/v1/inspect` returning fixed JSON. Do not wait on the stack. |
| **P1 Onboard** ⚠️ | 10:10–10:35 | **C** | `NEMOCLAW_NO_EXPRESS=1 NEMOCLAW_INFERENCE_INPUTS=text,image NEMOCLAW_AGENT=openclaw NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 nemoclaw onboard --name airlock --no-gpu --events=jsonl \| tee evidence/onboard.jsonl` — **say `text,image` out loud before pressing enter** |
| | 10:10–10:35 | **A** | Launch vLLM `:8000` = `nvidia/Qwen3.6-35B-A3B-NVFP4`. ⚠️ **Report the actual port to C** — if Express moved `NEMOCLAW_VLLM_PORT`, C's URLs change. |
| **P2 Advisor check** | 10:35–10:45 | **C** | The three commands in §S5.2. Announce **PATH A** or **PATH B** to the team. No revisiting. |
| **P3 Policy** | 10:45–11:30 | **C** | `nemoclaw airlock policy add local-inference --dry-run` then `--yes` · write + apply `policy/airlock-egress.yaml` via `policy add --from-file` · `nemoclaw airlock policy list` (capture exact baseline rule names) · `nemoclaw airlock policy explain --json \| tee evidence/airlock-policy.json` · `openshell settings set --global --key ocsf_json_enabled --value true` |
| | 10:45–11:30 | **A** | Launch vLLM `:8081` = `Hcompany/Holo1.5-7B`. ⚠️ **Watch unified memory together with C — OOM freezes the whole host.** Managed profile runs at `--gpu-memory-utilization 0.4`. |
| **P4 Denial artifact** | 11:30–12:00 | **C** | `nemoclaw airlock exec -- curl -sS https://api.openai.com/v1/models` → capture the `policy_denied` JSON to `evidence/policy-denied.json`. Verify both log channels: `nemoclaw airlock logs --follow` and the OCSF JSONL tail. |
| **P5 Middleware gate** ⚠️ | 12:00–13:00 | **C** | `nemoclaw airlock status --json \| jq .openshellVersion` · run the `network_middlewares: {}` probe (§S2.6). **13:00 hard decision: Tier A or Tier B.** Announce it. Never revisit. |
| | 12:00–13:00 | **A** | ⚠️ **Real timing test** with a representative revenue-chart PNG, not a thumbnail. Report p50/p95 latency to C — this is the input to the Tier A/B call and to the middleware `timeout` value. |
| **P6 OpenClaw** | 13:00–14:30 | **C** | Apply the config block in §S3.2 · `nemoclaw airlock skill install ./skills/airlock-verdict-explainer/` · `openclaw skills install xejrax/clipboard` · `openclaw automations add` (ledger sweep) · `openclaw plugins enable policy` · author `policy/openclaw-policy.jsonc` |
| | 13:00–14:30 | **A** | ⚠️ Escalation ladder steps 1–2 (`openclaw infer model run --local` / `--gateway`). Hand off to C at step 3 if tool-calling fails. |
| | 13:00–14:30 | **B** | ⚠️ Swap the stub for the real `airlockd` at `127.0.0.1:9100`. Agree the verdict JSON schema with C **in writing** before 13:15. |
| **P7 Integration** | 14:30–16:00 | **C** | Wire `show_widget` verdict card · Tier A only: register the gateway TOML, `timeout = "30s"`, **start `airlockd` before restarting the gateway** · `nemoclaw airlock shields up` and verify a `config set` is refused |
| | 14:30–16:00 | **B** | End-to-end all three demo beats through the real classifier |
| **P8 Rehearsal** | 16:00–17:00 | **C+A+B** | Full run twice. Split-screen layout locked. **Rehearse `openshell term` → `x` on `api.openai.com`.** Rehearse the shields auto-relock. Rehearse the snapshot grep. Rehearse the unplug. |
| **P9 Evidence** | 17:00–17:40 | **C** | Copy `/var/log/openshell-ocsf.$(date +%F).log` out of the sandbox · run the Rule 02 `jq` command (§S2.5) · `openclaw policy check --json` · `nemoclaw airlock policy explain --json` · screenshot the `show_widget` card, the interleaved log pane, and `openshell term` mid-denial |
| **P10 Submission** | 17:40–18:00 | **C** | Paste §S7 with real version numbers substituted. Attach the six artifacts. **Written submission alone picks the top 8 — do not run the demo past 17:40.** |
| **Anytime** | — | **C** | `nemoclaw airlock shields down --timeout 5m --reason "..."` before any `config set` or `inference set`. It will refuse otherwise and you will waste five minutes wondering why. |

**Trap register — print this and tape it to the monitor:**

1. `NEMOCLAW_INFERENCE_INPUTS=text,image` at onboard. Missing it = 15-minute rebuild.
2. `input: ["text","image"]` on the OpenClaw model entry. Missing it = beat 3 fails **silently**.
3. Never `uv tool install -U openshell`. Blueprint pins 0.0.106.
4. Middleware `timeout` defaults to **500 ms**. Set 30 s or it dies.
5. Webhook SSRF guard refuses loopback by default.
6. `POST /hooks/agent` returns on **admission**, not completion. Never block a paste on it.
7. Local-endpoint preflight caches 5 minutes. After restarting vLLM, automations may report `skipped` for up to 5 min — do not debug a phantom.
8. `github.com` is blocked from inside the sandbox; ClawHub and npm are not.
9. Main-process exit is terminal even at exit code 0. Run the sandbox detached with a long-lived main process.
10. `skills.workshop.autonomous.mode: "propose"` before we present.

---

## S7. What we say about the stack in the submission

### S7.1 The paragraph

> **Stack (Rule 02 — minimum 2/3, no remote LLM/API calls in the agent runtime path).**
> Airlock uses all three layers of the NVIDIA reference stack, in the documented relationship: **NemoClaw** (`NVIDIA/NemoClaw`, Apache-2.0, alpha, `v0.0.113` — see `evidence/onboard.jsonl`) orchestrates → **OpenShell** (`NVIDIA/OpenShell`, Rust, Apache-2.0, alpha, `v0.0.106` as pinned by the NemoClaw blueprint's `min`/`max_openshell_version`) isolates and runs → **OpenClaw** (`openclaw@2026.7.1-2`, MIT, Node 22.22.3) in the sandbox. Host: DGX Spark GB10, 128 GB unified (~121 GiB visible to CUDA), sm_121, driver 580.x. Inference is served on the host by vLLM in the SM121-patched `hellohal2064/vllm-dgx-spark-gb10` image: `nvidia/Qwen3.6-35B-A3B-NVFP4` on `:8000` as NemoClaw's managed inference route (reached in-sandbox as `https://inference.local/v1`), `Hcompany/Holo1.5-7B` on `:8081` for vision, and `BAAI/bge-small-en-v1.5` for the sub-100 ms prefilter.
>
> **We do not assert that no remote LLM was called — we enforce it in four layers and attach the log.** (1) OpenShell egress is deny-by-default; no allow rule names `api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com` or `integrate.api.nvidia.com`, so those hosts return `403 policy_denied / no matching policy` at the proxy — enforced outside the sandbox, unmodifiable from within it. (2) `inference.local` is not a hostname allowance but a whitelist of request *shapes*; the Privacy Router strips sandbox-supplied credentials, injects the gateway's, rewrites the model, and denies non-inference requests. (3) The inference route is gateway-scoped and set from the host; the sandbox's own `model` and `api_key` are discarded before anything leaves. (4) Every inference call emits an OCSF v1.8.0 `class_uid: 6003` API Activity record naming its provider URL — `evidence/rule02-providers.txt` is the output of `jq -r 'select(.class_uid==6003) | .ai_model.ai_provider' | sort | uniq -c` over the full run: **one provider, `host.openshell.internal`, zero cloud LLM hosts, zero denied-egress events to any inference endpoint.** The agent additionally runs under `llm.allowedCompletionModels` pinned to the local model, and `openclaw policy check --json` attests `models.providers.deny` at config level with an attestation hash (`evidence/openclaw-policy-check.json`).
>
> **The stack is load-bearing, not decorative.** Airlock's egress contract ships as a custom NemoClaw policy preset (`policy/airlock-egress.yaml`, applied with `nemoclaw airlock policy add --from-file`), recorded with the sandbox and replayed on rebuild and snapshot-restore. Our vision model is reachable on exactly one verb and one path (`POST /v1/chat/completions` on `host.openshell.internal:8081`, via the built-in `local-inference` preset). The sandbox runs with `shields up` — config locked, `inference set` refused, break-glass time-boxed and audited. Airlock's own verdict explanation is generated from `nemoclaw airlock policy explain --json`, the platform's redacted, agent-consumable view of the policy: **the bouncer knows the rules it is itself bound by, and cannot read the rule bodies.**
>
> **What we did not do, and why.** We did not ship a custom blueprint or a custom OpenClaw plugin: both require a full digest-pinned image rebuild matched to the installed CLI version, 5–15 minutes per iteration, and neither buys anything our demo shows. We used the data-only extension seams the docs point to instead — a policy preset, a policy exclusion record, and an installed skill. We also state plainly that the `@openclaw/policy` plugin verifies **config-level conformance only**; it does not enforce tool calls at request time. Runtime enforcement is OpenShell's proxy. And the clipboard interceptor necessarily runs on the host — a sandbox cannot and should not observe a paste event. Our host-side claim is architectural (loopback-only binding, no cloud SDK linked) and demonstrated the only honest way: **with the ethernet cable on the table.**

### S7.2 Evidence artifacts to attach

| File | Produced by | Proves |
|---|---|---|
| `evidence/airlock-host-probe.json` | `nemoclaw host probe --json` | clean, reproducible platform baseline; schema-versioned; changes no state |
| `evidence/onboard.jsonl` | `nemoclaw onboard --events=jsonl` | reproducible, credential-redacted, schema-versioned build trace |
| `evidence/airlock-policy.json` | `nemoclaw airlock policy explain --json` | tier, applied presets with `verification` field, allowed host categories, `redactedHostCount` |
| `evidence/policy-denied.json` + terminal capture | `curl https://api.openai.com/v1/models` from inside | the denial artifact, with `curl: (56) ... 403 from proxy after CONNECT` |
| **`evidence/rule02-providers.txt`** | the §S2.5 `jq` one-liner over the OCSF log | **Rule 02 as a machine-checkable fact.** The single strongest artifact. |
| `evidence/openclaw-policy-check.json` | `openclaw policy check --json` | attestation hashes over `models.providers.deny`, `dataHandling.telemetry.denyContentCapture` |
| `evidence/openshell-ocsf.YYYY-MM-DD.log` | in-sandbox OCSF JSONL | the complete decision record; the in-sandbox file is authoritative (the gateway buffer is in-memory) |
| `screenshots/verdict-card.png` | `show_widget`, exported from the card menu | the offline, themed verdict UI |
| `screenshots/interleaved-log.png` | `nemoclaw airlock logs --follow` | **agent verdicts and policy denials in one stream — the thesis as a screenshot** |
| `screenshots/openshell-term-deny.png` | `openshell term`, Network Rules, mid-denial | host, port and **the binary that tried it**, pending operator approval |
| `policy/airlock-egress.yaml`, `policy/openclaw-policy.jsonc`, `skills/airlock-verdict-explainer/SKILL.md` | checked in | the reviewable artifacts themselves |

**If we cut scope, cut in this order:** supervisor middleware (Tier A) → policy exclusions → snapshot demo → heartbeat → the ledger automation.
**Never cut:** `evidence/rule02-providers.txt`, the `openshell term` split-screen denial, `nemoclaw airlock logs --follow` on the left of the projector, and `policy/airlock-egress.yaml` in the repo. Those four are the difference between *"we used the stack"* and *"the stack is the product"* — and the written submission alone picks the top 8 at 18:00.
---

## 9. Team and Responsibilities

Three engineers. Surfaces are owned, not shared. Where two people need the same thing, one owns the artifact and the other consumes it over a frozen contract.

| | **A — Inference** | **B — Client & UI** | **C — Stack, Data & Writeup** |
|---|---|---|---|
| **Owns** | Every GPU process. vLLM launch/flags/env. `/v1/inspect` internals: T0, T1, T2, T3, span verification, calibration, threshold. All latency and throughput measurement. The seats-per-box arithmetic. | Chrome MV3 extension (`manifest.json`, `airlock.js`, `sw.js`, `mainworld.js`). Block overlay. Live console. Local replica page. Anything a judge sees on a screen that isn't a terminal. | NemoClaw → OpenShell → OpenClaw bring-up, policy artifact, egress allowlist. MongoDB container, collections, indexes, change stream, seed scripts. Benign + sensitive corpora. The FP-rate harness. The written submission. |
| **Files** | `services/inspect/**` (`app.py`, `tiers/t0.py`, `tiers/t1.py`, `tiers/t2.py`, `tiers/t3.py`, `verify.py`, `calib.py`, `schemas.py`), `stack/launch_text.sh`, `stack/launch_vision.sh`, `stack/preflight.sh`, `stack/warm.sh`, `bench/**` | `extension/**`, `web/replica/**` (the `localhost:5173` page), `web/console/**` | `stack/up_mongo.sh`, `stack/seed.js`, `stack/openshell-policy.toml`, `stack/proof.sh`, `services/inspect/mongo.py`, `services/inspect/stream.py`, `services/inspect/policy.yaml`, `bench/build_benign.py`, `bench/build_sensitive.py`, `bench/run_fpr.py`, `data/**`, `submission/**` |
| **Never touches** | The extension. The overlay CSS. The submission prose. Do not "quickly fix" B's JS — file it as a line in `NOTES.md` instead. | Anything with `--gpus`. Any `vllm serve`. Any bare `python` that imports torch. MongoDB indexes. The policy artifact. | Anything with `--gpus`. vLLM flags. The tier logic in `services/inspect/tiers/`. C may *read* it to write about it; C may not edit it. |
| **Owns the number** | Vision p50/p95, images/sec, escalation rate, throughput sweeps, seats/box | Nothing measured — B owns whether it *renders* | FPR with denominator, Wilson CI, ablation table, per-class breakdown |

### The one rule

> **NFR-S1 — Only A starts, stops, or restarts a GPU process.**
>
> B and C consume `http://127.0.0.1:8000`, `:8001`, and `:8787` over HTTP and nothing else. They never run `docker run --gpus`, never `vllm serve`, never a bare Python that imports torch with CUDA available. On this box unbounded allocation **freezes the whole host — no SSH, no ping** (pytorch/pytorch#174358). A concurrent second launch by an unaware team-mate is the single most likely way to lose the entire day at 14:00.
>
> A keeps a running total of summed `--gpu-memory-utilization` written on the whiteboard, updated **before** a launch, never after. Committed demo total: **0.64**. Hard ceiling: **0.85**.
>
> C owns the MongoDB container, which has no `--gpus` and is therefore C's to run — but it starts **before** A's first model (NFR-S6) and its heap is verified before A launches server #1.

### Escalation protocol

Anyone who believes the box is in trouble says the word **"FREEZE"** out loud. On "FREEZE": A runs `nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv` and `grep MemAvailable /proc/meminfo`. If `MemAvailable < 8 GB`, A stops `airlock-vision` immediately (NFR-S13). Nobody else touches anything for 60 seconds.

---

## 10. Phase Plan

Repository root: `/mnt/data/Projects/Dell_Hackathon/airlock/`. Created empty at 10:00 (Rule 01: empty scaffolding is permitted pre-staging; no logic exists before doors open).

**Contract freeze — 10:00, five minutes, all three, standing up.** The `airlock.inspect.v1` request and `airlock.verdict.v1` response bodies from §5.1 are pasted verbatim into `CONTRACT.md` and are immutable for the day. Every mock, fixture and stub in this plan conforms to that file. Nobody waits on anybody because of a field name.

---

### Phase 0 — 10:00 to 10:45 · De-risk

Purpose: kill the three things that can end the day, before spending a minute on anything pretty. Nothing built in this phase is expected to survive to the demo.

| A — Inference | B — Client & UI | C — Stack, Data & Writeup |
|---|---|---|
| 1. `bash stack/preflight.sh`: `sudo swapoff -a`; `sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'`; `nvidia-smi --query-gpu=driver_version --format=csv`; `free -h > /tmp/baseline_free.txt`. **If driver reads 590.x, stop and shout — hard stop, see Gate G0.**<br>2. `docker images \| grep -E 'vllm\|hellohal'` — confirm `hellohal2064/vllm-dgx-spark-gb10` and `vllm/vllm-openai` are present with arm64 digests. Pre-staged; do not pull now.<br>3. Wait for C's "mongo heap verified" call (≤10:08). Do not launch before it.<br>4. Launch **airlock-text** `:8000` at `--gpu-memory-utilization 0.40`, `--max-model-len 32768`, `--max-num-seqs 8`, `--moe-backend marlin`, `--kv-cache-dtype fp8`, `--limit-mm-per-prompt '{"image":0,"video":0}'`, env `VLLM_MARLIN_USE_ATOMIC_ADD=1 VLLM_USE_FLASHINFER_MOE_FP4=0 CUTE_DSL_ARCH=sm_121a`. Write `0.40` on the whiteboard.<br>5. Launch **airlock-vision** `:8001` at `0.24`, image `hellohal2064/vllm-dgx-spark-gb10`, `--attention-backend TRITON_ATTN`, `--mm-processor-kwargs '{"min_pixels":200704,"max_pixels":1003520}'`, `--mm-processor-cache-gb 1`, `-e VLLM_MM_INPUT_CACHE_GIB=2`, `--limit-mm-per-prompt '{"image":1,"video":0}'`. Whiteboard total → `0.64`.<br>6. `bash stack/warm.sh` — poll both `/health`, then fire a 1×1 px image at `:8001` with `max_tokens=3` and a 4-token text prompt at `:8000`. **Expect 25–57 s of torch.compile on the first call. This is not a hang.**<br>7. Write `bench/vision_gate.py`: loads the 20 pre-staged distinct 1280×720 chart images from `data/images/gate/`, POSTs each to `:8001` `/v1/chat/completions` with the T3 transcribe prompt, `max_tokens=8`, records `performance` timings, prints p50/p95. **Distinct images — identical images hit the V1 prefix cache and produce a fraudulent number.**<br>8. Run it. **This is Gate G1.**<br>9. In parallel with 8: `python -c` dump of the tokenizer to confirm all nine label strings are first-token-distinct; and one guided-JSON round-trip against `:8000` testing `response_format={"type":"json_schema",...}` → fallback `extra_body={"structured_outputs":{"json":...}}` → fallback `extra_body={"guided_json":...}`. Record which spelling the pinned build accepts in `NOTES.md`. | 1. `chrome://version` — record the version. **Must be ≥ 144.0.7512.0.** If 142.x or 143.x, apply `chrome://flags#local-network-access-check → Disabled` and relaunch, or launch with `--user-data-dir=/tmp/airlock-profile`. Note which was needed.<br>2. Write `tools/stub_inspect.py` — 40 lines of FastAPI on `127.0.0.1:8787`, serving `POST /v1/inspect`, `GET /healthz`, `OPTIONS *→204` with the full CORS + `Access-Control-Allow-Private-Network: true` header set. Rule: text containing `@` → `{"action":"block","label":"CUSTOMER_RECORD",...}`; anything else → allow. Response body copied verbatim from `CONTRACT.md`. **B owns this stub for the whole day; it is the thing B falls back to if A's service ever wedges.**<br>3. `uvicorn tools.stub_inspect:app --host 127.0.0.1 --port 8787` in its own terminal.<br>4. Write `extension/manifest.json` exactly as §6 of the MV3 spike. **No `clipboardRead` permission** — the install warning "Read data you copy and paste" is the wrong first impression for a privacy product.<br>5. Write `extension/sw.js` hello-world: `onMessage` → `fetch('http://127.0.0.1:8787/healthz')` → `sendResponse`. **`return true` at the end of the listener.** Missing it is the #1 MV3 bug and it looks exactly like model slowness.<br>6. Write `extension/airlock.js` stub: on load, `chrome.runtime.sendMessage({type:'PING'})` and `console.log` the reply.<br>7. Load unpacked at `chrome://extensions`, open `https://chatgpt.com`, confirm the ping round-trips. **This is Gate G1-B and it de-risks everything downstream: it proves the LNA-exempt service-worker path works on this box.**<br>8. Open the service-worker DevTools window (blue "service worker" link on the extension card) and leave it open all day. Content-script logs go to the *page* console; SW logs go here. Two consoles. | 1. `bash stack/up_mongo.sh`: the exact `docker run` from §3 — `--platform linux/arm64 --memory=6g --memory-swap=6g --cpus=4 -e DO_NOT_TRACK=1`, then the health-poll loop.<br>2. **Verify the heap cap within 5 minutes** (NFR-S6): `docker stats --no-stream airlock-mongo` and `docker exec airlock-mongo grep -i -m5 -E 'Xmx\|heap' /tmp/mongot.log`. Want ≈1.5 GB, not 32 GB. If not capped, add `-e JAVA_TOOL_OPTIONS="-Xms1g -Xmx2g"` and re-run. **Call "mongo heap verified" out loud — A is blocked on this.**<br>3. `mongosh mongodb://localhost:27017/?directConnection=true` — confirm connection in under 2 s. If it hangs, `directConnection=true` is missing.<br>4. Start `bench/build_benign.py` running in the background against the pre-staged dumps: 400 WildChat first-turns (`toxic==False`, PII-redaction flag unset), 200 Stack Exchange bodies, 100 MBPP, 80 HumanEval, 120 CFPB narratives, 100 Wikipedia paragraphs, `rng = random.Random(1337)`, 200–4000 chars, → `data/benign_v1.jsonl` + `data/benign_v1.manifest.json` with per-record `{id, source, license, sha256, char_len, provenance_url}`. **This is the deciding artifact and it has zero dependencies. It goes first.**<br>5. While it runs: `stack/seed.js` — `db.createCollection("inspect_metrics", {timeseries:...})`, the four indexes, both `createSearchIndex` calls, then the **blocking** `$listSearchIndexes` poll for `status:"READY" && queryable:true`.<br>6. Write `services/inspect/policy.yaml` — nine clauses POL-001…POL-009 with `id`, `class`, `severity`, `text`. This is the file the overlay renders from and it is a submission artifact in its own right.<br>7. NemoClaw express install (5–15 min, runs unattended). |

**Entry condition.** Doors open. Nothing exists but empty directories and pre-staged data, weights and container images.

**Exit criteria (all four, observable):**
1. `curl -s localhost:8000/v1/models` and `curl -s localhost:8001/v1/models` both return a model id.
2. `bench/vision_gate.py` prints p50 and p95 over 20 distinct images, and the numbers are written on the whiteboard whatever they are.
3. In a `chatgpt.com` tab, the content-script console shows `{"ok":true}` returned from the service worker.
4. `mongosh` connects, and `docker exec ... grep heap /tmp/mongot.log` shows a heap under 2 GB.

**Dependency map.**
- **A ← C:** mongo heap verification (blocking, ≤8 min, C calls it out loud).
- **A ← C:** 20 gate chart images. **Unblocked by pre-staging** — `data/images/gate/` is on the USB as data before doors open. A never waits.
- **B ← A:** nothing. B runs `tools/stub_inspect.py` and is fully independent through Phase 0 and most of Phase 1. This is the single most important parallelism decision in the plan.
- **C ← A:** nothing. The corpus build is pure CPU and needs no model.
- **All ← the contract:** frozen at 10:05.

---

### Phase 1 — 10:45 to 12:30 · Core path

Purpose: one real text paste, intercepted in Chrome, inspected by real code on the box, blocked with a real reason.

| A | B | C |
|---|---|---|
| 1. Scaffold `services/inspect/app.py` — FastAPI, uvicorn on `127.0.0.1:8787`. **Tell B the moment it binds; B then kills the stub.** Implement `GET /healthz`, `OPTIONS` handler, and `POST /v1/inspect` returning a hard-coded allow.<br>2. `tiers/t0.py` — `len<40 and no digit and none of {@ : / =}` → ALLOW, `tier:"T0"`.<br>3. `tiers/t1.py` — paste `PAN_RE` + `luhn()` verbatim from §6.2 (already tested 14/14 TP, 0/7 FP). Add the twelve gitleaks prefix rules, `SSN` with a 100-char keyword window, `IBAN`+mod-97, `PEM`, `CONNSTR`, `AWS_ARN`, `looks_like_secret()` entropy composite, the Stripe test-PAN exclusion list, the UUID whitelist, the bare-40-hex-needs-a-keyword rule, and `tabular_pii_score()`.<br>4. `tests/test_t1.py` — pytest with the exact positive and negative sets from the classify spike. **Green before moving on.** These tests are also a submission artifact.<br>5. `tiers/t2.py` — the §6.3 system prompt as a byte-identical module constant + the six few-shot exemplars (four hard negatives). Call `:8000` with `temperature=0.0, seed=1337, max_tokens=200, logprobs=True, top_logprobs=20` and the guided-JSON spelling recorded in `NOTES.md`.<br>6. `verify.py` — `verify(v, payload)` exactly as §6.4, including the whitespace-normalised second pass, returning `override:"unverified_evidence"` on failure. Log every override to a counter exposed on `/healthz`.<br>7. `p_block` from `top_logprobs` over the first token of the `label` value, renormalised across the nine labels. `T=1.0` for now — calibration is Phase 3.<br>8. Wire the router: CACHE → T0 → T1-HIGH → T2. Return the full `airlock.verdict.v1` body with `tier`, `latency_ms`, `bytes_egressed: 0`.<br>9. `curl` the three demo payloads end to end and paste the JSON into the team channel. | 1. Kill the stub the moment A says `:8787` is real. Change nothing else — same port, same contract.<br>2. `airlock.js`: `document.addEventListener('paste', onPaste, true)` at top level, `run_at:"document_start"`, `all_frames:true`, `window.__AIRLOCK__` double-injection guard. **Synchronous** extraction of `text/plain`, `text/html`, and `items[].getAsFile()` for images, then `preventDefault()` + `stopImmediatePropagation()`. Nothing may `await` above that line.<br>3. `beforeinput` second net (12 lines, `inputType === 'insertFromPaste'`), plus `drop` and file-`change` handlers.<br>4. `replayText()` via `document.execCommand('insertText', false, text)` with the React prototype-setter fallback in `setNativeValue()`. **Never assign `.value`. Never dispatch a synthetic `ClipboardEvent`** — it is `isTrusted:false`, performs no default action, and fails silently.<br>5. `replaying` re-entrancy flag so the replay is not itself intercepted.<br>6. `gate()` — async, `withTimeout(inspect(...), 2500)`, **fail closed** to `{action:'block', label:'airlock_unavailable'}` on any throw.<br>7. `viaWorker()` with the `chrome.runtime.id` orphan guard and the `chrome.runtime.lastError` read; `direct()` fallback with `targetAddressSpace:'local'`.<br>8. `sw.js` real: `AbortController` at 2500 ms, `return true`, `warm()` on `onInstalled` and `onStartup`, plus the dev-only tab-reload helper.<br>9. `shrinkToB64(file, 1024)` — `createImageBitmap` → `OffscreenCanvas` → JPEG q=0.82 → chunked `btoa`. **Tell A the exact max edge (1024) so the latency sweep uses the same input distribution.**<br>10. Minimal overlay: Shadow DOM host on `document.documentElement` (not `body` — it is `null` at `document_start`), `all:initial`, `z-index:2147483647`. Scanning chip appears **instantly** on `preventDefault`, before the verdict. Block card renders `reason`, `label`, `ms`, `bytes egressed: 0`. Styling is Phase 2. | 1. OpenShell install and configure. `stack/openshell-policy.toml`: deny-by-default egress, the 5-endpoint allowlist, GitHub explicitly blocked. **Decide now, before 12:30, whether MongoDB gets one of the five endpoints or whether the inspect service stays host-side and only `/v1/inspect` is exposed** — it is a policy-artifact change, not a code change, and it is C's call. Recommended: host-side, expose only `/v1/inspect`, spend zero endpoints on Mongo.<br>2. Verify a denial: `curl` a non-allowlisted host from inside the sandbox and confirm the body is literally `{"error":"policy_denied",...}`. Screenshot it. **This is demo beat 5 and it is now in the bag at 11:15.**<br>3. OpenClaw up. Rule 02 satisfied (3/3).<br>4. Finish `benign_v1.jsonl`; assert `wc -l == 1000`; commit the manifest.<br>5. `bench/build_sensitive.py` → `data/sensitive_v1.jsonl`, n≈400: Stripe's 14 published test PANs and fresh synthetic secrets matching each gitleaks prefix, `PresidioSentenceFaker` for GOV_ID, Synthea for HEALTH_RECORD, Faker CSV blocks for CUSTOMER_RECORD, templated forecast text for FINANCIAL_NONPUBLIC, identifier-rewritten OSS for PROPRIETARY_CODE. **Every artefact embedded in one of ≥20 carrier templates — never a bare PAN.** Plus an explicit `HARD_NEGATIVE` bucket labelled BENIGN: `AKIAIOSFODNN7EXAMPLE`, `user@example.com`, `555-0100`, a git SHA, a UUID, a 10-Q excerpt, Stripe test cards inside a debugging question.<br>6. `services/inspect/mongo.py` — motor client with `directConnection=true`, `write_decision()`, `get_by_hash()`, `rank_fusion_clauses()` using `{$meta:"score"}` / `{$meta:"scoreDetails"}` (**not** `searchScoreDetails`), and the client-side `rrf(k=60)` fallback emitting the identical shape.<br>7. Seed `policy_corpus` with the nine clauses plus ~200 exemplars embedded by bge-small on CPU via ONNX Runtime. Block on the `$listSearchIndexes` READY poll.<br>8. `services/inspect/stream.py` — `tail_decisions()` with the `invalidate` → `startAfter` transition and per-event resume-token persistence. **Without it the console dies permanently the first time the seed script re-drops `decisions`, and it will be re-dropped several times today.** |

**Entry condition.** Gate G1 passed or its declared fallback applied. Extension pings the stub successfully.

**Exit criteria — Gate G2, 12:30:**
Paste a 12-row `name,email,phone,plan,mrr` block into the ChatGPT composer. Observed: the text does **not** appear in the composer; the scanning chip appears within 100 ms; a block card renders within 2500 ms carrying `label:"CUSTOMER_RECORD"`, a `reason`, a latency in ms, and `bytes egressed: 0`; and a document exists in `decisions` with a matching `payload_sha256`. Then paste `"how do I reverse a linked list in Python?"` and observe it appear in the composer normally, with an `ALLOW` line in the log.

**Dependency map.**
- **B ← A (`/v1/inspect`):** the only real cross-dependency in the phase. **Unblocked by `tools/stub_inspect.py`**, which B owns and which conforms to the same contract. B does not stop working for one second if A is late; B simply demos against the stub at 12:30 and swaps at 12:35. Say this out loud at 10:05 so nobody panics.
- **A ← C (MongoDB writes):** A calls `mongo.write_decision()`. **Unblocked by a no-op:** `mongo.py` ships a `MONGO_ENABLED=false` env switch that makes every call a logged no-op returning a fake `decision_id`. A's router never blocks on Mongo, in Phase 1 or on stage.
- **A ← C (policy clauses):** A needs `policy_clause_id` → text. **Unblocked by `policy.yaml`**, a static file C writes at 10:30. Vector retrieval of candidate clauses is an upgrade in Phase 2, never a blocker.
- **C ← A (verdicts to write):** C's console has nothing to display. **Unblocked by `tools/fake_decisions.py`**, which C writes in 10 minutes to insert one synthetic decision per second into `decisions`. B builds and styles the live console against a full-looking stream from 11:00.

---

### Phase 2 — 12:30 to 14:30 · The three beats

Purpose: everything a judge will see, working, once.

| A | B | C |
|---|---|---|
| 1. `tiers/t3.py` — the "transcribe, do not interpret" prompt from §6.3 and the vision JSON schema (`image_type`, `extracted_text` ≤30×100, `org_markers`, `temporal_markers`, `confidentiality_markers`, then label). Call `:8001`.<br>2. Post-process: re-run `t1.scan()` over `" ".join(extracted_text)`. Force BENIGN with `override:"no_grounded_marker"` unless a temporal marker, a confidentiality marker, or a T1 hit is present.<br>3. `tiers/gate_img.py` — the cheap pre-VLM gate: 64×64 downscale, 64-bin colour histogram, Sobel edge density, unique-colour count. **One-sided: it may only fast-pass images it is confident are benign; it may never block.** Instrument the fast-pass rate.<br>4. Wire the sanctioned path: `POST /v1/answer` proxying `:8000` as an SSE stream, taking `{"prompt","decision_id"}`.<br>5. `POST /v1/feedback` → C's `write_back_corpus()`.<br>6. `bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55` — reads `benign_v1.jsonl`, POSTs each to `/v1/inspect` **directly over HTTP, no Chrome in the loop**, writes one doc per item to `benign_eval`, dumps per-item `p_block` to `results/scores_benign.json`. **Running by 13:00.** Use `exact:true` ENN for any vector call inside it — the number must be reproducible when a judge asks.<br>7. First full run on the 200-item dev split. Eyeball the FP list.<br>8. `bench/vision_sweep.sh` — `vllm bench serve --dataset-name random-mm --random-mm-bucket-config '{(720,1280,1):1.0}'` at `c ∈ {1,2,4,8,16}`. Kick it off; it runs while A does other things. | 1. **Finish the overlay properly. This is where pitch-quality points come from; do not under-invest.** Dark card, `backdrop-filter:blur(8px)`, `rise` + `fade` animations, the `<dl>` receipt (Classifier / Confidence / Decided in / Bytes egressed), the two buttons, and the `<pre>` rendering `{"error":"policy_denied","rule":…,"origin":…}` inside the card. Never a native `alert()` — it reads as a crash.<br>2. **Evidence-span highlight.** The verdict carries `evidence_spans` verified to be literal substrings; render the payload with those characters underlined in the card. This is what makes beat 1 visceral rather than assertive.<br>3. **`scoreDetails` tree**, collapsed by default, expandable: per-pipeline rank, weight, contribution, and MongoDB's own plain-English `description` of the RRF formula. 20 minutes; highest-leverage 20 minutes in the MongoDB workstream.<br>4. Live console panel: same shadow root, bottom-left, `pointer-events:auto`, collapsible, one line per decision — `14:22:07  chatgpt.com  text 412ch  ALLOW  p=0.02  T1  188ms`. Backfilled from `GET /v1/decisions?limit=50`, then tailed over `ws://127.0.0.1:8787/v1/stream` with exponential backoff 250 ms → 4 s.<br>5. Image path end to end: `getAsFile` → `shrinkToB64(1024)` → SW → `/v1/inspect` → block card showing the transcribed markers as the reason.<br>6. "Answer this on the local model instead" button → `POST /v1/answer`, render the SSE stream into a panel in the same overlay. **The judge must never see a second browser window.**<br>7. "Mark benign" button on the block card → `POST /v1/feedback`.<br>8. `web/replica/` — a static page served at `http://localhost:5173` that mimics a chat composer: a `contenteditable` div, a send button, nothing else. **This is beat 4's stage, and loopback→loopback means LNA is not involved at all.** | 1. Render the demo chart: a bar chart titled **"FY26 Revenue Forecast — Plan vs. Commit"**, axis labels, and a footer reading **"Internal — Do Not Distribute"**. Export at 1280×720 to `data/images/demo/fy26_forecast.png`. This is not cheating — it is what real internal decks look like, and it means beat 3's block reason is *"the chart title reads FY26 Revenue Forecast and the footer reads Internal — Do Not Distribute"* rather than *"the model thought it looked internal."*<br>2. Render ~100 benign images: matplotlib gallery figures (BSD), Wikimedia Commons charts (CC), screenshots of public docs pages. → `data/images/benign/` + manifest. Image FPR is reported **separately**; never folded into the text denominator.<br>3. `write_back_corpus(decision_id)` — pull the decision, embed its payload with bge-small, insert into `policy_corpus` with `origin:"analyst_override"`, `class:"benign"`. **The procedural-memory beat.**<br>4. Hash-keyed instant-block cache: index confirmed on `decisions.payload_sha256`, `get_by_hash()` wired into A's router at position zero.<br>5. `stack/proof.sh` — the five-block unified-memory evidence script from §4 of the GB10 spike, piped through `tee results/proof_$(date +%s).log`.<br>6. Start `submission/SUBMISSION.md` from the skeleton in §14. **Write every section that does not depend on a number now.** At 16:00 C should be pasting numbers into finished prose, not writing prose.<br>7. Draft the pitch script against §13 and time it with a stopwatch. |

**Entry condition.** Gate G2 passed (or its fallback applied). `/v1/inspect` is the real service, not the stub.

**Exit criteria — Gate G3, 14:30:** all three beats run back to back, in one browser session, without a reload, in under 90 seconds:
1. Customer list → BLOCKED, `CUSTOMER_RECORD`, evidence span underlined.
2. `"how do I reverse a linked list in Python?"` → appears in the composer, `ALLOW` line in the console, no overlay.
3. `fy26_forecast.png` → BLOCKED, `FINANCIAL_NONPUBLIC`, reason quotes the transcribed title and footer.
Plus: `bench/run_fpr.py` has completed at least one full 1000-item pass and `GET /v1/report` returns a real `fpr` with a real `n`.

**Dependency map.**
- **B ← A (`/v1/answer` SSE):** **unblocked by** A shipping the endpoint at 12:35 as a passthrough to `:8000` before T3 exists. B wires the button against real streaming tokens immediately.
- **B ← C (`fy26_forecast.png`):** **unblocked by** any 1280×720 PNG in the interim — B is wiring the transport, not the content. C delivers the real chart by 13:15.
- **B ← A (`evidence_spans`, `score_details`):** **unblocked by** `tools/fixtures/verdict_block.json` and `verdict_allow.json` — two static files A drops at 12:35 containing fully-populated verdicts. B renders against fixtures and swaps to live.
- **A ← C (`benign_v1.jsonl`):** delivered 11:00, well ahead of the 13:00 harness start. **If it slips**, A runs the harness against `data/smoke_20.jsonl` (20 pre-staged items) to prove the harness works, and re-runs on the real corpus when it lands. The harness is never blocked on the corpus.
- **C ← A (`results/scores_benign.json`):** C cannot compute the CI without it. **Unblocked by** C writing `bench/report.py` against a synthetic scores file first, so at 14:35 it is a one-command run.
- **Everybody ← the box:** if A needs to restart a GPU process, A announces it. B and C see fail-closed BLOCK screens for 60 seconds. That is the designed behaviour, not a bug.

---

### Phase 3 — 14:30 to 16:00 · Evaluation

Purpose: produce the artifact that converts one judge vote into three. Nothing new is built. This phase is measurement and prose.

| A | B | C |
|---|---|---|
| 1. Fit the calibration scalar `T`: `scipy.optimize.minimize_scalar(f, bounds=(0.05,10), method="bounded")` minimising NLL on the 200-item dev split. Write `T` into `services/inspect/calib.py`.<br>2. ECE before and after, 10 equal-width bins. Emit `results/reliability.png`.<br>3. Pick τ **on dev**, report **on test**. Default `0.55`.<br>4. Full test run: 1000 benign + 400 sensitive → `results/fpr_report.json`. Must complete in ≤15 min (NFR-T5).<br>5. **The ablation table — four rows, each a real run:** T1-only; T2-only without span verification; T2-only with span verification; full router at τ=0.55. Columns: FPR + Wilson CI, recall, p50, p95, %→LLM. Row 3 minus row 2 is the single best finding in the project if it replicates.<br>6. Escalation rate and cheap-gate fast-pass rate, both instrumented and reported.<br>7. Finish `bench/vision_sweep.sh`; extract images/sec at the largest `c` where E2E p95 ≤ 2.5 s. **Re-run the vision sweep once with the 35B under c=8 load and publish both columns** (NFR-T4).<br>8. Text sweep at `c ∈ {1,8,64,256}`.<br>9. Seats-per-box arithmetic with every bracketed value filled from measurement. State which path binds. **Do not invent a number.**<br>10. Hand `results/*.json` and the sweep tables to C. A's build is over. | 1. **Threshold slider** in the console panel: 0.20 → 0.75, re-thresholding **cached** per-item `p_block` from `results/scores_benign.json`. Instant and exact. Display FPR + recall live as it moves. Label it "scores cached; threshold sweep is exact" — do not imply 1000 fresh inferences.<br>2. Mode dropdown: Audit (0.30) / Balanced (0.55) / Strict (0.20), sent as `mode` in the request.<br>3. `mainworld.js` — the MAIN-world `fetch` patch returning a synthetic `403 {"error":"policy_denied","by":"airlock"}` on `/backend-api/conversation`, bridged over `window.postMessage`, failing closed after 3000 ms. **This is a stretch item. Cut it without hesitation at 16:00 if anything else is amber.**<br>4. `declarativeNetRequest` session rule blocking `||chatgpt.com/backend-api/conversation` behind a "lockdown" toggle. The hard floor that survives a dead service worker.<br>5. Console polish: KV-cache gauges for both vLLM `/metrics` endpoints side by side. **Two models' KV gauges moving on one screen is the unified-memory proof rendered as UI.**<br>6. Screenshot everything at final quality for the submission: block card, evidence highlight, `scoreDetails` tree, console with 900 ALLOW lines scrolled, the slider mid-drag. Hand to C by 15:40. | 1. `bench/report.py` → Wilson 95% CI on every rate, per-class recall table, per-class FP-contribution table, ROC with **log-scale FPR axis** (at 0.3% a linear axis shows nothing), PR curve with AP, reliability diagram. → `results/*.png` + `results/fpr_report.json`.<br>2. **Hand-adjudicate every single false positive.** With FPR <1% that is fewer than ten items. Report the adjudication verbatim in the submission — "7 blocked; on review 3 contained a genuine live-looking key the corpus author had pasted; corrected FP = 4/1000". This turns the corpus's weakness into a demonstration of rigour.<br>3. Inter-rater check: C and whoever is free independently review a random 100 benign items, mark anything not actually benign, report the count and Cohen's κ. 20 minutes, disproportionate credibility.<br>4. Run `stack/proof.sh`, attach the log.<br>5. Paste every number into `SUBMISSION.md`. Prose was written in Phase 2; this is fill-in-the-blanks.<br>6. Write the "things we tested and rejected" section: CUDA MPS (+10% throughput, TTFT 16.7 s → 27.1 s), vLLM sleep mode (offloads to the same DRAM), speculative decoding on the VLM (we emit ≤8 tokens), GridFS (atomicity), Queryable Encryption (Enterprise/Atlas only — we ship AES-GCM with a local key and say so).<br>7. Assemble attachments: `benign_v1.jsonl` + manifest, `sensitive_v1.jsonl`, `run_fpr.py`, `fpr_report.json`, `proof_*.log`, `policy.yaml`, `openshell-policy.toml`, `tests/test_t1.py`. |

**Entry condition.** Gate G3 passed. All three beats have run at least once.

**Exit criteria — Gate G4, 16:00 (feature freeze):** `results/fpr_report.json` exists on disk with `n ≥ 1000`, a `false_pos` integer, an `fpr`, a Wilson `ci95`, and a `by_class` breakdown. The four-row ablation table exists. The vision sweep table exists with a filled images/sec at a stated concurrency and p95. **From this moment no code changes and nothing large is loaded on the host (NFR-S11 — feature freeze is also an allocation freeze).**

**Dependency map.**
- **C ← A (all numbers):** the one true serial dependency of the day. **Mitigated by** A delivering incrementally: dev-split FPR at 14:00, ablation rows as each completes, sweeps last. C never waits for a batch.
- **B ← A (`scores_benign.json`):** **unblocked by** A writing a synthetic 1000-row scores file at 14:35 with the right shape, so B's slider is finished before the real scores exist.
- **A ← B:** nothing. A must not be pulled into UI debugging in Phase 3.

---

### Phase 4 — 16:00 to 16:30 · Dress runs

Purpose: three complete, silent, uninterrupted run-throughs. Code is frozen. The only permitted changes are demo-content and script wording.

| A | B | C |
|---|---|---|
| 1. Re-run `stack/warm.sh` against both servers. Cold JIT on stage is a lost demo.<br>2. `grep MemAvailable /proc/meminfo` — record. If under 8 GB, act now, not at 20:00.<br>3. Confirm the whiteboard total still reads 0.64 and no stray process appears in `nvidia-smi --query-compute-apps`.<br>4. Sit at the terminal for all three dress runs. A's only stage job is the terminal windows and `stack/proof.sh`.<br>5. Pre-stage the exact terminal layout: left = `proof.sh` output, right = `curl` of the OpenShell denial. Font size up. Dark theme. | 1. **Reload the extension, reload every tab. Then do not touch `chrome://extensions` again today.**<br>2. Pre-open the tabs in demo order: `chatgpt.com` (SPA already loaded), `localhost:5173`, the console panel expanded.<br>3. Fire one warm-up paste of each modality so the first stage paste is not the first inference.<br>4. Put the three payloads in a scratch file on screen 2, ready to copy. Never type on stage.<br>5. Drive all three dress runs. Time each with a stopwatch.<br>6. Verify the ethernet-unplug rehearsal on `localhost:5173` — **not** on `chatgpt.com`, because one accidental reload there and the page is gone. | 1. Read the pitch script aloud over B's clicks, all three runs. Cut any sentence that does not land.<br>2. Time-box each beat and write the running clock into the script margin.<br>3. Freeze the deck. Every number on it must match `fpr_report.json` exactly.<br>4. **Final read of `SUBMISSION.md` against §14 with the checklist open.** Top 8 is chosen from this document alone, without a human present.<br>5. Unplug the ethernet once, in the dress run, and plug it back in. Do not discover a DHCP problem at 20:04. |

**Entry condition.** Gate G4 passed. Code frozen.

**Exit criteria — Gate G5, 16:30 (demo freeze):** three consecutive complete run-throughs with zero interventions, each under 5:00 on the stopwatch. If run 3 needed an intervention, run a fourth; if run 4 needs one, cut the failing beat from the script (see §11 G5).

---

### Phase 5 — 16:30 to 17:45 · Writeup and submit

| A | B | C |
|---|---|---|
| 1. Write the technical appendix: exact `docker run` lines, exact flags, container digests, driver version, env vars, and the memory-budget table. Every benchmark number as its full tuple `(metric, percentile, concurrency, input_len, output_len, model, quantization, image resolution, container digest, driver version)`.<br>2. Answer C's factual questions. Nothing else.<br>3. **Do not touch a GPU process.** | 1. Final screenshots at full resolution if any are missing.<br>2. Write two paragraphs on the MV3 interception mechanism: why the clipboard payload and not the screen, why the service-worker fetch and not the content-script fetch (LNA), why `execCommand('insertText')` and not a synthetic `ClipboardEvent`.<br>3. Then stop touching Chrome. | 1. Assemble, proofread, attach, **submit by 17:45** — fifteen minutes of buffer before the 18:00 cut-off, because the upload will be slow when 40 teams submit at once.<br>2. Confirm the submission renders correctly in the portal preview.<br>3. Announce "SUBMITTED" out loud. |

**Entry condition.** G5 passed. **Exit criteria:** a submission confirmation on screen, screenshotted, before 17:45.

---

## 11. Gates and Decision Rules

Every gate has a pre-declared failure action with a time limit. **No gate may resolve to "debug it."** When a gate fails, the fallback is executed immediately by the owner without a team discussion; discussion happens after the fallback is running.

---

### **G0 — 10:05 · Driver version** · Owner A

**Pass:** `nvidia-smi --query-gpu=driver_version --format=csv` reads **580.x**.

**Fail (590.x):** **Hard stop, 15-minute budget.** Do not launch anything. 590.x causes CUDAGraph deadlocks — a demo that hangs mid-paste with no error. Attempt a downgrade to the 580 branch. If not complete by **10:20**, A relaunches both servers with `--enforce-eager` for the whole day, accepts the latency hit, moves the vision config immediately to NFR-L4b (`max_pixels=401408`, `max_tokens=1` + logprobs), and C writes the constraint into the submission as a stated environment limitation. **Never launch on 590.x with CUDA graphs enabled.**

---

### **G1 — 10:45 · Vision latency (NFR-L4)** · Owner A

**Pass:** over **20 distinct** 1280×720 chart images at `max_pixels=1003520`, ≤8 output tokens: **p50 ≤ 1.5 s AND p95 ≤ 2.5 s**.

*This is the single largest unverified number in the project — no first-party VLM image-throughput measurement exists for GB10 anywhere. Everything downstream waits for A's report and nothing may assume the result.*

**Fail, step 1 — 15 minutes:** drop to **NFR-L4b**: `max_pixels=401408` (512 visual tokens, 0.40× prefill), `max_tokens=1` with `logprobs=5`, reading the logprob margin between the `BLOCK` and `SAFE` first tokens. This also yields a continuous confidence score for free. Re-measure. Pass criterion unchanged.

**Fail, step 2 — 20 minutes, deadline 11:20:** swap weights to `nvidia/Qwen2.5-VL-7B-Instruct-NVFP4` — same `Qwen2_5_VLForConditionalGeneration` code path, NVIDIA-validated on Spark, ~2× prefill throughput. Re-measure.

**Fail, step 3 — deadline 11:35, final:** `max_pixels=200704` (256 tokens, 0.20× prefill), and B's client downscale drops to a 640 px long edge. Accept whatever p95 results and **state it honestly on the slide** as the measured number with its configuration. A slow, honest, measured image path beats a fast unmeasured claim.

**Catastrophic fail (vision server will not load at all, 11:35):** cut beat 3 to a **pre-recorded 15-second screen capture**, labelled on screen as a recording, and re-point the live demo at the text beats. C rewrites the pitch to lead with the FPR artifact. **Do not spend the afternoon on a VLM that will not boot** — the deciding artifact is the false-positive rate, not the image.

---

### **G1-B — 10:45 · Browser transport** · Owner B

**Pass:** a content script on `https://chatgpt.com` round-trips a message through the service worker to `http://127.0.0.1:8787/healthz` and back.

**Fail — 10 minutes:** if Chrome is 142.x/143.x, set `chrome://flags#local-network-access-check → Disabled` and relaunch. **Fail again — 10 minutes:** relaunch Chrome with `--user-data-dir=/tmp/airlock-profile` (also the fix for a corp-managed profile blocking developer-mode extensions). **Fail again — deadline 11:15:** switch to the **Tampermonkey userscript** path — the same `airlock.js` with `GM_xmlhttpRequest` in place of `chrome.runtime.sendMessage`, which is CORS- and LNA-free by construction. Keep the file dual-mode with one `typeof GM_xmlhttpRequest` branch so no other code changes. Weaker pitch, identical demo.

---

### **G2 — 12:30 · End-to-end text block** · Owner B, verified by all three

**Pass:** the customer-list paste is intercepted in the real ChatGPT composer and blocked by a verdict produced by A's real `/v1/inspect`; the benign Python question passes through and appears in the composer.

**Fail because A's service is not ready — 0 minutes:** B demos against `tools/stub_inspect.py` and the gate is recorded as **conditionally passed**. A has until **13:15** to land the real service. This is not a slip; it is why the stub exists.

**Fail because interception does not work — 20 minutes:** switch the demo surface from `chatgpt.com` to B's `localhost:5173` replica page for **all** beats. Loopback→loopback removes LNA entirely and the replica has no framework fighting for the paste event. Cost: the pitch line becomes "our replica of a chat composer" instead of "your actual ChatGPT tab" — a real loss on the *usefulness* axis, but a working demo. **Deadline 12:50.**

**Fail because the replay corrupts the composer — 0 minutes:** stop replaying. On `allow`, do not re-inject; instead show a one-second green "cleared" chip and let the user paste again. Degrades beat 2 from invisible to one extra keystroke. Note it honestly.

---

### **G3 — 14:30 · All three beats** · Owner B, verified by all three

**Pass:** beats 1, 2, 3 run back to back in one session, no reload, under 90 seconds; and `bench/run_fpr.py` has completed one full 1000-item pass.

**Fail on beat 3 only — 20 minutes:** apply the G1 ladder one step further; if already at the bottom, pre-record beat 3.

**Fail on the FPR harness — 30 minutes, deadline 15:00:** if the harness is not producing `benign_eval` documents, bypass MongoDB entirely — write results to `results/benign_eval.jsonl` and compute the aggregation in pandas. **The number matters more than where it is stored.** Keep the MongoDB aggregation pipeline in the submission as the production path and say the run was written to disk.

**Fail on the whole thing (any beat structurally broken at 14:30):** **cut in this pre-declared order and do not deviate:** self-consistency sampling → MongoDB `$rankFusion` clause retrieval (fall back to `policy.yaml` static enum) → the PR curve → the benign *image* corpus → the MAIN-world fetch patch → the `scoreDetails` tree. **Never cut:** the 1000-item benign FPR with a Wilson CI, the evidence-span verification, or the four-row ablation table. Those three are the score.

---

### **G4 — 16:00 · Feature freeze** · Owner C

**Pass:** `results/fpr_report.json` exists with `n ≥ 1000`, an integer `false_pos`, an `fpr`, a `ci95`, and `by_class`. The ablation table has four rows. The vision sweep has a filled images/sec at a stated `c` and p95.

**Fail — the numbers are not ready:** freeze anyway. **The freeze time does not move.** Report whatever `n` actually completed, with its own Wilson CI — 500/500 with an honest CI beats 1000 claimed. If `n < 300`, C reframes the artifact in the submission as "measured over n=X, harness and corpus attached, full 1000-item run reproducible with one command" and ships the corpus and the script. The reproducibility is worth nearly as much as the number.

**From 16:00: no code changes, and nothing large is loaded on the host (NFR-S11).**

---

### **G5 — 16:30 · Demo freeze** · Owner B

**Pass:** three consecutive complete run-throughs, zero interventions, each under 5:00.

**Fail — one intervention in run 3:** run a fourth. **Fail again:** **cut the beat that failed** from the stage script and move it to the written submission as a screenshot with a caption. A four-beat demo that runs clean beats a six-beat demo that stalls. Decision is B's, made in under 60 seconds, not debated.

**From 16:30: nobody touches `chrome://extensions`, nobody restarts a GPU process, nobody edits a file under `extension/` or `services/`.**

---

### **G6 — 17:45 · Submit** · Owner C

**Pass:** submission confirmation on screen, screenshotted.

**Fail — the portal is slow or rejecting:** C submits a reduced version immediately (prose + `fpr_report.json` + two screenshots) and follows with attachments if the portal allows edits. **An incomplete submission at 17:50 scores; a perfect one at 18:01 does not.** The 15-minute buffer exists precisely because 40 teams will upload simultaneously.

---

## 12. Risk Register

P = probability, I = impact. Ordered by P×I.

| # | Risk | P | I | Owner | Mitigation | Trigger that fires it |
|---|---|---|---|---|---|---|
| R1 | **Host freeze from OOM** — unbounded allocation hangs the whole box, no SSH, no ping. Total loss of the day. | Med | **Fatal** | A | NFR-S1 (only A launches GPU processes); summed util capped at 0.64 against a 0.85 ceiling; `swapoff -a` + `drop_caches` before every launch; mongot capped at a 6 GB cgroup; explicit `--gpu-memory-utilization` on every launch; whiteboard running total updated *before* launch | `MemAvailable < 8 GB` in `/proc/meminfo` → A stops `airlock-vision` immediately, `docker stop`, `drop_caches`, relaunch. If it fires twice → headless serving mode, reclaiming 10–15 GB from GNOME |
| R2 | **Vision latency misses the gate** — the single largest unverified number in the project | **High** | High | A | Three-step ladder pre-declared in G1: `max_pixels` 1003520 → 401408 → 200704, then a weights swap to `Qwen2.5-VL-7B-Instruct-NVFP4`, then `max_tokens=1` + logprobs | G1 measurement at 10:45 |
| R3 | **A's `/v1/inspect` is late and blocks B** | High | Med | B | `tools/stub_inspect.py`, owned by B, conforming to the frozen `CONTRACT.md`. B is never idle and never blocked; the swap is a one-line URL change that is already the same URL | A has not announced `:8787` live by 12:15 → B demos G2 against the stub, gate recorded conditionally passed |
| R4 | **FPR harness does not finish 1000 items in time** | Med | **High** (it is the deciding artifact) | C | Harness runs direct over HTTP with no browser; started by 13:00, four hours of slack; MongoDB write path is bypassable to a JSONL file | Not producing documents by 14:30 → bypass Mongo, compute in pandas, keep the aggregation pipeline in the writeup as the production path |
| R5 | **Chrome LNA blocks the local fetch** (142/143 bugs) | Med | High | B | Service-worker fetch with `host_permissions` is the exempt path, not the content script; checked at 10:20 in G1-B; three escape hatches pre-declared | `chrome://version` < 144.0.7512.0 at 10:20 → flag, then fresh profile, then Tampermonkey |
| R6 | **Site handler wins the paste** (ProseMirror/Lexical/React) | Med | High | B | `document`-level capture at `run_at:"document_start"` + `stopImmediatePropagation()`; `beforeinput` as a second net; bind to `document`, never to selectors | Paste text appears in the composer despite a block verdict → switch demo surface to `localhost:5173` replica (G2 fallback) |
| R7 | **`return true` missing in the MV3 `onMessage` listener** — `sendResponse` becomes a no-op, everything times out, everything blocks, and it looks exactly like model slowness | Med | Med | B | Present from the first line of `sw.js`; **it is the first thing to check on any "the model is slow" report** | Every verdict is `airlock_unavailable` at exactly 2500 ms → check `sw.js` before touching anything on the box |
| R8 | **mongot JVM takes 32 GB** of the pool vLLM sized itself against | Low | **Fatal** | C | `--memory=6g --memory-swap=6g --cpus=4`; verified within 5 minutes of first boot, before A launches server #1 | `docker stats` shows >4 GB, or `/tmp/mongot.log` shows a large `Xmx` → add `-e JAVA_TOOL_OPTIONS="-Xms1g -Xmx2g"`; if that fails, run plain `mongo:8` without mongot and use the client-side RRF fallback |
| R9 | **Cold torch.compile on stage** — 25–57 s on the first request | Med | **High** | A | `stack/warm.sh` after every launch and again at 16:30; a warm-up inspect fired on tab load | Any restart, at any time, for any reason → re-run `warm.sh` before the next paste |
| R10 | **Search index not queryable** — `$vectorSearch` against a non-READY index returns **empty results, not an error**, which looks like a broken detector and sends the team debugging the wrong layer | Med | Med | C | `$listSearchIndexes` READY poll as a **blocking** step in `seed.js`; clause retrieval degrades to the static `policy.yaml` enum, never to silent-allow | Retrieval returns zero clauses → check `queryable`, not the embeddings |
| R11 | **Change stream dies after a re-seed** — `resumeAfter` cannot cross an `invalidate`, and `decisions` is dropped several times today | **High** | Low | C | `invalidate` → `startAfter` transition implemented in `stream.py` from the first version; token persisted every event; harness writes to `benign_eval`, never `decisions`, so the 1000-doc burst cannot roll the oplog under the console | Live console stops updating after a seed → confirm the transition fired before suspecting the socket |
| R12 | **Extension context invalidated** — reloading the extension orphans every open tab's content script | **High** | Med | B | `chrome.runtime.id` guard → `direct()` fallback → fail-closed BLOCK; auto tab-reload on `onInstalled` in dev | Any extension reload → reload every tab, every time, no exceptions. After 16:30, no reloads at all |
| R13 | **Corpus licensing challenged** by a judge (Stack Exchange LLM-training terms) | Low | Med | C | Six independent sources so no single licence can sink the denominator; `ATTRIBUTION.md` with post IDs and authors; the CFPB snapshot date recorded | A judge raises it → the pre-computed answer: drop SO to 100, raise WildChat to 500 (ODC-BY, no such condition), and re-report — the corpus is regenerable with one seeded command |
| R14 | **Judge asks "did you test regexes against strings you generated to match them?"** | **High** | Med | C | The `HARD_NEGATIVE` bucket is reported as its own line; every artefact embedded in one of ≥20 carrier templates; the honest framing is pre-scripted: *"our sensitive set is synthetic, so recall is an upper bound; our benign set is human-written, so FPR is the number we stand behind"* | The question is asked → deliver the sentence verbatim |
| R15 | **Ethernet-unplug beat kills the tab** — a reload of `chatgpt.com` while offline loses the page permanently | Med | Med | B | Beat 4 runs on `localhost:5173`, never on `chatgpt.com`; rehearsed with the cable actually out in the dress run | Nothing to trigger — this is a rule, not a response. Never unplug while the `chatgpt.com` tab is focused |
| R16 | **Someone slides a VRAM bar onto a slide.** `nvidia-smi` on GB10 prints `Memory-Usage: Not Supported` by design — an iGPU has no framebuffer, and NVIDIA documents this. A judge who owns this box knows it | Low | High | C | Memory evidence comes only from `--query-compute-apps` plus `/proc/meminfo`; `stack/proof.sh` is the artifact; the missing bar is the punchline, not a gap | Deck review at 16:00 → any VRAM bar is deleted on sight |
| R17 | **Both beats run over time and the 5 minutes expires before the FPR number** | Med | High | C | Stopwatch on all three dress runs; per-beat second budgets in §13; the cut list is pre-declared | Dress run exceeds 4:45 → cut the mark-benign beat first, then the sanctioned-answer beat. **Never cut the FPR number — it is the reason the pitch exists** |

---

## 13. Demo Runbook

**Total: 5:00.** B drives the browser. C narrates. A drives the terminal and says nothing unless asked a direct technical question. Every payload is pre-staged in a scratch file on the second screen — **nobody types on stage.**

### Pre-stage checklist (16:30, then re-verified at 19:50)

- Both vLLM servers warm (a paste of each modality already fired).
- `chatgpt.com` tab loaded and scrolled to the composer. **Do not reload it again, ever.**
- `localhost:5173` replica tab loaded in the background.
- Console panel expanded, showing the backfilled ALLOW lines.
- Two terminals up on A's screen: `proof.sh` output, and a ready-to-run `curl` of the OpenShell denial.
- Ethernet cable accessible, with slack, not behind the table.
- Font sizes up, dark theme, notifications off, screensaver off.

---

### 0:00–0:35 — The problem · C narrates, nothing on screen but the composer

> "Every one of your employees has a browser tab open to a model you don't run. The data that leaves through that tab doesn't leave through your firewall — it leaves through a paste. Airlock is a bouncer that sits on the paste."

---

### 0:35–1:10 — **Beat 1: customer list → BLOCKED**

**B:** pastes a 12-row `name,email,phone,plan,mrr` block into the ChatGPT composer.
**On screen:** the text never appears. The scanning chip appears instantly. The block card renders with `CUSTOMER_RECORD`, the offending row **underlined** as the verified evidence span, `bytes egressed: 0`, and the decision latency in ms.
**C:** *"That never left the laptop. And notice what the block says — it quotes the exact characters that caused it, and we verified that string is literally present before we blocked. A filter could have caught that one."*

**Recovery:** if the card does not render but the console logs a BLOCK, C says *"the overlay is showing us the verdict in the console instead"* and points at the log line. If nothing happens at all, B pastes the same payload on `localhost:5173` — one tab switch, three seconds.

---

### 1:10–1:25 — **Beat 2: benign Python question → sails through**

**B:** pastes *"how do I reverse a linked list in Python?"*
**On screen:** the text appears in the composer normally. No overlay. One `ALLOW` line scrolls in the console at single-digit milliseconds, `tier: T1`.
**C:** *"No friction. That's the whole game — a control nobody turns off. That one was decided in under a millisecond and never touched a model."*

**Recovery:** if it blocks, C says *"and there's a false positive — let me show you exactly how often that happens"* and jumps straight to the FPR section. **A false positive on stage is survivable if and only if you have the denominator.** That is the entire argument for the artifact.

---

### 1:25–2:05 — **Beat 3: image of an unreleased revenue chart → BLOCKED**

**B:** pastes `fy26_forecast.png`.
**On screen:** scanning chip says "inspecting image locally". Block card: `FINANCIAL_NONPUBLIC`, reason quoting the transcribed title *"FY26 Revenue Forecast"* and the footer *"Internal — Do Not Distribute"*.
**C:** *"No regex catches a picture. That's a 7-billion-parameter vision model reading the chart's title and footer on this box, in [X] milliseconds. And notice it didn't try to read the bars — we deliberately never ask it to read data values, because that's the thing these models are worst at. We ask it to read the chrome, which is what actually determines confidentiality."*

**Recovery:** if it times out, the fail-closed BLOCK screen renders instead and C says *"and there's the fail-closed path — when the inspector can't reach a verdict, nothing leaves. Deny by default is the product, so it's also the failure mode."* **This failure is on-message.** If the pre-recorded fallback is in play, B plays the 15-second clip, labelled as a recording.

---

### 2:05–2:35 — **The sanctioned path**

**B:** clicks **"Answer this on the local model instead."**
**On screen:** tokens stream into the overlay from the 35B on the box.
**C:** *"Blocking alone pushes people to their phones. So the same question gets answered — by a 35-billion-parameter model running eighteen inches away. Nothing about that round trip left the room."*

**Recovery:** if the stream stalls, B closes the panel; C says *"that's the local 35B, and you'll see it live in the terminal in ten seconds"* and hands to A's `proof.sh`, which shows both `/v1/models` responding.

---

### 2:35–3:00 — **Beat 4: the detector learns**

**B:** on a fresh block card, clicks **"Mark benign."** Re-pastes the same payload → it sails through. Then pastes a *near neighbour* → it still blocks.
**C:** *"An analyst just corrected it. The payload and its embedding went back into the corpus in MongoDB, and the next paste of that shape passes — while a neighbour still blocks. The detector learned without retraining a model. You cannot do that with a regex."*

**Cut first if running long.**

---

### 3:00–3:25 — **`policy_denied` and the unplug**

**A:** runs the pre-staged `curl` from inside the sandbox. Raw `{"error":"policy_denied","rule":...,"endpoint":...}` on screen.
**C:** *"That's the sandbox layer — deny-by-default egress, five allowlisted endpoints, GitHub blocked. Byte for byte the same JSON the browser renders. Two layers, one denial shape."*

**B:** switches to `localhost:5173`. **A unplugs the ethernet.** B pastes the customer list again → still blocked. `free -h` and both `/v1/models` visible on A's terminal.
**C:** *"Cable's out. Still blocking, still answering. There is no cloud in this system."*

**Recovery:** the cable goes back in immediately afterwards, before anything else. If the replica page misbehaves offline, the beat becomes A's terminal alone — `curl localhost:8000/v1/models` with the cable visibly out is sufficient proof.

---

### 3:25–4:20 — **The number** ← *never cut this*

**B:** scrolls the console — hundreds of ALLOW lines — then opens the report panel.
**C:** *"Three pastes is a demo. Here's the detector. We measured a **[X]%** false-positive rate, 95% confidence interval **[a, b]**, over **1,000 benign pastes we did not write** — 400 real ChatGPT prompts from WildChat, 200 Stack Overflow questions, 180 code problems from MBPP and HumanEval, 120 CFPB consumer complaints, 100 Wikipedia paragraphs. The published industry average for DLP false positives is 51%."*

**B:** drags the threshold slider 0.55 → 0.30. FPR and recall move live.
**C:** *"Every DLP product has this dial. The difference is where it lives. On a cloud DLP you file a ticket and wait a quarter, and you never see the curve. Here the curve is on your desk — because the corpus and the inference are both on the box."*

**Recovery:** if the slider misbehaves, C reads the three-row table off the deck. The number is the asset; the slider is the flourish.

---

### 4:20–5:00 — **The box, and the close**

**A:** `stack/proof.sh` on screen.
**C:** *"`nvidia-smi` won't show you a VRAM bar on this machine. That's not a bug — there is no VRAM. The 35-billion-parameter text model and the 7-billion-parameter vision model are both resident, right now, in the same 128 gigabytes the operating system is running in. On a 24-gigabyte discrete GPU neither fits next to the other and you'd be swapping over PCIe between every paste. Here there is no PCIe to swap across.*
> *NVIDIA's own reference recipe for this exact text model runs at 40% memory utilisation. We're at 64% with two models and [Y] gigabytes still free.*
> *At the measured throughput that's **[Z] seats per box**, bound by the vision path, at 160 watts — about €350 a year of electricity for the whole fleet. That's how you get to Dell's 87% number: you stop paying per token, and you stop paying the interruption tax."*

---

## 14. Submission Checklist

The top 8 is chosen at 18:00 **from the written submission alone**, with nobody in the room to explain anything. Assume a skimming reader who reads the first 200 words and the tables, then decides whether to read the rest. Everything below is mandatory unless marked optional.

### Structure — in this order

- [ ] **Title and one-sentence thesis.** *"Airlock intercepts the clipboard payload the moment company data is about to leave a laptop for an unapproved cloud AI tool, inspects it locally, blocks it, and re-routes the question to a 35B model on the box so the employee still gets an answer."*
- [ ] **The headline number, in the first 100 words.** FPR with its denominator and Wilson CI, against the 51% industry average. If it is not on the first screen, it does not exist.
- [ ] **Three screenshots above the fold:** the block card with the underlined evidence span; the live console scrolled through hundreds of ALLOW lines; `proof.sh` showing two models resident in one pool.

### The deciding artifact

- [ ] FPR as `FP / N`, **N = 1000**, with a **Wilson 95% CI**. If FP = 0, write *"below 0.3% at 95% confidence by the rule of three"* — **never write "zero"**.
- [ ] Per-modality FPR reported **separately** (text and image). The image FPR has never been measured by anyone.
- [ ] Full 2×2 confusion matrix; per-class recall table; per-class FP-contribution table **including your worst class, named**. Publishing the weak class is what makes the strong ones believable.
- [ ] **Hand-adjudication of every false positive**, itemised. *"7 blocked; on review 3 contained a genuine live-looking key the corpus author had pasted; corrected FP = 4/1000."*
- [ ] Corpus provenance table: source, n, licence, snapshot date, URL, for all six sources.
- [ ] `HARD_NEGATIVE` bucket results as their own line.
- [ ] Inter-rater check: n reviewed, disagreements, Cohen's κ.
- [ ] Reproduction command, verbatim: `python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55` → `results/fpr_report.json`.
- [ ] The MongoDB aggregation that computes it, pasted in full.
- [ ] Precision at a stated prevalence, with the arithmetic shown: at π=2%, TPR=0.95, FPR=0.003 → precision 0.866; at FPR=0.03 → precision 0.393. **This one line is the entire argument for why FPR matters more than recall.**

### Technical execution

- [ ] The four-row **ablation table** — T1-only / T2-only / T2 + span verification / full router — with FPR+CI, recall, p50, p95, %→LLM. One sentence of interpretation per row.
- [ ] Span verification described as a **mechanism**, with the override rate reported as a number.
- [ ] Latency table (NFR-L1…L8) with targets and measured p50/p95.
- [ ] Every benchmark number as its full tuple: metric, percentile, concurrency, input_len, output_len, model, quantization, image resolution, container digest, driver version. Median of 3, 2 warm-ups discarded.
- [ ] Text concurrency sweep at c ∈ {1,8,64,256}.
- [ ] Vision sweep at c ∈ {1,2,4,8,16}, **run twice — idle and under 35B c=8 load, both columns published.** A benchmark that shows its own degradation is the most credible thing in the document.
- [ ] The section titled **"First measured VLM image-inspection throughput on NVIDIA GB10"**, with the naive 413 s/image literature baseline quoted as the thing you designed around.
- [ ] The explicit statement that vision is prefill-bound and scales 1.5–2.5×, **stated before the data is shown**. Claiming linear vision scaling to a Dell/NVIDIA judge is instant credibility loss.
- [ ] Reliability diagram before/after temperature scaling, with ECE on each.
- [ ] ROC (log-scale FPR axis) with AUC and three annotated operating points; PR curve with AP.
- [ ] **"Things we tested and rejected"**: CUDA MPS (+10% throughput, TTFT 16.7 s → 27.1 s); vLLM sleep mode (offloads to the same DRAM); speculative decoding on the VLM (we emit ≤8 tokens — kept on the 35B where it is worth 2.7×); GridFS (atomicity, two collections, fragments the one-document-one-decision story); Queryable Encryption (Enterprise/Atlas only).

### Local-first

- [ ] `proof.sh` output attached as a log file, with the explanation that `nvidia-smi` cannot show a memory bar on an iGPU **and NVIDIA's own citation for it**. **No VRAM bar appears anywhere in the document.**
- [ ] Memory budget table: per-process `--gpu-memory-utilization` fractions, GB, the 0.85 ceiling, the 126.5 GB crash ceiling, and the headroom.
- [ ] The NVIDIA-playbook comparison: their flagship recipe for this exact model runs at 0.40; Airlock runs two models at 0.64 with GB free.
- [ ] The **hidden multimodal-cache finding** (defaults are 4 GiB + 8 GiB, duplicated per API and engine-core process, living in the same unified pool — 15–20 GB of invisible consumption). **Nobody in the DGX Spark literature has written this down.**
- [ ] Offline evidence: beat 4 described, with the `free -h` + `/v1/models` screenshot taken with the cable out.
- [ ] The OpenShell policy artifact (`openshell-policy.toml`) attached, plus the raw `{"error":"policy_denied",...}` denial, plus the note that the browser layer emits the byte-identical shape.
- [ ] `DO_NOT_TRACK=1` on the MongoDB container, explained: *an unsolicited outbound call is exactly the thing this product claims to prevent.*
- [ ] Honest boundary statements: MongoDB Community runs without auth on loopback; Queryable Encryption is the production path and is unavailable in Community, so evidence is AES-GCM encrypted with a key in a 0600 file that never leaves the box; the MAIN-world patch is the unmanaged-browser approximation of a policy-force-installed extension with blocking `webRequest`.

### Usefulness

- [ ] Seats per box = `min(seats_vision, seats_text)`, **naming which binds**, with every assumption on the page (P=40 pastes/day, peak factor 4×, measured f_img).
- [ ] Escalation rate — % of pastes that ever reach a model — as the throughput multiplier.
- [ ] Cost: 160 W at the wall, ~€350/yr electricity, divided by seats, compared against per-seat cloud DLP + cloud LLM API. **Earn the 87% figure, do not quote it.**
- [ ] The interruption-tax arithmetic: 5,000 employees × 40 pastes/week; at the 51% industry average that is 102,000 wrong interruptions a week; at the measured rate it is [N].
- [ ] Three named operating points (Audit / Balanced / Strict) with their τ, recall and FPR.

### Attachments

- [ ] `data/benign_v1.jsonl` + `benign_v1.manifest.json` + `ATTRIBUTION.md`
- [ ] `data/sensitive_v1.jsonl`
- [ ] `bench/run_fpr.py`, `bench/build_benign.py`, `bench/report.py`
- [ ] `results/fpr_report.json`, `results/proof_*.log`, `results/*.png`
- [ ] `services/inspect/policy.yaml` (the nine clauses)
- [ ] `stack/openshell-policy.toml`
- [ ] `tests/test_t1.py` with its passing output
- [ ] The exact `docker run` lines for both vLLM servers and MongoDB, with container digests, driver version and env vars
- [ ] *(optional)* a 60-second screen capture of the three beats, as insurance against a live-demo failure at 20:00

### Final read, 17:30 — three checks

1. **Does the first screen contain the FPR with its denominator?** If not, move it up.
2. **Does any number in the prose disagree with `fpr_report.json`?** Grep for every digit.
3. **Is there a claim anywhere that was not measured?** Delete it or mark it explicitly as derived arithmetic pending measurement. One unsupported number invalidates the supported ones.

**Submit by 17:45. Not 17:55.**