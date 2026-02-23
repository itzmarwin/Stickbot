import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode, ChatMemberStatus
from pyrogram.errors import UserNotParticipant, PeerIdInvalid, FloodWait

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

# ============================================================
# RAM CACHE — warn_settings per group
# ============================================================
_warn_settings_cache: dict = {}


async def _get_cached_warn_settings(chat_id: int) -> dict:
    if chat_id not in _warn_settings_cache:
        settings = await get_warn_settings(chat_id)
        _warn_settings_cache[chat_id] = settings
    return _warn_settings_cache[chat_id]


def _update_settings_cache(chat_id: int, key: str, value):
    if chat_id not in _warn_settings_cache:
        _warn_settings_cache[chat_id] = {}
    _warn_settings_cache[chat_id][key] = value


# ============================================================
# HELPER — User resolve karo (reply/username/userid)
# ============================================================
async def _resolve_user(client: Client, message: Message):
    """
    Reply, username ya user_id se user resolve karo.
    Return: (user, error_msg)
    """
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        if not user:
            return None, "Could not get user from replied message."
        return user, None

    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        return None, None  # Caller handle karega

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


def _warn_buttons(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("-1", callback_data=f"warn_minus|{chat_id}|{user_id}"),
            InlineKeyboardButton("Reset All", callback_data=f"warn_reset|{chat_id}|{user_id}"),
            InlineKeyboardButton("+1", callback_data=f"warn_plus|{chat_id}|{user_id}"),
        ],
        [
            InlineKeyboardButton("Close", callback_data=f"warn_close"),
        ]
    ])


async def _apply_warn_action(client: Client, chat_id: int, user_id: int, mode: str):
    """Warn limit full hone pe action lo."""
    try:
        if mode == "ban":
            await client.ban_chat_member(chat_id, user_id)
        elif mode == "kick":
            await client.ban_chat_member(chat_id, user_id)
            await client.unban_chat_member(chat_id, user_id)
        elif mode == "mute":
            from pyrogram.types import ChatPermissions
            await client.restrict_chat_member(
                chat_id, user_id,
                ChatPermissions(can_send_messages=False)
            )
    except Exception as e:
        logger.error(f"Failed to apply warn action {mode} on {user_id} in {chat_id}: {e}")


