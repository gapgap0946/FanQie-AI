# fanqie — 爽文 AI 智能体

长篇网文创作引擎，专为百万字以上爽文设计。核心借鉴 InkOS 的防幻觉与长期记忆架构，适配国产大模型（OpenAI 兼容协议），SQLite + 本地文件存储。

## 核心能力

- **防幻觉**：Chapter Memo（7段结构化指令）+ Continuity Auditor（20+维度审查）+ 自动修订
- **长期记忆**：Protected/Compressible 分层上下文 + 伏笔生命周期管理 + 长跨度疲劳检测
- **题材模板**：6 个内置题材（玄幻、规则怪谈、全民穿越、克系修仙、末世、诡异降临），支持自定义
- **文风仿写**：纯文本统计分析（句长/段长/TTR/修辞），无需 LLM，结果注入 system prompt

## 架构

```
Plan -> Compose -> Write -> Settle -> Audit -> Revise
  |        |         |        |        |        |
  |   Chapter Memo    |   状态更新    |   自动修订   |
  |   (7段结构)      |   伏笔推进    |   (最多N次)  |
  +-------------------+--------------+--------------+
```

### 防幻觉机制

| 阶段 | 机制 | 说明 |
|------|------|------|
| 写作前 | Chapter Memo | 每章生成 7 段结构化指令，限定输出范围 |
| 写作前 | 分层上下文 | Protected（不可压缩）vs Compressible（可压缩） |
| 写作后 | Continuity Auditor | 20+ 维度审查（OOC、事实一致性、伏笔、节奏等） |
| 写作后 | 自动修订 | 根据审计结果自动修复，最多 N 次重试 |
| 全周期 | 伏笔生命周期 | 压力计算、stale/overdue 检测、强制回收 |
| 全周期 | 疲劳检测 | 开头/结尾模式重复、标题塌缩、情绪单调、章节类型固化 |

## 安装

```bash
git clone <repo-url> fanqie
cd fanqie
pip install -e "."
fanqie --help
```

依赖：Python 3.9+，pydantic、click、rich、httpx、pyyaml、tomli。

## 快速开始

### 1. 配置 LLM

```bash
fanqie config set --base-url https://your-api.com/v1 --api-key sk-xxx --model deepseek-chat
fanqie config show
```

支持所有 OpenAI 兼容协议的模型（DeepSeek、Qwen、GLM、mimo 等）。

### 2. 选择题材

```bash
fanqie genre list          # 查看可用题材
fanqie genre show xuanhuan # 查看题材详情
fanqie genre create my_genre --from xuanhuan  # 创建自定义题材
```

内置题材：

| ID | 名称 | 特点 |
|----|------|------|
| `xuanhuan` | 玄幻 | 修炼体系+势力对抗+主角逆袭 |
| `rule_horror` | 规则怪谈 | 诡异规则驱动，氛围优先 |
| `mass_isekai` | 全民穿越求生 | 数值体系+资源争夺 |
| `cthulhu_cultivation` | 克系修仙 | san值替代道心，诡异替代天劫 |
| `apocalypse` | 末世 | 生存压力+人性考验 |
| `weird_descend` | 诡异降临 | 日常场景异常化，能力觉醒 |

### 3. 创建新书

```bash
fanqie new "我的第一本爽文" --genre xuanhuan --words 2000 --chapters 500
```

参数：
- `--genre / -g`：题材 ID
- `--words / -w`：每章目标字数（默认 2000）
- `--chapters / -c`：目标总章数（默认 500）

### 4. 文风仿写（可选）

```bash
fanqie style analyze 参考小说.txt --output style.json  # 分析文风
fanqie style import style.json <book_id>               # 导入到书
fanqie style show <book_id>                            # 查看文风
fanqie style remove <book_id>                          # 移除文风
```

文风分析提取：平均句长、段长、词汇多样性（TTR）、高频开头模式、修辞特征密度。
分析结果注入 Writer 的 system prompt，AI 生成时会主动贴合这些统计特征。

### 5. 开始写作

```bash
fanqie write <book_id>              # 写一章
fanqie write <book_id> -n 5         # 连续写 5 章
fanqie write <book_id> -i "指令"    # 带干预指令
```

### 6. 查看状态

```bash
fanqie status <book_id>
```

### 7. 导出

```bash
fanqie export <book_id>           # 导出为 txt
fanqie export <book_id> -f md     # 导出为 markdown
fanqie export <book_id> -o 输出.txt
```

## 项目结构

```
fanqie/
├── models.py                    # Pydantic 数据模型
├── engine/
│   ├── orchestrator.py          # 写作主循环
│   ├── planner.py               # Chapter Memo 生成
│   ├── composer.py              # 上下文组装
│   ├── writer.py                # 章节生成（含文风注入）
│   ├── settler.py               # 章后结算
│   ├── auditor.py               # Continuity Auditor
│   ├── reviser.py               # 自动修订
│   └── intervener.py            # 人工干预
├── memory/
│   ├── state_manager.py         # JSON 状态读写
│   ├── hook_policy.py           # 伏笔策略
│   ├── hook_lifecycle.py        # 伏笔生命周期
│   ├── context_assembly.py      # 上下文组装
│   └── fatigue_detector.py      # 疲劳检测
├── style/
│   ├── profile.py               # StyleProfile 模型
│   ├── analyzer.py              # 文风分析（纯统计）
│   └── injector.py              # 文风注入
├── genres/
│   ├── loader.py                # 模板加载器
│   ├── builtin/                 # 6 个内置题材
│   └── custom/                  # 用户自定义题材
├── llm/client.py                # OpenAI 兼容客户端
├── storage/                     # SQLite 数据库
├── cli/main.py                  # Click + Rich CLI
└── utils/config.py              # 配置管理
```

## 配置

全局配置存储在 `~/.fanqie/config.yaml`，项目级配置可放在工作目录的 `fanqie.yaml`。

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

## 题材模板格式

自定义题材放在 `fanqie/genres/custom/` 目录，TOML 格式：

```toml
[meta]
name = "我的题材"
id = "my_genre"
description = "题材描述"

[craft]
chapter_types = ["事件章", "过渡章", "高潮章"]
fatigue_words = ["疲劳词1", "疲劳词2"]
pacing_rule = "节奏规则描述"
satisfaction_types = ["打脸", "升级", "真相揭示"]

[craft.rules]
atmosphere = "氛围规则"
pacing = "节奏规则"
character = "角色规则"
language = "语言规则"

[prohibitions]
items = ["禁止项1", "禁止项2"]

[audit]
dimensions = [1, 2, 3, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 18, 19, 24, 25, 26]
```

## 路线图

- **V1**（当前）：核心引擎 + CLI
- **V2**（计划中）：React Web 界面，可视化写作仪表盘
- **V3**（计划中）：多书并行、协作写作、章节分支管理

## License

MIT