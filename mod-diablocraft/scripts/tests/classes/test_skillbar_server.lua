-- Run from repo root with `lua mod-diablocraft/scripts/tests/classes/test_skillbar_server.lua`.
--
-- The server half of dc_skillbar.lua against stubbed DB access. The catalogue's
-- slot-rule shape is pinned here (PM review 2026-09-19): it reads only the gates
-- the configured passive_skill_slots asks for, the open count can never exceed
-- that count, and a gate row that is absent is not invented.

local VALUES = {
    ["combat.active_skill_slots"] = 6,
    ["combat.passive_skill_slots"] = 4,
    ["combat.skill_slot_gap_ms"] = 150,
    ["combat.passive_slot_1_unlock_level"] = 10,
    ["combat.passive_slot_2_unlock_level"] = 20,
    ["combat.passive_slot_3_unlock_level"] = 30,
    ["combat.passive_slot_4_unlock_level"] = 70,
}

local requested = {}
_G.DCTunables = {
    Get = function(category, name)
        requested[#requested + 1] = category .. "." .. name
        return VALUES[category .. "." .. name]
    end,
    Has = function(category, name)
        requested[#requested + 1] = category .. "." .. name
        return VALUES[category .. "." .. name] ~= nil
    end,
    Or = function(category, name, fallback)
        requested[#requested + 1] = category .. "." .. name
        local value = VALUES[category .. "." .. name]
        if value == nil then value = fallback end
        return value
    end,
}

-- dc_rift_floor rows by instance id, the newest live floor's run as the query orders them
-- (rift floors Part F6: the run is read through the floor the player stands on); every other
-- characters query answers nothing. riftQueries counts the floor reads, lastSql the last one.
local riftRows, riftQueries, lastSql = {}, 0, nil
local function rowOf(values)
    return {GetUInt32 = function(_, i) return values[i + 1] end,
            GetString = function(_, i) return values[i + 1] end}
end
_G.WorldDBQuery = function() return nil end
_G.CharDBQuery = function(sql)
    local instance = sql:match("FROM dc_rift_floor f JOIN dc_rift r ON r.id=f.run_id WHERE f.instance_id=(%d+) AND f.closed_at IS NULL")
    if not instance then return nil end
    riftQueries = riftQueries + 1
    lastSql = sql
    local values = riftRows[tonumber(instance)]
    return values and rowOf(values) or nil
end

local serverHandlers, pushed
_G.AIO = {
    AddAddon = function() return true end,
    AddHandlers = function(channel, handlers) serverHandlers = handlers return handlers end,
    AddOnInit = function() end,
    Handle = function(_, channel, action, payload)
        pushed = {channel = channel, action = action, payload = payload}
    end,
}

local player = {level = 70, guid = 1, wowClass = 1, instance = 0, map = 0}
function player:GetLevel() return self.level end
function player:GetInstanceId() return self.instance end
function player:GetMapId() return self.map end
function player:GetGUIDLow() return self.guid end
function player:GetClass() return self.wowClass end

-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
-- The file under test, overridable so a mutant copy can be run (the client test's own variable).
dofile(os.getenv("DC_SKILLBAR_LUA") or 'mod-diablocraft/lua/aio/dc_skillbar.lua')

local function catalogue()
    pushed = nil
    requested = {}
    serverHandlers.Request(player)
    assert(pushed and pushed.action == "Show", "Request answers with Show")
    return pushed.payload
end

assert(type(catalogue().categories) == "table",
       "the catalogue carries a categories list (empty here, DB stubbed to nil)")

local function asked(name)
    for _, key in ipairs(requested) do
        if key == name then return true end
    end
    return false
end

-- The four gate rows exist by default, and all four are open at 70.
local data = catalogue()
assert(data.activeSlots == 6, "active slots, got " .. tostring(data.activeSlots))
assert(data.passiveSlotCount == 4, "passive count, got " .. tostring(data.passiveSlotCount))
assert(#data.passiveSlotLevels == 4, "four gates, got " .. #data.passiveSlotLevels)
assert(data.passiveSlots == 4, "four open at 70, got " .. tostring(data.passiveSlots))

-- The gap between two DCSLOTs (or DCSWAPs) is the C++ gate's alone: a swap is one
-- message, so the catalogue carries no gap for the window to pace by.
assert(data.slotGapMs == nil, "the catalogue carries no slot gap, got " .. tostring(data.slotGapMs))

-- Two configured passive slots: only gates 1 and 2 are read, and at most two
-- open even at level 70. This was the PM's bug (counted gates 1-4 -> open 4).
VALUES["combat.passive_skill_slots"] = 2
data = catalogue()
assert(data.passiveSlotCount == 2, "two configured, got " .. tostring(data.passiveSlotCount))
assert(#data.passiveSlotLevels == 2, "two gates, got " .. #data.passiveSlotLevels)
assert(data.passiveSlots == 2, "two open at 70, got " .. tostring(data.passiveSlots))
assert(not asked("combat.passive_slot_3_unlock_level"), "gate 3 must not be read")
assert(not asked("combat.passive_slot_4_unlock_level"), "gate 4 must not be read")

-- A gate above the character's level does not open its slot.
VALUES["combat.passive_slot_2_unlock_level"] = 90
data = catalogue()
assert(data.passiveSlots == 1, "gate 2 at 90 leaves one open, got " .. tostring(data.passiveSlots))

-- An absent row means LOCKED, not a fallback value (Architect 2026-09-19):
-- the catalogue carries only slots that have a row, so nothing is invented.
VALUES["combat.passive_slot_1_unlock_level"] = nil
VALUES["combat.passive_slot_2_unlock_level"] = 20
data = catalogue()
assert(data.passiveSlotLevels[1] == nil, "an absent gate has no entry")
assert(data.passiveSlots == 1, "the locked slot does not open, got " .. tostring(data.passiveSlots))
VALUES["combat.passive_slot_1_unlock_level"] = 10

-- passive_skill_slots 5 with the four existing rows: the fifth is locked.
VALUES["combat.passive_skill_slots"] = 5
data = catalogue()
assert(data.passiveSlotCount == 5, "five configured, got " .. tostring(data.passiveSlotCount))
assert(#data.passiveSlotLevels == 4, "still the four existing gates, got " .. #data.passiveSlotLevels)
assert(data.passiveSlotLevels[5] == nil, "the fifth slot has no gate")
assert(data.passiveSlots == 4, "the gate-less fifth stays locked, got " .. tostring(data.passiveSlots))

-- An actual fifth row is consumed the moment it exists: no four-row ceiling.
VALUES["combat.passive_slot_5_unlock_level"] = 70
data = catalogue()
assert(#data.passiveSlotLevels == 5, "the fifth gate is read, got " .. #data.passiveSlotLevels)
assert(data.passiveSlotLevels[5] == 70, "with its value, got " .. tostring(data.passiveSlotLevels[5]))
assert(data.passiveSlots == 5, "the fifth slot opens at 70, got " .. tostring(data.passiveSlots))

-- Sparse gates keep slot identity: gate 1 absent, gates 2-4 present. The open
-- total is 3, but the payload must leave slot 1 without an entry so the client
-- locks exactly that slot and shifts no other (PM review 2026-09-19).
VALUES["combat.passive_skill_slots"] = 4
VALUES["combat.passive_slot_1_unlock_level"] = nil
VALUES["combat.passive_slot_2_unlock_level"] = 10
VALUES["combat.passive_slot_3_unlock_level"] = 20
VALUES["combat.passive_slot_4_unlock_level"] = 30
VALUES["combat.passive_slot_5_unlock_level"] = nil
data = catalogue()
assert(data.passiveSlotLevels[1] == nil, "slot 1 has no gate")
assert(data.passiveSlotLevels[2] == 10 and data.passiveSlotLevels[3] == 20
       and data.passiveSlotLevels[4] == 30, "slots 2-4 keep their own gates")
assert(data.passiveSlots == 3, "three open, slot 1 locked, got " .. tostring(data.passiveSlots))

-- A non-monotonic tuned gate is carried per slot, not sorted: gate 2 at 90
-- leaves slots 1, 3 and 4 open at level 70.
VALUES["combat.passive_slot_1_unlock_level"] = 10
VALUES["combat.passive_slot_2_unlock_level"] = 90
data = catalogue()
assert(data.passiveSlotLevels[2] == 90, "the second gate is carried as tuned")
assert(data.passiveSlots == 3, "gates 1, 3 and 4 met at 70, got " .. tostring(data.passiveSlots))

-- --- instanceEdits: the Show answer's hint (diablocraft-td1h) ------------------
-- True only where C++ GreaterRiftGuardianDead allows edits: the run of the live floor the
-- player stands on (dc_rift_floor by instance, rift floors Part F6), on the player's own
-- map, mode gr, state complete or closed. It is a hint for opening the screen;
-- SetSlot/SetPassive keep the rule.
local function edits() return catalogue().instanceEdits end

player.instance, player.map = 0, 0
riftQueries = 0
assert(edits() == false, "outside an instance there is no hint")
assert(riftQueries == 0, "and dc_rift_floor is not read")

player.instance, player.map = 77, 600
for _, case in ipairs({
    {state = "open", want = false, why = "a Greater Rift before its Guardian appears"},
    {state = "guardian", want = false, why = "a Greater Rift with its Guardian alive"},
    {state = "complete", want = true, why = "a Greater Rift whose Guardian is dead"},
    {state = "closed", want = true, why = "a paid or closed Greater Rift (GreaterRiftGuardianDead allows it)"},
}) do
    riftRows[77] = {600, "gr", case.state}
    assert(edits() == case.want, case.why .. ": expected " .. tostring(case.want))
end
assert(lastSql:find("dc_rift_floor f JOIN dc_rift r ON r.id=f.run_id", 1, true)
    and lastSql:find("f.closed_at IS NULL", 1, true),
    "the run is read through the floor the player stands on: " .. tostring(lastSql))
riftRows[77] = {600, "nr", "complete"}
assert(edits() == false, "a Nephalem Rift stays shut, Guardian dead or not")
riftRows[77] = {601, "gr", "complete"}
assert(edits() == false, "a floor for another map is not this instance's run (a reused instance id)")
riftRows[77] = nil
assert(edits() == false, "an instance with no floor row (a dungeon) stays shut")

-- The data-only Set (Refresh, AIO init) never carries the hint: only Show opens.
riftRows[77] = {600, "gr", "complete"}
pushed = nil
serverHandlers.Refresh(player)
assert(pushed and pushed.action == "Set" and pushed.payload.instanceEdits == nil, "Set carries no hint")
player.instance, player.map, riftRows[77] = 0, 0, nil

print('Skills server catalogue checks passed')
