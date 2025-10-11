cache_time=10)
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
import hashlib

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

# Callback data patterns
class PublishCallback:
    PUBLISH_PACK = "pub:"
    PUBLISH_INFO = "pub_info"
    PUBLISH_CONFIRM_YES = "pub_yes:"
    PUBLISH_CONFIRM_NO = "pub_no"
    OWNER_APPROVE = "own_app:"
    OWNER_REJECT = "own_rej:"

def validate_keyword(keyword: str) -> bool:
    """Validate publish keyword"""
    if not keyword or len(keyword) < 3 or len(keyword) > 20:
        return False
    if not re.match(r'^[a-zA-Z0-9]+$', keyword):
        return False
    return True

def create_request_id(user_id: int, short_name: str, keyword: str) -> str:
    """Create a short unique request ID to avoid long callback data"""
    data = f"{user_id}:{short_name}:{keyword}"
    return hashlib.md5(data.encode()).hexdigest()[:8]

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
            await callback.answer("Pack not found!", show_alert=True)
            return
        
        if await is_pack_published(short_name):
            await callback.message.edit_text(
                PUBLISH_ALREADY_PUBLISHED,
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
    
    if not validate_keyword(keyword):
        await message.reply(PUBLISH_KEYWORD_INVALID)
        return
    
    existing_pack = await get_published_pack_by_keyword(keyword)
    if existing_pack:
        await message.reply(PUBLISH_KEYWORD_TAKEN)
        return
    
    data = await state.get_data()
    pack_data = data.get("pack_data")
    
    if not pack_data:
        await message.reply(ERROR_OCCURRED)
        await state.clear()
        return
    
    await state.update_data(keyword=keyword)
    await state.set_state(PublishStates.confirming_publish)
    
    pack_name = pack_data["pack_name"].replace(f" ~ @{BOT_USERNAME}", "")
    escaped_pack_name = escape_html(pack_name)
    
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
        short_name = callback.data.split(":")[1]
        data = await state.get_data()
        keyword = data.get("keyword")
        pack_data = data.get("pack_data")
        
        if not keyword or not pack_data:
            await callback.answer("Error: Data lost. Please try again.", show_alert=True)
            await state.clear()
            return
        
        pack_name = pack_data["pack_name"]
        pack_link = f"https://t.me/addstickers/{short_name}"
        user_id = callback.from_user.id
        
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
        
        # Create request ID to shorten callback data
        request_id = create_request_id(user_id, short_name, keyword)
        
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
        
        # Send sticker + message to owner with shortened callback data
        builder = InlineKeyboardBuilder()
        builder.button(
            text="✅ Approve",
            callback_data=f"{PublishCallback.OWNER_APPROVE}{request_id}"
        )
        builder.button(
            text="❌ Reject",
            callback_data=f"{PublishCallback.OWNER_REJECT}{request_id}"
        )
        builder.adjust(2)
        
        # Store request data temporarily (in production, use Redis or database)
        # For now, we'll store it in a simple dict (in production use proper storage)
        if not hasattr(bot, 'publish_requests'):
            bot.publish_requests = {}
        
        bot.publish_requests[request_id] = {
            'user_id': user_id,
            'short_name': short_name,
            'keyword': keyword,
            'first_sticker_id': first_sticker_id,
            'pack_name': pack_name,
            'timestamp': datetime.utcnow()
        }
        
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

# ✅ Owner approves publish
@router.callback_query(F.data.startswith(PublishCallback.OWNER_APPROVE))
async def owner_approve_publish(callback: CallbackQuery, bot: Bot):
    """Owner approved publish request"""
    await callback.answer()
    
    try:
        request_id = callback.data.split(":")[1]
        
        # Get request data from temporary storage
        if not hasattr(bot, 'publish_requests') or request_id not in bot.publish_requests:
            await callback.answer("Request not found or expired!", show_alert=True)
            return
        
        request_data = bot.publish_requests[request_id]
        user_id = request_data['user_id']
        short_name = request_data['short_name']
        keyword = request_data['keyword']
        first_sticker_id = request_data['first_sticker_id']
        pack_name = request_data['pack_name']
        
        # Get pack info
        pack = await get_pack_by_short_name(short_name)
        if not pack:
            await callback.answer("Pack not found!", show_alert=True)
            return
        
        pack_link = f"https://t.me/addstickers/{short_name}"
        
        # Save to database
        success = await create_published_pack(
            user_id=user_id,
            pack_short_name=short_name,
            keyword=keyword,
            first_sticker_id=first_sticker_id
        )
        
        if not success:
            await callback.answer("Error saving to database!", show_alert=True)
            return
        
        # Post to publish channel
        if PUBLISH_CHANNEL_ID:
            try:
                escaped_pack_name = escape_html(pack_name.replace(f" ~ @{BOT_USERNAME}", ""))
                channel_message = PUBLISH_CHANNEL_MESSAGE.format(
                    pack_name=escaped_pack_name,
                    keyword=keyword,
                    bot_username=BOT_USERNAME,
                    pack_link=pack_link
                )
                
                # Send sticker to channel
                await bot.send_sticker(
                    chat_id=PUBLISH_CHANNEL_ID,
                    sticker=first_sticker_id,
                    caption=channel_message,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                        InlineKeyboardButton(text="➕ Add Pack", url=pack_link)
                    ]])
                )
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
        
        # Clean up temporary storage
        if hasattr(bot, 'publish_requests') and request_id in bot.publish_requests:
            del bot.publish_requests[request_id]
        
    except Exception as e:
        logger.error(f"Error approving publish: {e}")
        await callback.answer("Error approving publish!", show_alert=True)

# ✅ Owner rejects publish
@router.callback_query(F.data.startswith(PublishCallback.OWNER_REJECT))
async def owner_reject_publish(callback: CallbackQuery, bot: Bot):
    """Owner rejected publish request"""
    await callback.answer()
    
    try:
        request_id = callback.data.split(":")[1]
        
        # Get request data from temporary storage
        if not hasattr(bot, 'publish_requests') or request_id not in bot.publish_requests:
            await callback.answer("Request not found or expired!", show_alert=True)
            return
        
        request_data = bot.publish_requests[request_id]
        user_id = request_data['user_id']
        short_name = request_data['short_name']
        pack_name = request_data['pack_name']
        
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
        
        # Clean up temporary storage
        if hasattr(bot, 'publish_requests') and request_id in bot.publish_requests:
            del bot.publish_requests[request_id]
        
    except Exception as e:
        logger.error(f"Error rejecting publish: {e}")
        await callback.answer("Error rejecting publish!", show_alert=True)

# ✅ Inline query handler
@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery):
    """Handle inline queries for published packs"""
    query = inline_query.query.strip().lower()
    
    if not query:
        return
    
    try:
        results = []
        published_packs = await search_published_packs(query, limit=50)
        
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
        
    except Exception as e:
        logger.error(f"Error handling inline query: {e}")
        await inline_query.answer([], cache_time=10)
