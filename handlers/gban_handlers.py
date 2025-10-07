import asyncio
import logging
from datetime import datetime
from aiogram import Router, Bot, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.enums import ChatMemberStatus

from config import is_owner, LOG_GROUP_ID
from database import (
    add_banned_user, remove_banned_user, get_banned_count, get_banned_users,
    get_served_chats, is_banned_user, delete_user_packs
)

logger = logging.getLogger(__name__)
router = Router()

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

async def extract_user_info(bot: Bot, message: Message):
    """Extract user from message (reply or command arguments)"""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    
    if len(message.text.split()) > 1:
        user_input = message.text.split()[1]
        try:
            if user_input.isdigit():
                user_id = int(user_input)
                user = await bot.get_chat(user_id)
                return user
            else:
                username = user_input.lstrip('@')
                # Try to get user by username
                # Note: This might not work for all cases in Aiogram
                # We'll use a different approach
                return None
        except Exception as e:
            logger.error(f"Error extracting user: {e}")
            return None
    
    return None

async def ban_user_from_chat(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Ban user from specific chat"""
    try:
        await bot.ban_chat_member(chat_id, user_id)
        return True
    except Exception as e:
        logger.error(f"Failed to ban user {user_id} from chat {chat_id}: {e}")
        return False

async def unban_user_from_chat(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Unban user from specific chat"""
    try:
        await bot.unban_chat_member(chat_id, user_id)
        return True
    except Exception as e:
        logger.error(f"Failed to unban user {user_id} from chat {chat_id}: {e}")
        return False

@router.message(Command(["gban", "globalban"]))
async def global_ban(message: Message, bot: Bot):
    """Handle GBan command - Aiogram version"""
    # Check if user is owner
    if not is_owner(message.from_user.id):
        await message.reply("❌ This command is only for bot owners.")
        return
    
    user = await extract_user_info(bot, message)
    if not user:
        await message.reply("❌ **Usage:** `/gban <user_id> [reason]` or reply to user's message")
        return
    
    if user.id == message.from_user.id:
        return await message.reply("❌ You cannot gban yourself!")
    elif user.id == bot.id:
        return await message.reply("❌ I cannot gban myself!")
    elif is_owner(user.id):
        return await message.reply("❌ Cannot gban another owner!")
    
    # Check if already gbanned
    is_gbanned = await is_banned_user(user.id)
    if is_gbanned:
        return await message.reply(f"❌ {user.first_name} is already globally banned!")
    
    # Extract reason
    reason = "No reason provided"
    command_parts = message.text.split()
    if len(command_parts) > 2:
        reason = " ".join(command_parts[2:])
    
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
    processing_msg = await message.reply(
        f"🔄 **Global Ban in Progress...**\n\n"
        f"**User:** {user.first_name}\n"
        f"**Reason:** {reason}\n"
        f"**Estimated Time:** {time_expected}\n\n"
        f"*This will run in background. Bot will remain responsive.*"
    )
    
    # Run GBan in background without blocking
    asyncio.create_task(
        execute_gban_background(bot, user, message.from_user, reason, processing_msg, served_chats)
    )

async def execute_gban_background(bot: Bot, target_user, banned_by, reason, processing_msg, served_chats):
    """Execute GBan in background without blocking"""
    try:
        # Delete user's sticker packs first
        packs_deleted = await delete_user_packs(target_user.id)
        
        # Ban from all groups
        number_of_chats = 0
        failed_chats = 0
        
        for chat_id in served_chats:
            try:
                success = await ban_user_from_chat(bot, chat_id, target_user.id)
                if success:
                    number_of_chats += 1
                
                # Small delay to avoid flood
                await asyncio.sleep(0.3)
                
            except Exception:
                failed_chats += 1
                continue
        
        # Add to banned users database
        await add_banned_user(target_user.id)
        
        # Prepare success message
        success_msg = f"""
✅ **Global Ban Executed Successfully**

**Target User:** {target_user.first_name} (`{target_user.id}`)
**Banned by:** {banned_by.first_name}
**Reason:** {reason}
**Packs Deleted:** {packs_deleted}
**Groups Banned From:** {number_of_chats}
**Failed Bans:** {failed_chats}

**Auto-Ban Feature:** User will be automatically banned from any groups where I'm admin when they join.
"""
        
        await processing_msg.edit_text(success_msg)
        
        # Log to logger group
        if LOG_GROUP_ID:
            log_msg = f"""
🚫 **Global Ban Log**

**Target:** {target_user.first_name} (`{target_user.id}`)
**Banned by:** {banned_by.first_name} (`{banned_by.id}`)
**Reason:** {reason}
**Packs Deleted:** {packs_deleted}
**Groups Banned From:** {number_of_chats}
**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            try:
                await bot.send_message(LOG_GROUP_ID, log_msg)
            except Exception:
                pass
                
    except Exception as e:
        logger.error(f"Error in background GBan: {e}")
        await processing_msg.edit_text(f"❌ Error in GBan process: {e}")

@router.message(Command("ungban"))
async def global_unban(message: Message, bot: Bot):
    """Handle Ungban command - Aiogram version"""
    # Check if user is owner
    if not is_owner(message.from_user.id):
        await message.reply("❌ This command is only for bot owners.")
        return
    
    user = await extract_user_info(bot, message)
    if not user:
        await message.reply("❌ **Usage:** `/ungban <user_id>` or reply to user's message")
        return
    
    # Check if user is gbanned
    is_gbanned = await is_banned_user(user.id)
    if not is_gbanned:
        return await message.reply(f"❌ {user.first_name} is not globally banned!")
    
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
    processing_msg = await message.reply(
        f"🔄 **Global Unban in Progress...**\n\n"
        f"**User:** {user.first_name}\n"
        f"**Estimated Time:** {time_expected}\n\n"
        f"*This will run in background. Bot will remain responsive.*"
    )
    
    # Run UnGBan in background without blocking
    asyncio.create_task(
        execute_ungban_background(bot, user, message.from_user, processing_msg, served_chats)
    )

async def execute_ungban_background(bot: Bot, target_user, unbanned_by, processing_msg, served_chats):
    """Execute UnGBan in background without blocking"""
    try:
        # Unban from all groups
        number_of_chats = 0
        failed_chats = 0
        
        for chat_id in served_chats:
            try:
                success = await unban_user_from_chat(bot, chat_id, target_user.id)
                if success:
                    number_of_chats += 1
                
                # Small delay to avoid flood
                await asyncio.sleep(0.3)
                
            except Exception:
                failed_chats += 1
                continue
        
        # Remove from banned users database
        await remove_banned_user(target_user.id)
        
        success_msg = f"""
✅ **Global Unban Complete**

**User:** {target_user.first_name}
**Groups Unbanned From:** {number_of_chats}
**Failed Unbans:** {failed_chats}
"""
        
        await processing_msg.edit_text(success_msg)
        
        # Log to logger group
        if LOG_GROUP_ID:
            log_msg = f"""
✅ **Global Unban Log**

**Target:** {target_user.first_name} (`{target_user.id}`)
**Unbanned by:** {unbanned_by.first_name} (`{unbanned_by.id}`)
**Groups Unbanned From:** {number_of_chats}
**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
            try:
                await bot.send_message(LOG_GROUP_ID, log_msg)
            except Exception:
                pass
                
    except Exception as e:
        logger.error(f"Error in background UnGBan: {e}")
        await processing_msg.edit_text(f"❌ Error in UnGBan process: {e}")

@router.message(Command(["gbannedusers", "gbanlist"]))
async def gbanned_list(message: Message, bot: Bot):
    """Show list of globally banned users"""
    # Check if user is owner
    if not is_owner(message.from_user.id):
        await message.reply("❌ This command is only for bot owners.")
        return
    
    counts = await get_banned_count()
    if counts == 0:
        return await message.reply("📝 **No users are currently globally banned.**")
    
    processing_msg = await message.reply("🔄 **Fetching globally banned users...**")
    
    msg = "🚫 **Globally Banned Users:**\n\n"
    count = 0
    users = await get_banned_users()
    
    for user_id in users:
        count += 1
        try:
            user = await bot.get_chat(user_id)
            user_info = user.first_name if user else f"`{user_id}`"
            msg += f"{count}➤ {user_info} (`{user_id}`)\n"
        except Exception:
            msg += f"{count}➤ `{user_id}`\n"
            continue
    
    if count == 0:
        await processing_msg.edit_text("📝 **No users are currently globally banned.**")
    else:
        await processing_msg.edit_text(msg)

@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def auto_ban_gbanned_users(event: ChatMemberUpdated, bot: Bot):
    """Auto-ban GBanned users when they join groups"""
    try:
        # Check if the new member is not the bot itself
        if event.new_chat_member.user.id == bot.id:
            return
        
        # Check if bot is admin
        bot_member = await bot.get_chat_member(event.chat.id, bot.id)
        if not (bot_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and
                bot_member.can_restrict_members):
            return
        
        user_id = event.new_chat_member.user.id
        
        # Check if user is GBanned
        if await is_banned_user(user_id) or user_id in BANNED_USERS:
            # Ban the GBanned user
            await bot.ban_chat_member(event.chat.id, user_id)
            
            # Send notification
            warning_msg = f"""
🚫 **Auto-Ban Alert**

User {event.new_chat_member.user.first_name} (`{user_id}`) was automatically banned because they are globally banned.
"""
            await event.answer(warning_msg)
            
    except Exception as e:
        logger.error(f"Error in auto-ban: {e}")
