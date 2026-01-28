import logging
import re
import asyncio
import time
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, ChatMemberStatus, ChatMembersFilter
from pyrogram.errors import ChatAdminRequired, UserNotParticipant, BadRequest, FloodWait, UserAdminInvalid

from pyrogram_handlers.utils import (
    is_user_admin,
    log_error
)

logger = logging.getLogger(__name__)

MAX_BAN_DAYS = 30
MAX_BAN_HOURS = MAX_BAN_DAYS * 24

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
    if not time_string:
        return None, None
    
    pattern = r'^(\d+)([hd])$'
    match = re.match(pattern, time_string.lower())
    
    if not match:
        return None, None
    
    amount = int(match.group(1))
    unit = match.group(2)
    
    if unit == 'h':
        if amount > MAX_BAN_HOURS:
            return None, None
        seconds = amount * 3600
        time_display = f"{amount} hour{'s' if amount != 1 else ''}"
    elif unit == 'd':
        if amount > MAX_BAN_DAYS:
            return None, None
        seconds = amount * 86400
        time_display = f"{amount} day{'s' if amount != 1 else ''}"
    else:
        return None, None
    
    return seconds, time_display

def extract_user_and_reason(message: Message) -> tuple:
    user_id = None
    reason = None
    
    if message.reply_to_message:
        if message.reply_to_message.from_user:
            user_id = message.reply_to_message.from_user.id
        
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) > 1:
            reason = command_parts[1]
    else:
        command_parts = message.text.split()
        
        if len(command_parts) < 2:
            return None, None
        
        user_arg = command_parts[1]
        
        if user_arg.startswith('@'):
            username = user_arg[1:]
            user_id = username
        elif user_arg.isdigit():
            user_id = int(user_arg)
        else:
            return None, None
        
        if len(command_parts) > 2:
            reason = " ".join(command_parts[2:])
    
    return user_id, reason

