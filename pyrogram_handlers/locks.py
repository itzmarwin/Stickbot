import asyncio
import logging
import unicodedata
from typing import Optional, List, Dict

from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions
from pyrogram.enums import (
    ParseMode,
    ChatMemberStatus,
    MessageEntityType,
    MessageMediaType,
    MessageServiceType,
)
from pyrogram.errors import ChatAdminRequired, ChatNotModified, UserAdminInvalid

from pyrogram_handlers.utils import is_user_admin
from mongo.locksdb import (
    get_chat_locks,
    enable_multiple_locks,
    enable_all_db_locks,
    disable_multiple_locks,
    disable_all_locks,
    DB_LOCK_TYPES,
    NATIVE_LOCK_TYPES,
    ALL_LOCK_TYPES,
)

logger = logging.getLogger(__name__)

# ============================================================
# LOCK DESCRIPTIONS
# ============================================================

LOCK_DESCRIPTIONS = {
    "links":          "URLs and hyperlinks",
    "allforward":     "Forwarded messages from users and channels",
    "userforward":    "Forwarded messages from users only",
    "channelforward": "Forwarded messages from channels only",
    "anonchannel":    "Messages sent as a channel (Send as Chat)",
    "bot":            "Adding new bots to the group",
    "audio":          "Audio files and music",
    "voice":          "Voice messages",
    "video":          "Video messages",
    "gif":            "GIF animations",
    "document":       "Documents and uncompressed files",
    "album":          "Photo or document albums",
    "contact":        "Contact cards",
    "emoji":          "Messages containing any emoji",
    "emojicustom":    "Messages containing custom Telegram emoji",
    "command":        "Telegram bot commands (e.g. /start)",
    "email":          "Messages containing email addresses",
    "phone":          "Messages containing phone numbers",
    "poll":           "Poll messages",
    "checklist":      "Native Telegram checklist messages",
    "forwardstory":   "Forwarded user stories",
    "externalreply":  "Replies to messages from other chats",
    "comment":        "Messages from non-member channel commenters",
    "inline":         "Messages sent via inline bots (e.g. @gif)",
    "msg":            "All text messages",
    "media":          "Photos, videos, audio, documents and other media",
    "stickers":       "Sticker messages",
    "animations":     "Animations (native Telegram permission)",
    "games":          "Game bot messages",
    "webprev":        "Web page link previews",
    "polls":          "Poll creation (native permission)",
    "info":           "Changing group info",
    "invite":         "Inviting users to the group",
    "pin":            "Pinning messages",
}

LOCK_TYPES_TEXT = """<b>🔒 Available Lock Types:</b>

<b>── Content ──</b>
• <code>msg</code>         — All text messages
• <code>media</code>       — Photos, videos, audio, documents and other media
• <code>audio</code>       — Audio files and music
• <code>voice</code>       — Voice messages
• <code>video</code>       — Video messages
• <code>gif</code>         — GIF animations
• <code>document</code>    — Documents and uncompressed files
• <code>album</code>       — Photo or document albums
• <code>contact</code>     — Contact cards
• <code>stickers</code>    — Sticker messages (native)
• <code>animations</code>  — Animations (native)
• <code>games</code>       — Game bot messages (native)
• <code>poll</code>        — Poll messages
• <code>polls</code>       — Poll creation (native permission)
• <code>checklist</code>   — Native Telegram checklists
• <code>inline</code>      — Messages sent via inline bots

<b>── Text Patterns ──</b>
• <code>links</code>       — URLs and hyperlinks
• <code>email</code>       — Messages with email addresses
• <code>phone</code>       — Messages with phone numbers
• <code>command</code>     — Bot commands (e.g. /start)
• <code>emoji</code>       — Messages containing any emoji
• <code>emojicustom</code> — Custom Telegram emoji
• <code>webprev</code>     — Web page link previews (native)

<b>── Forwards ──</b>
• <code>allforward</code>     — All forwarded messages
• <code>userforward</code>    — Forwards from users
• <code>channelforward</code> — Forwards from channels
• <code>forwardstory</code>   — Forwarded user stories

<b>── User Actions ──</b>
• <code>bot</code>         — Adding bots to the group
• <code>invite</code>      — Inviting users (native)
• <code>pin</code>         — Pinning messages (native)
• <code>info</code>        — Changing group info (native)
• <code>anonchannel</code> — Sending as a channel

<b>── Other ──</b>
• <code>externalreply</code> — Replies to other-chat messages
• <code>comment</code>       — Non-member channel commenters

<b>Usage:</b>
<code>/lock &lt;type&gt;</code>
<code>/lock type1, type2, type3</code>
<code>/lock all</code> or <code>/lock everything</code>
<code>/unlock &lt;type&gt;</code>
<code>/unlock type1, type2</code>
<code>/unlock all</code> or <code>/unlock everything</code>"""


