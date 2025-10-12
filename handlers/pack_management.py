import logging
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, FSInputFile, InputSticker
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from aiogram.exceptions import TelegramBadRequest

from database import (
    get_user, create_user, update_user_started,
    get_user_packs_paginated, update_pack_name, delete_pack_by_short_name,
    get_pack_by_short_name, create_sticker_pack, increment_sticker_count,
    get_user_all_packs, update_pack_sticker_count,
    is_pack_published  # ✅ ADDED IMPORT
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
    PUBLISH_PACK_INFO  # ✅ ADDED IMPORT
)
from utils.fsm_states import PackManagementStates
from utils.helpers import validate_pack_name, format_pack_name, generate_short_name, get_file_size_mb
from utils.converters import convert_image_to_webp, convert_video_to_webm, cleanup_temp_files, create_temp_dir
from utils.html_utils import escape_html
from handlers.kang import add_sticker_to_pack, get_random_emoji
from config import BOT_USERNAME, MAX_VIDEO_SIZE_MB, LOG_GROUP_ID

# ✅ ADDED PUBLISH IMPORT
from handlers.publish import PublishCallback

logger = logging.getLogger(__name__)
router = Router()

# Callback data patterns
class PackManagementCallback:
    MANAGE_PACKS = "manage_packs"
    CREATE_NEW_PACK = "create_new_pack"
    PACK_SELECTED = "pack_selected:"
    PACK_OPTIONS = "pack_options:"
    RENAME_PACK = "rename_pack:"
    DELETE_PACK = "delete_pack:"
    ADD_STICKER = "add_sticker:"
    CONFIRM_DELETE = "confirm_delete:"
    CANCEL_DELETE = "cancel_delete:"
    PACK_INFO = "pack_info:"
    NEXT_PAGE = "next_page:"
    PREV_PAGE = "prev_page:"
    BACK_TO_MANAGE = "back_to_manage"
    BACK_TO_MAIN = "back_to_main"

def get_main_menu_keyboard():
    """Get main menu keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text=" Manage Packs", callback_data=PackManagementCallback.MANAGE_PACKS)
    builder.button(text=" Support", url="https://t.me/Samurais_Support_chat")
    builder.button(text=" Updates", url="https://t.me/Samurais_network")
    builder.adjust(1, 2)
    return builder.as_markup()

def get_back_to_main_keyboard():
    """Get back to main menu keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Back", callback_data=PackManagementCallback.BACK_TO_MAIN)
    return builder.as_markup()

def get_back_to_manage_keyboard():
    """Get back to manage packs keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Back", callback_data=PackManagementCallback.BACK_TO_MANAGE)
    return builder.as_markup()

def get_no_packs_keyboard():
    """Get keyboard for when user has no packs"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🆕 Create New Pack", callback_data=PackManagementCallback.CREATE_NEW_PACK)
    builder.button(text="⬅️ Back", callback_data=PackManagementCallback.BACK_TO_MAIN)
    builder.adjust(1, 1)
    return builder.as_markup()

def get_pack_link_keyboard(pack_link: str):
    """Get pack link keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Pack Link", url=pack_link)
    builder.adjust(1)
    return builder.as_markup()

async def get_manage_packs_keyboard(user_id: int, page: int = 0):
    """Get manage packs keyboard with user's packs"""
    builder = InlineKeyboardBuilder()
    
    packs, total = await get_user_packs_paginated(user_id, page)
    
    # Add pack buttons
    for pack in packs:
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        if len(pack_name) > 20:
            pack_name = pack_name[:17] + "..."
        builder.button(text=f" {pack_name}", callback_data=f"{PackManagementCallback.PACK_SELECTED}{pack['short_name']}")
    
    # Adjust to 1 button per row
    builder.adjust(1)
    
    # Add navigation and action buttons
    action_builder = InlineKeyboardBuilder()
    
    if page > 0:
        action_builder.button(text="⬅️ Previous", callback_data=f"{PackManagementCallback.PREV_PAGE}{page-1}")
    
    action_builder.button(text="🆕 Create New Pack", callback_data=PackManagementCallback.CREATE_NEW_PACK)
    
    if (page + 1) * 6 < total:
        action_builder.button(text="Next ➡️", callback_data=f"{PackManagementCallback.NEXT_PAGE}{page+1}")
    
    action_builder.button(text="⬅️ Back", callback_data=PackManagementCallback.BACK_TO_MAIN)
    action_builder.adjust(2, 1, 1)
    
    return builder.attach(action_builder).as_markup()

