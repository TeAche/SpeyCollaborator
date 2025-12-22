import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID", "0") or 0)
