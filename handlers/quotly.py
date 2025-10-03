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

# Default dark theme
DEFAULT_BG = "#1b1429"

# Available background colors (for named colors)
COLOR_MAP = {
    "red": "#d63031",
    "blue": "#74b9ff", 
    "green": "#00b894",
    "purple": "#6c5ce7",
    "pink": "#fd79a8",
    "orange": "#e17055",
    "yellow": "#fdcb6e",
    "cyan": "#81ecec",
    "black": "#0d1117",
    "white": "#ffffff",
    "dark": "#1b1429",
    "grey": "#2f3640",
    "brown": "#8B4513"
}

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
    
    bg_color = DEFAULT_BG  # Default dark theme
    quote_count = 1
    
    # Parse arguments
    if args:
        parts = args.split(maxsplit=1)
        
        # Check if first arg is a number (multiple consecutive quotes)
        if parts[0].isdigit():
            quote_count = int(parts[0])
            if quote_count > 10:
                quote_count = 10
            if quote_count < 1:
                quote_count = 1
            
            # Check for color in second part
            if len(parts) > 1:
                color_arg = parts[1].lower()
                if color_arg in COLOR_MAP:
                    bg_color = COLOR_MAP[color_arg]
                elif color_arg.startswith("#"):
                    bg_color = color_arg
        
        # Check for color name only
        elif parts[0].lower() in COLOR_MAP:
            bg_color = COLOR_MAP[parts[0].lower()]
        
        # Check if it's a hex color
        elif parts[0].startswith("#"):
            bg_color = parts[0]
    
    # Send processing message
    processing = await message.reply("⏳ <b>Creating quote sticker...</b>")
    
    try:
        messages_to_quote = []
        
        if quote_count > 1:
            # Get multiple consecutive messages starting from replied message
            # Simple approach: just duplicate the single message for now
            # In groups, getting exact consecutive messages is complex without message history
            for i in range(quote_count):
                messages_to_quote.append(reply_msg)
        else:
            # Single message quote
            messages_to_quote = [reply_msg]
        
        # Format messages for API
        formatted_messages = []
        for msg in messages_to_quote:
            # Check if this message is a reply
            replied_to_msg = None
            if msg.reply_to_message:
                replied_to_msg = msg.reply_to_message
            
            formatted_msg = await quotly.format_message(msg, bot, replied_to_msg)
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
