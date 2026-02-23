import time
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, DuplicateKeyError, OperationFailure
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import MONGO_URI_MANAGEMENT, DATABASE_NAME_MANAGEMENT

DB_MAX_POOL_SIZE = 20
DB_MIN_POOL_SIZE = 2
DB_MAX_IDLE_TIME_MS = 45000
DB_SERVER_SELECTION_TIMEOUT_MS = 5000
DB_CONNECT_TIMEOUT_MS = 10000
DB_SOCKET_TIMEOUT_MS = 30000
DB_WAIT_QUEUE_TIMEOUT_MS = 10000

CURRENT_SCHEMA_VERSION = 1
SCHEMA_COLLECTION = "schema_version"

DEFAULT_AUTO_DELETE_SECONDS = 600
DEFAULT_WARN_LIMIT = 3
DEFAULT_WARN_MODE = "ban"

management_client: Optional[AsyncIOMotorClient] = None
management_db = None


async def init_management_db():
    global management_client, management_db

    management_client = AsyncIOMotorClient(
        MONGO_URI_MANAGEMENT,
        serverSelectionTimeoutMS=DB_SERVER_SELECTION_TIMEOUT_MS,
        connectTimeoutMS=DB_CONNECT_TIMEOUT_MS,
        socketTimeoutMS=DB_SOCKET_TIMEOUT_MS,
        maxPoolSize=DB_MAX_POOL_SIZE,
        minPoolSize=DB_MIN_POOL_SIZE,
        waitQueueTimeoutMS=DB_WAIT_QUEUE_TIMEOUT_MS,
        maxIdleTimeMS=DB_MAX_IDLE_TIME_MS,
        retryWrites=True,
        retryReads=True
    )

    await management_client.admin.command('ping')
    management_db = management_client[DATABASE_NAME_MANAGEMENT]

    await _check_and_migrate_schema()
    await _create_indexes()

    return management_db


async def _create_indexes():
    # Welcome indexes
    await management_db.welcome_settings.create_index("chat_id", unique=True, name="idx_chat_id")
    await management_db.welcome_settings.create_index([("chat_id", 1), ("welcome.enabled", 1)], name="idx_chat_welcome")
    await management_db.welcome_settings.create_index([("updated_at", 1)], name="idx_updated_at")

    # Filters indexes
    await management_db.filters.create_index(
        [("chat_id", 1), ("keyword", 1)],
        unique=True,
        name="idx_filter_chat_keyword"
    )
    await management_db.filters.create_index("chat_id", name="idx_filter_chat_id")

    # Warns indexes — chat_id+user_id compound unique
    await management_db.warns.create_index(
        [("chat_id", 1), ("user_id", 1)],
        unique=True,
        name="idx_warns_chat_user"
    )

    # Warn settings index — ek document per group
    await management_db.warn_settings.create_index(
        "chat_id",
        unique=True,
        name="idx_warn_settings_chat"
    )


async def _get_current_schema_version() -> int:
    version_doc = await management_db[SCHEMA_COLLECTION].find_one({"_id": "current"})
    if version_doc:
        return version_doc.get("version", 0)
    return 0


