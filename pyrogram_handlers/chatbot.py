import asyncio
import logging
import re
import time
import os
from typing import Optional

import aiohttp
from pyrogram import Client, filters
from pyrogram.enums import ParseMode, ChatMemberStatus
from pyrogram.types import Message

from mongo.chatbotdb import get_chatbot_status, set_chatbot_status
from pyrogram_handlers.caching import get_admin_permissions

logger = logging.getLogger(__name__)

# ─── Groq config ────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "qwen/qwen3-32b"

# ─── Thread settings ─────────────────────────────────────────────────────────
_threads: dict[int, dict] = {}

THREAD_EXPIRY_SECONDS = 4 * 60 * 60
MAX_HISTORY_MESSAGES  = 20

# ─── Trigger pattern ─────────────────────────────────────────────────────────
_KAFKA_PATTERN = re.compile(
    r"\b(kafka\s+manager|kafka)\b",
    re.IGNORECASE
)

KAFKA_SYSTEM_PROMPT = """သင်သည် Kafka ဆိုတဲ့ Telegram group bot တစ်ယောက်ဖြစ်တယ်။ သင်မှာ ကိုယ်ပိုင် personality ရှိတယ်။

အရေးကြီးဆုံး rules:
- မြန်မာဘာသာနဲ့ပဲ default ပြောတယ်
- User က English ရေးမှသာ English ပြန်ဖြေ၊ Hindi ရေးရင် Hindi ပြန်ဖြေ၊ mixed ဆို mixed ပြန်ပြော
- Reply အတိုလေး — ၁-၂ ကြောင်းပဲ၊ paragraph ကြီးတွေ မရေး
- Bullet point, list တွေ မသုံး
- Real လူတစ်ယောက်လို casual ပြော၊ formal assistant လို မပြော
- "ကျွန်တော် ကူညီရတာ ဝမ်းသာပါတယ်" စတဲ့ cringe phrases တွေ မသုံးရ
- User ရဲ့ mood ကို mirror လုပ် — သူ playful ဆို playful၊ ဒေါသနဲ့ ဆို blunt၊ sad ဆို chill
- Mild roast လုပ်လို့ရတယ် သူ silly ဖြစ်နေရင်
- "ပေါက်ကရ"၊ "မိုက်တယ်" စတဲ့ mild words သုံးလို့ရတယ် ဒေါသ context မှာ
- Hardcore abuse မသုံးရ
- User က translate လုပ်ခိုင်းရင် ရှင်းပြချက် မထည့်ဘဲ တိုက်ရိုက် translate ပေး
- Opinion ရှိတယ်၊ neutral ဆုံးဖြတ်ချက်တွေ မပေး
- မည်သည့် topic မဆို မြန်မာဘာသာနဲ့ meaningful ဖြေပေး — "မသိဘူး" သို့မဟုတ် "မဖြေနိုင်ဘူး" လို့ မပြော
- User ပြောတာကို နားလည်ပြီး သဘာဝကျကျ ဆက်စကားပြော"""


# ─── Thread helpers ───────────────────────────────────────────────────────────
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
    if len(thread["history"]) > MAX_HISTORY_MESSAGES * 2:
        thread["history"] = thread["history"][-(MAX_HISTORY_MESSAGES * 2):]
    thread["last_activity"]   = time.time()
    thread["last_bot_msg_id"] = bot_msg_id
    thread["participants"].add(user_id)


def _is_reply_to_bot(message: Message, bot_id: int, chat_id: int) -> bool:
    if not message.reply_to_message:
        return False
    if _threads.get(chat_id) is None:
        return False
    return (
        message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == bot_id
    )


def _has_kafka_trigger(text: str) -> bool:
    return bool(_KAFKA_PATTERN.search(text))


# ─── Groq API call ────────────────────────────────────────────────────────────
async def _call_groq(history: list[dict], user_message: str) -> Optional[str]:
    if not GROQ_API_KEY:
        logger.error("[Groq] GROQ_API_KEY not set in environment!")
        return None

    messages = [{"role": "system", "content": KAFKA_SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model":            GROQ_MODEL,
        "messages":         messages,
        "max_tokens":       200,
        "temperature":      0.9,
        "top_p":            0.95,
        "stream":           False,
        # Thinking/reasoning tokens band karo
        "reasoning_effort": "none",
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROQ_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                body = await resp.text()

                if resp.status == 429:
                    logger.warning("[Groq] Rate limited (429)")
                    return None

                if resp.status == 400:
                    logger.error(f"[Groq] 400 Bad Request: {body[:300]}")
                    return None

                if resp.status != 200:
                    logger.error(f"[Groq] HTTP {resp.status}: {body[:300]}")
                    return None

                try:
                    data = await resp.json(content_type=None)
                    content = data["choices"][0]["message"]["content"]
                    return content.strip() if content else None
                except Exception as e:
                    logger.error(f"[Groq] JSON parse failed: {e} | body={body[:200]}")
                    return None

    except asyncio.TimeoutError:
        logger.error("[Groq] Request timed out after 25s")
        return None
    except aiohttp.ClientConnectorError as e:
        logger.error(f"[Groq] Connection failed: {e}")
        return None
    except aiohttp.ServerDisconnectedError as e:
        logger.error(f"[Groq] Server disconnected: {e}")
        return None
    except Exception as e:
        logger.error(f"[Groq] Unexpected {type(e).__name__}: {e}")
        return None


# ─── Admin check ──────────────────────────────────────────────────────────────
async def _is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    perms = get_admin_permissions(chat_id, user_id)
    if perms is not None:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


# ─── Handlers ─────────────────────────────────────────────────────────────────
async def setup_chatbot_handlers(client: Client):
    bot_me = await client.get_me()
    BOT_ID = bot_me.id

    @client.on_message(filters.command("chatbot") & filters.group)
    async def chatbot_toggle(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return

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
            _threads.pop(chat_id, None)
            await message.reply_text("❌ Chatbot ပိတ်လိုက်တယ်။")

        else:
            await message.reply_text(
                "<code>/chatbot on</code> သို့မဟုတ် <code>/chatbot off</code> သုံးပါ။",
                parse_mode=ParseMode.HTML
            )

    @client.on_message(filters.group & filters.text & ~filters.me, group=10)
    async def chatbot_watcher(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return

        if message.from_user and message.from_user.is_bot:
            return

        if not await get_chatbot_status(chat_id):
            return

        text = message.text or ""
        if not text.strip():
            return

        thread              = _get_thread(chat_id)
        has_trigger         = _has_kafka_trigger(text)
        is_reply_to_bot_msg = _is_reply_to_bot(message, BOT_ID, chat_id)

        should_respond = False

        if has_trigger:
            should_respond = True
            if thread is None:
                thread = _create_thread(chat_id)
        elif thread is not None and is_reply_to_bot_msg:
            should_respond = True

        if not should_respond:
            return

        history = thread["history"] if thread else []

        try:
            await client.send_chat_action(chat_id, "typing")
        except Exception:
            pass

        reply_text = await _call_groq(history, text)

        if not reply_text:
            logger.warning(f"[Chatbot] Groq returned None for chat {chat_id} | msg={text[:50]!r}")
            return

        try:
            sent = await message.reply_text(reply_text)
            _update_thread(chat_id, text, reply_text, user_id, sent.id)
        except Exception as e:
            logger.error(f"[Chatbot] Failed to send reply: {e}")
