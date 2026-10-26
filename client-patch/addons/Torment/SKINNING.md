# Skinning Torment

Everything Torment draws that has an image comes from a named slot in
`Diablocraft.ART`. A skin is an ordinary addon that fills those slots with its
own art. Nothing else is needed: no patch, no edit to Torment's Lua.

Two worked examples live in the repository under `client-patch/skins/`, neither
shipped: `TormentD3`, the designer's own skin, for the bottom bar and the orbs, and
`WindowSkinExample` for the windows ("Windows" below). Each is installed by hand.

## The shape of a skin

```
MySkin/
  MySkin.toc
  MySkin.lua
  media/ ...
```

`MySkin.toc`:

```
## Interface: 30300
## Title: MySkin
## Dependencies: Torment
```

`MySkin.lua`:

```lua
-- Torment declares the slots; the dependency above guarantees this file runs
-- after it, so Diablocraft.ART already exists.
local ART = Diablocraft.ART

-- Replace one image.
ART["slot-hover"] = {path = "Interface\\AddOns\\MySkin\\media\\slot_hover"}

-- Fill a whole globe: the sheet's geometry comes with the art.
ART["orb-health"] = {path = "Interface\\AddOns\\MySkin\\media\\healthglobe",
                     frames = 30, width = 1024, height = 1024,
                     cellW = 170, cellH = 170, cols = 6}

-- And the bar, which brings its own layout (see "The bar slot" below).
ART["bar"] = {path = "Interface\\AddOns\\MySkin\\media\\bar",
              width = 1416, height = 201, coords = {0, 0.69, 0, 0.78},
              wells = {...}, globeWells = {...}, strip = {...},
              stripTexture = "Interface\\AddOns\\MySkin\\media\\bar-fills", fills = {...}}
```

Set the slots while your addon loads. Torment re-applies the current slots once
at `PLAYER_LOGIN`, so a skin that loads after Torment is what the player sees.

Two rules for the images themselves:

- Power-of-two `.blp` or `.tga`. Anything else does not load.
- **A new image file needs a full client restart.** The client indexes the files
  in `Interface/AddOns` once, at startup; `/reload` re-runs the Lua but not that
  index, so a texture added while the game is running draws as nothing until the
  client is restarted.

## What a slot holds

A slot is a table. Every field is optional; what you leave out comes from
Torment's own art.

| field | meaning |
|---|---|
| `path` | the full texture path, e.g. `"Interface\\AddOns\\MySkin\\media\\foo"` (no `.blp`/`.tga`) |
| `file` | a file **in Torment's own art folder** (`Interface\AddOns\Torment\art\`); use `path` instead for your own art |
| `coords` | `{left, right, top, bottom}`, a `SetTexCoord` crop of the canvas |
| `tint` | `{r, g, b}`, a `SetVertexColor` tint |
| `colour` | the flat colour the slot draws when it has no image, and when art is off (`/dcstash noart`) |
| `slices` | `{left, right}`, two UV widths inside `coords`: the ends of a button frame that must not stretch (the death window, below) |

A slot with no `path`, no file and no `colour` draws the magenta probe, never
silently nothing.

Changing a slot **after** the game is running takes effect through
`Diablocraft.RefreshArt()` for the one-texture slots. The bar and the orbs are
laid out once from the slots, so their geometry changes need a `/reload`.

## The one-texture slots

Everything the stash, the character sheet, the Blacksmith, the Jeweler, the
Crafting, the Paragon and the Rift tracker windows draw, plus the skill bar's two
overlays:

