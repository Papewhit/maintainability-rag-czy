### Prior Findings Follow-Up

| Prior Issue | Status | Evidence |
| --- | --- | --- |
| Full OpenSpec change incomplete | Still Present | M6-M7 remain unchecked in [tasks.md](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/openspec/changes/rag-maintainability-chunker/tasks.md:79). |
| Profile gating missing | Fixed | `v4_step_protection` table probe now emits `[]`; table loop is skipped below `v4_table_aware` in [converters.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/converters.py:75). |
| Table chunk contract incomplete | Partially Fixed, Still Present | Caption and row splitting exist, but table nearby explanatory blocks are still not included. |
| Parse metadata persistence absent | Still Present | `document_parse_meta` table/API are still unchecked M6 tasks. |
| Table validation warnings discarded | Still Present | Warnings are logged but not written to `parse_meta.parse_warnings`. |
| New Milvus fields not surfaced downstream | Still Present | Candidate trace/downstream scoring still largely ignore the new structural and terminology fields. |
| Missing parameter-table ranking test | Still Present | No dedicated ranking-boost test found. |
| M5 terminology tests fail due missing models/integration | Partially Fixed, Still Present | DB models were added, but terminology tests were deleted and scoped mypy still fails. |

## OpenSpec Verification Report: `rag-maintainability-chunker`

**Result:** Failed.

No repository `AGENTS.md` exists in this worktree. I followed the prompt-provided AGENTS shell guidance, `CLAUDE.md`, previous report, OpenSpec artifacts, code, tests, and diffs as authoritative evidence.

### Critical Findings

1. **M5 is marked complete but no longer has its own tests in the tree.**  
   The latest commit deletes `tests/test_terminology_m*.py`, `tests/test_terminology_integration.py`, and `tests/test_terminology_rescan_regression.py`. Task 6.5 says terminology chunk metadata is tested, but only a generic dataclass test remains. The previous failing tests are gone, not fixed.

2. **Scoped mypy still fails.**  
   `uv run mypy backend/documents/parse_adapter/ backend/documents/normalizer/ backend/documents/chunker/ --ignore-missing-imports` fails with 18 errors, mainly SQLAlchemy `Base` typing in `models.py` and invalid key types in `backend/rag/terminology/table.py`.

3. **M5 ParentChunkStore persistence is not implemented correctly.**  
   `_scan_terminology_on_chunks()` writes top-level `term_matches` / `protected_tokens`, but `ParentChunkStore._payload_from_doc()` ignores those fields and only persists `parent_extras`: [parent_chunk_store.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/infra/vector_store/parent_chunk_store.py:53). `ParentChunk` also has no `term_matches` or `protected_tokens` columns, while `rescan.py` references `ParentChunk.term_matches` and `ParentChunk.protected_tokens`, which will fail at runtime.

4. **M6-M7 remain incomplete.**  
   Parse metadata persistence/admin API and soft-boundary cleanup remain unchecked and required by the OpenSpec artifacts.

### Warnings

- Table parent chunks still omit nearby explanatory blocks.
- Table validation warnings are not attached to parse metadata.
- OCR confidence and `parse_path="native_text"` remain unimplemented for parsing scenarios.
- Parameter-table ranking boost still lacks test coverage.
- The synced `openspec/specs/rag-terminology-module/spec.md` describes admin terminology APIs, but `backend/routers/admin_terminology.py` was deleted in the latest commit.

### Verification Evidence

Passed:

- `openspec validate rag-maintainability-chunker --strict`
- `uv run pytest tests/test_normalizer/ tests/test_chunker/ tests/test_parse_adapter/ tests/test_document_service.py -q`  
  Result: 105 passed, 1 warning
- `uv run pytest tests/test_application_entrypoints.py tests/test_api_routes.py tests/test_document_service.py tests/test_rag_pipeline.py -q`  
  Result: 18 passed, 1 warning
- `uv run python -m compileall backend tests`
- Targeted probe: `RAG_INDEX_PROFILE=v4_step_protection` with a table emits no chunks.
- Targeted probe: `v4_full` leaf chunk gets terminology metadata when a loaded `TerminologyTable` is injected.

Failed / not runnable:

- Previous terminology test command now fails because the test files were deleted.
- Scoped mypy on document modules fails with 18 errors.

**Conclusion:** The table profile-gating blocker is fixed, but verification still fails. The current blockers are M5’s unverified/partially wired terminology persistence, failing scoped mypy, and pending M6-M7 requirements.