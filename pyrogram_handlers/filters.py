import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from pyrogram.errors import ChatAdminRequired, BadRequest, FloodWait, MessageDeleteForbidden

from pyrogram_handlers.utils import (
    is_user_admin,
    log_error
)

from database_management import (
    add_filter,
    get_filter,
    get_all_filters,
    delete_filter,
    delete_all_filters
)

logger = logging.getLogger(__name__)

# ============================================================
# RAM CACHE — DB pe har message pe query nahi hogi
# { chat_id: { "keyword": { filter_data } } }
# ============================================================
_filters_cache: dict = {}
_cache_loaded: set = set()  # Kaunse groups cache ho chuke hain


async def _load_filters_to_cache(chat_id: int):
    """DB se group ke saare filters ek baar RAM mein load karo."""
    filters_list = await get_all_filters(chat_id)
    _filters_cache[chat_id] = {
        f["keyword"]: {
            "text": f.get("text"),
            "media_type": f.get("media_type"),
            "media_id": f.get("media_id"),
        }
        for f in filters_list
    }
    _cache_loaded.add(chat_id)


def _add_to_cache(chat_id: int, keyword: str, text, media_type, media_id):
    """Naya filter cache mein add karo."""
    if chat_id not in _filters_cache:
        _filters_cache[chat_id] = {}
    _filters_cache[chat_id][keyword.lower()] = {
        "text": text,
        "media_type": media_type,
        "media_id": media_id,
    }


def _remove_from_cache(chat_id: int, keyword: str):
    """Ek filter cache se hatao."""
    if chat_id in _filters_cache:
        _filters_cache[chat_id].pop(keyword.lower(), None)


def _clear_cache(chat_id: int):
    """Group ke saare filters cache se hatao."""
    _filters_cache.pop(chat_id, None)
    _cache_loaded.discard(chat_id)


async def _ensure_cache(chat_id: int):
    """Agar cache nahi loaded toh load karo."""
    if chat_id not in _cache_loaded:
        await _load_filters_to_cache(chat_id)


