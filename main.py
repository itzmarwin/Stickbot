import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient
from pyrogram import Client

from config import BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH, LOG_GROUP_ID

from database import init_db, close_db
from database_management import init_management_db, close_management_db

from handlers import start, kang, misc, logger
from handlers import sticker_id
from handlers import getsticker, getvidsticker
from handlers import copypack
from handlers import pack_management, publish

from telethon_quotly import setup_telethon_handlers

from pyrogram_handlers.gban import setup_gban_handlers
from pyrogram_handlers.afk import setup_afk_handlers
from pyrogram_handlers.memefi import setup_memefi_handlers
from pyrogram_handlers.tagall import setup_tagall_handlers
from pyrogram_handlers.broadcast import setup_broadcast_handlers
from pyrogram_handlers.welcome import setup_welcome_handlers
from pyrogram_handlers.goodbye import setup_goodbye_handlers
from pyrogram_handlers.restart import setup_restart_handlers
from pyrogram_handlers.extra import setup_extra_handlers
from pyrogram_handlers.ban import setup_ban_handlers

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").disabled = True
logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)

pyro_client = None
telethon_client = None
aiogram_bot = None


async def setup_pyrogram():
    global pyro_client

    try:
        pyro_client = Client(
            "bot_session",
            api_id=TELEGRAM_API_ID,
            api_hash=TELEGRAM_API_HASH,
            bot_token=BOT_TOKEN
        )

        await pyro_client.start()

        await setup_gban_handlers(pyro_client)
        await setup_broadcast_handlers(pyro_client)
        await setup_tagall_handlers(pyro_client)
        await setup_memefi_handlers(pyro_client)
        await setup_welcome_handlers(pyro_client)
        await setup_goodbye_handlers(pyro_client)
        await setup_afk_handlers(pyro_client)
        await setup_restart_handlers(pyro_client)
        await setup_extra_handlers(pyro_client)
        await setup_ban_handlers(pyro_client)

        return pyro_client

    except Exception as e:
        logging.error(f"Error starting Pyrogram client: {e}")
        raise


async def stop_pyrogram():
    global pyro_client
    if pyro_client:
        await pyro_client.stop()


async def send_startup_notification(bot: Bot):
    if not LOG_GROUP_ID or LOG_GROUP_ID == 0:
        logging.warning("⚠️ LOG_GROUP_ID not configured, skipping startup notification")
        return
    
    try:
        from datetime import datetime
        
        bot_info = await bot.get_me()
        now = datetime.now()
        timestamp = now.strftime("%d-%m-%Y %H:%M:%S")
        
        startup_msg = (
            "<b>Bot Restarted Successfully!</b>\n\n"
            f"<b>Bot:</b> @{bot_info.username}\n"
            f"<b>ID:</b> <code>{bot_info.id}</code>\n"
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
        logging.info("Initializing databases...")
        
        await init_db()
        logging.info("✅ Sticker database initialized")
        
        await init_management_db()
        logging.info("✅ Management database initialized")

        global aiogram_bot
        aiogram_bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher()

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

        global telethon_client
        telethon_client = TelegramClient(
            'quotly_bot_session',
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH
        )

        await telethon_client.start(bot_token=BOT_TOKEN)
        await setup_telethon_handlers(telethon_client)
        logging.info("✅ Telethon client started")

        await setup_pyrogram()
        logging.info("✅ Pyrogram client started")

        bot_info = await aiogram_bot.get_me()
        logging.info(f"🤖 Bot started: @{bot_info.username}")
        logging.info("=" * 60)
        logging.info("✅ ALL SYSTEMS OPERATIONAL")
        logging.info("=" * 60)

        await send_startup_notification(aiogram_bot)

        await dp.start_polling(aiogram_bot)

    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Error in main: {e}")
    finally:
        logging.info("=" * 60)
        logging.info("Shutting down gracefully...")
        logging.info("=" * 60)
        
        if telethon_client:
            logging.info("Disconnecting Telethon...")
            await telethon_client.disconnect()
        
        logging.info("Stopping Pyrogram...")
        await stop_pyrogram()
        
        if aiogram_bot:
            logging.info("Closing Aiogram session...")
            await aiogram_bot.session.close()
        
        logging.info("Closing sticker database connection...")
        await close_db()
        
        logging.info("Closing management database connection...")
        await close_management_db()
        
        logging.info("=" * 60)
        logging.info("✅ SHUTDOWN COMPLETE!")
        logging.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
