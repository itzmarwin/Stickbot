import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from mongo.userdb import get_user_language, set_user_language
from utils.language import get_text

logger = logging.getLogger(__name__)
router = Router()


def get_language_selection_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🇬🇧 English", callback_data="set_lang:en")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang:rus")
    builder.button(text="🇲🇲 မြန်မာ", callback_data="set_lang:bur")
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("lang"), F.chat.type == "private")
async def cmd_lang(message: Message):
    user_id = message.from_user.id
    lang_select_msg = await get_text(user_id, "LANG_SELECT_MESSAGE")
    await message.answer(lang_select_msg, reply_markup=get_language_selection_keyboard())


@router.callback_query(F.data.startswith("set_lang:"))
async def set_language_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
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

    start_text = await get_text(
        user_id,
        "START_MESSAGE_WITH_IMAGE",
        uid=user_id,
        first_name=escape_html(callback.from_user.first_name)
    )

    keyboard = await get_main_menu_keyboard(user_id)
    await callback.message.edit_text(start_text, reply_markup=keyboard)
    await callback.answer()


async def show_language_selection_for_new_user(message: Message):
    user_id = message.from_user.id
    lang_select_msg = await get_text(user_id, "LANG_SELECT_MESSAGE")
    await message.answer(lang_select_msg, reply_markup=get_language_selection_keyboard())
