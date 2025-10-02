from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from database import get_total_users_count, get_total_packs_count
from config import OWNER_ID

router = Router()

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Handle /stats command - show bot statistics (owner only)"""
    if message.from_user.id != OWNER_ID:
        return
    
    total_users = await get_total_users_count()
    total_packs = await get_total_packs_count()
    
    stats_msg = f"""
<b>📊 Bot Statistics</b>

<b>Total Users:</b> {total_users}
<b>Total Packs:</b> {total_packs}
"""
    
    await message.answer(stats_msg)

@router.message(F.text)
async def handle_text_messages(message: Message):
    """Handle any unhandled text messages"""
    # This catches any text that doesn't match other handlers
    # You can add a default response here if needed
    pass
