import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from config import is_owner, LOG_GROUP_ID
from database import (
    add_banned_user, remove_banned_user, get_banned_count, get_banned_users,
    get_served_chats, is_banned_user, delete_user_packs
)

# In-memory cache for banned users
BANNED_USERS = set()

async def get_readable_time(seconds: int) -> str:
    periods = [('s', 1), ('m', 60), ('h', 3600), ('d', 86400)]
    result = []
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result.append(f"{period_value}{period_name}")
    return " ".join(result[-2:]) if result else "0s"

async def extract_user(client: Client, message: Message):
    if message.reply_to_message:
        return message.reply_to_message.from_user
    
    if len(message.command) > 1:
        user_input = message.command[1]
        try:
            if user_input.isdigit():
                return await client.get_users(int(user_input))
            else:
                return await client.get_users(user_input.lstrip('@'))
        except Exception:
            return None
    return None

async def setup_gban_handlers(client: Client):
    """Setup GBan command handlers"""
    
    # Test command to check if Pyrogram is working
    @client.on_message(filters.command("gtest"))
    async def test_gban(client: Client, message: Message):
        await message.reply("✅ GBan test command working!")
    
    # GBan command
    @client.on_message(filters.command(["gban", "globalban"]))
    async def global_ban(client: Client, message: Message):
        if not is_owner(message.from_user.id):
            await message.reply("❌ Owner only command.")
            return
        
        user = await extract_user(client, message)
        if not user:
            await message.reply("❌ Reply to user or provide user ID.")
            return
        
        if user.id == message.from_user.id:
            return await message.reply("❌ Cannot gban yourself!")
        elif user.id == client.me.id:
            return await message.reply("❌ Cannot gban bot!")
        
        is_gbanned = await is_banned_user(user.id)
        if is_gbanned:
            return await message.reply(f"❌ {user.mention} already gbanned!")
        
        reason = " ".join(message.command[2:]) if len(message.command) > 2 else "No reason"
        
        mystic = await message.reply(f"🔄 Banning {user.mention}...")
        
        # Delete packs
        packs_deleted = await delete_user_packs(user.id)
        
        # Ban from groups
        served_chats = [int(chat["chat_id"]) for chat in await get_served_chats()]
        banned_chats = 0
        
        for chat_id in served_chats:
            try:
                await client.ban_chat_member(chat_id, user.id)
                banned_chats += 1
                await asyncio.sleep(0.5)
            except Exception:
                continue
        
        await add_banned_user(user.id)
        BANNED_USERS.add(user.id)
        
        await mystic.edit_text(
            f"✅ {user.mention} gbanned!\n"
            f"📦 Packs deleted: {packs_deleted}\n"
            f"👥 Groups banned: {banned_chats}\n"
            f"📝 Reason: {reason}"
        )

    # Ungban command
    @client.on_message(filters.command("ungban"))
    async def global_unban(client: Client, message: Message):
        if not is_owner(message.from_user.id):
            return
        
        user = await extract_user(client, message)
        if not user:
            await message.reply("❌ Reply to user or provide user ID.")
            return
        
        is_gbanned = await is_banned_user(user.id)
        if not is_gbanned:
            return await message.reply(f"❌ {user.mention} not gbanned!")
        
        mystic = await message.reply(f"🔄 Unbanning {user.mention}...")
        
        served_chats = [int(chat["chat_id"]) for chat in await get_served_chats()]
        unbanned_chats = 0
        
        for chat_id in served_chats:
            try:
                await client.unban_chat_member(chat_id, user.id)
                unbanned_chats += 1
                await asyncio.sleep(0.5)
            except Exception:
                continue
        
        await remove_banned_user(user.id)
        if user.id in BANNED_USERS:
            BANNED_USERS.remove(user.id)
        
        await mystic.edit_text(f"✅ {user.mention} unbanned from {unbanned_chats} groups!")

    # Gbanlist command
    @client.on_message(filters.command(["gbannedusers", "gbanlist"]))
    async def gbanned_list(client: Client, message: Message):
        if not is_owner(message.from_user.id):
            return
        
        users = await get_banned_users()
        if not users:
            await message.reply("📝 No gbanned users.")
            return
        
        text = "🚫 Gbanned Users:\n\n"
        for i, user_id in enumerate(users, 1):
            try:
                user = await client.get_users(user_id)
                text += f"{i}. {user.mention} ({user.id})\n"
            except Exception:
                text += f"{i}. {user_id}\n"
        
        await message.reply(text)
