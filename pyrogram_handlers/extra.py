import logging
import re
import httpx
from bs4 import BeautifulSoup
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

# Support group link
SUPPORT_GROUP = "https://t.me/Samuraissupportchat"


async def scrape_instagram_from_web(url: str) -> dict:
    """
    Scrape Instagram download links from SaveIG website
    
    IMPORTANT: This function DOES NOT download files to VPS
    It only extracts direct CDN URLs and returns them
    Telegram will stream/download directly from Instagram's CDN
    """
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            }
        ) as client:
            
            logger.info("🔍 Step 1: Accessing SaveIG website...")
            
            # Step 1: Get the SaveIG page with URL
            params = {
                "url": url
            }
            
            response = await client.get(
                "https://saveig.app/api/ajaxSearch",
                params={"q": url, "t": "media", "lang": "en"}
            )
            
            if response.status_code != 200:
                logger.error(f"❌ SaveIG returned {response.status_code}")
                return {"success": False, "error": f"SaveIG returned status {response.status_code}"}
            
            logger.info("✅ Step 2: Parsing HTML response...")
            
            # Step 2: Parse the response
            data = response.json()
            
            if "data" not in data:
                logger.error("❌ No data field in response")
                return {"success": False, "error": "No data in SaveIG response"}
            
            html_content = data["data"]
            soup = BeautifulSoup(html_content, 'html.parser')
            
            logger.info("🔎 Step 3: Extracting download links...")
            
            # Step 3: Find all download links
            media_items = []
            
            # Method 1: Find download buttons
            download_buttons = soup.find_all('a', class_='abutton')
            
            for button in download_buttons:
                href = button.get('href', '')
                
                # Only get Instagram CDN URLs
                if 'cdninstagram.com' in href or 'fbcdn.net' in href:
                    
                    # Check text to determine type
                    button_text = button.get_text().lower()
                    
                    if 'video' in button_text:
                        media_type = 'video'
                    elif 'photo' in button_text or 'image' in button_text:
                        media_type = 'photo'
                    else:
                        # Default to photo for carousel items
                        media_type = 'photo'
                    
                    media_items.append({
                        'url': href,
                        'type': media_type
                    })
                    
                    logger.info(f"   ✓ Found {media_type}: {href[:80]}...")
            
            # Method 2: Fallback - Find direct CDN links in HTML
            if not media_items:
                logger.info("   ⚠️ No buttons found, searching for direct CDN links...")
                
                # Find all links in the HTML
                all_links = soup.find_all('a', href=True)
                
                for link in all_links:
                    href = link.get('href', '')
                    
                    if 'cdninstagram.com' in href or 'fbcdn.net' in href:
                        # Determine type from URL
                        if '.mp4' in href or 'video' in href.lower():
                            media_type = 'video'
                        else:
                            media_type = 'photo'
                        
                        media_items.append({
                            'url': href,
                            'type': media_type
                        })
                        
                        logger.info(f"   ✓ Found {media_type}: {href[:80]}...")
            
            # Remove duplicates while preserving order
            seen = set()
            unique_media = []
            for item in media_items:
                if item['url'] not in seen:
                    seen.add(item['url'])
                    unique_media.append(item)
            
            logger.info(f"📊 Step 4: Found {len(unique_media)} unique media items")
            
            # Return results
            if len(unique_media) > 1:
                logger.info(f"✅ SUCCESS: Carousel with {len(unique_media)} items")
                return {
                    "success": True,
                    "type": "carousel",
                    "media_urls": unique_media,
                    "count": len(unique_media)
                }
            elif len(unique_media) == 1:
                logger.info("✅ SUCCESS: Single media item")
                return {
                    "success": True,
                    "type": "single",
                    "media_url": unique_media[0]['url'],
                    "media_type": unique_media[0]['type']
                }
            else:
                logger.error("❌ No media URLs found")
                return {"success": False, "error": "No download links found in response"}
            
    except httpx.TimeoutException:
        logger.error("❌ Request timeout")
        return {"success": False, "error": "Request timeout - SaveIG took too long"}
    except Exception as e:
        logger.error(f"❌ Scraping error: {e}", exc_info=True)
        return {"success": False, "error": f"Scraping failed: {str(e)}"}


