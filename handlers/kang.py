import os
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputSticker, BufferedInputFile
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database import (
    get_user, get_user_pack, create_sticker_pack, 
    increment_sticker_count
)
from templates import (
    NEED_TO_START, ASK_PACK_NAME, PACK_CREATED, 
    STICKER_ADDED, NO_MEDIA_REPLY, VIDEO_TOO_LARGE,
    PACK_NAME_TOO_LONG, PACK_NAME_INVALID, PROCESSING_MEDIA,
    ERROR_OCCURRED, VIDEO_COMPRESSION_FAILED
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

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("kang"))
async def cmd_kang(message: Message, state: FSMContext, bot: Bot):
    """Handle /kang command"""
    user_id = message.from_user.id
    
    # Check if user has started the bot
    user = await get_user(user_id)
    if not user or not user.get("has_started", False):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Start me",
                url=f"https://t.me/{BOT_USERNAME}?start=kang"
            )
        ]])
        await message.answer(NEED_TO_START, reply_markup=keyboard)
        return
    
    # Check if replying to a message with media
    if not message.reply_to_message:
        await message.answer(NO_MEDIA_REPLY)
        return
    
    replied_msg = message.reply_to_message
    
    # Get media from replied message
    media = None
    media_type = None
    
    if replied_msg.photo:
        media = replied_msg.photo[-1]  # Get highest quality
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
        await message.answer(NO_MEDIA_REPLY)
        return
    
    # Check video size
    if media_type == "video":
        file_size_mb = get_file_size_mb(media.file_size)
        if file_size_mb > MAX_VIDEO_SIZE_MB:
            await message.answer(VIDEO_TOO_LARGE)
            return
    
    # Check if user has a pack
    pack = await get_user_pack(user_id)
    
    if not pack:
        # Ask for pack name
        await state.set_state(KangStates.waiting_for_pack_name)
        await state.update_data(media=media.file_id, media_type=media_type)
        await message.answer(ASK_PACK_NAME)
        return
    
    # Add sticker to existing pack
    processing_msg = await message.answer(PROCESSING_MEDIA)
    
    try:
        success = await add_sticker_to_pack(
            bot=bot,
            user_id=user_id,
            pack_short_name=pack["short_name"],
            media=media,
            media_type=media_type
        )
        
        await processing_msg.delete()
        
        if success:
            await increment_sticker_count(user_id)
            await message.answer(
                STICKER_ADDED.format(pack_link=pack["pack_link"])
            )
        else:
            await message.answer(ERROR_OCCURRED)
    except Exception as e:
        logger.error(f"Error adding sticker: {e}")
        await processing_msg.delete()
        await message.answer(ERROR_OCCURRED)

