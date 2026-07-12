from unittest.mock import patch

import pytest

from backend.documents.chunker.step_chunker import chunk_normalized
from backend.documents.normalizer.base import ListGroup, NormalizedBlock, NormalizedDocument
from backend.documents.parse_adapter.base import ParsedDocument, ParseMeta
import backend.rag.utils as rag_utils


pytestmark = pytest.mark.eval


def _item(block_id: str, text: str, index: int) -> NormalizedBlock:
    return NormalizedBlock(
        block_id=block_id,
        page_no=1,
        block_type="list_item",
        text=text,
        list_level=1,
        list_marker=f"{index + 1}.",
        list_item_index=index,
    )


def test_real_chunker_metadata_repairs_complete_step_group(record_property):
    items = [
        _item("b1", "1. 拆卸外壳并记录状态", 0),
        _item("b2", "2. 检查密封面并记录状态", 1),
        _item("b3", "3. 安装新密封圈并复验", 2),
    ]
    document = NormalizedDocument(
        parsed=ParsedDocument(
            filename="manual.pdf",
            file_type="pdf",
            parse_meta=ParseMeta(parse_engine="test"),
        ),
        normalized_blocks=items,
        list_groups=[ListGroup(group_id="lg_p1_l1_s0", list_level=1, items=items)],
    )
    chunks = chunk_normalized(document, "/tmp/manual.pdf", root_tokens=5)
    roots = [
        {**chunk, "index_profile": "v4"}
        for chunk in chunks
        if chunk["chunk_role"] == "root"
    ]
    assert [root["list_order"] for root in roots] == [1, 2, 3]
    selected = [roots[1]]

    def fetch(group_id, orders, *, filename, index_profile):
        assert group_id == "lg_p1_l1_s0"
        assert filename == "manual.pdf"
        assert index_profile == "v4"
        return [root for root in roots if root["list_order"] in orders]

    with (
        patch.object(rag_utils, "STEP_CHAIN_CHECK_ENABLED", True),
        patch.object(rag_utils, "STEP_CHAIN_ADJACENT_LOOKBACK", 1),
        patch.object(rag_utils, "_fetch_adjacent_chunks", side_effect=fetch),
    ):
        repaired, meta = rag_utils._step_chain_check(selected, top_k=1)

    repaired_orders = {chunk["list_order"] for chunk in repaired}
    completion_ratio = len(repaired_orders) / len(roots)
    record_property("step_group_completion_ratio", completion_ratio)

    assert repaired_orders == {1, 2, 3}
    assert completion_ratio == 1.0
    assert meta["step_chain_repaired_groups"] == ["lg_p1_l1_s0"]
