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

SUPERGROUP_ONLY_MSG = (
    "This bot only works in supergroups.\n\n"
    "To convert your group to a supergroup:\n"
    "- Make chat history visible for new members\n"
    "- Enable any admin permission/restriction\n"
    "- Add a bot as admin\n\n"
    "Leaving..."
)


@router.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=IS_NOT_MEMBER >> IS_MEMBER
    )
)
async def bot_added_to_chat(event: ChatMemberUpdated):
    chat = event.chat
    added_by = event.from_user

    if chat.type not in ["group", "supergroup"]:
        return

    if chat.type == "group":
        try:
            await event.bot.send_message(chat.id, SUPERGROUP_ONLY_MSG)
        except Exception:
            pass
        try:
            await event.bot.leave_chat(chat.id)
        except Exception:
            pass
        return

    await add_served_chat(chat.id)

    if LOG_GROUP_ID:
        try:
            log_msg = BOT_ADDED_TO_GROUP.format(
                chat_title=chat.title or "Unknown",
                chat_id=chat.id,
                added_by=f"@{added_by.username}" if added_by.username else added_by.first_name,
                time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            )
            await event.bot.send_message(LOG_GROUP_ID, log_msg)
        except Exception:
            pass


@router.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=IS_MEMBER >> IS_NOT_MEMBER
    )
)
async def bot_removed_from_chat(event: ChatMemberUpdated):
    chat = event.chat

    if chat.type not in ["group", "supergroup"]:
        return

    await remove_served_chat(chat.id)

    if LOG_GROUP_ID:
        try:
            log_msg = BOT_REMOVED_FROM_GROUP.format(
                chat_title=chat.title or "Unknown",
                chat_id=chat.id,
                time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            )
            await event.bot.send_message(LOG_GROUP_ID, log_msg)
        except Exception:
            pass
