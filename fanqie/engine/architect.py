"""Architect — Foundation 生成器：世界观 + 链式反应 + 文明共识 + 主角 + 配角 + 冲突."""

from __future__ import annotations

import json
import re
from typing import Optional

from fanqie.llm.client import LLMClient
from fanqie.genres.loader import GenreProfile
from fanqie.models import (
    WorldSetting, CascadeRule, CascadeRules, CivilizationNorm, CivilizationNorms,
    ProtagonistProfile, SupportingCharacter, CoreConflict, Foundation,
)


def _safe_str(value) -> str:
    """防御 LLM 返回 dict/list 而非 string."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return str(value) if value else ""


# ---------------------------------------------------------------------------
# 1a. 世界观架构（6 要素）
# ---------------------------------------------------------------------------

def generate_world_setting(
    client: LLMClient,
    genre: GenreProfile,
    brief: str = "",
) -> WorldSetting:
    """生成世界观 6 要素."""
    world_modules = getattr(genre, 'world_modules', None)
    emphasis = getattr(genre, 'world_emphasis', {}) if world_modules else {}

    modules_desc = "\n".join(
        f"- {k}: {emphasis.get(k, '')}"
        for k in (world_modules.required if world_modules else
                  ["power_system", "geography", "history", "drive", "factions", "resources"])
    )

    extra_desc = ""
    if world_modules and world_modules.extra:
        extra_desc = "\n## 额外模块\n" + "\n".join(f"- {e}" for e in world_modules.extra)

    system_prompt = f"""你是{genre.name}题材的世界观架构师。请根据以下要求生成完整的世界观设定。

## 世界观 6 要素
{modules_desc}
{extra_desc}

## 输出格式（严格 JSON）
{{
  "power_system": "力量体系描述",
  "geography": "地理描述",
  "history": "历史描述",
  "drive": "世界前进的动力",
  "factions": "势力格局",
  "resources": "资源分配与权力循环",
  "extra_modules": {{}}
}}

每个要素至少 200 字，要有具体细节而非空泛描述。"""

    user_prompt = f"请为{genre.name}题材生成世界观设定。"
    if brief:
        user_prompt += f"\n\n## 用户创意简报\n{brief[:3000]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.7)
    parsed = result.get("parsed", {})

    return WorldSetting(
        power_system=_safe_str(parsed.get("power_system", "")),
        geography=_safe_str(parsed.get("geography", "")),
        history=_safe_str(parsed.get("history", "")),
        drive=_safe_str(parsed.get("drive", "")),
        factions=_safe_str(parsed.get("factions", "")),
        resources=_safe_str(parsed.get("resources", "")),
        extra_modules=_flatten_extra_modules(parsed.get("extra_modules", {})),
    )


# ---------------------------------------------------------------------------
# 1b. 链式反应设计
# ---------------------------------------------------------------------------

def generate_cascade_rules(
    client: LLMClient,
    genre: GenreProfile,
    world_setting: WorldSetting,
) -> CascadeRules:
    """从世界观推导链式反应."""
    world_text = _render_world_setting_text(world_setting)

    system_prompt = f"""你是{genre.name}题材的逻辑架构师。请从世界观设定中推导链式反应。

## 链式反应结构
每个核心设定推导 2-3 层连锁影响：
A 设定 → B 后果 → C 社会变化 → D 新矛盾

确保设定之间互相咬合，不是孤立的"设定列表"。

## 输出格式（严格 JSON）
{{
  "rules": [
    {{
      "setting": "核心设定",
      "consequence_1": "第一层后果",
      "consequence_2": "第二层社会变化",
      "consequence_3": "第三层新矛盾"
    }}
  ]
}}

至少生成 5 条链式反应规则。"""

    user_prompt = f"## 世界观设定\n{world_text[:4000]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.6)
    parsed = result.get("parsed", {})

    rules = []
    for r in parsed.get("rules", []):
        rules.append(CascadeRule(
            setting=_safe_str(r.get("setting", "")),
            consequence_1=_safe_str(r.get("consequence_1", "")),
            consequence_2=_safe_str(r.get("consequence_2", "")),
            consequence_3=_safe_str(r.get("consequence_3", "")),
        ))

    return CascadeRules(book_id="", rules=rules)


# ---------------------------------------------------------------------------
# 1c. 文明共识
# ---------------------------------------------------------------------------

def generate_civilization_norms(
    client: LLMClient,
    genre: GenreProfile,
    world_setting: WorldSetting,
    cascade_rules: CascadeRules,
) -> CivilizationNorms:
    """生成文明共识."""
    world_text = _render_world_setting_text(world_setting)
    cascade_text = _render_cascade_text(cascade_rules)

    norms_config = getattr(genre, 'civilization_norms_config', None)
    count = norms_config.count if norms_config else 5
    prompt_hint = norms_config.prompt_hint if norms_config else "从世界观推导该世界中人们不言自明的基本认知"

    system_prompt = f"""你是{genre.name}题材的社会学家。请从世界观和链式反应中提炼文明共识。