async def _set_schema_version(version: int) -> bool:
    await management_db[SCHEMA_COLLECTION].update_one(
        {"_id": "current"},
        {"$set": {"version": version, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    return True


async def _check_and_migrate_schema():
    current_version = await _get_current_schema_version()
    if current_version == CURRENT_SCHEMA_VERSION:
        return
    for version in range(current_version + 1, CURRENT_SCHEMA_VERSION + 1):
        if version == 1:
            await _migrate_to_v1()
        await _set_schema_version(version)


async def _migrate_to_v1():
    cursor = management_db.welcome_settings.find({
        "$or": [
            {"welcome.auto_delete": {"$exists": False}},
            {"goodbye.auto_delete": {"$exists": False}}
        ]
    })

    async for doc in cursor:
        chat_id = doc["chat_id"]
        update_fields = {}

        if "auto_delete" not in doc.get("welcome", {}):
            update_fields["welcome.auto_delete"] = {"enabled": False, "delete_after": None}
        if "auto_delete" not in doc.get("goodbye", {}):
            update_fields["goodbye.auto_delete"] = {"enabled": False, "delete_after": None}
        if "created_at" not in doc:
            update_fields["created_at"] = datetime.utcnow()
        if "updated_at" not in doc:
            update_fields["updated_at"] = datetime.utcnow()

        if update_fields:
            await management_db.welcome_settings.update_one({"chat_id": chat_id}, {"$set": update_fields})


async def close_management_db():
    global management_client
    if management_client:
        management_client.close()


def get_management_db():
    return management_db


# ============================================================
# WELCOME / GOODBYE FUNCTIONS
# ============================================================

async def get_welcome_settings(chat_id: int) -> Optional[Dict[str, Any]]:
    return await management_db.welcome_settings.find_one({"chat_id": chat_id})


async def create_default_welcome_settings(chat_id: int) -> bool:
    now = datetime.utcnow()
    default_settings = {
        "chat_id": chat_id,
        "welcome": {
            "enabled": False,
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
        await management_db.welcome_settings.insert_one(default_settings)
    except DuplicateKeyError:
        pass
    return True


async def update_welcome_status(chat_id: int, enabled: bool) -> bool:
    await management_db.welcome_settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"welcome.enabled": enabled, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    return True


async def update_goodbye_status(chat_id: int, enabled: bool) -> bool:
    await management_db.welcome_settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"goodbye.enabled": enabled, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    return True


async def set_custom_welcome(chat_id: int, media_type: Optional[str], media_id: Optional[str], text: str, buttons: Optional[List[Dict]] = None) -> bool:
    if buttons is None:
        buttons = []
    await management_db.welcome_settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"welcome.custom_set": True, "welcome.media_type": media_type, "welcome.media_id": media_id, "welcome.text": text, "welcome.buttons": buttons, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    return True


async def set_custom_goodbye(chat_id: int, media_type: Optional[str], media_id: Optional[str], text: str, buttons: Optional[List[Dict]] = None) -> bool:
    if buttons is None:
        buttons = []
    await management_db.welcome_settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"goodbye.custom_set": True, "goodbye.media_type": media_type, "goodbye.media_id": media_id, "goodbye.text": text, "goodbye.buttons": buttons, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    return True


async def delete_custom_welcome(chat_id: int) -> bool:
    result = await management_db.welcome_settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"welcome.enabled": False, "welcome.custom_set": False, "welcome.media_type": None, "welcome.media_id": None, "welcome.text": None, "welcome.buttons": [], "updated_at": datetime.utcnow()}}
    )
    return result.modified_count > 0


async def delete_custom_goodbye(chat_id: int) -> bool:
    result = await management_db.welcome_settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"goodbye.enabled": False, "goodbye.custom_set": False, "goodbye.media_type": None, "goodbye.media_id": None, "goodbye.text": None, "goodbye.buttons": [], "updated_at": datetime.utcnow()}}
    )
    return result.modified_count > 0


async def update_welcome_auto_delete(chat_id: int, enabled: bool, delete_after: Optional[int] = None) -> bool:
    if enabled and delete_after is None:
        delete_after = DEFAULT_AUTO_DELETE_SECONDS
    await management_db.welcome_settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"welcome.auto_delete.enabled": enabled, "welcome.auto_delete.delete_after": delete_after if enabled else None, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    return True


async def update_goodbye_auto_delete(chat_id: int, enabled: bool, delete_after: Optional[int] = None) -> bool:
    if enabled and delete_after is None:
        delete_after = DEFAULT_AUTO_DELETE_SECONDS
    await management_db.welcome_settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"goodbye.auto_delete.enabled": enabled, "goodbye.auto_delete.delete_after": delete_after if enabled else None, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    return True


async def check_management_db_health() -> Dict[str, Any]:
    health = {"management_db": {"status": "unknown", "latency_ms": 0}}
    try:
        start = time.time()
        await management_client.admin.command('ping')
        latency = (time.time() - start) * 1000
        health["management_db"] = {"status": "healthy", "latency_ms": round(latency, 2), "schema_version": CURRENT_SCHEMA_VERSION}
    except ServerSelectionTimeoutError as e:
        health["management_db"] = {"status": "timeout", "error": str(e)}
    except ConnectionFailure as e:
        health["management_db"] = {"status": "connection_failed", "error": str(e)}
    except Exception as e:
        health["management_db"] = {"status": "unhealthy", "error": str(e)}
    return health


async def get_enabled_chats(message_type: str) -> List[int]:
    field = f"{message_type}.enabled"
    cursor = management_db.welcome_settings.find({field: True}, {"chat_id": 1})
    return [doc["chat_id"] async for doc in cursor]


# ============================================================
# FILTERS FUNCTIONS
# ============================================================

