"""Convert ParsedDocument to legacy chunk-dict format.

Bridge between the new ParseAdapter output and the existing
DocumentService → ParentChunkStore / MilvusWriter pipeline.

The conversion is minimal — simple text splitting with no
maintainability awareness.  The Maintainability Chunker (M2+)
will replace this once complete.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.documents.parse_adapter.base import (
    ParsedBlock,
    ParsedDocument,
    ParsedFigureAnchor,
    ParsedTable,
)

_TABLE_LEAF_TEXT_CHAR_BUDGET = 2000
_TABLE_LEAF_RETRIEVAL_CHAR_BUDGET = 4000


def parsed_to_chunks(
    doc: ParsedDocument,
    file_path: str,
    *,
    filename: str | None = None,
    leaf_tokens: int = 500,
    root_tokens: int = 2000,
    profile: str | None = None,
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
    from backend.rag.profiles import current_index_profile

    profile = profile if profile is not None else current_index_profile()
    normalized = run_normalizer(doc)
    chunks.extend(
        chunk_normalized(
            normalized, str(path), filename=canonical_name,
            leaf_tokens=leaf_tokens, root_tokens=root_tokens,
            profile=profile,
        )
    )

    # ── Tables (M4: validated + parameter-aware, gated by profile) ──
    from backend.documents.chunker.step_chunker import _profile_allows

    if _profile_allows(profile, "v4_table_aware"):
        enriched_tables = normalized.normalized_tables
    else:
        enriched_tables = []  # tables not emitted below v4_table_aware

    for ti, table in enumerate(enriched_tables):
        table_text = _build_table_text(table)
        if not table_text.strip():
            continue

        # Parameter table detection (M4.4)
        table_role, param_keys = _detect_parameter_table(table)
        extras: dict = {
            "table_markdown": table.cells_markdown,
            "cells_structured": table.cells_structured,
        }
        if param_keys:
            extras["parameter_keys"] = param_keys

        # M8: Build parent text with nearby explanatory blocks
        # Format: caption + nearby_texts + table_markdown
        parent_text_parts: list[str] = []
        if table.caption:
            parent_text_parts.append(table.caption)

        # Append nearby block texts if present
        if table.nearby_block_ids:
            nearby_block_map = {b.block_id: b.text for b in normalized.normalized_blocks}
            for bid in table.nearby_block_ids:
                if bid in nearby_block_map:
                    parent_text_parts.append(nearby_block_map[bid])

        parent_text_parts.append(table_text)
        parent_text = "\n".join(parent_text_parts)

        # Store nearby_block_ids in parent_extras for evidence builder
        if table.nearby_block_ids:
            extras["nearby_block_ids"] = table.nearby_block_ids

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
            text=parent_text,
            retrieval_text="",
            block_type="table",
            table_id=table.table_id,
            table_role=table_role,
            parent_extras=extras,
        )
        chunks.append(root_tbl)

        for li, leaf in enumerate(_build_table_leaf_payloads(table, table_text)):
            chunks.append(
                _make_chunk(
                    chunk_id=f"{table_id}_leaf_{li}",
                    parent_chunk_id=table_id,
                    root_chunk_id=table_id,
                    chunk_level=3,
                    chunk_role="leaf",
                    filename=canonical_name,
                    file_path=str(path),
                    page_number=table.page_no,
                    text=leaf["text"],
                    retrieval_text=leaf["retrieval_text"],
                    block_type="table",
                    table_id=table.table_id,
                    table_role=table_role,
                    parent_extras={"table_markdown": leaf["table_markdown"]},
                )
            )

    # ── Figures are now handled by chunk_normalized via FigureAssociations.
    # The legacy figure-caption leaf loop is removed to avoid duplicate entries.

    # ── Terminology scan (M5: v4_full profile) ──
    if _profile_allows(profile, "v4_full"):
        _scan_terminology_on_chunks(chunks)

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


# ── Parameter table detection (M4) ──

_PARAM_HEADER_PATTERNS = [
    re.compile(r"(参数|Parameter)", re.IGNORECASE),
    re.compile(r"(名称|Name)", re.IGNORECASE),
    re.compile(r"(值|Value)", re.IGNORECASE),
    re.compile(r"(单位|Unit)", re.IGNORECASE),
    re.compile(r"(范围|Range|取值)", re.IGNORECASE),
]


def _rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    max_cols = max((len(r) for r in rows), default=0)
    lines: list[str] = []
    for i, row in enumerate(rows):
        padded = list(row) + [""] * (max_cols - len(row))
        lines.append("| " + " | ".join(padded) + " |")
        if i == 0:
            lines.append("| " + " | ".join("---" for _ in range(max_cols)) + " |")
    return "\n".join(lines)


def _build_table_leaf_payloads(table, table_text: str) -> list[dict[str, str]]:
    if table.cells_structured:
        return _build_structured_table_leaf_payloads(table)
    return _build_fallback_table_leaf_payloads(table, table_text)


def _build_structured_table_leaf_payloads(table) -> list[dict[str, str]]:
    rows = [[str(c) for c in row] for row in table.cells_structured]
    if not rows:
        return []

    header = rows[0]
    if len(rows) == 1:
        header_text = _rows_to_text([header])
        if len(header_text) > _TABLE_LEAF_TEXT_CHAR_BUDGET:
            return _split_single_row_table_payloads(table.caption, header_text)

    data_rows = rows[1:] or []
    payloads: list[dict[str, str]] = []
    batch: list[list[str]] = []

    def flush_batch() -> None:
        nonlocal batch
        if not batch:
            return
        chunk_rows = [header] + batch
        payloads.append(_table_leaf_payload(table.caption, chunk_rows))
        batch = []

    for row in data_rows:
        candidate = [header] + batch + [row]
        candidate_text = _rows_to_text(candidate)
        if len(candidate_text) <= _TABLE_LEAF_TEXT_CHAR_BUDGET:
            batch.append(row)
            continue

        flush_batch()
        single_row_text = _rows_to_text([header, row])
        if len(single_row_text) <= _TABLE_LEAF_TEXT_CHAR_BUDGET:
            batch.append(row)
            continue

        payloads.extend(_split_oversized_table_row(table.caption, header, row))

    flush_batch()
    if payloads:
        return payloads
    return [_table_leaf_payload(table.caption, [header])]


def _build_fallback_table_leaf_payloads(table, table_text: str) -> list[dict[str, str]]:
    source = table_text or table.cells_markdown
    if not source.strip():
        return []
    payloads: list[dict[str, str]] = []
    for piece in _split_by_char_budget(source, _TABLE_LEAF_TEXT_CHAR_BUDGET):
        retrieval = _limit_text(
            f"{table.caption}\n{piece}" if table.caption else piece,
            _TABLE_LEAF_RETRIEVAL_CHAR_BUDGET,
        )
        payloads.append(
            {
                "text": piece,
                "retrieval_text": retrieval,
                "table_markdown": piece,
            }
        )
    return payloads


def _split_oversized_table_row(
    caption: str,
    header: list[str],
    row: list[str],
) -> list[dict[str, str]]:
    header_text = _rows_to_text([header])
    row_text = _rows_to_text([row])
    prefix = f"{header_text}\n"
    budget = _TABLE_LEAF_TEXT_CHAR_BUDGET - len(prefix)
    if budget <= 0:
        prefix = ""
        budget = _TABLE_LEAF_TEXT_CHAR_BUDGET

    payloads: list[dict[str, str]] = []
    for piece in _split_by_char_budget(row_text, budget):
        text = f"{prefix}{piece}" if prefix else piece
        markdown = f"{_rows_to_markdown([header])}\n{piece}" if prefix else piece
        retrieval = _limit_text(
            f"{caption}\n{markdown}" if caption else markdown,
            _TABLE_LEAF_RETRIEVAL_CHAR_BUDGET,
        )
        payloads.append(
            {
                "text": text,
                "retrieval_text": retrieval,
                "table_markdown": markdown,
            }
        )
    return payloads


def _split_single_row_table_payloads(caption: str, row_text: str) -> list[dict[str, str]]:
    payloads: list[dict[str, str]] = []
    for piece in _split_by_char_budget(row_text, _TABLE_LEAF_TEXT_CHAR_BUDGET):
        retrieval = _limit_text(
            f"{caption}\n{piece}" if caption else piece,
            _TABLE_LEAF_RETRIEVAL_CHAR_BUDGET,
        )
        payloads.append(
            {
                "text": piece,
                "retrieval_text": retrieval,
                "table_markdown": piece,
            }
        )
    return payloads


def _table_leaf_payload(caption: str, rows: list[list[str]]) -> dict[str, str]:
    text = _limit_text(_rows_to_text(rows), _TABLE_LEAF_TEXT_CHAR_BUDGET)
    markdown = _rows_to_markdown(rows)
    retrieval = _limit_text(
        f"{caption}\n{markdown}" if caption else markdown,
        _TABLE_LEAF_RETRIEVAL_CHAR_BUDGET,
    )
    return {
        "text": text,
        "retrieval_text": retrieval,
        "table_markdown": markdown,
    }


def _rows_to_text(rows: list[list[str]]) -> str:
    return "\n".join(";".join(str(c) for c in row) for row in rows)


def _split_by_char_budget(text: str, budget: int) -> list[str]:
    if budget <= 0:
        return []
    return [text[i:i + budget] for i in range(0, len(text), budget)] or [""]


def _limit_text(text: str, budget: int) -> str:
    return text[:budget]


def _build_table_text(table) -> str:
    """Build table text from cells_markdown or cells_structured."""
    if table.cells_markdown:
        return table.cells_markdown
    if table.cells_structured:
        return "\n".join(";".join(r) for r in table.cells_structured)
    return ""


def _detect_parameter_table(table) -> tuple[str, list[str]]:
    """Detect if a table is a parameter table and extract parameter keys.

    Returns (table_role, parameter_keys).
    """
    role = "data"
    keys: list[str] = []

    if not table.cells_structured:
        return role, keys

    # Check header row for parameter-like column names
    header = [str(c).strip() for c in table.cells_structured[0]]
    header_text = " ".join(header)

    param_hits = sum(1 for p in _PARAM_HEADER_PATTERNS if p.search(header_text))
    if param_hits >= 2:
        role = "parameter"

    # Check first data rows for parameter-name patterns
    for row in table.cells_structured[1:6]:
        if row and str(row[0]).strip():
            keys.append(str(row[0]).strip())

    # Also check caption
    if table.caption and any(
        w in table.caption for w in ("参数", "parameter", "规格", "spec")
    ):
        role = "parameter"

    return role, keys[:20]


# ── Terminology scanning (M5) ──


def _scan_terminology_on_chunks(chunks: list[dict]) -> None:
    """Post-process chunks to annotate terminology metadata (spec §索引时术语扫描).

    Scans each chunk's retrieval_text for domain terms and writes
    entity_types, term_match_count, term_matches, and protected_tokens.
    Silently returns if the terminology table is not loaded or empty.
    """
    try:
        from backend.rag.terminology.table import get_terminology_table
        table = get_terminology_table()
    except Exception:
        return  # terminology module not available in this environment
    if not table.is_loaded or table.entry_count() == 0:
        return

    for chunk in chunks:
        retrieval_text = chunk.get("retrieval_text", "")
        if not retrieval_text:
            chunk.setdefault("entity_types", [])
            chunk["term_match_count"] = 0
            chunk.setdefault("term_matches", [])
            chunk.setdefault("protected_tokens", [])
            continue

        matches = table.scan_text(retrieval_text)
        entity_types: list[str] = []
        term_matches: list[dict] = []
        protected_tokens: list[str] = []
        seen_types: set[str] = set()
        for m in matches:
            if m.entity_type not in seen_types:
                seen_types.add(m.entity_type)
                entity_types.append(m.entity_type)
            term_matches.append({
                "surface": m.surface,
                "canonical": m.canonical,
                "entity_type": m.entity_type,
                "start": m.start,
                "end": m.end,
            })
            if len(m.surface) >= 2 and m.surface not in protected_tokens:
                protected_tokens.append(m.surface)

        chunk["entity_types"] = entity_types
        chunk["term_match_count"] = len(term_matches)
        chunk["term_matches"] = term_matches
        chunk["protected_tokens"] = protected_tokens
