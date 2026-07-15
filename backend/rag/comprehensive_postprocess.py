from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

from backend.rag.query_plan import (
    ComprehensiveQueryPlan,
    ComprehensiveRetrievalBranch,
)
from backend.rag.trace import candidate_identity


RerankFn = Callable[..., tuple[list[dict], dict[str, Any]]]
StageFn = Callable[[list[dict], int], tuple[list[dict], dict[str, Any]]]
ConfidenceFn = Callable[[str, list[dict]], dict[str, Any]]


@dataclass(frozen=True)
class BranchRetrievalResult:
    branch: ComprehensiveRetrievalBranch
    candidates: tuple[dict, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class BranchBudget:
    output_candidates: int = 0
    pairs: int = 0


class BudgetAllocationPolicy(Protocol):
    strategy_id: str

    def allocate(
        self,
        branch_results: Sequence[BranchRetrievalResult],
        *,
        output_candidate_budget: int,
        pair_budget: int,
    ) -> dict[str, BranchBudget]: ...


class BranchRerankPolicy(Protocol):
    strategy_id: str
    uses_crossencoder_pairs: bool

    def rerank(
        self,
        result: BranchRetrievalResult,
        budget: BranchBudget,
        *,
        rerank_fn: RerankFn,
    ) -> BranchRetrievalResult: ...


class CrossQueryMergePolicy(Protocol):
    strategy_id: str

    def merge(
        self,
        branch_results: Sequence[BranchRetrievalResult],
        *,
        rrf_k: int,
    ) -> tuple[list[dict], dict[str, Any]]: ...


class FinalSelectionPolicy(Protocol):
    strategy_id: str

    def select(
        self,
        docs: Sequence[dict],
        *,
        branches: Sequence[ComprehensiveRetrievalBranch],
        successful_generated_branch_ids: set[str],
        top_k: int,
    ) -> tuple[list[dict], dict[str, Any]]: ...


class PriorityBudgetAllocator:
    strategy_id = "priority_shared_budget_v1"

    @staticmethod
    def _allocate_one(
        results: Sequence[BranchRetrievalResult],
        budget: int,
    ) -> dict[str, int]:
        allocations = {item.branch.branch_id: 0 for item in results}
        eligible = [item for item in results if item.candidates]
        remaining = max(0, int(budget))
        ordered = sorted(eligible, key=lambda item: (item.branch.priority, item.branch.branch_id))

        for item in ordered:
            if remaining <= 0:
                break
            allocations[item.branch.branch_id] += 1
            remaining -= 1

        weighted_order = [
            item
            for item in ordered
            for _ in range(4 - item.branch.priority)
        ]
        while remaining > 0 and weighted_order:
            progressed = False
            for item in weighted_order:
                branch_id = item.branch.branch_id
                if allocations[branch_id] >= len(item.candidates):
                    continue
                allocations[branch_id] += 1
                remaining -= 1
                progressed = True
                if remaining <= 0:
                    break
            if not progressed:
                break
        return allocations

    def allocate(
        self,
        branch_results: Sequence[BranchRetrievalResult],
        *,
        output_candidate_budget: int,
        pair_budget: int,
    ) -> dict[str, BranchBudget]:
        outputs = self._allocate_one(branch_results, output_candidate_budget)
        pairs = self._allocate_one(branch_results, pair_budget)
        return {
            item.branch.branch_id: BranchBudget(
                output_candidates=outputs[item.branch.branch_id],
                pairs=pairs[item.branch.branch_id],
            )
            for item in branch_results
        }


class CrossEncoderLocalReranker:
    strategy_id = "crossencoder_local_v1"
    uses_crossencoder_pairs = True

    def rerank(
        self,
        result: BranchRetrievalResult,
        budget: BranchBudget,
        *,
        rerank_fn: RerankFn,
    ) -> BranchRetrievalResult:
        if not result.candidates:
            meta = {
                **result.meta,
                "branch_rerank_budget_exhausted": False,
                "allocated_output_budget": budget.output_candidates,
                "allocated_pair_budget": budget.pairs,
                "used_output_budget": 0,
                "used_pair_budget": 0,
            }
            return BranchRetrievalResult(result.branch, (), meta, result.error)

        local_rank_candidates = tuple(result.candidates[: max(0, budget.output_candidates)])
        if budget.output_candidates <= 0 or budget.pairs <= 0:
            meta = {
                **result.meta,
                "branch_rerank_budget_exhausted": True,
                "allocated_output_budget": budget.output_candidates,
                "allocated_pair_budget": budget.pairs,
                "used_output_budget": len(local_rank_candidates),
                "used_pair_budget": 0,
            }
            return BranchRetrievalResult(
                result.branch,
                local_rank_candidates,
                meta,
                result.error,
            )

        pair_docs = list(result.candidates[: budget.pairs])
        term_matches = list(result.meta.get("term_matches") or [])
        try:
            reranked, rerank_meta = rerank_fn(
                query=result.branch.query,
                docs=pair_docs,
                top_k=budget.output_candidates,
                query_term_matches=term_matches,
            )
            reranked = list(reranked[: budget.output_candidates])
            meta = {
                **result.meta,
                **rerank_meta,
                "branch_rerank_budget_exhausted": False,
                "allocated_output_budget": budget.output_candidates,
                "allocated_pair_budget": budget.pairs,
                "used_output_budget": len(reranked),
                "used_pair_budget": int(rerank_meta.get("rerank_input_count") or 0),
            }
            return BranchRetrievalResult(result.branch, tuple(reranked), meta, result.error)
        except Exception as exc:
            meta = {
                **result.meta,
                "branch_rerank_budget_exhausted": False,
                "allocated_output_budget": budget.output_candidates,
                "allocated_pair_budget": budget.pairs,
                "used_output_budget": len(local_rank_candidates),
                "used_pair_budget": len(pair_docs),
                "rerank_error": str(exc),
            }
            return BranchRetrievalResult(
                result.branch,
                local_rank_candidates,
                meta,
                str(exc),
            )


class MilvusRankOnlyReranker:
    strategy_id = "milvus_rank_only_v1"
    uses_crossencoder_pairs = False

    def rerank(
        self,
        result: BranchRetrievalResult,
        budget: BranchBudget,
        *,
        rerank_fn: RerankFn,
    ) -> BranchRetrievalResult:
        del rerank_fn
        limit = budget.output_candidates
        candidates = result.candidates[: max(0, limit)]
        meta = {
            **result.meta,
            "branch_rerank_budget_exhausted": limit <= 0 and bool(result.candidates),
            "allocated_output_budget": limit,
            "allocated_pair_budget": 0,
            "used_output_budget": len(candidates),
            "used_pair_budget": 0,
            "rerank_applied": False,
        }
        return BranchRetrievalResult(result.branch, tuple(candidates), meta, result.error)


def _branch_weight(branch: ComprehensiveRetrievalBranch) -> float:
    return float(4 - branch.priority)


class PriorityWeightedRRFMerger:
    strategy_id = "priority_weighted_rrf_v1"

    def merge(
        self,
        branch_results: Sequence[BranchRetrievalResult],
        *,
        rrf_k: int,
    ) -> tuple[list[dict], dict[str, Any]]:
        by_id: dict[str, dict] = {}
        source_count = 0
        for result in branch_results:
            for local_rank, source in enumerate(result.candidates, 1):
                source_count += 1
                identity = candidate_identity(source)
                merged = by_id.setdefault(
                    identity,
                    {
                        **source,
                        "matched_branch_ids": [],
                        "per_branch_local_rank": {},
                        "per_branch_rerank_score": {},
                        "multi_query_rrf_score": 0.0,
                        "baseline_matched": False,
                    },
                )
                branch_id = result.branch.branch_id
                if branch_id not in merged["matched_branch_ids"]:
                    merged["matched_branch_ids"].append(branch_id)
                merged["per_branch_local_rank"][branch_id] = local_rank
                if source.get("rerank_score") is not None:
                    merged["per_branch_rerank_score"][branch_id] = float(source["rerank_score"])
                merged["multi_query_rrf_score"] += _branch_weight(result.branch) / (max(1, rrf_k) + local_rank)
                merged["baseline_matched"] = merged["baseline_matched"] or result.branch.branch_kind == "baseline"

        for item in by_id.values():
            item["matched_branch_ids"] = sorted(item["matched_branch_ids"])
            item["best_local_rank"] = min(item["per_branch_local_rank"].values())
            item["coverage_count"] = sum(
                1 for branch_id in item["matched_branch_ids"] if branch_id != "baseline"
            )
            item["rerank_score"] = item["multi_query_rrf_score"]

        merged_docs = sorted(
            by_id.values(),
            key=lambda item: (-float(item["multi_query_rrf_score"]), candidate_identity(item)),
        )
        return merged_docs, {
            "branch_candidate_count": source_count,
            "merged_unique_candidate_count": len(merged_docs),
            "deduplicated_candidate_count": source_count - len(merged_docs),
        }


def complete_merge_trace(merged: Sequence[dict], meta: dict[str, Any]) -> dict[str, Any]:
    """Return complete success telemetry for the multi-query merge stage."""
    return {
        **meta,
        "merged_candidate_count": len(merged),
        "multi_query_merge_skipped": False,
    }


def merge_failure_fallback(
    branch_results: Sequence[BranchRetrievalResult],
    error: Exception,
) -> tuple[list[dict], dict[str, Any]]:
    """Preserve branch candidates and all knowable counts after merge failure."""
    merged = [dict(doc) for result in branch_results for doc in result.candidates]
    unique_count = len({candidate_identity(doc) for doc in merged})
    message = str(error)
    return merged, {
        "merge_error": message,
        "multi_query_merge_error": message,
        "multi_query_merge_skipped": True,
        "branch_candidate_count": len(merged),
        "merged_candidate_count": len(merged),
        "merged_unique_candidate_count": unique_count,
        "deduplicated_candidate_count": 0,
    }


class BranchAwareSelector:
    strategy_id = "generated_branch_reservation_v1"

    def select(
        self,
        docs: Sequence[dict],
        *,
        branches: Sequence[ComprehensiveRetrievalBranch],
        successful_generated_branch_ids: set[str],
        top_k: int,
    ) -> tuple[list[dict], dict[str, Any]]:
        limit = max(0, int(top_k))
        branch_map = {branch.branch_id: branch for branch in branches}
        ordered_generated = sorted(
            successful_generated_branch_ids,
            key=lambda branch_id: (branch_map[branch_id].priority, branch_id),
        )
        reserved: list[dict] = []
        reserved_ids: set[str] = set()
        for branch_id in ordered_generated:
            candidate = next(
                (doc for doc in docs if branch_id in set(doc.get("matched_branch_ids") or [])),
                None,
            )
            if candidate is None:
                continue
            identity = candidate_identity(candidate)
            if identity not in reserved_ids and len(reserved) < limit:
                reserved.append(candidate)
                reserved_ids.add(identity)
            if len(reserved) >= limit:
                break

        selected = list(reserved)
        for doc in docs:
            if len(selected) >= limit:
                break
            identity = candidate_identity(doc)
            if identity in reserved_ids:
                continue
            selected.append(doc)
            reserved_ids.add(identity)

        global_order = {candidate_identity(doc): index for index, doc in enumerate(docs)}
        selected.sort(key=lambda doc: global_order.get(candidate_identity(doc), len(global_order)))

        represented = sorted(
            {
                branch_id
                for doc in selected
                for branch_id in doc.get("matched_branch_ids") or []
                if branch_id in successful_generated_branch_ids
            }
        )
        baseline_selected = any(bool(doc.get("baseline_matched")) for doc in selected)
        return selected, {
            "successful_generated_branch_ids": ordered_generated,
            "represented_generated_branch_ids": represented,
            "generated_branch_representation_count": len(represented),
            "baseline_selected": baseline_selected,
            "final_candidate_count": len(selected),
        }


@dataclass(frozen=True)
class ComprehensivePostprocessPolicy:
    profile_id: str
    version: str
    shared_postprocess_version: str
    budget_allocator: BudgetAllocationPolicy
    branch_reranker: BranchRerankPolicy
    merger: CrossQueryMergePolicy
    final_selector: FinalSelectionPolicy
    budget_strategy_id: str
    branch_rerank_strategy_id: str
    merge_strategy_id: str
    final_selection_strategy_id: str

    def __post_init__(self) -> None:
        expected = (
            (self.budget_strategy_id, self.budget_allocator.strategy_id),
            (self.branch_rerank_strategy_id, self.branch_reranker.strategy_id),
            (self.merge_strategy_id, self.merger.strategy_id),
            (self.final_selection_strategy_id, self.final_selector.strategy_id),
        )
        if (
            not self.profile_id.strip()
            or not self.version.strip()
            or not self.shared_postprocess_version.strip()
        ):
            raise ValueError("comprehensive policy profile and version must not be empty")
        if any(declared != actual for declared, actual in expected):
            raise ValueError("comprehensive policy strategy id does not match implementation")


@dataclass(frozen=True)
class ComprehensivePolicyResolution:
    requested_profile: str
    effective_profile: str
    policy: ComprehensivePostprocessPolicy
    warning: str | None = None


def _policy(profile_id: str, branch_reranker: BranchRerankPolicy) -> ComprehensivePostprocessPolicy:
    allocator = PriorityBudgetAllocator()
    merger = PriorityWeightedRRFMerger()
    selector = BranchAwareSelector()
    return ComprehensivePostprocessPolicy(
        profile_id=profile_id,
        version="v1",
        shared_postprocess_version="shared-postprocess-v1",
        budget_allocator=allocator,
        branch_reranker=branch_reranker,
        merger=merger,
        final_selector=selector,
        budget_strategy_id=allocator.strategy_id,
        branch_rerank_strategy_id=branch_reranker.strategy_id,
        merge_strategy_id=merger.strategy_id,
        final_selection_strategy_id=selector.strategy_id,
    )


_PROFILE_REGISTRY = {
    "quality_first_v1": _policy("quality_first_v1", CrossEncoderLocalReranker()),
    "eval_no_crossencoder_v1": _policy("eval_no_crossencoder_v1", MilvusRankOnlyReranker()),
}


def resolve_comprehensive_postprocess_policy(requested_profile: str | None) -> ComprehensivePolicyResolution:
    requested = (requested_profile or "quality_first_v1").strip() or "quality_first_v1"
    policy = _PROFILE_REGISTRY.get(requested)
    if policy is not None:
        return ComprehensivePolicyResolution(requested, requested, policy)
    fallback = _PROFILE_REGISTRY["quality_first_v1"]
    return ComprehensivePolicyResolution(
        requested_profile=requested,
        effective_profile=fallback.profile_id,
        policy=fallback,
        warning=f"unknown comprehensive postprocess profile: {requested}",
    )


def build_retrieval_branches(plan: ComprehensiveQueryPlan) -> list[ComprehensiveRetrievalBranch]:
    branches = [ComprehensiveRetrievalBranch.baseline(plan.clean_query)]
    branches.extend(
        ComprehensiveRetrievalBranch.from_sub_query(sub_query, index=index)
        for index, sub_query in enumerate(plan.sub_queries)
    )
    return branches


def run_branch_rerank(
    policy: ComprehensivePostprocessPolicy,
    branch_results: Sequence[BranchRetrievalResult],
    *,
    output_candidate_budget: int,
    pair_budget: int,
    rerank_fn: RerankFn,
) -> tuple[list[BranchRetrievalResult], dict[str, Any]]:
    allocations = policy.budget_allocator.allocate(
        branch_results,
        output_candidate_budget=output_candidate_budget,
        pair_budget=pair_budget if policy.branch_reranker.uses_crossencoder_pairs else 0,
    )
    results = [
        policy.branch_reranker.rerank(
            result,
            allocations[result.branch.branch_id],
            rerank_fn=rerank_fn,
        )
        for result in branch_results
    ]
    diagnostics = []
    branch_errors = []
    for result in results:
        item = {
            "branch_id": result.branch.branch_id,
            "branch_kind": result.branch.branch_kind,
            "priority": result.branch.priority,
            "candidate_count": len(result.candidates),
            "top_local_rank": 1 if result.candidates else None,
            "top_rerank_score": (
                result.candidates[0].get("rerank_score") if result.candidates else None
            ),
            "allocated_output_budget": result.meta.get("allocated_output_budget", 0),
            "used_output_budget": result.meta.get("used_output_budget", 0),
            "allocated_pair_budget": result.meta.get("allocated_pair_budget", 0),
            "used_pair_budget": result.meta.get("used_pair_budget", 0),
            "branch_rerank_budget_exhausted": bool(result.meta.get("branch_rerank_budget_exhausted")),
            "error": result.error,
        }
        diagnostics.append(item)
        if result.error:
            branch_errors.append({
                "branch_id": result.branch.branch_id,
                "branch_kind": result.branch.branch_kind,
                "error": result.error,
            })
    return results, {
        "branch_diagnostics": diagnostics,
        "branch_errors": branch_errors,
        "allocated_output_budget": sum(
            int(item.meta.get("allocated_output_budget") or 0) for item in results
        ),
        "allocated_pair_budget": sum(
            int(item.meta.get("allocated_pair_budget") or 0) for item in results
        ),
        "used_output_budget": sum(int(item.meta.get("used_output_budget") or 0) for item in results),
        "used_pair_budget": sum(int(item.meta.get("used_pair_budget") or 0) for item in results),
        "rerank_pair_count": sum(int(item.meta.get("used_pair_budget") or 0) for item in results),
        "rerank_budget_exhausted": any(
            bool(item.meta.get("branch_rerank_budget_exhausted")) for item in results
        ),
    }


def merge_branch_results(
    branch_results: Sequence[BranchRetrievalResult],
    *,
    rrf_k: int,
) -> tuple[list[dict], dict[str, Any]]:
    return PriorityWeightedRRFMerger().merge(branch_results, rrf_k=rrf_k)


def select_branch_aware_top_k(
    docs: Sequence[dict],
    *,
    branches: Sequence[ComprehensiveRetrievalBranch],
    successful_generated_branch_ids: set[str],
    top_k: int,
) -> tuple[list[dict], dict[str, Any]]:
    return BranchAwareSelector().select(
        docs,
        branches=branches,
        successful_generated_branch_ids=successful_generated_branch_ids,
        top_k=top_k,
    )


def _inherit_parent_provenance(before: Sequence[dict], after: Sequence[dict]) -> list[dict]:
    result: list[dict] = []
    for source in after:
        item = dict(source)
        chunk_id = str(item.get("chunk_id") or "")
        contributors = [
            doc
            for doc in before
            if candidate_identity(doc) == candidate_identity(item)
            or (chunk_id and str(doc.get("parent_chunk_id") or "") == chunk_id)
        ]
        if not contributors:
            result.append(item)
            continue
        branch_ids = sorted({branch_id for doc in contributors for branch_id in doc.get("matched_branch_ids") or []})
        ranks: dict[str, int] = {}
        scores: dict[str, float] = {}
        for doc in contributors:
            for branch_id, rank in (doc.get("per_branch_local_rank") or {}).items():
                next_rank = int(rank)
                current_rank = ranks.get(branch_id)
                if current_rank is None or next_rank < current_rank:
                    ranks[branch_id] = next_rank
                    if branch_id in (doc.get("per_branch_rerank_score") or {}):
                        scores[branch_id] = float(doc["per_branch_rerank_score"][branch_id])
        item.update({
            "matched_branch_ids": branch_ids,
            "per_branch_local_rank": ranks,
            "per_branch_rerank_score": scores,
            "best_local_rank": min(ranks.values()) if ranks else None,
            "baseline_matched": any(bool(doc.get("baseline_matched")) for doc in contributors),
            "coverage_count": sum(1 for branch_id in branch_ids if branch_id != "baseline"),
        })
        result.append(item)
    return result


def run_shared_postprocess(
    policy: ComprehensivePostprocessPolicy,
    plan: ComprehensiveQueryPlan,
    branch_results: Sequence[BranchRetrievalResult],
    *,
    top_k: int,
    auto_merge_fn: StageFn,
    step_chain_fn: StageFn,
    structure_rerank_fn: StageFn,
    confidence_fn: ConfidenceFn,
    rrf_k: int = 60,
    premerged: tuple[Sequence[dict], dict[str, Any]] | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    stage_errors: list[dict[str, Any]] = []
    timings: dict[str, float] = {}
    if premerged is not None:
        merged = [dict(doc) for doc in premerged[0]]
        merge_meta = dict(premerged[1])
    else:
        merge_started = time.perf_counter()
        try:
            merged, merge_meta = policy.merger.merge(branch_results, rrf_k=rrf_k)
            merge_meta = complete_merge_trace(merged, merge_meta)
        except Exception as exc:
            merged, merge_meta = merge_failure_fallback(branch_results, exc)
            stage_errors.append({"stage": "multi_query_merge", "error": str(exc)})
        timings["multi_query_merge_ms"] = (time.perf_counter() - merge_started) * 1000.0

    stage_limit = max(len(merged), top_k)
    auto_started = time.perf_counter()
    try:
        auto_merged, auto_meta = auto_merge_fn(merged, stage_limit)
        auto_merged = _inherit_parent_provenance(merged, auto_merged)
        auto_meta = {**auto_meta, "auto_merge_skipped": False}
    except Exception as exc:
        auto_merged, auto_meta = merged, {
            "auto_merge_error": str(exc),
            "auto_merge_skipped": True,
        }
        stage_errors.append({"stage": "auto_merge", "error": str(exc)})
    timings["auto_merge_ms"] = (time.perf_counter() - auto_started) * 1000.0

    step_started = time.perf_counter()
    try:
        repaired, step_meta = step_chain_fn(auto_merged, max(len(auto_merged), top_k))
        step_meta = {**step_meta, "step_chain_skipped": False}
    except Exception as exc:
        repaired, step_meta = auto_merged, {
            "step_chain_error": str(exc),
            "step_chain_skipped": True,
        }
        stage_errors.append({"stage": "step_chain", "error": str(exc)})
    timings["step_chain_ms"] = (time.perf_counter() - step_started) * 1000.0

    structure_started = time.perf_counter()
    try:
        structured, structure_meta = structure_rerank_fn(repaired, max(len(repaired), top_k))
        structure_meta = {**structure_meta, "structure_rerank_skipped": False}
    except Exception as exc:
        structured, structure_meta = repaired, {
            "structure_rerank_error": str(exc),
            "structure_rerank_skipped": True,
        }
        stage_errors.append({"stage": "structure_rerank", "error": str(exc)})
    timings["structure_rerank_ms"] = (time.perf_counter() - structure_started) * 1000.0

    branches = [result.branch for result in branch_results]
    successful_generated = {
        result.branch.branch_id
        for result in branch_results
        if result.branch.branch_kind == "sub_query" and result.candidates
    }
    selection_pool = list(structured)
    represented_after_structure = {
        branch_id
        for doc in structured
        for branch_id in doc.get("matched_branch_ids") or []
        if branch_id in successful_generated
    }
    branch_map = {branch.branch_id: branch for branch in branches}
    restored_branch_ids: list[str] = []
    selection_identities = {candidate_identity(doc) for doc in selection_pool}
    for branch_id in sorted(
        successful_generated - represented_after_structure,
        key=lambda item: (branch_map[item].priority, item),
    ):
        candidate = next(
            (doc for doc in repaired if branch_id in set(doc.get("matched_branch_ids") or [])),
            None,
        )
        if candidate is None:
            continue
        identity = candidate_identity(candidate)
        if identity not in selection_identities:
            selection_pool.append(candidate)
            selection_identities.add(identity)
        restored_branch_ids.append(branch_id)

    selection_started = time.perf_counter()
    try:
        selected, selection_meta = policy.final_selector.select(
            selection_pool,
            branches=branches,
            successful_generated_branch_ids=successful_generated,
            top_k=top_k,
        )
        selection_meta = {**selection_meta, "final_selection_skipped": False}
    except Exception as exc:
        selected = list(structured[: max(0, int(top_k))])
        if not selected:
            selected = list(selection_pool[: max(0, int(top_k))])
        represented = sorted({
            branch_id
            for doc in selected
            for branch_id in doc.get("matched_branch_ids") or []
            if branch_id in successful_generated
        })
        selection_meta = {
            "final_selection_error": str(exc),
            "final_selection_skipped": True,
            "successful_generated_branch_ids": sorted(successful_generated),
            "represented_generated_branch_ids": represented,
            "generated_branch_representation_count": len(represented),
            "baseline_selected": any(bool(doc.get("baseline_matched")) for doc in selected),
            "final_candidate_count": len(selected),
        }
        stage_errors.append({"stage": "final_selection", "error": str(exc)})
    timings["final_selection_ms"] = (time.perf_counter() - selection_started) * 1000.0
    selection_meta["structure_reservation_restored_branch_ids"] = restored_branch_ids

    planned_generated = {
        result.branch.branch_id
        for result in branch_results
        if result.branch.branch_kind == "sub_query"
    }
    represented_generated = set(selection_meta.get("represented_generated_branch_ids") or [])
    failed_generated = {
        result.branch.branch_id
        for result in branch_results
        if result.branch.branch_kind == "sub_query" and result.error and not result.candidates
    }
    missing_generated = successful_generated - represented_generated
    confidence_started = time.perf_counter()
    try:
        confidence_meta = confidence_fn(plan.clean_query, selected)
        confidence_meta = {**confidence_meta, "confidence_gate_skipped": False}
    except Exception as exc:
        confidence_meta = {
            "confidence_error": str(exc),
            "confidence_gate_skipped": True,
            "fallback_required": False,
        }
        stage_errors.append({"stage": "confidence", "error": str(exc)})
    timings["confidence_ms"] = (time.perf_counter() - confidence_started) * 1000.0
    confidence_reasons = list(confidence_meta.get("confidence_reasons") or [])
    if confidence_meta.get("confidence_gate_enabled"):
        if failed_generated:
            confidence_reasons.append("generated_branch_failure")
        if missing_generated:
            confidence_reasons.append("missing_generated_branch_representation")
        if failed_generated or missing_generated:
            confidence_meta["fallback_required"] = True
    confidence_meta["confidence_reasons"] = list(dict.fromkeys(confidence_reasons))
    confidence_meta["comprehensive_confidence_inputs"] = {
        "planned_generated_branch_ids": sorted(planned_generated),
        "successful_generated_branch_ids": sorted(successful_generated),
        "represented_generated_branch_ids": sorted(represented_generated),
        "failed_generated_branch_ids": sorted(failed_generated),
        "missing_generated_branch_ids": sorted(missing_generated),
        "baseline_hit": any(
            result.branch.branch_kind == "baseline" and bool(result.candidates)
            for result in branch_results
        ),
    }

    trace = {
        "comprehensive_postprocess_profile": policy.profile_id,
        "comprehensive_policy_version": policy.version,
        "shared_postprocess_version": policy.shared_postprocess_version,
        "postprocess_contract": "comprehensive_retrieval_postprocess",
        "postprocess_contract_version": policy.shared_postprocess_version,
        "budget_strategy_id": policy.budget_strategy_id,
        "branch_rerank_strategy_id": policy.branch_rerank_strategy_id,
        "merge_strategy_id": policy.merge_strategy_id,
        "final_selection_strategy_id": policy.final_selection_strategy_id,
        "shared_postprocess_count": 1,
        "baseline_matched": any(bool(doc.get("baseline_matched")) for doc in merged),
        "timings": timings,
        "stage_errors": stage_errors,
        **merge_meta,
        **auto_meta,
        **step_meta,
        **structure_meta,
        **selection_meta,
        **confidence_meta,
    }
    return selected, trace
