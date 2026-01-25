import re
import io
import logging
import time
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChatAdminRequired, UserNotParticipant
from cachetools import TTLCache

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024
MAX_BUTTON_TEXT_LENGTH = 64
MAX_BUTTON_URL_LENGTH = 256

MAX_BUTTONS_TOTAL = 6
MAX_BUTTONS_PER_ROW = 2

MIN_AUTO_DELETE_SECONDS = 10
MAX_AUTO_DELETE_SECONDS = 86400
DEFAULT_AUTO_DELETE_SECONDS = 600

CACHE_TTL_SECONDS = 3600
CACHE_MAX_SIZE = 1000

FLOOD_THRESHOLD = 5
FLOOD_TIME_WINDOW = 60
FLOOD_COOLDOWN = 300

TASK_CLEANUP_INTERVAL = 3600

welcome_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)
goodbye_cache = TTLCache(maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS)

delete_tasks: Dict[int, Dict[str, Any]] = {}

join_tracker: Dict[int, List[float]] = defaultdict(list)
flood_cooldown: Dict[int, float] = {}

cache_locks: Dict[int, asyncio.Lock] = defaultdict(lambda: asyncio.Lock())

BUTTON_PATTERN = re.compile(r'\[([^\]]+)\]\(([^\)]+)\)')
PIPE_SEPARATOR = re.compile(r'\|')


def parse_buttons(text: str) -> Tuple[Optional[str], Optional[List[List[Dict]]], Optional[str]]:
    if not text:
        return "", [], None
    
    cleaned_text = text
    button_rows = []
    
    lines = text.split('\n')
    total_buttons = 0
    
    for line in lines:
        if '|' in line:
            parts = PIPE_SEPARATOR.split(line)
            row_buttons = []
            
            for part in parts:
                matches = BUTTON_PATTERN.findall(part.strip())
                
                for btn_text, btn_url in matches:
                    if total_buttons >= MAX_BUTTONS_TOTAL:
                        break
                    
                    error = validate_button(btn_text, btn_url)
                    if error:
                        return None, None, error
                    
                    row_buttons.append({"text": btn_text.strip(), "url": btn_url.strip()})
                    total_buttons += 1
                
                if len(row_buttons) > MAX_BUTTONS_PER_ROW:
                    return None, None, f"Maximum {MAX_BUTTONS_PER_ROW} buttons per row allowed!"
            
            if row_buttons:
                button_rows.append(row_buttons)
        else:
            matches = BUTTON_PATTERN.findall(line)
            for btn_text, btn_url in matches:
                if total_buttons >= MAX_BUTTONS_TOTAL:
                    break
                
                error = validate_button(btn_text, btn_url)
                if error:
                    return None, None, error
                
                button_rows.append([{"text": btn_text.strip(), "url": btn_url.strip()}])
                total_buttons += 1
    
    if total_buttons > MAX_BUTTONS_TOTAL:
        return None, None, f"Maximum {MAX_BUTTONS_TOTAL} buttons allowed! You added {total_buttons}."
    
    cleaned_text = BUTTON_PATTERN.sub('', text)
    cleaned_text = PIPE_SEPARATOR.sub('', cleaned_text)
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text, button_rows, None


def validate_button(text: str, url: str) -> Optional[str]:
    if len(text) > MAX_BUTTON_TEXT_LENGTH:
        return f"Button text too long! Max {MAX_BUTTON_TEXT_LENGTH} characters. '{text[:20]}...' is {len(text)} chars."
    
    if len(text.strip()) == 0:
        return "Button text cannot be empty!"
    
    if len(url) > MAX_BUTTON_URL_LENGTH:
        return f"Button URL too long! Max {MAX_BUTTON_URL_LENGTH} characters."
    
    if not url.startswith(('http://', 'https://', 't.me/', 'tg://')):
        return f"Invalid URL: {url}. Must start with http://, https://, t.me/, or tg://"
    
    if url.lower().startswith(('javascript:', 'data:', 'file:')):
        return "Blocked: Dangerous URL protocol detected!"
    
    return None


def create_button_markup(button_rows: Optional[List[List[Dict]]]) -> Optional[InlineKeyboardMarkup]:
    if not button_rows:
        return None
    
    keyboard = []
    for row in button_rows:
        keyboard_row = []
        for btn in row:
            keyboard_row.append(InlineKeyboardButton(text=btn['text'], url=btn['url']))
        keyboard.append(keyboard_row)
    
    return InlineKeyboardMarkup(keyboard) if keyboard else None


def format_message_text(text: str, user, chat) -> str:
    first_name = user.first_name or "User"
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    username = f"@{user.username}" if user.username else "None"
    user_mention = f'<a href="tg://user?id={user.id}">{first_name}</a>'
    group_name = chat.title or "Group"
    
    now = datetime.now()
    current_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%H:%M")
    
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
    if not text:
        return None
    
    max_length = MAX_CAPTION_LENGTH if is_caption else MAX_TEXT_LENGTH
    
    if len(text) > max_length:
        text_type = "Caption" if is_caption else "Text"
        return (f"{text_type} too long! Maximum {max_length} characters allowed. "
                f"Your text is {len(text)} characters.")
    
    return None


def format_time(seconds: int) -> str:
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


async def is_user_admin(client: Client, chat_id: int, user_id: int) -> bool:
    if user_id is None:
        raise ChatAdminRequired
    
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    
    except ChatAdminRequired:
        raise
    
    except UserNotParticipant:
        return False
    
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False


