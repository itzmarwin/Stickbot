import logging
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Tuple
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMemberUpdated, MessageEntity
from pyrogram.enums import ChatMemberStatus, ParseMode, MessageEntityType
from pyrogram.errors import ChatAdminRequired, MessageDeleteForbidden, BadRequest, FloodWait

from pyrogram_handlers.utils import (
    parse_buttons,
    create_button_markup,
    format_message_text,
    format_message_text_with_entities,
    entities_to_dict,
    dict_to_entities,
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

def _adjust_entities_after_text_change(
    original_text: str,
    new_text: str,
    entities: List[Dict]
) -> List[Dict]:
    """
    parse_buttons() text se button patterns remove karta hai.
    Jab text shorten hota hai, remaining entities ke offsets shift ho jaate hain.

    Approach: SequenceMatcher se original aur cleaned text ka position mapping banao,
    phir har entity ka offset aur length adjust karo.
    """
    if not entities or original_text == new_text:
        return entities

    # Position mapping: original_pos → new_pos
    # Sirf 'equal' blocks map hote hain (removed chars ka koi mapping nahi)
    mapping: Dict[int, int] = {}
    sm = SequenceMatcher(None, original_text, new_text, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            for k in range(i2 - i1):
                mapping[i1 + k] = j1 + k

    adjusted = []
    for ent in entities:
        old_start = ent["offset"]
        old_end   = old_start + ent["length"]

        # Entity ka new start: original position ka mapped position
        # Agar exact position remove ho gayi, next available mapped position lo
        new_start = None
        for pos in range(old_start, old_end + 1):
            if pos in mapping:
                new_start = mapping[pos]
                break

        if new_start is None:
            # Puri entity remove ho gayi (was inside button pattern) — skip
            continue

        # Entity ka new end
        new_end = None
        for pos in range(old_end, old_start - 1, -1):
            if pos in mapping:
                new_end = mapping[pos]
                break

        if new_end is None or new_end <= new_start:
            # Length 0 ho gayi — skip
            continue

        new_ent = dict(ent)
        new_ent["offset"] = new_start
        new_ent["length"] = new_end - new_start
        adjusted.append(new_ent)

    return adjusted


# ---------------------------------------------------------------------------
# HANDLERS
# ---------------------------------------------------------------------------

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
                # Status + preview
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
                            # Custom welcome — entities ke saath bhejo
                            preview_text = welcome_config['text']
                            stored_entities = welcome_config.get('entities', [])
                            # Preview mein from_user use karo as sample
                            sample_text, sample_entities = format_message_text_with_entities(
                                preview_text, stored_entities, message.from_user, message.chat
                            )

                            if welcome_config.get('media_type') and welcome_config.get('media_id'):
                                media_type = welcome_config['media_type']
                                media_id   = welcome_config['media_id']
                                if media_type == "photo":
                                    await message.reply_photo(
                                        photo=media_id, caption=sample_text,
                                        caption_entities=sample_entities, reply_markup=reply_markup
                                    )
                                elif media_type == "video":
                                    await message.reply_video(
                                        video=media_id, caption=sample_text,
                                        caption_entities=sample_entities, reply_markup=reply_markup
                                    )
                                elif media_type == "animation":
                                    await message.reply_animation(
                                        animation=media_id, caption=sample_text,
                                        caption_entities=sample_entities, reply_markup=reply_markup
                                    )
                            else:
                                await message.reply_text(
                                    text=sample_text,
                                    entities=sample_entities,
                                    reply_markup=reply_markup,
                                    disable_web_page_preview=True
                                )

                        else:
                            # Default welcome — premium emoji ke saath
                            sample_text, sample_entities = format_message_text_with_entities(
                                DEFAULT_WELCOME_TEXT,
                                DEFAULT_WELCOME_ENTITIES_RAW,
                                message.from_user,
                                message.chat
                            )
                            await message.reply_text(
                                text=sample_text,
                                entities=sample_entities,
                                reply_markup=reply_markup,
                                disable_web_page_preview=True
                            )

                    except BadRequest:
                        await message.reply_text(
                            "Preview unavailable (media may have expired)",
                            parse_mode=ParseMode.HTML
                        )

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
                    await message.reply_text("Welcome is already enabled.", parse_mode=ParseMode.HTML)
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
                    await message.reply_text("<b>Welcome disabled.</b>", parse_mode=ParseMode.HTML)

            else:
                await message.reply_text(
                    "Use <code>/welcome on</code> or <code>/welcome off</code>",
                    parse_mode=ParseMode.HTML
                )

        except FloodWait as e:
            await message.reply_text(
                f"⏳ Please wait {e.value} seconds before trying again.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            log_error("welcome_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text(
                "An error occurred. Please try again shortly.",
                parse_mode=ParseMode.HTML
            )


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
                await message.reply_text(
                    "<b>Please promote the bot to admin first.</b>",
                    parse_mode=ParseMode.HTML
                )
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
            media_id   = None
            text       = None
            raw_entities = []   # Pyrogram MessageEntity list replied message se

            if replied_msg.photo:
                media_type   = "photo"
                media_id     = replied_msg.photo.file_id
                text         = replied_msg.caption or ""
                raw_entities = replied_msg.caption_entities or []
            elif replied_msg.video:
                media_type   = "video"
                media_id     = replied_msg.video.file_id
                text         = replied_msg.caption or ""
                raw_entities = replied_msg.caption_entities or []
            elif replied_msg.animation:
                media_type   = "animation"
                media_id     = replied_msg.animation.file_id
                text         = replied_msg.caption or ""
                raw_entities = replied_msg.caption_entities or []
            elif replied_msg.text:
                text         = replied_msg.text
                raw_entities = replied_msg.entities or []
            else:
                await message.reply_text(
                    "<b>Unsupported message type.</b>\n\n"
                    "Supported: Text, Photo, Video, GIF",
                    parse_mode=ParseMode.HTML
                )
                return

            # --- Text length validation ---
            is_caption = media_type is not None
            validation_error = validate_text_length(text, is_caption)
            if validation_error:
                await message.reply_text(validation_error, parse_mode=ParseMode.HTML)
                return

            # --- Entities ko dict mein convert karo (DB ke liye) ---
            # Bold, italic, underline, strikethrough, spoiler, code, pre,
            # text_link (word pe link), custom_emoji (premium emoji) — sab save hoga
            entities_dict = entities_to_dict(raw_entities)

            # --- Button patterns extract karo ---
            button_rows = []
            if text:
                original_text = text
                text, button_rows, error = parse_buttons(text)

                if error:
                    await message.reply_text(
                        f"<b>Button Error:</b> {error}\n\n"
                        "<b>Format:</b> <code>[Text](URL)</code>\n"
                        "<b>Multiple:</b> <code>[Btn1](url) | [Btn2](url)</code>",
                        parse_mode=ParseMode.HTML
                    )
                    return

                # Button removal ke baad entity offsets adjust karo
                if original_text != text and entities_dict:
                    entities_dict = _adjust_entities_after_text_change(
                        original_text, text, entities_dict
                    )

            if not text or len(text.strip()) == 0:
                text = "Hey {MENTION}!\nWelcome to {GROUPNAME}!"

            # --- DB mein save karo ---
            success = await set_custom_welcome(
                chat_id=chat_id,
                media_type=media_type,
                media_id=media_id,
                text=text,
                buttons=button_rows,
                entities=entities_dict      # ← formatting + premium emoji
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
                await message.reply_text(
                    "Failed to set welcome message. Please try again.",
                    parse_mode=ParseMode.HTML
                )

        except Exception as e:
            log_error("setwelcome_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text(
                "Please try again later. If it still doesn't work, contact the support group.",
                parse_mode=ParseMode.HTML
            )


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
                await message.reply_text(
                    "No welcome settings found for this group.",
                    parse_mode=ParseMode.HTML
                )
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
                await message.reply_text(
                    "Failed to delete welcome message. Please try again.",
                    parse_mode=ParseMode.HTML
                )

        except Exception as e:
            log_error("delwelcome_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text(
                "Please try again later. If it still doesn't work, contact the support group.",
                parse_mode=ParseMode.HTML
            )


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
                    await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                    return
            except ChatAdminRequired:
                await message.reply_text(
                    "<b>I need admin privileges to verify permissions.</b>\n\n"
                    "Please promote me to admin first.",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception:
                await message.reply_text("Only admins can use this command.", parse_mode=ParseMode.HTML)
                return

            command_parts = message.text.split()
            settings = await get_welcome_settings(chat_id)
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)

            if len(command_parts) == 1:
                auto_delete = settings.get('welcome', {}).get('auto_delete', {})
                is_enabled  = auto_delete.get('enabled', False)
                if is_enabled:
                    delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
                    await message.reply_text(
                        f"<b>Auto-delete is enabled</b>\n\n"
                        f"Welcome messages will be deleted after: <b>{format_time(delete_after)}</b>",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await message.reply_text("<b>Auto-delete is disabled</b>", parse_mode=ParseMode.HTML)
                return

            action = command_parts[1].lower()

            if action == "on":
                auto_delete = settings.get('welcome', {}).get('auto_delete', {})
                if auto_delete.get('enabled'):
                    await message.reply_text("Auto-delete is already enabled.", parse_mode=ParseMode.HTML)
                    return

                success = await update_welcome_auto_delete(chat_id, True, DEFAULT_AUTO_DELETE_SECONDS)
                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                    await message.reply_text(
                        f"<b>Auto-delete enabled</b>\n\n"
                        f"Welcome messages will be deleted after: "
                        f"<b>{format_time(DEFAULT_AUTO_DELETE_SECONDS)}</b>",
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
                    await message.reply_text(validation_error, parse_mode=ParseMode.HTML)
                    return

                success = await update_welcome_auto_delete(chat_id, True, delete_after)
                if success:
                    settings = await get_welcome_settings(chat_id)
                    await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                    await message.reply_text(
                        f"<b>Auto-delete time updated</b>\n\n"
                        f"Welcome messages will be deleted after: <b>{format_time(delete_after)}</b>",
                        parse_mode=ParseMode.HTML
                    )

            else:
                await message.reply_text(
                    "Use <code>/cleanwelcome on</code> or <code>/cleanwelcome off</code>",
                    parse_mode=ParseMode.HTML
                )

        except Exception as e:
            log_error("cleanwelcome_command", e, chat_id=chat_id or 0, user_id=user_id or 0)
            await message.reply_text(
                "Please try again later. If it still doesn't work, contact the support group.",
                parse_mode=ParseMode.HTML
            )


    @client.on_chat_member_updated(filters.group)
    async def welcome_new_member(client: Client, member_update: ChatMemberUpdated):
        try:
            # Check 1: Must have new_chat_member
            if not member_update.new_chat_member:
                return

            # Check 2: Prevent false welcome on unban/kick
            if member_update.old_chat_member:
                old_status = member_update.old_chat_member.status
                if old_status in {
                    ChatMemberStatus.BANNED,
                    ChatMemberStatus.LEFT,
                    ChatMemberStatus.RESTRICTED
                }:
                    return
                return

            # Check 3: New status must be member
            new_status = member_update.new_chat_member.status
            if new_status in {
                ChatMemberStatus.BANNED,
                ChatMemberStatus.LEFT,
                ChatMemberStatus.RESTRICTED
            }:
                return

            if new_status != ChatMemberStatus.MEMBER:
                return

            user    = member_update.new_chat_member.user
            chat_id = member_update.chat.id

            if not user or user.is_bot:
                return

            # Silent flood check
            is_flooding, _ = check_join_flood(chat_id)
            if is_flooding:
                return

            # Settings load karo (cache-first)
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

            # --- Text aur entities prepare karo ---
            reply_markup = None
            if welcome_config.get('buttons'):
                reply_markup = create_button_markup(welcome_config['buttons'])

            sent_message = None

            try:
                if welcome_config.get('custom_set') and welcome_config.get('text'):
                    # ── Custom welcome — stored entities ke saath ──
                    raw_text       = welcome_config['text']
                    stored_entities = welcome_config.get('entities', [])

                    formatted_text, pyrogram_entities = format_message_text_with_entities(
                        raw_text, stored_entities, user, member_update.chat
                    )

                    if welcome_config.get('media_type') and welcome_config.get('media_id'):
                        media_type = welcome_config['media_type']
                        media_id   = welcome_config['media_id']

                        if media_type == "photo":
                            sent_message = await client.send_photo(
                                chat_id=chat_id,
                                photo=media_id,
                                caption=formatted_text,
                                caption_entities=pyrogram_entities,
                                reply_markup=reply_markup
                            )
                        elif media_type == "video":
                            sent_message = await client.send_video(
                                chat_id=chat_id,
                                video=media_id,
                                caption=formatted_text,
                                caption_entities=pyrogram_entities,
                                reply_markup=reply_markup
                            )
                        elif media_type == "animation":
                            sent_message = await client.send_animation(
                                chat_id=chat_id,
                                animation=media_id,
                                caption=formatted_text,
                                caption_entities=pyrogram_entities,
                                reply_markup=reply_markup
                            )
                    else:
                        sent_message = await client.send_message(
                            chat_id=chat_id,
                            text=formatted_text,
                            entities=pyrogram_entities,
                            reply_markup=reply_markup,
                            disable_web_page_preview=True   # ← word pe link se group preview nahi
                        )

                else:
                    # ── Default welcome — premium emoji ke saath ──
                    formatted_text, pyrogram_entities = format_message_text_with_entities(
                        DEFAULT_WELCOME_TEXT,
                        DEFAULT_WELCOME_ENTITIES_RAW,
                        user,
                        member_update.chat
                    )
                    sent_message = await client.send_message(
                        chat_id=chat_id,
                        text=formatted_text,
                        entities=pyrogram_entities,
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )

                # Auto-delete schedule karo
                auto_delete = welcome_config.get('auto_delete', {})
                if auto_delete.get('enabled') and sent_message:
                    delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
                    if await bot_can_delete_messages(client, chat_id):
                        await schedule_message_deletion(sent_message, delete_after, chat_id, 'welcome')

            except (BadRequest, MessageDeleteForbidden, FloodWait):
                pass
            except Exception as send_error:
                log_error("Send welcome failed", send_error, chat_id=chat_id)

        except Exception as e:
            log_error("welcome_new_member", e, chat_id=member_update.chat.id)

    logger.info("✅ Welcome handlers setup complete")
