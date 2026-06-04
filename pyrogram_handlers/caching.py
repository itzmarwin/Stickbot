import asyncio
import logging
from datetime import datetime, timezone
from time import time
from pyrogram.enums import ParseMode
from typing import Dict, Optional, Any

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatMembersFilter
from pyrogram.errors import ChatAdminRequired, FloodWait
from pyrogram.types import Message, ChatMemberUpdated

logger = logging.getLogger(__name__)

ADMIN_CACHE: Dict[int, Dict[int, Dict[str, Any]]] = {}

_fetch_locks: Dict[int, asyncio.Lock] = {}
_bot_id: Optional[int] = None

_reload_cooldowns: Dict[int, float] = {}
RELOAD_COOLDOWN = 300


async def _get_bot_id(client: Client) -> int:
    global _bot_id
    if _bot_id is None:
        me = await client.get_me()
        _bot_id = me.id
    return _bot_id


def _get_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _fetch_locks:
        _fetch_locks[chat_id] = asyncio.Lock()
    return _fetch_locks[chat_id]


def _seconds_until_4am_utc() -> float:
    now    = datetime.now(timezone.utc)
    target = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now >= target:
        target = target.replace(day=target.day + 1)
    return (target - now).total_seconds()


def _check_reload_cooldown(chat_id: int):
    last      = _reload_cooldowns.get(chat_id, 0)
    remaining = RELOAD_COOLDOWN - (time() - last)
    if remaining > 0:
        return True, int(remaining)
    return False, 0


def _build_entry(member) -> Dict[str, Any]:
    is_owner = member.status == ChatMemberStatus.OWNER
    p        = member.privileges

    if is_owner:
        can_ban = can_restrict = can_delete_messages = True
        can_change_info = can_pin_messages = can_promote_members = can_invite_users = True
    else:
        can_ban              = bool(getattr(p, "can_restrict_members", False))
        can_restrict         = bool(getattr(p, "can_restrict_members", False))
        can_delete_messages  = bool(getattr(p, "can_delete_messages",  False))
        can_change_info      = bool(getattr(p, "can_change_info",      False))
        can_pin_messages     = bool(getattr(p, "can_pin_messages",     False))
        can_promote_members  = bool(getattr(p, "can_promote_members",  False))
        can_invite_users     = bool(getattr(p, "can_invite_users",     False))

    return {
        "user_id"            : member.user.id,
        "username"           : f"@{member.user.username}" if member.user.username else None,
        "name"               : member.user.first_name or "Unknown",
        "is_owner"           : is_owner,
        "is_admin"           : True,
        "can_ban"            : can_ban,
        "can_restrict"       : can_restrict,
        "can_delete_messages": can_delete_messages,
        "can_change_info"    : can_change_info,
        "can_pin_messages"   : can_pin_messages,
        "can_promote_members": can_promote_members,
        "can_invite_users"   : can_invite_users,
    }


async def _fetch_and_cache(client: Client, chat_id: int):
    lock = _get_lock(chat_id)

    async with lock:
        if chat_id in ADMIN_CACHE:
            return

        try:
            admin_list: Dict[int, Dict[str, Any]] = {}

            async for member in client.get_chat_members(
                chat_id, filter=ChatMembersFilter.ADMINISTRATORS
            ):
                if member.user and not member.user.is_deleted and not member.user.is_bot:
                    admin_list[member.user.id] = _build_entry(member)

            ADMIN_CACHE[chat_id] = admin_list
            logger.info(f"Admin cache loaded | chat={chat_id} | admins={len(admin_list)}")

        except ChatAdminRequired:
            logger.warning(f"Bot not admin in chat {chat_id} — cache skipped")

        except FloodWait as e:
            logger.warning(f"FloodWait {e.value}s fetching admins for {chat_id}")

        except Exception as e:
            logger.error(f"Error caching admins for chat {chat_id}: {e}")


async def _force_fetch(client: Client, chat_id: int):
    lock = _get_lock(chat_id)

    async with lock:
        try:
            admin_list: Dict[int, Dict[str, Any]] = {}

            async for member in client.get_chat_members(
                chat_id, filter=ChatMembersFilter.ADMINISTRATORS
            ):
                if member.user and not member.user.is_deleted and not member.user.is_bot:
                    admin_list[member.user.id] = _build_entry(member)

            ADMIN_CACHE[chat_id] = admin_list
            logger.info(f"Admin cache force-reloaded | chat={chat_id} | admins={len(admin_list)}")
            return True

        except ChatAdminRequired:
            logger.warning(f"Bot not admin in chat {chat_id} — reload skipped")
            return False

        except FloodWait as e:
            logger.warning(f"FloodWait {e.value}s during force reload for {chat_id}")
            return False

        except Exception as e:
            logger.error(f"Error during force reload for chat {chat_id}: {e}")
            return False


