# Supplied angelic wings

The designer supplied `C:\Project-Heimdall\WoW-Client\Data\patch-f .mpq` on 2026-09-08
and requested integration in World of DiabloCraft with additional colors.
Archive SHA256: `d2cbac4b52010184ab34eb09d2d50e3590a860c8d2305f5247c039968b933ace`.

These five asset files are unchanged extracts. `source-records.json` records
the four added visual records, with string offsets resolved to strings.
The designer selected scripted texture recoloring; the generator changes DXT3 color
endpoints in every mip and preserves alpha and color-index bytes exactly.
The complete imported DBC files are not inputs to the build: their Spell.dbc
replaces spell 43024's visual and lacks the project's custom spells; its
SpellVisualEffectName.dbc also changes 89 unrelated stock model paths.

The model is MD20 version 264, with one animation, six bones, 810 vertices,
one skin, three textures, and no ribbon or particle emitters. All three BLP2
textures are 512 by 512. The texture named Red actually decodes as blue/cyan.
Keep the originals here; generated runtime files belong under `client-patch/art/`.

See `docs/research/wings-mpq-integration.md` for the inspection and
`docs/test-custom-wings.md` for deployment and in-game acceptance.
