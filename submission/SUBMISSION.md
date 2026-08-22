<!--
  submission/SUBMISSION.md — owner C. SRS §14.

  THE TOP 8 IS CHOSEN AT 18:00 FROM THIS DOCUMENT ALONE, with nobody in the room to
  explain anything. Assume a skimming reader who reads the first 200 words and the
  tables, then decides whether to read the rest.

  EVERY double-brace placeholder is filled from results/fpr_report.json by:

      python submission/fill.py

  Do not type numbers in by hand. The 17:30 check is "does any number in the prose
  disagree with fpr_report.json?" — fill.py makes that check vacuous by construction.

  Prose was written in Phase 2. Phase 3 is fill-in-the-blanks. SUBMIT BY 17:45.
-->

# Airlock — the bouncer that sits on the paste

**Airlock intercepts the clipboard payload the moment company data is about to leave a
laptop for an unapproved cloud AI tool, inspects it locally on the GB10, blocks it with a
cited policy clause, and re-routes the question to a 35B model on the box so the employee
still gets an answer.**

We measured a **{{FPR_HEADLINE}}** false-positive rate over **{{N}} benign pastes we did
not write**, drawn from {{N_SOURCES}} independently-licensed public sources of real
human-written text. The published industry average for DLP false positives is **51%**.

That number is the submission. Everything else is how we got it and why it holds.

<!-- THREE SCREENSHOTS ABOVE THE FOLD — SRS §14 -->
![Block card with the verified evidence span underlined](../screenshots/verdict-card.png)
![Live console after several hundred decisions](../screenshots/console.png)
![proof.sh — two models resident in one 128 GB pool](../screenshots/proof.png)

---

## 1. The problem, stated precisely

Every employee has a browser tab open to a model the company does not run. Data that
leaves through that tab does not leave through the firewall — it leaves through a paste.
Network DLP cannot see it, because by the time the bytes are on the wire they are inside
a TLS session to a domain the company has no reason to block.

The control that would work — inspect the payload before it leaves the endpoint — has
been impractical for one reason: doing it well needs a language model, and sending every
paste to a cloud model to check whether it should go to a cloud model is absurd. So the
industry ships regexes, and regexes produce the 51% false-positive rate that makes
employees route around the control entirely.

**A 128 GB unified-memory box changes the arithmetic.** The inspection model can live on
the endpoint. That is the whole thesis, and it is testable: if local inspection cannot get
the false-positive rate low enough to be left switched on, the idea fails. So we measured
it.

---

## 2. The deciding artifact — false-positive rate with a denominator

### Headline

| | |
|---|---|
| **False-positive rate** | **{{FPR_STATEMENT}}** |
| Denominator | {{N}} benign pastes, {{N_SOURCES}} sources, none written by us |
| Threshold | {{THRESHOLD}} (Balanced) — selected on dev, reported on test |
| Latency p50 / p95 | {{P50}} ms / {{P95}} ms |
| Escalation rate (reached a model at all) | {{ESCALATION}} |
| Recall (synthetic sensitive set) | {{RECALL_STATEMENT}} |

Reproduce, verbatim:

```bash
python bench/build_benign.py --seed 1337
python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55
python bench/report.py
```

### Precision at prevalence — why FPR matters more than recall

At a 2% prevalence of genuinely sensitive pastes, with our measured recall and FPR,
precision is **{{PRECISION_AT_2PCT}}**. Hold recall constant and raise the false-positive
rate to 3% and precision collapses to **{{PRECISION_AT_3PCT_FPR}}**.

That is the entire argument. A detector at 3% FPR is wrong more often than it is right,
and a control that is wrong more often than it is right gets switched off — after which
its recall is zero, whatever the datasheet said.

### Corpus provenance

{{CORPUS_TABLE}}

Multiple independent sources, so no single licence challenge can sink the denominator.
Where a source was unavailable at build time its share was redistributed across the
others and the manifest records the actual counts — the table above is what was used,
not what was planned. The corpus is regenerable from one seeded command; full per-record provenance
(`id, source, licence, sha256, char_len, provenance_url`) is in
`data/benign_v1.manifest.json` and `data/ATTRIBUTION.md`.

### Which tier resolved each paste — and what that does to the throughput numbers

{{TIER_MIX_TABLE}}

**We are stating this before anyone finds it.** Our benign corpus has a 200-character
floor. The T0 fast path fires only below 40 characters. So **T0 cannot fire on this
corpus by construction** — measured: 0 of 1000 items resolved at T0, and essentially the
entire corpus escalated to the language model.

That cuts two ways, and we report both:

