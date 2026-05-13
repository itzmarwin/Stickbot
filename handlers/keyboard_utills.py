import logging
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from utils.language import get_text_sync

logger = logging.getLogger(__name__)


class SharedCallbacks:
    MANAGE_PACKS = "manage_packs"
    EXTRA_COMMANDS = "extra_commands"
    BACK_TO_MAIN = "back_to_main"

    EXTRA_CMD_AFK = "extra_afk"
    EXTRA_CMD_QUOTLY = "extra_quotly"
    EXTRA_CMD_STICKERS = "extra_stickers"
    EXTRA_CMD_MEMEFI = "extra_memefi"
    EXTRA_CMD_WELCOME = "extra_welcome"
    EXTRA_CMD_TAGALL = "extra_tagall"


def get_main_menu_keyboard(language: str):
    from config import BOT_USERNAME

    builder = InlineKeyboardBuilder()

    builder.button(
        text=get_text_sync(language, "B_ADD_ME_GROUP") or "𝖠𝖽𝖽 𝖬𝖾 𝖨𝗇 𝖸𝗈𝗎𝗋 𝖦𝗋𝗈𝗎𝗉",
        url=f"https://t.me/{BOT_USERNAME}?startgroup=true"
    )
    builder.button(
        text=get_text_sync(language, "B_EXTRA_COMMANDS") or "𝖦𝗋𝗈𝗎𝗉 𝖬𝖺𝗇𝖺𝗀𝖾𝗋",
        callback_data=SharedCallbacks.EXTRA_COMMANDS
    )
    builder.button(
        text=get_text_sync(language, "B_MANAGE_PACKS") or "𝖬𝗒 𝖲𝗍𝗂𝖼𝗄𝖾𝗋 𝖯𝖺𝖼𝗄𝗌",
        callback_data=SharedCallbacks.MANAGE_PACKS
    )
    builder.button(
        text=get_text_sync(language, "B_SUPPORT") or "𝖲𝗎𝗉𝗉𝗈𝗋𝗍",
        url="https://t.me/Samurais_Support"
    )
    builder.button(
        text=get_text_sync(language, "B_UPDATES") or "𝖴𝗉𝖽𝖺𝗍𝖾𝗌",
        url="https://t.me/Samurais_network"
    )

    builder.adjust(1, 1, 1, 2)
    return builder.as_markup()


def get_group_start_keyboard():
    from config import BOT_USERNAME

    builder = InlineKeyboardBuilder()
    builder.button(text="𝖲𝗍𝖺𝗋𝗍 𝖬𝖾", url=f"https://t.me/{BOT_USERNAME}?start=group")
    builder.button(text="𝖲𝗎𝗉𝗉𝗈𝗋𝗍", url="https://t.me/Samurais_Support")
    builder.adjust(2)
    return builder.as_markup()


def get_extra_commands_keyboard(language: str):
    builder = InlineKeyboardBuilder()

    builder.button(text=get_text_sync(language, "B_AFK") or "𝖠𝖿𝗄", callback_data=SharedCallbacks.EXTRA_CMD_AFK)
    builder.button(text=get_text_sync(language, "B_QUOTLY") or "𝖰𝗎𝗈𝗍𝗅𝗒", callback_data=SharedCallbacks.EXTRA_CMD_QUOTLY)
    builder.button(text=get_text_sync(language, "B_STICKERS") or "𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌", callback_data=SharedCallbacks.EXTRA_CMD_STICKERS)
    builder.button(text=get_text_sync(language, "B_MEMEFI") or "𝖬𝖾𝗆𝖾𝖿𝗂", callback_data=SharedCallbacks.EXTRA_CMD_MEMEFI)
    builder.button(text=get_text_sync(language, "B_GREETINGS") or "𝖦𝗋𝖾𝖾𝗍𝗂𝗇𝗀𝗌", callback_data=SharedCallbacks.EXTRA_CMD_WELCOME)
    builder.button(text=get_text_sync(language, "B_TAGALL") or "𝖳𝖺𝗀𝖠𝗅𝗅", callback_data=SharedCallbacks.EXTRA_CMD_TAGALL)
    builder.button(text=get_text_sync(language, "B_BACK") or "⬅️ 𝖡𝖺𝖼𝗄", callback_data=SharedCallbacks.BACK_TO_MAIN)

    builder.adjust(3, 3, 1)
    return builder.as_markup()


def get_back_to_extra_keyboard(language: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text=get_text_sync(language, "B_BACK") or "⬅️ 𝖡𝖺𝖼𝗄",
        callback_data=SharedCallbacks.EXTRA_COMMANDS
    )
    return builder.as_markup()


def get_back_to_main_keyboard(language: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text=get_text_sync(language, "B_BACK") or "⬅️ 𝖡𝖺𝖼𝗄",
        callback_data=SharedCallbacks.BACK_TO_MAIN
    )
    return builder.as_markup()


async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        if callback.message.text:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        else:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
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
