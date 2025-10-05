from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

from config import MONGO_URI, DATABASE_NAME

logger = logging.getLogger(__name__)

# MongoDB client
client: Optional[AsyncIOMotorClient] = None
db = None

async def init_db():
    """Initialize database connection"""
    global client, db
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client[DATABASE_NAME]
        
        # Create indexes
        await db.users.create_index("user_id", unique=True)
        await db.sticker_packs.create_index("user_id")
        await db.sticker_packs.create_index("short_name", unique=True)
        await db.afk.create_index("user.id", unique=True)
        await db.gbans.create_index("user_id", unique=True)
        await db.served_chats.create_index("chat_id", unique=True)  # Add served_chats index
        
        logger.info("Database initialized successfully")
        return db  # Return db instance
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

async def close_db():
    """Close database connection"""
    global client
    if client:
        client.close()

# Get database instance
def get_db():
    """Get database instance"""
    return db

# User operations
async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user from database"""
    return await db.users.find_one({"user_id": user_id})

async def create_user(user_id: int, username: Optional[str] = None, 
                     first_name: Optional[str] = None) -> bool:
    """Create new user"""
    try:
        user_data = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "created_at": datetime.utcnow(),
            "has_started": True
        }
        await db.users.insert_one(user_data)
        return True
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")
        return False

async def update_user_started(user_id: int) -> bool:
    """Update user's has_started status"""
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

# Sticker pack operations
async def get_user_pack(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user's sticker pack"""
    return await db.sticker_packs.find_one({"user_id": user_id})

async def create_sticker_pack(user_id: int, pack_name: str, 
                             short_name: str) -> bool:
    """Create new sticker pack record"""
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
    """Increment sticker count in pack"""
    try:
        await db.sticker_packs.update_one(
            {"user_id": user_id},
            {"$inc": {"sticker_count": 1}}
        )
        return True
    except Exception as e:
        logger.error(f"Error incrementing sticker count: {e}")
        return False

# AFK operations
async def get_afk_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get AFK data for a user"""
    return await db.afk.find_one({"user.id": user_id})

async def set_afk_user(user_id: int, first_name: str, reason: str, since: datetime):
    """Set AFK data for a user"""
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

async def remove_afk_user(user_id: int):
    """Remove AFK data for a user"""
    await db.afk.delete_one({"user.id": user_id})

# ==================== SERVED CHATS OPERATIONS ====================
async def add_served_chat(chat_id: int, chat_title: str = ""):
    """Add chat to served chats list"""
    try:
        chat_data = {
            "chat_id": chat_id,
            "chat_title": chat_title,
            "added_at": datetime.utcnow()
        }
        await db.served_chats.update_one(
            {"chat_id": chat_id},
            {"$set": chat_data},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error adding served chat: {e}")
        return False

async def remove_served_chat(chat_id: int):
    """Remove chat from served chats list"""
    try:
        await db.served_chats.delete_one({"chat_id": chat_id})
        return True
    except Exception as e:
        logger.error(f"Error removing served chat: {e}")
        return False

async def get_served_chats():
    """Get all served chats"""
    try:
        cursor = db.served_chats.find({})
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error(f"Error getting served chats: {e}")
        return []

async def get_served_chats_count() -> int:
    """Get total served chats count"""
    try:
        return await db.served_chats.count_documents({})
    except Exception as e:
        logger.error(f"Error counting served chats: {e}")
        return 0

# ==================== NEW GBAN OPERATIONS (PROVIDED CODE STYLE) ====================
async def add_banned_user(user_id: int, reason: str = ""):
    """Add user to banned list (provided code style)"""
    try:
        banned_data = {
            "user_id": user_id,
            "reason": reason,
            "banned_at": datetime.utcnow()
        }
        await db.gbans.update_one(
            {"user_id": user_id},
            {"$set": banned_data},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error adding banned user: {e}")
        return False

async def remove_banned_user(user_id: int):
    """Remove user from banned list (provided code style)"""
    try:
        await db.gbans.delete_one({"user_id": user_id})
        return True
    except Exception as e:
        logger.error(f"Error removing banned user: {e}")
        return False

async def get_banned_count() -> int:
    """Get total banned users count (provided code style)"""
    try:
        return await db.gbans.count_documents({})
    except Exception as e:
        logger.error(f"Error getting banned count: {e}")
        return 0

async def get_banned_users():
    """Get all banned users (provided code style)"""
    try:
        cursor = db.gbans.find({})
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error(f"Error getting banned users: {e}")
        return []

# ==================== EXISTING GBAN OPERATIONS (KEEP FOR COMPATIBILITY) ====================
async def get_gban_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get GBan data for a user"""
    return await db.gbans.find_one({"user_id": user_id})

async def set_gban_user(user_id: int, reason: str, banned_by: int, 
                       packs_deleted: int = 0, groups_banned: int = 0) -> bool:
    """Set GBan data for a user"""
    try:
        gban_data = {
            "user_id": user_id,
            "reason": reason,
            "banned_by": banned_by,
            "packs_deleted": packs_deleted,
            "groups_banned": groups_banned,
            "banned_at": datetime.utcnow()
        }
        await db.gbans.update_one(
            {"user_id": user_id},
            {"$set": gban_data},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error setting GBan for user {user_id}: {e}")
        return False

async def update_gban_stats(user_id: int, packs_deleted: int = None, groups_banned: int = None):
    """Update GBan statistics"""
    update_data = {}
    if packs_deleted is not None:
        update_data["packs_deleted"] = packs_deleted
    if groups_banned is not None:
        update_data["groups_banned"] = groups_banned
    
    if update_data:
        await db.gbans.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )

async def is_user_gbanned(user_id: int) -> bool:
    """Check if user is globally banned"""
    gban_data = await db.gbans.find_one({"user_id": user_id})
    return gban_data is not None

# ==================== STATISTICS OPERATIONS ====================
async def get_all_users() -> list:
    """Get all users"""
    cursor = db.users.find({})
    return await cursor.to_list(length=None)

async def get_total_users_count() -> int:
    """Get total users count"""
    return await db.users.count_documents({})

async def get_total_packs_count() -> int:
    """Get total packs count"""
    return await db.sticker_packs.count_documents({})

async def get_gbanned_users_count() -> int:
    """Get total GBanned users count"""
    return await db.gbans.count_documents({})
