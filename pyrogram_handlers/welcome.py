import re
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMemberUpdated, LinkPreviewOptions
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import ChatAdminRequired

from pyrogram_handlers.caching import get_admin_permissions
from utils.language import get_chat_lang_dict
from pyrogram_handlers.utils import (
    parse_buttons,
    create_button_markup,
    format_message_text,
    format_time,
    validate_text_length,
    validate_auto_delete_time,
    is_bot_admin,
    bot_can_delete_messages,
    get_cached_settings,
    update_cached_settings,
    clear_cached_settings,
    schedule_message_deletion,
    cancel_pending_deletions,
    check_join_flood,
    DEFAULT_AUTO_DELETE_SECONDS,
)
from mongo.managementdb import (
    get_welcome_settings, create_default_welcome_settings,
    update_welcome_status, set_custom_welcome,
    delete_custom_welcome, update_welcome_auto_delete
)

DEFAULT_WELCOME_TEXT = (
    ' Welcome {MENTION}! '
    'Hope you have a great time here <emoji id="5447432232698389583">👋</emoji> '
)

FILLING_MAP = {
    "ID": "ID", "NAME": "NAME", "SURNAME": "SURNAME",
    "NAMESURNAME": "NAMESURNAME", "DATE": "DATE", "TIME": "TIME",
    "MENTION": "MENTION", "USERNAME": "USERNAME", "GROUPNAME": "GROUPNAME",
}


def normalize_fillings(text: str) -> str:
    def replacer(match):
        key = match.group(1).upper()
        if key in FILLING_MAP:
            return "{" + FILLING_MAP[key] + "}"
        return match.group(0)
    return re.sub(r'\{(\w+)\}', replacer, text)


async def _check_admin(client: Client, chat_id: int, user_id: int) -> bool:
    perms = get_admin_permissions(chat_id, user_id)
    if perms is not None:
        return True
    try:
        from pyrogram.enums import ChatMembersFilter
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except ChatAdminRequired:
        try:
            from pyrogram.enums import ChatMembersFilter
            async for admin in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                if admin.user.id == user_id:
                    return True
            return False
        except Exception:
            return False
    except Exception:
        return False


async def _check_can_change_info(client: Client, chat_id: int, user_id: int) -> tuple:
    perms = get_admin_permissions(chat_id, user_id)
    if perms is not None:
        return True, perms["can_change_info"]
    try:
        from pyrogram.enums import ChatMembersFilter
        member = await client.get_chat_member(chat_id, user_id)
        if member.status == ChatMemberStatus.OWNER:
            return True, True
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return False, False
        can_change = bool(getattr(member.privileges, "can_change_info", False))
        return True, can_change
    except ChatAdminRequired:
        try:
            from pyrogram.enums import ChatMembersFilter
            async for admin in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                if admin.user.id == user_id:
                    can_change = bool(getattr(admin.privileges, "can_change_info", False))
                    return True, can_change
            return False, False
        except Exception:
            return False, False
    except Exception:
        return False, False


