# Fanqie V1 改进方案：Foundation + Brief + Advise

## 问题诊断

当前流程：fanqie new 只创建空壳 -> fanqie write 直接生成章节
InkOS 流程：book create 生成 Foundation -> 卷纲规划 -> 逐章生成

核心缺陷：缺少 Foundation 阶段，AI 在没有世界观/角色/卷纲的情况下裸奔

## 改进后的完整流程

```
fanqie new "书名" --genre <id> [--brief 创意.txt]
  |
  +-- Step 0: Brief 优化（可选）
  |    - 读取用户创意简报
  |    - AI 补全优化（按题材模板检查缺失要素）
  |    - 输出评分报告（见评分维度）
  |    - 用户确认 -> 进入 Step 1
  |
  +-- Step 1: Foundation 生成（Architect）
  |    |
  |    |  [按依赖顺序生成，每步依赖前序产出]
  |    |
  |    ├── 1a. 世界观架构（6 要素，由题材模板决定侧重）
  |    │    - 力量体系（等级划分、突破条件、战力参照）
  |    │    - 地理（关键区域、势力分布、资源产地）
  |    │    - 历史（关键纪元、上古事件、当前时代背景）
  |    │    - 世界前进的动力（所有人为何而行动？生存？飞升？信仰？）
  |    │    - 势力格局（主要势力、势力间关系、权力真空）
  |    │    - 资源分配与权力循环（谁掌控资源、如何流转、权力更替机制）
  |    │
  |    ├── 1b. 链式反应设计 ← 依赖 1a
  |    │    - 每个核心设定推导 2-3 层连锁影响
  |    │    - 确保设定之间互相咬合，不是孤立的"设定列表"
  |    │    - 结构：A 设定 → B 后果 → C 社会变化 → D 新矛盾
  |    │    - 写入 story/cascade_rules.md
  |    │
  |    ├── 1c. 文明共识 ← 依赖 1a + 1b
  |    │    - 提炼 3-5 条"世界默认行为准则"
  |    │    - 这些共识是角色行为的"操作系统"，除非弧光设计明确打破
  |    │    - 由题材模板提供生成提示，AI 根据世界观 + 链式反应推导
  |    │    - 写入 story/civilization_norms.md
  |    │
  |    ├── 1d. 主角设定 ← 依赖 1a + 1b + 1c（主角需要在世界观中找到位置）
  |    │    - 身份：表面身份 + 隐藏身世 + 社会阶层轨迹
  |    │    - 动机：近期/中期/长期（三层递进）
  |    │    - 性格：核心特质 + 致命缺陷 + 内在冲突
  |    │    - 弧光：按卷规划角色蜕变节点（从哪里到哪里）
  |    │    - 金手指：能力说明 + 限制条件 + 成长路径 + 为什么不崩平衡
  |    │    - 写入 story/characters/main.md
  |    │
  |    ├── 1e. 核心配角 3-5 人 ← 依赖 1d
  |    │    - 身份背景 + 与主角的关系定位（盟友/对手/灰色地带）
  |    │    - 个人动机（独立于主角的自身诉求）
  |    │    - 与主角的互补/对立维度（性格互补？利益冲突？理念分歧？）
  |    │    - 命运走向（哪些配角会在哪卷退场/转变/黑化）
  |    │    - 各自写入 story/characters/xxx.md
  |    │
  |    ├── 1f. 核心冲突线 ← 依赖 1d + 1e
  |    │    - 主角 vs 世界的根本矛盾
  |    │    - 主角 vs 反派的核心对立
  |    │    - 主角内在冲突（性格缺陷 vs 目标的张力）
  |    │    - 写入 story/story_frame.md 末尾
  |    │
  |    └── 写入总览文件：
  |         - story/story_frame.md（世界观 6 要素 + 核心冲突）
  |
  +-- Step 2: 卷纲规划（Volume Planner）← 依赖全部 Step 1
  |    - 按 target_chapters 自动分卷（每卷 30-80 章）
  |    - 每卷主线目标 + 高潮节点 + 关键转折
  |    - 转折设计需参考 cascade_rules（利用连锁反应制造意外）
  |    - 角色行为需符合 civilization_norms（除非该卷设计了规范突破）
  |    - 伏笔播种计划（哪些伏笔在哪卷埋、哪卷收）
  |    - 节奏规划（紧张/舒缓/爆发分布）
  |    - 写入 story/volume_map.md
  |    - 初始化伏笔池 story/state/hooks.json（5个核心伏笔）
  |
  +-- Step 3: 用户确认
  |    - 展示 Foundation 摘要（世界观要点 + 主角定位 + 卷纲概览）
  |    - 用户可：确认 / 要求修改某部分 / 全部重新生成
  |    - 确认后写入状态文件，进入 ready
  |
  +-- Step 4: 状态初始化
  |    - 写入 story/author_intent.md
  |    - 写入 story/current_focus.md
  |    - 写入 story/book_rules.md
  |    - 写入 story/state/current_state.json
  |    - 书籍状态 -> ready
  |
  +-- 完成：可以开始 fanqie write
```

