# handlers/gban.py
from aiogram import Router, types
from aiogram.filters import Command

router = Router()  # Router create

@router.message(Command("gban", ignore_case=True))
async def gban_test_handler(message: types.Message):
    # Terminal me print hoga
    print(f"[DEBUG] /gban command received from user: {message.from_user.id}")

    # User ko reply bhi bhejega
    await message.reply("✅ GBAN command received!")
