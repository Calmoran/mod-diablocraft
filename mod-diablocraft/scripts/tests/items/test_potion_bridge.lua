-- Server inventory bridge with an in-memory potion row; no database writes.
local handlers, sent, commands = {}, {}, {}
local potionEntry
local player = {}
function player:GetGUIDLow() return 7 end
function player:GetLevel() return 70 end
function player:GetClass() return 8 end
function player:RunCommand(command) commands[#commands + 1] = command end
AIO = {
    AddHandlers = function() return handlers end,
    Handle = function(_, _, name, data) sent[#sent + 1] = {name, data} end,
}
DCAccount = {
    Principal = function() return nil end,
    Snapshot = function() return {gold = "0", materials = {}} end,
}
function CharDBQuery(sql)
    assert(sql:find("COALESCE(item_entry,0)", 1, true), "NULL is represented as zero")
    assert(sql:find("guid=7", 1, true), "only the acting character's potion")
    if potionEntry == nil then return nil end
    return {GetUInt32 = function() return potionEntry end}
end
local loginHandler
function RegisterPlayerEvent(event, handler) if event == 3 then loginHandler = handler end end
local classQueries = {}
local potionRows, potionQueries = {900001}, 0
function WorldDBQuery(sql)
    classQueries[#classQueries + 1] = sql
    if sql:find("dc_class_map", 1, true) then
        assert(sql:find("FROM dc_class_map WHERE wow_class_id = 8", 1, true), "only the class's own row: " .. sql)
        return {GetString = function() return "Intelligence" end}
    end
    if sql:find("slot = 'potion'", 1, true) then
        potionQueries = potionQueries + 1
        if not potionRows then return nil end
        local at = 1
        return {GetUInt32 = function() return potionRows[at] end,
                NextRow = function() at = at + 1; return potionRows[at] ~= nil end}
    end
    error("the sheet reads no other world table: " .. sql)
end
-- The G1 security bucket (683aa722) guards Refresh; load the real one. A clock
-- that only moves forward lets three refreshes pass while the burst stays unspent.
local now = 0
function GetCurrTime() now = now + 5000; return now end
dofile("mod-diablocraft/lua/aio/dc_throttle.lua")
dofile("mod-diablocraft/lua/aio/dc_inventory.lua")
handlers.Refresh(player)
assert(sent[#sent][2].potion.index == 100 and not sent[#sent][2].potion.entry, "missing row empty")
-- --------------------------------------------------------- no grid fields
-- The one-update shim is gone (diablocraft-pgfk): no push carries the old grid's
-- fields, with the sheet marker or without, on login or after an intent.
local function noGrid(data, what)
    assert(data.bags == nil and data.equipped == nil and data.layout == nil,
        what .. ": no bag cells, no worn cells, no grid layout")
end
local data = sent[#sent][2]
noGrid(data, "a Refresh with no marker")
handlers.Refresh(player, 2)
data = sent[#sent][2]
noGrid(data, "a Refresh with the sheet marker")
assert(data.mainStat == "Intelligence", "the class's main stat comes from dc_class_map")
assert(data.level == 70 and data.gold == "0" and data.materials, "level and funds are still sent")
assert(data.potionEntries and data.potionEntries[1] == 900001, "the potion entries are named for the right-click")
assert(sent[#sent][2].potion.index == 100 and not sent[#sent][2].potion.entry, "missing row empty")

-- The potion list is read on every push, so a potion row added while the server runs
-- (the acceptance fixture, a real potion) is named at the next refresh, no restart.
potionRows = nil
handlers.Refresh(player, 2)
assert(#sent[#sent][2].potionEntries == 0, "no potion rows: none named")
potionRows = {900001, 118}
handlers.Refresh(player, 2)
assert(#sent[#sent][2].potionEntries == 2 and sent[#sent][2].potionEntries[2] == 118,
    "a row added later is named without a restart")
potionRows = {900001}
loginHandler(nil, player)
noGrid(sent[#sent][2], "a login push")
handlers.Unequip(player, 100)
noGrid(sent[#sent][2], "an intent's push")
assert(handlers.Identify == nil and handlers.Socket == nil, "the old sheet's Identify and Socket intents are gone")
potionEntry = 0
handlers.Refresh(player)
assert(not sent[#sent][2].potion.entry, "NULL row empty")
potionEntry = 900001 -- test-only entry, never shipped
handlers.Refresh(player)
assert(sent[#sent][2].potion.entry == 900001 and sent[#sent][2].potion.index == 100, "equipped potion snapshot")
local before = #commands
handlers.Unequip(player, 100)
assert(commands[before + 1] == "dc inventory unequip 100", "virtual slot forwarded to C++")
before = #commands
handlers.Unequip(player, 99)
handlers.Unequip(player, "100")
handlers.Unequip(player, 100.5)
assert(#commands == before, "invalid slots rejected")
handlers.Equip(player, 25523)
assert(commands[before + 1] == "dc inventory equip 25523", "the Equip intent (the potion drop) is unchanged")
-- Security G1: a flood of Refresh on a frozen clock is dropped after the burst.
function GetCurrTime() return now end
local floodStart = #sent
for _ = 1, 30 do handlers.Refresh(player) end
assert(#sent - floodStart <= 10, "Refresh flood is throttled")
print("PASS potion inventory bridge checks")
