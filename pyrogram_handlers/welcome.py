import logging
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMemberUpdated, MessageEntity
from pyrogram.enums import ChatMemberStatus, ParseMode, MessageEntityType
from pyrogram.errors import ChatAdminRequired, MessageDeleteForbidden, BadRequest, FloodWait

from pyrogram_handlers.utils import (
    parse_buttons,
    create_button_markup,
    format_message_text,
    format_message_text_with_entities,
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
    check_join_flood,
    dict_to_entities,
    DEFAULT_AUTO_DELETE_SECONDS,
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

# ✅ CHANGE 1: Default welcome text — premium emoji ke saath
# 👋 emoji ki jagah custom_emoji_id "5447432232698389583" use hogi
# Text mein 👋 placeholder rakha hai jisko send karte waqt premium emoji entity se replace karenge
DEFAULT_WELCOME_TEXT = "Welcome {MENTION} Hope you have a great time here 👋"

# ✅ Premium emoji entity for default message — 👋 ka position text ke end mein hai
# "Welcome {MENTION} Hope you have a great time here 👋"
# {MENTION} replace hone ke baad offset dynamically calculate hoga — isliye
# hum default message ke liye ek special send function use karenge
DEFAULT_WELCOME_EMOJI_ID = "5447432232698389583"


async def setup_welcome_handlers(client: Client):

    @client.on_message(filters.command("welcome") & filters.group)
    async def welcome_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None

            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "<b>I need admin privileges to verify permissions.</b>\n\n"
                    "Please promote me to admin first.",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception as e:
                logger.error(f"Admin check failed: {type(e).__name__} - {e}")
                await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                return

            command_parts = message.text.split(maxsplit=1)

            if len(command_parts) < 2:
                settings = await get_welcome_settings(chat_id)

                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)

                welcome_config = settings.get('welcome', {})
                is_enabled = welcome_config.get('enabled', False)
                status_text = "enabled" if is_enabled else "disabled"

                await message.reply_text(
                    f"<b>Welcome messages are currently {status_text}.</b>",
                    parse_mode=ParseMode.HTML
                )

                # ✅ CHANGE 2: Preview mein bhi entities ke saath dikhao
                if is_enabled:
                    reply_markup = None
                    if welcome_config.get('buttons'):
                        reply_markup = create_button_markup(welcome_config['buttons'])

                    try:
                        if welcome_config.get('custom_set') and welcome_config.get('text'):
                            # Custom message — entities ke saath send karo
                            text = welcome_config['text']
                            stored_entities = welcome_config.get('entities') or []
                            entities = dict_to_entities(stored_entities) if stored_entities else None

                            if welcome_config.get('media_type') and welcome_config.get('media_id'):
                                media_type = welcome_config['media_type']
                                media_id = welcome_config['media_id']

                                if media_type == "photo":
                                    await message.reply_photo(
                                        photo=media_id,
                                        caption=text,
                                        caption_entities=entities,
                                        reply_markup=reply_markup
                                    )
                                elif media_type == "video":
                                    await message.reply_video(
                                        video=media_id,
                                        caption=text,
                                        caption_entities=entities,
                                        reply_markup=reply_markup
                                    )
                                elif media_type == "animation":
                                    await message.reply_animation(
                                        animation=media_id,
                                        caption=text,
                                        caption_entities=entities,
                                        reply_markup=reply_markup
                                    )
                            else:
                                await message.reply_text(
                                    text=text,
                                    entities=entities,
                                    reply_markup=reply_markup
                                )
                        else:
                            # Default message — premium emoji ke saath
                            await _send_default_welcome(
                                client=client,
                                chat_id=message.chat.id,
                                user=message.from_user,
                                chat=message.chat,
                                reply_markup=reply_markup,
                                reply_to_message_id=message.id
                            )
                    except BadRequest as e:
                        logger.error(f"BadRequest in welcome preview: {e}")
                        await message.reply_text("Preview unavailable (media may have expired)", parse_mode=ParseMode.HTML)

                return

            action = command_parts[1].lower()

            if action in ["on", "off"]:
                if not await is_bot_admin(client, chat_id):
                    await message.reply_text(
                        "<b>Please promote me to admin to enable welcome messages.</b>",
                        parse_mode=ParseMode.HTML
                    )
                    return

            settings = await get_welcome_settings(chat_id)

            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)

            welcome_config = settings.get('welcome', {})

            if action == "on":
                if welcome_config.get('enabled'):
                    await message.reply_text("Welcome is already enabled", parse_mode=ParseMode.HTML)
                    return

                success = await update_welcome_status(chat_id, True)

                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])

                    if welcome_config.get('custom_set'):
                        await message.reply_text(
                            "<b>Welcome enabled!</b>\n\n"
                            "Custom welcome message will be sent to new members.",
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        await message.reply_text(
                            "<b>Welcome enabled.</b>\n\n"
                            "Default welcome message will be sent to new members.\n"
                            "Use <code>/setwelcome</code> to set a custom message.",
                            parse_mode=ParseMode.HTML
                        )

            elif action == "off":
                if not welcome_config.get('enabled'):
                    await message.reply_text("Welcome is already disabled.", parse_mode=ParseMode.HTML)
                    return

                success = await update_welcome_status(chat_id, False)

                if success:
                    await clear_cached_settings(chat_id, 'welcome')
                    await message.reply_text(
                        "<b>Welcome disabled.</b>",
                        parse_mode=ParseMode.HTML
                    )

            else:
                await message.reply_text(
                    "Use <code>/welcome on</code> or <code>/welcome off</code>",
                    parse_mode=ParseMode.HTML
                )

        except FloodWait as e:
            await message.reply_text(f"⏳ Please wait {e.value} seconds before trying again.", parse_mode=ParseMode.HTML)
        except Exception as e:
            log_error("welcome_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("An error occurred. Please try again shortly.", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("setwelcome") & filters.group)
    async def setwelcome_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None

            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "<b>I need admin privileges to verify permissions.</b>\n\n"
                    "Please promote me to admin first.",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception:
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

            if settings.get('welcome', {}).get('custom_set'):
                await message.reply_text(
                    "<b>Welcome message already set.</b>\n\n"
                    "Use <code>/delwelcome</code> first to remove it.",
                    parse_mode=ParseMode.HTML
                )
                return

            replied_msg = message.reply_to_message

            media_type = None
            media_id = None
            text = None
            # ✅ CHANGE 3: Entities capture karna — bold/italic/spoiler/blockquote/premium emoji sab
            raw_entities = None

            if replied_msg.photo:
                media_type = "photo"
                media_id = replied_msg.photo.file_id
                # ✅ caption.html ki jagah plain text + caption_entities use karo
                text = replied_msg.caption or ""
                raw_entities = replied_msg.caption_entities or []
            elif replied_msg.video:
                media_type = "video"
                media_id = replied_msg.video.file_id
                text = replied_msg.caption or ""
                raw_entities = replied_msg.caption_entities or []
            elif replied_msg.animation:
                media_type = "animation"
                media_id = replied_msg.animation.file_id
                text = replied_msg.caption or ""
                raw_entities = replied_msg.caption_entities or []
            elif replied_msg.text:
                # ✅ replied_msg.text plain text hai, entities alag hain
                text = replied_msg.text
                raw_entities = replied_msg.entities or []
            else:
                await message.reply_text(
                    "<b>Unsupported message type.</b>\n\n"
                    "Supported: Text, Photo, Video, GIF",
                    parse_mode=ParseMode.HTML
                )
                return

            is_caption = media_type is not None
            validation_error = validate_text_length(text, is_caption)
            if validation_error:
                await message.reply_text(f"{validation_error}", parse_mode=ParseMode.HTML)
                return

            # ✅ CHANGE 4: Button parse karo — lekin entities ko preserve karo
            # Buttons [Text](URL) format ke liye text scan karo
            # Note: agar koi button text nahi hai toh entities waise hi rahenge
            button_rows = []
            if text:
                text, button_rows, raw_entities, error = parse_buttons_with_entities(text, raw_entities)
                if error:
                    await message.reply_text(
                        f"<b>Button Error:</b> {error}\n\n"
                        "<b>Format:</b> <code>[Text](URL)</code>\n"
                        "<b>Multiple:</b> <code>[Btn1](url) | [Btn2](url)</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return

            if not text or len(text.strip()) == 0:
                text = DEFAULT_WELCOME_TEXT
                raw_entities = []

            # ✅ CHANGE 5: Entities ko dict format mein convert karo DB mein save karne ke liye
            entities_list = _safe_entities_to_dict(raw_entities) if raw_entities else []

            success = await set_custom_welcome(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                entities=entities_list,   # ✅ NEW: entities DB mein save ho rahi hain
                buttons=button_rows
            )

            if success:
                await update_welcome_status(chat_id, True)
                settings = await get_welcome_settings(chat_id)
                await update_cached_settings(chat_id, 'welcome', settings['welcome'])

                await message.reply_text(
                    "<b>Welcome message set successfully.</b>\n\n"
                    "Welcome is now <b>enabled</b>.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text("Failed to set welcome message. Please try again.", parse_mode=ParseMode.HTML)

        except Exception as e:
            log_error("setwelcome_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("Please try again later. If it still doesn't work, contact the support group", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("delwelcome") & filters.group)
    async def delwelcome_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None

            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "<b>I need admin privileges to verify permissions.</b>\n\n"
                    "Please promote me to admin first.",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception:
                await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                return

            settings = await get_welcome_settings(chat_id)

            if not settings:
                await message.reply_text("No welcome settings found for this group.", parse_mode=ParseMode.HTML)
                return

            if not settings.get('welcome', {}).get('custom_set'):
                await message.reply_text(
                    "<b>No custom welcome message set.</b>\n\n"
                    "Use <code>/setwelcome</code> to set a custom message.",
                    parse_mode=ParseMode.HTML
                )
                return

            success = await delete_custom_welcome(chat_id)

            if success:
                await clear_cached_settings(chat_id, 'welcome')
                await message.reply_text(
                    "<b>Custom welcome message deleted successfully.</b>\n\n"
                    "Welcome is now <b>disabled</b>.\n"
                    "Use <code>/welcome on</code> to enable default message.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text("Failed to delete welcome message. Please try again.", parse_mode=ParseMode.HTML)

        except Exception as e:
            log_error("delwelcome_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("Please try again later. If it still doesn't work, contact the support group", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("cleanwelcome") & filters.group)
    async def cleanwelcome_command(client: Client, message: Message):
        chat_id = None
        user_id = None
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id if message.from_user else None

            try:
                is_admin = await is_user_admin(client, chat_id, user_id)
                if not is_admin:
                    await message.reply_text("Only admins can use this command", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "<b>I need admin privileges to verify permissions.</b>\n\n"
                    "Please promote me to admin first.",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception:
                await message.reply_text("Only admins can use this command", parse_mode=ParseMode.HTML)
                return

            command_parts = message.text.split()
            settings = await get_welcome_settings(chat_id)

            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)

            if len(command_parts) == 1:
                auto_delete = settings.get('welcome', {}).get('auto_delete', {})
                is_enabled = auto_delete.get('enabled', False)

                if is_enabled:
                    delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
                    time_str = format_time(delete_after)
                    await message.reply_text(
                        f"<b>Auto-delete is enabled</b>\n\n"
                        f"Welcome messages will be deleted after: <b>{time_str}</b>",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text("<b>Auto-delete is disabled</b>", parse_mode=ParseMode.HTML)
                return

            action = command_parts[1].lower()

            if action == "on":
                auto_delete = settings.get('welcome', {}).get('auto_delete', {})
                if auto_delete.get('enabled'):
                    await message.reply_text("Auto-delete is already enabled", parse_mode=ParseMode.HTML)
                    return

                success = await update_welcome_auto_delete(chat_id, True, DEFAULT_AUTO_DELETE_SECONDS)

                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                    await message.reply_text(
                        f"<b>Auto-delete enabled</b>\n\n"
                        f"Welcome messages will be deleted after: <b>{format_time(DEFAULT_AUTO_DELETE_SECONDS)}</b>",
                        parse_mode=ParseMode.HTML
                    )

            elif action == "off":
                auto_delete = settings.get('welcome', {}).get('auto_delete', {})
                if not auto_delete.get('enabled'):
                    await message.reply_text("Auto-delete is already disabled.", parse_mode=ParseMode.HTML)
                    return

                success = await update_welcome_auto_delete(chat_id, False, None)

                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                    await cancel_pending_deletions(chat_id, 'welcome')
                    await message.reply_text("<b>Auto-delete disabled</b>", parse_mode=ParseMode.HTML)

            elif action.isdigit():
                delete_after = int(action)
                validation_error = validate_auto_delete_time(delete_after)
                if validation_error:
                    await message.reply_text(f"{validation_error}", parse_mode=ParseMode.HTML)
                    return

                success = await update_welcome_auto_delete(chat_id, True, delete_after)

                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                    time_str = format_time(delete_after)
                    await message.reply_text(
                        f"<b>Auto-delete time updated</b>\n\n"
                        f"Welcome messages will be deleted after: <b>{time_str}</b>",
                        parse_mode=ParseMode.HTML
                    )

            else:
                await message.reply_text(
                    "Use <code>/cleanwelcome on</code> or <code>/cleanwelcome off</code>",
                    parse_mode=ParseMode.HTML
                )

        except Exception as e:
            log_error("cleanwelcome_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text("Please try again later. If it still doesn't work, contact the support group", parse_mode=ParseMode.HTML)


    @client.on_chat_member_updated(filters.group)
    async def welcome_new_member(client: Client, member_update: ChatMemberUpdated):
        try:
            if not member_update.new_chat_member:
                return

            if member_update.old_chat_member:
                old_status = member_update.old_chat_member.status
                if old_status in {ChatMemberStatus.BANNED, ChatMemberStatus.LEFT, ChatMemberStatus.RESTRICTED}:
                    return
                return

            new_status = member_update.new_chat_member.status
            if new_status in {ChatMemberStatus.BANNED, ChatMemberStatus.LEFT, ChatMemberStatus.RESTRICTED}:
                return

            if new_status != ChatMemberStatus.MEMBER:
                return

            user = member_update.new_chat_member.user if member_update.new_chat_member else member_update.from_user
            chat_id = member_update.chat.id

            if user.is_bot:
                return

            is_flooding, flood_msg = check_join_flood(chat_id)
            if is_flooding:
                return

            welcome_config = await get_cached_settings(chat_id, 'welcome')

            if not welcome_config:
                settings = await get_welcome_settings(chat_id)

                if not settings:
                    await create_default_welcome_settings(chat_id)
                    settings = await get_welcome_settings(chat_id)

                if not settings or not settings.get('welcome', {}).get('enabled'):
                    return

                welcome_config = settings['welcome']
                await update_cached_settings(chat_id, 'welcome', welcome_config)

            if not welcome_config.get('enabled'):
                return

            reply_markup = None
            if welcome_config.get('buttons'):
                reply_markup = create_button_markup(welcome_config['buttons'])

            sent_message = None

            try:
                if welcome_config.get('custom_set') and welcome_config.get('text'):
                    # ✅ CHANGE 6: Custom message — entities ke saath send karo
                    text = welcome_config['text']
                    stored_entities = welcome_config.get('entities') or []

                    # Entities DB se restore karo
                    entities = dict_to_entities(stored_entities) if stored_entities else None

                    # {MENTION} aur baaki placeholders replace karo
                    # Entities ke offsets bhi adjust honge kyunki {MENTION} ka length change hota hai
                    formatted_text, adjusted_entities = format_message_text_with_entities(
                        text, entities, user, member_update.chat
                    )

                    if welcome_config.get('media_type') and welcome_config.get('media_id'):
                        media_type = welcome_config['media_type']
                        media_id = welcome_config['media_id']

                        if media_type == "photo":
                            sent_message = await client.send_photo(
                                chat_id=chat_id,
                                photo=media_id,
                                caption=formatted_text,
                                caption_entities=adjusted_entities,  # ✅ parse_mode nahi, entities directly
                                reply_markup=reply_markup
                            )
                        elif media_type == "video":
                            sent_message = await client.send_video(
                                chat_id=chat_id,
                                video=media_id,
                                caption=formatted_text,
                                caption_entities=adjusted_entities,
                                reply_markup=reply_markup
                            )
                        elif media_type == "animation":
                            sent_message = await client.send_animation(
                                chat_id=chat_id,
                                animation=media_id,
                                caption=formatted_text,
                                caption_entities=adjusted_entities,
                                reply_markup=reply_markup
                            )
                    else:
                        sent_message = await client.send_message(
                            chat_id=chat_id,
                            text=formatted_text,
                            entities=adjusted_entities,  # ✅ parse_mode nahi, entities directly
                            reply_markup=reply_markup
                        )

                else:
                    # ✅ CHANGE 7: Default message — premium emoji ke saath
                    sent_message = await _send_default_welcome(
                        client=client,
                        chat_id=chat_id,
                        user=user,
                        chat=member_update.chat,
                        reply_markup=reply_markup
                    )

                auto_delete = welcome_config.get('auto_delete', {})
                if auto_delete.get('enabled') and sent_message:
                    delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
                    can_delete = await bot_can_delete_messages(client, chat_id)

                    if can_delete:
                        await schedule_message_deletion(sent_message, delete_after, chat_id, 'welcome')

            except (BadRequest, MessageDeleteForbidden, FloodWait):
                pass
            except Exception as send_error:
                log_error("Send welcome failed", send_error, chat_id=chat_id)

        except Exception as e:
            log_error("welcome_new_member", e, chat_id=member_update.chat.id)

    logger.info("✅ Welcome handlers setup complete")


# ✅ CHANGE 8: Default welcome message send karne ka helper function
# Premium emoji ke saath — {MENTION} replace hone ke baad emoji ka offset calculate karta hai
async def _send_default_welcome(client, chat_id, user, chat, reply_markup=None, reply_to_message_id=None):
    """
    Default welcome message premium emoji ke saath send karta hai.
    
    Message: "Welcome {MENTION} Hope you have a great time here 👋"
    
    {MENTION} replace hone ke baad:
    - User ka mention entity add hoti hai
    - 👋 ki jagah premium custom emoji entity add hoti hai
    - Emoji ka offset dynamically calculate hota hai kyunki {MENTION} ka length variable hai
    """
    try:
        first_name = user.first_name or "User"
        mention_text = first_name  # mention ke andar sirf name dikhega

        # Final text build karo — {MENTION} ko naam se replace karo, 👋 rakho
        # "Welcome {MENTION} Hope you have a great time here 👋"
        base_before_mention = "Welcome "
        base_after_mention = " Hope you have a great time here 👋"

        final_text = base_before_mention + mention_text + base_after_mention

        # Entities build karo
        entities = []

        # 1. Mention entity — user ka naam clickable hoga
        mention_offset = len(base_before_mention.encode('utf-16-le')) // 2
        mention_length = len(mention_text.encode('utf-16-le')) // 2

        mention_entity = MessageEntity(
            type=MessageEntityType.TEXT_MENTION,
            offset=mention_offset,
            length=mention_length,
            user=user
        )
        entities.append(mention_entity)

        # 2. Premium emoji entity — 👋 ki jagah animated emoji
        # 👋 emoji ek character hai (UTF-16 mein 2 code units = length 2)
        emoji_char = "👋"
        emoji_utf16_length = len(emoji_char.encode('utf-16-le')) // 2  # = 2

        # Offset: base_before + mention + base_after mein 👋 se pehle ka hissa
        base_after_before_emoji = " Hope you have a great time here "
        emoji_offset = (
            len(base_before_mention.encode('utf-16-le')) // 2 +
            mention_length +
            len(base_after_before_emoji.encode('utf-16-le')) // 2
        )

        emoji_entity = MessageEntity(
            type=MessageEntityType.CUSTOM_EMOJI,
            offset=emoji_offset,
            length=emoji_utf16_length,
            custom_emoji_id=DEFAULT_WELCOME_EMOJI_ID
        )
        entities.append(emoji_entity)

        kwargs = {
            "chat_id": chat_id,
            "text": final_text,
            "entities": entities,
            "reply_markup": reply_markup
        }
        if reply_to_message_id:
            kwargs["reply_to_message_id"] = reply_to_message_id

        sent = await client.send_message(**kwargs)
        return sent

    except Exception as e:
        logger.error(f"Error sending default welcome: {e}")
        # Fallback — plain text
        try:
            first_name = user.first_name or "User"
            fallback_text = f"Welcome {first_name}! Hope you have a great time here 👋"
            kwargs = {"chat_id": chat_id, "text": fallback_text, "reply_markup": reply_markup}
            if reply_to_message_id:
                kwargs["reply_to_message_id"] = reply_to_message_id
            return await client.send_message(**kwargs)
        except Exception:
            return None


# ✅ CHANGE 9: Button parser jo entities ke saath kaam kare
# Original parse_buttons sirf text return karta tha, ye entities bhi adjust karta hai
def parse_buttons_with_entities(text, entities):
    """
    Text mein se [Text](URL) format ke buttons parse karta hai.
    Entities ko bhi adjust karta hai kyunki button syntax remove hone ke baad
    text ka length change ho jaata hai — offsets recalculate honge.
    
    Returns: (cleaned_text, button_rows, adjusted_entities, error)
    """
    import re
    from pyrogram_handlers.utils import validate_button

    BUTTON_PATTERN = re.compile(r'\[([^\]]+)\]\(([^\)]+)\)')
    PIPE_SEPARATOR = re.compile(r'\|')

    MAX_BUTTONS_TOTAL = 6
    MAX_BUTTONS_PER_ROW = 2

    button_rows = []
    total_buttons = 0
    error = None

    # Pehle check karo koi button syntax hai bhi ya nahi
    if not BUTTON_PATTERN.search(text):
        # Koi button nahi — text aur entities waise hi return karo
        return text, [], entities, None

    lines = text.split('\n')
    cleaned_lines = []
    # Track karo kitna text remove hua — entities adjust karne ke liye
    # Hum offset-based adjustment karenge
    removals = []  # list of (start_byte_offset, end_byte_offset) in original text

    current_pos = 0  # character position in original text

    for line in lines:
        line_start = current_pos
        has_button = BUTTON_PATTERN.search(line)

        if has_button:
            if '|' in line:
                parts = PIPE_SEPARATOR.split(line)
                row_buttons = []

                for part in parts:
                    matches = BUTTON_PATTERN.findall(part.strip())
                    for btn_text, btn_url in matches:
                        if total_buttons >= MAX_BUTTONS_TOTAL:
                            break
                        err = validate_button(btn_text, btn_url)
                        if err:
                            return None, None, None, err
                        row_buttons.append({"text": btn_text.strip(), "url": btn_url.strip()})
                        total_buttons += 1

                    if len(row_buttons) > MAX_BUTTONS_PER_ROW:
                        return None, None, None, f"Maximum {MAX_BUTTONS_PER_ROW} buttons per row allowed!"

                if row_buttons:
                    button_rows.append(row_buttons)
            else:
                matches = BUTTON_PATTERN.findall(line)
                for btn_text, btn_url in matches:
                    if total_buttons >= MAX_BUTTONS_TOTAL:
                        break
                    err = validate_button(btn_text, btn_url)
                    if err:
                        return None, None, None, err
                    button_rows.append([{"text": btn_text.strip(), "url": btn_url.strip()}])
                    total_buttons += 1

            # Is line ko cleaned text mein mat add karo (button syntax line thi)
            # Track karo yahan kya remove hua
            removals.append((line_start, line_start + len(line)))
        else:
            cleaned_lines.append(line)

        # +1 for newline character
        current_pos += len(line) + 1

    if total_buttons > MAX_BUTTONS_TOTAL:
        return None, None, None, f"Maximum {MAX_BUTTONS_TOTAL} buttons allowed!"

    cleaned_text = '\n'.join(cleaned_lines).strip()

    # Entities adjust karo — removed portions ke baad ke offsets shift honge
    adjusted_entities = []
    if entities:
        for entity in entities:
            ent_offset = entity.offset
            ent_end = entity.offset + entity.length

            # Check karo entity remove hone wale hisse mein toh nahi
            entity_removed = False
            shift = 0

            for rem_start, rem_end in removals:
                if ent_offset >= rem_start and ent_end <= rem_end + 1:
                    # Entity poori tarah removed portion mein hai
                    entity_removed = True
                    break
                elif ent_offset >= rem_end + 1:
                    # Entity removed portion ke baad hai — shift karo
                    shift += (rem_end - rem_start + 1)  # +1 for newline

            if not entity_removed:
                new_entity = MessageEntity(
                    type=entity.type,
                    offset=entity.offset - shift,
                    length=entity.length,
                    url=getattr(entity, 'url', None),
                    user=getattr(entity, 'user', None),
                    language=getattr(entity, 'language', None),
                    custom_emoji_id=getattr(entity, 'custom_emoji_id', None)
                )
                adjusted_entities.append(new_entity)

    return cleaned_text, button_rows, adjusted_entities, None

# ✅ SAFE ENTITIES CONVERTER — utils.py pe depend nahi karta
# Raw Pyrogram TL objects aur MessageEntity objects dono handle karta hai
def _safe_entities_to_dict(entities) -> list:
    """
    COMPLETE FIX: replied_msg.entities do tarah ke objects de sakta hai:
    1. Pyrogram MessageEntity objects (entity.type = MessageEntityType enum)
    2. Raw TL objects (MessageEntityBold, MessageEntityItalic etc.)
       - in mein .type nahi hota, class ka naam hi type hota hai
       - MessageEntityCustomEmoji mein .document_id hota hai

    Ye function dono cases handle karta hai.
    """
    if not entities:
        return []

    import logging as _logging
    _logger = _logging.getLogger(__name__)

    # Raw TL class name → standard type string mapping
    RAW_TYPE_MAP = {
        'MessageEntityBold':          'bold',
        'MessageEntityItalic':        'italic',
        'MessageEntityUnderline':     'underline',
        'MessageEntityStrike':        'strikethrough',
        'MessageEntitySpoiler':       'spoiler',
        'MessageEntityCode':          'code',
        'MessageEntityPre':           'pre',
        'MessageEntityBlockquote':    'blockquote',
        'MessageEntityTextUrl':       'text_link',
        'MessageEntityMentionName':   'text_mention',
        'MessageEntityCustomEmoji':   'custom_emoji',
        'MessageEntityMention':       'mention',
        'MessageEntityHashtag':       'hashtag',
        'MessageEntityCashtag':       'cashtag',
        'MessageEntityBotCommand':    'bot_command',
        'MessageEntityUrl':           'url',
        'MessageEntityEmail':         'email',
        'MessageEntityPhone':         'phone_number',
    }

    result = []
    for e in entities:
        try:
            class_name = type(e).__name__

            # ── Type string determine karo ──────────────────────────────
            if class_name in RAW_TYPE_MAP:
                # Raw TL object hai
                type_str = RAW_TYPE_MAP[class_name]
                offset   = int(e.offset)
                length   = int(e.length)
            elif hasattr(e, 'type'):
                # Pyrogram MessageEntity object hai
                etype = e.type
                if hasattr(etype, 'value'):
                    type_str = etype.value
                else:
                    type_str = str(etype)
                offset = int(e.offset)
                length = int(e.length)
            else:
                _logger.warning(f"Unknown entity class: {class_name}, skipping")
                continue

            d = {
                "type":   type_str,
                "offset": offset,
                "length": length,
            }

            # ── url (text_link / MessageEntityTextUrl) ──────────────────
            url = getattr(e, 'url', None)
            if url and isinstance(url, str):
                d["url"] = url

            # ── language (pre / MessageEntityPre) ──────────────────────
            lang = getattr(e, 'language', None)
            if lang and isinstance(lang, str):
                d["language"] = lang

            # ── user_id (text_mention / MessageEntityMentionName) ───────
            # Raw TL: e.user_id (int)
            # Pyrogram: e.user (User object)
            raw_user_id = getattr(e, 'user_id', None)
            user_obj    = getattr(e, 'user', None)

            if raw_user_id is not None:
                d["user_id"] = int(raw_user_id)
            elif user_obj is not None:
                try:
                    d["user_id"]         = int(user_obj.id)
                    d["user_first_name"] = str(user_obj.first_name or "")
                    d["user_last_name"]  = str(user_obj.last_name  or "")
                    d["user_username"]   = str(user_obj.username   or "")
                    d["user_is_bot"]     = bool(getattr(user_obj, 'is_bot', False))
                except Exception as ue:
                    _logger.warning(f"User extract error: {ue}")

            # ── custom_emoji_id (MessageEntityCustomEmoji) ──────────────
            # Raw TL: e.document_id (int)  ← MAIN FIX
            # Pyrogram MessageEntity: e.custom_emoji_id (str ya raw object)
            if class_name == 'MessageEntityCustomEmoji':
                # Raw TL object — .document_id directly int hai
                doc_id = getattr(e, 'document_id', None)
                if doc_id is not None:
                    d["custom_emoji_id"] = str(doc_id)
            else:
                raw_emoji = getattr(e, 'custom_emoji_id', None)
                if raw_emoji is not None:
                    if isinstance(raw_emoji, int):
                        d["custom_emoji_id"] = str(raw_emoji)
                    elif isinstance(raw_emoji, str):
                        d["custom_emoji_id"] = raw_emoji
                    elif hasattr(raw_emoji, 'document_id'):
                        d["custom_emoji_id"] = str(raw_emoji.document_id)

            result.append(d)

        except Exception as ex:
            _logger.warning(f"Entity skip ({type(e).__name__}): {ex}")
            continue

    return result
