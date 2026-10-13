# PLAN.md — what is left, and the bugs found in the October audit

Audit run 2026-10-13 against `main` @ `34d01a6`. All three dev branches fully merged;
nothing stranded. **69 tests green.** Every finding below was reproduced, not inferred —
the command that proves it is listed with it.

---

## Where we actually are

| | Status |
|---|---|
| Detector T0 / T1 / T2 | working, measured on live models |
| Benign corpus | 1000 items, 6 real sources, 0 hash mismatches, scored set == corpus exactly |
| **FPR** | **4.00% [2.95%, 5.40%]** (40/1000), verdict and p_block agree |
| **Recall** | **98.50% [96.77%, 99.31%]** (394/400) — *corrected this audit, was published as 87.78%* |
| Hard negatives wrongly blocked | 1/50 = 2.0% [0.4%, 10.5%] |
| Mongo, console, WebSocket, overlay | working; overlay verified in a real browser |
| Stack evidence | `rule02-providers.txt`, `policy-denied.json`, `proof_*.log` present |
| Screenshots, demo PNG, demo video | present |
| Ablation table | **missing** |
| `SUBMISSION.final.md` | **not generated** |

---

## Bugs — fixed in this audit

### F1. Recall counted hard negatives as recall targets — **fixed** (C)

The sensitive corpus holds 400 sensitive items plus 50 `HARD_NEGATIVE` items labelled
BENIGN. Both `run_fpr.py` and `report.py` put all 450 in the recall denominator, so 49
*correct* allows were scored as misses.

```
published   395/450 = 87.78%
correct     394/400 = 98.50%  [96.77%, 99.31%]
```

It also produced a `BENIGN: 1/50` row in `by_class`, and left the hard-negative FP line
SRS §14 asks for by name unreported. **B's slider inherited the error** — it computes
recall from the same float list. Fixed at the source in `run_fpr.py`, so B's code needs no
change. `tests/test_report_recall.py` fails on the old code (recall 0.78 vs 0.95,
`BENIGN` in `by_class`) and passes on the fix.

The README published the wrong figure on Sept 1; corrected, with a dated note saying so.

### F2. `HARD_NEGATIVE_RESULT` was a hand-filled placeholder — **fixed** (C)

`fill.py` now fills it from `fpr_report.json`. One fewer number typed by hand.

### F3. Lint in C's files — **fixed** (C)

Unused imports and placeholder-less f-strings. Cosmetic; no behaviour change.

---

## Bugs — open, with owner and fix

Ordered by what they cost.

### B1. Any website can read blocked secrets and poison the detector — **HIGH** (A)

The gateway sends `Access-Control-Allow-Origin: *` with
`Access-Control-Allow-Private-Network: true` and checks no origin anywhere. Proven against
the live service with `Origin: https://evil.example`:

```
OPTIONS /v1/decisions   → 204, allow-origin *, allow-private-network true
GET     /v1/decisions   → 200, allow-origin *
POST    /v1/feedback    → 200, {"ok":true,"embedded":true}
```

Two consequences:

- **`/v1/decisions` returns `evidence_spans`** — the literal blocked substrings, e.g. the
  customer row. Any page the employee visits can read back every secret Airlock stopped.
  For a DLP product the audit log is the worst place to have an exfiltration path.
- **`/v1/feedback` accepts writes**, so any page can mark decisions benign and teach the
  detector to stop blocking a pattern.

Chrome 142+ Local Network Access puts a permission prompt in front of public sites, which
blunts this — but not for other `localhost` origins, not in other browsers, and the server
itself has no defence at all.

**Fix:** replace `*` with an allowlist — the extension's `chrome-extension://<id>` origin
and `http://localhost:5173`. Reject any other `Origin` with 403 on every route, not just
OPTIONS. Then project `evidence_spans` out of `/v1/decisions` — the console shows host,
label, tier and latency, and never needs the span text.

**Verify:** the three curls above with `Origin: https://evil.example` must all return 403.

### B2. The block card renders the blocked payload into the destination site's DOM — **HIGH** (B)

`extension/overlay.js:251` — `host.attachShadow({ mode: 'open' })`. The card shows the
payload with the offending row underlined, inside an *open* shadow root in the page we are
blocking it from. Any script on `chatgpt.com` can read `host.shadowRoot.textContent` — and
so can any DOM-capturing session-replay tool the site runs, which is the realistic vector.

**Fix:** `mode: 'closed'`, and render the payload masked except the evidence span itself.
The robust version is the extension side panel rather than in-page DOM.

**Checked and clean, worth saying:** every model-influenced field in the card — `reason`,
`label`, clause text, the payload itself — goes through `esc()` before `innerHTML`. No XSS
via a crafted paste.

### B3. `p_block` cannot be calibrated as written — **HIGH** (A)

98.1% of scores sit at the extremes, and **812 of 1000 are exactly 0.0**. A softmax over
nine labels cannot produce an exact zero, so for those 812 pastes BENIGN was the only label
in the dict. Cause, `calib.py` `label_logits_from_logprobs`:

```python
return {lb: math.log(m) for lb, m in mass.items() if m > 0}
```

Labels absent from the top-20 are dropped entirely, so `p_block_from_logits` renormalises
over BENIGN alone and returns exactly 0.0 — **at every temperature**. Proven against A's own
functions:

```
CURRENT  T=1.0 → 0.0     T=3.0 → 0.0      T=8.0 → 0.0
FLOORED  T=1.0 → 0.0001  T=3.0 → 0.1471   T=8.0 → 0.6549
```

**Fix (one line):** floor each absent label at the smallest observed top-k logprob — a
valid upper bound on its mass:

```python
floor = min(c["logprob"] for c in entry["top_logprobs"])
return {lb: (math.log(m) if m > 0 else floor) for lb, m in mass.items()}
```

**Also:** no `results/calibration.json` exists, so **T has been 1.0 the entire time** —
temperature scaling was never applied. After the fix, run `bench/fit_calibration.py` on the
200-item dev split. And record each score's `source` (logprobs vs verbalized) in the run
output: right now the fallback rate is unauditable.

**What it unblocks:** the threshold slider, three distinct operating points, a real
reliability diagram, a meaningful ECE. Today all four are cosmetic.

### B4. `/v1/feedback` reports success when nothing was written — **MEDIUM** (A)

`app.py:540-541`:

```python
corpus_id = await mongo.write_back_corpus(decision_id)
return {"ok": True, "corpus_id": str(corpus_id), "embedded": True}
```

`write_back_corpus` returns `None` when Mongo is down, the decision is missing, or there is
nothing to embed. The endpoint still answers `"embedded": true` with
`"corpus_id": "None"` — observed live. The analyst clicks *Mark benign*, sees success, and
nothing happened. That is demo beat 4 failing silently.

**Fix:** `if corpus_id is None: return 503 with the fail-closed body`.

### B5. T2 latency is ~3× its target — **MEDIUM** (A)

NFR-L3 is p95 ≤ 600 ms; measured ~1.7 s single-paste, and the T2 budget was raised to
2.0 s to make the run pass. The cause is model choice, not code: §5.1 sized the budget for
a 4B on a dedicated `:8002`; we run T2 on the 30B. Options, in order of cost: report it
honestly as measured; or launch the 4B classifier with text dropped to 0.34 per SRS §7.3
(sum 0.34 + 0.28 + 0.09 = 0.71, under the 0.85 ceiling).

### B6. Escalation is 99.8% — **documented, not a code bug**

The benign corpus has a 200-char floor and T0 fires below 40, so T0 cannot fire on it.
Makes the FPR conservative and the throughput numbers unrepresentative. Stated in the
README and SUBMISSION.md. `data/shortpaste_v1.jsonl` exists to show T0 works —
**it has never been run against the service.**

### B7. `@app.on_event` is deprecated — **LOW** (A)

`app.py:74` and `:80`. Works today; removed in a future FastAPI. Move to a `lifespan`
handler. Also `starlette.testclient` warns about `httpx` — pin or move to `httpx2`.

### B8. The committed manifest predates the provenance gate — **LOW** (C)

`data/benign_v1.manifest.json` has no `sources_used` / `provenance_ok` fields, because the
corpus was rebuilt on the box before the gate landed. The corpus itself passes (6 sources,
max share 40% < 55%), but the attestation is not in the artifact. Re-run
`build_benign.py --seed 1337` on the box; the seed makes it deterministic.

---

## The plan

### Phase 1 — fix what changes the numbers (≈1.5 h)

| # | Task | Owner | Done when |
|---|---|---|---|
| 1 | **B3** floor absent labels in `calib.py` | A | `p_block==0.0` count drops from 812 to ~0 |
| 2 | Run `bench/fit_calibration.py` on the dev split | A | `results/calibration.json` exists, T ≠ 1.0 |
| 3 | Record `p_source` per item in the run | A | fallback rate is a number in the report |
| 4 | Re-run `run_fpr.py` with the sensitive split | box | `scores_sensitive.json` on disk, recall 394/400 reproduced |
| 5 | `report.py` | C | recall 98.5%, hard-negative line present, slider spread visible |

### Phase 2 — fix what is unsafe (≈1 h)

| # | Task | Owner | Done when |
|---|---|---|---|
| 6 | **B1** origin allowlist + drop `evidence_spans` from `/v1/decisions` | A | evil-origin curls all 403 |
| 7 | **B2** closed shadow root, masked payload | B | `host.shadowRoot === null` from page context |
| 8 | **B4** feedback returns 503 on `None` | A | Mongo-down feedback ≠ `embedded:true` |

### Phase 3 — finish the evidence (≈2 h)

| # | Task | Owner | Done when |
|---|---|---|---|
| 9 | Ablation rows 2–4 | A | `results/ablation_table.md` with 4 rows |
| 10 | Run the T0 probe set against the service | box | 40/40 `tier=T0`, reported as its own line |
| 11 | Hand-adjudicate the 40 FPs | C | `false_positives.md` annotated, corrected count stated |
| 12 | Re-run `build_benign.py` for the manifest attestation | box | `provenance_ok: true` in the manifest |

### Phase 4 — ship (≈30 min)

| # | Task | Owner | Done when |
|---|---|---|---|
| 13 | `python submission/fill.py` | C | `grep -c '{{' SUBMISSION.final.md` → 0 |
| 14 | Re-check every number in README / PITCH against `fpr_report.json` | C | no drift |
| 15 | **B5, B7** | A | optional — honest reporting is acceptable for B5 |

**Critical path:** 1 → 2 → 4 → 5 → 9 → 13. Everything in Phase 2 can run in parallel with
it, and should — B1 and B2 are the two findings a security-minded judge would raise first.

---

## Checks to run after every phase

```bash
.venv/bin/python -m pytest tests/ -q
```

```bash
python bench/report.py && python -c "import json;d=json.load(open('results/fpr_report.json'));print(d['reportable'],d['verdict_fpr_statement'],d['recall_statement'],d['hard_negative']['statement'],d['p_block_saturated_frac'])"
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' "localhost:8787/v1/decisions?limit=1" -H "Origin: https://evil.example"
```

Expect: tests green · `reportable True` · recall ≈98.5% · saturation well under 0.98 after
B3 · `403` after B1.