- **It makes the false-positive rate stronger, not weaker.** Every item reached the
  classifier. Nothing was cheaply resolved by a length check before the model saw it. The
  FPR above is measured entirely on the hard subset, which is the conservative direction.
- **It makes our throughput figures unrepresentative.** Escalation rate, blended latency
  (NFR-L8) and seats-per-box (NFR-T7) all scale with the fraction of pastes that reach a
  model. Measured on a corpus that excludes short pastes entirely, those three numbers
  describe a worst case, not a realistic deployment. **We do not claim the ~14%
  escalation the design assumed.** Where those numbers appear below, they carry this
  caveat.

To show the fast path works rather than reporting one we never exercised, we ship a
separate **T0 probe set** (`data/shortpaste_v1.jsonl`) of short benign pastes that do
satisfy the gate. It is reported as its own line and is **never merged into the n=1000
denominator**:

{{T0_PROBE_RESULT}}

A realistic paste distribution contains a great many short messages, so a deployed
Airlock would resolve a substantial share at T0 for roughly a millisecond each. We have
not measured that share on real traffic, and we do not assert it.

### Hand-adjudication of every false positive

{{ADJUDICATION}}

Every false positive is itemised in `results/false_positives.md` with its `p_block`, tier,
predicted label and evidence span. We adjudicated each one by hand rather than reporting a
raw count, because a benign corpus scraped from the internet contains real secrets that
their authors pasted, and counting those against the detector would understate it.

### Per-source false-positive contribution

{{BY_SOURCE_TABLE}}

Our worst source is named in that table. Publishing the weak one is what makes the strong
ones believable.

### Recall by class

{{BY_CLASS_TABLE}}

**Honest framing, stated before anyone asks:** our sensitive set is synthetic, so recall
is an upper bound. Our benign set is human-written, so **FPR is the number we stand
behind**. Every synthetic artefact is embedded in one of 22 carrier templates — a Slack
message, a Jira ticket, a stack trace — never a bare PAN, because a detector tested only
on bare artefacts has been tested on a distribution that does not exist.

### The hard-negative bucket

{{HARD_NEGATIVE_RESULT}}

Thirty-six items designed to trip a naive detector, labelled BENIGN and reported
separately: published vendor test cards, `AKIAIOSFODNN7EXAMPLE`, `your-api-key-here`, git
SHAs, UUIDs, a 10-Q excerpt, and questions *about* credit-card regexes that contain no
card. This bucket is where a regex and a detector separate.

### Inter-rater check

{{INTER_RATER}}

### The aggregation that computes it

```javascript
db.benign_eval.aggregate([
  { $group: { _id: null, n: { $sum: 1 },
      false_pos: { $sum: { $cond: [ { $eq: ["$verdict","BLOCK"] }, 1, 0 ] } },
      p50_latency: { $percentile: { input:"$latency_ms", p:[0.50], method:"approximate" } },
      p95_latency: { $percentile: { input:"$latency_ms", p:[0.95], method:"approximate" } } } },
  { $set: { fpr: { $divide: ["$false_pos","$n"] },
            fpr_pct: { $round: [ { $multiply: [ { $divide: ["$false_pos","$n"] }, 100 ] }, 2 ] } } }
])
```

---

## 3. How it works

```
paste
 ├─ CACHE  sha256(payload) already in `decisions` → replay verdict      (~1 ms)
 ├─ T0     len<40, no digit, none of {@ : / =}    → ALLOW               (~0.01 ms)
 ├─ T1     deterministic scan                                           (~0.3 ms)
 │           HIGH (Luhn+context | PEM | provider-prefix+entropy) → BLOCK, no LLM
 │           LOW | structural | nothing ─────────────┐
 ├─ T2     Qwen3-4B, guided JSON, span-verified ◄────┘             (~200–400 ms)
 └─ T3     image: VLM transcribes chrome → re-run T1+T2 on the text  (~0.9–1.6 s)
```

**A router, not an AND-cascade.** An AND-cascade caps recall at T1's, which is
approximately zero for `FINANCIAL_NONPUBLIC` — no regex matches an unreleased forecast.
T1-HIGH is the only tier permitted to block without a model, and it is therefore
checksum-gated only: its false positives pass straight through to the reported total
rather than being filtered by a later stage.

### Span verification — the mechanism, not a vibe

Every non-BENIGN verdict from T2 or T3 must include an evidence span copied
character-for-character from the payload. If that string cannot be found in the payload —
after a whitespace-normalised second pass — the verdict is **forced to BENIGN** and logged
as `override:"unverified_evidence"`.

Override rate: **{{OVERRIDE_RATE}}**.

