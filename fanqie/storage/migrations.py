"""数据库迁移."""

from __future__ import annotations

from .database import Database

SCHEMA = [
    # 书籍表
    """
    CREATE TABLE IF NOT EXISTS books (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        genre_id TEXT NOT NULL,
        platform TEXT DEFAULT '番茄小说',
        chapter_word_count INTEGER DEFAULT 2000,
        target_chapters INTEGER DEFAULT 500,
        status TEXT DEFAULT 'draft',
        style_profile_path TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # 章节表
    """
    CREATE TABLE IF NOT EXISTS chapters (
        book_id TEXT NOT NULL,
        chapter_number INTEGER NOT NULL,
        title TEXT DEFAULT '',
        content TEXT DEFAULT '',
        word_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'draft',
        audit_score INTEGER,
        audit_issues TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (book_id, chapter_number),
        FOREIGN KEY (book_id) REFERENCES books(id)
    )
    """,
    # 角色表
    """
    CREATE TABLE IF NOT EXISTS characters (
        id TEXT PRIMARY KEY,
        book_id TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT DEFAULT 'supporting',
        tags TEXT DEFAULT '[]',
        contrast TEXT DEFAULT '',
        voice TEXT DEFAULT '',
        personality TEXT DEFAULT '',
        motivation TEXT DEFAULT '',
        current_goal TEXT DEFAULT '',
        relationships TEXT DEFAULT '{}',
        known_info TEXT DEFAULT '[]',
        unknown_info TEXT DEFAULT '[]',
        FOREIGN KEY (book_id) REFERENCES books(id)
    )
    """,
    # 伏笔表
    """
    CREATE TABLE IF NOT EXISTS hooks (
        hook_id TEXT NOT NULL,
        book_id TEXT NOT NULL,
        start_chapter INTEGER NOT NULL,
        last_advanced_chapter INTEGER DEFAULT 0,
        type TEXT DEFAULT '',
        status TEXT DEFAULT 'planted',
        expected_payoff TEXT DEFAULT '',
        payoff_timing TEXT DEFAULT 'mid_arc',
        notes TEXT DEFAULT '',
        seed_text TEXT DEFAULT '',
        depends_on TEXT DEFAULT '[]',
        core_hook INTEGER DEFAULT 0,
        promoted INTEGER DEFAULT 0,
        advanced_count INTEGER DEFAULT 0,
        PRIMARY KEY (book_id, hook_id),
        FOREIGN KEY (book_id) REFERENCES books(id)
    )
    """,
    # 章节摘要表
    """
    CREATE TABLE IF NOT EXISTS chapter_summaries (
        book_id TEXT NOT NULL,
        chapter INTEGER NOT NULL,
        title TEXT DEFAULT '',
        characters TEXT DEFAULT '',
        events TEXT DEFAULT '',
        state_changes TEXT DEFAULT '',
        hook_activity TEXT DEFAULT '',
        mood TEXT DEFAULT '',
        chapter_type TEXT DEFAULT '',
        PRIMARY KEY (book_id, chapter),
        FOREIGN KEY (book_id) REFERENCES books(id)
    )
    """,
    # 结构化事实表
    """
    CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id TEXT NOT NULL,
        subject TEXT NOT NULL,
        predicate TEXT NOT NULL,
        object TEXT NOT NULL,
        valid_from_chapter INTEGER NOT NULL,
        valid_until_chapter INTEGER,
        source_chapter INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (book_id) REFERENCES books(id)
    )
    """,
    # 全文搜索索引
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
        subject, predicate, object, content='facts', content_rowid='id'
    )
    """,
]


def run_migrations(db: Database) -> None:
    """执行数据库迁移."""
    for sql in SCHEMA:
        try:
            db.execute(sql)
        except Exception as e:
            # FTS5 在某些环境中可能不可用，忽略
            if "fts5" not in str(e).lower():
                raise
    db.commit()


def get_db_path(data_dir: str, book_id: str) -> str:
    """获取数据库文件路径."""
    import os
    return os.path.join(data_dir, book_id, "book.db")
