import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums import ChatMemberStatus, ChatType

from config import is_owner, BOT_USERNAME, LOG_GROUP_ID
from database import (
    add_banned_user, remove_banned_user, get_banned_count, get_banned_users,
    get_served_chats, is_banned_user, delete_user_packs, add_served_chat, remove_served_chat
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

async def extract_user(message: Message):
    """Extract user from message (reply or command arguments)"""
    if message.reply_to_message:
        return message.reply_to_message.from_user
    
    if len(message.command) > 1:
        user_input = message.command[1]
        try:
            if user_input.isdigit():
                user_id = int(user_input)
                user = await message._client.get_users(user_id)
                return user
            else:
                username = user_input.lstrip('@')
                user = await message._client.get_users(username)
                return user
        except Exception as e:
            logger.error(f"Error extracting user: {e}")
            return None
    
    return None

async def setup_gban_handlers(client: Client):
    """Setup GBan command handlers"""
    
    logger.info("🔧 Setting up new GBan handlers...")
    
    # GBan command
    @client.on_message(filters.command(["gban", "globalban"]) & filters.user(is_owner))
    async def global_ban(client: Client, message: Message):
        if not message.reply_to_message:
            if len(message.command) != 2:
                return await message.reply_text("❌ **Usage:** `/gban <user_id/username> [reason]` or reply to user's message")
        
        user = await extract_user(message)
        if not user:
            return await message.reply_text("❌ Could not identify target user.")
        
        if user.id == message.from_user.id:
            return await message.reply_text("❌ You cannot gban yourself!")
        elif user.id == client.me.id:
            return await message.reply_text("❌ I cannot gban myself!")
        elif is_owner(user.id):
            return await message.reply_text("❌ Cannot gban another owner!")
        
        # Check if already gbanned
        is_gbanned = await is_banned_user(user.id)
        if is_gbanned:
            return await message.reply_text(f"❌ {user.mention} is already globally banned!")
        
        # Add to in-memory cache
        BANNED_USERS.add(user.id)
        
        # Get all served chats
        served_chats = []
        chats = await get_served_chats()
        for chat in chats:
            served_chats.append(int(chat["chat_id"]))
        
        # Calculate expected time
        time_expected = await get_readable_time(len(served_chats))
        
        # Send processing message
        mystic = await message.reply_text(f"🔄 **Global Ban in Progress...**\n\n**User:** {user.mention}\n**Estimated Time:** {time_expected}")
        
        # Delete user's sticker packs first
        packs_deleted = await delete_user_packs(user.id)
        logger.info(f"🗑️ Deleted {packs_deleted} packs for user {user.id}")
        
        # Ban from all groups
        number_of_chats = 0
        for chat_id in served_chats:
            try:
                await client.ban_chat_member(chat_id, user.id)
                number_of_chats += 1
            except FloodWait as fw:
                await asyncio.sleep(int(fw.value))
                try:
                    await client.ban_chat_member(chat_id, user.id)
                    number_of_chats += 1
                except:
                    continue
            except Exception as e:
                logger.debug(f"Could not ban from {chat_id}: {e}")
                continue
        
        # Add to banned users database
        await add_banned_user(user.id)
        
        # Prepare success message
        success_msg = f"""
✅ **Global Ban Executed Successfully**

**Target User:** {user.mention} (`{user.id}`)
**Banned by:** {message.from_user.mention}
**Packs Deleted:** {packs_deleted}
**Groups Banned From:** {number_of_chats}

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
**Packs Deleted:** {packs_deleted}
**Groups Banned From:** {number_of_chats}
**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            try:
                await client.send_message(LOG_GROUP_ID, log_msg)
            except Exception as e:
                logger.error(f"Could not send log to LOG_GROUP: {e}")

    # Ungban command
    @client.on_message(filters.command("ungban") & filters.user(is_owner))
    async def global_unban(client: Client, message: Message):
        if not message.reply_to_message:
            if len(message.command) != 2:
                return await message.reply_text("❌ **Usage:** `/ungban <user_id/username>` or reply to user's message")
        
        user = await extract_user(message)
        if not user:
            return await message.reply_text("❌ Could not identify target user.")
        
        # Check if user is gbanned
        is_gbanned = await is_banned_user(user.id)
        if not is_gbanned:
            return await message.reply_text(f"❌ {user.mention} is not globally banned!")
        
        # Remove from in-memory cache
        if user.id in BANNED_USERS:
            BANNED_USERS.remove(user.id)
        
        # Get all served chats
        served_chats = []
        chats = await get_served_chats()
        for chat in chats:
            served_chats.append(int(chat["chat_id"]))
        
        # Calculate expected time
        time_expected = await get_readable_time(len(served_chats))
        
        # Send processing message
        mystic = await message.reply_text(f"🔄 **Global Unban in Progress...**\n\n**User:** {user.mention}\n**Estimated Time:** {time_expected}")
        
        # Unban from all groups
        number_of_chats = 0
        for chat_id in served_chats:
            try:
                await client.unban_chat_member(chat_id, user.id)
                number_of_chats += 1
            except FloodWait as fw:
                await asyncio.sleep(int(fw.value))
                try:
                    await client.unban_chat_member(chat_id, user.id)
                    number_of_chats += 1
                except:
                    continue
            except Exception as e:
                logger.debug(f"Could not unban from {chat_id}: {e}")
                continue
        
        # Remove from banned users database
        await remove_banned_user(user.id)
        
        await message.reply_text(f"✅ **Global Unban Complete**\n\n**User:** {user.mention}\n**Groups Unbanned From:** {number_of_chats}")
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
            except Exception as e:
                logger.error(f"Could not send log to LOG_GROUP: {e}")

    # Gbanlist command
    @client.on_message(filters.command(["gbannedusers", "gbanlist"]) & filters.user(is_owner))
    async def gbanned_list(client: Client, message: Message):
        counts = await get_banned_count()
        if counts == 0:
            return await message.reply_text("📝 **No users are currently globally banned.**")
        
        mystic = await message.reply_text("🔄 **Fetching globally banned users...**")
        
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

    # Auto-add groups to served chats when bot is added
    @client.on_message(filters.new_chat_members)
    async def add_new_chat(client: Client, message: Message):
        try:
            # Check if bot is in new members
            for member in message.new_chat_members:
                if member.id == client.me.id:
                    # Bot added to group, add to served chats
                    await add_served_chat(message.chat.id)
                    logger.info(f"✅ Added new chat to served chats: {message.chat.title} ({message.chat.id})")
                    break
        except Exception as e:
            logger.error(f"Error adding new chat: {e}")

    # Remove group from served chats when bot is removed
    @client.on_message(filters.left_chat_member)
    async def remove_chat(client: Client, message: Message):
        try:
            if message.left_chat_member.id == client.me.id:
                # Bot removed from group, remove from served chats
                await remove_served_chat(message.chat.id)
                logger.info(f"🗑️ Removed chat from served chats: {message.chat.title} ({message.chat.id})")
        except Exception as e:
            logger.error(f"Error removing chat: {e}")

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
                    logger.info(f"🤖 Auto-banned gbanned user {new_member.id} from {message.chat.title}")
                    
                    # Send notification
                    warning_msg = f"""
🚫 **Auto-Ban Alert**

User {new_member.mention} (`{new_member.id}`) was automatically banned because they are globally banned.
"""
                    await message.reply(warning_msg)
                    
        except Exception as e:
            logger.error(f"Error in auto-ban: {e}")

    logger.info("✅ New GBan handlers setup complete")
