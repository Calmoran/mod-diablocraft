-- luacheck: ignore 111 112 113 121 122 211 212 213 431 432
-- Run from repo root with `lua mod-diablocraft/scripts/tests/items/test_stash_look.lua`.
--
-- diablocraft-stash-look (ruling 2026-10-03): the stash window wears the shared Torment look, the
-- one the Jeweler and the Blacksmith draw, from the same pieces so it cannot drift:
--
--   * the palette the addon draws the stash with (DC.Style.palette) is dc_aio_ui.lua's DCUI
--     palette value for value, and its rarity colours are dc_tooltip.lua's DCRARITY;
--   * the panel is the shared dialog backdrop; no stock dialog template anywhere;
--   * the large centred gold title and the grey subtitle under it (the tab on show);
--   * the slots are DCUI slots - the flat 1px backdrop, SLOT_BG ground, SLOT_BORDER edge -
--     with an item's rarity as a 2 px border on OVERLAY, as the Blacksmith draws it, and the
--     last row's closing bottom edge drawn explicitly (the designer, q-1004-26);
--   * the tabs are DCUI tabs: TAB_ACTIVE on the tab on show, TAB_IDLE on the others;
--   * the gold line is "Your gold: N" in the gold font, the status line grey or the palette's
--     red for a refusal, and no materials row (ruling 2026-10-04, q-1004-04: the stash shows
--     no materials at the bottom);
--   * no Torment art texture is drawn on the stash, and nothing white: no flat backdrop left
--     uncoloured, no WHITE8X8 or colour texture left at opaque white;
--   * opened beside ElvUI's bags, the stash's right edge touches the bag frame's left edge, no
--     overlap (PM ruling A, 2026-10-03); with no ElvUI bag frame up it keeps its old spot.
--
-- Driven on the real core files and the real Stash.xml's font strings, with a stub 3.3.5a
-- API. What the stash SENDS is test_stash_client.lua's and test_item_dragging.lua's; this is the
-- look. A stub cannot prove what the client renders, only what the addon asks it to draw.

local EDGE = "Interface\\Buttons\\WHITE8X8"

-- ------------------------------------------------------- the shared palette

-- dc_aio_ui.lua is the AIO half: it runs on the client only (AddAddon false) and defines DCUI.
_G.AIO = {AddAddon = function() return false end}
dofile("mod-diablocraft/lua/aio/dc_aio_ui.lua")
local U = _G.DCUI
assert(U and U.SLOT_BG, "dc_aio_ui.lua defines the DCUI palette")
_G.DCUI = nil

-- dc_tooltip.lua's rarity palette, read from the file: it is "the one copy on the client".
local tooltip = io.open("mod-diablocraft/lua/aio/dc_tooltip.lua"):read("*a")
local rarityLine = tooltip:match("local colours=(%b{})%s*\n[^\n]*\n[^\n]*\n[^\n]*\nDCRARITY=colours")
assert(rarityLine, "dc_tooltip.lua's DCRARITY table is where this test reads it")
local DCRARITY = assert(load("return " .. rarityLine))()

-- ---------------------------------------------------------------- stub client

-- The 3.3.5a widget layer is the ONE shared strict mock (diablocraft-yey2).
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)

-- Stash.xml's three button templates: what the client builds from a virtual template before
-- the addon's OnLoad runs. The shared mock models the widget API, not the XML templates, so
-- this test's template layer sits on top of Mock.widget: the template's own size, its named
-- child regions on their XML layers, its HighlightTexture, and the template OnLoad the client
-- runs as the frame is made.
local TEMPLATES = {
    DiablocraftSlotTemplate = {size = {34, 34}, onLoad = "Slot_OnLoad", parts = {
        {"Back", "BACKGROUND"}, {"Rarity", "BORDER"}, {"Icon", "ARTWORK"},
        {"Count", "OVERLAY", "NumberFontNormalSmall", "FontString"},
        {"Select", "OVERLAY", nil, "Texture", true},  -- hidden="true" in the XML
    }},
    DiablocraftTabTemplate = {size = {40, 40}, onLoad = "Tab_OnLoad", parts = {
        {"Back", "BACKGROUND"}, {"Label", "OVERLAY", "GameFontNormal", "FontString"},
    }},
    DiablocraftButtonTemplate = {size = {170, 62}, onLoad = "Button_OnLoad", parts = {
        {"Back", "BACKGROUND"}, {"Label", "OVERLAY", "GameFontNormal", "FontString"},
    }},
}
local baseWidget = Mock.widget
function Mock.widget(kind, name, parent, template)
    local widget = baseWidget(kind, name, parent, template)
    local spec = TEMPLATES[template or ""]
    if spec then
        widget:SetSize(spec.size[1], spec.size[2])
        for _, entry in ipairs(spec.parts) do
            local region
            if entry[4] == "FontString" then
                region = widget:CreateFontString(name .. entry[1], entry[2], entry[3])
            else
                region = widget:CreateTexture(name .. entry[1], entry[2])
            end
            if entry[5] then region:Hide() end
        end
        widget:SetHighlightTexture(widget:CreateTexture(name .. "Highlight", "HIGHLIGHT"), "ADD")
        local onLoad = _G.Diablocraft and _G.Diablocraft[spec.onLoad]
        if onLoad then onLoad(widget) end
    end
    return widget
