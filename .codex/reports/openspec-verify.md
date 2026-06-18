### Prior Findings Follow-Up

| Prior Issue | Status | Evidence |
| --- | --- | --- |
| Full OpenSpec change incomplete | Still Present | M5-M7 remain unchecked in [tasks.md](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/openspec/changes/rag-maintainability-chunker/tasks.md:69). |
| Profile gating missing | Partially Fixed, Still Present | Figure chunks are now gated in [step_chunker.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/chunker/step_chunker.py:98), but table chunks still emit under `v4_step_protection` because the table loop is unconditional after [converters.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/converters.py:74). Targeted probe confirmed `v4_step_protection` still outputs `table_id=t1`. |
| Table chunk contract incomplete | Partially Fixed, Still Present | Caption and row-based leaf splitting were added in [converters.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/converters.py:93), but nearby explanatory blocks are still not included despite the spec requiring `caption + markdown + nearby explanation`. |
| Parse metadata persistence absent | Still Present | M6 parse-meta tasks remain unchecked; no `document_parse_meta` model/table/API is present. |
| Table validation warnings discarded | Partially Fixed, Still Present | Warnings are now logged, but still not recorded in `parse_meta.parse_warnings` as required by the spec: [table_normalizer.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/normalizer/table_normalizer.py:24). |
| New Milvus fields not surfaced downstream | Still Present | Candidate traces still omit `block_type`, list/table/figure fields, and terminology fields: [utils.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/rag/utils.py:403). |
| Missing parameter-table ranking test | Still Present | Search found only dataclass/metadata assertions, no ranking-boost test. |

## OpenSpec Verification Report: `rag-maintainability-chunker`

**Result:** Failed for full-change verification.

No repository `AGENTS.md` exists in this worktree. I followed the prompt-provided AGENTS shell guidance, `CLAUDE.md`, the current context file, the previous report, and the OpenSpec artifacts as authoritative.

### Critical Findings

1. **Full change remains incomplete.**  
   M5 terminology integration, M6 parse-meta/admin tooling, and M7 soft-boundary cleanup are still pending while their spec requirements remain active.

2. **Profile gating is still wrong for tables.**  
   `v4_step_protection` must leave `table_id` null, but `parsed_to_chunks()` still iterates and emits table chunks when `_profile_allows(profile, "v4_table_aware")` is false. Evidence: [converters.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/converters.py:74).

3. **Table parent chunk contract is still incomplete.**  
   Caption and row splitting improved, but nearby explanatory paragraphs are not added to table parent text, so the `caption + markdown + nearby explanation` requirement is not met.

4. **Parse metadata persistence/API is absent.**  
   `ParsedDocument.parse_meta` is still in-memory only; `document_parse_meta` and `GET /admin/documents/{id}/parse_meta` are not implemented.

### Warnings

- Table validation warnings are logged but not attached to parse metadata.
- OCR confidence and `parse_path="native_text"` are still not populated per parsing scenarios.
- Parameter-table ranking boost has no dedicated test coverage.
- New structural fields are written to Milvus, but candidate trace/downstream scoring still largely ignores them.

### Verification Evidence

Passed:

- `openspec validate rag-maintainability-chunker --strict`
- `uv run pytest tests/test_normalizer/ tests/test_chunker/ tests/test_parse_adapter/ tests/test_document_service.py -q`  
  Result: 105 passed, 1 warning
- `uv run pytest tests/test_application_entrypoints.py tests/test_api_routes.py tests/test_document_service.py tests/test_rag_pipeline.py -q`  
  Result: 18 passed, 1 warning
- `uv run python -m compileall backend tests`
- `uv run mypy backend/documents/parse_adapter/ backend/documents/normalizer/ backend/documents/chunker/ --ignore-missing-imports`

Targeted probes:

- `v4_step_protection` + figure association now emits paragraph chunks only.
- `v4_step_protection` + table still emits table root/leaf chunks with `table_id`.

**Conclusion:** The latest commit fixed part of the prior review, especially figure profile gating and row-based table leaves, but full OpenSpec verification still fails. The main remaining blocker inside M0-M4 is table profile gating; full-change blockers remain M5-M7 and parse-meta persistence.