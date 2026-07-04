"""Planner — 生成 Chapter Memo（7段结构），含完结窗口规划."""

from __future__ import annotations

from fanqie.llm.client import LLMClient
from fanqie.models import (
    ChapterMemo, HookScheduleEntry, CompletionPlan,
)
from fanqie.genres.loader import GenreProfile
from fanqie.memory.state_manager import StateManager
from fanqie.memory.hook_lifecycle import get_hook_ledger_summary, compute_recyclable_hooks
from fanqie.memory.fatigue_detector import run_fatigue_checks


def _ensure_list(value) -> list[str]:
    """确保值为字符串列表，防御 LLM 返回字符串的情况."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        if "\n" in value:
            items = [v.strip().lstrip("- ").strip() for v in value.split("\n") if v.strip()]
        elif "、" in value:
            items = [v.strip() for v in value.split("、") if v.strip()]
        elif "," in value:
            items = [v.strip() for v in value.split(",") if v.strip()]
        else:
            items = [value.strip()]
        return [v for v in items if v]
    return [str(value)]


def _ensure_str(value) -> str:
    """确保值为字符串，防御 LLM 返回列表的情况."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value if v)
    return str(value)


# ---- Completion Window ----

COMPLETION_WINDOW_RATIO = 0.15  # 最后 15% 章节进入完结窗口


def compute_completion_window(target_chapters: int) -> int:
    """计算完结窗口起始章."""
    window_size = max(int(target_chapters * COMPLETION_WINDOW_RATIO), 10)
    return target_chapters - window_size + 1


def is_in_completion_window(chapter_number: int, target_chapters: int) -> bool:
    """判断当前是否处于完结窗口."""
    if target_chapters <= 0:
        return False
    return chapter_number >= compute_completion_window(target_chapters)


def is_final_chapter(chapter_number: int, target_chapters: int) -> bool:
    """判断是否为最后一章."""
    return chapter_number == target_chapters


def build_completion_plan(
    hooks_raw: list[dict],
    chapter_number: int,
    target_chapters: int,
    book_id: str,
) -> CompletionPlan:
    """生成完结计划：为所有未回收伏笔分配目标回收章节."""
    window_start = compute_completion_window(target_chapters)
    remaining = target_chapters - chapter_number + 1

    # 过滤未回收伏笔
    resolved_statuses = {"resolved", "closed", "done", "deferred", "paused", "hold"}
    unresolved = [
        h for h in hooks_raw
        if h.get("status", "") not in resolved_statuses
    ]

    # 按紧迫度排序：endgame > slow_burn > mid_arc > near_term > immediate
    timing_priority = {"endgame": 5, "slow_burn": 4, "mid_arc": 3, "near_term": 2, "immediate": 1}
    unresolved.sort(
        key=lambda h: (
            -timing_priority.get(h.get("payoff_timing", "mid_arc"), 3),
            -(h.get("last_advanced_chapter", 0) or h.get("start_chapter", 0)),
        )
    )

    # 分配目标章节：均匀分布在完结窗口内
    schedule: list[HookScheduleEntry] = []
    if unresolved and remaining > 0:
        # 每个伏笔分配一个目标章，尽量均匀分布
        # 使用 round 而非 int 避免截断导致重复分配
        n = len(unresolved)
        for i, hook in enumerate(unresolved):
            # 均匀分布：把 remaining 章分成 n 份，每个伏笔占一份的中点
            offset = round((i + 0.5) / n * remaining)
            target_ch = min(window_start + offset - 1, target_chapters)
            target_ch = max(target_ch, window_start)
            schedule.append(HookScheduleEntry(
                hook_id=hook.get("hook_id", f"hook_{i}"),
                hook_type=hook.get("type", ""),
                target_chapter=target_ch,
                status="pending",
            ))

    # 生成弧线阶段描述
    if remaining >= 20:
        arc_phases = f"""收尾弧线：
第{window_start}-{window_start + remaining // 3}章: 各支线收束
第{window_start + remaining // 3 + 1}-{window_start + 2 * remaining // 3}章: 最终冲突爆发
第{window_start + 2 * remaining // 3 + 1}-{target_chapters}章: 结局与余韵"""
    elif remaining >= 10:
        arc_phases = f"""收尾弧线：
第{window_start}-{window_start + remaining // 2}章: 冲突收束
第{window_start + remaining // 2 + 1}-{target_chapters}章: 结局与余韵"""
    else:
        arc_phases = f"收尾弧线：第{window_start}-{target_chapters}章: 紧凑收束与结局"

    return CompletionPlan(
        book_id=book_id,
        completion_window_start=window_start,
        completion_window_end=target_chapters,
        remaining_chapters=remaining,
        total_unresolved_hooks=len(unresolved),
        hook_schedule=schedule,
        arc_phases=arc_phases,
    )


