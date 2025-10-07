import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from database import get_user_pack, get_user_packs, delete_user_pack, update_pack_name
from templates import (
    PACK_OPTIONS_MESSAGE, 
    DELETE_PACK_CONFIRMATION,
    PACK_DELETED_SUCCESS,
    RENAME_PACK_MESSAGE,
    PACK_RENAMED_SUCCESS,
    PUBLISH_REQUEST_SENT,
    ADD_STICKER_INSTRUCTIONS,
    PACK_FULL_MESSAGE,
    CREATE_PACK_PROMPT,
    GENERIC_ERROR_MESSAGE
)
from start import (
    PackManagementCallback,
    PackOptionsCallback,
    PackActionsCallback,
    show_packs_page,
    get_back_to_main_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

# FSM States
class PackStates:
    waiting_for_pack_name = "waiting_for_pack_name"
    waiting_for_rename = "waiting_for_rename"
    waiting_for_sticker = "waiting_for_sticker"

@router.callback_query(F.data.startswith(PackManagementCallback.VIEW_PACK))
async def view_pack_options(callback: CallbackQuery):
    """Show options for a specific pack"""
    pack_short_name = callback.data.replace(PackManagementCallback.VIEW_PACK, "")
    user_id = callback.from_user.id
    
    try:
        pack = await get_user_pack(user_id, pack_short_name)
        if not pack:
            await callback.answer("Pack not found!")
            return
        
        from templates import PACK_OPTIONS_MESSAGE
        builder = InlineKeyboardBuilder()
        
        # Pack action buttons
        builder.button(text="✏️ Rename Pack", callback_data=f"{PackOptionsCallback.RENAME_PACK}{pack_short_name}")
        builder.button(text="🗑️ Delete Pack", callback_data=f"{PackOptionsCallback.DELETE_PACK}{pack_short_name}")
        builder.button(text="📤 Publish Pack", callback_data=f"{PackOptionsCallback.PUBLISH_PACK}{pack_short_name}")
        builder.button(text="🎨 Add Sticker", callback_data=f"{PackOptionsCallback.ADD_STICKER}{pack_short_name}")
        builder.button(text="🔙 Back", callback_data=PackManagementCallback.BACK_TO_PACKS)
        
        builder.adjust(1, 1, 1, 1, 1)
        
        await callback.message.edit_text(
            PACK_OPTIONS_MESSAGE.format(pack_name=pack["pack_name"]),
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in view_pack_options: {e}")
        await callback.message.edit_text(GENERIC_ERROR_MESSAGE)
        await callback.answer()

@router.callback_query(F.data.startswith(PackOptionsCallback.RENAME_PACK))
async def rename_pack_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompt user to rename pack"""
    pack_short_name = callback.data.replace(PackOptionsCallback.RENAME_PACK, "")
    user_id = callback.from_user.id
    
    try:
        pack = await get_user_pack(user_id, pack_short_name)
        if not pack:
            await callback.answer("Pack not found!")
            return
        
        await state.set_state(PackStates.waiting_for_rename)
        await state.update_data(pack_short_name=pack_short_name, old_name=pack["pack_name"])
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Cancel", callback_data=f"{PackOptionsCallback.BACK_TO_PACK}{pack_short_name}")
        
        await callback.message.edit_text(
            RENAME_PACK_MESSAGE.format(pack_name=pack["pack_name"]),
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in rename_pack_prompt: {e}")
        await callback.message.edit_text(GENERIC_ERROR_MESSAGE)
        await callback.answer()

@router.callback_query(F.data.startswith(PackOptionsCallback.DELETE_PACK))
async def delete_pack_confirmation(callback: CallbackQuery):
    """Show delete pack confirmation"""
    pack_short_name = callback.data.replace(PackOptionsCallback.DELETE_PACK, "")
    user_id = callback.from_user.id
    
    try:
        pack = await get_user_pack(user_id, pack_short_name)
        if not pack:
            await callback.answer("Pack not found!")
            return
        
        # Format created date
        created_at = pack.get("created_at")
        if isinstance(created_at, datetime):
            created_str = created_at.strftime("%Y-%m-%d")
        else:
            created_str = "Unknown"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Confirm Delete", callback_data=f"{PackActionsCallback.CONFIRM_DELETE}{pack_short_name}")
        builder.button(text="❌ Cancel", callback_data=f"{PackOptionsCallback.BACK_TO_PACK}{pack_short_name}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            DELETE_PACK_CONFIRMATION.format(
                pack_name=pack["pack_name"],
                sticker_count=pack.get("sticker_count", 0),
                created_date=created_str
            ),
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in delete_pack_confirmation: {e}")
        await callback.message.edit_text(GENERIC_ERROR_MESSAGE)
        await callback.answer()

@router.callback_query(F.data.startswith(PackActionsCallback.CONFIRM_DELETE))
async def confirm_delete_pack(callback: CallbackQuery):
    """Confirm and delete pack"""
    pack_short_name = callback.data.replace(PackActionsCallback.CONFIRM_DELETE, "")
    user_id = callback.from_user.id
    
    try:
        pack = await get_user_pack(user_id, pack_short_name)
        if not pack:
            await callback.answer("Pack not found!")
            return
        
        pack_name = pack["pack_name"]
        
        # Delete pack from database
        success = await delete_user_pack(user_id, pack_short_name)
        
        if success:
            # Also delete from Telegram (this would require additional implementation)
            # await callback.bot.delete_sticker_set(pack_short_name)
            
            await callback.message.edit_text(
                PACK_DELETED_SUCCESS.format(pack_name=pack_name),
                reply_markup=get_back_to_main_keyboard()
            )
        else:
            await callback.message.edit_text(
                "❌ Failed to delete pack. Please try again.",
                reply_markup=get_back_to_main_keyboard()
            )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in confirm_delete_pack: {e}")
        await callback.message.edit_text(GENERIC_ERROR_MESSAGE)
        await callback.answer()

@router.callback_query(F.data.startswith(PackOptionsCallback.PUBLISH_PACK))
async def publish_pack_request(callback: CallbackQuery):
    """Handle pack publish request"""
    pack_short_name = callback.data.replace(PackOptionsCallback.PUBLISH_PACK, "")
    user_id = callback.from_user.id
    
    try:
        pack = await get_user_pack(user_id, pack_short_name)
        if not pack:
            await callback.answer("Pack not found!")
            return
        
        # Here you would implement the actual publishing logic
        # For now, we'll just show a message
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Back", callback_data=f"{PackOptionsCallback.BACK_TO_PACK}{pack_short_name}")
        
        await callback.message.edit_text(
            PUBLISH_REQUEST_SENT.format(pack_name=pack["pack_name"]),
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in publish_pack_request: {e}")
        await callback.message.edit_text(GENERIC_ERROR_MESSAGE)
        await callback.answer()

@router.callback_query(F.data.startswith(PackOptionsCallback.ADD_STICKER))
async def add_sticker_to_pack(callback: CallbackQuery, state: FSMContext):
    """Prompt user to add sticker to pack"""
    pack_short_name = callback.data.replace(PackOptionsCallback.ADD_STICKER, "")
    user_id = callback.from_user.id
    
    try:
        pack = await get_user_pack(user_id, pack_short_name)
        if not pack:
            await callback.answer("Pack not found!")
            return
        
        # Check if pack is full
        if pack.get("sticker_count", 0) >= 120:
            builder = InlineKeyboardBuilder()
            builder.button(text="🔙 Back", callback_data=f"{PackOptionsCallback.BACK_TO_PACK}{pack_short_name}")
            
            await callback.message.edit_text(
                PACK_FULL_MESSAGE.format(pack_name=pack["pack_name"]),
                reply_markup=builder.as_markup()
            )
            await callback.answer()
            return
        
        await state.set_state(PackStates.waiting_for_sticker)
        await state.update_data(pack_short_name=pack_short_name, pack_name=pack["pack_name"])
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Cancel", callback_data=f"{PackOptionsCallback.BACK_TO_PACK}{pack_short_name}")
        
        await callback.message.edit_text(
            ADD_STICKER_INSTRUCTIONS.format(pack_name=pack["pack_name"]),
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in add_sticker_to_pack: {e}")
        await callback.message.edit_text(GENERIC_ERROR_MESSAGE)
        await callback.answer()

@router.callback_query(F.data.startswith(PackOptionsCallback.BACK_TO_PACK))
async def back_to_pack_options(callback: CallbackQuery):
    """Go back to pack options"""
    pack_short_name = callback.data.replace(PackOptionsCallback.BACK_TO_PACK, "")
    await view_pack_options(callback)

@router.callback_query(F.data == PackManagementCallback.BACK_TO_PACKS)
async def back_to_packs_list(callback: CallbackQuery, state: FSMContext):
    """Go back to packs list"""
    await state.clear()
    user_id = callback.from_user.id
    packs = await get_user_packs(user_id)
    await show_packs_page(callback, packs, 0)
    await callback.answer()

@router.callback_query(F.data.startswith(PackManagementCallback.NEXT_PAGE))
async def next_packs_page(callback: CallbackQuery):
    """Show next page of packs"""
    page = int(callback.data.replace(PackManagementCallback.NEXT_PAGE, ""))
    user_id = callback.from_user.id
    packs = await get_user_packs(user_id)
    await show_packs_page(callback, packs, page)
    await callback.answer()

@router.callback_query(F.data.startswith(PackManagementCallback.PREV_PAGE))
async def prev_packs_page(callback: CallbackQuery):
    """Show previous page of packs"""
    page = int(callback.data.replace(PackManagementCallback.PREV_PAGE, ""))
    user_id = callback.from_user.id
    packs = await get_user_packs(user_id)
    await show_packs_page(callback, packs, page)
    await callback.answer()
