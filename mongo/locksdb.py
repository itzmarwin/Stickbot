from typing import Optional, Dict, List
from pymongo import AsyncMongoClient

_client: Optional[AsyncMongoClient] = None
_db = None

_locks_cache: Dict[int, Dict[str, bool]] = {}

DB_LOCK_TYPES = frozenset({
    "all",
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
    "stickers",
    "animations",
    "games",
    "msg",
    "webprev",
    "invite",
    "pin",
    "info",
})


def init_locksdb(client: AsyncMongoClient, db):
    global _client, _db
    _client = client
    _db = db


async def create_indexes():
    if _db is None:
        return
    await _db.locks.create_index("chat_id", unique=True)


def _cache_get(chat_id: int) -> Optional[Dict[str, bool]]:
    return _locks_cache.get(chat_id)


def _cache_set(chat_id: int, locks: Dict[str, bool]):
    _locks_cache[chat_id] = locks


def _cache_update_one(chat_id: int, lock_type: str, enabled: bool):
    if chat_id not in _locks_cache:
        _locks_cache[chat_id] = {}
    if enabled:
        _locks_cache[chat_id][lock_type] = True
    else:
        _locks_cache[chat_id].pop(lock_type, None)


async def get_chat_locks(chat_id: int) -> Dict[str, bool]:
    if _db is None:
        return {}
    cached = _cache_get(chat_id)
    if cached is not None:
        return cached
    try:
        doc = await _db.locks.find_one({"chat_id": chat_id}, {"locks": 1})
        locks = {k: True for k, v in doc["locks"].items() if v} if doc and doc.get("locks") else {}
        _cache_set(chat_id, locks)
        return locks
    except Exception:
        return {}


async def enable_lock(chat_id: int, lock_type: str) -> bool:
    if _db is None or lock_type not in DB_LOCK_TYPES:
        return False
    try:
        await _db.locks.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, f"locks.{lock_type}": True}},
            upsert=True
        )
        _cache_update_one(chat_id, lock_type, True)
        return True
    except Exception:
        return False


async def enable_multiple_locks(chat_id: int, lock_types: List[str]) -> bool:
    if _db is None:
        return False
    valid = [lt for lt in lock_types if lt in DB_LOCK_TYPES]
    if not valid:
        return False
    try:
        set_fields = {"chat_id": chat_id}
        set_fields.update({f"locks.{lt}": True for lt in valid})
        await _db.locks.update_one({"chat_id": chat_id}, {"$set": set_fields}, upsert=True)
        for lt in valid:
            _cache_update_one(chat_id, lt, True)
        return True
    except Exception:
        return False


async def _cleanup_empty_doc(chat_id: int):
    if _db is None:
        return
    try:
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
    except Exception:
        pass


async def disable_lock(chat_id: int, lock_type: str) -> bool:
    if _db is None or lock_type not in DB_LOCK_TYPES:
        return False
    try:
        await _db.locks.update_one({"chat_id": chat_id}, {"$unset": {f"locks.{lock_type}": ""}})
        await _cleanup_empty_doc(chat_id)
        return True
    except Exception:
        return False


async def disable_multiple_locks(chat_id: int, lock_types: List[str]) -> bool:
    if _db is None:
        return False
    valid = [lt for lt in lock_types if lt in DB_LOCK_TYPES]
    if not valid:
        return False
    try:
        await _db.locks.update_one(
            {"chat_id": chat_id},
            {"$unset": {f"locks.{lt}": "" for lt in valid}}
        )
        await _cleanup_empty_doc(chat_id)
        return True
    except Exception:
        return False


async def disable_all_locks(chat_id: int) -> bool:
    if _db is None:
        return False
    try:
        await _db.locks.delete_one({"chat_id": chat_id})
        _cache_set(chat_id, {})
        return True
    except Exception:
        return False
