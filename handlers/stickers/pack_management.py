import logging
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InputSticker
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from callback_manager import create_callback, parse_callback
from mongo.stickerdb import (
    get_user_packs_paginated, update_pack_name, delete_pack_by_short_name,
    get_pack_by_short_name, create_sticker_pack,
    update_pack_sticker_count
)
from utils.language import get_lang_dict, get_text_from_dict
from utils.fsm_states import PackManagementStates
from utils.helpers import validate_pack_name, format_pack_name, generate_short_name, get_file_size_mb
from utils.converters import convert_image_to_webp, convert_video_to_webm, cleanup_temp_files, create_temp_dir
from utils.html_utils import escape_html
from handlers.stickers.kang import add_sticker_to_pack, get_random_emoji
from config import BOT_USERNAME, MAX_VIDEO_SIZE_MB
from rate_limiter import is_sticker_processing, start_sticker_processing, stop_sticker_processing

from handlers.keyboard_utils import (
    SharedCallbacks,
    get_back_to_main_keyboard,
    safe_edit_message
)

logger = logging.getLogger(__name__)
router = Router()


class PackManagementCallback:
    CREATE_NEW_PACK = "create_new_pack"
    PACK_SELECTED = "ps:"
    RENAME_PACK = "rp:"
    DELETE_PACK = "dp:"
    ADD_STICKER = "as:"
    CONFIRM_DELETE = "cd:"
    CANCEL_DELETE = "xd:"
    PACK_INFO = "pack_info:"
    NEXT_PAGE = "np:"
    PREV_PAGE = "pp:"
    BACK_TO_MANAGE = "back_to_manage"

def get_back_to_manage_keyboard(lang: dict):
    back_text = get_text_from_dict(lang, "B_BACK") or "⬅️ 𝖡𝖺𝖼𝗄"
    builder = InlineKeyboardBuilder()
    builder.button(text=back_text, callback_data=PackManagementCallback.BACK_TO_MANAGE)
    return builder.as_markup()


def get_no_packs_keyboard(lang: dict):
    create_pack_text = get_text_from_dict(lang, "B_CREATE_NEW_PACK") or "𝖢𝗋𝖾𝖺𝗍𝖾 𝖭𝖾𝗐 𝖯𝖺𝖼𝗄"
    back_text = get_text_from_dict(lang, "B_BACK") or "⬅️ 𝖡𝖺𝖼𝗄"
    builder = InlineKeyboardBuilder()
    builder.button(text=create_pack_text, callback_data=PackManagementCallback.CREATE_NEW_PACK)
    builder.button(text=back_text, callback_data=SharedCallbacks.BACK_TO_MAIN)
    builder.adjust(1, 1)
    return builder.as_markup()


def get_pack_link_keyboard(lang: dict, pack_link: str):
    pack_link_text = get_text_from_dict(lang, "B_PACK_LINK") or "🔗 𝖯𝖺𝖼𝗄 𝖫𝗂𝗇𝗄"
    builder = InlineKeyboardBuilder()
    builder.button(text=pack_link_text, url=pack_link)
    builder.adjust(1)
    return builder.as_markup()


async def get_manage_packs_keyboard(lang: dict, user_id: int, page: int = 0):
    builder = InlineKeyboardBuilder()
    packs, total = await get_user_packs_paginated(user_id, page)

    for pack in packs:
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        if len(pack_name) > 20:
            pack_name = pack_name[:17] + "..."
        callback_data = create_callback("pack_selected", pack['short_name'])
        builder.button(text=pack_name, callback_data=callback_data)

    builder.adjust(1)
    action_builder = InlineKeyboardBuilder()

    if page > 0:
        prev_text = get_text_from_dict(lang, "B_PREVIOUS") or "⬅️ 𝖯𝗋𝖾𝗏𝗂𝗈𝗎𝗌"
        action_builder.button(text=prev_text, callback_data=create_callback("prev_page", str(page - 1)))

    create_pack_text = get_text_from_dict(lang, "B_CREATE_NEW_PACK") or "🆕 𝖢𝗋𝖾𝖺𝗍𝖾 𝖭𝖾𝗐 𝖯𝖺𝖼𝗄"
    action_builder.button(text=create_pack_text, callback_data=PackManagementCallback.CREATE_NEW_PACK)

    if (page + 1) * 6 < total:
        next_text = get_text_from_dict(lang, "B_NEXT") or "𝖭𝖾𝗑𝗍 ➡️"
        action_builder.button(text=next_text, callback_data=create_callback("next_page", str(page + 1)))

    back_text = get_text_from_dict(lang, "B_BACK") or "⬅️ 𝖡𝖺𝖼𝗄"
    action_builder.button(text=back_text, callback_data=SharedCallbacks.BACK_TO_MAIN)
    action_builder.adjust(2, 1, 1)

    return builder.attach(action_builder).as_markup()


