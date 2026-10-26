#!/usr/bin/env python3
"""The gem item icons: the designer's legendary gems and his ruby set, hue-shifted to the five colours.

diablocraft-fpo9l (brief: azerothcore-wotlk/build/_agent-scratch/legendary-gem-icons-2026-10-11/brief.md).
The designer's own art (Nano Banana), not Blizzard's.

    python3 client-patch/source/gems/draw_gem_icons.py --crop   # the designer's sheets -> png/ (legendary + ruby)
    python3 client-patch/source/gems/draw_gem_icons.py          # ruby -> the other four colours, png/ -> BLP

`--crop` reads the sheets from the brief's folder (`--sheets` moves it) and writes the 64x64 crops to `png/`;
those crops are the kept source, so a re-render without the sheets is the second command. That one makes the
other four colours from the ruby crops (the shift below) and writes every `png/*.png` as a 64x64 DXT5 BLP2
(build_ui_art.py's writer) to `client-patch/art/Interface/Icons/`, which build.sh packs as Interface\\Icons\\:
the folder the client reads an item's InventoryIcon from. The names are `DC_Gem_<gem_id>` (legendary_gems.csv)
and `DC_Gem_<Colour>_<Tier>` (gems.csv, spaces dropped); mod-diablocraft/data/gem_icons.csv points the items at
them and generate_gem_icons.py writes the display rows.
"""
from __future__ import annotations

import argparse
import colorsys
import csv
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
DATA = ROOT / "mod-diablocraft" / "data" / "d3"
SHEETS = ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "legendary-gem-icons-2026-10-11"
ICON = 64

sys.path.insert(0, str(ROOT / "client-patch"))
from build_ui_art import write_blp  # noqa: E402

# Each legendary gem's square on its sheet: (sheet, centre x, centre y, side), in the sheet's 2000-px pixels.
# The gem's own box plus about a tenth; sheet 3 inside its drawn cell frames (36-412 ... 1588-1964 x 368-748);
# Mirinae and Gogok looser, so the light thread and the streaks fade out rather than end at a hard edge.
LEGENDARY = {
    "Iceblink": ("sheet1", 236, 561, 400),
    "Invigorating Gemstone": ("sheet1", 614, 563, 340),
    "Legacy of Dreams": ("sheet1", 1000, 559, 390),
    "Mirinae, Teardrop of the Starweaver": ("sheet1", 1384, 540, 470),
    "Molten Wildebeest's Gizzard": ("sheet1", 1773, 557, 375),
    "Enforcer": ("sheet2", 228, 561, 355),
    "Esoteric Alteration": ("sheet2", 613, 558, 365),
    "Gem of Ease": ("sheet2", 1003, 557, 345),
    "Gem of Efficacious Toxin": ("sheet2", 1393, 574, 390),
    "Gogok of Swiftness": ("sheet2", 1771, 564, 400),
    "Bane of the Powerful": ("sheet3", 224, 558, 364),
    "Bane of the Stricken": ("sheet3", 612, 558, 364),
    "Bane of the Trapped": ("sheet3", 1000, 558, 364),
    "Boon of the Hoarder": ("sheet3", 1388, 558, 364),
    "Boyarsky's Chip": ("sheet3", 1776, 558, 364),
    "Moratorium": ("sheet4", 212, 556, 445),
    "Mutilation Guard": ("sheet4", 607, 554, 480),
    "Pain Enhancer": ("sheet4", 1004, 555, 484),
    "Red Soul Shard": ("sheet4", 1399, 557, 480),
    "Simplicity's Strength": ("sheet4", 1788, 557, 450),
    "Taeguk": ("sheet5", 364, 557, 515),
    "Wreath of Lightning": ("sheet5", 1001, 554, 530),
    "Zei's Stone of Vengeance": ("sheet5", 1636, 556, 565),
}

# The ruby sheet: 2 rows of 5 cells of 400x402, the ten tiers in gems.csv order (README.md, 'Stat gems').
# The whole cell less its faint grid line, so a Normal stays smaller than a Flawless Royal as the designer drew them.
RUBY_CELL, RUBY_SIDE = (400, 402), 384

