-- luacheck: globals DCRequestItemLink DCItemRarity DCOnItemRecords IsModifiedClick IsInventoryItemLocked CursorHasItem PickupInventoryItem SocketInventoryItem InCombatLockdown GetContainerItemLink GetContainerNumSlots NUM_CONTAINER_FRAMES MAX_CONTAINER_ITEMS IsShiftKeyDown IsControlKeyDown IsAltKeyDown GetBindingAction SetBinding SaveBindings GetCurrentBindingSet BINDING_HEADER_TORMENT BINDING_NAME_TORMENT_PARAGON DiablocraftUI UnitPowerType
-- Diablocraft UI kit - the Torment character sheet.
--
-- It REPLACES WoW's character sheet. C and the character micro-button open this
-- panel and the stock sheet never appears, the same way the skills screen took
-- the spellbook key (12-ui U2).
--
-- There is no bag grid. The player's bags are ElvUI's, and a move between them
-- and this sheet is the STOCK cursor: this file draws the worn items from the
-- stock inventory API (GetInventoryItemLink and friends) and says what a drop or
-- a click on a slot means. Two sources feed the rest, both from the server and
-- neither computed here:
--
--   Snapshot   one AIO message from lua/aio/dc_inventory.lua: the character and
--              Paragon levels, the class's main stat, the potion slot (a virtual
--              slot the client cannot see) and the funds fallback.
--   DCSHEET    the 22 stats and the three D3 summary values, pushed straight
--              from C++ (src/items/dc_inventory.cpp) because they are stat
--              maths and Lua never does stat maths (00 §5, 12-ui §2). It is
--              sent on the same session immediately before the snapshot, so it
--              is always here first.
--
-- The addon sends two intents, Equip and Unequip, and decides neither: C++
-- validates both through the core's own CanEquipItem/SwapItem path. The one
-- thing decided here is a courtesy: a drop on a slot the item cannot go in says
-- "That doesn't go there." before the cursor is spent; the server's refusal is
-- the backstop.
--
-- Details and Materials share ONE panel on the sheet's left.

Diablocraft = Diablocraft or {}
local DC = Diablocraft

local CHANNEL = "DiablocraftInventory"
local SHEET_PREFIX = "DCSHEET"
-- The Paragon push (dc_paragon.cpp Wire). It carries the Paragon level the
-- header shows, so a Paragon level-up, an allocation or a respec has to move
-- this screen too; E is the record that says the snapshot is complete (contract
-- paragon-messages.md), so a half-received push never asks.
local PARAGON_PREFIX = "DCPARAGON"
local AIO = AIO or (require and require("AIO"))

-- ------------------------------------------------------------------- layout

-- The mockup's numbers, shifted by the panel band: the doll is 372 square, so
-- the sheet is the doll plus a 24 margin each side.
local PANEL_WIDTH = 420
local PANEL_HEIGHT = 660
local SIDE_WIDTH = 340

local MARGIN = 24
local DOLL = 372
local DOLL_X, DOLL_Y = MARGIN, -96

local MARGIN_SIDE = 28
local TOP = -72
local SIDE_ROW_W = SIDE_WIDTH - 2 * MARGIN_SIDE - 24
local VALUE_W = 86
local LABEL_W = SIDE_ROW_W - VALUE_W - 8
local ROW_STEP, GROUP_STEP = 17, 23

