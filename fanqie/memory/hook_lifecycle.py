"""伏笔生命周期管理."""

from __future__ import annotations

from .hook_policy import describe_hook_lifecycle


def filter_active_hooks(hooks: list[dict]) -> list[dict]:
    """过滤出活跃伏笔（未回收、未延期、已升级）."""
    resolved_statuses = {"resolved", "closed", "done"}
    deferred_statuses = {"deferred", "paused", "hold", "dormant"}
    return [
        h for h in hooks
        if h.get("status", "") not in resolved_statuses
        and h.get("status", "") not in deferred_statuses
        and h.get("promoted", False)
    ]


def compute_recyclable_hooks(
    hooks: list[dict],
    chapter_number: int,
    target_chapters: int | None = None,
) -> list[dict]:
    """计算需要强制回收的伏笔（stale/overdue）."""
    active = filter_active_hooks(hooks)
    terminal = {"resolved", "closed", "done", "deferred", "paused", "hold"}

    def _silence(h: dict) -> int:
        last_touch = max(h.get("start_chapter", 0), h.get("last_advanced_chapter", 0))
        if last_touch <= 0:
            return chapter_number
        return max(0, chapter_number - last_touch)

    def _threshold(h: dict) -> int:
        status = h.get("status", "").lower()
        if any(kw in status for kw in ("pressured", "near_payoff", "progressing")):
            return 5
        if h.get("core_hook"):
            return 8
        return 10

    recyclable = []
    for h in active:
        if h.get("status", "") in terminal:
            continue
        silence = _silence(h)
        if silence >= _threshold(h):
            h["_silence"] = silence
            recyclable.append(h)

    recyclable.sort(key=lambda h: -h["_silence"])
    return recyclable


def get_hook_ledger_summary(
    hooks: list[dict],
    chapter_number: int,
    target_chapters: int | None = None,
) -> str:
    """生成伏笔账本摘要（用于 Chapter Memo 的 hook_ledger 段）."""
    active = filter_active_hooks(hooks)
    if not active:
        return "暂无活跃伏笔。"

    lines = ["## 本章 hook 账本", ""]
    for h in active:
        lifecycle = describe_hook_lifecycle(
            payoff_timing=h.get("payoff_timing", "mid_arc"),
            start_chapter=h.get("start_chapter", 0),
            last_advanced_chapter=h.get("last_advanced_chapter", 0),
            status=h.get("status", "planted"),
            chapter_number=chapter_number,
            target_chapters=target_chapters,
        )
        stale_mark = " [STALE]" if lifecycle["stale"] else ""
        overdue_mark = " [OVERDUE]" if lifecycle["overdue"] else ""
        core_mark = " [CORE]" if h.get("core_hook") else ""

        lines.append(
            f"- {h['hook_id']}{core_mark}{stale_mark}{overdue_mark}: "
            f"{h.get('type', '')} | 状态={h.get('status','planted')} | "
            f"沉默{lifecycle['dormancy']}章 | "
            f"推进压力={lifecycle['advance_pressure']} | "
            f"回收压力={lifecycle['resolve_pressure']}"
        )
        if h.get("expected_payoff"):
            lines.append(f"  预期回收: {h['expected_payoff']}")
        if h.get("seed_text"):
            lines.append(f"  种子文本: {h['seed_text'][:80]}...")

    return "\n".join(lines)
