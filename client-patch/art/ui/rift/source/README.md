# Rift tracker art sources

`exocet-blizzard-light.ttf` — Blizzard's Exocet, the display face Diablo III draws its list
header ("OBJECTIVES") and its COMPLETE!/NEW!/UPDATE! flourishes in. `draw_rift_art.py` baked
those words into `rift_header_text.png` and the `rift_flourish_*.png` textures from this copy
until diablocraft-rift-tracker-exocet-slider (ruling 2026-10-04): the tracker draws them as real
font strings now, from the shipped `client-patch/addons/Torment/fonts/Exocet.ttf` that
`build_tooltip_fonts.py` builds, and those four textures are gone. The face is kept here as the
kit's pinned source. It is d3planner's copy of the font
(`https://d3planner.com`, its BNet asset pack `external/bnet/fonts/exocet/exocet-blizzard-light.ttf`),
the same face the D3 client uses. Blizzard art is fine by the designer (rift tracker brief, art plan
2026-10-03).

    sha256  754e738d05e884f0c3b980d0ad2512792d1d998ab267e8cbfc79df7f984d6be1