`titlebar`, `panel-frame-fill`, `panel-frame-edge-top/bottom/left/right`,
`panel-frame-corner-tl/tr/bl/br`, `panel-frame-plain-tl/tr/bl/br`, `slot`,
`slot-hover`, `slot-selected`, the five `slot-rarity-*`, `tab-normal`,
`tab-selected`, `tab-locked`, `button`, `button-pressed`, `close`, `coin`,
`bug-report`, `skill-slotted` (the skill bar's chosen-slot border),
`skill-chosen` (its highlight).

The window parts every Torment window reads through `Diablocraft.Style` (the
server windows too), empty by default so a client with no skin looks as it did:
`window-panel`, `window-flat`, `window-title`, `window-close`,
`window-close-hover`, `button`, `button-hover`, `button-pressed`,
`button-disabled`, `tab`, `tab-active`, `slot`, `slot-hover`, `box`,
`box-active`, `row-select`, `row-hilite`, `bar-bg`, `bar-fill`, `input`,
`scroll-track`, `scroll-thumb`. A skin's picture is its `path`; the palette
parts also take `colour` (and `edge`) to recolour. How each is drawn is the
"Windows" section below.

## The death window's buttons

`dc_revive.lua` draws its three buttons from `death-button`,
`death-button-hover`, `death-button-pressed` and `death-button-disabled`, and a
glow behind the button from `death-button-glow`. Nothing ships for them: with no
skin each button is its slot's flat `colour` (dark red) inside a thin bronze
edge. A slot that carries an image replaces both, and the button keeps its own
size and wording, so the layout is the same with and without a skin.

`slices` is for a frame whose ornate ends must not stretch (the child client has
no 9-slice). Its two values are UV widths **inside `coords`**: the left cap is
`coords[1] .. coords[1]+left`, the right cap `coords[2]-right .. coords[2]`, and
the middle stretches between them. Nothing shipped sets it: the death window is
the one reader, and no art for those slots is in the repository - they stay
normal interfaces until a bead asks otherwise (ruling 2026-10-05).

## The bar slot

`bar` is the bottom bar ElvUI_Torment draws. Torment ships it filled: the designer's
generated hotbar (the two orb frames with the demon and the angel, and the bar
between them; `client-patch/art/ui/elvui/cut_hotbar_art.py`, diablocraft-lhoeu),
with `orb-back` its black glass. A skin replaces it like any slot. With the slot
emptied, the mock HUD draws
instead: a flat near-black panel fitted to the eight buttons, with a bronze frame
as thick as the orb ring, its ends cut to the two orb rings, eight well
backgrounds, a thin purple XP strip in its top rows and the micro bar spot.

A skin's `bar` carries the art and the layout together:

| field | meaning |
|---|---|
| `path` | the bar art |
| `width`, `height` | the canvas in pixels |
| `coords` | the crop that trims the power-of-two padding |
| `wells` | eight `{left, top, width, height}`, the eight action buttons' wells, in canvas pixels from the top-left |
| `globeWells` | `{health = {centreX, centreY, diameter}, power = {...}}`, where the orbs sit |
| `micro` | optional `{left, top, width, height}`, the micro menu's opening: ElvUI's micro bar is centred in it and shrunk to fit. Left out, a skin leaves the micro bar where ElvUI puts it |
| `strip` | `{left, top, width, height}`, the XP strip |
| `stripTexture` | the sheet the `fills` crop lives in (a `SetStatusBarTexture` path). Left out, the `bar-buttons` slot's sheet is used; with neither, the mock's flat tinted sheet |
| `fills` | `{blue = {l, r, t, b}, orange = {l, r, t, b}}`, the XP fill's `SetTexCoord` crop **in the `stripTexture` sheet** (orange is drawn at max level) |

`bar-buttons` is the button sheet: `path`, and `portal = {normal, highlight,
disabled}`, three `SetTexCoord` crops for action button 8 (the portal). They are
drawn with `ADD` blending. Without this slot, button 8 is an ordinary well.

## The orb slots

`orb-health` and one `orb-resource-<key>` per D3 resource key (`fury` for
Warrior Rage, `arcane_power` for Mage Energy, `spirit` for Monk Runic Power; more join as their class goes
live) are the liquid. Torment reads the class and power tokens, so two classes
on one WoW slot keep their own globe.

A globe slot is one sheet, or a pair:

| field | meaning |
|---|---|
| `path` | the first sheet (frames 1..n/2 with `path2`, else 1..n) |
| `path2` | optional second sheet (frames n/2+1..n) |
| `frames` | how many frames the animation has |
| `width`, `height` | the sheet's size |
| `cellW`, `cellH`, `cols` | the grid: cell size and columns, rows follow |
| `disc` | for a fill whose cell is bigger than its liquid disc: the disc's size in the cell |
| `glow` | `true` for D3's own health sheet, whose flat light Torment adds back with a second `ADD` pass |

The designer's delivered fills are 60 frames over two sheets (`..._1` and `..._2`); each
sheet is 1024x1024 RGBA, 30 cells of 170x170 in 6 columns by 5 rows from the
top-left, a 160px disc with a 5px transparent margin, full liquid only. The code
plays sheet 1 then sheet 2 and loops, at one speed: 20 frames a second
(`/ec` -> Torment -> orb animation).

The cosmetics are separate slots and draw only when filled:
`orb-back` (the plate under the liquid), `orb-gloss` (additive), `orb-spark`
(additive), `orb-lowhp-glow` (additive) and `orb-skull`.

The ring around a globe is part of the bar art, not a slot: the bar's
`globeWells` are where the orbs sit and the bar's own art carries the ring, so a
skin that fills `bar` fills its rings with it.

## Windows

Every Torment window (the stash, the character sheet, the artisans, the Cube,
the Paragon, the rift windows, the bug report and the rest) draws from slots
too, in two layers. All of them are empty by default: with no skin a window
looks exactly as it does without one, and a skin fills only what it wants.

1. **Window parts**: the frame, title, close button, buttons, tabs, item slots,
   boxes, list rows, bars, input boxes and scrollbars every window is built
   from. Fill one and every window that has that part wears it.
2. **Whole windows**: one slot per window, holding one picture of the whole
   window (a *canvas*) and the spots on it where the window's pieces go. Fill
   one and that window is drawn on your canvas instead of its frame.

The layers work together: a whole-window canvas replaces a window's frame, and
the slots, buttons and rows inside it still come from the parts.

### Window parts

The frame and the stock pieces (empty means the client's own look):

| slot | what it is | fields |
|---|---|---|
| `window-panel` | every window's frame | backdrop fields, below |
| `window-flat` | the flat panels inside a window | backdrop fields; `colour` and `edge` are its ground and 1 px line |
| `window-title` | the window's title | `colour` (the text), `path` a plate behind it, `width` and `height` its size (else the title's) |
| `window-close`, `window-close-hover` | the close button, and under the mouse | `path`, `coords`, `tint` |
| `button`, `button-hover`, `button-pressed`, `button-disabled` | every native button's four states | `path`, `coords`, `tint`, `slices` |
| `input` | an input box (replaces its border) | `path`, `coords`, `tint` |
| `scroll-thumb`, `scroll-track` | a scrollbar's knob, and a strip behind the bar | `path`, `coords`, `tint` |

The flat parts, drawn in Torment's palette (empty means that palette):

| slot | what it is | `colour` | `edge` |
|---|---|---|---|
| `slot` | an item slot | its ground | its 1 px line |
| `slot-hover` | an item slot under the mouse (the stash) | | |
| `tab`, `tab-active` | a tab, and the tab on show | its line | |
| `box`, `box-active` | a framed box, and one holding an item | its line | |
| `row-select`, `row-hilite` | a list row's selection, and its hover | the colour | |
| `bar-bg`, `bar-fill` | a cast bar's ground, and its fill | the colour | the ground's line |

A flat part takes `colour` (and `edge`) to recolour it, or `path` for a
picture: the picture is laid over the part (a slot's picture covers its ground
and line; the item icon stays on top), so draw the whole part into it.

`slot`, `slot-hover`, `button` and `button-pressed` also have Torment's own art,
which the character sheet and the bounty map draw. To change them, set the whole
slot (`ART["slot"] = {...}`), not one field of it.

### The backdrop fields

`window-panel` and `window-flat` are drawn the way the client draws any window
frame: a background and one *edge strip*.

| field | meaning |
|---|---|
| `path` | the background picture |
| `edgePath` | the edge strip |
| `edgeSize` | how thick the edge is drawn, in pixels |
| `tile`, `tileSize` | repeat the background in squares of this size, instead of stretching it |
| `insets` | `{left, right, top, bottom}`: how far the background stays inside the edge |
| `colour`, `edge` | tint the background, and the edge (`{r, g, b, a}`) |

A field you leave out keeps the client's own dialog look.

**The edge-strip rule.** This client draws a frame's edge only from one strip:
eight equal squares side by side, left to right: the left edge, the right edge,
the top edge, the bottom edge, then the top-left, top-right, bottom-left and
bottom-right corners. A 16-pixel edge is a 128 x 16 picture. The four edge
squares are stretched or repeated along their side; the top and bottom ones are
turned a quarter by the client, so paint them as upright strips like the sides.
A frame that cannot be cut that way (a shaped outline, ornaments that must not
repeat) belongs in a whole-window canvas instead.

### Whole windows

One slot per window:

| slot | window | its pieces a skin can place |
|---|---|---|
| `window-cube` | Kanai's Cube | title, close, buttons: Transmute, the recipe book |
| `window-blacksmith` | the Blacksmith | title, close, tabs |
| `window-jeweler` | the Jeweler | title, close, tabs |
| `window-mystic` | the Mystic | title, close, tabs, buttons: the action button |
| `window-paragon` | Paragon | title, close, buttons: Respec, Refresh |
| `window-urshi` | Urshi | title, close, buttons: Upgrade |
| `window-greater-rift` | the Greater Rift opener | title, close, buttons: Open |
| `window-tier` | Difficulty | title, close |
| `window-stash` | the stash | title, close, tabs (the stash tabs), buttons: Buy Tab |
| `window-inventory` | the character sheet | close, buttons: Paragon |
| `window-bounty-map` | the bounty panel on the world map | title, buttons: New bounties |
| `window-bug-report` | the bug report | title, close, buttons: Cancel, Send |
| `window-revive` | the death window | title, buttons: the three revive buttons, top to bottom |

`window-account`, `window-elite`, `window-crafting` and `window-dungeon-finder`
are declared too, but no Torment window reads them yet: filling one changes
nothing until such a window exists.

A whole-window slot:

| field | meaning |
|---|---|
| `path` | the canvas picture |
| `width`, `height` | the canvas in its own pixels (the part of the file that is the window) |
| `coords` | `{left, right, top, bottom}`, the same part as a crop of the file (the file is a power of two, the canvas need not be) |
| `anchors.content` | `{left, top, width, height}`: where the window's own body goes |
| `anchors.title`, `anchors.close` | the spots for the title and the close button |
| `anchors.tabs`, `anchors.buttons` | one spot per tab or button, in the order the table above lists them |

Every spot is `{left, top, width, height}` in canvas pixels from the canvas's
top-left corner. How Torment draws it:

- The window's own body (its slots, lists and text, laid out as always) is the
  `content` spot. Torment scales the canvas so `content` is as wide as the
  window, and uses that one scale for the height too, so draw `content` in the
  window's own proportions (the Cube's body is 300 x 460).
