"""DeepDoc ParseAdapter — embedded adapter for PDF and DOCX documents.

Wraps the copied DeepDoc vision and parser modules.  Models are
lazy-loaded on the first ``parse()`` call so that importing this
module does not trigger ONNX / PaddleOCR initialisation.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from backend.documents.parse_adapter.base import (
    ParsedBlock,
    ParsedDocument,
    ParsedFigureAnchor,
    ParsedTable,
    ParseError,
    ParseMeta,
)


class DeepDocAdapter:
    """Parse PDF and DOCX documents using DeepDoc vision + parser modules.

    Parameters
    ----------
    model_dir:
        Path to the DeepDoc ONNX model files.  Defaults to the
        ``DEEPDOC_MODEL_DIR`` environment variable, or a ``models/``
        directory next to this adapter package.
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}

    def __init__(self, model_dir: str | None = None) -> None:
        self._model_dir = model_dir
        self._initialized = False

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _lazy_init(self) -> None:
        """Load ONNX models on first use."""
        if self._initialized:
            return
        # Ensure DEEPDOC_MODEL_DIR is set before vision modules import
        if self._model_dir:
            os.environ.setdefault("DEEPDOC_MODEL_DIR", self._model_dir)
        self._initialized = True

    # ------------------------------------------------------------------
    # parse()
    # ------------------------------------------------------------------

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ParseError(
                f"DeepDocAdapter does not support '{ext}'. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )

        if not path.exists():
            raise ParseError(f"File not found: {file_path}")

        self._lazy_init()
        t0 = time.perf_counter()

        if ext == ".pdf":
            return self._parse_pdf(file_path, t0)
        else:
            return self._parse_docx(file_path, t0)

    # ------------------------------------------------------------------
    # PDF path
    # ------------------------------------------------------------------

    def _parse_pdf(self, file_path: str, t0: float) -> ParsedDocument:
        """Run the DeepDoc PDF pipeline and convert to ParsedDocument."""
        from ._pdf_parser import RAGFlowPdfParser

        parser = RAGFlowPdfParser()
        text_output, tbls_output = parser(str(file_path), need_image=False, zoomin=3, return_html=True)

        warnings: list[str] = []
        blocks = self._convert_text_blocks(text_output, warnings)
        tables, figures = self._convert_tables_figures(tbls_output)

        # M8: Extract OCR confidence scores from parser.boxes
        # parser.boxes is a list of dicts with "text" and optional "score"
        ocr_scores: list[float] = []
        if hasattr(parser, 'boxes') and isinstance(parser.boxes, list):
            for box in parser.boxes:
                if isinstance(box, dict) and "score" in box and box.get("score") is not None:
                    ocr_scores.append(float(box["score"]))

        ocr_confidence_avg = sum(ocr_scores) / len(ocr_scores) if ocr_scores else None

        # M8: Determine parse_path based on OCR ratio
        ocr_ratio = len(ocr_scores) / len(blocks) if blocks else 0.0
        if ocr_ratio >= 0.8:
            parse_path = "ocr"
        elif ocr_ratio <= 0.2:
            parse_path = "native_text"
        elif 0.2 < ocr_ratio < 0.8:
            parse_path = "mixed"
        else:
            parse_path = "unknown"
            if not ocr_scores and blocks:
                warnings.append("Cannot determine parse_path — OCR confidence not available")

        duration_ms = (time.perf_counter() - t0) * 1000
        meta = ParseMeta(
            parse_engine="deepdoc",
            parse_engine_version="1.0",
            parse_duration_ms=duration_ms,
            total_pages=getattr(parser, "total_page", 0),
            parse_warnings=warnings,
            ocr_confidence_avg=ocr_confidence_avg,
            parse_path=parse_path,
        )

        return ParsedDocument(
            filename=Path(file_path).name,
            file_type="pdf",
            blocks=blocks,
            tables=tables,
            figures=figures,
            parse_meta=meta,
        )

    # ------------------------------------------------------------------
    # DOCX path
    # ------------------------------------------------------------------

    def _parse_docx(self, file_path: str, t0: float) -> ParsedDocument:
        """Run the DeepDoc DOCX pipeline and convert to ParsedDocument."""
        from ._docx_parser import RAGFlowDocxParser

        parser = RAGFlowDocxParser()
        sections, tbls = parser(str(file_path))

        warnings: list[str] = []
        blocks: list[ParsedBlock] = []
        for i, (text, style_name) in enumerate(sections):
            if not text.strip():
                continue
            block_type = "heading" if style_name and "heading" in style_name.lower() else "paragraph"
            blocks.append(
                ParsedBlock(
                    block_id=f"b_{i}",
                    page_no=i // 10,  # rough estimate: ~10 paragraphs per page
                    block_type=block_type,  # type: ignore[arg-type]
                    text=text.strip(),
                    order_index=i,
                    style={"style_name": style_name},
                )
            )

        tables: list[ParsedTable] = []
        for table_idx, rows in enumerate(tbls):
            if not rows:
                continue
            md = _rows_to_markdown(rows) if isinstance(rows, list) else str(rows)
            tables.append(
                ParsedTable(
                    table_id=f"t_{table_idx}",
                    page_no=table_idx // 5,
                    cells_markdown=md,
                    cells_structured=rows if isinstance(rows, list) else [],
                )
            )

        duration_ms = (time.perf_counter() - t0) * 1000
        meta = ParseMeta(
            parse_engine="deepdoc",
            parse_engine_version="1.0",
            parse_duration_ms=duration_ms,
            total_pages=0,
            parse_warnings=warnings,
            parse_path="native_text",  # M8: DOCX is always native text
        )

        return ParsedDocument(
            filename=Path(file_path).name,
            file_type="docx",
            blocks=blocks,
            tables=tables,
            parse_meta=meta,
        )

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_text_blocks(text_output: str, warnings: list[str]) -> list[ParsedBlock]:
        """Convert DeepDoc text output to ParsedBlocks.

        DeepDoc text output is newline-separated blocks, each with
        embedded ``@@page\tx0\tx1\ttop\tbottom##`` position tags.
        """
        blocks: list[ParsedBlock] = []
        if not text_output:
            return blocks

        for i, line in enumerate(text_output.split("\n\n")):
            line = line.strip()
            if not line:
                continue

            # Extract position tags
            tags: list[dict[str, object]] = []
            clean_text = line
            for m in re.finditer(
                r"@@([\d-]+)\t([\d.]+)\t([\d.]+)\t([\d.]+)\t([\d.]+)##", line
            ):
                tags.append(
                    {
                        "page": m.group(1),
                        "x0": float(m.group(2)),
                        "x1": float(m.group(3)),
                        "top": float(m.group(4)),
                        "bottom": float(m.group(5)),
                    }
                )
            clean_text = re.sub(r"@@[\d.\t-]+##", "", line).strip()
            if not clean_text:
                continue

            # Determine the primary page for this block
            primary_tag: dict[str, object] = tags[0] if tags else {"page": "1", "x0": 0.0, "x1": 0.0, "top": 0.0, "bottom": 0.0}
            try:
                page_no = int(str(primary_tag["page"]).split("-")[0])
            except (ValueError, IndexError):
                page_no = 1

            block_type = _classify_block_type(clean_text)
            block = ParsedBlock(
                block_id=f"b_{i}",
                page_no=page_no,
                block_type=block_type,  # type: ignore[arg-type]
                text=clean_text,
                bbox=(
                    float(str(primary_tag["x0"])),
                    float(str(primary_tag["x1"])),
                    float(str(primary_tag["top"])),
                    float(str(primary_tag["bottom"])),
                ),
                order_index=i,
            )
            blocks.append(block)

        return blocks

    @staticmethod
    def _convert_tables_figures(
        tbls_output: list,
    ) -> tuple[list[ParsedTable], list[ParsedFigureAnchor]]:
        """Convert DeepDoc table/figure output."""
        tables: list[ParsedTable] = []
        figures: list[ParsedFigureAnchor] = []

        for idx, item in enumerate(tbls_output):
            # item is (PIL_Image | None, content) where content is str or list[str]
            if isinstance(item, (list, tuple)) and len(item) == 2:
                img, content = item
            else:
                continue

            content_str = ""
            cells_md = ""
            cells_structured: list[list[str]] = []

            if isinstance(content, str):
                content_str = content
                # If HTML table, use as markdown
                if content.startswith("<table"):
                    cells_md = content
                else:
                    cells_md = content
            elif isinstance(content, list) and content:
                content_str = "\n".join(str(r) for r in content)
                cells_md = _rows_to_markdown(
                    [[c for c in str(r).split(";")] for r in content]
                )
                cells_structured = [[c for c in str(r).split(";")] for r in content]

            # Heuristic: if content looks like a chart, treat as figure; otherwise table.
            page_no = _extract_page_from_content(content_str, fallback=idx)
            if _looks_like_chart(content_str):
                figures.append(
                    ParsedFigureAnchor(
                        figure_id=f"f_{idx}",
                        page_no=page_no,
                        caption=content_str[:200],
                    )
                )
            else:
                tables.append(
                    ParsedTable(
                        table_id=f"t_{idx}",
                        page_no=page_no,
                        caption="",
                        cells_markdown=cells_md,
                        cells_structured=cells_structured,
                    )
                )

        return tables, figures


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _classify_block_type(text: str) -> str:
    """Heuristic block-type classifier based on structural text patterns.

    Returns a BlockType literal string: heading, list_item, or paragraph.
    """
    head = text.strip().split("\n")[0].strip()
    # Chinese chapter/section headings
    if re.match(
        r"(第[零一二三四五六七八九十百千万\d]+[章节条]|"
        r"[\(（][零一二三四五六七八九十百\d]+[）\)]|"
        r"(PART|Chapter|Section|Article)\s+\w+|"
        r"^[一二三四五六七八九十]、|"
        r"^[0-9]{1,2}\.[0-9]{1,2}?\s)",
        head,
    ):
        return "heading"
    # Figure captions
    if re.match(r"(图|圖|Fig\.?|Figure)\s*[0-9]", head):
        return "figure_caption"
    # Table captions
    if re.match(r"(表|Table|Tab\.?)\s*[0-9]", head):
        return "table_caption"
    # List items
    if re.match(r"^[\s]*[\(（]?[0-9a-zA-Z]{1,2}[\)）.、]|^[\s]*[⚫•➢✓⚠※●○]", head):
        return "list_item"
    # Short all-caps or bold-like lines → likely heading
    if len(head) <= 60 and head.strip().endswith("：") is False and "。" not in head:
        # Heuristic: lines that are short, don't end with punctuation, likely headings
        pass  # fall through to paragraph for safety
    return "paragraph"


def _looks_like_chart(text: str) -> bool:
    """Heuristic: *text* likely describes a chart/figure, not a data table."""
    chart_markers = ["图", "同比", "%", "亿元", "万千瓦", "增长率", "下降", "上升"]
    score = sum(1 for m in chart_markers if m in text[:300])
    return score >= 2


def _extract_page_from_content(text: str, fallback: int = 0) -> int:
    """Try to extract a page number from content text; returns *fallback* if unclear."""
    # Look for page-like patterns
    m = re.search(r"@@(\d+)[\-\t]", text)
    if m:
        return int(m.group(1))
    return fallback


def _rows_to_markdown(rows: list[list[str]]) -> str:
    """Convert a 2-D list of strings to a basic markdown table."""
    if not rows:
        return ""
    lines: list[str] = []
    for i, row in enumerate(rows):
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
        if i == 0 and len(rows) > 1:
            lines.append("| " + " | ".join("---" for _ in row) + " |")
    return "\n".join(lines)
