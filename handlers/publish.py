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

# ✅ NEW IMPORT: Callback manager for fixing BUTTON_DATA_INVALID
from callback_manager import create_callback, parse_callback

from database import (
    get_pack_by_short_name, 
    create_published_pack, 
    get_published_pack_by_keyword,
    search_published_packs,
    is_pack_published,
    get_user,
    get_published_pack_by_short_name
)
from templates import (
    PUBLISH_PACK_INFO, PUBLISH_PACK_ASK_KEYWORD,
    PUBLISH_KEYWORD_INVALID,
    PUBLISH_CONFIRM_REQUEST, PUBLISH_REQUEST_SENT,
    PUBLISH_REQUEST_APPROVED, PUBLISH_REQUEST_REJECTED,
    PUBLISH_ALREADY_PUBLISHED, PUBLISH_OWNER_NOTIFICATION,
    PUBLISH_OWNER_APPROVED, PUBLISH_OWNER_REJECTED,
    PUBLISH_CHANNEL_MESSAGE, ERROR_OCCURRED
)
from utils.fsm_states import PublishStates
from utils.html_utils import escape_html
from config import BOT_USERNAME, PUBLISH_OWNER_ID, PUBLISH_CHANNEL_ID

logger = logging.getLogger(__name__)
router = Router()

# ✅ FIXED: Shortened callback prefixes to prevent BUTTON_DATA_INVALID
class PublishCallback:
    PUBLISH_PACK = "pb:"           # ✅ Shortened (will use hash)
    PUBLISH_INFO = "pi"
    PUBLISH_CONFIRM_YES = "py:"    # ✅ Shortened (will use hash)
    PUBLISH_CONFIRM_NO = "pcn"
    OWNER_APPROVE = "oa:"          # ✅ Shortened (will use hash)
    OWNER_REJECT = "or:"           # ✅ Shortened (will use hash)


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


# ✅ Info button callback
@router.callback_query(F.data == PublishCallback.PUBLISH_INFO)
async def publish_info_callback(callback: CallbackQuery):
    """Show publish info popup"""
    await callback.answer(PUBLISH_PACK_INFO, show_alert=True)


# ✅ FIXED: Start publish flow with callback_manager
@router.callback_query(F.data.startswith(PublishCallback.PUBLISH_PACK))
async def start_publish_callback(callback: CallbackQuery, state: FSMContext):
    """Start publish pack flow - ask for keyword"""
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        short_name = parse_callback(callback.data)
        
        if not short_name:
            await callback.answer("❌ Session expired. Please try again.", show_alert=True)
            return
        
        pack = await get_pack_by_short_name(short_name)
        
        if not pack:
            logger.warning(f"[PUBLISH] Pack not found: {short_name}")
            await callback.answer("Pack not found!", show_alert=True)
            return
        
        # Check if THIS PACK is already published
        if await is_pack_published(short_name):
            logger.info(f"[PUBLISH] Pack already published: {short_name}")
            await callback.message.edit_text(
                PUBLISH_ALREADY_PUBLISHED,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_manage")
                ]])
            )
            return
        
        # Set state and store pack data
        await state.set_state(PublishStates.waiting_for_keyword)
        await state.update_data(
            pack_short_name=short_name,
            pack_data=pack
        )
        
        pack_name = pack["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
        escaped_pack_name = escape_html(pack_name)
        
        logger.info(f"[PUBLISH] Started publish flow for pack: {short_name}")
        
        # Ask for keyword
        await callback.message.edit_text(
            PUBLISH_PACK_ASK_KEYWORD.format(
                pack_name=escaped_pack_name,
                bot_username=BOT_USERNAME
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Cancel", callback_data="back_to_manage")
            ]])
        )
        
    except Exception as e:
        logger.error(f"[PUBLISH] Error starting publish flow: {e}", exc_info=True)
        await callback.answer("Error starting publish flow.", show_alert=True)


