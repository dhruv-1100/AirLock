# False positives — every one, for hand-adjudication

Threshold 0.55. 69 of 1000 benign items blocked.

Adjudicate each row and record the verdict in the `Adjudication` column. Report
the corrected count in the submission, e.g. *"7 blocked; on review 3 contained a
genuine live-looking key the corpus author had pasted; corrected FP = 4/1000"*.
This turns the corpus's weakness into a demonstration of rigour.

## 1. `wildchat:e5a3efada0c3ce18c60a2295738b8571` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `HEALTH_RECORD` · 491 chars
- evidence spans: `['Patricia Bertier is a young active woman who has been suffering from several conditions, including mild bilateral hip', 'bilateral hip dislocation and narrowing of the birth canal']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 2. `wildchat:20b4eb5cb22ecce019a62dae6e02f150` — WildChat-1M

- p_block **0.7314** · tier `T2` · predicted `BENIGN` · 351 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 3. `wildchat:4b93f2ee31db290820c5408d061f796f` — WildChat-1M

- p_block **0.9982** · tier `T2` · predicted `PROPRIETARY_CODE` · 3129 chars
- evidence spans: `['access_token =', 'account_id =', 'insights.metric(impressions,engagement)']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 4. `cfpb:6150` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 1270 chars
- evidence spans: `['15 USC 1681', '15 U.S.C 1681 section 602 A', '15 U.S.C 1681 section 604 A Section 2 : It also states a consumer reporting agency can not furnish a account without my']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 5. `cfpb:6427` — CFPB

- p_block **0.9997** · tier `T2` · predicted `LEGAL_HR` · 815 chars
- evidence spans: `['My consumer report contains data that was obtained through identity theft']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 6. `wildchat:2d523ca32a96b1d02e64e26ccb46b0bf` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `HEALTH_RECORD` · 460 chars
- evidence spans: `['Alice Flamand is a young active woman who sustained multiple severe injuries in a car accident, including traumatic ampu', 'traumatic amputation of both legs above the knee. However, her legs were successfully reattached during treatment.']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 7. `cfpb:4066` — CFPB

- p_block **0.9866** · tier `T2` · predicted `FINANCIAL_NONPUBLIC` · 329 chars
- evidence spans: `['{$15000.00}']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 8. `wildchat:fb8b1efef359a99949b2e99ef86237c9` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `HEALTH_RECORD` · 476 chars
- evidence spans: `['Patricia Bertier is a young active woman who has been involved in a serious car accident, suffering multiple severe inj']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 9. `cfpb:359` — CFPB

- p_block **1.0** · tier `T2` · predicted `BENIGN` · 560 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 10. `cfpb:839` — CFPB

- p_block **0.9997** · tier `T2` · predicted `LEGAL_HR` · 1821 chars
- evidence spans: `['XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX', '15 U.S.C 1681 section 602A. States I have the right to privacy.']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 11. `wildchat:8080c7b9308009818f5ddb803ccf148f` — WildChat-1M

- p_block **0.8936** · tier `T2` · predicted `BENIGN` · 456 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 12. `wildchat:a07842b1a28cca9853c88c480edcbfd8` — WildChat-1M

- p_block **0.9136** · tier `T2` · predicted `BENIGN` · 725 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 13. `cfpb:4428` — CFPB

- p_block **0.6901** · tier `T2` · predicted `LEGAL_HR` · 680 chars
- evidence spans: `['15 U.S.C. 1681n']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 14. `wildchat:f3f1790cb820404ec3f680121bde1006` — WildChat-1M

- p_block **1.0** · tier `ERR` · predicted `airlock_unavailable` · 2549 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 15. `cfpb:728` — CFPB

- p_block **0.9999** · tier `T2` · predicted `FINANCIAL_NONPUBLIC` · 1953 chars
- evidence spans: `['Account No. XXXX', 'XXXX XXXXXXXX XXXX XXXXXXXX', '{$630.00}']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 16. `cfpb:6668` — CFPB

- p_block **0.9999** · tier `T2` · predicted `FINANCIAL_NONPUBLIC` · 1359 chars
- evidence spans: `['XXXX XXXX  To Whom It May Concern, I am writing to formally dispute an inaccurately reported late payment by XXXX XXXX', 'XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 17. `wildchat:83529ffadfe2af24993fbcc8f12c4f6c` — WildChat-1M

- p_block **0.9859** · tier `T2` · predicted `BENIGN` · 1427 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 18. `wildchat:082c3553c3c0a583ddb2e6e96bb64213` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `HEALTH_RECORD` · 706 chars
- evidence spans: `['Patricia Hertig has been suffering from several conditions, which were exacerbated by her recent accident']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 19. `cfpb:6673` — CFPB

