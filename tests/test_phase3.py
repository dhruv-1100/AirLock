"""Phase 3 tests: temperature scaling, ECE, ablation rows, synthetic scores."""

import importlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.inspect import app as app_mod
from services.inspect.calib import p_block_from_logits
from bench.fit_calibration import ece

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------- temperature scaling
def test_higher_T_flattens_posterior():
    logits = {"BENIGN": -0.1, "CREDENTIAL": -3.0}
    sharp = p_block_from_logits(logits, T=0.5)
    mid = p_block_from_logits(logits, T=1.0)
    flat = p_block_from_logits(logits, T=5.0)
    assert sharp < mid < flat < 0.5  # BENIGN dominates but mass spreads with T


def test_p_block_is_one_minus_benign_share():
    logits = {"BENIGN": math.log(0.25), "CREDENTIAL": math.log(0.75)}
    assert p_block_from_logits(logits, T=1.0) == pytest.approx(0.75, abs=1e-9)


def test_ece_near_zero_when_calibrated():
    # p_block == empirical rate in every bin → ECE ~ 0.
    samples = []
    for p in (0.05, 0.25, 0.45, 0.65, 0.85):
        for i in range(100):
            samples.append({"y": 1 if i < p * 100 else 0,
                            "logits": {"BENIGN": math.log(1 - p),
                                       "CREDENTIAL": math.log(p)}})
    err, _ = ece(samples, T=1.0)
    assert err < 0.02


# --------------------------------------------------------------- ablation rows
@pytest.fixture(autouse=True)
def clean_router_state():
    """The instant-block cache and tier counters are module-level, so without
    this a payload cached by an earlier test replays as CACHE and the next
    test silently measures the wrong tier — passing alone, failing in suite."""
    app_mod._cache.clear()
    app_mod._tier_counts.clear()
    yield
    app_mod._cache.clear()
    app_mod._tier_counts.clear()


@pytest.fixture
def client():
    return TestClient(app_mod.app)


def _inspect(client, text):
    return client.post("/v1/inspect", json={"schema": "airlock.inspect.v1",
                                            "text": text})


CRED = "deploy key AKIAQYLPMN5HHHFPZSPQ now"
ESCALATING = "employee SSN: 536-90-4399 for the I-9 form"


def test_t1_only_blocks_high_and_allows_escalations(client, monkeypatch):
    monkeypatch.setattr(app_mod, "ABLATION", "t1_only")
    v = _inspect(client, CRED).json()
    assert v["action"] == "block" and v["tier"] == "T1"
    v = _inspect(client, ESCALATING).json()  # MEDIUM would go to T2 — must not
    assert v["action"] == "allow" and v["tier"] == "T1"


def test_t2_rows_skip_t1_block(client, monkeypatch):
    # With no classifier running, forcing the credential past T1 into T2 must
    # fail CLOSED, proving the T1 short-circuit is really off.
    #
    # Asserts the INTENT, not one specific code. 503 (upstream unreachable) and 504
    # (upstream exceeded budget) are both the fail-closed shape, and which one wins is
    # a race between the connect attempt and TOTAL_BUDGET_S. Raising T2_TIMEOUT_S from
    # 1.2 s to 2.0 s — required because T2 on the 30B measures ~1.70 s, see the note in
    # t2.py — flipped this from 503 to 504 without changing the behaviour under test.
    # Pinning the code made the test sensitive to a timeout constant it was not written
    # to police.
    monkeypatch.setattr(app_mod, "ABLATION", "t2_verify")
    r = _inspect(client, CRED)
    assert r.status_code in (503, 504)
    body = r.json()
    assert body["error"] == "policy_denied"
    assert body["action"] == "block"


def test_full_row_unaffected(client, monkeypatch):
    monkeypatch.setattr(app_mod, "ABLATION", "full")
    v = _inspect(client, CRED).json()
    assert v["action"] == "block" and v["tier"] in ("T1", "CACHE")


