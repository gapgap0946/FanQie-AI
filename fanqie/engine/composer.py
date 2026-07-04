"""Composer — 上下文组装入口."""

from __future__ import annotations

from fanqie.models import ChapterMemo, ContextPackage
from fanqie.memory.state_manager import StateManager
from fanqie.memory.context_assembly import assemble_context
from fanqie.memory.bible_manager import BibleManager


def compose_context(
    state_mgr: StateManager,
    memo: ChapterMemo,
    chapter_number: int,
    target_chapters: int | None = None,
    bible: BibleManager | None = None,
) -> ContextPackage:
    """组装上下文，含故事圣经."""
    return assemble_context(
        state_mgr=state_mgr,
        memo=memo,
        chapter_number=chapter_number,
        target_chapters=target_chapters,
        bible=bible,
    )
