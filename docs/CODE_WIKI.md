# fanqie 代码 Wiki

> 长篇网文 AI 创作引擎 —— 完整代码架构与模块说明文档

本文档基于对仓库源码的逐文件分析生成，用于帮助开发者快速理解 `fanqie` 项目的整体架构、模块职责、关键类与函数、依赖关系及运行方式。

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [目录结构](#3-目录结构)
4. [核心数据模型](#4-核心数据模型-models)
5. [模块职责详解](#5-模块职责详解)
   - [5.1 engine 引擎层](#51-engine-引擎层)
   - [5.2 memory 记忆层](#52-memory-记忆层)
   - [5.3 storage 存储层](#53-storage-存储层)
   - [5.4 llm 模型接入层](#54-llm-模型接入层)
   - [5.5 style 文风层](#55-style-文风层)
   - [5.6 genres 题材层](#56-genres-题材层)
   - [5.7 utils 配置层](#57-utils-配置层)
   - [5.8 cli 命令行入口](#58-cli-命令行入口)
   - [5.9 web 服务端与前端](#59-web-服务端与前端)
6. [核心写作流程（Pipeline）](#6-核心写作流程pipeline)
7. [依赖关系图](#7-依赖关系图)
8. [数据持久化设计](#8-数据持久化设计)
9. [运行方式](#9-运行方式)
10. [关键设计要点](#10-关键设计要点)

---

## 1. 项目概述

**fanqie（番茄）** 是一个专为百万字以上「爽文」网文设计的 AI 创作引擎。它借鉴 InkOS 的**防幻觉**与**长期记忆**架构，适配国产大模型（OpenAI 兼容协议），采用 SQLite + 本地文件双重存储。

| 属性 | 值 |
|------|-----|
| 项目名 | fanqie |
| 版本 | 0.1.0 |
| 语言 | Python ≥ 3.9 |
| 许可证 | MIT |
| 入口命令 | `fanqie`（Click CLI） |

### 核心能力

- **防幻觉**：Chapter Memo（7 段结构化指令）+ Continuity Auditor（20+ 维度审查）+ 自动修订。
- **长期记忆**：Protected/Compressible 分层上下文 + 伏笔生命周期管理 + 长跨度疲劳检测 + 故事圣经（Story Bible）。
- **题材模板**：6 个内置题材（玄幻、规则怪谈、全民穿越、克系修仙、末世、诡异降临），支持自定义 TOML 模板。
- **文风仿写**：纯文本统计分析（句长/段长/TTR/修辞），无需 LLM，结果注入 system prompt。

### 技术依赖

| 依赖 | 用途 |
|------|------|
| `click` | CLI 命令框架 |
| `rich` | 终端富文本渲染 |
| `pydantic` (v2) | 数据模型与校验 |
| `httpx` | LLM HTTP 调用 |
| `pyyaml` | 配置文件读写 |
| `tomli` / `tomllib` | 题材 TOML 解析 |

---

## 2. 整体架构

系统采用**单一编排中心 + 无状态阶段模块**的设计。`Orchestrator` 持有全部可变状态并串联各写作阶段，每个阶段模块（planner/composer/writer/settler/auditor/reviser 等）都是接收依赖注入的纯函数集合，便于测试与替换。

```
                    ┌─────────────────────────────────────────┐
                    │           CLI (cli/main.py)              │  ← 用户主入口
                    │        Web Server (web_server.py)        │  ← 薄壳，调 CLI 子进程
                    └────────────────────┬────────────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │        Orchestrator (编排中心)           │
                    │  Foundation → Volume Plan → 逐章写作循环 │
                    └────────────────────┬────────────────────┘
                                         │
          ┌──────────────┬──────────────┼──────────────┬──────────────┐
          ▼              ▼              ▼              ▼              ▼
      architect      planner        writer         settler        auditor
      (世界基石)    (ChapterMemo)   (章节正文)    (章后结算)      (审计+修订)
          │              │              │              │              │
          └──────────────┴──────────────┼──────────────┴──────────────┘
                                         │
          ┌──────────────┬──────────────┼──────────────┬──────────────┐
          ▼              ▼              ▼              ▼              ▼
       memory/        storage/         llm/          style/         genres/
   (状态·伏笔·      (SQLite CRUD)   (OpenAI 兼容    (文风分析     (TOML 题材
    上下文·圣经)                      客户端)        与注入)       模板)
```

### 写作主流程（六阶段）

```
Plan -> Compose -> Write -> Settle -> Audit -> Revise
  |        |         |        |        |        |
  |   Chapter Memo   |    状态更新    |   自动修订   |
  |   (7段结构)      |    伏笔推进    |   (最多N次)  |
  +------------------+---------------+--------------+
```

---

## 3. 目录结构

```
fanqie/
├── models.py                    # Pydantic 数据模型（全局共享 schema）
├── engine/                      # 引擎编排层
│   ├── orchestrator.py          # 写作主循环（核心编排中心）
│   ├── architect.py             # Foundation 世界基石生成
│   ├── volume_planner.py        # 卷纲规划 + 伏笔排期
│   ├── planner.py               # Chapter Memo 生成 + 完结窗口逻辑
│   ├── composer.py              # 上下文组装入口（薄封装）
│   ├── writer.py                # 章节正文生成（含文风注入、字数校正）
│   ├── settler.py               # 章后结算（摘要/状态/伏笔/完结报告）
│   ├── auditor.py               # 连贯性审计 + 审计→重写循环
│   ├── reviser.py               # 自动修订器
│   ├── intervener.py            # 人工干预解析
│   ├── advisor.py               # 波及分析 + 定向修订（人机协作）
│   └── brief_optimizer.py       # 创意简报优化与评分
├── memory/                      # 记忆与状态层（JSON + Markdown）
│   ├── state_manager.py         # 状态双写（JSON 机读 + MD 人读）
│   ├── hook_policy.py           # 伏笔回收策略（纯计算底座）
│   ├── hook_lifecycle.py        # 伏笔集合操作 + 账本摘要
│   ├── context_assembly.py      # 分层上下文组装引擎
│   ├── fatigue_detector.py      # 长跨度疲劳检测
│   └── bible_manager.py         # 故事圣经管理（防幻觉锚点）
├── storage/                     # 数据持久化层（SQLite）
│   ├── database.py              # SQLite 连接薄封装
│   ├── migrations.py            # Schema 定义与迁移
│   └── repository.py            # 仓储模式 CRUD（一书一实例）
├── llm/
│   └── client.py                # OpenAI 兼容 LLM 客户端
├── style/                       # 文风仿写层
│   ├── profile.py               # StyleProfile 数据模型
│   ├── analyzer.py              # 纯统计文风分析
│   └── injector.py              # 文风指纹注入 prompt
├── genres/                      # 题材模板层
│   ├── loader.py                # TOML 模板加载器
│   └── builtin/                 # 6 个内置题材 TOML
├── utils/
│   └── config.py                # 分层配置管理（默认→全局→项目→环境变量）
└── cli/
    └── main.py                  # Click + Rich CLI 入口

web/index.html                   # 单文件 SPA 管理界面
web_server.py                    # 本地 Web 服务端（http.server）
pyproject.toml                   # 项目定义与依赖
```

---

## 4. 核心数据模型 (models.py)

`models.py` 定义了全局共享的 Pydantic v2 数据模型，是各模块通信的契约。按领域分组如下：

### 4.1 书籍与章节

| 模型 | 说明 | 关键字段 |
|------|------|----------|
| `BookConfig` | 一本书的完整配置 | id, title, genre_id, chapter_word_count, target_chapters, status, style_profile_path |
| `BookStatus`(Enum) | 书籍状态 | draft / outlining / ready / writing / paused / completed |
| `Chapter` | 一个章节 | book_id, chapter_number, title, content, word_count, status, audit_score, audit_issues |
| `ChapterStatus`(Enum) | 章节状态 | draft / audited / revised / approved |
| `ChapterSummary` | 章节摘要表 | chapter, title, characters, events, state_changes, hook_activity, mood, chapter_type |

### 4.2 伏笔（Hook）

| 模型 | 说明 |
|------|------|
| `Hook` | 一个伏笔，含层级、状态、回收时机、依赖等 |
| `HookStatus`(Enum) | planted / progressing / pressured / near_payoff / resolved / deferred |
| `HookPayoffTiming`(Enum) | immediate / near_term / mid_arc / slow_burn / endgame |
| `HookLevel`(Enum) | core（核心，跨卷 5-8 个）/ volume（卷级 8-15 个）/ chapter（章级 1-5 章回收） |
| `HookPool` | 伏笔池（hooks 列表） |

### 4.3 运行时状态

| 模型 | 说明 |
|------|------|
| `Fact` | 结构化事实三元组（subject-predicate-object + 生效章节范围） |
| `CurrentState` | 当前状态快照（facts, current_conflict, current_goal, protagonist_state, location...） |
| `ChapterMemo` | **每章写作前的 7 段结构化指令**（防幻觉核心） |
| `ContextEntry` / `ContextPackage` | 组装好的上下文包（含 Protected/Compressible token 统计） |

### 4.4 审计

| 模型 | 说明 |
|------|------|
| `AuditIssue` | 审查发现的单条问题（severity, category, description, suggestion） |
| `AuditResult` | 审查结果（passed, overall_score 0-100, issues, parse_failed） |

### 4.5 Foundation（世界基石）

| 模型 | 说明 |
|------|------|
| `WorldSetting` | 世界观 6 要素（力量体系/地理/历史/动力/势力/资源） |
| `CascadeRule` / `CascadeRules` | 链式反应规则（设定→三层后果） |
| `CivilizationNorm` / `CivilizationNorms` | 文明共识 |
| `ProtagonistProfile` | 主角 5 维度设定（身份/动机/性格/成长弧/金手指） |
| `SupportingCharacter` | 核心配角 |
| `CoreConflict` | 核心冲突线（主角 vs 世界/反派/内在） |
| `Foundation` | 完整世界基石（聚合以上所有） |

### 4.6 卷纲与规划

| 模型 | 说明 |
|------|------|
| `Volume` / `VolumePlan` | 单卷规划（章节范围/主线/高潮/转折/伏笔计划/节奏） |

### 4.7 Brief / Advise / Completion

| 模型 | 说明 |
|------|------|
| `BriefScore` / `BriefReport` | 简报评分（5 维度加权，含 total 与 verdict 属性） |
| `ImpactEntry` / `ImpactReport` / `AdvisePlan` | 波及分析（设定变更影响评估） |
| `CompletionPlan` / `HookScheduleEntry` | 完结计划与伏笔回收排期 |
| `CompletionReport` / `CharacterEnding` | 完结报告与角色归宿 |
| `GoldenThreeConfig` | 黄金三章配置（前 3 章结构与规则） |

---

## 5. 模块职责详解

### 5.1 engine 引擎层

引擎层是流程编排的核心，围绕 `Orchestrator` 组织。

#### orchestrator.py — 写作编排器（核心）

写作主循环的总指挥，管理书籍全生命周期。

**核心类：`Orchestrator`**

```python
def __init__(self, book: BookConfig, genre: GenreProfile,
             data_dir: str = "data", style_profile: StyleProfile | None = None)
```
初始化时建立目录结构（`data/<book_id>/chapters`、`story`），实例化 `StateManager`、`BibleManager`、`Repository`、`LLMClient`，维护内部状态 `_interventions`、`_foundation`、`_volume_plan`、`_completion_plan`。

主要方法：

| 方法 | 说明 |
|------|------|
| `build_foundation(brief="")` | Step1：调 `architect.generate_foundation` 生成世界基石并落盘 |
| `build_volume_plan()` | Step2：分卷 + 核心伏笔排期 + 节奏规划 |
| `initialize_book_state()` | Step4：初始化状态文件，状态置 READY |
| `run_brief(raw_brief)` | Brief 优化流水线 |
| `advise(change_request)` | 波及分析 + 记忆/章节修订 + 日志 |
| `write_next_chapter(user_instruction="")` | **核心：写下一章（六阶段流程）** |
| `write_chapters(count)` | 连续写 N 章 |
| `generate_completion_plan()` | 生成并校验完结计划 |
| `finalize()` | 手动完结，生成完结报告 |
| `get_status()` | 返回进度/伏笔/完结状态 |

模块级函数：`create_book(title, genre_id, ...)` — 加载题材、生成 8 位 uuid book_id、保存 BookConfig、返回 Orchestrator。

#### architect.py — Foundation 生成器

按依赖顺序分 6 步生成完整世界基石：世界观 6 要素 → 链式反应 → 文明共识 → 主角 → 配角 → 核心冲突。

关键函数：`generate_foundation(client, genre, book_id, brief="")` 串联全部步骤；`save_foundation_to_files` 写 `foundation/world.md`、`protagonist.md`、`characters/*.md`；`present_foundation_summary` 生成摘要展示。含 `_safe_str` 防御 LLM 返回结构异常。

#### volume_planner.py — 卷纲规划器

基于 Foundation 规划分卷（每卷 30-80 章）、播种核心伏笔与卷级伏笔、规划节奏。

关键函数：`plan_volumes`（分卷）、`plan_hook_schedule`（核心伏笔 core_hook=True）、`plan_volume_hooks`（卷级伏笔 hook_level=VOLUME）、`plan_pacing`（标注打破共识的卷）、`save_volume_plan` / `save_hooks_to_pool`（落盘）。

#### planner.py — 章节规划器

为下一章生成 7 段结构化 `ChapterMemo`，同时提供完结窗口计算逻辑。

关键函数：
- `plan_chapter(client, genre, state_mgr, book_id, chapter_number, ...)` — 根据章节状态（黄金三章≤3 章 / 最终章 / 完结窗口 / 普通）选择不同 system prompt，输出 ChapterMemo。
- `compute_completion_window` / `is_in_completion_window` / `is_final_chapter` — 完结窗口判定（最后 15%，最少 10 章）。
- `build_completion_plan` — 按紧迫度排序未回收伏笔，均匀分配目标回收章。
- `validate_completion_feasibility` — 校验伏笔数是否超剩余章数。

#### composer.py — 上下文组装入口

极薄封装层，将上下文组装委托给 memory 层的 `assemble_context`。

```python
def compose_context(state_mgr, memo, chapter_number,
                    target_chapters=None, bible=None) -> ContextPackage
```

#### writer.py — 章节生成器

生成章节正文，注入题材规则、写作心法、爽点密度、疲劳词黑名单、防元叙事、黄金三章/完结/最终章模式规则、文风指纹，并做字数校验与自动修正。

关键函数：`write_chapter(client, genre, memo, context_pkg, chapter_number, ...)` — 字数区间 0.8-1.2×，`max_tokens=2.5×`，`temperature=0.8`，最多 3 次重试（不足则扩写，超标则精简）。`_parse_chapter_output` 解析 `=== CHAPTER_TITLE ===` / `=== CHAPTER_CONTENT ===` 段。

#### settler.py — 章后结算

章节写完后的状态结算：生成摘要、更新当前状态与事实、推进/回收伏笔、章后伏笔发现、完结进度追踪。

关键函数：`settle_chapter(...)`（章后结算主入口）、`finalize_book(...)`（生成完结报告，强制回收未回收伏笔）。成本优化：`_discover_hooks_from_chapter` 每 5 章用 LLM 扫描新伏笔，其余章走 `_quick_hook_scan`（正则检测章末悬念）。含大量无 LLM 的启发式抽取函数（人名/事件/情绪/章节类型/事实）。

#### auditor.py — 连贯性审计器

多维度审查章节（OOC/事实一致性/时间线/伏笔/节奏/爽点密度/疲劳词/黄金三章专项），并驱动「审计→重写」循环。

关键常量：`GOLDEN_THREE_CHECKS`（前 3 章各 4 条 critical 检查）、`DIMENSION_LABELS`（26 维度编号→中文标签）。

关键函数：
- `audit_chapter(...)` — 加载状态跑审计（`temperature=0.3`），合并 `run_fatigue_checks` 疲劳检测结果。
- `audit_and_revise(..., max_retries=3)` — 循环审计，未通过则调 `revise_chapter` 重写，返回最终章节与审计历史。

#### reviser.py — 自动修订器

根据审计结果中的 critical 问题自动修订章节文本，仅修问题部分，保持风格与字数。`revise_chapter(client, genre, chapter, audit, memo)` — 无 critical 直接返回原章。

#### intervener.py — 人工干预处理

解析用户干预指令并分类（`InterventionType`：DIRECTION/CHARACTER/PACING/HARD_EDIT/GENERAL），渲染为 prompt 片段。纯本地逻辑，无 LLM 调用，无 fanqie 内部依赖。

#### advisor.py — 人机协作编辑器

处理设定变更请求：基于链式反应做波及分析，定向修订记忆文件与已生成章节，并记录修改日志。

关键函数：`analyze_impact`（波及分析）、`revise_memory`（修订记忆文件）、`revise_chapters`（修订章节）、`log_modification`（写 `reports/modification_log.md`）。

#### brief_optimizer.py — 简报优化器

将用户原始创意简报 AI 补全优化，按 5 维度加权评分（题材契合 30 / 爽点 25 / 可执行 20 / 完整 15 / 差异 10）。关键函数：`optimize_brief`、`score_brief`、`run_brief_pipeline`、`save_brief_report`。

### 5.2 memory 记忆层

记忆层使用 **JSON（机器读）+ Markdown（人读/LLM 上下文）双写**机制，是防幻觉与长期记忆的核心。

#### state_manager.py — 状态管理器

管理单本书的 JSON 结构化状态与对应的 Markdown 可读副本。JSON 存于 `story/state/`，Markdown 通过 `_file_routing` 路由表分发到 `foundation/`、`runtime/`、`reports/` 三个子目录。

**核心类：`StateManager`**，主要方法：`load/save_current_state`、`load/save_hook_pool`、`load/save_summaries`、`ensure_story_files`、`read_story_file`（新目录优先，回退旧扁平结构）、`write_story_file`。

#### hook_policy.py — 伏笔回收策略（纯计算底座）

伏笔回收策略的纯计算内核，无 fanqie 内部依赖。定义故事阶段（`HookPhase`：OPENING/MIDDLE/LATE）、5 种节奏画像（`TIMING_PROFILES`）、压力权重表。

关键函数：`resolve_hook_phase`（判定故事阶段）、`describe_hook_lifecycle`（计算 age/dormancy/stale/overdue/advance_pressure/resolve_pressure）。

#### hook_lifecycle.py — 伏笔集合操作

在 `hook_policy` 之上封装集合层面操作：`filter_active_hooks`（过滤活跃伏笔）、`compute_recyclable_hooks`（计算需强制回收的伏笔）、`get_hook_ledger_summary`（生成带 `[STALE]`/`[OVERDUE]`/`[CORE]` 标记的账本文本，供 ChapterMemo 使用）。

#### context_assembly.py — 分层上下文组装引擎

将多来源信息（故事圣经、Protected 基础文件、章节摘要、伏笔、卷纲）按优先级与相关性打分组装成 `ContextPackage`，分 Protected（不可压缩）与 Compressible（可压缩）两层，并做「脱敏」（去除章节号、hook_id 等内部标识）。

主入口 `assemble_context(...)` 六阶段组装：圣经索引 → Protected 文件 → 查询词提取 → 按需拉取圣经 → 章节摘要打分脱敏 → 伏笔脱敏 → 卷纲 → 估算 token 分层。

#### fatigue_detector.py — 疲劳检测

长跨度写作疲劳检测，无 fanqie 内部依赖。检测器：`detect_opening_pattern_repeat`（开头重复）、`detect_ending_pattern_repeat`（结尾重复）、`detect_title_collapse`（标题塌缩）、`detect_mood_monotony`（情绪单调）、`detect_chapter_type_monotony`（类型固化）。`run_fatigue_checks` 汇总。基于 Dice 系数（bigram）计算相似度。

#### bible_manager.py — 故事圣经管理

「故事圣经」管理器，防止长篇幻觉。分层维护 `story/runtime/` 下文件，更新频率不同：`update_index`（每章、<500 字锚点、不调 LLM）、`update_timeline`（每章追加、仅留最近 25 条）、`update_items`（每 5 章调 LLM 增量更新，异常静默）。是 memory 层唯一直接调用 LLM 的模块。

### 5.3 storage 存储层

存储层使用 **SQLite**（面向结构化查询与全文检索），与 memory 层的文件存储并行，职责分离。

#### database.py — SQLite 连接封装

`Database` 类：惰性连接、Row 字典化、WAL 模式、外键约束、上下文管理器。方法：`conn`（property）、`execute`、`executemany`、`fetchone`、`fetchall`、`commit`、`close`。

#### migrations.py — Schema 与迁移

定义完整 schema（全部 `IF NOT EXISTS`，幂等）。表结构：

| 表 | 主键 | 说明 |
|----|------|------|
| `books` | id | 书籍元信息 |
| `chapters` | (book_id, chapter_number) | 章节正文与审校 |
| `characters` | id | 角色档案 |
| `hooks` | (book_id, hook_id) | 伏笔 |
| `chapter_summaries` | (book_id, chapter) | 章节摘要 |
| `facts` | id | 结构化三元组事实 |
| `facts_fts` | — | FTS5 虚拟表，全文检索 |

`run_migrations(db)` 遍历执行，FTS5 不可用时容错跳过。`get_db_path(data_dir, book_id)` 返回 `data_dir/book_id/book.db`。

#### repository.py — 仓储模式 CRUD

`Repository` 类：一个实例 = 一本书的数据访问入口，构造时自动跑迁移。按领域实体提供 CRUD：Book / Chapter / Hook / Summary / Fact。JSON 字段（audit_issues、depends_on、relationships）写入时序列化，使用 `INSERT OR REPLACE` 实现 upsert。`search_facts` 优先 FTS5 MATCH，失败回退 LIKE。

### 5.4 llm 模型接入层

#### client.py — OpenAI 兼容客户端

基于 `httpx` 直接发 HTTP 请求的 LLM 客户端。

**核心类：`LLMClient`**
- 配置来源：构造时调 `get_llm_config()`，默认 model `gpt-4o`。
- 鉴权：`Authorization: Bearer {api_key}`。
- 端点：`{base_url}/chat/completions`。
- 传输：`httpx.Client(timeout=120)`，最多 3 次重试，指数退避。
- `chat(messages, temperature, max_tokens, stream)` → 返回 `{content, usage, model}`。
- `chat_json(messages, temperature=0.3)` → 调 chat 后用 `_extract_json` 抽取并解析，失败置 `parse_error=True`。

工具函数：`_extract_json`（匹配 ```json 代码块或括号深度匹配）、`estimate_tokens`（1 汉字 ≈ 1.5 token）。

### 5.5 style 文风层

#### profile.py — StyleProfile 数据模型

`@dataclass StyleProfile`：avg_sentence_length、sentence_length_stddev、avg_paragraph_length、paragraph_length_range、vocabulary_diversity、top_patterns、rhetorical_features。含 `to_dict` / `from_dict`（JSON 序列化）。

#### analyzer.py — 纯统计文风分析

`analyze_style(text, source_name=None) -> StyleProfile` — 不调 LLM，从参考文本提取：平均句长、句长标准差、平均段长、段长范围、词汇多样性（TTR）、高频开头模式、修辞特征密度（`_RHETORICAL_ZH` 5 组正则）。

#### injector.py — 文风指纹注入

`render_style_fingerprint(profile)` 生成 Markdown 片段；`inject_style_fingerprint(system_prompt, profile)` 追加到 system prompt。

### 5.6 genres 题材层

#### loader.py — TOML 模板加载器

加载/枚举 TOML 题材模板，映射为强类型 `GenreProfile`。TOML 用 `tomllib`（Py≥3.11）或 `tomli` 解析。

配套数据类：`WorldModulesConfig`、`ProtagonistConfig`、`CivilizationNormsConfig`、`GenreProfile`（主配置）。

关键函数：`GenreProfile.from_toml(path)`、`list_all_genres()`、`load_genre(genre_id)`（先 builtin 后 custom）、`get_genre_path(genre_id)`。

**内置题材 TOML 结构**（以 xuanhuan 为例）：`[meta]` / `[craft]`（chapter_types、fatigue_words、numerical_system、pacing_rule、satisfaction_types）/ `[craft.rules]` / `[craft.style_defaults]` / `[craft.world_modules]` / `[craft.protagonist]` / `[craft.civilization_norms]` / `[craft.golden_three]` / `[prohibitions]` / `[audit].dimensions`。

内置 6 题材：`xuanhuan`、`rule_horror`、`mass_isekai`、`cthulhu_cultivation`、`apocalypse`、`weird_descend`。

### 5.7 utils 配置层

#### config.py — 分层配置管理

分层加载/合并配置：**默认 → 全局（`~/.fanqie/config.yaml`）→ 项目（`./fanqie.yaml`）→ 环境变量**。

关键函数：`load_config()`（深合并）、`save_global_config(config)`、`get_llm_config()`、`get_writing_config()`、`_deep_merge`。环境变量 `FANQIE_API_KEY` 可覆盖 api_key。

### 5.8 cli 命令行入口

#### main.py — Click + Rich CLI

顶层 `main` 为 Click 命令组。辅助函数 `_load_orchestrator(book_id)` 从 `data/` 载入并构造 Orchestrator。

**全部命令：**

| 命令 | 说明 | 主要选项 |
|------|------|----------|
| `config set` | 设置 LLM 配置 | `--base-url` `--api-key` `--model` |
| `config show` | 展示当前配置 | — |
| `genre list` | 列出题材 | — |
| `genre show <id>` | 题材详情 | — |
| `genre create <id>` | 创建自定义题材 | `--from`（默认 xuanhuan） |
| `style analyze <file>` | 分析文风 | `--output/-o` |
| `style import <file> <book_id>` | 导入文风 | — |
| `style show <book_id>` | 查看文风 | — |
| `style remove <book_id>` | 移除文风 | — |
| `new <title>` | 创建新书 | `--genre/-g` `--words/-w` `--chapters/-c` `--brief/-b` `--yes/-y` |
| `write <book_id>` | 写章节 | `--chapters/-n` `--instruction/-i` |
| `complete <book_id>` | 手动完结 | `--yes/-y` |
| `audit <book_id> <ch>` | 审计+重写指定章 | `--retry/-r`（默认 3） |
| `status <book_id>` | 查看状态 | — |
| `advise <book_id> <instruction>` | 人机协作编辑 | `--dry-run` |
| `export <book_id>` | 导出（txt/md） | `--format/-f` `--output/-o` |

### 5.9 web 服务端与前端

#### web_server.py — 本地 Web 服务端

基于标准库 `http.server`，端口 `127.0.0.1:8765`。**架构定位为薄壳**：所有耗时写作/审计/导出操作通过 `subprocess.Popen` 以 `python -m fanqie.cli.main ...` 子进程运行，前端轮询任务状态。

任务模型：全局 `_tasks` dict + `_tasks_lock`；`_run_task` 后台线程执行 CLI 并更新状态；`_start_task` 生成 8 位 task_id。

**主要 HTTP 端点：**

GET（同步查询）：`/`、`/web/*`、`/api/books`、`/api/book`、`/api/chapters`、`/api/chapter`、`/api/genres`、`/api/genre-detail`、`/api/story-file`、`/api/config`、`/api/task`、`/api/chat/history`。

POST（多数创建后台任务）：`/api/new`、`/api/write`、`/api/advise`、`/api/export`、`/api/create-genre`、`/api/chat`（创意顾问对话）、`/api/audit`、`/api/delete`。

> ⚠️ **已知缺口**：前端 `saveLLMConfig()` 提交 `POST /api/config`，但服务端 `do_POST` 未注册该分支（仅注册 GET），故界面保存 LLM 配置不生效。

#### web/index.html — 单文件 SPA

暗色 GitHub 风主题，内联 CSS + 原生 JS 无框架。左侧书籍列表 + 右侧 Tab 内容区 + 右下任务进度面板 + 聊天悬浮组件 + 弹窗。所有交互通过 `fetch(API + '/api/...')` 调用后端，任务类操作通过 `pollTask` 轮询 `/api/task`。

---

## 6. 核心写作流程（Pipeline）

`Orchestrator.write_next_chapter()` 是系统心脏，完整执行如下：

**前置检查**
1. 若书籍已完结 → 抛异常禁止续写。
2. 计算 `chapter_number = 已有章数 + 1`；超过 `target_chapters` → 提示用 `complete` 或 `advise`。
3. 处理用户干预：`parse_intervention` 解析 → `render_intervention_prompt` 生成提示文本。
4. 完结窗口检测：进入窗口则确保 `_completion_plan` 已生成。

**① Plan（planner.plan_chapter）**
生成 7 段结构化 `ChapterMemo`。根据黄金三章/最终章/完结窗口/普通选择不同 prompt，注入伏笔账本与可回收伏笔。

**② Compose（composer.compose_context）**
调 `assemble_context`，结合 memo + bible 组装 `ContextPackage`（Protected 不可压缩 + Compressible 可压缩，含脱敏）。

**③ Write（writer.write_chapter）**
取上一章标题防重复，生成含标题与正文的 `Chapter`，字数区间校验（0.8-1.2×），最多 3 次自动扩写/精简。落盘草稿 + 入库（status=draft）。

**④ Settle（settler.settle_chapter）**
生成摘要、更新 current_state、推进/回收伏笔、章后发现新伏笔、完结进度追踪。Orchestrator 额外做：更新 bible（index/timeline/items）、更新 current_focus、进入新卷时播种卷级伏笔。

**⑤ Audit + Revise（auditor.audit_and_revise）**
「审计→不合格→重写→再审计」循环（默认 `review_retries=3`）。写回 `audit_score`、`audit_issues`；passed → APPROVED，否则 REVISED，合并疲劳检测结果。

**收尾**
最终保存章节文件与入库；若为最终章 → `_auto_finalize()` 生成完结报告并置 COMPLETED。

```
write_next_chapter 循环：
   Plan     ─▶ planner.plan_chapter        (ChapterMemo 7段结构)
   Compose  ─▶ composer.compose_context     (ContextPackage 分层脱敏)
   Write    ─▶ writer.write_chapter         (Chapter, 字数自校正)
   Settle   ─▶ settler.settle_chapter       (摘要/状态/伏笔/发现)
              + bible/current_focus/卷级伏笔播种
   Audit    ─▶ auditor.audit_and_revise ──▶ reviser.revise_chapter (循环)
   [完结]   ─▶ settler.finalize_book        (CompletionReport)
```

---

## 7. 依赖关系图

### 引擎层阶段依赖

```
create_book ─▶ Orchestrator
                 │
   ├─ Brief ─────┴─ brief_optimizer (optimize→score)
   ├─ Step1 build_foundation ─▶ architect (world→cascade→norms→protagonist→characters→conflict)
   ├─ Step2 build_volume_plan ─▶ volume_planner (plan_volumes→plan_hook_schedule→plan_pacing)
   ├─ Step4 initialize_book_state
   └─ write_next_chapter 循环 (Plan→Compose→Write→Settle→Audit→Revise)
   横切：intervener（干预）、advisor（波及分析）、planner（完结窗口计算）
```

### memory / storage / llm 内部依赖

```
hook_policy.py        (无内部依赖，纯策略底座)
      ↑
hook_lifecycle.py     (依赖 hook_policy)
      ↑
context_assembly.py   (依赖 hook_lifecycle + state_manager + bible_manager + models)

state_manager.py      (依赖 models)
bible_manager.py      (依赖 llm.client + models + genres.loader)
fatigue_detector.py   (无内部依赖，纯算法)

llm/client.py         (依赖 utils.config)  ← 唯一对外 API 出口

storage/database.py   (无内部依赖)
      ↑
storage/migrations.py (依赖 database)
      ↑
storage/repository.py (依赖 database + migrations)
```

**关键观察：**
1. 两套并行持久化：`memory/`（JSON+MD，面向 LLM 上下文/人读）与 `storage/`（SQLite，面向结构化查询/FTS），字段高度对应但彼此无直接引用，职责分离。
2. `hook_policy → hook_lifecycle → context_assembly` 构成清晰的三层伏笔调度链：纯策略计算 → 集合过滤/账本 → 上下文注入。
3. `llm/client.py` 是唯一对外 API 出口；`bible_manager` 是 memory 层唯一直接调 LLM 的模块。
4. CLI 是唯一真正的业务执行入口；Web 服务端作为薄壳，将操作转成 CLI 子进程调用。

---

## 8. 数据持久化设计

单本书的数据存储在 `data/<book_id>/` 目录下：

```
data/<book_id>/
├── book.db                      # SQLite 数据库（结构化查询）
├── chapters/                    # 章节 Markdown 草稿
│   └── vol{NN}/{NNNN}.md        # 按卷号分子目录
└── story/                       # 记忆文件（人读 + LLM 上下文）
    ├── state/                   # JSON 结构化状态（机器读）
    │   ├── current_state.json
    │   ├── hooks.json
    │   └── chapter_summaries.json
    ├── foundation/              # 世界基石（world.md / protagonist.md / volume_map.md / characters/）
    ├── runtime/                 # 运行时（current_state.md / hooks.md / index.md / timeline.md / items.md）
    └── reports/                 # 报告（brief_report.md / modification_log.md / 完结报告）
```

- **SQLite（storage/）**：books、chapters、hooks、characters、chapter_summaries、facts、facts_fts（全文检索）。
- **JSON（state/）**：机器读结构化状态，供程序加载。
- **Markdown（foundation/runtime/reports/）**：人类可读 + 作为 LLM 上下文注入源。

---

## 9. 运行方式

### 安装

```bash
git clone <repo-url> fanqie
cd fanqie
pip install -e "."
fanqie --help
```

依赖：Python 3.9+，pydantic、click、rich、httpx、pyyaml、tomli。

### 命令行使用

```bash
# 1. 配置 LLM（支持 DeepSeek / Qwen / GLM 等 OpenAI 兼容模型）
fanqie config set --base-url https://your-api.com/v1 --api-key sk-xxx --model deepseek-chat
fanqie config show

# 2. 选择题材
fanqie genre list
fanqie genre show xuanhuan
fanqie genre create my_genre --from xuanhuan

# 3. 创建新书（生成 Foundation + 卷纲）
fanqie new "我的第一本爽文" --genre xuanhuan --words 2000 --chapters 500

# 4. 文风仿写（可选）
fanqie style analyze 参考小说.txt --output style.json
fanqie style import style.json <book_id>

# 5. 写作
fanqie write <book_id>              # 写一章
fanqie write <book_id> -n 5         # 连续写 5 章
fanqie write <book_id> -i "指令"    # 带干预指令

# 6. 查看状态 / 审计 / 完结 / 导出
fanqie status <book_id>
fanqie audit <book_id> 10 -r 3
fanqie complete <book_id>
fanqie export <book_id> -f md -o 输出.md
```

### Web 界面

```bash
python web_server.py
# 浏览器打开 http://127.0.0.1:8765
```

Web 服务端将写作/审计/导出等操作转为后台 CLI 子进程执行，前端轮询进度。

### 配置文件

全局配置 `~/.fanqie/config.yaml`，项目级配置 `./fanqie.yaml`：

```yaml
llm:
  base_url: https://api.openai.com/v1
  api_key: ""
  model: gpt-4o
  temperature: 0.7
  max_tokens: 4096

writing:
  default_chapter_words: 2000
  target_chapters: 500
  review_retries: 1
  core_hooks_count: 5
```

环境变量 `FANQIE_API_KEY` 可覆盖 API Key。

---

## 10. 关键设计要点

1. **单一编排中心**：`Orchestrator` 持有全部可变状态（foundation/volume_plan/completion_plan/interventions），阶段模块均为无状态纯函数，便于测试与替换。

2. **防幻觉三重机制**：
   - 写作前 Chapter Memo（7 段结构限定输出范围）+ 分层上下文（Protected 不可压缩 / Compressible 可压缩）。
   - 写作后 Continuity Auditor（20+ 维度审查）+ 自动修订闭环（默认 3 次）。
   - 全周期故事圣经（index/timeline/items 分频更新）。

3. **完结窗口机制**：最后 15%（最少 10 章）自动生成 `CompletionPlan`，按紧迫度排期伏笔回收，Planner/Writer 切换到「禁止新伏笔、加速收束」的专用 prompt，最终章自动 finalize。

4. **黄金三章特化**：前 3 章在 Planner、Writer、Auditor 三处均有专项 prompt/检查（每章 4 条 critical 规则）。

5. **伏笔分层调度**：core（跨卷）/ volume（卷级）/ chapter（章级）三层，`hook_policy → hook_lifecycle` 计算压力与 stale/overdue 状态，强制回收避免坑埋不填。

6. **成本优化**：伏笔发现（settler）与 bible items 更新采用「每 5 章一次 LLM + 其余规则扫描」策略，降低 LLM 调用频率。

7. **健壮性防御**：planner 的 `_ensure_list/_ensure_str`、architect 的 `_safe_str`、auditor 的 `parse_failed` 分支，均在防御 LLM 返回结构不符预期。

8. **双持久化职责分离**：SQLite 面向结构化查询与 FTS 全文检索，文件（JSON+MD）面向 LLM 上下文与人类可读，互不耦合。

---

*本文档由代码分析自动生成，反映仓库当前源码状态。*
