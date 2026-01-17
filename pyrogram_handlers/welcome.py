import logging
import re
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from pyrogram.enums import ChatMemberStatus, ParseMode

from database_management import (
    get_welcome_settings,
    create_default_welcome_settings,
    update_welcome_status,
    set_custom_welcome,
    delete_custom_welcome
)

logger = logging.getLogger(__name__)

WELCOME_CACHE = {}


def parse_buttons(text: str) -> tuple:
    buttons = []
    button_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
    
    matches = re.findall(button_pattern, text)
    
    for match in matches:
        button_text = match[0].strip()
        button_url = match[1].strip()
        buttons.append({"text": button_text, "url": button_url})
    
    cleaned_text = re.sub(button_pattern, '', text).strip()
    
    return cleaned_text, buttons


def format_welcome_text(text: str, user, chat) -> str:
    from datetime import datetime
    
    user_mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    first_name = user.first_name or "User"
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    username = f"@{user.username}" if user.username else "None"
    
    now = datetime.now()
    current_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%H:%M")
    
    formatted = text.replace("{ID}", str(user.id))
    formatted = formatted.replace("{NAME}", first_name)
    formatted = formatted.replace("{SURNAME}", last_name)
    formatted = formatted.replace("{NAMESURNAME}", full_name)
    formatted = formatted.replace("{DATE}", current_date)
    formatted = formatted.replace("{TIME}", current_time)
    formatted = formatted.replace("{MENTION}", user_mention)
    formatted = formatted.replace("{USERNAME}", username)
    formatted = formatted.replace("{GROUPNAME}", chat.title)
    
    return formatted


def create_button_markup(buttons: list) -> InlineKeyboardMarkup:
    if not buttons:
        return None
    
    keyboard = []
    row = []
    
    for i, btn in enumerate(buttons):
        row.append(InlineKeyboardButton(text=btn['text'], url=btn['url']))
        
        if len(row) == 2 or i == len(buttons) - 1:
            keyboard.append(row)
            row = []
    
    return InlineKeyboardMarkup(keyboard) if keyboard else None


async def is_user_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False


async def is_bot_admin(client: Client, chat_id: int) -> bool:
    try:
        bot = await client.get_me()
        bot_member = await client.get_chat_member(chat_id, bot.id)
        return bot_member.status in [ChatMemberStatus.ADMINISTRATOR]
    except Exception as e:
        logger.error(f"Error checking bot admin status: {e}")
        return False


