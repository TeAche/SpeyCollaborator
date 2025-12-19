import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import CATEGORIES_FILE, OWNER_CHAT_ID, TASKS_TEMPLATE_FILE, DATABASE_URL


def _conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    print("DEBUG: init_db (postgres)")
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id BIGINT PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    category TEXT,
                    priority TEXT,
                    done BOOLEAN DEFAULT FALSE,
                    comment TEXT DEFAULT ''
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    PRIMARY KEY(user_id, name)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    PRIMARY KEY(user_id, name)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS task_tags (
                    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    tag TEXT NOT NULL,
                    PRIMARY KEY(task_id, tag)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY(user_id, key)
                )
            """)
        conn.commit()

    # register default owner user and import initial data if DB is empty
    if OWNER_CHAT_ID:
        register_user(OWNER_CHAT_ID)
    else:
        print("WARNING: OWNER_CHAT_ID is not set; skipping owner registration")


def import_tasks_from_template(user_id: int):
    print("DEBUG: import_tasks_from_template")
    if not os.path.exists(TASKS_TEMPLATE_FILE):
        print("WARNING: tasks template not found")
        return

    with open(TASKS_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    with _conn() as conn:
        with conn.cursor() as c:
            row = c.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM tasks").fetchone()
            next_id = int(row["max_id"]) + 1

            for t in tasks:
                c.execute(
                    """
                    INSERT INTO tasks(id, user_id, title, category, priority, done, comment)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        next_id,
                        user_id,
                        t["title"],
                        t.get("category"),
                        t.get("priority"),
                        bool(t.get("done", False)),
                        t.get("comment", ""),
                    ),
                )

                for tag in t.get("tags", []):
                    c.execute(
                        """
                        INSERT INTO tags(user_id, name) VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (user_id, tag),
                    )
                    c.execute(
                        """
                        INSERT INTO task_tags(task_id, tag) VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (next_id, tag),
                    )
                next_id += 1
        conn.commit()


def register_user(user_id: int, name: str | None = None):
    """Ensure user exists and has default data."""
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "INSERT INTO users(user_id, name) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
                (user_id, name),
            )

            # default settings
            row = c.execute("SELECT COUNT(*) AS cnt FROM settings WHERE user_id=%s", (user_id,)).fetchone()
            if int(row["cnt"]) == 0:
                c.execute(
                    "INSERT INTO settings(user_id, key, value) VALUES (%s, 'reminder_time', '09:00')",
                    (user_id,),
                )
                c.execute(
                    "INSERT INTO settings(user_id, key, value) VALUES (%s, 'notify_weekends', '0')",
                    (user_id,),
                )

            # default categories
            row = c.execute("SELECT COUNT(*) AS cnt FROM categories WHERE user_id=%s", (user_id,)).fetchone()
            if int(row["cnt"]) == 0 and os.path.exists(CATEGORIES_FILE):
                with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
                    for cat_name in json.load(f):
                        c.execute(
                            "INSERT INTO categories(user_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (user_id, cat_name),
                        )

            # default tasks check
            row = c.execute("SELECT COUNT(*) AS cnt FROM tasks WHERE user_id=%s", (user_id,)).fetchone()
            has_tasks = int(row["cnt"]) > 0

        conn.commit()

    if not has_tasks:
        import_tasks_from_template(user_id)


def get_all_users():
    with _conn() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
    return [int(r["user_id"]) for r in rows]


def get_next_task_id(user_id: int) -> int:
    # kept for compatibility with existing logic
    with _conn() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM tasks").fetchone()
    return int(row["max_id"]) + 1


def load_tasks(user_id: int):
    print("DEBUG: load_tasks")
    with _conn() as conn:
        tasks = conn.execute(
            "SELECT * FROM tasks WHERE user_id=%s ORDER BY id",
            (user_id,),
        ).fetchall()

        for t in tasks:
            rows = conn.execute(
                "SELECT tag FROM task_tags WHERE task_id=%s",
                (t["id"],),
            ).fetchall()
            t["tags"] = [r["tag"] for r in rows]
            t["done"] = bool(t["done"])

    print(f"DEBUG: load_tasks -> {len(tasks)} tasks")
    if not tasks:
        print("WARNING: load_tasks returned empty list")
    return tasks


