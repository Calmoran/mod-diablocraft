-- luacheck: ignore 111 112 113 121 122 142 143 211 212 213 431 432
-- Run from the repo root: lua mod-diablocraft/scripts/tests/rifts/test_rift_tracker_server.lua
--
-- diablocraft-rift-tracker (ruling 2026-10-03): the server half of
-- mod-diablocraft/lua/aio/dc_riftbar.lua pushes the run to every enrolled member who holds
-- its quest, IN THE RIFT AND IN TOWN, until someone turns in; nobody else sees it.
-- The run is found through dc_rift_member, never through the instance the player stands in.
-- The database is a double: the test checks the query's own clauses and answers it with
-- the row a member would get, so what is proved is what the file does with that row.
local SOURCE = os.getenv("DC_RIFT_LUA") or "mod-diablocraft/lua/aio/dc_riftbar.lua"

local sent, queries, events, onInit = {}, {}, {}, nil
local answer = {} -- player guid -> the joined row, or nil
local floors = {} -- "run id:instance id" -> {map = map id, floor = floor number}
local function rowOf(values)
    local function get(_, column) return values[column + 1] end
    return {GetUInt32 = get, GetUInt64 = get, GetString = get, GetInt32 = get, NextRow = function() return false end}
end
function CharDBQuery(sql)
    queries[#queries + 1] = sql
    local guid = tonumber(sql:match("player_guid%s*=%s*(%d+)"))
    if guid then
        local values = answer[guid]
        return values and rowOf(values) or nil
    end
    local runId, instance, mapId = sql:match("f.run_id=(%d+) AND f.instance_id=(%d+) AND f.map_id=(%d+)")
    if not runId then return nil end
    local row = floors[runId .. ":" .. instance]
    if not row or row.map ~= tonumber(mapId) then return nil end
    return rowOf({row.floor})
end
function RegisterPlayerEvent(id, fn) events[id] = fn end
DCThrottle = {Allow = function() return true end}
AIO = {AddAddon = function() return true end,
    AddHandlers = function(_, h) return h end,
    AddOnInit = function(fn) onInit = fn end,
    Handle = function(player, channel, name, data) sent[#sent + 1] = {player = player, channel = channel, name = name, data = data} end}

local function player(guid, quests, instance, map)
    return {guid = guid, quests = quests or {},
        GetGUIDLow = function(self) return self.guid end,
        GetGUID = function(self) return self.guid end,
        HasQuest = function(self, id) return self.quests[id] == true end,
        -- Standing in town: no instance. The file must not care.
        GetInstanceId = function() return instance or 0 end,
        GetMapId = function() return map or 0 end}
end

dofile(SOURCE)
assert(type(onInit) == "function" and events[3] and events[28] and events[7], "pushes at AIO init, login, map change and kill")

local function last() return sent[#sent] end

-- The row: id, mode, state, progress, required_units, quest_id, closing flag.
local OPEN = {41, "nr", "open", 300, 1200, 910020, 0}

-- 1. An enrolled member holding the quest, standing in TOWN, gets the run.
local member = player(1, {[910020] = true}, 0)
answer[1] = OPEN
local before = #queries
events[3](nil, member)
assert(#queries == before + 1, "a holder of the run's quest is looked up in the database")
assert(last().player == member and last().name == "Update", "the enrolled holder in town gets the run, got " .. tostring(last().name))
local data = last().data
assert(data.run == 41 and data.mode == "nr" and data.state == "open" and data.progress == 300 and data.required == 1200,
    "the pushed row carries run, mode, state, progress and required")
local sql = queries[#queries]
assert(sql:find("dc_rift_member", 1, true) and sql:find("m.state IN ('enrolled','offline')", 1, true)
    and sql:find("r.state<>'closed'", 1, true) and sql:find("player_guid=1", 1, true),
    "the run is looked up through the member's own enrolment: " .. sql)
assert(not sql:find("instance_id", 1, true), "never through the instance the player stands in")

-- Inside the rift the same member gets the same entry.
member = player(1, {[910020] = true}, 7001)
events[28](nil, member)
assert(last().name == "Update" and last().data.run == 41, "and in the rift")

-- 1b. The floor the player stands on (rift floors Part F6): the run's live dc_rift_floor row
-- whose instance and map the player is in, carried as `floor`. In town there is no floor.
floors["41:7001"] = {map = 600, floor = 2}
member = player(1, {[910020] = true}, 7001, 600)
events[28](nil, member)
assert(last().name == "Update" and last().data.floor == 2,
    "in the rift the run carries the floor the player stands on, got " .. tostring(last().data.floor))
local floorSql = queries[#queries]
assert(floorSql:find("dc_rift_floor f WHERE f.run_id=41 AND f.instance_id=7001 AND f.map_id=600", 1, true)
    and floorSql:find("f.closed_at IS NULL", 1, true),
    "the floor is read from dc_rift_floor for the run, the instance and the map: " .. floorSql)
-- The same instance id on another map (the core reuses ids) is not this floor.
member = player(1, {[910020] = true}, 7001, 601)
events[28](nil, member)
assert(last().data.floor == nil, "an instance id that now names another map carries no floor")
-- Town: no instance, no floor; dc_rift_floor is not read.
member = player(1, {[910020] = true}, 0)
local beforeFloor = #queries
events[3](nil, member)
assert(last().data.floor == nil, "in town the run carries no floor")
assert(#queries == beforeFloor + 1, "and dc_rift_floor is not read outside an instance")

-- 2. Nobody else.
-- Not enrolled (no live row for them): Hide.
local stranger = player(2, {}, 7001)
local beforeHide = #queries
events[3](nil, stranger)
assert(last().player == stranger and last().name == "Hide", "someone not enrolled sees nothing, even standing in the rift")
assert(#queries == beforeHide, "a player holding no rift quest costs no database query")
-- Enrolled but no longer holding the quest (abandoned, stripped): Hide.
local dropped = player(3, {}, 0)
answer[3] = OPEN
events[3](nil, dropped)
assert(last().name == "Hide", "an enrolled member who no longer holds the quest sees nothing")
-- Holding a different quest than the run's: Hide.
local other = player(4, {[910023] = true}, 0)
answer[4] = OPEN
events[3](nil, other)
assert(last().name == "Hide", "holding another rift quest is not holding this run's")

-- 3. Someone turned in: the run is closing and every holder was paid, so the entry leaves.
answer[1] = {41, "nr", "complete", 1200, 1200, 910020, 1}
member = player(1, {[910020] = true}, 0)
events[3](nil, member)
assert(last().name == "Hide", "after the first turn-in (closing_at set) the entry leaves every holder")

-- 4. The states go through as they are.
for _, state in ipairs({"open", "guardian", "complete"}) do
    answer[1] = {41, "nr", state, 1200, 1200, 910020, 0}
    events[7](nil, member)
    assert(last().name == "Update" and last().data.state == state, "state " .. state .. " is pushed as is")
end

-- 4b. A Greater Rift (diablocraft-g5dh, greater-rift-tracker.md): the level, the result and
-- the seconds on the clock ride along, the seconds read from the server's own clock in the
-- same query. Row: ..., closing flag, gr_rank, outcome, time_left, seconds to the deadline.
sql = queries[#queries]
assert(sql:find("UNIX_TIMESTAMP(r.deadline) - UNIX_TIMESTAMP(NOW())", 1, true),
    "the seconds left come from the server's clock in the query: " .. sql)
local gr = player(5, {[910023] = true}, 0)
answer[5] = {51, "gr", "open", 300, 1800, 910023, 0, 25, "pending", 0, 754}
events[7](nil, gr)
data = last().data
assert(last().name == "Update" and data.mode == "gr" and data.rank == 25 and data.outcome == "pending"
    and data.left == 754, "a running Greater Rift pushes its level, pending and the seconds to the deadline")
-- Beaten: the clock is final, time_left, whatever the deadline says now.
answer[5] = {51, "gr", "complete", 1800, 1800, 910023, 0, 25, "success", 312, 0}
events[7](nil, gr)
data = last().data
assert(data.outcome == "success" and data.left == 312, "a beaten run's clock is its time_left, got " .. tostring(data.left))
-- Failed: 0.
answer[5] = {51, "gr", "guardian", 1800, 1800, 910023, 0, 25, "expired", 0, 0}
events[7](nil, gr)
data = last().data
assert(data.outcome == "expired" and data.left == 0, "a failed run's clock reads 0")
-- No deadline yet (the query's -1): no clock.
answer[5] = {51, "gr", "open", 0, 1800, 910023, 0, 25, "pending", 0, -1}
events[7](nil, gr)
assert(last().data.left == nil and last().data.rank == 25, "no deadline yet, no clock")
-- A Nephalem Rift carries none of it.
answer[1] = {41, "nr", "open", 300, 1200, 910020, 0, 0, "pending", 0, -1}
events[7](nil, member)
data = last().data
assert(data.rank == nil and data.left == nil and data.outcome == nil, "a Nephalem Rift pushes no Greater Rift fields")

-- 5. The refresh is throttled and answers the same way.
local handlers
AIO.AddHandlers = function(_, h) handlers = h; return h end
dofile(SOURCE)
local allowed = true
DCThrottle = {Allow = function() return allowed end}
local count = #sent
handlers.Refresh(member)
assert(#sent == count + 1 and last().name == "Update", "a refresh pushes")
allowed = false
handlers.Refresh(member)
assert(#sent == count + 1, "a flood is dropped")

print("PASS rift tracker server: the run reaches an enrolled holder in town and in the rift, through dc_rift_member; "
    .. "not the unenrolled, not a member without the quest, not after the first turn-in; the floor the holder stands on "
    .. "from dc_rift_floor; a Greater Rift's level, result "
    .. "and server-clock seconds")
