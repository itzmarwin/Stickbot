import logging
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus, ChatType

from config import is_owner, BOT_USERNAME, LOG_GROUP_ID
from database import get_user_pack, db

logger = logging.getLogger(__name__)

# GBan data storage
gban_cache = {}

async def gban_user(client: Client, user_id: int, reason: str, banned_by: int):
    """
    Global ban a user across all groups where bot is admin
    """
    try:
        logger.info(f"🚀 Starting GBan process for user {user_id}")
        
        # Store GBan info
        gban_data = {
            "user_id": user_id,
            "reason": reason,
            "banned_by": banned_by,
            "banned_at": datetime.utcnow(),
            "packs_deleted": 0,
            "groups_banned": 0
        }
        
        # Step 1: Delete all user's sticker packs
        logger.info(f"🗑️ Deleting packs for user {user_id}")
        packs_deleted = await delete_user_packs(user_id)
        gban_data["packs_deleted"] = packs_deleted
        logger.info(f"✅ Deleted {packs_deleted} packs")
        
        # Step 2: Ban from all groups where bot is admin
        logger.info(f"🔨 Banning user {user_id} from groups")
        groups_banned = await ban_from_groups(client, user_id)
        gban_data["groups_banned"] = groups_banned
        logger.info(f"✅ Banned from {groups_banned} groups")
        
        # Save to database
        await db.gbans.update_one(
            {"user_id": user_id},
            {"$set": gban_data},
            upsert=True
        )
        
        # Update cache
        gban_cache[user_id] = gban_data
        
        logger.info(f"🎯 GBan completed for user {user_id}")
        return gban_data
        
    except Exception as e:
        logger.error(f"❌ Error in gban_user: {e}")
        return None

async def delete_user_packs(user_id: int) -> int:
    """
    Delete all sticker packs created by user
    """
    try:
        # Get all packs by user
        packs_cursor = db.sticker_packs.find({"user_id": user_id})
        packs = await packs_cursor.to_list(length=None)
        
        deleted_count = len(packs)
        
        for pack in packs:
            # Remove from database
            await db.sticker_packs.delete_one({"_id": pack["_id"]})
            logger.debug(f"🗑️ Deleted pack: {pack.get('pack_name', 'Unknown')}")
            
        return deleted_count
    except Exception as e:
        logger.error(f"❌ Error deleting user packs: {e}")
        return 0

async def ban_from_groups(client: Client, user_id: int) -> int:
    """
    Ban user from all groups where bot has admin rights
    """
    try:
        banned_count = 0
        total_chats = 0
        
        logger.info("🔍 Scanning groups for banning...")
        
        async for dialog in client.get_dialogs():
            try:
                if dialog.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
                    total_chats += 1
                    
                    # Check if bot is admin and has ban rights
                    bot_member = await dialog.chat.get_member(client.me.id)
                    
                    can_ban = (bot_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and
                              bot_member.privileges and bot_member.privileges.can_restrict_members)
                    
                    if can_ban:
                        # Try to ban user
                        try:
                            await client.ban_chat_member(dialog.chat.id, user_id)
                            banned_count += 1
                            logger.info(f"✅ Banned {user_id} from {dialog.chat.title}")
                            
                            # Small delay to avoid flood
                            await asyncio.sleep(0.3)
                            
                        except Exception as ban_error:
                            logger.debug(f"⚠️ Could not ban in {dialog.chat.title}: {ban_error}")
                            continue
                    else:
                        logger.debug(f"⏭️ No ban rights in {dialog.chat.title}")
                            
            except Exception as e:
                logger.debug(f"⚠️ Error processing chat {getattr(dialog.chat, 'title', 'Unknown')}: {e}")
                continue
                
        logger.info(f"📊 Banned from {banned_count}/{total_chats} groups")
        return banned_count
        
    except Exception as e:
        logger.error(f"❌ Error in ban_from_groups: {e}")
        return 0

