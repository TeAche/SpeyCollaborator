from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import OWNER_CHAT_ID
from .db_orm.session import SessionLocal
from .db_orm.models import Category, Setting, Tag, Task, TaskTag, User


def init_db():
    """
    С миграциями Alembic эта функция больше не создает таблицы.
    Оставлена для совместимости: можно зарегистрировать OWNER, если задан.
    """
    print("DEBUG: init_db (orm)")
    if OWNER_CHAT_ID:
        register_user(OWNER_CHAT_ID)


def _session() -> Session:
    return SessionLocal()


def register_user(user_id: int, name: str | None = None):
    """Ensure user exists and has default settings (no seed tasks/categories)."""
    with _session() as s:
        user = s.get(User, user_id)
        if not user:
            s.add(User(user_id=user_id, name=name))
        elif name and not user.name:
            user.name = name

        s.flush()  # важно: гарантирует, что user уже вставлен до settings

        # default settings if missing
        existing = {
            row.key for row in s.execute(
                select(Setting.key).where(Setting.user_id == user_id)
            ).all()
        }
        if "reminder_time" not in existing:
            s.add(Setting(user_id=user_id, key="reminder_time", value="09:00"))
        if "notify_weekends" not in existing:
            s.add(Setting(user_id=user_id, key="notify_weekends", value="0"))

        s.commit()


def get_all_users():
    with _session() as s:
        rows = s.execute(select(User.user_id)).all()
        return [int(r[0]) for r in rows]


def get_next_task_id(user_id: int) -> int:
    with _session() as s:
        return int(s.execute(text("SELECT nextval('tasks_id_seq')")).scalar_one())


def load_tasks(user_id: int):
    print("DEBUG: load_tasks (orm)")
    with _session() as s:
        tasks = s.execute(
            select(Task).where(Task.user_id == user_id).order_by(Task.id)
        ).scalars().all()

        # preload tags for each task
        task_ids = [t.id for t in tasks]
        tags_by_task: dict[int, list[str]] = {tid: [] for tid in task_ids}
        if task_ids:
            rows = s.execute(
                select(TaskTag.task_id, TaskTag.tag).where(TaskTag.task_id.in_(task_ids))
            ).all()
            for task_id, tag in rows:
                tags_by_task[int(task_id)].append(str(tag))

        out: list[dict[str, Any]] = []
        for t in tasks:
            out.append(
                {
                    "id": int(t.id),
                    "title": t.title,
                    "category": t.category,
                    "priority": t.priority,
                    "done": bool(t.done),
                    "comment": t.comment or "",
                    "tags": tags_by_task.get(int(t.id), []),
                }
            )

    print(f"DEBUG: load_tasks -> {len(out)} tasks")
    if not out:
        print("WARNING: load_tasks returned empty list")
    return out


def save_tasks(user_id: int, tasks: list[dict[str, Any]]):
    print("DEBUG: save_tasks (orm, sync)")
    with _session() as s:
        # 1) какие задачи уже есть у пользователя
        existing_ids = set(
            s.execute(select(Task.id).where(Task.user_id == user_id)).scalars().all()
        )

        incoming_ids: set[int] = set()

        # 2) upsert задач
        for t in tasks:
            task_id = t.get("id")
            if task_id is None:
                # если когда-то встретится None — получим id из sequence
                task_id = int(s.execute(text("SELECT nextval('tasks_id_seq')")).scalar_one())
                t["id"] = task_id
            task_id = int(task_id)
            incoming_ids.add(task_id)

            if task_id in existing_ids:
                # update
                obj = s.get(Task, task_id)
                if obj and obj.user_id == user_id:
                    obj.title = t["title"]
                    obj.category = t.get("category")
                    obj.priority = t.get("priority")
                    obj.done = bool(t.get("done", False))
                    obj.comment = t.get("comment", "") or ""
            else:
                # insert
                s.add(Task(
                    id=task_id,
                    user_id=user_id,
                    title=t["title"],
                    category=t.get("category"),
                    priority=t.get("priority"),
                    done=bool(t.get("done", False)),
                    comment=t.get("comment", "") or "",
                ))

            # 3) теги: для простоты чистим и вставляем заново только для этой задачи
            s.execute(delete(TaskTag).where(TaskTag.task_id == task_id))
            for tag in (t.get("tags") or []):
                tag = str(tag).strip()
                if not tag:
                    continue
                s.merge(Tag(user_id=user_id, name=tag))
                s.add(TaskTag(task_id=task_id, tag=tag))

        # 4) delete только удалённые задачи
        to_delete = existing_ids - incoming_ids
        if to_delete:
            s.execute(delete(Task).where(Task.user_id == user_id, Task.id.in_(to_delete)))

        s.commit()


def load_categories(user_id: int):
    print("DEBUG: load_categories (orm)")
    with _session() as s:
        rows = s.execute(
            select(Category.name).where(Category.user_id == user_id).order_by(Category.name)
        ).all()
        categories = [r[0] for r in rows]
    print(f"DEBUG: load_categories -> {len(categories)} categories")
    if not categories:
        print("WARNING: load_categories returned empty list")
    return categories


def save_categories(user_id: int, categories: list[str]):
    print("DEBUG: save_categories (orm)")
    with _session() as s:
        s.execute(delete(Category).where(Category.user_id == user_id))
        for name in categories:
            name = str(name).strip()
            if name:
                s.add(Category(user_id=user_id, name=name))
        s.commit()


def load_tags(user_id: int):
    print("DEBUG: load_tags (orm)")
    with _session() as s:
        rows = s.execute(
            select(Tag.name).where(Tag.user_id == user_id).order_by(Tag.name)
        ).all()
        tags = [r[0] for r in rows]
    print(f"DEBUG: load_tags -> {len(tags)} tags")
    if not tags:
        print("WARNING: load_tags returned empty list")
    return tags


def load_active_tags(user_id: int):
    print("DEBUG: load_active_tags (orm)")
    with _session() as s:
        rows = s.execute(
            select(func.distinct(TaskTag.tag))
            .join(Task, Task.id == TaskTag.task_id)
            .where(Task.user_id == user_id, Task.done.is_(False))
            .order_by(TaskTag.tag)
        ).all()
        tags = [r[0] for r in rows]
    print(f"DEBUG: load_active_tags -> {len(tags)} tags")
    if not tags:
        print("WARNING: load_active_tags returned empty list")
    return tags


def load_settings(user_id: int):
    print("DEBUG: load_settings (orm)")
    with _session() as s:
        rows = s.execute(
            select(Setting.key, Setting.value).where(Setting.user_id == user_id)
        ).all()
        settings = {k: v for k, v in rows}
    print(f"DEBUG: load_settings -> {len(settings)} entries")
    if not settings:
        print("WARNING: load_settings returned empty dict")
    return settings


def save_setting(user_id: int, key: str, value: Any):
    print(f"DEBUG: save_setting (orm) {key}={value}")
    with _session() as s:
        row = s.get(Setting, {"user_id": user_id, "key": key})
        if row is None:
            s.add(Setting(user_id=user_id, key=key, value=str(value)))
        else:
            row.value = str(value)
        s.commit()
