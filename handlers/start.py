from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database import get_user, create_user, update_user_started
from templates import START_MESSAGE, HELP_MESSAGE
from config import LOG_GROUP_ID, BOT_USERNAME
from datetime import datetime

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command"""
    user = message.from_user
    
    # Clear any existing FSM state
    await state.clear()
    
    # Check if user exists
    user_data = await get_user(user.id)
    
    if not user_data:
        # Create new user
        await create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        
        # Send log to logger group if this is a new user
        if LOG_GROUP_ID:
            try:
                from templates import NEW_USER_LOG
                log_msg = NEW_USER_LOG.format(
                    user_id=user.id,
                    username=user.username or "None",
                    first_name=user.first_name or "Unknown",
                    time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                )
                await message.bot.send_message(LOG_GROUP_ID, log_msg)
            except Exception as e:
                pass
    else:
        # Update has_started status
        await update_user_started(user.id)
    
    await message.answer(START_MESSAGE)

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    await message.answer(HELP_MESSAGE)
