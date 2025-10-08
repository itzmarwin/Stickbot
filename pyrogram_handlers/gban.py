import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums import ChatMemberStatus

from config import is_admin, LOG_GROUP_ID  # Changed from is_owner to is_admin
from database import (
    add_banned_user, remove_banned_user, get_banned_count, get_banned_users,
    get_served_chats, is_banned_user, delete_user_packs
)

logger = logging.getLogger(__name__)

# In-memory cache for banned users
BANNED_USERS = set()

async def get_readable_time(seconds: int) -> str:
    """Convert seconds to human readable time"""
    periods = [
        ('s', 1),
        ('m', 60),
        ('h', 3600),
        ('d', 86400),
    ]
    
    result = []
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result.append(f"{period_value}{period_name}")
    
    return " ".join(result[-2:]) if result else "0s"

async def extract_user(client: Client, message: Message):
    """Extract user from message (reply or command arguments)"""
    if message.reply_to_message:
        return message.reply_to_message.from_user
    
    if len(message.command) > 1:
        user_input = message.command[1]
        try:
            if user_input.isdigit():
                user_id = int(user_input)
                user = await client.get_users(user_id)
                return user
            else:
                username = user_input.lstrip('@')
                user = await client.get_users(username)
                return user
        except Exception:
            return None
    
    return None

async def setup_gban_handlers(client: Client):
    """Setup GBan command handlers"""
    
    # GBan command
    @client.on_message(filters.command(["gban", "globalban"]))
    async def global_ban(client: Client, message: Message):
        # Check if user is admin
        if not is_admin(message.from_user.id):
            await message.reply("❌ This command is only for bot admins.")
            return
        
        user = await extract_user(client, message)
        if not user:
            await message.reply("❌ **Usage:** `/gban <user_id/username> [reason]` or reply to user's message")
            return
        
        if user.id == message.from_user.id:
            return await message.reply("❌ You cannot gban yourself!")
        elif user.id == client.me.id:
            return await message.reply("❌ I cannot gban myself!")
        elif is_admin(user.id):  # Changed from is_owner to is_admin
            return await message.reply("❌ Cannot gban another admin!")
        
        # Check if already gbanned
        is_gbanned = await is_banned_user(user.id)
        if is_gbanned:
            return await message.reply(f"❌ {user.mention} is already globally banned!")
        
        # Extract reason
        reason = "No reason provided"
        if len(message.command) > 2:
            reason = " ".join(message.command[2:])
        elif len(message.command) > 1 and not message.reply_to_message:
            reason = " ".join(message.command[1:])
        
        # Add to in-memory cache
        BANNED_USERS.add(user.id)
        
        # Get all served chats
        served_chats = []
        chats = await get_served_chats()
        for chat in chats:
            served_chats.append(int(chat["chat_id"]))
        
        # Calculate expected time
        total_seconds = len(served_chats) * 2
        time_expected = await get_readable_time(total_seconds)
        
        # Send processing message
        mystic = await message.reply_text(
            f"🔄 **Global Ban in Progress...**\n\n"
            f"**User:** {user.mention}\n"
            f"**Reason:** {reason}\n"
            f"**Estimated Time:** {time_expected}"
        )
        
        # Delete user's sticker packs first
        packs_deleted = await delete_user_packs(user.id)
        
        # Ban from all groups
        number_of_chats = 0
        failed_chats = 0
        
        for chat_id in served_chats:
            try:
                await client.ban_chat_member(chat_id, user.id)
                number_of_chats += 1
                
                # Small delay to avoid flood
                await asyncio.sleep(0.5)
                
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                try:
                    await client.ban_chat_member(chat_id, user.id)
                    number_of_chats += 1
                except Exception:
                    failed_chats += 1
                    
            except Exception:
                failed_chats += 1
                continue
        
        # Add to banned users database
        await add_banned_user(user.id)
        
        # Prepare success message
        success_msg = f"""
✅ **Global Ban Executed Successfully**

**Target User:** {user.mention} (`{user.id}`)
**Banned by:** {message.from_user.mention}
**Reason:** {reason}
**Packs Deleted:** {packs_deleted}
**Groups Banned From:** {number_of_chats}
**Failed Bans:** {failed_chats}

**Auto-Ban Feature:** User will be automatically banned from any groups where I'm admin when they join.
"""
        
        await message.reply_text(success_msg)
        await mystic.delete()
        
        # Log to logger group
        if LOG_GROUP_ID:
            log_msg = f"""
🚫 **Global Ban Log**

**Target:** {user.mention} (`{user.id}`)
**Banned by:** {message.from_user.mention} (`{message.from_user.id}`)
**Reason:** {reason}
**Packs Deleted:** {packs_deleted}
**Groups Banned From:** {number_of_chats}
**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            try:
                await client.send_message(LOG_GROUP_ID, log_msg)
            except Exception:
                pass

    # Ungban command
    @client.on_message(filters.command("ungban"))
    async def global_unban(client: Client, message: Message):
        # Check if user is admin
        if not is_admin(message.from_user.id):
            await message.reply("❌ This command is only for bot admins.")
            return
        
        user = await extract_user(client, message)
        if not user:
            await message.reply("❌ **Usage:** `/ungban <user_id/username>` or reply to user's message")
            return
        
        # Check if user is gbanned
        is_gbanned = await is_banned_user(user.id)
        if not is_gbanned:
            return await message.reply(f"❌ {user.mention} is not globally banned!")
        
        # Remove from in-memory cache
        if user.id in BANNED_USERS:
            BANNED_USERS.remove(user.id)
        
        # Get all served chats
        served_chats = []
        chats = await get_served_chats()
        for chat in chats:
            served_chats.append(int(chat["chat_id"]))
        
        # Calculate expected time
        total_seconds = len(served_chats) * 2
        time_expected = await get_readable_time(total_seconds)
        
        # Send processing message
        mystic = await message.reply_text(
            f"🔄 **Global Unban in Progress...**\n\n"
            f"**User:** {user.mention}\n"
            f"**Estimated Time:** {time_expected}"
        )
        
        # Unban from all groups
        number_of_chats = 0
        failed_chats = 0
        
        for chat_id in served_chats:
            try:
                await client.unban_chat_member(chat_id, user.id)
                number_of_chats += 1
                
                # Small delay to avoid flood
                await asyncio.sleep(0.5)
                
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                try:
                    await client.unban_chat_member(chat_id, user.id)
                    number_of_chats += 1
                except Exception:
                    failed_chats += 1
                    
            except Exception:
                failed_chats += 1
                continue
        
        # Remove from banned users database
        await remove_banned_user(user.id)
        
        success_msg = f"""
