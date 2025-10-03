import os
import io
import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, BufferedInputFile
from PIL import Image, ImageDraw, ImageFont
import aiohttp

from utils.quote_generator import generate_quote_sticker

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("q", "quote"))
async def cmd_quote(message: Message, bot: Bot):
    """Handle /q command - create quote sticker from replied message"""
    
    # Check if replying to a message
    if not message.reply_to_message:
        await message.reply(
            "⚠️ <b>Please reply to a message to quote it!</b>\n\n"
            "Usage: Reply to any message and send /q"
        )
        return
    
    replied_msg = message.reply_to_message
    
    # Check if message has text
    if not replied_msg.text and not replied_msg.caption:
        await message.reply(
            "⚠️ <b>This message has no text to quote!</b>\n\n"
            "I can only quote text messages."
        )
        return
    
    # Send processing message
    processing = await message.reply("⏳ <b>Creating quote sticker...</b>")
    
    try:
        # Get user info
        user = replied_msg.from_user
        user_name = user.first_name
        if user.last_name:
            user_name += f" {user.last_name}"
        
        # Get message text
        text = replied_msg.text or replied_msg.caption
        
        # Get user profile photo
        profile_pic = None
        try:
            photos = await bot.get_user_profile_photos(user.id, limit=1)
            if photos.total_count > 0:
                photo = photos.photos[0][-1]  # Get largest photo
                file = await bot.get_file(photo.file_id)
                
                # Download profile photo
                photo_bytes = io.BytesIO()
                await bot.download_file(file.file_path, photo_bytes)
                photo_bytes.seek(0)
                profile_pic = Image.open(photo_bytes)
        except Exception as e:
            logger.warning(f"Could not get profile photo: {e}")
            profile_pic = None
        
        # Get timestamp
        timestamp = replied_msg.date.strftime("%H:%M")
        
        # Generate quote sticker
        sticker_bytes = await generate_quote_sticker(
            user_name=user_name,
            text=text,
            profile_pic=profile_pic,
            timestamp=timestamp
        )
        
        if not sticker_bytes:
            raise Exception("Failed to generate quote sticker")
        
        # Send as sticker
        sticker_file = BufferedInputFile(sticker_bytes, filename="quote.webp")
        await bot.send_sticker(
            chat_id=message.chat.id,
            sticker=sticker_file,
            reply_to_message_id=message.message_id
        )
        
        # Delete processing message
        await processing.delete()
        
    except Exception as e:
        logger.error(f"Error creating quote: {e}")
        await processing.edit_text(
            "❌ <b>Failed to create quote sticker!</b>\n\n"
            "Please try again later."
      )
