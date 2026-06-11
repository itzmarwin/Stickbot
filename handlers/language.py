import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from mongo.userdb import set_user_language, set_group_language
from pyrogram_handlers.caching import get_admin_permissions
from utils.language import get_lang_dict, get_text_from_dict, get_chat_lang_dict

logger = logging.getLogger(__name__)
router = Router()


def get_language_selection_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🇬🇧 English", callback_data="set_lang:en")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang:rus")
    builder.button(text="🇲🇲 မြန်မာ",  callback_data="set_lang:bur")
    builder.adjust(1)
    return builder.as_markup()


def get_group_language_selection_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🇬🇧 English", callback_data="set_group_lang:en")
    builder.button(text="🇷🇺 Русский", callback_data="set_group_lang:rus")
    builder.button(text="🇲🇲 မြန်မာ",  callback_data="set_group_lang:bur")
    builder.adjust(1)
    return builder.as_markup()


# ─── Private /lang ────────────────────────────────────────────────────────────

@router.message(Command("lang"), F.chat.type == "private")
async def cmd_lang(message: Message):
    user_id = message.from_user.id
    _, lang  = await get_lang_dict(user_id)
    lang_select_msg = get_text_from_dict(lang, "LANG_SELECT_MESSAGE")
    await message.answer(lang_select_msg, reply_markup=get_language_selection_keyboard())


@router.callback_query(F.data.startswith("set_lang:"))
async def set_language_callback(callback: CallbackQuery):
    user_id  = callback.from_user.id
    language = callback.data.split(":")[1]

    if language not in ["en", "rus", "bur"]:
        await callback.answer("Invalid language!", show_alert=True)
        return

    success = await set_user_language(user_id, language)
    if not success:
        await callback.answer("Error saving language!", show_alert=True)
        return

    from handlers.keyboard_utils import get_main_menu_keyboard
    from utils.html_utils import escape_html

    _, lang = await get_lang_dict(user_id)

    start_text = get_text_from_dict(
        lang,
        "START_MESSAGE_WITH_IMAGE",
        uid=user_id,
        first_name=escape_html(callback.from_user.first_name)
    )

    await callback.message.edit_text(
        start_text,
        reply_markup=get_main_menu_keyboard(lang)
    )
    await callback.answer()


# ─── Group /lang ──────────────────────────────────────────────────────────────

@router.message(Command("lang"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_lang_group(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None

    if not user_id:
        return

    perms = get_admin_permissions(chat_id, user_id)
    if perms is None:
        try:
            member = await message.bot.get_chat_member(chat_id, user_id)
            from aiogram.enums import ChatMemberStatus
            if member.status not in (
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR
            ):
                lang = await get_chat_lang_dict(chat_id)
                await message.answer(lang.get("only_admins", "Only admins can use this command."))
                return
        except Exception:
            lang = await get_chat_lang_dict(chat_id)
            await message.answer(lang.get("only_admins", "Only admins can use this command."))
            return

    lang = await get_chat_lang_dict(chat_id)
    await message.answer(
        lang.get("LANG_SELECT_MESSAGE", "Choose language:"),
        reply_markup=get_group_language_selection_keyboard()
    )


@router.callback_query(F.data.startswith("set_group_lang:"))
async def set_group_language_callback(callback: CallbackQuery):
    chat_id  = callback.message.chat.id
    user_id  = callback.from_user.id
    language = callback.data.split(":")[1]

    perms = get_admin_permissions(chat_id, user_id)
    if perms is None:
        try:
            member = await callback.bot.get_chat_member(chat_id, user_id)
            from aiogram.enums import ChatMemberStatus
            if member.status not in (
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR
            ):
                await callback.answer("Only admins can change group language!", show_alert=True)
                return
        except Exception:
            await callback.answer("Only admins can change group language!", show_alert=True)
            return

    if language not in ["en", "rus", "bur"]:
        await callback.answer("Invalid language!", show_alert=True)
        return

    success = await set_group_language(chat_id, language)
    if not success:
        await callback.answer("Error saving language!", show_alert=True)
        return

    lang      = await get_chat_lang_dict(chat_id)
    lang_names = {"en": "English 🇬🇧", "rus": "Русский 🇷🇺", "bur": "မြန်မာ 🇲🇲"}

    await callback.message.edit_text(
        lang.get("group_lang_changed", "Group language changed to") + f" <b>{lang_names.get(language, language)}</b>"
    )
    await callback.answer()

async def show_language_selection_for_new_user(message: Message):
    user_id = message.from_user.id
    _, lang  = await get_lang_dict(user_id)
    lang_select_msg = get_text_from_dict(lang, "LANG_SELECT_MESSAGE")
    await message.answer(lang_select_msg, reply_markup=get_language_selection_keyboard())
