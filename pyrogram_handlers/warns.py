import logging
import re
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatPermissions
from pyrogram.enums import ParseMode
from pyrogram.errors import PeerIdInvalid

from pyrogram_handlers.utils import is_user_admin
from database_management import (
    get_user_warns,
    add_warn,
    remove_one_warn,
    reset_user_warns,
    get_warn_settings,
    set_warn_limit,
    set_warn_mode
)

logger = logging.getLogger(__name__)

DEFAULT_WARN_LIMIT = 3
DEFAULT_WARN_MODE = "ban"

_warn_settings_cache: dict = {}


async def _get_cached_warn_settings(chat_id: int) -> dict:
    if chat_id not in _warn_settings_cache:
        settings = await get_warn_settings(chat_id)
        _warn_settings_cache[chat_id] = {
            "warn_limit": settings.get("warn_limit", DEFAULT_WARN_LIMIT),
            "warn_mode": settings.get("warn_mode", DEFAULT_WARN_MODE)
        }
    return _warn_settings_cache[chat_id]


def _update_settings_cache(chat_id: int, key: str, value):
    if chat_id not in _warn_settings_cache:
        _warn_settings_cache[chat_id] = {
            "warn_limit": DEFAULT_WARN_LIMIT,
            "warn_mode": DEFAULT_WARN_MODE
        }
    _warn_settings_cache[chat_id][key] = value


async def _resolve_user(client: Client, message: Message):
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        if not user:
            return None, "Could not get user from replied message."
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
        return None, f"User <code>{target}</code> not found."
    except Exception:
        return None, f"Could not find user <code>{target}</code>."


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


def _make_user_mention(user_id: int, user_name: str) -> str:
    """Hamesha consistent clickable mention banao"""
    return f'<a href="tg://user?id={user_id}">{user_name}</a>'


def _extract_reason_from_text(text: str) -> str | None:
    """
    Plain text message se reason extract karo
    'Reason: ...' pattern dhundho
    """
    match = re.search(r'Reason:\s*(.+?)(?:\n|$)', text)
    if match:
        return match.group(1).strip()
    return None


def _extract_admin_mention_from_text(text: str) -> str | None:
    """
    Plain text message se admin mention extract karo
    'from admin NAME.' pattern dhundho
    """
    match = re.search(r'from admin (.+?)\.', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


# FIX: Warn buttons — 0 warns pe sirf +1 aur Close
def _warn_buttons(chat_id: int, user_id: int, warn_count: int = 1) -> InlineKeyboardMarkup:
    if warn_count <= 0:
        # 0 warns — sirf +1 aur Close
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("+1", callback_data=f"warn_plus|{chat_id}|{user_id}"),
            ],
            [
                InlineKeyboardButton("Close", callback_data="warn_close"),
            ]
        ])
    else:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("-1", callback_data=f"warn_minus|{chat_id}|{user_id}"),
                InlineKeyboardButton("Reset All", callback_data=f"warn_reset|{chat_id}|{user_id}"),
                InlineKeyboardButton("+1", callback_data=f"warn_plus|{chat_id}|{user_id}"),
            ],
            [
                InlineKeyboardButton("Close", callback_data="warn_close"),
            ]
        ])


def _action_buttons(chat_id: int, user_id: int, mode: str) -> InlineKeyboardMarkup:
    if mode == "ban":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Unban", callback_data=f"warn_unban|{chat_id}|{user_id}"),
            InlineKeyboardButton("Close", callback_data="warn_close"),
        ]])
    elif mode == "mute":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Unmute", callback_data=f"warn_unmute|{chat_id}|{user_id}"),
            InlineKeyboardButton("Close", callback_data="warn_close"),
        ]])
    else:  # kick
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Close", callback_data="warn_close"),
        ]])


def _warn_text(user_mention: str, warn_count: int, warn_limit: int, admin_mention: str, reason: str = None) -> str:
    text = (
        f"{user_mention} has received a warning "
        f"(<b>{warn_count}/{warn_limit}</b>) "
        f"from admin {admin_mention}."
    )
    if reason:
        text += f"\n<b>Reason:</b> {reason}"
    return text


