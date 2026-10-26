-- luacheck: globals DCThrottle
-- The D3 inventory screen - server half only (12-ui §2).
--
-- The client half is the real addon, client-patch/addons/Torment
-- (Inventory.lua / Inventory.xml). AIO is only the bridge between the two, so
-- this file deliberately never calls AIO.AddAddon(): nothing here is sent to a
-- client.
--
-- Nothing in this file decides anything. It reads rows for one Snapshot and it
-- forwards two intents, Equip and Unequip, to C++ (.dc inventory equip /
-- unequip), which owns eligibility, slot legality and the move. Lua asks and
-- draws.
--
-- The 22 stats and the three D3 summary values are NOT in the snapshot: they
-- are stat maths and live in C++ (00 §5, 12-ui §2), and Eluna cannot call into
-- the module. `.dc inventory sheet` pushes them straight to the addon as a
-- DCSHEET addon whisper, the channel DCPARAGON and DCECON already use. It is
-- run immediately before every AIO.Handle below, on the same session, so the
-- stat block is always on the wire ahead of the snapshot that redraws with it.
local AIO = AIO or require("AIO")
local CHANNEL = "DiablocraftInventory"
local handlers = AIO.AddHandlers(CHANNEL, {})

-- The thirteen gear slots of the approved slot map plus the five cosmetic slots
-- of 05 §7, as the Unequip handler bounds them.
local EQUIP_FIRST, EQUIP_LAST = 0, 18
-- constant: virtual potion slot, shared with DC::Potion::InventorySlot.
local POTION_SLOT = 100

local function quote(text)
    return tostring(text or ""):gsub("['\\]", "")
end

-- The Paragon level shown beside the character level, D3's "Level: 70 (186)".
-- A read, never a calculation: DC::Paragon owns the pool.
local function paragonLevel(player)
    local account, mode = DCAccount.Principal(player)
    if not account then return 0 end
    local row = CharDBQuery(("SELECT level FROM dc_account_paragon WHERE account_id=%d AND pool='%s'")
        :format(account, quote(mode)))
    return row and row:GetUInt32(0) or 0
end

-- The class's main stat, "Strength" / "Dexterity" / "Intelligence", from
-- dc_class_map (class_primary_stats.csv through generate_sql.py). A read: no
-- class is named in code, and a WoW class with no row sends none, so the sheet
-- highlights nothing rather than guessing.
local function mainStat(player)
    local row = WorldDBQuery("SELECT primary_stat FROM dc_class_map WHERE wow_class_id = " .. player:GetClass())
    return row and row:GetString(0) or nil
end

-- Item entries that belong in the potion slot (dc_base_item.slot = 'potion', the
-- same test C++ IsPotionItem makes). Generated data, read once. The sheet uses it
-- to equip a potion on right-click in the bags instead of letting the stock Use
-- drink it; the server re-checks on every Equip.
-- Read on every push, not cached: the table is tiny and the fixture or a real potion
-- can be added while the server runs (C++ IsPotionItem reads it live too).
local function potionList()
    local list = {}
    local rows = WorldDBQuery("SELECT entry FROM dc_base_item WHERE slot = 'potion'")
    if rows then repeat list[#list + 1] = rows:GetUInt32(0) until not rows:NextRow() end
    return list
end

-- The new sheet draws no bag cells: the worn items come from the stock client, the
-- bags are ElvUI's. So the snapshot carries only what the client cannot know: the
-- potion slot (a virtual slot, dc_character_potion), the Paragon level, the main
-- stat, the potion entries and the funds fallback.
local function snapshot(player)
    local potionRow = CharDBQuery(("SELECT COALESCE(item_entry,0) FROM dc_character_potion WHERE guid=%d")
        :format(player:GetGUIDLow()))
    local potionEntry = potionRow and potionRow:GetUInt32(0) or 0
    -- Exact decimal strings, never Lua numbers (0007). The addon's own DCECON
    -- snapshot wins when it has one; these are its fallback, exactly as the
    -- stash does it.
    local pools = DCAccount.Snapshot(player)
    return {
        level = player:GetLevel(),
        paragon = paragonLevel(player),
        mainStat = mainStat(player),
        potion = potionEntry ~= 0 and {index = POTION_SLOT, entry = potionEntry} or {index = POTION_SLOT},
        potionEntries = potionList(),
        gold = pools.gold,
        materials = pools.materials,
    }
end

local function push(player, note)
    -- The stat block first, on the same session, so it can never arrive after
    -- the snapshot that is meant to draw it.
    player:RunCommand("dc inventory sheet")
    local data = snapshot(player)
    data.note = note
    AIO.Handle(player, CHANNEL, "Snapshot", data)
end

-- The sheet's stat block and potion slot come from THIS channel and no other, so
-- a screen that changes what the sheet shows (dc_stash.lua's Move changes gold
-- and the bags the stats read) pushes one here. Resolved by name per call, like
-- DCGrid and DCAccount, never at load.
DCInventory = DCInventory or {}
function DCInventory.Refresh(player, note)
    push(player, note)
end

function handlers.Refresh(player)
    -- Security G1: push() reads the sheet; drop a flood.
    if not DCThrottle.Allow(player, "inventory:refresh", 5, 10) then return end
    push(player, "refresh")
end

-- The screen is read-only in combat (12-ui §3); C++ refuses both intents there
-- and again when the player is dead, and answers with its own error line.
function handlers.Equip(player, index)
    -- constant: 25600 = 256 bags x 100 slots, the packed index bound.
    if type(index) ~= "number" or index ~= math.floor(index) or index < 0 or index > 25600 then return end
    -- Security G1: the command and push() read the sheet; drop a flood.
    if not DCThrottle.Allow(player, "inventory:equip", 5, 10) then return end
    player:RunCommand("dc inventory equip " .. index)
    push(player, "equip")
end

function handlers.Unequip(player, slot)
    if type(slot) ~= "number" or slot ~= math.floor(slot) then return end
    if slot ~= POTION_SLOT and (slot < EQUIP_FIRST or slot > EQUIP_LAST) then return end
    if not DCThrottle.Allow(player, "inventory:unequip", 5, 10) then return end
    player:RunCommand("dc inventory unequip " .. slot)
    push(player, "unequip")
end

-- Login push, so the first press of C draws a filled screen instead of an empty
-- one waiting on a round trip. The addon holds it and shows nothing until asked.
RegisterPlayerEvent(3, function(_, player)
    if player then push(player, "login") end
end)
