"""Brief Optimizer — 简报优化器：AI 补全 + 5 维度评分."""

from __future__ import annotations

import os

from fanqie.llm.client import LLMClient
from fanqie.genres.loader import GenreProfile
from fanqie.models import BriefScore, BriefReport


def optimize_brief(
    client: LLMClient,
    raw_brief: str,
    genre: GenreProfile,
) -> tuple[str, list[str], list[str]]:
    """AI 补全优化简报，返回 (优化后简报, 建议列表, 缺失要素列表)."""
    system_prompt = f"""你是{genre.name}题材的创意编辑。请根据用户提供的创意简报，补全优化。

## 优化要求
1. 补充缺失的核心要素（世界观/主角/冲突/金手指）
2. 增强爽点设计（打脸/逆袭/升级/揭秘）
3. 确保设定自洽，AI 可据此生成连贯章节
4. 保持用户原有创意的核心方向

## 输出格式（严格 JSON）
{{
  "optimized_brief": "优化后的完整简报",
  "suggestions": ["建议1", "建议2"],
  "missing_elements": ["缺失要素1", "缺失要素2"]
}}"""

    user_prompt = f"## 用户创意简报\n{raw_brief[:4000]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.7)
    parsed = result.get("parsed", {})

    optimized = parsed.get("optimized_brief", raw_brief)
    suggestions = parsed.get("suggestions", [])
    missing = parsed.get("missing_elements", [])

    return optimized, suggestions, missing


def score_brief(
    client: LLMClient,
    brief: str,
    genre: GenreProfile,
) -> BriefScore:
    """按 5 维度加权评分."""
    system_prompt = f"""你是{genre.name}题材的资深编辑。请对以下创意简报按 5 个维度评分。

## 评分维度（满分）
1. 题材契合度（30 分）— 是否符合所选题材的核心套路和读者期待
2. 爽点潜力（25 分）— 打脸/逆袭/升级/揭秘等爽感设计是否充足
3. 可执行性（20 分）— AI 能否据此生成连贯章节，设定是否自洽
4. 完整性（15 分）— 核心要素是否齐全（世界观/主角/冲突/金手指）
5. 差异化（10 分）— 与同题材常见套路的区分度

## 输出格式（严格 JSON）
{{
  "genre_fit": 25,
  "satisfaction_potential": 20,
  "executability": 15,
  "completeness": 12,
  "differentiation": 7,
  "comment": "评分说明"
}}"""

    user_prompt = f"## 创意简报\n{brief[:4000]}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.3)
    parsed = result.get("parsed", {})

    return BriefScore(
        genre_fit=parsed.get("genre_fit", 0),
        satisfaction_potential=parsed.get("satisfaction_potential", 0),
        executability=parsed.get("executability", 0),
        completeness=parsed.get("completeness", 0),
        differentiation=parsed.get("differentiation", 0),
    )


def run_brief_pipeline(
    client: LLMClient,
    raw_brief: str,
    genre: GenreProfile,
    book_id: str,
) -> BriefReport:
    """完整 Brief 优化流程：优化 → 评分."""
    optimized, suggestions, missing = optimize_brief(client, raw_brief, genre)
    score = score_brief(client, optimized, genre)

    return BriefReport(
        book_id=book_id,
        original_brief=raw_brief,
        optimized_brief=optimized,
        score=score,
        suggestions=suggestions,
        missing_elements=missing,
    )


def save_brief_report(report: BriefReport, story_dir: str) -> None:
    """保存 Brief 报告到 reports/ 目录."""
    reports_dir = os.path.join(story_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    content = f"""# Brief 优化报告

## 评分
- 题材契合度: {report.score.genre_fit}/30
- 爽点潜力: {report.score.satisfaction_potential}/25
- 可执行性: {report.score.executability}/20
- 完整性: {report.score.completeness}/15
- 差异化: {report.score.differentiation}/10
- **总分: {report.score.total}/100 — {report.score.verdict}**

## 优化建议
{chr(10).join(f'- {s}' for s in report.suggestions)}

## 缺失要素
{chr(10).join(f'- {m}' for m in report.missing_elements)}

## 优化后简报
{report.optimized_brief}
"""
    with open(os.path.join(reports_dir, "brief_report.md"), "w", encoding="utf-8") as f:
        f.write(content)
