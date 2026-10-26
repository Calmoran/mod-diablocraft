-- luacheck: globals DCThrottle DCBlacksmithServer DCRange DCAffixFallback
local AIO = AIO or require("AIO")
local CHANNEL = "DiablocraftCrafting"
if AIO.AddAddon() then
    local handlers = AIO.AddHandlers(CHANNEL, {})
    local contexts = {}
    local names, percent, gemNames = {str="Strength",dex="Dexterity",int="Intelligence"}, {}, {}
    -- The 'elemental' pool row rolls one of these seven (dc_items.cpp ElementalAffixes).
    -- Same names and percent flag as dc_tooltip.lua's describe(), so the window and the tooltip say the same words.
    local ELEMENTAL={dmgphy="Physical Damage Increase",dmgfir="Fire Damage Increase",dmgcol="Cold Damage Increase",dmgpsn="Poison Damage Increase",
        dmgarc="Arcane Damage Increase",dmglit="Lightning Damage Increase",dmghol="Holy Damage Increase"}
    -- The 'resist' pool row rolls one of these six (D3 resistSingle); flat, like dc_tooltip.lua's.
    local RESIST={resphy="Physical Resistance",resfir="Fire Resistance",rescol="Cold Resistance",respsn="Poison Resistance",
        resarc="Arcane Resistance",reslit="Lightning Resistance"}
    -- The base item's slot per entry. The client half needs it to order a rolled item's affix
    -- rows the way the tooltip does once the rows arrive from the bridge (handlers.Tables).
    local baseSlots = {}
    -- Per-slot affix order and kind, and the skill-affix groups, exactly as
    -- dc_tooltip.lua reads them: an affix_id means a different display_order in a
    -- different slot, so these stay keyed by slot.
    local orders, kinds, skillGroups = {}, {}, {}
    local function load()
        local rows=WorldDBQuery("SELECT affix_id,affix_name,is_percent FROM dc_affix_pool UNION SELECT affix_id,affix_name,1 FROM dc_skill_affix")
        if rows then repeat
            local id,name=rows:GetString(0),rows:GetString(1)
            if name and name:find("%S") then names[id]=name end
            percent[id]=rows:GetUInt32(2)~=0
        until not rows:NextRow() end
        names.str,names.dex,names.int="Strength","Dexterity","Intelligence"
        for id,name in pairs(ELEMENTAL) do names[id]=name;percent[id]=true end
        for id,name in pairs(RESIST) do names[id]=name;percent[id]=false end
        rows=WorldDBQuery("SELECT slot,affix_id,kind,display_order FROM dc_affix_pool")
        if rows then repeat
            local slot,id=rows:GetString(0),rows:GetString(1)
            orders[slot]=orders[slot] or {};kinds[slot]=kinds[slot] or {}
            kinds[slot][id]=rows:GetString(2);orders[slot][id]=rows:GetUInt32(3)
        until not rows:NextRow() end
        rows=WorldDBQuery("SELECT affix_id,group_id FROM dc_skill_affix")
        if rows then repeat skillGroups[rows:GetString(0)]=rows:GetString(1) until not rows:NextRow() end
        rows=WorldDBQuery("SELECT entry,name FROM dc_gem_item")
        if rows then repeat gemNames[rows:GetUInt32(0)]=rows:GetString(1) until not rows:NextRow() end
        rows=WorldDBQuery("SELECT entry,slot FROM dc_base_item")
        if rows then repeat baseSlots[rows:GetUInt32(0)]=rows:GetString(1) until not rows:NextRow() end
    end
    load()
    local function show(player,refresh)
        local kind=contexts[player:GetGUIDLow()]
        if not kind then return end
        -- The Blacksmith's window is dc_blacksmith.lua's. This file kept an older Blacksmith
        -- screen behind it; it is gone, so if dc_blacksmith
        -- failed to load, the Blacksmith's gossip opens nothing rather than that old window.
        if kind=="Blacksmith" then
            if DCBlacksmithServer then DCBlacksmithServer.Show(player) end
            return
        end
        local snapshot=DCAccount.Snapshot(player)
        local out={kind=kind,items={},materials={},gold=snapshot.gold,managed=snapshot.managed,refresh=refresh}
        for _,entry in ipairs(DCAccount.MATERIALS) do out.materials[entry]=snapshot.materials[entry] or "0" end
        -- docs/contracts/mystic-enchant-messages.md section 1a: items[] is now only an INDEX that
        -- turns a dragged or right-clicked bag item into its guid; everything the window draws comes
        -- from the DCARTISAN records (N, L, P, T, C, V), and C++ owns the price, the rolls and the
        -- rules. The bag and slot are the client's own numbering (0 backpack and 1..4 the equipped
        -- bags, 1..36 the bag slots; 255 and 0..18 a worn item, as the Jeweler and Blacksmith list
        -- them), the numbering the drag and the right-click claim use. Worn items are listed too, so
        -- a drag or right-click from the character sheet puts the item in.
        local function add(bag,slot,item)
            if not item then return end
            local entry,guid=item:GetEntry(),item:GetGUIDLow()
            -- A rolled item is the only thing the Mystic can enchant (12-ui section 2): a plain
            -- stack is not indexed, so the window cannot offer it.
            local head=CharDBQuery("SELECT rarity FROM dc_item_instance WHERE item_guid="..guid)
            if not head then return end
            out.items[#out.items+1]={guid=guid,entry=entry,name=item:GetName(),rarity=head:GetString(0),bag=bag,slot=slot}
        end
        for slot=0,18 do add(255,slot,player:GetItemByPos(255,slot)) end
        for slot=23,38 do add(0,slot-22,player:GetItemByPos(255,slot)) end
        for bag=19,22 do for slot=0,35 do add(bag-18,slot+1,player:GetItemByPos(bag,slot)) end end
        AIO.Handle(player,CHANNEL,"Show",out)
    end
    -- Walking away closes the Mystic: the shared range watcher
    -- (dc_aio_range.lua) sends Close the moment the Mystic is out of the range every bridge verb is
    -- refused outside (C++ Artisan(), artisan_interaction_range_yards). The Blacksmith's watch is
    -- dc_blacksmith.lua's own.
    for _,entry in ipairs({910000,910001}) do
        RegisterCreatureGossipEvent(entry,1,function(_,player,creature)
            contexts[player:GetGUIDLow()]=creature:GetEntry()==910001 and "Mystic" or "Blacksmith"
            player:GossipComplete();show(player)
            if contexts[player:GetGUIDLow()]=="Mystic" then DCRange.Artisan(player,CHANNEL,910001) end
            return true
        end)
    end
    -- Security G1: show() runs one query per carried item; drop a flood. The Mystic asks it when its
    -- bags or worn gear change while it is up, and marks the answer so it renews only the index.
    function handlers.Refresh(player)
        if DCThrottle.Allow(player, "crafting:refresh", 5, 10) then show(player,true) end
    end
    -- The window's buttons never type `.dc artisan ...` on this half. They
    -- send DCARTISAN on the bridge (docs/contracts/window-bridge.md) and C++ answers with the
    -- records of what the action changed, so nothing here wraps RunCommand and the command is
    -- SEC_ADMINISTRATOR.
    --
    -- The client half draws a rolled item from the reply's F and O rows, which carry the affix id
    -- and its value rather than the line the tooltip prints, so the tables that turn one into the
    -- other are pushed once: the affix names and their percent flag, the display order and kind
    -- per slot, the skill-affix groups, the gem names and the base item slot per entry. They are
    -- this half's own tables, so the window and the tooltip cannot order or name an affix
    -- differently.
    function handlers.Tables(player)
        -- A preset-only line (an item's own dc_item_preset_range row) or a stat no pool holds: named by
        -- dc_tooltip.lua's fallback, read when asked rather than at load (AIO file load order is not ours to depend on).
        if DCAffixFallback then
            for id,info in pairs(DCAffixFallback) do
                if not names[id] then names[id]=info.name;percent[id]=info.percent end
            end
        end
        AIO.Handle(player,CHANNEL,"Tables",{names=names,percent=percent,orders=orders,kinds=kinds,
            skillGroups=skillGroups,gems=gemNames,slots=baseSlots})
    end
    RegisterPlayerEvent(4,function(_,player) contexts[player:GetGUIDLow()]=nil end)
    return
end
-- Mystic (Enchant) window, rebuilt the D3 way.
--
-- Nothing of the stock Enchant window is kept on purpose, so this is a rewrite, not a patch.
-- The flow and texts are the approved mockups': the six steps and the `?` over a property. The look is the
-- Blacksmith and Jeweler's (over the mockups' tan D3 panels): every
-- piece comes from dc_aio_ui.lua (DCUI), so the Mystic cannot drift from them.
--
-- This half draws; it decides nothing. It never works out a price or a roll and never touches
-- damage or stats (12-ui, 00 section 5): the cost, the material counts and the three replacement
-- choices are the server's own values and strings, and the window prints them.
--
-- Steps, from the records the server sends:
--   1 no item            "Place an Item to Replace a Property", the intro, the empty slot
--   2 item placed        "Select a Property to Replace", every enchantable property, the cost
--   3 a property picked  "Replace Property: <cost>", the picked row marked
--   4 the bind warning   the same window under the warning, first enchant only
--   5 a paid roll        "Select Replacement Property", the three choices one second apart
--   6 already enchanted  "Replace a Previously Enchanted Property", the locked row alone
--
-- WIRED (contract docs/contracts/mystic-enchant-messages.md): the window sends `place`, `preview`,
-- `roll` and `pick` on the DCARTISAN bridge
-- and draws the R, B, M, N, L, P, T, C, V, E records that come back, one request in flight at a
-- time (section 1b: the bucket drops a flood silently, and a record carries no request id). It
-- holds the Show payload's items[] only as an index (a bag item's guid by its bag and slot); the
-- item, its lines, its price, its materials and its three choices are all the server's, worded with
-- the item tooltip's own formatter (dc_tooltip.lua's DCAFFIXLINE) so a property reads the same in
-- both. Nothing here has a price, a roll or a rule.
-- luacheck: globals Mystic DCAFFIXLINE DCRARITY DCUI IsAltKeyDown PickupContainerItem PickupInventoryItem
local handlers = AIO.AddHandlers(CHANNEL, {})
local U = DCUI or error("dc_aio_ui.lua must load before dc_crafting.lua")
Mystic = {}
local M = Mystic
local ui = {}
M.ui = ui

