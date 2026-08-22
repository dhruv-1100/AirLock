# What's left, by developer

State as of the bring-up run. Both models are up (0.68 of a 0.85 ceiling), MongoDB is
seeded, the `airlock` sandbox is Ready, and the detector has a real measured number.

---

## A — Inference

| # | Task | Cost | Why it blocks |
|---|---|---|---|
| A1 | **Re-run the harness against your own p_block fix.** The code fix is in `473e5d0`; the *artifact* is not. `results/scores_benign.json` still shows 925 / 15 / 60 — the saturated distribution C reported. Until it is re-run, the slider stays inert and Audit/Balanced/Strict stay identical. B has one running now; if it lands clean this is done. | done-or-15min | Slider, three operating points, ECE, and the 5.30 vs 6.90 headline |
| A2 | **Ablation rows 2–4.** Row 1 exists (`bench/t1_offline.py`, 0/1000 T1-HIGH FPs). Rows 2–4 are T2-without-span-verification, T2-with, and full router at τ=0.55. Row 3 minus row 2 is the best single finding in the project if it replicates. | 3 runs | §14 requires four rows |
| A3 | **Decide what to do about T3.** 10–20 s per image on the 30B against a 2500 ms client abort. NFR-L4's gate (p50 ≤ 1.5 s, p95 ≤ 2.5 s) fails — that is the first measurement anyone has taken of it. Either accept and frame the image path as asynchronous, or drop to a smaller VLM. See `results/t3_latency.md`. | decision | Beat 3 |
| A4 | **Get the demo chart to block.** It transcribes correctly — `'FY26 Revenue Forecast — Plan vs. Commit'` is in `extracted_text` — then returns `allow BENIGN` with zero `evidence_spans`, because the model narrates its markers in prose instead of populating the field. Span verification then forces BENIGN, correctly. `gate_01.png` blocks fine, so the tier is sound; this is prompt adherence in `t3.py`. | ~30 min | Beat 3 does not currently block |
| A5 | Optional: revisit the six launch-time constants B made env-driven during bring-up (`T2_TIMEOUT_S` 1.2→2.0, `TOTAL_BUDGET_S`, `T3_TIMEOUT_S`, the moe-backend / FlashInfer / MTP flags). All default to the original behaviour; all are documented at the point of change. | 20 min | Nothing — review only |

---

## B — Client & UI (me)

| # | Task | Cost | Status |
|---|---|---|---|
| B1 | **Three screenshots** — block card, console, proof. | — | **DONE.** Chrome 151 installed, captured headless: `screenshots/verdict-card.png`, `console.png` (the standalone console against the LIVE service, real decisions mid-harness-run), `proof.png`. |
| B2 | **Three beats through Chrome against the real service.** | 20 min | Now unblocked by Chrome 151. Not started. Beat 3 will not pass until A4. |
| B3 | **The two MV3 paragraphs for the submission.** | 20 min | Mine, not started. Everything needed is in `NOTES_B.md`. |
| B4 | Re-copy `results/scores_benign.json` over both console fixtures after A1 lands. | 1 min | Waiting on A1 |

---

## C — Stack, Data & Writeup

| # | Task | Cost | Why it blocks |
|---|---|---|---|
| C1 | **Hand-adjudicate the false positives**, itemised. `results/false_positives.md` is generated and ready. Your §13 read is right and B's was wrong: CFPB being 12% of the corpus and 41 of 69 FPs means CFPB was a poor BENIGN source, not that our FPR is really 3.2%. Report measured, publish per-source, give ex-CFPB as a labelled sensitivity analysis. | ~30 min | §14 requires it itemised |
| C2 | **`SUBMISSION.final.md`** — does not exist yet. Blocked on A1 and A2. | after A | The submission |
| C3 | **Correct `RUNBOOK-C.md` against the installed CLIs.** The working command table is in `RUNBOOK-C-FINDINGS.md`. Headline: there is no `nemoclaw host probe`, no `profiles`, and `policy add/list/explain` are hyphenated `policy-add` etc.; `nemoclaw airlock <verb>` should be `openshell sandbox exec -n airlock`. | 15 min | Anyone following the runbook cold |
| C4 | **Say in the writeup that `sensitive_v1.jsonl` is not in the repo** and why: GitHub push protection rejects it (GH013) on the synthetic Slack and AWS keys. Fake, but convincing enough to trip a scanner — which is what a CREDENTIAL corpus is for. The attachment is the builder plus manifest. | 5 min | §14 attachment list |

---

## Unowned / whole-team

| # | Task | Note |
|---|---|---|
| X1 | **OpenClaw is not installed into the sandbox.** The `airlock` sandbox exists and has the local inference route, but the agent runtime and `skills/airlock-verdict-explainer/` are not deployed. Everything Rule 02 needs is already evidenced without it, so this is a completeness item, not a blocker. | ~1 h |
| X2 | **Nobody has rehearsed anything end to end.** Zero dress runs. | 1 h |
| X3 | **MongoDB was listening on `0.0.0.0:27017` with no auth.** Found by fixing `proof.sh` (below). On a product whose claim is "nothing leaves this machine", an unauthenticated database on every interface is the finding proof.sh itself says to look for. `up_mongo.sh` now publishes `127.0.0.1:27017:27017`. **The running container still has the old binding** — recreate it once the harness run finishes. | 2 min |
| X4 | **`proof.sh`'s listener check silently proved nothing.** Its awk filter used `\b`, which POSIX ERE does not support, so it matched no rows and printed a bare header under "expect 127.0.0.1 only". An empty table there reads as proof when it is the absence of proof. Fixed. | done |
| X5 | `proof.sh` says "a 35B and a 7B VLM are co-resident" — both models are 30B. Same stale labels were in both consoles; fixed there. C owns proof.sh. | 1 min |

---

## Already done, so nobody re-does it

- Both models up on the pre-staged weights (0.40 + 0.28 = 0.68), warm, MongoDB seeded, search indexes READY and queryable, retrieval returning real hits.
- `airlock` sandbox Ready; inference routes only to the local 30B; `evidence/policy-denied.json` (all four cloud LLM hosts, 403 `policy_denied`) and `evidence/rule02-providers.txt` both captured.
- FPR **6.80% [5.40%, 8.53%]**, recall **87.78% [84.43%, 90.49%]**, `reportable: true`, ROC/PR/reliability figures generated.
- `benign_v1` all six sources real, n=1000; `sensitive_v1` built (450); 121 demo/gate/benign images including the real `fy26_forecast.png`.
- `proof.sh` captured to `results/proof_*.log`; the four §14 evidence attachments are now tracked rather than gitignored.
