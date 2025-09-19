import asyncio
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo.errors import ServerSelectionTimeoutError
from config import settings
import logging

logger = logging.getLogger(__name__)


class MongoDB:
    """MongoDB connection manager"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None
        self.users_collection: Optional[AsyncIOMotorCollection] = None
    
    async def connect(self) -> None:
        """Establish connection to MongoDB"""
        try:
            # Build connection URI
            if settings.MONGO_USERNAME and settings.MONGO_PASSWORD:
                # With authentication
                uri = f"mongodb://{settings.MONGO_USERNAME}:{settings.MONGO_PASSWORD}@{settings.MONGO_URI.replace('mongodb://', '')}"
            else:
                # Without authentication
                uri = settings.MONGO_URI
            
            # Create client
            self.client = AsyncIOMotorClient(
                uri,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                maxPoolSize=10,
                minPoolSize=1
            )
            
            # Test connection
            await self.client.admin.command('ping')
            
            # Set database and collections
            self.database = self.client[settings.MONGO_DB_NAME]
            self.users_collection = self.database.users
            
            # Create indexes for better performance
            await self._create_indexes()
            
            logger.info(f"Connected to MongoDB: {settings.MONGO_DB_NAME}")
            
        except ServerSelectionTimeoutError as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")
    
    async def _create_indexes(self) -> None:
        """Create database indexes for optimization"""
        if self.users_collection is not None:
            # Index on user_id and bot_id combination for faster queries
            await self.users_collection.create_index([
                ("user_id", 1),
                ("bot_id", 1)
            ], unique=True)
            
            # Index on pack short names for faster pack lookups
            await self.users_collection.create_index("packs.pack_short_name")
            
            logger.info("Database indexes created successfully")
    
    def get_users_collection(self) -> AsyncIOMotorCollection:
        """Get users collection"""
        if self.users_collection is None:
            raise RuntimeError("Database not connected")
        return self.users_collection


# Global MongoDB instance
mongodb = MongoDB()


async def init_database() -> None:
    """Initialize database connection"""
    await mongodb.connect()


async def close_database() -> None:
    """Close database connection"""
    await mongodb.disconnect()


def get_database() -> MongoDB:
    """Get database instance"""
    return mongodb
