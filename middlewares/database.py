from typing import Callable, Dict, Any, Awaitable, Optional
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from database import get_database, UserData
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """
    Middleware that provides database operations for handlers
    Adds user data to handler context and provides save functionality
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Get user from event
        user: Optional[User] = data.get("event_from_user")
        if not user:
            # No user in event, continue without database operations
            return await handler(event, data)

        # Get bot info
        bot = data.get("bot")
        if not bot:
            logger.error("Bot not found in middleware data")
            return await handler(event, data)

        # Get bot ID
        bot_info = await bot.get_me()
        bot_id = bot_info.id

        # Add database operations to data
        data["db_operations"] = DatabaseOperations(user.id, bot_id)
        
        return await handler(event, data)


class DatabaseOperations:
    """Database operations helper for handlers"""
    
    def __init__(self, user_id: int, bot_id: int):
        self.user_id = user_id
        self.bot_id = bot_id
        self.db = get_database()
    
    async def get_user_data(self) -> Optional[UserData]:
        """Get user data from database"""
        try:
            collection = self.db.get_users_collection()
            
            # Find user document
            doc = await collection.find_one({
                "user_id": self.user_id,
                "bot_id": self.bot_id
            })
            
            if doc:
                return UserData.from_dict(doc)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user data for user {self.user_id}: {e}")
            return None
    
    async def save_user_data(self, user_data: UserData) -> bool:
        """Save user data to database"""
        try:
            collection = self.db.get_users_collection()
            
            # Convert to dict for MongoDB
            doc = user_data.to_dict()
            
            # Use upsert to insert or update
            result = await collection.replace_one(
                {
                    "user_id": self.user_id,
                    "bot_id": self.bot_id
                },
                doc,
                upsert=True
            )
            
            logger.info(f"Saved user data for user {self.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving user data for user {self.user_id}: {e}")
            return False
    
    async def create_user_data(self) -> UserData:
        """Create new user data instance"""
        return UserData(
            user_id=self.user_id,
            bot_id=self.bot_id,
            packs=[]
        )
    
    async def get_or_create_user_data(self) -> UserData:
        """Get existing user data or create new one"""
        user_data = await self.get_user_data()
        
        if user_data is None:
            user_data = await self.create_user_data()
            # Save the new user data
            await self.save_user_data(user_data)
        
        return user_data