## 题材模板驱动的差异化

不同题材的 Foundation 由 TOML 题材模板控制。模板定义：

1. **世界观 6 要素的侧重** — 哪些要素是核心，哪些是辅助
2. **特殊模块** — 该题材独有的额外设定维度
3. **文明共识的生成提示** — 引导 AI 生成符合题材气质的世界默认准则
4. **主角设定偏好** — 该题材常见的主角定位模式

### 题材模板 TOML 新增字段

```toml
[craft.world_modules]
# 定义该题材需要生成哪些世界观模块（默认全部 6 个）
required = ["power_system", "geography", "history", "drive", "factions", "resources"]
# 可选：该题材独有的额外模块
extra = ["rule_system", "sanity_system"]

# 每个模块的生成侧重提示
[craft.world_modules.emphasis]
power_system = "重点设计等级划分、突破条件、战力天花板"
drive = "世界前进的核心动力：为什么所有角色都在行动？"
resources = "资源的稀缺性、分配机制、垄断与打破垄断"
```

```toml
[craft.protagonist]
# 主角设定的题材偏好提示（AI 参考，不硬性约束）
identity_hint = "该题材常见的主角起点定位"
motivation_hint = "近期动机的常见挂钩方式"
arc_hint = "角色弧光的典型节奏"
```

```toml
[craft.civilization_norms]
# 文明共识的生成引导
count = 5
prompt_hint = "从世界观推导该世界中人们不言自明的基本认知"
```

```toml
[craft.prohibitions]
# 已有字段，增强：与文明共识联动
# 违反 prohibitions 的内容即是打破文明共识的写法
items = [...]
```

## Brief 评分维度

5 个维度，按权重排序（括号内为满分）：

1. **题材契合度**（30 分）— 是否符合所选题材的核心套路和读者期待
2. **爽点潜力**（25 分）— 打脸/逆袭/升级/揭秘等爽感设计是否充足
3. **可执行性**（20 分）— AI 能否据此生成连贯章节，设定是否自洽
4. **完整性**（15 分）— 核心要素是否齐全（世界观/主角/冲突/金手指）
5. **差异化**（10 分）— 与同题材常见套路的区分度

总分 100 分。70 分以上可执行，50-70 分建议优化后使用，50 分以下建议重写。

## 文件夹结构

```
data/<book_id>/
  book.db                          # SQLite 数据库
  story/
    story_frame.md                 # 世界观设定（6 要素 + 核心冲突）
    cascade_rules.md               # 链式反应设计
    civilization_norms.md          # 文明共识
    author_intent.md               # 作者意图/长期方向
    current_focus.md               # 当前关注点
    book_rules.md                  # 本书专属规则
    volume_map.md                  # 卷纲
    modification_log.md            # 修改记录（advise 生成）
    brief_report.md                # Brief 优化报告（brief 生成）
    characters/
      main.md                      # 主角设定（5 维度）
      antagonist.md                # 反派设定
      ...                          # 其他配角
    state/
      current_state.json           # 当前状态快照
      hooks.json                   # 伏笔池
      chapter_summaries.json       # 章节摘要
    current_state.md               # 状态的 Markdown 副本
  chapters/
    vol01/                         # 第一卷
      0001.md
      0002.md
      ...
    vol02/                         # 第二卷
      ...
    ...
  style_profile.json               # 文风指纹（可选）
```

