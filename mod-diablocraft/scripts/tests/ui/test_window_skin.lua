-- luacheck: ignore 111 112 113 121 122 211 212 213 311 431 432
-- Run from repo root with `lua mod-diablocraft/scripts/tests/ui/test_window_skin.lua`.
--
-- Window skin slots: every generic window part is a named slot in Diablocraft.ART, read by DC.Style and through it by the server windows' kit (DCUI):
--
--   * every generic part is declared; the palette parts carry today's palette value as
--     their colour, the stock parts (the dialog backdrop, title, close, native button, input,
--     scrollbar) are empty, and with no skin DC.Style and DCUI hand out exactly today's look;
--   * a skin that recolours a part (a new slot table, or the colour changed in place) reaches
--     DCUI's palette, its callers' own U.SLOT_BG reads included;
--   * a skin's image (`path`) reaches each part: the window and flat backdrops (edge strip,
--     edge size and what is left out kept), the slot / tab / box faces, the row marks, the cast
--     bar, the title's colour and plate, the native button's four states (three pieces with
--     `slices`), the close button, the input box and the scroll bar;
--   * a window painted before the skin loaded (the stash and the sheet are built while Torment
--     loads) wears it after DC.RefreshArt (Torment's PLAYER_LOGIN), and art off draws the
--     skin's colours;
--   * DCUI with an addon from before the slots draws as before;
--   * every window Torment draws has an empty whole-window slot; a filled one (a canvas with
--     its size) hides the generic frame, draws the canvas around the window's body at the
--     window's width (both axes at one scale) and puts the declared title, close, tabs and
--     buttons on their anchors, also when the skin loaded after the window was built; art off,
--     a canvas with no size, a window with no key and an old addon draw no canvas;
--   * SKINNING.md's "Windows" section names every part and window slot, the backdrop fields,
--     the edge-strip rule, the anchors and live changes, points at the example, and names no game,
--     company or art source.
--
-- That nothing changes with no skin is also proved window by window: every Lua UI test's
-- widget state at the end of the test, nightly against this branch, identical. A stub cannot prove what the client renders, only what the
-- addon asks it to draw.

_G.AIO = {AddAddon = function() return false end}
dofile("mod-diablocraft/lua/aio/dc_aio_ui.lua")
local U = _G.DCUI

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
_G.AIO = {AddHandlers = function() return {} end, Handle = function() end}
_G.Diablocraft = {Econ = {Gold = tostring, OnChange = function() end}}
_G.require = nil
_G.PickupContainerItem = function() end
_G.PickupInventoryItem = function() end
_G.DEFAULT_CHAT_FRAME = {AddMessage = function() end}
dofile("mod-diablocraft/scripts/dc_addon_core.lua")
local DC = _G.Diablocraft
local ART, Style = DC.ART, DC.Style

local function same(a, b, label)
    assert(type(a) == "table" and type(b) == "table", label .. ": missing")
    assert(#a == #b, label .. ": " .. #a .. " values against " .. #b)
    for index = 1, #b do
        assert(math.abs(a[index] - b[index]) < 1e-9, label .. ": value " .. index .. " is " .. tostring(a[index])
            .. ", want " .. tostring(b[index]))
    end
end
-- Run `body` with some slots replaced, then put Torment's own back.
local function skin(slots, body)
    local saved = {}
    for name, slot in pairs(slots) do saved[name] = ART[name]; ART[name] = slot end
    local ok, err = pcall(body)
    for name in pairs(slots) do ART[name] = saved[name] end
    assert(ok, err)
end

-- ------------------------------------------------ (1) the slots, and no skin is today's look
local PARTS = {"window-panel", "window-flat", "window-title", "window-close", "window-close-hover", "button",
    "button-hover", "button-pressed", "button-disabled", "tab", "tab-active", "slot", "slot-hover", "box",
    "box-active", "row-select", "row-hilite", "bar-bg", "bar-fill", "input", "scroll-track", "scroll-thumb"}
for _, name in ipairs(PARTS) do assert(type(ART[name]) == "table", "the brief's part " .. name .. " is a slot") end
for _, name in ipairs({"window-panel", "window-title", "window-close", "window-close-hover", "button-hover",
                       "button-disabled", "input", "scroll-track", "scroll-thumb"}) do
    assert(next(ART[name]) == nil, name .. " is stock art today, so its slot is empty")
    assert(Style.Skin(name) == nil, "and an empty " .. name .. " is not a skin")
end
-- The palette parts: the colour (and edge) is the palette's, DCUI's default value for value.
for key, where in pairs(Style.PALETTE_PARTS) do
    same(Style.Colour(key), U.PALETTE[key], "no skin: " .. key)
    same(U[key], U.PALETTE[key], "no skin: DCUI's " .. key)
    if not ART[where[1]].file then same(ART[where[1]][where[2]], U.PALETTE[key], where[1] .. "'s " .. where[2]) end
end
-- Torment's own `slot` (the sheet's and the bounty map's art) keeps its file and art-off colour,
-- and is no image a window would draw: the flat windows keep the palette's.
assert(ART["slot"].file == "slot_empty" and Style.Image("slot") == nil and Style.Skin("button") == nil,
    "Torment's own slot and button art are not a skin")
assert(Style.Backdrop("window-panel") == Style.backdrop and Style.Backdrop("window-flat") == Style.flat,
    "no skin: the stock dialog and flat backdrops")
local window = U.window("SkinTestWindow")
assert(window.backdrop == Style.backdrop and window.backdropColor == nil, "no skin: the window is the stock dialog, untinted")
local title = U.title(window, "Cube")
assert(title.textColor == nil and window.dcTitlePlate == nil, "no skin: the title is the font's own gold, no plate")
local slot = U.slot(window, 40)
assert(slot.dcFace == nil, "no skin: a slot is the flat ground and edge, no face")
local button = U.button(window, 100, "Go")
assert(button.template == "UIPanelButtonTemplate" and button.dcStateArt == nil and button.dcSlices == nil,
    "no skin: the native button, untouched")
local row = U.row(window)
assert(row.mark.texture == U.EDGE, "no skin: the row mark is the flat edge texture")

-- ------------------------------------------------ (2) a recolour reaches every reader
skin({tab = {colour = {.1, .2, .3}}, slot = {colour = {.4, .5, .6}, edge = {.7, .8, .9}}}, function()
    same(U.TAB_IDLE, {.1, .2, .3}, "a skin's tab colour is DCUI's TAB_IDLE")
    same(U.SLOT_BG, {.4, .5, .6}, "a skin's slot colour is the slot ground")
    same(U.SLOT_BORDER, {.7, .8, .9}, "and its edge the slot border")
    local tab = U.tab(window, 32)
    same({tab.borderColor[1], tab.borderColor[2], tab.borderColor[3]}, {.1, .2, .3}, "a DCUI tab draws it")
    same({tab.backdropColor[1], tab.backdropColor[2], tab.backdropColor[3]}, {.4, .5, .6}, "on the skin's slot ground")
end)
local box = ART["box"].colour
ART["box"].colour = {.2, .2, .2}
same(U.BOX_BORDER, {.2, .2, .2}, "a colour changed in place reaches DCUI too")
ART["box"].colour = box

-- ------------------------------------------------ (3) an image reaches each part
skin({["window-panel"] = {path = "Skin\\panel", edgePath = "Skin\\edge", edgeSize = 16}}, function()
    local frame = U.window("SkinTestWindow2")
    assert(frame.backdrop.bgFile == "Skin\\panel" and frame.backdrop.edgeFile == "Skin\\edge"
        and frame.backdrop.edgeSize == 16, "the skin's window background, edge strip and edge size")
    assert(frame.backdrop.tile == true and frame.backdrop.insets == Style.backdrop.insets,
        "and what it left out is the stock dialog's")
end)
skin({["window-flat"] = {path = "Skin\\flat", colour = {0, 0, 0}, edge = {0, 0, 0}}}, function()
    local panel = Mock.widget("Frame", nil, window)
    U.flat(panel, 1, 1, 1, 1, 1, 1)
    assert(panel.backdrop.bgFile == "Skin\\flat" and panel.backdrop.edgeFile == Style.flat.edgeFile,
        "a flat panel takes the skin's background and keeps the 1px edge")
end)
skin({slot = {path = "Skin\\slot"}, tab = {path = "Skin\\tab"}, ["tab-active"] = {path = "Skin\\tabOn"},
      box = {path = "Skin\\box"}, ["box-active"] = {path = "Skin\\boxOn"}}, function()
    local faced = U.slot(window, 40)
    assert(faced.dcFace and faced.dcFace.texture == "Skin\\slot" and faced.dcFace.drawLayer == "BACKGROUND",
        "a slot's image is a face on the BACKGROUND layer, over the flat backdrop and under the icon")
    local tab = U.tab(window, 32)
    assert(tab.dcFace.texture == "Skin\\tab", "an idle tab")
    U.tabActive(tab, true)
    assert(tab.dcFace.texture == "Skin\\tabOn", "the tab on show")
    U.tabActive(tab, false)
    assert(tab.dcFace.texture == "Skin\\tab", "and back")
    local framed = U.box(window, 96)
    U.boxActive(framed, true)
    assert(framed.dcFace.texture == "Skin\\boxOn", "the box holding an item")
    U.boxActive(framed, false)
    assert(framed.dcFace.texture == "Skin\\box", "and empty")
end)
skin({["row-select"] = {path = "Skin\\mark"}, ["row-hilite"] = {path = "Skin\\hover"},
      ["bar-bg"] = {path = "Skin\\barBack"}, ["bar-fill"] = {path = "Skin\\barFill"}}, function()
    local line = U.row(window)
    assert(line.mark.texture == "Skin\\mark" and line:GetHighlightTexture().texture == "Skin\\hover",
        "a row's selection mark and hover")
    local bar = U.bar(window)
    assert(bar.bg.texture == "Skin\\barBack" and bar.fill.texture == "Skin\\barFill", "the cast bar's ground and fill")
end)
skin({["window-title"] = {colour = {.5, .4, .3}, path = "Skin\\plate", width = 200, height = 40}}, function()
    local frame = U.window("SkinTestWindow3")
    local text = U.title(frame, "Cube")
    same(text.textColor, {.5, .4, .3}, "the title's colour")
    assert(frame.dcTitlePlate.texture == "Skin\\plate" and frame.dcTitlePlate:GetWidth() == 200
        and frame.dcTitlePlate:GetHeight() == 40, "and its plate, at the slot's size")
end)
skin({button = {path = "Skin\\up"}, ["button-hover"] = {path = "Skin\\hover"}}, function()
    local native = U.button(window, 100, "Go")
    assert(native:GetNormalTexture().texture == "Skin\\up" and native:GetHighlightTexture().texture == "Skin\\hover",
        "the native button's normal and hover states")
    assert(native:GetPushedTexture() == nil, "a state the skin left empty stays stock")
end)
skin({button = {path = "Skin\\frame", coords = {0, 1, 0, .5}, slices = {left = .1, right = .2}},
      ["button-pressed"] = {path = "Skin\\down", slices = {left = .1, right = .2}}}, function()
    local native = U.button(window, 100, "Go")
    local left, middle, right = native.dcSlices[1], native.dcSlices[2], native.dcSlices[3]
    assert(left.texture == "Skin\\frame" and middle.texture == "Skin\\frame" and right.texture == "Skin\\frame",
        "a sliced button is three pieces of its frame")
    same(left.texCoord, {0, .1, 0, .5}, "the left cap at its own crop")
    same(middle.texCoord, {.1, .8, 0, .5}, "the middle between the caps")
    same(right.texCoord, {.8, 1, 0, .5}, "the right cap")
    assert(math.abs(left:GetWidth() - 10) < 1e-9 and math.abs(right:GetWidth() - 20) < 1e-9,
        "the caps keep their share of the width")
    native.scripts.OnMouseDown(native)
    assert(left.texture == "Skin\\down", "pressed, the pieces are the pressed slot's")
    native.scripts.OnMouseUp(native)
    assert(left.texture == "Skin\\frame", "and back up")
end)
skin({["window-close"] = {path = "Skin\\x"}}, function()
    local close = U.close(window)
    assert(close.template == "UIPanelCloseButton" and close:GetNormalTexture().texture == "Skin\\x",
        "the close button, in its stock place")
end)
skin({input = {path = "Skin\\input"}}, function()
    local box = U.input(window, "SkinTestInput")
    local stock = box:CreateTexture(nil, "BACKGROUND")
    Style.Input(box)
    assert(box.dcInput.texture == "Skin\\input" and box.dcInput.shown ~= false, "the input's image")
    assert(stock.shown == false, "and the template's own border pieces hidden")
end)
skin({["scroll-thumb"] = {path = "Skin\\knob"}, ["scroll-track"] = {path = "Skin\\track"}}, function()
    local scroll = CreateFrame("ScrollFrame", "SkinTestScroll", window, "UIPanelScrollFrameTemplate")
    local bar = CreateFrame("Slider", "SkinTestScrollScrollBar", scroll)
    bar:SetThumbTexture(bar:CreateTexture(nil, "OVERLAY"))
    assert(U.scroll(scroll) == scroll, "U.scroll hands the frame back")
    assert(bar:GetThumbTexture().texture == "Skin\\knob" and bar.dcTrack.texture == "Skin\\track",
        "the scroll bar's knob and its track")
end)

-- ------------------------------------------------ (4) painted before the skin, refreshed after
local early = Mock.widget("Frame", nil, Mock.UIParent)
Style.Panel(early)
assert(early.backdrop == Style.backdrop, "built while Torment loads: the stock dialog")
skin({["window-panel"] = {path = "Skin\\late"}}, function()
    DC.RefreshArt()
    assert(early.backdrop.bgFile == "Skin\\late", "after DC.RefreshArt (PLAYER_LOGIN) it wears the skin")
    DC.USE_ART = false
    DC.RefreshArt()
    assert(early.backdrop == Style.backdrop, "art off: the stock dialog again")
    DC.USE_ART = true
end)
skin({slot = {path = "Skin\\slot", colour = {.3, .2, .1}}}, function()
    DC.USE_ART = false
    local faced = U.slot(window, 40)
    same(faced.dcFace.textureColor, {.3, .2, .1}, "art off: a face draws the slot's colour")
    DC.USE_ART = true
end)

-- ------------------------------------------------ (5) DCUI with an addon from before the slots
DC.Style = {backdrop = Style.backdrop, flat = Style.flat}
same(U.TAB_IDLE, U.PALETTE.TAB_IDLE, "an old addon: DCUI's own palette")
local old = U.window("SkinTestWindow4")
assert(old.backdrop == Style.backdrop and U.slot(old, 40).dcFace == nil and U.row(old).mark.texture == U.EDGE,
    "an old addon: the same window, slot and row as before")
DC.Style = Style

-- ------------------------------------------------ (6) whole windows
-- Every window Torment draws has its slot, empty by default.
for _, key in ipairs({"cube", "blacksmith", "jeweler", "mystic", "paragon", "stash", "inventory", "urshi",
                      "greater-rift", "revive", "bug-report", "bounty-map", "tier",
                      -- declared, unread: no Torment window draws these yet
                      "account", "elite", "crafting", "dungeon-finder"}) do
    assert(type(ART["window-" .. key]) == "table" and next(ART["window-" .. key]) == nil, "window-" .. key .. " is an empty slot")
end
local function point(region)
    local p = region.points[1]
    return p[1], p[2], p[3], p[4], p[5]
end
local function near(a, b, label) assert(math.abs(a - b) < 1e-9, label .. ": " .. tostring(a) .. ", want " .. tostring(b)) end
-- A Cube-shaped window as dc_cube.lua makes it: title, close, a tab, its two buttons declared.
local function cube(width)
    local frame = U.window("SkinTestCube" .. width, width, 460, "cube")
    local heading = U.title(frame, "Kanai's Cube")
    local close = U.close(frame)
    local tab = U.tab(frame, 48)
    local go = U.button(frame, 140, "Transmute")
    local book = U.slot(frame, 30)
    U.anchor(frame, "buttons", {go, book})
    return frame, heading, close, tab, go, book
end
do
    local frame, heading, close = cube(300)
    assert(frame.backdrop == Style.backdrop and frame.dcCanvas == nil, "no skin: the Cube is today's dialog, no canvas")
    assert(point(heading) == "TOPLEFT" and point(close) == "TOPRIGHT", "no skin: title and close where the kit put them")
end
local CANVAS = {path = "Skin\\cube", width = 600, height = 800, anchors = {
    content = {left = 150, top = 100, width = 300, height = 460},
    title = {left = 200, top = 20, width = 200, height = 30},
    close = {left = 560, top = 10, width = 30, height = 30},
    tabs = {{left = 0, top = 200, width = 40, height = 40}},
    buttons = {{left = 230, top = 600, width = 140, height = 24}, {left = 400, top = 600, width = 30, height = 30}}}}
skin({["window-cube"] = CANVAS}, function()
    local frame, heading, close, tab, go, book = cube(300)
    assert(frame.backdrop == nil, "a filled window slot hides the generic frame")
    local canvas = frame.dcCanvas
    assert(canvas and canvas.texture == "Skin\\cube" and canvas.drawLayer == "BACKGROUND", "and draws the canvas behind the content")
    local p, rel, relPoint, x, y = point(canvas)
    assert(p == "TOPLEFT" and rel == frame and relPoint == "TOPLEFT" and x == -150 and y == 100,
        "the frame is the canvas's content spot: the canvas starts 150 left and 100 above it")
    near(canvas:GetWidth(), 600, "canvas width at scale 1"); near(canvas:GetHeight(), 800, "canvas height")
    p, rel, relPoint, x, y = point(heading)
    assert(p == "CENTER" and rel == canvas and relPoint == "TOPLEFT" and x == 300 and y == -35, "the title on its anchor")
    near(heading:GetWidth(), 200, "at the anchor's width")
    p, rel, relPoint, x, y = point(close)
    assert(rel == canvas and x == 575 and y == -25 and close:GetWidth() == 30, "the close button on its anchor, at its size")
    p, rel, relPoint, x, y = point(tab)
    assert(rel == canvas and x == 20 and y == -220, "the tab on its spot")
    p, rel, relPoint, x, y = point(go)
    assert(rel == canvas and x == 300 and y == -612 and go:GetWidth() == 140, "the first button on the first spot")
    p, rel, relPoint, x, y = point(book)
    assert(rel == canvas and x == 415 and y == -615, "the second on the second")
    -- A window twice as wide draws the canvas at twice the scale, both axes.
    local wide, wideTitle = cube(600)
    near(wide.dcCanvas:GetWidth(), 1200, "scale 2 width"); near(wide.dcCanvas:GetHeight(), 1600, "scale 2 height")
    p, rel, relPoint, x, y = point(wide.dcCanvas)
    assert(x == -300 and y == 200, "and its content spot at scale 2")
    p, rel, relPoint, x, y = point(wideTitle)
    assert(x == 600 and y == -70, "the title's spot at scale 2")
end)
skin({["window-cube"] = {path = "Skin\\cube", anchors = CANVAS.anchors}}, function()
    assert(cube(300).dcCanvas == nil, "a canvas with no size is not drawn")
end)
-- Built before the skin loaded: DC.RefreshArt draws the canvas, after the panel paint.
do
    local frame = cube(300)
    skin({["window-cube"] = CANVAS}, function()
        DC.RefreshArt()
        assert(frame.dcCanvas and frame.dcCanvas.texture == "Skin\\cube" and frame.backdrop == nil,
            "a window built before the skin wears it after DC.RefreshArt, its backdrop hidden")
    end)
end
skin({["window-cube"] = CANVAS}, function()
    DC.USE_ART = false
    local frame = cube(300)
    assert(frame.dcCanvas == nil and frame.backdrop == Style.backdrop, "art off: no canvas, the generic frame")
    DC.USE_ART = true
end)
-- A window the kit makes with no slot key is never a whole-window skin.
skin({["window-cube"] = CANVAS}, function()
    local plain = U.window("SkinTestPlain", 300, 460)
    U.title(plain, "Plain")
    assert(plain.dcCanvas == nil and plain.backdrop == Style.backdrop, "no key, no canvas")
end)
-- An addon from before the whole-window slots: the kit's declarations draw nothing and break nothing.
DC.Style = {backdrop = Style.backdrop, flat = Style.flat}
local older = U.window("SkinTestOlder", 300, 460, "cube")
U.anchor(older, "buttons", {U.button(older, 100, "Go")})
assert(older.dcCanvas == nil and older.backdrop == Style.backdrop, "an old addon: the window as before")
DC.Style = Style

-- ------------------------------------------------ (7) the guide
-- SKINNING.md's "Windows" section names every window slot Torment declares, says how each is drawn,
-- points at the worked example, and stays neutral: a skin addon, the player's own pictures;
-- no game, company or art source is named.
local guide = io.open("client-patch/addons/Torment/SKINNING.md"):read("*a")
local windows = assert(guide:match("\n## Windows\n(.-)\n## What a skin cannot change"), "SKINNING.md has a Windows section")
for _, name in ipairs(PARTS) do
    assert(windows:find("`" .. name .. "`", 1, true), "the Windows section names the part " .. name)
end
for name in pairs(ART) do
    if name:match("^window%-") then
        assert(windows:find("`" .. name .. "`", 1, true), "the Windows section names the slot " .. name)
    end
end
for _, word in ipairs({"edgePath", "edgeSize", "insets", "anchors.content", "slices", "RefreshArt", "/reload"}) do
    assert(windows:find(word, 1, true), "the Windows section explains " .. word)
end
assert(windows:find("eight equal squares", 1, true), "and the edge-strip rule")
assert(windows:find("client-patch/skins/WindowSkinExample/", 1, true)
    and io.open("client-patch/skins/WindowSkinExample/WindowSkinExample.lua"), "the worked example it names exists")
-- Whole words only: the addon's own Diablocraft table is not a game's name.
for _, word in ipairs({"d3", "diablo", "blizzard"}) do
    assert(not windows:lower():find("%f[%w]" .. word .. "%f[%W]"), "the Windows section names no game or company: " .. word)
end

print("test_window_skin: the window parts and whole windows are slots; no skin is today's look, a skin reaches each part and window; the guide names them all")
