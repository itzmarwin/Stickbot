import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from pyrogram.errors import ChatAdminRequired, MessageDeleteForbidden, BadRequest, FloodWait

from pyrogram_handlers.utils import (
    parse_buttons,
    create_button_markup,
    format_message_text,
    format_time,
    validate_text_length,
    validate_auto_delete_time,
    is_user_admin,
    is_bot_admin,
    bot_can_delete_messages,
    get_cached_settings,
    update_cached_settings,
    clear_cached_settings,
    schedule_message_deletion,
    cancel_pending_deletions,
    DEFAULT_AUTO_DELETE_SECONDS,
    log_error
)

from database_management import (
    get_welcome_settings,
    create_default_welcome_settings,
    update_goodbye_status,
    set_custom_goodbye,
    delete_custom_goodbye,
    update_goodbye_auto_delete
)

logger = logging.getLogger(__name__)


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
                
                goodbye_config = settings.get('goodbye', {})
                is_enabled = goodbye_config.get('enabled', False)
                status_text = "✅ enabled" if is_enabled else "❌ disabled"
                
                await message.reply_text(
                    f"<b>Goodbye messages are currently {status_text}.</b>",
                    parse_mode=ParseMode.HTML
                )
                
                if is_enabled:
                    if goodbye_config.get('custom_set') and goodbye_config.get('text'):
                        text = goodbye_config['text']
                    else:
                        text = goodbye_config.get('default_text', 'Goodbye {MENTION}! 👋 We hope to see you again.')
                    
                    reply_markup = None
                    if goodbye_config.get('buttons'):
                        reply_markup = create_button_markup(goodbye_config['buttons'])
                    
                    try:
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
                    except BadRequest:
                        await message.reply_text("Preview unavailable (media may have expired)", parse_mode=ParseMode.HTML)
                
                return
            
            action = command_parts[1].lower()
            
            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please promote the bot to admin to enable goodbye messages.</b>", parse_mode=ParseMode.HTML)
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            goodbye_config = settings.get('goodbye', {})
            
            if action == "on":
                if goodbye_config.get('enabled'):
                    await message.reply_text("Goodbye is already enabled.", parse_mode=ParseMode.HTML)
                    return
                
                success = await update_goodbye_status(chat_id, True)
                
                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'goodbye', settings['goodbye'])
                    
                    if goodbye_config.get('custom_set'):
                        await message.reply_text(
                            "<b>Goodbye enabled.</b>",
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        await message.reply_text(
                            "<b>Goodbye enabled.</b>",
                            parse_mode=ParseMode.HTML
                        )
            
            elif action == "off":
                if not goodbye_config.get('enabled'):
                    await message.reply_text("Goodbye is already disabled.", parse_mode=ParseMode.HTML)
                    return
                
                success = await update_goodbye_status(chat_id, False)
                
                if success:
                    await clear_cached_settings(chat_id, 'goodbye')
                    await message.reply_text(
                        "<b>Goodbye disabled</b>\n\n"
                        "Members leaving will not receive goodbye messages.",
                        parse_mode=ParseMode.HTML
                    )
            
            else:
                await message.reply_text(
                    "Use <code>/goodbye on</code> or <code>/goodbye off</code>",
                    parse_mode=ParseMode.HTML
                )
        
        except ChatAdminRequired:
            await message.reply_text("Bot needs admin to manage goodbye messages.", parse_mode=ParseMode.HTML)
        except FloodWait as e:
            await message.reply_text(f"⏳ Please wait {e.value} seconds before trying again.", parse_mode=ParseMode.HTML)
        except Exception as e:
            log_error("goodbye_command", e, chat_id=chat_id, user_id=user_id)
            await message.reply_text("An error occurred. Please try again shortly.", parse_mode=ParseMode.HTML)
    
    
    @client.on_message(filters.command("setgoodbye") & filters.group)
    async def setgoodbye_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                return
            
            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please promote the bot to admin first.</b>", parse_mode=ParseMode.HTML)
                return
            
            if not message.reply_to_message:
                await message.reply_text(
                    "<b>Please reply to a message.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            if settings.get('goodbye', {}).get('custom_set'):
                await message.reply_text(
                    "<b>Goodbye message already set.</b>\n\n"
                    "Use <code>/delgoodbye</code> first to remove it.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            replied_msg = message.reply_to_message
            
            media_type = None
            media_id = None
            text = None
            
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
                    "<b>Unsupported message type.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            is_caption = media_type is not None
            validation_error = validate_text_length(text, is_caption)
            if validation_error:
                await message.reply_text(f"{validation_error}", parse_mode=ParseMode.HTML)
                return
            
            button_rows = []
            if text:
                text, button_rows, error = parse_buttons(text)
                if error:
                    await message.reply_text(
                        f"<b>Button Error:</b> {error}\n\n"
                        "<b>Format:</b> <code>[Text](URL)</code>\n"
                        "<b>Multiple:</b> <code>[Btn1](url) | [Btn2](url)</code>",
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
                await update_cached_settings(chat_id, 'goodbye', settings['goodbye'])
                
                await message.reply_text(
                    "<b>Goodbye message set successfully!</b>\n\n"
                    "Goodbye is now <b>enabled</b>.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text("Failed to set goodbye message. Please try again.", parse_mode=ParseMode.HTML)
        
        except ChatAdminRequired:
            await message.reply_text("Nigga Bot needs Admin Rights", parse_mode=ParseMode.HTML)
        except Exception as e:
            log_error("setgoodbye_command", e, chat_id=chat_id, user_id=user_id)
            await message.reply_text("Please try again later. If the problem continues, contact the support group.", parse_mode=ParseMode.HTML)
    
    
    @client.on_message(filters.command("delgoodbye") & filters.group)
    async def delgoodbye_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                return
            
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await message.reply_text("No goodbye settings found for this group.", parse_mode=ParseMode.HTML)
                return
            
            if not settings.get('goodbye', {}).get('custom_set'):
                await message.reply_text(
                    "<b>No custom goodbye message set.</b>\n\n"
                    "Use <code>/setgoodbye</code> to set a custom message.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            success = await delete_custom_goodbye(chat_id)
            
            if success:
                await clear_cached_settings(chat_id, 'goodbye')
                await message.reply_text(
                    "<b>Goodbye message deleted successfully!</b>\n"
                    "Use <code>/goodbye on</code> to enable.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text("Please try again later. If the problem continues, contact the support group.", parse_mode=ParseMode.HTML)
        
        except Exception as e:
            log_error("delgoodbye_command", e, chat_id=chat_id, user_id=user_id)
            await message.reply_text("Please try again later. If the problem continues, contact the support group.", parse_mode=ParseMode.HTML)
    
    
    @client.on_message(filters.command("cleangoodbye") & filters.group)
    async def cleangoodbye_command(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                return
            
            command_parts = message.text.split()
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            if len(command_parts) == 1:
                auto_delete = settings.get('goodbye', {}).get('auto_delete', {})
                is_enabled = auto_delete.get('enabled', False)
                
                if is_enabled:
                    delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
                    time_str = format_time(delete_after)
                    await message.reply_text(
                        f"<b>Auto-delete is enabled</b>\n\n"
                        f"Goodbye messages will be deleted after: <b>{time_str}</b>",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text("<b>Auto-delete is disabled</b>", parse_mode=ParseMode.HTML)
                return
            
            action = command_parts[1].lower()
            
            if action == "on":
                auto_delete = settings.get('goodbye', {}).get('auto_delete', {})
                if auto_delete.get('enabled'):
                    await message.reply_text("Auto-delete is already enabled.", parse_mode=ParseMode.HTML)
                    return
                
                success = await update_goodbye_auto_delete(chat_id, True, DEFAULT_AUTO_DELETE_SECONDS)
                
                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'goodbye', settings['goodbye'])
                    await message.reply_text(
                        f"<b>Auto-delete enabled</b>\n\n"
                        f"Goodbye messages will be deleted after: <b>{format_time(DEFAULT_AUTO_DELETE_SECONDS)}</b>",
                        parse_mode=ParseMode.HTML
                    )
            
            elif action == "off":
                auto_delete = settings.get('goodbye', {}).get('auto_delete', {})
                if not auto_delete.get('enabled'):
                    await message.reply_text("Auto-delete is already disabled.", parse_mode=ParseMode.HTML)
                    return
                
                success = await update_goodbye_auto_delete(chat_id, False, None)
                
                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'goodbye', settings['goodbye'])
                    await cancel_pending_deletions(chat_id, 'goodbye')
                    await message.reply_text("<b>Auto-delete disabled</b>", parse_mode=ParseMode.HTML)
            
            elif action.isdigit():
                delete_after = int(action)
                validation_error = validate_auto_delete_time(delete_after)
                if validation_error:
                    await message.reply_text(f"❌ {validation_error}", parse_mode=ParseMode.HTML)
                    return
                
                success = await update_goodbye_auto_delete(chat_id, True, delete_after)
                
                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'goodbye', settings['goodbye'])
                    time_str = format_time(delete_after)
                    await message.reply_text(
                        f"<b>Auto-delete time updated</b>\n\n"
                        f"Goodbye messages will be deleted after: <b>{time_str}</b>",
                        parse_mode=ParseMode.HTML
                    )
            
            else:
                await message.reply_text(
                    "Use <code>/cleangoodbye on</code> or <code>/cleangoodbye off</code>",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            log_error("cleangoodbye_command", e, chat_id=chat_id, user_id=user_id)
            await message.reply_text("Please try again later. If it still doesn’t work contact the support group.", parse_mode=ParseMode.HTML)
    
    
    @client.on_message(filters.left_chat_member & filters.group)
    async def goodbye_left_member(client: Client, message: Message):
        try:
            chat_id = message.chat.id
            left_member = message.left_chat_member
            
            if left_member.is_bot:
                return
            
            goodbye_config = await get_cached_settings(chat_id, 'goodbye')
            
            if not goodbye_config:
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                if not settings or not settings.get('goodbye', {}).get('enabled'):
                    return
                
                goodbye_config = settings['goodbye']
                await update_cached_settings(chat_id, 'goodbye', goodbye_config)
            
            if not goodbye_config.get('enabled'):
                return
            
            if goodbye_config.get('custom_set') and goodbye_config.get('text'):
                text = goodbye_config['text']
            else:
                text = goodbye_config.get('default_text', 'Goodbye {MENTION}! 👋 We hope to see you again.')
            
            formatted_text = format_message_text(text, left_member, message.chat)
            
            reply_markup = None
            if goodbye_config.get('buttons'):
                reply_markup = create_button_markup(goodbye_config['buttons'])
            
            sent_message = None
            
            try:
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
                    delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
                    can_delete = await bot_can_delete_messages(client, chat_id)
                    
                    if can_delete:
                        await schedule_message_deletion(sent_message, delete_after, chat_id, 'goodbye')
                
            except (BadRequest, MessageDeleteForbidden, FloodWait):
                pass
            except Exception as send_error:
                log_error("Send goodbye failed", send_error, chat_id=chat_id)
        
        except Exception as e:
            log_error("goodbye_left_member", e, chat_id=message.chat.id)
    
    logger.info("✅ Goodbye handlers setup complete")