# ---------------------------------------------------------------------------
# The shift (the designer's table, the bead's numbers): hue is turned by `hue` degrees, and the stone's saturation and
# lightness are multiplied by `sat` and `light`. Ruby is the source and is left as drawn.
GEM_COLOURS = {
    "Ruby":     {"hue": 0.0,   "sat": 1.0,  "light": 1.0},
    "Emerald":  {"hue": 120.0, "sat": 1.0,  "light": 1.0},
    "Amethyst": {"hue": -90.0, "sat": 1.0,  "light": 1.0},
    "Topaz":    {"hue": 45.0,  "sat": 1.1,  "light": 1.1},
    "Diamond":  {"hue": 0.0,   "sat": 0.08, "light": 1.45},
}
# The dark red-brown ground stays as it is in every colour: a pixel is shifted in full from this lightness up,
# not at all at the ground's own, and in between in proportion, so the gem's soft edge and glow blend over.
GROUND_LIGHT, STONE_LIGHT = 0.10, 0.22


def legendary_ids() -> dict[str, str]:
    """gem_name -> gem_id, for the gems that have one (the ones without have no item yet)."""
    with (DATA / "legendary_gems.csv").open(encoding="utf-8", newline="") as stream:
        return {row["gem_name"]: row["gem_id"] for row in csv.DictReader(stream) if row["gem_id"]}


def tiers() -> list[str]:
    """The ten stat gem tiers in gems.csv order, which is the ruby sheet's order."""
    out: list[str] = []
    with (DATA / "gems.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["is_legendary"] == "0" and row["tier"] not in out:
                out.append(row["tier"])
    return out


def stat_name(colour: str, tier: str) -> str:
    return f"DC_Gem_{colour}_{tier.replace(' ', '')}"


def square(sheet: Image.Image, cx: int, cy: int, side: int) -> Image.Image:
    half = side // 2
    return sheet.crop((cx - half, cy - half, cx - half + side, cy - half + side)).resize((ICON, ICON), Image.LANCZOS)


def shift(image: Image.Image, hue: float, sat: float, light: float) -> Image.Image:
    """Turn the stone's hue and scale its saturation and lightness; the dark ground is left alone.

    diablocraft-fdyr's shift, two changes: the hue is turned rather than set (the designer's ruby is not one hue - its
    fire runs orange - so a turn keeps that), and the ground is masked out by lightness.
    """
    out = []
    for r, g, b, a in image.convert("RGBA").get_flattened_data():
        h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        weight = min(1.0, max(0.0, (l - GROUND_LIGHT) / (STONE_LIGHT - GROUND_LIGHT)))
        r2, g2, b2 = colorsys.hls_to_rgb((h + hue / 360.0) % 1.0, min(1.0, l * light), min(1.0, s * sat))
        out.append((round(r + (r2 * 255.0 - r) * weight), round(g + (g2 * 255.0 - g) * weight),
                    round(b + (b2 * 255.0 - b) * weight), a))
    shifted = Image.new("RGBA", image.size)
    shifted.putdata(out)
    return shifted


def crop(sheets: Path) -> None:
    PNG.mkdir(exist_ok=True)
    ids = legendary_ids()
    files = {path.name.split("-")[0]: path for path in sheets.glob("sheet*.jpg")}
    for name, (sheet, cx, cy, side) in LEGENDARY.items():
        if name not in ids:
            print(f"  no gem_id for {name} in legendary_gems.csv: not cropped")
            continue
        square(Image.open(files[sheet]).convert("RGB"), cx, cy, side).save(PNG / f"DC_Gem_{ids[name]}.png")
    ruby = Image.open(sheets / "stat-gems-ruby-10-tiers.jpg").convert("RGB")
    for index, tier in enumerate(tiers()):
        column, row = index % 5, index // 5
        cx, cy = RUBY_CELL[0] * column + RUBY_CELL[0] // 2, RUBY_CELL[1] * row + RUBY_CELL[1] // 2
        square(ruby, cx, cy, RUBY_SIDE).save(PNG / f"{stat_name('Ruby', tier)}.png")


def build() -> int:
    for tier in tiers():
        ruby = Image.open(PNG / f"{stat_name('Ruby', tier)}.png")
        for colour, value in GEM_COLOURS.items():
            if colour != "Ruby":
                shift(ruby, value["hue"], value["sat"], value["light"]).save(PNG / f"{stat_name(colour, tier)}.png")
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
