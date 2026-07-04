"""Orchestrator — 写作主循环，含完结窗口管理."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fanqie.llm.client import LLMClient
from fanqie.models import (
    BookConfig, BookStatus, Chapter, ChapterMemo, ChapterStatus, AuditResult,
    Foundation, VolumePlan, BriefReport, ImpactReport,
    CompletionPlan, CompletionReport,
)
from fanqie.genres.loader import GenreProfile, load_genre
from fanqie.style.profile import StyleProfile
from fanqie.memory.state_manager import StateManager
from fanqie.memory.bible_manager import BibleManager
from fanqie.storage.repository import Repository
from fanqie.utils.config import get_writing_config

from .planner import (
    plan_chapter,
    build_completion_plan,
    validate_completion_feasibility,
    compute_completion_window,
    is_in_completion_window,
    is_final_chapter,
)
from .composer import compose_context
from .writer import write_chapter
from .settler import settle_chapter, finalize_book, resettle_chapter
from .auditor import audit_and_revise
from .reviser import rewrite_chapter as _rewrite_chapter_impl
from .intervener import Intervention, render_intervention_prompt
from .architect import (
    generate_foundation, present_foundation_summary,
    save_foundation_to_files,
)
from .volume_planner import (
    plan_volumes, plan_hook_schedule, plan_pacing,
    save_volume_plan, save_hooks_to_pool,
    plan_volume_hooks,
)
from .brief_optimizer import run_brief_pipeline, save_brief_report
from .advisor import analyze_impact, revise_memory, revise_chapters, log_modification


class Orchestrator:
    """写作编排器."""

    def __init__(
        self,
        book: BookConfig,
        genre: GenreProfile,
        data_dir: str = "data",
        style_profile: StyleProfile | None = None,
    ):
        self.book = book
        self.genre = genre
        self.data_dir = data_dir
        self.style_profile = style_profile
        self.book_dir = Path(data_dir) / book.id
        self.chapters_dir = self.book_dir / "chapters"
        self.chapters_dir.mkdir(parents=True, exist_ok=True)

        self.state_mgr = StateManager(str(self.book_dir))
        self.state_mgr.ensure_story_files()
        self.bible = BibleManager(str(self.book_dir / "story"))
        self.bible.ensure_bible_files()
        self.repo = Repository(data_dir, book.id)
        self.client = LLMClient()

        self._interventions: list[Intervention] = []
        self._writing_config = get_writing_config()
        self._foundation: Foundation | None = None
        self._volume_plan: VolumePlan | None = None
        self._completion_plan: CompletionPlan | None = None

    # ---- Public API ----

    # ---- Foundation + Volume Planning ----

    def build_foundation(self, brief: str = "") -> Foundation:
        """Step 1: 生成完整 Foundation."""
        self._foundation = generate_foundation(
            client=self.client,
            genre=self.genre,
            book_id=self.book.id,
            brief=brief,
        )
        story_dir = str(self.book_dir / "story")
        save_foundation_to_files(self._foundation, story_dir)
        return self._foundation

    def build_volume_plan(self) -> VolumePlan:
        """Step 2: 生成卷纲规划."""
        if self._foundation is None:
            raise RuntimeError("请先调用 build_foundation()")

        self._volume_plan = plan_volumes(
            client=self.client,
            genre=self.genre,
            foundation=self._foundation,
            target_chapters=self.book.target_chapters,
        )
        story_dir = str(self.book_dir / "story")
        save_volume_plan(self._volume_plan, story_dir)

        core_hooks_count = self._writing_config.get("core_hooks_count", 5)
        hooks = plan_hook_schedule(
            client=self.client,
            genre=self.genre,
            volumes=self._volume_plan,
            cascade_rules=self._foundation.cascade_rules,
            core_hooks_count=core_hooks_count,
        )
        save_hooks_to_pool(hooks, story_dir)

        pacing_notes = plan_pacing(self._volume_plan, self._foundation.civilization_norms)

        return self._volume_plan

    def initialize_book_state(self) -> None:
        """Step 4: 初始化书籍状态文件."""
        story_dir = str(self.book_dir / "story")
        os.makedirs(story_dir, exist_ok=True)

        if self._foundation:
            p = self._foundation.protagonist
            author_intent = f"""# 作者意图

