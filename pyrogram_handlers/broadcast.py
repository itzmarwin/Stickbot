import asyncio
from typing import List, Dict, Union
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError, UserIsBlocked, ChatWriteForbidden

from config import is_admin, LOG_GROUP_ID
from database import get_all_users, get_served_chats


class BroadcastSystem:
    def __init__(self):
        self.active_broadcasts = set()
        self.flood_wait_threshold = 300
        self.base_delay_users = 0.2
        self.base_delay_groups = 0.3

    async def parse_broadcast_command(self, message: Message) -> Dict:
        command_text = message.text or message.caption or ""
        parts = command_text.split()

        flags = {
            "user": False,
            "group": False,
            "message": None,
            "is_reply": message.reply_to_message is not None
        }

        for part in parts:
            if part == "-user":
                flags["user"] = True
            elif part == "-group":
                flags["group"] = True

        if not flags["user"] and not flags["group"]:
            flags["user"] = True
            flags["group"] = True

        if flags["is_reply"]:
            flags["content"] = message.reply_to_message
        else:
            message_parts = []
            for part in parts:
                if part in ["/broadcast", "-user", "-group"]:
                    continue
                message_parts.append(part)

            flags["message"] = " ".join(message_parts) if message_parts else None

        return flags

    async def send_message_safe(self, client: Client, chat_id: int,
                                content: Union[Message, str], broadcast_id: str) -> tuple:
        try:
            if isinstance(content, Message):
                await content.copy(chat_id=chat_id)
            else:
                await client.send_message(chat_id=chat_id, text=content)
            return True, None

        except FloodWait as e:
            if e.value > 60:
                return False, "flood_wait_excessive"

            await asyncio.sleep(e.value + 1)

            try:
                if isinstance(content, Message):
                    await content.copy(chat_id=chat_id)
                else:
                    await client.send_message(chat_id=chat_id, text=content)
                return True, None
            except Exception:
                return False, "retry_failed"

        except UserIsBlocked:
            return False, "user_blocked"

        except ChatWriteForbidden:
            return False, "no_permission"

        except RPCError:
            return False, "rpc_error"

        except Exception:
            return False, "unknown_error"

    async def broadcast_to_users(self, client: Client, content: Union[Message, str],
                                 broadcast_id: str) -> Dict:
        users = await get_all_users()
        total = len(users)
        success = 0
        failed = 0
        flood_wait_total = 0
        error_stats = {}

        current_delay = self.base_delay_users
        consecutive_flood_waits = 0

        for i, user in enumerate(users):
            if broadcast_id not in self.active_broadcasts:
                break

            if flood_wait_total > self.flood_wait_threshold:
                break

            user_id = user["user_id"]

            send_success, error_type = await self.send_message_safe(client, user_id, content, broadcast_id)

            if send_success:
                success += 1
                consecutive_flood_waits = 0
            else:
                failed += 1
                error_stats[error_type] = error_stats.get(error_type, 0) + 1

                if error_type == "flood_wait_excessive":
                    consecutive_flood_waits += 1
                    flood_wait_total += 60

                    if consecutive_flood_waits >= 3:
                        current_delay *= 1.5

            if (i + 1) % 100 == 0:
                current_delay = min(current_delay + 0.1, 1.0)

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
        groups = await get_served_chats()
        total = len(groups)
        success = 0
        failed = 0
        flood_wait_total = 0
        error_stats = {}

        current_delay = self.base_delay_groups
        consecutive_flood_waits = 0

        for i, group in enumerate(groups):
            if broadcast_id not in self.active_broadcasts:
                break

            if flood_wait_total > self.flood_wait_threshold:
                break

            chat_id = group["chat_id"]

            send_success, error_type = await self.send_message_safe(client, chat_id, content, broadcast_id)

            if send_success:
                success += 1
                consecutive_flood_waits = 0
            else:
                failed += 1
                error_stats[error_type] = error_stats.get(error_type, 0) + 1

                if error_type == "flood_wait_excessive":
                    consecutive_flood_waits += 1
                    flood_wait_total += 60

                    if consecutive_flood_waits >= 3:
                        current_delay *= 1.5

            if (i + 1) % 50 == 0:
                current_delay = min(current_delay + 0.1, 2.0)

            await asyncio.sleep(current_delay)

        return {
            "success": success,
            "failed": failed,
            "total": total,
            "flood_wait_total": flood_wait_total,
            "error_stats": error_stats
        }

    async def execute_broadcast(self, client: Client, message: Message, flags: Dict):
        broadcast_id = f"broadcast_{message.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.active_broadcasts.add(broadcast_id)

        start_time = datetime.now()

        try:
            content = flags["content"] if flags["is_reply"] else flags["message"]

            if not content:
                await message.reply("❌ **Error:** No message content found!")
                return

            status_msg = await message.reply("🔄 **Starting broadcast...**")

            results = {}

            if flags["user"]:
                await status_msg.edit_text("🔄 **Broadcasting to users...**")
                results["users"] = await self.broadcast_to_users(client, content, broadcast_id)

            if flags["group"] and broadcast_id in self.active_broadcasts:
                await status_msg.edit_text("🔄 **Broadcasting to groups...**")
                results["groups"] = await self.broadcast_to_groups(client, content, broadcast_id)

            duration = datetime.now() - start_time

            summary = await self.generate_summary(results, flags, duration)
            await status_msg.edit_text(summary)

            await self.log_broadcast(client, message, results, flags, duration)

        except Exception as e:
            await message.reply(f"❌ **Broadcast failed:** {str(e)}")
        finally:
            self.active_broadcasts.discard(broadcast_id)

    async def generate_summary(self, results: Dict, flags: Dict, duration: timedelta) -> str:
        summary_parts = ["✅ **Broadcast Completed**\n"]

        if flags["user"] and "users" in results:
            user_stats = results["users"]
            summary_parts.append(
                f"👤 **Users:** {user_stats['success']}/{user_stats['total']} "
                f"({user_stats['failed']} failed)"
            )
            if user_stats.get('error_stats'):
                error_summary = self._format_error_stats(user_stats['error_stats'])
                summary_parts.append(f"   └─ Errors: {error_summary}")

        if flags["group"] and "groups" in results:
            group_stats = results["groups"]
            summary_parts.append(
                f"👥 **Groups:** {group_stats['success']}/{group_stats['total']} "
                f"({group_stats['failed']} failed)"
            )
            if group_stats.get('error_stats'):
                error_summary = self._format_error_stats(group_stats['error_stats'])
                summary_parts.append(f"   └─ Errors: {error_summary}")

        total_success = sum(stats["success"] for stats in results.values())
        total_failed = sum(stats["failed"] for stats in results.values())
        total_targets = sum(stats["total"] for stats in results.values())

        summary_parts.append(f"\n**Total:** {total_success}/{total_targets} successful")

        if total_failed > 0:
            summary_parts.append(f"**Failed:** {total_failed}")

        duration_str = str(duration).split('.')[0]
        rate = total_success / duration.total_seconds() if duration.total_seconds() > 0 else 0
        summary_parts.append(f"**Duration:** {duration_str}")
        summary_parts.append(f"**Rate:** {rate:.1f} msg/s")

        return "\n".join(summary_parts)

    def _format_error_stats(self, error_stats: Dict) -> str:
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
        except Exception:
            pass


