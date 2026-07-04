"""Settler — 章后结算：摘要、状态更新、伏笔推进、完结追踪."""

from __future__ import annotations

import re
from datetime import datetime

from fanqie.llm.client import LLMClient
from fanqie.models import (
    Chapter, ChapterMemo, ChapterSummary, CurrentState, Fact, Hook, HookPool,
    CompletionPlan, CompletionReport, CharacterEnding, HookScheduleEntry,
    HookLevel, HookStatus, HookPayoffTiming,
)
from fanqie.genres.loader import GenreProfile
from fanqie.memory.state_manager import StateManager


def settle_chapter(
    client: LLMClient,
    genre: GenreProfile,
    state_mgr: StateManager,
    chapter: Chapter,
    memo: ChapterMemo,
    completion_plan: CompletionPlan | None = None,
) -> None:
    """章后结算 — 更新摘要、状态、伏笔，完结窗口时追踪进度."""

    # 1. 生成章节摘要
    summary = ChapterSummary(
        chapter=chapter.chapter_number,
        title=chapter.title,
        characters=_extract_characters(chapter.content),
        events=_summarize_events(chapter.content),
        state_changes=memo.end_changes,
        hook_activity=memo.pay_off,
        mood=_detect_mood(chapter.content),
        chapter_type=_detect_chapter_type(chapter.content, genre),
    )
    summaries = state_mgr.load_summaries()
    summaries = [s for s in summaries if s.chapter != chapter.chapter_number]
    summaries.append(summary)
    summaries.sort(key=lambda s: s.chapter)
    state_mgr.save_summaries(summaries)

    # 2. 更新当前状态
    current_state = state_mgr.load_current_state()
    current_state.chapter_number = chapter.chapter_number

    new_facts = _extract_facts_from_chapter(chapter)
    for fact in new_facts:
        current_state.facts.append(fact)

    current_state.current_conflict = _extract_conflict(chapter.content)
    current_state.current_goal = memo.goal
    current_state.protagonist_state = _extract_protagonist_state(chapter.content)

    state_mgr.save_current_state(current_state)

    # 3. 更新伏笔
    hook_pool = state_mgr.load_hook_pool()
    _update_hooks_from_memo(hook_pool, memo, chapter.chapter_number)

    # 完结窗口：标记已回收伏笔
    if completion_plan and memo.is_completion_arc:
        _update_completion_progress(hook_pool, completion_plan, chapter.chapter_number)

    # 章后伏笔发现：从章节内容中自动发现新播种的伏笔/钩子
    if not memo.is_completion_arc:
        discovered = _discover_hooks_from_chapter(
            client, genre, chapter, hook_pool, state_mgr,
        )
        for h in discovered:
            hook_pool.hooks.append(h)

    state_mgr.save_hook_pool(hook_pool)

    # 4. 完结窗口：保存更新后的完结计划
    if completion_plan and memo.is_completion_arc:
        _save_completion_plan(state_mgr, completion_plan)


def finalize_book(
    client: LLMClient,
    genre: GenreProfile,
    state_mgr: StateManager,
    book_id: str,
    book_title: str,
    total_chapters: int,
    total_words: int,
) -> CompletionReport:
    """全书完结：生成完结报告."""
    hook_pool = state_mgr.load_hook_pool()

    # 强制标记所有未回收伏笔为 resolved
    for hook in hook_pool.hooks:
        if hook.status.value not in ("resolved", "deferred"):
            hook.status = HookStatus.RESOLVED
    state_mgr.save_hook_pool(hook_pool)

    # 生成完结报告
    resolved = sum(1 for h in hook_pool.hooks if h.status.value in ("resolved", "deferred"))
    total_hooks = len(hook_pool.hooks)

    # 收集章节摘要用于生成全书总结
    summaries = state_mgr.load_summaries()
    summary_text = _generate_book_summary(summaries, book_title)

    # 从 Foundation 和卷纲提取角色信息
    story_frame = state_mgr.read_story_file("story_frame.md")
    volume_map = state_mgr.read_story_file("volume_map.md")
    character_endings = _extract_character_endings(story_frame, volume_map)

    # 主题回顾
    author_intent = state_mgr.read_story_file("author_intent.md")
    theme_review = _generate_theme_review(author_intent, summary_text)

    report = CompletionReport(
        book_id=book_id,
        book_title=book_title,
        total_chapters=total_chapters,
        total_words=total_words,
        hooks_resolved=resolved,
        hooks_total=total_hooks,
        summary=summary_text,
        character_endings=character_endings,
        theme_review=theme_review,
    )

    # 保存完结报告
    _save_completion_report(state_mgr, report)

    return report