## 核心方向
{p.motivation}

## 主角定位
{p.identity}

## 长期目标
{p.arc}
"""
            self.state_mgr.write_story_file("author_intent.md", author_intent)

        current_focus = """# 当前关注点

## 近期重点
- 建立世界观基础设定
- 展开主角初始处境
- 引入核心冲突线

## 当前卷目标
见 volume_map.md
"""
        self.state_mgr.write_story_file("current_focus.md", current_focus)

        book_rules = f"""# 本书专属规则

## 题材规则
{chr(10).join(f'- {k}: {v}' for k, v in self.genre.rules.items())}

## 禁忌
{chr(10).join(f'- {p}' for p in self.genre.prohibitions)}
"""
        self.state_mgr.write_story_file("book_rules.md", book_rules)

        self.book.status = BookStatus.READY
        self.repo.save_book(self.book.model_dump())

    def get_foundation_summary(self) -> str:
        """获取 Foundation 摘要文本."""
        if self._foundation is None:
            return "Foundation 尚未生成"
        return present_foundation_summary(self._foundation, self.genre.name)

    # ---- Brief ----

    def run_brief(self, raw_brief: str) -> BriefReport:
        """运行 Brief 优化流程."""
        report = run_brief_pipeline(
            client=self.client,
            raw_brief=raw_brief,
            genre=self.genre,
            book_id=self.book.id,
        )
        story_dir = str(self.book_dir / "story")
        save_brief_report(report, story_dir)
        return report

    # ---- Advise ----

    def advise(self, change_request: str) -> ImpactReport:
        """执行 Advise：波及分析 + 修改."""
        story_dir = str(self.book_dir / "story")
        cascade_rules = self._load_cascade_rules()

        impact = analyze_impact(
            client=self.client,
            genre=self.genre,
            change_request=change_request,
            cascade_rules=cascade_rules,
            story_dir=story_dir,
        )
        impact.book_id = self.book.id

        mem_mods = revise_memory(
            client=self.client,
            genre=self.genre,
            book_id=self.book.id,
            impact_report=impact,
            story_dir=story_dir,
        )

        ch_mods = revise_chapters(
            client=self.client,
            genre=self.genre,
            book_id=self.book.id,
            impact_report=impact,
            chapters_dir=str(self.chapters_dir),
        )

        log_modification(story_dir, change_request, impact)

        return impact

    # ---- Completion ----

    @property
    def is_complete(self) -> bool:
        """是否已完结."""
        return self.book.status == BookStatus.COMPLETED

    @property
    def is_in_completion_window(self) -> bool:
        """是否处于完结窗口."""
        ch_count = self.repo.get_chapter_count()
        return is_in_completion_window(ch_count + 1, self.book.target_chapters)

    def get_completion_plan(self) -> CompletionPlan | None:
        """获取完结计划（自动生成或从文件加载）."""
        if self._completion_plan:
            return self._completion_plan

        # 尝试从文件加载
        plan_path = self.book_dir / "story" / "reports" / "completion_plan.md"
        if plan_path.exists():
            # 从 state 加载
            state_plan_path = self.book_dir / "story" / "state" / "completion_plan.json"
            if state_plan_path.exists():
                with open(state_plan_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._completion_plan = CompletionPlan(**data)
                return self._completion_plan

        return None

    def generate_completion_plan(self) -> CompletionPlan:
        """生成完结计划."""
        ch_count = self.repo.get_chapter_count()
        next_chapter = ch_count + 1

        if not is_in_completion_window(next_chapter, self.book.target_chapters):
            window_start = compute_completion_window(self.book.target_chapters)
            raise RuntimeError(
                f"尚未进入完结窗口。完结窗口从第 {window_start} 章开始，"
                f"当前在第 {ch_count} 章。"
            )

        hook_pool = self.state_mgr.load_hook_pool()
        hooks_raw = [h.model_dump() for h in hook_pool.hooks]

        plan = build_completion_plan(
            hooks_raw=hooks_raw,
            chapter_number=next_chapter,
            target_chapters=self.book.target_chapters,
            book_id=self.book.id,
        )

        # 验证可行性
        unresolved = [
            h for h in hooks_raw
            if h.get("status", "") not in ("resolved", "closed", "done", "deferred", "paused", "hold")
        ]
        feasible, msg = validate_completion_feasibility(unresolved, plan.remaining_chapters)
        if not feasible:
            raise RuntimeError(msg)

        self._completion_plan = plan

        # 持久化
        state_dir = self.book_dir / "story" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        with open(state_dir / "completion_plan.json", "w", encoding="utf-8") as f:
            json.dump(plan.model_dump(), f, ensure_ascii=False, indent=2)

        return plan

    def finalize(self) -> CompletionReport:
        """手动完结：生成完结报告，标记书籍为已完成."""
        if self.is_complete:
            raise RuntimeError("本书已完结。")

        ch_count = self.repo.get_chapter_count()
        chapters = self.repo.get_all_chapters()
        total_words = sum(ch.get("word_count", 0) for ch in chapters)

        report = finalize_book(
            client=self.client,
            genre=self.genre,
            state_mgr=self.state_mgr,
            book_id=self.book.id,
            book_title=self.book.title,
            total_chapters=ch_count,
            total_words=total_words,
        )

        # 更新书籍状态
        self.book.status = BookStatus.COMPLETED
        self.book.updated_at = datetime.now().isoformat()
        self.repo.save_book(self.book.model_dump())

        return report

    # ---- Chapter Writing ----

    def write_next_chapter(self, user_instruction: str = "") -> Chapter:
        """写下一章: Plan → Compose → Write → Settle → Audit → Revise.

        支持完结窗口自动规划、最终章特殊处理、完结后自动 finalize.
        """
        # 检查是否已完结
        if self.is_complete:
            raise RuntimeError(
                f"《{self.book.title}》已完结，无法继续写作。"
            )

        chapter_number = self.repo.get_chapter_count() + 1

        # 检查是否超目标
        if chapter_number > self.book.target_chapters:
            raise RuntimeError(
                f"当前章号 {chapter_number} 已超过目标 {self.book.target_chapters} 章。\n"
                f"请使用 'fanqie complete {self.book.id}' 手动完结，"
                f"或使用 'fanqie advise {self.book.id} \"延长目标章数\"' 调整。"
            )

        # 处理用户干预
        intervention_text = ""
        if user_instruction:
            from .intervener import parse_intervention
            self._interventions.append(parse_intervention(user_instruction))
        if self._interventions:
            intervention_text = render_intervention_prompt(self._interventions)

        # 完结窗口：自动生成/加载完结计划
        if is_in_completion_window(chapter_number, self.book.target_chapters):
            if self._completion_plan is None:
                self._completion_plan = self.get_completion_plan()
            if self._completion_plan is None:
                self._completion_plan = self.generate_completion_plan()

        # 1. Plan
        memo = plan_chapter(
            client=self.client,
            genre=self.genre,
            state_mgr=self.state_mgr,
            book_id=self.book.id,
            chapter_number=chapter_number,
            target_chapters=self.book.target_chapters,
            user_intervention=intervention_text,
            completion_plan=self._completion_plan,
        )

        # 2. Compose
        context_pkg = compose_context(
            state_mgr=self.state_mgr,
            memo=memo,
            chapter_number=chapter_number,
            target_chapters=self.book.target_chapters,
            bible=self.bible,
        )

        # 3. Write
        # 获取上一章标题（防重复）
        prev_title = ""
        all_chapters = self.repo.get_all_chapters()
        if all_chapters:
            prev_ch = all_chapters[-1]
            prev_title = prev_ch.get("title", "")

        chapter = write_chapter(
            client=self.client,
            genre=self.genre,
            memo=memo,
            context_pkg=context_pkg,
            chapter_number=chapter_number,
            chapter_word_count=self.book.chapter_word_count,
            style_profile=self.style_profile,
            prev_title=prev_title,
        )

        # 保存草稿
        self._save_chapter_file(chapter)
        self.repo.save_chapter({
            "book_id": self.book.id,
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
            "content": chapter.content,
            "word_count": chapter.word_count,
            "status": "draft",
            "audit_score": None,
            "audit_issues": [],
            "created_at": chapter.created_at,
            "updated_at": chapter.updated_at,
        })

        # 4. Settle
        settle_chapter(
            client=self.client,
            genre=self.genre,
            state_mgr=self.state_mgr,
            chapter=chapter,
            memo=memo,
            completion_plan=self._completion_plan,
        )

        # 4.4 更新故事圣经
        self._update_bible(chapter, memo)

        # 4.5 更新 current_focus.md
        self._update_current_focus(chapter, memo)

        # 4.6 进入新卷时自动播种卷级伏笔
        self._seed_volume_hooks_if_new_volume(chapter.chapter_number)

        # 5. Audit + Revise 循环
        retries = self._writing_config.get("review_retries", 3)
        chapter, audit_history = audit_and_revise(
            client=self.client,
            genre=self.genre,
            state_mgr=self.state_mgr,
            chapter=chapter,
            memo=memo,
            max_retries=retries,
        )
        final_audit = audit_history[-1]

        chapter.audit_score = final_audit.overall_score
        chapter.audit_issues = [i.model_dump() for i in final_audit.issues]

        if final_audit.passed:
            chapter.status = ChapterStatus.APPROVED
        else:
            chapter.status = ChapterStatus.REVISED

        # 最终保存
        self._save_chapter_file(chapter)
        self.repo.save_chapter({
            "book_id": self.book.id,
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
            "content": chapter.content,
            "word_count": chapter.word_count,
            "status": chapter.status.value,
            "audit_score": chapter.audit_score,
            "audit_issues": json.dumps(chapter.audit_issues, ensure_ascii=False),
            "created_at": chapter.created_at,
            "updated_at": datetime.now().isoformat(),
        })

        # 最终章：自动完结
        if is_final_chapter(chapter_number, self.book.target_chapters):
            self._auto_finalize()

        return chapter

    def write_chapters(self, count: int) -> list[Chapter]:
        """连续写 N 章."""
        chapters = []
        for _ in range(count):
            ch = self.write_next_chapter()
            chapters.append(ch)
        return chapters

    def intervene(self, instruction: str) -> None:
        """添加干预指令."""
        from .intervener import parse_intervention
        self._interventions.append(parse_intervention(instruction))

    def get_status(self) -> dict:
        """获取写作状态."""
        chapter_count = self.repo.get_chapter_count()
        current_state = self.state_mgr.load_current_state()
        hook_pool = self.state_mgr.load_hook_pool()
        active_hooks = len([h for h in hook_pool.hooks if h.status.value not in ("resolved", "deferred")])

        status = {
            "book": self.book.title,
            "genre": self.genre.name,
            "chapters_written": chapter_count,
            "target_chapters": self.book.target_chapters,
            "progress": f"{chapter_count}/{self.book.target_chapters} ({100*chapter_count/max(1,self.book.target_chapters):.1f}%)",
            "active_hooks": active_hooks,
            "current_conflict": current_state.current_conflict,
            "current_location": current_state.current_location,
            "style_profile": self.style_profile.source_name if self.style_profile else "无",
        }

        # 完结状态
        if self.is_complete:
            status["status"] = "✅ 已完结"
        elif is_in_completion_window(chapter_count + 1, self.book.target_chapters):
            remaining = self.book.target_chapters - chapter_count
            status["status"] = f"🔔 完结窗口 — 剩余 {remaining} 章"
        else:
            status["status"] = "📝 写作中"

        return status

    def rewrite_chapter(self, chapter_number: int, instruction: str = "",
                        mode: str = "refine", truncate_after: bool = False) -> Chapter:
        """按用户意见重写指定章节，并同步记忆.

        mode="refine" 微调 / "rewrite" 大幅重写。覆盖前会将原章备份为 .bak。
        truncate_after=True：删除本章之后的所有章节（备份），并把记忆回滚到本章，
            适合"改了这一章、后续推倒重来"的场景；
        truncate_after=False：保留后续章，仅重算本章记忆（摘要/事实/当前状态）。
        """
        existing = self.repo.get_chapter(chapter_number)
        if existing is None:
            raise ValueError(f"第{chapter_number}章不存在，无法重写")

        original = Chapter(
            book_id=self.book.id,
            chapter_number=chapter_number,
            title=existing.get("title", ""),
            content=existing.get("content", ""),
            word_count=existing.get("word_count", 0),
        )

        if mode not in ("refine", "rewrite"):
            mode = "refine"

        revised = _rewrite_chapter_impl(
            client=self.client,
            genre=self.genre,
            chapter=original,
            instruction=instruction,
            mode=mode,
        )

        # 覆盖前备份原章
        self._backup_chapter_file(chapter_number)

        revised.status = ChapterStatus.REVISED
        self._save_chapter_file(revised)
        self.repo.save_chapter({
            "book_id": self.book.id,
            "chapter_number": revised.chapter_number,
            "title": revised.title,
            "content": revised.content,
            "word_count": revised.word_count,
            "status": ChapterStatus.REVISED.value,
            "audit_score": None,
            "audit_issues": [],
            "created_at": existing.get("created_at", datetime.now().isoformat()),
            "updated_at": datetime.now().isoformat(),
        })

        # ---- 记忆同步 ----
        if truncate_after:
            # 删除后续章节（文件备份 + 数据库删除），并把记忆回滚到本章
            self._delete_chapters_after_files(chapter_number)
            self.repo.delete_chapters_after(chapter_number)
            self.state_mgr.truncate_memory_after(chapter_number)

        # 无论哪种模式，都根据新正文重算本章记忆
        try:
            resettle_chapter(
                client=self.client,
                genre=self.genre,
                state_mgr=self.state_mgr,
                chapter=revised,
            )
        except Exception:
            pass

        return revised

    # ---- Internal ----

    def _delete_chapters_after_files(self, chapter_number: int) -> None:
        """删除章节号 > chapter_number 的所有章节 .md 文件（重命名为 .deleted 作软备份）."""
        for vol_dir in sorted(self.chapters_dir.glob("vol*")):
            for ch_file in vol_dir.glob("*.md"):
                stem = ch_file.stem
                if stem.isdigit() and int(stem) > chapter_number:
                    try:
                        bak = ch_file.with_suffix(".md.deleted")
                        if bak.exists():
                            bak.unlink()
                        ch_file.rename(bak)
                    except OSError:
                        pass

    def _backup_chapter_file(self, chapter_number: int) -> None:
        """将指定章节的现有 .md 文件备份为 .bak（覆盖旧备份）."""
        for vol_dir in sorted(self.chapters_dir.glob("vol*")):
            ch_file = vol_dir / f"{chapter_number:04d}.md"
            if ch_file.exists():
                bak = vol_dir / f"{chapter_number:04d}.md.bak"
                try:
                    bak.write_text(ch_file.read_text(encoding="utf-8"), encoding="utf-8")
                except OSError:
                    pass
                return
        flat = self.chapters_dir / f"{chapter_number:04d}.md"
        if flat.exists():
            bak = self.chapters_dir / f"{chapter_number:04d}.md.bak"
            try:
                bak.write_text(flat.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                pass

    def _save_chapter_file(self, chapter: Chapter) -> None:
        """保存章节到 volXX/ 文件夹."""
        # 从卷纲中找到当前章节所属的卷号
        vol_num = None
        if self._volume_plan and self._volume_plan.volumes:
            for v in self._volume_plan.volumes:
                m = re.match(r"(\d+)\s*-\s*(\d+)", v.chapter_range)
                if m:
                    start, end = int(m.group(1)), int(m.group(2))
                    if start <= chapter.chapter_number <= end:
                        vol_num = v.volume_number
                        break
        # 回退：按每 50 章一卷计算
        if vol_num is None:
            vol_num = (chapter.chapter_number - 1) // 50 + 1

        vol_dir = self.chapters_dir / f"vol{vol_num:02d}"
        vol_dir.mkdir(parents=True, exist_ok=True)

        path = vol_dir / f"{chapter.chapter_number:04d}.md"
        content = f"# 第{chapter.chapter_number}章 {chapter.title}\n\n{chapter.content}"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _update_current_focus(self, chapter: Chapter, memo: ChapterMemo) -> None:
        """每章写完后更新 current_focus.md."""
        current_state = self.state_mgr.load_current_state()
        summaries = self.state_mgr.load_summaries()

        recent = [s for s in summaries if s.chapter <= chapter.chapter_number]
        recent.sort(key=lambda s: s.chapter, reverse=True)
        recent_text = ""
        for s in recent[:3]:
            recent_text += f"- 第{s.chapter}章《{s.title}》：{s.events[:80]}（{s.mood}）\n"

        next_goal = memo.goal if memo.goal else "延续上一章情节"

        # 完结标记
        completion_header = ""
        if memo.is_final:
            completion_header = "\n## ⚠️ 最终章\n"
        elif memo.is_completion_arc:
            remaining = self.book.target_chapters - chapter.chapter_number
            completion_header = f"\n## ⚠️ 完结窗口 — 剩余 {remaining} 章\n"

        focus = f"""# 当前关注点
{completion_header}
## 最新进度
- 已完成第{chapter.chapter_number}章《{chapter.title}》
- 字数：{chapter.word_count}
- 状态：{chapter.status.value}

