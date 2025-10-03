import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0"))  # Logger group ID

# Database configuration
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "sticker_kang_bot")

# Sticker pack settings
MAX_PACK_NAME_LENGTH = 64
MAX_STICKERS_PER_PACK = 120
MAX_VIDEO_SIZE_MB = 4

# config.py
OWNER_IDS = [123456789, 987654321, 555555555]

def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS
