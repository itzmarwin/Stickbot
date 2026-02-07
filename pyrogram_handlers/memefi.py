import logging
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, filters
from pyrogram.types import Message

logger = logging.getLogger(__name__)

FONT_SIZE_TOP = 60
FONT_SIZE_CENTER = 60
FONT_SIZE_BOTTOM = 60
TEXT_COLOR = (255, 255, 255)
OUTLINE_COLOR = (0, 0, 0)
OUTLINE_WIDTH = 1

TOP_POSITION = 0.01
CENTER_POSITION = 0.5
BOTTOM_POSITION = 0.95

SUPPORT_GROUP = "https://t.me/Samurais_Support"

# ✅ FONT PATHS
PRIMARY_FONT = "assets/default.ttf"  # English font (don't touch)
FALLBACK_FONT = "assets/noto-sans.ttf"  # Unicode font (Burmese, Chinese, Russian, Hindi)


def detect_unicode_script(text: str) -> bool:
    """
    Detect if text contains non-ASCII characters (Burmese, Chinese, Russian, Hindi, etc.)
    Returns True if Unicode characters found, False if only ASCII/English
    """
    try:
        text.encode('ascii')
        return False  # Pure English text
    except UnicodeEncodeError:
        return True  # Contains Unicode characters


def get_font(size: int, text: str = ""):
    """
    Smart font selection:
    - English text → default.ttf (primary font)
    - Unicode text (Burmese, Chinese, Russian, Hindi) → noto-sans.ttf (fallback)
    """
    
    # ✅ Check if text needs Unicode support
    needs_unicode = detect_unicode_script(text) if text else False
    
    if needs_unicode:
        # Try Unicode fallback font first
        if os.path.exists(FALLBACK_FONT):
            try:
                logger.info(f"Using Unicode font for: {text[:20]}...")
                return ImageFont.truetype(FALLBACK_FONT, size)
            except Exception as e:
                logger.warning(f"Unicode font failed, trying primary font: {e}")
        else:
            logger.warning(f"Unicode font not found at {FALLBACK_FONT}, using primary font")
    
    # ✅ Use primary English font (default behavior)
    if os.path.exists(PRIMARY_FONT):
        try:
            logger.info(f"Using primary font for: {text[:20] if text else 'default'}...")
            return ImageFont.truetype(PRIMARY_FONT, size)
        except Exception as e:
            logger.error(f"Error loading primary font {PRIMARY_FONT}: {e}")
            raise FileNotFoundError(f"Font file exists but failed to load: {PRIMARY_FONT}")
    else:
        raise FileNotFoundError(f"Primary font not found! Make sure {PRIMARY_FONT} exists in your repo.")


def get_hybrid_font(text: str, size: int):
    """
    Advanced: Returns best font for mixed-language text
    Tries Unicode font first if any Unicode chars detected
    """
    has_unicode = detect_unicode_script(text)
    
    # If has Unicode, try fallback font first
    if has_unicode and os.path.exists(FALLBACK_FONT):
        try:
            return ImageFont.truetype(FALLBACK_FONT, size)
        except Exception:
            pass
    
    # Default to primary font
    if os.path.exists(PRIMARY_FONT):
        try:
            return ImageFont.truetype(PRIMARY_FONT, size)
        except Exception as e:
            logger.error(f"Error loading font: {e}")
            raise FileNotFoundError(f"Font loading failed: {PRIMARY_FONT}")
    else:
        raise FileNotFoundError(f"Font not found: {PRIMARY_FONT}")


