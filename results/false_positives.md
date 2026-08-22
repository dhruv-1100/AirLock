# False positives — every one, for hand-adjudication

Threshold 0.55. 40 of 1000 benign items blocked.

Adjudicate each row and record the verdict in the `Adjudication` column. Report
the corrected count in the submission, e.g. *"7 blocked; on review 3 contained a
genuine live-looking key the corpus author had pasted; corrected FP = 4/1000"*.
This turns the corpus's weakness into a demonstration of rigour.

## 1. `wildchat:e5a3efada0c3ce18c60a2295738b8571` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `HEALTH_RECORD` · 491 chars
- evidence spans: `['Patricia Bertier is a young active woman who has been suffering from several conditions, including mild bilateral hip', 'bilateral hip dislocation and narrowing of the birth canal']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 2. `wildchat:4b93f2ee31db290820c5408d061f796f` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `PROPRIETARY_CODE` · 3129 chars
- evidence spans: `['access_token =', 'account_id =', 'https://graph.facebook.com/v11.0/{account_id}/media']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 3. `cfpb:6427` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 815 chars
- evidence spans: `['My consumer report contains data that was obtained through identity theft']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 4. `cfpb:6150` — CFPB

- p_block **0.8446** · tier `T2` · predicted `LEGAL_HR` · 1270 chars
- evidence spans: `['15 U.S.C 1681 section 604 A Section 2 : It also states a consumer reporting agency can not furnish a account without my']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 5. `wildchat:fb8b1efef359a99949b2e99ef86237c9` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `HEALTH_RECORD` · 476 chars
- evidence spans: `['Patricia Bertier is a young active woman who has been involved in a serious car accident, suffering multiple severe inj']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 6. `cfpb:4172` — CFPB

- p_block **0.9361** · tier `T2` · predicted `PAYMENT_CARD` · 2573 chars
- evidence spans: `['XXXX XXXX XXXX, XXXX.', 'XXXX XXXX XXXX.', 'XXXX XXXX, LA XXXX XX/XX/year> First Source Advantage XXXX XXXX XXXX XXXXXXXX XXXX  XXXX XXXX NY XXXX ACCOUNT XXXX : XXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 7. `wildchat:8080c7b9308009818f5ddb803ccf148f` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `PROPRIETARY_CODE` · 456 chars
- evidence spans: `['move_rcpt_id CHAR VARYING 0 0 False False 移库单号', 'raw_id CHAR VARYING 0 0 True False 原料主键', 'material_type CHAR VARYING 255 0 True False 材质']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 8. `wildchat:a07842b1a28cca9853c88c480edcbfd8` — WildChat-1M

- p_block **0.7443** · tier `T2` · predicted `PROPRIETARY_CODE` · 725 chars
- evidence spans: `["exec(marshal.loads(b'c", 'requests']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 9. `wildchat:f3f1790cb820404ec3f680121bde1006` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `HEALTH_RECORD` · 2549 chars
- evidence spans: `['16.52mg/dl', '752.38mg/dl', '7μl']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 10. `cfpb:728` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 1953 chars
- evidence spans: `['LVNV Funding LLC C/O Resurgent Capital Services XXXX, SC XXXX XXXX : Dispute of Debt Collection Account ( Account No. XX', 'I do not recognize this debt and believe it may have been reported in error or is otherwise unverifiable.', 'Under the Fair Debt Collection Practices Act ( FDCPA, 15 U.S.C. 1692g ), I am entitled to debt validation. If this debt']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 11. `cfpb:6668` — CFPB

- p_block **0.9993** · tier `T2` · predicted `LEGAL_HR` · 1359 chars
- evidence spans: `['XXXX XXXX  To Whom It May Concern, I am writing to formally dispute an inaccurately reported late payment by XXXX XXXX', 'XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 12. `wildchat:082c3553c3c0a583ddb2e6e96bb64213` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `HEALTH_RECORD` · 706 chars
- evidence spans: `['Patricia Hertig has been suffering from several conditions, which were exacerbated by her recent accident']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 13. `cfpb:2092` — CFPB

- p_block **0.9998** · tier `T2` · predicted `LEGAL_HR` · 2692 chars
- evidence spans: `['Fair Credit Reporting Act ( FCRA ) : 15 U.S. Code 1681i : Credit reporting agencies are required to ensure the accuracy', '15 U.S. Code 1681b : The reporting of inaccurate late payments violates my right to privacy and ensures only accurate']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 14. `cfpb:6673` — CFPB

- p_block **0.9542** · tier `T2` · predicted `LEGAL_HR` · 1927 chars
- evidence spans: `['130.00}']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 15. `cfpb:5717` — CFPB

- p_block **0.9964** · tier `T2` · predicted `PAYMENT_CARD` · 1699 chars
- evidence spans: `['XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX', '15 USC 1666b', '15 USC 1666b ( a ) Time to make payments']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 16. `cfpb:3512` — CFPB

- p_block **0.9993** · tier `T2` · predicted `PAYMENT_CARD` · 487 chars
- evidence spans: `['XXXX XXXX XXXX Balance Owed : {$0.00} XXXX XXXX XXXX XXXXXXXX Balance Owed : {$0.00}']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 17. `cfpb:528` — CFPB

- p_block **1.0** · tier `T2` · predicted `GOV_ID` · 2653 chars
- evidence spans: `['XXXX. XXXXXXXX XXXX XXXX, last date of activity, closed date, last payment date and dispute status are not reporting', 'XXXX. XXXX, last activity date, closed date, last payment date and dispute status are not reporting correctly', 'XXXX. XXXX XXXX, last activity date, closed date, last payment date and dispute status are not reporting correctly']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 18. `cfpb:155` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 2189 chars
- evidence spans: `["Mr. Cooper ( Nationstar? ) has been messing with my money since they bought my loan in XXXX. They've moved around my", 'XXXX XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 19. `cfpb:5817` — CFPB

- p_block **0.9994** · tier `T2` · predicted `LEGAL_HR` · 1207 chars
- evidence spans: `['XXXX XXXX XXXX XXXXXXXX, XXXX XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 20. `cfpb:6589` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 3404 chars
- evidence spans: `['CFPB', 'Fair Credit Reporting Act ( FCRA )', 'Fair Debt Collections Practices Act ( FDCPA )']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 21. `cfpb:6792` — CFPB

- p_block **0.9917** · tier `T2` · predicted `LEGAL_HR` · 1402 chars
- evidence spans: `['XXXX XXXX XXXX This CFPB complaint has been filed to request pursuant to FCRA 605B ( 15 U. S. C. 1681c-2 ) that you, EQU', 'XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 22. `cfpb:1174` — CFPB

- p_block **0.7092** · tier `T2` · predicted `GOV_ID` · 1799 chars
- evidence spans: `['Consumer Social Security Number : ( XXXX )']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 23. `cfpb:6129` — CFPB

- p_block **0.9997** · tier `T2` · predicted `PAYMENT_CARD` · 954 chars
- evidence spans: `['$29000.00', '$36000.00', '$9600.00']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 24. `cfpb:3224` — CFPB

- p_block **1.0** · tier `T2` · predicted `PAYMENT_CARD` · 1460 chars
- evidence spans: `['XXXX XXXX XXXX XXXX XXXX, TX XXXX Request for Investigation and Removal of Negative Items per 15 U.S.C. 1681b']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 25. `cfpb:3714` — CFPB

- p_block **0.9802** · tier `T2` · predicted `PAYMENT_CARD` · 747 chars
- evidence spans: `['XXXX XXXX XXXX XXXX', 'XXXXXXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX', 'XXXXXXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 26. `wildchat:b34043702435fac520b51376130b27b1` — WildChat-1M

- p_block **0.9948** · tier `T2` · predicted `PROPRIETARY_CODE` · 746 chars
- evidence spans: `['c:/Users/mozit/cookies.json', 'wss://sydney.bing.com/sydney/ChatHub']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 27. `cfpb:1772` — CFPB

- p_block **0.9995** · tier `T2` · predicted `LEGAL_HR` · 1697 chars
- evidence spans: `['DELETE THIS ACCOUNTS IN MY CREDIT REPORT IMMEDIATELY!']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 28. `cfpb:4339` — CFPB

- p_block **1.0** · tier `ERR` · predicted `airlock_unavailable` · 1619 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 29. `cfpb:3935` — CFPB

- p_block **0.9413** · tier `T2` · predicted `LEGAL_HR` · 898 chars
- evidence spans: `['XXXX XXXX, XXXX, XX/XX/year>', 'CFPB complaint', 'FCRA 605B ( 15 U.S.C. 1681c-2 )']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 30. `cfpb:6210` — CFPB

- p_block **0.9992** · tier `T2` · predicted `PAYMENT_CARD` · 2820 chars
- evidence spans: `['XXXX XXXX XXXX XXXX XXXX XXXX PA XXXX XXXX XXXX Portfolio Recovery XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 31. `cfpb:418` — CFPB

- p_block **1.0** · tier `T2` · predicted `GOV_ID` · 2698 chars
- evidence spans: `['XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX, Pennsylvania XXXX Telephone : ( XXXX ) XXXX Date of Birth : XX/XX/XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 32. `wildchat:eefe96cb176fcc3fce4233b9a8018eb9` — WildChat-1M

- p_block **0.9999** · tier `T2` · predicted `PROPRIETARY_CODE` · 3727 chars
- evidence spans: `['BBG_DICT', 'LMCADS03 Curncy', 'XAU Curncy']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 33. `cfpb:7126` — CFPB

- p_block **0.948** · tier `T2` · predicted `LEGAL_HR` · 2817 chars
- evidence spans: `['NM XXXX Experian Dispute Division po box XXXX XXXX, TX XXXX FTC Case # : XXXX CFPB Complaint # : [ Insert if applicable ', 'XXXX. XXXX v. Experian Information Solutions , Inc .']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 34. `cfpb:7070` — CFPB

- p_block **0.9994** · tier `T2` · predicted `GOV_ID` · 1724 chars
- evidence spans: `['XXXX XXXX', 'XXXX', 'XXXX XXXX XXXX  on XX/XX/XXXX under the account number XXXX and a collections account opened at XXXX XXXX XXXX on XX/XX/']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 35. `cfpb:2940` — CFPB

- p_block **0.9998** · tier `T2` · predicted `GOV_ID` · 727 chars
- evidence spans: `['XXXX XXXX XXXX, XXXX XXXX XXXX  because the information on the accounts is incorrect. The original amounts are incorrect', 'XXXX XXXX ID : XXXX from XXXX ( XXXX XXXX XXXX  for student loans on behalf of XXXX XXXX or XXXX XXXX XXXX ) the company']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 36. `cfpb:5908` — CFPB

- p_block **0.9979** · tier `T2` · predicted `FINANCIAL_NONPUBLIC` · 1568 chars
- evidence spans: `['{$26000.00}', '{$5300.00}', '{$10000.00}']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 37. `cfpb:732` — CFPB

- p_block **1.0** · tier `ERR` · predicted `airlock_unavailable` · 1627 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 38. `wildchat:7722c68dbf007f85be9487938b48969c` — WildChat-1M

- p_block **0.9997** · tier `T2` · predicted `CREDENTIAL` · 903 chars
- evidence spans: `['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']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 39. `wildchat:d17d67ced7b5b3c6297943c0471f916b` — WildChat-1M

- p_block **0.9996** · tier `T2` · predicted `CREDENTIAL` · 3358 chars
- evidence spans: `['AAAAAAAAAAAAAAAAAAAAAPFamQEAAAAAPOx1y2vzxQf8Qjb8J68VCiK6M3E%3DUxjFF0WpJmBedg2mzP8PMLU4OWEZgmaok4B0eByBiSOyLdfilh']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 40. `cfpb:1415` — CFPB

- p_block **1.0** · tier `T2` · predicted `PAYMENT_CARD` · 1278 chars
- evidence spans: `['XXXXXXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXXXXXX', 'TX XXXX XXXX XXXX XXXX XXXX XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

