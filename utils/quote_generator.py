import io
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageOps
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Telegram-style colors
BG_COLOR = (15, 20, 25)  # Dark Telegram background
BUBBLE_COLOR = (32, 39, 48)  # Message bubble color
TEXT_COLOR = (255, 255, 255)  # White text
NAME_COLOR = (114, 137, 218)  # Blue for name
TIME_COLOR = (130, 142, 157)  # Gray for timestamp

# Font sizes
NAME_FONT_SIZE = 28
TEXT_FONT_SIZE = 32
TIME_FONT_SIZE = 24

async def generate_quote_sticker(
    user_name: str,
    text: str,
    profile_pic: Optional[Image.Image] = None,
    timestamp: str = "00:00"
) -> bytes:
    """
    Generate a Telegram-style quote sticker
    
    Args:
        user_name: Name of the user
        text: Message text to quote
        profile_pic: User's profile picture (PIL Image)
        timestamp: Message time (HH:MM format)
    
    Returns:
        bytes: WebP sticker image data
    """
    try:
        # Dimensions
        max_width = 512
        padding = 30
        avatar_size = 80
        bubble_padding = 20
        
        # Load default font (system font)
        try:
            name_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", NAME_FONT_SIZE)
            text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", TEXT_FONT_SIZE)
            time_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", TIME_FONT_SIZE)
        except:
            # Fallback to default font
            name_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            time_font = ImageFont.load_default()
        
        # Wrap text
        max_chars = 35
        wrapped_text = textwrap.fill(text, width=max_chars)
        text_lines = wrapped_text.split('\n')
        
        # Limit to 15 lines max
        if len(text_lines) > 15:
            text_lines = text_lines[:15]
            text_lines[-1] += "..."
        
        # Calculate dimensions
        name_bbox = name_font.getbbox(user_name)
        name_height = name_bbox[3] - name_bbox[1]
        
        line_height = TEXT_FONT_SIZE + 8
        text_height = len(text_lines) * line_height
        
        time_bbox = time_font.getbbox(timestamp)
        time_height = time_bbox[3] - time_bbox[1]
        
        # Calculate bubble dimensions
        bubble_height = name_height + text_height + time_height + (bubble_padding * 3) + 20
        bubble_width = max_width - avatar_size - (padding * 2) - 20
        
        # Calculate total image height
        total_height = max(avatar_size + (padding * 2), bubble_height + (padding * 2))
        
        # Create image with dark background
        img = Image.new('RGB', (max_width, total_height), BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # Draw avatar (circular)
        avatar_x = padding
        avatar_y = padding
        
        if profile_pic:
            # Resize and crop profile pic to square
            profile_pic = profile_pic.convert('RGB')
            profile_pic = ImageOps.fit(profile_pic, (avatar_size, avatar_size), Image.Resampling.LANCZOS)
            
            # Create circular mask
            mask = Image.new('L', (avatar_size, avatar_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
            
            # Create circular avatar
            circular_avatar = Image.new('RGB', (avatar_size, avatar_size), BG_COLOR)
            circular_avatar.paste(profile_pic, (0, 0))
            
            # Paste onto main image with mask
            img.paste(circular_avatar, (avatar_x, avatar_y), mask)
        else:
            # Draw default avatar circle
            draw.ellipse(
                [avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size],
                fill=(100, 100, 100)
            )
            # Draw first letter of name
            if user_name:
                initial = user_name[0].upper()
                initial_bbox = name_font.getbbox(initial)
                initial_width = initial_bbox[2] - initial_bbox[0]
                initial_height = initial_bbox[3] - initial_bbox[1]
                initial_x = avatar_x + (avatar_size - initial_width) // 2
                initial_y = avatar_y + (avatar_size - initial_height) // 2
                draw.text((initial_x, initial_y), initial, fill=TEXT_COLOR, font=name_font)
        
        # Draw message bubble
        bubble_x = avatar_x + avatar_size + 20
        bubble_y = padding
        
        # Rounded rectangle for bubble
        bubble_radius = 15
        draw.rounded_rectangle(
            [bubble_x, bubble_y, bubble_x + bubble_width, bubble_y + bubble_height],
            radius=bubble_radius,
            fill=BUBBLE_COLOR
        )
        
        # Draw user name
        name_y = bubble_y + bubble_padding
        draw.text((bubble_x + bubble_padding, name_y), user_name, fill=NAME_COLOR, font=name_font)
        
        # Draw message text
        text_y = name_y + name_height + 15
        for line in text_lines:
            draw.text((bubble_x + bubble_padding, text_y), line, fill=TEXT_COLOR, font=text_font)
            text_y += line_height
        
        # Draw timestamp
        time_y = bubble_y + bubble_height - time_height - bubble_padding
        time_x = bubble_x + bubble_width - time_font.getbbox(timestamp)[2] - bubble_padding
        draw.text((time_x, time_y), timestamp, fill=TIME_COLOR, font=time_font)
        
        # Convert to WebP
        output = io.BytesIO()
        img.save(output, format='WEBP', quality=95)
        output.seek(0)
        
        return output.read()
        
    except Exception as e:
        logger.error(f"Error generating quote sticker: {e}")
        return None