async def setup_warn_handlers(client: Client):

    # ============================================================
    # /warn — user ko warn karo
    # ============================================================
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

        # Admin ko warn nahi kar sakte
        if await is_user_admin(client, chat_id, user.id):
            await message.reply_text("Admins cannot be warned.", parse_mode=ParseMode.HTML)
            return

        # Reason extract karo
        parts = message.text.split(maxsplit=2)
        reason = None
        if message.reply_to_message and len(parts) >= 2:
            reason = parts[1].strip()
        elif not message.reply_to_message and len(parts) >= 3:
            reason = parts[2].strip()

        # Warn add karo
        warn_data = await add_warn(chat_id, user.id, reason)
        warn_count = warn_data["warns"]

        settings = await _get_cached_warn_settings(chat_id)
        warn_limit = settings["warn_limit"]
        warn_mode = settings["warn_mode"]

        admin_mention = message.from_user.mention if message.from_user else "Admin"
        user_mention = user.mention

        warn_msg = (
            f"{user_mention} has received a warning "
            f"(<b>{warn_count}/{warn_limit}</b>) "
            f"from admin {admin_mention}."
        )

        if reason:
            warn_msg += f"\n<b>Reason:</b> {reason}"

        warn_msg += "\n\nReply to this message to manage warnings or apply additional actions."

        # Warn limit reach ho gayi
        if warn_limit > 0 and warn_count >= warn_limit:
            await message.reply_text(
                warn_msg + f"\n\n⚠️ Warning limit reached! Applying action: <b>{warn_mode}</b>.",
                parse_mode=ParseMode.HTML,
                reply_markup=_warn_buttons(chat_id, user.id)
            )
            await reset_user_warns(chat_id, user.id)
            await _apply_warn_action(client, chat_id, user.id, warn_mode)
        else:
            await message.reply_text(
                warn_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=_warn_buttons(chat_id, user.id)
            )


    # ============================================================
    # /warns — user ki warns dekho
    # ============================================================
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

        reasons_text = ""
        if reasons:
            reasons_text = "\n".join([f"{i+1}. {r}" for i, r in enumerate(reasons)])
        else:
            reasons_text = "• Not specified."

        await message.reply_text(
            f"<b>Warnings: {warn_count}/{warn_limit}</b>\n\n"
            f"<b>Reasons:</b>\n{reasons_text}",
            parse_mode=ParseMode.HTML
        )


    # ============================================================
    # /rmwarn — ek warn hatao
    # ============================================================
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


    # ============================================================
    # /resetwarns — saari warns reset karo
    # ============================================================
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


    # ============================================================
    # /warnlimit — limit dekho ya set karo
    # ============================================================
    @client.on_message(filters.command("warnlimit") & filters.group)
    async def warnlimit_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        parts = message.text.split(maxsplit=1)

        # Sirf dekho
        if len(parts) < 2:
            settings = await _get_cached_warn_settings(chat_id)
            limit = settings["warn_limit"]
            if limit == 0:
                await message.reply_text(
                    "Warn limit is currently set to <b>0</b>.\n"
                    "Warning system is effectively disabled.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    f"Warn limit is currently set to <b>{limit}</b>.",
                    parse_mode=ParseMode.HTML
                )
            return

        # Set karo — admin only
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
            await message.reply_text(
                f"Warn limit updated to <b>{limit}</b>.",
                parse_mode=ParseMode.HTML
            )


    # ============================================================
    # /warnmode — mode dekho ya set karo
    # ============================================================
    @client.on_message(filters.command("warnmode") & filters.group)
    async def warnmode_command(client: Client, message: Message):
        chat_id = message.chat.id
        admin_id = message.from_user.id if message.from_user else None

        parts = message.text.split(maxsplit=1)

        # Sirf dekho
        if len(parts) < 2:
            settings = await _get_cached_warn_settings(chat_id)
            mode = settings["warn_mode"]
            mode_desc = {
                "ban": "Users who exceed the warning limit will be automatically banned.",
                "mute": "Users who exceed the warning limit will be automatically muted.",
                "kick": "Users who exceed the warning limit will be automatically kicked.",
            }.get(mode, "")

            await message.reply_text(
                f"<b>Warn Mode: {mode.capitalize()}</b>\n"
                f"{mode_desc}\n\n"
                f"Change mode:\n<code>/warnmode ban | mute | kick</code>",
                parse_mode=ParseMode.HTML
            )
            return

        # Set karo — admin only
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

        mode_desc = {
            "ban": "Users who exceed the warning limit will be automatically banned.",
            "mute": "Users who exceed the warning limit will be automatically muted.",
            "kick": "Users who exceed the warning limit will be automatically kicked.",
        }.get(mode, "")

        await message.reply_text(
            f"<b>Warn Mode: {mode.capitalize()}</b>\n{mode_desc}",
            parse_mode=ParseMode.HTML
        )


    # ============================================================
    # CALLBACK QUERY — Buttons handle karo (-1, Reset All, +1, Close)
    # ============================================================
    @client.on_callback_query(filters.regex(r"^warn_"))
    async def warn_callback(client: Client, callback: CallbackQuery):
        admin_id = callback.from_user.id
        chat_id = callback.message.chat.id

        if not await is_user_admin(client, chat_id, admin_id):
            await callback.answer("Only admins can use these buttons.", show_alert=True)
            return

        data = callback.data

        # Close button
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

        if action == "warn_plus":
            warn_data = await add_warn(target_chat_id, target_user_id)
            warn_count = warn_data["warns"]
            await callback.answer(f"Warning added: {warn_count}/{warn_limit}")

        elif action == "warn_minus":
            warn_data = await remove_one_warn(target_chat_id, target_user_id)
            warn_count = warn_data["warns"]
            await callback.answer(f"Warning removed: {warn_count}/{warn_limit}")

        elif action == "warn_reset":
            await reset_user_warns(target_chat_id, target_user_id)
            await callback.answer("All warnings reset!")

        # Button update karo
        try:
            await callback.message.edit_reply_markup(
                reply_markup=_warn_buttons(target_chat_id, target_user_id)
            )
        except Exception:
            pass

    logger.info("✅ Warn handlers setup complete")
