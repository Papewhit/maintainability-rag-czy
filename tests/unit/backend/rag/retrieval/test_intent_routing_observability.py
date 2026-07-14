from __future__ import annotations

import pytest

from backend.rag.observability import summarize_intent_routing_traces


pytestmark = pytest.mark.unit


def test_observability_summary_exposes_rollout_metrics_and_latency_percentiles():
    traces = [
        {
            "intent": "precise_lookup",
            "intent_classifier_enabled": True,
            "intent_llm_ms": 100.0,
            "intent_fallback_to_rules": False,
            "timings": {"total_rag_graph_ms": 200.0},
        },
        {
            "intent": "comprehensive_analysis",
            "intent_classifier_enabled": True,
            "intent_llm_ms": 200.0,
            "intent_llm_error": "timeout",
            "intent_fallback_to_rules": True,
            "effective_comprehensive_postprocess_profile": "quality_first_v1",
            "sub_query_count": 2,
            "retrieval_branch_count": 3,
            "baseline_hit": True,
            "baseline_selected": False,
            "embedding_call_count": 6,
            "hybrid_search_call_count": 3,
            "rerank_pair_count": 8,
            "rerank_budget_exhausted": True,
            "timings": {
                "multi_query_merge_ms": 5.0,
                "comprehensive_shared_postprocess_ms": 10.0,
                "total_rag_graph_ms": 400.0,
            },
        },
    ]

    summary = summarize_intent_routing_traces(traces)

    assert summary["request_count"] == 2
    assert summary["intent_classifier_latency_ms"] == {"p50": 150.0, "p95": 200.0}
    assert summary["llm_failure_rate"] == 0.5
    assert summary["rule_fallback_rate"] == 0.5
    assert summary["intent_share"] == {
        "comprehensive_analysis": 0.5,
        "precise_lookup": 0.5,
    }
    comprehensive = summary["comprehensive"]
    assert comprehensive["profile_counts"] == {"quality_first_v1": 1}
    assert comprehensive["sub_query_count_buckets"] == {"2": 1}
    assert comprehensive["retrieval_branch_count_buckets"] == {"3": 1}
    assert comprehensive["baseline_hit_rate"] == 1.0
    assert comprehensive["baseline_selected_rate"] == 0.0
    assert comprehensive["embedding_call_count_total"] == 6
    assert comprehensive["hybrid_search_call_count_total"] == 3
    assert comprehensive["rerank_pair_count_total"] == 8
    assert comprehensive["budget_exhaustion_rate"] == 1.0
    assert comprehensive["merge_latency_ms"] == {"p50": 5.0, "p95": 5.0}
    assert comprehensive["postprocess_latency_ms"] == {"p50": 10.0, "p95": 10.0}
    assert summary["total_rag_graph_latency_ms"] == {"p50": 300.0, "p95": 400.0}
