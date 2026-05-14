import re
import asyncio
import time
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode, ChatMemberStatus, MessageEntityType
from pyrogram.errors import ChatAdminRequired, FloodWait, UserAdminInvalid

import logging

logger = logging.getLogger(__name__)

MAX_MUTE_DAYS = 30
MAX_MUTE_HOURS = MAX_MUTE_DAYS * 24
COOLDOWN_SECONDS = 3

_bot_cache = None
_user_cooldowns = {}

MUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_media_messages=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_send_polls=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
)

UNMUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_media_messages=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_send_polls=True,
    can_invite_users=True,
)


async def get_bot_cached(client: Client):
    global _bot_cache
    if _bot_cache is None:
        _bot_cache = await client.get_me()
    return _bot_cache


def check_cooldown(user_id: int, chat_id: int, command: str) -> bool:
    key = f"{user_id}:{chat_id}:{command}"
    now = time.time()
    if key in _user_cooldowns and now - _user_cooldowns[key] < COOLDOWN_SECONDS:
        return True
    _user_cooldowns[key] = now
    return False


def extract_time(time_string: str) -> tuple:
    if not time_string:
        return None, None
    match = re.match(r'^(\d+)([mhd])$', time_string.lower())
    if not match:
        return None, None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 'm':
        seconds = amount * 60
        display = f"{amount} minute{'s' if amount != 1 else ''}"
    elif unit == 'h':
        if amount > MAX_MUTE_HOURS:
            return None, None
        seconds = amount * 3600
        display = f"{amount} hour{'s' if amount != 1 else ''}"
    elif unit == 'd':
        if amount > MAX_MUTE_DAYS:
            return None, None
        seconds = amount * 86400
        display = f"{amount} day{'s' if amount != 1 else ''}"
    else:
        return None, None
    return seconds, display


def extract_user_and_reason(message: Message) -> tuple:
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id if message.reply_to_message.from_user else None
        parts = message.text.split(maxsplit=1)
        return user_id, parts[1] if len(parts) > 1 else None

    if message.entities:
        for entity in message.entities:
            if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                text_after = message.text[entity.offset + entity.length:].strip()
                return entity.user.id, text_after or None

    parts = message.text.split()
    if len(parts) < 2:
        return None, None
    user_arg = parts[1]
    if user_arg.startswith('@'):
        user_id = user_arg[1:]
    elif user_arg.isdigit():
        user_id = int(user_arg)
    else:
        return None, None
    return user_id, " ".join(parts[2:]) if len(parts) > 2 else None


async def get_admin_status(client: Client, chat_id: int, user_id: int) -> tuple:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status == ChatMemberStatus.OWNER:
            return True, True
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return False, False
        return True, getattr(member.privileges, "can_restrict_members", False)
    except Exception:
        return False, False


async def resolve_user(client: Client, identifier) -> tuple:
    try:
        user = await client.get_users(identifier)
        return user.id, user, None
    except Exception:
        tag = f"@{identifier}" if isinstance(identifier, str) else str(identifier)
        return None, None, f"User {tag} not found!"


def make_mention(user_id: int, first_name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{first_name}</a>'


def unmute_button(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Unmute", callback_data=f"unmute_user={user_id}"),
        InlineKeyboardButton("Close", callback_data="mute_close")
    ]])


async def mute_with_retry(client: Client, chat_id: int, user_id: int, until_date=None):
    async def _do():
        if until_date is not None:
            await client.restrict_chat_member(chat_id, user_id, MUTE_PERMISSIONS, until_date=until_date)
        else:
            await client.restrict_chat_member(chat_id, user_id, MUTE_PERMISSIONS)
    try:
        await _do()
    except FloodWait as e:
        if e.value <= 10:
            await asyncio.sleep(e.value)
            await _do()
        else:
            raise


async def unmute_with_retry(client: Client, chat_id: int, user_id: int):
    async def _do():
        await client.restrict_chat_member(chat_id, user_id, UNMUTE_PERMISSIONS)
    try:
        await _do()
    except FloodWait as e:
        if e.value <= 10:
            await asyncio.sleep(e.value)
            await _do()
        else:
            raise