async def is_bot_admin(client: Client, chat_id: int) -> bool:
    try:
        bot = await client.get_me()
        bot_member = await client.get_chat_member(chat_id, bot.id)
        return bot_member.status == ChatMemberStatus.ADMINISTRATOR
    except Exception as e:
        logger.error(f"Error checking bot admin status in chat {chat_id}: {e}")
        return False


async def bot_can_delete_messages(client: Client, chat_id: int) -> bool:
    try:
        bot = await client.get_me()
        bot_member = await client.get_chat_member(chat_id, bot.id)
        
        if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
            return False
        
        return bot_member.privileges and bot_member.privileges.can_delete_messages
    except Exception as e:
        logger.error(f"Error checking bot delete permission in chat {chat_id}: {e}")
        return False


async def get_cached_settings(chat_id: int, message_type: str) -> Optional[Dict]:
    cache = welcome_cache if message_type == 'welcome' else goodbye_cache
    
    async with cache_locks[chat_id]:
        return cache.get(chat_id)


async def update_cached_settings(chat_id: int, message_type: str, settings: Dict) -> None:
    cache = welcome_cache if message_type == 'welcome' else goodbye_cache
    
    async with cache_locks[chat_id]:
        cache[chat_id] = settings


async def clear_cached_settings(chat_id: int, message_type: str) -> None:
    cache = welcome_cache if message_type == 'welcome' else goodbye_cache
    
    async with cache_locks[chat_id]:
        cache.pop(chat_id, None)


async def delete_message_after(message: Message, seconds: int, task_id: str) -> None:
    try:
        await asyncio.sleep(seconds)
        
        try:
            await message.delete()
        except Exception as delete_error:
            logger.warning(f"Failed to delete message {message.id}: {delete_error}")
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in delete_message_after for task {task_id}: {e}")
    finally:
        if task_id in delete_tasks:
            del delete_tasks[task_id]


async def schedule_message_deletion(message: Message, seconds: int, chat_id: int, message_type: str) -> None:
    task_id = f"{message_type}_{chat_id}_{message.id}_{time.time()}"
    
    task = asyncio.create_task(delete_message_after(message, seconds, task_id))
    
    delete_tasks[task_id] = {
        'task': task,
        'message_id': message.id,
        'chat_id': chat_id,
        'type': message_type,
        'scheduled_at': datetime.now(),
        'delete_at': datetime.now() + timedelta(seconds=seconds)
    }


async def cancel_pending_deletions(chat_id: Optional[int] = None, message_type: Optional[str] = None) -> int:
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
    now = datetime.now()
    cleaned = 0
    
    for task_id in list(delete_tasks.keys()):
        task_data = delete_tasks[task_id]
        
        if task_data['task'].done():
            del delete_tasks[task_id]
            cleaned += 1
            continue
        
        if task_data['delete_at'] < now:
            task_data['task'].cancel()
            del delete_tasks[task_id]
            cleaned += 1
    
    if cleaned > 0:
        logger.info(f"🧹 Cleaned up {cleaned} expired delete tasks")


def check_join_flood(chat_id: int) -> Tuple[bool, Optional[str]]:
    current_time = time.time()
    
    if chat_id in flood_cooldown:
        cooldown_until = flood_cooldown[chat_id]
        if current_time < cooldown_until:
            remaining = int(cooldown_until - current_time)
            return True, f"⚠️ Welcome messages paused due to flood. Resumes in {format_time(remaining)}."
        else:
            del flood_cooldown[chat_id]
            join_tracker[chat_id].clear()
    
    join_tracker[chat_id].append(current_time)
    
    join_tracker[chat_id] = [
        t for t in join_tracker[chat_id]
        if current_time - t <= FLOOD_TIME_WINDOW
    ]
    
    if len(join_tracker[chat_id]) >= FLOOD_THRESHOLD:
        flood_cooldown[chat_id] = current_time + FLOOD_COOLDOWN
        logger.warning(f"🚨 Join flood detected in chat {chat_id}. Cooldown activated.")
        return True, f"⚠️ Too many joins detected! Welcome messages paused for {format_time(FLOOD_COOLDOWN)}."
    
    return False, None


def reset_flood_tracking(chat_id: int) -> None:
    if chat_id in join_tracker:
        join_tracker[chat_id].clear()
    if chat_id in flood_cooldown:
        del flood_cooldown[chat_id]


def validate_auto_delete_time(seconds: int) -> Optional[str]:
    if seconds < MIN_AUTO_DELETE_SECONDS:
        return f"Auto-delete time cannot be less than {MIN_AUTO_DELETE_SECONDS} seconds."
    
    if seconds > MAX_AUTO_DELETE_SECONDS:
        max_hours = MAX_AUTO_DELETE_SECONDS // 3600
        return f"Maximum auto-delete time is {max_hours} hours ({MAX_AUTO_DELETE_SECONDS} seconds)."
    
    return None


def get_default_auto_delete_time() -> int:
    return DEFAULT_AUTO_DELETE_SECONDS


def log_error(operation: str, error: Exception, **context) -> None:
    context_str = ", ".join(f"{k}={v}" for k, v in context.items())
    logger.error(f"❌ {operation} failed | {context_str} | Error: {error}", exc_info=True)


def get_utils_stats() -> Dict[str, Any]:
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
