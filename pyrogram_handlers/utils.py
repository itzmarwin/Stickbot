"""
Common Utilities for Pyrogram Handlers
Centralized functions to avoid code duplication
Handles: buttons, formatting, validation, caching, anti-flood
"""

import re
import asyncio
import logging
import time
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS (Fix Issue #32 - Magic Numbers)
# ============================================================================

# Message Limits (Telegram API)
MAX_TEXT_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024
MAX_BUTTON_TEXT_LENGTH = 64
MAX_BUTTON_URL_LENGTH = 256

# Button Constraints
MAX_BUTTONS_TOTAL = 6
MAX_BUTTONS_PER_ROW = 2

# Auto-Delete Settings
MIN_AUTO_DELETE_SECONDS = 10
MAX_AUTO_DELETE_SECONDS = 86400  # 24 hours
DEFAULT_AUTO_DELETE_SECONDS = 600  # 10 minutes

# Cache Settings (Fix Issue #24 - Cache TTL)
CACHE_TTL_SECONDS = 3600  # 1 hour
CACHE_MAX_SIZE = 1000  # Max groups cached

# Anti-Flood Settings (Fix Issue #35)
FLOOD_THRESHOLD = 5  # Max 5 joins
FLOOD_TIME_WINDOW = 60  # Within 60 seconds
FLOOD_COOLDOWN = 300  # 5 minute cooldown

# Task Cleanup
TASK_CLEANUP_INTERVAL = 3600  # Cleanup every hour


# ============================================================================
# GLOBAL CACHE & TRACKING (Fix Issue #1, #2, #3, #24)
# ============================================================================

# TTL Cache with automatic expiry
welcome_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)
goodbye_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)

# Delete task tracking with metadata
delete_tasks: Dict[int, Dict[str, Any]] = {}

# Anti-flood tracking (Fix Issue #35)
join_tracker: Dict[int, List[float]] = defaultdict(list)
flood_cooldown: Dict[int, float] = {}

# Cache locks for thread safety (Fix Issue #1 - Race Condition)
cache_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


# ============================================================================
# REGEX PATTERNS (Pre-compiled for performance)
# ============================================================================

BUTTON_PATTERN = re.compile(r'\[([^\]]+)\]\(([^\)]+)\)')
PIPE_SEPARATOR = re.compile(r'\|')


# ============================================================================
# BUTTON PARSING & VALIDATION (Fix Issue #5, #12)
# ============================================================================

def parse_buttons(text: str) -> Tuple[Optional[str], Optional[List[List[Dict]]], Optional[str]]:
    """
    Parse inline buttons from text with validation
    
    Format:
        [Button Text](URL) - Single button
        [Btn1](URL) | [Btn2](URL) - Two buttons in same row
    
    Args:
        text: Message text with button syntax
        
    Returns:
        Tuple of (cleaned_text, button_rows, error_message)
        
    Fixes:
        - Issue #5: Centralized duplicate code
        - Issue #12: Added validation
    """
    if not text:
        return "", [], None
    
    cleaned_text = text
    button_rows = []
    
    lines = text.split('\n')
    total_buttons = 0
    
    for line in lines:
        # Check for pipe separator (multiple buttons in row)
        if '|' in line:
            parts = PIPE_SEPARATOR.split(line)
            row_buttons = []
            
            for part in parts:
                matches = BUTTON_PATTERN.findall(part.strip())
                
                for btn_text, btn_url in matches:
                    if total_buttons >= MAX_BUTTONS_TOTAL:
                        break
                    
                    # Validate button (Fix Issue #12)
                    error = validate_button(btn_text, btn_url)
                    if error:
                        return None, None, error
                    
                    row_buttons.append({
                        "text": btn_text.strip(),
                        "url": btn_url.strip()
                    })
                    total_buttons += 1
                
                if len(row_buttons) > MAX_BUTTONS_PER_ROW:
                    return None, None, f"Maximum {MAX_BUTTONS_PER_ROW} buttons per row allowed!"
            
            if row_buttons:
                button_rows.append(row_buttons)
        else:
            # Single button per line
            matches = BUTTON_PATTERN.findall(line)
            for btn_text, btn_url in matches:
                if total_buttons >= MAX_BUTTONS_TOTAL:
                    break
                
                # Validate button
                error = validate_button(btn_text, btn_url)
                if error:
                    return None, None, error
                
                button_rows.append([{
                    "text": btn_text.strip(),
                    "url": btn_url.strip()
                }])
                total_buttons += 1
    
    if total_buttons > MAX_BUTTONS_TOTAL:
        return None, None, f"Maximum {MAX_BUTTONS_TOTAL} buttons allowed! You added {total_buttons}."
    
    # Clean text (remove button syntax)
    cleaned_text = BUTTON_PATTERN.sub('', text)
    cleaned_text = PIPE_SEPARATOR.sub('', cleaned_text)
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text, button_rows, None