## 最近章节摘要
{recent_text}
## 当前状态
- 冲突：{current_state.current_conflict}
- 位置：{current_state.current_location}
- 主角状态：{current_state.protagonist_state}

## 下一章方向
{next_goal}

## 活跃伏笔
"""
        hook_pool = self.state_mgr.load_hook_pool()
        active_hooks = [h for h in hook_pool.hooks
                        if h.status.value not in ("resolved", "deferred")]
        for h in active_hooks[:5]:
            focus += f"- {h.hook_id}（{h.status.value}）：{h.expected_payoff[:60]}\n"

        self.state_mgr.write_story_file("current_focus.md", focus)

    def _auto_finalize(self) -> None:
        """最终章写完后自动完结."""
        ch_count = self.repo.get_chapter_count()
        chapters = self.repo.get_all_chapters()
        total_words = sum(ch.get("word_count", 0) for ch in chapters)

        report = finalize_book(
            client=self.client,
            genre=self.genre,
            state_mgr=self.state_mgr,
            book_id=self.book.id,
            book_title=self.book.title,
            total_chapters=ch_count,
            total_words=total_words,
        )

        self.book.status = BookStatus.COMPLETED
        self.book.updated_at = datetime.now().isoformat()
        self.repo.save_book(self.book.model_dump())

    def _update_bible(self, chapter: Chapter, memo: ChapterMemo) -> None:
        """更新故事圣经文件."""
        current_state = self.state_mgr.load_current_state()
        hook_pool = self.state_mgr.load_hook_pool()
        summaries = self.state_mgr.load_summaries()
        ch_count = self.repo.get_chapter_count()

        # 找到本章摘要
        chapter_summary = None
        for s in summaries:
            if s.chapter == chapter.chapter_number:
                chapter_summary = s
                break

        # index.md — 每章更新（不调 LLM）
        self.bible.update_index(
            chapter=chapter,
            memo=memo,
            current_state=current_state,
            hook_pool=hook_pool,
            chapter_count=ch_count,
            target_chapters=self.book.target_chapters,
        )

        # timeline.md — 每章追加（不调 LLM）
        if chapter_summary:
            self.bible.update_timeline(chapter, chapter_summary)

        # items.md — 每 5 章 LLM 增量更新
        if self.bible.should_update_items(chapter.chapter_number):
            self.bible.update_items(
                client=self.client,
                genre=self.genre,
                chapter=chapter,
                recent_summaries=summaries,
            )

    def _seed_volume_hooks_if_new_volume(self, chapter_number: int) -> None:
        """进入新卷时自动播种卷级伏笔."""
        if self._volume_plan is None or not self._volume_plan.volumes:
            return

        # 从卷纲中找到当前章节所属的卷号和卷起始章
        current_vol = None
        vol_start = None
        chapters_per_volume = 50
        for v in self._volume_plan.volumes:
            m = re.match(r"(\d+)\s*-\s*(\d+)", v.chapter_range)
            if m:
                start, end = int(m.group(1)), int(m.group(2))
                if start <= chapter_number <= end:
                    current_vol = v.volume_number
                    vol_start = start
                    chapters_per_volume = end - start + 1
                    break
        # 回退：按每 50 章一卷计算
        if current_vol is None:
            current_vol = (chapter_number - 1) // 50 + 1
            vol_start = (current_vol - 1) * 50 + 1
        if chapter_number != vol_start + 1:
            return

        # 检查该卷是否已有卷级伏笔
        hook_pool = self.state_mgr.load_hook_pool()
        existing_volume_hooks = [
            h for h in hook_pool.hooks
            if h.hook_level and h.hook_level.value == "volume"
            and h.volume_number == current_vol
        ]
        if existing_volume_hooks:
            return  # 已播种过

        # 找到当前卷的 Volume 对象
        current_volume = None
        for v in self._volume_plan.volumes:
            if v.volume_number == current_vol:
                current_volume = v
                break

        if current_volume is None:
            return

        # 播种卷级伏笔
        volume_hooks_count = self._writing_config.get("volume_hooks_count", 10)
        new_hooks = plan_volume_hooks(
            client=self.client,
            genre=self.genre,
            volume=current_volume,
            book_id=self.book.id,
            chapter_number=chapter_number,
            chapters_per_volume=chapters_per_volume,
            volume_hooks_count=volume_hooks_count,
        )

        if new_hooks:
            hook_pool = self.state_mgr.load_hook_pool()
            for h in new_hooks:
                hook_pool.hooks.append(h)
            self.state_mgr.save_hook_pool(hook_pool)

    def _load_cascade_rules(self):
        """加载链式反应规则."""
        from fanqie.models import CascadeRules, CascadeRule
        path = self.book_dir / "story" / "foundation" / "world.md"
        if not path.exists():
            # 回退到旧位置
            old_path = self.book_dir / "story" / "cascade_rules.md"
            if old_path.exists():
                path = old_path
            else:
                return CascadeRules(book_id=self.book.id)
        rules = []
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        blocks = re.split(r"## 规则 \d+: ", content)
        for block in blocks[1:]:
            lines = block.strip().split("\n")
            setting = lines[0].strip() if lines else ""
            c1 = c2 = c3 = ""
            for line in lines[1:]:
                line = line.strip()
                if line.startswith("- 第一层后果:"):
                    c1 = line.replace("- 第一层后果:", "").strip()
                elif line.startswith("- 第二层社会变化:"):
                    c2 = line.replace("- 第二层社会变化:", "").strip()
                elif line.startswith("- 第三层新矛盾:"):
                    c3 = line.replace("- 第三层新矛盾:", "").strip()
            if setting:
                rules.append(CascadeRule(
                    setting=setting,
                    consequence_1=c1,
                    consequence_2=c2,
                    consequence_3=c3,
                ))
        return CascadeRules(book_id=self.book.id, rules=rules)


def create_book(
    title: str,
    genre_id: str,
    data_dir: str = "data",
    chapter_word_count: int = 2000,
    target_chapters: int = 500,
) -> Orchestrator:
    """创建新书."""
    import uuid

    genre = load_genre(genre_id)
    if genre is None:
        raise ValueError(f"题材 '{genre_id}' 不存在，请用 'fanqie genre list' 查看可用题材")

    book_id = str(uuid.uuid4())[:8]
    book = BookConfig(
        id=book_id,
        title=title,
        genre_id=genre_id,
        chapter_word_count=chapter_word_count,
        target_chapters=target_chapters,
    )

    repo = Repository(data_dir, book_id)
    repo.save_book(book.model_dump())

    return Orchestrator(book=book, genre=genre, data_dir=data_dir)