## 文明共识
这些共识是角色行为的"操作系统"，除非弧光设计明确打破。
{prompt_hint}

## 输出格式（严格 JSON）
{{
  "norms": [
    {{
      "norm": "世界默认行为准则",
      "derivation": "从哪个设定推导而来"
    }}
  ]
}}

生成 {count} 条文明共识。"""

    user_prompt = f"## 世界观设定\n{world_text[:3000]}\n\n## 链式反应\n{cascade_text[:2000]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.6)
    parsed = result.get("parsed", {})

    norms = []
    for n in parsed.get("norms", []):
        norms.append(CivilizationNorm(
            norm=n.get("norm", ""),
            derivation=n.get("derivation", ""),
        ))

    return CivilizationNorms(book_id="", norms=norms)


# ---------------------------------------------------------------------------
# 1d. 主角设定
# ---------------------------------------------------------------------------

def generate_protagonist(
    client: LLMClient,
    genre: GenreProfile,
    world_setting: WorldSetting,
    norms: CivilizationNorms,
) -> ProtagonistProfile:
    """生成主角 5 维度设定."""
    world_text = _render_world_setting_text(world_setting)
    norms_text = "\n".join(f"- {n.norm}（来自: {n.derivation}）" for n in norms.norms)

    protagonist_config = getattr(genre, 'protagonist_config', None)
    identity_hint = protagonist_config.identity_hint if protagonist_config else ""
    motivation_hint = protagonist_config.motivation_hint if protagonist_config else ""
    arc_hint = protagonist_config.arc_hint if protagonist_config else ""

    system_prompt = f"""你是{genre.name}题材的角色设计师。请根据世界观和文明共识设计主角。

## 主角 5 维度
1. 身份：表面身份 + 隐藏身世 + 社会阶层轨迹
2. 动机：近期/中期/长期（三层递进）
3. 性格：核心特质 + 致命缺陷 + 内在冲突
4. 弧光：按卷规划角色蜕变节点（从哪里到哪里）
5. 金手指：能力说明 + 限制条件 + 成长路径 + 为什么不崩平衡

{identity_hint}
{motivation_hint}
{arc_hint}

## 输出格式（严格 JSON）
{{
  "identity": "身份描述",
  "motivation": "动机描述",
  "personality": "性格描述",
  "arc": "弧光描述",
  "golden_finger": "金手指描述"
}}"""

    user_prompt = f"## 世界观设定\n{world_text[:3000]}\n\n## 文明共识\n{norms_text[:1500]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.7)
    parsed = result.get("parsed", {})

    return ProtagonistProfile(
        identity=_safe_str(parsed.get("identity", "")),
        motivation=_safe_str(parsed.get("motivation", "")),
        personality=_safe_str(parsed.get("personality", "")),
        arc=_safe_str(parsed.get("arc", "")),
        golden_finger=_safe_str(parsed.get("golden_finger", "")),
    )


# ---------------------------------------------------------------------------
# 1e. 核心配角
# ---------------------------------------------------------------------------

def generate_characters(
    client: LLMClient,
    genre: GenreProfile,
    protagonist: ProtagonistProfile,
    world_setting: WorldSetting,
) -> list[SupportingCharacter]:
    """生成核心配角 3-5 人."""
    world_text = _render_world_setting_text(world_setting)

    system_prompt = f"""你是{genre.name}题材的角色设计师。请根据主角设定和世界观设计 3-5 个核心配角。

## 配角设计要求
- 身份背景 + 与主角的关系定位（盟友/对手/灰色地带）
- 个人动机（独立于主角的自身诉求）
- 与主角的互补/对立维度（性格互补？利益冲突？理念分歧？）
- 命运走向（哪些配角会在哪卷退场/转变/黑化）

## 输出格式（严格 JSON）
{{
  "characters": [
    {{
      "name": "角色名",
      "role": "盟友/对手/灰色地带",
      "background": "身份背景",
      "motivation": "个人动机",
      "complement_dimension": "与主角的互补/对立维度",
      "fate": "命运走向"
    }}
  ]
}}"""

    user_prompt = f"""## 主角设定
身份: {protagonist.identity}
动机: {protagonist.motivation}
性格: {protagonist.personality}
弧光: {protagonist.arc}

