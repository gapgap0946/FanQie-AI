"""Advisor — 人机协作编辑器：波及分析 + 定向修订."""

from __future__ import annotations

import os
from datetime import datetime

from fanqie.llm.client import LLMClient
from fanqie.genres.loader import GenreProfile
from fanqie.models import ImpactEntry, ImpactReport, CascadeRules


def analyze_impact(
    client: LLMClient,
    genre: GenreProfile,
    change_request: str,
    cascade_rules: CascadeRules,
    story_dir: str,
) -> ImpactReport:
    """波及分析：查找修改请求的所有下游影响."""
    cascade_text = "\n".join(
        f"- {r.setting} → {r.consequence_1} → {r.consequence_2} → {r.consequence_3}"
        for r in cascade_rules.rules
    )

    # 列出 story 目录下所有文件
    story_files = _list_story_files(story_dir)

    system_prompt = f"""你是{genre.name}题材的设定编辑。请分析修改请求的波及影响。

## 波及分析流程
1. 在链式反应中查找该节点的所有下游影响
2. 列出受影响的文件列表
3. 每个文件说明为什么受影响 + 建议修改内容

## 输出格式（严格 JSON）
{{
  "affected_nodes": ["受影响的级联节点1", "节点2"],
  "impacts": [
    {{
      "file": "story/story_frame.md",
      "reason": "为什么受影响",
      "suggested_change": "建议修改内容",
      "severity": "critical/major/moderate/minor"
    }}
  ],
  "summary": "波及分析总结"
}}"""

    user_prompt = f"""## 修改请求
{change_request}

## 链式反应规则
{cascade_text[:4000]}

## 现有文件
{story_files[:2000]}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.4)
    parsed = result.get("parsed", {})

    impacts = []
    for i in parsed.get("impacts", []):
        impacts.append(ImpactEntry(
            file=i.get("file", ""),
            reason=i.get("reason", ""),
            suggested_change=i.get("suggested_change", ""),
            severity=i.get("severity", "moderate"),
        ))

    return ImpactReport(
        book_id="",
        change_request=change_request,
        affected_nodes=parsed.get("affected_nodes", []),
        impacts=impacts,
        summary=parsed.get("summary", ""),
    )


def revise_memory(
    client: LLMClient,
    genre: GenreProfile,
    book_id: str,
    impact_report: ImpactReport,
    story_dir: str,
) -> list[dict]:
    """按波及报告修改记忆文件."""
    modifications = []

    for impact in impact_report.impacts:
        # 处理新路径前缀：foundation/、runtime/、reports/
        clean_path = impact.file
        for prefix in ("foundation/", "runtime/", "reports/", "story/"):
            if clean_path.startswith(prefix):
                clean_path = clean_path[len(prefix):]
                break
        file_path = os.path.join(story_dir, clean_path)
        if not os.path.exists(file_path):
            # 尝试在新子目录下查找
            for sub in ("foundation", "runtime", "reports"):
                alt_path = os.path.join(story_dir, sub, clean_path)
                if os.path.exists(alt_path):
                    file_path = alt_path
                    break
            else:
                modifications.append({
                    "file": impact.file,
                    "status": "skipped",
                    "reason": "文件不存在",
                })
                continue

        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()

        system_prompt = f"""你是{genre.name}题材的设定修订编辑。请根据波及分析修改文件。

## 修改原则
- 只修改受影响的部分，保持其他内容不变
- 确保修改后与链式反应一致
- 输出完整文件内容"""

        user_prompt = f"""## 修改原因
{impact.reason}

## 建议修改
{impact.suggested_change}

## 原文件内容
{original[:5000]}

请输出修订后的完整文件内容。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result = client.chat(messages, temperature=0.4)
        revised = result["content"]

        # 写入修订后内容
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(revised)

        modifications.append({
            "file": impact.file,
            "status": "revised",
            "severity": impact.severity,
        })

    return modifications


def revise_chapters(
    client: LLMClient,
    genre: GenreProfile,
    book_id: str,
    impact_report: ImpactReport,
    chapters_dir: str,
) -> list[dict]:
    """对已生成章节做定向修订."""
    modifications = []

    if not os.path.isdir(chapters_dir):
        return modifications

    chapter_files = sorted(
        [f for f in os.listdir(chapters_dir) if f.endswith(".md")],
    )

    # 只修订受影响的章节（取前 3 章做示范）
    for cf in chapter_files[:3]:
        file_path = os.path.join(chapters_dir, cf)
        with open(file_path, "r", encoding="utf-8") as f:
            original = f.read()

        system_prompt = f"""你是{genre.name}题材的修订编辑。请根据设定修改定向修订章节。

## 修订原则
- 只修改与设定变更相关的部分
- 保持原有风格和节奏
- 修改后字数应接近原文"""

        user_prompt = f"""## 波及分析摘要
{impact_report.summary}

## 需要修改的设定
{impact_report.change_request}

## 原章节内容
{original[:4000]}

请输出修订后的完整章节内容。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result = client.chat(messages, temperature=0.4)
        revised = result["content"]

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(revised)

        modifications.append({
            "chapter": cf,
            "status": "revised",
        })

    return modifications


def log_modification(
    story_dir: str,
    change_summary: str,
    impact_report: ImpactReport,
) -> None:
    """记录修改日志到 reports/."""
    reports_dir = os.path.join(story_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    log_path = os.path.join(reports_dir, "modification_log.md")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = f"""## {timestamp}

**修改请求**: {change_summary}

**波及分析**: {impact_report.summary}

**受影响节点**: {'、'.join(impact_report.affected_nodes) if impact_report.affected_nodes else '无'}

**受影响文件**:
{chr(10).join(f'- [{i.severity}] {i.file}: {i.reason}' for i in impact_report.impacts)}

---
"""

    existing = ""
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            existing = f.read()

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(entry + existing)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_story_files(story_dir: str) -> str:
    """列出 story 目录下的文件结构."""
    lines = []
    if os.path.isdir(story_dir):
        for root, dirs, files in os.walk(story_dir):
            rel = os.path.relpath(root, story_dir)
            if rel == ".":
                prefix = "story"
            else:
                prefix = f"story/{rel.replace(os.sep, '/')}"
            for f in sorted(files):
                if f.endswith((".md", ".json")):
                    lines.append(f"- {prefix}/{f}")
    return "\n".join(lines)
