import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, filters
from pyrogram.types import Message

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


def is_burmese(text: str) -> bool:
    for char in text:
        if '\u1000' <= char <= '\u109F':
            return True
    return False


def get_font(size: int, text: str = ""):
    if is_burmese(text):
        font_path = "assets/noto-sans.ttf"
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        else:
            raise FileNotFoundError("Noto Sans font not found! Make sure assets/noto-sans.ttf exists in your repo.")
    else:
        font_path = "assets/default.ttf"
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        else:
            raise FileNotFoundError("Font not found! Make sure assets/default.ttf exists in your repo.")


def wrap_text(text: str, font, max_width: int):
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
    x, y = position

    for adj_x in range(-outline_width, outline_width + 1):
        for adj_y in range(-outline_width, outline_width + 1):
            if adj_x != 0 or adj_y != 0:
                draw.text((x + adj_x, y + adj_y), text, font=font, fill=outline_color)

    draw.text(position, text, font=font, fill=text_color)


def parse_mmf_command(text: str):
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
    img = Image.open(sticker_path).convert("RGBA")
    width, height = img.size

    text_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)

    max_text_width = int(width * 0.85)

    if top_text:
        font = get_font(FONT_SIZE_TOP, top_text)
        lines = wrap_text(top_text, font, max_text_width)

        line_height = FONT_SIZE_TOP + 15
        y = int(height * TOP_POSITION)

        for line in lines:
            bbox = font.getbbox(line)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw_text_with_outline(draw, (x, y), line, font, TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH)
            y += line_height

    if center_text:
        font = get_font(FONT_SIZE_CENTER, center_text)
        lines = wrap_text(center_text, font, max_text_width)

        line_height = FONT_SIZE_CENTER + 15
        total_height = len(lines) * line_height
        y = int(height * CENTER_POSITION) - (total_height // 2)

        for line in lines:
            bbox = font.getbbox(line)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw_text_with_outline(draw, (x, y), line, font, TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH)
            y += line_height

    if bottom_text:
        font = get_font(FONT_SIZE_BOTTOM, bottom_text)
        lines = wrap_text(bottom_text, font, max_text_width)

        line_height = FONT_SIZE_BOTTOM + 15
        total_height = len(lines) * line_height
        y = int(height * BOTTOM_POSITION) - total_height

        for line in lines:
            bbox = font.getbbox(line)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw_text_with_outline(draw, (x, y), line, font, TEXT_COLOR, OUTLINE_COLOR, OUTLINE_WIDTH)
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


async def setup_memefi_handlers(client: Client):

    @client.on_message(filters.command(["mmf", "memefi"]) & (filters.group | filters.private))
    async def memefi_command(client: Client, message: Message):
        if not message.reply_to_message:
            await message.reply_text(
                "Please reply to a sticker.\n\n"
                "How to use:\n"
                "• /mmf Text (top only)\n"
                "• /mmf Text1 ; Text2 (top and bottom)\n"
                "• /mmf -c Text (center only)\n"
                "• /mmf Text ; -c Center (top and center)\n"
                "• /mmf -c Center ; Bottom (center and bottom)\n\n"
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
                "Or: /mmf Top ; Bottom"
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
        except Exception:
            pass

        await processing_msg.delete()
