import json
import os
import sqlite3
from datetime import time
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()  # загрузит переменные из .env

TASKS_FILE = 'tasks.json'
CATEGORIES_FILE = 'categories.json'
DB_FILE = 'tasks.db'
BOT_TOKEN = os.getenv('TOKEN', 'PLACEHOLDER_TOKEN')
OWNER_CHAT_ID = int(os.getenv('OWNER_CHAT_ID', '123456789'))

# Conversation states
(
    COMMENT,
    ADD_TASK_TITLE,
    ADD_TASK_CATEGORY_CHOOSE,
    ADD_TASK_CATEGORY_INPUT,
    ADD_TASK_PRIORITY,
    ADD_TASK_TAGS,
    EDIT_TASK_TITLE,
    EDIT_TASK_CATEGORY_CHOOSE,
    EDIT_TASK_CATEGORY_INPUT,
    EDIT_TASK_PRIORITY,
    EDIT_TASK_TAGS,
    CATEGORY_MENU,
    CATEGORY_EDIT,
    CATEGORY_ADD,
    SETTINGS_MENU,
    SETTINGS_TIME,
    FILTER_MENU,
) = range(17)


def init_db():
    """Создает таблицы БД и при первом запуске импортирует данные из JSON."""
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
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    conn.close()
    return [r[0] for r in rows]


def save_categories(categories):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM categories")
    for name in categories:
        conn.execute("INSERT INTO categories(name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def load_tags():
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
    conn.close()
    return [r[0] for r in rows]


def load_settings():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


def save_setting(key, value):
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def schedule_reminder_job(application):
    if not application.job_queue:
        return
    for job in application.job_queue.get_jobs_by_name("daily"):
        job.schedule_removal()
    settings = load_settings()
    time_str = settings.get("reminder_time", "09:00")
    hour, minute = map(int, time_str.split(":"))
    notify_weekends = settings.get("notify_weekends", "0") == "1"
    days = (0, 1, 2, 3, 4, 5, 6) if notify_weekends else (0, 1, 2, 3, 4)
    application.job_queue.run_daily(
        send_daily_tasks,
        time(hour=hour, minute=minute),
        days=days,
        name="daily",
    )


def build_keyboard(tasks, include_add_button=False):
    keyboard = []
    for task in tasks:
        if not task.get('done'):
            keyboard.append([
                InlineKeyboardButton(
                    f"{task['title']} ({task.get('category', '')}, {task.get('priority', '')})" + (f" [{', '.join(task.get('tags', []))}]" if task.get('tags') else ''),
                    callback_data=f"task_{task['id']}"
                )
            ])
            keyboard.append([
                InlineKeyboardButton('✏️', callback_data=f"edit_{task['id']}"),
                InlineKeyboardButton('🗑️', callback_data=f"delete_{task['id']}"),
            ])
    if include_add_button:
        keyboard.append([InlineKeyboardButton('Добавить задачу', callback_data='add_task')])
    if keyboard:
        return InlineKeyboardMarkup(keyboard)
    return InlineKeyboardMarkup([[InlineKeyboardButton('Добавить задачу', callback_data='add_task')]]) if include_add_button else None


def build_completed_keyboard(tasks):
    keyboard = []
    for task in tasks:
        if task.get('done'):
            keyboard.append([
                InlineKeyboardButton(
                    f"{task['title']} ({task.get('category', '')}, {task.get('priority', '')})" + (f" [{', '.join(task.get('tags', []))}]" if task.get('tags') else '') + " ✓",
                    callback_data=f"restore_{task['id']}"
                )
            ])
    if keyboard:
        return InlineKeyboardMarkup(keyboard)
    return None


def build_category_keyboard(categories, include_new=True):
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"choose_cat_{i}")]
                for i, cat in enumerate(categories)]
    if include_new:
        keyboard.append([InlineKeyboardButton('Новая категория', callback_data='new_category')])
    keyboard.append([InlineKeyboardButton('Отмена', callback_data='cancel')])
    return InlineKeyboardMarkup(keyboard)


