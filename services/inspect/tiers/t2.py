"""Tier 2 — text LLM classifier (SRS §6.3).

System prompt is a byte-identical module constant so vLLM prefix caching serves
the prefill. Guided-JSON spelling varies by vLLM build — VERIFY-ON-THE-DAY at
the 10:45 gate; the three spellings are tried in order and the winner is cached
for the process lifetime (record it in NOTES.md).
"""

import json
import os

import httpx

from ..schemas import CLASSIFIER_SCHEMA

# Defaults ARE the committed two-server config: T2 runs on the text server at
# :8000. Previously this defaulted to :8002 — the server we deliberately do not
# launch — so forgetting to source stack/models.env sent every escalation to a
# dead port, timing out and fail-closing to BLOCK: an FPR near 1.0 that reads
# exactly like a broken detector (RUN-DAY.md §2 called this the
# highest-consequence check of the day). Defaulting to the config we actually
# run removes the failure mode instead of documenting it.
# Launching airlock-clf is the three-server case: set both vars explicitly.
CLF_BASE_URL = os.environ.get("AIRLOCK_CLF_URL", "http://127.0.0.1:8000/v1")
# Request model NAME (--served-model-name), never a weights path.
CLF_MODEL = os.environ.get("AIRLOCK_CLF_MODEL", "airlock-text")
T2_TIMEOUT_S = 1.2  # server internal budget for the T2 call (SRS §5.1)

SYSTEM_PROMPT = """You are AIRLOCK, a local data-egress inspector. You classify a payload that an
employee is about to paste into an external AI service.

You have exactly one job: decide whether this payload contains information that
this company has not already made public.

DEFAULT TO "BENIGN". Blocking a benign paste costs an employee real time and
erodes trust in the control. Only depart from BENIGN when you can quote the
exact characters in the payload that make it sensitive.

BENIGN includes, and you must not block:
  - Questions about programming, tools, maths, writing, or general knowledge,
    even long ones, even ones containing code.
  - Open-source, tutorial, textbook, or documentation code and config.
  - Placeholder, dummy, example, redacted, or test data: "user@example.com",
    "555-0100", "AKIAIOSFODNN7EXAMPLE", "4242424242424242", "XXXX", "<redacted>",
    "your-api-key-here", "changeme", "hunter2", faker-generated names.
  - Information the payload itself shows is already public.
  - A QUESTION ABOUT sensitive data that does not itself contain any.
    "How do I write a regex for a credit card number?" is BENIGN.
  - Public financial data: reported historical earnings, stock prices, filings.

Classify as sensitive ONLY for:
  CREDENTIAL           live secrets: API keys, tokens, private keys, passwords,
                       connection strings with real credentials
  PAYMENT_CARD         real payment card numbers
  GOV_ID               SSN, passport, driver's licence, national ID
  CUSTOMER_RECORD      3+ records identifying real customers or employees
  HEALTH_RECORD        patient-identifiable clinical information
  FINANCIAL_NONPUBLIC  UNRELEASED financials: forecasts, projections, pipeline,
                       ARR/MRR, pre-announcement results, cap tables, compensation
  PROPRIETARY_CODE     internal source or infrastructure config, identifiable by
                       internal hostnames, internal service names, or an explicit
                       internal/confidential marking
  LEGAL_HR             contracts under NDA, litigation, disciplinary or HR matters

Rules:
1. Every non-BENIGN verdict MUST include at least one evidence_span copied
   character-for-character from the payload. If you cannot copy such a span,
   the answer is BENIGN.
2. confidence is the probability that a trained security reviewer would agree
   with your label. Use the full range. If you are unsure, say 0.5, not 0.9.
3. Output only the JSON object."""


def _wrap(payload):
    return f"<<<PAYLOAD\n{payload}\nPAYLOAD>>>"


def _ex(evidence, rationale, label, severity, clause, confidence):
    # Property order mirrors CLASSIFIER_SCHEMA — evidence precedes label.
    return json.dumps({"evidence_spans": evidence, "rationale": rationale,
                       "label": label, "severity": severity,
                       "policy_clause_id": clause, "confidence": confidence})


