"""Single-call repair for one failed generated comprehensive branch."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Sequence, TypeVar

from pydantic import BaseModel, Field

from backend.rag.query_plan import (
    ComprehensiveQueryPlan,
    ComprehensiveRetrievalBranch,
    SubQuery,
)


class RewriteSubQuery(BaseModel):
    query: str
    domain: str
    priority: Literal[1, 2, 3]


class ComprehensiveRewriteOutput(BaseModel):
    strategy: Literal["generalize", "specialize", "replace", "decompose"]
    new_sub_queries: list[RewriteSubQuery] = Field(min_length=1, max_length=2)
    reason: str


@dataclass(frozen=True)
class ComprehensiveRewriteResult:
    plan: ComprehensiveQueryPlan
    strategy: str
    new_sub_queries: tuple[SubQuery, ...]
    reason: str
    replaced_branch_id: str


_SYSTEM_PROMPT = """你是综合分析查询的修复器。一个由 LLM 生成的 sub_query 召回不足，需要修复。
基于完整 plan、失败信号和成功 sub_query，选择且只选择一种策略：
- generalize：改写为一个更通用的 sub_query
- specialize：改写为一个假设性、更具体的 sub_query
- replace：从不同角度改写为一个 sub_query
- decompose：拆成恰好两个更细的 sub_query
不得改写 clean-query baseline，不得重复成功的 sub_query。"""


_BranchResult = TypeVar("_BranchResult")


def select_failed_generated_branches(
    branch_results: Sequence[_BranchResult],
    *,
    window: int,
) -> list[_BranchResult]:
    """Select failed generated branches by priority and stable branch id."""
    failed = [
        item
        for item in branch_results
        if item.branch.branch_kind == "sub_query"
        and (item.error is not None or not item.candidates)
    ]
    failed.sort(key=lambda item: (item.branch.priority, item.branch.branch_id))
    return failed[:window]


def _normalized_query(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _output_value(output: object, name: str) -> Any:
    if isinstance(output, dict):
        return output.get(name)
    return getattr(output, name)


def _coerce_sub_query(value: object) -> SubQuery:
    if isinstance(value, SubQuery):
        return value
    if isinstance(value, dict):
        query = value.get("query")
        domain = value.get("domain")
        priority = value.get("priority")
    else:
        query = getattr(value, "query")
        domain = getattr(value, "domain")
        priority = getattr(value, "priority")
    return SubQuery(
        query=str(query).strip(),
        domain=str(domain).strip(),
        priority=int(priority),
    )


def _failed_sub_query_index(
    plan: ComprehensiveQueryPlan,
    failed_branch: ComprehensiveRetrievalBranch,
) -> int:
    if failed_branch.branch_kind == "baseline":
        raise ValueError("clean-query baseline cannot be a comprehensive rewrite target")
    prefix = "sub_query_"
    if not failed_branch.branch_id.startswith(prefix):
        raise ValueError("failed generated branch has no stable sub-query index")
    try:
        index = int(failed_branch.branch_id[len(prefix) :])
    except ValueError as exc:
        raise ValueError("failed generated branch has no stable sub-query index") from exc
    if index < 0 or index >= len(plan.sub_queries):
        raise ValueError("failed generated branch is outside the current plan")
    expected = plan.sub_queries[index]
    if (
        failed_branch.query != expected.query
        or failed_branch.domain != expected.domain
        or failed_branch.priority != expected.priority
    ):
        raise ValueError("failed generated branch does not match the current plan")
    return index


def rewrite_failed_sub_query(
    plan: ComprehensiveQueryPlan,
    *,
    failed_branch: ComprehensiveRetrievalBranch,
    failure_signal: dict[str, Any],
    succeeded_sub_queries: Sequence[SubQuery],
    model: Any,
) -> ComprehensiveRewriteResult:
    """Replace one failed generated sub-query while preserving the rest of the plan."""
    failed_index = _failed_sub_query_index(plan, failed_branch)
    payload = {
        "original_plan": asdict(plan),
        "failed_sub_query": asdict(plan.sub_queries[failed_index]),
        "failure_signal": dict(failure_signal),
        "succeeded_sub_queries": [asdict(item) for item in succeeded_sub_queries],
    }
    output = model.with_structured_output(ComprehensiveRewriteOutput).invoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            },
        ]
    )
    strategy = str(_output_value(output, "strategy"))
    if strategy not in {"generalize", "specialize", "replace", "decompose"}:
        raise ValueError("unsupported comprehensive rewrite strategy")
    new_sub_queries = tuple(
        _coerce_sub_query(item) for item in list(_output_value(output, "new_sub_queries") or [])
    )
    expected_count = 2 if strategy == "decompose" else 1
    if len(new_sub_queries) != expected_count:
        raise ValueError(
            f"strategy {strategy} requires {expected_count} new_sub_queries"
        )
    succeeded_queries = {_normalized_query(item.query) for item in succeeded_sub_queries}
    generated_queries: set[str] = set()
    for item in new_sub_queries:
        normalized = _normalized_query(item.query)
        if normalized in succeeded_queries:
            raise ValueError("new_sub_queries duplicates a succeeded sub-query")
        if normalized in generated_queries:
            raise ValueError("new_sub_queries contains duplicates")
        generated_queries.add(normalized)

    updated_sub_queries = (
        plan.sub_queries[:failed_index]
        + new_sub_queries
        + plan.sub_queries[failed_index + 1 :]
    )
    coverage_domains = tuple(
        dict.fromkeys(item.domain for item in updated_sub_queries)
    )
    updated_plan = replace(
        plan,
        sub_queries=updated_sub_queries,
        coverage_domains=coverage_domains,
    )
    return ComprehensiveRewriteResult(
        plan=updated_plan,
        strategy=strategy,
        new_sub_queries=new_sub_queries,
        reason=str(_output_value(output, "reason") or "").strip(),
        replaced_branch_id=failed_branch.branch_id,
    )
