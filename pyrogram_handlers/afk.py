from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

from database import get_afk_user, set_afk_user, remove_afk_user
from pyrogram_handlers.commands import cmd, get_args

@client.on_message(filters.group)
async def test_handler(_, message: Message):
    if message.text and message.text.startswith(".afk"):
        await message.reply("TEST WORKS")
        

class AFKCache:
    def __init__(self, max_size: int = 1000, ttl_hours: int = 24):
        self.cache: OrderedDict[int, tuple] = OrderedDict()
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)
        self.last_cleanup = datetime.now()
        self.cleanup_interval = timedelta(hours=1)

    def get(self, user_id: int) -> Optional[Dict[str, Any]]:
        if datetime.now() - self.last_cleanup > self.cleanup_interval:
            self._cleanup()

        if user_id in self.cache:
            data, timestamp = self.cache[user_id]
            if datetime.now() - timestamp < self.ttl:
                self.cache.move_to_end(user_id)
                return data
            else:
                del self.cache[user_id]

        return None

    def set(self, user_id: int, data: Dict[str, Any]):
        if user_id in self.cache:
            del self.cache[user_id]

        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)

        self.cache[user_id] = (data, datetime.now())

    def remove(self, user_id: int):
        self.cache.pop(user_id, None)

    def _cleanup(self):
        current_time = datetime.now()
        expired = [
            uid for uid, (_, timestamp) in list(self.cache.items())
            if current_time - timestamp > self.ttl
        ]
        for uid in expired:
            del self.cache[uid]
        self.last_cleanup = current_time

    def get_stats(self) -> Dict[str, Any]:
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "usage_percent": round((len(self.cache) / self.max_size) * 100, 2),
            "last_cleanup": self.last_cleanup.isoformat()
        }

    def clear(self):
        self.cache.clear()


afk_cache = AFKCache(max_size=1000, ttl_hours=24)


def get_afk_duration(since: datetime) -> str:
    delta = datetime.now() - since
    seconds = int(delta.total_seconds())

    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    duration = []
    if days:
        duration.append(f"{days}d")
    if hours:
        duration.append(f"{hours}h")
    if minutes:
        duration.append(f"{minutes}m")
    duration.append(f"{seconds}s")

    return " ".join(duration)


def format_afk_message(user_mention: str, reason: Optional[str], duration: str) -> str:
    if reason:
        return f"{user_mention} is AFK: {reason} (since {duration})."
    else:
        return f"{user_mention} is AFK (since {duration})."


async def setup_afk_handlers(client: Client):

    @client.on_message(filters.group)
    async def test_handler(_, message: Message):
        if message.text and message.text.startswith(".afk"):
            await message.reply("TEST WORKS")

    @client.on_message(cmd("afk") & filters.group)
    async def afk_command(_, message: Message):
        user = message.from_user
        reason = " ".join(get_args(message)).strip() or None
        now = datetime.now()

        await set_afk_user(user.id, user.first_name, reason, now)

        afk_cache.set(user.id, {
            "user": {"id": user.id, "first_name": user.first_name},
            "reason": reason,
            "since": now
        })

        response = f"{user.mention} is now AFK."
        if reason:
            response += f"\nReason: {reason}"

        await message.reply(response)

    @client.on_message(filters.all & ~filters.service & filters.group)
    async def afk_user_handler(_, message: Message):
        user = message.from_user

        if user:
            afk_data = afk_cache.get(user.id)

            if not afk_data:
                afk_data = await get_afk_user(user.id)
                if afk_data:
                    if isinstance(afk_data["since"], str):
                        afk_data["since"] = datetime.fromisoformat(afk_data["since"])
                    afk_cache.set(user.id, afk_data)

            if afk_data:
                await remove_afk_user(user.id)
                afk_cache.remove(user.id)

                duration = get_afk_duration(afk_data["since"])
                await message.reply(
                    f"Welcome back, {user.mention}! You were AFK for {duration}."
                )
                return

        if message.reply_to_message:
            replied_user = message.reply_to_message.from_user
            if replied_user:
                afk_data = afk_cache.get(replied_user.id)

                if not afk_data:
                    afk_data = await get_afk_user(replied_user.id)
                    if afk_data:
                        if isinstance(afk_data["since"], str):
                            afk_data["since"] = datetime.fromisoformat(afk_data["since"])
                        afk_cache.set(replied_user.id, afk_data)

                if afk_data:
                    duration = get_afk_duration(afk_data["since"])
                    text = format_afk_message(
                        replied_user.mention, afk_data["reason"], duration
                    )
                    await message.reply(text)
                    return

        mentioned_users = []
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntityType.TEXT_MENTION:
                    mentioned_users.append(entity.user)
                elif entity.type == MessageEntityType.MENTION:
                    username = message.text[entity.offset: entity.offset + entity.length]
                    mentioned_user = await client.get_users(username)
                    if mentioned_user:
                        mentioned_users.append(mentioned_user)

        for u in mentioned_users:
            afk_data = afk_cache.get(u.id)

            if not afk_data:
                afk_data = await get_afk_user(u.id)
                if afk_data:
                    if isinstance(afk_data["since"], str):
                        afk_data["since"] = datetime.fromisoformat(afk_data["since"])
                    afk_cache.set(u.id, afk_data)

            if afk_data:
                duration = get_afk_duration(afk_data["since"])
                text = format_afk_message(u.mention, afk_data["reason"], duration)
                await message.reply(text)
                break


async def get_afk_cache_stats() -> Dict[str, Any]:
    return afk_cache.get_stats()


async def clear_afk_cache():
    afk_cache.clear()
