#!/usr/bin/env python3
"""Pack the D3 health and Barbarian resource globes into the TormentD3 skin.

Blizzard ships each 60-frame globe animation as one .tex atlas whose pixels are
a BLACK SQUARE with the globe painted in it and NO alpha channel (every pixel is
opaque, alpha 255; D3 masks the circle in its own engine). This client is
3.3.5a and has no Texture:SetMask, so this script bakes the mask into the sheet:

  * the globe body keeps alpha 255, so its colour is never faded (the health
    centre is (63,0,0), which a luminance alpha would make ~25% transparent);
  * OUTSIDE the body disc the alpha is the pixel's luminance, so a glow fades
    to nothing instead of ending in a hard black square;
  * the disc edge is feathered a pixel or two, because RothUI draws these at
    roughly 1.6x (health) and 3.3x (Barbarian) and a hard circle aliases.

The disc is derived from the art, not assumed: the extent of the non-black
pixels over all 60 frames gives its centre and radius.

Blizzard also ships them 2048 wide; this client is reliable at 1024 and only
usually fine at 2048, so each atlas is re-packed into ONE 1024-wide sheet per
orb, frames driven by texture coordinates in ElvUI_Torment/orbs.lua, never a
guessed grid.

Run with the scratch venv that has Pillow (AGENTS.md):

    azerothcore-wotlk/build/_agent-scratch/venv-pil/bin/python \
        client-patch/build_d3_globes.py [preview_dir]

Writes client-patch/skins/TormentD3/media/d3_healthglobe.blp and the class
resource globes (d3_barbarianresourceglobe.blp, d3_wizardresourceglobe.blp, ...).
That folder is the designer's own TormentD3 skin, which is never shipped (the mock HUD is
what ships; TormentD3 exists to prove the skin system and to restore today's
look). Each JOBS row is one sheet; the skin sets the globe slots from these
files and ElvUI_Torment drives frames by texture coordinates.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "client-patch"))
import d3_tex_slice  # noqa: E402  (reuse its .tex frame-table reader and BLP writer)

SOURCE = ROOT / "reference" / "D3 Assets" / "Base" / "Textures"
OUT = ROOT / "client-patch" / "skins" / "TormentD3" / "media"

# atlas stem, output name, columns in the NEW sheet, sheet size, feather. The
# frame count and cell size are read from the .tex frame table, never guessed.
JOBS = (
    ("2DUI_HealthGlobe_Classic", "d3_healthglobe", 10, 1024, 1024, 2.0),
    ("2DUI_BarbarianResourceGlobe", "d3_barbarianresourceglobe", 20, 1024, 256, 1.5),
    ("2DUI_WizardResourceGlobe", "d3_wizardresourceglobe", 20, 1024, 256, 1.5),
    ("2DUI_MonkResourceGlobe", "d3_monkresourceglobe", 20, 1024, 256, 1.5),
    ("2DUI_CrusaderResourceGlobe", "d3_crusaderresourceglobe", 20, 1024, 256, 1.5),
    ("2DUI_DemonHunterResourceGlobe", "d3_demonhunterresourceglobe", 20, 1024, 256, 1.5),
    ("2DUI_WitchDoctorResourceGlobe", "d3_witchdoctorresourceglobe", 20, 1024, 256, 1.5),
    ("2DUI_NecromancerResourceGlobe", "d3_necromancerresourceglobe", 16, 1024, 256, 2.0),
)


def disc_mask(union: Image.Image, width: int, height: int, feather: float):
    """Alpha mask for one cell: 255 inside the globe body, luminance outside.

    `union` is the per-pixel maximum luminance across all 60 frames, so the disc
    is derived from the art over the whole animation and does not jitter.
    """
    box = union.point(lambda value: 255 if value > 0 else 0).getbbox()
    if not box:
        raise SystemExit("frame is entirely black; nothing to mask")
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    radius = min(x1 - x0, y1 - y0) / 2.0
    mask = Image.new("L", (width, height), 0)
    out = mask.load()
    source = union.load()
    for y in range(height):
        for x in range(width):
            lum = source[x, y]
            distance = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if distance <= radius - feather:
                alpha = 255
            elif distance >= radius:
                alpha = lum
            else:
                t = (distance - (radius - feather)) / feather
                alpha = int(round(255 * (1.0 - t) + lum * t))
            out[x, y] = alpha
    return mask, (cx, cy, radius)


def pack(stem, name, cols, sheet_w, sheet_h, feather, preview_dir):
    tex = SOURCE / f"{stem}.tex"
    width, height, frames = d3_tex_slice.read_frames(tex.read_bytes())
    image = d3_tex_slice.load_pixels(tex)
    if image.size != (width, height):
        raise SystemExit(f"{stem}: pixels are {image.size} but the .tex says {(width, height)}")
    # Cell size from the frame table, never a guessed grid; every frame must agree.
    _, fu0, fv0, fu1, fv1 = frames[0]
    cell_w, cell_h = round((fu1 - fu0) * width), round((fv1 - fv0) * height)
    for index, (_frame, u0, v0, u1, v1) in enumerate(frames):
        if (round((u1 - u0) * width), round((v1 - v0) * height)) != (cell_w, cell_h):
            raise SystemExit(f"{stem} frame {index}: inconsistent cell size")
    rows = (len(frames) + cols - 1) // cols
    if rows * cell_h > sheet_h or cols * cell_w > sheet_w:
        raise SystemExit(f"{stem}: {len(frames)} frames at {cell_w}x{cell_h} do not fit "
                         f"{cols} cols in {sheet_w}x{sheet_h}")

    crops = []
    for index, (_frame, u0, v0, u1, v1) in enumerate(frames):
        x0, y0 = round(u0 * width), round(v0 * height)
        x1, y1 = round(u1 * width), round(v1 * height)
        if (x1 - x0, y1 - y0) != (cell_w, cell_h):
            raise SystemExit(f"{stem} frame {index}: {x1 - x0}x{y1 - y0}, expected {cell_w}x{cell_h}")
        crops.append((index, image.crop((x0, y0, x1, y1))))

    union = None
    for _index, crop in crops:
        lum = crop.convert("L")
        union = lum if union is None else ImageChops.lighter(union, lum)
    mask, (cx, cy, radius) = disc_mask(union, cell_w, cell_h, feather)

    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    for index, crop in crops:
        masked = crop.copy()
        masked.putalpha(mask)
        col, row = index % cols, index // cols
        sheet.alpha_composite(masked, (col * cell_w, row * cell_h))

    OUT.mkdir(parents=True, exist_ok=True)
    blp = OUT / f"{name}.blp"
    # Uncompressed BLP2 (encoding 3, BGRA). DXT5's two colour endpoints per
    # 4x4 block are worst-case for a smooth sphere: at orb size the health cell
    # (~2.5x) turns each block into a ~10 px patch and the Barbarian (~5x) a
    # ~20 px patch, which is the pixelation. Lossless costs ~5.6 MB / 1.4 MB
    # instead of ~1.3 MB / 0.35 MB; the designer accepted that for loose files.
    size = d3_tex_slice.build_ui_art.write_blp(sheet, blp, True)
    sheet.save(preview_dir / f"{name}.png")

    # Verify the mask on the packed sheet (all values are the packed alpha).
    alpha = sheet.getchannel("A")
    corner = alpha.getpixel((0, 0))
    body = alpha.getpixel((int(cx), int(cy)))
    ring = []
    for step in range(0, 360, 5):
        radians = math.radians(step)
        for r in (radius, radius + feather, radius + 3, radius + 6):
            x = int(round(cx + r * math.cos(radians)))
            y = int(round(cy + r * math.sin(radians)))
            if 0 <= x < cell_w and 0 <= y < cell_h:
                ring.append(alpha.getpixel((x, y)))
    glow = [v for v in ring if 0 < v < 255]
    print(f"{stem}: {len(frames)} frames {cell_w}x{cell_h} -> {blp.relative_to(ROOT)} "
          f"({sheet_w}x{sheet_h}, {size // 1024} KiB)")
    print(f"  disc centre ({cx:.1f},{cy:.1f}) radius {radius:.1f}, feather {feather}")
    print(f"  packed alpha: corner {corner}, body centre {body}, "
          f"glow ring min {min(ring) if ring else 'n/a'} max {max(ring) if ring else 'n/a'} "
          f"partial {len(glow)}/{len(ring)}")


def main() -> int:
    preview_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/opencode")
    preview_dir.mkdir(parents=True, exist_ok=True)
    for job in JOBS:
        pack(*job, preview_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
