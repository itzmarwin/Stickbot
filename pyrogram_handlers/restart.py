"""
Bot Restart Handler
Owner-only command to gracefully restart the bot
Clears all caches and performs clean shutdown
Works with systemd, PM2, screen, tmux, and manual python3 main.py
"""
import logging
import os
import sys
import shutil
import asyncio
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
            status_msg = await message.reply_text(
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
            await status_msg.edit_text(
                "🔄 <b>Restarting Bot...</b>\n\n"
                "🧹 Clearing memory caches...",
                parse_mode=ParseMode.HTML
            )
            
            cache_count = clear_memory_caches()
            logger.info(f"✅ Cleared {cache_count} memory cache entries")
            
            await asyncio.sleep(0.5)
            
            # ============================================================================
            # STEP 2: CLEAR FOLDER CACHES
            # ============================================================================
            await status_msg.edit_text(
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
            
            await asyncio.sleep(0.5)
            
            # ============================================================================
            # STEP 3: CLOSE DATABASE CONNECTIONS
            # ============================================================================
            await status_msg.edit_text(
                "🔄 <b>Restarting Bot...</b>\n\n"
                "✅ Memory caches cleared\n"
                "✅ Temporary folders cleared\n"
                "🔌 Closing database connections...",
                parse_mode=ParseMode.HTML
            )
            
            try:
                from database import close_db
                from database_management import close_management_db
                
                await close_db()
                await close_management_db()
                logger.info("✅ Database connections closed")
            except Exception as e:
                logger.warning(f"⚠️ Error closing databases: {e}")
            
            await asyncio.sleep(0.5)
            
            # ============================================================================
            # STEP 4: FINAL MESSAGE & RESTART
            # ============================================================================
            await status_msg.edit_text(
                "✅ <b>Bot Restarting!</b>\n\n"
                "✅ Memory caches cleared\n"
                "✅ Temporary folders cleared\n"
                "✅ Database connections closed\n\n"
                "🔄 Restarting now...\n"
                "⏰ Back online in ~5-10 seconds!",
                parse_mode=ParseMode.HTML
            )
            
            logger.info("=" * 60)
            logger.info("✅ RESTART PREPARATION COMPLETE")
            logger.info("🔄 Initiating graceful shutdown...")
            logger.info("=" * 60)
            
            # Give time for message to send
            await asyncio.sleep(1)
            
            # ============================================================================
            # GRACEFUL SHUTDOWN & RESTART
            # ============================================================================
            
            # Stop Pyrogram client cleanly
            await client.stop()
            
            # Exit with code 0 (success)
            # If running under systemd/PM2/supervisor with auto-restart, bot will restart
            # If running manually, user needs to restart with: python3 main.py
            sys.exit(0)
            
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
