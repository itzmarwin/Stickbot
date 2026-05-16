import logging
from pymongo import AsyncMongoClient
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_client: Optional[AsyncMongoClient] = None
_db = None


def init_stickerdb(client: AsyncMongoClient, db):
    global _client, _db
    _client = client
    _db = db


async def create_indexes():
    await _db.sticker_packs.create_index("user_id")
    await _db.sticker_packs.create_index("short_name", unique=True)
    await _db.sticker_packs.create_index([("user_id", 1), ("created_at", -1)])
    await _db.afk.create_index("user.id", unique=True)
    logger.info("✅ stickerdb indexes created")


async def get_user_active_pack(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        cursor = _db.sticker_packs.find(
            {"user_id": user_id},
            {"pack_name": 1, "short_name": 1, "sticker_count": 1, "created_at": 1, "pack_link": 1}
        ).sort("created_at", -1).limit(1)

        packs = await cursor.to_list(1)
        return packs[0] if packs else None
    except Exception as e:
        logger.error(f"Error getting user active pack {user_id}: {e}")
        return None


async def get_user_all_packs(user_id: int) -> List[Dict[str, Any]]:
    try:
        cursor = _db.sticker_packs.find(
            {"user_id": user_id},
            {"pack_name": 1, "short_name": 1, "sticker_count": 1, "created_at": 1, "pack_link": 1}
        ).sort("created_at", -1)
        return await cursor.to_list(None)
    except Exception as e:
        logger.error(f"Error getting user packs {user_id}: {e}")
        return []


async def create_sticker_pack(user_id: int, pack_name: str, short_name: str) -> bool:
    try:
        pack_data = {
            "user_id": user_id,
            "pack_name": pack_name,
            "short_name": short_name,
            "pack_link": f"https://t.me/addstickers/{short_name}",
            "sticker_count": 1,
            "created_at": datetime.utcnow()
        }
        await _db.sticker_packs.insert_one(pack_data)
        return True
    except Exception as e:
        logger.error(f"Error creating pack for user {user_id}: {e}")
        return False


async def increment_sticker_count(user_id: int) -> bool:
    try:
        latest_pack = await get_user_active_pack(user_id)
        if latest_pack:
            await _db.sticker_packs.update_one(
                {"short_name": latest_pack["short_name"]},
                {"$inc": {"sticker_count": 1}}
            )
            return True
        return False
    except Exception as e:
        logger.error(f"Error incrementing sticker count: {e}")
        return False


async def update_pack_sticker_count(pack_short_name: str, count: int) -> bool:
    try:
        await _db.sticker_packs.update_one(
            {"short_name": pack_short_name},
            {"$set": {"sticker_count": count}}
        )
        return True
    except Exception as e:
        logger.error(f"Error updating pack count {pack_short_name}: {e}")
        return False


async def delete_user_pack(user_id: int) -> bool:
    try:
        result = await _db.sticker_packs.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting user pack for {user_id}: {e}")
        return False


async def get_user_packs_paginated(user_id: int, page: int = 0, limit: int = 6):
    try:
        skip = page * limit
        cursor = _db.sticker_packs.find(
            {"user_id": user_id},
            {"pack_name": 1, "short_name": 1, "sticker_count": 1, "created_at": 1}
        ).sort("created_at", -1).skip(skip).limit(limit)

        packs = await cursor.to_list(limit)
        total = await _db.sticker_packs.count_documents({"user_id": user_id})
        return packs, total
    except Exception as e:
        logger.error(f"Error getting paginated packs for user {user_id}: {e}")
        return [], 0


async def update_pack_name(short_name: str, new_pack_name: str) -> bool:
    try:
        result = await _db.sticker_packs.update_one(
            {"short_name": short_name},
            {"$set": {"pack_name": new_pack_name}}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error updating pack name {short_name}: {e}")
        return False


async def delete_pack_by_short_name(short_name: str) -> bool:
    try:
        result = await _db.sticker_packs.delete_one({"short_name": short_name})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting pack {short_name}: {e}")
        return False


async def get_pack_by_short_name(short_name: str) -> Optional[Dict[str, Any]]:
    try:
        return await _db.sticker_packs.find_one({"short_name": short_name})
    except Exception as e:
        logger.error(f"Error getting pack {short_name}: {e}")
        return None


async def delete_user_packs(user_id: int) -> int:
    try:
        result = await _db.sticker_packs.delete_many({"user_id": user_id})
        return result.deleted_count
    except Exception as e:
        logger.error(f"Error deleting user packs for {user_id}: {e}")
        return 0


async def get_total_packs_count() -> int:
    try:
        return await _db.sticker_packs.count_documents({})
    except Exception as e:
        logger.error(f"Error getting packs count: {e}")
        return 0


async def get_afk_user(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        return await _db.afk.find_one({"user.id": user_id})
    except Exception as e:
        logger.error(f"Error getting AFK user {user_id}: {e}")
        return None


async def set_afk_user(user_id: int, first_name: str, reason: str, since: datetime):
    try:
        afk_data = {
            "user": {
                "id": user_id,
                "first_name": first_name,
            },
            "reason": reason,
            "since": since
        }
        await _db.afk.update_one(
            {"user.id": user_id},
            {"$set": afk_data},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error setting AFK user {user_id}: {e}")


async def remove_afk_user(user_id: int):
    try:
        await _db.afk.delete_one({"user.id": user_id})
    except Exception as e:
        logger.error(f"Error removing AFK user {user_id}: {e}")