def get_pack_options_keyboard(lang: dict, short_name: str):
    builder = InlineKeyboardBuilder()

    rename_text = get_text_from_dict(lang, "B_RENAME_PACK") or "𝖱𝖾𝗇𝖺𝗆𝖾 𝖯𝖺𝖼𝗄"
    builder.button(text=rename_text, callback_data=create_callback("rename_pack", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}rename")

    add_sticker_text = get_text_from_dict(lang, "B_ADD_STICKER") or "𝖠𝖽𝖽 𝖲𝗍𝗂𝖼𝗄𝖾𝗋"
    builder.button(text=add_sticker_text, callback_data=create_callback("add_sticker", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}add")

    delete_text = get_text_from_dict(lang, "B_DELETE_PACK") or "🗑️ 𝖣𝖾𝗅𝖾𝗍𝖾 𝖯𝖺𝖼𝗄"
    builder.button(text=delete_text, callback_data=create_callback("delete_pack", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}delete")

    back_text = get_text_from_dict(lang, "B_BACK") or "⬅️ 𝖡𝖺𝖼𝗄"
    builder.button(text=back_text, callback_data=PackManagementCallback.BACK_TO_MANAGE)

    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def get_delete_confirmation_keyboard(lang: dict, short_name: str):
    confirm_text = get_text_from_dict(lang, "B_CONFIRM") or "𝖸𝖾𝗌, 𝖣𝖾𝗅𝖾𝗍𝖾"
    cancel_text = get_text_from_dict(lang, "B_CANCEL") or "𝖢𝖺𝗇𝖼𝖾𝗅"
    builder = InlineKeyboardBuilder()
    builder.button(text=confirm_text, callback_data=create_callback("confirm_delete", short_name))
    builder.button(text=cancel_text, callback_data=create_callback("cancel_delete", short_name))
    builder.adjust(2)
    return builder.as_markup()

@router.callback_query(F.data == SharedCallbacks.MANAGE_PACKS)
async def manage_packs_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)
        packs, total = await get_user_packs_paginated(user_id)

        if total == 0:
            no_packs_msg = (
                get_text_from_dict(lang, "NO_PACKS_MESSAGE")
                or " <b>𝖭𝗈 𝗉𝖺𝖼𝗄𝗌 𝗒𝖾𝗍.</b>\n𝖢𝗋𝖾𝖺𝗍𝖾 𝗒𝗈𝗎𝗋 𝖿𝗂𝗋𝗌𝗍 𝗍𝗈 𝗀𝖾𝗍 𝗌𝗍𝖺𝗋𝗍𝖾𝖽."
            )
            await safe_edit_message(callback, no_packs_msg, get_no_packs_keyboard(lang))
        else:
            manage_msg = (
                get_text_from_dict(lang, "MANAGE_PACKS_MESSAGE")
                or "<b>𝖸𝗈𝗎𝗋 𝖲𝗍𝗂𝖼𝗄𝖾𝗋 𝖯𝖺𝖼𝗄𝗌</b>"
            )
            await safe_edit_message(callback, manage_msg, await get_manage_packs_keyboard(lang, user_id))
    except Exception as e:
        logger.error(f"Error in manage_packs_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.PACK_SELECTED))
async def pack_selected_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)

        if not short_name:
            expired_msg = (
                get_text_from_dict(lang, "SESSION_EXPIRED")
                or "Please send /start again to continue."
            )
            await callback.answer(expired_msg, show_alert=True)
            return

        pack = await get_pack_by_short_name(short_name)
        if not pack:
            await manage_packs_callback(callback)
            return

        try:
            telegram_pack = await bot.get_sticker_set(short_name)
            real_count = len(telegram_pack.stickers)
            await update_pack_sticker_count(short_name, real_count)

        except TelegramBadRequest:
            await delete_pack_by_short_name(short_name)
            ghost_msg = (
                get_text_from_dict(lang, "PACK_DELETED_FROM_TELEGRAM")
                or "❌ <b>Pack Not Found</b>\n\nThis pack was deleted from Telegram and has been removed from your list."
            )
            await callback.answer(ghost_msg, show_alert=True)
            await manage_packs_callback(callback)
            return

        full_pack_name = pack["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"

        pack_options_msg = get_text_from_dict(
            lang,
            "PACK_OPTIONS_MESSAGE",
            pack_link=pack_link,
            pack_name=escape_html(full_pack_name),
            sticker_count=real_count
        ) or f"🛠️ <b>𝖯𝖺𝖼𝗄 𝖮𝗉𝗍𝗂𝗈𝗇𝗌</b>\n\n<a href=\"{pack_link}\">{escape_html(full_pack_name)}</a>\n<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌:</b> {real_count}/120"

        await safe_edit_message(callback, pack_options_msg, get_pack_options_keyboard(lang, short_name))
    except Exception as e:
        logger.error(f"Error in pack_selected_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.PACK_INFO))
async def pack_info_callback(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)
        info_type = callback.data.split(":")[1]

        if info_type == "rename":
            msg = (
                get_text_from_dict(lang, "RENAME_PACK_INFO")
                or "✏️ 𝖢𝗁𝖺𝗇𝗀𝖾 𝗒𝗈𝗎𝗋 𝗉𝖺𝖼𝗄'𝗌 𝗇𝖺𝗆𝖾."
            )
        elif info_type == "add":
            msg = (
                get_text_from_dict(lang, "ADD_STICKER_INFO")
                or "🎨 𝖠𝖽𝖽 𝗎𝗉 𝗍𝗈 120 𝗌𝗍𝗂𝖼𝗄𝖾𝗋𝗌 (𝗂𝗆𝖺𝗀𝖾𝗌, 𝗏𝗂𝖽𝖾𝗈𝗌, 𝗀𝗂𝖿𝗌)."
            )
        elif info_type == "delete":
            msg = (
                get_text_from_dict(lang, "DELETE_PACK_INFO")
                or "🗑️ 𝖯𝖾𝗋𝗆𝖺𝗇𝖾𝗇𝗍𝗅𝗒 𝖽𝖾𝗅𝖾𝗍𝖾 𝗍𝗁𝗂𝗌 𝗉𝖺𝖼𝗄. 𝖳𝗁𝗂𝗌 𝖼𝖺𝗇𝗇𝗈𝗍 𝖻𝖾 𝗎𝗇𝖽𝗈𝗇𝖾."
            )
        else:
            msg = "Information about this action."

        await callback.answer(msg, show_alert=True)
    except Exception as e:
        logger.error(f"Error in pack_info_callback: {e}")
        await callback.answer("Error showing info.", show_alert=True)


@router.callback_query(F.data.startswith(PackManagementCallback.RENAME_PACK))
async def rename_pack_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)

        if not short_name:
            expired_msg = (
                get_text_from_dict(lang, "SESSION_EXPIRED")
                or "❌ Session expired. Please try again."
            )
            await callback.answer(expired_msg, show_alert=True)
            return

        pack = await get_pack_by_short_name(short_name)
        if pack:
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            escaped_pack_name = escape_html(pack_name)

            rename_msg = get_text_from_dict(
                lang, "RENAME_PACK_MESSAGE", pack_name=escaped_pack_name
            ) or f"✏️ <b>𝖱𝖾𝗇𝖺𝗆𝖾 𝖯𝖺𝖼𝗄</b>\n𝖲𝖾𝗇𝖽 𝖺 𝗇𝖾𝗐 𝗇𝖺𝗆𝖾 𝖿𝗈𝗋 <b>\"{escaped_pack_name}\"</b>.\n(𝖬𝖺𝗑 𝟨𝟦 𝖼𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌, 𝖾𝗆𝗈𝗃𝗂𝗌 𝖺𝗅𝗅𝗈𝗐𝖾𝖽)"

            await safe_edit_message(callback, rename_msg, get_back_to_manage_keyboard(lang))
            await state.set_state(PackManagementStates.waiting_for_rename_pack_name)
            await state.update_data(
                short_name=short_name,
                bot_message_id=callback.message.message_id,
                chat_id=callback.message.chat.id
            )
    except Exception as e:
        logger.error(f"Error in rename_pack_callback: {e}")


@router.message(PackManagementStates.waiting_for_rename_pack_name)
async def process_rename_pack_name(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    short_name = data.get("short_name")
    bot_message_id = data.get("bot_message_id")
    chat_id = data.get("chat_id")
    user_id = message.from_user.id
    _, lang = await get_lang_dict(user_id)

    if not message.text:
        invalid_msg = (
            get_text_from_dict(lang, "PACK_NAME_SEND_VALID")
            or "Please send a valid pack name."
        )
        await message.reply(invalid_msg)
        return

    new_name = message.text.strip()
    is_valid, error = validate_pack_name(new_name)

    if not is_valid:
        if error == "pack_name_too_long":
            too_long_msg = (
                get_text_from_dict(lang, "PACK_NAME_TOO_LONG")
                or "Pack name is too long! Maximum 64 characters."
            )
            await message.reply(too_long_msg)
        else:
            invalid_msg = (
                get_text_from_dict(lang, "PACK_NAME_INVALID_SIMPLE")
                or "Invalid pack name!"
            )
            await message.reply(invalid_msg)
        return

    formatted_name = format_pack_name(new_name)

    try:
        await bot.set_sticker_set_title(name=short_name, title=formatted_name)
        await update_pack_name(short_name, formatted_name)

        try:
            await message.delete()
        except:
            pass

        try:
            telegram_pack = await bot.get_sticker_set(short_name)
            real_count = len(telegram_pack.stickers)
            await update_pack_sticker_count(short_name, real_count)
        except:
            pack_db = await get_pack_by_short_name(short_name)
            real_count = pack_db.get("sticker_count", 0) if pack_db else 0

        pack_link = f"https://t.me/addstickers/{short_name}"
        escaped_new_name = escape_html(formatted_name)

        pack_options_msg = get_text_from_dict(
            lang,
            "PACK_OPTIONS_MESSAGE",
            pack_link=pack_link,
            pack_name=escaped_new_name,
            sticker_count=real_count
        ) or f"🛠️ <b>𝖯𝖺𝖼𝗄 𝖮𝗉𝗍𝗂𝗈𝗇𝗌</b>\n\n<a href=\"{pack_link}\">{escaped_new_name}</a>\n<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌:</b> {real_count}/120"

        options_kb = get_pack_options_keyboard(lang, short_name)

        if bot_message_id and chat_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=bot_message_id,
                    text=pack_options_msg,
                    reply_markup=options_kb
                )
            except:
                await message.answer(pack_options_msg, reply_markup=options_kb)
        else:
            await message.answer(pack_options_msg, reply_markup=options_kb)

    except Exception as e:
        logger.error(f"Error renaming pack: {e}")
        error_msg = (
            get_text_from_dict(lang, "ERROR_OCCURRED")
            or " <b>𝖮𝗈𝗉𝗌 — 𝗌𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀.</b>"
        )
        await message.reply(error_msg)

    await state.clear()


@router.callback_query(F.data.startswith(PackManagementCallback.DELETE_PACK))
async def delete_pack_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)

        if not short_name:
            expired_msg = (
                get_text_from_dict(lang, "SESSION_EXPIRED")
                or "❌ Session expired. Please try again."
            )
            await callback.answer(expired_msg, show_alert=True)
            return

        pack = await get_pack_by_short_name(short_name)
        if pack:
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            escaped_pack_name = escape_html(pack_name)
            sticker_count = pack.get("sticker_count", 0)
            created_date = pack["created_at"].strftime("%Y-%m-%d") if pack.get("created_at") else "Unknown"

            delete_confirm_msg = get_text_from_dict(
                lang,
                "DELETE_PACK_CONFIRMATION",
                pack_name=escaped_pack_name,
                sticker_count=sticker_count,
                created_date=created_date
            ) or (
                f"🗑️ <b>𝖣𝖾𝗅𝖾𝗍𝖾 𝖯𝖺𝖼𝗄</b>\n\n"
                f"<b>{escaped_pack_name}</b>\n"
                f"<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌:</b> {sticker_count}\n"
                f"<b>𝖢𝗋𝖾𝖺𝗍𝖾𝖽:</b> {created_date}\n\n"
                f"𝖠𝗋𝖾 𝗒𝗈𝗎 𝗌𝗎𝗋𝖾? 𝖳𝗁𝗂𝗌 𝖼𝖺𝗇𝗇𝗈𝗍 𝖻𝖾 𝗎𝗇𝖽𝗈𝗇𝖾."
            )

            await safe_edit_message(
                callback,
                delete_confirm_msg,
                get_delete_confirmation_keyboard(lang, short_name)
            )
    except Exception as e:
        logger.error(f"Error in delete_pack_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.CONFIRM_DELETE))
async def confirm_delete_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)

        if not short_name:
            expired_msg = (
                get_text_from_dict(lang, "SESSION_EXPIRED")
                or "❌ Session expired. Please try again."
            )
            await callback.answer(expired_msg, show_alert=True)
            return

        pack = await get_pack_by_short_name(short_name)
        if pack:
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            escaped_pack_name = escape_html(pack_name)

            try:
                await bot.delete_sticker_set(short_name)
            except TelegramBadRequest:
                pass
            except Exception as e:
                logger.error(f"Error deleting sticker set from Telegram: {e}")

            await delete_pack_by_short_name(short_name)

            deleted_msg = get_text_from_dict(
                lang, "PACK_DELETED_SUCCESS", pack_name=escaped_pack_name
            ) or f"✅ <b>𝖯𝖺𝖼𝗄 𝖽𝖾𝗅𝖾𝗍𝖾𝖽!</b>\n\n<b>\"{escaped_pack_name}\"</b> 𝗁𝖺𝗌 𝖻𝖾𝖾𝗇 𝗋𝖾𝗆𝗈𝗏𝖾𝖽."

            await safe_edit_message(callback, deleted_msg, get_back_to_manage_keyboard(lang))
        else:
            await manage_packs_callback(callback)

    except Exception as e:
        logger.error(f"Error in confirm_delete_callback: {e}")
        _, lang = await get_lang_dict(callback.from_user.id)
        error_msg = (
            get_text_from_dict(lang, "ERROR_OCCURRED")
            or " <b>𝖮𝗈𝗉𝗌 — 𝗌𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀.</b>"
        )
        await safe_edit_message(callback, error_msg)


@router.callback_query(F.data.startswith(PackManagementCallback.CANCEL_DELETE))
async def cancel_delete_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)

        if not short_name:
            expired_msg = (
                get_text_from_dict(lang, "SESSION_EXPIRED")
                or "❌ Session expired. Please try again."
            )
            await callback.answer(expired_msg, show_alert=True)
            return

        pack = await get_pack_by_short_name(short_name)
        if not pack:
            await manage_packs_callback(callback)
            return

        try:
            telegram_pack = await bot.get_sticker_set(short_name)
            real_count = len(telegram_pack.stickers)
            await update_pack_sticker_count(short_name, real_count)
        except TelegramBadRequest:
            await delete_pack_by_short_name(short_name)
            ghost_msg = (
                get_text_from_dict(lang, "PACK_DELETED_FROM_TELEGRAM")
                or "❌ <b>Pack Not Found</b>\n\nThis pack was deleted from Telegram and has been removed from your list."
            )
            await callback.answer(ghost_msg, show_alert=True)
            await manage_packs_callback(callback)
            return
        except:
            real_count = pack.get("sticker_count", 0)

        full_pack_name = pack["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"

        pack_options_msg = get_text_from_dict(
            lang,
            "PACK_OPTIONS_MESSAGE",
            pack_link=pack_link,
            pack_name=escape_html(full_pack_name),
            sticker_count=real_count
        ) or f"🛠️ <b>𝖯𝖺𝖼𝗄 𝖮𝗉𝗍𝗂𝗈𝗇𝗌</b>\n\n<a href=\"{pack_link}\">{escape_html(full_pack_name)}</a>\n<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌:</b> {real_count}/120"

        await safe_edit_message(callback, pack_options_msg, get_pack_options_keyboard(lang, short_name))
    except Exception as e:
        logger.error(f"Error in cancel_delete_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.ADD_STICKER))
async def add_sticker_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)

        if not short_name:
            expired_msg = (
                get_text_from_dict(lang, "SESSION_EXPIRED")
                or "❌ Session expired. Please try again."
            )
            await callback.answer(expired_msg, show_alert=True)
            return

        pack = await get_pack_by_short_name(short_name)
        if pack:
            if pack.get("sticker_count", 0) >= 120:
                return

            await state.set_state(PackManagementStates.waiting_for_sticker_to_add)
            await state.update_data(
                short_name=short_name,
                pack_data=pack,
                sticker_count=pack.get("sticker_count", 0)
            )

            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            escaped_pack_name = escape_html(pack_name)

            add_sticker_msg = get_text_from_dict(
                lang,
                "ADD_STICKER_INSTRUCTIONS",
                pack_name=escaped_pack_name,
                sticker_count=pack.get("sticker_count", 0)
            ) or f"<b>Add Stickers to {escaped_pack_name}</b>\n\nSend me images, videos, GIFs, or stickers to add to your pack.\n\n<b>Current count:</b> {pack.get('sticker_count', 0)}/120"

            await callback.message.delete()
            await callback.message.answer(add_sticker_msg)
    except Exception as e:
        logger.error(f"Error in add_sticker_callback: {e}")


@router.message(PackManagementStates.waiting_for_sticker_to_add)
async def process_sticker_addition(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    short_name = data.get("short_name")
    pack_data = data.get("pack_data")
    current_count = data.get("sticker_count", 0)
    user_id = message.from_user.id
    _, lang = await get_lang_dict(user_id)

    if current_count >= 120:
        pack_full_msg = (
            get_text_from_dict(lang, "PACK_FULL_CANNOT_ADD")
            or "❌ Pack is full! Cannot add more stickers."
        )
        await message.reply(pack_full_msg)
        await state.clear()
        return

    if not message.photo and not message.sticker and not message.animation and not message.video:
        cancel_msg = (
            get_text_from_dict(lang, "STATE_CANCELLED_MESSAGE")
            or "<b>Operation cancelled.</b>"
        )
        await message.reply(cancel_msg)
        await state.clear()
        return

    if await is_sticker_processing(user_id):
        wait_msg = (
            get_text_from_dict(lang, "STICKER_PROCESSING_WAIT")
            or "⏳ <b>Please wait!</b>\n\nYour previous sticker is still being added. Try again in a moment."
        )
        await message.reply(wait_msg)
        return

    media = None
    media_type = None

    if message.photo:
        media = message.photo[-1]
        media_type = "photo"
    elif message.sticker:
        media = message.sticker
        media_type = "sticker"
    elif message.animation:
        media = message.animation
        media_type = "animation"
    elif message.video:
        media = message.video
        media_type = "video"

    if media_type == "video":
        file_size_mb = get_file_size_mb(media.file_size)
        if file_size_mb > MAX_VIDEO_SIZE_MB:
            video_large_msg = (
                get_text_from_dict(lang, "VIDEO_TOO_LARGE")
                or " <b>𝖵𝗂𝖽𝖾𝗈 𝗍𝗈𝗈 𝗅𝖺𝗋𝗀𝖾 (𝗈𝗏𝖾𝗋 𝟦𝖬𝖡)</b>"
            )
            await message.reply(video_large_msg)
            return

    processing_msg_text = (
        get_text_from_dict(lang, "ADDING_STICKER_WAIT")
        or "⌛ Adding sticker to your pack..."
    )
    processing_msg = await message.reply(processing_msg_text)

    start_sticker_processing(user_id)

    try:
        success, pack_full = await add_sticker_to_pack(
            bot=bot,
            user_id=user_id,
            pack_short_name=short_name,
            pack_data=pack_data,
            media=media,
            media_type=media_type,
            message=message,
            state=state
        )

        if success:
            try:
                telegram_pack = await bot.get_sticker_set(short_name)
                real_count = len(telegram_pack.stickers)
                await update_pack_sticker_count(short_name, real_count)
                await state.update_data(sticker_count=real_count)
            except:
                new_count = current_count + 1
                await state.update_data(sticker_count=new_count)
                await update_pack_sticker_count(short_name, new_count)

            pack_link = f"https://t.me/addstickers/{short_name}"
            success_msg = (
                get_text_from_dict(lang, "STICKER_ADDED_SUCCESS")
                or "✅ <b>Sticker added successfully!</b>"
            )
            await processing_msg.edit_text(
                success_msg,
                reply_markup=get_pack_link_keyboard(lang, pack_link)
            )

        elif pack_full:
            pack_full_msg = (
                get_text_from_dict(lang, "PACK_FULL_120_LIMIT")
                or "❌ <b>Pack is full!</b>\n\nThis pack has reached the maximum limit of 120 stickers."
            )
            await processing_msg.edit_text(pack_full_msg)
            await state.clear()
        else:
            fail_msg = (
                get_text_from_dict(lang, "STICKER_ADD_FAILED")
                or "❌ Failed to add sticker. Please try again with a different file."
            )
            await processing_msg.edit_text(fail_msg)
    finally:
        stop_sticker_processing(user_id)


@router.callback_query(F.data == PackManagementCallback.CREATE_NEW_PACK)
async def create_new_pack_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)

        create_pack_msg = get_text_from_dict(
            lang, "CREATE_NEW_PACK_PROMPT"
        ) or "<b>Let's create a new sticker pack!</b>\n\n<b>First, send me the sticker you want to start your pack with.</b>\nIt can be GIF, video, image or sticker"

        await state.set_state(PackManagementStates.waiting_for_first_sticker)
        await safe_edit_message(callback, create_pack_msg, get_back_to_manage_keyboard(lang))
    except Exception as e:
        logger.error(f"Error in create_new_pack_callback: {e}")


@router.message(PackManagementStates.waiting_for_first_sticker)
async def process_first_sticker(message: Message, state: FSMContext):
    user_id = message.from_user.id
    _, lang = await get_lang_dict(user_id)

    if not message.photo and not message.sticker and not message.animation and not message.video:
        cancel_msg = (
            get_text_from_dict(lang, "STATE_CANCELLED_MESSAGE")
            or "<b>Operation cancelled.</b>"
        )
        await message.reply(cancel_msg)
        await state.clear()
        return

    media = None
    media_type = None

    if message.photo:
        media = message.photo[-1]
        media_type = "photo"
    elif message.sticker:
        media = message.sticker
        media_type = "sticker"
    elif message.animation:
        media = message.animation
        media_type = "animation"
    elif message.video:
        media = message.video
        media_type = "video"

    if media_type == "video":
        file_size_mb = get_file_size_mb(media.file_size)
        if file_size_mb > MAX_VIDEO_SIZE_MB:
            video_large_msg = (
                get_text_from_dict(lang, "VIDEO_TOO_LARGE")
                or " <b>𝖵𝗂𝖽𝖾𝗈 𝗍𝗈𝗈 𝗅𝖺𝗋𝗀𝖾 (𝗈𝗏𝖾𝗋 𝟦𝖬𝖡)</b>"
            )
            await message.reply(video_large_msg)
            return

    await state.update_data(first_sticker=media, first_sticker_type=media_type)

    got_it_msg = get_text_from_dict(
        lang, "GOT_IT_SEND_PACK_NAME"
    ) or "👍 <b>Got it!</b> Now send me a name for your pack.\n\n<i>You can use any symbols, emojis, or fonts in the name.</i>"

    await message.reply(got_it_msg)
    await state.set_state(PackManagementStates.waiting_for_new_pack_name)


@router.message(PackManagementStates.waiting_for_new_pack_name)
async def process_new_pack_name(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    _, lang = await get_lang_dict(user_id)

    if not message.text:
        invalid_msg = (
            get_text_from_dict(lang, "PACK_NAME_SEND_VALID")
            or "❌ Please send a valid pack name."
        )
        await message.reply(invalid_msg)
        return

    pack_name = message.text.strip()
    data = await state.get_data()
    first_sticker = data.get("first_sticker")
    first_sticker_type = data.get("first_sticker_type")

    if not first_sticker:
        sticker_lost_msg = (
            get_text_from_dict(lang, "STICKER_DATA_LOST")
            or "❌ Sticker data lost. Please start over."
        )
        await message.reply(sticker_lost_msg)
        await state.clear()
        return

    if len(pack_name) > 64:
        too_long_msg = (
            get_text_from_dict(lang, "PACK_NAME_TOO_LONG")
            or "❌ Pack name is too long! Maximum 64 characters."
        )
        await message.reply(too_long_msg)
        return

    if len(pack_name) == 0:
        empty_msg = (
            get_text_from_dict(lang, "PACK_NAME_EMPTY")
            or "❌ Pack name cannot be empty."
        )
        await message.reply(empty_msg)
        return

    formatted_name = format_pack_name(pack_name)
    short_name = generate_short_name(pack_name, user_id)

    creating_msg = (
        get_text_from_dict(lang, "CREATING_PACK_WAIT")
        or "⌛ <b>Creating your sticker pack...</b>\nPlease wait a moment"
    )
    processing_msg = await message.reply(creating_msg)

    temp_files = []

    try:
        sticker_file = None
        sticker_format = None

        if first_sticker_type == "sticker":
            sticker_file = first_sticker.file_id
            sticker_format = "static" if not first_sticker.is_video else "video"

        elif first_sticker_type == "photo":
            file = await bot.get_file(first_sticker.file_id)
            temp_dir = create_temp_dir()
            input_path = os.path.join(temp_dir, f"{user_id}_first_input.jpg")
            output_path = os.path.join(temp_dir, f"{user_id}_first_output.webp")
            temp_files.extend([input_path, output_path])
            await bot.download_file(file.file_path, input_path)
            if await convert_image_to_webp(input_path, output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webp")
                sticker_format = "static"
            else:
                raise Exception("Failed to convert image")

        elif first_sticker_type in ["animation", "video"]:
            file = await bot.get_file(first_sticker.file_id)
            temp_dir = create_temp_dir()
            input_path = os.path.join(temp_dir, f"{user_id}_first_input.mp4")
            output_path = os.path.join(temp_dir, f"{user_id}_first_output.webm")
            temp_files.extend([input_path, output_path])
            await bot.download_file(file.file_path, input_path)
            conversion_success = await convert_video_to_webm(input_path, output_path)
            if conversion_success and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webm")
                sticker_format = "video"
            else:
                cleanup_temp_files(*temp_files)
                fail_msg = (
                    get_text_from_dict(lang, "VIDEO_COMPRESSION_FAILED")
                    or " <b>𝗎𝗇𝖺𝖻𝗅𝖾 𝗍𝗈 𝗉𝗋𝗈𝖼𝖾𝗌𝗌 𝗏𝗂𝖽𝖾𝗈</b>"
                )
                await processing_msg.edit_text(fail_msg)
                await state.clear()
                return

        if not sticker_file:
            raise Exception("Failed to prepare sticker file")

        sticker = InputSticker(
            sticker=sticker_file,
            emoji_list=[get_random_emoji()],
            format=sticker_format
        )

        await bot.create_new_sticker_set(
            user_id=user_id,
            name=short_name,
            title=formatted_name,
            stickers=[sticker]
        )

        pack_link = f"https://t.me/addstickers/{short_name}"
        await create_sticker_pack(user_id=user_id, pack_name=formatted_name, short_name=short_name)
        await update_pack_sticker_count(short_name, 1)
        cleanup_temp_files(*temp_files)

        success_message = get_text_from_dict(
            lang,
            "PACK_CREATED_SUCCESS",
            pack_link=pack_link,
            pack_name=escape_html(formatted_name)
        ) or f"✅ <b>Your sticker pack has been created successfully!</b>\n\n<a href=\"{pack_link}\">{escape_html(formatted_name)}</a>"

        await processing_msg.edit_text(
            success_message,
            reply_markup=get_pack_options_keyboard(lang, short_name)
        )

    except Exception as e:
        logger.error(f"Error creating new pack: {e}")
        cleanup_temp_files(*temp_files)
        error_msg_str = str(e)
        if "STICKERSET_INVALID" in error_msg_str or "invalid" in error_msg_str.lower():
            fail_msg = (
                get_text_from_dict(lang, "PACK_CREATE_FAILED_TEMP")
                or "❌ <b>Failed to create pack.</b>\nThis might be a temporary issue. Please try again."
            )
            await processing_msg.edit_text(fail_msg)
        else:
            error_msg = (
                get_text_from_dict(lang, "ERROR_OCCURRED")
                or " <b>𝖮𝗈𝗉𝗌 — 𝗌𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀.</b>"
            )
            await processing_msg.edit_text(error_msg)

    await state.clear()


@router.callback_query(F.data.startswith(PackManagementCallback.NEXT_PAGE))
async def next_page_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        page_str = parse_callback(callback.data)
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)

        if not page_str:
            expired_msg = (
                get_text_from_dict(lang, "SESSION_EXPIRED")
                or "❌ Session expired. Please try again."
            )
            await callback.answer(expired_msg, show_alert=True)
            return

        page = int(page_str)
        manage_msg = (
            get_text_from_dict(lang, "MANAGE_PACKS_MESSAGE")
            or "<b>𝖸𝗈𝗎𝗋 𝖲𝗍𝗂𝖼𝗄𝖾𝗋 𝖯𝖺𝖼𝗄𝗌</b>"
        )
        await safe_edit_message(callback, manage_msg, await get_manage_packs_keyboard(lang, user_id, page))
    except Exception as e:
        logger.error(f"Error in next_page_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.PREV_PAGE))
async def prev_page_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        page_str = parse_callback(callback.data)
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)

        if not page_str:
            expired_msg = (
                get_text_from_dict(lang, "SESSION_EXPIRED")
                or "❌ Session expired. Please try again."
            )
            await callback.answer(expired_msg, show_alert=True)
            return

        page = int(page_str)
        manage_msg = (
            get_text_from_dict(lang, "MANAGE_PACKS_MESSAGE")
            or "<b>𝖸𝗈𝗎𝗋 𝖲𝗍𝗂𝖼𝗄𝖾𝗋 𝖯𝖺𝖼𝗄𝗌</b>"
        )
        await safe_edit_message(callback, manage_msg, await get_manage_packs_keyboard(lang, user_id, page))
    except Exception as e:
        logger.error(f"Error in prev_page_callback: {e}")


@router.callback_query(F.data == PackManagementCallback.BACK_TO_MANAGE)
async def back_to_manage_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        user_id = callback.from_user.id
        _, lang = await get_lang_dict(user_id)
        packs, total = await get_user_packs_paginated(user_id)

        if total == 0:
            no_packs_msg = (
                get_text_from_dict(lang, "NO_PACKS_MESSAGE")
                or " <b>𝖭𝗈 𝗉𝖺𝖼𝗄𝗌 𝗒𝖾𝗍.</b>\n𝖢𝗋𝖾𝖺𝗍𝖾 𝗒𝗈𝗎𝗋 𝖿𝗂𝗋𝗌𝗍 𝗍𝗈 𝗀𝖾𝗍 𝗌𝗍𝖺𝗋𝗍𝖾𝖽."
            )
            await safe_edit_message(callback, no_packs_msg, get_no_packs_keyboard(lang))
        else:
            manage_msg = (
                get_text_from_dict(lang, "MANAGE_PACKS_MESSAGE")
                or "<b>𝖸𝗈𝗎𝗋 𝖲𝗍𝗂𝖼𝗄𝖾𝗋 𝖯𝖺𝖼𝗄𝗌</b>"
            )
            await safe_edit_message(callback, manage_msg, await get_manage_packs_keyboard(lang, user_id))
    except Exception as e:
        logger.error(f"Error in back_to_manage_callback: {e}")


@router.message(StateFilter(PackManagementStates), Command("cancel"))
async def cancel_pack_management(message: Message, state: FSMContext):
    user_id = message.from_user.id
    _, lang = await get_lang_dict(user_id)
    await state.clear()
    cancel_msg = (
        get_text_from_dict(lang, "OPERATION_CANCELLED")
        or "Operation cancelled."
    )
    await message.reply(cancel_msg, reply_markup=get_back_to_main_keyboard(lang))
