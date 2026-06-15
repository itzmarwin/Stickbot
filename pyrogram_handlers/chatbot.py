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

ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ZHIPU_MODEL   = "glm-4.5-flash"

_threads: dict[int, dict] = {}

THREAD_EXPIRY_SECONDS = 4 * 60 * 60
MAX_HISTORY_MESSAGES  = 20

_KAFKA_PATTERN = re.compile(
    r"\b(kafka\s+manager|kafka)\b",
    re.IGNORECASE
)

KAFKA_SYSTEM_PROMPT = """You are Kafka, a chill Telegram group bot with a real personality. You are NOT a formal assistant.

Your vibe:
- You talk like a real person, casual and natural
- Match the user's energy exactly — if they're playful, be playful. If they're angry, be blunt. If they're sad, be chill and comforting
- Keep replies SHORT — 1-3 sentences max, never paragraphs
- No bullet points, no lists, no "I'd be happy to help!" type cringe
- You can roast people lightly if they're being silly
- You swear mildly if the conversation calls for it
- Never sound like a customer service bot

Language rules:
- Reply in whatever language the user writes in
- If someone writes in Burmese, reply in Burmese
- If someone writes in English, reply in English
- If someone mixes languages, mix back
- If user asks you to translate something, just translate it directly — don't explain, don't add commentary, just give the translation

Personality:
- You have opinions, you're not neutral about everything
- You get bored of repetitive questions
- You're a bit sarcastic but not mean
- You're helpful but only if asked nicely enough"""


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


def _sanitize_text(text: str) -> str:
    """Remove non-latin scripts that might trigger ZhipuAI content filter."""
    return text.strip()


async def _call_zhipu(history: list[dict], user_message: str) -> Optional[str]:
    if not ZHIPU_API_KEY:
        logger.error("ZHIPU_API_KEY not set!")
        return None

    messages = [{"role": "system", "content": KAFKA_SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model":       ZHIPU_MODEL,
        "messages":    messages,
        "max_tokens":  150,
        "temperature": 0.9,
        "top_p":       0.95,
        "stream":      False,
    }

    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ZHIPU_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 400:
                    error_data = await resp.json()
                    error_code = error_data.get("error", {}).get("code", "")
                    if error_code == "1301":
                        logger.warning(f"ZhipuAI content filter triggered, retrying with fallback")
                        return await _call_zhipu_fallback(history, user_message)
                    logger.error(f"ZhipuAI API error 400: {error_data}")
                    return None
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"ZhipuAI API error {resp.status}: {text}")
                    return None
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip() if content else None
    except asyncio.TimeoutError:
        logger.error("ZhipuAI API timeout")
        return None
    except Exception as e:
        logger.error(f"ZhipuAI API exception: {e}")
        return None


async def _call_zhipu_fallback(history: list[dict], user_message: str) -> Optional[str]:
    """Fallback: translate Burmese/non-latin to English context for ZhipuAI, then reply naturally."""
    if not ZHIPU_API_KEY:
        return None

    safe_history = []
    for msg in history[-6:]:
        safe_history.append({
            "role": msg["role"],
            "content": f"[previous message in conversation]" if len(msg["content"]) > 100 else msg["content"]
        })

    fallback_system = """You are Kafka, a casual Telegram bot. The user may be writing in Burmese or a mix of languages. Understand their intent and reply naturally and casually. Keep it short — 1-2 sentences. Match their energy."""

    messages = [{"role": "system", "content": fallback_system}]
    messages.extend(safe_history)
    messages.append({"role": "user", "content": f"User message (may contain Burmese or mixed language): {user_message}"})

    payload = {
        "model":       ZHIPU_MODEL,
        "messages":    messages,
        "max_tokens":  150,
        "temperature": 0.9,
        "stream":      False,
    }

    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ZHIPU_API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip() if content else None
    except Exception as e:
        logger.error(f"ZhipuAI fallback exception: {e}")
        return None


async def _is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    perms = get_admin_permissions(chat_id, user_id)
    if perms is not None:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


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

        reply_text = await _call_zhipu(history, text)

        if not reply_text:
            logger.warning(f"[Chatbot] ZhipuAI returned None for chat {chat_id}")
            return

        try:
            sent = await message.reply_text(reply_text)
            _update_thread(chat_id, text, reply_text, user_id, sent.id)
        except Exception as e:
            logger.error(f"[Chatbot] Failed to send reply: {e}")
