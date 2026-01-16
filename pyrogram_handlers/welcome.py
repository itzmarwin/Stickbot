"""
Welcome System Handler
Handles welcome messages with custom media, text, and buttons
"""
import logging
import re
import traceback
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus, ParseMode

from database_management import (
    get_welcome_settings,
    create_default_welcome_settings,
    update_welcome_status,
    set_custom_welcome,
    delete_custom_welcome
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


def format_welcome_text(text: str, user, chat) -> str:
    """
    Replace variables in welcome text
    
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


async def setup_welcome_handlers(client: Client):
    """Setup welcome command handlers"""
    print("🔄 DEBUG: Setting up welcome handlers...")
    
    @client.on_message(filters.command("welcome") & filters.group)
    async def welcome_command(client: Client, message: Message):
        """
        Handle /welcome on and /welcome off commands
        """
        print(f"🔄 DEBUG: /welcome command received from {message.from_user.id} in chat {message.chat.id}")
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            print(f"🔄 DEBUG: Checking admin status for user {user_id}")
            # Check admin
            if not await is_user_admin(client, chat_id, user_id):
                print(f"❌ DEBUG: User {user_id} is not admin")
                await message.reply_text(
                    "❌ <b>Only admins can use this command!</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            print(f"✅ DEBUG: User {user_id} is admin")
            # Parse command
            command_parts = message.text.split(maxsplit=1)
            
            if len(command_parts) < 2:
                print(f"ℹ️ DEBUG: No action specified in /welcome command")
                await message.reply_text(
                    "ℹ️ <b>Welcome Command Usage:</b>\n\n"
                    "<code>/welcome on</code> - Enable welcome messages\n"
                    "<code>/welcome off</code> - Disable welcome messages\n\n"
                    "💡 Use <code>/setwelcome</code> to set custom welcome\n\n"
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
            print(f"🔄 DEBUG: Action requested: {action}")
            
            # Get current settings
            print(f"🔄 DEBUG: Fetching settings for chat {chat_id}")
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                print(f"⚠️ DEBUG: No settings found, creating default")
                # Create default settings
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
                print(f"✅ DEBUG: Default settings created")
            
            print(f"✅ DEBUG: Settings loaded: enabled={settings['welcome']['enabled']}, custom_set={settings['welcome']['custom_set']}")
            
            # Handle /welcome on
            if action == "on":
                if settings['welcome']['enabled']:
                    print(f"ℹ️ DEBUG: Welcome already enabled")
                    await message.reply_text(
                        "✅ <b>Welcome is already enabled!</b>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                # Enable welcome
                print(f"🔄 DEBUG: Enabling welcome for chat {chat_id}")
                await update_welcome_status(chat_id, True)
                print(f"✅ DEBUG: Welcome enabled")
                
                if settings['welcome']['custom_set']:
                    await message.reply_text(
                        "✅ <b>Welcome enabled!</b>\n\n"
                        "Custom welcome message will be sent to new members.",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text(
                        "✅ <b>Welcome enabled!</b>\n\n"
                        "Default welcome message will be sent to new members.\n"
                        "Use <code>/setwelcome</code> to set a custom message.",
                        parse_mode=ParseMode.HTML
                    )
            
            # Handle /welcome off
            elif action == "off":
                if not settings['welcome']['enabled']:
                    print(f"ℹ️ DEBUG: Welcome already disabled")
                    await message.reply_text(
                        "ℹ️ <b>Welcome is already disabled!</b>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                # Disable welcome
                print(f"🔄 DEBUG: Disabling welcome for chat {chat_id}")
                await update_welcome_status(chat_id, False)
                print(f"✅ DEBUG: Welcome disabled")
                
                await message.reply_text(
                    "❌ <b>Welcome disabled!</b>\n\n"
                    "New members will not receive welcome messages.",
                    parse_mode=ParseMode.HTML
                )
            
            else:
                print(f"❌ DEBUG: Invalid action: {action}")
                await message.reply_text(
                    "⚠️ <b>Invalid action!</b>\n\n"
                    "Use <code>/welcome on</code> or <code>/welcome off</code>",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            print(f"❌ DEBUG: Error in welcome_command: {e}")
            print(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
            logger.error(f"Error in welcome_command: {e}", exc_info=True)
            await message.reply_text(
                "❌ An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )

    @client.on_message(filters.command("testjoin") & filters.group)
    async def test_join(client: Client, message: Message):
        """Test if Pyrogram is receiving messages"""
        await message.reply("✅ Pyrogram is working!")
        print("✅ TEST: Pyrogram command received!")
    
    @client.on_message(filters.command("setwelcome") & filters.group)
    async def setwelcome_command(client: Client, message: Message):
        """
        Handle /setwelcome command
        Must be used as reply to media or text
        """
        print(f"🔄 DEBUG: /setwelcome command received from {message.from_user.id}")
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            # Check admin
            if not await is_user_admin(client, chat_id, user_id):
                print(f"❌ DEBUG: User {user_id} is not admin")
                await message.reply_text(
                    "❌ <b>Only admins can use this command!</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            print(f"✅ DEBUG: User {user_id} is admin")
            # Must be reply
            if not message.reply_to_message:
                print(f"❌ DEBUG: No reply message found")
                await message.reply_text(
                    "⚠️ <b>Please reply to a message!</b>\n\n"
                    "<b>Usage:</b>\n"
                    "1. Send/forward a photo/video/GIF with caption\n"
                    "2. Or send a text message\n"
                    "3. Reply to it with <code>/setwelcome</code>\n\n"
                    "<b>Variables:</b>\n"
                    "<code>{ID}</code> {NAME} {SURNAME} {NAMESURNAME}\n"
                    "<code>{DATE}</code> {TIME} {MENTION} {USERNAME}\n"
                    "<code>{GROUPNAME}</code> {RULES}\n\n"
                    "<b>Buttons:</b> Use <code>[Text](URL)</code> format",
                    parse_mode=ParseMode.HTML
                )
                return
            
            replied_msg = message.reply_to_message
            print(f"✅ DEBUG: Reply found, message type: {replied_msg.media}")
            
            # Get current settings
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                print(f"⚠️ DEBUG: No settings found, creating default")
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            # ✅ FIXED: Removed blocking check
            
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
                print(f"✅ DEBUG: Photo detected, file_id: {media_id[:20]}...")
            
            # Check for video
            elif replied_msg.video:
                media_type = "video"
                media_id = replied_msg.video.file_id
                text = replied_msg.caption or ""
                print(f"✅ DEBUG: Video detected, file_id: {media_id[:20]}...")
            
            # Check for animation (GIF)
            elif replied_msg.animation:
                media_type = "animation"
                media_id = replied_msg.animation.file_id
                text = replied_msg.caption or ""
                print(f"✅ DEBUG: Animation detected, file_id: {media_id[:20]}...")
            
            # Text only
            elif replied_msg.text:
                text = replied_msg.text
                print(f"✅ DEBUG: Text detected, length: {len(text)}")
            
            else:
                print(f"❌ DEBUG: Unsupported message type")
                await message.reply_text(
                    "❌ <b>Unsupported message type!</b>\n\n"
                    "Supported: Photo, Video, GIF, Text",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Parse buttons from text
            if text:
                print(f"🔄 DEBUG: Parsing buttons from text")
                text, buttons = parse_buttons(text)
                if buttons:
                    print(f"✅ DEBUG: Found {len(buttons)} buttons")
            
            if not text or len(text.strip()) == 0:
                text = "Welcome {MENTION}!"
                print(f"⚠️ DEBUG: No text found, using default")
            
            print(f"✅ DEBUG: Final text length: {len(text)}, media_type: {media_type}")
            
            # Save custom welcome
            success = await set_custom_welcome(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                buttons=buttons
            )
            
            if success:
                # ✅ FIXED: Auto-enable welcome
                print(f"🔄 DEBUG: Auto-enabling welcome")
                await update_welcome_status(chat_id, True)
                
                response = "✅ <b>Custom welcome set and enabled!</b>\n\n"
                
                if media_type:
                    response += f"<b>Type:</b> {media_type.title()}\n"
                
                response += f"<b>Text:</b> {text[:50]}...\n" if len(text) > 50 else f"<b>Text:</b> {text}\n"
                
                if buttons:
                    response += f"<b>Buttons:</b> {len(buttons)}\n"
                
                response += "\n✅ Welcome is now ON!"
                
                print(f"✅ DEBUG: Custom welcome set successfully")
                await message.reply_text(response, parse_mode=ParseMode.HTML)
            else:
                print(f"❌ DEBUG: Failed to set custom welcome in database")
                await message.reply_text(
                    "❌ Failed to set custom welcome. Please try again.",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            print(f"❌ DEBUG: Error in setwelcome_command: {e}")
            print(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
            logger.error(f"Error in setwelcome_command: {e}", exc_info=True)
            await message.reply_text(
                "❌ An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.command("delwelcome") & filters.group)
    async def delwelcome_command(client: Client, message: Message):
        """
        Handle /delwelcome command
        Deletes custom welcome and disables welcome
        """
        print(f"🔄 DEBUG: /delwelcome command received")
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
            
            if not settings or not settings['welcome']['custom_set']:
                await message.reply_text(
                    "ℹ️ <b>No custom welcome message is set!</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Delete custom welcome
            success = await delete_custom_welcome(chat_id)
            
            if success:
                await message.reply_text(
                    "✅ <b>Custom welcome deleted!</b>\n\n"
                    "Welcome is now disabled.\n"
                    "Use <code>/setwelcome</code> to set a new one.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    "❌ Failed to delete custom welcome.",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in delwelcome_command: {e}", exc_info=True)
            await message.reply_text(
                "❌ An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    # ✅ DEBUG COMMANDS
    @client.on_message(filters.command("checkwelcome") & filters.group)
    async def check_welcome_settings(client: Client, message: Message):
        """Debug command to check welcome settings"""
        print(f"🔄 DEBUG: /checkwelcome command received")
        try:
            chat_id = message.chat.id
            
            if not await is_user_admin(client, chat_id, message.from_user.id):
                await message.reply_text("❌ Only admins!")
                return
            
            print(f"🔄 DEBUG: Fetching settings for chat {chat_id}")
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                print(f"❌ DEBUG: No settings found in database")
                await message.reply_text("❌ No settings found!")
                return
            
            print(f"✅ DEBUG: Settings found: {settings}")
            welcome_config = settings.get('welcome', {})
            
            debug_msg = f"""
🔍 <b>Welcome Settings Debug</b>

<b>Chat ID:</b> <code>{chat_id}</code>

<b>Welcome Enabled:</b> {welcome_config.get('enabled', False)}
<b>Custom Set:</b> {welcome_config.get('custom_set', False)}
<b>Media Type:</b> {welcome_config.get('media_type') or 'None'}
<b>Has Text:</b> {bool(welcome_config.get('text'))}
<b>Buttons:</b> {len(welcome_config.get('buttons', []))}

<b>Text Preview:</b>
{welcome_config.get('text', 'No text')[:100]}
"""
            
            await message.reply_text(debug_msg, parse_mode=ParseMode.HTML)
            
        except Exception as e:
            print(f"❌ DEBUG: Error in check: {e}")
            logger.error(f"Error in check: {e}", exc_info=True)
            await message.reply_text(f"❌ Error: {e}")
    
    
    @client.on_message(filters.command("checkperms") & filters.group)
    async def check_bot_permissions(client: Client, message: Message):
        """Check bot permissions"""
        print(f"🔄 DEBUG: /checkperms command received")
        try:
            chat_id = message.chat.id
            
            if not await is_user_admin(client, chat_id, message.from_user.id):
                await message.reply_text("❌ Only admins!")
                return
            
            bot_member = await client.get_chat_member(chat_id, client.me.id)
            status = bot_member.status
            
            perms_msg = f"""
🤖 <b>Bot Status</b>

<b>Status:</b> {status.value}
<b>Bot ID:</b> <code>{client.me.id}</code>
<b>Chat ID:</b> <code>{chat_id}</code>
"""
            
            if status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                perms_msg += "\n✅ Bot is admin"
            else:
                perms_msg += "\n⚠️ Bot is NOT admin!"
            
            await message.reply_text(perms_msg, parse_mode=ParseMode.HTML)
            
        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")
    
    
    @client.on_message(filters.new_chat_members & filters.group)
    async def welcome_new_member(client: Client, message: Message):
        """Send welcome message to new members"""
        print(f"🔔🔔🔔 DEBUG: NEW MEMBER EVENT TRIGGERED!")
        print(f"🔔 DEBUG: Chat ID: {message.chat.id}")
        print(f"🔔 DEBUG: Chat Title: {message.chat.title}")
        print(f"🔔 DEBUG: New members count: {len(message.new_chat_members)}")
        
        for i, member in enumerate(message.new_chat_members):
            print(f"🔔 DEBUG: Member {i+1}: {member.id} - {member.first_name} (bot: {member.is_bot})")
        
        try:
            chat_id = message.chat.id
            
            print(f"🔄 DEBUG: Getting bot's own member status...")
            try:
                bot_member = await client.get_chat_member(chat_id, client.me.id)
                print(f"✅ DEBUG: Bot status: {bot_member.status}")
                if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                    print(f"⚠️ WARNING: Bot is not admin in this group!")
            except Exception as e:
                print(f"❌ DEBUG: Error checking bot status: {e}")
            
            logger.info(f"🔔 New member(s) in chat {chat_id}")
            
            # Get settings
            print(f"🔄 DEBUG: Fetching welcome settings from database...")
            settings = await get_welcome_settings(chat_id)
            print(f"✅ DEBUG: Settings fetched: {settings is not None}")
            
            if not settings:
                print(f"⚠️ DEBUG: No settings found for {chat_id}, creating default...")
                logger.warning(f"⚠️ No settings for {chat_id}")
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
                print(f"✅ DEBUG: Default settings created")
            
            if settings:
                print(f"✅ DEBUG: Settings loaded successfully")
                print(f"✅ DEBUG: Welcome enabled: {settings.get('welcome', {}).get('enabled')}")
                print(f"✅ DEBUG: Custom set: {settings.get('welcome', {}).get('custom_set')}")
            else:
                print(f"❌ DEBUG: Failed to load settings even after creating default!")
                return
            
            logger.info(f"Settings: enabled={settings.get('welcome', {}).get('enabled')}")
            
            # Check if enabled
            if not settings or not settings.get('welcome', {}).get('enabled'):
                print(f"❌ DEBUG: Welcome is DISABLED for chat {chat_id}")
                logger.warning(f"⚠️ Welcome disabled for {chat_id}")
                return
            
            print(f"✅✅✅ DEBUG: Welcome is ENABLED for chat {chat_id}")
            
            # Welcome each member
            for new_member in message.new_chat_members:
                print(f"🔄 DEBUG: Processing member: {new_member.id} - {new_member.first_name}")
                
                if new_member.is_bot:
                    print(f"⏭️ DEBUG: Skipping bot user")
                    logger.info(f"⏭️ Skipping bot")
                    continue
                
                welcome_config = settings['welcome']
                
                # Get text
                if welcome_config.get('custom_set') and welcome_config.get('text'):
                    text = welcome_config['text']
                    print(f"✅ DEBUG: Using custom welcome text")
                else:
                    text = welcome_config.get('default_text', 'Welcome {MENTION}!')
                    print(f"✅ DEBUG: Using default welcome text")
                
                # Format text
                formatted_text = format_welcome_text(text, new_member, message.chat)
                print(f"✅ DEBUG: Formatted text length: {len(formatted_text)}")
                
                # Buttons
                reply_markup = None
                if welcome_config.get('buttons'):
                    reply_markup = create_button_markup(welcome_config['buttons'])
                    print(f"✅ DEBUG: Created {len(welcome_config['buttons'])} buttons")
                
                # Send message
                try:
                    if welcome_config.get('media_type') and welcome_config.get('media_id'):
                        media_type = welcome_config['media_type']
                        media_id = welcome_config['media_id']
                        
                        print(f"🔄 DEBUG: Sending {media_type} welcome with media_id: {media_id[:30]}...")
                        logger.info(f"Sending {media_type} welcome")
                        
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
                        print(f"✅✅✅ DEBUG: Media welcome sent successfully!")
                    else:
                        print(f"🔄 DEBUG: Sending text-only welcome")
                        logger.info(f"Sending text welcome")
                        await client.send_message(
                            chat_id=chat_id,
                            text=formatted_text,
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.HTML
                        )
                        print(f"✅✅✅ DEBUG: Text welcome sent successfully!")
                    
                    logger.info(f"✅ Welcome sent to {new_member.id}")
                    print(f"✅✅✅ DEBUG: Welcome message SENT to {new_member.id}")
                    
                except Exception as send_error:
                    print(f"❌❌❌ DEBUG: Error sending welcome: {send_error}")
                    print(f"❌ DEBUG: Traceback: {traceback.format_exc()}")
                    logger.error(f"❌ Send failed: {send_error}", exc_info=True)
                    try:
                        print(f"🔄 DEBUG: Trying fallback welcome message...")
                        await client.send_message(
                            chat_id=chat_id,
                            text=f"Welcome {new_member.mention}!",
                            parse_mode=ParseMode.HTML
                        )
                        print(f"✅ DEBUG: Fallback sent")
                        logger.info(f"✅ Fallback sent")
                    except Exception as fallback_error:
                        print(f"❌❌❌ DEBUG: Fallback also failed: {fallback_error}")
        
        except Exception as e:
            print(f"❌❌❌ DEBUG: CRITICAL ERROR in welcome handler: {e}")
            print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
            logger.error(f"❌ Critical error: {e}", exc_info=True)
    
    print("✅✅✅ DEBUG: Welcome handlers setup COMPLETE")
    logger.info("✅ Welcome handlers setup complete")
