"""Span verification (SRS §6.4) — runs on every non-BENIGN T2/T3 verdict.

A verdict whose evidence cannot be found in the payload is overridden to
BENIGN. Every override increments a counter exposed on /healthz; the override
rate is a reported number.
"""

override_count = 0


def verify(v, payload):
    global override_count
    if v["label"] == "BENIGN":
        return v
    spans = [s for s in v.get("evidence_spans", []) if s and s in payload]
    if not spans:
        norm = " ".join(payload.split()).casefold()
        spans = [s for s in v.get("evidence_spans", [])
                 if " ".join(s.split()).casefold() in norm]
    if not spans:
        override_count += 1
        return {**v, "label": "BENIGN", "severity": "NONE",
                "policy_clause_id": "NONE", "override": "unverified_evidence"}
    return {**v, "evidence_spans": spans}
