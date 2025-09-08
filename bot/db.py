import json
import os
import sqlite3
from datetime import time

from .config import CATEGORIES_FILE, DB_FILE, OWNER_CHAT_ID, TASKS_TEMPLATE_FILE
from .constants import *


def init_db():
    print("DEBUG: init_db")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT,
            priority TEXT,
            done INTEGER DEFAULT 0,
            comment TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            user_id INTEGER NOT NULL,
            name TEXT,
            PRIMARY KEY(user_id, name),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            user_id INTEGER NOT NULL,
            name TEXT,
            PRIMARY KEY(user_id, name),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS task_tags (
            task_id INTEGER,
            tag TEXT,
            PRIMARY KEY(task_id, tag),
            FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY(tag) REFERENCES tags(name) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            user_id INTEGER NOT NULL,
            key TEXT,
            value TEXT,
            PRIMARY KEY(user_id, key),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()

    # register default owner user and import initial data if DB is empty
    register_user(OWNER_CHAT_ID)
    conn.close()


def import_tasks_from_template(user_id: int):
    print("DEBUG: import_tasks_from_template")
    if not os.path.exists(TASKS_TEMPLATE_FILE):
        print("WARNING: tasks template not found")
        return
    with open(TASKS_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    row = c.execute("SELECT MAX(id) FROM tasks").fetchone()
    next_id = (row[0] or 0) + 1
    for t in tasks:
        c.execute(
            "INSERT INTO tasks(id, user_id, title, category, priority, done, comment) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                next_id,
                user_id,
                t["title"],
                t.get("category"),
                t.get("priority"),
                int(t.get("done", False)),
                t.get("comment", ""),
            ),
        )
        for tag in t.get("tags", []):
            c.execute(
                "INSERT OR IGNORE INTO tags(user_id, name) VALUES (?, ?)",
                (user_id, tag),
            )
            c.execute(
                "INSERT INTO task_tags(task_id, tag) VALUES (?, ?)",
                (next_id, tag),
            )
        next_id += 1
    conn.commit()
    conn.close()


def register_user(user_id: int, name: str | None = None):
    """Ensure user exists and has default data."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users(user_id, name) VALUES (?, ?)",
        (user_id, name),
    )
    # default settings
    c.execute("SELECT COUNT(*) FROM settings WHERE user_id=?", (user_id,))
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO settings(user_id, key, value) VALUES (?, 'reminder_time', '09:00')",
            (user_id,),
        )
        c.execute(
            "INSERT INTO settings(user_id, key, value) VALUES (?, 'notify_weekends', '0')",
            (user_id,),
        )
    # default categories
    c.execute("SELECT COUNT(*) FROM categories WHERE user_id=?", (user_id,))
    if c.fetchone()[0] == 0 and os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            for name in json.load(f):
                c.execute(
                    "INSERT INTO categories(user_id, name) VALUES (?, ?)",
                    (user_id, name),
                )
    # default tasks
    c.execute("SELECT COUNT(*) FROM tasks WHERE user_id=?", (user_id,))
    has_tasks = c.fetchone()[0] > 0
    conn.commit()
    conn.close()
    if not has_tasks:
        import_tasks_from_template(user_id)


def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_next_task_id(user_id: int) -> int:
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute("SELECT MAX(id) FROM tasks WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return (row[0] or 0) + 1


def load_tasks(user_id: int):
    print("DEBUG: load_tasks")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    tasks = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM tasks WHERE user_id=? ORDER BY id",
            (user_id,),
        )
    ]
    for t in tasks:
        rows = conn.execute("SELECT tag FROM task_tags WHERE task_id=?", (t["id"],)).fetchall()
        t["tags"] = [r[0] for r in rows]
        t["done"] = bool(t["done"])
    conn.close()
    print(f"DEBUG: load_tasks -> {len(tasks)} tasks")
    if not tasks:
        print("WARNING: load_tasks returned empty list")
    return tasks


def save_tasks(user_id: int, tasks):
    print("DEBUG: save_tasks")
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM tasks WHERE user_id=?", (user_id,))
    conn.execute(
        "DELETE FROM task_tags WHERE task_id IN (SELECT id FROM tasks WHERE user_id=?)",
        (user_id,),
    )
    for t in tasks:
        task_id = t.get("id") or get_next_task_id(user_id)
        t["id"] = task_id
        conn.execute(
            "INSERT INTO tasks(id, user_id, title, category, priority, done, comment) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                user_id,
                t["title"],
                t.get("category"),
                t.get("priority"),
                int(t.get("done", False)),
                t.get("comment", ""),
            ),
        )
        for tag in t.get("tags", []):
            conn.execute(
                "INSERT OR IGNORE INTO tags(user_id, name) VALUES (?, ?)",
                (user_id, tag),
            )
            conn.execute(
                "INSERT INTO task_tags(task_id, tag) VALUES (?, ?)",
                (task_id, tag),
            )
    conn.commit()
    conn.close()


def load_categories(user_id: int):
    print("DEBUG: load_categories")
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT name FROM categories WHERE user_id=? ORDER BY name",
        (user_id,),
    ).fetchall()
    conn.close()
    categories = [r[0] for r in rows]
    print(f"DEBUG: load_categories -> {len(categories)} categories")
    if not categories:
        print("WARNING: load_categories returned empty list")
    return categories


def save_categories(user_id: int, categories):
    print("DEBUG: save_categories")
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM categories WHERE user_id=?", (user_id,))
    for name in categories:
        conn.execute(
            "INSERT INTO categories(user_id, name) VALUES (?, ?)",
            (user_id, name),
        )
    conn.commit()
    conn.close()


def load_tags(user_id: int):
    print("DEBUG: load_tags")
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT name FROM tags WHERE user_id=? ORDER BY name",
        (user_id,),
    ).fetchall()
    conn.close()
    tags = [r[0] for r in rows]
    print(f"DEBUG: load_tags -> {len(tags)} tags")
    if not tags:
        print("WARNING: load_tags returned empty list")
    return tags


def load_active_tags(user_id: int):
    print("DEBUG: load_active_tags")
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        """
        SELECT DISTINCT tag FROM task_tags
        JOIN tasks ON tasks.id = task_tags.task_id
        WHERE tasks.done = 0 AND tasks.user_id = ?
        ORDER BY tag
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    tags = [r[0] for r in rows]
    print(f"DEBUG: load_active_tags -> {len(tags)} tags")
    if not tags:
        print("WARNING: load_active_tags returned empty list")
    return tags


def load_settings(user_id: int):
    print("DEBUG: load_settings")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE user_id=?",
        (user_id,),
    ).fetchall()
    conn.close()
    settings = {row["key"]: row["value"] for row in rows}
    print(f"DEBUG: load_settings -> {len(settings)} entries")
    if not settings:
        print("WARNING: load_settings returned empty dict")
    return settings


def save_setting(user_id: int, key, value):
    print(f"DEBUG: save_setting {key}={value}")
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO settings(user_id, key, value) VALUES (?, ?, ?)",
        (user_id, key, str(value)),
    )
    conn.commit()
    conn.close()
