import logging
import re
import httpx
import json
from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo
from pyrogram.enums import ChatMemberStatus

logger = logging.getLogger(__name__)

# Regex patterns
TIKTOK_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com|vm\.tiktok\.com)/[@\w\-\.]+/?.*',
    re.IGNORECASE
)

INSTAGRAM_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/([\w\-]+)/?.*',
    re.IGNORECASE
)

SUPPORT_GROUP = "https://t.me/Samuraissupportchat"


async def get_instagram_media_official(url: str) -> dict:
    """
    Get Instagram media using multiple methods
    Method 1: Direct Instagram Graph API scraping
    Method 2: Instagram oEmbed API
    Method 3: Fallback to working APIs
    """
    
    # Extract shortcode
    match = INSTAGRAM_PATTERN.search(url)
    if not match:
        return {"success": False, "error": "Invalid URL"}
    
    shortcode = match.group(1)
    logger.info(f"📌 Processing shortcode: {shortcode}")
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0"
        }
    ) as client:
        
        # ==================== METHOD 1: Instagram Page Scraping ====================
        logger.info("🔄 Method 1: Scraping Instagram page...")
        
        try:
            # Get Instagram post page
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            response = await client.get(post_url)
            
            if response.status_code == 200:
                html = response.text
                
                # Extract JSON data from page
                # Instagram embeds data in <script type="application/ld+json">
                json_match = re.search(r'<script type="application/ld\+json">(.+?)</script>', html, re.DOTALL)
                
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                        
                        # Check if it's a carousel
                        if isinstance(data, list):
                            # Multiple items
                            media_urls = []
                            
                            for item in data:
                                if 'contentUrl' in item:
                                    url = item['contentUrl']
                                    media_type = 'video' if item.get('@type') == 'VideoObject' else 'photo'
                                    media_urls.append({
                                        'url': url,
                                        'type': media_type
                                    })
                            
                            if len(media_urls) > 1:
                                logger.info(f"✅ Method 1: Found carousel with {len(media_urls)} items")
                                return {
                                    "success": True,
                                    "type": "carousel",
                                    "media_urls": media_urls
                                }
                        
                        # Single item
                        if 'contentUrl' in data:
                            logger.info("✅ Method 1: Found single item")
                            return {
                                "success": True,
                                "type": "single",
                                "media_url": data['contentUrl'],
                                "media_type": 'video' if data.get('@type') == 'VideoObject' else 'photo'
                            }
                            
                    except json.JSONDecodeError:
                        logger.warning("⚠️ Method 1: JSON parse failed")
                
                # Alternative: Find all image/video URLs in HTML
                logger.info("🔄 Method 1b: Extracting media from HTML...")
                
                # Find high-res images
                image_matches = re.findall(r'"display_url":"(https://[^"]+)"', html)
                video_matches = re.findall(r'"video_url":"(https://[^"]+)"', html)
                
                media_urls = []
                
                for video_url in video_matches:
                    # Unescape the URL
                    video_url = video_url.replace(r'\u0026', '&')
                    media_urls.append({'url': video_url, 'type': 'video'})
                
                for img_url in image_matches:
                    img_url = img_url.replace(r'\u0026', '&')
                    if img_url not in [m['url'] for m in media_urls]:  # Avoid duplicates
                        media_urls.append({'url': img_url, 'type': 'photo'})
                
                if len(media_urls) > 1:
                    logger.info(f"✅ Method 1b: Found {len(media_urls)} items")
                    return {
                        "success": True,
                        "type": "carousel",
                        "media_urls": media_urls[:10]  # Limit to 10
                    }
                elif len(media_urls) == 1:
                    logger.info("✅ Method 1b: Found single item")
                    return {
                        "success": True,
                        "type": "single",
                        "media_url": media_urls[0]['url'],
                        "media_type": media_urls[0]['type']
                    }
                    
        except Exception as e:
            logger.error(f"❌ Method 1 failed: {e}")
        
        # ==================== METHOD 2: Instagram oEmbed API ====================
        logger.info("🔄 Method 2: Trying oEmbed API...")
        
        try:
            oembed_url = f"https://api.instagram.com/oembed/?url=https://www.instagram.com/p/{shortcode}/"
            response = await client.get(oembed_url)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'thumbnail_url' in data:
                    logger.info("✅ Method 2: oEmbed success")
                    return {
                        "success": True,
                        "type": "single",
                        "media_url": data['thumbnail_url'],
                        "media_type": 'photo',
                        "note": "oEmbed API - may not include all carousel items"
                    }
                    
        except Exception as e:
            logger.error(f"❌ Method 2 failed: {e}")
        
        # ==================== METHOD 3: Fallback to Working API ====================
        logger.info("🔄 Method 3: Using fallback API...")
        
        try:
            api_url = "https://insta-dl.hazex.workers.dev/"
            response = await client.get(api_url, params={"url": url})
            
            if response.status_code == 200:
                data = response.json()
                
                if "result" in data:
                    result = data["result"]
                    media_url = result.get("url")
                    
                    if media_url:
                        logger.info("✅ Method 3: Hazex API success")
                        
                        extension = result.get("extension", "jpg").lower()
                        is_video = extension in ["mp4", "webm", "mov"]
                        
                        return {
                            "success": True,
                            "type": "single",
                            "media_url": media_url,
                            "media_type": "video" if is_video else "photo",
                            "note": "Limited to first item if carousel"
                        }
                        
        except Exception as e:
            logger.error(f"❌ Method 3 failed: {e}")
    
    return {"success": False, "error": "All methods failed"}


