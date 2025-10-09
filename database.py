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
    """Initialize database connection with proper timeout and pooling"""
    global client, db
    try:
        client = AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            maxPoolSize=50,
            minPoolSize=10
        )
        
        # Test connection
        await client.admin.command('ping')
        db = client[DATABASE_NAME]
        
        # Create indexes
        await db.users.create_index("user_id", unique=True)
        await db.sticker_packs.create_index("user_id")
        await db.sticker_packs.create_index("short_name", unique=True)
        await db.afk.create_index("user.id", unique=True)
        await db.gbans.create_index("user_id", unique=True)
        await db.served_chats.create_index("chat_id", unique=True)
        
        logger.info("Database initialized successfully")
        return db
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

async def close_db():
    """Close database connection"""
    global client
    if client:
        client.close()

def get_db():
    return db

# User operations
async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user from database"""
    try:
        return await db.users.find_one({"user_id": user_id})
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None

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
    try:
        return await db.sticker_packs.find_one({"user_id": user_id})
    except Exception as e:
        logger.error(f"Error getting user pack {user_id}: {e}")
        return None

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

async def delete_user_pack(user_id: int) -> bool:
    """Delete user's sticker pack from database"""
    try:
        result = await db.sticker_packs.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Error deleting user pack for {user_id}: {e}")
        return False

# AFK operations
async def get_afk_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get AFK data for a user"""
    try:
        return await db.afk.find_one({"user.id": user_id})
    except Exception as e:
        logger.error(f"Error getting AFK user {user_id}: {e}")
        return None

async def set_afk_user(user_id: int, first_name: str, reason: str, since: datetime):
    """Set AFK data for a user"""
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
    """Remove AFK data for a user"""
    try:
        await db.afk.delete_one({"user.id": user_id})
    except Exception as e:
        logger.error(f"Error removing AFK user {user_id}: {e}")

# Served Chats Operations
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

# GBan Operations
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

async def delete_user_packs(user_id: int) -> int:
    """Delete all sticker packs created by user"""
    try:
        packs_cursor = db.sticker_packs.find({"user_id": user_id})
        packs = await packs_cursor.to_list(length=None)
        deleted_count = len(packs)
        
        for pack in packs:
            await db.sticker_packs.delete_one({"_id": pack["_id"]})
            
        return deleted_count
    except Exception as e:
        logger.error(f"Error deleting user packs for {user_id}: {e}")
        return 0

# Broadcast functions
async def get_all_users() -> List[Dict[str, Any]]:
    """Get all users from database for broadcast"""
    try:
        cursor = db.users.find({})
        return await cursor.to_list(length=None)
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

# Statistics operations
async def get_total_users_count() -> int:
    """Get total users count"""
    try:
        return await db.users.count_documents({})
    except Exception as e:
        logger.error(f"Error getting users count: {e}")
        return 0

async def get_total_packs_count() -> int:
    """Get total packs count"""
    try:
        return await db.sticker_packs.count_documents({})
    except Exception as e:
        logger.error(f"Error getting packs count: {e}")
        return 0

async def get_gbanned_users_count() -> int:
    """Get total GBanned users count"""
    try:
        return await db.gbans.count_documents({})
    except Exception as e:
        logger.error(f"Error getting gbanned count: {e}")
        return 0
