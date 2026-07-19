from pydantic import BaseModel
from typing import Any, Dict, Optional, List


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: Optional[str] = "user"
    admin_code: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class CurrentUserResponse(BaseModel):
    username: str
    role: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default_session"
    regenerate: Optional[bool] = False
    context_files: Optional[List[str]] = None


class RetrievedChunk(BaseModel):
    filename: str
    page_number: Optional[str | int] = None
    text: Optional[str] = None
    score: Optional[float] = None
    rrf_rank: Optional[int] = None
    rerank_score: Optional[float] = None
    matched_branch_ids: Optional[List[str]] = None
    per_branch_local_rank: Optional[Dict[str, int]] = None
    per_branch_rerank_score: Optional[Dict[str, float]] = None
    best_local_rank: Optional[int] = None
    baseline_matched: Optional[bool] = None
    coverage_count: Optional[int] = None
    multi_query_rrf_score: Optional[float] = None


class RagTrace(BaseModel):
    tool_used: bool
    tool_name: str
    intent: Optional[str] = None
    intent_confidence: Optional[float] = None
    query_plan_type: Optional[str] = None
    intent_classifier_enabled: Optional[bool] = None
    intent_compatibility_source: Optional[str] = None
    intent_llm_model: Optional[str] = None
    intent_llm_ms: Optional[float] = None
    intent_llm_error: Optional[str] = None
    intent_fallback_to_rules: Optional[bool] = None
    analysis_type: Optional[str] = None
    sub_query_count: Optional[int] = None
    retrieval_branch_count: Optional[int] = None
    requested_sub_query_count: Optional[int] = None
    sub_query_fanout_limit: Optional[int] = None
    sub_query_truncated_count: Optional[int] = None
    sub_queries_truncated: Optional[bool] = None
    truncated_sub_queries: Optional[List[Dict[str, Any]]] = None
    requested_comprehensive_postprocess_profile: Optional[str] = None
    effective_comprehensive_postprocess_profile: Optional[str] = None
    comprehensive_postprocess_profile_warning: Optional[str] = None
    comprehensive_postprocess_profile: Optional[str] = None
    comprehensive_policy_version: Optional[str] = None
    shared_postprocess_version: Optional[str] = None
    postprocess_contract: Optional[str] = None
    postprocess_contract_version: Optional[str] = None
    budget_strategy_id: Optional[str] = None
    branch_rerank_strategy_id: Optional[str] = None
    merge_strategy_id: Optional[str] = None
    final_selection_strategy_id: Optional[str] = None
    branch_retrieval_diagnostics: Optional[List[Dict[str, Any]]] = None
    branch_diagnostics: Optional[List[Dict[str, Any]]] = None
    branch_errors: Optional[List[Dict[str, Any]]] = None
    allocated_output_budget: Optional[int] = None
    used_output_budget: Optional[int] = None
    allocated_pair_budget: Optional[int] = None
    used_pair_budget: Optional[int] = None
    rerank_pair_count: Optional[int] = None
    rerank_budget_exhausted: Optional[bool] = None
    rerank_output_candidate_budget: Optional[int] = None
    rerank_pair_budget_cap: Optional[int] = None
    rerank_pair_device_tier: Optional[str] = None
    dense_embedding_call_count: Optional[int] = None
    sparse_embedding_call_count: Optional[int] = None
    embedding_call_count: Optional[int] = None
    hybrid_search_call_count: Optional[int] = None
    split_search_call_count: Optional[int] = None
    baseline_candidate_count: Optional[int] = None
    baseline_hit: Optional[bool] = None
    baseline_matched: Optional[bool] = None
    baseline_selected: Optional[bool] = None
    shared_postprocess_count: Optional[int] = None
    branch_candidate_count: Optional[int] = None
    merged_candidate_count: Optional[int] = None
    merged_unique_candidate_count: Optional[int] = None
    deduplicated_candidate_count: Optional[int] = None
    multi_query_merge_skipped: Optional[bool] = None
    multi_query_merge_error: Optional[str] = None
    final_candidate_count: Optional[int] = None
    generated_branch_representation_count: Optional[int] = None
    successful_generated_branch_ids: Optional[List[str]] = None
    represented_generated_branch_ids: Optional[List[str]] = None
    structure_reservation_restored_branch_ids: Optional[List[str]] = None
    comprehensive_confidence_inputs: Optional[Dict[str, Any]] = None
    query_plan_enabled: Optional[bool] = None
    scope_filter_applied: Optional[bool] = None
    strict_scope_filter: Optional[bool] = None
    retrieval_scope: Optional[Dict[str, Any]] = None
    query: Optional[str] = None
    semantic_query: Optional[str] = None
    normalized_query: Optional[str] = None
    sparse_expansion: Optional[str] = None
    protected_tokens: Optional[List[str]] = None
    expanded_query: Optional[str] = None
    step_back_question: Optional[str] = None
    step_back_answer: Optional[str] = None
    expansion_type: Optional[str] = None
    hypothetical_doc: Optional[str] = None
    retrieval_stage: Optional[str] = None
    grade_score: Optional[str] = None
    grade_route: Optional[str] = None
    rewrite_needed: Optional[bool] = None
    rewrite_strategy: Optional[str] = None
    rewrite_query: Optional[str] = None
    rerank_enabled: Optional[bool] = None
    rerank_applied: Optional[bool] = None
    rerank_model: Optional[str] = None
    rerank_error: Optional[str] = None
    rerank_skipped: Optional[bool] = None
    hybrid_error: Optional[str] = None
    dense_error: Optional[str] = None
    retrieval_mode: Optional[str] = None
    candidate_k: Optional[int] = None
    rerank_candidate_pool_size: Optional[int] = None
    candidate_count_before_rerank: Optional[int] = None
    candidate_count_after_rerank: Optional[int] = None
    candidate_count_after_structure_rerank: Optional[int] = None
    final_top_k_count: Optional[int] = None
    rerank_output_count: Optional[int] = None
    rerank_ms: Optional[float] = None
    leaf_retrieve_level: Optional[int] = None
    auto_merge_enabled: Optional[bool] = None
    auto_merge_applied: Optional[bool] = None
    auto_merge_threshold: Optional[int] = None
    auto_merge_replaced_chunks: Optional[int] = None
    auto_merge_steps: Optional[int] = None
    auto_merge_ms: Optional[float] = None
    auto_merge_skipped: Optional[bool] = None
    auto_merge_error: Optional[str] = None
    step_chain_check_enabled: Optional[bool] = None
    step_chain_repaired_groups: Optional[List[str]] = None
    step_chain_completion_count: Optional[int] = None
    step_chain_ms: Optional[float] = None
    step_chain_skipped: Optional[bool] = None
    step_chain_error: Optional[str] = None
    structure_rerank_enabled: Optional[bool] = None
    structure_rerank_applied: Optional[bool] = None
    structure_rerank_ms: Optional[float] = None
    structure_rerank_skipped: Optional[bool] = None
    structure_rerank_error: Optional[str] = None
    entity_metadata_score_applied: Optional[bool] = None
    entity_type_coverage: Optional[float] = None
    entity_match_density: Optional[float] = None
    term_matches: Optional[List[Dict[str, Any]]] = None
    confidence_gate_enabled: Optional[bool] = None
    fallback_required: Optional[bool] = None
    confidence_reasons: Optional[List[str]] = None
    confidence_ms: Optional[float] = None
    confidence_gate_skipped: Optional[bool] = None
    confidence_error: Optional[str] = None
    fallback_level: Optional[int] = None
    fallback_signals: Optional[List[str]] = None
    fallback_path: Optional[List[int]] = None
    fallback_decisions: Optional[List[Dict[str, Any]]] = None
    fallback_total_ms: Optional[float] = None
    level1_strategy: Optional[str] = None
    level1_rewritten_query: Optional[str | List[str]] = None
    level1_comprehensive_strategy: Optional[List[str]] = None
    level1_new_sub_queries: Optional[List[Dict[str, Any]]] = None
    level1_sub_query_replaced: Optional[List[str]] = None
    level1_timeout: Optional[bool] = None
    level1_ms: Optional[float] = None
    level2_relaxations: Optional[List[str]] = None
    level2_previous_scope_mode: Optional[str] = None
    level2_new_scope_mode: Optional[str] = None
    level2_ms: Optional[float] = None
    level3_reason: Optional[str] = None
    level3_attempted_levels: Optional[List[int]] = None
    level3_uncovered_sub_queries: Optional[List[str]] = None
    level3_baseline_evidence_used: Optional[bool] = None
    level3_answer: Optional[str] = None
    level3_ms: Optional[float] = None
    timings: Optional[Dict[str, float]] = None
    stage_errors: Optional[List[Dict[str, Any]]] = None
    retrieved_chunks: Optional[List[RetrievedChunk]] = None
    initial_retrieved_chunks: Optional[List[RetrievedChunk]] = None
    expanded_retrieved_chunks: Optional[List[RetrievedChunk]] = None
    attached_context_chunks: Optional[List[RetrievedChunk]] = None
    context_files: Optional[List[str]] = None


class ChatResponse(BaseModel):
    response: str
    rag_trace: Optional[RagTrace] = None


class MessageInfo(BaseModel):
    type: str
    content: str
    timestamp: str
    rag_trace: Optional[RagTrace] = None


class SessionMessagesResponse(BaseModel):
    messages: List[MessageInfo]


class SessionInfo(BaseModel):
    session_id: str
    title: Optional[str] = None
    updated_at: str
    message_count: int


class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]


class SessionDeleteResponse(BaseModel):
    session_id: str
    message: str


class SessionRenameRequest(BaseModel):
    title: str = ""


class SessionRenameResponse(BaseModel):
    session_id: str
    title: Optional[str] = None
    message: str = "已更新标题"


class DocumentInfo(BaseModel):
    filename: str
    file_type: str
    chunk_count: int
    uploaded_at: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: List[DocumentInfo]


class DocumentUploadResponse(BaseModel):
    filename: str
    chunks_processed: int
    message: str


class DocumentDeleteResponse(BaseModel):
    filename: str
    chunks_deleted: int
    message: str
