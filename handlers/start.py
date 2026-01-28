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


def get_language_selection_keyboard():
    """Build language selection keyboard with 3 languages"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🇬🇧 English", callback_data="set_lang:en")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang:rus")
    builder.button(text="🇲🇲 မြန်မာ", callback_data="set_lang:bur")
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command"""
    user = message.from_user
    await state.clear()
    
    if message.chat.type in ["group", "supergroup"]:
        group_start_msg = await get_text(user.id, "GROUP_START_MESSAGE", bot_username=BOT_USERNAME)
        await message.reply(group_start_msg, reply_markup=get_group_start_keyboard())
        logger.info(f"Group start command from {user.id} in chat {message.chat.id}")
        return
    
    user_data = await get_user(user.id)
    
    if not user_data:
        logger.info(f"New user {user.id} started bot")
        
        await create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language="en"
        )
        
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
        
        lang_select_msg = await get_text(user.id, "LANG_SELECT_MESSAGE")
        await message.answer(lang_select_msg, reply_markup=get_language_selection_keyboard())
        logger.info(f"Showed language selection to new user {user.id}")
        return
    
    else:
        logger.info(f"Existing user {user.id} used /start command")
        
        try:
            await update_user_started(user.id)
            
            start_text = await get_text(
                user.id, 
                "START_MESSAGE_WITH_IMAGE",
                uid=user.id,
                first_name=escape_html(user.first_name)
            )
            
            keyboard = await get_main_menu_keyboard(user.id)
            await message.answer(start_text, reply_markup=keyboard)
            logger.info(f"Sent start message to existing user {user.id}")
            
        except Exception as e:
            logger.error(f"Error in existing user /start flow: {e}", exc_info=True)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    try:
        user_id = message.from_user.id
        help_text = await get_text(user_id, "HELP_MESSAGE")
        await message.answer(help_text)
        logger.info(f"Help command from user {user_id}")
    except Exception as e:
        logger.error(f"Error in help command: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_COMMANDS)
async def extra_commands_callback(callback: CallbackQuery):
    """Show extra commands menu"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        message_text = await get_text(user_id, "EXTRA_COMMANDS_MESSAGE")
        await safe_edit_message(callback, message_text, await get_extra_commands_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in extra_commands_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_AFK)
async def extra_afk_callback(callback: CallbackQuery):
    """Show AFK feature information"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        message_text = await get_text(user_id, "AFK_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in extra_afk_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_QUOTLY)
async def extra_quotly_callback(callback: CallbackQuery):
    """Show Quotly feature information"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        message_text = await get_text(user_id, "QUOTLY_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in extra_quotly_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_STICKERS)
async def extra_stickers_callback(callback: CallbackQuery):
    """Show Stickers feature information"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        message_text = await get_text(user_id, "STICKERS_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in extra_stickers_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_MEMEFI)
async def extra_memefi_callback(callback: CallbackQuery):
    """Show MemeFi feature information"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        message_text = await get_text(user_id, "MEMEFI_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in extra_memefi_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_WELCOME)
async def extra_welcome_callback(callback: CallbackQuery):
    """Show Welcome feature information"""
    await callback.answer()
    try:
        user_id = callback.from_user.id
        message_text = await get_text(user_id, "WELCOME_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in extra_welcome_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.BACK_TO_MAIN)
async def back_to_main_callback(callback: CallbackQuery):
    """Navigate back to main menu"""
    await callback.answer()
    
    try:
        user = callback.from_user
        
        start_text = await get_text(
            user.id,
            "START_MESSAGE_WITH_IMAGE",
            uid=user.id,
            first_name=escape_html(user.first_name)
        )
        
        await safe_edit_message(callback, start_text, await get_main_menu_keyboard(user.id))
    except Exception as e:
        logger.error(f"Error in back_to_main_callback: {e}")
