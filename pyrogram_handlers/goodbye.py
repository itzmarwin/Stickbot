import logging
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus, ParseMode

from database_management import (
    get_welcome_settings,
    create_default_welcome_settings,
    update_goodbye_status,
    set_custom_goodbye,
    delete_custom_goodbye,
    update_goodbye_auto_delete
)

logger = logging.getLogger(__name__)

GOODBYE_CACHE = {}
GOODBYE_DELETE_TASKS = {}


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


def format_goodbye_text(text: str, user, chat) -> str:
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


def format_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs > 0:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    
    return " ".join(parts)


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
    except Exception:
        return False


async def is_bot_admin(client: Client, chat_id: int) -> bool:
    try:
        bot = await client.get_me()
        bot_member = await client.get_chat_member(chat_id, bot.id)
        return bot_member.status in [ChatMemberStatus.ADMINISTRATOR]
    except Exception:
        return False


async def delete_message_after(message: Message, seconds: int, chat_id: int, message_id: int):
    try:
        await asyncio.sleep(seconds)
        await message.delete()
        if message_id in GOODBYE_DELETE_TASKS:
            del GOODBYE_DELETE_TASKS[message_id]
    except Exception as e:
        logger.error(f"Failed to delete goodbye message {message_id}: {e}")
        if message_id in GOODBYE_DELETE_TASKS:
            del GOODBYE_DELETE_TASKS[message_id]