async def setup_welcome_handlers(client: Client):
    
    @client.on_message(filters.command("welcome") & filters.group)
    async def welcome_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text(
                    "Only admins can use this command!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            command_parts = message.text.split(maxsplit=1)
            
            if len(command_parts) < 2:
                await message.reply_text(
                    "<b>Welcome Command Usage:</b>\n\n"
                    "<code>/welcome on</code> - Enable welcome messages\n"
                    "<code>/welcome off</code> - Disable welcome messages\n\n"
                    "Use <code>/setwelcome</code> to set custom welcome\n\n"
                    "<b>Available Variables:</b>\n"
                    "<code>{ID}</code> - User ID\n"
                    "<code>{NAME}</code> - First name\n"
                    "<code>{SURNAME}</code> - Last name\n"
                    "<code>{NAMESURNAME}</code> - Full name\n"
                    "<code>{DATE}</code> - Current date\n"
                    "<code>{TIME}</code> - Current time\n"
                    "<code>{MENTION}</code> - User mention\n"
                    "<code>{USERNAME}</code> - Username\n"
                    "<code>{GROUPNAME}</code> - Group name",
                    parse_mode=ParseMode.HTML
                )
                return
            
            action = command_parts[1].lower()
            
            if not await is_bot_admin(client, chat_id):
                await message.reply_text(
                    "<b>I need admin rights first!</b>\n\n"
                    "Please promote me as admin with:\n"
                    "Change Group Info permission\n\n"
                    "Then try again!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            if action == "on":
                if settings['welcome']['enabled']:
                    await message.reply_text(
                        "Welcome is already enabled!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                await update_welcome_status(chat_id, True)
                
                settings = await get_welcome_settings(chat_id)
                WELCOME_CACHE[chat_id] = settings['welcome']
                
                if settings['welcome']['custom_set']:
                    await message.reply_text(
                        "<b>Welcome enabled!</b>\n\n"
                        "Custom welcome message will be sent to new members.",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text(
                        "<b>Welcome enabled!</b>\n\n"
                        "Default welcome message will be sent to new members.\n"
                        "Use <code>/setwelcome</code> to set a custom message.",
                        parse_mode=ParseMode.HTML
                    )
            
            elif action == "off":
                if not settings['welcome']['enabled']:
                    await message.reply_text(
                        "Welcome is already disabled!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                await update_welcome_status(chat_id, False)
                
                if chat_id in WELCOME_CACHE:
                    del WELCOME_CACHE[chat_id]
                
                await message.reply_text(
                    "<b>Welcome disabled!</b>\n\n"
                    "New members will not receive welcome messages.",
                    parse_mode=ParseMode.HTML
                )
            
            else:
                await message.reply_text(
                    "<b>Invalid action!</b>\n\n"
                    "Use <code>/welcome on</code> or <code>/welcome off</code>",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in welcome_command: {e}", exc_info=True)
            await message.reply_text(
                "An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.command("setwelcome") & filters.group)
    async def setwelcome_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text(
                    "Only admins can use this command!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            if not await is_bot_admin(client, chat_id):
                await message.reply_text(
                    "<b>I need admin rights first!</b>\n\n"
                    "Please promote me as admin with:\n"
                    "Change Group Info permission\n\n"
                    "Then try again!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            if not message.reply_to_message:
                await message.reply_text(
                    "<b>Please reply to a message!</b>\n\n"
                    "<b>Usage:</b>\n"
                    "1. Send/forward a photo/video/GIF with caption\n"
                    "2. Or send a text message\n"
                    "3. Reply to it with <code>/setwelcome</code>\n\n"
                    "<b>Variables:</b>\n"
                    "<code>{ID}</code> {NAME} {SURNAME} {NAMESURNAME}\n"
                    "<code>{DATE}</code> {TIME} {MENTION} {USERNAME}\n"
                    "<code>{GROUPNAME}</code>\n\n"
                    "<b>Buttons:</b> Use <code>[Text](URL)</code> format",
                    parse_mode=ParseMode.HTML
                )
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            if settings['welcome']['custom_set']:
                await message.reply_text(
                    "<b>Custom welcome already set!</b>\n\n"
                    "First use <code>/delwelcome</code> to remove the existing custom welcome,\n"
                    "then set the new one.\n\n"
                    "This prevents accidental overwrites.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            replied_msg = message.reply_to_message
            
            media_type = None
            media_id = None
            text = None
            buttons = []
            
            if replied_msg.photo:
                media_type = "photo"
                media_id = replied_msg.photo.file_id
                text = replied_msg.caption or ""
            
            elif replied_msg.video:
                media_type = "video"
                media_id = replied_msg.video.file_id
                text = replied_msg.caption or ""
            
            elif replied_msg.animation:
                media_type = "animation"
                media_id = replied_msg.animation.file_id
                text = replied_msg.caption or ""
            
            elif replied_msg.text:
                text = replied_msg.text
            
            else:
                await message.reply_text(
                    "<b>Unsupported message type!</b>\n\n"
                    "Supported: Photo, Video, GIF, Text",
                    parse_mode=ParseMode.HTML
                )
                return
            
            if text:
                text, buttons = parse_buttons(text)
            
            if not text or len(text.strip()) == 0:
                text = "Hey {MENTION}!\nWelcome to {GROUPNAME}!"
            
            success = await set_custom_welcome(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                buttons=buttons
            )
            
            if success:
                await update_welcome_status(chat_id, True)
                
                settings = await get_welcome_settings(chat_id)
                WELCOME_CACHE[chat_id] = settings['welcome']
                
                response = "<b>Custom welcome set and enabled!</b>\n\n"
                
                if media_type:
                    response += f"<b>Type:</b> {media_type.title()}\n"
                
                response += f"<b>Text:</b> {text[:50]}...\n" if len(text) > 50 else f"<b>Text:</b> {text}\n"
                
                if buttons:
                    response += f"<b>Buttons:</b> {len(buttons)}\n"
                
                response += "\nWelcome is now ON!"
                
                await message.reply_text(response, parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(
                    "Failed to set custom welcome. Please try again.",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in setwelcome_command: {e}", exc_info=True)
            await message.reply_text(
                "An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.command("delwelcome") & filters.group)
    async def delwelcome_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text(
                    "Only admins can use this command!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings or not settings['welcome']['custom_set']:
                await message.reply_text(
                    "<b>No custom welcome message is set!</b>\n\n"
                    "You can use <code>/setwelcome</code> to set one.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            success = await delete_custom_welcome(chat_id)
            
            if success:
                if chat_id in WELCOME_CACHE:
                    del WELCOME_CACHE[chat_id]
                    logger.info(f"Cleared welcome cache for chat {chat_id}")
                
                await message.reply_text(
                    "<b>Custom welcome deleted!</b>\n\n"
                    "Welcome is now <b>disabled</b>.\n\n"
                    "<b>Options:</b>\n"
                    "Use <code>/setwelcome</code> to set a new custom welcome\n"
                    "Use <code>/welcome on</code> to enable default welcome",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    "Failed to delete custom welcome.",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in delwelcome_command: {e}", exc_info=True)
            await message.reply_text(
                "An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_chat_member_updated(filters.group)
    async def welcome_new_member(client: Client, member_update: ChatMemberUpdated):
        try:
            if (
                not member_update.new_chat_member
                or member_update.new_chat_member.status in {"banned", "left", "restricted"}
                or member_update.old_chat_member
            ):
                return
            
            user = member_update.new_chat_member.user if member_update.new_chat_member else member_update.from_user
            chat_id = member_update.chat.id
            
            if user.is_bot:
                return
            
            if chat_id in WELCOME_CACHE:
                welcome_config = WELCOME_CACHE[chat_id]
                
                if not welcome_config.get('enabled'):
                    return
                
                logger.info(f"Using cached welcome for chat {chat_id}")
            
            else:
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                if not settings or not settings.get('welcome', {}).get('enabled'):
                    return
                
                welcome_config = settings['welcome']
                
                WELCOME_CACHE[chat_id] = welcome_config
                
                logger.info(f"Cached welcome for chat {chat_id}")
            
            if welcome_config.get('custom_set') and welcome_config.get('text'):
                text = welcome_config['text']
            else:
                text = welcome_config.get('default_text', 'Hey {MENTION}!\nWelcome to {GROUPNAME}!')
            
            formatted_text = format_welcome_text(text, user, member_update.chat)
            
            reply_markup = None
            if welcome_config.get('buttons'):
                reply_markup = create_button_markup(welcome_config['buttons'])
            
            try:
                if welcome_config.get('media_type') and welcome_config.get('media_id'):
                    media_type = welcome_config['media_type']
                    media_id = welcome_config['media_id']
                    
                    if media_type == "photo":
                        await client.send_photo(
                            chat_id=chat_id,
                            photo=media_id,
                            caption=formatted_text,
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.HTML
                        )
                    elif media_type == "video":
                        await client.send_video(
                            chat_id=chat_id,
                            video=media_id,
                            caption=formatted_text,
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.HTML
                        )
                    elif media_type == "animation":
                        await client.send_animation(
                            chat_id=chat_id,
                            animation=media_id,
                            caption=formatted_text,
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.HTML
                        )
                else:
                    await client.send_message(
                        chat_id=chat_id,
                        text=formatted_text,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML
                    )
                
                logger.info(f"Welcome sent to {user.id} in chat {chat_id}")
                
            except Exception as send_error:
                logger.error(f"Send failed: {send_error}", exc_info=True)
        
        except Exception as e:
            logger.error(f"Critical error in welcome handler: {e}", exc_info=True)
    
    logger.info("Welcome handlers setup complete")
