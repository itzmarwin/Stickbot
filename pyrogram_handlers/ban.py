import re
import asyncio
import time
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, ChatMemberStatus, ChatMembersFilter, MessageEntityType
from pyrogram.errors import ChatAdminRequired, FloodWait, UserAdminInvalid

from pyrogram_handlers.caching import get_admin_permissions

MAX_BAN_DAYS  = 30
MAX_BAN_HOURS = MAX_BAN_DAYS * 24

_bot_cache       = None
_user_cooldowns  = {}
COOLDOWN_SECONDS = 3


async def get_bot_cached(client: Client):
    global _bot_cache
    if _bot_cache is None:
        _bot_cache = await client.get_me()
    return _bot_cache


def check_cooldown(user_id: int, chat_id: int, command: str) -> bool:
    key          = f"{user_id}:{chat_id}:{command}"
    current_time = time.time()
    if key in _user_cooldowns:
        if current_time - _user_cooldowns[key] < COOLDOWN_SECONDS:
            return True
    _user_cooldowns[key] = current_time
    return False


async def check_ban_permission(client: Client, chat_id: int, user_id: int) -> tuple:
    perms = get_admin_permissions(chat_id, user_id)
    if perms is not None:
        return True, perms["can_ban"]

    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status == ChatMemberStatus.OWNER:
            return True, True
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return False, False
        can_ban = bool(getattr(member.privileges, "can_restrict_members", False))
        return True, can_ban
    except ChatAdminRequired:
        try:
            async for admin in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                if admin.user.id == user_id:
                    can_ban = bool(getattr(admin.privileges, "can_restrict_members", False))
                    return True, can_ban
            return False, False
        except Exception:
            return False, False
    except Exception:
        return False, False


def is_target_admin(chat_id: int, target_user_id: int) -> bool:
    return get_admin_permissions(chat_id, target_user_id) is not None


def extract_time(time_string: str) -> tuple:
    if not time_string:
        return None, None
    match = re.match(r'^(\d+)([hd])$', time_string.lower())
    if not match:
        return None, None
    amount = int(match.group(1))
    unit   = match.group(2)
    if unit == 'h':
        if amount > MAX_BAN_HOURS:
            return None, None
        return amount * 3600, f"{amount} hour{'s' if amount != 1 else ''}"
    if unit == 'd':
        if amount > MAX_BAN_DAYS:
            return None, None
        return amount * 86400, f"{amount} day{'s' if amount != 1 else ''}"
    return None, None


def extract_user_and_reason(message: Message) -> tuple:
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id if message.reply_to_message.from_user else None
        parts   = message.text.split(maxsplit=1)
        return user_id, parts[1] if len(parts) > 1 else None

    if message.entities:
        for entity in message.entities:
            if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                text_after = message.text[entity.offset + entity.length:].strip()
                return entity.user.id, text_after if text_after else None

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


async def resolve_user(client: Client, user_identifier) -> tuple:
    if isinstance(user_identifier, (int, str)):
        try:
            user = await client.get_users(user_identifier)
            return user.id, user, None
        except Exception:
            tag = f"@{user_identifier}" if isinstance(user_identifier, str) else str(user_identifier)
            return None, None, f"User {tag} not found!"
    return None, None, "Invalid user!"


async def ban_with_retry(client: Client, chat_id: int, user_id: int, until_date=None):
    try:
        if until_date:
            await client.ban_chat_member(chat_id, user_id, until_date=until_date)
        else:
            await client.ban_chat_member(chat_id, user_id)
    except FloodWait as e:
        if e.value <= 10:
            await asyncio.sleep(e.value)
            if until_date:
                await client.ban_chat_member(chat_id, user_id, until_date=until_date)
            else:
                await client.ban_chat_member(chat_id, user_id)
        else:
            raise


async def unban_with_retry(client: Client, chat_id: int, user_id: int):
    try:
        await client.unban_chat_member(chat_id, user_id)
    except FloodWait as e:
        if e.value <= 10:
            await asyncio.sleep(e.value)
            await client.unban_chat_member(chat_id, user_id)
        else:
            raise


