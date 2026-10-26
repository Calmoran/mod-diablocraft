-- Run from the repo root: lua5.1 mod-diablocraft/scripts/tests/ui/test_character_sheet.lua
--
-- The Torment character sheet (client-patch/addons/Torment/Inventory.lua and
-- Inventory.xml) against a stub 3.3.5a client, bead
-- diablocraft-inventory-grid-removal. This replaces test_inventory_client.lua,
-- whose subject - a 60-cell grid on a 470px panel - no longer exists. Pinned
-- here, none of it visible until the designer is in the game:
--
--   * no bag grid: no cell frame, no cell template, no snapshot cells read;
--   * the mockup's parts: header (name, "Level N <Class>", "Paragon N"), the
--     paperdoll in D3's three columns, the Cosmetics swap with its line, the four
--     primaries in one row with the class's main stat lit, Damage / Toughness /
--     Recovery, the footer with Details, Materials and the gold;
--   * Details and Materials are ONE panel on the sheet's left: the other button
--     swaps it, the open one's button closes it, and it is anchored to the sheet;
--   * C toggles the sheet; Escape closes the panel first, then the sheet;
--   * the stock cursor does the equipping: a drop on the right slot hands the
--     cursor to PickupInventoryItem, a drop on the wrong one says "That doesn't
--     go there." and touches nothing, a worn item is picked up by dragging, and
--     the potion slot (virtual) sends the existing Equip intent;
--   * right-click on a worn slot sends Unequip, a left-click sends nothing, and a
--     shift-right-click opens the socket window (SocketInventoryItem) without unequipping;
--   * each element's resistance gets a Details row only when a single-element
--     source raised it above All Resistance;
--   * a stat number that moved flashes green (up) or red (down) and fades back;
--   * DCSHEET is only drawn once its E arrives; the screen refreshes while up.
-- luacheck: globals IsModifiedClick CursorHasItem GetCursorInfo ClearCursor PickupInventoryItem
-- luacheck: ignore 122 431 143

local sent = {}

-- ---------------------------------------------------------------- stub client

-- The 3.3.5a widget layer is the ONE shared strict mock (diablocraft-yey2): a
-- method the client lacks, a method of another widget kind, a public .width and
-- a texture-less bar all fail here as they do in the game. The doubles below it
-- are this test's own client globals.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)

-- The XML's DiablocraftSheetSlotTemplate: the client makes each named part and
-- runs the template's OnLoad as the frame is created, and buildSlot reads the
-- parts straight after CreateFrame. The mock makes widgets, not XML, so its
-- factory is wrapped to do that step here.
local rawWidget = Mock.widget
Mock.widget = function(kind, name, parent, template)
    local made = rawWidget(kind, name, parent, template)
    if template == "DiablocraftSheetSlotTemplate" then
        made.highlightTexture = rawWidget("Texture", nil, made)
        for _, suffix in ipairs({"Back", "Rarity", "Icon", "Empty"}) do
            _G[name .. suffix] = rawWidget("Texture", nil, made)
        end
        local DCx = _G.Diablocraft
        DCx.SheetSlot_OnLoad(made)
        made.scripts.OnClick = function(this, button) DCx.SheetSlot_OnClick(this, button) end
        made.scripts.OnEnter = function(this) DCx.SheetSlot_OnEnter(this) end
        made.scripts.OnLeave = function(this) DCx.SheetSlot_OnLeave(this) end
        made.scripts.OnDragStart = function(this) DCx.SheetSlot_OnDragStart(this) end
        made.scripts.OnReceiveDrag = function(this) DCx.SheetSlot_OnReceiveDrag(this) end
    end
    return made
end

