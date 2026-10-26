# HUD art kit

Painted by Gemini (2026-09-13, v3 renders in `source/`), sliced by Claude
(Cowork) into the pieces the addon assembles; layer order and pixel rects are
in `manifest.csv`. Scale: every piece is the painting at 0.5, so the assembled
HUD is 1280 UI units wide at scale 1 (`docs/screenshots/UI_HUD_Kit_Assembly.png`
is the test assembly). Construction follows docs/research/hud-addon-anatomy.md.

- `hud_cap_left/right.png` (512x512) — orb bracket + ring + EMPTY glass; the
  glass centre and radius for each are in the manifest.
- `hud_body.png` (1024x512) — bar body with crest and eight slot frames baked
  in; aperture rects (0 = potion, 1–6 skills, 7 = Town Portal) in the manifest.
- `orb_fill_red/orange.png` (256) — full liquid disc, diameter = glass; the
  addon clips it from the bottom to Life % / Fury %. Draw ABOVE the cap.
- `orb_gloss.png` (256) — glass highlights, ADDITIVE, above the fill.
- `orb_swirl.png` (256) — galaxy layer, ADDITIVE, low alpha, rotate; three
  copies at different speeds and alphas.
- `slot_normal/pushed/highlight/checked.png` (128) — state overlays sized to
  the baked apertures; highlight and checked are ADDITIVE.
- `menu_<name>.png` (128, content 96x128) — six baked menu buttons;
  `menu_pushed/highlight.png` overlay.
- `icon_*.png` (64) — potion and Town Portal glyphs for their slots; menu
  glyphs kept for later use.
Convert with client-patch/build_ui_art.py like the stash kit.