async def add_filter(chat_id: int, keyword: str, media_type: Optional[str], media_id: Optional[str], text: Optional[str]) -> bool:
    try:
        await management_db.filters.update_one(
            {"chat_id": chat_id, "keyword": keyword.lower()},
            {
                "$set": {"chat_id": chat_id, "keyword": keyword.lower(), "media_type": media_type, "media_id": media_id, "text": text, "updated_at": datetime.utcnow()},
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
        return True
    except Exception:
        return False


async def get_filter(chat_id: int, keyword: str) -> Optional[Dict[str, Any]]:
    return await management_db.filters.find_one({"chat_id": chat_id, "keyword": keyword.lower()})


async def get_all_filters(chat_id: int) -> List[Dict[str, Any]]:
    cursor = management_db.filters.find(
        {"chat_id": chat_id},
        {"keyword": 1, "media_type": 1, "media_id": 1, "text": 1}
    ).sort("keyword", 1)
    return [doc async for doc in cursor]


async def delete_filter(chat_id: int, keyword: str) -> bool:
    result = await management_db.filters.delete_one({"chat_id": chat_id, "keyword": keyword.lower()})
    return result.deleted_count > 0


async def delete_all_filters(chat_id: int) -> int:
    result = await management_db.filters.delete_many({"chat_id": chat_id})
    return result.deleted_count


# ============================================================
# WARNS FUNCTIONS
# — 2 collections: warns (user data) + warn_settings (group config)
# — RAM cache warn_settings mein — DB call sirf update pe hogi
# ============================================================

async def get_user_warns(chat_id: int, user_id: int) -> Dict[str, Any]:
    """User ki warns lo — sirf zaruri fields."""
    doc = await management_db.warns.find_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"warns": 1, "reasons": 1}
    )
    if doc:
        return {"warns": doc.get("warns", 0), "reasons": doc.get("reasons", [])}
    return {"warns": 0, "reasons": []}


async def add_warn(chat_id: int, user_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
    """
    Warn add karo — upsert se ek hi DB call mein sab ho jaata hai.
    Return: updated warns count aur reasons.
    """
    reason_to_add = reason if reason else None

    update = {
        "$inc": {"warns": 1},
        "$set": {"chat_id": chat_id, "user_id": user_id, "updated_at": datetime.utcnow()},
        "$setOnInsert": {"created_at": datetime.utcnow()}
    }

    if reason_to_add:
        update["$push"] = {"reasons": reason_to_add}

    result = await management_db.warns.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        update,
        upsert=True,
        return_document=True,
        projection={"warns": 1, "reasons": 1}
    )

    return {
        "warns": result.get("warns", 1) if result else 1,
        "reasons": result.get("reasons", []) if result else []
    }


async def remove_one_warn(chat_id: int, user_id: int) -> Dict[str, Any]:
    """Ek warn hatao — 0 se neeche nahi jaayega."""
    doc = await management_db.warns.find_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"warns": 1, "reasons": 1}
    )

    if not doc or doc.get("warns", 0) <= 0:
        return {"warns": 0, "reasons": []}

    # Last reason hatao
    new_warns = doc["warns"] - 1
    reasons = doc.get("reasons", [])
    if reasons:
        reasons = reasons[:-1]

    await management_db.warns.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"warns": new_warns, "reasons": reasons, "updated_at": datetime.utcnow()}}
    )

    return {"warns": new_warns, "reasons": reasons}


async def reset_user_warns(chat_id: int, user_id: int) -> bool:
    """User ki saari warns reset karo — document delete karo (space bachao)."""
    result = await management_db.warns.delete_one({"chat_id": chat_id, "user_id": user_id})
    return result.deleted_count > 0


async def get_warn_settings(chat_id: int) -> Dict[str, Any]:
    """Group ki warn settings lo."""
    doc = await management_db.warn_settings.find_one(
        {"chat_id": chat_id},
        {"warn_limit": 1, "warn_mode": 1}
    )
    if doc:
        return {
            "warn_limit": doc.get("warn_limit", DEFAULT_WARN_LIMIT),
            "warn_mode": doc.get("warn_mode", DEFAULT_WARN_MODE)
        }
    return {"warn_limit": DEFAULT_WARN_LIMIT, "warn_mode": DEFAULT_WARN_MODE}


async def set_warn_limit(chat_id: int, limit: int) -> bool:
    """Group ka warn limit set karo."""
    await management_db.warn_settings.update_one(
        {"chat_id": chat_id},
        {
            "$set": {"warn_limit": limit, "updated_at": datetime.utcnow()},
            "$setOnInsert": {"created_at": datetime.utcnow(), "warn_mode": DEFAULT_WARN_MODE}
        },
        upsert=True
    )
    return True


async def set_warn_mode(chat_id: int, mode: str) -> bool:
    """Group ka warn mode set karo — ban/mute/kick."""
    await management_db.warn_settings.update_one(
        {"chat_id": chat_id},
        {
            "$set": {"warn_mode": mode, "updated_at": datetime.utcnow()},
            "$setOnInsert": {"created_at": datetime.utcnow(), "warn_limit": DEFAULT_WARN_LIMIT}
        },
        upsert=True
    )
    return True
