import json
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import MONGO_URI, DATABASE_NAME

logger = logging.getLogger(__name__)

client: Optional[AsyncIOMotorClient] = None
db = None


async def init_db():
    """
    Initialize MongoDB connection with optimized settings
    """
    global client, db
    try:
        # ✅ Optimized connection pool for 10K+ users
        client = AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            maxPoolSize=200,
            minPoolSize=50,
            waitQueueTimeoutMS=10000,
            retryWrites=True,
            retryReads=True,
            maxIdleTimeMS=45000
        )
        
        # Test connection
        await client.admin.command('ping')
        db = client[DATABASE_NAME]
        
        # ✅ Create optimized indexes
        logger.info("Creating database indexes...")
        
        # User indexes (added language index)
        await db.users.create_index("user_id", unique=True)
        await db.users.create_index([("username", 1)])
        await db.users.create_index([("created_at", -1)])
        await db.users.create_index([("has_started", 1)])
        await db.users.create_index([("language", 1)])  # NEW: Language index
        
        # Sticker pack indexes
        await db.sticker_packs.create_index("user_id")
        await db.sticker_packs.create_index("short_name", unique=True)
        await db.sticker_packs.create_index([("user_id", 1), ("created_at", -1)])
        await db.sticker_packs.create_index([("sticker_count", 1)])
        
        # AFK indexes
        await db.afk.create_index("user.id", unique=True)
        await db.afk.create_index([("since", 1)])
        
        # GBan indexes
        await db.gbans.create_index("user_id", unique=True)
        await db.gbans.create_index([("banned_at", -1)])
        
        # Served chats indexes
        await db.served_chats.create_index("chat_id", unique=True)
        await db.served_chats.create_index([("added_at", -1)])
        
        # Published packs indexes
        await db.published_packs.create_index("pack_short_name", unique=True)
        await db.published_packs.create_index([("keyword", 1), ("is_active", 1)])
        await db.published_packs.create_index([("user_id", 1)])
        await db.published_packs.create_index([("published_at", -1)])
        
        logger.info("✅ Database indexes created successfully")
        logger.info("✅ Database initialized successfully")
        return db
        
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)
        raise


async def close_db():
    """
    Graceful shutdown with proper cleanup
    """
    global client
    try:
        if client:
            logger.info("Closing MongoDB connection...")
            client.close()
        
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")


def get_db():
    """Get database instance"""
    return db


# ============================================================================
# USER FUNCTIONS
# ============================================================================

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by ID"""
    try:
        user = await db.users.find_one({"user_id": user_id})
        return user
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None


async def create_user(user_id: int, username: Optional[str] = None, 
                     first_name: Optional[str] = None, language: str = "en") -> bool:
    """Create new user with language preference"""
    try:
        user_data = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "created_at": datetime.utcnow(),
            "has_started": True,
            "language": language  # NEW: Default language
        }
        await db.users.insert_one(user_data)
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
        return True
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        return False


async def get_all_users() -> List[Dict[str, Any]]:
    """Get all users (for broadcast)"""
    try:
        cursor = db.users.find({}, {"user_id": 1, "username": 1, "first_name": 1})
        users = await cursor.to_list(length=None)
        return users
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []


async def get_total_users_count() -> int:
    """Get total users count"""
    try:
        count = await db.users.count_documents({})
        return count
    except Exception as e:
        logger.error(f"Error getting users count: {e}")
        return 0


# ============================================================================
# LANGUAGE FUNCTIONS (NEW)
# ============================================================================

async def get_user_language(user_id: int) -> str:
    """
    Get user's language preference
    Returns: "en" | "rus" | "bur"
    Default: "en"
    """
    try:
        user = await db.users.find_one({"user_id": user_id}, {"language": 1})
        if user and "language" in user:
            return user["language"]
        return "en"  # Default fallback
    except Exception as e:
        logger.error(f"Error getting user language {user_id}: {e}")
        return "en"


async def set_user_language(user_id: int, language: str) -> bool:
    """
    Set user's language preference
    Args:
        user_id: User's Telegram ID
        language: "en" | "rus" | "bur"
    """
    try:
        # Validate language
        if language not in ["en", "rus", "bur"]:
            logger.warning(f"Invalid language {language} for user {user_id}, defaulting to 'en'")
            language = "en"
        
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"language": language}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error setting language for user {user_id}: {e}")
        return False


async def update_user_language(user_id: int, language: str) -> bool:
    """
    Update existing user's language
    Alias for set_user_language
    """
    return await set_user_language(user_id, language)


# ============================================================================
# STICKER PACK FUNCTIONS
# ============================================================================

async def get_user_active_pack(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user's most recent pack"""
    try:
        cursor = db.sticker_packs.find(
            {"user_id": user_id},
            {"pack_name": 1, "short_name": 1, "sticker_count": 1, "created_at": 1, "pack_link": 1}
        ).sort("created_at", -1).limit(1)
        
        packs = await cursor.to_list(length=1)
        pack = packs[0] if packs else None
        return pack
    except Exception as e:
        logger.error(f"Error getting user active pack {user_id}: {e}")
        return None


