"""伏笔策略 — 回收压力计算、stale/overdue 判定."""

from __future__ import annotations

from enum import Enum


class HookPhase(str, Enum):
    OPENING = "opening"
    MIDDLE = "middle"
    LATE = "late"


PHASE_THRESHOLDS = {
    "late_progress": 0.75,
    "middle_progress": 0.30,
    "late_chapter": 200,
    "middle_chapter": 50,
}

PHASE_WEIGHT = {
    HookPhase.OPENING: 0,
    HookPhase.MIDDLE: 1,
    HookPhase.LATE: 2,
}

TIMING_PROFILES = {
    "immediate": {
        "minimum_phase": HookPhase.OPENING,
        "overdue_age": 5,
        "stale_dormancy": 3,
        "earliest_resolve_age": 2,
        "resolve_bias": 3,
    },
    "near_term": {
        "minimum_phase": HookPhase.OPENING,
        "overdue_age": 10,
        "stale_dormancy": 5,
        "earliest_resolve_age": 3,
        "resolve_bias": 2,
    },
    "mid_arc": {
        "minimum_phase": HookPhase.MIDDLE,
        "overdue_age": 20,
        "stale_dormancy": 10,
        "earliest_resolve_age": 8,
        "resolve_bias": 1,
    },
    "slow_burn": {
        "minimum_phase": HookPhase.MIDDLE,
        "overdue_age": 40,
        "stale_dormancy": 20,
        "earliest_resolve_age": 15,
        "resolve_bias": 1,
    },
    "endgame": {
        "minimum_phase": HookPhase.LATE,
        "overdue_age": 60,
        "stale_dormancy": 30,
        "earliest_resolve_age": 30,
        "resolve_bias": 2,
    },
}

PRESSURE_WEIGHTS = {
    "stale_advance_bonus": 10,
    "overdue_advance_bonus": 20,
    "resolve_bias_multiplier": 5,
    "progressing_resolve_bonus": 15,
    "max_dormancy_resolve_bonus": 30,
    "dormancy_resolve_multiplier": 2,
}

ACTIVITY_THRESHOLDS = {
    "recently_touched_dormancy": 3,
}


def resolve_hook_phase(chapter_number: int, target_chapters: int | None = None) -> HookPhase:
    if target_chapters and target_chapters > 0:
        progress = chapter_number / target_chapters
        if progress >= PHASE_THRESHOLDS["late_progress"]:
            return HookPhase.LATE
        if progress >= PHASE_THRESHOLDS["middle_progress"]:
            return HookPhase.MIDDLE
        return HookPhase.OPENING

    if chapter_number >= PHASE_THRESHOLDS["late_chapter"]:
        return HookPhase.LATE
    if chapter_number >= PHASE_THRESHOLDS["middle_chapter"]:
        return HookPhase.MIDDLE
    return HookPhase.OPENING


def describe_hook_lifecycle(
    payoff_timing: str,
    start_chapter: int,
    last_advanced_chapter: int,
    status: str,
    chapter_number: int,
    target_chapters: int | None = None,
) -> dict:
    profile = TIMING_PROFILES.get(payoff_timing, TIMING_PROFILES["mid_arc"])
    phase = resolve_hook_phase(chapter_number, target_chapters)

    age = max(0, chapter_number - max(1, start_chapter))
    last_touch = max(start_chapter, last_advanced_chapter)
    dormancy = max(0, chapter_number - max(1, last_touch))

    is_progressing = status in ("progressing", "pressured", "near_payoff")
    phase_ready = PHASE_WEIGHT[phase] >= PHASE_WEIGHT[profile["minimum_phase"]]
    recently_touched = dormancy <= ACTIVITY_THRESHOLDS["recently_touched_dormancy"]
    overdue = phase_ready and age >= profile["overdue_age"]
    momentum = is_progressing or recently_touched

    stale = phase_ready and (
        dormancy >= profile["stale_dormancy"]
        or (overdue and not momentum)
    )

    cadence_ready = True
    if payoff_timing == "slow_burn":
        cadence_ready = phase == HookPhase.LATE or overdue
    elif payoff_timing == "endgame":
        cadence_ready = phase == HookPhase.LATE

    ready_to_resolve = (
        phase_ready
        and cadence_ready
        and age >= profile["earliest_resolve_age"]
        and (momentum or (overdue and is_progressing))
    )

    return {
        "timing": payoff_timing,
        "phase": phase.value,
        "age": age,
        "dormancy": dormancy,
        "ready_to_resolve": ready_to_resolve,
        "stale": stale,
        "overdue": overdue,
        "advance_pressure": (
            age + dormancy
            + (PRESSURE_WEIGHTS["stale_advance_bonus"] if stale else 0)
            + (PRESSURE_WEIGHTS["overdue_advance_bonus"] if overdue else 0)
        ),
        "resolve_pressure": (
            (profile["resolve_bias"] * PRESSURE_WEIGHTS["resolve_bias_multiplier"]
             + (PRESSURE_WEIGHTS["progressing_resolve_bonus"] if is_progressing else 0)
             + min(PRESSURE_WEIGHTS["max_dormancy_resolve_bonus"],
                   dormancy * PRESSURE_WEIGHTS["dormancy_resolve_multiplier"])
             + (PRESSURE_WEIGHTS["overdue_advance_bonus"] if overdue else 0))
            if ready_to_resolve else 0
        ),
    }
