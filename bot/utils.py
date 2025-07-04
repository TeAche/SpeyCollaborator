from datetime import time
from telegram import Update
import logging
from telegram.ext import Application

logger = logging.getLogger(__name__)

from .db import load_settings


def schedule_reminder_job(application: Application):
    print("DEBUG: schedule_reminder_job")
    from .handlers import send_daily_tasks  # local import to avoid circular
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


async def send_and_store(context, chat_id: int, text: str, reply_markup=None):
    print('DEBUG: send_and_store')
    try:
        sent = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    except Exception:
        logger.exception("Failed to send message to %s: %s", chat_id, text)
        return None
    if hasattr(context, 'chat_data'):
        context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)
    return sent


async def reply_or_edit(update: Update, context, text: str, reply_markup=None):
    """Send or edit message depending on update type."""
    message = update.message or (update.callback_query and update.callback_query.message)
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            logger.exception("Failed to answer callback query")
        if message:
            try:
                await message.edit_text(text, reply_markup=reply_markup)
            except Exception:
                logger.exception("Failed to edit message: %s", text)
    else:
        if message:
            try:
                sent = await message.reply_text(text, reply_markup=reply_markup)
            except Exception:
                logger.exception("Failed to send reply: %s", text)
            else:
                if hasattr(context, 'chat_data'):
                    context.chat_data.setdefault('bot_messages', set()).add(sent.message_id)


