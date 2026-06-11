import asyncio
import unicodedata
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions
from pyrogram.enums import (
    ParseMode,
    ChatMemberStatus,
    ChatMembersFilter,
    MessageEntityType,
    MessageMediaType,
    MessageServiceType,
)
from pyrogram.errors import ChatAdminRequired, ChatNotModified, UserAdminInvalid

from pyrogram_handlers.caching import get_admin_permissions, is_chat_cached
from utils.language import get_chat_lang_dict
from mongo.locksdb import (
    get_chat_locks,
    enable_multiple_locks,
    disable_multiple_locks,
    disable_all_locks,
    DB_LOCK_TYPES,
)

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


async def _check_admin(client: Client, chat_id: int, user_id: int) -> bool:
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


async def _bot_can_delete(client: Client, chat_id: int) -> bool:
    perms = get_admin_permissions(chat_id, (await client.get_me()).id)
    if perms is not None:
        return perms.get("can_delete_messages", False)
    try:
        bot    = await client.get_me()
        member = await client.get_chat_member(chat_id, bot.id)
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return False
        return bool(getattr(member.privileges, "can_delete_messages", False))
    except Exception:
        return False


def _is_admin_in_cache(chat_id: int, user_id: int) -> bool:
    return get_admin_permissions(chat_id, user_id) is not None


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
        lang = await get_chat_lang_dict(message.chat.id)
        await message.reply_text(lang["lock_types_text"], parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("lock") & filters.group)
    async def lock_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        lang    = await get_chat_lang_dict(chat_id)

        if not await _check_admin(client, chat_id, user_id):
            await message.reply_text(lang["only_admins_lock"], parse_mode=ParseMode.HTML)
            return

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text(lang["lock_usage"], parse_mode=ParseMode.HTML)
            return

        raw = parts[1].strip()

        if raw.lower() in ("all", "everything"):
            try:
                await client.set_chat_permissions(chat_id, ALL_LOCKED)
            except (ChatAdminRequired, ChatNotModified):
                pass
            await enable_multiple_locks(chat_id, ["all"])
            await message.reply_text(lang["all_locked"], parse_mode=ParseMode.HTML)
            return

        requested = [t.strip().lower() for t in raw.split(",") if t.strip()]
        requested = [t for t in requested if t != "all"]

        valid   = [t for t in requested if t in DB_LOCK_TYPES]
        invalid = [t for t in requested if t not in DB_LOCK_TYPES]

        if valid:
            if not await _bot_can_delete(client, chat_id):
                await message.reply_text(lang["lock_need_delete_perm"], parse_mode=ParseMode.HTML)
                return
            await enable_multiple_locks(chat_id, valid)

        lines = []
        if valid:
            lines.append(lang["locked_types"].format(types=", ".join(f"<code>{t}</code>" for t in valid)))
        if invalid:
            lines.append(lang["unknown_types"].format(types=", ".join(f"<code>{t}</code>" for t in invalid)))
            lines.append(lang["see_locktypes"])
        if lines:
            await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("unlock") & filters.group)
    async def unlock_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        lang    = await get_chat_lang_dict(chat_id)

        if not await _check_admin(client, chat_id, user_id):
            await message.reply_text(lang["only_admins_unlock"], parse_mode=ParseMode.HTML)
            return

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text(lang["unlock_usage"], parse_mode=ParseMode.HTML)
            return

        raw = parts[1].strip()

        if raw.lower() in ("all", "everything"):
            try:
                await client.set_chat_permissions(chat_id, ALL_UNLOCKED)
            except (ChatAdminRequired, ChatNotModified):
                pass
            await disable_all_locks(chat_id)
            await message.reply_text(lang["all_unlocked"], parse_mode=ParseMode.HTML)
            return

        requested = [t.strip().lower() for t in raw.split(",") if t.strip()]
        valid   = [t for t in requested if t in DB_LOCK_TYPES]
        invalid = [t for t in requested if t not in DB_LOCK_TYPES]

        if valid:
            await disable_multiple_locks(chat_id, valid)

        lines = []
        if valid:
            lines.append(lang["unlocked_types"].format(types=", ".join(f"<code>{t}</code>" for t in valid)))
        if invalid:
            lines.append(lang["unknown_types"].format(types=", ".join(f"<code>{t}</code>" for t in invalid)))
            lines.append(lang["see_locktypes"])
        if lines:
            await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("locks") & filters.group)
    async def locks_command(_, message: Message):
        chat_id = message.chat.id
        lang    = await get_chat_lang_dict(chat_id)
        locks   = await get_chat_locks(chat_id)

        if not locks:
            await message.reply_text(lang["no_active_locks"], parse_mode=ParseMode.HTML)
            return

        lines = [f"<b>{lang['active_locks_header']}</b>\n"]
        for lock_type in sorted(locks.keys()):
            desc_key = f"lock_desc_{lock_type}"
            desc     = lang.get(desc_key, "")
            entry    = f"  • <code>{lock_type}</code>"
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
                await client.ban_chat_member(
                    message.chat.id, member.id,
                    until_date=datetime.now() + timedelta(minutes=5)
                )
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
            if _is_admin_in_cache(chat_id, user.id):
                return
            try:
                member = await client.get_chat_member(chat_id, user.id)
                if member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
                    return
            except Exception:
                pass

        async def _del():
            try:
                await message.delete()
                return True
            except Exception:
                return False

        async def _no_perm_disable():
            await disable_all_locks(chat_id)
            try:
                lang = await get_chat_lang_dict(chat_id)
                await client.send_message(
                    chat_id,
                    lang["lock_no_delete_perm_disabled"],
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass

        should_delete = False

        if locks.get("all"):
            should_delete = True
        elif locks.get("anonchannel") and message.sender_chat and not message.forward_from_chat:
            should_delete = True
        elif locks.get("allforward") and (message.forward_from or message.forward_from_chat):
            should_delete = True
        elif locks.get("userforward") and message.forward_from and not message.forward_from_chat:
            should_delete = True
        elif locks.get("channelforward") and message.forward_from_chat:
            should_delete = True
        elif locks.get("forwardstory") and (getattr(message, "forward_story", None) or getattr(message, "story", None)):
            should_delete = True
        elif locks.get("externalreply") and getattr(message, "external_reply", None):
            should_delete = True
        elif locks.get("inline") and message.via_bot:
            should_delete = True
        else:
            media = message.media
            if media:
                if locks.get("audio")        and media == MessageMediaType.AUDIO:     should_delete = True
                elif locks.get("voice")      and media == MessageMediaType.VOICE:     should_delete = True
                elif locks.get("video")      and media == MessageMediaType.VIDEO:     should_delete = True
                elif locks.get("gif")        and media == MessageMediaType.ANIMATION: should_delete = True
                elif locks.get("document")   and media == MessageMediaType.DOCUMENT:  should_delete = True
                elif locks.get("contact")    and media == MessageMediaType.CONTACT:   should_delete = True
                elif locks.get("poll")       and media == MessageMediaType.POLL:      should_delete = True
                elif locks.get("stickers")   and media == MessageMediaType.STICKER:   should_delete = True
                elif locks.get("animations") and media == MessageMediaType.ANIMATION: should_delete = True
                elif locks.get("games")      and media == MessageMediaType.GAME:      should_delete = True

            if not should_delete and locks.get("checklist") and getattr(message, "checklist", None):
                should_delete = True
            if not should_delete and locks.get("album") and message.media_group_id:
                should_delete = True
            if not should_delete and locks.get("msg") and message.text and not message.via_bot:
                should_delete = True
            if not should_delete and locks.get("links") and _has_links(message):
                should_delete = True
            if not should_delete and locks.get("email") and _has_email(message):
                should_delete = True
            if not should_delete and locks.get("phone") and _has_phone(message):
                should_delete = True
            if not should_delete and locks.get("command") and _has_command(message):
                should_delete = True
            if not should_delete and locks.get("emojicustom") and _has_custom_emoji(message):
                should_delete = True
            if not should_delete and locks.get("emoji"):
                text = message.text or message.caption or ""
                if _has_emoji(text):
                    should_delete = True
            if not should_delete and locks.get("webprev"):
                entities = message.entities or message.caption_entities or []
                if any(e.type == MessageEntityType.URL for e in entities):
                    should_delete = True
            if not should_delete and locks.get("comment") and message.sender_chat:
                should_delete = True

        if should_delete:
            deleted = await _del()
            if not deleted:
                await _no_perm_disable()
