from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from database import get_user, create_user, update_user_started, get_user_pack, get_user_packs
from templates import START_MESSAGE_WITH_IMAGE, GENERIC_ERROR_MESSAGE
from config import LOG_GROUP_ID, BOT_USERNAME, SUPPORT_GROUP, UPDATE_CHANNEL
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = Router()

# Callback data classes
class MainMenuCallback:
    MANAGE_PACKS = "main:manage_packs"
    SUPPORT = "main:support"
    UPDATES = "main:updates"
    BACK_TO_MAIN = "main:back"

class PackManagementCallback:
    BACK_TO_PACKS = "packs:back"
    CREATE_PACK = "packs:create"
    VIEW_PACK = "packs:view:"
    NEXT_PAGE = "packs:next:"
    PREV_PAGE = "packs:prev:"

class PackOptionsCallback:
    BACK_TO_PACK = "pack:back:"
    RENAME_PACK = "pack:rename:"
    DELETE_PACK = "pack:delete:"
    PUBLISH_PACK = "pack:publish:"
    ADD_STICKER = "pack:add_sticker:"

class PackActionsCallback:
    CONFIRM_DELETE = "pack_confirm_delete:"
    CANCEL_DELETE = "pack_cancel_delete:"

def get_main_menu_keyboard():
    """Get main menu inline keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Manage Packs", callback_data=MainMenuCallback.MANAGE_PACKS)
    builder.button(text="💬 Support", url=SUPPORT_GROUP)
    builder.button(text="📢 Updates", url=UPDATE_CHANNEL)
    builder.adjust(1, 2)
    return builder.as_markup()

def get_back_to_main_keyboard():
    """Get back to main menu keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Back", callback_data=MainMenuCallback.BACK_TO_MAIN)
    return builder.as_markup()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command with image and menu"""
    user = message.from_user
    
    # Clear any existing FSM state
    await state.clear()
    
    # Check if user exists
    user_data = await get_user(user.id)
    
    if not user_data:
        # Create new user
        await create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        
        # Send log to logger group if this is a new user
        if LOG_GROUP_ID:
            try:
                from templates import NEW_USER_LOG
                log_msg = NEW_USER_LOG.format(
                    user_id=user.id,
                    username=user.username or "None",
                    first_name=user.first_name or "Unknown",
                    time=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                )
                await message.bot.send_message(LOG_GROUP_ID, log_msg)
            except Exception as e:
                logger.error(f"Error sending new user log: {e}")
    else:
        # Update has_started status
        await update_user_started(user.id)
    
    # Send welcome image and message
    # Note: You'll need to add a welcome image file or use a URL
    try:
        # Option 1: Send with local image file
        # with open("assets/welcome.jpg", "rb") as f:
        #     welcome_image = BufferedInputFile(f.read(), filename="welcome.jpg")
        # await message.answer_photo(
        #     welcome_image,
        #     caption=START_MESSAGE_WITH_IMAGE,
        #     reply_markup=get_main_menu_keyboard()
        # )
        
        # Option 2: Send without image (for now)
        await message.answer(
            START_MESSAGE_WITH_IMAGE,
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")
        await message.answer(
            START_MESSAGE_WITH_IMAGE,
            reply_markup=get_main_menu_keyboard()
        )

@router.callback_query(F.data == MainMenuCallback.BACK_TO_MAIN)
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    """Handle back to main menu"""
    await state.clear()
    await callback.message.edit_text(
        START_MESSAGE_WITH_IMAGE,
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == MainMenuCallback.MANAGE_PACKS)
async def manage_packs(callback: CallbackQuery, state: FSMContext):
    """Show user's packs management panel"""
    user_id = callback.from_user.id
    
    try:
        # Get user's packs
        packs = await get_user_packs(user_id)
        
        if not packs:
            from templates import NO_PACKS_MESSAGE
            builder = InlineKeyboardBuilder()
            builder.button(text="📝 Create New Pack", callback_data=PackManagementCallback.CREATE_PACK)
            builder.button(text="🔙 Back", callback_data=MainMenuCallback.BACK_TO_MAIN)
            builder.adjust(1)
            
            await callback.message.edit_text(
                NO_PACKS_MESSAGE,
                reply_markup=builder.as_markup()
            )
        else:
            from templates import MANAGE_PACKS_MESSAGE
            await show_packs_page(callback, packs, 0)
        
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in manage_packs: {e}")
        await callback.message.edit_text(GENERIC_ERROR_MESSAGE)
        await callback.answer()

async def show_packs_page(callback: CallbackQuery, packs: list, page: int):
    """Show a page of user's packs"""
    from templates import MANAGE_PACKS_MESSAGE
    
    items_per_page = 6
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_packs = packs[start_idx:end_idx]
    
    builder = InlineKeyboardBuilder()
    
    # Add pack buttons (1 per row)
    for pack in page_packs:
        builder.button(
            text=f"📦 {pack['pack_name'][:20]} ({pack.get('sticker_count', 0)})",
            callback_data=f"{PackManagementCallback.VIEW_PACK}{pack['short_name']}"
        )
    
    # Add navigation and action buttons
    row_buttons = []
    
    if page > 0:
        row_buttons.append(("◀️ Prev", f"{PackManagementCallback.PREV_PAGE}{page-1}"))
    
    row_buttons.append(("📝 Create New", PackManagementCallback.CREATE_PACK))
    
    if end_idx < len(packs):
        row_buttons.append(("Next ▶️", f"{PackManagementCallback.NEXT_PAGE}{page+1}"))
    
    # Add navigation row
    for text, data in row_buttons:
        builder.button(text=text, callback_data=data)
    
    # Add back button
    builder.button(text="🔙 Back", callback_data=MainMenuCallback.BACK_TO_MAIN)
    
    # Adjust layout
    builder.adjust(1, len(row_buttons), 1)
    
    await callback.message.edit_text(
        MANAGE_PACKS_MESSAGE,
        reply_markup=builder.as_markup()
    )