end

_G.GetItemIcon = function(entry) return "icon" .. entry end
_G.DEFAULT_CHAT_FRAME = {AddMessage = function() end}
_G.GetCursorPosition = function() return -999, -999 end
_G.IsModifiedClick = function() return false end
local handlers = {}
_G.AIO = {AddHandlers = function() return handlers end, Handle = function() end}
_G.Diablocraft = {Econ = {
    MATERIALS = {{entry = 102000, name = "Death's Breath"}},
    Gold = function(value)
        local out, n = tostring(value or "0"), 1
        while n > 0 do out, n = out:gsub("^(%d+)(%d%d%d)", "%1,%2") end
        return out
    end,
    Balance = function() return "1234567" end,
    Material = function() return "7" end,
    OnChange = function() end,
}}
_G.require = nil
-- Stash.lua hooks these two stock cursor calls: the
-- client has them as functions and the mock refuses to hook a name that is not one.
_G.PickupContainerItem = function() end
_G.PickupInventoryItem = function() end

dofile("mod-diablocraft/scripts/dc_addon_core.lua")
local DC = _G.Diablocraft

-- The stash frame's own font strings and textures, as Stash.xml declares them: name, layer,
-- font and anchor, read from the real file so the test cannot drift from it.
local xml = io.open("client-patch/addons/Torment/Stash.xml"):read("*a")
local frameXml = assert(xml:match('<Frame name="DiablocraftStashFrame".-</Frame>'), "Stash.xml declares the frame")
local frame = Mock.widget("Frame", "DiablocraftStashFrame", Mock.UIParent)
frame:Hide()  -- the XML's own hidden="true"
local declared = {}
for layer, body in frameXml:gmatch('<Layer level="(%u+)">(.-)</Layer>') do
    for tag, attrs in body:gmatch("<(%a+) (name=[^>]*)>") do
        local suffix = attrs:match('name="%$parent(%w+)"')
        if suffix and (tag == "FontString" or tag == "Texture") then
            local font = attrs:match('inherits="([%w_]+)"')
            local object = tag == "FontString"
                and frame:CreateFontString("DiablocraftStashFrame" .. suffix, layer, font)
                or frame:CreateTexture("DiablocraftStashFrame" .. suffix, layer)
            object.text = attrs:match('text="([^"]*)"')
            declared[suffix] = object
        end
    end
end
DC.Frame_OnLoad(frame)

local function item(entry, guid, colour)
    return {entry = entry, count = 1, colour = colour, guid = guid, name = "Item " .. entry, link = "|Hitem:" .. entry .. "|h"}
end
-- ElvUI's bag frame, which opening the stash opens. It starts hidden, as the real one does.
local bagFrame = Mock.widget("Frame", "ElvUI_ContainerFrame", Mock.UIParent)
bagFrame._rect = {600, 700, 0, 0}
bagFrame:Hide()
_G.OpenAllBags = function() bagFrame:Show() end
_G.CloseAllBags = function() bagFrame:Hide() end
handlers.Snapshot(nil, {
    note = "open", revision = "1", gold = "1234567",
    tabs = {granted = 2, max = 5, prices = {}},
    layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10},
    stash = {[0] = item(1000, 100, "orange"), [1] = item(1001, 101, "grey"), [2] = item(1002, 102, "blue")},
})
assert(frame:IsShown(), "the snapshot opens the window")
local anchor = {frame:GetPoint(1)}
assert(anchor[1] == "RIGHT" and anchor[2] == bagFrame and anchor[3] == "LEFT" and anchor[4] == 0 and anchor[5] == 0,
    "the stash's right edge touches the open bag frame's left edge, no overlap")

