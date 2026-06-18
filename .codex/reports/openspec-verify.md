### Prior Critical Follow-up

| Prior Critical | Status | Evidence |
| --- | --- | --- |
| M6 admin API mount | Fixed | `admin_documents_router` is imported and mounted in [api.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/api.py:7). Route probe confirmed `/admin/documents/{document_id}/parse_meta` is present. |
| Float columns | Fixed, with new cleanup issue | `watermark_filter_ratio` and `ocr_confidence_avg` now use `Float` in [models.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/infra/db/models.py:68), and runtime DDL uses `FLOAT` in [database.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/infra/db/database.py:78). However, `hierarchy_validation_warnings` is defined twice, causing mypy `no-redef`. |
| parse_meta field completeness | Still Present | Persistence now writes watermark/OCR/hierarchy keys, and API returns them, but `ParseMeta` has no `hierarchy_validation_warnings` field and `_parse_meta_to_dict()` does not emit it: [base.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/base.py:132), [document_service.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/services/document_service.py:231). Probe output confirmed `hasattr(ParseMeta(...), "hierarchy_validation_warnings") == False`. |
| M7 design cleanup | Still Present | The old ambiguity section remains: `待 DeepDoc 源代码核对`, `归属暂时模糊`, and `待澄清` still appear in [design.md](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/openspec/changes/rag-maintainability-chunker/design.md:137), despite the M7 appendix. |

## OpenSpec Verification Report: `rag-maintainability-chunker`

**Verdict: Fail.**

All 46/46 tasks are checked, and `openspec validate rag-maintainability-chunker --strict` passes. However, final verification still fails because two named prior criticals remain unresolved and verification commands still fail.

### Critical Findings

1. **parse_meta completeness is still incomplete on the actual upload path.**  
   The DB row/API shape includes `hierarchy_validation_warnings`, but `ParseMeta` cannot carry it and `_parse_meta_to_dict()` cannot emit it. Upload-derived parse metadata will therefore persist `None` for this required field.

2. **M7 design cleanup is not complete.**  
   The document still contains the original “soft boundary pending clarification” text and table, then later says all ambiguity was removed. That is contradictory.

3. **Scoped mypy still fails.**  
   `uv run mypy backend/documents/parse_adapter/ backend/documents/normalizer/ backend/documents/chunker/ --ignore-missing-imports` fails with 21 errors, including the new duplicate `hierarchy_validation_warnings` definition.

4. **Terminology restored suite still fails.**  
   `uv run pytest tests/test_terminology_m1.py ... tests/test_terminology_rescan_regression.py -q` still reports 11 failed, 59 passed.

### Verification Evidence

Passed:
- `openspec validate rag-maintainability-chunker --strict`
- `uv run python -m compileall backend tests`
- `uv run pytest tests/test_application_entrypoints.py tests/test_api_routes.py tests/test_document_service.py tests/test_rag_pipeline.py -q` → 18 passed
- `uv run pytest tests/test_normalizer/ tests/test_chunker/ tests/test_parse_adapter/ tests/test_document_service.py -q` → 105 passed
- Route probe confirmed `/admin/documents/{document_id}/parse_meta` is mounted

Failed:
- Scoped mypy → 21 errors
- Terminology suite → 11 failed, 59 passed

No repository `AGENTS.md` exists in this worktree; I followed the prompt-provided AGENTS instructions and OpenSpec artifacts as authoritative.