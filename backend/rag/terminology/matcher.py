"""Pure-Python Aho-Corasick automaton for multi-pattern longest-match scanning.

Design Decision 3: pyahocorasick is preferred but optional. This pure-Python
fallback handles up to ~25000 patterns (5000 entries x 5 variants) with acceptable
performance for chunk-level scanning (~500 chars, near-instant). Full collection
rescan (100k chunks) completes in minutes, not seconds, but is acceptable for v1
given admin-triggered frequency (weekly/monthly).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TermMatch:
    surface: str
    canonical: str
    entity_type: str
    start: int
    end: int


class AhoCorasick:
    """Pure-Python Aho-Corasick automaton — linear time matching w/ failure links."""

    def __init__(self) -> None:
        # trie nodes: dict of child edges keyed by character
        self._trie: list[dict[str, int]] = [{}]
        # output for each node: list of (canonical, entity_type, pattern_len)
        self._output: list[list[tuple[str, str, int]]] = [[]]
        self._fail: list[int] = [0]
        self._built = False

    def add_pattern(self, pattern: str, canonical: str, entity_type: str) -> None:
        """Insert a pattern into the trie. Multiple patterns may share a surface form."""
        if self._built:
            raise RuntimeError("Cannot add patterns after build()")
        node = 0
        for ch in pattern:
            nxt = self._trie[node].get(ch)
            if nxt is None:
                nxt = len(self._trie)
                self._trie[node][ch] = nxt
                self._trie.append({})
                self._output.append([])
                self._fail.append(0)
            node = nxt
        self._output[node].append((canonical, entity_type, len(pattern)))

    def build(self) -> None:
        """Build failure links via BFS (must be called after all add_pattern calls)."""
        if self._built:
            return
        q: deque[int] = deque()
        # Initialize failure links for depth-1 nodes
        for ch, child in self._trie[0].items():
            self._fail[child] = 0
            q.append(child)
        # BFS to build rest
        while q:
            r = q.popleft()
            for ch, child in self._trie[r].items():
                q.append(child)
                f = self._fail[r]
                while f != 0 and ch not in self._trie[f]:
                    f = self._fail[f]
                if ch in self._trie[f]:
                    self._fail[child] = self._trie[f][ch]
                else:
                    self._fail[child] = 0
                # Merge outputs from failure node
                self._output[child].extend(self._output[self._fail[child]])
        self._built = True

    def scan(self, text: str) -> list[TermMatch]:
        """Scan text and return all term matches.

        Returns matches sorted by (start, -length) to facilitate longest-match
        non-overlapping selection. The caller should apply longest-match dedup.
        """
        if not self._built:
            self.build()
        matches: list[TermMatch] = []
        node = 0
        for i, ch in enumerate(text):
            while node != 0 and ch not in self._trie[node]:
                node = self._fail[node]
            nxt = self._trie[node].get(ch)
            node = nxt if nxt is not None else 0
            if self._output[node]:
                for canonical, entity_type, pat_len in self._output[node]:
                    start = i - pat_len + 1
                    matches.append(TermMatch(
                        surface=text[start:i + 1],
                        canonical=canonical,
                        entity_type=entity_type,
                        start=start,
                        end=i + 1,
                    ))
        return matches


def longest_non_overlapping(matches: list[TermMatch]) -> list[TermMatch]:
    """Select longest, non-overlapping subset from raw AC matches.

    Strategy:
    1. Sort by (start asc, length desc) — longest match wins at each position.
    2. Iterate, skipping any match whose [start, end) overlaps with the last kept match.
    """
    if not matches:
        return []
    # Sort: earliest start first; for same start, longest pattern first
    matches.sort(key=lambda m: (m.start, -(m.end - m.start)))
    kept: list[TermMatch] = []
    for m in matches:
        if not kept:
            kept.append(m)
            continue
        last = kept[-1]
        # If this match starts after or at the end of the last kept, no overlap
        if m.start >= last.end:
            kept.append(m)
        # Otherwise overlap: since we sort by (start, -length), the first match
        # at any start position is the longest, so skip shorter overlapping ones.
    return kept


def scan_text(automaton: AhoCorasick, text: str) -> list[TermMatch]:
    """Full scan: AC all-matches → longest non-overlapping selection."""
    raw = automaton.scan(text)
    return longest_non_overlapping(raw)


# Optional pyahocorasick accelerator.
# Falls back silently to the pure-Python AhoCorasick above.
try:
    import ahocorasick as _ac  # pyahocorasick

    class PyAhoCorasick:
        """Thin wrapper around pyahocorasick.Automaton for our scan interface."""

        def __init__(self) -> None:
            self._auto = _ac.Automaton()
            self._built = False

        def add_pattern(self, pattern: str, canonical: str, entity_type: str) -> None:
            if self._built:
                raise RuntimeError("Cannot add patterns after build()")
            self._auto.add_word(pattern, (canonical, entity_type, len(pattern)))

        def build(self) -> None:
            if self._built:
                return
            self._auto.make_automaton()
            self._built = True

        def scan(self, text: str) -> list[TermMatch]:
            if not self._built:
                self.build()
            matches: list[TermMatch] = []
            for end, (canonical, entity_type, pat_len) in self._auto.iter(text):
                start = end - pat_len + 1
                matches.append(TermMatch(
                    surface=text[start:end + 1],
                    canonical=canonical,
                    entity_type=entity_type,
                    start=start,
                    end=end + 1,
                ))
            return matches

    # Override with accelerated version
    AhoCorasick = PyAhoCorasick  # type: ignore[misc,assignment]

except ImportError:
    pass
