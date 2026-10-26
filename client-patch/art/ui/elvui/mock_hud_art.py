#!/usr/bin/env python3
"""Draw the mock HUD's two orb images, then build them with build_ui_art.py.

The approved mockup (azerothcore-wotlk/build/_agent-scratch/mock-hud-2026-10-04)
is pure CSS; only its orb ring cannot be drawn from flat colour fills, because
3.3.5a has no texture masks and a square cannot make a circle. So the ring is
drawn here, once, as our own art. Nothing else in the mock HUD is an image.

  orb_ring.png  a 256x256 canvas: the 4px dark drop shadow, the bronze ring,
                the gold inner edge and the 60% dark glass inside, scaled from
                the mockup's 174px orb. Drawn at orb size x 91/87
                (elvui/orbs.lua MOCK_RING_OVER), so the ring's outer edge lands
                on the orb's own edge and the bar's cut (4px beyond it) hides
                the shadow's outer pixel.
                Round 2 (diablocraft-9z10, the designer): the ring is half the mockup's
                thickness - a 4px bronze band and a 1px gold inner edge in place
                of 8px and 2px - so the glass is 164 of the orb's 174 pixels
                (RING_INNER; the bar's own border is 4px to match).
  orb_disc.png  a white 256px disc with a soft 2px edge, tinted per resource by
                the orb code: the stand-in fill for a resource with no sheet.

The stock-texture search the brief asks for (B.3, diablocraft-rr2e), run before
this file: the 3.3.5 client's own Interface source kept for the UI audit
(`azerothcore-wotlk/build/_agent-scratch/pm-ui-audit-framexml-stock/`, 301
files) grepped for round/ring/orb/circle/disc texture names. The round textures
that source references are:

  Interface\\Buttons\\ButtonHilight-Round      an ADD highlight (PaperDollFrame.xml:501)
  Interface\\Minimap\\CompassRing              the minimap compass ring (Minimap.xml:336)
  Interface\\PlayerFrame\\UI-PlayerFrame-Deathknight-Ring    (RuneFrame.xml:28)
  Interface\\PlayerFrame\\UI-PlayerFrame-DeathKnight-GoldBorder (PlayerFrame.lua:554)
  Interface\\TimeManager\\ClockBackground      the round clock face (Blizzard_TimeManager.xml:298)
  Interface\\LFGFrame\\UI-LFG-ICON-REWARDRING  (AlertFrames.xml:33)
  Interface\\TargetingFrame\\UI-Classes-Circles  an eight-circle icon sheet

None fits: each is role art with its own baked colours, ticks or bevel and its
own size, an ADD glow, or an icon sheet, and the mockup's ring is three
concentric bands (8px bronze, a 2px gold inset edge, 60% dark glass) that a
single tinted texture cannot produce. The client's own MPQ listfile is not on
this box either - the archive reads in docs/archive/test-stash.md ran over SSH
from the client - so this is the source-level search, and the ring stays ours.

    python client-patch/art/ui/elvui/mock_hud_art.py
    python client-patch/build_ui_art.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent
SIZE = 256
HALF = SIZE / 2
# The mockup's orb is 174px across, with 4px of drop shadow outside it. The
# canvas covers the shadow: one canvas pixel is 91/128 of an art pixel.
ART = 174
CUT = 4
RING_OVER = 91 / 87          # what the code draws the image at; must equal orbs.lua
RING_INNER = 164 / 174       # the glass diameter the code fills; must equal orbs.lua
SCALE = HALF / (ART / 2 + CUT)
BRONZE_BAND = 4              # half the mockup's 8px ring (round 2)
GOLD_BAND = 1                # half the mockup's 2px inner edge
# From the mockup: a 2px + 1px drop shadow, the bronze band, the gold inset
# edge, then the glass. Colours are the mockup's own hex values.
SHADOW = (28, 19, 11, 230)
BRONZE = (107, 78, 44, 255)
GOLD = (199, 154, 74, 255)
GLASS = (10, 7, 5, 153)
DISC = (255, 255, 255, 255)
DISC_FEATHER = 2


def ring() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    pixels = image.load()
    shadow_outer = HALF
    bronze_outer = HALF - CUT * SCALE
    gold_outer = bronze_outer - BRONZE_BAND * SCALE
    glass_outer = gold_outer - GOLD_BAND * SCALE
    for y in range(SIZE):
        for x in range(SIZE):
            radius = math.hypot(x + 0.5 - HALF, y + 0.5 - HALF)
            if radius >= HALF:
                continue
            if radius >= bronze_outer:
                pixels[x, y] = SHADOW
            elif radius >= gold_outer:
                pixels[x, y] = BRONZE
            elif radius >= glass_outer:
                pixels[x, y] = GOLD
            else:
                pixels[x, y] = GLASS
    assert shadow_outer == HALF
    return image


def disc() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    pixels = image.load()
    radius = HALF - 1
    for y in range(SIZE):
        for x in range(SIZE):
            distance = math.hypot(x + 0.5 - HALF, y + 0.5 - HALF)
            if distance <= radius - DISC_FEATHER:
                alpha = 255
            elif distance >= radius:
                alpha = 0
            else:
                alpha = int(round(255 * (radius - distance) / DISC_FEATHER))
            if alpha:
                pixels[x, y] = (DISC[0], DISC[1], DISC[2], alpha)
    return image


def check(ring_image: Image.Image) -> None:
    """The two constants elvui/orbs.lua reads off this image must agree with it."""
    pixels = ring_image.load()
    middle = SIZE // 2
    # Walk out from the centre along the middle row: glass, then the gold inner
    # edge, the bronze ring, the shadow, then transparent.
    glass = 0
    while pixels[middle + glass, middle][:3] == GLASS[:3]:
        glass += 1
    outer = 0
    while outer < HALF and pixels[middle + outer, middle][3] != 0:
        outer += 1
    # Both radii are canvas pixels; the image is drawn at RING_OVER x orb size,
    # so the diameter in orb-size units is RING_OVER * 2 * radius / SIZE.
    inner = RING_OVER * 2 * glass / SIZE
    assert abs(inner - RING_INNER) < 0.005, f"glass diameter {inner:.4f}, code says {RING_INNER:.4f}"
    # The shadow reaches the canvas edge, so the ring's outer edge (the bronze,
    # CUT art pixels inside it) lands on the orb's own edge.
    edge = RING_OVER * 2 * (outer - CUT * SCALE) / SIZE
    assert abs(edge - 1.0) < 0.01, f"ring outer edge {edge:.4f}, expected 1.0"


def main() -> int:
    ring_image, disc_image = ring(), disc()
    check(ring_image)
    ring_image.save(OUT / "orb_ring.png")
    disc_image.save(OUT / "orb_disc.png")
    print(f"wrote orb_ring.png and orb_disc.png ({SIZE}x{SIZE}) to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
