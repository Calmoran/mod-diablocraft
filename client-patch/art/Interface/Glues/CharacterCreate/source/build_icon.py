#!/usr/bin/env python3
"""The create screen's own class icons: the designer's art, not Blizzard's (the Monk diablocraft-3exia, the Necromancer
diablocraft-im7mr.4), and the Witch Doctor's plain WD (diablocraft-vxrcu.34) until he sends his.

    python3 client-patch/art/Interface/Glues/CharacterCreate/source/build_icon.py

Reads each class image beside this script (`monk.*`, `necromancer.*`, `witch_doctor.*`) and writes it as a 64x64 DXT5 BLP2
(build_ui_art.py's writer) to `../Torment-<Class>.blp`, which build.sh packs as
Interface\\Glues\\CharacterCreate\\Torment-<Class> and GlueXML CharacterCreate.lua (CLASS_ICON_TEXTURE) draws whole on
the class's button and in the details pane. A new icon is a one-file swap: replace <class>.* (any square image Pillow
reads, transparent background), run this, rebuild the MPQ. build.sh never packs source/.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
try:
    from PIL import Image
except ModuleNotFoundError:                      # Pillow is vendored in the shared scratch
    sys.path.append(str(ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "pil"))
    from PIL import Image
from PIL import ImageFilter, ImageMath  # noqa: E402
sys.path.insert(0, str(ROOT / "client-patch"))
from build_ui_art import write_blp  # noqa: E402

ICON = 64
BLEED = 3                                        # blur radius in icon pixels
CLASSES = ("monk", "necromancer", "witch_doctor")


def out_path(token: str) -> Path:
    return HERE.parent / f"Torment-{token.title().replace('_', '')}.blp"


def bleed(image: Image.Image) -> Image.Image:
    """DXT picks each 4x4 block's two colours from RGB alone, so the colour under near-transparent pixels (the WebP
    keeps stray greens there) shows as fringes. Put the nearby visible colour (an alpha-weighted blur) under them."""
    alpha = image.getchannel("A")
    weight = alpha.filter(ImageFilter.GaussianBlur(BLEED)).convert("F")
    premultiplied = Image.new("RGBA", image.size, (0, 0, 0, 255))
    premultiplied.alpha_composite(image)
    bands = [ImageMath.lambda_eval(lambda e: e["c"] * 255 / (e["w"] + 0.001),
                                   c=band.filter(ImageFilter.GaussianBlur(BLEED)).convert("F"), w=weight).convert("L")
             for band in premultiplied.convert("RGB").split()]
    flat = Image.merge("RGB", bands).convert("RGBA")
    flat.alpha_composite(image)
    flat.putalpha(alpha)
    return flat


def source_of(token: str) -> Path:
    (source,) = [p for p in HERE.glob(f"{token}.*") if p.suffix != ".py"]
    return source


def build(token: str, out: Path) -> None:
    image = Image.open(source_of(token)).convert("RGBA").resize((ICON, ICON), Image.LANCZOS)
    write_blp(bleed(image), out, uncompressed=False)


def main() -> int:
    for token in CLASSES:
        build(token, out_path(token))
        print(f"{source_of(token).name} -> {out_path(token)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