def validate_completion_feasibility(
    unresolved_hooks: list[dict],
    remaining_chapters: int,
) -> tuple[bool, str]:
    """验证完结可行性：伏笔数量不能超过剩余章数."""
    if len(unresolved_hooks) > remaining_chapters:
        return False, (
            f"❌ 完结不可行！未回收伏笔 ({len(unresolved_hooks)} 个) "
            f"超过剩余章节 ({remaining_chapters} 章)。\n"
            f"请使用 'fanqie advise <book_id> \"合并或提前回收部分伏笔\"' 处理。"
        )
    if len(unresolved_hooks) > remaining_chapters * 0.8:
        return True, (
            f"⚠️ 伏笔较密集：{len(unresolved_hooks)} 个伏笔 / {remaining_chapters} 章，"
            f"平均每章需回收 {len(unresolved_hooks)/remaining_chapters:.1f} 个伏笔。"
        )
    return True, ""


# ---- Prompt Builders ----

def build_anti_monotony_hint(state_mgr: StateManager, chapter_number: int) -> str:
    """基于最近章节摘要构建反单调约束，从生成端主动去重.

    读取最近若干章的 mood/chapter_type 与事件，运行疲劳检测，
    把"需要避免的开篇/情绪/章节功能"作为约束注入 planner prompt。
    """
    summaries = state_mgr.load_summaries()
    prev = [s for s in summaries if s.chapter < chapter_number]
    if len(prev) < 3:
        return ""

    prev.sort(key=lambda s: s.chapter)
    summary_dicts = [
        {"mood": s.mood, "chapter_type": s.chapter_type}
        for s in prev
    ]
    titles = [s.title for s in prev]
    # 用事件文本近似"章节正文"用于开头/结尾模式检测
    chapter_texts = [s.events for s in prev if s.events]

    issues = run_fatigue_checks(chapter_texts, summary_dicts, titles)

    recent = prev[-5:]
    recent_moods = "、".join(dict.fromkeys(s.mood for s in recent if s.mood))
    recent_types = "、".join(dict.fromkeys(s.chapter_type for s in recent if s.chapter_type))

    lines = ["## 反单调约束（避免与近期章节雷同）"]
    if recent_moods:
        lines.append(f"- 最近几章情绪基调：{recent_moods}。若已连续多章同调，本章切换情绪节奏。")
    if recent_types:
        lines.append(f"- 最近几章章节类型：{recent_types}。本章尽量切换章节功能，避免重复同一布局。")
    for issue in issues:
        lines.append(f"- ⚠️ {issue['description']} 建议：{issue['suggestion']}")

    if len(lines) == 1:
        return ""
    return "\n".join(lines) + "\n"


