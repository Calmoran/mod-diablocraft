-- luacheck: globals DCRequestItemLink IsModifiedClick GetMouseFocus
-- Diablocraft UI kit - account stash and inventory.
--
-- This is a real client addon, not an AIO-delivered file. AIO is only the
-- bridge: the server pushes one Snapshot and this addon draws it; the addon
-- sends back one intent, Move, and never decides whether it is legal. Every
-- rule - eligibility, item legality, slot legality, price - lives in C++
-- (mod-diablocraft/src/items/dc_stash.cpp).

Diablocraft = Diablocraft or {}
local DC = Diablocraft

local CHANNEL = "DiablocraftStash"
local AIO = AIO or (require and require("AIO"))

-- WindowStyle.lua's own helpers (see the note on `Style` there) and the border band PanelKit.lua measured.
local Style = DC.Style
local stashStyle, flatLook, hoverLook = DC.StashStyle, DC.FlatLook, DC.HoverLook
local PANEL_EDGE = DC.PANEL_EDGE

-- The stash's own lines, published for the look test: the subtitle.
local look = {}
DC.StashLook = look

local SLOT, GAP = 34, 2
local CELL = SLOT + GAP
local STASH_ROWS, STASH_COLS = 7, 10  -- 70 slots per tab, as in D3
-- The tab column is built for the five tabs the stash launches with and grows
-- to the server's tabs.max (a tunable, economy.stash_max_tabs) on the first
-- snapshot that carries a larger one, as far as the column has room for.
local BUILT_TABS, TAB_ROOM = 5, 7
local MARGIN = PANEL_EDGE + 10        -- clear of the border band, with air
local GRID_TOP = -140
local TAB_X = MARGIN
local STASH_X = TAB_X + 54
local TAB_STEP = 46
local AUTO = -1                       -- "first free slot on the other side"

-- There is ONE inventory in this game and the stash does not own one: it is
-- ElvUI's bags (one inventory, drag and drop in every direction). Opening the stash opens the
-- bags beside it so a drag has somewhere to start and land, and closing it puts
-- them away only if it opened them.
--
-- The frame is sized from its contents rather than the other way round, so the
-- grid never runs under the border: right edge of the stash grid plus a margin.
-- 200 is the bottom block under the grid: the status line's full-width row above
-- the gold line and the BUY TAB button (at 464 the status line no longer fit
-- BESIDE them, so it is its own row with room to wrap). The materials row that
-- used to sit under it is gone; the block's height
-- is unchanged, so the grid keeps the same clearance.
local PANEL_WIDTH = STASH_X + STASH_COLS * CELL - GAP + MARGIN
local PANEL_HEIGHT = -GRID_TOP + STASH_ROWS * CELL - GAP + 200

local frame, tabs, stashSlots = nil, {}, {}
local snapshot, currentTab = nil, 0
local buyTabButton
local tabCount = 0   -- tab buttons that exist
-- Set while THIS window opened the bags beside itself, so closing the stash puts
-- them away again and leaves bags the player already had open where they were.
local openedBags = false

-- --------------------------------------------------------------- primitives

local function part(button, suffix)
    return _G[button:GetName() .. suffix]
end

-- Balances and counts go through Economy.lua's one shared formatter.
-- This wrapper only keeps the stash's prices, which are
-- plain Lua numbers from dc_stash_tuning, on the same grouping.
local function commas(number)
    return DC.Econ and DC.Econ.Gold(number) or tostring(number or 0)
end

local function status(message, isError)
    if not frame then return end
    local line = _G["DiablocraftStashFrameStatus"]
    line:SetText(message or "")
    local palette = stashStyle().palette
    local colour = isError and palette.RED or palette.GREY
    line:SetTextColor(colour[1], colour[2], colour[3])
end

local function send(...)
    if AIO then AIO.Handle(CHANNEL, ...) end
end

-- ------------------------------------------------------------- slot drawing

function DC.Slot_OnLoad(self)
    self:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    -- A click that does not move is still a click; only a click that moves
    -- becomes a drag, so the click-select path below is untouched.
    self:RegisterForDrag("LeftButton")
    self.back, self.rarity = part(self, "Back"), part(self, "Rarity")
    self.icon, self.count, self.select = part(self, "Icon"), part(self, "Count"), part(self, "Select")
    -- A DCUI slot: the flat ground and bronze edge, no Torment art.
    -- The template's art textures stay declared and empty.
    flatLook(self, "SLOT_BG", "SLOT_BORDER", "slot")
    hoverLook(self)
    self.back:SetTexture(nil)
    self.select:SetTexture(nil)
    self.rarity:SetTexture(nil)
    self.icon:SetTexture(nil)
