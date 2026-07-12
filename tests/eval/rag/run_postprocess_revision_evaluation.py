"""Run the same frozen postprocess evaluation against any repository revision."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch


CASES = (
    ("seal-basic", 1, 2),
    ("pump-access", 2, 8),
    ("bearing-check", 4, 12),
    ("valve-service", 7, 14),
    ("filter-change", 3, 17),
    ("shaft-alignment", 11, 18),
    ("gasket-renewal", 16, 19),
    ("impeller-service", 5, 20),
)
EXPECTED_FACTS = ("prepare", "inspect", "install")


class _StableCrossEncoder:
    def predict(self, pairs):
        return [1.0 - index / 100 for index in range(len(pairs))]


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _fingerprint(repo: Path) -> dict[str, str]:
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    digest = hashlib.sha256()
    for relative in ("backend/rag/utils.py", "backend/rag/context.py", "backend/rag/rerank.py"):
        path = repo / relative
        digest.update(relative.encode())
        digest.update(path.read_bytes())
    return {"revision": revision, "source_sha256": digest.hexdigest()}


def _fixture(case_name: str, first_rank: int, second_rank: int):
    parent_id = f"{case_name}-parent-middle"
    group_id = f"{case_name}-steps"
    docs = []
    for rank in range(1, 21):
        common = {
            "score": 1.0 - rank / 100,
            "filename": f"{case_name}.pdf",
            "index_profile": "v4",
        }
        if rank in (first_rank, second_rank):
            docs.append(
                {
                    **common,
                    "chunk_id": f"{case_name}-leaf-{rank}",
                    "parent_chunk_id": parent_id,
                    "root_chunk_id": parent_id,
                    "chunk_level": 3,
                    "chunk_role": "leaf",
                    "text": f"inspect {case_name} component detail {rank}",
                }
            )
        else:
            docs.append(
                {
                    **common,
                    "chunk_id": f"{case_name}-background-{rank}",
                    "parent_chunk_id": f"{case_name}-background-root-{rank}",
                    "root_chunk_id": f"{case_name}-background-root-{rank}",
                    "chunk_level": 3,
                    "chunk_role": "leaf",
                    "text": f"background note {rank}",
                }
            )
    parent = {
        "chunk_id": parent_id,
        "parent_chunk_id": parent_id,
        "root_chunk_id": parent_id,
        "chunk_level": 1,
        "chunk_role": "root",
        "filename": f"{case_name}.pdf",
        "index_profile": "v4",
        "text": f"inspect {case_name} component",
        "list_group_id": group_id,
        "list_order": 2,
        "list_complete": False,
        "score": 0.0,
    }
    adjacent = [
        {
            **parent,
            "chunk_id": f"{case_name}-parent-first",
            "root_chunk_id": parent_id,
            "text": f"prepare {case_name} tools",
            "list_order": 1,
            "score": 1.2,
        },
        {
            **parent,
            "chunk_id": f"{case_name}-parent-last",
            "root_chunk_id": parent_id,
            "text": f"install {case_name} component and verify",
            "list_order": 3,
            "score": 1.1,
        },
    ]
    return docs, parent, adjacent


def _coverage(docs: list[dict]) -> float:
    evidence = "\n".join(str(doc.get("text") or "") for doc in docs)
    return sum(fact in evidence for fact in EXPECTED_FACTS) / len(EXPECTED_FACTS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--pool-size", type=int, default=20)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    sys.path.insert(0, str(repo))
    import backend.rag.utils as rag_utils

    is_current_pipeline = hasattr(rag_utils, "STEP_CHAIN_CHECK_ENABLED")
    results = []
    latency_samples = []

    for case_name, first_rank, second_rank in CASES:
        docs, parent, adjacent = _fixture(case_name, first_rank, second_rank)
        parent_store = MagicMock()
        parent_store.get_documents_by_ids.side_effect = lambda chunk_ids: (
            [parent] if chunk_ids == [parent["chunk_id"]] else adjacent
        )
        adjacent_leaf_refs = [
            {"parent_chunk_id": item["chunk_id"], "parent_list_order": item["list_order"]}
            for item in adjacent
        ]

        with ExitStack() as stack:
            settings = {
                "RERANK_MODEL": "frozen-eval-cross-encoder",
                "RERANK_TOP_N": 0,
                "RERANK_INPUT_K_CPU": 0,
                "RERANK_DEVICE": "cpu",
                "RERANK_CACHE_ENABLED": False,
                "RERANK_SCORE_FUSION_ENABLED": False,
                "AUTO_MERGE_ENABLED": True,
                "AUTO_MERGE_THRESHOLD": 2,
                "STRUCTURE_RERANK_ENABLED": True,
                "SAME_ROOT_CAP": 3,
                "CONFIDENCE_GATE_ENABLED": False,
            }
            if is_current_pipeline:
                settings.update(
                    {
                        "RERANK_CANDIDATE_POOL_SIZE": args.pool_size,
                        "STEP_CHAIN_CHECK_ENABLED": True,
                        "STEP_CHAIN_ADJACENT_LOOKBACK": 1,
                    }
                )
            for name, value in settings.items():
                if hasattr(rag_utils, name):
                    stack.enter_context(patch.object(rag_utils, name, value))
            stack.enter_context(
                patch.object(rag_utils, "_get_local_reranker", return_value=_StableCrossEncoder())
            )
            stack.enter_context(
                patch.object(rag_utils, "_get_parent_chunk_store", return_value=parent_store)
            )
            if is_current_pipeline:
                stack.enter_context(
                    patch.object(rag_utils._milvus_manager, "query_all", return_value=adjacent_leaf_refs)
                )

            first_result = None
            for _ in range(args.samples):
                started = time.perf_counter()
                result = rag_utils._finish_retrieval_pipeline(
                    query=f"{case_name} maintenance procedure",
                    search_query=f"{case_name} maintenance procedure",
                    retrieved=docs,
                    top_k=3,
                    candidate_k=len(docs),
                    timings={},
                    stage_errors=[],
                    total_start=time.perf_counter(),
                )
                latency_samples.append((time.perf_counter() - started) * 1000)
                first_result = first_result or result

        final_docs = first_result["docs"]
        results.append(
            {
                "case": case_name,
                "relevant_ranks": [first_rank, second_rank],
                "top_k": [doc.get("chunk_id") for doc in final_docs],
                "answerability": _coverage(final_docs),
                "complete_step_group": _coverage(final_docs) == 1.0,
            }
        )

    payload = {
        "label": args.label,
        "repo": str(repo),
        **_fingerprint(repo),
        "pipeline": "current" if is_current_pipeline else "baseline",
        "candidate_pool_size": args.pool_size if is_current_pipeline else None,
        "sample_count": len(latency_samples),
        "p50_ms": round(statistics.median(latency_samples), 3),
        "p95_ms": round(_percentile(latency_samples, 0.95), 3),
        "mean_answerability": round(
            statistics.mean(item["answerability"] for item in results), 4
        ),
        "complete_step_groups": sum(item["complete_step_group"] for item in results),
        "total_cases": len(results),
        "cases": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
