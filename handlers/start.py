import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime

from mongo.userdb import get_user, create_user
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

_started_users: set = set()


def get_language_selection_keyboard():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🇬🇧 English", callback_data="set_lang:en")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang:rus")
    builder.button(text="🇲🇲 မြန်မာ", callback_data="set_lang:bur")
    builder.adjust(1)
    return builder.as_markup()


async def _log_new_user(bot, user):
    if not LOG_GROUP_ID:
        return
    try:
        log_msg = (
            f"👤 <b>New User Started Bot</b>\n\n"
            f"<b>User ID:</b> <code>{user.id}</code>\n"
            f"<b>Username:</b> @{user.username or 'None'}\n"
            f"<b>Name:</b> {user.first_name or 'Unknown'}\n"
            f"<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        await bot.send_message(LOG_GROUP_ID, log_msg)
    except Exception as e:
        logger.error(f"Error sending new user log: {e}")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user = message.from_user
    await state.clear()

    if message.chat.type in ["group", "supergroup"]:
        group_start_msg = await get_text(user.id, "GROUP_START_MESSAGE", bot_username=BOT_USERNAME)
        await message.reply(group_start_msg, reply_markup=get_group_start_keyboard())
        return

    if user.id in _started_users:
        start_text = await get_text(
            user.id,
            "START_MESSAGE_WITH_IMAGE",
            uid=user.id,
            first_name=escape_html(user.first_name)
        )
        keyboard = await get_main_menu_keyboard(user.id)
        await message.answer(start_text, reply_markup=keyboard)
        return

    user_data = await get_user(user.id)

    if not user_data:
        await create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language="en"
        )
        lang_select_msg = await get_text(user.id, "LANG_SELECT_MESSAGE")
        await message.answer(lang_select_msg, reply_markup=get_language_selection_keyboard())
        asyncio.create_task(_log_new_user(message.bot, user))
    else:
        _started_users.add(user.id)
        start_text = await get_text(
            user.id,
            "START_MESSAGE_WITH_IMAGE",
            uid=user.id,
            first_name=escape_html(user.first_name)
        )
        keyboard = await get_main_menu_keyboard(user.id)
        await message.answer(start_text, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message):
    try:
        help_text = await get_text(message.from_user.id, "HELP_MESSAGE")
        await message.answer(help_text)
    except Exception as e:
        logger.error(f"Error in help command: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_COMMANDS)
async def extra_commands_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "EXTRA_COMMANDS_MESSAGE")
        await safe_edit_message(callback, message_text, await get_extra_commands_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_commands_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_AFK)
async def extra_afk_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "AFK_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_afk_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_QUOTLY)
async def extra_quotly_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "QUOTLY_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_quotly_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_STICKERS)
async def extra_stickers_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "STICKERS_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_stickers_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_MEMEFI)
async def extra_memefi_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "MEMEFI_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_memefi_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_WELCOME)
async def extra_welcome_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "WELCOME_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_welcome_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_TAGALL)
async def extra_tagall_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "TAGALL_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_tagall_callback: {e}")

@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_LOCKS)
async def extra_locks_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "LOCKS_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_locks_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_WARNS)
async def extra_warns_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "WARNS_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_warns_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_BAN)
async def extra_ban_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "BAN_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_ban_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_MUTE)
async def extra_mute_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "MUTE_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_mute_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_FILTERS)
async def extra_filters_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        message_text = await get_text(callback.from_user.id, "FILTERS_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, await get_back_to_extra_keyboard(callback.from_user.id))
    except Exception as e:
        logger.error(f"Error in extra_filters_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.BACK_TO_MAIN)
async def back_to_main_callback(callback: CallbackQuery):
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
