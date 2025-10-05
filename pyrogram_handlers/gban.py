import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums import ChatMemberStatus

from config import is_owner, LOG_GROUP_ID
from database import get_db, get_served_chats, add_banned_user, remove_banned_user, is_user_gbanned, get_banned_count, get_banned_users

logger = logging.getLogger(__name__)

# In-memory banned users set for fast access
BANNED_USERS = set()

async def load_banned_users():
    """Load banned users from database to memory"""
    try:
        db = get_db()
        if db:
            users = await get_banned_users()
            BANNED_USERS.clear()
            for user in users:
                BANNED_USERS.add(user["user_id"])
        logger.info(f"✅ Loaded {len(BANNED_USERS)} banned users to memory")
    except Exception as e:
        logger.error(f"❌ Error loading banned users: {e}")

def get_readable_time(seconds: int) -> str:
    """Convert seconds to human readable time"""
    periods = [
        ('year', 60*60*24*365),
        ('month', 60*60*24*30),
        ('day', 60*60*24),
        ('hour', 60*60),
        ('minute', 60),
        ('second', 1)
    ]
    
    result = []
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            if period_value == 1:
                result.append(f"{period_value} {period_name}")
            else:
                result.append(f"{period_value} {period_name}s")
    
    return ', '.join(result) if result else "0 seconds"

async def extract_user(message: Message):
    """Extract user from message"""
    try:
        if message.reply_to_message:
            return message.reply_to_message.from_user
        elif len(message.command) > 1:
            user_input = message.command[1]
            if user_input.isdigit():
                return await message._client.get_users(int(user_input))
            else:
                return await message._client.get_users(user_input.lstrip('@'))
    except Exception as e:
        logger.error(f"Error extracting user: {e}")
        return None