## 世界观
{world_text[:2000]}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.7)
    parsed = result.get("parsed", {})

    characters = []
    for c in parsed.get("characters", []):
        characters.append(SupportingCharacter(
            name=c.get("name", ""),
            role=c.get("role", ""),
            background=c.get("background", ""),
            motivation=c.get("motivation", ""),
            complement_dimension=c.get("complement_dimension", ""),
            fate=c.get("fate", ""),
        ))

    return characters


# ---------------------------------------------------------------------------
# 1f. 核心冲突线
# ---------------------------------------------------------------------------

def generate_core_conflict(
    client: LLMClient,
    genre: GenreProfile,
    protagonist: ProtagonistProfile,
    characters: list[SupportingCharacter],
    world_setting: WorldSetting,
) -> CoreConflict:
    """生成核心冲突线."""
    world_text = _render_world_setting_text(world_setting)
    chars_text = "\n".join(
        f"- {c.name}（{c.role}）: {c.motivation}"
        for c in characters
    )

    system_prompt = f"""你是{genre.name}题材的剧情架构师。请根据主角、配角和世界观设计核心冲突线。

## 三条冲突线
1. 主角 vs 世界的根本矛盾
2. 主角 vs 反派的核心对立
3. 主角内在冲突（性格缺陷 vs 目标的张力）

## 输出格式（严格 JSON）
{{
  "protagonist_vs_world": "主角 vs 世界的根本矛盾",
  "protagonist_vs_antagonist": "主角 vs 反派的核心对立",
  "protagonist_inner": "主角内在冲突"
}}"""

    user_prompt = f"""## 主角
身份: {protagonist.identity}
动机: {protagonist.motivation}
性格: {protagonist.personality}

## 配角
{chars_text}

## 世界观
{world_text[:2000]}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.6)
    parsed = result.get("parsed", {})

    return CoreConflict(
        protagonist_vs_world=_safe_str(parsed.get("protagonist_vs_world", "")),
        protagonist_vs_antagonist=_safe_str(parsed.get("protagonist_vs_antagonist", "")),
        protagonist_inner=_safe_str(parsed.get("protagonist_inner", "")),
    )


# ---------------------------------------------------------------------------
# 完整 Foundation 生成
# ---------------------------------------------------------------------------

def generate_foundation(
    client: LLMClient,
    genre: GenreProfile,
    book_id: str,
    brief: str = "",
) -> Foundation:
    """按依赖顺序生成完整 Foundation."""
    # 1a. 世界观
    world_setting = generate_world_setting(client, genre, brief)

    # 1b. 链式反应（依赖 1a）
    cascade_rules = generate_cascade_rules(client, genre, world_setting)
    cascade_rules.book_id = book_id

    # 1c. 文明共识（依赖 1a + 1b）
    norms = generate_civilization_norms(client, genre, world_setting, cascade_rules)
    norms.book_id = book_id

    # 1d. 主角（依赖 1a + 1b + 1c）
    protagonist = generate_protagonist(client, genre, world_setting, norms)

    # 1e. 配角（依赖 1d）
    characters = generate_characters(client, genre, protagonist, world_setting)

    # 1f. 核心冲突（依赖 1d + 1e）
    core_conflict = generate_core_conflict(client, genre, protagonist, characters, world_setting)

    return Foundation(
        book_id=book_id,
        world_setting=world_setting,
        cascade_rules=cascade_rules,
        civilization_norms=norms,
        protagonist=protagonist,
        supporting_characters=characters,
        core_conflict=core_conflict,
    )


# ---------------------------------------------------------------------------
# 展示摘要（供用户确认）
# ---------------------------------------------------------------------------

def present_foundation_summary(foundation: Foundation, genre_name: str) -> str:
    """生成 Foundation 摘要文本，供用户确认."""
    ws = foundation.world_setting
    cp = foundation.core_conflict
    p = foundation.protagonist

    lines = [
        f"# {genre_name} — Foundation 摘要",
        "",
        "## 世界观要点",
        "",
        f"**力量体系**: {ws.power_system[:200]}...",
        f"**地理**: {ws.geography[:150]}...",
        f"**历史**: {ws.history[:150]}...",
        f"**世界动力**: {ws.drive[:150]}...",
        f"**势力格局**: {ws.factions[:150]}...",
        f"**资源循环**: {ws.resources[:150]}...",
        "",
        f"## 链式反应（共 {len(foundation.cascade_rules.rules)} 条）",
    ]
    for i, cr in enumerate(foundation.cascade_rules.rules[:3], 1):
        lines.append(f"{i}. {cr.setting[:80]} → {cr.consequence_1[:60]} → {cr.consequence_2[:60]}")

    lines.extend([
        "",
        f"## 文明共识（共 {len(foundation.civilization_norms.norms)} 条）",
    ])
    for n in foundation.civilization_norms.norms:
        lines.append(f"- {n.norm}")

    lines.extend([
        "",
        "## 主角定位",
        f"**身份**: {p.identity[:200]}",
        f"**动机**: {p.motivation[:200]}",
        f"**性格**: {p.personality[:150]}",
        f"**弧光**: {p.arc[:150]}",
        f"**金手指**: {p.golden_finger[:150]}",
        "",
        "## 核心配角",
    ])
    for c in foundation.supporting_characters:
        lines.append(f"- **{c.name}**（{c.role}）: {c.background[:80]} | 命运: {c.fate}")

    lines.extend([
        "",
        "## 核心冲突",
        f"- 主角 vs 世界: {cp.protagonist_vs_world[:200]}",
        f"- 主角 vs 反派: {cp.protagonist_vs_antagonist[:200]}",
        f"- 内在冲突: {cp.protagonist_inner[:200]}",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 持久化 Foundation 到文件
# ---------------------------------------------------------------------------

def save_foundation_to_files(foundation: Foundation, story_dir: str) -> None:
    """将 Foundation 写入 story/foundation/ 目录下的各个文件."""
    import os
    foundation_dir = os.path.join(story_dir, "foundation")
    os.makedirs(foundation_dir, exist_ok=True)

    ws = foundation.world_setting
    cp = foundation.core_conflict

    # world.md（合并 story_frame + cascade_rules + civilization_norms）
    world_md = f"""# 世界观设定

