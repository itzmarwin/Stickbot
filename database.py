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

# ✅ FIX: Multi-tier caching strategy for different data types
REDIS_TTL_SHORT = 300      # 5 minutes - Frequently changing data
REDIS_TTL_MEDIUM = 3600    # 1 hour - Semi-static data
REDIS_TTL_LONG = 86400     # 24 hours - Static data
REDIS_MAX_MEMORY = "500mb"
REDIS_EVICTION_POLICY = "allkeys-lru"

async def init_db():
    """
    Initialize MongoDB and Redis connections with optimized settings
    """
    global client, db, redis_client
    try:
        # ✅ FIX 1: Increased connection pool for 10K+ users
        client = AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            maxPoolSize=200,        # ✅ Increased from 50
            minPoolSize=50,         # ✅ Increased from 10
            waitQueueTimeoutMS=10000,  # ✅ Added: Queue timeout
            retryWrites=True,       # ✅ Added: Retry failed writes
            retryReads=True,        # ✅ Added: Retry failed reads
            maxIdleTimeMS=45000     # ✅ Added: Close idle connections
        )
        
        # Test connection
        await client.admin.command('ping')
        db = client[DATABASE_NAME]
        
        # ✅ FIX 2: Optimized indexes with compound indexes
        logger.info("Creating database indexes...")
        
        # User indexes
        await db.users.create_index("user_id", unique=True)
        await db.users.create_index([("username", 1)])  # ✅ Added: Username search
        await db.users.create_index([("created_at", -1)])  # ✅ Added: Sorting
        await db.users.create_index([("has_started", 1)])  # ✅ Added: Filter active users
        
        # Sticker pack indexes
        await db.sticker_packs.create_index("user_id")
        await db.sticker_packs.create_index("short_name", unique=True)
        await db.sticker_packs.create_index([("user_id", 1), ("created_at", -1)])  # ✅ Compound index
        await db.sticker_packs.create_index([("sticker_count", 1)])  # ✅ Added: Pack size queries
        
        # AFK indexes
        await db.afk.create_index("user.id", unique=True)
        await db.afk.create_index([("since", 1)])  # ✅ Added: Time-based cleanup
        
        # GBan indexes
        await db.gbans.create_index("user_id", unique=True)
        await db.gbans.create_index([("banned_at", -1)])  # ✅ Added: Recent bans
        
        # Served chats indexes
        await db.served_chats.create_index("chat_id", unique=True)
        await db.served_chats.create_index([("added_at", -1)])  # ✅ Added: Sorting
        
        # Published packs indexes
        await db.published_packs.create_index("pack_short_name", unique=True)
        await db.published_packs.create_index([("keyword", 1), ("is_active", 1)])  # ✅ Compound index
        await db.published_packs.create_index([("user_id", 1)])  # ✅ Added: User's published packs
        await db.published_packs.create_index([("published_at", -1)])  # ✅ Added: Recent packs
        
        logger.info("✅ Database indexes created successfully")
        
        # ✅ FIX 3: Redis connection with increased pool
        redis_client = await aioredis.from_url(
            "redis://localhost:6379",
            encoding="utf-8",
            decode_responses=True,
            max_connections=100,    # ✅ Increased from 50
            socket_keepalive=True,  # ✅ Added: Keep connections alive
            socket_connect_timeout=5,  # ✅ Added: Connection timeout
            retry_on_timeout=True   # ✅ Added: Retry on timeout
        )
        
        await redis_client.config_set("maxmemory", REDIS_MAX_MEMORY)
        await redis_client.config_set("maxmemory-policy", REDIS_EVICTION_POLICY)
        
        await redis_client.ping()
        
        logger.info(f"✅ Redis cache initialized: {REDIS_MAX_MEMORY} max memory, {REDIS_EVICTION_POLICY} eviction")
        logger.info("✅ Database initialized successfully")
        return db
        
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)
        raise

async def close_db():
    """
    ✅ FIX 4: Graceful shutdown with proper cleanup
    """
    global client, redis_client
    try:
        if redis_client:
            logger.info("Closing Redis connection...")
            await redis_client.close()
            await redis_client.connection_pool.disconnect()
        
        if client:
            logger.info("Closing MongoDB connection...")
            client.close()
        
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")

def get_db():
    """Get database instance"""
    return db

