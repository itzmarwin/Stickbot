from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from utils import extract_sticker_from_message
import logging

logger = logging.getLogger(__name__)

# Create router for stickerid command
stickerid_router = Router()


@stickerid_router.message(Command("stickerid"))
async def stickerid_command(message: Message):
    """
    Handle /stickerid command - reply to any sticker to get its file ID
    Works in both private chats and groups
    """
    
    # Check if replying to a sticker
    sticker = extract_sticker_from_message(message)
    if not sticker:
        await message.answer(
            "📋 Please reply to a sticker with /stickerid to get its file ID",
            reply_to_message_id=message.message_id
        )
        return
    
    try:
        # Prepare sticker info
        sticker_type = "🎬 Video" if sticker.is_video else "✨ Animated" if sticker.is_animated else "🖼 Static"
        emoji = sticker.emoji or "❓"
        
        # Format response with sticker details
        response = (
            f"📋 **Sticker Information**\n\n"
            f"🆔 **File ID**: `{sticker.file_id}`\n"
            f"🔗 **Unique ID**: `{sticker.file_unique_id}`\n"
            f"📁 **Type**: {sticker_type}\n"
            f"😀 **Emoji**: {emoji}\n"
            f"📏 **Size**: {sticker.width}×{sticker.height}px"
        )
        
        if sticker.file_size:
            response += f"\n💾 **File Size**: {sticker.file_size} bytes"
        
        await message.answer(
            response,
            reply_to_message_id=message.message_id,
            parse_mode="Markdown"
        )
        
        logger.info(f"Provided sticker ID for user {message.from_user.id}, sticker: {sticker.file_id}")
        
    except Exception as e:
        logger.error(f"Error in stickerid command for user {message.from_user.id}: {e}")
        await message.answer(
            "❌ Failed to get sticker information. Please try again.",
            reply_to_message_id=message.message_id
)
