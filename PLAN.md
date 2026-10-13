# PLAN.md — project status after the GB10

**Updated 2026-10-13. The GB10 is no longer available, so measurement is over.** The
numbers in `results/` are final. What remains is keeping every written claim tied to them,
plus a few tasks that need a person rather than a GPU.

Check that nothing has drifted, at any time:

```bash
.venv/bin/python -m pytest tests/ -q
```

```bash
.venv/bin/python submission/check_claims.py
```

```bash
.venv/bin/python submission/fill.py
```

Expect 88 passing tests, every claim `ok`, and `no placeholders remain`.

---

## Final measured results

| | Value | Source |
|---|---|---|
| False-positive rate | **4.00% [2.95%, 5.40%]** (40/1000) | `results/fpr_report.json` |
| After adjudication | 38/1000 = 3.80% (2 blocks were correct — live credentials in the corpus) | `results/adjudication.md` |
| Recall (synthetic) | **98.50% [96.77%, 99.31%]** (394/400) | `results/fpr_report.json` |
| Hard negatives blocked | 1/50 | `results/fpr_report.json` |
| Code & technical text | 0 false positives in 480 items | `results/fpr_report.json` |
| T1 with no model | 0/1000 benign blocked; 105/400 sensitive blocked | `results/t1_offline*.json` |
| T0 fast path | 40/40 resolved, p50 4.8 ms | `results/t0_fastpath.md` |
| Image path | 10–20 s per image; demo chart **not** blocked | `results/t3_latency.md` |
| Memory, both models warm | 47,847 + 35,325 MiB resident, 25.06 GB free | `results/proof_*.log` |
| Sandbox egress | 1 local inference endpoint; 4 cloud APIs → 403 | `evidence/rule02-providers.txt` |

---

## Done in the October audit

**Reporting bugs (would have put wrong numbers in the submission):**

- **Recall** counted the 50 hard negatives as recall targets: published 87.78%, true 98.50%.
  Fixed in `run_fpr.py` / `report.py`; `results/fpr_report.json` corrected from its own
  per-class counts, with the derivation recorded in the file.
- **The industry comparison was invalid.** "12.8× better than the 51% industry average"
  divided a false-positive *rate* by a survey's share of wrong *alerts*. Withdrawn
  everywhere; the like-for-like comparison is in `SUBMISSION.md` §2.
- **The CFPB explanation was wrong.** We said its blocks were defensible because the
  narratives contain identifiers; CFPB redacts them to `XXXX`, and the model mistook the
  masks for card numbers. Corrected everywhere.
- **The submission described the planned system, not the measured one:** a Qwen 35B, a
  Holo 7B and a 4B classifier that never ran, a throughput sweep "run twice" that never ran,
  NVIDIA baseline exclusions never applied, a cable unplug never captured, and ROC / PR /
  reliability figures drawn with the hard negatives counted as positives. All rewritten or
  withdrawn. `submission/check_claims.py` now verifies 35 hand-written numbers against
  their source files.

**Code bugs (fixed and pinned by `tests/test_audit_fixes.py`; 15 of its 19 tests fail on
the old code):**

| | Fix |
|---|---|
| B1 | Any website could read blocked secrets from `/v1/decisions` and write to `/v1/feedback`. Origin allowlist (`services/inspect/origins.py`), WebSocket included; blocked text and hashes removed from the decision feed. |
| B2 | The block card rendered the secret in an open shadow root inside the destination site. Now closed, showing only evidence-bearing lines. |
| B3 | 812/1000 scores were exactly 0.0 because absent labels were dropped before normalising; temperature could never move them. Floored instead. |
| B4 | `/v1/feedback` reported success when nothing was written. Now 503. |
| B7 | Deprecated FastAPI startup hooks replaced with a lifespan. |

**Adjudication:** all 40 false positives reviewed — 2 correct blocks, 2 timeouts,
3 borderline, 33 genuine errors (`results/adjudication.md`).

---

## Permanently not measured — needs hardware we no longer have

Each is marked "not measured" in `SUBMISSION.md` rather than estimated.

| | Why it matters |
|---|---|
| **Re-run after the B3 fix** | The scoring fix is verified by unit test only. Its effect on the real score distribution is unknown. |
| **Temperature calibration** | No temperature was ever fitted; the calibration story rests on it. |
| **Ablation rows 2–4** | Only row 1 (T1 alone) exists. |
| **Throughput sweep, seats per box, cost per seat** | All derived from the sweep, which never ran. |
| **Image false-positive rate** | Only four image calls were ever made. |
| **Offline (cable-unplugged) demonstration** | Planned, never captured. |

---

## Still to do — needs a person, not a GPU

| # | Task | Who | Why |
|---|---|---|---|
| 1 | **Find the 121 s demo recording.** It was never committed. If it only lived on the GB10, fall back to the 62 s cut: `git show 0878291:submission/airlock-demo.mp4 > airlock-demo.mp4`. Both show the superseded "recall 87.8%" on screen — narrate the correction (`submission/PITCH.md`). | B | the only recording of the real system |
| 2 | **Second reviewer for `results/adjudication.md`.** Agree or disagree with each category, then report agreement. | anyone but C | an inter-rater figure cannot come from one reviewer |
| 3 | **A human ⌘V test.** The recording used synthetic paste events. A real paste can be tested without the GB10 on any machine: load the extension, run the service with `MONGO_ENABLED=false`, paste an AWS-key-shaped string — T1 blocks it with no model. | B | B's own open note in `airlock-demo.md` |
| 4 | **Pin `AIRLOCK_EXTENSION_ID`** for any real deployment. Until then any Chrome extension may call the restricted routes. | deployer | B1 hardening |
| 5 | Keep `evidence/nemoclaw-status.json` and `evidence/nemoclaw-policy-list.txt` out of anything presented as evidence. They describe a different sandbox (`my-qwen-claw`, Qwen via Ollama, Hugging Face / npm / OpenRouter enabled), not Airlock's. | C | they undercut the egress claim |

## If hardware becomes available again

In this order — each one changes numbers that are currently final:

1. Strip runs of `XXXX`-style redaction masks before classification — the largest error
   class (12 of 33). Re-run the 1000-item harness.
2. Re-run with the B3 fix, then fit the temperature on a held-out split.
3. Ablation rows 2–4.
4. A smaller vision model, and re-measure image latency.

**One caveat on the link between code and numbers.** The published results describe the
code as it ran in August. One fix since then touches scoring: B3 fills in labels that were
missing from the model's top-20 instead of dropping them. That moves the 812 exact-0.0
scores up slightly and the 16 exact-1.0 scores down slightly, so it should not flip any
decision at τ = 0.55 — but that has not been confirmed on the live model. The other fixes
(B1, B2, B4, B7) change no detection decision at all. Larger detector changes, like
stripping redaction masks, were deliberately **not** made: changing what the detector does
without being able to re-measure it would leave the published numbers describing code that
no longer exists.
