import asyncio
import logging
from datetime import datetime
from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import Command

from config import is_owner, LOG_GROUP_ID
from database import get_served_chats, add_banned_user, delete_user_packs

logger = logging.getLogger(__name__)
router = Router()

@router.message(Command("gban"))
async def gban_command(message: Message, bot: Bot):
    """Simple GBan command for testing"""
    logging.info(f"GBan command received from user: {message.from_user.id}")
    
    if not is_owner(message.from_user.id):
        await message.reply("❌ This command is only for bot owners.")
        return
    
    # Check if user is replying to a message
    if not message.reply_to_message:
        await message.reply("❌ Please reply to a user's message to gban them.")
        return
    
    target_user = message.reply_to_message.from_user
    if not target_user:
        await message.reply("❌ Could not get user info.")
        return
    
    if target_user.id == message.from_user.id:
        return await message.reply("❌ You cannot gban yourself!")
    elif target_user.id == bot.id:
        return await message.reply("❌ I cannot gban myself!")
    elif is_owner(target_user.id):
        return await message.reply("❌ Cannot gban another owner!")
    
    # Send initial message
    processing_msg = await message.reply("🔄 Starting GBan process...")
    
    try:
        # Get served chats
        served_chats = []
        chats = await get_served_chats()
        for chat in chats:
            served_chats.append(int(chat["chat_id"]))
        
        await processing_msg.edit_text(f"🔄 GBanning user from {len(served_chats)} chats...")
        
        # Delete user's sticker packs
        packs_deleted = await delete_user_packs(target_user.id)
        
        # Ban from groups (in background)
        asyncio.create_task(
            ban_user_from_chats(bot, target_user, served_chats, processing_msg, packs_deleted)
        )
        
    except Exception as e:
        logger.error(f"Error in GBan: {e}")
        await processing_msg.edit_text(f"❌ Error: {e}")

async def ban_user_from_chats(bot: Bot, target_user, served_chats, processing_msg, packs_deleted):
    """Ban user from all chats in background"""
    try:
        banned_chats = 0
        failed_chats = 0
        
        for chat_id in served_chats:
            try:
                await bot.ban_chat_member(chat_id, target_user.id)
                banned_chats += 1
                
                # Update progress every 5 chats
                if banned_chats % 5 == 0:
                    await processing_msg.edit_text(
                        f"🔄 Progress: {banned_chats}/{len(served_chats)} chats..."
                    )
                
                await asyncio.sleep(0.5)  # Avoid flood
                
            except Exception as e:
                logger.error(f"Failed to ban from {chat_id}: {e}")
                failed_chats += 1
                continue
        
        # Add to banned users database
        await add_banned_user(target_user.id)
        
        # Send completion message
        success_msg = f"""
✅ **GBan Complete**

**User:** {target_user.first_name} (`{target_user.id}`)
**Packs Deleted:** {packs_deleted}
**Chats Banned From:** {banned_chats}
**Failed:** {failed_chats}
"""
        await processing_msg.edit_text(success_msg)
        
    except Exception as e:
        logger.error(f"Error in background ban: {e}")
        await processing_msg.edit_text(f"❌ Background error: {e}")

@router.message(Command("test_gban"))
async def test_gban(message: Message):
    """Test command to check if GBan router is working"""
    logging.info("Test GBan command received")
    await message.reply("✅ GBan router is working! Bot can receive GBan commands.")

@router.message(Command("debug_gban"))
async def debug_gban(message: Message):
    """Debug GBan system"""
    if not is_owner(message.from_user.id):
        return
    
    from database import get_served_chats_count
    chat_count = await get_served_chats_count()
    
    debug_info = f"""
🔧 **GBan Debug Info**

✅ GBan router is loaded
✅ Database accessible
📊 Served chats: {chat_count}
👤 Your ID: {message.from_user.id}
🤖 Bot ID: {message.bot.id}
"""
    await message.answer(debug_info)