broadcast_system = BroadcastSystem()


async def setup_broadcast_handlers(client: Client):

    @client.on_message(filters.command("broadcast"))
    async def broadcast_command(client: Client, message: Message):
        if not is_admin(message.from_user.id):
            await message.reply("❌ This command is only for bot admins.")
            return

        flags = await broadcast_system.parse_broadcast_command(message)

        if not flags["user"] and not flags["group"]:
            await message.reply("❌ **Usage:** `/broadcast -user <message>` or `/broadcast -group <message>` or reply to a message with `/broadcast -user -group`")
            return

        if not flags["is_reply"] and not flags["message"]:
            await message.reply("❌ **Error:** No message content provided! Either reply to a message or provide text after the command.")
            return

        asyncio.create_task(
            broadcast_system.execute_broadcast(client, message, flags)
        )

        targets = []
        if flags["user"]:
            targets.append("users")
        if flags["group"]:
            targets.append("groups")

        await message.reply(f"🔄 **Broadcast started!**\nTargets: {', '.join(targets)}\n\nI'll notify you when it's complete.")

    @client.on_message(filters.command("broadcast_status"))
    async def broadcast_status(client: Client, message: Message):
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
        if not is_admin(message.from_user.id):
            return

        cancelled_count = len(broadcast_system.active_broadcasts)
        broadcast_system.active_broadcasts.clear()

        await message.reply(f"✅ Cancelled {cancelled_count} active broadcast(s).")
