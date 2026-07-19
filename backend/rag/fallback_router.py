"""Pure signal-to-level routing for multilevel RAG fallback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.rag.query_plan import ComprehensiveQueryPlan, PreciseQueryPlan


DEFAULT_LEVEL1_BUDGET_MS = 3000
DEFAULT_LEVEL2_BUDGET_MS = 2500


@dataclass(frozen=True)
class FallbackDecision:
    target_level: Literal[0, 1, 2, 3]
    primary_signal: str
    contributing_signals: list[str]
    reason: str
    budget_ms: int


def route_fallback(
    confidence: dict[str, Any],
    query_plan: PreciseQueryPlan | ComprehensiveQueryPlan,
    attempted_levels: list[int],
    remaining_budget_ms: float,
    *,
    level1_budget_ms: int = DEFAULT_LEVEL1_BUDGET_MS,
    level2_budget_ms: int = DEFAULT_LEVEL2_BUDGET_MS,
) -> FallbackDecision:
    """Choose the next non-repeating fallback level without invoking an LLM."""
    del query_plan  # Plan type is consumed by level nodes, not by signal priority.
    reasons = [str(reason) for reason in confidence.get("confidence_reasons", []) if reason]

    if not reasons:
        return FallbackDecision(0, "confidence_sufficient", [], "confidence gate passed", 0)
    if "no_docs" in reasons:
        return FallbackDecision(
            3,
            "no_docs",
            reasons,
            "no_docs detected, retry unlikely to help",
            0,
        )

    attempted = set(attempted_levels)
    if 2 in attempted:
        return FallbackDecision(
            3,
            "levels_exhausted",
            reasons,
            "available fallback levels already attempted",
            0,
        )

    if 1 in attempted:
        target_level = 2
        primary_signal = "level1_exhausted"
        reason = "Level 1 did not restore confidence; broaden eligible candidates"
        required_budget = level2_budget_ms
    elif "anchor_mismatch" in reasons:
        target_level = 1
        primary_signal = "anchor_mismatch"
        reason = "query anchor not matching retrieved chunks"
        required_budget = level1_budget_ms
    elif "weak_margin_and_root" in reasons:
        target_level = 2
        primary_signal = "weak_margin_and_root"
        reason = "results scattered, need broader scope"
        required_budget = level2_budget_ms
    elif "low_score_and_margin" in reasons:
        target_level = 1
        primary_signal = "low_score_and_margin"
        reason = "retrieval query needs reformulation"
        required_budget = level1_budget_ms
    else:
        target_level = 1
        primary_signal = reasons[0]
        reason = "unclassified confidence failure; try query rewrite"
        required_budget = level1_budget_ms

    if remaining_budget_ms < required_budget:
        return FallbackDecision(
            3,
            "budget_exhausted",
            reasons,
            "budget_exhausted",
            0,
        )
    return FallbackDecision(
        target_level,
        primary_signal,
        reasons,
        reason,
        required_budget,
    )