def get_redis():
    """Get Redis client instance"""
    return redis_client

# ✅ FIX 5: Added error handling for Redis failures
async def safe_redis_get(key: str) -> Optional[str]:
    """Safely get from Redis with fallback"""
    try:
        return await redis_client.get(key)
    except Exception as e:
        logger.error(f"Redis GET error for key {key}: {e}")
        return None

async def safe_redis_set(key: str, value: str, ttl: int):
    """Safely set to Redis with error handling"""
    try:
        await redis_client.setex(key, ttl, value)
    except Exception as e:
        logger.error(f"Redis SET error for key {key}: {e}")

async def safe_redis_delete(key: str):
    """Safely delete from Redis with error handling"""
    try:
        await redis_client.delete(key)
    except Exception as e:
        logger.error(f"Redis DELETE error for key {key}: {e}")

# Serialization functions remain the same
def serialize_doc(doc: Dict[str, Any]) -> str:
    """Serialize MongoDB document to JSON string"""
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
    """Deserialize JSON string to MongoDB document"""
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

# ✅ User functions with optimized caching
async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by ID with long-term caching (user data rarely changes)"""
    try:
        cache_key = f"user:{user_id}"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        user = await db.users.find_one({"user_id": user_id})
        
        if user:
            await safe_redis_set(cache_key, serialize_doc(user), REDIS_TTL_LONG)  # ✅ 24h cache
        
        return user
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None

async def create_user(user_id: int, username: Optional[str] = None, 
                     first_name: Optional[str] = None) -> bool:
    """Create new user with cache invalidation"""
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
        await safe_redis_set(cache_key, serialize_doc(user_data), REDIS_TTL_LONG)
        await safe_redis_delete("total_users_count")
        
        return True
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")
        return False

async def update_user_started(user_id: int) -> bool:
    """Update user started status"""
    try:
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"has_started": True}},
            upsert=True
        )
        
        cache_key = f"user:{user_id}"
        await safe_redis_delete(cache_key)
        
        return True
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        return False

# ✅ Pack functions with optimized caching
async def get_user_active_pack(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user's most recent pack with medium-term caching"""
    try:
        cache_key = f"user_active_pack:{user_id}"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        # ✅ FIX: Added projection to reduce data transfer
        cursor = db.sticker_packs.find(
            {"user_id": user_id},
            {"pack_name": 1, "short_name": 1, "sticker_count": 1, "created_at": 1, "pack_link": 1}
        ).sort("created_at", -1).limit(1)
        
        packs = await cursor.to_list(length=1)
        pack = packs[0] if packs else None
        
        if pack:
            await safe_redis_set(cache_key, serialize_doc(pack), REDIS_TTL_MEDIUM)  # ✅ 1h cache
        
        return pack
    except Exception as e:
        logger.error(f"Error getting user active pack {user_id}: {e}")
        return None

async def get_user_all_packs(user_id: int) -> List[Dict[str, Any]]:
    """Get all user packs with projection for efficiency"""
    try:
        cache_key = f"user_all_packs:{user_id}"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return [deserialize_doc(p) for p in json.loads(cached)]
        
        # ✅ FIX: Added projection to reduce data transfer
        cursor = db.sticker_packs.find(
            {"user_id": user_id},
            {"pack_name": 1, "short_name": 1, "sticker_count": 1, "created_at": 1, "pack_link": 1}
        ).sort("created_at", -1)
        
        packs = await cursor.to_list(length=None)
        
        if packs:
            serialized_packs = [json.loads(serialize_doc(p)) for p in packs]
            await safe_redis_set(cache_key, json.dumps(serialized_packs), REDIS_TTL_MEDIUM)
        
        return packs
    except Exception as e:
        logger.error(f"Error getting user packs {user_id}: {e}")
        return []

async def create_sticker_pack(user_id: int, pack_name: str, 
                             short_name: str) -> bool:
    """Create new sticker pack"""
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
        await safe_redis_set(cache_key, serialize_doc(pack_data), REDIS_TTL_MEDIUM)
        
        # Invalidate user's pack caches
        await safe_redis_delete(f"user_active_pack:{user_id}")
        await safe_redis_delete(f"user_all_packs:{user_id}")
        await safe_redis_delete("total_packs_count")
        
        return True
    except Exception as e:
        logger.error(f"Error creating pack for user {user_id}: {e}")
        return False

