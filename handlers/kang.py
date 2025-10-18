import os
import logging
import random
import time
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputSticker, BufferedInputFile
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database import (
    get_user, get_user_active_pack, create_sticker_pack, 
    increment_sticker_count, delete_user_pack, get_user_all_packs,
    update_pack_sticker_count
)
from templates import (
    NEED_TO_START, ASK_PACK_NAME, PACK_CREATED, 
    STICKER_ADDED, NO_MEDIA_REPLY, VIDEO_TOO_LARGE,
    PACK_NAME_INVALID, PROCESSING_MEDIA,
    ERROR_OCCURRED, VIDEO_COMPRESSION_FAILED,
    PACK_FULL_MESSAGE, NEW_PACK_CREATED_MULTI,
    STICKER_ADDED_SIMPLE, PACK_NOT_FOUND_MESSAGE
)
from utils.fsm_states import KangStates
from utils.helpers import (
    validate_pack_name, generate_short_name, 
    format_pack_name, get_file_size_mb
)
from utils.converters import (
    convert_image_to_webp, convert_video_to_webm,
    cleanup_temp_files, create_temp_dir
)
from config import BOT_USERNAME, MAX_VIDEO_SIZE_MB
from rate_limiter import is_rate_limited

logger = logging.getLogger(__name__)
router = Router()

# Predefined list of emojis for random selection
EMOJI_LIST = ["😀", "😂", "🥰", "😎", "🤯", "😱", "😜", "🤖", "🐱", "🌸", "🍕", "🎉", "❤️", "✨", "⭐"]

def get_random_emoji():
    """Get random emoji from predefined list"""
    return random.choice(EMOJI_LIST)


@router.message(Command("kang"))
async def cmd_kang(message: Message, state: FSMContext, bot: Bot):
    """
    ✅ Handle /kang command with multiple packs support
    
    Race condition prevention with guaranteed cleanup
    """
    # Rate limiting check
    if await is_rate_limited(message.from_user.id):
        await message.reply("⏳ Please wait a few seconds before making another request.")
        return
    
    user_id = message.from_user.id
    processing_msg = None
    
    try:
        # Check if user has started the bot
        user = await get_user(user_id)
        if not user or not user.get("has_started", False):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="Start me",
                    url=f"https://t.me/{BOT_USERNAME}?start=kang"
                )
            ]])
            await message.reply(NEED_TO_START, reply_markup=keyboard)
            return
        
        # Check if replying to a message with media
        if not message.reply_to_message:
            await message.reply(NO_MEDIA_REPLY)
            return
        
        replied_msg = message.reply_to_message
        
        # Get media from replied message
        media = None
        media_type = None
        
        if replied_msg.photo:
            media = replied_msg.photo[-1]
            media_type = "photo"
        elif replied_msg.sticker:
            media = replied_msg.sticker
            media_type = "sticker"
        elif replied_msg.animation:
            media = replied_msg.animation
            media_type = "animation"
        elif replied_msg.video:
            media = replied_msg.video
            media_type = "video"
        
        if not media:
            await message.reply(NO_MEDIA_REPLY)
            return
        
        # Check video size
        if media_type == "video":
            file_size_mb = get_file_size_mb(media.file_size)
            if file_size_mb > MAX_VIDEO_SIZE_MB:
                await message.reply(VIDEO_TOO_LARGE)
                return
        
        # ✅ FIX 1: Get fresh pack data to prevent race condition
        active_pack = await get_user_active_pack(user_id)
        
        if not active_pack:
            # Ask for first pack name
            await state.set_state(KangStates.waiting_for_pack_name)
            await state.update_data(media=media.file_id, media_type=media_type)
            await message.reply(ASK_PACK_NAME)
            return
        
        # Add sticker to existing pack
        processing_msg = await message.reply(PROCESSING_MEDIA)
        
        # ✅ FIX 2: Pass processing_msg to add_sticker_to_pack for cleanup
        success, pack_full = await add_sticker_to_pack(
            bot=bot,
            user_id=user_id,
            pack_short_name=active_pack["short_name"],
            pack_data=active_pack,
            media=media,
            media_type=media_type,
            message=message,
            state=state
        )
        
        if success:
            await increment_sticker_count(user_id)
            
            # Create button for pack link
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="View Pack",
                    url=active_pack["pack_link"]
                )
            ]])
            
            await processing_msg.edit_text(STICKER_ADDED_SIMPLE, reply_markup=keyboard)
            
        elif pack_full:
            # Pack is full, ask for new pack name
            await processing_msg.delete()
            await state.set_state(KangStates.waiting_for_pack_name)
            await state.update_data(media=media.file_id, media_type=media_type)
            
            # Get all user packs to show count
            all_packs = await get_user_all_packs(user_id)
            pack_count = len(all_packs)
            
            await message.reply(PACK_FULL_MESSAGE.format(pack_count=pack_count))
            
        else:
            await processing_msg.edit_text(ERROR_OCCURRED)
            
    except Exception as e:
        logger.error(f"Error in kang command: {e}", exc_info=True)
        await state.clear()
        
        if processing_msg:
            try:
                await processing_msg.edit_text(ERROR_OCCURRED)
            except Exception:
                await message.reply(ERROR_OCCURRED)
        else:
            await message.reply(ERROR_OCCURRED)


