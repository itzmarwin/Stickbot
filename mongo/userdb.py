import logging
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db = None

_lang_cache: Dict[int, str] = {}


def init_userdb(client: AsyncIOMotorClient, db):
    global _client, _db
    _client = client
    _db = db


async def create_indexes():
    await _db.users.create_index("user_id", unique=True)
    await _db.gbans.create_index("user_id", unique=True)
    await _db.served_chats.create_index("chat_id", unique=True)


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        return await _db.users.find_one({"user_id": user_id})
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None


async def create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    language: str = "en"
) -> bool:
    try:
        await _db.users.update_one(
            {"user_id": user_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "username": username,
                    "first_name": first_name,
                    "created_at": datetime.utcnow(),
                    "has_started": True,
                    "language": language
                }
            },
            upsert=True
        )
        _lang_cache[user_id] = language
        return True
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")
        return False


async def get_all_users() -> List[Dict[str, Any]]:
    try:
        cursor = _db.users.find({}, {"user_id": 1, "username": 1, "first_name": 1})
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []


async def get_total_users_count() -> int:
    try:
        return await _db.users.count_documents({})
    except Exception as e:
        logger.error(f"Error getting users count: {e}")
        return 0


async def get_user_language(user_id: int) -> str:
    if user_id in _lang_cache:
        return _lang_cache[user_id]
    try:
        user = await _db.users.find_one({"user_id": user_id}, {"language": 1})
        lang = user["language"] if user and "language" in user else "en"
        _lang_cache[user_id] = lang
        return lang
    except Exception as e:
        logger.error(f"Error getting user language {user_id}: {e}")
        return "en"


async def set_user_language(user_id: int, language: str) -> bool:
    try:
        if language not in ["en", "rus", "bur"]:
            language = "en"
        await _db.users.update_one(
            {"user_id": user_id},
            {"$set": {"language": language}},
            upsert=True
        )
        _lang_cache[user_id] = language
        return True
    except Exception as e:
        logger.error(f"Error setting language for user {user_id}: {e}")
        return False


async def add_served_chat(chat_id: int) -> bool:
    try:
        await _db.served_chats.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "added_at": datetime.utcnow()}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error adding served chat {chat_id}: {e}")
        return False


async def remove_served_chat(chat_id: int) -> bool:
    try:
        await _db.served_chats.delete_one({"chat_id": chat_id})
        return True
    except Exception as e:
        logger.error(f"Error removing served chat {chat_id}: {e}")
        return False


async def get_served_chats() -> List[Dict[str, Any]]:
    try:
        cursor = _db.served_chats.find({})
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error(f"Error getting served chats: {e}")
        return []


async def get_served_chats_count() -> int:
    try:
        return await _db.served_chats.count_documents({})
    except Exception as e:
        logger.error(f"Error getting served chats count: {e}")
        return 0


async def add_banned_user(user_id: int) -> bool:
    try:
        await _db.gbans.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "banned_at": datetime.utcnow()}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error adding banned user {user_id}: {e}")
        return False


async def remove_banned_user(user_id: int) -> bool:
    try:
        await _db.gbans.delete_one({"user_id": user_id})
        return True
    except Exception as e:
        logger.error(f"Error removing banned user {user_id}: {e}")
        return False


async def get_banned_users() -> List[int]:
    try:
        cursor = _db.gbans.find({})
        banned_users = await cursor.to_list(length=None)
        return [user["user_id"] for user in banned_users]
    except Exception as e:
        logger.error(f"Error getting banned users: {e}")
        return []


async def get_banned_count() -> int:
    try:
        return await _db.gbans.count_documents({})
    except Exception as e:
        logger.error(f"Error getting banned count: {e}")
        return 0


async def is_banned_user(user_id: int) -> bool:
    try:
        ban_data = await _db.gbans.find_one({"user_id": user_id})
        return ban_data is not None
    except Exception as e:
        logger.error(f"Error checking banned user {user_id}: {e}")
        return False
