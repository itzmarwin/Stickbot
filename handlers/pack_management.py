import logging
import os
import random
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, FSInputFile, InputSticker
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from aiogram.exceptions import TelegramBadRequest

# ✅ NEW IMPORT: Callback manager for fixing BUTTON_DATA_INVALID
from callback_manager import create_callback, parse_callback

from database import (
    get_user, create_user, update_user_started,
    get_user_packs_paginated, update_pack_name, delete_pack_by_short_name,
    get_pack_by_short_name, create_sticker_pack, increment_sticker_count,
    get_user_all_packs, update_pack_sticker_count,
    is_pack_published
)
from templates import (
    START_MESSAGE_WITH_IMAGE, MANAGE_PACKS_MESSAGE, NO_PACKS_MESSAGE,
    PACK_OPTIONS_MESSAGE, RENAME_PACK_MESSAGE, DELETE_PACK_CONFIRMATION,
    PACK_DELETED_SUCCESS, PACK_RENAMED_SUCCESS, ADD_STICKER_INSTRUCTIONS,
    PACK_FULL_MESSAGE, STICKER_ADDED_TO_PACK, ASK_PACK_NAME,
    NEW_PACK_CREATED_MULTI, NO_MEDIA_REPLY, VIDEO_TOO_LARGE,
    VIDEO_COMPRESSION_FAILED, ERROR_OCCURRED, PROCESSING_MEDIA,
    RENAME_PACK_INFO, DELETE_PACK_INFO, ADD_STICKER_INFO,
    RATE_LIMIT_MESSAGE, STICKER_ADDING_IN_PROGRESS,
    PUBLISH_PACK_INFO, EXTRA_COMMANDS_MESSAGE, AFK_INFO_MESSAGE,
    QUOTLY_INFO_MESSAGE, STICKERS_INFO_MESSAGE, STICKER_ADDED_SIMPLE
)
from utils.fsm_states import PackManagementStates
from utils.helpers import validate_pack_name, format_pack_name, generate_short_name, get_file_size_mb
from utils.converters import convert_image_to_webp, convert_video_to_webm, cleanup_temp_files, create_temp_dir
from utils.html_utils import escape_html
from handlers.kang import add_sticker_to_pack, get_random_emoji
from config import BOT_USERNAME, MAX_VIDEO_SIZE_MB, LOG_GROUP_ID

from handlers.publish import PublishCallback

logger = logging.getLogger(__name__)
router = Router()

# ✅ FIXED: Shortened callback prefixes to prevent BUTTON_DATA_INVALID
class PackManagementCallback:
    MANAGE_PACKS = "manage_packs"
    CREATE_NEW_PACK = "create_new_pack"
    PACK_SELECTED = "ps:"      # ✅ Shortened (will use hash)
    PACK_OPTIONS = "po:"       # ✅ Shortened (will use hash)
    RENAME_PACK = "rp:"        # ✅ Shortened (will use hash)
    DELETE_PACK = "dp:"        # ✅ Shortened (will use hash)
    ADD_STICKER = "as:"        # ✅ Shortened (will use hash)
    CONFIRM_DELETE = "cd:"     # ✅ Shortened (will use hash)
    CANCEL_DELETE = "xd:"      # ✅ Shortened (will use hash)
    PACK_INFO = "pack_info:"
    NEXT_PAGE = "np:"          # ✅ Shortened (will use hash)
    PREV_PAGE = "pp:"          # ✅ Shortened (will use hash)
    BACK_TO_MANAGE = "back_to_manage"
    BACK_TO_MAIN = "back_to_main"
    EXTRA_COMMANDS = "extra_commands"
    EXTRA_CMD_AFK = "extra_afk"
    EXTRA_CMD_QUOTLY = "extra_quotly"
    EXTRA_CMD_STICKERS = "extra_stickers"