async def resolve_user_optimized(client: Client, user_identifier) -> tuple:
    if isinstance(user_identifier, int):
        try:
            user = await client.get_users(user_identifier)
            return user.id, user, None
        except:
            return user_identifier, None, None
    
    if isinstance(user_identifier, str):
        try:
            user = await client.get_users(user_identifier)
            return user.id, user, None
        except:
            return None, None, f"User @{user_identifier} not found!"
    
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
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            if check_cooldown(user_id, chat_id, "ban"):
                return
            
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            
            target_identifier, reason = extract_user_and_reason(message)
            
            if not target_identifier:
                await message.reply_text(
                    "<b>Reply to a user or mention a username to ban.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            bot = await get_bot_cached(client)
            
            if isinstance(target_identifier, int) and target_identifier == bot.id:
                await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
                return
            
            target_user_id, target_user, error = await resolve_user_optimized(client, target_identifier)
            
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            
            if target_user_id == bot.id:
                await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
                return
            
            if not reason:
                reason = "No reason provided"
            
            try:
                await ban_with_retry(client, chat_id, target_user_id)
                
                if target_user:
                    user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name}</a>'
                else:
                    user_mention = f'<a href="tg://user?id={target_user_id}">User</a>'
                
                ban_msg = (
                    f"<b>Ban Event</b>\n\n"
                    f"<b>User:</b> {user_mention}\n"
                    f"<b>Reason:</b> {reason}"
                )
                
                await message.reply_text(ban_msg, parse_mode=ParseMode.HTML)
            
            except ChatAdminRequired:
                await message.reply_text("<b>Please make me admin first.</b>", parse_mode=ParseMode.HTML)
            except UserAdminInvalid:
                await message.reply_text("I can't ban admins.", parse_mode=ParseMode.HTML)
            except FloodWait:
                pass
            except Exception as e:
                log_error("ban_command", e, chat_id=chat_id, user_id=user_id)
        
        except Exception as e:
            log_error("ban_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
    
    
    @client.on_message(filters.command("sban") & filters.group)
    async def silent_ban_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            if check_cooldown(user_id, chat_id, "sban"):
                return
            
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            
            target_identifier, reason = extract_user_and_reason(message)
            
            if not target_identifier:
                await message.reply_text(
                    "<b>Reply to a user or mention a username to Silent ban.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            bot = await get_bot_cached(client)
            
            if isinstance(target_identifier, int) and target_identifier == bot.id:
                temp_msg = await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
                await asyncio.sleep(3)
                try:
                    await temp_msg.delete()
                    await message.delete()
                except:
                    pass
                return
            
            target_user_id, target_user, error = await resolve_user_optimized(client, target_identifier)
            
            if error:
                temp_msg = await message.reply_text(error, parse_mode=ParseMode.HTML)
                await asyncio.sleep(3)
                try:
                    await temp_msg.delete()
                    await message.delete()
                except:
                    pass
                return
            
            if target_user_id == bot.id:
                temp_msg = await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
                await asyncio.sleep(3)
                try:
                    await temp_msg.delete()
                    await message.delete()
                except:
                    pass
                return
            
            try:
                await ban_with_retry(client, chat_id, target_user_id)
                
                if message.reply_to_message:
                    try:
                        await message.reply_to_message.delete()
                    except:
                        pass
                
                try:
                    await message.delete()
                except:
                    pass
            
            except ChatAdminRequired:
                await message.reply_text("<b>Please make me admin first.</b>", parse_mode=ParseMode.HTML)
            except UserAdminInvalid:
                temp_msg = await message.reply_text("I can't ban admins.", parse_mode=ParseMode.HTML)
                await asyncio.sleep(3)
                try:
                    await temp_msg.delete()
                    await message.delete()
                except:
                    pass
            except FloodWait:
                pass
            except Exception as e:
                log_error("silent_ban_command", e, chat_id=chat_id, user_id=user_id)
        
        except Exception as e:
            log_error("silent_ban_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
    
    
    @client.on_message(filters.command("tban") & filters.group)
    async def temp_ban_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            if check_cooldown(user_id, chat_id, "tban"):
                return
            
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
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
                        "Please specify ban duration.",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                time_val = command_parts[1]
                if len(command_parts) > 2:
                    reason = " ".join(command_parts[2:])
            else:
                command_parts = message.text.split()
                
                if len(command_parts) < 3:
                    await message.reply_text(
                        "<b>Reply to a user or mention a username to Temporary ban.</b>",
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
                    await message.reply_text("Invalid user", parse_mode=ParseMode.HTML)
                    return
                
                if len(command_parts) > 3:
                    reason = " ".join(command_parts[3:])
            
            ban_seconds, time_display = extract_time(time_val)
            
            if not ban_seconds:
                await message.reply_text(
                    "<b>Invalid time format.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            bot = await get_bot_cached(client)
            
            if isinstance(target_identifier, int) and target_identifier == bot.id:
                await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
                return
            
            target_user_id, target_user, error = await resolve_user_optimized(client, target_identifier)
            
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            
            if target_user_id == bot.id:
                await message.reply_text("I can't ban myself.", parse_mode=ParseMode.HTML)
                return
            
            if not reason:
                reason = "No reason provided"
            
            ban_until = datetime.now() + timedelta(seconds=ban_seconds)
            
            try:
                await ban_with_retry(client, chat_id, target_user_id, ban_until)
                
                if target_user:
                    user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name}</a>'
                else:
                    user_mention = f'<a href="tg://user?id={target_user_id}">User</a>'
                
                ban_msg = (
                    f"<b>Temporary Ban</b>\n\n"
                    f"<b>User:</b> {user_mention}\n"
                    f"<b>Duration:</b> {time_display}\n"
                    f"<b>Reason:</b> {reason}"
                )
                
                await message.reply_text(ban_msg, parse_mode=ParseMode.HTML)
            
            except ChatAdminRequired:
                await message.reply_text("<b>Please make me admin first.</b>", parse_mode=ParseMode.HTML)
            except UserAdminInvalid:
                await message.reply_text("I can't ban admins.", parse_mode=ParseMode.HTML)
            except FloodWait:
                pass
            except Exception as e:
                log_error("temp_ban_command", e, chat_id=chat_id, user_id=user_id)
        
        except Exception as e:
            log_error("temp_ban_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
    
    
    @client.on_message(filters.command("unban") & filters.group)
    async def unban_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            if check_cooldown(user_id, chat_id, "unban"):
                return
            
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            
            target_identifier, reason = extract_user_and_reason(message)
            
            if not target_identifier:
                await message.reply_text(
                    "<b>Reply to a user or mention a username to Unban.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            bot = await get_bot_cached(client)
            
            if isinstance(target_identifier, int) and target_identifier == bot.id:
                await message.reply_text("I'm not banned.", parse_mode=ParseMode.HTML)
                return
            
            target_user_id, target_user, error = await resolve_user_optimized(client, target_identifier)
            
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            
            if target_user_id == bot.id:
                await message.reply_text("I'm not banned.", parse_mode=ParseMode.HTML)
                return
            
            try:
                await unban_with_retry(client, chat_id, target_user_id)
                
                if target_user:
                    user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name}</a>'
                else:
                    user_mention = f'<a href="tg://user?id={target_user_id}">User</a>'
                
                unban_msg = (
                    f"<b>Unban Event</b>\n\n"
                    f"<b>User:</b> {user_mention}"
                )
                
                await message.reply_text(unban_msg, parse_mode=ParseMode.HTML)
            
            except ChatAdminRequired:
                await message.reply_text("<b>Please make me admin first.</b>", parse_mode=ParseMode.HTML)
            except FloodWait:
                pass
            except Exception as e:
                log_error("unban_command", e, chat_id=chat_id, user_id=user_id)
        
        except Exception as e:
            log_error("unban_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
    
    
    @client.on_message(filters.command("kick") & filters.group)
    async def kick_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            if check_cooldown(user_id, chat_id, "kick"):
                return
            
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            
            target_identifier, reason = extract_user_and_reason(message)
            
            if not target_identifier:
                await message.reply_text(
                    "<b>Reply to a user or mention a username to Kick.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            bot = await get_bot_cached(client)
            
            if isinstance(target_identifier, int) and target_identifier == bot.id:
                await message.reply_text("I can't kick myself.", parse_mode=ParseMode.HTML)
                return
            
            target_user_id, target_user, error = await resolve_user_optimized(client, target_identifier)
            
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            
            if target_user_id == bot.id:
                await message.reply_text("I can't kick myself.", parse_mode=ParseMode.HTML)
                return
            
            if not reason:
                reason = "No reason provided"
            
            try:
                await ban_with_retry(client, chat_id, target_user_id)
                await unban_with_retry(client, chat_id, target_user_id)
                
                if target_user:
                    user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name}</a>'
                else:
                    user_mention = f'<a href="tg://user?id={target_user_id}">User</a>'
                
                kick_msg = (
                    f"<b>Kick Event</b>\n\n"
                    f"<b>User:</b> {user_mention}\n"
                    f"<b>Reason:</b> {reason}"
                )
                
                await message.reply_text(kick_msg, parse_mode=ParseMode.HTML)
            
            except ChatAdminRequired:
                await message.reply_text("<b>Please make me admin first.</b>", parse_mode=ParseMode.HTML)
            except UserAdminInvalid:
                await message.reply_text("I can't kick admins.", parse_mode=ParseMode.HTML)
            except FloodWait:
                pass
            except Exception as e:
                log_error("kick_command", e, chat_id=chat_id, user_id=user_id)
        
        except Exception as e:
            log_error("kick_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
    
    
    @client.on_message(filters.command("kickme") & filters.group)
    async def kickme_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            if not user_id:
                return
            
            if check_cooldown(user_id, chat_id, "kickme"):
                return
            
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if is_admin:
                    await message.reply_text(
                        "I wish I could... but you're an admin.",
                        parse_mode=ParseMode.HTML
                    )
                    return
            except:
                pass
            
            try:
                await ban_with_retry(client, chat_id, user_id)
                await unban_with_retry(client, chat_id, user_id)
                
                await message.reply_text(
                    "Goodbye..... You have been kicked as requested.",
                    parse_mode=ParseMode.HTML
                )
            
            except ChatAdminRequired:
                await message.reply_text("<b>Please make me admin first.</b>", parse_mode=ParseMode.HTML)
            except FloodWait:
                pass
            except Exception as e:
                log_error("kickme_command", e, chat_id=chat_id, user_id=user_id)
        
        except Exception as e:
            log_error("kickme_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
    
    
    @client.on_message(filters.command("unbanall") & filters.group)
    async def unbanall_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            try:
                member = await client.get_chat_member(chat_id, user_id)
                if member.status != ChatMemberStatus.OWNER:
                    await message.reply_text(
                        "<b>Only the group owner can use this command.</b>",
                        parse_mode=ParseMode.HTML
                    )
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception as e:
                await message.reply_text("Error checking permissions.", parse_mode=ParseMode.HTML)
                return
            
            progress_msg = await message.reply_text(
                "<b>Fetching banned users...</b>",
                parse_mode=ParseMode.HTML
            )
            
            try:
                banned_users = []
                
                async for member in client.get_chat_members(
                    chat_id,
                    filter=ChatMembersFilter.BANNED
                ):
                    banned_users.append(member.user)
                
                if not banned_users:
                    await progress_msg.edit_text(
                        "<b>No banned users found.</b>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                total = len(banned_users)
                await progress_msg.edit_text(
                    f"<b>Found {total} banned user(s).</b>\n\n"
                    f"Starting unban process...",
                    parse_mode=ParseMode.HTML
                )
                
                unbanned = 0
                failed = 0
                
                for user in banned_users:
                    try:
                        await client.unban_chat_member(chat_id, user.id)
                        unbanned += 1
                        
                        if unbanned % 10 == 0:
                            await progress_msg.edit_text(
                                f"<b>Unbanning in progress...</b>\n\n"
                                f"<b>Progress:</b> {unbanned}/{total}",
                                parse_mode=ParseMode.HTML
                            )
                        
                        await asyncio.sleep(0.5)
                    
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                        try:
                            await client.unban_chat_member(chat_id, user.id)
                            unbanned += 1
                        except:
                            failed += 1
                    
                    except Exception as e:
                        failed += 1
                        logger.error(f"Failed to unban {user.id}: {e}")
                
                await progress_msg.edit_text(
                    f"<b>Unban Complete!</b>\n\n"
                    f"<b>Total banned users:</b> {total}\n"
                    f"<b>Successfully unbanned:</b> {unbanned}\n"
                    f"<b>Failed:</b> {failed}",
                    parse_mode=ParseMode.HTML
                )
            
            except FloodWait as e:
                await progress_msg.edit_text(
                    f"<b>Flood limit reached!</b>\n\n"
                    f"Please wait {e.value} seconds and try again.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                await progress_msg.edit_text(
                    f"<b>Error:</b> {str(e)}",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            log_error("unbanall_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred.", parse_mode=ParseMode.HTML)
    
    logger.info("✅ Ban handlers setup complete")
