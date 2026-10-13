# Airlock

**Airlock intercepts the clipboard payload the moment company data is about to leave a
laptop for an unapproved cloud AI tool, inspects it locally on a Dell Pro Max with GB10,
blocks it with a cited policy clause, and re-routes the question to a 30B model on the box
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
| Recall | **98.50%  [96.77%, 99.31%]  (394/400)** — synthetic set, so an **upper bound** |
| Hard negatives wrongly blocked | 1/50 = 2.0%  [0.4%, 10.5%] — reported as its own line |
| Threshold | 0.55 (Balanced), selected on dev, reported on test |
| Adjudicated | 38/1000 = 3.80% [2.78%, 5.17%] after removing 2 correct blocks — see `results/adjudication.md` |
| Interruption tax | ~8,000 wrong blocks a week at 5,000 employees × 40 pastes — about one paste in 25 |

> **No industry multiplier.** The often-quoted 51% ([Cyberhaven survey](https://www.cyberhaven.com/blog/dlp-false-positives))
> is the share of DLP *alerts* that are wrong; ours is the share of *benign pastes* blocked.
> Like for like, our share of wrong blocks matches 51% at ~3.8% prevalence — the same range,
> not better. An earlier version of this README claimed "12.8× better"; that was wrong.

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

**The GB10 is no longer available.** Measurement is over; the numbers above are final.
`PLAN.md` lists what was never measured and why.

**Working and measured:** the detector end to end on live models, the corpus and harness,
the Mongo layer, the console and WebSocket feed, the block overlay, the sandbox egress
evidence, the T0 fast path (40/40, p50 4.8 ms), and a recorded demo.

**Known limitations — stated here rather than discovered:**

- **The false-positive rate missed the under-1% design target.** It is 4.00%.
- **Most errors are one fixable kind.** 12 of the 33 genuine classifier errors fired on
  CFPB's `XXXX` redaction masks, read as card numbers or SSNs; 13 more are consumer
  credit-dispute letters labelled LEGAL_HR. **We previously said CFPB blocks were
  defensible because the narratives contain identifiers. They don't — CFPB redacts them.**
- **The scores barely spread, so the operating points barely differ.** 98.1% of scores
  sat below 0.05 or above 0.95 because of a bug that dropped absent labels before
  normalising (812 of 1000 were exactly 0.0). Fixed in `calib.py` with tests — **but the
  fix was never re-run against the live model**, and no calibration temperature was fitted.
- **Escalation is 99.8%.** The corpus has a 200-character floor and T0 fires below 40, so
  T0 cannot fire on it. That makes the FPR conservative and any throughput figure from this
  corpus unrepresentative — so none is reported.
- **The image path is not interactive.** 10–20 s per image with the 30B vision model, and
  the demo chart did not block (`results/t3_latency.md`).
- **The sensitive corpus is synthetic**, so recall is an upper bound.
- **Language is not a driver.** Pre-registered and checked on the final run: latin 38/944,
  cjk 2/35, cyrillic 0/20 — overlapping intervals, no effect.
- **Adjudication had one reviewer**; no inter-rater claim is made.
- MongoDB Community runs without auth on loopback; evidence is AES-GCM encrypted with a key
  in a 0600 file, because Queryable Encryption is Enterprise/Atlas only.

**Corrections (Oct 2026):** recall was first published here as 87.78% (395/450) — the
tooling counted the 50 hard negatives as recall targets; the true figure is 394/400 =
98.50%. And the "12.8× better than industry" claim compared two different metrics.

**Outstanding:** see `PLAN.md`.

---

## The one operational rule

**Only one person starts, stops or restarts a GPU process.** On this box unbounded
allocation freezes the whole host — no SSH, no ping — rather than raising OOM. Summed
`--gpu-memory-utilization` must never exceed **0.85**; the committed demo value is
**0.68**. Update the running total *before* a launch, never after.
