import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from handlers import gban  # import router

from config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Include router
    dp.include_router(gban.router)

    print("Bot started. Send /gban to test.")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