# ============================================================
# NATIVE PERMISSION HELPERS
# ============================================================

async def _get_current_permissions(client: Client, chat_id: int) -> Optional[ChatPermissions]:
    """Fetch fresh chat permissions from Telegram API."""
    try:
        chat = await client.get_chat(chat_id)
        return chat.permissions
    except Exception as e:
        logger.error(f"Error fetching chat permissions for {chat_id}: {e}")
        return None


def _safe_perm(perms: Optional[ChatPermissions], field: str, default: bool) -> bool:
    """
    Safely read a permission field.
    If field is None (deprecated/not set by Telegram), return default.
    """
    if perms is None:
        return default
    val = getattr(perms, field, None)
    return val if val is not None else default


def _build_permissions(perms: Optional[ChatPermissions], lock_type: str, locking: bool) -> ChatPermissions:
    """
    Build a new ChatPermissions object.

    KEY RULE: Every field MUST be explicitly True or False — never None.
    pyrotgfork's write() does `not field`, so None → not None → True → BANNED.

    locking=True  → we are locking   → target field = False
    locking=False → we are unlocking → target field = True
    """
    # When locking: default = keep existing (True = allow)
    # When unlocking: default = keep existing (True = allow)
    # Safe read: if field is None from Telegram, assume it was True (allowed)
    d = True  # safe default for "not explicitly set" fields

    msg         = _safe_perm(perms, "can_send_messages", d)
    media       = _safe_perm(perms, "can_send_media_messages", d)
    other       = _safe_perm(perms, "can_send_other_messages", d)
    webprev     = _safe_perm(perms, "can_add_web_page_previews", d)
    polls       = _safe_perm(perms, "can_send_polls", d)
    info        = _safe_perm(perms, "can_change_info", d)
    invite      = _safe_perm(perms, "can_invite_users", d)
    pin         = _safe_perm(perms, "can_pin_messages", d)
    audios      = _safe_perm(perms, "can_send_audios", d)
    documents   = _safe_perm(perms, "can_send_documents", d)
    photos      = _safe_perm(perms, "can_send_photos", d)
    videos      = _safe_perm(perms, "can_send_videos", d)
    video_notes = _safe_perm(perms, "can_send_video_notes", d)
    voice_notes = _safe_perm(perms, "can_send_voice_notes", d)

    val = not locking  # True when unlocking, False when locking

    if lock_type == "msg":
        msg = val
    elif lock_type == "media":
        # Set BOTH old field and all granular fields to avoid any ambiguity
        media = val
        audios = documents = photos = videos = video_notes = voice_notes = val
    elif lock_type in ("stickers", "animations", "games"):
        other = val
    elif lock_type == "webprev":
        webprev = val
    elif lock_type == "polls":
        polls = val
    elif lock_type == "info":
        info = val
    elif lock_type == "invite":
        invite = val
    elif lock_type == "pin":
        pin = val

    return ChatPermissions(
        can_send_messages=msg,
        can_send_media_messages=media,        # ← always explicit, never None
        can_send_other_messages=other,
        can_add_web_page_previews=webprev,
        can_send_polls=polls,
        can_change_info=info,
        can_invite_users=invite,
        can_pin_messages=pin,
        can_send_audios=audios,               # granular fields
        can_send_documents=documents,
        can_send_photos=photos,
        can_send_videos=videos,
        can_send_video_notes=video_notes,
        can_send_voice_notes=voice_notes,
    )


def _all_locked() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_send_polls=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
    )


def _all_unlocked() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
    )


