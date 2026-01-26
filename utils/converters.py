import os
import logging
from pathlib import Path
from PIL import Image
import subprocess
import io

logger = logging.getLogger(__name__)

def create_transparent_webp() -> bytes:
    """Create a transparent 512x512 WebP sticker"""
    try:
        img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format='WEBP', quality=1)
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Error creating transparent WebP: {e}")
        img = Image.new('RGB', (512, 512), (255, 255, 255))
        buffer = io.BytesIO()
        img.save(buffer, format='WEBP', quality=1)
        return buffer.getvalue()

async def convert_image_to_webp(input_path: str, output_path: str) -> bool:
    """Convert image to WebP format (512x512 with transparent background)"""
    try:
        with Image.open(input_path) as img:
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            img.thumbnail((512, 512), Image.Resampling.LANCZOS)
            background = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
            offset = ((512 - img.size[0]) // 2, (512 - img.size[1]) // 2)
            background.paste(img, offset)
            background.save(output_path, 'WEBP', quality=90)
            
        return True
    except Exception as e:
        logger.error(f"Error converting image to WebP: {e}")
        return False

async def convert_video_to_webm(input_path: str, output_path: str) -> bool:
    """Convert video/GIF to WebM format (max 2.9s, 256KB, 512x512)"""
    try:
        max_size = 256 * 1024
        durations = [2.9, 2, 1.5, 1, 0.5]
        
        for duration in durations:
            temp_output = output_path + f".temp_{duration}.webm"
            target_bitrate = int((max_size * 8) / duration / 1024 * 0.8)
            target_bitrate = max(100, min(target_bitrate, 500))
            
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-t', str(duration),
                '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000',
                '-c:v', 'libvpx-vp9',
                '-b:v', f'{target_bitrate}k',
                '-crf', '40',
                '-pix_fmt', 'yuva420p',
                '-an',
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
                    if os.path.exists(temp_output):
                        os.remove(temp_output)
                    continue
                
                file_size = os.path.getsize(temp_output)
                
                if file_size <= max_size:
                    os.rename(temp_output, output_path)
                    return True
                else:
                    os.remove(temp_output)
                    continue
                    
            except subprocess.TimeoutExpired:
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                continue
        
        cmd_final = [
            'ffmpeg',
            '-i', input_path,
            '-t', '0.5',
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000',
            '-c:v', 'libvpx-vp9',
            '-b:v', '150k',
            '-crf', '50',
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
                return True
        
        logger.error("Failed to compress video to under 256KB")
        return False
            
    except Exception as e:
        logger.error(f"Error converting video to WebM: {e}")
        return False
    finally:
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
        except Exception as e:
            logger.error(f"Error cleaning up {file_path}: {e}")

def create_temp_dir() -> str:
    """Create temporary directory for file processing"""
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    return str(temp_dir)
