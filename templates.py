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



# Get Sticker Command Templates
GETSTICKER_NO_REPLY = "❌ <b>Please reply to a sticker to get its image file.</b>"
GETSTICKER_NOT_STICKER = "❌ <b>The replied message is not a sticker.</b>"
GETSTICKER_VIDEO_NOT_SUPPORTED = "❌ <b>This is a video sticker. Use /getvidsticker for video stickers.</b>"
GETSTICKER_PROCESSING = "⏳ <b>Processing your sticker...</b>"

GETVIDSTICKER_NO_REPLY = "❌ <b>Please reply to a video sticker to get its video file.</b>"
GETVIDSTICKER_NOT_STICKER = "❌ <b>The replied message is not a sticker.</b>"
GETVIDSTICKER_NOT_VIDEO = "❌ <b>This is not a video sticker. Use /getsticker for static stickers.</b>"
GETVIDSTICKER_PROCESSING = "⏳ <b>Processing your video sticker...</b>"

# Success messages
STICKER_CONVERSION_SUCCESS = "✅ <b>Here's your sticker as an image:</b>"
VIDEO_STICKER_CONVERSION_SUCCESS = "✅ <b>Here's your sticker as a video:</b>"



# Start command templates
START_MESSAGE_WITH_IMAGE = """
🎨 <b>Welcome to Sticker Kang Bot!</b>

Create your own sticker packs easily!
• Convert images, videos, GIFs to stickers
• Manage multiple packs
• Publish your creations

Use the buttons below to get started!
"""

MANAGE_PACKS_MESSAGE = """
📦 <b>Your Sticker Packs</b>

Select a pack to manage or create a new one:
"""

NO_PACKS_MESSAGE = """
📦 <b>You don't have any packs yet!</b>

Create your first sticker pack to get started.
"""

PACK_OPTIONS_MESSAGE = """
🛠️ <b>Pack Options:</b> {pack_name}

Choose an action for this pack:
"""

RENAME_PACK_MESSAGE = """
✏️ <b>Rename Pack</b>

Please send the new name for your pack <b>"{pack_name}"</b>:

• Maximum 64 characters
• Can include emojis and special characters

Type /cancel to go back.
"""

DELETE_PACK_CONFIRMATION = """
🗑️ <b>Delete Pack</b>

Are you sure you want to delete <b>"{pack_name}"</b>?

This action cannot be undone! All stickers in this pack will be lost.

<b>Pack details:</b>
• Stickers: {sticker_count}
• Created: {created_date}
"""

PACK_DELETED_SUCCESS = """
✅ <b>Pack deleted successfully!</b>

Pack <b>"{pack_name}"</b> has been deleted.
"""

PACK_RENAMED_SUCCESS = """
✅ <b>Pack renamed successfully!</b>

<b>Old name:</b> {old_name}
<b>New name:</b> {new_name}
"""

PUBLISH_REQUEST_SENT = """
📤 <b>Publish Request Sent</b>

Your publish request for <b>"{pack_name}"</b> has been sent to the owner.

⏳ <b>Approval may take 4-5 hours.</b>

You will be notified once your pack is published.
"""

ADD_STICKER_INSTRUCTIONS = """
🎨 <b>Add Sticker to {pack_name}</b>

Send me an image, video, GIF, or sticker to add to your pack.

<b>Supported formats:</b>
• Images (JPEG, PNG, WebP)
• Videos (MP4, WebM - max 4MB)
• GIFs
• Other stickers

Type /cancel to go back.
"""

PACK_FULL_MESSAGE = """
❌ <b>Pack is Full</b>

Pack <b>"{pack_name}"</b> has reached the maximum limit of 120 stickers.

Please create a new pack to add more stickers.
"""

STICKER_ADDED_TO_PACK = """
✅ <b>Sticker Added</b>

Sticker successfully added to <b>"{pack_name}"</b>

Current sticker count: {sticker_count}/120
"""

# Add these new templates to templates.py

# Multiple packs support messages
PACK_FULL_MESSAGE = """
📦 Your current sticker pack is full (120 stickers limit).

You have {pack_count} pack(s) already.
Please provide a name for your new sticker pack:
"""

NEW_PACK_CREATED_MULTI = """
✅ <b>New pack created successfully!</b>

<b>Pack:</b> {pack_name}
<b>Total Packs:</b> {pack_count}

Your first sticker has been added! 🎉
"""

STICKER_ADDED_SIMPLE = "✅ <b>Sticker added successfully!</b>"

PACK_NOT_FOUND_MESSAGE = """
❌ Your sticker pack was not found.

Please provide a name for your new sticker pack:
"""