end

-- An item's rarity, the Blacksmith's way (dc_blacksmith.lua rarityBorder): a 2 px frame on
-- OVERLAY, above the icon, all four sides inside the slot, in the D3 rarity colour. A normal
-- item ("grey") keeps the slot's own bronze edge. The colour names are dc_grid.lua's.
local RARITY_OF = {blue = "magic", yellow = "rare", orange = "legendary", green = "set"}
local RARITY_EDGE = 2
local EDGE_POINTS = {top = {"TOPLEFT", "TOPRIGHT"}, bottom = {"BOTTOMLEFT", "BOTTOMRIGHT"},
                     left = {"TOPLEFT", "BOTTOMLEFT"}, right = {"TOPRIGHT", "BOTTOMRIGHT"}}
local function rarityEdge(button, colour)
    local tint = colour and stashStyle().palette.RARITY[RARITY_OF[colour] or ""]
    button.rarityEdge = button.rarityEdge or {}
    for _, side in ipairs({"top", "bottom", "left", "right"}) do
        local edge = button.rarityEdge[side]
        if tint then
            if not edge then
                edge = button:CreateTexture(nil, "OVERLAY")
                button.rarityEdge[side] = edge
            end
            edge:SetTexture(tint[1], tint[2], tint[3], 1)
            edge:ClearAllPoints()
            edge:SetPoint(EDGE_POINTS[side][1], button, EDGE_POINTS[side][1], 0, 0)
            edge:SetPoint(EDGE_POINTS[side][2], button, EDGE_POINTS[side][2], 0, 0)
            if side == "top" or side == "bottom" then edge:SetHeight(RARITY_EDGE) else edge:SetWidth(RARITY_EDGE) end
            edge:Show()
        elseif edge then
            edge:Hide()
        end
    end
end

-- The grid's last row has no row below it to close it: every other row is closed by the row
-- under it, and the last one showed only its left and right edges (seen
-- in a screenshot). The slot's own 1 px flat backdrop edge does not draw its top and bottom sides
-- in this grid, so the closing line is drawn explicitly, the way the active tab's square and
-- the Blacksmith's rarity border are: an OVERLAY texture on the slot's own bottom corners.
-- Thickness: the other slot edges are the flat backdrop's 1 px edgeSize, so 1 px here; this is
-- the one constant to move if it reads too thin.
local CLOSING_EDGE = 1
local function closingEdge(button)
    if button.closingEdge then return button.closingEdge end
    local bronze = Style.Colour("SLOT_BORDER")
    local edge = button:CreateTexture(nil, "OVERLAY")
    edge:SetTexture(bronze[1], bronze[2], bronze[3], 1)
    edge:SetHeight(CLOSING_EDGE)
    edge:SetPoint(EDGE_POINTS.bottom[1], button, EDGE_POINTS.bottom[1], 0, 0)
    edge:SetPoint(EDGE_POINTS.bottom[2], button, EDGE_POINTS.bottom[2], 0, 0)
    button.closingEdge = edge
    return edge
end

local function drawSlot(button, cell)
    button.cell = cell
    local usable = cell and cell.available ~= false
    button:SetAlpha(usable and 1 or 0.25)
    button:EnableMouse(usable and true or false)
    if cell and cell.entry then
        rarityEdge(button, cell.colour)
        button.icon:SetTexture(GetItemIcon and GetItemIcon(cell.entry) or nil)
        button.count:SetText((cell.count or 1) > 1 and cell.count or "")
    else
        rarityEdge(button, nil)
        button.icon:SetTexture(nil)
        button.count:SetText("")
    end
    -- Nothing is ever "selected" any more: the click-select path is gone and a
    -- move is a drag. The texture stays declared so the art
    -- keeps a name and a revert is one line.
    button.select:Hide()
end

function DC.Slot_OnEnter(self)
    local cell = self.cell
    if not cell or not cell.entry then return end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    if cell.link then GameTooltip:SetHyperlink(cell.link) end
    -- The rolled affixes come from the existing item tooltip path; the stash
    -- ships its own records with the snapshot because its items sit in nobody's
    -- bags and the bag/slot lookup there cannot find them.
    if DCShowItemTooltip and cell.guid then DCShowItemTooltip(GameTooltip, cell.guid) end
    GameTooltip:Show()
end

