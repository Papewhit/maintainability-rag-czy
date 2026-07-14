from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable


def _latencies(values: Iterable[float]) -> dict[str, float] | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    p50 = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    return {"p50": round(p50, 3), "p95": round(p95, 3)}


def _rate(count: int, total: int) -> float | None:
    return round(count / total, 6) if total else None


def summarize_intent_routing_traces(traces: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = [dict(trace or {}) for trace in traces]
    classifier_calls = [trace for trace in items if trace.get("intent_classifier_enabled")]
    comprehensive = [trace for trace in items if trace.get("intent") == "comprehensive_analysis"]
    intent_counts = Counter(str(trace.get("intent") or "unknown") for trace in items)
    total_timings = [dict(trace.get("timings") or {}) for trace in items]
    comprehensive_timings = [dict(trace.get("timings") or {}) for trace in comprehensive]
    return {
        "request_count": len(items),
        "intent_classifier_call_count": len(classifier_calls),
        "intent_classifier_latency_ms": _latencies(
            trace["intent_llm_ms"] for trace in classifier_calls if trace.get("intent_llm_ms") is not None
        ),
        "llm_failure_rate": _rate(
            sum(bool(trace.get("intent_llm_error")) for trace in classifier_calls),
            len(classifier_calls),
        ),
        "rule_fallback_rate": _rate(
            sum(bool(trace.get("intent_fallback_to_rules")) for trace in classifier_calls),
            len(classifier_calls),
        ),
        "intent_share": {
            key: round(value / len(items), 6)
            for key, value in sorted(intent_counts.items())
        } if items else {},
        "total_rag_graph_latency_ms": _latencies(
            timing["total_rag_graph_ms"]
            for timing in total_timings
            if timing.get("total_rag_graph_ms") is not None
        ),
        "comprehensive": {
            "request_count": len(comprehensive),
            "profile_counts": dict(sorted(Counter(
                str(trace.get("effective_comprehensive_postprocess_profile") or "unknown")
                for trace in comprehensive
            ).items())),
            "sub_query_count_buckets": dict(sorted(Counter(
                str(int(trace.get("sub_query_count") or 0)) for trace in comprehensive
            ).items())),
            "retrieval_branch_count_buckets": dict(sorted(Counter(
                str(int(trace.get("retrieval_branch_count") or 0)) for trace in comprehensive
            ).items())),
            "baseline_hit_rate": _rate(
                sum(bool(trace.get("baseline_hit")) for trace in comprehensive), len(comprehensive)
            ),
            "baseline_selected_rate": _rate(
                sum(bool(trace.get("baseline_selected")) for trace in comprehensive), len(comprehensive)
            ),
            "embedding_call_count_total": sum(
                int(trace.get("embedding_call_count") or 0) for trace in comprehensive
            ),
            "hybrid_search_call_count_total": sum(
                int(trace.get("hybrid_search_call_count") or 0) for trace in comprehensive
            ),
            "rerank_pair_count_total": sum(
                int(trace.get("rerank_pair_count") or 0) for trace in comprehensive
            ),
            "budget_exhaustion_rate": _rate(
                sum(bool(trace.get("rerank_budget_exhausted")) for trace in comprehensive),
                len(comprehensive),
            ),
            "merge_latency_ms": _latencies(
                timing["multi_query_merge_ms"]
                for timing in comprehensive_timings
                if timing.get("multi_query_merge_ms") is not None
            ),
            "postprocess_latency_ms": _latencies(
                timing["comprehensive_shared_postprocess_ms"]
                for timing in comprehensive_timings
                if timing.get("comprehensive_shared_postprocess_ms") is not None
            ),
        },
    }
