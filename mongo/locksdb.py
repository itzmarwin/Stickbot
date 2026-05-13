import logging
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db = None

# ============================================================
# IN-MEMORY CACHE
# Key   : chat_id (int)
# Value : dict of active locks  → {"links": True, "bot": True}
#         empty dict {}         → checked, no active DB locks
#         None (key missing)    → never checked (cache miss)
# ============================================================
_locks_cache: Dict[int, Dict[str, bool]] = {}

# ============================================================
# LOCK TYPE SETS
# ============================================================

# Stored in MongoDB — bot manually detects & deletes messages
DB_LOCK_TYPES = frozenset({
    "links",
    "allforward",
    "userforward",
    "channelforward",
    "anonchannel",
    "bot",
    "audio",
    "voice",
    "video",
    "gif",
    "document",
    "album",
    "contact",
    "emoji",
    "emojicustom",
    "command",
    "email",
    "phone",
    "poll",
    "checklist",
    "forwardstory",
    "externalreply",
    "comment",
    "inline",
})

# Handled by Telegram's set_chat_permissions() — NOT stored in DB
NATIVE_LOCK_TYPES = frozenset({
    "msg",
    "media",
    "stickers",
    "animations",
    "games",
    "webprev",
    "polls",
    "info",
    "invite",
    "pin",
})

ALL_LOCK_TYPES = DB_LOCK_TYPES | NATIVE_LOCK_TYPES


# ============================================================
# INIT
# ============================================================

def init_locksdb(client: AsyncIOMotorClient, db):
    """
    Initialize locksdb with shared MongoDB client and db.
    Call from main.py after the main DB connection is established.
    """
    global _client, _db
    _client = client
    _db = db


async def create_indexes():
    """Create indexes for the locks collection."""
    await _db.locks.create_index("chat_id", unique=True)
    logger.info("✅ locksdb indexes created")


# ============================================================
# CACHE HELPERS (internal)
# ============================================================

def _cache_get(chat_id: int) -> Optional[Dict[str, bool]]:
    """
    Returns:
        None  → cache miss  (DB not yet queried for this chat)
        {}    → cache hit, no active DB locks
        {...} → cache hit, these locks are active
    """
    return _locks_cache.get(chat_id)


def _cache_set(chat_id: int, locks: Dict[str, bool]):
    _locks_cache[chat_id] = locks


def _cache_remove_chat(chat_id: int):
    _locks_cache.pop(chat_id, None)


def _cache_update_one(chat_id: int, lock_type: str, enabled: bool):
    """Add or remove a single lock from the cache without touching DB."""
    if chat_id not in _locks_cache:
        _locks_cache[chat_id] = {}
    if enabled:
        _locks_cache[chat_id][lock_type] = True
    else:
        _locks_cache[chat_id].pop(lock_type, None)


# ============================================================
# READ
# ============================================================

async def get_chat_locks(chat_id: int) -> Dict[str, bool]:
    """
    Return all active DB locks for a chat.
    Cache-first: DB is queried only on cache miss.

    Returns:
        {"links": True, "bot": True, ...}   → active locks
        {}                                  → no active locks
    """
    cached = _cache_get(chat_id)
    if cached is not None:
        return cached

    try:
        doc = await _db.locks.find_one({"chat_id": chat_id}, {"locks": 1})
        if doc and doc.get("locks"):
            locks = {k: True for k, v in doc["locks"].items() if v}
        else:
            locks = {}

        _cache_set(chat_id, locks)
        return locks

    except Exception as e:
        logger.error(f"Error getting locks for chat {chat_id}: {e}")
        return {}


async def is_lock_enabled(chat_id: int, lock_type: str) -> bool:
    """Check if a specific DB lock is enabled. Cache-first."""
    if lock_type not in DB_LOCK_TYPES:
        return False
    locks = await get_chat_locks(chat_id)
    return locks.get(lock_type, False)


# ============================================================
# ENABLE LOCKS
# ============================================================

async def enable_lock(chat_id: int, lock_type: str) -> bool:
    """
    Enable a single DB lock.
    Returns True on success, False on failure or invalid type.
    """
    if lock_type not in DB_LOCK_TYPES:
        return False
    try:
        await _db.locks.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, f"locks.{lock_type}": True}},
            upsert=True
        )
        _cache_update_one(chat_id, lock_type, True)
        return True
    except Exception as e:
        logger.error(f"Error enabling lock {lock_type} for chat {chat_id}: {e}")
        return False


