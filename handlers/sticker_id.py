from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
import logging

from templates import (
    STICKER_ID_RESPONSE,
    STICKER_ID_NO_REPLY,
    STICKER_ID_NOT_STICKER,
    ERROR_OCCURRED
)

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("stickerid"))
async def cmd_stickerid(message: Message):
    """Handle /stickerid command - get sticker file ID"""
    try:
        # Check if replying to a message
        if not message.reply_to_message:
            await message.reply(STICKER_ID_NO_REPLY)
            return
        
        replied_msg = message.reply_to_message
        
        # Check if replied message contains a sticker
        if not replied_msg.sticker:
            await message.reply(STICKER_ID_NOT_STICKER)
            return
        
        sticker = replied_msg.sticker
        sticker_id = sticker.file_id
        emoji = sticker.emoji or 'None'
        
        # Prepare response using template
        response = STICKER_ID_RESPONSE.format(
            sticker_id=sticker_id,
            emoji=emoji
        )
        
        await message.reply(response)
        
    except Exception as e:
        logger.error(f"Error in stickerid command: {e}")
        # Send the generic error message from templates
        await message.reply(ERROR_OCCURRED)
