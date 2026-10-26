-- luacheck: globals DCRange DCTunables
-- One walk-away close for every window opened at an NPC: the Stash, the Mystic, the Blacksmith and
-- the Jeweler (it began as dc_stash.lua's
-- watchRange and shut). Server only: this file never calls AIO.AddAddon(), so nothing here reaches a
-- client. Its name sorts before every caller (dc_aio_range < dc_blacksmith < dc_crafting < dc_jeweler
-- < dc_stash), the way dc_aio_ui.lua does for the client kit.
--
-- There is no movement hook, so while a window is up the server re-runs that window's own action
-- gate on a timer. The first time the gate fails it stops watching and sends the window its close
-- message. Because the gate is the one every action is refused on, the window is gone before an
-- action could be refused.
local AIO = AIO or require("AIO")

DCRange = {}

-- constant: how often an open window re-runs its gate (dc_stash.lua's WATCH_MS, moved here).
local WATCH_MS = 500

local watch = {}   -- guid -> channel -> the watcher's event id

function DCRange.Unwatch(player, channel)
    local mine = watch[player:GetGUIDLow()]
    if mine and mine[channel] then
        player:RemoveEventById(mine[channel])
        mine[channel] = nil
    end
end

-- One watcher per player and window (its AIO channel). gate(player) is true while the window may
-- stay open; close(player) runs once, after the watcher has stopped.
function DCRange.Watch(player, channel, gate, close)
    DCRange.Unwatch(player, channel)
    local guid = player:GetGUIDLow()
    watch[guid] = watch[guid] or {}
    watch[guid][channel] = player:RegisterEvent(function(_, _, _, watched)
        if not watched or not watched:IsInWorld() or gate(watched) then return end
        DCRange.Unwatch(watched, channel)
        close(watched)
    end, WATCH_MS, 0)
end

-- An artisan window: open while its NPC is within crafting.artisan_interaction_range_yards, the
-- range C++ Artisan() refuses every action outside; then `Close` on its channel.
function DCRange.Artisan(player, channel, entry)
    DCRange.Watch(player, channel, function(watched)
        local range = DCTunables.Get("crafting", "artisan_interaction_range_yards")
        return range and watched:GetNearestCreature(range, entry)
    end, function(watched) AIO.Handle(watched, channel, "Close") end)
end

RegisterPlayerEvent(4, function(_, player)               -- logout
    for channel in pairs(watch[player:GetGUIDLow()] or {}) do DCRange.Unwatch(player, channel) end
    watch[player:GetGUIDLow()] = nil
end)
