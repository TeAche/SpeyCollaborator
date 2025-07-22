import logging

logger = logging.getLogger(__name__)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackContext, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters

from .config import BOT_TOKEN, OWNER_CHAT_ID
from .constants import *
from .db import (
    init_db,
    load_tasks,
    save_tasks,
    load_categories,
    save_categories,
    load_tags,
    load_active_tags,
    load_settings,
    save_setting,
    register_user,
    get_next_task_id,
    get_all_users,
)
from .keyboards import (
    build_keyboard, build_completed_keyboard, build_category_keyboard,
    build_priority_keyboard, build_filter_category_keyboard,
    build_filter_priority_keyboard, build_filter_tag_keyboard,
    build_tag_keyboard, build_cancel_keyboard
)
from .utils import schedule_reminder_job, reply_or_edit, send_and_store


async def send_daily_tasks(context: CallbackContext, user_id: int | None = None):
    print("DEBUG: send_daily_tasks")
    if user_id is None:
        if getattr(context, "job", None) and context.job.data:
            user_id = context.job.data.get("user_id", OWNER_CHAT_ID)
        else:
            user_id = OWNER_CHAT_ID
    tasks = load_tasks(user_id)
    markup = build_keyboard(tasks)
    text = 'Задачи на сегодня:' if markup else 'На сегодня задач нет.'
    await send_and_store(context, user_id, text, reply_markup=markup)