function DC.Slot_OnLeave()
    GameTooltip:Hide()
end

local function maxTabs()
    local value = snapshot and snapshot.tabs and tonumber(snapshot.tabs.max)
    return math.min(TAB_ROOM, math.max(1, value or BUILT_TABS))
end

-- The active tab's square: the 1 px flat backdrop edge is cut off at the
-- top, so the whole square is drawn as four OVERLAY edges, the Blacksmith's rarity-border
-- way, and a few pixels thick so the tab on show reads at a glance.
local TAB_EDGE = 3
local function tabSquare(button, colour)
    button.tabSquare = button.tabSquare or {}
    for _, side in ipairs({"top", "bottom", "left", "right"}) do
        local edge = button.tabSquare[side]
        if colour then
            if not edge then
                edge = button:CreateTexture(nil, "OVERLAY")
                button.tabSquare[side] = edge
            end
            edge:SetTexture(colour[1], colour[2], colour[3], 1)
            edge:ClearAllPoints()
            edge:SetPoint(EDGE_POINTS[side][1], button, EDGE_POINTS[side][1], 0, 0)
            edge:SetPoint(EDGE_POINTS[side][2], button, EDGE_POINTS[side][2], 0, 0)
            if side == "top" or side == "bottom" then edge:SetHeight(TAB_EDGE) else edge:SetWidth(TAB_EDGE) end
            edge:Show()
        elseif edge then
            edge:Hide()
        end
    end
end

local function buildTab(tab)
    local button = CreateFrame("Button", "DiablocraftStashTab" .. tab, frame, "DiablocraftTabTemplate")
    button:SetPoint("TOPLEFT", frame, "TOPLEFT", TAB_X, GRID_TOP - (tab - 1) * TAB_STEP)
    button.tab = tab
    tabs[tab] = button
    tabCount = tab
end

local function redraw()
    if not snapshot then return end
    local granted = snapshot.tabs and snapshot.tabs.granted or 1
    if currentTab >= granted then currentTab = granted - 1 end
    while tabCount < maxTabs() do buildTab(tabCount + 1) end
    local palette = stashStyle().palette
    for tab = 1, tabCount do
        local button = tabs[tab]
        if tab > maxTabs() then button:Hide() else button:Show() end
        local unlocked = tab <= granted
        -- DCUI's tab (U.tab / U.tabActive): the active bronze on the tab on show, the idle
        -- one on the rest; a locked tab's number is grey and the whole tab dimmed.
        local active = tab - 1 == currentTab
        local edge = Style.Colour(active and "TAB_ACTIVE" or "TAB_IDLE")
        button:SetBackdropBorderColor(edge[1], edge[2], edge[3], 1)
        -- A skin's tab image marks the tab on show itself, so the square is drawn only without one.
        local faced = Style.Face(button, active and "tab-active" or "tab")
        tabSquare(button, active and not faced and edge or nil)
        local label = part(button, "Label")
        label:SetText(tab)
        local number = unlocked and palette.GOLD or palette.GREY
        label:SetTextColor(number[1], number[2], number[3])
        button.unlocked = unlocked
        button:SetAlpha(unlocked and 1 or 0.45)
    end
    for position = 1, STASH_ROWS * STASH_COLS do
        local index = currentTab * (snapshot.layout and snapshot.layout.slotsPerTab or 70) + position - 1
        local cell = snapshot.stash[index] or snapshot.stash[tostring(index)]
        drawSlot(stashSlots[position], cell and {index = index, available = true, entry = cell.entry,
            count = cell.count, colour = cell.colour, guid = cell.guid, link = cell.link, name = cell.name}
            or {index = index, available = true})
    end
    -- No bag grid here. The player's bags are ElvUI's (or the stock ones), and
    -- this window opens them beside itself.
    -- Exact decimal strings only (0007). The live account snapshot wins; the
    -- server's own string is the fallback. Neither becomes a Lua number, which
    -- would start dropping digits at 2^53 while a pool runs to UINT64_MAX.
    local balance = DC.Econ and DC.Econ.Balance() or snapshot.gold
    -- The Jeweler's and the Blacksmith's gold line, word for word.
    _G["DiablocraftStashFrameGold"]:SetText("Your gold: " .. commas(balance))
    if look.subtitle then look.subtitle:SetText("TAB " .. (currentTab + 1)) end
    if buyTabButton then
        buyTabButton:SetText(granted >= maxTabs() and "ALL TABS" or ("BUY TAB " .. (granted + 1)))
    end
end

-- -------------------------------------------------------------------- input