local DIAMOND = "Interface\\AddOns\\Torment\\art\\dc_diamond.blp"
-- Stock stand-ins for the tab art (we ship no Mystic art yet): one line each to swap.
local ENCHANT_ICON = "Interface\\Icons\\INV_Enchant_Disenchant"
local TRANSMOGRIFY_ICON = "Interface\\Icons\\Spell_Nature_Polymorph"
-- A property line in the item tooltip's affix blue, so a row reads like the line on the item.
local AFFIX_BLUE = {.49, .49, 1}

------------------------------------------------------------------------------------------------
-- The wire
------------------------------------------------------------------------------------------------
-- Forward: the wiring block below fills these, the tray and the rows are built here.
local requestPreview, placeAt, finishRequest, scanBagButtons, restoreIds
-- The pushed tables (the server half's handlers.Tables) name a property; its line is worded by the
-- item tooltip's own formatter, published as DCAFFIXLINE by dc_tooltip.lua and read lazily, at the
-- moment a row is drawn (AIO file load order is not ours to depend on). Nothing here rewords, adds
-- or computes a value: the numbers are the record's own decimal text turned into numbers, because
-- the formatter compares them (a string never compares against a number).
local names, percent, tables = {}, {}, false
-- The wire state. `pending` is the one request in flight (contract section 1b) with the records read
-- so far; `queued` is the one that waits for its E or X. `previews` is the `?` popover cache keyed
-- guid:seq, `hovered` the row it is open on. `itemIndex` and `slotted` are the Show payload's items[],
-- by guid and by bag and slot, and `goldBalance` is the account balance it last reported.
local REQUEST_TIMEOUT = 3
local pending, queued, hovered, itemIndex, slotted, previews = nil, nil, nil, {}, {}, {}
local goldBalance, scanElapsed, cursorBag, cursorSlot, indexDirty = "0", 0, nil, nil, false
local function splitFields(value, separator)
    local fields = {}
    for field in (value .. separator):gmatch("(.-)" .. separator) do fields[#fields + 1] = field end
    return fields
end
local function lineText(entry, preview)
    -- A Primal can only roll the top, so its `?` entry is a range of one value: worded as that value.
    if preview and entry.min == entry.max and (entry.min2 or 0) == (entry.max2 or 0) then
        entry = {id = entry.id, value = entry.max, value2 = entry.max2, min = entry.min, max = entry.max,
            min2 = entry.min2, max2 = entry.max2}
        preview = false
    end
    -- The sockets of an item are ONE line carrying a count, not a pooled affix (contract section 3).
    if entry.id == "sockets" then
        if preview then return "Sockets ([" .. (entry.min or 0) .. " - " .. (entry.max or 0) .. "])" end
        return "Sockets (" .. (entry.value or 0) .. ")"
    end
    local formatter = DCAFFIXLINE
    if not formatter then return names[entry.id] or entry.id end
    return formatter({id = entry.id, name = names[entry.id], percent = percent[entry.id],
        value = entry.value, value2 = entry.value2, min = entry.min, max = entry.max,
        min2 = (entry.min2 or 0) > 0 and entry.min2 or nil, max2 = (entry.max2 or 0) > 0 and entry.max2 or nil,
        fixed = preview, rerolled = false})
end
-- The two state texts of contract section 3: a line the server marks 2 (gems are in its sockets) or
-- 3 (nothing else can roll there) cannot be replaced, and says why beside its own line.
local LINE_STATE = {[2] = "Remove the socketed gems first.", [3] = "This property cannot be replaced."}
-- One packed line of an L or C record: seq : id : kind : (state :) value : value2 : min : max : min2 : max2.
local function readAffix(value, withState)
    local f = splitFields(value, ":")
    local at = withState and 4 or 3
    local function num(field) return tonumber(f[field]) end
    local entry = {seq = num(1) or 0, id = f[2] or "", kind = f[3] or "primary",
        state = withState and num(4) or nil,
        value = num(at + 1), value2 = num(at + 2), min = num(at + 3), max = num(at + 4),
        min2 = num(at + 5), max2 = num(at + 6)}
    entry.text = lineText(entry, false)
    -- A line the server marks 2 or 3 cannot be replaced; the reason is shown beside its own line
    -- (contract section 3, the shape update 8's guard used).
    if entry.state and entry.state >= 2 then
        entry.text = entry.text .. " - " .. LINE_STATE[entry.state]
    end
    return entry
end
-- One packed V entry (what a line can become): id : kind : min : max : min2 : max2.
local function readPreview(value)
    local f = splitFields(value, ":")
    local entry = {id = f[1] or "", kind = f[2], min = tonumber(f[3]), max = tonumber(f[4]),
        min2 = tonumber(f[5]), max2 = tonumber(f[6])}
    return lineText(entry, true)
end

------------------------------------------------------------------------------------------------
-- The window
------------------------------------------------------------------------------------------------
-- The Blacksmith and Jeweler's look (the approved style): the shared window, a gold title over a
-- small-caps subtitle, the black detail
-- boxes, gold section labels, the stock red buttons, square icon tabs on the right edge and the gold
-- "Your gold" line. Every piece is DCUI's, so the three windows cannot drift apart.
local frame = U.window("DiablocraftCraftingFrame", nil, nil, "mystic")
U.title(frame, "Mystic")
U.subtitle(frame, "ENCHANT")
U.close(frame)
ui.frame = frame

-- The body, where the Blacksmith's tab bodies sit.
local panel = CreateFrame("Frame", nil, frame)
panel:SetPoint("TOPLEFT", 16, -64)
panel:SetPoint("BOTTOMRIGHT", -16, 16)
ui.panel = panel

-- The item: one square slot in a box. An item goes in from the bags or the character sheet, dragged
-- in or right-clicked there. The box takes the drop anywhere inside it; the Show index says which
-- item the cursor is holding (its bag and slot), and placeAt turns it into the guid it sends
-- (contract section 2). A click with an item held drops it the same way.
local tray = U.box(panel, 76)
local NOT_TAKEN = "The Mystic cannot enchant that item."
local function dropHeld()
    if GetCursorInfo() ~= "item" then return end
    local bag, slotNumber = cursorBag, cursorSlot
    cursorBag, cursorSlot = nil, nil
    -- Taken or not, the item leaves the cursor (it goes back where it came from): an item left held
    -- turns every later bag click into a swap and the right-click claim stands aside, so the window
    -- took nothing more until it was reopened.
    ClearCursor()
    if not placeAt(bag, slotNumber) then U.say(NOT_TAKEN, true) end
end
tray:SetScript("OnReceiveDrag", dropHeld)
tray:SetScript("OnClick", dropHeld)
ui.tray = tray
local slot = U.slot(tray, 54)
slot:SetPoint("TOPLEFT", 11, -11)
slot:EnableMouse(false)
slot.icon:Hide()
ui.slot = slot
local itemName = U.text(tray, 78, -18, 420, "GameFontNormalLarge")
ui.itemName = itemName
local itemHint = U.text(tray, 78, -44, 420, "GameFontHighlightSmall")
U.colour(itemHint, U.GREY)
itemHint:SetText("Drag an item here, or right-click it in your bags or on your character.")
ui.itemHint = itemHint

-- The property list: a gold section label over a black box, then the rows (or the intro when no
-- item is in).
local listTitle = U.text(panel, 4, -84, 520, "GameFontNormal")
ui.listTitle = listTitle
local listFrame = CreateFrame("Frame", nil, panel)
listFrame:SetPoint("TOPLEFT", 0, -102)
listFrame:SetPoint("TOPRIGHT", 0, -102)
listFrame:SetHeight(186)
U.flat(listFrame, U.DETAIL_BG[1], U.DETAIL_BG[2], U.DETAIL_BG[3], U.DETAIL_BORDER[1], U.DETAIL_BORDER[2], U.DETAIL_BORDER[3])
ui.list = listFrame

local ROW_STEP = 26
local scroll = U.scroll(CreateFrame("ScrollFrame", "TormentMysticScroll", listFrame, "UIPanelScrollFrameTemplate"))
scroll:SetPoint("TOPLEFT", 4, -4)
scroll:SetPoint("BOTTOMRIGHT", -4, 4)
if scroll.ScrollBar then scroll.ScrollBar:Hide() end
scroll:EnableMouseWheel(true)
scroll:SetScript("OnMouseWheel", function(self, delta)
    local next = self:GetVerticalScroll() - delta * ROW_STEP
    if next < 0 then next = 0
    elseif next > self:GetVerticalScrollRange() then next = self:GetVerticalScrollRange() end
    self:SetVerticalScroll(next)
end)
local rowsParent = CreateFrame("Frame", nil, scroll)
rowsParent:SetSize(520, 178)
scroll:SetScrollChild(rowsParent)
ui.rowsParent = rowsParent

local intro = U.text(rowsParent, 30, -40, 460, "GameFontHighlight", "CENTER")
intro:SetHeight(90)
intro:SetText("The Mystic can replace an unwanted property on a rare or legendary item with a new random property. You can replace the property as many times as you want, paying the enchant cost each time.")
intro:Hide()
ui.intro = intro

local lockedNote = U.text(rowsParent, 30, -40, 460, "GameFontHighlight", "CENTER")
lockedNote:SetHeight(40)
lockedNote:SetText("This item already has an enchanted property.\nI can replace the same one again for you.")
lockedNote:Hide()
ui.lockedNote = lockedNote

-- A row: the diamond bullet, the line in the affix blue, the help `?` on its right. Picked, it wears
-- the list's gold selection mark (DCUI's row look).
local rows = {}
local function rowAt(index)
    local row = rows[index]
    if row then return row end
    row = U.row(rowsParent)
    row:SetHeight(ROW_STEP - 2)
    row.bullet = row:CreateTexture(nil, "ARTWORK")
    row.bullet:SetTexture(DIAMOND)
    row.bullet:SetSize(9, 9)
    row.bullet:SetPoint("LEFT", 8, 0)
    row.label:ClearAllPoints()
    row.label:SetPoint("LEFT", 24, 0)
    row.label:SetWidth(450)
    -- The `?` is help, drawn as help: a gold question mark on the dark slot ground, not an icon (the
    -- stock question-mark icon reads as a missing texture). It shows what the line can become; that
    -- list is the server's, asked for once per line (contract section 3, the `preview` verb) and kept.
    row.help = CreateFrame("Button", nil, row)
    row.help:SetSize(18, 18)
    row.help:SetPoint("RIGHT", -4, 0)
    U.flat(row.help, U.SLOT_BG[1], U.SLOT_BG[2], U.SLOT_BG[3], U.SLOT_BORDER[1], U.SLOT_BORDER[2], U.SLOT_BORDER[3])
    row.help.mark = row.help:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    row.help.mark:SetPoint("CENTER", 0, 0)
    row.help.mark:SetText("?")
    row.help:SetScript("OnEnter", function(self)
        if row.entry then requestPreview(row, self) end
    end)
    row.help:SetScript("OnLeave", function()
        hovered = nil
        GameTooltip:Hide()
    end)
    rows[index] = row
    return row
end
ui.rows = rows

-- The materials: a gold section label, then the Blacksmith's material lines (slot, name, have / need).
local chestHeading = U.text(panel, 4, -296, 520, "GameFontNormal")
chestHeading:SetText("Required materials")
ui.chestHeading = chestHeading

local function materialAt(index)
    local line = ui.materials and ui.materials[index]
    if line then return line end
    ui.materials = ui.materials or {}
    line = U.material(panel, (index - 1) % 2 * 264, -312 - math.floor((index - 1) / 2) * 44, 196)
    line:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(self.dcName or "", 1, 1, 1)
        GameTooltip:Show()
    end)
    line:SetScript("OnLeave", function() GameTooltip:Hide() end)
    ui.materials[index] = line
    return line
end
ui.materialAt = materialAt

local chooseNote = U.text(panel, 0, -300, 528, "GameFontHighlight", "CENTER")
chooseNote:SetHeight(40)
chooseNote:SetText("Choose from one of the new properties above\nto enchant your item.")
chooseNote:Hide()
ui.chooseNote = chooseNote

-- Why the button is grey, in the server's own words (contract section 4), so a short material or
-- purse is never a silent dead button.
local short = U.text(panel, 0, -358, 528, "GameFontHighlightSmall", "CENTER")
U.colour(short, U.RED)
ui.short = short

local action = U.button(panel, 300, "", nil)
U.anchor(frame, "buttons", {action})
action:SetPoint("TOP", panel, "TOP", 0, -374)
ui.action = action

-- The gold line, where the Blacksmith and Jeweler keep theirs.
local goldValue = U.text(frame, 16, -478, 512, "GameFontNormal")
ui.goldValue = goldValue

-- The two icon tabs on the right edge, Enchant first and Transmogrify second, square
-- and placed exactly as the Blacksmith's.
local TABDEFS = {
    {key = "enchant", label = "Enchant", icon = ENCHANT_ICON},
    {key = "transmogrify", label = "Transmogrify", icon = TRANSMOGRIFY_ICON},
}
local tabs = {}
for index, def in ipairs(TABDEFS) do
    local tab = U.tab(frame, 48)
    tab:SetPoint("TOPLEFT", frame, "TOPRIGHT", -2, -70 - (index - 1) * 56)
    tab.icon:SetTexture(def.icon)
    tab:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(def.label, 1, 1, 1)
        GameTooltip:Show()
    end)
    tab:SetScript("OnLeave", function() GameTooltip:Hide() end)
    if def.key == "transmogrify" then
        -- Transmogrify keeps working as today: it closes this window and asks the bridge verb the
        -- old button asked (docs/contracts/window-bridge.md, fixed).
        tab:SetScript("OnClick", function()
            frame:Hide()
            SendAddonMessage("DCARTISAN", "transmog", "WHISPER", UnitName("player"))
        end)
    end
    U.tabActive(tab, def.key == "enchant")
    tabs[index] = tab
