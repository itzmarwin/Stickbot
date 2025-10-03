import time
import psutil
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from database import get_total_users_count, get_total_packs_count
from config import is_owner

router = Router()

# Store bot start time
bot_start_time = time.time()

@router.message(Command("ping"))
async def cmd_ping(message: Message):
    """Handle /ping command - show bot status and system info (owner only)"""
    # Check if user is owner
    if not is_owner(message.from_user.id):
        return
    
    # Calculate response time
    start_time = time.time()
    
    # Get system stats
    ram_percent = psutil.virtual_memory().percent
    cpu_percent = psutil.cpu_percent(interval=0.1)
    disk_percent = psutil.disk_usage('/').percent
    
    # Calculate uptime
    uptime_seconds = time.time() - bot_start_time
    uptime_delta = timedelta(seconds=int(uptime_seconds))
    
    # Format uptime as: 1d 3h:42m:18s
    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        uptime_str = f"{days}d {hours}h:{minutes:02d}m:{seconds:02d}s"
    else:
        uptime_str = f"{hours}h:{minutes:02d}m:{seconds:02d}s"
    
    # Send initial message
    sent_msg = await message.answer("🏓 Pinging...")
    
    # Calculate ping time
    end_time = time.time()
    ping_ms = (end_time - start_time) * 1000
    
    # Format response
    response = f"""<code>&lt; Pong : {ping_ms:.3f} ms &gt;</code>

<b>=== Sticker Kang Bot Status ===</b>
<code>:: Uptime :: {uptime_str}
:: RAM    :: {ram_percent:5.1f}%
:: CPU    :: {cpu_percent:5.1f}%
:: Disk   :: {disk_percent:5.1f}%
===============================</code>"""
    
    # Edit message with stats
    await sent_msg.edit_text(response)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Handle /stats command - show bot statistics (owner only)"""
    if not is_owner(message.from_user.id):
        return
    
    total_users = await get_total_users_count()
    total_packs = await get_total_packs_count()
    
    # Calculate uptime
    uptime_seconds = time.time() - bot_start_time
    uptime_delta = timedelta(seconds=int(uptime_seconds))
    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        uptime_str = f"{days}d {hours}h:{minutes:02d}m:{seconds:02d}s"
    else:
        uptime_str = f"{hours}h:{minutes:02d}m:{seconds:02d}s"
    
    stats_msg = f"""
<b>📊 Bot Statistics</b>

<b>Total Users:</b> {total_users}
<b>Total Packs:</b> {total_packs}
<b>Uptime:</b> {uptime_str}
"""
    
    await message.answer(stats_msg)

@router.message(F.text)
async def handle_text_messages(message: Message):
    """Handle any unhandled text messages"""
    # This catches any text that doesn't match other handlers
    pass