# ---- Internal ----

def _extract_characters(content: str) -> str:
    """从章节内容中提取出场人物."""
    names = re.findall(
        r"(?:[李王张刘陈杨赵黄周吴徐孙马胡朱郭何罗高林郑梁谢宋唐许邓冯韩曹彭曾萧田董潘袁于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤温康施文牛]"
        r"[^\s，。！？、：；""''（）【】《》\-\d]{1,2})",
        content,
    )
    unique = list(dict.fromkeys(names))[:8]
    return "、".join(unique)


def _summarize_events(content: str) -> str:
    """提取章节事件摘要."""
    clean = content.replace("\n", " ").strip()
    return clean[:150] + ("..." if len(clean) > 150 else "")


def _detect_mood(content: str) -> str:
    """检测章节情绪."""
    moods = {
        "紧张": ["紧张", "恐惧", "危险", "死亡", "威胁"],
        "愤怒": ["愤怒", "怒火", "咬牙", "握紧拳头", "杀意"],
        "悲伤": ["悲伤", "眼泪", "哭泣", "难过"],
        "爽快": ["冷笑", "不屑", "打脸", "碾压", "震惊"],
        "悬疑": ["奇怪", "诡异", "不对", "异常"],
        "温情": ["温暖", "微笑", "感动", "温柔"],
        "绝望": ["绝望", "崩溃", "无力", "完了"],
        "平静": ["平静", "日常", "休息", "整理"],
    }
    scores = {}
    for mood, keywords in moods.items():
        scores[mood] = sum(content.count(kw) for kw in keywords)
    if not scores or max(scores.values()) == 0:
        return "中性"
    return max(scores, key=scores.get)


def _detect_chapter_type(content: str, genre: GenreProfile) -> str:
    """检测章节类型."""
    if not genre.chapter_types:
        return "事件章"
    if any(kw in content for kw in ["高潮", "爆发", "决战", "真相", "揭晓"]):
        for ct in genre.chapter_types:
            if "高潮" in ct or "揭示" in ct:
                return ct
    if any(kw in content for kw in ["日常", "休息", "整理"]):
        for ct in genre.chapter_types:
            if "过渡" in ct or "日常" in ct:
                return ct
    return genre.chapter_types[-2] if len(genre.chapter_types) >= 2 else genre.chapter_types[0]


def _extract_facts_from_chapter(chapter: Chapter) -> list[Fact]:
    """从章节中提取结构化事实."""
    facts = []
    cn = chapter.chapter_number
    loc_match = re.search(r"(?:来到|抵达|进入|身处)([^\s，。]{2,8})", chapter.content)
    if loc_match:
        facts.append(Fact(
            subject="主角",
            predicate="当前位置",
            object=loc_match.group(1),
            valid_from_chapter=cn,
            source_chapter=cn,
        ))
    return facts


def _extract_conflict(content: str) -> str:
    """提取当前冲突."""
    if "战斗" in content or "攻击" in content:
        return "战斗冲突"
    if "追杀" in content or "逃跑" in content:
        return "逃亡冲突"
    if "谜团" in content or "线索" in content:
        return "解谜冲突"
    return "日常推进"


def _extract_protagonist_state(content: str) -> str:
    """提取主角状态."""
    if "受伤" in content or "虚弱" in content:
        return "受伤"
    if "突破" in content:
        return "实力提升"
    return "正常"


