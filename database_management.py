import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, DuplicateKeyError, OperationFailure
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import MONGO_URI_MANAGEMENT, DATABASE_NAME_MANAGEMENT

logger = logging.getLogger(__name__)

DB_MAX_POOL_SIZE = 20
DB_MIN_POOL_SIZE = 2
DB_MAX_IDLE_TIME_MS = 45000
DB_SERVER_SELECTION_TIMEOUT_MS = 5000
DB_CONNECT_TIMEOUT_MS = 10000
DB_SOCKET_TIMEOUT_MS = 30000
DB_WAIT_QUEUE_TIMEOUT_MS = 10000

CURRENT_SCHEMA_VERSION = 1
SCHEMA_COLLECTION = "schema_version"

DEFAULT_AUTO_DELETE_SECONDS = 600

management_client: Optional[AsyncIOMotorClient] = None
management_db = None


async def init_management_db():
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
        
        try:
            await management_client.admin.command('ping')
        except ServerSelectionTimeoutError as e:
            logger.error(f"❌ Cannot reach MongoDB server: {e}")
            raise
        except ConnectionFailure as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            raise
        
        management_db = management_client[DATABASE_NAME_MANAGEMENT]
        
        await _check_and_migrate_schema()
        await _create_indexes()
        
        logger.info("✅ Management database initialized successfully")
        logger.info(f"✅ Schema version: {CURRENT_SCHEMA_VERSION}")
        
        return management_db
        
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"❌ Database connection error: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected database initialization error: {e}", exc_info=True)
        raise


async def _create_indexes():
    try:
        await management_db.welcome_settings.create_index("chat_id", unique=True, name="idx_chat_id")
        await management_db.welcome_settings.create_index([("chat_id", 1), ("welcome.enabled", 1)], name="idx_chat_welcome")
        await management_db.welcome_settings.create_index([("updated_at", 1)], name="idx_updated_at")
        logger.info("✅ Database indexes created")
    except OperationFailure as e:
        logger.error(f"❌ Index creation failed: {e}")
        raise


async def _get_current_schema_version() -> int:
    try:
        version_doc = await management_db[SCHEMA_COLLECTION].find_one({"_id": "current"})
        if version_doc:
            return version_doc.get("version", 0)
        return 0
    except Exception as e:
        logger.error(f"Error getting schema version: {e}")
        return 0


async def _set_schema_version(version: int) -> bool:
    try:
        await management_db[SCHEMA_COLLECTION].update_one(
            {"_id": "current"},
            {"$set": {"version": version, "updated_at": datetime.utcnow()}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error setting schema version: {e}")
        return False


async def _check_and_migrate_schema():
    current_version = await _get_current_schema_version()
    
    if current_version == CURRENT_SCHEMA_VERSION:
        return
    
    logger.info(f"🔄 Schema migration: v{current_version} → v{CURRENT_SCHEMA_VERSION}")
    
    for version in range(current_version + 1, CURRENT_SCHEMA_VERSION + 1):
        try:
            if version == 1:
                await _migrate_to_v1()
            
            await _set_schema_version(version)
            logger.info(f"✅ Migrated to v{version}")
        except Exception as e:
            logger.error(f"❌ Migration to v{version} failed, stopping: {e}")
            raise


async def _migrate_to_v1():
    try:
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
            
            if "auto_delete" not in doc.get("welcome", {}):
                update_fields["welcome.auto_delete"] = {"enabled": False, "delete_after": None}
            
            if "auto_delete" not in doc.get("goodbye", {}):
                update_fields["goodbye.auto_delete"] = {"enabled": False, "delete_after": None}
            
            if "created_at" not in doc:
                update_fields["created_at"] = datetime.utcnow()
            
            if "updated_at" not in doc:
                update_fields["updated_at"] = datetime.utcnow()
            
            if update_fields:
                await management_db.welcome_settings.update_one({"chat_id": chat_id}, {"$set": update_fields})
                migrated += 1
        
        logger.info(f"✅ Migrated {migrated} documents to v1 schema")
        
    except Exception as e:
        logger.error(f"❌ Migration to v1 failed: {e}")
        raise


async def close_management_db():
    global management_client
    
    try:
        if management_client:
            management_client.close()
            logger.info("✅ Management database connection closed")
    except Exception as e:
        logger.error(f"❌ Error closing management database: {e}")


def get_management_db():
    if management_db is None:
        logger.error("❌ Database not initialized! Call init_management_db() first.")
    return management_db


async def get_welcome_settings(chat_id: int) -> Optional[Dict[str, Any]]:
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
                "auto_delete": {"enabled": False, "delete_after": None}
            },
            "goodbye": {
                "enabled": False,
                "custom_set": False,
                "media_type": None,
                "media_id": None,
                "text": None,
                "buttons": [],
                "auto_delete": {"enabled": False, "delete_after": None}
            },
            "created_at": now,
            "updated_at": now
        }
        
        await management_db.welcome_settings.insert_one(default_settings)
        return True
        
    except DuplicateKeyError:
        return True
    except OperationFailure as e:
        logger.error(f"❌ Database operation failed for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error creating default settings for chat {chat_id}: {e}")
        return False


