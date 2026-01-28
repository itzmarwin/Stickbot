import logging
import re
import unicodedata
from aiogram import Router, Bot, F
from aiogram.types import (
    CallbackQuery, Message, InlineQuery, 
    InlineQueryResultCachedSticker, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from callback_manager import create_callback, parse_callback

from database import (
    get_pack_by_short_name, 
    create_published_pack, 
    get_published_pack_by_keyword,
    search_published_packs,
    is_pack_published,
    get_user,
    get_published_pack_by_short_name,
    get_user_language
)
from utils.language import get_text
from utils.fsm_states import PublishStates
from utils.html_utils import escape_html
from config import BOT_USERNAME, PUBLISH_OWNER_ID, PUBLISH_CHANNEL_ID

logger = logging.getLogger(__name__)
router = Router()

class PublishCallback:
    PUBLISH_PACK = "pb:"
    PUBLISH_INFO = "pi"
    PUBLISH_CONFIRM_YES = "py:"
    PUBLISH_CONFIRM_NO = "pcn"
    OWNER_APPROVE = "oa:"
    OWNER_REJECT = "or:"


def validate_keyword(keyword: str) -> bool:
    """
    Validate publish keyword
    Rules: 3-20 characters, alphanumeric only, no spaces
    """
    if not keyword or len(keyword) < 3 or len(keyword) > 20:
        return False
    
    if not re.match(r'^[a-zA-Z0-9]+$', keyword):
        return False
    
    return True


@router.callback_query(F.data == PublishCallback.PUBLISH_INFO)
async def publish_info_callback(callback: CallbackQuery):
    """Show publish info popup"""
    user_id = callback.from_user.id
    
    info_msg = await get_text(user_id, "PUBLISH_PACK_INFO")
    if info_msg is None:
        info_msg = "📤 𝖯𝗎𝖻𝗅𝗂𝗌𝗁 𝗒𝗈𝗎𝗋 𝗉𝖺𝖼𝗄 𝗍𝗈 𝗆𝖺𝗄𝖾 𝗂𝗍 𝗌𝖾𝖺𝗋𝖼𝗁𝖺𝖻𝗅𝖾 𝗂𝗇 𝗂𝗇𝗅𝗂𝗇𝖾 𝗆𝗈𝖽𝖾."
    
    await callback.answer(info_msg, show_alert=True)


@router.callback_query(F.data.startswith(PublishCallback.PUBLISH_PACK))
async def start_publish_callback(callback: CallbackQuery, state: FSMContext):
    """Start publish pack flow - ask for keyword"""
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        short_name = parse_callback(callback.data)
        
        if not short_name:
            expired_msg = await get_text(user_id, "SESSION_EXPIRED")
            if expired_msg is None:
                expired_msg = "❌ Session expired. Please try again."
            await callback.answer(expired_msg, show_alert=True)
            return
        
        pack = await get_pack_by_short_name(short_name)
        
        if not pack:
            logger.warning(f"[PUBLISH] Pack not found: {short_name}")
            not_found_msg = await get_text(user_id, "PACK_NOT_FOUND_MESSAGE")
            if not_found_msg is None:
                not_found_msg = "Pack not found!"
            await callback.answer(not_found_msg, show_alert=True)
            return
        
        if await is_pack_published(short_name):
            logger.info(f"[PUBLISH] Pack already published: {short_name}")
            
            already_published_msg = await get_text(user_id, "PUBLISH_ALREADY_PUBLISHED")
            if already_published_msg is None:
                already_published_msg = "⚠️ <b>This pack is already published!</b>\n\nYou cannot publish the same pack twice."
            
            await callback.message.edit_text(
                already_published_msg,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_manage")
                ]])
            )
            return
        
        await state.set_state(PublishStates.waiting_for_keyword)
        await state.update_data(
            pack_short_name=short_name,
            pack_data=pack
        )
        
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        escaped_pack_name = escape_html(pack_name)
        
        logger.info(f"[PUBLISH] Started publish flow for pack: {short_name}")
        
        ask_keyword_msg = await get_text(
            user_id,
            "PUBLISH_PACK_ASK_KEYWORD",
            pack_name=escaped_pack_name,
            bot_username=BOT_USERNAME
        )
        
        if ask_keyword_msg is None:
            ask_keyword_msg = f"📤 <b>Publish Pack</b>\n\n<b>Pack:</b> {escaped_pack_name}\n\nPlease send a keyword (3-20 characters, alphanumeric only) that people will use to find your pack via inline mode.\n\n<b>Example:</b> <code>@{BOT_USERNAME} memes</code>"
        
        await callback.message.edit_text(
            ask_keyword_msg,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Cancel", callback_data="back_to_manage")
            ]])
        )
        
    except Exception as e:
        logger.error(f"[PUBLISH] Error starting publish flow: {e}", exc_info=True)
        await callback.answer("Error starting publish flow.", show_alert=True)


