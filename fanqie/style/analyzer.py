"""文风分析器 — 统计分析 + 可选 LLM 深度理解."""

from __future__ import annotations

import re
import math
import json
from .profile import StyleProfile

# 中文修辞模式
_RHETORICAL_ZH = [
    ("比喻(像/如/仿佛)", re.compile(r"[像如仿佛似](?:是|同|一样|一般)")),
    ("反问", re.compile(r"难道|怎么可能|岂不|何尝不")),
    ("夸张", re.compile(r"天崩地裂|惊天动地|翻天覆地|震耳欲聋")),
    ("拟人", re.compile(r"[风雨雪月花树草石](?:在|像|仿佛).*?(?:笑|哭|叫|唱|叹|怒|舞)")),
    ("短句节奏", re.compile(r"[。！？][^。！？]{1,8}[。！？]")),
]


def analyze_style(text: str, source_name: str | None = None, client=None) -> StyleProfile:
    """分析参考文本，提取文风指纹.

    client 为可选的 LLMClient；提供时会额外做一次 LLM 深度分析，
    提炼语气/人称/节奏/句式/意象等高层笔触特征。
    """
    # 分句
    sentences = [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]
    # 分段
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    def _char_len(s: str) -> int:
        return len(s.replace(" ", ""))

    # 句长统计
    sent_lens = [_char_len(s) for s in sentences]
    avg_sent = sum(sent_lens) / len(sent_lens) if sent_lens else 0
    sent_std = math.sqrt(sum((l - avg_sent) ** 2 for l in sent_lens) / len(sent_lens)) if len(sent_lens) > 1 else 0

    # 段长统计
    para_lens = [_char_len(p) for p in paragraphs]
    avg_para = int(sum(para_lens) / len(para_lens)) if para_lens else 0
    para_range = (min(para_lens), max(para_lens)) if para_lens else (0, 0)

    # 词汇多样性 (TTR)
    chars = re.sub(r"[\s\n\r，。！？、：；""''（）【】《》\-\d]", "", text)
    vocab_div = len(set(chars)) / len(chars) if chars else 0

    # 高频开头模式（句首2字）
    opening_counts: dict[str, int] = {}
    for s in sentences:
        key = s[:2] if len(s) >= 2 else s
        if key:
            opening_counts[key] = opening_counts.get(key, 0) + 1
    top_patterns = [
        f"{p}({c}次)" for p, c in
        sorted(opening_counts.items(), key=lambda x: -x[1])[:5]
        if c >= 3
    ]

    # 修辞特征
    rhetorical = []
    for name, pattern in _RHETORICAL_ZH:
        matches = pattern.findall(text)
        if len(matches) >= 2:
            rhetorical.append(f"{name}({len(matches)}处)")

    profile = StyleProfile(
        avg_sentence_length=round(avg_sent, 1),
        sentence_length_stddev=round(sent_std, 1),
        avg_paragraph_length=avg_para,
        paragraph_length_range=para_range,
        vocabulary_diversity=round(vocab_div, 3),
        top_patterns=top_patterns,
        rhetorical_features=rhetorical,
        source_name=source_name,
    )

    # LLM 深度分析（可选）
    if client is not None:
        try:
            _apply_llm_analysis(profile, text, client)
        except Exception:
            pass

    return profile


def _apply_llm_analysis(profile: StyleProfile, text: str, client) -> None:
    """调用 LLM 提炼高层文风特征，写回 profile."""
    sample = text[:4000]
    system_prompt = (
        "你是资深文学编辑，擅长分析作者的写作风格。请阅读给定的文本片段，"
        "提炼其文风特征。只输出 JSON，不要任何多余说明。"
    )
    user_prompt = f"""请分析以下文本的写作风格，输出 JSON，字段如下：
{{
  "tone": "整体语气与情绪基调（如：冷峻克制/热血张扬/诙谐轻快），一句话",
  "narrative_pov": "叙事人称与视角（如：第三人称限知视角）",
  "pacing": "叙事节奏特点（如：快节奏，多短句推进；或舒缓，重铺陈）",
  "sentence_habits": "句式偏好与习惯（如：偏爱短句+破折号，动词密集）",
  "imagery": ["常用意象或词汇色彩，3-6个关键词"],
  "style_summary": "一句话概括这个作者的文风",
  "writing_tips": ["若要模仿此文风，需要遵循的3-5条可执行要点"]
}}

文本片段：
{sample}"""

    result = client.chat_json([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], temperature=0.3)

    parsed = result.get("parsed") if isinstance(result, dict) else None
    if not isinstance(parsed, dict):
        return

    profile.tone = str(parsed.get("tone", "")).strip()
    profile.narrative_pov = str(parsed.get("narrative_pov", "")).strip()
    profile.pacing = str(parsed.get("pacing", "")).strip()
    profile.sentence_habits = str(parsed.get("sentence_habits", "")).strip()
    profile.style_summary = str(parsed.get("style_summary", "")).strip()
    imagery = parsed.get("imagery", [])
    if isinstance(imagery, list):
        profile.imagery = [str(x).strip() for x in imagery if str(x).strip()][:6]
    tips = parsed.get("writing_tips", [])
    if isinstance(tips, list):
        profile.writing_tips = [str(x).strip() for x in tips if str(x).strip()][:5]