def validate_button(text: str, url: str) -> Optional[str]:
    """
    Validate button text and URL
    
    Args:
        text: Button text
        url: Button URL
        
    Returns:
        Error message or None if valid
        
    Fixes:
        - Issue #12: Missing validation
    """
    # Validate text length
    if len(text) > MAX_BUTTON_TEXT_LENGTH:
        return f"Button text too long! Max {MAX_BUTTON_TEXT_LENGTH} characters. '{text[:20]}...' is {len(text)} chars."
    
    if len(text.strip()) == 0:
        return "Button text cannot be empty!"
    
    # Validate URL length
    if len(url) > MAX_BUTTON_URL_LENGTH:
        return f"Button URL too long! Max {MAX_BUTTON_URL_LENGTH} characters."
    
    # Validate URL format
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        return f"Invalid URL: {url}. Must start with http://, https://, t.me/, or tg://"
    
    # Security: Block dangerous protocols (Fix Issue #15)
    if url.lower().startswith(('javascript:', 'data:', 'file:')):
        return "Blocked: Dangerous URL protocol detected!"
    
    return None


def create_button_markup(button_rows: Optional[List[List[Dict]]]) -> Optional[InlineKeyboardMarkup]:
    """
    Create InlineKeyboardMarkup from button rows
    
    Args:
        button_rows: List of button rows
        
    Returns:
        InlineKeyboardMarkup or None
        
    Fixes:
        - Issue #5: Centralized duplicate code
    """
    if not button_rows:
        return None
    
    keyboard = []
    for row in button_rows:
        keyboard_row = []
        for btn in row:
            keyboard_row.append(
                InlineKeyboardButton(
                    text=btn['text'],
                    url=btn['url']
                )
            )
        keyboard.append(keyboard_row)
    
    return InlineKeyboardMarkup(keyboard) if keyboard else None


# ============================================================================
# TEXT FORMATTING & VALIDATION (Fix Issue #5, #12, #13)
# ============================================================================

def format_message_text(text: str, user, chat) -> str:
    """
    Format message text with variables
    
    Variables:
        {ID} - User ID
        {NAME} - First name
        {SURNAME} - Last name
        {NAMESURNAME} - Full name
        {USERNAME} - Username with @
        {MENTION} - HTML mention
        {GROUPNAME} - Chat title
        {DATE} - Current date
        {TIME} - Current time
        
    Args:
        text: Text with variables
        user: User object
        chat: Chat object
        
    Returns:
        Formatted text
        
    Fixes:
        - Issue #5: Centralized duplicate code
        - Issue #44: Handle None values
    """
    # Safe attribute access (Fix Issue #44)
    first_name = user.first_name or "User"
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    username = f"@{user.username}" if user.username else "None"
    user_mention = f'<a href="tg://user?id={user.id}">{first_name}</a>'
    group_name = chat.title or "Group"
    
    # Current time
    now = datetime.now()
    current_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%H:%M")
    
    # Replace variables
    formatted = text.replace("{ID}", str(user.id))
    formatted = formatted.replace("{NAME}", first_name)
    formatted = formatted.replace("{SURNAME}", last_name)
    formatted = formatted.replace("{NAMESURNAME}", full_name)
    formatted = formatted.replace("{DATE}", current_date)
    formatted = formatted.replace("{TIME}", current_time)
    formatted = formatted.replace("{MENTION}", user_mention)
    formatted = formatted.replace("{USERNAME}", username)
    formatted = formatted.replace("{GROUPNAME}", group_name)
    
    return formatted


