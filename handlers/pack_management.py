import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, FSInputFile
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from aiogram.exceptions import TelegramBadRequest

from database import (
    get_user, create_user, update_user_started,
    get_user_packs_paginated, update_pack_name, delete_pack_by_short_name,
    get_pack_by_short_name, create_sticker_pack, increment_sticker_count,
    get_user_all_packs, update_pack_sticker_count
)
from templates import (
    START_MESSAGE_WITH_IMAGE, MANAGE_PACKS_MESSAGE, NO_PACKS_MESSAGE,
    PACK_OPTIONS_MESSAGE, RENAME_PACK_MESSAGE, DELETE_PACK_CONFIRMATION,
    PACK_DELETED_SUCCESS, PACK_RENAMED_SUCCESS, ADD_STICKER_INSTRUCTIONS,
    PACK_FULL_MESSAGE, STICKER_ADDED_TO_PACK, ASK_PACK_NAME,
    NEW_PACK_CREATED_MULTI, NO_MEDIA_REPLY, VIDEO_TOO_LARGE,
    VIDEO_COMPRESSION_FAILED, ERROR_OCCURRED, PROCESSING_MEDIA,
    RENAME_PACK_INFO, DELETE_PACK_INFO, ADD_STICKER_INFO,
    RATE_LIMIT_MESSAGE, STICKER_ADDING_IN_PROGRESS
)
from utils.fsm_states import PackManagementStates
from utils.helpers import validate_pack_name, format_pack_name, generate_short_name, get_file_size_mb
from utils.converters import convert_image_to_webp, convert_video_to_webm, cleanup_temp_files, create_temp_dir
from handlers.kang import add_sticker_to_pack, get_random_emoji
from config import BOT_USERNAME, MAX_VIDEO_SIZE_MB, LOG_GROUP_ID

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
    STOP_ADDING_STICKERS = "stop_adding_stickers:"

def get_main_menu_keyboard():
    """Get main menu keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Manage Packs", callback_data=PackManagementCallback.MANAGE_PACKS)
    builder.button(text="🆘 Support", url="https://t.me/YourSupportGroup")
    builder.button(text="📢 Updates", url="https://t.me/YourUpdateChannel")
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

def get_continue_adding_keyboard(short_name: str):
    """Get keyboard for continuous sticker adding"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🛑 Stop Adding", callback_data=f"{PackManagementCallback.STOP_ADDING_STICKERS}{short_name}")
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
        builder.button(text=f"📦 {pack_name}", callback_data=f"{PackManagementCallback.PACK_SELECTED}{pack['short_name']}")
    
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
    """Get pack options keyboard"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="✏️ Rename Pack", callback_data=f"{PackManagementCallback.RENAME_PACK}{short_name}")
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}rename")
    
    builder.button(text="🗑️ Delete Pack", callback_data=f"{PackManagementCallback.DELETE_PACK}{short_name}")
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}delete")
    
    builder.button(text="🎨 Add Sticker", callback_data=f"{PackManagementCallback.ADD_STICKER}{short_name}")
    builder.button(text="ℹ️", callback_data=f"{PackManagementCallback.PACK_INFO}add")
    
    builder.button(text="⬅️ Back", callback_data=PackManagementCallback.BACK_TO_MANAGE)
    
    builder.adjust(2, 2, 2, 1)
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
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup
        )
    except TelegramBadRequest as e:
        if "no text in the message" in str(e):
            # Original message was a photo, send new text message
            await callback.message.delete()
            await callback.message.answer(
                text,
                reply_markup=reply_markup
            )
        else:
            raise e

# Start command handler - TEXT ONLY to avoid editing issues
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command with main menu"""
    user = message.from_user
    
    # Clear any existing FSM state
    await state.clear()
    
    # Check if user exists
    user_data = await get_user(user.id)
    
    if not user_data:
        # Create new user
        await create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        
        # Send log to logger group if this is a new user
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
        # Update has_started status
        await update_user_started(user.id)
    
    # Send welcome message as TEXT ONLY to avoid photo editing issues
    await message.answer(
        START_MESSAGE_WITH_IMAGE,
        reply_markup=get_main_menu_keyboard()
    )

# Manage Packs callback
@router.callback_query(F.data == PackManagementCallback.MANAGE_PACKS)
async def manage_packs_callback(callback: CallbackQuery):
    """Show manage packs panel"""
    user_id = callback.from_user.id
    packs, total = await get_user_packs_paginated(user_id)
    
    if total == 0:
        await safe_edit_message(
            callback,
            NO_PACKS_MESSAGE,
            get_no_packs_keyboard()  # CHANGED: Now has Create New Pack button
        )
    else:
        await safe_edit_message(
            callback,
            MANAGE_PACKS_MESSAGE,
            await get_manage_packs_keyboard(user_id)
        )
    
    await callback.answer()

