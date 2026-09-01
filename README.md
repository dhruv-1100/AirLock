# Airlock

**Airlock intercepts the clipboard payload the moment company data is about to leave a
laptop for an unapproved cloud AI tool, inspects it locally on a Dell Pro Max with GB10,
blocks it with a cited policy clause, and re-routes the question to a 35B model on the box
so the employee still gets an answer.**

Nothing leaves the machine. Every verdict reports `bytes_egressed: 0`, and the agent
runtime is denied egress at the proxy — enforced outside the sandbox, unmodifiable from
within it.

---

## Measured results

From `results/fpr_report.json`. Every number here is regenerable with one seeded command;
none is typed in by hand.

| | |
|---|---|
| **False-positive rate** | **4.00%  [2.95%, 5.40%]  (40/1000)** |
| Denominator | 1000 benign pastes we did not write, six independently-licensed sources |
| Recall | 87.78%  [84.43%, 90.49%]  (395/450) — synthetic set, so an **upper bound** |
| Threshold | 0.55 (Balanced), selected on dev, reported on test |
| Published industry average | 51% → **12.8× better** |
| Interruption tax | 8,000/week at 5,000 employees × 40 pastes, vs 102,000 at the industry average |

**Zero false positives across 480 items** of Stack Exchange, Wikipedia, MBPP and HumanEval
— the code and technical prose an engineer actually pastes.

| Source | n | FP | rate |
|---|---|---|---|
| CFPB | 120 | 29 | 24.2% |
| WildChat-1M | 400 | 11 | 2.8% |
| StackExchange | 200 | 0 | 0.0% |
| Wikipedia | 100 | 0 | 0.0% |
| MBPP | 100 | 0 | 0.0% |
| HumanEval | 80 | 0 | 0.0% |

Reproduce:

```bash
python bench/build_benign.py --seed 1337
python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55
python bench/report.py
```

---

## How it works

```
paste
 ├─ CACHE  sha256(payload) already seen → replay verdict            (~1 ms)
 ├─ T0     len<40, no digit, none of {@ : / =}      → ALLOW         (~0.01 ms)
 ├─ T1     regex + Luhn + entropy, deterministic                    (~0.3 ms)
 │           HIGH → BLOCK with no model call
 │           anything else ─────────────────────────┐
 ├─ T2     text LLM, guided JSON, span-verified ◄───┘          (~200–1700 ms)
 └─ T3     image: VLM transcribes chrome → re-run T1+T2 on the text
```

**A router, not an AND-cascade.** An AND-cascade would cap recall at T1's, which is
approximately zero for unreleased financials — no regex matches a forecast.

**Span verification is the load-bearing guard.** Every non-BENIGN verdict must quote
characters that appear verbatim in the payload. If the model cannot point at anything
real, the verdict is forced to BENIGN and logged. That is a deliberate fail-open, and it
is one of exactly two in the system.

---

## Quick start

```bash
pip install -r services/inspect/requirements.txt
```

```bash
bash stack/up_mongo.sh
```

```bash
bash stack/seed.sh
```

Models are launched by whoever owns the box — **two servers, never three**
(`0.40 + 0.28 = 0.68` against a 0.85 ceiling; exceeding it freezes the host rather than
raising OOM). Then:

```bash
set -a; . stack/models.env; set +a && uvicorn services.inspect.app:app --host 127.0.0.1 --port 8787
```

Sourcing `models.env` is not optional — `t2.py` otherwise points at a classifier port the
two-server config does not launch, and every escalated paste fail-closes to BLOCK.

**See the UI with no extension and no models:**

```bash
python3 -m http.server 5175 --bind 127.0.0.1
```

Then open `http://localhost:5175/tools/harness/` — states at `#block`, `#evidence`,
`#console`, `#slider`.

---

## Repository map

| Path | What |
|---|---|
| `services/inspect/` | the gateway: tiers T0–T3, span verification, Mongo, change stream, console API |
| `stack/` | Mongo bring-up, seed, model launches, preflight, `proof.sh` |
| `bench/` | corpus builders, FPR harness, report, T1 offline pass, image assets |
| `extension/`, `web/` | MV3 extension, block overlay, live console, replica composer |
| `policy/`, `skills/` | OpenShell egress preset, OpenClaw attestation, the verdict-explainer skill |
| `submission/` | `SUBMISSION.md`, `PITCH.md`, `fill.py` (substitutes every number from the JSON) |
| `data/`, `results/`, `evidence/` | corpora + manifests, measured output, stack artifacts |

