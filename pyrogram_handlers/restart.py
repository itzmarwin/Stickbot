import os
import sys
import shutil
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from config import OWNER_ID


def clear_cache_folders():
    folders_to_clear = ["cache", "downloads", "temp", "stickers", "__pycache__"]

    cleared = []
    failed = []

    for folder in folders_to_clear:
        try:
            if os.path.exists(folder):
                shutil.rmtree(folder)
                cleared.append(folder)
        except Exception:
            failed.append(folder)

    return cleared, failed


def clear_memory_caches():
    try:
        from pyrogram_handlers.welcome import WELCOME_CACHE
        from pyrogram_handlers.goodbye import GOODBYE_CACHE

        welcome_count = len(WELCOME_CACHE)
        goodbye_count = len(GOODBYE_CACHE)

        WELCOME_CACHE.clear()
        GOODBYE_CACHE.clear()

        return welcome_count + goodbye_count
    except Exception:
        return 0


async def setup_restart_handlers(client: Client):

    @client.on_message(filters.command("restart") & filters.user(OWNER_ID))
    async def restart_bot(client: Client, message: Message):
        response = await message.reply_text(
            "🔄 <b>Restarting Bot...</b>\n\n"
            "⏳ Please wait...",
            parse_mode=ParseMode.HTML
        )

        await response.edit_text(
            "🔄 <b>Restarting Bot...</b>\n\n"
            "🧹 Clearing memory caches...",
            parse_mode=ParseMode.HTML
        )

        clear_memory_caches()

        await response.edit_text(
            "🔄 <b>Restarting Bot...</b>\n\n"
            "✅ Memory caches cleared\n"
            "🧹 Clearing temporary folders...",
            parse_mode=ParseMode.HTML
        )

        clear_cache_folders()

        await response.edit_text(
            "✅ <b>Bot Restarting!</b>\n\n"
            "✅ Memory caches cleared\n"
            "✅ Temporary folders cleared\n"
            "✅ Database connections will close\n\n"
            "🔄 Restarting now...\n"
            "⏰ Back online in ~5-10 seconds!",
            parse_mode=ParseMode.HTML
        )

        os.system(f"kill -9 {os.getpid()} && python3 main.py")
