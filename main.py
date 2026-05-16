import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient
from pyrogram import Client
from pymongo import AsyncMongoClient

from config import BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH, LOG_GROUP_ID, MONGO_URI, DATABASE_NAME

from mongo.userdb import init_userdb, create_indexes as create_user_indexes
from mongo.stickerdb import init_stickerdb, create_indexes as create_sticker_indexes
from mongo.managementdb import init_managementdb, create_indexes as create_management_indexes
from mongo.locksdb import init_locksdb, create_indexes as create_locks_indexes

from handlers import start, kang, misc, logger
from handlers import sticker_id
from handlers import getsticker, getvidsticker
from handlers import copypack
from handlers import pack_management
from handlers import language

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
from pyrogram_handlers.filters import setup_filter_handlers
from pyrogram_handlers.warns import setup_warn_handlers
from pyrogram_handlers.mute import setup_mute_handlers
from pyrogram_handlers.locks import setup_locks_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logging.getLogger("aiogram").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").disabled = True
logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

pyro_client = None
telethon_client = None
aiogram_bot = None
mongo_client = None


async def init_databases():
    global mongo_client

    mongo_client = AsyncMongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
        maxPoolSize=100,
        minPoolSize=10,
        waitQueueTimeoutMS=10000,
        retryWrites=True,
        retryReads=True,
        maxIdleTimeMS=45000
    )

    await mongo_client.admin.command('ping')
    db = mongo_client[DATABASE_NAME]

    init_userdb(mongo_client, db)
    init_stickerdb(mongo_client, db)
    init_managementdb(mongo_client, db)
    init_locksdb(mongo_client, db)

    await create_user_indexes()
    await create_sticker_indexes()
    await create_management_indexes()
    await create_locks_indexes()

    logging.info("✅ Database initialized successfully")
    logging.info(f"✅ Connected to: {DATABASE_NAME}")


async def close_databases():
    global mongo_client
    if mongo_client:
        logging.info("Closing MongoDB connection...")
        mongo_client.close()
        logging.info("✅ MongoDB connection closed")


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
        await setup_ban_handlers(pyro_client)
        await setup_warn_handlers(pyro_client)
        await setup_mute_handlers(pyro_client)
        await setup_locks_handlers(pyro_client)
        await setup_filter_handlers(pyro_client)
        await setup_afk_handlers(pyro_client)
        await setup_restart_handlers(pyro_client)
        await setup_extra_handlers(pyro_client)

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
        logging.info("Initializing database...")
        await init_databases()

        global aiogram_bot
        aiogram_bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher()

        dp.include_router(language.router)
        dp.include_router(start.router)
        dp.include_router(kang.router)
        dp.include_router(sticker_id.router)
        dp.include_router(getvidsticker.router)
        dp.include_router(getsticker.router)
        dp.include_router(logger.router)
        dp.include_router(pack_management.router)
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

        await close_databases()

        logging.info("=" * 60)
        logging.info("✅ SHUTDOWN COMPLETE!")
        logging.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