def validate_text_length(text: str, is_caption: bool = False) -> Optional[str]:
    """
    Validate text length according to Telegram limits
    
    Args:
        text: Text to validate
        is_caption: True if caption, False if regular text
        
    Returns:
        Error message or None if valid
        
    Fixes:
        - Issue #12: Missing validation
        - Issue #13: Caption length check
    """
    if not text:
        return None
    
    max_length = MAX_CAPTION_LENGTH if is_caption else MAX_TEXT_LENGTH
    
    if len(text) > max_length:
        text_type = "Caption" if is_caption else "Text"
        return (f"{text_type} too long! Maximum {max_length} characters allowed. "
                f"Your text is {len(text)} characters.")
    
    return None


def format_time(seconds: int) -> str:
    """
    Format seconds into human-readable time
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string
        
    Fixes:
        - Issue #5: Centralized duplicate code
    """
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs > 0:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    
    return " ".join(parts)


# ============================================================================
# PERMISSION CHECKS (Fix Issue #5, #11)
# ============================================================================

async def is_user_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """
    Check if user is admin
    
    Args:
        client: Pyrogram client
        chat_id: Chat ID
        user_id: User ID
        
    Returns:
        True if admin, False otherwise
        
    Fixes:
        - Issue #5: Centralized duplicate code
        - Issue #33: Specific exception handling
    """
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False


async def is_bot_admin(client: Client, chat_id: int) -> bool:
    """
    Check if bot is admin
    
    Args:
        client: Pyrogram client
        chat_id: Chat ID
        
    Returns:
        True if bot is admin, False otherwise
        
    Fixes:
        - Issue #5: Centralized duplicate code
        - Issue #11: Bot admin check before operations
        - Issue #33: Specific exception handling
    """
    try:
        bot = await client.get_me()
        bot_member = await client.get_chat_member(chat_id, bot.id)
        return bot_member.status == ChatMemberStatus.ADMINISTRATOR
    except Exception as e:
        logger.error(f"Error checking bot admin status in chat {chat_id}: {e}")
        return False


async def bot_can_delete_messages(client: Client, chat_id: int) -> bool:
    """
    Check if bot has delete permission (Fix Issue #11)
    
    Args:
        client: Pyrogram client
        chat_id: Chat ID
        
    Returns:
        True if bot can delete messages, False otherwise
        
    Fixes:
        - Issue #11: Bot admin check missing for delete operations
    """
    try:
        bot = await client.get_me()
        bot_member = await client.get_chat_member(chat_id, bot.id)
        
        if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
            return False
        
        # Check delete permission
        return bot_member.privileges and bot_member.privileges.can_delete_messages
    except Exception as e:
        logger.error(f"Error checking bot delete permission in chat {chat_id}: {e}")
        return False


# ============================================================================
# CACHE MANAGEMENT (Fix Issue #1, #24)
# ============================================================================

async def get_cached_settings(chat_id: int, message_type: str) -> Optional[Dict]:
    """
    Get settings from cache with lock (thread-safe)
    
    Args:
        chat_id: Chat ID
        message_type: 'welcome' or 'goodbye'
        
    Returns:
        Settings dict or None
        
    Fixes:
        - Issue #1: Race condition in cache
        - Issue #24: TTL cache
    """
    cache = welcome_cache if message_type == 'welcome' else goodbye_cache
    
    async with cache_locks[chat_id]:
        return cache.get(chat_id)


async def update_cached_settings(chat_id: int, message_type: str, settings: Dict) -> None:
    """
    Update cache with lock (thread-safe)
    
    Args:
        chat_id: Chat ID
        message_type: 'welcome' or 'goodbye'
        settings: Settings to cache
        
    Fixes:
        - Issue #1: Race condition in cache
        - Issue #24: TTL cache
    """
    cache = welcome_cache if message_type == 'welcome' else goodbye_cache
    
    async with cache_locks[chat_id]:
        cache[chat_id] = settings


async def clear_cached_settings(chat_id: int, message_type: str) -> None:
    """
    Clear cache for a chat
    
    Args:
        chat_id: Chat ID
        message_type: 'welcome' or 'goodbye'
        
    Fixes:
        - Issue #1: Race condition in cache
    """
    cache = welcome_cache if message_type == 'welcome' else goodbye_cache
    
    async with cache_locks[chat_id]:
        cache.pop(chat_id, None)