This is a deliberate fail-open, and it is the only one on the text path. The reasoning: a
model that cannot point at the characters that made it block did not find anything; it
produced a plausible label. Blocking on that is how DLP products earn their reputation.
The image path has the analogous rule — a non-BENIGN image verdict with no temporal
marker, no confidentiality marker and no T1 hit over the transcribed text is forced to
BENIGN as `override:"no_grounded_marker"`.

### The ablation table

{{ABLATION_TABLE}}

Row 3 minus row 2 is span verification in isolation.

### Why the vision model reads the chrome and not the bars

The T3 prompt transcribes title, axis labels, legend, column headers, footnotes,
watermarks and filenames — and is **explicitly forbidden from reading data values off bars
or lines**. `FINANCIAL_NONPUBLIC` then requires *both* financial vocabulary *and* a
forward-looking or internal marker in the transcribed text.

This routes around every documented VLM chart failure mode. OCRBench v2 scores 54.3 EN:
fine-grained value reading is not reliable. Chrome text is. And chrome is what actually
determines confidentiality in a real deck — "FY26 Revenue Forecast" and "Internal — Do Not
Distribute" are the sensitive part, not the height of the third bar.

---

## 4. Local-first — enforced in four layers, not asserted

**We do not claim no remote LLM was called. We enforce it, and we attach the log.**

1. **OpenShell egress is deny-by-default.** No allow rule names `api.openai.com`,
   `api.anthropic.com`, `generativelanguage.googleapis.com` or `integrate.api.nvidia.com`.
   Those hosts return `403 policy_denied` at the proxy — enforced *outside* the sandbox and
   unmodifiable from within it.
2. **`inference.local` is a whitelist of request shapes, not a hostname allowance.** The
   Privacy Router strips sandbox-supplied credentials, injects the gateway's, rewrites the
   model, and denies non-inference requests.
3. **The inference route is gateway-scoped and set from the host.** The sandbox's own
   `model` and `api_key` are discarded before anything leaves.
4. **Every inference call emits an OCSF v1.8.0 `class_uid: 6003` record naming its
   provider URL.** `evidence/rule02-providers.txt` is the output of
   `jq -r 'select(.class_uid==6003) | .ai_model.ai_provider' | sort | uniq -c` over the
   full run:

   ```
   {{RULE02_PROVIDERS}}
   ```

   One provider. Zero cloud LLM hosts. Zero denied-egress events to any inference endpoint.

We also removed two rules from NVIDIA's own baseline rather than only adding our own — the
platform required a written feature-impact disclosure to do it, and the resulting exclusion
record is versioned, bound to the baseline it was reviewed against, and replayed on every
rebuild, failing closed if that baseline changed (`policy/exclusions.md`).

### The offline demonstration

The ethernet cable comes out, on stage, and the demo keeps working — blocking and
answering. `free -h` and both `/v1/models` responses are on screen with the cable visibly
out.

Stated honestly: the host has a network. Our claim is not that the laptop is airgapped. It
is that (a) the inspection path never uses the network and reports `bytes_egressed: 0` on
every verdict, and (b) the agent runtime is denied egress at the proxy, outside its own
control — and (b) is the machine-checkable one.

---

## 5. The box

### Memory budget

| Process | `--gpu-memory-utilization` | ≈ GB | Contents |
|---|---|---|---|
| vLLM text `:8000` — Qwen3.6-35B-A3B-NVFP4 | 0.40 | 51.6 | weights ~22 + FP8 KV ~26 + graphs ~3 |
| vLLM vision `:8001` — Holo1.5-7B BF16 | 0.24 | 31.0 | weights ~16.5 + KV ~9 + MM caches ~2 + graphs ~3 |
| **Sum reserved by CUDA** | **0.64** | **~82.6** | hard ceiling **0.85** |
| MongoDB (`--memory=6g --cpus=4`) | — | 6.0 | mongot JVM ≈ 25% of the cgroup ≈ 1.5 GB heap |
| bge-small + reranker (CPU, ONNX Runtime) | — | 1.7 | 20 Arm cores, **no GPU process** |
| OS + desktop + docker + page cache | — | ~14 | |
| **Total** | | **~104** | vs a **126.5 GB** host-crash ceiling |

Headroom: **{{HEADROOM}}**.

**NVIDIA's own flagship recipe for this exact text model runs at 0.40. We run two models
at 0.64 with room left.** That is the unified-memory argument in one line: on a 24 GB
discrete GPU neither model fits beside the other, and you would swap over PCIe between
every paste. Here there is no PCIe to swap across.

### `nvidia-smi` shows no memory bar, and that is correct

