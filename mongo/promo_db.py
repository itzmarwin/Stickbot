import logging
from typing import Optional, Dict
from pymongo import AsyncMongoClient

logger = logging.getLogger(__name__)

_client: Optional[AsyncMongoClient] = None
_db = None

# ─── In-Memory Cache ─────────────────────────────────────────────────
# {chat_id: enabled} — whether user-link/username deletion is ON for this chat.
_promo_cache: Dict[int, bool] = {}


def init_promo_db(client: AsyncMongoClient, db):
    global _client, _db
    _client = client
    _db = db


async def create_indexes():
    if _db is None:
        return
    await _db.promo_settings.create_index("chat_id", unique=True)
    logger.info("✅ promo (user anti-link) indexes created")


# ─── Per-Chat Settings ───────────────────────────────────────────────

async def get_promo_status(chat_id: int) -> bool:
    """
    Whether non-admin users' links/username-mentions get deleted in this chat.
    Cache check first — DB only on miss.
    """
    if chat_id in _promo_cache:
        return _promo_cache[chat_id]
    if _db is None:
        return False
    try:
        doc = await _db.promo_settings.find_one(
            {"chat_id": chat_id}, {"enabled": 1}
        )
        status = doc.get("enabled", False) if doc else False
        _promo_cache[chat_id] = status
        return status
    except Exception as e:
        logger.error(f"Error getting promo status {chat_id}: {e}")
        return False


async def set_promo_status(chat_id: int, enabled: bool) -> bool:
    if _db is None:
        return False
    try:
        await _db.promo_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "enabled": enabled}},
            upsert=True
        )
        _promo_cache[chat_id] = enabled
        return True
    except Exception as e:
        logger.error(f"Error setting promo status {chat_id}: {e}")
        return False
