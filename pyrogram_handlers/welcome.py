import logging
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMemberUpdated
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import (
    ChatAdminRequired,
    MessageDeleteForbidden,
    BadRequest,
    FloodWait
)

from pyrogram_handlers.utils import (
    parse_buttons,
    create_button_markup,
    
    # Text formatting
    format_message_text,
    format_time,
    
    # Validation
    validate_text_length,
    validate_auto_delete_time,
    get_default_auto_delete_time,
    
    # Permission checks
    is_user_admin,
    is_bot_admin,
    bot_can_delete_messages,
    
    # Cache management (Fix Issue #1, #24)
    get_cached_settings,
    update_cached_settings,
    clear_cached_settings,
    
    # Task management (Fix Issue #2, #3)
    schedule_message_deletion,
    cancel_pending_deletions,
    
    # Anti-flood (Fix Issue #35)
    check_join_flood,
    
    # Constants (Fix Issue #32)
    MIN_AUTO_DELETE_SECONDS,
    MAX_AUTO_DELETE_SECONDS,
    DEFAULT_AUTO_DELETE_SECONDS,
    MAX_TEXT_LENGTH,
    MAX_CAPTION_LENGTH,
    
    # Error handling
    log_error
)

from database_management import (
    get_welcome_settings,
    create_default_welcome_settings,
    update_welcome_status,
    set_custom_welcome,
    delete_custom_welcome,
    update_welcome_auto_delete
)

logger = logging.getLogger(__name__)


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

