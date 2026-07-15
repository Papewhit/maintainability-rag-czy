from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict


class StageErrorDict(TypedDict):
    stage: str
    error: str
    fallback_to: NotRequired[str]
    error_code: NotRequired[str]
    severity: NotRequired[str]
    recoverable: NotRequired[bool]
    user_visible: NotRequired[bool]


class CandidateTrace(TypedDict, total=False):
    chunk_id: str
    candidate_id: str
    root_chunk_id: str
    anchor_id: str
    filename: str
    section_title: str
    section_path: str
    page_number: int | None
    page_start: int | None
    page_end: int | None
    text_hash: str
    text_preview: str
    index_profile: str
    score: float | None
    raw_rerank_score: float | None
    rerank_score: float | None
    fusion_score: float | None
    final_score: float | None
    doc_scope_match_score: float | None
    filename_boost_applied: bool
    filename_boost_score: float | None


class RetrievalMeta(TypedDict, total=False):
    execution_mode: str
    deep_executed: bool
    plan_applied: bool
    retrieval_mode: str
    pipeline_stage_model: str
    candidate_strategy_requested: str
    candidate_strategy_effective: str
    candidate_strategy_version: str
    candidate_strategy_detail: str
    candidate_strategy_fallback_from: str
    candidate_strategy_warnings: list[str]
    rerank_contract: str
    rerank_contract_version: str
    rerank_execution_mode: str
    postprocess_contract: str
    postprocess_contract_version: str
    candidate_k: int | None
    candidate_count_before_rerank: int
    candidate_count_after_rerank: int
    candidate_count_after_structure_rerank: int
    final_top_k_count: int
    rerank_enabled: bool
    rerank_applied: bool
    rerank_model: str | None
    rerank_error: str | None
    rerank_skipped: bool
    rerank_input_count: int
    rerank_output_count: int
    rerank_ms: float
    rerank_candidate_pool_size: int
    rerank_input_cap: int | None
    rerank_input_device_tier: str | None
    rerank_cache_enabled: bool
    rerank_cache_hit: bool
    auto_merge_enabled: bool
    auto_merge_applied: bool
    auto_merge_replaced_chunks: int
    auto_merge_ms: float
    auto_merge_skipped: bool
    auto_merge_error: str
    step_chain_check_enabled: bool
    step_chain_repaired_groups: list[str]
    step_chain_completion_count: int
    step_chain_ms: float
    step_chain_skipped: bool
    step_chain_error: str
    structure_rerank_enabled: bool
    structure_rerank_applied: bool
    structure_rerank_ms: float
    structure_rerank_skipped: bool
    structure_rerank_error: str
    entity_metadata_score_applied: bool
    entity_type_coverage: float
    entity_match_density: float
    term_matches: list[dict[str, Any]]
    query_plan_enabled: bool
    scope_filter_applied: bool
    strict_scope_filter: bool
    confidence_gate_enabled: bool
    confidence_ms: float
    confidence_gate_skipped: bool
    confidence_error: str
    fallback_required: bool
    confidence_reasons: list[str]
    context_files: list[str]
    candidates_before_rerank: list[CandidateTrace]
    candidates_after_rerank: list[CandidateTrace]
    candidates_after_structure_rerank: list[CandidateTrace]
    timings: dict[str, float]
    stage_errors: list[StageErrorDict]
    extra: dict[str, Any]


class RagTrace(TypedDict, total=False):
    execution_mode: str
    deep_executed: bool
    plan_applied: bool
    tool_used: bool
    tool_name: str
    query: str
    expanded_query: str
    retrieved_chunks: list[dict[str, Any]]
    initial_retrieved_chunks: list[dict[str, Any]]
    expanded_retrieved_chunks: list[dict[str, Any]]
    attached_context_chunks: list[dict[str, Any]]
    attached_context_count: int
    context_files: list[str]
    context_delivery_mode: str
    context_format_version: str
    retrieval_stage: str
    retrieval_mode: str | None
    timings: dict[str, float]
    stage_errors: list[StageErrorDict]
    context_chars: int
    retrieved_chunk_count: int
    final_context_chunk_count: int
    citation_verifier: dict[str, Any]
    rerank_candidate_pool_size: int
    candidate_count_before_rerank: int
    candidate_count_after_rerank: int
    candidate_count_after_structure_rerank: int
    final_top_k_count: int
    rerank_output_count: int
    rerank_ms: float
    rerank_skipped: bool
    auto_merge_enabled: bool
    auto_merge_applied: bool
    auto_merge_replaced_chunks: int
    auto_merge_ms: float
    auto_merge_skipped: bool
    auto_merge_error: str
    step_chain_check_enabled: bool
    step_chain_repaired_groups: list[str]
    step_chain_completion_count: int
    step_chain_ms: float
    step_chain_skipped: bool
    step_chain_error: str
    structure_rerank_applied: bool
    structure_rerank_ms: float
    structure_rerank_skipped: bool
    structure_rerank_error: str
    entity_metadata_score_applied: bool
    entity_type_coverage: float
    entity_match_density: float
    term_matches: list[dict[str, Any]]
    query_plan_enabled: bool
    scope_filter_applied: bool
    strict_scope_filter: bool
    confidence_gate_enabled: bool
    confidence_ms: float
    confidence_gate_skipped: bool
    confidence_error: str
    fallback_required: bool
    confidence_reasons: list[str]


@dataclass(frozen=True)
class StageError:
    stage: str
    error: str
    fallback_to: str | None = None
    error_code: str | None = None
    severity: str = "warning"
    recoverable: bool = True
    user_visible: bool = False

    def as_dict(self) -> StageErrorDict:
        payload: StageErrorDict = {
            "stage": self.stage,
            "error": self.error,
            "severity": self.severity,
            "recoverable": self.recoverable,
            "user_visible": self.user_visible,
        }
        if self.fallback_to:
            payload["fallback_to"] = self.fallback_to
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload

