from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.config import ARK_API_KEY, FAST_MODEL
from backend.evaluation.intent_routing import (
    IntentEvalSample,
    SubQueryQualityJudge,
    evaluate_intent_samples,
    load_intent_eval_filename_registry,
    load_intent_eval_samples,
    write_intent_eval_report,
)
from backend.rag.intent import IntentClassifier, IntentDecision, build_intent_parse_result


pytestmark = pytest.mark.eval

DATA_DIR = Path(__file__).parents[1] / "data" / "intent_routing"
REPO_ROOT = Path(__file__).parents[3]


def test_intent_routing_dataset_has_required_schema_ratio_and_coverage():
    samples = load_intent_eval_samples(DATA_DIR)

    assert len(samples) == 100
    assert sum(sample.expected_intent == "precise_lookup" for sample in samples) == 70
    assert sum(sample.expected_intent == "comprehensive_analysis" for sample in samples) == 30
    assert {sample.expected_granularity for sample in samples if sample.expected_granularity} == {
        "paragraph",
        "table",
        "step_list",
        "figure",
    }
    assert {sample.expected_analysis_type for sample in samples if sample.expected_analysis_type} == {
        "design_reuse",
        "comparison",
        "procedure_synthesis",
        "general",
    }
    assert {sample.expected_scope for sample in samples if sample.expected_scope} >= {
        "filter",
        "boost",
        "none",
    }


def test_intent_eval_filename_registry_covers_labeled_document_hints():
    registry, fingerprint = load_intent_eval_filename_registry(DATA_DIR)

    assert len(registry) == 39
    assert all(set(entry) == {"raw", "normalized"} for entry in registry)
    assert fingerprint.startswith("sha256:")
    assert len(fingerprint) == len("sha256:") + 64


def test_intent_eval_harness_scores_intent_plan_and_sub_query_quality(tmp_path):
    samples = [
        IntentEvalSample(
            query="表 2 的额定电流是多少",
            expected_intent="precise_lookup",
            expected_scope="none",
            expected_granularity="table",
            notes="精确表格定位",
        ),
        IntentEvalSample(
            query="比较机械与电气风险",
            expected_intent="comprehensive_analysis",
            expected_sub_queries=("机械风险", "电气风险"),
            expected_analysis_type="comparison",
            notes="跨域比较",
        ),
    ]

    def classify(sample):
        if sample.expected_intent == "precise_lookup":
            decision = IntentDecision(
                intent="precise_lookup",
                confidence=0.9,
                scope_hint="none",
                target_granularity="table",
            )
        else:
            decision = IntentDecision.model_validate(
                {
                    "intent": "comprehensive_analysis",
                    "confidence": 0.8,
                    "analysis_type": "comparison",
                    "sub_queries": [
                        {"query": "机械风险", "domain": "mechanical", "priority": 1},
                        {"query": "电气风险", "domain": "electrical", "priority": 2},
                    ],
                }
            )
        return build_intent_parse_result(sample.query, decision=decision, llm_model="fake")

    report = evaluate_intent_samples(
        samples,
        classify=classify,
        judge_sub_queries=lambda sample, result: 4.5,
        model_name="fake-model",
        evaluation_mode="deterministic_contract_test",
    )

    assert report["intent_accuracy"] == 1.0
    assert report["plan_validity"] == 1.0
    assert report["sub_query_quality_mean"] == 4.5
    assert report["sub_query_quality_scored_count"] == 1
    assert report["status"] == "partial"
    output = write_intent_eval_report(report, repo_root=tmp_path)
    assert output.parent == tmp_path / "eval" / "intent"
    assert output.name.endswith("_fake-model.json")


@pytest.mark.requires_models
@pytest.mark.skipif(
    os.getenv("RAG_INTENT_EVAL_RUN_REAL_MODEL") != "1" or not ARK_API_KEY or not FAST_MODEL,
    reason="set RAG_INTENT_EVAL_RUN_REAL_MODEL=1 with FAST_MODEL credentials",
)
def test_current_intent_classifier_writes_release_evaluation_report():
    samples = load_intent_eval_samples(DATA_DIR)
    filename_registry, registry_fingerprint = load_intent_eval_filename_registry(DATA_DIR)
    classifier = IntentClassifier(model_name=FAST_MODEL, timeout_seconds=10.0)
    judge = SubQueryQualityJudge(model=classifier._get_model())
    report = evaluate_intent_samples(
        samples,
        classify=lambda sample: build_intent_parse_result(
            sample.query,
            classifier=classifier,
            classifier_enabled=True,
            filename_registry=filename_registry,
            llm_model=FAST_MODEL,
        ),
        judge_sub_queries=judge.judge,
        model_name=FAST_MODEL,
        evaluation_mode="current_model",
        registry_fingerprint=registry_fingerprint,
    )

    output = write_intent_eval_report(report, repo_root=REPO_ROOT)
    assert output.exists()
    assert report["sample_count"] == 100
    assert report["evaluation_mode"] == "current_model"
    assert report["filename_registry_fingerprint"] == registry_fingerprint
