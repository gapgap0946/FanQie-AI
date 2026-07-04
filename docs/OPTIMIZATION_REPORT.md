# fanqie 优化分析报告

> 基于对仓库源码的逐行审查，本报告仅提供分析与建议，**不改动任何现有代码**。
> 每条建议均标注了证据位置（文件与行号），并按优先级排序，便于后续实施。

---

## 目录

1. [核心结论（TL;DR）](#1-核心结论tldr)
2. [🎯 专题：剧情后续单调问题根因分析](#2--专题剧情后续单调问题根因分析)
3. [代码质量与 Bug](#3-代码质量与-bug)
4. [性能与成本](#4-性能与成本)
5. [架构与可维护性](#5-架构与可维护性)
6. [工程管理与 Git 版本控制](#6-工程管理与-git-版本控制)
7. [优先级路线图](#7-优先级路线图)

---

## 1. 核心结论（TL;DR）

| 维度 | 关键问题 | 影响 |
|------|----------|------|
| **剧情单调（重点）** | 章节摘要仅截取正文前 150 字；情绪/类型/冲突全靠关键词硬编码判定 | 上下文注入低质 → LLM 无法基于真实剧情推进 → 原地打转 |
| **剧情单调** | 疲劳检测建立在错误的 mood/chapter_type 信号上，阈值又钝 | 反单调机制形同虚设 |
| **剧情单调** | Writer system prompt 每章完全相同的固定爽点模板 | 模板化的结构性来源 |
| **Bug** | `_update_hooks_from_memo` 用子串匹配 hook_id 推进伏笔，几乎不触发 | 伏笔推进/回收失效 |
| **Bug** | `POST /api/config` 前端提交但后端未注册 | Web 保存 LLM 配置无效 |
| **性能** | 字数重试把历史对话累积进 messages 重发；facts 只增不删 | token 成本随篇幅线性膨胀 |
| **架构** | memory(JSON/MD) 与 storage(SQLite) 双写字段重复、无同步 | 一致性风险，SQLite 价值闲置 |
| **工程管理** | 仓库已 `git init` 但**零提交、无分支、无提交规范/CI** | 无版本历史，改动不可追溯、无法回滚 |

**最高杠杆的单点改动**：把 [settler._summarize_events](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L148-L151) 与 mood/type/conflict 抽取从「正文截断 + 关键词计数」升级为「结算阶段用 LLM 生成结构化摘要」。这一处直接决定了后续所有章节看到的"前情"质量，是剧情单调的第一根因。

---

## 2. 🎯 专题：剧情后续单调问题根因分析

剧情单调不是单一 bug，而是一条**低质信号在流水线中被逐级放大**的因果链：

```
Settle 生成低质摘要 ──▶ 存入 summaries ──▶ Compose 注入"前情提要" ──▶ Write 拿到残缺上下文
      │                                                                    │
      └──▶ 错误的 mood/type 信号 ──▶ Fatigue 检测失真 ──▶ 反单调机制失效 ◀──┘
```

### 2.1 根因一：章节摘要是「正文前 150 字截断」，不是真摘要 ⭐️ 最高优先级

[_summarize_events](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L148-L151)：

```python
def _summarize_events(content: str) -> str:
    clean = content.replace("\n", " ").strip()
    return clean[:150] + ("..." if len(clean) > 150 else "")
```

- **问题**：摘要 = 章节开头 150 字。开头通常是环境/心理铺垫，往往**不包含本章真正发生的事件与结果**。
- **传导**：[context_assembly.py:L139](file:///d:/AI/AI-fanqie/fanqie/memory/context_assembly.py#L139) 把 `s.events` 作为"前情提要"注入下一章。于是 LLM 每章看到的"前情"都是上一章的**开头片段**，而非剧情走向。
- **后果**：模型缺乏"故事到底推进到哪、发生了什么后果"的信息，只能重复安全套路 → **原地打转、单调**。
- **建议**：在 `settle_chapter` 中新增一次轻量 LLM 调用生成结构化摘要（events / 关键转折 / 状态变化 / 遗留悬念），或复用已有的 [bible_manager.update_items](file:///d:/AI/AI-fanqie/fanqie/memory/bible_manager.py#L153-L207) 的"每 5 章 LLM"模式，对摘要也做分频 LLM 化。这是投入产出比最高的一处。

### 2.2 根因二：情绪 / 章节类型 / 冲突全靠关键词硬编码

- [_detect_mood](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L154-L171)：数关键词出现次数取最大值。"冷笑"计入"爽快"，但一个转折复杂的章节可能被误判。
- [_detect_chapter_type](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L174-L186)：命中不到就 `return genre.chapter_types[-2]`——**默认永远返回倒数第二个类型**，导致 `chapter_type` 长期恒定。
- [_extract_conflict](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L205-L213)：只有 4 种硬编码冲突，`current_conflict` 长期在这几种间跳。

**传导后果**：这三个字段是疲劳检测的输入信号（见 2.3）。信号本身失真，检测就无从谈起。

**建议**：这些字段与 2.1 的摘要一并由 LLM 结构化产出（一次调用同时返回 events/mood/type/conflict/state_changes），既省调用又保证信号真实。

### 2.3 根因三：疲劳检测建立在失真信号上，且阈值过钝

[fatigue_detector.py](file:///d:/AI/AI-fanqie/fanqie/memory/fatigue_detector.py)：

- [detect_mood_monotony](file:///d:/AI/AI-fanqie/fanqie/memory/fatigue_detector.py#L104-L122)：需**连续 5 章**都命中高张力词才报警；而 mood 本身来自 2.2 的失真判定 → 实际几乎不触发。
- [detect_chapter_type_monotony](file:///d:/AI/AI-fanqie/fanqie/memory/fatigue_detector.py#L125-L138)：由于 `_detect_chapter_type` 恒返回倒数第二类型，这里反而可能**恒报警或恒不报警**，失去区分力。
- [detect_opening/ending_pattern_repeat](file:///d:/AI/AI-fanqie/fanqie/memory/fatigue_detector.py#L41-L80)：相似度阈值 0.4 偏高，且只看最近 3 章。真正的"套路化"往往是句式结构相似而非字面相似，bigram Dice 难以捕捉。

**传导后果**：即使检测到疲劳，结果只作为 audit issue 传给 [auditor.audit_chapter](file:///d:/AI/AI-fanqie/fanqie/engine/auditor.py)，而 [reviser.revise_chapter](file:///d:/AI/AI-fanqie/fanqie/engine/reviser.py#L10-L68) **只处理 critical 级问题**——疲劳 issue 若非 critical，不会被修订，等于只提示不修复。

**建议**：
1. 修正 `_detect_chapter_type` 的默认返回逻辑（不应恒定）。
2. 疲劳信号应**前置到 Planner**：在生成下一章 ChapterMemo 时，把"最近 N 章的 mood/type/开篇方式"作为约束注入 planner prompt（"避免与最近 3 章相同的开篇/情绪/章节功能"），从**生成端**主动去重，而非事后审计。
3. 降低单调判定门槛或改为"滑动窗口占比"（如最近 5 章≥3 章同类型即预警）。

### 2.4 根因四：Writer 每章使用完全相同的固定爽点模板

[build_writer_system_prompt](file:///d:/AI/AI-fanqie/fanqie/engine/writer.py#L46-L140) 中的"爽点密度要求""文笔要求"是**硬编码常量**，每章一字不差：

```
每 300 字必须有 1 个小爽点 … 每 500 字 1 个中爽点 … 每 1000-1500 字 1 个大爽点
```

- **问题**：所有章节被强制套进同一节奏骨架，本身就是"模板化"的结构性来源。过渡章、铺垫章、收束章不应与爆发章使用同一爽点密度。
- **建议**：爽点密度模板应**按章节类型/卷阶段差异化**。可让 Planner 在 ChapterMemo 中输出本章的"节奏配方"（张力曲线、爽点目标数），Writer 据此动态生成密度要求，而非固定常量。

### 2.5 根因五：事实库几乎为空，连贯性缺乏支撑

[_extract_facts_from_chapter](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L189-L202) **只能抽取"当前位置"一种事实**，其他事实（关系变化、获得物品、实力变化、承诺、仇怨）全部丢失。

- **后果**：`CurrentState.facts` 长期近乎为空，SQLite 的 `facts` / `facts_fts` 全文检索表基本没有数据可查，长期记忆的"事实层"名存实亡 → 人物关系/设定容易漂移，也是"感觉在重复但细节对不上"的来源。
- **建议**：与 2.1 的结构化摘要合并，让 LLM 一并抽取 3-5 条结构化事实三元组入库。

### 2.6 剧情单调 · 改进优先级小结

| 顺序 | 动作 | 预期收益 |
|------|------|----------|
| 1 | 结算阶段 LLM 化：一次调用产出 events/mood/type/conflict/facts | 从源头修复上下文质量，收益最大 |
| 2 | 疲劳信号前置到 Planner，从生成端主动去重 | 主动防单调，比事后审计有效 |
| 3 | Writer 爽点密度按章节类型/阶段差异化 | 打破结构模板化 |
| 4 | 修正 `_detect_chapter_type` 默认返回、降低疲劳阈值 | 让现有检测器真正生效 |

---

## 3. 代码质量与 Bug

### 3.1 伏笔推进逻辑几乎不触发（功能性 Bug）⭐️

[_update_hooks_from_memo](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L225-L243)：

```python
for hook in pool.hooks:
    if hook.hook_id in pay_off_text:   # 子串匹配 hook_id
        hook.last_advanced_chapter = chapter_number
        hook.advanced_count += 1
```

- **问题**：`pay_off_text` 是 memo 的自然语言字段（如"揭示主角身世"），几乎不可能包含形如 `ch0001_01` 的 hook_id 字符串，因此 `advanced_count` 基本永远不增长。
- **连锁影响**：[hook_lifecycle.compute_recyclable_hooks](file:///d:/AI/AI-fanqie/fanqie/memory/hook_lifecycle.py#L20-L53) 依赖 `last_advanced_chapter` 判定 stale/overdue；此值不更新 → 伏笔要么被误判为长期沉默强制回收，要么状态紊乱。
- **建议**：改用 `memo.hooks_to_resolve`（已是结构化 ID 列表）驱动推进，或在 Planner 输出中明确"本章推进哪些 hook_id"。

### 3.2 `POST /api/config` 未注册（前后端不一致）

前端 `saveLLMConfig()` 提交 `POST /api/config`，但 [web_server.py 的 do_POST](file:///d:/AI/AI-fanqie/web_server.py) 仅注册了 GET 分支 → 界面保存 LLM 配置落到 `{"error":"not found"}`，保存无效。
- **建议**：补全 POST 分支，调用 `save_global_config`。

### 3.3 `_detect_chapter_type` 默认返回值可疑

[settler.py:L186](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L186) `return genre.chapter_types[-2]`——无匹配时恒返回倒数第二个类型，语义不明且导致类型判定塌缩（详见 2.2）。

### 3.4 facts 只增不清理（内存/存储膨胀）

[settle_chapter](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L49-L51) 持续 `append` 新 fact，但从无设置 `valid_until_chapter` 的逻辑。`CurrentState.facts` 无限增长。
- **建议**：引入事实失效机制（如同一 subject+predicate 的新 fact 使旧 fact `valid_until_chapter` 生效），配合 `get_current_facts()`（已按 `valid_until IS NULL` 过滤）才能真正生效。

### 3.5 章节字数统计口径可能偏差

[writer.py:L274](file:///d:/AI/AI-fanqie/fanqie/engine/writer.py#L274) `len(body.replace(" ", "").replace("\n", ""))` 统计字符数（含标点）作为"字数"。中文场景尚可近似，但标点占比会让实际正文偏短。属轻微问题，注意口径一致即可。

### 3.6 异常处理静默吞掉

[bible_manager.update_items](file:///d:/AI/AI-fanqie/fanqie/memory/bible_manager.py#L153-L207)、[settler._discover_hooks_from_chapter](file:///d:/AI/AI-fanqie/fanqie/engine/settler.py#L450-L454) 均 `except Exception: pass/return []`，静默失败。长跑时难以定位问题。
- **建议**：至少记录一条 warning 日志（不中断流程）。

---

## 4. 性能与成本

### 4.1 字数重试累积对话历史重发 ⭐️

[write_chapter](file:///d:/AI/AI-fanqie/fanqie/engine/writer.py#L267-L293) 的重试循环把上一版整章正文（assistant）+ 纠正指令（user）**append 进 messages 再重发**：

```python
messages.append({"role": "assistant", "content": content})  # 整章正文
messages.append({"role": "user", "content": correction})
```

- **问题**：第 2、3 次重试的输入 = system + user + (上一版整章 ~4000 tokens) …… prompt 线性膨胀，重试越多越贵。
- **建议**：纠正时不必回传整章，可只保留"字数不足/超标"的指令 + 让模型基于原 user prompt 重写；或对超长/超短只做局部续写/裁剪。

### 4.2 每章 LLM 调用次数可能叠加过高

单章潜在调用：Planner ×1 + Writer ×(1~3) + 伏笔发现 ×(每5章1) + Auditor ×1 + Reviser ×(0~3) + Bible items ×(每5章1)。最坏情形一章 ~9 次调用。
- **建议**：把 Writer 字数重试上限与 Reviser 重试上限做全局预算控制；合并"结算摘要 + 伏笔发现"为单次调用。

### 4.3 Protected 上下文每章全量重发

[context_assembly.py:L79-L87](file:///d:/AI/AI-fanqie/fanqie/memory/context_assembly.py#L79-L87) 每章都注入 5 个 protected 文件（各截断 2000 字）。这些文件（世界观/规则/作者意图）**基本不随章节变化**。
- **建议**：对基本不变的 protected 内容做摘要压缩或利用会话级缓存；`current_state.md` 等动态文件才需每章刷新。

### 4.4 facts 膨胀（见 3.4）

长篇后 `current_state.facts` 若全量注入将显著推高 token。需配合失效机制。

---

## 5. 架构与可维护性

### 5.1 双持久化字段重复、无同步机制 ⭐️

`memory/`（JSON+MD）与 `storage/`（SQLite）对 hooks / chapter_summaries / facts / current_state 各存一份，字段高度重叠，但代码中**彼此无引用、无同步**（见依赖分析）。
- **现状风险**：写作流程主要读写 memory 的 JSON/MD；SQLite 主要在 Repository 层由 Orchestrator/CLI 写入，`facts_fts` 全文检索能力实际未被写作链路使用。两套数据可能不一致。
- **建议**：明确"单一事实来源（Single Source of Truth）"。要么让 SQLite 成为唯一结构化源、MD 仅作导出视图；要么保留双写但增加一致性校验。当前 SQLite 的 FTS5 检索优势未被利用，属能力闲置。

### 5.2 Prompt 硬编码散落各模块，难维护

大量 system/user prompt 以多行字符串硬编码在 writer/planner/auditor/settler/architect 中，且含固定业务规则（爽点密度、维度表等）。
- **建议**：抽取为集中的 prompt 模板资源（如 `prompts/` 目录或 TOML），支持按题材覆盖与 A/B 调参。这也能顺带解决 2.4 的差异化需求。

### 5.3 启发式抽取与题材关键词强耦合

settler 的人名姓氏正则、mood/type/conflict 关键词表都硬编码在代码里，新增题材或调整判定需改 Python。
- **建议**：这些启发式若保留（作为 LLM 的降级方案），应把关键词表迁到题材 TOML 配置中；主路径改为 LLM 结构化产出（见第 2 节）。

### 5.4 缺少测试与日志基建

`pyproject.toml` 声明了 pytest/pytest-asyncio/pytest-cov 依赖，但仓库中未见测试目录。长流程、多 LLM 调用的系统尤其需要对**纯逻辑模块**（hook_policy、fatigue_detector、context_assembly 打分、planner 完结窗口计算）做单元测试。
- **建议**：优先为无 LLM 依赖的纯函数补测试；引入结构化日志替代 `except: pass`。

---

## 6. 工程管理与 Git 版本控制

### 6.1 现状：仓库已初始化但零提交 ⭐️

对仓库执行 `git status` / `git log` / `git branch` 的实测结果：

- 仓库**已 `git init`**（存在 `.git`），但**没有任何 commit**（`git log` 为空）。
- **没有任何分支**（`git branch` 无输出，HEAD 尚未指向首个提交）。
- 所有源码文件（`fanqie/`、`web/`、`docs/`、`pyproject.toml` 等）当前均处于 **untracked（`??`）** 状态。
- [.gitignore](file:///d:/AI/AI-fanqie/.gitignore) **已存在且合理**：已忽略 `__pycache__/`、`.venv/`、`data/`（生成的书稿数据）、`*.egg-info/`、`fanqie/genres/custom/*`（保留 `.gitkeep`）、`inkos-ref/` 等。

**影响**：没有版本历史意味着——本报告 P0/P1/P2 的每一处改动都**无法追溯、无法安全回滚**；多点重构（尤其是"结算摘要 LLM 化""伏笔匹配修复"这类跨文件改动）一旦出问题难以定位到引入点；也无法在改动前后对生成质量做对照实验。因此，**建立 git 基线应作为实施任何优化前的第 0 步**。

### 6.2 建议的工程管理措施（不含实际 git 操作）

以下为纳入计划的建议清单，均属工程流程规范，落地时再执行：

1. **建立首个提交基线（P0 前置）**
   - 在动任何优化代码前，先对当前可运行版本做一次干净的 `initial commit`，作为所有后续改动的对照基线。
   - 提交前确认 `.gitignore` 生效（`data/` 等生成物不应入库——现状已正确忽略）。

2. **审查待忽略项**
   - 仓库根目录存在 `1.txt`（用途不明的散落文件）与 `.codex/` —— 建议确认是否应纳入版本控制，或补进 `.gitignore`。
   - `docs/` 下的计划文档（本报告、REFACTOR_PLAN.md 等）建议纳入版本控制，便于计划演进留痕。

3. **分支策略**
   - 采用轻量 `main` + 特性分支模型：每个优化项（如 `feat/llm-summary`、`fix/hook-advance-match`、`fix/web-config-post`）独立开分支，对应本报告的路线图条目。
   - P0 三项因互相关联，建议各自独立分支、独立提交，便于单独回滚与验证。

4. **提交规范（Conventional Commits）**
   - 统一采用 `type(scope): subject` 格式，如 `fix(settler): 修复伏笔推进的 hook_id 子串匹配缺陷`、`feat(settler): 结算阶段 LLM 结构化摘要`、`docs: 补充优化报告`。
   - type 建议限定：`feat` / `fix` / `refactor` / `perf` / `docs` / `test` / `chore`。

5. **标签与里程碑**
   - 当前 `pyproject.toml` 版本为 `0.1.0`。建议每完成一个路线图阶段打 tag（如 `v0.1.1`），并在 commit / tag 说明中对应报告中的优化项编号。

6. **提交前质量门禁**
   - 结合 5.4 的测试建议：为纯逻辑模块（hook_policy、fatigue_detector、context_assembly、planner 完结窗口计算）补单元测试后，配置 pre-commit 或轻量 CI（如 GitHub Actions）在提交/PR 时运行 `pytest` + lint。
   - `pyproject.toml` 已声明 `pytest`/`pytest-cov` 依赖，具备接入基础。

7. **敏感信息防护**
   - LLM `api_key` 存于 `~/.fanqie/config.yaml`（用户目录，不在仓库内）与环境变量 `FANQIE_API_KEY`，当前设计已避免入库。规范中应明确：**严禁将含真实 key 的 `fanqie.yaml` 项目级配置提交**，必要时在 `.gitignore` 补充 `fanqie.yaml`。

---

## 7. 优先级路线图

### P0 — 直接影响剧情质量与正确性
0. **建立 git 提交基线**（6.2）—— 实施任何改动前的第 0 步，先提交当前可运行版本作为对照与回滚锚点。
1. **结算摘要 LLM 化**（2.1 + 2.2 + 2.5 合并为一次调用）—— 修复剧情单调第一根因。
2. **修复伏笔推进匹配逻辑**（3.1）—— 恢复伏笔生命周期功能。
3. **疲劳信号前置到 Planner**（2.3）—— 从生成端主动防单调。

### P1 — 明显收益 / 低风险
4. Writer 爽点密度按章节类型差异化（2.4）。
5. 修正 `_detect_chapter_type` 默认返回（3.3）与疲劳阈值（2.3）。
6. 补全 `POST /api/config`（3.2）。
7. 字数重试不再回传整章（4.1）。

### P2 — 结构性改进
8. facts 失效机制（3.4 + 4.4）。
9. 明确双持久化的单一事实来源（5.1）。
10. Prompt 模板集中化 + 关键词表配置化（5.2 / 5.3）。
11. 为纯逻辑模块补单元测试（5.4）。
12. 落地 git 工程规范：分支策略 + Conventional Commits + 版本 tag + pre-commit/CI 门禁（6.2）。

---

*本报告基于对 writer.py、settler.py、fatigue_detector.py、context_assembly.py、hook_lifecycle.py、auditor.py 等文件的直接审查，所有问题均可溯源到具体代码位置。报告不含任何代码改动。*
