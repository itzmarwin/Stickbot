START_MESSAGE = "nigga"
HELP_MESSAGE = "nigga"

# Kang command
NEED_TO_START = """
𝐎𝐨𝐩𝐬! 𝐘𝐨𝐮 𝐧𝐞𝐞𝐝 𝐭𝐨 𝐬𝐭𝐚𝐫𝐭 𝐦𝐞 𝐟𝐢𝐫𝐬𝐭 𝐭𝐨 𝐮𝐬𝐞 𝐭𝐡𝐢𝐬 𝐛𝐨𝐭.
"""

ASK_PACK_NAME = "nigga pack name do"

PACK_CREATED = """
✅ <b>New pack grabbed successfully!</b>

<b>Pack:</b> {pack_name}

Your first sticker has been added! 🎉
"""

STICKER_ADDED = """
✅ <b>Sticker grabbed successfully!</b>
"""

NO_MEDIA_REPLY = """
⚠️ <b>Nigga...Please reply to a media message</b>
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

STICKER_ID_RESPONSE = """
<b>Sticker ID:</b> <code>{sticker_id}</code>
<b>Emoji:</b> {emoji}
"""

STICKER_ID_NO_REPLY = "❌ <b>Please reply to a sticker message to get its ID.</b>"

STICKER_ID_NOT_STICKER = "❌ <b>The replied message is not a sticker.</b>"

GENERIC_ERROR_MESSAGE = """
⚠️ <b>Oops — something went wrong.</b>
<b>Don't worry, our team is on it.</b>
If the issue continues, please report it here: <a href="https://t.me/YourSupportGroup"><b>Support Group</b></a>
"""