## 力量体系
{ws.power_system}

## 地理
{ws.geography}

## 历史
{ws.history}

## 世界前进的动力
{ws.drive}

## 势力格局
{ws.factions}

## 资源分配与权力循环
{ws.resources}

## 核心冲突

### 主角 vs 世界
{cp.protagonist_vs_world}

### 主角 vs 反派
{cp.protagonist_vs_antagonist}

### 主角内在冲突
{cp.protagonist_inner}

## 链式反应设计
"""
    for i, cr in enumerate(foundation.cascade_rules.rules, 1):
        world_md += f"""### 规则 {i}: {cr.setting}
- 第一层后果: {cr.consequence_1}
- 第二层社会变化: {cr.consequence_2}
- 第三层新矛盾: {cr.consequence_3}

"""

    world_md += "## 文明共识\n\n"
    for n in foundation.civilization_norms.norms:
        world_md += f"- **{n.norm}**（推导自: {n.derivation}）\n"

    _write_file(os.path.join(foundation_dir, "world.md"), world_md)

    # protagonist.md
    p = foundation.protagonist
    protagonist_md = f"""# 主角设定

## 身份
{p.identity}

## 动机
{p.motivation}

## 性格
{p.personality}

## 弧光
{p.arc}

## 金手指
{p.golden_finger}
"""
    _write_file(os.path.join(foundation_dir, "protagonist.md"), protagonist_md)

    # 配角文件 → foundation/characters/
    chars_dir = os.path.join(foundation_dir, "characters")
    os.makedirs(chars_dir, exist_ok=True)
    for c in foundation.supporting_characters:
        safe_name = c.name.replace(" ", "_").lower()
        char_md = f"""# {c.name}

- **角色定位**: {c.role}
- **身份背景**: {c.background}
- **个人动机**: {c.motivation}
- **与主角的关系维度**: {c.complement_dimension}
- **命运走向**: {c.fate}
"""
        _write_file(os.path.join(chars_dir, f"{safe_name}.md"), char_md)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_world_setting_text(ws: WorldSetting) -> str:
    return f"""力量体系: {ws.power_system}
地理: {ws.geography}
历史: {ws.history}
世界动力: {ws.drive}
势力格局: {ws.factions}
资源循环: {ws.resources}"""


def _render_cascade_text(cr: CascadeRules) -> str:
    lines = []
    for i, r in enumerate(cr.rules, 1):
        lines.append(f"{i}. {r.setting} → {r.consequence_1} → {r.consequence_2} → {r.consequence_3}")
    return "\n".join(lines)


def _write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _flatten_extra_modules(extra: dict) -> dict[str, str]:
    """将嵌套的 extra_modules 展平为 dict[str, str]."""
    result = {}
    for key, value in extra.items():
        if isinstance(value, dict):
            # 将嵌套 dict 转为多行字符串
            lines = []
            for k, v in value.items():
                if isinstance(v, (list, dict)):
                    lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
                else:
                    lines.append(f"{k}: {v}")
            result[key] = "\n".join(lines)
        elif isinstance(value, list):
            result[key] = "\n".join(str(v) for v in value)
        else:
            result[key] = str(value)
    return result
