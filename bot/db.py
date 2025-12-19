import json
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg import errors
from psycopg.rows import dict_row

from .config import CATEGORIES_FILE, DATABASE_URL, OWNER_CHAT_ID, TASKS_TEMPLATE_FILE

PRIORITY_TO_VALUE = {"низкий": 0, "средний": 1, "высокий": 2}
VALUE_TO_PRIORITY = {v: k for k, v in PRIORITY_TO_VALUE.items()}
DEFAULT_PRIORITY_VALUE = 1
DEFAULT_STATUS = "active"


def _conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def _priority_to_db(priority: str | None) -> int | None:
    if priority is None:
        return None
    return PRIORITY_TO_VALUE.get(priority, DEFAULT_PRIORITY_VALUE)


def _priority_from_db(value: int | None) -> str | None:
    if value is None:
        return None
    return VALUE_TO_PRIORITY.get(int(value), "средний")


def _next_task_id(cursor) -> int:
    row = cursor.execute("SELECT nextval(pg_get_serial_sequence('tasks', 'id')) AS id").fetchone()
    return int(row["id"])


def _sync_task_sequence(cursor) -> None:
    cursor.execute(
        "SELECT setval(pg_get_serial_sequence('tasks', 'id'), COALESCE((SELECT MAX(id) FROM tasks), 0), true)"
    )


def _get_or_create_category_id(cursor, user_id: int, name: str | None) -> int | None:
    if not name:
        return None
    row = cursor.execute(
        """
        INSERT INTO categories(user_id, name, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, name)
        DO UPDATE SET updated_at = EXCLUDED.updated_at
        RETURNING id
        """,
        (user_id, name),
    ).fetchone()
    return int(row["id"])


def _get_or_create_tag_id(cursor, user_id: int, name: str) -> int:
    row = cursor.execute(
        """
        INSERT INTO tags(user_id, name, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, name)
        DO UPDATE SET updated_at = EXCLUDED.updated_at
        RETURNING id
        """,
        (user_id, name),
    ).fetchone()
    return int(row["id"])


def _normalize_done_at(task: dict[str, Any]) -> datetime | None:
    if task.get("done"):
        done_at = task.get("done_at")
        if isinstance(done_at, datetime):
            return done_at
        return datetime.now(timezone.utc)
    return None


def init_db():
    print("DEBUG: init_db (postgres)")
    with _conn() as conn:
        with conn.cursor() as c:
            try:
                c.execute("SELECT version_num FROM alembic_version")
            except errors.UndefinedTable as exc:
                raise RuntimeError(
                    "Схема базы данных не инициализирована. Выполните `alembic upgrade head`."
                ) from exc
        conn.commit()

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
            for t in tasks:
                category_id = _get_or_create_category_id(c, user_id, t.get("category"))
                priority_value = _priority_to_db(t.get("priority"))
                status = "done" if t.get("done") else DEFAULT_STATUS
                done_at = datetime.now(timezone.utc) if status == "done" else None

                row = c.execute(
                    """
                    INSERT INTO tasks(user_id, title, category_id, priority, status, comment, done_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        t["title"],
                        category_id,
                        priority_value,
                        status,
                        t.get("comment", ""),
                        done_at,
                    ),
                ).fetchone()
                task_id = int(row["id"])

                for tag in t.get("tags", []):
                    tag_id = _get_or_create_tag_id(c, user_id, tag)
                    c.execute(
                        """
                        INSERT INTO task_tags(task_id, tag_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (task_id, tag_id),
                    )

            _sync_task_sequence(c)
        conn.commit()


def register_user(user_id: int, name: str | None = None):
    """Ensure user exists and has default data."""
    with _conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """
                INSERT INTO users(user_id, name)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET name = EXCLUDED.name
                """,
                (user_id, name),
            )

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

            row = c.execute("SELECT COUNT(*) AS cnt FROM categories WHERE user_id=%s", (user_id,)).fetchone()
            if int(row["cnt"]) == 0 and os.path.exists(CATEGORIES_FILE):
                with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
                    for cat_name in json.load(f):
                        c.execute(
                            """
                            INSERT INTO categories(user_id, name)
                            VALUES (%s, %s)
                            ON CONFLICT (user_id, name) DO NOTHING
                            """,
                            (user_id, cat_name),
                        )

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
    with _conn() as conn:
        with conn.cursor() as cursor:
            _sync_task_sequence(cursor)
            next_id = _next_task_id(cursor)
        conn.commit()
    return next_id


def load_tasks(user_id: int):
    print("DEBUG: load_tasks")
    with _conn() as conn:
        with conn.cursor() as c:
            tasks = c.execute(
                """
                SELECT t.id, t.title, t.priority, t.status, t.comment, t.due_at, t.created_at, t.updated_at, t.done_at,
                       c.name AS category
                FROM tasks t
                LEFT JOIN categories c ON c.id = t.category_id
                WHERE t.user_id=%s
                ORDER BY t.id
                """,
                (user_id,),
            ).fetchall()

            for t in tasks:
                rows = c.execute(
                    """
                    SELECT tg.name AS tag
                    FROM task_tags tt
                    JOIN tags tg ON tg.id = tt.tag_id
                    WHERE tt.task_id=%s
                    ORDER BY tg.name
                    """,
                    (t["id"],),
                ).fetchall()
                t["tags"] = [r["tag"] for r in rows]
                t["done"] = (t.get("status") == "done")
                t["priority"] = _priority_from_db(t.get("priority"))

    print(f"DEBUG: load_tasks -> {len(tasks)} tasks")
    if not tasks:
        print("WARNING: load_tasks returned empty list")
    return tasks


def save_tasks(user_id: int, tasks: list[dict[str, Any]]):
    print("DEBUG: save_tasks")
    with _conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM task_tags
                USING tasks
                WHERE task_tags.task_id = tasks.id AND tasks.user_id=%s
                """,
                (user_id,),
            )
            cursor.execute("DELETE FROM tasks WHERE user_id=%s", (user_id,))

            for t in tasks:
                priority_value = _priority_to_db(t.get("priority"))
                status = "done" if t.get("done") else t.get("status", DEFAULT_STATUS)
                done_at = _normalize_done_at(t)
                category_id = _get_or_create_category_id(cursor, user_id, t.get("category"))

                task_id = t.get("id")
                if task_id is None:
                    task_id = _next_task_id(cursor)
                else:
                    task_id = int(task_id)

                cursor.execute(
                    """
                    INSERT INTO tasks(id, user_id, title, category_id, priority, status, comment, due_at, done_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        task_id,
                        user_id,
                        t["title"],
                        category_id,
                        priority_value,
                        status,
                        t.get("comment", ""),
                        t.get("due_at"),
                        done_at,
                    ),
                )
                t["id"] = task_id

                for tag in t.get("tags", []) or []:
                    tag_id = _get_or_create_tag_id(cursor, user_id, tag)
                    cursor.execute(
                        "INSERT INTO task_tags(task_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (task_id, tag_id),
                    )

            _sync_task_sequence(cursor)

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
                    """
                    INSERT INTO categories(user_id, name, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    """,
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
            SELECT DISTINCT tg.name AS tag
            FROM task_tags tt
            JOIN tasks t ON t.id = tt.task_id
            JOIN tags tg ON tg.id = tt.tag_id
            WHERE t.status = 'active' AND t.user_id = %s
            ORDER BY tg.name
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
