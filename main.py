import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient

from config import BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH
from database import init_db
from telethon_quotly import setup_telethon_handlers

# Import individual routers
from handlers.start import router as start_router
from handlers.kang import router as kang_router
from handlers.packs import router as packs_router
from handlers.misc import router as misc_router
from handlers.logger import router as logger_router
from handlers.gban import router as gban_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    try:
        # Initialize database
        await init_db()
        
        # Initialize Aiogram bot and dispatcher
        bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher()
        
        # Include routers in specific order
        dp.include_router(start_router)
        dp.include_router(kang_router)
        dp.include_router(packs_router)
        dp.include_router(logger_router)
        dp.include_router(misc_router)
        dp.include_router(gban_router)  # GBan router last mein
        
        # Initialize Telethon client for /q command
        telethon_client = TelegramClient(
            'quotly_bot_session',
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH
        )
        
        # Start Telethon client
        await telethon_client.start(bot_token=BOT_TOKEN)
        await setup_telethon_handlers(telethon_client)
        
        # Get bot info
        bot_info = await bot.get_me()
        logging.info(f"✅ Bot started: @{bot_info.username}")
        
        # Log all loaded routers
        logging.info("📋 Loaded routers:")
        logging.info(f"   - Start: ✅")
        logging.info(f"   - Kang: ✅")
        logging.info(f"   - Packs: ✅")
        logging.info(f"   - Logger: ✅")
        logging.info(f"   - Misc: ✅")
        logging.info(f"   - GBan: ✅")
        logging.info(f"   - Telethon Quotly: ✅")
        
        print("\n🎉 Bot successfully started!")
        print("📝 Available commands:")
        print("   /start, /help, /kang, /packs, /ping, /stats, /gban, /ungban, /gbanlist, /q")
        
        # Run the bot
        await dp.start_polling(bot)
        
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Error in main: {e}")
    finally:
        # Disconnect all clients
        if 'telethon_client' in locals():
            await telethon_client.disconnect()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