end
ui.tabs = tabs

-- The bind warning, over the window (the item's first enchant only; the server says when). It
-- swallows the clicks under it.
local overlay = CreateFrame("Frame", nil, frame)
overlay:SetAllPoints()
overlay:SetFrameLevel(frame:GetFrameLevel() + 30)
overlay:EnableMouse(true)
local shade = overlay:CreateTexture(nil, "BACKGROUND")
shade:SetAllPoints()
shade:SetTexture(U.EDGE)
shade:SetVertexColor(0, 0, 0, .55)
overlay:Hide()
ui.overlay = overlay
local warn = CreateFrame("Frame", nil, overlay)
warn:SetSize(400, 170)
warn:SetPoint("CENTER")
U.backdrop(warn)
ui.warning = warn
local warnTitle = U.text(warn, 0, -22, 400, "GameFontNormalLarge", "CENTER")
warnTitle:SetText("WARNING!")
local warnBody = U.text(warn, 30, -52, 340, "GameFontHighlight", "CENTER")
warnBody:SetHeight(44)
warnBody:SetText("Enchanting an item will bind it to your account. Continue?")
ui.warnBody = warnBody

-- The window's state: the model the server last sent, and what the player has picked on it.
local currentModel, itemGuid, currentSelection, currentChoice, currentLocked
local currentStep, currentChoices = 1, {}
local rollKey, rollShown, rollElapsed = "", 0, 0
-- The bind warning was accepted before, for this item and this line: display state, not a rule.
local warning, warningAccepted = false, false
local render

local function warnButton(label, x, on)
    local button = U.button(warn, 120, label, on)
    button:SetPoint("BOTTOM", warn, "BOTTOM", x, 24)
    return button
end
ui.warnOK = warnButton("OK", -66, function()
    warningAccepted, warning = true, false
    local entry = currentModel and currentModel.item
    if entry then M.Send("roll", entry.guid, currentSelection or currentLocked) end
    render()
end)
ui.warnCancel = warnButton("Cancel", 66, function() warning = false render() end)

------------------------------------------------------------------------------------------------
-- The model, and the six steps drawn from it
------------------------------------------------------------------------------------------------
local TITLE = {
    [1] = "Place an Item to Replace a Property",
    [2] = "Select a Property to Replace",
    [3] = "Select a Property to Replace",
    [5] = "Select Replacement Property",
    [6] = "Replace a Previously Enchanted Property",
}

-- The button's cost is the server's own gold figure, grouped by the shared formatter (12-ui U4);
-- a jewellery roll sends no gold, so the button carries none. Nothing is added or multiplied here.
local function costLabel(cost)
    if not cost or not cost.gold or cost.gold == "0" or cost.gold == "" then return nil end
    return U.number(cost.gold) .. " gold"
end

-- What keeps the button grey, in the server's own refusal words (contract section 4): the purse the
-- server says cannot pay, else the first material it marks short. nil when nothing is short. The
-- button is live only when this is nil; the server checks both again on `roll`.
local function shortfall(cost, materials)
    if not cost then return "" end
    if cost.enough == false then return "Not enough account gold." end
    for _, material in ipairs(materials or {}) do
        if material.enough == false then
            return "Not enough " .. (material.name or "materials") .. ": you have " .. U.number(material.have)
                .. " of " .. U.number(material.need) .. "."
        end
    end
    return nil
end

-- The 3.3.5a client has no widget:SetShown (Inventory.lua:923); Show and Hide are the whole API.
local function setShown(widget, shown)
    if shown then widget:Show() else widget:Hide() end
end

local function drawRow(index, entry, wanted, picked, step)
    local row = rowAt(index)
    setShown(row, index <= wanted)
    if index > wanted then return end
    row:ClearAllPoints()
    row:SetPoint("TOPLEFT", 0, -(index - 1) * ROW_STEP)
    row:SetPoint("TOPRIGHT", 0, -(index - 1) * ROW_STEP)
    -- A line the server marks 2 or 3 cannot be replaced (its text carries the server's reason,
    -- contract section 3): greyed, no `?`, and a click selects nothing.
    local dead = entry.state ~= nil and entry.state >= 2
    U.colour(row.label, picked and U.WHITE or dead and U.GREY or AFFIX_BLUE)
    setShown(row.mark, picked)
    row.label:SetText(entry.text or "")
    setShown(row.help, step ~= 5 and not dead)
    row.entry = entry
    row:SetScript("OnClick", function()
        if dead then return end
        if step == 5 then currentChoice = entry.seq else currentSelection = entry.seq end
        render()
    end)
end

render = function()
    local model = currentModel
    local item = model and model.item
    local choices = (model and model.choices) or {}
    local step
    if not item then step = 1
    elseif #choices > 0 then step = 5
    elseif model.locked then step = 6
    elseif currentSelection then step = 3
    else step = 2 end
    if step ~= 5 then
        rollKey, rollShown, rollElapsed = "", 0, 0
    else
        local key = tostring(#choices) .. "|" .. tostring(choices[1] and choices[1].text)
        if key ~= rollKey then rollKey, rollShown, rollElapsed = key, 1, 0 end
    end
    currentStep, currentChoices = step, choices

    ui.listTitle:SetText(TITLE[step])
    setShown(ui.intro, step == 1)
    setShown(ui.lockedNote, step == 6)
    setShown(ui.chooseNote, step == 5)
    -- The rows: every enchantable property, or the three choices of a paid roll.
    local entries = step == 5 and choices or ((model and model.properties) or {})
    local wanted = step == 5 and rollShown or #entries
    -- The scroll child grows with the rows, so an item with more lines than the box holds scrolls.
    ui.rowsParent:SetHeight(math.max(178, wanted * ROW_STEP))
    for index = 1, math.max(#rows, wanted) do
        local entry = entries[index]
        if entry then
            local picked = step == 6 or (step == 5 and entry.seq == currentChoice)
                or (step ~= 5 and entry.seq == currentSelection)
            drawRow(index, entry, wanted, picked, step)
        elseif rows[index] then
            rows[index]:Hide()
        end
    end

    -- The slot: the item's own icon, square, and its name in its rarity colour; empty, the hint.
    local icon = item and GetItemIcon(item.entry)
    setShown(ui.slot.icon, icon ~= nil)
    if icon then ui.slot.icon:SetTexture(icon) end
    ui.itemName:SetText(item and (item.name or GetItemInfo(item.entry)) or "")
    U.colour(ui.itemName, (item and DCRARITY and DCRARITY[item.rarity]) or U.GOLD)
    setShown(ui.itemHint, not item)

    -- The materials: when an item is in and the roll is not open. A material with no icon the client
    -- knows (the jewellery gem is "any colour", entry 0) is left out until a property is picked, and
    -- then drawn as its name and count over an empty slot, never a missing-texture box (round 3).
    local showMaterials = item ~= nil and step ~= 5
    local picking = step == 3 or step == 6
    setShown(ui.chestHeading, showMaterials)
    local materials = (model and model.materials) or {}
    for index = 1, math.max(#materials, ui.materials and #ui.materials or 0) do
        local material = materials[index]
        local line = (ui.materials and ui.materials[index]) or (material and materialAt(index))
        local known = material and material.entry ~= 0 and GetItemIcon(material.entry)
        local drawn = showMaterials and material ~= nil and (known or picking)
        setShown(line, drawn)
        setShown(line.label, drawn)
        if drawn then
            setShown(line.icon, known)
            if known then line.icon:SetTexture(known) end
            line.dcName = material.name or (GetItemInfo(material.entry) or "")
            line.label:SetText(line.dcName)
            U.count(line, material.have, material.need, material.enough)
        end
    end

    -- The button: the label and the grey. The price and the choice are the server's.
    local cost = model and model.cost
    local price = costLabel(cost)
    local label, enabled, why
    if step == 1 then label, enabled = "Place an Item to Replace a Property", false
    elseif step == 2 then label, enabled = "Select a Property to Replace", false
    elseif step == 5 then label, enabled = "Select Property", currentChoice ~= nil
    else
        label = price and ("Replace Property: " .. price) or "Replace Property"
        why = shortfall(cost, model and model.materials)
        enabled = why == nil
    end
    ui.action:SetText(label)
    if enabled then ui.action:Enable() else ui.action:Disable() end
    ui.short:SetText(why or "")
    ui.goldValue:SetText("Your gold: " .. U.number((model and model.gold) or goldBalance))
    setShown(ui.overlay, warning)
end

action:SetScript("OnClick", function()
    local entry = currentModel and currentModel.item
    if not entry then return end
    if currentStep == 3 then
        if currentModel.bindWarning and not warningAccepted then
            warning = true
            render()
        else
            M.Send("roll", entry.guid, currentSelection)
        end
    elseif currentStep == 6 then
        if currentModel.bindWarning and not warningAccepted then
            warning = true
            render()
        else
            M.Send("roll", entry.guid, currentLocked)
        end
    elseif currentStep == 5 then
        M.Send("pick", entry.guid, currentChoice)
    end
end)
frame:SetScript("OnUpdate", function(_, delta)
    -- The first choice (the current value) shows at once; the second and third one second apart.
    if currentStep == 5 and #currentChoices > 0 then
        rollElapsed = rollElapsed + delta
        local want = math.min(#currentChoices, 1 + math.floor(rollElapsed))
        if want ~= rollShown then
            rollShown = want
            render()
        end
    end
    -- Budget: an over-budget request is dropped with no reply (contract section 1b), so a request
    -- that has waited too long stops blocking the next one.
    if pending and GetTime() - pending.at > REQUEST_TIMEOUT then finishRequest() end
    -- The right-click claim hooks the bag buttons as they exist: ElvUI builds its slots when the
    -- bags are first opened, so the scan runs again about once a second while the window is up.
    if frame:IsShown() then
        scanElapsed = scanElapsed + delta
        if scanElapsed >= 1 then
            scanElapsed = 0
            M.ScanBagButtons()
        end
        if indexDirty and not pending then
            indexDirty = false
            AIO.Handle(CHANNEL, "Refresh")
        end
    end
end)
frame:SetScript("OnHide", function() warning = false restoreIds() render() end)

------------------------------------------------------------------------------------------------
-- The bridge: one request in flight, drawn from the records that answer it
------------------------------------------------------------------------------------------------
-- docs/contracts/mystic-enchant-messages.md section 2: the four verbs and their fields. A field is
-- decimal digits inside its bounds or the window does not send at all, the same strictness the
-- bridge parses with.
local VERBS = {
    place = {{1, 4294967295}},
    preview = {{1, 4294967295}, {0, 4294967295}},
    roll = {{1, 4294967295}, {0, 4294967295}},
    pick = {{1, 4294967295}, {1, 3}},
}
local function whole(value, low, high)
    return type(value) == "number" and value == math.floor(value) and value >= low and value <= high
end
local function sendRequest(fields)
    SendAddonMessage("DCARTISAN", table.concat(fields, "\t"), "WHISPER", UnitName("player"))
end
-- The window's one send point: every click, drag and hover comes through here. One request at a
-- time (section 1b), the rest wait in `queued` for its E or X.
function M.Send(verb, first, second)
    local bounds = VERBS[verb]
    if not bounds then return false end
    local fields = {verb}
    for position, bound in ipairs(bounds) do
        local value = position == 1 and first or second
        if not whole(value, bound[1], bound[2]) then return false end
        fields[#fields + 1] = tostring(value)
    end
    -- The `?` answer replaces what was cached for that line, and the V records of the reply may
    -- arrive as several records of the same letter (section 3): start it empty.
    if verb == "preview" then previews[first .. ":" .. second] = {} end
    if pending then
        queued = fields
        return false
    end
    pending = {verb = verb, at = GetTime(), state = {lines = {}, choices = {}, materials = {}}}
    sendRequest(fields)
    return true
end

-- The `?` popover: the line's own text, then everything the server says it can become with the
-- range each would roll in (the V records). Asked once per line (the bucket drops a flood with no
-- reply, section 1b) and drawn again the moment the answer lands under the same cursor.
local function drawPreview()
    local at = hovered
    if not at then return end
    GameTooltip:SetOwner(at.owner, "ANCHOR_RIGHT")
    GameTooltip:SetText(at.text or "", 1, 1, 1)
    for _, line in ipairs(previews[at.guid .. ":" .. at.seq] or {}) do
        GameTooltip:AddLine(line, 1, .82, 0)
    end
    GameTooltip:Show()
end
requestPreview = function(row, owner)
    local item = currentModel and currentModel.item
    if not item or not row.entry then return end
    hovered = {guid = item.guid, seq = row.entry.seq, owner = owner, text = row.entry.text}
    drawPreview()
    if not previews[item.guid .. ":" .. row.entry.seq] then M.Send("preview", item.guid, row.entry.seq) end
end

-- One record of a reply, read into the request it belongs to (contract section 3). R names the
-- verb; the transmog tab's reply can arrive in the middle of a window request, and a record that
-- is not ours is dropped whole. M, I and D are the other artisan verbs' money and bag records and
-- are ignored: the bag index comes back with the next Show.
local function readRecord(f)
    if f[1] == "R" then
        if f[2] == pending.verb then pending.accepted = true else pending.foreign = true end
        return
    end
    if pending.foreign then return end
    local state = pending.state
    if f[1] == "B" then goldBalance = f[2] or goldBalance
    elseif f[1] == "N" then
        state.item = {guid = tonumber(f[2]) or 0, entry = tonumber(f[3]) or 0, rarity = f[4],
            enchanted = f[5] == "1", attempts = tonumber(f[6]) or 0, bind = f[7] == "1", pending = f[8] == "1"}
    elseif f[1] == "L" then
        for index = 3, #f do if f[index] ~= "" then state.lines[#state.lines + 1] = readAffix(f[index], true) end end
    elseif f[1] == "C" then
        for index = 3, #f do if f[index] ~= "" then state.choices[#state.choices + 1] = readAffix(f[index], false) end end
    elseif f[1] == "P" then
        state.price = {gold = f[3], enough = f[4] == "1"}
    elseif f[1] == "T" then
        state.materials[#state.materials + 1] = {entry = tonumber(f[3]) or 0, need = f[4], have = f[5],
            enough = f[6] == "1", name = f[7]}
    elseif f[1] == "V" then
        local key = f[2] .. ":" .. f[3]
        previews[key] = previews[key] or {}
        for index = 4, #f do
            if f[index] ~= "" then previews[key][#previews[key] + 1] = readPreview(f[index]) end
        end
        drawPreview()
    end
end
-- The item's state as the server described it, in the shape the six steps are drawn from. Nothing
-- is worked out here: the lines, the price, the material counts and the three choices are its own.
local function toModel(state)
    local item = itemIndex[state.item.guid]
    local model = {gold = goldBalance, item = {guid = state.item.guid, entry = state.item.entry,
        name = item and item.name, rarity = state.item.rarity}, locked = state.item.enchanted, bindWarning = state.item.bind}
    if state.item.pending then
        model.choices = state.choices
        return model
    end
    model.properties = state.lines
    model.cost = state.price
    model.materials = state.materials
    return model
end
-- The request is done (E, or its reply never came): draw what it brought, then send the next one.
finishRequest = function()
    local done = pending
    pending = nil
    if done and done.state.item and not done.foreign then
        -- The item's state moved, so what a line could become has moved with it: a `?` asked
        -- before this reply is stale (a reroll changes what the pool may offer).
        previews = {}
        M.Render(toModel(done.state))
    end
    if queued then
        local fields = queued
        queued = nil
        pending = {verb = fields[1], at = GetTime(), state = {lines = {}, choices = {}, materials = {}}}
        sendRequest(fields)
    end
end

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("CHAT_MSG_ADDON")
watcher:SetScript("OnEvent", function(_, _, prefix, body, distribution, sender)
    if prefix ~= "DCARTISAN" or distribution ~= "WHISPER" then return end
    local own = UnitName("player")
    if sender ~= own and sender ~= own .. "-" .. GetRealmName() then return end
    local f = splitFields(body, "|")
    if f[1] == "X" then
        -- A refusal: only X arrives, with the server's own text, shown as is (section 3).
        U.say(f[2] or "The Mystic refused that.", true)
        if pending and not pending.foreign then finishRequest() end
        return
    end
    if not pending then return end
    if f[1] == "E" then
        if f[2] == pending.verb then finishRequest() end
    else
        readRecord(f)
    end
end)

------------------------------------------------------------------------------------------------
-- The bags and the character sheet: a plain right-click loads an item instead of using it
------------------------------------------------------------------------------------------------
-- The claim dc_jeweler.lua's socket tab makes, on the bag buttons and the character sheet's (every
-- way in puts the item in): the buttons' own PreClick
-- and PostClick hooks, never a replacement of a stock global. PreClick runs before the button's
-- OnClick and cannot cancel it, so the button's id is pointed at a slot that holds nothing for the
-- length of that one click - the stock OnClick then acts on nothing - and PostClick puts it back.
-- The Torment sheet's OnClick reads its own equipSlot, not the id: it yields to the claim registered
-- below instead (Inventory.lua's ClaimRightClick), and so do its stash and potion rules on the bags.
local SHEET_SLOTS = {"Head", "Neck", "Shoulder", "Back", "Chest", "Shirt", "Tabard", "Wrist", "Hands", "Waist",
    "Legs", "Feet", "Finger0", "Finger1", "Trinket0", "Trinket1", "MainHand", "SecondaryHand", "Ranged"}
local hooked, blanked, sheet = {}, {}, {}
local function clickButtons()
    local found = {}
    for frameNo = 1, (_G.NUM_CONTAINER_FRAMES or 13) do
        for itemNo = 1, (MAX_CONTAINER_ITEMS or 36) do
            local button = _G["ContainerFrame" .. frameNo .. "Item" .. itemNo]
            if button then found[#found + 1] = button end
        end
    end
    local client = _G.ElvUI and _G.ElvUI[1]
    local bags = client and client.GetModule and client:GetModule("Bags", true)
    local holder = bags and bags.BagFrame and bags.BagFrame.Bags
    if holder then
        for bagId = 0, 4 do
            for _, button in pairs(holder[bagId] or {}) do
                if type(button) == "table" and button.HookScript then found[#found + 1] = button end
            end
        end
    end
    for _, name in ipairs(SHEET_SLOTS) do
        local button = _G["Character" .. name .. "Slot"]
        if button then sheet[button] = "stock"; found[#found + 1] = button end
    end
    for worn = 0, 18 do
        for _, name in ipairs({"DiablocraftGearSlot", "DiablocraftCosmeticSlot"}) do
            local button = _G[name .. worn]
            if button then sheet[button] = "torment"; found[#found + 1] = button end
        end
    end
    return found
end
-- True only while a plain right-click would load an item: the window up, out of combat, nothing on
-- the cursor (the stock click drops a held item), no modifier (the stock modified click).
local function takesRightClick()
    if not frame:IsShown() or (InCombatLockdown and InCombatLockdown()) then return false end
    if GetCursorInfo and GetCursorInfo() then return false end
    return not ((IsShiftKeyDown and IsShiftKeyDown()) or (IsControlKeyDown and IsControlKeyDown())
        or (IsAltKeyDown and IsAltKeyDown()))
end
if Diablocraft and type(Diablocraft.ClaimRightClick) == "function" then Diablocraft.ClaimRightClick(takesRightClick) end
-- What a right-clicked button holds, in the index's numbering, and the id its stock click is pointed
-- at for that one click (nil: the click is left alone). A full bag has no empty cell, and the cell
-- past its last slot holds nothing either (Inventory.lua's potion hook does the same); the stock
-- sheet's click is UseInventoryItem, pointed at an empty worn slot when there is one.
local function clicked(button)
    local kind = sheet[button]
    if kind == "torment" then
        local worn = button.equipSlot
        if not worn or worn < 0 or worn > 18 or not GetInventoryItemLink("player", worn + 1) then return end
        return 255, worn, nil
    end
    local id = button:GetID()
    if not id or id < 1 then return end
    if kind == "stock" then
        if not GetInventoryItemLink("player", id) then return end
        for spare = 1, 19 do
            if spare ~= id and not GetInventoryItemLink("player", spare) then return 255, id - 1, spare end
        end
        return 255, id - 1, nil
    end
    local parent = button:GetParent()
    local bagId = parent and parent:GetID()
    if not bagId or not GetContainerItemLink(bagId, id) then return end
    local slots = GetContainerNumSlots and GetContainerNumSlots(bagId) or 0
    for spare = 1, slots do
        if not GetContainerItemLink(bagId, spare) then return bagId, id, spare end
    end
    return bagId, id, slots + 1
end
restoreIds = function()
    for button, id in pairs(blanked) do button:SetID(id) end
    blanked = {}
end
scanBagButtons = function()
    for _, button in ipairs(clickButtons()) do
        if not hooked[button] then
            hooked[button] = true
            button:HookScript("PreClick", function(self, mouseButton)
                if mouseButton ~= "RightButton" or not takesRightClick() then return end
                restoreIds()
                local bag, slotNumber, spare = clicked(self)
                if not bag then return end
                -- Taken or refused, the click is the window's: a stock click on an item it cannot
                -- take would equip or unequip it and move it out from under the index.
                if not placeAt(bag, slotNumber) then U.say(NOT_TAKEN, true) end
                if spare then
                    blanked[self] = self:GetID()
                    self:SetID(spare)
                end
            end)
            button:HookScript("PostClick", function(self)
                local id = blanked[self]
                if id then self:SetID(id); blanked[self] = nil end
            end)
        end
    end
end
M.ScanBagButtons = scanBagButtons
-- The Show index turns an item into its guid: the client has no API that says which container a
-- drag started in, so the pickup calls are hooked to remember it (the pattern every window keeps).
-- A worn item is bag 255 and its slot 0..18, as the index lists it.
hooksecurefunc("PickupContainerItem", function(bag, slotNumber) cursorBag, cursorSlot = bag, slotNumber end)
hooksecurefunc("PickupInventoryItem", function(slotNumber) cursorBag, cursorSlot = 255, slotNumber - 1 end)
placeAt = function(bag, slotNumber)
    local entry = bag and slotNumber and slotted[bag] and slotted[bag][slotNumber]
    if not entry then return false end
    -- True whether the request goes now or waits its turn: the item is consumed either way, and the
    -- stock click of a right-click claim is blanked for it (contract section 1b).
    M.Send("place", entry.guid)
    return true
end
-- An equip, an unequip or a bag move while the window is up moves items out from under the index, so
-- it is asked for again (the Blacksmith's dirty flag): the answer is a Show marked refresh.
local indexWatch = CreateFrame("Frame")
indexWatch:RegisterEvent("BAG_UPDATE")
indexWatch:RegisterEvent("PLAYER_EQUIPMENT_CHANGED")
indexWatch:SetScript("OnEvent", function() if frame:IsShown() then indexDirty = true end end)

-- The window opened (contract section 1a, the Show payload): the item index, the balance and the
-- pushed tables. Nothing is placed, so the window is at step 1.
function M.Show(payload)
    itemIndex, slotted, goldBalance = {}, {}, payload.gold or "0"
    for _, item in ipairs(payload.items or {}) do
        itemIndex[item.guid] = item
        slotted[item.bag] = slotted[item.bag] or {}
        slotted[item.bag][item.slot] = item
    end
    -- The answer to the window's own Refresh renews the index and nothing else: the placed item and a
    -- request in flight stay, and a window closed meanwhile stays closed.
    if payload.refresh then return end
    currentModel, itemGuid = nil, nil
    currentSelection, currentChoice, currentLocked = nil, nil, nil
    warning, warningAccepted, pending, queued = false, false, nil, nil
    if not tables then AIO.Handle(CHANNEL, "Tables") end
    render()
    frame:Show()
end
handlers.Show = function(_, payload) M.Show(payload) end
-- The server's range watcher: the player walked away from the Mystic.
handlers.Close = function() frame:Hide() end
-- The pushed tables name a property (contract section 1a); the line's wording is dc_tooltip.lua's.
handlers.Tables = function(_, payload)
    names, percent, tables = payload.names or {}, payload.percent or {}, true
    render()
end

function M.Render(model)
    local guid = model and model.item and model.item.guid
    if guid ~= itemGuid then
        currentSelection, currentChoice, currentLocked = nil, nil, nil
        warning, warningAccepted = false, false
    end
    -- A fresh set of choices (a new paid roll) starts unpicked, and its one-second stagger starts
    -- over: nothing carries over from the roll before it.
    if currentStep ~= 5 then currentChoice, rollKey = nil, "" end
    itemGuid = guid
    currentModel = model
    if model and model.locked and model.properties then currentLocked = model.properties[1] and model.properties[1].seq end
    render()
    frame:Show()
end

