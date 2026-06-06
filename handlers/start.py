import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime

from mongo.userdb import get_user, create_user
from utils.language import get_lang_dict, get_text, get_text_from_dict
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
        # group mein sirf ek text aur ek keyboard — get_text direct
        group_start_msg = await get_text(user.id, "GROUP_START_MESSAGE", bot_username=BOT_USERNAME)
        await message.reply(group_start_msg, reply_markup=get_group_start_keyboard())
        return

    # ek baar lang fetch — poore handler mein reuse
    _, lang = await get_lang_dict(user.id)

    if user.id in _started_users:
        start_text = get_text_from_dict(
            lang,
            "START_MESSAGE_WITH_IMAGE",
            uid=user.id,
            first_name=escape_html(user.first_name)
        )
        await message.answer(start_text, reply_markup=get_main_menu_keyboard(lang))
        return

    user_data = await get_user(user.id)

    if not user_data:
        # naya user — language select pehle, default "en" se message
        await create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            language="en"
        )
        lang_select_msg = get_text_from_dict(lang, "LANG_SELECT_MESSAGE")
        await message.answer(lang_select_msg, reply_markup=get_language_selection_keyboard())
        asyncio.create_task(_log_new_user(message.bot, user))
    else:
        _started_users.add(user.id)
        start_text = get_text_from_dict(
            lang,
            "START_MESSAGE_WITH_IMAGE",
            uid=user.id,
            first_name=escape_html(user.first_name)
        )
        await message.answer(start_text, reply_markup=get_main_menu_keyboard(lang))


@router.message(Command("help"))
async def cmd_help(message: Message):
    try:
        _, lang = await get_lang_dict(message.from_user.id)
        help_text = get_text_from_dict(lang, "HELP_MESSAGE")
        await message.answer(help_text)
    except Exception as e:
        logger.error(f"Error in help command: {e}")


# ─────────────────────────────────────────────────────────
# Har callback mein pattern yahi hai:
#   1. callback.answer() — non-blocking background task
#   2. get_lang_dict() — sirf EK await, sirf EK DB call max
#   3. text aur keyboard — sync, zero DB, pure memory
#   4. safe_edit_message — sirf yahi actual Telegram call
# ─────────────────────────────────────────────────────────

@router.callback_query(F.data == SharedCallbacks.EXTRA_COMMANDS)
async def extra_commands_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "EXTRA_COMMANDS_MESSAGE")
        await safe_edit_message(callback, message_text, get_extra_commands_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_commands_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_AFK)
async def extra_afk_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "AFK_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_afk_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_QUOTLY)
async def extra_quotly_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "QUOTLY_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_quotly_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_STICKERS)
async def extra_stickers_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "STICKERS_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_stickers_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_MEMEFI)
async def extra_memefi_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "MEMEFI_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_memefi_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_WELCOME)
async def extra_welcome_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "WELCOME_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_welcome_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_TAGALL)
async def extra_tagall_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "TAGALL_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_tagall_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_LOCKS)
async def extra_locks_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "LOCKS_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_locks_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_WARNS)
async def extra_warns_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "WARNS_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_warns_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_BAN)
async def extra_ban_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "BAN_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_ban_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_MUTE)
async def extra_mute_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "MUTE_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_mute_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.EXTRA_CMD_FILTERS)
async def extra_filters_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        _, lang = await get_lang_dict(callback.from_user.id)
        message_text = get_text_from_dict(lang, "FILTERS_INFO_MESSAGE")
        await safe_edit_message(callback, message_text, get_back_to_extra_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in extra_filters_callback: {e}")


@router.callback_query(F.data == SharedCallbacks.BACK_TO_MAIN)
async def back_to_main_callback(callback: CallbackQuery):
    asyncio.create_task(callback.answer())
    try:
        user = callback.from_user
        _, lang = await get_lang_dict(user.id)
        start_text = get_text_from_dict(
            lang,
            "START_MESSAGE_WITH_IMAGE",
            uid=user.id,
            first_name=escape_html(user.first_name)
        )
        await safe_edit_message(callback, start_text, get_main_menu_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in back_to_main_callback: {e}")
