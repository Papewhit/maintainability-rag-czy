# Test Taxonomy

Tests are organized first by execution layer, then by product area. New tests should not be added directly under `tests/`.

## Directories

| Directory | Use for |
| --- | --- |
| `tests/unit/` | Pure unit tests with fakes, mocks, temp files, or in-memory stores. No real services. |
| `tests/integration/` | Cross-component tests, real document parsers, real sample files, or real DB dependencies. |
| `tests/e2e/` | Full validation scripts that require a running service or full document ingestion flow. |
| `tests/eval/` | RAG dataset, qrels, metric, and evaluation helper tests. |
| `tests/regression/` | Tests locking previously fixed bugs or metric drift checks. |
| `tests/fixtures/` | Shared test data. Document samples live in `tests/fixtures/documents/`. |

## Markers

Use markers to make execution cost explicit:

```python
@pytest.mark.slow
@pytest.mark.requires_models
@pytest.mark.requires_db
```

Directory is the primary taxonomy. Markers add runtime requirements.

## Commands

```powershell
uv run pytest tests/unit -q
uv run pytest tests/integration -m "not slow" -q
uv run pytest tests/eval tests/regression -q
uv run pytest tests -m "not slow and not e2e" -q
uv run pytest tests/integration -m "slow" -v
node tests/unit/frontend/ui-redesign.test.mjs
```

DeepDoc parse metadata validation scripts live in `tests/e2e/deepdoc_parse_metadata/`.

## Placement Rules

- No DB, Redis, Milvus, network, running service, or heavyweight model dependency: `tests/unit/`.
- Real PostgreSQL, Redis, Milvus, DeepDoc models, or real sample document parsing: `tests/integration/`.
- Running FastAPI, curl/HTTP validation, or full ingestion validation scripts: `tests/e2e/`.
- Gold datasets, qrels, RAG metrics, chunk-pool generation, or evaluation CLIs: `tests/eval/`.
- Historical bug fixes or quality drift checks: `tests/regression/`.
- Shared document samples: `tests/fixtures/documents/`.