def _action_text(user_mention: str, warn_count: int, warn_limit: int, admin_mention: str, mode: str, reason: str = None) -> str:
    text = (
        f"{user_mention} has received a warning "
        f"(<b>{warn_count}/{warn_limit}</b>) "
        f"from admin {admin_mention}."
    )
    if reason:
        text += f"\n<b>Reason:</b> {reason}"
    text += f"\n\nWarning limit reached! Applying action: <b>{mode}</b>."
    return text


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
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if not await is_user_admin(client, chat_id, admin_id):
            await message.reply_text("Only admins can warn users.", parse_mode=ParseMode.HTML)
            return

        user, error = await _resolve_user(client, message)

        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return

        if not user:
            await message.reply_text(
                "Mention a user, reply to their message, or provide their user ID.\n"
                "<code>/warn @username reason</code>",
                parse_mode=ParseMode.HTML
            )
            return

        if user.is_bot:
            await message.reply_text("Bots cannot be warned.", parse_mode=ParseMode.HTML)
            return

        if await is_user_admin(client, chat_id, user.id):
            await message.reply_text("Admins cannot be warned.", parse_mode=ParseMode.HTML)
            return

        reason = _extract_reason(message)

        warn_data = await add_warn(chat_id, user.id, reason)
        warn_count = warn_data["warns"]

        settings = await _get_cached_warn_settings(chat_id)
        warn_limit = settings["warn_limit"]
        warn_mode = settings["warn_mode"]

        admin_mention = message.from_user.mention if message.from_user else "Admin"
        # FIX: Hamesha consistent mention banao
        user_mention = _make_user_mention(user.id, user.first_name)

        if warn_limit > 0 and warn_count >= warn_limit:
            await message.reply_text(
                _action_text(user_mention, warn_count, warn_limit, admin_mention, warn_mode, reason),
                parse_mode=ParseMode.HTML,
                reply_markup=_action_buttons(chat_id, user.id, warn_mode)
            )
            await reset_user_warns(chat_id, user.id)
            await _apply_warn_action(client, chat_id, user.id, warn_mode)
        else:
            text = _warn_text(user_mention, warn_count, warn_limit, admin_mention, reason)
            text += "\n\nReply to this message to manage warnings or apply additional actions."
            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=_warn_buttons(chat_id, user.id, warn_count)
            )


    @client.on_message(filters.command("warns") & filters.group)
    async def warns_command(client: Client, message: Message):
        chat_id = message.chat.id

        user, error = await _resolve_user(client, message)

        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return

        if not user:
            await message.reply_text(
                "Mention a user, reply to their message, or provide their user ID.",
                parse_mode=ParseMode.HTML
            )
            return

        warn_data = await get_user_warns(chat_id, user.id)
        warn_count = warn_data["warns"]
        reasons = warn_data["reasons"]

        settings = await _get_cached_warn_settings(chat_id)
        warn_limit = settings["warn_limit"]

        if warn_count == 0:
            await message.reply_text(
                f"{user.mention} has no active warnings.",
                parse_mode=ParseMode.HTML
            )
            return

        if reasons:
            reasons_text = "\n".join([f"{i+1}. {r}" for i, r in enumerate(reasons)])
        else:
            reasons_text = "• Not specified."

        await message.reply_text(
            f"<b>Warnings: {warn_count}/{warn_limit}</b>\n\n"
            f"<b>Reasons:</b>\n{reasons_text}",
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("rmwarn") & filters.group)
    async def rmwarn_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if not await is_user_admin(client, chat_id, admin_id):
            await message.reply_text("Only admins can remove warnings.", parse_mode=ParseMode.HTML)
            return

        user, error = await _resolve_user(client, message)

        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return

        if not user:
            await message.reply_text(
                "Mention a user, reply to their message, or provide their user ID.",
                parse_mode=ParseMode.HTML
            )
            return

        warn_data = await remove_one_warn(chat_id, user.id)
        warn_count = warn_data["warns"]

        settings = await _get_cached_warn_settings(chat_id)
        warn_limit = settings["warn_limit"]

        await message.reply_text(
            f"Removed one warning from {user.mention}.\n"
            f"<b>Warnings: {warn_count}/{warn_limit}</b>",
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("resetwarns") & filters.group)
    async def resetwarns_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        if not await is_user_admin(client, chat_id, admin_id):
            await message.reply_text("Only admins can reset warnings.", parse_mode=ParseMode.HTML)
            return

        user, error = await _resolve_user(client, message)

        if error:
            await message.reply_text(error, parse_mode=ParseMode.HTML)
            return

        if not user:
            await message.reply_text(
                "Mention a user, reply to their message, or provide their user ID.",
                parse_mode=ParseMode.HTML
            )
            return

        await reset_user_warns(chat_id, user.id)
        await message.reply_text(
            f"All warnings for {user.mention} have been reset.",
            parse_mode=ParseMode.HTML
        )


    @client.on_message(filters.command("warnlimit") & filters.group)
    async def warnlimit_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None
        parts = message.text.split(maxsplit=1)

        if len(parts) < 2:
            settings = await _get_cached_warn_settings(chat_id)
            limit = settings["warn_limit"]
            if limit == 0:
                await message.reply_text(
                    "Warn limit is currently set to <b>0</b>.\nWarning system is effectively disabled.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    f"Warn limit is currently set to <b>{limit}</b>.",
                    parse_mode=ParseMode.HTML
                )
            return

        if not await is_user_admin(client, chat_id, admin_id):
            await message.reply_text("Only admins can change warn limit.", parse_mode=ParseMode.HTML)
            return

        try:
            limit = int(parts[1].strip())
            if limit < 0:
                raise ValueError
        except ValueError:
            await message.reply_text(
                "Please provide a valid number.\n<code>/warnlimit 3</code>",
                parse_mode=ParseMode.HTML
            )
            return

        await set_warn_limit(chat_id, limit)
        _update_settings_cache(chat_id, "warn_limit", limit)

        if limit == 0:
            await message.reply_text(
                "Warn limit set to <b>0</b>.\nWarning system is now disabled.",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply_text(f"Warn limit updated to <b>{limit}</b>.", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("warnmode") & filters.group)
    async def warnmode_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None
        parts = message.text.split(maxsplit=1)

        mode_desc = {
            "ban": "Users who exceed the warning limit will be automatically banned.",
            "mute": "Users who exceed the warning limit will be automatically muted.",
            "kick": "Users who exceed the warning limit will be automatically kicked.",
        }

        if len(parts) < 2:
            settings = await _get_cached_warn_settings(chat_id)
            mode = settings["warn_mode"]
            await message.reply_text(
                f"<b>Warn Mode: {mode.capitalize()}</b>\n"
                f"{mode_desc.get(mode, '')}\n\n"
                f"Change mode:\n<code>/warnmode ban | mute | kick</code>",
                parse_mode=ParseMode.HTML
            )
            return

        if not await is_user_admin(client, chat_id, admin_id):
            await message.reply_text("Only admins can change warn mode.", parse_mode=ParseMode.HTML)
            return

        mode = parts[1].strip().lower()
        if mode not in ["ban", "mute", "kick"]:
            await message.reply_text(
                "Invalid mode. Choose from: <code>ban</code>, <code>mute</code>, <code>kick</code>",
                parse_mode=ParseMode.HTML
            )
            return

        await set_warn_mode(chat_id, mode)
        _update_settings_cache(chat_id, "warn_mode", mode)

        await message.reply_text(
            f"<b>Warn Mode: {mode.capitalize()}</b>\n{mode_desc.get(mode, '')}",
            parse_mode=ParseMode.HTML
        )


    @client.on_callback_query(filters.regex(r"^warn_"))
    async def warn_callback(client: Client, callback: CallbackQuery):
        admin_id = callback.from_user.id
        chat_id = callback.message.chat.id

        if not await is_user_admin(client, chat_id, admin_id):
            await callback.answer("Only admins can use these buttons.", show_alert=True)
            return

        data = callback.data

        # Close
        if data == "warn_close":
            await callback.message.delete()
            await callback.answer()
            return

        parts = data.split("|")
        if len(parts) != 3:
            await callback.answer("Invalid button.", show_alert=True)
            return

        action = parts[0]
        target_chat_id = int(parts[1])
        target_user_id = int(parts[2])

        settings = await _get_cached_warn_settings(target_chat_id)
        warn_limit = settings["warn_limit"]
        warn_mode = settings["warn_mode"]

        # FIX: Plain text se reason aur admin extract karo
        original_text = callback.message.text or ""
        existing_reason = _extract_reason_from_text(original_text)
        existing_admin_mention = _extract_admin_mention_from_text(original_text)
        admin_mention = existing_admin_mention or callback.from_user.mention

        # FIX: User ko Telegram se directly fetch karo
        try:
            target_user = await client.get_users(target_user_id)
            user_mention = _make_user_mention(target_user.id, target_user.first_name)
        except Exception:
            user_mention = f'<a href="tg://user?id={target_user_id}">User</a>'

        # FIX: Unban — delete nahi, edit karo
        if action == "warn_unban":
            try:
                await client.unban_chat_member(target_chat_id, target_user_id)
                await callback.answer("User unbanned!")
                await callback.message.edit_text(
                    f"{user_mention} has been <b>unbanned</b>.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Close", callback_data="warn_close")
                    ]])
                )
            except Exception as e:
                await callback.answer(f"Failed to unban: {e}", show_alert=True)
            return

        # FIX: Unmute — delete nahi, edit karo
        if action == "warn_unmute":
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
                await callback.answer("User unmuted!")
                await callback.message.edit_text(
                    f"{user_mention} has been <b>unmuted</b>.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Close", callback_data="warn_close")
                    ]])
                )
            except Exception as e:
                await callback.answer(f"Failed to unmute: {e}", show_alert=True)
            return

        # -1
        if action == "warn_minus":
            warn_data = await remove_one_warn(target_chat_id, target_user_id)
            warn_count = warn_data["warns"]
            await callback.answer(f"Warning removed: {warn_count}/{warn_limit}")

        # +1
        elif action == "warn_plus":
            warn_data = await add_warn(target_chat_id, target_user_id)
            warn_count = warn_data["warns"]

            # FIX: Limit reach hone par — consistent mention ke saath action text
            if warn_limit > 0 and warn_count >= warn_limit:
                await callback.answer(f"Limit reached! Applying: {warn_mode}")

                try:
                    await callback.message.edit_text(
                        _action_text(
                            user_mention,       # FIX: existing mention use karo, User hardcoded nahi
                            warn_count,
                            warn_limit,
                            admin_mention,
                            warn_mode,
                            existing_reason
                        ),
                        parse_mode=ParseMode.HTML,
                        reply_markup=_action_buttons(target_chat_id, target_user_id, warn_mode)
                    )
                except Exception:
                    pass

                await reset_user_warns(target_chat_id, target_user_id)
                await _apply_warn_action(client, target_chat_id, target_user_id, warn_mode)
                return

            await callback.answer(f"Warning added: {warn_count}/{warn_limit}")

        # Reset All
        elif action == "warn_reset":
            await reset_user_warns(target_chat_id, target_user_id)
            warn_count = 0
            await callback.answer("All warnings reset!")

        else:
            return

        # FIX: Normal update — re.sub nahi, fresh _warn_text banao
        # Taaki mention hamesha consistent rahe
        try:
            warn_data = await get_user_warns(target_chat_id, target_user_id)
            warn_count = warn_data["warns"]

            new_text = _warn_text(user_mention, warn_count, warn_limit, admin_mention, existing_reason)

            # Sirf warn actions ke liye extra line add karo (reset ya minus ke baad bhi)
            if warn_count > 0:
                new_text += "\n\nReply to this message to manage warnings or apply additional actions."

            await callback.message.edit_text(
                new_text,
                parse_mode=ParseMode.HTML,
                # FIX: warn_count pass karo taaki 0 pe buttons sahi dikhein
                reply_markup=_warn_buttons(target_chat_id, target_user_id, warn_count)
            )
        except Exception:
            pass

    logger.info("✅ Warn handlers setup complete")
