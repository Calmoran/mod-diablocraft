# wxl-loot-beam

A pillar of light over every corpse that can still be looted.

![A loot beam rising from a corpse](screenshot.jpg)

Hunting for the body you just killed means squinting at a pile of grey models and reading nameplates.
**Loot Beam** raises a beam of light straight up from every NPC body that can still be looted, so the
one worth walking to announces itself. The beam is capped at 20 yards by default -- tall enough to spot
across a camp or clear a low rise, short enough to stay a marker rather than a light show. By default
the world occludes it like any other geometry, so a body tucked behind a rise is hidden until you have
line of sight; turn **Through walls** on to draw through terrain and walls instead.

- a camera-facing shaft rises a little above the body and fades in from transparent there, peaking a
  short way up and easing to nothing at the top, with a horizontal falloff that keeps its edges soft
  and its core whiter;
- the whole thing breathes slowly and eases in and out, so a live beacon never reads as scenery;
- sparkle motes drift and twinkle through the shaft, each with its own drift, flicker and lifetime and
  each seeded from its corpse's GUID, so the light shimmers rather than sits and no two bodies sparkle
  in lockstep;
- colour, size, height, opacity, range, pulse, fade and the sparkles are all tunable from the in-game
  overlay panel under **Loot Beam**;
- with **Colour by loot rarity** on (the default), a corpse whose loot is known glows in the quality
  colour of its best item -- green for a green, purple for an epic -- instead of the default gold.

## Installation

### Client (the beacon itself)

This is a WarcraftXL module. It needs the **WarcraftXL** framework, which is installed next to
`Wow.exe` and loads modules from the client's `Extensions` folder. Nothing in this module patches the
client or its data.

**Through the WXL store:** install **Loot Beam** from the store and start the client. The store drops
the DLL and its INI into `<client>\Extensions\wxl-loot-beam\` for you.

**Manually:**

1. Make sure the WarcraftXL core is installed in your client folder (`WarcraftXL.dll` next to
   `Wow.exe`, along with the framework's own `d3d9.dll`).
2. Create the folder `<client>\Extensions\wxl-loot-beam\`.
3. Copy `wxl-loot-beam.dll` and `wxl-loot-beam.ini` into it. The framework discovers the folder by
   name, so keep the folder name `wxl-loot-beam`.
4. Launch the client. Open the WarcraftXL overlay and confirm the **Loot Beam** panel is present.

The `.ini` must sit next to the DLL. It is read live while the client runs: save a change and the
module picks it up within about a second, no restart. If the file is missing it is written with the
defaults on first load.

### Server module (optional)

The companion **mod-loot-beam** AzerothCore module colours a beam the instant a body dies, before
anyone opens it. It is **not** installed by the store or by cloning this repo -- those ship only the
client DLL and INI -- so a server owner has to build it into the worldserver. The server half is
entirely optional: the client still colours a corpse from the loot it learns when the loot window is
opened without it (see **Server-driven colour**).

1. Copy `server/mod-loot-beam/` into your server's `modules/` directory so it becomes
   `<azerothcore>/modules/mod-loot-beam/`. Keep the hyphenated folder name: the loader symbol
   `Addmod_loot_beamScripts` is derived from it.
2. Re-run CMake and rebuild `worldserver`; the module loader picks it up automatically (no core edits
   needed).
3. Put `mod_loot_beam.conf` beside `worldserver.conf` (copy the `.dist`) and set
   `LootBeam.Enable = 1`.
4. Start `worldserver` and check the log for
   `mod-loot-beam: server-driven loot beam colour is enabled` (it also notes
   `UNIT_FIELD_PADDING promoted to public`).

The module adds one setting, `LootBeam.Enable` (default 1), to `mod_loot_beam.conf`.

If the beams only colour **after** you open a corpse, the server half is not active: confirm the log
line in step 4 fired, that `LootBeam.Enable = 1`, and that `LootColor` and `ServerColor` are both on
in `wxl-loot-beam.ini`.

### Building from source

Targets 32-bit (Win32); sources are C++20 with a static CRT. This module is staged under its
extension id `wxl-loot-beam`.

```powershell
$core = "C:\Users\Strix\Documents\Github Projects\WXL-BUIDLER\wxl-build\wxl-core"
$dst  = "$core\extensions\wxl-loot-beam"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item ".\*" -Destination $dst -Recurse -Force

