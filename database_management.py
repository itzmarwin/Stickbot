"""
Management Database Module
Handles all group management features database operations
Separate from sticker database for scalability

FIXES APPLIED:
- Issue #9: Auto-delete default consistency
- Issue #27: Index optimization
- Issue #28: Schema migration strategy
- Issue #29: Updated_at consistency
- Issue #30: Mutable default arguments
- Issue #32: Magic numbers → Constants
- Issue #33: Specific exception handling
"""
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
    DuplicateKeyError,
    OperationFailure
)
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import MONGO_URI_MANAGEMENT, DATABASE_NAME_MANAGEMENT

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS (Fix Issue #32 - Magic Numbers)
# ============================================================================

# Connection Pool Settings
DB_MAX_POOL_SIZE = 20
DB_MIN_POOL_SIZE = 2
DB_MAX_IDLE_TIME_MS = 45000
DB_SERVER_SELECTION_TIMEOUT_MS = 5000
DB_CONNECT_TIMEOUT_MS = 10000
DB_SOCKET_TIMEOUT_MS = 30000
DB_WAIT_QUEUE_TIMEOUT_MS = 10000

# Schema Version (Fix Issue #28 - Migration Strategy)
CURRENT_SCHEMA_VERSION = 1
SCHEMA_COLLECTION = "schema_version"

# Default Messages
DEFAULT_WELCOME_TEXT = "Welcome {MENTION} Hope you have a great time here."
DEFAULT_GOODBYE_TEXT = "Goodbye {MENTION} We hope to see you again."

# Auto-delete defaults (Fix Issue #9 - Import from utils would be circular, so define here)
DEFAULT_AUTO_DELETE_SECONDS = 600  # 10 minutes

# ============================================================================
# Global database variables
# ============================================================================

management_client: Optional[AsyncIOMotorClient] = None
management_db = None


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

async def init_management_db():
    """
    Initialize Management MongoDB connection
    
    FIXES:
        - Issue #27: Optimized index strategy
        - Issue #28: Schema versioning
        - Issue #32: Constants instead of magic numbers
        - Issue #33: Specific exception handling
    """
    global management_client, management_db
    
    try:
        management_client = AsyncIOMotorClient(
            MONGO_URI_MANAGEMENT,
            serverSelectionTimeoutMS=DB_SERVER_SELECTION_TIMEOUT_MS,
            connectTimeoutMS=DB_CONNECT_TIMEOUT_MS,
            socketTimeoutMS=DB_SOCKET_TIMEOUT_MS,
            maxPoolSize=DB_MAX_POOL_SIZE,
            minPoolSize=DB_MIN_POOL_SIZE,
            waitQueueTimeoutMS=DB_WAIT_QUEUE_TIMEOUT_MS,
            maxIdleTimeMS=DB_MAX_IDLE_TIME_MS,
            retryWrites=True,
            retryReads=True
        )
        
        # Test connection (Fix Issue #33 - Specific exceptions)
        try:
            await management_client.admin.command('ping')
        except ServerSelectionTimeoutError as e:
            logger.error(f"❌ Cannot reach MongoDB server: {e}")
            raise
        except ConnectionFailure as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            raise
        
        management_db = management_client[DATABASE_NAME_MANAGEMENT]
        
        # Check and perform migrations (Fix Issue #28)
        await _check_and_migrate_schema()
        
        # Create optimized indexes (Fix Issue #27)
        await _create_indexes()
        
        logger.info("✅ Management database initialized successfully")
        logger.info(f"✅ Connection pool: max={DB_MAX_POOL_SIZE}, min={DB_MIN_POOL_SIZE}, idle_timeout={DB_MAX_IDLE_TIME_MS}ms")
        logger.info(f"✅ Schema version: {CURRENT_SCHEMA_VERSION}")
        
        return management_db
        
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"❌ Database connection error: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected database initialization error: {e}", exc_info=True)
        raise


