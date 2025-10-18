import os
import logging
import resource
import signal
from pathlib import Path
from PIL import Image
import subprocess
from typing import Optional
import io

logger = logging.getLogger(__name__)

# ✅ FIX 1: FFmpeg resource limits
MAX_FFMPEG_MEMORY_MB = 512  # 512MB memory limit
MAX_FFMPEG_TIMEOUT = 60     # 60 second timeout


def limit_ffmpeg_resources():
    """
    ✅ Limit FFmpeg memory and CPU usage to prevent resource exhaustion
    Called via preexec_fn in subprocess
    """
    try:
        # Limit memory (virtual memory)
        max_memory = MAX_FFMPEG_MEMORY_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))
        
        # Limit CPU time (prevents infinite loops)
        resource.setrlimit(resource.RLIMIT_CPU, (120, 120))  # 2 minutes CPU time
        
        # Set process priority to low (nice value)
        os.nice(10)
        
    except Exception as e:
        logger.warning(f"Could not set resource limits: {e}")


def create_transparent_webp() -> bytes:
    """
    Create a transparent 512x512 WebP sticker for empty pack creation
    
    Returns:
        bytes: WebP image data
    """
    try:
        # Create a 512x512 transparent image (NOT 1x1)
        img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        img.save(buffer, format='WEBP', quality=1)
        
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Error creating transparent WebP: {e}")
        # Fallback: create a 512x512 white image
        img = Image.new('RGB', (512, 512), (255, 255, 255))
        buffer = io.BytesIO()
        img.save(buffer, format='WEBP', quality=1)
        return buffer.getvalue()