def build_priority_keyboard():
    keyboard = [
        [InlineKeyboardButton('низкий', callback_data='priority_низкий')],
        [InlineKeyboardButton('средний', callback_data='priority_средний')],
        [InlineKeyboardButton('высокий', callback_data='priority_высокий')],
        [InlineKeyboardButton('Отмена', callback_data='cancel')],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_filter_category_keyboard(categories):
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"fcat_{i}")]
                for i, cat in enumerate(categories)]
    keyboard.append([InlineKeyboardButton('Любая', callback_data='fcat_none')])
    keyboard.append([InlineKeyboardButton('Назад', callback_data='filter')])
    return InlineKeyboardMarkup(keyboard)


def build_filter_priority_keyboard():
    keyboard = [
        [InlineKeyboardButton('низкий', callback_data='fprio_низкий')],
        [InlineKeyboardButton('средний', callback_data='fprio_средний')],
        [InlineKeyboardButton('высокий', callback_data='fprio_высокий')],
        [InlineKeyboardButton('Любой', callback_data='fprio_none')],
        [InlineKeyboardButton('Назад', callback_data='filter')],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_filter_tag_keyboard(tags):
    keyboard = [[InlineKeyboardButton(tag, callback_data=f"ftag_{i}")]
                for i, tag in enumerate(tags)]
    keyboard.append([InlineKeyboardButton('Любой', callback_data='ftag_none')])
    keyboard.append([InlineKeyboardButton('Назад', callback_data='filter')])
    return InlineKeyboardMarkup(keyboard)


def build_tag_keyboard(tags, include_new=True):
    keyboard = [[InlineKeyboardButton(tag, callback_data=f"choose_tag_{i}")]
                for i, tag in enumerate(tags)]
    if include_new:
        keyboard.append([InlineKeyboardButton('Новый тег', callback_data='new_tag')])
    keyboard.append([InlineKeyboardButton('Отмена', callback_data='cancel')])
    return InlineKeyboardMarkup(keyboard)


async def send_daily_tasks(context: CallbackContext):
    tasks = load_tasks()
    markup = build_keyboard(tasks)
    text = 'Задачи на сегодня:' if markup else 'На сегодня задач нет.'
    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=text,
        reply_markup=markup,
    )


async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton('Показать задачи', callback_data='show_tasks')],
        [InlineKeyboardButton('Добавить задачу', callback_data='add_task')],
        [InlineKeyboardButton('Категории', callback_data='categories')],
        [InlineKeyboardButton('Фильтр', callback_data='filter')],
        [InlineKeyboardButton('Настройки', callback_data='settings')],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    message = update.message or (update.callback_query and update.callback_query.message)
    if update.callback_query:
        await update.callback_query.answer()
    if message:
        await message.reply_text('Привет! Я помогу спланировать день.', reply_markup=markup)


async def list_tasks(update: Update, context: CallbackContext):
    tasks = load_tasks()
    filters_data = context.user_data.get('filters', {})
    category = filters_data.get('category')
    priority = filters_data.get('priority')
    tag = filters_data.get('tag')
    if category:
        tasks = [t for t in tasks if t.get('category') == category]
    if priority:
        tasks = [t for t in tasks if t.get('priority') == priority]
    if tag:
        tasks = [t for t in tasks if tag in t.get('tags', [])]
    markup = build_keyboard(tasks, include_add_button=True)
    text = 'Ваши задачи:' if tasks else 'Задач нет.'
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
        if message:
            await message.reply_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)


async def list_completed(update: Update, context: CallbackContext):
    tasks = load_tasks()
    markup = build_completed_keyboard(tasks)
    text = 'Выполненные задачи:' if markup else 'Выполненных задач нет.'
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
        if message:
            await message.reply_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)


