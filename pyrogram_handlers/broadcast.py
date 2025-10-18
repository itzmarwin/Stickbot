import asyncio
import logging
from typing import List, Dict, Union
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError, UserIsBlocked, ChatWriteForbidden

from config import is_admin, LOG_GROUP_ID
from database import get_all_users, get_served_chats

logger = logging.getLogger(__name__)


class BroadcastSystem:
    """
    ✅ Production-ready broadcast system with:
    - Adaptive delay (prevents FloodWait)
    - FloodWait accumulation tracking
    - Automatic slowdown on repeated FloodWaits
    - Emergency stop on excessive rate limiting
    """
    def __init__(self):
        self.active_broadcasts = set()
        self.flood_wait_threshold = 300  # 5 minutes total FloodWait = stop
        self.base_delay_users = 0.2      # Base delay for users (200ms)
        self.base_delay_groups = 0.3     # Base delay for groups (300ms)
        
        logger.info("BroadcastSystem initialized with adaptive rate limiting")
    
    async def parse_broadcast_command(self, message: Message) -> Dict:
        """Parse broadcast command and extract flags and content"""
        command_text = message.text or message.caption or ""
        parts = command_text.split()
        
        flags = {
            "user": False,
            "group": False,
            "message": None,
            "is_reply": message.reply_to_message is not None
        }
        
        # Extract flags
        for part in parts:
            if part == "-user":
                flags["user"] = True
            elif part == "-group":
                flags["group"] = True
        
        # If no flags specified, default to both
        if not flags["user"] and not flags["group"]:
            flags["user"] = True
            flags["group"] = True
        
        # Extract message content
        if flags["is_reply"]:
            flags["content"] = message.reply_to_message
        else:
            # Extract text after command and flags
            message_parts = []
            skip_next = False
            for i, part in enumerate(parts):
                if skip_next:
                    skip_next = False
                    continue
                if part in ["/broadcast", "-user", "-group"]:
                    skip_next = False
                    continue
                message_parts.append(part)
            
            flags["message"] = " ".join(message_parts) if message_parts else None
        
        return flags
    
    async def send_message_safe(self, client: Client, chat_id: int, 
                                content: Union[Message, str], broadcast_id: str) -> tuple[bool, str]:
        """
        ✅ Send message with comprehensive error handling
        
        Returns:
            (success: bool, error_type: str)
        """
        try:
            if isinstance(content, Message):
                await content.copy(chat_id=chat_id)
            else:
                await client.send_message(chat_id=chat_id, text=content)
            return True, None
            
        except FloodWait as e:
            logger.warning(f"Broadcast {broadcast_id}: FloodWait {e.value}s for chat {chat_id}")
            
            # ✅ Check if FloodWait is reasonable (< 60s)
            if e.value > 60:
                logger.error(f"Broadcast {broadcast_id}: Excessive FloodWait ({e.value}s), skipping chat {chat_id}")
                return False, "flood_wait_excessive"
            
            # Wait as required
            await asyncio.sleep(e.value + 1)
            
            # Retry once
            try:
                if isinstance(content, Message):
                    await content.copy(chat_id=chat_id)
                else:
                    await client.send_message(chat_id=chat_id, text=content)
                return True, None
            except Exception as retry_error:
                logger.error(f"Broadcast {broadcast_id}: Retry failed for chat {chat_id}: {retry_error}")
                return False, "retry_failed"
        
        except UserIsBlocked:
            # User blocked the bot
            logger.debug(f"Broadcast {broadcast_id}: User {chat_id} blocked bot")
            return False, "user_blocked"
        
        except ChatWriteForbidden:
            # Bot cannot write to chat
            logger.debug(f"Broadcast {broadcast_id}: No write permission in chat {chat_id}")
            return False, "no_permission"
        
        except RPCError as e:
            logger.error(f"Broadcast {broadcast_id}: RPC error for chat {chat_id}: {e}")
            return False, "rpc_error"
        
        except Exception as e:
            logger.error(f"Broadcast {broadcast_id}: Unexpected error for chat {chat_id}: {e}")
            return False, "unknown_error"
    
    async def broadcast_to_users(self, client: Client, content: Union[Message, str], 
                                 broadcast_id: str) -> Dict:
        """
        ✅ Broadcast to all users with adaptive delay
        """
        users = await get_all_users()
        total = len(users)
        success = 0
        failed = 0
        flood_wait_total = 0
        error_stats = {}
        
        # ✅ Adaptive delay parameters
        current_delay = self.base_delay_users
        consecutive_flood_waits = 0
        
        logger.info(f"Broadcast {broadcast_id}: Starting user broadcast to {total} users")
        
        for i, user in enumerate(users):
            # Check if broadcast was cancelled
            if broadcast_id not in self.active_broadcasts:
                logger.info(f"Broadcast {broadcast_id}: Cancelled by admin")
                break
            
            # ✅ Emergency stop if too many FloodWaits
            if flood_wait_total > self.flood_wait_threshold:
                logger.error(f"Broadcast {broadcast_id}: FloodWait threshold exceeded ({flood_wait_total}s), stopping")
                break
            
            user_id = user["user_id"]
            
            # Send message
            send_success, error_type = await self.send_message_safe(client, user_id, content, broadcast_id)
            
            if send_success:
                success += 1
                consecutive_flood_waits = 0  # Reset on success
            else:
                failed += 1
                # Track error types
                error_stats[error_type] = error_stats.get(error_type, 0) + 1
                
                # ✅ Track FloodWait accumulation
                if error_type == "flood_wait_excessive":
                    consecutive_flood_waits += 1
                    flood_wait_total += 60  # Approximate
                    
                    # ✅ Adaptive slowdown
                    if consecutive_flood_waits >= 3:
                        current_delay *= 1.5  # Increase delay by 50%
                        logger.warning(f"Broadcast {broadcast_id}: Increased delay to {current_delay:.2f}s due to FloodWaits")
            
            # ✅ Progress logging every 50 users
            if (i + 1) % 50 == 0:
                logger.info(f"Broadcast {broadcast_id}: User progress {i+1}/{total} "
                           f"(success: {success}, failed: {failed}, delay: {current_delay:.2f}s)")
            
            # ✅ Adaptive delay
            # Increase delay every 100 messages
            if (i + 1) % 100 == 0:
                current_delay = min(current_delay + 0.1, 1.0)  # Max 1s delay
            
            await asyncio.sleep(current_delay)
        
        return {
            "success": success, 
            "failed": failed, 
            "total": total,
            "flood_wait_total": flood_wait_total,
            "error_stats": error_stats
        }
    
    async def broadcast_to_groups(self, client: Client, content: Union[Message, str], 
                                  broadcast_id: str) -> Dict:
        """
        ✅ Broadcast to all groups with adaptive delay
        """
        groups = await get_served_chats()
        total = len(groups)
        success = 0
        failed = 0
        flood_wait_total = 0
        error_stats = {}
        
        # ✅ Adaptive delay parameters
        current_delay = self.base_delay_groups
        consecutive_flood_waits = 0
        
        logger.info(f"Broadcast {broadcast_id}: Starting group broadcast to {total} groups")
        
        for i, group in enumerate(groups):
            # Check if broadcast was cancelled
            if broadcast_id not in self.active_broadcasts:
                logger.info(f"Broadcast {broadcast_id}: Cancelled by admin")
                break
            
            # ✅ Emergency stop if too many FloodWaits
            if flood_wait_total > self.flood_wait_threshold:
                logger.error(f"Broadcast {broadcast_id}: FloodWait threshold exceeded ({flood_wait_total}s), stopping")
                break
            
            chat_id = group["chat_id"]
            
            # Send message
            send_success, error_type = await self.send_message_safe(client, chat_id, content, broadcast_id)
            
            if send_success:
                success += 1
                consecutive_flood_waits = 0  # Reset on success
            else:
                failed += 1
                # Track error types
                error_stats[error_type] = error_stats.get(error_type, 0) + 1
                
                # ✅ Track FloodWait accumulation
                if error_type == "flood_wait_excessive":
                    consecutive_flood_waits += 1
                    flood_wait_total += 60  # Approximate
                    
                    # ✅ Adaptive slowdown
                    if consecutive_flood_waits >= 3:
                        current_delay *= 1.5  # Increase delay by 50%
                        logger.warning(f"Broadcast {broadcast_id}: Increased delay to {current_delay:.2f}s due to FloodWaits")
            
            # ✅ Progress logging every 20 groups
            if (i + 1) % 20 == 0:
                logger.info(f"Broadcast {broadcast_id}: Group progress {i+1}/{total} "
                           f"(success: {success}, failed: {failed}, delay: {current_delay:.2f}s)")
            
            # ✅ Adaptive delay
            # Groups need more delay than users
            if (i + 1) % 50 == 0:
                current_delay = min(current_delay + 0.1, 2.0)  # Max 2s delay
            
            await asyncio.sleep(current_delay)
        
        return {
            "success": success, 
            "failed": failed, 
            "total": total,
            "flood_wait_total": flood_wait_total,
            "error_stats": error_stats
        }
    
    async def execute_broadcast(self, client: Client, message: Message, flags: Dict):
        """Execute the broadcast in background"""
        broadcast_id = f"broadcast_{message.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.active_broadcasts.add(broadcast_id)
        
        start_time = datetime.now()
        
        try:
            content = flags["content"] if flags["is_reply"] else flags["message"]
            
            if not content:
                await message.reply("❌ **Error:** No message content found!")
                return
            
            # Send initial confirmation
            status_msg = await message.reply("🔄 **Starting broadcast...**")
            
            results = {}
            
            # Broadcast to users
            if flags["user"]:
                await status_msg.edit_text("🔄 **Broadcasting to users...**")
                results["users"] = await self.broadcast_to_users(client, content, broadcast_id)
            
            # Broadcast to groups (only if not cancelled)
            if flags["group"] and broadcast_id in self.active_broadcasts:
                await status_msg.edit_text("🔄 **Broadcasting to groups...**")
                results["groups"] = await self.broadcast_to_groups(client, content, broadcast_id)
            
            # Calculate duration
            duration = datetime.now() - start_time
            
            # Generate summary
            summary = await self.generate_summary(results, flags, duration)
            await status_msg.edit_text(summary)
            
            # Log to logger group
            await self.log_broadcast(client, message, results, flags, duration)
            
        except Exception as e:
            logger.error(f"Broadcast {broadcast_id}: Critical error: {e}", exc_info=True)
            await message.reply(f"❌ **Broadcast failed:** {str(e)}")
        finally:
            self.active_broadcasts.discard(broadcast_id)
    
    async def generate_summary(self, results: Dict, flags: Dict, duration: timedelta) -> str:
        """✅ Generate detailed broadcast summary with error breakdown"""
        summary_parts = ["✅ **Broadcast Completed**\n"]
        
        if flags["user"] and "users" in results:
            user_stats = results["users"]
            summary_parts.append(
                f"👤 **Users:** {user_stats['success']}/{user_stats['total']} "
                f"({user_stats['failed']} failed)"
            )
            
            # ✅ Add error breakdown
            if user_stats.get('error_stats'):
                error_summary = self._format_error_stats(user_stats['error_stats'])
                summary_parts.append(f"   └─ Errors: {error_summary}")
        
        if flags["group"] and "groups" in results:
            group_stats = results["groups"]
            summary_parts.append(
                f"👥 **Groups:** {group_stats['success']}/{group_stats['total']} "
                f"({group_stats['failed']} failed)"
            )
            
            # ✅ Add error breakdown
            if group_stats.get('error_stats'):
                error_summary = self._format_error_stats(group_stats['error_stats'])
                summary_parts.append(f"   └─ Errors: {error_summary}")
        
        # Calculate totals
        total_success = sum(stats["success"] for stats in results.values())
        total_failed = sum(stats["failed"] for stats in results.values())
        total_targets = sum(stats["total"] for stats in results.values())
        
        summary_parts.append(f"\n**Total:** {total_success}/{total_targets} successful")
        
        if total_failed > 0:
            summary_parts.append(f"**Failed:** {total_failed}")
        
        # ✅ Add duration and rate
        duration_str = str(duration).split('.')[0]  # Remove microseconds
        rate = total_success / duration.total_seconds() if duration.total_seconds() > 0 else 0
        summary_parts.append(f"**Duration:** {duration_str}")
        summary_parts.append(f"**Rate:** {rate:.1f} msg/s")
        
        return "\n".join(summary_parts)
    
    def _format_error_stats(self, error_stats: Dict) -> str:
        """Format error statistics for summary"""
        error_names = {
            "user_blocked": "Blocked",
            "no_permission": "No Permission",
            "flood_wait_excessive": "FloodWait",
            "retry_failed": "Retry Failed",
            "rpc_error": "RPC Error",
            "unknown_error": "Unknown"
        }
        
        parts = []
        for error_type, count in error_stats.items():
            error_name = error_names.get(error_type, error_type)
            parts.append(f"{error_name}({count})")
        
        return ", ".join(parts)
    
    async def log_broadcast(self, client: Client, message: Message, results: Dict, 
                           flags: Dict, duration: timedelta):
        """✅ Log broadcast with detailed statistics"""
        if not LOG_GROUP_ID:
            return
        
        try:
            admin = message.from_user
            content_type = "Replied Message" if flags["is_reply"] else "Text Message"
            targets = []
            
            if flags["user"]:
                targets.append("Users")
            if flags["group"]:
                targets.append("Groups")
            
            duration_str = str(duration).split('.')[0]
            
            log_message = f"""
📢 **Broadcast Log**

**Admin:** {admin.mention} ({admin.id})
**Content Type:** {content_type}
**Targets:** {', '.join(targets)}
**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Duration:** {duration_str}

**Results:**
"""
            
            if "users" in results:
                user_stats = results["users"]
                log_message += f"👤 Users: {user_stats['success']}/{user_stats['total']} successful\n"
                if user_stats.get('flood_wait_total'):
                    log_message += f"   FloodWait Total: {user_stats['flood_wait_total']}s\n"
            
            if "groups" in results:
                group_stats = results["groups"]
                log_message += f"👥 Groups: {group_stats['success']}/{group_stats['total']} successful\n"
                if group_stats.get('flood_wait_total'):
                    log_message += f"   FloodWait Total: {group_stats['flood_wait_total']}s\n"
            
            await client.send_message(LOG_GROUP_ID, log_message)
        except Exception as e:
            logger.error(f"Failed to log broadcast: {e}")


