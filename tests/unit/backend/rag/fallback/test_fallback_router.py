from __future__ import annotations

import pytest

from backend.rag.fallback_router import route_fallback
from backend.rag.query_plan import PreciseQueryPlan


pytestmark = pytest.mark.unit


def _plan() -> PreciseQueryPlan:
    return PreciseQueryPlan(
        raw_query="如何回滚",
        semantic_query="如何回滚",
        clean_query="如何回滚",
    )


@pytest.mark.parametrize(
    ("reasons", "target", "signal", "budget"),
    [
        ([], 0, "confidence_sufficient", 0),
        (["no_docs"], 3, "no_docs", 0),
        (["anchor_mismatch"], 1, "anchor_mismatch", 3000),
        (["low_score_and_margin"], 1, "low_score_and_margin", 3000),
        (["weak_margin_and_root"], 2, "weak_margin_and_root", 2500),
        (["unknown_confidence_reason"], 1, "unknown_confidence_reason", 3000),
    ],
)
def test_signal_rules_are_deterministic(reasons, target, signal, budget):
    decision = route_fallback(
        {"confidence_reasons": reasons},
        _plan(),
        [],
        8000,
    )

    assert decision.target_level == target
    assert decision.primary_signal == signal
    assert decision.budget_ms == budget
    assert decision.contributing_signals == reasons


def test_no_docs_wins_over_other_signals_and_budget():
    decision = route_fallback(
        {"confidence_reasons": ["anchor_mismatch", "no_docs"]},
        _plan(),
        [],
        0,
    )

    assert decision.target_level == 3
    assert decision.primary_signal == "no_docs"
    assert "retry unlikely" in decision.reason


@pytest.mark.parametrize(
    ("reasons", "target", "signal"),
    [
        (["weak_margin_and_root", "anchor_mismatch"], 1, "anchor_mismatch"),
        (["low_score_and_margin", "weak_margin_and_root"], 2, "weak_margin_and_root"),
    ],
)
def test_multi_signal_priority_matches_the_contract(reasons, target, signal):
    decision = route_fallback(
        {"confidence_reasons": reasons},
        _plan(),
        [],
        8000,
    )

    assert decision.target_level == target
    assert decision.primary_signal == signal


@pytest.mark.parametrize(
    ("attempted", "remaining", "target", "signal"),
    [
        ([1], 8000, 2, "level1_exhausted"),
        ([1], 2499, 3, "budget_exhausted"),
        ([2], 8000, 3, "levels_exhausted"),
        ([1, 2], 8000, 3, "levels_exhausted"),
    ],
)
def test_attempted_levels_never_repeat(attempted, remaining, target, signal):
    decision = route_fallback(
        {"confidence_reasons": ["anchor_mismatch"]},
        _plan(),
        attempted,
        remaining,
    )

    assert decision.target_level == target
    assert decision.primary_signal == signal


@pytest.mark.parametrize(
    ("reason", "remaining"),
    [
        ("anchor_mismatch", 2999),
        ("weak_margin_and_root", 2499),
    ],
)
def test_insufficient_budget_skips_selected_level(reason, remaining):
    decision = route_fallback(
        {"confidence_reasons": [reason]},
        _plan(),
        [],
        remaining,
    )

    assert decision.target_level == 3
    assert decision.primary_signal == "budget_exhausted"
    assert decision.budget_ms == 0


def test_router_ignores_terminology_coverage_for_scope_routing():
    decision = route_fallback(
        {
            "confidence_reasons": ["low_score_and_margin"],
            "entity_type_coverage": 0.0,
        },
        _plan(),
        [],
        8000,
    )

    assert decision.target_level == 1


def test_exact_custom_level_budget_is_available_to_selected_level():
    decision = route_fallback(
        {"confidence_reasons": ["anchor_mismatch"]},
        _plan(),
        [],
        1200,
        level1_budget_ms=1200,
        level2_budget_ms=900,
    )

    assert decision.target_level == 1
    assert decision.budget_ms == 1200