local function move(fromKind, fromIndex, toKind, toIndex)
    send("Move", fromKind, fromIndex, toKind, toIndex)
    status("")
end

-- Whether the stash session is live. The server closes this window the moment
-- the session dies, so the frame being up is the addon's only honest answer.
function DC.StashIsOpen()
    return frame ~= nil and frame:IsShown()
end

function DC.Status(message, isError)
    status(message, isError)
end

-- Right-click is WoW's quick-move: a stash item goes to the first free bag cell.
--
-- Left-click does nothing here any more. The click-select-then-click path is
-- gone (shift right-click to grab, then another click into another slot, was
-- too convoluted). Moving an item is dragging it.
-- The first empty bag cell, in the server's numbering, found from the stock bag API
-- (ElvUI's bags are the same containers): the backpack first, then the carried bags,
-- as the core's own auto-store walks them. nil when every cell is taken.
local function firstFreeBagIndex()
    local slots, link = _G.GetContainerNumSlots, _G.GetContainerItemLink
    if not slots or not link then return nil end
    for bag = 0, 4 do
        for slot = 1, (slots(bag) or 0) do
            if not link(bag, slot) then return DC.BagIndex(bag, slot) end
        end
    end
    return nil
end

function DC.Slot_OnClick(self, button)
    local cell = self.cell
    if not cell or cell.available == false then return end
    -- Shift-click shares a rolled item.
    if button == "LeftButton" and IsModifiedClick("CHATLINK") and cell.guid and DCRequestItemLink then DCRequestItemLink(cell.guid); return end
    if button ~= "RightButton" or not cell.entry then return end
    -- The destination is NAMED, as a drag names it, not AUTO: dev's log showed
    -- every drag arriving and no right-click at all, so the one move that has never been
    -- seen to work is the one that leaves the choice to the server. A full bag is said so
    -- here, in the status line, instead of being left to a refusal that may not show.
    local index = firstFreeBagIndex()
    if not index then
        status("Your bags are full.", true)
        return
    end
    move("stash", cell.index, "bag", index)
    redraw()
end

-- --------------------------------------------------------------------- drag
--
-- Checked against the stock 3.3.5a API rather than assumed. There is no call
-- that puts an arbitrary item on the cursor: every pickup addresses a container
-- the client already knows - PickupContainerItem(bag, slot),
-- PickupInventoryItem(slot), PickupGuildBankItem(tab, slot) - and a stash item
-- is parked in the database with its owner and container cleared, so it sits in
-- none of them and CursorHasItem() can never become true for one.
--
-- So a drag that STARTS in the stash is the one drag that needs a virtual
-- cursor - the item icon on an overlay frame following the mouse - and it is the
-- only one left. Everything
-- that starts in a bag or on a worn slot is the stock cursor, because ElvUI's
-- bags and the sheet's slots are stock-cursor citizens; the stash's own slots
-- and tabs take that cursor as a drop target (Slot_OnReceiveDrag below) and the
-- virtual one lands on the stash, its tabs, or an ElvUI bag slot.
--
-- Stash targets are found geometrically rather than with GetMouseFocus(): a
-- cell the server marked unavailable has its mouse disabled and so is never the
-- mouse focus, and a drop on one has to say why it was refused rather than
-- vanish. A bag slot is the opposite case - ElvUI's buttons are always live - so
-- those ARE found by the mouse focus.
local GetCursorPosition = _G.GetCursorPosition

local dragFrame, dragIcon, dragging = nil, nil, nil
-- The stash's drop targets (its 70 slots and its tabs), each group with the
-- frame it lives on: a hidden window is not a drop target.
local dropGroups = {}

local function cursorPoint()
    if not GetCursorPosition then return nil end
    local x, y = GetCursorPosition()
    if not x or not y then return nil end
    -- GetCursorPosition answers in screen units; every frame here is a child of
    -- UIParent at scale 1, so one divide puts both in the same space.
    local scale = UIParent:GetEffectiveScale()
    if not scale or scale == 0 then scale = 1 end
    return x / scale, y / scale
end

local function covers(button, x, y)
    if button.IsShown and not button:IsShown() then return false end
    local left, right = button:GetLeft(), button:GetRight()
    local bottom, top = button:GetBottom(), button:GetTop()
    if not left or not right or not bottom or not top then return false end
    return x >= left and x < right and y >= bottom and y < top
end

function DC.RegisterDropTargets(owner, buttons)
    dropGroups[#dropGroups + 1] = {owner = owner, buttons = buttons}
end

local function dropTarget()
    local x, y = cursorPoint()
    if not x then return nil end
    for _, group in ipairs(dropGroups) do
        if not group.owner or group.owner:IsShown() then
            for _, button in ipairs(group.buttons) do
                if covers(button, x, y) then return button end
            end
        end
    end
    return nil
end

local function stopDrag()
    dragging = nil
    if dragFrame then dragFrame:Hide() end
    if dragIcon then dragIcon:SetTexture(nil) end
end

DC.CancelDrag = stopDrag

-- bag * 100 + slot, the one encoding both halves and C++ use (dc_grid.lua), from
-- an ElvUI (or stock) bag button's own bagID/slotID. The two numbering systems do
-- not agree and the conversion is the whole reason this exists: the CLIENT's bag 0
-- is the backpack and bags 1-4 the carried bags, a slot inside either is 1-based;
-- the server puts the backpack's 16 cells at player slots 23-38 and numbers a
-- carried bag's own cells from 0 (dc_grid.lua, INVENTORY_SLOT_BAG_START 19).
local function bagIndex(bag, slot)
    if type(bag) ~= "number" or type(slot) ~= "number" then return nil end
    if bag == 0 then return 255 * 100 + (slot + 22) end
    if bag >= 1 and bag <= 4 then return (bag + 18) * 100 + (slot - 1) end
    return nil
end
DC.BagIndex = bagIndex

-- What is on the virtual cursor: a stash cell, `index` echoed back untouched.
function DC.StartDrag(kind, cell)
    if kind ~= "stash" then return false end
    if not cell or cell.available == false or not cell.entry then return false end
    dragging = {kind = kind, index = cell.index, guid = cell.guid, entry = cell.entry, name = cell.name}
    if dragIcon then dragIcon:SetTexture(GetItemIcon and GetItemIcon(cell.entry) or nil) end
    if dragFrame then dragFrame:Show() end
    status("")
    return true
end

function DC.HeldDrag()
    return dragging
end

-- A drop onto a stash TAB button moves the item into that tab.
-- The index is the first slot the snapshot shows empty in that tab:
-- an explicit destination, exactly like every other drop, so the tab button
-- needs no new encoding on the wire and the server validates it as usual.
local function dropOnTab(held, target)
    if not target.unlocked then
        status("Stash tab " .. target.tab .. " is locked. Buy it with the button below.", true)
        return
    end
    local perTab = (snapshot and snapshot.layout and snapshot.layout.slotsPerTab) or 70
    local first = (target.tab - 1) * perTab
    local stash = (snapshot and snapshot.stash) or {}
    for index = first, first + perTab - 1 do
        if not (stash[index] or stash[tostring(index)]) then
            move(held.kind, held.index, "stash", index)
            redraw()
            return
        end
    end
    status("Stash tab " .. target.tab .. " is full.", true)
end

-- Deposit one item from the bags or a worn slot into the tab that is open, at its
-- first free slot (a right-click on a bag item or a worn item while
-- the stash is open). `index` is the bag index (bag * 100 + slot, DC.BagIndex) or,
-- for a worn item, 25500 + its 0-based equipment slot. A locked or full tab says so
-- and the item stays where it is.
function DC.DepositToOpenTab(index)
    local target = tabs[(currentTab or 0) + 1]
    if not target then return false end
    dropOnTab({kind = "bag", index = index}, target)
    return true
end

-- The bag slot under the mouse, if the mouse is over one: ElvUI's buttons carry
-- bagID and slotID (dc_tooltip.lua locate() reads the same two fields), and the
-- stock ContainerFrame button is its own slot with its parent's id for the bag.
local function bagSlotUnderMouse()
    local focus = GetMouseFocus and GetMouseFocus()
    if not focus then return nil end
    if type(focus.bagID) == "number" and type(focus.slotID) == "number" then
        return bagIndex(focus.bagID, focus.slotID)
    end
    local name = focus.GetName and focus:GetName() or ""
    if name:find("^ContainerFrame%d+Item%d+$") then
        return bagIndex(focus:GetParent():GetID(), focus:GetID())
    end
    return nil
end

-- The one place a stash-origin drop decides what to send. Legality is still
-- entirely the server's: this picks a destination index and C++ refuses anything
-- it should not honour.
function DC.ResolveDrop()
    local held = dragging
    stopDrag()
    if not held then return end
    local target = dropTarget()
    if not target then
        -- Not on the stash: an ElvUI bag slot takes it to exactly that cell.
        local index = bagSlotUnderMouse()
        if index then
            move("stash", held.index, "bag", index)
            redraw()
        end
        return
    end
    if target.tab then
        dropOnTab(held, target)
        return
    end
    local cell = target.cell
    if not cell then return end
    if cell.available == false then
        status("That stash slot is not available.", true)
        return
    end
    -- Dropped on itself: nothing happened, and the server is not asked.
    if held.index == cell.index then return end
    move("stash", held.index, "stash", cell.index)
    redraw()
end

function DC.Slot_OnDragStart(self)
    if DC.StartDrag(self.kind, self.cell) then redraw() end
end

function DC.Slot_OnDragStop()
    DC.ResolveDrop()
    redraw()
end

-- The STOCK cursor, for a drag that started in a bag. There is no API that says
-- which container an item on the cursor came from, so the two pickup calls are
-- hooked to remember it - the pattern dc_crafting.lua's drop target already uses.
local cursorBag, cursorSlot

-- Published so the headless test can drive the conversion without having to
-- intercept two of the client's own globals.
function DC.SetStockCursor(bag, slot)
    cursorBag, cursorSlot = bag, slot
end

if hooksecurefunc then
    hooksecurefunc("PickupContainerItem", function(bag, slot) DC.SetStockCursor(bag, slot) end)
    hooksecurefunc("PickupInventoryItem", function(slot) DC.SetStockCursor(255, slot - 1) end)
end

-- The bag index of the item on the stock cursor, or nil when it did not come
-- from a bag. Worn gear is bag 255 here and is not a bag cell: DecodeBag refuses
-- it, which is right - worn gear is not deposited from a bag cell.
function DC.StockCursorIndex()
    if not cursorBag or not cursorSlot then return nil end
    if cursorBag == 255 then return 255 * 100 + cursorSlot end
    return bagIndex(cursorBag, cursorSlot)
end
local stockCursorIndex = DC.StockCursorIndex

-- A real drop target for the stock cursor: dropping a bag item from ElvUI's bags
-- onto a stash slot deposits it. Same explicit Move, same server.
function DC.Slot_OnReceiveDrag(self)
    if dragging then
        DC.ResolveDrop()
        redraw()
        return
    end
    local hasItem = _G.CursorHasItem
    if not GetCursorInfo or not hasItem or not hasItem() then return end
    local kind = GetCursorInfo()
    if kind ~= "item" then return end
    local index = stockCursorIndex()
    local cell = self.cell
    if not index or not cell or cell.available == false then return end
    if cursorBag == 255 then
        -- A worn item goes straight into the stash in ONE server move (unequip and
        -- deposit together, or neither). Only onto an EMPTY slot: the server refuses a
        -- swap with a worn item too, and says so here before asking.
        if ClearCursor then ClearCursor() end
        if cell.entry then
            status("Drop a worn item on an empty Stash slot.", true)
            return
        end
        move("bag", index, self.kind, cell.index)
        redraw()
        return
    end
    if ClearCursor then ClearCursor() end
    move("bag", index, self.kind, cell.index)
    redraw()
end

function DC.Tab_OnReceiveDrag(self)
    if dragging then
        DC.ResolveDrop()
        redraw()
        return
    end
    local hasItem = _G.CursorHasItem
    if not GetCursorInfo or not hasItem or not hasItem() then return end
    if GetCursorInfo() ~= "item" then return end
    local index = stockCursorIndex()
    if not index then return end
    if ClearCursor then ClearCursor() end
    dropOnTab({kind = "bag", index = index}, self)
end

function DC.Tab_OnLoad(self)
    self:RegisterForClicks("LeftButtonUp")
    -- A DCUI tab: a slot's flat ground with the idle bronze edge; redraw marks the active one.
    flatLook(self, "SLOT_BG", "TAB_IDLE", "tab")
    hoverLook(self)
    part(self, "Back"):SetTexture(nil)
end

function DC.Tab_OnClick(self)
    if not self.unlocked then
        status("Stash tab " .. self.tab .. " is locked. Buy it with the button below.", true)
        return
    end
    currentTab = self.tab - 1
    redraw()
end

local function priceOf(tab)
    local prices = snapshot and snapshot.tabs and snapshot.tabs.prices
    return prices and (prices[tab] or prices[tostring(tab)])
end

function DC.Tab_OnEnter(self)
    if self.unlocked then return end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:AddLine("Stash tab " .. self.tab)
    local price = priceOf(self.tab)
    if price then
        GameTooltip:AddLine(commas(price) .. " gold", 1, 0.82, 0)
    else
        GameTooltip:AddLine("Price not set yet.", 0.7, 0.7, 0.7)
    end
    GameTooltip:Show()
end

function DC.Button_OnLoad(self)
    self:RegisterForClicks("LeftButtonUp")
    DC.SetArt(part(self, "Back"), "button")
end

function DC.Button_OnMouseDown(self)
    DC.SetArt(part(self, "Back"), "button-pressed")
end

function DC.Button_OnMouseUp(self)
    DC.SetArt(part(self, "Back"), "button")
end

function DC.BuyTab()
    send("BuyTab")
end

function DC.BuyTab_OnEnter(self)
    local granted = snapshot and snapshot.tabs and snapshot.tabs.granted or 1
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    if granted >= maxTabs() then
        GameTooltip:AddLine("All " .. maxTabs() .. " stash tabs are yours.")
        GameTooltip:Show()
        return
    end
    local price = priceOf(granted + 1)
    GameTooltip:AddLine("Buy stash tab " .. (granted + 1))
    if price then
        GameTooltip:AddLine(commas(price) .. " gold", 1, 0.82, 0)
    else
        GameTooltip:AddLine("Price not set yet; the purchase is refused.", 0.7, 0.7, 0.7)
    end
    GameTooltip:Show()
end

-- Opening the stash opens the player's bags (ElvUI's, or the stock ones when
-- ElvUI is off) and sits to their left, clear of ElvUI's default bottom-right
-- column. The bags are only closed again if this window is what opened them.
local BAG_CLEARANCE = 440

local function openBagsBeside()
    if not frame then return end
    local open = false
    if _G.ElvUI_ContainerFrame then open = _G.ElvUI_ContainerFrame:IsShown() end
    if not open and _G.ContainerFrame1 then open = _G.ContainerFrame1:IsShown() end
    if not open and _G.OpenAllBags then
        _G.OpenAllBags(true)
        openedBags = true
    end
    -- The bag buttons take their right-click hook (Inventory.lua) while the stash is up too.
    if DC.Inventory_ScanBagButtons then DC.Inventory_ScanBagButtons() end
    frame:ClearAllPoints()
    -- Beside ElvUI's bags, the stash's right edge touches the bag frame's left edge with no
    -- overlap. The stock bags are a stack of
    -- frames rather than one, so with them the stash keeps its old spot clear of their column.
    local bags = _G.ElvUI_ContainerFrame
    if bags and bags:IsShown() then
        frame:SetPoint("RIGHT", bags, "LEFT", 0, 0)
    else
        frame:SetPoint("RIGHT", UIParent, "RIGHT", -BAG_CLEARANCE, 0)
    end
end

function DC.Hide()
    if frame then frame:Hide() end
end

function DC.Frame_OnHide()
    -- Escape closes the window mid-drag; OnDragStop never arrives, so the
    -- virtual cursor is put away here too.
    stopDrag()
    -- If this window opened the bags, this window puts them away, and bags the
    -- player already had open are left exactly where they were.
    if openedBags then
        openedBags = false
        if _G.CloseAllBags then _G.CloseAllBags() end
    end
    send("Close")
end

-- ------------------------------------------------------------------- build

local function buildGrid(parent, prefix, kind, originX, rows, cols, store)
    for row = 0, rows - 1 do
        for col = 0, cols - 1 do
            local position = row * cols + col + 1
            local button = CreateFrame("Button", prefix .. position, parent, "DiablocraftSlotTemplate")
            button:SetPoint("TOPLEFT", parent, "TOPLEFT", originX + col * CELL, GRID_TOP - row * CELL)
            button.kind = kind
            -- The last row has no row under it to close it; its own closing line is drawn
            -- here (closingEdge).
            if row == rows - 1 then closingEdge(button) end
            store[position] = button
        end
    end
end

function DC.Frame_OnLoad(self)
    frame = self
    self:RegisterForDrag("LeftButton")
    self:SetClampedToScreen(true)
    self:SetWidth(PANEL_WIDTH)
    self:SetHeight(PANEL_HEIGHT)
    local style = stashStyle()
    if DC.Style.Panel then DC.Style.Panel(self) else self:SetBackdrop(style.backdrop) end
    local title = _G[(self:GetName() or "") .. "Title"]
    if title and DC.Style.Title then DC.Style.Title(self, title) end
    local close = style.Close(self)
    close:SetScript("OnClick", function() DC.Hide() end)
    buyTabButton = style.Button(self, 140, "BUY TAB 2", function() DC.BuyTab() end)
    buyTabButton:SetPoint("BOTTOMRIGHT", self, "BOTTOMRIGHT", -MARGIN, 60)
    buyTabButton:SetScript("OnEnter", function(this) DC.BuyTab_OnEnter(this) end)
    buyTabButton:SetScript("OnLeave", function(this) DC.Slot_OnLeave(this) end)
    -- The grey subtitle under the title, U.subtitle's font and spot: the tab on show.
    local grey = style.palette.GREY
    look.subtitle = self:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    look.subtitle:SetPoint("TOP", self, "TOP", 0, -42)
    look.subtitle:SetWidth(PANEL_WIDTH)
    look.subtitle:SetJustifyH("CENTER")
    look.subtitle:SetTextColor(grey[1], grey[2], grey[3])
    for tab = 1, BUILT_TABS do buildTab(tab) end
    -- The whole-window slot: `tabs` is the column itself, so tabs the stash grows later are
    -- placed on the next paint (DC.RefreshArt).
    if DC.Style.Window then
        DC.Style.Window(self, "stash", {title = title, close = close, tabs = tabs, buttons = {buyTabButton}})
    end
    buildGrid(self, "DiablocraftStashSlot", "stash", STASH_X, STASH_ROWS, STASH_COLS, stashSlots)
    -- The stash's own drop targets: its 70 slots and its five tab buttons. A bag
    -- slot is ElvUI's live button, found by the mouse focus instead, which is
    -- what lets one drag cross between the stash and the bags.
    DC.RegisterDropTargets(self, stashSlots)
    DC.RegisterDropTargets(self, tabs)
    -- The virtual cursor: one slot-sized icon above everything, parented to
    -- UIParent so it is not clipped by the panel it is dragged out of.
    dragFrame = CreateFrame("Frame", "DiablocraftStashDrag", UIParent)
    dragFrame:SetWidth(SLOT)
    dragFrame:SetHeight(SLOT)
    dragFrame:SetFrameStrata("TOOLTIP")
    dragFrame:Hide()
    dragIcon = dragFrame:CreateTexture(nil, "OVERLAY")
    dragIcon:SetAllPoints(dragFrame)
    dragFrame:SetScript("OnUpdate", function(this)
        local x, y = cursorPoint()
        if not x then return end
        this:ClearAllPoints()
        this:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x, y)
    end)
    -- The account materials row that used to sit above the gold line is gone:
    -- the balances are on the sheet's Materials
    -- panel, and the window keeps its band to itself.
    tinsert(UISpecialFrames, "DiablocraftStashFrame")
    if DC.Econ then DC.Econ.OnChange(function() if frame and frame:IsShown() then redraw() end end) end