def _update_hooks_from_memo(pool: HookPool, memo: ChapterMemo, chapter_number: int) -> None:
    """根据 Chapter Memo 更新伏笔状态."""
    pay_off_text = memo.pay_off
    if not pay_off_text:
        return

    for hook in pool.hooks:
        if hook.hook_id in pay_off_text:
            hook.last_advanced_chapter = chapter_number
            hook.advanced_count += 1

    # 如果 memo 指定了要回收的伏笔，标记为 resolved
    for hook_id in memo.hooks_to_resolve:
        for hook in pool.hooks:
            if hook.hook_id == hook_id:
                hook.status = HookStatus.RESOLVED
                hook.last_advanced_chapter = chapter_number
                hook.advanced_count += 1
                break


def _update_completion_progress(
    pool: HookPool,
    plan: CompletionPlan,
    chapter_number: int,
) -> None:
    """更新完结计划中的伏笔回收进度."""
    for entry in plan.hook_schedule:
        if entry.status == "pending":
            for hook in pool.hooks:
                if hook.hook_id == entry.hook_id:
                    if hook.status.value in ("resolved", "deferred"):
                        entry.status = "resolved"
                        entry.resolved_in_chapter = chapter_number
                    break


def _save_completion_plan(state_mgr: StateManager, plan: CompletionPlan) -> None:
    """保存完结计划到 reports/ 目录."""
    lines = [
        f"# 完结计划",
        "",
        f"- 完结窗口: 第{plan.completion_window_start}-{plan.completion_window_end}章",
        f"- 剩余章节: {plan.remaining_chapters} 章",
        f"- 未回收伏笔: {plan.total_unresolved_hooks} 个",
        "",
        plan.arc_phases,
        "",
        "## 伏笔回收排期",
        "",
        "| 伏笔 | 类型 | 目标章 | 状态 | 实际回收章 |",
        "|------|------|--------|------|-----------|",
    ]
    for entry in plan.hook_schedule:
        resolved_ch = str(entry.resolved_in_chapter) if entry.resolved_in_chapter else "-"
        status_icon = {"pending": "⏳", "resolved": "✅", "deferred": "⏸️"}.get(entry.status, "⏳")
        lines.append(
            f"| {entry.hook_id} | {entry.hook_type} | {entry.target_chapter} | "
            f"{status_icon} {entry.status} | {resolved_ch} |"
        )

    state_mgr.write_story_file("completion_plan.md", "\n".join(lines))


def _save_completion_report(state_mgr: StateManager, report: CompletionReport) -> None:
    """保存完结报告到 reports/."""
    lines = [
        f"# 完结报告 — {report.book_title}",
        "",
        f"- 总章节: {report.total_chapters} 章",
        f"- 总字数: {report.total_words} 字",
        f"- 伏笔回收: {report.hooks_resolved}/{report.hooks_total}",
        f"- 完结时间: {report.completed_at}",
        "",
        "## 全书摘要",
        "",
        report.summary,
        "",
        "## 角色归宿",
        "",
    ]
    for ce in report.character_endings:
        lines.append(f"### {ce.name}（{ce.role}）")
        lines.append(f"{ce.ending}")
        if ce.arc_summary:
            lines.append(f"*弧线: {ce.arc_summary}*")
        lines.append("")

    lines.extend([
        "## 主题回顾",
        "",
        report.theme_review,
    ])

    state_mgr.write_story_file("completion_report.md", "\n".join(lines))


