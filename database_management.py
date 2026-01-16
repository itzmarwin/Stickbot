"""
Management Database Module
Handles all group management features database operations
Separate from sticker database for scalability
"""
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import MONGO_URI_MANAGEMENT, DATABASE_NAME_MANAGEMENT

logger = logging.getLogger(__name__)

# Global database variables
management_client: Optional[AsyncIOMotorClient] = None
management_db = None


async def init_management_db():
    """
    Initialize Management MongoDB connection
    """
    global management_client, management_db
    try:
        management_client = AsyncIOMotorClient(
            MONGO_URI_MANAGEMENT,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            maxPoolSize=100,
            minPoolSize=10,
            waitQueueTimeoutMS=10000,
            retryWrites=True,
            retryReads=True
        )
        
        # Test connection
        await management_client.admin.command('ping')
        management_db = management_client[DATABASE_NAME_MANAGEMENT]
        
        # Create indexes
        logger.info("Creating management database indexes...")
        
        # Welcome settings indexes
        await management_db.welcome_settings.create_index("chat_id", unique=True)
        
        logger.info("✅ Management database initialized successfully")
        return management_db
        
    except Exception as e:
        logger.error(f"❌ Management database initialization error: {e}", exc_info=True)
        raise


async def close_management_db():
    """
    Graceful shutdown for management database
    """
    global management_client
    try:
        if management_client:
            logger.info("Closing management MongoDB connection...")
            management_client.close()
        
        logger.info("✅ Management database connection closed")
    except Exception as e:
        logger.error(f"Error closing management database: {e}")


def get_management_db():
    """Get management database instance"""
    return management_db


# ============================================================================
# WELCOME/GOODBYE FUNCTIONS
# ============================================================================

async def get_welcome_settings(chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Get welcome/goodbye settings for a chat
    
    Args:
        chat_id: Chat ID
        
    Returns:
        Settings dict or None if not found
    """
    try:
        settings = await management_db.welcome_settings.find_one({"chat_id": chat_id})
        return settings
    except Exception as e:
        logger.error(f"Error getting welcome settings for chat {chat_id}: {e}")
        return None


async def create_default_welcome_settings(chat_id: int) -> bool:
    """
    Create default welcome/goodbye settings for a new chat
    
    Args:
        chat_id: Chat ID
        
    Returns:
        True if successful
    """
    try:
        default_settings = {
            "chat_id": chat_id,
            "welcome": {
                "enabled": False,
                "custom_set": False,
                "media_type": None,
                "media_id": None,
                "text": None,
                "buttons": [],
                "default_text": "Welcome {MENTION} to {GROUPNAME}!"  # ✅ FIXED
            },
            "goodbye": {
                "enabled": False,
                "custom_set": False,
                "media_type": None,
                "media_id": None,
                "text": None,
                "buttons": [],
                "default_text": "Goodbye {NAME}!"  # ✅ FIXED
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await management_db.welcome_settings.insert_one(default_settings)
        logger.info(f"Created default welcome settings for chat {chat_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating default settings for chat {chat_id}: {e}")
        return False


async def update_welcome_status(chat_id: int, enabled: bool) -> bool:
    """
    Enable/disable welcome messages
    
    Args:
        chat_id: Chat ID
        enabled: True to enable, False to disable
        
    Returns:
        True if successful
    """
    try:
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "welcome.enabled": enabled,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error updating welcome status for chat {chat_id}: {e}")
        return False


async def update_goodbye_status(chat_id: int, enabled: bool) -> bool:
    """
    Enable/disable goodbye messages
    
    Args:
        chat_id: Chat ID
        enabled: True to enable, False to disable
        
    Returns:
        True if successful
    """
    try:
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "goodbye.enabled": enabled,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error updating goodbye status for chat {chat_id}: {e}")
        return False


async def set_custom_welcome(chat_id: int, media_type: Optional[str], 
                            media_id: Optional[str], text: str, 
                            buttons: List[Dict] = []) -> bool:
    """
    Set custom welcome message
    
    Args:
        chat_id: Chat ID
        media_type: Type of media (photo/video/animation) or None
        media_id: Telegram file_id or None
        text: Welcome text/caption
        buttons: List of button dicts
        
    Returns:
        True if successful
    """
    try:
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "welcome.custom_set": True,
                    "welcome.media_type": media_type,
                    "welcome.media_id": media_id,
                    "welcome.text": text,
                    "welcome.buttons": buttons,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        logger.info(f"Set custom welcome for chat {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Error setting custom welcome for chat {chat_id}: {e}")
        return False


async def set_custom_goodbye(chat_id: int, media_type: Optional[str], 
                            media_id: Optional[str], text: str, 
                            buttons: List[Dict] = []) -> bool:
    """
    Set custom goodbye message
    
    Args:
        chat_id: Chat ID
        media_type: Type of media (photo/video/animation) or None
        media_id: Telegram file_id or None
        text: Goodbye text/caption
        buttons: List of button dicts
        
    Returns:
        True if successful
    """
    try:
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "goodbye.custom_set": True,
                    "goodbye.media_type": media_type,
                    "goodbye.media_id": media_id,
                    "goodbye.text": text,
                    "goodbye.buttons": buttons,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        logger.info(f"Set custom goodbye for chat {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Error setting custom goodbye for chat {chat_id}: {e}")
        return False


async def delete_custom_welcome(chat_id: int) -> bool:
    """
    Delete custom welcome and disable welcome
    
    Args:
        chat_id: Chat ID
        
    Returns:
        True if successful
    """
    try:
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "welcome.enabled": False,
                    "welcome.custom_set": False,
                    "welcome.media_type": None,
                    "welcome.media_id": None,
                    "welcome.text": None,
                    "welcome.buttons": [],
                    "updated_at": datetime.utcnow()
                }
            }
        )
        logger.info(f"Deleted custom welcome for chat {chat_id}")
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error deleting custom welcome for chat {chat_id}: {e}")
        return False


async def delete_custom_goodbye(chat_id: int) -> bool:
    """
    Delete custom goodbye and disable goodbye
    
    Args:
        chat_id: Chat ID
        
    Returns:
        True if successful
    """
    try:
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "goodbye.enabled": False,
                    "goodbye.custom_set": False,
                    "goodbye.media_type": None,
                    "goodbye.media_id": None,
                    "goodbye.text": None,
                    "goodbye.buttons": [],
                    "updated_at": datetime.utcnow()
                }
            }
        )
        logger.info(f"Deleted custom goodbye for chat {chat_id}")
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error deleting custom goodbye for chat {chat_id}: {e}")
        return False


# ============================================================================
# HEALTH CHECK
# ============================================================================

async def check_management_db_health() -> Dict[str, Any]:
    """
    Check management database health
    Returns status dict for monitoring
    """
    health = {
        "management_db": {"status": "unknown", "latency_ms": 0}
    }
    
    try:
        import time
        start = time.time()
        await management_client.admin.command('ping')
        latency = (time.time() - start) * 1000
        health["management_db"] = {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        health["management_db"] = {"status": "unhealthy", "error": str(e)}
        logger.error(f"Management DB health check failed: {e}")
    
    return health
