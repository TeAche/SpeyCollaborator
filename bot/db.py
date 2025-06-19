import json
import os
import sqlite3
from datetime import time

from .config import TASKS_FILE, CATEGORIES_FILE, DB_FILE
from .constants import *


def init_db():
    print("DEBUG: init_db")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT,
            priority TEXT,
            done INTEGER DEFAULT 0,
            comment TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            name TEXT PRIMARY KEY
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            name TEXT PRIMARY KEY
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
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.commit()

    c.execute("SELECT COUNT(*) FROM settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO settings(key, value) VALUES ('reminder_time', '09:00')")
        c.execute("INSERT INTO settings(key, value) VALUES ('notify_weekends', '0')")

    c.execute("SELECT COUNT(*) FROM tasks")
    if c.fetchone()[0] == 0 and os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            for t in json.load(f):
                c.execute(
                    "INSERT INTO tasks(id, title, category, priority, done, comment) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        t["id"],
                        t["title"],
                        t.get("category"),
                        t.get("priority"),
                        int(t.get("done", False)),
                        t.get("comment", ""),
                    ),
                )
                for tag in t.get("tags", []):
                    c.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
                    c.execute(
                        "INSERT OR IGNORE INTO task_tags(task_id, tag) VALUES (?, ?)",
                        (t["id"], tag),
                    )
    c.execute("SELECT COUNT(*) FROM categories")
    if c.fetchone()[0] == 0 and os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
            for name in json.load(f):
                c.execute("INSERT OR IGNORE INTO categories(name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def load_tasks():
    print("DEBUG: load_tasks")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    tasks = [dict(row) for row in conn.execute("SELECT * FROM tasks ORDER BY id")]
    for t in tasks:
        rows = conn.execute("SELECT tag FROM task_tags WHERE task_id=?", (t["id"],)).fetchall()
        t["tags"] = [r[0] for r in rows]
        t["done"] = bool(t["done"])
    conn.close()
    return tasks


def save_tasks(tasks):
    print("DEBUG: save_tasks")
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM tasks")
    conn.execute("DELETE FROM task_tags")
    for t in tasks:
        conn.execute(
            "INSERT INTO tasks(id, title, category, priority, done, comment) VALUES (?, ?, ?, ?, ?, ?)",
            (
                t["id"],
                t["title"],
                t.get("category"),
                t.get("priority"),
                int(t.get("done", False)),
                t.get("comment", ""),
            ),
        )
        for tag in t.get("tags", []):
            conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
            conn.execute("INSERT INTO task_tags(task_id, tag) VALUES (?, ?)", (t["id"], tag))
    conn.commit()
    conn.close()


def load_categories():
    print("DEBUG: load_categories")
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    conn.close()
    return [r[0] for r in rows]


def save_categories(categories):
    print("DEBUG: save_categories")
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM categories")
    for name in categories:
        conn.execute("INSERT INTO categories(name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def load_tags():
    print("DEBUG: load_tags")
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
    conn.close()
    return [r[0] for r in rows]


def load_active_tags():
    print("DEBUG: load_active_tags")
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        """
        SELECT DISTINCT tag FROM task_tags
        JOIN tasks ON tasks.id = task_tags.task_id
        WHERE tasks.done = 0
        ORDER BY tag
        """
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def load_settings():
    print("DEBUG: load_settings")
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


def save_setting(key, value):
    print(f"DEBUG: save_setting {key}={value}")
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()