# ✅ Handle keyword input
@router.message(PublishStates.waiting_for_keyword)
async def process_publish_keyword(message: Message, state: FSMContext):
    """Process keyword input for publish"""
    
    # Text validation
    if not message.text:
        await message.reply("❌ Please send a text keyword.")
        return
    
    # Sanitize keyword input
    keyword = message.text.strip().lower()
    
    # Remove any non-alphanumeric characters
    keyword = re.sub(r'[^a-z0-9]', '', keyword)
    
    logger.info(f"[PUBLISH] User {message.from_user.id} submitted keyword: '{keyword}'")
    
    # Validate keyword format
    if not validate_keyword(keyword):
        logger.warning(f"[PUBLISH] Invalid keyword format: '{keyword}'")
        await message.reply(PUBLISH_KEYWORD_INVALID)
        return
    
    # Get stored pack data
    data = await state.get_data()
    pack_data = data.get("pack_data")
    
    if not pack_data:
        logger.error(f"[PUBLISH] Pack data lost from state for user {message.from_user.id}")
        await message.reply(ERROR_OCCURRED)
        await state.clear()
        return
    
    # Update state with keyword
    await state.update_data(keyword=keyword)
    await state.set_state(PublishStates.confirming_publish)
    
    pack_name = pack_data["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
    escaped_pack_name = escape_html(pack_name)
    
    logger.info(f"[PUBLISH] Keyword validated, showing confirmation for: {pack_data['short_name']}")
    
    # ✅ USE CALLBACK MANAGER for confirmation button
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
    
    await message.reply(
        PUBLISH_CONFIRM_REQUEST.format(
            pack_name=escaped_pack_name,
            keyword=keyword,
            bot_username=BOT_USERNAME
        ),
        reply_markup=builder.as_markup()
    )


# ✅ FIXED: Handle publish confirmation with callback_manager
@router.callback_query(F.data.startswith(PublishCallback.PUBLISH_CONFIRM_YES))
async def confirm_publish_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """User confirmed publish - send to owner"""
    await callback.answer()
    
    try:
        # Get state data
        data = await state.get_data()
        keyword = data.get("keyword")
        pack_data = data.get("pack_data")
        
        if not keyword or not pack_data:
            logger.error(f"[PUBLISH] State data lost for user {callback.from_user.id}")
            await callback.answer("Error: Data lost. Please try again.", show_alert=True)
            await state.clear()
            return
        
        short_name = pack_data["short_name"]
        pack_name = pack_data["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"
        user_id = callback.from_user.id
        
        logger.info(f"[PUBLISH] User {user_id} confirmed publish for pack {short_name} with keyword '{keyword}'")
        
        # Check if publish owner is configured
        if not PUBLISH_OWNER_ID:
            logger.error("[PUBLISH] PUBLISH_OWNER_ID not configured in config!")
            await callback.message.edit_text(
                "❌ <b>Publish feature is not configured.</b>\n\n"
                "Please contact the bot administrator."
            )
            await state.clear()
            return
        
        # Get first sticker from pack
        try:
            sticker_set = await bot.get_sticker_set(short_name)
            first_sticker_id = sticker_set.stickers[0].file_id
            logger.info(f"[PUBLISH] Got first sticker from pack: {first_sticker_id[:20]}...")
        except Exception as e:
            logger.error(f"[PUBLISH] Error getting sticker set {short_name}: {e}")
            await callback.message.edit_text(ERROR_OCCURRED)
            await state.clear()
            return
        
        # Get user info
        user = await get_user(user_id)
        user_name = user.get("first_name", "Unknown") if user else "Unknown"
        if user and user.get("username"):
            user_name = f"@{user['username']}"
        
        # Create owner notification
        escaped_pack_name = escape_html(pack_name.replace(f" ~ @{BOT_USERNAME}", ""))
        created_date = pack_data.get("created_at", datetime.utcnow()).strftime("%Y-%m-%d")
        
        owner_message = PUBLISH_OWNER_NOTIFICATION.format(
            user_name=user_name,
            user_id=user_id,
            pack_name=escaped_pack_name,
            keyword=keyword,
            pack_link=pack_link,
            sticker_count=pack_data.get("sticker_count", 0),
            created_date=created_date
        )
        
        # ✅ USE CALLBACK MANAGER for owner buttons
        # Store data as: "user_id:short_name:keyword"
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
        
        # Send sticker first
        await bot.send_sticker(
            chat_id=PUBLISH_OWNER_ID,
            sticker=first_sticker_id
        )
        
        # Then send notification
        await bot.send_message(
            chat_id=PUBLISH_OWNER_ID,
            text=owner_message,
            reply_markup=builder.as_markup()
        )
        
        logger.info(f"[PUBLISH] Publish request sent to owner for pack {short_name}")
        
        # Notify user
        await callback.message.edit_text(
            PUBLISH_REQUEST_SENT.format(pack_name=escaped_pack_name)
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"[PUBLISH] Error sending publish request: {e}", exc_info=True)
        await callback.message.edit_text(ERROR_OCCURRED)
        await state.clear()


# ✅ Handle publish confirmation - NO
@router.callback_query(F.data == PublishCallback.PUBLISH_CONFIRM_NO)
async def confirm_publish_no(callback: CallbackQuery, state: FSMContext):
    """User cancelled publish"""
    logger.info(f"[PUBLISH] User {callback.from_user.id} cancelled publish request")
    await callback.answer("Publish cancelled.", show_alert=True)
    await state.clear()
    
    await callback.message.edit_text(
        "❌ <b>Publish cancelled.</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_manage")
        ]])
    )


