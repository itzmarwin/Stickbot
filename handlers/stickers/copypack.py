import logging
import asyncio
import re
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputSticker
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramRetryAfter

from mongo.userdb import get_user
from mongo.stickerdb import create_sticker_pack, get_pack_by_short_name, update_pack_sticker_count
from utils.fsm_states import CopyPackStates
from utils.helpers import validate_pack_name, format_pack_name, generate_short_name
from utils.html_utils import escape_html
from config import BOT_USERNAME, LOG_GROUP_ID
from handlers.stickers.kang import get_random_emoji
from rate_limiter import (
    is_copypack_processing, can_copy_pack,
    start_copypack_processing, stop_copypack_processing
)

logger = logging.getLogger(__name__)
router = Router()

MSG_PROCESSING_WAIT = "<b>Please wait!</b>\n\nYour previous pack is still being copied. Try again in a moment."
MSG_RATE_LIMIT = "<b>Please wait {seconds} seconds</b>\n\nYou can copy another pack after that."
MSG_FLOOD_WAIT = "<b>Too many requests!</b>\n\nPlease wait {minutes} minutes and try again."
MSG_INVALID_PACK = "<b>Unable to access this pack</b>\n\nIt may be private or deleted."
MSG_NETWORK_ERROR = "<b>Network error</b>\n\nPlease check your connection and try again."
MSG_FAILED_GENERIC = "<b>Failed to copy pack</b>\n\nPlease try again later."


def parse_error_message(error: Exception) -> str:
    error_str = str(error).lower()
    
    if "flood" in error_str or "retry after" in error_str:
        match = re.search(r'retry (?:in|after) (\d+)', error_str)
        if match:
            seconds = int(match.group(1))
            if seconds >= 60:
                minutes = seconds // 60
                return MSG_FLOOD_WAIT.format(minutes=minutes)
            else:
                return MSG_RATE_LIMIT.format(seconds=seconds)
        return MSG_FLOOD_WAIT.format(minutes=1)
    
    elif "stickerset_invalid" in error_str or "not found" in error_str:
        return MSG_INVALID_PACK
    
    elif "network" in error_str or "connection" in error_str or "timeout" in error_str:
        return MSG_NETWORK_ERROR
    
    else:
        return MSG_FAILED_GENERIC


