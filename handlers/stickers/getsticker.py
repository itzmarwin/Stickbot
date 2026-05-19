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
    """Convert WebP sticker to PNG format"""
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
    """Clean up temporary files"""
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Error cleaning up {file_path}: {e}")

@router.message(Command("getsticker"))
async def cmd_getsticker(message: Message, bot: Bot):
    """Handle /getsticker command - convert sticker to PNG file"""
    processing_msg = None
    temp_files = []
    
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
        
        # Create temporary directory
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        
        user_id = message.from_user.id
        webp_path = temp_dir / f"{user_id}_sticker.webp"
        png_path = temp_dir / f"{user_id}_sticker.png"
        
        temp_files.extend([webp_path, png_path])
        
        # Download sticker file
        file = await bot.get_file(sticker.file_id)
        await bot.download_file(file.file_path, webp_path)
        
        # Convert to PNG in background
        success = await asyncio.get_event_loop().run_in_executor(
            None, 
            convert_webp_to_png, str(webp_path), str(png_path)
        )
        
        if not success or not os.path.exists(png_path):
            await processing_msg.edit_text(ERROR_OCCURRED)
            await cleanup_files(*temp_files)
            return
        
        # Read PNG file and send as DOCUMENT
        with open(png_path, 'rb') as f:
            png_file = BufferedInputFile(f.read(), filename="sticker.png")
        
        # Send as DOCUMENT
        await message.reply_document(
            png_file,
            caption=STICKER_CONVERSION_SUCCESS
        )
        
        # Delete processing message
        if processing_msg:
            await processing_msg.delete()
        
        # Cleanup files in background
        asyncio.create_task(cleanup_files(*temp_files))
        
    except Exception as e:
        logger.error(f"Error in getsticker command: {e}")
        
        # Delete processing message if it exists
        if processing_msg:
            try:
                await processing_msg.delete()
            except:
                pass
        
        await message.reply(ERROR_OCCURRED)
        
        # Cleanup any temporary files
        await cleanup_files(*temp_files)
