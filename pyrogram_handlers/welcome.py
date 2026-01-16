"""
Welcome System Handler - DEBUG VERSION
"""
import logging
import re
import traceback
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated
from pyrogram.enums import ChatMemberStatus, ParseMode, ChatType, ChatMemberStatus

from database_management import (
    get_welcome_settings,
    create_default_welcome_settings,
    update_welcome_status,
    set_custom_welcome,
    delete_custom_welcome
)

logger = logging.getLogger(__name__)

# Global variable to track if handler is working
WELCOME_HANDLER_ACTIVE = False

def parse_buttons(text: str) -> tuple:
    """
    Parse buttons from text
    Format: [Button Text](https://url.com)
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


async def send_welcome_message(client: Client, chat_id: int, new_member, chat, settings):
    """
    Send welcome message to new member
    """
    try:
        welcome_config = settings['welcome']
        
        # Get text
        if welcome_config.get('custom_set') and welcome_config.get('text'):
            text = welcome_config['text']
        else:
            text = welcome_config.get('default_text', 'Welcome {MENTION}!')
        
        # Format text
        formatted_text = format_welcome_text(text, new_member, chat)
        
        # Buttons
        reply_markup = None
        if welcome_config.get('buttons'):
            reply_markup = create_button_markup(welcome_config['buttons'])
        
        # Send message
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
        
        return True
        
    except Exception as e:
        print(f"❌❌❌ DEBUG: Error sending welcome: {e}")
        return False


async def setup_welcome_handlers(client: Client):
    """Setup welcome command handlers"""
    global WELCOME_HANDLER_ACTIVE
    print("🔄 DEBUG: Setting up welcome handlers...")
    
    # Test handler to check if bot is receiving any messages
    @client.on_message(filters.group)
    async def test_all_messages(client: Client, message: Message):
        """Test handler to check if bot is receiving messages"""
        if message.new_chat_members:
            print(f"🎉🎉🎉 DEBUG: NEW MEMBER DETECTED in test handler!")
            print(f"Chat: {message.chat.id} - {message.chat.title}")
            print(f"New members: {[m.id for m in message.new_chat_members]}")
    
    @client.on_message(filters.command("welcome") & filters.group)
    async def welcome_command(client: Client, message: Message):
        """Handle /welcome commands"""
        print(f"🔄 DEBUG: /welcome command received")
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            # Check admin
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text("❌ Only admins can use this command!")
                return
            
            command_parts = message.text.split(maxsplit=1)
            
            if len(command_parts) < 2:
                await message.reply_text(
                    "Usage: /welcome on|off\n"
                    "/setwelcome - Set custom welcome\n"
                    "/delwelcome - Delete custom welcome"
                )
                return
            
            action = command_parts[1].lower()
            
            # Get current settings
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            if action == "on":
                if settings['welcome']['enabled']:
                    await message.reply_text("✅ Welcome is already enabled!")
                    return
                
                await update_welcome_status(chat_id, True)
                await message.reply_text("✅ Welcome enabled!")
                
            elif action == "off":
                if not settings['welcome']['enabled']:
                    await message.reply_text("ℹ️ Welcome is already disabled!")
                    return
                
                await update_welcome_status(chat_id, False)
                await message.reply_text("❌ Welcome disabled!")
            
            else:
                await message.reply_text("⚠️ Invalid action! Use /welcome on or /welcome off")
        
        except Exception as e:
            print(f"❌ DEBUG: Error in welcome_command: {e}")
            await message.reply_text("❌ An error occurred.")
    
    @client.on_message(filters.command("setwelcome") & filters.group)
    async def setwelcome_command(client: Client, message: Message):
        """Handle /setwelcome command"""
        print(f"🔄 DEBUG: /setwelcome command received")
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text("❌ Only admins!")
                return
            
            if not message.reply_to_message:
                await message.reply_text(
                    "⚠️ Please reply to a message!\n\n"
                    "1. Send a photo/video/text\n"
                    "2. Reply with /setwelcome"
                )
                return
            
            replied_msg = message.reply_to_message
            
            # Get current settings
            settings = await get_welcome_settings(chat_id)
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            # Extract data
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
                await message.reply_text("❌ Unsupported message type!")
                return
            
            # Parse buttons
            if text:
                text, buttons = parse_buttons(text)
            
            if not text or len(text.strip()) == 0:
                text = "Welcome {MENTION}!"
            
            # Save custom welcome
            success = await set_custom_welcome(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                buttons=buttons
            )
            
            if success:
                await update_welcome_status(chat_id, True)
                await message.reply_text("✅ Custom welcome set and enabled!")
            else:
                await message.reply_text("❌ Failed to set custom welcome.")
        
        except Exception as e:
            print(f"❌ DEBUG: Error in setwelcome_command: {e}")
            await message.reply_text("❌ An error occurred.")
    
    @client.on_message(filters.command("delwelcome") & filters.group)
    async def delwelcome_command(client: Client, message: Message):
        """Handle /delwelcome command"""
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text("❌ Only admins!")
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings or not settings['welcome']['custom_set']:
                await message.reply_text("ℹ️ No custom welcome set!")
                return
            
            success = await delete_custom_welcome(chat_id)
            
            if success:
                await message.reply_text("✅ Custom welcome deleted!")
            else:
                await message.reply_text("❌ Failed to delete welcome.")
        
        except Exception as e:
            print(f"❌ DEBUG: Error: {e}")
            await message.reply_text("❌ An error occurred.")
    
    # ✅ DEBUG COMMANDS
    @client.on_message(filters.command("checkwelcome") & filters.group)
    async def check_welcome_settings(client: Client, message: Message):
        """Debug command to check welcome settings"""
        try:
            chat_id = message.chat.id
            
            if not await is_user_admin(client, chat_id, message.from_user.id):
                await message.reply_text("❌ Only admins!")
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await message.reply_text("❌ No settings found!")
                return
            
            welcome_config = settings.get('welcome', {})
            
            debug_msg = f"""
