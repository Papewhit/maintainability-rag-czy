"""Terminology table: in-memory representation loaded from DB, with Aho-Corasick scan."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from backend.rag.terminology.matcher import AhoCorasick, TermMatch, scan_text

logger = logging.getLogger(__name__)


class EntityType(StrEnum):
    PRODUCT_MODEL = "product_model"
    EQUIPMENT = "equipment"
    COMPONENT = "component"
    PARAMETER = "parameter"
    MAINTENANCE_ACTION = "maintenance_action"


@dataclass(frozen=True, slots=True)
class TerminologyEntry:
    canonical: str
    entity_type: EntityType
    variants: tuple[str, ...] = ()
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueryTerminologyResult:
    term_matches: list[TermMatch]
    normalized_query: str
    sparse_expansion: str
    protected_tokens: list[str]


class TerminologyTable:
    """In-memory terminology index built from DB.

    Provides:
    - _by_canonical: canonical -> entry lookup
    - _surface_to_canonical: any surface form (canonical or variant) -> (canonical, entity_type)
    - _aho_corasick: multi-pattern matcher for chunk/query scanning
    """

    def __init__(self) -> None:
        self._by_canonical: dict[str, TerminologyEntry] = {}
        self._surface_to_canonical: dict[str, tuple[str, EntityType]] = {}
        self._aho_corasick: AhoCorasick = AhoCorasick()
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def reload_from_db(self, entries: Sequence[TerminologyEntry]) -> None:
        """Rebuild all in-memory structures from a flat list of entries."""
        self._by_canonical.clear()
        self._surface_to_canonical.clear()
        self._aho_corasick = AhoCorasick()

        for entry in entries:
            key = (entry.entity_type, entry.canonical)
            self._by_canonical[key] = entry
            self._surface_to_canonical[entry.canonical] = (entry.canonical, entry.entity_type)
            for variant in entry.variants:
                v = variant.strip()
                if not v or v == entry.canonical:
                    continue
                # If variant already maps to a different canonical, keep first (longest-match
                # in AC handles ambiguity; _surface_to_canonical is for lookup, not disambiguation).
                if v not in self._surface_to_canonical:
                    self._surface_to_canonical[v] = (entry.canonical, entry.entity_type)

            # Register all surface forms in AC automaton
            surfaces = {entry.canonical}
            surfaces.update(v.strip() for v in entry.variants if v.strip())
            for surface in surfaces:
                self._aho_corasick.add_pattern(surface, entry.canonical, str(entry.entity_type))

        self._aho_corasick.build()
        self._loaded = True
        logger.info("TerminologyTable loaded: %d entries, %d surface forms",
                     len(self._by_canonical), len(self._surface_to_canonical))

    @classmethod
    def load_from_db(cls, db: Session) -> "TerminologyTable":
        """Factory: query all terminology entries from DB and build a loaded table."""
        from backend.infra.db.models import TerminologyEntryModel

        rows = db.query(TerminologyEntryModel).order_by(TerminologyEntryModel.id).all()
        entries: list[TerminologyEntry] = []
        for row in rows:
            entries.append(TerminologyEntry(
                canonical=row.canonical,
                entity_type=EntityType(row.entity_type),
                variants=tuple(row.variants) if row.variants else (),
                description=row.description,
                metadata=row.metadata_json or {},
            ))
        table = cls()
        table.reload_from_db(entries)
        return table

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get(self, entity_type: EntityType, canonical: str) -> TerminologyEntry | None:
        return self._by_canonical.get((entity_type, canonical))

    def resolve_canonical(self, surface: str) -> tuple[str, EntityType] | None:
        return self._surface_to_canonical.get(surface)

    def all_entries(self) -> list[TerminologyEntry]:
        return list(self._by_canonical.values())

    def entry_count(self) -> int:
        return len(self._by_canonical)

    def surface_count(self) -> int:
        return len(self._surface_to_canonical)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def scan_text(self, text: str) -> list[TermMatch]:
        """Scan text for term matches using Aho-Corasick + longest-match dedup."""
        return scan_text(self._aho_corasick, text)

    def query_preflight(self, raw_query: str) -> QueryTerminologyResult:
        """Preflight a user query: scan for entities, normalize, expand.

        Args:
            raw_query: The user's original query string.

        Returns:
            QueryTerminologyResult with entities, normalized_query, sparse_expansion, protected_tokens.
        """
        matches = self.scan_text(raw_query)

        # Normalized query: replace surface forms with canonical forms
        normalized = raw_query
        # Process matches in reverse order (end to start) to preserve positions
        for m in sorted(matches, key=lambda x: -x.start):
            if m.surface != m.canonical:
                normalized = normalized[:m.start] + m.canonical + normalized[m.end:]

        # Sparse expansion: collect all unique variants + canonicals for matched entities
        expansion_parts: list[str] = [raw_query]
        seen_canonicals: set[str] = set()
        for m in matches:
            key = (m.entity_type, m.canonical)
            if key in seen_canonicals:
                continue
            seen_canonicals.add(key)
            entry = self._by_canonical.get(key)
            if entry:
                expansion_parts.append(entry.canonical)
                expansion_parts.extend(entry.variants)

        # Protected tokens: multi-char surface forms that were matched
        protected_tokens: list[str] = []
        seen_surfaces: set[str] = set()
        for m in matches:
            if m.surface not in seen_surfaces and len(m.surface) >= 2:
                seen_surfaces.add(m.surface)
                protected_tokens.append(m.surface)

        # Word-level dedup of sparse_expansion preserving order
        expansion_words: list[str] = []
        seen_tokens: set[str] = set()
        for part in expansion_parts:
            for token in part.split():
                token_lower = token.lower()
                if token_lower not in seen_tokens:
                    seen_tokens.add(token_lower)
                    expansion_words.append(token)

        return QueryTerminologyResult(
            term_matches=matches,
            normalized_query=normalized,
            sparse_expansion=" ".join(expansion_words),
            protected_tokens=protected_tokens,
        )


# Process-level singleton — loaded once at startup, updated on term-table writes.
_terminology_table: TerminologyTable | None = None


def get_terminology_table() -> TerminologyTable:
    """Return the process-level terminology singleton.

    Raises RuntimeError if not yet initialised (should be set during startup).
    """
    if _terminology_table is None:
        raise RuntimeError("TerminologyTable not initialised — call init_terminology_table() at startup")
    return _terminology_table


def set_terminology_table(table: TerminologyTable) -> None:
    global _terminology_table
    _terminology_table = table
