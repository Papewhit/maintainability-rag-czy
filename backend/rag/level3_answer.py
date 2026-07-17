from __future__ import annotations

from collections.abc import Sequence

from backend.rag.query_plan import ComprehensiveQueryPlan, PreciseQueryPlan


def _attempts(attempted_levels: Sequence[int]) -> str:
    return " → ".join(f"Level {level}" for level in attempted_levels)


def _evidence_text(candidate: dict) -> str:
    return str(
        candidate.get("text")
        or candidate.get("retrieval_text")
        or candidate.get("content")
        or ""
    ).strip()


def _evidence_for_branch(
    final_documents: Sequence[dict],
    branch_id: str,
) -> tuple[str, str]:
    for document in final_documents:
        if branch_id in set(document.get("matched_branch_ids") or []):
            evidence = _evidence_text(document)
            source = (
                f"{document.get('filename', 'Unknown')}，"
                f"第 {document.get('page_number', 'N/A')} 页"
            )
            return evidence, source
    return "", ""


def generate_level3_answer(
    query_plan: PreciseQueryPlan | ComprehensiveQueryPlan,
    attempted_levels: Sequence[int],
    *,
    final_documents: Sequence[dict] = (),
) -> str:
    """Build the deterministic Level 3 answer without retrieval or an LLM."""
    attempts = _attempts(attempted_levels)
    suggestion = "建议: 检查相关文档是否已上传 / 调整问法 / 提供更多上下文文件。"
    if isinstance(query_plan, PreciseQueryPlan):
        if query_plan.scope_mode == "filter":
            return (
                "未在你指定的文档范围内找到足够依据；"
                "本次没有搜索该范围之外的知识库。"
                f"已尝试: {attempts}。"
                f"{suggestion}"
            )
        return (
            "未在当前知识库中找到与当前查询及结构范围匹配的足够依据。"
            f"已尝试: {attempts}。"
            f"{suggestion}"
        )

    covered: list[tuple[str, str, str]] = []
    uncovered: list[str] = []
    for index, sub_query in enumerate(query_plan.sub_queries):
        label = sub_query.domain or sub_query.query
        evidence, source = _evidence_for_branch(
            final_documents,
            f"sub_query_{index}",
        )
        if evidence:
            covered.append((label, evidence, source))
        else:
            uncovered.append(label)

    total = len(query_plan.sub_queries)
    if covered:
        lines = [f"已完成 {len(covered)}/{total} 个分析维度。"]
        lines.extend(
            f"- {label}（证据摘录，不是生成答案）[来源：{source}]：{evidence}"
            for label, evidence, source in covered
        )
        lines.append(f"未覆盖维度: [{', '.join(uncovered)}]。")
        if len(covered) == total:
            lines.append("全部维度已有相关证据，但整体置信度不足。")
            lines.append("交付约束：仅展示上述证据摘录，不生成综合解答。")
            lines.append("建议: 核对证据来源或补充更具判别力的查询条件。")
        else:
            lines.append(
                "回答约束：仅基于上述证据，为已覆盖维度分别生成部分解答，"
                "并保留对应来源；明确说明整体证据不足。"
                "不得回答未覆盖维度，也不得生成跨维度比较、汇总或总体建议。"
            )
        return "\n".join(lines)

    baseline_evidence, _baseline_source = _evidence_for_branch(
        final_documents,
        "baseline",
    )
    if baseline_evidence:
        return "\n".join(
            [
                f"已完成 0/{total} 个分析维度。",
                f"一般背景证据（不得计入分析覆盖率）：{baseline_evidence}",
                f"未覆盖维度: [{', '.join(uncovered)}]。",
                "交付约束：仅展示上述一般背景证据，不生成分析解答。",
                "建议: 补充各分析维度的资料或提供更具体的问题。",
            ]
        )

    return (
        "证据不足：当前没有可用于完成这些分析维度的检索证据。"
        "建议: 检查相关文档是否已上传 / 调整问法 / 提供更多上下文文件。"
    )
