-- luacheck: ignore 111 112 113 121 122 431
-- diablocraft-paragon-look: the Paragon window wears the artisans' shared look, and its
-- Primary stat row names the class's own main stat.
--
-- The window is built from the same pieces as the Jeweler, the Blacksmith and the Skills
-- window: dc_aio_ui.lua's DCUI (the window, title, subtitle, buttons, list row, bar, text,
-- colour, message) and the Torment addon's Diablocraft.Style through it. This test loads the
-- Jeweler and the Paragon window against one 3.3.5a frame API double and compares every
-- shared visual property field by field - the backdrop, the title and subtitle, the buttons,
-- the XP bar - and pins the pieces the Paragon window has and the artisans' do not (the text
-- tabs, the two-line stat row) to the same palette. It also fails if any frame of the window
-- is built from UIPanelDialogTemplate (today's module) or if a flat backdrop is left without
-- a colour (the white-box bug).
--
-- The row name: the server half reads class_map.csv's primary_stat for the player's class and
-- pushes it; the window's "primary" row shows it. The test drives the push and the complete
-- snapshot directly, so Barbarian (Strength) and Wizard (Intelligence) name the row, and a
-- class with no primary_stat keeps the server's generic name.
local UI_SOURCE = os.getenv("DC_UI_LUA") or "mod-diablocraft/lua/aio/dc_aio_ui.lua"
local JEWELER_SOURCE = os.getenv("DC_JEWELER_LUA") or "mod-diablocraft/lua/aio/dc_jeweler.lua"
local PARAGON_SOURCE = os.getenv("DC_PARAGON_LUA") or "mod-diablocraft/lua/aio/dc_paragon.lua"

----------------------------------------------------------------------------------------------------
-- The stub client
----------------------------------------------------------------------------------------------------

local sent, aio = {}, {}

----------------------------------------------------------------------------------------------------
-- The 3.3.5a widget layer is ONE shared strict mock (diablocraft-yey2): unknown
-- methods, wrong argument counts, a public size field and a texture-less bar all
-- fail here as they do in the game. The doubles below the mock are this test's
-- own client globals.
----------------------------------------------------------------------------------------------------
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)
StaticPopup_Show = function(name) return {name = name, data = nil} end
StaticPopup_Hide = function() end
SlashCmdList = {}
function UnitName() return "Tester" end
function GetRealmName() return "Diablocraft" end
function GetTime() return 0 end
function GetUnitSpeed() return 0 end
function UnitAffectingCombat() return false end
function InCombatLockdown() return false end
function UnitIsDeadOrGhost() return false end
function GetItemIcon(entry) return "icon:" .. tostring(entry) end
function GetItemInfo() return nil end
function GetCursorInfo() return nil end
function ClearCursor() end
function GetCursorPosition() return 0, 0 end
function IsMouseButtonDown() return false end
function GetMouseFocus() return nil end
function GetContainerNumSlots() return 0 end
function GetContainerNumFreeSlots() return 0 end
function GetContainerItemLink() return nil end
function GetInventoryItemLink() return nil end
function GetContainerNumFreeSlots() return 0 end
function IsShiftKeyDown() return false end
function IsControlKeyDown() return false end
function IsAltKeyDown() return false end
function PickupContainerItem() end
function PickupInventoryItem() end
function SocketContainerItem() end
function SocketInventoryItem() end
ItemSocketingFrame = Mock.widget("Frame", "ItemSocketingFrame")
function HideUIPanel() end
local hooked = {}
function hooksecurefunc(name, fn, tableFn)
    local owner = _G
    if type(name) == "table" then owner, name, fn = name, fn, tableFn end
    if type(owner[name]) == "function" then
        local original = owner[name]
        owner[name] = function(...) local r = {original(...)}; fn(...); return unpack(r) end
        hooked[name] = (hooked[name] or 0) + 1
    end