def build_planner_system_prompt(genre: GenreProfile) -> str:
    return f"""你是一位专业的{genre.name}网文策划编辑。为下一章生成结构化 Chapter Memo。
题材规则：{genre.pacing_rule}
爽点类型：{'、'.join(genre.satisfaction_types)}
输出格式：严格 JSON，包含 goal/reader_waiting_for/pay_off/keep_hidden/transition_duty/key_choice_check/end_changes/must_avoid/style_emphasis/hooks_to_advance
注意：must_avoid、style_emphasis 和 hooks_to_advance 必须是字符串数组，即使只有一个元素也要用 [] 包裹。
hooks_to_advance：从"伏笔账本"中挑选本章要推进的伏笔，填写其伏笔ID（如 ch0003_01、core_01），没有则填 []。
pacing（字符串）：规划本章节奏配方——判断本章功能（如 铺垫/过渡/冲突升级/爽点爆发/收束），给出张力曲线与爽点节拍建议，不同功能的章节爽点密度应不同，不要千篇一律。"""


def build_completion_planner_system_prompt(genre: GenreProfile) -> str:
    """完结窗口专用的 Planner system prompt."""
    return f"""你是一位专业的{genre.name}网文策划编辑，当前处于【完结窗口】阶段。

## 完结窗口规则（必须严格遵守）

1. **禁止播种新伏笔**：不得引入任何新的悬念、谜团或未解问题
2. **每章必须推进伏笔回收**：pay_off 字段必须明确列出本章要推进/回收的伏笔
3. **角色弧线收束**：配角开始退场、转变或获得归宿，不要引入新角色
4. **冲突加速解决**：已有冲突线推向解决，不开启新冲突
5. **情绪节奏过渡**：从"紧张/爆发"逐步过渡到"释放/余韵"
6. **呼应开头**：在合适时机呼应第一卷的主题和意象
7. **不留未解悬念**：除开放式结尾外，所有主要问题必须在最终章前解决

## 题材规则
{genre.pacing_rule}
爽点类型：{'、'.join(genre.satisfaction_types)}

输出格式：严格 JSON，包含 goal/reader_waiting_for/pay_off/keep_hidden/transition_duty/key_choice_check/end_changes/must_avoid/style_emphasis/hooks_to_advance
注意：must_avoid、style_emphasis 和 hooks_to_advance 必须是字符串数组。
hooks_to_advance：从"伏笔账本/回收排期"中挑选本章要推进的伏笔ID，没有则填 []。"""


def build_final_chapter_planner_system_prompt(genre: GenreProfile) -> str:
    """最终章专用的 Planner system prompt."""
    return f"""你是一位专业的{genre.name}网文策划编辑，正在规划【最终章】。

## 最终章规则（必须严格遵守）

1. **所有伏笔必须回收**：pay_off 字段列出所有剩余伏笔，本章全部回收
2. **高潮收束**：最终冲突在本章达到顶点并解决
3. **角色归宿**：每个主要角色都要有明确的结局交代
4. **主题呼应**：呼应全书的主题和开篇意象
5. **情感释放**：给读者一个满意的情感收尾
6. **开放式余韵**：可以留一个开放式结尾，但不能留未解悬念
7. **不要仓促**：虽然是最后一章，但节奏要从容，给读者回味空间

## 题材规则
{genre.pacing_rule}

输出格式：严格 JSON，包含 goal/reader_waiting_for/pay_off/keep_hidden/transition_duty/key_choice_check/end_changes/must_avoid/style_emphasis
注意：must_avoid 和 style_emphasis 必须是字符串数组。"""


# ---- Golden Three Planner ----

