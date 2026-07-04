"""核心数据模型 — Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Book
# ---------------------------------------------------------------------------

class BookStatus(str, Enum):
    DRAFT = "draft"
    OUTLINING = "outlining"
    READY = "ready"
    WRITING = "writing"
    PAUSED = "paused"
    COMPLETED = "completed"


class BookConfig(BaseModel):
    """一本书的完整配置."""
    id: str = Field(description="书籍唯一 ID")
    title: str = Field(description="书名")
    genre_id: str = Field(description="题材模板 ID")
    platform: str = Field(default="番茄小说")
    chapter_word_count: int = Field(default=2000)
    target_chapters: int = Field(default=500)
    status: BookStatus = Field(default=BookStatus.DRAFT)
    style_profile_path: Optional[str] = Field(default=None)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Chapter
# ---------------------------------------------------------------------------

class ChapterStatus(str, Enum):
    DRAFT = "draft"
    AUDITED = "audited"
    REVISED = "revised"
    APPROVED = "approved"


class Chapter(BaseModel):
    """一个章节."""
    book_id: str
    chapter_number: int
    title: str = ""
    content: str = ""
    word_count: int = 0
    status: ChapterStatus = Field(default=ChapterStatus.DRAFT)
    audit_score: Optional[int] = Field(default=None)
    audit_issues: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Character
# ---------------------------------------------------------------------------

class Character(BaseModel):
    """角色."""
    id: str
    book_id: str
    name: str
    role: str = Field(description="protagonist / antagonist / ally / supporting")
    tags: list[str] = Field(default_factory=list)
    contrast: str = Field(default="")
    voice: str = Field(default="")
    personality: str = Field(default="")
    motivation: str = Field(default="")
    current_goal: str = Field(default="")
    relationships: dict[str, str] = Field(default_factory=dict)
    known_info: list[str] = Field(default_factory=list)
    unknown_info: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Hook (伏笔)
# ---------------------------------------------------------------------------

class HookStatus(str, Enum):
    PLANTED = "planted"
    PROGRESSING = "progressing"
    PRESSURED = "pressured"
    NEAR_PAYOFF = "near_payoff"
    RESOLVED = "resolved"
    DEFERRED = "deferred"


class HookPayoffTiming(str, Enum):
    IMMEDIATE = "immediate"
    NEAR_TERM = "near_term"
    MID_ARC = "mid_arc"
    SLOW_BURN = "slow_burn"
    ENDGAME = "endgame"


class HookLevel(str, Enum):
    """伏笔层级."""
    CORE = "core"       # 核心伏笔：跨越多卷，5-8 个
    VOLUME = "volume"   # 卷级伏笔：卷内回收，每卷 8-15 个
    CHAPTER = "chapter" # 章级钩子：1-5 章内回收


class Hook(BaseModel):
    """一个伏笔."""
    hook_id: str
    book_id: str
    start_chapter: int
    last_advanced_chapter: int = 0
    type: str = ""
    status: HookStatus = Field(default=HookStatus.PLANTED)
    expected_payoff: str = ""
    payoff_timing: HookPayoffTiming = Field(default=HookPayoffTiming.MID_ARC)
    notes: str = ""
    seed_text: str = ""
    depends_on: list[str] = Field(default_factory=list)
    core_hook: bool = False
    promoted: bool = False
    advanced_count: int = 0
    target_resolution_chapter: Optional[int] = Field(default=None, description="完结计划中分配的目标回收章节")
    hook_level: HookLevel = Field(default=HookLevel.CORE, description="伏笔层级：core/volume/chapter")
    volume_number: Optional[int] = Field(default=None, description="所属卷号（卷级伏笔）")


# ---------------------------------------------------------------------------
# Chapter Summary
# ---------------------------------------------------------------------------

class ChapterSummary(BaseModel):
    """章节摘要表."""
    chapter: int
    title: str
    characters: str = ""
    events: str = ""
    state_changes: str = ""
    hook_activity: str = ""
    mood: str = ""
    chapter_type: str = ""


# ---------------------------------------------------------------------------
# Runtime State
# ---------------------------------------------------------------------------

class Fact(BaseModel):
    """一个结构化事实."""
    subject: str
    predicate: str
    object: str
    valid_from_chapter: int
    valid_until_chapter: Optional[int] = None
    source_chapter: int


class CurrentState(BaseModel):
    """当前状态快照."""
    book_id: str
    chapter_number: int
    facts: list[Fact] = Field(default_factory=list)
    current_conflict: str = ""
    current_goal: str = ""
    protagonist_state: str = ""
    current_location: str = ""
    current_constraint: str = ""
    current_alliances: str = ""


class HookPool(BaseModel):
    """伏笔池."""
    book_id: str
    hooks: list[Hook] = Field(default_factory=list)


class ChapterMemo(BaseModel):
    """每章写作前的结构化指令（7段）."""
    book_id: str
    chapter_number: int
    goal: str = ""
    reader_waiting_for: str = ""
    pay_off: str = ""
    keep_hidden: str = ""
    transition_duty: str = ""
    key_choice_check: str = ""
    end_changes: str = ""
    hook_ledger: str = ""
    must_avoid: list[str] = Field(default_factory=list)
    style_emphasis: list[str] = Field(default_factory=list)
    body: str = ""
    # 完结相关
    is_completion_arc: bool = Field(default=False, description="是否处于完结窗口")
    is_final: bool = Field(default=False, description="是否为最后一章")
    hooks_to_resolve: list[str] = Field(default_factory=list, description="本章需要回收的伏笔ID列表")
    hooks_to_advance: list[str] = Field(default_factory=list, description="本章需要推进（非回收）的伏笔ID列表")
    pacing: str = Field(default="", description="本章节奏配方：张力曲线与爽点节拍建议")


# ---------------------------------------------------------------------------
# Context Package
# ---------------------------------------------------------------------------

class ContextEntry(BaseModel):
    """一条上下文条目."""
    source: str
    reason: str = ""
    excerpt: str = ""
    is_protected: bool = False


class ContextPackage(BaseModel):
    """组装好的上下文包."""
    book_id: str
    chapter_number: int
    selected_context: list[ContextEntry] = Field(default_factory=list)
    protected_tokens: int = 0
    compressible_tokens: int = 0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditIssue(BaseModel):
    """审查发现的问题."""
    severity: str
    category: str
    description: str
    suggestion: str
    repair_scope: Optional[str] = None


class AuditResult(BaseModel):
    """审查结果."""
    passed: bool
    overall_score: Optional[int] = Field(default=None, ge=0, le=100)
    issues: list[AuditIssue] = Field(default_factory=list)
    summary: str = ""
    parse_failed: bool = False


# ---------------------------------------------------------------------------
# Foundation 相关模型
# ---------------------------------------------------------------------------

class WorldSetting(BaseModel):
    """世界观 6 要素."""
    power_system: str = Field(default="", description="力量体系：等级划分、突破条件、战力参照")
    geography: str = Field(default="", description="地理：关键区域、势力分布、资源产地")
    history: str = Field(default="", description="历史：关键纪元、上古事件、当前时代背景")
    drive: str = Field(default="", description="世界前进的动力：所有人为何而行动")
    factions: str = Field(default="", description="势力格局：主要势力、势力间关系、权力真空")
    resources: str = Field(default="", description="资源分配与权力循环：谁掌控资源、如何流转、权力更替机制")
    extra_modules: dict[str, str] = Field(default_factory=dict, description="题材独有的额外模块")


class CascadeRule(BaseModel):
    """链式反应规则."""
    setting: str = Field(description="核心设定")
    consequence_1: str = Field(description="第一层后果")
    consequence_2: str = Field(description="第二层社会变化")
    consequence_3: str = Field(description="第三层新矛盾")


class CascadeRules(BaseModel):
    """链式反应集合."""
    book_id: str
    rules: list[CascadeRule] = Field(default_factory=list)


class CivilizationNorm(BaseModel):
    """文明共识."""
    norm: str = Field(description="世界默认行为准则")
    derivation: str = Field(description="从哪个设定推导而来")


class CivilizationNorms(BaseModel):
    """文明共识集合."""
    book_id: str
    norms: list[CivilizationNorm] = Field(default_factory=list)


class ProtagonistProfile(BaseModel):
    """主角设定（5 维度）."""
    identity: str = Field(default="", description="表面身份 + 隐藏身世 + 社会阶层轨迹")
    motivation: str = Field(default="", description="近期/中期/长期三层递进动机")
    personality: str = Field(default="", description="核心特质 + 致命缺陷 + 内在冲突")
    arc: str = Field(default="", description="按卷规划角色蜕变节点")
    golden_finger: str = Field(default="", description="金手指：能力说明 + 限制条件 + 成长路径 + 为什么不崩平衡")


class SupportingCharacter(BaseModel):
    """核心配角."""
    name: str
    role: str = Field(description="盟友/对手/灰色地带")
    background: str = ""
    motivation: str = Field(description="独立于主角的自身诉求")
    complement_dimension: str = Field(description="与主角的互补/对立维度")
    fate: str = Field(description="命运走向：哪卷退场/转变/黑化")


class CoreConflict(BaseModel):
    """核心冲突线."""
    protagonist_vs_world: str = Field(default="", description="主角 vs 世界的根本矛盾")
    protagonist_vs_antagonist: str = Field(default="", description="主角 vs 反派的核心对立")
    protagonist_inner: str = Field(default="", description="主角内在冲突")


class Foundation(BaseModel):
    """完整 Foundation."""
    book_id: str
    world_setting: WorldSetting = Field(default_factory=WorldSetting)
    cascade_rules: CascadeRules = Field(default_factory=lambda: CascadeRules(book_id=""))
    civilization_norms: CivilizationNorms = Field(default_factory=lambda: CivilizationNorms(book_id=""))
    protagonist: ProtagonistProfile = Field(default_factory=ProtagonistProfile)
    supporting_characters: list[SupportingCharacter] = Field(default_factory=list)
    core_conflict: CoreConflict = Field(default_factory=CoreConflict)


# ---------------------------------------------------------------------------
# Volume 相关模型
# ---------------------------------------------------------------------------

class Volume(BaseModel):
    """单卷规划."""
    volume_number: int
    chapter_range: str = Field(description="章节范围，如 '1-50'")
    main_goal: str = Field(description="本卷主线目标")
    climax: str = Field(description="高潮节点")
    key_turns: list[str] = Field(default_factory=list, description="关键转折")
    hook_plan: list[str] = Field(default_factory=list, description="伏笔播种/回收计划")
    pacing: str = Field(description="节奏规划")
    norm_breaks: list[str] = Field(default_factory=list, description="打破文明共识的节点")


class VolumePlan(BaseModel):
    """卷纲规划."""
    book_id: str
    volumes: list[Volume] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Brief 相关模型
# ---------------------------------------------------------------------------

class BriefScore(BaseModel):
    """Brief 评分."""
    genre_fit: int = Field(default=0, ge=0, le=30, description="题材契合度")
    satisfaction_potential: int = Field(default=0, ge=0, le=25, description="爽点潜力")
    executability: int = Field(default=0, ge=0, le=20, description="可执行性")
    completeness: int = Field(default=0, ge=0, le=15, description="完整性")
    differentiation: int = Field(default=0, ge=0, le=10, description="差异化")

    @property
    def total(self) -> int:
        return self.genre_fit + self.satisfaction_potential + self.executability + self.completeness + self.differentiation

    @property
    def verdict(self) -> str:
        if self.total >= 70:
            return "可执行"
        elif self.total >= 50:
            return "建议优化后使用"
        else:
            return "建议重写"


class BriefReport(BaseModel):
    """Brief 优化报告."""
    book_id: str
    original_brief: str = ""
    optimized_brief: str = ""
    score: BriefScore = Field(default_factory=BriefScore)
    suggestions: list[str] = Field(default_factory=list)
    missing_elements: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Advise 相关模型
# ---------------------------------------------------------------------------

class ImpactEntry(BaseModel):
    """波及影响条目."""
    file: str = Field(description="受影响的文件")
    reason: str = Field(description="为什么受影响")
    suggested_change: str = Field(description="建议修改内容")
    severity: str = Field(default="moderate", description="影响程度: critical/major/moderate/minor")


class ImpactReport(BaseModel):
    """波及分析报告."""
    book_id: str
    change_request: str = Field(description="用户修改请求")
    affected_nodes: list[str] = Field(default_factory=list, description="受影响的级联节点")
    impacts: list[ImpactEntry] = Field(default_factory=list)
    summary: str = ""


class AdvisePlan(BaseModel):
    """Advise 执行计划."""
    book_id: str
    impact_report: ImpactReport = Field(default_factory=lambda: ImpactReport(book_id=""))
    modifications: list[dict] = Field(default_factory=list)
    log_entry: str = ""


# ---------------------------------------------------------------------------
# Completion 相关模型
# ---------------------------------------------------------------------------

class HookScheduleEntry(BaseModel):
    """伏笔回收排期条目."""
    hook_id: str
    hook_type: str = ""
    target_chapter: int
    status: str = "pending"  # pending / resolved / deferred
    resolved_in_chapter: Optional[int] = None


class CompletionPlan(BaseModel):
    """完结计划."""
    book_id: str
    completion_window_start: int = Field(description="完结窗口起始章")
    completion_window_end: int = Field(description="完结窗口结束章（目标总章数）")
    remaining_chapters: int = Field(description="剩余章节数")
    total_unresolved_hooks: int = Field(description="未回收伏笔总数")
    hook_schedule: list[HookScheduleEntry] = Field(default_factory=list, description="伏笔回收排期")
    arc_phases: str = Field(default="", description="收尾弧线阶段划分")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class CharacterEnding(BaseModel):
    """角色归宿."""
    name: str
    role: str = ""
    ending: str = ""
    arc_summary: str = ""


class CompletionReport(BaseModel):
    """完结报告."""
    book_id: str
    book_title: str = ""
    total_chapters: int = 0
    total_words: int = 0
    hooks_resolved: int = 0
    hooks_total: int = 0
    summary: str = Field(default="", description="全书摘要")
    character_endings: list[CharacterEnding] = Field(default_factory=list, description="角色归宿")
    theme_review: str = Field(default="", description="主题回顾")
    completed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# 黄金三章
# ---------------------------------------------------------------------------

class GoldenThreeConfig(BaseModel):
    """黄金三章配置."""
    chapter_1_structure: str = ""
    chapter_1_rules: list[str] = Field(default_factory=list)
    chapter_2_structure: str = ""
    chapter_2_rules: list[str] = Field(default_factory=list)
    chapter_3_structure: str = ""
    chapter_3_rules: list[str] = Field(default_factory=list)
