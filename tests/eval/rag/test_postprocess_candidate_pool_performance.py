import statistics
import time
from unittest.mock import patch

import pytest

import backend.rag.utils as rag_utils


pytestmark = pytest.mark.eval


class _DeterministicReranker:
    def predict(self, pairs):
        # Keep this benchmark model-free while retaining work proportional to the
        # number of CrossEncoder pairs.
        scores = []
        for index, (_, text) in enumerate(pairs):
            checksum = sum(ord(char) for char in text * 50)
            scores.append(float(checksum % 997) - index / 1000)
        return scores


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


@pytest.mark.parametrize("pool_size", [5, 10, 20])
def test_candidate_pool_performance_profile(pool_size, record_property):
    docs = [
        {
            "chunk_id": f"chunk-{index}",
            "text": f"maintenance evidence {index}",
            "score": 1.0 - index / 100,
        }
        for index in range(30)
    ]
    samples: list[float] = []

    with (
        patch.object(rag_utils, "RERANK_CANDIDATE_POOL_SIZE", pool_size),
        patch.object(rag_utils, "RERANK_TOP_N", 0),
        patch.object(rag_utils, "RERANK_PROVIDER", "local"),
        patch.object(rag_utils, "RERANK_MODEL", "deterministic-test-reranker"),
        patch.object(rag_utils, "RERANK_INPUT_K_CPU", 0),
        patch.object(rag_utils, "RERANK_DEVICE", "cpu"),
        patch.object(rag_utils, "RERANK_CACHE_ENABLED", False),
        patch.object(rag_utils, "_get_local_reranker", return_value=_DeterministicReranker()),
    ):
        for _ in range(15):
            started = time.perf_counter()
            reranked, meta = rag_utils._rerank_documents("maintenance", docs, top_k=5)
            samples.append((time.perf_counter() - started) * 1000)

    p50 = statistics.median(samples)
    p95 = _percentile(samples, 0.95)
    record_property("candidate_pool_size", pool_size)
    record_property("p50_ms", round(p50, 3))
    record_property("p95_ms", round(p95, 3))

    assert len(reranked) == pool_size
    assert meta["rerank_output_count"] == pool_size
    assert 0 <= p50 <= p95
