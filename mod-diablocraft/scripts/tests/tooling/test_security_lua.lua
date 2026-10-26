-- Security G6 (Economy half) and G10 (link-rate prune guard). Run from the repo
-- root:
--   lua mod-diablocraft/scripts/tests/tooling/test_security_lua.lua
--
-- The Inventory half of G6 is covered by test_inventory_client.lua (forged
-- DCSHEET and DCPARAGON senders); the version bound is covered by
-- test_version_notice.lua.
-- luacheck: globals UnitName SendChatMessage SlashCmdList DEFAULT_CHAT_FRAME Diablocraft DiablocraftUI

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames

function UnitName() return "Tester" end
function SendChatMessage() end
SlashCmdList = {}
DEFAULT_CHAT_FRAME = {AddMessage = function() end}
Diablocraft = {}
DiablocraftUI = {}

dofile("client-patch/addons/Torment/Economy.lua")

local watcher
for _, frame in ipairs(frames) do
    if frame.scripts and frame.scripts.OnEvent then watcher = frame end
end
assert(watcher and watcher.scripts.OnEvent, "the economy watcher is installed")
local function addon(prefix, payload, sender)
    watcher.scripts.OnEvent(watcher, "CHAT_MSG_ADDON", prefix, payload, "WHISPER", sender or "Tester")
end
local Econ = Diablocraft.Econ
assert(Econ, "Diablocraft.Econ is exported")

local VALID = "1;normal;1;500;102000=5"

-- A forged DCECON from another player is ignored, whether it is a snapshot or a
-- clear; the server's own self-whisper is accepted.
addon("DCECON", VALID, "Mallory")
assert(Econ.Balance() == nil, "a forged DCECON snapshot from another player is ignored")
addon("DCECON", VALID)
assert(Econ.Balance() == "500", "the server's own DCECON snapshot is accepted")
addon("DCECON", "clear", "Mallory")
assert(Econ.Balance() == "500", "a forged DCECON clear from another player is ignored")
addon("DCECON", "clear")
assert(Econ.Balance() == nil, "the server's own DCECON clear is accepted")

-- G10: the per-player link-rate table must be pruned, or it grows one entry per
-- GUID that ever linked. Reverting the prune removes both strings.
local src = assert(io.open("mod-diablocraft/lua/aio/dc_tooltip.lua")):read("*a")
assert(src:find("pruneRate", 1, true), "the link-rate table is swept (G10)")
assert(src:find("rate[id] = nil", 1, true), "stale link-rate ids are dropped (G10)")

print("PASS: DCECON is server-only, and the link-rate table is pruned (G6/G10)")
