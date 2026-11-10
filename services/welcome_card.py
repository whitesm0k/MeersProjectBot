from __future__ import annotations

import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
BACKGROUND_PATH = ROOT / 'assets' / 'welcome_background.png'
CARD_SIZE = (1088, 608)
AVATAR_SIZE = 300
AVATAR_POSITION = (48, 137)


def _font(size: int, bold: bool = False):
    filename = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    for path in (ROOT / 'fonts' / filename,
                 Path('/usr/share/fonts/truetype/dejavu') / filename):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def generate_welcome_card(avatar_bytes: bytes, member_count: int | None = None) -> bytes:
    """Avatar at left, MeersProject Secure on the right, no framed panel."""
    with Image.open(BACKGROUND_PATH) as bg:
        canvas = bg.convert('RGBA').resize(CARD_SIZE, Image.Resampling.LANCZOS)
    with Image.open(io.BytesIO(avatar_bytes)) as src:
        avatar = ImageOps.fit(src.convert('RGBA'), (AVATAR_SIZE, AVATAR_SIZE),
                              method=Image.Resampling.LANCZOS)

    x, y = AVATAR_POSITION
    cx, cy = x + AVATAR_SIZE // 2, y + AVATAR_SIZE // 2
    glow = Image.new('RGBA', CARD_SIZE, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((x-10, y-10, x+AVATAR_SIZE+10, y+AVATAR_SIZE+10),
               outline=(255, 255, 255, 235), width=11)
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(18)))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((x-7, y-7, x+AVATAR_SIZE+7, y+AVATAR_SIZE+7),
                 fill=(245, 245, 250, 255))
    mask = Image.new('L', (AVATAR_SIZE, AVATAR_SIZE), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, AVATAR_SIZE-1, AVATAR_SIZE-1), fill=255)
    canvas.paste(avatar, (x, y), mask)
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((x-3, y-3, x+AVATAR_SIZE+3, y+AVATAR_SIZE+3),
                 outline=(255, 255, 255, 255), width=5)

    # Keep the text inside the large right-hand empty area from the reference.
    tx = 405
    available = CARD_SIZE[0] - tx - 34
    label = 'MeersProject Secure'
    size = 57
    while size >= 24:
        font = _font(size, True)
        if draw.textbbox((0, 0), label, font=font, stroke_width=1)[2] <= available:
            break
        size -= 1
    bbox = draw.textbbox((0, 0), label, font=font, stroke_width=1)
    ty = 244 - (bbox[3]-bbox[1])//2 - bbox[1]
    # Subtle shadow, without a rectangular panel.
    draw.text((tx+3, ty+4), label, font=font, fill=(0, 0, 0, 210), stroke_width=2,
              stroke_fill=(0, 0, 0, 210))
    draw.text((tx, ty), label, font=font, fill=(247, 247, 250, 255),
              stroke_width=1, stroke_fill=(175, 175, 195, 255))

    if member_count is not None:
        subtitle = f'Member #{member_count:,}'
        draw.text((tx+2, ty+83), subtitle, font=_font(31, False),
                  fill=(215, 215, 225, 245), stroke_width=1, stroke_fill=(0, 0, 0, 200))

    result = io.BytesIO()
    canvas.convert('RGB').save(result, format='PNG', optimize=True)
    return result.getvalue()
