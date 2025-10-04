import os
import base64
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile

from utils.quotly_api import QuotlyAPI

logger = logging.getLogger(__name__)
router = Router()

# Default dark theme
DEFAULT_BG = "#1b1429"

# Available background colors
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

async def get_reply_chain(bot: Bot, chat_id: int, message_id: int) -> tuple:
    """
    Manually fetch reply chain since aiogram has limitations
    Returns: (current_message, replied_to_message)
    """
    try:
        # Get current message
        current_msg = await bot.get_message(chat_id, message_id)
        
        # Check if current message is a reply
        if current_msg.reply_to_message:
            replied_to_id = current_msg.reply_to_message.message_id
            replied_to_msg = await bot.get_message(chat_id, replied_to_id)
            return current_msg, replied_to_msg
        
        return current_msg, None
    except Exception as e:
        logger.error(f"Error fetching reply chain: {e}")
        return None, None

@router.message(Command("q", "quote"))
async def cmd_quote(message: Message, bot: Bot):
    """Handle /q command - create quote sticker using lyo.su API"""
    
    # Check if replying to a message
    if not message.reply_to_message:
        await message.reply(
            "⚠️ <b>Please reply to a message to quote it!</b>\n\n"
            "Usage:\n"
            "• <code>/q</code> - Quote message\n"
            "• <code>/q r</code> - Quote with reply context\n"
            "• <code>/q blue</code> - Colored quote"
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
    cmd_text = message.text or ""
    args = cmd_text.split(maxsplit=1)[1] if len(cmd_text.split()) > 1 else ""
    
    bg_color = DEFAULT_BG
    include_reply = False
    
    # Parse arguments
    if args:
        parts = args.lower().split()
        
        # Check for 'r' or 'reply' flag
        if 'r' in parts or 'reply' in parts:
            include_reply = True
            # Remove 'r' or 'reply' from parts for color parsing
            parts = [p for p in parts if p not in ['r', 'reply']]
        
        # Check for color
        if parts:
            color_arg = parts[0]
            if color_arg in COLOR_MAP:
                bg_color = COLOR_MAP[color_arg]
            elif color_arg.startswith("#") and len(color_arg) == 7:
                bg_color = color_arg
    
    # Send processing message
    processing = await message.reply("⏳ <b>Creating quote sticker...</b>")
    
    try:
        # Get reply context if needed - FIXED WITH MANUAL FETCH
        replied_to_msg = None
        
        if include_reply:
            # Manually fetch the reply chain
            current_msg, original_reply_msg = await get_reply_chain(
                bot, message.chat.id, reply_msg.message_id
            )
            
            if original_reply_msg:
                replied_to_msg = original_reply_msg
                logger.info(f"Found reply chain: {original_reply_msg.text[:50] if original_reply_msg.text else 'media message'}")
            else:
                await processing.edit_text(
                    "⚠️ <b>Could not find reply chain!</b>\n\n"
                    "Make sure:\n"
                    "• The message you're quoting is actually a reply\n"
                    "• I have access to the original message\n"
                    "• The messages are in the same chat"
                )
                return
        
        # Format message for API
        formatted_msg = await quotly.format_message(reply_msg, bot, replied_to_msg)
        
        if not formatted_msg:
            raise Exception("Failed to format message for API")
        
        # Create quote using API
        sticker_data = await quotly.create_quote(
            messages=[formatted_msg],
            bg_color=bg_color
        )
        
        if not sticker_data:
            raise Exception("API failed to generate sticker")
        
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
        logger.error(f"Error creating quote: {e}", exc_info=True)
        error_msg = str(e)
        if "API" in error_msg:
            error_msg = "Quote service is temporarily unavailable. Please try again later."
        
        await processing.edit_text(
            f"❌ <b>Failed to create quote sticker!</b>\n\n"
            f"<code>{error_msg}</code>"
        )
