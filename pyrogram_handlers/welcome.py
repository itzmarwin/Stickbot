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
    cleaned_text = text
    button_rows = []
    
    lines = text.split('\n')
    button_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
    
    total_buttons = 0
    for line in lines:
        if '|' in line:
            parts = line.split('|')
            row_buttons = []
            
            for part in parts:
                matches = re.findall(button_pattern, part.strip())
                for match in matches:
                    if total_buttons >= 6:
                        break
                    row_buttons.append({"text": match[0].strip(), "url": match[1].strip()})
                    total_buttons += 1
                
                if len(row_buttons) > 2:
                    return None, None, "Maximum 2 buttons per row allowed!"
            
            if row_buttons:
                button_rows.append(row_buttons)
        else:
            matches = re.findall(button_pattern, line)
            for match in matches:
                if total_buttons >= 6:
                    break
                button_rows.append([{"text": match[0].strip(), "url": match[1].strip()}])
                total_buttons += 1
    
    if total_buttons > 6:
        return None, None, "Maximum 6 buttons allowed!"
    
    cleaned_text = re.sub(button_pattern, '', text)
    cleaned_text = re.sub(r'\|', '', cleaned_text)
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text, button_rows, None


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


def create_button_markup(button_rows: list) -> InlineKeyboardMarkup:
    if not button_rows:
        return None
    
    keyboard = []
    
    for row in button_rows:
        keyboard_row = []
        for btn in row:
            keyboard_row.append(InlineKeyboardButton(text=btn['text'], url=btn['url']))
        keyboard.append(keyboard_row)
    
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
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                is_enabled = settings.get('welcome', {}).get('enabled', False)
                status_text = "enabled" if is_enabled else "disabled"
                
                status_msg = await message.reply_text(
                    f"<b>Welcome messages are currently {status_text}.</b>",
                    parse_mode=ParseMode.HTML
                )
                
                if is_enabled:
                    welcome_config = settings['welcome']
                    
                    if welcome_config.get('custom_set') and welcome_config.get('text'):
                        text = welcome_config['text']
                    else:
                        text = welcome_config.get('default_text', 'Hey {MENTION}!\nWelcome to {GROUPNAME}!')
                    
                    reply_markup = None
                    if welcome_config.get('buttons'):
                        reply_markup = create_button_markup(welcome_config['buttons'])
                    
                    if welcome_config.get('media_type') and welcome_config.get('media_id'):
                        media_type = welcome_config['media_type']
                        media_id = welcome_config['media_id']
                        
                        if media_type == "photo":
                            await message.reply_photo(
                                photo=media_id,
                                caption=text,
                                reply_markup=reply_markup
                            )
                        elif media_type == "video":
                            await message.reply_video(
                                video=media_id,
                                caption=text,
                                reply_markup=reply_markup
                            )
                        elif media_type == "animation":
                            await message.reply_animation(
                                animation=media_id,
                                caption=text,
                                reply_markup=reply_markup
                            )
                    else:
                        await message.reply_text(
                            text=text,
                            reply_markup=reply_markup
                        )
                
                return
            
            action = command_parts[1].lower()
            
            if not await is_bot_admin(client, chat_id):
                await message.reply_text(
                    "<b>Please promote the bot to admin to enable welcome messages.</b>",
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
                    "<b>Use <code>/welcome on</code> or <code>/welcome off</code></b>",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in welcome_command: {e}", exc_info=True)
            await message.reply_text(
                "Please try again shortly. If the problem continues, contact our support group.",
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
                    "<b>Please promote the bot to admin to enable welcome messages.</b>",
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
                    "<b>Buttons Format:</b>\n"
                    "<code>[Button](URL)</code> - Single button\n"
                    "<code>[Btn1](URL) | [Btn2](URL)</code> - Two buttons in one row\n"
                    "Max 2 buttons per row, Max 6 buttons total",
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
            button_rows = []
            
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
                    "<b>The selected message type is not supported.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            if text:
                text, button_rows, error = parse_buttons(text)
                if error:
                    await message.reply_text(
                        f"<b>Button Error:</b> {error}\n\n"
                        "<b>Rules:</b>\n"
                        "• Max 2 buttons per row\n"
                        "• Max 6 buttons total\n"
                        "• Use | to put buttons in same row\n\n"
                        "<b>Examples:</b>\n"
                        "<code>[Btn1](url) | [Btn2](url)</code>\n"
                        "<code>[Btn3](url)</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return
            
            if not text or len(text.strip()) == 0:
                text = "Hey {MENTION}!\nWelcome to {GROUPNAME}!"
            
            success = await set_custom_welcome(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                buttons=button_rows
            )
            
            if success:
                await update_welcome_status(chat_id, True)
                
                settings = await get_welcome_settings(chat_id)
                WELCOME_CACHE[chat_id] = settings['welcome']
                
                response = "<b>Welcome message has been set successfully!</b>\n\nWelcome is now <b>enabled</b>"
                
                await message.reply_text(response, parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(
                    "Unable to set the welcome message at this time. Please try again later.",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in setwelcome_command: {e}", exc_info=True)
            await message.reply_text(
                "Please try again later or contact the support group if the issue persists.",
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
                    "<b>No welcome message is set.</b>\n\n"
                    "Set it using <code>/setwelcome</code>.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            success = await delete_custom_welcome(chat_id)
            
            if success:
                if chat_id in WELCOME_CACHE:
                    del WELCOME_CACHE[chat_id]
                    logger.info(f"Cleared welcome cache for chat {chat_id}")
                
                await message.reply_text(
                    "<b>Welcome message deleted.</b>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    "Unable to delete the welcome message.",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in delwelcome_command: {e}", exc_info=True)
            await message.reply_text(
                "Please try again later. If the problem continues, contact the support group.",
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
