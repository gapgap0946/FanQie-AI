"""Volume Planner — 卷纲规划器：分卷 + 伏笔播种 + 节奏规划."""

from __future__ import annotations

import json
import os

from fanqie.llm.client import LLMClient
from fanqie.genres.loader import GenreProfile
from fanqie.models import (
    Foundation, Volume, VolumePlan, CascadeRules, CivilizationNorms,
    Hook, HookPool, HookStatus, HookPayoffTiming, HookLevel,
)


def plan_volumes(
    client: LLMClient,
    genre: GenreProfile,
    foundation: Foundation,
    target_chapters: int,
) -> VolumePlan:
    """根据 Foundation 规划分卷."""
    chapters_per_volume = _calc_chapters_per_volume(target_chapters)
    volume_count = max(1, target_chapters // chapters_per_volume)

    # 渲染 Foundation 摘要
    foundation_text = _render_foundation_for_planning(foundation)

    system_prompt = f"""你是{genre.name}题材的卷纲规划师。请根据 Foundation 设定规划分卷。

## 分卷规则
- 目标总章数: {target_chapters}
- 每卷约 {chapters_per_volume} 章
- 共 {volume_count} 卷
- 每卷必须有：主线目标 + 高潮节点 + 关键转折
- 转折设计需参考链式反应（利用连锁反应制造意外）
- 角色行为需符合文明共识（除非该卷设计了规范突破）

## 输出格式（严格 JSON）
{{
  "volumes": [
    {{
      "volume_number": 1,
      "chapter_range": "1-50",
      "main_goal": "本卷主线目标",
      "climax": "高潮节点",
      "key_turns": ["转折1", "转折2"],
      "hook_plan": ["播种伏笔A", "回收伏笔B"],
      "pacing": "紧张/舒缓/爆发分布",
      "norm_breaks": ["打破文明共识X的节点"]
    }}
  ]
}}"""

    user_prompt = f"## Foundation 设定\n{foundation_text[:6000]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.6)
    parsed = result.get("parsed", {})

    volumes = []
    for v in parsed.get("volumes", []):
        volumes.append(Volume(
            volume_number=v.get("volume_number", 0),
            chapter_range=v.get("chapter_range", ""),
            main_goal=v.get("main_goal", ""),
            climax=v.get("climax", ""),
            key_turns=v.get("key_turns", []),
            hook_plan=v.get("hook_plan", []),
            pacing=v.get("pacing", ""),
            norm_breaks=v.get("norm_breaks", []),
        ))

    return VolumePlan(book_id=foundation.book_id, volumes=volumes)


def plan_hook_schedule(
    client: LLMClient,
    genre: GenreProfile,
    volumes: VolumePlan,
    cascade_rules: CascadeRules,
    core_hooks_count: int = 5,
) -> list[Hook]:
    """根据卷纲和链式反应播种伏笔."""
    cascade_text = "\n".join(
        f"- {r.setting[:80]} → {r.consequence_1[:60]} → {r.consequence_2[:60]}"
        for r in cascade_rules.rules[:5]
    )

    volume_text = "\n".join(
        f"第{v.volume_number}卷 ({v.chapter_range}): {v.main_goal}"
        for v in volumes.volumes
    )

    system_prompt = f"""你是{genre.name}题材的伏笔设计师。请根据卷纲和链式反应设计核心伏笔。

## 伏笔要求
- 生成 {core_hooks_count} 个核心伏笔
- 每个伏笔标注播种卷和回收卷
- 参考链式反应设计伏笔之间的依赖关系
- 伏笔类型: 身份/能力/关系/世界观/阴谋

## 输出格式（严格 JSON）
{{
  "hooks": [
    {{
      "hook_id": "hook_001",
      "type": "身份/能力/关系/世界观/阴谋",
      "plant_volume": 1,
      "payoff_volume": 3,
      "payoff_timing": "mid_arc/slow_burn/endgame",
      "notes": "伏笔说明",
      "seed_text": "播种文本示例",
      "depends_on": []
    }}
  ]
}}"""

    user_prompt = f"## 卷纲\n{volume_text}\n\n## 链式反应\n{cascade_text}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.7)
    parsed = result.get("parsed", {})

    hooks = []
    chapters_per_volume = _calc_chapters_per_volume(
        sum(_parse_chapter_range(v.chapter_range) for v in volumes.volumes)
    )

    for h in parsed.get("hooks", []):
        plant_vol = h.get("plant_volume", 1)
        payoff_vol = h.get("payoff_volume", len(volumes.volumes))

        timing_map = {
            "immediate": HookPayoffTiming.IMMEDIATE,
            "near_term": HookPayoffTiming.NEAR_TERM,
            "mid_arc": HookPayoffTiming.MID_ARC,
            "slow_burn": HookPayoffTiming.SLOW_BURN,
            "endgame": HookPayoffTiming.ENDGAME,
        }
        payoff_timing = timing_map.get(h.get("payoff_timing", "mid_arc"), HookPayoffTiming.MID_ARC)

        hooks.append(Hook(
            hook_id=h.get("hook_id", f"hook_{len(hooks)+1:03d}"),
            book_id=volumes.book_id,
            start_chapter=(plant_vol - 1) * chapters_per_volume + 1,
            type=h.get("type", ""),
            status=HookStatus.PLANTED,
            expected_payoff=f"第{payoff_vol}卷回收",
            payoff_timing=payoff_timing,
            notes=h.get("notes", ""),
            seed_text=h.get("seed_text", ""),
            depends_on=h.get("depends_on", []),
            core_hook=True,
            promoted=True,
        ))

    return hooks


def plan_volume_hooks(
    client: LLMClient,
    genre: GenreProfile,
    volume: Volume,
    book_id: str,
    chapter_number: int,
    chapters_per_volume: int,
    volume_hooks_count: int = 10,
) -> list[Hook]:
    """为一卷播种卷级伏笔（中短期，卷内回收）."""
    vol_start = (volume.volume_number - 1) * chapters_per_volume + 1
    vol_end = min(volume.volume_number * chapters_per_volume, 9999)

    system_prompt = f"""你是{genre.name}题材的伏笔设计师。请为当前卷播种卷级伏笔。

## 卷级伏笔规则
- 生成 {volume_hooks_count} 个卷级伏笔
- 这些伏笔必须在本卷内（第{vol_start}-{vol_end}章）回收
- 类型分布：角色关系 30%、能力升级 25%、冲突升级 25%、世界观揭示 20%
- 每个伏笔标注播种章（当前章附近）和回收章（卷内）
- 伏笔之间可以有依赖关系
- 不要与核心伏笔重复

## 输出格式（严格 JSON）
{{
  "hooks": [
    {{
      "type": "角色关系/能力升级/冲突升级/世界观揭示",
      "plant_chapter": {chapter_number},
      "payoff_chapter": {min(chapter_number + 15, vol_end)},
      "payoff_timing": "near_term",
      "notes": "伏笔说明（50字以内）",
      "seed_text": "播种文本示例（用于后续识别）"
    }}
  ]
}}"""

    user_prompt = f"""## 当前卷信息
卷号: 第{volume.volume_number}卷
章节范围: {volume.chapter_range}
主线目标: {volume.main_goal}
高潮节点: {volume.climax}
关键转折: {'; '.join(volume.key_turns[:3])}

请为本卷播种 {volume_hooks_count} 个卷级伏笔。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.7)
    parsed = result.get("parsed", {})

    timing_map = {
        "immediate": HookPayoffTiming.IMMEDIATE,
        "near_term": HookPayoffTiming.NEAR_TERM,
        "mid_arc": HookPayoffTiming.MID_ARC,
        "slow_burn": HookPayoffTiming.SLOW_BURN,
        "endgame": HookPayoffTiming.ENDGAME,
    }

    hooks = []
    for i, h in enumerate(parsed.get("hooks", [])):
        plant_ch = h.get("plant_chapter", chapter_number)
        payoff_ch = h.get("payoff_chapter", chapter_number + 10)
        payoff_timing = timing_map.get(h.get("payoff_timing", "near_term"), HookPayoffTiming.NEAR_TERM)

        hook_id = f"vol{volume.volume_number:02d}_{i+1:03d}"
        hooks.append(Hook(
            hook_id=hook_id,
            book_id=book_id,
            start_chapter=plant_ch,
            type=h.get("type", ""),
            status=HookStatus.PLANTED,
            expected_payoff=f"第{payoff_ch}章回收",
            payoff_timing=payoff_timing,
            notes=h.get("notes", ""),
            seed_text=h.get("seed_text", ""),
            depends_on=h.get("depends_on", []),
            core_hook=False,
            promoted=True,
            hook_level=HookLevel.VOLUME,
            volume_number=volume.volume_number,
        ))

    return hooks


def plan_pacing(
    volumes: VolumePlan,
    civilization_norms: CivilizationNorms,
) -> list[dict]:
    """节奏规划：标注哪些卷打破共识."""
    pacing_notes = []
    for v in volumes.volumes:
        note = {
            "volume": v.volume_number,
            "chapter_range": v.chapter_range,
            "pacing": v.pacing,
            "norm_breaks": [],
        }
        for nb in v.norm_breaks:
            for norm in civilization_norms.norms:
                if norm.norm[:10] in nb or nb[:10] in norm.norm:
                    note["norm_breaks"].append({
                        "norm": norm.norm,
                        "break_point": nb,
                    })
                    break
        pacing_notes.append(note)
    return pacing_notes


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------

def save_volume_plan(volume_plan: VolumePlan, story_dir: str) -> None:
    """保存卷纲到 foundation/ 目录."""
    foundation_dir = os.path.join(story_dir, "foundation")
    os.makedirs(foundation_dir, exist_ok=True)

    lines = ["# 卷纲规划", ""]
    for v in volume_plan.volumes:
        lines.extend([
            f"## 第{v.volume_number}卷 ({v.chapter_range})",
            "",
            f"**主线目标**: {v.main_goal}",
            f"**高潮节点**: {v.climax}",
            "",
            "**关键转折**:",
        ])
        for t in v.key_turns:
            lines.append(f"- {t}")
        lines.append("")
        lines.append("**伏笔计划**:")
        for h in v.hook_plan:
            lines.append(f"- {h}")
        lines.append("")
        lines.append(f"**节奏**: {v.pacing}")
        if v.norm_breaks:
            lines.append(f"**打破共识**: {'、'.join(v.norm_breaks)}")
        lines.append("")

    with open(os.path.join(foundation_dir, "volume_map.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def save_hooks_to_pool(hooks: list[Hook], story_dir: str) -> None:
    """保存伏笔到 runtime/ 目录下的 hooks.json."""
    runtime_dir = os.path.join(story_dir, "runtime")
    os.makedirs(runtime_dir, exist_ok=True)

    pool = HookPool(book_id="", hooks=hooks)
    with open(os.path.join(runtime_dir, "hooks.json"), "w", encoding="utf-8") as f:
        json.dump(pool.model_dump(), f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calc_chapters_per_volume(target_chapters: int) -> int:
    """计算每卷章数（30-80 章范围）."""
    if target_chapters <= 80:
        return target_chapters
    for c in [80, 70, 60, 50, 40, 30]:
        if target_chapters % c == 0:
            return c
    return 50


def _parse_chapter_range(range_str: str) -> int:
    """解析章节范围字符串，返回章数."""
    import re
    m = re.match(r"(\d+)\s*-\s*(\d+)", range_str)
    if m:
        return int(m.group(2)) - int(m.group(1)) + 1
    return 50


def _render_foundation_for_planning(foundation: Foundation) -> str:
    """渲染 Foundation 摘要用于卷纲规划."""
    ws = foundation.world_setting
    p = foundation.protagonist
    cp = foundation.core_conflict

    chars_text = "\n".join(
        f"- {c.name}（{c.role}）: {c.motivation[:60]}"
        for c in foundation.supporting_characters
    )

    cascade_text = "\n".join(
        f"- {r.setting[:60]} → {r.consequence_1[:40]}"
        for r in foundation.cascade_rules.rules[:5]
    )

    norms_text = "\n".join(
        f"- {n.norm}"
        for n in foundation.civilization_norms.norms
    )

    return f"""## 世界观
力量体系: {ws.power_system[:200]}
地理: {ws.geography[:150]}
势力格局: {ws.factions[:150]}

## 链式反应
{cascade_text}

## 文明共识
{norms_text}

## 主角
身份: {p.identity[:150]}
动机: {p.motivation[:150]}
弧光: {p.arc[:150]}
金手指: {p.golden_finger[:150]}

## 配角
{chars_text}

## 核心冲突
- vs 世界: {cp.protagonist_vs_world[:150]}
- vs 反派: {cp.protagonist_vs_antagonist[:150]}
- 内在: {cp.protagonist_inner[:150]}"""
