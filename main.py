import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient
from pyrogram import Client

from config import BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH, LOG_GROUP_ID

# ============================================================================
# STICKER DATABASE (Existing)
# ============================================================================
from database import init_db, close_db

# ============================================================================
# MANAGEMENT DATABASE (New)
# ============================================================================
from database_management import init_management_db, close_management_db

# ============================================================================
# AIOGRAM HANDLERS (Sticker Features)
# ============================================================================
from handlers import start, kang, misc, logger
from handlers import sticker_id
from handlers import getsticker, getvidsticker
from handlers import copypack
from handlers import pack_management, publish

# ============================================================================
# TELETHON HANDLERS (Quotly)
# ============================================================================
from telethon_quotly import setup_telethon_handlers

# ============================================================================
# PYROGRAM HANDLERS (Group Management + Other Features)
# ============================================================================
from pyrogram_handlers.gban import setup_gban_handlers
from pyrogram_handlers.afk import setup_afk_handlers
from pyrogram_handlers.memefi import setup_memefi_handlers
from pyrogram_handlers.tagall import setup_tagall_handlers
from pyrogram_handlers.broadcast import setup_broadcast_handlers

# ✅ Welcome/Goodbye Handlers
from pyrogram_handlers.welcome import setup_welcome_handlers
from pyrogram_handlers.goodbye import setup_goodbye_handlers

# ✅ NEW: Restart Handler
from pyrogram_handlers.restart import setup_restart_handlers

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# 🚫 Disable aiogram spam logs
logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").disabled = True
logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)

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
        await setup_broadcast_handlers(pyro_client)
        await setup_tagall_handlers(pyro_client)
        await setup_memefi_handlers(pyro_client)
        await setup_welcome_handlers(pyro_client)
        await setup_goodbye_handlers(pyro_client)
        await setup_afk_handlers(pyro_client)
        await setup_restart_handlers(pyro_client)  # ✅ NEW

        return pyro_client

    except Exception as e:
        logging.error(f"Error starting Pyrogram client: {e}")
        raise


async def stop_pyrogram():
    """Stop Pyrogram client"""
    global pyro_client
    if pyro_client:
        await pyro_client.stop()


async def send_startup_notification(bot: Bot):
    """
    Send startup notification to logger group
    """
    if not LOG_GROUP_ID or LOG_GROUP_ID == 0:
        logging.warning("⚠️ LOG_GROUP_ID not configured, skipping startup notification")
        return
    
    try:
        from datetime import datetime
        
        # Get bot info
        bot_info = await bot.get_me()
        
        # Current time
        now = datetime.now()
        timestamp = now.strftime("%d-%m-%Y %H:%M:%S")
        
        # Startup message
        startup_msg = (
            "✅ <b>Bot Restarted Successfully!</b>\n\n"
            f"🤖 <b>Bot:</b> @{bot_info.username}\n"
            f"🆔 <b>ID:</b> <code>{bot_info.id}</code>\n"
            f"⏰ <b>Time:</b> {timestamp}\n\n"
            "🔥 <b>Status:</b> All systems operational\n"
            "📡 <b>Connection:</b> Stable\n"
            "💾 <b>Databases:</b> Connected\n"
            "🧹 <b>Cache:</b> Cleared\n\n"
            "🎯 Bot is ready to serve!"
        )
        
        await bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=startup_msg,
            parse_mode=ParseMode.HTML
        )
        
        logging.info(f"✅ Startup notification sent to LOG_GROUP_ID: {LOG_GROUP_ID}")
        
    except Exception as e:
        logging.error(f"❌ Failed to send startup notification: {e}")


async def main():
    try:
        # ============================================================================
        # INITIALIZE DATABASES
        # ============================================================================
        logging.info("Initializing databases...")
        
        # ✅ Initialize Sticker Database (Existing)
        await init_db()
        logging.info("✅ Sticker database initialized")
        
        # ✅ Initialize Management Database (New)
        await init_management_db()
        logging.info("✅ Management database initialized")

        # ============================================================================
        # INITIALIZE AIOGRAM BOT
        # ============================================================================
        global aiogram_bot
        aiogram_bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher()

        # Register Aiogram routers (Sticker features)
        dp.include_router(start.router)
        dp.include_router(kang.router)
        dp.include_router(sticker_id.router)
        dp.include_router(getvidsticker.router)
        dp.include_router(getsticker.router)
        dp.include_router(logger.router)
        dp.include_router(pack_management.router)
        dp.include_router(publish.router)
        dp.include_router(copypack.router)
        dp.include_router(misc.router)

        # ============================================================================
        # INITIALIZE TELETHON CLIENT (Quotly)
        # ============================================================================
        global telethon_client
        telethon_client = TelegramClient(
            'quotly_bot_session',
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH
        )

        # Start Telethon client
        await telethon_client.start(bot_token=BOT_TOKEN)
        await setup_telethon_handlers(telethon_client)
        logging.info("✅ Telethon client started")

        # ============================================================================
        # INITIALIZE PYROGRAM CLIENT (Group Management)
        # ============================================================================
        await setup_pyrogram()
        logging.info("✅ Pyrogram client started")

        # Get bot info
        bot_info = await aiogram_bot.get_me()
        logging.info(f"🤖 Bot started: @{bot_info.username}")
        logging.info("=" * 60)
        logging.info("✅ ALL SYSTEMS OPERATIONAL")
        logging.info("=" * 60)

        # ============================================================================
        # ✅ SEND STARTUP NOTIFICATION TO LOGGER GROUP
        # ============================================================================
        await send_startup_notification(aiogram_bot)

        # Run all clients
        await dp.start_polling(aiogram_bot)

    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Error in main: {e}")
    finally:
        # ============================================================================
        # GRACEFUL SHUTDOWN
        # ============================================================================
        logging.info("=" * 60)
        logging.info("Shutting down gracefully...")
        logging.info("=" * 60)
        
        # Disconnect Telethon
        if telethon_client:
            logging.info("Disconnecting Telethon...")
            await telethon_client.disconnect()
        
        # Stop Pyrogram
        logging.info("Stopping Pyrogram...")
        await stop_pyrogram()
        
        # Close Aiogram bot session
        if aiogram_bot:
            logging.info("Closing Aiogram session...")
            await aiogram_bot.session.close()
        
        # ✅ Close Sticker Database
        logging.info("Closing sticker database connection...")
        await close_db()
        
        # ✅ Close Management Database
        logging.info("Closing management database connection...")
        await close_management_db()
        
        logging.info("=" * 60)
        logging.info("✅ SHUTDOWN COMPLETE!")
        logging.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
