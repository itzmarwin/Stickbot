import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from config import BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_pyrogram():
    """Test Pyrogram connection and message reception"""
    try:
        client = Client(
            "test_session",
            api_id=TELEGRAM_API_ID,
            api_hash=TELEGRAM_API_HASH,
            bot_token=BOT_TOKEN
        )
        
        @client.on_message(filters.command("test123"))
        async def test_handler(client: Client, message: Message):
            await message.reply(f"✅ Pyrogram test successful! Chat: {message.chat.type}")
            logger.info(f"Test message received in {message.chat.type} chat {message.chat.id}")
        
        await client.start()
        logger.info("Pyrogram test client started")
        
        # Keep running for testing
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_pyrogram())
