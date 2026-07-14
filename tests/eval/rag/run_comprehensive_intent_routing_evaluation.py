from __future__ import annotations

import hashlib
import os
import subprocess
import time
from dataclasses import asdict, replace
from pathlib import Path

from backend.config import ARK_API_KEY, FAST_MODEL, MILVUS_COLLECTION
from backend.evaluation.answer_eval import ANSWER_MODEL, JUDGE_MODEL, evaluate_answer_end_to_end
from backend.evaluation.comprehensive_routing import (
    build_comprehensive_comparison,
    config_fingerprint,
    routing_source_fingerprint,
    run_comprehensive_profile,
    write_comprehensive_comparison_report,
)
from backend.evaluation.intent_routing import load_intent_eval_samples
from backend.rag.intent import IntentClassifier, build_intent_parse_result
from backend.rag.pipeline import (
    branch_rerank_node,
    decompose_and_fanout,
    merge_sub_query_results,
    shared_postprocess_node,
)
from backend.rag.query_plan import ComprehensiveQueryPlan
from backend.rag.runtime_config import load_runtime_config


REPO_ROOT = Path(__file__).parents[3]
DATA_DIR = Path(__file__).parents[1] / "data" / "intent_routing"
PROFILES = ("quality_first_v1", "eval_no_crossencoder_v1")


def _required_env(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise SystemExit(f"{name} is required to bind the release retrieval corpus")
    return value


def _file_fingerprint(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"BM25 state file is required for release evaluation: {path}")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _source_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _config_fingerprint() -> str:
    config = asdict(load_runtime_config())
    config.pop("comprehensive_postprocess_profile", None)
    bm25_state_path = Path(os.getenv("BM25_STATE_PATH", "data/bm25_state.json")).resolve()
    return config_fingerprint(
        {
            "runtime": config,
            "intent_model": FAST_MODEL,
            "answer_model": ANSWER_MODEL,
            "judge_model": JUDGE_MODEL,
            "milvus_collection": MILVUS_COLLECTION,
            "embedding_model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
            "bm25_state_path": str(bm25_state_path),
            "bm25_state_fingerprint": _file_fingerprint(bm25_state_path),
            "milvus_index_version": _required_env("RAG_EVAL_MILVUS_INDEX_VERSION"),
            "release_corpus_fingerprint": _required_env("RAG_EVAL_CORPUS_FINGERPRINT"),
        }
    )


def _execute_plan(case: dict, profile: str) -> dict:
    plan = replace(case["plan"], postprocess_profile=profile)
    state = {
        "question": plan.raw_query,
        "query": plan.raw_query,
        "context": "",
        "docs": [],
        "context_files": [],
        "query_plan": plan,
        "query_plan_type": "comprehensive",
        "rag_trace": {
            "intent": "comprehensive_analysis",
            "query_plan_type": "comprehensive",
            "analysis_type": plan.analysis_type,
        },
    }
    started = time.perf_counter()
    for node in (
        decompose_and_fanout,
        branch_rerank_node,
        merge_sub_query_results,
        shared_postprocess_node,
    ):
        state.update(node(state))
    timings = dict(state["rag_trace"].get("timings") or {})
    timings["total_rag_graph_ms"] = round((time.perf_counter() - started) * 1000, 3)
    state["rag_trace"]["timings"] = timings
    answer_eval = evaluate_answer_end_to_end(
        plan.raw_query,
        list(state.get("docs") or []),
        expected={},
    )
    return {
        "rag_trace": state["rag_trace"],
        "citation_validity": answer_eval.get("citation_validity"),
        "answer_quality": answer_eval.get("answer_relevance_score"),
    }


def main() -> int:
    if os.getenv("RAG_COMPREHENSIVE_EVAL_RUN_REAL") != "1":
        raise SystemExit("set RAG_COMPREHENSIVE_EVAL_RUN_REAL=1 to run real profile evaluation")
    if not ARK_API_KEY or not FAST_MODEL:
        raise SystemExit("FAST_MODEL credentials are required")

    samples = [
        sample
        for sample in load_intent_eval_samples(DATA_DIR)
        if sample.expected_intent == "comprehensive_analysis"
    ]
    classifier = IntentClassifier(model_name=FAST_MODEL, timeout_seconds=10.0)
    cases = []
    for index, sample in enumerate(samples, 1):
        parsed = build_intent_parse_result(
            sample.query,
            classifier=classifier,
            classifier_enabled=True,
            llm_model=FAST_MODEL,
        )
        if not isinstance(parsed.query_plan, ComprehensiveQueryPlan):
            raise RuntimeError(f"comprehensive dataset case {index} was not classified comprehensive")
        cases.append({"case_id": f"comprehensive-{index:03d}", "plan": parsed.query_plan})

    source_commit = _source_commit()
    fingerprint = routing_source_fingerprint(REPO_ROOT)
    source_fingerprint = "sha256:" + fingerprint["sha256"]
    config_fingerprint = _config_fingerprint()
    runs = {
        profile: run_comprehensive_profile(
            cases,
            profile=profile,
            run_case=_execute_plan,
            source_commit=source_commit,
            source_fingerprint=source_fingerprint,
            config_fingerprint=config_fingerprint,
        )
        for profile in PROFILES
    }
    report = build_comprehensive_comparison(runs[PROFILES[0]], runs[PROFILES[1]])
    report["environment"] = {
        "intent_model": FAST_MODEL,
        "answer_model": ANSWER_MODEL,
        "judge_model": JUDGE_MODEL,
        "milvus_collection": MILVUS_COLLECTION,
        "embedding_model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
        "bm25_state_path": str(Path(os.getenv("BM25_STATE_PATH", "data/bm25_state.json")).resolve()),
        "milvus_index_version": _required_env("RAG_EVAL_MILVUS_INDEX_VERSION"),
        "release_corpus_fingerprint": _required_env("RAG_EVAL_CORPUS_FINGERPRINT"),
        "run_mode": "real-model-real-retrieval",
        "case_count": len(cases),
    }
    report["status"] = (
        "partial"
        if report["quality_first"].get("citation_validity_mean") is None
        or report["quality_first"].get("answer_quality_mean") is None
        else "measured"
    )
    output = write_comprehensive_comparison_report(report, repo_root=REPO_ROOT)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
