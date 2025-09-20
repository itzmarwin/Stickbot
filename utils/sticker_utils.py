import aiohttp
import aiofiles
from typing import Optional, Tuple
from aiogram.types import Sticker, InputSticker
from aiogram import Bot
from config import settings
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


async def download_sticker(bot: Bot, sticker: Sticker) -> Optional[str]:
    """
    Download sticker file and return local file path
    Returns None if download fails
    """
    try:
        # Get file info from Telegram
        file_info = await bot.get_file(sticker.file_id)
        
        if not file_info.file_path:
            logger.error("Could not get file path for sticker")
            return None
        
        # Create temporary file
        file_extension = get_sticker_file_extension(sticker)
        temp_file = tempfile.NamedTemporaryFile(
            suffix=file_extension,
            delete=False
        )
        temp_file_path = temp_file.name
        temp_file.close()
        
        # Download file from Telegram
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status == 200:
                    async with aiofiles.open(temp_file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                    
                    logger.info(f"Downloaded sticker to: {temp_file_path}")
                    return temp_file_path
                else:
                    logger.error(f"Failed to download sticker: HTTP {response.status}")
                    return None
    
    except Exception as e:
        logger.error(f"Error downloading sticker: {e}")
        return None


async def download_gif(bot: Bot, gif_object) -> Optional[str]:
    """
    Download GIF file and return local file path
    Works with both Animation and Document objects
    Returns None if download fails
    """
    try:
        # Get file info from Telegram
        file_info = await bot.get_file(gif_object.file_id)
        
        if not file_info.file_path:
            logger.error("Could not get file path for GIF")
            return None
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(
            suffix='.gif',
            delete=False
        )
        temp_file_path = temp_file.name
        temp_file.close()
        
        # Download file from Telegram
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status == 200:
                    async with aiofiles.open(temp_file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                    
                    logger.info(f"Downloaded GIF to: {temp_file_path}")
                    return temp_file_path
                else:
                    logger.error(f"Failed to download GIF: HTTP {response.status}")
                    return None
    
    except Exception as e:
        logger.error(f"Error downloading GIF: {e}")
        return None


def get_sticker_file_extension(sticker: Sticker) -> str:
    """Get appropriate file extension for sticker type"""
    if sticker.is_animated:
        return ".tgs"  # Animated stickers (Lottie format)
    elif sticker.is_video:
        return ".webm"  # Video stickers
    else:
        return ".webp"  # Static stickers


def cleanup_temp_file(file_path: str) -> None:
    """Clean up temporary file"""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.info(f"Cleaned up temp file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up temp file {file_path}: {e}")


async def create_input_sticker(sticker_file_path: str, emoji_list: list[str]) -> InputSticker:
    """
    Create InputSticker object for Telegram API
    """
    from aiogram.types import FSInputFile
    
    # Create InputFile from file path
    input_file = FSInputFile(sticker_file_path)
    
    # Determine sticker format based on file extension
    if sticker_file_path.endswith('.tgs'):
        sticker_format = "animated"
    elif sticker_file_path.endswith('.webm'):
        sticker_format = "video"
    else:
        sticker_format = "static"
    
    # Create InputSticker
    input_sticker = InputSticker(
        sticker=input_file,
        emoji_list=emoji_list,
        format=sticker_format
    )
    
    return input_sticker


def get_sticker_emoji(sticker: Sticker) -> list[str]:
    """
    Get emoji list from sticker, with fallback
    """
    if sticker.emoji:
        return [sticker.emoji]
    else:
        # Default emoji if none provided
        return ["🔥"]


async def create_sticker_pack(
    bot: Bot,
    user_id: int,
    pack_name: str,
    pack_short_name: str,
    first_sticker: Sticker
) -> bool:
    """
    Create a new sticker pack with the first sticker
    Returns True if successful, False otherwise
    """
    try:
        # Download the first sticker
        sticker_file_path = await download_sticker(bot, first_sticker)
        if not sticker_file_path:
            return False
        
        try:
            # Get emoji for the sticker
            emoji_list = get_sticker_emoji(first_sticker)
            
            # Create InputSticker
            input_sticker = await create_input_sticker(sticker_file_path, emoji_list)
            
            # Create sticker pack
            await bot.create_new_sticker_set(
                user_id=user_id,
                name=pack_short_name,
                title=pack_name,
                stickers=[input_sticker]
            )
            
            logger.info(f"Created sticker pack: {pack_short_name}")
            return True
            
        finally:
            # Clean up temp file
            cleanup_temp_file(sticker_file_path)
    
    except Exception as e:
        logger.error(f"Error creating sticker pack: {e}")
        return False


async def add_sticker_to_pack(
    bot: Bot,
    user_id: int,
    pack_short_name: str,
    sticker: Sticker
) -> bool:
    """
    Add sticker to existing pack
    Returns True if successful, False otherwise
    """
    try:
        # Download the sticker
        sticker_file_path = await download_sticker(bot, sticker)
        if not sticker_file_path:
            return False
        
        try:
            # Get emoji for the sticker
            emoji_list = get_sticker_emoji(sticker)
            
            # Create InputSticker
            input_sticker = await create_input_sticker(sticker_file_path, emoji_list)
            
            # Add sticker to pack
            await bot.add_sticker_to_set(
                user_id=user_id,
                name=pack_short_name,
                sticker=input_sticker
            )
            
            logger.info(f"Added sticker to pack: {pack_short_name}")
            return True
            
        finally:
            # Clean up temp file
            cleanup_temp_file(sticker_file_path)
    
    except Exception as e:
        logger.error(f"Error adding sticker to pack: {e}")
        return False
