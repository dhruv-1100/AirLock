"""Hard negatives must never enter the recall denominator.

The sensitive corpus carries 50 HARD_NEGATIVE items labelled BENIGN. Counting them as
recall targets published 395/450 = 87.8% when the true figure was 394/400 = 98.5%, and
hid the hard-negative false-positive line SRS §14 asks for by name.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench"))


def _row(i, label, bucket, p, verdict):
    return {"_id": f"x:{i}", "source": "synthetic", "label": label, "bucket": bucket,
            "p_block": p, "verdict": verdict, "latency_ms": 5, "tier": "T2", "char_len": 300,
            "predicted_label": label if verdict == "BLOCK" else "BENIGN"}


@pytest.fixture
def scored(tmp_path, monkeypatch):
    benign = [_row(i, "BENIGN", "", 0.01, "ALLOW") for i in range(100)]
    sens = [_row(i, "CREDENTIAL", "SENSITIVE", 0.99, "BLOCK") for i in range(38)]
    sens += [_row(100 + i, "CREDENTIAL", "SENSITIVE", 0.01, "ALLOW") for i in range(2)]
    # 10 hard negatives: 9 correctly allowed, 1 wrongly blocked
    sens += [_row(200 + i, "BENIGN", "HARD_NEGATIVE", 0.01, "ALLOW") for i in range(9)]
    sens += [_row(300, "BENIGN", "HARD_NEGATIVE", 0.99, "BLOCK")]

    (tmp_path / "results").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "results/scores_benign.json").write_text(json.dumps({"items": benign}))
    (tmp_path / "results/scores_sensitive.json").write_text(json.dumps({"items": sens}))
    monkeypatch.chdir(tmp_path)

    import report
    monkeypatch.setattr(report, "RESULTS", tmp_path / "results")
    report.build_report(0.55, 0.02, selftest=False)
    return json.loads((tmp_path / "results/fpr_report.json").read_text())


def test_recall_excludes_hard_negatives(scored):
    # 38 of 40 genuinely sensitive items blocked — NOT 39/50
    assert scored["recall"] == pytest.approx(38 / 40)


def test_hard_negative_reported_as_its_own_line(scored):
    hn = scored["hard_negative"]
    assert hn["n"] == 10
    assert hn["false_pos"] == 1
    assert hn["blocked_ids"] == ["x:300"]


def test_by_class_has_no_benign_recall_row(scored):
    assert "BENIGN" not in scored["by_class"]
