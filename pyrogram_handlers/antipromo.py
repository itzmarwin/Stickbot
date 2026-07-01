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
    add_to_toughlist,
    remove_from_toughlist,
    is_in_toughlist,
    get_toughlist,
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
    "viber.com/",
)

_URL_PATTERN = re.compile(
    r"(https?://)?([a-zA-Z0-9-]+\.)*"
    r"(t\.me|telegram\.me|youtube\.com|youtu\.be"
    r"|facebook\.com|fb\.com|instagram\.com|play\.google\.com"
    r"|viber\.com)"
    r"/\S*",
    re.IGNORECASE,
)

# Any http(s) link, regardless of domain - used only for tough-list bots,
# which get stricter scrutiny than the curated-domain check above.
_ANY_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

# For default-tier bots: a message with 1 promo link + 2 safe words is normally
# forgiven (looks like a genuine "now playing" announcement), but if it's this
# long anyway, treat it as spam that padded in safe words to slip through.
_LONG_MESSAGE_WORD_THRESHOLD = 25


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


def _count_words(message: Message) -> int:
    text = message.text or message.caption or ""
    return len(text.split())


def _count_any_links(message: Message) -> int:
    """
    Count links regardless of domain - no curated-domain filter.
    Used only for tough-list bots, which get stricter scrutiny.
    """
    found: Set[str] = set()
    entities = message.entities or message.caption_entities or []
    text = message.text or message.caption or ""

    for entity in entities:
        if entity.type == MessageEntityType.URL:
            url = text[entity.offset: entity.offset + entity.length]
            found.add(url.lower())
        elif entity.type == MessageEntityType.TEXT_LINK:
            url = entity.url or ""
            found.add(url.lower())

    if text:
        for match in _ANY_URL_PATTERN.finditer(text):
            found.add(match.group(0).lower())

    return len(found)


def _has_username_mention(message: Message) -> bool:
    """True if the message @mentions a username or text-mentions a user."""
    entities = message.entities or message.caption_entities or []
    for entity in entities:
        if entity.type in (MessageEntityType.MENTION, MessageEntityType.TEXT_MENTION):
            return True
    return False


def _should_delete_toughlist(message: Message) -> bool:
    """
    Strict rules for bots on the /atp tough list.
    Any message containing a link (any domain) OR a username mention gets
    checked; if it doesn't have at least 2 safe words, it's deleted.
    A plain message with neither a link nor a mention is left alone.
    """
    has_link    = _count_any_links(message) > 0
    has_mention = _has_username_mention(message)

    if not has_link and not has_mention:
        return False

    return _count_safe_words(message) < 2


def _should_delete_default(message: Message) -> bool:
    """
    Default rules for bots not on the tough list - curated promo domains only.
    """
    link_count = _count_promo_links(message)
    if link_count == 0:
        return False
    if link_count >= 2:
        return True

    # exactly 1 promo link
    if _count_safe_words(message) < 2:
        return True

    # 2+ safe words present, but reject anyway if the message is suspiciously
    # long - closes the loophole where a spammer pads in "Title"/"Duration"
    # to slip a long promo message past the safe-word check.
    return _count_words(message) > _LONG_MESSAGE_WORD_THRESHOLD


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

        if await is_in_toughlist(sender_id):
            should_delete = _should_delete_toughlist(message)
        else:
            should_delete = _should_delete_default(message)

        if not should_delete:
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


    @client.on_message(filters.command("atp"))
    async def antipromo_toughlist_add(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text(
                "Only the bot owner can manage the tough list.",
                parse_mode=ParseMode.HTML,
            )
            return

        target = None
        if message.reply_to_message and message.reply_to_message.from_user:
            target = message.reply_to_message.from_user
        else:
            parts = message.text.split()
            if len(parts) < 2:
                await message.reply_text("Usage: /atp @botusername", parse_mode=ParseMode.HTML)
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

        if await is_in_toughlist(target.id):
            await message.reply_text(f"@{target.username} is already on the tough list.", parse_mode=ParseMode.HTML)
            return

        success = await add_to_toughlist(target.id, target.username or str(target.id))
        if success:
            await message.reply_text(
                f"@{target.username} added to the tough list. Any of its messages with a link or "
                f"a username mention now need 2+ safe words to survive.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text("Something went wrong. Try again.", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("atpr"))
    async def antipromo_toughlist_remove(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text(
                "Only the bot owner can manage the tough list.",
                parse_mode=ParseMode.HTML,
            )
            return

        target = None
        if message.reply_to_message and message.reply_to_message.from_user:
            target = message.reply_to_message.from_user
        else:
            parts = message.text.split()
            if len(parts) < 2:
                await message.reply_text("Usage: /atpr @botusername", parse_mode=ParseMode.HTML)
                return
            try:
                target = await client.get_users(parts[1].lstrip("@"))
            except Exception:
                await message.reply_text(f"Could not find {parts[1]}", parse_mode=ParseMode.HTML)
                return

        if not target:
            await message.reply_text("Could not identify the bot.", parse_mode=ParseMode.HTML)
            return

        success = await remove_from_toughlist(target.id)
        if success:
            await message.reply_text(
                f"@{target.username} removed from the tough list.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply_text(
                f"@{target.username} was not on the tough list.",
                parse_mode=ParseMode.HTML,
            )


    @client.on_message(filters.command("atplist"))
    async def antipromo_toughlist_view(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text(
                "Only the bot owner can view the tough list.",
                parse_mode=ParseMode.HTML,
            )
            return

        toughlist = await get_toughlist()
        if not toughlist:
            await message.reply_text("Tough list is empty.", parse_mode=ParseMode.HTML)
            return

        lines = []
        for i, entry in enumerate(toughlist, 1):
            uname  = entry.get("username", "")
            bot_id = entry.get("bot_id", "")
            lines.append(
                f"{i}. @{uname} (<code>{bot_id}</code>)" if uname
                else f"{i}. <code>{bot_id}</code>"
            )

        await message.reply_text(
            "<b>Tough-list bots:</b>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )
