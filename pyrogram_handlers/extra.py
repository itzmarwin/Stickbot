import logging
import re
import httpx
import tempfile
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from pyrogram.enums import ChatMemberStatus

logger = logging.getLogger(__name__)

# Regex patterns for link detection
TIKTOK_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com|vm\.tiktok\.com)/[@\w\-\.]+/?.*',
    re.IGNORECASE
)

INSTAGRAM_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/[\w\-]+/?.*',
    re.IGNORECASE
)

# API Endpoints
TIKTOK_API = "https://tiktok-dl.hazex.workers.dev/"

# Support group link
SUPPORT_GROUP = "https://t.me/Samuraissupportchat"


async def download_tiktok(url: str) -> dict:
    """
    Download TikTok video or images using API
    
    Args:
        url: TikTok video/slideshow URL
        
    Returns:
        dict with 'success', 'type', 'video_url'/'images', 'title', 'error' keys
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(TIKTOK_API, params={"url": url})
            
            if response.status_code != 200:
                return {"success": False, "error": "API request failed"}
            
            data = response.json()
            
            if "result" not in data:
                return {"success": False, "error": "Invalid API response"}
            
            result = data["result"]
            
            video_url = result.get("download_url", {}).get("without_watermark")
            images = result.get("images")
            
            if video_url:
                return {
                    "success": True,
                    "type": "video",
                    "video_url": video_url,
                    "title": result.get("title", "TikTok Video"),
                    "username": result.get("username", "Unknown")
                }
            elif images and isinstance(images, list) and len(images) > 0:
                return {
                    "success": True,
                    "type": "images",
                    "images": images,
                    "title": result.get("title", "TikTok Slideshow"),
                    "username": result.get("username", "Unknown")
                }
            else:
                return {"success": False, "error": "No video or images found in post"}
            
    except httpx.TimeoutException:
        return {"success": False, "error": "Request timeout"}
    except Exception as e:
        logger.error(f"TikTok download error: {e}")
        return {"success": False, "error": str(e)}


async def download_instagram_ytdlp(url: str) -> dict:
    """
    Download Instagram media using yt-dlp (supports carousels)
    
    Args:
        url: Instagram post/reel URL
        
    Returns:
        dict with success status and media info
    """
    try:
        # Run yt-dlp command to get info
        cmd = f'yt-dlp -J "{url}"'
        
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"yt-dlp error: {stderr.decode()}")
            return {"success": False, "error": "Failed to fetch Instagram data"}
        
        import json
        data = json.loads(stdout.decode())
        
        # Check if it's a carousel (multiple entries)
        if "entries" in data and len(data["entries"]) > 1:
            # Multiple images/videos
            media_urls = []
            
            for entry in data["entries"]:
                if "url" in entry:
                    media_type = "video" if entry.get("ext") in ["mp4", "webm"] else "photo"
                    media_urls.append({
                        "url": entry["url"],
                        "type": media_type
                    })
                elif "thumbnail" in entry:
                    # Fallback to thumbnail for images
                    media_urls.append({
                        "url": entry["thumbnail"],
                        "type": "photo"
                    })
            
            if media_urls:
                return {
                    "success": True,
                    "type": "carousel",
                    "media_urls": media_urls,
                    "title": data.get("title", "Instagram Post")
                }
        
        # Single media
        if "url" in data:
            return {
                "success": True,
                "type": "single",
                "media_url": data["url"],
                "media_type": "video" if data.get("ext") in ["mp4", "webm"] else "photo",
                "title": data.get("title", "Instagram Media")
            }
        elif "thumbnail" in data:
            return {
                "success": True,
                "type": "single",
                "media_url": data["thumbnail"],
                "media_type": "photo",
                "title": data.get("title", "Instagram Media")
            }
        
        return {"success": False, "error": "No media found"}
        
    except Exception as e:
        logger.error(f"yt-dlp Instagram download error: {e}")
        return {"success": False, "error": str(e)}


async def download_instagram_gallery_dl(url: str) -> dict:
    """
    Download Instagram media using gallery-dl (best for carousels)
    
    Args:
        url: Instagram post/reel URL
        
    Returns:
        dict with success status and media info
    """
    try:
        # Run gallery-dl command to get info
        cmd = f'gallery-dl -j --no-download "{url}"'
        
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"gallery-dl error: {stderr.decode()}")
            return {"success": False, "error": "Failed to fetch Instagram data"}
        
        import json
        
        # Parse JSON lines output
        media_urls = []
        for line in stdout.decode().strip().split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    
                    if "url" in data:
                        # Determine if it's video or photo
                        media_type = "video" if data.get("typename") == "GraphVideo" else "photo"
                        
                        media_urls.append({
                            "url": data["url"],
                            "type": media_type
                        })
                except json.JSONDecodeError:
                    continue
        
        if len(media_urls) > 1:
            return {
                "success": True,
                "type": "carousel",
                "media_urls": media_urls
            }
        elif len(media_urls) == 1:
            return {
                "success": True,
                "type": "single",
                "media_url": media_urls[0]["url"],
                "media_type": media_urls[0]["type"]
            }
        
        return {"success": False, "error": "No media found"}
        
    except Exception as e:
        logger.error(f"gallery-dl Instagram download error: {e}")
        return {"success": False, "error": str(e)}


async def download_instagram(url: str) -> dict:
    """
    Download Instagram media with fallback methods
    
    Args:
        url: Instagram post/reel URL
        
    Returns:
        dict with success status and media info
    """
    # Try gallery-dl first (best for carousels)
    result = await download_instagram_gallery_dl(url)
    if result["success"]:
        logger.info("✅ gallery-dl succeeded")
        return result
    
    logger.warning(f"⚠️ gallery-dl failed: {result.get('error')}")
    
    # Try yt-dlp as fallback
    result = await download_instagram_ytdlp(url)
    if result["success"]:
        logger.info("✅ yt-dlp succeeded")
        return result
    
    logger.warning(f"⚠️ yt-dlp failed: {result.get('error')}")
    
    return {"success": False, "error": "All download methods failed"}


async def is_bot_admin(client: Client, chat_id: int) -> bool:
    """Check if bot is admin in the group"""
    try:
        bot_member = await client.get_chat_member(chat_id, client.me.id)
        return bot_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"Error checking bot admin status: {e}")
        return False


async def send_error_message(message: Message, platform: str):
    """Send error message with support link"""
    await message.reply_text(
        f"❌ **Failed to download {platform} media**\n\n"
        f"The link might be invalid or the API is experiencing issues.\n"
        f"Please report this issue to our [Support Group]({SUPPORT_GROUP}).",
        disable_web_page_preview=True
    )


async def send_instagram_media(message: Message, result: dict, processing_msg: Message = None):
    """Helper function to send Instagram media (single or carousel)"""
    try:
        if result["type"] == "carousel":
            # Multiple images/videos
            media_count = len(result['media_urls'])
            
            if processing_msg:
                await processing_msg.edit_text(
                    f"⏳ **Downloading {media_count} items...**"
                )
            
            media_group = []
            for idx, media in enumerate(result['media_urls'][:10]):  # Telegram limit: 10 items
                caption = f"📸 **Instagram Carousel Post**\n{media_count} items total" if idx == 0 else ""
                
                if media.get("type") == "video":
                    media_group.append(InputMediaVideo(media=media["url"], caption=caption))
                else:
                    media_group.append(InputMediaPhoto(media=media["url"], caption=caption))
            
            await message.reply_media_group(media=media_group)
            if processing_msg:
                await processing_msg.delete()
        
        elif result["type"] == "single":
            # Single video or image
            media_type = result.get("media_type", "photo")
            title = result.get("title", "Instagram Media")
            
            if media_type == "video":
                await message.reply_video(
                    video=result["media_url"],
                    caption=f"📸 **{title}**"
                )
            else:
                await message.reply_photo(
                    photo=result["media_url"],
                    caption=f"📸 **{title}**"
                )
            
            if processing_msg:
                await processing_msg.delete()
    
    except Exception as e:
        logger.error(f"Error sending Instagram media: {e}")
        error_msg = f"❌ Failed to send media: {str(e)}\nPlease report to [Support Group]({SUPPORT_GROUP})."
        
        if processing_msg:
            await processing_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)


async def setup_extra_handlers(client: Client):
    """Setup TikTok and Instagram downloader handlers"""
    
    # ==================== PRIVATE CHAT - AUTO DOWNLOAD ====================
    
    @client.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
    async def private_link_handler(client: Client, message: Message):
        """Auto-download TikTok/Instagram links in private chat"""
        text = message.text
        
        # Check for TikTok link
        tiktok_match = TIKTOK_PATTERN.search(text)
        if tiktok_match:
            url = tiktok_match.group(0)
            
            # Add https if missing
            if not url.startswith("http"):
                url = "https://" + url
            
            processing_msg = await message.reply_text("⏳ **Downloading TikTok video...**")
            
            result = await download_tiktok(url)
            
            if result["success"]:
                try:
                    if result["type"] == "video":
                        await message.reply_video(
                            video=result["video_url"],
                            caption=f"📹 **{result['title']}**\n👤 @{result['username']}"
                        )
                        await processing_msg.delete()
                    elif result["type"] == "images":
                        await processing_msg.edit_text(f"⏳ **Downloading {len(result['images'])} images...**")
                        
                        media_group = []
                        
                        for idx, img_url in enumerate(result['images'][:10]):
                            caption = f"📸 **{result['title']}**\n👤 @{result['username']}" if idx == 0 else ""
                            media_group.append(InputMediaPhoto(media=img_url, caption=caption))
                        
                        await message.reply_media_group(media=media_group)
                        await processing_msg.delete()
                except Exception as e:
                    logger.error(f"Error sending TikTok media: {e}")
                    await processing_msg.edit_text(
                        f"❌ Failed to send media.\n"
                        f"Please report to [Support Group]({SUPPORT_GROUP})."
                    )
            else:
                await processing_msg.delete()
                await send_error_message(message, "TikTok")
            
            return
        
        # Check for Instagram link
        instagram_match = INSTAGRAM_PATTERN.search(text)
        if instagram_match:
            url = instagram_match.group(0)
            
            # Add https if missing
            if not url.startswith("http"):
                url = "https://" + url
            
            processing_msg = await message.reply_text("⏳ **Downloading Instagram media...**")
            
            result = await download_instagram(url)
            
            if result["success"]:
                await send_instagram_media(message, result, processing_msg)
            else:
                await processing_msg.delete()
                await send_error_message(message, "Instagram")
            
            return
    
    # ==================== GROUP CHAT - COMMAND BASED ====================
    
    @client.on_message(filters.group & filters.command("tt"))
    async def tiktok_group_handler(client: Client, message: Message):
        """TikTok downloader for groups with /tt command"""
        
        # Check if bot is admin
        if not await is_bot_admin(client, message.chat.id):
            await message.reply_text(
                "❌ **I need admin rights to download media in groups!**\n\n"
                "Please promote me as an admin first."
            )
            return
        
        # Get URL from command or replied message
        url = None
        
        if message.reply_to_message and message.reply_to_message.text:
            # Check if replied message contains TikTok link
            tiktok_match = TIKTOK_PATTERN.search(message.reply_to_message.text)
            if tiktok_match:
                url = tiktok_match.group(0)
        elif len(message.command) > 1:
            # URL provided as argument
            url = message.command[1]
        
        if not url:
            await message.reply_text(
                "❌ **Please provide a TikTok link!**\n\n"
                "**Usage:**\n"
                "• `/tt <link>`\n"
                "• Reply to a message containing TikTok link with `/tt`"
            )
            return
        
        # Add https if missing
        if not url.startswith("http"):
            url = "https://" + url
        
        processing_msg = await message.reply_text("⏳ **Downloading TikTok video...**")
        
        result = await download_tiktok(url)
        
        if result["success"]:
            try:
                if result["type"] == "video":
                    await message.reply_video(
                        video=result["video_url"],
                        caption=f"📹 **{result['title']}**\n👤 @{result['username']}"
                    )
                    await processing_msg.delete()
                elif result["type"] == "images":
                    await processing_msg.edit_text(f"⏳ **Downloading {len(result['images'])} images...**")
                    
                    media_group = []
                    
                    for idx, img_url in enumerate(result['images'][:10]):
                        caption = f"📸 **{result['title']}**\n👤 @{result['username']}" if idx == 0 else ""
                        media_group.append(InputMediaPhoto(media=img_url, caption=caption))
                    
                    await message.reply_media_group(media=media_group)
                    await processing_msg.delete()
            except Exception as e:
                logger.error(f"Error sending TikTok media in group: {e}")
                await processing_msg.edit_text(
                    f"❌ Failed to send media.\n"
                    f"Please report to [Support Group]({SUPPORT_GROUP})."
                )
        else:
            await processing_msg.delete()
            await send_error_message(message, "TikTok")
    
    @client.on_message(filters.group & filters.command("ig"))
    async def instagram_group_handler(client: Client, message: Message):
        """Instagram downloader for groups with /ig command"""
        
        # Check if bot is admin
        if not await is_bot_admin(client, message.chat.id):
            await message.reply_text(
                "❌ **I need admin rights to download media in groups!**\n\n"
                "Please promote me as an admin first."
            )
            return
        
        # Get URL from command or replied message
        url = None
        
        if message.reply_to_message and message.reply_to_message.text:
            # Check if replied message contains Instagram link
            instagram_match = INSTAGRAM_PATTERN.search(message.reply_to_message.text)
            if instagram_match:
                url = instagram_match.group(0)
        elif len(message.command) > 1:
            # URL provided as argument
            url = message.command[1]
        
        if not url:
            await message.reply_text(
                "❌ **Please provide an Instagram link!**\n\n"
                "**Usage:**\n"
                "• `/ig <link>`\n"
                "• Reply to a message containing Instagram link with `/ig`"
            )
            return
        
        # Add https if missing
        if not url.startswith("http"):
            url = "https://" + url
        
        processing_msg = await message.reply_text("⏳ **Downloading Instagram media...**")
        
        result = await download_instagram(url)
        
        if result["success"]:
            await send_instagram_media(message, result, processing_msg)
        else:
            await processing_msg.delete()
            await send_error_message(message, "Instagram")
    
    logger.info("✅ Extra handlers (TikTok & Instagram downloader) setup complete")
