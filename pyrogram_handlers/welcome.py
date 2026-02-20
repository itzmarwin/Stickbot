import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMemberUpdated, MessageEntity
from pyrogram.enums import ChatMemberStatus, ParseMode, MessageEntityType as MET
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
    check_join_flood,
    entities_to_list,
    list_to_entities,
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

DEFAULT_WELCOME_TEXT = '<emoji id="5447432232698389583">👋</emoji> Welcome {MENTION} Hope you have a great time here 👋.'


def _format_text_with_entities(raw_text: str, entities, user, chat):
    """
    Replace {MENTION}, {NAME} etc in plain text while shifting entity offsets correctly.
    Returns (formatted_text, adjusted_entities_or_None).
    """
    first_name = user.first_name or "User"
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    username = f"@{user.username}" if user.username else first_name
    group_name = chat.title or "Group"
    now = datetime.now()

    replacements = [
        ("{MENTION}", first_name),
        ("{NAME}", first_name),
        ("{SURNAME}", last_name),
        ("{NAMESURNAME}", full_name),
        ("{USERNAME}", username),
        ("{GROUPNAME}", group_name),
        ("{DATE}", now.strftime("%d-%m-%Y")),
        ("{TIME}", now.strftime("%H:%M")),
        ("{ID}", str(user.id)),
    ]

    result = raw_text
    ent_list = []
    if entities:
        for e in entities:
            ent_list.append({
                "type": e.type,
                "offset": e.offset,
                "length": e.length,
                "url": getattr(e, "url", None),
                "user": getattr(e, "user", None),
                "language": getattr(e, "language", None),
                "custom_emoji_id": getattr(e, "custom_emoji_id", None),
            })

    mention_positions = []

    for placeholder, value in replacements:
        if placeholder not in result:
            continue
        placeholder_len = len(placeholder)
        value_len = len(value)
        diff = value_len - placeholder_len
        search_start = 0
        while True:
            pos = result.find(placeholder, search_start)
            if pos == -1:
                break
            if placeholder == "{MENTION}":
                mention_positions.append(pos)
            for ent in ent_list:
                if ent["offset"] > pos:
                    ent["offset"] += diff
                elif ent["offset"] <= pos < ent["offset"] + ent["length"]:
                    ent["length"] += diff
            result = result[:pos] + value + result[pos + placeholder_len:]
            search_start = pos + value_len

    for pos in mention_positions:
        ent_list.append({
            "type": MET.TEXT_LINK,
            "offset": pos,
            "length": len(first_name),
            "url": f"tg://user?id={user.id}",
            "user": None,
            "language": None,
            "custom_emoji_id": None,
        })

    if not ent_list:
        return result, None

    final_entities = []
    for e in ent_list:
        try:
            final_entities.append(MessageEntity(
                type=e["type"],
                offset=e["offset"],
                length=e["length"],
                url=e["url"],
                user=e["user"],
                language=e["language"],
                custom_emoji_id=e["custom_emoji_id"],
            ))
        except Exception:
            pass

    return result, final_entities if final_entities else None


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
                    "<b>I need admin privileges to verify permissions.</b>\n\nPlease promote me to admin first.",
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

                if is_enabled:
                    reply_markup = None
                    if welcome_config.get('buttons'):
                        reply_markup = create_button_markup(welcome_config['buttons'])
                    try:
                        if welcome_config.get('custom_set') and welcome_config.get('text'):
                            raw_text = welcome_config['text']
                            saved_entities = welcome_config.get('entities', [])
                            msg_entities = list_to_entities(saved_entities) if saved_entities else None
                            if welcome_config.get('media_type') and welcome_config.get('media_id'):
                                media_type = welcome_config['media_type']
                                media_id = welcome_config['media_id']
                                if media_type == "photo":
                                    await message.reply_photo(photo=media_id, caption=raw_text, caption_entities=msg_entities, reply_markup=reply_markup)
                                elif media_type == "video":
                                    await message.reply_video(video=media_id, caption=raw_text, caption_entities=msg_entities, reply_markup=reply_markup)
                                elif media_type == "animation":
                                    await message.reply_animation(animation=media_id, caption=raw_text, caption_entities=msg_entities, reply_markup=reply_markup)
                            else:
                                if msg_entities:
                                    await message.reply_text(text=raw_text, entities=msg_entities, reply_markup=reply_markup, disable_web_page_preview=True)
                                else:
                                    await message.reply_text(text=raw_text, reply_markup=reply_markup, disable_web_page_preview=True)
                        else:
                            await message.reply_text(
                                text=DEFAULT_WELCOME_TEXT, reply_markup=reply_markup,
                                parse_mode=ParseMode.HTML, disable_web_page_preview=True
                            )
                    except BadRequest:
                        await message.reply_text("Preview unavailable (media may have expired)", parse_mode=ParseMode.HTML)
                return

            action = command_parts[1].lower()

            if action in ["on", "off"]:
                if not await is_bot_admin(client, chat_id):
                    await message.reply_text("<b>Please promote me to admin to enable welcome messages.</b>", parse_mode=ParseMode.HTML)
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
                        await message.reply_text("<b>Welcome enabled!</b>\n\nCustom welcome message will be sent to new members.", parse_mode=ParseMode.HTML)
                    else:
                        await message.reply_text(
                            "<b>Welcome enabled.</b>\n\nDefault welcome message will be sent to new members.\n"
                            "Use <code>/setwelcome</code> to set a custom message.", parse_mode=ParseMode.HTML
                        )

            elif action == "off":
                if not welcome_config.get('enabled'):
                    await message.reply_text("Welcome is already disabled.", parse_mode=ParseMode.HTML)
                    return
                success = await update_welcome_status(chat_id, False)
                if success:
                    await clear_cached_settings(chat_id, 'welcome')
                    await message.reply_text("<b>Welcome disabled.</b>", parse_mode=ParseMode.HTML)

            else:
                await message.reply_text("Use <code>/welcome on</code> or <code>/welcome off</code>", parse_mode=ParseMode.HTML)

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
                await message.reply_text("<b>I need admin privileges to verify permissions.</b>\n\nPlease promote me to admin first.", parse_mode=ParseMode.HTML)
                return
            except Exception:
                await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                return

            if not await is_bot_admin(client, chat_id):
                await message.reply_text("<b>Please promote the bot to admin first.</b>", parse_mode=ParseMode.HTML)
                return

            if not message.reply_to_message:
                await message.reply_text("<b>Please reply to a message.</b>", parse_mode=ParseMode.HTML)
                return

            settings = await get_welcome_settings(chat_id)
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)

            if settings.get('welcome', {}).get('custom_set'):
                await message.reply_text(
                    "<b>Welcome message already set.</b>\n\nUse <code>/delwelcome</code> first to remove it.",
                    parse_mode=ParseMode.HTML
                )
                return

            replied_msg = message.reply_to_message
            media_type = None
            media_id = None
            text = None
            raw_entities = []

            if replied_msg.photo:
                media_type = "photo"
                media_id = replied_msg.photo.file_id
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
                text = replied_msg.text
                raw_entities = replied_msg.entities or []
            else:
                await message.reply_text("<b>Unsupported message type.</b>\n\nSupported: Photo, Video, GIF, Text", parse_mode=ParseMode.HTML)
                return

            is_caption = media_type is not None
            validation_error = validate_text_length(text, is_caption)
            if validation_error:
                await message.reply_text(f"{validation_error}", parse_mode=ParseMode.HTML)
                return

            entities_list = entities_to_list(raw_entities)

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
                text = DEFAULT_WELCOME_TEXT
                entities_list = []

            success = await set_custom_welcome(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                entities=entities_list,
                buttons=button_rows
            )

            if success:
                await update_welcome_status(chat_id, True)
                settings = await get_welcome_settings(chat_id)
                await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                await message.reply_text("<b>Welcome message set successfully.</b>\n\nWelcome is now <b>enabled</b>.", parse_mode=ParseMode.HTML)
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
                await message.reply_text("<b>I need admin privileges to verify permissions.</b>\n\nPlease promote me to admin first.", parse_mode=ParseMode.HTML)
                return
            except Exception:
                await message.reply_text("Only admins can use this command!", parse_mode=ParseMode.HTML)
                return

            settings = await get_welcome_settings(chat_id)
            if not settings:
                await message.reply_text("No welcome settings found for this group.", parse_mode=ParseMode.HTML)
                return

            if not settings.get('welcome', {}).get('custom_set'):
                await message.reply_text("<b>No custom welcome message set.</b>\n\nUse <code>/setwelcome</code> to set a custom message.", parse_mode=ParseMode.HTML)
                return

            success = await delete_custom_welcome(chat_id)
            if success:
                await clear_cached_settings(chat_id, 'welcome')
                await message.reply_text(
                    "<b>Custom welcome message deleted successfully.</b>\n\n"
                    "Welcome is now <b>disabled</b>.\nUse <code>/welcome on</code> to enable default message.",
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
                await message.reply_text("<b>I need admin privileges to verify permissions.</b>\n\nPlease promote me to admin first.", parse_mode=ParseMode.HTML)
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
                    await message.reply_text(f"<b>Auto-delete is enabled</b>\n\nWelcome messages will be deleted after: <b>{time_str}</b>", parse_mode=ParseMode.HTML)
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
                    await message.reply_text(f"<b>Auto-delete enabled</b>\n\nWelcome messages will be deleted after: <b>{format_time(DEFAULT_AUTO_DELETE_SECONDS)}</b>", parse_mode=ParseMode.HTML)

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
                    await message.reply_text(f"<b>Auto-delete time updated</b>\n\nWelcome messages will be deleted after: <b>{time_str}</b>", parse_mode=ParseMode.HTML)

            else:
                await message.reply_text("Use <code>/cleanwelcome on</code> or <code>/cleanwelcome off</code>", parse_mode=ParseMode.HTML)

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
                    raw_text = welcome_config['text']
                    saved_entities = welcome_config.get('entities', [])
                    msg_entities = list_to_entities(saved_entities) if saved_entities else None

                    formatted_text, formatted_entities = _format_text_with_entities(
                        raw_text, msg_entities, user, member_update.chat
                    )

                    if welcome_config.get('media_type') and welcome_config.get('media_id'):
                        media_type = welcome_config['media_type']
                        media_id = welcome_config['media_id']
                        if media_type == "photo":
                            sent_message = await client.send_photo(
                                chat_id=chat_id, photo=media_id,
                                caption=formatted_text, caption_entities=formatted_entities,
                                reply_markup=reply_markup
                            )
                        elif media_type == "video":
                            sent_message = await client.send_video(
                                chat_id=chat_id, video=media_id,
                                caption=formatted_text, caption_entities=formatted_entities,
                                reply_markup=reply_markup
                            )
                        elif media_type == "animation":
                            sent_message = await client.send_animation(
                                chat_id=chat_id, animation=media_id,
                                caption=formatted_text, caption_entities=formatted_entities,
                                reply_markup=reply_markup
                            )
                    else:
                        sent_message = await client.send_message(
                            chat_id=chat_id,
                            text=formatted_text,
                            entities=formatted_entities,
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                else:
                    formatted_text = format_message_text(DEFAULT_WELCOME_TEXT, user, member_update.chat)
                    sent_message = await client.send_message(
                        chat_id=chat_id,
                        text=formatted_text,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
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
