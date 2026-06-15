import asyncio
import logging
import re
import time
from typing import Optional

import aiohttp
from pyrogram import Client, filters
from pyrogram.enums import ParseMode, ChatMemberStatus
from pyrogram.types import Message

from config import OWNER_ID
from mongo.chatbotdb import get_chatbot_status, set_chatbot_status
from pyrogram_handlers.caching import get_admin_permissions

logger = logging.getLogger(__name__)

# ─── DeepSeek Config ──────────────────────────────────────────────────────────
import os
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZHIPU_MODEL   = "glm-4.5-flash"

# ─── Thread Storage (RAM only) ────────────────────────────────────────────────
# Structure:
# {
#   chat_id: {
#       "history":        [...],   # list of {"role": "user"/"assistant", "content": "..."}
#       "last_activity":  float,   # time.time()
#       "last_bot_msg_id": int,    # bot ka last message ID
#       "participants":   set(),   # jo log thread mein aa chuke
#   }
# }
_threads: dict[int, dict] = {}

THREAD_EXPIRY_SECONDS = 4 * 60 * 60   # 4 hours
MAX_HISTORY_MESSAGES  = 20             # max messages to keep in history

# ─── Kafka trigger words ──────────────────────────────────────────────────────
_KAFKA_PATTERN = re.compile(
    r"\b(kafka\s+manager|kafka)\b",
    re.IGNORECASE
)

# ─── System Prompt ────────────────────────────────────────────────────────────
KAFKA_SYSTEM_PROMPT = """သင်သည် Kafka Manager ဖြစ်သည်။ Telegram group management bot တစ်ခုဖြစ်သည်။

သင့်အကြောင်း:
- သင့်နာမည်မှာ Kafka Manager သို့မဟုတ် Kafka ဟုခေါ်သည်
- သင်သည် group management လုပ်သော bot ဖြစ်သည်
- သင်တွင် ကိုယ်ရည်ကိုယ်သွေး ရှိသည်

စကားပြောပုံ:
- Default language: မြန်မာဘာသာ
- User က English သုံးလျှင် English ဖြင့် ပြန်ဖြေ
- User က ချစ်ချစ်ခင်ခင် ပြောလျှင် ချစ်ချစ်ခင်ခင် ပြန်ပြော
- User က ဒေါသတကြီး ပြောလျှင် ဒေါသတကြီး ပြန်ပြော
- User က ဖျားနာနေလျှင် စာနာသော tone သုံး
- Mood mirror လုပ်ရမည် — user ၏ tone အတိုင်း ပြန်ပြော
- "stupid", "idiot", "ပေါက်ကရ", "မိုက်တယ်" ကဲ့သို့ mild abusive words သုံးနိုင်သည် ဒေါသဖြင့် ပြောလျှင်
- Extreme hardcore abuse မသုံးရ
- Reply တိုတိုရေး — paragraph ကြီးများ မရေး
- Natural conversation လုပ်ရမည်
- သင်သည် bot ဟု acknowledge လုပ်ပေမယ့် personality ရှိသည်"""

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_expired(thread: dict) -> bool:
    return (time.time() - thread["last_activity"]) > THREAD_EXPIRY_SECONDS


def _get_thread(chat_id: int) -> Optional[dict]:
    thread = _threads.get(chat_id)
    if thread is None:
        return None
    if _is_expired(thread):
        del _threads[chat_id]
        return None
    return thread


def _create_thread(chat_id: int) -> dict:
    thread = {
        "history":         [],
        "last_activity":   time.time(),
        "last_bot_msg_id": None,
        "participants":    set(),
    }
    _threads[chat_id] = thread
    return thread


def _update_thread(chat_id: int, user_msg: str, bot_reply: str, user_id: int, bot_msg_id: int):
    thread = _threads.get(chat_id)
    if thread is None:
        return
    thread["history"].append({"role": "user",      "content": user_msg})
    thread["history"].append({"role": "assistant",  "content": bot_reply})
    # Trim history to max
    if len(thread["history"]) > MAX_HISTORY_MESSAGES * 2:
        thread["history"] = thread["history"][-(MAX_HISTORY_MESSAGES * 2):]
    thread["last_activity"]   = time.time()
    thread["last_bot_msg_id"] = bot_msg_id
    thread["participants"].add(user_id)


def _is_reply_to_bot(message: Message, bot_id: int, chat_id: int) -> bool:
    """Check if message is a reply to bot's last message in thread."""
    if not message.reply_to_message:
        return False
    thread = _threads.get(chat_id)
    if thread is None:
        return False
    replied_id = message.reply_to_message.id
    # Bot ke kisi bhi message ka reply ho
    return (
        message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == bot_id
    )