async def _create_indexes():
    """
    Create database indexes with optimized strategy
    
    FIXES:
        - Issue #27: Reduced index overhead
        - Only essential indexes for read-heavy operations
    """
    logger.info("Creating management database indexes...")
    
    try:
        # PRIMARY INDEX: Unique chat_id (ESSENTIAL)
        await management_db.welcome_settings.create_index(
            "chat_id",
            unique=True,
            name="idx_chat_id"
        )
        
        # REMOVED: Separate enabled status indexes (Issue #27)
        # These caused write overhead for minimal read benefit
        # Queries for enabled chats are rare (only during bulk operations)
        
        # COMPOUND INDEX: For common query pattern (chat_id + enabled check)
        # Only ONE compound index instead of multiple
        await management_db.welcome_settings.create_index(
            [("chat_id", 1), ("welcome.enabled", 1)],
            name="idx_chat_welcome"
        )
        
        # OPTIONAL: Updated_at index for cleanup operations (kept for maintenance)
        await management_db.welcome_settings.create_index(
            [("updated_at", 1)],
            name="idx_updated_at",
        )
        
        logger.info("✅ Optimized indexes created (3 total instead of 6)")
        
    except OperationFailure as e:
        logger.error(f"❌ Index creation failed: {e}")
        raise


# ============================================================================
# SCHEMA MIGRATION (Fix Issue #28)
# ============================================================================

async def _get_current_schema_version() -> int:
    """Get current schema version from database"""
    try:
        version_doc = await management_db[SCHEMA_COLLECTION].find_one({"_id": "current"})
        if version_doc:
            return version_doc.get("version", 0)
        return 0
    except Exception as e:
        logger.error(f"Error getting schema version: {e}")
        return 0


