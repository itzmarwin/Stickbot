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


async def scrape_saveig(url: str) -> dict:
    """
    Scrape SaveIG.app website for Instagram download links
    No files stored on VPS - just extracts direct URLs
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Step 1: POST request to SaveIG
            logger.info("🔍 Scraping SaveIG...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Origin": "https://saveig.app",
                "Referer": "https://saveig.app/en"
            }
            
            data = {
                "q": url,
                "t": "media",
                "lang": "en"
            }
            
            response = await client.post(
                "https://v3.saveig.app/api/ajaxSearch",
                data=data,
                headers=headers
            )
            
            if response.status_code != 200:
                logger.warning(f"SaveIG returned status {response.status_code}")
                return {"success": False, "error": "SaveIG request failed"}
            
            # Step 2: Parse HTML response
            result = response.json()
            
            if "data" not in result:
                return {"success": False, "error": "No data in response"}
            
            html = result["data"]
            soup = BeautifulSoup(html, 'html.parser')
            
            # Step 3: Extract download links
            media_urls = []
            
            # Find all download links
            download_links = soup.find_all('a', {'class': 'abutton'})
            
            for link in download_links:
                href = link.get('href')
                if href and href.startswith('http'):
                    # Determine if video or image
                    text = link.get_text().lower()
                    
                    if 'video' in text:
                        media_urls.append({
                            "url": href,
                            "type": "video"
                        })
                    elif 'photo' in text or 'image' in text:
                        media_urls.append({
                            "url": href,
                            "type": "photo"
                        })
            
            # Step 4: Return results
            if len(media_urls) > 1:
                logger.info(f"✅ SaveIG found {len(media_urls)} media items (carousel)")
                return {
                    "success": True,
                    "type": "carousel",
                    "media_urls": media_urls
                }
            elif len(media_urls) == 1:
                logger.info("✅ SaveIG found single media")
                return {
                    "success": True,
                    "type": "single",
                    "media_url": media_urls[0]["url"],
                    "media_type": media_urls[0]["type"]
                }
            else:
                return {"success": False, "error": "No download links found"}
            
    except Exception as e:
        logger.error(f"SaveIG scraping error: {e}")
        return {"success": False, "error": str(e)}


async def scrape_snapinsta(url: str) -> dict:
    """
    Scrape SnapInsta.app website for Instagram download links
    Fallback method if SaveIG fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            logger.info("🔍 Scraping SnapInsta...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "*/*",
                "Origin": "https://snapinsta.app",
                "Referer": "https://snapinsta.app/"
            }
            
            data = {
                "url": url,
                "action": "post"
            }
            
            response = await client.post(
                "https://snapinsta.app/action.php",
                data=data,
                headers=headers
            )
            
            if response.status_code != 200:
                logger.warning(f"SnapInsta returned status {response.status_code}")
                return {"success": False, "error": "SnapInsta request failed"}
            
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract download links
            media_urls = []
            
            # Find download buttons/links
            download_links = soup.find_all('a', href=True)
            
            for link in download_links:
                href = link.get('href')
                
                # Check if it's a valid media URL
                if href and ('cdninstagram.com' in href or 'fbcdn.net' in href):
                    # Determine type
                    if '.mp4' in href or 'video' in href.lower():
                        media_type = "video"
                    else:
                        media_type = "photo"
                    
                    media_urls.append({
                        "url": href,
                        "type": media_type
                    })
            
            # Remove duplicates
            seen = set()
            unique_media = []
            for media in media_urls:
                if media["url"] not in seen:
                    seen.add(media["url"])
                    unique_media.append(media)
            
            if len(unique_media) > 1:
                logger.info(f"✅ SnapInsta found {len(unique_media)} media items (carousel)")
                return {
                    "success": True,
                    "type": "carousel",
                    "media_urls": unique_media
                }
            elif len(unique_media) == 1:
                logger.info("✅ SnapInsta found single media")
                return {
                    "success": True,
                    "type": "single",
                    "media_url": unique_media[0]["url"],
                    "media_type": unique_media[0]["type"]
                }
            else:
                return {"success": False, "error": "No download links found"}
            
    except Exception as e:
        logger.error(f"SnapInsta scraping error: {e}")
        return {"success": False, "error": str(e)}


async def download_instagram(url: str) -> dict:
    """
    Download Instagram media using web scraping
    Tries multiple methods with fallback
    """
    # Method 1: SaveIG (usually best for carousels)
    result = await scrape_saveig(url)
    if result["success"]:
        logger.info("✅ SaveIG succeeded")
        return result
    
    logger.warning(f"⚠️ SaveIG failed: {result.get('error')}")
    
    # Method 2: SnapInsta (fallback)
    result = await scrape_snapinsta(url)
    if result["success"]:
        logger.info("✅ SnapInsta succeeded")
        return result
    
    logger.warning(f"⚠️ SnapInsta failed: {result.get('error')}")
    
    return {"success": False, "error": "All scraping methods failed"}


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
    """
    Send Instagram media to user
    IMPORTANT: No files stored on VPS - direct URLs sent to Telegram
    """
    try:
        if result["type"] == "carousel":
            # Multiple images/videos
            media_count = len(result['media_urls'])
            
            if processing_msg:
                await processing_msg.edit_text(
                    f"⏳ **Uploading {media_count} items...**"
                )
            
            media_group = []
            for idx, media in enumerate(result['media_urls'][:10]):  # Telegram limit: 10 items
                caption = f"📸 **Instagram Carousel Post**\n✅ {media_count} items" if idx == 0 else ""
                
                # Direct URL - no VPS download!
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
            
            # Direct URL - no VPS download!
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
            
            processing_msg = await message.reply_text("⏳ **Fetching Instagram media...**")
            
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
                "• Reply to a message containing TikTok link with `/tt`"
            )
            return
        
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
                "• Reply to a message containing Instagram link with `/ig`"
            )
            return
        
        if not url.startswith("http"):
            url = "https://" + url
        
        processing_msg = await message.reply_text("⏳ **Fetching Instagram media...**")
        
        result = await download_instagram(url)
        
        if result["success"]:
            await send_instagram_media(message, result, processing_msg)
        else:
            await processing_msg.delete()
            await send_error_message(message, "Instagram")
    
    logger.info("✅ Extra handlers (TikTok & Instagram downloader) setup complete")
