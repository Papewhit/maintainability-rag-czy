"""Step-protected chunker — consumes NormalizedDocument, produces MaintenanceChunks.

Step protection rules (per M2):
  1. Continuous ListGroup stays together in a parent chunk (up to token budget).
  2. Long ListGroup splits by top-level items (list_level=0).  Child items
     (level >= 1) follow their parent — never split between parent and children.
  3. Maintenance action words (拆卸/检查/更换/...) start new semantic step groups.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from backend.documents.chunker.base import MaintenanceChunk
from backend.documents.normalizer.base import (
    FigureAssociation,
    ListGroup,
    NormalizedBlock,
    NormalizedDocument,
)
from backend.documents.normalizer.figure_normalizer import _infer_figure_role
from backend.documents.parse_adapter.converters import _make_chunk, _split_text_into_chunks

# ── Maintenance action words (step boundary signals) ──

_MAINTENANCE_ACTIONS = {
    "拆卸", "检查", "更换", "安装", "复验", "调试", "校准",
    "清理", "润滑", "紧固", "调整", "更换件", "备件",
    "分解", "组装", "测试", "测量", "记录", "确认",
    "拆解", "修复", "替换", "接通", "断开", "标记",
}


def _starts_with_maintenance_action(text: str) -> bool:
    head = text.strip()[:8]
    return any(head.startswith(w) for w in _MAINTENANCE_ACTIONS)


def _contains_action_word(text: str) -> bool:
    """True if *text* contains any maintenance action word (spec: 包含)."""
    return any(w in text for w in _MAINTENANCE_ACTIONS)


def _estimate_tokens(text: str) -> int:
    """Rough token count: Chinese ~1 char/token, English ~4 char/token."""
    return max(1, len(text) // 2)


# ── Main chunker ──


def chunk_normalized(
    doc: NormalizedDocument,
    file_path: str,
    *,
    filename: str | None = None,
    leaf_tokens: int = 500,
    root_tokens: int = 2000,
    profile: str = "",
) -> list[dict]:
    """Convert a NormalizedDocument into chunk dicts ready for indexing.

    Step-protected list groups are chunked as atomic units; non-list blocks
    are chunked as in the original parsed_to_chunks.

    *profile* gates stage-specific features (spec §阶段化 profile 支持):
    - "" or "legacy" → list-group fields only (M2)
    - "v4_figure_nearby" → list + figure fields (M2+M3)
    - "v4_table_aware" / "v4_full" → all fields (M2+M3+M4)
    """
    path = Path(file_path)
    canonical = filename or path.name
    chunks: list[dict] = []

    # Track which blocks belong to a ListGroup (to avoid double-chunking)
    grouped_block_ids: set[str] = set()
    for lg in doc.list_groups:
        for item in lg.items:
            grouped_block_ids.add(item.block_id)

    # Build parent → children index
    children_of: dict[str, list[ListGroup]] = {}
    for lg in doc.list_groups:
        if lg.parent_group_id:
            children_of.setdefault(lg.parent_group_id, []).append(lg)

    # ── Process ListGroups (step-protected path) ──
    for g_idx, group in enumerate(doc.list_groups):
        if group.parent_group_id:
            continue  # child groups merged into parent below
        lg_chunks = _chunk_list_group(
            group, g_idx, canonical, str(path), root_tokens, leaf_tokens,
            child_groups=children_of.get(group.group_id),
        )
        chunks.extend(lg_chunks)

    # ── Process FigureAssociations (M3) — gated behind profile ──
    figure_block_ids: set[str] = set()
    if _profile_allows(profile, "v4_figure_nearby"):
        for fa in doc.figure_associations:
            fig_chunks = _chunk_figure(
                fa, canonical, str(path),
                doc.normalized_blocks, root_tokens, leaf_tokens,
            )
            chunks.extend(fig_chunks)
            figure_block_ids.update(fa.nearby_block_ids)

    # Merge figure_block_ids into grouped_block_ids so nearby blocks
    # included in figure chunks aren't also chunked as standalone blocks
    grouped_block_ids.update(figure_block_ids)

    # ── Process non-list blocks ──
    for block in doc.normalized_blocks:
        if block.block_id in grouped_block_ids:
            continue
        if not block.text.strip():
            continue

        root_id = f"{canonical}_root_{block.block_id}"
        root_chunk = _make_chunk(
            chunk_id=root_id,
            parent_chunk_id=root_id,
            root_chunk_id=root_id,
            chunk_level=1,
            chunk_role="root",
            filename=canonical,
            file_path=str(path),
            page_number=block.page_no,
            text=block.text,
            retrieval_text="",
            block_type=block.block_type,
            section_title=block.section_title,
            section_path=block.section_path,
            anchor_id=block.anchor_id,
            page_start=block.page_no,
            page_end=block.page_no,
        )
        chunks.append(root_chunk)

        # For long paragraphs, use maintenance action words as soft boundary hints.
        # Spec: 包含 (not just 以...开头) action words → boundary signal.
        text_to_split = block.text
        if _estimate_tokens(text_to_split) > leaf_tokens and _contains_action_word(text_to_split):
            # Action word detected → prefer splitting at action boundaries
            parts = _split_paragraph_by_actions(text_to_split)
            if len(parts) > 1:
                leaves = []
                for part in parts:
                    leaves.extend(_split_text_into_chunks(part, max_tokens=leaf_tokens))
            else:
                leaves = _split_text_into_chunks(text_to_split, max_tokens=leaf_tokens)
        else:
            leaves = _split_text_into_chunks(text_to_split, max_tokens=leaf_tokens)

        for li, leaf_text in enumerate(leaves):
            chunks.append(
                _make_chunk(
                    chunk_id=f"{canonical}_{block.block_id}_leaf_{li}",
                    parent_chunk_id=root_id,
                    root_chunk_id=root_id,
                    chunk_level=3,
                    chunk_role="leaf",
                    filename=canonical,
                    file_path=str(path),
                    page_number=block.page_no,
                    text=leaf_text,
                    retrieval_text=leaf_text,
                    block_type=block.block_type,
                    section_title=block.section_title,
                    section_path=block.section_path,
                    anchor_id=block.anchor_id,
                    page_start=block.page_no,
                    page_end=block.page_no,
                )
            )

    return chunks


def _chunk_list_group(
    group: ListGroup,
    group_idx: int,
    canonical: str,
    file_path: str,
    root_tokens: int,
    leaf_tokens: int,
    *,
    child_groups: list[ListGroup] | None = None,
) -> list[dict]:
    """Chunk a ListGroup with step protection, merging child groups."""
    # Merge child items into parent items (child items follow their parent)
    items = list(group.items)
    if child_groups:
        # Build a flat merged list: parent items interleaved with their children
        merged: list[NormalizedBlock] = []
        child_by_parent: dict[int, list[NormalizedBlock]] = {}
        for cg in child_groups:
            # Child group belongs to the parent item that precedes it
            # (child items have higher list_level)
            pass  # items are already ordered by order_index in the document
        for item in items:
            merged.append(item)
        for cg in child_groups:
            for ci in cg.items:
                merged.append(ci)
        # Re-sort by order_index to maintain document order
        merged.sort(key=lambda b: b.order_index)
        items = merged

    if not items:
        return []

    # ── Decide if the group needs splitting ──
    full_text = "\n".join(it.text for it in items)
    if _estimate_tokens(full_text) <= root_tokens:
        sub_groups = [items]
    else:
        # Split by maintenance action boundaries first
        sub_groups = _split_by_maintenance_actions(items)
        # If still too large, split by top-level items
        final_subs: list[list[NormalizedBlock]] = []
        for sg in sub_groups:
            sg_text = "\n".join(it.text for it in sg)
            if _estimate_tokens(sg_text) <= root_tokens:
                final_subs.append(sg)
            else:
                final_subs.extend(_split_by_toplevel(sg))
        sub_groups = final_subs

    chunks: list[dict] = []
    for sg_idx, sub_items in enumerate(sub_groups):
        # Parent chunk for this sub-group
        parent_text = "\n".join(it.text for it in sub_items)
        parent_id = f"{canonical}_lg{group_idx}_sg{sg_idx}"
        page_numbers = {it.page_no for it in sub_items}

        chunk_data = _make_chunk(
            chunk_id=parent_id,
            parent_chunk_id=parent_id,
            root_chunk_id=parent_id,
            chunk_level=1,
            chunk_role="root",
            filename=canonical,
            file_path=file_path,
            page_number=min(page_numbers),
            text=parent_text,
            retrieval_text="",
            block_type="list_item",
            page_start=min(page_numbers),
            page_end=max(page_numbers),
            list_group_id=group.group_id,
            list_complete=(len(sub_groups) == 1),
        )
        chunk_data.setdefault("parent_extras", {})["list_group_items"] = len(sub_items)
        chunks.append(chunk_data)

        # Leaf chunks — one per item
        for li, item in enumerate(sub_items):
            chunk_data_leaf = _make_chunk(
                chunk_id=f"{parent_id}_leaf_{li}",
                parent_chunk_id=parent_id,
                root_chunk_id=parent_id,
                chunk_level=3,
                chunk_role="leaf",
                filename=canonical,
                file_path=file_path,
                page_number=item.page_no,
                text=item.text,
                retrieval_text=item.text,
                block_type="list_item",
                section_title=item.section_title or "",
                section_path=item.section_path or "",
                anchor_id=item.anchor_id or "",
                page_start=item.page_no,
                page_end=item.page_no,
                list_group_id=group.group_id,
                list_order=item.list_item_index,
                list_marker=item.list_marker or "",
                list_level=item.list_level,
                list_complete=(len(sub_groups) == 1),
            )
            chunks.append(chunk_data_leaf)

    return chunks


# ── Figure chunking (M3) ──


def _chunk_figure(
    fa: FigureAssociation,
    canonical: str,
    file_path: str,
    blocks: list[NormalizedBlock],
    root_tokens: int,
    leaf_tokens: int,
) -> list[dict]:
    """Generate a figure parent chunk + optional leaf chunks.

    Spec: chunk text = caption (first line) + figure marker + nearby blocks.
    Caption and page_no come from the ParsedFigureAnchor (carried through
    FigureAssociation) as the authoritative source of truth.
    """
    block_by_id = {b.block_id: b for b in blocks}
    nearby_texts: list[str] = []
    page_nos: set[int] = {fa.page_no}

    for bid in fa.nearby_block_ids:
        blk = block_by_id.get(bid)
        if blk:
            nearby_texts.append(blk.text)
            page_nos.add(blk.page_no)

    # Authoritative caption from the figure anchor (not guessed)
    caption = fa.caption[:200] if fa.caption else ""
    figure_role = _infer_figure_role(caption) if caption else "diagram"

    # Build parent text: caption (first line) + figure marker + nearby blocks
    parent_lines: list[str] = []
    if caption:
        parent_lines.append(caption)
    parent_lines.append(f"[Figure: {fa.figure_id}]")  # marker
    parent_lines.extend(nearby_texts)
    parent_text = "\n\n".join(parent_lines)

    page_no = fa.page_no or min(page_nos) if page_nos else 1
    parent_id = f"{canonical}_{fa.figure_id}"

    chunks: list[dict] = [
        _make_chunk(
            chunk_id=parent_id,
            parent_chunk_id=parent_id,
            root_chunk_id=parent_id,
            chunk_level=1,
            chunk_role="root",
            filename=canonical,
            file_path=file_path,
            page_number=page_no,
            text=parent_text,
            retrieval_text="",
            block_type="figure",
            page_start=page_no,
            page_end=max(page_nos) if page_nos else page_no,
            figure_id=fa.figure_id,
            figure_role=figure_role,
            parent_extras={"nearby_block_ids": list(fa.nearby_block_ids)},
        ),
    ]

    # Leaf chunks — caption + figure marker prepended to each leaf
    leaf_prefix = f"{caption}\n[Figure: {fa.figure_id}]\n" if caption else f"[Figure: {fa.figure_id}]\n"
    if _estimate_tokens(parent_text) > leaf_tokens:
        for li, leaf_text in enumerate(_split_text_into_chunks(parent_text, max_tokens=leaf_tokens)):
            retrieval = leaf_prefix + leaf_text
            chunks.append(
                _make_chunk(
                    chunk_id=f"{parent_id}_leaf_{li}",
                    parent_chunk_id=parent_id,
                    root_chunk_id=parent_id,
                    chunk_level=3,
                    chunk_role="leaf",
                    filename=canonical,
                    file_path=file_path,
                    page_number=page_no,
                    text=leaf_text,
                    retrieval_text=retrieval[:1000],
                    block_type="figure",
                    page_start=page_no,
                    page_end=max(page_nos) if page_nos else page_no,
                    figure_id=fa.figure_id,
                    figure_role=figure_role,
                )
            )
    else:
        chunks.append(
            _make_chunk(
                chunk_id=f"{parent_id}_leaf_0",
                parent_chunk_id=parent_id,
                root_chunk_id=parent_id,
                chunk_level=3,
                chunk_role="leaf",
                filename=canonical,
                file_path=file_path,
                page_number=page_no,
                text=parent_text,
                retrieval_text=leaf_prefix + parent_text[:500],
                block_type="figure",
                page_start=page_no,
                page_end=max(page_nos) if page_nos else page_no,
                figure_id=fa.figure_id,
                figure_role=figure_role,
            )
        )

    return chunks


def _split_by_maintenance_actions(
    items: list[NormalizedBlock],
) -> list[list[NormalizedBlock]]:
    """Split items at maintenance action word boundaries."""
    if not items:
        return []
    sub_groups: list[list[NormalizedBlock]] = []
    current: list[NormalizedBlock] = [items[0]]

    for item in items[1:]:
        if _starts_with_maintenance_action(item.text):
            sub_groups.append(current)
            current = [item]
        else:
            current.append(item)
    sub_groups.append(current)
    return sub_groups


def _split_by_toplevel(
    items: list[NormalizedBlock],
) -> list[list[NormalizedBlock]]:
    """Split items at the minimum level in the group, keeping children
    (higher levels) with their parent item.

    Example: [1.(L1), a(L2), b(L2), 2.(L1), a(L2)] ->
             [[1., a, b], [2., a]]
    """
    if not items:
        return []
    min_level = min((it.list_level or 1) for it in items)

    sub_groups: list[list[NormalizedBlock]] = []
    current: list[NormalizedBlock] = []

    for item in items:
        level = item.list_level or 1
        if level == min_level and current:
            sub_groups.append(current)
            current = [item]
        else:
            current.append(item)

    if current:
        sub_groups.append(current)
    return sub_groups


def _split_paragraph_by_actions(text: str) -> list[str]:
    """Soft-split a long paragraph at maintenance action word boundaries.

    The action word serves as a hint; the split is not forced.
    Returns [text] if no action boundaries are found.
    """
    import re
    actions = "|".join(_MAINTENANCE_ACTIONS)
    pattern = re.compile(rf"(?<=[。；\n])\s*(?={actions})")
    parts = pattern.split(text)
    if len(parts) <= 1:
        return [text]
    # Merge very short parts with neighbors
    merged: list[str] = []
    buf = ""
    for p in parts:
        if len(p) < 20 and buf:
            buf += p
        else:
            if buf:
                merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    return merged if merged else [text]


# ── Profile gating (spec §阶段化 profile 支持) ──

_PROFILE_STAGES: dict[str, int] = {
    "": 2,               # default: step protection only (M2)
    "legacy": 2,
    "v4_step_protection": 2,
    "v4_figure_nearby": 3,
    "v4_table_aware": 4,
    "v4_full": 4,
}


def _profile_allows(current: str, minimum: str) -> bool:
    """True if *current* profile is at least *minimum* stage."""
    cur_stage = _PROFILE_STAGES.get(
        (current or "").strip(), 2,
    )
    min_stage = _PROFILE_STAGES.get(minimum.strip(), 2)
    return cur_stage >= min_stage