async def get_user_all_packs(user_id: int) -> List[Dict[str, Any]]:
    """Get all user packs"""
    try:
        cursor = db.sticker_packs.find(
            {"user_id": user_id},
            {"pack_name": 1, "short_name": 1, "sticker_count": 1, "created_at": 1, "pack_link": 1}
        ).sort("created_at", -1)
        
        packs = await cursor.to_list(length=None)
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
        return True
    except Exception as e:
        logger.error(f"Error updating pack count {pack_short_name}: {e}")
        return False


async def delete_user_pack(user_id: int) -> bool:
    """Delete user's pack (legacy function - deletes one pack)"""
    try:
        result = await db.sticker_packs.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting user pack for {user_id}: {e}")
        return False


async def get_user_packs_paginated(user_id: int, page: int = 0, limit: int = 6):
    """Get paginated user packs"""
    try:
        skip = page * limit
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
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error updating pack name {short_name}: {e}")
        return False


async def delete_pack_by_short_name(short_name: str) -> bool:
    """Delete pack by short name"""
    try:
        result = await db.sticker_packs.delete_one({"short_name": short_name})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting pack {short_name}: {e}")
        return False


async def get_pack_by_short_name(short_name: str) -> Optional[Dict[str, Any]]:
    """Get pack by short name"""
    try:
        pack = await db.sticker_packs.find_one({"short_name": short_name})
        return pack
    except Exception as e:
        logger.error(f"Error getting pack {short_name}: {e}")
        return None


async def get_pack_by_name(pack_name: str) -> Optional[Dict[str, Any]]:
    """Get pack by name"""
    try:
        return await db.sticker_packs.find_one({"pack_name": pack_name})
    except Exception as e:
        logger.error(f"Error getting pack by name {pack_name}: {e}")
        return None


async def delete_user_packs(user_id: int) -> int:
    """Delete all packs for a user (used in gban)"""
    try:
        result = await db.sticker_packs.delete_many({"user_id": user_id})
        deleted_count = result.deleted_count
        return deleted_count
    except Exception as e:
        logger.error(f"Error deleting user packs for {user_id}: {e}")
        return 0


async def get_total_packs_count() -> int:
    """Get total packs count"""
    try:
        count = await db.sticker_packs.count_documents({})
        return count
    except Exception as e:
        logger.error(f"Error getting packs count: {e}")
        return 0


async def get_user_pack(user_id: int) -> Optional[Dict[str, Any]]:
    """Legacy function - get user's active pack"""
    return await get_user_active_pack(user_id)


# ============================================================================
# PUBLISHED PACKS FUNCTIONS
# ============================================================================