async def start(update: Update, context: CallbackContext):
    print('DEBUG: start')
    if update.callback_query:
        await update.callback_query.answer()
    chat_id = update.effective_chat.id
    register_user(chat_id, update.effective_user.full_name)
    schedule_reminder_job(context.application)
    # Clear any saved filters to avoid showing a filtered task list
    context.user_data['filters'] = {}
    for mid in context.chat_data.get('bot_messages', set()):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            logger.exception("Failed to delete message %s" , mid)
    context.chat_data['bot_messages'] = set()
    keyboard = [
        [InlineKeyboardButton('Показать задачи', callback_data='show_tasks')],
        [InlineKeyboardButton('Добавить задачу', callback_data='add_task')],
        [InlineKeyboardButton('Категории', callback_data='categories')],
        [InlineKeyboardButton('Фильтр', callback_data='filter')],
        [InlineKeyboardButton('Настройки', callback_data='settings')],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await send_and_store(context, chat_id, 'Привет! Я помогу спланировать день.', reply_markup=markup)


async def list_tasks(update: Update, context: CallbackContext):
    print('DEBUG: list_tasks')
    chat_id = update.effective_chat.id
    tasks = load_tasks(chat_id)
    print(f'DEBUG: list_tasks loaded {len(tasks)} tasks')
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
    print(f'DEBUG: list_tasks after filtering -> {len(tasks)} tasks')
    if not tasks:
        print('WARNING: list_tasks resulting list is empty')
    markup = build_keyboard(tasks, include_add_button=True, include_back_button=True)
    text = 'Ваши задачи:' if tasks else 'Задач нет.'
    await reply_or_edit(update, context, text, reply_markup=markup)


async def list_completed(update: Update, context: CallbackContext):
    print('DEBUG: list_completed')
    chat_id = update.effective_chat.id
    tasks = load_tasks(chat_id)
    markup = build_completed_keyboard(tasks, include_back_button=True)
    text = 'Выполненные задачи:' if markup else 'Выполненных задач нет.'
    await reply_or_edit(update, context, text, reply_markup=markup)


async def task_selected(update: Update, context: CallbackContext):
    print('DEBUG: task_selected')
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    context.user_data['task_id'] = task_id
    message = query.message
    if message:
        try:
            await message.edit_text('Введите комментарий к задаче:', reply_markup=build_cancel_keyboard())
        except Exception:
            logger.exception('Failed to edit message')
    return COMMENT


async def edit_task_start(update: Update, context: CallbackContext):
    print('DEBUG: edit_task_start')
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    context.user_data['edit_id'] = task_id
    chat_id = update.effective_chat.id
    tasks = load_tasks(chat_id)
    title = next((t['title'] for t in tasks if t['id'] == task_id), '')
    message = query.message
    if message:
        try:
            await message.edit_text(f'Текущее название: {title}\nВведите новое название задачи:', reply_markup=build_cancel_keyboard())
        except Exception:
            logger.exception('Failed to edit message')
    return EDIT_TASK_TITLE


async def edit_task_category(update: Update, context: CallbackContext):
    print('DEBUG: edit_task_category')
    context.user_data['edit_title'] = update.message.text
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    markup = build_category_keyboard(categories)
    try:
        sent = await update.message.reply_text('Выберите категорию:', reply_markup=markup)
    except Exception:
        logger.exception('Failed to send reply')
    else:
        context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return EDIT_TASK_CATEGORY_CHOOSE


async def choose_edit_category(update: Update, context: CallbackContext):
    print('DEBUG: choose_edit_category')
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    if data == 'new_category':
        try:
            await query.message.edit_text('Введите название новой категории:', reply_markup=build_cancel_keyboard())
        except Exception:
            logger.exception('Failed to edit message')
        return EDIT_TASK_CATEGORY_INPUT
    index = int(data.split('_')[2])
    context.user_data['edit_category'] = categories[index]
    markup = build_priority_keyboard()
    try:
        await query.message.edit_text('Выберите приоритет:', reply_markup=markup)
    except Exception:
        logger.exception('Failed to edit message')
    return EDIT_TASK_PRIORITY


async def edit_task_category_input(update: Update, context: CallbackContext):
    print('DEBUG: edit_task_category_input')
    new_cat = update.message.text
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    if new_cat not in categories:
        categories.append(new_cat)
        save_categories(chat_id, categories)
    context.user_data['edit_category'] = new_cat
    markup = build_priority_keyboard()
    try:
        sent = await update.message.reply_text('Выберите приоритет:', reply_markup=markup)
    except Exception:
        logger.exception('Failed to send reply')
    else:
        context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return EDIT_TASK_PRIORITY


async def choose_edit_priority(update: Update, context: CallbackContext):
    print('DEBUG: choose_edit_priority')
    query = update.callback_query
    await query.answer()
    priority = query.data.split('_')[1]
    context.user_data['edit_priority'] = priority
    task_id = context.user_data.get('edit_id')
    chat_id = update.effective_chat.id
    tasks = load_tasks(chat_id)
    for task in tasks:
        if task['id'] == task_id:
            task['title'] = context.user_data.get('edit_title')
            task['category'] = context.user_data.get('edit_category')
            task['priority'] = context.user_data.get('edit_priority')
            break
    save_tasks(chat_id, tasks)
    try:
        await query.message.edit_text('Задача обновлена.')
    except Exception:
        logger.exception('Failed to edit message')
    await list_tasks(update, context)
    return ConversationHandler.END


async def add_tags_to_task(update: Update, context: CallbackContext):
    print('DEBUG: add_tags_to_task')
    tags_text = update.message.text.strip()
    tags = [t.strip() for t in tags_text.split(',') if t.strip()] if tags_text else []
    task_id = context.user_data.get('tag_id')
    chat_id = update.effective_chat.id
    tasks = load_tasks(chat_id)
    for task in tasks:
        if task['id'] == task_id:
            current_tags = task.get('tags', [])
            for tag in tags:
                if tag not in current_tags:
                    current_tags.append(tag)
            task['tags'] = current_tags
            break
    save_tasks(chat_id, tasks)
    try:
        sent = await update.message.reply_text('Теги добавлены.')
    except Exception:
        logger.exception('Failed to send reply')
    else:
        context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    await list_tasks(update, context)
    return ConversationHandler.END


async def save_comment(update: Update, context: CallbackContext):
    print('DEBUG: save_comment')
    comment = update.message.text
    task_id = context.user_data.get('task_id')
    chat_id = update.effective_chat.id
    tasks = load_tasks(chat_id)
    for task in tasks:
        if task['id'] == task_id:
            task['done'] = True
            task['comment'] = comment
            break
    done_count = sum(1 for t in tasks if t.get('done'))
    print(f'DEBUG: save_comment marked task {task_id} done. Done count {done_count}')
    save_tasks(chat_id, tasks)
    try:
        sent = await update.message.reply_text('Задача сохранена.')
    except Exception:
        logger.exception('Failed to send reply')
    else:
        context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    await send_daily_tasks(context, chat_id)
    return ConversationHandler.END


async def delete_task(update: Update, context: CallbackContext):
    print('DEBUG: delete_task')
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    chat_id = update.effective_chat.id
    tasks = load_tasks(chat_id)
    tasks = [t for t in tasks if t['id'] != task_id]
    print(f'DEBUG: delete_task remaining {len(tasks)} tasks')
    save_tasks(chat_id, tasks)
    if query.message:
        try:
            await query.message.edit_text('Задача удалена.')
        except Exception:
            logger.exception('Failed to edit message')
    await list_tasks(update, context)


async def restore_task(update: Update, context: CallbackContext):
    print('DEBUG: restore_task')
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    chat_id = update.effective_chat.id
    tasks = load_tasks(chat_id)
    for task in tasks:
        if task['id'] == task_id:
            task['done'] = False
            break
    done_count = sum(1 for t in tasks if t.get('done'))
    print(f'DEBUG: restore_task restored {task_id}. Done count {done_count}')
    save_tasks(chat_id, tasks)
    if query.message:
        try:
            await query.message.edit_text('Задача восстановлена.')
        except Exception:
            logger.exception('Failed to edit message')
    await list_tasks(update, context)


async def add_tag_start(update: Update, context: CallbackContext):
    print('DEBUG: add_tag_start')
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    context.user_data['tag_id'] = task_id
    try:
        await query.message.edit_text('Введите теги через запятую:', reply_markup=build_cancel_keyboard())
    except Exception:
        logger.exception('Failed to edit message')
    return EDIT_TASK_TAGS


async def add_task_start(update: Update, context: CallbackContext):
    print('DEBUG: add_task_start')
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
        if message:
            try:
                await message.edit_text('Введите название новой задачи:', reply_markup=build_cancel_keyboard())
            except Exception:
                logger.exception('Failed to edit message')
    else:
        try:
            sent = await update.message.reply_text('Введите название новой задачи:', reply_markup=build_cancel_keyboard())
        except Exception:
            logger.exception('Failed to send reply')
        else:
            context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return ADD_TASK_TITLE

async def add_task_category(update: Update, context: CallbackContext):
    print('DEBUG: add_task_category')
    context.user_data['new_title'] = update.message.text
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    markup = build_category_keyboard(categories)
    try:
        sent = await update.message.reply_text('Выберите категорию:', reply_markup=markup)
    except Exception:
        logger.exception('Failed to send reply')
    else:
        context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return ADD_TASK_CATEGORY_CHOOSE


async def choose_task_category(update: Update, context: CallbackContext):
    print('DEBUG: choose_task_category')
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    if data == 'new_category':
        try:
            await query.message.edit_text('Введите название новой категории:', reply_markup=build_cancel_keyboard())
        except Exception:
            logger.exception('Failed to edit message')
        return ADD_TASK_CATEGORY_INPUT
    index = int(data.split('_')[2])
    context.user_data['new_category'] = categories[index]
    markup = build_priority_keyboard()
    try:
        await query.message.edit_text('Выберите приоритет:', reply_markup=markup)
    except Exception:
        logger.exception('Failed to edit message')
    return ADD_TASK_PRIORITY


async def add_task_category_input(update: Update, context: CallbackContext):
    print('DEBUG: add_task_category_input')
    new_cat = update.message.text
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    if new_cat not in categories:
        categories.append(new_cat)
        save_categories(chat_id, categories)
    context.user_data['new_category'] = new_cat
    markup = build_priority_keyboard()
    try:
        sent = await update.message.reply_text('Выберите приоритет:', reply_markup=markup)
    except Exception:
        logger.exception('Failed to send reply')
    else:
        context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return ADD_TASK_PRIORITY


async def choose_task_priority(update: Update, context: CallbackContext):
    print('DEBUG: choose_task_priority')
    query = update.callback_query
    await query.answer()
    priority = query.data.split('_')[1]
    context.user_data['new_priority'] = priority
    try:
        await query.message.edit_text('Введите теги через запятую (можно оставить пустым):', reply_markup=build_cancel_keyboard())
    except Exception:
        logger.exception('Failed to edit message')
    return ADD_TASK_TAGS


async def add_task_tags(update: Update, context: CallbackContext):
    print('DEBUG: add_task_tags')
    tags_text = update.message.text.strip()
    tags = [t.strip() for t in tags_text.split(',') if t.strip()] if tags_text else []
    title = context.user_data.get('new_title')
    category = context.user_data.get('new_category')
    priority = context.user_data.get('new_priority')
    chat_id = update.effective_chat.id
    tasks = load_tasks(chat_id)
    new_id = get_next_task_id()
    tasks.append({
        'id': new_id,
        'title': title,
        'category': category,
        'priority': priority,
        'tags': tags,
        'done': False,
        'comment': '',
    })
    print(f'DEBUG: add_task_tags added task id {new_id}. Total {len(tasks)} tasks')
    save_tasks(chat_id, tasks)
    try:
        sent = await update.message.reply_text('Задача добавлена.')
    except Exception:
        logger.exception('Failed to send reply')
    else:
        context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    await list_tasks(update, context)
    return ConversationHandler.END


async def categories_menu(update: Update, context: CallbackContext):
    print('DEBUG: categories_menu')
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    print(f'DEBUG: categories_menu -> {len(categories)} categories')
    keyboard = [
        [InlineKeyboardButton(cat, callback_data=f'editcat_{i}'), InlineKeyboardButton('🗑️', callback_data=f'delcat_{i}')]
        for i, cat in enumerate(categories)
    ]
    keyboard.append([InlineKeyboardButton('Добавить категорию', callback_data='addcat')])
    keyboard.append([InlineKeyboardButton('Отмена', callback_data='cancel')])
    markup = InlineKeyboardMarkup(keyboard)
    if message:
        if update.callback_query:
            try:
                await message.edit_text('Категории:', reply_markup=markup)
            except Exception:
                logger.exception('Failed to edit message')
        else:
            try:
                sent = await message.reply_text('Категории:', reply_markup=markup)
            except Exception:
                logger.exception('Failed to send reply')
            else:
                context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return CATEGORY_MENU


async def category_add(update: Update, context: CallbackContext):
    print('DEBUG: category_add')
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.edit_text('Введите название новой категории:', reply_markup=build_cancel_keyboard())
        except Exception:
            logger.exception('Failed to edit message')
    else:
        try:
            sent = await update.message.reply_text('Введите название новой категории:', reply_markup=build_cancel_keyboard())
        except Exception:
            logger.exception('Failed to send reply')
        else:
            context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return CATEGORY_ADD


async def save_new_category(update: Update, context: CallbackContext):
    print('DEBUG: save_new_category')
    name = update.message.text
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    if name not in categories:
        categories.append(name)
        save_categories(chat_id, categories)
    await categories_menu(update, context)
    return CATEGORY_MENU


async def category_edit_start(update: Update, context: CallbackContext):
    print('DEBUG: category_edit_start')
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split('_')[1])
    context.user_data['cat_index'] = idx
    try:
        await query.message.edit_text('Введите новое название категории:', reply_markup=build_cancel_keyboard())
    except Exception:
        logger.exception('Failed to edit message')
    return CATEGORY_EDIT


