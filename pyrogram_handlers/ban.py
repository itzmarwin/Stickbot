import logging
import re
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, ChatMemberStatus, ChatMembersFilter
from pyrogram.errors import ChatAdminRequired, UserNotParticipant, BadRequest, FloodWait

from pyrogram_handlers.utils import (
    is_user_admin,
    is_bot_admin,
    log_error
)

logger = logging.getLogger(__name__)

# Constants
MAX_BAN_DAYS = 30
MAX_BAN_HOURS = MAX_BAN_DAYS * 24  # 720 hours


def extract_time(time_string: str) -> tuple:
    """
    Extract time from string. Only supports hours (h) and days (d)
    
    Args:
        time_string: Time string like "1h", "24h", "7d", "30d"
    
    Returns:
        tuple: (seconds, formatted_string) or (None, None) if invalid
    
    Examples:
        "1h" -> (3600, "1 hour")
        "24h" -> (86400, "24 hours")
        "7d" -> (604800, "7 days")
    """
    
    if not time_string:
        return None, None
    
    # Regex pattern: number followed by h or d
    pattern = r'^(\d+)([hd])$'
    match = re.match(pattern, time_string.lower())
    
    if not match:
        return None, None
    
    amount = int(match.group(1))
    unit = match.group(2)
    
    # Calculate seconds
    if unit == 'h':
        # Hours
        if amount > MAX_BAN_HOURS:
            return None, None
        seconds = amount * 3600
        time_display = f"{amount} hour{'s' if amount != 1 else ''}"
    elif unit == 'd':
        # Days
        if amount > MAX_BAN_DAYS:
            return None, None
        seconds = amount * 86400
        time_display = f"{amount} day{'s' if amount != 1 else ''}"
    else:
        return None, None
    
    return seconds, time_display


def extract_user_and_reason(message: Message) -> tuple:
    """
    Extract user ID/username and reason from message
    
    Returns:
        tuple: (user_id, reason)
    
    Scenarios:
        1. Reply: /ban reason -> (replied_user_id, "reason")
        2. Username: /ban @user reason -> (user_id, "reason")
        3. ID: /ban 123456 reason -> (123456, "reason")
    """
    
    user_id = None
    reason = None
    
    # Check if it's a reply
    if message.reply_to_message:
        if message.reply_to_message.from_user:
            user_id = message.reply_to_message.from_user.id
        
        # Extract reason from command text
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) > 1:
            reason = command_parts[1]
    
    else:
        # Not a reply, extract from command text
        command_parts = message.text.split()
        
        if len(command_parts) < 2:
            # No user specified
            return None, None
        
        user_arg = command_parts[1]
        
        # Check if it's a username
        if user_arg.startswith('@'):
            username = user_arg[1:]
            user_id = username  # Will resolve later
        elif user_arg.isdigit():
            user_id = int(user_arg)
        else:
            # Invalid user format
            return None, None
        
        # Extract reason (everything after user)
        if len(command_parts) > 2:
            reason = " ".join(command_parts[2:])
    
    return user_id, reason


async def resolve_user(client: Client, chat_id: int, user_identifier) -> tuple:
    """
    Resolve user from username or ID
    
    Returns:
        tuple: (user_id, user_object, error_message)
    """
    
    if isinstance(user_identifier, str):
        # It's a username
        try:
            user = await client.get_users(user_identifier)
            return user.id, user, None
        except Exception as e:
            return None, None, f"User @{user_identifier} not found!"
    
    elif isinstance(user_identifier, int):
        # It's a user ID
        try:
            user = await client.get_users(user_identifier)
            return user.id, user, None
        except Exception as e:
            return None, None, f"User with ID {user_identifier} not found!"
    
    return None, None, "Invalid user!"


