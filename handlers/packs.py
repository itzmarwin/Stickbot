from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from database import get_user_pack
from templates import NO_PACK_YET, YOUR_PACK_INFO

router = Router()

@router.message(Command("packs"))
async def cmd_packs(message: Message):
    """Handle /packs command - show user's sticker pack info"""
    user_id = message.from_user.id
    
    # Get user's pack
    pack = await get_user_pack(user_id)
    
    if not pack:
        await message.answer(NO_PACK_YET)
        return
    
    # Format created date
    created_at = pack.get("created_at")
    if isinstance(created_at, datetime):
        created_str = created_at.strftime("%Y-%m-%d")
    else:
        created_str = "Unknown"
    
    # Create inline button to open pack
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📦 Open Pack",
            url=pack["pack_link"]
        )
    ]])
    
    pack_info = YOUR_PACK_INFO.format(
        pack_name=pack["pack_name"],
        sticker_count=pack.get("sticker_count", 0),
        created_at=created_str,
        pack_link=pack["pack_link"]
    )
    
    await message.answer(pack_info, reply_markup=keyboard)
