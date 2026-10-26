-- Security G2: the `.dc tunables ...` cache-drop in dc_tunables.lua fires only
-- for GM level 3. The cache drop is the observable: DCTunables.Get() queries the
-- database only when the cache is empty, so the query count proves whether a
-- command text dropped it. Run from the repo root:
--   lua mod-diablocraft/scripts/tests/tunables/test_dc_tunables_gate.lua
-- luacheck: globals RegisterPlayerEvent WorldDBQuery PrintError DCTunables

local queries = 0
local commandHook
function RegisterPlayerEvent(event, fn)
    assert(event == 42)
    commandHook = fn
end
function PrintError() end

local function cursor()
    local index = 0
    return {
        GetString = function(_, column)
            index = index + 1
            return ({"rifts", "test_throwaway", "7"})[column + 1]
        end,
        NextRow = function() return false end,
    }
end
function WorldDBQuery()
    queries = queries + 1
    return cursor()
end

dofile("mod-diablocraft/lua/aio/dc_tunables.lua")
assert(type(DCTunables.Get) == "function", "DCTunables.Get registered")
assert(type(commandHook) == "function", "the tunables command hook is registered")

local function player(rank) return {GetGMRank = function() return rank end} end
local function read() return DCTunables.Get("rifts", "test_throwaway") end

-- First read loads; a second read is served from the cache.
assert(read() == 7 and queries == 1, "first read queries once")
assert(read() == 7 and queries == 1, "second read is cached")

-- A non-admin typing the text must not drop the cache: no new query.
commandHook(42, player(0), "dc tunables set rifts test_throwaway 9")
assert(queries == 1, "GM 0 cannot drop the cache")
commandHook(42, player(2), "dc tunables set rifts test_throwaway 9")
assert(queries == 1, "GM 2 cannot drop the cache")

-- GM 3 does. The drop itself reads nothing (the value is not written yet) and
-- returns nothing, so the core goes on to run the real command.
local stop = commandHook(42, player(3), "dc tunables set rifts test_throwaway 9")
assert(stop == nil, "the hook does not stop the real command")
assert(queries == 1, "the cache drop reads nothing")
assert(read() == 7 and queries == 2, "GM 3 drops the cache so the next read queries")

-- A non-tunables command never touches the cache.
commandHook(42, player(3), "dc stash")
assert(read() == 7 and queries == 2, "another .dc command does not drop the cache")

print("PASS: tunables cache-drop is GM-3 only (G2)")
