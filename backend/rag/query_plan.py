"""QueryPlan: parse user query into semantic_query + metadata constraints + route.

Design principles (from all-in-rag):
  - Query Construction: separate semantic_query from metadata_filter
  - Query Routing: rule-based routing to scoped_hybrid or global_hybrid
  - Model numbers are only removed from semantic_query when high-confidence
    file matches occur (scope_mode in {filter, boost}); otherwise retained.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Literal

import jieba

from backend.config import MILVUS_COLLECTION
from backend.shared.filename_normalization import normalize_filename_for_match

logger = logging.getLogger(__name__)

# --- Configuration from env ---
DOC_SCOPE_MATCH_FILTER = float(os.getenv("DOC_SCOPE_MATCH_FILTER", "0.85"))
DOC_SCOPE_MATCH_BOOST = float(os.getenv("DOC_SCOPE_MATCH_BOOST", "0.60"))
DOC_SCOPE_FILENAME_REGISTRY_REFRESH_SECONDS = int(
    os.getenv("DOC_SCOPE_FILENAME_REGISTRY_REFRESH_SECONDS", "600")
)
DOC_SCOPE_MATCH_TRACE_MIN = float(os.getenv("DOC_SCOPE_MATCH_TRACE_MIN", "0.30"))
_REGISTRY_CACHE_MAX_KEYS = int(os.getenv("DOC_SCOPE_FILENAME_REGISTRY_CACHE_KEYS", "8"))

# --- Regex patterns ---
_BOOK_TITLE_RE = re.compile(r"《([^》]+)》")
_MODEL_NUMBER_RE = re.compile(r"[A-Z]{2,}\d{3,}[A-Z0-9]*")
_CHAPTER_RE = re.compile(r"第\s*[一二三四五六七八九十百千万零两\d]+\s*章|附录\s*[A-Z\d一二三四五六七八九十]")
_BOOK_TITLE_PREFIX_RE = re.compile(r"《[^》]+》\s*中[，,]?\s*")


@dataclass(frozen=True)
class ConsumedSpan:
    kind: Literal["document", "anchor", "model"]
    text: str
    start: int
    end: int
    owner: Literal["scope", "anchor"]


@dataclass
class QueryPlan:
    raw_query: str
    semantic_query: str
    clean_query: str
    doc_hints: list[str] = field(default_factory=list)
    matched_files: list[tuple[str, float]] = field(default_factory=list)
    scope_mode: Literal["filter", "boost", "none"] = "none"
    heading_hint: str | None = None
    anchors: list[str] = field(default_factory=list)
    model_numbers: list[str] = field(default_factory=list)
    intent_type: str | None = None
    route: Literal["scoped_hybrid", "global_hybrid"] = "global_hybrid"
    consumed_spans: list[ConsumedSpan] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "semantic_query": self.semantic_query,
            "clean_query": self.clean_query,
            "doc_hints": self.doc_hints,
            "matched_files": [(f, round(s, 3)) for f, s in self.matched_files],
            "scope_mode": self.scope_mode,
            "heading_hint": self.heading_hint,
            "anchors": self.anchors,
            "model_numbers": self.model_numbers,
            "intent_type": self.intent_type,
            "route": self.route,
            "consumed_spans": [
                {
                    "kind": span.kind,
                    "text": span.text,
                    "start": span.start,
                    "end": span.end,
                    "owner": span.owner,
                }
                for span in self.consumed_spans
            ],
        }


@dataclass(frozen=True)
class SubQuery:
    query: str
    domain: str
    priority: int

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("sub-query text must not be empty")
        if not self.domain.strip():
            raise ValueError("sub-query domain must not be empty")
        if self.priority not in {1, 2, 3}:
            raise ValueError("sub-query priority must be 1, 2, or 3")


@dataclass(frozen=True)
class RetrievalScope:
    """Shared deterministic retrieval scope for every comprehensive branch."""

    scope_mode: Literal["filter", "boost", "none"] = "none"
    matched_files: tuple[tuple[str, float], ...] = ()
    doc_hints: tuple[str, ...] = ()
    anchors: tuple[str, ...] = ()
    heading_hint: str | None = None
    source: Literal[
        "none",
        "document_hints",
        "explicit_closed_scope",
        "context_files",
    ] = "none"

    def __post_init__(self) -> None:
        if self.scope_mode in {"filter", "boost"} and not self.matched_files:
            raise ValueError("active retrieval scope requires matched files")
        if self.scope_mode == "none" and self.matched_files:
            raise ValueError("matched files require an active retrieval scope")


@dataclass(frozen=True)
class PreciseQueryPlan:
    raw_query: str
    semantic_query: str
    clean_query: str
    doc_hints: tuple[str, ...] = ()
    scope_mode: Literal["filter", "boost", "none"] = "none"
    matched_files: tuple[tuple[str, float], ...] = ()
    heading_hint: str | None = None
    anchors: tuple[str, ...] = ()
    model_numbers: tuple[str, ...] = ()
    intent_type: str | None = None
    target_granularity: Literal["paragraph", "table", "step_list", "figure"] = "paragraph"
    route: Literal["scoped_hybrid", "global_hybrid"] = "global_hybrid"
    consumed_spans: tuple[ConsumedSpan, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "semantic_query": self.semantic_query,
            "clean_query": self.clean_query,
            "doc_hints": list(self.doc_hints),
            "matched_files": [(name, round(score, 3)) for name, score in self.matched_files],
            "scope_mode": self.scope_mode,
            "heading_hint": self.heading_hint,
            "anchors": list(self.anchors),
            "model_numbers": list(self.model_numbers),
            "intent_type": self.intent_type,
            "target_granularity": self.target_granularity,
            "route": self.route,
            "consumed_spans": [
                {
                    "kind": span.kind,
                    "text": span.text,
                    "start": span.start,
                    "end": span.end,
                    "owner": span.owner,
                }
                for span in self.consumed_spans
            ],
        }


@dataclass(frozen=True)
class ComprehensiveQueryPlan:
    raw_query: str
    clean_query: str
    analysis_type: Literal["design_reuse", "comparison", "procedure_synthesis", "general"]
    sub_queries: tuple[SubQuery, ...]
    coverage_domains: tuple[str, ...]
    postprocess_profile: str = "quality_first_v1"
    retrieval_scope: RetrievalScope = field(default_factory=RetrievalScope)

    def __post_init__(self) -> None:
        if not self.clean_query.strip():
            raise ValueError("comprehensive clean_query must not be empty")
        if not self.sub_queries:
            raise ValueError("comprehensive plan requires at least one sub-query")


@dataclass(frozen=True)
class ComprehensiveRetrievalBranch:
    branch_id: str
    branch_kind: Literal["baseline", "sub_query"]
    query: str
    domain: str | None
    priority: int

    def __post_init__(self) -> None:
        if not self.branch_id.strip() or not self.query.strip():
            raise ValueError("retrieval branch id and query must not be empty")
        if self.priority not in {1, 2, 3}:
            raise ValueError("retrieval branch priority must be 1, 2, or 3")
        if self.branch_kind == "baseline" and self.branch_id != "baseline":
            raise ValueError("baseline branch must use stable id 'baseline'")

    @classmethod
    def baseline(cls, clean_query: str) -> "ComprehensiveRetrievalBranch":
        return cls(
            branch_id="baseline",
            branch_kind="baseline",
            query=clean_query,
            domain=None,
            priority=2,
        )

    @classmethod
    def from_sub_query(cls, sub_query: SubQuery, *, index: int) -> "ComprehensiveRetrievalBranch":
        return cls(
            branch_id=f"sub_query_{index}",
            branch_kind="sub_query",
            query=sub_query.query,
            domain=sub_query.domain,
            priority=sub_query.priority,
        )


IntentQueryPlan = PreciseQueryPlan | ComprehensiveQueryPlan


def precise_plan_from_legacy(
    plan: QueryPlan,
    *,
    target_granularity: Literal["paragraph", "table", "step_list", "figure"] = "paragraph",
) -> PreciseQueryPlan:
    return PreciseQueryPlan(
        raw_query=plan.raw_query,
        semantic_query=plan.semantic_query,
        clean_query=plan.clean_query,
        doc_hints=tuple(plan.doc_hints),
        matched_files=tuple(plan.matched_files),
        scope_mode=plan.scope_mode,
        heading_hint=plan.heading_hint,
        anchors=tuple(plan.anchors),
        model_numbers=tuple(plan.model_numbers),
        intent_type=plan.intent_type,
        target_granularity=target_granularity,
        route=plan.route,
        consumed_spans=tuple(plan.consumed_spans),
    )


def build_compatible_precise_plan(
    raw_query: str,
    *,
    query_plan_enabled: bool,
    filename_registry: list[dict[str, str]] | None = None,
    context_files: list[str] | None = None,
) -> PreciseQueryPlan:
    if not query_plan_enabled:
        return PreciseQueryPlan(
            raw_query=raw_query,
            semantic_query=raw_query,
            clean_query=raw_query,
            scope_mode="none",
            route="global_hybrid",
        )
    return precise_plan_from_legacy(
        parse_query_plan(
            raw_query,
            filename_registry=filename_registry,
            context_files=context_files,
        )
    )


def _normalize_filename(name: str) -> str:
    """Normalize filename for matching: strip extension, lower, remove suffixes."""
    return normalize_filename_for_match(name)


def _filename_match_score(query_hint: str, filename_norm: str) -> float:
    """Compute compound match score between a query hint and normalized filename."""
    if query_hint == filename_norm:
        return 1.0
    if query_hint in filename_norm or filename_norm in query_hint:
        return 0.95

    hint_tokens = set(jieba.cut(query_hint))
    file_tokens = set(jieba.cut(filename_norm))
    token_coverage = len(hint_tokens & file_tokens) / max(len(hint_tokens), 1)

    seq_ratio = SequenceMatcher(None, query_hint, filename_norm).ratio()

    return max(token_coverage, seq_ratio)


def _match_doc_hints(
    doc_hints: list[str],
    filename_registry: list[dict[str, str]],
) -> list[tuple[str, float]]:
    """Match doc_hints against filename registry, return (filename, score) pairs."""
    scored: list[tuple[str, float]] = []
    for hint in doc_hints:
        hint_norm = _normalize_filename(hint)
        if not hint_norm:
            continue
        for entry in filename_registry:
            score = _filename_match_score(hint_norm, entry["normalized"])
            if score >= DOC_SCOPE_MATCH_TRACE_MIN:
                scored.append((entry["raw"], score))

    # Deduplicate by filename, keeping best score
    best: dict[str, float] = {}
    for filename, score in scored:
        best[filename] = max(best.get(filename, 0.0), score)

    result = sorted(best.items(), key=lambda x: -x[1])
    return result


# --- Lazy filename registry ---

_registry_cache: OrderedDict[str, tuple[list[dict[str, str]], float]] = OrderedDict()


def _index_version_from_cache(cache_client: Any = None) -> str:
    if not cache_client:
        return "0"
    try:
        if hasattr(cache_client, "get_string"):
            return str(cache_client.get_string("milvus_index_version") or "0")
        value = cache_client.get("milvus_index_version")
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return str(value or "0")
    except Exception:
        return "0"


def _registry_cache_key(collection: str, index_version: str) -> str:
    # RedisCache prefixes this logical key with "ragtenance:", yielding
    # ragtenance:filename_registry:{collection}:v{milvus_index_version}.
    return f"filename_registry:{collection}:v{index_version}"


def _remember_registry(cache_key: str, entries: list[dict[str, str]], cached_at: float) -> None:
    _registry_cache[cache_key] = (entries, cached_at)
    _registry_cache.move_to_end(cache_key)
    while len(_registry_cache) > max(1, _REGISTRY_CACHE_MAX_KEYS):
        _registry_cache.popitem(last=False)


def _registry_from_process_cache(cache_key: str, now: float, refresh_interval: int) -> list[dict[str, str]] | None:
    cached = _registry_cache.get(cache_key)
    if not cached:
        return None
    cached_entries, cached_at = cached
    if now - cached_at >= refresh_interval:
        return None
    _registry_cache.move_to_end(cache_key)
    return cached_entries


def _registry_from_redis(cache_client: Any, cache_key: str) -> list[dict[str, str]]:
    if not cache_client:
        return []
    try:
        if hasattr(cache_client, "get_json"):
            value = cache_client.get_json(cache_key)
            return value if isinstance(value, list) else []
        return _decode_registry(cache_client.get(cache_key))
    except Exception:
        return []


def _store_registry_in_redis(
    cache_client: Any,
    cache_key: str,
    entries: list[dict[str, str]],
    ttl_seconds: int,
) -> None:
    if not cache_client or not entries:
        return
    try:
        if hasattr(cache_client, "set_json"):
            cache_client.set_json(cache_key, entries, ttl=ttl_seconds)
            return
        import json

        cache_client.setex(cache_key, ttl_seconds, json.dumps(entries, ensure_ascii=False))
    except Exception:
        return


def get_filename_registry(milvus_manager: Any, cache_client: Any = None) -> list[dict[str, str]]:
    """Get or refresh the filename registry from Milvus (with Redis caching)."""
    collection = MILVUS_COLLECTION
    index_version = _index_version_from_cache(cache_client)
    cache_key = _registry_cache_key(collection, index_version)
    now = time.time()
    refresh_interval = DOC_SCOPE_FILENAME_REGISTRY_REFRESH_SECONDS

    cached_entries = _registry_from_process_cache(cache_key, now, refresh_interval)
    if cached_entries is not None:
        return cached_entries

    entries = _registry_from_redis(cache_client, cache_key)
    if entries:
        _remember_registry(cache_key, entries, now)
        return entries

    # Query Milvus for distinct filenames
    entries = _query_filenames_from_milvus(milvus_manager)

    _store_registry_in_redis(cache_client, cache_key, entries, refresh_interval * 2)
    _remember_registry(cache_key, entries, now)
    return entries


def _decode_registry(data: Any) -> list[dict[str, str]]:
    """Decode registry data from Redis cache."""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if isinstance(data, str):
        import json
        try:
            return json.loads(data)
        except Exception:
            return []
    return []


def _query_filenames_from_milvus(milvus_manager: Any) -> list[dict[str, str]]:
    """Query Milvus for distinct filenames at leaf level."""
    entries: list[dict[str, str]] = []
    try:
        leaf_level = int(os.getenv("LEAF_RETRIEVE_LEVEL", "3"))
        filenames = milvus_manager.query_unique_filenames(
            filter_expr=f"chunk_level == {leaf_level}",
        )
        for f in filenames:
            entries.append({
                "raw": f,
                "normalized": _normalize_filename(f),
            })
    except Exception as exc:
        logger.warning("Failed to query filename registry from Milvus: %s", exc)
    return entries


# --- Main parser ---

def parse_query_plan(
    raw_query: str,
    filename_registry: list[dict[str, str]] | None = None,
    context_files: list[str] | None = None,
    additional_anchors: list[str] | None = None,
    *,
    fallback_empty_queries: bool = True,
    preferred_scope_mode: Literal["filter", "boost", "none"] | None = None,
) -> QueryPlan:
    """Parse raw query into a QueryPlan with semantic_query, doc_hints, and route.

    Args:
        raw_query: Original user query.
        filename_registry: List of {"raw": ..., "normalized": ...} dicts.
        context_files: User-explicit context files (highest priority).
    """
    # 1. Extract 《》 book titles, retaining spans until scope ownership is known.
    book_title_matches = list(_BOOK_TITLE_RE.finditer(raw_query))
    book_titles = [match.group(1) for match in book_title_matches]
    doc_hints = list(book_titles)

    # 2. Extract model numbers
    model_numbers = _MODEL_NUMBER_RE.findall(raw_query)

    # 3. Extract chapter/appendix anchors
    document_ranges = [(match.start(), match.end()) for match in book_title_matches]

    def inside_document_hint(start: int, end: int) -> bool:
        return any(doc_start <= start and end <= doc_end for doc_start, doc_end in document_ranges)

    anchor_spans: list[tuple[str, int, int]] = [
        (match.group(0), match.start(), match.end())
        for match in _CHAPTER_RE.finditer(raw_query)
        if not inside_document_hint(match.start(), match.end())
    ]
    occupied_anchor_ranges = {(start, end) for _, start, end in anchor_spans}
    for anchor in additional_anchors or []:
        if not anchor:
            continue
        for match in re.finditer(re.escape(anchor), raw_query):
            if inside_document_hint(match.start(), match.end()):
                continue
            marker = (match.start(), match.end())
            if marker not in occupied_anchor_ranges:
                anchor_spans.append((anchor, match.start(), match.end()))
                occupied_anchor_ranges.add(marker)
    anchor_spans.sort(key=lambda item: (item[1], item[2]))
    anchors = list(dict.fromkeys(text for text, _, _ in anchor_spans))

    # 5. Match doc_hints against filename registry
    matched_files: list[tuple[str, float]] = []
    model_scope_matches: dict[str, set[str]] = {}
    scope_mode: Literal["filter", "boost", "none"] = "none"

    if context_files:
        effective_registry = [
            {"raw": context_file, "normalized": _normalize_filename(context_file)}
            for context_file in context_files
        ]
    else:
        effective_registry = list(filename_registry or [])

    if effective_registry and doc_hints:
        matched_files = _match_doc_hints(doc_hints, effective_registry)

        # Also try matching model numbers against filenames
        if model_numbers:
            model_hints = matched_files[:]
            for mn in model_numbers:
                mn_matches = _match_doc_hints([mn], effective_registry)
                model_scope_matches[mn] = {
                    filename
                    for filename, score in mn_matches
                    if score >= DOC_SCOPE_MATCH_BOOST
                }
                for f, s in mn_matches:
                    # Only add if not already present with higher score
                    existing = [i for i, (ef, _) in enumerate(model_hints) if ef == f]
                    if existing:
                        idx = existing[0]
                        model_hints[idx] = (f, max(model_hints[idx][1], s))
                    else:
                        model_hints.append((f, s))
            matched_files = sorted(model_hints, key=lambda x: -x[1])

    # Determine scope_mode based on best match score
    routable_matches = [(f, score) for f, score in matched_files if score >= DOC_SCOPE_MATCH_BOOST]
    if routable_matches:
        best_score = routable_matches[0][1]
        if preferred_scope_mode is not None:
            scope_mode = preferred_scope_mode
        elif best_score >= DOC_SCOPE_MATCH_FILTER:
            scope_mode = "filter"
        elif best_score >= DOC_SCOPE_MATCH_BOOST:
            scope_mode = "boost"

    # Explicit attached files are always the final hard scope, independent of LLM hints.
    if context_files:
        scope_mode = "filter"
        matched_files = [(f, 1.0) for f in context_files]

    # 6. Build clean/semantic queries only from spans with an established owner.
    consumed_spans: list[ConsumedSpan] = [
        ConsumedSpan(kind="anchor", text=text, start=start, end=end, owner="anchor")
        for text, start, end in anchor_spans
    ]
    if scope_mode in {"filter", "boost"}:
        for match in book_title_matches:
            hint_matches = _match_doc_hints([match.group(1)], effective_registry)
            if not any(score >= DOC_SCOPE_MATCH_BOOST for _, score in hint_matches):
                continue
            end = match.end()
            suffix = re.match(r"\s*中[，,]?\s*", raw_query[end:])
            if suffix:
                end += suffix.end()
            consumed_spans.append(
                ConsumedSpan(
                    kind="document",
                    text=raw_query[match.start():end],
                    start=match.start(),
                    end=end,
                    owner="scope",
                )
            )

        scoped_filenames = {filename for filename, _ in matched_files}
        for model_number in model_numbers:
            if not (model_scope_matches.get(model_number, set()) & scoped_filenames):
                continue
            for match in re.finditer(re.escape(model_number), raw_query):
                consumed_spans.append(
                    ConsumedSpan(
                        kind="model",
                        text=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        owner="scope",
                    )
                )

    clean_query = _remove_consumed_spans(raw_query, consumed_spans)
    clean_query = _clean_retrieval_text(clean_query)
    semantic_query = clean_query

    if fallback_empty_queries and not semantic_query:
        semantic_query = raw_query

    if fallback_empty_queries and not clean_query:
        clean_query = raw_query

    # Extract a heading hint after confirmed structural spans have been removed.
    heading_hint = None
    heading_match = re.match(r"^(?:如何|怎么|怎样)?\s*(.+?)[？?]?\s*$", clean_query)
    if heading_match:
        heading_hint = heading_match.group(1).strip()

    # 8. Route determination (tightened rules)
    route: Literal["scoped_hybrid", "global_hybrid"]
    if scope_mode in {"filter", "boost"}:
        route = "scoped_hybrid"
    else:
        route = "global_hybrid"

    return QueryPlan(
        raw_query=raw_query,
        semantic_query=semantic_query,
        clean_query=clean_query,
        doc_hints=doc_hints,
        matched_files=matched_files,
        scope_mode=scope_mode,
        heading_hint=heading_hint,
        anchors=anchors,
        model_numbers=model_numbers,
        intent_type=None,
        route=route,
        consumed_spans=consumed_spans,
    )


def _remove_consumed_spans(text: str, spans: list[ConsumedSpan]) -> str:
    if not spans:
        return text
    chars = list(text)
    for span in spans:
        for index in range(max(0, span.start), min(len(chars), span.end)):
            chars[index] = " "
    return "".join(chars)


def _clean_retrieval_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[，,、；;：:\s]+", "", text)
    return text.strip()


# --- Terminology preflight ---------------------------------------------------


def terminology_preflight(semantic_query: str) -> dict | None:
    """Run terminology preflight on a user query.

    Returns a dict with term_matches, normalized_query, sparse_expansion,
    and protected_tokens keys, or None if the terminology table is not loaded.
    """
    try:
        from backend.rag.terminology.table import get_terminology_table
        table = get_terminology_table()
    except RuntimeError:
        return None
    if not table.is_loaded:
        return None
    result = table.query_preflight(semantic_query)
    return {
        "term_matches": [
            {
                "surface": m.surface,
                "canonical": m.canonical,
                "entity_type": m.entity_type,
                "start": m.start,
                "end": m.end,
            }
            for m in result.term_matches
        ],
        "normalized_query": result.normalized_query,
        "sparse_expansion": result.sparse_expansion,
        "protected_tokens": result.protected_tokens,
    }
