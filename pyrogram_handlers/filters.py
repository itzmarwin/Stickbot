from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from pyrogram.errors import ChatAdminRequired, BadRequest, FloodWait, MessageDeleteForbidden
import asyncio

from pyrogram_handlers.utils import is_user_admin

from database_management import (
    add_filter,
    get_filter,
    get_all_filters,
    delete_filter,
    delete_all_filters
)

_filters_cache: dict = {}
_cache_loaded: set = set()


async def _load_filters_to_cache(chat_id: int):
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
    if chat_id not in _filters_cache:
        _filters_cache[chat_id] = {}
    _filters_cache[chat_id][keyword.lower()] = {
        "text": text,
        "media_type": media_type,
        "media_id": media_id,
    }


def _remove_from_cache(chat_id: int, keyword: str):
    if chat_id in _filters_cache:
        _filters_cache[chat_id].pop(keyword.lower(), None)


def _clear_cache(chat_id: int):
    _filters_cache.pop(chat_id, None)
    _cache_loaded.discard(chat_id)


async def _ensure_cache(chat_id: int):
    if chat_id not in _cache_loaded:
        await _load_filters_to_cache(chat_id)


async def setup_filter_handlers(client: Client):

    @client.on_message(filters.command("filter") & filters.group, group=0)
    async def filter_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        is_admin = await is_user_admin(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("Only admins can add filters.", parse_mode=ParseMode.HTML)
            return

        parts = message.text.split(maxsplit=2)

        if len(parts) < 2:
            await message.reply_text(
                "Add a filter with /filter &lt;keyword&gt; &lt;reply&gt; or reply to a message using /filter &lt;keyword&gt;.",
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
                    "This media type is not supported as a filter. Try again with: Text, Photo, Video, GIF or Sticker.",
                    parse_mode=ParseMode.HTML
                )
                return

        elif len(parts) >= 3:
            cmd_and_keyword_len = len(parts[0]) + 1 + len(parts[1]) + 1
            full_html = message.text.html
            text = full_html[cmd_and_keyword_len:].strip()

        else:
            await message.reply_text(
                "<b>Please provide a reply message.</b>\n"
                "Either write text after keyword or reply to a message.",
                parse_mode=ParseMode.HTML
            )
            return

        success = await add_filter(
            chat_id=chat_id,
            keyword=keyword,
            media_type=media_type,
            media_id=media_id,
            text=text
        )

        if success:
            _add_to_cache(chat_id, keyword, text, media_type, media_id)
            await message.reply_text(
                f"Filter <code>{keyword}</code> saved successfully!",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply_text("Failed to save filter. Please try again.", parse_mode=ParseMode.HTML)

    @client.on_message(filters.command("filters") & filters.group, group=0)
    async def filters_list_command(client: Client, message: Message):
        chat_id = message.chat.id

        await _ensure_cache(chat_id)

        chat_filters = _filters_cache.get(chat_id, {})

        if not chat_filters:
            await message.reply_text("No active filters in this group.", parse_mode=ParseMode.HTML)
            return

        keywords = sorted(chat_filters.keys())
        keyword_list = "\n".join([f"- <code>{kw}</code>" for kw in keywords])

        await message.reply_text(
            f"<b>Active filters:</b>\n\n{keyword_list}",
            parse_mode=ParseMode.HTML
        )

    @client.on_message(filters.command("stopfilter") & filters.group, group=0)
    async def stopfilter_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        is_admin = await is_user_admin(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("Only admins can remove filters.", parse_mode=ParseMode.HTML)
            return

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("You forgot the filter keyword", parse_mode=ParseMode.HTML)
            return

        keyword = parts[1].lower().strip()

        await _ensure_cache(chat_id)
        chat_filters = _filters_cache.get(chat_id, {})

        if keyword not in chat_filters:
            await message.reply_text(
                f"No filter found for <code>{keyword}</code>.",
                parse_mode=ParseMode.HTML
            )
            return

        success = await delete_filter(chat_id, keyword)

        if success:
            _remove_from_cache(chat_id, keyword)
            await message.reply_text(
                f"Filter <code>{keyword}</code> removed successfully!",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply_text("Failed to remove filter. Please try again.", parse_mode=ParseMode.HTML)

    @client.on_message(filters.command("stopallfilters") & filters.group, group=0)
    async def stop_all_filters_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        is_admin = await is_user_admin(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("Only admins can remove filters.", parse_mode=ParseMode.HTML)
            return

        await _ensure_cache(chat_id)
        chat_filters = _filters_cache.get(chat_id, {})

        if not chat_filters:
            await message.reply_text("No active filters in this group.", parse_mode=ParseMode.HTML)
            return

        deleted = await delete_all_filters(chat_id)

        _clear_cache(chat_id)

        await message.reply_text(
            f"All <b>{deleted}</b> filters removed successfully!",
            parse_mode=ParseMode.HTML
        )

    @client.on_message(filters.group & filters.text, group=2)
    async def filter_trigger(client: Client, message: Message):
        chat_id = message.chat.id

        await _ensure_cache(chat_id)

        chat_filters = _filters_cache.get(chat_id)
        if not chat_filters:
            return

        msg_text = message.text.lower() if message.text else ""
        if not msg_text:
            return

        matched_filter = None
        for keyword, filter_data in chat_filters.items():
            if (keyword == msg_text or
                msg_text.startswith(keyword + " ") or
                msg_text.endswith(" " + keyword) or
                (" " + keyword + " ") in msg_text):
                matched_filter = filter_data
                break

        if not matched_filter:
            return

        text = matched_filter.get("text")
        media_type = matched_filter.get("media_type")
        media_id = matched_filter.get("media_id")

        if media_type and media_id:
            if media_type == "photo":
                await message.reply_photo(photo=media_id, caption=text, parse_mode=ParseMode.HTML)
            elif media_type == "video":
                await message.reply_video(video=media_id, caption=text, parse_mode=ParseMode.HTML)
            elif media_type == "animation":
                await message.reply_animation(animation=media_id, caption=text, parse_mode=ParseMode.HTML)
            elif media_type == "sticker":
                await message.reply_sticker(sticker=media_id)
        elif text:
            await message.reply_text(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
