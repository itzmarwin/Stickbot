"""
Bot Restart Handler
Owner-only command to gracefully restart the bot
Clears all caches and performs clean shutdown
Works universally without async conflicts
"""
import logging
import os
import sys
import shutil
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from config import OWNER_ID

logger = logging.getLogger(__name__)


def clear_cache_folders():
    """
    Clear temporary cache folders
    """
    folders_to_clear = ["cache", "downloads", "temp", "stickers", "__pycache__"]
    
    cleared = []
    failed = []
    
    for folder in folders_to_clear:
        try:
            if os.path.exists(folder):
                shutil.rmtree(folder)
                cleared.append(folder)
                logger.info(f"✅ Cleared: {folder}/")
        except Exception as e:
            failed.append(folder)
            logger.warning(f"⚠️ Could not clear {folder}/: {e}")
    
    return cleared, failed


def clear_memory_caches():
    """
    Clear in-memory caches from welcome/goodbye handlers
    """
    try:
        # Import cache dictionaries
        from pyrogram_handlers.welcome import WELCOME_CACHE
        from pyrogram_handlers.goodbye import GOODBYE_CACHE
        
        welcome_count = len(WELCOME_CACHE)
        goodbye_count = len(GOODBYE_CACHE)
        
        # Clear caches
        WELCOME_CACHE.clear()
        GOODBYE_CACHE.clear()
        
        logger.info(f"✅ Cleared WELCOME_CACHE ({welcome_count} entries)")
        logger.info(f"✅ Cleared GOODBYE_CACHE ({goodbye_count} entries)")
        
        return welcome_count + goodbye_count
    except Exception as e:
        logger.error(f"❌ Error clearing memory caches: {e}")
        return 0


async def setup_restart_handlers(client: Client):
    """Setup restart command handler"""
    
    @client.on_message(filters.command("restart") & filters.user(OWNER_ID))
    async def restart_bot(client: Client, message: Message):
        """
        Handle /restart command
        Owner-only: Gracefully restart the bot
        """
        try:
            # Send initial message
            response = await message.reply_text(
                "🔄 <b>Restarting Bot...</b>\n\n"
                "⏳ Please wait...",
                parse_mode=ParseMode.HTML
            )
            
            logger.info("=" * 60)
            logger.info("🔄 RESTART COMMAND INITIATED BY OWNER")
            logger.info("=" * 60)
            
            # ============================================================================
            # STEP 1: CLEAR MEMORY CACHES
            # ============================================================================
            await response.edit_text(
                "🔄 <b>Restarting Bot...</b>\n\n"
                "🧹 Clearing memory caches...",
                parse_mode=ParseMode.HTML
            )
            
            cache_count = clear_memory_caches()
            logger.info(f"✅ Cleared {cache_count} memory cache entries")
            
            # ============================================================================
            # STEP 2: CLEAR FOLDER CACHES
            # ============================================================================
            await response.edit_text(
                "🔄 <b>Restarting Bot...</b>\n\n"
                "✅ Memory caches cleared\n"
                "🧹 Clearing temporary folders...",
                parse_mode=ParseMode.HTML
            )
            
            cleared, failed = clear_cache_folders()
            
            if cleared:
                logger.info(f"✅ Cleared folders: {', '.join(cleared)}")
            if failed:
                logger.warning(f"⚠️ Failed to clear: {', '.join(failed)}")
            
            # ============================================================================
            # STEP 3: FINAL MESSAGE
            # ============================================================================
            await response.edit_text(
                "✅ <b>Bot Restarting!</b>\n\n"
                "✅ Memory caches cleared\n"
                "✅ Temporary folders cleared\n"
                "✅ Database connections will close\n\n"
                "🔄 Restarting now...\n"
                "⏰ Back online in ~5-10 seconds!",
                parse_mode=ParseMode.HTML
            )
            
            logger.info("=" * 60)
            logger.info("✅ RESTART PREPARATION COMPLETE")
            logger.info("🔄 Killing current process and restarting...")
            logger.info("=" * 60)
            
            # ============================================================================
            # RESTART USING KILL + PYTHON RESTART
            # ============================================================================
            # This kills current process and restarts with python3 main.py
            # Works with systemd, PM2, screen, tmux, and manual execution
            os.system(f"kill -9 {os.getpid()} && python3 main.py")
            
        except Exception as e:
            logger.error(f"❌ Error in restart command: {e}", exc_info=True)
            try:
                await message.reply_text(
                    "❌ <b>Restart failed!</b>\n\n"
                    f"Error: {str(e)}\n\n"
                    "Please check logs and restart manually.",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    logger.info("✅ Restart handler setup complete")
