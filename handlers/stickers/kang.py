import os
import logging
import random
import time
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputSticker, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from mongo.userdb import get_user
from mongo.stickerdb import (
    get_user_active_pack, create_sticker_pack,
    increment_sticker_count, delete_user_pack, get_user_all_packs,
    update_pack_sticker_count
)
from templates import (
    NEED_TO_START, ASK_PACK_NAME, PACK_CREATED,
    STICKER_ADDED, NO_MEDIA_REPLY, VIDEO_TOO_LARGE,
    PACK_NAME_INVALID, PROCESSING_MEDIA,
    ERROR_OCCURRED, VIDEO_COMPRESSION_FAILED,
    PACK_FULL_MESSAGE, NEW_PACK_CREATED_MULTI,
    STICKER_ADDED_SIMPLE, PACK_NOT_FOUND_MESSAGE,
    STATE_CANCELLED_MESSAGE
)
from utils.fsm_states import KangStates
from utils.helpers import (
    validate_pack_name, generate_short_name,
    format_pack_name, get_file_size_mb
)
from utils.converters import (
    convert_image_to_webp, convert_video_to_webm,
    cleanup_temp_files, create_temp_dir
)
from config import BOT_USERNAME, MAX_VIDEO_SIZE_MB
from rate_limiter import is_rate_limited

logger = logging.getLogger(__name__)
router = Router()

EMOJI_LIST = ["😀", "😂", "🥰", "😎", "🤯", "😱", "😜", "🤖", "🐱", "🌸", "🍕", "🎉", "❤️", "✨", "⭐"]


def get_random_emoji():
    return random.choice(EMOJI_LIST)


@router.message(Command("kang"))
async def cmd_kang(message: Message, state: FSMContext, bot: Bot):
    if await is_rate_limited(message.from_user.id):
        await message.reply("⏳ Please wait a few seconds before making another request.")
        return

    user_id = message.from_user.id
    processing_msg = None

    try:
        user = await get_user(user_id)
        if not user or not user.get("has_started", False):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="Start me",
                    url=f"https://t.me/{BOT_USERNAME}?start=kang"
                )
            ]])
            await message.reply(NEED_TO_START, reply_markup=keyboard)
            return

        if not message.reply_to_message:
            await message.reply(NO_MEDIA_REPLY)
            return

        replied_msg = message.reply_to_message

        media = None
        media_type = None

        if replied_msg.photo:
            media = replied_msg.photo[-1]
            media_type = "photo"
        elif replied_msg.sticker:
            media = replied_msg.sticker
            media_type = "sticker"
        elif replied_msg.animation:
            media = replied_msg.animation
            media_type = "animation"
        elif replied_msg.video:
            media = replied_msg.video
            media_type = "video"

        if not media:
            await message.reply(NO_MEDIA_REPLY)
            return

        if media_type == "video":
            file_size_mb = get_file_size_mb(media.file_size)
            if file_size_mb > MAX_VIDEO_SIZE_MB:
                await message.reply(VIDEO_TOO_LARGE)
                return

        active_pack = await get_user_active_pack(user_id)

        if not active_pack:
            await state.set_state(KangStates.waiting_for_pack_name)
            await state.update_data(media=media.file_id, media_type=media_type)
            await message.reply(ASK_PACK_NAME)
            return

        processing_msg = await message.reply(PROCESSING_MEDIA)

        success, pack_full = await add_sticker_to_pack(
            bot=bot,
            user_id=user_id,
            pack_short_name=active_pack["short_name"],
            pack_data=active_pack,
            media=media,
            media_type=media_type,
            message=message,
            state=state
        )

        if success:
            try:
                telegram_pack = await bot.get_sticker_set(active_pack["short_name"])
                real_count = len(telegram_pack.stickers)
                await update_pack_sticker_count(active_pack["short_name"], real_count)
            except:
                await increment_sticker_count(user_id)
                updated_pack = await get_user_active_pack(user_id)
                real_count = updated_pack.get("sticker_count", 0) if updated_pack else 0

            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="View Pack",
                    url=active_pack["pack_link"]
                )
            ]])

            await processing_msg.edit_text(
                STICKER_ADDED_SIMPLE.format(sticker_count=real_count),
                reply_markup=keyboard
            )

        elif pack_full:
            await processing_msg.delete()
            await state.set_state(KangStates.waiting_for_pack_name)
            await state.update_data(media=media.file_id, media_type=media_type)

            all_packs = await get_user_all_packs(user_id)
            pack_count = len(all_packs)

            await message.reply(PACK_FULL_MESSAGE.format(pack_count=pack_count))

        else:
            await processing_msg.edit_text(ERROR_OCCURRED)

    except Exception as e:
        logger.error(f"Error in kang command: {e}")
        await state.clear()

        if processing_msg:
            try:
                await processing_msg.edit_text(ERROR_OCCURRED)
            except:
                await message.reply(ERROR_OCCURRED)
        else:
            await message.reply(ERROR_OCCURRED)


