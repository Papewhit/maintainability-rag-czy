from __future__ import annotations

import math
import json
import re
import threading
import time
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


_ROUTING_SOURCE_FILES = (
    "backend/contracts/schemas.py",
    "backend/evaluation/answer_eval.py",
    "backend/evaluation/comprehensive_routing.py",
    "backend/evaluation/intent_routing.py",
    "backend/rag/comprehensive_postprocess.py",
    "backend/rag/intent.py",
    "backend/rag/observability.py",
    "backend/rag/pipeline.py",
    "backend/rag/query_plan.py",
    "backend/rag/rerank.py",
    "backend/rag/runtime_config.py",
    "backend/rag/utils.py",
    "openspec/changes/rag-intent-routing/design.md",
    "openspec/changes/rag-intent-routing/specs/rag-intent-routing/spec.md",
    "tests/eval/data/intent_routing/comprehensive_analysis.jsonl",
    "tests/eval/data/intent_routing/filename_registry.json",
    "tests/eval/data/intent_routing/precise_lookup.jsonl",
    "tests/eval/rag/run_comprehensive_intent_routing_evaluation.py",
    "tests/eval/rag/test_comprehensive_intent_routing_eval.py",
    "tests/eval/rag/test_intent_classifier_eval.py",
)


def config_fingerprint(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def routing_source_fingerprint(repo_root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    for relative in _ROUTING_SOURCE_FILES:
        path = repo_root / relative
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(relative.replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return {
        "version": 1,
        "normalization": "lf",
        "source_files": list(_ROUTING_SOURCE_FILES),
        "sha256": digest.hexdigest(),
    }


class ResourcePeakSampler:
    def __init__(self, *, interval_seconds: float = 0.01) -> None:
        self.interval_seconds = max(0.001, float(interval_seconds))
        self.cpu_peak_mb = 0.0
        self.gpu_peak_mb = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample_cpu(self) -> None:
        try:
            import psutil

            process = psutil.Process()
            while not self._stop.is_set():
                self.cpu_peak_mb = max(
                    self.cpu_peak_mb,
                    process.memory_info().rss / (1024.0 * 1024.0),
                )
                self._stop.wait(self.interval_seconds)
        except Exception:
            return

    def __enter__(self) -> "ResourcePeakSampler":
        self._stop.clear()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
        except Exception:
            pass
        self._thread = threading.Thread(target=self._sample_cpu, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, self.interval_seconds * 4))
        try:
            import torch

            if torch.cuda.is_available():
                self.gpu_peak_mb = torch.cuda.max_memory_allocated() / (1024.0 * 1024.0)
        except Exception:
            self.gpu_peak_mb = 0.0


def run_comprehensive_profile(
    cases: Iterable[dict[str, Any]],
    *,
    profile: str,
    run_case: Callable[[dict[str, Any], str], dict[str, Any]],
    source_commit: str,
    source_fingerprint: str,
    config_fingerprint: str,
    sampler_factory: Callable[[], Any] = ResourcePeakSampler,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("comprehensive evaluation case_id must not be empty")
        started = time.perf_counter()
        sampler = sampler_factory()
        with sampler:
            result = dict(run_case(case, profile) or {})
        rag_trace = dict(result.get("rag_trace") or {})
        timings = dict(rag_trace.get("timings") or {})
        timings.setdefault("total_rag_graph_ms", round((time.perf_counter() - started) * 1000, 3))
        rag_trace["timings"] = timings
        runs.append(
            {
                "case_id": case_id,
                "profile": profile,
                "source_commit": source_commit,
                "source_fingerprint": source_fingerprint,
                "config_fingerprint": config_fingerprint,
                "cpu_peak_mb": round(float(getattr(sampler, "cpu_peak_mb", 0.0)), 3),
                "gpu_peak_mb": round(float(getattr(sampler, "gpu_peak_mb", 0.0)), 3),
                "citation_validity": result.get("citation_validity"),
                "answer_quality": result.get("answer_quality"),
                "rag_trace": rag_trace,
            }
        )
    return runs


def write_comprehensive_comparison_report(
    report: dict[str, Any],
    *,
    repo_root: Path,
) -> Path:
    commit = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(report.get("source_commit") or "unknown"))
    date = str(report.get("executed_at") or datetime.now(timezone.utc).isoformat())[:10]
    output_dir = repo_root / "eval" / "comprehensive-intent-routing"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{date}_{commit}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def _mean(values: Iterable[float]) -> float | None:
    items = [float(value) for value in values]
    return round(sum(items) / len(items), 6) if items else None


def _latency_summary(values: Iterable[float]) -> dict[str, float] | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    p50 = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    return {"p50": round(p50, 3), "p95": round(p95, 3)}


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def summarize_comprehensive_runs(runs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(runs)
    traces = [dict(item.get("rag_trace") or {}) for item in items]
    timings = [dict(trace.get("timings") or {}) for trace in traces]
    successful = sum(len(trace.get("successful_generated_branch_ids") or []) for trace in traces)
    represented = sum(len(trace.get("represented_generated_branch_ids") or []) for trace in traces)
    timing_keys = (
        "comprehensive_fanout_ms",
        "comprehensive_branch_rerank_ms",
        "multi_query_merge_ms",
        "auto_merge_ms",
        "step_chain_ms",
        "structure_rerank_ms",
        "final_selection_ms",
        "confidence_ms",
        "comprehensive_shared_postprocess_ms",
        "total_rag_graph_ms",
    )
    timing_summary = {
        key: summary
        for key in timing_keys
        if (summary := _latency_summary(timing[key] for timing in timings if timing.get(key) is not None))
        is not None
    }
    error_cases = sum(bool(trace.get("stage_errors")) for trace in traces)
    degradation_cases = sum(
        bool(trace.get("stage_errors"))
        or bool(trace.get("rerank_budget_exhausted"))
        or any(bool(value) for key, value in trace.items() if key.endswith("_skipped"))
        for trace in traces
    )
    return {
        "case_count": len(items),
        "sub_query_count_buckets": dict(
            sorted(Counter(str(int(trace.get("sub_query_count") or 0)) for trace in traces).items())
        ),
        "retrieval_branch_count_buckets": dict(
            sorted(
                Counter(str(int(trace.get("retrieval_branch_count") or 0)) for trace in traces).items()
            )
        ),
        "baseline_hit_rate": _rate(sum(bool(trace.get("baseline_hit")) for trace in traces), len(traces)),
        "baseline_selected_rate": _rate(
            sum(bool(trace.get("baseline_selected")) for trace in traces), len(traces)
        ),
        "dense_embedding_call_count_total": sum(
            int(trace.get("dense_embedding_call_count") or 0) for trace in traces
        ),
        "sparse_embedding_call_count_total": sum(
            int(trace.get("sparse_embedding_call_count") or 0) for trace in traces
        ),
        "hybrid_search_call_count_total": sum(
            int(trace.get("hybrid_search_call_count") or 0) for trace in traces
        ),
        "split_search_call_count_total": sum(
            int(trace.get("split_search_call_count") or 0) for trace in traces
        ),
        "rerank_pair_count_total": sum(int(trace.get("rerank_pair_count") or 0) for trace in traces),
        "branch_candidate_count_total": sum(
            int(trace.get("branch_candidate_count") or 0) for trace in traces
        ),
        "merged_candidate_count_total": sum(
            int(trace.get("merged_unique_candidate_count") or 0) for trace in traces
        ),
        "final_candidate_count_total": sum(
            int(trace.get("final_candidate_count") or 0) for trace in traces
        ),
        "generated_branch_representation_rate": _rate(represented, successful),
        "timings_ms": timing_summary,
        "cpu_peak_mb": max((float(item.get("cpu_peak_mb") or 0.0) for item in items), default=0.0),
        "gpu_peak_mb": max((float(item.get("gpu_peak_mb") or 0.0) for item in items), default=0.0),
        "error_rate": _rate(error_cases, len(items)),
        "degradation_rate": _rate(degradation_cases, len(items)),
        "citation_validity_mean": _mean(
            item["citation_validity"] for item in items if item.get("citation_validity") is not None
        ),
        "answer_quality_mean": _mean(
            item["answer_quality"] for item in items if item.get("answer_quality") is not None
        ),
    }


def _uniform_value(items: list[dict[str, Any]], key: str, label: str) -> Any:
    values = {item.get(key) for item in items}
    if len(values) != 1:
        raise ValueError(f"{label} runs do not share one {key.replace('_', ' ')}")
    return next(iter(values))


def build_comprehensive_comparison(
    quality_first_runs: Iterable[dict[str, Any]],
    ablation_runs: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    quality = sorted(list(quality_first_runs), key=lambda item: str(item.get("case_id")))
    ablation = sorted(list(ablation_runs), key=lambda item: str(item.get("case_id")))
    if not quality or not ablation:
        raise ValueError("both comprehensive profiles require runs")
    quality_ids = [str(item.get("case_id")) for item in quality]
    ablation_ids = [str(item.get("case_id")) for item in ablation]
    if quality_ids != ablation_ids:
        raise ValueError("profile runs must use the same paired case ids")
    source_commit = _uniform_value(quality + ablation, "source_commit", "paired")
    source_fingerprint = _uniform_value(quality + ablation, "source_fingerprint", "paired")
    config_fingerprint = _uniform_value(quality + ablation, "config_fingerprint", "paired")
    if not source_commit:
        raise ValueError("paired runs require source commit")
    if not source_fingerprint:
        raise ValueError("paired runs require source fingerprint")
    if not config_fingerprint:
        raise ValueError("paired runs require config fingerprint")
    quality_summary = summarize_comprehensive_runs(quality)
    ablation_summary = summarize_comprehensive_runs(ablation)
    quality_p95 = quality_summary.get("timings_ms", {}).get("total_rag_graph_ms", {}).get("p95")
    ablation_p95 = ablation_summary.get("timings_ms", {}).get("total_rag_graph_ms", {}).get("p95")
    return {
        "schema_version": "comprehensive-routing-comparison-v1",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "source_fingerprint": source_fingerprint,
        "config_fingerprint": config_fingerprint,
        "case_ids": quality_ids,
        "quality_first_profile": _uniform_value(quality, "profile", "quality-first"),
        "ablation_profile": _uniform_value(ablation, "profile", "ablation"),
        "quality_first": quality_summary,
        "ablation": ablation_summary,
        "deltas": {
            "answer_quality_mean": round(
                float(quality_summary.get("answer_quality_mean") or 0.0)
                - float(ablation_summary.get("answer_quality_mean") or 0.0),
                6,
            ),
            "citation_validity_mean": round(
                float(quality_summary.get("citation_validity_mean") or 0.0)
                - float(ablation_summary.get("citation_validity_mean") or 0.0),
                6,
            ),
            "generated_branch_representation_rate": round(
                float(quality_summary.get("generated_branch_representation_rate") or 0.0)
                - float(ablation_summary.get("generated_branch_representation_rate") or 0.0),
                6,
            ),
            "total_rag_graph_p95_ms": (
                round(float(quality_p95) - float(ablation_p95), 3)
                if quality_p95 is not None and ablation_p95 is not None
                else None
            ),
            "cpu_peak_mb": round(
                float(quality_summary["cpu_peak_mb"]) - float(ablation_summary["cpu_peak_mb"]), 3
            ),
            "gpu_peak_mb": round(
                float(quality_summary["gpu_peak_mb"]) - float(ablation_summary["gpu_peak_mb"]), 3
            ),
            "rerank_pair_count_total": (
                int(quality_summary["rerank_pair_count_total"])
                - int(ablation_summary["rerank_pair_count_total"])
            ),
        },
    }
