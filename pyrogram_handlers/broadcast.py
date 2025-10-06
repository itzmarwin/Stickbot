import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from config import is_owner
from database import get_served_chats

logger = logging.getLogger(__name__)

async def setup_broadcast_handlers(client: Client):
    """Setup broadcast command handler for testing"""
    
    @client.on_message(filters.command("broadcast_test"))
    async def broadcast_test(client: Client, message: Message):
        """Simple broadcast test command"""
        if not is_owner(message.from_user.id):
            return
        
        # Get all served chats
        served_chats = await get_served_chats()
        total_chats = len(served_chats)
        
        # Send test message to current chat
        test_msg = await message.reply(
            f"📊 **Broadcast Test**\n\n"
            f"✅ Pyrogram is working!\n"
            f"📝 This is a test message\n"
            f"👥 Total groups: {total_chats}\n"
            f"💬 Chat type: {message.chat.type}\n"
            f"🆔 Chat ID: {message.chat.id}"
        )
        
        logger.info(f"Broadcast test executed in {message.chat.type} chat {message.chat.id}")

    @client.on_message(filters.command("echo"))
    async def echo_test(client: Client, message: Message):
        """Echo command to test message reception"""
        if not is_owner(message.from_user.id):
            return
        
        if len(message.command) > 1:
            text = " ".join(message.command[1:])
            await message.reply(f"🔊 Echo: {text}")
        else:
            await message.reply("❌ Usage: `/echo <message>`")

    logger.info("Broadcast test handlers setup complete")
