from __future__ import annotations

import pytest

from backend.rag.fallback_scope import (
    level2_candidate_k,
    level2_same_root_cap,
    relax_scope,
)
from backend.rag.query_plan import (
    ComprehensiveQueryPlan,
    PreciseQueryPlan,
    RetrievalScope,
    SubQuery,
)


pytestmark = pytest.mark.unit


def _precise(scope_mode: str) -> PreciseQueryPlan:
    matched = (("manual.pdf", 0.9),) if scope_mode != "none" else ()
    return PreciseQueryPlan(
        raw_query="raw",
        clean_query="clean",
        semantic_query="semantic",
        scope_mode=scope_mode,
        matched_files=matched,
        route="scoped_hybrid" if matched else "global_hybrid",
    )


def _comprehensive(scope_mode: str, *, source: str) -> ComprehensiveQueryPlan:
    matched = (("manual.pdf", 0.9),) if scope_mode != "none" else ()
    return ComprehensiveQueryPlan(
        raw_query="raw",
        clean_query="clean",
        analysis_type="general",
        sub_queries=(SubQuery("q", "domain", 1),),
        coverage_domains=("domain",),
        retrieval_scope=RetrievalScope(
            scope_mode=scope_mode,
            matched_files=matched,
            source=source,
        ),
    )


@pytest.mark.parametrize("scope_mode", ["filter", "none"])
def test_precise_filter_and_none_preserve_scope_invariants(scope_mode):
    plan = _precise(scope_mode)

    relaxed = relax_scope(plan)

    assert relaxed == plan


def test_precise_boost_to_none_updates_mode_files_and_route_atomically():
    relaxed = relax_scope(_precise("boost"))

    assert relaxed.scope_mode == "none"
    assert relaxed.matched_files == ()
    assert relaxed.route == "global_hybrid"
    assert relaxed.semantic_query == "semantic"


@pytest.mark.parametrize("source", ["document_hints", "context_files"])
def test_comprehensive_scope_behavior_does_not_depend_on_source(source):
    relaxed = relax_scope(_comprehensive("boost", source=source))

    assert relaxed.retrieval_scope.scope_mode == "none"
    assert relaxed.retrieval_scope.matched_files == ()
    assert relaxed.retrieval_scope.source == source
    assert relaxed.clean_query == "clean"
    assert relaxed.postprocess_profile == "quality_first_v1"


def test_comprehensive_filter_remains_hard_scope():
    plan = _comprehensive("filter", source="context_files")

    assert relax_scope(plan) == plan


@pytest.mark.parametrize(
    ("current", "maximum", "expected"),
    [
        (50, 100, 75),
        (51, 100, 77),
        (80, 100, 100),
        (100, 100, 100),
        (120, 50, 120),
    ],
)
def test_level2_candidate_k_grows_by_one_point_five_and_respects_existing_cap(
    current, maximum, expected
):
    assert level2_candidate_k(current, maximum) == expected


def test_level2_same_root_cap_increases_by_one():
    assert level2_same_root_cap(2) == 3
