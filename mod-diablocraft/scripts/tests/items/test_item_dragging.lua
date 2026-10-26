-- Run from the repo root: lua5.1 mod-diablocraft/scripts/tests/items/test_item_dragging.lua
--
-- Moving items between the stash and the player's bags, bead
-- diablocraft-inventory-grid-removal. The bags are ElvUI's now, and the stock
-- cursor carries every drag that starts in a bag or on a worn slot. The one drag
-- that cannot use it is a drag that STARTS in the stash: a stash item is parked in
-- the database, in no container, so CursorHasItem() can never be true for it. So
-- Stash.lua keeps a virtual cursor for stash-origin drags only. Pinned here:
--
--   * the virtual cursor starts for a stash cell and for nothing else, and the
--     handlers of the old grid, the gem socket, and the worn-slot drop are gone;
--   * stash -> bags: a stash drag released over an ElvUI bag slot sends Move to
--     exactly that cell, with the server's own numbering (bag 0 is the backpack at
--     255, slot + 22; bags 1-4 are containers 19-22, slot - 1); the stock
--     ContainerFrameNItemM buttons work the same; released over the world it
--     sends nothing;
--   * bags -> stash: the stock cursor, with the bag it was picked up from
--     remembered by the pickup hook, dropped on a stash slot or a stash tab, sends
--     Move with an explicit destination and puts the cursor away;
--   * a worn item on the stock cursor is not a bag item: dropped on the stash it
--     is refused with a line of text and nothing is sent;
--   * stash -> stash is unchanged, and so is the right-click quick-move.
-- luacheck: ignore 122 431 143

local sent = {}
local AUTO = -1

-- ---------------------------------------------------------------- stub client

-- The widget layer is the ONE shared strict mock (diablocraft-yey2): unknown
-- methods, wrong argument counts and a readable .width all fail here as they do
-- in the game.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)

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
-- The first Stash.lua load already hooks these two stock cursor calls
-- (Stash.lua, the hooksecurefunc pair); the client has them as functions and the mock refuses
-- to hook a name that is not one. They are replaced lower down with the real cursor.
_G.PickupContainerItem = function() end
_G.PickupInventoryItem = function() end

dofile("mod-diablocraft/scripts/dc_addon_core.lua")
local DC = _G.Diablocraft

-- The frame the XML would have built, and the regions it declares.
local function newStash()
    local frame = Mock.widget("Frame", "DiablocraftStashFrame", _G.UIParent)
    -- The XML text, each with its template font: the mock refuses SetText on a FontString
    -- with no font, as the client does (dc_widget_mock rule 5, diablocraft-scog).
    Mock.widget("FontString", "DiablocraftStashFrameStatus", nil, "GameFontHighlightSmall")
    Mock.widget("FontString", "DiablocraftStashFrameGold", nil, "GameFontNormal")
    Mock.widget("FontString", "DiablocraftStashFrameBuyTabLabel", nil, "GameFontNormal")
    Mock.widget("Texture", "DiablocraftStashFrameTitleBar")
    Mock.widget("Texture", "DiablocraftStashFrameCoin")
    DC.Frame_OnLoad(frame)
    -- The XML's own <OnHide>, which the mock does not parse.
    frame:SetScript("OnHide", DC.Frame_OnHide)
    return frame
end

-- The XML templates the stash's slots, tabs and button are built from: the
-- client makes each template's named parts, font and all, and runs its OnLoad as
-- the frame is created. The mock makes widgets, not XML, so the test does that
-- step here, in creation order - every 34x34 slot and 40x40 tab, at the size the
-- XML gives it, is what a drop lands on. The parts and their font templates are
-- the XML's own (Stash.xml), which is also what the mock's font rule requires.
local TEMPLATES = {
    DiablocraftSlotTemplate = {34, 34, {Back = "Texture", Rarity = "Texture", Icon = "Texture",
        Count = "NumberFontNormalSmall", Select = "Texture"}, "Slot_OnLoad"},
    DiablocraftTabTemplate = {40, 40, {Back = "Texture", Label = "GameFontNormal"}, "Tab_OnLoad"},
    DiablocraftButtonTemplate = {170, 62, {Back = "Texture", Label = "GameFontNormal"}, "Button_OnLoad"},
}
local function instantiateTemplates()
    for _, f in ipairs(frames) do
        local spec = TEMPLATES[f.template]
        if spec and not f.dcTemplated then
            f.dcTemplated = true
            f:SetSize(spec[1], spec[2])
            for suffix, part in pairs(spec[3]) do
                if part == "Texture" then
                    f:CreateTexture(f:GetName() .. suffix)
                else
                    f:CreateFontString(f:GetName() .. suffix, "OVERLAY", part)
                end
            end
            DC[spec[4]](f)
        end
    end
