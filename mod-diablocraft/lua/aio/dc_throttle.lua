-- luacheck: globals DCThrottle GetCurrTime
-- Shared per-player token bucket for server-side AIO handlers (security G1).
--
-- The world thread runs every handler synchronously, and several Refresh
-- handlers do tens of synchronous database queries per call. A modified client
-- can send them far faster than any player plays, so each DB-querying handler
-- asks this bucket first and drops the excess instead of queueing it.
--
-- The limits are chosen so ordinary play never trips them: a burst is what a screen legitimately sends while it
-- settles, and the refill is well above the client's own debounce. A caller
-- that is over budget is dropped, never buffered.
--
-- The clock is GetCurrTime(): ALE registers GetCurrTime (milliseconds,
-- LuaFunctions.cpp) and GetGameTime, but not the client's GetTime -- calling
-- that here would error on the first Refresh and break every throttled screen.
DCThrottle = DCThrottle or {}
local T = DCThrottle

local buckets = {}

-- key identifies the handler; rate is tokens per second and burst is the bucket
-- size. Returns true when the call may run, false when it must be dropped.
function T.Allow(player, key, rate, burst)
    if not player or not key then return false end
    local byKey = buckets[key]
    if not byKey then byKey = {}; buckets[key] = byKey end
    local guid = player:GetGUIDLow()
    local b = byKey[guid]
    local now = GetCurrTime() / 1000
    if not b then
        b = {tokens = burst, last = now}
        byKey[guid] = b
    end
    local elapsed = now - b.last
    if elapsed < 0 then elapsed = 0 end -- GetCurrTime is uint32 ms and wraps
    if elapsed > 0 then
        b.tokens = math.min(burst, b.tokens + elapsed * rate)
    end
    b.last = now
    if b.tokens < 1 then return false end
    b.tokens = b.tokens - 1
    return true
end

-- Drop a player's buckets on logout so the table does not keep one entry per
-- character that ever logged in.
RegisterPlayerEvent(4, function(_, player)
    if not player then return end
    local guid = player:GetGUIDLow()
    for _, byKey in pairs(buckets) do byKey[guid] = nil end
end)
