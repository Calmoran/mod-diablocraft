#!/usr/bin/env python3
"""The potion icons: the designer's 11 Bottomless potions and the plain Health Potion.

diablocraft-71scy (brief: azerothcore-wotlk/build/_agent-scratch/legendary-potion-icons-2026-10-12/brief.md).
The designer's own art (Nano Banana 2.1), not Blizzard's. The gem icons' pipeline (client-patch/source/gems/).

    python3 client-patch/source/potions/draw_potion_icons.py --crop   # the designer's sheets -> png/
    python3 client-patch/source/potions/draw_potion_icons.py          # png/ -> BLP

`--crop` reads the sheets from the brief's folder (`--sheets` moves it) and writes the 64x64 crops to `png/`;
those crops are the kept source, so a re-render without the sheets is the second command. That one writes every
`png/*.png` as a 64x64 DXT5 BLP2 (build_ui_art.py's writer) to `client-patch/art/Interface/Icons/`, which
build.sh packs as Interface\\Icons\\. The names are `DC_Potion_<d3_id>` (legendary_potions.csv) and
`DC_Potion_HealthPotion` for the plain one.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ModuleNotFoundError:                      # Pillow is vendored in the shared scratch
    sys.path.append(str(Path(__file__).resolve().parents[3] / "azerothcore-wotlk" / "build" / "_agent-scratch" / "pil"))
    from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PNG = HERE / "png"
ICONS = ROOT / "client-patch" / "art" / "Interface" / "Icons"
SHEETS = ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "legendary-potion-icons-2026-10-12"
ICON = 64

sys.path.insert(0, str(ROOT / "client-patch"))
from build_ui_art import write_blp  # noqa: E402

# Each potion's square on its sheet: (sheet, centre x, centre y, side), in the sheet's 2000-px pixels. The centre
# is the flask's box on the black (every pixel brighter than 40 of 255), the side its longer edge plus about a
# tenth; Rejuvenation (its glow) and Unfettered (the hanging shackle) looser, as README.md asks.
POTIONS = {
    "HealthPotionLegendary_01": ("sheet1", 236, 552, 425),     # the Tower
    "HealthPotionLegendary_02": ("sheet1", 617, 558, 400),     # the Diamond
    "HealthPotionLegendary_03": ("sheet1", 1020, 554, 400),    # Regeneration
    "HealthPotionLegendary_04": ("sheet1", 1392, 550, 410),    # the Leech
    "HealthPotionLegendary_05": ("sheet1", 1759, 554, 395),    # Mutilation
    "HealthPotionLegendary_06": ("sheet2", 264, 536, 475),     # Kulle-Aid
    "P2_HealthPotionLegendary_07": ("sheet2", 633, 548, 500),  # Rejuvenation, looser
    "HealthPotionLegendary_08": ("sheet2", 1004, 553, 435),    # Fear
    "HealthPotionLegendary_09": ("sheet2", 1389, 556, 410),    # Amplification
    "HealthPotionLegendary_10": ("sheet2", 1769, 550, 410),    # Chaos
    "HealthPotionLegendary_11": ("sheet3", 262, 550, 470),     # the Unfettered, looser
    "HealthPotion": ("sheet3", 645, 548, 410),                 # the plain Health Potion
}


def square(sheet: Image.Image, cx: int, cy: int, side: int) -> Image.Image:
    half = side // 2
    return sheet.crop((cx - half, cy - half, cx - half + side, cy - half + side)).resize((ICON, ICON), Image.LANCZOS)


def crop(sheets: Path) -> None:
    """A looser square can reach the next flask (Rejuvenation reaches Kulle-Aid's spout), so each potion is
    cropped from a copy of its sheet blacked out past halfway to its neighbours' centres."""
    PNG.mkdir(exist_ok=True)
    files = {path.name.split("-")[0]: path for path in sheets.glob("sheet*.jpg")}
    for name, (sheet, cx, cy, side) in POTIONS.items():
        image = Image.open(files[sheet]).convert("RGB")
        others = [x for other, x, _, _ in POTIONS.values() if other == sheet and x != cx]
        left = max([(x + cx) // 2 for x in others if x < cx], default=0)
        right = min([(x + cx) // 2 for x in others if x > cx], default=image.width)
        image.paste((0, 0, 0), (0, 0, left, image.height))
        image.paste((0, 0, 0), (right, 0, image.width, image.height))
        square(image, cx, cy, side).save(PNG / f"DC_Potion_{name}.png")


def build() -> int:
    ICONS.mkdir(parents=True, exist_ok=True)
    sources = sorted(PNG.glob("*.png"))
    for source in sources:
        write_blp(Image.open(source).convert("RGBA"), ICONS / f"{source.stem}.blp", uncompressed=False)
    return len(sources)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crop", action="store_true", help="re-crop png/ from the designer's sheets first")
    parser.add_argument("--sheets", type=Path, default=SHEETS, help="the folder holding the designer's sheets")
    arguments = parser.parse_args()
    if arguments.crop:
        crop(arguments.sheets)
    print(f"{build()} icons in {ICONS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
