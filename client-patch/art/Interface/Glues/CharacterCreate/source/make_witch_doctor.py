#!/usr/bin/env python3
"""How witch_doctor.png is drawn: a plain 'WD' in Witch Doctor Green (4CDB3E) on the dark tile the class icons sit on, until the designer
sends his own art; kept to redo the picture, not run by the build.

    python3 client-patch/art/Interface/Glues/CharacterCreate/source/make_witch_doctor.py

Writes witch_doctor.png beside this script (256x256, transparent outside the tile's rounded corners); build_icon.py makes the
create screen's Torment-WitchDoctor.blp from it. The lettering is generated, so no Blizzard art is in it.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
try:
    from PIL import Image, ImageDraw, ImageFont
except ModuleNotFoundError:                      # Pillow is vendored in the shared scratch
    sys.path.append(str(ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "pil"))
    from PIL import Image, ImageDraw, ImageFont

SIZE = 256
SCALE = 2                                        # drawn at 2x and reduced, for smooth edges
GREEN = (0x4C, 0xDB, 0x3E, 255)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def tile() -> Image.Image:
    """A dark rounded square with a thin pale line inside a black edge, and the letters centred on it."""
    size = SIZE * SCALE
    unit = size // 64                            # the tile's proportions are those of a 64 pixel cell
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def outline(target, margin, corner, fill):
        target.rounded_rectangle((margin, margin, size - margin - 1, size - margin - 1), corner, fill=fill)

    radius = 9 * unit
    outline(draw, 1 * unit, radius, (0, 0, 0, 255))
    outline(draw, 3 * unit, radius - 2 * unit, (150, 152, 150, 255))
    body = 4 * unit
    inner = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gradient = ImageDraw.Draw(inner)
    top, bottom = (22, 26, 28), (6, 8, 10)
    for y in range(body, size - body):
        t = (y - body) / (size - 2 * body)
        gradient.line((0, y, size, y), fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (size, size), 0)
    outline(ImageDraw.Draw(mask), body, radius - 3 * unit, 255)
    image.paste(inner, (0, 0), mask)
    font = ImageFont.truetype(FONT, 30 * unit)
    left, top_, right, bottom_ = draw.textbbox((0, 0), "WD", font=font)
    x = (size - (right - left)) // 2 - left
    y = (size - (bottom_ - top_)) // 2 - top_
    draw.text((x + unit, y + unit), "WD", font=font, fill=(0, 0, 0, 255))        # a shadow
    draw.text((x, y), "WD", font=font, fill=GREEN)
    return image.resize((SIZE, SIZE), Image.LANCZOS)


if __name__ == "__main__":
    tile().save(HERE / "witch_doctor.png")
    print(f"witch_doctor.png -> {HERE}")
