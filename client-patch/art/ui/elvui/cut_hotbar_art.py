#!/usr/bin/env python3
"""Cut the designer's generated hotbar sheet into the HUD art Torment ships (diablocraft-lhoeu).

The source is `source/hotbar-full-v2.jpg` (2000x388, Nano Banana 2.1, ruling 2026-10-11): generated art, not
Blizzard's, so it ships. Brief: azerothcore-wotlk/build/_agent-scratch/hotbar-art-2026-10-11/. It fills the
`bar` and `orb-back` slots in client-patch/addons/Torment/ArtSlots.lua (SKINNING.md); the geometry this
prints is what that table carries.

  hud_bar.png       the whole sheet, both orb frames with the demon and the angel and the bar between them,
                    on a black key. One texture, drawn over the orbs (barart.lua ART_LEVEL), so the liquid
                    shows only through the holes and the figures stay on top. Keyed: black reached from the
                    background, from inside each orb and from inside each of the nine openings (six skills,
                    potion, Town Portal, micro menu). Black that none of them reaches stays: the XP channel
                    and the shadows inside the figures. Inside each orb hole, outside the figure that reaches
                    into it, every pixel is light-keyed instead (alpha = its brightness): the glass shine
                    stays in this texture as a highlight over the liquid. The shine is in the bar art, not
                    the orb-gloss slot, because the two shines differ and orb-gloss is one image for both.
  hud_orb_back.png  the black disc under the liquid, the size of the liquid's own disc, so an empty orb is
                    the sheet's black glass rather than a hole onto the world.
  hud_xp_fill.png   the XP strip's fill: the mock's purple (#8a4bd0), one colour at every level as the mock.

    python client-patch/art/ui/elvui/cut_hotbar_art.py
    python client-patch/build_ui_art.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ModuleNotFoundError:                      # Pillow is vendored in the shared scratch
    sys.path.append(str(Path(__file__).resolve().parents[4] / "azerothcore-wotlk" / "build" / "_agent-scratch"
                        / "pil"))
    from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SHEET = HERE / "source" / "hotbar-full-v2.jpg"

# Every measurement below is in sheet pixels, read off the sheet: the hole circles by an edge-score fit to
# the ring's inner edge (sectors clear of the shine and the figures), the openings and the XP channel as
# runs of black between their frames.
#
# The crop: rows 68..387 (to the bar's lower rim, the sheet's last row) and columns 0..2021, 22 columns of
# padding past the sheet's right edge, so the orbs sit about the canvas centre exactly as the mock's do
# (3 art units right of it) and nothing moves when the art replaces the mock.
CROP = (0, 68, 2022, 388)
# Art units per sheet pixel: the mock's orb centres are 936 apart (barart.lua GLOBE_WELLS), the sheet's
# 1332, so the orbs land on the mock's centres and the rest follows the sheet's own proportions.
K = 936 / 1332
# centreX, centreY, hole radius.
ORBS = {"health": (349, 229, 136), "power": (1681, 227.5, 138)}
# The figures reach into the holes: the demon's horn, head and claw into the health orb, the angel's hood
# and sword arm into the power orb. Inside these boxes the black key decides, so the figure stays opaque.
FIGURES = {"health": (0, 145, 315, 388), "power": (1745, 135, 2022, 388)}
# The openings, inclusive (left, top, right, bottom): wells 1-6 the skills, 7 the potion, 8 the Town
# Portal's gold slot (its rim is art, not a highlight), then the micro menu's panel.
WELLS = [(530, 258, 613, 348), (637, 258, 721, 348), (743, 258, 827, 348), (850, 258, 934, 348),
         (957, 258, 1040, 348), (1063, 258, 1146, 348), (1169, 258, 1252, 348), (1278, 258, 1318, 348)]
MICRO = (1344, 258, 1497, 348)
XP = (508, 226, 1524, 237)
# Each button is drawn this many art units past its opening on every side: buttonart.lua insets the icon by
# its default iconInset (2), so the icon covers the opening and the hole shows only in an empty slot.
GROW = 2
# The black key: a seed's flood takes pixels whose r+g+b is within FLOOD of black; inside it alpha ramps
# from 0 at a brightest channel of KEY_LO to opaque at KEY_HI, with the colour un-premultiplied so the
# edge composites over black exactly as the sheet.
FLOOD = 36
KEY_LO, KEY_HI = 4, 16
# The orb geometry the code reads: orbs.lua draws a fill's disc at RING_INNER (164/174) of the orb, so
# the orb is the hole plus OVERLAP pixels a side, over that fraction; the ring covers the overlap.
RING_INNER = 164 / 174
OVERLAP = 2
XP_COLOUR = (0x8a, 0x4b, 0xd0, 255)


def inside(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def flooded(sheet: Image.Image) -> set:
    """Pixels of the sheet the black key takes: every seed's black, flood-filled."""
    marked = sheet.copy()
    marker = (255, 0, 255)
    seeds = [(x, 0) for x in range(0, sheet.width, 25)]
    seeds += [(cx, cy) for cx, cy, _ in ORBS.values()]
    seeds += [((l + r) // 2, (t + b) // 2) for l, t, r, b in WELLS + [MICRO]]
    for x, y in seeds:
        ImageDraw.floodfill(marked, (int(x), int(y)), marker, thresh=FLOOD)
    pixels = marked.load()
    return {(x, y) for y in range(sheet.height) for x in range(sheet.width) if pixels[x, y] == marker}


def unpremultiply(colour, alpha):
    if alpha <= 0:
        return (0, 0, 0, 0)
    return tuple(min(255, round(c * 255 / alpha)) for c in colour) + (alpha,)


def bar(sheet: Image.Image) -> Image.Image:
    key = flooded(sheet)
    source = sheet.load()
    out = Image.new("RGBA", (CROP[2] - CROP[0], CROP[3] - CROP[1]), (0, 0, 0, 0))
    pixels = out.load()
    for y in range(CROP[1], CROP[3]):
        for x in range(CROP[0], min(CROP[2], sheet.width)):
            colour = source[x, y]
            brightest = max(colour)
            hole = next((name for name, (cx, cy, r) in ORBS.items()
                         if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 < r * r), None)
            if hole and not inside(FIGURES[hole], x, y):
                pixel = unpremultiply(colour, brightest)
            elif (x, y) in key:
                alpha = max(0, min(255, round((brightest - KEY_LO) * 255 / (KEY_HI - KEY_LO))))
                pixel = unpremultiply(colour, alpha)
            else:
                pixel = colour + (255,)
            pixels[x - CROP[0], y - CROP[1]] = pixel
    return out


def disc(size: int = 256) -> Image.Image:
    """Black, the liquid's own diameter (RING_INNER of the canvas), a one-pixel soft edge."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = image.load()
    half, radius = size / 2, size * RING_INNER / 2
    for y in range(size):
        for x in range(size):
            d = ((x + 0.5 - half) ** 2 + (y + 0.5 - half) ** 2) ** 0.5
            pixels[x, y] = (0, 0, 0, max(0, min(255, round((radius - d + 0.5) * 255))))
    return image


def units(value: float) -> float:
    return round(value * K, 2)


def geometry() -> dict:
    """The bar slot's geometry in art units, from the measurements above."""
    def rect(box, grow=0):
        l, t, r, b = box
        return {"left": round(units(l - CROP[0]) - grow, 2), "top": round(units(t - CROP[1]) - grow, 2),
                "width": round(units(r - l + 1) + 2 * grow, 2), "height": round(units(b - t + 1) + 2 * grow, 2)}
    globes = {name: {"centreX": units(cx - CROP[0]), "centreY": units(cy - CROP[1]),
                     "diameter": units((2 * r + 2 * OVERLAP) / RING_INNER)}
              for name, (cx, cy, r) in ORBS.items()}
    return {"width": units(CROP[2] - CROP[0]), "height": units(CROP[3] - CROP[1]),
            "wells": [rect(w, GROW) for w in WELLS], "micro": rect(MICRO), "strip": rect(XP), "globeWells": globes}


def main() -> int:
    sheet = Image.open(SHEET).convert("RGB")
    bar(sheet).save(HERE / "hud_bar.png")
    disc().save(HERE / "hud_orb_back.png")
    Image.new("RGBA", (8, 8), XP_COLOUR).save(HERE / "hud_xp_fill.png")
    for name, value in geometry().items():
        print(name, value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