🔍 Welcome Settings

Chat ID: {chat_id}
Enabled: {welcome_config.get('enabled', False)}
Custom Set: {welcome_config.get('custom_set', False)}
Media Type: {welcome_config.get('media_type') or 'None'}
Text: {welcome_config.get('text', 'No text')[:50]}
"""
            
            await message.reply_text(debug_msg)
            
        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")
    
    @client.on_message(filters.command("checkperms") & filters.group)
    async def check_bot_permissions(client: Client, message: Message):
        """Check bot permissions"""
        try:
            chat_id = message.chat.id
            
            if not await is_user_admin(client, chat_id, message.from_user.id):
                await message.reply_text("❌ Only admins!")
                return
            
            bot_member = await client.get_chat_member(chat_id, client.me.id)
            status = bot_member.status
            
            perms_msg = f"""
🤖 Bot Status

Status: {status.value}
Bot ID: {client.me.id}
Chat ID: {chat_id}
"""
            
            if status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                perms_msg += "\n✅ Bot is admin"
            else:
                perms_msg += "\n⚠️ Bot is NOT admin!"
            
            await message.reply_text(perms_msg)
            
        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")
    
    @client.on_message(filters.command("testwelcome") & filters.group)
    async def test_welcome_command(client: Client, message: Message):
        """Test welcome by simulating new member"""
        try:
            chat_id = message.chat.id
            
            if not await is_user_admin(client, chat_id, message.from_user.id):
                await message.reply_text("❌ Only admins!")
                return
            
            # Simulate welcome for the command user
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await message.reply_text("❌ No welcome settings!")
                return
            
            if not settings['welcome']['enabled']:
                await message.reply_text("❌ Welcome is disabled!")
                return
            
            # Send test welcome
            await send_welcome_message(client, chat_id, message.from_user, message.chat, settings)
            await message.reply_text("✅ Test welcome sent!")
            
        except Exception as e:
            print(f"❌ DEBUG: Test error: {e}")
            await message.reply_text(f"❌ Error: {e}")
    
    # ✅ METHOD 1: Traditional new chat members handler
    @client.on_message(filters.new_chat_members & filters.group)
    async def welcome_new_member_old(client: Client, message: Message):
        """OLD METHOD: Send welcome message to new members"""
        print("🎯 OLD HANDLER TRIGGERED!")
        print(f"Chat: {message.chat.id} - {message.chat.title}")
        print(f"New members: {[m.id for m in message.new_chat_members]}")
        
        try:
            chat_id = message.chat.id
            
            # Get settings
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            if not settings or not settings['welcome']['enabled']:
                return
            
            # Welcome each member
            for new_member in message.new_chat_members:
                if new_member.is_bot:
                    continue
                
                await send_welcome_message(client, chat_id, new_member, message.chat, settings)
                print(f"✅ OLD HANDLER: Welcome sent to {new_member.id}")
        
        except Exception as e:
            print(f"❌ OLD HANDLER ERROR: {e}")
    
    # ✅ METHOD 2: New method for updated Pyrogram
    @client.on_chat_member_updated()
    async def welcome_new_member_new(client: Client, chat_member_updated: ChatMemberUpdated):
        """NEW METHOD: Handle chat member updates"""
        try:
            # Check if this is a new member joining
            if (chat_member_updated.old_chat_member and 
                chat_member_updated.new_chat_member and
                chat_member_updated.old_chat_member.status == ChatMemberStatus.LEFT and
                chat_member_updated.new_chat_member.status == ChatMemberStatus.MEMBER):
                
                print("🎯 NEW HANDLER TRIGGERED!")
                print(f"Chat: {chat_member_updated.chat.id} - {chat_member_updated.chat.title}")
                print(f"User: {chat_member_updated.new_chat_member.user.id} - {chat_member_updated.new_chat_member.user.first_name}")
                
                chat_id = chat_member_updated.chat.id
                new_member = chat_member_updated.new_chat_member.user
                
                # Get settings
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                if not settings or not settings['welcome']['enabled']:
                    return
                
                if new_member.is_bot:
                    return
                
                await send_welcome_message(client, chat_id, new_member, chat_member_updated.chat, settings)
                print(f"✅ NEW HANDLER: Welcome sent to {new_member.id}")
        
        except Exception as e:
            print(f"❌ NEW HANDLER ERROR: {e}")
            print(traceback.format_exc())
    
    # ✅ METHOD 3: Alternative method using filters
    @client.on_message(filters.group)
    async def welcome_new_member_alt(client: Client, message: Message):
        """ALTERNATIVE METHOD: Check for new members in all group messages"""
        if message.new_chat_members:
            print("🎯 ALT HANDLER TRIGGERED!")
            print(f"Chat: {message.chat.id} - {message.chat.title}")
            print(f"New members count: {len(message.new_chat_members)}")
            
            try:
                chat_id = message.chat.id
                
                # Get settings
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                if not settings or not settings['welcome']['enabled']:
                    return
                
                # Welcome each member
                for new_member in message.new_chat_members:
                    if new_member.is_bot:
                        continue
                    
                    await send_welcome_message(client, chat_id, new_member, message.chat, settings)
                    print(f"✅ ALT HANDLER: Welcome sent to {new_member.id}")
            
            except Exception as e:
                print(f"❌ ALT HANDLER ERROR: {e}")
    
    WELCOME_HANDLER_ACTIVE = True
    print("✅✅✅ DEBUG: All welcome handlers setup complete!")
    print("✅ Test with /testwelcome command")
    print("✅ Check settings with /checkwelcome")
    print("✅ Check permissions with /checkperms")
