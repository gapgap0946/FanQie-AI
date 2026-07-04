"""Writer — 章节生成，含 pre-write checklist + 文风指纹注入 + 完结模式."""

from __future__ import annotations

import re

from fanqie.llm.client import LLMClient
from fanqie.models import ChapterMemo, ContextPackage, Chapter
from fanqie.genres.loader import GenreProfile
from fanqie.models import GoldenThreeConfig
from fanqie.style.profile import StyleProfile
from fanqie.style.injector import render_style_fingerprint


def render_golden_three_rules(config: GoldenThreeConfig, chapter_number: int) -> str:
    """渲染黄金三章写作规则."""
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

    rules_text = "\n".join(f"- {r}" for r in rules)

    return f"""

## ⚠️ 黄金三章 — {chapter_label} 专项规则

本章结构框架：{structure}

必须遵守：
{rules_text}

黄金三章是读者留存的关键。前三章的质量直接决定追读率。
请严格按照上述规则写作，确保本章达到网文行业最佳实践标准。
"""


def build_writer_system_prompt(
    genre: GenreProfile,
    chapter_number: int,
    chapter_word_count: int = 2000,
    style_profile: StyleProfile | None = None,
    is_completion_arc: bool = False,
    is_final: bool = False,
) -> str:
    """构建 Writer 的 system prompt."""
    fatigue = "、".join(genre.fatigue_words[:8])
    chapter_types = "、".join(genre.chapter_types) if genre.chapter_types else "事件章/过渡章/揭示章/高潮章"
    satisfaction = "、".join(genre.satisfaction_types) if genre.satisfaction_types else "打脸/升级/真相揭示"

    prompt = f"""你是一位专业的{genre.name}网文写手，为番茄小说平台创作高质量章节。

## 题材规则
{chr(10).join(f'{k}: {v}' for k, v in genre.rules.items())}

## 输出格式

1. 先输出 PRE_WRITE_CHECK 表格，逐项确认后再开始正文
2. 目标字数 {chapter_word_count} 字，允许范围 {int(chapter_word_count*0.8)}-{int(chapter_word_count*1.2)} 字
3. 章节标题用"第X章 标题"格式，标题要有吸引力
4. 正文段落适合手机屏幕阅读

## 写作心法

- 番茄小说的核心爽感来自"冲突+解决+打脸"的循环
- 每章必须有至少一个爽点：打脸+反转=读者爽感最大化
- 主角的每一次行动都要有明确的因果链条
- 配角不是工具人，要有自己的动机和弧光
- 对话/心理/动作/环境描写交替使用，避免单一

## 黄金法则

- Show, don't tell：用行动和对话展示，不要直接叙述
- 每章至少制造 1-2 个悬念钩子
- 节奏张弛有度：紧张/舒缓/爆发交替
- 主角必须主动推进剧情，不能被动等待
- 每章结尾必须有"下一章会怎样"的冲动
- 反派/对手必须聪明，不能降智

## 爽点密度要求

- 每 300 字必须有 1 个小爽点（如主角展示能力、打脸配角、获得新线索）
- 每 500 字必须有 1 个中爽点（如"原来如此"的反转）
- 每 1000-1500 字必须有 1 个大爽点（如"你惹错人了"的爆发）
- 章末 300 字必须为下一章制造期待（悬念、新目标、或即将到来的冲突）

## 文笔要求

- 对话占比不低于 40%，每段对话不超过 2 句
- 段落控制在 40-120 字，3-5 行手机屏幕
- 避免大段环境描写
- 字数 < 40 字的短段落有三种用途：(1) 强调 300 字内的关键动作 (2) 制造节奏变化 (3) 每 3 段用一次"呼吸"
- 连续 3 段不超过 60 字则节奏过碎

## 严禁事项

{chr(10).join(f'- {p}' for p in genre.prohibitions)}

## 严禁元叙事（防幻觉）

- 禁止在正文中出现"第X章""上一章""前文提到"等章节引用
- 禁止在正文中出现"读者""作者""写作"等元叙事词汇
- 禁止在正文中引用内部标识（如 hook_001、伏笔编号等）
- 所有信息必须通过角色视角自然呈现，不能像写报告一样罗列
- 章节标题不能与上一章标题相同或高度相似，必须有明显区分

## 疲劳词黑名单（避免使用）

{fatigue}

## 输出模板（必须严格遵循）

=== PRE_WRITE_CHECK ===
用 Markdown 表格逐项检查 Chapter Memo 中的要求
| 检查项 | 具体要求 | 状态 |
|--------|----------|------|
| 核心任务 | 对照 Chapter Memo 的 goal 字段，确认本章要完成什么 | 已确认 |
| 读者期待 | 本章要给读者什么样的满足感 | 见 memo 字段 |
| 兑现 / 压牌 | 哪些伏笔要推进 + 哪些信息要隐藏 | 见 memo 字段 |
| 过渡/日常任务 | 本章是否承担过渡/日常功能 | 见 memo 字段 |
| 章末必须变化 | 对照 memo 的 end_changes，确认 1-3 个具体变化 | 已确认 |
| 禁忌 | 对照 memo 的 must_avoid | 已确认 |
| 章节类型 | {chapter_types} | |

=== CHAPTER_TITLE ===
格式"第X章 标题"，标题要抓人眼球且有信息量

=== CHAPTER_CONTENT ===
正文内容，约 {chapter_word_count} 字

请严格按照 PRE_WRITE_CHECK、CHAPTER_TITLE、CHAPTER_CONTENT 三段输出。
确保每章都有明确的爽点和悬念钩子。"""

    # 黄金三章规则注入
    if chapter_number <= 3 and genre.golden_three_config:
        prompt += render_golden_three_rules(genre.golden_three_config, chapter_number)

    # 完结窗口模式
    if is_completion_arc and not is_final:
        prompt += """

## ⚠️ 完结窗口模式

你正处于完结窗口阶段，请遵守以下规则：

1. **不引入新人物**：不要创建任何新角色
2. **不开启新冲突线**：只推进和解决已有冲突
3. **不播种新伏笔**：不要制造新的悬念或谜团
4. **推进伏笔回收**：每章至少推进 1 个待回收伏笔
5. **配角开始收束**：给配角安排退场、转变或归宿的铺垫
6. **节奏逐步放缓**：从"紧张/爆发"逐步过渡到"释放/收束"
7. **章末钩子改为"期待收束"**：不再制造"下一章会怎样"的悬念，而是制造"下一章会如何收束"的期待"""

    # 最终章模式
    if is_final:
        prompt += """

## ⚠️ 最终章模式

这是全书的最后一章，请遵守以下规则：

1. **所有伏笔必须回收**：本章解决所有剩余悬念
2. **高潮收束**：最终冲突达到顶点并解决
3. **角色归宿**：每个主要角色都要有明确的结局交代
4. **主题呼应**：呼应全书的主题和开篇意象
5. **情感释放**：给读者一个满意的情感收尾，让读者感到"值得"
6. **节奏从容**：虽然是最后一章，但不要仓促，给读者回味空间
7. **开放式余韵**：可以留一个开放式结尾（如"新的旅程即将开始"），但不能留未解悬念
8. **结尾金句**：最后一段最好有一句能让人记住的金句
9. **章末不设钩子**：不再制造悬念，而是给读者一个完整的句号"""

    # 注入文风指纹
    if style_profile:
        prompt += "\n\n" + render_style_fingerprint(style_profile)

    return prompt


