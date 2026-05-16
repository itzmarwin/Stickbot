import logging
from pymongo import AsyncMongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_client: Optional[AsyncMongoClient] = None
_db = None

DEFAULT_AUTO_DELETE_SECONDS = 600
DEFAULT_WARN_LIMIT = 3
DEFAULT_WARN_MODE = "ban"


def init_managementdb(client: AsyncMongoClient, db):
    global _client, _db
    _client = client
    _db = db


async def create_indexes():
    await _db.welcome_settings.create_index("chat_id", unique=True)
    await _db.filters.create_index(
        [("chat_id", 1), ("keyword", 1)],
        unique=True
    )
    await _db.filters.create_index("chat_id")
    await _db.warns.create_index(
        [("chat_id", 1), ("user_id", 1)],
        unique=True
    )
    await _db.warn_settings.create_index("chat_id", unique=True)
    logger.info("✅ managementdb indexes created")


async def get_welcome_settings(chat_id: int) -> Optional[Dict[str, Any]]:
    try:
        return await _db.welcome_settings.find_one({"chat_id": chat_id})
    except Exception as e:
        logger.error(f"Error getting welcome settings {chat_id}: {e}")
        return None


async def create_default_welcome_settings(chat_id: int) -> bool:
    now = datetime.utcnow()
    default_settings = {
        "chat_id": chat_id,
        "welcome": {
            "enabled": True,
            "custom_set": False,
            "media_type": None,
            "media_id": None,
            "text": None,
            "buttons": [],
            "auto_delete": {"enabled": False, "delete_after": None}
        },
        "goodbye": {
            "enabled": False,
            "custom_set": False,
            "media_type": None,
            "media_id": None,
            "text": None,
            "buttons": [],
            "auto_delete": {"enabled": False, "delete_after": None}
        },
        "created_at": now,
        "updated_at": now
    }
    try:
        await _db.welcome_settings.insert_one(default_settings)
    except DuplicateKeyError:
        pass
    return True


async def update_welcome_status(chat_id: int, enabled: bool) -> bool:
    try:
        await _db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {"welcome.enabled": enabled, "updated_at": datetime.utcnow()}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error updating welcome status {chat_id}: {e}")
        return False


async def update_goodbye_status(chat_id: int, enabled: bool) -> bool:
    try:
        await _db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {"goodbye.enabled": enabled, "updated_at": datetime.utcnow()}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error updating goodbye status {chat_id}: {e}")
        return False


async def set_custom_welcome(
    chat_id: int,
    media_type: Optional[str],
    media_id: Optional[str],
    text: str,
    buttons: Optional[List[Dict]] = None
) -> bool:
    if buttons is None:
        buttons = []
    try:
        await _db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "welcome.custom_set": True,
                    "welcome.media_type": media_type,
                    "welcome.media_id": media_id,
                    "welcome.text": text,
                    "welcome.buttons": buttons,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error setting custom welcome {chat_id}: {e}")
        return False


async def set_custom_goodbye(
    chat_id: int,
    media_type: Optional[str],
    media_id: Optional[str],
    text: str,
    buttons: Optional[List[Dict]] = None
) -> bool:
    if buttons is None:
        buttons = []
    try:
        await _db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "goodbye.custom_set": True,
                    "goodbye.media_type": media_type,
                    "goodbye.media_id": media_id,
                    "goodbye.text": text,
                    "goodbye.buttons": buttons,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error setting custom goodbye {chat_id}: {e}")
        return False


async def delete_custom_welcome(chat_id: int) -> bool:
    try:
        result = await _db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "welcome.enabled": False,
                    "welcome.custom_set": False,
                    "welcome.media_type": None,
                    "welcome.media_id": None,
                    "welcome.text": None,
                    "welcome.buttons": [],
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error deleting custom welcome {chat_id}: {e}")
        return False


async def delete_custom_goodbye(chat_id: int) -> bool:
    try:
        result = await _db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "goodbye.enabled": False,
                    "goodbye.custom_set": False,
                    "goodbye.media_type": None,
                    "goodbye.media_id": None,
                    "goodbye.text": None,
                    "goodbye.buttons": [],
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error deleting custom goodbye {chat_id}: {e}")
        return False


async def update_welcome_auto_delete(
    chat_id: int,
    enabled: bool,
    delete_after: Optional[int] = None
) -> bool:
    if enabled and delete_after is None:
        delete_after = DEFAULT_AUTO_DELETE_SECONDS
    try:
        await _db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "welcome.auto_delete.enabled": enabled,
                    "welcome.auto_delete.delete_after": delete_after if enabled else None,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error updating welcome auto delete {chat_id}: {e}")
        return False


async def update_goodbye_auto_delete(
    chat_id: int,
    enabled: bool,
    delete_after: Optional[int] = None
) -> bool:
    if enabled and delete_after is None:
        delete_after = DEFAULT_AUTO_DELETE_SECONDS
    try:
        await _db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "goodbye.auto_delete.enabled": enabled,
                    "goodbye.auto_delete.delete_after": delete_after if enabled else None,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error updating goodbye auto delete {chat_id}: {e}")
        return False


