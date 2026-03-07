import asyncio
import logging
from typing import List, Dict, Union
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait, RPCError, UserIsBlocked, ChatWriteForbidden,
    PeerIdInvalid, InputUserDeactivated, UserDeactivatedBan,
    ChannelPrivate, ChatAdminRequired, BotBlocked,
    UserBannedInChannel, ChatNotModified, Forbidden,
    UserNotParticipant, NotAcceptable
)

from config import is_admin, LOG_GROUP_ID
from database import get_all_users, get_served_chats

logger = logging.getLogger(__name__)


class BroadcastSystem:
    def __init__(self):
        self.active_broadcasts = set()
        self.flood_wait_threshold = 300
        self.base_delay_users = 0.05
        self.base_delay_groups = 0.1

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
            wait_time = e.value
            logger.warning(f"FloodWait {wait_time}s for chat {chat_id}")

            if wait_time > 60:
                return False, "flood_wait_excessive"

            await asyncio.sleep(wait_time + 1)

            try:
                if isinstance(content, Message):
                    await content.copy(chat_id=chat_id)
                else:
                    await client.send_message(chat_id=chat_id, text=content)
                return True, None
            except Exception as retry_err:
                logger.error(f"Retry failed for {chat_id}: {retry_err}")
                return False, "retry_failed"

        except (UserIsBlocked, BotBlocked):
            return False, "user_blocked"

        except (ChatWriteForbidden, ChatAdminRequired, Forbidden):
            return False, "no_permission"

        except (InputUserDeactivated, UserDeactivatedBan):
            return False, "user_deactivated"

        except (PeerIdInvalid, UserNotParticipant):
            return False, "invalid_peer"

        except ChannelPrivate:
            return False, "channel_private"

        except RPCError as e:
            logger.error(f"RPCError for chat {chat_id}: {e}")
            return False, "rpc_error"

        except Exception as e:
            # ✅ NOW WE LOG THE ACTUAL ERROR so you can see what's wrong
            logger.error(f"Unexpected error sending to {chat_id}: {type(e).__name__}: {e}")
            return False, f"unknown:{type(e).__name__}"

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

        logger.info(f"Starting user broadcast to {total} users")

        for i, user in enumerate(users):
            if broadcast_id not in self.active_broadcasts:
                logger.info("Broadcast cancelled, stopping.")
                break

            if flood_wait_total > self.flood_wait_threshold:
                logger.warning("Flood wait threshold exceeded, stopping broadcast.")
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
                        current_delay = min(current_delay * 1.5, 2.0)

            await asyncio.sleep(current_delay)

        logger.info(f"User broadcast done: {success}/{total} success, {failed} failed")

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

        logger.info(f"Starting group broadcast to {total} groups")

        for i, group in enumerate(groups):
            if broadcast_id not in self.active_broadcasts:
                logger.info("Broadcast cancelled, stopping.")
                break

            if flood_wait_total > self.flood_wait_threshold:
                logger.warning("Flood wait threshold exceeded, stopping broadcast.")
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
                        current_delay = min(current_delay * 1.5, 3.0)

            await asyncio.sleep(current_delay)

        logger.info(f"Group broadcast done: {success}/{total} success, {failed} failed")

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

            # ✅ Test send to yourself first to catch config issues early
            try:
                test_chat = message.from_user.id
                if isinstance(content, Message):
                    await content.copy(chat_id=test_chat)
                else:
                    await client.send_message(chat_id=test_chat, text=f"[Broadcast Test]\n\n{content}")
            except Exception as test_err:
                logger.error(f"Broadcast test send failed: {type(test_err).__name__}: {test_err}")
                await message.reply(
                    f"❌ **Broadcast aborted!**\n\n"
                    f"Test message failed: `{type(test_err).__name__}: {test_err}`\n\n"
                    f"Fix this error before broadcasting."
                )
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
            logger.error(f"Broadcast execution error: {type(e).__name__}: {e}", exc_info=True)
            await message.reply(f"❌ **Broadcast failed:** `{type(e).__name__}: {e}`")
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
            "user_deactivated": "Deactivated",
            "invalid_peer": "Invalid Peer",
            "channel_private": "Private Channel",
            "unknown_error": "Unknown"
        }

        parts = []
        for error_type, count in error_stats.items():
            # Handle dynamic unknown:ClassName errors
            if error_type.startswith("unknown:"):
                class_name = error_type.split(":", 1)[1]
                parts.append(f"{class_name}({count})")
            else:
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

            log_message = (
                f"📢 **Broadcast Log**\n\n"
                f"**Admin:** {admin.mention} ({admin.id})\n"
                f"**Content Type:** {content_type}\n"
                f"**Targets:** {', '.join(targets)}\n"
                f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"**Duration:** {duration_str}\n\n"
                f"**Results:**\n"
            )

            if "users" in results:
                u = results["users"]
                log_message += f"👤 Users: {u['success']}/{u['total']} successful\n"
                if u.get('error_stats'):
                    log_message += f"   Errors: {self._format_error_stats(u['error_stats'])}\n"

            if "groups" in results:
                g = results["groups"]
                log_message += f"👥 Groups: {g['success']}/{g['total']} successful\n"
                if g.get('error_stats'):
                    log_message += f"   Errors: {self._format_error_stats(g['error_stats'])}\n"

            await client.send_message(LOG_GROUP_ID, log_message)
        except Exception as e:
            logger.error(f"Failed to log broadcast: {e}")


broadcast_system = BroadcastSystem()


async def setup_broadcast_handlers(client: Client):

    @client.on_message(filters.command("broadcast"))
    async def broadcast_command(client: Client, message: Message):
        if not is_admin(message.from_user.id):
            await message.reply("❌ This command is only for bot admins.")
            return

        flags = await broadcast_system.parse_broadcast_command(message)

        if not flags["is_reply"] and not flags["message"]:
            await message.reply(
                "❌ **Error:** No message content provided!\n"
                "Reply to a message or provide text after the command.\n\n"
                "**Usage:**\n"
                "`/broadcast Hello everyone!`\n"
                "`/broadcast -user -group Hello!`\n"
                "Or reply to a message with `/broadcast`"
            )
            return

        asyncio.create_task(
            broadcast_system.execute_broadcast(client, message, flags)
        )

        targets = []
        if flags["user"]:
            targets.append("users")
        if flags["group"]:
            targets.append("groups")

        await message.reply(
            f"🔄 **Broadcast started!**\n"
            f"Targets: {', '.join(targets)}\n\n"
            f"I'll notify you when it's complete."
        )

    @client.on_message(filters.command("broadcast_status"))
    async def broadcast_status(client: Client, message: Message):
        if not is_admin(message.from_user.id):
            return

        active_count = len(broadcast_system.active_broadcasts)
        if active_count == 0:
            await message.reply("✅ No active broadcasts running.")
        else:
            broadcast_list = "\n".join(
                f"• {bid}" for bid in list(broadcast_system.active_broadcasts)[:5]
            )
            await message.reply(f"🔄 **Active broadcasts:** {active_count}\n\n{broadcast_list}")

    @client.on_message(filters.command("broadcast_cancel"))
    async def broadcast_cancel(client: Client, message: Message):
        if not is_admin(message.from_user.id):
            return

        cancelled_count = len(broadcast_system.active_broadcasts)
        broadcast_system.active_broadcasts.clear()
        await message.reply(f"✅ Cancelled {cancelled_count} active broadcast(s).")
