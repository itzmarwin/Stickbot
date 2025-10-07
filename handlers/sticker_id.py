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
    
    # Prepare response with sticker information
    response = f"""
📄 **Sticker Information**

**🆔 Sticker ID:** `{sticker_id}`
**📦 Emoji:** {sticker.emoji or 'None'}
**✨ Type:** {'Video Sticker' if sticker.is_video else 'Static Sticker'}
**📏 Set Name:** {sticker.set_name or 'Not part of a pack'}
"""
    
    await message.reply(response)

# Optional: Also handle when someone sends a sticker directly (not as reply to command)
@router.message(F.sticker)
async def handle_sticker_direct(message: Message):
    """Handle when someone sends a sticker (optional feature)"""
    
    sticker = message.sticker
    sticker_id = sticker.file_id
    
    response = f"""
📄 **Sticker Detected**

**🆔 Sticker ID:** `{sticker_id}`
**📦 Emoji:** {sticker.emoji or 'None'}
**✨ Type:** {'Video Sticker' if sticker.is_video else 'Static Sticker'}

💡 *Tip: Use /stickerid as a reply to any sticker to get its ID anytime!*
"""
    
    await message.reply(response)