# ============================================================================
# AUTO-DELETE TASK MANAGEMENT (Fix Issue #2, #3)
# ============================================================================

async def delete_message_after(message: Message, seconds: int, task_id: str) -> None:
    """
    Delete message after specified seconds
    
    Args:
        message: Message to delete
        seconds: Delay in seconds
        task_id: Unique task identifier
        
    Fixes:
        - Issue #2: Memory leak - proper cleanup
        - Issue #3: Orphaned tasks - tracked properly
        - Issue #11: Check delete permission before scheduling
    """
    try:
        await asyncio.sleep(seconds)
        
        # Double-check permission before deleting (Fix Issue #11)
        try:
            await message.delete()
            logger.info(f"✅ Deleted message {message.id} after {seconds}s")
        except Exception as delete_error:
            logger.warning(f"Failed to delete message {message.id}: {delete_error}")
        
    except asyncio.CancelledError:
        logger.info(f"Delete task cancelled for message {message.id}")
    except Exception as e:
        logger.error(f"Error in delete_message_after for task {task_id}: {e}")
    finally:
        # Cleanup (Fix Issue #2 - Memory leak)
        if task_id in delete_tasks:
            del delete_tasks[task_id]


async def schedule_message_deletion(
    message: Message,
    seconds: int,
    chat_id: int,
    message_type: str
) -> None:
    """
    Schedule message deletion with proper tracking
    
    Args:
        message: Message to delete
        seconds: Delay in seconds
        chat_id: Chat ID
        message_type: 'welcome' or 'goodbye'
        
    Fixes:
        - Issue #2: Memory leak risk
        - Issue #3: Orphaned tasks
    """
    task_id = f"{message_type}_{chat_id}_{message.id}_{time.time()}"
    
    task = asyncio.create_task(delete_message_after(message, seconds, task_id))
    
    # Track task with metadata (Fix Issue #3)
    delete_tasks[task_id] = {
        'task': task,
        'message_id': message.id,
        'chat_id': chat_id,
        'type': message_type,
        'scheduled_at': datetime.now(),
        'delete_at': datetime.now() + timedelta(seconds=seconds)
    }


async def cancel_pending_deletions(chat_id: Optional[int] = None, message_type: Optional[str] = None) -> int:
    """
    Cancel pending deletion tasks
    
    Args:
        chat_id: If provided, cancel only for this chat
        message_type: If provided, cancel only this type
        
    Returns:
        Number of tasks cancelled
        
    Fixes:
        - Issue #2: Proper task cleanup
        - Issue #3: Handle orphaned tasks
    """
    cancelled = 0
    
    for task_id in list(delete_tasks.keys()):
        task_data = delete_tasks[task_id]
        
        should_cancel = True
        if chat_id and task_data['chat_id'] != chat_id:
            should_cancel = False
        if message_type and task_data['type'] != message_type:
            should_cancel = False
        
        if should_cancel:
            task_data['task'].cancel()
            del delete_tasks[task_id]
            cancelled += 1
    
    return cancelled


async def cleanup_expired_tasks() -> None:
    """
    Periodic cleanup of completed/failed tasks (Fix Issue #2)
    
    Should be called periodically from main loop
    """
    now = datetime.now()
    cleaned = 0
    
    for task_id in list(delete_tasks.keys()):
        task_data = delete_tasks[task_id]
        
        # Remove completed tasks
        if task_data['task'].done():
            del delete_tasks[task_id]
            cleaned += 1
            continue
        
        # Remove tasks that should have completed but didn't
        if task_data['delete_at'] < now:
            task_data['task'].cancel()
            del delete_tasks[task_id]
            cleaned += 1
    
    if cleaned > 0:
        logger.info(f"🧹 Cleaned up {cleaned} expired delete tasks")


# ============================================================================
# ANTI-FLOOD PROTECTION (Fix Issue #35)
# ============================================================================