def _has_kafka_trigger(text: str) -> bool:
    return bool(_KAFKA_PATTERN.search(text))


async def _call_deepseek(history: list[dict], user_message: str) -> Optional[str]:
    """Call DeepSeek API with conversation history."""
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not set!")
        return None

    messages = [{"role": "system", "content": KAFKA_SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model":       DEEPSEEK_MODEL,
        "messages":    messages,
        "max_tokens":  300,
        "temperature": 0.85,
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                DEEPSEEK_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"DeepSeek API error {resp.status}: {text}")
                    return None
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except asyncio.TimeoutError:
        logger.error("DeepSeek API timeout")
        return None
    except Exception as e:
        logger.error(f"DeepSeek API exception: {e}")
        return None


async def _is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Check if user is admin."""
    perms = get_admin_permissions(chat_id, user_id)
    if perms is not None:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


# ─── Setup ────────────────────────────────────────────────────────────────────

async def setup_chatbot_handlers(client: Client):
    bot_me = await client.get_me()
    BOT_ID = bot_me.id

    # ── /chatbot on/off command ───────────────────────────────────────────────
    @client.on_message(filters.command("chatbot") & filters.group)
    async def chatbot_toggle(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return

        # Sirf admins
        if not await _is_admin(client, chat_id, user_id):
            await message.reply_text(
                "ဒီ command ကို admin တွေပဲ သုံးနိုင်တယ်။",
                parse_mode=ParseMode.HTML
            )
            return

        parts  = message.text.split()
        action = parts[1].lower() if len(parts) > 1 else ""

        if not action:
            status = await get_chatbot_status(chat_id)
            state  = "on ✅" if status else "off ❌"
            await message.reply_text(
                f"Chatbot အခုအချိန်မှာ <b>{state}</b> ဖြစ်နေတယ်။\n"
                f"<code>/chatbot on</code> သို့မဟုတ် <code>/chatbot off</code> သုံးပါ။",
                parse_mode=ParseMode.HTML
            )
            return

        if action == "on":
            if await get_chatbot_status(chat_id):
                await message.reply_text("Chatbot ရှိပြီးသားပဲ on ဖြစ်နေတယ်။")
                return
            await set_chatbot_status(chat_id, True)
            await message.reply_text(
                "✅ Chatbot ဖွင့်လိုက်တယ်။\n"
                "<b>Kafka</b> သို့မဟုတ် <b>Kafka Manager</b> ကိုခေါ်ပြီး စကားပြောနိုင်တယ်။",
                parse_mode=ParseMode.HTML
            )

        elif action == "off":
            if not await get_chatbot_status(chat_id):
                await message.reply_text("Chatbot ရှိပြီးသားပဲ off ဖြစ်နေတယ်။")
                return
            await set_chatbot_status(chat_id, False)
            # Clear thread for this group
            _threads.pop(chat_id, None)
            await message.reply_text("❌ Chatbot ပိတ်လိုက်တယ်။")

        else:
            await message.reply_text(
                "<code>/chatbot on</code> သို့မဟုတ် <code>/chatbot off</code> သုံးပါ။",
                parse_mode=ParseMode.HTML
            )


    # ── Main message watcher ──────────────────────────────────────────────────
    @client.on_message(filters.group & filters.text & ~filters.me, group=10)
    async def chatbot_watcher(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return

        # Bots ko ignore karo
        if message.from_user and message.from_user.is_bot:
            return

        # Chatbot enabled hai is group mein?
        if not await get_chatbot_status(chat_id):
            return

        text = message.text or ""
        if not text.strip():
            return

        thread      = _get_thread(chat_id)
        has_trigger = _has_kafka_trigger(text)
        is_reply_to_bot_msg = _is_reply_to_bot(message, BOT_ID, chat_id)

        # Decide karo respond karna hai ya nahi
        should_respond = False

        if has_trigger:
            # "Kafka" ya "Kafka Manager" mention hai
            should_respond = True
            if thread is None:
                thread = _create_thread(chat_id)

        elif thread is not None and is_reply_to_bot_msg:
            # Bot ke message ka reply — thread continue karo
            should_respond = True

        if not should_respond:
            return

        # DeepSeek ko call karo
        history = thread["history"] if thread else []

        # Typing indicator
        try:
            await client.send_chat_action(chat_id, "typing")
        except Exception:
            pass

        reply_text = await _call_deepseek(history, text)

        if not reply_text:
            # API fail — silent fail, no error message to group
            logger.warning(f"[Chatbot] DeepSeek returned None for chat {chat_id}")
            return

        try:
            sent = await message.reply_text(reply_text)
            _update_thread(chat_id, text, reply_text, user_id, sent.id)
        except Exception as e:
            logger.error(f"[Chatbot] Failed to send reply: {e}")
