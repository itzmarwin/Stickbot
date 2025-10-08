# pyrogram_handlers/broadcast.py
import asyncio
import logging
from typing import List, Dict, Union
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError
from datetime import datetime

from config import is_admin, LOG_GROUP_ID
from database import get_all_users, get_served_chats

logger = logging.getLogger(__name__)

class BroadcastSystem:
    def __init__(self):
        self.active_broadcasts = set()
    
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
    
    async def send_message_safe(self, client: Client, chat_id: int, content: Union[Message, str], broadcast_id: str) -> bool:
        """Send message with flood control and error handling"""
        try:
            if isinstance(content, Message):
                # Forward the replied message
                await content.copy(chat_id=chat_id)
            else:
                # Send new message
                await client.send_message(chat_id=chat_id, text=content)
            return True
            
        except FloodWait as e:
            logger.warning(f"Broadcast {broadcast_id}: FloodWait for {e.value}s for chat {chat_id}")
            await asyncio.sleep(e.value)
            # Retry after waiting
            try:
                if isinstance(content, Message):
                    await content.copy(chat_id=chat_id)
                else:
                    await client.send_message(chat_id=chat_id, text=content)
                return True
            except Exception as retry_error:
                logger.error(f"Broadcast {broadcast_id}: Failed retry for chat {chat_id}: {retry_error}")
                return False
                
        except RPCError as e:
            logger.error(f"Broadcast {broadcast_id}: Failed to send to chat {chat_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Broadcast {broadcast_id}: Unexpected error for chat {chat_id}: {e}")
            return False
    
    async def broadcast_to_users(self, client: Client, content: Union[Message, str], broadcast_id: str) -> Dict:
        """Broadcast to all users"""
        users = await get_all_users()
        total = len(users)
        success = 0
        failed = 0
        
        logger.info(f"Broadcast {broadcast_id}: Starting user broadcast to {total} users")
        
        for i, user in enumerate(users):
            if broadcast_id not in self.active_broadcasts:
                logger.info(f"Broadcast {broadcast_id}: Cancelled by user")
                break
                
            user_id = user["user_id"]
            if await self.send_message_safe(client, user_id, content, broadcast_id):
                success += 1
            else:
                failed += 1
            
            # Progress logging every 50 users
            if (i + 1) % 50 == 0:
                logger.info(f"Broadcast {broadcast_id}: User progress {i+1}/{total}")
            
            # Small delay to avoid flood
            await asyncio.sleep(0.1)
        
        return {"success": success, "failed": failed, "total": total}
    
    async def broadcast_to_groups(self, client: Client, content: Union[Message, str], broadcast_id: str) -> Dict:
        """Broadcast to all groups"""
        groups = await get_served_chats()
        total = len(groups)
        success = 0
        failed = 0
        
        logger.info(f"Broadcast {broadcast_id}: Starting group broadcast to {total} groups")
        
        for i, group in enumerate(groups):
            if broadcast_id not in self.active_broadcasts:
                logger.info(f"Broadcast {broadcast_id}: Cancelled by user")
                break
                
            chat_id = group["chat_id"]
            if await self.send_message_safe(client, chat_id, content, broadcast_id):
                success += 1
            else:
                failed += 1
            
            # Progress logging every 20 groups
            if (i + 1) % 20 == 0:
                logger.info(f"Broadcast {broadcast_id}: Group progress {i+1}/{total}")
            
            # Small delay to avoid flood
            await asyncio.sleep(0.2)
        
        return {"success": success, "failed": failed, "total": total}
    
    async def execute_broadcast(self, client: Client, message: Message, flags: Dict):
        """Execute the broadcast in background"""
        broadcast_id = f"broadcast_{message.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.active_broadcasts.add(broadcast_id)
        
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
            
            # Broadcast to groups
            if flags["group"] and broadcast_id in self.active_broadcasts:
                await status_msg.edit_text("🔄 **Broadcasting to groups...**")
                results["groups"] = await self.broadcast_to_groups(client, content, broadcast_id)
            
            # Generate summary
            summary = await self.generate_summary(results, flags)
            await status_msg.edit_text(summary)
            
            # Log to logger group
            await self.log_broadcast(client, message, results, flags)
            
        except Exception as e:
            logger.error(f"Broadcast {broadcast_id}: Error: {e}")
            await message.reply(f"❌ **Broadcast failed:** {str(e)}")
        finally:
            self.active_broadcasts.discard(broadcast_id)
    
    async def generate_summary(self, results: Dict, flags: Dict) -> str:
        """Generate broadcast summary"""
        summary_parts = ["✅ **Broadcast Completed**\n"]
        
        if flags["user"] and "users" in results:
            user_stats = results["users"]
            summary_parts.append(
                f"👤 **Users:** {user_stats['success']}/{user_stats['total']} "
                f"({user_stats['failed']} failed)"
            )
        
        if flags["group"] and "groups" in results:
            group_stats = results["groups"]
            summary_parts.append(
                f"👥 **Groups:** {group_stats['success']}/{group_stats['total']} "
                f"({group_stats['failed']} failed)"
            )
        
        total_success = 0
        total_failed = 0
        total_targets = 0
        
        for stats in results.values():
            total_success += stats["success"]
            total_failed += stats["failed"]
            total_targets += stats["total"]
        
        summary_parts.append(f"\n**Total:** {total_success}/{total_targets} successful")
        
        if total_failed > 0:
            summary_parts.append(f"**Failed:** {total_failed}")
        
        return "\n".join(summary_parts)
    
    async def log_broadcast(self, client: Client, message: Message, results: Dict, flags: Dict):
        """Log broadcast to logger group"""
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
            
            log_message = f"""
📢 **Broadcast Log**

**Admin:** {admin.mention} ({admin.id})
**Content Type:** {content_type}
**Targets:** {', '.join(targets)}
**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Results:**
"""
            
            if "users" in results:
                user_stats = results["users"]
                log_message += f"👤 Users: {user_stats['success']}/{user_stats['total']} successful\n"
            
            if "groups" in results:
                group_stats = results["groups"]
                log_message += f"👥 Groups: {group_stats['success']}/{group_stats['total']} successful\n"
            
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
        
        await message.reply(f"🔄 **Broadcast started!**\nTargets: {', '.join(targets)}\n\nI'll notify you when it's complete.")

    @client.on_message(filters.command("broadcast_status"))
    async def broadcast_status(client: Client, message: Message):
        """Check active broadcasts"""
        if not is_admin(message.from_user.id):
            return
        
        active_count = len(broadcast_system.active_broadcasts)
        if active_count == 0:
            await message.reply("✅ No active broadcasts running.")
        else:
            await message.reply(f"🔄 **Active broadcasts:** {active_count}")

    @client.on_message(filters.command("broadcast_cancel"))
    async def broadcast_cancel(client: Client, message: Message):
        """Cancel all active broadcasts"""
        if not is_admin(message.from_user.id):
            return
        
        cancelled_count = len(broadcast_system.active_broadcasts)
        broadcast_system.active_broadcasts.clear()
        
        await message.reply(f"✅ Cancelled {cancelled_count} active broadcast(s).")

    logger.info("Broadcast handlers setup complete")
