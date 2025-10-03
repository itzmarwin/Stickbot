import os
import base64
import logging
from random import choice
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from aiogram.utils.markdown import html_decoration as hd

from utils.quotly_api import QuotlyAPI

logger = logging.getLogger(__name__)
router = Router()

# Available background colors
COLORS = [
    "#1b1429", "#0d1117", "#1a1a2e", "#16213e", "#0f3460",
    "#533483", "#6c5ce7", "#a29bfe", "#fd79a8", "#fab1a0",
    "#ff7675", "#d63031", "#e17055", "#fdcb6e", "#ffeaa7",
    "#55efc4", "#00b894", "#81ecec", "#74b9ff", "#a29bfe"
]

quotly = QuotlyAPI()

@router.message(Command("q", "quote"))
async def cmd_quote(message: Message, bot: Bot):
    """Handle /q command - create quote sticker using lyo.su API"""
    
    # Check if replying to a message
    if not message.reply_to_message:
        await message.reply(
            "⚠️ <b>Please reply to a message to quote it!</b>\n\n"
            "Usage: Reply to any message and send /q"
        )
        return
    
    reply_msg = message.reply_to_message
    
    # Check if message has text
    if not reply_msg.text and not reply_msg.caption:
        await message.reply(
            "⚠️ <b>This message has no text to quote!</b>\n\n"
            "I can only quote text messages."
        )
        return
    
    # Parse command arguments
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
    
    messages_to_quote = []
    bg_color = choice(COLORS)  # Random color by default
    quote_count = 1
    
    # Parse arguments
    if args:
        parts = args.split(maxsplit=1)
        
        # Check if first arg is a number (multiple quotes)
        if parts[0].isdigit():
            quote_count = int(parts[0])
            if quote_count > 10:
                quote_count = 10
            if len(parts) > 1:
                bg_color = parts[1] if parts[1] in COLORS or parts[1].startswith("#") else choice(COLORS)
        
        # Check for color name
        elif parts[0] in ["red", "blue", "green", "purple", "pink", "orange", "yellow", "cyan", "black", "white"]:
            color_map = {
                "red": "#d63031",
                "blue": "#74b9ff",
                "green": "#00b894",
                "purple": "#6c5ce7",
                "pink": "#fd79a8",
                "orange": "#e17055",
                "yellow": "#fdcb6e",
                "cyan": "#81ecec",
                "black": "#0d1117",
                "white": "#ffffff"
            }
            bg_color = color_map.get(parts[0], choice(COLORS))
        
        # Check if it's a hex color
        elif parts[0].startswith("#"):
            bg_color = parts[0]
    
    # Send processing message
    processing = await message.reply("⏳ <b>Creating quote sticker...</b>")
    
    try:
        # Get messages to quote
        if quote_count > 1:
            # Get multiple messages
            messages_to_quote = []
            start_id = reply_msg.message_id
            
            for i in range(quote_count):
                try:
                    msg = await bot.forward_message(
                        chat_id=message.chat.id,
                        from_chat_id=message.chat.id,
                        message_id=start_id + i
                    )
                    # Delete the forwarded message
                    await msg.delete()
                    
                    # Get the actual message
                    actual_msg = await bot.forward_message(
                        chat_id=message.chat.id,
                        from_chat_id=message.chat.id, 
                        message_id=start_id + i
                    )
                    await actual_msg.delete()
                    
                    messages_to_quote.append(reply_msg)
                except:
                    break
        else:
            messages_to_quote = [reply_msg]
        
        # Format messages for API
        formatted_messages = []
        for msg in messages_to_quote:
            formatted_msg = await quotly.format_message(msg, bot)
            if formatted_msg:
                formatted_messages.append(formatted_msg)
        
        if not formatted_messages:
            raise Exception("No valid messages to quote")
        
        # Create quote using API
        sticker_data = await quotly.create_quote(
            messages=formatted_messages,
            bg_color=bg_color
        )
        
        if not sticker_data:
            raise Exception("Failed to generate quote sticker")
        
        # Send as sticker
        sticker_file = BufferedInputFile(sticker_data, filename="quote.webp")
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
