import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
DELAY_BETWEEN_BATCHES = 3
MAX_RETRIES = 3
MAX_MESSAGE_LENGTH = 3900

active_tagall = {}


async def get_all_members(client: Client, chat_id: int) -> list:
    members = []
    try:
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot:
                members.append(member.user)
    except Exception as e:
        logger.error(f"Error fetching members from {chat_id}: {e}")
    
    return members


async def send_mention_batch(message_target, mentions: str, retry_count: int = 0):
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
        
        await asyncio.sleep(wait_time + 1)
        return await send_mention_batch(message_target, mentions, retry_count + 1)
        
    except Exception as e:
        logger.error(f"Error sending mention batch: {e}")
        return False


async def setup_tagall_handlers(client: Client):
    
    @client.on_message(filters.command(["tagall", "all"]) & filters.group)
    async def tagall_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            
            try:
                member = await client.get_chat_member(chat_id, message.from_user.id)
                if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                    await message.reply_text(
                        "⚠️ 𝖮𝗇𝗅𝗒 𝖺𝖽𝗆𝗂𝗇𝗌 𝖼𝖺𝗇 𝗎𝗌𝖾 𝗍𝗁𝗂𝗌 𝖼𝗈𝗆𝗆𝖺𝗇𝖽."
                    )
                    return
            except Exception as e:
                logger.error(f"Error checking admin status: {e}")
                await message.reply_text("❌ 𝖴𝗇𝖺𝖻𝗅𝖾 𝗍𝗈 𝗏𝖾𝗋𝗂𝖿𝗒 𝖺𝖽𝗆𝗂𝗇 𝗌𝗍𝖺𝗍𝗎𝗌.")
                return
            
            if chat_id in active_tagall and active_tagall[chat_id]:
                await message.reply_text(
                    "⚠️ 𝖳𝖺𝗀𝖺𝗅𝗅 𝖺𝗅𝗋𝖾𝖺𝖽𝗒 𝗋𝗎𝗇𝗇𝗂𝗇𝗀!\n\n"
                    "𝖴𝗌𝖾 /stop 𝗈𝗋 /cancel 𝗍𝗈 𝗌𝗍𝗈𝗉 𝗂𝗍."
                )
                return
            
            is_reply = message.reply_to_message is not None
            
            if not is_reply:
                command_parts = message.text.split(maxsplit=1)
                if len(command_parts) > 1:
                    user_message = command_parts[1]
                    
                    estimated_mentions = BATCH_SIZE * 50
                    total_length = len(user_message) + estimated_mentions
                    
                    if total_length > 4000:
                        await message.reply_text(
                            f"❌ 𝖬𝖾𝗌𝗌𝖺𝗀𝖾 𝗍𝗈𝗈 𝗅𝗈𝗇𝗀!\n\n"
                            f"𝖸𝗈𝗎𝗋 𝗆𝖾𝗌𝗌𝖺𝗀𝖾: {len(user_message)} 𝖼𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌\n"
                            f"𝖬𝖺𝗑𝗂𝗆𝗎𝗆 𝖺𝗅𝗅𝗈𝗐𝖾𝖽: {MAX_MESSAGE_LENGTH} 𝖼𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌\n\n"
                            f"𝖯𝗅𝖾𝖺𝗌𝖾 𝗌𝗁𝗈𝗋𝗍𝖾𝗇 𝗒𝗈𝗎𝗋 𝗆𝖾𝗌𝗌𝖺𝗀𝖾."
                        )
                        return
            
            progress_msg = await message.reply_text("🔄 𝖥𝖾𝗍𝖼𝗁𝗂𝗇𝗀 𝗆𝖾𝗆𝖻𝖾𝗋𝗌...")
            members = await get_all_members(client, chat_id)
            
            if not members:
                await progress_msg.edit_text("❌ 𝖭𝗈 𝗆𝖾𝗆𝖻𝖾𝗋𝗌 𝖿𝗈𝗎𝗇𝖽!")
                return
            
            active_tagall[chat_id] = True
            
            if is_reply:
                original_message = message.reply_to_message
                await progress_msg.delete()
                
                total_batches = (len(members) + BATCH_SIZE - 1) // BATCH_SIZE
                successful = 0
                failed = 0
                
                for i in range(0, len(members), BATCH_SIZE):
                    if chat_id not in active_tagall or not active_tagall[chat_id]:
                        await message.reply_text("⛔ 𝖳𝖺𝗀𝖺𝗅𝗅 𝗌𝗍𝗈𝗉𝗉𝖾𝖽.")
                        logger.info(f"Tagall stopped in chat {chat_id}")
                        return
                    
                    batch = members[i:i + BATCH_SIZE]
                    batch_number = (i // BATCH_SIZE) + 1
                    
                    mentions = ", ".join([
                        f"[{user.first_name}](tg://user?id={user.id})"
                        for user in batch
                    ])
                    
                    success = await send_mention_batch(original_message, mentions)
                    
                    if success:
                        successful += 1
                        logger.info(f"Batch {batch_number}/{total_batches} sent successfully")
                    else:
                        failed += 1
                        logger.error(f"Batch {batch_number}/{total_batches} failed after retries")
                    
                    if i + BATCH_SIZE < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)
            
            else:
                command_text = message.text.split(maxsplit=1)
                header = command_text[1] if len(command_text) > 1 else "📢 Tagging Everyone"
                
                await progress_msg.delete()
                
                total_batches = (len(members) + BATCH_SIZE - 1) // BATCH_SIZE
                successful = 0
                failed = 0
                
                for i in range(0, len(members), BATCH_SIZE):
                    if chat_id not in active_tagall or not active_tagall[chat_id]:
                        await message.reply_text("⛔ 𝖳𝖺𝗀𝖺𝗅𝗅 𝗌𝗍𝗈𝗉𝗉𝖾𝖽.")
                        logger.info(f"Tagall stopped in chat {chat_id}")
                        return
                    
                    batch = members[i:i + BATCH_SIZE]
                    batch_number = (i // BATCH_SIZE) + 1
                    
                    mentions = ", ".join([
                        f"[{user.first_name}](tg://user?id={user.id})"
                        for user in batch
                    ])
                    
                    text = f"{header}\n\n{mentions}"
                    
                    success = await send_mention_batch(message, text)
                    
                    if success:
                        successful += 1
                        logger.info(f"Batch {batch_number}/{total_batches} sent successfully")
                    else:
                        failed += 1
                        logger.error(f"Batch {batch_number}/{total_batches} failed after retries")
                    
                    if i + BATCH_SIZE < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                
                if failed > 0:
                    logger.warning(f"Tagged {len(members)} members in {chat_id} - Success: {successful}, Failed: {failed}")
                else:
                    logger.info(f"Successfully tagged {len(members)} members in {chat_id}")
            
            active_tagall[chat_id] = False
            
        except Exception as e:
            logger.error(f"Error in tagall command: {e}", exc_info=True)
            active_tagall[chat_id] = False
            try:
                await message.reply_text("❌ 𝖲𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀. 𝖳𝗋𝗒 𝖺𝗀𝖺𝗂𝗇 𝗅𝖺𝗍𝖾𝗋.")
            except:
                pass
    
    @client.on_message(filters.command(["stop", "cancel"]) & filters.group)
    async def stop_tagall_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            
            try:
                member = await client.get_chat_member(chat_id, message.from_user.id)
                if member.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                    await message.reply_text("⚠️ 𝖮𝗇𝗅𝗒 𝖺𝖽𝗆𝗂𝗇𝗌 𝖼𝖺𝗇 𝗌𝗍𝗈𝗉 𝗍𝖺𝗀𝖺𝗅𝗅.")
                    return
            except Exception as e:
                logger.error(f"Error checking admin status: {e}")
                return
            
            if chat_id not in active_tagall or not active_tagall[chat_id]:
                await message.reply_text("ℹ️ 𝖭𝗈 𝖺𝖼𝗍𝗂𝗏𝖾 𝗍𝖺𝗀𝖺𝗅𝗅 𝗉𝗋𝗈𝖼𝖾𝗌𝗌.")
                return
            
            active_tagall[chat_id] = False
            await message.reply_text("✅ 𝖳𝖺𝗀𝖺𝗅𝗅 𝗌𝗍𝗈𝗉𝗉𝖾𝖽 𝗌𝗎𝖼𝖼𝖾𝗌𝗌𝖿𝗎𝗅𝗅𝗒!")
            logger.info(f"Tagall stopped by admin in chat {chat_id}")
            
        except Exception as e:
            logger.error(f"Error in stop command: {e}", exc_info=True)
    
    logger.info("✅ TagAll handlers setup complete")
