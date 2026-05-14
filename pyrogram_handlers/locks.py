import asyncio
import unicodedata
from typing import Optional

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
    disable_multiple_locks,
    disable_all_locks,
    DB_LOCK_TYPES,
)

LOCK_DESCRIPTIONS = {
    "all":            "All messages and media blocked",
    "msg":            "Text messages",
    "links":          "URLs and hyperlinks",
    "allforward":     "Forwarded messages from users and channels",
    "userforward":    "Forwarded messages from users only",
    "channelforward": "Forwarded messages from channels only",
    "anonchannel":    "Messages sent as a channel",
    "bot":            "Adding new bots to the group",
    "audio":          "Audio files and music",
    "voice":          "Voice messages",
    "video":          "Video messages",
    "gif":            "GIF animations",
    "document":       "Documents and uncompressed files",
    "album":          "Photo or document albums",
    "contact":        "Contact cards",
    "stickers":       "Sticker messages",
    "animations":     "Animation messages",
    "games":          "Game messages",
    "emoji":          "Messages containing any emoji",
    "emojicustom":    "Messages containing custom Telegram emoji",
    "command":        "Telegram bot commands",
    "email":          "Messages containing email addresses",
    "phone":          "Messages containing phone numbers",
    "poll":           "Poll messages",
    "checklist":      "Telegram checklist messages",
    "forwardstory":   "Forwarded user stories",
    "externalreply":  "Replies to messages from other chats",
    "comment":        "Messages from non-member channel commenters",
    "inline":         "Messages sent via inline bots",
    "webprev":        "Web page link previews",
    "invite":         "Inviting users to the group",
    "pin":            "Pinning messages",
    "info":           "Changing group info",
}