@router.message(KangStates.waiting_for_pack_name)
async def process_pack_name(message: Message, state: FSMContext, bot: Bot):
    """Process pack name input"""
    pack_name = message.text
    
    # Validate pack name
    is_valid, error = validate_pack_name(pack_name)
    
    if not is_valid:
        if error == "pack_name_too_long":
            await message.answer(PACK_NAME_TOO_LONG)
        elif error == "pack_name_invalid":
            await message.answer(PACK_NAME_INVALID)
        else:
            await message.answer(ERROR_OCCURRED)
        return
    
    # Get stored media info
    data = await state.get_data()
    media_file_id = data.get("media")
    media_type = data.get("media_type")
    
    if not media_file_id:
        await message.answer(ERROR_OCCURRED)
        await state.clear()
        return
    
    user_id = message.from_user.id
    
    # Format pack name
    formatted_pack_name = format_pack_name(pack_name)
    
    # Generate short name
    short_name = generate_short_name(pack_name, user_id)
    
    # Create pack
    processing_msg = await message.answer(PROCESSING_MEDIA)
    
    temp_files = []
    
    try:
        # Get file
        file = await bot.get_file(media_file_id)
        
        # Create temporary directory
        temp_dir = create_temp_dir()
        
        # Prepare sticker based on media type
        sticker_file = None
        
        if media_type == "sticker":
            # Direct sticker
            sticker_file = media_file_id
            sticker_format = "static"
        elif media_type == "photo":
            # Convert photo to WebP
            input_path = os.path.join(temp_dir, f"{user_id}_input.jpg")
            output_path = os.path.join(temp_dir, f"{user_id}_output.webp")
            temp_files.extend([input_path, output_path])
            
            await bot.download_file(file.file_path, input_path)
            
            if await convert_image_to_webp(input_path, output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webp")
                sticker_format = "static"
            else:
                raise Exception("Failed to convert image")
        
        elif media_type in ["animation", "video"]:
            # Convert to WebM with automatic duration adjustment
            input_path = os.path.join(temp_dir, f"{user_id}_input.mp4")
            output_path = os.path.join(temp_dir, f"{user_id}_output.webm")
            temp_files.extend([input_path, output_path])
            
            await bot.download_file(file.file_path, input_path)
            
            conversion_success = await convert_video_to_webm(input_path, output_path)
            
            if conversion_success and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webm")
                sticker_format = "video"
            else:
                cleanup_temp_files(*temp_files)
                await processing_msg.delete()
                await message.answer(VIDEO_COMPRESSION_FAILED)
                await state.clear()
                return
        
        if not sticker_file:
            raise Exception("Failed to prepare sticker file")
        
        # Create sticker pack
        sticker = InputSticker(
            sticker=sticker_file,
            emoji_list=["🎨"],
            format=sticker_format
        )
        
        await bot.create_new_sticker_set(
            user_id=user_id,
            name=short_name,
            title=formatted_pack_name,
            stickers=[sticker]
        )
        
        # Save to database
        pack_link = f"https://t.me/addstickers/{short_name}"
        await create_sticker_pack(
            user_id=user_id,
            pack_name=formatted_pack_name,
            short_name=short_name
        )
        
        # Clean up temp files
        cleanup_temp_files(*temp_files)
        
        await processing_msg.delete()
        await message.answer(
            PACK_CREATED.format(
                pack_name=formatted_pack_name,
                pack_link=pack_link
            )
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error creating pack: {e}")
        cleanup_temp_files(*temp_files)
        await processing_msg.delete()
        await message.answer(ERROR_OCCURRED)
        await state.clear()

async def add_sticker_to_pack(bot: Bot, user_id: int, pack_short_name: str, 
                              media, media_type: str) -> bool:
    """Add sticker to existing pack"""
    temp_files = []
    
    try:
        temp_dir = create_temp_dir()
        sticker_file = None
        
        if media_type == "sticker":
            # Direct sticker
            sticker_file = media.file_id
            sticker_format = "static" if not media.is_video else "video"
        
        elif media_type == "photo":
            # Convert photo
            file = await bot.get_file(media.file_id)
            input_path = os.path.join(temp_dir, f"{user_id}_add_input.jpg")
            output_path = os.path.join(temp_dir, f"{user_id}_add_output.webp")
            temp_files.extend([input_path, output_path])
            
            await bot.download_file(file.file_path, input_path)
            
            if await convert_image_to_webp(input_path, output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webp")
                sticker_format = "static"
            else:
                cleanup_temp_files(*temp_files)
                return False
        
        elif media_type in ["animation", "video"]:
            # Convert video/GIF
            file = await bot.get_file(media.file_id)
            input_path = os.path.join(temp_dir, f"{user_id}_add_input.mp4")
            output_path = os.path.join(temp_dir, f"{user_id}_add_output.webm")
            temp_files.extend([input_path, output_path])
            
            await bot.download_file(file.file_path, input_path)
            
            conversion_success = await convert_video_to_webm(input_path, output_path)
            
            if conversion_success and os.path.exists(output_path):
                # Check final file size
                final_size = os.path.getsize(output_path)
                if final_size > 256 * 1024:  # 256KB
                    cleanup_temp_files(*temp_files)
                    logger.error(f"Compressed video still too large: {final_size} bytes")
                    return False
                
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webm")
                sticker_format = "video"
            else:
                cleanup_temp_files(*temp_files)
                return False
        
        if not sticker_file:
            cleanup_temp_files(*temp_files)
            return False
        
        # Add to pack
        sticker = InputSticker(
            sticker=sticker_file,
            emoji_list=["🎨"],
            format=sticker_format
        )
        
        await bot.add_sticker_to_set(
            user_id=user_id,
            name=pack_short_name,
            sticker=sticker
        )
        
        cleanup_temp_files(*temp_files)
        return True
        
    except Exception as e:
        logger.error(f"Error adding sticker to pack: {e}")
        cleanup_temp_files(*temp_files)
        return False
