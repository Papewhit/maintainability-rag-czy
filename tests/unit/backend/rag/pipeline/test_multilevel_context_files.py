from __future__ import annotations

from unittest.mock import patch

import pytest

import backend.rag.pipeline as rag_pipeline
from backend.rag.query_plan import ComprehensiveQueryPlan, RetrievalScope, SubQuery


pytestmark = pytest.mark.unit


def test_comprehensive_context_files_remain_one_shared_filter_on_existing_fanout_only():
    context_files = ["manual-a.pdf", "manual-b.pdf"]
    plan = ComprehensiveQueryPlan(
        raw_query="综合分析安装与维护",
        clean_query="综合分析安装与维护",
        analysis_type="general",
        sub_queries=(
            SubQuery("安装步骤", "installation", 1),
            SubQuery("维护要求", "maintenance", 2),
        ),
        coverage_domains=("installation", "maintenance"),
        retrieval_scope=RetrievalScope(
            scope_mode="filter",
            matched_files=(("manual-a.pdf", 1.0), ("manual-b.pdf", 1.0)),
            source="context_files",
        ),
    )
    calls = []

    def retrieve(query, **kwargs):
        calls.append((query, kwargs))
        return {
            "candidates": [],
            "meta": {"candidate_k": 50, "timings": {}, "stage_errors": []},
        }

    with (
        patch("backend.rag.pipeline.retrieve_candidate_pool", side_effect=retrieve),
        patch(
            "backend.rag.pipeline.retrieve_context_documents",
            side_effect=AssertionError("attachment branch must not run"),
            create=True,
        ),
    ):
        result = rag_pipeline.decompose_and_fanout(
            {
                "question": plan.raw_query,
                "query_plan": plan,
                "query_plan_type": "comprehensive",
                "context_files": context_files,
                "rag_trace": {},
            }
        )

    assert len(calls) == 3
    assert {query for query, _ in calls} == {
        plan.clean_query,
        "安装步骤",
        "维护要求",
    }
    assert all(kwargs["context_files"] == context_files for _, kwargs in calls)
    assert all(kwargs["strict_scope_filter"] is True for _, kwargs in calls)
    assert all(
        kwargs["query_plan"].matched_files == plan.retrieval_scope.matched_files
        for _, kwargs in calls
    )
    assert result["rag_trace"]["retrieval_branch_count"] == 3
    assert result["rag_trace"]["scope_filter_applied"] is True
