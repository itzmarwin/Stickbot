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

Let's get started! 🎨
"""

HELP_MESSAGE = """
<b>🔰 How to use Sticker Kang Bot</b>

<b>Creating Your Pack:</b>
1. Reply to any image/GIF/sticker/video with /kang
2. If it's your first time, I'll ask for a pack name
3. Send your desired pack name (e.g., "My Cool Pack")
4. Done! Your pack is created

<b>Adding Stickers:</b>
• Reply to media with /kang
• I support: Images, GIFs, Stickers, Videos
• Videos are automatically compressed to 256KB

<b>Commands:</b>
/kang - Add media to your pack
/packs - View your pack info
/help - Show this message

<b>Tips:</b>
• Pack names must be 1-64 characters
• Videos under 4MB work best
• Each pack can have up to 120 stickers
• Video stickers are limited to 3 seconds
"""

# Kang command
NEED_TO_START = """
𝐎𝐨𝐩𝐬! 𝐘𝐨𝐮 𝐧𝐞𝐞𝐝 𝐭𝐨 𝐬𝐭𝐚𝐫𝐭 𝐦𝐞 𝐟𝐢𝐫𝐬𝐭 𝐭𝐨 𝐮𝐬𝐞 𝐭𝐡𝐢𝐬 𝐛𝐨𝐭.
"""

ASK_PACK_NAME = """
<b>🎨 Let's create your sticker pack!</b>

Please send me a name for your pack.

<b>Example:</b> <code>devil pack @itzdevil</code>

Your pack name will be formatted as:
<code>YourName ~ @BotUsername</code>

<i>Note: Pack name must be 1-64 characters</i>
"""

PACK_CREATED = """
✅ <b>Pack created successfully!</b>

<b>Pack Name:</b> {pack_name}
<b>Link:</b> {pack_link}

Your first sticker has been added! 🎉
"""

STICKER_ADDED = """
✅ <b>Added to your pack!</b>

<a href="{pack_link}">View Your Pack</a>
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
⚠️ <b>Invalid pack name!</b>

Pack names can only contain:
• Letters (a-z, A-Z)
• Numbers (0-9)
• Underscores (_)
• Spaces

Please try again with a valid name.
"""

PROCESSING_MEDIA = "⏳ Processing your media..."

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
