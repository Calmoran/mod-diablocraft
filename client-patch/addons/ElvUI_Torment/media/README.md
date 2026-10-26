# ElvUI_Torment media

The shipped hotbar and the mock HUD's own art.

## `hud_bar.blp`, `hud_orb_back.blp`, `hud_xp_fill.blp`

The designer's generated hotbar (2026-10-11, not Blizzard art; diablocraft-lhoeu), the
shipped `bar` and `orb-back` slots in Torment's `Diablocraft.ART`. Cut from
`client-patch/art/ui/elvui/source/hotbar-full-v2.jpg` by
`client-patch/art/ui/elvui/cut_hotbar_art.py` (which says what each piece is and
prints the slot geometry), then converted by `build_ui_art.py`: `hud_bar` is the
2022x320 cut padded to 2048x512, the other two are power-of-two already.

## The mock HUD

Drawn only when the `bar` slot is emptied. The D3 art this folder used to carry
(the bottom bar, the button sheet, the globes, the skull and the orb cosmetics)
now lives in the designer's own skin, `client-patch/skins/TormentD3/`, which is never
shipped; `client-patch/skins/` and `manifest.py`'s `OWN_ADDONS` keep it out of a
release.

## `orb_ring.blp` and `orb_disc.blp`

Drawn by `client-patch/art/ui/elvui/mock_hud_art.py`, then converted by
`client-patch/build_ui_art.py` (BLP2, DXT5, full mip chain). They are the only
mock HUD images: its bar, wells, XP strip and micro spot are flat Lua fills.

`orb_ring` is a 256x256 canvas carrying the 4px drop shadow, the 8px bronze
ring, the 2px gold inner edge and the 60% dark glass the approved mockup draws,
scaled from that mockup's 174px orb. `orbs.lua` draws it 91/87 of the orb's size
(`MOCK_RING_OVER`), so the ring's outer edge lands on the orb's own edge and the
shadow fills the gap up to the bar's cut; the glass circle is 154/174 of the orb
(`MOCK_RING_INNER`), which is where a mock fill's disc is scaled to. The script
asserts both constants against the pixels it drew, so the two files cannot drift.

`orb_disc` is a white 256px disc with a soft 2px edge: the stand-in liquid for a
resource Torment has no sheet for, tinted per resource at runtime.

## The orb fills

The designer's own fills (Codex's second pass, `diablocraft-zgjb`), shipped as the mock
HUD's liquid. Each orb is 60 frames over two sheets:

| file | frames | grid | disc |
|---|---|---|---|
| `orb_fill_health_1.blp` | 1..30 | 1024x1024, 6 columns x 5 rows of 170x170 | 160px, 5px transparent margin |
| `orb_fill_health_2.blp` | 31..60 | the same | the same |
| `orb_fill_fury_1/2.blp` | the same | the same | the same |
| `orb_fill_arcane_power_1/2.blp` | the same | the same | the same |
| `orb_fill_spirit_1/2.blp` | the same | the same | the same |
| `orb_fill_wrath_1/2.blp`, `_essence_`, `_hatred_`, `_discipline_`, `_mana_`, `_maelstrom_` | the same | the same | the same |

`orbs.lua` plays sheet 1 then sheet 2 and loops, at one speed: 20 frames a
second (`E.db.torment.orbFps`, the Torment plugin's "Orb animation" slider).
Their sources are under `client-patch/art/ui/elvui/orb_fill_*_{1,2}.png`.

The Monk's Spirit fill is the Arcane Power one colour-shifted to tan/white (the designer,
card q-1013-23, diablocraft-9k91n): `client-patch/art/ui/elvui/shift_orb_fill.py`
writes `orb_fill_spirit_{1,2}.png` from `orb_fill_arcane_power_{1,2}.png`
(a gradient map on luminance, alpha unchanged; its `RAMP` is the look). Run it
before `build_ui_art.py` when the Arcane Power sources change.

The Shaman's Maelstrom fill is the same Arcane Power fill mapped to blue with a purple edge (the designer, card q-1021-157, "blue centre
fading to a subtle purple edge"): `client-patch/art/ui/elvui/maelstrom_orb_fill.py` writes `orb_fill_maelstrom_{1,2}.png` (a
gradient map on luminance through a blue ramp and a purple ramp, mixed by how far the pixel is from the middle of its cell's disc,
none at the middle and `EDGE_MIX` at the rim; alpha unchanged; its two ramps and three numbers are the look). The sheet's
`display_colour` for Maelstrom is the mean of that fill's brightest tenth, measured as the other powers' are.

Every other class power has the same orb in its own colour, never a flat disc:
`client-patch/art/ui/elvui/tint_orb_fills.py` writes `orb_fill_<token>_{1,2}.png`
(the token in lower case) for each row of
`mod-diablocraft/data/tunables/class_resources.csv` whose token has no hand-made
fill (Fury, Arcane Power, Spirit and Maelstrom keep theirs). Each pixel of the Arcane Power
fill becomes the row's `display_colour` scaled by its luminance over the fill's
brightest-tenth mean, so the tinted fill's brightest tenth is the sheet's
colour, which is how P0 measured it from D3's globes; alpha is copied unchanged.
It prints each fill's measured brightest tenth beside the sheet's colour. A
planned class's fill (Hatred, Discipline, the Witch Doctor's Mana) ships before
the class does, so its orb never starts as a stand-in. Run it, like
`shift_orb_fill.py`, before `build_ui_art.py` when a colour or the Arcane Power
sources change.

Rebuild, with the scratch Pillow venv (AGENTS.md; Pillow is a build-host
dependency, not shipped):

    azerothcore-wotlk/build/_agent-scratch/venv-pil/bin/python \
        client-patch/art/ui/elvui/mock_hud_art.py
    azerothcore-wotlk/build/_agent-scratch/venv-pil/bin/python \
        client-patch/art/ui/elvui/shift_orb_fill.py
    azerothcore-wotlk/build/_agent-scratch/venv-pil/bin/python \
        client-patch/art/ui/elvui/maelstrom_orb_fill.py
    azerothcore-wotlk/build/_agent-scratch/venv-pil/bin/python \
        client-patch/art/ui/elvui/tint_orb_fills.py
    azerothcore-wotlk/build/_agent-scratch/venv-pil/bin/python \
        client-patch/build_ui_art.py