cmake -S $core -B "$core\build" -A Win32
cmake --build "$core\build" --config Release --target wxl-loot-beam --parallel

# copy the DLL back into this repo, backing up any existing one first
if (Test-Path "wxl-loot-beam.dll") { Copy-Item "wxl-loot-beam.dll" "wxl-loot-beam.dll.bak" -Force }
Copy-Item "$core\build\Release\wxl-loot-beam.dll" "wxl-loot-beam.dll" -Force
```

The game must be closed while deploying -- the running client locks the loaded DLL.

## Loot rarity colour

The beacon is tinted with the rarest item quality in the corpse's loot, using a per-tier palette
(currency, poor and common black, uncommon green, rare `#0032FF`, epic `#9600FF`, legendary orange,
artifact gold; each retunable in the INI or the panel). A corpse holding several items takes the
colour of the highest quality among them, so a body with one epic and a pile of greys reads purple. A
body whose loot is not known keeps the configured `Color`.

The 3.3.5a client only receives a corpse's loot when loot is requested for it -- normally the loot
window opening -- so on a stock server the quality colour appears once you have opened that body. The
module reads the loot the client already holds (via the client's own `GetNumLootItems` /
`GetLootSlotInfo` script functions) and caches the rarest quality against the corpse's GUID.

### Server-driven colour

To colour a beam the moment the body dies -- before anyone opens it -- run the companion
**mod-loot-beam** module (see **Server module** above). At creature death the server has just rolled
the corpse's loot, so it computes the rarest item quality in it and writes that back onto the corpse's
own `UNIT_FIELD_PADDING` update field as `quality + 1` (0 means "no hint"; 9 means the loot held money
but no gear, the `Currency` tier). The client reads that field straight out of the object it is
already walking, so the beacon is the right colour immediately and no custom opcode, addon message or
client patch is involved.

This is opt-in on the client too: with **Use server loot colour** on (the default, `ServerColor=1`)
the server's hint and the loot the client discovers for itself are merged, and whichever holds the
rarest item wins. The server still gives a body its colour the instant it dies, but it can never pin a
beacon below a rarer item the client later learns -- the colour only ever climbs. With the option off
the module ignores the field and uses the client's own loot alone. On a server that does not run the
module the field stays 0 and the client falls back to its own loot, so nothing needs changing.

Turn **Colour by loot rarity** off (or set `LootColor=0`) to use a single fixed tint; that disables
the server colour as well.

### Gear tiers

Every beam belongs to a **tier**, and each tier has its own colour and an on/off switch, both live in
the panel's **Gear tiers** section (and the `Tier.*` keys in the INI):

| Tier | Meaning |
|---|---|
| `Currency` | the corpse's loot held money but no gear (server-flagged; the client cannot tell on its own) |
| `Poor` .. `Heirloom` | the rarest item quality in the loot: 0 grey, 1 white, 2 green, 3 blue, 4 purple, 5 orange, 6 artifact, 7 heirloom |

A tier switched off produces **no beacon at all** for corpses whose rarest loot falls into it, so you
can hide e.g. currency-only or uncommon bodies and keep the rest. Each tier's default colour is set
in the INI and the panel (currency, poor and common ship pure black, rare `#0032FF`, epic `#9600FF`); a
body whose loot (and so tier) is not known still uses `Color`.

## How it works

Every frame the module walks the resident unit objects through the SDK's object enumerator, drops any
that are the player or still alive, and keeps the rest as beacon positions (optionally filtered to the
ones the server still flags `UNIT_DYNFLAG_LOOTABLE`). Positions are turned into world-space triangles
and drawn on `OnWorldSceneEnd`, which is the one point in the frame where geometry placed by world
coordinate lands where its coordinates say -- the scene's own view and projection are still on the
device and its depth buffer is complete. Nothing is retained: a body that stops being lootable loses
its beacon with no cleanup.

