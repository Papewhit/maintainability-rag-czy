"""Convert ParsedDocument to legacy chunk-dict format.

Bridge between the new ParseAdapter output and the existing
DocumentService → ParentChunkStore / MilvusWriter pipeline.

The conversion is minimal — simple text splitting with no
maintainability awareness.  The Maintainability Chunker (M2+)
will replace this once complete.
"""

from __future__ import annotations

from pathlib import Path

from backend.documents.parse_adapter.base import (
    ParsedBlock,
    ParsedDocument,
    ParsedFigureAnchor,
    ParsedTable,
)


def parsed_to_chunks(
    doc: ParsedDocument,
    file_path: str,
    *,
    filename: str | None = None,
    leaf_tokens: int = 500,
    root_tokens: int = 2000,
) -> list[dict]:
    """Convert a ParsedDocument to a list of chunk dicts.

    Each chunk dict has the fields expected by DocumentService
    (match the contract of ``DocumentLoader.load_document()``).

    Strategy:
    - Root chunks (level=1) hold full text of logical sections for
      evidence context.
    - Leaf chunks (level=3) are small searchable fragments.
    - Tables become leaf chunks with ``table_markdown`` in parent_extras.
    - Figure captions become leaf chunks.

    Args:
        doc: The parsed document.
        file_path: Path to the source file on disk.
        filename: Canonical filename for chunk identity.  If *None*,
            derived from ``file_path.name``.  Callers working with
            temporary / pending files MUST pass the real filename here.
    """
    path = Path(file_path)
    canonical_name = filename or path.name
    chunks: list[dict] = []

    # ── Normalize + step-protected chunking (M2 pipeline) ──
    from backend.documents.normalizer.pipeline import run_normalizer
    from backend.documents.chunker.step_chunker import chunk_normalized

    normalized = run_normalizer(doc)
    chunks.extend(
        chunk_normalized(
            normalized, str(path), filename=canonical_name,
            leaf_tokens=leaf_tokens, root_tokens=root_tokens,
        )
    )

    # ── Tables (unchanged: pass-through as before) ──
    for ti, table in enumerate(doc.tables):
        table_text = (
            table.cells_markdown
            or "\n".join(";".join(r) for r in table.cells_structured)
        )
        if not table_text.strip():
            continue

        table_id = f"{canonical_name}_table_{ti}"
        root_tbl = _make_chunk(
            chunk_id=table_id,
            parent_chunk_id=table_id,
            root_chunk_id=table_id,
            chunk_level=1,
            chunk_role="root",
            filename=canonical_name,
            file_path=str(path),
            page_number=table.page_no,
            text=table_text,
            retrieval_text="",
            block_type="table",
            table_id=table.table_id,
            table_role="data",
            parent_extras={
                "table_markdown": table.cells_markdown,
                "cells_structured": table.cells_structured,
            },
        )
        chunks.append(root_tbl)

        leaf_tbl = _make_chunk(
            chunk_id=f"{table_id}_leaf",
            parent_chunk_id=table_id,
            root_chunk_id=table_id,
            chunk_level=3,
            chunk_role="leaf",
            filename=canonical_name,
            file_path=str(path),
            page_number=table.page_no,
            text=table_text,
            retrieval_text=(
                table.cells_markdown or table_text[:500]
            ),
            block_type="table",
            table_id=table.table_id,
            table_role="data",
            parent_extras={"table_markdown": table.cells_markdown},
        )
        chunks.append(leaf_tbl)

    # ── Figures (unchanged: pass-through as before) ──
    for fi, figure in enumerate(doc.figures):
        if not figure.caption:
            continue
        fig_id = f"{canonical_name}_figure_{fi}"
        fig_chunk = _make_chunk(
            chunk_id=fig_id,
            parent_chunk_id=fig_id,
            root_chunk_id=fig_id,
            chunk_level=3,
            chunk_role="leaf",
            filename=canonical_name,
            file_path=str(path),
            page_number=figure.page_no,
            text=figure.caption,
            retrieval_text=figure.caption,
            block_type="figure_caption",
            figure_id=figure.figure_id,
        )
        chunks.append(fig_chunk)

    return chunks


