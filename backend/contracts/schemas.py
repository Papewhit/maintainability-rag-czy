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


class RagTrace(BaseModel):
    tool_used: bool
    tool_name: str
    query: Optional[str] = None
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
    query_entities: Optional[List[Dict[str, Any]]] = None
    confidence_gate_enabled: Optional[bool] = None
    fallback_required: Optional[bool] = None
    confidence_reasons: Optional[List[str]] = None
    confidence_ms: Optional[float] = None
    confidence_gate_skipped: Optional[bool] = None
    confidence_error: Optional[str] = None
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
