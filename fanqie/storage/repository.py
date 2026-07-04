"""数据仓库 — CRUD 操作."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from .database import Database
from .migrations import run_migrations, get_db_path


class Repository:
    """书籍数据仓库."""

    def __init__(self, data_dir: str, book_id: str):
        self.data_dir = data_dir
        self.book_id = book_id
        self.db = Database(get_db_path(data_dir, book_id))
        run_migrations(self.db)

    # ---- Book ----

    def save_book(self, book: dict) -> None:
        book["updated_at"] = datetime.now().isoformat()
        self.db.execute(
            """INSERT OR REPLACE INTO books
               (id, title, genre_id, platform, chapter_word_count,
                target_chapters, status, style_profile_path, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (book["id"], book["title"], book["genre_id"], book.get("platform", "番茄小说"),
             book.get("chapter_word_count", 2000), book.get("target_chapters", 500),
             book.get("status", "draft"), book.get("style_profile_path"),
             book.get("created_at", datetime.now().isoformat()), book["updated_at"]),
        )
        self.db.commit()

    def get_book(self) -> dict | None:
        return self.db.fetchone("SELECT * FROM books WHERE id=?", (self.book_id,))

    def list_books(self) -> list[dict]:
        return self.db.fetchall("SELECT * FROM books ORDER BY updated_at DESC")

    def delete_book(self) -> None:
        for table in ["chapters", "characters", "hooks", "chapter_summaries", "facts"]:
            self.db.execute(f"DELETE FROM {table} WHERE book_id=?", (self.book_id,))
        self.db.execute("DELETE FROM books WHERE id=?", (self.book_id,))
        self.db.commit()

    # ---- Chapter ----

    def save_chapter(self, chapter: dict) -> None:
        chapter["updated_at"] = datetime.now().isoformat()
        issues_json = json.dumps(chapter.get("audit_issues", []), ensure_ascii=False)
        self.db.execute(
            """INSERT OR REPLACE INTO chapters
               (book_id, chapter_number, title, content, word_count, status,
                audit_score, audit_issues, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (self.book_id, chapter["chapter_number"], chapter.get("title", ""),
             chapter.get("content", ""), chapter.get("word_count", 0),
             chapter.get("status", "draft"), chapter.get("audit_score"),
             issues_json, chapter.get("created_at", datetime.now().isoformat()),
             chapter["updated_at"]),
        )
        self.db.commit()

    def get_chapter(self, chapter_number: int) -> dict | None:
        return self.db.fetchone(
            "SELECT * FROM chapters WHERE book_id=? AND chapter_number=?",
            (self.book_id, chapter_number),
        )

    def get_all_chapters(self) -> list[dict]:
        return self.db.fetchall(
            "SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_number",
            (self.book_id,),
        )

    def get_chapter_count(self) -> int:
        row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM chapters WHERE book_id=?",
            (self.book_id,),
        )
        return row["cnt"] if row else 0

    # ---- Hook ----

    def save_hook(self, hook: dict) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO hooks
               (hook_id, book_id, start_chapter, last_advanced_chapter, type, status,
                expected_payoff, payoff_timing, notes, seed_text, depends_on,
                core_hook, promoted, advanced_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (hook["hook_id"], self.book_id, hook.get("start_chapter", 0),
             hook.get("last_advanced_chapter", 0), hook.get("type", ""),
             hook.get("status", "planted"), hook.get("expected_payoff", ""),
             hook.get("payoff_timing", "mid_arc"), hook.get("notes", ""),
             hook.get("seed_text", ""), json.dumps(hook.get("depends_on", []), ensure_ascii=False),
             1 if hook.get("core_hook") else 0, 1 if hook.get("promoted") else 0,
             hook.get("advanced_count", 0)),
        )
        self.db.commit()

    def get_hooks(self) -> list[dict]:
        return self.db.fetchall(
            "SELECT * FROM hooks WHERE book_id=? ORDER BY start_chapter",
            (self.book_id,),
        )

    def get_active_hooks(self) -> list[dict]:
        return self.db.fetchall(
            """SELECT * FROM hooks WHERE book_id=?
               AND status NOT IN ('resolved','deferred')
               AND promoted=1""",
            (self.book_id,),
        )

    # ---- Chapter Summary ----

    def save_summary(self, summary: dict) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO chapter_summaries
               (book_id, chapter, title, characters, events, state_changes,
                hook_activity, mood, chapter_type)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (self.book_id, summary["chapter"], summary.get("title", ""),
             summary.get("characters", ""), summary.get("events", ""),
             summary.get("state_changes", ""), summary.get("hook_activity", ""),
             summary.get("mood", ""), summary.get("chapter_type", "")),
        )
        self.db.commit()

    def get_summaries(self, from_ch: int = 1, to_ch: int | None = None) -> list[dict]:
        if to_ch is None:
            return self.db.fetchall(
                "SELECT * FROM chapter_summaries WHERE book_id=? AND chapter>=? ORDER BY chapter",
                (self.book_id, from_ch),
            )
        return self.db.fetchall(
            "SELECT * FROM chapter_summaries WHERE book_id=? AND chapter>=? AND chapter<=? ORDER BY chapter",
            (self.book_id, from_ch, to_ch),
        )

    # ---- Fact (结构化事实) ----

    def save_fact(self, fact: dict) -> None:
        self.db.execute(
            """INSERT INTO facts (book_id, subject, predicate, object,
               valid_from_chapter, valid_until_chapter, source_chapter)
               VALUES (?,?,?,?,?,?,?)""",
            (self.book_id, fact["subject"], fact["predicate"], fact["object"],
             fact.get("valid_from_chapter", 0), fact.get("valid_until_chapter"),
             fact.get("source_chapter", 0)),
        )
        self.db.commit()

    def get_current_facts(self) -> list[dict]:
        return self.db.fetchall(
            """SELECT * FROM facts WHERE book_id=?
               AND valid_until_chapter IS NULL
               ORDER BY id""",
            (self.book_id,),
        )

    def search_facts(self, query: str, limit: int = 10) -> list[dict]:
        """全文搜索事实."""
        try:
            return self.db.fetchall(
                """SELECT f.* FROM facts f
                   JOIN facts_fts ft ON f.id = ft.rowid
                   WHERE f.book_id=? AND facts_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (self.book_id, query, limit),
            )
        except Exception:
            # FTS5 不可用时回退到 LIKE
            like_q = f"%{query}%"
            return self.db.fetchall(
                """SELECT * FROM facts WHERE book_id=?
                   AND (subject LIKE ? OR predicate LIKE ? OR object LIKE ?)
                   LIMIT ?""",
                (self.book_id, like_q, like_q, like_q, limit),
            )

    def close(self) -> None:
        self.db.close()
