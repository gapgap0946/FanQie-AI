# fanqie — 爽文 AI 智能体

> 长篇网文创作引擎，专为百万字以上爽文设计。基于 LLM，具备防幻觉、长期记忆、伏笔管理能力，适配所有 OpenAI 兼容协议的大模型。

`fanqie`（番茄）帮你从一句创意开始，自动生成世界观、卷纲，并逐章写出结构完整、前后连贯、爽点密集的长篇小说。支持命令行和网页两种使用方式。

---

## ✨ 核心能力

- **一句话开书**：输入书名和题材，自动生成世界观基石（Foundation）与分卷大纲。
- **防幻觉写作**：每章先生成结构化写作指令，写完后经 20+ 维度连贯性审查并自动修订，避免人物/设定崩坏。
- **长期记忆**：分层上下文 + 伏笔生命周期管理 + 故事圣经，支撑百万字不失忆、不埋坑不填。
- **反套路机制**：自动检测开头/结尾重复、情绪单调、章节类型固化，主动打破模板化。
- **6 大内置题材**：玄幻、规则怪谈、全民穿越、克系修仙、末世、诡异降临，也支持自定义。
- **文风仿写**：分析参考小说的句长、段落、修辞特征，让 AI 贴合你想要的笔触。
- **两种界面**：命令行（CLI）+ 本地网页管理界面（Web UI）。

---

## 🚀 安装

需要 **Python 3.9 或更高版本**。

```bash
git clone https://github.com/你的用户名/fanqie.git
cd fanqie
pip install -e .
fanqie --help
```

依赖会自动安装：`click`、`rich`、`pydantic`、`httpx`、`pyyaml`、`tomli`。

---

## ⚙️ 第一步：配置大模型

fanqie 的写作、审查全靠大模型驱动，使用前必须先配置。支持所有 OpenAI 兼容 API（DeepSeek、通义千问 Qwen、智谱 GLM 等）。

```bash
fanqie config set --base-url https://api.deepseek.com/v1 --api-key sk-你的密钥 --model deepseek-chat
fanqie config show   # 确认配置
```

> 配置保存在用户目录 `~/.fanqie/config.yaml`，不会进入项目仓库。也可用环境变量 `FANQIE_API_KEY` 提供密钥。

---

## 📖 使用方式一：命令行

### 1. 选择题材

```bash
fanqie genre list            # 查看所有题材
fanqie genre show xuanhuan   # 查看某题材详情
```

| ID | 名称 | 特点 |
|----|------|------|
| `xuanhuan` | 玄幻 | 修炼体系 + 势力对抗 + 主角逆袭 |
| `rule_horror` | 规则怪谈 | 诡异规则驱动，氛围优先 |
| `mass_isekai` | 全民穿越求生 | 数值体系 + 资源争夺 |
| `cthulhu_cultivation` | 克系修仙 | san 值替代道心，诡异替代天劫 |
| `apocalypse` | 末世 | 生存压力 + 人性考验 |
| `weird_descend` | 诡异降临 | 日常场景异常化，能力觉醒 |

### 2. 创建新书

```bash
fanqie new "我的第一本爽文" --genre xuanhuan --words 2000 --chapters 500
```

| 选项 | 说明 | 默认 |
|------|------|------|
| `--genre / -g` | 题材 ID | `xuanhuan` |
| `--words / -w` | 每章目标字数 | `2000` |
| `--chapters / -c` | 目标总章数 | `500` |
| `--brief / -b` | 创意简报文件（可选） | — |

命令执行后会输出一个 **book_id**，后续操作都用它。

### 3. 开始写作

```bash
fanqie write <book_id>            # 写 1 章
fanqie write <book_id> -n 5       # 连续写 5 章
fanqie write <book_id> -i "让主角这一章遭遇背叛"   # 带干预指令
```

### 4. 查看进度 / 完结 / 导出

```bash
fanqie status <book_id>                    # 查看章数、伏笔、完结进度
fanqie complete <book_id>                  # 手动收尾完结
fanqie export <book_id> -f md -o 我的小说.md # 导出（txt / md）
```

### 5. 文风仿写（可选）

```bash
fanqie style analyze 参考小说.txt --output style.json  # 分析参考文风
fanqie style import style.json <book_id>              # 应用到你的书
```

### 6. 修改设定（人机协作）

```bash
fanqie advise <book_id> "把主角的师父改成隐藏反派" --dry-run  # 先分析影响
fanqie advise <book_id> "把主角的师父改成隐藏反派"           # 执行修改
```

---

## 🖥️ 使用方式二：网页界面

```bash
python web_server.py
```

启动后在浏览器打开 **http://127.0.0.1:8765**，即可可视化地建书、写章、查看章节与伏笔状态、修改设定、导出成品，还带一个「创意顾问」聊天助手。

---

## 📂 生成的内容存在哪

每本书的数据保存在 `data/<book_id>/` 目录下：

```
data/<book_id>/
├── book.db          # SQLite 数据库（结构化数据）
├── chapters/        # 章节正文（Markdown，按卷分目录）
└── story/           # 世界观、大纲、伏笔、状态等记忆文件
```

> `data/` 目录已被 `.gitignore` 忽略，不会上传到仓库。

---

## 🔧 配置项参考

全局配置 `~/.fanqie/config.yaml`（也可在项目目录放 `fanqie.yaml` 覆盖）：

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

---

## 🎨 自定义题材

```bash
fanqie genre create my_genre --from xuanhuan
```

会在 `fanqie/genres/custom/` 生成一份 TOML 模板供你编辑，包含题材名称、章节类型、爽点类型、节奏规则、审查维度等字段。

---

## License

MIT
