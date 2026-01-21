import logging
import re
import httpx
import json
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
    r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/([\w\-]+)/?.*',
    re.IGNORECASE
)

# API Endpoints
TIKTOK_API = "https://tiktok-dl.hazex.workers.dev/"

# Support group link
SUPPORT_GROUP = "https://t.me/Samuraissupportchat"


async def download_tiktok(url: str) -> dict:
    """Download TikTok video or images using API"""
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


async def download_instagram_api_multiple(url: str) -> dict:
    """
    Try multiple Instagram download APIs
    """
    # Extract shortcode from URL
    shortcode_match = INSTAGRAM_PATTERN.search(url)
    if not shortcode_match:
        return {"success": False, "error": "Invalid Instagram URL"}
    
    shortcode = shortcode_match.group(1)
    logger.info(f"📌 Shortcode extracted: {shortcode}")
    
    apis_to_try = [
        # API 1: InstaDownloader
        {
            "name": "InstaDownloader",
            "url": f"https://v3.saveig.app/api/ajaxSearch",
            "method": "POST",
            "data": {
                "q": f"https://www.instagram.com/p/{shortcode}/",
                "t": "media",
                "lang": "en"
            },
            "headers": {
                "Content-Type": "application/x-www-form-urlencoded"
            }
        },
        # API 2: Inflact
        {
            "name": "Inflact",
            "url": f"https://inflact.com/downloader/instagram/post-photo-video/api/?url=https://www.instagram.com/p/{shortcode}/",
            "method": "GET",
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        },
        # API 3: SnapInsta
        {
            "name": "SnapInsta",
            "url": "https://snapinsta.app/action.php",
            "method": "POST",
            "data": {
                "url": f"https://www.instagram.com/p/{shortcode}/",
                "action": "post"
            },
            "headers": {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0"
            }
        }
    ]
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for api in apis_to_try:
            try:
                logger.info(f"🔄 Trying {api['name']}...")
                
                if api["method"] == "POST":
                    response = await client.post(
                        api["url"],
                        data=api.get("data", {}),
                        headers=api.get("headers", {})
                    )
                else:
                    response = await client.get(
                        api["url"],
                        headers=api.get("headers", {})
                    )
                
                if response.status_code != 200:
                    logger.warning(f"❌ {api['name']} returned status {response.status_code}")
                    continue
                
                # Parse response
                try:
                    data = response.json()
                except:
                    # Try parsing HTML response
                    html = response.text
                    data = {"html": html}
                
                logger.info(f"📦 {api['name']} response received")
                
                # Parse based on API
                result = None
                
                if api["name"] == "InstaDownloader":
                    result = parse_instadownloader_response(data)
                elif api["name"] == "Inflact":
                    result = parse_inflact_response(data)
                elif api["name"] == "SnapInsta":
                    result = parse_snapinsta_response(data)
                
                if result and result["success"]:
                    logger.info(f"✅ {api['name']} succeeded!")
                    return result
                
            except Exception as e:
                logger.error(f"❌ {api['name']} error: {e}")
                continue
    
    return {"success": False, "error": "All APIs failed"}


def parse_instadownloader_response(data: dict) -> dict:
    """Parse InstaDownloader API response"""
    try:
        if "data" in data:
            html = data["data"]
            
            # Extract all image/video URLs from HTML
            import re
            
            # Find all download links
            video_urls = re.findall(r'href="([^"]+)"[^>]*>Download \(Video\)', html)
            image_urls = re.findall(r'href="([^"]+)"[^>]*>Download \(Image\)', html)
            
            media_urls = []
            
            for url in video_urls:
                media_urls.append({"url": url, "type": "video"})
            
            for url in image_urls:
                media_urls.append({"url": url, "type": "photo"})
            
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
        logger.error(f"Parse error: {e}")
        return {"success": False, "error": str(e)}


def parse_inflact_response(data: dict) -> dict:
    """Parse Inflact API response"""
    try:
        if "url" in data:
            # Single media
            return {
                "success": True,
                "type": "single",
                "media_url": data["url"],
                "media_type": "photo" if data.get("type") == "image" else "video"
            }
        elif "items" in data:
            # Multiple media
            media_urls = []
            for item in data["items"]:
                if "url" in item:
                    media_urls.append({
                        "url": item["url"],
                        "type": "photo" if item.get("type") == "image" else "video"
                    })
            
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
        logger.error(f"Parse error: {e}")
        return {"success": False, "error": str(e)}


def parse_snapinsta_response(data: dict) -> dict:
    """Parse SnapInsta API response"""
    try:
        if "html" in data:
            html = data["html"]
            
            # Extract download URLs
            import re
            urls = re.findall(r'href="([^"]+)"[^>]*class="[^"]*download[^"]*"', html)
            
            media_urls = []
            for url in urls:
                # Determine type based on URL or extension
                media_type = "video" if any(ext in url.lower() for ext in ['.mp4', 'video']) else "photo"
                media_urls.append({"url": url, "type": media_type})
            
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
        logger.error(f"Parse error: {e}")
        return {"success": False, "error": str(e)}


async def download_instagram(url: str) -> dict:
    """
    Download Instagram media with multiple API fallbacks
    """
    result = await download_instagram_api_multiple(url)
    return result


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
            
            if media_type == "video":
                await message.reply_video(
                    video=result["media_url"],
                    caption=f"📸 **Instagram Media**"
                )
            else:
                await message.reply_photo(
                    photo=result["media_url"],
                    caption=f"📸 **Instagram Media**"
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
