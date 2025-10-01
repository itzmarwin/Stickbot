import aiohttp
import aiofiles
from typing import Optional
from aiogram.types import Sticker, InputSticker
from aiogram import Bot
from config import settings
import logging
import os
import tempfile
import asyncio

logger = logging.getLogger(__name__)


async def download_sticker(bot: Bot, sticker: Sticker) -> Optional[str]:
    """
    FAST Download sticker file and return local file path
    Returns None if download fails
    """
    try:
        # Get file info from Telegram
        file_info = await bot.get_file(sticker.file_id)
        
        if not file_info.file_path:
            return None
        
        # Create temporary file
        file_extension = get_sticker_file_extension(sticker)
        temp_file = tempfile.NamedTemporaryFile(
            suffix=file_extension,
            delete=False
        )
        temp_file_path = temp_file.name
        temp_file.close()
        
        # Download file from Telegram with optimized settings
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        # Use faster download settings
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(file_url) as response:
                if response.status == 200:
                    async with aiofiles.open(temp_file_path, 'wb') as f:
                        # Increased chunk size for faster download
                        async for chunk in response.content.iter_chunked(16384):
                            await f.write(chunk)
                    
                    return temp_file_path
                else:
                    return None
    
    except Exception as e:
        logger.error(f"Error downloading sticker: {e}")
        return None


async def download_gif(bot: Bot, gif_object) -> Optional[str]:
    """
    FAST Download GIF file and return local file path
    Works with both Animation and Document objects
    Returns None if download fails
    """
    try:
        # Get file info from Telegram
        file_info = await bot.get_file(gif_object.file_id)
        
        if not file_info.file_path:
            return None
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(
            suffix='.gif',
            delete=False
        )
        temp_file_path = temp_file.name
        temp_file.close()
        
        # Download file from Telegram with optimized settings
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        # Use faster download settings
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(file_url) as response:
                if response.status == 200:
                    async with aiofiles.open(temp_file_path, 'wb') as f:
                        # Increased chunk size for faster download
                        async for chunk in response.content.iter_chunked(16384):
                            await f.write(chunk)
                    
                    return temp_file_path
                else:
                    return None
    
    except Exception as e:
        logger.error(f"Error downloading GIF: {e}")
        return None


def get_sticker_file_extension(sticker: Sticker) -> str:
    """Get appropriate file extension for sticker type"""
    if sticker.is_animated:
        return ".tgs"
    elif sticker.is_video:
        return ".webm"
    else:
        return ".webp"


def cleanup_temp_file(file_path: str) -> None:
    """Clean up temporary file - FAST version"""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception as e:
        logger.error(f"Error cleaning up temp file {file_path}: {e}")


async def create_input_sticker(sticker_file_path: str, emoji_list: list[str]) -> InputSticker:
    """
    Create InputSticker object for Telegram API - FAST version
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
    FAST Create a new sticker pack with the first sticker
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
    FAST Add sticker to existing pack
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
            
            return True
            
        finally:
            # Clean up temp file
            cleanup_temp_file(sticker_file_path)
    
    except Exception as e:
        logger.error(f"Error adding sticker to pack: {e}")
        return False


# NEW OPTIMIZED FUNCTIONS FOR MAXIMUM SPEED

async def create_sticker_pack_fast(
    bot: Bot,
    user_id: int,
    pack_name: str,
    pack_short_name: str,
    sticker: Sticker
) -> bool:
    """
    ULTRA FAST sticker pack creation
    """
    try:
        # Download sticker
        sticker_file_path = await download_sticker(bot, sticker)
        if not sticker_file_path:
            return False
        
        try:
            emoji_list = get_sticker_emoji(sticker)
            input_sticker = await create_input_sticker(sticker_file_path, emoji_list)
            
            # Create pack
            await bot.create_new_sticker_set(
                user_id=user_id,
                name=pack_short_name,
                title=pack_name,
                stickers=[input_sticker]
            )
            return True
        finally:
            cleanup_temp_file(sticker_file_path)
    except Exception as e:
        logger.error(f"Fast sticker pack creation error: {e}")
        return False


async def add_sticker_to_pack_fast(
    bot: Bot,
    user_id: int,
    pack_short_name: str,
    sticker: Sticker
) -> bool:
    """
    ULTRA FAST sticker addition to pack
    """
    try:
        # Download sticker
        sticker_file_path = await download_sticker(bot, sticker)
        if not sticker_file_path:
            return False
        
        try:
            emoji_list = get_sticker_emoji(sticker)
            input_sticker = await create_input_sticker(sticker_file_path, emoji_list)
            
            # Add to pack
            await bot.add_sticker_to_set(
                user_id=user_id,
                name=pack_short_name,
                sticker=input_sticker
            )
            return True
        finally:
            cleanup_temp_file(sticker_file_path)
    except Exception as e:
        logger.error(f"Fast sticker addition error: {e}")
        return False


async def add_converted_sticker_to_pack_fast(
    bot: Bot,
    user_id: int,
    pack_short_name: str,
    webm_file_path: str
) -> bool:
    """
    FAST Add converted WebM sticker to pack
    """
    try:
        from aiogram.types import FSInputFile, InputSticker
        
        input_file = FSInputFile(webm_file_path)
        input_sticker = InputSticker(
            sticker=input_file,
            emoji_list=["🎬"],  # Default emoji for GIF conversions
            format="video"
        )
        
        await bot.add_sticker_to_set(
            user_id=user_id,
            name=pack_short_name,
            sticker=input_sticker
        )
        return True
    except Exception as e:
        logger.error(f"Error adding converted sticker: {e}")
        return False


async def create_pack_with_converted_sticker_fast(
    bot: Bot,
    user_id: int,
    pack_name: str,
    pack_short_name: str,
    webm_file_path: str
) -> bool:
    """
    FAST Create pack with converted WebM sticker
    """
    try:
        from aiogram.types import FSInputFile, InputSticker
        
        input_file = FSInputFile(webm_file_path)
        input_sticker = InputSticker(
            sticker=input_file,
            emoji_list=["🎬"],  # Default emoji for GIF conversions
            format="video"
        )
        
        await bot.create_new_sticker_set(
            user_id=user_id,
            name=pack_short_name,
            title=pack_name,
            stickers=[input_sticker]
        )
        return True
    except Exception as e:
        logger.error(f"Error creating pack with converted sticker: {e}")
        return False