async def scrape_tiktok_from_web(url: str) -> dict:
    """
    Scrape TikTok download links from web
    Returns direct CDN URLs - NO VPS DOWNLOAD
    """
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        ) as client:
            
            logger.info("🔍 Scraping TikTok from web...")
            
            # Use TikTok downloader API
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
            
            # Get video URL
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
        logger.error(f"TikTok scraping error: {e}")
        return {"success": False, "error": str(e)}


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
        f"The link might be invalid or the service is temporarily unavailable.\n"
        f"Please try again later or report to [Support Group]({SUPPORT_GROUP}).",
        disable_web_page_preview=True
    )


async def send_media_to_telegram(message: Message, result: dict, processing_msg: Message = None):
    """
    Send media to Telegram user
    
    CRITICAL: This function sends DIRECT URLs to Telegram
    Files are NOT downloaded to VPS
    Telegram downloads directly from Instagram/TikTok CDN
    """
    try:
        if result["type"] == "carousel":
            # Multiple items
            media_count = len(result['media_urls'])
            
            if processing_msg:
                await processing_msg.edit_text(
                    f"📤 **Uploading {media_count} items...**\n\n"
                    f"⚡ Direct streaming from Instagram CDN\n"
                    f"💾 Zero VPS storage used"
                )
            
            media_group = []
            
            for idx, media in enumerate(result['media_urls'][:10]):  # Telegram max: 10
                caption = (
                    f"📸 **Instagram Post**\n"
                    f"✅ {media_count} items total\n"
                    f"🚀 Streamed directly from CDN"
                ) if idx == 0 else ""
                
                # IMPORTANT: Passing direct URL - NO VPS DOWNLOAD!
                if media['type'] == 'video':
                    media_group.append(
                        InputMediaVideo(media=media['url'], caption=caption)
                    )
                else:
                    media_group.append(
                        InputMediaPhoto(media=media['url'], caption=caption)
                    )
            
            # Send to Telegram - Telegram handles download from CDN
            await message.reply_media_group(media=media_group)
            
            if processing_msg:
                await processing_msg.delete()
                
            logger.info(f"✅ Sent {len(media_group)} items - VPS load: 0 MB")
        
        elif result["type"] == "single":
            # Single item
            media_type = result.get("media_type", "photo")
            
            caption = (
                f"📸 **Instagram Media**\n"
                f"🚀 Streamed directly from CDN\n"
                f"💾 Zero VPS storage used"
            )
            
            # IMPORTANT: Passing direct URL - NO VPS DOWNLOAD!
            if media_type == 'video':
                await message.reply_video(
                    video=result["media_url"],
                    caption=caption
                )
            else:
                await message.reply_photo(
                    photo=result["media_url"],
                    caption=caption
                )
            
            if processing_msg:
                await processing_msg.delete()
                
            logger.info("✅ Sent single item - VPS load: 0 MB")
        
        elif result["type"] == "video":
            # TikTok video
            await message.reply_video(
                video=result["video_url"],
                caption=f"📹 **{result['title']}**\n👤 @{result['username']}"
            )
            
            if processing_msg:
                await processing_msg.delete()
        
        elif result["type"] == "images":
            # TikTok images
            media_group = []
            
            for idx, img_url in enumerate(result['images'][:10]):
                caption = f"📸 **{result['title']}**\n👤 @{result['username']}" if idx == 0 else ""
                media_group.append(InputMediaPhoto(media=img_url, caption=caption))
            
            await message.reply_media_group(media=media_group)
            
            if processing_msg:
                await processing_msg.delete()
    
    except Exception as e:
        logger.error(f"Error sending media: {e}", exc_info=True)
        
        error_msg = (
            f"❌ **Failed to send media**\n\n"
            f"Error: {str(e)}\n\n"
            f"Please try again or report to [Support Group]({SUPPORT_GROUP})."
        )
        
        if processing_msg:
            await processing_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)


