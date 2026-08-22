# Airlock — evaluation report

Reproduce: `python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55`

> **NOT REPORTABLE.** Selftest mode. These numbers exercise the harness; they are not evidence.

## Headline

- **False-positive rate: 0.40% [0.16%, 1.02%] (4/1000)**
- Latency p50 / p95: **7 ms / 481 ms**
- Escalation rate (reached a model): **15.0%**
- Recall on the sensitive split: **97.75% [95.78%, 98.81%] (391/400)**
- ECE: **0.1026**

## False positives by source

| Source | n | FP | FPR | 95% CI |
|---|---|---|---|---|
| CFPB | 148 | 0 | 0.00% | [0.00%, 2.53%] |
| HumanEval | 176 | 3 | 1.70% | [0.58%, 4.89%] |
| MBPP | 165 | 0 | 0.00% | [0.00%, 2.28%] |
| StackExchange | 161 | 0 | 0.00% | [0.00%, 2.33%] |
| Wikipedia | 173 | 1 | 0.58% | [0.10%, 3.20%] |
| WildChat-1M | 177 | 0 | 0.00% | [0.00%, 2.12%] |

## Recall by class

| Class | n | TP | Recall | 95% CI |
|---|---|---|---|---|
| CREDENTIAL | 50 | 49 | 98.0% | [89.5%, 99.6%] |
| CUSTOMER_RECORD | 51 | 49 | 96.1% | [86.8%, 98.9%] |
| FINANCIAL_NONPUBLIC | 50 | 49 | 98.0% | [89.5%, 99.6%] |
| GOV_ID | 43 | 43 | 100.0% | [91.8%, 100.0%] |
| HEALTH_RECORD | 50 | 49 | 98.0% | [89.5%, 99.6%] |
| LEGAL_HR | 61 | 60 | 98.4% | [91.3%, 99.7%] |
| PAYMENT_CARD | 49 | 47 | 95.9% | [86.3%, 98.9%] |
| PROPRIETARY_CODE | 46 | 45 | 97.8% | [88.7%, 99.6%] |

## False positives by language

The corpus is multilingual; the classifier prompt is English. This table
reports that rather than asserting it.

| Language | n | FP | FPR | 95% CI |
|---|---|---|---|---|
| unknown | 1000 | 4 | 0.40% | [0.16%, 1.02%] |

## Precision at prevalence

The argument for why FPR matters more than recall.

| Prevalence | Precision |
|---|---|
| 0.5% | 0.551 |
| 2.0% | 0.833 |
| 5.0% | 0.928 |

At π=2% the measured FPR gives precision **0.833**. At a 3% FPR the same detector gives **0.399** — ten times the false-positive rate turns a usable control into one people switch off.
