"""上下文组装 — Protected/Compressible 分层 + 相关性评分 + 故事圣经."""

from __future__ import annotations

import re
from typing import Optional

from fanqie.models import ContextEntry, ContextPackage, ChapterMemo
from .state_manager import StateManager
from .hook_lifecycle import filter_active_hooks, compute_recyclable_hooks
from .bible_manager import BibleManager


PROTECTED_SOURCES = {
    "story_frame.md",
    "current_state.md",
    "book_rules.md",
    "author_intent.md",
    "current_focus.md",
}

_STOP_WORDS = {
    "本章", "继续", "重新", "拉回", "回到", "推进", "优先", "围绕",
    "聚焦", "坚持", "保持", "注意力", "处理", "回拉", "当前",
    "一个", "这个", "那个", "什么", "怎么", "可以", "应该",
}


def _extract_query_terms(text: str) -> list[str]:
    chinese = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
    terms = [t for t in chinese if t not in _STOP_WORDS]
    seen = set()
    result = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result[:12]


def _score_text(text: str, query_terms: list[str]) -> int:
    score = 0
    for term in query_terms:
        if term in text:
            score += max(8, len(term) * 2)
    return score


def assemble_context(
    state_mgr: StateManager,
    memo: ChapterMemo,
    chapter_number: int,
    target_chapters: int | None = None,
    max_summaries: int = 4,
    max_hooks: int = 6,
    bible: BibleManager | None = None,
) -> ContextPackage:
    entries: list[ContextEntry] = []

    # ---- 0. 故事圣经索引（最高优先级，必读） ----
    if bible:
        bible_index = bible.read("index.md")
        if bible_index.strip() and bible_index != "# 故事索引\n\n待初始化\n":
            entries.append(ContextEntry(
                source="runtime/index.md",
                reason="故事圣经索引（当前状态锚点）",
                excerpt=bible_index[:800],
                is_protected=True,
            ))

    # ---- 1. Protected 文件 ----
    protected_files = [
        ("story_frame.md", "世界观设定"),
        ("current_state.md", "当前状态快照"),
        ("book_rules.md", "本书专属规则"),
        ("author_intent.md", "长期方向"),
        ("current_focus.md", "近期关注点"),
    ]
    for filename, reason in protected_files:
        content = state_mgr.read_story_file(filename)
        if content.strip():
            entries.append(ContextEntry(
                source=f"{_file_source_prefix(filename)}",
                reason=reason,
                excerpt=content[:2000],
                is_protected=True,
            ))

    # ---- 2. 查询词提取 ----
    query_terms = _extract_query_terms(
        f"{memo.goal} {memo.pay_off} {memo.reader_waiting_for}"
    )

    # ---- 3. 按需拉取圣经文件 ----
    if bible:
        # 物品/能力相关 → items.md
        item_keywords = ["物品", "能力", "装备", "法宝", "丹药", "解锁", "获得", "突破", "升级", "禁忌", "书页", "纹路"]
        if any(kw in f"{memo.goal} {memo.pay_off}" for kw in item_keywords):
            items = bible.read("items.md")
            if items.strip() and items != "# 物品与能力\n\n待初始化\n":
                entries.append(ContextEntry(
                    source="runtime/items.md",
                    reason="物品与能力（按需）",
                    excerpt=items[:1000],
                    is_protected=False,
                ))

        # 时间线 → timeline.md（总是取最近 5 条）
        timeline = bible.read("timeline.md")
        if timeline.strip() and timeline != "# 事件时间线\n\n待初始化\n":
            recent_timeline = _extract_recent_timeline(timeline, 5)
            if recent_timeline:
                entries.append(ContextEntry(
                    source="runtime/timeline.md",
                    reason="最近事件线",
                    excerpt=recent_timeline[:600],
                    is_protected=False,
                ))

    # ---- 4. 章节摘要（脱敏：去掉章节号等元信息，用角色视角描述） ----
    summaries = state_mgr.load_summaries()
    if summaries:
        scored = []
        for s in summaries:
            if s.chapter >= chapter_number:
                continue
            text = f"{s.title} {s.characters} {s.events} {s.state_changes} {s.hook_activity}"
            score = _score_text(text, query_terms)
            if s.chapter >= chapter_number - 3 or score > 0:
                scored.append((s, score + max(0, 12 - (chapter_number - s.chapter))))

        scored.sort(key=lambda x: -x[1])
        for s, _ in scored[:max_summaries]:
            # 脱敏：去掉"第X章"，只保留事件内容
            clean_title = _strip_chapter_prefix(s.title)
            entries.append(ContextEntry(
                source="前情提要",
                reason="前情提要",
                excerpt=f"{clean_title}: {s.events}",
                is_protected=False,
            ))

    # ---- 5. 伏笔（脱敏：去掉 hook_id 等内部标识） ----
    hook_pool = state_mgr.load_hook_pool()
    active = filter_active_hooks([h.model_dump() for h in hook_pool.hooks])
    if active:
        scored = []
        for h in active:
            text = f"{h.get('hook_id','')} {h.get('type','')} {h.get('expected_payoff','')} {h.get('notes','')}"
            score = _score_text(text, query_terms)
            scored.append((h, score))

        scored.sort(key=lambda x: -x[1])
        for h, _ in scored[:max_hooks]:
            entries.append(ContextEntry(
                source="待回收伏笔",
                reason=f"伏笔: {h.get('type','')}",
                excerpt=h.get("notes", "") or h.get("expected_payoff", ""),
                is_protected=False,
            ))

    # ---- 6. 卷纲 ----
    volume_map = state_mgr.read_story_file("volume_map.md")
    if volume_map.strip():
        entries.append(ContextEntry(
            source="foundation/volume_map.md",
            reason="卷纲",
            excerpt=volume_map[:1500],
            is_protected=False,
        ))

    def _est_tokens(text: str) -> int:
        return int(len(text) * 1.5)

    protected_tokens = sum(_est_tokens(e.excerpt) for e in entries if e.is_protected)
    compressible_tokens = sum(_est_tokens(e.excerpt) for e in entries if not e.is_protected)

    return ContextPackage(
        book_id=memo.book_id,
        chapter_number=chapter_number,
        selected_context=entries,
        protected_tokens=protected_tokens,
        compressible_tokens=compressible_tokens,
        total_tokens=protected_tokens + compressible_tokens,
    )