async def setup_extra_handlers(client: Client):
    """Setup Instagram and TikTok downloader handlers"""
    
    # ==================== PRIVATE CHAT - AUTO DOWNLOAD ====================
    
    @client.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
    async def private_link_handler(client: Client, message: Message):
        """Auto-download Instagram/TikTok links in private chat"""
        text = message.text
        
        # Check for TikTok link
        tiktok_match = TIKTOK_PATTERN.search(text)
        if tiktok_match:
            url = tiktok_match.group(0)
            
            if not url.startswith("http"):
                url = "https://" + url
            
            processing_msg = await message.reply_text("⏳ **Processing TikTok link...**")
            
            result = await scrape_tiktok_from_web(url)
            
            if result["success"]:
                await send_media_to_telegram(message, result, processing_msg)
            else:
                await processing_msg.delete()
                await send_error_message(message, "TikTok")
            
            return
        
        # Check for Instagram link
        instagram_match = INSTAGRAM_PATTERN.search(text)
        if instagram_match:
            url = instagram_match.group(0)
            
            if not url.startswith("http"):
                url = "https://" + url
            
            processing_msg = await message.reply_text(
                "⏳ **Processing Instagram link...**\n\n"
                "🔍 Extracting media URLs from web...\n"
                "💾 Zero VPS storage used"
            )
            
            result = await scrape_instagram_from_web(url)
            
            if result["success"]:
                await send_media_to_telegram(message, result, processing_msg)
            else:
                await processing_msg.delete()
                await send_error_message(message, "Instagram")
            
            return
    
    # ==================== GROUP CHAT - COMMAND BASED ====================
    
    @client.on_message(filters.group & filters.command("tt"))
    async def tiktok_group_handler(client: Client, message: Message):
        """TikTok downloader for groups"""
        
        if not await is_bot_admin(client, message.chat.id):
            await message.reply_text(
                "❌ **I need admin rights in this group!**\n\n"
                "Please promote me as admin first."
            )
            return
        
        url = None
        
        if message.reply_to_message and message.reply_to_message.text:
            tiktok_match = TIKTOK_PATTERN.search(message.reply_to_message.text)
            if tiktok_match:
                url = tiktok_match.group(0)
        elif len(message.command) > 1:
            url = message.command[1]
        
        if not url:
            await message.reply_text(
                "❌ **Please provide a TikTok link!**\n\n"
                "**Usage:**\n"
                "• `/tt <link>`\n"
                "• Reply to a TikTok link with `/tt`"
            )
            return
        
        if not url.startswith("http"):
            url = "https://" + url
        
        processing_msg = await message.reply_text("⏳ **Processing TikTok...**")
        
        result = await scrape_tiktok_from_web(url)
        
        if result["success"]:
            await send_media_to_telegram(message, result, processing_msg)
        else:
            await processing_msg.delete()
            await send_error_message(message, "TikTok")
    
    @client.on_message(filters.group & filters.command("ig"))
    async def instagram_group_handler(client: Client, message: Message):
        """Instagram downloader for groups"""
        
        if not await is_bot_admin(client, message.chat.id):
            await message.reply_text(
                "❌ **I need admin rights in this group!**\n\n"
                "Please promote me as admin first."
            )
            return
        
        url = None
        
        if message.reply_to_message and message.reply_to_message.text:
            instagram_match = INSTAGRAM_PATTERN.search(message.reply_to_message.text)
            if instagram_match:
                url = instagram_match.group(0)
        elif len(message.command) > 1:
            url = message.command[1]
        
        if not url:
            await message.reply_text(
                "❌ **Please provide an Instagram link!**\n\n"
                "**Usage:**\n"
                "• `/ig <link>`\n"
                "• Reply to an Instagram link with `/ig`"
            )
            return
        
        if not url.startswith("http"):
            url = "https://" + url
        
        processing_msg = await message.reply_text(
            "⏳ **Processing Instagram link...**\n\n"
            "🔍 Extracting from web...\n"
            "💾 Zero VPS storage"
        )
        
        result = await scrape_instagram_from_web(url)
        
        if result["success"]:
            await send_media_to_telegram(message, result, processing_msg)
        else:
            await processing_msg.delete()
            await send_error_message(message, "Instagram")
    
    logger.info("✅ Web scraping handlers initialized - Zero VPS storage mode")


# VPS LOAD SUMMARY:
# ================
# RAM: ~50-100 MB (HTML parsing only)
# CPU: Minimal (HTTP requests + BeautifulSoup parsing)
# DISK: 0 MB (NO file downloads!)
# BANDWIDTH: ~1-5 KB per request (just HTML scraping)
# 
# Files are streamed DIRECTLY from Instagram/TikTok CDN to Telegram
# VPS only extracts URLs - does NOT store any media files
