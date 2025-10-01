from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from utils import (
    is_private_chat, is_group_chat, extract_sticker_from_message, extract_gif_from_message,
    validate_pack_name, generate_pack_short_name, generate_pack_link, 
    format_sticker_success_message, create_sticker_pack_fast, 
    add_sticker_to_pack_fast, download_gif, convert_gif_to_webm_optimized, cleanup_temp_file
)
from middlewares import DatabaseOperations
from database import StickerPack
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

# Create router for kang command
kang_router = Router()


class KangStates(StatesGroup):
    waiting_for_pack_name = State()


@kang_router.message(Command("kang"))
async def kang_command(message: Message, bot: Bot, state: FSMContext, db_operations: DatabaseOperations):
    """
    /kang command - works in groups when replying to sticker/GIF
    Checks if user started bot first
    """
    
    # Check if command is used in private chat
    if is_private_chat(message):
        await message.answer("⚠️ Please use /kang in a group by replying to a sticker or GIF")
        return
    
    # Check if command is used in group
    if not is_group_chat(message):
        return
    
    # Check if replying to a sticker or GIF
    sticker = extract_sticker_from_message(message)
    gif = extract_gif_from_message(message) if not sticker else None
    
    if not sticker and not gif:
        await message.answer(
            "⚠️ Please reply to a sticker or GIF with /kang to add it to your pack",
            reply_to_message_id=message.message_id
        )
        return
    
    try:
        # Get user data - don't create if not exists
        user_data = await db_operations.get_user_data()
        
        # Check if user has started the bot
        if not user_data or not user_data.started:
            # User hasn't started the bot - send start message with button
            start_url = f"https://t.me/Stickerkangbot?start=start"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Start Me", url=start_url)]
            ])
            
            await message.answer(
                "𝐎𝐨𝐩𝐬! 𝐘𝐨𝐮 𝐧𝐞𝐞𝐝 𝐭𝐨 𝐬𝐭𝐚𝐫𝐭 𝐦𝐞 𝐟𝐢𝐫𝐬𝐭 𝐭𝐨 𝐮𝐬𝐞 𝐭𝐡𝐢𝐬 𝐛𝐨𝐭.",
                reply_markup=keyboard,
                reply_to_message_id=message.message_id
            )
            return
        
        # User has started bot - proceed with kang process
        if gif:
            await handle_gif_kang_fast(message, bot, state, db_operations, gif, user_data)
        else:
            await handle_sticker_kang_fast(message, bot, state, db_operations, sticker, user_data)
            
    except Exception as e:
        logger.error(f"Error in kang command for user {message.from_user.id}: {e}")
        await message.answer(
            "❌ Something went wrong. Please try again later.",
            reply_to_message_id=message.message_id
        )


async def handle_sticker_kang_fast(message: Message, bot: Bot, state: FSMContext, db_operations: DatabaseOperations, sticker, user_data):
    """Handle sticker kang for users who have started the bot"""
    
    # Check if user has active packs (not full)
    if user_data.has_active_packs():
        # Add to latest active pack
        latest_pack = user_data.get_latest_pack()
        
        success = await add_sticker_to_pack_fast(
            bot=bot,
            user_id=message.from_user.id,
            pack_short_name=latest_pack.pack_short_name,
            sticker=sticker
        )
        
        if success:
            # Update sticker count in pack
            latest_pack.sticker_count += 1
            await db_operations.save_user_data(user_data)
            
            sticker_emoji = sticker.emoji or "🔥"
            message_text, keyboard = format_sticker_success_message(
                latest_pack.pack_link,
                sticker_emoji
            )
            await message.answer(
                message_text,
                reply_to_message_id=message.message_id,
                reply_markup=keyboard
            )
            
            # Check if pack is now full
            if latest_pack.is_full():
                await message.answer(
                    "📦 Your sticker pack is now full! The next sticker will create a new pack.",
                    reply_to_message_id=message.message_id
                )
        else:
            await message.answer(
                "❌ Failed to add sticker to pack. Please try again.",
                reply_to_message_id=message.message_id
            )
    
    else:
        # No active packs or all packs are full - ask for new pack name
        await state.set_state(KangStates.waiting_for_pack_name)
        
        await state.update_data(
            user_id=message.from_user.id,
            sticker_file_id=sticker.file_id,
            sticker_emoji=sticker.emoji,
            sticker_is_video=sticker.is_video,
            sticker_is_animated=sticker.is_animated,
            chat_id=message.chat.id,
            reply_to_message_id=message.message_id,
            is_gif_conversion=False
        )
        
        await message.answer(
            "🆕 You don't have any active sticker packs!\n\n"
            "Please reply to this message with a name for your new sticker pack:",
            reply_to_message_id=message.message_id
        )


