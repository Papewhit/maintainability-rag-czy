from __future__ import annotations

from pathlib import Path

import pytest

from backend.evaluation.comprehensive_routing import (
    build_comprehensive_comparison,
    config_fingerprint,
    routing_source_fingerprint,
    run_comprehensive_profile,
    summarize_comprehensive_runs,
)


pytestmark = pytest.mark.eval


def _run(case_id: str, profile: str, *, total_ms: float, answer_quality: float) -> dict:
    return {
        "case_id": case_id,
        "profile": profile,
        "source_commit": "abc123",
        "source_fingerprint": "sha256:fixture",
        "config_fingerprint": "same-config-except-profile",
        "cpu_peak_mb": 128.0,
        "gpu_peak_mb": 64.0 if profile == "quality_first_v1" else 0.0,
        "citation_validity": 1.0,
        "answer_quality": answer_quality,
        "rag_trace": {
            "sub_query_count": 2,
            "retrieval_branch_count": 3,
            "baseline_hit": True,
            "baseline_selected": case_id == "case-a",
            "dense_embedding_call_count": 3,
            "sparse_embedding_call_count": 3,
            "hybrid_search_call_count": 3,
            "split_search_call_count": 0,
            "rerank_pair_count": 6 if profile == "quality_first_v1" else 0,
            "branch_candidate_count": 30,
            "merged_unique_candidate_count": 12,
            "final_candidate_count": 5,
            "successful_generated_branch_ids": ["sub_query_0", "sub_query_1"],
            "represented_generated_branch_ids": ["sub_query_0", "sub_query_1"],
            "rerank_budget_exhausted": False,
            "stage_errors": [],
            "timings": {
                "multi_query_merge_ms": 4.0,
                "comprehensive_shared_postprocess_ms": 8.0,
                "total_rag_graph_ms": total_ms,
            },
        },
    }


def test_comprehensive_eval_aggregates_cost_quality_buckets_and_percentiles():
    runs = [
        _run("case-a", "quality_first_v1", total_ms=100.0, answer_quality=0.9),
        _run("case-b", "quality_first_v1", total_ms=140.0, answer_quality=0.8),
    ]

    summary = summarize_comprehensive_runs(runs)

    assert summary["case_count"] == 2
    assert summary["sub_query_count_buckets"] == {"2": 2}
    assert summary["retrieval_branch_count_buckets"] == {"3": 2}
    assert summary["baseline_hit_rate"] == 1.0
    assert summary["baseline_selected_rate"] == 0.5
    assert summary["dense_embedding_call_count_total"] == 6
    assert summary["hybrid_search_call_count_total"] == 6
    assert summary["rerank_pair_count_total"] == 12
    assert summary["generated_branch_representation_rate"] == 1.0
    assert summary["timings_ms"]["total_rag_graph_ms"] == {"p50": 120.0, "p95": 140.0}
    assert summary["cpu_peak_mb"] == 128.0
    assert summary["gpu_peak_mb"] == 64.0
    assert summary["error_rate"] == 0.0
    assert summary["degradation_rate"] == 0.0
    assert summary["citation_validity_mean"] == 1.0
    assert summary["answer_quality_mean"] == 0.85


def test_profile_comparison_requires_paired_source_bound_runs_and_reports_deltas():
    quality = [
        _run("case-a", "quality_first_v1", total_ms=140.0, answer_quality=0.9),
        _run("case-b", "quality_first_v1", total_ms=160.0, answer_quality=0.8),
    ]
    ablation = [
        _run("case-a", "eval_no_crossencoder_v1", total_ms=100.0, answer_quality=0.8),
        _run("case-b", "eval_no_crossencoder_v1", total_ms=120.0, answer_quality=0.7),
    ]

    report = build_comprehensive_comparison(quality, ablation)

    assert report["source_commit"] == "abc123"
    assert report["source_fingerprint"] == "sha256:fixture"
    assert report["case_ids"] == ["case-a", "case-b"]
    assert report["quality_first_profile"] == "quality_first_v1"
    assert report["ablation_profile"] == "eval_no_crossencoder_v1"
    assert report["deltas"]["answer_quality_mean"] == pytest.approx(0.1)
    assert report["deltas"]["total_rag_graph_p95_ms"] == 40.0
    assert report["deltas"]["rerank_pair_count_total"] == 12

    mismatched = [dict(ablation[0], source_fingerprint="other"), ablation[1]]
    with pytest.raises(ValueError, match="source fingerprint"):
        build_comprehensive_comparison(quality, mismatched)


def test_profile_runner_binds_each_case_to_source_config_and_resource_peaks():
    class FakeSampler:
        cpu_peak_mb = 12.5
        gpu_peak_mb = 3.0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    runs = run_comprehensive_profile(
        [{"case_id": "case-a", "query": "综合风险"}],
        profile="quality_first_v1",
        run_case=lambda case, profile: {
            "rag_trace": {"sub_query_count": 2, "timings": {"total_rag_graph_ms": 10.0}},
            "citation_validity": 0.9,
            "answer_quality": 0.8,
        },
        source_commit="abc123",
        source_fingerprint="sha256:fixture",
        config_fingerprint="config:v1",
        sampler_factory=FakeSampler,
    )

    assert runs[0]["profile"] == "quality_first_v1"
    assert runs[0]["source_commit"] == "abc123"
    assert runs[0]["source_fingerprint"] == "sha256:fixture"
    assert runs[0]["config_fingerprint"] == "config:v1"
    assert runs[0]["cpu_peak_mb"] == 12.5
    assert runs[0]["gpu_peak_mb"] == 3.0


def test_routing_source_fingerprint_binds_implementation_spec_and_dataset():
    repo_root = Path(__file__).parents[3]

    fingerprint = routing_source_fingerprint(repo_root)

    assert fingerprint["version"] == 2
    assert fingerprint["normalization"] == "lf"
    assert len(fingerprint["sha256"]) == 64
    assert "backend/rag/comprehensive_postprocess.py" in fingerprint["source_files"]
    assert "backend/rag/trace.py" in fingerprint["source_files"]
    assert "backend/rag/terminology/table.py" in fingerprint["source_files"]
    assert "backend/infra/embedding.py" in fingerprint["source_files"]
    assert "backend/infra/vector_store/milvus_client.py" in fingerprint["source_files"]
    assert "backend/evaluation/answer_eval.py" in fingerprint["source_files"]
    assert "tests/eval/data/intent_routing/precise_lookup.jsonl" in fingerprint["source_files"]
    assert "tests/eval/data/intent_routing/filename_registry.json" in fingerprint["source_files"]


def test_config_fingerprint_binds_models_collection_and_retrieval_configuration():
    baseline = {
        "runtime": {"milvus_rrf_k": 60},
        "intent_model": "intent-a",
        "answer_model": "answer-a",
        "judge_model": "judge-a",
        "milvus_collection": "collection-a",
        "embedding_model": "bge-m3",
        "bm25_state_path": "data/bm25_state.json",
    }

    first = config_fingerprint(baseline)
    second = config_fingerprint({**baseline, "judge_model": "judge-b"})

    assert first.startswith("sha256:")
    assert first != second
