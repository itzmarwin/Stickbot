import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient
from pyrogram import Client

from config import BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH
from database import init_db
from handlers import start, kang, packs, misc, logger
from handlers import sticker_id  # Add this line
from telethon_quotly import setup_telethon_handlers
from pyrogram_handlers.gban import setup_gban_handlers
from pyrogram_handlers.afk import setup_afk_handlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Global clients
pyro_client = None
telethon_client = None
aiogram_bot = None

async def setup_pyrogram():
    """Setup and start Pyrogram client"""
    global pyro_client
    
    try:
        pyro_client = Client(
            "bot_session",
            api_id=TELEGRAM_API_ID,
            api_hash=TELEGRAM_API_HASH,
            bot_token=BOT_TOKEN
        )
        
        await pyro_client.start()
        
        # Setup all Pyrogram handlers
        await setup_gban_handlers(pyro_client)
        await setup_afk_handlers(pyro_client)
        
        return pyro_client
        
    except Exception as e:
        logging.error(f"Error starting Pyrogram client: {e}")
        raise

async def stop_pyrogram():
    """Stop Pyrogram client"""
    global pyro_client
    if pyro_client:
        await pyro_client.stop()

async def main():
    try:
        # Initialize database
        await init_db()
        
        # Initialize Aiogram bot and dispatcher
        global aiogram_bot
        aiogram_bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher()
        
        # Register Aiogram routers
        dp.include_router(start.router)
        dp.include_router(kang.router)
        dp.include_router(packs.router)
        dp.include_router(logger.router)
        dp.include_router(misc.router)
        dp.include_router(sticker_id.router)
        
        # Initialize Telethon client for /q command
        global telethon_client
        telethon_client = TelegramClient(
            'quotly_bot_session',
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH
        )
        
        # Start Telethon client
        await telethon_client.start(bot_token=BOT_TOKEN)
        await setup_telethon_handlers(telethon_client)
        
        # Start Pyrogram client
        await setup_pyrogram()
        
        # Get bot info
        bot_info = await aiogram_bot.get_me()
        logging.info(f"Bot started: @{bot_info.username}")
        
        # Run all clients
        await dp.start_polling(aiogram_bot)
        
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Error in main: {e}")
    finally:
        # Disconnect all clients
        if telethon_client:
            await telethon_client.disconnect()
        await stop_pyrogram()
        if aiogram_bot:
            await aiogram_bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
