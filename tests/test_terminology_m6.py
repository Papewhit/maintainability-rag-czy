"""Tests for M6: Rescan task management."""
from __future__ import annotations

import pytest


class TestRescanLock:
    def test_lock_prevents_concurrent_rescans(self) -> None:
        from backend.rag.terminology.rescan import _rescan_lock, is_rescan_running

        assert not is_rescan_running()
        assert _rescan_lock.acquire(blocking=False)
        try:
            assert is_rescan_running()
            # Second acquire should fail
            assert not _rescan_lock.acquire(blocking=False)
        finally:
            _rescan_lock.release()
        assert not is_rescan_running()



