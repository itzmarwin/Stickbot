import re
import logging
import asyncio
from typing import Set, Optional, Dict

from pyrogram import Client, filters
from pyrogram.enums import ParseMode, MessageEntityType, ChatMemberStatus, ChatMembersFilter
from pyrogram.errors import ChatAdminRequired
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
    get_promo_status,
    set_promo_status,
)

logger = logging.getLogger(__name__)

# ============================================================================
#  BOT ANTI-PROMO  (formerly antipromo.py)
#  Watches messages sent BY BOTS in a group and deletes promo spam based on
#  a curated domain list (default tier) or a strict any-link rule (tough tier).
# ============================================================================

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

# Any http(s) link, regardless of domain - used only for tough-list BOTS,
# which get stricter scrutiny than the curated-domain check above.
#
# NOTE: renamed from the original _ANY_URL_PATTERN. promo.py (below) also had
# a module-level _ANY_URL_PATTERN with a DIFFERENT, broader regex (it also
# matches bare domains like "example.com", not just http(s):// links). Merging
# both into one file under the same name would have made whichever definition
# came second silently win for BOTH use sites - so each now has its own name.
_TOUGHLIST_ANY_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

# For default-tier bots: a message with 1 promo link + 2 safe words is normally
# forgiven (looks like a genuine "now playing" announcement), but if it's this
# long anyway, treat it as spam that padded in safe words to slip through.
_LONG_MESSAGE_WORD_THRESHOLD = 25


def _is_promo_url(url: str) -> bool:
    url_lower = url.lower()
    return any(domain in url_lower for domain in _PROMO_DOMAINS)