end

newStash()

-- The stock bag buttons and the world, for GetMouseFocus.
local focus = nil
_G.GetMouseFocus = function() return focus end
local cursorItem = false
_G.CursorHasItem = function() return cursorItem end
_G.GetCursorInfo = function() if cursorItem then return "item", 1, "link" end end
_G.ClearCursor = function() cursorItem = false end
_G.PickupContainerItem = function() cursorItem = true end
_G.PickupInventoryItem = function() cursorItem = true end

dofile("mod-diablocraft/scripts/dc_addon_core.lua")
DC = _G.Diablocraft

newStash()
instantiateTemplates()
-- Bags are not what is under test here; a stub frame so the stash can open them.
_G.OpenAllBags = function() end
_G.CloseAllBags = function() end

local function item(entry, guid)
    return {entry = entry, count = 1, colour = "orange", guid = guid, name = "Item " .. entry,
            link = "|Hitem:" .. entry .. "|h"}
end
handlers.Snapshot(nil, {
    note = "open", revision = "1", gold = "1234",
    tabs = {granted = 2, max = 5, prices = {}},
    layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10},
    stash = {[0] = item(1000, 100), [3] = item(1001, 101)},
})

local stashSlot = function(position) return _G["DiablocraftStashSlot" .. position] end
local tab = function(index) return _G["DiablocraftStashTab" .. index] end
local function centre(button)
    return button:GetLeft() + button:GetWidth() / 2, button:GetTop() - button:GetHeight() / 2
