# Verification Context

Change: rag-maintainability-chunker
Milestone: M0-M4 complete (31/46 tasks), M5-M7 pending

Completed Scope:
- M0: DeepDoc integration spike + embedded adapter
- M1: ParseAdapter/Excel/Registry/Converters three-layer skeleton
- M2: List detection, heading tree, step-protected chunking, parent_group_id
- M3: Figure nearby association, figure parent chunking, parent_extras persistence
- M4: Table validation, markdown fallback, parameter table detection

Changed Files (full list via git diff):
- backend/documents/parse_adapter/ (base, converters, excel, registry, deepdoc/*)
- backend/documents/normalizer/ (base, pipeline, heading, list, figure, table)
- backend/documents/chunker/ (base, step_chunker)
- backend/services/document_service.py
- backend/infra/vector_store/milvus_client.py, milvus_writer.py, parent_chunk_store.py
- backend/infra/db/models.py, database.py (parent_extras migration)
- pyproject.toml (DeepDoc deps)
- tests/test_parse_adapter/, test_normalizer/, test_chunker/, test_document_service.py

Tests Run:
- uv run pytest tests/test_normalizer/ tests/test_chunker/ tests/test_parse_adapter/ tests/test_document_service.py -q
- Result: 105 passed (including slow integration tests)

Known Risks:
- M5 (terminology integration) not started
- M6 (parse_meta table) not started
- M7 (soft boundary cleanup) not started
- M4 has no dedicated test file yet (tests covered indirectly by existing integration tests)

Out of Scope:
- M5-M7 milestones
- merge to main branch