-- The old stub collected each frame's font strings in a .strings list; the mock
-- keeps them as FontString children.
local function fsOf(frame)
    local out = {}
    for _, child in ipairs(frame.children or {}) do
        if child.kind == "FontString" then out[#out + 1] = child end
    end
    return out
end

_G.UnitName = function() return "Tester" end
_G.UnitClass = function() return "Wizard" end
_G.UnitLevel = function() return 70 end
_G.SetPortraitTexture = function() end
_G.GetItemIcon = function(entry) return "icon" .. entry end
IsModifiedClick = function() return false end
_G.HideUIPanel = function(panel) panel:Hide() end
_G.DEFAULT_CHAT_FRAME = {AddMessage = function() end}

-- The stock inventory and cursor, reduced to what the sheet reads and does.
local worn = {}          -- client slot id -> {texture, link, quality}
local cursor = nil       -- {itemId, link} or nil
local picked = {}        -- every PickupInventoryItem(id) call, in order
local items = {
    helm = {id = 7001, link = "item:7001", loc = "INVTYPE_HEAD", quality = 4},
    chest = {id = 7002, link = "item:7002", loc = "INVTYPE_CHEST", quality = 5},
    ring = {id = 7003, link = "item:7003", loc = "INVTYPE_FINGER", quality = 3},
    sword = {id = 7004, link = "item:7004", loc = "INVTYPE_WEAPON", quality = 2},
    shield = {id = 7005, link = "item:7005", loc = "INVTYPE_SHIELD", quality = 3},
    potion = {id = 7006, link = "item:7006", loc = "INVTYPE_NON_EQUIP", quality = 1},
}
_G.GetInventoryItemTexture = function(_, id) return worn[id] and worn[id].texture end
_G.GetInventoryItemLink = function(_, id) return worn[id] and worn[id].link end
_G.IsInventoryItemLocked = function(id) return worn[id] and worn[id].locked or false end
_G.GetItemInfo = function(link)
    for _, item in pairs(items) do
        if link == item.link or link == item.id then
            return "name", link, item.quality, 70, 0, "Armor", "x", 1, item.loc
        end
    end
end
_G.CursorHasItem = function() return cursor ~= nil end
_G.GetCursorInfo = function()
    if cursor then return "item", cursor.item.id, cursor.item.link end
end
_G.ClearCursor = function() cursor = nil end
_G.PickupInventoryItem = function(id) picked[#picked + 1] = id end
-- Stock behaviour the sheet relies on: the real call swaps. Not needed by the
-- sheet, so it is only recorded.

-- UISpecialFrames, as FrameXML's CloseSpecialWindows runs it: EVERY shown frame in
-- the list is hidden by one press.
local function pressEscape()
    local found = false
    for _, name in pairs(_G.UISpecialFrames) do
        local made = _G[name]
        if made and made:IsShown() then
            made:Hide()
            found = true
        end
    end
    return found
end

-- The stock character sheet: C and the micro-button both call ToggleCharacter.
-- The client builds these hidden; the mock defaults a widget shown, so hide them.
_G.PaperDollFrame = CreateFrame("Frame", "PaperDollFrame")
_G.TokenFrame = CreateFrame("Frame", "TokenFrame")
_G.CharacterFrame = CreateFrame("Frame", "CharacterFrame")
_G.PaperDollFrame:Hide()
_G.TokenFrame:Hide()
_G.CharacterFrame:Hide()
_G.ToggleCharacter = function(tab)
    local sub = _G[tab]
    if sub:IsShown() and _G.CharacterFrame:IsShown() then
        _G.CharacterFrame:Hide()
        sub:Hide()
    else
        _G.PaperDollFrame:Hide()
        _G.TokenFrame:Hide()
        sub:Show()
        _G.CharacterFrame:Show()
    end
end
-- The addon hooksecurefuncs ToggleCharacter; the mock's hooksecurefunc runs it.
local function pressC()
    _G.ToggleCharacter("PaperDollFrame")
end

-- AIO, reduced to "what did the addon send".
local handlers = {}
_G.AIO = {
    AddHandlers = function() return handlers end,
    Handle = function(_, name, ...) sent[#sent + 1] = {name = name, ...} end,
}

local function sentNamed(name)
    local out = {}
    for _, message in ipairs(sent) do if message.name == name then out[#out + 1] = message end end
    return out
end

_G.Diablocraft = {
    SetArt = function(made, slot) if made then made.art = slot end end,
    Close_OnLoad = function() end,
    StockCursorIndex = function() return _G.stockIndex end,
    -- Stash.lua's stash side (test_stash_client.lua pins the real ones): whether
    -- the stash is up, and the deposit into its open tab, recorded.
    StashIsOpen = function() return _G.stashOpen == true end,
    DepositToOpenTab = function(index) _G.deposits[#_G.deposits + 1] = index; return true end,
    -- Stash.lua's own conversion (test_item_dragging.lua pins the real one).
    BagIndex = function(bag, slot)
        if bag == 0 then return 25500 + slot + 22 end
        if bag >= 1 and bag <= 4 then return (bag + 18) * 100 + slot - 1 end
    end,
    Econ = {
        MATERIALS = {{entry = 102000, name = "Death's Breath"}},
        CURRENCIES = {
            {entry = 102001, name = "Reusable Parts"}, {entry = 102002, name = "Arcane Dust"},
            {entry = 102003, name = "Veiled Crystal"}, {entry = 102004, name = "Forgotten Soul"},
            {entry = 102000, name = "Death's Breath"}, {entry = 102005, name = "Greater Rift Keystone"},
        },
        Gold = function(value) return tostring(value) end,
        Balance = function() return "1234" end,
        Material = function(entry) return entry == 102000 and "7" or "3" end,
        OnChange = function() end,
    },
}

dofile("client-patch/addons/Torment/Inventory.lua")
local DC = _G.Diablocraft

-- The frames the XML would have built, with the XML's own scripts wired. The XML
-- declares all three hidden, and the mock defaults a widget shown.
local panel = CreateFrame("Frame", "DiablocraftInventoryFrame", _G.UIParent)
-- The XML text, all of it fonted: a FontString with no font refuses SetText in the client
-- (dc_widget_mock rule 5), and Inventory.lua's status() and toggleSide() write these.
Mock.widget("FontString", "DiablocraftInventoryFrameStatus", nil, "GameFontNormal")
-- The XML title, font and all: a FontString with no font refuses SetText in the client
-- (dc_widget_mock rule 5), and Inventory.lua's toggleSide writes it.
Mock.widget("FontString", "DiablocraftSidePanelTitle", nil, "GameFontNormal")
local escape = CreateFrame("Frame", "DiablocraftInventoryEscape", _G.UIParent)
panel:Hide()
escape:Hide()
escape:SetScript("OnHide", DC.Escape_OnHide)
DC.Inventory_OnLoad(panel)
panel:SetScript("OnShow", DC.Inventory_OnShow)
panel:SetScript("OnHide", DC.Inventory_OnHide)
local side = CreateFrame("Frame", "DiablocraftSidePanel", _G.UIParent)
side:Hide()
DC.Side_OnLoad(side)

local function lastPoint(made) return made.points[#made.points] end
local function press(made, button) made.scripts.OnClick(made, button or "LeftButton") end

-- Statuses and flashes are read straight off the font strings.
local function find(prefix)
    local out = {}
    for _, made in ipairs(frames) do
        if made.name and made.name:find(prefix) then out[#out + 1] = made end
    end
    return out
end

-- ------------------------------------------------------------ no bag grid

assert(#find("^DiablocraftInvCell") == 0, "the 60-cell grid is gone")
assert(DC.InvSlot_OnLoad == nil and DC.EquipSlot_OnLoad == nil and DC.DropOnEquip == nil,
    "no handler is left for a grid cell or a virtual-cursor worn-slot drop")
local xml = assert(io.open("client-patch/addons/Torment/Inventory.xml")):read("*a")
assert(not xml:find("DiablocraftInvSlotTemplate", 1, true), "the grid cell template is gone from the XML")
assert(not xml:find("DiablocraftDetailsFrame", 1, true) and not xml:find("DiablocraftMaterialsFrame", 1, true),
    "Details and Materials are not two frames any more")
local lua = assert(io.open("client-patch/addons/Torment/Inventory.lua")):read("*a")
assert(not lua:find("snapshot.bags", 1, true) and not lua:find("StartDrag", 1, true)
    and not lua:find("ResolveDrop", 1, true), "the sheet reads no bag cells and starts no virtual drag")

-- ------------------------------------------------------------- the slot map

-- The mockup's columns: left x 40-108, centre 152-220, right 264-332, in the
-- 372 square doll; so left < centre < right and every slot is inside the sheet.
local gear = find("^DiablocraftGearSlot")
assert(#gear == 14, "thirteen gear slots plus potion, got " .. #gear)
local by = {}
local seen = {}
for _, made in ipairs(gear) do
    by[made.equipSlot] = made
    local point = made.points[1]
    local key = point.x .. ":" .. point.y
    assert(not seen[key], "two gear slots share a position at " .. key)
    seen[key] = true
    assert(point.x >= 16 and point.x + made:GetWidth() <= panel:GetWidth() - 16,
        "slot " .. made.equipSlot .. " stays inside the border band")
    -- bagID/slotID: dc_tooltip.lua locate() finds the worn item by them.
    assert(made.bagID == 255 and made.slotID == made.equipSlot, "tooltip owner carries bag 255 and the slot")
end
assert(panel:GetWidth() == 420 and panel:GetHeight() == 660, "the sheet is 420 x 660")
for _, slot in ipairs({0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 15, 16, 100}) do
    assert(by[slot], "equipment slot " .. slot .. " is on the paperdoll")
end
-- Column membership is by centre line: the rings and the potion are smaller than
-- the armour slots and sit centred in their column, as in the mockup.
local function x(slot) return by[slot].points[1].x + by[slot]:GetWidth() / 2 end
local function y(slot) return by[slot].points[1].y end
-- left column: shoulders, gloves, ring, main hand, potion; top to bottom
local left = {2, 9, 10, 15, 100}
for index = 2, #left do
    assert(y(left[index]) < y(left[index - 1]), "the left column runs shoulders to potion")
end
for _, slot in ipairs({2, 9, 10, 15}) do assert(x(slot) == x(2), "the left column is one column") end
-- centre: helm, chest, belt, pants, boots
local centre = {0, 4, 5, 6, 7}
for index = 2, #centre do
    assert(x(centre[index]) == x(0), "the centre column is one column")
    assert(y(centre[index]) < y(centre[index - 1]), "the centre column runs helm to boots")
end
-- right: amulet, bracers, ring, off hand
local right = {1, 8, 11, 16}
for index = 2, #right do
    assert(y(right[index]) < y(right[index - 1]), "the right column runs amulet to off hand")
end
assert(x(2) < x(0) and x(0) < x(8), "left, centre, right in that order")
assert(x(100) < x(0), "the potion sits to the left of the boots")

-- Cosmetics: five slots, hidden until the toggle, with the mockup's line.
local cosmetic = find("^DiablocraftCosmeticSlot")
assert(#cosmetic == 5, "five cosmetic slots, got " .. #cosmetic)
for _, made in ipairs(cosmetic) do assert(not made:IsShown(), "cosmetics start hidden") end
assert(panel.cosmeticNote.text == "Cosmetics change how you look. They have no stats.", "the Cosmetics line")

-- ---------------------------------------------------------------- the header

local function snapshot(extra)
    local data = {level = 70, paragon = 186, mainStat = "Intelligence", potion = {index = 100},
                  gold = "1234", materials = {}}
    for key, value in pairs(extra or {}) do data[key] = value end
    return data
end
handlers.Snapshot(nil, snapshot())
local strings = {}
for _, made in ipairs(fsOf(panel)) do strings[#strings + 1] = made.text end
local function has(text)
    for _, entry in ipairs(strings) do if entry == text then return true end end
    return false
end
-- The header is plain font strings on the sheet; re-read after the draw.
strings = {}
for _, made in ipairs(fsOf(panel)) do strings[#strings + 1] = made.text end
assert(has("Tester"), "the header shows the name")
assert(has("Level 70 |cff8cbaff(186)|r Wizard"), "the header says Level N (Paragon) <Class>, the number in the Paragon colour, got " .. table.concat(
    (function() local out = {} for _, s in ipairs(strings) do out[#out + 1] = tostring(s) end return out end)(), "|"))
assert(_G.DiablocraftInventoryParagon.template == "UIPanelButtonTemplate", "the Paragon opener is a native WoW button")
assert(_G.DiablocraftInventoryParagon:GetText() == "Paragon", "and it just says Paragon; the level is in the bracket")

-- --------------------------------------------------------------- the stat row

local function sheetMessage(...)
    for _, payload in ipairs({...}) do
        -- The watcher's own handler, as the client calls it.
        _G.DiablocraftInventoryWatcher.scripts.OnEvent(nil, "CHAT_MSG_ADDON", "DCSHEET", payload, "WHISPER", "Tester")
    end
end
local function sheetOf(values)
    local pairs_ = {}
    for key, value in pairs(values) do pairs_[#pairs_ + 1] = key .. "=" .. value end
    table.sort(pairs_)
    return {"B|70", "V|" .. table.concat(pairs_, ";"), "E"}
end
DC.Inventory_Open()
sheetMessage(unpack(sheetOf({str = 12, dex = 15, int = 4217, vit = 988, dmg = 100000, tough = 2500000, recov = 8000})))

local stats = {}
for _, key in ipairs({"str", "dex", "int", "vit"}) do stats[key] = _G["DiablocraftInventoryStat" .. key] end
for _, key in ipairs({"str", "dex", "int", "vit"}) do assert(stats[key], "the " .. key .. " stat is on the sheet") end
-- One row: the four share a y and run left to right in the mockup's order.
for _, key in ipairs({"dex", "int", "vit"}) do
    assert(stats[key].points[1].y == stats.str.points[1].y, "the four primaries are in one row")
end
assert(stats.str.points[1].x < stats.dex.points[1].x and stats.dex.points[1].x < stats.int.points[1].x
    and stats.int.points[1].x < stats.vit.points[1].x, "Strength, Dexterity, Intelligence, Vitality")
local function number(key) return fsOf(stats[key])[2] end
assert(fsOf(stats.int)[2].text == "4217", "Intelligence shows the server's number, got " .. tostring(fsOf(stats.int)[2].text))
-- The class's main stat is the lit one; the others are plain.
local function colourOf(text) return text.textColor[1] .. "," .. text.textColor[2] .. "," .. text.textColor[3] end
assert(colourOf(number("int")) ~= colourOf(number("str")), "the main stat is highlighted")
assert(colourOf(number("str")) == colourOf(number("dex")), "the other primaries are plain")
handlers.Snapshot(nil, snapshot({mainStat = "Strength"}))
assert(colourOf(number("str")) ~= colourOf(number("int")), "the highlight follows the class's main stat")
handlers.Snapshot(nil, snapshot())
local damage = _G.DiablocraftInventorySummarydmg
assert(damage and fsOf(damage)[2].text == "100000", "Damage shows")
assert(fsOf(_G.DiablocraftInventorySummarytough)[2].text == "2500000", "Toughness shows")
assert(fsOf(_G.DiablocraftInventorySummaryrecov)[2].text == "8000", "Recovery shows")
assert(fsOf(damage)[1].text == "Damage" and fsOf(_G.DiablocraftInventorySummaryrecov)[1].text == "Recovery",
    "Recovery, not Healing")

-- DCSHEET is only drawn once its E arrives.
sheetMessage("B|70", "V|int=1")
assert(number("int").text == "4217", "a half-received block leaves the previous sheet up")

-- A stranger's whisper of the prefix is dropped.
_G.DiablocraftInventoryWatcher.scripts.OnEvent(nil, "CHAT_MSG_ADDON", "DCSHEET", "B|70", "WHISPER", "Mallory")
sheetMessage(unpack(sheetOf({int = 4217, str = 12, dex = 15, vit = 988, dmg = 100000, tough = 2500000, recov = 8000})))

-- ----------------------------------------------------------------- the footer

assert(_G.DiablocraftInventoryDetails and _G.DiablocraftInventoryMaterials, "Details and Materials buttons")
assert(_G.DiablocraftInventoryDetails:GetText() == "DETAILS" and _G.DiablocraftInventoryMaterials:GetText() == "MATERIALS")
local footerY = _G.DiablocraftInventoryDetails.points[1].y
assert(footerY < _G.DiablocraftInventorySummarydmg.points[1].y, "the footer is under the summary")
assert(_G.DiablocraftInventoryMaterials.points[1].y == footerY, "the two buttons share a row")
local goldText
for _, made in ipairs(fsOf(panel)) do if made.text and made.text:find("gold$") then goldText = made.text end end
assert(goldText == "1234 gold", "the footer shows the gold total, got " .. tostring(goldText))

-- -------------------------------------------- styled like the Jeweler window

-- Ruling 2026-10-01: the Jeweler's look - the stock dialog backdrop and native buttons,
-- now defined once in dc_aio_ui.lua. The backdrop is read out of the module's own PANEL
-- table and compared field by field, so the windows cannot drift apart.
local uiModuleSource = assert(io.open("mod-diablocraft/lua/aio/dc_aio_ui.lua")):read("*a")
local panelSource = assert(uiModuleSource:match("local PANEL=(%b{})"), "dc_aio_ui.lua declares the shared PANEL")
local function field(name) return panelSource:match(name .. '="([^"]+)"') end
local function numberOf(name) return tonumber(panelSource:match(name .. "=(%d+)")) end
local want = {bgFile = field("bgFile"):gsub("\\\\", "\\"), edgeFile = field("edgeFile"):gsub("\\\\", "\\")}
for _, window in ipairs({panel, side}) do
    local look = window.backdrop
    assert(look, (window.name or "?") .. " has the Jeweler's backdrop set")
    assert(look.bgFile == want.bgFile and look.edgeFile == want.edgeFile, "the same dialog textures as the Jeweler")
    assert(look.tile == true and look.tileSize == numberOf("tileSize") and look.edgeSize == numberOf("edgeSize"),
        "the same tiling and edge size")
    assert(look.insets.left == numberOf("left") and look.insets.right == numberOf("right")
        and look.insets.top == numberOf("top") and look.insets.bottom == numberOf("bottom"), "the same insets")
end
assert(uiModuleSource:find('"UIPanelCloseButton"', 1, true) and uiModuleSource:find('"UIPanelButtonTemplate"', 1, true),
    "the templates this sheet copies are the ones the shared module uses")
for _, name in ipairs({"DiablocraftInventoryDetails", "DiablocraftInventoryMaterials", "DiablocraftInventoryCosmetics", "DiablocraftInventoryParagon"}) do
    assert(_G[name].template == "UIPanelButtonTemplate", name .. " is a native WoW button")
end
local closes = 0
for _ in xml:gmatch('<Button name="%$parentClose" inherits="UIPanelCloseButton">') do closes = closes + 1 end
assert(closes == 2, "both close buttons are the native UIPanelCloseButton, got " .. closes)
assert(not xml:find("Close_OnLoad", 1, true), "and neither wears the Torment X art")
assert(not lua:find("DC.PanelFrame", 1, true) and not lua:find("PanelReport", 1, true),
    "no Torment panel kit border on either window")

-- No portrait, no ring.
assert(not lua:find("SetPortraitTexture", 1, true) and not lua:find("TrackingBorder", 1, true),
    "the round portrait and its ring are gone")

-- Every slot one size, square, each centre where the mockup box had it.
local CENTRES = {
    [2] = {74, 61}, [9] = {74, 140}, [10] = {74, 208}, [15] = {74, 282}, [100] = {74, 351},
    [0] = {186, 40}, [4] = {186, 125}, [5] = {186, 193}, [6] = {186, 255}, [7] = {186, 333},
    [1] = {298, 62}, [8] = {298, 140}, [11] = {298, 208}, [16] = {298, 282},
}
local COSMETIC_CENTRES = {[3] = {74, 104}, [18] = {74, 270}, [12] = {186, 40}, [13] = {186, 316}, [14] = {298, 104}}
local size
local function pinCentres(buttons, centres)
    for _, made in ipairs(buttons) do
        size = size or made:GetWidth()
        assert(made:GetWidth() == size and made:GetHeight() == size, "slot " .. made.equipSlot .. " is the one square size")
        local point = made.points[1]
        local cx, cy = point.x - 24 + made:GetWidth() / 2, -point.y - 96 + made:GetHeight() / 2
        local want = centres[made.equipSlot]
        assert(want and cx == want[1] and cy == want[2],
            "slot " .. made.equipSlot .. " keeps its centre, got " .. cx .. "," .. cy)
    end
end
pinCentres(gear, CENTRES)
pinCentres(cosmetic, COSMETIC_CENTRES)
assert(size and size >= 40 and size <= 56, "a sensible icon size, got " .. tostring(size))
local clear = {}
for _, made in ipairs(gear) do clear[#clear + 1] = made end
for first = 1, #clear do
    for second = first + 1, #clear do
        local a, b = clear[first].points[1], clear[second].points[1]
        local apart = math.abs(a.x - b.x) >= size or math.abs(a.y - b.y) >= size
        assert(apart, "slots " .. clear[first].equipSlot .. " and " .. clear[second].equipSlot .. " do not overlap")
    end
end
assert(-gear[1].points[1].y - 96 + 0 >= 0, "no slot above the doll")

-- ------------------------------------------- one side panel, two contents

assert(#find("^DiablocraftDetailsFrame$") == 0 and #find("^DiablocraftMaterialsFrame$") == 0, "no second panel")
local anchor = lastPoint(side)
assert(anchor.point == "TOPRIGHT" and anchor.relativePoint == "TOPLEFT" and anchor.relativeTo == panel,
    "the panel is attached to the sheet's left edge")
assert(side:GetWidth() == 340 and side:GetHeight() == 660, "side panel size")
local sideXml = xml:match('<Frame name="DiablocraftSidePanel".-</Frame>')
assert(sideXml and sideXml:find('relativeTo="DiablocraftInventoryFrame"', 1, true), "anchored in the XML too")
assert(not sideXml:find("OnDragStart", 1, true) and not sideXml:find('movable="true"', 1, true), "no drag of its own")

DC.Inventory_Open()
assert(panel:IsShown() and not side:IsShown(), "the panel starts shut")
press(_G.DiablocraftInventoryDetails)
assert(side:IsShown() and _G.DiablocraftSidePanelTitle.text == "Details", "Details opens the panel")
assert(_G.DiablocraftDetailsScroll.shown ~= false and _G.DiablocraftMaterialsList.shown == false, "with the Details list")
press(_G.DiablocraftInventoryMaterials)
assert(side:IsShown() and _G.DiablocraftSidePanelTitle.text == "Materials", "Materials swaps the same panel")
assert(_G.DiablocraftMaterialsList.shown == true and _G.DiablocraftDetailsScroll.shown == false, "Materials list is up")
press(_G.DiablocraftInventoryMaterials)
assert(not side:IsShown(), "pressing the open one again closes it")
press(_G.DiablocraftInventoryDetails)
press(_G.DiablocraftInventoryDetails)
assert(not side:IsShown(), "Details closes on its own button too")
-- The Materials rows: icon, full name, count, and the mockup's line.
press(_G.DiablocraftInventoryMaterials)
local rowText = {}
for _, made in ipairs(frames) do
    if made.parent == _G.DiablocraftMaterialsList then
        for _, line in ipairs(fsOf(made)) do rowText[#rowText + 1] = line.text end
    end
end
local joined = "|" .. table.concat(rowText, "|") .. "|"
for _, name in ipairs({"Reusable Parts", "Arcane Dust", "Veiled Crystal", "Forgotten Soul", "Death's Breath", "Greater Rift Keystone"}) do
    assert(joined:find("|" .. name .. "|", 1, true), "Materials lists " .. name)
end
assert(_G.DiablocraftMaterialsList.note.text == "Materials are kept on the sheet. They take no bag space.", "the Materials line")
press(_G.DiablocraftInventoryMaterials)

-- Details: five groups, every row's label clear of its value.
press(_G.DiablocraftInventoryDetails)
local groups = {}
for _, made in ipairs(frames) do
    if made.parent == _G.DiablocraftDetailsContent and made.shown then
        local row = fsOf(made)
        if row[1] and row[1].text == row[1].text:upper() and row[2].text == "" then
            groups[#groups + 1] = row[1].text
        end
    end
end
assert(table.concat(groups, ",") == "OFFENSE,DEFENSE,LIFE,RESOURCE,ADVENTURE", "five groups, got " .. table.concat(groups, ","))
-- Each element's resistance shows only when a single-element source raised it
-- above All Resistance, which has its own row (so the row is never a repeat).
local function detailRows()
    local rows = {}
    for _, made in ipairs(frames) do
        if made.parent == _G.DiablocraftDetailsContent and made.shown then
            local row = fsOf(made)
            if row[1] and row[2] and row[2].text ~= "" then rows[row[1].text] = row[2].text end
        end
    end
    return rows
end
local flat = {int = 4217, str = 12, dex = 15, vit = 988, dmg = 100000, tough = 2500000, recov = 8000,
              resall = 500, res0 = 500, res1 = 500, res2 = 500, res3 = 500, res4 = 500, res5 = 500, res6 = 500}
sheetMessage(unpack(sheetOf(flat)))
assert(detailRows()["All Resistance"] == "500", "All Resistance shows")
assert(detailRows()["Fire Resistance"] == nil, "an element equal to All Resistance adds no row")
flat.res1 = 650
sheetMessage(unpack(sheetOf(flat)))
assert(detailRows()["Fire Resistance"] == "650", "an element raised on its own shows its own row")
assert(detailRows()["Cold Resistance"] == nil, "and the untouched elements stay off the list")
press(_G.DiablocraftInventoryDetails)

-- --------------------------------------------------------------- C and Escape

panel:Hide()
assert(not panel:IsShown())
pressC()
assert(panel:IsShown() and not _G.CharacterFrame:IsShown(), "C opens the Torment sheet, not the stock one")
pressC()
assert(not panel:IsShown(), "C again closes it")
-- The currency tab is untouched.
_G.ToggleCharacter("TokenFrame")
assert(_G.CharacterFrame:IsShown() and not panel:IsShown(), "the currency tab is still stock")
_G.CharacterFrame:Hide()

-- Escape: the side panel first, then the sheet.
DC.Inventory_Open()
press(_G.DiablocraftInventoryDetails)
assert(side:IsShown() and panel:IsShown())
assert(pressEscape(), "Escape found something to close")
assert(not side:IsShown() and panel:IsShown(), "the first Escape closes only the side panel")
assert(pressEscape(), "and the second finds the sheet")
assert(not panel:IsShown(), "the second Escape closes the sheet")
assert(not pressEscape(), "a third finds nothing, so the game menu may open")
-- With the cosmetics view up, Escape closes the sheet in one press and nothing stays shown.
DC.Inventory_Open()
press(_G.DiablocraftInventoryCosmetics)
assert(pressEscape() and not panel:IsShown(), "Escape closes the sheet from the cosmetics view")
assert(not cosmetic[1]:IsShown(), "and the cosmetics view is reset")

-- --------------------------------------------------------- the Cosmetics swap

DC.Inventory_Open()
assert(by[0]:IsShown() and not cosmetic[1]:IsShown())
press(_G.DiablocraftInventoryCosmetics)
assert(not by[0]:IsShown() and cosmetic[1]:IsShown(), "Cosmetics swaps the paperdoll for the five slots")
assert(panel.cosmeticNote.shown == true, "and shows its line")
assert(_G.DiablocraftInventoryCosmetics:GetText() == "EQUIPMENT", "the toggle becomes the way back")
local labels = {}
for _, line in ipairs(panel.cosmeticLabels) do labels[#labels + 1] = line.text end
assert(table.concat(labels, ",") == "Wings,Pet,Aura,Footsteps,Back", "Wings, Pet, Aura, Footsteps, Back")
press(_G.DiablocraftInventoryCosmetics)
assert(by[0]:IsShown() and not cosmetic[1]:IsShown(), "and back")

-- --------------------------------------------------------- stock-cursor equip

local function hold(item) cursor = {item = item} end
local function drop(slot)
    by[slot].scripts.OnReceiveDrag(by[slot])
end

-- A helm onto the helm slot: the stock cursor does the equip.
picked = {}
hold(items.helm)
drop(0)
assert(#picked == 1 and picked[1] == 1, "a helm on the helm slot is PickupInventoryItem(1), got " .. #picked)
-- Dropped on the wrong slot: the message, no pickup, nothing sent.
picked, sent = {}, {}
_G.UIErrorsFrame.lines = {}
hold(items.helm)
drop(4)
assert(#picked == 0, "a drop on the wrong slot touches nothing")
assert(_G.DiablocraftInventoryFrameStatus.text == "That doesn't go there.", "wrong slot says so on the sheet")
assert(_G.UIErrorsFrame.lines[1] == "That doesn't go there.", "and in the error frame")
assert(#sent == 0, "and sends no intent")
-- Left-click with an item held is the same drop.
picked = {}
hold(items.chest)
press(by[4])
assert(picked[1] == 5, "a click with a chest held equips it in the chest slot (slot 4, client id 5)")
-- Rings go in either ring slot; a shield in the off hand but not the main hand.
picked = {}
hold(items.ring); drop(10); hold(items.ring); drop(11)
assert(picked[1] == 11 and picked[2] == 12, "a ring fits both ring slots")
picked = {}
hold(items.shield); drop(15)
assert(#picked == 0, "a shield does not go in the main hand")
hold(items.shield); drop(16)
assert(picked[1] == 17, "a shield goes in the off hand")
hold(items.sword); drop(15)
assert(picked[#picked] == 16, "a one-handed weapon goes in the main hand")
-- An item the client cannot name yet: the drop goes through and the server decides.
picked = {}
hold({id = 9999, link = "item:9999"})
drop(0)
assert(#picked == 1, "an uncached item is left to the server")

-- The potion slot is virtual: the existing Equip intent, with the bag index the
-- stock cursor came from. A worn item (bag 255 below the bags) is refused.
sent, picked = {}, {}
_G.stockIndex = 100 * 19 + 3
hold(items.potion)
drop(100)
assert(#picked == 0, "the potion slot never uses PickupInventoryItem")
local equips = sentNamed("Equip")
assert(#equips == 1 and equips[1][1] == 1903, "a drop on the potion slot sends Equip with the bag index")
assert(cursor == nil, "and the cursor is put away")
-- The BACKPACK is container 255 too (cells 23-38): a potion dragged from the backpack
-- is a bag item, not a worn one (the first build refused every 255xx index).
sent, picked = {}, {}
_G.stockIndex = 255 * 100 + 23
hold(items.potion)
drop(100)
local fromPack = sentNamed("Equip")
assert(#fromPack == 1 and fromPack[1][1] == 25523, "a potion from the first backpack cell is equipped")
sent = {}
_G.stockIndex = 255 * 100 + 38
hold(items.potion)
drop(100)
assert(#sentNamed("Equip") == 1, "and from the last one")
sent = {}
_G.stockIndex = 255 * 100 + 22
hold(items.potion)
drop(100)
assert(#sentNamed("Equip") == 0, "slot 22 is the last equipment slot, not a bag cell")
sent = {}
_G.stockIndex = 255 * 100 + 4
hold(items.helm)
drop(100)
assert(#sentNamed("Equip") == 0 and _G.DiablocraftInventoryFrameStatus.text == "That doesn't go there.",
    "a worn item is not a potion")
cursor = nil
_G.stockIndex = nil

-- ------------------------------------------------------- worn item: drag, click

-- A worn slot draws from the stock API: the icon, the quality colour, and the
-- empty picture when bare.
worn[1] = {texture = "helmicon", link = items.helm.link}
DC.Inventory_DrawSlots()
assert(by[0].filled == true and by[0].icon.texture == "helmicon", "a worn slot shows the stock item's icon")
assert(by[4].filled == false and by[4].empty.alpha == 0.35, "a bare slot shows its faint picture")
-- Dragging it picks it up with the stock cursor (so an ElvUI bag slot takes it).
picked = {}
by[0].scripts.OnDragStart(by[0])
assert(picked[1] == 1, "dragging a worn item is PickupInventoryItem(its client id)")
picked = {}
by[4].scripts.OnDragStart(by[4])
assert(#picked == 0, "an empty slot starts no drag")
by[100].scripts.OnDragStart(by[100])
assert(#picked == 0, "the potion slot has no stock pickup")
-- Right-click takes it off; left-click and a bare right-click send nothing.
sent = {}
press(by[0], "LeftButton")
press(by[4], "RightButton")
assert(#sent == 0, "a left-click and a right-click on an empty slot send nothing")
press(by[0], "RightButton")
local unequips = sentNamed("Unequip")
assert(#unequips == 1 and unequips[1][1] == 0, "right-click on a worn slot sends Unequip with the WoW slot")
-- Shift-right-click opens the socket window for the worn item and never unequips
-- (the stock paperdoll gesture; dc_jeweler.lua's hook answers SocketInventoryItem).
local socketCalls = {}
_G.SocketInventoryItem = function(id) socketCalls[#socketCalls + 1] = id end
IsModifiedClick = function(action) return action == "SOCKETITEM" end
sent = {}
press(by[0], "RightButton")
assert(#sentNamed("Unequip") == 0, "shift-right-click does not unequip")
assert(socketCalls[1] == 1, "shift-right-click opens the socket window for the worn slot's WoW id")
socketCalls = {}
press(by[100], "RightButton")
assert(#socketCalls == 0, "the virtual potion slot has no stock socket id")
IsModifiedClick = function() return false end
-- The potion: right-click unequips only when one is set.
sent = {}
press(by[100], "RightButton")
assert(#sent == 0, "an empty potion slot sends nothing")
handlers.Snapshot(nil, snapshot({potion = {index = 100, entry = 6006}}))
press(by[100], "RightButton")
assert(sent[1] and sent[1].name == "Unequip" and sent[1][1] == 100, "right-click on the potion unequips it")
by[100].scripts.OnEnter(by[100])
assert(_G.GameTooltip.hyperlink == "item:6006", "the potion's tooltip is its item")
-- Stock tooltip on a worn item.
by[0].scripts.OnEnter(by[0])
assert(_G.GameTooltip.inventoryItem and _G.GameTooltip.inventoryItem[2] == 1, "a worn item shows the stock item tooltip")
by[4].scripts.OnEnter(by[4])
assert(_G.GameTooltip.lines[1] == "Chest", "an empty slot names itself")

-- ------------------------------------------------------------- stat flashes

local function step(seconds) DC.Inventory_FlashStep(seconds) end
local int = number("int")
local base = colourOf(int)
sheetMessage(unpack(sheetOf({int = 4300, str = 12, dex = 15, vit = 988, dmg = 100000, tough = 2500000, recov = 8000})))
assert(int.text == "4300", "the new number is drawn")
assert(int.textColor[2] > int.textColor[1] and int.textColor[2] > int.textColor[3], "a stat that went up turns green")
step(0.5)
assert(colourOf(int) ~= base, "mid-fade it is neither the flash nor the base colour")
step(5)
assert(colourOf(int) == base, "and fades back to its own colour")
local toughness = fsOf(_G.DiablocraftInventorySummarytough)[2]
sheetMessage(unpack(sheetOf({int = 4300, str = 12, dex = 15, vit = 988, dmg = 100000, tough = 2000000, recov = 8000})))
assert(toughness.textColor[1] > toughness.textColor[2] and toughness.textColor[1] > toughness.textColor[3], "a stat that went down turns red")
step(5)
-- A refresh with nothing new flashes nothing.
local before = colourOf(int)
sheetMessage(unpack(sheetOf({int = 4300, str = 12, dex = 15, vit = 988, dmg = 100000, tough = 2000000, recov = 8000})))
assert(colourOf(int) == before and next(_G.Diablocraft) ~= nil, "an unchanged value does not flash")
-- Details rows flash too.
press(_G.DiablocraftInventoryDetails)
sheetMessage(unpack(sheetOf({int = 4300, str = 20, dex = 15, vit = 988, dmg = 100000, tough = 2000000, recov = 8000})))
local flashed = false
for _, made in ipairs(frames) do
    if made.parent == _G.DiablocraftDetailsContent then
        local row = fsOf(made)
        if row[2] and row[2].text == "20.00%" then
            flashed = row[2].textColor[2] > row[2].textColor[1]
        end
    end
end
assert(flashed, "a Details row whose number rose turns green")
press(_G.DiablocraftInventoryDetails)

-- ------------------------------------------------------- the refresh watcher

local watcher = _G.DiablocraftInventoryWatcher
sent = {}
panel:Hide()
watcher.scripts.OnEvent(watcher, "PLAYER_EQUIPMENT_CHANGED")
watcher.scripts.OnUpdate(watcher, 1)
assert(#sentNamed("Refresh") == 0, "a hidden screen asks for nothing")
DC.Inventory_Open()
assert(#sentNamed("Refresh") == 1, "opening asks for a fresh snapshot")
sent = {}
watcher.scripts.OnEvent(watcher, "PLAYER_EQUIPMENT_CHANGED")
watcher.scripts.OnEvent(watcher, "UNIT_INVENTORY_CHANGED", "player")
watcher.scripts.OnUpdate(watcher, 0.1)
assert(#sentNamed("Refresh") == 0, "debounced")
watcher.scripts.OnUpdate(watcher, 0.4)
assert(#sentNamed("Refresh") == 1, "an equipment burst is one round trip")
-- Equipping through the stock cursor redraws the worn slots at once.
worn[5] = {texture = "chesticon", link = items.chest.link}
watcher.scripts.OnEvent(watcher, "PLAYER_EQUIPMENT_CHANGED")
assert(by[4].icon.texture == "chesticon", "a worn slot redraws on the stock equipment event")
worn[5].locked = true
watcher.scripts.OnEvent(watcher, "ITEM_LOCK_CHANGED")
assert(by[4].filled == true, "the lock event redraws the slots")

-- ----------------------------------------------- the rolled rarity border

-- The border is the ROLLED rarity when dc_tooltip.lua holds a record, else the
-- stock quality (a chest of quality 3 is blue, a rolled Legendary orange).
worn[5] = {texture = "chesticon", link = items.chest.link}
DC.Inventory_DrawSlots()
assert(by[4].rarity.art == "slot-rarity-orange", "no record: the stock quality (the chest is quality 5)")
items.chest.quality = 3
DC.Inventory_DrawSlots()
assert(by[4].rarity.art == "slot-rarity-blue", "no record: a stock quality-3 chest is blue")
_G.DCItemRarity = function(bag, slot) return bag == 255 and slot == 4 and "legendary" or nil end
_G.DCOnItemRecords()
assert(by[4].rarity.art == "slot-rarity-orange", "a rolled Legendary shows orange whatever the stock quality")
_G.DCItemRarity = function() return "set" end
_G.DCOnItemRecords()
assert(by[4].rarity.art == "slot-rarity-green", "a Set item shows green, and the arrival of records redraws")
_G.DCItemRarity = function() return "bogus" end
_G.DCOnItemRecords()
assert(by[4].rarity.art == "slot-rarity-blue", "an unknown rarity falls back to the stock quality")
_G.DCItemRarity = nil
panel:Hide()
_G.DCOnItemRecords()   -- hidden sheet: nothing to draw, no error

-- ----------------------------------------------- right-click a potion in the bags

local originals = {OnClick = function() end, Use = function() end}
_G.ContainerFrameItemButton_OnClick, _G.UseContainerItem = originals.OnClick, originals.Use

cursor = nil
local bagItems = {}   -- slot -> link; bag 0 has 6 slots
_G.GetContainerNumSlots = function() return 6 end
_G.GetContainerItemLink = function(b, slot) return b == 0 and bagItems[slot] or nil end
local combat, shift, claim = false, false, false
_G.InCombatLockdown = function() return combat end
_G.IsShiftKeyDown = function() return shift end
_G.IsControlKeyDown = function() return false end
_G.IsAltKeyDown = function() return false end
local function bagButton(slot)
    local button = Mock.widget("Button", "ContainerFrame1Item" .. slot, {GetID = function() return 0 end})
    button.id = slot
    button.GetParent = function() return {GetID = function() return 0 end} end
    return button
end
local button3 = bagButton(3)
bagItems = {[3] = "item:7006", [4] = "item:7004", [1] = "item:7004", [2] = "item:7004", [6] = "item:7004"}   -- slot 5 is empty

_G.deposits = {}
-- The client runs the button's own script, then the hooks (dc_widget_mock HookScript).
local function click(button, mouseButton)
    if button.scripts.PreClick then button.scripts.PreClick(button, mouseButton or "RightButton") end
    local during = button.id
    if button.scripts.PostClick then button.scripts.PostClick(button) end
    return during
end

-- No potion named by the server: the button is hooked all the same (the stash needs the
-- hook), but a right-click on any item does nothing the stock click would not.
handlers.Snapshot(nil, snapshot())
DC.Inventory_ScanPotionButtons()
sent = {}
assert(click(button3) == 3 and #sentNamed("Equip") == 0, "a server that names no potion: the click is left to the stock")

handlers.Snapshot(nil, snapshot({potionEntries = {7006}}))
DC.Inventory_ScanPotionButtons()
assert(button3.scripts.PreClick and button3.scripts.PostClick, "a hook, per button, once")
local preClick, postClick = button3.scripts.PreClick, button3.scripts.PostClick
DC.Inventory_ScanPotionButtons()
assert(button3.scripts.PreClick == preClick and button3.scripts.PostClick == postClick,
    "scanning again does not hook twice")

sent = {}
local during = click(button3)
assert(during == 5, "the stock click is pointed at the bag's empty slot for that one click, got " .. tostring(during))
assert(button3.id == 3, "and the button's own slot is put back")
local equipSent = sentNamed("Equip")
assert(#equipSent == 1 and equipSent[1][1] == 255 * 100 + 25, "the potion's bag index goes out as Equip")
assert(_G.ContainerFrameItemButton_OnClick == originals.OnClick and _G.UseContainerItem == originals.Use,
    "no stock global was replaced")

local function quiet(why, setup, teardown, button)
    sent = {}
    setup()
    local id = click(button or button3, why == "left" and "LeftButton" or "RightButton")
    teardown()
    assert(#sentNamed("Equip") == 0 and id == (button or button3).id, why .. ": nothing is sent and the id is untouched")
end
quiet("left", function() end, function() end)
quiet("combat", function() combat = true end, function() combat = false end)
quiet("a held item", function() cursor = {item = items.helm} end, function() cursor = nil end)
quiet("shift", function() shift = true end, function() shift = false end)
local plain = bagButton(4)
handlers.Snapshot(nil, snapshot({potionEntries = {7006}}))
DC.Inventory_ScanPotionButtons()
quiet("an item that is not a potion", function() end, function() end, plain)
bagItems[5] = "item:7004"
-- A full bag has no empty cell, so the stock click is pointed past the bag's last slot
-- (nothing there) instead of being let through to drink the potion.
sent = {}
assert(click(button3) == 7 and #sentNamed("Equip") == 1, "a full bag: the potion is still equipped, the stock click blanked")
bagItems[5] = nil

-- Another screen's claim (the Jeweler's Unsocket tab) wins, whichever PreClick
-- runs first: while it is true this hook does nothing at all.
DC.ClaimRightClick(function() return claim end)
quiet("a claimed right-click", function() claim = true end, function() claim = false end)
-- ...and the sheet's own worn slot yields to it too: with the Jeweler's Unsocket tab open
-- a right-click on a worn item loads it there instead of taking it off.
worn[1] = {texture = "helmicon", link = items.helm.link}
DC.Inventory_DrawSlots()
sent = {}
claim = true
press(by[0], "RightButton")
assert(#sentNamed("Unequip") == 0, "a claimed right-click on a worn slot does not unequip")
claim = false
press(by[0], "RightButton")
assert(#sentNamed("Unequip") == 1, "and unequips once the claim is dropped")
sent = {}
assert(click(button3) == 5 and #sentNamed("Equip") == 1, "and once the claim is dropped the hook works again")

-- Combat starting puts any borrowed id back.
button3.scripts.PreClick(button3, "RightButton")
assert(button3.id == 5, "mid-click the id is the stand-in")
watcher.scripts.OnEvent(watcher, "PLAYER_REGEN_DISABLED")
assert(button3.id == 3, "PLAYER_REGEN_DISABLED restores it")

-- ------------------------------------- the new addon against TODAY's server Lua

-- Today's server sends the grid snapshot: worn cells, 60 bag cells, a layout, a
-- potion that is a full cell, and no mainStat or potionEntries. The new addon draws
-- from the stock client and ignores all of it - quietly.
local oldBags = {}
for position = 1, 60 do oldBags[position] = {index = -1, available = false} end
oldBags[1] = {index = 25523, available = true, entry = 5001, count = 1, colour = "orange", guid = 900, name = "X"}
panel:Hide()
DC.Inventory_Open()
local ok, err = pcall(handlers.Snapshot, nil, {
    level = 70, paragon = 3, gold = "99", materials = {},
    equipped = {[15] = {index = 15, entry = 6001, count = 1, colour = "yellow", guid = 901, name = "Y"}},
    potion = {index = 100, available = true, entry = 6006, count = 1, colour = "grey", name = "P", link = "[p]"},
    bags = oldBags, layout = {bagRows = 6, bagCols = 10}, note = "login",
})
assert(ok, "an old-server snapshot must not error: " .. tostring(err))
strings = {}
for _, made in ipairs(fsOf(panel)) do strings[#strings + 1] = made.text end
assert(has("Level 70 |cff8cbaff(3)|r Wizard"), "and the header still draws")
assert(by[100].icon.texture == "icon6006", "the old potion cell still fills the potion slot")
assert(by[100].filled == true, "the potion slot is filled from it")
assert(colourOf(number("int")) == colourOf(number("str")), "no mainStat, so nothing is highlighted (and nothing errors)")
assert(#find("^DiablocraftInvCell") == 0, "and no grid appears")
-- The old server's Refresh handler ignores the extra argument; the sheet still asks.
sent = {}
watcher.scripts.OnEvent(watcher, "PLAYER_EQUIPMENT_CHANGED")
watcher.scripts.OnUpdate(watcher, 1)
local asks = sentNamed("Refresh")
assert(#asks == 1 and asks[1][1] == 2, "every Refresh carries the sheet's marker")

-- ------------------------------------------- header: Level N (Paragon), Paragon button

local function headerStrings()
    strings = {}
    for _, made in ipairs(fsOf(panel)) do strings[#strings + 1] = made.text end
end
panel:Hide(); DC.Inventory_Open()
handlers.Snapshot(nil, snapshot({paragon = 0}))
headerStrings()
assert(has("Level 70 Wizard"), "Paragon 0 shows Level N alone, no brackets")
handlers.Snapshot(nil, snapshot({paragon = 200}))
headerStrings()
assert(has("Level 70 |cff8cbaff(200)|r Wizard"), "Paragon 200 is Level 70 (200), the bracket in the Paragon colour")
assert(not has("Paragon 200"), "the old 'Paragon 200' text is gone")
local opened = 0
_G.DiablocraftOpenParagon = function() opened = opened + 1 end
press(_G.DiablocraftInventoryParagon)
assert(opened == 1, "the Paragon button opens the Paragon page")

-- The N key: Bindings.xml carries the entry, and Toggle Paragon puts a shown page away.
local bindings = assert(io.open("client-patch/addons/Torment/Bindings.xml")):read("*a")
assert(bindings:find('<Binding name="TORMENT_PARAGON"', 1, true) and bindings:find("Diablocraft.ToggleParagon()", 1, true),
    "Bindings.xml: Toggle Paragon runs Diablocraft.ToggleParagon")
assert(_G.BINDING_NAME_TORMENT_PARAGON == "Toggle Paragon" and _G.BINDING_HEADER_TORMENT == "Torment",
    "and its Key Bindings words exist")
local page = {shown = true, IsShown = function(self) return self.shown end, Hide = function(self) self.shown = false end}
_G.DiablocraftParagonFrame = page
opened = 0
DC.ToggleParagon()
assert(page.shown == false and opened == 0, "N on a shown page puts it away")
DC.ToggleParagon()
assert(opened == 1, "N on a hidden page asks for it")
_G.DiablocraftParagonFrame = nil
DC.ToggleParagon()
assert(opened == 2, "and with no page yet (an old server's Lua) it still asks, as the button does")

-- N is bound by default ONLY when the player has not bound it to something else.
local bound, saved = {}, 0
_G.GetBindingAction = function(key) return bound[key] or "" end
_G.SetBinding = function(key, action) bound[key] = action; return 1 end
_G.SaveBindings = function() saved = saved + 1 end
_G.GetCurrentBindingSet = function() return 1 end
local function login(initial)
    bound = {N = initial}; saved = 0; _G.DiablocraftUI = {}
    watcher.scripts.OnEvent(watcher, "PLAYER_LOGIN")
end
login("TOGGLETALENTS")
assert(bound.N == "TORMENT_PARAGON" and saved == 1, "stock N (talents, removed) becomes Toggle Paragon and is saved")
login(nil)
assert(bound.N == "TORMENT_PARAGON", "an unbound N becomes Toggle Paragon")
login("MOVEFORWARD")
assert(bound.N == "MOVEFORWARD" and saved == 0, "a player's own binding on N is left alone")
login("TOGGLETALENTS")
bound.N = nil   -- the player unbinds it afterwards
saved = 0
watcher.scripts.OnEvent(watcher, "PLAYER_LOGIN")
assert(bound.N == nil and saved == 0, "decided once: a later login never takes N back")

-- ---------------------------------------- the stash is open: right-click deposits

-- Order: the Jeweler's claim > the stash (deposit) > sheet/potion equip > stock.
panel:Hide(); DC.Inventory_Open()
handlers.Snapshot(nil, snapshot({potionEntries = {7006}}))
DC.Inventory_ScanPotionButtons()
bagItems = {[3] = "item:7006", [4] = "item:7004", [1] = "item:7004", [2] = "item:7004", [6] = "item:7004"}
_G.stashOpen = true
_G.deposits = {}
sent = {}
local blanked = click(button3)
assert(#_G.deposits == 1 and _G.deposits[1] == 25500 + 3 + 22, "stash open: a right-click on a bag item deposits that bag index")
assert(#sentNamed("Equip") == 0, "stash open: a potion is NOT equipped too")
assert(blanked == 5 and button3.id == 3, "and the stock click is pointed at an empty cell for that click, then restored")
_G.deposits = {}
bagItems[5] = "item:7004"
assert(click(button3) == 7 and #_G.deposits == 1, "a full bag: still deposited, the stock click blanked past the last slot")
bagItems[5] = nil
_G.deposits = {}
local empty = bagButton(5)
DC.Inventory_ScanPotionButtons()
assert(click(empty) == 5 and #_G.deposits == 0, "an empty cell deposits nothing")
claim = true
_G.deposits = {}
assert(click(button3) == 3 and #_G.deposits == 0 and #sentNamed("Equip") == 0, "the Jeweler's claim beats the stash: this hook does nothing")
claim = false
combat = true
assert(click(button3) == 3 and #_G.deposits == 0, "never in combat")
combat = false
shift = true
assert(click(button3) == 3 and #_G.deposits == 0, "a modified click is left alone")
shift = false
cursor = {item = items.helm}
assert(click(button3) == 3 and #_G.deposits == 0, "and so is one with an item on the cursor")
cursor = nil

-- A worn item on the sheet: deposited into the open tab; the Jeweler's claim still first.
worn[1] = {texture = "helmicon", link = items.helm.link}
DC.Inventory_DrawSlots()
sent = {}; _G.deposits = {}
press(by[0], "RightButton")
assert(#_G.deposits == 1 and _G.deposits[1] == 25500 and #sentNamed("Unequip") == 0,
    "stash open: a right-click on a worn item deposits it (25500 + its slot) instead of taking it off")
claim = true; _G.deposits = {}
press(by[0], "RightButton")
assert(#_G.deposits == 0 and #sentNamed("Unequip") == 0, "the Jeweler's claim beats the stash here too")
claim = false
_G.stashOpen = false
_G.deposits = {}
press(by[0], "RightButton")
assert(#_G.deposits == 0 and #sentNamed("Unequip") == 1, "stash closed: the right-click takes it off, as before")
sent = {}
assert(click(button3) == 5 and #sentNamed("Equip") == 1 and #_G.deposits == 0, "stash closed: a potion is equipped, as before")

-- ------------------------------------- the resource row names the class's resource

-- UI fixes row 8 (ruling 2026-10-03): the Resource group's maximum is the class's
-- own primary resource, named from the generated ResourceNames.lua (Fury for a
-- Barbarian, Arcane Power for a Wizard), not "Maximum Fury" for every class. A
-- class the list does not carry gets the client's own word for its power.
dofile("client-patch/addons/Torment/ResourceNames.lua")
local function resourceRow()
    DC.Details_Redraw()
    local found
    for _, made in ipairs(frames) do
        local row = made.shown and fsOf(made) or nil
        local label = row and row[1] and row[1].text
        if label and label:find("^Maximum ") and label ~= "Maximum Life" then
            assert(not found, "one resource maximum row, got " .. tostring(found) .. " and " .. label)
            found = label
        end
    end
    return found
end
local stockClass, stockPower, stockMana = _G.UnitClass, _G.UnitPowerType, _G.MANA
_G.UnitClass = function() return "Wizard", "MAGE" end
_G.UnitPowerType = function() return 3, "ENERGY" end
assert(resourceRow() == "Maximum Arcane Power", "a Wizard's row, got " .. tostring(resourceRow()))
_G.UnitClass = function() return "Barbarian", "WARRIOR" end
_G.UnitPowerType = function() return 1, "RAGE" end
assert(resourceRow() == "Maximum Fury", "a Barbarian's row, got " .. tostring(resourceRow()))
_G.UnitClass = function() return "Priest", "PRIEST" end
_G.UnitPowerType = function() return 0, "MANA" end
_G.MANA = "Mana"
assert(resourceRow() == "Maximum Mana", "a class with no row gets the client's word, got " .. tostring(resourceRow()))
_G.MANA = nil
assert(resourceRow() == "Maximum Resource", "and with no word at all, a neutral one, got " .. tostring(resourceRow()))
_G.UnitClass, _G.UnitPowerType, _G.MANA = stockClass, stockPower, stockMana

-- ------------------------------------- the shared window look (DC.Style)

-- Ruling 2026-10-01 (restyle): the sheet takes its backdrop from the addon's
-- shared Diablocraft.Style when it is there. Everything above loaded the file
-- with a stub Diablocraft that has no Style, so it exercised the fallback copy
-- that the Jeweler pin checks; load it again with the shared table and the sheet
-- must READ it rather than draw its own.
_G.Diablocraft.Style = {backdrop = {bgFile = "Interface\\Marker", edgeFile = "Interface\\Marker"}}
dofile("client-patch/addons/Torment/Inventory.lua")
DC.Inventory_OnLoad(panel)
assert(panel.backdrop and panel.backdrop.bgFile == "Interface\\Marker",
    "a sheet loaded with the addon's shared DC.Style must use it, got "
        .. tostring(panel.backdrop and panel.backdrop.bgFile))
_G.Diablocraft.Style = nil

print("test_character_sheet: ok")
