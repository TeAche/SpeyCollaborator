import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base directory of the project so that files work regardless of the
# current working directory.
BASE_DIR = Path(__file__).resolve().parent.parent

CATEGORIES_FILE = str(BASE_DIR / 'categories.json')
TASKS_TEMPLATE_FILE = str(BASE_DIR / 'tasks_template.json')
DB_FILE = str(BASE_DIR / 'tasks.db')
BOT_TOKEN = os.getenv('TOKEN', 'PLACEHOLDER_TOKEN')
DATABASE_URL = os.getenv("DATABASE_URL")
OWNER_CHAT_ID = int(os.getenv('OWNER_CHAT_ID', '0'))