The draw is additive (source alpha added to the frame, so the beacon glows and never dims what is
behind it) with a colour on every vertex, so the GPU interpolates the falloffs and a handful of quads
read as a soft volume. The shaft is one camera-facing billboard, gridded across its width and up
its height so its horizontal and vertical falloffs read as light rather than a slab.

AzerothCore flags `UNIT_FIELD_PADDING` as a never-sent field, so the server module promotes it to a
public field in the core's runtime flag table when the config loads (one unused dword per unit
update). That is what carries the loot hint to nearby clients without a custom opcode, an addon
message or a core patch; it is why the module must run on the server and why a client-only install
never colours a body before its loot window opens.

## Tuning

The look lives in `wxl-loot-beam.ini` next to the DLL. The file is read live: save a change and the
module picks it up within about a second, no restart. The panel's **Save** button writes the current
slider values back to the file; **Revert** discards unsaved edits. If the file is missing it is written
with the defaults on first load.

| Key | Meaning |
|---|---|
| `Enabled` | master switch: 1 draws beacons, 0 leaves corpses unmarked |
| `Height` | how far the beam rises, yards (default 20) |
| `BaseOffset` | how far above the body the shaft begins, yards (default 1) |
| `BeamWidth` | half-width of the beam at its base (default 0.5) |
| `BeamAlpha` | opacity of the beam |
| `Color` | tint, as `#RRGGBB` |
| `Pulse`, `PulseSpeed` | breathing depth and rate |
| `FadeIn`, `FadeOut` | seconds to ease a beacon in on appear / out on loot (0 = instant) |
| `Sparkles` | draw drifting, twinkling motes around the beam (default on) |
| `SparkleCount` | motes per beacon, 0..32 (default 24) |
| `SparkleSize`, `SparkleAlpha` | half-size in yards (default 0.04) and peak opacity of a mote |
| `SparkleRise`, `SparkleDrift` | a mote's upward drift (default 1.0) and lateral wander (default 0.05), yards/s |
| `SparkleLife`, `SparkleTwinkle` | seconds a mote lives before it is reborn, and its flicker rate (default 6.0) |
| `MaxDistance` | ignore corpses beyond this range (0 = unlimited) |
| `ShowBeam` | draw the beam (the sparkles can still be shown without it) |
| `ThroughWalls` | off by default: the world hides the beam behind terrain, WMO and M2 objects (trees, rocks) like any other geometry; on draws through terrain and walls, so a rise cannot hide the beacon |
| `DepthPush`, `DepthPushPerYard` | yards the beacon is pulled toward the camera while occluded, plus extra per yard of distance, so the coarser terrain LOD at range cannot hide it |
| `WidthPerYard` | minimum beam half-width per yard of camera distance |
| `RequireLootable` | only beam corpses the server still flags lootable (default on) |
| `LootColor` | tint a known corpse by the rarest item quality in its loot (default on) instead of `Color` |
| `ServerColor` | also read the server's best-loot hint and let the rarest of it and the locally read loot win (default on) |
| `Tier.<name>.Enabled`, `Tier.<name>.Color` | per-tier on/off and colour; `<name>` is `Currency`, `Poor`, `Common`, `Uncommon`, `Rare`, `Epic`, `Legendary`, `Artifact`, `Heirloom` |

## Notes

- A looted body loses its beam. The default (`RequireLootable=1`) marks only corpses the server still
  flags `UNIT_DYNFLAG_LOOTABLE`, so once you loot one the flag clears and the beacon goes away. Set it
  to 0 to mark every dead NPC instead. If the flags field cannot be trusted on a given client build it
  falls back to the health-only verdict rather than turning into noise.
- Loot quality is only known for a body the client has been sent loot for, unless the server runs
  the companion **mod-loot-beam** module. The module does not request loot itself: it never asks the
  server for anything and never opens the loot window.
- Player corpses are left alone -- this marks NPC bodies.
- Purely visual: the module sends nothing to the server, and on a stock server the server never
  learns the beams exist. When the companion server module is present it only writes the corpse's own
  best-loot-quality back onto that corpse; it does not read anything from the client.
