#!/usr/bin/env python3
"""Turn the active UI source art into addon BLP textures.

The stash kit under art/ui/ is converted into the Torment addon art folder and
the ElvUI bottom bar under art/ui/elvui/ into the ElvUI_Torment media folder.
The rift kit and the /bug button icon (art/ui/bug/) also go to the Torment addon
art folder. Reference art for removed UI, including art/ui/hud/, is deliberately
not built.
Non-PNG bookkeeping beside a kit (manifest.csv, README.md) is ignored because
only *.png is globbed, and source/ subfolders holding superseded kits are
skipped.

The 3.3.5a client reads no PNG at all - `Wow.exe` holds no ".png" string - so the
source art has to be converted before the addon can draw it. Output goes to
client-patch/addons/Torment/art/, which the addon references by the file
names in its own `Diablocraft.ART` table.

Format: BLP2, type 1 (direct), encoding 2 (DXT), alphaDepth 8, alphaType 7
(DXT5), with a full mip chain. That is what the pinned client's own UI uses -
635 of the 2310 Interface BLPs in its archives are exactly this variant, and
another 1608 are other DXT flavours. Uncompressed BGRA (encoding 3) also decodes
in this client but ships only once in the whole install, so DXT5 is the safer
default; pass --uncompressed if DXT blocking ever shows on a gradient.

Textures must be power-of-two in both dimensions. Anything that is not is scaled
down to fit its target canvas and padded with transparency at the top left; the
addon crops the padding back off with SetTexCoord, so the art is never stretched.

    python client-patch/build_ui_art.py
    python client-patch/build_ui_art.py --uncompressed
"""
from __future__ import annotations

import argparse
import io
import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
# Removed UI kits stay under art/ui/ as reference but do not produce addon art.
SOURCES = (ROOT / "art" / "ui" / "stash", ROOT / "art" / "ui" / "elvui", ROOT / "art" / "ui" / "rift",
           ROOT / "art" / "ui" / "bug", ROOT / "art" / "ui" / "tooltip", ROOT / "art" / "ui" / "bounties")
# Each kit writes into its own addon's art folder.
TARGETS = {
    "stash": ROOT / "addons" / "Torment" / "art",
    "elvui": ROOT / "addons" / "ElvUI_Torment" / "media",
    # The rift tracker's pieces (diablocraft-rift-tracker), drawn by draw_rift_art.py.
    "rift": ROOT / "addons" / "Torment" / "art",
    # The /bug button icon (diablocraft-sn9c), a later client's Blizzard bug icon;
    # see art/ui/bug/manifest.json for its source and pin.
    "bug": ROOT / "addons" / "Torment" / "art",
    # The tooltip's diamond bullet and DPS glow (diablocraft-tooltip-reskin),
    # drawn by draw_tooltip_art.py.
    "tooltip": ROOT / "addons" / "Torment" / "art",
    # The bounty map panel's zone waypoint compass (diablocraft-dm9vg.6), cut by
    # art/ui/bounties/cut_bounty_waypoint.py from the designer's own icon.
    "bounties": ROOT / "addons" / "Torment" / "art",
}

# Source art that is a reference picture, not a texture, and the bookkeeping
# that sits beside a kit. source/ holds superseded kits and is skipped whole.
SKIP = {"stash_inventory_reference.png"}
SKIP_DIRS = {"source"}

# Sources that are not power-of-two, and the canvas each is fitted into.
CANVAS = {"title_bar_strip.png": (512, 256)}
# Sources pasted at native size into the canvas top-left, never scaled; the
# addon crops the padding back off with SetTexCoord.
# hud_bar.png is the 2022x320 cut of the designer's hotbar sheet (art/ui/elvui/cut_hotbar_art.py, diablocraft-lhoeu).
PAD = {"BottomBar_GameRes.png": (2048, 256), "hud_bar.png": (2048, 512)}

BLP_HEADER = 148
# Every BLP2 in the pinned client - DXT and uncompressed alike - starts its mip
# data at 1172, so the 1024-byte palette block is written even when nothing reads
# it. Checked against 2310 of the client's own Interface textures.
BLP_PALETTE = 1024
BLP_DATA = BLP_HEADER + BLP_PALETTE
MIP_SLOTS = 16


def power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def dxt5(image: Image.Image) -> bytes:
    """Pillow writes a 128-byte DDS header in front of the block data."""
    buffer = io.BytesIO()
    image.save(buffer, format="DDS", pixel_format="DXT5")
    return buffer.getvalue()[128:]


