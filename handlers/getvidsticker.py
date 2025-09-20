from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from utils import extract_sticker_from_message, download_sticker, cleanup_temp_file, convert_webm_to_mp4
import logging

logger = logging.getLogger(__name__)

# Create router for getvidsticker command
getvidsticker_router = Router()


@getvidsticker_router.message(Command("getvidsticker"))
async def getvidsticker_command(message: Message, bot: Bot):
    """
    Handle /getvidsticker command - reply to video sticker to download as MP4
    Works in both private chats and groups
    """
    
    # Check if replying to a sticker
    sticker = extract_sticker_from_message(message)
    if not sticker:
        await message.answer(
            "🎬 Please reply to a video sticker with /getvidsticker to download its MP4 file",
            reply_to_message_id=message.message_id
        )
        return
    
    # Check if it's a video sticker
    if not sticker.is_video:
        sticker_type = "animated" if sticker.is_animated else "static"
        await message.answer(
            f"❌ This is a {sticker_type} sticker, not a video sticker. Use /getsticker for static stickers.",
            reply_to_message_id=message.message_id
        )
        return
    
    try:
        # Send "processing" message
        processing_msg = await message.answer(
            "⏳ Downloading and converting video sticker to MP4...",
            reply_to_message_id=message.message_id
        )
        
        # Download sticker
        sticker_file_path = await download_sticker(bot, sticker)
        if not sticker_file_path:
            await processing_msg.edit_text("❌ Failed to download video sticker. Please try again.")
            return
        
        try:
            # Convert WebM to MP4
            mp4_file_path = await convert_webm_to_mp4(sticker_file_path)
            if not mp4_file_path:
                await processing_msg.edit_text("❌ Failed to convert video sticker to MP4. Please try again.")
                return
            
            try:
                # Upload MP4 file
                mp4_file = FSInputFile(mp4_file_path, filename=f"video_sticker_{sticker.file_unique_id}.mp4")
                
                await message.answer_video(
                    video=mp4_file,
                    caption=f"🎬 **Video Sticker as MP4**\n📁 File ID: `{sticker.file_id}`",
                    reply_to_message_id=message.message_id,
                    parse_mode="Markdown"
                )
                
                # Delete processing message
                await processing_msg.delete()
                
                logger.info(f"Sent MP4 file for user {message.from_user.id}, sticker: {sticker.file_id}")
                
            finally:
                # Clean up MP4 file
                cleanup_temp_file(mp4_file_path)
        
        finally:
            # Clean up original sticker file
            cleanup_temp_file(sticker_file_path)
    
    except Exception as e:
        logger.error(f"Error in getvidsticker command for user {message.from_user.id}: {e}")
        try:
            await processing_msg.edit_text("❌ Something went wrong while processing the video sticker. Please try again.")
        except:
            await message.answer(
                "❌ Something went wrong while processing the video sticker. Please try again.",
                reply_to_message_id=message.message_id
              )
