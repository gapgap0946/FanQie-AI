"""长跨度疲劳检测 — 开头/结尾模式重复、标题塌缩、情绪单调."""

from __future__ import annotations

import re
from collections import Counter


def _dice_coefficient(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if len(a) < 2 or len(b) < 2:
        return 0.0

    def _bigrams(s: str) -> Counter:
        return Counter(s[i:i+2] for i in range(len(s)-1))

    ba = _bigrams(a)
    bb = _bigrams(b)
    overlap = sum(min(ba[k], bb[k]) for k in ba if k in bb)
    total = sum(ba.values()) + sum(bb.values())
    return (2 * overlap) / total if total > 0 else 0.0


def _extract_boundary_sentence(text: str, boundary: str = "opening") -> str | None:
    flattened = " ".join(
        line.strip() for line in text.split("\n")
        if line.strip() and not line.strip().startswith("#")
    )
    sentences = re.split(r"(?<=[。！？!?])\s+", flattened)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return None
    return sentences[0] if boundary == "opening" else sentences[-1]


def _normalize_sentence(s: str) -> str:
    return re.sub(r"[，。！？、：；""''（）【】《》\s\-—…]+", "", s).lower()


def detect_opening_pattern_repeat(chapters: list[str]) -> dict | None:
    if len(chapters) < 3:
        return None
    recent = chapters[-3:]
    openings = [_extract_boundary_sentence(ch, "opening") for ch in recent]
    if any(o is None for o in openings):
        return None
    norm = [_normalize_sentence(o) for o in openings]
    if any(len(n) < 4 for n in norm):
        return None
    sim01 = _dice_coefficient(norm[0], norm[1])
    sim12 = _dice_coefficient(norm[1], norm[2])
    if min(sim01, sim12) < 0.4:
        return None
    return {
        "type": "opening_pattern_repeat",
        "description": f"最近3章开头句式高度相似（相似度 {sim01:.2f}/{sim12:.2f}），容易形成模板化开篇。",
        "suggestion": "下一章换一个开篇入口，用动作、后果或异常信息切入。",
    }


def detect_ending_pattern_repeat(chapters: list[str]) -> dict | None:
    if len(chapters) < 3:
        return None
    recent = chapters[-3:]
    endings = [_extract_boundary_sentence(ch, "ending") for ch in recent]
    if any(e is None for e in endings):
        return None
    norm = [_normalize_sentence(e) for e in endings]
    if any(len(n) < 4 for n in norm):
        return None
    sim01 = _dice_coefficient(norm[0], norm[1])
    sim12 = _dice_coefficient(norm[1], norm[2])
    if min(sim01, sim12) < 0.4:
        return None
    return {
        "type": "ending_pattern_repeat",
        "description": f"最近3章结尾句式高度相似（相似度 {sim01:.2f}/{sim12:.2f}），容易形成模板化章尾。",
        "suggestion": "下一章换一个收束方式，用行动后果、角色决断或新变量落板。",
    }


def detect_title_collapse(titles: list[str]) -> dict | None:
    if len(titles) < 5:
        return None
    recent = titles[-5:]
    all_terms: Counter = Counter()
    for t in recent:
        terms = re.findall(r"[\u4e00-\u9fff]{2,3}", t)
        for term in terms:
            all_terms[term] += 1
    if not all_terms:
        return None
    top_term, count = all_terms.most_common(1)[0]
    if count < 3:
        return None
    return {
        "type": "title_collapse",
        "description": f"最近标题持续围绕{top_term}命名（命中{count}次），命名开始塌缩。",
        "suggestion": "下一章标题换一个新的意象、动作、后果或人物焦点。",
    }


def detect_mood_monotony(summaries: list[dict]) -> dict | None:
    if len(summaries) < 5:
        return None
    recent = summaries[-5:]
    moods = [s.get("mood", "") for s in recent]
    high_tension = {"紧张", "恐惧", "愤怒", "绝望", "高压", "激烈"}
    streak = 0
    for m in moods:
        if any(ht in m for ht in high_tension):
            streak += 1
        else:
            streak = 0
    if streak >= 5:
        return {
            "type": "mood_monotony",
            "description": f"连续{streak}章持续高张力，缺乏明显的情绪释放。",
            "suggestion": "下一章安排一次喘息、温情、幽默或静场释放，再继续加压。",
        }
    return None


def detect_chapter_type_monotony(summaries: list[dict]) -> dict | None:
    if len(summaries) < 5:
        return None
    recent = summaries[-5:]
    types = [s.get("chapter_type", "") for s in recent]
    counter = Counter(types)
    top_type, count = counter.most_common(1)[0]
    if count >= 4:
        return {
            "type": "chapter_type_monotony",
            "description": f"最近{len(recent)}章中{count}章类型为{top_type}，长篇章节节奏可能开始固化。",
            "suggestion": "下一章应切换章节功能，不要连续重复同一种布局/推进节拍。",
        }
    return None


def run_fatigue_checks(
    chapters: list[str],
    summaries: list[dict],
    titles: list[str],
) -> list[dict]:
    issues = []
    for check in [
        lambda: detect_opening_pattern_repeat(chapters),
        lambda: detect_ending_pattern_repeat(chapters),
        lambda: detect_title_collapse(titles),
        lambda: detect_mood_monotony(summaries),
        lambda: detect_chapter_type_monotony(summaries),
    ]:
        result = check()
        if result:
            issues.append(result)
    return issues
