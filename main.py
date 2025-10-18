import asyncio
import logging
import signal
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient
from pyrogram import Client

from config import BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH
from database import init_db, close_db
from handlers import start, kang, misc, logger
from handlers import sticker_id
from handlers import getsticker, getvidsticker
from handlers import pack_management, publish
from telethon_quotly import setup_telethon_handlers
from pyrogram_handlers.gban import setup_gban_handlers
from pyrogram_handlers.afk import setup_afk_handlers
from pyrogram_handlers.broadcast import setup_broadcast_handlers

# ✅ FIX 1: Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')  # ✅ Log to file
    ]
)

logger = logging.getLogger(__name__)

# Global clients
pyro_client = None
telethon_client = None
aiogram_bot = None
dispatcher = None

# ✅ FIX 2: Shutdown event for graceful shutdown
shutdown_event = asyncio.Event()


async def setup_pyrogram():
    """
    ✅ Setup and start Pyrogram client with error handling
    """
    global pyro_client
    
    try:
        logger.info("Starting Pyrogram client...")
        
        pyro_client = Client(
            "bot_session",
            api_id=TELEGRAM_API_ID,
            api_hash=TELEGRAM_API_HASH,
            bot_token=BOT_TOKEN
        )
        
        await pyro_client.start()
        
        # Setup all Pyrogram handlers
        await setup_gban_handlers(pyro_client)
        await setup_broadcast_handlers(pyro_client)
        await setup_afk_handlers(pyro_client)
        
        logger.info("✅ Pyrogram client started successfully")
        return pyro_client
        
    except Exception as e:
        logger.error(f"❌ Error starting Pyrogram client: {e}", exc_info=True)
        raise


async def stop_pyrogram():
    """
    ✅ Stop Pyrogram client gracefully
    """
    global pyro_client
    if pyro_client:
        try:
            logger.info("Stopping Pyrogram client...")
            await pyro_client.stop()
            logger.info("✅ Pyrogram client stopped")
        except Exception as e:
            logger.error(f"Error stopping Pyrogram: {e}")


async def shutdown(signal_name=None):
    """
    ✅ Graceful shutdown handler
    
    Args:
        signal_name: Name of signal that triggered shutdown (if any)
    """
    if signal_name:
        logger.info(f"Received signal {signal_name}, initiating graceful shutdown...")
    else:
        logger.info("Initiating graceful shutdown...")
    
    # Set shutdown event
    shutdown_event.set()
    
    try:
        # Stop polling
        if dispatcher and aiogram_bot:
            logger.info("Stopping dispatcher...")
            await dispatcher.stop_polling()
        
        # Disconnect Telethon
        if telethon_client and telethon_client.is_connected():
            logger.info("Disconnecting Telethon client...")
            await telethon_client.disconnect()
        
        # Stop Pyrogram
        await stop_pyrogram()
        
        # Close database connections
        logger.info("Closing database connections...")
        await close_db()
        
        # Close bot session
        if aiogram_bot:
            logger.info("Closing bot session...")
            await aiogram_bot.session.close()
        
        logger.info("✅ Graceful shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


def setup_signal_handlers(loop):
    """
    ✅ Setup signal handlers for graceful shutdown
    
    Args:
        loop: Event loop
    """
    if sys.platform != 'win32':
        # Unix/Linux signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(signal.Signals(s).name))
            )
    else:
        # Windows doesn't support add_signal_handler
        # Use signal.signal for SIGINT (Ctrl+C)
        signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(shutdown("SIGINT")))


async def main():
    """
    ✅ Main function with comprehensive error handling and graceful shutdown
    """
    global aiogram_bot, dispatcher, telethon_client
    
    try:
        logger.info("=" * 50)
        logger.info("Starting Sticker Kang Bot...")
        logger.info("=" * 50)
        
        # ✅ FIX 3: Initialize database with error handling
        try:
            logger.info("Initializing database...")
            await init_db()
            logger.info("✅ Database initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}", exc_info=True)
            logger.error("Cannot proceed without database. Exiting...")
            return
        
        # ✅ FIX 4: Initialize Aiogram bot
        try:
            logger.info("Initializing Aiogram bot...")
            aiogram_bot = Bot(
                token=BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
            dispatcher = Dispatcher()
            logger.info("✅ Aiogram bot initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Aiogram: {e}", exc_info=True)
            return
        
        # ✅ FIX 5: Register routers with error handling
        try:
            logger.info("Registering routers...")
            dispatcher.include_router(start.router)
            dispatcher.include_router(kang.router)
            dispatcher.include_router(sticker_id.router)
            dispatcher.include_router(getvidsticker.router)
            dispatcher.include_router(getsticker.router)
            dispatcher.include_router(logger.router)
            dispatcher.include_router(pack_management.router)
            dispatcher.include_router(publish.router)
            dispatcher.include_router(misc.router)
            logger.info("✅ All routers registered")
        except Exception as e:
            logger.error(f"❌ Error registering routers: {e}", exc_info=True)
            return
        
        # ✅ FIX 6: Initialize Telethon client
        try:
            logger.info("Initializing Telethon client...")
            telethon_client = TelegramClient(
                'quotly_bot_session',
                TELEGRAM_API_ID,
                TELEGRAM_API_HASH
            )
            
            await telethon_client.start(bot_token=BOT_TOKEN)
            await setup_telethon_handlers(telethon_client)
            logger.info("✅ Telethon client started successfully")
        except Exception as e:
            logger.error(f"❌ Error starting Telethon: {e}", exc_info=True)
            logger.warning("Continuing without Telethon (Quotly will be unavailable)")
            telethon_client = None
        
        # ✅ FIX 7: Initialize Pyrogram client
        try:
            await setup_pyrogram()
        except Exception as e:
            logger.error(f"❌ Error starting Pyrogram: {e}", exc_info=True)
            logger.warning("Continuing without Pyrogram (GBan/Broadcast/AFK will be unavailable)")
        
        # ✅ FIX 8: Get bot info
        try:
            bot_info = await aiogram_bot.get_me()
            logger.info("=" * 50)
            logger.info(f"✅ Bot started successfully: @{bot_info.username}")
            logger.info(f"Bot ID: {bot_info.id}")
            logger.info(f"Bot Name: {bot_info.first_name}")
            logger.info("=" * 50)
        except Exception as e:
            logger.error(f"❌ Error getting bot info: {e}", exc_info=True)
        
        # ✅ FIX 9: Setup signal handlers
        loop = asyncio.get_running_loop()
        setup_signal_handlers(loop)
        
        # ✅ FIX 10: Start polling with shutdown monitoring
        logger.info("Starting polling...")
        
        # Create polling task
        polling_task = asyncio.create_task(dispatcher.start_polling(aiogram_bot))
        
        # Wait for either polling to complete or shutdown signal
        await asyncio.wait(
            [polling_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # If shutdown was triggered, stop polling
        if shutdown_event.is_set():
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                logger.info("Polling cancelled")
        
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt")
        await shutdown("KeyboardInterrupt")
        
    except Exception as e:
        logger.error(f"❌ Critical error in main: {e}", exc_info=True)
        await shutdown("Critical Error")
        
    finally:
        # ✅ FIX 11: Ensure cleanup even if shutdown wasn't called
        if not shutdown_event.is_set():
            await shutdown()
        
        logger.info("Bot stopped. Goodbye! 👋")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
