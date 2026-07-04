"""Auditor — Continuity Auditor，多维度审查 + 审计重写循环."""

from __future__ import annotations

from fanqie.llm.client import LLMClient
from fanqie.models import Chapter, ChapterMemo, AuditResult, AuditIssue
from fanqie.genres.loader import GenreProfile
from fanqie.models import GoldenThreeConfig
from fanqie.memory.state_manager import StateManager
from fanqie.memory.fatigue_detector import run_fatigue_checks
from .reviser import revise_chapter


# 黄金三章审计规则：每章覆盖全部 4 条规则
GOLDEN_THREE_CHECKS = {
    1: [
        {
            "label": "黄金三章-第1章冲突开局",
            "description": "前300字是否有强冲突（死亡/背叛/危机），不能是流水账",
            "suggestion": "前300字必须出现死亡/背叛/危机等强冲突，用动作/对话开篇",
        },
        {
            "label": "黄金三章-第1章主角亮相",
            "description": "500字内主角是否亮相，用动作/台词立人设",
            "suggestion": "500字内必须让主角出场，通过具体行动或对话展示性格",
        },
        {
            "label": "黄金三章-第1章世界观极简",
            "description": "世界观是否用极简方式点出（10-20字），没有堆设定",
            "suggestion": "世界观只做极简暗示，不要大段介绍设定，让读者通过剧情感知",
        },
        {
            "label": "黄金三章-第1章章末钩子",
            "description": "章末是否有强烈的'下一章会怎样'钩子",
            "suggestion": "章末必须有悬念钩子：新威胁、意外发现、或关键选择",
        },
    ],
    2: [
        {
            "label": "黄金三章-第2章金手指亮相",
            "description": "金手指是否在本章亮相并通过戏剧性场景展示",
            "suggestion": "金手指必须在第2章亮相，用具体的戏剧性场景展示其效果",
        },
        {
            "label": "黄金三章-第2章金手指效果",
            "description": "金手指首次使用是否有明显效果，规则是否简单清晰",
            "suggestion": "金手指首次使用要有立竿见影的效果，规则一句话能说清",
        },
        {
            "label": "黄金三章-第2章关系补充",
            "description": "是否通过剧情展示了人物关系和世界观细节，而非直接叙述",
            "suggestion": "人物关系和世界观细节要通过剧情自然展示，不要写成设定说明",
        },
        {
            "label": "黄金三章-第2章冲突升级",
            "description": "冲突是否升级：叠加人际/资源/认知三重压力",
            "suggestion": "本章冲突要比第1章更复杂，至少叠加两种不同类型的压力",
        },
    ],
    3: [
        {
            "label": "黄金三章-第3章爽点爆发",
            "description": "本章是否有至少1个爽点（打脸/收获/反转）",
            "suggestion": "第3章必须有至少1个明确的爽点：打脸、收获或反转",
        },
        {
            "label": "黄金三章-第3章情绪爆点",
            "description": "是否有情绪爆点让读者获得满足感",
            "suggestion": "第3章要有情绪高潮：主角扬眉吐气、真相揭示、或能力突破",
        },
        {
            "label": "黄金三章-第3章信息差钩子",
            "description": "章末是否通过信息差制造期待感",
            "suggestion": "章末用信息差钩子：主角知道但读者不知道，或读者知道但主角不知道",
        },
        {
            "label": "黄金三章-第3章阻碍升级",
            "description": "是否在爽点之后埋下更大的阻碍/挑战",
            "suggestion": "爽点之后要暗示更大的挑战，让读者期待后续发展",
        },
    ],
}


def _build_golden_three_audit_prompt(
    chapter_number: int, content: str, config: GoldenThreeConfig | None = None
) -> str:
    """构建黄金三章专项审查 prompt，覆盖全部规则."""
    checks = GOLDEN_THREE_CHECKS.get(chapter_number)
    if not checks:
        return ""

    # 第1章只看前800字，其余看前3000字
    sample = content[:800] if chapter_number == 1 else content[:3000]

    checks_text = "\n".join(
        f"{i+1}. **{c['label']}**：{c['description']}"
        for i, c in enumerate(checks)
    )

    return f"""
## 黄金三章专项检查 — 第{chapter_number}章

请逐条检查以下黄金三章规则，每一条不符合都要在 issues 中添加 severity="critical" 的条目：

{checks_text}

章节内容（节选）：
{sample}
"""


DIMENSION_LABELS = {
    1: "OOC检测", 2: "事实一致性", 3: "时间线", 4: "空间位置",
    5: "物品状态", 6: "伏笔推进", 7: "伏笔矛盾", 8: "伏笔回收",
    9: "节奏检测", 10: "爽点密度", 11: "章节功能", 13: "对话质量",
    14: "段落节奏", 15: "疲劳词", 16: "开头模式", 17: "结尾",
    18: "情绪单调", 19: "标题塌缩", 24: "角色关系", 25: "力量体系",
    26: "世界观一致",
}


