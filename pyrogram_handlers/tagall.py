
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

# Configuration
BATCH_SIZE = 5  # 5 users per message
DELAY_BETWEEN_BATCHES = 2  # 2 seconds delay (increased to avoid FloodWait)
MAX_RETRIES = 3  # Maximum retry attempts for FloodWait


async def get_all_members(client: Client, chat_id: int) -> list:
    """
    Fetch all non-bot members from group
    
    Args:
        client: Pyrogram client
        chat_id: Group chat ID
        
    Returns:
        List of user objects (excluding bots)
    """
    members = []
    try:
        async for member in client.get_chat_members(chat_id):
            # Skip bot accounts
            if not member.user.is_bot:
                members.append(member.user)
    except Exception as e:
        logger.error(f"Error fetching members from {chat_id}: {e}")
    
    return members


async def send_mention_batch(message_target, mentions: str, retry_count: int = 0):
    """
    Send mention batch with FloodWait retry mechanism
    
    Args:
        message_target: Message object to reply to
        mentions: Mention text to send
        retry_count: Current retry attempt
        
    Returns:
        bool: True if successful, False if failed after retries
    """
    try:
        await message_target.reply_text(
            mentions,
            disable_web_page_preview=True
        )
        return True
        
    except FloodWait as e:
        wait_time = e.value
        logger.warning(f"FloodWait: Need to wait {wait_time} seconds (Retry {retry_count + 1}/{MAX_RETRIES})")
        
        if retry_count >= MAX_RETRIES:
            logger.error(f"Max retries reached. Giving up after {MAX_RETRIES} attempts.")
            return False
        
        # Wait as required by Telegram + 1 extra second
        await asyncio.sleep(wait_time + 1)
        
        # Retry with incremented counter
        return await send_mention_batch(message_target, mentions, retry_count + 1)
        
    except Exception as e:
        logger.error(f"Error sending mention batch: {e}")
        return False


async def setup_tagall_handlers(client: Client):
    """Setup tagall command handlers"""
    
    @client.on_message(filters.command(["tagall", "all"]) & filters.group)
    async def tagall_command(client: Client, message: Message):
        """
        Handle /tagall and /all commands
        
        Mode 1: Reply to message - tags in reply to that message
        Mode 2: With text - tags with custom header repeated in each batch
        """
        try:
            chat_id = message.chat.id
            
            # ✅ Admin-only check - Only group admins can use this command
            try:
                member = await client.get_chat_member(chat_id, message.from_user.id)
                if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                    await message.reply_text(
                        "⚠️ **Admin Only Command**\n\n"
                        "Only group admins can use /tagall and /all commands."
                    )
                    return
            except Exception as e:
                logger.error(f"Error checking admin status: {e}")
                await message.reply_text("❌ Unable to verify admin status. Please try again.")
                return
            
            # Fetch group members
            progress_msg = await message.reply_text("🔄 Fetching members...")
            members = await get_all_members(client, chat_id)
            
            if not members:
                await progress_msg.edit_text("❌ No members found or unable to fetch members!")
                return
            
            # Check if replying to a message
            is_reply = message.reply_to_message is not None
            
            # Mode 1: Reply to message mode
            if is_reply:
                original_message = message.reply_to_message
                await progress_msg.delete()
                
                total_batches = (len(members) + BATCH_SIZE - 1) // BATCH_SIZE
                successful = 0
                failed = 0
                
                # Divide members into batches of 5
                for i in range(0, len(members), BATCH_SIZE):
                    batch = members[i:i + BATCH_SIZE]
                    batch_number = (i // BATCH_SIZE) + 1
                    
                    # Create blue text mentions (clickable)
                    mentions = " ".join([
                        f"[{user.first_name}](tg://user?id={user.id})"
                        for user in batch
                    ])
                    
                    # Send with retry mechanism
                    success = await send_mention_batch(original_message, mentions)
                    
                    if success:
                        successful += 1
                        logger.info(f"Batch {batch_number}/{total_batches} sent successfully")
                    else:
                        failed += 1
                        logger.error(f"Batch {batch_number}/{total_batches} failed after retries")
                    
                    # Delay to avoid spam (2 seconds between batches)
                    if i + BATCH_SIZE < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)
            
            # Mode 2: Header text mode
            else:
                # Extract text after command
                command_text = message.text.split(maxsplit=1)
                header = command_text[1] if len(command_text) > 1 else "📢 Tagging Everyone"
                
                await progress_msg.delete()
                
                total_batches = (len(members) + BATCH_SIZE - 1) // BATCH_SIZE
                successful = 0
                failed = 0
                
                # Divide members into batches of 5
                for i in range(0, len(members), BATCH_SIZE):
                    batch = members[i:i + BATCH_SIZE]
                    batch_number = (i // BATCH_SIZE) + 1
                    
                    # Create blue text mentions
                    mentions = " ".join([
                        f"[{user.first_name}](tg://user?id={user.id})"
                        for user in batch
                    ])
                    
                    # Header + blank line + mentions (header repeated in each batch)
                    text = f"{header}\n\n{mentions}"
                    
                    # Send with retry mechanism
                    success = await send_mention_batch(message, text)
                    
                    if success:
                        successful += 1
                        logger.info(f"Batch {batch_number}/{total_batches} sent successfully")
                    else:
                        failed += 1
                        logger.error(f"Batch {batch_number}/{total_batches} failed after retries")
                    
                    # Delay to avoid spam (2 seconds between batches)
                    if i + BATCH_SIZE < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                
                # Log final results
                if failed > 0:
                    logger.warning(f"✅ Tagged {len(members)} members in {chat_id} - Success: {successful}, Failed: {failed}")
                else:
                    logger.info(f"✅ Successfully tagged {len(members)} members in {chat_id}")
            
        except Exception as e:
            logger.error(f"Error in tagall command: {e}", exc_info=True)
            try:
                await message.reply_text(
                    "❌ An error occurred while processing the command. "
                    "Please try again later."
                )
            except:
                pass
    
    logger.info("✅ TagAll handlers setup complete")