async def is_user_gbanned(user_id: int) -> bool:
    """Check if user is globally banned"""
    # Check cache first
    if user_id in gban_cache:
        return True
    
    # Check database
    gban_data = await db.gbans.find_one({"user_id": user_id})
    if gban_data:
        gban_cache[user_id] = gban_data
        return True
    
    return False

async def setup_gban_handlers(client: Client):
    """Setup GBan command handlers"""
    
    logger.info("🔧 Setting up GBan handlers...")
    
    @client.on_message(filters.command("gban") & filters.group)
    async def gban_command(client: Client, message: Message):
        logger.info(f"📨 GBan command received from {message.from_user.id}")
        
        # Check if user is owner
        if not is_owner(message.from_user.id):
            logger.warning(f"🚫 Non-owner {message.from_user.id} tried to use GBan")
            await message.reply("❌ This command is only for bot owners.")
            return
        
        logger.info(f"✅ Owner {message.from_user.id} using GBan")
        
        # Extract target user
        target_user = None
        reason = "No reason provided"
        
        # Check if replying to message
        if message.reply_to_message:
            target_user = message.reply_to_message.from_user
            # Extract reason from command arguments
            if len(message.command) > 1:
                reason = " ".join(message.command[1:])
            logger.info(f"🎯 GBan via reply to user {target_user.id}")
        else:
            # Extract from command arguments
            if len(message.command) < 2:
                await message.reply("❌ Usage: `/gban <user_id/username> [reason]` or reply to user's message")
                return
            
            user_input = message.command[1]
            logger.info(f"🎯 GBan via argument: {user_input}")
            
            # Try to resolve user input
            try:
                if user_input.isdigit():
                    target_user = await client.get_users(int(user_input))
                else:
                    username = user_input.lstrip('@')
                    target_user = await client.get_users(username)
                    
                # Extract reason
                if len(message.command) > 2:
                    reason = " ".join(message.command[2:])
                    
            except Exception as e:
                logger.error(f"❌ Could not find user {user_input}: {e}")
                await message.reply(f"❌ Could not find user: {user_input}")
                return
        
        if not target_user:
            await message.reply("❌ Could not identify target user.")
            return
        
        # Prevent self-gban
        if target_user.id == client.me.id:
            await message.reply("❌ I cannot ban myself!")
            return
        
        # Prevent owner-gban
        if is_owner(target_user.id):
            await message.reply("❌ Cannot ban another owner!")
            return
        
        logger.info(f"🚀 Starting GBan for {target_user.id} ({target_user.first_name})")
        
        # Send processing message
        processing_msg = await message.reply(f"🔄 Globally banning {target_user.mention}...")
        
        # Execute GBan
        gban_result = await gban_user(client, target_user.id, reason, message.from_user.id)
        
        if gban_result:
            # Prepare report
            report_msg = f"""
✅ **Global Ban Executed**

**User:** {target_user.mention} (`{target_user.id}`)
**Reason:** {reason}
**Banned by:** {message.from_user.mention}

**Actions Taken:**
• Deleted {gban_result['packs_deleted']} sticker packs
• Banned from {gban_result['groups_banned']} groups
• Added to global ban list

User will be automatically banned from any new groups where I'm added as admin.
"""
            
            await processing_msg.edit_text(report_msg)
            
            # Log to logger group
            if LOG_GROUP_ID:
                log_msg = f"""
🚫 **Global Ban Log**

**Target:** {target_user.mention} (`{target_user.id}`)
**Banned by:** {message.from_user.mention} (`{message.from_user.id}`)
**Reason:** {reason}
**Packs deleted:** {gban_result['packs_deleted']}
**Groups banned:** {gban_result['groups_banned']}
**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                try:
                    await client.send_message(LOG_GROUP_ID, log_msg)
                except Exception as e:
                    logger.error(f"❌ Could not send log to LOG_GROUP: {e}")
        else:
            await processing_msg.edit_text("❌ Failed to execute global ban. Check logs for details.")

    @client.on_message(filters.command("ungban") & filters.group)
    async def ungban_command(client: Client, message: Message):
        logger.info(f"📨 Ungban command received from {message.from_user.id}")
        
        # Check if user is owner
        if not is_owner(message.from_user.id):
            await message.reply("❌ This command is only for bot owners.")
            return
        
        # Extract target user
        if len(message.command) < 2:
            await message.reply("❌ Usage: `/ungban <user_id>`")
            return
        
        user_input = message.command[1]
        
        try:
            if user_input.isdigit():
                user_id = int(user_input)
            else:
                await message.reply("❌ Please provide a valid user ID.")
                return
        except ValueError:
            await message.reply("❌ Invalid user ID.")
            return
        
        # Check if user is actually gbanned
        if not await is_user_gbanned(user_id):
            await message.reply("❌ This user is not globally banned.")
            return
        
        # Execute unban
        processing_msg = await message.reply(f"🔄 Removing global ban for user ID: {user_id}...")
        
        try:
            # Remove from database
            await db.gbans.delete_one({"user_id": user_id})
            # Remove from cache
            gban_cache.pop(user_id, None)
            
            await processing_msg.edit_text(f"✅ Global ban removed for user ID: {user_id}")
            logger.info(f"✅ Removed GBan for user {user_id}")
            
            # Log to logger group
            if LOG_GROUP_ID:
                log_msg = f"""
