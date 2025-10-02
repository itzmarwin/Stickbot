from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, Dict, Any
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
        
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

async def close_db():
    """Close database connection"""
    global client
    if client:
        client.close()

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
