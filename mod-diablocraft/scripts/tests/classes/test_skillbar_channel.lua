-- luacheck: globals AIO DCTunables WorldDBQuery CharDBQuery
-- luacheck: ignore 111 121 122 431 432
-- Run from repo root with `lua5.1 mod-diablocraft/scripts/tests/classes/test_skillbar_channel.lua`.
--
-- The generic channel stop of dc_skillbar.lua (vz49.1, docs/contracts/skillbar-messages.md): the
-- client observer (Torment/ChannelObserver.lua) sends Channel "stop" with the spell id of the
-- channel whose key was let go. It ends the player's own running channel when that is the spell
-- named, and nothing else; a start is the native cast's, so it casts nothing here.

_G.WorldDBQuery = function() return nil end
_G.CharDBQuery = function() return nil end
_G.DCTunables = {Get = function() return nil end, Has = function() return false end,
                 Or = function(_, _, fallback) return fallback end}
local handlers
_G.AIO = {
    AddAddon = function() return true end,
    AddHandlers = function(_, table) handlers = table return table end,
    AddOnInit = function() end,
    Handle = function() end,
}
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore

local channel, interrupts, casts = nil, {}, {}
local player = {alive = true}
function player:IsAlive() return self.alive end
function player:GetCurrentSpell(kind)
    assert(kind == 2, "reads the channelled slot (CURRENT_CHANNELED_SPELL)")
    return channel and {GetEntry = function() return channel end}
end
function player:InterruptSpell(kind, withDelayed)
    interrupts[#interrupts + 1] = {kind, withDelayed}
    channel = nil
end
function player:CastSpell(_, spell) casts[#casts + 1] = spell end
dofile('mod-diablocraft/lua/aio/dc_skillbar.lua')

assert(type(handlers.Channel) == "function", "dc_skillbar.lua handles the generic Channel message")

channel = 83104
handlers.Channel(player, "stop", 83104)
assert(#interrupts == 1 and interrupts[1][1] == 2 and interrupts[1][2] == false,
    "a stop for the spell that is channelling ends that channel")

channel = 83104
handlers.Channel(player, "stop", 81004)
assert(#interrupts == 1 and channel == 83104, "a stop naming another spell leaves the running channel")

channel = nil
handlers.Channel(player, "stop", 83104)
assert(#interrupts == 1, "a stop with nothing channelling does nothing")

channel = 83104
handlers.Channel(player, "start", 83104)
assert(#interrupts == 1 and #casts == 0, "a start casts and ends nothing: the native cast started the channel")

player.alive = false
handlers.Channel(player, "stop", 83104)
assert(#interrupts == 1, "a dead player is not touched")
player.alive = true
handlers.Channel(nil, "stop", 83104)

print("test_skillbar_channel: ok")