Key documents: **`RUN-DAY.md`** (end-to-end run with PASS criteria), **`CONTRACT.md`**
(frozen API), **`INTEGRATION.md`** and **`INTEGRATION-B.md`** (cross-branch findings).

---

## Why MongoDB is load-bearing

Time-series collections support neither change streams nor Search nor CSFLE, so no single
collection can be searchable, watchable and time-series. The data model is a deliberate
three-way split by access pattern:

- **`policy_corpus`** — `$vectorSearch` (384-d cosine, bge-small on CPU) + `$search`,
  fused server-side by **`$rankFusion`**. The `scoreDetails` tree is rendered verbatim in
  the block card: rank, weight, per-pipeline contribution. An auditable explanation, not a
  black-box BLOCK. The top-3 retrieved clause IDs become the constrained enum for the
  classifier, **so the cited clause cannot be hallucinated.**
- **`decisions`** — regular, because the live console needs **change streams**. Also the
  hash-keyed instant-block cache: the second identical paste blocks in ~1 ms, no model.
- **`inspect_metrics`** — time-series, `$setWindowFields`, TTL.
- **`benign_eval`** — isolated, so a 1000-doc harness burst cannot roll the oplog under
  the console's resume token.
- **Write-back to `policy_corpus`** — an analyst marks a false positive benign, its
  embedding goes back into the corpus, the next paste of that shape passes while a near
  neighbour still blocks. **The detector learns without retraining a model.**

---

## Status

**Working and measured:** the detector end to end, the corpus and harness, the Mongo
layer, the console and WebSocket feed, the block overlay, the stack egress artifacts, a
recorded demo.

**Known limitations — stated here rather than discovered:**

- **`p_block` is saturated.** 98.1% of items sit below 0.05 or above 0.95. The threshold
  slider therefore barely moves (FPR 4.70% → 4.00% across τ 0.20 → 0.55) and **recall is
  identical at all three operating points**. The verdict-based and score-based FPRs now
  agree, so the headline is sound, but the operating-point story is weak and the
  calibration curve is fitted to two spikes.
- **Escalation is 99.8%, not the ~14% the design assumed.** The benign corpus has a
  200-character floor and T0 only fires below 40, so T0 cannot fire on it by construction.
  This makes the **FPR conservative** — every item reached the model, nothing was resolved
  by a cheap length check — but it makes escalation rate, blended latency and
  seats-per-box measured here unrepresentative of a real paste distribution. A separate
  T0 probe set (`data/shortpaste_v1.jsonl`) demonstrates the fast path works.
- **CFPB contributes 29 of 40 false positives** while being 12% of the corpus. Its
  narratives are consumers' personal financial grievances containing identifiers, which
  our own POL-004/POL-005 cover — so CFPB was a poor choice of *benign* source. We report
  the measured rate and give the ex-CFPB figure only as a labelled sensitivity analysis,
  never as the headline.
- **The sensitive corpus is synthetic**, so recall is an upper bound. The benign corpus is
  human-written, which is why **FPR is the number we stand behind**.
- **Language is not a driver.** We pre-registered the hypothesis that the multilingual
  corpus would skew the FP list and checked it: latin 7.0%, cjk 8.6%, cyrillic 0/20 —
  overlapping intervals, no effect. Reported as a negative result.
- MongoDB Community runs without auth on loopback; Queryable Encryption is the production
  path and is Enterprise/Atlas only, so evidence is AES-GCM encrypted with a key in a 0600
  file that never leaves the box.

**Outstanding:** the four-row ablation table, and generating `SUBMISSION.final.md` from
the current numbers.

---

## The one operational rule

**Only one person starts, stops or restarts a GPU process.** On this box unbounded
allocation freezes the whole host — no SSH, no ping — rather than raising OOM. Summed
`--gpu-memory-utilization` must never exceed **0.85**; the committed demo value is
**0.68**. Update the running total *before* a launch, never after.