- p_block **0.9369** · tier `T2` · predicted `LEGAL_HR` · 1927 chars
- evidence spans: `['Aldous and Associates', '$130.00']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 20. `cfpb:2092` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 2692 chars
- evidence spans: `['Fair Credit Reporting Act ( FCRA ) : 15 U.S. Code 1681i : Credit reporting agencies are required to ensure the accuracy', '15 U.S. Code 1681b : The reporting of inaccurate late payments violates my right to privacy and ensures only accurate', 'Truth in Lending Act ( TILA ) : 15 U.S. Code 1666b : Creditors must send periodic statements at least 21 days before the']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 21. `cfpb:5717` — CFPB

- p_block **0.9986** · tier `T2` · predicted `PAYMENT_CARD` · 1699 chars
- evidence spans: `['XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX', '15 USC 1666b', '15 USC 1666b ( a ) Time to make payments']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 22. `wildchat:59cab2ce7ac675e1ddf21eebfcefc0da` — WildChat-1M

- p_block **0.9991** · tier `T2` · predicted `BENIGN` · 2888 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 23. `cfpb:3512` — CFPB

- p_block **0.9999** · tier `T2` · predicted `PAYMENT_CARD` · 487 chars
- evidence spans: `['XXXX XXXX XXXX Balance Owed : {$0.00} XXXX XXXX XXXX XXXXXXXX Balance Owed : {$0.00}']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 24. `cfpb:528` — CFPB