## 新增模块

### 1. fanqie/engine/architect.py — Foundation 生成器
- generate_world_setting(genre_template) — 世界观 6 要素
- generate_cascade_rules(world_setting) — 链式反应
- generate_civilization_norms(world_setting, cascade_rules, genre_template) — 文明共识
- generate_protagonist(world_setting, norms, genre_template) — 主角 5 维度
- generate_characters(protagonist) — 配角（含关系定位和命运走向）
- generate_core_conflict(protagonist, characters, world_setting) — 核心冲突
- present_for_confirmation(foundation) — 展示摘要供用户确认

### 2. fanqie/engine/volume_planner.py — 卷纲规划器
- plan_volumes(foundation, target_chapters) — 分卷规划
- plan_hook_schedule(volumes, cascade_rules) — 伏笔播种（参考链式反应）
- plan_pacing(volumes, civilization_norms) — 节奏规划（标注哪些卷打破共识）

### 3. fanqie/engine/brief_optimizer.py — 简报优化器
- optimize_brief(raw_brief, genre_template) — AI 补全优化
- score_brief(brief, genre_template) — 按 5 维度加权评分

### 4. fanqie/engine/advisor.py — 人机协作编辑器
- analyze_impact(target, cascade_rules) — 波及分析
    - 输入：用户要修改的设定/角色/情节
    - 流程：在 cascade_rules 中查找该节点的所有下游影响
    - 输出：受影响的文件列表 + 每个文件需要修改的具体内容
- revise_memory(book_id, impact_report) — 按波及报告修改记忆文件
- revise_chapters(book_id, impact_report) — 对已生成章节做定向修订
- log_modification(book_id, change_summary) — 记录修改日志

## 修改现有模块

### 1. fanqie/engine/orchestrator.py
- create_book() 调用 architect + volume_planner，含用户确认环节
- write_next_chapter() 按卷创建子文件夹 volXX/

### 2. fanqie/cli/main.py
- new 命令增加 --brief 参数
- new 命令增加 Foundation 确认交互（展示摘要，等待 y/n/修改指令）
- 新增 advise 命令

### 3. fanqie/models.py
- 新增 Foundation, CascadeRule, CivilizationNorm, ProtagonistProfile
- 新增 BriefReport, AdvisePlan, Volume, VolumePlan
- BookStatus 新增 OUTLINING, READY 状态

### 4. fanqie/genres/ — 题材模板增强
- TOML 模板新增 [craft.world_modules]、[craft.protagonist]、[craft.civilization_norms]

## 实施步骤

### Phase 1: Foundation + 文件夹结构（核心）
1. 新增 architect.py + volume_planner.py
2. 修改 models.py — 新增数据模型
3. 修改题材 TOML — 新增字段
4. 修改 orchestrator.py — create_book 调用 Foundation + 用户确认
5. 修改 writer.py / settler.py — 章节写入 volXX/
6. 修改 cli/main.py — new 命令支持 Foundation + 确认交互
7. 测试

### Phase 2: Brief 优化
1. 新增 brief_optimizer.py
2. 修改 cli/main.py — new --brief
3. 测试

### Phase 3: Advise 模式
1. 新增 advisor.py（含波及分析机制）
2. 修改 cli/main.py — advise 命令
3. 测试

## 验收标准

1. fanqie new "书名" --genre <id> 自动生成完整 Foundation + 展示摘要等待确认
2. Foundation 包含：世界观6要素 + 链式反应 + 文明共识 + 主角5维度 + 配角 + 冲突线
3. 卷纲规划参考链式反应设计转折，参考文明共识标注行为边界
4. fanqie new "书名" --brief 创意.txt 先评分优化简报再生成
5. fanqie advise <book-id> "意见" 先做波及分析再修改
6. fanqie write <book-id> 按卷生成章节到 volXX/ 文件夹
7. fanqie status <book-id> 显示当前卷/章/伏笔状态

## 参考

- InkOS: https://github.com/Narcooo/inkos
- InkOS book create: inkos-ref/packages/cli/src/commands/book.ts
- InkOS plan: inkos-ref/packages/cli/src/commands/plan.ts