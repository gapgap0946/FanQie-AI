# 项目规则（fanqie）

## 文档维护
- **每次改动功能后都要同步更新 `README.md`**：新增/修改命令、API、Web 入口、配置项、数据目录结构等，都要在 README 对应小节反映出来，保持文档与代码一致。

## 运行环境
- 本项目依赖安装在 **Python 3.9**（`pip install -e .`）。机器上另有 Python 3.10 但未装依赖。
- 启动 Web 服务必须用装了依赖的 Python：`python web_server.py`（默认 `python` 即 3.9）。用错版本会报 `No module named 'click'`。
- 修改后端（`web_server.py` 或 `fanqie/` 下的 Python）后需**重启** Web 服务才生效；纯前端（`web/index.html`）改动刷新浏览器即可。
- Web 服务默认端口 **8765**。

## 验证约定
- 改 Python 后用 `ast.parse` 做语法检查、按需做导入/端到端小测。
- 改 `web/index.html` 后用 HTMLParser 校验结构。
- 提交前尽量跑一次相关的最小验证。