async def setup_goodbye_handlers(client: Client):
    
    @client.on_message(filters.command("goodbye") & filters.group)
    async def goodbye_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                return
            
            command_parts = message.text.split(maxsplit=1)
            
            if len(command_parts) < 2:
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                is_enabled = settings.get('goodbye', {}).get('enabled', False)
                status_text = "enabled" if is_enabled else "disabled"
                
                await message.reply_text(
                    f"<b>Goodbye messages are currently {status_text}.</b>",
                    parse_mode=ParseMode.HTML
                )
                
                if is_enabled:
                    goodbye_config = settings['goodbye']
                    
                    if goodbye_config.get('custom_set') and goodbye_config.get('text'):
                        text = goodbye_config['text']
                    else:
                        text = goodbye_config.get('default_text', 'Goodbye {MENTION}! 👋 We hope to see you again.')
                    
                    reply_markup = None
                    if goodbye_config.get('buttons'):
                        reply_markup = create_button_markup(goodbye_config['buttons'])
                    
                    if goodbye_config.get('media_type') and goodbye_config.get('media_id'):
                        media_type = goodbye_config['media_type']
                        media_id = goodbye_config['media_id']
                        
                        if media_type == "photo":
                            await message.reply_photo(photo=media_id, caption=text, reply_markup=reply_markup)
                        elif media_type == "video":
                            await message.reply_video(video=media_id, caption=text, reply_markup=reply_markup)
                        elif media_type == "animation":
                            await message.reply_animation(animation=media_id, caption=text, reply_markup=reply_markup)
                    else:
                        await message.reply_text(text=text, reply_markup=reply_markup)
                
                return
            
            action = command_parts[1].lower()
            
            if not await is_bot_admin(client, chat_id):
                await message.reply_text(
                    "<b>Please promote the bot to admin to enable goodbye messages.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            if action == "on":
                if settings['goodbye']['enabled']:
                    await message.reply_text("Goodbye is already enabled!", parse_mode=ParseMode.HTML)
                    return
                
                await update_goodbye_status(chat_id, True)
                settings = await get_welcome_settings(chat_id)
                GOODBYE_CACHE[chat_id] = settings['goodbye']
                
                if settings['goodbye']['custom_set']:
                    await message.reply_text(
                        "<b>Goodbye enabled!</b>\n\nCustom goodbye message will be sent when members leave.",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text(
                        "<b>Goodbye enabled!</b>\n\nDefault goodbye message will be sent when members leave.\n"
                        "Use <code>/setgoodbye</code> to set a custom message.",
                        parse_mode=ParseMode.HTML
                    )
            
            elif action == "off":
                if not settings['goodbye']['enabled']:
                    await message.reply_text("Goodbye is already disabled!", parse_mode=ParseMode.HTML)
                    return
                
                await update_goodbye_status(chat_id, False)
                
                if chat_id in GOODBYE_CACHE:
                    del GOODBYE_CACHE[chat_id]
                
                await message.reply_text(
                    "<b>Goodbye disabled!</b>\n\nMembers leaving will not receive goodbye messages.",
                    parse_mode=ParseMode.HTML
                )
            
            else:
                await message.reply_text(
                    "<b>Use <code>/goodbye on</code> or <code>/goodbye off</code></b>",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in goodbye_command: {e}", exc_info=True)
            await message.reply_text(
                "Please try again shortly. If the problem continues, contact our support group.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.command("setgoodbye") & filters.group)
    async def setgoodbye_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                return
            
            if not await is_bot_admin(client, chat_id):
                await message.reply_text(
                    "<b>Please promote the bot to admin to enable goodbye messages.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            if not message.reply_to_message:
                await message.reply_text(
                    "<b>Please reply to a message!</b>\n\n<b>Usage:</b>\n"
                    "1. Send/forward a photo/video/GIF with caption\n2. Or send a text message\n"
                    "3. Reply to it with <code>/setgoodbye</code>\n\n<b>Variables:</b>\n"
                    "<code>{ID}</code> {NAME} {SURNAME} {NAMESURNAME}\n<code>{DATE}</code> {TIME} {MENTION} {USERNAME}\n"
                    "<code>{GROUPNAME}</code>\n\n<b>Buttons Format:</b>\n<code>[Button](URL)</code> - Single button\n"
                    "<code>[Btn1](URL) | [Btn2](URL)</code> - Two buttons in one row\nMax 2 buttons per row, Max 6 buttons total",
                    parse_mode=ParseMode.HTML
                )
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            if settings['goodbye']['custom_set']:
                await message.reply_text(
                    "<b>Custom goodbye already set!</b>\n\nFirst use <code>/delgoodbye</code> to remove the existing custom goodbye,\n"
                    "then set the new one.\n\nThis prevents accidental overwrites.",
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
                        f"<b>Button Error:</b> {error}\n\n<b>Rules:</b>\n• Max 2 buttons per row\n"
                        "• Max 6 buttons total\n• Use | to put buttons in same row\n\n<b>Examples:</b>\n"
                        "<code>[Btn1](url) | [Btn2](url)</code>\n<code>[Btn3](url)</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return
            
            if not text or len(text.strip()) == 0:
                text = "Goodbye {MENTION}! 👋 We hope to see you again."
            
            success = await set_custom_goodbye(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                buttons=button_rows
            )
            
            if success:
                await update_goodbye_status(chat_id, True)
                settings = await get_welcome_settings(chat_id)
                GOODBYE_CACHE[chat_id] = settings['goodbye']
                
                await message.reply_text(
                    "<b>Goodbye message has been set successfully!</b>\n\nGoodbye is now <b>enabled</b>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    "Unable to set the goodbye message at this time. Please try again later.",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            logger.error(f"Error in setgoodbye_command: {e}", exc_info=True)
            await message.reply_text(
                "Please try again later or contact the support group if the issue persists.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.command("delgoodbye") & filters.group)
    async def delgoodbye_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                return
            
            command_parts = message.text.split()
            
            if len(command_parts) == 1:
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                auto_delete = settings.get('goodbye', {}).get('auto_delete', {})
                is_enabled = auto_delete.get('enabled', False)
                
                if is_enabled:
                    delete_after = auto_delete.get('delete_after', 600)
                    time_str = format_time(delete_after)
                    
                    await message.reply_text(
                        f"✅ <b>Auto-delete goodbye is enabled</b>\n\n"
                        f"⏰ Goodbye messages will be deleted after: <b>{time_str}</b>",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text(
                        "❌ <b>Auto-delete goodbye is disabled for this group</b>",
                        parse_mode=ParseMode.HTML
                    )
                return
            
            action = command_parts[1].lower()
            
            if action == "on":
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                auto_delete = settings.get('goodbye', {}).get('auto_delete', {})
                if auto_delete.get('enabled'):
                    await message.reply_text(
                        "✅ Auto-delete goodbye is already enabled!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                await update_goodbye_auto_delete(chat_id, True, 600)
                
                settings = await get_welcome_settings(chat_id)
                if chat_id in GOODBYE_CACHE:
                    GOODBYE_CACHE[chat_id] = settings['goodbye']
                
                await message.reply_text(
                    "✅ <b>Auto-delete goodbye enabled!</b>\n\n"
                    "⏰ Goodbye messages will be deleted after: <b>10 minutes</b>",
                    parse_mode=ParseMode.HTML
                )
            
            elif action == "off":
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await message.reply_text(
                        "❌ Auto-delete is not configured for this group.",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                auto_delete = settings.get('goodbye', {}).get('auto_delete', {})
                if not auto_delete.get('enabled'):
                    await message.reply_text(
                        "❌ Auto-delete goodbye is already disabled!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                await update_goodbye_auto_delete(chat_id, False, None)
                
                if chat_id in GOODBYE_CACHE:
                    settings = await get_welcome_settings(chat_id)
                    GOODBYE_CACHE[chat_id] = settings['goodbye']
                
                for msg_id in list(GOODBYE_DELETE_TASKS.keys()):
                    if msg_id in GOODBYE_DELETE_TASKS:
                        GOODBYE_DELETE_TASKS[msg_id].cancel()
                        del GOODBYE_DELETE_TASKS[msg_id]
                
                await message.reply_text(
                    "❌ <b>Auto-delete goodbye disabled!</b>\n\n"
                    "Goodbye messages will not be deleted automatically.",
                    parse_mode=ParseMode.HTML
                )
            
            elif action.isdigit():
                delete_after = int(action)
                
                if delete_after < 10:
                    await message.reply_text(
                        "⚠️ Minimum delete time is 10 seconds!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                if delete_after > 86400:
                    await message.reply_text(
                        "⚠️ Maximum delete time is 24 hours (86400 seconds)!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                await update_goodbye_auto_delete(chat_id, True, delete_after)
                
                settings = await get_welcome_settings(chat_id)
                if chat_id in GOODBYE_CACHE:
                    GOODBYE_CACHE[chat_id] = settings['goodbye']
                
                time_str = format_time(delete_after)
                
                await message.reply_text(
                    f"✅ <b>Auto-delete goodbye updated!</b>\n\n"
                    f"⏰ Goodbye messages will be deleted after: <b>{time_str}</b>",
                    parse_mode=ParseMode.HTML
                )
            
            else:
                settings = await get_welcome_settings(chat_id)
                
                if not settings or not settings['goodbye']['custom_set']:
                    await message.reply_text(
                        "<b>No goodbye message is set.</b>\n\nSet it using <code>/setgoodbye</code>.",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                success = await delete_custom_goodbye(chat_id)
                
                if success:
                    if chat_id in GOODBYE_CACHE:
                        del GOODBYE_CACHE[chat_id]
                    
                    await message.reply_text("<b>Goodbye message deleted.</b>", parse_mode=ParseMode.HTML)
                else:
                    await message.reply_text("Unable to delete the goodbye message.", parse_mode=ParseMode.HTML)
        
        except Exception as e:
            logger.error(f"Error in delgoodbye_command: {e}", exc_info=True)
            await message.reply_text(
                "Please try again later. If the problem continues, contact the support group.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.left_chat_member & filters.group)
    async def goodbye_left_member(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            left_member = message.left_chat_member
            
            if left_member.is_bot:
                return
            
            if chat_id in GOODBYE_CACHE:
                goodbye_config = GOODBYE_CACHE[chat_id]
                
                if not goodbye_config.get('enabled'):
                    return
            else:
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                if not settings or not settings.get('goodbye', {}).get('enabled'):
                    return
                
                goodbye_config = settings['goodbye']
                GOODBYE_CACHE[chat_id] = goodbye_config
            
            if goodbye_config.get('custom_set') and goodbye_config.get('text'):
                text = goodbye_config['text']
            else:
                text = goodbye_config.get('default_text', 'Goodbye {MENTION}! 👋 We hope to see you again.')
            
            formatted_text = format_goodbye_text(text, left_member, message.chat)
            
            reply_markup = None
            if goodbye_config.get('buttons'):
                reply_markup = create_button_markup(goodbye_config['buttons'])
            
            sent_message = None
            
            if goodbye_config.get('media_type') and goodbye_config.get('media_id'):
                media_type = goodbye_config['media_type']
                media_id = goodbye_config['media_id']
                
                if media_type == "photo":
                    sent_message = await client.send_photo(
                        chat_id=chat_id,
                        photo=media_id,
                        caption=formatted_text,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML
                    )
                elif media_type == "video":
                    sent_message = await client.send_video(
                        chat_id=chat_id,
                        video=media_id,
                        caption=formatted_text,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML
                    )
                elif media_type == "animation":
                    sent_message = await client.send_animation(
                        chat_id=chat_id,
                        animation=media_id,
                        caption=formatted_text,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML
                    )
            else:
                sent_message = await client.send_message(
                    chat_id=chat_id,
                    text=formatted_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            
            auto_delete = goodbye_config.get('auto_delete', {})
            if auto_delete.get('enabled') and sent_message:
                delete_after = auto_delete.get('delete_after', 600)
                
                task = asyncio.create_task(
                    delete_message_after(sent_message, delete_after, chat_id, sent_message.id)
                )
                GOODBYE_DELETE_TASKS[sent_message.id] = task
        
        except Exception as e:
            logger.error(f"Error in goodbye_left_member: {e}", exc_info=True)
    
    logger.info("✅ Goodbye handlers setup complete")