def _count_promo_links(message: Message) -> int:
    """
    Counts DIRECT links only - a URL that's actually visible/typed out in
    the message text. Deliberately does NOT count TEXT_LINK entities
    (a link hidden behind styled text, e.g. a hyperlinked word like
    "Now Playing"). Bots routinely style a normal caption word as a
    clickable link without that being spam, so that case is exempted;
    only a visibly-typed promo URL counts toward deletion.
    """
    found: Set[str] = set()
    entities = message.entities or message.caption_entities or []
    text = message.text or message.caption or ""

    for entity in entities:
        if entity.type == MessageEntityType.URL:
            url = text[entity.offset: entity.offset + entity.length]
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
    Count DIRECT links only (visible/typed-out URL text), any domain -
    no curated-domain filter. Used only for tough-list bots, which get
    stricter scrutiny. Same exemption as _count_promo_links: a link
    hidden behind styled text (TEXT_LINK) is not counted here.
    """
    found: Set[str] = set()
    entities = message.entities or message.caption_entities or []
    text = message.text or message.caption or ""

    for entity in entities:
        if entity.type == MessageEntityType.URL:
            url = text[entity.offset: entity.offset + entity.length]
            found.add(url.lower())

    if text:
        for match in _TOUGHLIST_ANY_URL_PATTERN.finditer(text):
            found.add(match.group(0).lower())

    return len(found)


def _has_username_mention(message: Message) -> bool:
    """
    True if the message @mentions a username or text-mentions a user.
    Shared by both the bot-antipromo checks below and the user-promo
    checks further down (promo.py's copy of this exact function was
    identical, so it's kept once here instead of duplicated).
    """
    entities = message.entities or message.caption_entities or []
    for entity in entities:
        if entity.type in (MessageEntityType.MENTION, MessageEntityType.TEXT_MENTION):
            return True
    return False


def _should_delete_toughlist(message: Message) -> bool:
    """
    Strict rules for bots on the /aptoughlist tough list.
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


def _antipromo_removed_buttons(lang: dict) -> InlineKeyboardMarkup:
    """
    Renamed from the original _promo_removed_buttons. promo.py (below) has
    its OWN _promo_removed_buttons with a DIFFERENT callback_data
    ("promo_close" vs this one's "antipromo_close"). Merging both under one
    name would have made one silently override the other, and the close
    button on whichever watcher lost the naming fight would send a
    callback_data that no @on_callback_query handler is listening for -
    i.e. the button would silently stop working. Hence the two-name split.
    """
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
                # Reuses the same "advertisement" wording/style as the
                # user-side promo_removed message (en.json) per request -
                # {user} here just receives the bot's display name.
                text=lang["promo_removed"].format(user=sender_name),
                parse_mode=ParseMode.HTML,
                reply_markup=_antipromo_removed_buttons(lang),
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


    @client.on_message(filters.command("apwhitelist"))
    async def antipromo_whitelist_command(client: Client, message: Message):
        """
        /apwhitelist add @bot     - whitelisted bots are never checked at all
        /apwhitelist remove @bot
        /apwhitelist list         (or just /apwhitelist)
        Replaces the old /antipw, /antipr, /antiplist trio - same three
        actions, one memorable command instead of three similar-looking ones.
        """
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text(
                "Only the bot owner can manage the whitelist.",
                parse_mode=ParseMode.HTML,
            )
            return

        parts  = message.text.split()
        action = parts[1].lower() if len(parts) > 1 else "list"

        if action == "list":
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
            return

        if action not in ("add", "remove"):
            await message.reply_text(
                "<b>Usage:</b>\n"
                "<code>/apwhitelist add @botusername</code>\n"
                "<code>/apwhitelist remove @botusername</code>\n"
                "<code>/apwhitelist list</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        target = None
        if message.reply_to_message and message.reply_to_message.from_user:
            target = message.reply_to_message.from_user
        else:
            if len(parts) < 3:
                await message.reply_text(f"Usage: /apwhitelist {action} @botusername", parse_mode=ParseMode.HTML)
                return
            try:
                target = await client.get_users(parts[2].lstrip("@"))
            except Exception:
                await message.reply_text(f"Could not find {parts[2]}", parse_mode=ParseMode.HTML)
                return

        if not target:
            await message.reply_text("Could not identify the bot.", parse_mode=ParseMode.HTML)
            return

        if action == "add":
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

        else:  # remove
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


    @client.on_message(filters.command("aptoughlist"))
    async def antipromo_toughlist_command(client: Client, message: Message):
        """
        /aptoughlist add @bot     - any of its messages with a link or mention
                                     now need 2+ safe words to survive
        /aptoughlist remove @bot
        /aptoughlist list         (or just /aptoughlist)
        Replaces the old /atp, /atpr, /atplist trio - same three actions,
        one memorable command instead of three similar-looking ones.
        """
        user_id = message.from_user.id if message.from_user else None
        if user_id != OWNER_ID:
            await message.reply_text(
                "Only the bot owner can manage the tough list.",
                parse_mode=ParseMode.HTML,
            )
            return

        parts  = message.text.split()
        action = parts[1].lower() if len(parts) > 1 else "list"

        if action == "list":
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
            return

        if action not in ("add", "remove"):
            await message.reply_text(
                "<b>Usage:</b>\n"
                "<code>/aptoughlist add @botusername</code>\n"
                "<code>/aptoughlist remove @botusername</code>\n"
                "<code>/aptoughlist list</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        target = None
        if message.reply_to_message and message.reply_to_message.from_user:
            target = message.reply_to_message.from_user
        else:
            if len(parts) < 3:
                await message.reply_text(f"Usage: /aptoughlist {action} @botusername", parse_mode=ParseMode.HTML)
                return
            try:
                target = await client.get_users(parts[2].lstrip("@"))
            except Exception:
                await message.reply_text(f"Could not find {parts[2]}", parse_mode=ParseMode.HTML)
                return

        if not target:
            await message.reply_text("Could not identify the bot.", parse_mode=ParseMode.HTML)
            return

        if action == "add":
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

        else:  # remove
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


# ============================================================================
#  USER ANTI-LINK/MENTION  (formerly promo.py)
#  Watches messages sent BY REGULAR USERS (non-bot) in a group and deletes
#  any message containing a link or an @mention, unless the sender is admin.
# ============================================================================

# Any http(s) link, t.me link, or bare domain-looking link — no curated
# domain list here, unlike the bot-antipromo checker above. Users get the
# strict "any link at all" treatment.
#
# NOTE: renamed from the original _ANY_URL_PATTERN to avoid colliding with
# _TOUGHLIST_ANY_URL_PATTERN above — see the comment on that pattern for why.
_USER_ANY_URL_PATTERN = re.compile(
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
    if text and _USER_ANY_URL_PATTERN.search(text):
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
                f"User anti-promo turned ON for <code>{target_chat_id}</code>.\n"
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
                f"User anti-promo turned OFF for <code>{target_chat_id}</code>.",
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
        state = "ON" if status else "OFF"
        await message.reply_text(
            f"User anti-promo for <code>{target_chat_id}</code> is currently <b>{state}</b>.",
            parse_mode=ParseMode.HTML,
        )
