"""Tier 1 — deterministic detectors (SRS §6.2).

Only three detector families may block without a model (SRS §6.4):
  Luhn-valid PAN (minus published test cards) | PEM | provider-prefix secrets.
Everything else escalates to T2 with a hint. T1-HIGH FPs pass straight through
to the total, so HIGH stays checksum/prefix-gated only.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field

# ---------------------------------------------------------------- PAN + Luhn
# The (?<![\w.\-]) boundary — NOT \b — is what kills hex literals, IPs and
# timestamp-shaped 16-digit runs.
PAN_RE = re.compile(
    r'(?<![\w.\-])'
    r'(?:4\d{3}|5[1-5]\d{2}|2(?:2[2-9]\d|[3-6]\d{2}|7[01]\d|720)|3[47]\d{2}'
    r'|6(?:011|5\d{2}|4[4-9]\d|2\d{2})|3(?:0[0-5]|[68]\d)\d|35\d{2})'
    r'[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,7}(?![\w.\-])')


def luhn(s):
    d = [int(c) for c in re.sub(r'\D', '', s)]
    if not 12 <= len(d) <= 19:
        return False
    t = 0
    for i, x in enumerate(reversed(d)):
        if i % 2:
            x *= 2
            if x > 9:
                x -= 9
        t += x
    return t % 10 == 0


# Stripe's published test PANs route to BENIGN by exclusion — Purview does the
# same. Compared digits-only.
STRIPE_TEST_PANS = {
    "4242424242424242", "4000056655665556", "5555555555554444",
    "2223003122003222", "5200828282828210", "5105105105105100",
    "378282246310005", "371449635398431", "6011111111111117",
    "6011000990139424", "3056930009020004", "36227206271667",
    "3566002020360505", "6200000000000005",
}

# ------------------------------------------------- provider-prefix credentials
# Verbatim from gitleaks config/gitleaks.toml. All HIGH-confidence auto-block.
PROVIDER_PREFIX_RULES = [
    ("aws-access-key", re.compile(r'\b((?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\b')),
    ("github-pat", re.compile(r'ghp_[0-9a-zA-Z]{36}')),
    ("github-fine-grained-pat", re.compile(r'github_pat_\w{82}')),
    ("gitlab-pat", re.compile(r'glpat-[\w-]{20}')),
    ("slack-bot-token", re.compile(r'xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*')),
    ("stripe-key", re.compile(r'\b((?:sk|rk)_(?:test|live|prod)_[a-zA-Z0-9]{10,99})')),
    ("openai-key", re.compile(r'\b(sk-(?:proj|svcacct|admin)-)')),
    ("anthropic-key", re.compile(r'\b(sk-ant-api03-[a-zA-Z0-9_\-]{93}AA)')),
    ("private-key", re.compile(r'(?i)-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY')),
    ("jwt", re.compile(r'\b(ey[a-zA-Z0-9]{17,}\.ey[a-zA-Z0-9\/\_-]{17,})')),
    ("gcp-api-key", re.compile(r'\b(AIza[\w-]{35})')),
    ("azure-secret", re.compile(r'([a-zA-Z0-9_~.]{3}\dQ~[a-zA-Z0-9_~.-]{31,34})')),
]

# Documentation placeholders never block.
CREDENTIAL_EXCLUSIONS = {"AKIAIOSFODNN7EXAMPLE"}

# --------------------------------------------------------------- other detectors
SSN_RE = re.compile(r'(?<!\d)(?!000|666|9\d\d)\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}(?!\d)')
SSN_KEYWORDS = re.compile(r'(?i)\b(ssn|social security|soc\.? ?sec|taxpayer|itin)\b')
IBAN_RE = re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b')
EMAIL_RE = re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b')
PHONE_US_RE = re.compile(r'(?<!\d)(?:\+1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)')
CONNSTR_RE = re.compile(r'\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:@]+:[^\s@]+@')
AWS_ARN_RE = re.compile(r'\barn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:[^\s]+')
UUID_RE = re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b')
HEX40_RE = re.compile(r'\b[0-9a-f]{40}\b')
SECRET_KEYWORD_RE = re.compile(r'(?i)secret|token|key|password|apikey')

CAND = re.compile(r'[A-Za-z0-9+/_\-=]{20,}')


def shannon(s):
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def looks_like_secret(tok):
    # Entropy only ever applies to a candidate token, never prose
    # (English prose H=4.39 > SHA-256 hex H=3.79).
    H = shannon(tok)
    cls = sum(bool(re.search(p, tok)) for p in (r'[a-z]', r'[A-Z]', r'\d', r'[+/_\-=]'))
    return H >= 3.7 and cls >= 3 and len(tok) >= 20


def iban_mod97(s):
    rearranged = s[4:] + s[:4]
    digits = ''.join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


def tabular_pii_score(text):
    """Structural customer-list detector (SRS §6.2): consistent delimiter across
    ≥3 non-empty lines, first line ≥2 delimiters, ≤2 distinct arities, and
    (n_email + n_phone)/rows ≥ 0.6 → score min(1.0, 0.5 + 0.1*rows)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3:
        return 0.0
    for delim in (",", "\t", ";", "|"):
        if lines[0].count(delim) < 2:
            continue
        arities = [ln.count(delim) for ln in lines]
        if len(set(arities)) > 2:
            continue
        rows = len(lines)
        n_email = sum(1 for ln in lines if EMAIL_RE.search(ln))
        n_phone = sum(1 for ln in lines if PHONE_US_RE.search(ln))
        if (n_email + n_phone) / rows >= 0.6:
            return min(1.0, 0.5 + 0.1 * rows)
    return 0.0


