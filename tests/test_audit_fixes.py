"""Regression tests for the October audit fixes — PLAN.md B1, B3, B4.

Each test states the behaviour that was wrong, so a failure reads as the bug coming back.
"""

import math
import os

import pytest

os.environ.setdefault("MONGO_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402

from services.inspect import app as app_mod  # noqa: E402
from services.inspect import calib, mongo, origins  # noqa: E402

EVIL = "https://evil.example"


@pytest.fixture
def client():
    return TestClient(app_mod.app)


# ------------------------------------------------------------------ B1 origin policy
@pytest.mark.parametrize("method,path", [
    ("GET", "/v1/decisions?limit=1"),
    ("GET", "/v1/report"),
    ("POST", "/v1/feedback"),
    ("POST", "/v1/answer"),
])
def test_hostile_origin_is_refused_on_restricted_routes(client, method, path):
    # Was: 200 with Access-Control-Allow-Origin: * — any page could read blocked
    # evidence spans back out, or poison the corpus via /v1/feedback.
    r = client.request(method, path, headers={"Origin": EVIL},
                       json={"decision_id": "6712c0f1a3e94b2d8c5e1102", "prompt": "x"})
    assert r.status_code == 403
    assert r.json()["error"] == "policy_denied"


def test_hostile_preflight_is_refused(client):
    r = client.options("/v1/decisions", headers={
        "Origin": EVIL, "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Private-Network": "true"})
    assert r.status_code == 403
    assert "access-control-allow-private-network" not in r.headers


@pytest.mark.parametrize("path", ["/healthz", "/v1/policy"])
def test_public_routes_stay_open_to_any_origin(client, path):
    # The extension's content-script fallback calls these from the PAGE's origin.
    r = client.get(path, headers={"Origin": "https://chatgpt.com"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize("origin", [
    "chrome-extension://abcdefghijklmnopabcdefghijklmnop",
    "http://localhost:5173", "http://127.0.0.1:5174", "http://localhost:5175",
])
def test_allowlisted_origins_get_their_own_origin_echoed(client, origin):
    r = client.get("/v1/decisions?limit=1", headers={"Origin": origin})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == origin   # not "*"
    assert r.headers["vary"] == "Origin"


def test_non_browser_clients_without_origin_are_unaffected(client):
    # curl and the FPR harness send no Origin; no web page can drive them.
    assert client.get("/v1/decisions?limit=1").status_code == 200


def test_pinned_extension_id_rejects_other_extensions(monkeypatch):
    monkeypatch.setenv("AIRLOCK_EXTENSION_ID", "ours")
    assert origins.origin_allowed("chrome-extension://ours")
    assert not origins.origin_allowed("chrome-extension://someone-else")


def test_hostile_websocket_is_closed(client):
    # Browsers do not apply CORS to WebSockets at all — Origin is the only signal.
    with pytest.raises(Exception):
        with client.websocket_connect("/v1/stream", headers={"Origin": EVIL}) as ws:
            ws.receive_text()


def test_decisions_projection_drops_blocked_content():
    # recent_decisions must never ship the blocked text, or a hash of it.
    import inspect
    src = inspect.getsource(mongo.recent_decisions)
    for field in ("evidence_spans", "payload_sha256", "payload_enc", "evidence_png"):
        assert f'"{field}": 0' in src, f"{field} is not projected out"


# ------------------------------------------------------------------ B3 calibration
def _confident_benign_logprobs():
    top = ([{"token": '"BEN', "logprob": math.log(0.97)},
            {"token": '"B', "logprob": math.log(0.02)},
            {"token": ' "BENIGN', "logprob": math.log(0.009)}]
           + [{"token": f'"x{i}', "logprob": math.log(1e-5)} for i in range(17)])
    return [{"token": '{"label": "', "logprob": 0, "top_logprobs": []},
            {"token": '"BEN', "logprob": math.log(0.97), "top_logprobs": top}]


def test_absent_labels_are_floored_not_dropped():
    logits = calib.label_logits_from_logprobs(_confident_benign_logprobs())
    assert set(logits) == set(calib.LABELS)


def test_p_block_is_never_exactly_zero_for_a_confident_model():
    # Was exactly 0.0 for 812 of 1000 benign items.
    logits = calib.label_logits_from_logprobs(_confident_benign_logprobs())
    assert calib.p_block_from_logits(logits, 1.0) > 0.0


def test_temperature_actually_moves_p_block():
    # Was 0.0 at T=1, 3 and 8 — calibration could not move anything.
    logits = calib.label_logits_from_logprobs(_confident_benign_logprobs())
    p1, p3, p8 = (calib.p_block_from_logits(logits, t) for t in (1.0, 3.0, 8.0))
    assert p1 < p3 < p8


# ------------------------------------------------------------------ B4 feedback honesty
def test_feedback_does_not_claim_success_when_nothing_was_written(client, monkeypatch):
    # Was {"ok": true, "embedded": true, "corpus_id": "None"} with Mongo down.
    async def nothing(_decision_id):
        return None
    monkeypatch.setattr(app_mod, "_HAVE_MONGO", True)
    monkeypatch.setattr(mongo, "write_back_corpus", nothing)
    r = client.post("/v1/feedback", json={"decision_id": "6712c0f1a3e94b2d8c5e1102"})
    assert r.status_code == 503
    assert r.json().get("ok") is not True
