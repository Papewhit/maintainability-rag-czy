### Prior Findings Follow-Up

| Prior Issue | Status | Evidence |
| --- | --- | --- |
| Full OpenSpec change incomplete | Still Present | M5 is now checked, but M6-M7 remain unchecked in [tasks.md](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/openspec/changes/rag-maintainability-chunker/tasks.md:79). |
| Profile gating missing | Fixed | `v4_step_protection` table probe now emits `[]`; table loop is skipped below `v4_table_aware` in [converters.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/converters.py:75). Figure gating remains in [step_chunker.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/chunker/step_chunker.py:98). |
| Table chunk contract incomplete | Partially Fixed, Still Present | Caption and row splitting exist, but table nearby explanatory blocks still are not assembled into parent text as required by the table parent chunk spec. |
| Parse metadata persistence absent | Still Present | `document_parse_meta` table/API are still unchecked M6 tasks; [models.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/infra/db/models.py:59) still only defines existing core models plus `ParentChunk`. |
| Table validation warnings discarded | Still Present | Warnings are logged, but not recorded in `parse_meta.parse_warnings`: [table_normalizer.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/normalizer/table_normalizer.py:24). |
| New Milvus fields not surfaced downstream | Still Present | Candidate trace still omits structural and terminology fields in `backend/rag/utils.py` candidate tracing. |
| Missing parameter-table ranking test | Still Present | Search found no dedicated ranking-boost test. |

## OpenSpec Verification Report: `rag-maintainability-chunker`

**Result:** Failed.

No repository `AGENTS.md` exists in this worktree. I followed the prompt-provided AGENTS shell guidance, `CLAUDE.md`, current context, previous report, OpenSpec artifacts, code, tests, and diffs as authoritative evidence.

### Critical Findings

1. **M5 is marked complete but terminology tests fail.**  
   The new terminology modules import DB models that do not exist in this branch: `TerminologyEntryModel`, `AuditLog`, and `RescanTaskModel`. Collection fails for `tests/test_terminology_m5.py` and `tests/test_terminology_integration.py`; broader terminology tests fail 19 cases. Evidence: [admin_terminology.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/routers/admin_terminology.py:17), [rescan.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/rag/terminology/rescan.py:22), [table.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/rag/terminology/table.py:94).

2. **M5 integration references missing/nonexistent integration points.**  
   Terminology tests expect `backend.rag.query_plan.terminology_preflight` and `backend.documents.loader._scan_terminology`, but those symbols are absent. This means the synced terminology tests/spec are not integrated with the current code shape.

3. **Scoped mypy now fails.**  
   `uv run mypy backend/documents/parse_adapter/ backend/documents/normalizer/ backend/documents/chunker/ --ignore-missing-imports` fails because `converters.py` imports terminology code, which exposes missing DB model attributes and typing errors in `backend/rag/terminology/table.py`.

4. **Full change remains incomplete.**  
   M6 parse metadata/admin tooling and M7 soft-boundary cleanup remain unchecked while their OpenSpec requirements remain active.

### Warnings

- Table parent chunks still omit nearby explanatory blocks.
- Table validation warnings are not written into parse metadata.
- OCR confidence and `parse_path="native_text"` remain unimplemented for parsing scenarios.
- Parameter-table ranking boost still lacks dedicated test coverage.
- Candidate traces/downstream scoring still do not expose or use most new structural/terminology metadata.

### Verification Evidence

Passed:

- `openspec validate rag-maintainability-chunker --strict`
- `uv run pytest tests/test_normalizer/ tests/test_chunker/ tests/test_parse_adapter/ tests/test_document_service.py -q`  
  Result: 105 passed, 1 warning
- `uv run pytest tests/test_application_entrypoints.py tests/test_api_routes.py tests/test_document_service.py tests/test_rag_pipeline.py -q`  
  Result: 18 passed, 1 warning
- `uv run python -m compileall backend tests`
- Targeted probe: `RAG_INDEX_PROFILE=v4_step_protection` with a table now emits no table chunks.

Failed:

- Terminology suite including `tests/test_terminology_m5.py` and `tests/test_terminology_integration.py`: collection errors for missing DB models.
- Terminology subset excluding collection-error files: 34 passed, 19 failed.
- Scoped mypy on document modules: 13 errors.

**Conclusion:** M4 profile gating is fixed, but the change still fails verification. The current main blocker is the newly added M5 terminology integration: tasks are checked, but the code is not runnable against its own tests because required DB models and integration points are missing.