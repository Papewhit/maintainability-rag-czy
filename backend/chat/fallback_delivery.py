from __future__ import annotations


FALLBACK_DELIVERY_HEADER = "Fallback Delivery Instruction:"


def build_fallback_delivery_instruction(
    *,
    fallback_level: int,
    scope_mode_before: str | None = None,
    scope_mode_after: str | None = None,
    level3_answer: str | None = None,
) -> str:
    """Return the single scope-aware instruction shared by both delivery modes."""
    if fallback_level == 3 and level3_answer:
        return (
            "请以以下确定性 Level 3 模板为最终回答基础，不要补充模板没有依据的事实：\n"
            f"{level3_answer}"
        )
    if fallback_level != 2:
        return ""
    if scope_mode_before == "boost" and scope_mode_after == "none":
        return (
            "未在优先文件中找到精确匹配，以下包含范围外相关参考；"
            "请对每个引用标注是否完全匹配，并建议用户补充信息。"
        )
    if scope_mode_before == "filter" and scope_mode_after == "filter":
        return (
            "未在指定文档范围内找到精确匹配，以下是该范围内的相关参考；"
            "本次没有搜索范围外知识库。"
        )
    if scope_mode_before == "none" and scope_mode_after == "none":
        return (
            "未在当前知识库中找到精确匹配，以下是扩大候选池及放宽结构限制后得到的相关参考；"
            "本轮没有改变文档检索范围。"
        )
    return ""
