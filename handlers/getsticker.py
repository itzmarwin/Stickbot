import os
import logging
import asyncio
from pathlib import Path
from PIL import Image
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from aiogram import Bot

from templates import (
    GETSTICKER_NO_REPLY,
    GETSTICKER_NOT_STICKER,
    GETSTICKER_VIDEO_NOT_SUPPORTED,
    GETSTICKER_PROCESSING,
    STICKER_CONVERSION_SUCCESS,
    ERROR_OCCURRED
)

logger = logging.getLogger(__name__)
router = Router()


def convert_webp_to_png(webp_path: str, png_path: str) -> bool:
    """
    Convert WebP sticker to PNG format
    
    Args:
        webp_path: Path to input WebP file
        png_path: Path to output PNG file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with Image.open(webp_path) as img:
            # Convert to RGB if needed (for PNG compatibility)
            if img.mode in ('RGBA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                rgb_img.save(png_path, 'PNG')
            else:
                img.save(png_path, 'PNG')
        return True
    except Exception as e:
        logger.error(f"Error converting WebP to PNG: {e}")
        return False


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


@router.message(Command("getsticker"))
async def cmd_getsticker(message: Message, bot: Bot):
    """
    ✅ Handle /getsticker command - convert sticker to PNG file
    
    Guaranteed cleanup with try-finally pattern
    """
    processing_msg = None
    temp_files = []
    
    # ✅ FIX 1: Use try-finally to GUARANTEE cleanup
    try:
        # Check if replying to a message
        if not message.reply_to_message:
            await message.reply(GETSTICKER_NO_REPLY)
            return
        
        replied_msg = message.reply_to_message
        
        # Check if replied message contains a sticker
        if not replied_msg.sticker:
            await message.reply(GETSTICKER_NOT_STICKER)
            return
        
        sticker = replied_msg.sticker
        
        # Check if it's a video sticker
        if sticker.is_video:
            await message.reply(GETSTICKER_VIDEO_NOT_SUPPORTED)
            return
        
        # Send processing message
        processing_msg = await message.reply(GETSTICKER_PROCESSING)
        
        # ✅ FIX 2: Create temporary directory safely
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True, parents=True)
        
        # ✅ FIX 3: Add timestamp to prevent file conflicts
        import time
        timestamp = int(time.time() * 1000)
        user_id = message.from_user.id
        
        webp_path = temp_dir / f"{user_id}_{timestamp}_sticker.webp"
        png_path = temp_dir / f"{user_id}_{timestamp}_sticker.png"
        
        temp_files.extend([webp_path, png_path])
        
        # Download sticker file
        try:
            file = await bot.get_file(sticker.file_id)
            await bot.download_file(file.file_path, webp_path)
            logger.info(f"Downloaded sticker for user {user_id}")
        except Exception as e:
            logger.error(f"Error downloading sticker: {e}")
            await processing_msg.edit_text("❌ Failed to download sticker. Please try again.")
            return
        
        # ✅ FIX 4: Add timeout to prevent hanging
        try:
            success = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, 
                    convert_webp_to_png, str(webp_path), str(png_path)
                ),
                timeout=30.0  # 30 second timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Conversion timeout for user {user_id}")
            await processing_msg.edit_text("❌ Conversion took too long. Please try again.")
            return
        
        if not success or not os.path.exists(png_path):
            logger.error(f"Conversion failed for user {user_id}")
            await processing_msg.edit_text(ERROR_OCCURRED)
            return
        
        # ✅ FIX 5: Check file size before sending
        file_size = os.path.getsize(png_path)
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            logger.warning(f"Converted file too large: {file_size} bytes")
            await processing_msg.edit_text("❌ Converted file is too large (> 10MB).")
            return
        
        # Read PNG file and send as DOCUMENT
        try:
            with open(png_path, 'rb') as f:
                png_file = BufferedInputFile(f.read(), filename="sticker.png")
            
            # Send as DOCUMENT
            await message.reply_document(
                png_file,
                caption=STICKER_CONVERSION_SUCCESS
            )
            
            logger.info(f"Successfully sent converted sticker to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error sending document: {e}")
            await processing_msg.edit_text("❌ Failed to send converted file.")
            return
        
        # Delete processing message
        if processing_msg:
            try:
                await processing_msg.delete()
            except Exception as e:
                logger.debug(f"Could not delete processing message: {e}")
        
    except Exception as e:
        logger.error(f"Error in getsticker command: {e}", exc_info=True)
        
        # Delete processing message if it exists
        if processing_msg:
            try:
                await processing_msg.delete()
            except Exception:
                pass
        
        # ✅ FIX 6: More specific error message
        try:
            await message.reply(ERROR_OCCURRED)
        except Exception:
            logger.error("Could not send error message to user")
    
    # ✅ FIX 7: GUARANTEED cleanup in finally block
    finally:
        # Cleanup files synchronously to ensure completion
        await cleanup_files(*temp_files)
        logger.debug(f"Cleanup completed for user {message.from_user.id if message.from_user else 'unknown'}")
