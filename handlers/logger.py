from aiogram import Router, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from datetime import datetime
import logging

from config import LOG_GROUP_ID
from templates import BOT_ADDED_TO_GROUP, BOT_REMOVED_FROM_GROUP
from mongo.userdb import add_served_chat, remove_served_chat

logger = logging.getLogger(__name__)
router = Router()

@router.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=IS_NOT_MEMBER >> IS_MEMBER
    )
)
async def bot_added_to_chat(event: ChatMemberUpdated):
    """Handle when bot is added to a group"""
    try:
        chat = event.chat
        added_by = event.from_user
        
        # Only handle groups and supergroups
        if chat.type in ["group", "supergroup"]:
            # Add to served chats in database
            await add_served_chat(chat.id)
            logger.info(f"✅ Added chat to served chats: {chat.title} ({chat.id})")
            
            # Log to logger group if available
            if LOG_GROUP_ID:
                log_msg = BOT_ADDED_TO_GROUP.format(
                    chat_title=chat.title or "Unknown",
                    chat_id=chat.id,
                    added_by=f"@{added_by.username}" if added_by.username else added_by.first_name,
                    time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                )
                await event.bot.send_message(LOG_GROUP_ID, log_msg)
                
    except Exception as e:
        logger.error(f"Error handling bot addition: {e}")

@router.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=IS_MEMBER >> IS_NOT_MEMBER
    )
)
async def bot_removed_from_chat(event: ChatMemberUpdated):
    """Handle when bot is removed from a group"""
    try:
        chat = event.chat
        
        # Only handle groups and supergroups
        if chat.type in ["group", "supergroup"]:
            # Remove from served chats in database
            await remove_served_chat(chat.id)
            logger.info(f"🗑️ Removed chat from served chats: {chat.title} ({chat.id})")
            
            # Log to logger group if available
            if LOG_GROUP_ID:
                log_msg = BOT_REMOVED_FROM_GROUP.format(
                    chat_title=chat.title or "Unknown",
                    chat_id=chat.id,
                    time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                )
                await event.bot.send_message(LOG_GROUP_ID, log_msg)
                
    except Exception as e:
        logger.error(f"Error handling bot removal: {e}")
