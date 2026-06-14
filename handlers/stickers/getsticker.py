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
    try:
        with Image.open(webp_path) as img:
            if img.mode == 'P':
                img = img.convert('RGBA')
            elif img.mode != 'RGBA':
                img = img.convert('RGBA')
            img.save(png_path, 'PNG')
        return True
    except Exception as e:
        logger.error(f"Error converting WebP to PNG: {e}")
        return False


async def cleanup_files(*file_paths):
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Error cleaning up {file_path}: {e}")


@router.message(Command("getsticker"))
async def cmd_getsticker(message: Message, bot: Bot):
    processing_msg = None
    temp_files = []

    try:
        if not message.reply_to_message:
            await message.reply(GETSTICKER_NO_REPLY)
            return

        replied_msg = message.reply_to_message

        if not replied_msg.sticker:
            await message.reply(GETSTICKER_NOT_STICKER)
            return

        sticker = replied_msg.sticker

        if sticker.is_video:
            await message.reply(GETSTICKER_VIDEO_NOT_SUPPORTED)
            return

        processing_msg = await message.reply(GETSTICKER_PROCESSING)

        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)

        user_id = message.from_user.id
        webp_path = temp_dir / f"{user_id}_sticker.webp"
        png_path = temp_dir / f"{user_id}_sticker.png"

        temp_files.extend([webp_path, png_path])

        file = await bot.get_file(sticker.file_id)
        await bot.download_file(file.file_path, webp_path)

        success = await asyncio.get_event_loop().run_in_executor(
            None,
            convert_webp_to_png, str(webp_path), str(png_path)
        )

        if not success or not os.path.exists(png_path):
            await processing_msg.edit_text(ERROR_OCCURRED)
            await cleanup_files(*temp_files)
            return

        with open(png_path, 'rb') as f:
            png_file = BufferedInputFile(f.read(), filename="sticker.png")

        await message.reply_document(
            png_file,
            caption=STICKER_CONVERSION_SUCCESS
        )

        if processing_msg:
            await processing_msg.delete()

        asyncio.create_task(cleanup_files(*temp_files))

    except Exception as e:
        logger.error(f"Error in getsticker command: {e}")

        if processing_msg:
            try:
                await processing_msg.delete()
            except:
                pass

        await message.reply(ERROR_OCCURRED)
        await cleanup_files(*temp_files)
