import logging
import re
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatPermissions
from pyrogram.enums import ParseMode
from pyrogram.errors import PeerIdInvalid

from pyrogram_handlers.caching import get_admin_permissions
from utils.language import get_chat_lang_dict
from mongo.managementdb import (
    get_user_warns, add_warn, remove_one_warn,
    reset_user_warns, get_warn_settings,
    set_warn_limit, set_warn_mode
)

logger = logging.getLogger(__name__)

DEFAULT_WARN_LIMIT = 3
DEFAULT_WARN_MODE  = "ban"

_warn_settings_cache: dict = {}


async def _get_cached_warn_settings(chat_id: int) -> dict:
    if chat_id not in _warn_settings_cache:
        settings = await get_warn_settings(chat_id)
        _warn_settings_cache[chat_id] = {
            "warn_limit": settings.get("warn_limit", DEFAULT_WARN_LIMIT),
            "warn_mode" : settings.get("warn_mode",  DEFAULT_WARN_MODE)
        }
    return _warn_settings_cache[chat_id]


def _update_settings_cache(chat_id: int, key: str, value):
    if chat_id not in _warn_settings_cache:
        _warn_settings_cache[chat_id] = {
            "warn_limit": DEFAULT_WARN_LIMIT,
            "warn_mode" : DEFAULT_WARN_MODE
        }
    _warn_settings_cache[chat_id][key] = value


def _check_admin(chat_id: int, user_id: int) -> bool:
    return get_admin_permissions(chat_id, user_id) is not None


async def _check_admin_with_fallback(client: Client, chat_id: int, user_id: int) -> bool:
    perms = get_admin_permissions(chat_id, user_id)
    if perms is not None:
        return True
    try:
        from pyrogram.enums import ChatMemberStatus, ChatMembersFilter
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        try:
            from pyrogram.enums import ChatMembersFilter
            async for admin in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                if admin.user.id == user_id:
                    return True
            return False
        except Exception:
            return False


async def _resolve_user(client: Client, message: Message):
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        if not user:
            return None, "reply_user_error"
        return user, None

    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        return None, None

    target = parts[1].strip()
    try:
        if target.startswith("@"):
            user = await client.get_users(target)
        elif target.lstrip("-").isdigit():
            user = await client.get_users(int(target))
        else:
            user = await client.get_users(target)
        return user, None
    except PeerIdInvalid:
        return None, f"user_not_found:{target}"
    except Exception:
        return None, f"user_not_found:{target}"


def _extract_reason(message: Message) -> str | None:
    parts = message.text.split(maxsplit=1)
    if message.reply_to_message:
        if len(parts) >= 2:
            reason_words = parts[1].strip().split()
            return " ".join(reason_words[:10]) if reason_words else None
    else:
        if len(parts) >= 2:
            after_cmd = parts[1].strip().split(maxsplit=1)
            if len(after_cmd) >= 2:
                reason_words = after_cmd[1].strip().split()
                return " ".join(reason_words[:10]) if reason_words else None
    return None


def _make_mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{name}</a>'


def _extract_reason_from_text(text: str) -> str | None:
    for prefix in ["Reason:", "Причина:", "အကြောင်းပြချက်:"]:
        match = re.search(rf'{prefix}\s*(.+?)(?:\n|$)', text)
        if match:
            return match.group(1).strip()
    return None


def _warn_buttons(chat_id: int, user_id: int, admin_id: int, warn_count: int, lang: dict) -> InlineKeyboardMarkup:
    cb_minus = f"warn_minus|{chat_id}|{user_id}|{admin_id}"
    cb_reset = f"warn_reset|{chat_id}|{user_id}|{admin_id}"
    cb_plus  = f"warn_plus|{chat_id}|{user_id}|{admin_id}"

    if warn_count <= 0:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("+1", callback_data=cb_plus)],
            [InlineKeyboardButton(lang["btn_close"], callback_data="warn_close")],
        ])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("-1",                        callback_data=cb_minus),
            InlineKeyboardButton(lang["btn_reset_all"],       callback_data=cb_reset),
            InlineKeyboardButton("+1",                        callback_data=cb_plus),
        ],
        [InlineKeyboardButton(lang["btn_close"], callback_data="warn_close")],
    ])