async def handle_gif_kang_fast(message: Message, bot: Bot, state: FSMContext, db_operations: DatabaseOperations, gif_object, user_data):
    """Handle GIF kang for users who have started the bot"""
    
    processing_msg = await message.answer(
        "🔄 Processing...",
        reply_to_message_id=message.message_id
    )
    
    gif_file_path = await download_gif(bot, gif_object)
    if not gif_file_path:
        await processing_msg.edit_text("❌ Failed to download GIF. Please try again.")
        return
    
    try:
        webm_file_path = await convert_gif_to_webm_optimized(gif_file_path)
        if not webm_file_path:
            await processing_msg.edit_text("❌ Failed to convert GIF. Please try again.")
            return
        
        try:
            # Check if user has active packs
            if user_data.has_active_packs():
                latest_pack = user_data.get_latest_pack()
                
                success = await add_converted_sticker_to_pack_fast(
                    bot=bot,
                    user_id=message.from_user.id,
                    pack_short_name=latest_pack.pack_short_name,
                    webm_file_path=webm_file_path
                )
                
                if success:
                    # Update sticker count
                    latest_pack.sticker_count += 1
                    await db_operations.save_user_data(user_data)
                    
                    message_text, keyboard = format_sticker_success_message(
                        latest_pack.pack_link, "🎬"
                    )
                    await processing_msg.edit_text(message_text, reply_markup=keyboard)
                    
                    if latest_pack.is_full():
                        await message.answer(
                            "📦 Your sticker pack is now full! The next sticker will create a new pack.",
                            reply_to_message_id=message.message_id
                        )
                else:
                    await processing_msg.edit_text("❌ Failed to add converted GIF to pack.")
            
            else:
                # No active packs - ask for pack name
                await state.set_state(KangStates.waiting_for_pack_name)
                
                await state.update_data(
                    user_id=message.from_user.id,
                    is_gif_conversion=True,
                    webm_file_path=webm_file_path,
                    chat_id=message.chat.id,
                    reply_to_message_id=message.message_id
                )
                
                await processing_msg.edit_text(
                    "🆕 You don't have any active sticker packs!\n\n"
                    "Please reply to this message with a name for your new sticker pack:"
                )
        
        finally:
            if not await state.get_data() or not (await state.get_data()).get('webm_file_path'):
                cleanup_temp_file(webm_file_path)
    
    finally:
        cleanup_temp_file(gif_file_path)


@kang_router.message(KangStates.waiting_for_pack_name)
async def process_pack_name_fast(message: Message, bot: Bot, state: FSMContext, db_operations: DatabaseOperations):
    """Process pack name from user reply"""
    
    # Check if this is a reply to bot's message
    if not message.reply_to_message:
        await message.answer("❌ Please reply to my message with the pack name.")
        return
    
    # Only accept text messages for pack name
    if not message.text:
        await message.answer("❌ Please send a text message with your pack name.")
        return
    
    pack_name = message.text.strip()
    
    # Validate pack name
    is_valid, error_message = validate_pack_name(pack_name)
    if not is_valid:
        await message.answer(f"❌ {error_message}\n\nPlease send a valid pack name:")
        return
    
    try:
        data = await state.get_data()
        
        if not data.get('user_id'):
            await message.answer("❌ Session expired. Please try /kang again.")
            await state.clear()
            return
        
        if data.get('is_gif_conversion'):
            await handle_gif_pack_creation_fast(message, bot, state, db_operations, pack_name, data)
        else:
            await handle_sticker_pack_creation_fast(message, bot, state, db_operations, pack_name, data)
            
    except Exception as e:
        logger.error(f"Error creating pack for user {message.from_user.id}: {e}")
        await message.answer("❌ Failed to create sticker pack. Please try again.")
    finally:
        await state.clear()