async def setup_gban_handlers(client: Client):
    """Setup GBan command handlers"""
    
    logger.info("🔧 Setting up GBan handlers...")
    
    # Load banned users on startup
    await load_banned_users()
    
    @client.on_message(filters.command(["gban", "globalban"]) & filters.group)
    async def global_ban(client: Client, message: Message):
        """Handle /gban command"""
        # Check if user is owner
        if not is_owner(message.from_user.id):
            await message.reply("❌ This command is only for bot owners.")
            return
        
        # Extract user
        user = await extract_user(message)
        if not user:
            await message.reply("❌ Please reply to a user or provide user ID/username.")
            return
        
        # Validation checks
        if user.id == message.from_user.id:
            await message.reply("❌ You can't gban yourself.")
            return
        elif user.id == client.me.id:
            await message.reply("❌ I can't gban myself.")
            return
        elif is_owner(user.id):
            await message.reply("❌ You can't gban another owner.")
            return
        
        # Check if already gbanned
        if await is_user_gbanned(user.id):
            await message.reply(f"❌ {user.mention} is already globally banned.")
            return
        
        # Add to in-memory set
        BANNED_USERS.add(user.id)
        
        # Get served chats
        served_chats = await get_served_chats()
        chat_ids = [int(chat["chat_id"]) for chat in served_chats]
        
        # Calculate expected time
        time_expected = get_readable_time(len(chat_ids))
        
        # Send processing message
        mystic = await message.reply(
            f"🚀 Starting global ban for {user.mention}\n"
            f"⏰ Estimated time: {time_expected}\n"
            f"📊 Total chats: {len(chat_ids)}"
        )
        
        # Ban from all served chats
        number_of_chats = 0
        for chat_id in chat_ids:
            try:
                await client.ban_chat_member(chat_id, user.id)
                number_of_chats += 1
            except FloodWait as fw:
                await asyncio.sleep(int(fw.value))
                # Retry after flood wait
                try:
                    await client.ban_chat_member(chat_id, user.id)
                    number_of_chats += 1
                except:
                    continue
            except:
                continue
        
        # Add to database
        await add_banned_user(user.id, f"Banned by {message.from_user.id}")
        
        # Send completion message
        result_text = (
            f"✅ **Global Ban Complete**\n\n"
            f"**User:** {user.mention} (`{user.id}`)\n"
            f"**Banned by:** {message.from_user.mention}\n"
            f"**Chats affected:** {number_of_chats}/{len(chat_ids)}\n"
            f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        await message.reply(result_text)
        await mystic.delete()
        
        # Log to logger group
        if LOG_GROUP_ID:
            log_text = (
                f"🚫 **Global Ban Executed**\n\n"
                f"**Target:** {user.mention} (`{user.id}`)\n"
                f"**Banned by:** {message.from_user.mention} (`{message.from_user.id}`)\n"
                f"**Chats banned:** {number_of_chats}\n"
                f"**Total chats:** {len(chat_ids)}\n"
                f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
            await client.send_message(LOG_GROUP_ID, log_text)

    @client.on_message(filters.command(["ungban"]) & filters.group)
    async def global_unban(client: Client, message: Message):
        """Handle /ungban command"""
        # Check if user is owner
        if not is_owner(message.from_user.id):
            await message.reply("❌ This command is only for bot owners.")
            return
        
        # Extract user
        user = await extract_user(message)
        if not user:
            await message.reply("❌ Please reply to a user or provide user ID/username.")
            return
        
        # Check if user is gbanned
        if not await is_user_gbanned(user.id):
            await message.reply(f"❌ {user.mention} is not globally banned.")
            return
        
        # Remove from in-memory set
        if user.id in BANNED_USERS:
            BANNED_USERS.remove(user.id)
        
        # Get served chats
        served_chats = await get_served_chats()
        chat_ids = [int(chat["chat_id"]) for chat in served_chats]
        
        # Calculate expected time
        time_expected = get_readable_time(len(chat_ids))
        
        # Send processing message
        mystic = await message.reply(
            f"🔄 Removing global ban for {user.mention}\n"
            f"⏰ Estimated time: {time_expected}\n"
            f"📊 Total chats: {len(chat_ids)}"
        )
        
        # Unban from all served chats
        number_of_chats = 0
        for chat_id in chat_ids:
            try:
                await client.unban_chat_member(chat_id, user.id)
                number_of_chats += 1
            except FloodWait as fw:
                await asyncio.sleep(int(fw.value))
                # Retry after flood wait
                try:
                    await client.unban_chat_member(chat_id, user.id)
                    number_of_chats += 1
                except:
                    continue
            except:
                continue
        
        # Remove from database
        await remove_banned_user(user.id)
        
        # Send completion message
        result_text = (
            f"✅ **Global Unban Complete**\n\n"
            f"**User:** {user.mention} (`{user.id}`)\n"
            f"**Unbanned by:** {message.from_user.mention}\n"
            f"**Chats affected:** {number_of_chats}/{len(chat_ids)}\n"
            f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        await message.reply(result_text)
        await mystic.delete()
        
        # Log to logger group
        if LOG_GROUP_ID:
            log_text = (
                f"✅ **Global Unban Executed**\n\n"
                f"**Target:** {user.mention} (`{user.id}`)\n"
                f"**Unbanned by:** {message.from_user.mention} (`{message.from_user.id}`)\n"
                f"**Chats unbanned:** {number_of_chats}\n"
                f"**Total chats:** {len(chat_ids)}\n"
                f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
            await client.send_message(LOG_GROUP_ID, log_text)

    @client.on_message(filters.command(["gbannedusers", "gbanlist"]) & filters.group)
    async def gbanned_list(client: Client, message: Message):
        """Handle /gbanlist command"""
        # Check if user is owner
        if not is_owner(message.from_user.id):
            await message.reply("❌ This command is only for bot owners.")
            return
        
        # Get banned count
        counts = await get_banned_count()
        if counts == 0:
            await message.reply("📝 No users are globally banned.")
            return
        
        # Get banned users
        users = await get_banned_users()
        
        # Format list
        msg = "🚫 **Globally Banned Users:**\n\n"
        count = 0
        
        for user_data in users:
            count += 1
            try:
                user = await client.get_users(user_data["user_id"])
                user_display = user.mention if user.mention else user.first_name
                msg += f"{count}➤ {user_display} (`{user.id}`)\n"
            except Exception:
                msg += f"{count}➤ `{user_data['user_id']}`\n"
                continue
        
        if count == 0:
            await message.reply("📝 No users are globally banned.")
        else:
            # Split if too long
            if len(msg) > 4000:
                parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
                for part in parts:
                    await message.reply(part)
            else:
                await message.reply(msg)

    # Auto-ban handler for new group members
    @client.on_message(filters.new_chat_members & filters.group)
    async def auto_ban_gbanned_users(client: Client, message: Message):
        """Auto-ban GBanned users when they join groups"""
        try:
            for new_member in message.new_chat_members:
                if new_member.id in BANNED_USERS or await is_user_gbanned(new_member.id):
                    # Ban the user
                    await client.ban_chat_member(message.chat.id, new_member.id)
                    
                    # Send notification
                    warning_msg = (
                        f"🚫 **Auto-Ban Alert**\n\n"
                        f"User {new_member.mention} was automatically banned "
                        f"because they are globally banned."
                    )
                    await message.reply(warning_msg)
                    logger.info(f"Auto-banned {new_member.id} from {message.chat.title}")
                    
        except Exception as e:
            logger.error(f"Error in auto-ban: {e}")

    # Auto-ban handler for messages from GBanned users
    @client.on_message(filters.group & filters.all)
    async def auto_ban_on_message(client: Client, message: Message):
        """Auto-ban GBanned users when they send messages"""
        try:
            if not message.from_user:
                return
            
            # Skip if message is from bot itself
            if message.from_user.id == client.me.id:
                return
            
            # Skip service messages
            if message.service:
                return
            
            # Check if user is GBanned
            if message.from_user.id in BANNED_USERS or await is_user_gbanned(message.from_user.id):
                # Ban the user
                await client.ban_chat_member(message.chat.id, message.from_user.id)
                
                # Try to delete the message
                try:
                    await message.delete()
                except:
                    pass
                
                # Send notification
                warning_msg = (
                    f"🚫 **Auto-Ban Alert**\n\n"
                    f"User {message.from_user.mention} was automatically banned "
                    f"because they are globally banned."
                )
                await message.reply(warning_msg)
                logger.info(f"Auto-banned {message.from_user.id} from {message.chat.title} on message")
                    
        except Exception as e:
            logger.error(f"Error in auto-ban on message: {e}")

    logger.info("✅ GBan handlers setup complete")