async def copy_pack_background(
    bot: Bot,
    user_id: int,
    source_pack_name: str,
    new_pack_name: str,
    new_short_name: str,
    chat_id: int,
    progress_msg_id: int
):
    
    try:
        source_pack = await bot.get_sticker_set(source_pack_name)
        total_stickers = len(source_pack.stickers)
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg_id,
            text=f"⏳ <b>𝖢𝗈𝗉𝗒𝗂𝗇𝗀 𝗉𝖺𝖼𝗄...</b>\n\n"
                 f"𝖥𝗈𝗎𝗇𝖽 {total_stickers} 𝗌𝗍𝗂𝖼𝗄𝖾𝗋𝗌 𝗍𝗈 𝖼𝗈𝗉𝗒.\n"
                 f"𝖳𝗁𝗂𝗌 𝗆𝖺𝗒 𝗍𝖺𝗄𝖾 𝖺 𝖿𝖾𝗐 𝗆𝗈𝗆𝖾𝗇𝗍𝗌..."
        )
        
        first_sticker = source_pack.stickers[0]
        emoji_list = [first_sticker.emoji] if first_sticker.emoji else [get_random_emoji()]
        
        sticker_input = InputSticker(
            sticker=first_sticker.file_id,
            emoji_list=emoji_list,
            format="static" if not first_sticker.is_video else "video"
        )
        
        await bot.create_new_sticker_set(
            user_id=user_id,
            name=new_short_name,
            title=new_pack_name,
            stickers=[sticker_input]
        )
        
        await create_sticker_pack(
            user_id=user_id,
            pack_name=new_pack_name,
            short_name=new_short_name
        )
        
        copied_count = 1
        failed_count = 0
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg_id,
            text=f"⏳ <b>𝖢𝗈𝗉𝗒𝗂𝗇𝗀 𝗌𝗍𝗂𝖼𝗄𝖾𝗋𝗌...</b>\n\n"
                 f"𝖯𝗋𝗈𝗀𝗋𝖾𝗌𝗌: {copied_count}/{total_stickers}"
        )
        
        for i, sticker in enumerate(source_pack.stickers[1:], start=2):
            try:
                emoji_list = [sticker.emoji] if sticker.emoji else [get_random_emoji()]
                
                sticker_input = InputSticker(
                    sticker=sticker.file_id,
                    emoji_list=emoji_list,
                    format="static" if not sticker.is_video else "video"
                )
                
                await bot.add_sticker_to_set(
                    user_id=user_id,
                    name=new_short_name,
                    sticker=sticker_input
                )
                
                copied_count += 1
                
                if i % 10 == 0 or i == total_stickers:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_msg_id,
                        text=f"⏳ <b>𝖢𝗈𝗉𝗒𝗂𝗇𝗀 𝗌𝗍𝗂𝖼𝗄𝖾𝗋𝗌...</b>\n\n"
                             f"𝖯𝗋𝗈𝗀𝗋𝖾𝗌𝗌: {copied_count}/{total_stickers}"
                    )
                
                await asyncio.sleep(0.3)
                
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                
                try:
                    await bot.add_sticker_to_set(
                        user_id=user_id,
                        name=new_short_name,
                        sticker=sticker_input
                    )
                    copied_count += 1
                except:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error adding sticker {i}: {e}")
                failed_count += 1
                continue
        
        await update_pack_sticker_count(new_short_name, copied_count)
        
        pack_link = f"https://t.me/addstickers/{new_short_name}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔗 𝗩𝗶𝗲𝘄 𝗣𝗮𝗰𝗸", url=pack_link)
        ]])
        
        success_message = (
            f"<b>𝖯𝖺𝖼𝗄 𝖼𝗈𝗉𝗂𝖾𝖽 𝗌𝗎𝖼𝖼𝖾𝗌𝗌𝖿𝗎𝗅𝗅𝗒!</b>\n\n"
            f"<b>𝖭𝖾𝗐 𝗉𝖺𝖼𝗄:</b> {escape_html(new_pack_name.replace(f' ~ @{BOT_USERNAME}', ''))}\n"
            f"<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌 𝖼𝗈𝗉𝗂𝖾𝖽:</b> {copied_count}/{total_stickers}"
        )
        
        if failed_count > 0:
            success_message += f"\n<b>𝖥𝖺𝗂𝗅𝖾𝖽:</b> {failed_count}"
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg_id,
            text=success_message,
            reply_markup=keyboard
        )
        
        if LOG_GROUP_ID:
            try:
                log_msg = (
                    f"<b>Pack Copied</b>\n\n"
                    f"<b>User:</b> {user_id}\n"
                    f"<b>Source:</b> {source_pack_name}\n"
                    f"<b>New Pack:</b> {new_short_name}\n"
                    f"<b>Stickers:</b> {copied_count}/{total_stickers}"
                )
                await bot.send_message(LOG_GROUP_ID, log_msg)
            except:
                pass
        
    except Exception as e:
        logger.error(f"Critical error in copy_pack_background: {e}")
        
        error_message = parse_error_message(e)
        
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg_id,
                text=error_message
            )
        except:
            pass
    
    finally:
        stop_copypack_processing(user_id)