@router.message(PublishStates.waiting_for_keyword)
async def process_publish_keyword(message: Message, state: FSMContext):
    """Process keyword input for publish"""
    user_id = message.from_user.id
    
    if not message.text:
        invalid_msg = await get_text(user_id, "PUBLISH_KEYWORD_SEND_TEXT")
        if invalid_msg is None:
            invalid_msg = "❌ Please send a text keyword."
        await message.reply(invalid_msg)
        return
    
    keyword = message.text.strip().lower()
    keyword = re.sub(r'[^a-z0-9]', '', keyword)
    
    logger.info(f"[PUBLISH] User {user_id} submitted keyword: '{keyword}'")
    
    if not validate_keyword(keyword):
        logger.warning(f"[PUBLISH] Invalid keyword format: '{keyword}'")
        
        invalid_keyword_msg = await get_text(user_id, "PUBLISH_KEYWORD_INVALID")
        if invalid_keyword_msg is None:
            invalid_keyword_msg = "❌ <b>Invalid keyword!</b>\n\nKeyword must be:\n- 3-20 characters long\n- Alphanumeric only (a-z, 0-9)\n- No spaces or special characters\n\nPlease try again."
        
        await message.reply(invalid_keyword_msg)
        return
    
    data = await state.get_data()
    pack_data = data.get("pack_data")
    
    if not pack_data:
        logger.error(f"[PUBLISH] Pack data lost from state for user {user_id}")
        error_msg = await get_text(user_id, "ERROR_OCCURRED")
        if error_msg is None:
            error_msg = "⚠️ <b>𝖮𝗈𝗉𝗌 — 𝗌𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀.</b>"
        await message.reply(error_msg)
        await state.clear()
        return
    
    await state.update_data(keyword=keyword)
    await state.set_state(PublishStates.confirming_publish)
    
    pack_name = pack_data["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
    escaped_pack_name = escape_html(pack_name)
    
    logger.info(f"[PUBLISH] Keyword validated, showing confirmation for: {pack_data['short_name']}")
    
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Yes, Publish",
        callback_data=create_callback("publish_confirm_yes", pack_data['short_name'])
    )
    builder.button(
        text="❌ Cancel",
        callback_data=PublishCallback.PUBLISH_CONFIRM_NO
    )
    builder.adjust(2)
    
    confirm_msg = await get_text(
        user_id,
        "PUBLISH_CONFIRM_REQUEST",
        pack_name=escaped_pack_name,
        keyword=keyword,
        bot_username=BOT_USERNAME
    )
    
    if confirm_msg is None:
        confirm_msg = f"📤 <b>Confirm Publish</b>\n\n<b>Pack:</b> {escaped_pack_name}\n<b>Keyword:</b> <code>{keyword}</code>\n\n<b>Usage:</b> <code>@{BOT_USERNAME} {keyword}</code>\n\nAre you sure you want to submit this pack for publishing?"
    
    await message.reply(
        confirm_msg,
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data.startswith(PublishCallback.PUBLISH_CONFIRM_YES))
async def confirm_publish_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """User confirmed publish - send to owner"""
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        data = await state.get_data()
        keyword = data.get("keyword")
        pack_data = data.get("pack_data")
        
        if not keyword or not pack_data:
            logger.error(f"[PUBLISH] State data lost for user {user_id}")
            await callback.answer("Error: Data lost. Please try again.", show_alert=True)
            await state.clear()
            return
        
        short_name = pack_data["short_name"]
        pack_name = pack_data["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"
        
        logger.info(f"[PUBLISH] User {user_id} confirmed publish for pack {short_name} with keyword '{keyword}'")
        
        if not PUBLISH_OWNER_ID:
            logger.error("[PUBLISH] PUBLISH_OWNER_ID not configured in config!")
            
            not_configured_msg = await get_text(user_id, "PUBLISH_NOT_CONFIGURED")
            if not_configured_msg is None:
                not_configured_msg = "❌ <b>Publish feature is not configured.</b>\n\nPlease contact the bot administrator."
            
            await callback.message.edit_text(not_configured_msg)
            await state.clear()
            return
        
        try:
            sticker_set = await bot.get_sticker_set(short_name)
            first_sticker_id = sticker_set.stickers[0].file_id
            logger.info(f"[PUBLISH] Got first sticker from pack: {first_sticker_id[:20]}...")
        except Exception as e:
            logger.error(f"[PUBLISH] Error getting sticker set {short_name}: {e}")
            error_msg = await get_text(user_id, "ERROR_OCCURRED")
            if error_msg is None:
                error_msg = "⚠️ <b>𝖮𝗈𝗉𝗌 — 𝗌𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀.</b>"
            await callback.message.edit_text(error_msg)
            await state.clear()
            return
        
        user = await get_user(user_id)
        user_name = user.get("first_name", "Unknown") if user else "Unknown"
        if user and user.get("username"):
            user_name = f"@{user['username']}"
        
        escaped_pack_name = escape_html(pack_name.replace(f" ~ @{BOT_USERNAME}", ""))
        created_date = pack_data.get("created_at", datetime.utcnow()).strftime("%Y-%m-%d")
        
        # Owner notification (English only - not translated)
        owner_message = (
            f"📤 <b>New Publish Request</b>\n\n"
            f"<b>From:</b> {user_name} (<code>{user_id}</code>)\n"
            f"<b>Pack:</b> {escaped_pack_name}\n"
            f"<b>Keyword:</b> <code>{keyword}</code>\n"
            f"<b>Link:</b> {pack_link}\n"
            f"<b>Stickers:</b> {pack_data.get('sticker_count', 0)}\n"
            f"<b>Created:</b> {created_date}"
        )
        
        approve_data = f"{user_id}:{short_name}:{keyword}"
        reject_data = f"{user_id}:{short_name}:{keyword}"
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="✅ Approve",
            callback_data=create_callback("owner_approve", approve_data)
        )
        builder.button(
            text="❌ Reject",
            callback_data=create_callback("owner_reject", reject_data)
        )
        builder.adjust(2)
        
        await bot.send_sticker(
            chat_id=PUBLISH_OWNER_ID,
            sticker=first_sticker_id
        )
        
        await bot.send_message(
            chat_id=PUBLISH_OWNER_ID,
            text=owner_message,
            reply_markup=builder.as_markup()
        )
        
        logger.info(f"[PUBLISH] Publish request sent to owner for pack {short_name}")
        
        request_sent_msg = await get_text(user_id, "PUBLISH_REQUEST_SENT", pack_name=escaped_pack_name)
        if request_sent_msg is None:
            request_sent_msg = f"✅ <b>Request sent!</b>\n\nYour pack <b>{escaped_pack_name}</b> has been submitted for publishing. You'll be notified when it's reviewed."
        
        await callback.message.edit_text(request_sent_msg)
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"[PUBLISH] Error sending publish request: {e}", exc_info=True)
        error_msg = await get_text(user_id, "ERROR_OCCURRED")
        if error_msg is None:
            error_msg = "⚠️ <b>𝖮𝗈𝗉𝗌 — 𝗌𝗈𝗆𝖾𝗍𝗁𝗂𝗇𝗀 𝗐𝖾𝗇𝗍 𝗐𝗋𝗈𝗇𝗀.</b>"
        await callback.message.edit_text(error_msg)
        await state.clear()