async def save_edited_category(update: Update, context: CallbackContext):
    print('DEBUG: save_edited_category')
    idx = context.user_data.get('cat_index')
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    if 0 <= idx < len(categories):
        categories[idx] = update.message.text
        save_categories(chat_id, categories)
    await categories_menu(update, context)
    return CATEGORY_MENU


async def delete_category(update: Update, context: CallbackContext):
    print('DEBUG: delete_category')
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split('_')[1])
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    if 0 <= idx < len(categories):
        categories.pop(idx)
        save_categories(chat_id, categories)
    await categories_menu(update, context)
    return CATEGORY_MENU


async def filter_menu(update: Update, context: CallbackContext):
    print('DEBUG: filter_menu')
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
        if update.callback_query:
            try:
                await message.edit_text('Фильтр задач:', reply_markup=markup)
            except Exception:
                logger.exception('Failed to edit message')
        else:
            try:
                sent = await message.reply_text('Фильтр задач:', reply_markup=markup)
            except Exception:
                logger.exception('Failed to send reply')
            else:
                context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return FILTER_MENU


async def filter_choose_category(update: Update, context: CallbackContext):
    print('DEBUG: filter_choose_category')
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    categories = load_categories(chat_id)
    markup = build_filter_category_keyboard(categories)
    try:
        await query.message.edit_text('Выберите категорию:', reply_markup=markup)
    except Exception:
        logger.exception('Failed to edit message')
    return FILTER_MENU


