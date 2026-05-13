import re
import asyncio
import time
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode, ChatMemberStatus, MessageEntityType
from pyrogram.errors import ChatAdminRequired, FloodWait, UserAdminInvalid, UserNotParticipant

import logging

logger = logging.getLogger(__name__)

MAX_MUTE_DAYS = 30
MAX_MUTE_HOURS = MAX_MUTE_DAYS * 24

_bot_cache = None
_user_cooldowns = {}

COOLDOWN_SECONDS = 3


async def get_bot_cached(client: Client):
    global _bot_cache
    if _bot_cache is None:
        _bot_cache = await client.get_me()
    return _bot_cache


def check_cooldown(user_id: int, chat_id: int, command: str) -> bool:
    key = f"{user_id}:{chat_id}:{command}"
    current_time = time.time()
    if key in _user_cooldowns:
        if current_time - _user_cooldowns[key] < COOLDOWN_SECONDS:
            return True
    _user_cooldowns[key] = current_time
    return False


def extract_time(time_string: str) -> tuple:
    """
    Time string parse karo aur seconds + display string return karo.
    Supported formats: 30m, 2h, 1d
    """
    if not time_string:
        return None, None

    pattern = r'^(\d+)([mhd])$'
    match = re.match(pattern, time_string.lower())
    if not match:
        return None, None

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == 'm':
        if amount < 1:
            return None, None
        seconds = amount * 60
        time_display = f"{amount} minute{'s' if amount != 1 else ''}"
    elif unit == 'h':
        if amount > MAX_MUTE_HOURS:
            return None, None
        seconds = amount * 3600
        time_display = f"{amount} hour{'s' if amount != 1 else ''}"
    elif unit == 'd':
        if amount > MAX_MUTE_DAYS:
            return None, None
        seconds = amount * 86400
        time_display = f"{amount} day{'s' if amount != 1 else ''}"
    else:
        return None, None

    return seconds, time_display


def extract_user_and_reason(message: Message) -> tuple:
    """
    Message se user_id aur reason extract karo.
    Reply ya mention ya username/id se kaam karta hai.
    """
    user_id = None
    reason = None

    if message.reply_to_message:
        if message.reply_to_message.from_user:
            user_id = message.reply_to_message.from_user.id
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) > 1:
            reason = command_parts[1]
    else:
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                    user_id = entity.user.id
                    text_after = message.text[entity.offset + entity.length:].strip()
                    reason = text_after if text_after else None
                    return user_id, reason

        command_parts = message.text.split()
        if len(command_parts) < 2:
            return None, None
        user_arg = command_parts[1]
        if user_arg.startswith('@'):
            user_id = user_arg[1:]
        elif user_arg.isdigit():
            user_id = int(user_arg)
        else:
            return None, None
        if len(command_parts) > 2:
            reason = " ".join(command_parts[2:])

    return user_id, reason


async def check_admin_with_permission(client: Client, chat_id: int, user_id: int) -> tuple:
    """
    User admin hai ya nahi + restrict permission hai ya nahi check karo.
    Returns: (is_admin, can_restrict)
    """
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status == ChatMemberStatus.OWNER:
            return True, True
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return False, False
        can_restrict = getattr(member.privileges, "can_restrict_members", False)
        return True, can_restrict
    except Exception as e:
        logger.error(f"Error checking admin permission: {e}")
        return False, False


async def resolve_user(client: Client, user_identifier) -> tuple:
    """
    user_identifier se actual user object fetch karo.
    Returns: (user_id, user_object, error_message)
    """
    if isinstance(user_identifier, int):
        try:
            user = await client.get_users(user_identifier)
            return user.id, user, None
        except Exception:
            return None, None, "User not found!"
    if isinstance(user_identifier, str):
        try:
            user = await client.get_users(user_identifier)
            return user.id, user, None
        except Exception:
            return None, None, f"User @{user_identifier} not found!"
    return None, None, "Invalid user!"


