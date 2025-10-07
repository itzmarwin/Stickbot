# handlers/gban.py
from aiogram import Router, types
from aiogram.filters import Command

router = Router()  # Router create

@router.message(Command("gban"))
async def gban_handler(message: types.Message):
    print(f"/gban command received from user: {message.from_user.id}")
    await message.reply("GBAN command received! ✅")