async def _set_schema_version(version: int) -> bool:
    """Set schema version in database"""
    try:
        await management_db[SCHEMA_COLLECTION].update_one(
            {"_id": "current"},
            {
                "$set": {
                    "version": version,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error setting schema version: {e}")
        return False


async def _check_and_migrate_schema():
    """
    Check schema version and run migrations if needed
    
    FIXES:
        - Issue #28: Migration strategy implementation
    """
    current_version = await _get_current_schema_version()
    
    if current_version == CURRENT_SCHEMA_VERSION:
        logger.info(f"✅ Schema up to date (v{current_version})")
        return
    
    logger.info(f"🔄 Schema migration needed: v{current_version} → v{CURRENT_SCHEMA_VERSION}")
    
    # Run migrations sequentially
    for version in range(current_version + 1, CURRENT_SCHEMA_VERSION + 1):
        logger.info(f"Running migration to v{version}...")
        
        if version == 1:
            await _migrate_to_v1()
        # Add future migrations here:
        # elif version == 2:
        #     await _migrate_to_v2()
        
        await _set_schema_version(version)
        logger.info(f"✅ Migrated to v{version}")


async def _migrate_to_v1():
    """
    Migration to schema version 1
    
    Ensures all existing documents have:
    - auto_delete fields
    - created_at and updated_at
    - default values
    """
    logger.info("📦 Migrating existing documents to v1 schema...")
    
    try:
        # Find documents without auto_delete structure
        cursor = management_db.welcome_settings.find({
            "$or": [
                {"welcome.auto_delete": {"$exists": False}},
                {"goodbye.auto_delete": {"$exists": False}}
            ]
        })
        
        migrated = 0
        async for doc in cursor:
            chat_id = doc["chat_id"]
            
            update_fields = {}
            
            # Add auto_delete if missing
            if "auto_delete" not in doc.get("welcome", {}):
                update_fields["welcome.auto_delete"] = {
                    "enabled": False,
                    "delete_after": None
                }
            
            if "auto_delete" not in doc.get("goodbye", {}):
                update_fields["goodbye.auto_delete"] = {
                    "enabled": False,
                    "delete_after": None
                }
            
            # Add timestamps if missing (Fix Issue #29)
            if "created_at" not in doc:
                update_fields["created_at"] = datetime.utcnow()
            
            if "updated_at" not in doc:
                update_fields["updated_at"] = datetime.utcnow()
            
            if update_fields:
                await management_db.welcome_settings.update_one(
                    {"chat_id": chat_id},
                    {"$set": update_fields}
                )
                migrated += 1
        
        logger.info(f"✅ Migrated {migrated} documents to v1 schema")
        
    except Exception as e:
        logger.error(f"❌ Migration to v1 failed: {e}")
        raise


# ============================================================================
# CONNECTION MANAGEMENT
# ============================================================================

async def close_management_db():
    """
    Graceful shutdown for management database
    
    FIXES:
        - Issue #33: Specific exception handling
    """
    global management_client
    
    try:
        if management_client:
            logger.info("Closing management MongoDB connection...")
            management_client.close()
            logger.info("✅ Management database connection closed")
    except Exception as e:
        logger.error(f"❌ Error closing management database: {e}")


def get_management_db():
    """Get management database instance"""
    if management_db is None:
        logger.error("❌ Database not initialized! Call init_management_db() first.")
    return management_db


# ============================================================================
# WELCOME/GOODBYE SETTINGS
# ============================================================================

async def get_welcome_settings(chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Get welcome/goodbye settings for a chat
    
    Args:
        chat_id: Chat ID
        
    Returns:
        Settings dict or None if not found
        
    FIXES:
        - Issue #33: Specific exception handling
    """
    try:
        settings = await management_db.welcome_settings.find_one({"chat_id": chat_id})
        return settings
        
    except OperationFailure as e:
        logger.error(f"❌ Database operation failed for chat {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error getting welcome settings for chat {chat_id}: {e}")
        return None


async def create_default_welcome_settings(chat_id: int) -> bool:
    """
    Create default welcome/goodbye settings for a new chat
    
    Args:
        chat_id: Chat ID
        
    Returns:
        True if successful
        
    FIXES:
        - Issue #9: Use constant for default auto-delete
        - Issue #29: Always set updated_at
        - Issue #32: Use defined constants
        - Issue #33: Specific exception handling
    """
    try:
        now = datetime.utcnow()
        
        default_settings = {
            "chat_id": chat_id,
            "welcome": {
                "enabled": False,
                "custom_set": False,
                "media_type": None,
                "media_id": None,
                "text": None,
                "buttons": [],
                "default_text": DEFAULT_WELCOME_TEXT,
                "auto_delete": {
                    "enabled": False,
                    "delete_after": None
                }
            },
            "goodbye": {
                "enabled": False,
                "custom_set": False,
                "media_type": None,
                "media_id": None,
                "text": None,
                "buttons": [],
                "default_text": DEFAULT_GOODBYE_TEXT,
                "auto_delete": {
                    "enabled": False,
                    "delete_after": None
                }
            },
            "created_at": now,
            "updated_at": now  # Fix Issue #29
        }
        
        await management_db.welcome_settings.insert_one(default_settings)
        logger.info(f"✅ Created default welcome settings for chat {chat_id}")
        return True
        
    except DuplicateKeyError:
        logger.warning(f"⚠️ Settings already exist for chat {chat_id}")
        return True  # Not an error, settings exist
    except OperationFailure as e:
        logger.error(f"❌ Database operation failed for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error creating default settings for chat {chat_id}: {e}")
        return False


# ============================================================================
# STATUS UPDATES
# ============================================================================

async def update_welcome_status(chat_id: int, enabled: bool) -> bool:
    """
    Enable/disable welcome messages
    
    Args:
        chat_id: Chat ID
        enabled: True to enable, False to disable
        
    Returns:
        True if successful
        
    FIXES:
        - Issue #29: Always update updated_at
        - Issue #33: Specific exception handling
    """
    try:
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "welcome.enabled": enabled,
                    "updated_at": datetime.utcnow()  # Fix Issue #29
                }
            },
            upsert=True
        )
        
        logger.info(f"✅ Welcome {'enabled' if enabled else 'disabled'} for chat {chat_id}")
        return True
        
    except OperationFailure as e:
        logger.error(f"❌ Failed to update welcome status for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error updating welcome status for chat {chat_id}: {e}")
        return False


async def update_goodbye_status(chat_id: int, enabled: bool) -> bool:
    """
    Enable/disable goodbye messages
    
    Args:
        chat_id: Chat ID
        enabled: True to enable, False to disable
        
    Returns:
        True if successful
        
    FIXES:
        - Issue #29: Always update updated_at
        - Issue #33: Specific exception handling
    """
    try:
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "goodbye.enabled": enabled,
                    "updated_at": datetime.utcnow()  # Fix Issue #29
                }
            },
            upsert=True
        )
        
        logger.info(f"✅ Goodbye {'enabled' if enabled else 'disabled'} for chat {chat_id}")
        return True
        
    except OperationFailure as e:
        logger.error(f"❌ Failed to update goodbye status for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error updating goodbye status for chat {chat_id}: {e}")
        return False


# ============================================================================
# CUSTOM MESSAGE SETTERS
# ============================================================================

async def set_custom_welcome(
    chat_id: int,
    media_type: Optional[str],
    media_id: Optional[str],
    text: str,
    buttons: Optional[List[Dict]] = None  # Fix Issue #30
) -> bool:
    """
    Set custom welcome message
    
    Args:
        chat_id: Chat ID
        media_type: Type of media (photo/video/animation) or None
        media_id: Telegram file_id or None
        text: Welcome text/caption
        buttons: List of button dicts (default: None)
        
    Returns:
        True if successful
        
    FIXES:
        - Issue #29: Always update updated_at
        - Issue #30: Mutable default argument
        - Issue #33: Specific exception handling
    """
    if buttons is None:
        buttons = []
    
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
                    "updated_at": datetime.utcnow()  # Fix Issue #29
                }
            },
            upsert=True
        )
        
        logger.info(f"✅ Set custom welcome for chat {chat_id}")
        return True
        
    except OperationFailure as e:
        logger.error(f"❌ Failed to set custom welcome for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error setting custom welcome for chat {chat_id}: {e}")
        return False


async def set_custom_goodbye(
    chat_id: int,
    media_type: Optional[str],
    media_id: Optional[str],
    text: str,
    buttons: Optional[List[Dict]] = None  # Fix Issue #30
) -> bool:
    """
    Set custom goodbye message
    
    Args:
        chat_id: Chat ID
        media_type: Type of media (photo/video/animation) or None
        media_id: Telegram file_id or None
        text: Goodbye text/caption
        buttons: List of button dicts (default: None)
        
    Returns:
        True if successful
        
    FIXES:
        - Issue #29: Always update updated_at
        - Issue #30: Mutable default argument
        - Issue #33: Specific exception handling
    """
    if buttons is None:
        buttons = []
    
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
                    "updated_at": datetime.utcnow()  # Fix Issue #29
                }
            },
            upsert=True
        )
        
        logger.info(f"✅ Set custom goodbye for chat {chat_id}")
        return True
        
    except OperationFailure as e:
        logger.error(f"❌ Failed to set custom goodbye for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error setting custom goodbye for chat {chat_id}: {e}")
        return False


# ============================================================================
# CUSTOM MESSAGE DELETERS
# ============================================================================

async def delete_custom_welcome(chat_id: int) -> bool:
    """
    Delete custom welcome and disable welcome
    
    Args:
        chat_id: Chat ID
        
    Returns:
        True if successful
        
    FIXES:
        - Issue #29: Always update updated_at
        - Issue #33: Specific exception handling
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
                    "updated_at": datetime.utcnow()  # Fix Issue #29
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"✅ Deleted custom welcome for chat {chat_id}")
            return True
        else:
            logger.warning(f"⚠️ No custom welcome found for chat {chat_id}")
            return False
            
    except OperationFailure as e:
        logger.error(f"❌ Failed to delete custom welcome for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error deleting custom welcome for chat {chat_id}: {e}")
        return False


async def delete_custom_goodbye(chat_id: int) -> bool:
    """
    Delete custom goodbye and disable goodbye
    
    Args:
        chat_id: Chat ID
        
    Returns:
        True if successful
        
    FIXES:
        - Issue #29: Always update updated_at
        - Issue #33: Specific exception handling
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
                    "updated_at": datetime.utcnow()  # Fix Issue #29
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"✅ Deleted custom goodbye for chat {chat_id}")
            return True
        else:
            logger.warning(f"⚠️ No custom goodbye found for chat {chat_id}")
            return False
            
    except OperationFailure as e:
        logger.error(f"❌ Failed to delete custom goodbye for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error deleting custom goodbye for chat {chat_id}: {e}")
        return False


# ============================================================================
# AUTO-DELETE FUNCTIONS
# ============================================================================

async def update_welcome_auto_delete(
    chat_id: int,
    enabled: bool,
    delete_after: Optional[int] = None
) -> bool:
    """
    Update welcome auto-delete settings
    
    Args:
        chat_id: Chat ID
        enabled: True to enable auto-delete, False to disable
        delete_after: Seconds after which to delete (None if disabled)
        
    Returns:
        True if successful
        
    FIXES:
        - Issue #9: Use constant for default value
        - Issue #29: Always update updated_at
        - Issue #32: Use defined constant
        - Issue #33: Specific exception handling
    """
    try:
        # Fix Issue #9: Consistent default
        if enabled and delete_after is None:
            delete_after = DEFAULT_AUTO_DELETE_SECONDS
        
        update_data = {
            "welcome.auto_delete.enabled": enabled,
            "welcome.auto_delete.delete_after": delete_after if enabled else None,
            "updated_at": datetime.utcnow()  # Fix Issue #29
        }
        
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {"$set": update_data},
            upsert=True
        )
        
        logger.info(f"✅ Updated welcome auto-delete for chat {chat_id}: enabled={enabled}, delete_after={delete_after}")
        return True
        
    except OperationFailure as e:
        logger.error(f"❌ Failed to update welcome auto-delete for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error updating welcome auto-delete for chat {chat_id}: {e}")
        return False


async def update_goodbye_auto_delete(
    chat_id: int,
    enabled: bool,
    delete_after: Optional[int] = None
) -> bool:
    """
    Update goodbye auto-delete settings
    
    Args:
        chat_id: Chat ID
        enabled: True to enable auto-delete, False to disable
        delete_after: Seconds after which to delete (None if disabled)
        
    Returns:
        True if successful
        
    FIXES:
        - Issue #9: Use constant for default value
        - Issue #29: Always update updated_at
        - Issue #32: Use defined constant
        - Issue #33: Specific exception handling
    """
    try:
        # Fix Issue #9: Consistent default
        if enabled and delete_after is None:
            delete_after = DEFAULT_AUTO_DELETE_SECONDS
        
        update_data = {
            "goodbye.auto_delete.enabled": enabled,
            "goodbye.auto_delete.delete_after": delete_after if enabled else None,
            "updated_at": datetime.utcnow()  # Fix Issue #29
        }
        
        result = await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {"$set": update_data},
            upsert=True
        )
        
        logger.info(f"✅ Updated goodbye auto-delete for chat {chat_id}: enabled={enabled}, delete_after={delete_after}")
        return True
        
    except OperationFailure as e:
        logger.error(f"❌ Failed to update goodbye auto-delete for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error updating goodbye auto-delete for chat {chat_id}: {e}")
        return False


# ============================================================================
# HEALTH CHECK
# ============================================================================

async def check_management_db_health() -> Dict[str, Any]:
    """
    Check management database health
    
    Returns:
        Status dict for monitoring
        
    FIXES:
        - Issue #32: Use constants
        - Issue #33: Specific exception handling
    """
    health = {
        "management_db": {"status": "unknown", "latency_ms": 0}
    }
    
    try:
        import time
        start = time.time()
        await management_client.admin.command('ping')
        latency = (time.time() - start) * 1000
        
        pool_stats = {
            "max_pool_size": DB_MAX_POOL_SIZE,
            "min_pool_size": DB_MIN_POOL_SIZE,
            "idle_timeout_ms": DB_MAX_IDLE_TIME_MS
        }
        
        health["management_db"] = {
            "status": "healthy",
            "latency_ms": round(latency, 2),
            "pool": pool_stats,
            "schema_version": CURRENT_SCHEMA_VERSION
        }
        
    except ServerSelectionTimeoutError as e:
        health["management_db"] = {"status": "timeout", "error": str(e)}
        logger.error(f"❌ Management DB health check timeout: {e}")
    except ConnectionFailure as e:
        health["management_db"] = {"status": "connection_failed", "error": str(e)}
        logger.error(f"❌ Management DB health check connection failed: {e}")
    except Exception as e:
        health["management_db"] = {"status": "unhealthy", "error": str(e)}
        logger.error(f"❌ Management DB health check failed: {e}")
    
    return health


# ============================================================================
# BULK OPERATIONS (Fix Issue #23 - Future-ready)
# ============================================================================

async def get_enabled_chats(message_type: str) -> List[int]:
    """
    Get all chats with welcome/goodbye enabled
    
    Args:
        message_type: 'welcome' or 'goodbye'
        
    Returns:
        List of chat IDs
        
    NOTE: Useful for bulk operations/notifications
    """
    try:
        field = f"{message_type}.enabled"
        cursor = management_db.welcome_settings.find(
            {field: True},
            {"chat_id": 1}
        )
        
        chat_ids = [doc["chat_id"] async for doc in cursor]
        return chat_ids
        
    except Exception as e:
        logger.error(f"❌ Error getting enabled chats for {message_type}: {e}")
        return []


logger.info("✅ Management database module loaded")