- The window's frame is hidden and the canvas drawn around the body.
- The title is centred on its spot at the spot's width; the close button, tabs
  and buttons are centred on theirs at the spot's size. A piece with no spot
  stays where the window puts it.
- With art off (`/dcstash noart`) no canvas is drawn.

### Worked example

**A recolour and a new frame**, in your skin's Lua:

```lua
local ART = Diablocraft.ART
local MEDIA = "Interface\\AddOns\\MySkin\\media\\"

-- Gold lines on every tab on show and every framed box: colours only.
ART["tab-active"] = {colour = {1.00, 0.84, 0.40}}
ART["box"] = {colour = {0.60, 0.45, 0.25}}

-- Every window's frame: your background and your 16-pixel edge strip (128 x 16).
ART["window-panel"] = {path = MEDIA .. "mypanel", edgePath = MEDIA .. "myedge",
                       edgeSize = 16, tile = false}

-- Every native button: your button picture, its ends kept unstretched.
ART["button"] = {path = MEDIA .. "mybutton", coords = {0, 1, 0, 0.5},
                 slices = {left = 0.1, right = 0.1}}
ART["button-pressed"] = {path = MEDIA .. "mybutton_down", coords = {0, 1, 0, 0.5},
                         slices = {left = 0.1, right = 0.1}}
```

