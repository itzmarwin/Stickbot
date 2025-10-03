"""Message templates for the bot"""

# Start command
START_MESSAGE = """
👋 <b>Welcome to Sticker Kang Bot!</b>

I can help you add images, GIFs, stickers, and videos to your personal sticker pack.

<b>Commands:</b>
/kang - Add a sticker to your pack
/packs - View your sticker pack
/help - Get help

<b>How to use:</b>
1. Send me an image, GIF, sticker, or video
2. Reply to it with /kang
3. I'll add it to your personal pack!

<b>✨ Special Features:</b>
• Use any Unicode fonts in pack names
• Add emojis and special characters
• Support for 𝐛𝐨𝐥𝐝, 𝕚𝕥𝕒𝕝𝕚𝕔, 𝓬𝓾𝓻𝓼𝓲𝓿𝓮 fonts
• Full creative freedom!

Let's get started! 🎨
"""

HELP_MESSAGE = """
<b>🔰 How to use Sticker Kang Bot</b>

<b>Creating Your Pack:</b>
1. Reply to any image/GIF/sticker/video with /kang
2. If it's your first time, I'll ask for a pack name
3. Send your desired pack name with any fonts/characters!
   • Use fancy fonts: 𝐛𝐨𝐥𝐝, 𝕚𝕥𝕒𝕝𝕚𝕔, 𝓬𝓾𝓻𝓼𝓲𝓿𝓮
   • Add emojis: 🔥 💎 ⚡
   • Use symbols: [], {}, @, #, *, etc.
4. Done! Your pack is created

<b>Adding Stickers:</b>
• Reply to media with /kang
• Supported: Images, GIFs, Stickers, Videos
• Videos auto-trimmed to fit 256KB limit

<b>Commands:</b>
/kang - Add media to your pack
/packs - View your pack info
/help - Show this message

<b>Pack Names:</b>
✅ Any Unicode characters allowed
✅ Maximum 64 characters
✅ Emojis and special fonts supported
"""

# Kang command
NEED_TO_START = """
𝐎𝐨𝐩𝐬! 𝐘𝐨𝐮 𝐧𝐞𝐞𝐝 𝐭𝐨 𝐬𝐭𝐚𝐫𝐭 𝐦𝐞 𝐟𝐢𝐫𝐬𝐭 𝐭𝐨 𝐮𝐬𝐞 𝐭𝐡𝐢𝐬 𝐛𝐨𝐭.
"""

ASK_PACK_NAME = """
<b>🎨 Let's create your sticker pack!</b>

Please send me a name for your pack.

<b>Examples:</b>
<code>𝐃𝐞𝐯𝐢𝐥'𝐬 𝐏𝐚𝐜𝐤 🔥</code>
<code>【MyStickers】✨</code>
<code>Cool Pack [2025]</code>

Your pack name will be formatted as:
<code>YourName ~ @BotUsername</code>

<i>✨ Use any Unicode fonts, emojis, or special characters!
📝 Pack name must be 1-64 characters</i>
"""

PACK_CREATED = """
✅ <b>New pack grabbed successfully!</b>

<b>Pack:</b> {pack_name}

Your first sticker has been added! 🎉
"""

STICKER_ADDED = """
✅ <b>Sticker grabbed successfully!</b>
"""

NO_MEDIA_REPLY = """
⚠️ <b>Please reply to a media message</b>

You need to reply to:
• Image
• GIF
• Sticker
• Video (under 4MB)

Then use /kang to add it to your pack.
"""

VIDEO_TOO_LARGE = """
⚠️ <b>This video is too large (over 4MB).</b>

Please send a smaller video file.

<i>Note: Videos are compressed to meet Telegram's 256KB limit for video stickers.</i>
"""

VIDEO_COMPRESSION_FAILED = """
⚠️ <b>Unable to process this video.</b>

The video couldn't be compressed to meet Telegram's 256KB limit.

<b>This might happen if:</b>
• Video has very high detail/motion
• Source quality is too high

<b>Try:</b>
• Use a shorter or simpler video
• Use lower quality source
• Try a GIF instead

Images and other stickers work great! 🎨
"""

PACK_NAME_TOO_LONG = """
⚠️ <b>Pack name is too long!</b>

Please keep it under 64 characters.
Try a shorter name.
"""

PACK_NAME_INVALID = """
⚠️ <b>Pack name is too long!</b>

Maximum length is 64 characters.
Your name has {length} characters.

Please use a shorter name.
"""

PROCESSING_MEDIA = "⌛ <b>Grabbing your sticker, hold on...</b>"

ERROR_OCCURRED = """
❌ <b>An error occurred</b>

Please try again later or contact support.
"""

# Packs command
NO_PACK_YET = """
<b>📦 You don't have a sticker pack yet!</b>

Use /kang on any image, GIF, sticker, or video to create your first pack!
"""

YOUR_PACK_INFO = """
<b>📦 Your Sticker Pack</b>

<b>Name:</b> {pack_name}
<b>Stickers:</b> {sticker_count}
<b>Created:</b> {created_at}

<b>Link:</b> {pack_link}

<a href="{pack_link}">Open Pack</a>
"""

# Logger messages
NEW_USER_LOG = """
👤 <b>New User Started Bot</b>

<b>User ID:</b> <code>{user_id}</code>
<b>Username:</b> @{username}
<b>Name:</b> {first_name}
<b>Time:</b> {time}
"""

BOT_ADDED_TO_GROUP = """
➕ <b>Bot Added to Group</b>

<b>Group:</b> {chat_title}
<b>Chat ID:</b> <code>{chat_id}</code>
<b>Added by:</b> {added_by}
<b>Time:</b> {time}
"""

BOT_REMOVED_FROM_GROUP = """
➖ <b>Bot Removed from Group</b>

<b>Group:</b> {chat_title}
<b>Chat ID:</b> <code>{chat_id}</code>
<b>Time:</b> {time}
"""