def _generate_book_summary(summaries: list[ChapterSummary], book_title: str) -> str:
    """从章节摘要生成全书摘要."""
    if not summaries:
        return f"《{book_title}》全书完结。"

    total = len(summaries)
    # 取首、中、尾各 3 章摘要
    samples = []
    if total <= 9:
        samples = summaries
    else:
        samples = summaries[:3] + summaries[total // 2 - 1:total // 2 + 2] + summaries[-3:]

    lines = [f"《{book_title}》共 {total} 章。"]
    lines.append("")
    lines.append("### 开篇")
    for s in samples[:3]:
        lines.append(f"- 第{s.chapter}章《{s.title}》：{s.events[:60]}（{s.mood}）")

    if total > 6:
        lines.append("")
        lines.append("### 中段")
        mid_start = 3 if total <= 9 else 3
        mid_end = 6 if total <= 9 else 6
        for s in samples[mid_start:mid_end]:
            lines.append(f"- 第{s.chapter}章《{s.title}》：{s.events[:60]}（{s.mood}）")

    lines.append("")
    lines.append("### 结局")
    for s in samples[-3:]:
        lines.append(f"- 第{s.chapter}章《{s.title}》：{s.events[:60]}（{s.mood}）")

    return "\n".join(lines)


def _extract_character_endings(story_frame: str, volume_map: str) -> list[CharacterEnding]:
    """从 Foundation 和卷纲中提取角色信息生成归宿."""
    endings = []

    # 从 story_frame 中提取角色名
    name_pattern = re.findall(r"(?:主角|反派|配角|盟友)[：:]\s*([^\n]+)", story_frame)
    character_pattern = re.findall(r"\*\*([^*]+)\*\*[：:]\s*([^\n]+)", story_frame)

    # 从 volume_map 中提取角色命运
    fate_pattern = re.findall(r"(?:退场|转变|黑化|牺牲|归宿)[：:]\s*([^\n]+)", volume_map)

    for name, desc in character_pattern[:8]:
        endings.append(CharacterEnding(
            name=name.strip(),
            role="",
            ending=desc.strip()[:200],
            arc_summary="",
        ))

    if not endings:
        endings.append(CharacterEnding(
            name="主角",
            role="protagonist",
            ending="完成使命，开启新的旅程。",
            arc_summary="从平凡到非凡的完整蜕变。",
        ))

    return endings


def _discover_hooks_from_chapter(
    client: LLMClient,
    genre: GenreProfile,
    chapter: Chapter,
    hook_pool: HookPool,
    state_mgr: StateManager,
) -> list[Hook]:
    """从章节内容中自动发现新播种的伏笔和章级钩子.

    每 5 章执行一次完整 LLM 扫描，减少调用。
    其他章用简单规则扫描。
    """
    # 每 5 章或首章执行 LLM 扫描
    if chapter.chapter_number % 5 != 1 and chapter.chapter_number != 1:
        return _quick_hook_scan(chapter, hook_pool)

    # 获取已有伏笔摘要
    existing_summary = ""
    for h in hook_pool.hooks[-20:]:
        existing_summary += f"- {h.hook_id}（{h.type}）: {h.notes[:60]}\n"

    system_prompt = f"""你是{genre.name}题材的伏笔分析师。请从章节内容中发现新播种的伏笔。

## 发现规则
- 只发现本章新播种的伏笔，不要重复已有伏笔
- 伏笔类型：角色关系/能力升级/冲突升级/世界观揭示/阴谋线索
- 章级钩子（1-5章内回收的小悬念）也算伏笔
- 每个伏笔标注播种章和预计回收章
- 不要虚构不存在的伏笔

## 输出格式（严格 JSON）
{{
  "discovered_hooks": [
    {{
      "type": "角色关系/能力升级/冲突升级/世界观揭示/阴谋线索",
      "payoff_chapter": {chapter.chapter_number + 3},
      "payoff_timing": "immediate/near_term/mid_arc",
      "notes": "伏笔说明（30字以内）",
      "seed_text": "章节中播种该伏笔的关键文本片段（20字以内）"
    }}
  ]
}}

如果没有发现新伏笔，返回 {{"discovered_hooks": []}}"""

    # 取章节前 1500 字和后 500 字
    content_sample = chapter.content[:1500]
    if len(chapter.content) > 2000:
        content_sample += "\n...\n" + chapter.content[-500:]

    user_prompt = f"""## 第{chapter.chapter_number}章《{chapter.title}》
{content_sample}

## 已有伏笔（避免重复）
{existing_summary if existing_summary else '暂无'}

请发现本章新播种的伏笔。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        result = client.chat_json(messages, temperature=0.4)
        parsed = result.get("parsed", {})
    except Exception:
        return []

    timing_map = {
        "immediate": HookPayoffTiming.IMMEDIATE,
        "near_term": HookPayoffTiming.NEAR_TERM,
        "mid_arc": HookPayoffTiming.MID_ARC,
        "slow_burn": HookPayoffTiming.SLOW_BURN,
        "endgame": HookPayoffTiming.ENDGAME,
    }

    hooks = []
    for i, h in enumerate(parsed.get("discovered_hooks", [])):
        payoff_ch = h.get("payoff_chapter", chapter.chapter_number + 3)
        payoff_timing = timing_map.get(h.get("payoff_timing", "near_term"), HookPayoffTiming.NEAR_TERM)

        hook_id = f"ch{chapter.chapter_number:04d}_{i+1:02d}"
        hooks.append(Hook(
            hook_id=hook_id,
            book_id=chapter.book_id,
            start_chapter=chapter.chapter_number,
            type=h.get("type", ""),
            status=HookStatus.PLANTED,
            expected_payoff=f"第{payoff_ch}章回收",
            payoff_timing=payoff_timing,
            notes=h.get("notes", ""),
            seed_text=h.get("seed_text", ""),
            depends_on=[],
            core_hook=False,
            promoted=True,
            hook_level=HookLevel.CHAPTER,
            volume_number=None,
        ))

    return hooks


def _quick_hook_scan(chapter: Chapter, hook_pool: HookPool) -> list[Hook]:
    """快速规则扫描：从章节中检测明显的章级钩子（不调用 LLM）."""
    content = chapter.content
    hooks = []

    # 检测章末悬念钩子
    suspense_patterns = [
        (r'(?:突然|忽然|就在这时|正在此时)(.{10,40}?)(?:[。！])', "突发事件"),
        (r'(?:他不知道|她不知道|没人知道|谁也不.{0,3}知道)(.{10,40}?)(?:[。！])', "未知信息"),
        (r'(?:暗中|暗处|阴影中|黑暗里)(.{10,40}?)(?:[。！])', "暗中观察"),
        (r'(?:冷笑|阴笑|诡笑|意味深长).{0,10}(?:说|道)(.{10,30}?)(?:[。！])', "反派暗示"),
        (r'(?:留下|刻下|写着|写着).{0,5}(?:一句话|一行字|几个字)(.{10,40}?)(?:[。！])', "神秘信息"),
        (r'(?:预感|直觉|本能).{0,5}(?:告诉|提醒)(.{10,40}?)(?:[。！])', "预感伏笔"),
    ]

    # 只看章末 500 字
    tail = content[-500:] if len(content) > 500 else content

    existing_ids = {h.hook_id for h in hook_pool.hooks}
    count = 0

    for pattern, hook_type in suspense_patterns:
        matches = re.findall(pattern, tail)
        for match in matches[:1]:
            hook_id = f"ch{chapter.chapter_number:04d}_q{count+1:02d}"
            if hook_id in existing_ids:
                continue
            hooks.append(Hook(
                hook_id=hook_id,
                book_id=chapter.book_id,
                start_chapter=chapter.chapter_number,
                type=hook_type,
                status=HookStatus.PLANTED,
                expected_payoff=f"第{chapter.chapter_number + 3}章回收",
                payoff_timing=HookPayoffTiming.NEAR_TERM,
                notes=match[:50],
                seed_text=match[:30],
                depends_on=[],
                core_hook=False,
                promoted=True,
                hook_level=HookLevel.CHAPTER,
                volume_number=None,
            ))
            count += 1
            if count >= 3:
                break
        if count >= 3:
            break

    return hooks


def _generate_theme_review(author_intent: str, summary: str) -> str:
    """生成主题回顾."""
    if not author_intent or author_intent == "# 作者意图\n\n待填写\n":
        return "本书围绕核心主题展开，完成了完整的叙事弧线。"

    # 提取关键主题词
    themes = re.findall(r"(?:核心|主题|方向)[：:]\s*([^\n]+)", author_intent)
    if themes:
        return f"本书以「{themes[0]}」为核心主题，通过主角的完整旅程，对这一主题进行了多层次的探索与呈现。"
    return "本书完成了从开篇到结局的完整叙事弧线，主题贯穿始终。"
