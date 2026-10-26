-- luacheck: globals DCTunables
-- Shared server-side reader for dc_tunables (tunables phase 2, section C).
--
-- This file deliberately never calls AIO.AddAddon(), so nothing here is sent to
-- a client. The read pattern is docs/contracts/tunables.md: one WORLD query at
-- first use builds a cache, and a `.dc tunables ...` command drops it, so the
-- next read sees the number the command wrote. No C++ bridge.
DCTunables = DCTunables or {}
local T = DCTunables

local cache

local function load()
    cache = {}
    local rows = WorldDBQuery(
        "SELECT category,name,CAST(COALESCE(tuned_value,d3_value) AS CHAR) FROM dc_tunables "
        .. "WHERE COALESCE(tuned_value,d3_value) IS NOT NULL")
    if rows then
        repeat
            local category, name, value = rows:GetString(0), rows:GetString(1), tonumber(rows:GetString(2))
            if value then
                cache[category] = cache[category] or {}
                cache[category][name] = value
            end
        until not rows:NextRow()
    end
end

-- The effective value (tuned_value, else d3_value), or nil when the row is
-- missing or has neither. Safe in a hot path: it reads the cache.
function T.Get(category, name)
    if not cache then load() end
    local group = cache[category]
    return group and group[name] or nil
end

function T.Has(category, name)
    return T.Get(category, name) ~= nil
end

-- For a value read here but owned by another module's row (the stash keys).
-- The literal keeps the old number working and is reported once, so a
-- not-yet-migrated row is loud rather than silent.
local reported = {}
function T.Or(category, name, fallback)
    local value = T.Get(category, name)
    if value then return value end
    local key = category .. "." .. name
    if not reported[key] then
        reported[key] = true
        PrintError(("[tunables] %s.%s is not set; using the literal %s until it is migrated")
            :format(category, name, tostring(fallback)))
    end
    return fallback
end

-- ALE fires PLAYER_EVENT_ON_COMMAND (42) before the command runs, so drop the
-- cache here and let the next read query (docs/contracts/tunables.md).
-- The reload side effect is admin-only (`.dc tu*` is GM 3 under
-- the security rule); a non-admin typing the text must not be able to make every
-- later read hit the database. Everyone else gets the normal "no such command"
-- from the core.
RegisterPlayerEvent(42, function(_, player, text)
    if type(text) == "string" and text:lower():match("^dc%s+tu")
        and player and player:GetGMRank() >= 3 then
        cache = nil
        reported = {}
    end
end)