@dataclass
class T1Result:
    confidence: str | None = None      # "HIGH" blocks with no LLM; "MEDIUM" escalates
    label: str = "BENIGN"
    detector: str = ""
    evidence_spans: list = field(default_factory=list)
    hints: list = field(default_factory=list)   # forwarded to T2 on escalation
    tabular_score: float = 0.0


def _digits(s):
    return re.sub(r'\D', '', s)


def scan(text: str) -> T1Result:
    r = T1Result()
    uuids = set(m.group(0) for m in UUID_RE.finditer(text))

    # --- HIGH: PEM / provider-prefix secrets --------------------------------
    for name, rx in PROVIDER_PREFIX_RULES:
        for m in rx.finditer(text):
            span = m.group(0)
            if span in CREDENTIAL_EXCLUSIONS or any(span in u for u in uuids):
                continue
            return T1Result(confidence="HIGH", label="CREDENTIAL", detector=name,
                            evidence_spans=[span[:120]])

    # --- HIGH: Luhn-valid PAN, minus published test cards -------------------
    for m in PAN_RE.finditer(text):
        span = m.group(0)
        if not luhn(span):
            continue
        if _digits(span) in STRIPE_TEST_PANS:
            continue
        return T1Result(confidence="HIGH", label="PAYMENT_CARD",
                        detector="pan-luhn", evidence_spans=[span])

    # --- MEDIUM: everything below escalates to T2 with a hint ---------------
    for m in SSN_RE.finditer(text):
        lo, hi = max(0, m.start() - 100), m.end() + 100
        if SSN_KEYWORDS.search(text[lo:hi]):
            r.confidence = "MEDIUM"
            r.label = "GOV_ID"
            r.detector = "ssn-keyword"
            r.evidence_spans.append(m.group(0))
            r.hints.append("ssn_with_keyword")
            break

    for m in IBAN_RE.finditer(text):
        if iban_mod97(m.group(0)):
            r.confidence = r.confidence or "MEDIUM"
            r.hints.append("iban_mod97")
            r.evidence_spans.append(m.group(0))
            break

    if CONNSTR_RE.search(text):
        m = CONNSTR_RE.search(text)
        r.confidence = "MEDIUM"
        r.label = r.label if r.label != "BENIGN" else "CREDENTIAL"
        r.detector = r.detector or "connstr"
        r.evidence_spans.append(m.group(0)[:120])
        r.hints.append("credentialed_connection_string")

    if AWS_ARN_RE.search(text):
        r.hints.append("aws_arn")

    # generic-api-key composite is MEDIUM → escalate, never auto-block
    for tok in CAND.findall(text):
        if tok in uuids or UUID_RE.fullmatch(tok):
            continue
        if HEX40_RE.fullmatch(tok):
            # bare 40-hex is a git SHA: flag only with a secret keyword nearby.
            # Hex has 2 char classes so the entropy composite can never pass it;
            # the keyword context is the whole signal.
            idx = text.find(tok)
            lo, hi = max(0, idx - 40), idx + len(tok) + 40
            if SECRET_KEYWORD_RE.search(text[lo:hi]):
                r.confidence = r.confidence or "MEDIUM"
                r.label = r.label if r.label != "BENIGN" else "CREDENTIAL"
                r.detector = r.detector or "hex40-keyword"
                r.evidence_spans.append(tok)
                r.hints.append("hex40_with_secret_keyword")
                break
            continue
        if looks_like_secret(tok):
            r.confidence = r.confidence or "MEDIUM"
            r.label = r.label if r.label != "BENIGN" else "CREDENTIAL"
            r.detector = r.detector or "entropy-composite"
            r.evidence_spans.append(tok[:120])
            r.hints.append("high_entropy_token")
            break

    r.tabular_score = tabular_pii_score(text)
    if r.tabular_score >= 0.7:
        r.confidence = r.confidence or "MEDIUM"
        r.label = r.label if r.label != "BENIGN" else "CUSTOMER_RECORD"
        r.detector = r.detector or "tabular-pii"
        r.hints.append(f"tabular_pii_score={r.tabular_score:.2f}")

    return r
