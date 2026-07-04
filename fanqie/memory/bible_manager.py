"""BibleManager — 故事圣经管理：分文件 + 智能索引，防止 LLM 幻觉."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fanqie.llm.client import LLMClient
from fanqie.models import (
    Chapter, ChapterMemo, ChapterSummary, CurrentState, HookPool, Hook,
)
from fanqie.genres.loader import GenreProfile


class BibleManager:
    """管理 story/bible/ 目录下的故事圣经文件.

    分层结构:
      index.md      — 极简锚点（每章更新，不调 LLM）
      timeline.md   — 最近 20 章事件线（每章追加，不调 LLM）
      characters.md — 角色状态（每 5 章 LLM 增量更新）
      factions.md   — 势力动态（每 10 章 LLM 增量更新）
      items.md      — 物品/能力（每 5 章 LLM 增量更新）
    """

    def __init__(self, story_dir: str):
        self.bible_dir = Path(story_dir) / "runtime"
        self.bible_dir.mkdir(parents=True, exist_ok=True)

    # ---- Public API ----

    def ensure_bible_files(self) -> None:
        """确保所有圣经文件存在."""
        defaults = {
            "index.md": "# 故事索引\n\n待初始化\n",
            "timeline.md": "# 事件时间线\n\n待初始化\n",
            "items.md": "# 物品与能力\n\n待初始化\n",
        }
        for name, content in defaults.items():
            path = self.bible_dir / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    def read(self, filename: str) -> str:
        """读取圣经文件."""
        path = self.bible_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    # ---- Index (每章更新，不调 LLM) ----

    def update_index(
        self,
        chapter: Chapter,
        memo: ChapterMemo,
        current_state: CurrentState,
        hook_pool: HookPool,
        chapter_count: int,
        target_chapters: int,
    ) -> None:
        """更新 index.md — 极简锚点，< 500 字."""
        # 统计伏笔
        total_hooks = len(hook_pool.hooks)
        active_hooks = [h for h in hook_pool.hooks if h.status.value not in ("resolved", "deferred")]
        core_active = [h for h in active_hooks if h.hook_level and h.hook_level.value == "core"]
        vol_active = [h for h in active_hooks if h.hook_level and h.hook_level.value == "volume"]
        ch_active = [h for h in active_hooks if h.hook_level and h.hook_level.value == "chapter"]

        # 读取主角信息（从 foundation/protagonist.md）
        foundation_dir = self.bible_dir.parent / "foundation"
        protagonist_text = ""
        protagonist_path = foundation_dir / "protagonist.md"
        if protagonist_path.exists():
            protagonist_text = protagonist_path.read_text(encoding="utf-8")[:500]

        # 完结标记
        completion_tag = ""
        if memo.is_final:
            completion_tag = "\n⚠️ **最终章** — 全书收尾"
        elif memo.is_completion_arc:
            remaining = target_chapters - chapter_count
            completion_tag = f"\n⚠️ **完结窗口** — 剩余 {remaining} 章"

        lines = f"""# 故事索引 — 第{chapter.chapter_number}章

## 主角
- 状态: {current_state.protagonist_state}
- 位置: {current_state.current_location or '未知'}
- 当前冲突: {current_state.current_conflict}
- 当前目标: {memo.goal[:80] if memo.goal else '延续剧情'}

## 伏笔概览
- 总计: {total_hooks} 个（核心 {len(core_active)} / 卷级 {len(vol_active)} / 章级 {len(ch_active)}）
- 活跃: {len(active_hooks)} 个
- 已回收: {total_hooks - len(active_hooks)} 个

## 角色与势力
见 foundation/characters/ 和 foundation/world.md
{completion_tag}
"""
        (self.bible_dir / "index.md").write_text(lines, encoding="utf-8")

    # ---- Timeline (每章追加，不调 LLM) ----

    def update_timeline(self, chapter: Chapter, summary: ChapterSummary) -> None:
        """追加一行到 timeline.md."""
        path = self.bible_dir / "timeline.md"
        existing = path.read_text(encoding="utf-8") if path.exists() else "# 事件时间线\n\n"

        # 只保留最近 30 行
        lines = existing.strip().split("\n")
        header_lines = []
        event_lines = []
        in_header = True
        for line in lines:
            if in_header and (line.startswith("#") or line.startswith("|") or line.strip() == ""):
                header_lines.append(line)
            else:
                in_header = False
                if line.strip():
                    event_lines.append(line)

        # 追加新行
        event_lines.append(
            f"| {chapter.chapter_number} | {chapter.title} | "
            f"{summary.events[:60]} | {summary.mood} | {summary.chapter_type} |"
        )

        # 只保留最近 25 条
        if len(event_lines) > 25:
            event_lines = event_lines[-25:]

        # 确保有表头
        if not any("章节" in h for h in header_lines):
            header_lines = [
                "# 事件时间线",
                "",
                "| 章节 | 标题 | 事件 | 情绪 | 类型 |",
                "|------|------|------|------|------|",
            ]

        path.write_text(
            "\n".join(header_lines + [""] + event_lines),
            encoding="utf-8",
        )

    # ---- Items (每 5 章 LLM 增量更新) ----

    def should_update_items(self, chapter_number: int) -> bool:
        return chapter_number % 5 == 0 or chapter_number == 1

    def update_items(
        self,
        client: LLMClient,
        genre: GenreProfile,
        chapter: Chapter,
        recent_summaries: list[ChapterSummary],
    ) -> None:
        """LLM 增量更新物品与能力."""
        existing = self.read("items.md")
        if not existing or existing == "# 物品与能力\n\n待初始化\n":
            existing = "# 物品与能力\n\n待填充\n"

        summaries_text = "\n".join(
            f"- 第{s.chapter}章: {s.events[:80]}"
            for s in recent_summaries[-10:]
        )

        system_prompt = f"""你是{genre.name}题材的故事编辑。请增量更新物品与能力文件。

## 更新规则
- 记录主角获得的重要物品和已解锁的能力
- 标注获得章节和当前状态
- 已消耗/已失去的物品标注状态，不要删除
- 格式保持一致

## 条目格式
### 物品/能力名
- 类型: 物品/能力/知识
- 获得: 第X章
- 状态: 持有/已消耗/已失去/已升级
- 说明: 一句话功能"""

        user_prompt = f"""## 当前物品文件
{existing[:2000]}

## 最近章节摘要
{summaries_text}

## 本章
第{chapter.chapter_number}章《{chapter.title}》

请更新物品与能力文件，返回完整的更新后内容。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = client.chat(messages, temperature=0.3, max_tokens=2000)
            (self.bible_dir / "items.md").write_text(
                result["content"], encoding="utf-8"
            )
        except Exception:
            pass



