import json
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, Dict, Any, List
import redis.asyncio as aioredis

from config import MONGO_URI, DATABASE_NAME

logger = logging.getLogger(__name__)

client: Optional[AsyncIOMotorClient] = None
db = None
redis_client: Optional[aioredis.Redis] = None

REDIS_TTL = 3600
REDIS_MAX_MEMORY = "500mb"
REDIS_EVICTION_POLICY = "allkeys-lru"

async def init_db():
    global client, db, redis_client
    try:
        client = AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            maxPoolSize=50,
            minPoolSize=10
        )
        
        await client.admin.command('ping')
        db = client[DATABASE_NAME]
        
        await db.users.create_index("user_id", unique=True)
        await db.sticker_packs.create_index("user_id")
        await db.sticker_packs.create_index("short_name", unique=True)
        await db.afk.create_index("user.id", unique=True)
        await db.gbans.create_index("user_id", unique=True)
        await db.served_chats.create_index("chat_id", unique=True)
        await db.published_packs.create_index("pack_short_name", unique=True)
        await db.published_packs.create_index("keyword")
        
        redis_client = await aioredis.from_url(
            "redis://localhost:6379",
            encoding="utf-8",
            decode_responses=True,
            max_connections=50
        )
        
        await redis_client.config_set("maxmemory", REDIS_MAX_MEMORY)
        await redis_client.config_set("maxmemory-policy", REDIS_EVICTION_POLICY)
        
        await redis_client.ping()
        
        logger.info(f"Redis cache initialized: {REDIS_MAX_MEMORY} max memory, {REDIS_EVICTION_POLICY} eviction")
        logger.info("Database initialized successfully")
        return db
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

async def close_db():
    global client, redis_client
    if client:
        client.close()
    if redis_client:
        await redis_client.close()

def get_db():
    return db

def serialize_doc(doc: Dict[str, Any]) -> str:
    if doc is None:
        return None
    doc_copy = doc.copy()
    if '_id' in doc_copy:
        doc_copy['_id'] = str(doc_copy['_id'])
    if 'created_at' in doc_copy and isinstance(doc_copy['created_at'], datetime):
        doc_copy['created_at'] = doc_copy['created_at'].isoformat()
    if 'published_at' in doc_copy and isinstance(doc_copy['published_at'], datetime):
        doc_copy['published_at'] = doc_copy['published_at'].isoformat()
    if 'since' in doc_copy and isinstance(doc_copy['since'], datetime):
        doc_copy['since'] = doc_copy['since'].isoformat()
    if 'banned_at' in doc_copy and isinstance(doc_copy['banned_at'], datetime):
        doc_copy['banned_at'] = doc_copy['banned_at'].isoformat()
    if 'added_at' in doc_copy and isinstance(doc_copy['added_at'], datetime):
        doc_copy['added_at'] = doc_copy['added_at'].isoformat()
    return json.dumps(doc_copy)

def deserialize_doc(data: str) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    doc = json.loads(data)
    if 'created_at' in doc and isinstance(doc['created_at'], str):
        doc['created_at'] = datetime.fromisoformat(doc['created_at'])
    if 'published_at' in doc and isinstance(doc['published_at'], str):
        doc['published_at'] = datetime.fromisoformat(doc['published_at'])
    if 'since' in doc and isinstance(doc['since'], str):
        doc['since'] = datetime.fromisoformat(doc['since'])
    if 'banned_at' in doc and isinstance(doc['banned_at'], str):
        doc['banned_at'] = datetime.fromisoformat(doc['banned_at'])
    if 'added_at' in doc and isinstance(doc['added_at'], str):
        doc['added_at'] = datetime.fromisoformat(doc['added_at'])
    return doc

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        cache_key = f"user:{user_id}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        user = await db.users.find_one({"user_id": user_id})
        
        if user:
            await redis_client.setex(cache_key, REDIS_TTL, serialize_doc(user))
        
        return user
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None