end
local function lastSent() return sent[#sent] end
local status = _G.DiablocraftStashFrameStatus

-- A stock-style bag button, as ElvUI builds one: bagID and slotID on the button.
local function elvuiSlot(bag, slot) return {bagID = bag, slotID = slot} end
-- A stock ContainerFrame button: its own id is the slot, its parent's the bag.
local function stockSlot(bag, slot)
    local parent = {GetID = function() return bag end}
    return {GetName = function() return "ContainerFrame" .. bag .. "Item" .. slot end,
            GetParent = function() return parent end, GetID = function() return slot end}
end

-- A drag out of the stash, released with the mouse over `over` (a frame of ours,
-- a bag button, or nothing).
local function dragFromStash(from, over, mouseFocus)
    local before = #sent
    DC.Slot_OnDragStart(from)
    local held = _G.DiablocraftStashDrag:IsShown()
    if over then cursor.x, cursor.y = centre(over) else cursor.x, cursor.y = -999, -999 end
    focus = mouseFocus
    DC.Slot_OnDragStop(from)
    focus = nil
    return before, held
end

-- ------------------------------------------------ the virtual cursor, trimmed

assert(DC.StartDrag("bag", {index = 25523, entry = 1, available = true}) == false,
    "a bag cell no longer starts a virtual drag: the stock cursor carries it")
assert(DC.StartDrag("equip", {index = 4, entry = 1, available = true}) == false,
    "neither does a worn slot")
assert(not _G.DiablocraftStashDrag:IsShown(), "and nothing is held after a refused start")
for _, gone in ipairs({"InvSlot_OnLoad", "InvSlot_OnClick", "InvSlot_OnDragStart", "InvSlot_OnReceiveDrag",
                       "EquipSlot_OnLoad", "EquipSlot_OnDragStart", "DropOnEquip", "SendSocket", "SendMove",
                       "Inventory_Status"}) do
    assert(DC[gone] == nil, gone .. " belonged to the grid and is gone")
end
local source = ""
for _, name in ipairs({"ArtSlots.lua", "PanelKit.lua", "WindowStyle.lua", "Stash.lua"}) do
    source = source .. assert(io.open("client-patch/addons/Torment/" .. name)):read("*a")
end
assert(not source:find("dropGemOn", 1, true) and not source:find("gem = cell.gem", 1, true),
    "the gem-onto-item drop is gone (Shift+Right-click and Socket Gems are the socket path)")

-- --------------------------------------------------------- stash to the bags

-- The server's numbering, from the client's: the one conversion.
assert(DC.BagIndex(0, 1) == 255 * 100 + 23, "backpack slot 1 is player slot 23")
assert(DC.BagIndex(0, 16) == 255 * 100 + 38, "backpack slot 16 is player slot 38")
assert(DC.BagIndex(1, 1) == 19 * 100, "the first carried bag's first cell is container 19, slot 0")
assert(DC.BagIndex(4, 22) == 22 * 100 + 21, "the fourth bag's 22nd cell is container 22, slot 21")
assert(DC.BagIndex(5, 1) == nil and DC.BagIndex(nil, 1) == nil and DC.BagIndex(0, nil) == nil,
    "a bag that is not a bag, and a half-known one, convert to nothing")

local before, held = dragFromStash(stashSlot(1), nil, elvuiSlot(0, 3))
assert(held, "the stash cell started a drag")
local message = lastSent()
assert(#sent == before + 1 and message.name == "Move", "released over an ElvUI bag slot it sends Move")
assert(message[1] == "stash" and message[2] == 0, "from the stash cell")
assert(message[3] == "bag" and message[4] == 255 * 100 + 25, "to that backpack slot, explicitly, got " .. tostring(message[4]))
assert(message[4] ~= AUTO, "never AUTO")
before = dragFromStash(stashSlot(4), nil, elvuiSlot(2, 5))
message = lastSent()
assert(#sent == before + 1 and message[2] == 3 and message[3] == "bag" and message[4] == 20 * 100 + 4,
    "a carried bag's cell: container 20, slot 4")
before = dragFromStash(stashSlot(1), nil, stockSlot(1, 7))
message = lastSent()
assert(#sent == before + 1 and message[3] == "bag" and message[4] == 19 * 100 + 6,
    "a stock ContainerFrame button works the same")
-- The world, a frame of someone else's, and an ElvUI button that is not a bag slot.
before = dragFromStash(stashSlot(1), nil, nil)
assert(#sent == before, "released over nothing it sends nothing")
before = dragFromStash(stashSlot(1), nil, {GetName = function() return "WorldFrame" end})
assert(#sent == before, "released over the world it sends nothing")
before = dragFromStash(stashSlot(1), nil, {bagID = 0})
assert(#sent == before, "a button with a bag and no slot is not a target")
before = dragFromStash(stashSlot(1), nil, elvuiSlot(255, 3))
assert(#sent == before, "and neither is the equipment pseudo-bag")
assert(not _G.DiablocraftStashDrag:IsShown(), "the icon is put away every time")
-- Stash targets still win over a bag button underneath them.
before = dragFromStash(stashSlot(1), stashSlot(4), elvuiSlot(0, 3))
message = lastSent()
assert(#sent == before + 1 and message[3] == "stash" and message[4] == 3, "a stash slot under the cursor is the target")

-- ---------------------------------------------------------- bags to the stash

local function pickup(bag, slot)
    _G.PickupContainerItem(bag, slot)
end

pickup(0, 3)
before = #sent
DC.Slot_OnReceiveDrag(stashSlot(4))
message = lastSent()
assert(#sent == before + 1 and message.name == "Move", "a bag item dropped on a stash slot sends Move")
assert(message[1] == "bag" and message[2] == 255 * 100 + 25, "from the bag the pickup hook remembered")
assert(message[3] == "stash" and message[4] == 3, "to that stash slot, explicitly")
assert(cursorItem == false, "and the cursor is put away")

pickup(3, 2)
before = #sent
DC.Tab_OnReceiveDrag(tab(2))
message = lastSent()
assert(#sent == before + 1 and message[1] == "bag" and message[2] == 21 * 100 + 1
    and message[3] == "stash" and message[4] == 70, "dropped on tab 2 it goes to that tab first free slot: " .. tostring(message[1]) .. "," .. tostring(message[2]) .. "," .. tostring(message[3]) .. "," .. tostring(message[4]))
-- A locked tab refuses by name.
pickup(0, 1)
before = #sent
status:SetText("")
DC.Tab_OnReceiveDrag(tab(3))
assert(#sent == before and status:GetText() and status:GetText():find("locked"), "a locked tab refuses with text")

-- An empty cursor, and a cursor that is not an item, send nothing.
cursorItem = false
before = #sent
DC.Slot_OnReceiveDrag(stashSlot(4))
DC.Tab_OnReceiveDrag(tab(2))
assert(#sent == before, "an empty cursor sends nothing")

-- A worn item (bag 255, slot below 23) now goes STRAIGHT into the stash, as one server
-- move: from index 25500 + its 0-based slot, onto an EMPTY slot or a tab.
_G.PickupInventoryItem(5)
before = #sent
status:SetText("")
DC.Slot_OnReceiveDrag(stashSlot(2))
message = lastSent()
assert(#sent == before + 1 and message.name == "Move" and message[1] == "bag" and message[2] == 25504
    and message[3] == "stash" and message[4] == 1, "a worn item dropped on an empty stash slot is one Move from 25500 + slot")
assert(cursorItem == false, "and the cursor is put away")
_G.PickupInventoryItem(5)
before = #sent
status:SetText("")
DC.Slot_OnReceiveDrag(stashSlot(4))
assert(#sent == before and status:GetText() and status:GetText():find("empty Stash slot"),
    "a worn item onto an OCCUPIED stash slot is refused (no swap with a worn item)")
_G.PickupInventoryItem(5)
before = #sent
DC.Tab_OnReceiveDrag(tab(2))
message = lastSent()
assert(#sent == before + 1 and message[1] == "bag" and message[2] == 25504 and message[3] == "stash" and message[4] == 70,
    "a worn item dropped on tab 2 goes to that tab's first free slot")
_G.PickupInventoryItem(5)
before = #sent
status:SetText("")
DC.Tab_OnReceiveDrag(tab(3))
assert(#sent == before and status:GetText():find("locked"), "a locked tab refuses a worn item with text")

-- A right-click (the sheet's) deposits into the OPEN tab's first free slot; a full or
-- locked tab refuses with a message and sends nothing.
before = #sent
status:SetText("")
assert(DC.DepositToOpenTab(25504), "the deposit entry point exists")
message = lastSent()
assert(#sent == before + 1 and message[1] == "bag" and message[2] == 25504 and message[3] == "stash" and message[4] == 1,
    "a worn item goes to the open tab's first free slot (index 1)")
before = #sent
DC.DepositToOpenTab(25523)
message = lastSent()
assert(#sent == before + 1 and message[2] == 25523 and message[4] == 1, "a bag item the same way")
local fullTab = {}
for index = 0, 69 do fullTab[index] = item(2000 + index, 200 + index) end
handlers.Snapshot(nil, {note = "move", revision = "2", gold = "1234",
    tabs = {granted = 2, max = 5, prices = {}}, layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10}, stash = fullTab})
before = #sent
status:SetText("")
DC.DepositToOpenTab(25504)
assert(#sent == before and status:GetText():find("full"), "a full open tab refuses with a message, nothing is sent")
handlers.Snapshot(nil, {note = "move", revision = "3", gold = "1234",
    tabs = {granted = 2, max = 5, prices = {}}, layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10},
    stash = {[0] = item(1000, 100), [3] = item(1001, 101)}})

-- ------------------------------------------------- what did not change

_G.GetContainerNumSlots = function(bag) return bag == 0 and 2 or 0 end
_G.GetContainerItemLink = function(bag, slot) return (bag == 0 and slot == 1) and "item:1" or nil end
before = #sent
DC.Slot_OnClick(stashSlot(1), "RightButton")
message = lastSent()
assert(#sent == before + 1 and message[1] == "stash" and message[3] == "bag" and message[4] == 255 * 100 + 24,
    "right-click on a stash item goes to the first empty bag cell, named (backpack slot 2)")
before = dragFromStash(stashSlot(1), stashSlot(4), nil)
message = lastSent()
assert(#sent == before + 1 and message[1] == "stash" and message[2] == 0 and message[3] == "stash" and message[4] == 3,
    "stash to stash is unchanged")
before = dragFromStash(stashSlot(1), stashSlot(1), nil)
assert(#sent == before, "a drop on its own slot sends nothing")
before = dragFromStash(stashSlot(1), tab(2), nil)
assert(#sent == before + 1 and lastSent()[4] == 70, "a drop on a tab is unchanged")

-- The XML: the stash's slots are still real stock-cursor drop targets.
local xml = assert(io.open("client-patch/addons/Torment/Stash.xml")):read("*a")
assert(xml:find("Diablocraft.Slot_OnReceiveDrag", 1, true) and xml:find("Diablocraft.Tab_OnReceiveDrag", 1, true),
    "the stash's slots and tabs take the stock cursor")

-- The new addon against TODAY's server Lua: its stash snapshot still carries 60
-- bag cells and layout.bagRows/bagCols. They are ignored, nothing errors, and the
-- stash draws.
local oldBags = {}
for position = 1, 60 do oldBags[position] = {index = 25500 + 22 + position, available = true} end
local ok, err = pcall(handlers.Snapshot, nil, {
    note = "move", revision = "2", gold = "1234", tabs = {granted = 2, max = 5, prices = {}},
    layout = {slotsPerTab = 70, stashRows = 7, stashCols = 10, bagRows = 6, bagCols = 10},
    stash = {[0] = item(1000, 100)}, bags = oldBags,
})
assert(ok, "an old-server stash snapshot must not error: " .. tostring(err))
assert(stashSlot(1).cell.entry == 1000, "and the stash still draws")
assert(_G.DiablocraftBagSlot1 == nil, "with no bag grid")

print("Item dragging checks passed (stash <-> ElvUI bags, stock cursor in, virtual cursor out)")
