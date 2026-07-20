import re
import logging
from typing import Set

from pyrogram import Client, filters
from pyrogram.enums import ParseMode, MessageEntityType, ChatMemberStatus, ChatMembersFilter
from pyrogram.errors import ChatAdminRequired
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import OWNER_ID, BOT_USERNAME
from pyrogram_handlers.caching import get_admin_permissions
from utils.language import get_chat_lang_dict
from mongo.promo_db import get_promo_status, set_promo_status

logger = logging.getLogger(__name__)

# Any http(s) link, t.me link, or bare domain-looking link — no curated
# domain list here, unlike antipromo.py's bot-checker. Users get the strict
# "any link at all" treatment.
_ANY_URL_PATTERN = re.compile(
    r"(?:https?://\S+)|(?:(?:www\.)?[a-zA-Z0-9-]+\.(?:com|me|org|net|io|co|in|xyz|link|club|info|gg|tv|app)\S*)",
    re.IGNORECASE,
)


async def _check_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """
    True if user_id is an admin/owner in chat_id. Cache first, live API fallback
    (mirrors the pattern already used in locks.py / filters.py) so a cold cache
    never causes an admin's own message to get deleted.
    """
    perms = get_admin_permissions(chat_id, user_id)
    if perms is not None:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except ChatAdminRequired:
        try:
            async for admin in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                if admin.user.id == user_id:
                    return True
            return False
        except Exception:
            return False
    except Exception:
        return False


def _has_link(message: Message) -> bool:
    entities = message.entities or message.caption_entities or []
    for entity in entities:
        if entity.type in (MessageEntityType.URL, MessageEntityType.TEXT_LINK):
            return True

    text = message.text or message.caption or ""
    if text and _ANY_URL_PATTERN.search(text):
        return True
    return False


def _has_username_mention(message: Message) -> bool:
    entities = message.entities or message.caption_entities or []
    for entity in entities:
        if entity.type in (MessageEntityType.MENTION, MessageEntityType.TEXT_MENTION):
            return True
    return False


def _should_delete_user_message(message: Message) -> bool:
    return _has_link(message) or _has_username_mention(message)


def _promo_removed_buttons(lang: dict) -> InlineKeyboardMarkup:
    bot_user = BOT_USERNAME.lstrip("@") if BOT_USERNAME else ""
    add_link = f"https://t.me/{bot_user}?startgroup=start"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(lang["btn_add_me"], url=add_link),
        InlineKeyboardButton(lang["btn_close"],  callback_data="promo_close"),
    ]])


async def setup_promo_handlers(client: Client):

    @client.on_message(filters.group & filters.text & ~filters.via_bot, group=-1)
    async def promo_watcher(client: Client, message: Message):
        chat_id = message.chat.id
        user = message.from_user

        if not user or user.is_bot:
            return

        if not await get_promo_status(chat_id):
            return

        if await _check_admin(client, chat_id, user.id):
            return

        if not _should_delete_user_message(message):
            return

        try:
            await message.delete()
            logger.info(
                f"[Promo] Deleted user link/mention | chat={chat_id} "
                f"user_id={user.id} msg_id={message.id}"
            )
        except Exception as e:
            logger.warning(f"[Promo] Delete failed: {e}")
            return

        try:
            lang = await get_chat_lang_dict(chat_id)
            await client.send_message(
                chat_id=chat_id,
                text=lang["promo_removed"].format(user=user.mention),
                parse_mode=ParseMode.HTML,
                reply_markup=_promo_removed_buttons(lang),
            )
        except Exception as e:
            logger.warning(f"[Promo] Notify failed: {e}")

        message.stop_propagation()


    @client.on_callback_query(filters.regex(r"^promo_close$"))
    async def promo_close(client: Client, callback: CallbackQuery):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()


    # ─── Owner-only enable/disable (per chat_id, from the log group) ──────

    @client.on_message(filters.command("antienable"))
    async def antienable_command(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text("Only the bot owner can use this command.", parse_mode=ParseMode.HTML)
            return

        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text("Usage: /antienable <chat_id>", parse_mode=ParseMode.HTML)
            return

        try:
            target_chat_id = int(parts[1])
        except ValueError:
            await message.reply_text("chat_id must be a number.", parse_mode=ParseMode.HTML)
            return

        if await get_promo_status(target_chat_id):
            await message.reply_text(
                f"User anti-promo is already ON for <code>{target_chat_id}</code>.",
                parse_mode=ParseMode.HTML,
            )
            return

        success = await set_promo_status(target_chat_id, True)
        if success:
            await message.reply_text(
                f"✅ User anti-promo turned ON for <code>{target_chat_id}</code>.\n"
                f"Non-admin users' links/username mentions will now be deleted there.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text("Something went wrong. Try again.", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("antidisable"))
    async def antidisable_command(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text("Only the bot owner can use this command.", parse_mode=ParseMode.HTML)
            return

        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text("Usage: /antidisable <chat_id>", parse_mode=ParseMode.HTML)
            return

        try:
            target_chat_id = int(parts[1])
        except ValueError:
            await message.reply_text("chat_id must be a number.", parse_mode=ParseMode.HTML)
            return

        if not await get_promo_status(target_chat_id):
            await message.reply_text(
                f"User anti-promo is already OFF for <code>{target_chat_id}</code>.",
                parse_mode=ParseMode.HTML,
            )
            return

        success = await set_promo_status(target_chat_id, False)
        if success:
            await message.reply_text(
                f"❌ User anti-promo turned OFF for <code>{target_chat_id}</code>.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text("Something went wrong. Try again.", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("antistatus"))
    async def antistatus_command(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text("Only the bot owner can use this command.", parse_mode=ParseMode.HTML)
            return

        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text("Usage: /antistatus <chat_id>", parse_mode=ParseMode.HTML)
            return

        try:
            target_chat_id = int(parts[1])
        except ValueError:
            await message.reply_text("chat_id must be a number.", parse_mode=ParseMode.HTML)
            return

        status = await get_promo_status(target_chat_id)
        state = "ON ✅" if status else "OFF ❌"
        await message.reply_text(
            f"User anti-promo for <code>{target_chat_id}</code> is currently <b>{state}</b>.",
            parse_mode=ParseMode.HTML,
        )