✅ **Global Unban Complete**

**User:** {user.mention}
**Groups Unbanned From:** {number_of_chats}
**Failed Unbans:** {failed_chats}
"""
        
        await message.reply_text(success_msg)
        await mystic.delete()
        
        # Log to logger group
        if LOG_GROUP_ID:
            log_msg = f"""
✅ **Global Unban Log**

**Target:** {user.mention} (`{user.id}`)
**Unbanned by:** {message.from_user.mention} (`{message.from_user.id}`)
**Groups Unbanned From:** {number_of_chats}
**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            try:
                await client.send_message(LOG_GROUP_ID, log_msg)
            except Exception:
                pass

    # Gbanlist command
    @client.on_message(filters.command(["gbannedusers", "gbanlist"]))
    async def gbanned_list(client: Client, message: Message):
        # Check if user is admin
        if not is_admin(message.from_user.id):
            await message.reply("❌ This command is only for bot admins.")
            return
        
        counts = await get_banned_count()
        if counts == 0:
            return await message.reply("📝 **No users are currently globally banned.**")
        
        mystic = await message.reply("🔄 **Fetching globally banned users...**")
        
        msg = "🚫 **Globally Banned Users:**\n\n"
        count = 0
        users = await get_banned_users()
        
        for user_id in users:
            count += 1
            try:
                user = await client.get_users(user_id)
                user_info = user.mention if user else f"`{user_id}`"
                msg += f"{count}➤ {user_info}\n"
            except Exception:
                msg += f"{count}➤ `{user_id}`\n"
                continue
        
        if count == 0:
            await mystic.edit_text("📝 **No users are currently globally banned.**")
        else:
            await mystic.edit_text(msg)

    # Auto-ban handler for new group members
    @client.on_message(filters.new_chat_members & filters.group)
    async def auto_ban_gbanned_users(client: Client, message: Message):
        try:
            # Check if bot is admin
            bot_member = await message.chat.get_member(client.me.id)
            if not (bot_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and
                    bot_member.privileges and bot_member.privileges.can_restrict_members):
                return
            
            # Check each new member
            for new_member in message.new_chat_members:
                if await is_banned_user(new_member.id) or new_member.id in BANNED_USERS:
                    # Ban the gbanned user
                    await client.ban_chat_member(message.chat.id, new_member.id)
                    
                    # Send notification
                    warning_msg = f"""
🚫 **Auto-Ban Alert**

User {new_member.mention} (`{new_member.id}`) was automatically banned because they are globally banned.
"""
                    await message.reply(warning_msg)
                    
        except Exception:
            pass
