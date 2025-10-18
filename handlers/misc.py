import time
import psutil
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from database import (
    get_total_users_count, 
    get_total_packs_count, 
    get_served_chats_count,
    check_database_health,  # ✅ NEW: From database.py fix
    get_cache_stats          # ✅ NEW: From database.py fix
)
from config import is_admin
from rate_limiter import get_rate_limiter_stats  # ✅ NEW: From rate_limiter.py fix

router = Router()

# Store bot start time
bot_start_time = time.time()


def format_uptime(seconds: float) -> str:
    """
    ✅ Format uptime in human-readable format
    
    Args:
        seconds: Uptime in seconds
        
    Returns:
        Formatted string (e.g., "2d 5h:23m:45s")
    """
    uptime_delta = timedelta(seconds=int(seconds))
    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        return f"{days}d {hours}h:{minutes:02d}m:{seconds:02d}s"
    else:
        return f"{hours}h:{minutes:02d}m:{seconds:02d}s"


@router.message(Command("ping"))
async def cmd_ping(message: Message):
    """
    ✅ Handle /ping command - show bot status and system info (admin only)
    """
    # Check if user is admin
    if not is_admin(message.from_user.id):
        return
    
    # Calculate response time
    start_time = time.time()
    
    # Get system stats
    ram_percent = psutil.virtual_memory().percent
    cpu_percent = psutil.cpu_percent(interval=0.1)
    disk_percent = psutil.disk_usage('/').percent
    
    # Calculate uptime
    uptime_seconds = time.time() - bot_start_time
    uptime_str = format_uptime(uptime_seconds)
    
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
    """
    ✅ Handle /stats command - show bot statistics with health check (admin only)
    
    Includes:
    - User/Pack/Group counts
    - Database health
    - Redis cache statistics
    - Rate limiter statistics
    - System uptime
    """
    if not is_admin(message.from_user.id):
        return
    
    # Send loading message
    loading_msg = await message.answer("📊 Gathering statistics...")
    
    try:
        # ✅ FIX 1: Get database health
        db_health = await check_database_health()
        
        # ✅ FIX 2: Get cache statistics
        cache_stats = await get_cache_stats()
        
        # ✅ FIX 3: Get rate limiter statistics
        rate_limiter_stats = get_rate_limiter_stats()
        
        # Get basic counts
        total_users = await get_total_users_count()
        total_packs = await get_total_packs_count()
        total_groups = await get_served_chats_count()
        
        # Calculate uptime
        uptime_seconds = time.time() - bot_start_time
        uptime_str = format_uptime(uptime_seconds)
        
        # ✅ FIX 4: Get system stats
        ram_percent = psutil.virtual_memory().percent
        ram_used_gb = psutil.virtual_memory().used / (1024**3)
        ram_total_gb = psutil.virtual_memory().total / (1024**3)
        
        cpu_percent = psutil.cpu_percent(interval=0.5)
        disk_percent = psutil.disk_usage('/').percent
        
        # ✅ FIX 5: Format comprehensive stats message
        stats_msg = f"""<b>📊 Bot Statistics</b>

<b>👥 Users & Groups</b>
├─ Total Users: {total_users:,}
├─ Total Packs: {total_packs:,}
└─ Total Groups: {total_groups:,}

<b>🗄️ Database Health</b>
├─ MongoDB: {db_health['mongodb']['status'].title()}
│   └─ Latency: {db_health['mongodb'].get('latency_ms', 'N/A')} ms
└─ Redis: {db_health['redis']['status'].title()}
    └─ Latency: {db_health['redis'].get('latency_ms', 'N/A')} ms

<b>💾 Cache Statistics</b>
├─ Memory: {cache_stats.get('used_memory_mb', 0):.1f}/{cache_stats.get('max_memory_mb', 0):.0f} MB
├─ Usage: {cache_stats.get('memory_usage_percent', 0):.1f}%
├─ Total Keys: {cache_stats.get('total_keys', 0):,}
├─ Hit Rate: {cache_stats.get('hit_rate', 0):.1f}%
└─ Evicted: {cache_stats.get('evicted_keys', 0):,}

<b>⏱️ Rate Limiter</b>
├─ Active Users: {rate_limiter_stats['total_users']:,}
├─ Max Capacity: {rate_limiter_stats['max_entries']:,}
├─ Usage: {rate_limiter_stats['usage_percent']:.1f}%
└─ Memory: ~{rate_limiter_stats['memory_usage_mb']:.2f} MB

<b>💻 System Resources</b>
├─ RAM: {ram_used_gb:.1f}/{ram_total_gb:.1f} GB ({ram_percent:.1f}%)
├─ CPU: {cpu_percent:.1f}%
├─ Disk: {disk_percent:.1f}%
└─ Uptime: {uptime_str}

<i>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"""
        
        # Edit message with stats
        await loading_msg.edit_text(stats_msg)
        
    except Exception as e:
        # ✅ FIX 6: Error handling
        error_msg = f"""<b>❌ Error Gathering Statistics</b>

{str(e)}

<i>Please check logs for details.</i>"""
        
        await loading_msg.edit_text(error_msg)


@router.message(F.text)
async def handle_text_messages(message: Message):
    """
    Handle any unhandled text messages
    
    This catches any text that doesn't match other handlers
    Prevents unnecessary logging of every message
    """
    # Silently ignore unhandled text messages
    pass