# ✅ FIXED: Owner approves publish with callback_manager
@router.callback_query(F.data.startswith(PublishCallback.OWNER_APPROVE))
async def owner_approve_publish(callback: CallbackQuery, bot: Bot):
    """Owner approved publish request"""
    logger.info(f"[OWNER_APPROVE] Button clicked")
    await callback.answer("Processing approval...")
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        data_str = parse_callback(callback.data)
        
        if not data_str:
            await callback.answer("❌ Session expired. Please ask user to resubmit.", show_alert=True)
            return
        
        # Parse: "user_id:short_name:keyword"
        parts = data_str.split(":")
        if len(parts) != 3:
            logger.error(f"[OWNER_APPROVE] Invalid data format: {data_str}")
            await callback.answer("❌ Invalid data format.", show_alert=True)
            return
        
        user_id = int(parts[0])
        short_name = parts[1]
        keyword = parts[2]
        
        logger.info(f"[OWNER_APPROVE] Processing: user={user_id}, pack={short_name}, keyword='{keyword}'")
        
        # Check if THIS PACK is already published
        existing_published = await get_published_pack_by_short_name(short_name)
        if existing_published:
            logger.warning(f"[OWNER_APPROVE] Pack {short_name} already published")
            await callback.message.edit_text(
                f"⚠️ <b>Pack Already Published</b>\n\n"
                f"Keyword: <code>{existing_published['keyword']}</code>\n\n"
                f"No action taken."
            )
            return
        
        # Get pack info
        pack = await get_pack_by_short_name(short_name)
        if not pack:
            logger.error(f"[OWNER_APPROVE] Pack not found: {short_name}")
            await callback.answer("Pack not found!", show_alert=True)
            return
        
        pack_name = pack["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"
        
        # Get first sticker
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
        
        # Save to database
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
        
        # Post to publish channel
        if PUBLISH_CHANNEL_ID:
            try:
                await bot.send_sticker(
                    chat_id=PUBLISH_CHANNEL_ID,
                    sticker=first_sticker_id
                )
                logger.info(f"[OWNER_APPROVE] ✅ Posted to channel")
            except Exception as e:
                logger.error(f"[OWNER_APPROVE] Error posting to channel: {e}")
        
        # Notify user
        try:
            escaped_pack_name = escape_html(pack_name.replace(f" ~ @{BOT_USERNAME}", ""))
            await bot.send_message(
                chat_id=user_id,
                text=PUBLISH_REQUEST_APPROVED.format(
                    pack_name=escaped_pack_name,
                    keyword=keyword,
                    bot_username=BOT_USERNAME,
                    pack_link=pack_link
                )
            )
            logger.info(f"[OWNER_APPROVE] ✅ Notified user {user_id}")
        except Exception as e:
            logger.error(f"[OWNER_APPROVE] Error notifying user: {e}")
        
        # Update owner message
        await callback.message.edit_text(
            PUBLISH_OWNER_APPROVED.format(
                pack_name=pack_name,
                user_id=user_id,
                keyword=keyword
            )
        )
        
        logger.info(f"[OWNER_APPROVE] ✅✅✅ Approval completed successfully")
        
    except Exception as e:
        logger.error(f"[OWNER_APPROVE] ❌ Critical error: {e}", exc_info=True)
        await callback.answer("Error approving publish!", show_alert=True)


# ✅ FIXED: Owner rejects publish with callback_manager
@router.callback_query(F.data.startswith(PublishCallback.OWNER_REJECT))
async def owner_reject_publish(callback: CallbackQuery, bot: Bot):
    """Owner rejected publish request"""
    logger.info(f"[OWNER_REJECT] Button clicked")
    await callback.answer()
    
    try:
        # ✅ PARSE CALLBACK DATA from hash
        data_str = parse_callback(callback.data)
        
        if not data_str:
            await callback.answer("❌ Session expired.", show_alert=True)
            return
        
        # Parse: "user_id:short_name:keyword"
        parts = data_str.split(":")
        if len(parts) < 2:
            logger.error(f"[OWNER_REJECT] Invalid data format: {data_str}")
            await callback.answer("❌ Invalid data format.", show_alert=True)
            return
        
        user_id = int(parts[0])
        short_name = parts[1]
        
        logger.info(f"[OWNER_REJECT] Rejecting pack {short_name} for user {user_id}")
        
        # Get pack info
        pack = await get_pack_by_short_name(short_name)
        pack_name = pack["pack_name"] if pack else "Unknown Pack"
        
        # Notify user
        try:
            escaped_pack_name = escape_html(pack_name.replace(f" ~ @{BOT_USERNAME}", ""))
            await bot.send_message(
                chat_id=user_id,
                text=PUBLISH_REQUEST_REJECTED.format(pack_name=escaped_pack_name)
            )
            logger.info(f"[OWNER_REJECT] ✅ Notified user {user_id}")
        except Exception as e:
            logger.error(f"[OWNER_REJECT] Error notifying user: {e}")
        
        # Update owner message
        await callback.message.edit_text(
            PUBLISH_OWNER_REJECTED.format(
                pack_name=pack_name,
                user_id=user_id
            )
        )
        
        logger.info(f"[OWNER_REJECT] ✅ Rejection completed")
        
    except Exception as e:
        logger.error(f"[OWNER_REJECT] Error: {e}", exc_info=True)
        await callback.answer("Error rejecting publish!", show_alert=True)


# ✅ Inline query handler
@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery):
    """
    Handle inline queries for published packs
    Shows all matching packs (multiple users can use same keyword)
    """
    query = inline_query.query.strip().lower()
    
    if not query:
        return
    
    try:
        # Search for ALL published packs matching the keyword
        published_packs = await search_published_packs(query, limit=50)
        
        logger.info(f"[INLINE_QUERY] Query '{query}' found {len(published_packs)} packs")
        
        # Create results
        results = []
        for pack in published_packs:
            result = InlineQueryResultCachedSticker(
                id=pack["pack_short_name"],
                sticker_file_id=pack["first_sticker_id"]
            )
            results.append(result)
        
        # Return all results
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
