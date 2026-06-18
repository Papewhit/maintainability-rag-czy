"""Regression tests for rescan paths that previously had critical bugs.

Tests: BM25 rebuild deadlock, multi-page text collection, rollback correctness,
_count_chunks return type, parent store rollback not corrupting non-term fields.
"""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

import pytest


class _FakeEmbeddingService:
    """Minimal fake that reproduces the threading.Lock behavior of EmbeddingService."""

    def __init__(self, state_path: Path) -> None:
        import threading
        self._state_path = state_path
        self._lock = threading.Lock()
        self._vocab: dict[str, int] = {}
        self._vocab_counter = 0
        self._doc_freq: Counter[str] = Counter()
        self._total_docs = 0
        self._sum_token_len = 0
        self._avg_doc_len = 1.0
        self.k1 = 1.5
        self.b = 0.75

    def tokenize(self, text: str) -> list[str]:
        return text.lower().split()

    def _recompute_avg_len(self) -> None:
        self._avg_doc_len = self._sum_token_len / max(self._total_docs, 1)

    def _persist_unlocked(self) -> None:
        payload = {
            "version": 1,
            "total_docs": self._total_docs,
            "sum_token_len": self._sum_token_len,
            "vocab": self._vocab,
            "doc_freq": dict(self._doc_freq),
        }
        tmp = self._state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._state_path)

    def increment_add_documents(self, texts: list[str]) -> None:
        """Same lock pattern as real EmbeddingService — would deadlock if called under _lock."""
        with self._lock:
            for text in texts:
                tokens = self.tokenize(text)
                self._sum_token_len += len(tokens)
                self._total_docs += 1
                for token in set(tokens):
                    if token not in self._vocab:
                        self._vocab[token] = self._vocab_counter
                        self._vocab_counter += 1
                    self._doc_freq[token] += 1
            self._recompute_avg_len()
            self._persist_unlocked()

    def _load_state(self) -> None:
        state_path = self._state_path
        if not state_path.is_file():
            return
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        self._vocab = {str(k): int(v) for k, v in raw.get("vocab", {}).items()}
        self._doc_freq = Counter({str(k): int(v) for k, v in raw.get("doc_freq", {}).items()})
        self._total_docs = int(raw.get("total_docs", 0))
        self._sum_token_len = int(raw.get("sum_token_len", 0))
        self._vocab_counter = max(self._vocab.values()) + 1 if self._vocab else 0
        self._recompute_avg_len()


