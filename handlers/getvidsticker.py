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
    ERROR_OCCURRED
)

logger = logging.getLogger(__name__)
router = Router()


async def cleanup_files(*file_paths):
    """
    Clean up temporary files
    
    Args:
        *file_paths: Variable number of file paths to delete
    """
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up file: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up {file_path}: {e}")


@router.message(Command("getvidsticker"))
async def cmd_getvidsticker(message: Message, bot: Bot):
    """
    ✅ Handle /getvidsticker command - get video sticker as playable video
    
    Guaranteed cleanup with try-finally pattern
    """
    processing_msg = None
    temp_files = []
    
    # ✅ FIX 1: Use try-finally to GUARANTEE cleanup
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
        
        # ✅ FIX 2: Create temporary directory safely
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True, parents=True)
        
        # ✅ FIX 3: Add timestamp to prevent file conflicts
        import time
        timestamp = int(time.time() * 1000)
        user_id = message.from_user.id
        
        webm_path = temp_dir / f"{user_id}_{timestamp}_vidsticker.webm"
        
        temp_files.append(webm_path)
        
        # Download video sticker file
        try:
            file = await bot.get_file(sticker.file_id)
            await bot.download_file(file.file_path, webm_path)
            logger.info(f"Downloaded video sticker for user {user_id}")
        except Exception as e:
            logger.error(f"Error downloading video sticker: {e}")
            await processing_msg.edit_text("❌ Failed to download video sticker. Please try again.")
            return
        
        # Check if file was downloaded successfully
        if not os.path.exists(webm_path):
            logger.error(f"Downloaded file not found: {webm_path}")
            await processing_msg.edit_text(ERROR_OCCURRED)
            return
        
        # ✅ FIX 4: Check file size before reading
        file_size = os.path.getsize(webm_path)
        max_size = 20 * 1024 * 1024  # 20MB limit (Telegram video limit is 50MB, but we limit to 20MB)
        
        if file_size > max_size:
            logger.warning(f"Video file too large: {file_size} bytes (max {max_size})")
            await processing_msg.edit_text("❌ Video sticker is too large (> 20MB). Cannot process.")
            return
        
        if file_size == 0:
            logger.error(f"Downloaded file is empty: {webm_path}")
            await processing_msg.edit_text(ERROR_OCCURRED)
            return
        
        # ✅ FIX 5: Read file with timeout protection
        try:
            async def read_file():
                with open(webm_path, 'rb') as f:
                    return f.read()
            
            video_data = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, read_file),
                timeout=30.0  # 30 second timeout
            )
            
            logger.info(f"Read video file: {len(video_data)} bytes")
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout reading video file for user {user_id}")
            await processing_msg.edit_text("❌ Processing took too long. Please try again.")
            return
        except Exception as e:
            logger.error(f"Error reading video file: {e}")
            await processing_msg.edit_text(ERROR_OCCURRED)
            return
        
        # ✅ FIX 6: Validate video data
        if not video_data or len(video_data) == 0:
            logger.error(f"Video data is empty for user {user_id}")
            await processing_msg.edit_text(ERROR_OCCURRED)
            return
        
        # Create video file with proper MIME type
        # Use .webm extension to maintain compatibility
        video_file = BufferedInputFile(video_data, filename="video_sticker.webm")
        
        # ✅ FIX 7: Send with error handling and timeout
        try:
            await asyncio.wait_for(
                message.reply_video(
                    video=video_file,
                    caption=VIDEO_STICKER_CONVERSION_SUCCESS,
                    supports_streaming=True  # Enable streaming for better playback
                ),
                timeout=60.0  # 60 second timeout for upload
            )
            
            logger.info(f"Successfully sent video sticker to user {user_id}")
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout sending video to user {user_id}")
            await processing_msg.edit_text("❌ Upload took too long. Please try again.")
            return
        except Exception as e:
            logger.error(f"Error sending video: {e}")
            await processing_msg.edit_text("❌ Failed to send video. Please try again.")
            return
        
        # Delete processing message
        if processing_msg:
            try:
                await processing_msg.delete()
            except Exception as e:
                logger.debug(f"Could not delete processing message: {e}")
        
    except Exception as e:
        logger.error(f"Error in getvidsticker command: {e}", exc_info=True)
        
        # Delete processing message if it exists
        if processing_msg:
            try:
                await processing_msg.delete()
            except Exception:
                pass
        
        # ✅ FIX 8: More specific error message
        try:
            await message.reply(ERROR_OCCURRED)
        except Exception:
            logger.error("Could not send error message to user")
    
    # ✅ FIX 9: GUARANTEED cleanup in finally block
    finally:
        # Cleanup files synchronously to ensure completion
        await cleanup_files(*temp_files)
        logger.debug(f"Cleanup completed for user {message.from_user.id if message.from_user else 'unknown'}")
