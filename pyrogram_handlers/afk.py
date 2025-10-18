import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

from database import get_afk_user, set_afk_user, remove_afk_user

logger = logging.getLogger(__name__)


class AFKCache:
    """
    ✅ Memory-safe AFK cache with automatic cleanup
    Prevents memory leak from unlimited cache growth
    """
    def __init__(self, max_size: int = 1000, ttl_hours: int = 24):
        """
        Args:
            max_size: Maximum number of AFK users to cache
            ttl_hours: Time-to-live for cache entries (hours)
        """
        self.cache: OrderedDict[int, tuple] = OrderedDict()
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)
        self.last_cleanup = datetime.now()
        self.cleanup_interval = timedelta(hours=1)  # Cleanup every hour
        
        logger.info(f"AFKCache initialized: max_size={max_size}, ttl={ttl_hours}h")
    
    def get(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get AFK data for user with automatic expiry check
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            AFK data dict or None if not found/expired
        """
        # Periodic cleanup
        if datetime.now() - self.last_cleanup > self.cleanup_interval:
            self._cleanup()
        
        if user_id in self.cache:
            data, timestamp = self.cache[user_id]
            
            # Check if expired
            if datetime.now() - timestamp < self.ttl:
                # Move to end (mark as recently used)
                self.cache.move_to_end(user_id)
                return data
            else:
                # Expired, remove
                del self.cache[user_id]
                logger.debug(f"AFK cache expired for user {user_id}")
        
        return None
    
    def set(self, user_id: int, data: Dict[str, Any]):
        """
        Set AFK data for user with automatic size management
        
        Args:
            user_id: Telegram user ID
            data: AFK data dict
        """
        # Remove old entry if exists
        if user_id in self.cache:
            del self.cache[user_id]
        
        # Check size limit
        if len(self.cache) >= self.max_size:
            # Remove oldest entry (FIFO)
            removed_id, _ = self.cache.popitem(last=False)
            logger.debug(f"AFK cache full, removed user {removed_id}")
        
        # Add new entry
        self.cache[user_id] = (data, datetime.now())
    
    def remove(self, user_id: int):
        """Remove user from cache"""
        self.cache.pop(user_id, None)
    
    def _cleanup(self):
        """
        Remove expired entries from cache
        Called periodically to prevent memory buildup
        """
        initial_size = len(self.cache)
        current_time = datetime.now()
        
        # Find expired entries
        expired = [
            uid for uid, (_, timestamp) in list(self.cache.items())
            if current_time - timestamp > self.ttl
        ]
        
        # Remove expired
        for uid in expired:
            del self.cache[uid]
        
        self.last_cleanup = current_time
        
        removed = len(expired)
        if removed > 0:
            logger.info(f"AFK cache cleanup: removed {removed} expired entries, "
                       f"size: {initial_size} -> {len(self.cache)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "usage_percent": round((len(self.cache) / self.max_size) * 100, 2),
            "last_cleanup": self.last_cleanup.isoformat()
        }
    
    def clear(self):
        """Clear entire cache (admin function)"""
        initial_size = len(self.cache)
        self.cache.clear()
        logger.info(f"AFK cache cleared: {initial_size} entries removed")


# ✅ Global cache instance with memory-safe implementation
afk_cache = AFKCache(max_size=1000, ttl_hours=24)


def get_afk_duration(since: datetime) -> str:
    """
    Calculate human-readable duration since AFK
    
    Args:
        since: Datetime when user went AFK
        
    Returns:
        Formatted duration string (e.g., "2d 3h 45m 12s")
    """
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
    """
    Format AFK notification message
    
    Args:
        user_mention: User mention string
        reason: AFK reason (optional)
        duration: Duration string
        
    Returns:
        Formatted message
    """
    if reason:
        return f"{user_mention} is AFK: {reason} (since {duration})."
    else:
        return f"{user_mention} is AFK (since {duration})."


async def setup_afk_handlers(client: Client):
    """Setup AFK command handlers with memory-safe caching"""
    
    @client.on_message(filters.command("afk") & filters.group)
    async def afk_command(_, message: Message):
        """Handle /afk command"""
        user = message.from_user
        reason = " ".join(message.command[1:]).strip() or None
        now = datetime.now()

        try:
            # Set AFK in database (persistent storage)
            await set_afk_user(user.id, user.first_name, reason, now)
            
            # ✅ Set AFK in memory-safe cache
            afk_cache.set(user.id, {
                "user": {"id": user.id, "first_name": user.first_name},
                "reason": reason,
                "since": now
            })

            response = f"{user.mention} is now AFK."
            if reason:
                response += f"\nReason: {reason}"
            
            await message.reply(response)
            logger.info(f"User {user.id} set AFK: {reason or 'No reason'}")
            
        except Exception as e:
            logger.error(f"Error setting AFK for user {user.id}: {e}")
            await message.reply("❌ Failed to set AFK. Please try again.")

    @client.on_message(filters.all & ~filters.service & filters.group)
    async def afk_user_handler(_, message: Message):
        """Handle AFK checks and notifications"""
        user = message.from_user

        # ✅ Check if the message sender is AFK and remove AFK if they are
        if user:
            try:
                # Check memory-safe cache first
                afk_data = afk_cache.get(user.id)
                
                # If not in cache, check database
                if not afk_data:
                    afk_data = await get_afk_user(user.id)
                    if afk_data:
                        # Convert stored string to datetime if needed
                        if isinstance(afk_data["since"], str):
                            afk_data["since"] = datetime.fromisoformat(afk_data["since"])
                        # ✅ Update memory-safe cache
                        afk_cache.set(user.id, afk_data)

                if afk_data:
                    # User is back, remove AFK
                    await remove_afk_user(user.id)
                    afk_cache.remove(user.id)  # ✅ Use remove() method

                    duration = get_afk_duration(afk_data["since"])
                    await message.reply(
                        f"Welcome back, {user.mention}! You were AFK for {duration}."
                    )
                    logger.info(f"User {user.id} returned from AFK after {duration}")
                    return
                    
            except Exception as e:
                logger.error(f"Error checking sender AFK status {user.id}: {e}")

        # ✅ Check if the replied user is AFK
        if message.reply_to_message:
            replied_user = message.reply_to_message.from_user
            if replied_user:
                try:
                    # Check cache first
                    afk_data = afk_cache.get(replied_user.id)
                    
                    # If not in cache, check database
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
                        
                except Exception as e:
                    logger.error(f"Error checking replied user AFK {replied_user.id}: {e}")

        # ✅ Check mentioned users
        mentioned_users = []
        if message.entities:
            for entity in message.entities:
                try:
                    if entity.type == MessageEntityType.TEXT_MENTION:
                        mentioned_users.append(entity.user)
                    elif entity.type == MessageEntityType.MENTION:
                        username = message.text[entity.offset : entity.offset + entity.length]
                        try:
                            mentioned_user = await client.get_users(username)
                            if mentioned_user:
                                mentioned_users.append(mentioned_user)
                        except Exception as e:
                            logger.debug(f"Could not get user for mention {username}: {e}")
                            pass
                except Exception as e:
                    logger.error(f"Error processing entity: {e}")

        # Check AFK status for mentioned users
        for u in mentioned_users:
            try:
                # Check cache first
                afk_data = afk_cache.get(u.id)
                
                # If not in cache, check database
                if not afk_data:
                    afk_data = await get_afk_user(u.id)
                    if afk_data:
                        if isinstance(afk_data["since"], str):
                            afk_data["since"] = datetime.fromisoformat(afk_data["since"])
                        afk_cache.set(u.id, afk_data)

                if afk_data:
                    duration = get_afk_duration(afk_data["since"])
                    text = format_afk_message(
                        u.mention, afk_data["reason"], duration
                    )
                    await message.reply(text)
                    break  # Stop after first AFK mention
                    
            except Exception as e:
                logger.error(f"Error checking mentioned user AFK {u.id}: {e}")

    logger.info("✅ AFK handlers setup complete")


# ✅ NEW: Admin function to get cache statistics
async def get_afk_cache_stats() -> Dict[str, Any]:
    """Get AFK cache statistics for monitoring"""
    return afk_cache.get_stats()


# ✅ NEW: Admin function to clear cache
async def clear_afk_cache():
    """Clear AFK cache (admin function)"""
    afk_cache.clear()
