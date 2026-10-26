-- Drives the built AIO_Server/AIO.lua server rules added by
-- core-patches/0020-aio-server-security.patch:
--   G2: `.aio trace|debug|pcall|printio` is GM 3 only, everyone else falls
--       through to the core's normal "no such command";
--   G1: a message over 100 blocks is dropped whole, and a per-player bucket
--       (200 burst, 100 blocks/s) drops the excess rather than queueing it.
--
-- Invoked by core-patches/tests/test_aio_server_security.py against the output
-- of mod-diablocraft/scripts/build_live_aio.sh, with the pinned checkout as the
-- control: the same harness must fail on the unpAtched pin, so a green run means
-- the patch is what makes it pass.
--
-- usage: lua aio_server_security_harness.lua <built-AIO_Server-dir>
local built = assert(arg[1], "usage: aio_server_security_harness.lua <built-AIO_Server-dir>")
package.path = built .. "/?.lua;" .. built .. "/Dep_Smallfolk/?.lua;" .. built
    .. "/Dep_LuaSrcDiet/?.lua;" .. built .. "/Dep_crc32lua/?.lua;" .. built
    .. "/lualzw-zeros/?.lua;" .. package.path
local realRequire = require
function require(name) if name == "AIO" then return {} end return realRequire(name) end
local Smallfolk = realRequire("smallfolk")

local clock = 0
os.time = function() return clock end

function GetLuaEngine() return {} end
function GetStateMapId() return -1 end
function CreateLuaEvent() return 1 end
function RemoveEventById() end
local hooks = {}
function RegisterPlayerEvent(e, fn) hooks["p" .. e] = fn end
function RegisterServerEvent(e, fn) hooks["s" .. e] = fn end
function GetPlayersInWorld() return {} end
function PrintInfo() end
function PrintError() end
function SendWorldMessage() end
function GetPlayerByGUID() return nil end
function UnitName() return "Tester" end
local function stub()
    local t = {}
    function t:RegisterEvent() end
    function t:SetScript() end
    function t:HookScript() end
    function t:CreateFontString() return stub() end
    function t:SetPoint() end
    function t:SetWidth() end
    function t:SetHeight() end
    function t:GetName() return nil end
    return t
end
function CreateFrame() return stub() end

-- Spy on the parse timeout hook. The patch clears it on every drop; a dropped
-- message that left the hook installed would abort unrelated code later.
local realSetHook = debug.sethook
local hookInstalled = false
debug.sethook = function(...)
    hookInstalled = select("#", ...) > 0
    return realSetHook(...)
end

assert(loadfile(built .. "/AIO.lua"))()
assert(type(hooks.p42) == "function", "the .aio command hook registered")
assert(type(hooks.s30) == "function", "the addon-message hook registered")
local AIO = assert(_G.AIO, "AIO global missing")

-- ---- G2: the .aio switches are GM 3 only ---------------------------------
local function player(rank, guid)
    return {rank = rank, guid = guid or 1,
        GetGMRank = function(self) return self.rank end,
        GetGUIDLow = function(self) return self.guid end,
        SendBroadcastMessage = function() end}
end
assert(hooks.p42(42, player(0), "aio debug") == true, "GM 0 falls through (returns true)")
assert(hooks.p42(42, player(2), "aio printio") == true, "GM 2 falls through")
assert(hooks.p42(42, player(3), "aio debug") == false, "GM 3 is handled (returns false)")
assert(hooks.p42(42, nil, "aio debug") == true, "console is left alone")
-- Reverted (no gate): GM 0 would return false, failing the assertions above.

-- ---- G1: block cap and per-player budget ---------------------------------
local handled = 0
AIO.RegisterEvent("TestBlock", function(_, arg) handled = handled + 1 end)

-- The client splits long messages; parts are reassembled before parsing, so a
-- message can exceed the 510-byte part check. Rebuild that envelope here.
local function enc16(value)
    local high = math.floor(value / 254)
    return string.char(high + 1) .. string.char(value - high * 254 + 1)
end
local messageId = 0
local function sendLong(p, data)
    messageId = messageId + 1
    local payload = Smallfolk.dumps(data)
    local chunks = {}
    for i = 1, #payload, 250 do chunks[#chunks + 1] = payload:sub(i, i + 249) end
    for index, chunk in ipairs(chunks) do
        hooks.s30(30, p, 7, "CAIO", enc16(messageId) .. enc16(#chunks) .. enc16(index) .. chunk, p)
    end
end
local function block() return {1, "TestBlock", "x"} end
local function blocks(n) local t = {}; for i = 1, n do t[i] = block() end; return t end

local p = player(0, 42)
clock = 1000
sendLong(p, blocks(1))
assert(handled == 1, "a one-block message is handled")
assert(not hookInstalled, "a handled message leaves no parse hook installed")

-- A message over the block cap is dropped whole, and the parse hook the handler
-- set is cleared before the drop returns.
handled = 0
sendLong(p, blocks(101))
assert(handled == 0, "a 101-block message is dropped, not parsed")
assert(not hookInstalled, "a dropped over-cap message clears the parse hook")

-- The per-player budget drops the excess. Burst is 200 blocks: eight 25-block
-- messages pass and the ninth is dropped.
handled = 0
clock = clock + 100
for _ = 1, 8 do sendLong(p, blocks(25)) end
assert(handled == 200, "the burst passes exactly, got " .. handled)
sendLong(p, blocks(25))
assert(handled == 200, "over-budget message is dropped, got " .. handled)
assert(not hookInstalled, "a dropped over-budget message clears the parse hook")

-- After a second the bucket refills and normal traffic passes again.
handled = 0
clock = clock + 1
sendLong(p, blocks(25))
assert(handled == 25, "normal traffic passes again after the refill")

-- Another player has their own budget.
handled = 0
local q = player(0, 43)
sendLong(q, blocks(25))
assert(handled == 25, "the budget is per player")

print("PASS: AIO .aio gate (G2) and block cap/budget (G1)")