async def add_filter(
    chat_id: int,
    keyword: str,
    media_type: Optional[str],
    media_id: Optional[str],
    text: Optional[str]
) -> bool:
    try:
        await _db.filters.update_one(
            {"chat_id": chat_id, "keyword": keyword.lower()},
            {
                "$set": {
                    "chat_id": chat_id,
                    "keyword": keyword.lower(),
                    "media_type": media_type,
                    "media_id": media_id,
                    "text": text,
                    "updated_at": datetime.utcnow()
                },
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error adding filter {chat_id} {keyword}: {e}")
        return False


async def get_all_filters(chat_id: int) -> List[Dict[str, Any]]:
    try:
        cursor = _db.filters.find(
            {"chat_id": chat_id},
            {"keyword": 1, "media_type": 1, "media_id": 1, "text": 1}
        ).sort("keyword", 1)
        return [doc async for doc in cursor]
    except Exception as e:
        logger.error(f"Error getting filters {chat_id}: {e}")
        return []


async def delete_filter(chat_id: int, keyword: str) -> bool:
    try:
        result = await _db.filters.delete_one(
            {"chat_id": chat_id, "keyword": keyword.lower()}
        )
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting filter {chat_id} {keyword}: {e}")
        return False


async def delete_all_filters(chat_id: int) -> int:
    try:
        result = await _db.filters.delete_many({"chat_id": chat_id})
        return result.deleted_count
    except Exception as e:
        logger.error(f"Error deleting all filters {chat_id}: {e}")
        return 0


async def get_user_warns(chat_id: int, user_id: int) -> Dict[str, Any]:
    try:
        doc = await _db.warns.find_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"warns": 1, "reasons": 1}
        )
        if doc:
            return {"warns": doc.get("warns", 0), "reasons": doc.get("reasons", [])}
        return {"warns": 0, "reasons": []}
    except Exception as e:
        logger.error(f"Error getting user warns {chat_id} {user_id}: {e}")
        return {"warns": 0, "reasons": []}


async def add_warn(
    chat_id: int,
    user_id: int,
    reason: Optional[str] = None
) -> Dict[str, Any]:
    try:
        update = {
            "$inc": {"warns": 1},
            "$set": {
                "chat_id": chat_id,
                "user_id": user_id,
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {"created_at": datetime.utcnow()}
        }

        if reason:
            update["$push"] = {"reasons": reason}

        result = await _db.warns.find_one_and_update(
            {"chat_id": chat_id, "user_id": user_id},
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
            projection={"warns": 1, "reasons": 1}
        )

        return {
            "warns": result.get("warns", 1) if result else 1,
            "reasons": result.get("reasons", []) if result else []
        }
    except Exception as e:
        logger.error(f"Error adding warn {chat_id} {user_id}: {e}")
        return {"warns": 1, "reasons": []}


async def remove_one_warn(chat_id: int, user_id: int) -> Dict[str, Any]:
    try:
        doc = await _db.warns.find_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"warns": 1, "reasons": 1}
        )

        if not doc or doc.get("warns", 0) <= 0:
            return {"warns": 0, "reasons": []}

        new_warns = doc["warns"] - 1
        reasons = doc.get("reasons", [])
        if reasons:
            reasons = reasons[:-1]

        await _db.warns.update_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"$set": {"warns": new_warns, "reasons": reasons, "updated_at": datetime.utcnow()}}
        )

        return {"warns": new_warns, "reasons": reasons}
    except Exception as e:
        logger.error(f"Error removing warn {chat_id} {user_id}: {e}")
        return {"warns": 0, "reasons": []}


async def reset_user_warns(chat_id: int, user_id: int) -> bool:
    try:
        result = await _db.warns.delete_one({"chat_id": chat_id, "user_id": user_id})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error resetting warns {chat_id} {user_id}: {e}")
        return False


async def get_warn_settings(chat_id: int) -> Dict[str, Any]:
    try:
        doc = await _db.warn_settings.find_one(
            {"chat_id": chat_id},
            {"warn_limit": 1, "warn_mode": 1}
        )
        if doc:
            return {
                "warn_limit": doc.get("warn_limit", DEFAULT_WARN_LIMIT),
                "warn_mode": doc.get("warn_mode", DEFAULT_WARN_MODE)
            }
        return {"warn_limit": DEFAULT_WARN_LIMIT, "warn_mode": DEFAULT_WARN_MODE}
    except Exception as e:
        logger.error(f"Error getting warn settings {chat_id}: {e}")
        return {"warn_limit": DEFAULT_WARN_LIMIT, "warn_mode": DEFAULT_WARN_MODE}


async def set_warn_limit(chat_id: int, limit: int) -> bool:
    try:
        await _db.warn_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {"warn_limit": limit, "updated_at": datetime.utcnow()},
                "$setOnInsert": {"created_at": datetime.utcnow(), "warn_mode": DEFAULT_WARN_MODE}
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error setting warn limit {chat_id}: {e}")
        return False


async def set_warn_mode(chat_id: int, mode: str) -> bool:
    try:
        await _db.warn_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {"warn_mode": mode, "updated_at": datetime.utcnow()},
                "$setOnInsert": {"created_at": datetime.utcnow(), "warn_limit": DEFAULT_WARN_LIMIT}
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error setting warn mode {chat_id}: {e}")
        return False