end
function SendAddonMessage(prefix, body, distribution, target)
    sent[#sent + 1] = {prefix = prefix, body = body, distribution = distribution, target = target}
end
NUM_CONTAINER_FRAMES, MAX_CONTAINER_ITEMS = 13, 36
-- The real formatter, doubled faithfully: groups in threes, so 100002 reads "100,002" in a
-- count. Both windows call Diablocraft.Econ.Gold for the material line when the addon is present.
-- Torment/Economy.lua digits() refuses any string holding a non-digit as "0", so the mock must
-- refuse the same way: a balance formatted twice ("100,002") the client really shows as "0"
-- would otherwise pass (diablocraft-materials-count regression, dc_jeweler.lua).
local function group(v)
    local s = tostring(v or "")
    if s == "" or s:find("%D") then return "0" end
    s = s:gsub("^0+(%d)", "%1")
    local n = 1
    while n > 0 do s, n = s:gsub("^(%d+)(%d%d%d)", "%1,%2") end
    return s
end
Diablocraft = {Econ = {Gold = group, OnChange = function() end,
    MATERIALS = {}}, ClaimRightClick = function() end}
local handlersByChannel = {}
AIO = {
    AddAddon = function() return false end,
    AddHandlers = function(channel, table_) handlersByChannel[channel] = table_; return table_ end,
    Handle = function(...) aio[#aio + 1] = {...} end,
}

----------------------------------------------------------------------------------------------------
-- Load the shared look, the Jeweler and the Paragon window
----------------------------------------------------------------------------------------------------
dofile(UI_SOURCE)
dofile(JEWELER_SOURCE)
dofile(PARAGON_SOURCE)
assert(DCUI and DCJeweler and DCJeweler.ui and DCParagon and DCParagon.ui,
    "the shared look module, the Jeweler and the Paragon window must all load")
local U, P, J = DCUI, DCParagon.ui, DCJeweler.ui

local function dump(value)
    if type(value) ~= "table" then return tostring(value) end
    local keys = {}
    for key in pairs(value) do keys[#keys + 1] = key end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    local out = {}
    for _, key in ipairs(keys) do out[#out + 1] = tostring(key) .. "=" .. dump(value[key]) end
    return "{" .. table.concat(out, ",") .. "}"
end
local function backdropFields(backdrop)
    if not backdrop then return nil end
    return {bgFile = backdrop.bgFile, edgeFile = backdrop.edgeFile, tile = backdrop.tile,
        tileSize = backdrop.tileSize, edgeSize = backdrop.edgeSize, insets = backdrop.insets}
end
local function same(what, a, b)
    assert(dump(a) == dump(b), what .. ":\n  Paragon " .. dump(a) .. "\n  Jeweler " .. dump(b))
end
-- A frame the window owns, judged by its parent chain, so a property of some other window's
-- frame (the Jeweler's, loaded in the same stub) cannot answer for the Paragon window.
local function inWindow(f, root)
    local node = f
    while node do
        if node == root then return true end
        node = node.parent
    end
    return false
end

----------------------------------------------------------------------------------------------------
-- A complete Paragon snapshot, then the class's own stat from the server half
----------------------------------------------------------------------------------------------------
local receiver
for _, f in ipairs(frames) do if f.events and f.events.CHAT_MSG_ADDON then receiver = f end end
assert(receiver, "the Paragon snapshot receiver is registered")
local GENERIC = "Primary stat (Strength/Dexterity/Intelligence by class)"
local function send(message)
    receiver.scripts.OnEvent(receiver, "CHAT_MSG_ADDON", "DCPARAGON", message, "WHISPER", "Tester")
end
send("H|normal|800|100|200|1")
for i = 0, 3 do send("C|" .. i .. "|200") end
for i = 1, 16 do
    local key = i == 1 and "primary" or "chc"
    local name = i == 1 and GENERIC or "Critical Hit Chance"
    send("R|" .. i .. "|" .. key .. "|" .. name .. "|" .. math.floor((i - 1) / 4) .. "|50|0.2|10|50|%")
end
send("E")
local primary = function() return P.lines[1].label.text or "" end
local function push(stat) handlersByChannel.DiablocraftParagon.PrimaryStat(nil, stat) end

-- Barbarian: class_map.csv says Strength, the server half pushes it, the row reads it.
push("Strength")
assert(primary():find("Strength", 1, true) == 1, "the Barbarian's Primary stat row reads Strength, got " .. tostring(primary()))
assert(not primary():find("Primary stat", 1, true), "the generic name is replaced when the class stat is known")
-- Wizard: Intelligence.
push("Intelligence")
assert(primary():find("Intelligence", 1, true) == 1, "the Wizard's Primary stat row reads Intelligence, got " .. tostring(primary()))
-- A class with no primary_stat keeps today's name for that class.
push("")
assert(primary():find(GENERIC, 1, true) == 1, "a class with no primary_stat keeps today's name, got " .. tostring(primary()))
-- The other rows keep their own names whatever the class stat is.
assert((P.lines[2].label.text or ""):find("Critical Hit Chance", 1, true) == 1, "the non-primary rows keep their names")

----------------------------------------------------------------------------------------------------
-- The look: the artisans' shared pieces, no stock dialog-template chrome, no white box
----------------------------------------------------------------------------------------------------
assert(P.frame.template ~= "UIPanelDialogTemplate", "the Paragon window is not built from UIPanelDialogTemplate")
for _, f in ipairs(frames) do
    if inWindow(f, P.frame) then
        assert(f.template ~= "UIPanelDialogTemplate", "no Paragon frame carries the stock dialog-template chrome")
    end
end
same("the window backdrop is the Jeweler's", backdropFields(P.frame.backdrop), backdropFields(J.frame.backdrop))
same("the title is the Jeweler's large centred one", {P.title.template, P.title.justify, P.title.points},
    {J.title.template, J.title.justify, J.title.points})
same("the subtitle is the Jeweler's grey one", {P.summary.template, P.summary.justify, P.summary.points, P.summary.textColor},
    {J.sub.template, J.sub.justify, J.sub.points, J.sub.textColor})
same("the XP bar is the Jeweler's shared bar", backdropFields(P.bar.backdrop), backdropFields(J.bar.backdrop))
same("the XP bar's ground is the shared bar's", P.bar.backdropColor, J.bar.backdropColor)
same("the XP bar's border is the shared bar's", P.bar.borderColor, J.bar.borderColor)
same("the XP bar's fill is the shared bar's", P.bar.fill.vertexColor, J.bar.fill.vertexColor)
same("the XP bar keeps the shared bar's size", {P.bar:GetWidth(), P.bar:GetHeight()}, {J.bar:GetWidth(), J.bar:GetHeight()})

-- Every button the window builds is the native UIPanelButtonTemplate button the shared
-- button makes, at the shared 22 px height: the four +/- pairs, Respec and Refresh.
local native = 0
for _, f in ipairs(frames) do
    if inWindow(f, P.frame) and f.template == "UIPanelButtonTemplate" then
        native = native + 1
        assert(f:GetHeight() == 22, "a Paragon button is the native 22 px button, got " .. tostring(f:GetHeight()))
    end
end
assert(native >= 10, "the Paragon window builds all its buttons from the shared native button (found " .. native .. ")")

-- The text tabs (Core/Offense/Defense/Utility) have no counterpart in the artisans' windows,
-- whose tabs are icons; they wear the same palette: the active tab the shared selection gold,
-- an idle tab the shared bronze.
same("the active tab wears the shared selection gold", P.tabs[1].borderColor,
    {U.TAB_ACTIVE[1], U.TAB_ACTIVE[2], U.TAB_ACTIVE[3], 1})
for i = 2, 4 do
    same("an idle tab wears the shared bronze", P.tabs[i].borderColor, {U.TAB_IDLE[1], U.TAB_IDLE[2], U.TAB_IDLE[3], 1})
    same("an idle tab's label is the shared grey", P.tabs[i].label.textColor, {U.GREY[1], U.GREY[2], U.GREY[3]})
end
same("the active tab's label is the shared gold", P.tabs[1].label.textColor, {U.GOLD[1], U.GOLD[2], U.GOLD[3]})
same("the hint is the shared grey", P.hint.textColor, {U.GREY[1], U.GREY[2], U.GREY[3]})

-- The stat row is the shared row - its font, its hover highlight and its gold selection
-- mark - two lines tall so it can carry the stat's numbers under its name (a class with no
-- primary_stat keeps the server's long generic name, which needs that second line).
local row = P.lines[1].button
assert(row:GetHeight() == U.ROW_HEIGHT * 2, "the stat row is the shared row at twice its height, got " .. tostring(row:GetHeight()))
assert(row.label.template == "GameFontNormal", "the stat row keeps the shared row's font")
same("the row's selection mark is the shared gold", row.mark.vertexColor,
    {U.ROW_SELECT[1], U.ROW_SELECT[2], U.ROW_SELECT[3], U.ROW_SELECT[4]})
same("the row's hover is the shared highlight", row:GetHighlightTexture().vertexColor,
    {U.ROW_HILITE[1], U.ROW_HILITE[2], U.ROW_HILITE[3], U.ROW_HILITE[4]})

-- No flat backdrop anywhere in the window is left without a background and a border colour.
for _, f in ipairs(frames) do
    if inWindow(f, P.frame) and f.backdrop and f.backdrop.bgFile == U.EDGE then
        assert(f.backdropColor and f.borderColor, "a flat Paragon backdrop must have a background and a border colour")
    end
end

print("PASS Paragon look: the window, backdrop, title, subtitle, buttons, XP bar, tabs, rows and "
    .. "colour are the artisans' shared pieces; no UIPanelDialogTemplate chrome, no white flat "
    .. "backdrop; the Primary stat row reads Strength / Intelligence / the generic name per class.")
