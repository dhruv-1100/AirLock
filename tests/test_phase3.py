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
    # fail CLOSED (503), proving the T1 short-circuit is really off.
    monkeypatch.setattr(app_mod, "ABLATION", "t2_verify")
    r = _inspect(client, CRED)
    assert r.status_code == 503
    assert r.json()["error"] == "policy_denied"


def test_full_row_unaffected(client, monkeypatch):
    monkeypatch.setattr(app_mod, "ABLATION", "full")
    v = _inspect(client, CRED).json()
    assert v["action"] == "block" and v["tier"] in ("T1", "CACHE")


# ------------------------------------------------------------ synthetic scores
def test_synthetic_scores_shape(tmp_path):
    subprocess.run([sys.executable, "bench/make_synthetic_scores.py",
                    "--n", "50", "--n-sensitive", "20"], cwd=ROOT, check=True)
    s = json.loads((ROOT / "results" / "scores_benign.json").read_text())
    assert s["corpus_is_real"] is False           # never reportable
    assert len(s["benign"]) == 50 and len(s["items"]) == 50
    assert len(s["sensitive"]) == 20
    assert all(isinstance(p, float) for p in s["benign"])  # B: SCORES.benign
    assert {"_id", "p_block", "tier", "verdict"} <= set(s["items"][0])