@router.message(KangStates.waiting_for_pack_name)
async def process_pack_name(message: Message, state: FSMContext, bot: Bot):
    """
    ✅ Process pack name input with guaranteed cleanup
    """
    # Check if message has text
    if not message.text:
        await message.reply("Please send a valid pack name.")
        return
    
    pack_name = message.text.strip()
    processing_msg = None
    temp_files = []
    
    # ✅ FIX 3: Use try-finally for guaranteed cleanup
    try:
        # Validate pack name
        is_valid, error = validate_pack_name(pack_name)
        
        if not is_valid:
            if error == "pack_name_too_long":
                await message.reply(
                    PACK_NAME_INVALID.format(length=len(pack_name))
                )
            else:
                await message.reply(ERROR_OCCURRED)
            return
        
        # Get stored media info
        data = await state.get_data()
        media_file_id = data.get("media")
        media_type = data.get("media_type")
        
        if not media_file_id:
            await message.reply(ERROR_OCCURRED)
            await state.clear()
            return
        
        user_id = message.from_user.id
        
        # Format pack name
        formatted_pack_name = format_pack_name(pack_name)
        
        # ✅ FIX 4: Generate short name with guaranteed uniqueness (from helpers.py fix)
        short_name = generate_short_name(pack_name, user_id)
        
        # Create pack
        processing_msg = await message.reply(PROCESSING_MEDIA)
        
        # Get file
        file = await bot.get_file(media_file_id)
        
        # ✅ FIX 5: Add timestamp to temp files
        timestamp = int(time.time() * 1000)
        temp_dir = create_temp_dir()
        
        # Prepare sticker based on media type
        sticker_file = None
        
        if media_type == "sticker":
            sticker_file = media_file_id
            sticker_format = "static"
            
        elif media_type == "photo":
            input_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_input.jpg")
            output_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_output.webp")
            temp_files.extend([input_path, output_path])
            
            await bot.download_file(file.file_path, input_path)
            
            if await convert_image_to_webp(input_path, output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webp")
                sticker_format = "static"
            else:
                await processing_msg.edit_text("❌ Failed to convert image.")
                await state.clear()
                return
        
        elif media_type in ["animation", "video"]:
            input_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_input.mp4")
            output_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_output.webm")
            temp_files.extend([input_path, output_path])
            
            await bot.download_file(file.file_path, input_path)
            
            conversion_success = await convert_video_to_webm(input_path, output_path)
            
            if conversion_success and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webm")
                sticker_format = "video"
            else:
                await processing_msg.edit_text(VIDEO_COMPRESSION_FAILED)
                await state.clear()
                return
        
        if not sticker_file:
            await processing_msg.edit_text("❌ Failed to prepare sticker file.")
            await state.clear()
            return
        
        # Get random emoji
        random_emoji = get_random_emoji()
        
        # Create sticker pack
        sticker = InputSticker(
            sticker=sticker_file,
            emoji_list=[random_emoji],
            format=sticker_format
        )
        
        # ✅ FIX 6: Retry logic for Telegram API race conditions
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await bot.create_new_sticker_set(
                    user_id=user_id,
                    name=short_name,
                    title=formatted_pack_name,
                    stickers=[sticker]
                )
                break  # Success
                
            except Exception as e:
                error_msg = str(e)
                
                if "STICKERSET_INVALID" in error_msg and attempt < max_retries - 1:
                    # Pack name collision, regenerate
                    logger.warning(f"Pack name collision, regenerating (attempt {attempt + 1})")
                    short_name = generate_short_name(pack_name, user_id)
                    continue
                    
                elif attempt == max_retries - 1:
                    # Final attempt failed
                    raise
                    
                else:
                    raise
        
        # Save to database
        pack_link = f"https://t.me/addstickers/{short_name}"
        await create_sticker_pack(
            user_id=user_id,
            pack_name=formatted_pack_name,
            short_name=short_name
        )
        
        # Get all user packs count
        all_packs = await get_user_all_packs(user_id)
        pack_count = len(all_packs)
        
        # Create button for pack link
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="View Pack",
                url=pack_link
            )
        ]])
        
        await processing_msg.edit_text(
            NEW_PACK_CREATED_MULTI.format(
                pack_name=formatted_pack_name,
                pack_count=pack_count
            ),
            reply_markup=keyboard
        )
        await state.clear()
        
        logger.info(f"Successfully created pack {short_name} for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error processing pack name: {e}", exc_info=True)
        await state.clear()
        
        if processing_msg:
            try:
                await processing_msg.edit_text(ERROR_OCCURRED)
            except Exception:
                await message.reply(ERROR_OCCURRED)
        else:
            await message.reply(ERROR_OCCURRED)
    
    # ✅ FIX 7: GUARANTEED cleanup in finally block
    finally:
        cleanup_temp_files(*temp_files)
        logger.debug(f"Cleanup completed for user {user_id if 'user_id' in locals() else 'unknown'}")


