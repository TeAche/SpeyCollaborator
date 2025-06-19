import json
import os
from datetime import time
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (ApplicationBuilder, CallbackContext, CallbackQueryHandler,
                          CommandHandler, ConversationHandler, MessageHandler,
                          filters)

load_dotenv()  # загрузит переменные из .env

TASKS_FILE = 'tasks.json'
BOT_TOKEN = os.getenv('TOKEN', 'PLACEHOLDER_TOKEN')
OWNER_CHAT_ID = int(os.getenv('OWNER_CHAT_ID', '123456789'))

# Conversation states
COMMENT = 1


def load_tasks():
    if not os.path.exists(TASKS_FILE):
        return []
    with open(TASKS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tasks(tasks):
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def build_keyboard(tasks):
    keyboard = []
    for task in tasks:
        if not task.get('done'):
            keyboard.append([InlineKeyboardButton(task['title'], callback_data=f"task_{task['id']}")])
    return InlineKeyboardMarkup(keyboard) if keyboard else None


def send_daily_tasks(context: CallbackContext):
    tasks = load_tasks()
    markup = build_keyboard(tasks)
    text = 'Задачи на сегодня:' if markup else 'На сегодня задач нет.'
    context.bot.send_message(chat_id=OWNER_CHAT_ID, text=text, reply_markup=markup)


def start(update: Update, context: CallbackContext):
    update.message.reply_text('Привет! Я помогу спланировать день.')


def list_tasks(update: Update, context: CallbackContext):
    tasks = load_tasks()
    markup = build_keyboard(tasks)
    text = 'Ваши задачи:' if markup else 'Задач нет.'
    update.message.reply_text(text, reply_markup=markup)


def task_selected(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    task_id = int(query.data.split('_')[1])
    context.user_data['task_id'] = task_id
    query.message.reply_text('Введите комментарий к задаче:')
    return COMMENT


def save_comment(update: Update, context: CallbackContext):
    comment = update.message.text
    task_id = context.user_data.get('task_id')
    tasks = load_tasks()
    for task in tasks:
        if task['id'] == task_id:
            task['done'] = True
            task['comment'] = comment
            break
    save_tasks(tasks)
    update.message.reply_text('Задача сохранена.')
    send_daily_tasks(context)
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext):
    update.message.reply_text('Действие отменено.')
    return ConversationHandler.END


def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('tasks', list_tasks))

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(task_selected, pattern=r'^task_')],
        states={
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv)

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
