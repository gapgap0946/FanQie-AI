# 题材模板 + 黄金三章 — 实施计划

## 一、创建题材时提供模板

### 现状

创建自定义题材时，只有一个空下拉框选基础模板，用户不知道每个模板里有什么。

### 改动

**`web/index.html` — 题材管理弹窗改造：**

1. 左侧"现有题材"列表改为可展开的卡片式：
   - 每个题材显示：名称、简介（一行）、章节类型、爽点类型
   - 点击展开查看完整 TOML 配置
2. 右侧"创建新题材"加模板预览：
   - 选择基础模板后，下方显示该模板的关键信息摘要
   - "章节类型 / 爽点类型 / 节奏规则 / 禁忌" 一目了然
3. 加一个"复制模板"按钮：一键复制现有模板的 TOML 到编辑区

### 文件改动

| 文件 | 改动 |
|---|---|
| `web/index.html` | 题材弹窗 UI 改造 |

---

## 二、黄金三章支持

### 融合方案：结构框架（方案一）+ 写作技法（方案二）

| 章节 | 结构框架 | 写作技法 |
|---|---|---|
| **第 1 章** | 事件 → 背景 → 发展 → 钩子 | 300 字冲突种子 + 500 字主角亮相 + 10-20 字世界观 |
| **第 2 章** | 信息 → 发展 → 钩子 | 金手指亮相（戏剧性场景）+ 冲突升级（人际/资源/认知） |
| **第 3 章** | 阻碍 → 升级 → 期待感 | 至少 1 个爽点 + 信息差/危机预告钩子 + 每 800 字情绪爆点 |

### 实现方案

#### 1. 题材模板加黄金三章配置

每个 `.toml` 文件新增 `[craft.golden_three]` 段：

```toml
[craft.golden_three]
chapter_1_structure = "事件→背景→发展→钩子"
chapter_1_rules = [
    "前300字必须有强冲突（死亡/背叛/危机），拒绝流水账",
    "500字内主角亮相，用动作/台词立人设",
    "世界观用10-20字极简点出，不堆设定",
    "章末必须有'下一章会怎样'的强烈钩子",
]
chapter_2_structure = "信息→发展→钩子"
chapter_2_rules = [
    "金手指必须在第2章亮相，用戏剧性场景展示",
    "金手指首次使用有明显效果，规则简单清晰",
    "补充人物关系和世界观细节，但通过剧情展示而非叙述",
    "冲突升级：叠加人际/资源/认知三重压力",
]
chapter_3_structure = "阻碍→升级→期待感"
chapter_3_rules = [
    "必须有至少1个爽点（打脸/收获/反转）",
    "每800字设一个情绪爆点",
    "章末设置信息差/危机预告/选择困境钩子",
    "让读者产生'必须读第四章'的冲动",
]
```

#### 2. 数据模型

`models.py` 新增：

```python
class GoldenThreeConfig(BaseModel):
    """黄金三章配置."""
    chapter_1_structure: str = ""
    chapter_1_rules: list[str] = Field(default_factory=list)
    chapter_2_structure: str = ""
    chapter_2_rules: list[str] = Field(default_factory=list)
    chapter_3_structure: str = ""
    chapter_3_rules: list[str] = Field(default_factory=list)
```

`GenreProfile` 加 `golden_three_config: GoldenThreeConfig | None`

#### 3. Planner 注入黄金三章逻辑

`planner.py` 的 `plan_chapter()` 中：

```python
if chapter_number <= 3 and genre.golden_three_config:
    system_prompt = build_golden_three_planner_prompt(genre, chapter_number)
```

每章有专属的 system prompt，强调该章的结构框架和核心任务。

#### 4. Writer 注入黄金三章约束

`writer.py` 的 `build_writer_system_prompt()` 中：

```python
if chapter_number <= 3 and golden_three_config:
    prompt += render_golden_three_rules(golden_three_config, chapter_number)
```

注入该章的具体写作规则。

#### 5. Auditor 加黄金三章专项检查

`auditor.py` 中前 3 章额外检查：
- 第 1 章：前 300 字是否有冲突/悬念
- 第 2 章：金手指是否亮相、是否通过剧情展示世界观
- 第 3 章：是否有爽点、是否有强烈钩子

### 文件改动

| 文件 | 改动 |
|---|---|
| `models.py` | 新增 `GoldenThreeConfig`，`GenreProfile` 加字段 |
| `genres/builtin/*.toml` | 6 个模板各加 `[craft.golden_three]` |
| `genres/loader.py` | `GenreProfile.from_toml()` 解析 `golden_three` |
| `engine/planner.py` | 前 3 章用黄金三章专用 prompt |
| `engine/writer.py` | 前 3 章注入黄金三章写作规则 |
| `engine/auditor.py` | 前 3 章专项检查 |

---

## 执行顺序

1. 数据模型（models.py + loader.py）
2. 题材模板配置（6 个 toml）
3. 黄金三章 Planner/Writer/Auditor
4. 题材管理 UI 改造