- p_block **0.9868** · tier `T2` · predicted `GOV_ID` · 2653 chars
- evidence spans: `['XXXX. XXXXXXXX XXXX XXXX, last date of activity, closed date, last payment date and dispute status are not reporting', 'XXXX. XXXX, last activity date, closed date and dispute status are not reporting correctly', 'XXXX. XXXX XXXX, last activity date, closed date, last payment date and dispute status are not reporting correctly']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 25. `cfpb:155` — CFPB

- p_block **0.9999** · tier `T2` · predicted `LEGAL_HR` · 2189 chars
- evidence spans: `['Mr. Cooper ( Nationstar? ) has been messing with my money since they bought my loan in XXXX', 'XXXX XXXX XXXX', 'XXXX dollars ( My down payment )']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 26. `wildchat:d51c5ede98fee5ac2d15bb43625cb72f` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `BENIGN` · 1497 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 27. `cfpb:3556` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 1334 chars
- evidence spans: `['15 U.S.C. 1681e ( b ) : Procedures to ensure accuracy were not followed.', '15 U.S.C. 1681i ( a ) ( 1 ) ( A ) : The disputes were not properly reinvestigated.', '15 U.S.C. 1681i ( a ) ( 4 ) : Relevant information was not reviewed during reinvestigation.']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 28. `wildchat:f90779e2f5e81b513138558537002b8b` — WildChat-1M

- p_block **0.9981** · tier `T2` · predicted `BENIGN` · 2209 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 29. `cfpb:2855` — CFPB

- p_block **1.0** · tier `T2` · predicted `BENIGN` · 3318 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 30. `wildchat:41422ba8a5d52d7ace05ed11ce5144d8` — WildChat-1M

- p_block **1.0** · tier `ERR` · predicted `airlock_unavailable` · 282 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 31. `cfpb:3542` — CFPB

- p_block **0.9928** · tier `T2` · predicted `PAYMENT_CARD` · 784 chars
- evidence spans: `['XXXX XXXX XXXX', 'Last for digits of ss # is XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 32. `wildchat:d4a129a5df04e9a85e7e96e59c19276c` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `HEALTH_RECORD` · 436 chars
- evidence spans: `['drooling, muscle spasms and incontinence']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 33. `cfpb:248` — CFPB

- p_block **0.998** · tier `T2` · predicted `LEGAL_HR` · 1373 chars
- evidence spans: `['26 U.S. Code 1099-C', 'IRS Form 1099-C', '{$600.00}']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 34. `cfpb:6589` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 3404 chars
- evidence spans: `['CFPB', 'Fair Credit Reporting Act ( FCRA )', 'Fair Debt Collections Practices Act ( FDCPA )']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 35. `cfpb:5817` — CFPB

- p_block **0.9998** · tier `T2` · predicted `GOV_ID` · 1207 chars
- evidence spans: `['1099c to support the charge off and it has not been sent', 'Fair Credit Reporting Act ( FCRA ) and Code 15 U.S.C. 1681e ( b )']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 36. `cfpb:2151` — CFPB

- p_block **1.0** · tier `T2` · predicted `FINANCIAL_NONPUBLIC` · 3502 chars
- evidence spans: `['XXXX Police Identity Theft Report, FTC ID Theft Report']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 37. `cfpb:6792` — CFPB

- p_block **0.9796** · tier `T2` · predicted `LEGAL_HR` · 1402 chars
- evidence spans: `['XXXX XXXX XXXX This CFPB complaint has been filed to request pursuant to FCRA 605B ( 15 U. S. C. 1681c-2 ) that you, EQU', 'XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX', 'XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXXXXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 38. `cfpb:1174` — CFPB

- p_block **0.9998** · tier `T2` · predicted `GOV_ID` · 1799 chars
- evidence spans: `['Consumer Social Security Number : ( XXXX )', 'Consumer Date of Birth : ( XX/XX/XXXX )', 'Consumer Name : XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 39. `cfpb:6129` — CFPB

- p_block **0.9992** · tier `T2` · predicted `PAYMENT_CARD` · 954 chars
- evidence spans: `['$29000.00', '$36000.00', '$9600.00']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 40. `wildchat:e850a3673c27423f2c07c226fc8423bf` — WildChat-1M

- p_block **0.9932** · tier `T2` · predicted `PROPRIETARY_CODE` · 682 chars
- evidence spans: `['nazi schoolgirl']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 41. `cfpb:3224` — CFPB

- p_block **1.0** · tier `T2` · predicted `PAYMENT_CARD` · 1460 chars
- evidence spans: `['XXXX XXXX XXXX XXXX XXXX', 'TX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 42. `cfpb:3714` — CFPB

- p_block **0.9709** · tier `T2` · predicted `PAYMENT_CARD` · 747 chars
- evidence spans: `['XXXX XXXX XXXX XXXX', 'XXXXXXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX', 'XXXX/XX/year>']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 43. `wildchat:b34043702435fac520b51376130b27b1` — WildChat-1M

- p_block **0.9675** · tier `T2` · predicted `PROPRIETARY_CODE` · 746 chars
- evidence spans: `['c:/Users/mozit/cookies.json', 'wss://sydney.bing.com/sydney/ChatHub']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 44. `cfpb:1772` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 1697 chars
- evidence spans: `['15 U.S. Code 1681i ( 6 )', '15 U.S. Code 1681n ( Civil Liability for Willful Noncompliance )', '15 U.S. Code 1681o ( Civil Liability for Negligent Noncompliance )']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 45. `cfpb:4339` — CFPB

- p_block **0.9981** · tier `T2` · predicted `GOV_ID` · 1619 chars
- evidence spans: `['EQUIFAX XXXX XXXX', '15 USC 1666b', '15 USC 1666b ( a )']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 46. `cfpb:3935` — CFPB

- p_block **0.998** · tier `T2` · predicted `GOV_ID` · 898 chars
- evidence spans: `['XXXX XXXX, XXXX, XX/XX/year>', 'CFPB complaint', 'FCRA 605B']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 47. `wildchat:ab966e886a801f4c45603586704ecaea` — WildChat-1M

- p_block **0.9609** · tier `T2` · predicted `BENIGN` · 663 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 48. `cfpb:6210` — CFPB

- p_block **0.9867** · tier `T2` · predicted `LEGAL_HR` · 2820 chars
- evidence spans: `['Cease and Desist Request for Deletion of Collection Account Dear COLLECTION COMPANY, I am writing to formally request', 'I seek comprehensive validation of the alleged debt, including evidence establishing that I am the party obligated to']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 49. `wildchat:4bf54b9d4f14cbbf8d2dbace13d2e4d8` — WildChat-1M

- p_block **0.9941** · tier `T2` · predicted `LEGAL_HR` · 981 chars
- evidence spans: `['Company Act 2063']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 50. `cfpb:4851` — CFPB

- p_block **0.9989** · tier `T2` · predicted `LEGAL_HR` · 349 chars
- evidence spans: `['XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 51. `wildchat:72addbf5f4febc6b68d7156a0d17b8b2` — WildChat-1M

- p_block **0.9526** · tier `T2` · predicted `BENIGN` · 3830 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 52. `cfpb:418` — CFPB

- p_block **1.0** · tier `T2` · predicted `GOV_ID` · 2698 chars
- evidence spans: `['XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX, Pennsylvania XXXX Telephone : ( XXXX ) XXXX Date of Birth : XX/XX/XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 53. `wildchat:7a05aa4eed5efc56af1f459205a7c05e` — WildChat-1M

- p_block **1.0** · tier `T2` · predicted `PROPRIETARY_CODE` · 2338 chars
- evidence spans: `['namespace TextFileProcessor', 'using System;', 'using System.Collections.Generic;']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 54. `wildchat:eefe96cb176fcc3fce4233b9a8018eb9` — WildChat-1M

- p_block **0.852** · tier `T2` · predicted `BENIGN` · 3727 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 55. `cfpb:5079` — CFPB

- p_block **0.8963** · tier `T2` · predicted `PAYMENT_CARD` · 1860 chars
- evidence spans: `['XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 56. `cfpb:7126` — CFPB

- p_block **0.9886** · tier `T2` · predicted `GOV_ID` · 2817 chars
- evidence spans: `['NM XXXX Experian Dispute Division po box XXXX XXXX, TX XXXX FTC Case # : XXXX CFPB Complaint # : [ Insert if applicable ', 'XXXX XXXX Enclosures : Notarized Affidavit of Identity Theft FTC Complaint Documentation Copy of ID']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 57. `cfpb:7070` — CFPB

- p_block **0.9999** · tier `T2` · predicted `GOV_ID` · 1724 chars
- evidence spans: `['Consumer Social Security Number : XXXX', 'Consumer Date of Birth : XX/XX/XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 58. `cfpb:4114` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 651 chars
- evidence spans: `['any foreclosure proceedings will continue as scheduled under the heading ']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 59. `cfpb:2995` — CFPB

- p_block **0.917** · tier `T2` · predicted `LEGAL_HR` · 1476 chars
- evidence spans: `['XXXX XXXX XXXX', 'FCRA 605B', '15 U.S.C. 1681c-2']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 60. `wildchat:cfde1388929d00987e5b790cc0c687c9` — WildChat-1M

- p_block **0.9968** · tier `T2` · predicted `BENIGN` · 1998 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 61. `cfpb:2940` — CFPB

- p_block **0.9999** · tier `T2` · predicted `GOV_ID` · 727 chars
- evidence spans: `['XXXX XXXX XXXX, XXXX XXXX XXXX  because the information on the accounts is incorrect. The original amounts are incorrect', 'XXXX from XXXX ( XXXX XXXX XXXX  for student loans on behalf of XXXX XXXX or XXXX XXXX XXXX ) the company is no longer']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 62. `cfpb:5908` — CFPB

- p_block **0.9997** · tier `T2` · predicted `FINANCIAL_NONPUBLIC` · 1568 chars
- evidence spans: `['{$26000.00}', '{$5300.00}', '{$10000.00}']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 63. `cfpb:4212` — CFPB

- p_block **1.0** · tier `T2` · predicted `LEGAL_HR` · 981 chars
- evidence spans: `['EXCLUSION section of the FCRAs definitions', 'account SHALL be deleted', 'permissible purpose section of the FCRA']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 64. `wildchat:7722c68dbf007f85be9487938b48969c` — WildChat-1M

- p_block **0.9998** · tier `T2` · predicted `CREDENTIAL` · 903 chars
- evidence spans: `['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']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 65. `wildchat:d17d67ced7b5b3c6297943c0471f916b` — WildChat-1M

- p_block **0.9999** · tier `T2` · predicted `CREDENTIAL` · 3358 chars
- evidence spans: `['AAAAAAAAAAAAAAAAAAAAAPFamQEAAAAAPOx1y2vzxQf8Qjb8J68VCiK6M3E%3DUxjFF0WpJmBedg2mzP8PMLU4OWEZgmaok4B0eByBiSOyLdfilh']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 66. `cfpb:1415` — CFPB

- p_block **0.9996** · tier `T2` · predicted `GOV_ID` · 1278 chars
- evidence spans: `['XXXXXXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXX XXXXXXXX', 'TX XXXX XXXX XXXX XXXX XXXX XXXX XXXX']`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 67. `wildchat:522b559399816aa9ffce9db579dd47ab` — WildChat-1M

- p_block **0.9999** · tier `T2` · predicted `BENIGN` · 1430 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 68. `wildchat:17b99b14bd2f0c6675a841fc08b77caf` — WildChat-1M

- p_block **0.9933** · tier `T2` · predicted `BENIGN` · 3137 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

## 69. `wildchat:9df5c7d054acec3d29ac9a9e61a707fc` — WildChat-1M

- p_block **0.9999** · tier `T2` · predicted `BENIGN` · 2718 chars
- evidence spans: `[]`
- **Adjudication:** _(genuine FP / corpus contamination / borderline)_

