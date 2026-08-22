"""Tier 1 detector tests (SRS §10 Phase 1 item 4) — also a submission artifact.

Positive/negative sets mirror the classify spike: HIGH must fire on real-shaped
secrets and Luhn-valid PANs; it must NOT fire on test cards, example keys,
UUIDs, git SHAs, hex literals, IPs, timestamps, or prose.
"""

import pytest

from services.inspect.tiers import t0, t1
from services.inspect.verify import verify


# --------------------------------------------------------------------- T0
@pytest.mark.parametrize("text", [
    "what is a monad?", "explain CSS grid", "thanks!", "hello world",
])
def test_t0_trivial_allows(text):
    assert t0.is_trivial(text)


@pytest.mark.parametrize("text", [
    "my ssn is 123-45-6789",                     # digits
    "user@example.com",                          # @
    "a" * 40,                                    # length
    "key=value",                                 # =
])
def test_t0_not_trivial(text):
    assert not t0.is_trivial(text)


# ------------------------------------------------------------- PAN + Luhn
LIVE_SHAPED_PANS = [
    "4556737586899855",        # Visa, Luhn-valid, not a Stripe test card
    "5425233430109903",        # Mastercard
    "4556 7375 8689 9855",     # spaced
    "4556-7375-8689-9855",     # dashed
]


@pytest.mark.parametrize("pan", LIVE_SHAPED_PANS)
def test_pan_blocks_high(pan):
    r = t1.scan(f"card on file: {pan} exp 09/27")
    assert r.confidence == "HIGH" and r.label == "PAYMENT_CARD"


@pytest.mark.parametrize("text", [
    "use test card 4242424242424242 in sandbox",          # Stripe test PAN
    "amex test: 378282246310005",                          # Stripe test PAN
    "deadbeef4242424242424242cafe",                        # embedded in hex
    "ip 4234.1234.1234.1234 is not a card",                # dotted
    "ts=4556737586899855123 event id",                     # 19-digit run attached to word
    "invalid luhn 4556737586899856",                       # Luhn fails
])
def test_pan_negatives(text):
    r = t1.scan(text)
    assert not (r.confidence == "HIGH" and r.label == "PAYMENT_CARD")


def test_luhn():
    assert t1.luhn("4242424242424242")
    assert not t1.luhn("4242424242424241")
    assert not t1.luhn("1234")  # too short


# ----------------------------------------------------- provider prefixes
@pytest.mark.parametrize("secret", [
    "AKIAQYLPMN5HHHFPZSPQ",
    "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
    "glpat-XY7abcdEFgh12345ijkl",
    "sk_live_51Nc8xKAbCdEfGh1234567890",
    "xoxb-1234567890-1234567890123-AbCdEfGhIjKlMnOp",
    "sk-ant-api03-" + "a1B" * 31 + "AA",  # exactly 93 body chars + AA
    "AIzaSyD-1234567890abcdefghijklmnopqrstuv",
    "-----BEGIN RSA PRIVATE KEY-----",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0",
])
def test_provider_prefix_blocks_high(secret):
    r = t1.scan(f"here is the config: {secret}")
    assert r.confidence == "HIGH" and r.label == "CREDENTIAL", secret


def test_aws_example_key_is_excluded():
    r = t1.scan("docs example: AKIAIOSFODNN7EXAMPLE")
    assert r.confidence != "HIGH"


# ----------------------------------------------- entropy + hex/UUID rules
def test_git_sha_without_keyword_passes():
    r = t1.scan("commit 356a192b7913b04c54574d18c28d46e6395428ab fixed it")
    assert r.confidence is None


def test_hex40_with_keyword_escalates():
    r = t1.scan("api token = 356a192b7913b04c54574d18c28d46e6395428ab")
    assert r.confidence == "MEDIUM"


def test_uuid_whitelisted():
    r = t1.scan("request id 91fdca18-ea82-44a3-88e2-d47202c6729c failed")
    assert r.confidence is None


def test_prose_never_trips_entropy():
    r = t1.scan("The quarterly retrospective covered engineering throughput "
                "and hiring, nothing unusual to report this sprint.")
    assert r.confidence is None


# --------------------------------------------------------------- SSN / IBAN
def test_ssn_with_keyword_escalates():
    r = t1.scan("employee SSN: 536-90-4399 for the I-9 form")
    assert r.confidence == "MEDIUM" and r.label == "GOV_ID"


def test_ssn_without_keyword_passes():
    r = t1.scan("part number 536-90-4399 restocked")
    assert r.confidence is None


def test_iban_mod97():
    assert t1.scan("wire to GB82WEST12345698765432 please").hints  # valid IBAN
    r = t1.scan("code GB82WEST12345698765433 is not an account")   # bad check
    assert "iban_mod97" not in r.hints


# ------------------------------------------------------------- conn strings
def test_credentialed_connstr_escalates():
    r = t1.scan("DATABASE_URL=postgres://svc:s3cretPW@db.internal:5432/prod")
    assert r.confidence == "MEDIUM" and "credentialed_connection_string" in r.hints


def test_credentialless_url_passes():
    r = t1.scan("connect to postgres://db.example.com:5432/demo")
    assert "credentialed_connection_string" not in r.hints


# ------------------------------------------------------------ tabular PII
CUSTOMER_CSV = "\n".join(
    ["name,email,phone,plan"] +
    [f"User {i},user{i}@northwind.example,+1-415-555-01{i:02d},Pro"
     for i in range(1, 9)])


def test_tabular_customer_list_escalates():
    r = t1.scan(CUSTOMER_CSV)
    assert r.tabular_score >= 0.7 and r.confidence == "MEDIUM"


def test_csv_without_pii_passes():
    csv = "\n".join(["sku,qty,price"] +
                    [f"SKU-{i},{i * 3},{i * 10}.99" for i in range(1, 9)])
    r = t1.scan(csv)
    assert r.tabular_score == 0.0


# ------------------------------------------------------------ verify()
def test_verify_overrides_unfound_span():
    v = {"label": "CREDENTIAL", "severity": "HIGH",
         "policy_clause_id": "POL-001", "evidence_spans": ["not in payload"]}
    out = verify(v, "totally benign text")
    assert out["label"] == "BENIGN" and out["override"] == "unverified_evidence"


def test_verify_keeps_whitespace_normalised_span():
    v = {"label": "CUSTOMER_RECORD", "severity": "HIGH",
         "policy_clause_id": "POL-004",
         "evidence_spans": ["Ana  Ruiz,ana@x.example"]}
    out = verify(v, "row: ana ruiz,ana@x.example plan Pro")
    assert out["label"] == "CUSTOMER_RECORD"


def test_verify_benign_passthrough():
    v = {"label": "BENIGN", "severity": "NONE", "evidence_spans": []}
    assert verify(v, "anything")["label"] == "BENIGN"
