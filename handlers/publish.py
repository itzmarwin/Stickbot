import logging
import re
from aiogram import Router, Bot, F
from aiogram.types import (
    CallbackQuery, Message, InlineQuery, 
    InlineQueryResultCachedSticker, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from database import (
    get_pack_by_short_name, 
    create_published_pack, 
    get_published_pack_by_keyword,
    search_published_packs,
    is_pack_published,
    get_user
)
from templates import (
    PUBLISH_PACK_INFO, PUBLISH_PACK_ASK_KEYWORD,
    PUBLISH_KEYWORD_INVALID, PUBLISH_KEYWORD_TAKEN,
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

# Callback data patterns - SHORTENED
class PublishCallback:
    PUBLISH_PACK = "pp:"  # Shorter prefix
    PUBLISH_INFO = "pi"   # Shorter
    PUBLISH_CONFIRM_YES = "pcy:"  # Shorter
    PUBLISH_CONFIRM_NO = "pcn"    # Shorter
    OWNER_APPROVE = "oa:"  # Shorter
    OWNER_REJECT = "or:"   # Shorter

def validate_keyword(keyword: str) -> bool:
    """Validate publish keyword"""
    # Must be 3-20 characters, alphanumeric only, no spaces
    if not keyword or len(keyword) < 3 or len(keyword) > 20:
        return False
    
    # Only letters and numbers
    if not re.match(r'^[a-zA-Z0-9]+$', keyword):
        return False
    
    return True

# ✅ FIXED: Info button callback
@router.callback_query(F.data == PublishCallback.PUBLISH_INFO)
async def publish_info_callback(callback: CallbackQuery):
    """Show publish info popup"""
    await callback.answer(PUBLISH_PACK_INFO, show_alert=True)

# ✅ Start publish flow
@router.callback_query(F.data.startswith(PublishCallback.PUBLISH_PACK))
async def start_publish_callback(callback: CallbackQuery, state: FSMContext):
    """Start publish pack flow - ask for keyword"""
    await callback.answer()  # Instant response
    
    try:
        short_name = callback.data.split(":")[1]
        pack = await get_pack_by_short_name(short_name)
        
        if not pack:
            await callback.answer("Pack not found!", show_alert=True)
            return
        
        # Check if already published
        if await is_pack_published(short_name):
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
        logger.error(f"Error starting publish flow: {e}")
        await callback.answer("Error starting publish flow.", show_alert=True)

# ✅ Handle keyword input
@router.message(PublishStates.waiting_for_keyword)
async def process_publish_keyword(message: Message, state: FSMContext):
    """Process keyword input for publish"""
    keyword = message.text.strip().lower()
    
    # Validate keyword
    if not validate_keyword(keyword):
        await message.reply(PUBLISH_KEYWORD_INVALID)
        return
    
    # Check if keyword is already taken
    existing_pack = await get_published_pack_by_keyword(keyword)
    if existing_pack:
        await message.reply(PUBLISH_KEYWORD_TAKEN)
        return
    
    # Get stored pack data
    data = await state.get_data()
    pack_data = data.get("pack_data")
    
    if not pack_data:
        await message.reply(ERROR_OCCURRED)
        await state.clear()
        return
    
    # Update state with keyword
    await state.update_data(keyword=keyword)
    await state.set_state(PublishStates.confirming_publish)
    
    pack_name = pack_data["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
    escaped_pack_name = escape_html(pack_name)
    
    # Show confirmation
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Yes, Publish",
        callback_data=f"{PublishCallback.PUBLISH_CONFIRM_YES}{pack_data['short_name']}"
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

# ✅ FIXED: Handle publish confirmation - YES
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
            await callback.answer("Error: Data lost. Please try again.", show_alert=True)
            await state.clear()
            return
        
        short_name = pack_data["short_name"]
        pack_name = pack_data["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"
        user_id = callback.from_user.id
        
        # Check if publish owner is configured
        if not PUBLISH_OWNER_ID:
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
        except Exception as e:
            logger.error(f"Error getting sticker set: {e}")
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
        
        # ✅ FIXED: Create even shorter callback data
        approve_data = f"{PublishCallback.OWNER_APPROVE}{user_id}:{short_name}"
        reject_data = f"{PublishCallback.OWNER_REJECT}{user_id}:{short_name}"
        
        # Check callback data length (Telegram limit is 64 bytes)
        if len(approve_data) > 64:
            logger.error(f"Callback data too long: {len(approve_data)} bytes")
            await callback.message.edit_text(
                "❌ <b>Error: Data too long for approval.</b>\n\n"
                "Please try with a shorter pack name."
            )
            await state.clear()
            return
        
        # Send sticker + message to owner
        builder = InlineKeyboardBuilder()
        builder.button(
            text="✅ Approve",
            callback_data=approve_data
        )
        builder.button(
            text="❌ Reject",
            callback_data=reject_data
        )
        builder.adjust(2)
        
        # Send sticker first
        await bot.send_sticker(
            chat_id=PUBLISH_OWNER_ID,
            sticker=first_sticker_id
        )
        
        # Then send notification with keyword in the message text
        await bot.send_message(
            chat_id=PUBLISH_OWNER_ID,
            text=owner_message,
            reply_markup=builder.as_markup()
        )
        
        # Notify user
        await callback.message.edit_text(
            PUBLISH_REQUEST_SENT.format(pack_name=escaped_pack_name)
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error sending publish request: {e}")
        await callback.message.edit_text(ERROR_OCCURRED)
        await state.clear()

# ✅ Handle publish confirmation - NO
@router.callback_query(F.data == PublishCallback.PUBLISH_CONFIRM_NO)
async def confirm_publish_no(callback: CallbackQuery, state: FSMContext):
    """User cancelled publish"""
    await callback.answer("Publish cancelled.", show_alert=True)
    await state.clear()
    
    await callback.message.edit_text(
        "❌ <b>Publish cancelled.</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_manage")
        ]])
    )

# ✅ FIXED: Owner approves publish - with detailed debugging
@router.callback_query(F.data.startswith(PublishCallback.OWNER_APPROVE))
async def owner_approve_publish(callback: CallbackQuery, bot: Bot):
    """Owner approved publish request"""
    logger.info(f"Approve button clicked with data: {callback.data}")
    await callback.answer("Processing approval...")
    
    try:
        # Parse callback data
        data_parts = callback.data.split(":")[1:]
        logger.info(f"Parsed data parts: {data_parts}")
        
        if len(data_parts) < 2:
            await callback.answer("Error: Invalid callback data format.", show_alert=True)
            return
        
        user_id = int(data_parts[0])
        short_name = data_parts[1]
        
        logger.info(f"Processing approval for user_id: {user_id}, short_name: {short_name}")
        
        # ✅ FIXED: Extract keyword from the message text
        message_text = callback.message.text
        logger.info(f"Message text: {message_text}")
        
        # Try different patterns to extract keyword
        keyword_match = None
        patterns = [
            r"Keyword:</b>\s*<code>([a-zA-Z0-9]+)</code>",
            r"Keyword[^<]*<code>([a-zA-Z0-9]+)</code>",
            r"keyword[^<]*<code>([a-zA-Z0-9]+)</code>"
        ]
        
        for pattern in patterns:
            keyword_match = re.search(pattern, message_text, re.IGNORECASE)
            if keyword_match:
                break
        
        if not keyword_match:
            logger.error(f"Could not find keyword in message. Message: {message_text}")
            await callback.answer("Error: Could not find keyword in message.", show_alert=True)
            return
        
        keyword = keyword_match.group(1)
        logger.info(f"Extracted keyword: {keyword}")
        
        # Get pack info
        pack = await get_pack_by_short_name(short_name)
        if not pack:
            logger.error(f"Pack not found: {short_name}")
            await callback.answer("Pack not found!", show_alert=True)
            return
        
        pack_name = pack["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"
        
        logger.info(f"Found pack: {pack_name}")
        
        # ✅ FIXED: Get first sticker again with error handling
        try:
            sticker_set = await bot.get_sticker_set(short_name)
            if not sticker_set.stickers:
                logger.error(f"No stickers found in pack: {short_name}")
                await callback.answer("Error: No stickers in pack!", show_alert=True)
                return
            
            first_sticker_id = sticker_set.stickers[0].file_id
            logger.info(f"Got first sticker ID: {first_sticker_id[:20]}...")
        except Exception as e:
            logger.error(f"Error getting sticker set for approval: {e}")
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
            logger.error("Failed to save published pack to database")
            await callback.answer("Error saving to database!", show_alert=True)
            return
        
        logger.info("Successfully saved to database")
        
        # Post to publish channel - ONLY STICKER, NO MESSAGE
        if PUBLISH_CHANNEL_ID:
            try:
                logger.info(f"Posting sticker to channel: {PUBLISH_CHANNEL_ID}")
                await bot.send_sticker(
                    chat_id=PUBLISH_CHANNEL_ID,
                    sticker=first_sticker_id
                )
                logger.info("Successfully posted sticker to channel")
            except Exception as e:
                logger.error(f"Error posting to channel: {e}")
        
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
            logger.info("Successfully notified user")
        except Exception as e:
            logger.error(f"Error notifying user: {e}")
        
        # Update owner message
        await callback.message.edit_text(
            PUBLISH_OWNER_APPROVED.format(
                pack_name=pack_name,
                user_id=user_id,
                keyword=keyword
            )
        )
        
        logger.info("Approval process completed successfully")
        
    except Exception as e:
        logger.error(f"Error approving publish: {e}", exc_info=True)
        await callback.answer("Error approving publish!", show_alert=True)

# ✅ FIXED: Owner rejects publish
@router.callback_query(F.data.startswith(PublishCallback.OWNER_REJECT))
async def owner_reject_publish(callback: CallbackQuery, bot: Bot):
    """Owner rejected publish request"""
    await callback.answer()
    
    try:
        # Parse callback data
        data_parts = callback.data.split(":")[1:]
        user_id = int(data_parts[0])
        short_name = data_parts[1]
        
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
        except Exception as e:
            logger.error(f"Error notifying user: {e}")
        
        # Update owner message
        await callback.message.edit_text(
            PUBLISH_OWNER_REJECTED.format(
                pack_name=pack_name,
                user_id=user_id
            )
        )
        
    except Exception as e:
        logger.error(f"Error rejecting publish: {e}")
        await callback.answer("Error rejecting publish!", show_alert=True)

# ✅ Inline query handler
@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery):
    """Handle inline queries for published packs"""
    query = inline_query.query.strip().lower()
    
    # If empty query, return nothing or show help
    if not query:
        return
    
    try:
        # Search for published packs
        results = []
        published_packs = await search_published_packs(query, limit=50)
        
        for pack in published_packs:
            result = InlineQueryResultCachedSticker(
                id=pack["pack_short_name"],
                sticker_file_id=pack["first_sticker_id"]
            )
            results.append(result)
        
        # Return results
        await inline_query.answer(
            results=results,
            cache_time=300,  # Cache for 5 minutes
            is_personal=False
        )
        
    except Exception as e:
        logger.error(f"Error handling inline query: {e}")
        # Return empty results on error
        await inline_query.answer([], cache_time=10)
