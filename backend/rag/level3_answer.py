from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.rag.query_plan import ComprehensiveQueryPlan, PreciseQueryPlan
from backend.rag.trace import candidate_identity
from backend.rag.types import Level3Delivery, Level3EvidenceRef


def _attempts(attempted_levels: Sequence[int]) -> str:
    return " → ".join(f"Level {level}" for level in attempted_levels)


def _evidence_text(candidate: Mapping[str, Any]) -> str:
    return str(
        candidate.get("text")
        or candidate.get("retrieval_text")
        or candidate.get("content")
        or ""
    ).strip()


def _evidence_ref(document: dict[str, Any]) -> Level3EvidenceRef:
    identity = candidate_identity(document)
    return {
        "candidate_id": identity,
        "chunk_id": str(document.get("chunk_id") or identity),
        "filename": str(document.get("filename") or "Unknown"),
        "page_number": document.get("page_number"),
        "excerpt": _evidence_text(document),
    }


def _first_evidence_for_branch(
    final_documents: Sequence[dict[str, Any]],
    branch_id: str,
) -> Level3EvidenceRef | None:
    for document in final_documents:
        if branch_id in set(document.get("matched_branch_ids") or []):
            if _evidence_text(document):
                return _evidence_ref(document)
    return None


def build_level3_delivery(
    query_plan: PreciseQueryPlan | ComprehensiveQueryPlan,
    attempted_levels: Sequence[int],
    *,
    final_documents: Sequence[dict[str, Any]] = (),
) -> Level3Delivery:
    """Build the authoritative typed Level 3 delivery contract."""
    attempts = list(attempted_levels)
    if isinstance(query_plan, PreciseQueryPlan):
        return {
            "mode": "precise_insufficient",
            "covered_count": 0,
            "total_count": 0,
            "covered_dimensions": [],
            "uncovered_dimensions": [],
            "dimension_evidence": [],
            "baseline_evidence": [],
            "constraints": ["insufficient_evidence", f"scope_mode:{query_plan.scope_mode}"],
            "attempted_levels": attempts,
        }

    dimension_evidence: list[dict[str, Any]] = []
    uncovered: list[str] = []
    for index, sub_query in enumerate(query_plan.sub_queries):
        label = sub_query.domain or sub_query.query
        evidence = _first_evidence_for_branch(final_documents, f"sub_query_{index}")
        if evidence:
            dimension_evidence.append({
                "dimension_id": f"sub_query_{index}",
                "label": label,
                "evidence_refs": [evidence],
            })
        else:
            uncovered.append(label)

    total = len(query_plan.sub_queries)
    covered_count = len(dimension_evidence)
    baseline = _first_evidence_for_branch(final_documents, "baseline")
    if 0 < covered_count < total:
        mode = "partial_synthesis"
        constraints = [
            "answer_covered_dimensions_only",
            "cite_each_dimension",
            "state_overall_insufficiency",
            "do_not_answer_uncovered_dimensions",
            "no_cross_dimension_conclusions",
            "do_not_expose_internal_labels",
        ]
    elif covered_count == total and total > 0:
        mode = "full_coverage_low_confidence"
        constraints = ["evidence_only", "no_synthesis"]
    elif baseline:
        mode = "baseline_only"
        constraints = ["evidence_only", "baseline_not_coverage", "no_synthesis"]
    else:
        mode = "no_evidence"
        constraints = ["insufficient_evidence", "no_synthesis"]

    return {
        "mode": mode,
        "covered_count": covered_count,
        "total_count": total,
        "covered_dimensions": [item["label"] for item in dimension_evidence],
        "uncovered_dimensions": uncovered,
        "dimension_evidence": dimension_evidence,
        "baseline_evidence": [baseline] if baseline and mode == "baseline_only" else [],
        "constraints": constraints,
        "attempted_levels": attempts,
    }


def level3_answer_evidence(
    delivery: Level3Delivery,
    final_documents: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve referenced evidence back to the final top-k, preserving final order."""
    referenced_ids = {
        str(ref.get("candidate_id"))
        for dimension in delivery.get("dimension_evidence") or []
        for ref in dimension.get("evidence_refs") or []
        if ref.get("candidate_id")
    }
    referenced_ids.update(
        str(ref.get("candidate_id"))
        for ref in delivery.get("baseline_evidence") or []
        if ref.get("candidate_id")
    )
    return [
        document
        for document in final_documents
        if candidate_identity(document) in referenced_ids
    ]


def _render_ref(ref: Mapping[str, Any]) -> str:
    source = f"{ref.get('filename', 'Unknown')}，第 {ref.get('page_number') or 'N/A'} 页"
    return f"[来源：{source}]：{ref.get('excerpt', '')}"


def render_level3_delivery(delivery: Level3Delivery) -> str:
    """Render the sole deterministic compatibility projection."""
    mode = delivery.get("mode")
    attempts = _attempts(delivery.get("attempted_levels") or [])
    suggestion = "建议: 检查相关文档是否已上传 / 调整问法 / 提供更多上下文文件。"
    if mode == "precise_insufficient":
        filtered = "scope_mode:filter" in set(delivery.get("constraints") or [])
        if filtered:
            return (
                "未在你指定的文档范围内找到足够依据；本次没有搜索该范围之外的知识库。"
                f"已尝试: {attempts}。{suggestion}"
            )
        return (
            "未在当前知识库中找到与当前查询及结构范围匹配的足够依据。"
            f"已尝试: {attempts}。{suggestion}"
        )
    if mode == "no_evidence":
        return f"证据不足：当前没有可用于完成这些分析维度的检索证据。{suggestion}"

    covered = int(delivery.get("covered_count") or 0)
    total = int(delivery.get("total_count") or 0)
    lines = [f"已完成 {covered}/{total} 个分析维度。"]
    for dimension in delivery.get("dimension_evidence") or []:
        for ref in dimension.get("evidence_refs") or []:
            lines.append(
                f"- {dimension.get('label')}（证据摘录，不是生成答案）{_render_ref(ref)}"
            )
    for ref in delivery.get("baseline_evidence") or []:
        if mode == "baseline_only":
            lines.append(f"一般背景证据（不得计入分析覆盖率）：{_render_ref(ref)}")
    lines.append(f"未覆盖维度: [{', '.join(delivery.get('uncovered_dimensions') or [])}]。")
    if mode == "partial_synthesis":
        lines.append(
            "回答约束：仅基于上述证据，为已覆盖维度分别生成部分解答，并保留对应来源；"
            "明确说明整体证据不足。不得回答未覆盖维度，也不得生成跨维度比较、汇总或总体建议。"
        )
    elif mode == "full_coverage_low_confidence":
        lines.extend([
            "全部维度已有相关证据，但整体置信度不足。",
            "交付约束：仅展示上述证据摘录，不生成综合解答。",
            "建议: 核对证据来源或补充更具判别力的查询条件。",
        ])
    else:
        lines.extend([
            "交付约束：仅展示上述一般背景证据，不生成分析解答。",
            "建议: 补充各分析维度的资料或提供更具体的问题。",
        ])
    return "\n".join(lines)


def generate_level3_answer(
    query_plan: PreciseQueryPlan | ComprehensiveQueryPlan,
    attempted_levels: Sequence[int],
    *,
    final_documents: Sequence[dict[str, Any]] = (),
) -> str:
    """Backward-compatible projection; never use this string as a control input."""
    return render_level3_delivery(
        build_level3_delivery(
            query_plan,
            attempted_levels,
            final_documents=final_documents,
        )
    )