def make_mention(user_id: int, first_name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{first_name}</a>'


async def mute_with_retry(client: Client, chat_id: int, user_id: int, until_date=None):
    """
    User ko mute karo — FloodWait handle karta hai.
    until_date None hone par permanent mute — until_date pass hi nahi karte.
    """
    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_send_polls=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False,
    )

    async def _do_restrict():
        if until_date is not None:
            await client.restrict_chat_member(chat_id, user_id, permissions, until_date=until_date)
        else:
            await client.restrict_chat_member(chat_id, user_id, permissions)

    try:
        await _do_restrict()
    except FloodWait as e:
        if e.value <= 10:
            await asyncio.sleep(e.value)
            await _do_restrict()
        else:
            raise


async def unmute_with_retry(client: Client, chat_id: int, user_id: int):
    """
    User ko unmute karo — sari permissions restore karta hai.
    """
    try:
        await client.restrict_chat_member(
            chat_id,
            user_id,
            ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_send_polls=True,
                can_invite_users=True,
            )
        )
    except FloodWait as e:
        if e.value <= 10:
            await asyncio.sleep(e.value)
            await client.restrict_chat_member(
                chat_id,
                user_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_send_polls=True,
                    can_invite_users=True,
                )
            )
        else:
            raise


def unmute_button(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Unmute 🔊", callback_data=f"unmute_user={user_id}")
    ]])