async def filter_choose_priority(update: Update, context: CallbackContext):
    print('DEBUG: filter_choose_priority')
    query = update.callback_query
    await query.answer()
    markup = build_filter_priority_keyboard()
    try:
        await query.message.edit_text('Выберите приоритет:', reply_markup=markup)
    except Exception:
        logger.exception('Failed to edit message')
    return FILTER_MENU


async def filter_choose_tag(update: Update, context: CallbackContext):
    print('DEBUG: filter_choose_tag')
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    tags = load_active_tags(chat_id)
    markup = build_filter_tag_keyboard(tags)
    try:
        await query.message.edit_text('Выберите тег:', reply_markup=markup)
    except Exception:
        logger.exception('Failed to edit message')
    return FILTER_MENU


async def filter_set(update: Update, context: CallbackContext):
    print('DEBUG: filter_set')
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    filters_data = context.user_data.setdefault('filters', {})
    if data.startswith('fcat_'):
        if data == 'fcat_none':
            filters_data.pop('category', None)
        else:
            index = int(data.split('_')[1])
            categories = load_categories(chat_id)
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
            tags = load_active_tags(chat_id)
            if 0 <= index < len(tags):
                filters_data['tag'] = tags[index]
    elif data == 'filter_reset':
        context.user_data.pop('filters', None)
    await list_tasks(update, context)
    return FILTER_MENU


