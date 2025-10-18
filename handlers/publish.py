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

# Callback data patterns - SHORTENED
class PublishCallback:
    PUBLISH_PACK = "pp:"
    PUBLISH_INFO = "pi"
    PUBLISH_CONFIRM_YES = "pcy:"
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


def safe_extract_keyword(text: str) -> str:
    """
    ✅ PRODUCTION-READY KEYWORD EXTRACTOR with Unicode normalization
    
    Extracts keyword from any text (ASCII/Unicode) with multiple fallback methods
    
    Returns: 
        keyword string or None
    """
    try:
        logger.info(f"[KEYWORD_EXTRACT] Starting extraction from text (length: {len(text)})")
        
        # ✅ FIX 1: Unicode normalization FIRST
        # Convert Unicode to ASCII-compatible form before processing
        try:
            normalized_text = unicodedata.normalize('NFKD', text)
            normalized_text = normalized_text.encode('ascii', 'ignore').decode('ascii')
            logger.debug(f"[KEYWORD_EXTRACT] Normalized text length: {len(normalized_text)}")
        except Exception as e:
            logger.warning(f"[KEYWORD_EXTRACT] Unicode normalization failed: {e}")
            normalized_text = text  # Fallback to original
        
        # Method 1: Line-by-line search with colon delimiter
        # Most reliable method - works with any text structure
        lines = normalized_text.split('\n')
        for i, line in enumerate(lines):
            # Check if line has colon (keyword indicator)
            if ':' not in line:
                continue
            
            # Split by colon
            parts = line.split(':', 1)
            if len(parts) != 2:
                continue
            
            label = parts[0].strip().lower()
            value = parts[1].strip()
            
            # ✅ FIX 2: Look for specific label patterns
            if any(keyword_label in label for keyword_label in ['keyword', 'ключевое слово', 'キーワード']):
                # Extract first alphanumeric word after colon
                words = re.findall(r'[a-zA-Z0-9]+', value)
                
                if words:
                    potential_keyword = words[0].lower()
                    
                    # Validate length
                    if 3 <= len(potential_keyword) <= 20:
                        logger.info(f"[KEYWORD_EXTRACT] ✅ Found via label match (line {i}): '{potential_keyword}'")
                        return potential_keyword
        
        # Method 2: Code tag extraction (Telegram markdown)
        # Keywords are often wrapped in <code> tags
        code_pattern = r'<code>([a-zA-Z0-9]+)</code>'
        code_matches = re.findall(code_pattern, normalized_text)
        
        for match in code_matches:
            if 3 <= len(match) <= 20:
                logger.info(f"[KEYWORD_EXTRACT] ✅ Found in <code> tag: '{match.lower()}'")
                return match.lower()
        
        # Method 3: Colon-based extraction (any line with colon)
        for i, line in enumerate(lines):
            if ':' not in line:
                continue
            
            # Extract everything after colon
            parts = line.split(':', 1)
            if len(parts) != 2:
                continue
            
            after_colon = parts[1].strip()
            
            # Extract first alphanumeric word
            words = re.findall(r'[a-zA-Z0-9]+', after_colon)
            
            if not words:
                continue
            
            potential_keyword = words[0].lower()
            
            # Validate length
            if 3 <= len(potential_keyword) <= 20:
                # ✅ FIX 3: Skip common false positives
                false_positives = ['user', 'from', 'pack', 'admin', 'name', 'text', 'message', 
                                  'content', 'time', 'date', 'type', 'users', 'groups', 'total']
                
                if potential_keyword not in false_positives:
                    logger.info(f"[KEYWORD_EXTRACT] ✅ Found via colon search (line {i}): '{potential_keyword}'")
                    return potential_keyword
        
        # Method 4: Regex fallback - extract all alphanumeric words
        logger.warning("[KEYWORD_EXTRACT] Direct methods failed, trying word extraction")
        all_words = re.findall(r'[a-zA-Z0-9]+', normalized_text)
        
        # Filter valid keyword-length words
        potential_keywords = [w.lower() for w in all_words if 3 <= len(w) <= 20]
        
        if potential_keywords:
            # ✅ FIX 4: Smart word selection based on position
            # In publish messages, keyword usually appears in specific positions
            
            # Try to find keyword in middle section (after headers, before results)
            if len(potential_keywords) >= 5:
                # Check positions 4-8 (most likely keyword positions)
                for idx in range(4, min(8, len(potential_keywords))):
                    candidate = potential_keywords[idx]
                    # Skip false positives
                    if candidate not in ['user', 'from', 'pack', 'admin', 'name', 'users', 
                                        'groups', 'text', 'message', 'content', 'time']:
                        logger.info(f"[KEYWORD_EXTRACT] ⚠️ Found via position {idx}: '{candidate}'")
                        return candidate
            
            # Fallback: last valid word
            keyword = potential_keywords[-1]
            logger.info(f"[KEYWORD_EXTRACT] ⚠️ Found via last word: '{keyword}'")
            return keyword
        
        # Method 5: Last resort - look for isolated alphanumeric sequences
        # This catches keywords that might be surrounded by special characters
        isolated_words = re.findall(r'\b([a-zA-Z0-9]{3,20})\b', normalized_text)
        if isolated_words:
            # Take the last one (usually the keyword in publish messages)
            keyword = isolated_words[-1].lower()
            logger.info(f"[KEYWORD_EXTRACT] ⚠️ Found via isolated word: '{keyword}'")
            return keyword
        
        logger.error("[KEYWORD_EXTRACT] ❌ All extraction methods failed")
        return None
        
    except Exception as e:
        logger.error(f"[KEYWORD_EXTRACT] Exception occurred: {e}", exc_info=True)
        return None


