import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import get_user_language, set_user_language
from utils.language import get_text

logger = logging.getLogger(__name__)
router = Router()


# ============================================================================
# LANGUAGE SELECTION KEYBOARDS
# ============================================================================

def get_language_selection_keyboard() -> InlineKeyboardMarkup:
    """
    Build language selection keyboard with 3 language options
    
    Returns:
        InlineKeyboardMarkup with English, Russian, Burmese buttons
    """
    builder = InlineKeyboardBuilder()
    
    # Language buttons with callback data
    builder.button(
        text="🇬🇧 English",
        callback_data="set_lang:en"
    )
    builder.button(
        text="🇷🇺 Русский",
        callback_data="set_lang:rus"
    )
    builder.button(
        text="🇲🇲 မြန်မာ",
        callback_data="set_lang:bur"
    )
    
    # Arrange buttons in a column (one per row)
    builder.adjust(1)
    
    return builder.as_markup()


async def get_language_selection_message(user_id: int) -> str:
    """
    Get language selection message in user's current language
    
    Args:
        user_id: User's Telegram ID
    
    Returns:
        Formatted language selection message
    """
    message = await get_text(user_id, "LANG_SELECT_MESSAGE")
    if message is None:
        # Fallback if key missing
        return "🌐 <b>Choose Your Language</b>\n\nSelect your preferred language:"
    return message


# ============================================================================
# /lang COMMAND HANDLER
# ============================================================================

@router.message(Command("lang"))
async def cmd_lang(message: Message):
    """
    Handle /lang command - show language selection menu
    Only works in private chat
    """
    # Check if command is in private chat
    if message.chat.type != "private":
        logger.info(f"User {message.from_user.id} tried /lang in group {message.chat.id}")
        return  # Silently ignore in groups
    
    try:
        user_id = message.from_user.id
        
        # Get language selection message
        lang_message = await get_language_selection_message(user_id)
        
        # Send language selection keyboard
        await message.answer(
            lang_message,
            reply_markup=get_language_selection_keyboard()
        )
        
        logger.info(f"User {user_id} opened language selection menu")
        
    except Exception as e:
        logger.error(f"Error in /lang command: {e}", exc_info=True)
        await message.answer("❌ An error occurred. Please try again.")


# ============================================================================
# LANGUAGE SELECTION CALLBACK HANDLER
# ============================================================================

@router.callback_query(F.data.startswith("set_lang:"))
async def callback_set_language(callback: CallbackQuery):
    """
    Handle language selection callback
    Format: set_lang:en | set_lang:rus | set_lang:bur
    """
    await callback.answer()
    
    try:
        # Parse language code from callback data
        language = callback.data.split(":")[1]
        user_id = callback.from_user.id
        
        # Validate language
        if language not in ["en", "rus", "bur"]:
            logger.warning(f"Invalid language selection: {language}")
            await callback.message.edit_text("❌ Invalid language selection.")
            return
        
        # Save language preference to database
        success = await set_user_language(user_id, language)
        
        if not success:
            await callback.message.edit_text("❌ Failed to save language preference. Please try again.")
            return
        
        # Get confirmation message in NEW language
        confirmation = await get_text(user_id, "LANG_CHANGED")
        
        if confirmation is None:
            # Fallback confirmation messages
            confirmations = {
                "en": "✅ Language changed to English",
                "rus": "✅ Язык изменен на русский",
                "bur": "✅ ဘာသာစကားကို မြန်မာသို့ပြောင်းလဲပြီးပါပြီ"
            }
            confirmation = confirmations.get(language, "✅ Language changed successfully")
        
        # Update message with confirmation
        await callback.message.edit_text(confirmation)
        
        logger.info(f"User {user_id} changed language to '{language}'")
        
    except Exception as e:
        logger.error(f"Error in language selection callback: {e}", exc_info=True)
        await callback.message.edit_text("❌ An error occurred. Please try again.")


# ============================================================================
# HELPER FUNCTION FOR NEW USERS
# ============================================================================

async def show_language_selection_for_new_user(message: Message) -> bool:
    """
    Show language selection for new users
    Called from start.py for first-time users
    
    Args:
        message: Message object from /start command
    
    Returns:
        True if language selection shown successfully
    """
    try:
        user_id = message.from_user.id
        
        # Get language selection message (will use default "en" for new users)
        lang_message = await get_language_selection_message(user_id)
        
        # Send language selection keyboard
        await message.answer(
            lang_message,
            reply_markup=get_language_selection_keyboard()
        )
        
        logger.info(f"New user {user_id} shown language selection")
        return True
        
    except Exception as e:
        logger.error(f"Error showing language selection for new user: {e}", exc_info=True)
        return False