async def setup_ban_handlers(client: Client):
    
    @client.on_message(filters.command("ban") & filters.group)
    async def ban_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            # Admin check
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Bot admin check
            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please make me admin first!</b>", parse_mode=ParseMode.HTML)
                return
            
            # Extract user and reason
            target_identifier, reason = extract_user_and_reason(message)
            
            if not target_identifier:
                await message.reply_text(
                    "<b>How to use:</b>\n"
                    "• Reply: <code>/ban [reason]</code>\n"
                    "• Username: <code>/ban @username [reason]</code>\n"
                    "• User ID: <code>/ban 123456 [reason]</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Resolve user
            target_user_id, target_user, error = await resolve_user(client, chat_id, target_identifier)
            
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            
            # Self-protection check
            bot = await client.get_me()
            if target_user_id == bot.id:
                await message.reply_text("I can't ban myself! 🤔", parse_mode=ParseMode.HTML)
                return
            
            # Check if target is admin
            try:
                target_member = await client.get_chat_member(chat_id, target_user_id)
                if target_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                    await message.reply_text("I can't ban admins!", parse_mode=ParseMode.HTML)
                    return
            except:
                pass
            
            # Default reason
            if not reason:
                reason = "No reason provided"
            
            # Execute ban
            try:
                await client.ban_chat_member(chat_id, target_user_id)
                
                user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name}</a>'
                admin_mention = f'<a href="tg://user?id={user_id}">{message.from_user.first_name}</a>'
                
                ban_msg = (
                    f"🚫 <b>Ban Event</b>\n\n"
                    f"<b>User:</b> {user_mention}\n"
                    f"<b>Reason:</b> {reason}\n"
                    f"<b>Banned by:</b> {admin_mention}"
                )
                
                await message.reply_text(ban_msg, parse_mode=ParseMode.HTML)
            
            except FloodWait as e:
                await message.reply_text(f"⏳ Please wait {e.value} seconds!", parse_mode=ParseMode.HTML)
            except Exception as e:
                await message.reply_text(f"❌ Failed to ban user: {str(e)}", parse_mode=ParseMode.HTML)
        
        except Exception as e:
            log_error("ban_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred!", parse_mode=ParseMode.HTML)
    
    
    @client.on_message(filters.command("sban") & filters.group)
    async def silent_ban_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            # Admin check
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    return  # Silent fail
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Bot admin check
            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please make me admin first!</b>", parse_mode=ParseMode.HTML)
                return
            
            # Check if bot can delete messages
            bot = await client.get_me()
            bot_member = await client.get_chat_member(chat_id, bot.id)
            
            can_delete = False
            if bot_member.status == ChatMemberStatus.ADMINISTRATOR:
                if bot_member.privileges and bot_member.privileges.can_delete_messages:
                    can_delete = True
            
            if not can_delete:
                await message.reply_text(
                    "❌ I need delete message permission for silent ban!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Extract user and reason
            target_identifier, reason = extract_user_and_reason(message)
            
            if not target_identifier:
                await message.reply_text(
                    "<b>How to use:</b>\n"
                    "• Reply: <code>/sban [reason]</code>\n"
                    "• Username: <code>/sban @username [reason]</code>\n"
                    "• User ID: <code>/sban 123456 [reason]</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Resolve user
            target_user_id, target_user, error = await resolve_user(client, chat_id, target_identifier)
            
            if error:
                temp_msg = await message.reply_text(error, parse_mode=ParseMode.HTML)
                await asyncio.sleep(3)
                await temp_msg.delete()
                await message.delete()
                return
            
            # Self-protection check
            if target_user_id == bot.id:
                temp_msg = await message.reply_text("I can't ban myself! 🤔", parse_mode=ParseMode.HTML)
                await asyncio.sleep(3)
                await temp_msg.delete()
                await message.delete()
                return
            
            # Check if target is admin
            try:
                target_member = await client.get_chat_member(chat_id, target_user_id)
                if target_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                    temp_msg = await message.reply_text("I can't ban admins!", parse_mode=ParseMode.HTML)
                    await asyncio.sleep(3)
                    await temp_msg.delete()
                    await message.delete()
                    return
            except:
                pass
            
            # Execute silent ban
            try:
                await client.ban_chat_member(chat_id, target_user_id)
                
                # Delete replied message if exists
                if message.reply_to_message:
                    try:
                        await message.reply_to_message.delete()
                    except:
                        pass
                
                # Delete command message
                try:
                    await message.delete()
                except:
                    pass
            
            except FloodWait as e:
                await message.reply_text(f"⏳ Please wait {e.value} seconds!", parse_mode=ParseMode.HTML)
            except Exception as e:
                await message.reply_text(f"❌ Failed to ban user: {str(e)}", parse_mode=ParseMode.HTML)
        
        except Exception as e:
            log_error("silent_ban_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
    
    
    @client.on_message(filters.command("tban") & filters.group)
    async def temp_ban_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            # Admin check
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Bot admin check
            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please make me admin first!</b>", parse_mode=ParseMode.HTML)
                return
            
            # Parse command for tban
            target_identifier = None
            time_val = None
            reason = None
            
            if message.reply_to_message:
                # Reply method: /tban 1h reason
                if message.reply_to_message.from_user:
                    target_identifier = message.reply_to_message.from_user.id
                
                command_parts = message.text.split()
                
                if len(command_parts) < 2:
                    await message.reply_text(
                        "❌ Please specify ban duration!\n\n"
                        "<b>Usage:</b> <code>/tban 1h [reason]</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                time_val = command_parts[1]
                if len(command_parts) > 2:
                    reason = " ".join(command_parts[2:])
            
            else:
                # Not a reply: /tban @user 1h reason OR /tban 123456 1h reason
                command_parts = message.text.split()
                
                if len(command_parts) < 3:
                    await message.reply_text(
                        "<b>How to use:</b>\n"
                        "• Reply: <code>/tban 1h [reason]</code>\n"
                        "• Username: <code>/tban @username 1h [reason]</code>\n"
                        "• User ID: <code>/tban 123456 1h [reason]</code>\n\n"
                        "<b>Time format:</b> <code>1h</code> (hours) or <code>7d</code> (days)\n"
                        "<b>Max duration:</b> 30 days",
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
                    await message.reply_text("Invalid user!", parse_mode=ParseMode.HTML)
                    return
                
                if len(command_parts) > 3:
                    reason = " ".join(command_parts[3:])
            
            # Validate time
            ban_seconds, time_display = extract_time(time_val)
            
            if not ban_seconds:
                await message.reply_text(
                    "❌ <b>Invalid time format!</b>\n\n"
                    "<b>Valid formats:</b>\n"
                    "• <code>1h</code> - 1 hour\n"
                    "• <code>12h</code> - 12 hours\n"
                    "• <code>24h</code> - 24 hours\n"
                    "• <code>1d</code> - 1 day\n"
                    "• <code>7d</code> - 7 days\n"
                    "• <code>30d</code> - 30 days (max)\n\n"
                    "⚠️ Only hours (h) and days (d) are supported!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Resolve user
            target_user_id, target_user, error = await resolve_user(client, chat_id, target_identifier)
            
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            
            # Self-protection check
            bot = await client.get_me()
            if target_user_id == bot.id:
                await message.reply_text("I can't ban myself! 🤔", parse_mode=ParseMode.HTML)
                return
            
            # Check if target is admin
            try:
                target_member = await client.get_chat_member(chat_id, target_user_id)
                if target_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                    await message.reply_text("I can't ban admins!", parse_mode=ParseMode.HTML)
                    return
            except:
                pass
            
            # Default reason
            if not reason:
                reason = "No reason provided"
            
            # Calculate ban until time
            ban_until = datetime.now() + timedelta(seconds=ban_seconds)
            
            # Execute temporary ban
            try:
                await client.ban_chat_member(chat_id, target_user_id, until_date=ban_until)
                
                user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name}</a>'
                admin_mention = f'<a href="tg://user?id={user_id}">{message.from_user.first_name}</a>'
                
                ban_msg = (
                    f"⏰ <b>Temporary Ban</b>\n\n"
                    f"<b>User:</b> {user_mention}\n"
                    f"<b>Duration:</b> {time_display}\n"
                    f"<b>Reason:</b> {reason}\n"
                    f"<b>Banned by:</b> {admin_mention}"
                )
                
                await message.reply_text(ban_msg, parse_mode=ParseMode.HTML)
            
            except FloodWait as e:
                await message.reply_text(f"⏳ Please wait {e.value} seconds!", parse_mode=ParseMode.HTML)
            except Exception as e:
                await message.reply_text(f"❌ Failed to ban user: {str(e)}", parse_mode=ParseMode.HTML)
        
        except Exception as e:
            log_error("temp_ban_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred!", parse_mode=ParseMode.HTML)
    
    
    @client.on_message(filters.command("unban") & filters.group)
    async def unban_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            # Admin check
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Bot admin check
            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please make me admin first!</b>", parse_mode=ParseMode.HTML)
                return
            
            # Extract user and reason
            target_identifier, reason = extract_user_and_reason(message)
            
            if not target_identifier:
                await message.reply_text(
                    "<b>How to use:</b>\n"
                    "• Reply: <code>/unban</code>\n"
                    "• Username: <code>/unban @username</code>\n"
                    "• User ID: <code>/unban 123456</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Resolve user
            target_user_id, target_user, error = await resolve_user(client, chat_id, target_identifier)
            
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            
            # Self-protection check
            bot = await client.get_me()
            if target_user_id == bot.id:
                await message.reply_text("I'm not banned! 🤔", parse_mode=ParseMode.HTML)
                return
            
            # Check if user is actually banned
            try:
                target_member = await client.get_chat_member(chat_id, target_user_id)
                
                if target_member.status == ChatMemberStatus.ADMINISTRATOR:
                    await message.reply_text("This person is an admin!", parse_mode=ParseMode.HTML)
                    return
                
                if target_member.status == ChatMemberStatus.OWNER:
                    await message.reply_text("This person is the group owner!", parse_mode=ParseMode.HTML)
                    return
                
                if target_member.status == ChatMemberStatus.MEMBER:
                    await message.reply_text("This user is not banned!", parse_mode=ParseMode.HTML)
                    return
            
            except UserNotParticipant:
                # User is not in chat, might be banned
                pass
            except:
                pass
            
            # Execute unban
            try:
                await client.unban_chat_member(chat_id, target_user_id)
                
                user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name}</a>'
                admin_mention = f'<a href="tg://user?id={user_id}">{message.from_user.first_name}</a>'
                
                unban_msg = (
                    f"✅ <b>Unban Event</b>\n\n"
                    f"<b>User:</b> {user_mention}\n"
                    f"<b>Unbanned by:</b> {admin_mention}"
                )
                
                await message.reply_text(unban_msg, parse_mode=ParseMode.HTML)
            
            except FloodWait as e:
                await message.reply_text(f"⏳ Please wait {e.value} seconds!", parse_mode=ParseMode.HTML)
            except Exception as e:
                await message.reply_text(f"❌ Failed to unban user: {str(e)}", parse_mode=ParseMode.HTML)
        
        except Exception as e:
            log_error("unban_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred!", parse_mode=ParseMode.HTML)
    
    
    @client.on_message(filters.command("kick") & filters.group)
    async def kick_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            # Admin check
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "Looks like you're using anonymous admin mode.\n"
                    "Switch back to your user account to continue~",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Bot admin check
            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please make me admin first!</b>", parse_mode=ParseMode.HTML)
                return
            
            # Extract user and reason
            target_identifier, reason = extract_user_and_reason(message)
            
            if not target_identifier:
                await message.reply_text(
                    "<b>How to use:</b>\n"
                    "• Reply: <code>/kick [reason]</code>\n"
                    "• Username: <code>/kick @username [reason]</code>\n"
                    "• User ID: <code>/kick 123456 [reason]</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Resolve user
            target_user_id, target_user, error = await resolve_user(client, chat_id, target_identifier)
            
            if error:
                await message.reply_text(error, parse_mode=ParseMode.HTML)
                return
            
            # Self-protection check
            bot = await client.get_me()
            if target_user_id == bot.id:
                await message.reply_text("I can't kick myself! 🤔", parse_mode=ParseMode.HTML)
                return
            
            # Check if target is admin
            try:
                target_member = await client.get_chat_member(chat_id, target_user_id)
                if target_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                    await message.reply_text("I can't kick admins!", parse_mode=ParseMode.HTML)
                    return
            except:
                pass
            
            # Default reason
            if not reason:
                reason = "No reason provided"
            
            # Execute kick (ban + unban)
            try:
                await client.ban_chat_member(chat_id, target_user_id)
                await client.unban_chat_member(chat_id, target_user_id)
                
                user_mention = f'<a href="tg://user?id={target_user_id}">{target_user.first_name}</a>'
                admin_mention = f'<a href="tg://user?id={user_id}">{message.from_user.first_name}</a>'
                
                kick_msg = (
                    f"👢 <b>Kick Event</b>\n\n"
                    f"<b>User:</b> {user_mention}\n"
                    f"<b>Reason:</b> {reason}\n"
                    f"<b>Kicked by:</b> {admin_mention}"
                )
                
                await message.reply_text(kick_msg, parse_mode=ParseMode.HTML)
            
            except FloodWait as e:
                await message.reply_text(f"⏳ Please wait {e.value} seconds!", parse_mode=ParseMode.HTML)
            except Exception as e:
                await message.reply_text(f"❌ Failed to kick user: {str(e)}", parse_mode=ParseMode.HTML)
        
        except Exception as e:
            log_error("kick_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred!", parse_mode=ParseMode.HTML)
    
    
    @client.on_message(filters.command("kickme") & filters.group)
    async def kickme_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            if not user_id:
                return
            
            # Bot admin check
            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please make me admin first!</b>", parse_mode=ParseMode.HTML)
                return
            
            # Check if user is admin
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if is_admin:
                    await message.reply_text(
                        "I wish I could... but you're an admin! 😅",
                        parse_mode=ParseMode.HTML
                    )
                    return
            except:
                pass
            
            # IMPORTANT: Always kick the command sender, ignore everything else
            # Even if they reply to someone or mention someone, kick them!
            
            try:
                await client.ban_chat_member(chat_id, user_id)
                await client.unban_chat_member(chat_id, user_id)
                
                await message.reply_text(
                    "👋 Goodbye! You have been kicked as requested.",
                    parse_mode=ParseMode.HTML
                )
            
            except FloodWait as e:
                await message.reply_text(f"⏳ Please wait {e.value} seconds!", parse_mode=ParseMode.HTML)
            except Exception as e:
                await message.reply_text(f"❌ Failed to kick you: {str(e)}", parse_mode=ParseMode.HTML)
        
        except Exception as e:
            log_error("kickme_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
    
    
    @client.on_message(filters.command("unbanall") & filters.group)
    async def unbanall_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None
            
            # OWNER CHECK (not just admin)
            try:
                member = await client.get_chat_member(chat_id, user_id)
                if member.status != ChatMemberStatus.OWNER:
                    await message.reply_text(
                        "❌ <b>Only the group owner can use this command!</b>",
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
                await message.reply_text("Error checking permissions!", parse_mode=ParseMode.HTML)
                return
            
            # Bot admin check
            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please make me admin first!</b>", parse_mode=ParseMode.HTML)
                return
            
            # Start unbanning process
            progress_msg = await message.reply_text(
                "🔄 <b>Fetching banned users...</b>",
                parse_mode=ParseMode.HTML
            )
            
            try:
                banned_users = []
                
                # Fetch all banned members
                async for member in client.get_chat_members(
                    chat_id,
                    filter=ChatMembersFilter.BANNED
                ):
                    banned_users.append(member.user)
                
                if not banned_users:
                    await progress_msg.edit_text(
                        "✅ <b>No banned users found!</b>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                total = len(banned_users)
                await progress_msg.edit_text(
                    f"🔄 <b>Found {total} banned user(s).</b>\n\n"
                    f"Starting unban process...",
                    parse_mode=ParseMode.HTML
                )
                
                unbanned = 0
                failed = 0
                
                for user in banned_users:
                    try:
                        await client.unban_chat_member(chat_id, user.id)
                        unbanned += 1
                        
                        # Update progress every 10 users
                        if unbanned % 10 == 0:
                            await progress_msg.edit_text(
                                f"🔄 <b>Unbanning in progress...</b>\n\n"
                                f"<b>Progress:</b> {unbanned}/{total}",
                                parse_mode=ParseMode.HTML
                            )
                        
                        # Avoid flood
                        await asyncio.sleep(0.5)
                    
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                        # Retry
                        try:
                            await client.unban_chat_member(chat_id, user.id)
                            unbanned += 1
                        except:
                            failed += 1
                    
                    except Exception as e:
                        failed += 1
                        logger.error(f"Failed to unban {user.id}: {e}")
                
                # Final result
                await progress_msg.edit_text(
                    f"✅ <b>Unban Complete!</b>\n\n"
                    f"<b>Total banned users:</b> {total}\n"
                    f"<b>Successfully unbanned:</b> {unbanned}\n"
                    f"<b>Failed:</b> {failed}",
                    parse_mode=ParseMode.HTML
                )
            
            except FloodWait as e:
                await progress_msg.edit_text(
                    f"⏳ <b>Flood limit reached!</b>\n\n"
                    f"Please wait {e.value} seconds and try again.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                await progress_msg.edit_text(
                    f"❌ <b>Error:</b> {str(e)}",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            log_error("unbanall_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred!", parse_mode=ParseMode.HTML)
    
    logger.info("✅ Ban handlers setup complete")
