## OpenSpec Verification Report: `rag-maintainability-chunker`

**Result:** Failed for full-change verification.

I read `.codex/reports/openspec-verify-context.md` and the existing `.codex/reports/openspec-verify.md`, then re-verified against the OpenSpec artifacts, code, tests, and diff. No repository `AGENTS.md` exists in this worktree, so I used the prompt-provided AGENTS shell guidance plus `CLAUDE.md`.

### Prior Findings Follow-Up

| Prior Issue | Status | Evidence |
| --- | --- | --- |
| Full OpenSpec change incomplete | Still Present | M5-M7 remain unchecked in [tasks.md](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/openspec/changes/rag-maintainability-chunker/tasks.md:69) |
| Profile gating missing | Still Present | Chunk/table/figure generation has no profile gate in [converters.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/converters.py:55) and [step_chunker.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/chunker/step_chunker.py:92) |
| Table chunk contract incomplete | Still Present | Table chunks omit caption/nearby text and always create one leaf in [converters.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/converters.py:71) |
| Parse metadata persistence absent | Still Present | No `document_parse_meta` model/table/API; current DB additions only cover parent chunk extras in [models.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/infra/db/models.py:74) |

### Critical Findings

1. **The full change is not archive-ready.**  
   M5 terminology integration, M6 parse metadata/admin tooling, and M7 soft-boundary cleanup are still pending while their spec requirements remain authoritative.

2. **Staged profile behavior is missing.**  
   The spec requires early profiles such as `v4_step_protection` to leave later fields null. Current code always runs figure/table-capable paths once implemented.

3. **Table chunking does not satisfy the M4 spec.**  
   The spec requires parent text as `caption + markdown + nearby explanation`, retrieval text with caption plus markdown summary, and row-based leaf splitting for long tables. Current implementation only uses markdown/cells and creates a single table leaf.

4. **Parse metadata persistence and admin read API are absent.**  
   `ParsedDocument.parse_meta` is modeled in memory, but is not persisted to `document_parse_meta` and there is no `GET /admin/documents/{id}/parse_meta`.

### Warnings

- Table validation warnings are computed but discarded in [table_normalizer.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/normalizer/table_normalizer.py:20).
- New Milvus fields are written, but retrieval formatting drops `block_type`, list/table/figure fields, and terminology fields, limiting downstream use.
- Task 5.6 is checked, but I found no dedicated test proving parameter-table query ranking boost.

### Verification Evidence

- `openspec validate rag-maintainability-chunker --strict`: passed.
- `uv run pytest tests/test_normalizer/ tests/test_chunker/ tests/test_parse_adapter/ tests/test_document_service.py -q`: 105 passed, 1 warning.
- `uv run pytest tests/test_application_entrypoints.py tests/test_api_routes.py tests/test_document_service.py tests/test_rag_pipeline.py -q`: 18 passed, 1 warning.
- `uv run python -m compileall backend tests`: passed.
- `uv run mypy backend/documents/parse_adapter/ backend/documents/normalizer/ backend/documents/chunker/ --ignore-missing-imports`: passed.

**Conclusion:** M0-M4 are substantially implemented and tested, but full OpenSpec verification fails. The main blockers are profile gating, the M4 table chunk contract, and known pending M5-M7 requirements.