async def setup_welcome_handlers(client: Client):
    
    @client.on_message(filters.command("welcome") & filters.group)
    async def welcome_command(client: Client, message: Message):
        """
        Handle /welcome command
        Usage: /welcome [on|off]
        
        FIXES:
            - Issue #22: Reduced duplicate DB calls
            - Issue #33: Specific exception handling
        """
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            # Permission check
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text(
                    "❌ Only admins can use this command!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            command_parts = message.text.split(maxsplit=1)
            
            # No argument - show status and preview
            if len(command_parts) < 2:
                # Fix Issue #22: Single DB call instead of multiple
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                welcome_config = settings.get('welcome', {})
                is_enabled = welcome_config.get('enabled', False)
                status_text = "✅ enabled" if is_enabled else "❌ disabled"
                
                await message.reply_text(
                    f"<b>Welcome messages are currently {status_text}.</b>",
                    parse_mode=ParseMode.HTML
                )
                
                # Show preview if enabled
                if is_enabled:
                    if welcome_config.get('custom_set') and welcome_config.get('text'):
                        text = welcome_config['text']
                    else:
                        text = welcome_config.get('default_text', 'Hey {MENTION}!\nWelcome to {GROUPNAME}!')
                    
                    reply_markup = None
                    if welcome_config.get('buttons'):
                        reply_markup = create_button_markup(welcome_config['buttons'])
                    
                    # Send preview
                    try:
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
                    except BadRequest as e:
                        log_error("Preview send failed", e, chat_id=chat_id)
                        await message.reply_text(
                            "⚠️ Preview unavailable (media may have expired)",
                            parse_mode=ParseMode.HTML
                        )
                
                return
            
            # Action specified (on/off)
            action = command_parts[1].lower()
            
            # Check bot admin status
            if not await is_bot_admin(client, chat_id):
                await message.reply_text(
                    "⚠️ <b>Please promote the bot to admin to enable welcome messages.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Fix Issue #22: Single fetch, reuse settings
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            welcome_config = settings.get('welcome', {})
            
            if action == "on":
                if welcome_config.get('enabled'):
                    await message.reply_text(
                        "ℹ️ Welcome is already enabled!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                success = await update_welcome_status(chat_id, True)
                
                if success:
                    # Fix Issue #1: Thread-safe cache update
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                    
                    if welcome_config.get('custom_set'):
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
            
            elif action == "off":
                if not welcome_config.get('enabled'):
                    await message.reply_text(
                        "ℹ️ Welcome is already disabled!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                success = await update_welcome_status(chat_id, False)
                
                if success:
                    # Fix Issue #1: Thread-safe cache clear
                    await clear_cached_settings(chat_id, 'welcome')
                    
                    await message.reply_text(
                        "✅ <b>Welcome disabled!</b>\n\n"
                        "New members will not receive welcome messages.",
                        parse_mode=ParseMode.HTML
                    )
            
            else:
                await message.reply_text(
                    "❌ Invalid option!\n\n"
                    "Use <code>/welcome on</code> or <code>/welcome off</code>",
                    parse_mode=ParseMode.HTML
                )
        
        except ChatAdminRequired:
            await message.reply_text(
                "❌ Bot needs admin privileges to manage welcome messages.",
                parse_mode=ParseMode.HTML
            )
        except FloodWait as e:
            logger.warning(f"FloodWait: {e.value} seconds")
            await message.reply_text(
                f"⏳ Please wait {e.value} seconds before trying again.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            log_error("welcome_command", e, chat_id=chat_id, user_id=user_id)
            await message.reply_text(
                "❌ An error occurred. Please try again shortly.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.command("setwelcome") & filters.group)
    async def setwelcome_command(client: Client, message: Message):
        """
        Handle /setwelcome command
        Usage: Reply to a message with /setwelcome
        
        FIXES:
            - Issue #12: Input validation
            - Issue #13: Caption length check
            - Issue #22: Reduced DB calls
            - Issue #33: Specific exceptions
        """
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            # Permission check
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text(
                    "❌ Only admins can use this command!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Bot admin check
            if not await is_bot_admin(client, chat_id):
                await message.reply_text(
                    "⚠️ <b>Please promote the bot to admin first.</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Must reply to a message
            if not message.reply_to_message:
                await message.reply_text(
                    "❌ <b>Please reply to a message!</b>\n\n"
                    "<b>Supported:</b> Text, Photo, Video, GIF\n"
                    "<b>Variables:</b> <code>{MENTION} {NAME} {GROUPNAME}</code>\n"
                    "<b>Buttons:</b> <code>[Text](URL)</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Fix Issue #22: Single fetch
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            # Check if custom already set
            if settings.get('welcome', {}).get('custom_set'):
                await message.reply_text(
                    "⚠️ <b>Welcome message already set!</b>\n\n"
                    "Use <code>/delwelcome</code> first to remove it.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            replied_msg = message.reply_to_message
            
            # Parse message
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
                    "❌ <b>Unsupported message type!</b>\n\n"
                    "Supported: Text, Photo, Video, GIF",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Fix Issue #12, #13: Validate text length
            is_caption = media_type is not None
            validation_error = validate_text_length(text, is_caption)
            if validation_error:
                await message.reply_text(
                    f"❌ {validation_error}",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Parse buttons (with validation)
            button_rows = []
            if text:
                text, button_rows, error = parse_buttons(text)
                if error:
                    await message.reply_text(
                        f"❌ <b>Button Error:</b> {error}\n\n"
                        "<b>Format:</b> <code>[Text](URL)</code>\n"
                        "<b>Multiple:</b> <code>[Btn1](url) | [Btn2](url)</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return
            
            # Default text if empty
            if not text or len(text.strip()) == 0:
                text = "Hey {MENTION}!\nWelcome to {GROUPNAME}!"
            
            # Save to database
            success = await set_custom_welcome(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                buttons=button_rows
            )
            
            if success:
                # Enable welcome automatically
                await update_welcome_status(chat_id, True)
                
                # Fix Issue #1: Thread-safe cache update
                settings = await get_welcome_settings(chat_id)
                await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                
                await message.reply_text(
                    "✅ <b>Welcome message set successfully!</b>\n\n"
                    "Welcome is now <b>enabled</b>.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    "❌ Failed to set welcome message. Please try again.",
                    parse_mode=ParseMode.HTML
                )
        
        except ChatAdminRequired:
            await message.reply_text(
                "❌ Bot needs admin privileges.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            log_error("setwelcome_command", e, chat_id=chat_id, user_id=user_id)
            await message.reply_text(
                "❌ An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_message(filters.command("delwelcome") & filters.group)
    async def delwelcome_command(client: Client, message: Message):
        """
        Handle /delwelcome command
        Usage: 
            /delwelcome - Show auto-delete status
            /delwelcome on - Enable auto-delete
            /delwelcome off - Disable auto-delete
            /delwelcome <seconds> - Set custom time
            /delwelcome delete - Delete custom message
        
        FIXES:
            - Issue #22: Reduced DB calls
            - Issue #32: Use constants for validation
            - Issue #33: Specific exceptions
        """
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            
            # Permission check
            if not await is_user_admin(client, chat_id, user_id):
                await message.reply_text(
                    "❌ Only admins can use this command!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            command_parts = message.text.split()
            
            # Fix Issue #22: Single fetch
            settings = await get_welcome_settings(chat_id)
            
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)
            
            # No argument - show auto-delete status
            if len(command_parts) == 1:
                auto_delete = settings.get('welcome', {}).get('auto_delete', {})
                is_enabled = auto_delete.get('enabled', False)
                
                if is_enabled:
                    delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
                    time_str = format_time(delete_after)
                    
                    await message.reply_text(
                        f"✅ <b>Auto-delete is enabled</b>\n\n"
                        f"Welcome messages will be deleted after: <b>{time_str}</b>",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text(
                        "ℹ️ <b>Auto-delete is disabled</b>",
                        parse_mode=ParseMode.HTML
                    )
                return
            
            action = command_parts[1].lower()
            
            # Enable auto-delete
            if action == "on":
                auto_delete = settings.get('welcome', {}).get('auto_delete', {})
                if auto_delete.get('enabled'):
                    await message.reply_text(
                        "ℹ️ Auto-delete is already enabled!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                # Fix Issue #32: Use constant
                success = await update_welcome_auto_delete(
                    chat_id, True, DEFAULT_AUTO_DELETE_SECONDS
                )
                
                if success:
                    # Fix Issue #1: Update cache
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                    
                    await message.reply_text(
                        f"✅ <b>Auto-delete enabled</b>\n\n"
                        f"Welcome messages will be deleted after: <b>{format_time(DEFAULT_AUTO_DELETE_SECONDS)}</b>",
                        parse_mode=ParseMode.HTML
                    )
            
            # Disable auto-delete
            elif action == "off":
                auto_delete = settings.get('welcome', {}).get('auto_delete', {})
                if not auto_delete.get('enabled'):
                    await message.reply_text(
                        "ℹ️ Auto-delete is already disabled!",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                success = await update_welcome_auto_delete(chat_id, False, None)
                
                if success:
                    # Fix Issue #1: Update cache
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                    
                    # Fix Issue #2, #3: Cancel pending tasks
                    cancelled = await cancel_pending_deletions(chat_id, 'welcome')
                    
                    await message.reply_text(
                        "✅ <b>Auto-delete disabled</b>",
                        parse_mode=ParseMode.HTML
                    )
            
            # Set custom time
            elif action.isdigit():
                delete_after = int(action)
                
                # Fix Issue #32: Use constants for validation
                validation_error = validate_auto_delete_time(delete_after)
                if validation_error:
                    await message.reply_text(
                        f"❌ {validation_error}",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                success = await update_welcome_auto_delete(chat_id, True, delete_after)
                
                if success:
                    # Fix Issue #1: Update cache
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                    
                    time_str = format_time(delete_after)
                    
                    await message.reply_text(
                        f"✅ <b>Auto-delete time updated</b>\n\n"
                        f"Welcome messages will be deleted after: <b>{time_str}</b>",
                        parse_mode=ParseMode.HTML
                    )
            
            # Delete custom message
            elif action == "delete":
                if not settings.get('welcome', {}).get('custom_set'):
                    await message.reply_text(
                        "ℹ️ No custom welcome message set.\n\n"
                        "Use <code>/setwelcome</code> to set one.",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                success = await delete_custom_welcome(chat_id)
                
                if success:
                    # Fix Issue #1: Clear cache
                    await clear_cached_settings(chat_id, 'welcome')
                    
                    await message.reply_text(
                        "✅ <b>Welcome message deleted</b>",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text(
                        "❌ Failed to delete welcome message.",
                        parse_mode=ParseMode.HTML
                    )
            
            else:
                await message.reply_text(
                    "❌ Invalid option!\n\n"
                    "<b>Usage:</b>\n"
                    "<code>/delwelcome</code> - Status\n"
                    "<code>/delwelcome on</code> - Enable auto-delete\n"
                    "<code>/delwelcome off</code> - Disable auto-delete\n"
                    "<code>/delwelcome 300</code> - Set 5 min\n"
                    "<code>/delwelcome delete</code> - Remove custom message",
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            log_error("delwelcome_command", e, chat_id=chat_id, user_id=user_id)
            await message.reply_text(
                "❌ An error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
    
    
    @client.on_chat_member_updated(filters.group)
    async def welcome_new_member(client: Client, member_update: ChatMemberUpdated):
        """
        Send welcome message to new members
        
        FIXES:
            - Issue #1: Thread-safe cache
            - Issue #2, #3: Proper task management
            - Issue #11: Check delete permission
            - Issue #22: Efficient caching
            - Issue #35: Anti-flood protection
        """
        try:
            # Check if user joined
            if (
                not member_update.new_chat_member
                or member_update.new_chat_member.status in {"banned", "left", "restricted"}
                or member_update.old_chat_member  # Skip if rejoining
            ):
                return
            
            user = member_update.new_chat_member.user if member_update.new_chat_member else member_update.from_user
            chat_id = member_update.chat.id
            
            # Skip bots
            if user.is_bot:
                return
            
            # Fix Issue #35: Anti-flood check
            is_flooding, flood_msg = check_join_flood(chat_id)
            if is_flooding:
                logger.warning(f"Join flood detected in {chat_id}: {flood_msg}")
                return
            
            # Fix Issue #1, #22: Try cache first (thread-safe)
            welcome_config = await get_cached_settings(chat_id, 'welcome')
            
            if not welcome_config:
                # Cache miss - fetch from DB
                settings = await get_welcome_settings(chat_id)
                
                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)
                
                if not settings or not settings.get('welcome', {}).get('enabled'):
                    return
                
                welcome_config = settings['welcome']
                
                # Fix Issue #1: Thread-safe cache update
                await update_cached_settings(chat_id, 'welcome', welcome_config)
            
            # Check if enabled
            if not welcome_config.get('enabled'):
                return
            
            # Get text
            if welcome_config.get('custom_set') and welcome_config.get('text'):
                text = welcome_config['text']
            else:
                text = welcome_config.get('default_text', 'Hey {MENTION}!\nWelcome to {GROUPNAME}!')
            
            # Format text with variables
            formatted_text = format_message_text(text, user, member_update.chat)
            
            # Create buttons
            reply_markup = None
            if welcome_config.get('buttons'):
                reply_markup = create_button_markup(welcome_config['buttons'])
            
            # Send message
            sent_message = None
            
            try:
                if welcome_config.get('media_type') and welcome_config.get('media_id'):
                    media_type = welcome_config['media_type']
                    media_id = welcome_config['media_id']
                    
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
                
                # Fix Issue #2, #3, #11: Proper task management with permission check
                auto_delete = welcome_config.get('auto_delete', {})
                if auto_delete.get('enabled') and sent_message:
                    delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
                    
                    # Fix Issue #11: Check if bot can delete
                    can_delete = await bot_can_delete_messages(client, chat_id)
                    
                    if can_delete:
                        # Fix Issue #2, #3: Use utils task management
                        await schedule_message_deletion(
                            sent_message,
                            delete_after,
                            chat_id,
                            'welcome'
                        )
                    else:
                        logger.warning(f"Bot lacks delete permission in {chat_id}, skipping auto-delete")
                
            except BadRequest as e:
                log_error("Send welcome failed", e, chat_id=chat_id, error_type="BadRequest")
            except MessageDeleteForbidden:
                logger.warning(f"Cannot delete messages in {chat_id}")
            except FloodWait as e:
                logger.warning(f"FloodWait in welcome: {e.value}s")
            except Exception as send_error:
                log_error("Send welcome failed", send_error, chat_id=chat_id)
        
        except Exception as e:
            log_error("welcome_new_member", e, chat_id=member_update.chat.id)
    
    logger.info("✅ Welcome handlers setup complete")
