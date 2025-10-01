import asyncio
import tempfile
import os
from typing import Optional
from PIL import Image
import logging
import subprocess

logger = logging.getLogger(__name__)


async def convert_sticker_to_png(webp_file_path: str) -> Optional[str]:
    """
    FAST Convert WebP sticker to PNG format
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
            return png_file_path
        else:
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
        
        # Save as PNG with optimization
        img.save(png_path, 'PNG', optimize=True)


async def convert_webm_to_mp4(webm_file_path: str) -> Optional[str]:
    """
    FAST Convert WebM video sticker to MP4 format using ffmpeg
    Returns path to MP4 file or None if conversion fails
    """
    try:
        # Create temp file for MP4 output
        temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        mp4_file_path = temp_file.name
        temp_file.close()
        
        # Optimized FFmpeg command for WebM to MP4 conversion
        cmd = [
            'ffmpeg',
            '-i', webm_file_path,           # Input WebM file
            '-c:v', 'libx264',              # Video codec
            '-preset', 'fast',              # Encoding speed
            '-crf', '20',                   # Better quality
            '-c:a', 'aac',                  # Audio codec
            '-movflags', '+faststart',      # Optimize for web playback
            '-y',                           # Overwrite output file
            mp4_file_path                   # Output MP4 file
        ]
        
        # Run ffmpeg command with timeout
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return None
        
        if process.returncode == 0:
            if os.path.exists(mp4_file_path) and os.path.getsize(mp4_file_path) > 0:
                return mp4_file_path
            else:
                return None
        else:
            return None
            
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please install FFmpeg.")
        return None
    except Exception as e:
        logger.error(f"Error converting WebM to MP4: {e}")
        return None


async def convert_gif_to_webm(gif_file_path: str) -> Optional[str]:
    """
    FAST Convert GIF to WebM format for video stickers using ffmpeg
    Handles ANY size GIF without errors
    Returns path to WebM file or None if conversion fails
    """
    try:
        # First, get GIF dimensions to handle any size
        width, height = await get_gif_dimensions(gif_file_path)
        if not width or not height:
            return None
        
        # Create temp file for WebM output
        temp_file = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
        webm_file_path = temp_file.name
        temp_file.close()
        
        # Calculate optimal scale while maintaining aspect ratio
        max_size = 512
        if width > max_size or height > max_size:
            if width > height:
                new_width = max_size
                new_height = int((height * max_size) / width)
            else:
                new_height = max_size
                new_width = int((width * max_size) / height)
        else:
            new_width = width
            new_height = height
        
        # Ensure dimensions are even (required by codec)
        new_width = new_width if new_width % 2 == 0 else new_width - 1
        new_height = new_height if new_height % 2 == 0 else new_height - 1
        
        # Optimized FFmpeg command for GIF to WebM conversion
        cmd = [
            'ffmpeg',
            '-i', gif_file_path,            # Input GIF file
            '-vf', f'scale={new_width}:{new_height}:flags=lanczos,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=black@0',
            '-c:v', 'libvpx-vp9',           # VP9 codec
            '-crf', '30',                   # Quality
            '-b:v', '500k',                 # Bitrate
            '-deadline', 'good',            # Speed vs quality
            '-cpu-used', '2',               # CPU usage
            '-row-mt', '1',                 # Multi-threading
            '-threads', '2',                # Number of threads
            '-t', '3',                      # Limit duration
            '-loop', '0',                   # Loop infinitely
            '-an',                          # No audio
            '-pix_fmt', 'yuva420p',         # Pixel format with alpha
            '-auto-alt-ref', '0',           # Disable alternate reference frames
            '-f', 'webm',                   # Force WebM format
            '-y',                           # Overwrite output file
            webm_file_path                  # Output WebM file
        ]
        
        # Run ffmpeg command with timeout
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return None
        
        if process.returncode == 0:
            if os.path.exists(webm_file_path) and os.path.getsize(webm_file_path) > 0:
                # Check file size (Telegram limit is 256KB for video stickers)
                file_size = os.path.getsize(webm_file_path)
                if file_size > 256 * 1024:  # 256KB
                    # File too large, try compressed version
                    return await convert_gif_to_webm_compressed(gif_file_path)
                return webm_file_path
            else:
                return None
        else:
            # If first attempt fails, try compressed version
            return await convert_gif_to_webm_compressed(gif_file_path)
            
    except FileNotFoundError:
        logger.error("FFmpeg not found. Please install FFmpeg.")
        return None
    except Exception as e:
        logger.error(f"Error converting GIF to WebM: {e}")
        return None


async def convert_gif_to_webm_compressed(gif_file_path: str) -> Optional[str]:
    """
    COMPRESSED version for large GIF files
    Handles any size with higher compression
    """
    try:
        # Create temp file for WebM output
        temp_file = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
        webm_file_path = temp_file.name
        temp_file.close()
        
        # Higher compression settings
        cmd = [
            'ffmpeg',
            '-i', gif_file_path,
            '-vf', 'scale=384:384:flags=lanczos,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=black@0',
            '-c:v', 'libvpx-vp9',
            '-crf', '35',                   # Higher compression
            '-b:v', '300k',                 # Lower bitrate
            '-deadline', 'realtime',        # Faster encoding
            '-cpu-used', '4',               # More CPU usage for speed
            '-row-mt', '1',
            '-threads', '2',
            '-t', '3',
            '-loop', '0',
            '-an',
            '-pix_fmt', 'yuva420p',
            '-auto-alt-ref', '0',
            '-f', 'webm',
            '-y',
            webm_file_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return None
        
        if process.returncode == 0:
            if os.path.exists(webm_file_path) and os.path.getsize(webm_file_path) > 0:
                return webm_file_path
        return None
        
    except Exception as e:
        logger.error(f"Error in compressed GIF conversion: {e}")
        return None


async def get_gif_dimensions(gif_file_path: str) -> tuple[int, int]:
    """
    Get GIF dimensions using Pillow
    Returns (width, height) or (None, None) if failed
    """
    try:
        def get_dimensions_sync(path):
            with Image.open(path) as img:
                return img.size
        
        return await asyncio.get_event_loop().run_in_executor(
            None, get_dimensions_sync, gif_file_path
        )
    except Exception as e:
        logger.error(f"Error getting GIF dimensions: {e}")
        return None, None


async def convert_gif_to_webm_optimized(gif_file_path: str) -> Optional[str]:
    """
    ULTRA FAST GIF to WebM conversion with quality preservation
    Uses optimal settings for speed and reliability
    """
    try:
        # Try normal conversion first
        result = await convert_gif_to_webm(gif_file_path)
        if result:
            return result
        
        # If normal conversion fails, try fallback method
        return await convert_gif_to_webm_fallback(gif_file_path)
        
    except Exception as e:
        logger.error(f"Error in optimized GIF conversion: {e}")
        return None


async def convert_gif_to_webm_fallback(gif_file_path: str) -> Optional[str]:
    """
    FALLBACK method for problematic GIFs
    Uses simplest possible conversion
    """
    try:
        temp_file = tempfile.NamedTemporaryFile(suffix='.webm', delete=False)
        webm_file_path = temp_file.name
        temp_file.close()
        
        # Simplest possible conversion command
        cmd = [
            'ffmpeg',
            '-i', gif_file_path,
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease:flags=fast_bilinear,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=black@0',
            '-c:v', 'libvpx-vp9',
            '-crf', '40',                   # Maximum compression
            '-deadline', 'realtime',        # Fastest encoding
            '-cpu-used', '8',               # Maximum speed
            '-t', '3',
            '-loop', '0',
            '-an',
            '-f', 'webm',
            '-y',
            webm_file_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return None
        
        if process.returncode == 0:
            if os.path.exists(webm_file_path) and os.path.getsize(webm_file_path) > 0:
                return webm_file_path
        return None
        
    except Exception as e:
        logger.error(f"Error in fallback GIF conversion: {e}")
        return None
