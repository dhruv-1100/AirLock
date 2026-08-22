# Corpus attribution — `benign_v1`

> **THIS CORPUS CONTAINS SYNTHETIC PLACEHOLDER TEXT. It exists to wire the harness end to end. Do NOT report an FPR from it. bench/report.py will refuse to emit a headline number while corpus_is_real is false.**

Six independent sources, so no single licence challenge can sink the denominator.

Reproduce: `python bench/build_benign.py --seed 1337 --out data/benign_v1.jsonl`

| Source | n | Licence | Method | URL |
|---|---|---|---|---|
| WildChat-1M | 400 | ODC-BY | synthetic | https://huggingface.co/datasets/allenai/WildChat-1M |
| StackExchange | 200 | CC BY-SA 4.0 | synthetic | https://archive.org/details/stackexchange |
| MBPP | 100 | CC-BY-4.0 | synthetic | https://huggingface.co/datasets/google-research-datasets/mbpp |
| HumanEval | 80 | MIT | synthetic | https://huggingface.co/datasets/openai/openai_humaneval |
| CFPB | 120 | US Government / public domain | synthetic | https://www.consumerfinance.gov/data-research/consumer-complaints/ |
| Wikipedia | 100 | CC BY-SA 4.0 | synthetic | https://dumps.wikimedia.org/ |

**Total: 1000** · `corpus_is_real: false`

## Notes

- WildChat records with `toxic == True` or the PII-redaction flag set are excluded.
- Only the first user turn of a WildChat conversation is used.
- Records are de-duplicated by SHA-256 of the text before sampling.
- Length window: 200–4000 characters.

## If a judge challenges the Stack Exchange terms

Pre-computed answer: drop Stack Exchange to 100 and raise WildChat to 500
(ODC-BY, no such condition), then re-run the single seeded command above and
re-report. The corpus is regenerable; the number moves, the method does not.