async def update_welcome_status(chat_id: int, enabled: bool) -> bool:
    try:
        await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {"welcome.enabled": enabled, "updated_at": datetime.utcnow()}},
            upsert=True
        )
        return True
    except OperationFailure as e:
        logger.error(f"❌ Failed to update welcome status for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error updating welcome status for chat {chat_id}: {e}")
        return False


async def update_goodbye_status(chat_id: int, enabled: bool) -> bool:
    try:
        await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {"goodbye.enabled": enabled, "updated_at": datetime.utcnow()}},
            upsert=True
        )
        return True
    except OperationFailure as e:
        logger.error(f"❌ Failed to update goodbye status for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error updating goodbye status for chat {chat_id}: {e}")
        return False


async def set_custom_welcome(
    chat_id: int,
    media_type: Optional[str],
    media_id: Optional[str],
    text: str,
    buttons: Optional[List[Dict]] = None
) -> bool:
    if buttons is None:
        buttons = []
    
    try:
        await management_db.welcome_settings.update_one(
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
    buttons: Optional[List[Dict]] = None
) -> bool:
    if buttons is None:
        buttons = []
    
    try:
        await management_db.welcome_settings.update_one(
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
        return True
    except OperationFailure as e:
        logger.error(f"❌ Failed to set custom goodbye for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error setting custom goodbye for chat {chat_id}: {e}")
        return False


async def delete_custom_welcome(chat_id: int) -> bool:
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
        
        if result.modified_count > 0:
            return True
        else:
            return False
    except OperationFailure as e:
        logger.error(f"❌ Failed to delete custom welcome for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error deleting custom welcome for chat {chat_id}: {e}")
        return False


async def delete_custom_goodbye(chat_id: int) -> bool:
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
        
        if result.modified_count > 0:
            return True
        else:
            return False
    except OperationFailure as e:
        logger.error(f"❌ Failed to delete custom goodbye for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error deleting custom goodbye for chat {chat_id}: {e}")
        return False


async def update_welcome_auto_delete(chat_id: int, enabled: bool, delete_after: Optional[int] = None) -> bool:
    try:
        if enabled and delete_after is None:
            delete_after = DEFAULT_AUTO_DELETE_SECONDS
        
        update_data = {
            "welcome.auto_delete.enabled": enabled,
            "welcome.auto_delete.delete_after": delete_after if enabled else None,
            "updated_at": datetime.utcnow()
        }
        
        await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {"$set": update_data},
            upsert=True
        )
        return True
    except OperationFailure as e:
        logger.error(f"❌ Failed to update welcome auto-delete for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error updating welcome auto-delete for chat {chat_id}: {e}")
        return False


async def update_goodbye_auto_delete(chat_id: int, enabled: bool, delete_after: Optional[int] = None) -> bool:
    try:
        if enabled and delete_after is None:
            delete_after = DEFAULT_AUTO_DELETE_SECONDS
        
        update_data = {
            "goodbye.auto_delete.enabled": enabled,
            "goodbye.auto_delete.delete_after": delete_after if enabled else None,
            "updated_at": datetime.utcnow()
        }
        
        await management_db.welcome_settings.update_one(
            {"chat_id": chat_id},
            {"$set": update_data},
            upsert=True
        )
        return True
    except OperationFailure as e:
        logger.error(f"❌ Failed to update goodbye auto-delete for chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error updating goodbye auto-delete for chat {chat_id}: {e}")
        return False


async def check_management_db_health() -> Dict[str, Any]:
    health = {"management_db": {"status": "unknown", "latency_ms": 0}}
    
    try:
        import time
        start = time.time()
        await management_client.admin.command('ping')
        latency = (time.time() - start) * 1000
        
        health["management_db"] = {
            "status": "healthy",
            "latency_ms": round(latency, 2),
            "schema_version": CURRENT_SCHEMA_VERSION
        }
    except ServerSelectionTimeoutError as e:
        health["management_db"] = {"status": "timeout", "error": str(e)}
    except ConnectionFailure as e:
        health["management_db"] = {"status": "connection_failed", "error": str(e)}
    except Exception as e:
        health["management_db"] = {"status": "unhealthy", "error": str(e)}
    
    return health


async def get_enabled_chats(message_type: str) -> List[int]:
    try:
        field = f"{message_type}.enabled"
        cursor = management_db.welcome_settings.find({field: True}, {"chat_id": 1})
        chat_ids = [doc["chat_id"] async for doc in cursor]
        return chat_ids
    except Exception as e:
        logger.error(f"❌ Error getting enabled chats for {message_type}: {e}")
        return []


logger.info("✅ Management database module loaded")
