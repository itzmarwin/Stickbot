import re
import logging
import asyncio  
from typing import Set, Optional, Dict

from pyrogram import Client, filters
from pyrogram.enums import ParseMode, MessageEntityType, ChatMemberStatus
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import OWNER_ID, BOT_USERNAME
from pyrogram_handlers.caching import get_admin_permissions
from utils.language import get_chat_lang_dict
from mongo.antipromo_db import (
    add_to_whitelist,
    remove_from_whitelist,
    is_whitelisted,
    get_whitelist,
    get_antipromo_status,
    set_antipromo_status,
)

logger = logging.getLogger(__name__)

_SAFE_WORDS_RAW = [
    "Title",       "𝖳𝗂𝗍𝗅𝖾",
    "Duration",    "𝖣𝗎𝗋𝖺𝗍𝗂𝗈𝗇",
    "Streaming",   "𝖲𝗍𝗋𝖾𝖺𝗆𝗂𝗇𝗀",
    "Stream",      "𝖲𝗍𝗋𝖾𝖺𝗆",
    "Queue",       "𝖰𝗎𝖾𝗎𝖾",
    "ကြာချိန်",
    "ခေါင်းစဉ်",
]

_SAFE_WORDS_LOWER: Set[str] = {w.lower() for w in _SAFE_WORDS_RAW}

_PROMO_DOMAINS = (
    "t.me/",
    "telegram.me/",
    "youtube.com/",
    "youtu.be/",
    "facebook.com/",
    "fb.com/",
    "instagram.com/",
    "play.google.com/",
)

_URL_PATTERN = re.compile(
    r"(https?://)?(www\.)?"
    r"(t\.me|telegram\.me|youtube\.com|youtu\.be"
    r"|facebook\.com|fb\.com|instagram\.com|play\.google\.com)"
    r"/\S*",
    re.IGNORECASE,
)


def _is_promo_url(url: str) -> bool:
    url_lower = url.lower()
    return any(domain in url_lower for domain in _PROMO_DOMAINS)


def _count_promo_links(message: Message) -> int:
    found: Set[str] = set()
    entities = message.entities or message.caption_entities or []
    text = message.text or message.caption or ""

    for entity in entities:
        if entity.type == MessageEntityType.URL:
            url = text[entity.offset: entity.offset + entity.length]
            if _is_promo_url(url):
                found.add(url.lower())
        elif entity.type == MessageEntityType.TEXT_LINK:
            url = entity.url or ""
            if _is_promo_url(url):
                found.add(url.lower())

    if text:
        for match in _URL_PATTERN.finditer(text):
            url = match.group(0)
            if _is_promo_url(url):
                found.add(url.lower())

    return len(found)


def _count_safe_words(message: Message) -> int:
    text = (message.text or message.caption or "").lower()
    if not text:
        return 0
    return sum(1 for word in _SAFE_WORDS_LOWER if word in text)


def _should_delete(message: Message) -> bool:
    link_count = _count_promo_links(message)
    if link_count == 0:
        return False
    safe_count = _count_safe_words(message)
    if safe_count >= 2 and link_count == 1:
        return False
    return True


def _can_manage_antipromo(chat_id: int, user_id: int) -> Optional[bool]:
    perms = get_admin_permissions(chat_id, user_id)
    if perms is None:
        return None
    return perms.get("can_delete_messages", False)


def _promo_removed_buttons(lang: dict) -> InlineKeyboardMarkup:
    bot_user = BOT_USERNAME.lstrip("@") if BOT_USERNAME else ""
    add_link = f"https://t.me/{bot_user}?startgroup=start"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(lang["btn_add_me"], url=add_link),
        InlineKeyboardButton(lang["btn_close"],  callback_data="antipromo_close"),
    ]])


