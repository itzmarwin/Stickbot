from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from config import settings
from utils import is_private_chat
from middlewares import DatabaseOperations
import logging

logger = logging.getLogger(__name__)

# Create router for start command
start_router = Router()


@start_router.message(Command("start"))
async def start_command(message: Message, db_operations: DatabaseOperations):
    """
    Handle /start command - only works in private chat
    Marks user as started and shows welcome message
    """
    
    # Check if command is used in private chat
    if not is_private_chat(message):
        # Silently ignore /start in groups to avoid spam
        logger.info(f"User {message.from_user.id} tried to use /start in group {message.chat.id}")
        return
    
    try:
        # Get or create user data and mark as started
        user_data = await db_operations.get_or_create_user_data()
        user_data.mark_started()  # Mark user as started
        await db_operations.save_user_data(user_data)
        
        # Send welcome message
        await message.answer(
            text=settings.WELCOME_MESSAGE,
            parse_mode="Markdown"
        )
        
        logger.info(f"User {message.from_user.id} started the bot and was marked as started")
        
    except Exception as e:
        logger.error(f"Error in start command for user {message.from_user.id}: {e}")
        
        # Send generic error message
        await message.answer(
            "Sorry, something went wrong. Please try again later."
        )
