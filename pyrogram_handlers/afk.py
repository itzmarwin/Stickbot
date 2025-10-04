import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType
from datetime import datetime

from database import get_afk_user, set_afk_user, remove_afk_user

logger = logging.getLogger(__name__)

# In-memory cache for AFK users (optional, for performance)
afk_cache = {}

def get_afk_duration(since):
    delta = datetime.now() - since
    seconds = int(delta.total_seconds())
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    duration = []
    if days: duration.append(f"{days}d")
    if hours: duration.append(f"{hours}h")
    if minutes: duration.append(f"{minutes}m")
    duration.append(f"{seconds}s")
    return " ".join(duration)

def format_afk_message(user_mention, reason, duration):
    if reason:
        return f"{user_mention} is AFK: {reason} (since {duration})."
    else:
        return f"{user_mention} is AFK (since {duration})."

async def setup_afk_handlers(client: Client):
    """Setup AFK command handlers"""
    
    @client.on_message(filters.command("afk") & filters.group)
    async def afk_command(_, message: Message):
        user = message.from_user
        reason = " ".join(message.command[1:]).strip() or None

        # Set AFK in database and cache
        await set_afk_user(user.id, user.first_name, reason, datetime.now())
        afk_cache[user.id] = {
            "user": {"id": user.id, "first_name": user.first_name},
            "reason": reason,
            "since": datetime.now()
        }

        response = f"{user.mention} is now AFK."
        if reason:
            response += f"\nReason: {reason}"
        await message.reply(response)

    @client.on_message(filters.all & ~filters.service & filters.group)
    async def afk_user_handler(_, message: Message):
        user = message.from_user

        # Check if the message sender is AFK and remove AFK if they are
        if user:
            # Check cache first, then database
            afk_data = afk_cache.get(user.id)
            if not afk_data:
                afk_data = await get_afk_user(user.id)
                if afk_data:
                    # Convert stored string to datetime if needed
                    if isinstance(afk_data["since"], str):
                        afk_data["since"] = datetime.fromisoformat(afk_data["since"])
                    afk_cache[user.id] = afk_data

            if afk_data:
                # Remove AFK
                await remove_afk_user(user.id)
                afk_cache.pop(user.id, None)

                duration = get_afk_duration(afk_data["since"])
                await message.reply(
                    f"Welcome back, {user.mention}! You were AFK for {duration}."
                )
                return

        # Check if the replied user is AFK
        if message.reply_to_message:
            replied_user = message.reply_to_message.from_user
            if replied_user:
                afk_data = afk_cache.get(replied_user.id)
                if not afk_data:
                    afk_data = await get_afk_user(replied_user.id)
                    if afk_data:
                        if isinstance(afk_data["since"], str):
                            afk_data["since"] = datetime.fromisoformat(afk_data["since"])
                        afk_cache[replied_user.id] = afk_data

                if afk_data:
                    duration = get_afk_duration(afk_data["since"])
                    text = format_afk_message(
                        replied_user.mention, afk_data["reason"], duration
                    )
                    await message.reply(text)
                    return

        # Check mentioned users
        mentioned_users = []
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntityType.TEXT_MENTION:
                    mentioned_users.append(entity.user)
                elif entity.type == MessageEntityType.MENTION:
                    username = message.text[entity.offset : entity.offset + entity.length]
                    try:
                        mentioned_user = await client.get_users(username)
                        if mentioned_user:
                            mentioned_users.append(mentioned_user)
                    except Exception:
                        pass

        for u in mentioned_users:
            afk_data = afk_cache.get(u.id)
            if not afk_data:
                afk_data = await get_afk_user(u.id)
                if afk_data:
                    if isinstance(afk_data["since"], str):
                        afk_data["since"] = datetime.fromisoformat(afk_data["since"])
                    afk_cache[u.id] = afk_data

            if afk_data:
                duration = get_afk_duration(afk_data["since"])
                text = format_afk_message(
                    u.mention, afk_data["reason"], duration
                )
                await message.reply(text)
                break  # stop after first AFK mention

    logger.info("AFK handlers setup complete")