@router.message(KangStates.waiting_for_pack_name)
async def process_pack_name(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.reply(STATE_CANCELLED_MESSAGE)
        await state.clear()
        return

    pack_name = message.text.strip()
    processing_msg = None
    temp_files = []

    try:
        is_valid, error = validate_pack_name(pack_name)

        if not is_valid:
            if error == "pack_name_too_long":
                await message.reply(PACK_NAME_INVALID.format(length=len(pack_name)))
            else:
                await message.reply(ERROR_OCCURRED)
            return

        data = await state.get_data()
        media_file_id = data.get("media")
        media_type = data.get("media_type")

        if not media_file_id:
            await message.reply(ERROR_OCCURRED)
            await state.clear()
            return

        user_id = message.from_user.id
        formatted_pack_name = format_pack_name(pack_name)
        short_name = generate_short_name(pack_name, user_id)

        processing_msg = await message.reply(PROCESSING_MEDIA)

        file = await bot.get_file(media_file_id)
        timestamp = int(time.time() * 1000)
        temp_dir = create_temp_dir()

        sticker_file = None

        if media_type == "sticker":
            sticker_file = media_file_id
            sticker_format = "static"

        elif media_type == "photo":
            input_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_input.jpg")
            output_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_output.webp")
            temp_files.extend([input_path, output_path])

            await bot.download_file(file.file_path, input_path)

            if await convert_image_to_webp(input_path, output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webp")
                sticker_format = "static"
            else:
                await processing_msg.edit_text("❌ Failed to convert image.")
                await state.clear()
                return

        elif media_type in ["animation", "video"]:
            input_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_input.mp4")
            output_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_output.webm")
            temp_files.extend([input_path, output_path])

            await bot.download_file(file.file_path, input_path)

            conversion_success = await convert_video_to_webm(input_path, output_path)

            if conversion_success and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webm")
                sticker_format = "video"
            else:
                await processing_msg.edit_text(VIDEO_COMPRESSION_FAILED)
                await state.clear()
                return

        if not sticker_file:
            await processing_msg.edit_text("❌ Failed to prepare sticker file.")
            await state.clear()
            return

        random_emoji = get_random_emoji()

        sticker = InputSticker(
            sticker=sticker_file,
            emoji_list=[random_emoji],
            format=sticker_format
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await bot.create_new_sticker_set(
                    user_id=user_id,
                    name=short_name,
                    title=formatted_pack_name,
                    stickers=[sticker]
                )
                break

            except Exception as e:
                error_msg = str(e)

                if "STICKERSET_INVALID" in error_msg and attempt < max_retries - 1:
                    short_name = generate_short_name(pack_name, user_id)
                    continue
                elif attempt == max_retries - 1:
                    raise
                else:
                    raise

        pack_link = f"https://t.me/addstickers/{short_name}"
        await create_sticker_pack(
            user_id=user_id,
            pack_name=formatted_pack_name,
            short_name=short_name
        )

        all_packs = await get_user_all_packs(user_id)
        pack_count = len(all_packs)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="View Pack",
                url=pack_link
            )
        ]])

        await processing_msg.edit_text(
            NEW_PACK_CREATED_MULTI.format(
                pack_name=formatted_pack_name,
                pack_count=pack_count
            ),
            reply_markup=keyboard
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Error processing pack name: {e}")
        await state.clear()

        if processing_msg:
            try:
                await processing_msg.edit_text(ERROR_OCCURRED)
            except:
                await message.reply(ERROR_OCCURRED)
        else:
            await message.reply(ERROR_OCCURRED)

    finally:
        cleanup_temp_files(*temp_files)


async def add_sticker_to_pack(bot: Bot, user_id: int, pack_short_name: str,
                              pack_data: dict, media, media_type: str,
                              message: Message, state: FSMContext):
    temp_files = []

    try:
        timestamp = int(time.time() * 1000)
        temp_dir = create_temp_dir()
        sticker_file = None

        if media_type == "sticker":
            sticker_file = media.file_id
            sticker_format = "static" if not media.is_video else "video"

        elif media_type == "photo":
            file = await bot.get_file(media.file_id)
            input_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_add_input.jpg")
            output_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_add_output.webp")
            temp_files.extend([input_path, output_path])

            await bot.download_file(file.file_path, input_path)

            if await convert_image_to_webp(input_path, output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webp")
                sticker_format = "static"
            else:
                return False, False

        elif media_type in ["animation", "video"]:
            file = await bot.get_file(media.file_id)
            input_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_add_input.mp4")
            output_path = os.path.join(temp_dir, f"{user_id}_{timestamp}_add_output.webm")
            temp_files.extend([input_path, output_path])

            await bot.download_file(file.file_path, input_path)

            conversion_success = await convert_video_to_webm(input_path, output_path)

            if conversion_success and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    sticker_file = BufferedInputFile(f.read(), filename="sticker.webm")
                sticker_format = "video"
            else:
                return False, False

        if not sticker_file:
            return False, False

        random_emoji = get_random_emoji()

        sticker = InputSticker(
            sticker=sticker_file,
            emoji_list=[random_emoji],
            format=sticker_format
        )

        try:
            count_before = 0
            try:
                pack_before = await bot.get_sticker_set(pack_short_name)
                count_before = len(pack_before.stickers)
            except:
                pass

            await bot.add_sticker_to_set(
                user_id=user_id,
                name=pack_short_name,
                sticker=sticker
            )

            try:
                pack_after = await bot.get_sticker_set(pack_short_name)
                count_after = len(pack_after.stickers)

                if count_after == count_before + 1:
                    return True, False
                else:
                    return False, False
            except:
                return True, False

        except Exception as e:
            error_msg = str(e)

            if "STICKERSET_INVALID" in error_msg:
                await delete_user_pack(user_id)

                await state.update_data(
                    media=media.file_id,
                    media_type=media_type
                )
                await state.set_state(KangStates.waiting_for_pack_name)
                await message.reply(PACK_NOT_FOUND_MESSAGE)
                return False, False

            elif "STICKERS_TOO_MUCH" in error_msg:
                await update_pack_sticker_count(pack_short_name, 120)
                return False, True

            else:
                return False, False

    except Exception as e:
        logger.error(f"Unexpected error in add_sticker_to_pack: {e}")
        return False, False

    finally:
        cleanup_temp_files(*temp_files)
