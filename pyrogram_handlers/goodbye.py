"""
Goodbye System Handler
Handles goodbye messages with custom media, text, and buttons
"""
import logging
import re
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus, ParseMode

from database_management import (
    get_welcome_settings,
    create_default_welcome_settings,
    update_goodbye_status,
    set_custom_goodbye,
    delete_custom_goodbye
)

logger = logging.getLogger(__name__)


def parse_buttons(text: str) -> tuple:
    """
    Parse buttons from text
    Format: [Button Text](https://url.com)
    
    Returns:
        (cleaned_text, buttons_list)
    """
    buttons = []
    button_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
    
    matches = re.findall(button_pattern, text)
    
    for match in matches:
        button_text = match[0].strip()
        button_url = match[1].strip()
        buttons.append({"text": button_text, "url": button_url})
    
    # Remove button markdown from text
    cleaned_text = re.sub(button_pattern, '', text).strip()
    
    return cleaned_text, buttons


def format_goodbye_text(text: str, user, chat) -> str:
    """
    Replace variables in goodbye text
    
    Variables:
        {ID} - User ID
        {NAME} - User first name
        {SURNAME} - User last name
        {NAMESURNAME} - Full name
        {DATE} - Current date (DD-MM-YYYY)
        {TIME} - Current time (HH:MM)
        {MENTION} - User mention (clickable)
        {USERNAME} - Username with @
        {GROUPNAME} - Group name
        {RULES} - Group rules (placeholder)
    """
    from datetime import datetime
    
    # User info
    user_mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    first_name = user.first_name or "User"
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    username = f"@{user.username}" if user.username else "No username"
    
    # Date and time
    now = datetime.now()
    current_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%H:%M")
    
    # Replace all variables
    formatted = text.replace("{ID}", str(user.id))
    formatted = formatted.replace("{NAME}", first_name)
    formatted = formatted.replace("{SURNAME}", last_name)
    formatted = formatted.replace("{NAMESURNAME}", full_name)
    formatted = formatted.replace("{DATE}", current_date)
    formatted = formatted.replace("{TIME}", current_time)
    formatted = formatted.replace("{MENTION}", user_mention)
    formatted = formatted.replace("{USERNAME}", username)
    formatted = formatted.replace("{GROUPNAME}", chat.title)
    formatted = formatted.replace("{RULES}", "Check pinned message for rules")
    
    return formatted


def create_button_markup(buttons: list) -> InlineKeyboardMarkup:
    """
    Create inline keyboard markup from button list
    
    Args:
        buttons: List of dicts with 'text' and 'url'
        
    Returns:
        InlineKeyboardMarkup or None
    """
    if not buttons:
        return None
    
    keyboard = []
    row = []
    
    for i, btn in enumerate(buttons):
        row.append(InlineKeyboardButton(text=btn['text'], url=btn['url']))
        
        # 2 buttons per row
        if len(row) == 2 or i == len(buttons) - 1:
            keyboard.append(row)
            row = []
    
    return InlineKeyboardMarkup(keyboard) if keyboard else None


async def is_user_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """
    Check if user is admin in chat
    """
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False


