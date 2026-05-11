import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")

# Telethon configuration
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

# Owner ID
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Multiple admin IDs (comma-separated in .env, includes owner automatically)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
# Always include owner in admin list
if OWNER_ID and OWNER_ID not in ADMIN_IDS:
    ADMIN_IDS.append(OWNER_ID)

# Logger group
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0"))

# Database configuration - ek hi URI
MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "sticker_kang_bot")

# Sticker pack settings
MAX_PACK_NAME_LENGTH = 64
MAX_STICKERS_PER_PACK = 120
MAX_VIDEO_SIZE_MB = 4

# GBan system - in-memory cache
BANNED_USERS = set()


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