def get_main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="𝗔𝗱𝗱 𝗠𝗲 𝗜𝗻 𝗬𝗼𝘂𝗿 𝗚𝗿𝗼𝘂𝗽", url=f"https://t.me/stickerkangbot?startgroup=true")
    builder.button(text="𝗘𝘅𝘁𝗿𝗮 𝗖𝗼𝗺𝗺𝗮𝗻𝗱𝘀", callback_data=PackManagementCallback.EXTRA_COMMANDS)
    builder.button(text="𝗠𝗮𝗻𝗮𝗴𝗲 𝗣𝗮𝗰𝗸𝘀", callback_data=PackManagementCallback.MANAGE_PACKS)
    builder.button(text="𝗦𝘂𝗽𝗽𝗼𝗿𝘁", url="https://t.me/Samurais_Support_chat")
    builder.button(text="𝗨𝗽𝗱𝗮𝘁𝗲𝘀", url="https://t.me/Samurais_network")
    builder.adjust(1, 2, 2)
    return builder.as_markup()

def get_extra_commands_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="𝗔𝗙𝗞", callback_data=PackManagementCallback.EXTRA_CMD_AFK)
    builder.button(text="𝗤𝘂𝗼𝘁𝗹𝘆", callback_data=PackManagementCallback.EXTRA_CMD_QUOTLY)
    builder.button(text="𝗦𝘁𝗶𝗰𝗸𝗲𝗿𝘀", callback_data=PackManagementCallback.EXTRA_CMD_STICKERS)
    builder.button(text="⬅️ 𝗕𝗮𝗰𝗸", callback_data=PackManagementCallback.BACK_TO_MAIN)
    builder.adjust(3, 1)
    return builder.as_markup()

def get_back_to_extra_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ 𝗕𝗮𝗰𝗸", callback_data=PackManagementCallback.EXTRA_COMMANDS)
    return builder.as_markup()

def get_back_to_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ 𝗕𝗮𝗰𝗸", callback_data=PackManagementCallback.BACK_TO_MAIN)
    return builder.as_markup()

def get_back_to_manage_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ 𝗕𝗮𝗰𝗸", callback_data=PackManagementCallback.BACK_TO_MANAGE)
    return builder.as_markup()

def get_no_packs_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🆕 𝗖𝗿𝗲𝗮𝘁𝗲 𝗡𝗲𝘄 𝗣𝗮𝗰𝗸", callback_data=PackManagementCallback.CREATE_NEW_PACK)
    builder.button(text="⬅️ 𝗕𝗮𝗰𝗸", callback_data=PackManagementCallback.BACK_TO_MAIN)
    builder.adjust(1, 1)
    return builder.as_markup()

