"""End-to-end DOCX fixture test for M2 step-protected chunking."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.documents.chunker.step_chunker import chunk_normalized
from backend.documents.normalizer.pipeline import run_normalizer
from backend.documents.parse_adapter.deepdoc.adapter import DeepDocAdapter


PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())
DOCUMENT_FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "documents"
FIXTURE = DOCUMENT_FIXTURES_DIR / "maintenance_chunker_edge_cases.docx"


@pytest.mark.slow
def test_maintenance_docx_step_protection_end_to_end() -> None:
    """Real DOCX -> parse -> normalize -> chunk covers M2 edge cases.

    The fixture is synthetic so the test does not depend on production or
    customer documents. It intentionally includes parent/child steps, an
    interrupted list, a long numbered list, action-word prose, and tables.
    """
    assert FIXTURE.exists(), f"Missing fixture: {FIXTURE}"

    parsed = DeepDocAdapter().parse(str(FIXTURE))
    normalized = run_normalizer(parsed)
    chunks = chunk_normalized(
        normalized,
        str(FIXTURE),
        filename=FIXTURE.name,
    )

    roots = [c for c in chunks if c["chunk_role"] == "root"]
    leaves = [c for c in chunks if c["chunk_role"] == "leaf"]
    list_roots = [c for c in roots if c.get("list_group_id")]
    partial_roots = [c for c in list_roots if c.get("list_complete") is False]

    assert parsed.file_type == "docx"
    assert len(parsed.blocks) >= 40
    assert len(parsed.tables) >= 1
    assert len(normalized.list_groups) >= 10
    assert roots
    assert leaves

    assert any(g.parent_group_id for g in normalized.list_groups), (
        "nested ListGroup parent links were not created"
    )

    assert any(
        "1. 拆卸前盖板" in c["text"]
        and "(1) 断开控制电缆" in c["text"]
        and "(2) 拆下固定螺栓" in c["text"]
        for c in roots
    ), "parent root chunk does not include its child steps"

    assert any(
        "1. 检查电缆护套" in c["text"] for c in roots
    ), "pre-interruption list root missing"
    assert any(
        "2. 复验电源端子" in c["text"] for c in roots
    ), "post-interruption list root missing"

    assert partial_roots, "long numbered list did not split into partial roots"
    assert all(c["list_complete"] is False for c in partial_roots)

    assert any(
        any(
            phrase in c["text"]
            for phrase in ["拆卸外壳", "检查密封面是否磨损", "更换损坏密封圈"]
        )
        for c in leaves
    ), "action-word prose did not produce searchable leaves"

    list_leaves = [c for c in leaves if c.get("list_group_id")]
    assert list_leaves, "list leaves missing"
    assert all(c.get("list_marker") for c in list_leaves)
    assert all(c.get("list_level") is not None for c in list_leaves)
    assert all(c.get("list_complete") is not None for c in list_leaves)

    assert all(c["filename"] == FIXTURE.name for c in chunks)
    assert all(".pending-" not in c.get("file_path", "") for c in chunks)

