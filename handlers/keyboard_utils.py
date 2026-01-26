import logging
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)


# ============================================================================
# CALLBACK DATA CONSTANTS
# ============================================================================

class SharedCallbacks:
    """Shared callback data constants used across handlers"""
    
    # Main menu callbacks
    MANAGE_PACKS = "manage_packs"
    EXTRA_COMMANDS = "extra_commands"
    BACK_TO_MAIN = "back_to_main"
    
    # Extra commands callbacks
    EXTRA_CMD_AFK = "extra_afk"
    EXTRA_CMD_QUOTLY = "extra_quotly"
    EXTRA_CMD_STICKERS = "extra_stickers"
    EXTRA_CMD_MEMEFI = "extra_memefi"
    EXTRA_CMD_WELCOME = "extra_welcome"


# ============================================================================
# KEYBOARD BUILDERS
# ============================================================================

def get_main_menu_keyboard():
    """
    Main menu keyboard shown on /start command
    
    Returns:
        InlineKeyboardMarkup with main menu buttons
    """
    from config import BOT_USERNAME
    
    builder = InlineKeyboardBuilder()
    builder.button(
        text="𝖠𝖽𝖽 𝖬𝖾 𝖨𝗇 𝖸𝗈𝗎𝗋 𝖦𝗋𝗈𝗎𝗉", 
        url=f"https://t.me/{BOT_USERNAME}?startgroup=true"
    )
    builder.button(
        text="𝖤𝗑𝗍𝗋𝖺 𝖢𝗈𝗆𝗆𝖺𝗇𝖽𝗌", 
        callback_data=SharedCallbacks.EXTRA_COMMANDS
    )
    builder.button(
        text="𝖬𝖺𝗇𝖺𝗀𝖾 𝖯𝖺𝖼𝗄𝗌", 
        callback_data=SharedCallbacks.MANAGE_PACKS
    )
    builder.button(
        text="𝖲𝗎𝗉𝗉𝗈𝗋𝗍", 
        url="https://t.me/Samurais_Support"
    )
    builder.button(
        text="𝖴𝗉𝖽𝖺𝗍𝖾𝗌", 
        url="https://t.me/Samurais_network"
    )
    builder.adjust(1, 2, 2)
    return builder.as_markup()


def get_group_start_keyboard():
    """
    Keyboard for group /start command
    
    Returns:
        InlineKeyboardMarkup with start and support buttons
    """
    from config import BOT_USERNAME
    
    builder = InlineKeyboardBuilder()
    builder.button(
        text="𝖲𝗍𝖺𝗋𝗍 𝖬𝖾", 
        url=f"https://t.me/{BOT_USERNAME}?start=group"
    )
    builder.button(
        text="𝖲𝗎𝗉𝗉𝗈𝗋𝗍", 
        url="https://t.me/Samurais_Support"
    )
    builder.adjust(2)
    return builder.as_markup()


def get_extra_commands_keyboard():
    """
    Extra commands menu keyboard
    
    Returns:
        InlineKeyboardMarkup with extra command buttons
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="𝖠𝖿𝗄", 
        callback_data=SharedCallbacks.EXTRA_CMD_AFK
    )
    builder.button(
        text="𝖰𝗎𝗈𝗍𝗅𝗒", 
        callback_data=SharedCallbacks.EXTRA_CMD_QUOTLY
    )
    builder.button(
        text="𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌", 
        callback_data=SharedCallbacks.EXTRA_CMD_STICKERS
    )
    builder.button(
        text="𝖬𝖾𝗆𝖾𝖿𝗂", 
        callback_data=SharedCallbacks.EXTRA_CMD_MEMEFI
    )
    builder.button(
        text="𝖦𝗋𝖾𝖾𝗍𝗂𝗇𝗀𝗌", 
        callback_data=SharedCallbacks.EXTRA_CMD_WELCOME
    )
    builder.button(
        text="⬅️ 𝖡𝖺𝖼𝗄", 
        callback_data=SharedCallbacks.BACK_TO_MAIN
    )
    builder.adjust(3, 2, 1)
    return builder.as_markup()


def get_back_to_extra_keyboard():
    """
    Back to extra commands keyboard
    
    Returns:
        InlineKeyboardMarkup with back button
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ 𝖡𝖺𝖼𝗄", 
        callback_data=SharedCallbacks.EXTRA_COMMANDS
    )
    return builder.as_markup()


def get_back_to_main_keyboard():
    """
    Back to main menu keyboard
    
    Returns:
        InlineKeyboardMarkup with back button
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ 𝖡𝖺𝖼𝗄", 
        callback_data=SharedCallbacks.BACK_TO_MAIN
    )
    return builder.as_markup()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None):
    """
    Safely edit a message with error handling
    
    Handles common edit errors like "message is not modified" 
    and "no text in the message"
    
    Args:
        callback: CallbackQuery object
        text: New message text
        reply_markup: Optional inline keyboard markup
    """
    try:
        if callback.message.text:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        else:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
            # Message content is same, ignore
            pass
        elif "no text in the message" in error_msg:
            try:
                await callback.message.delete()
                await callback.message.answer(text, reply_markup=reply_markup)
            except Exception as fallback_error:
                logger.error(f"Fallback edit failed: {fallback_error}")
        else:
            logger.error(f"Error editing message: {e}")
            raise