async def _scheduled_cache_clear():
    while True:
        seconds = _seconds_until_4am_utc()
        logger.info(f"Next cache clear in {int(seconds // 3600)}h {int((seconds % 3600) // 60)}m (4:00 AM UTC)")
        await asyncio.sleep(seconds)
        ADMIN_CACHE.clear()
        _reload_cooldowns.clear()
        logger.info("Admin cache cleared — 4:00 AM UTC scheduled reset")


def get_admin_permissions(chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    return ADMIN_CACHE.get(chat_id, {}).get(user_id, None)


def is_chat_cached(chat_id: int) -> bool:
    return chat_id in ADMIN_CACHE


def get_all_admins(chat_id: int) -> Dict[int, Dict[str, Any]]:
    return ADMIN_CACHE.get(chat_id, {})


def invalidate_chat(chat_id: int):
    ADMIN_CACHE.pop(chat_id, None)
    logger.info(f"Cache invalidated for chat {chat_id}")


async def is_bot_admin_cached(client: Client, chat_id: int) -> bool:
    if is_chat_cached(chat_id):
        return True
    bot_id = await _get_bot_id(client)
    try:
        member = await client.get_chat_member(chat_id, bot_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def setup_cache_handlers(client: Client):

    asyncio.create_task(_scheduled_cache_clear())

    @client.on_message(filters.group & ~filters.me, group=-2)
    async def on_group_message(client: Client, message: Message):
        chat_id = message.chat.id

        if chat_id in ADMIN_CACHE:
            return

        bot_id = await _get_bot_id(client)

        try:
            bot_member   = await client.get_chat_member(chat_id, bot_id)
            bot_is_admin = bot_member.status in (
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER
            )
        except Exception:
            return

        if not bot_is_admin:
            return

        asyncio.create_task(_fetch_and_cache(client, chat_id))


    @client.on_chat_member_updated(filters.group)
    async def on_member_updated(client: Client, update: ChatMemberUpdated):
        chat_id    = update.chat.id
        old        = update.old_chat_member
        new        = update.new_chat_member

        if not new or not new.user:
            return

        user_id    = new.user.id
        old_status = old.status if old else None
        new_status = new.status

        admin_statuses = (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
        bot_id         = await _get_bot_id(client)

        if user_id == bot_id:
            if new_status in admin_statuses:
                logger.info(f"Bot promoted in chat {chat_id} — fetching admin cache")
                if chat_id in ADMIN_CACHE:
                    del ADMIN_CACHE[chat_id]
                asyncio.create_task(_fetch_and_cache(client, chat_id))

            elif old_status in admin_statuses and new_status not in admin_statuses:
                logger.info(f"Bot demoted in chat {chat_id} — invalidating cache")
                invalidate_chat(chat_id)

            return

        if new.user.is_deleted or new.user.is_bot:
            return

        if chat_id not in ADMIN_CACHE:
            return

        if new_status in admin_statuses:
            ADMIN_CACHE[chat_id][user_id] = _build_entry(new)
            logger.info(f"Cache updated | PROMOTED | user={user_id} | chat={chat_id}")

        elif old_status in admin_statuses and new_status not in admin_statuses:
            ADMIN_CACHE[chat_id].pop(user_id, None)
            logger.info(f"Cache updated | DEMOTED | user={user_id} | chat={chat_id}")


    @client.on_message(filters.command("reload") & filters.group)
    async def reload_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if not user_id:
            return

        perms = get_admin_permissions(chat_id, user_id)
        if perms is None:
            try:
                member = await client.get_chat_member(chat_id, user_id)
                if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                    await message.reply_text("Only admins can use this command.")
                    return
            except Exception:
                await message.reply_text("Only admins can use this command.")
                return

        on_cooldown, remaining = _check_reload_cooldown(chat_id)
        if on_cooldown:
            minutes = remaining // 60
            seconds = remaining % 60
            if minutes > 0:
                time_str = f"{minutes}m {seconds}s"
            else:
                time_str = f"{seconds}s"
            await message.reply_text(
                f"Please wait <b>{time_str}</b> before reloading again.",
                parse_mode=ParseMode.HTML
            )
            return

        ADMIN_CACHE.pop(chat_id, None)
        _reload_cooldowns[chat_id] = time()

        processing = await message.reply_text("Reloading admin cache...")

        success = await _force_fetch(client, chat_id)

        if success:
            count = len(ADMIN_CACHE.get(chat_id, {}))
            await processing.edit_text(
                f"Admin cache refreshed - <b>{count} admin(s)</b> cached.",
                parse_mode=ParseMode.HTML
            )
        else:
            await processing.edit_text("Failed to reload cache. Make sure I'm an admin in this group.")
