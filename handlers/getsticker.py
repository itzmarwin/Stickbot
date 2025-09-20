from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from utils import extract_sticker_from_message, download_sticker, cleanup_temp_file, convert_sticker_to_png
import logging

logger = logging.getLogger(__name__)

# Create router for getsticker command
getsticker_router = Router()


@getsticker_router.message(Command("getsticker"))
async def getsticker_command(message: Message, bot: Bot):
    """
    Handle /getsticker command - reply to any sticker to download as PNG
    Works in both private chats and groups
    """
    
    # Check if replying to a sticker
    sticker = extract_sticker_from_message(message)
    if not sticker:
        await message.answer(
            "🖼 Please reply to a sticker with /getsticker to download its PNG file",
            reply_to_message_id=message.message_id
        )
        return
    
    # Check if it's an animated sticker
    if sticker.is_animated:
        await message.answer(
            "❌ Animated stickers (.tgs) cannot be converted to PNG. Try /stickerid to get file information instead.",
            reply_to_message_id=message.message_id
        )
        return
    
    # Check if it's a video sticker
    if sticker.is_video:
        await message.answer(
            "❌ Video stickers cannot be converted to PNG. Use /getvidsticker for video stickers instead.",
            reply_to_message_id=message.message_id
        )
        return
    
    try:
        # Send "processing" message
        processing_msg = await message.answer(
            "⏳ Downloading and converting sticker to PNG...",
            reply_to_message_id=message.message_id
        )
        
        # Download sticker
        sticker_file_path = await download_sticker(bot, sticker)
        if not sticker_file_path:
            await processing_msg.edit_text("❌ Failed to download sticker. Please try again.")
            return
        
        try:
            # Convert to PNG
            png_file_path = await convert_sticker_to_png(sticker_file_path)
            if not png_file_path:
                await processing_msg.edit_text("❌ Failed to convert sticker to PNG. Please try again.")
                return
            
            try:
                # Upload PNG file
                png_file = FSInputFile(png_file_path, filename=f"sticker_{sticker.file_unique_id}.png")
                
                await message.answer_document(
                    document=png_file,
                    caption=f"🖼 **Sticker as PNG**\n📁 File ID: `{sticker.file_id}`",
                    reply_to_message_id=message.message_id,
                    parse_mode="Markdown"
                )
                
                # Delete processing message
                await processing_msg.delete()
                
                logger.info(f"Sent PNG file for user {message.from_user.id}, sticker: {sticker.file_id}")
                
            finally:
                # Clean up PNG file
                cleanup_temp_file(png_file_path)
        
        finally:
            # Clean up original sticker file
            cleanup_temp_file(sticker_file_path)
    
    except Exception as e:
        logger.error(f"Error in getsticker command for user {message.from_user.id}: {e}")
        try:
            await processing_msg.edit_text("❌ Something went wrong while processing the sticker. Please try again.")
        except:
            await message.answer(
                "❌ Something went wrong while processing the sticker. Please try again.",
                reply_to_message_id=message.message_id
            )
