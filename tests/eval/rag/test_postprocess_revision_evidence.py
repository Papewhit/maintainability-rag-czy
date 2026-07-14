import json
from pathlib import Path

import pytest

from scripts.source_fingerprint import postprocess_source_fingerprint


pytestmark = pytest.mark.eval

RESULTS_DIR = Path(__file__).parents[3] / "docs" / "rag-postprocess-evidence"
REPO_ROOT = Path(__file__).parents[3]


def _load(name: str) -> dict:
    return json.loads((RESULTS_DIR / name).read_text(encoding="utf-8"))


def _paired_outcome(left: dict, right: dict) -> tuple[int, int, int]:
    wins = losses = ties = 0
    for left_case, right_case in zip(left["cases"], right["cases"], strict=True):
        assert left_case["case"] == right_case["case"]
        delta = left_case["answerability"] - right_case["answerability"]
        wins += delta > 0
        losses += delta < 0
        ties += delta == 0
    return wins, losses, ties


def test_revision_evidence_is_paired_and_historically_source_fingerprinted():
    baseline = _load("baseline-results.json")
    pool20 = _load("current-pool-20-results.json")

    assert baseline["revision"] == "06faa1c2a74599656dffcf0b67102f532ba951a3"
    assert baseline["source_fingerprint_version"] == 2
    assert baseline["source_fingerprint_normalization"] == "lf"
    assert baseline["source_sha256"] != pool20["source_sha256"]
    assert pool20["source_fingerprint_version"] == 2
    assert pool20["source_fingerprint_normalization"] == "lf"
    assert pool20["source_files"] == [
        "backend/rag/utils.py",
        "backend/rag/context.py",
        "backend/rag/rerank.py",
    ]
    assert pool20["source_sha256"] == "faf0e2b01e76a81fd56f452584a44e1345820258c9712e93da12d4eb8537e6c1"
    assert pool20["source_sha256"] != postprocess_source_fingerprint(REPO_ROOT)["source_sha256"]
    assert baseline["pipeline"] == "baseline"
    assert pool20["pipeline"] == "current"
    assert [case["case"] for case in baseline["cases"]] == [
        case["case"] for case in pool20["cases"]
    ]
    assert pool20["mean_answerability"] > baseline["mean_answerability"]
    assert pool20["complete_step_groups"] > baseline["complete_step_groups"]


def test_pool_20_has_best_paired_quality_without_losses():
    pool10 = _load("current-pool-10-results.json")
    pool15 = _load("current-pool-15-results.json")
    pool20 = _load("current-pool-20-results.json")

    assert pool20["mean_answerability"] > pool15["mean_answerability"] > pool10["mean_answerability"]
    assert _paired_outcome(pool20, pool15) == (4, 0, 4)
    assert _paired_outcome(pool20, pool10) == (6, 0, 2)
    assert pool20["complete_step_groups"] > pool15["complete_step_groups"] > pool10["complete_step_groups"]
    assert 0 <= pool20["p50_ms"] <= pool20["p95_ms"]