def build_golden_three_planner_prompt(genre: GenreProfile, chapter_number: int) -> str:
    """构建黄金三章专用 Planner prompt."""
    config = genre.golden_three_config
    if not config:
        return build_planner_system_prompt(genre)

    # 根据章节号选择对应的结构和规则
    if chapter_number == 1:
        structure = config.chapter_1_structure
        rules = config.chapter_1_rules
        chapter_label = "第1章"
    elif chapter_number == 2:
        structure = config.chapter_2_structure
        rules = config.chapter_2_rules
        chapter_label = "第2章"
    else:
        structure = config.chapter_3_structure
        rules = config.chapter_3_rules
        chapter_label = "第3章"

    rules_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules))

    return f"""你是一位专业的{genre.name}网文策划编辑，正在规划【黄金三章】的{chapter_label}。

## 黄金三章总纲

黄金三章是网文成败的关键。前三章必须：
- 第1章：事件→背景→发展→钩子（强冲突开局，主角亮相，极简世界观，强烈钩子）
- 第2章：信息→发展→钩子（金手指亮相，关系补充，冲突升级）
- 第3章：阻碍→升级→期待感（爽点爆发，情绪爆点，信息差钩子）

## {chapter_label} 结构框架：{structure}

## {chapter_label} 必须遵守的规则

{rules_text}

## 题材规则
{genre.pacing_rule}
爽点类型：{'、'.join(genre.satisfaction_types)}

输出格式：严格 JSON，包含 goal/reader_waiting_for/pay_off/keep_hidden/transition_duty/key_choice_check/end_changes/must_avoid/style_emphasis
注意：must_avoid 和 style_emphasis 必须是字符串数组，即使只有一个元素也要用 [] 包裹。"""


# ---- Main Plan Function ----