@router.message(Command("copypack"))
async def cmd_copypack(message: Message, state: FSMContext):
    try:
        if not message.reply_to_message:
            await message.reply(
                "<b>𝖯𝗅𝖾𝖺𝗌𝖾 𝗋𝖾𝗉𝗅𝗒 𝗍𝗈 𝖺 𝗌𝗍𝗂𝖼𝗄𝖾𝗋</b>\n\n"
                "𝖴𝗌𝖺𝗀𝖾: 𝖱𝖾𝗉𝗅𝗒 𝗍𝗈 𝖺𝗇𝗒 𝗌𝗍𝗂𝖼𝗄𝖾𝗋 𝗐𝗂𝗍𝗁 /copypack"
            )
            return
        
        if not message.reply_to_message.sticker:
            await message.reply(
                "<b>𝖳𝗁𝖺𝗍'𝗌 𝗇𝗈𝗍 𝖺 𝗌𝗍𝗂𝖼𝗄𝖾𝗋</b>\n\n"
                "𝖯𝗅𝖾𝖺𝗌𝖾 𝗋𝖾𝗉𝗅𝗒 𝗍𝗈 𝖺 𝗌𝗍𝗂𝖼𝗄𝖾𝗋 𝖿𝗋𝗈𝗆 𝖺 𝗉𝖺𝖼𝗄."
            )
            return
        
        sticker = message.reply_to_message.sticker
        
        if not sticker.set_name:
            await message.reply(
                "<b>𝖳𝗁𝗂𝗌 𝗌𝗍𝗂𝖼𝗄𝖾𝗋 𝖽𝗈𝖾𝗌𝗇'𝗍 𝖻𝖾𝗅𝗈𝗇𝗀 𝗍𝗈 𝖺 𝗉𝖺𝖼𝗄</b>\n\n"
                "𝖯𝗅𝖾𝖺𝗌𝖾 𝗋𝖾𝗉𝗅𝗒 𝗍𝗈 𝖺 𝗌𝗍𝗂𝖼𝗄𝖾𝗋 𝖿𝗋𝗈𝗆 𝖺 𝗌𝗍𝗂𝖼𝗄𝖾𝗋 𝗉𝖺𝖼𝗄."
            )
            return
        
        user_id = message.from_user.id
        
        if await is_copypack_processing(user_id):
            await message.reply(MSG_PROCESSING_WAIT)
            return
        
        can_copy, remaining = await can_copy_pack(user_id)
        if not can_copy:
            await message.reply(MSG_RATE_LIMIT.format(seconds=remaining))
            return
        
        user = await get_user(user_id)
        if not user or not user.get("has_started", False):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="𝗦𝘁𝗮𝗿𝘁 𝗺𝗲",
                    url=f"https://t.me/{BOT_USERNAME}?start=copypack"
                )
            ]])
            await message.reply(
                "<b>𝖸𝗈𝗎 𝗇𝖾𝖾𝖽 𝗍𝗈 𝗌𝗍𝖺𝗋𝗍 𝗆𝖾 𝖿𝗂𝗋𝗌𝗍.</b>",
                reply_markup=keyboard
            )
            return
        
        source_pack_name = sticker.set_name
        
        try:
            source_pack = await message.bot.get_sticker_set(source_pack_name)
        except Exception as e:
            error_message = parse_error_message(e)
            await message.reply(error_message)
            return
        
        if len(source_pack.stickers) > 120:
            await message.reply(
                f"<b>𝖯𝖺𝖼𝗄 𝗍𝗈𝗈 𝗅𝖺𝗋𝗀𝖾</b>\n\n"
                f"𝖳𝗁𝗂𝗌 𝗉𝖺𝖼𝗄 𝗁𝖺𝗌 {len(source_pack.stickers)} 𝗌𝗍𝗂𝖼𝗄𝖾𝗋𝗌.\n"
                f"𝖬𝖺𝗑𝗂𝗆𝗎𝗆 𝖺𝗅𝗅𝗈𝗐𝖾𝖽: 120 𝗌𝗍𝗂𝖼𝗄𝖾𝗋𝗌."
            )
            return
        
        await state.set_state(CopyPackStates.waiting_for_pack_name)
        await state.update_data(
            source_pack_name=source_pack_name,
            source_pack_title=source_pack.title,
            sticker_count=len(source_pack.stickers)
        )
        
        escaped_title = escape_html(source_pack.title)
        await message.reply(
            f"<b>𝖲𝗈𝗎𝗋𝖼𝖾 𝗉𝖺𝖼𝗄 𝖿𝗈𝗎𝗇𝖽</b>\n\n"
            f"<b>𝖭𝖺𝗆𝖾:</b> {escaped_title}\n"
            f"<b>𝖲𝗍𝗂𝖼𝗄𝖾𝗋𝗌:</b> {len(source_pack.stickers)}\n\n"
            f"𝖯𝗅𝖾𝖺𝗌𝖾 𝗌𝖾𝗇𝖽 𝗆𝖾 𝖺 𝗇𝖾𝗐 𝗇𝖺𝗆𝖾 𝖿𝗈𝗋 𝗒𝗈𝗎𝗋 𝖼𝗈𝗉𝗂𝖾𝖽 𝗉𝖺𝖼𝗄.\n\n"
            f"<i>𝖸𝗈𝗎 𝖼𝖺𝗇 𝗎𝗌𝖾 𝖺𝗇𝗒 𝗌𝗒𝗆𝖻𝗈𝗅𝗌, 𝖾𝗆𝗈𝗃𝗂𝗌, 𝗈𝗋 𝖿𝗈𝗇𝗍𝗌 𝗂𝗇 𝗍𝗁𝖾 𝗇𝖺𝗆𝖾.</i>"
        )
        
    except Exception as e:
        logger.error(f"Error in cmd_copypack: {e}")
        await message.reply(
            "<b>𝖠𝗇 𝖾𝗋𝗋𝗈𝗋 𝗈𝖼𝖼𝗎𝗋𝗋𝖾𝖽</b>\n\n"
            "𝖯𝗅𝖾𝖺𝗌𝖾 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇 𝗅𝖺𝗍𝖾𝗋."
        )


