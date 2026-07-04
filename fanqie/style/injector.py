"""文风指纹注入器 — 将 StyleProfile 渲染为 prompt 片段."""

from __future__ import annotations

from .profile import StyleProfile


def render_style_fingerprint(profile: StyleProfile) -> str:
    """将文风指纹渲染为可注入 system prompt 的文本."""
    lines = ["## 文风指纹（模仿目标）", ""]

    if profile.source_name:
        lines.append(f"参考来源：{profile.source_name}")
        lines.append("")

    lines.append("以下是从参考文本中提取的写作风格特征。你的输出必须尽量贴合这些特征：")
    lines.append("")

    # 句长
    lines.append(
        f"- 平均句长：{profile.avg_sentence_length} 字，"
        f"标准差 {profile.sentence_length_stddev}"
        f"（句子长短交替，有呼吸感）"
    )

    # 段长
    pmin, pmax = profile.paragraph_length_range
    lines.append(
        f"- 平均段长：{profile.avg_paragraph_length} 字，"
        f"范围 {pmin}-{pmax} 字（适合手机阅读的段落节奏）"
    )

    # 词汇多样性
    diversity_desc = "偏高，用词丰富" if profile.vocabulary_diversity > 0.25 else "中等，避免重复用词"
    lines.append(
        f"- 词汇多样性：{profile.vocabulary_diversity}"
        f"（{diversity_desc}）"
    )

    # 高频开头模式
    if profile.top_patterns:
        lines.append(f"- 高频开头模式：{'、'.join(profile.top_patterns)}")

    # 修辞特征
    if profile.rhetorical_features:
        lines.append(f"- 修辞特征：{'、'.join(profile.rhetorical_features)}")

    lines.append("")
    lines.append("写作时注意：")
    lines.append("- 句子长短交替，避免连续 3 句以上等长")
    lines.append("- 段落控制在 3-5 行手机屏幕内")
    if profile.top_patterns:
        lines.append("- 主动避开高频开头模式的机械重复")
    if profile.rhetorical_features:
        lines.append("- 保持与参考文本相近的修辞密度")

    return "\n".join(lines)


def inject_style_fingerprint(
    system_prompt: str,
    profile: StyleProfile | None,
) -> str:
    """将文风指纹注入 system prompt."""
    if profile is None:
        return system_prompt

    fingerprint = render_style_fingerprint(profile)
    return system_prompt + "\n\n" + fingerprint
