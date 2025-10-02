import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Database configuration
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "sticker_kang_bot")

# Sticker pack settings
MAX_PACK_NAME_LENGTH = 64
MAX_STICKERS_PER_PACK = 120
MAX_VIDEO_SIZE_MB = 4
