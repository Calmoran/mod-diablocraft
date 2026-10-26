-- luacheck: ignore 111 112 113 121 122 211 212 213 411 431 432
-- Run from repo root with lua52_interpreter.exe.
--
-- The stash screen's INPUT half (client-patch/addons/Torment/Stash.lua)
-- against a stub 3.3.5a API. test_panel_kit.lua already covers the border the
-- same file draws; this covers what the file sends, which is the part a bad
-- change makes silently wrong:
--
--   * this window builds NO bag grid of its own and opens the player's BAGS
--     (ElvUI's) beside itself instead - the bags are the one inventory in this
--     game (ruling 2026-10-01; decisions.md, superseding 2026-09-15);
--   * a drag from a stash slot sends Move with an EXPLICIT destination index -
--     never AUTO, which is the right-click quick-move and lets the server pick;
--   * a drop on a TAB button moves the item into that tab's first free slot;
--   * a cancelled drag sends NOTHING and puts the icon back;
--   * a locked tab refuses through the status line rather than silently;
--   * right-click still sends AUTO, and the click-select-then-click path is
--     GONE: a left-click sends nothing at all (ruling 2026-09-15).
--
-- Every direction that crosses between the stash and the bags - the stock cursor
-- in, the virtual cursor out onto an ElvUI bag slot - is in test_item_dragging.lua.
--
-- Nothing here tests the server. dc_stash.cpp owns every rule; the addon only
-- echoes back indices it was given, and this pins which ones.

local sent = {}
local AUTO = -1

-- ---------------------------------------------------------------- stub client

-- The 3.3.5a widget layer is the ONE shared strict mock (diablocraft-yey2).
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)