def build_auditor_system_prompt(genre: GenreProfile) -> str:
    """构建 Auditor 的 system prompt."""
    dims = genre.audit_dimensions
    dim_list = "\n".join(
        f"{d}. {DIMENSION_LABELS.get(d, f'维度{d}')}"
        for d in dims
    )

    return f"""你是{genre.name}题材的专业审稿编辑，负责审查章节的一致性和质量。

## 角色定位

你是 Polisher 而非 Creator，只标记问题不修改内容。severity="info" 的条目不影响 passed/overall_score，不要误报 critical。

## 审查维度

{dim_list}

## 输出格式（严格 JSON）

{{
  "passed": true/false,
  "overall_score": 0-100,
  "issues": [
    {{
      "severity": "critical|warning|info",
      "repair_scope": "local|structural|unknown",
      "category": "维度名称",
      "description": "具体问题描述",
      "suggestion": "修改建议"
    }}
  ],
  "summary": "总体评价一句话"
}}

passed 判定：有 critical 级别问题则为 false。

overall_score 评分标准：
- 95-100：无明显问题，可直接发布
- 85-94：有小问题但不影响阅读
- 75-84：有明显问题需要修订
- 65-74：存在严重问题必须重写
- < 65：质量不合格"""


def audit_chapter(
    client: LLMClient,
    genre: GenreProfile,
    state_mgr: StateManager,
    chapter: Chapter,
    memo: ChapterMemo,
) -> AuditResult:
    """审查一个章节."""
    current_state = state_mgr.read_story_file("current_state.md")
    hooks_md = state_mgr.read_story_file("hooks.md")

    # 加载最近章节用于疲劳检测
    all_chapters = [ch.content for ch in _load_recent_chapters(state_mgr, chapter.chapter_number, 3)]
    all_chapters.append(chapter.content)
    summaries = state_mgr.load_summaries()
    summaries_dicts = [s.model_dump() for s in summaries]
    titles = [s.title for s in summaries]

    fatigue_issues = run_fatigue_checks(all_chapters, summaries_dicts, titles)

    # LLM 审查
    system_prompt = build_auditor_system_prompt(genre)

    user_prompt = f"""请审查第{chapter.chapter_number}章。

## 当前状态
{current_state[:2000]}

## 伏笔池
{hooks_md[:1500]}

## Chapter Memo
目标: {memo.goal}
兑现: {memo.pay_off}
禁忌: {'、'.join(memo.must_avoid) if memo.must_avoid else '无'}

## 章节内容
{chapter.content[:4000]}

请输出 JSON 格式审查结果。"""

    # 黄金三章专项检查
    if chapter.chapter_number <= 3 and genre.golden_three_config:
        gt_prompt = _build_golden_three_audit_prompt(
            chapter.chapter_number, chapter.content, genre.golden_three_config
        )
        if gt_prompt:
            user_prompt += gt_prompt

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = client.chat_json(messages, temperature=0.3)
    parsed = result.get("parsed", {})

    if not parsed:
        return AuditResult(
            passed=False,
            parse_failed=True,
            issues=[AuditIssue(
                severity="critical",
                category="解析失败",
                description="LLM 返回了无法解析的 JSON",
                suggestion="请重新运行审查或检查 LLM 配置",
            )],
            summary="审查解析失败",
        )

    issues = []
    for i in parsed.get("issues", []):
        issues.append(AuditIssue(
            severity=i.get("severity", "warning"),
            category=i.get("category", "未知"),
            description=i.get("description", ""),
            suggestion=i.get("suggestion", ""),
            repair_scope=i.get("repair_scope"),
        ))

    # 合并疲劳检测结果
    for fi in fatigue_issues:
        issues.append(AuditIssue(
            severity="warning",
            category=fi.get("type", "疲劳检测"),
            description=fi.get("description", ""),
            suggestion=fi.get("suggestion", ""),
            repair_scope="local",
        ))

    return AuditResult(
        passed=parsed.get("passed", len([i for i in issues if i.severity == "critical"]) == 0),
        overall_score=parsed.get("overall_score"),
        issues=issues,
        summary=parsed.get("summary", ""),
    )


def audit_and_revise(
    client: LLMClient,
    genre: GenreProfile,
    state_mgr: StateManager,
    chapter: Chapter,
    memo: ChapterMemo,
    max_retries: int = 3,
) -> tuple[Chapter, list[AuditResult]]:
    """审计 + 自动重写循环：审计 → 不合格 → 重写 → 再审计，直到通过或达到上限.

    Returns:
        (最终章节, 所有审计结果列表)
    """
    audit_history: list[AuditResult] = []

    for attempt in range(max_retries + 1):
        audit = audit_chapter(
            client=client,
            genre=genre,
            state_mgr=state_mgr,
            chapter=chapter,
            memo=memo,
        )
        audit_history.append(audit)

        chapter.audit_score = audit.overall_score
        chapter.audit_issues = [i.model_dump() for i in audit.issues]

        if audit.passed:
            break

        if attempt < max_retries:
            chapter = revise_chapter(
                client=client,
                genre=genre,
                chapter=chapter,
                audit=audit,
                memo=memo,
            )

    return chapter, audit_history


def _load_recent_chapters(state_mgr: StateManager, current: int, count: int) -> list[Chapter]:
    """加载最近 N 章."""
    chapters = []
    chapters_dir = state_mgr.book_dir / "chapters"
    for cn in range(max(1, current - count), current):
        # 章节保存在 volXX/ 子目录下，需要遍历查找
        found = False
        if chapters_dir.exists():
            for vol_dir in sorted(chapters_dir.glob("vol*")):
                path = vol_dir / f"{cn:04d}.md"
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        chapters.append(Chapter(
                            book_id=state_mgr.book_dir.name,
                            chapter_number=cn,
                            content=f.read(),
                        ))
                    found = True
                    break
        # 回退：扁平目录
        if not found:
            path = chapters_dir / f"{cn:04d}.md"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    chapters.append(Chapter(
                        book_id=state_mgr.book_dir.name,
                        chapter_number=cn,
                        content=f.read(),
                    ))
    return chapters
