# Airlock — evaluation report

Reproduce: `python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55`

## Headline

- **False-positive rate: 4.00% [2.95%, 5.40%] (40/1000)**
- Latency p50 / p95: **5880 ms / 8994 ms**
- Escalation rate (reached a model): **99.8%**
- Recall on the sensitive split: **87.78% [84.43%, 90.49%] (395/450)**
- ECE: **0.0665**

## Which tier resolved each paste

| Tier | n | % |
|---|---|---|
| T2 | 998 | 99.8% |
| ERR | 2 | 0.2% |

> **Escalation is near-total because the benign corpus has a 200-character floor and the T0 fast path only fires below 40 characters. FPR is measured on the hard subset and is therefore conservative; escalation rate, blended latency and seats-per-box from this run are NOT representative of a real paste distribution and must be reported with this caveat.**

## False positives by source

| Source | n | FP | FPR | 95% CI |
|---|---|---|---|---|
| CFPB | 120 | 29 | 24.17% | [17.39%, 32.55%] |
| HumanEval | 80 | 0 | 0.00% | [0.00%, 4.58%] |
| MBPP | 100 | 0 | 0.00% | [0.00%, 3.70%] |
| StackExchange | 200 | 0 | 0.00% | [0.00%, 1.88%] |
| Wikipedia | 100 | 0 | 0.00% | [0.00%, 3.70%] |
| WildChat-1M | 400 | 11 | 2.75% | [1.54%, 4.86%] |

## Recall by class

| Class | n | TP | Recall | 95% CI |
|---|---|---|---|---|
| BENIGN | 50 | 1 | 2.0% | [0.4%, 10.5%] |
| CREDENTIAL | 70 | 69 | 98.6% | [92.3%, 99.7%] |
| CUSTOMER_RECORD | 60 | 55 | 91.7% | [81.9%, 96.4%] |
| FINANCIAL_NONPUBLIC | 60 | 60 | 100.0% | [94.0%, 100.0%] |
| GOV_ID | 45 | 45 | 100.0% | [92.1%, 100.0%] |
| HEALTH_RECORD | 45 | 45 | 100.0% | [92.1%, 100.0%] |
| LEGAL_HR | 35 | 35 | 100.0% | [90.1%, 100.0%] |
| PAYMENT_CARD | 45 | 45 | 100.0% | [92.1%, 100.0%] |
| PROPRIETARY_CODE | 40 | 40 | 100.0% | [91.2%, 100.0%] |

## False positives by language

The corpus is multilingual; the classifier prompt is English. This table
reports that rather than asserting it.

| Language | n | FP | FPR | 95% CI |
|---|---|---|---|---|
| latin | 944 | 38 | 4.03% | [2.95%, 5.48%] |
| cjk | 35 | 2 | 5.71% | [1.58%, 18.61%] |
| cyrillic | 20 | 0 | 0.00% | [0.00%, 16.11%] |
| arabic | 1 | 0 | 0.00% | [0.00%, 79.35%] |

## Precision at prevalence

The argument for why FPR matters more than recall.

| Prevalence | Precision |
|---|---|
| 0.5% | 0.099 |
| 2.0% | 0.309 |
| 5.0% | 0.536 |

At π=2% the measured FPR gives precision **0.309**. At a 3% FPR the same detector gives **0.374** — ten times the false-positive rate turns a usable control into one people switch off.
