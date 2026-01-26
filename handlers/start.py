"""
Start Handler - /start command and extra commands

Handles:
- /start command (private and group)
- Extra commands menu (AFK, Quotly, Stickers, MemeFi, Welcome)
- Back to main navigation
"""

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database import get_user, create_user, update_user_started
from templates import (
    START_MESSAGE_WITH_IMAGE, GROUP_START_MESSAGE, 
    EXTRA_COMMANDS_MESSAGE, AFK_INFO_MESSAGE,
    QUOTLY_INFO_MESSAGE, STICKERS_INFO_MESSAGE,
    MEMEFI_INFO_MESSAGE, WELCOME_INFO_MESSAGE,
    NEW_USER_LOG, HELP_MESSAGE
)
from utils.html_utils import escape_html
from config import BOT_USERNAME, LOG_GROUP_ID

# Import shared utilities
from handlers.keyboard_utils import (
    SharedCallbacks,
    get_main_menu_keyboard,
    get_group_start_keyboard,
    get_extra_commands_keyboard,
    get_back_to_extra_keyboard,
    get_back_to_main_keyboard,
    safe_edit_message
)

logger = logging.getLogger(__name__)
router = Router()


# ============================================================================
# START COMMAND
# ============================================================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """
    Handle /start command
    
    - In groups: Shows introduction with buttons
    - In private: Shows main menu with user greeting
    """
    user = message.from_user
    await state.clear()
    
    # Check if command is in group
    if message.chat.type in ["group", "supergroup"]:
        # Group start - show introduction with 2 buttons
        await message.reply(
            GROUP_START_MESSAGE.format(bot_username=BOT_USERNAME),
            reply_markup=get_group_start_keyboard()
        )
        return
    
    # Private chat - normal start flow
    user_data = await get_user(user.id)
    
    if not user_data:
        # New user - create in database
        await create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        
        # Log new user to admin group
        if LOG_GROUP_ID:
            try:
                log_msg = NEW_USER_LOG.format(
                    user_id=user.id,
                    username=user.username or "None",
                    first_name=user.first_name or "Unknown",
                    time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                )
                await message.bot.send_message(LOG_GROUP_ID, log_msg)
            except Exception as e:
                logger.error(f"Error sending new user log: {e}")
    else:
        # Existing user - update started status
        await update_user_started(user.id)
    
    # Send start message with main menu
    start_text = START_MESSAGE_WITH_IMAGE.format(
        user_id=user.id,
        first_name=escape_html(user.first_name)
    )
    
    await message.answer(start_text, reply_markup=get_main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    await message.answer(HELP_MESSAGE)


# ============================================================================
# EXTRA COMMANDS MENU
# ============================================================================

@router.callback_query(F.data == SharedCallbacks.EXTRA_COMMANDS)
async def extra_commands_callback(callback: CallbackQuery):
    """Show extra commands menu"""
    await callback.answer()
    try:
        await safe_edit_message(
            callback, 
            EXTRA_COMMANDS_MESSAGE, 
            get_extra_commands_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in extra_commands_callback: {e}")


# ============================================================================
# EXTRA COMMAND INFO HANDLERS
# ============================================================================

@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_AFK)
async def extra_afk_callback(callback: CallbackQuery):
    """Show AFK feature information"""
    await callback.answer()
    try:
        await safe_edit_message(
            callback, 
            AFK_INFO_MESSAGE, 
            get_back_to_extra_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in extra_afk_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_QUOTLY)
async def extra_quotly_callback(callback: CallbackQuery):
    """Show Quotly feature information"""
    await callback.answer()
    try:
        await safe_edit_message(
            callback, 
            QUOTLY_INFO_MESSAGE, 
            get_back_to_extra_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in extra_quotly_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_STICKERS)
async def extra_stickers_callback(callback: CallbackQuery):
    """Show Stickers feature information"""
    await callback.answer()
    try:
        await safe_edit_message(
            callback, 
            STICKERS_INFO_MESSAGE, 
            get_back_to_extra_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in extra_stickers_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_MEMEFI)
async def extra_memefi_callback(callback: CallbackQuery):
    """Show MemeFi feature information"""
    await callback.answer()
    try:
        await safe_edit_message(
            callback, 
            MEMEFI_INFO_MESSAGE, 
            get_back_to_extra_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in extra_memefi_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_WELCOME)
async def extra_welcome_callback(callback: CallbackQuery):
    """Show Welcome feature information"""
    await callback.answer()
    try:
        await safe_edit_message(
            callback, 
            WELCOME_INFO_MESSAGE, 
            get_back_to_extra_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in extra_welcome_callback: {e}")


# ============================================================================
# NAVIGATION - BACK TO MAIN
# ============================================================================

@router.callback_query(F.data == SharedCallbacks.BACK_TO_MAIN)
async def back_to_main_callback(callback: CallbackQuery):
    """Navigate back to main menu"""
    await callback.answer()
    
    try:
        user = callback.from_user
        start_text = START_MESSAGE_WITH_IMAGE.format(
            user_id=user.id,
            first_name=escape_html(user.first_name)
        )
        await safe_edit_message(
            callback, 
            start_text, 
            get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in back_to_main_callback: {e}")
