# Story 目录架构优化 — 分析

## 现状问题

### 1. 信息重复严重

同一份信息出现在多个文件中：

| 信息 | 出现在 |
|---|---|
| 主角状态/位置/冲突 | `current_state.md` + `current_focus.md` + `bible/index.md` |
| 章节摘要 | `chapter_summaries.md` + `bible/timeline.md` + `current_focus.md` |
| 伏笔列表 | `pending_hooks.md` + `current_focus.md` + `bible/index.md` |
| 角色信息 | `characters/*.md` + `bible/characters.md` |

### 2. bible/ 和 story/ 功能重叠

- `bible/characters.md` 只有主角，但 `story/characters/` 有完整配角文件
- `bible/factions.md` 把主角当成势力、怪物群当成势力
- `bible/index.md` 在场角色写的是"林北（第5章）"——但林北是主角

### 3. current_state.md 事实库有 bug

位置提取逻辑坏了，把界震倒计时当成了位置：
```
- 主角 当前位置 :72小时】
- 主角 当前位置 :71小时】
```

### 4. 缺少关键文件

- 没有 `brief_report.md`
- 没有 `modification_log.md`
- 没有 `completion_plan.md` / `completion_report.md`

---

## 优化方案：三层结构

```
story/
  foundation/           ← 静态设定（建书时生成，很少改）
    world.md            ← 世界观（合并 story_frame + cascade_rules + civilization_norms）
    protagonist.md      ← 主角设定
    characters/         ← 配角设定
      ＜角色名＞.md
    volume_map.md       ← 卷纲
    author_intent.md    ← 作者意图
    book_rules.md       ← 本书规则

  runtime/              ← 动态状态（每章更新）
    index.md            ← 极简锚点（合并 current_state + current_focus + bible/index）
    timeline.md         ← 最近 20 章事件线
    hooks.md            ← 伏笔状态（合并 pending_hooks + hooks.json 摘要）
    items.md            ← 物品/能力

  reports/              ← 阶段性报告（按需生成）
    brief_report.md
    completion_plan.md
    completion_report.md
    modification_log.md
```

### 改动对照

| 现在 | 优化后 | 变化 |
|---|---|---|
| `story_frame.md` | `foundation/world.md` | 合并 3→1 |
| `cascade_rules.md` | ↑ 同上 | |
| `civilization_norms.md` | ↑ 同上 | |
| `current_state.md` | `runtime/index.md` | 合并 3→1 |
| `current_focus.md` | ↑ 同上 | |
| `bible/index.md` | ↑ 同上 | |
| `chapter_summaries.md` | `runtime/timeline.md` | 合并 2→1 |
| `bible/timeline.md` | ↑ 同上 | |
| `pending_hooks.md` | `runtime/hooks.md` | 重命名 |
| `bible/characters.md` | **删除** | 已有 foundation/characters/ |
| `bible/factions.md` | **删除** | 势力在 foundation/world.md |
| `bible/items.md` | `runtime/items.md` | 移动 |
| `characters/main.md` | `foundation/protagonist.md` | 重命名 |
| `characters/*.md` | `foundation/characters/*.md` | 移动 |
| `volume_map.md` | `foundation/volume_map.md` | 移动 |
| `author_intent.md` | `foundation/author_intent.md` | 移动 |
| `book_rules.md` | `foundation/book_rules.md` | 移动 |

### 效果

- 文件数：25 → 15（减少 40%）
- 每章更新文件：5-6 个 → 2-3 个
- 信息冗余：大幅减少
- Planner 上下文：更干净、更一致

---

## 受影响文件分析

### 需要改路径的（文件读写路径变化）

| 文件 | 引用的路径 | 影响程度 |
|---|---|---|
| `state_manager.py` | `story_frame.md`, `current_state.md`, `current_focus.md`, `book_rules.md`, `volume_map.md`, `chapter_summaries.md`, `pending_hooks.md`, `author_intent.md` | **核心**，所有读写入口 |
| `context_assembly.py` | 同上 + `bible/` 路径 | 10+ 处 |
| `bible_manager.py` | `bible/` 目录 | 全部 |
| `architect.py` | `story_frame.md`, `cascade_rules.md`, `civilization_norms.md` | 写入端 |
| `orchestrator.py` | `author_intent.md`, `current_focus.md`, `book_rules.md`, `cascade_rules.md` | 初始化 + 读取 |
| `planner.py` | `current_state.md`, `volume_map.md`, `author_intent.md`, `current_focus.md` | 读取端 |
| `settler.py` | `story_frame.md`, `volume_map.md`, `author_intent.md` | 读取端 |
| `auditor.py` | `current_state.md`, `pending_hooks.md` | 读取端 |
| `volume_planner.py` | `volume_map.md` | 写入端 |
| `advisor.py` | `story_frame.md`, `story/` 前缀 | 读取端 |

### 不需要改的（只引模型对象，不碰文件路径）

| 文件 | 说明 |
|---|---|
| `models.py` | 只定义数据模型 |
| `loader.py` | 只读 toml |
| `hook_lifecycle.py` | 只操作 Hook 对象 |
| `hook_policy.py` | 只做计算 |
| `repository.py` | 只操作 SQLite |
| `migrations.py` | 只操作 SQLite |
| `cli/main.py` | 通过 Orchestrator 间接操作 |

---

## 结论

**改动量较大**，核心是 `state_manager.py`（所有文件读写的入口），其次是 `context_assembly.py`、`bible_manager.py`、`architect.py`、`orchestrator.py`。

**建议**：这个重构先放一放，等黄金三章和题材模板做完再做。现有架构虽然冗余但能跑，重构风险高于收益。