async def setup_mute_handlers(client: Client):

    # ══════════════════════════════════════════════════════
    # /mute — Permanent mute
    # Usage: /mute @user reason  |  reply + /mute reason
    # ══════════════════════════════════════════════════════
    @client.on_message(filters.command("mute") & filters.group)
    async def mute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "mute"):
            return

        is_admin, can_restrict = await check_admin_with_permission(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        target_identifier, reason = extract_user_and_reason(message)
        if not target_identifier:
            await message.reply_text(
                "Mention a user or reply to their message.\n"
                "<code>/mute @username reason</code>",
                parse_mode=ParseMode.HTML
            )
            return

        bot = await get_bot_cached(client)
        if isinstance(target_identifier, int) and target_identifier == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return
        if target_user_id == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        target_is_admin, _ = await check_admin_with_permission(client, chat_id, target_user_id)
        if target_is_admin:
            await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
            return

        try:
            await mute_with_retry(client, chat_id, target_user_id)

            admin_mention = make_mention(admin_id, message.from_user.first_name)
            user_mention = make_mention(target_user_id, target_user.first_name)

            text = (
                f"<b>Mute Event</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {admin_mention}\n"
                f"<b>Reason:</b> {reason if reason else 'No reason provided'}"
            )

            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=unmute_button(target_user_id)
            )

        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user — they might be an admin.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Mute error: {e}")
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    # ══════════════════════════════════════════════════════
    # /smute — Silent permanent mute
    # Command + replied message dono delete ho jaate hain
    # ══════════════════════════════════════════════════════
    @client.on_message(filters.command("smute") & filters.group)
    async def smute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "smute"):
            return

        is_admin, can_restrict = await check_admin_with_permission(client, chat_id, admin_id)
        if not is_admin or not can_restrict:
            # Silent command hai — koi message nahi, bas return
            return

        target_identifier, _ = extract_user_and_reason(message)
        if not target_identifier:
            return

        bot = await get_bot_cached(client)
        if isinstance(target_identifier, int) and target_identifier == bot.id:
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error or not target_user_id:
            return
        if target_user_id == bot.id:
            return

        target_is_admin, _ = await check_admin_with_permission(client, chat_id, target_user_id)
        if target_is_admin:
            return

        try:
            await mute_with_retry(client, chat_id, target_user_id)
            logger.info(f"Smute: user {target_user_id} muted in chat {chat_id} by admin {admin_id}")

            if message.reply_to_message:
                try:
                    await message.reply_to_message.delete()
                except Exception as e:
                    logger.warning(f"Smute: couldn't delete replied message: {e}")
            try:
                await message.delete()
            except Exception as e:
                logger.warning(f"Smute: couldn't delete command message: {e}")

        except ChatAdminRequired:
            logger.warning(f"Smute: bot lacks admin rights in chat {chat_id}")
        except UserAdminInvalid:
            logger.warning(f"Smute: target {target_user_id} is admin, can't mute")
        except Exception as e:
            logger.error(f"Smute error: {e}", exc_info=True)


    # ══════════════════════════════════════════════════════
    # /dmute — Delete replied message + permanent mute
    # Sirf reply pe kaam karta hai
    # ══════════════════════════════════════════════════════
    @client.on_message(filters.command("dmute") & filters.group)
    async def dmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "dmute"):
            return

        is_admin, can_restrict = await check_admin_with_permission(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        if not message.reply_to_message:
            await message.reply_text(
                "Reply to a message to delete and mute the user.\n"
                "<code>/dmute</code> [reply to message]",
                parse_mode=ParseMode.HTML
            )
            return

        if not message.reply_to_message.from_user:
            await message.reply_text("Cannot identify the user from replied message.", parse_mode=ParseMode.HTML)
            return

        target_user_id = message.reply_to_message.from_user.id
        target_user = message.reply_to_message.from_user
        reason = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None

        bot = await get_bot_cached(client)
        if target_user_id == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        target_is_admin, _ = await check_admin_with_permission(client, chat_id, target_user_id)
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

            text = (
                f"<b>Mute Event</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {admin_mention}\n"
                f"<b>Reason:</b> {reason if reason else 'No reason provided'}"
            )

            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=unmute_button(target_user_id)
            )

        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user — they might be an admin.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Dmute error: {e}")
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    # ══════════════════════════════════════════════════════
    # /tmute — Timed mute
    # Usage: /tmute @user 1h reason  |  reply + /tmute 30m reason
    # Formats: 30m, 2h, 1d
    # ══════════════════════════════════════════════════════
    @client.on_message(filters.command("tmute") & filters.group)
    async def tmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "tmute"):
            return

        is_admin, can_restrict = await check_admin_with_permission(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        target_identifier = None
        time_val = None
        reason = None

        if message.reply_to_message:
            if message.reply_to_message.from_user:
                target_identifier = message.reply_to_message.from_user.id
            command_parts = message.text.split()
            if len(command_parts) < 2:
                await message.reply_text(
                    "Please specify mute duration.\n"
                    "<code>/tmute 1h</code> [reply to message]",
                    parse_mode=ParseMode.HTML
                )
                return
            time_val = command_parts[1]
            if len(command_parts) > 2:
                reason = " ".join(command_parts[2:])
        else:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                        target_identifier = entity.user.id
                        text_after = message.text[entity.offset + entity.length:].strip().split()
                        if text_after:
                            time_val = text_after[0]
                            reason = " ".join(text_after[1:]) if len(text_after) > 1 else None
                        break

            if not target_identifier:
                command_parts = message.text.split()
                if len(command_parts) < 3:
                    await message.reply_text(
                        "Please specify user and duration.\n"
                        "<code>/tmute @username 1h reason</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                user_arg = command_parts[1]
                time_val = command_parts[2]
                if user_arg.startswith('@'):
                    target_identifier = user_arg[1:]
                elif user_arg.isdigit():
                    target_identifier = int(user_arg)
                else:
                    await message.reply_text("Couldn't identify the user.", parse_mode=ParseMode.HTML)
                    return
                if len(command_parts) > 3:
                    reason = " ".join(command_parts[3:])

        mute_seconds, time_display = extract_time(time_val)
        if not mute_seconds:
            await message.reply_text(
                "<b>Invalid time format.</b>\n\n"
                "Use: <code>30m</code>, <code>2h</code>, <code>1d</code>",
                parse_mode=ParseMode.HTML
            )
            return

        bot = await get_bot_cached(client)
        if isinstance(target_identifier, int) and target_identifier == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return
        if target_user_id == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        target_is_admin, _ = await check_admin_with_permission(client, chat_id, target_user_id)
        if target_is_admin:
            await message.reply_text("I can't mute an admin.", parse_mode=ParseMode.HTML)
            return

        try:
            mute_until = datetime.now() + timedelta(seconds=mute_seconds)
            await mute_with_retry(client, chat_id, target_user_id, mute_until)

            admin_mention = make_mention(admin_id, message.from_user.first_name)
            user_mention = make_mention(target_user_id, target_user.first_name)

            text = (
                f"<b>Temporary Mute</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {admin_mention}\n"
                f"<b>Duration:</b> {time_display}\n"
                f"<b>Reason:</b> {reason if reason else 'No reason provided'}"
            )

            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=unmute_button(target_user_id)
            )

        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user — they might be an admin.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Tmute error: {e}")
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    # ══════════════════════════════════════════════════════
    # /stmute — Silent timed mute
    # Command + replied message dono delete — koi notification nahi
    # ══════════════════════════════════════════════════════
    @client.on_message(filters.command("stmute") & filters.group)
    async def stmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "stmute"):
            return

        is_admin, can_restrict = await check_admin_with_permission(client, chat_id, admin_id)
        if not is_admin or not can_restrict:
            return

        target_identifier = None
        time_val = None

        if message.reply_to_message:
            if message.reply_to_message.from_user:
                target_identifier = message.reply_to_message.from_user.id
            command_parts = message.text.split()
            if len(command_parts) < 2:
                return
            time_val = command_parts[1]
        else:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                        target_identifier = entity.user.id
                        text_after = message.text[entity.offset + entity.length:].strip().split()
                        if text_after:
                            time_val = text_after[0]
                        break

            if not target_identifier:
                command_parts = message.text.split()
                if len(command_parts) < 3:
                    return
                user_arg = command_parts[1]
                time_val = command_parts[2]
                if user_arg.startswith('@'):
                    target_identifier = user_arg[1:]
                elif user_arg.isdigit():
                    target_identifier = int(user_arg)
                else:
                    return

        mute_seconds, _ = extract_time(time_val)
        if not mute_seconds:
            return

        bot = await get_bot_cached(client)
        if isinstance(target_identifier, int) and target_identifier == bot.id:
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error or not target_user_id:
            return
        if target_user_id == bot.id:
            return

        target_is_admin, _ = await check_admin_with_permission(client, chat_id, target_user_id)
        if target_is_admin:
            return

        try:
            mute_until = datetime.now() + timedelta(seconds=mute_seconds)
            await mute_with_retry(client, chat_id, target_user_id, mute_until)
            logger.info(f"Stmute: user {target_user_id} muted for {mute_seconds}s in chat {chat_id} by admin {admin_id}")

            if message.reply_to_message:
                try:
                    await message.reply_to_message.delete()
                except Exception as e:
                    logger.warning(f"Stmute: couldn't delete replied message: {e}")
            try:
                await message.delete()
            except Exception as e:
                logger.warning(f"Stmute: couldn't delete command message: {e}")

        except ChatAdminRequired:
            logger.warning(f"Stmute: bot lacks admin rights in chat {chat_id}")
        except UserAdminInvalid:
            logger.warning(f"Stmute: target {target_user_id} is admin, can't mute")
        except Exception as e:
            logger.error(f"Stmute error: {e}", exc_info=True)


    # ══════════════════════════════════════════════════════
    # /dtmute — Delete replied message + timed mute
    # Sirf reply pe kaam karta hai
    # ══════════════════════════════════════════════════════
    @client.on_message(filters.command("dtmute") & filters.group)
    async def dtmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "dtmute"):
            return

        is_admin, can_restrict = await check_admin_with_permission(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to mute users.", parse_mode=ParseMode.HTML)
            return

        if not message.reply_to_message:
            await message.reply_text(
                "Reply to a message to delete and timed mute the user.\n"
                "<code>/dtmute 1h</code> [reply to message]",
                parse_mode=ParseMode.HTML
            )
            return

        if not message.reply_to_message.from_user:
            await message.reply_text("Cannot identify the user from replied message.", parse_mode=ParseMode.HTML)
            return

        target_user_id = message.reply_to_message.from_user.id
        target_user = message.reply_to_message.from_user

        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.reply_text(
                "Please specify mute duration.\n"
                "<code>/dtmute 1h</code> [reply to message]",
                parse_mode=ParseMode.HTML
            )
            return

        time_val = command_parts[1]
        reason = " ".join(command_parts[2:]) if len(command_parts) > 2 else None

        mute_seconds, time_display = extract_time(time_val)
        if not mute_seconds:
            await message.reply_text(
                "<b>Invalid time format.</b>\n\n"
                "Use: <code>30m</code>, <code>2h</code>, <code>1d</code>",
                parse_mode=ParseMode.HTML
            )
            return

        bot = await get_bot_cached(client)
        if target_user_id == bot.id:
            await message.reply_text("I can't mute myself.", parse_mode=ParseMode.HTML)
            return

        target_is_admin, _ = await check_admin_with_permission(client, chat_id, target_user_id)
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

            text = (
                f"<b>Temporary Mute</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {admin_mention}\n"
                f"<b>Duration:</b> {time_display}\n"
                f"<b>Reason:</b> {reason if reason else 'No reason provided'}"
            )

            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=unmute_button(target_user_id)
            )

        except ChatAdminRequired:
            await message.reply_text("I need admin rights to mute users.", parse_mode=ParseMode.HTML)
        except UserAdminInvalid:
            await message.reply_text("I can't mute this user — they might be an admin.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Dtmute error: {e}")
            await message.reply_text(f"Failed to mute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    # ══════════════════════════════════════════════════════
    # /unmute — User ko unmute karo
    # Usage: /unmute @user  |  reply + /unmute
    # ══════════════════════════════════════════════════════
    @client.on_message(filters.command("unmute") & filters.group)
    async def unmute_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if check_cooldown(admin_id, chat_id, "unmute"):
            return

        is_admin, can_restrict = await check_admin_with_permission(client, chat_id, admin_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_restrict:
            await message.reply_text("You need restrict permission to unmute users.", parse_mode=ParseMode.HTML)
            return

        target_identifier, _ = extract_user_and_reason(message)
        if not target_identifier:
            await message.reply_text(
                "Mention a user or reply to their message.\n"
                "<code>/unmute @username</code>",
                parse_mode=ParseMode.HTML
            )
            return

        bot = await get_bot_cached(client)
        if isinstance(target_identifier, int) and target_identifier == bot.id:
            await message.reply_text("I'm not muted.", parse_mode=ParseMode.HTML)
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return
        if target_user_id == bot.id:
            await message.reply_text("I'm not muted.", parse_mode=ParseMode.HTML)
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
            logger.error(f"Unmute error: {e}")
            await message.reply_text(f"Failed to unmute user.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


    # ══════════════════════════════════════════════════════
    # Unmute Callback — Inline button se unmute
    # ══════════════════════════════════════════════════════
    @client.on_callback_query(filters.regex(r"^unmute_user="))
    async def unmute_callback(client: Client, callback: CallbackQuery):
        chat_id = callback.message.chat.id
        caller_id = callback.from_user.id

        is_admin, can_restrict = await check_admin_with_permission(client, chat_id, caller_id)
        if not is_admin:
            await callback.answer("Only admins can unmute users!", show_alert=True)
            return
        if not can_restrict:
            await callback.answer("You need restrict permission to unmute users!", show_alert=True)
            return

        target_user_id = int(callback.data.split("=")[1])

        try:
            target_user = await client.get_users(target_user_id)
            user_mention = make_mention(target_user_id, target_user.first_name)
        except Exception:
            user_mention = f'<a href="tg://user?id={target_user_id}">User</a>'

        try:
            await unmute_with_retry(client, chat_id, target_user_id)

            caller_mention = make_mention(caller_id, callback.from_user.first_name)

            await callback.message.edit_text(
                f"<b>Unmute Event</b>\n\n"
                f"<b>User:</b> {user_mention}\n"
                f"<b>By:</b> {caller_mention}",
                parse_mode=ParseMode.HTML
            )
            await callback.answer("User unmuted!")

        except ChatAdminRequired:
            await callback.answer("I need admin rights to unmute!", show_alert=True)
        except Exception as e:
            await callback.answer(f"Failed: {e}", show_alert=True)
            logger.error(f"Unmute callback error: {e}")

    logger.info("✅ Mute handlers setup complete")