**One whole window.** `client-patch/skins/WindowSkinExample/` in the repository
is a complete skin that draws the Cube on its own canvas; copy it and change it.
To make your own:

1. Draw the window as one picture, `mywindow.tga` (or `.blp`), on a power-of-two
   file: a canvas 256 x 400 sits on a 256 x 512 file. Leave room for the body:
   the Cube's is 300 x 460, so its `content` spot is that shape at your scale.
2. Measure, in the picture's pixels from the top-left: the canvas size, the
   `content` spot, and a spot for the title, the close button and each button.
3. Fill the slot:

```lua
ART["window-cube"] = {
    path = MEDIA .. "mywindow",
    width = 256, height = 400,
    coords = {0, 1, 0, 400 / 512},
    anchors = {
        content = {left = 21, top = 36, width = 214, height = 328},
        title = {left = 21, top = 8, width = 214, height = 22},
        close = {left = 232, top = 8, width = 18, height = 18},
        buttons = {
            {left = 78, top = 370, width = 100, height = 18},   -- Transmute
            {left = 200, top = 368, width = 22, height = 22},   -- the recipe book
        },
    },
}
```

4. Copy the skin's folder into `Interface\AddOns\` and restart the client (a new
   picture needs a restart), then open the window.

### Changing slots while playing

Torment applies the slots at login, so a skin that loads after it is what you
see. A skin that changes a slot later calls `Diablocraft.RefreshArt()`: that
re-applies every window's frame and canvas (its spots included) and every
picture already drawn. A part that had no picture until now, and the colours
a window already drew, take a `/reload`.

### Frame names

Frame names are stable; never rename one. The top-level frames:

`DiablocraftStashFrame`, `DiablocraftInventoryFrame`, `DiablocraftSidePanel`,
`DiablocraftSkillbarFrame`, `DiablocraftJewelerFrame`, `DiablocraftSocketsFrame`,
`DiablocraftCraftingFrame`, `DiablocraftParagonFrame`, `DiablocraftTierFrame`,
`DiablocraftRiftTracker`, `DiablocraftRiftBar`, `DiablocraftMaterialsList`,
`DiablocraftDetailsScroll`, `TormentBlacksmithFrame`, `TormentCubeFrame`,
`TormentUrshiFrame`, `TormentGreaterRiftOpenFrame`, `DiablocraftReviveFrame`,
`TormentBountyMapFrame`, `TormentBugReportFrame`, `TormentButtonStrip`,
`TormentVersionNotice`.

## What a skin cannot change

Item icons, spell icons and in-world art are not addon textures: they come from
the client's own files, and only a patch MPQ can replace them. The launcher
warns about a patched client and never blocks it.
