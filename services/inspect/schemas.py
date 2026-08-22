"""airlock.inspect.v1 / airlock.verdict.v1 contract shapes (SRS §5.1, §5.4).

The classifier JSON schema property order is load-bearing: xgrammar emits in
schema order, so evidence precedes label and the label is conditioned on it.
"""

LABELS = [
    "BENIGN", "CREDENTIAL", "PAYMENT_CARD", "GOV_ID", "CUSTOMER_RECORD",
    "HEALTH_RECORD", "FINANCIAL_NONPUBLIC", "PROPRIETARY_CODE", "LEGAL_HR",
]

CLAUSE_IDS = ["NONE", "POL-001", "POL-002", "POL-003", "POL-004",
              "POL-005", "POL-006", "POL-007", "POL-008", "POL-009"]

LABEL_TO_CLAUSE = {
    "CREDENTIAL": "POL-001",
    "PAYMENT_CARD": "POL-002",
    "GOV_ID": "POL-003",
    "CUSTOMER_RECORD": "POL-004",
    "HEALTH_RECORD": "POL-005",
    "FINANCIAL_NONPUBLIC": "POL-006",
    "PROPRIETARY_CODE": "POL-007",
    "LEGAL_HR": "POL-008",
    "BENIGN": "NONE",
}

# SRS §5.4 — sent to vLLM as guided/structured output. Do not reorder keys.
CLASSIFIER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["evidence_spans", "rationale", "label", "severity",
                 "policy_clause_id", "confidence"],
    "properties": {
        "evidence_spans": {"type": "array", "maxItems": 3,
                           "items": {"type": "string", "maxLength": 120}},
        "rationale": {"type": "string", "maxLength": 160},
        "label": {"type": "string", "enum": LABELS},
        "severity": {"type": "string", "enum": ["NONE", "LOW", "MEDIUM", "HIGH"]},
        "policy_clause_id": {"type": "string", "enum": CLAUSE_IDS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

# Operating points (SRS §6.5). Audit logs but never blocks.
MODES = {"audit": 0.30, "balanced": 0.55, "strict": 0.20}
DEFAULT_MODE = "balanced"


def verdict_body(*, request_id, action, label, severity, clause_id, clause_text,
                 reason, evidence_spans, evidence_verified, p_block, threshold,
                 tier, model, modality, latency_ms, decision_id=None,
                 score_details=None):
    """Full airlock.verdict.v1 response body (SRS §5.1)."""
    return {
        "schema": "airlock.verdict.v1",
        "request_id": request_id,
        "action": action,
        "label": label,
        "severity": severity,
        "policy_clause_id": clause_id,
        "policy_clause_text": clause_text,
        "reason": reason,
        "evidence_spans": evidence_spans,
        "evidence_verified": evidence_verified,
        "score": p_block,
        "p_block": p_block,
        "threshold": threshold,
        "tier": tier,
        "model": model,
        "modality": modality,
        "latency_ms": latency_ms,
        "bytes_egressed": 0,
        "decision_id": decision_id,
        "score_details": score_details,
    }


def error_body(code, label, reason, request_id):
    """Fail-closed error shape — byte-compatible with OpenShell policy_denied."""
    return {"schema": "airlock.error.v1", "error": "policy_denied", "code": code,
            "label": label, "action": "block", "reason": reason,
            "request_id": request_id}