async def add_sticker_to_pack(bot: Bot, user_id: int, pack_short_name: str, 
                              pack_data: dict, media, media_type: str, 
                              message: Message, state: FSMContext):
    """
    ✅ Add sticker to existing pack with automatic recovery and guaranteed cleanup
    """
    temp_files = []
    
    # ✅ FIX 8: Use try-finally for guaranteed cleanup
    try:
        # ✅ FIX 9: Add timestamp to temp files
        timestamp = int(time.time() * 1000)
        temp_dir = create_temp_dir()
        sticker_file = None
        
        if media_type == "sticker":
            sticker_file = media.file_id
            sticker_format = "static" if not media.is_video else "video"
        
        elif media_type == "photo":
            file = await bot.get_file(media.file_id)
            input_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_add_input.jpg")
            output_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_add_output.webp")
            temp_files.extend([input_path, output_path])
            
            await bot.download_file(file.file_path, input_path)
            
            if await convert_image_to_webp(input_path, output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webp")
                sticker_format = "static"
            else:
                logger.error(f"Failed to convert image for user {user_id}")
                return False, False
        
        elif media_type in ["animation", "video"]:
            file = await bot.get_file(media.file_id)
            input_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_add_input.mp4")
            output_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_add_output.webm")
            temp_files.extend([input_path, output_path])
            
            await bot.download_file(file.file_path, input_path)
            
            conversion_success = await convert_video_to_webm(input_path, output_path)
            
            if conversion_success and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webm")
                sticker_format = "video"
            else:
                logger.error(f"Failed to convert video for user {user_id}")
                return False, False
        
        if not sticker_file:
            logger.error(f"No sticker file prepared for user {user_id}")
            return False, False
        
        # Get random emoji
        random_emoji = get_random_emoji()
        
        # Add to pack
        sticker = InputSticker(
            sticker=sticker_file,
            emoji_list=[random_emoji],
            format=sticker_format
        )
        
        try:
            await bot.add_sticker_to_set(
                user_id=user_id,
                name=pack_short_name,
                sticker=sticker
            )
            
            logger.info(f"Successfully added sticker to pack {pack_short_name} for user {user_id}")
            return True, False
            
        except Exception as e:
            error_msg = str(e)
            
            # Handle STICKERSET_INVALID (pack deleted or not found)
            if "STICKERSET_INVALID" in error_msg:
                logger.warning(f"Pack {pack_short_name} not found, deleting from database")
                await delete_user_pack(user_id)
                
                await state.update_data(
                    media=media.file_id, 
                    media_type=media_type
                )
                await state.set_state(KangStates.waiting_for_pack_name)
                
                await message.reply(PACK_NOT_FOUND_MESSAGE)
                
                return False, False
            
            # Handle STICKERS_TOO_MUCH (pack is full - 120 stickers limit)
            elif "STICKERS_TOO_MUCH" in error_msg:
                logger.info(f"Pack {pack_short_name} is full (120 stickers)")
                # Mark pack as full in database
                await update_pack_sticker_count(pack_short_name, 120)
                return False, True
            
            else:
                logger.error(f"Error adding sticker to pack {pack_short_name}: {e}", exc_info=True)
                return False, False
        
    except Exception as e:
        logger.error(f"Unexpected error in add_sticker_to_pack: {e}", exc_info=True)
        return False, False
        
    # ✅ FIX 10: GUARANTEED cleanup in finally block
    finally:
        cleanup_temp_files(*temp_files)
        logger.debug(f"add_sticker_to_pack cleanup completed for user {user_id}")
