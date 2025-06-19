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
COMMENT, ADD_TASK_TITLE = range(2)


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
            keyboard.append([InlineKeyboardButton(task['title'], callback_data=f"task_{task['id']}")])
    if include_add_button:
        keyboard.append([InlineKeyboardButton('Добавить задачу', callback_data='add_task')])
    if keyboard:
        return InlineKeyboardMarkup(keyboard)
    return InlineKeyboardMarkup([[InlineKeyboardButton('Добавить задачу', callback_data='add_task')]]) if include_add_button else None


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


async def task_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    context.user_data['task_id'] = task_id
    message = query.message
    if message:
        await message.reply_text('Введите комментарий к задаче:')
    return COMMENT


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


async def add_task_start(update: Update, context: CallbackContext):
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
        if message:
            await message.reply_text('Введите название новой задачи:')
    else:
        await update.message.reply_text('Введите название новой задачи:')
    return ADD_TASK_TITLE


async def save_new_task(update: Update, context: CallbackContext):
    title = update.message.text
    tasks = load_tasks()
    new_id = max([t['id'] for t in tasks], default=0) + 1
    tasks.append({'id': new_id, 'title': title, 'done': False, 'comment': ''})
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
            ADD_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_task)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(add_conv)

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
