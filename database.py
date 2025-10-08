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
        await db.served_chats.create_index("chat_id", unique=True)  # NEW: For served chats tracking
        
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

# ==================== NEW GBAN SYSTEM DATABASE FUNCTIONS ====================

# Served Chats Operations (for tracking groups where bot is added)
async def add_served_chat(chat_id: int) -> bool:
    """Add chat to served chats list"""
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
    """Remove chat from served chats list"""
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
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error(f"Error getting served chats: {e}")
        return []

async def get_served_chats_count() -> int:
    """Get total served chats count"""
    try:
        return await db.served_chats.count_documents({})
    except Exception as e:
        logger.error(f"Error getting served chats count: {e}")
        return 0

# New GBan Operations (for new GBan system)
async def add_banned_user(user_id: int) -> bool:
    """Add user to banned users list"""
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
    """Remove user from banned users list"""
    try:
        await db.gbans.delete_one({"user_id": user_id})
        return True
    except Exception as e:
        logger.error(f"Error removing banned user {user_id}: {e}")
        return False

async def get_banned_users() -> List[int]:
    """Get all banned user IDs"""
    try:
        cursor = db.gbans.find({})
        banned_users = await cursor.to_list(length=None)
        return [user["user_id"] for user in banned_users]
    except Exception as e:
        logger.error(f"Error getting banned users: {e}")
        return []

async def get_banned_count() -> int:
    """Get total banned users count"""
    try:
        return await db.gbans.count_documents({})
    except Exception as e:
        logger.error(f"Error getting banned count: {e}")
        return 0

async def is_banned_user(user_id: int) -> bool:
    """Check if user is banned"""
    try:
        ban_data = await db.gbans.find_one({"user_id": user_id})
        return ban_data is not None
    except Exception as e:
        logger.error(f"Error checking banned user {user_id}: {e}")
        return False

# Pack deletion function for GBan system
async def delete_user_packs(user_id: int) -> int:
    """
    Delete all sticker packs created by user and return count of deleted packs
    """
    try:
        # Get all packs by user
        packs_cursor = db.sticker_packs.find({"user_id": user_id})
        packs = await packs_cursor.to_list(length=None)
        
        deleted_count = len(packs)
        
        # Delete all packs
        for pack in packs:
            await db.sticker_packs.delete_one({"_id": pack["_id"]})
            logger.info(f"🗑️ Deleted pack for GBanned user {user_id}: {pack.get('pack_name', 'Unknown')}")
            
        return deleted_count
    except Exception as e:
        logger.error(f"Error deleting user packs for {user_id}: {e}")
        return 0

# ==================== BROADCAST SYSTEM FUNCTIONS ====================

async def get_all_users() -> List[Dict[str, Any]]:
    """Get all users from database for broadcast"""
    try:
        cursor = db.users.find({})
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

# ==================== OLD GBAN FUNCTIONS (KEPT FOR COMPATIBILITY) ====================

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

async def get_all_gbanned_users() -> List[Dict[str, Any]]:
    """Get all globally banned users"""
    cursor = db.gbans.find({})
    return await cursor.to_list(length=None)

# Statistics operations
async def get_total_users_count() -> int:
    """Get total users count"""
    return await db.users.count_documents({})

async def get_total_packs_count() -> int:
    """Get total packs count"""
    return await db.sticker_packs.count_documents({})

async def get_gbanned_users_count() -> int:
    """Get total GBanned users count"""
    return await db.gbans.count_documents({})
