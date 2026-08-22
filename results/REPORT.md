# Airlock — evaluation report

Reproduce: `python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55`

## Headline

- **False-positive rate: below 6.00% at 95% confidence by the rule of three (0/50)**
- Latency p50 / p95: **7 ms / 438 ms**
- Escalation rate (reached a model): **100.0%**
- ECE: **0.0382**

## Which tier resolved each paste

| Tier | n | % |
|---|---|---|
| T2 | 50 | 100.0% |

> **Escalation is near-total because the benign corpus has a 200-character floor and the T0 fast path only fires below 40 characters. FPR is measured on the hard subset and is therefore conservative; escalation rate, blended latency and seats-per-box from this run are NOT representative of a real paste distribution and must be reported with this caveat.**

## False positives by source

| Source | n | FP | FPR | 95% CI |
|---|---|---|---|---|
| SYNTHETIC | 50 | 0 | 0.00% | [0.00%, 7.13%] |

## False positives by language

The corpus is multilingual; the classifier prompt is English. This table
reports that rather than asserting it.

| Language | n | FP | FPR | 95% CI |
|---|---|---|---|---|
| unknown | 50 | 0 | 0.00% | [0.00%, 7.13%] |
