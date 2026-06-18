"""Table normalizer — validates and enriches ParsedTables.

Two passes:
  - Validate DeepDoc tables (row/col consistency, record warnings)
  - Markdown fallback when cells_markdown is missing
"""

from __future__ import annotations

from backend.documents.parse_adapter.base import ParsedTable


def validate_and_enrich_tables(tables: list[ParsedTable]) -> list[ParsedTable]:
    """Validate table cells and provide markdown fallback.

    Returns enriched tables (frozen → new instances).
    """
    enriched: list[ParsedTable] = []

    for table in tables:
        warnings: list[str] = []
        cells_md = table.cells_markdown
        cells_struct = table.cells_structured

        # ── 5.1: Validate DeepDoc output ──
        if cells_struct:
            col_count = len(cells_struct[0]) if cells_struct else 0
            for ri, row in enumerate(cells_struct):
                if len(row) != col_count:
                    warnings.append(
                        f"table {table.table_id} row {ri}: "
                        f"expected {col_count} cols, got {len(row)}"
                    )

        # ── 5.2: Markdown fallback ──
        if not cells_md and cells_struct:
            cells_md = _rows_to_markdown(cells_struct)

        enriched.append(
            ParsedTable(
                table_id=table.table_id,
                page_no=table.page_no,
                caption=table.caption,
                cells_markdown=cells_md,
                cells_structured=cells_struct,
                bbox=table.bbox,
                nearby_block_ids=list(table.nearby_block_ids),
            )
        )

    return enriched


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
