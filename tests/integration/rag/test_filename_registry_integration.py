"""Opt-in integration coverage for filename registry Redis + Milvus flow.

Run manually when Redis and Milvus are available and the configured Milvus
collection already contains indexed filenames:

    $env:RUN_REDIS_MILVUS_REGISTRY_INTEGRATION = "1"
    uv run pytest tests/integration/rag/test_filename_registry_integration.py -q
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_redis,
    pytest.mark.requires_milvus,
]


@pytest.mark.skipif(
    os.getenv("RUN_REDIS_MILVUS_REGISTRY_INTEGRATION") != "1",
    reason="Set RUN_REDIS_MILVUS_REGISTRY_INTEGRATION=1 to use real Redis and Milvus.",
)
def test_filename_registry_queries_milvus_and_reuses_redis_cache():
    from backend.config import MILVUS_COLLECTION
    from backend.infra.cache import RedisCache
    from backend.infra.vector_store.milvus_client import MilvusManager
    from backend.rag import query_plan

    cache = RedisCache()
    manager = MilvusManager()
    index_version = query_plan._index_version_from_cache(cache)
    cache_key = query_plan._registry_cache_key(MILVUS_COLLECTION, index_version)

    query_plan._registry_cache.clear()
    cache.delete(cache_key)
    try:
        entries = query_plan.get_filename_registry(manager, cache)
        if not entries:
            pytest.skip("Configured Milvus collection has no indexed filenames.")

        assert all({"raw", "normalized"} <= set(entry) for entry in entries)
        assert cache.get_json(cache_key) == entries

        query_plan._registry_cache.clear()
        with patch.object(
            manager,
            "query_unique_filenames",
            side_effect=AssertionError("Redis cache should satisfy the second lookup"),
        ):
            assert query_plan.get_filename_registry(manager, cache) == entries
    finally:
        query_plan._registry_cache.clear()
        cache.delete(cache_key)
