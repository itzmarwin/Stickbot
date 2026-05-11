import logging
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InputSticker
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from callback_manager import create_callback, parse_callback
from mongo.userdb import get_user_language
from mongo.stickerdb import (
    get_user_packs_paginated, update_pack_name, delete_pack_by_short_name,
    get_pack_by_short_name, create_sticker_pack,
    update_pack_sticker_count
)
from utils.language import get_text, get_text_sync
from utils.fsm_states import PackManagementStates
from utils.helpers import validate_pack_name, format_pack_name, generate_short_name, get_file_size_mb
from utils.converters import convert_image_to_webp, convert_video_to_webm, cleanup_temp_files, create_temp_dir
from utils.html_utils import escape_html
from handlers.kang import add_sticker_to_pack, get_random_emoji
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


async def get_back_to_manage_keyboard(user_id: int):
    language = await get_user_language(user_id)
    back_text = get_text_sync(language, "B_BACK")
    if back_text is None:
        back_text = "⬅️ 𝖡𝖺𝖼𝗄"
    builder = InlineKeyboardBuilder()
    builder.button(text=back_text, callback_data=PackManagementCallback.BACK_TO_MANAGE)
    return builder.as_markup()


async def get_no_packs_keyboard(user_id: int):
    language = await get_user_language(user_id)
    create_pack_text = get_text_sync(language, "B_CREATE_NEW_PACK")
    if create_pack_text is None:
        create_pack_text = "𝖢𝗋𝖾𝖺𝗍𝖾 𝖭𝖾𝗐 𝖯𝖺𝖼𝗄"
    back_text = get_text_sync(language, "B_BACK")
    if back_text is None:
        back_text = "⬅️ 𝖡𝖺𝖼𝗄"
    builder = InlineKeyboardBuilder()
    builder.button(text=create_pack_text, callback_data=PackManagementCallback.CREATE_NEW_PACK)
    builder.button(text=back_text, callback_data=SharedCallbacks.BACK_TO_MAIN)
    builder.adjust(1, 1)
    return builder.as_markup()


async def get_pack_link_keyboard(user_id: int, pack_link: str):
    language = await get_user_language(user_id)
    pack_link_text = get_text_sync(language, "B_PACK_LINK")
    if pack_link_text is None:
        pack_link_text = "🔗 𝖯𝖺𝖼𝗄 𝖫𝗂𝗇𝗄"
    builder = InlineKeyboardBuilder()
    builder.button(text=pack_link_text, url=pack_link)
    builder.adjust(1)
    return builder.as_markup()


async def get_manage_packs_keyboard(user_id: int, page: int = 0):
    language = await get_user_language(user_id)
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
        prev_text = get_text_sync(language, "B_PREVIOUS")
        if prev_text is None:
            prev_text = "⬅️ 𝖯𝗋𝖾𝗏𝗂𝗈𝗎𝗌"
        action_builder.button(text=prev_text, callback_data=create_callback("prev_page", str(page - 1)))

    create_pack_text = get_text_sync(language, "B_CREATE_NEW_PACK")
    if create_pack_text is None:
        create_pack_text = "🆕 𝖢𝗋𝖾𝖺𝗍𝖾 𝖭𝖾𝗐 𝖯𝖺𝖼𝗄"
    action_builder.button(text=create_pack_text, callback_data=PackManagementCallback.CREATE_NEW_PACK)

    if (page + 1) * 6 < total:
        next_text = get_text_sync(language, "B_NEXT")
        if next_text is None:
            next_text = "𝖭𝖾𝗑𝗍 ➡️"
        action_builder.button(text=next_text, callback_data=create_callback("next_page", str(page + 1)))

    back_text = get_text_sync(language, "B_BACK")
    if back_text is None:
        back_text = "⬅️ 𝖡𝖺𝖼𝗄"
    action_builder.button(text=back_text, callback_data=SharedCallbacks.BACK_TO_MAIN)
    action_builder.adjust(2, 1, 1)

    return builder.attach(action_builder).as_markup()