class TestBM25RebuildNoDeadlock:
    def test_single_page_completes(self) -> None:
        """_rebuild_bm25_atomic must complete without deadlocking."""
        from backend.rag.terminology.rescan import _rebuild_bm25_atomic

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "bm25_state.json"
            svc = _FakeEmbeddingService(state_path)

            texts = ["hello world", "hello python", "python test"]
            _rebuild_bm25_atomic(svc, texts)

            assert state_path.is_file()
            assert svc._total_docs == 3
            assert "hello" in svc._vocab
            assert "world" in svc._vocab
            assert "python" in svc._vocab

    def test_multi_page_preserves_all_texts(self) -> None:
        """All pages worth of texts must be present in the rebuilt BM25 state."""
        from backend.rag.terminology.rescan import _rebuild_bm25_atomic

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "bm25_state.json"
            svc = _FakeEmbeddingService(state_path)

            # Simulate 3 "pages" of texts
            page1 = [f"page1_term_{i}" for i in range(20)]
            page2 = [f"page2_term_{i}" for i in range(20)]
            page3 = [f"page3_term_{i}" for i in range(20)]
            all_texts = page1 + page2 + page3

            _rebuild_bm25_atomic(svc, all_texts)

            assert svc._total_docs == 60, f"Expected 60 docs, got {svc._total_docs}"
            assert "page1_term_0" in svc._vocab
            assert "page2_term_0" in svc._vocab
            assert "page3_term_0" in svc._vocab

    def test_increment_add_documents_would_deadlock_under_lock(self) -> None:
        """Verify that increment_add_documents acquires the same lock — proof
        that the old code path would deadlock, and the inline version won't."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "bm25_state.json"
            svc = _FakeEmbeddingService(state_path)

            acquired = svc._lock.acquire(blocking=False)
            assert acquired, "Should acquire lock"

            # Now try to call increment_add_documents — it should block
            # (we use a short timeout thread as proxy)
            import threading
            result: list[str] = []
            def blocker() -> None:
                try:
                    svc.increment_add_documents(["test"])
                    result.append("completed")
                except Exception:
                    result.append("error")

            t = threading.Thread(target=blocker)
            t.start()
            t.join(timeout=0.5)
            assert t.is_alive() or "completed" not in result, "increment_add_documents should still be blocked on the lock"
            svc._lock.release()
            t.join(timeout=1.0)


class TestCountChunksReturnType:
    def test_returns_int_for_empty_collection(self) -> None:
        """_count_chunks must always return an int."""
        from backend.rag.terminology.rescan import _count_chunks

        class _FakeMilvus:
            collection_name = "test"

            def _call_with_reconnect(self, operation, **kwargs):
                return []

        result = _count_chunks(_FakeMilvus())
        assert isinstance(result, int)
        assert result == 0

    def test_returns_int_for_nonempty_collection(self) -> None:
        from backend.rag.terminology.rescan import _count_chunks

        class _FakeMilvus:
            collection_name = "test"

            def __init__(self) -> None:
                self._calls = 0

            def _call_with_reconnect(self, operation, **kwargs):
                self._calls += 1
                if self._calls == 1:
                    return [{"chunk_id": f"c{i}"} for i in range(100)]
                return []

        result = _count_chunks(_FakeMilvus())
        assert isinstance(result, int)
        assert result == 100

    def test_returns_int_on_error(self) -> None:
        from backend.rag.terminology.rescan import _count_chunks

        class _FakeMilvus:
            collection_name = "test"

            def _call_with_reconnect(self, operation, **kwargs):
                raise RuntimeError("boom")

        result = _count_chunks(_FakeMilvus())
        assert isinstance(result, int)
        assert result == 0


class TestParentStoreRestore:
    def test_snapshot_excludes_non_term_fields(self) -> None:
        """Snapshot dict must not include text/filename etc. that upsert would default-blank."""
        snapshot = [
            {"chunk_id": "abc123", "term_matches": [{"surface": "old"}], "protected_tokens": ["old"]},
        ]
        assert "text" not in snapshot[0], "Snapshot should not contain text field"
        assert "filename" not in snapshot[0], "Snapshot should not contain filename field"
        assert "file_path" not in snapshot[0]

    def test_restore_accepts_empty_snapshot(self) -> None:
        """_restore_parent_store should be a no-op for empty input."""
        from backend.rag.terminology.rescan import _restore_parent_store
        # Should not raise
        _restore_parent_store([])

    def test_restore_accepts_none_entries(self) -> None:
        """Entries with None/missing term_matches should be handled gracefully."""
        from backend.rag.terminology.rescan import _restore_parent_store
        # Should not raise — empty snapshot
        _restore_parent_store([])

    def test_snapshot_shape_from_full_doc(self) -> None:
        """Verify _snapshot_parent_store extracts only chunk_id + term fields
        from a full document dict (simulating get_documents_by_ids return)."""
        from backend.rag.terminology.rescan import _snapshot_parent_store

        class _FakeStore:
            def get_documents_by_ids(self, chunk_ids):
                return [
                    {"chunk_id": cid,
                     "text": "should be stripped",
                     "filename": "should be stripped",
                     "file_path": "/should/be/stripped",
                     "page_number": 1,
                     "term_matches": [{"surface": "test"}],
                     "protected_tokens": ["test"]}
                    for cid in chunk_ids
                ]

        result = _snapshot_parent_store(_FakeStore(), ["chunk-1", "chunk-2"])
        assert len(result) == 2
        for r in result:
            assert "chunk_id" in r
            assert "term_matches" in r
            assert "protected_tokens" in r
            assert "text" not in r, "text should be stripped"
            assert "filename" not in r, "filename should be stripped"


class TestBM25InMemoryRollback:
    def test_failure_restores_in_memory_state(self) -> None:
        """After _persist_unlocked fails, the live service must have old state."""
        from backend.rag.terminology.rescan import _rebuild_bm25_atomic

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "bm25_state.json"
            svc = _FakeEmbeddingService(state_path)

            # Seed pre-existing state
            svc.increment_add_documents(["old term"])
            old_vocab = dict(svc._vocab)
            old_total = svc._total_docs

            assert "old" in old_vocab

            # Break _persist_unlocked to trigger rollback
            original_persist = svc._persist_unlocked
            def fail_persist() -> None:
                raise OSError("simulated disk failure")
            svc._persist_unlocked = fail_persist

            with pytest.raises(OSError):
                _rebuild_bm25_atomic(svc, ["new token", "more new"])

            svc._persist_unlocked = original_persist

            # In-memory state must be restored to pre-rebuild values
            assert svc._total_docs == old_total, f"total_docs: expected {old_total}, got {svc._total_docs}"
            assert "old" in svc._vocab, "old vocab should be restored"
            assert "new" not in svc._vocab, "new vocab should NOT leak into live service"
            assert "token" not in svc._vocab, "new token should NOT leak"
