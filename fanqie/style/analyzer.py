"""文风分析器 — 纯文本统计分析，无需 LLM."""

from __future__ import annotations

import re
import math
from .profile import StyleProfile

# 中文修辞模式
_RHETORICAL_ZH = [
    ("比喻(像/如/仿佛)", re.compile(r"[像如仿佛似](?:是|同|一样|一般)")),
    ("反问", re.compile(r"难道|怎么可能|岂不|何尝不")),
    ("夸张", re.compile(r"天崩地裂|惊天动地|翻天覆地|震耳欲聋")),
    ("拟人", re.compile(r"[风雨雪月花树草石](?:在|像|仿佛).*?(?:笑|哭|叫|唱|叹|怒|舞)")),
    ("短句节奏", re.compile(r"[。！？][^。！？]{1,8}[。！？]")),
]


def analyze_style(text: str, source_name: str | None = None) -> StyleProfile:
    """分析参考文本，提取文风指纹."""
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

    return StyleProfile(
        avg_sentence_length=round(avg_sent, 1),
        sentence_length_stddev=round(sent_std, 1),
        avg_paragraph_length=avg_para,
        paragraph_length_range=para_range,
        vocabulary_diversity=round(vocab_div, 3),
        top_patterns=top_patterns,
        rhetorical_features=rhetorical,
        source_name=source_name,
    )