local function same(a, b, label)
    assert(type(a) == "table" and type(b) == "table", label .. ": missing")
    assert(#a == #b, label .. ": " .. #a .. " values against " .. #b)
    for index = 1, #b do
        assert(math.abs(a[index] - b[index]) < 1e-9, label .. ": value " .. index .. " is " .. tostring(a[index])
            .. ", the shared one is " .. tostring(b[index]))
    end
end
local function rgb(colour, want, label)
    assert(colour, label .. ": no colour set")
    for index = 1, 3 do
        assert(math.abs(colour[index] - want[index]) < 1e-9, label .. ": " .. table.concat(colour, ",")
            .. " against " .. table.concat(want, ","))
    end
end
-- A frame the stash window owns, judged by its parent chain, so a property of some other
-- window's frame cannot answer for the stash.
local function owned_by_frame(object)
    local owner = object.parent
    while owner do
        if owner == frame then return true end
        owner = owner.parent
    end
    return false
end

-- (1) One palette: the addon's copy is dc_aio_ui.lua's, value for value.
local P = DC.Style and DC.Style.palette
assert(P, "DC.Style carries the shared palette")
-- DCUI's window-part colours resolve through DC.Style.Colour once the addon is loaded (window skin
-- slots W1), so the pin is against DCUI's own defaults, U.PALETTE; its text colours stay plain.
for _, key in ipairs({"SLOT_BG", "SLOT_BORDER", "TAB_ACTIVE", "TAB_IDLE", "BOX_BORDER", "ROW_SELECT",
                      "ROW_HILITE", "DETAIL_BG", "DETAIL_BORDER", "BOX_ACTIVE", "BAR_BG", "BAR_FILL",
                      "BAR_BORDER"}) do
    same(P[key], U.PALETTE[key], "palette " .. key)
    same(DC.Style.Colour(key), U.PALETTE[key], "with no skin the window part's colour is the palette's: " .. key)
end
for _, key in ipairs({"GOLD", "GREY", "RED"}) do
    same(P[key], U[key], "palette " .. key)
end
for _, rarity in ipairs({"magic", "rare", "legendary", "set"}) do
    same(P.RARITY[rarity], DCRARITY[rarity], "rarity " .. rarity)
end

-- (2) The panel: the shared dialog backdrop, and no stock dialog template anywhere.
assert(frame.backdrop == DC.Style.backdrop, "the stash wears the shared dialog backdrop")
assert(not xml:find("DialogTemplate", 1, true) and not xml:find("BasicFrameTemplate", 1, true),
    "Stash.xml inherits no stock dialog template")
for _, created in ipairs(frames) do
    local t = created.template or ""
    assert(not t:find("DialogTemplate", 1, true) and not t:find("BasicFrame", 1, true),
        "no stock dialog template is built: " .. t)
end

-- (3) Title and subtitle: the large gold title centred at the top, the grey subtitle under it
-- naming the tab on show, as U.title and U.subtitle draw them.
assert(declared.Title and declared.Title.template == "GameFontNormalLarge", "the title is the large gold font")
assert(_G.DiablocraftStashFrameTitle.text == "Stash", "and reads Stash")
local subtitle = DC.StashLook and DC.StashLook.subtitle
assert(subtitle, "the stash has a subtitle line")
assert(subtitle.template == "GameFontHighlightSmall", "in U.subtitle's font, got " .. tostring(subtitle.template))
rgb(subtitle.textColor, U.GREY, "the subtitle is the palette's grey")
assert(subtitle.justify == "CENTER", "centred")
assert(subtitle.text == "TAB 1", "and names the tab on show, got " .. tostring(subtitle.text))

-- (4) Slots: DCUI slots, and no Torment art behind them.
local slot = function(position) return _G["DiablocraftStashSlot" .. position] end
for position = 1, 70 do
    local button = slot(position)
    assert(button.backdrop == DC.Style.flat, "slot " .. position .. " wears the flat 1px backdrop")
    same(button.backdropColor, {U.SLOT_BG[1], U.SLOT_BG[2], U.SLOT_BG[3], .85}, "slot " .. position .. " ground")
    same(button.borderColor, {U.SLOT_BORDER[1], U.SLOT_BORDER[2], U.SLOT_BORDER[3], 1}, "slot " .. position .. " border")
