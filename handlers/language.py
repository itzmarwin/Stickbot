"""
Language Handler - Multi-language support (DEBUG VERSION)

Handles:
- /lang command for changing language
- Language selection for new users
- Language preference storage
"""

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import get_user_language, set_user_language
from utils.language import get_text

logger = logging.getLogger(__name__)
router = Router()


# ============================================================================
# LANGUAGE SELECTION KEYBOARD
# ============================================================================

def get_language_selection_keyboard():
    """Build language selection keyboard with 3 languages"""
    builder = InlineKeyboardBuilder()
    
    # English
    builder.button(text="🇬🇧 English", callback_data="set_lang:en")
    
    # Russian
    builder.button(text="🇷🇺 Русский", callback_data="set_lang:rus")
    
    # Burmese
    builder.button(text="🇲🇲 မြန်မာ", callback_data="set_lang:bur")
    
    builder.adjust(1)  # 1 button per row
    return builder.as_markup()


# ============================================================================
# /LANG COMMAND
# ============================================================================

@router.message(Command("lang"), F.chat.type == "private")
async def cmd_lang(message: Message):
    """Handle /lang command - show language selection"""
    user_id = message.from_user.id
    
    # Get current language
    current_lang = await get_user_language(user_id)
    
    # Get message in current language
    lang_select_msg = await get_text(user_id, "LANG_SELECT_MESSAGE")
    
    if lang_select_msg is None:
        lang_select_msg = (
            "🌐 <b>Choose Your Language</b>\n\n"
            "Select your preferred language:"
        )
    
    await message.answer(
        lang_select_msg,
        reply_markup=get_language_selection_keyboard()
    )
    
    logger.info(f"User {user_id} opened language selection (current: {current_lang})")


# ============================================================================
# LANGUAGE SELECTION CALLBACK (DEBUG VERSION)
# ============================================================================

@router.callback_query(F.data.startswith("set_lang:"))
async def set_language_callback(callback: CallbackQuery):
    """Handle language selection - shows start message immediately"""
    await callback.answer()
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    logger.info(f"🔍 DEBUG: Starting language callback for user {user_id}")
    
    # Extract language code from callback data
    language = callback.data.split(":")[1]
    logger.info(f"🔍 DEBUG: Selected language: {language}")
    
    # Validate language
    if language not in ["en", "rus", "bur"]:
        logger.error(f"❌ DEBUG: Invalid language {language}")
        await callback.answer("Invalid language!", show_alert=True)
        return
    
    # Save language preference FIRST
    logger.info(f"🔍 DEBUG: Saving language {language} for user {user_id}")
    success = await set_user_language(user_id, language)
    
    if not success:
        logger.error(f"❌ DEBUG: Failed to save language")
        await callback.answer("Error saving language!", show_alert=True)
        return
    
    logger.info(f"✅ User {user_id} changed language to {language}")
    
    # Get confirmation message
    logger.info(f"🔍 DEBUG: Getting confirmation message")
    confirmation_msg = await get_text(user_id, "LANG_CHANGED")
    
    if confirmation_msg is None:
        fallback_messages = {
            "en": "✅ Language changed to English",
            "rus": "✅ Язык изменен на русский",
            "bur": "✅ ဘာသာစကားကို မြန်မာသို့ ပြောင်းလဲပြီးပါပြီ"
        }
        confirmation_msg = fallback_messages.get(language, "✅ Language changed")
        logger.info(f"🔍 DEBUG: Using fallback confirmation: {confirmation_msg[:30]}...")
    
    # Import utilities
    logger.info(f"🔍 DEBUG: Importing utilities")
    try:
        from handlers.keyboard_utils import get_main_menu_keyboard
        from utils.html_utils import escape_html
        logger.info(f"✅ DEBUG: Imports successful")
    except Exception as import_error:
        logger.error(f"❌ DEBUG: Import failed: {import_error}")
        return
    
    # Get START message
    logger.info(f"🔍 DEBUG: Getting start message for user {user_id}")
    try:
        start_text = await get_text(
            user_id,
            "START_MESSAGE_WITH_IMAGE",
            user_id=user_id,
            first_name=escape_html(callback.from_user.first_name)
        )
        
        if start_text is None:
            start_text = f"Hello {escape_html(callback.from_user.first_name)}!"
            logger.info(f"🔍 DEBUG: Using fallback start text")
        else:
            logger.info(f"✅ DEBUG: Got start text: {start_text[:50]}...")
            
    except Exception as text_error:
        logger.error(f"❌ DEBUG: Error getting start text: {text_error}")
        start_text = f"Hello {escape_html(callback.from_user.first_name)}!"
    
    # Delete old message
    logger.info(f"🔍 DEBUG: Attempting to delete old message")
    try:
        await callback.message.delete()
        logger.info(f"✅ DEBUG: Old message deleted")
    except Exception as delete_error:
        logger.warning(f"⚠️ DEBUG: Could not delete message: {delete_error}")
    
    # Send new message with buttons
    logger.info(f"🔍 DEBUG: Preparing to send new message")
    try:
        # Get keyboard
        logger.info(f"🔍 DEBUG: Getting main menu keyboard")
        keyboard = await get_main_menu_keyboard(user_id)
        logger.info(f"✅ DEBUG: Got keyboard")
        
        # Prepare message
        full_message = f"{confirmation_msg}\n\n{start_text}"
        logger.info(f"🔍 DEBUG: Full message prepared (length: {len(full_message)})")
        
        # Send message
        logger.info(f"🔍 DEBUG: Sending message to chat {chat_id}")
        sent_message = await callback.bot.send_message(
            chat_id=chat_id,
            text=full_message,
            reply_markup=keyboard
        )
        
        logger.info(f"✅ Sent start message to user {user_id} in {language} (msg_id: {sent_message.message_id})")
        
    except Exception as send_error:
        logger.error(f"❌ DEBUG: Error sending message: {send_error}", exc_info=True)
        
        # Fallback: try editing instead
        logger.info(f"🔍 DEBUG: Trying fallback edit method")
        try:
            await callback.message.edit_text(
                f"{confirmation_msg}\n\n{start_text}",
                reply_markup=await get_main_menu_keyboard(user_id)
            )
            logger.info(f"✅ DEBUG: Fallback edit successful")
        except Exception as fallback_error:
            logger.error(f"❌ DEBUG: Fallback also failed: {fallback_error}", exc_info=True)


# ============================================================================
# HELPER FUNCTION FOR NEW USERS
# ============================================================================

async def show_language_selection_for_new_user(message: Message):
    """
    Show language selection for new users during /start
    Called from start.py for first-time users
    """
    user_id = message.from_user.id
    
    # Get language selection message
    lang_select_msg = await get_text(user_id, "LANG_SELECT_MESSAGE")
    
    # Fallback if template missing
    if lang_select_msg is None:
        lang_select_msg = (
            "🌐 <b>Choose Your Language</b>\n\n"
            "Select your preferred language to continue:"
        )
    
    # Show language selection keyboard
    await message.answer(
        lang_select_msg,
        reply_markup=get_language_selection_keyboard()
    )
    
    logger.info(f"Showed language selection to new user {user_id}")
