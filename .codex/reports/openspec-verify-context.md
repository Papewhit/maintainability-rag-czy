# Verification Context

Change: rag-maintainability-chunker
Milestone: M0-M5 complete (36/46 tasks), M6-M7 pending

Completed Scope since last verification:
- M5: Terminology integration — _scan_terminology_on_chunks added to parsed_to_chunks
  (v4_full profile, stage 5). Reuses TerminologyTable.scan_text() API from
  backend/rag/terminology/. Guarded import — silently returns if table not loaded.
- Profile gating: table loop skipped below v4_table_aware; v4_full → stage 5
- Synced: backend/rag/terminology/*, admin_terminology router, terminology specs

New/Changed Files:
- backend/documents/parse_adapter/converters.py (+_scan_terminology_on_chunks)
- backend/documents/chunker/step_chunker.py (v4_full → stage 5)
- backend/rag/terminology/* (synced from main)
- backend/routers/admin_terminology.py (synced)
- openspec/specs/rag-terminology-module/spec.md (synced)

Tests Run:
- uv run pytest tests/test_normalizer/ tests/test_chunker/ tests/test_parse_adapter/ tests/test_document_service.py -q
- Result: 105 passed (fast), 5 passed (integration)

Known Risks:
- Mypy on full backend/ shows pre-existing errors in models.py/table.py (not M5 scope)
- Scoped mypy on backend/documents/ is clean
- Terminology table requires DB initialization to be loaded; without it, scan silently passes

Out of Scope:
- M6 (parse_meta persistence)
- M7 (soft boundary cleanup)
