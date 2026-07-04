"""Intervener — 人工干预处理."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InterventionType(str, Enum):
    DIRECTION = "direction"       # 方向调整
    CHARACTER = "character"       # 角色干预
    PACING = "pacing"             # 节奏干预
    HARD_EDIT = "hard_edit"       # 硬编辑（直接修改文本）
    GENERAL = "general"           # 通用指令


@dataclass
class Intervention:
    """用户干预指令."""
    type: InterventionType
    instruction: str
    target_chapter: int | None = None  # None = 应用到下一章
    created_at: str = ""


def parse_intervention(text: str) -> Intervention:
    """解析用户干预文本."""
    text = text.strip()

    if any(kw in text for kw in ["方向", "剧情走向", "主线", "结局"]):
        itype = InterventionType.DIRECTION
    elif any(kw in text for kw in ["角色", "人物", "性格", "关系", "感情", "人设"]):
        itype = InterventionType.CHARACTER
    elif any(kw in text for kw in ["节奏", "速度", "进度", "篇幅", "详略"]):
        itype = InterventionType.PACING
    elif any(kw in text for kw in ["修改", "替换文本", "直接改"]):
        itype = InterventionType.HARD_EDIT
    else:
        itype = InterventionType.GENERAL

    return Intervention(type=itype, instruction=text)


def render_intervention_prompt(interventions: list[Intervention]) -> str:
    """将干预列表渲染为 prompt 片段."""
    if not interventions:
        return ""

    lines = ["## 用户干预指令", ""]
    for i in interventions:
        type_label = {
            InterventionType.DIRECTION: "方向调整",
            InterventionType.CHARACTER: "角色干预",
            InterventionType.PACING: "节奏干预",
            InterventionType.HARD_EDIT: "硬编辑",
            InterventionType.GENERAL: "通用指令",
        }.get(i.type, "指令")

        lines.append(f"### {type_label}")
        lines.append(i.instruction)
        lines.append("")

    lines.append("请严格遵循以上干预指令进行创作。")
    return "\n".join(lines)