async def enable_multiple_locks(chat_id: int, lock_types: List[str]) -> Dict[str, bool]:
    """
    Enable multiple DB locks in a single DB write.

    Returns:
        {lock_type: True/False}  — True means successfully enabled
    """
    db_locks = [lt for lt in lock_types if lt in DB_LOCK_TYPES]
    results: Dict[str, bool] = {}

    if not db_locks:
        return results

    try:
        set_fields = {f"locks.{lt}": True for lt in db_locks}
        set_fields["chat_id"] = chat_id

        await _db.locks.update_one(
            {"chat_id": chat_id},
            {"$set": set_fields},
            upsert=True
        )

        for lt in db_locks:
            _cache_update_one(chat_id, lt, True)
            results[lt] = True

    except Exception as e:
        logger.error(f"Error enabling multiple locks for chat {chat_id}: {e}")
        for lt in db_locks:
            results[lt] = False

    return results


async def enable_all_db_locks(chat_id: int) -> bool:
    """
    Enable every DB lock type for a chat in one write.
    Returns True on success.
    """
    try:
        set_fields = {f"locks.{lt}": True for lt in DB_LOCK_TYPES}
        set_fields["chat_id"] = chat_id

        await _db.locks.update_one(
            {"chat_id": chat_id},
            {"$set": set_fields},
            upsert=True
        )

        _cache_set(chat_id, {lt: True for lt in DB_LOCK_TYPES})
        return True

    except Exception as e:
        logger.error(f"Error enabling all locks for chat {chat_id}: {e}")
        return False


# ============================================================
# DISABLE LOCKS
# ============================================================

async def _cleanup_empty_doc(chat_id: int):
    """
    After an unset operation, delete the document if no locks remain.
    Updates cache accordingly.
    """
    doc = await _db.locks.find_one({"chat_id": chat_id}, {"locks": 1})
    if not doc:
        _cache_set(chat_id, {})
        return

    remaining = {k: True for k, v in doc.get("locks", {}).items() if v}
    if not remaining:
        await _db.locks.delete_one({"chat_id": chat_id})
        _cache_set(chat_id, {})
    else:
        _cache_set(chat_id, remaining)


async def disable_lock(chat_id: int, lock_type: str) -> bool:
    """
    Disable a single DB lock.
    Deletes the document entirely if no locks remain.
    Returns True on success.
    """
    if lock_type not in DB_LOCK_TYPES:
        return False
    try:
        await _db.locks.update_one(
            {"chat_id": chat_id},
            {"$unset": {f"locks.{lock_type}": ""}}
        )
        await _cleanup_empty_doc(chat_id)
        return True
    except Exception as e:
        logger.error(f"Error disabling lock {lock_type} for chat {chat_id}: {e}")
        return False


async def disable_multiple_locks(chat_id: int, lock_types: List[str]) -> Dict[str, bool]:
    """
    Disable multiple DB locks in a single DB write.
    Deletes the document if no locks remain.

    Returns:
        {lock_type: True/False}
    """
    db_locks = [lt for lt in lock_types if lt in DB_LOCK_TYPES]
    results: Dict[str, bool] = {}

    if not db_locks:
        return results

    try:
        unset_fields = {f"locks.{lt}": "" for lt in db_locks}

        await _db.locks.update_one(
            {"chat_id": chat_id},
            {"$unset": unset_fields}
        )

        await _cleanup_empty_doc(chat_id)

        for lt in db_locks:
            results[lt] = True

    except Exception as e:
        logger.error(f"Error disabling multiple locks for chat {chat_id}: {e}")
        for lt in db_locks:
            results[lt] = False

    return results


async def disable_all_locks(chat_id: int) -> bool:
    """
    Disable ALL locks — deletes the document from DB entirely.
    Clears cache (sets to empty {}).
    Returns True on success.
    """
    try:
        await _db.locks.delete_one({"chat_id": chat_id})
        _cache_set(chat_id, {})
        return True
    except Exception as e:
        logger.error(f"Error disabling all locks for chat {chat_id}: {e}")
        return False
