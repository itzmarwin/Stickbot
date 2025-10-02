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
    Automatically adjusts duration to fit 256KB limit
    Requirements:
    - 512x512 resolution
    - VP9 codec
    - Max 256KB file size (will auto-cut duration to fit)
    """
    try:
        max_size = 256 * 1024  # 256KB in bytes
        
        # Try different durations: 3s, 2s, 1.5s, 1s, 0.5s
        durations = [3, 2, 1.5, 1, 0.5]
        
        for duration in durations:
            temp_output = output_path + f".temp_{duration}.webm"
            
            # Calculate appropriate bitrate based on duration
            # Rough formula: (256KB * 8 bits) / duration / 1024 = bitrate in kbps
            target_bitrate = int((max_size * 8) / duration / 1024 * 0.8)  # 0.8 for safety margin
            target_bitrate = max(100, min(target_bitrate, 500))  # Clamp between 100-500k
            
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-t', str(duration),  # Limit duration
                '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2',
                '-c:v', 'libvpx-vp9',
                '-b:v', f'{target_bitrate}k',
                '-crf', '40',
                '-pix_fmt', 'yuva420p',
                '-an',  # No audio
                '-deadline', 'good',
                '-cpu-used', '4',
                '-row-mt', '1',
                '-auto-alt-ref', '0',
                '-y',
                temp_output
            ]
            
            try:
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30
                )
                
                if process.returncode != 0 or not os.path.exists(temp_output):
                    logger.warning(f"Failed to convert with {duration}s duration")
                    if os.path.exists(temp_output):
                        os.remove(temp_output)
                    continue
                
                # Check file size
                file_size = os.path.getsize(temp_output)
                logger.info(f"Created video with {duration}s duration: {file_size} bytes")
                
                if file_size <= max_size:
                    # Success! Move to final output
                    os.rename(temp_output, output_path)
                    logger.info(f"Successfully created video sticker: {file_size} bytes, {duration}s")
                    return True
                else:
                    # Too large, try shorter duration
                    logger.info(f"File too large ({file_size} bytes) with {duration}s, trying shorter...")
                    os.remove(temp_output)
                    continue
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout for {duration}s duration")
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                continue
        
        # If all durations failed, try one last aggressive compression with 0.5s
        logger.info("Attempting final aggressive compression...")
        
        cmd_final = [
            'ffmpeg',
            '-i', input_path,
            '-t', '0.5',
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2',
            '-c:v', 'libvpx-vp9',
            '-b:v', '150k',
            '-crf', '50',  # Very high CRF for maximum compression
            '-pix_fmt', 'yuva420p',
            '-an',
            '-deadline', 'good',
            '-cpu-used', '5',
            '-y',
            output_path
        ]
        
        process = subprocess.run(
            cmd_final,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )
        
        if process.returncode == 0 and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            if file_size <= max_size:
                logger.info(f"Final aggressive compression succeeded: {file_size} bytes")
                return True
        
        logger.error("Failed to compress video to under 256KB")
        return False
            
    except Exception as e:
        logger.error(f"Error converting video to WebM: {e}")
        return False
    finally:
        # Cleanup any remaining temp files
        try:
            for f in os.listdir(os.path.dirname(output_path)):
                if f.startswith(os.path.basename(output_path)) and '.temp_' in f:
                    os.remove(os.path.join(os.path.dirname(output_path), f))
        except:
            pass

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
