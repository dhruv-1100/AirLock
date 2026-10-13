<!--
  submission/SUBMISSION.md — owner C. SRS §14.

  Every double-brace placeholder is filled from results/fpr_report.json and the corpus
  manifest by:   python submission/fill.py   ->   submission/SUBMISSION.final.md

  Numbers written out literally below are each followed by the artifact they come from,
  and submission/check_claims.py verifies every one of them against that file.

  Rewritten 2026-10-13 after the GB10 became unavailable. The previous draft described
  the PLANNED system (Qwen 35B, Holo 7B, a 4B classifier, a throughput sweep, a
  calibration fit, an ablation table). Several of those never ran. This version claims
  only what was measured, and says plainly what was not.
-->

# Airlock — the bouncer that sits on the paste

**Airlock intercepts the clipboard payload the moment company data is about to leave a
laptop for an unapproved cloud AI tool, inspects it locally on a Dell Pro Max with GB10,
blocks it with a cited policy clause, and re-routes the question to a 30B model on the
same box so the employee still gets an answer.**

We measured a **{{FPR_HEADLINE}}** false-positive rate over **{{N}} benign pastes we did
not write**, drawn from {{N_SOURCES}} independently-licensed public sources of real
human-written text — with the corpus, the harness and every per-item score published, so
the number can be reproduced from one seeded command.

That number is the submission. Everything else is how we got it, what it does and does not
license — including why it does **not** support a simple "N times better than industry"
claim — and, because the hardware is no longer available to us, exactly which planned
measurements were never taken.

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
industry ships pattern matchers, which produce the false-positive rates that make employees
route around the control.

**A 128 GB unified-memory box changes the arithmetic.** The inspection model can live on
the endpoint. That is the thesis, and it is testable: if local inspection cannot get the
false-positive rate down, the idea fails. So we measured it.

---

## 2. The deciding artifact — false-positive rate with a denominator

### Headline

| | |
|---|---|
| **False-positive rate** | **{{FPR_STATEMENT}}** |
| Denominator | {{N}} benign pastes, {{N_SOURCES}} sources, none written by us |
| Threshold | {{THRESHOLD}} — the design default, fixed before the run. **Not tuned on this corpus**; there was no dev/test split. |
| Recall (synthetic sensitive set) | {{RECALL_STATEMENT}} |
| Hard negatives wrongly blocked | {{HARD_NEGATIVE_RESULT}} |
| Latency p50 / p95 | {{P50}} ms / {{P95}} ms — **under the harness's concurrency of 8**, so it includes queueing. It is not the latency of a single interactive paste. |
| Reached a language model | {{ESCALATION}} of pastes — see "which tier resolved each paste" below |

Reproduce, verbatim:

```bash
python bench/build_benign.py --seed 1337
python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55
python bench/report.py
```

### What the number does and does not mean