-- The window look is the shared one (the Skills restyle's): the
-- Torment addon's Diablocraft.Style when it is there - WindowStyle.lua loads
-- before this file, so in the game it always is - else this same table, so a
-- load with no kit (test_character_sheet.lua's stub client) still draws the
-- right window. The copy is pinned field by field against the Jeweler's PANEL by
-- test_character_sheet.lua, and this file's read of DC.Style by its own reload.
local WINDOW_BACKDROP = {
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tile = true, tileSize = 32, edgeSize = 32,
    insets = {left = 11, right = 12, top = 12, bottom = 11},
}
local STYLE = {backdrop = (DC.Style and DC.Style.backdrop) or WINDOW_BACKDROP}
-- The skin-aware window parts when the kit has them: true if it drew.
local function styled(name, ...)
    local helper = DC.Style and DC.Style[name]
    if not helper then return false end
    helper(...)
    return true
end

-- EVERY slot is one size and square (WoW item icons are square); only the size
-- changed, each slot keeps the centre of the mockup box it came from. 46 is the
-- largest that keeps the closest pair (the belt and pants centres, 62 apart) clear
-- of each other and the potion inside the doll.
local SLOT_SIZE = 46

-- The mockup's paperdoll boxes in the 372 x 372 doll, D3's layout: left
-- Shoulders, Gloves, Ring, Main Hand, Potion; centre Helm, Chest, Belt, Pants,
-- Boots; right Amulet, Bracers, Ring, Off Hand. `slot` is the WoW equipment slot
-- the server sends and `.dc inventory unequip` takes (the stock client's id is
-- slot + 1); 100 is the virtual potion slot.
local GEAR = {
    {slot = 2,   art = "Shoulder",      label = "Shoulders", x = 40,  y = 28,  w = 68, h = 66},
    {slot = 9,   art = "Hands",         label = "Gloves",    x = 40,  y = 102, w = 68, h = 76},
    {slot = 10,  art = "Finger",        label = "Ring",      x = 54,  y = 188, w = 40, h = 40},
    {slot = 15,  art = "MainHand",      label = "Main Hand", x = 40,  y = 236, w = 68, h = 92},
    {slot = 100, art = "Potion",        label = "Potion",    x = 56,  y = 334, w = 36, h = 34},
    {slot = 0,   art = "Head",          label = "Helm",      x = 152, y = 8,   w = 68, h = 64},
    {slot = 4,   art = "Chest",         label = "Chest",     x = 152, y = 80,  w = 68, h = 90},
    {slot = 5,   art = "Waist",         label = "Belt",      x = 152, y = 178, w = 68, h = 30},
    {slot = 6,   art = "Legs",          label = "Pants",     x = 152, y = 216, w = 68, h = 78},
    {slot = 7,   art = "Feet",          label = "Boots",     x = 152, y = 302, w = 68, h = 62},
    {slot = 1,   art = "Neck",          label = "Amulet",    x = 274, y = 38,  w = 48, h = 48},
    {slot = 8,   art = "Wrists",        label = "Bracers",   x = 264, y = 102, w = 68, h = 76},
    {slot = 11,  art = "Finger",        label = "Ring",      x = 278, y = 188, w = 40, h = 40},
    {slot = 16,  art = "SecondaryHand", label = "Off Hand",  x = 264, y = 236, w = 68, h = 92},
}

-- 05 §7's five cosmetic slots, drawn in place of the paperdoll by the Cosmetics
-- view. The WoW slot each one rides on is that table's, not a new one.
local COSMETIC = {
    {slot = 3,  art = "Shirt",   label = "Wings",     x = 40,  y = 62,  w = 68, h = 84},
    {slot = 18, art = "Tabard",  label = "Pet",       x = 40,  y = 236, w = 68, h = 68},
    {slot = 12, art = "Trinket", label = "Aura",      x = 152, y = 8,   w = 68, h = 64},
    {slot = 13, art = "Trinket", label = "Footsteps", x = 152, y = 288, w = 68, h = 56},
    {slot = 14, art = "Back",    label = "Back",      x = 264, y = 62,  w = 68, h = 84},
}

-- Which item types (GetItemInfo's equipLoc) each WoW slot takes - the client
-- half of "That doesn't go there." The server's CanEquipItem is the real check.
local FITS = {
    [0] = {INVTYPE_HEAD = true},
    [1] = {INVTYPE_NECK = true},
    [2] = {INVTYPE_SHOULDER = true},
    [3] = {INVTYPE_BODY = true},
    [4] = {INVTYPE_CHEST = true, INVTYPE_ROBE = true},
    [5] = {INVTYPE_WAIST = true},
    [6] = {INVTYPE_LEGS = true},
    [7] = {INVTYPE_FEET = true},
    [8] = {INVTYPE_WRIST = true},
    [9] = {INVTYPE_HAND = true},
    [10] = {INVTYPE_FINGER = true},
    [11] = {INVTYPE_FINGER = true},
    [12] = {INVTYPE_TRINKET = true},
    [13] = {INVTYPE_TRINKET = true},
    [14] = {INVTYPE_CLOAK = true},
    [15] = {INVTYPE_WEAPON = true, INVTYPE_2HWEAPON = true, INVTYPE_WEAPONMAINHAND = true},
    [16] = {INVTYPE_WEAPON = true, INVTYPE_SHIELD = true, INVTYPE_HOLDABLE = true, INVTYPE_WEAPONOFFHAND = true},
    [18] = {INVTYPE_TABARD = true},
}
local POTION_SLOT = 100

-- item_template.Quality to the art slot's colour name (dc_grid.lua's table).
local QUALITY_COLOUR = {[0] = "grey", [1] = "grey", [2] = "green", [3] = "blue", [4] = "yellow",
                        [5] = "orange", [6] = "orange", [7] = "orange"}

-- The rolled rarity (dc_tooltip.lua's record cache) to the same colour names.
local RARITY_COLOUR = {normal = "grey", magic = "blue", rare = "yellow", legendary = "orange", set = "green"}

-- The four primaries in one row; the key is the DCSHEET key and the name is what
-- the snapshot's mainStat says.
local PRIMARIES = {
    {key = "str", name = "Strength"},
    {key = "dex", name = "Dexterity"},
    {key = "int", name = "Intelligence"},
    {key = "vit", name = "Vitality"},
}
local SUMMARIES = {
    {key = "dmg",   name = "Damage",    tip = "Damage per second with your weapon and all bonuses."},
    {key = "tough", name = "Toughness", tip = "How much damage you can take, counting Life, Armor and Resistance."},
    {key = "recov", name = "Recovery",  tip = "Life you get back per second from Life per Second and Life per Hit."},
}

-- stats.csv's 22 stats in D3's five groups, with the derived values D3's own
-- Details panel shows beside them (Attacks per Second, Maximum Life, Maximum
-- Fury). `key` is the DCSHEET key C++ sends; nothing here is calculated.
--   int  whole number        pct  two decimals and a % sign
--   num  two decimals        ele  expands to one row per element carried
local DETAILS = {
    {group = "Offense"},
    {key = "str",      label = "Damage Increased by Str",  kind = "pct"},
    {key = "aps",      label = "Attacks per Second",       kind = "num"},
    {key = "ias",      label = "Attack Speed Increase",    kind = "pct"},
    {key = "chc",      label = "Critical Hit Chance",      kind = "pct"},
    {key = "chd",      label = "Critical Hit Damage",      kind = "pct"},
    {key = "ad",       label = "Area Damage",              kind = "pct"},
    {key = "cdr",      label = "Cooldown Reduction",       kind = "pct"},
    {key = "ele",      label = "Elemental Damage",         kind = "ele"},
    {group = "Defense"},
    {key = "armor",    label = "Armor",                    kind = "int"},
    {key = "dex",      label = "Dexterity",                kind = "int"},
    {key = "int",      label = "Intelligence",             kind = "int"},
    {key = "resall",   label = "All Resistance",           kind = "int"},
    -- One row per element a single-element source raised (D3's secondary
    -- resists: an item line or a power like Esoteric Alteration raises one),
    -- the way Elemental Damage above expands. All Resistance is the flat
    -- total every element shares; a row appears only when an element is
    -- higher than it, so nothing is repeated when nothing special is worn.
    {key = "res",      label = "Resistance",               kind = "res"},
    -- Block has four stat slots (docs/research/block.md).
    -- The Amount is a MIN-MAX range a blocked hit rolls inside, so the row shows
    -- the range from the two keys C++ sends, never one number.
    {key = "block",    label = "Block Chance",             kind = "pct"},
    {key = "blockmin", label = "Block Amount",             kind = "range", upper = "blockmax"},
    {key = "thorns",   label = "Thorns",                   kind = "num"},
    {group = "Life"},
    {key = "life",     label = "Maximum Life",             kind = "int"},
    {key = "vit",      label = "Vitality",                 kind = "int"},
    {key = "lifepct",  label = "Total Life Bonus",         kind = "pct"},
    {key = "regen",    label = "Life per Second",          kind = "num"},
    {key = "loh",      label = "Life per Hit",             kind = "num"},
    {key = "lpk",      label = "Life per Kill",            kind = "num"},
    {group = "Resource"},
    -- The label is the class's own resource (resourceLabel below), not this one.
    {key = "fury",     label = "Maximum Resource",         kind = "int", resource = true},
    {key = "rcr",      label = "Resource Cost Reduction",  kind = "pct"},
    -- The fifth group. It was last in the list and
    -- below the fold; the re-flow is what makes it reachable.
    {group = "Adventure"},
    {key = "ms",       label = "Movement Speed",           kind = "pct"},
    {key = "gf",       label = "Gold Find",                kind = "pct"},
    {key = "mf",       label = "Magic Find",               kind = "pct"},
    {key = "xp",       label = "Bonus Experience",         kind = "pct"},
}

local ELEMENTS = {"Physical", "Fire", "Cold", "Lightning", "Poison", "Arcane", "Holy"}

-- ------------------------------------------------------------------- state

local frame, sidePanel, escapeProxy
local gearButtons, cosmeticButtons = {}, {}
local nameText, levelText, paragonButton
local primaryText, summaryText, fundsText
local detailsRows, detailsScroll, materialsFrame, materialsRows
local sideMode                  -- "details", "materials" or nil
local snapshot, sheet, sheetBuffer = nil, nil, nil
local changed = {}              -- DCSHEET key -> 1 (went up) / -1 (went down), last receive
local cosmeticsShown = false
local escapeBusy = false
local model

-- ------------------------------------------------------------- primitives

local function part(button, suffix)
    return _G[button:GetName() .. suffix]
end

local function send(...)
    if AIO then AIO.Handle(CHANNEL, ...) end
end

-- Every Refresh carries SHEET_MARK: it is how dc_inventory.lua knows this is the
-- new sheet and need not be sent the old grid's cells (the old addon sends none).
local SHEET_MARK = 2
local function refresh()
    send("Refresh", SHEET_MARK)
end

-- Another screen can claim the right-click (the Jeweler's Unsocket tab loads an item
-- with it). While any claim is true, nothing on this sheet or in the potion hook
-- below acts on a right-click: there is exactly one winner, whichever PreClick runs
-- first.
DC.rightClickClaims = DC.rightClickClaims or {}
function DC.ClaimRightClick(claim)
    DC.rightClickClaims[#DC.rightClickClaims + 1] = claim
end
local function claimed()
    for _, claim in ipairs(DC.rightClickClaims) do
        if claim() then return true end
    end
    return false
end

local function status(message, isError)
    local line = _G["DiablocraftInventoryFrameStatus"]
    if not line then return end
    line:SetText(message or "")
    if isError then line:SetTextColor(1, 0.4, 0.3) else line:SetTextColor(0.7, 0.7, 0.7) end
end

-- Grouping only, never rounding: the digits are the server's. Econ.Gold owns
-- the thousands separators, so the integer half goes
-- through it and any decimals are put back untouched.
local function grouped(text)
    text = tostring(text or "0")
    local sign, body = text:match("^(%-?)(.*)$")
    local whole, fraction = body:match("^(%d*)%.?(%d*)$")
    if not whole or whole == "" then return text end
    local out = DC.Econ and DC.Econ.Gold(whole) or whole
    if fraction ~= "" then out = out .. "." .. fraction end
    return sign .. out
end

local function value(key)
    return sheet and sheet[key] or nil
end

-- One Details row, formatted the way D3 formats that kind of number. tonumber
-- and string.format are presentation; every value came finished from C++.
local function formatted(kind, raw)
    local number = tonumber(raw)
    if not number then return "-" end
    if kind == "int" then return grouped(string.format("%.0f", number)) end
    if kind == "pct" then return grouped(string.format("%.2f", number)) .. "%" end
    return grouped(string.format("%.2f", number))
end

-- ----------------------------------------------------------------- flashing

-- A stat number that moved turns green (up) or red (down) and fades back to its
-- own colour (the mockup's chg-up / chg-down). Driven by the watcher's OnUpdate.
local FLASH_SECONDS = 1.2
local GREEN, RED = {0.35, 1, 0.35}, {1, 0.3, 0.3}
local flashing = {}

local function paint(text, base)
    text.dcBase = base
    text:SetTextColor(base[1], base[2], base[3])
end

local function flash(text, direction)
    if not direction or not text.dcBase then return end
    text.dcFlash = {age = 0, tint = direction > 0 and GREEN or RED}
    flashing[text] = true
    local tint = text.dcFlash.tint
    text:SetTextColor(tint[1], tint[2], tint[3])
end

local function stepFlashes(delta)
    for text in pairs(flashing) do
        local state = text.dcFlash
        if not state then
            flashing[text] = nil
        else
            state.age = state.age + delta
            local k = state.age / FLASH_SECONDS
            if k >= 1 then
                text.dcFlash = nil
                flashing[text] = nil
                text:SetTextColor(text.dcBase[1], text.dcBase[2], text.dcBase[3])
            else
                local base, tint = text.dcBase, state.tint
                text:SetTextColor(tint[1] + (base[1] - tint[1]) * k, tint[2] + (base[2] - tint[2]) * k,
                    tint[3] + (base[3] - tint[3]) * k)
            end
        end
    end
end

-- DC.Inventory_FlashStep is the watcher's tick, published so the headless test
-- can drive the fade without a frame clock.
DC.Inventory_FlashStep = stepFlashes

-- ------------------------------------------------------------ the stat block

-- DCSHEET arrives as B | V | V | ... | E. Nothing is drawn from a half-received
-- block: E is what promotes the buffer, so a dropped packet leaves the previous
-- sheet in place rather than a screen of blanks.
local function diff(old, new)
    local out = {}
    if not old then return out end
    for key, raw in pairs(new) do
        local a, b = tonumber(old[key]), tonumber(raw)
        if a and b and math.abs(a - b) > 1e-6 then out[key] = b > a and 1 or -1 end
    end
    return out
end

local function receiveSheet(payload)
    local head, body = payload:match("^(%a)|?(.*)$")
    if not head then return end
    if head == "N" then
        sheet, sheetBuffer, changed = nil, nil, {}
        return
    end
    if head == "B" then
        sheetBuffer = {level = body}
        return
    end
    if head == "V" then
        if not sheetBuffer then return end
        for pair in body:gmatch("[^;]+") do
            local key, raw = pair:match("^([%w_]+)=(-?[%d%.]+)$")
            if key then sheetBuffer[key] = raw end
        end
        return
    end
    if head == "E" and sheetBuffer then
        changed = diff(sheet, sheetBuffer)
        sheet = sheetBuffer
        sheetBuffer = nil
        if frame and frame:IsShown() then DC.Inventory_Redraw() end
        if sidePanel and sidePanel:IsShown() and sideMode == "details" then DC.Details_Redraw() end
        changed = {}
    end
end

-- --------------------------------------------------------------- slot drawing

local function slotId(button)
    return button.equipSlot + 1
end

-- The border colour: the ROLLED rarity when dc_tooltip.lua holds a record for the
-- worn item (a Legendary is orange, a Set item green, whatever the base item's
-- stock quality), else the stock quality. The client only has the records once the
-- server has pushed them; DCOnItemRecords below redraws when they arrive.
local function borderColour(button, quality)
    local rolled = DCItemRarity and button.equipSlot ~= POTION_SLOT and DCItemRarity(255, button.equipSlot)
    return RARITY_COLOUR[rolled or ""] or QUALITY_COLOUR[quality or 1] or "grey"
end

local function drawWorn(button)
    local link, texture, quality
    if button.equipSlot == POTION_SLOT then
        local entry = snapshot and snapshot.potion and snapshot.potion.entry
        if entry then
            texture = GetItemIcon and GetItemIcon(entry) or nil
            local _, _, q = GetItemInfo(entry)
            quality = q
        end
    else
        local id = slotId(button)
        texture = GetInventoryItemTexture("player", id)
        link = texture and GetInventoryItemLink("player", id)
        if link then
            local _, _, q = GetItemInfo(link)
            quality = q
        end
    end
    if texture then
        DC.SetArt(button.rarity, "slot-rarity-" .. borderColour(button, quality))
        button.icon:SetTexture(texture)
        button.icon:Show()
        button.empty:SetAlpha(0)
        local locked = button.equipSlot ~= POTION_SLOT and IsInventoryItemLocked and IsInventoryItemLocked(slotId(button))
        button.icon:SetVertexColor(locked and 0.4 or 1, locked and 0.4 or 1, locked and 0.4 or 1)
    else
        button.rarity:SetTexture(nil)
        button.icon:SetTexture(nil)
        button.empty:SetAlpha(0.35)
    end
    button.filled = texture and true or false
end

local function drawSlots()
    for _, button in ipairs(gearButtons) do drawWorn(button) end
    for _, button in ipairs(cosmeticButtons) do drawWorn(button) end
end

-- Published for the tests.
DC.Inventory_DrawSlots = drawSlots

-- dc_tooltip.lua calls this when its item records change, so a border drawn
-- before the records arrived is redrawn with the rolled rarity.
function DCOnItemRecords()
    if frame and frame:IsShown() then drawSlots() end
end

function DC.SheetSlot_OnLoad(self)
    self:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    self:RegisterForDrag("LeftButton")
    self.back, self.rarity = part(self, "Back"), part(self, "Rarity")
    self.icon, self.empty = part(self, "Icon"), part(self, "Empty")
    DC.SetArt(self.back, "slot")
    DC.SetArt(self:GetHighlightTexture(), "slot-hover")
    self.rarity:SetTexture(nil)
    self.icon:SetTexture(nil)
end

-- ------------------------------------------------------------------ tooltips

function DC.SheetSlot_OnEnter(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    if self.equipSlot == POTION_SLOT then
        local entry = snapshot and snapshot.potion and snapshot.potion.entry
        if entry then
            GameTooltip:SetHyperlink("item:" .. entry)
        else
            GameTooltip:AddLine("Potion")
            GameTooltip:AddLine("Empty slot", 0.62, 0.62, 0.62)
        end
        GameTooltip:Show()
        return
    end
    if self.filled then
        -- The stock item tooltip, with the owner carrying bagID/slotID the way an
        -- ElvUI bag button does, so dc_tooltip.lua draws the rolled affixes.
        GameTooltip:SetInventoryItem("player", slotId(self))
    else
        GameTooltip:AddLine(self.label or "Empty")
        GameTooltip:AddLine("Empty slot", 0.62, 0.62, 0.62)
    end
    GameTooltip:Show()
end

function DC.SheetSlot_OnLeave()
    GameTooltip:Hide()
end

-- --------------------------------------------------------- equip and unequip

local function refuse(message)
    status(message, true)
    if UIErrorsFrame then UIErrorsFrame:AddMessage(message, 1, 0.1, 0.1) end
end

-- What the cursor holds, in the one question a drop needs: does it fit here?
-- nil answer means the client does not know the item yet (GetItemInfo is empty
-- for an uncached one), and then the drop is sent and the server decides.
local function cursorFits(slot)
    local _, itemId, link = GetCursorInfo()
    local info = {GetItemInfo(link or itemId or "")}
    local loc = info[9]
    if not loc then return true end
    local allowed = FITS[slot]
    return allowed ~= nil and allowed[loc] == true
end

-- A drop on a worn slot, from a click or from the drag's release. The stock
-- cursor does the equip itself (PickupInventoryItem swaps the cursor's item in
-- and the old one onto the cursor); the potion slot is virtual, so that one is
-- the existing Equip intent with the bag index the cursor came from.
local function dropOn(self)
    if not CursorHasItem() then return end
    local kind = GetCursorInfo()
    if kind ~= "item" then return end
    status("")
    if self.equipSlot == POTION_SLOT then
        local index = DC.StockCursorIndex and DC.StockCursorIndex()
        -- A worn item is bag 255 and below 23 (25500-25522): not a bag cell, so
        -- not a potion. The backpack's own cells are 255, 23 and up.
        if not index or (index >= 25500 and index < 25523) then
            refuse("That doesn't go there.")
            return
        end
        ClearCursor()
        send("Equip", index)
        return
    end
    if not cursorFits(self.equipSlot) then
        refuse("That doesn't go there.")
        return
    end
    PickupInventoryItem(slotId(self))
end

function DC.SheetSlot_OnReceiveDrag(self)
    dropOn(self)
end

-- A worn item is dragged with the stock cursor: it can be dropped into any
-- ElvUI bag slot, which is the unequip. The potion slot is virtual and has no
-- stock pickup, so it unequips by right-click only.
function DC.SheetSlot_OnDragStart(self)
    if self.equipSlot == POTION_SLOT or not self.filled then return end
    status("")
    PickupInventoryItem(slotId(self))
end

-- Left-click drops a held item here (the stock paperdoll does the same), shift-
-- left-click shares the rolled item, right-click takes the item off - the
-- server picks the bag cell, as it does everywhere.
function DC.SheetSlot_OnClick(self, button)
    if button == "LeftButton" then
        if CursorHasItem() then
            dropOn(self)
            return
        end
        if IsModifiedClick("CHATLINK") and DCRequestItemLink and GameTooltip:GetOwner() == self
           and GameTooltip.dcGuid then
            DCRequestItemLink(GameTooltip.dcGuid)
        end
        return
    end
    if button ~= "RightButton" or not self.filled then return end
    -- Shift-right-click opens the socket window for the worn item, the stock
    -- gesture, and never unequips it. SocketInventoryItem is the client's own
    -- entry point the stock paperdoll uses here; dc_jeweler.lua's hook turns it
    -- into the Sockets window and puts the client's own ItemSocketingFrame away.
    -- The potion slot (POTION_SLOT) has no stock slot id, so it is left alone.
    if self.equipSlot >= 0 and self.equipSlot <= 18 and SocketInventoryItem
       and IsModifiedClick and IsModifiedClick("SOCKETITEM") then
        SocketInventoryItem(self.equipSlot + 1)
        return
    end
    -- The Jeweler's Unsocket tab loads the worn item with this right-click instead
    -- (dc_jeweler.lua, a PreClick hook on this button); it wins.
    if claimed() then return end
    -- The stash is open: the worn item goes straight into its open tab, one server
    -- move (unequip and deposit together, or neither - the item stays worn).
    if DC.StashIsOpen and DC.StashIsOpen() then
        if InCombatLockdown and InCombatLockdown() then return end
        DC.DepositToOpenTab(25500 + self.equipSlot)
        return
    end
    status("")
    send("Unequip", self.equipSlot)
end


-- ------------------------------------------------- a potion in the bags: equip it

-- Right-click a potion in the bags EQUIPS it (as the old
-- grid's right-click did) instead of the stock Use, which would drink it. Which
-- items are potions is the server's (snapshot.potionEntries, dc_base_item.slot =
-- 'potion'); the server re-checks on every Equip.
--
-- NO STOCK GLOBAL IS WRITTEN: ContainerFrameItemButton_OnClick and UseContainerItem
-- stay the originals. This is a per-button HookScript("PreClick") / ("PostClick"),
-- the same technique and the same rules as dc_jeweler.lua's right-click loading:
-- only a plain right-click with an empty cursor, never in combat, and a hook cannot
-- cancel the click, so PreClick points the button at an EMPTY slot of its own bag
-- for that one click (the stock OnClick reads GetParent():GetID() and GetID()) and
-- PostClick puts the id back. A full bag has no empty slot: then the stock click
-- runs and nothing is lost.
--
-- Who wins: another screen that wants the right-click (the Jeweler's Unsocket tab)
-- registers a claim with DC.ClaimRightClick; while any claim is true this hook does
-- nothing at all, whichever PreClick runs first. Two hooks that both change the id
-- would fight; with a claim there is only ever one.
local potionSet, potionHooked, potionBlanked = {}, {}, {}

local function bagButtons()
    local found = {}
    for frameNo = 1, (NUM_CONTAINER_FRAMES or 13) do
        for itemNo = 1, (MAX_CONTAINER_ITEMS or 36) do
            local b = _G["ContainerFrame" .. frameNo .. "Item" .. itemNo]
            if b then found[#found + 1] = b end
        end
    end
    local E = _G.ElvUI and _G.ElvUI[1]
    local Bags = E and E.GetModule and E:GetModule("Bags", true)
    local holder = Bags and Bags.BagFrame and Bags.BagFrame.Bags
    if holder then
        for bagId = 0, 4 do
            for _, b in pairs(holder[bagId] or {}) do
                if type(b) == "table" and b.HookScript then found[#found + 1] = b end
            end
        end
    end
    return found
end

local function restorePotionIds()
    for button, id in pairs(potionBlanked) do button:SetID(id) end
    potionBlanked = {}
end

-- Points the button at a cell that holds nothing for this one click, so the stock
-- OnClick (use, equip, open) acts on nothing. A full bag has no empty cell; a cell
-- past the bag's last slot holds nothing either.
local function blankButton(self, bag, slot)
    local spare
    for candidate = 1, (GetContainerNumSlots and GetContainerNumSlots(bag) or 0) do
        if not GetContainerItemLink(bag, candidate) then spare = candidate; break end
    end
    spare = spare or ((GetContainerNumSlots and GetContainerNumSlots(bag) or 0) + 1)
    potionBlanked[self] = slot
    self:SetID(spare)
end

-- One right-click rule for a bag button, in this order:
--   1. a claim (the Jeweler's Unsocket tab) - this hook does nothing at all;
--   2. the stash is open - the item is deposited into the open tab, and the stock
--      click is blanked so it is NOT also used or equipped;
--   3. a potion the server named - equipped into the sheet's potion slot;
--   4. otherwise the stock click runs untouched.
-- The Blacksmith registers no claim, so with it open the stash still wins.
local function bagPreClick(self, mouseButton)
    if mouseButton ~= "RightButton" then return end
    if InCombatLockdown and InCombatLockdown() then return end
    if claimed() then return end
    restorePotionIds()
    if GetCursorInfo and GetCursorInfo() then return end
    if (IsShiftKeyDown and IsShiftKeyDown()) or (IsControlKeyDown and IsControlKeyDown())
       or (IsAltKeyDown and IsAltKeyDown()) then return end
    local parent = self:GetParent()
    local bag, slot = parent and parent:GetID(), self:GetID()
    if not bag or not slot or slot < 1 then return end
    local link = GetContainerItemLink(bag, slot)
    if not link then return end
    local index = DC.BagIndex and DC.BagIndex(bag, slot)
    if not index then return end
    if DC.StashIsOpen and DC.StashIsOpen() then
        if DC.DepositToOpenTab(index) then blankButton(self, bag, slot) end
        return
    end
    local entry = tonumber(link:match("item:(%d+)"))
    if not entry or not potionSet[entry] then return end
    status("")
    send("Equip", index)
    blankButton(self, bag, slot)
end

local function bagPostClick(self)
    local id = potionBlanked[self]
    if id then
        self:SetID(id)
        potionBlanked[self] = nil
    end
end

-- Hook every bag button that exists and is not hooked yet. ElvUI builds its slots
-- when the bags are first opened, so this runs on every sheet open, when the stash
-- opens, and about once a second while either is up.
local function scanBagButtons()
    potionSet = {}
    for _, entry in ipairs((snapshot and snapshot.potionEntries) or {}) do potionSet[entry] = true end
    for _, button in ipairs(bagButtons()) do
        if not potionHooked[button] then
            potionHooked[button] = true
            button:HookScript("PreClick", bagPreClick)
            button:HookScript("PostClick", bagPostClick)
        end
    end
end
DC.Inventory_ScanBagButtons = scanBagButtons
DC.Inventory_ScanPotionButtons = scanBagButtons
DC.Inventory_RestoreIds = restorePotionIds

-- ------------------------------------------------------------------ redraw

local MAIN_COLOUR, STAT_COLOUR = {1, 0.82, 0.25}, {1, 1, 1}

local function mainKey()
    local name = snapshot and snapshot.mainStat
    for _, entry in ipairs(PRIMARIES) do
        if entry.name == name then return entry.key end
    end
    return nil
end

-- The Paragon colour: the blue the old "Paragon N" text wore (0.55, 0.73, 1).
DC.PARAGON_HEX = "8cbaff"

local function drawHeader()
    local class = UnitClass and UnitClass("player") or ""
    local level = snapshot and snapshot.level or UnitLevel("player") or 1
    local paragon = snapshot and tonumber(snapshot.paragon) or 0
    nameText:SetText(UnitName("player") or "")
    -- D3's header: "Level 70 (200) Barbarian", the bracketed Paragon level in the
    -- Paragon colour. Paragon 0 is "Level 70 Barbarian" alone; the Paragon button
    -- below it always opens the page.
    local bracket = paragon > 0 and (" |cff" .. DC.PARAGON_HEX .. "(" .. paragon .. ")|r") or ""
    levelText:SetText("Level " .. level .. bracket .. " " .. (class or ""))
end

local function drawStats()
    local main = mainKey()
    for _, entry in ipairs(PRIMARIES) do
        local text = primaryText[entry.key]
        text:SetText(sheet and formatted("int", value(entry.key)) or "-")
        paint(text, entry.key == main and MAIN_COLOUR or STAT_COLOUR)
        if entry.key == main then
            text.label:SetTextColor(MAIN_COLOUR[1], MAIN_COLOUR[2], MAIN_COLOUR[3])
        else
            text.label:SetTextColor(0.78, 0.78, 0.78)
        end
        flash(text, changed[entry.key])
    end
    for _, entry in ipairs(SUMMARIES) do
        local text = summaryText[entry.key]
        text:SetText(sheet and formatted("int", value(entry.key)) or "-")
        paint(text, STAT_COLOUR)
        flash(text, changed[entry.key])
    end
end

-- The line under the stats is GOLD ONLY. Every other currency
-- is in the Materials panel, which is the screen that says it lists them all.
local function drawFunds()
    local balance = DC.Econ and DC.Econ.Balance() or (snapshot and snapshot.gold) or "0"
    fundsText:SetText((DC.Econ and DC.Econ.Gold(balance) or balance) .. " gold")
end

function DC.Inventory_Redraw()
    if not frame then return end
    drawHeader()
    drawStats()
    drawFunds()
    drawSlots()
    if sidePanel and sidePanel:IsShown() and sideMode == "materials" then DC.Materials_Redraw() end
end

-- The rows the Details panel is about to draw, flattened: group headers, stat
-- rows, and one row per element actually carried (D3 lists "Cold Damage
-- Increase" on its own line, and a list crammed into the value column is what
-- would collide with the label). `key` is the DCSHEET key the row shows, so a
-- changed value can flash.
-- The "fury" key is the class's primary resource maximum (dc_inventory.cpp, Stat::MaxFury),
-- so its row names that resource: the primary row of the generated ResourceNames.lua (Fury
-- for a Barbarian, Arcane Power for a Wizard), else the client's own word for the player's
-- power, else the spec's neutral label.
local function resourceLabel(spec)
    local classToken
    if UnitClass then classToken = select(2, UnitClass("player")) end
    local rows = classToken and DC.ResourceNames and DC.ResourceNames[classToken]
    for _, entry in pairs(rows or {}) do
        if entry.role == "primary" and entry.name then return "Maximum " .. entry.name end
    end
    local powerToken
    if UnitPowerType then powerToken = select(2, UnitPowerType("player")) end
    local word = powerToken and _G[powerToken]
    if type(word) == "string" and word ~= "" then return "Maximum " .. word end
    return spec.label
end

local function detailsList()
    local list = {}
    for _, spec in ipairs(DETAILS) do
        if spec.group then
            list[#list + 1] = {group = spec.group:upper()}
        elseif spec.kind == "range" then
            -- Two keys, one row: "min - max", and a single number only when the
            -- range has collapsed. Both digits are the server's.
            local low, high = value(spec.key), value(spec.upper)
            local text = "-"
            if sheet then
                local a, b = formatted("int", low), formatted("int", high)
                text = a == b and a or (a .. " - " .. b)
            end
            list[#list + 1] = {label = spec.label, text = text, key = spec.key}
        elseif spec.kind == "ele" then
            local any = false
            for index = 1, #ELEMENTS do
                local raw = tonumber(value("ele" .. (index - 1)))
                if raw and raw ~= 0 then
                    any = true
                    list[#list + 1] = {label = ELEMENTS[index] .. " Damage Increase",
                                       text = formatted("pct", raw), key = "ele" .. (index - 1)}
                end
            end
            if not any then
                list[#list + 1] = {label = spec.label, text = sheet and formatted("pct", 0) or "-"}
            end
        elseif spec.kind == "res" then
            -- The element totals D3's sheet carries (res0..res6, dc_inventory.cpp),
            -- shown only where they rise above All Resistance, which already has
            -- its own row. Each is a whole number, like All Resistance.
            local base = tonumber(value("resall"))
            for index = 1, #ELEMENTS do
                local raw = tonumber(value("res" .. (index - 1)))
                if raw and base and raw ~= base then
                    list[#list + 1] = {label = ELEMENTS[index] .. " Resistance",
                                       text = formatted("int", raw), key = "res" .. (index - 1)}
                end
            end
        else
            list[#list + 1] = {label = spec.resource and resourceLabel(spec) or spec.label, key = spec.key,
                               text = sheet and formatted(spec.kind, value(spec.key)) or "-"}
        end
    end
    return list
end

-- A pooled row: the panel's row count changes with the elements carried.
local function sideRow(store, parent, index)
    local row = store[index]
    if row then return row end
    row = CreateFrame("Frame", nil, parent)
    row:SetWidth(SIDE_ROW_W)
    row:SetHeight(ROW_STEP - 1)
    row.left = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    row.left:SetPoint("TOPLEFT", row, "TOPLEFT", 0, 0)
    row.left:SetWidth(LABEL_W)
    row.left:SetJustifyH("LEFT")
    row.right = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    row.right:SetPoint("TOPRIGHT", row, "TOPRIGHT", 0, 0)
    row.right:SetWidth(VALUE_W)
    row.right:SetJustifyH("RIGHT")
    store[index] = row
    return row
end

function DC.Details_Redraw()
    if not detailsScroll then return end
    local list = detailsList()
    local y = 0
    for index, entry in ipairs(list) do
        local row = sideRow(detailsRows, detailsScroll.content, index)
        -- Re-anchored on every redraw, so the old point has to go first: SetPoint
        -- adds an anchor, it does not replace one.
        row:ClearAllPoints()
        if entry.group then
            row:SetPoint("TOPLEFT", detailsScroll.content, "TOPLEFT", 0, -y - 6)
            row.left:SetText(entry.group)
            row.left:SetTextColor(0.95, 0.78, 0.35)
            row.right:SetText("")
            y = y + GROUP_STEP
        else
            row:SetPoint("TOPLEFT", detailsScroll.content, "TOPLEFT", 12, -y)
            row.left:SetText(entry.label)
            row.left:SetTextColor(0.85, 0.85, 0.85)
            row.right:SetText(entry.text)
            paint(row.right, {1, 1, 1})
            if entry.key then flash(row.right, changed[entry.key]) end
            y = y + ROW_STEP
        end
        row:Show()
    end
    for index = #list + 1, #detailsRows do detailsRows[index]:Hide() end
    detailsScroll.content:SetHeight(y + 12)
end

function DC.Materials_Redraw()
    if not materialsFrame then return end
    local currencies = (DC.Econ and (DC.Econ.CURRENCIES or DC.Econ.MATERIALS)) or {}
    local y = 0
    for index, currency in ipairs(currencies) do
        local row = sideRow(materialsRows, materialsFrame, index)
        row:ClearAllPoints()
        row:SetHeight(22)
        row:SetPoint("TOPLEFT", materialsFrame, "TOPLEFT", 0, -y)
        if not row.icon then
            row.icon = row:CreateTexture(nil, "ARTWORK")
            row.icon:SetWidth(18)
            row.icon:SetHeight(18)
            row.icon:SetPoint("LEFT", row, "LEFT", 0, 0)
            row.left:ClearAllPoints()
            row.left:SetPoint("LEFT", row, "LEFT", 26, 0)
            row.left:SetWidth(LABEL_W - 26)
            row.right:ClearAllPoints()
            row.right:SetPoint("RIGHT", row, "RIGHT", 0, 0)
        end
        row.icon:SetTexture(currency.entry and GetItemIcon and GetItemIcon(currency.entry) or nil)
        row.left:SetText(currency.name)
        row.left:SetTextColor(0.85, 0.85, 0.85)
        -- The same fallback chain the funds line uses: the live DCECON snapshot
        -- first, the server's own snapshot strings behind it. Neither ever
        -- becomes a Lua number - an account pool runs past 2^53.
        local amount = (DC.Econ and DC.Econ.Material(currency.entry))
            or (snapshot and snapshot.materials and (snapshot.materials[currency.entry]
                or snapshot.materials[tostring(currency.entry)])) or "0"
        row.right:SetText(DC.Econ and DC.Econ.Gold(amount) or tostring(amount))
        row.right:SetTextColor(1, 1, 1)
        row:Show()
        y = y + 26
    end
    for index = #currencies + 1, #materialsRows do materialsRows[index]:Hide() end
    materialsFrame.note:ClearAllPoints()
    materialsFrame.note:SetPoint("TOPLEFT", materialsFrame, "TOPLEFT", 0, -y - 8)
end

-- ------------------------------------------------------------------- views

-- Cosmetics replaces the paperdoll in place and comes back with Back.
-- Nothing else on the panel moves.
local function showCosmetics(on)
    cosmeticsShown = on and true or false
    for _, button in ipairs(gearButtons) do
        if cosmeticsShown then button:Hide() else button:Show() end
    end
    for _, button in ipairs(cosmeticButtons) do
        if cosmeticsShown then button:Show() else button:Hide() end
    end
    for _, label in ipairs(frame.cosmeticLabels) do
        if cosmeticsShown then label:Show() else label:Hide() end
    end
    if cosmeticsShown then frame.cosmeticNote:Show() else frame.cosmeticNote:Hide() end
    if model then
        if cosmeticsShown then model:Hide() else model:Show() end
    end
    -- 3.3.5a has no SetShown; Show/Hide is the whole API here.
    frame.cosmeticsButton:SetText(cosmeticsShown and "EQUIPMENT" or "COSMETICS")
end
DC.Inventory_ShowCosmetics = showCosmetics

-- The panel opens against the right edge of the window.
-- Re-placed on every open, so a panel dragged somewhere during a session is
-- back where it belongs the next time it is opened.
local function placeAtRightEdge(self)
    self:ClearAllPoints()
    self:SetPoint("RIGHT", UIParent, "RIGHT", 0, 0)
end

function DC.Inventory_Hide()
    if frame then frame:Hide() end
end

function DC.Inventory_OnShow()
    refresh()
    DC.Inventory_Redraw()
    -- Escape goes through the proxy: it is shown whenever the sheet is.
    if escapeProxy then
        escapeBusy = true
        escapeProxy:Show()
        escapeBusy = false
    end
end

function DC.Inventory_OnHide()
    if sidePanel then sidePanel:Hide() end
    sideMode = nil
    showCosmetics(false)
    if escapeProxy then
        escapeBusy = true
        escapeProxy:Hide()
        escapeBusy = false
    end
end

-- Escape closes the side panel first, then the sheet. UISpecialFrames hides
-- every listed frame that is shown, so only the proxy is listed and this decides
-- what its hiding means. Re-showing the proxy keeps the next Escape ours.
function DC.Escape_OnHide(self)
    if escapeBusy then return end
    if sidePanel and sidePanel:IsShown() then
        sidePanel:Hide()
        sideMode = nil
        escapeBusy = true
        self:Show()
        escapeBusy = false
        return
    end
    if frame then frame:Hide() end
end

local function openParagon()
    -- dc_paragon.lua is AIO-delivered and publishes this; the slash command is
    -- the same entry point and is the fallback if the screen has not loaded yet.
    if DiablocraftOpenParagon then
        DiablocraftOpenParagon()
    elseif SlashCmdList and SlashCmdList.DIABLOCRAFTPARAGON then
        SlashCmdList.DIABLOCRAFTPARAGON("")
    end
end

-- The Paragon page's own toggle: a shown page is put away, otherwise it is asked
-- for (the server answers the Open and the page shows itself). The frame is
-- dc_paragon.lua's and AIO-delivered; without it this is just openParagon's
-- fallback, so an addon newer than the server's Lua does nothing worse than the
-- header's button does.
function DC.ToggleParagon()
    local page = _G.DiablocraftParagonFrame
    if page and page:IsShown() then
        page:Hide()
        return
    end
    openParagon()
end

-- The Key Bindings entry (Bindings.xml: TORMENT_PARAGON) and its words.
BINDING_HEADER_TORMENT = "Torment"
BINDING_NAME_TORMENT_PARAGON = "Toggle Paragon"

-- N is the default, once per character: talents are removed, so the stock N
-- (TOGGLETALENTS) is free; anything else on N is the player's own choice and is
-- left alone. Decided once - if the player later unbinds or rebinds it, it stays
-- theirs. A real SetBinding + SaveBindings, no stock global replaced.
function DC.BindParagonKey()
    if not (GetBindingAction and SetBinding and SaveBindings and GetCurrentBindingSet) then return end
    DiablocraftUI = DiablocraftUI or {}
    if DiablocraftUI.paragonKey then return end
    DiablocraftUI.paragonKey = true
    local current = GetBindingAction("N")
    if current ~= nil and current ~= "" and current ~= "TOGGLETALENTS" then return end
    if SetBinding("N", "TORMENT_PARAGON") then SaveBindings(GetCurrentBindingSet()) end
end

-- The side panel hangs off the sheet's left edge, flush against it;
-- anchored in the XML as well, so it follows the sheet.
local function attachToCharacter(self)
    if not frame then return end
    self:ClearAllPoints()
    self:SetPoint("TOPRIGHT", frame, "TOPLEFT", 0, 0)
end

-- One panel, two contents. Pressing the other button swaps it; pressing the
-- open one's own button closes it.
local function toggleSide(mode)
    if not sidePanel then return end
    if sidePanel:IsShown() and sideMode == mode then
        sidePanel:Hide()
        sideMode = nil
        return
    end
    sideMode = mode
    _G["DiablocraftSidePanelTitle"]:SetText(mode == "details" and "Details" or "Materials")
    if mode == "details" then
        materialsFrame:Hide()
        detailsScroll:Show()
        DC.Details_Redraw()
    else
        detailsScroll:Hide()
        materialsFrame:Show()
        DC.Materials_Redraw()
    end
    sidePanel:Show()
end
DC.Sheet_ToggleSide = toggleSide

function DC.Side_Close()
    if sidePanel then sidePanel:Hide() end
    sideMode = nil
end

-- Opens without toggling.
function DC.Inventory_Open()
    if not frame then return end
    if frame:IsShown() then return end
    placeAtRightEdge(frame)
    frame:Show()
end

function DC.Inventory_Toggle()
    if not frame then return end
    if frame:IsShown() then
        frame:Hide()
        return
    end
    DC.Inventory_Open()
end

-- -------------------------------------------------------------------- build

local function label(parent, font, x, y, text, justify)
    local line = parent:CreateFontString(nil, "OVERLAY", font)
    line:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    line:SetJustifyH(justify or "LEFT")
    if text then line:SetText(text) end
    return line
end

local function button(parent, name, text, width, height, x, y, handler)
    -- The native WoW button, as the Jeweler's (UIPanelButtonTemplate).
    local made = CreateFrame("Button", name, parent, "UIPanelButtonTemplate")
    made:SetWidth(width)
    made:SetHeight(height)
    made:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    made:SetText(text)
    made:SetScript("OnClick", handler)
    styled("SkinButton", made, DC.Style and DC.Style.BUTTON_STATES)
    return made
end

local function tip(owner, title, lines)
    GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
    GameTooltip:AddLine(title)
    for _, line in ipairs(lines) do GameTooltip:AddLine(line, 0.85, 0.85, 0.85, true) end
    GameTooltip:Show()
end

-- Tooltips on the stats, one line each (the mockup's STAT_TIP). The main stat
-- says what it does; the other two attributes say they are not the class's.
local function statTip(owner, entry)
    local class = UnitClass and UnitClass("player") or "your"
    if entry.key == "vit" then
        tip(owner, entry.name, {"Increases your Life before Life bonuses."})
    elseif entry.key == mainKey() then
        local points = sheet and formatted("pct", value(entry.key)) or "-"
        tip(owner, entry.name, {"Your main stat. Increases your damage by " .. points .. "."})
    else
        tip(owner, entry.name, {"Not a " .. class .. " stat."})
    end
end

local function buildHeader(self)
    nameText = label(self, "GameFontNormalLarge", MARGIN, -26)
    levelText = label(self, "GameFontHighlight", MARGIN, -48)
    -- The native WoW button, as Details and Materials are (UIPanelButtonTemplate).
    paragonButton = button(self, "DiablocraftInventoryParagon", "Paragon", 84, 22, MARGIN, -66, openParagon)
    paragonButton:SetScript("OnEnter", function(this)
        tip(this, "Paragon", {"Click to open the Paragon screen."})
    end)
    paragonButton:SetScript("OnLeave", function() GameTooltip:Hide() end)
end

local function buildSlot(self, spec, store, isCosmetic)
    local name = (isCosmetic and "DiablocraftCosmeticSlot" or "DiablocraftGearSlot") .. spec.slot
    local made = CreateFrame("Button", name, self, "DiablocraftSheetSlotTemplate")
    made:SetWidth(SLOT_SIZE)
    made:SetHeight(SLOT_SIZE)
    made:SetPoint("TOPLEFT", self, "TOPLEFT", DOLL_X + spec.x + spec.w / 2 - SLOT_SIZE / 2,
        DOLL_Y - (spec.y + spec.h / 2 - SLOT_SIZE / 2))
    made.equipSlot = spec.slot
    made.label = spec.label
    -- dc_tooltip.lua locate(): the bag and slot of the worn item, the way an
    -- ElvUI bag button carries them (255 is the equipment "bag").
    made.bagID, made.slotID = 255, spec.slot
    local inner = SLOT_SIZE
    made.icon:SetWidth(inner - 10)
    made.icon:SetHeight(inner - 10)
    made.empty:SetWidth(inner - 14)
    made.empty:SetHeight(inner - 14)
    -- Stock paperdoll silhouettes behind an empty slot. They are the client's
    -- own art, used the way stage 1 uses stock art everywhere else (12-ui U1).
    if spec.slot == POTION_SLOT then
        made.empty:SetTexture("Interface\\Icons\\INV_Potion_54")
        made.empty:SetVertexColor(0.5, 0.5, 0.5)
    else
        made.empty:SetTexture("Interface\\PaperDoll\\UI-PaperDoll-Slot-" .. spec.art)
    end
    made.empty:SetAlpha(0.35)
    made:SetFrameLevel(self:GetFrameLevel() + 5)
    store[#store + 1] = made
    return made
end

local function buildPaperdoll(self)
    -- The character behind the slots, built first and pinned to the panel's own
    -- frame level so the slots sit over it (the 3d model is
    -- kept). Guarded: a client that refuses the model must still draw the screen.
    local ok, made = pcall(CreateFrame, "PlayerModel", "DiablocraftInventoryModel", self)
    if ok and made then
        made:SetPoint("TOPLEFT", self, "TOPLEFT", DOLL_X + 112, DOLL_Y)
        made:SetWidth(148)
        made:SetHeight(DOLL)
        made:SetFrameLevel(self:GetFrameLevel())
        pcall(made.SetUnit, made, "player")
        model = made
    end
    for _, spec in ipairs(GEAR) do buildSlot(self, spec, gearButtons, false) end
    self.cosmeticLabels = {}
    for _, spec in ipairs(COSMETIC) do
        buildSlot(self, spec, cosmeticButtons, true):Hide()
        local line = label(self, "GameFontHighlightSmall", DOLL_X + spec.x + spec.w / 2 - (SLOT_SIZE + 24) / 2,
            DOLL_Y - (spec.y + spec.h / 2 + SLOT_SIZE / 2) - 3, spec.label, "CENTER")
        line:SetWidth(SLOT_SIZE + 24)
        line:Hide()
        self.cosmeticLabels[#self.cosmeticLabels + 1] = line
    end
    self.cosmeticNote = label(self, "GameFontHighlightSmall", DOLL_X, DOLL_Y - DOLL + 6,
        "Cosmetics change how you look. They have no stats.", "CENTER")
    self.cosmeticNote:SetWidth(DOLL)
    self.cosmeticNote:SetTextColor(0.7, 0.7, 0.7)
    self.cosmeticNote:Hide()
    self.cosmeticsButton = button(self, "DiablocraftInventoryCosmetics", "COSMETICS", 92, 22,
        DOLL_X + DOLL - 92, DOLL_Y - 2, function() showCosmetics(not cosmeticsShown) end)
end

local function buildStats(self)
    primaryText, summaryText = {}, {}
    local width = DOLL / #PRIMARIES
    for index, entry in ipairs(PRIMARIES) do
        local cell = CreateFrame("Frame", "DiablocraftInventoryStat" .. entry.key, self)
        cell:SetWidth(width)
        cell:SetHeight(34)
        cell:SetPoint("TOPLEFT", self, "TOPLEFT", DOLL_X + (index - 1) * width, -474)
        cell:EnableMouse(true)
        local caption = cell:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        caption:SetPoint("TOP", cell, "TOP", 0, 0)
        caption:SetText(entry.name)
        local amount = cell:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        amount:SetPoint("TOP", cell, "TOP", 0, -14)
        amount.label = caption
        primaryText[entry.key] = amount
        cell:SetScript("OnEnter", function(this) statTip(this, entry) end)
        cell:SetScript("OnLeave", function() GameTooltip:Hide() end)
    end
    -- Damage, Toughness and RECOVERY (Recovery, not
    -- Healing - patch 2.1.0 replaced it). Every one of the three is built in C++
    -- from docs/research/sheet-summary.md; none of it is invented here.
    local swidth = DOLL / #SUMMARIES
    for index, entry in ipairs(SUMMARIES) do
        local cell = CreateFrame("Frame", "DiablocraftInventorySummary" .. entry.key, self)
        cell:SetWidth(swidth)
        cell:SetHeight(48)
        cell:SetPoint("TOPLEFT", self, "TOPLEFT", DOLL_X + (index - 1) * swidth, -516)
        cell:EnableMouse(true)
        local caption = cell:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        caption:SetPoint("TOP", cell, "TOP", 0, 0)
        caption:SetText(entry.name)
        local amount = cell:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        amount:SetPoint("TOP", cell, "TOP", 0, -16)
        summaryText[entry.key] = amount
        cell:SetScript("OnEnter", function(this) tip(this, entry.name, {entry.tip}) end)
        cell:SetScript("OnLeave", function() GameTooltip:Hide() end)
    end
end

local function buildFooter(self)
    button(self, "DiablocraftInventoryDetails", "DETAILS", 108, 28, DOLL_X, -576,
        function() toggleSide("details") end)
    button(self, "DiablocraftInventoryMaterials", "MATERIALS", 108, 28, DOLL_X + 114, -576,
        function() toggleSide("materials") end)
    local coin = self:CreateTexture(nil, "OVERLAY")
    coin:SetWidth(14)
    coin:SetHeight(14)
    coin:SetPoint("TOPRIGHT", self, "TOPRIGHT", -MARGIN, -583)
    DC.SetArt(coin, "coin")
    fundsText = self:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    fundsText:SetPoint("RIGHT", coin, "LEFT", -4, 0)
    fundsText:SetJustifyH("RIGHT")
end

function DC.Inventory_OnLoad(self)
    frame = self
    self:RegisterForDrag("LeftButton")
    self:SetClampedToScreen(true)
    self:SetWidth(PANEL_WIDTH)
    self:SetHeight(PANEL_HEIGHT)
    if not styled("Panel", self) then self:SetBackdrop(STYLE.backdrop) end
    local close = _G[(self:GetName() or "") .. "Close"]
    if close then styled("SkinButton", close, DC.Style and DC.Style.CLOSE_STATES) end
    buildHeader(self)
    buildPaperdoll(self)
    buildStats(self)
    buildFooter(self)
    placeAtRightEdge(self)
    styled("Window", self, "inventory", {close = close, buttons = {paragonButton}})
    escapeProxy = _G["DiablocraftInventoryEscape"]
    if escapeProxy then tinsert(UISpecialFrames, "DiablocraftInventoryEscape") end
    if DC.Econ then
        DC.Econ.OnChange(function()
            if frame and frame:IsShown() then drawFunds() end
            if sidePanel and sidePanel:IsShown() and sideMode == "materials" then DC.Materials_Redraw() end
        end)
    end
    DC.Inventory_Redraw()
end

function DC.Side_OnLoad(self)
    sidePanel = self
    -- No drag and no clamp of its own: this panel is attached to the sheet. It is
    -- anchored to it in the XML, so it follows the sheet wherever that goes and
    -- can never be pulled off it.
    self:SetWidth(SIDE_WIDTH)
    self:SetHeight(PANEL_HEIGHT)
    attachToCharacter(self)
    if not styled("Panel", self) then self:SetBackdrop(STYLE.backdrop) end
    local title = _G[(self:GetName() or "") .. "Title"]
    if title then styled("Title", self, title) end
    local close = _G[(self:GetName() or "") .. "Close"]
    if close then styled("SkinButton", close, DC.Style and DC.Style.CLOSE_STATES) end
    -- Named, always: UIPanelScrollFrameTemplate looks up <name>ScrollBar, and an
    -- unnamed scroll frame is what broke the crafting screen.
    local scroll = CreateFrame("ScrollFrame", "DiablocraftDetailsScroll", self, "UIPanelScrollFrameTemplate")
    styled("Scroll", scroll)
    scroll:SetPoint("TOPLEFT", self, "TOPLEFT", MARGIN_SIDE, TOP)
    scroll:SetWidth(SIDE_ROW_W + 12)
    scroll:SetHeight(PANEL_HEIGHT + TOP - 40)
    local content = CreateFrame("Frame", "DiablocraftDetailsContent", scroll)
    content:SetWidth(SIDE_ROW_W)
    content:SetHeight(1)
    scroll:SetScrollChild(content)
    scroll.content = content
    detailsScroll = scroll
    detailsRows = {}
    materialsFrame = CreateFrame("Frame", "DiablocraftMaterialsList", self)
    materialsFrame:SetPoint("TOPLEFT", self, "TOPLEFT", MARGIN_SIDE, TOP)
    materialsFrame:SetWidth(SIDE_ROW_W + 12)
    materialsFrame:SetHeight(PANEL_HEIGHT + TOP - 40)
    materialsFrame:Hide()
    materialsRows = {}
    materialsFrame.note = materialsFrame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    materialsFrame.note:SetWidth(SIDE_ROW_W)
    materialsFrame.note:SetJustifyH("LEFT")
    materialsFrame.note:SetTextColor(0.7, 0.7, 0.7)
    materialsFrame.note:SetText("Materials are kept on the sheet. They take no bag space.")
end

-- ---------------------------------------------------------------- the bridge

if AIO then
    local handlers = AIO.AddHandlers(CHANNEL, {})

    function handlers.Snapshot(_, data)
        if not data then return end
        snapshot = data
        scanBagButtons()
        DC.Inventory_Redraw()
    end

    function handlers.Error(_, message)
        status(message, true)
    end
end

-- Security G6: DCSHEET and DCPARAGON arrive as server self-whispers, so their
-- sender is the player's own name. Another player whispering the prefix is
-- dropped; a spoofed push must never redraw the sheet or trigger a Refresh.
local function fromServer(sender)
    return sender ~= nil and UnitName ~= nil and sender == UnitName("player")
end

local watcher = CreateFrame("Frame", "DiablocraftInventoryWatcher")
watcher:RegisterEvent("CHAT_MSG_ADDON")
-- The 22 stats C++ owns are pushed at login and after every intent THIS screen
-- sends, but not when gear changes by another route (a right-click or drag in a
-- bag, the client patch's own use/equip), when the character levels, or when
-- Paragon moves. Without asking, the sheet drawn from those numbers stays stale
-- until a relog. These are the stock events that say the numbers moved; the
-- request is debounced so an equipment burst is one round trip. Only while the
-- screen is up - a hidden screen re-reads on open.
--
-- The worn slots themselves are redrawn at once from the stock API on the same
-- events, plus ITEM_LOCK_CHANGED, which is what dims a slot whose item is on the
-- cursor.
watcher:RegisterEvent("PLAYER_EQUIPMENT_CHANGED")
watcher:RegisterEvent("UNIT_INVENTORY_CHANGED")
watcher:RegisterEvent("PLAYER_LEVEL_UP")
watcher:RegisterEvent("ITEM_LOCK_CHANGED")
watcher:RegisterEvent("PLAYER_REGEN_DISABLED")
watcher:RegisterEvent("PLAYER_LOGIN")
local sheetDirty, sheetElapsed = false, 0
watcher:SetScript("OnEvent", function(_, event, arg1, arg2, arg3, sender)
    if event == "CHAT_MSG_ADDON" then
        if arg1 == SHEET_PREFIX and fromServer(sender) then
            receiveSheet(arg2)
        elseif arg1 == PARAGON_PREFIX and arg2 == "E" and fromServer(sender) then
            sheetDirty, sheetElapsed = true, 0
        end
        return
    end
    if event == "PLAYER_LOGIN" then
        DC.BindParagonKey()
        return
    end
    if event == "PLAYER_REGEN_DISABLED" then
        restorePotionIds()
        return
    end
    if event == "ITEM_LOCK_CHANGED" then
        if frame and frame:IsShown() then drawSlots() end
        return
    end
    if event == "PLAYER_EQUIPMENT_CHANGED" and frame and frame:IsShown() then drawSlots() end
    if event == "UNIT_INVENTORY_CHANGED" then
        if arg1 ~= "player" then return end
        if frame and frame:IsShown() then drawSlots() end
    end
    sheetDirty, sheetElapsed = true, 0
end)
local scanElapsed = 0
watcher:SetScript("OnUpdate", function(_, delta)
    stepFlashes(delta)
    if (frame and frame:IsShown()) or (DC.StashIsOpen and DC.StashIsOpen()) then
        scanElapsed = scanElapsed + delta
        if scanElapsed >= 1 then
            scanElapsed = 0
            scanBagButtons()
        end
    end
    if not sheetDirty then return end
    sheetElapsed = sheetElapsed + delta
    if sheetElapsed < 0.3 then return end
    sheetDirty = false
    if (frame and frame:IsShown()) or (sidePanel and sidePanel:IsShown()) then
        refresh()
    end
end)

-- ------------------------------------------------------- taking the sheet key

-- C and the character micro-button both run ToggleCharacter("PaperDollFrame") -
-- that is the whole body of the TOGGLECHARACTER0 binding and of
-- CharacterMicroButton's OnClick - so hooking that one global covers both, and
-- any addon that calls it too. 12-ui U2: the character sheet is replaced.
--
-- hooksecurefunc, never a replacement: assigning to ToggleCharacter would taint
-- the global for every caller, and UnregisterAllEvents or a bare :Hide() on
-- CharacterFrame taints the frame itself. The hook runs after the stock
-- function, so the sheet has opened by the time we see it; HideUIPanel is plain
-- FrameXML and puts it away through the panel system's own bookkeeping.
--
-- Only the paperdoll tab is ours. The currency tab is explicitly kept (12-ui
-- U2), and it reaches CharacterFrame through the same global.
if type(ToggleCharacter) == "function" then
    hooksecurefunc("ToggleCharacter", function(tab)
        if tab ~= "PaperDollFrame" then return end
        if not (CharacterFrame and CharacterFrame:IsShown()) then return end
        -- ToggleCharacter shows the sub-frame it was given and then the panel,
        -- so the paperdoll being up is what says this press was ours.
        if not (PaperDollFrame and PaperDollFrame:IsShown()) then return end
        HideUIPanel(CharacterFrame)
        DC.Inventory_Toggle()
    end)
end

SLASH_DIABLOCRAFTINVENTORY1 = "/dcinv"
SlashCmdList.DIABLOCRAFTINVENTORY = function(arg)
    -- Where the two windows actually are, for a layout that looks wrong in game.
    if arg == "frame" then
        for _, panel in ipairs({frame, sidePanel}) do
            if panel then
                DEFAULT_CHAT_FRAME:AddMessage(string.format("Torment panel %s: %dx%d, %s",
                    panel:GetName() or "?", panel:GetWidth() or 0, panel:GetHeight() or 0,
                    panel:IsShown() and "shown" or "hidden"))
            end
        end
        return
    end
    DC.Inventory_Toggle()
end