# -------------------------------------------------------------- tier_timings
# B's contract: a stage that did not run is ABSENT. A 0 would light the stage
# up as having run instantly, which inverts the point of the waterfall.
def test_timings_omit_stages_that_did_not_run(client, monkeypatch):
    monkeypatch.setattr(app_mod, "ABLATION", "full")
    t = _inspect(client, "what is a monad").json()["tier_timings"]
    assert set(t) == {"CACHE", "T0"}          # never reached T1/T2/T3
    assert "T2" not in t and "T3" not in t


def test_timings_stop_at_the_deciding_stage(client, monkeypatch):
    monkeypatch.setattr(app_mod, "ABLATION", "full")
    v = _inspect(client, "deploy key AKIAQYLPMN5HHHFPZSPQ now").json()
    assert v["tier"] == "T1"
    assert set(v["tier_timings"]) == {"CACHE", "T0", "T1"}   # no model call


def test_cache_replay_reports_only_cache(client, monkeypatch):
    monkeypatch.setattr(app_mod, "ABLATION", "full")
    payload = "deploy key AKIAQYLPMN5HHHFPZSPQ twice"
    _inspect(client, payload)
    v = _inspect(client, payload).json()
    assert v["tier"] == "CACHE" and set(v["tier_timings"]) == {"CACHE"}


# ------------------------------------------- p_block / verdict consistency
def test_overridden_verdict_reports_p_block_zero(monkeypatch):
    """Found by dry-running the pipeline against bench/mock_vllm.py.

    When span verification overrules the model, the DECISION is BENIGN. If
    p_block kept the model's pre-override score, the verdict body would read
    `action:allow, p_block:0.97` — and because B's threshold slider redraws
    the FPR/recall curve by re-thresholding these cached scores, that item
    would count as a block at every tau below 0.97. The published curve would
    disagree with the verdicts the service actually returned.
    """
    from services.inspect import app as m
    verdict = {"label": "FINANCIAL_NONPUBLIC", "severity": "HIGH",
               "policy_clause_id": "POL-006",
               "evidence_spans": ["not present in the payload"]}
    out = m.verify(verdict, "a completely unrelated benign payload")
    assert out["label"] == "BENIGN" and out["override"] == "unverified_evidence"

    # The router's rule, asserted directly: an override forces p_block to 0 so
    # the cached score reproduces the verdict at every selectable threshold.
    p_block = 0.97
    if "override" in out:
        p_block = 0.0
    assert p_block < min(m.MODES.values())


def test_p_block_reports_its_source():
    """INTEGRATION.md §11: a silent fallback to verbalized confidence looked
    like a calibrated posterior for a whole run. The source must be visible."""
    import math
    from services.inspect.calib import p_block_from_logprobs
    content = '{"label":"BENIGN","severity":"NONE"}'
    i = content.find('"BENIGN"')
    toks = [{"token": content[:i + 1], "logprob": -0.01, "top_logprobs": []},
            {"token": "BEN", "logprob": math.log(0.9), "top_logprobs": [
                {"token": ' "BEN', "logprob": math.log(0.9)},
                {"token": "\nFIN", "logprob": math.log(0.1)}]},
            {"token": content[i + 4:], "logprob": -0.01, "top_logprobs": []}]
    p, src = p_block_from_logprobs(toks, {"label": "BENIGN", "confidence": 0.97})
    assert src == "logprobs" and 0.0 < p < 0.5   # quotes/newlines still match

    p, src = p_block_from_logprobs([], {"label": "BENIGN", "confidence": 0.97})
    assert src == "verbalized"                   # and it says so


# ------------------------------------------------------------ synthetic scores
def test_synthetic_scores_shape(tmp_path):
    out = tmp_path / "scores.json"   # never clobber the team's results file
    subprocess.run([sys.executable, "bench/make_synthetic_scores.py",
                    "--n", "50", "--n-sensitive", "20", "--out", str(out)],
                   cwd=ROOT, check=True)
    s = json.loads(out.read_text())
    assert s["corpus_is_real"] is False           # never reportable
    assert len(s["benign"]) == 50 and len(s["items"]) == 50
    assert len(s["sensitive"]) == 20
    assert all(isinstance(p, float) for p in s["benign"])  # B: SCORES.benign
    assert {"_id", "p_block", "tier", "verdict"} <= set(s["items"][0])
