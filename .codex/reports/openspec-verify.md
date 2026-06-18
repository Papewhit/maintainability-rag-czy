### Prior Findings Follow-up

| Prior Issue | Status | Evidence |
| --- | --- | --- |
| M5 marked complete but tests deleted | Fixed structurally, still failing | Terminology tests are restored, but `uv run pytest tests/test_terminology_*.py ...` fails: 11 failed, 59 passed. |
| Scoped mypy fails | Still Present | `uv run mypy backend/documents/parse_adapter/ backend/documents/normalizer/ backend/documents/chunker/ --ignore-missing-imports` fails with 20 errors. |
| M5 ParentChunkStore term persistence incorrect | Still Present | `ParentChunkStore._payload_from_doc()` only persists `parent_extras`, not top-level `term_matches` / `protected_tokens`: [parent_chunk_store.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/infra/vector_store/parent_chunk_store.py:53). Restored test fails with `KeyError: 'term_matches'`. |
| M6-M7 unchecked/incomplete | Partially Fixed | Tasks are now checked, but M6 implementation remains incomplete and endpoint is unreachable; M7 has an appendix but older ambiguous text remains in design. |
| Table parent chunks omit nearby explanatory blocks | Still Present | Table chunk text is caption + table text only; `nearby_block_ids` are not used in table chunk construction: [converters.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/converters.py:94). |
| Table validation warnings not attached to parse metadata | Still Present | Warnings are local/logged and discarded: [table_normalizer.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/normalizer/table_normalizer.py:25). |
| OCR confidence / `parse_path="native_text"` incomplete | Still Present | `ParseMeta` has `ocr_confidence_avg`, but no `parse_path`; persistence does not write OCR/watermark fields: [base.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/documents/parse_adapter/base.py:132), [document_service.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/services/document_service.py:98). |
| Parameter-table ranking test missing | Still Present | Parameter metadata exists, but no dedicated ranking-boost test was found. |
| Admin terminology router deleted | Fixed as file, not mounted | `backend/routers/admin_terminology.py` exists, but `backend/api.py` does not include admin routers: [api.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/api.py:8). |
| Profile gating missing | Fixed | Probe with `profile='v4_step_protection'` emitted only paragraph root/leaf chunks, no table chunks. |
| Parse metadata persistence absent | Partially Fixed | Table/model/router exist, but persistence/API omit required fields and router is not mounted. |

## OpenSpec Verification Report: `rag-maintainability-chunker`

**Result: Failed.**

No repository `AGENTS.md` exists in this worktree, so I followed the prompt-provided AGENTS instructions plus OpenSpec artifacts, code, tests, and diffs as authoritative evidence. All 46/46 tasks are checked, but checked tasks do not match implementation completeness.

### Critical Findings

1. **M6 parse metadata API is not reachable and does not return the required full metadata.**  
   `admin_documents.py` defines `GET /admin/documents/{id}/parse_meta`, but `backend/api.py` only mounts auth/chat/sessions/documents routers, so the endpoint is not exposed by the app. The handler also returns only engine/version/duration/pages/warnings, omitting `watermark_filter_ratio`, `ocr_confidence_avg`, and `hierarchy_validation_warnings`: [admin_documents.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/routers/admin_documents.py:23).

2. **M6 parse metadata persistence is incomplete.**  
   `_parse_meta_to_dict()` includes watermark/OCR, but `_persist_parse_meta()` only writes `parse_engine`, version, duration, total pages, and `parse_warnings`: [document_service.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/services/document_service.py:98). The spec requires `watermark_filter_ratio`, `ocr_confidence_avg`, `hierarchy_validation_warnings`, `parse_warnings`, and duration.

3. **Terminology suite is restored but failing.**  
   The restored M3/M4/integration tests fail on missing `terminology_preflight`, missing `_scan_terminology`, missing seed CSV/load function, and missing ParentChunkStore term fields. Command result: 11 failed, 59 passed.

4. **M5 ParentChunkStore term-field contract remains broken.**  
   The chunker now places `term_matches` / `protected_tokens` in `parent_extras`, but restored tests and `rescan.py` expect top-level fields. `rescan.py` even references nonexistent `ParentChunk.term_matches` / `ParentChunk.protected_tokens`: [rescan.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/rag/terminology/rescan.py:195).

5. **Scoped mypy still fails.**  
   The scoped command reports 20 errors in `backend/infra/db/models.py` and `backend/rag/terminology/table.py`.

### Warnings

- `DocumentParseMeta` stores float-like fields as `Integer`, which can truncate ratio/confidence values: [models.py](F:/dev/llm/SuperHermes/.claude/worktrees/maintainability-chunker/backend/infra/db/models.py:66).
- The M7 appendix clarifies ownership, but the earlier “待澄清” soft-boundary section remains in `design.md`, so the document still contains contradictory historical ambiguity.
- Table validation warnings are still not propagated into `parse_meta.parse_warnings`.
- Table chunks still do not include nearby explanatory blocks.
- Admin terminology router exists but is not mounted, so prior “router deleted” is only partially addressed at application level.

### Verification Evidence

Passed:
- `openspec validate rag-maintainability-chunker --strict` → valid
- `uv run pytest tests/test_normalizer/ tests/test_chunker/ tests/test_parse_adapter/ tests/test_document_service.py -q` → 105 passed
- `uv run pytest tests/test_application_entrypoints.py tests/test_api_routes.py tests/test_document_service.py tests/test_rag_pipeline.py -q` → 18 passed
- `uv run python -m compileall backend tests` → passed
- `v4_step_protection` table probe → no table chunks emitted

Failed:
- Terminology restored suite → 11 failed, 59 passed
- Scoped mypy → 20 errors

**Conclusion:** final verification fails. The task checklist is fully checked, but M6 is not actually delivered through the running app, M5 terminology persistence/integration remains broken, and required verification still fails.