**A false-positive rate is not the same thing as the share of alerts that are wrong.**
Our 4.00% is the share of *benign pastes* that get blocked. The figure usually quoted for
DLP — a vendor survey of 300 security leaders reporting that **51% of DLP alerts are false
positives** ([Cyberhaven](https://www.cyberhaven.com/blog/dlp-false-positives)) — is the
share of *blocks* that are wrong. Dividing one by the other would be meaningless, and an
earlier draft of this document did exactly that. We withdraw that comparison.

The like-for-like number is our share of wrong blocks, and it depends on how often a paste
is genuinely sensitive — which we do not know for real traffic:

| If this share of pastes is sensitive | share of our blocks that are wrong |
|---|---|
| 1% | 80.1% |
| 2% | 66.6% |
| 5% | 43.6% |
| 10% | 26.8% |

**We match the survey's 51% at a prevalence of about 3.8%** — better above that, worse below.
So on the evidence we have, Airlock's alerts are in the same range as the industry's, not
clearly better. (And the survey describes real deployments while our figures are computed
from a benchmark, so even that comparison is only indicative.)

What we can claim is narrower and still worth something: a false-positive rate published
**with its denominator, its corpus, and its per-item scores**, so it can be checked —
which a single survey percentage cannot be. Our design target was under 1%; **we did not
reach it**, and at 4% Airlock is not good enough to block silently. That is why the block
card always offers to answer the question on the local model instead of simply refusing,
and why an Audit mode exists.

### Hand-adjudication of every false positive

All 40 blocks were reviewed individually. Full table with a reason per item:
`results/adjudication.md`.

| | n |
|---|---|
| Correct blocks — the "benign" corpus contained a live-format credential (a Shopify `shpat_` token, an X/Twitter bearer token) | 2 |
| Fail-closed timeouts — the inspector failed closed; not a classifier decision | 2 |
| Borderline — fictional named-patient narratives that match POL-005's surface form | 3 |
| **Genuine classifier errors** | **33** |

**After removing the two correct blocks: 38/1000 = 3.80% [2.78%, 5.17%].** Genuine
classifier errors alone: 33/1000. We keep 4.00% as the headline because it is what a user
experiences, timeouts included.

**This review was done by one reviewer and has not been confirmed by a second.** We make
no inter-rater agreement claim.

**What the errors are, and what we got wrong about them.** 12 of the 33 genuine errors fired
on CFPB's `XXXX` redaction masks — CFPB publishes complaint narratives with personal details
already replaced by `XXXX`, and the classifier read runs of `XXXX` as card numbers or social
security numbers, despite its prompt listing `XXXX` as placeholder data. A further 13 are
ordinary consumer credit-dispute letters labelled LEGAL_HR. **We had previously argued that
CFPB blocks were defensible because the narratives "contain identifiers". They do not —
CFPB redacts them. That argument was wrong.**

### Per-source false-positive contribution

{{BY_SOURCE_TABLE}}

**Zero false positives across the 480 Stack Exchange, Wikipedia, MBPP and HumanEval items**
— the code and technical prose engineers paste most. CFPB is our worst source by a wide
margin, for the redaction-mask reason above.

### Corpus provenance

{{CORPUS_TABLE}}

The corpus is regenerable from one seeded command. Per-record provenance
(`id, source, licence, sha256, char_len, provenance_url`) is in
`data/benign_v1.manifest.json` and `data/ATTRIBUTION.md`. All 1000 SHA-256 values verify
against the text.

### Which tier resolved each paste

{{TIER_MIX_TABLE}}

**Stated before anyone finds it.** The benign corpus has a 200-character floor; the T0 fast
path fires only below 40 characters. **T0 cannot fire on this corpus by construction**, so
essentially every item reached the language model.

That cuts two ways:

- **It makes the false-positive rate conservative.** Nothing was waved through by a length
  check before the model saw it.
- **It makes any throughput claim from this corpus unrepresentative.** Escalation rate,
  blended latency and seats-per-box all scale with the share of pastes that reach a model.
  We do not report a blended escalation rate.

To show the fast path works rather than claiming one we never exercised, a separate set of
40 short pastes written to satisfy the T0 gate was run against the live service: **40 of 40
resolved at T0, p50 4.8 ms, p95 6.7 ms, HTTP round trip included** (`results/t0_fastpath.md`).
That set is authored by us and is never merged into the denominator — it shows the path
works, not how often real traffic takes it.

### Recall by class

{{BY_CLASS_TABLE}}

**Our sensitive set is synthetic, so recall is an upper bound. Our benign set is
human-written, which is why the false-positive rate is the number we stand behind.** Every
synthetic artefact is embedded in one of 22 carrier templates — a Slack message, a Jira
ticket, a stack trace — never presented bare.

The sensitive corpus also carries **50 hard negatives**, labelled BENIGN: published Stripe
test cards (one probe per card), `AKIAIOSFODNN7EXAMPLE`, `your-api-key-here`, git SHAs,
UUIDs, a 10-Q excerpt, and questions *about* credit-card formats that contain no card. They
are reported on their own line in the headline table, never mixed into recall.

> **Correction.** An earlier version of our tooling put those 50 hard negatives in the
> recall denominator and reported recall as 87.78% (395/450). The correct figure is above.
> Recomputed from the run's own per-class counts; covered by a regression test.

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
 ├─ CACHE  sha256(payload) already seen → replay the verdict
 ├─ T0     len<40, no digit, none of @ : / =  → ALLOW         measured p50 4.8 ms
 ├─ T1     regex + Luhn + entropy, deterministic
 │           HIGH → BLOCK with no model call
 │           anything else ──────────────────┐
 ├─ T2     Nemotron-3.5-Lightning-30B, guided JSON, span-verified ◄┘
 └─ T3     image: Nemotron-3-Nano-Omni-30B transcribes the chart's text → T1 + T2
```

**A router, not an AND-cascade.** An AND-cascade caps recall at T1's, which is near zero
for unreleased financials — no regex matches a forecast. T1-HIGH is the only tier allowed
to block without a model.

**T1 alone, measured offline:** zero T1-HIGH blocks across the 1000 benign pastes (below
0.30% by the rule of three; `results/t1_offline.json`), and 105 of the 400 sensitive
items blocked with no model call at all — with none of the 50 hard negatives
(`results/t1_offline_sensitive.json`).

### Span verification — the mechanism

Every non-BENIGN verdict from T2 or T3 must quote characters that appear verbatim in the
payload. If the quoted string is not there — after a whitespace-normalised second pass — the
verdict is forced to BENIGN and logged as `override: "unverified_evidence"`.

Measured on the benign run: **{{OVERRIDE_RATE}}.**

This is a deliberate fail-open. A model that cannot point at the characters that made it
block did not find anything; it produced a plausible label. The image path has the same
rule.

### The image path — what actually happened

The vision tier reads a chart's *text* — title, axis labels, legend, footnotes, watermarks —
and is told never to read values off the bars, which is where vision models are least
reliable. It ran end to end against the live model (`results/t3_latency.md`):

| image | verdict | latency |
|---|---|---|
| `fy26_forecast.png`, first call | allow BENIGN | 12,995 ms |
| same image, second call | allow BENIGN, from cache | 1 ms |
| `gate_00.png` | 504, timed out | 19,909 ms |
| `gate_01.png` | **block FINANCIAL_NONPUBLIC**, 1 evidence span | 10,013 ms |

Two honest findings:

- **The demo chart did not block.** The model transcribed "FY26 Revenue Forecast" correctly
  and described its reasoning in prose — but put no quoted text in `evidence_spans`, so span
  verification forced BENIGN. That is the mechanism working as designed: it refused to block
  on something the model would not point at. It also means the image beat was cut from our
  recorded demo rather than faked.
- **10 to 20 seconds per image.** The latency budget was sized for a 7B vision model; the
  model on the box was a 30B. The browser gives up at 2.5 s and fails closed, so a pasted
  image in the browser always shows the "inspector unavailable" card, never a verdict. With
  this model the image path is not interactive.

### Not measured — the ablation

The plan was a four-row ablation: T1 only; T2 without span verification; T2 with it; the
full router. **Only row 1 exists** (above). Rows 2–4 needed live model runs and were not
taken before hardware access ended.

---

## 4. Local-first — enforced at the sandbox, demonstrated at the host

**For the agent sandbox, we do not assert that no remote model was called — we show it from
the platform's own log.** `evidence/rule02-providers.txt`, captured from the OpenShell log
for sandbox `airlock`:

- **Every inference request went to one endpoint:** 4 requests, all to
  `http://172.17.0.1:8000/v1` — the vLLM serving Nemotron-3.5-Lightning-30B from local
  weights. Zero cloud providers.
- **The only host the sandbox opened was `inference.local`** — the gateway's router, which
  forwards to that local endpoint.
- **The four cloud model APIs are denied at the proxy:** `api.openai.com`,
  `api.anthropic.com`, `generativelanguage.googleapis.com`, `integrate.api.nvidia.com` each
  returned `403 {"error":"policy_denied"}` (`evidence/policy-denied.json`). Nothing in the
  policy allows them, and the policy lives outside the sandbox where code inside cannot
  change it.
- **The sandbox cannot repoint inference.** A request from inside asking for model
  `ignored-by-router` came back as `airlock-text` — the router discards the sandbox's
  choice of model.

**The honest limit, stated in the evidence file itself:** all of that governs the sandbox.
The host-side classifier calls its model over loopback and sits outside OpenShell's
enforcement entirely. For the host, the claim is architectural — the inspect service binds
127.0.0.1 only, links no cloud SDK, and every verdict reports `bytes_egressed: 0`. We planned
to demonstrate it by unplugging the ethernet cable mid-demo; **that demonstration was not
captured**.

---

## 5. The box

### Memory, as measured

Read from `nvidia-smi --query-compute-apps` and `/proc/meminfo` with both models resident
and warm (`results/proof_*.log`):

| Process | `--gpu-memory-utilization` | Resident |
|---|---|---|
| vLLM text `:8000` — Nemotron-3.5-Lightning-30B-A3B, NVFP4 | 0.40 | 47,847 MiB |
| vLLM vision `:8001` — Nemotron-3-Nano-Omni-30B-A3B, BF16 | 0.28 | 35,325 MiB |
| MongoDB container (6 GB cgroup) | — | 910 MiB |
| **MemAvailable with everything loaded** | | **25.06 GB** of 121.63 GB |

Two 30B models, a database and the operating system, resident at once in one memory pool,
with 25 GB still free. (Process-to-model mapping is by utilisation fraction.) On a 24 GB
discrete GPU neither model would fit beside the other.

### `nvidia-smi` shows no memory bar, and that is correct

GB10 is an integrated GPU with no separate framebuffer, and `nvidia-smi` reports total memory
as `[N/A]` by design — the proof log shows exactly that. Memory state comes from the
per-process figures and `/proc/meminfo` above. **No VRAM bar appears in this document.**

### Not measured — throughput and seats per box

The plan included concurrency sweeps for text and vision, an images-per-second figure, and a
seats-per-box estimate built from them. **None was run.** We do not report throughput, and
we do not report seats per box or cost per seat, because both are derived from the sweep.

Multimodal cache sizes were capped at launch on the advice of our design document, which
estimated the defaults could hold 15–20 GB of memory invisible to GPU accounting. We did not
measure what the defaults would have consumed, so we present that as configuration, not as a
finding.

---

## 6. Why MongoDB is load-bearing and not decorative

Time-series collections support neither change streams nor Search nor client-side
encryption. No single collection can be searchable, watchable and time-series. So the data
model is a deliberate three-way split by access pattern, plus an isolated harness
collection:

| Collection | Type | Why it must be this type |
|---|---|---|
| `policy_corpus` | regular | needs `$search` + `$vectorSearch` |
| `decisions` | regular | needs **change streams** for the live console |
| `inspect_metrics` | **time-series** | append-only telemetry; columnar buckets, `$setWindowFields`, TTL |
| `benign_eval` | regular | a 1000-doc harness burst would roll the single-node oplog and kill the console's resume token |

- **Vector Search** (384-d cosine, bge-small on CPU) — semantic memory: exemplars of what
  "sensitive" looks like.
- **`$search`** — recovers exact tokens (`FY26`, `Do Not Distribute`) that embeddings blur.
- **`$rankFusion` + `scoreDetails`** — one server-side call fuses both signals and returns
  the per-signal audit trail, rendered in the block card: rank, weight, contribution.
- **Change streams** — the console is push, not poll, and survives the collection being
  dropped and re-seeded.
- **Hash index on `decisions.payload_sha256`** — a second identical paste replays its
  verdict without a model call (seen in the image table above: 1 ms).
- **Write-back to `policy_corpus`** — an analyst marks a false positive benign; its
  embedding goes back into the corpus, so the next paste of that shape passes while a near
  neighbour still blocks. The detector learns without retraining a model.

The top-3 retrieved clause IDs become the allowed values for the classifier's cited clause,
**so the cited policy clause cannot be invented.**

---

## 7. Usefulness

### The interruption tax

5,000 employees × 40 pastes a week = 200,000 pastes, nearly all of them benign. At our
measured rate that is **{{INTERRUPTIONS}}** — about one paste in twenty-five. We do not set
that against an industry figure: the commonly quoted 51% measures something else (see §2).

### Three operating points — and why they barely differ

| Mode | τ | Recall | FPR |
|---|---|---|---|
| Audit | 0.30 | {{RECALL_AUDIT}} | {{FPR_AUDIT}} — log only, never blocks |
| **Balanced** (default) | **0.55** | {{RECALL_BALANCED}} | **{{FPR_BALANCED}}** |
| Strict | 0.20 | {{RECALL_STRICT}} | {{FPR_STRICT}} |

**These three rows are nearly identical, and we know why.** 98.1% of the run's scores sit
below 0.05 or above 0.95, so moving the threshold moves almost nothing. The cause was a bug
in how the score was computed: when the model was confident, every label except one was
dropped before normalising, so 812 of 1000 benign scores came out exactly 0.0 and no
temperature setting could spread them. **It is fixed in the code and covered by tests, but
the fix was never re-run against the live model**, and no calibration temperature was ever
fitted. The threshold slider in the console is honest about the scores it has; those scores
just leave it little to do.

---

## 8. Design decisions

| Choice | Reason |
|---|---|
| **No third GPU process for embeddings** | bge-small is 67 MB. A GPU context costs far more than that plus its own warm-up. It runs on the CPU. |
| **Prefix caching on, speculative decoding (MTP) off** for the text model | On this vLLM build the two are mutually exclusive, and the classifier sends the same long system prompt every call. We kept the cache (`stack/launch_text.sh`). |
| **Reasoning disabled for classification** (`enable_thinking=False`) | With it on, the model spent its whole 200-token budget thinking and never produced the JSON verdict. Off: 8 tokens, clean JSON, 236 ms (`services/inspect/tiers/t3.py`). |
| **Evidence stored as `BinData`, not GridFS** | Crops are far under the 16 MB document limit; GridFS costs two collections, a second round trip, and atomicity. |
| **AES-GCM with a local key, not Queryable Encryption** | Queryable Encryption is Enterprise/Atlas only. We say so rather than implying otherwise. |

---

## 9. Honest boundaries

- **Hardware access ended before several planned measurements were taken:** the ablation,
  the throughput sweep, seats per box, temperature calibration, and a re-run after the
  score-computation fix. Each is marked "not measured" where it would have appeared.
- **The image path is not interactive** with the 30B vision model on the box, and the demo
  chart did not block. Both are reported above.
- **The false-positive rate missed our under-1% design target.** It is 4.00%.
- **Our sensitive corpus is synthetic**, so recall is an upper bound.
- **Adjudication had one reviewer.** No inter-rater claim is made.
- **MongoDB Community runs without authentication on loopback** in this deployment.
- **The browser extension's origin allowlist** accepts any extension ID until
  `AIRLOCK_EXTENSION_ID` is set, because an unpacked extension's ID differs per machine.
- **Out of scope:** fleet deployment, endpoint management, screenshots and photographs of
  the screen.

---

## 10. Stack

Airlock runs on a Dell Pro Max with GB10 (driver 580.159.03). Inference is served by vLLM
from local weights: **Nemotron-3.5-Lightning-30B-A3B (NVFP4)** for text classification and
for answering the employee's question, and **Nemotron-3-Nano-Omni-30B-A3B (BF16)** for
images. The agent sandbox runs under **NemoClaw with OpenShell 0.0.44**, whose
deny-by-default egress policy and inference router produce the evidence in §4. We planned to
run an OpenClaw agent inside that sandbox for the local answer; **in the build as captured,
the local answer is served by the host gateway's `/v1/answer`**, and we make no OpenClaw
claim. MongoDB (Atlas Local) holds the policy corpus, the decision log and telemetry.

---

## Attachments

| File | What it shows |
|---|---|
| `data/benign_v1.jsonl` + manifest + `ATTRIBUTION.md` | the denominator, with per-record provenance |
| `data/sensitive_v1.jsonl` + manifest | the recall side and the 50 hard negatives |
| `bench/build_benign.py`, `bench/run_fpr.py`, `bench/report.py` | the harness, reproducible from one seeded command |
| `results/fpr_report.json` | every computed number in this document |
| `results/adjudication.md` | all 40 false positives, each categorised with a reason |
| `results/t1_offline.json`, `results/t0_fastpath.md`, `results/t3_latency.md` | T1 offline, the T0 probe, the image-path run |
| `results/proof_*.log` | both models resident in one pool, read without a VRAM bar |
| `evidence/rule02-providers.txt`, `evidence/policy-denied.json` | the sandbox's inference and egress record |
| `services/inspect/policy.yaml` | the nine policy clauses |
| `tests/` | 88 tests, including regressions for every bug fixed after the run |

`results/roc.png`, `pr.png` and `reliability.png` are **not** offered as evidence: they were
drawn by the earlier tooling that counted the 50 hard negatives as positives, and the
per-item data needed to redraw them was not kept.
