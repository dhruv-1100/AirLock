# Airlock — evaluation report

Reproduce: `python bench/run_fpr.py --seed 1337 --n 1000 --threshold 0.55`

## Headline

- **False-positive rate: 6.90% [5.49%, 8.64%] (69/1000)**
- Latency p50 / p95: **5928 ms / 9203 ms**
- Escalation rate (reached a model): **99.8%**
- ECE: **0.0695**

## False positives by source

| Source | n | FP | FPR | 95% CI |
|---|---|---|---|---|
| CFPB | 120 | 41 | 34.17% | [26.29%, 43.03%] |
| HumanEval | 80 | 0 | 0.00% | [0.00%, 4.58%] |
| MBPP | 100 | 0 | 0.00% | [0.00%, 3.70%] |
| StackExchange | 200 | 0 | 0.00% | [0.00%, 1.88%] |
| Wikipedia | 100 | 0 | 0.00% | [0.00%, 3.70%] |
| WildChat-1M | 400 | 28 | 7.00% | [4.89%, 9.93%] |

## False positives by language

The corpus is multilingual; the classifier prompt is English. This table
reports that rather than asserting it.

| Language | n | FP | FPR | 95% CI |
|---|---|---|---|---|
| latin | 944 | 66 | 6.99% | [5.53%, 8.80%] |
| cjk | 35 | 3 | 8.57% | [2.96%, 22.38%] |
| cyrillic | 20 | 0 | 0.00% | [0.00%, 16.11%] |
| arabic | 1 | 0 | 0.00% | [0.00%, 79.35%] |