def build_writer_user_prompt(
    memo: ChapterMemo,
    context_pkg: ContextPackage,
    chapter_number: int,
    prev_title: str = "",
) -> str:
    """构建 Writer 的 user prompt."""
    memo_text = memo.body if memo.body else f"""## 当前任务
{memo.goal}

## 读者此刻在等什么
{memo.reader_waiting_for}

## 该兑现的 / 暂不揭的
兑现: {memo.pay_off}
压牌: {memo.keep_hidden}

## 章末必须发生的变化
{memo.end_changes}

## 不要做
{chr(10).join(f'- {x}' for x in memo.must_avoid) if memo.must_avoid else '- 无'}"""

    ctx_lines = ["## 相关上下文", ""]
    for entry in context_pkg.selected_context:
        tag = "[PROTECTED]" if entry.is_protected else ""
        ctx_lines.append(f"- {entry.source} {tag}: {entry.excerpt[:200]}")

    # 最终章特殊提示
    final_note = ""
    if memo.is_final:
        final_note = "\n\n⚠️ 这是全书的最后一章。请给读者一个满意的结局。"

    # 上一章标题提示（防重复）
    prev_note = ""
    if prev_title:
        clean_prev = re.sub(r'^第\d+章\s*', '', prev_title)
        prev_note = f"\n\n⚠️ 上一章标题是「{clean_prev}」，本章标题必须不同，不能重复或高度相似。"

    return f"""请为第{chapter_number}章生成内容。

## Chapter Memo
{memo_text}

{chr(10).join(ctx_lines)}{final_note}{prev_note}

请先完成 PRE_WRITE_CHECK 再开始正文。"""