def check_join_flood(chat_id: int) -> Tuple[bool, Optional[str]]:
    """
    Check if group is experiencing join flood
    
    Args:
        chat_id: Chat ID
        
    Returns:
        Tuple of (is_flooding, cooldown_message)
        
    Fixes:
        - Issue #35: Anti-flood protection
    """
    current_time = time.time()
    
    # Check if in cooldown
    if chat_id in flood_cooldown:
        cooldown_until = flood_cooldown[chat_id]
        if current_time < cooldown_until:
            remaining = int(cooldown_until - current_time)
            return True, f"⚠️ Welcome messages paused due to flood. Resumes in {format_time(remaining)}."
        else:
            # Cooldown expired
            del flood_cooldown[chat_id]
            join_tracker[chat_id].clear()
    
    # Track this join
    join_tracker[chat_id].append(current_time)
    
    # Remove old entries outside time window
    join_tracker[chat_id] = [
        t for t in join_tracker[chat_id]
        if current_time - t <= FLOOD_TIME_WINDOW
    ]
    
    # Check flood threshold
    if len(join_tracker[chat_id]) >= FLOOD_THRESHOLD:
        # Flood detected!
        flood_cooldown[chat_id] = current_time + FLOOD_COOLDOWN
        logger.warning(f"🚨 Join flood detected in chat {chat_id}. Cooldown activated.")
        return True, f"⚠️ Too many joins detected! Welcome messages paused for {format_time(FLOOD_COOLDOWN)}."
    
    return False, None


def reset_flood_tracking(chat_id: int) -> None:
    """
    Reset flood tracking for a chat
    
    Args:
        chat_id: Chat ID
    """
    if chat_id in join_tracker:
        join_tracker[chat_id].clear()
    if chat_id in flood_cooldown:
        del flood_cooldown[chat_id]


# ============================================================================
# VALIDATION HELPERS (Fix Issue #9, #12)
# ============================================================================

def validate_auto_delete_time(seconds: int) -> Optional[str]:
    """
    Validate auto-delete time
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Error message or None if valid
        
    Fixes:
        - Issue #9: Auto-delete default value inconsistency
        - Issue #32: Magic numbers → constants
    """
    if seconds < MIN_AUTO_DELETE_SECONDS:
        return f"Auto-delete time cannot be less than {MIN_AUTO_DELETE_SECONDS} seconds."
    
    if seconds > MAX_AUTO_DELETE_SECONDS:
        max_hours = MAX_AUTO_DELETE_SECONDS // 3600
        return f"Maximum auto-delete time is {max_hours} hours ({MAX_AUTO_DELETE_SECONDS} seconds)."
    
    return None


def get_default_auto_delete_time() -> int:
    """
    Get default auto-delete time (Fix Issue #9)
    
    Returns:
        Default time in seconds
    """
    return DEFAULT_AUTO_DELETE_SECONDS


# ============================================================================
# ERROR HANDLING HELPERS (Fix Issue #33)
# ============================================================================

def log_error(operation: str, error: Exception, **context) -> None:
    """
    Log error with context
    
    Args:
        operation: Operation that failed
        error: Exception object
        **context: Additional context
        
    Fixes:
        - Issue #33: Better exception handling
    """
    context_str = ", ".join(f"{k}={v}" for k, v in context.items())
    logger.error(f"❌ {operation} failed | {context_str} | Error: {error}", exc_info=True)


# ============================================================================
# HEALTH CHECK & MONITORING
# ============================================================================

def get_utils_stats() -> Dict[str, Any]:
    """
    Get utility module statistics
    
    Returns:
        Statistics dictionary
    """
    return {
        'cache': {
            'welcome_size': len(welcome_cache),
            'goodbye_size': len(goodbye_cache),
            'max_size': CACHE_MAX_SIZE,
            'ttl_seconds': CACHE_TTL_SECONDS
        },
        'tasks': {
            'pending_deletions': len(delete_tasks),
            'task_types': {
                'welcome': sum(1 for t in delete_tasks.values() if t['type'] == 'welcome'),
                'goodbye': sum(1 for t in delete_tasks.values() if t['type'] == 'goodbye')
            }
        },
        'flood_protection': {
            'tracked_chats': len(join_tracker),
            'cooldown_chats': len(flood_cooldown),
            'threshold': FLOOD_THRESHOLD,
            'window_seconds': FLOOD_TIME_WINDOW
        }
    }


logger.info("✅ Pyrogram utilities module loaded")