async def setup_goodbye_handlers(client: Client):
    """Setup goodbye command handlers"""
    
    @client.on_message(filters.command("goodbye") & filters.group)
    async def goodbye_command(client: Client, message: Message):
        """
        Handle /goodbye on and /goodbye off commands
        """
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            # Check admin
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text(
                    "❌ <b>Only admins can use this command!</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Parse command
            command_parts = message.text.split(maxsplit=1)
            
            if len(command_parts) < 2:
                await message.reply_text(
                    "ℹ️ <b>Goodbye Command Usage:</b>\n\n"
                    "<code>/goodbye on</code> - Enable goodbye messages\n"
                    "<code>/goodbye off</code> - Disable goodbye messages\n\n"
                    "💡 Use <code>/setgoodbye</code> to set custom goodbye\n\n"
                    "<b>Available Variables:</b>\n"
                    "<code>{ID}</code> - User ID\n"
                    "<code>{NAME}</code> - First name\n"
                    "<code>{SURNAME}</code> - Last name\n"
                    "<code>{NAMESURNAME}</code> - Full name\n"
                    "<code>{DATE}</code> - Current date\n"
                    "<code>{TIME}</code> - Current time\n"
                    "<code>{MENTION}</code> - User mention\n"
                    "<code>{USERNAME}</code> - Username\n"
                    "<code>{GROUPNAME}</code> - Group name\n"
                    "<code>{RULES}</code> - Group rules",
                    parse_mode=ParseMode.HTML
                )
                return
            
            action = command_parts[1].lower()
            
            # Get current settings
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                # Create default settings
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            # Handle /goodbye on
            if action == "on":
                if settings['goodbye']['enabled']:
                    await message.reply_text(
                        "✅ <b>Goodbye is already enabled!</b>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                # Enable goodbye
                await update_goodbye_status(chat_id, True)
                
                if settings['goodbye']['custom_set']:
                    await message.reply_text(
                        "✅ <b>Goodbye enabled!</b>\n\n"
                        "Custom goodbye message will be sent when members leave.",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text(
                        "✅ <b>Goodbye enabled!</b>\n\n"
                        "Default goodbye message will be sent when members leave.\n"
                        "Use <code>/setgoodbye</code> to set a custom message.",
                        parse_mode=ParseMode.HTML
                    )
            
            # Handle /goodbye off
            elif action == "off":
                if not settings['goodbye']['enabled']:
                    await message.reply_text(
                        "ℹ️ <b>Goodbye is already disabled!</b>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                # Disable goodbye
                await update_goodbye_status(chat_id, False)
                
                await message.reply_text(
                    "❌ <b>Goodbye disabled!</b>\n\n"
                    "Members leaving will not receive goodbye messages.",
                    parse_mode=ParseMode.HTML
                )
            
            else:
                await message.reply_text(
                    "⚠️ <b>Invalid action!</b>\n\n"
                    "Use <code>/goodbye on</code> or <code>/goodbye off</code>",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in goodbye_command: {e}", exc_info=True)
            await message.reply_text(
                "❌ An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.command("setgoodbye") & filters.group)
    async def setgoodbye_command(client: Client, message: Message):
        """
        Handle /setgoodbye command
        Must be used as reply to media or text
        """
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            # Check admin
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text(
                    "❌ <b>Only admins can use this command!</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Must be reply
            if not message.reply_to_message:
                await message.reply_text(
                    "⚠️ <b>Please reply to a message!</b>\n\n"
                    "<b>Usage:</b>\n"
                    "1. Send/forward a photo/video/GIF with caption\n"
                    "2. Or send a text message\n"
                    "3. Reply to it with <code>/setgoodbye</code>\n\n"
                    "<b>Variables:</b>\n"
                    "<code>{ID}</code> {NAME} {SURNAME} {NAMESURNAME}\n"
                    "<code>{DATE}</code> {TIME} {MENTION} {USERNAME}\n"
                    "<code>{GROUPNAME}</code> {RULES}\n\n"
                    "<b>Buttons:</b> Use <code>[Text](URL)</code> format",
                    parse_mode=ParseMode.HTML
                )
                return
            
            replied_msg = message.reply_to_message
            
            # Get current settings
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            # Check if goodbye already ON with custom
            if settings['goodbye']['enabled'] and settings['goodbye']['custom_set']:
                await message.reply_text(
                    "⚠️ <b>Goodbye is already ON with a custom message!</b>\n\n"
                    "First use <code>/delgoodbye</code> to remove it,\n"
                    "then set the new goodbye message.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Extract data from replied message
            media_type = None
            media_id = None
            text = None
            buttons = []
            
            # Check for photo
            if replied_msg.photo:
                media_type = "photo"
                media_id = replied_msg.photo.file_id
                text = replied_msg.caption or ""
            
            # Check for video
            elif replied_msg.video:
                media_type = "video"
                media_id = replied_msg.video.file_id
                text = replied_msg.caption or ""
            
            # Check for animation (GIF)
            elif replied_msg.animation:
                media_type = "animation"
                media_id = replied_msg.animation.file_id
                text = replied_msg.caption or ""
            
            # Text only
            elif replied_msg.text:
                text = replied_msg.text
            
            else:
                await message.reply_text(
                    "❌ <b>Unsupported message type!</b>\n\n"
                    "Supported: Photo, Video, GIF, Text",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Parse buttons from text
            if text:
                text, buttons = parse_buttons(text)
            
            if not text or len(text.strip()) == 0:
                text = "Goodbye {NAME}!"
            
            # Save custom goodbye
            success = await set_custom_goodbye(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                buttons=buttons
            )
            
            if success:
                response = "✅ <b>Custom goodbye set!</b>\n\n"
                
                if media_type:
                    response += f"<b>Type:</b> {media_type.title()}\n"
                
                response += f"<b>Text:</b> {text[:50]}...\n" if len(text) > 50 else f"<b>Text:</b> {text}\n"
                
                if buttons:
                    response += f"<b>Buttons:</b> {len(buttons)}\n"
                
                response += "\nUse <code>/goodbye on</code> to enable."
                
                await message.reply_text(response, parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(
                    "❌ Failed to set custom goodbye. Please try again.",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in setgoodbye_command: {e}", exc_info=True)
            await message.reply_text(
                "❌ An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.command("delgoodbye") & filters.group)
    async def delgoodbye_command(client: Client, message: Message):
        """
        Handle /delgoodbye command
        Deletes custom goodbye and disables goodbye
        """
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            # Check admin
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text(
                    "❌ <b>Only admins can use this command!</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Get settings
            settings = await get_welcome_settings(chat_id)
            
            if not settings or not settings['goodbye']['custom_set']:
                await message.reply_text(
                    "ℹ️ <b>No custom goodbye message is set!</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Delete custom goodbye
            success = await delete_custom_goodbye(chat_id)
            
            if success:
                await message.reply_text(
                    "✅ <b>Custom goodbye deleted!</b>\n\n"
                    "Goodbye is now disabled.\n"
                    "Use <code>/setgoodbye</code> to set a new one.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    "❌ Failed to delete custom goodbye.",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in delgoodbye_command: {e}", exc_info=True)
            await message.reply_text(
                "❌ An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.left_chat_member & filters.group)
    async def goodbye_left_member(client: Client, message: Message):
        """
        Send goodbye message when member leaves
        """
        try:
            chat_id = message.chat.id
            left_member = message.left_chat_member
            
            # Skip if bot left
            if left_member.is_bot:
                return
            
            # Get settings
            settings = await get_welcome_settings(chat_id)
            
            # Check if goodbye enabled
            if not settings or not settings['goodbye']['enabled']:
                return
            
            # Get goodbye config
            goodbye_config = settings['goodbye']
            
            # Determine text to use
            if goodbye_config['custom_set'] and goodbye_config['text']:
                text = goodbye_config['text']
            else:
                text = goodbye_config['default_text']
            
            # Format text with variables
            formatted_text = format_goodbye_text(text, left_member, message.chat)
            
            # Create buttons
            reply_markup = None
            if goodbye_config['buttons']:
                reply_markup = create_button_markup(goodbye_config['buttons'])
            
            # Send goodbye message
            if goodbye_config['media_type'] and goodbye_config['media_id']:
                # Send with media
                media_type = goodbye_config['media_type']
                media_id = goodbye_config['media_id']
                
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
                # Text only
                await client.send_message(
                    chat_id=chat_id,
                    text=formatted_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            
            logger.info(f"Sent goodbye for user {left_member.id} in chat {chat_id}")
        
        except Exception as e:
            logger.error(f"Error in goodbye_left_member: {e}", exc_info=True)
    
    logger.info("✅ Goodbye handlers setup complete")