def get_pack_options_keyboard(short_name: str):
    """Get pack options keyboard with PUBLISH button"""
    builder = InlineKeyboardBuilder()
    
    # Row 1: Rename Pack
    builder.button(text="✏️ Rename Pack", callback_data=f"{PackManagementCallback.RENAME_PACK}{short_name}")
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}rename")
    
    # Row 2: Add Sticker
    builder.button(text="➕ Add Sticker", callback_data=f"{PackManagementCallback.ADD_STICKER}{short_name}")
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}add")
    
    # Row 3: Delete Pack
    builder.button(text="🗑️ Delete Pack", callback_data=f"{PackManagementCallback.DELETE_PACK}{short_name}")
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}delete")
    
    # ✅ Row 4: Publish Pack (NEW)
    builder.button(text="📤 Publish Pack", callback_data=f"{PublishCallback.PUBLISH_PACK}{short_name}")
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}publish")
    
    # Row 5: Back
    builder.button(text="⬅️ Back", callback_data=PackManagementCallback.BACK_TO_MANAGE)
    
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()

def get_delete_confirmation_keyboard(short_name: str):
    """Get delete confirmation keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm", callback_data=f"{PackManagementCallback.CONFIRM_DELETE}{short_name}")
    builder.button(text="❌ Cancel", callback_data=f"{PackManagementCallback.CANCEL_DELETE}{short_name}")
    builder.button(text="⬅️ Back", callback_data=PackManagementCallback.BACK_TO_MANAGE)
    builder.adjust(2, 1)
    return builder.as_markup()

async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None):
    """Safely edit message, handling photo messages by sending new message"""
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

# Start command handler
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command with main menu"""
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
    
    await message.answer(START_MESSAGE_WITH_IMAGE, reply_markup=get_main_menu_keyboard())

@router.callback_query(F.data == PackManagementCallback.MANAGE_PACKS)
async def manage_packs_callback(callback: CallbackQuery):
    """Show manage packs panel"""
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

@router.callback_query(F.data.startswith(PackManagementCallback.PACK_SELECTED))
async def pack_selected_callback(callback: CallbackQuery):
    """Show options for selected pack"""
    await callback.answer()
    
    try:
        short_name = callback.data.split(":")[1]
        pack = await get_pack_by_short_name(short_name)
        
        if pack:
            pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
            escaped_pack_name = escape_html(pack_name)
            await safe_edit_message(
                callback,
                PACK_OPTIONS_MESSAGE.format(pack_name=escaped_pack_name),
                get_pack_options_keyboard(short_name)
            )
    except Exception as e:
        logger.error(f"Error in pack_selected_callback: {e}")

@router.callback_query(F.data.startswith(PackManagementCallback.PACK_INFO))
async def pack_info_callback(callback: CallbackQuery):
    """Show info alert for pack actions"""
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

@router.callback_query(F.data.startswith(PackManagementCallback.RENAME_PACK))
async def rename_pack_callback(callback: CallbackQuery, state: FSMContext):
    """Start rename pack process"""
    await callback.answer()
    
    try:
        short_name = callback.data.split(":")[1]
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
    """Process new pack name for renaming"""
    data = await state.get_data()
    short_name = data.get("short_name")
    old_name = data.get("old_name")
    
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
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error renaming pack: {e}")
        await message.reply(ERROR_OCCURRED)
    
    await state.clear()

@router.callback_query(F.data.startswith(PackManagementCallback.DELETE_PACK))
async def delete_pack_callback(callback: CallbackQuery):
    """Show delete confirmation"""
    await callback.answer()
    
    try:
        short_name = callback.data.split(":")[1]
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

