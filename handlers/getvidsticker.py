import os
import logging
import asyncio
from pathlib import Path
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from aiogram import Bot

from templates import (
    GETVIDSTICKER_NO_REPLY,
    GETVIDSTICKER_NOT_STICKER,
    GETVIDSTICKER_NOT_VIDEO,
    GETVIDSTICKER_PROCESSING,
    VIDEO_STICKER_CONVERSION_SUCCESS,
    GENERIC_ERROR_MESSAGE
)

logger = logging.getLogger(__name__)
router = Router()

async def cleanup_files(*file_paths):
    """Clean up temporary files asynchronously"""
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up {file_path}: {e}")

@router.message(Command("getvidsticker"))
async def cmd_getvidsticker(message: Message, bot: Bot):
    """Handle /getvidsticker command - get video sticker as playable video"""
    processing_msg = None
    temp_files = []
    
    try:
        # Check if replying to a message
        if not message.reply_to_message:
            await message.reply(GETVIDSTICKER_NO_REPLY)
            return
        
        replied_msg = message.reply_to_message
        
        # Check if replied message contains a sticker
        if not replied_msg.sticker:
            await message.reply(GETVIDSTICKER_NOT_STICKER)
            return
        
        sticker = replied_msg.sticker
        
        # Check if it's a video sticker
        if not sticker.is_video:
            await message.reply(GETVIDSTICKER_NOT_VIDEO)
            return
        
        # Send processing message
        processing_msg = await message.reply(GETVIDSTICKER_PROCESSING)
        
        # Create temporary directory
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        
        user_id = message.from_user.id
        webm_path = temp_dir / f"{user_id}_vidsticker.webm"
        
        temp_files.append(webm_path)
        
        # Download video sticker file
        file = await bot.get_file(sticker.file_id)
        await bot.download_file(file.file_path, webm_path)
        
        # Check if file was downloaded successfully
        if not os.path.exists(webm_path):
            await processing_msg.edit_text(GENERIC_ERROR_MESSAGE)
            await cleanup_files(*temp_files)
            return
        
        # Read WebM file
        with open(webm_path, 'rb') as f:
            video_data = f.read()
        
        # Create video file with proper MIME type
        video_file = BufferedInputFile(video_data, filename="video.mp4")
        
        # Send as VIDEO (playable in chat)
        await message.reply_video(
            video=video_file,
            caption=VIDEO_STICKER_CONVERSION_SUCCESS
        )
        
        # Delete processing message
        if processing_msg:
            await processing_msg.delete()
        
        # Cleanup files in background
        asyncio.create_task(cleanup_files(*temp_files))
        
    except Exception as e:
        logger.error(f"Error in getvidsticker command: {e}")
        
        # Delete processing message if it exists
        if processing_msg:
            try:
                await processing_msg.delete()
            except:
                pass
        
        await message.reply(GENERIC_ERROR_MESSAGE)
        
        # Cleanup any temporary files
        await cleanup_files(*temp_files)