def wrap_text(text: str, font, max_width: int):
    """
    Text wrapping with Unicode support
    Handles Burmese, Chinese, Russian, Hindi properly
    """
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0]
        except Exception as e:
            logger.warning(f"getbbox failed for '{test_line}': {e}")
            # Fallback: assume average width
            width = len(test_line) * (max_width // 20)
        
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines


def draw_text_with_outline(draw, position, text, font, text_color, outline_color, outline_width):
    """
    Draw text with outline - works with all Unicode scripts
    """
    x, y = position
    
    # Draw outline
    for adj_x in range(-outline_width, outline_width + 1):
        for adj_y in range(-outline_width, outline_width + 1):
            if adj_x != 0 or adj_y != 0:
                try:
                    draw.text((x + adj_x, y + adj_y), text, font=font, fill=outline_color)
                except Exception as e:
                    logger.warning(f"Outline drawing failed: {e}")
    
    # Draw main text
    try:
        draw.text(position, text, font=font, fill=text_color)
    except Exception as e:
        logger.error(f"Text drawing failed for '{text}': {e}")


def parse_mmf_command(text: str):
    """
    Parse /mmf command - supports all languages
    """
    text = text.replace("/mmf", "").replace("/memefi", "").strip()
    
    if not text:
        return (None, None, None)
    
    parts = [p.strip() for p in text.split(";")]
    
    top_text = None
    center_text = None
    bottom_text = None
    
    if len(parts) == 1:
        if parts[0].startswith("-c "):
            center_text = parts[0][3:].strip()
        else:
            top_text = parts[0]
    
    elif len(parts) == 2:
        first = parts[0]
        second = parts[1]
        
        if first.startswith("-c "):
            center_text = first[3:].strip()
            bottom_text = second
        elif second.startswith("-c "):
            top_text = first
            center_text = second[3:].strip()
        else:
            top_text = first
            bottom_text = second
    
    else:
        top_text = parts[0]
        bottom_text = parts[1]
    
    return (top_text, center_text, bottom_text)


async def add_text_to_static_sticker(sticker_path: str, top_text: str = None, 
                                     center_text: str = None, bottom_text: str = None):
    """
    Add text to sticker with multi-language support
    Supports: English, Burmese (Myanmar), Chinese, Russian, Hindi, and more
    """
    try:
        img = Image.open(sticker_path).convert("RGBA")
        width, height = img.size
        
        text_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)
        
        max_text_width = int(width * 0.85)
        
        # ✅ TOP TEXT - Smart font selection
        if top_text:
            font = get_hybrid_font(top_text, FONT_SIZE_TOP)
            lines = wrap_text(top_text, font, max_text_width)
            
            line_height = FONT_SIZE_TOP + 15
            y = int(height * TOP_POSITION)
            
            for line in lines:
                try:
                    bbox = font.getbbox(line)
                    text_width = bbox[2] - bbox[0]
                except Exception:
                    text_width = len(line) * (FONT_SIZE_TOP // 2)
                
                x = (width - text_width) // 2
                
                draw_text_with_outline(
                    draw, (x, y), line, font, 
                    TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH
                )
                y += line_height
        
        # ✅ CENTER TEXT - Smart font selection
        if center_text:
            font = get_hybrid_font(center_text, FONT_SIZE_CENTER)
            lines = wrap_text(center_text, font, max_text_width)
            
            line_height = FONT_SIZE_CENTER + 15
            total_height = len(lines) * line_height
            y = int(height * CENTER_POSITION) - (total_height // 2)
            
            for line in lines:
                try:
                    bbox = font.getbbox(line)
                    text_width = bbox[2] - bbox[0]
                except Exception:
                    text_width = len(line) * (FONT_SIZE_CENTER // 2)
                
                x = (width - text_width) // 2
                
                draw_text_with_outline(
                    draw, (x, y), line, font, 
                    TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH
                )
                y += line_height
        
        # ✅ BOTTOM TEXT - Smart font selection
        if bottom_text:
            font = get_hybrid_font(bottom_text, FONT_SIZE_BOTTOM)
            lines = wrap_text(bottom_text, font, max_text_width)
            
            line_height = FONT_SIZE_BOTTOM + 15
            total_height = len(lines) * line_height
            y = int(height * BOTTOM_POSITION) - total_height
            
            for line in lines:
                try:
                    bbox = font.getbbox(line)
                    text_width = bbox[2] - bbox[0]
                except Exception:
                    text_width = len(line) * (FONT_SIZE_BOTTOM // 2)
                
                x = (width - text_width) // 2
                
                draw_text_with_outline(
                    draw, (x, y), line, font, 
                    TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH
                )
                y += line_height
        
        final_image = Image.alpha_composite(img, text_layer)
        
        final_image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        
        sticker_canvas = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
        
        offset = ((512 - final_image.size[0]) // 2, (512 - final_image.size[1]) // 2)
        sticker_canvas.paste(final_image, offset, final_image)
        
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        output_path = temp_dir / f"meme_static_{os.getpid()}.webp"
        
        sticker_canvas.save(str(output_path), format='WEBP', quality=95)
        
        return str(output_path)
    
    except Exception as e:
        logger.error(f"Error adding text to static sticker: {e}", exc_info=True)
        return None


async def setup_memefi_handlers(client: Client):
    
    @client.on_message(filters.command(["mmf", "memefi"]) & (filters.group | filters.private))
    async def memefi_command(client: Client, message: Message):
        try:
            if not message.reply_to_message:
                await message.reply_text(
                    "Please reply to a sticker.\n\n"
                    "How to use:\n"
                    "• /mmf Text (top only)\n"
                    "• /mmf Text1 ; Text2 (top and bottom)\n"
                    "• /mmf -c Text (center only)\n"
                    "• /mmf Text ; -c Center (top and center)\n"
                    "• /mmf -c Center ; Bottom (center and bottom)"
                )
                return
            
            replied_msg = message.reply_to_message
            if not replied_msg.sticker:
                await message.reply_text("That's not a sticker. Please reply to a sticker and add your text.")
                return
            
            if replied_msg.sticker.is_video:
                await message.reply_text("Video stickers are not supported yet. Please use image stickers only.")
                return
            
            top_text, center_text, bottom_text = parse_mmf_command(message.text)
            
            if not top_text and not center_text and not bottom_text:
                await message.reply_text(
                    "Please provide some text.\n\n"
                    "Usage: /mmf Your Text Here\n"
                    "Or: /mmf Top ; Bottom\n\n"
                    "✅ Works with Burmese, Chinese, Russian, Hindi!"
                )
                return
            
            processing_msg = await message.reply_text("Memifying this Sticker! Please wait.")
            
            temp_dir = Path("temp")
            temp_dir.mkdir(exist_ok=True)
            
            sticker_path = temp_dir / f"sticker_{message.from_user.id}.webp"
            await client.download_media(replied_msg.sticker.file_id, file_name=str(sticker_path))
            
            result_path = await add_text_to_static_sticker(
                str(sticker_path),
                top_text=top_text,
                center_text=center_text,
                bottom_text=bottom_text
            )
            
            if not result_path:
                await processing_msg.edit_text(
                    f"Failed to create your Sticker. Please try again.\n\n"
                    f"If this issue persists, report it in our support group: {SUPPORT_GROUP}"
                )
                return
            
            await message.reply_sticker(sticker=result_path)
            
            try:
                os.remove(sticker_path)
                os.remove(result_path)
            except:
                pass
            
            await processing_msg.delete()
            
            logger.info(f"MemeFi: Created meme for user {message.from_user.id}")
        
        except FileNotFoundError as e:
            logger.error(f"Font error: {e}")
            try:
                await message.reply_text(
                    f"Font file not found. Please contact the bot owner.\n\n"
                    f"Make sure both fonts exist:\n"
                    f"• assets/default.ttf (English)\n"
                    f"• assets/noto-sans.ttf (Unicode)\n\n"
                    f"Support: {SUPPORT_GROUP}"
                )
            except:
                pass
        
        except Exception as e:
            logger.error(f"Error in memefi command: {e}", exc_info=True)
            try:
                await message.reply_text(
                    f"Something went wrong. Please try again later.\n\n"
                    f"If the problem continues, report it here: {SUPPORT_GROUP}"
                )
            except:
                pass
    
    logger.info("MemeFi handlers setup complete - Multi-language support enabled!")
