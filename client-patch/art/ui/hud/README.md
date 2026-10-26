# HUD art kit (retired)

The Roth UI textures this folder held — `hud_body`, `hud_cap_left/right`,
`orb_*`, `slot_*`, `menu_*` and `xp_bar`, all listed below — were removed on
2026-10-04 (diablocraft-lido part A, the designer: "Roth_UI, the skull, the 45 blacksmith
panels, all of it can go"). The mock HUD that replaces them is drawn in Lua from
flat colour fills (`client-patch/addons/ElvUI_Torment/barart.lua`), so this kit
built nothing and was only kept as reference. `reference/addons/rothui/` keeps
the upstream package.

What is left:

- `icon_potion.png`, `icon_town_portal.png` — kept from the kit before Roth UI;
  not built into any addon.
- `source/` — the superseded AI-generated kits, reference only.

Was: sources (all copied as-is unless noted).

- `hud_cap_left/right.png` — `archive/rBottomBarStyler/d3tex/figure_left/right.tga`
  (512x256, ring built in, glass hole transparent).
- `hud_body.png` — `wow4.0/rTextures/d3_bar10.tga` (1024x128) with the baked
  "1–5 / mouse / Tab" labels painted over with the bar's own stone.
- `orb_back / orb_fill_* / orb_gloss.png` — `wow4.0/rBBS/media/orb_*.tga`;
  the grey filling was tinted red and orange here (one file per orb).
- `orb_swirl.png`, `orb_swirl2.png` — `wow4.0/rTextures/galaxy2.tga`, `galaxy4.tga`.
- `slot_*.png` — `wow4.0/rTextures/d3_action_button_orig / pushed / hover /
  checked / gloss.tga` (64).
- `menu_pushed / menu_highlight.png` — `pushed.tga` masked to a disc (the six
  menu buttons and their icons are baked into `hud_body.png`).
- `xp_bar.png` — `archive/rBottomBarStyler/d3tex/xpbar.tga` (1024x32).

Layer order was: body → caps (over the body ends) → orb_back → orb_fill (clipped)
→ orb_swirl layers (additive, rotating) → orb_gloss → slots and glyphs → xp fill
→ xp_bar frame. Construction followed docs/research/hud-addon-anatomy.md. `build_ui_art.py`
never built this folder ("Reference art for removed UI, including art/ui/hud/, is
deliberately not built"), so nothing referenced the retired files.