async def setup_mute_handlers(client: Client):

    @client.on_message(filters.command("mute") & filters.group)
    async def mute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "mute"):
            return

        is_admin, can_restrict = await get_admin_status(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        if message.reply_to_message and message.reply_to_message.from_user:
            target_user = message.reply_to_message.from_user
            target_user_id = target_user.id
            parts = message.text.split(maxsplit=1)
            reason = parts[1] if len(parts) > 1 else None
            bot = await get_bot_cached(client)
            if target_user_id == bot.id:
                await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
                return
            target_is_admin, _ = await get_admin_status(client, chat_id, target_user_id)
            if target_is_admin:
                await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
                return
        else:
            identifier, reason = extract_user_and_reason(message)
            if not identifier:
                await message.reply_text(
                    "Mention a user or reply to their message.\n<code>/mute @username reason</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            bot = await get_bot_cached(client)
            if isinstance(identifier, int) and identifier == bot.id:
                await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
                return
            target_user_id, target_user, error = await resolve_user(client, identifier)
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            if target_user_id == bot.id:
                await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
                return
            target_is_admin, _ = await get_admin_status(client, chat_id, target_user_id)
            if target_is_admin:
                await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
                return

        try:
            await mute_with_retry(client, chat_id, target_user_id)
            admin_mention = make_mention(admin_id, message.from_user.first_name)
            user_mention = make_mention(target_user_id, target_user.first_name)
            await message.reply_text(
                f"<b>Mute Event</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {admin_mention}\n"
                f"<b>Reason:</b> {reason or 'No reason provided'}",
                parse_mode=ParseMode.HTML,
                reply_markup=unmute_button(target_user_id)
            )
        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"mute_command: {e}", exc_info=True)
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("smute") & filters.group)
    async def smute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "smute"):
            return

        is_admin, can_restrict = await get_admin_status(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        if message.reply_to_message and message.reply_to_message.from_user:
            target_user_id = message.reply_to_message.from_user.id
            bot = await get_bot_cached(client)
            if target_user_id == bot.id:
                await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
                return
            target_is_admin, _ = await get_admin_status(client, chat_id, target_user_id)
            if target_is_admin:
                await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
                return
        else:
            identifier, _ = extract_user_and_reason(message)
            if not identifier:
                await message.reply_text(
                    "Mention a user or reply to their message.\n<code>/smute @username</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            bot = await get_bot_cached(client)
            if isinstance(identifier, int) and identifier == bot.id:
                await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
                return
            target_user_id, _, error = await resolve_user(client, identifier)
            if error or not target_user_id:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            if target_user_id == bot.id:
                await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
                return
            target_is_admin, _ = await get_admin_status(client, chat_id, target_user_id)
            if target_is_admin:
                await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
                return

        try:
            await mute_with_retry(client, chat_id, target_user_id)
            if message.reply_to_message:
                try:
                    await message.reply_to_message.delete()
                except Exception:
                    pass
            try:
                await message.delete()
            except Exception:
                pass
        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"smute_command: {e}", exc_info=True)
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("dmute") & filters.group)
    async def dmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "dmute"):
            return

        is_admin, can_restrict = await get_admin_status(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply_text(
                "Reply to a message to delete and mute the user.\n<code>/dmute</code> [reply]",
                parse_mode=ParseMode.HTML
            )
            return

        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        parts = message.text.split(maxsplit=1)
        reason = parts[1] if len(parts) > 1 else None

        bot = await get_bot_cached(client)
        if target_user_id == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        target_is_admin, _ = await get_admin_status(client, chat_id, target_user_id)
        if target_is_admin:
            await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
            return

        try:
            await mute_with_retry(client, chat_id, target_user_id)
            try:
                await message.reply_to_message.delete()
            except Exception:
                pass
            admin_mention = make_mention(admin_id, message.from_user.first_name)
            user_mention = make_mention(target_user_id, target_user.first_name)
            await message.reply_text(
                f"<b>Mute Event</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {admin_mention}\n"
                f"<b>Reason:</b> {reason or 'No reason provided'}",
                parse_mode=ParseMode.HTML,
                reply_markup=unmute_button(target_user_id)
            )
        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"dmute_command: {e}", exc_info=True)
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("tmute") & filters.group)
    async def tmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "tmute"):
            return

        is_admin, can_restrict = await get_admin_status(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        target_user = None
        target_user_id = None
        time_val = None
        reason = None

        if message.reply_to_message and message.reply_to_message.from_user:
            target_user = message.reply_to_message.from_user
            target_user_id = target_user.id
            parts = message.text.split()
            if len(parts) < 2:
                await message.reply_text(
                    "Please specify mute duration.\n<code>/tmute 1h</code> [reply]",
                    parse_mode=ParseMode.HTML
                )
                return
            time_val = parts[1]
            reason = " ".join(parts[2:]) if len(parts) > 2 else None
        else:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                        target_user_id = entity.user.id
                        text_after = message.text[entity.offset + entity.length:].strip().split()
                        if text_after:
                            time_val = text_after[0]
                            reason = " ".join(text_after[1:]) if len(text_after) > 1 else None
                        break

            if not target_user_id:
                parts = message.text.split()
                if len(parts) < 3:
                    await message.reply_text(
                        "Please specify user and duration.\n<code>/tmute @username 1h reason</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                user_arg = parts[1]
                time_val = parts[2]
                reason = " ".join(parts[3:]) if len(parts) > 3 else None
                if user_arg.startswith('@'):
                    identifier = user_arg[1:]
                elif user_arg.isdigit():
                    identifier = int(user_arg)
                else:
                    await message.reply_text("Couldn't identify the user.", parse_mode=ParseMode.HTML)
                    return
                target_user_id, target_user, error = await resolve_user(client, identifier)
                if error:
                    await message.reply_text(error, parse_mode=ParseMode.HTML)
                    return

        mute_seconds, time_display = extract_time(time_val)
        if not mute_seconds:
            await message.reply_text(
                "<b>Invalid time format.</b>\nUse: <code>30m</code>, <code>2h</code>, <code>1d</code>",
                parse_mode=ParseMode.HTML
            )
            return

        bot = await get_bot_cached(client)
        if target_user_id == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        if target_user is None:
            target_user_id, target_user, error = await resolve_user(client, target_user_id)
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return

        target_is_admin, _ = await get_admin_status(client, chat_id, target_user_id)
        if target_is_admin:
            await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
            return

        try:
            mute_until = datetime.now() + timedelta(seconds=mute_seconds)
            await mute_with_retry(client, chat_id, target_user_id, mute_until)
            admin_mention = make_mention(admin_id, message.from_user.first_name)
            user_mention = make_mention(target_user_id, target_user.first_name)
            await message.reply_text(
                f"<b>Temporary Mute</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {admin_mention}\n"
                f"<b>Duration:</b> {time_display}\n"
                f"<b>Reason:</b> {reason or 'No reason provided'}",
                parse_mode=ParseMode.HTML,
                reply_markup=unmute_button(target_user_id)
            )
        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"tmute_command: {e}", exc_info=True)
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("stmute") & filters.group)
    async def stmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "stmute"):
            return

        is_admin, can_restrict = await get_admin_status(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        target_user_id = None
        time_val = None

        if message.reply_to_message and message.reply_to_message.from_user:
            target_user_id = message.reply_to_message.from_user.id
            parts = message.text.split()
            if len(parts) < 2:
                await message.reply_text(
                    "Please specify mute duration.\n<code>/stmute 1h</code> [reply]",
                    parse_mode=ParseMode.HTML
                )
                return
            time_val = parts[1]
        else:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                        target_user_id = entity.user.id
                        text_after = message.text[entity.offset + entity.length:].strip().split()
                        if text_after:
                            time_val = text_after[0]
                        break

            if not target_user_id:
                parts = message.text.split()
                if len(parts) < 3:
                    await message.reply_text(
                        "Please specify user and duration.\n<code>/stmute @username 1h</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                user_arg = parts[1]
                time_val = parts[2]
                if user_arg.startswith('@'):
                    identifier = user_arg[1:]
                elif user_arg.isdigit():
                    identifier = int(user_arg)
                else:
                    await message.reply_text("Couldn't identify the user.", parse_mode=ParseMode.HTML)
                    return
                target_user_id, _, error = await resolve_user(client, identifier)
                if error or not target_user_id:
                    await message.reply_text(error, parse_mode=ParseMode.HTML)
                    return

        mute_seconds, _ = extract_time(time_val)
        if not mute_seconds:
            await message.reply_text(
                "<b>Invalid time format.</b>\nUse: <code>30m</code>, <code>2h</code>, <code>1d</code>",
                parse_mode=ParseMode.HTML
            )
            return

        bot = await get_bot_cached(client)
        if target_user_id == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        target_is_admin, _ = await get_admin_status(client, chat_id, target_user_id)
        if target_is_admin:
            await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
            return

        try:
            mute_until = datetime.now() + timedelta(seconds=mute_seconds)
            await mute_with_retry(client, chat_id, target_user_id, mute_until)
            if message.reply_to_message:
                try:
                    await message.reply_to_message.delete()
                except Exception:
                    pass
            try:
                await message.delete()
            except Exception:
                pass
        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"stmute_command: {e}", exc_info=True)
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("dtmute") & filters.group)
    async def dtmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "dtmute"):
            return

        is_admin, can_restrict = await get_admin_status(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply_text(
                "Reply to a message to delete and timed mute the user.\n<code>/dtmute 1h</code> [reply]",
                parse_mode=ParseMode.HTML
            )
            return

        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text(
                "Please specify mute duration.\n<code>/dtmute 1h</code> [reply]",
                parse_mode=ParseMode.HTML
            )
            return

        time_val = parts[1]
        reason = " ".join(parts[2:]) if len(parts) > 2 else None

        mute_seconds, time_display = extract_time(time_val)
        if not mute_seconds:
            await message.reply_text(
                "<b>Invalid time format.</b>\nUse: <code>30m</code>, <code>2h</code>, <code>1d</code>",
                parse_mode=ParseMode.HTML
            )
            return

        bot = await get_bot_cached(client)
        if target_user_id == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        target_is_admin, _ = await get_admin_status(client, chat_id, target_user_id)
        if target_is_admin:
            await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
            return

        try:
            mute_until = datetime.now() + timedelta(seconds=mute_seconds)
            await mute_with_retry(client, chat_id, target_user_id, mute_until)
            try:
                await message.reply_to_message.delete()
            except Exception:
                pass
            admin_mention = make_mention(admin_id, message.from_user.first_name)
            user_mention = make_mention(target_user_id, target_user.first_name)
            await message.reply_text(
                f"<b>Temporary Mute</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {admin_mention}\n"
                f"<b>Duration:</b> {time_display}\n"
                f"<b>Reason:</b> {reason or 'No reason provided'}",
                parse_mode=ParseMode.HTML,
                reply_markup=unmute_button(target_user_id)
            )
        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"dtmute_command: {e}", exc_info=True)
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("unmute") & filters.group)
    async def unmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "unmute"):
            return

        is_admin, can_restrict = await get_admin_status(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to unmute users.", parse_mode=ParseMode.HTML)
            return

        if message.reply_to_message and message.reply_to_message.from_user:
            target_user = message.reply_to_message.from_user
            target_user_id = target_user.id
        else:
            identifier, _ = extract_user_and_reason(message)
            if not identifier:
                await message.reply_text(
                    "Mention a user or reply to their message.\n<code>/unmute @username</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            bot = await get_bot_cached(client)
            if isinstance(identifier, int) and identifier == bot.id:
                await message.reply_text("I'm not muted.", parse_mode=ParseMode.HTML)
                return
            target_user_id, target_user, error = await resolve_user(client, identifier)
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return

        try:
            await unmute_with_retry(client, chat_id, target_user_id)
            admin_mention = make_mention(admin_id, message.from_user.first_name)
            user_mention = make_mention(target_user_id, target_user.first_name)
            await message.reply_text(
                f"<b>Unmute Event</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {admin_mention}",
                parse_mode=ParseMode.HTML
            )
        except ChatAdminRequired:
            await message.reply_text("I need admin rights to unmute users.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"unmute_command: {e}", exc_info=True)
            await message.reply_text(f"Failed to unmute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    @client.on_callback_query(filters.regex(r"^unmute_user="))
    async def unmute_callback(client: Client, callback: CallbackQuery):
        chat_id = callback.message.chat.id
        caller_id = callback.from_user.id

        is_admin, can_restrict = await get_admin_status(client, chat_id, caller_id)
        if not is_admin:
            await callback.answer("Only admins can unmute users!", show_alert=True)
            return
        if not can_restrict:
            await callback.answer("You need restrict permission to unmute!", show_alert=True)
            return

        target_user_id = int(callback.data.split("=")[1])

        try:
            target_user, _ = await asyncio.gather(
                client.get_users(target_user_id),
                unmute_with_retry(client, chat_id, target_user_id)
            )
            user_mention = make_mention(target_user_id, target_user.first_name)
        except ChatAdminRequired:
            await callback.answer("I need admin rights to unmute!", show_alert=True)
            return
        except Exception as e:
            logger.error(f"unmute_callback: {e}", exc_info=True)
            await callback.answer(f"Failed: {e}", show_alert=True)
            return

        caller_mention = make_mention(caller_id, callback.from_user.first_name)
        await callback.message.edit_text(
            f"<b>Unmute Event</b>\n\n"
            f"<b>User:</b> {user_mention}\n"
            f"<b>By:</b> {caller_mention}",
            parse_mode=ParseMode.HTML
        )
        await callback.answer("User unmuted!")


    @client.on_callback_query(filters.regex(r"^mute_close$"))
    async def mute_close_callback(client: Client, callback: CallbackQuery):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()