def get_pack_link_keyboard(pack_link: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 𝗣𝗮𝗰𝗸 𝗟𝗶𝗻𝗸", url=pack_link)
    builder.adjust(1)
    return builder.as_markup()

# ✅ FIXED: Using callback_manager to store long short_names
async def get_manage_packs_keyboard(user_id: int, page: int = 0):
    builder = InlineKeyboardBuilder()
    packs, total = await get_user_packs_paginated(user_id, page)
    
    for pack in packs:
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        if len(pack_name) > 20:
            pack_name = pack_name[:17] + "..."
        
        # ✅ USE CALLBACK MANAGER: Stores long short_name, returns short hash
        callback_data = create_callback("pack_selected", pack['short_name'])
        builder.button(text=f"{pack_name}", callback_data=callback_data)
    
    builder.adjust(1)
    action_builder = InlineKeyboardBuilder()
    
    if page > 0:
        # ✅ USE CALLBACK MANAGER for page numbers
        callback_data = create_callback("prev_page", str(page-1))
        action_builder.button(text="⬅️ 𝗣𝗿𝗲𝘃𝗶𝗼𝘂𝘀", callback_data=callback_data)
    
    action_builder.button(text="🆕 𝗖𝗿𝗲𝗮𝘁𝗲 𝗡𝗲𝘄 𝗣𝗮𝗰𝗸", callback_data=PackManagementCallback.CREATE_NEW_PACK)
    
    if (page + 1) * 6 < total:
        # ✅ USE CALLBACK MANAGER for page numbers
        callback_data = create_callback("next_page", str(page+1))
        action_builder.button(text="𝗡𝗲𝘅𝘁 ➡️", callback_data=callback_data)
    
    action_builder.button(text="⬅️ 𝗕𝗮𝗰𝗸", callback_data=PackManagementCallback.BACK_TO_MAIN)
    action_builder.adjust(2, 1, 1)
    
    return builder.attach(action_builder).as_markup()

# ✅ FIXED: Using callback_manager for all pack-related buttons
def get_pack_options_keyboard(short_name: str):
    builder = InlineKeyboardBuilder()
    
    # ✅ USE CALLBACK MANAGER for each button
    builder.button(text="✏️ 𝗥𝗲𝗻𝗮𝗺𝗲 𝗣𝗮𝗰𝗸", 
                   callback_data=create_callback("rename_pack", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}rename")
    
    builder.button(text="➕ 𝗔𝗱𝗱 𝗦𝘁𝗶𝗰𝗸𝗲𝗿", 
                   callback_data=create_callback("add_sticker", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}add")
    
    builder.button(text="🗑️ 𝗗𝗲𝗹𝗲𝘁𝗲 𝗣𝗮𝗰𝗸", 
                   callback_data=create_callback("delete_pack", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}delete")
    
    builder.button(text="📤 𝗟𝗮𝘂𝗻𝗰𝗵 𝗣𝗮𝗰𝗸", 
                   callback_data=create_callback("publish_pack", short_name))
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}publish")
    
    builder.button(text="⬅️ 𝗕𝗮𝗰𝗸", callback_data=PackManagementCallback.BACK_TO_MANAGE)
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()

# ✅ FIXED: Using callback_manager for delete confirmation
def get_delete_confirmation_keyboard(short_name: str):
    builder = InlineKeyboardBuilder()
    
    # ✅ USE CALLBACK MANAGER
    builder.button(text="✅ 𝗖𝗼𝗻𝗳𝗶𝗿𝗺", 
                   callback_data=create_callback("confirm_delete", short_name))
    builder.button(text="❌ 𝗖𝗮𝗻𝗰𝗲𝗹", 
                   callback_data=create_callback("cancel_delete", short_name))
    builder.button(text="⬅️ 𝗕𝗮𝗰𝗸", callback_data=PackManagementCallback.BACK_TO_MANAGE)
    builder.adjust(2, 1)
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

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user = message.from_user
    await state.clear()
    
    user_data = await get_user(user.id)
    
    if not user_data:
        await create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        
        if LOG_GROUP_ID:
            try:
                from templates import NEW_USER_LOG
                log_msg = NEW_USER_LOG.format(
                    user_id=user.id,
                    username=user.username or "None",
                    first_name=user.first_name or "Unknown",
                    time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                )
                await message.bot.send_message(LOG_GROUP_ID, log_msg)
            except Exception as e:
                logger.error(f"Error sending new user log: {e}")
    else:
        await update_user_started(user.id)
    
    start_text = START_MESSAGE_WITH_IMAGE.format(
        user_id=user.id,
        first_name=escape_html(user.first_name)
    )
    
    await message.answer(start_text, reply_markup=get_main_menu_keyboard())

@router.callback_query(F.data == PackManagementCallback.EXTRA_COMMANDS)
async def extra_commands_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        await safe_edit_message(callback, EXTRA_COMMANDS_MESSAGE, get_extra_commands_keyboard())
    except Exception as e:
        logger.error(f"Error in extra_commands_callback: {e}")

@router.callback_query(F.data == PackManagementCallback.EXTRA_CMD_AFK)
async def extra_afk_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        await safe_edit_message(callback, AFK_INFO_MESSAGE, get_back_to_extra_keyboard())
    except Exception as e:
        logger.error(f"Error in extra_afk_callback: {e}")

@router.callback_query(F.data == PackManagementCallback.EXTRA_CMD_QUOTLY)
async def extra_quotly_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        await safe_edit_message(callback, QUOTLY_INFO_MESSAGE, get_back_to_extra_keyboard())
    except Exception as e:
        logger.error(f"Error in extra_quotly_callback: {e}")

@router.callback_query(F.data == PackManagementCallback.EXTRA_CMD_STICKERS)
async def extra_stickers_callback(callback: CallbackQuery):
    await callback.answer()
    try:
        await safe_edit_message(callback, STICKERS_INFO_MESSAGE, get_back_to_extra_keyboard())
    except Exception as e:
        logger.error(f"Error in extra_stickers_callback: {e}")

@router.callback_query(F.data == PackManagementCallback.MANAGE_PACKS)
async def manage_packs_callback(callback: CallbackQuery):
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        packs, total = await get_user_packs_paginated(user_id)
        
        if total == 0:
            await safe_edit_message(callback, NO_PACKS_MESSAGE, get_no_packs_keyboard())
        else:
            await safe_edit_message(callback, MANAGE_PACKS_MESSAGE, await get_manage_packs_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in manage_packs_callback: {e}")

# ✅ FIXED: Show clickable pack name with full display name and sticker count
@router.callback_query(F.data.startswith(PackManagementCallback.PACK_SELECTED))
async def pack_selected_callback(callback: CallbackQuery):
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        short_name = parse_callback(callback.data)
        
        if not short_name:
            await callback.answer("❌ Session expired. Please try again.", show_alert=True)
            return
        
        pack = await get_pack_by_short_name(short_name)
        
        if pack:
            # Get full pack name (with bot username)
            full_pack_name = pack["pack_name"]
            pack_link = f"https://t.me/addstickers/{short_name}"
            sticker_count = pack.get("sticker_count", 0)
            
            # Format message with clickable pack name and sticker count
            message_text = PACK_OPTIONS_MESSAGE.format(
                pack_link=pack_link,
                pack_name=escape_html(full_pack_name),
                sticker_count=sticker_count
            )
            
            await safe_edit_message(
                callback,
                message_text,
                get_pack_options_keyboard(short_name)
            )
    except Exception as e:
        logger.error(f"Error in pack_selected_callback: {e}")

@router.callback_query(F.data.startswith(PackManagementCallback.PACK_INFO))
async def pack_info_callback(callback: CallbackQuery):
    try:
        info_type = callback.data.split(":")[1]
        
        if info_type == "rename":
            message = RENAME_PACK_INFO
        elif info_type == "delete":
            message = DELETE_PACK_INFO
        elif info_type == "add":
            message = ADD_STICKER_INFO
        elif info_type == "publish":
            message = PUBLISH_PACK_INFO
        else:
            message = "Information about this action."
        
        await callback.answer(message, show_alert=True)
    except Exception as e:
        logger.error(f"Error in pack_info_callback: {e}")
        await callback.answer("Error showing info.", show_alert=True)

# ✅ FIXED: Parse callback data using callback_manager
@router.callback_query(F.data.startswith(PackManagementCallback.RENAME_PACK))
async def rename_pack_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        short_name = parse_callback(callback.data)
        
        if not short_name:
            await callback.answer("❌ Session expired. Please try again.", show_alert=True)
            return
        
        pack = await get_pack_by_short_name(short_name)
        
        if pack:
            await state.set_state(PackManagementStates.waiting_for_rename_pack_name)
            await state.update_data(short_name=short_name, old_name=pack["pack_name"])
            
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            escaped_pack_name = escape_html(pack_name)
            await safe_edit_message(
                callback,
                RENAME_PACK_MESSAGE.format(pack_name=escaped_pack_name),
                get_back_to_manage_keyboard()
            )
    except Exception as e:
        logger.error(f"Error in rename_pack_callback: {e}")

@router.message(PackManagementStates.waiting_for_rename_pack_name)
async def process_rename_pack_name(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    short_name = data.get("short_name")
    old_name = data.get("old_name")
    
    if not message.text:
        await message.reply("Please send a valid pack name.")
        return
    
    new_name = message.text.strip()
    
    is_valid, error = validate_pack_name(new_name)
    
    if not is_valid:
        if error == "pack_name_too_long":
            await message.reply("Pack name is too long! Maximum 64 characters.")
        else:
            await message.reply("Invalid pack name!")
        return
    
    formatted_name = format_pack_name(new_name)
    
    try:
        await bot.set_sticker_set_title(name=short_name, title=formatted_name)
        await update_pack_name(short_name, formatted_name)
        
        escaped_old_name = escape_html(old_name.replace(f" ~ @{BOT_USERNAME}", ""))
        escaped_new_name = escape_html(formatted_name.replace(f" ~ @{BOT_USERNAME}", ""))
        
        await message.reply(
            PACK_RENAMED_SUCCESS.format(old_name=escaped_old_name, new_name=escaped_new_name),
            reply_markup=get_pack_options_keyboard(short_name)
        )
    except Exception as e:
        logger.error(f"Error renaming pack: {e}")
        await message.reply(ERROR_OCCURRED)
    
    await state.clear()

# ✅ FIXED: Parse callback data using callback_manager
@router.callback_query(F.data.startswith(PackManagementCallback.DELETE_PACK))
async def delete_pack_callback(callback: CallbackQuery):
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        short_name = parse_callback(callback.data)
        
        if not short_name:
            await callback.answer("❌ Session expired. Please try again.", show_alert=True)
            return
        
        pack = await get_pack_by_short_name(short_name)
        
        if pack:
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            escaped_pack_name = escape_html(pack_name)
            created_date = pack["created_at"].strftime("%Y-%m-%d") if pack.get("created_at") else "Unknown"
            
            await safe_edit_message(
                callback,
                DELETE_PACK_CONFIRMATION.format(
                    pack_name=escaped_pack_name,
                    sticker_count=pack.get("sticker_count", 0),
                    created_date=created_date
                ),
                get_delete_confirmation_keyboard(short_name)
            )
    except Exception as e:
        logger.error(f"Error in delete_pack_callback: {e}")

# ✅ FIXED: Parse callback data using callback_manager
@router.callback_query(F.data.startswith(PackManagementCallback.CONFIRM_DELETE))
async def confirm_delete_callback(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        short_name = parse_callback(callback.data)
        
        if not short_name:
            await callback.answer("❌ Session expired. Please try again.", show_alert=True)
            return
        
        pack = await get_pack_by_short_name(short_name)
        
        if pack:
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            
            try:
                await bot.delete_sticker_set(short_name)
                await delete_pack_by_short_name(short_name)
                
                escaped_pack_name = escape_html(pack_name.replace(f" ~ @{BOT_USERNAME}", ""))
                
                await safe_edit_message(
                    callback,
                    PACK_DELETED_SUCCESS.format(pack_name=escaped_pack_name),
                    get_back_to_manage_keyboard()
                )
            except Exception as e:
                logger.error(f"Error deleting pack: {e}")
                await safe_edit_message(callback, ERROR_OCCURRED)
    except Exception as e:
        logger.error(f"Error in confirm_delete_callback: {e}")

# ✅ FIXED: Parse callback data using callback_manager
@router.callback_query(F.data.startswith(PackManagementCallback.CANCEL_DELETE))
async def cancel_delete_callback(callback: CallbackQuery):
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        short_name = parse_callback(callback.data)
        
        if not short_name:
            await callback.answer("❌ Session expired. Please try again.", show_alert=True)
            return
        
        pack = await get_pack_by_short_name(short_name)
        
        if pack:
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            await safe_edit_message(
                callback,
                PACK_OPTIONS_MESSAGE.format(pack_name=pack_name),
                get_pack_options_keyboard(short_name)
            )
    except Exception as e:
        logger.error(f"Error in cancel_delete_callback: {e}")

# ✅ FIXED: Parse callback data using callback_manager
@router.callback_query(F.data.startswith(PackManagementCallback.ADD_STICKER))
async def add_sticker_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        short_name = parse_callback(callback.data)
        
        if not short_name:
            await callback.answer("❌ Session expired. Please try again.", show_alert=True)
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
            
            await callback.message.delete()
            await callback.message.answer(
                f"<b>Add Stickers to {escaped_pack_name}</b>\n\n"
                f"Send me images, videos, GIFs, or stickers to add to your pack.\n"
                f"I'll keep adding them until the pack is full.\n\n"
                f"<b>Current count:</b> {pack.get('sticker_count', 0)}/120\n"
                f"<b>Supported formats:</b> Images, Videos (max 4MB), GIFs, Stickers"
            )
    except Exception as e:
        logger.error(f"Error in add_sticker_callback: {e}")

# ✅ FIXED: Show sticker count after adding
@router.message(PackManagementStates.waiting_for_sticker_to_add)
async def process_sticker_addition(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    short_name = data.get("short_name")
    pack_data = data.get("pack_data")
    current_count = data.get("sticker_count", 0)
    
    if current_count >= 120:
        await message.reply("❌ Pack is full! Cannot add more stickers.")
        await state.clear()
        return
    
    if not message.photo and not message.sticker and not message.animation and not message.video:
        await message.reply("⚠️ Please send an image, video, GIF, or sticker to add to your pack.")
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
            await message.reply(VIDEO_TOO_LARGE)
            return
    
    processing_msg = await message.reply("⌛ Adding sticker to your pack...")
    
    success, pack_full = await add_sticker_to_pack(
        bot=bot,
        user_id=message.from_user.id,
        pack_short_name=short_name,
        pack_data=pack_data,
        media=media,
        media_type=media_type,
        message=message,
        state=state
    )
    
    if success:
        new_count = current_count + 1
        await state.update_data(sticker_count=new_count)
        await update_pack_sticker_count(short_name, new_count)
        
        pack_name = pack_data["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        pack_link = f"https://t.me/addstickers/{short_name}"
        
        success_message = "✅ <b>Sticker added successfully!</b>"
        
        await processing_msg.edit_text(
            success_message,
            reply_markup=get_pack_link_keyboard(pack_link)
        )
    elif pack_full:
        await processing_msg.edit_text(
            "❌ <b>Pack is full!</b>\n\n"
            "This pack has reached the maximum limit of 120 stickers. "
            "Please create a new pack to add more stickers."
        )
        await state.clear()
    else:
        await processing_msg.edit_text(
            "❌ Failed to add sticker. Please try again with a different file."
        )

@router.callback_query(F.data == PackManagementCallback.CREATE_NEW_PACK)
async def create_new_pack_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        await state.set_state(PackManagementStates.waiting_for_first_sticker)
        await safe_edit_message(
            callback,
            "<b>Let's create a new sticker pack!</b>\n\n"
            "<b>First, send me the sticker you want to start your pack with.</b>\n"
            "It can be GIF, video, image or sticker",
            get_back_to_manage_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in create_new_pack_callback: {e}")

@router.message(PackManagementStates.waiting_for_first_sticker)
async def process_first_sticker(message: Message, state: FSMContext):
    if not message.photo and not message.sticker and not message.animation and not message.video:
        await message.reply(
            "⚠️ <b>That media is not valid.</b> Please send a proper sticker:\n"
            "- PNG/JPEG/WEBP for static stickers\n" 
            "- WEBM/MP4 for video stickers\n"
            "- GIF for animated\n"
            "- Existing stickers"
        )
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
            await message.reply(VIDEO_TOO_LARGE)
            return

    await state.update_data(
        first_sticker=media,
        first_sticker_type=media_type
    )
    
    await message.reply(
        "👍 <b>Got it!</b> Now send me a name for your pack.\n\n"
        "<i>You can use any symbols, emojis, or fonts in the name.</i>"
    )
    await state.set_state(PackManagementStates.waiting_for_new_pack_name)

@router.message(PackManagementStates.waiting_for_new_pack_name)
async def process_new_pack_name(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.reply("❌ Please send a valid pack name.")
        return
    
    pack_name = message.text.strip()
    
    data = await state.get_data()
    first_sticker = data.get("first_sticker")
    first_sticker_type = data.get("first_sticker_type")
    
    if not first_sticker:
        await message.reply("❌ Sticker data lost. Please start over.")
        await state.clear()
        return

    if len(pack_name) > 64:
        await message.reply("❌ Pack name is too long! Maximum 64 characters.")
        return
    
    if len(pack_name) == 0:
        await message.reply("❌ Pack name cannot be empty.")
        return

    formatted_name = format_pack_name(pack_name)
    short_name = generate_short_name(pack_name, message.from_user.id)
    
    processing_msg = await message.reply(
        "⌛ <b>Creating your sticker pack...</b>\n"
        "Please wait a moment"
    )
    
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
            input_path = os.path.join(temp_dir, f"{message.from_user.id}_first_input.jpg")
            output_path = os.path.join(temp_dir, f"{message.from_user.id}_first_output.webp")
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
            input_path = os.path.join(temp_dir, f"{message.from_user.id}_first_input.mp4")
            output_path = os.path.join(temp_dir, f"{message.from_user.id}_first_output.webm")
            temp_files.extend([input_path, output_path])
            
            await bot.download_file(file.file_path, input_path)
            
            conversion_success = await convert_video_to_webm(input_path, output_path)
            
            if conversion_success and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webm")
                sticker_format = "video"
            else:
                cleanup_temp_files(*temp_files)
                await processing_msg.edit_text(VIDEO_COMPRESSION_FAILED)
                await state.clear()
                return

        if not sticker_file:
            raise Exception("Failed to prepare sticker file")

        random_emoji = get_random_emoji()
        
        sticker = InputSticker(
            sticker=sticker_file,
            emoji_list=[random_emoji],
            format=sticker_format
        )
        
        await bot.create_new_sticker_set(
            user_id=message.from_user.id,
            name=short_name,
            title=formatted_name,
            stickers=[sticker]
        )
        
        pack_link = f"https://t.me/addstickers/{short_name}"
        await create_sticker_pack(
            user_id=message.from_user.id,
            pack_name=formatted_name,
            short_name=short_name
        )
        
        await update_pack_sticker_count(short_name, 1)
        
        cleanup_temp_files(*temp_files)
        
        all_packs = await get_user_all_packs(message.from_user.id)
        pack_count = len(all_packs)
        
        escaped_pack_name = escape_html(formatted_name)
        
        success_message = (
            f"✅ <b>Your sticker pack has been created successfully!</b>\n\n"
            f'<a href="{pack_link}">{escaped_pack_name}</a>'
        )
        
        await processing_msg.edit_text(
            success_message,
            reply_markup=get_pack_options_keyboard(short_name)
        )
        
    except Exception as e:
        logger.error(f"Error creating new pack: {e}")
        cleanup_temp_files(*temp_files)
        
        error_msg = str(e)
        if "STICKERSET_INVALID" in error_msg or "invalid" in error_msg.lower():
            await processing_msg.edit_text(
                "❌ <b>Failed to create pack.</b>\n"
                "This might be a temporary issue. Please try again."
            )
        else:
            await processing_msg.edit_text(ERROR_OCCURRED)
    
    await state.clear()

# ✅ FIXED: Parse callback data using callback_manager
@router.callback_query(F.data.startswith(PackManagementCallback.NEXT_PAGE))
async def next_page_callback(callback: CallbackQuery):
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        page_str = parse_callback(callback.data)
        
        if not page_str:
            await callback.answer("❌ Session expired. Please try again.", show_alert=True)
            return
        
        page = int(page_str)
        user_id = callback.from_user.id
        
        await safe_edit_message(
            callback,
            MANAGE_PACKS_MESSAGE,
            await get_manage_packs_keyboard(user_id, page)
        )
    except Exception as e:
        logger.error(f"Error in next_page_callback: {e}")

# ✅ FIXED: Parse callback data using callback_manager
@router.callback_query(F.data.startswith(PackManagementCallback.PREV_PAGE))
async def prev_page_callback(callback: CallbackQuery):
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        page_str = parse_callback(callback.data)
        
        if not page_str:
            await callback.answer("❌ Session expired. Please try again.", show_alert=True)
            return
        
        page = int(page_str)
        user_id = callback.from_user.id
        
        await safe_edit_message(
            callback,
            MANAGE_PACKS_MESSAGE,
            await get_manage_packs_keyboard(user_id, page)
        )
    except Exception as e:
        logger.error(f"Error in prev_page_callback: {e}")

@router.callback_query(F.data == PackManagementCallback.BACK_TO_MANAGE)
async def back_to_manage_callback(callback: CallbackQuery):
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        packs, total = await get_user_packs_paginated(user_id)
        
        if total == 0:
            await safe_edit_message(callback, NO_PACKS_MESSAGE, get_no_packs_keyboard())
        else:
            await safe_edit_message(callback, MANAGE_PACKS_MESSAGE, await get_manage_packs_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in back_to_manage_callback: {e}")

@router.callback_query(F.data == PackManagementCallback.BACK_TO_MAIN)
async def back_to_main_callback(callback: CallbackQuery):
    await callback.answer()
    
    try:
        user = callback.from_user
        start_text = START_MESSAGE_WITH_IMAGE.format(
            user_id=user.id,
            first_name=escape_html(user.first_name)
        )
        await safe_edit_message(callback, start_text, get_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error in back_to_main_callback: {e}")

@router.message(StateFilter(PackManagementStates), Command("cancel"))
async def cancel_pack_management(message: Message, state: FSMContext):
    await state.clear()
    await message.reply("Operation cancelled.", reply_markup=get_main_menu_keyboard())
