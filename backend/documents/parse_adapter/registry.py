"""Extension-based dispatch to ParseAdapter instances.

Module-level ``get_registry()`` returns a lazily-built default
registry wired with DeepDoc (PDF/DOCX) and Excel parsers.
"""

from __future__ import annotations

from backend.documents.parse_adapter.base import ParseAdapter, UnsupportedFileType


class AdapterRegistry:
    """Maps file extensions (without dot) to ParseAdapter instances.

    Usage::

        registry = AdapterRegistry()
        registry.register("pdf", deepdoc_adapter)
        registry.register("xlsx", excel_adapter)

        adapter = registry.get_adapter("report.pdf")
        doc = adapter.parse("/path/to/report.pdf")
    """

    def __init__(self) -> None:
        self._adapters: dict[str, ParseAdapter] = {}

    def register(self, extension: str, adapter: ParseAdapter) -> None:
        """Register *adapter* for the given file extension(s).

        *extension* may be a single extension like ``".pdf"`` or ``"pdf"``
        (dot is stripped automatically).
        """
        ext = extension.lower().lstrip(".")
        self._adapters[ext] = adapter

    def get_adapter(self, filename: str) -> ParseAdapter:
        """Return the adapter registered for *filename*'s extension.

        Args:
            filename: A bare filename or full path.

        Returns:
            The registered ParseAdapter.

        Raises:
            UnsupportedFileType: No adapter is registered for this extension.
        """
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        adapter = self._adapters.get(ext)
        if adapter is None:
            raise UnsupportedFileType(
                f"No parser adapter registered for '.{ext}' files"
            )
        return adapter

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Return the set of registered extensions."""
        return frozenset(self._adapters.keys())


# ------------------------------------------------------------------
# Module-level default registry
# ------------------------------------------------------------------

_default_registry: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    """Return the default AdapterRegistry (lazy singleton).

    On first call, wires all standard adapters:
    - ``.pdf``, ``.docx``, ``.doc`` → DeepDocAdapter
    - ``.xlsx``, ``.xls``        → ExcelParser
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = _build_default_registry()
    return _default_registry


def _build_default_registry() -> AdapterRegistry:
    from backend.documents.parse_adapter.deepdoc.adapter import DeepDocAdapter
    from backend.documents.parse_adapter.excel import ExcelParser

    registry = AdapterRegistry()

    deepdoc = DeepDocAdapter()
    for ext in ("pdf", "docx", "doc"):
        registry.register(ext, deepdoc)

    excel = ExcelParser()
    for ext in ("xlsx", "xls"):
        registry.register(ext, excel)

    return registry