async def increment_sticker_count(user_id: int) -> bool:
    """Increment sticker count for user's active pack"""
    try:
        latest_pack = await get_user_active_pack(user_id)
        if latest_pack:
            await db.sticker_packs.update_one(
                {"short_name": latest_pack["short_name"]},
                {"$inc": {"sticker_count": 1}}
            )
            
            # Invalidate related caches
            cache_key = f"pack:{latest_pack['short_name']}"
            await safe_redis_delete(cache_key)
            await safe_redis_delete(f"user_active_pack:{user_id}")
            await safe_redis_delete(f"user_all_packs:{user_id}")
            
            return True
        return False
    except Exception as e:
        logger.error(f"Error incrementing sticker count: {e}")
        return False

async def update_pack_sticker_count(pack_short_name: str, count: int) -> bool:
    """Update pack sticker count"""
    try:
        await db.sticker_packs.update_one(
            {"short_name": pack_short_name},
            {"$set": {"sticker_count": count}}
        )
        
        cache_key = f"pack:{pack_short_name}"
        await safe_redis_delete(cache_key)
        
        pack = await db.sticker_packs.find_one({"short_name": pack_short_name}, {"user_id": 1})
        if pack:
            await safe_redis_delete(f"user_active_pack:{pack['user_id']}")
            await safe_redis_delete(f"user_all_packs:{pack['user_id']}")
        
        return True
    except Exception as e:
        logger.error(f"Error updating pack count {pack_short_name}: {e}")
        return False

async def delete_user_pack(user_id: int) -> bool:
    """Delete user's pack (legacy function - deletes one pack)"""
    try:
        result = await db.sticker_packs.delete_one({"user_id": user_id})
        
        await safe_redis_delete(f"user_active_pack:{user_id}")
        await safe_redis_delete(f"user_all_packs:{user_id}")
        await safe_redis_delete("total_packs_count")
        
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting user pack for {user_id}: {e}")
        return False