-- Stash.xml's three button templates: what the client builds from a virtual template before
-- the addon's OnLoad runs. The shared mock models the widget API, not the XML templates, so
-- this test's template layer sits on top of Mock.widget: the template's own size, its named
-- child regions, its HighlightTexture, and the template OnLoad the client runs as the frame
-- is made. Every slot and tab in Stash.lua is placed with
-- SetPoint("TOPLEFT", parent, "TOPLEFT", x, y), which the mock's geometry resolves.
local TEMPLATES = {
    DiablocraftSlotTemplate = {size = {34, 34}, onLoad = "Slot_OnLoad", parts = {
        {"Back", "BACKGROUND"}, {"Rarity", "BORDER"}, {"Icon", "ARTWORK"},
        {"Count", "OVERLAY", "NumberFontNormalSmall", "FontString"},
        {"Select", "OVERLAY", nil, "Texture", true},
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

-- The cursor the addon reads. Screen units at scale 1, so one number each way.
local cursor = {x = -999, y = -999}
_G.GetCursorPosition = function() return cursor.x, cursor.y end

-- AIO, reduced to "what did the addon send".
local handlers = {}
-- Shift-click shares a rolled item (decisions.md 2026-09-26): the client's own
-- modified-click test, off unless a check turns it on.
local chatLinkHeld, requestedLinks = false, {}
_G.IsModifiedClick = function(action) return chatLinkHeld and action == "CHATLINK" end
_G.DCRequestItemLink = function(guid) requestedLinks[#requestedLinks + 1] = guid end

_G.AIO = {
    AddHandlers = function() return handlers end,
    Handle = function(_, name, ...) sent[#sent + 1] = {name = name, ...} end,
}

-- The addon reuses an existing Diablocraft table, so the shared economy surface
-- is put in before the file is loaded. Nothing else is stubbed: the art table,
-- the panel kit and the grids are the real ones.
_G.Diablocraft = {
    Econ = {
        MATERIALS = {{entry = 102000, name = "Death's Breath"}},
        Gold = function(value) return tostring(value) end,
        Balance = function() return "1234" end,
        Material = function() return "7" end,
        OnChange = function() end,
    },
}
_G.require = nil
-- Stash.lua hooks these two stock cursor calls: the
-- client has them as functions and the mock refuses to hook a name that is not one.
_G.PickupContainerItem = function() end
_G.PickupInventoryItem = function() end

dofile("mod-diablocraft/scripts/dc_addon_core.lua")
local DC = _G.Diablocraft

-- The frame the XML would have built, and the two font strings it declares.
local frame = Mock.widget("Frame", "DiablocraftStashFrame", Mock.UIParent)
frame:Hide()  -- the XML's own hidden="true"
-- The XML text, each with its template font: the mock refuses SetText on a FontString
-- with no font, as the client does (dc_widget_mock rule 5, diablocraft-scog).
Mock.widget("FontString", "DiablocraftStashFrameStatus", nil, "GameFontHighlightSmall")
Mock.widget("FontString", "DiablocraftStashFrameGold", nil, "GameFontNormal")
DC.Frame_OnLoad(frame)
-- The XML's own <OnHide>, which the stub does not parse.
frame:SetScript("OnHide", DC.Frame_OnHide)

-- (1) The player's bags, which the stash now opens beside itself. ElvUI's bag
-- frame is ElvUI_ContainerFrame; the stock one is ContainerFrame1. Only the
-- three globals Stash.lua calls are stubbed.
local bagFrame = Mock.widget("Frame", "ElvUI_ContainerFrame", Mock.UIParent)
-- A rectangle of its own: the stash now anchors to it, so its slots are placed off it.
bagFrame._rect = {600, 700, 0, 0}
bagFrame:Hide()
local opened, closed = 0, 0
_G.OpenAllBags = function() opened = opened + 1; bagFrame:Show() end
_G.CloseAllBags = function() closed = closed + 1; bagFrame:Hide() end

-- ------------------------------------------------------------- the snapshot

-- Tab 1 holds two items; the account has two of five tabs. The snapshot carries
-- no bag cells: the bags are ElvUI's.
local function item(entry, guid)
    return {entry = entry, count = 1, colour = "orange", guid = guid, name = "Item " .. entry,
            link = "|Hitem:" .. entry .. "|h"}
end

handlers.Snapshot(nil, {
    note = "open",
    revision = "1",
    gold = "1234",
    tabs = {granted = 2, max = 5, prices = {}},
    layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10},
    stash = {[0] = item(1000, 100), [3] = item(1001, 101)},
})

local stashSlot = function(position) return _G["DiablocraftStashSlot" .. position] end
local tab = function(index) return _G["DiablocraftStashTab" .. index] end

assert(frame:IsShown(), "the snapshot opens the window")
assert(stashSlot(1).cell.entry == 1000, "stash slot 1 drew the first item")
assert(stashSlot(4).cell.entry == 1001, "stash slot 4 drew the second item")

-- (1) There is ONE inventory and it is ElvUI's bags. The second grid this window
-- used to build is gone, the snapshot carries none, and opening the stash opens
-- the bags beside it.
assert(_G.DiablocraftBagSlot1 == nil, "the stash builds no bag grid of its own")
assert(_G.DiablocraftBagSlot60 == nil, "not one cell of it")
assert(opened == 1 and bagFrame:IsShown(), "opening the stash opens the bags")
-- PM ruling A (2026-10-03, diablocraft-stash-look): its right edge touches the bag frame's
-- left edge, no overlap. test_stash_look.lua covers the stock-bags fallback.
local anchor = {frame:GetPoint(1)}
assert(anchor[2] == bagFrame and anchor[1] == "RIGHT" and anchor[3] == "LEFT" and anchor[4] == 0 and anchor[5] == 0,
    "and the stash sits flush against the left of the bag frame")
assert(DC.SendMove == nil, "the stash no longer lends its Move to a second screen")

-- --------------------------------------------------------------- the harness

local function centre(button)
    return button:GetLeft() + button:GetWidth() / 2, button:GetTop() - button:GetHeight() / 2
end

local function lastSent()
    return sent[#sent]
end

local function drag(from, to)
    local before = #sent
    DC.Slot_OnDragStart(from)
    local dragging = _G.DiablocraftStashDrag:IsShown()
    if to then cursor.x, cursor.y = centre(to) else cursor.x, cursor.y = -999, -999 end
    DC.Slot_OnDragStop(from)
    return before, dragging
end

-- Every slot and tab is where the mock can find it, or the drops below would
-- pass by resolving nothing.
for _, button in ipairs({stashSlot(1), stashSlot(4), stashSlot(8), tab(3)}) do
    assert(button:GetLeft() and button:GetTop(), (button:GetName() or "?") .. " has a rectangle")
    assert(button.drag == nil or button.drag[1] == "LeftButton", "a slot drags on LeftButton only")
end

-- --------------------------------------------------- (d) drag sends the index

-- Stash to stash: the move that (a) made impossible, and the reason drag looked
-- like it was missing rather than broken.
local before = drag(stashSlot(1), stashSlot(4))
assert(#sent == before + 1, "a drag onto another slot sends exactly one message")
local message = lastSent()
assert(message.name == "Move", "it sends Move, got " .. tostring(message.name))
assert(message[1] == "stash" and message[2] == 0, "from the stash slot the icon was picked up in")
assert(message[3] == "stash" and message[4] == 3, "to the stash slot it was dropped on")
assert(message[4] ~= AUTO, "the destination is explicit, never AUTO")

-- Two rows down, still explicit: the row-major index the grid drew.
before = drag(stashSlot(1), stashSlot(11))
message = lastSent()
assert(#sent == before + 1 and message.name == "Move", "a drop two rows down sends Move")
assert(message[1] == "stash" and message[2] == 0 and message[3] == "stash" and message[4] == 10,
    "with the index that cell carries")

-- Dropping on an occupied slot is the same message as dropping on an empty one;
-- the swap is the server's business (dc_stash.cpp Move).
before = drag(stashSlot(4), stashSlot(1))
message = lastSent()
assert(#sent == before + 1 and message[2] == 3 and message[4] == 0, "a drop on an occupied slot swaps")

-- ------------------------------------------------------- a cancelled drag

-- Outside the frame.
before = drag(stashSlot(1), nil)
assert(#sent == before, "a drag dropped outside the frame sends nothing")
assert(not _G.DiablocraftStashDrag:IsShown(), "and the icon is put back")

-- On itself.
before = drag(stashSlot(1), stashSlot(1))
assert(#sent == before, "a drag dropped on its own slot sends nothing")

-- On an empty slot the drag never started from: an empty slot carries nothing.
before = #sent
DC.Slot_OnDragStart(stashSlot(2))
assert(not _G.DiablocraftStashDrag:IsShown(), "an empty slot does not start a drag")
cursor.x, cursor.y = centre(stashSlot(1))
DC.Slot_OnDragStop(stashSlot(2))
assert(#sent == before, "and dropping that non-drag sends nothing")

-- ------------------------------------------------- refusals, not silence

local status = _G.DiablocraftStashFrameStatus

status:SetText("")
before = drag(stashSlot(1), tab(3))
assert(#sent == before, "a drop on a locked tab sends nothing")
assert(status:GetText() and status:GetText():find("locked"), "and says so: " .. tostring(status:GetText()))

-- (2) A drop on an UNLOCKED tab moves the item into that tab (the designer,
-- 2026-09-15). Tab 2 is slots 70-139 and is empty, so the destination is 70.
status:SetText("")
before = drag(stashSlot(1), tab(2))
message = lastSent()
assert(#sent == before + 1 and message.name == "Move", "a drop on tab 2 sends Move")
assert(message[1] == "stash" and message[2] == 0, "from the slot the drag started in")
assert(message[3] == "stash" and message[4] == 70, "into tab 2's first free slot, explicitly")
assert(message[4] ~= AUTO, "never AUTO: the addon names the slot it can see is free")

-- Tab 1 holds items at 0 and 3, so its first free slot is 1, not 0.
status:SetText("")
before = drag(stashSlot(4), tab(1))
message = lastSent()
assert(#sent == before + 1 and message[2] == 3 and message[4] == 1,
    "and it is the FIRST free slot, not simply the tab's first")

-- ------------------------------------------- the icon follows the cursor

DC.Slot_OnDragStart(stashSlot(1))
local carrier = _G.DiablocraftStashDrag
assert(carrier:IsShown(), "the drag frame is up while a drag is held")
cursor.x, cursor.y = 321, 654
carrier.scripts.OnUpdate(carrier)
local placed = {carrier:GetPoint(1)}
assert(placed[1] == "CENTER" and placed[3] == "BOTTOMLEFT", "the icon is anchored to the cursor")
assert(placed[4] == 321 and placed[5] == 654, "at the cursor's own position")
cursor.x, cursor.y = 120, 240
carrier.scripts.OnUpdate(carrier)
placed = {carrier:GetPoint(1)}
assert(placed[4] == 120 and placed[5] == 240, "and it follows")
cursor.x, cursor.y = -999, -999
DC.Slot_OnDragStop(stashSlot(1))
assert(not carrier:IsShown(), "and is put away when the drag ends")

-- Escape closes the window mid-drag, and OnDragStop never arrives.
DC.Slot_OnDragStart(stashSlot(1))
assert(carrier:IsShown(), "a drag is held")
frame:Hide()
assert(not carrier:IsShown(), "hiding the window puts the icon away")
frame:Show()
before = #sent
cursor.x, cursor.y = centre(stashSlot(4))
DC.Slot_OnDragStop(stashSlot(1))
assert(#sent == before, "and the abandoned drag sends nothing when it is released")

-- --------------------------------------- right-click, and only right-click

-- Right-click: the quick-move to the other container, with the destination NAMED. Dev's
-- log showed every drag arriving and no right-click at all, so the move that leaves the
-- choice to the server (AUTO) is not used any more: the first empty bag cell is found
-- from the stock bag API, backpack first, in the server's numbering.
local bagLinks = {}
_G.GetContainerNumSlots = function(bag) return bag == 0 and 4 or (bag == 1 and 3 or 0) end
_G.GetContainerItemLink = function(bag, slot) return bagLinks[bag .. ":" .. slot] end
bagLinks["0:1"], bagLinks["0:2"] = "item:1", "item:2"
before = #sent
DC.Slot_OnClick(stashSlot(1), "RightButton")
message = lastSent()
assert(#sent == before + 1 and message.name == "Move", "right-click still sends Move")
assert(message[1] == "stash" and message[2] == 0 and message[3] == "bag", "from that stash cell to the bags")
assert(message[4] == 255 * 100 + 25 and message[4] ~= AUTO, "to the first empty backpack cell (slot 3), named, never AUTO")
bagLinks["0:3"], bagLinks["0:4"] = "item:3", "item:4"
DC.Slot_OnClick(stashSlot(1), "RightButton")
message = lastSent()
assert(message[4] == 19 * 100, "with the backpack full it walks to the first carried bag's first cell")
for slot = 1, 3 do bagLinks["1:" .. slot] = "item:9" end
before = #sent
_G.DiablocraftStashFrameStatus:SetText("")
DC.Slot_OnClick(stashSlot(1), "RightButton")
assert(#sent == before, "every cell taken: nothing is sent")
assert(_G.DiablocraftStashFrameStatus:GetText() == "Your bags are full.", "and the status line says so")
bagLinks = {}

-- The click-select-then-click path is GONE (ruling 2026-09-15: "I'm not sure why
-- we're trying to make this so convoluted with shift right click to grab, click
-- one item into another slot with another click, its wrong"). A left-click sends
-- nothing, however many times it is pressed: there is no state behind it now.
before = #sent
DC.Slot_OnClick(stashSlot(1), "LeftButton")
DC.Slot_OnClick(stashSlot(4), "LeftButton")
DC.Slot_OnClick(stashSlot(1), "LeftButton")
assert(#sent == before, "left-clicking sends nothing at all")
for _, position in ipairs({1, 4}) do
    assert(stashSlot(position).select.shown == false, "and lights nothing up")
end

-- Shift-left-click asks for the item's link instead, and still moves nothing.
local linkCell = stashSlot(1).cell
linkCell.guid = linkCell.guid or 4242
chatLinkHeld = true
before = #sent
DC.Slot_OnClick(stashSlot(1), "LeftButton")
chatLinkHeld = false
assert(#requestedLinks == 1 and requestedLinks[1] == linkCell.guid, "shift-click requests the item link")
assert(#sent == before, "and sends no move")

-- ------------------------------------------------------- what the XML says

local xml = assert(io.open("client-patch/addons/Torment/Stash.xml")):read("*a")
local slot = xml:match('<Button name="DiablocraftSlotTemplate".-</Button>')
assert(slot, "the slot template is declared")
assert(slot:find("Diablocraft.Slot_OnDragStart", 1, true), "the slot template runs Slot_OnDragStart")
assert(slot:find("Diablocraft.Slot_OnDragStop", 1, true), "the slot template runs Slot_OnDragStop")
assert(slot:find("Diablocraft.Slot_OnReceiveDrag", 1, true),
    "and is a real drop target for the stock cursor too (ruling 2026-09-15)")
assert(slot:find("Diablocraft.Slot_OnClick", 1, true), "and still runs Slot_OnClick")
local tabTemplate = xml:match('<Button name="DiablocraftTabTemplate".-</Button>')
assert(tabTemplate and tabTemplate:find("Diablocraft.Tab_OnReceiveDrag", 1, true),
    "the tab template is a drop target too")
assert(not xml:find("Stash &amp; Inventory", 1, true),
    "the window is the Stash; the inventory is its own screen")
assert(stashSlot(1).drag and stashSlot(1).drag[1] == "LeftButton",
    "Slot_OnLoad registers the left button for drag")

-- ------------------------------------------- the bags, opened and closed

local function reopen(revision)
    handlers.Snapshot(nil, {
        note = "open",
        revision = revision,
        gold = "1234",
        tabs = {granted = 2, max = 5, prices = {}},
        layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10},
        stash = {[0] = item(1000, 100)},
    })
end

-- Closing the stash puts away the bags THIS window opened.
frame:Hide()
bagFrame:Hide()
opened, closed = 0, 0
reopen("2")
assert(frame:IsShown() and opened == 1, "the snapshot opens both")
frame:Hide()
assert(closed == 1 and not bagFrame:IsShown(), "closing the stash closes the bags it opened")

-- Bags the player already had open are left exactly where they were.
bagFrame:Show()
opened, closed = 0, 0
reopen("3")
assert(frame:IsShown(), "the snapshot opens the stash again")
assert(opened == 0, "bags already open are not opened again")
frame:Hide()
assert(closed == 0 and bagFrame:IsShown(), "and are NOT closed with the stash, because it did not open them")

-- ----------------------------------- the tab column follows the server's tabs.max

local function withTabs(granted, max)
    handlers.Snapshot(nil, {
        note = "open",
        revision = "9",
        gold = "1234",
        tabs = {granted = granted, max = max, prices = {}},
        layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10},
        stash = {},
    })
end

-- economy.stash_max_tabs is a tunable: with six, the window draws six tab buttons
-- and says "BUY TAB 3" rather than stopping at the five it was built with.
withTabs(2, 6)
assert(tab(6) and tab(6).tab == 6, "a sixth tab button is built when the server allows six")
assert(tab(6).shown and not tab(6).unlocked, "and it is drawn locked until it is bought")
local function buyButton()
    for _, created in ipairs(frames) do
        if created.template == "UIPanelButtonTemplate" then return created end
    end
end
assert(buyButton().text == "BUY TAB 3", "the buy button names the next tab")
withTabs(6, 6)
assert(buyButton().text == "ALL TABS", "all six bought: nothing left to buy")
assert(tab(6).unlocked, "tab six is open once granted")
DC.BuyTab_OnEnter({})
assert(_G.GameTooltip.lines[1] == "All 6 stash tabs are yours.", "the tooltip counts the tabs, it does not say five: " .. tostring(_G.GameTooltip.lines[1]))

-- With three, tabs four and five are not there at all, and three is the last one.
withTabs(3, 3)
assert(tab(3).shown and not tab(4).shown and not tab(5).shown, "tabs beyond the server's maximum are hidden")
assert(buyButton().text == "ALL TABS", "three of three is all of them")
withTabs(2, 5)
assert(tab(4).shown and tab(5).shown, "and they come back when the maximum does")

-- ------------------------------------------ the Jeweler's look, from DC.Style

-- The window wears the shared dialog backdrop and nothing of the Torment frame: no nine-piece
-- border, no banner. Its close and buy buttons are the two native frames DC.Style makes.
assert(frame.backdrop == DC.Style.backdrop, "the stash frame wears the shared dialog backdrop")
assert(frame.backdrop.bgFile == "Interface\\DialogFrame\\UI-DialogBox-Background",
    "and that is the stock dialog the Jeweler draws")
for _, created in ipairs(frames) do
    assert(not (created.name or ""):find("PanelFrame", 1, true), "no Torment panel piece is built: " .. tostring(created.name))
end
local closes, buttons = {}, {}
for _, created in ipairs(frames) do
    if created.template == "UIPanelCloseButton" then closes[#closes + 1] = created end
    if created.template == "UIPanelButtonTemplate" then buttons[#buttons + 1] = created end
end
assert(#closes == 1 and closes[1].parent == frame, "one native close button, on the stash frame")
local close = {closes[1]:GetPoint(1)}
assert(close[1] == "TOPRIGHT" and close[4] == -6 and close[5] == -6,
    "six pixels in from the top right corner, as DC.Style.Close places it")
assert(closes[1].scripts.OnClick, "and it runs the stash's own close, which tells the server")
assert(#buttons == 1 and buttons[1].parent == frame and buttons[1]:GetHeight() == 22,
    "one native button, at the dialog's own height")
xml = io.open("client-patch/addons/Torment/Stash.xml"):read("*a")
assert(not xml:find("TitleBar", 1, true), "the banner is gone from the XML")
assert(not xml:find('name="$parentClose"', 1, true) and not xml:find("Close_OnLoad", 1, true),
    "and so is the Torment X button")
assert(not xml:find('name="$parentBuyTab"', 1, true), "and the art button; the buy button is built in Lua")
assert(DC.Close_OnLoad == nil, "nothing wears the Torment X art any more")

-- Member by member: a DC.Style that carries only part of the helper still draws the right window.
local savedStyle, savedCount = DC.Style, #frames
DC.Style = {}   -- an addon file that declared a table and nothing in it
local bare = Mock.widget("Frame", "DiablocraftStashFrame2", Mock.UIParent)
bare:Hide()
DC.Frame_OnLoad(bare)
assert(bare.backdrop and bare.backdrop.bgFile == "Interface\\DialogFrame\\UI-DialogBox-Background",
    "with no shared backdrop the same stock dialog is used")
local natives = 0
for index = savedCount + 1, #frames do
    if frames[index].template == "UIPanelCloseButton" or frames[index].template == "UIPanelButtonTemplate" then
        natives = natives + 1
    end
end
assert(natives == 2, "and the same two native frames are built without the helper, got " .. natives)
-- And a member that IS there wins: the stash takes the shared helper, it does not carry its own.
local sentinel, usedClose, usedButton = {bgFile = "shared"}, 0, 0
DC.Style = {
    backdrop = sentinel,
    Close = function(parent) usedClose = usedClose + 1; return Mock.widget("Button", nil, parent) end,
    Button = function(parent) usedButton = usedButton + 1; return Mock.widget("Button", nil, parent) end,
}
local shared = Mock.widget("Frame", "DiablocraftStashFrame3", Mock.UIParent)
shared:Hide()
DC.Frame_OnLoad(shared)
assert(shared.backdrop == sentinel and usedClose == 1 and usedButton == 1,
    "a shared backdrop, Close and Button are the ones the stash uses")
DC.Style = savedStyle

print("Stash client checks passed (bags beside the stash, tab drops, no click-select, tabs follow tabs.max, the Jeweler's look)")