async def setup_ban_handlers(client: Client):

    @client.on_message(filters.command("ban") & filters.group)
    async def ban_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if check_cooldown(user_id, chat_id, "ban"):
            return

        is_admin, can_ban = await check_ban_permission(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_ban:
            await message.reply_text("You need ban permission to use this command.", parse_mode=ParseMode.HTML)
            return

        target_identifier, reason = extract_user_and_reason(message)
        if not target_identifier:
            await message.reply_text("Couldn't identify the user, please reply to their message.", parse_mode=ParseMode.HTML)
            return

        bot = await get_bot_cached(client)
        if isinstance(target_identifier, int) and target_identifier == bot.id:
            await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return
        if target_user_id == bot.id:
            await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
            return
        if is_target_admin(chat_id, target_user_id):
            await message.reply_text("I can't ban an admin.", parse_mode=ParseMode.HTML)
            return

        if not reason:
            reason = "No reason provided"

        try:
            await ban_with_retry(client, chat_id, target_user_id)
        except UserAdminInvalid:
            await message.reply_text("I can't ban an admin.", parse_mode=ParseMode.HTML)
            return
        except Exception:
            await message.reply_text("Failed to ban user.", parse_mode=ParseMode.HTML)
            return

        user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name if target_user else "User"}</a>'
        await message.reply_text(
            f"<b>Ban Event</b>\n\n<b>User:</b> {user_mention}\n<b>Reason:</b> {reason}",
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("sban") & filters.group)
    async def silent_ban_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if check_cooldown(user_id, chat_id, "sban"):
            return

        is_admin, can_ban = await check_ban_permission(client, chat_id, user_id)
        if not is_admin or not can_ban:
            return

        target_identifier, reason = extract_user_and_reason(message)
        if not target_identifier:
            await message.reply_text("Couldn't identify the user, please reply to their message.", parse_mode=ParseMode.HTML)
            return

        bot = await get_bot_cached(client)

        if isinstance(target_identifier, int) and target_identifier == bot.id:
            temp = await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
            await asyncio.sleep(3)
            try:
                await temp.delete()
                await message.delete()
            except Exception:
                pass
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error:
            temp = await message.reply_text(error, parse_mode=ParseMode.HTML)
            await asyncio.sleep(3)
            try:
                await temp.delete()
                await message.delete()
            except Exception:
                pass
            return
        if target_user_id == bot.id:
            temp = await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
            await asyncio.sleep(3)
            try:
                await temp.delete()
                await message.delete()
            except Exception:
                pass
            return
        if is_target_admin(chat_id, target_user_id):
            return

        try:
            await ban_with_retry(client, chat_id, target_user_id)
        except (UserAdminInvalid, Exception):
            return

        if message.reply_to_message:
            try:
                await message.reply_to_message.delete()
            except Exception:
                pass
        try:
            await message.delete()
        except Exception:
            pass


    @client.on_message(filters.command("tban") & filters.group)
    async def temp_ban_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if check_cooldown(user_id, chat_id, "tban"):
            return

        is_admin, can_ban = await check_ban_permission(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_ban:
            await message.reply_text("You need ban permission to use this command.", parse_mode=ParseMode.HTML)
            return

        target_identifier = None
        time_val          = None
        reason            = None

        if message.reply_to_message:
            if message.reply_to_message.from_user:
                target_identifier = message.reply_to_message.from_user.id
            parts    = message.text.split()
            if len(parts) < 2:
                await message.reply_text("Please specify ban duration.", parse_mode=ParseMode.HTML)
                return
            time_val = parts[1]
            reason   = " ".join(parts[2:]) if len(parts) > 2 else None
        else:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                        target_identifier = entity.user.id
                        text_after        = message.text[entity.offset + entity.length:].strip().split()
                        if text_after:
                            time_val = text_after[0]
                            reason   = " ".join(text_after[1:]) if len(text_after) > 1 else None
                        break

            if not target_identifier:
                parts = message.text.split()
                if len(parts) < 3:
                    await message.reply_text("Couldn't identify the user, please reply to their message.", parse_mode=ParseMode.HTML)
                    return
                user_arg = parts[1]
                time_val = parts[2]
                if user_arg.startswith('@'):
                    target_identifier = user_arg[1:]
                elif user_arg.isdigit():
                    target_identifier = int(user_arg)
                else:
                    await message.reply_text("Couldn't identify the user, please reply to their message.", parse_mode=ParseMode.HTML)
                    return
                reason = " ".join(parts[3:]) if len(parts) > 3 else None

        ban_seconds, time_display = extract_time(time_val)
        if not ban_seconds:
            await message.reply_text("<b>Invalid time format.</b>", parse_mode=ParseMode.HTML)
            return

        bot = await get_bot_cached(client)
        if isinstance(target_identifier, int) and target_identifier == bot.id:
            await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return
        if target_user_id == bot.id:
            await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
            return
        if is_target_admin(chat_id, target_user_id):
            await message.reply_text("I can't ban an admin.", parse_mode=ParseMode.HTML)
            return

        if not reason:
            reason = "No reason provided"

        try:
            ban_until = datetime.now() + timedelta(seconds=ban_seconds)
            await ban_with_retry(client, chat_id, target_user_id, ban_until)
        except UserAdminInvalid:
            await message.reply_text("I can't ban an admin.", parse_mode=ParseMode.HTML)
            return
        except Exception:
            await message.reply_text("Failed to ban user.", parse_mode=ParseMode.HTML)
            return

        user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name if target_user else "User"}</a>'
        await message.reply_text(
            f"<b>Temporary Ban</b>\n\n<b>User:</b> {user_mention}\n<b>Duration:</b> {time_display}\n<b>Reason:</b> {reason}",
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("unban") & filters.group)
    async def unban_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if check_cooldown(user_id, chat_id, "unban"):
            return

        is_admin, can_ban = await check_ban_permission(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_ban:
            await message.reply_text("You need ban permission to use this command.", parse_mode=ParseMode.HTML)
            return

        target_identifier, reason = extract_user_and_reason(message)
        if not target_identifier:
            await message.reply_text("Couldn't identify the user, please reply to their message.", parse_mode=ParseMode.HTML)
            return

        bot = await get_bot_cached(client)
        if isinstance(target_identifier, int) and target_identifier == bot.id:
            await message.reply_text("I'm not banned.", parse_mode=ParseMode.HTML)
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return
        if target_user_id == bot.id:
            await message.reply_text("I'm not banned.", parse_mode=ParseMode.HTML)
            return

        await unban_with_retry(client, chat_id, target_user_id)

        user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name if target_user else "User"}</a>'
        await message.reply_text(
            f"<b>Unban Event</b>\n\n<b>User:</b> {user_mention}",
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("kick") & filters.group)
    async def kick_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if check_cooldown(user_id, chat_id, "kick"):
            return

        is_admin, can_ban = await check_ban_permission(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
            return
        if not can_ban:
            await message.reply_text("You need ban permission to use this command.", parse_mode=ParseMode.HTML)
            return

        target_identifier, reason = extract_user_and_reason(message)
        if not target_identifier:
            await message.reply_text("Couldn't identify the user, please reply to their message.", parse_mode=ParseMode.HTML)
            return

        bot = await get_bot_cached(client)
        if isinstance(target_identifier, int) and target_identifier == bot.id:
            await message.reply_text("I can't kick myself.", parse_mode=ParseMode.HTML)
            return

        target_user_id, target_user, error = await resolve_user(client, target_identifier)
        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return
        if target_user_id == bot.id:
            await message.reply_text("I can't kick myself.", parse_mode=ParseMode.HTML)
            return
        if is_target_admin(chat_id, target_user_id):
            await message.reply_text("I can't kick an admin.", parse_mode=ParseMode.HTML)
            return

        if not reason:
            reason = "No reason provided"

        try:
            await ban_with_retry(client, chat_id, target_user_id)
            await unban_with_retry(client, chat_id, target_user_id)
        except UserAdminInvalid:
            await message.reply_text("I can't kick an admin.", parse_mode=ParseMode.HTML)
            return
        except Exception:
            await message.reply_text("Failed to kick user.", parse_mode=ParseMode.HTML)
            return

        user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name if target_user else "User"}</a>'
        await message.reply_text(
            f"<b>Kick Event</b>\n\n<b>User:</b> {user_mention}\n<b>Reason:</b> {reason}",
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("kickme") & filters.group)
    async def kickme_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if not user_id:
            return
        if check_cooldown(user_id, chat_id, "kickme"):
            return

        if is_target_admin(chat_id, user_id):
            await message.reply_text("I wish I could... but you're an admin.", parse_mode=ParseMode.HTML)
            return

        try:
            member = await client.get_chat_member(chat_id, user_id)
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                await message.reply_text("I wish I could... but you're an admin.", parse_mode=ParseMode.HTML)
                return
        except Exception:
            pass

        await ban_with_retry(client, chat_id, user_id)
        await unban_with_retry(client, chat_id, user_id)
        await message.reply_text("Goodbye..... You have been kicked as requested.", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("unbanall") & filters.group)
    async def unbanall_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        perms = get_admin_permissions(chat_id, user_id)
        if perms is not None:
            if not perms["is_owner"]:
                await message.reply_text("<b>Only the group owner can use this command.</b>", parse_mode=ParseMode.HTML)
                return
        else:
            try:
                member = await client.get_chat_member(chat_id, user_id)
                if member.status != ChatMemberStatus.OWNER:
                    await message.reply_text("<b>Only the group owner can use this command.</b>", parse_mode=ParseMode.HTML)
                    return
            except Exception:
                await message.reply_text("<b>Only the group owner can use this command.</b>", parse_mode=ParseMode.HTML)
                return

        progress_msg = await message.reply_text("<b>Fetching banned users...</b>", parse_mode=ParseMode.HTML)

        banned_users = []
        async for m in client.get_chat_members(chat_id, filter=ChatMembersFilter.BANNED):
            banned_users.append(m.user)

        if not banned_users:
            await progress_msg.edit_text("<b>No banned users found.</b>", parse_mode=ParseMode.HTML)
            return

        total = len(banned_users)
        await progress_msg.edit_text(
            f"<b>Found {total} banned user(s).</b>\n\nStarting unban process...",
            parse_mode=ParseMode.HTML
        )

        unbanned = 0
        failed   = 0

        for user in banned_users:
            try:
                await client.unban_chat_member(chat_id, user.id)
                unbanned += 1
                if unbanned % 10 == 0:
                    await progress_msg.edit_text(
                        f"<b>Unbanning in progress...</b>\n\n<b>Progress:</b> {unbanned}/{total}",
                        parse_mode=ParseMode.HTML
                    )
                await asyncio.sleep(0.5)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    await client.unban_chat_member(chat_id, user.id)
                    unbanned += 1
                except Exception:
                    failed += 1
            except Exception:
                failed += 1

        await progress_msg.edit_text("<b>Unban Complete.</b>", parse_mode=ParseMode.HTML)