# Six few-shot exemplars, four hard negatives (SRS §6.3).
FEW_SHOTS = [
    (_wrap("From the AWS docs: configure the CLI with access key "
           "AKIAIOSFODNN7EXAMPLE and secret wJalrXUtnFEMI/K7MDENG/bPxRfiCY"
           "EXAMPLEKEY, then run aws s3 ls."),
     _ex([], "Documented AWS example credentials, explicitly placeholder.",
         "BENIGN", "NONE", "NONE", 0.97)),
    (_wrap("My Stripe charge keeps failing in test mode. I'm sending card "
           "4242 4242 4242 4242 exp 12/34 cvc 123 like the docs say. Why do "
           "I get card_declined?"),
     _ex([], "Stripe published test card in a debugging question.",
         "BENIGN", "NONE", "NONE", 0.96)),
    (_wrap("import pandas as pd\ndf = pd.read_csv('customers.csv')\n"
           "print(df.groupby('plan').mrr.sum())  # why is this NaN?"),
     _ex([], "Code that references a customer file but contains no rows.",
         "BENIGN", "NONE", "NONE", 0.95)),
    (_wrap("Acme reported Q2 revenue of $1.2B, up 14% YoY (from the 10-Q "
           "filed 2025-08-04). Summarize the drivers."),
     _ex([], "Reported historical earnings from a public filing.",
         "BENIGN", "NONE", "NONE", 0.95)),
    (_wrap(".env\nDATABASE_URL=postgres://svc:pw@db.internal:5432/prod\n"
           "ANTHROPIC_API_KEY=sk-ant-api03-Yx7Jq2Rm9tKfLpWv3Bn8cZs1Dh4Ge6Ua"
           "0QoXiE5rNw2MbVdT7yHkC9fSj8AzP1lOu4mI6xWq3eKnR5tYgAA"),
     _ex(["sk-ant-api03-Yx7Jq2Rm9tKfLpWv3Bn8cZs1Dh4Ge6Ua0QoXiE5rNw2MbVdT7yHkC9fSj8AzP1lOu4mI6xWq3eKnR5tYgAA"],
         "Live-shaped Anthropic API key and credentialed DSN in an env file.",
         "CREDENTIAL", "HIGH", "POL-001", 0.97)),
    (_wrap("name,email,phone,plan,mrr\n"
           "Ana Ruiz,ana.ruiz@northwind.example,+1-415-555-0142,Pro,4200\n"
           "Ben Okafor,b.okafor@northwind.example,+1-206-555-0187,Team,980\n"
           "Chloe Park,c.park@northwind.example,+1-646-555-0110,Pro,4100\n"
           "Dev Batra,d.batra@northwind.example,+1-408-555-0139,Starter,120\n"
           "Eva Silva,e.silva@northwind.example,+1-503-555-0171,Team,990\n"
           "Finn Moore,f.moore@northwind.example,+1-212-555-0155,Pro,4300\n"
           "Gia Tran,g.tran@northwind.example,+1-617-555-0122,Starter,110\n"
           "Hugo Klein,h.klein@northwind.example,+1-312-555-0166,Team,970\n"
           "Iris Chen,i.chen@northwind.example,+1-650-555-0133,Pro,4150\n"
           "Jon Ames,j.ames@northwind.example,+1-720-555-0148,Starter,130\n"
           "Kai Ito,k.ito@northwind.example,+1-206-555-0193,Team,960\n"
           "Lena Voss,l.voss@northwind.example,+1-415-555-0177,Pro,4250"),
     _ex(["ana.ruiz@northwind.example,+1-415-555-0142,Pro,4200"],
         "12 rows of name,email,phone,plan,mrr identifying customers.",
         "CUSTOMER_RECORD", "HIGH", "POL-004", 0.95)),
]

# Guided-decoding spellings, tried in order (SRS §5.4). Index of the one that
# worked is cached after the first successful call.
_GUIDED_SPELLINGS = [
    {"response_format": {"type": "json_schema",
                         "json_schema": {"name": "airlock_verdict",
                                         "schema": CLASSIFIER_SCHEMA}}},
    {"extra_body": {"structured_outputs": {"json": CLASSIFIER_SCHEMA}}},
    {"extra_body": {"guided_json": CLASSIFIER_SCHEMA}},
]
_working_spelling = None


def _messages(payload, hints=None):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for user, assistant in FEW_SHOTS:
        msgs.append({"role": "user", "content": user})
        msgs.append({"role": "assistant", "content": assistant})
    user = _wrap(payload)
    if hints:
        user += "\n\nDeterministic pre-scan hints: " + ", ".join(hints)
    msgs.append({"role": "user", "content": user})
    return msgs


async def classify(payload: str, hints=None, client: httpx.AsyncClient = None):
    """Call the classifier. Returns (verdict_dict, choice_logprobs, model_name).

    Raises httpx errors / ValueError upward: the router converts any failure
    into the fail-closed 503/504 shape. Never fails open.
    """
    global _working_spelling
    base = {
        "model": CLF_MODEL,
        "messages": _messages(payload, hints),
        "temperature": 0.0,
        "seed": 1337,
        "max_tokens": 200,
        "logprobs": True,
        "top_logprobs": 20,
    }
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=T2_TIMEOUT_S)
    try:
        spellings = ([_working_spelling] if _working_spelling is not None
                     else range(len(_GUIDED_SPELLINGS)))
        last_err = None
        for i in spellings:
            body = {**base}
            for k, v in _GUIDED_SPELLINGS[i].items():
                if k == "extra_body":
                    body.update(v)
                else:
                    body[k] = v
            try:
                resp = await client.post(f"{CLF_BASE_URL}/chat/completions",
                                         json=body, timeout=T2_TIMEOUT_S)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                last_err = e
                if e.response.status_code in (400, 422):
                    continue  # spelling rejected — try the next one
                raise
            data = resp.json()
            choice = data["choices"][0]
            verdict = json.loads(choice["message"]["content"])
            _working_spelling = i
            logprobs = (choice.get("logprobs") or {}).get("content") or []
            return verdict, logprobs, data.get("model", CLF_MODEL)
        raise last_err or RuntimeError("no guided-JSON spelling accepted")
    finally:
        if own:
            await client.aclose()
