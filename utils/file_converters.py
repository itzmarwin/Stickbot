import asyncio
import tempfile
import os
from typing import Optional
from PIL import Image
import logging

logger = logging.getLogger(__name__)


async def convert_sticker_to_png(webp_file_path: str) -> Optional[str]:
    """
    Convert WebP sticker to PNG format
    Returns path to PNG file or None if conversion fails
    """
    try:
        # Create temp file for PNG output
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        png_file_path = temp_file.name
        temp_file.close()
        
        # Run conversion in thread to avoid blocking
        await asyncio.get_event_loop().run_in_executor(
            None,
            _convert_webp_to_png_sync,
            webp_file_path,
            png_file_path
        )
        
        # Check if conversion was successful
        if os.path.exists(png_file_path) and os.path.getsize(png_file_path) > 0:
            logger.info(f"Successfully converted WebP to PNG: {png_file_path}")
            return png_file_path
        else:
            logger.error("PNG conversion failed - output file is empty or missing")
            return None
            
    except Exception as e:
        logger.error(f"Error converting WebP to PNG: {e}")
        return None


def _convert_webp_to_png_sync(webp_path: str, png_path: str) -> None:
    """Synchronous WebP to PNG conversion using Pillow"""
    with Image.open(webp_path) as img:
        # Convert to RGBA mode for better PNG compatibility
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Save as PNG
        img.save(png_path, 'PNG', optimize=True)


async def convert_webm_to_mp4(webm_file_path: str) -> Optional[str]:
    """
    Convert WebM video sticker to MP4 format using ffmpeg
    Returns path to MP4 file or None if conversion fails
    """
    try:
        # Create temp file for MP4 output
        temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        mp4_file_path = temp_file.name
        temp_file.close()
        
        # FFmpeg command for WebM to MP4 conversion
        cmd = [
            'ffmpeg',
            '-i', webm_file_path,           # Input WebM file
            '-c:v', 'libx264',              # Video codec
            '-preset', 'fast',              # Encoding speed
            '-crf', '23',                   # Quality (lower = better quality)
            '-c:a', 'aac',                  # Audio codec
            '-movflags', '+faststart',      # Optimize for web playback
            '-y',                           # Overwrite output file
            mp4_file_path                   # Output MP4 file
        ]
        
        # Run ffmpeg command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            # Check if conversion was successful
            if os.path.exists(mp4_file_path) and os.path.getsize(mp4_file_path) > 0:
                logger.info(f"Successfully converted WebM to MP4: {mp4_file_path}")
                return mp4_file_path
            else:
                logger.error("MP4 conversion failed - output file is empty or missing")
                return None
        else:
            logger.error(f"FFmpeg conversion failed: {stderr.decode()}")
            return None
            
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please install FFmpeg to use video conversion features.")
        return None
    except Exception as e:
        logger.error(f"Error converting WebM to MP4: {e}")
        return None


async def convert_gif_to_webm(gif_file_path: str) -> Optional[str]:
    """
    Convert GIF to WebM format for video stickers using ffmpeg
    Returns path to WebM file or None if conversion fails
    """
    try:
        # Create temp file for WebM output
        temp_file = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
        webm_file_path = temp_file.name
        temp_file.close()
        
        # FFmpeg command for GIF to WebM conversion (optimized for stickers)
        cmd = [
            'ffmpeg',
            '-i', gif_file_path,            # Input GIF file
            '-c:v', 'libvpx-vp9',           # VP9 codec for better compression
            '-crf', '30',                   # Quality (higher = smaller file)
            '-b:v', '0',                    # Variable bitrate
            '-deadline', 'good',            # Quality vs speed tradeoff
            '-cpu-used', '0',               # CPU usage (0 = best quality)
            '-loop', '0',                   # Loop infinitely
            '-an',                          # No audio
            '-pix_fmt', 'yuva420p',         # Pixel format with alpha support
            '-f', 'webm',                   # Force WebM format
            '-y',                           # Overwrite output file
            webm_file_path                  # Output WebM file
        ]
        
        # Run ffmpeg command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            # Check if conversion was successful
            if os.path.exists(webm_file_path) and os.path.getsize(webm_file_path) > 0:
                logger.info(f"Successfully converted GIF to WebM: {webm_file_path}")
                return webm_file_path
            else:
                logger.error("GIF to WebM conversion failed - output file is empty or missing")
                return None
        else:
            logger.error(f"FFmpeg GIF conversion failed: {stderr.decode()}")
            return None
            
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please install FFmpeg to use GIF conversion features.")
        return None
    except Exception as e:
        logger.error(f"Error converting GIF to WebM: {e}")
        return None