async def setup_welcome_handlers(client: Client):

    @client.on_message(filters.command("welcome") & filters.group)
    async def welcome_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        lang    = await get_chat_lang_dict(chat_id)

        is_admin, can_change_info = await _check_can_change_info(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text(lang["only_admins"], parse_mode=ParseMode.HTML)
            return

        command_parts = message.text.split(maxsplit=1)

        if len(command_parts) < 2:
            settings = await get_welcome_settings(chat_id)
            if not settings:
                await create_default_welcome_settings(chat_id)
                settings = await get_welcome_settings(chat_id)

            welcome_config = settings.get('welcome', {})
            is_enabled     = welcome_config.get('enabled', False)

            await message.reply_text(
                lang["welcome_status_enabled" if is_enabled else "welcome_status_disabled"],
                parse_mode=ParseMode.HTML
            )

            if is_enabled:
                text         = welcome_config['text'] if welcome_config.get('custom_set') and welcome_config.get('text') else DEFAULT_WELCOME_TEXT
                reply_markup = create_button_markup(welcome_config['buttons']) if welcome_config.get('buttons') else None

                if welcome_config.get('media_type') and welcome_config.get('media_id'):
                    media_type = welcome_config['media_type']
                    media_id   = welcome_config['media_id']
                    if media_type == "photo":
                        await message.reply_photo(photo=media_id, caption=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                    elif media_type == "video":
                        await message.reply_video(video=media_id, caption=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                    elif media_type == "animation":
                        await message.reply_animation(animation=media_id, caption=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                else:
                    await message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))
            return

        action = command_parts[1].lower()

        if action in ["on", "off"]:
            if not can_change_info:
                await message.reply_text(lang["need_change_info_perm"], parse_mode=ParseMode.HTML)
                return
            if not await is_bot_admin(client, chat_id):
                await message.reply_text(lang["promote_bot_admin"], parse_mode=ParseMode.HTML)
                return

        settings = await get_welcome_settings(chat_id)
        if not settings:
            await create_default_welcome_settings(chat_id)
            settings = await get_welcome_settings(chat_id)

        welcome_config = settings.get('welcome', {})

        if action == "on":
            if welcome_config.get('enabled'):
                await message.reply_text(lang["welcome_already_enabled"], parse_mode=ParseMode.HTML)
                return
            success = await update_welcome_status(chat_id, True)
            if success:
                settings = await get_welcome_settings(chat_id)
                await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                if welcome_config.get('custom_set'):
                    await message.reply_text(lang["welcome_enabled_custom"], parse_mode=ParseMode.HTML)
                else:
                    await message.reply_text(lang["welcome_enabled_default"], parse_mode=ParseMode.HTML)

        elif action == "off":
            if not welcome_config.get('enabled'):
                await message.reply_text(lang["welcome_already_disabled"], parse_mode=ParseMode.HTML)
                return
            success = await update_welcome_status(chat_id, False)
            if success:
                await clear_cached_settings(chat_id, 'welcome')
                await message.reply_text(lang["welcome_disabled"], parse_mode=ParseMode.HTML)

        else:
            await message.reply_text(lang["welcome_usage"], parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("setwelcome") & filters.group)
    async def setwelcome_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        lang    = await get_chat_lang_dict(chat_id)

        is_admin, can_change_info = await _check_can_change_info(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text(lang["only_admins"], parse_mode=ParseMode.HTML)
            return
        if not can_change_info:
            await message.reply_text(lang["need_change_info_perm"], parse_mode=ParseMode.HTML)
            return
        if not await is_bot_admin(client, chat_id):
            await message.reply_text(lang["promote_bot_admin"], parse_mode=ParseMode.HTML)
            return

        settings = await get_welcome_settings(chat_id)
        if not settings:
            await create_default_welcome_settings(chat_id)
            settings = await get_welcome_settings(chat_id)

        if settings.get('welcome', {}).get('custom_set'):
            await message.reply_text(lang["welcome_already_set"], parse_mode=ParseMode.HTML)
            return

        media_type = None
        media_id   = None
        text       = None

        if message.reply_to_message:
            replied_msg = message.reply_to_message
            if replied_msg.photo:
                media_type = "photo"
                media_id   = replied_msg.photo.file_id
                text       = replied_msg.caption.html if replied_msg.caption else ""
            elif replied_msg.video:
                media_type = "video"
                media_id   = replied_msg.video.file_id
                text       = replied_msg.caption.html if replied_msg.caption else ""
            elif replied_msg.animation:
                media_type = "animation"
                media_id   = replied_msg.animation.file_id
                text       = replied_msg.caption.html if replied_msg.caption else ""
            elif replied_msg.text:
                text = replied_msg.text.html
            else:
                await message.reply_text(lang["welcome_unsupported_media"], parse_mode=ParseMode.HTML)
                return
        else:
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await message.reply_text(lang["setwelcome_usage"], parse_mode=ParseMode.HTML)
                return
            text = parts[1].strip()

        if text:
            text = normalize_fillings(text)

        validation_error = validate_text_length(text, media_type is not None)
        if validation_error:
            await message.reply_text(validation_error, parse_mode=ParseMode.HTML)
            return

        button_rows = []
        if text:
            text, button_rows, error = parse_buttons(text)
            if error:
                await message.reply_text(
                    lang["welcome_button_error"].format(error=error),
                    parse_mode=ParseMode.HTML
                )
                return

        if not text or len(text.strip()) == 0:
            text = DEFAULT_WELCOME_TEXT

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
            await update_cached_settings(chat_id, 'welcome', settings['welcome'])
            await message.reply_text(lang["welcome_set_success"], parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(lang["welcome_set_failed"], parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("delwelcome") & filters.group)
    async def delwelcome_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        lang    = await get_chat_lang_dict(chat_id)

        is_admin, can_change_info = await _check_can_change_info(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text(lang["only_admins"], parse_mode=ParseMode.HTML)
            return
        if not can_change_info:
            await message.reply_text(lang["need_change_info_perm"], parse_mode=ParseMode.HTML)
            return

        settings = await get_welcome_settings(chat_id)
        if not settings:
            await message.reply_text(lang["no_welcome_settings"], parse_mode=ParseMode.HTML)
            return

        if not settings.get('welcome', {}).get('custom_set'):
            await message.reply_text(lang["no_custom_welcome"], parse_mode=ParseMode.HTML)
            return

        success = await delete_custom_welcome(chat_id)
        if success:
            await clear_cached_settings(chat_id, 'welcome')
            await message.reply_text(lang["welcome_deleted"], parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(lang["welcome_delete_failed"], parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("cleanwelcome") & filters.group)
    async def cleanwelcome_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        lang    = await get_chat_lang_dict(chat_id)

        is_admin, can_change_info = await _check_can_change_info(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text(lang["only_admins"], parse_mode=ParseMode.HTML)
            return
        if not can_change_info:
            await message.reply_text(lang["need_change_info_perm"], parse_mode=ParseMode.HTML)
            return

        command_parts = message.text.split()
        settings      = await get_welcome_settings(chat_id)
        if not settings:
            await create_default_welcome_settings(chat_id)
            settings = await get_welcome_settings(chat_id)

        if len(command_parts) == 1:
            auto_delete = settings.get('welcome', {}).get('auto_delete', {})
            is_enabled  = auto_delete.get('enabled', False)
            if is_enabled:
                delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
                await message.reply_text(
                    lang["autodelete_enabled"].format(time=format_time(delete_after)),
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(lang["autodelete_disabled"], parse_mode=ParseMode.HTML)
            return

        action = command_parts[1].lower()

        if action == "on":
            auto_delete = settings.get('welcome', {}).get('auto_delete', {})
            if auto_delete.get('enabled'):
                await message.reply_text(lang["autodelete_already_enabled"], parse_mode=ParseMode.HTML)
                return
            success = await update_welcome_auto_delete(chat_id, True, DEFAULT_AUTO_DELETE_SECONDS)
            if success:
                settings = await get_welcome_settings(chat_id)
                await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                await message.reply_text(
                    lang["autodelete_turned_on"].format(time=format_time(DEFAULT_AUTO_DELETE_SECONDS)),
                    parse_mode=ParseMode.HTML
                )

        elif action == "off":
            auto_delete = settings.get('welcome', {}).get('auto_delete', {})
            if not auto_delete.get('enabled'):
                await message.reply_text(lang["autodelete_already_disabled"], parse_mode=ParseMode.HTML)
                return
            success = await update_welcome_auto_delete(chat_id, False, None)
            if success:
                settings = await get_welcome_settings(chat_id)
                await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                await cancel_pending_deletions(chat_id, 'welcome')
                await message.reply_text(lang["autodelete_turned_off"], parse_mode=ParseMode.HTML)

        elif action.isdigit():
            delete_after     = int(action)
            validation_error = validate_auto_delete_time(delete_after)
            if validation_error:
                await message.reply_text(validation_error, parse_mode=ParseMode.HTML)
                return
            success = await update_welcome_auto_delete(chat_id, True, delete_after)
            if success:
                settings = await get_welcome_settings(chat_id)
                await update_cached_settings(chat_id, 'welcome', settings['welcome'])
                await message.reply_text(
                    lang["autodelete_time_updated"].format(time=format_time(delete_after)),
                    parse_mode=ParseMode.HTML
                )

        else:
            await message.reply_text(lang["cleanwelcome_usage"], parse_mode=ParseMode.HTML)


    @client.on_chat_member_updated(filters.group)
    async def welcome_new_member(client: Client, member_update: ChatMemberUpdated):
        if not member_update.new_chat_member:
            return

        old_status = member_update.old_chat_member.status if member_update.old_chat_member else None
        new_status = member_update.new_chat_member.status

        if new_status != ChatMemberStatus.MEMBER:
            return
        if old_status is not None and old_status not in {ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER}:
            return

        user = member_update.new_chat_member.user
        if not user or user.is_bot:
            return

        chat_id = member_update.chat.id

        is_flooding, _ = check_join_flood(chat_id)
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

        text         = welcome_config['text'] if welcome_config.get('custom_set') and welcome_config.get('text') else DEFAULT_WELCOME_TEXT
        formatted    = format_message_text(text, user, member_update.chat)
        reply_markup = create_button_markup(welcome_config['buttons']) if welcome_config.get('buttons') else None

        sent_message = None
        try:
            if welcome_config.get('media_type') and welcome_config.get('media_id'):
                media_type = welcome_config['media_type']
                media_id   = welcome_config['media_id']
                if media_type == "photo":
                    sent_message = await client.send_photo(chat_id=chat_id, photo=media_id, caption=formatted, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                elif media_type == "video":
                    sent_message = await client.send_video(chat_id=chat_id, video=media_id, caption=formatted, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                elif media_type == "animation":
                    sent_message = await client.send_animation(chat_id=chat_id, animation=media_id, caption=formatted, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            else:
                sent_message = await client.send_message(
                    chat_id=chat_id,
                    text=formatted,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
        except Exception:
            return

        auto_delete = welcome_config.get('auto_delete', {})
        if auto_delete.get('enabled') and sent_message:
            delete_after = auto_delete.get('delete_after', DEFAULT_AUTO_DELETE_SECONDS)
            can_delete   = await bot_can_delete_messages(client, chat_id)
            if can_delete:
                await schedule_message_deletion(sent_message, delete_after, chat_id, 'welcome')