def save_tasks(user_id: int, tasks: list[dict[str, Any]]):
    print("DEBUG: save_tasks")
    with _conn() as conn:
        with conn.cursor() as cursor:
            row = cursor.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM tasks").fetchone()
            next_id = int(row["max_id"]) + 1

            # delete tags for tasks belonging to user (must be before deleting tasks if you had FK constraints)
            cursor.execute(
                """
                DELETE FROM task_tags
                WHERE task_id IN (SELECT id FROM tasks WHERE user_id=%s)
                """,
                (user_id,),
            )
            cursor.execute("DELETE FROM tasks WHERE user_id=%s", (user_id,))

            for t in tasks:
                task_id = t.get("id")
                if task_id is None:
                    task_id = next_id
                    next_id += 1
                else:
                    next_id = max(next_id, int(task_id) + 1)
                t["id"] = task_id

                cursor.execute(
                    """
                    INSERT INTO tasks(id, user_id, title, category, priority, done, comment)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        task_id,
                        user_id,
                        t["title"],
                        t.get("category"),
                        t.get("priority"),
                        bool(t.get("done", False)),
                        t.get("comment", ""),
                    ),
                )

                for tag in t.get("tags", []) or []:
                    cursor.execute(
                        "INSERT INTO tags(user_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (user_id, tag),
                    )
                    cursor.execute(
                        "INSERT INTO task_tags(task_id, tag) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (task_id, tag),
                    )

        conn.commit()


def load_categories(user_id: int):
    print("DEBUG: load_categories")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT name FROM categories WHERE user_id=%s ORDER BY name",
            (user_id,),
        ).fetchall()
    categories = [r["name"] for r in rows]
    print(f"DEBUG: load_categories -> {len(categories)} categories")
    if not categories:
        print("WARNING: load_categories returned empty list")
    return categories


def save_categories(user_id: int, categories: list[str]):
    print("DEBUG: save_categories")
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM categories WHERE user_id=%s", (user_id,))
            for name in categories:
                c.execute(
                    "INSERT INTO categories(user_id, name) VALUES (%s, %s)",
                    (user_id, name),
                )
        conn.commit()


def load_tags(user_id: int):
    print("DEBUG: load_tags")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT name FROM tags WHERE user_id=%s ORDER BY name",
            (user_id,),
        ).fetchall()
    tags = [r["name"] for r in rows]
    print(f"DEBUG: load_tags -> {len(tags)} tags")
    if not tags:
        print("WARNING: load_tags returned empty list")
    return tags


def load_active_tags(user_id: int):
    print("DEBUG: load_active_tags")
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT tt.tag AS tag
            FROM task_tags tt
            JOIN tasks t ON t.id = tt.task_id
            WHERE t.done = FALSE AND t.user_id = %s
            ORDER BY tt.tag
            """,
            (user_id,),
        ).fetchall()
    tags = [r["tag"] for r in rows]
    print(f"DEBUG: load_active_tags -> {len(tags)} tags")
    if not tags:
        print("WARNING: load_active_tags returned empty list")
    return tags


def load_settings(user_id: int):
    print("DEBUG: load_settings")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE user_id=%s",
            (user_id,),
        ).fetchall()
    settings = {row["key"]: row["value"] for row in rows}
    print(f"DEBUG: load_settings -> {len(settings)} entries")
    if not settings:
        print("WARNING: load_settings returned empty dict")
    return settings


def save_setting(user_id: int, key: str, value: Any):
    print(f"DEBUG: save_setting {key}={value}")
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO settings(user_id, key, value)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, key) DO UPDATE SET value=EXCLUDED.value
            """,
            (user_id, key, str(value)),
        )
        conn.commit()
