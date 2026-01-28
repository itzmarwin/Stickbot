"""
Language Handler - Multi-language support

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
# LANGUAGE SELECTION CALLBACK
# ============================================================================

@router.callback_query(F.data.startswith("set_lang:"))
async def set_language_callback(callback: CallbackQuery):
    """Handle language selection - shows start message immediately"""
    await callback.answer()
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    # Extract language code from callback data
    language = callback.data.split(":")[1]  # "set_lang:en" -> "en"
    
    # Validate language
    if language not in ["en", "rus", "bur"]:
        await callback.answer("Invalid language!", show_alert=True)
        return
    
    # Save language preference FIRST
    success = await set_user_language(user_id, language)
    
    if not success:
        await callback.answer("Error saving language!", show_alert=True)
        return
    
    logger.info(f"✅ User {user_id} changed language to {language}")
    
    # NOW get text in the NEW language (after saving)
    confirmation_msg = await get_text(user_id, "LANG_CHANGED")
    
    # Fallback messages for each language
    if confirmation_msg is None:
        fallback_messages = {
            "en": "✅ Language changed to English",
            "rus": "✅ Язык изменен на русский",
            "bur": "✅ ဘာသာစကားကို မြန်မာသို့ ပြောင်းလဲပြီးပါပြီ"
        }
        confirmation_msg = fallback_messages.get(language, "✅ Language changed")
    
    # Import here to avoid circular import
    from handlers.keyboard_utils import get_main_menu_keyboard
    from utils.html_utils import escape_html
    
    # Get START message in NEW language
    start_text = await get_text(
        user_id,
        "START_MESSAGE_WITH_IMAGE",
        user_id=user_id,
        first_name=escape_html(callback.from_user.first_name)
    )
    
    if start_text is None:
        # Fallback
        start_text = f"Hello {escape_html(callback.from_user.first_name)}!"
    
    # ✅ FIX: Delete old message first
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete language selection message: {e}")
    
    # ✅ FIX: Use bot.send_message instead of callback.message.answer
    try:
        # Send confirmation + start message together
        full_message = f"{confirmation_msg}\n\n{start_text}"
        
        await callback.bot.send_message(
            chat_id=chat_id,
            text=full_message,
            reply_markup=await get_main_menu_keyboard(user_id)
        )
        
        logger.info(f"✅ Sent start message to user {user_id} in {language}")
        
    except Exception as e:
        logger.error(f"❌ Error sending start message: {e}")
        # Fallback: try without deleting previous message
        try:
            await callback.message.edit_text(
                confirmation_msg,
                reply_markup=await get_main_menu_keyboard(user_id)
            )
        except Exception as fallback_error:
            logger.error(f"❌ Fallback also failed: {fallback_error}")


# ============================================================================
# HELPER FUNCTION FOR NEW USERS
# ============================================================================

async def show_language_selection_for_new_user(message: Message):
    """
    Show language selection for new users during /start
    Called from start.py for first-time users
    """
    user_id = message.from_user.id
    
    # Get language selection message (will use default "en" for new users)
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
