-- Security G1: the shared per-player token bucket. A normal refresh rate always
-- passes; a burst is capped; the excess is dropped, never queued. Run from the
-- repo root:
--   lua mod-diablocraft/scripts/tests/ui/test_dc_throttle.lua
--
-- The clock stub mirrors ALE: GetCurrTime is defined (milliseconds) and GetTime
-- is deliberately NOT, because ALE registers GetGameTime/GetCurrTime and never
-- GetTime. If dc_throttle.lua calls GetTime the suite errors instead of passing.
-- luacheck: globals RegisterPlayerEvent GetCurrTime

local nowMs = 100000
function GetCurrTime() return nowMs end
local logoutHook
function RegisterPlayerEvent(event, fn)
    assert(event == 4)
    logoutHook = fn
end

assert(rawget(_G, "GetTime") == nil, "the harness leaves GetTime undefined, as ALE does")
dofile("mod-diablocraft/lua/aio/dc_throttle.lua")

local function player(guid)
    return {GetGUIDLow = function() return guid end}
end

local a, b = player(1), player(2)

-- Burst is allowed exactly, then the excess is dropped.
local allowed = 0
for _ = 1, 10 do if DCThrottle.Allow(a, "test:refresh", 5, 10) then allowed = allowed + 1 end end
assert(allowed == 10, "a burst of 10 passes, got " .. allowed)
assert(not DCThrottle.Allow(a, "test:refresh", 5, 10), "the 11th call in the same instant is dropped")

-- Normal sustained traffic (one call per 0.25 s, 4/s) is under the 5/s refill
-- and always passes.
for _ = 1, 20 do
    nowMs = nowMs + 250
    assert(DCThrottle.Allow(a, "test:refresh", 5, 10), "4/s traffic is never dropped")
end

-- A flood is capped near the refill rate: one second of calls at 1 ms
-- intervals (1000/s) yields about 5 passes, never 1000.
nowMs = nowMs + 60000
local flood = 0
for _ = 1, 1000 do
    if DCThrottle.Allow(a, "test:refresh", 5, 10) then flood = flood + 1 end
    nowMs = nowMs + 1
end
assert(flood <= 16, "a 1000/s flood is capped near the burst+refill, got " .. flood)

-- The uint32 millisecond clock wraps: a smaller "now" refills nothing and just
-- re-bases, it must not leave the bucket permanently empty.
nowMs = 1000
DCThrottle.Allow(a, "test:refresh", 5, 10)
nowMs = 2000
assert(DCThrottle.Allow(a, "test:refresh", 5, 10), "the bucket refills after a wrapped clock")

-- The bucket is per player.
nowMs = nowMs + 1000
assert(DCThrottle.Allow(b, "test:refresh", 5, 10), "another player has their own bucket")

-- The key separates handlers.
nowMs = nowMs + 1000
assert(DCThrottle.Allow(a, "other:refresh", 5, 10), "a different key has its own bucket")

-- Logout drops the player's buckets.
nowMs = nowMs + 1000
logoutHook(4, a)
local afterLogout = 0
for _ = 1, 10 do if DCThrottle.Allow(a, "test:refresh", 5, 10) then afterLogout = afterLogout + 1 end end
assert(afterLogout == 10, "logout resets the bucket to a full burst")

print("PASS: token bucket caps bursts and floods, passes normal traffic (G1)")
