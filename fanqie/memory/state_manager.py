"""状态管理器 — JSON 结构化状态读写."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fanqie.models import CurrentState, HookPool, ChapterSummary, Fact, Hook


class StateManager:
    """管理书籍的 JSON 状态和 Markdown 副本."""

    def __init__(self, book_dir: str):
        self.book_dir = Path(book_dir)
        self.story_dir = self.book_dir / "story"
        self.state_dir = self.book_dir / "story" / "state"
        self.foundation_dir = self.story_dir / "foundation"
        self.runtime_dir = self.story_dir / "runtime"
        self.reports_dir = self.story_dir / "reports"
        self.story_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.foundation_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # 文件路由：文件名 → 目标子目录
        self._file_routing: dict[str, Path] = {
            # Foundation
            "story_frame.md": self.foundation_dir,
            "author_intent.md": self.foundation_dir,
            "book_rules.md": self.foundation_dir,
            "volume_map.md": self.foundation_dir,
            "world.md": self.foundation_dir,
            "protagonist.md": self.foundation_dir,
            "cascade_rules.md": self.foundation_dir,
            "civilization_norms.md": self.foundation_dir,
            # Runtime
            "current_focus.md": self.runtime_dir,
            "current_state.md": self.runtime_dir,
            "pending_hooks.md": self.runtime_dir,
            "chapter_summaries.md": self.runtime_dir,
            "index.md": self.runtime_dir,
            "timeline.md": self.runtime_dir,
            "hooks.md": self.runtime_dir,
            "items.md": self.runtime_dir,
            # Reports
            "completion_plan.md": self.reports_dir,
            "completion_report.md": self.reports_dir,
            "modification_log.md": self.reports_dir,
            "brief_report.md": self.reports_dir,
        }

    # ---- Current State ----

    def load_current_state(self) -> CurrentState:
        path = self.state_dir / "current_state.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return CurrentState(**data)
        return CurrentState(
            book_id=self.book_dir.name,
            chapter_number=0,
        )

    def save_current_state(self, state: CurrentState) -> None:
        path = self.state_dir / "current_state.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(), f, ensure_ascii=False, indent=2)
        self._write_state_markdown(state)

    def _write_state_markdown(self, state: CurrentState) -> None:
        lines = [
            f"# 当前状态 — 第{state.chapter_number}章",
            "",
            f"**当前冲突**: {state.current_conflict}",
            f"**当前目标**: {state.current_goal}",
            f"**主角状态**: {state.protagonist_state}",
            f"**当前位置**: {state.current_location}",
            f"**当前限制**: {state.current_constraint}",
            f"**当前同盟**: {state.current_alliances}",
            "",
            "## 事实库",
            "",
        ]
        for fact in state.facts:
            valid = f" (有效期至{fact.valid_until_chapter}章)" if fact.valid_until_chapter else ""
            lines.append(f"- {fact.subject} {fact.predicate} {fact.object}{valid}")

        path = self.runtime_dir / "current_state.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ---- Hook Pool ----

    def load_hook_pool(self) -> HookPool:
        path = self.state_dir / "hooks.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return HookPool(**data)
        return HookPool(book_id=self.book_dir.name)

    def save_hook_pool(self, pool: HookPool) -> None:
        path = self.state_dir / "hooks.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pool.model_dump(), f, ensure_ascii=False, indent=2)
        self._write_hooks_markdown(pool)

    def _write_hooks_markdown(self, pool: HookPool) -> None:
        lines = ["# 伏笔池", ""]
        for h in pool.hooks:
            core = " [核心]" if h.core_hook else ""
            lines.append(f"## {h.hook_id}{core}")
            lines.append(f"- 类型: {h.type}")
            lines.append(f"- 状态: {h.status.value}")
            lines.append(f"- 起始章: {h.start_chapter}")
            lines.append(f"- 最后推进: {h.last_advanced_chapter}")
            lines.append(f"- 预期回收: {h.expected_payoff}")
            lines.append(f"- 回收节奏: {h.payoff_timing.value}")
            if h.seed_text:
                lines.append(f"- 种子文本: {h.seed_text[:120]}")
            lines.append("")

        path = self.runtime_dir / "hooks.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ---- Chapter Summaries ----

    def load_summaries(self) -> list[ChapterSummary]:
        path = self.state_dir / "chapter_summaries.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [ChapterSummary(**row) for row in data.get("rows", [])]
        return []

    def save_summaries(self, summaries: list[ChapterSummary]) -> None:
        path = self.state_dir / "chapter_summaries.json"
        rows = [s.model_dump() for s in summaries]
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rows": rows}, f, ensure_ascii=False, indent=2)
        self._write_summaries_markdown(summaries)

    def _write_summaries_markdown(self, summaries: list[ChapterSummary]) -> None:
        lines = [
            "| 章节 | 标题 | 出场人物 | 事件 | 状态变化 | 伏笔活动 | 情绪 | 章节类型 |",
            "|------|------|----------|----------|----------|----------|----------|----------|",
        ]
        for s in summaries:
            lines.append(
                f"| {s.chapter} | {s.title} | {s.characters} | {s.events} | "
                f"{s.state_changes} | {s.hook_activity} | {s.mood} | {s.chapter_type} |"
            )

        path = self.runtime_dir / "chapter_summaries.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # ---- Story Files ----

    def ensure_story_files(self) -> None:
        """确保 story 目录下关键文件存在."""
        files = {
            "story_frame.md": ("foundation", "# 世界观设定\n\n待填写\n"),
            "author_intent.md": ("foundation", "# 作者意图\n\n待填写\n"),
            "current_focus.md": ("runtime", "# 当前关注点\n\n待填写\n"),
            "book_rules.md": ("foundation", "# 本书专属规则\n\n待填写\n"),
            "volume_map.md": ("foundation", "# 卷纲\n\n待填写\n"),
        }
        for name, (subdir, default_content) in files.items():
            target = getattr(self, f"{subdir}_dir")
            path = target / name
            if not path.exists():
                with open(path, "w", encoding="utf-8") as f:
                    f.write(default_content)

    def read_story_file(self, name: str) -> str:
        # 先尝试新位置（foundation/runtime/reports）
        target_dir = self._file_routing.get(name)
        if target_dir is not None:
            path = target_dir / name
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
        # 回退到旧扁平结构（兼容已有书籍）
        path = self.story_dir / name
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def write_story_file(self, name: str, content: str) -> None:
        target_dir = self._file_routing.get(name, self.story_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / name
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
