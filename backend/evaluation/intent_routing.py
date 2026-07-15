from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.rag.intent import IntentParseResult
from backend.rag.query_plan import ComprehensiveQueryPlan, PreciseQueryPlan


IntentLabel = Literal["precise_lookup", "comprehensive_analysis"]


class SubQueryQualityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=1.0, le=5.0)
    rationale: str = Field(min_length=1)


class SubQueryQualityJudge:
    def __init__(self, *, model: Any) -> None:
        self._structured = model.with_structured_output(SubQueryQualityDecision)

    def judge(self, sample: "IntentEvalSample", result: IntentParseResult) -> float:
        if not isinstance(result.query_plan, ComprehensiveQueryPlan):
            raise ValueError("sub-query judge requires comprehensive plan")
        generated = [
            {"query": item.query, "domain": item.domain, "priority": item.priority}
            for item in result.query_plan.sub_queries
        ]
        decision = self._structured.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "你是 RAG sub-query 质量评审。根据原问题和人工参考维度，"
                        "从互补性、覆盖度、可检索性评价生成的 sub-query，给出 1-5 分。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "query": sample.query,
                            "reference_dimensions": list(sample.expected_sub_queries),
                            "generated_sub_queries": generated,
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
        )
        value = (
            decision
            if isinstance(decision, SubQueryQualityDecision)
            else SubQueryQualityDecision.model_validate(decision)
        )
        return value.score