# Pack selected callback
@router.callback_query(F.data.startswith(PackManagementCallback.PACK_SELECTED))
async def pack_selected_callback(callback: CallbackQuery):
    """Show options for selected pack"""
    short_name = callback.data.split(":")[1]
    pack = await get_pack_by_short_name(short_name)
    
    if pack:
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        await safe_edit_message(
            callback,
            PACK_OPTIONS_MESSAGE.format(pack_name=pack_name),
            get_pack_options_keyboard(short_name)
        )
    else:
        await callback.answer("Pack not found!", show_alert=True)
    
    await callback.answer()

# Pack info callback (alert popup)
@router.callback_query(F.data.startswith(PackManagementCallback.PACK_INFO))
async def pack_info_callback(callback: CallbackQuery):
    """Show info alert for pack actions"""
    info_type = callback.data.split(":")[1]
    
    if info_type == "rename":
        message = RENAME_PACK_INFO
    elif info_type == "delete":
        message = DELETE_PACK_INFO
    elif info_type == "add":
        message = ADD_STICKER_INFO
    else:
        message = "Information about this action."
    
    await callback.answer(message, show_alert=True)

# Rename pack callback
@router.callback_query(F.data.startswith(PackManagementCallback.RENAME_PACK))
async def rename_pack_callback(callback: CallbackQuery, state: FSMContext):
    """Start rename pack process"""
    short_name = callback.data.split(":")[1]
    pack = await get_pack_by_short_name(short_name)
    
    if pack:
        await state.set_state(PackManagementStates.waiting_for_rename_pack_name)
        await state.update_data(short_name=short_name, old_name=pack["pack_name"])
        
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        await safe_edit_message(
            callback,
            RENAME_PACK_MESSAGE.format(pack_name=pack_name),
            get_back_to_manage_keyboard()
        )
    else:
        await callback.answer("Pack not found!", show_alert=True)
    
    await callback.answer()

