import logging
import os
import io
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

# ✅ UPDATED: Bigger font sizes
FONT_SIZE_TOP = 80
FONT_SIZE_CENTER = 70
FONT_SIZE_BOTTOM = 80
TEXT_COLOR = (255, 255, 255)  # White
OUTLINE_COLOR = (0, 0, 0)  # Black
OUTLINE_WIDTH = 4

# Position settings
TOP_POSITION = 0.1  # 10% from top
CENTER_POSITION = 0.5  # 50% (middle)
BOTTOM_POSITION = 0.9  # 90% from top


def check_ffmpeg_installed():
    """Check if FFmpeg is installed"""
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def get_font(size: int):
    """Get Impact font or fallback to default"""
    try:
        # Try to load Impact font (Windows)
        font_path = "C:/Windows/Fonts/impact.ttf"
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except:
        pass
    
    try:
        # Try Linux path
        font_path = "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf"
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except:
        pass
    
    try:
        # Fallback: Arial Bold
        return ImageFont.truetype("arial.ttf", size)
    except:
        # Ultimate fallback: default font
        return ImageFont.load_default()


def wrap_text(text: str, font, max_width: int):
    """Wrap text to fit within max_width"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]
        
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
    """Draw text with outline (stroke effect)"""
    x, y = position
    
    # Draw outline (black)
    for adj_x in range(-outline_width, outline_width + 1):
        for adj_y in range(-outline_width, outline_width + 1):
            draw.text((x + adj_x, y + adj_y), text, font=font, fill=outline_color)
    
    # Draw main text (white)
    draw.text(position, text, font=font, fill=text_color)


def parse_mmf_command(text: str):
    """
    Parse MMF/MEMEFI command
    
    Returns: (top_text, center_text, bottom_text)
    """
    # Remove command
    text = text.replace("/mmf", "").replace("/memefi", "").strip()
    
    if not text:
        return (None, None, None)
    
    # Split by semicolon
    parts = [p.strip() for p in text.split(";")]
    
    top_text = None
    center_text = None
    bottom_text = None
    
    if len(parts) == 1:
        # Single text
        if parts[0].startswith("-c "):
            center_text = parts[0][3:].strip()
        else:
            top_text = parts[0]
    
    elif len(parts) == 2:
        # Two texts
        first = parts[0]
        second = parts[1]
        
        # Check for -c flag
        if first.startswith("-c "):
            center_text = first[3:].strip()
            bottom_text = second
        elif second.startswith("-c "):
            top_text = first
            center_text = second[3:].strip()
        else:
            # Normal top + bottom
            top_text = first
            bottom_text = second
    
    else:
        # Too many parts - take first two
        top_text = parts[0]
        bottom_text = parts[1]
    
    return (top_text, center_text, bottom_text)


async def add_text_to_static_sticker(sticker_path: str, top_text: str = None, 
                                     center_text: str = None, bottom_text: str = None):
    """
    Add text to static sticker image and return path to output file
    
    Returns: Path to output WEBP file
    """
    try:
        # Open image and ensure RGBA mode (for transparency)
        img = Image.open(sticker_path).convert("RGBA")
        width, height = img.size
        
        # Create a transparent overlay for text
        text_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)
        
        # Calculate max text width (90% of image width)
        max_text_width = int(width * 0.9)
        
        # Add TOP text
        if top_text:
            font = get_font(FONT_SIZE_TOP)
            lines = wrap_text(top_text.upper(), font, max_text_width)
            
            line_height = FONT_SIZE_TOP + 10
            y = int(height * TOP_POSITION)
            
            for line in lines:
                bbox = font.getbbox(line)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                
                draw_text_with_outline(
                    draw, (x, y), line, font, 
                    TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH
                )
                
                y += line_height
        
        # Add CENTER text
        if center_text:
            font = get_font(FONT_SIZE_CENTER)
            lines = wrap_text(center_text.upper(), font, max_text_width)
            
            line_height = FONT_SIZE_CENTER + 10
            total_height = len(lines) * line_height
            
            y = int(height * CENTER_POSITION) - (total_height // 2)
            
            for line in lines:
                bbox = font.getbbox(line)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                
                draw_text_with_outline(
                    draw, (x, y), line, font, 
                    TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH
                )
                
                y += line_height
        
        # Add BOTTOM text
        if bottom_text:
            font = get_font(FONT_SIZE_BOTTOM)
            lines = wrap_text(bottom_text.upper(), font, max_text_width)
            
            line_height = FONT_SIZE_BOTTOM + 10
            total_height = len(lines) * line_height
            
            y = int(height * BOTTOM_POSITION) - total_height
            
            for line in lines:
                bbox = font.getbbox(line)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                
                draw_text_with_outline(
                    draw, (x, y), line, font, 
                    TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH
                )
                
                y += line_height
        
        # Composite text layer over original image
        final_image = Image.alpha_composite(img, text_layer)
        
        # Resize to 512x512 (Telegram sticker requirement)
        final_image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        
        # Create new 512x512 canvas with transparency
        sticker_canvas = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
        
        # Center the image on canvas
        offset = ((512 - final_image.size[0]) // 2, (512 - final_image.size[1]) // 2)
        sticker_canvas.paste(final_image, offset)
        
        # ✅ Save to temp file with proper name
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        output_path = temp_dir / f"meme_output_{os.getpid()}.webp"
        
        sticker_canvas.save(str(output_path), format='WEBP', quality=95)
        
        return str(output_path)
    
    except Exception as e:
        logger.error(f"Error adding text to static sticker: {e}", exc_info=True)
        return None


async def add_text_to_video_sticker(video_path: str, top_text: str = None,
                                    center_text: str = None, bottom_text: str = None):
    """
    Add text to video sticker using FFmpeg
    
    Returns: Path to output WEBM file
    """
    try:
        if not check_ffmpeg_installed():
            logger.error("FFmpeg not installed!")
            return None
        
        # Build FFmpeg drawtext filters
        filters = []
        
        # Common text styling
        fontsize = 60
        fontcolor = "white"
        borderw = 3
        bordercolor = "black"
        
        # TOP text
        if top_text:
            text_escaped = top_text.upper().replace("'", "'\\\\\\''").replace(":", "\\:")
            filters.append(
                f"drawtext=text='{text_escaped}':"
                f"fontsize={fontsize}:fontcolor={fontcolor}:"
                f"borderw={borderw}:bordercolor={bordercolor}:"
                f"x=(w-text_w)/2:y=h*0.1"
            )
        
        # CENTER text
        if center_text:
            text_escaped = center_text.upper().replace("'", "'\\\\\\''").replace(":", "\\:")
            filters.append(
                f"drawtext=text='{text_escaped}':"
                f"fontsize={fontsize-10}:fontcolor={fontcolor}:"
                f"borderw={borderw}:bordercolor={bordercolor}:"
                f"x=(w-text_w)/2:y=(h-text_h)/2"
            )
        
        # BOTTOM text
        if bottom_text:
            text_escaped = bottom_text.upper().replace("'", "'\\\\\\''").replace(":", "\\:")
            filters.append(
                f"drawtext=text='{text_escaped}':"
                f"fontsize={fontsize}:fontcolor={fontcolor}:"
                f"borderw={borderw}:bordercolor={bordercolor}:"
                f"x=(w-text_w)/2:y=h*0.85-text_h"
            )
        
        if not filters:
            return None
        
        # Combine filters
        filter_complex = ",".join(filters)
        
        # Output path
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        output_path = temp_dir / f"meme_video_{os.getpid()}.webm"
        
        # FFmpeg command
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vf', filter_complex,
            '-c:v', 'libvpx-vp9',  # VP9 codec for WEBM
            '-pix_fmt', 'yuva420p',  # Alpha channel support
            '-auto-alt-ref', '0',
            '-b:v', '400k',  # Bitrate
            '-an',  # No audio
            '-y',  # Overwrite
            str(output_path)
        ]
        
        # Run FFmpeg
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )
        
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {process.stderr.decode()}")
            return None
        
        return str(output_path)
    
    except Exception as e:
        logger.error(f"Error adding text to video sticker: {e}", exc_info=True)
        return None


async def setup_memefi_handlers(client: Client):
    """Setup MemeFi command handlers"""
    
    @client.on_message(filters.command(["mmf", "memefi"]) & (filters.group | filters.private))
    async def memefi_command(client: Client, message: Message):
        try:
            # Check if replying to a message
            if not message.reply_to_message:
                await message.reply_text(
                    "⚠️ 𝖯𝗅𝖾𝖺𝗌𝖾 𝗋𝖾𝗉𝗅𝗒 𝗍𝗈 𝖺 𝗌𝗍𝗂𝖼𝗄𝖾𝗋!\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "📝 𝖧𝗈𝗐 𝗍𝗈 𝗎𝗌𝖾:\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "• /mmf Text\n"
                    "  (𝖳𝗈𝗉 𝗈𝗇𝗅𝗒)\n\n"
                    "• /mmf Text1 ; Text2\n"
                    "  (𝖳𝗈𝗉 + 𝖡𝗈𝗍𝗍𝗈𝗆)\n\n"
                    "• /mmf -c Text\n"
                    "  (𝖢𝖾𝗇𝗍𝖾𝗋 𝗈𝗇𝗅𝗒)\n\n"
                    "• /mmf Text ; -c Center\n"
                    "  (𝖳𝗈𝗉 + 𝖢𝖾𝗇𝗍𝖾𝗋)\n\n"
                    "• /mmf -c Center ; Bottom\n"
                    "  (𝖢𝖾𝗇𝗍𝖾𝗋 + 𝖡𝗈𝗍𝗍𝗈𝗆)\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "𝖤𝗑𝖺𝗆𝗉𝗅𝖾:\n"
                    "/mmf ME ON MONDAY ; NEED COFFEE"
                )
                return
            
            # Check if replied message has sticker
            replied_msg = message.reply_to_message
            if not replied_msg.sticker:
                await message.reply_text(
                    "⚠️ 𝖳𝗁𝖺𝗍'𝗌 𝗇𝗈𝗍 𝖺 𝗌𝗍𝗂𝖼𝗄𝖾𝗋!\n\n"
                    "𝖯𝗅𝖾𝖺𝗌𝖾 𝗋𝖾𝗉𝗅𝗒 𝗍𝗈 𝖺 𝗌𝗍𝗂𝖼𝗄𝖾𝗋 𝖺𝗇𝖽 𝖺𝖽𝖽 𝗍𝖾𝗑𝗍."
                )
                return
            
            # Parse command
            top_text, center_text, bottom_text = parse_mmf_command(message.text)
            
            # Check if any text provided
            if not top_text and not center_text and not bottom_text:
                await message.reply_text(
                    "⚠️ 𝖯𝗅𝖾𝖺𝗌𝖾 𝗉𝗋𝗈𝗏𝗂𝖽𝖾 𝗍𝖾𝗑𝗍!\n\n"
                    "𝖴𝗌𝖺𝗀𝖾: /mmf Your Text Here\n"
                    "𝖮𝗋: /mmf Top ; Bottom"
                )
                return
            
            # Send processing message
            processing_msg = await message.reply_text("⏳ 𝖢𝗋𝖾𝖺𝗍𝗂𝗇𝗀 𝗆𝖾𝗆𝖾...")
            
            # Create temp directory
            temp_dir = Path("temp")
            temp_dir.mkdir(exist_ok=True)
            
            # Check if video or static sticker
            is_video = replied_msg.sticker.is_video or replied_msg.sticker.is_animated
            
            if is_video:
                # ✅ VIDEO STICKER PROCESSING
                if not check_ffmpeg_installed():
                    await processing_msg.edit_text(
                        "❌ 𝖵𝗂𝖽𝖾𝗈 𝗌𝗍𝗂𝖼𝗄𝖾𝗋𝗌 𝗇𝖾𝖾𝖽 𝖥𝖥𝗆𝗉𝖾𝗀.\n\n"
                        "𝖯𝗅𝖾𝖺𝗌𝖾 𝖼𝗈𝗇𝗍𝖺𝖼𝗍 𝖻𝗈𝗍 𝗈𝗐𝗇𝖾𝗋."
                    )
                    return
                
                # Download video sticker
                sticker_path = temp_dir / f"sticker_{message.from_user.id}.webm"
                await client.download_media(replied_msg.sticker.file_id, file_name=str(sticker_path))
                
                # Add text to video
                result_path = await add_text_to_video_sticker(
                    str(sticker_path),
                    top_text=top_text,
                    center_text=center_text,
                    bottom_text=bottom_text
                )
                
                if not result_path:
                    await processing_msg.edit_text(
                        "❌ 𝖥𝖺𝗂𝗅𝖾𝖽 𝗍𝗈 𝗉𝗋𝗈𝖼𝖾𝗌𝗌 𝗏𝗂𝖽𝖾𝗈.\n"
                        "𝖯𝗅𝖾𝖺𝗌𝖾 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇."
                    )
                    return
                
                # Send video sticker
                await message.reply_video(video=result_path)
                
                # Cleanup
                try:
                    os.remove(sticker_path)
                    os.remove(result_path)
                except:
                    pass
            
            else:
                # ✅ STATIC STICKER PROCESSING
                # Download sticker
                sticker_path = temp_dir / f"sticker_{message.from_user.id}.webp"
                await client.download_media(replied_msg.sticker.file_id, file_name=str(sticker_path))
                
                # Add text to sticker
                result_path = await add_text_to_static_sticker(
                    str(sticker_path),
                    top_text=top_text,
                    center_text=center_text,
                    bottom_text=bottom_text
                )
                
                if not result_path:
                    await processing_msg.edit_text(
                        "❌ 𝖥𝖺𝗂𝗅𝖾𝖽 𝗍𝗈 𝖼𝗋𝖾𝖺𝗍𝖾 𝗆𝖾𝗆𝖾.\n"
                        "𝖯𝗅𝖾𝖺𝗌𝖾 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇."
                    )
                    return
                
                # ✅ Send result as STICKER with file path (not BytesIO)
                await message.reply_sticker(sticker=result_path)
                
                # Cleanup
                try:
                    os.remove(sticker_path)
                    os.remove(result_path)
                except:
                    pass
            
            # Delete processing message
            await processing_msg.delete()
            
            logger.info(f"MemeFi: Created meme sticker for user {message.from_user.id}")
        
        except Exception as e:
            logger.error(f"Error in memefi command: {e}", exc_info=True)
            try:
                await message.reply_text(
                    "❌ 𝖠𝗇 𝖾𝗋𝗋𝗈𝗋 𝗈𝖼𝖼𝗎𝗋𝗋𝖾𝖽.\n"
                    "𝖯𝗅𝖾𝖺𝗌𝖾 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇 𝗅𝖺𝗍𝖾𝗋."
                )
            except:
                pass
    
    logger.info("✅ MemeFi handlers setup complete")