async def setup_antipromo_handlers(client: Client):

    @client.on_message(filters.group & filters.bot, group=5)
    async def antipromo_watcher(client: Client, message: Message):
        chat_id = message.chat.id

        if not await get_antipromo_status(chat_id):
            return

        sender_id: Optional[int] = None
        sender_name: str         = "a bot"

        if message.from_user and message.from_user.is_bot:
            sender_id   = message.from_user.id
            sender_name = (
                f"@{message.from_user.username}"
                if message.from_user.username
                else message.from_user.first_name or "a bot"
            )
        elif message.sender_chat:
            sender_id   = message.sender_chat.id
            sender_name = message.sender_chat.title or "a bot"

        if sender_id is None:
            return

        if await is_whitelisted(sender_id):
            return

        if not _should_delete(message):
            return

        try:
            await asyncio.sleep(1)  
            await message.delete()
            logger.info(
                f"[AntiPromo] Deleted | chat={chat_id} "
                f"bot_id={sender_id} msg_id={message.id}"
            )
        except Exception as e:
            logger.warning(f"[AntiPromo] Delete failed: {e}")
            return

        try:
            lang = await get_chat_lang_dict(chat_id)
            await client.send_message(
                chat_id=chat_id,
                text=lang["antipromo_removed"].format(sender=sender_name),
                parse_mode=ParseMode.HTML,
                reply_markup=_promo_removed_buttons(lang),
            )
        except Exception as e:
            logger.warning(f"[AntiPromo] Notify failed: {e}")


    @client.on_callback_query(filters.regex(r"^antipromo_close$"))
    async def antipromo_close(client: Client, callback: CallbackQuery):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()


    @client.on_message(filters.command("antipromo") & filters.group)
    async def antipromo_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return

        lang = await get_chat_lang_dict(chat_id)

        perm = _can_manage_antipromo(chat_id, user_id)
        if perm is None:
            await message.reply_text(lang["only_admins"], parse_mode=ParseMode.HTML)
            return
        if perm is False:
            await message.reply_text(lang["antipromo_need_delete_perm"], parse_mode=ParseMode.HTML)
            return

        parts  = message.text.split()
        action = parts[1].lower() if len(parts) > 1 else ""

        if not action:
            status = await get_antipromo_status(chat_id)
            state  = "on" if status else "off"
            await message.reply_text(
                lang["antipromo_status"].format(state=state),
                parse_mode=ParseMode.HTML,
            )
            return

        if action == "on":
            if await get_antipromo_status(chat_id):
                await message.reply_text(lang["antipromo_already_on"], parse_mode=ParseMode.HTML)
                return
            await set_antipromo_status(chat_id, True)
            await message.reply_text(lang["antipromo_turned_on"], parse_mode=ParseMode.HTML)

        elif action == "off":
            if not await get_antipromo_status(chat_id):
                await message.reply_text(lang["antipromo_already_off"], parse_mode=ParseMode.HTML)
                return
            await set_antipromo_status(chat_id, False)
            await message.reply_text(lang["antipromo_turned_off"], parse_mode=ParseMode.HTML)

        else:
            await message.reply_text(lang["antipromo_usage"], parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("antipw"))
    async def antipromo_whitelist_add(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text(
                "Only the bot owner can manage the whitelist.",
                parse_mode=ParseMode.HTML,
            )
            return

        target = None
        if message.reply_to_message and message.reply_to_message.from_user:
            target = message.reply_to_message.from_user
        else:
            parts = message.text.split()
            if len(parts) < 2:
                await message.reply_text("Usage: /antipw @botusername", parse_mode=ParseMode.HTML)
                return
            try:
                target = await client.get_users(parts[1].lstrip("@"))
            except Exception:
                await message.reply_text(f"Could not find {parts[1]}", parse_mode=ParseMode.HTML)
                return

        if not target:
            await message.reply_text("Could not identify the bot.", parse_mode=ParseMode.HTML)
            return

        if not target.is_bot:
            await message.reply_text(f"@{target.username} is not a bot.", parse_mode=ParseMode.HTML)
            return

        if await is_whitelisted(target.id):
            await message.reply_text(f"@{target.username} is already whitelisted.", parse_mode=ParseMode.HTML)
            return

        success = await add_to_whitelist(target.id, target.username or str(target.id))
        if success:
            await message.reply_text(
                f"@{target.username} added to the whitelist. Its messages won't be deleted in any group.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text("Something went wrong. Try again.", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("antipr"))
    async def antipromo_whitelist_remove(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text(
                "Only the bot owner can manage the whitelist.",
                parse_mode=ParseMode.HTML,
            )
            return

        target = None
        if message.reply_to_message and message.reply_to_message.from_user:
            target = message.reply_to_message.from_user
        else:
            parts = message.text.split()
            if len(parts) < 2:
                await message.reply_text("Usage: /antipr @botusername", parse_mode=ParseMode.HTML)
                return
            try:
                target = await client.get_users(parts[1].lstrip("@"))
            except Exception:
                await message.reply_text(f"Could not find {parts[1]}", parse_mode=ParseMode.HTML)
                return

        if not target:
            await message.reply_text("Could not identify the bot.", parse_mode=ParseMode.HTML)
            return

        success = await remove_from_whitelist(target.id)
        if success:
            await message.reply_text(
                f"@{target.username} removed from the whitelist.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text(
                f"@{target.username} was not in the whitelist.",
                parse_mode=ParseMode.HTML,
            )


    @client.on_message(filters.command("antiplist"))
    async def antipromo_whitelist_list(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text(
                "Only the bot owner can view the whitelist.",
                parse_mode=ParseMode.HTML,
            )
            return

        whitelist = await get_whitelist()
        if not whitelist:
            await message.reply_text("Whitelist is empty.", parse_mode=ParseMode.HTML)
            return

        lines = []
        for i, entry in enumerate(whitelist, 1):
            uname  = entry.get("username", "")
            bot_id = entry.get("bot_id", "")
            lines.append(
                f"{i}. @{uname} (<code>{bot_id}</code>)" if uname
                else f"{i}. <code>{bot_id}</code>"
            )

        await message.reply_text(
            "<b>Whitelisted bots:</b>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )
