import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient

from config import BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH
from database import init_db
from handlers import start, kang, packs, misc, logger
from telethon_quotly import setup_telethon_handlers
from pyrogram_afk import start_pyrogram, stop_pyrogram

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

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
    
    # Start Pyrogram client for AFK
    await start_pyrogram()
    logging.info("Pyrogram client started for /afk command")
    
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
