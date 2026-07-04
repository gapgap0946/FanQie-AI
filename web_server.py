"""Fanqie Web Server — 异步任务模式 + 进度反馈."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

FANQIE_DIR = Path(__file__).resolve().parent
DATA_DIR = FANQIE_DIR / "data"

if str(FANQIE_DIR) not in sys.path:
    sys.path.insert(0, str(FANQIE_DIR))

# 任务状态存储
_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


def _run_task(task_id: str, cmd: list[str], cwd: str, timeout: int = 600):
    """在后台线程运行 fanqie CLI 命令，实时更新状态."""
    with _tasks_lock:
        _tasks[task_id]["status"] = "running"
        _tasks[task_id]["started_at"] = time.time()

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding="utf-8", errors="replace",
            env=env,
        )
        with _tasks_lock:
            _tasks[task_id]["pid"] = proc.pid

        output_lines = []
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                output_lines.append(line)
                with _tasks_lock:
                    _tasks[task_id]["output"] = "\n".join(output_lines[-50:])
                    _tasks[task_id]["lines"] = len(output_lines)

        proc.wait(timeout=timeout)

        with _tasks_lock:
            _tasks[task_id]["status"] = "done" if proc.returncode == 0 else "error"
            _tasks[task_id]["returncode"] = proc.returncode
            _tasks[task_id]["output"] = "\n".join(output_lines)
            _tasks[task_id]["finished_at"] = time.time()

    except subprocess.TimeoutExpired:
        proc.kill()
        with _tasks_lock:
            _tasks[task_id]["status"] = "timeout"
            _tasks[task_id]["output"] = "\n".join(output_lines) + "\n[超时]"
    except Exception as e:
        with _tasks_lock:
            _tasks[task_id]["status"] = "error"
            _tasks[task_id]["output"] = str(e)


def _start_task(cmd: list[str], cwd: str, label: str = "", timeout: int = 600) -> str:
    """启动一个后台任务，返回 task_id."""
    task_id = str(uuid.uuid4())[:8]
    with _tasks_lock:
        _tasks[task_id] = {
            "id": task_id,
            "label": label,
            "status": "pending",
            "output": "",
            "lines": 0,
            "returncode": None,
            "started_at": None,
            "finished_at": None,
            "pid": None,
        }
    t = threading.Thread(target=_run_task, args=(task_id, cmd, cwd, timeout), daemon=True)
    t.start()
    return task_id


class FanqieAPI(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_html(self, html, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_file(self, path, content_type):
        if not os.path.exists(path):
            self._send_json({"error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        with open(path, "rb") as f:
            self.wfile.write(f.read())

    def do_OPTIONS(self):
        self._send_json({})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            self._send_file(FANQIE_DIR / "web" / "index.html", "text/html; charset=utf-8")
        elif path == "/api/books":
            self._list_books()
        elif path == "/api/book":
            self._get_book(qs.get("id", [""])[0])
        elif path == "/api/chapters":
            self._get_chapters(qs.get("id", [""])[0])
        elif path == "/api/chapter":
            self._get_chapter(qs.get("id", [""])[0], qs.get("ch", ["1"])[0])
        elif path == "/api/genres":
            self._list_genres()
        elif path == "/api/genre-detail":
            self._get_genre_detail(qs.get("id", [""])[0])
        elif path == "/api/story-file":
            self._get_story_file(qs.get("id", [""])[0], qs.get("file", [""])[0])
        elif path == "/api/config":
            self._get_config()
        elif path == "/api/task":
            self._get_task(qs.get("id", [""])[0])
        elif path == "/api/chat/history":
            self._get_chat_history()
        elif path.startswith("/web/"):
            file_path = FANQIE_DIR / path.lstrip("/")
            ct = "text/css" if path.endswith(".css") else "application/javascript" if path.endswith(".js") else "text/html"
            self._send_file(file_path, f"{ct}; charset=utf-8")
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}
        parsed = urlparse(self.path)

        if parsed.path == "/api/new":
            self._create_book(body)
        elif parsed.path == "/api/write":
            self._write_chapter(body)
        elif parsed.path == "/api/advise":
            self._advise(body)
        elif parsed.path == "/api/export":
            self._export_book(body)
        elif parsed.path == "/api/create-genre":
            self._create_genre(body)
        elif parsed.path == "/api/chat":
            self._chat(body)
        elif parsed.path == "/api/audit":
            self._audit_chapter(body)
        elif parsed.path == "/api/delete":
            self._delete_book(body)
        else:
            self._send_json({"error": "not found"}, 404)

    # ---- API Handlers ----

    def _list_books(self):
        books = []
        if DATA_DIR.exists():
            for d in sorted(DATA_DIR.iterdir(), reverse=True):
                if d.is_dir() and (d / "book.db").exists():
                    try:
                        from fanqie.storage.repository import Repository
                        repo = Repository(str(DATA_DIR), d.name)
                        book = repo.get_book()
                        if book:
                            ch_count = repo.get_chapter_count()
                            books.append({
                                "id": book["id"],
                                "title": book["title"],
                                "genre_id": book.get("genre_id", ""),
                                "status": book.get("status", "draft"),
                                "chapters": ch_count,
                                "target_chapters": book.get("target_chapters", 500),
                                "updated_at": book.get("updated_at", ""),
                            })
                    except Exception:
                        pass
        self._send_json(books)

    def _get_book(self, book_id):
        if not book_id:
            self._send_json({"error": "missing id"}, 400)
            return
        try:
            from fanqie.storage.repository import Repository
            from fanqie.memory.state_manager import StateManager
            repo = Repository(str(DATA_DIR), book_id)
            book = repo.get_book()
            if not book:
                self._send_json({"error": "book not found"}, 404)
                return
            state_mgr = StateManager(str(DATA_DIR / book_id))
            hook_pool = state_mgr.load_hook_pool()
            active_hooks = len([h for h in hook_pool.hooks if h.status.value not in ("resolved", "deferred")])
            current_state = state_mgr.load_current_state()
            self._send_json({
                "id": book["id"], "title": book["title"],
                "genre_id": book.get("genre_id", ""),
                "status": book.get("status", "draft"),
                "chapters": repo.get_chapter_count(),
                "target_chapters": book.get("target_chapters", 500),
                "chapter_word_count": book.get("chapter_word_count", 2000),
                "active_hooks": active_hooks,
                "total_hooks": len(hook_pool.hooks),
                "current_conflict": current_state.current_conflict,
                "current_location": current_state.current_location,
                "updated_at": book.get("updated_at", ""),
            })
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_chapters(self, book_id):
        if not book_id:
            self._send_json({"error": "missing id"}, 400)
            return
        try:
            from fanqie.storage.repository import Repository
            repo = Repository(str(DATA_DIR), book_id)
            chapters = repo.get_all_chapters()
            result = [{
                "chapter_number": ch["chapter_number"],
                "title": ch.get("title", ""),
                "word_count": ch.get("word_count", 0),
                "status": ch.get("status", "draft"),
                "audit_score": ch.get("audit_score"),
            } for ch in chapters]
            self._send_json(result)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_chapter(self, book_id, chapter_number):
        if not book_id:
            self._send_json({"error": "missing id"}, 400)
            return
        try:
            ch_num = int(chapter_number)
            chapters_dir = DATA_DIR / book_id / "chapters"
            content = ""
            for vol_dir in sorted(chapters_dir.glob("vol*")):
                ch_file = vol_dir / f"{ch_num:04d}.md"
                if ch_file.exists():
                    content = ch_file.read_text(encoding="utf-8")
                    break
            if not content:
                ch_file = chapters_dir / f"{ch_num:04d}.md"
                if ch_file.exists():
                    content = ch_file.read_text(encoding="utf-8")
            self._send_json({"chapter_number": ch_num, "content": content})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _list_genres(self):
        try:
            from fanqie.genres.loader import list_all_genres, load_genre
            all_genres = list_all_genres()
            result = [{"id": gid, "name": g.name if (g := load_genre(gid)) else gid,
                       "description": g.description if g else "", "source": src}
                      for gid, src in sorted(all_genres.items())]
            self._send_json(result)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_story_file(self, book_id, filename):
        if not book_id or not filename:
            self._send_json({"error": "missing params"}, 400)
            return
        safe_name = os.path.basename(filename)
        if not safe_name.endswith(".md"):
            self._send_json({"error": "only .md files allowed"}, 403)
            return
        file_path = DATA_DIR / book_id / "story" / safe_name
        if not file_path.exists():
            file_path = DATA_DIR / book_id / "story" / "foundation" / safe_name
        if not file_path.exists():
            file_path = DATA_DIR / book_id / "story" / "characters" / safe_name
        if not file_path.exists():
            file_path = DATA_DIR / book_id / "story" / "foundation" / "characters" / safe_name
        if not file_path.exists():
            self._send_json({"error": "file not found"}, 404)
            return
        content = file_path.read_text(encoding="utf-8")
        self._send_json({"file": safe_name, "content": content})

    def _get_config(self):
        try:
            from fanqie.utils.config import load_config
            cfg = load_config()
            llm = cfg.get("llm", {})
            self._send_json({"base_url": llm.get("base_url", ""), "model": llm.get("model", ""),
                             "has_key": bool(llm.get("api_key", "")),
                             "temperature": llm.get("temperature", 0.7),
                             "max_tokens": llm.get("max_tokens", 4096)})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_task(self, task_id):
        if not task_id:
            self._send_json({"error": "missing id"}, 400)
            return
        with _tasks_lock:
            task = _tasks.get(task_id)
        if not task:
            self._send_json({"error": "task not found"}, 404)
            return
        self._send_json(task)

    # ---- Async Actions (return task_id immediately) ----

    def _create_book(self, body):
        title = body.get("title", "").strip()
        genre_id = body.get("genre_id", "xuanhuan")
        words = body.get("words", 2000)
        chapters = body.get("chapters", 500)
        brief = body.get("brief", "")
        if not title:
            self._send_json({"error": "书名不能为空"}, 400)
            return
        cmd = [sys.executable, "-m", "fanqie.cli.main", "new", title,
               "-g", genre_id, "-w", str(words), "-c", str(chapters), "-y"]
        if brief:
            brief_path = DATA_DIR / "_temp_brief.txt"
            brief_path.write_text(brief, encoding="utf-8")
            cmd.extend(["-b", str(brief_path)])
        task_id = _start_task(cmd, str(FANQIE_DIR), f"创建《{title}》", timeout=600)
        self._send_json({"task_id": task_id, "status": "pending"})

    def _write_chapter(self, body):
        book_id = body.get("id", "")
        count = body.get("count", 1)
        instruction = body.get("instruction", "")
        if not book_id:
            self._send_json({"error": "missing id"}, 400)
            return
        cmd = [sys.executable, "-m", "fanqie.cli.main", "write", book_id, "-n", str(count)]
        if instruction:
            cmd.extend(["-i", instruction])
        task_id = _start_task(cmd, str(FANQIE_DIR), f"写 {count} 章", timeout=600)
        self._send_json({"task_id": task_id, "status": "pending"})

    def _advise(self, body):
        book_id = body.get("id", "")
        instruction = body.get("instruction", "")
        if not book_id or not instruction:
            self._send_json({"error": "missing params"}, 400)
            return
        cmd = [sys.executable, "-m", "fanqie.cli.main", "advise", book_id, instruction]
        task_id = _start_task(cmd, str(FANQIE_DIR), "修改设定", timeout=300)
        self._send_json({"task_id": task_id, "status": "pending"})

    def _audit_chapter(self, body):
        book_id = body.get("id", "")
        chapter_number = body.get("chapter_number", 0)
        retry = body.get("retry", 3)
        if not book_id or not chapter_number:
            self._send_json({"error": "missing params"}, 400)
            return
        cmd = [sys.executable, "-m", "fanqie.cli.main", "audit", book_id, str(chapter_number), "-r", str(retry)]
        task_id = _start_task(cmd, str(FANQIE_DIR), f"审计第{chapter_number}章", timeout=600)
        self._send_json({"task_id": task_id, "status": "pending"})

    def _export_book(self, body):
        book_id = body.get("id", "")
        fmt = body.get("format", "md")
        if not book_id:
            self._send_json({"error": "missing id"}, 400)
            return
        output_path = DATA_DIR / f"{book_id}_export.{fmt}"
        cmd = [sys.executable, "-m", "fanqie.cli.main", "export", book_id, "-f", fmt, "-o", str(output_path)]
        task_id = _start_task(cmd, str(FANQIE_DIR), "导出", timeout=60)
        self._send_json({"task_id": task_id, "status": "pending"})

    def _delete_book(self, body):
        book_id = body.get("id", "")
        if not book_id:
            self._send_json({"error": "missing id"}, 400)
            return
        import shutil
        book_dir = DATA_DIR / book_id
        if not book_dir.exists():
            self._send_json({"error": "书籍不存在"}, 404)
            return
        try:
            shutil.rmtree(book_dir)
            self._send_json({"success": True, "message": f"已删除 {book_id}"})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _get_genre_detail(self, genre_id):
        if not genre_id:
            self._send_json({"error": "missing id"}, 400)
            return
        try:
            from fanqie.genres.loader import load_genre, get_genre_path
            g = load_genre(genre_id)
            if not g:
                self._send_json({"error": "题材不存在"}, 404)
                return
            path = get_genre_path(genre_id) or ""
            if path:
                content = Path(path).read_text(encoding="utf-8")
            else:
                content = ""
            self._send_json({
                "id": g.id, "name": g.name, "description": g.description,
                "chapter_types": g.chapter_types, "satisfaction_types": g.satisfaction_types,
                "pacing_rule": g.pacing_rule, "prohibitions": g.prohibitions,
                "rules": g.rules, "source_path": path, "toml": content,
            })
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    # ---- Chat API ----

    CHAT_SYSTEM_PROMPT = (
        "你是番茄小说平台的创意顾问，专精网文设定和剧情设计。\n"
        "你的风格：脑洞大、点子多、一针见血。擅长帮作者：\n"
        "- 设计独特的力量体系、世界观规则\n"
        "- 构思反转、伏笔、爽点\n"
        "- 解决剧情卡点和逻辑漏洞\n"
        "- 给角色注入灵魂（动机、缺陷、弧光）\n"
        "说话直接，不绕弯，每个建议都有具体例子。"
    )

    CHAT_HISTORY_FILE = DATA_DIR / "_chat_history.json"
    CHAT_MAX_HISTORY = 100

    def _load_chat_history(self) -> list[dict]:
        if self.CHAT_HISTORY_FILE.exists():
            try:
                return json.loads(self.CHAT_HISTORY_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save_chat_history(self, history: list[dict]):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if len(history) > self.CHAT_MAX_HISTORY:
            history = history[-self.CHAT_MAX_HISTORY:]
        self.CHAT_HISTORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _get_chat_history(self):
        history = self._load_chat_history()
        self._send_json(history)

    def _chat(self, body):
        message = body.get("message", "").strip()
        if not message:
            self._send_json({"error": "消息不能为空"}, 400)
            return

        try:
            from fanqie.llm.client import LLMClient
            client = LLMClient()

            history = self._load_chat_history()
            messages = [{"role": "system", "content": self.CHAT_SYSTEM_PROMPT}]
            for entry in history:
                messages.append({"role": entry["role"], "content": entry["content"]})
            messages.append({"role": "user", "content": message})

            result = client.chat(messages)
            reply = result["content"]
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

            history.append({"role": "user", "content": message, "timestamp": timestamp})
            history.append({"role": "assistant", "content": reply, "timestamp": timestamp})
            self._save_chat_history(history)

            self._send_json({"reply": reply, "timestamp": timestamp})
        except Exception as e:
            self._send_json({"error": f"AI 回复失败: {str(e)}"}, 500)

    def _create_genre(self, body):
        genre_id = body.get("id", "").strip()
        base_genre = body.get("base", "xuanhuan")
        toml_content = body.get("toml", "")
        if not genre_id:
            self._send_json({"error": "题材ID不能为空"}, 400)
            return
        try:
            from fanqie.genres.loader import get_genre_path
            custom_dir = FANQIE_DIR / "fanqie" / "genres" / "custom"
            custom_dir.mkdir(parents=True, exist_ok=True)
            dest = custom_dir / f"{genre_id}.toml"
            if toml_content:
                dest.write_text(toml_content, encoding="utf-8")
            else:
                src = get_genre_path(base_genre)
                if not src:
                    self._send_json({"error": f"基础题材 {base_genre} 不存在"}, 400)
                    return
                import shutil
                shutil.copy(src, dest)
            self._send_json({"success": True, "message": f"题材 {genre_id} 已创建", "path": str(dest)})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)


def main():
    port = 8765
    server = HTTPServer(("127.0.0.1", port), FanqieAPI)
    print(f"Fanqie Web 管理界面已启动: http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