@router.callback_query(F.data == PublishCallback.PUBLISH_CONFIRM_NO)
async def confirm_publish_no(callback: CallbackQuery, state: FSMContext):
    """User cancelled publish"""
    user_id = callback.from_user.id
    logger.info(f"[PUBLISH] User {user_id} cancelled publish request")
    
    await callback.answer("Publish cancelled.", show_alert=True)
    await state.clear()
    
    cancelled_msg = await get_text(user_id, "PUBLISH_CANCELLED")
    if cancelled_msg is None:
        cancelled_msg = "❌ <b>Publish cancelled.</b>"
    
    await callback.message.edit_text(
        cancelled_msg,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_manage")
        ]])
    )


@router.callback_query(F.data.startswith(PublishCallback.OWNER_APPROVE))
async def owner_approve_publish(callback: CallbackQuery, bot: Bot):
    """Owner approved publish request"""
    logger.info(f"[OWNER_APPROVE] Button clicked")
    await callback.answer("Processing approval...")
    
    try:
        data_str = parse_callback(callback.data)
        
        if not data_str:
            await callback.answer("❌ Session expired. Please ask user to resubmit.", show_alert=True)
            return
        
        parts = data_str.split(":")
        if len(parts) != 3:
            logger.error(f"[OWNER_APPROVE] Invalid data format: {data_str}")
            await callback.answer("❌ Invalid data format.", show_alert=True)
            return
        
        user_id = int(parts[0])
        short_name = parts[1]
        keyword = parts[2]
        
        logger.info(f"[OWNER_APPROVE] Processing: user={user_id}, pack={short_name}, keyword='{keyword}'")
        
        existing_published = await get_published_pack_by_short_name(short_name)
        if existing_published:
            logger.warning(f"[OWNER_APPROVE] Pack {short_name} already published")
            await callback.message.edit_text(
                f"⚠️ <b>Pack Already Published</b>\n\n"
                f"Keyword: <code>{existing_published['keyword']}</code>\n\n"
                f"No action taken."
            )
            return
        
        pack = await get_pack_by_short_name(short_name)
        if not pack:
            logger.error(f"[OWNER_APPROVE] Pack not found: {short_name}")
            await callback.answer("Pack not found!", show_alert=True)
            return
        
        pack_name = pack["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"
        
        try:
            sticker_set = await bot.get_sticker_set(short_name)
            if not sticker_set.stickers:
                logger.error(f"[OWNER_APPROVE] No stickers in pack: {short_name}")
                await callback.answer("Error: No stickers in pack!", show_alert=True)
                return
            
            first_sticker_id = sticker_set.stickers[0].file_id
            logger.info(f"[OWNER_APPROVE] Got first sticker")
        except Exception as e:
            logger.error(f"[OWNER_APPROVE] Error getting sticker set: {e}")
            await callback.answer("Error getting sticker set!", show_alert=True)
            return
        
        success = await create_published_pack(
            user_id=user_id,
            pack_short_name=short_name,
            keyword=keyword,
            first_sticker_id=first_sticker_id
        )
        
        if not success:
            logger.error(f"[OWNER_APPROVE] Failed to save to database")
            await callback.answer("Error saving to database!", show_alert=True)
            return
        
        logger.info(f"[OWNER_APPROVE] ✅ Saved to database successfully")
        
        if PUBLISH_CHANNEL_ID:
            try:
                await bot.send_sticker(
                    chat_id=PUBLISH_CHANNEL_ID,
                    sticker=first_sticker_id
                )
                logger.info(f"[OWNER_APPROVE] ✅ Posted to channel")
            except Exception as e:
                logger.error(f"[OWNER_APPROVE] Error posting to channel: {e}")
        
        try:
            escaped_pack_name = escape_html(pack_name.replace(f" ~ @{BOT_USERNAME}", ""))
            
            approved_msg = await get_text(
                user_id,
                "PUBLISH_REQUEST_APPROVED",
                pack_name=escaped_pack_name,
                keyword=keyword,
                bot_username=BOT_USERNAME,
                pack_link=pack_link
            )
            
            if approved_msg is None:
                approved_msg = f"✅ <b>Pack Published!</b>\n\n<b>Pack:</b> {escaped_pack_name}\n<b>Keyword:</b> <code>{keyword}</code>\n\n<b>Usage:</b> <code>@{BOT_USERNAME} {keyword}</code>\n\nYour pack is now live! Anyone can find it by typing the keyword in inline mode.\n\n<a href=\"{pack_link}\">View Pack</a>"
            
            await bot.send_message(
                chat_id=user_id,
                text=approved_msg
            )
            logger.info(f"[OWNER_APPROVE] ✅ Notified user {user_id}")
        except Exception as e:
            logger.error(f"[OWNER_APPROVE] Error notifying user: {e}")
        
        # Owner notification (English only)
        await callback.message.edit_text(
            f"✅ <b>Approved!</b>\n\n"
            f"<b>Pack:</b> {pack_name}\n"
            f"<b>User:</b> {user_id}\n"
            f"<b>Keyword:</b> <code>{keyword}</code>\n\n"
            f"Pack is now published."
        )
        
        logger.info(f"[OWNER_APPROVE] ✅✅✅ Approval completed successfully")
        
    except Exception as e:
        logger.error(f"[OWNER_APPROVE] ❌ Critical error: {e}", exc_info=True)
        await callback.answer("Error approving publish!", show_alert=True)


@router.callback_query(F.data.startswith(PublishCallback.OWNER_REJECT))
async def owner_reject_publish(callback: CallbackQuery, bot: Bot):
    """Owner rejected publish request"""
    logger.info(f"[OWNER_REJECT] Button clicked")
    await callback.answer()
    
    try:
        data_str = parse_callback(callback.data)
        
        if not data_str:
            await callback.answer("❌ Session expired.", show_alert=True)
            return
        
        parts = data_str.split(":")
        if len(parts) < 2:
            logger.error(f"[OWNER_REJECT] Invalid data format: {data_str}")
            await callback.answer("❌ Invalid data format.", show_alert=True)
            return
        
        user_id = int(parts[0])
        short_name = parts[1]
        
        logger.info(f"[OWNER_REJECT] Rejecting pack {short_name} for user {user_id}")
        
        pack = await get_pack_by_short_name(short_name)
        pack_name = pack["pack_name"] if pack else "Unknown Pack"
        
        try:
            escaped_pack_name = escape_html(pack_name.replace(f" ~ @{BOT_USERNAME}", ""))
            
            rejected_msg = await get_text(user_id, "PUBLISH_REQUEST_REJECTED", pack_name=escaped_pack_name)
            if rejected_msg is None:
                rejected_msg = f"❌ <b>Publish Request Rejected</b>\n\nYour pack <b>{escaped_pack_name}</b> was not approved for publishing."
            
            await bot.send_message(
                chat_id=user_id,
                text=rejected_msg
            )
            logger.info(f"[OWNER_REJECT] ✅ Notified user {user_id}")
        except Exception as e:
            logger.error(f"[OWNER_REJECT] Error notifying user: {e}")
        
        # Owner notification (English only)
        await callback.message.edit_text(
            f"❌ <b>Rejected</b>\n\n"
            f"<b>Pack:</b> {pack_name}\n"
            f"<b>User:</b> {user_id}"
        )
        
        logger.info(f"[OWNER_REJECT] ✅ Rejection completed")
        
    except Exception as e:
        logger.error(f"[OWNER_REJECT] Error: {e}", exc_info=True)
        await callback.answer("Error rejecting publish!", show_alert=True)


@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery):
    """Handle inline queries for published packs"""
    query = inline_query.query.strip().lower()
    
    if not query:
        return
    
    try:
        published_packs = await search_published_packs(query, limit=50)
        
        logger.info(f"[INLINE_QUERY] Query '{query}' found {len(published_packs)} packs")
        
        results = []
        for pack in published_packs:
            result = InlineQueryResultCachedSticker(
                id=pack["pack_short_name"],
                sticker_file_id=pack["first_sticker_id"]
            )
            results.append(result)
        
        await inline_query.answer(
            results=results,
            cache_time=300,
            is_personal=False
        )
        
        if results:
            logger.info(f"[INLINE_QUERY] ✅ Returned {len(results)} results")
        
    except Exception as e:
        logger.error(f"[INLINE_QUERY] Error: {e}", exc_info=True)
        await inline_query.answer([], cache_time=10)