async def create_user(user_id: int, username: Optional[str] = None, 
                     first_name: Optional[str] = None) -> bool:
    try:
        user_data = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "created_at": datetime.utcnow(),
            "has_started": True
        }
        await db.users.insert_one(user_data)
        
        cache_key = f"user:{user_id}"
        await redis_client.setex(cache_key, REDIS_TTL, serialize_doc(user_data))
        await redis_client.delete("total_users_count")
        
        return True
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")
        return False

async def update_user_started(user_id: int) -> bool:
    try:
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"has_started": True}},
            upsert=True
        )
        
        cache_key = f"user:{user_id}"
        await redis_client.delete(cache_key)
        
        return True
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        return False

async def get_user_active_pack(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        cache_key = f"user_active_pack:{user_id}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        cursor = db.sticker_packs.find({"user_id": user_id}).sort("created_at", -1).limit(1)
        packs = await cursor.to_list(length=1)
        pack = packs[0] if packs else None
        
        if pack:
            await redis_client.setex(cache_key, REDIS_TTL, serialize_doc(pack))
        
        return pack
    except Exception as e:
        logger.error(f"Error getting user active pack {user_id}: {e}")
        return None

async def get_user_all_packs(user_id: int) -> List[Dict[str, Any]]:
    try:
        cache_key = f"user_all_packs:{user_id}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return [deserialize_doc(p) for p in json.loads(cached)]
        
        cursor = db.sticker_packs.find({"user_id": user_id}).sort("created_at", -1)
        packs = await cursor.to_list(length=None)
        
        if packs:
            serialized_packs = [json.loads(serialize_doc(p)) for p in packs]
            await redis_client.setex(cache_key, REDIS_TTL, json.dumps(serialized_packs))
        
        return packs
    except Exception as e:
        logger.error(f"Error getting user packs {user_id}: {e}")
        return []

async def create_sticker_pack(user_id: int, pack_name: str, 
                             short_name: str) -> bool:
    try:
        pack_data = {
            "user_id": user_id,
            "pack_name": pack_name,
            "short_name": short_name,
            "pack_link": f"https://t.me/addstickers/{short_name}",
            "sticker_count": 1,
            "created_at": datetime.utcnow()
        }
        await db.sticker_packs.insert_one(pack_data)
        
        cache_key = f"pack:{short_name}"
        await redis_client.setex(cache_key, REDIS_TTL, serialize_doc(pack_data))
        
        await redis_client.delete(f"user_active_pack:{user_id}")
        await redis_client.delete(f"user_all_packs:{user_id}")
        await redis_client.delete("total_packs_count")
        
        return True
    except Exception as e:
        logger.error(f"Error creating pack for user {user_id}: {e}")
        return False

async def increment_sticker_count(user_id: int) -> bool:
    try:
        latest_pack = await get_user_active_pack(user_id)
        if latest_pack:
            await db.sticker_packs.update_one(
                {"short_name": latest_pack["short_name"]},
                {"$inc": {"sticker_count": 1}}
            )
            
            cache_key = f"pack:{latest_pack['short_name']}"
            await redis_client.delete(cache_key)
            await redis_client.delete(f"user_active_pack:{user_id}")
            await redis_client.delete(f"user_all_packs:{user_id}")
            
            return True
        return False
    except Exception as e:
        logger.error(f"Error incrementing sticker count: {e}")
        return False

async def update_pack_sticker_count(pack_short_name: str, count: int) -> bool:
    try:
        await db.sticker_packs.update_one(
            {"short_name": pack_short_name},
            {"$set": {"sticker_count": count}}
        )
        
        cache_key = f"pack:{pack_short_name}"
        await redis_client.delete(cache_key)
        
        pack = await db.sticker_packs.find_one({"short_name": pack_short_name})
        if pack:
            await redis_client.delete(f"user_active_pack:{pack['user_id']}")
            await redis_client.delete(f"user_all_packs:{pack['user_id']}")
        
        return True
    except Exception as e:
        logger.error(f"Error updating pack count {pack_short_name}: {e}")
        return False

async def delete_user_pack(user_id: int) -> bool:
    try:
        result = await db.sticker_packs.delete_one({"user_id": user_id})
        
        await redis_client.delete(f"user_active_pack:{user_id}")
        await redis_client.delete(f"user_all_packs:{user_id}")
        await redis_client.delete("total_packs_count")
        
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting user pack for {user_id}: {e}")
        return False

async def get_user_packs_paginated(user_id: int, page: int = 0, limit: int = 6):
    try:
        skip = page * limit
        cursor = db.sticker_packs.find({"user_id": user_id}).sort("created_at", -1).skip(skip).limit(limit)
        packs = await cursor.to_list(length=limit)
        total = await db.sticker_packs.count_documents({"user_id": user_id})
        return packs, total
    except Exception as e:
        logger.error(f"Error getting paginated packs for user {user_id}: {e}")
        return [], 0

async def update_pack_name(short_name: str, new_pack_name: str) -> bool:
    try:
        result = await db.sticker_packs.update_one(
            {"short_name": short_name},
            {"$set": {"pack_name": new_pack_name}}
        )
        
        cache_key = f"pack:{short_name}"
        await redis_client.delete(cache_key)
        
        pack = await db.sticker_packs.find_one({"short_name": short_name})
        if pack:
            await redis_client.delete(f"user_active_pack:{pack['user_id']}")
            await redis_client.delete(f"user_all_packs:{pack['user_id']}")
        
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error updating pack name {short_name}: {e}")
        return False

async def delete_pack_by_short_name(short_name: str) -> bool:
    try:
        pack = await db.sticker_packs.find_one({"short_name": short_name})
        result = await db.sticker_packs.delete_one({"short_name": short_name})
        
        cache_key = f"pack:{short_name}"
        await redis_client.delete(cache_key)
        
        if pack:
            await redis_client.delete(f"user_active_pack:{pack['user_id']}")
            await redis_client.delete(f"user_all_packs:{pack['user_id']}")
        
        await redis_client.delete("total_packs_count")
        
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting pack {short_name}: {e}")
        return False

async def get_pack_by_short_name(short_name: str) -> Optional[Dict[str, Any]]:
    try:
        cache_key = f"pack:{short_name}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        pack = await db.sticker_packs.find_one({"short_name": short_name})
        
        if pack:
            await redis_client.setex(cache_key, REDIS_TTL, serialize_doc(pack))
        
        return pack
    except Exception as e:
        logger.error(f"Error getting pack {short_name}: {e}")
        return None

async def get_pack_by_name(pack_name: str) -> Optional[Dict[str, Any]]:
    try:
        return await db.sticker_packs.find_one({"pack_name": pack_name})
    except Exception as e:
        logger.error(f"Error getting pack by name {pack_name}: {e}")
        return None

async def is_pack_published(short_name: str) -> bool:
    try:
        cache_key = f"published:{short_name}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return cached == "1"
        
        published_pack = await db.published_packs.find_one({"pack_short_name": short_name})
        result = published_pack is not None
        
        await redis_client.setex(cache_key, REDIS_TTL, "1" if result else "0")
        
        return result
    except Exception as e:
        logger.error(f"Error checking if pack is published {short_name}: {e}")
        return False

async def create_published_pack(user_id: int, pack_short_name: str, keyword: str, first_sticker_id: str) -> bool:
    try:
        published_pack_data = {
            "user_id": user_id,
            "pack_short_name": pack_short_name,
            "keyword": keyword.lower(),
            "first_sticker_id": first_sticker_id,
            "published_at": datetime.utcnow(),
            "is_active": True
        }
        await db.published_packs.insert_one(published_pack_data)
        
        cache_key = f"published:{pack_short_name}"
        await redis_client.setex(cache_key, REDIS_TTL, "1")
        
        await redis_client.delete(f"published_keyword:{keyword.lower()}")
        
        return True
    except Exception as e:
        logger.error(f"Error creating published pack for {pack_short_name}: {e}")
        return False

async def get_published_pack_by_keyword(keyword: str) -> Optional[Dict[str, Any]]:
    try:
        cache_key = f"published_keyword:{keyword.lower()}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        pack = await db.published_packs.find_one({"keyword": keyword.lower(), "is_active": True})
        
        if pack:
            await redis_client.setex(cache_key, REDIS_TTL, serialize_doc(pack))
        
        return pack
    except Exception as e:
        logger.error(f"Error getting published pack by keyword {keyword}: {e}")
        return None

async def search_published_packs(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        cursor = db.published_packs.find({
            "keyword": {"$regex": f"^{query.lower()}", "$options": "i"},
            "is_active": True
        }).sort("published_at", -1).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as e:
        logger.error(f"Error searching published packs for {query}: {e}")
        return []

async def get_published_pack_by_short_name(short_name: str) -> Optional[Dict[str, Any]]:
    try:
        cache_key = f"published_pack:{short_name}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        pack = await db.published_packs.find_one({"pack_short_name": short_name, "is_active": True})
        
        if pack:
            await redis_client.setex(cache_key, REDIS_TTL, serialize_doc(pack))
        
        return pack
    except Exception as e:
        logger.error(f"Error getting published pack by short name {short_name}: {e}")
        return None

async def get_afk_user(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        cache_key = f"afk:{user_id}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        afk_data = await db.afk.find_one({"user.id": user_id})
        
        if afk_data:
            await redis_client.setex(cache_key, REDIS_TTL, serialize_doc(afk_data))
        
        return afk_data
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
        await db.afk.update_one(
            {"user.id": user_id},
            {"$set": afk_data},
            upsert=True
        )
        
        cache_key = f"afk:{user_id}"
        await redis_client.setex(cache_key, REDIS_TTL, serialize_doc(afk_data))
    except Exception as e:
        logger.error(f"Error setting AFK user {user_id}: {e}")

async def remove_afk_user(user_id: int):
    try:
        await db.afk.delete_one({"user.id": user_id})
        
        cache_key = f"afk:{user_id}"
        await redis_client.delete(cache_key)
    except Exception as e:
        logger.error(f"Error removing AFK user {user_id}: {e}")

async def add_served_chat(chat_id: int) -> bool:
    try:
        chat_data = {
            "chat_id": chat_id,
            "added_at": datetime.utcnow()
        }
        await db.served_chats.update_one(
            {"chat_id": chat_id},
            {"$set": chat_data},
            upsert=True
        )
        
        await redis_client.delete("served_chats_list")
        await redis_client.delete("served_chats_count")
        
        return True
    except Exception as e:
        logger.error(f"Error adding served chat {chat_id}: {e}")
        return False

async def remove_served_chat(chat_id: int) -> bool:
    try:
        await db.served_chats.delete_one({"chat_id": chat_id})
        
        await redis_client.delete("served_chats_list")
        await redis_client.delete("served_chats_count")
        
        return True
    except Exception as e:
        logger.error(f"Error removing served chat {chat_id}: {e}")
        return False

async def get_served_chats() -> List[Dict[str, Any]]:
    try:
        cache_key = "served_chats_list"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return [deserialize_doc(c) for c in json.loads(cached)]
        
        cursor = db.served_chats.find({})
        chats = await cursor.to_list(length=None)
        
        if chats:
            serialized_chats = [json.loads(serialize_doc(c)) for c in chats]
            await redis_client.setex(cache_key, REDIS_TTL, json.dumps(serialized_chats))
        
        return chats
    except Exception as e:
        logger.error(f"Error getting served chats: {e}")
        return []

async def get_served_chats_count() -> int:
    try:
        cache_key = "served_chats_count"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return int(cached)
        
        count = await db.served_chats.count_documents({})
        
        await redis_client.setex(cache_key, REDIS_TTL, str(count))
        
        return count
    except Exception as e:
        logger.error(f"Error getting served chats count: {e}")
        return 0

async def add_banned_user(user_id: int) -> bool:
    try:
        ban_data = {
            "user_id": user_id,
            "banned_at": datetime.utcnow()
        }
        await db.gbans.update_one(
            {"user_id": user_id},
            {"$set": ban_data},
            upsert=True
        )
        
        cache_key = f"gban:{user_id}"
        await redis_client.setex(cache_key, REDIS_TTL, "1")
        
        await redis_client.delete("gbans_list")
        await redis_client.delete("gbans_count")
        
        return True
    except Exception as e:
        logger.error(f"Error adding banned user {user_id}: {e}")
        return False

async def remove_banned_user(user_id: int) -> bool:
    try:
        await db.gbans.delete_one({"user_id": user_id})
        
        cache_key = f"gban:{user_id}"
        await redis_client.delete(cache_key)
        
        await redis_client.delete("gbans_list")
        await redis_client.delete("gbans_count")
        
        return True
    except Exception as e:
        logger.error(f"Error removing banned user {user_id}: {e}")
        return False

async def get_banned_users() -> List[int]:
    try:
        cache_key = "gbans_list"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        cursor = db.gbans.find({})
        banned_users = await cursor.to_list(length=None)
        user_ids = [user["user_id"] for user in banned_users]
        
        await redis_client.setex(cache_key, REDIS_TTL, json.dumps(user_ids))
        
        return user_ids
    except Exception as e:
        logger.error(f"Error getting banned users: {e}")
        return []

async def get_banned_count() -> int:
    try:
        cache_key = "gbans_count"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return int(cached)
        
        count = await db.gbans.count_documents({})
        
        await redis_client.setex(cache_key, REDIS_TTL, str(count))
        
        return count
    except Exception as e:
        logger.error(f"Error getting banned count: {e}")
        return 0

async def is_banned_user(user_id: int) -> bool:
    try:
        cache_key = f"gban:{user_id}"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return cached == "1"
        
        ban_data = await db.gbans.find_one({"user_id": user_id})
        result = ban_data is not None
        
        await redis_client.setex(cache_key, REDIS_TTL, "1" if result else "0")
        
        return result
    except Exception as e:
        logger.error(f"Error checking banned user {user_id}: {e}")
        return False

async def delete_user_packs(user_id: int) -> int:
    try:
        packs_cursor = db.sticker_packs.find({"user_id": user_id})
        packs = await packs_cursor.to_list(length=None)
        deleted_count = len(packs)
        
        for pack in packs:
            await db.sticker_packs.delete_one({"_id": pack["_id"]})
            
            cache_key = f"pack:{pack['short_name']}"
            await redis_client.delete(cache_key)
        
        await redis_client.delete(f"user_active_pack:{user_id}")
        await redis_client.delete(f"user_all_packs:{user_id}")
        await redis_client.delete("total_packs_count")
        
        return deleted_count
    except Exception as e:
        logger.error(f"Error deleting user packs for {user_id}: {e}")
        return 0

async def get_all_users() -> List[Dict[str, Any]]:
    try:
        cache_key = "all_users_list"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return [deserialize_doc(u) for u in json.loads(cached)]
        
        cursor = db.users.find({})
        users = await cursor.to_list(length=None)
        
        if users:
            serialized_users = [json.loads(serialize_doc(u)) for u in users]
            await redis_client.setex(cache_key, 300, json.dumps(serialized_users))
        
        return users
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

async def get_total_users_count() -> int:
    try:
        cache_key = "total_users_count"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return int(cached)
        
        count = await db.users.count_documents({})
        
        await redis_client.setex(cache_key, REDIS_TTL, str(count))
        
        return count
    except Exception as e:
        logger.error(f"Error getting users count: {e}")
        return 0

async def get_total_packs_count() -> int:
    try:
        cache_key = "total_packs_count"
        cached = await redis_client.get(cache_key)
        
        if cached:
            return int(cached)
        
        count = await db.sticker_packs.count_documents({})
        
        await redis_client.setex(cache_key, REDIS_TTL, str(count))
        
        return count
    except Exception as e:
        logger.error(f"Error getting packs count: {e}")
        return 0

async def get_gbanned_users_count() -> int:
    try:
        return await get_banned_count()
    except Exception as e:
        logger.error(f"Error getting gbanned count: {e}")
        return 0

async def get_user_pack(user_id: int) -> Optional[Dict[str, Any]]:
    return await get_user_active_pack(user_id)
