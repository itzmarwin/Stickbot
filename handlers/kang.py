from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from utils import (
    is_private_chat, is_group_chat, extract_sticker_from_message,
    is_sticker_supported, validate_pack_name, generate_pack_short_name,
    generate_pack_link, format_pack_creation_message, format_sticker_added_message,
    create_sticker_pack, add_sticker_to_pack
)
from middlewares import DatabaseOperations
from database import StickerPack
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Create router for kang command
kang_router = Router()


class KangStates(StatesGroup):
    waiting_for_pack_name = State()


@kang_router.message(Command("kang"))
async def kang_command(message: Message, bot: Bot, state: FSMContext, db_operations: DatabaseOperations):
    """
    Handle /kang command - only works in groups when replying to a sticker
    """
    
    # Check if command is used in private chat
    if is_private_chat(message):
        await message.answer(settings.KANG_PRIVATE_CHAT_MESSAGE)
        return
    
    # Check if command is used in group
    if not is_group_chat(message):
        return
    
    # Check if replying to a sticker
    sticker = extract_sticker_from_message(message)
    if not sticker:
        await message.answer(
            "⚠️ Please reply to a sticker with /kang to add it to your pack",
            reply_to_message_id=message.message_id
        )
        return
    
    # Check if sticker is supported
    if not is_sticker_supported(sticker):
        await message.answer(
            "❌ Sorry, only static image and video stickers are supported (no animated stickers)",
            reply_to_message_id=message.message_id
        )
        return
    
    try:
        # Get user data
        user_data = await db_operations.get_or_create_user_data()
        
        # Check if user has existing packs
        if user_data.has_packs():
            # User has packs, add to the most recent one
            latest_pack = user_data.packs[-1]  # Get latest pack
            
            # Add sticker to existing pack
            success = await add_sticker_to_pack(
                bot=bot,
                user_id=message.from_user.id,
                pack_short_name=latest_pack.pack_short_name,
                sticker=sticker
            )
            
            if success:
                await message.answer(
                    format_sticker_added_message(latest_pack.pack_name, latest_pack.pack_link),
                    reply_to_message_id=message.message_id,
                    parse_mode="Markdown"
                )
                logger.info(f"Added sticker to pack {latest_pack.pack_short_name} for user {message.from_user.id}")
            else:
                await message.answer(
                    "❌ Failed to add sticker to pack. Please try again later.",
                    reply_to_message_id=message.message_id
                )
        
        else:
            # User doesn't have packs, ask for pack name
            await state.set_state(KangStates.waiting_for_pack_name)
            
            # Store sticker data in FSM context
            await state.update_data(
                sticker_file_id=sticker.file_id,
                sticker_emoji=sticker.emoji,
                sticker_is_video=sticker.is_video,
                sticker_is_animated=sticker.is_animated,
                chat_id=message.chat.id,
                reply_to_message_id=message.message_id
            )
            
            await message.answer(
                "🆕 You don't have any sticker packs yet!\n\n"
                "Please send me a name for your new sticker pack:",
                reply_to_message_id=message.message_id
            )
    
    except Exception as e:
        logger.error(f"Error in kang command for user {message.from_user.id}: {e}")
        await message.answer(
            "❌ Something went wrong. Please try again later.",
            reply_to_message_id=message.message_id
        )


@kang_router.message(KangStates.waiting_for_pack_name)
async def process_pack_name(message: Message, bot: Bot, state: FSMContext, db_operations: DatabaseOperations):
    """
    Process the pack name provided by user and create the sticker pack
    """
    
    # Only accept text messages for pack name
    if not message.text:
        await message.answer("Please send a text message with your pack name.")
        return
    
    pack_name = message.text.strip()
    
    # Validate pack name
    is_valid, error_message = validate_pack_name(pack_name)
    if not is_valid:
        await message.answer(f"❌ {error_message}\n\nPlease send a valid pack name:")
        return
    
    try:
        # Get FSM data
        data = await state.get_data()
        
        # Check if required data exists
        if 'sticker_file_id' not in data:
            await message.answer("❌ Session expired. Please try /kang again.")
            await state.clear()
            return
        
        # Create a minimal sticker object for our operations
        class MinimalSticker:
            def __init__(self, file_id: str, emoji: str, is_video: bool):
                self.file_id = file_id
                self.emoji = emoji
                self.is_video = is_video
                self.is_animated = False
        
        minimal_sticker = MinimalSticker(
            file_id=data['sticker_file_id'],
            emoji=data.get('sticker_emoji'),
            is_video=data.get('sticker_is_video', False)
        )
        
        # Generate pack details
        pack_short_name = generate_pack_short_name(pack_name, message.from_user.id)
        pack_link = generate_pack_link(pack_short_name)
        
        # Create sticker pack
        success = await create_sticker_pack(
            bot=bot,
            user_id=message.from_user.id,
            pack_name=pack_name,
            pack_short_name=pack_short_name,
            first_sticker=minimal_sticker
        )
        
        if success:
            # Save pack info to database
            user_data = await db_operations.get_or_create_user_data()
            
            new_pack = StickerPack(
                pack_name=pack_name,
                pack_short_name=pack_short_name,
                pack_link=pack_link,
                created_at=datetime.now()
            )
            
            user_data.add_pack(new_pack)
            await db_operations.save_user_data(user_data)
            
            # Send success message to the original chat
            try:
                await bot.send_message(
                    chat_id=data['chat_id'],
                    text=format_pack_creation_message(pack_name, pack_link),
                    reply_to_message_id=data['reply_to_message_id'],
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send message to original chat: {e}")
                # Send to current chat as fallback
                await message.answer(
                    format_pack_creation_message(pack_name, pack_link),
                    parse_mode="Markdown"
                )
            
            # Also confirm in current chat (private)
            await message.answer("✅ Pack created successfully!")
            
            logger.info(f"Created pack {pack_short_name} for user {message.from_user.id}")
        
        else:
            await message.answer(
                "❌ Failed to create sticker pack. Please try again later."
            )
    
    except Exception as e:
        logger.error(f"Error creating pack for user {message.from_user.id}: {e}")
        await message.answer(
            "❌ Something went wrong while creating the pack. Please try again later."
        )
    
    finally:
        # Clear FSM state
        await state.clear()