LOCK_TYPES_TEXT = """<b>🔒 Available Lock Types:</b>

<b>── Global ──</b>
• <code>all</code>         — Lock everything (native Telegram permissions)

<b>── Content ──</b>
• <code>msg</code>         — Text messages
• <code>audio</code>       — Audio files and music
• <code>voice</code>       — Voice messages
• <code>video</code>       — Video messages
• <code>gif</code>         — GIF animations
• <code>document</code>    — Documents and uncompressed files
• <code>album</code>       — Photo or document albums
• <code>contact</code>     — Contact cards
• <code>stickers</code>    — Sticker messages
• <code>animations</code>  — Animation messages
• <code>games</code>       — Game messages
• <code>poll</code>        — Poll messages
• <code>checklist</code>   — Telegram checklists
• <code>inline</code>      — Messages sent via inline bots

<b>── Text Patterns ──</b>
• <code>links</code>       — URLs and hyperlinks
• <code>email</code>       — Messages with email addresses
• <code>phone</code>       — Messages with phone numbers
• <code>command</code>     — Bot commands (e.g. /start)
• <code>emoji</code>       — Messages containing any emoji
• <code>emojicustom</code> — Custom Telegram emoji
• <code>webprev</code>     — Web page link previews

<b>── Forwards ──</b>
• <code>allforward</code>     — All forwarded messages
• <code>userforward</code>    — Forwards from users
• <code>channelforward</code> — Forwards from channels
• <code>forwardstory</code>   — Forwarded user stories

<b>── User Actions ──</b>
• <code>bot</code>         — Adding bots to the group
• <code>invite</code>      — Inviting users
• <code>pin</code>         — Pinning messages
• <code>info</code>        — Changing group info
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

ALL_LOCKED = ChatPermissions(
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

ALL_UNLOCKED = ChatPermissions(
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


def _has_emoji(text: str) -> bool:
    return any(unicodedata.category(c) in ("So", "Cs") for c in text) if text else False


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


async def setup_locks_handlers(client: Client):

    @client.on_message(filters.command("locktypes") & filters.group)
    async def locktypes_command(_, message: Message):
        await message.reply_text(LOCK_TYPES_TEXT, parse_mode=ParseMode.HTML)

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
                "Specify what to lock.\n<code>/lock &lt;type&gt;</code> or <code>/lock all</code>\nSee <code>/locktypes</code>.",
                parse_mode=ParseMode.HTML
            )
            return

        raw = parts[1].strip()

        if raw.lower() in ("all", "everything"):
            try:
                await client.set_chat_permissions(chat_id, ALL_LOCKED)
            except (ChatAdminRequired, ChatNotModified):
                pass
            await enable_multiple_locks(chat_id, ["all"])
            await message.reply_text("🔒 <b>All permissions locked.</b>", parse_mode=ParseMode.HTML)
            return

        requested = [t.strip().lower() for t in raw.split(",") if t.strip()]
        valid = [t for t in requested if t in DB_LOCK_TYPES]
        invalid = [t for t in requested if t not in DB_LOCK_TYPES]

        if valid:
            await enable_multiple_locks(chat_id, valid)

        lines = []
        if valid:
            lines.append("🔒 Locked: " + ", ".join(f"<code>{t}</code>" for t in valid))
        if invalid:
            lines.append("⚠️ Unknown: " + ", ".join(f"<code>{t}</code>" for t in invalid))
            lines.append("Use <code>/locktypes</code> to see valid types.")
        if lines:
            await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

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
                "Specify what to unlock.\n<code>/unlock &lt;type&gt;</code> or <code>/unlock all</code>\nSee <code>/locktypes</code>.",
                parse_mode=ParseMode.HTML
            )
            return

        raw = parts[1].strip()

        if raw.lower() in ("all", "everything"):
            try:
                await client.set_chat_permissions(chat_id, ALL_UNLOCKED)
            except (ChatAdminRequired, ChatNotModified):
                pass
            await disable_all_locks(chat_id)
            await message.reply_text("🔓 <b>All permissions unlocked.</b>", parse_mode=ParseMode.HTML)
            return

        requested = [t.strip().lower() for t in raw.split(",") if t.strip()]
        valid = [t for t in requested if t in DB_LOCK_TYPES]
        invalid = [t for t in requested if t not in DB_LOCK_TYPES]

        if valid:
            await disable_multiple_locks(chat_id, valid)

        lines = []
        if valid:
            lines.append("🔓 Unlocked: " + ", ".join(f"<code>{t}</code>" for t in valid))
        if invalid:
            lines.append("⚠️ Unknown: " + ", ".join(f"<code>{t}</code>" for t in invalid))
            lines.append("Use <code>/locktypes</code> to see valid types.")
        if lines:
            await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    @client.on_message(filters.command("locks") & filters.group)
    async def locks_command(_, message: Message):
        chat_id = message.chat.id
        locks = await get_chat_locks(chat_id)

        if not locks:
            await message.reply_text("🔓 No active locks in this chat.", parse_mode=ParseMode.HTML)
            return

        lines = ["<b>🔒 Active Locks:</b>\n"]
        for lock_type in sorted(locks.keys()):
            desc = LOCK_DESCRIPTIONS.get(lock_type, "")
            entry = f"  • <code>{lock_type}</code>"
            if desc:
                entry += f" — {desc}"
            lines.append(entry)

        await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    @client.on_message(filters.service & filters.group, group=5)
    async def service_bot_lock(client: Client, message: Message):
        if message.service != MessageServiceType.NEW_CHAT_MEMBERS:
            return
        locks = await get_chat_locks(message.chat.id)
        if not locks.get("bot"):
            return
        for member in (message.new_chat_members or []):
            if not member.is_bot:
                continue
            try:
                from datetime import datetime, timedelta
                await client.ban_chat_member(message.chat.id, member.id, until_date=datetime.now() + timedelta(minutes=5))
                await asyncio.sleep(0.5)
            except (UserAdminInvalid, ChatAdminRequired):
                continue
            except Exception:
                pass

    @client.on_message(filters.group & ~filters.me, group=6)
    async def lock_watcher(client: Client, message: Message):
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

        async def _del():
            try:
                await message.delete()
            except Exception:
                pass

        if locks.get("all"):
            await _del(); return

        if locks.get("anonchannel") and message.sender_chat and not message.forward_from_chat:
            await _del(); return

        if locks.get("allforward") and (message.forward_from or message.forward_from_chat):
            await _del(); return
        if locks.get("userforward") and message.forward_from and not message.forward_from_chat:
            await _del(); return
        if locks.get("channelforward") and message.forward_from_chat:
            await _del(); return
        if locks.get("forwardstory") and (getattr(message, "forward_story", None) or getattr(message, "story", None)):
            await _del(); return

        if locks.get("externalreply") and getattr(message, "external_reply", None):
            await _del(); return

        if locks.get("inline") and message.via_bot:
            await _del(); return

        media = message.media
        if media:
            if locks.get("audio")    and media == MessageMediaType.AUDIO:     await _del(); return
            if locks.get("voice")    and media == MessageMediaType.VOICE:     await _del(); return
            if locks.get("video")    and media == MessageMediaType.VIDEO:     await _del(); return
            if locks.get("gif")      and media == MessageMediaType.ANIMATION: await _del(); return
            if locks.get("document") and media == MessageMediaType.DOCUMENT:  await _del(); return
            if locks.get("contact")  and media == MessageMediaType.CONTACT:   await _del(); return
            if locks.get("poll")     and media == MessageMediaType.POLL:      await _del(); return
            if locks.get("stickers") and media == MessageMediaType.STICKER:   await _del(); return

        if locks.get("checklist") and getattr(message, "checklist", None):
            await _del(); return

        if locks.get("album") and message.media_group_id:
            await _del(); return

        if locks.get("animations") and media == MessageMediaType.ANIMATION:
            await _del(); return
        if locks.get("games") and media == MessageMediaType.GAME:
            await _del(); return

        if locks.get("msg") and message.text and not message.via_bot:
            await _del(); return

        if locks.get("links")       and _has_links(message):        await _del(); return
        if locks.get("email")       and _has_email(message):        await _del(); return
        if locks.get("phone")       and _has_phone(message):        await _del(); return
        if locks.get("command")     and _has_command(message):      await _del(); return
        if locks.get("emojicustom") and _has_custom_emoji(message): await _del(); return
        if locks.get("emoji"):
            text = message.text or message.caption or ""
            if _has_emoji(text):
                await _del(); return

        if locks.get("webprev"):
            entities = message.entities or message.caption_entities or []
            if any(e.type == MessageEntityType.URL for e in entities):
                await _del(); return

        if locks.get("comment") and message.sender_chat:
            await _del(); return