async def setup_filter_handlers(client: Client):

    # ============================================================
    # /filter command
    # Usage 1: /filter <keyword> <reply text>
    # Usage 2: /filter <keyword> — reply to a message (text/photo/video/gif)
    # ============================================================
    @client.on_message(filters.command("filter") & filters.group)
    async def filter_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None

            # Admin check
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text(
                        "Only admins can add filters.",
                        parse_mode=ParseMode.HTML
                    )
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "<b>I need admin privileges to verify permissions.</b>\n\n"
                    "Please promote me to admin first.",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception:
                await message.reply_text("Only admins can add filters.", parse_mode=ParseMode.HTML)
                return

            parts = message.text.split(maxsplit=2)

            # /filter akela — usage batao
            if len(parts) < 2:
                await message.reply_text(
                    "<b>How to add a filter:</b>\n\n"
                    "<b>Option 1</b> — Text reply:\n"
                    "<code>/filter keyword your reply message</code>\n\n"
                    "<b>Option 2</b> — Reply to a message:\n"
                    "Reply to any message with <code>/filter keyword</code>\n\n"
                    "<b>Example:</b>\n"
                    "<code>/filter hello Hello! How are you?</code>",
                    parse_mode=ParseMode.HTML
                )
                return

            keyword = parts[1].lower().strip()

            if not keyword:
                await message.reply_text("Keyword cannot be empty.", parse_mode=ParseMode.HTML)
                return

            media_type = None
            media_id = None
            text = None

            # Option 2: Reply to a message
            if message.reply_to_message:
                replied = message.reply_to_message

                if replied.photo:
                    media_type = "photo"
                    media_id = replied.photo.file_id
                    text = replied.caption.html if replied.caption else None
                elif replied.video:
                    media_type = "video"
                    media_id = replied.video.file_id
                    text = replied.caption.html if replied.caption else None
                elif replied.animation:
                    media_type = "animation"
                    media_id = replied.animation.file_id
                    text = replied.caption.html if replied.caption else None
                elif replied.sticker:
                    media_type = "sticker"
                    media_id = replied.sticker.file_id
                    text = None
                elif replied.text:
                    text = replied.text.html
                else:
                    await message.reply_text(
                        "This media type is not supported as a filter.
"
                        "Try again with: Text, Photo, Video, GIF or Sticker.",
                        parse_mode=ParseMode.HTML
                    )
                    return

            # Option 1: Inline text — /filter keyword reply message
            elif len(parts) >= 3:
                # .html se formatting preserve hogi
                cmd_and_keyword_len = len(parts[0]) + 1 + len(parts[1]) + 1
                full_html = message.text.html
                text = full_html[cmd_and_keyword_len:].strip()

            else:
                await message.reply_text(
                    "<b>Please provide a reply message.</b>\n\n"
                    "Either write text after keyword or reply to a message.\n\n"
                    "<code>/filter keyword your reply</code>",
                    parse_mode=ParseMode.HTML
                )
                return

            # DB mein save karo
            success = await add_filter(
                chat_id=chat_id,
                keyword=keyword,
                media_type=media_type,
                media_id=media_id,
                text=text
            )

            if success:
                # Cache update karo
                _add_to_cache(chat_id, keyword, text, media_type, media_id)
                await message.reply_text(
                    f"Filter <code>{keyword}</code> saved successfully!",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    "Failed to save filter. Please try again.",
                    parse_mode=ParseMode.HTML
                )

        except Exception as e:
            log_error("filter_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred. Please try again.", parse_mode=ParseMode.HTML)


    # ============================================================
    # /filters command — group ke saare active filters show karo
    # ============================================================
    @client.on_message(filters.command("filters") & filters.group)
    async def filters_list_command(client: Client, message: Message):
        chat_id = None
        try:
            chat_id = message.chat.id

            await _ensure_cache(chat_id)

            chat_filters = _filters_cache.get(chat_id, {})

            if not chat_filters:
                await message.reply_text(
                    "No active filters in this group.\n\n"
                    "Use <code>/filter keyword reply</code> to add one.",
                    parse_mode=ParseMode.HTML
                )
                return

            keywords = sorted(chat_filters.keys())
            keyword_list = "\n".join([f"- <code>{kw}</code>" for kw in keywords])

            await message.reply_text(
                f"<b>Active filters ({len(keywords)}):</b>\n\n"
                f"{keyword_list}",
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            log_error("filters_list_command", e, chat_id=chat_id or 0)
            await message.reply_text("An error occurred. Please try again.", parse_mode=ParseMode.HTML)


    # ============================================================
    # /stop <keyword> — ek specific filter delete karo
    # ============================================================
    @client.on_message(filters.command("stop") & filters.group)
    async def stop_filter_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None

            # Admin check
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can remove filters.", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "<b>I need admin privileges to verify permissions.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception:
                await message.reply_text("Only admins can remove filters.", parse_mode=ParseMode.HTML)
                return

            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                await message.reply_text(
                    "<b>Usage:</b> <code>/stop keyword</code>\n\n"
                    "Use <code>/filters</code> to see all active filters.",
                    parse_mode=ParseMode.HTML
                )
                return

            keyword = parts[1].lower().strip()

            await _ensure_cache(chat_id)
            chat_filters = _filters_cache.get(chat_id, {})

            if keyword not in chat_filters:
                await message.reply_text(
                    f"No filter found for <code>{keyword}</code>.\n\n"
                    f"Use <code>/filters</code> to see all active filters.",
                    parse_mode=ParseMode.HTML
                )
                return

            # DB se delete karo
            success = await delete_filter(chat_id, keyword)

            if success:
                _remove_from_cache(chat_id, keyword)
                await message.reply_text(
                    f"Filter <code>{keyword}</code> removed successfully!",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text("Failed to remove filter. Please try again.", parse_mode=ParseMode.HTML)

        except Exception as e:
            log_error("stop_filter_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred. Please try again.", parse_mode=ParseMode.HTML)


    # ============================================================
    # /stopallfilters — group ke saare filters ek saath delete karo
    # ============================================================
    @client.on_message(filters.command("stopallfilters") & filters.group)
    async def stop_all_filters_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None

            # Admin check
            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can remove filters.", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "<b>I need admin privileges to verify permissions.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception:
                await message.reply_text("Only admins can remove filters.", parse_mode=ParseMode.HTML)
                return

            await _ensure_cache(chat_id)
            chat_filters = _filters_cache.get(chat_id, {})

            if not chat_filters:
                await message.reply_text(
                    "No active filters in this group.",
                    parse_mode=ParseMode.HTML
                )
                return

            total = len(chat_filters)

            # DB se saare delete karo
            deleted = await delete_all_filters(chat_id)

            # Cache clear karo
            _clear_cache(chat_id)

            await message.reply_text(
                f"All <b>{deleted}</b> filters removed successfully!",
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            log_error("stop_all_filters_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred. Please try again.", parse_mode=ParseMode.HTML)


    # ============================================================
    # AUTO-TRIGGER — Har message check karo
    # RAM cache use hoga — DB call nahi hogi har message pe
    # ============================================================
    @client.on_message(filters.group & filters.text)
    async def filter_trigger(client: Client, message: Message):
        try:
            chat_id = message.chat.id

            # Cache load karo agar nahi hai
            await _ensure_cache(chat_id)

            chat_filters = _filters_cache.get(chat_id)
            if not chat_filters:
                return

            # Message text lowercase mein
            msg_text = message.text.lower() if message.text else ""
            if not msg_text:
                return

            # Har keyword check karo — word match ya substring match
            matched_filter = None
            for keyword, filter_data in chat_filters.items():
                # Word boundary check — "hi" se "this" trigger nahi hoga
                # Exact word match ya start/end mein ho
                if (keyword == msg_text or
                    msg_text.startswith(keyword + " ") or
                    msg_text.endswith(" " + keyword) or
                    (" " + keyword + " ") in msg_text):
                    matched_filter = filter_data
                    break

            if not matched_filter:
                return

            # Filter ka response bhejo
            text = matched_filter.get("text")
            media_type = matched_filter.get("media_type")
            media_id = matched_filter.get("media_id")

            try:
                if media_type and media_id:
                    if media_type == "photo":
                        await message.reply_photo(
                            photo=media_id,
                            caption=text,
                            parse_mode=ParseMode.HTML
                        )
                    elif media_type == "video":
                        await message.reply_video(
                            video=media_id,
                            caption=text,
                            parse_mode=ParseMode.HTML
                        )
                    elif media_type == "animation":
                        await message.reply_animation(
                            animation=media_id,
                            caption=text,
                            parse_mode=ParseMode.HTML
                        )
                    elif media_type == "sticker":
                        await message.reply_sticker(sticker=media_id)
                elif text:
                    await message.reply_text(
                        text=text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
            except (BadRequest, MessageDeleteForbidden):
                pass
            except FloodWait as e:
                import asyncio
                await asyncio.sleep(e.value)

        except Exception as e:
            log_error("filter_trigger", e, chat_id=message.chat.id)

    logger.info("✅ Filter handlers setup complete")
