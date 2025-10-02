import os
import logging
from pathlib import Path
from PIL import Image
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

async def convert_image_to_webp(input_path: str, output_path: str) -> bool:
    """
    Convert image to WebP format for static stickers
    Target size: 512x512
    """
    try:
        with Image.open(input_path) as img:
            # Convert to RGBA if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Resize to 512x512 maintaining aspect ratio
            img.thumbnail((512, 512), Image.Resampling.LANCZOS)
            
            # Create new image with white background if needed
            background = Image.new('RGBA', (512, 512), (255, 255, 255, 0))
            
            # Calculate position to center the image
            offset = ((512 - img.size[0]) // 2, (512 - img.size[1]) // 2)
            background.paste(img, offset)
            
            # Save as WebP
            background.save(output_path, 'WEBP', quality=90)
            
        return True
    except Exception as e:
        logger.error(f"Error converting image to WebP: {e}")
        return False

async def convert_video_to_webm(input_path: str, output_path: str) -> bool:
    """
    Convert video/GIF to WebM format for video stickers
    Requirements:
    - Max 3 seconds
    - 512x512 resolution
    - VP9 codec
    """
    try:
        # FFmpeg command for video sticker conversion
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-t', '3',  # Limit to 3 seconds
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2',
            '-c:v', 'libvpx-vp9',
            '-b:v', '500k',
            '-pix_fmt', 'yuva420p',
            '-an',  # No audio
            '-y',  # Overwrite output file
            output_path
        ]
        
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )
        
        if process.returncode == 0 and os.path.exists(output_path):
            return True
        else:
            logger.error(f"FFmpeg error: {process.stderr.decode()}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Video conversion timeout")
        return False
    except Exception as e:
        logger.error(f"Error converting video to WebM: {e}")
        return False

def cleanup_temp_files(*file_paths: str):
    """Remove temporary files"""
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up {file_path}: {e}")

def create_temp_dir() -> str:
    """Create temporary directory for file processing"""
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    return str(temp_dir)
