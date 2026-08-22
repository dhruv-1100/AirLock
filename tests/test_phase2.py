"""Phase 2 tests: image gate one-sidedness, T3 grounding, harness stats."""

import base64
import io
import random

import pytest
from PIL import Image, ImageDraw

from services.inspect.tiers import gate_img, t3
from bench.run_fpr import wilson_ci


def _b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _photo_like():
    # Smooth colour-rich gradient with mild noise — no text-like edges.
    rng = random.Random(1337)
    img = Image.new("RGB", (640, 480))
    px = img.load()
    for y in range(480):
        for x in range(640):
            px[x, y] = (x * 255 // 640 + rng.randint(-6, 6),
                        y * 255 // 480 + rng.randint(-6, 6),
                        (x + y) * 255 // 1120 + rng.randint(-6, 6))
    return img


def _chart_like():
    # White canvas, axis lines, bars, dense tick text — screenshot territory.
    img = Image.new("RGB", (1280, 720), "white")
    d = ImageDraw.Draw(img)
    d.line([(100, 50), (100, 650), (1200, 650)], fill="black", width=3)
    for i, h in enumerate([200, 350, 500, 280, 430]):
        d.rectangle([160 + i * 200, 650 - h, 300 + i * 200, 650], fill="black")
    for y in range(80, 640, 40):
        d.text((20, y), "FY26 1234", fill="black")
    d.text((400, 20), "FY26 Revenue Forecast - Plan vs Commit", fill="black")
    return img


def test_gate_fast_passes_photo():
    r = gate_img.inspect_image(_b64(_photo_like()))
    assert r.fast_pass, (r.edge_density, r.unique_colours, r.hist_entropy)


def test_gate_never_passes_chart():
    r = gate_img.inspect_image(_b64(_chart_like()))
    assert not r.fast_pass


def test_gate_never_passes_flat_screenshot():
    img = Image.new("RGB", (800, 600), "#f0f0f0")  # flat UI background
    r = gate_img.inspect_image(_b64(img))
    assert not r.fast_pass  # low colour count — must escalate, never pass


# ------------------------------------------------------------- T3 grounding
def _v(**kw):
    base = {"image_type": "chart", "extracted_text": [], "org_markers": [],
            "temporal_markers": [], "confidentiality_markers": [],
            "evidence_spans": [], "rationale": "", "label": "BENIGN",
            "severity": "NONE", "policy_clause_id": "NONE", "confidence": 0.9}
    base.update(kw)
    return base


def test_ground_forces_benign_without_markers():
    v = _v(label="FINANCIAL_NONPUBLIC", severity="HIGH",
           policy_clause_id="POL-006",
           extracted_text=["Revenue", "Q1", "Q2"],
           evidence_spans=["Revenue"])
    out, _ = t3.ground(v)
    assert out["label"] == "BENIGN" and out["override"] == "no_grounded_marker"


def test_ground_keeps_verdict_with_confidentiality_marker():
    v = _v(label="FINANCIAL_NONPUBLIC", severity="HIGH",
           policy_clause_id="POL-006",
           extracted_text=["FY26 Revenue Forecast", "Internal - Do Not Distribute"],
           temporal_markers=["FY26"],
           confidentiality_markers=["Internal - Do Not Distribute"],
           evidence_spans=["FY26 Revenue Forecast"])
    out, ocr = t3.ground(v)
    assert out["label"] == "FINANCIAL_NONPUBLIC"
    assert "FY26 Revenue Forecast" in ocr


def test_ground_keeps_verdict_on_t1_hit_in_ocr():
    v = _v(label="CREDENTIAL", severity="HIGH", policy_clause_id="POL-001",
           extracted_text=["config.py", "AKIAQYLPMN5HHHFPZSPQ"],
           evidence_spans=["AKIAQYLPMN5HHHFPZSPQ"])
    out, _ = t3.ground(v)
    assert out["label"] == "CREDENTIAL"


def test_ground_benign_passthrough():
    out, _ = t3.ground(_v(extracted_text=["matplotlib demo"]))
    assert out["label"] == "BENIGN" and "override" not in out


# ------------------------------------------------------------- harness math
def test_wilson_ci_matches_srs_example():
    lo, hi = wilson_ci(3, 1000)
    # SRS: 3/1000 → 0.30% [0.10%, 0.88%]
    assert round(lo * 100, 2) == 0.10
    assert round(hi * 100, 2) == 0.88


def test_wilson_ci_zero_fp_not_zero_bound():
    lo, hi = wilson_ci(0, 1000)
    assert lo == 0.0 and hi > 0.0  # never report "zero"
