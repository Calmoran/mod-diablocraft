-- luacheck: ignore 111 121
-- Run from repo root: lua mod-diablocraft/scripts/tests/items/test_stash_server.lua
--
-- The stash's server Lua (lua/aio/dc_stash.lua) against a stub ALE: what it lets
-- through to the C++ commands. Security G1 (diablocraft-stash-audit, 1b): every
-- move and every tab purchase ends in a database commit that the world thread
-- waits for, so a flood of them is dropped, not queued. Runs the real
-- dc_throttle.lua; the clock is the test's.

local handlers, sent, commands = {}, {}, {}
AIO = {
    AddHandlers = function() return handlers end,
    Handle = function(player, _, name) sent[#sent + 1] = {player = player and player:GetGUIDLow(), name = name} end,
}
DCTunables = {Or = function(_, _, default) return default end}
DCAccount = {
    Principal = function() return 1, "normal" end,
    Snapshot = function() return {gold = "0", materials = {}} end,
}
DCGrid = {
    Describe = function() return {}, {} end,
    Rarities = function() return {} end,
    Cell = function() return {} end,
}
local gossip
function RegisterCreatureGossipEvent(_, _, handler) gossip = handler end
function RegisterPlayerEvent() end
function WorldDBQuery() return nil end
function CharDBQuery() return nil end

local now = 0
function GetCurrTime() return now end
dofile("mod-diablocraft/lua/aio/dc_throttle.lua")
dofile("mod-diablocraft/lua/aio/dc_aio_range.lua")
dofile("mod-diablocraft/lua/aio/dc_stash.lua")

local function newPlayer(guid)
    local player = {}
    function player:GetGUIDLow() return guid end
    function player:IsAlive() return true end
    function player:IsInCombat() return false end
    function player:GetNearestCreature() return {} end
    function player:GossipComplete() end
    function player:IsInWorld() return true end
    function player:RegisterEvent() return 1 end
    function player:RemoveEventById() end
    function player:RunCommand(command) commands[#commands + 1] = {guid = guid, command = command} end
    return player
end

local function count(prefix, guid)
    local n = 0
    for _, entry in ipairs(commands) do
        if entry.command:find(prefix, 1, true) == 1 and (not guid or entry.guid == guid) then n = n + 1 end
    end
    return n
end

local alice, bob = newPlayer(1), newPlayer(2)
gossip(nil, alice)
gossip(nil, bob)   -- both stand at the Stash with the window open

-- A modified client sends a hundred moves in one instant: the bucket's burst gets
-- through and the rest is dropped.
for _ = 1, 100 do handlers.Move(alice, "bag", 25523, "stash", 0) end
assert(count("dc stash move", 1) == 8, "a frozen clock lets exactly the burst through, got " .. count("dc stash move", 1))

-- Dropped moves do not close the window or push a snapshot the player did not ask for.
local snapshotsBefore = 0
for _, entry in ipairs(sent) do if entry.name == "Snapshot" and entry.player == 1 then snapshotsBefore = snapshotsBefore + 1 end end
handlers.Move(alice, "bag", 25523, "stash", 0)
local snapshotsAfter = 0
for _, entry in ipairs(sent) do if entry.name == "Snapshot" and entry.player == 1 then snapshotsAfter = snapshotsAfter + 1 end end
assert(snapshotsAfter == snapshotsBefore, "a dropped move sends no snapshot")
for _, entry in ipairs(sent) do assert(entry.name ~= "CloseWindow", "throttling a move is not a reason to close the window") end

-- The bucket is per player.
handlers.Move(bob, "stash", 0, "bag", -1)
assert(count("dc stash move", 2) == 1, "another player's bucket is untouched")

-- And it refills: a second later, about five more.
now = now + 1000
for _ = 1, 100 do handlers.Move(alice, "bag", 25523, "stash", 0) end
local refilled = count("dc stash move", 1) - 8
assert(refilled >= 4 and refilled <= 6, "one second refills about five moves, got " .. refilled)

-- A bag-to-bag move is a commit too, so it spends the same bucket.
now = now + 60000
for _ = 1, 100 do handlers.Move(bob, "bag", 25523, "bag", 25524) end
assert(count("dc stash move bag 25523 bag 25524", 2) == 8, "bag-to-bag moves are throttled as well")

-- The tab purchase: two in a burst, then one every two seconds.
for _ = 1, 50 do handlers.BuyTab(alice) end
assert(count("dc stash buytab", 1) == 2, "a flood of purchases reaches the server twice, got " .. count("dc stash buytab", 1))
now = now + 2000
handlers.BuyTab(alice)
assert(count("dc stash buytab", 1) == 3, "and one more two seconds later")

-- Malformed messages still never reach the command line (the throttle did not replace those checks).
now = now + 60000
local before = #commands
handlers.Move(alice, "bag", "x", "stash", 0)
handlers.Move(alice, "bag", 1.5, "stash", 0)
handlers.Move(alice, "bag", 25523, "mail", 0)
handlers.Move(alice, "bag", 25523, "stash", 99999)
assert(#commands == before, "malformed moves are refused before the command line")

-- Walking away shuts the Stash (the shared watcher, dc_aio_range.lua): its gossip starts one 500 ms
-- watcher, an in-range tick sends nothing, out of the action range it sends CloseWindow and stops;
-- the window's own Close stops it too.
do
    local timers, nextTimer, near, asked = {}, 0, true, nil
    local carol = newPlayer(3)
    function carol:GetNearestCreature(range) asked = range; return near and {} or nil end
    function carol:RegisterEvent(fn, delay, repeats)
        nextTimer = nextTimer + 1
        timers[nextTimer] = {fn = fn, delay = delay, repeats = repeats}
        return nextTimer
    end
    function carol:RemoveEventById(id) timers[id] = nil end
    local function live() local out = {} for id, t in pairs(timers) do t.id = id; out[#out + 1] = t end return out end
    local function closes() local n = 0 for _, e in ipairs(sent) do if e.player == 3 and e.name == "CloseWindow" then n = n + 1 end end return n end
    gossip(nil, carol)
    gossip(nil, carol)
    assert(#live() == 1 and live()[1].delay == 500 and live()[1].repeats == 0, "one repeating watcher per open Stash, not one per gossip")
    local tick = live()[1]
    tick.fn(tick.id, 500, 0, carol)
    assert(closes() == 0 and timers[tick.id], "in range, the watcher keeps the Stash open")
    assert(asked == 6.5, "the watcher re-runs the action gate (ui.stash_action_range_yards), not the opening one")
    near = false
    tick.fn(tick.id, 500, 0, carol)
    assert(closes() == 1 and #live() == 0, "out of range, the watcher sends CloseWindow and stops")
    near = true
    gossip(nil, carol)
    handlers.Close(carol)
    assert(#live() == 0, "closing the window stops the watcher")
end

print("Stash server checks passed (moves and purchases throttled per player, malformed still refused, the walk-away close)")
