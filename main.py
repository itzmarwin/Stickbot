import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient
from pyrogram import Client  # Add Pyrogram import

from config import BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH
from database import init_db
from handlers import start, kang, packs, misc, logger
from telethon_quotly import setup_telethon_handlers
from pyrogram_handlers.afk import setup_afk_handlers  # Direct import from handlers
from pyrogram_handlers.gban import setup_gban_handlers  # Direct import from handlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Global Pyrogram client
pyro_client = None

async def setup_pyrogram():
    """Setup and start Pyrogram client"""
    global pyro_client
    
    pyro_client = Client(
        "bot_session",
        api_id=TELEGRAM_API_ID,
        api_hash=TELEGRAM_API_HASH,
        bot_token=BOT_TOKEN
    )
    
    await pyro_client.start()
    
    # Setup all Pyrogram handlers
    await setup_afk_handlers(pyro_client)
    await setup_gban_handlers(pyro_client)
    
    logging.info("Pyrogram client started with AFK and GBan handlers")
    return pyro_client

async def stop_pyrogram():
    """Stop Pyrogram client"""
    global pyro_client
    if pyro_client:
        await pyro_client.stop()
        logging.info("Pyrogram client stopped")

async def main():
    # Initialize database
    await init_db()
    
    # Initialize Aiogram bot and dispatcher
    aiogram_bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Register Aiogram routers (EXCLUDE QUOTLY - now handled by Telethon)
    dp.include_router(start.router)
    dp.include_router(kang.router)
    dp.include_router(packs.router)
    dp.include_router(logger.router)
    dp.include_router(misc.router)
    
    # Initialize Telethon client for /q command
    telethon_client = TelegramClient(
        'quotly_bot_session',
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH
    )
    
    # Start all three clients
    logging.info("Starting Aiogram, Telethon and Pyrogram clients...")
    
    # Start Telethon client
    await telethon_client.start(bot_token=BOT_TOKEN)
    await setup_telethon_handlers(telethon_client)
    logging.info("Telethon client started for /q command")
    
    # Start Pyrogram client directly (no separate file needed)
    await setup_pyrogram()
    logging.info("Pyrogram client started for /afk and /gban commands")
    
    logging.info("Aiogram bot started for all other commands")
    
    # Run all clients
    try:
        # Start Aiogram polling
        await dp.start_polling(aiogram_bot)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Error in main: {e}")
    finally:
        # Disconnect all clients
        await telethon_client.disconnect()
        await stop_pyrogram()
        logging.info("All clients disconnected")

if __name__ == "__main__":
    asyncio.run(main())
