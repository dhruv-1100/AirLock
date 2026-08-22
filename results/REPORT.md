# Airlock — evaluation report

Reproduce: `python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55`

## Headline

- **False-positive rate: 6.80% [5.40%, 8.53%] (68/1000)**
- Latency p50 / p95: **2 ms / 4 ms**
- Escalation rate (reached a model): **0.2%**
- Recall on the sensitive split: **87.78% [84.43%, 90.49%] (395/450)**
- ECE: **0.0845**

## Which tier resolved each paste

| Tier | n | % |
|---|---|---|
| CACHE | 998 | 99.8% |
| T2 | 2 | 0.2% |

## False positives by source

| Source | n | FP | FPR | 95% CI |
|---|---|---|---|---|
| CFPB | 120 | 41 | 34.17% | [26.29%, 43.03%] |
| HumanEval | 80 | 0 | 0.00% | [0.00%, 4.58%] |
| MBPP | 100 | 0 | 0.00% | [0.00%, 3.70%] |
| StackExchange | 200 | 0 | 0.00% | [0.00%, 1.88%] |
| Wikipedia | 100 | 0 | 0.00% | [0.00%, 3.70%] |
| WildChat-1M | 400 | 27 | 6.75% | [4.68%, 9.64%] |

## Recall by class

| Class | n | TP | Recall | 95% CI |
|---|---|---|---|---|
| BENIGN | 50 | 0 | 0.0% | [0.0%, 7.1%] |
| CREDENTIAL | 70 | 70 | 100.0% | [94.8%, 100.0%] |
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
| latin | 944 | 65 | 6.89% | [5.44%, 8.68%] |
| cjk | 35 | 3 | 8.57% | [2.96%, 22.38%] |
| cyrillic | 20 | 0 | 0.00% | [0.00%, 16.11%] |
| arabic | 1 | 0 | 0.00% | [0.00%, 79.35%] |

## Precision at prevalence

The argument for why FPR matters more than recall.

| Prevalence | Precision |
|---|---|
| 0.5% | 0.061 |
| 2.0% | 0.208 |
| 5.0% | 0.405 |

At π=2% the measured FPR gives precision **0.208**. At a 3% FPR the same detector gives **0.374** — ten times the false-positive rate turns a usable control into one people switch off.