def bgra(image: Image.Image) -> bytes:
    red, green, blue, alpha = image.split()
    return Image.merge("RGBA", (blue, green, red, alpha)).tobytes()


def mip_chain(image: Image.Image) -> list[Image.Image]:
    levels = [image]
    width, height = image.size
    while width > 1 or height > 1:
        width, height = max(1, width // 2), max(1, height // 2)
        levels.append(image.resize((width, height), Image.LANCZOS))
    return levels[:MIP_SLOTS]


def write_blp(image: Image.Image, path: Path, uncompressed: bool) -> int:
    encode = bgra if uncompressed else dxt5
    payloads = [encode(level) for level in mip_chain(image)]
    offsets, sizes, cursor = [0] * MIP_SLOTS, [0] * MIP_SLOTS, BLP_DATA
    for index, payload in enumerate(payloads):
        offsets[index], sizes[index] = cursor, len(payload)
        cursor += len(payload)
    header = b"BLP2" + struct.pack("<I", 1)
    header += struct.pack("<BBBB", 3 if uncompressed else 2, 8, 2 if uncompressed else 7, 1)
    header += struct.pack("<II", *image.size)
    header += struct.pack("<16I", *offsets) + struct.pack("<16I", *sizes)
    assert len(header) == BLP_HEADER, len(header)
    path.write_bytes(header + bytes(BLP_PALETTE) + b"".join(payloads))
    return cursor


def fit(image: Image.Image, canvas: tuple[int, int]) -> tuple[Image.Image, float]:
    """Scale to the canvas width, keep the aspect, pad the rest transparent."""
    width, height = canvas
    scaled_height = max(1, round(image.height * width / image.width))
    if scaled_height > height:
        raise SystemExit(f"{image.size} does not fit {canvas} without cropping")
    padded = Image.new("RGBA", canvas, (0, 0, 0, 0))
    padded.paste(image.resize((width, scaled_height), Image.LANCZOS), (0, 0))
    return padded, scaled_height / height


def pad(image: Image.Image, canvas: tuple[int, int]) -> tuple[Image.Image, tuple[float, float]]:
    """Paste the source at native size into the canvas top-left; never scale."""
    width, height = canvas
    if image.width > width or image.height > height:
        raise SystemExit(f"{image.size} does not fit {canvas}")
    padded = Image.new("RGBA", canvas, (0, 0, 0, 0))
    padded.paste(image, (0, 0))
    return padded, (image.width / width, image.height / height)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uncompressed", action="store_true",
                        help="write BLP2 encoding 3 (lossless BGRA) instead of DXT5")
    arguments = parser.parse_args()

    missing = [folder for folder in SOURCES if not folder.is_dir()]
    if missing:
        raise SystemExit("No source art at " + ", ".join(str(folder) for folder in missing))

    written = 0
    for folder in SOURCES:
        target = TARGETS[folder.name]
        target.mkdir(parents=True, exist_ok=True)
        print(f"{folder.name}/")
        # Top level only: source/ holds the superseded kits and is not converted.
        sources = sorted(entry for entry in folder.glob("*.png")
                         if entry.parent.name not in SKIP_DIRS)
        seen: dict[str, Path] = {}
        for source in sources:
            if source.name in SKIP:
                print(f"  skip     {source.name} (reference picture, not a texture)")
                continue
            # One art folder, one namespace: a clash would silently overwrite.
            if source.stem in seen:
                raise SystemExit(f"{source} and {seen[source.stem]} both write {source.stem}.blp")
            seen[source.stem] = source
            image = Image.open(source).convert("RGBA")
            note = ""
            if source.name in PAD:
                image, fractions = pad(image, PAD[source.name])
                note = (f"  padded (not scaled) to {image.width}x{image.height}, "
                        f"SetTexCoord(0, {fractions[0]:.8f}, 0, {fractions[1]:.8f})")
            elif source.name in CANVAS:
                image, fraction = fit(image, CANVAS[source.name])
                note = f"  padded to {image.width}x{image.height}, addon texcoord bottom = {fraction:.9f}"
            elif not (power_of_two(image.width) and power_of_two(image.height)):
                print(f"  SKIPPED  {source.name} is {image.width}x{image.height}, not power-of-two "
                      f"and has no canvas in CANVAS")
                continue
            out = target / (source.stem + ".blp")
            size = write_blp(image, out, arguments.uncompressed)
            written += 1
            print(f"  {out.name:24} {image.width:>4}x{image.height:<4} {size:>8} bytes{note}")

    print(f"{written} texture(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
