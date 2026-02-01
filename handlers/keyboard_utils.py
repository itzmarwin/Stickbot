import logging
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from database import get_user_language
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


async def get_main_menu_keyboard(user_id: int):
    from config import BOT_USERNAME
    
    language = await get_user_language(user_id)
    
    builder = InlineKeyboardBuilder()
    
    add_group_text = get_text_sync(language, "B_ADD_ME_GROUP")
    if add_group_text is None:
        add_group_text = "𝖠𝖽𝖽 𝖬𝖾 𝖨𝗇 𝖸𝗈𝗎𝗋 𝖦𝗋𝗈𝗎𝗉"
    
    builder.button(
        text=add_group_text, 
        url=f"https://t.me/{BOT_USERNAME}?startgroup=true"
    )
    
    extra_cmd_text = get_text_sync(language, "B_EXTRA_COMMANDS")
    if extra_cmd_text is None:
        extra_cmd_text = "𝖤𝗑𝗍𝗋𝖺 𝖢𝗈𝗆𝗆𝖺𝗇𝖽𝗌"
    
    builder.button(
        text=extra_cmd_text, 
        callback_data=SharedCallbacks.EXTRA_COMMANDS
    )
    
    manage_packs_text = get_text_sync(language, "B_MANAGE_PACKS")
    if manage_packs_text is None:
        manage_packs_text = "𝖬𝖺𝗇𝖺𝗀𝖾 𝖯𝖺𝖼𝗄𝗌"
    
    builder.button(
        text=manage_packs_text, 
        callback_data=SharedCallbacks.MANAGE_PACKS
    )
    
    support_text = get_text_sync(language, "B_SUPPORT")
    if support_text is None:
        support_text = "𝖲𝗎𝗉𝗉𝗈𝗋𝗍"
    
    builder.button(
        text=support_text, 
        url="https://t.me/Samurais_Support"
    )
    
    updates_text = get_text_sync(language, "B_UPDATES")
    if updates_text is None:
        updates_text = "𝖴𝗉𝖽𝖺𝗍𝖾𝗌"
    
    builder.button(
        text=updates_text, 
        url="https://t.me/Samurais_network"
    )
    
    builder.adjust(1, 1, 1, 2)
    return builder.as_markup()


def get_group_start_keyboard():
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


async def get_extra_commands_keyboard(user_id: int):
    language = await get_user_language(user_id)
    
    builder = InlineKeyboardBuilder()
    
    afk_text = get_text_sync(language, "B_AFK")
    if afk_text is None:
        afk_text = "𝖠𝖿𝗄"
    builder.button(text=afk_text, callback_data=SharedCallbacks.EXTRA_CMD_AFK)
    
    quotly_text = get_text_sync(language, "B_QUOTLY")
    if quotly_text is None:
        quotly_text = "𝖰𝗎𝗈𝗍𝗅𝗒"
    builder.button(text=quotly_text, callback_data=SharedCallbacks.EXTRA_CMD_QUOTLY)
    
    stickers_text = get_text_sync(language, "B_STICKERS")
    if stickers_text is None:
        stickers_text = "𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌"
    builder.button(text=stickers_text, callback_data=SharedCallbacks.EXTRA_CMD_STICKERS)
    
    memefi_text = get_text_sync(language, "B_MEMEFI")
    if memefi_text is None:
        memefi_text = "𝖬𝖾𝗆𝖾𝖿𝗂"
    builder.button(text=memefi_text, callback_data=SharedCallbacks.EXTRA_CMD_MEMEFI)
    
    greetings_text = get_text_sync(language, "B_GREETINGS")
    if greetings_text is None:
        greetings_text = "𝖦𝗋𝖾𝖾𝗍𝗂𝗇𝗀𝗌"
    builder.button(text=greetings_text, callback_data=SharedCallbacks.EXTRA_CMD_WELCOME)

    tagall_text = get_text_sync(language, "B_TAGALL")
    if tagall_text is None:
        tagall_text = "𝖳𝖺𝗀𝖠𝗅𝗅"
    builder.button(text=tagall_text, callback_data=SharedCallbacks.EXTRA_CMD_TAGALL)
    
    back_text = get_text_sync(language, "B_BACK")
    if back_text is None:
        back_text = "⬅️ 𝖡𝖺𝖼𝗄"
    builder.button(text=back_text, callback_data=SharedCallbacks.BACK_TO_MAIN)
    
    builder.adjust(3, 3, 1)
    return builder.as_markup()


async def get_back_to_extra_keyboard(user_id: int):
    language = await get_user_language(user_id)
    
    builder = InlineKeyboardBuilder()
    
    back_text = get_text_sync(language, "B_BACK")
    if back_text is None:
        back_text = "⬅️ 𝖡𝖺𝖼𝗄"
    
    builder.button(
        text=back_text, 
        callback_data=SharedCallbacks.EXTRA_COMMANDS
    )
    return builder.as_markup()


async def get_back_to_main_keyboard(user_id: int):
    language = await get_user_language(user_id)
    
    builder = InlineKeyboardBuilder()
    
    back_text = get_text_sync(language, "B_BACK")
    if back_text is None:
        back_text = "⬅️ 𝖡𝖺𝖼𝗄"
    
    builder.button(
        text=back_text, 
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