def plan_chapter(
    client,
    genre,
    state_mgr,
    book_id,
    chapter_number,
    target_chapters=None,
    user_intervention="",
    completion_plan: CompletionPlan | None = None,
):
    """生成 Chapter Memo，支持完结窗口和最终章模式."""
    current_state = state_mgr.read_story_file("current_state.md")
    volume_map = state_mgr.read_story_file("volume_map.md")
    author_intent = state_mgr.read_story_file("author_intent.md")
    current_focus = state_mgr.read_story_file("current_focus.md")
    hook_pool = state_mgr.load_hook_pool()
    hooks_raw = [h.model_dump() for h in hook_pool.hooks]
    hook_ledger = get_hook_ledger_summary(hooks_raw, chapter_number, target_chapters)
    recyclable = compute_recyclable_hooks(hooks_raw, chapter_number, target_chapters)

    # 判断完结状态
    in_completion = is_in_completion_window(chapter_number, target_chapters or 500)
    is_final = is_final_chapter(chapter_number, target_chapters or 500)

    # 选择 system prompt
    if chapter_number <= 3 and genre.golden_three_config:
        system_prompt = build_golden_three_planner_prompt(genre, chapter_number)
    elif is_final:
        system_prompt = build_final_chapter_planner_system_prompt(genre)
    elif in_completion:
        system_prompt = build_completion_planner_system_prompt(genre)
    else:
        system_prompt = build_planner_system_prompt(genre)

    # 构建完结相关上下文
    completion_context = ""
    if in_completion:
        remaining = (target_chapters or 500) - chapter_number + 1
        completion_context = f"""
## ⚠️ 完结窗口 — 剩余 {remaining} 章

{completion_plan.arc_phases if completion_plan else ''}

### 伏笔回收排期（本章需推进的伏笔）
"""
        if completion_plan and completion_plan.hook_schedule:
            # 找到本章附近需要回收的伏笔
            nearby_hooks = [
                h for h in completion_plan.hook_schedule
                if abs(h.target_chapter - chapter_number) <= 3 and h.status == "pending"
            ]
            if nearby_hooks:
                for h in nearby_hooks[:5]:
                    completion_context += f"- {h.hook_id}（目标章 {h.target_chapter}）: {h.hook_type}\n"
            else:
                completion_context += "- 本章无紧急回收任务，但需推进任意活跃伏笔\n"
        completion_context += "\n### 完结规则提醒\n- 禁止播种新伏笔\n- 每章必须推进至少 1 个待回收伏笔\n- 角色弧线开始收束\n"

    # 待回收伏笔列表
    recyclable_text = ""
    if recyclable:
        recyclable_text = "## 待回收伏笔\n"
        for h in recyclable[:5]:
            recyclable_text += f"- {h['hook_id']}: {h.get('type','')}\n"

    intervention_text = ""
    if user_intervention:
        intervention_text = f"## 用户干预指令\n{user_intervention}\n"

    anti_monotony_text = build_anti_monotony_hint(state_mgr, chapter_number)

    user_prompt = (
        f"请为第{chapter_number}章生成 Chapter Memo。\n"
        f"## 当前状态\n{current_state[:2000]}\n"
        f"## 卷纲\n{volume_map[:1500]}\n"
        f"## 作者意图\n{author_intent[:1000]}\n"
        f"## 当前关注点\n{current_focus[:1000]}\n"
        f"## 伏笔账本\n{hook_ledger}\n"
        f"{recyclable_text}"
        f"{anti_monotony_text}"
        f"{completion_context}"
        f"{intervention_text}"
        f"请输出 JSON 格式。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    result = client.chat_json(messages, temperature=0.5)
    parsed = result.get("parsed", {})

    must_avoid = _ensure_list(parsed.get("must_avoid"))
    style_emphasis = _ensure_list(parsed.get("style_emphasis"))

    # 解析本章要推进的伏笔ID，并用真实伏笔池校验，过滤幻觉ID
    valid_hook_ids = {h["hook_id"] for h in hooks_raw if h.get("hook_id")}
    hooks_to_advance = [
        hid for hid in _ensure_list(parsed.get("hooks_to_advance"))
        if hid in valid_hook_ids
    ]

    # 收集本章需回收的伏笔
    hooks_to_resolve: list[str] = []
    if completion_plan and in_completion:
        for h in completion_plan.hook_schedule:
            if h.target_chapter == chapter_number and h.status == "pending":
                hooks_to_resolve.append(h.hook_id)

    memo = ChapterMemo(
        book_id=book_id,
        chapter_number=chapter_number,
        goal=_ensure_str(parsed.get("goal", "")),
        reader_waiting_for=_ensure_str(parsed.get("reader_waiting_for", "")),
        pay_off=_ensure_str(parsed.get("pay_off", "")),
        keep_hidden=_ensure_str(parsed.get("keep_hidden", "")),
        transition_duty=_ensure_str(parsed.get("transition_duty", "")),
        key_choice_check=_ensure_str(parsed.get("key_choice_check", "")),
        end_changes=_ensure_str(parsed.get("end_changes", "")),
        hook_ledger=hook_ledger,
        must_avoid=must_avoid,
        style_emphasis=style_emphasis,
        is_completion_arc=in_completion,
        is_final=is_final,
        hooks_to_resolve=hooks_to_resolve,
        hooks_to_advance=hooks_to_advance,
        pacing=_ensure_str(parsed.get("pacing", "")),
    )
    memo.body = _render_memo_body(memo)
    return memo


def _render_memo_body(memo):
    avoid = "\n".join(f"- {x}" for x in memo.must_avoid) if memo.must_avoid else "- 无"

    # 完结标记
    completion_banner = ""
    if memo.is_final:
        completion_banner = "\n⚠️ **最终章** — 所有伏笔必须回收，角色归宿必须交代\n"
    elif memo.is_completion_arc:
        completion_banner = "\n⚠️ **完结窗口** — 禁止新伏笔，推进已有伏笔回收\n"

    hooks_section = ""
    if memo.hooks_to_resolve:
        hooks_section = f"\n## 本章需回收的伏笔\n" + "\n".join(f"- {h}" for h in memo.hooks_to_resolve)

    return (
        f"{completion_banner}"
        f"## 当前任务\n{memo.goal}\n\n"
        f"## 读者此刻在等什么\n{memo.reader_waiting_for}\n\n"
        f"## 该兑现的 / 暂不揭的\n兑现: {memo.pay_off}\n压牌: {memo.keep_hidden}\n\n"
        f"## 日常/过渡承担什么任务\n{memo.transition_duty}\n\n"
        f"## 关键选择过三连问\n{memo.key_choice_check}\n\n"
        f"## 章末必须发生的变化\n{memo.end_changes}\n\n"
        f"## 本章 hook 账本\n{memo.hook_ledger}\n\n"
        f"## 不要做\n{avoid}"
        f"{hooks_section}"
    )