# Handle rename pack name input
@router.message(PackManagementStates.waiting_for_rename_pack_name)
async def process_rename_pack_name(message: Message, state: FSMContext, bot: Bot):
    """Process new pack name for renaming"""
    data = await state.get_data()
    short_name = data.get("short_name")
    old_name = data.get("old_name")
    
    new_name = message.text.strip()
    
    # Validate pack name
    is_valid, error = validate_pack_name(new_name)
    
    if not is_valid:
        if error == "pack_name_too_long":
            await message.reply("Pack name is too long! Maximum 64 characters.")
        else:
            await message.reply("Invalid pack name!")
        return
    
    # Format new pack name
    formatted_name = format_pack_name(new_name)
    
    # Update pack via bot API
    try:
        await bot.set_sticker_set_title(
            name=short_name,
            title=formatted_name
        )
        
        # Update in database
        await update_pack_name(short_name, formatted_name)
        
        await message.reply(
            PACK_RENAMED_SUCCESS.format(old_name=old_name, new_name=formatted_name),
            reply_markup=get_main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error renaming pack: {e}")
        await message.reply(ERROR_OCCURRED)
    
    await state.clear()

# Delete pack callback
@router.callback_query(F.data.startswith(PackManagementCallback.DELETE_PACK))
async def delete_pack_callback(callback: CallbackQuery):
    """Show delete confirmation"""
    short_name = callback.data.split(":")[1]
    pack = await get_pack_by_short_name(short_name)
    
    if pack:
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        created_date = pack["created_at"].strftime("%Y-%m-%d") if pack.get("created_at") else "Unknown"
        
        await safe_edit_message(
            callback,
            DELETE_PACK_CONFIRMATION.format(
                pack_name=pack_name,
                sticker_count=pack.get("sticker_count", 0),
                created_date=created_date
            ),
            get_delete_confirmation_keyboard(short_name)
        )
    else:
        await callback.answer("Pack not found!", show_alert=True)
    
    await callback.answer()

# Confirm delete callback
@router.callback_query(F.data.startswith(PackManagementCallback.CONFIRM_DELETE))
async def confirm_delete_callback(callback: CallbackQuery, bot: Bot):
    """Confirm and delete pack"""
    short_name = callback.data.split(":")[1]
    pack = await get_pack_by_short_name(short_name)
    
    if pack:
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        
        try:
            # Delete pack via bot API
            await bot.delete_sticker_set(short_name)
            
            # Delete from database
            await delete_pack_by_short_name(short_name)
            
            await safe_edit_message(
                callback,
                PACK_DELETED_SUCCESS.format(pack_name=pack_name),
                get_back_to_manage_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Error deleting pack: {e}")
            await safe_edit_message(callback, ERROR_OCCURRED)
    else:
        await callback.answer("Pack not found!", show_alert=True)
    
    await callback.answer()

# Cancel delete callback
@router.callback_query(F.data.startswith(PackManagementCallback.CANCEL_DELETE))
async def cancel_delete_callback(callback: CallbackQuery):
    """Cancel delete and go back to pack options"""
    short_name = callback.data.split(":")[1]
    pack = await get_pack_by_short_name(short_name)
    
    if pack:
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        await safe_edit_message(
            callback,
            PACK_OPTIONS_MESSAGE.format(pack_name=pack_name),
            get_pack_options_keyboard(short_name)
        )
    
    await callback.answer()

# Add sticker callback - UPDATED for continuous adding
@router.callback_query(F.data.startswith(PackManagementCallback.ADD_STICKER))
async def add_sticker_callback(callback: CallbackQuery, state: FSMContext):
    """Start add sticker process - continuous adding"""
    short_name = callback.data.split(":")[1]
    pack = await get_pack_by_short_name(short_name)
    
    if pack:
        # Check if pack is full
        if pack.get("sticker_count", 0) >= 120:
            await callback.answer("Pack is full! Create a new pack.", show_alert=True)
            return
        
        await state.set_state(PackManagementStates.waiting_for_sticker_to_add)
        await state.update_data(
            short_name=short_name, 
            pack_data=pack,
            sticker_count=pack.get("sticker_count", 0)
        )
        
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        
        # Send new message instead of editing to start fresh session
        await callback.message.delete()
        await callback.message.answer(
            f"🎨 <b>Add Stickers to {pack_name}</b>\n\n"
            f"Now send me images, videos, GIFs, or stickers to add to your pack.\n"
            f"I'll keep adding them until you click 'Stop Adding' or the pack is full.\n\n"
            f"<b>Current count:</b> {pack.get('sticker_count', 0)}/120\n"
            f"<b>Supported formats:</b> Images, Videos (max 4MB), GIFs, Stickers",
            reply_markup=get_continue_adding_keyboard(short_name)
        )
    else:
        await callback.answer("Pack not found!", show_alert=True)
    
    await callback.answer()

# Stop adding stickers callback
@router.callback_query(F.data.startswith(PackManagementCallback.STOP_ADDING_STICKERS))
async def stop_adding_stickers_callback(callback: CallbackQuery, state: FSMContext):
    """Stop continuous sticker adding and go back to pack options"""
    short_name = callback.data.split(":")[1]
    pack = await get_pack_by_short_name(short_name)
    
    if pack:
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        await state.clear()
        
        await callback.message.delete()
        await callback.message.answer(
            f"✅ <b>Sticker adding session ended for {pack_name}</b>\n\n"
            f"Pack now has {pack.get('sticker_count', 0)}/120 stickers.",
            reply_markup=get_pack_options_keyboard(short_name)
        )
    else:
        await callback.answer("Pack not found!", show_alert=True)
    
    await callback.answer()

# Handle sticker addition - UPDATED for continuous adding
@router.message(PackManagementStates.waiting_for_sticker_to_add)
async def process_sticker_addition(message: Message, state: FSMContext, bot: Bot):
    """Process sticker addition to pack - continuous mode"""
    data = await state.get_data()
    short_name = data.get("short_name")
    pack_data = data.get("pack_data")
    current_count = data.get("sticker_count", 0)
    
    # Check if pack is full
    if current_count >= 120:
        await message.reply("❌ Pack is full! Cannot add more stickers.")
        await state.clear()
        return
    
    # Check if replying to a message with media
    if not message.photo and not message.sticker and not message.animation and not message.video:
        await message.reply("⚠️ Please send an image, video, GIF, or sticker to add to your pack.")
        return
    
    # Get media from message
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
    
    # Check video size
    if media_type == "video":
        file_size_mb = get_file_size_mb(media.file_size)
        if file_size_mb > MAX_VIDEO_SIZE_MB:
            await message.reply(VIDEO_TOO_LARGE)
            return
    
    processing_msg = await message.reply("⌛ Adding sticker to your pack...")
    
    # REUSE existing function from kang.py
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
        # Update sticker count in state and database
        new_count = current_count + 1
        await state.update_data(sticker_count=new_count)
        await update_pack_sticker_count(short_name, new_count)
        
        pack_name = pack_data["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        pack_link = f"https://t.me/addstickers/{short_name}"
        
        # Success message with pack link
        success_message = (
            f"✅ <b>Sticker #{new_count} added successfully!</b>\n\n"
            f"<b>Pack:</b> {pack_name}\n"
            f"<b>Current count:</b> {new_count}/120\n\n"
            f"<a href='{pack_link}'>View Your Pack</a>\n\n"
            f"Send another sticker to continue adding, or click 'Stop Adding' to finish."
        )
        
        await processing_msg.edit_text(
            success_message,
            reply_markup=get_continue_adding_keyboard(short_name)
        )
        
    elif pack_full:
        await processing_msg.edit_text(
            "❌ <b>Pack is full!</b>\n\n"
            "This pack has reached the maximum limit of 120 stickers. "
            "Please create a new pack to add more stickers.",
            reply_markup=get_continue_adding_keyboard(short_name)
        )
        await state.clear()
    else:
        await processing_msg.edit_text(
            "❌ Failed to add sticker. Please try again with a different file.",
            reply_markup=get_continue_adding_keyboard(short_name)
        )

# Create new pack callback
@router.callback_query(F.data == PackManagementCallback.CREATE_NEW_PACK)
async def create_new_pack_callback(callback: CallbackQuery, state: FSMContext):
    """Start create new pack process"""
    await state.set_state(PackManagementStates.waiting_for_new_pack_name)
    await safe_edit_message(
        callback,
        ASK_PACK_NAME,
        get_back_to_manage_keyboard()
    )
    await callback.answer()

# Handle new pack name input
@router.message(PackManagementStates.waiting_for_new_pack_name)
async def process_new_pack_name(message: Message, state: FSMContext, bot: Bot):
    """Process new pack name creation"""
    pack_name = message.text.strip()
    
    # Validate pack name
    is_valid, error = validate_pack_name(pack_name)
    
    if not is_valid:
        if error == "pack_name_too_long":
            await message.reply("Pack name is too long! Maximum 64 characters.")
        else:
            await message.reply("Invalid pack name!")
        return
    
    # Format pack name and generate short name
    formatted_name = format_pack_name(pack_name)
    short_name = generate_short_name(pack_name, message.from_user.id)
    
    # Create empty sticker pack (we'll add stickers later)
    try:
        # Create with a dummy sticker (Telegram requires at least one sticker)
        # We'll use a simple approach - user needs to add first sticker manually
        from aiogram.types import InputSticker
        
        # For now, we'll create the pack when user adds first sticker
        # Just create the database entry
        await create_sticker_pack(
            user_id=message.from_user.id,
            pack_name=formatted_name,
            short_name=short_name
        )
        
        # Get all user packs count
        all_packs = await get_user_all_packs(message.from_user.id)
        pack_count = len(all_packs)
        
        await message.reply(
            "✅ Pack created! Now use the 'Add Sticker' option to add your first sticker to the pack.",
            reply_markup=get_main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error creating new pack: {e}")
        await message.reply(ERROR_OCCURRED)
    
    await state.clear()

# Navigation callbacks
@router.callback_query(F.data.startswith(PackManagementCallback.NEXT_PAGE))
async def next_page_callback(callback: CallbackQuery):
    """Show next page of packs"""
    page = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    await safe_edit_message(
        callback,
        MANAGE_PACKS_MESSAGE,
        await get_manage_packs_keyboard(user_id, page)
    )
    await callback.answer()

@router.callback_query(F.data.startswith(PackManagementCallback.PREV_PAGE))
async def prev_page_callback(callback: CallbackQuery):
    """Show previous page of packs"""
    page = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    await safe_edit_message(
        callback,
        MANAGE_PACKS_MESSAGE,
        await get_manage_packs_keyboard(user_id, page)
    )
    await callback.answer()

@router.callback_query(F.data == PackManagementCallback.BACK_TO_MANAGE)
async def back_to_manage_callback(callback: CallbackQuery):
    """Go back to manage packs"""
    user_id = callback.from_user.id
    packs, total = await get_user_packs_paginated(user_id)
    
    if total == 0:
        await safe_edit_message(
            callback,
            NO_PACKS_MESSAGE,
            get_no_packs_keyboard()  # CHANGED: Now has Create New Pack button
        )
    else:
        await safe_edit_message(
            callback,
            MANAGE_PACKS_MESSAGE,
            await get_manage_packs_keyboard(user_id)
        )
    
    await callback.answer()

@router.callback_query(F.data == PackManagementCallback.BACK_TO_MAIN)
async def back_to_main_callback(callback: CallbackQuery):
    """Go back to main menu"""
    await safe_edit_message(
        callback,
        START_MESSAGE_WITH_IMAGE,
        get_main_menu_keyboard()
    )
    await callback.answer()

# Cancel handlers
@router.message(StateFilter(PackManagementStates), Command("cancel"))
async def cancel_pack_management(message: Message, state: FSMContext):
    """Cancel any pack management operation"""
    await state.clear()
    await message.reply(
        "Operation cancelled.",
        reply_markup=get_main_menu_keyboard()
    )
