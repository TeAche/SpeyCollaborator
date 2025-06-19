import json
import os
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
BOT_TOKEN = os.getenv('TOKEN', 'PLACEHOLDER_TOKEN')
OWNER_CHAT_ID = int(os.getenv('OWNER_CHAT_ID', '123456789'))

# Conversation states
(
    COMMENT,
    ADD_TASK_TITLE,
    ADD_TASK_CATEGORY,
    ADD_TASK_PRIORITY,
    EDIT_TASK_TITLE,
    EDIT_TASK_CATEGORY,
    EDIT_TASK_PRIORITY,
) = range(7)


def load_tasks():
    if not os.path.exists(TASKS_FILE):
        return []
    with open(TASKS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tasks(tasks):
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def build_keyboard(tasks, include_add_button=False):
    keyboard = []
    for task in tasks:
        if not task.get('done'):
            keyboard.append([
                InlineKeyboardButton(
                    f"{task['title']} ({task.get('category', '')}, {task.get('priority', '')})",
                    callback_data=f"task_{task['id']}"
                ),
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
                    f"{task['title']} ({task.get('category', '')}, {task.get('priority', '')}) ✓",
                    callback_data=f"restore_{task['id']}"
                )
            ])
    if keyboard:
        return InlineKeyboardMarkup(keyboard)
    return None


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
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Привет! Я помогу спланировать день.', reply_markup=markup)


async def list_tasks(update: Update, context: CallbackContext):
    tasks = load_tasks()
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
    message = query.message
    if message:
        await message.reply_text('Введите новое название задачи:')
    return EDIT_TASK_TITLE


async def edit_task_category(update: Update, context: CallbackContext):
    context.user_data['edit_title'] = update.message.text
    await update.message.reply_text('Введите новую категорию:')
    return EDIT_TASK_CATEGORY


async def edit_task_priority(update: Update, context: CallbackContext):
    context.user_data['edit_category'] = update.message.text
    await update.message.reply_text('Введите новый приоритет (низкий/средний/высокий):')
    return EDIT_TASK_PRIORITY


async def save_edited_task(update: Update, context: CallbackContext):
    priority = update.message.text
    task_id = context.user_data.get('edit_id')
    tasks = load_tasks()
    for task in tasks:
        if task['id'] == task_id:
            task['title'] = context.user_data.get('edit_title')
            task['category'] = context.user_data.get('edit_category')
            task['priority'] = priority
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
    await update.message.reply_text('Введите категорию:')
    return ADD_TASK_CATEGORY


async def add_task_priority(update: Update, context: CallbackContext):
    context.user_data['new_category'] = update.message.text
    await update.message.reply_text('Введите приоритет (низкий/средний/высокий):')
    return ADD_TASK_PRIORITY


async def save_new_task(update: Update, context: CallbackContext):
    priority = update.message.text
    title = context.user_data.get('new_title')
    category = context.user_data.get('new_category')
    tasks = load_tasks()
    new_id = max([t['id'] for t in tasks], default=0) + 1
    tasks.append({
        'id': new_id,
        'title': title,
        'category': category,
        'priority': priority,
        'done': False,
        'comment': '',
    })
    save_tasks(tasks)
    await update.message.reply_text('Задача добавлена.')
    await list_tasks(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text('Действие отменено.')
    return ConversationHandler.END


def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler(['tasks', 'list'], list_tasks))
    application.add_handler(CallbackQueryHandler(list_tasks, pattern='^show_tasks$'))

    comment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(task_selected, pattern=r'^task_')],
        states={
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(comment_conv)

    add_conv = ConversationHandler(
        entry_points=[
            CommandHandler('add', add_task_start),
            CallbackQueryHandler(add_task_start, pattern='^add_task$'),
        ],
        states={
            ADD_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_category)],
            ADD_TASK_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_priority)],
            ADD_TASK_PRIORITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_task)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(add_conv)

    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_task_start, pattern=r'^edit_')],
        states={
            EDIT_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_category)],
            EDIT_TASK_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_priority)],
            EDIT_TASK_PRIORITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_task)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(edit_conv)

    application.add_handler(CallbackQueryHandler(delete_task, pattern=r'^delete_'))
    application.add_handler(CallbackQueryHandler(restore_task, pattern=r'^restore_'))
    application.add_handler(CommandHandler('completed', list_completed))

    # Job to send tasks daily at 9:00 on weekdays
    if application.job_queue:
        application.job_queue.run_daily(
            send_daily_tasks,
            time(hour=9, minute=0),
            days=(0, 1, 2, 3, 4),
        )
    else:
        print(
            "Warning: JobQueue is not available. Install python-telegram-bot[job-queue] to enable scheduled tasks."
        )

    application.run_polling()


if __name__ == '__main__':
    main()