async def get_user_packs_paginated(user_id: int, page: int = 0, limit: int = 6):
    """Get paginated user packs"""
    try:
        skip = page * limit
        # ✅ FIX: Added projection
        cursor = db.sticker_packs.find(
            {"user_id": user_id},
            {"pack_name": 1, "short_name": 1, "sticker_count": 1, "created_at": 1}
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        packs = await cursor.to_list(length=limit)
        total = await db.sticker_packs.count_documents({"user_id": user_id})
        return packs, total
    except Exception as e:
        logger.error(f"Error getting paginated packs for user {user_id}: {e}")
        return [], 0

async def update_pack_name(short_name: str, new_pack_name: str) -> bool:
    """Update pack name"""
    try:
        result = await db.sticker_packs.update_one(
            {"short_name": short_name},
            {"$set": {"pack_name": new_pack_name}}
        )
        
        cache_key = f"pack:{short_name}"
        await safe_redis_delete(cache_key)
        
        pack = await db.sticker_packs.find_one({"short_name": short_name}, {"user_id": 1})
        if pack:
            await safe_redis_delete(f"user_active_pack:{pack['user_id']}")
            await safe_redis_delete(f"user_all_packs:{pack['user_id']}")
        
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error updating pack name {short_name}: {e}")
        return False

async def delete_pack_by_short_name(short_name: str) -> bool:
    """Delete pack by short name"""
    try:
        pack = await db.sticker_packs.find_one({"short_name": short_name}, {"user_id": 1})
        result = await db.sticker_packs.delete_one({"short_name": short_name})
        
        cache_key = f"pack:{short_name}"
        await safe_redis_delete(cache_key)
        
        if pack:
            await safe_redis_delete(f"user_active_pack:{pack['user_id']}")
            await safe_redis_delete(f"user_all_packs:{pack['user_id']}")
        
        await safe_redis_delete("total_packs_count")
        
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting pack {short_name}: {e}")
        return False

async def get_pack_by_short_name(short_name: str) -> Optional[Dict[str, Any]]:
    """Get pack by short name with caching"""
    try:
        cache_key = f"pack:{short_name}"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        pack = await db.sticker_packs.find_one({"short_name": short_name})
        
        if pack:
            await safe_redis_set(cache_key, serialize_doc(pack), REDIS_TTL_MEDIUM)
        
        return pack
    except Exception as e:
        logger.error(f"Error getting pack {short_name}: {e}")
        return None

async def get_pack_by_name(pack_name: str) -> Optional[Dict[str, Any]]:
    """Get pack by name (no caching - rarely used)"""
    try:
        return await db.sticker_packs.find_one({"pack_name": pack_name})
    except Exception as e:
        logger.error(f"Error getting pack by name {pack_name}: {e}")
        return None

# ✅ Published packs functions
async def is_pack_published(short_name: str) -> bool:
    """Check if pack is published with long-term caching"""
    try:
        cache_key = f"published:{short_name}"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return cached == "1"
        
        published_pack = await db.published_packs.find_one({"pack_short_name": short_name})
        result = published_pack is not None
        
        await safe_redis_set(cache_key, "1" if result else "0", REDIS_TTL_LONG)  # ✅ 24h cache
        
        return result
    except Exception as e:
        logger.error(f"Error checking if pack is published {short_name}: {e}")
        return False

async def create_published_pack(user_id: int, pack_short_name: str, keyword: str, first_sticker_id: str) -> bool:
    """Create published pack"""
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
        await safe_redis_set(cache_key, "1", REDIS_TTL_LONG)
        
        await safe_redis_delete(f"published_keyword:{keyword.lower()}")
        
        return True
    except Exception as e:
        logger.error(f"Error creating published pack for {pack_short_name}: {e}")
        return False

async def get_published_pack_by_keyword(keyword: str) -> Optional[Dict[str, Any]]:
    """Get published pack by keyword with medium-term caching"""
    try:
        cache_key = f"published_keyword:{keyword.lower()}"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        pack = await db.published_packs.find_one({"keyword": keyword.lower(), "is_active": True})
        
        if pack:
            await safe_redis_set(cache_key, serialize_doc(pack), REDIS_TTL_MEDIUM)
        
        return pack
    except Exception as e:
        logger.error(f"Error getting published pack by keyword {keyword}: {e}")
        return None

async def search_published_packs(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Search published packs by keyword prefix"""
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
    """Get published pack by short name"""
    try:
        cache_key = f"published_pack:{short_name}"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        pack = await db.published_packs.find_one({"pack_short_name": short_name, "is_active": True})
        
        if pack:
            await safe_redis_set(cache_key, serialize_doc(pack), REDIS_TTL_LONG)
        
        return pack
    except Exception as e:
        logger.error(f"Error getting published pack by short name {short_name}: {e}")
        return None

# ✅ AFK functions
async def get_afk_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get AFK user with short-term caching (AFK changes frequently)"""
    try:
        cache_key = f"afk:{user_id}"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return deserialize_doc(cached)
        
        afk_data = await db.afk.find_one({"user.id": user_id})
        
        if afk_data:
            await safe_redis_set(cache_key, serialize_doc(afk_data), REDIS_TTL_SHORT)  # ✅ 5min cache
        
        return afk_data
    except Exception as e:
        logger.error(f"Error getting AFK user {user_id}: {e}")
        return None

async def set_afk_user(user_id: int, first_name: str, reason: str, since: datetime):
    """Set user as AFK"""
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
        await safe_redis_set(cache_key, serialize_doc(afk_data), REDIS_TTL_SHORT)
    except Exception as e:
        logger.error(f"Error setting AFK user {user_id}: {e}")

async def remove_afk_user(user_id: int):
    """Remove user from AFK"""
    try:
        await db.afk.delete_one({"user.id": user_id})
        
        cache_key = f"afk:{user_id}"
        await safe_redis_delete(cache_key)
    except Exception as e:
        logger.error(f"Error removing AFK user {user_id}: {e}")

# ✅ Served chats functions
async def add_served_chat(chat_id: int) -> bool:
    """Add served chat"""
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
        
        await safe_redis_delete("served_chats_list")
        await safe_redis_delete("served_chats_count")
        
        return True
    except Exception as e:
        logger.error(f"Error adding served chat {chat_id}: {e}")
        return False

async def remove_served_chat(chat_id: int) -> bool:
    """Remove served chat"""
    try:
        await db.served_chats.delete_one({"chat_id": chat_id})
        
        await safe_redis_delete("served_chats_list")
        await safe_redis_delete("served_chats_count")
        
        return True
    except Exception as e:
        logger.error(f"Error removing served chat {chat_id}: {e}")
        return False

async def get_served_chats() -> List[Dict[str, Any]]:
    """Get all served chats with medium-term caching"""
    try:
        cache_key = "served_chats_list"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return [deserialize_doc(c) for c in json.loads(cached)]
        
        cursor = db.served_chats.find({})
        chats = await cursor.to_list(length=None)
        
        if chats:
            serialized_chats = [json.loads(serialize_doc(c)) for c in chats]
            await safe_redis_set(cache_key, json.dumps(serialized_chats), REDIS_TTL_MEDIUM)
        
        return chats
    except Exception as e:
        logger.error(f"Error getting served chats: {e}")
        return []

async def get_served_chats_count() -> int:
    """Get served chats count with medium-term caching"""
    try:
        cache_key = "served_chats_count"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return int(cached)
        
        count = await db.served_chats.count_documents({})
        
        await safe_redis_set(cache_key, str(count), REDIS_TTL_MEDIUM)
        
        return count
    except Exception as e:
        logger.error(f"Error getting served chats count: {e}")
        return 0

# ✅ GBan functions
async def add_banned_user(user_id: int) -> bool:
    """Add banned user"""
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
        await safe_redis_set(cache_key, "1", REDIS_TTL_LONG)  # ✅ Long cache for bans
        
        await safe_redis_delete("gbans_list")
        await safe_redis_delete("gbans_count")
        
        return True
    except Exception as e:
        logger.error(f"Error adding banned user {user_id}: {e}")
        return False

async def remove_banned_user(user_id: int) -> bool:
    """Remove banned user"""
    try:
        await db.gbans.delete_one({"user_id": user_id})
        
        cache_key = f"gban:{user_id}"
        await safe_redis_delete(cache_key)
        
        await safe_redis_delete("gbans_list")
        await safe_redis_delete("gbans_count")
        
        return True
    except Exception as e:
        logger.error(f"Error removing banned user {user_id}: {e}")
        return False

async def get_banned_users() -> List[int]:
    """Get all banned users with medium-term caching"""
    try:
        cache_key = "gbans_list"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        cursor = db.gbans.find({})
        banned_users = await cursor.to_list(length=None)
        user_ids = [user["user_id"] for user in banned_users]
        
        await safe_redis_set(cache_key, json.dumps(user_ids), REDIS_TTL_MEDIUM)
        
        return user_ids
    except Exception as e:
        logger.error(f"Error getting banned users: {e}")
        return []

async def get_banned_count() -> int:
    """Get banned users count with medium-term caching"""
    try:
        cache_key = "gbans_count"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return int(cached)
        
        count = await db.gbans.count_documents({})
        
        await safe_redis_set(cache_key, str(count), REDIS_TTL_MEDIUM)
        
        return count
    except Exception as e:
        logger.error(f"Error getting banned count: {e}")
        return 0

async def is_banned_user(user_id: int) -> bool:
    """Check if user is banned with long-term caching"""
    try:
        cache_key = f"gban:{user_id}"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return cached == "1"
        
        ban_data = await db.gbans.find_one({"user_id": user_id})
        result = ban_data is not None
        
        await safe_redis_set(cache_key, "1" if result else "0", REDIS_TTL_LONG)
        
        return result
    except Exception as e:
        logger.error(f"Error checking banned user {user_id}: {e}")
        return False

async def delete_user_packs(user_id: int) -> int:
    """Delete all packs for a user (used in gban)"""
    try:
        # ✅ FIX: Use delete_many instead of loop for better performance
        packs_cursor = db.sticker_packs.find({"user_id": user_id}, {"short_name": 1})
        packs = await packs_cursor.to_list(length=None)
        
        if not packs:
            return 0
        
        # Delete all packs in one operation
        result = await db.sticker_packs.delete_many({"user_id": user_id})
        deleted_count = result.deleted_count
        
        # Invalidate caches
        for pack in packs:
            cache_key = f"pack:{pack['short_name']}"
            await safe_redis_delete(cache_key)
        
        await safe_redis_delete(f"user_active_pack:{user_id}")
        await safe_redis_delete(f"user_all_packs:{user_id}")
        await safe_redis_delete("total_packs_count")
        
        return deleted_count
    except Exception as e:
        logger.error(f"Error deleting user packs for {user_id}: {e}")
        return 0

# ✅ Statistics functions
async def get_all_users() -> List[Dict[str, Any]]:
    """Get all users with short-term caching (for broadcast)"""
    try:
        cache_key = "all_users_list"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return [deserialize_doc(u) for u in json.loads(cached)]
        
        # ✅ FIX: Added projection to reduce data transfer
        cursor = db.users.find({}, {"user_id": 1, "username": 1, "first_name": 1})
        users = await cursor.to_list(length=None)
        
        if users:
            serialized_users = [json.loads(serialize_doc(u)) for u in users]
            await safe_redis_set(cache_key, json.dumps(serialized_users), REDIS_TTL_SHORT)  # ✅ 5min cache
        
        return users
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

async def get_total_users_count() -> int:
    """Get total users count with medium-term caching"""
    try:
        cache_key = "total_users_count"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return int(cached)
        
        count = await db.users.count_documents({})
        
        await safe_redis_set(cache_key, str(count), REDIS_TTL_MEDIUM)
        
        return count
    except Exception as e:
        logger.error(f"Error getting users count: {e}")
        return 0

async def get_total_packs_count() -> int:
    """Get total packs count with medium-term caching"""
    try:
        cache_key = "total_packs_count"
        cached = await safe_redis_get(cache_key)
        
        if cached:
            return int(cached)
        
        count = await db.sticker_packs.count_documents({})
        
        await safe_redis_set(cache_key, str(count), REDIS_TTL_MEDIUM)
        
        return count
    except Exception as e:
        logger.error(f"Error getting packs count: {e}")
        return 0

async def get_gbanned_users_count() -> int:
    """Get gbanned users count"""
    try:
        return await get_banned_count()
    except Exception as e:
        logger.error(f"Error getting gbanned count: {e}")
        return 0

async def get_user_pack(user_id: int) -> Optional[Dict[str, Any]]:
    """Legacy function - get user's active pack"""
    return await get_user_active_pack(user_id)

# ✅ NEW: Health check function for monitoring
async def check_database_health() -> Dict[str, Any]:
    """
    Check database and Redis health
    Returns status dict for monitoring
    """
    health = {
        "mongodb": {"status": "unknown", "latency_ms": 0},
        "redis": {"status": "unknown", "latency_ms": 0},
        "connection_pool": {"active": 0, "available": 0}
    }
    
    # Check MongoDB
    try:
        import time
        start = time.time()
        await client.admin.command('ping')
        latency = (time.time() - start) * 1000
        health["mongodb"] = {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        health["mongodb"] = {"status": "unhealthy", "error": str(e)}
        logger.error(f"MongoDB health check failed: {e}")
    
    # Check Redis
    try:
        start = time.time()
        await redis_client.ping()
        latency = (time.time() - start) * 1000
        health["redis"] = {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        health["redis"] = {"status": "unhealthy", "error": str(e)}
        logger.error(f"Redis health check failed: {e}")
    
    # Check connection pool stats (if available)
    try:
        pool_info = redis_client.connection_pool.get_connection_kwargs()
        health["connection_pool"] = {
            "max_connections": redis_client.connection_pool.max_connections,
            "status": "healthy"
        }
    except Exception as e:
        logger.error(f"Connection pool check failed: {e}")
    
    return health

# ✅ NEW: Cache statistics function
async def get_cache_stats() -> Dict[str, Any]:
    """Get Redis cache statistics"""
    try:
        info = await redis_client.info('memory')
        stats = await redis_client.info('stats')
        
        return {
            "used_memory_mb": round(info.get('used_memory', 0) / (1024 * 1024), 2),
            "max_memory_mb": round(info.get('maxmemory', 0) / (1024 * 1024), 2),
            "memory_usage_percent": round((info.get('used_memory', 0) / info.get('maxmemory', 1)) * 100, 2) if info.get('maxmemory') else 0,
            "total_keys": await redis_client.dbsize(),
            "hit_rate": round((stats.get('keyspace_hits', 0) / (stats.get('keyspace_hits', 0) + stats.get('keyspace_misses', 1))) * 100, 2),
            "evicted_keys": stats.get('evicted_keys', 0)
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {
            "error": str(e),
            "status": "unavailable"
        }
