from datetime import time
from telegram.ext import Application

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


