"""Reviser — 自动修订，根据审计结果修复章节."""

from __future__ import annotations

import re

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


def rewrite_chapter(
    client: LLMClient,
    genre: GenreProfile,
    chapter: Chapter,
    instruction: str,
    mode: str = "refine",
) -> Chapter:
    """根据用户意见重写章节.

    mode="refine"：基于原文按用户意见微调，保留大部分情节；
    mode="rewrite"：以原章为参考，按用户意见大幅重写本章。
    """
    target_words = chapter.word_count or len(chapter.content.replace(" ", "").replace("\n", ""))
    instruction = (instruction or "").strip()

    if mode == "rewrite":
        mode_rules = """## 重写模式（大幅改写）
- 以原章为参考，按用户意见重新创作本章，可大幅调整情节、节奏与描写
- 保持本章在整部书中的定位与承接关系（章号、核心目标不变）
- 保留原章标题指向的主线事件，除非用户明确要求更换"""
    else:
        mode_rules = """## 微调模式（保留主体）
- 在原文基础上按用户意见修改，保留大部分情节与结构
- 只调整用户指出的问题，不要推翻重来
- 尽量保持原有风格、人物口吻与节奏"""

    system_prompt = f"""你是{genre.name}题材的专业网文写手，正在按作者的意见重写某一章。

{mode_rules}

## 写作要求
- 目标字数约 {target_words} 字（允许上下浮动 20%）
- 保持{genre.name}题材的爽感节奏与文风
- 章末保留或强化"追读钩子"，让读者想看下一章
- 严格遵循作者意见，这是最高优先级

## 输出格式（严格遵守）
=== CHAPTER_TITLE ===
第{chapter.chapter_number}章 标题（若作者未要求改标题，沿用原标题）
=== CHAPTER_CONTENT ===
（正文，不要包含任何解释、点评或标题行）"""

    user_prompt = f"""## 作者的重写意见（最高优先级）
{instruction if instruction else '（作者未填写具体意见，请提升本章的可读性、爽点密度与钩子强度）'}

## 原章标题
第{chapter.chapter_number}章 {chapter.title}

## 原章正文
{chapter.content[:6000]}

请按上述意见输出重写后的章节。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat(messages, temperature=0.8)
    content = result["content"]

    title, body = _parse_rewrite_output(content, chapter.title)
    word_count = len(body.replace(" ", "").replace("\n", ""))

    return Chapter(
        book_id=chapter.book_id,
        chapter_number=chapter.chapter_number,
        title=title,
        content=body,
        word_count=word_count,
        status="revised",
    )


def _parse_rewrite_output(content: str, fallback_title: str) -> tuple[str, str]:
    """解析重写输出的标题与正文，解析失败时回退到原标题与全文."""
    title = fallback_title
    body = content.strip()

    if "=== CHAPTER_TITLE ===" in content and "=== CHAPTER_CONTENT ===" in content:
        try:
            title_part = content.split("=== CHAPTER_TITLE ===")[1].split("=== CHAPTER_CONTENT ===")[0].strip()
            body_part = content.split("=== CHAPTER_CONTENT ===")[1].strip()
            title_part = re.sub(r"^第\s*\d+\s*章\s*", "", title_part).strip()
            if title_part:
                title = title_part
            if body_part:
                body = body_part
        except (IndexError, ValueError):
            pass

    body = re.sub(r"^#\s*第\s*\d+\s*章.*?\n+", "", body).strip()
    return title, body
