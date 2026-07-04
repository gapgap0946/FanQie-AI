# AI 聊天面板 — 实施计划

## 目标

在 Fanqie Web UI 右侧增加 AI 对话面板，作为"小说设定点子王"创意顾问。

## 布局

```
┌──────────┬──────────────────┬───────────┐
│          │                  │           │
│ Sidebar  │   Main Content   │ AI 对话   │
│ 260px    │   (flex:1)       │ 340px     │
│          │                  │ 可折叠    │
└──────────┴──────────────────┴───────────┘
```

## 后端改动

### `web_server.py`

**新增端点：**

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/chat` | POST | 发送消息，返回 `{reply, timestamp}` |
| `/api/chat/history` | GET | 返回对话历史 JSON |

**实现细节：**

- 调 fanqie 配置的 LLM（`fanqie.llm.client.LLMClient`）
- 对话历史存 `data/_chat_history.json`，最多保留 100 条
- 非流式，简单 request/response

**System Prompt：**

```
你是番茄小说平台的创意顾问，专精网文设定和剧情设计。
你的风格：脑洞大、点子多、一针见血。擅长帮作者：
- 设计独特的力量体系、世界观规则
- 构思反转、伏笔、爽点
- 解决剧情卡点和逻辑漏洞
- 给角色注入灵魂（动机、缺陷、弧光）
说话直接，不绕弯，每个建议都有具体例子。
```

## 前端改动

### `web/index.html`

**CSS 新增：**
- `.chat-panel` — 右侧面板，340px 宽，flex 列布局
- `.chat-messages` — 消息滚动区
- `.chat-bubble` — 聊天气泡（用户蓝底右对齐，AI 灰底左对齐）
- `.chat-input-area` — 输入框 + 发送按钮
- `.chat-panel.collapsed` — 折叠状态（只显示标题栏）

**HTML 新增：**
- 聊天面板 DOM（在 `.app` 内，`.main` 之后）

**JS 新增：**
- `sendChat()` — 发送消息，调 `/api/chat`
- `loadChatHistory()` — 加载历史
- `toggleChat()` — 折叠/展开
- 页面加载时自动加载历史

**移动端适配：**
- `<1024px` 时聊天面板默认隐藏
- 顶部加一个 💬 按钮呼出

## 不做的

- 不流式（SSE）
- 不感知书籍上下文
- 不按书分对话历史
- 不持久化到数据库

## 文件清单

| 文件 | 改动 |
|---|---|
| `web_server.py` | 新增 2 个 API 端点 |
| `web/index.html` | CSS + HTML + JS 新增聊天面板 |