async def convert_image_to_webp(input_path: str, output_path: str) -> bool:
    """
    ✅ Convert image to WebP format for static stickers
    Target size: 512x512
    
    Args:
        input_path: Path to input image
        output_path: Path to output WebP file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # ✅ FIX 2: Validate input file exists and is not empty
        if not os.path.exists(input_path):
            logger.error(f"Input file does not exist: {input_path}")
            return False
        
        file_size = os.path.getsize(input_path)
        if file_size == 0:
            logger.error(f"Input file is empty: {input_path}")
            return False
        
        # ✅ FIX 3: Check file size limit (max 10MB for images)
        max_size = 10 * 1024 * 1024  # 10MB
        if file_size > max_size:
            logger.error(f"Input file too large: {file_size} bytes (max {max_size})")
            return False
        
        with Image.open(input_path) as img:
            # Convert to RGBA if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Resize to 512x512 maintaining aspect ratio
            img.thumbnail((512, 512), Image.Resampling.LANCZOS)
            
            # Create new image with transparent background
            background = Image.new('RGBA', (512, 512), (255, 255, 255, 0))
            
            # Calculate position to center the image
            offset = ((512 - img.size[0]) // 2, (512 - img.size[1]) // 2)
            background.paste(img, offset)
            
            # Save as WebP
            background.save(output_path, 'WEBP', quality=90)
            
        # ✅ FIX 4: Validate output was created
        if not os.path.exists(output_path):
            logger.error(f"Output file was not created: {output_path}")
            return False
        
        output_size = os.path.getsize(output_path)
        if output_size == 0:
            logger.error(f"Output file is empty: {output_path}")
            return False
        
        logger.info(f"Successfully converted image: {input_path} → {output_path} ({output_size} bytes)")
        return True
        
    except Exception as e:
        logger.error(f"Error converting image to WebP: {e}", exc_info=True)
        return False


async def convert_video_to_webm(input_path: str, output_path: str) -> bool:
    """
    ✅ Convert video/GIF to WebM format for video stickers
    Automatically adjusts duration to fit 256KB limit with resource protection
    
    Args:
        input_path: Path to input video/GIF
        output_path: Path to output WebM file
        
    Returns:
        True if successful, False otherwise
    """
    temp_files = []
    
    try:
        # ✅ FIX 5: Validate input file
        if not os.path.exists(input_path):
            logger.error(f"Input file does not exist: {input_path}")
            return False
        
        input_size = os.path.getsize(input_path)
        if input_size == 0:
            logger.error(f"Input file is empty: {input_path}")
            return False
        
        logger.info(f"Converting video: {input_path} ({input_size} bytes)")
        
        max_size = 256 * 1024  # 256KB in bytes
        
        # Try different durations: 3s, 2s, 1.5s, 1s, 0.5s
        durations = [3, 2, 1.5, 1, 0.5]
        
        for duration in durations:
            temp_output = output_path + f".temp_{duration}.webm"
            temp_files.append(temp_output)
            
            # Calculate appropriate bitrate based on duration
            target_bitrate = int((max_size * 8) / duration / 1024 * 0.8)
            target_bitrate = max(100, min(target_bitrate, 500))
            
            # Use crop and scale to fill entire 512x512 without black borders
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-t', str(duration),
                '-vf', 'crop=min(iw\\,ih):min(iw\\,ih),scale=512:512,setsar=1',
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
                # ✅ FIX 6: Use Popen with resource limits
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=limit_ffmpeg_resources  # ✅ Memory limit
                )
                
                # ✅ FIX 7: Increased timeout to 60s
                try:
                    stdout, stderr = process.communicate(timeout=MAX_FFMPEG_TIMEOUT)
                except subprocess.TimeoutExpired:
                    logger.warning(f"FFmpeg timeout ({MAX_FFMPEG_TIMEOUT}s) for duration {duration}s")
                    process.kill()
                    process.communicate()  # Clean up zombie process
                    if os.path.exists(temp_output):
                        os.remove(temp_output)
                    continue
                
                if process.returncode != 0:
                    logger.warning(f"FFmpeg failed (code {process.returncode}) for duration {duration}s")
                    if os.path.exists(temp_output):
                        os.remove(temp_output)
                    continue
                
                if not os.path.exists(temp_output):
                    logger.warning(f"FFmpeg did not create output for duration {duration}s")
                    continue
                
                # Check file size
                file_size = os.path.getsize(temp_output)
                
                if file_size <= max_size:
                    # Success! Move to final output
                    os.rename(temp_output, output_path)
                    logger.info(f"Successfully converted video: {duration}s duration, {file_size} bytes")
                    return True
                else:
                    # Too large, try shorter duration
                    logger.debug(f"Output too large ({file_size} bytes) for {duration}s, trying shorter")
                    os.remove(temp_output)
                    continue
                    
            except Exception as e:
                logger.error(f"Error in FFmpeg conversion (duration {duration}s): {e}")
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                continue
        
        # ✅ FIX 8: If all durations failed, try one last aggressive compression
        logger.warning("All duration attempts failed, trying aggressive compression")
        
        cmd_final = [
            'ffmpeg',
            '-i', input_path,
            '-t', '0.5',
            '-vf', 'crop=min(iw\\,ih):min(iw\\,ih),scale=512:512,setsar=1',
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
        
        try:
            process = subprocess.Popen(
                cmd_final,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=limit_ffmpeg_resources
            )
            
            try:
                stdout, stderr = process.communicate(timeout=MAX_FFMPEG_TIMEOUT)
            except subprocess.TimeoutExpired:
                logger.error("Final aggressive compression timed out")
                process.kill()
                process.communicate()
                return False
            
            if process.returncode == 0 and os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                if file_size <= max_size and file_size > 0:
                    logger.info(f"Aggressive compression succeeded: {file_size} bytes")
                    return True
        
        except Exception as e:
            logger.error(f"Error in final compression: {e}")
        
        logger.error("Failed to compress video to under 256KB with all methods")
        return False
            
    except Exception as e:
        logger.error(f"Error converting video to WebM: {e}", exc_info=True)
        return False
        
    finally:
        # ✅ FIX 9: Cleanup all temp files in finally block
        cleanup_temp_files(*temp_files)
        
        # Additional cleanup for any remaining temp files
        try:
            output_dir = os.path.dirname(output_path)
            output_basename = os.path.basename(output_path)
            
            for f in os.listdir(output_dir):
                if f.startswith(output_basename) and '.temp_' in f:
                    temp_file_path = os.path.join(output_dir, f)
                    try:
                        os.remove(temp_file_path)
                        logger.debug(f"Cleaned up temp file: {temp_file_path}")
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Error in temp file cleanup: {e}")


def cleanup_temp_files(*file_paths: str):
    """
    ✅ Remove temporary files with enhanced error handling
    
    Args:
        *file_paths: Variable number of file paths to delete
    """
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up {file_path}: {e}")


def create_temp_dir() -> str:
    """
    ✅ Create temporary directory for file processing with parent directory support
    
    Returns:
        str: Path to temporary directory
    """
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True, parents=True)
    return str(temp_dir)
