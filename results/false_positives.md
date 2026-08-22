# False positives — every one, for hand-adjudication

Threshold 0.55. 4 of 1000 benign items blocked.

Adjudicate each row and record the verdict in the `Adjudication` column. Report
the corrected count in the submission, e.g. *"7 blocked; on review 3 contained a
genuine live-looking key the corpus author had pasted; corrected FP = 4/1000"*.
This turns the corpus's weakness into a demonstration of rigour.

## 1. `selftest:benign:246` — HumanEval

- p_block **0.5776** · tier `T2` · predicted `CUSTOMER_RECORD` · 1978 chars
- evidence spans: `['synthetic span']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 2. `selftest:benign:521` — HumanEval

- p_block **0.833** · tier `T1` · predicted `CUSTOMER_RECORD` · 3770 chars
- evidence spans: `['synthetic span']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 3. `selftest:benign:830` — Wikipedia

- p_block **0.6971** · tier `T1` · predicted `CUSTOMER_RECORD` · 2681 chars
- evidence spans: `['synthetic span']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 4. `selftest:benign:836` — HumanEval

- p_block **0.5932** · tier `T0` · predicted `CUSTOMER_RECORD` · 3820 chars
- evidence spans: `['synthetic span']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

