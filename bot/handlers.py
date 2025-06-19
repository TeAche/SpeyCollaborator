from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackContext, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters

from .config import BOT_TOKEN, OWNER_CHAT_ID
from .constants import *
from .db import (
    init_db, load_tasks, save_tasks,
    load_categories, save_categories,
    load_tags, load_active_tags,
    load_settings, save_setting
)
from .keyboards import (
    build_keyboard, build_completed_keyboard, build_category_keyboard,
    build_priority_keyboard, build_filter_category_keyboard,
    build_filter_priority_keyboard, build_filter_tag_keyboard,
    build_tag_keyboard
)
from .utils import schedule_reminder_job


async def send_daily_tasks(context: CallbackContext):
    print("DEBUG: send_daily_tasks")
    tasks = load_tasks()
    markup = build_keyboard(tasks)
    text = 'Задачи на сегодня:' if markup else 'На сегодня задач нет.'
    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=text,
        reply_markup=markup,
    )

async def start(update: Update, context: CallbackContext):
    print('DEBUG: start')
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
    print('DEBUG: list_tasks')
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
    print('DEBUG: list_completed')
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
    print('DEBUG: task_selected')
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    context.user_data['task_id'] = task_id
    message = query.message
    if message:
        await message.reply_text('Введите комментарий к задаче:')
    return COMMENT


async def edit_task_start(update: Update, context: CallbackContext):
    print('DEBUG: edit_task_start')
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
    print('DEBUG: edit_task_category')
    context.user_data['edit_title'] = update.message.text
    categories = load_categories()
    markup = build_category_keyboard(categories)
    await update.message.reply_text('Выберите категорию:', reply_markup=markup)
    return EDIT_TASK_CATEGORY_CHOOSE


async def choose_edit_category(update: Update, context: CallbackContext):
    print('DEBUG: choose_edit_category')
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
    print('DEBUG: edit_task_category_input')
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
    print('DEBUG: choose_edit_priority')
    query = update.callback_query
    await query.answer()
    priority = query.data.split('_')[1]
    context.user_data['edit_priority'] = priority
    await query.message.reply_text('Введите теги через запятую (можно оставить пустым):')
    return EDIT_TASK_TAGS


async def edit_task_tags(update: Update, context: CallbackContext):
    print('DEBUG: edit_task_tags')
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
    print('DEBUG: save_comment')
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
    print('DEBUG: delete_task')
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
    print('DEBUG: restore_task')
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
    print('DEBUG: add_task_start')
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
        if message:
            await message.reply_text('Введите название новой задачи:')
    else:
        await update.message.reply_text('Введите название новой задачи:')
    return ADD_TASK_TITLE

async def add_task_category(update: Update, context: CallbackContext):
    print('DEBUG: add_task_category')
    context.user_data['new_title'] = update.message.text
    categories = load_categories()
    markup = build_category_keyboard(categories)
    await update.message.reply_text('Выберите категорию:', reply_markup=markup)
    return ADD_TASK_CATEGORY_CHOOSE


async def choose_task_category(update: Update, context: CallbackContext):
    print('DEBUG: choose_task_category')
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
    print('DEBUG: add_task_category_input')
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
    print('DEBUG: choose_task_priority')
    query = update.callback_query
    await query.answer()
    priority = query.data.split('_')[1]
    context.user_data['new_priority'] = priority
    await query.message.reply_text('Введите теги через запятую (можно оставить пустым):')
    return ADD_TASK_TAGS


async def add_task_tags(update: Update, context: CallbackContext):
    print('DEBUG: add_task_tags')
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
    print('DEBUG: categories_menu')
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
    print('DEBUG: category_add')
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text('Введите название новой категории:')
    else:
        await update.message.reply_text('Введите название новой категории:')
    return CATEGORY_ADD


async def save_new_category(update: Update, context: CallbackContext):
    print('DEBUG: save_new_category')
    name = update.message.text
    categories = load_categories()
    if name not in categories:
        categories.append(name)
        save_categories(categories)
    await categories_menu(update, context)
    return CATEGORY_MENU


async def category_edit_start(update: Update, context: CallbackContext):
    print('DEBUG: category_edit_start')
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split('_')[1])
    context.user_data['cat_index'] = idx
    await query.message.reply_text('Введите новое название категории:')
    return CATEGORY_EDIT


async def save_edited_category(update: Update, context: CallbackContext):
    print('DEBUG: save_edited_category')
    idx = context.user_data.get('cat_index')
    categories = load_categories()
    if 0 <= idx < len(categories):
        categories[idx] = update.message.text
        save_categories(categories)
    await categories_menu(update, context)
    return CATEGORY_MENU


async def delete_category(update: Update, context: CallbackContext):
    print('DEBUG: delete_category')
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
        await message.reply_text('Фильтр задач:', reply_markup=markup)
    return FILTER_MENU


async def filter_choose_category(update: Update, context: CallbackContext):
    print('DEBUG: filter_choose_category')
    query = update.callback_query
    await query.answer()
    categories = load_categories()
    markup = build_filter_category_keyboard(categories)
    await query.message.reply_text('Выберите категорию:', reply_markup=markup)
    return FILTER_MENU


async def filter_choose_priority(update: Update, context: CallbackContext):
    print('DEBUG: filter_choose_priority')
    query = update.callback_query
    await query.answer()
    markup = build_filter_priority_keyboard()
    await query.message.reply_text('Выберите приоритет:', reply_markup=markup)
    return FILTER_MENU


async def filter_choose_tag(update: Update, context: CallbackContext):
    print('DEBUG: filter_choose_tag')
    query = update.callback_query
    await query.answer()
    tags = load_active_tags()
    markup = build_filter_tag_keyboard(tags)
    await query.message.reply_text('Выберите тег:', reply_markup=markup)
    return FILTER_MENU


async def filter_set(update: Update, context: CallbackContext):
    print('DEBUG: filter_set')
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
            tags = load_active_tags()
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
    print('DEBUG: settings_set_time')
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Введите время в формате ЧЧ:ММ")
    else:
        await update.message.reply_text("Введите время в формате ЧЧ:ММ")
    return SETTINGS_TIME


async def settings_save_time(update: Update, context: CallbackContext):
    print('DEBUG: settings_save_time')
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
    print('DEBUG: toggle_weekends')
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
    print('DEBUG: cancel')
    message = update.message or (update.callback_query and update.callback_query.message)
    if update.callback_query:
        await update.callback_query.answer()
    if message:
        await message.reply_text('Действие отменено.')
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

    schedule_reminder_job(application)

    application.run_polling()


if __name__ == '__main__':
    main()