def _extract_recent_timeline(timeline_text: str, count: int) -> str:
    """从 timeline.md 提取最近 N 条事件，脱敏为角色视角."""
    lines = timeline_text.strip().split("\n")
    event_lines = [l for l in lines if l.startswith("|") and not l.startswith("|--") and not l.startswith("| 章节")]
    recent = event_lines[-count:] if len(event_lines) > count else event_lines
    # 脱敏：去掉表格格式，转为纯文本事件描述
    result = []
    for line in recent:
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 3:
            # parts: [章节号, 标题, 事件, 情绪, 类型]
            title = _strip_chapter_prefix(parts[1]) if len(parts) > 1 else ""
            event = parts[2] if len(parts) > 2 else ""
            result.append(f"- {title}: {event}")
    return "\n".join(result)


def _strip_chapter_prefix(title: str) -> str:
    """去掉标题中的'第X章 '前缀."""
    return re.sub(r'^第\d+章\s*', '', title)


def _file_source_prefix(filename: str) -> str:
    """根据文件名返回对应的 source 前缀."""
    foundation_files = {"story_frame.md", "author_intent.md", "book_rules.md", "volume_map.md", "world.md", "protagonist.md"}
    runtime_files = {"current_focus.md", "current_state.md", "pending_hooks.md", "chapter_summaries.md", "index.md", "timeline.md", "hooks.md", "items.md"}
    reports_files = {"completion_plan.md", "completion_report.md", "modification_log.md", "brief_report.md"}
    if filename in foundation_files:
        return f"foundation/{filename}"
    if filename in runtime_files:
        return f"runtime/{filename}"
    if filename in reports_files:
        return f"reports/{filename}"
    return f"story/{filename}"