def _is_media_locked(perms: Optional[ChatPermissions]) -> bool:
    """
    Media is locked only if ALL granular fields are explicitly False.
    None = not set by Telegram = NOT locked.
    """
    if perms is None:
        return False

    granular = [
        getattr(perms, "can_send_audios", None),
        getattr(perms, "can_send_documents", None),
        getattr(perms, "can_send_photos", None),
        getattr(perms, "can_send_videos", None),
        getattr(perms, "can_send_video_notes", None),
        getattr(perms, "can_send_voice_notes", None),
    ]
    available = [f for f in granular if f is not None]

    if available:
        # If ALL available granular fields are False → locked
        return not any(available)

    # Fallback: old field — None means NOT locked
    old = getattr(perms, "can_send_media_messages", None)
    if old is None:
        return False
    return not old


# ============================================================
# MESSAGE DETECTION HELPERS
# ============================================================

def _has_emoji(text: str) -> bool:
    if not text:
        return False
    for char in text:
        if unicodedata.category(char) in ("So", "Cs"):
            return True
    return False


def _has_custom_emoji(message: Message) -> bool:
    entities = message.entities or message.caption_entities or []
    return any(e.type == MessageEntityType.CUSTOM_EMOJI for e in entities)


def _has_links(message: Message) -> bool:
    entities = message.entities or message.caption_entities or []
    return any(e.type in (MessageEntityType.URL, MessageEntityType.TEXT_LINK) for e in entities)


def _has_email(message: Message) -> bool:
    entities = message.entities or message.caption_entities or []
    return any(e.type == MessageEntityType.EMAIL for e in entities)


def _has_phone(message: Message) -> bool:
    entities = message.entities or message.caption_entities or []
    return any(e.type == MessageEntityType.PHONE_NUMBER for e in entities)


def _has_command(message: Message) -> bool:
    return any(e.type == MessageEntityType.BOT_COMMAND for e in (message.entities or []))


def _has_inline(message: Message) -> bool:
    return message.via_bot is not None


def _is_forward_from_user(message: Message) -> bool:
    return bool(message.forward_from) and not message.forward_from_chat


def _is_forward_from_channel(message: Message) -> bool:
    return bool(message.forward_from_chat)


def _is_any_forward(message: Message) -> bool:
    return bool(message.forward_from or message.forward_from_chat)


def _is_anon_channel(message: Message) -> bool:
    return bool(message.sender_chat and not message.forward_from_chat)


def _is_album(message: Message) -> bool:
    return bool(message.media_group_id)


def _is_forward_story(message: Message) -> bool:
    return bool(getattr(message, "forward_story", None) or getattr(message, "story", None))


def _is_external_reply(message: Message) -> bool:
    return bool(getattr(message, "external_reply", None))


def _is_checklist(message: Message) -> bool:
    return bool(getattr(message, "checklist", None))


# ============================================================
# SETUP
# ============================================================

