import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import get_user_language, set_user_language
from utils.language import get_text

logger = logging.getLogger(__name__)
router = Router()


def get_language_selection_keyboard():
    """Build language selection keyboard with 3 languages"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="🇬🇧 English", callback_data="set_lang:en")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang:rus")
    builder.button(text="🇲🇲 မြန်မာ", callback_data="set_lang:bur")
    
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("lang"), F.chat.type == "private")
async def cmd_lang(message: Message):
    """Handle /lang command - show language selection"""
    user_id = message.from_user.id
    current_lang = await get_user_language(user_id)
    lang_select_msg = await get_text(user_id, "LANG_SELECT_MESSAGE")
    
    if lang_select_msg is None:
        lang_select_msg = (
            "🌐 <b>Choose Your Language</b>\n\n"
            "Select your preferred language:"
        )
    
    await message.answer(lang_select_msg, reply_markup=get_language_selection_keyboard())
    logger.info(f"User {user_id} opened language selection (current: {current_lang})")


@router.callback_query(F.data.startswith("set_lang:"))
async def set_language_callback(callback: CallbackQuery):
    """Handle language selection"""
    await callback.answer()
    
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    language = callback.data.split(":")[1]
    
    if language not in ["en", "rus", "bur"]:
        await callback.answer("Invalid language!", show_alert=True)
        return
    
    success = await set_user_language(user_id, language)
    
    if not success:
        await callback.answer("Error saving language!", show_alert=True)
        return
    
    logger.info(f"User {user_id} changed language to {language}")
    
    confirmation_msg = await get_text(user_id, "LANG_CHANGED")
    
    if confirmation_msg is None:
        fallback_messages = {
            "en": "✅ Language changed to English",
            "rus": "✅ Язык изменен на русский",
            "bur": "✅ ဘာသာစကားကို မြန်မာသို့ ပြောင်းလဲပြီးပါပြီ"
        }
        confirmation_msg = fallback_messages.get(language, "✅ Language changed")
    
    from handlers.keyboard_utils import get_main_menu_keyboard
    from utils.html_utils import escape_html
    
    start_text = await get_text(
        user_id,
        "START_MESSAGE_WITH_IMAGE",
        uid=user_id,
        first_name=escape_html(callback.from_user.first_name)
    )
    
    if start_text is None:
        start_text = f"────「  ꜱᴛɪᴄᴋᴇʀ ᴋᴀɴɢ 」────\n✦ ʜᴇʏ {escape_html(callback.from_user.first_name)}...\n╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\nɪ ᴀᴍ ʏᴏᴜʀ ꜱᴛɪᴄᴋᴇʀ ᴄᴏᴍᴘᴀɴɪᴏɴ 💫\nᴡɪᴛʜ ᴍᴇ ʏᴏᴜ ᴄᴀɴ:\n➤ ᴋᴀɴɢ ꜱᴛɪᴄᴋᴇʀꜱ ɪɴ ᴏɴᴇ ᴛᴀᴘ\n➤ ᴍᴀᴋᴇ ʏᴏᴜʀ ᴏᴡɴ ᴘᴀᴄᴋꜱ\n➤ ᴍᴀɴᴀɢᴇ & ꜱʜᴀʀᴇ ᴇᴀꜱɪʟʏ\n╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\nᴘʀᴇꜱꜱ ᴛʜᴇ ʙᴜᴛᴛᴏɴꜱ ʙᴇʟᴏᴡ ᴛᴏ ꜱᴛᴀʀᴛ"
    
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete language selection message: {e}")
    
    try:
        full_message = f"{confirmation_msg}\n\n{start_text}"
        keyboard = await get_main_menu_keyboard(user_id)
        
        await callback.bot.send_message(
            chat_id=chat_id,
            text=full_message,
            reply_markup=keyboard
        )
        
        logger.info(f"Sent start message to user {user_id} in {language}")
        
    except Exception as e:
        logger.error(f"Error sending start message: {e}", exc_info=True)
        
        try:
            await callback.message.edit_text(
                f"{confirmation_msg}\n\n{start_text}",
                reply_markup=await get_main_menu_keyboard(user_id)
            )
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}", exc_info=True)


async def show_language_selection_for_new_user(message: Message):
    """Show language selection for new users during /start"""
    user_id = message.from_user.id
    lang_select_msg = await get_text(user_id, "LANG_SELECT_MESSAGE")
    
    if lang_select_msg is None:
        lang_select_msg = (
            "🌐 <b>Choose Your Language</b>\n\n"
            "Select your preferred language to continue:"
        )
    
    await message.answer(lang_select_msg, reply_markup=get_language_selection_keyboard())
    logger.info(f"Showed language selection to new user {user_id}")