def _action_buttons(chat_id: int, user_id: int, mode: str, lang: dict) -> InlineKeyboardMarkup:
    if mode == "ban":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(lang["btn_unban"],  callback_data=f"warn_unban|{chat_id}|{user_id}"),
            InlineKeyboardButton(lang["btn_close"],  callback_data="warn_close"),
        ]])
    if mode == "mute":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(lang["btn_unmute"], callback_data=f"warn_unmute|{chat_id}|{user_id}"),
            InlineKeyboardButton(lang["btn_close"],  callback_data="warn_close"),
        ]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(lang["btn_close"], callback_data="warn_close"),
    ]])


async def _apply_warn_action(client: Client, chat_id: int, user_id: int, mode: str):
    try:
        if mode == "ban":
            await client.ban_chat_member(chat_id, user_id)
        elif mode == "kick":
            await client.ban_chat_member(chat_id, user_id)
            await client.unban_chat_member(chat_id, user_id)
        elif mode == "mute":
            await client.restrict_chat_member(
                chat_id, user_id,
                ChatPermissions(can_send_messages=False)
            )
    except Exception as e:
        logger.error(f"Failed to apply warn action {mode} on {user_id} in {chat_id}: {e}")


async def setup_warn_handlers(client: Client):

    @client.on_message(filters.command("warn") & filters.group)
    async def warn_command(client: Client, message: Message):
        chat_id  = message.chat.id
        admin_id = message.from_user.id if message.from_user else None
        lang     = await get_chat_lang_dict(chat_id)

        if not await _check_admin_with_fallback(client, chat_id, admin_id):
            await message.reply_text(lang["only_admins_warn"], parse_mode=ParseMode.HTML)
            return

        user, error = await _resolve_user(client, message)
        if error:
            if error == "reply_user_error":
                await message.reply_text(lang["reply_user_error"], parse_mode=ParseMode.HTML)
            elif error.startswith("user_not_found:"):
                target = error.split(":", 1)[1]
                await message.reply_text(lang["user_not_found"].format(target=target), parse_mode=ParseMode.HTML)
            return
        if not user:
            await message.reply_text(lang["warn_usage"], parse_mode=ParseMode.HTML)
            return
        if user.is_bot:
            await message.reply_text(lang["bots_cannot_be_warned"], parse_mode=ParseMode.HTML)
            return
        if _check_admin(chat_id, user.id):
            await message.reply_text(lang["admins_cannot_be_warned"], parse_mode=ParseMode.HTML)
            return

        reason     = _extract_reason(message)
        warn_data  = await add_warn(chat_id, user.id, reason)
        warn_count = warn_data["warns"]
        settings   = await _get_cached_warn_settings(chat_id)
        warn_limit = settings["warn_limit"]
        warn_mode  = settings["warn_mode"]

        admin_mention = _make_mention(message.from_user.id, message.from_user.first_name)
        user_mention  = _make_mention(user.id, user.first_name)

        if warn_limit > 0 and warn_count >= warn_limit:
            text = lang["warn_action_text"].format(
                user=user_mention,
                count=warn_count,
                limit=warn_limit,
                admin=admin_mention,
                reason=f"\n<b>{lang['warn_reason_label']}:</b> {reason}" if reason else "",
                mode=warn_mode
            )
            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=_action_buttons(chat_id, user.id, warn_mode, lang)
            )
            await reset_user_warns(chat_id, user.id)
            await _apply_warn_action(client, chat_id, user.id, warn_mode)
        else:
            text = lang["warn_text"].format(
                user=user_mention,
                count=warn_count,
                limit=warn_limit,
                admin=admin_mention,
                reason=f"\n<b>{lang['warn_reason_label']}:</b> {reason}" if reason else ""
            )
            text += f"\n\n{lang['warn_manage_hint']}"
            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=_warn_buttons(chat_id, user.id, admin_id, warn_count, lang)
            )


    @client.on_message(filters.command("warns") & filters.group)
    async def warns_command(client: Client, message: Message):
        chat_id = message.chat.id
        lang    = await get_chat_lang_dict(chat_id)

        user, error = await _resolve_user(client, message)
        if error:
            if error == "reply_user_error":
                await message.reply_text(lang["reply_user_error"], parse_mode=ParseMode.HTML)
            elif error.startswith("user_not_found:"):
                target = error.split(":", 1)[1]
                await message.reply_text(lang["user_not_found"].format(target=target), parse_mode=ParseMode.HTML)
            return
        if not user:
            await message.reply_text(lang["warns_usage"], parse_mode=ParseMode.HTML)
            return

        warn_data  = await get_user_warns(chat_id, user.id)
        warn_count = warn_data["warns"]
        reasons    = warn_data["reasons"]
        settings   = await _get_cached_warn_settings(chat_id)
        warn_limit = settings["warn_limit"]

        if warn_count == 0:
            await message.reply_text(
                lang["no_warnings"].format(user=user.mention),
                parse_mode=ParseMode.HTML
            )
            return

        reasons_text = (
            "\n".join([f"{i+1}. {r}" for i, r in enumerate(reasons)])
            if reasons else lang["reasons_not_specified"]
        )
        await message.reply_text(
            lang["warns_list"].format(
                count=warn_count,
                limit=warn_limit,
                reasons=reasons_text
            ),
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("rmwarn") & filters.group)
    async def rmwarn_command(client: Client, message: Message):
        chat_id  = message.chat.id
        admin_id = message.from_user.id if message.from_user else None
        lang     = await get_chat_lang_dict(chat_id)

        if not await _check_admin_with_fallback(client, chat_id, admin_id):
            await message.reply_text(lang["only_admins_rmwarn"], parse_mode=ParseMode.HTML)
            return

        user, error = await _resolve_user(client, message)
        if error:
            if error == "reply_user_error":
                await message.reply_text(lang["reply_user_error"], parse_mode=ParseMode.HTML)
            elif error.startswith("user_not_found:"):
                target = error.split(":", 1)[1]
                await message.reply_text(lang["user_not_found"].format(target=target), parse_mode=ParseMode.HTML)
            return
        if not user:
            await message.reply_text(lang["warns_usage"], parse_mode=ParseMode.HTML)
            return

        warn_data  = await remove_one_warn(chat_id, user.id)
        warn_count = warn_data["warns"]
        settings   = await _get_cached_warn_settings(chat_id)
        warn_limit = settings["warn_limit"]

        await message.reply_text(
            lang["rmwarn_success"].format(user=user.mention, count=warn_count, limit=warn_limit),
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("resetwarns") & filters.group)
    async def resetwarns_command(client: Client, message: Message):
        chat_id  = message.chat.id
        admin_id = message.from_user.id if message.from_user else None
        lang     = await get_chat_lang_dict(chat_id)

        if not await _check_admin_with_fallback(client, chat_id, admin_id):
            await message.reply_text(lang["only_admins_resetwarns"], parse_mode=ParseMode.HTML)
            return

        user, error = await _resolve_user(client, message)
        if error:
            if error == "reply_user_error":
                await message.reply_text(lang["reply_user_error"], parse_mode=ParseMode.HTML)
            elif error.startswith("user_not_found:"):
                target = error.split(":", 1)[1]
                await message.reply_text(lang["user_not_found"].format(target=target), parse_mode=ParseMode.HTML)
            return
        if not user:
            await message.reply_text(lang["warns_usage"], parse_mode=ParseMode.HTML)
            return

        await reset_user_warns(chat_id, user.id)
        await message.reply_text(
            lang["resetwarns_success"].format(user=user.mention),
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("warnlimit") & filters.group)
    async def warnlimit_command(client: Client, message: Message):
        chat_id  = message.chat.id
        admin_id = message.from_user.id if message.from_user else None
        lang     = await get_chat_lang_dict(chat_id)
        parts    = message.text.split(maxsplit=1)

        if len(parts) < 2:
            settings = await _get_cached_warn_settings(chat_id)
            limit    = settings["warn_limit"]
            if limit == 0:
                await message.reply_text(lang["warnlimit_disabled"], parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(lang["warnlimit_current"].format(limit=limit), parse_mode=ParseMode.HTML)
            return

        if not await _check_admin_with_fallback(client, chat_id, admin_id):
            await message.reply_text(lang["only_admins_warnlimit"], parse_mode=ParseMode.HTML)
            return

        try:
            limit = int(parts[1].strip())
            if limit < 0:
                raise ValueError
        except ValueError:
            await message.reply_text(lang["warnlimit_invalid"], parse_mode=ParseMode.HTML)
            return

        await set_warn_limit(chat_id, limit)
        _update_settings_cache(chat_id, "warn_limit", limit)

        if limit == 0:
            await message.reply_text(lang["warnlimit_set_zero"], parse_mode=ParseMode.HTML)
        else:
            await message.reply_text(lang["warnlimit_updated"].format(limit=limit), parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("warnmode") & filters.group)
    async def warnmode_command(client: Client, message: Message):
        chat_id  = message.chat.id
        admin_id = message.from_user.id if message.from_user else None
        lang     = await get_chat_lang_dict(chat_id)
        parts    = message.text.split(maxsplit=1)

        if len(parts) < 2:
            settings = await _get_cached_warn_settings(chat_id)
            mode     = settings["warn_mode"]
            mode_desc_key = f"warnmode_desc_{mode}"
            await message.reply_text(
                lang["warnmode_current"].format(
                    mode=mode.capitalize(),
                    desc=lang.get(mode_desc_key, "")
                ),
                parse_mode=ParseMode.HTML
            )
            return

        if not await _check_admin_with_fallback(client, chat_id, admin_id):
            await message.reply_text(lang["only_admins_warnmode"], parse_mode=ParseMode.HTML)
            return

        mode = parts[1].strip().lower()
        if mode not in ["ban", "mute", "kick"]:
            await message.reply_text(lang["warnmode_invalid"], parse_mode=ParseMode.HTML)
            return

        await set_warn_mode(chat_id, mode)
        _update_settings_cache(chat_id, "warn_mode", mode)
        mode_desc_key = f"warnmode_desc_{mode}"
        await message.reply_text(
            lang["warnmode_set"].format(
                mode=mode.capitalize(),
                desc=lang.get(mode_desc_key, "")
            ),
            parse_mode=ParseMode.HTML
        )


    @client.on_callback_query(filters.regex(r"^warn_"))
    async def warn_callback(client: Client, callback: CallbackQuery):
        caller_id = callback.from_user.id
        chat_id   = callback.message.chat.id
        lang      = await get_chat_lang_dict(chat_id)

        if not await _check_admin_with_fallback(client, chat_id, caller_id):
            await callback.answer(lang["cb_only_admins_warn"], show_alert=True)
            return

        data = callback.data

        if data == "warn_close":
            await callback.message.delete()
            await callback.answer()
            return

        parts = data.split("|")

        if parts[0] in ("warn_unban", "warn_unmute") and len(parts) == 3:
            action         = parts[0]
            target_chat_id = int(parts[1])
            target_user_id = int(parts[2])

            try:
                target_user  = await client.get_users(target_user_id)
                user_mention = _make_mention(target_user.id, target_user.first_name)
            except Exception:
                user_mention = f'<a href="tg://user?id={target_user_id}">User</a>'

            if action == "warn_unban":
                try:
                    await client.unban_chat_member(target_chat_id, target_user_id)
                    await callback.answer(lang["cb_user_unbanned"])
                    await callback.message.edit_text(
                        lang["warn_unbanned"].format(user=user_mention),
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(lang["btn_close"], callback_data="warn_close")
                        ]])
                    )
                except Exception as e:
                    await callback.answer(lang["cb_unban_failed"].format(error=e), show_alert=True)

            elif action == "warn_unmute":
                try:
                    await client.restrict_chat_member(
                        target_chat_id, target_user_id,
                        ChatPermissions(
                            can_send_messages=True,
                            can_send_media_messages=True,
                            can_send_other_messages=True,
                            can_add_web_page_previews=True
                        )
                    )
                    await callback.answer(lang["cb_user_unmuted"])
                    await callback.message.edit_text(
                        lang["warn_unmuted"].format(user=user_mention),
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(lang["btn_close"], callback_data="warn_close")
                        ]])
                    )
                except Exception as e:
                    await callback.answer(lang["cb_unmute_failed"].format(error=e), show_alert=True)
            return

        if len(parts) != 4:
            await callback.answer(lang["cb_invalid_button"], show_alert=True)
            return

        action            = parts[0]
        target_chat_id    = int(parts[1])
        target_user_id    = int(parts[2])
        original_admin_id = int(parts[3])

        settings   = await _get_cached_warn_settings(target_chat_id)
        warn_limit = settings["warn_limit"]
        warn_mode  = settings["warn_mode"]

        try:
            target_user  = await client.get_users(target_user_id)
            user_mention = _make_mention(target_user.id, target_user.first_name)
        except Exception:
            user_mention = f'<a href="tg://user?id={target_user_id}">User</a>'

        try:
            orig_admin    = await client.get_users(original_admin_id)
            admin_mention = _make_mention(orig_admin.id, orig_admin.first_name)
        except Exception:
            admin_mention = _make_mention(caller_id, callback.from_user.first_name)

        original_text   = callback.message.text or ""
        existing_reason = _extract_reason_from_text(original_text)

        if action == "warn_minus":
            warn_data  = await remove_one_warn(target_chat_id, target_user_id)
            warn_count = warn_data["warns"]
            await callback.answer(lang["cb_warn_removed"].format(count=warn_count, limit=warn_limit))

        elif action == "warn_plus":
            warn_data  = await add_warn(target_chat_id, target_user_id)
            warn_count = warn_data["warns"]

            if warn_limit > 0 and warn_count >= warn_limit:
                await callback.answer(lang["cb_limit_reached"].format(mode=warn_mode))
                try:
                    text = lang["warn_action_text"].format(
                        user=user_mention,
                        count=warn_count,
                        limit=warn_limit,
                        admin=admin_mention,
                        reason=f"\n<b>{lang['warn_reason_label']}:</b> {existing_reason}" if existing_reason else "",
                        mode=warn_mode
                    )
                    await callback.message.edit_text(
                        text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=_action_buttons(target_chat_id, target_user_id, warn_mode, lang)
                    )
                except Exception:
                    pass
                await reset_user_warns(target_chat_id, target_user_id)
                await _apply_warn_action(client, target_chat_id, target_user_id, warn_mode)
                return

            await callback.answer(lang["cb_warn_added"].format(count=warn_count, limit=warn_limit))

        elif action == "warn_reset":
            await reset_user_warns(target_chat_id, target_user_id)
            warn_count = 0
            await callback.answer(lang["cb_warns_reset"])

        else:
            return

        try:
            warn_data  = await get_user_warns(target_chat_id, target_user_id)
            warn_count = warn_data["warns"]
            new_text   = lang["warn_text"].format(
                user=user_mention,
                count=warn_count,
                limit=warn_limit,
                admin=admin_mention,
                reason=f"\n<b>{lang['warn_reason_label']}:</b> {existing_reason}" if existing_reason else ""
            )
            if warn_count > 0:
                new_text += f"\n\n{lang['warn_manage_hint']}"
            await callback.message.edit_text(
                new_text,
                parse_mode=ParseMode.HTML,
                reply_markup=_warn_buttons(target_chat_id, target_user_id, original_admin_id, warn_count, lang)
            )
        except Exception:
            pass

    logger.info("Warn handlers setup complete")
