from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

@router.message(Command("stickerid"))
async def cmd_stickerid(message: Message):
    """Handle /stickerid command - get sticker file ID"""
    
    # Check if replying to a message
    if not message.reply_to_message:
        await message.reply("❌ **Please reply to a sticker message to get its ID.**")
        return
    
    replied_msg = message.reply_to_message
    
    # Check if replied message contains a sticker
    if not replied_msg.sticker:
        await message.reply("❌ **The replied message is not a sticker.**")
        return
    
    sticker = replied_msg.sticker
    sticker_id = sticker.file_id
    
    # Prepare response with exact format as requested
    response = f"""**Sticker ID:** `{sticker_id}`
**Emoji:** {sticker.emoji or 'None'}"""
    
    await message.reply(response)

# REMOVED the automatic sticker response handler to prevent unwanted replies