def write_chapter(
    client: LLMClient,
    genre: GenreProfile,
    memo: ChapterMemo,
    context_pkg: ContextPackage,
    chapter_number: int,
    chapter_word_count: int = 2000,
    style_profile: StyleProfile | None = None,
    prev_title: str = "",
) -> Chapter:
    """生成一个章节，含字数校验和自动修正."""
    system_prompt = build_writer_system_prompt(
        genre=genre,
        chapter_number=chapter_number,
        chapter_word_count=chapter_word_count,
        style_profile=style_profile,
        is_completion_arc=memo.is_completion_arc,
        is_final=memo.is_final,
    )
    user_prompt = build_writer_user_prompt(memo, context_pkg, chapter_number, prev_title)

    # 字数范围
    min_words = int(chapter_word_count * 0.8)
    max_words = int(chapter_word_count * 1.2)
    max_tokens = int(chapter_word_count * 2.5)

    max_retries = 3
    title, body, word_count = "", "", 0
    correction = ""
    for attempt in range(max_retries):
        # 重试时在原始 user_prompt 后追加字数纠正指令，而非累积上一版整章正文，
        # 避免 prompt 随重试线性膨胀导致 token 成本飙升。
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt + correction},
        ]
        result = client.chat(messages, temperature=0.8, max_tokens=max_tokens)

        content = result["content"]
        title, body = _parse_chapter_output(content)

        word_count = len(body.replace(" ", "").replace("\n", ""))

        if min_words <= word_count <= max_words:
            break

        if attempt < max_retries - 1:
            if word_count < min_words:
                correction = (
                    f"\n\n[系统指令] 请严格控制字数：目标 {chapter_word_count} 字"
                    f"（允许 {min_words}-{max_words} 字）。上一次生成偏少，"
                    f"请通过增加细节描写、对话、心理活动或环境描写写足字数，情节保持完整。"
                )
            else:
                correction = (
                    f"\n\n[系统指令] 请严格控制字数：目标 {chapter_word_count} 字"
                    f"（允许 {min_words}-{max_words} 字）。上一次生成偏多，"
                    f"请精炼表达、删减冗余描写和重复内容，保留核心情节和爽点。"
                )

    return Chapter(
        book_id=memo.book_id,
        chapter_number=chapter_number,
        title=title,
        content=body,
        word_count=word_count,
    )


def _parse_chapter_output(content: str) -> tuple[str, str]:
    """解析 Writer 输出的章节内容."""
    title = ""
    body = content

    title_match = re.search(
        r"=== CHAPTER_TITLE ===\s*\n+(.*?)\n+=== CHAPTER_CONTENT ===",
        content, re.DOTALL
    )
    if title_match:
        title = title_match.group(1).strip()
        body_start = content.find("=== CHAPTER_CONTENT ===")
        if body_start >= 0:
            body = content[body_start + len("=== CHAPTER_CONTENT ==="):].strip()

    for marker in ["=== POST_SETTLEMENT ===", "=== UPDATED_STATE ===", "=== CHAPTER_SUMMARY ==="]:
        idx = body.find(marker)
        if idx >= 0:
            body = body[:idx].strip()

    return title, body