async def get_tiktok_media(url: str) -> dict:
    """Get TikTok media"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://tiktok-dl.hazex.workers.dev/",
                params={"url": url}
            )
            
            if response.status_code != 200:
                return {"success": False, "error": "API failed"}
            
            data = response.json()
            
            if "result" not in data:
                return {"success": False, "error": "Invalid response"}
            
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
            
            return {"success": False, "error": "No media found"}
            
    except Exception as e:
        logger.error(f"TikTok error: {e}")
        return {"success": False, "error": str(e)}


async def is_bot_admin(client: Client, chat_id: int) -> bool:
    """Check if bot is admin"""
    try:
        member = await client.get_chat_member(chat_id, client.me.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False


async def send_error_message(message: Message, platform: str):
    """Send error message"""
    await message.reply_text(
        f"❌ **Failed to download {platform} media**\n\n"
        f"Please try again or report to [Support]({SUPPORT_GROUP}).",
        disable_web_page_preview=True
    )


async def send_media(message: Message, result: dict, processing_msg: Message = None):
    """Send media to user - DIRECT URLs, NO VPS DOWNLOAD"""
    try:
        if result["type"] == "carousel":
            count = len(result['media_urls'])
            
            if processing_msg:
                await processing_msg.edit_text(f"📤 **Uploading {count} items...**")
            
            media_group = []
            for idx, media in enumerate(result['media_urls'][:10]):
                caption = f"📸 **Instagram Post**\n✅ {count} items" if idx == 0 else ""
                
                if media['type'] == 'video':
                    media_group.append(InputMediaVideo(media=media['url'], caption=caption))
                else:
                    media_group.append(InputMediaPhoto(media=media['url'], caption=caption))
            
            await message.reply_media_group(media=media_group)
            
            if processing_msg:
                await processing_msg.delete()
        
        elif result["type"] == "single":
            note = result.get("note", "")
            caption = f"📸 **Instagram Media**"
            if "carousel" in note.lower():
                caption += f"\n\n⚠️ {note}"
            
            if result.get("media_type") == 'video':
                await message.reply_video(video=result["media_url"], caption=caption)
            else:
                await message.reply_photo(photo=result["media_url"], caption=caption)
            
            if processing_msg:
                await processing_msg.delete()
        
        elif result["type"] == "video":
            await message.reply_video(
                video=result["video_url"],
                caption=f"📹 **{result['title']}**\n👤 @{result['username']}"
            )
            if processing_msg:
                await processing_msg.delete()
        
        elif result["type"] == "images":
            media_group = []
            for idx, img_url in enumerate(result['images'][:10]):
                caption = f"📸 **{result['title']}**\n👤 @{result['username']}" if idx == 0 else ""
                media_group.append(InputMediaPhoto(media=img_url, caption=caption))
            
            await message.reply_media_group(media=media_group)
            if processing_msg:
                await processing_msg.delete()
    
    except Exception as e:
        logger.error(f"Send error: {e}")
        if processing_msg:
            await processing_msg.edit_text(f"❌ Failed: {e}")


async def setup_extra_handlers(client: Client):
    """Setup handlers"""
    
    @client.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
    async def private_handler(client: Client, message: Message):
        """Private chat handler"""
        text = message.text
        
        # TikTok
        tiktok_match = TIKTOK_PATTERN.search(text)
        if tiktok_match:
            url = tiktok_match.group(0)
            if not url.startswith("http"):
                url = "https://" + url
            
            processing = await message.reply_text("⏳ **Processing TikTok...**")
            result = await get_tiktok_media(url)
            
            if result["success"]:
                await send_media(message, result, processing)
            else:
                await processing.delete()
                await send_error_message(message, "TikTok")
            return
        
        # Instagram
        instagram_match = INSTAGRAM_PATTERN.search(text)
        if instagram_match:
            url = instagram_match.group(0)
            if not url.startswith("http"):
                url = "https://" + url
            
            processing = await message.reply_text("⏳ **Processing Instagram...**")
            result = await get_instagram_media_official(url)
            
            if result["success"]:
                await send_media(message, result, processing)
            else:
                await processing.delete()
                await send_error_message(message, "Instagram")
            return
    
    @client.on_message(filters.group & filters.command("tt"))
    async def tt_group(client: Client, message: Message):
        """TikTok group command"""
        if not await is_bot_admin(client, message.chat.id):
            await message.reply_text("❌ **Need admin rights!**")
            return
        
        url = None
        if message.reply_to_message and message.reply_to_message.text:
            match = TIKTOK_PATTERN.search(message.reply_to_message.text)
            if match:
                url = match.group(0)
        elif len(message.command) > 1:
            url = message.command[1]
        
        if not url:
            await message.reply_text("❌ **Provide TikTok link!**\n\n`/tt <link>`")
            return
        
        if not url.startswith("http"):
            url = "https://" + url
        
        processing = await message.reply_text("⏳ **Processing...**")
        result = await get_tiktok_media(url)
        
        if result["success"]:
            await send_media(message, result, processing)
        else:
            await processing.delete()
            await send_error_message(message, "TikTok")
    
    @client.on_message(filters.group & filters.command("ig"))
    async def ig_group(client: Client, message: Message):
        """Instagram group command"""
        if not await is_bot_admin(client, message.chat.id):
            await message.reply_text("❌ **Need admin rights!**")
            return
        
        url = None
        if message.reply_to_message and message.reply_to_message.text:
            match = INSTAGRAM_PATTERN.search(message.reply_to_message.text)
            if match:
                url = match.group(0)
        elif len(message.command) > 1:
            url = message.command[1]
        
        if not url:
            await message.reply_text("❌ **Provide Instagram link!**\n\n`/ig <link>`")
            return
        
        if not url.startswith("http"):
            url = "https://" + url
        
        processing = await message.reply_text("⏳ **Processing...**")
        result = await get_instagram_media_official(url)
        
        if result["success"]:
            await send_media(message, result, processing)
        else:
            await processing.delete()
            await send_error_message(message, "Instagram")
    
    logger.info("✅ Instagram/TikTok handlers ready")