async def task_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    context.user_data['task_id'] = task_id
    message = query.message
    if message:
        await message.reply_text('Введите комментарий к задаче:')
    return COMMENT


async def edit_task_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    context.user_data['edit_id'] = task_id
    tasks = load_tasks()
    title = next((t['title'] for t in tasks if t['id'] == task_id), '')
    message = query.message
    if message:
        await message.reply_text(f'Текущее название: {title}\nВведите новое название задачи:')
    return EDIT_TASK_TITLE


async def edit_task_category(update: Update, context: CallbackContext):
    context.user_data['edit_title'] = update.message.text
    categories = load_categories()
    markup = build_category_keyboard(categories)
    await update.message.reply_text('Выберите категорию:', reply_markup=markup)
    return EDIT_TASK_CATEGORY_CHOOSE


async def choose_edit_category(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data
    categories = load_categories()
    if data == 'new_category':
        await query.message.reply_text('Введите название новой категории:')
        return EDIT_TASK_CATEGORY_INPUT
    index = int(data.split('_')[2])
    context.user_data['edit_category'] = categories[index]
    markup = build_priority_keyboard()
    await query.message.reply_text('Выберите приоритет:', reply_markup=markup)
    return EDIT_TASK_PRIORITY


async def edit_task_category_input(update: Update, context: CallbackContext):
    new_cat = update.message.text
    categories = load_categories()
    if new_cat not in categories:
        categories.append(new_cat)
        save_categories(categories)
    context.user_data['edit_category'] = new_cat
    markup = build_priority_keyboard()
    await update.message.reply_text('Выберите приоритет:', reply_markup=markup)
    return EDIT_TASK_PRIORITY


async def choose_edit_priority(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    priority = query.data.split('_')[1]
    context.user_data['edit_priority'] = priority
    await query.message.reply_text('Введите теги через запятую (можно оставить пустым):')
    return EDIT_TASK_TAGS


async def edit_task_tags(update: Update, context: CallbackContext):
    tags_text = update.message.text.strip()
    tags = [t.strip() for t in tags_text.split(',') if t.strip()] if tags_text else []
    task_id = context.user_data.get('edit_id')
    tasks = load_tasks()
    for task in tasks:
        if task['id'] == task_id:
            task['title'] = context.user_data.get('edit_title')
            task['category'] = context.user_data.get('edit_category')
            task['priority'] = context.user_data.get('edit_priority')
            task['tags'] = tags
            break
    save_tasks(tasks)
    await update.message.reply_text('Задача обновлена.')
    await list_tasks(update, context)
    return ConversationHandler.END


async def save_comment(update: Update, context: CallbackContext):
    comment = update.message.text
    task_id = context.user_data.get('task_id')
    tasks = load_tasks()
    for task in tasks:
        if task['id'] == task_id:
            task['done'] = True
            task['comment'] = comment
            break
    save_tasks(tasks)
    await update.message.reply_text('Задача сохранена.')
    await send_daily_tasks(context)
    return ConversationHandler.END


async def delete_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    tasks = load_tasks()
    tasks = [t for t in tasks if t['id'] != task_id]
    save_tasks(tasks)
    if query.message:
        await query.message.reply_text('Задача удалена.')
    await list_tasks(update, context)


async def restore_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    tasks = load_tasks()
    for task in tasks:
        if task['id'] == task_id:
            task['done'] = False
            break
    save_tasks(tasks)
    if query.message:
        await query.message.reply_text('Задача восстановлена.')
    await list_tasks(update, context)


async def add_task_start(update: Update, context: CallbackContext):
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
        if message:
            await message.reply_text('Введите название новой задачи:')
    else:
        await update.message.reply_text('Введите название новой задачи:')
    return ADD_TASK_TITLE

async def add_task_category(update: Update, context: CallbackContext):
    context.user_data['new_title'] = update.message.text
    categories = load_categories()
    markup = build_category_keyboard(categories)
    await update.message.reply_text('Выберите категорию:', reply_markup=markup)
    return ADD_TASK_CATEGORY_CHOOSE


async def choose_task_category(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data
    categories = load_categories()
    if data == 'new_category':
        await query.message.reply_text('Введите название новой категории:')
        return ADD_TASK_CATEGORY_INPUT
    index = int(data.split('_')[2])
    context.user_data['new_category'] = categories[index]
    markup = build_priority_keyboard()
    await query.message.reply_text('Выберите приоритет:', reply_markup=markup)
    return ADD_TASK_PRIORITY


async def add_task_category_input(update: Update, context: CallbackContext):
    new_cat = update.message.text
    categories = load_categories()
    if new_cat not in categories:
        categories.append(new_cat)
        save_categories(categories)
    context.user_data['new_category'] = new_cat
    markup = build_priority_keyboard()
    await update.message.reply_text('Выберите приоритет:', reply_markup=markup)
    return ADD_TASK_PRIORITY


async def choose_task_priority(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    priority = query.data.split('_')[1]
    context.user_data['new_priority'] = priority
    await query.message.reply_text('Введите теги через запятую (можно оставить пустым):')
    return ADD_TASK_TAGS


async def add_task_tags(update: Update, context: CallbackContext):
    tags_text = update.message.text.strip()
    tags = [t.strip() for t in tags_text.split(',') if t.strip()] if tags_text else []
    title = context.user_data.get('new_title')
    category = context.user_data.get('new_category')
    priority = context.user_data.get('new_priority')
    tasks = load_tasks()
    new_id = max([t['id'] for t in tasks], default=0) + 1
    tasks.append({
        'id': new_id,
        'title': title,
        'category': category,
        'priority': priority,
        'tags': tags,
        'done': False,
        'comment': '',
    })
    save_tasks(tasks)
    await update.message.reply_text('Задача добавлена.')
    await list_tasks(update, context)
    return ConversationHandler.END


async def categories_menu(update: Update, context: CallbackContext):
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
    categories = load_categories()
    keyboard = [
        [InlineKeyboardButton(cat, callback_data=f'editcat_{i}'), InlineKeyboardButton('🗑️', callback_data=f'delcat_{i}')]
        for i, cat in enumerate(categories)
    ]
    keyboard.append([InlineKeyboardButton('Добавить категорию', callback_data='addcat')])
    keyboard.append([InlineKeyboardButton('Отмена', callback_data='cancel')])
    markup = InlineKeyboardMarkup(keyboard)
    if message:
        await message.reply_text('Категории:', reply_markup=markup)
    return CATEGORY_MENU


async def category_add(update: Update, context: CallbackContext):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text('Введите название новой категории:')
    else:
        await update.message.reply_text('Введите название новой категории:')
    return CATEGORY_ADD


async def save_new_category(update: Update, context: CallbackContext):
    name = update.message.text
    categories = load_categories()
    if name not in categories:
        categories.append(name)
        save_categories(categories)
    await categories_menu(update, context)
    return CATEGORY_MENU


async def category_edit_start(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split('_')[1])
    context.user_data['cat_index'] = idx
    await query.message.reply_text('Введите новое название категории:')
    return CATEGORY_EDIT


async def save_edited_category(update: Update, context: CallbackContext):
    idx = context.user_data.get('cat_index')
    categories = load_categories()
    if 0 <= idx < len(categories):
        categories[idx] = update.message.text
        save_categories(categories)
    await categories_menu(update, context)
    return CATEGORY_MENU


async def delete_category(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split('_')[1])
    categories = load_categories()
    if 0 <= idx < len(categories):
        categories.pop(idx)
        save_categories(categories)
    await categories_menu(update, context)
    return CATEGORY_MENU


async def filter_menu(update: Update, context: CallbackContext):
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
    keyboard = [
        [InlineKeyboardButton('Категория', callback_data='filter_category')],
        [InlineKeyboardButton('Приоритет', callback_data='filter_priority')],
        [InlineKeyboardButton('Тег', callback_data='filter_tag')],
        [InlineKeyboardButton('Сбросить', callback_data='filter_reset')],
        [InlineKeyboardButton('Отмена', callback_data='cancel')],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if message:
        await message.reply_text('Фильтр задач:', reply_markup=markup)
    return FILTER_MENU


async def filter_choose_category(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    categories = load_categories()
    markup = build_filter_category_keyboard(categories)
    await query.message.reply_text('Выберите категорию:', reply_markup=markup)
    return FILTER_MENU


async def filter_choose_priority(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    markup = build_filter_priority_keyboard()
    await query.message.reply_text('Выберите приоритет:', reply_markup=markup)
    return FILTER_MENU


async def filter_choose_tag(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    tags = load_tags()
    markup = build_filter_tag_keyboard(tags)
    await query.message.reply_text('Выберите тег:', reply_markup=markup)
    return FILTER_MENU


async def filter_set(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data
    filters_data = context.user_data.setdefault('filters', {})
    if data.startswith('fcat_'):
        if data == 'fcat_none':
            filters_data.pop('category', None)
        else:
            index = int(data.split('_')[1])
            categories = load_categories()
            if 0 <= index < len(categories):
                filters_data['category'] = categories[index]
    elif data.startswith('fprio_'):
        if data == 'fprio_none':
            filters_data.pop('priority', None)
        else:
            filters_data['priority'] = data.split('_')[1]
    elif data.startswith('ftag_'):
        if data == 'ftag_none':
            filters_data.pop('tag', None)
        else:
            index = int(data.split('_')[1])
            tags = load_tags()
            if 0 <= index < len(tags):
                filters_data['tag'] = tags[index]
    elif data == 'filter_reset':
        context.user_data.pop('filters', None)
    await list_tasks(update, context)
    return FILTER_MENU


async def settings_menu(update: Update, context: CallbackContext):
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
    settings = load_settings()
    time_str = settings.get("reminder_time", "09:00")
    weekends = settings.get("notify_weekends", "0") == "1"
    keyboard = [
        [InlineKeyboardButton(f"Время: {time_str}", callback_data="set_time")],
        [
            InlineKeyboardButton(
                ("Не уведомлять в выходные" if weekends else "Уведомлять в выходные"),
                callback_data="toggle_weekends",
            )
        ],
        [InlineKeyboardButton("Отмена", callback_data="cancel")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if message:
        await message.reply_text("Настройки напоминаний:", reply_markup=markup)
    return SETTINGS_MENU


async def settings_set_time(update: Update, context: CallbackContext):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Введите время в формате ЧЧ:ММ")
    else:
        await update.message.reply_text("Введите время в формате ЧЧ:ММ")
    return SETTINGS_TIME


async def settings_save_time(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    try:
        hour, minute = map(int, text.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
    except Exception:
        await update.message.reply_text("Неверный формат времени, попробуйте ещё раз.")
        return SETTINGS_TIME
    save_setting("reminder_time", f"{hour:02d}:{minute:02d}")
    await update.message.reply_text("Время напоминания обновлено.")
    schedule_reminder_job(context.application)
    return await settings_menu(update, context)


async def toggle_weekends(update: Update, context: CallbackContext):
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
    settings = load_settings()
    current = settings.get("notify_weekends", "0") == "1"
    save_setting("notify_weekends", "0" if current else "1")
    schedule_reminder_job(context.application)
    if message:
        await message.reply_text("Настройки обновлены.")
    return await settings_menu(update, context)


async def cancel(update: Update, context: CallbackContext):
    message = update.message or (update.callback_query and update.callback_query.message)
    if update.callback_query:
        await update.callback_query.answer()
    if message:
        await message.reply_text('Действие отменено.')
    await start(update, context)
    return ConversationHandler.END


def main():
    init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler(['tasks', 'list'], list_tasks))
    application.add_handler(CallbackQueryHandler(list_tasks, pattern='^show_tasks$'))

    comment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(task_selected, pattern=r'^task_')],
        states={
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel), CallbackQueryHandler(cancel, pattern='^cancel$')],
    )
    application.add_handler(comment_conv)

    add_conv = ConversationHandler(
        entry_points=[
            CommandHandler('add', add_task_start),
            CallbackQueryHandler(add_task_start, pattern='^add_task$'),
        ],
        states={
            ADD_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_category)],
            ADD_TASK_CATEGORY_CHOOSE: [CallbackQueryHandler(choose_task_category, pattern=r'^choose_cat_\d+$|^new_category$')],
            ADD_TASK_CATEGORY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_category_input)],
            ADD_TASK_PRIORITY: [CallbackQueryHandler(choose_task_priority, pattern=r'^priority_')],
            ADD_TASK_TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_tags)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel), CallbackQueryHandler(cancel, pattern='^cancel$')],
    )
    application.add_handler(add_conv)

    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_task_start, pattern=r'^edit_')],
        states={
            EDIT_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_category)],
            EDIT_TASK_CATEGORY_CHOOSE: [CallbackQueryHandler(choose_edit_category, pattern=r'^choose_cat_\d+$|^new_category$')],
            EDIT_TASK_CATEGORY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_category_input)],
            EDIT_TASK_PRIORITY: [CallbackQueryHandler(choose_edit_priority, pattern=r'^priority_')],
            EDIT_TASK_TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_tags)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel), CallbackQueryHandler(cancel, pattern='^cancel$')],
    )
    application.add_handler(edit_conv)

    cat_conv = ConversationHandler(
        entry_points=[CommandHandler('categories', categories_menu), CallbackQueryHandler(categories_menu, pattern='^categories$')],
        states={
            CATEGORY_MENU: [
                CallbackQueryHandler(category_edit_start, pattern=r'^editcat_\d+$'),
                CallbackQueryHandler(delete_category, pattern=r'^delcat_\d+$'),
                CallbackQueryHandler(category_add, pattern='^addcat$')
            ],
            CATEGORY_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_category)],
            CATEGORY_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_category)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel), CallbackQueryHandler(cancel, pattern='^cancel$')],
    )
    application.add_handler(cat_conv)

    filter_conv = ConversationHandler(
        entry_points=[CommandHandler('filter', filter_menu), CallbackQueryHandler(filter_menu, pattern='^filter$')],
        states={
            FILTER_MENU: [
                CallbackQueryHandler(filter_choose_category, pattern='^filter_category$'),
                CallbackQueryHandler(filter_choose_priority, pattern='^filter_priority$'),
                CallbackQueryHandler(filter_choose_tag, pattern='^filter_tag$'),
                CallbackQueryHandler(filter_set, pattern='^f(cat|prio|tag)_.*|^filter_reset$'),
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel), CallbackQueryHandler(cancel, pattern='^cancel$')],
    )
    application.add_handler(filter_conv)

    settings_conv = ConversationHandler(
        entry_points=[CommandHandler('settings', settings_menu), CallbackQueryHandler(settings_menu, pattern='^settings$')],
        states={
            SETTINGS_MENU: [
                CallbackQueryHandler(settings_set_time, pattern='^set_time$'),
                CallbackQueryHandler(toggle_weekends, pattern='^toggle_weekends$'),
            ],
            SETTINGS_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_save_time)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel), CallbackQueryHandler(cancel, pattern='^cancel$')],
    )
    application.add_handler(settings_conv)

    application.add_handler(CallbackQueryHandler(delete_task, pattern=r'^delete_'))
    application.add_handler(CallbackQueryHandler(restore_task, pattern=r'^restore_'))
    application.add_handler(CommandHandler('completed', list_completed))

    schedule_reminder_job(application)

    application.run_polling()


if __name__ == '__main__':
    main()