GB10 is an integrated GPU with no framebuffer. NVIDIA documents `Memory-Usage: Not
Supported`. Memory state is read from `nvidia-smi --query-compute-apps` plus `/proc/meminfo`
`MemAvailable` and `SwapFree`. **No VRAM bar appears anywhere in this document**, because
there is no VRAM to bar-chart. `results/proof_*.log` is the artifact.

### The hidden multimodal-cache finding

vLLM's multimodal caches default to 4 GiB and 8 GiB and are **duplicated per API process
and per engine-core process**. They live in what the docs call "CPU RAM" — which on a
unified-memory box is *the same physical pool the model weights are in*. Left at defaults
across two servers this silently consumes 15–20 GB that appears in no GPU memory
accounting.

The fix is two flags: `-e VLLM_MM_INPUT_CACHE_GIB=2` and `--mm-processor-cache-gb 1`.

**We have not found this written down anywhere in the DGX Spark literature.** It is the
single most useful operational finding in this project for anyone else running two models
on one of these boxes.

### Throughput

{{THROUGHPUT_TABLE}}

**Vision is prefill-bound and scales 1.5–2.5× from c=1 to c=8, then flattens.** We state
that before showing the data. The vision sweep was run twice — once idle, once with the
35B under c=8 load — and **both columns are published**, because decode is bandwidth-bound
and every process shares 273 GB/s. A benchmark that shows its own degradation is more
credible than one that does not.

**First measured VLM image-inspection throughput on NVIDIA GB10:** {{IMAGES_PER_SEC}}. No
first-party number for this exists. The naive literature baseline we designed around is
413 s/image.

---

## 6. Why MongoDB is load-bearing and not decorative

Time-series collections support neither change streams nor Search nor CSFLE. No single
collection can be searchable, watchable, and time-series. So the data model is a
deliberate three-way split by access pattern, plus an isolated harness collection:

| Collection | Type | Why it must be this type |
|---|---|---|
| `policy_corpus` | regular | needs `$search` + `$vectorSearch` |
| `decisions` | regular | needs **change streams** for the live console |
| `inspect_metrics` | **time-series** | append-only telemetry; columnar buckets, `$setWindowFields`, TTL |
| `benign_eval` | regular | a 1000-doc harness burst would roll the single-node oplog and kill the console's resume token |

- **Vector Search** (384-d cosine, bge-small) — semantic memory: exemplars of what
  "sensitive" looks like. This *is* the detector for classes no regex reaches.
- **`$search`** — recovers exact tokens (`FY26`, `Do Not Distribute`) that embeddings blur.
- **`$rankFusion` + `scoreDetails`** — one server-side call fuses both signals *and*
  returns the per-signal audit trail. We render it verbatim in the block card: rank,
  weight, per-pipeline contribution, and the server's own plain-English description of the
  RRF formula. **That is an auditable explanation rather than a black-box BLOCK.**
- **Change streams** — the console is push, not poll.
- **Time-series + `$setWindowFields` + TTL** — bucketed columnar telemetry with
  rate-over-time windows and automatic expiry.
- **Hash index on `decisions.payload_sha256`** — the semantic-cache pattern applied to
  security: the second identical paste blocks in ~1 ms with no model call.
- **Write-back to `policy_corpus`** — procedural memory. An analyst marks a false positive
  benign, its embedding is written back, the next paste of that shape passes, and a near
  neighbour still blocks. **The detector learns without retraining a model.** Live,
  visible, and impossible with a regex.

The top-3 retrieved `clause_id`s become the constrained enum for the classifier's guided
JSON output, **so the cited policy clause cannot be hallucinated.**

Retrieval for the FP harness uses `exact: true` ENN unconditionally. The corpus is a few
thousand documents, ENN needs no `numCandidates`, and the number must be reproducible when
a judge asks us to re-run it — ANN recall jitter would make the same benign paste block on
one run and pass on the next.

---

## 7. Usefulness

### Seats per box

{{SEATS_ARITHMETIC}}

`seats = min(seats_vision, seats_text)`, and we name which binds. Assumptions on the page:
P = 40 pastes per employee per 8-hour day, peak factor 4×, measured image fraction
`f_img = {{F_IMG}}`, measured escalation rate {{ESCALATION}}.

### Cost

160 W at the wall is roughly €350/year of electricity for the whole box. Divided by
{{SEATS}} seats, against per-seat cloud DLP licensing plus per-token cloud LLM API spend.

**We earn the 87% figure rather than quoting it:** you stop paying per token, and you stop
paying the interruption tax.

### The interruption tax