end
-- An item's rarity is a 2 px border on OVERLAY in the D3 rarity colour; a normal (grey) item
-- keeps the slot's own bronze edge.
local function rarityEdges(button)
    local shown = {}
    for _, side in ipairs({"top", "bottom", "left", "right"}) do
        local edge = button.rarityEdge and button.rarityEdge[side]
        if edge and edge.shown then shown[#shown + 1] = edge end
    end
    return shown
end
local legendary = rarityEdges(slot(1))
assert(#legendary == 4, "a legendary item draws its rarity border on all four sides")
for _, edge in ipairs(legendary) do
    assert(edge.drawLayer == "OVERLAY", "on OVERLAY, above the icon")
    same(edge.textureColor, {DCRARITY.legendary[1], DCRARITY.legendary[2], DCRARITY.legendary[3], 1}, "legendary edge")
    assert(edge:GetWidth() == 2 or edge:GetHeight() == 2, "2 px")
end
assert(#rarityEdges(slot(2)) == 0, "a normal item keeps the bronze slot edge")
assert(#rarityEdges(slot(3)) == 4 and rarityEdges(slot(3))[1].textureColor[3] == DCRARITY.magic[3], "a magic item is blue")
assert(#rarityEdges(slot(4)) == 0, "an empty slot has no rarity border")
-- Moving off tab 1 clears the borders it drew.
DC.Tab_OnClick(_G.DiablocraftStashTab2)
assert(#rarityEdges(slot(1)) == 0, "a rarity border does not outlive its item")
assert(subtitle.text == "TAB 2", "the subtitle follows the tab")

-- (4b) The grid's last row is closed by its own bottom edge (the designer, q-1004-26, his screenshot:
-- "the slots in the LAST ROW have no bottom border line, so the grid looks open at the
-- bottom; every other row is closed by the row below it"). The closing line is an explicit
-- OVERLAY texture on the slot's own bottom corners, 1 px, the slot's bronze.
local function closingEdge(button)
    local edge = button.closingEdge
    return edge and edge.shown ~= false and edge or nil
end
for position = 61, 70 do
    local edge = closingEdge(slot(position))
    assert(edge, "the last row's slot " .. position .. " draws its closing bottom edge")
    assert(edge.drawLayer == "OVERLAY", "slot " .. position .. " closing edge is on OVERLAY, got "
        .. tostring(edge.drawLayer))
    same(edge.textureColor, {U.SLOT_BORDER[1], U.SLOT_BORDER[2], U.SLOT_BORDER[3], 1},
        "slot " .. position .. " closing edge is the slot bronze")
    assert(edge:GetHeight() == 1 and edge:GetWidth() == 0, "slot " .. position .. " closing edge is 1 px, got "
        .. tostring(edge:GetWidth()) .. "x" .. tostring(edge:GetHeight()))
    assert(#(edge.points or {}) == 2 and edge.points[1][1] == "BOTTOMLEFT" and edge.points[2][1] == "BOTTOMRIGHT",
        "slot " .. position .. " closing edge is anchored across its own bottom edge")
end
for _, position in ipairs({1, 10, 11, 60}) do
    assert(not closingEdge(slot(position)),
        "slot " .. position .. " needs no closing edge: the row below it closes it")
end

-- (5) Tabs: DCUI tabs, the active edge on the tab on show.
for index = 1, 5 do
    local button = _G["DiablocraftStashTab" .. index]
    assert(button.backdrop == DC.Style.flat, "tab " .. index .. " wears the flat backdrop")
    same(button.backdropColor, {U.SLOT_BG[1], U.SLOT_BG[2], U.SLOT_BG[3], .85}, "tab " .. index .. " ground")
    local want = index == 2 and U.TAB_ACTIVE or U.TAB_IDLE
    same(button.borderColor, {want[1], want[2], want[3], 1}, "tab " .. index .. " edge")
end
-- The active tab's square, drawn in full and thicker (the designer, q-1003-29): tab 1 showed only a
-- thin line with the top side missing, because the 1 px flat backdrop edge is cut off at the
-- top. The whole square is drawn as four OVERLAY edges, 3 px, the Blacksmith's rarity-border way.
local function tabSquare(button)
    local shown = {}
    for _, side in ipairs({"top", "bottom", "left", "right"}) do
        local edge = button.tabSquare and button.tabSquare[side]
        if edge and edge.shown then shown[#shown + 1] = edge end
    end
    return shown
end
local square = tabSquare(_G.DiablocraftStashTab2)
assert(#square == 4, "the active tab's square is drawn on all four sides, got " .. #square)
for _, edge in ipairs(square) do
    assert(edge.drawLayer == "OVERLAY", "the square draws above the ground, got " .. tostring(edge.drawLayer))
    same(edge.textureColor, {P.TAB_ACTIVE[1], P.TAB_ACTIVE[2], P.TAB_ACTIVE[3], 1}, "the active square wears TAB_ACTIVE")
    assert(edge:GetWidth() == 3 or edge:GetHeight() == 3, "the square is 3 px thick, got "
        .. tostring(edge:GetWidth()) .. "x" .. tostring(edge:GetHeight()))
end
assert(#tabSquare(_G.DiablocraftStashTab1) == 0, "an idle tab draws no thick square")
-- It follows the tab on show.
DC.Tab_OnClick(_G.DiablocraftStashTab1)
assert(#tabSquare(_G.DiablocraftStashTab1) == 4 and #tabSquare(_G.DiablocraftStashTab2) == 0,
    "the square follows the tab on show")
DC.Tab_OnClick(_G.DiablocraftStashTab2)
rgb(_G.DiablocraftStashTab2Label.textColor, U.GOLD, "an open tab's number is gold")
rgb(_G.DiablocraftStashTab3Label.textColor, U.GREY, "a locked tab's number is grey")
DC.Tab_OnClick(_G.DiablocraftStashTab1)

-- (6) The gold line, the status line, and no materials row (the designer, q-1004-04).
assert(declared.Gold and declared.Gold.template == "GameFontNormal", "the gold line is the Jeweler's gold font")
assert(_G.DiablocraftStashFrameGold.text == "Your gold: 1,234,567", "and reads like the Jeweler's: "
    .. tostring(_G.DiablocraftStashFrameGold.text))
assert(not declared.Coin, "no Torment coin art beside it")
DC.Tab_OnClick(_G.DiablocraftStashTab4)
rgb(_G.DiablocraftStashFrameStatus.textColor, U.RED, "a refusal is the palette's red")
DC.Tab_OnClick(_G.DiablocraftStashTab1)
handlers.Snapshot(nil, {revision = "2", gold = "1", tabs = {granted = 2, max = 5, prices = {}},
    materials = {[102000] = "7"}, layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10}, stash = {}})
assert(DC.StashLook.materials == nil, "the stash publishes no materials line")
-- A snapshot that carries materials draws none of them: the row is gone from the window.
for _, f in ipairs(frames) do
    if f.kind == "FontString" and owned_by_frame(f) then
        local text = tostring(f.text or "")
        assert(not (text:find("Reusable Parts", 1, true) or text:find("Death's Breath", 1, true)),
            "no materials line is drawn on the stash, got: " .. text)
    end
end

-- (7) No Torment art and nothing white.
for _, t in ipairs(frames) do
    if t.kind == "Texture" and owned_by_frame(t) and t.shown ~= false then
        local value = t.texture
        assert(not (type(value) == "string" and value:find(DC.ART_PATH, 1, true)),
            "no Torment art texture on the stash: " .. tostring(value))
        if value == EDGE then
            assert(t.vertexColor and not (t.vertexColor[1] == 1 and t.vertexColor[2] == 1 and t.vertexColor[3] == 1 and t.vertexColor[4] > .5),
                "a WHITE8X8 texture is tinted, never left white")
        elseif t.textureColor then
            local c = t.textureColor
            assert(not (c[1] == 1 and c[2] == 1 and c[3] == 1 and c[4] > .5), "no opaque white colour texture")
        end
    end
end
for _, created in ipairs(frames) do
    if created.backdrop == DC.Style.flat then
        assert(created.backdropColor and created.borderColor, "every flat backdrop is coloured: " .. tostring(created.name))
    end
end

-- With no ElvUI bag frame up (stock bags) the stash keeps its old spot against the screen edge.
frame:Hide()
_G.ElvUI_ContainerFrame = nil
_G.OpenAllBags = function() end
handlers.Snapshot(nil, {note = "open", revision = "3", gold = "1", tabs = {granted = 2, max = 5, prices = {}},
    layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10}, stash = {}})
local fallback = {frame:GetPoint(1)}
assert(fallback[2] == _G.UIParent and fallback[1] == "RIGHT" and fallback[4] < 0,
    "with no ElvUI bag frame the stash sits where it did")

print("test_stash_look: the stash wears the shared Torment look (palette, panel, title, slots, tabs, lines, no art, no white)")
