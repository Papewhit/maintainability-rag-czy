# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Install dependencies
uv sync

# Start infrastructure (PostgreSQL, Redis, Milvus, etcd, MinIO, Attu)
docker compose up -d

# Run the app (two equivalent entry points)
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
uv run python backend/app.py

# Run core tests
uv run pytest tests/test_application_entrypoints.py tests/test_api_routes.py tests/test_document_service.py tests/test_rag_pipeline.py -q

# Run a single test file
uv run pytest tests/test_rag_pipeline.py -q

# Static checks
uv run python -m compileall backend tests
node --check frontend/script.js
node frontend/ui-redesign.test.mjs
```

## Architecture

This is a **RAG (Retrieval-Augmented Generation) Q&A system** for private document knowledge bases. FastAPI backend, static Vue CDN frontend, backed by PostgreSQL + Redis + Milvus + local embedding/reranker models.

### Layer boundaries (top to bottom)

| Layer | Module | Role |
|---|---|---|
| HTTP | `backend/routers/` | auth, chat, sessions, documents endpoints |
| Contracts | `backend/contracts/` | Pydantic request/response schemas |
| Security | `backend/security/` | JWT, PBKDF2 password hashing, admin guard |
| Services | `backend/services/` | Document upload/index/delete orchestration |
| Chat | `backend/chat/` | Agent, tools, RAG execution policy, streaming |
| RAG pipeline | `backend/rag/` | QueryPlan, retrieval, rerank, confidence, trace |
| Infrastructure | `backend/infra/` | DB, Redis cache, embeddings, Milvus, parent chunk store |
| Documents | `backend/documents/` | PDF/Word/Excel parsing, chunking, metadata extraction |

### Request flow (non-streaming chat)

```
POST /chat → JWT check → plan_rag_turn() → determines policy:
  - FORCED_PRELOAD (context_files present or document intent detected):
      run_rag_graph() directly → model.invoke() with context injected as system message
  - OPTIONAL_TOOL (default):
      agent.invoke() → agent may call search_knowledge_base tool → tool runs RAG → agent answers
```

### RAG pipeline (`backend/rag/pipeline.py`)

LangGraph state machine: `retrieve_initial → grade_documents → rewrite_question → retrieve_expanded`.

1. **Hybrid retrieval**: Milvus dense (HNSW) + sparse (BM25 inverted index) with RRF fusion
2. **QueryPlan** (`query_plan.py`): Parses user query for filename hints, model numbers, chapter/page anchors, structural cues. Sets `scope_mode` (filter/boost/global).
3. **CrossEncoder rerank**: `BAAI/bge-reranker-v2-m3`, score fusion combining rerank + RRF + scope + metadata signals
4. **Document relevance grading**: Optional LLM grader → fallback path triggers query expansion (step-back, HyDE)
5. **Context assembly**: Parent chunk, root/section hierarchy, token budget

### Runtime config gear system (`runtime_config.py`)

All RAG behavior is controlled via env vars (no code changes). Key groups:

- **K gear** (candidate strategy): `K1`=baseline, `K2`=QueryPlan+rerank+fusion (default), `K3`=fast
- **I gear** (index profile): `I2`=v3_quality collection
- **M gear** (mode routing): `M0`=off, `M1`=shadow, `M2`=active
- **A gear** (device auto-select): `A1`=GPU-first with CPU fallback

Config is loaded via `load_runtime_config()` → `RagRuntimeConfig` frozen dataclass. All knobs are env-var driven; there's no config file.

### Embedding service (`backend/infra/embedding.py`)

Singleton `EmbeddingService` provides both dense embeddings (HuggingFace `BAAI/bge-m3`) and sparse BM25 embeddings with persistent vocabulary/df state. BM25 state is persisted to JSON and supports incremental add/remove of documents.

### Database (`backend/infra/db/database.py`)

Primary: PostgreSQL (from `DATABASE_URL`). Automatic SQLite fallback on connection failure (`FALLBACK_DATABASE_URL`). Uses SQLAlchemy with `init_db()` called at app startup via lifespan. Models live in `backend/infra/db/models.py`.

### Milvus client (`backend/infra/vector_store/milvus_client.py`)

`MilvusManager` creates a fresh client per operation (no shared long-lived client). Supports `hybrid_retrieve` (dense+sparse RRF), `split_retrieve` (separate dense/sparse scores), and `dense_retrieve`. Automatic reconnect with backoff for recoverable errors (closed channels, connection refused, etc.).

### Document loading (`backend/documents/loader.py`)

Custom `RecursiveCharacterTextSplitter` (avoids langchain_text_splitters import at module load). Two profiles:
- **structured**: Detects headings/chapters/sections, creates hierarchical chunks with section paths
- **generic**: Page-based root+leaf chunking

`retrieval_text` field supports multiple modes (`title_context_filename` is the default eval mode).

### Chat agent (`backend/chat/agent.py`)

Thread-safe singleton agent using LangChain's `create_agent`. Two tools: `search_knowledge_base` (RAG retrieval) and `get_current_weather`. System prompt is extensive and bilingual (Chinese/English). Supports streaming via `chat_with_agent_stream()` with a unified output queue that interleaves content chunks and RAG step events.

### Frontend

Single-page static app in `frontend/` (index.html, script.js, style.css). Uses Vue 3 via CDN. FastAPI serves it as static files at `/`. Has a companion `ui-redesign.test.mjs` for Node-based testing.

## Key Design Decisions

- **No shared Milvus client**: Fresh client per operation to avoid cross-thread invalidation
- **Default M0 mode**: Deep Mode and active routing are off by default; only enabled explicitly
- **RAG trace is always produced**: Every chat response includes a `rag_trace` with candidates, rerank status, errors, and timing - essential for debugging retrieval failures
- **BM25 state is persistent**: Vocabulary and document frequencies survive restarts via JSON file
- **Password hashing**: Custom PBKDF2-SHA256 (not passlib/bcrypt) with backward compatibility for legacy hashes
- **index_profile system**: Different experiment variants can use different Milvus collections and BM25 state files via `RAG_INDEX_PROFILE` while keeping chunk IDs user-facing-consistent

## Project-specific conventions

- Python 3.12+ only; `uv` for package management
- `from __future__ import annotations` in all backend modules
- Env vars are read at module level (not lazily) in `config.py` and `runtime_config.py`
- Tests use pytest; test files that need env var isolation should set them before importing backend modules
- The following directories are local-only (gitignored): `data/`, `docs/`, `eval/`, `scripts/`, `volumes/`