@router.callback_query(F.data.startswith(PackManagementCallback.CONFIRM_DELETE))
async def confirm_delete_callback(callback: CallbackQuery, bot: Bot):
    """Confirm and delete pack"""
    await callback.answer()
    
    try:
        short_name = callback.data.split(":")[1]
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

@router.callback_query(F.data.startswith(PackManagementCallback.CANCEL_DELETE))
async def cancel_delete_callback(callback: CallbackQuery):
    """Cancel delete and go back to pack options"""
    await callback.answer()
    
    try:
        short_name = callback.data.split(":")[1]
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

@router.callback_query(F.data.startswith(PackManagementCallback.ADD_STICKER))
async def add_sticker_callback(callback: CallbackQuery, state: FSMContext):
    """Start add sticker process"""
    await callback.answer()
    
    try:
        short_name = callback.data.split(":")[1]
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
                f"🎨 <b>Add Stickers to {escaped_pack_name}</b>\n\n"
                f"Send me images, videos, GIFs, or stickers to add to your pack.\n"
                f"I'll keep adding them until the pack is full.\n\n"
                f"<b>Current count:</b> {pack.get('sticker_count', 0)}/120\n"
                f"<b>Supported formats:</b> Images, Videos (max 4MB), GIFs, Stickers"
            )
    except Exception as e:
        logger.error(f"Error in add_sticker_callback: {e}")

@router.message(PackManagementStates.waiting_for_sticker_to_add)
async def process_sticker_addition(message: Message, state: FSMContext, bot: Bot):
    """Process sticker addition to pack"""
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
    """Start create new pack process"""
    await callback.answer()
    
    try:
        await state.set_state(PackManagementStates.waiting_for_first_sticker)
        await safe_edit_message(
            callback,
            "🎨 <b>Let's create a new sticker pack!</b>\n\n"
            "<b>First, send me the sticker you want to start your pack with.</b>\n"
            "It can be GIF, video, image or sticker",
            get_back_to_manage_keyboard()
        )
    except Exception as e:
        logger.error(f"Error in create_new_pack_callback: {e}")

@router.message(PackManagementStates.waiting_for_first_sticker)
async def process_first_sticker(message: Message, state: FSMContext):
    """Process the first sticker for new pack"""
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
    """Process new pack name and create pack with first sticker"""
    pack_name = message.text.strip()
    
    data = await state.get_data()
    first_sticker = data.get("first_sticker")
    first_sticker_type = data.get("first_sticker_type")
    
    if not first_sticker:
        await message.reply("❌ Sticker data lost. Please start over.")
        await state.clear()
        return

    # ✅ REMOVED: Pack name uniqueness check - multiple users can use same name!

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

@router.callback_query(F.data.startswith(PackManagementCallback.NEXT_PAGE))
async def next_page_callback(callback: CallbackQuery):
    """Show next page of packs"""
    await callback.answer()
    
    try:
        page = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        await safe_edit_message(
            callback,
            MANAGE_PACKS_MESSAGE,
            await get_manage_packs_keyboard(user_id, page)
        )
    except Exception as e:
        logger.error(f"Error in next_page_callback: {e}")

@router.callback_query(F.data.startswith(PackManagementCallback.PREV_PAGE))
async def prev_page_callback(callback: CallbackQuery):
    """Show previous page of packs"""
    await callback.answer()
    
    try:
        page = int(callback.data.split(":")[1])
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
    """Go back to manage packs"""
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
    """Go back to main menu"""
    await callback.answer()
    
    try:
        await safe_edit_message(callback, START_MESSAGE_WITH_IMAGE, get_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error in back_to_main_callback: {e}")

@router.message(StateFilter(PackManagementStates), Command("cancel"))
async def cancel_pack_management(message: Message, state: FSMContext):
    """Cancel any pack management operation"""
    await state.clear()
    await message.reply("Operation cancelled.", reply_markup=get_main_menu_keyboard())