@router.message(CopyPackStates.waiting_for_pack_name)
async def process_copypack_name(message: Message, state: FSMContext, bot: Bot):
    try:
        if not message.text:
            await message.reply("<b>𝖯𝗅𝖾𝖺𝗌𝖾 𝗌𝖾𝗇𝖽 𝖺 𝗏𝖺𝗅𝗂𝖽 𝗉𝖺𝖼𝗄 𝗇𝖺𝗆𝖾.</b>")
            return
        
        new_pack_name = message.text.strip()
        
        is_valid, error = validate_pack_name(new_pack_name)
        
        if not is_valid:
            if error == "pack_name_too_long":
                await message.reply(
                    "<b>𝖯𝖺𝖼𝗄 𝗇𝖺𝗆𝖾 𝗂𝗌 𝗍𝗈𝗈 𝗅𝗈𝗇𝗀!</b>\n\n"
                    "𝖬𝖺𝗑𝗂𝗆𝗎𝗆 64 𝖼𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌 𝖺𝗅𝗅𝗈𝗐𝖾𝖽."
                )
            else:
                await message.reply(
                    "<b>𝖨𝗇𝗏𝖺𝗅𝗂𝖽 𝗉𝖺𝖼𝗄 𝗇𝖺𝗆𝖾!</b>\n\n"
                    "𝖯𝗅𝖾𝖺𝗌𝖾 𝗎𝗌𝖾 𝖺 𝗏𝖺𝗅𝗂𝖽 𝗇𝖺𝗆𝖾."
                )
            return
        
        data = await state.get_data()
        source_pack_name = data.get("source_pack_name")
        
        if not source_pack_name:
            await message.reply(
                "<b>𝖲𝖾𝗌𝗌𝗂𝗈𝗇 𝖾𝗑𝗉𝗂𝗋𝖾𝖽</b>\n\n"
                "𝖯𝗅𝖾𝖺𝗌𝖾 𝗌𝗍𝖺𝗋𝗍 𝖺𝗀𝖺𝗂𝗇 𝗐𝗂𝗍𝗁 /copypack"
            )
            await state.clear()
            return
        
        formatted_name = format_pack_name(new_pack_name)
        new_short_name = generate_short_name(new_pack_name, message.from_user.id)
        
        existing_pack = await get_pack_by_short_name(new_short_name)
        if existing_pack:
            await message.reply(
                "<b>𝖯𝖺𝖼𝗄 𝖺𝗅𝗋𝖾𝖺𝖽𝗒 𝖾𝗑𝗂𝗌𝗍𝗌</b>\n\n"
                "𝖯𝗅𝖾𝖺𝗌𝖾 𝖼𝗁𝗈𝗈𝗌𝖾 𝖺 𝖽𝗂𝖿𝖿𝖾𝗋𝖾𝗇𝗍 𝗇𝖺𝗆𝖾."
            )
            return
        
        progress_msg = await message.reply(
            "⏳ <b>𝖲𝗍𝖺𝗋𝗍𝗂𝗇𝗀 𝖼𝗈𝗉𝗒 𝗉𝗋𝗈𝖼𝖾𝗌𝗌...</b>\n\n"
            "𝖯𝗅𝖾𝖺𝗌𝖾 𝗐𝖺𝗂𝗍 𝗐𝗁𝗂𝗅𝖾 𝖨 𝖼𝗈𝗉𝗒 𝖺𝗅𝗅 𝗌𝗍𝗂𝖼𝗄𝖾𝗋𝗌."
        )
        
        await state.clear()
        
        start_copypack_processing(message.from_user.id)
        
        asyncio.create_task(
            copy_pack_background(
                bot=bot,
                user_id=message.from_user.id,
                source_pack_name=source_pack_name,
                new_pack_name=formatted_name,
                new_short_name=new_short_name,
                chat_id=message.chat.id,
                progress_msg_id=progress_msg.message_id
            )
        )
        
    except Exception as e:
        logger.error(f"Error in process_copypack_name: {e}")
        await message.reply(
            "<b>𝖥𝖺𝗂𝗅𝖾𝖽 𝗍𝗈 𝗌𝗍𝖺𝗋𝗍 𝖼𝗈𝗉𝗒</b>\n\n"
            "𝖯𝗅𝖾𝖺𝗌𝖾 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇 𝗅𝖺𝗍𝖾𝗋."
        )
        await state.clear()