5,000 employees × 40 pastes/week = 200,000 pastes. At the published 51% industry
false-positive average that is **102,000 wrong interruptions a week**. At our measured
rate it is **{{INTERRUPTIONS}}**.

### Three operating points

| Mode | τ | Recall | FPR |
|---|---|---|---|
| Audit | 0.30 | {{RECALL_AUDIT}} | {{FPR_AUDIT}} (log only, never blocks) |
| **Balanced** (default) | **0.55** | {{RECALL_BALANCED}} | **{{FPR_BALANCED}}** |
| Strict | 0.20 | {{RECALL_STRICT}} | {{FPR_STRICT}} |

The threshold slider in the console re-thresholds **cached** per-item `p_block` scores, so
the sweep is exact and instant. We label it as cached; it is not 1,000 fresh inferences.

---

## 8. Things we tested and rejected

| Thing | Why not |
|---|---|
| **CUDA MPS** | +10% aggregate throughput, but mean TTFT 16,726 ms → 27,142 ms (**+62%**), measured on this box. Airlock is a keystroke-path product; TTFT is the only latency that matters. |
| **vLLM sleep mode** | Level 1 "offloads weights to CPU RAM". On GB10 that is the same DRAM. You free nothing physical; you move a pointer. |
| **Speculative decoding on the VLM** | MTP amortises over long generations. We emit ≤8 output tokens. Kept on the 35B, where it is worth ~2.7×. |
| **A third GPU process for embeddings** | bge-small is 67 MB. A CUDA context costs 300–500 MB plus its own compile warm-up plus SM time. Runs on the 20 Arm cores via ONNX Runtime instead. |
| **GridFS for evidence crops** | Two collections, a second round trip, and loss of atomicity — the crop and its verdict could not be written in one operation. Crops are far under the 16 MB BSON limit, so `BinData` in the decision document. |
| **Queryable Encryption** | Enterprise/Atlas only. We ship AES-GCM with a key in a 0600 file that never leaves the box, and say so rather than implying otherwise. |
| **gRPC for the middleware path** | OpenShell's inference router speaks HTTP. Protobuf costs an hour and buys nothing. |

---

## 9. Honest boundaries

- **MongoDB Community runs without auth on loopback** in this deployment.
- **Queryable Encryption is the production path and is unavailable in Community.** Evidence
  crops are AES-GCM encrypted with a local key file; full-resolution originals are *never*
  persisted — storing the data you just blocked from leaving is indefensible for a DLP
  product.
- **The MAIN-world `fetch` patch is the unmanaged-browser approximation** of a
  policy-force-installed extension with blocking `webRequest`. In a managed fleet you would
  use the real thing.
- **The clipboard interceptor necessarily runs on the host.** A sandbox cannot and should
  not observe a paste event — that would require display-server access. Our host-side claim
  is architectural (loopback-only binding, no cloud SDK linked) and demonstrated the only
  honest way: with the ethernet cable on the table.
- **`@openclaw/policy` verifies config-level conformance only.** It does not enforce tool
  calls at request time. Runtime enforcement is OpenShell's proxy. We say this ourselves
  rather than letting it be discovered.
- **Our sensitive corpus is synthetic**, so recall is an upper bound. The benign corpus is
  human-written, which is why FPR is the number we stand behind.
- **Out of scope, stated plainly:** fleet deployment, endpoint management,
  screen-photography threat vectors, and anything requiring synthetic input injection.

---

## 10. Stack

{{STACK_PARAGRAPH}}

---

## Attachments

| File | Proves |
|---|---|
| `data/benign_v1.jsonl` + manifest + `ATTRIBUTION.md` | the denominator, with per-record provenance |
| `data/sensitive_v1.jsonl` + manifest | the recall side and the hard-negative bucket |
| `bench/build_benign.py`, `bench/run_fpr.py`, `bench/report.py` | the harness, reproducible from one seeded command |
| `results/fpr_report.json` | every number in this document, machine-readable |
| `results/false_positives.md` | every false positive, itemised and adjudicated |
| `results/roc.png`, `pr.png`, `reliability.png` | log-scale ROC, PR with AP, calibration before/after |
| `results/proof_*.log` | two models resident in one pool, no VRAM bar |
| `evidence/rule02-providers.txt` | **Rule 02 as a machine-checkable fact** |
| `evidence/policy-denied.json` | the raw egress denial the browser layer mirrors byte-for-byte |
| `evidence/airlock-policy.json` | applied presets with their `verification` field |
| `services/inspect/policy.yaml` | the nine clauses |
| `stack/openshell-policy.toml`, `policy/*` | the reviewable policy artifacts |
| `tests/test_t1.py` | the deterministic detectors, with passing output |
