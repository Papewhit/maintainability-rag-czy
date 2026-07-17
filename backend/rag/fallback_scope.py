"""Pure Level 2 scope and candidate-parameter relaxation rules."""
from __future__ import annotations

import math
from dataclasses import replace

from backend.rag.query_plan import (
    ComprehensiveQueryPlan,
    IntentQueryPlan,
    PreciseQueryPlan,
)


def relax_scope(query_plan: IntentQueryPlan) -> IntentQueryPlan:
    """Relax only a soft document preference; hard filters are immutable."""
    if isinstance(query_plan, PreciseQueryPlan):
        if query_plan.scope_mode != "boost":
            return query_plan
        return replace(
            query_plan,
            scope_mode="none",
            matched_files=(),
            route="global_hybrid",
        )

    if not isinstance(query_plan, ComprehensiveQueryPlan):
        raise TypeError("relax_scope requires a typed intent query plan")
    scope = query_plan.retrieval_scope
    if scope.scope_mode != "boost":
        return query_plan
    return replace(
        query_plan,
        retrieval_scope=replace(
            scope,
            scope_mode="none",
            matched_files=(),
        ),
    )


def level2_candidate_k(current_candidate_k: int, max_candidate_k: int) -> int:
    """Grow the current candidate count by 1.5x without crossing the legacy cap."""
    return min(max_candidate_k, math.ceil(current_candidate_k * 1.5))


def level2_same_root_cap(current_same_root_cap: int) -> int:
    """Allow one additional final candidate from the same root for this round."""
    return current_same_root_cap + 1