✅ **Global Unban Log**

**Target User ID:** {user_id}
**Unbanned by:** {message.from_user.mention} (`{message.from_user.id}`)
**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
                await client.send_message(LOG_GROUP_ID, log_msg)
                
        except Exception as e:
            logger.error(f"❌ Error in ungban: {e}")
            await processing_msg.edit_text("❌ Failed to remove global ban.")

    @client.on_message(filters.command("gbanlist") & filters.group)
    async def gbanlist_command(client: Client, message: Message):
        logger.info(f"📨 Gbanlist command received from {message.from_user.id}")
        
        # Check if user is owner
        if not is_owner(message.from_user.id):
            await message.reply("❌ This command is only for bot owners.")
            return
        
        # Get all gbanned users
        gbanned_users = []
        async for gban in db.gbans.find():
            gbanned_users.append(gban)
        
        if not gbanned_users:
            await message.reply("📝 No users are currently globally banned.")
            return
        
        # Format list
        list_text = "🚫 **Globally Banned Users:**\n\n"
        
        for i, gban in enumerate(gbanned_users, 1):
            try:
                user = await client.get_users(gban["user_id"])
                user_info = f"{user.mention} (`{user.id}`)"
            except:
                user_info = f"`{gban['user_id']}`"
            
            list_text += f"{i}. {user_info}\n"
            list_text += f"   **Reason:** {gban.get('reason', 'No reason')}\n"
            list_text += f"   **Banned on:** {gban['banned_at'].strftime('%Y-%m-%d')}\n"
            list_text += f"   **Packs deleted:** {gban.get('packs_deleted', 0)}\n"
            list_text += f"   **Groups banned:** {gban.get('groups_banned', 0)}\n\n"
        
        # Split if too long
        if len(list_text) > 4000:
            parts = [list_text[i:i+4000] for i in range(0, len(list_text), 4000)]
            for part in parts:
                await message.reply(part)
        else:
            await message.reply(list_text)

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
                if await is_user_gbanned(new_member.id):
                    # Ban the gbanned user
                    await client.ban_chat_member(message.chat.id, new_member.id)
                    logger.info(f"🤖 Auto-banned gbanned user {new_member.id} from {message.chat.title}")
                    
                    # Send notification
                    warning_msg = f"""
🚫 **Auto-Ban Alert**

User {new_member.mention} (`{new_member.id}`) was automatically banned because they are globally banned.

**Reason:** {gban_cache.get(new_member.id, {}).get('reason', 'No reason provided')}
"""
                    await message.reply(warning_msg)
                    
        except Exception as e:
            logger.error(f"❌ Error in auto-ban: {e}")

    logger.info("✅ GBan handlers setup complete")
