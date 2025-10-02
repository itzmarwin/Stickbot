from aiogram import Router, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from datetime import datetime
import logging

from config import OWNER_ID
from templates import BOT_ADDED_TO_GROUP, BOT_REMOVED_FROM_GROUP

logger = logging.getLogger(__name__)
router = Router()

@router.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=IS_NOT_MEMBER >> IS_MEMBER
    )
)
async def bot_added_to_chat(event: ChatMemberUpdated):
    """Handle when bot is added to a group"""
    if not OWNER_ID:
        return
    
    try:
        chat = event.chat
        added_by = event.from_user
        
        # Only log for groups and supergroups
        if chat.type in ["group", "supergroup"]:
            log_msg = BOT_ADDED_TO_GROUP.format(
                chat_title=chat.title or "Unknown",
                chat_id=chat.id,
                added_by=f"@{added_by.username}" if added_by.username else added_by.first_name,
                time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            )
            
            await event.bot.send_message(OWNER_ID, log_msg)
    except Exception as e:
        logger.error(f"Error logging bot addition: {e}")

@router.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=IS_MEMBER >> IS_NOT_MEMBER
    )
)
async def bot_removed_from_chat(event: ChatMemberUpdated):
    """Handle when bot is removed from a group"""
    if not OWNER_ID:
        return
    
    try:
        chat = event.chat
        
        # Only log for groups and supergroups
        if chat.type in ["group", "supergroup"]:
            log_msg = BOT_REMOVED_FROM_GROUP.format(
                chat_title=chat.title or "Unknown",
                chat_id=chat.id,
                time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            )
            
            await event.bot.send_message(OWNER_ID, log_msg)
    except Exception as e:
        logger.error(f"Error logging bot removal: {e}")
