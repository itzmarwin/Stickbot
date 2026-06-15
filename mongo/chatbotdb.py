from typing import Optional
from pymongo import AsyncMongoClient

_client: Optional[AsyncMongoClient] = None
_db = None

# In-memory cache for chatbot status per group
_chatbot_status_cache: dict[int, bool] = {}


def init_chatbotdb(client: AsyncMongoClient, db):
    global _client, _db
    _client = client
    _db = db


async def create_indexes():
    if _db is None:
        return
    await _db.chatbot_settings.create_index("chat_id", unique=True)


async def get_chatbot_status(chat_id: int) -> bool:
    """Check if chatbot is enabled for a group. Default: False."""
    if chat_id in _chatbot_status_cache:
        return _chatbot_status_cache[chat_id]
    try:
        doc = await _db.chatbot_settings.find_one({"chat_id": chat_id}, {"enabled": 1})
        status = doc.get("enabled", False) if doc else False
        _chatbot_status_cache[chat_id] = status
        return status
    except Exception:
        return False


async def set_chatbot_status(chat_id: int, enabled: bool) -> bool:
    """Enable or disable chatbot for a group."""
    try:
        await _db.chatbot_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "enabled": enabled}},
            upsert=True
        )
        _chatbot_status_cache[chat_id] = enabled
        return True
    except Exception:
        return False