async def setup_locks_handlers(client: Client):

    # ── /locktypes ────────────────────────────────────────────
    @client.on_message(filters.command("locktypes") & filters.group)
    async def locktypes_command(_, message: Message):
        await message.reply_text(LOCK_TYPES_TEXT, parse_mode=ParseMode.HTML)

    # ── /lock ─────────────────────────────────────────────────
    @client.on_message(filters.command("lock") & filters.group)
    async def lock_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if not await is_user_admin(client, chat_id, user_id):
            await message.reply_text("Only admins can lock permissions.", parse_mode=ParseMode.HTML)
            return

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text(
                "Please specify what to lock.\n"
                "<code>/lock &lt;type&gt;</code> or <code>/lock all</code>\n"
                "Use <code>/locktypes</code> to see all types.",
                parse_mode=ParseMode.HTML
            )
            return

        raw_args = parts[1].strip()

        if raw_args.lower() in ("all", "everything"):
            try:
                await client.set_chat_permissions(chat_id, _all_locked())
            except (ChatAdminRequired, ChatNotModified):
                pass
            await enable_all_db_locks(chat_id)
            await message.reply_text("🔒 <b>All permissions locked</b> for this chat.", parse_mode=ParseMode.HTML)
            return

        requested = [t.strip().lower() for t in raw_args.split(",") if t.strip()]
        invalid, native_done, db_done = [], [], []

        has_native = any(t in NATIVE_LOCK_TYPES for t in requested)
        current_perms = None
        if has_native:
            current_perms = await _get_current_permissions(client, chat_id)

        for lock_type in requested:
            if lock_type not in ALL_LOCK_TYPES:
                invalid.append(lock_type)
                continue
            if lock_type in NATIVE_LOCK_TYPES:
                try:
                    new_perms = _build_permissions(current_perms, lock_type, locking=True)
                    await client.set_chat_permissions(chat_id, new_perms)
                    current_perms = new_perms
                    native_done.append(lock_type)
                except ChatAdminRequired:
                    await message.reply_text("I need admin rights to change permissions.", parse_mode=ParseMode.HTML)
                    return
                except ChatNotModified:
                    native_done.append(lock_type)
            else:
                db_done.append(lock_type)

        if db_done:
            await enable_multiple_locks(chat_id, db_done)

        lines = []
        all_done = native_done + db_done
        if all_done:
            lines.append("🔒 Locked: " + ", ".join(f"<code>{t}</code>" for t in all_done))
        if invalid:
            lines.append("⚠️ Unknown: " + ", ".join(f"<code>{t}</code>" for t in invalid))
            lines.append("Use <code>/locktypes</code> to see valid types.")
        if lines:
            await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    # ── /unlock ───────────────────────────────────────────────
    @client.on_message(filters.command("unlock") & filters.group)
    async def unlock_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        if not await is_user_admin(client, chat_id, user_id):
            await message.reply_text("Only admins can unlock permissions.", parse_mode=ParseMode.HTML)
            return

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text(
                "Please specify what to unlock.\n"
                "<code>/unlock &lt;type&gt;</code> or <code>/unlock all</code>\n"
                "Use <code>/locktypes</code> to see all types.",
                parse_mode=ParseMode.HTML
            )
            return

        raw_args = parts[1].strip()

        if raw_args.lower() in ("all", "everything"):
            try:
                await client.set_chat_permissions(chat_id, _all_unlocked())
            except (ChatAdminRequired, ChatNotModified):
                pass
            await disable_all_locks(chat_id)
            await message.reply_text("🔓 <b>All permissions unlocked</b> for this chat.", parse_mode=ParseMode.HTML)
            return

        requested = [t.strip().lower() for t in raw_args.split(",") if t.strip()]
        invalid, native_done, db_done = [], [], []

        has_native = any(t in NATIVE_LOCK_TYPES for t in requested)
        current_perms = None
        if has_native:
            current_perms = await _get_current_permissions(client, chat_id)

        for lock_type in requested:
            if lock_type not in ALL_LOCK_TYPES:
                invalid.append(lock_type)
                continue
            if lock_type in NATIVE_LOCK_TYPES:
                try:
                    new_perms = _build_permissions(current_perms, lock_type, locking=False)
                    await client.set_chat_permissions(chat_id, new_perms)
                    current_perms = new_perms
                    native_done.append(lock_type)
                except ChatAdminRequired:
                    await message.reply_text("I need admin rights to change permissions.", parse_mode=ParseMode.HTML)
                    return
                except ChatNotModified:
                    native_done.append(lock_type)
            else:
                db_done.append(lock_type)

        if db_done:
            await disable_multiple_locks(chat_id, db_done)

        lines = []
        all_done = native_done + db_done
        if all_done:
            lines.append("🔓 Unlocked: " + ", ".join(f"<code>{t}</code>" for t in all_done))
        if invalid:
            lines.append("⚠️ Unknown: " + ", ".join(f"<code>{t}</code>" for t in invalid))
            lines.append("Use <code>/locktypes</code> to see valid types.")
        if lines:
            await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    # ── /locks ────────────────────────────────────────────────
    @client.on_message(filters.command("locks") & filters.group)
    async def locks_command(client: Client, message: Message):
        chat_id = message.chat.id

        db_locks = await get_chat_locks(chat_id)
        perms = await _get_current_permissions(client, chat_id)

        native_active = []
        if perms:
            if perms.can_send_messages is False:
                native_active.append("msg")
            if _is_media_locked(perms):
                native_active.append("media")
            if perms.can_send_other_messages is False:
                native_active.append("stickers / animations / games")
            if perms.can_add_web_page_previews is False:
                native_active.append("webprev")
            if perms.can_send_polls is False:
                native_active.append("polls")
            if perms.can_change_info is False:
                native_active.append("info")
            if perms.can_invite_users is False:
                native_active.append("invite")
            if perms.can_pin_messages is False:
                native_active.append("pin")

        if not db_locks and not native_active:
            await message.reply_text("🔓 No active locks in this chat.", parse_mode=ParseMode.HTML)
            return

        lines = ["<b>🔒 Active Locks:</b>\n"]
        if native_active:
            lines.append("<b>Telegram Permissions (disabled):</b>")
            for n in native_active:
                lines.append(f"  • <code>{n}</code>")
            lines.append("")
        if db_locks:
            lines.append("<b>Content Locks (bot enforced):</b>")
            for lock_type in sorted(db_locks.keys()):
                desc = LOCK_DESCRIPTIONS.get(lock_type, "")
                entry = f"  • <code>{lock_type}</code>"
                if desc:
                    entry += f" — {desc}"
                lines.append(entry)

        await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    # ── Service: bot added → ban if bot lock on ───────────────
    @client.on_message(filters.service & filters.group, group=5)
    async def service_bot_lock(client: Client, message: Message):
        if message.service != MessageServiceType.NEW_CHAT_MEMBERS:
            return
        chat_id = message.chat.id
        locks = await get_chat_locks(chat_id)
        if not locks.get("bot"):
            return
        for member in (message.new_chat_members or []):
            if not member.is_bot:
                continue
            try:
                from datetime import datetime, timedelta
                until = datetime.now() + timedelta(minutes=5)
                await client.ban_chat_member(chat_id, member.id, until_date=until)
                await asyncio.sleep(0.5)
            except (UserAdminInvalid, ChatAdminRequired):
                continue
            except Exception as e:
                logger.error(f"Bot lock ban error in {chat_id}: {e}")

    # ── Message watcher — enforce DB locks ────────────────────
    @client.on_message(filters.group & ~filters.me, group=6)
    async def lock_message_watcher(client: Client, message: Message):
        chat_id = message.chat.id

        locks = await get_chat_locks(chat_id)
        if not locks:
            return

        user = message.from_user
        if user:
            try:
                member = await client.get_chat_member(chat_id, user.id)
                if member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
                    return
            except Exception:
                pass

        async def _delete():
            try:
                await message.delete()
            except Exception:
                pass

        if locks.get("anonchannel")    and _is_anon_channel(message):       await _delete(); return
        if locks.get("allforward")     and _is_any_forward(message):        await _delete(); return
        if locks.get("userforward")    and _is_forward_from_user(message):  await _delete(); return
        if locks.get("channelforward") and _is_forward_from_channel(message): await _delete(); return
        if locks.get("forwardstory")   and _is_forward_story(message):      await _delete(); return
        if locks.get("externalreply")  and _is_external_reply(message):     await _delete(); return
        if locks.get("inline")         and _has_inline(message):            await _delete(); return

        media = message.media
        if media:
            if locks.get("audio")    and media == MessageMediaType.AUDIO:     await _delete(); return
            if locks.get("voice")    and media == MessageMediaType.VOICE:     await _delete(); return
            if locks.get("video")    and media == MessageMediaType.VIDEO:     await _delete(); return
            if locks.get("gif")      and media == MessageMediaType.ANIMATION: await _delete(); return
            if locks.get("document") and media == MessageMediaType.DOCUMENT:  await _delete(); return
            if locks.get("contact")  and media == MessageMediaType.CONTACT:   await _delete(); return
            if locks.get("poll")     and media == MessageMediaType.POLL:      await _delete(); return

        if locks.get("checklist") and _is_checklist(message): await _delete(); return
        if locks.get("album")     and _is_album(message):     await _delete(); return

        if locks.get("links")       and _has_links(message):        await _delete(); return
        if locks.get("email")       and _has_email(message):        await _delete(); return
        if locks.get("phone")       and _has_phone(message):        await _delete(); return
        if locks.get("command")     and _has_command(message):      await _delete(); return
        if locks.get("emojicustom") and _has_custom_emoji(message): await _delete(); return
        if locks.get("emoji"):
            text = message.text or message.caption or ""
            if _has_emoji(text):
                await _delete(); return
        if locks.get("comment") and message.sender_chat:
            await _delete(); return

    logger.info("✅ Locks handlers setup complete")
