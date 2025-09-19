import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import settings
from database import init_database, close_database
from middlewares import DatabaseMiddleware
from handlers import start_router, kang_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Main function to initialize and run the bot"""
    
    logger.info("Starting Telegram Sticker Kang Bot...")
    
    try:
        # Initialize database
        logger.info("Connecting to database...")
        await init_database()
        
        # Initialize bot and dispatcher
        bot = Bot(token=settings.BOT_TOKEN)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        # Register middleware
        dp.message.middleware(DatabaseMiddleware())
        
        # Register routers
        dp.include_router(start_router)
        dp.include_router(kang_router)
        
        logger.info("Bot initialized successfully")
        
        # Start polling
        logger.info("Starting bot polling...")
        await dp.start_polling(bot)
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        try:
            await close_database()
            if 'bot' in locals():
                await bot.session.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    """Entry point of the application"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot terminated by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit(1)