async def is_pack_published(short_name: str) -> bool:
    """Check if pack is published"""
    try:
        published_pack = await db.published_packs.find_one({"pack_short_name": short_name})
        result = published_pack is not None
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
        return True
    except Exception as e:
        logger.error(f"Error creating published pack for {pack_short_name}: {e}")
        return False


async def get_published_pack_by_keyword(keyword: str) -> Optional[Dict[str, Any]]:
    """Get published pack by keyword"""
    try:
        pack = await db.published_packs.find_one({"keyword": keyword.lower(), "is_active": True})
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
        pack = await db.published_packs.find_one({"pack_short_name": short_name, "is_active": True})
        return pack
    except Exception as e:
        logger.error(f"Error getting published pack by short name {short_name}: {e}")
        return None


# ============================================================================
# AFK FUNCTIONS
# ============================================================================

async def get_afk_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get AFK user"""
    try:
        afk_data = await db.afk.find_one({"user.id": user_id})
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
    except Exception as e:
        logger.error(f"Error setting AFK user {user_id}: {e}")


async def remove_afk_user(user_id: int):
    """Remove user from AFK"""
    try:
        await db.afk.delete_one({"user.id": user_id})
    except Exception as e:
        logger.error(f"Error removing AFK user {user_id}: {e}")


# ============================================================================
# SERVED CHATS FUNCTIONS
# ============================================================================

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
        return True
    except Exception as e:
        logger.error(f"Error adding served chat {chat_id}: {e}")
        return False


async def remove_served_chat(chat_id: int) -> bool:
    """Remove served chat"""
    try:
        await db.served_chats.delete_one({"chat_id": chat_id})
        return True
    except Exception as e:
        logger.error(f"Error removing served chat {chat_id}: {e}")
        return False


async def get_served_chats() -> List[Dict[str, Any]]:
    """Get all served chats"""
    try:
        cursor = db.served_chats.find({})
        chats = await cursor.to_list(length=None)
        return chats
    except Exception as e:
        logger.error(f"Error getting served chats: {e}")
        return []


async def get_served_chats_count() -> int:
    """Get served chats count"""
    try:
        count = await db.served_chats.count_documents({})
        return count
    except Exception as e:
        logger.error(f"Error getting served chats count: {e}")
        return 0


# ============================================================================
# GBAN FUNCTIONS
# ============================================================================

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
        return True
    except Exception as e:
        logger.error(f"Error adding banned user {user_id}: {e}")
        return False


async def remove_banned_user(user_id: int) -> bool:
    """Remove banned user"""
    try:
        await db.gbans.delete_one({"user_id": user_id})
        return True
    except Exception as e:
        logger.error(f"Error removing banned user {user_id}: {e}")
        return False


async def get_banned_users() -> List[int]:
    """Get all banned users"""
    try:
        cursor = db.gbans.find({})
        banned_users = await cursor.to_list(length=None)
        user_ids = [user["user_id"] for user in banned_users]
        return user_ids
    except Exception as e:
        logger.error(f"Error getting banned users: {e}")
        return []


async def get_banned_count() -> int:
    """Get banned users count"""
    try:
        count = await db.gbans.count_documents({})
        return count
    except Exception as e:
        logger.error(f"Error getting banned count: {e}")
        return 0


async def is_banned_user(user_id: int) -> bool:
    """Check if user is banned"""
    try:
        ban_data = await db.gbans.find_one({"user_id": user_id})
        result = ban_data is not None
        return result
    except Exception as e:
        logger.error(f"Error checking banned user {user_id}: {e}")
        return False


async def get_gbanned_users_count() -> int:
    """Get gbanned users count"""
    try:
        return await get_banned_count()
    except Exception as e:
        logger.error(f"Error getting gbanned count: {e}")
        return 0


# ============================================================================
# HEALTH CHECK FUNCTION
# ============================================================================

async def check_database_health() -> Dict[str, Any]:
    """
    Check database health
    Returns status dict for monitoring
    """
    health = {
        "mongodb": {"status": "unknown", "latency_ms": 0}
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
    
    return health