end

-- The stash draws its own gold line rather than a stock money frame, so it is
-- refreshed from Frame_OnLoad's DCECON listener above.

-- ---------------------------------------------------------------- the bridge

if AIO then
    local handlers = AIO.AddHandlers(CHANNEL, {})

    function handlers.Snapshot(_, data)
        if not data then return end
        snapshot = data
        snapshot.stash = snapshot.stash or {}
        if DCAddItemTooltips then DCAddItemTooltips(data.tooltips) end
        if data.note == "open" then currentTab = 0 end
        redraw()
        if frame and not frame:IsShown() then
            openBagsBeside()
            frame:Show()
        end
    end

    function handlers.Error(_, message)
        status(message, true)
    end

    -- The server closes the window; the addon never decides to. It shuts on the
    -- same range check every move is refused on, and on death, teleport and
    -- combat (mod-diablocraft/lua/aio/dc_stash.lua). Hide() runs Frame_OnHide,
    -- which echoes Close back, so the server needs no acknowledgement.
    function handlers.CloseWindow(_, reason)
        if reason and reason ~= "" then
            DEFAULT_CHAT_FRAME:AddMessage("|cffffcc66Torment:|r " .. reason)
        end
        DC.Hide()
    end
end

SLASH_DIABLOCRAFTSTASH1 = "/dcstash"
SlashCmdList.DIABLOCRAFTSTASH = function(arg)
    if not frame then return end
    if arg == "noart" or arg == "art" then
        DC.USE_ART = arg == "art"
        DEFAULT_CHAT_FRAME:AddMessage("Torment: art " .. (DC.USE_ART and "on" or "off") .. "; /reload to redraw.")
        return
    end
    if frame:IsShown() then frame:Hide() else send("Refresh") end
end