# ✅ Info button callback
@router.callback_query(F.data == PublishCallback.PUBLISH_INFO)
async def publish_info_callback(callback: CallbackQuery):
    """Show publish info popup"""
    await callback.answer(PUBLISH_PACK_INFO, show_alert=True)


# ✅ Start publish flow
@router.callback_query(F.data.startswith(PublishCallback.PUBLISH_PACK))
async def start_publish_callback(callback: CallbackQuery, state: FSMContext):
    """Start publish pack flow - ask for keyword"""
    await callback.answer()
    
    try:
        short_name = callback.data.split(":")[1]
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
    
    # ✅ FIX: Sanitize keyword input
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


# ✅ Handle publish confirmation - YES
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
        
        # ✅ FIX: Store keyword IN CALLBACK DATA with length check
        approve_data = f"{PublishCallback.OWNER_APPROVE}{user_id}:{short_name}:{keyword}"
        reject_data = f"{PublishCallback.OWNER_REJECT}{user_id}:{short_name}:{keyword}"
        
        # Check callback data length (Telegram limit: 64 bytes)
        if len(approve_data) > 64:
            # ✅ FIX: Use hash of keyword if too long
            import hashlib
            keyword_hash = hashlib.md5(keyword.encode()).hexdigest()[:8]
            approve_data = f"{PublishCallback.OWNER_APPROVE}{user_id}:{short_name}:{keyword_hash}"
            reject_data = f"{PublishCallback.OWNER_REJECT}{user_id}:{short_name}:{keyword_hash}"
            
            logger.warning(f"[PUBLISH] Callback data too long, using hash: {keyword_hash}")
            
            # Store full keyword in message for fallback extraction
            owner_message += f"\n\n<b>Keyword Hash:</b> <code>{keyword_hash}</code>"
        
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
        
        # Then send notification with keyword in callback data
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


# ✅ Owner approves publish
@router.callback_query(F.data.startswith(PublishCallback.OWNER_APPROVE))
async def owner_approve_publish(callback: CallbackQuery, bot: Bot):
    """
    Owner approved publish request with enhanced keyword extraction
    """
    logger.info(f"[OWNER_APPROVE] Button clicked with data: {callback.data}")
    await callback.answer("Processing approval...")
    
    try:
        # Parse callback data: oa:user_id:short_name:keyword
        data_parts = callback.data.split(":")[1:]
        logger.info(f"[OWNER_APPROVE] Parsed {len(data_parts)} parts from callback data")
        
        if len(data_parts) < 2:
            logger.error(f"[OWNER_APPROVE] Invalid callback data format: {callback.data}")
            await callback.answer("Error: Invalid callback data format.", show_alert=True)
            return
        
        user_id = int(data_parts[0])
        short_name = data_parts[1]
        
        # ✅ Get keyword with multiple fallback methods
        keyword = None
        
        # Method 1: From callback data (most reliable)
        if len(data_parts) >= 3:
            keyword = data_parts[2]
            logger.info(f"[OWNER_APPROVE] ✅ Got keyword from callback data: '{keyword}'")
        
        # Method 2: Extract from message text (fallback)
        if not keyword:
            logger.warning("[OWNER_APPROVE] Keyword not in callback data, extracting from message...")
            keyword = safe_extract_keyword(callback.message.text)
            
            if keyword:
                logger.info(f"[OWNER_APPROVE] ✅ Extracted keyword from message: '{keyword}'")
            else:
                logger.error("[OWNER_APPROVE] ❌ Failed to extract keyword")
                await callback.answer(
                    "Error: Could not find keyword. Please reject and ask user to resubmit.",
                    show_alert=True
                )
                return
        
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


# ✅ Owner rejects publish
@router.callback_query(F.data.startswith(PublishCallback.OWNER_REJECT))
async def owner_reject_publish(callback: CallbackQuery, bot: Bot):
    """Owner rejected publish request"""
    logger.info(f"[OWNER_REJECT] Button clicked")
    await callback.answer()
    
    try:
        # Parse callback data
        data_parts = callback.data.split(":")[1:]
        user_id = int(data_parts[0])
        short_name = data_parts[1]
        
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
