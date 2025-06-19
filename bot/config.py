import os
from dotenv import load_dotenv

load_dotenv()

TASKS_FILE = 'tasks.json'
CATEGORIES_FILE = 'categories.json'
DB_FILE = 'tasks.db'
BOT_TOKEN = os.getenv('TOKEN', 'PLACEHOLDER_TOKEN')
OWNER_CHAT_ID = int(os.getenv('OWNER_CHAT_ID', '123456789'))