async def settings_menu(update: Update, context: CallbackContext):
    print('DEBUG: settings_menu')
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
    chat_id = update.effective_chat.id
    settings = load_settings(chat_id)
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
        if update.callback_query:
            try:
                await message.edit_text("Настройки напоминаний:", reply_markup=markup)
            except Exception:
                logger.exception('Failed to edit message')
        else:
            try:
                sent = await message.reply_text("Настройки напоминаний:", reply_markup=markup)
            except Exception:
                logger.exception('Failed to send reply')
            else:
                context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return SETTINGS_MENU


async def settings_set_time(update: Update, context: CallbackContext):
    print('DEBUG: settings_set_time')
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.edit_text("Введите время в формате ЧЧ:ММ", reply_markup=build_cancel_keyboard())
        except Exception:
            logger.exception('Failed to edit message')
    else:
        try:
            sent = await update.message.reply_text("Введите время в формате ЧЧ:ММ", reply_markup=build_cancel_keyboard())
        except Exception:
            logger.exception('Failed to send reply')
        else:
            context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return SETTINGS_TIME


async def settings_save_time(update: Update, context: CallbackContext):
    print('DEBUG: settings_save_time')
    text = update.message.text.strip()
    try:
        hour, minute = map(int, text.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
    except Exception:
        try:
            sent = await update.message.reply_text("Неверный формат времени, попробуйте ещё раз.")
        except Exception:
            logger.exception('Failed to send reply')
        else:
            context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
        return SETTINGS_TIME
    chat_id = update.effective_chat.id
    save_setting(chat_id, "reminder_time", f"{hour:02d}:{minute:02d}")
    try:
        sent = await update.message.reply_text("Время напоминания обновлено.")
    except Exception:
        logger.exception('Failed to send reply')
    else:
        context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    schedule_reminder_job(context.application)
    return await settings_menu(update, context)


async def toggle_weekends(update: Update, context: CallbackContext):
    print('DEBUG: toggle_weekends')
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
    chat_id = update.effective_chat.id
    settings = load_settings(chat_id)
    current = settings.get("notify_weekends", "0") == "1"
    save_setting(chat_id, "notify_weekends", "0" if current else "1")
    schedule_reminder_job(context.application)
    if message:
        if update.callback_query:
            try:
                await message.edit_text("Настройки обновлены.")
            except Exception:
                logger.exception('Failed to edit message')
        else:
            try:
                sent = await message.reply_text("Настройки обновлены.")
            except Exception:
                logger.exception('Failed to send reply')
            else:
                context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return await settings_menu(update, context)


async def cancel(update: Update, context: CallbackContext):
    print('DEBUG: cancel')
    message = update.message or (update.callback_query and update.callback_query.message)
    if update.callback_query:
        await update.callback_query.answer()
    if message:
        if update.callback_query:
            try:
                await message.edit_text('Действие отменено.')
            except Exception:
                logger.exception('Failed to edit message')
        else:
            try:
                sent = await message.reply_text('Действие отменено.')
            except Exception:
                logger.exception('Failed to send reply')
            else:
                context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    await start(update, context)
    return ConversationHandler.END


def main():
    print('DEBUG: main')
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
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel), CallbackQueryHandler(cancel, pattern='^cancel$')],
    )
    application.add_handler(edit_conv)

    tag_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_tag_start, pattern=r'^tag_')],
        states={
            EDIT_TASK_TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_tags_to_task)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', cancel), CallbackQueryHandler(cancel, pattern='^cancel$')],
    )
    application.add_handler(tag_conv)

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
                CommandHandler('filter', filter_menu),
                CallbackQueryHandler(filter_menu, pattern='^filter$'),
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
    application.add_handler(CallbackQueryHandler(cancel, pattern='^cancel$'))

    schedule_reminder_job(application)

    application.run_polling()


if __name__ == '__main__':
    main()