# Global instance
broadcast_system = BroadcastSystem()


async def setup_broadcast_handlers(client: Client):
    """Setup broadcast command handlers"""
    
    @client.on_message(filters.command("broadcast"))
    async def broadcast_command(client: Client, message: Message):
        # Check if user is admin
        if not is_admin(message.from_user.id):
            await message.reply("❌ This command is only for bot admins.")
            return
        
        # Parse command
        flags = await broadcast_system.parse_broadcast_command(message)
        
        # Validate
        if not flags["user"] and not flags["group"]:
            await message.reply("❌ **Usage:** `/broadcast -user <message>` or `/broadcast -group <message>` or reply to a message with `/broadcast -user -group`")
            return
        
        if not flags["is_reply"] and not flags["message"]:
            await message.reply("❌ **Error:** No message content provided! Either reply to a message or provide text after the command.")
            return
        
        # Start broadcast in background
        asyncio.create_task(
            broadcast_system.execute_broadcast(client, message, flags)
        )
        
        # Immediate response
        targets = []
        if flags["user"]:
            targets.append("users")
        if flags["group"]:
            targets.append("groups")
        
        await message.reply(f"🔄 **Broadcast started!**\nTargets: {', '.join(targets)}\n\n"
                          f"I'll notify you when it's complete.")

    @client.on_message(filters.command("broadcast_status"))
    async def broadcast_status(client: Client, message: Message):
        """Check active broadcasts"""
        if not is_admin(message.from_user.id):
            return
        
        active_count = len(broadcast_system.active_broadcasts)
        if active_count == 0:
            await message.reply("✅ No active broadcasts running.")
        else:
            broadcast_list = "\n".join(f"• {bid}" for bid in list(broadcast_system.active_broadcasts)[:5])
            await message.reply(f"🔄 **Active broadcasts:** {active_count}\n\n{broadcast_list}")

    @client.on_message(filters.command("broadcast_cancel"))
    async def broadcast_cancel(client: Client, message: Message):
        """Cancel all active broadcasts"""
        if not is_admin(message.from_user.id):
            return
        
        cancelled_count = len(broadcast_system.active_broadcasts)
        broadcast_system.active_broadcasts.clear()
        
        await message.reply(f"✅ Cancelled {cancelled_count} active broadcast(s).")

    logger.info("✅ Broadcast handlers setup complete")