async def get_pack_options_keyboard(user_id: int, short_name: str):
    language = await get_user_language(user_id)
    builder = InlineKeyboardBuilder()

    rename_text = get_text_sync(language, "B_RENAME_PACK")
    if rename_text is None:
        rename_text = "𝖱𝖾𝗇𝖺𝗆𝖾 𝖯𝖺𝖼𝗄"
    builder.button(text=rename_text, callback_data=create_callback("rename_pack", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}rename")

    add_sticker_text = get_text_sync(language, "B_ADD_STICKER")
    if add_sticker_text is None:
        add_sticker_text = "𝖠𝖽𝖽 𝖲𝗍𝗂𝖼𝗄𝖾𝗋"
    builder.button(text=add_sticker_text, callback_data=create_callback("add_sticker", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}add")

    delete_text = get_text_sync(language, "B_DELETE_PACK")
    if delete_text is None:
        delete_text = "🗑️ 𝖣𝖾𝗅𝖾𝗍𝖾 𝖯𝖺𝖼𝗄"
    builder.button(text=delete_text, callback_data=create_callback("delete_pack", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}delete")

    back_text = get_text_sync(language, "B_BACK")
    if back_text is None:
        back_text = "⬅️ 𝖡𝖺𝖼𝗄"
    builder.button(text=back_text, callback_data=PackManagementCallback.BACK_TO_MANAGE)

    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


async def get_delete_confirmation_keyboard(user_id: int, short_name: str):
    language = await get_user_language(user_id)

    confirm_text = get_text_sync(language, "B_CONFIRM")
    if confirm_text is None:
        confirm_text = "𝖸𝖾𝗌, 𝖣𝖾𝗅𝖾𝗍𝖾"

    cancel_text = get_text_sync(language, "B_CANCEL")
    if cancel_text is None:
        cancel_text = "𝖢𝖺𝗇𝖼𝖾𝗅"

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
        packs, total = await get_user_packs_paginated(user_id)

        if total == 0:
            no_packs_msg = await get_text(user_id, "NO_PACKS_MESSAGE")
            if no_packs_msg is None:
                no_packs_msg = " <b>𝖭𝗈 𝗉𝖺𝖼𝗄𝗌 𝗒𝖾𝗍.</b>\n𝖢𝗋𝖾𝖺𝗍𝖾 𝗒𝗈𝗎𝗋 𝖿𝗂𝗋𝗌𝗍 𝗍𝗈 𝗀𝖾𝗍 𝗌𝗍𝖺𝗋𝗍𝖾𝖽."
            await safe_edit_message(callback, no_packs_msg, await get_no_packs_keyboard(user_id))
        else:
            manage_msg = await get_text(user_id, "MANAGE_PACKS_MESSAGE")
            if manage_msg is None:
                manage_msg = "<b>𝖸𝗈𝗎𝗋 𝖲𝗍𝗂𝖼𝗄𝖾𝗋 𝖯𝖺𝖼𝗄𝗌</b>"
            await safe_edit_message(callback, manage_msg, await get_manage_packs_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in manage_packs_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.PACK_SELECTED))
async def pack_selected_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id

        if not short_name:
            expired_msg = await get_text(user_id, "SESSION_EXPIRED")
            if expired_msg is None:
                expired_msg = "Please send /start again to continue."
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
            ghost_msg = await get_text(user_id, "PACK_DELETED_FROM_TELEGRAM")
            if ghost_msg is None:
                ghost_msg = "❌ <b>Pack Not Found</b>\n\nThis pack was deleted from Telegram and has been removed from your list."
            await callback.answer(ghost_msg, show_alert=True)
            await manage_packs_callback(callback)
            return

        full_pack_name = pack["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"

        pack_options_msg = await get_text(
            user_id,
            "PACK_OPTIONS_MESSAGE",
            pack_link=pack_link,
            pack_name=escape_html(full_pack_name),
            sticker_count=real_count
        )

        if pack_options_msg is None:
            pack_options_msg = f"🛠️ <b>𝖯𝖺𝖼𝗄 𝖮𝗉𝗍𝗂𝗈𝗇𝗌</b>\n\n<a href=\"{pack_link}\">{escape_html(full_pack_name)}</a>\n<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌:</b> {real_count}/120"

        await safe_edit_message(callback, pack_options_msg, await get_pack_options_keyboard(user_id, short_name))
    except Exception as e:
        logger.error(f"Error in pack_selected_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.PACK_INFO))
async def pack_info_callback(callback: CallbackQuery):
    try:
        user_id = callback.from_user.id
        info_type = callback.data.split(":")[1]

        if info_type == "rename":
            msg = await get_text(user_id, "RENAME_PACK_INFO")
            if msg is None:
                msg = "✏️ 𝖢𝗁𝖺𝗇𝗀𝖾 𝗒𝗈𝗎𝗋 𝗉𝖺𝖼𝗄'𝗌 𝗇𝖺𝗆𝖾."
        elif info_type == "add":
            msg = await get_text(user_id, "ADD_STICKER_INFO")
            if msg is None:
                msg = "🎨 𝖠𝖽𝖽 𝗎𝗉 𝗍𝗈 120 𝗌𝗍𝗂𝖼𝗄𝖾𝗋𝗌 (𝗂𝗆𝖺𝗀𝖾𝗌, 𝗏𝗂𝖽𝖾𝗈𝗌, 𝗀𝗂𝖿𝗌)."
        elif info_type == "delete":
            msg = await get_text(user_id, "DELETE_PACK_INFO")
            if msg is None:
                msg = "🗑️ 𝖯𝖾𝗋𝗆𝖺𝗇𝖾𝗇𝗍𝗅𝗒 𝖽𝖾𝗅𝖾𝗍𝖾 𝗍𝗁𝗂𝗌 𝗉𝖺𝖼𝗄. 𝖳𝗁𝗂𝗌 𝖼𝖺𝗇𝗇𝗈𝗍 𝖻𝖾 𝗎𝗇𝖽𝗈𝗇𝖾."
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

        if not short_name:
            expired_msg = await get_text(user_id, "SESSION_EXPIRED")
            if expired_msg is None:
                expired_msg = "❌ Session expired. Please try again."
            await callback.answer(expired_msg, show_alert=True)
            return

        pack = await get_pack_by_short_name(short_name)

        if pack:
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            escaped_pack_name = escape_html(pack_name)

            rename_msg = await get_text(user_id, "RENAME_PACK_MESSAGE", pack_name=escaped_pack_name)
            if rename_msg is None:
                rename_msg = f"✏️ <b>𝖱𝖾𝗇𝖺𝗆𝖾 𝖯𝖺𝖼𝗄</b>\n𝖲𝖾𝗇𝖽 𝖺 𝗇𝖾𝗐 𝗇𝖺𝗆𝖾 𝖿𝗈𝗋 <b>\"{escaped_pack_name}\"</b>.\n(𝖬𝖺𝗑 𝟨𝟦 𝖼𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌, 𝖾𝗆𝗈𝗃𝗂𝗌 𝖺𝗅𝗅𝗈𝗐𝖾𝖽)"

            await safe_edit_message(callback, rename_msg, await get_back_to_manage_keyboard(user_id))

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

    if not message.text:
        invalid_msg = await get_text(user_id, "PACK_NAME_SEND_VALID")
        if invalid_msg is None:
            invalid_msg = "Please send a valid pack name."
        await message.reply(invalid_msg)
        return

    new_name = message.text.strip()
    is_valid, error = validate_pack_name(new_name)

    if not is_valid:
        if error == "pack_name_too_long":
            too_long_msg = await get_text(user_id, "PACK_NAME_TOO_LONG")
            if too_long_msg is None:
                too_long_msg = "Pack name is too long! Maximum 64 characters."
            await message.reply(too_long_msg)
        else:
            invalid_msg = await get_text(user_id, "PACK_NAME_INVALID_SIMPLE")
            if invalid_msg is None:
                invalid_msg = "Invalid pack name!"
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

        pack_options_msg = await get_text(
            user_id,
            "PACK_OPTIONS_MESSAGE",
            pack_link=pack_link,
            pack_name=escaped_new_name,
            sticker_count=real_count
        )

        if pack_options_msg is None:
            pack_options_msg = f"🛠️ <b>𝖯𝖺𝖼𝗄 𝖮𝗉𝗍𝗂𝗈𝗇𝗌</b>\n\n<a href=\"{pack_link}\">{escaped_new_name}</a>\n<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌:</b> {real_count}/120"

        if bot_message_id and chat_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=bot_message_id,
                    text=pack_options_msg,
                    reply_markup=await get_pack_options_keyboard(user_id, short_name)
                )
            except:
                await message.answer(pack_options_msg, reply_markup=await get_pack_options_keyboard(user_id, short_name))
        else:
            await message.answer(pack_options_msg, reply_markup=await get_pack_options_keyboard(user_id, short_name))

    except Exception as e:
        logger.error(f"Error renaming pack: {e}")
        error_msg = await get_text(user_id, "ERROR_OCCURRED")
        if error_msg is None:
            error_msg = " <b>𝖮𝗈𝗉𝗌 — 𝗌𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀.</b>"
        await message.reply(error_msg)

    await state.clear()


@router.callback_query(F.data.startswith(PackManagementCallback.DELETE_PACK))
async def delete_pack_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id

        if not short_name:
            expired_msg = await get_text(user_id, "SESSION_EXPIRED")
            if expired_msg is None:
                expired_msg = "❌ Session expired. Please try again."
            await callback.answer(expired_msg, show_alert=True)
            return

        pack = await get_pack_by_short_name(short_name)

        if pack:
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            escaped_pack_name = escape_html(pack_name)
            sticker_count = pack.get("sticker_count", 0)
            created_date = pack["created_at"].strftime("%Y-%m-%d") if pack.get("created_at") else "Unknown"

            delete_confirm_msg = await get_text(
                user_id,
                "DELETE_PACK_CONFIRMATION",
                pack_name=escaped_pack_name,
                sticker_count=sticker_count,
                created_date=created_date
            )

            if delete_confirm_msg is None:
                delete_confirm_msg = (
                    f"🗑️ <b>𝖣𝖾𝗅𝖾𝗍𝖾 𝖯𝖺𝖼𝗄</b>\n\n"
                    f"<b>{escaped_pack_name}</b>\n"
                    f"<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌:</b> {sticker_count}\n"
                    f"<b>𝖢𝗋𝖾𝖺𝗍𝖾𝖽:</b> {created_date}\n\n"
                    f"𝖠𝗋𝖾 𝗒𝗈𝗎 𝗌𝗎𝗋𝖾? 𝖳𝗁𝗂𝗌 𝖼𝖺𝗇𝗇𝗈𝗍 𝖻𝖾 𝗎𝗇𝖽𝗈𝗇𝖾."
                )

            await safe_edit_message(
                callback,
                delete_confirm_msg,
                await get_delete_confirmation_keyboard(user_id, short_name)
            )
    except Exception as e:
        logger.error(f"Error in delete_pack_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.CONFIRM_DELETE))
async def confirm_delete_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id

        if not short_name:
            expired_msg = await get_text(user_id, "SESSION_EXPIRED")
            if expired_msg is None:
                expired_msg = "❌ Session expired. Please try again."
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

            deleted_msg = await get_text(user_id, "PACK_DELETED_SUCCESS", pack_name=escaped_pack_name)
            if deleted_msg is None:
                deleted_msg = f"✅ <b>𝖯𝖺𝖼𝗄 𝖽𝖾𝗅𝖾𝗍𝖾𝖽!</b>\n\n<b>\"{escaped_pack_name}\"</b> 𝗁𝖺𝗌 𝖻𝖾𝖾𝗇 𝗋𝖾𝗆𝗈𝗏𝖾𝖽."

            await safe_edit_message(
                callback,
                deleted_msg,
                await get_back_to_manage_keyboard(user_id)
            )
        else:
            await manage_packs_callback(callback)

    except Exception as e:
        logger.error(f"Error in confirm_delete_callback: {e}")
        error_msg = await get_text(callback.from_user.id, "ERROR_OCCURRED")
        if error_msg is None:
            error_msg = " <b>𝖮𝗈𝗉𝗌 — 𝗌𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀.</b>"
        await safe_edit_message(callback, error_msg)


@router.callback_query(F.data.startswith(PackManagementCallback.CANCEL_DELETE))
async def cancel_delete_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id

        if not short_name:
            expired_msg = await get_text(user_id, "SESSION_EXPIRED")
            if expired_msg is None:
                expired_msg = "❌ Session expired. Please try again."
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
            ghost_msg = await get_text(user_id, "PACK_DELETED_FROM_TELEGRAM")
            if ghost_msg is None:
                ghost_msg = "❌ <b>Pack Not Found</b>\n\nThis pack was deleted from Telegram and has been removed from your list."
            await callback.answer(ghost_msg, show_alert=True)
            await manage_packs_callback(callback)
            return
        except:
            real_count = pack.get("sticker_count", 0)

        full_pack_name = pack["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"

        pack_options_msg = await get_text(
            user_id,
            "PACK_OPTIONS_MESSAGE",
            pack_link=pack_link,
            pack_name=escape_html(full_pack_name),
            sticker_count=real_count
        )

        if pack_options_msg is None:
            pack_options_msg = f"🛠️ <b>𝖯𝖺𝖼𝗄 𝖮𝗉𝗍𝗂𝗈𝗇𝗌</b>\n\n<a href=\"{pack_link}\">{escape_html(full_pack_name)}</a>\n<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌:</b> {real_count}/120"

        await safe_edit_message(callback, pack_options_msg, await get_pack_options_keyboard(user_id, short_name))
    except Exception as e:
        logger.error(f"Error in cancel_delete_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.ADD_STICKER))
async def add_sticker_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        short_name = parse_callback(callback.data)
        user_id = callback.from_user.id

        if not short_name:
            expired_msg = await get_text(user_id, "SESSION_EXPIRED")
            if expired_msg is None:
                expired_msg = "❌ Session expired. Please try again."
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

            add_sticker_msg = await get_text(
                user_id,
                "ADD_STICKER_INSTRUCTIONS",
                pack_name=escaped_pack_name,
                sticker_count=pack.get("sticker_count", 0)
            )

            if add_sticker_msg is None:
                add_sticker_msg = f"<b>Add Stickers to {escaped_pack_name}</b>\n\nSend me images, videos, GIFs, or stickers to add to your pack.\n\n<b>Current count:</b> {pack.get('sticker_count', 0)}/120"

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

    if current_count >= 120:
        pack_full_msg = await get_text(user_id, "PACK_FULL_CANNOT_ADD")
        if pack_full_msg is None:
            pack_full_msg = "❌ Pack is full! Cannot add more stickers."
        await message.reply(pack_full_msg)
        await state.clear()
        return

    if not message.photo and not message.sticker and not message.animation and not message.video:
        cancel_msg = await get_text(user_id, "STATE_CANCELLED_MESSAGE")
        if cancel_msg is None:
            cancel_msg = "<b>Operation cancelled.</b>"
        await message.reply(cancel_msg)
        await state.clear()
        return

    if await is_sticker_processing(user_id):
        wait_msg = await get_text(user_id, "STICKER_PROCESSING_WAIT")
        if wait_msg is None:
            wait_msg = "⏳ <b>Please wait!</b>\n\nYour previous sticker is still being added. Try again in a moment."
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
            video_large_msg = await get_text(user_id, "VIDEO_TOO_LARGE")
            if video_large_msg is None:
                video_large_msg = " <b>𝖵𝗂𝖽𝖾𝗈 𝗍𝗈𝗈 𝗅𝖺𝗋𝗀𝖾 (𝗈𝗏𝖾𝗋 𝟦𝖬𝖡)</b>"
            await message.reply(video_large_msg)
            return

    processing_msg_text = await get_text(user_id, "ADDING_STICKER_WAIT")
    if processing_msg_text is None:
        processing_msg_text = "⌛ Adding sticker to your pack..."
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
            success_msg = await get_text(user_id, "STICKER_ADDED_SUCCESS")
            if success_msg is None:
                success_msg = "✅ <b>Sticker added successfully!</b>"
            await processing_msg.edit_text(success_msg, reply_markup=await get_pack_link_keyboard(user_id, pack_link))

        elif pack_full:
            pack_full_msg = await get_text(user_id, "PACK_FULL_120_LIMIT")
            if pack_full_msg is None:
                pack_full_msg = "❌ <b>Pack is full!</b>\n\nThis pack has reached the maximum limit of 120 stickers."
            await processing_msg.edit_text(pack_full_msg)
            await state.clear()
        else:
            fail_msg = await get_text(user_id, "STICKER_ADD_FAILED")
            if fail_msg is None:
                fail_msg = "❌ Failed to add sticker. Please try again with a different file."
            await processing_msg.edit_text(fail_msg)
    finally:
        stop_sticker_processing(user_id)


@router.callback_query(F.data == PackManagementCallback.CREATE_NEW_PACK)
async def create_new_pack_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        user_id = callback.from_user.id
        create_pack_msg = await get_text(user_id, "CREATE_NEW_PACK_PROMPT")
        if create_pack_msg is None:
            create_pack_msg = "<b>Let's create a new sticker pack!</b>\n\n<b>First, send me the sticker you want to start your pack with.</b>\nIt can be GIF, video, image or sticker"
        await state.set_state(PackManagementStates.waiting_for_first_sticker)
        await safe_edit_message(callback, create_pack_msg, await get_back_to_manage_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in create_new_pack_callback: {e}")


@router.message(PackManagementStates.waiting_for_first_sticker)
async def process_first_sticker(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if not message.photo and not message.sticker and not message.animation and not message.video:
        cancel_msg = await get_text(user_id, "STATE_CANCELLED_MESSAGE")
        if cancel_msg is None:
            cancel_msg = "<b>Operation cancelled.</b>"
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
            video_large_msg = await get_text(user_id, "VIDEO_TOO_LARGE")
            if video_large_msg is None:
                video_large_msg = " <b>𝖵𝗂𝖽𝖾𝗈 𝗍𝗈𝗈 𝗅𝖺𝗋𝗀𝖾 (𝗈𝗏𝖾𝗋 𝟦𝖬𝖡)</b>"
            await message.reply(video_large_msg)
            return

    await state.update_data(first_sticker=media, first_sticker_type=media_type)

    got_it_msg = await get_text(user_id, "GOT_IT_SEND_PACK_NAME")
    if got_it_msg is None:
        got_it_msg = "👍 <b>Got it!</b> Now send me a name for your pack.\n\n<i>You can use any symbols, emojis, or fonts in the name.</i>"

    await message.reply(got_it_msg)
    await state.set_state(PackManagementStates.waiting_for_new_pack_name)


@router.message(PackManagementStates.waiting_for_new_pack_name)
async def process_new_pack_name(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id

    if not message.text:
        invalid_msg = await get_text(user_id, "PACK_NAME_SEND_VALID")
        if invalid_msg is None:
            invalid_msg = "❌ Please send a valid pack name."
        await message.reply(invalid_msg)
        return

    pack_name = message.text.strip()
    data = await state.get_data()
    first_sticker = data.get("first_sticker")
    first_sticker_type = data.get("first_sticker_type")

    if not first_sticker:
        sticker_lost_msg = await get_text(user_id, "STICKER_DATA_LOST")
        if sticker_lost_msg is None:
            sticker_lost_msg = "❌ Sticker data lost. Please start over."
        await message.reply(sticker_lost_msg)
        await state.clear()
        return

    if len(pack_name) > 64:
        too_long_msg = await get_text(user_id, "PACK_NAME_TOO_LONG")
        if too_long_msg is None:
            too_long_msg = "❌ Pack name is too long! Maximum 64 characters."
        await message.reply(too_long_msg)
        return

    if len(pack_name) == 0:
        empty_msg = await get_text(user_id, "PACK_NAME_EMPTY")
        if empty_msg is None:
            empty_msg = "❌ Pack name cannot be empty."
        await message.reply(empty_msg)
        return

    formatted_name = format_pack_name(pack_name)
    short_name = generate_short_name(pack_name, user_id)

    creating_msg = await get_text(user_id, "CREATING_PACK_WAIT")
    if creating_msg is None:
        creating_msg = "⌛ <b>Creating your sticker pack...</b>\nPlease wait a moment"
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
                fail_msg = await get_text(user_id, "VIDEO_COMPRESSION_FAILED")
                if fail_msg is None:
                    fail_msg = " <b>𝗎𝗇𝖺𝖻𝗅𝖾 𝗍𝗈 𝗉𝗋𝗈𝖼𝖾𝗌𝗌 𝗏𝗂𝖽𝖾𝗈</b>"
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

        success_message = await get_text(
            user_id,
            "PACK_CREATED_SUCCESS",
            pack_link=pack_link,
            pack_name=escape_html(formatted_name)
        )

        if success_message is None:
            success_message = f"✅ <b>Your sticker pack has been created successfully!</b>\n\n<a href=\"{pack_link}\">{escape_html(formatted_name)}</a>"

        await processing_msg.edit_text(
            success_message,
            reply_markup=await get_pack_options_keyboard(user_id, short_name)
        )

    except Exception as e:
        logger.error(f"Error creating new pack: {e}")
        cleanup_temp_files(*temp_files)
        error_msg_str = str(e)
        if "STICKERSET_INVALID" in error_msg_str or "invalid" in error_msg_str.lower():
            fail_msg = await get_text(user_id, "PACK_CREATE_FAILED_TEMP")
            if fail_msg is None:
                fail_msg = "❌ <b>Failed to create pack.</b>\nThis might be a temporary issue. Please try again."
            await processing_msg.edit_text(fail_msg)
        else:
            error_msg = await get_text(user_id, "ERROR_OCCURRED")
            if error_msg is None:
                error_msg = " <b>𝖮𝗈𝗉𝗌 — 𝗌𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀.</b>"
            await processing_msg.edit_text(error_msg)

    await state.clear()


@router.callback_query(F.data.startswith(PackManagementCallback.NEXT_PAGE))
async def next_page_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        page_str = parse_callback(callback.data)
        user_id = callback.from_user.id
        if not page_str:
            expired_msg = await get_text(user_id, "SESSION_EXPIRED")
            if expired_msg is None:
                expired_msg = "❌ Session expired. Please try again."
            await callback.answer(expired_msg, show_alert=True)
            return
        page = int(page_str)
        manage_msg = await get_text(user_id, "MANAGE_PACKS_MESSAGE")
        if manage_msg is None:
            manage_msg = "<b>𝖸𝗈𝗎𝗋 𝖲𝗍𝗂𝖼𝗄𝖾𝗋 𝖯𝖺𝖼𝗄𝗌</b>"
        await safe_edit_message(callback, manage_msg, await get_manage_packs_keyboard(user_id, page))
    except Exception as e:
        logger.error(f"Error in next_page_callback: {e}")


@router.callback_query(F.data.startswith(PackManagementCallback.PREV_PAGE))
async def prev_page_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        page_str = parse_callback(callback.data)
        user_id = callback.from_user.id
        if not page_str:
            expired_msg = await get_text(user_id, "SESSION_EXPIRED")
            if expired_msg is None:
                expired_msg = "❌ Session expired. Please try again."
            await callback.answer(expired_msg, show_alert=True)
            return
        page = int(page_str)
        manage_msg = await get_text(user_id, "MANAGE_PACKS_MESSAGE")
        if manage_msg is None:
            manage_msg = "<b>𝖸𝗈𝗎𝗋 𝖲𝗍𝗂𝖼𝗄𝖾𝗋 𝖯𝖺𝖼𝗄𝗌</b>"
        await safe_edit_message(callback, manage_msg, await get_manage_packs_keyboard(user_id, page))
    except Exception as e:
        logger.error(f"Error in prev_page_callback: {e}")


@router.callback_query(F.data == PackManagementCallback.BACK_TO_MANAGE)
async def back_to_manage_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        user_id = callback.from_user.id
        packs, total = await get_user_packs_paginated(user_id)
        if total == 0:
            no_packs_msg = await get_text(user_id, "NO_PACKS_MESSAGE")
            if no_packs_msg is None:
                no_packs_msg = " <b>𝖭𝗈 𝗉𝖺𝖼𝗄𝗌 𝗒𝖾𝗍.</b>\n𝖢𝗋𝖾𝖺𝗍𝖾 𝗒𝗈𝗎𝗋 𝖿𝗂𝗋𝗌𝗍 𝗍𝗈 𝗀𝖾𝗍 𝗌𝗍𝖺𝗋𝗍𝖾𝖽."
            await safe_edit_message(callback, no_packs_msg, await get_no_packs_keyboard(user_id))
        else:
            manage_msg = await get_text(user_id, "MANAGE_PACKS_MESSAGE")
            if manage_msg is None:
                manage_msg = "<b>𝖸𝗈𝗎𝗋 𝖲𝗍𝗂𝖼𝗄𝖾𝗋 𝖯𝖺𝖼𝗄𝗌</b>"
            await safe_edit_message(callback, manage_msg, await get_manage_packs_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in back_to_manage_callback: {e}")


@router.message(StateFilter(PackManagementStates), Command("cancel"))
async def cancel_pack_management(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()
    cancel_msg = await get_text(user_id, "OPERATION_CANCELLED")
    if cancel_msg is None:
        cancel_msg = "Operation cancelled."
    await message.reply(cancel_msg, reply_markup=await get_back_to_main_keyboard(user_id))