async def handle_gif_pack_creation_fast(message: Message, bot: Bot, state: FSMContext, db_operations: DatabaseOperations, pack_name: str, data: dict):
    """Create new pack with GIF"""
    webm_file_path = data.get('webm_file_path')
    user_id = data.get('user_id')
    
    if not webm_file_path or not user_id:
        await message.answer("❌ Data lost. Please try /kang again.")
        return
    
    try:
        pack_name_with_bot = f"{pack_name} by @{settings.BOT_USERNAME}"
        pack_short_name = generate_pack_short_name(pack_name, user_id)
        pack_link = generate_pack_link(pack_short_name)
        
        success = await create_pack_with_converted_sticker_fast(
            bot=bot,
            user_id=user_id,
            pack_name=pack_name_with_bot,
            pack_short_name=pack_short_name,
            webm_file_path=webm_file_path
        )
        
        if success:
            user_data = await db_operations.get_user_data()
            new_pack = StickerPack(
                pack_name=pack_name_with_bot,
                pack_short_name=pack_short_name,
                pack_link=pack_link,
                created_at=datetime.now(),
                sticker_count=1
            )
            user_data.add_pack(new_pack)
            await db_operations.save_user_data(user_data)
            
            message_text, keyboard = format_sticker_success_message(pack_link, "🎬")
            await bot.send_message(
                chat_id=data['chat_id'],
                text=message_text,
                reply_to_message_id=data['reply_to_message_id'],
                reply_markup=keyboard
            )
        else:
            await message.answer("❌ Failed to create sticker pack.")
    
    except Exception as e:
        logger.error(f"Error in GIF pack creation: {e}")
        await message.answer("❌ Failed to create sticker pack.")
    finally:
        if webm_file_path and os.path.exists(webm_file_path):
            cleanup_temp_file(webm_file_path)


async def handle_sticker_pack_creation_fast(message: Message, bot: Bot, state: FSMContext, db_operations: DatabaseOperations, pack_name: str, data: dict):
    """Create new pack with sticker"""
    user_id = data.get('user_id')
    
    if not user_id:
        await message.answer("❌ User data lost. Please try /kang again.")
        return
    
    class MinimalSticker:
        def __init__(self, file_id: str, emoji: str, is_video: bool, is_animated: bool = False):
            self.file_id = file_id
            self.emoji = emoji
            self.is_video = is_video
            self.is_animated = is_animated
    
    minimal_sticker = MinimalSticker(
        file_id=data['sticker_file_id'],
        emoji=data.get('sticker_emoji'),
        is_video=data.get('sticker_is_video', False),
        is_animated=data.get('sticker_is_animated', False)
    )
    
    pack_name_with_bot = f"{pack_name} by @{settings.BOT_USERNAME}"
    pack_short_name = generate_pack_short_name(pack_name, user_id)
    pack_link = generate_pack_link(pack_short_name)
    
    success = await create_sticker_pack_fast(
        bot=bot,
        user_id=user_id,
        pack_name=pack_name_with_bot,
        pack_short_name=pack_short_name,
        sticker=minimal_sticker
    )
    
    if success:
        user_data = await db_operations.get_user_data()
        new_pack = StickerPack(
            pack_name=pack_name_with_bot,
            pack_short_name=pack_short_name,
            pack_link=pack_link,
            created_at=datetime.now(),
            sticker_count=1
        )
        user_data.add_pack(new_pack)
        await db_operations.save_user_data(user_data)
        
        sticker_emoji = minimal_sticker.emoji or "🔥"
        message_text, keyboard = format_sticker_success_message(pack_link, sticker_emoji)
        await bot.send_message(
            chat_id=data['chat_id'],
            text=message_text,
            reply_to_message_id=data['reply_to_message_id'],
            reply_markup=keyboard
        )
    else:
        await message.answer("❌ Failed to create sticker pack.")


async def add_converted_sticker_to_pack_fast(bot: Bot, user_id: int, pack_short_name: str, webm_file_path: str) -> bool:
    """Add converted GIF to existing pack"""
    try:
        from aiogram.types import FSInputFile, InputSticker
        
        input_file = FSInputFile(webm_file_path)
        input_sticker = InputSticker(
            sticker=input_file,
            emoji_list=["🎬"],
            format="video"
        )
        
        await bot.add_sticker_to_set(
            user_id=user_id,
            name=pack_short_name,
            sticker=input_sticker
        )
        return True
    except Exception as e:
        logger.error(f"Error adding converted sticker: {e}")
        return False


async def create_pack_with_converted_sticker_fast(bot: Bot, user_id: int, pack_name: str, pack_short_name: str, webm_file_path: str) -> bool:
    """Create new pack with converted GIF"""
    try:
        from aiogram.types import FSInputFile, InputSticker
        
        input_file = FSInputFile(webm_file_path)
        input_sticker = InputSticker(
            sticker=input_file,
            emoji_list=["🎬"],
            format="video"
        )
        
        await bot.create_new_sticker_set(
            user_id=user_id,
            name=pack_short_name,
            title=pack_name,
            stickers=[input_sticker]
        )
        return True
    except Exception as e:
        logger.error(f"Error creating pack with converted sticker: {e}")
        return False