def _make_chunk(
    chunk_id: str,
    parent_chunk_id: str,
    root_chunk_id: str,
    chunk_level: int,
    chunk_role: str,
    filename: str,
    file_path: str,
    page_number: int,
    text: str,
    retrieval_text: str,
    block_type: str = "paragraph",
    section_title: str = "",
    section_path: str = "",
    section_type: str = "",
    anchor_id: str = "",
    page_start: int | None = None,
    page_end: int | None = None,
    table_id: str | None = None,
    table_role: str | None = None,
    figure_id: str | None = None,
    figure_role: str | None = None,
    list_group_id: str | None = None,
    list_order: int | None = None,
    list_marker: str | None = None,
    list_level: int | None = None,
    list_complete: bool | None = None,
    entity_types: list | None = None,
    term_match_count: int = 0,
    term_matches: list | None = None,
    protected_tokens: list | None = None,
    parent_extras: dict | None = None,
) -> dict:
    """Build a chunk dict in the legacy format."""
    extras: dict = {**(parent_extras or {})}
    if section_path:
        extras["section_path"] = section_path
    if anchor_id:
        extras["anchor_id"] = anchor_id
    if list_group_id:
        extras["list_group_id"] = list_group_id

    return {
        "chunk_id": chunk_id,
        "parent_chunk_id": parent_chunk_id,
        "root_chunk_id": root_chunk_id,
        "chunk_level": chunk_level,
        "chunk_role": chunk_role,
        "filename": filename,
        "file_path": file_path,
        "file_type": Path(filename).suffix.lstrip("."),
        "page_number": page_number,
        "text": text,
        "retrieval_text": retrieval_text,
        "block_type": block_type,
        "section_title": section_title,
        "section_type": section_type,
        "section_path": section_path,
        "anchor_id": anchor_id,
        "page_start": page_start if page_start is not None else page_number,
        "page_end": page_end if page_end is not None else page_number,
        "table_id": table_id or "",
        "table_role": table_role or "",
        "figure_id": figure_id or "",
        "figure_role": figure_role or "",
        "list_group_id": list_group_id or "",
        "list_order": list_order,
        "list_marker": list_marker or "",
        "list_level": list_level,
        "list_complete": list_complete if list_complete is not None else True,
        "entity_types": entity_types or [],
        "term_match_count": term_match_count,
        "term_matches": term_matches or [],
        "protected_tokens": protected_tokens or [],
        "parent_extras": extras,
    }


def _extract_block_title(block: ParsedBlock) -> str:
    """Extract a section title from a heading block."""
    if block.block_type == "heading":
        return block.text.split("\n")[0].strip()[:120]
    return ""


def _split_text_into_chunks(text: str, max_tokens: int = 500) -> list[str]:
    """Simple recursive character-text split (no langchain dependency).

    Splits by paragraphs first, then sentences, then words.
    """
    import re

    if not text.strip():
        return []

    separators = [
        "\n\n", "\n", "。", "；", "？", "！", ". ", "; ", "? ", "! ",
        "，", ", ", " ", "",
    ]

    def _split_recursive(t: str, seps: list[str]) -> list[str]:
        if not t.strip():
            return []
        # Rough token estimate: Chinese ~1 char/token, English ~4 char/token
        est_tokens = len(t) // 2
        if est_tokens <= max_tokens:
            return [t.strip()] if t.strip() else []

        sep = seps[0] if seps else ""
        if sep:
            parts = t.split(sep)
        else:
            parts = [t[i:i + max_tokens * 2] for i in range(0, len(t), max_tokens * 2)]

        result: list[str] = []
        for part in parts:
            if not part.strip():
                continue
            if len(part) // 2 <= max_tokens:
                result.append(part.strip())
            elif len(seps) > 1:
                result.extend(_split_recursive(part, seps[1:]))
            else:
                # Hard split
                result.append(part.strip()[: max_tokens * 2])
        return result

    return _split_recursive(text, separators)
