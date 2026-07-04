"""Reviser — 自动修订，根据审计结果修复章节."""

from __future__ import annotations

from fanqie.llm.client import LLMClient
from fanqie.models import Chapter, AuditResult, ChapterMemo
from fanqie.genres.loader import GenreProfile


def revise_chapter(
    client: LLMClient,
    genre: GenreProfile,
    chapter: Chapter,
    audit: AuditResult,
    memo: ChapterMemo,
) -> Chapter:
    """根据审计结果自动修订章节."""
    if audit.passed or audit.parse_failed:
        return chapter

    critical_issues = [i for i in audit.issues if i.severity == "critical"]
    if not critical_issues:
        return chapter

    issues_text = "\n".join(
        f"- [{i.severity}] {i.category}: {i.description}\n  建议: {i.suggestion}"
        for i in critical_issues
    )

    system_prompt = f"""你是{genre.name}题材的专业修订编辑。请根据审查意见修改以下章节。

## 修订原则
- 只修改被标记的问题部分
- 保持原有风格和节奏
- 修改后字数应接近原文
- 不要引入新的问题"""

    user_prompt = f"""请修订以下章节。

## 审查意见
{issues_text}

## Chapter Memo
目标: {memo.goal}
禁忌: {'、'.join(memo.must_avoid) if memo.must_avoid else '无'}

## 原文
{chapter.content[:5000]}

请输出修订后的完整章节内容。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat(messages, temperature=0.5)
    revised_content = result["content"]

    word_count = len(revised_content.replace(" ", "").replace("\n", ""))

    return Chapter(
        book_id=chapter.book_id,
        chapter_number=chapter.chapter_number,
        title=chapter.title,
        content=revised_content,
        word_count=word_count,
        status="revised",
    )