@dataclass(frozen=True)
class IntentEvalSample:
    query: str
    expected_intent: IntentLabel
    expected_sub_queries: tuple[str, ...] = ()
    expected_scope: Literal["filter", "boost", "none"] | None = None
    expected_granularity: Literal["paragraph", "table", "step_list", "figure"] | None = None
    expected_analysis_type: Literal[
        "design_reuse", "comparison", "procedure_synthesis", "general"
    ] | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.query.strip() or not self.notes.strip():
            raise ValueError("intent evaluation query and notes must not be empty")
        if self.expected_intent == "precise_lookup":
            if self.expected_granularity is None or self.expected_analysis_type is not None:
                raise ValueError("precise samples require granularity and forbid analysis type")
            if self.expected_sub_queries:
                raise ValueError("precise samples must not define sub-queries")
        elif self.expected_intent == "comprehensive_analysis":
            if self.expected_analysis_type is None or not self.expected_sub_queries:
                raise ValueError("comprehensive samples require analysis type and sub-queries")
            if self.expected_scope is not None or self.expected_granularity is not None:
                raise ValueError("comprehensive samples must not define precise fields")
        else:
            raise ValueError(f"unknown expected intent: {self.expected_intent}")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IntentEvalSample":
        allowed = {
            "query",
            "expected_intent",
            "expected_sub_queries",
            "expected_scope",
            "expected_granularity",
            "expected_analysis_type",
            "notes",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unknown intent evaluation fields: {sorted(unknown)}")
        return cls(
            query=str(payload.get("query") or ""),
            expected_intent=payload.get("expected_intent"),
            expected_sub_queries=tuple(payload.get("expected_sub_queries") or ()),
            expected_scope=payload.get("expected_scope"),
            expected_granularity=payload.get("expected_granularity"),
            expected_analysis_type=payload.get("expected_analysis_type"),
            notes=str(payload.get("notes") or ""),
        )


def load_intent_eval_samples(data_dir: Path) -> list[IntentEvalSample]:
    samples: list[IntentEvalSample] = []
    for path in sorted(data_dir.glob("*.jsonl")):
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw_line.strip():
                continue
            try:
                samples.append(IntentEvalSample.from_dict(json.loads(raw_line)))
            except Exception as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
    if not samples:
        raise ValueError(f"no intent evaluation samples found under {data_dir}")
    queries = [sample.query for sample in samples]
    if len(queries) != len(set(queries)):
        raise ValueError("intent evaluation queries must be unique")
    return samples


def load_intent_eval_filename_registry(data_dir: Path) -> tuple[list[dict[str, str]], str]:
    """Load the curated registry that defines filename scope for the synthetic eval set."""
    path = data_dir / "filename_registry.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("intent evaluation filename registry must be a non-empty list")
    names = [str(value).strip() for value in payload]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("intent evaluation filename registry must contain unique names")
    samples = load_intent_eval_samples(data_dir)
    scoped_hints = {
        match.group(1)
        for sample in samples
        if sample.expected_scope in {"filter", "boost"}
        for match in re.finditer(r"《([^》]+)》", sample.query)
    }
    missing = sorted(scoped_hints - set(names))
    if missing:
        raise ValueError(f"filename registry does not cover scoped eval hints: {missing}")
    fingerprint = "sha256:" + hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return ([{"raw": name, "normalized": name} for name in names], fingerprint)


def _plan_is_valid(sample: IntentEvalSample, result: IntentParseResult) -> bool:
    plan = result.query_plan
    if sample.expected_intent == "precise_lookup":
        return (
            isinstance(plan, PreciseQueryPlan)
            and result.intent == "precise_lookup"
            and plan.target_granularity == sample.expected_granularity
            and (sample.expected_scope is None or plan.scope_mode == sample.expected_scope)
            and bool(plan.clean_query)
        )
    return (
        isinstance(plan, ComprehensiveQueryPlan)
        and result.intent == "comprehensive_analysis"
        and plan.analysis_type == sample.expected_analysis_type
        and bool(plan.clean_query)
        and bool(plan.sub_queries)
        and all(item.query.strip() and item.domain.strip() for item in plan.sub_queries)
    )


def _safe_mean(values: Iterable[float]) -> float | None:
    items = list(values)
    if not items:
        return None
    return round(sum(items) / len(items), 6)


def evaluate_intent_samples(
    samples: Iterable[IntentEvalSample],
    *,
    classify: Callable[[IntentEvalSample], IntentParseResult],
    judge_sub_queries: Callable[[IntentEvalSample, IntentParseResult], float] | None,
    model_name: str,
    evaluation_mode: str,
    registry_fingerprint: str | None = None,
) -> dict[str, Any]:
    sample_list = list(samples)
    cases: list[dict[str, Any]] = []
    intent_hits = 0
    valid_plans = 0
    quality_scores: list[float] = []
    for sample in sample_list:
        try:
            result = classify(sample)
            intent_correct = result.intent == sample.expected_intent
            plan_valid = _plan_is_valid(sample, result)
            intent_hits += int(intent_correct)
            valid_plans += int(plan_valid)
            quality = None
            if (
                judge_sub_queries is not None
                and sample.expected_intent == "comprehensive_analysis"
                and isinstance(result.query_plan, ComprehensiveQueryPlan)
            ):
                quality = max(1.0, min(5.0, float(judge_sub_queries(sample, result))))
                quality_scores.append(quality)
            cases.append(
                {
                    **asdict(sample),
                    "actual_intent": result.intent,
                    "intent_correct": intent_correct,
                    "plan_valid": plan_valid,
                    "sub_query_quality": quality,
                    "intent_confidence": result.confidence,
                    "trace": dict(result.trace),
                    "error": None,
                }
            )
        except Exception as exc:
            cases.append(
                {
                    **asdict(sample),
                    "actual_intent": None,
                    "intent_correct": False,
                    "plan_valid": False,
                    "sub_query_quality": None,
                    "intent_confidence": None,
                    "trace": {},
                    "error": str(exc),
                }
            )
    count = len(sample_list)
    return {
        "schema_version": "intent-routing-eval-v1",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "evaluation_mode": evaluation_mode,
        "filename_registry_fingerprint": registry_fingerprint,
        "status": "partial",
        "status_reason": (
            "thresholds require a reviewed real-model baseline; deterministic substitutes are contract evidence only"
        ),
        "sample_count": count,
        "label_counts": {
            "precise_lookup": sum(item.expected_intent == "precise_lookup" for item in sample_list),
            "comprehensive_analysis": sum(
                item.expected_intent == "comprehensive_analysis" for item in sample_list
            ),
        },
        "intent_accuracy": round(intent_hits / count, 6) if count else 0.0,
        "plan_validity": round(valid_plans / count, 6) if count else 0.0,
        "sub_query_quality_mean": _safe_mean(quality_scores),
        "sub_query_quality_scored_count": len(quality_scores),
        "cases": cases,
    }


def write_intent_eval_report(report: dict[str, Any], *, repo_root: Path) -> Path:
    model_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(report.get("model") or "unknown")).strip("-")
    date = str(report.get("executed_at") or datetime.now(timezone.utc).isoformat())[:10]
    output_dir = repo_root / "eval" / "intent"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{date}_{model_slug or 'unknown'}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
