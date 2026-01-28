"""
Start Handler - /start command and extra commands

Handles:
- /start command (private and group)
- Language selection for new users
- Extra commands menu (AFK, Quotly, Stickers, MemeFi, Welcome)
- Back to main navigation
"""

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database import get_user, create_user, update_user_started, get_user_language
from utils.language import get_text
from utils.html_utils import escape_html
from config import BOT_USERNAME, LOG_GROUP_ID

# Import language handler
from handlers.language import show_language_selection_for_new_user

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
    
    - In groups: Shows introduction with buttons (English only)
    - In private: Shows language selection for new users, then main menu
    """
    user = message.from_user
    await state.clear()
    
    # Check if command is in group
    if message.chat.type in ["group", "supergroup"]:
        # Group start - show introduction with 2 buttons (ENGLISH ONLY)
        group_start_msg = await get_text(user.id, "GROUP_START_MESSAGE", bot_username=BOT_USERNAME)
        if group_start_msg is None:
            # Fallback for groups (should not happen)
            group_start_msg = f"<b>Hello! I'm Sticker Kang Bot</b>\n\nI help you create and manage custom sticker packs!\n\n<b>Start me in PM to use all features!</b>"
        
        await message.reply(
            group_start_msg,
            reply_markup=get_group_start_keyboard()
        )
        return
    
    # Private chat - check if new or existing user
    user_data = await get_user(user.id)
    
    if not user_data:
        # NEW USER - Show language selection first
        logger.info(f"New user {user.id} started bot - showing language selection")
        
        # Show language selection
        await show_language_selection_for_new_user(message)
        
        # Create user in database with default language (will be updated after selection)
        await create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language="en"  # Default, will be updated when user selects
        )
        
        # Log new user to admin group (ENGLISH ONLY)
        if LOG_GROUP_ID:
            try:
                log_msg = (
                    f"👤 <b>New User Started Bot</b>\n\n"
                    f"<b>User ID:</b> <code>{user.id}</code>\n"
                    f"<b>Username:</b> @{user.username or 'None'}\n"
                    f"<b>Name:</b> {user.first_name or 'Unknown'}\n"
                    f"<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                await message.bot.send_message(LOG_GROUP_ID, log_msg)
            except Exception as e:
                logger.error(f"Error sending new user log: {e}")
        
        # Don't show main menu yet - wait for language selection
        return
    
    else:
        # EXISTING USER - Show main menu in their language
        await update_user_started(user.id)
        
        # Get start message in user's language
        start_text = await get_text(
            user.id, 
            "START_MESSAGE_WITH_IMAGE",
            user_id=user.id,
            first_name=escape_html(user.first_name)
        )
        
        if start_text is None:
            # Fallback if key missing
            start_text = f"Hello {escape_html(user.first_name)}! Welcome back."
        
        await message.answer(start_text, reply_markup=await get_main_menu_keyboard(user.id))


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command - in user's language"""
    try:
        user_id = message.from_user.id
        help_text = await get_text(user_id, "HELP_MESSAGE")
        
        if help_text is None:
            help_text = "For help, contact @Samurais_Support"
        
        await message.answer(help_text)
    except Exception as e:
        logger.error(f"Error in help command: {e}")


# ============================================================================
# EXTRA COMMANDS MENU
# ============================================================================

@router.callback_query(F.data == SharedCallbacks.EXTRA_COMMANDS)
async def extra_commands_callback(callback: CallbackQuery):
    """Show extra commands menu"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        
        # Get message in user's language
        message_text = await get_text(user_id, "EXTRA_COMMANDS_MESSAGE")
        
        if message_text is None:
            message_text = "<b>Extra Commands</b>"
        
        await safe_edit_message(
            callback, 
            message_text, 
            await get_extra_commands_keyboard(user_id)
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
        user_id = callback.from_user.id
        
        message_text = await get_text(user_id, "AFK_INFO_MESSAGE")
        
        if message_text is None:
            message_text = "<b>AFK Feature</b>\n\nSet yourself as away from keyboard."
        
        await safe_edit_message(
            callback, 
            message_text, 
            await get_back_to_extra_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error in extra_afk_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_QUOTLY)
async def extra_quotly_callback(callback: CallbackQuery):
    """Show Quotly feature information"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        
        message_text = await get_text(user_id, "QUOTLY_INFO_MESSAGE")
        
        if message_text is None:
            message_text = "<b>Quotly Feature</b>\n\nConvert messages to stickers."
        
        await safe_edit_message(
            callback, 
            message_text, 
            await get_back_to_extra_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error in extra_quotly_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_STICKERS)
async def extra_stickers_callback(callback: CallbackQuery):
    """Show Stickers feature information"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        
        message_text = await get_text(user_id, "STICKERS_INFO_MESSAGE")
        
        if message_text is None:
            message_text = "<b>Stickers Feature</b>\n\nManage your sticker packs."
        
        await safe_edit_message(
            callback, 
            message_text, 
            await get_back_to_extra_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error in extra_stickers_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_MEMEFI)
async def extra_memefi_callback(callback: CallbackQuery):
    """Show MemeFi feature information"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        
        message_text = await get_text(user_id, "MEMEFI_INFO_MESSAGE")
        
        if message_text is None:
            message_text = "<b>MemeFi Feature</b>\n\nAdd text to stickers."
        
        await safe_edit_message(
            callback, 
            message_text, 
            await get_back_to_extra_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error in extra_memefi_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_WELCOME)
async def extra_welcome_callback(callback: CallbackQuery):
    """Show Welcome feature information"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        
        message_text = await get_text(user_id, "WELCOME_INFO_MESSAGE")
        
        if message_text is None:
            message_text = "<b>Welcome Feature</b>\n\nCustomize welcome messages."
        
        await safe_edit_message(
            callback, 
            message_text, 
            await get_back_to_extra_keyboard(user_id)
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
        
        # Get start message in user's language
        start_text = await get_text(
            user.id,
            "START_MESSAGE_WITH_IMAGE",
            user_id=user.id,
            first_name=escape_html(user.first_name)
        )
        
        if start_text is None:
            start_text = f"Hello {escape_html(user.first_name)}!"
        
        await safe_edit_message(
            callback, 
            start_text, 
            await get_main_menu_keyboard(user.id)
        )
    except Exception as e:
        logger.error(f"Error in back_to_main_callback: {e}")
