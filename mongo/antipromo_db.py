import logging
from typing import Optional, Dict, Set, List
from pymongo import AsyncMongoClient

logger = logging.getLogger(__name__)

_client: Optional[AsyncMongoClient] = None
_db = None

# ─── In-Memory Caches ───────────────────────────────────────────────
_antipromo_cache: Dict[int, bool] = {}   # {chat_id: enabled}
_whitelist_cache: Set[int]        = set() # {bot_id, ...}
_whitelist_loaded: bool           = False
_toughlist_cache: Set[int]        = set() # {bot_id, ...} - bots under strict /atp rules
_toughlist_loaded: bool           = False


def init_antipromo_db(client: AsyncMongoClient, db):
    global _client, _db
    _client = client
    _db = db


async def create_indexes():
    if _db is None:
        return
    await _db.antipromo_settings.create_index("chat_id", unique=True)
    await _db.antipromo_whitelist.create_index("bot_id",  unique=True)
    await _db.antipromo_toughlist.create_index("bot_id",  unique=True)
    logger.info("✅ antipromo indexes created")


# ─── Whitelist ───────────────────────────────────────────────────────

async def _ensure_whitelist_loaded():
    """Load whitelist from DB into cache once on first use."""
    global _whitelist_loaded
    if _whitelist_loaded:
        return
    if _db is None:
        _whitelist_loaded = True
        return
    try:
        async for doc in _db.antipromo_whitelist.find({}, {"bot_id": 1}):
            _whitelist_cache.add(doc["bot_id"])
        _whitelist_loaded = True
        logger.info(f"✅ Antipromo whitelist loaded: {len(_whitelist_cache)} bots")
    except Exception as e:
        logger.error(f"Error loading antipromo whitelist: {e}")
        _whitelist_loaded = True


async def add_to_whitelist(bot_id: int, bot_username: str) -> bool:
    if _db is None:
        return False
    try:
        await _db.antipromo_whitelist.update_one(
            {"bot_id": bot_id},
            {"$set": {"bot_id": bot_id, "username": bot_username}},
            upsert=True
        )
        _whitelist_cache.add(bot_id)
        return True
    except Exception as e:
        logger.error(f"Error adding to whitelist {bot_id}: {e}")
        return False


async def remove_from_whitelist(bot_id: int) -> bool:
    if _db is None:
        return False
    try:
        result = await _db.antipromo_whitelist.delete_one({"bot_id": bot_id})
        _whitelist_cache.discard(bot_id)
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error removing from whitelist {bot_id}: {e}")
        return False


async def is_whitelisted(bot_id: int) -> bool:
    """Pure cache check after first load — zero DB hits."""
    await _ensure_whitelist_loaded()
    return bot_id in _whitelist_cache


async def get_whitelist() -> List[Dict]:
    if _db is None:
        return []
    try:
        cursor = _db.antipromo_whitelist.find({}, {"bot_id": 1, "username": 1, "_id": 0})
        return [doc async for doc in cursor]
    except Exception as e:
        logger.error(f"Error getting whitelist: {e}")
        return []


# ─── Tough List (strict /atp rules) ───────────────────────────────────

async def _ensure_toughlist_loaded():
    """Load tough list from DB into cache once on first use."""
    global _toughlist_loaded
    if _toughlist_loaded:
        return
    if _db is None:
        _toughlist_loaded = True
        return
    try:
        async for doc in _db.antipromo_toughlist.find({}, {"bot_id": 1}):
            _toughlist_cache.add(doc["bot_id"])
        _toughlist_loaded = True
        logger.info(f"✅ Antipromo tough list loaded: {len(_toughlist_cache)} bots")
    except Exception as e:
        logger.error(f"Error loading antipromo tough list: {e}")
        _toughlist_loaded = True


async def add_to_toughlist(bot_id: int, bot_username: str) -> bool:
    if _db is None:
        return False
    try:
        await _db.antipromo_toughlist.update_one(
            {"bot_id": bot_id},
            {"$set": {"bot_id": bot_id, "username": bot_username}},
            upsert=True
        )
        _toughlist_cache.add(bot_id)
        return True
    except Exception as e:
        logger.error(f"Error adding to tough list {bot_id}: {e}")
        return False


async def remove_from_toughlist(bot_id: int) -> bool:
    if _db is None:
        return False
    try:
        result = await _db.antipromo_toughlist.delete_one({"bot_id": bot_id})
        _toughlist_cache.discard(bot_id)
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error removing from tough list {bot_id}: {e}")
        return False


async def is_in_toughlist(bot_id: int) -> bool:
    """Pure cache check after first load — zero DB hits."""
    await _ensure_toughlist_loaded()
    return bot_id in _toughlist_cache


async def get_toughlist() -> List[Dict]:
    if _db is None:
        return []
    try:
        cursor = _db.antipromo_toughlist.find({}, {"bot_id": 1, "username": 1, "_id": 0})
        return [doc async for doc in cursor]
    except Exception as e:
        logger.error(f"Error getting tough list: {e}")
        return []


# ─── Per-Chat Settings ───────────────────────────────────────────────

async def get_antipromo_status(chat_id: int) -> bool:
    if chat_id in _antipromo_cache:
        return _antipromo_cache[chat_id]
    if _db is None:
        return False
    try:
        doc = await _db.antipromo_settings.find_one(
            {"chat_id": chat_id}, {"enabled": 1}
        )
        status = doc.get("enabled", False) if doc else False
        _antipromo_cache[chat_id] = status
        return status
    except Exception as e:
        logger.error(f"Error getting antipromo status {chat_id}: {e}")
        return False


async def set_antipromo_status(chat_id: int, enabled: bool) -> bool:
    if _db is None:
        return False
    try:
        await _db.antipromo_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "enabled": enabled}},
            upsert=True
        )
        _antipromo_cache[chat_id] = enabled
        return True
    except Exception as e:
        logger.error(f"Error setting antipromo status {chat_id}: {e}")
        return False
