-- luacheck: globals manifestText manifestReads manifestPath AIO GetConfigValue RegisterPlayerEvent CreateLuaEvent GetPlayerByGUID GetAddOnMetadata DEFAULT_CHAT_FRAME IsAddOnLoaded PrintError
-- luacheck: ignore 111 121 122 431 432
-- Run from repo root with `lua mod-diablocraft/scripts/tests/release/test_version_notice.lua`.
--
-- Drives the production `DiablocraftVersion` bridge both ways:
--   server (mod-diablocraft/lua/aio/dc_version.lua) and
--   addon  (client-patch/addons/Torment/Version.lua).
-- Offline mocks assert payload shape, substitution, one-per-session warning and
-- the non-blocking property (nothing here can refuse a login). They do not prove
-- live delivery in the client.
--
-- Contract: docs/contracts/version-enforcement.md.

local realio = io -- the server mock below replaces `io`
local handlers, sent = {}, {}
local functions_ = {}

-- ---------------------------------------------------------- server-side bridge

local serverAIO = {
    AddAddon = function() return true end,
    AddHandlers = function(_, _) return handlers end,
    Handle = function(player, channel, name, ...) sent[#sent + 1] = {player = player, channel = channel, name = name, args = {...}} end,
}
local config = {
    ["Diablocraft.VersionFile"] = "VERSION",
    ["Diablocraft.ClientMismatchMessage"] = "files out of date (patch {client}, current {current})",
}
GetConfigValue = function(key) return config[key] end

local timers = {}
CreateLuaEvent = function(fn) timers[#timers + 1] = fn end
local loginHandler, logoutHandler
RegisterPlayerEvent = function(event, fn) if event == 3 then loginHandler = fn else logoutHandler = fn end end

-- The grace callback re-resolves its player by GUID (GitHub #83). `online` is
-- the world; a guid is present only while that login session is live.
local online = {}
GetPlayerByGUID = function(guid) return online[guid] end

-- The VERSION file and the published manifest are both served by this mock. `manifestText` is the
-- manifest's content (nil = the file does not exist); tests change it between logins.
manifestText = '{"files": [], "client_patch": 33, "version": "0.1.6"}'
manifestReads = 0
manifestPath = "/srv/torment-dl/stable/manifest.json"
io = {
    open = function(path)
        if path == "VERSION" then
            local lines = {"# comment", "module=0.0.0", "schema=16", "client_patch=33"}
            local index = 0
            return {
                lines = function() return function() index = index + 1 return lines[index] end end,
                close = function() end,
            }
        end
        assert(path == manifestPath, "unexpected open: " .. tostring(path))
        manifestReads = manifestReads + 1
        if manifestText == nil then return nil end
        return {read = function() return manifestText end, close = function() end}
    end,
}

AIO = serverAIO
-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
dofile("mod-diablocraft/lua/aio/dc_version.lua")
assert(type(handlers.Report) == "function", "server did not register Report")
assert(type(loginHandler) == "function" and type(logoutHandler) == "function", "login/logout reset registered")

local player = {broadcast = nil}
function player:GetGUIDLow() return 1 end
function player:GetGUID() return "G1" end
function player:GetName() return "Tester" end
function player:SendBroadcastMessage(text) self.broadcast = text end
online["G1"] = player

local function report(patch) sent = {}; handlers.Report(player, patch); return sent[1] end

local status = report("33")
assert(status.name == "Status", "server answers with Status")
assert(status.args[1] == "0.0.0" and status.args[2] == 16 and status.args[3] == "33", "module/schema/patch fields")
assert(status.args[4] == "33" and status.args[5] == true and status.args[6] == false, "matching: addon true, mismatch false")
assert(status.args[7] == nil, "matching: no message")

status = report("32")
assert(status.args[4] == "32" and status.args[5] == true and status.args[6] == true, "older patch: mismatch")
assert(status.args[7] == "files out of date (patch 32, current 33)", "older patch message substituted")

status = report("")
assert(status.args[4] == nil and status.args[5] == false and status.args[6] == true, "no value: addon false")
assert(status.args[7] == "files out of date (patch missing, current 33)", "missing client shown as missing")

-- Security G10: an over-long Report is treated as no report, not echoed back.
status = report(string.rep("9", 16))
assert(status.args[4] == string.rep("9", 16) and status.args[6] == false, "a 16-char Report is still read, and a higher patch is never warned")
status = report(string.rep("9", 17))
assert(status.args[4] == nil and status.args[5] == false and status.args[6] == true,
    "a 17-char Report is dropped as missing, never echoed")

-- Missing addon: the login grace timer fires a chat-only warning once.
online["G1"] = player
logoutHandler(4, player)
loginHandler(3, player)
assert(#timers == 1, "login schedules one grace callback")
local grace = timers[#timers]
grace()
assert(player.broadcast == "Torment: files out of date (patch missing, current 33)", "missing addon chat warning")
player.broadcast = nil
grace()
assert(player.broadcast == nil, "one warning per session")

-- GitHub #83: logging out before the grace callback fires must not call into the
-- invalidated Player. The callback re-resolves by GUID and finds nobody online.
online["G1"] = player
logoutHandler(4, player)
loginHandler(3, player)
local stale = timers[#timers]
online["G1"] = nil
logoutHandler(4, player)
player.broadcast = nil
stale()
assert(player.broadcast == nil, "callback after logout sends nothing")

-- Relog inside the grace window is a different session: the previous session's
-- callback stays quiet, the new login's notice still fires.
online["G1"] = player
logoutHandler(4, player)
loginHandler(3, player)
local previous = timers[#timers]
logoutHandler(4, player)
loginHandler(3, player)
local current = timers[#timers]
assert(previous ~= current, "relog schedules a new grace callback")
player.broadcast = nil
previous()
assert(player.broadcast == nil, "previous session's callback sends nothing after relog")
current()
assert(player.broadcast == "Torment: files out of date (patch missing, current 33)", "current session's notice still fires")

-- A player who reported never gets the chat warning.
online["G1"] = player
logoutHandler(4, player)
loginHandler(3, player)
local reported = timers[#timers]
sent = {}
handlers.Report(player, "33")
player.broadcast = nil
reported()
assert(player.broadcast == nil, "reported player gets no missing-addon chat")

-- ------------------------------------------------------------------ addon half

local chat = {}
local addonHandlers = {}

-- The widget layer is ONE shared strict mock (diablocraft-yey2); the doubles
-- below are this test's own client globals.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)
local sentToServer
local clientAIO = {
    AddHandlers = function(_, _) return addonHandlers end,
    Handle = function(channel, name, ...) sentToServer = {channel = channel, name = name, args = {...}} end,
}
AIO = clientAIO
GetAddOnMetadata = function(_, field) if field == "X-Torment-Client-Patch" then return "33" end end
IsAddOnLoaded = function() return false end
DEFAULT_CHAT_FRAME = {AddMessage = function(_, text) chat[#chat + 1] = text end}

dofile("client-patch/addons/Torment/Version.lua")
assert(type(addonHandlers.Status) == "function", "addon did not register Status")

local loader
for _, frame in ipairs(frames) do if frame.events["PLAYER_ENTERING_WORLD"] then loader = frame end end
assert(loader, "addon reported on PLAYER_ENTERING_WORLD")
loader.scripts.OnEvent()
assert(sentToServer.name == "Report" and sentToServer.args[1] == "33", "addon reports its TOC patch")

addonHandlers.Status(nil, "0.0.0", 16, "33", "32", true, true, "files out of date (patch 32, current 33)")
assert(chat[1] == "|cfff0c96aTorment|r: files out of date (patch 32, current 33)", "one chat warning")
local frame = assert(_G.TormentVersionNotice, "the notice frame is created named")
assert(frame.shown and frame.text.text:find("patch 32"), "notice frame shown with the message")

addonHandlers.Status(nil, "0.0.0", 16, "33", "32", true, true, "again")
assert(#chat == 1, "warning not repeated in-session")

addonHandlers.Status(nil, "0.0.0", 16, "33", "33", true, false, nil)
assert(#chat == 1, "matching status shows nothing")

-- ------------------------------------------- diablocraft-gy3j: report timing and logging
-- (a) The cause. Torment.toc depends on AIO_Client, so AIO_Client is loaded first and the addon's
-- `IsAddOnLoaded("AIO_Client")` is true at load: the one Report goes out during the loading screen
-- and the PLAYER_ENTERING_WORLD send never runs. This proves WHEN the Report is sent; that a send
-- that early is lost in transit is the field report, not something an offline mock can show.
local tocFile = assert(realio.open("client-patch/addons/Torment/Torment.toc"))
local tocText = tocFile:read("*a")
tocFile:close()
local loadsAIOFirst = tocText:match("## Dependencies:%s*([^\n]*)"):find("AIO_Client", 1, true) ~= nil
assert(loadsAIOFirst, "Torment.toc must keep depending on AIO_Client (this test models that load order)")

local function loadAddonAs(aioLoaded)
    local sends, lateFrames = {}, {}
    AIO = {
        AddHandlers = function(_, t) return t end,
        Handle = function(channel, name, ...) sends[#sends + 1] = {channel = channel, name = name, args = {...}} end,
    }
    IsAddOnLoaded = function(name) return aioLoaded and name == "AIO_Client" end
    local created = CreateFrame
    CreateFrame = function(...) local f = created(...); lateFrames[#lateFrames + 1] = f; return f end
    dofile("client-patch/addons/Torment/Version.lua")
    CreateFrame = created
    return sends, lateFrames
end
local sends, loadFrames = loadAddonAs(loadsAIOFirst)
assert(#sends == 1 and sends[1].name == "Report", "with AIO_Client loaded first the Report is sent once, at addon load")
for _, f in ipairs(loadFrames) do
    if f.events["PLAYER_ENTERING_WORLD"] then f.scripts.OnEvent() end
end
assert(#sends == 1, "PLAYER_ENTERING_WORLD sends nothing more: the load-time send already used the one slot")
local sends2, frames2 = loadAddonAs(false)
assert(#sends2 == 0, "control: without AIO_Client at load nothing is sent at load")
for _, f in ipairs(frames2) do if f.events["PLAYER_ENTERING_WORLD"] then f.scripts.OnEvent() end end
assert(#sends2 == 1, "control: it is the PLAYER_ENTERING_WORLD send that would otherwise carry the Report")

-- (b) The fix: dc_version.lua also runs on the client (AIO ships it after its handshake) and sends a Report.
local function runOnClient(patch)
    local out = {}
    local handlerCalls = 0
    AIO = {
        AddAddon = function() return false end,
        AddHandlers = function() handlerCalls = handlerCalls + 1; return {} end,
        Handle = function(channel, name, ...) out[#out + 1] = {channel = channel, name = name, args = {...}} end,
    }
    GetAddOnMetadata = function(addon, field)
        if addon == "Torment" and field == "X-Torment-Client-Patch" then return patch end
    end
    dofile("mod-diablocraft/lua/aio/dc_version.lua")
    return out, handlerCalls
end
local clientOut, handlerCalls = runOnClient(" 46 ")
assert(#clientOut == 1 and clientOut[1].channel == "DiablocraftVersion" and clientOut[1].name == "Report"
    and clientOut[1].args[1] == "46", "client branch sends one Report carrying the TOC patch, trimmed")
assert(handlerCalls == 0, "client branch registers no handler (the addon owns Status; a second AddHandlers asserts)")
assert(#runOnClient(nil) == 0, "no Torment addon: nothing sent, the server's grace timer covers it")

-- (c) One log line per Report, at a level that shows (PrintError; print() is dropped at Logger.ALE=4),
-- with the player, the reported patch and the seconds since login.
local clock = 1000
os.time = function() return clock end
local logs = {}
PrintError = function(line) logs[#logs + 1] = line end
local logged = {broadcast = nil}
function logged:GetGUIDLow() return 7 end
function logged:GetGUID() return "G7" end
function logged:GetName() return "the designer" end
function logged:SendBroadcastMessage(t) self.broadcast = t end
online["G7"] = logged
AIO = serverAIO
logoutHandler(4, logged)
loginHandler(3, logged)
clock = 1013
sent = {}
handlers.Report(logged, "33")
assert(#logs == 1, "one log line per Report")
assert(logs[1]:find("the designer", 1, true) and logs[1]:find("patch=33", 1, true) and logs[1]:find("after_login=13s", 1, true)
    and logs[1]:find("mismatch=false", 1, true), logs[1])
handlers.Report(logged, "")
assert(#logs == 2 and logs[2]:find("patch=none", 1, true) and logs[2]:find("mismatch=true", 1, true), logs[2])

-- (d) The addon's own Report plus the client branch's: the duplicate is harmless.
sent = {}
handlers.Report(logged, "33")
handlers.Report(logged, "33")
assert(#sent == 2 and sent[1].args[6] == false and sent[2].args[6] == false and sent[2].args[7] == nil,
    "a duplicate matching Report answers twice with no mismatch and no message")
sent = {}
handlers.Report(logged, "32")
handlers.Report(logged, "32")
assert(sent[1].args[7] ~= nil and sent[2].args[7] ~= nil, "a mismatch answers with the message each time; the addon shows it once")

-- (e) A Report that lands late but before the grace window ends keeps the chat warning away.
logoutHandler(4, logged)
loginHandler(3, logged)
local lateGrace = timers[#timers]
handlers.Report(logged, "33") -- e.g. AIO's init took a while
logged.broadcast = nil
lateGrace()
assert(logged.broadcast == nil, "a late Report within the window silences the grace timer")

-- ---------------------------------- diablocraft-gy3j.1: warn only below the newest PUBLISHED patch
-- Current = max(VERSION client_patch (33 here), the manifest's client_patch). A fresh server instance
-- (a second dofile) starts with an empty manifest cache and an empty "already logged" flag.
local function freshServer()
    AIO = serverAIO
    dofile("mod-diablocraft/lua/aio/dc_version.lua")
end
local function reportAt(patch, at)
    clock = at
    sent = {}
    handlers.Report(logged, patch)
    return sent[1]
end
local function manifestLogs()
    local n = 0
    for _, line in ipairs(logs) do if line:find("published manifest", 1, true) then n = n + 1 end end
    return n
end
local T0 = 4000000000 -- later than any real os.time(), so no earlier cache entry can answer

-- (f1) A client above the published patch is never warned; below it is; at it is not.
manifestText = '{"client_patch": 48}'
freshServer()
local st = reportAt("49", T0)
assert(st.args[6] == false and st.args[7] == nil, "higher than published: not warned")
st = reportAt("48", T0)
assert(st.args[6] == false, "equal to published: not warned")
st = reportAt("47", T0)
assert(st.args[6] == true and st.args[7] == "files out of date (patch 47, current 48)",
    "lower than published: warned, and `current` is the published patch")
assert(st.args[3] == "48", "Status carries the current patch (the published one)")

-- (f2) VERSION ahead of the manifest: the larger of the two counts.
manifestText = '{"client_patch": 30}'
freshServer()
assert(reportAt("32", T0).args[6] == true, "below VERSION (33) although above the published 30: warned")
st = reportAt("33", T0)
assert(st.args[6] == false and st.args[3] == "33", "at VERSION: not warned, current is VERSION")

-- (f3) No manifest file: nobody with a patch is warned, one log line for the outage, not one per login.
manifestText = nil
freshServer()
logs = {}
assert(reportAt("20", T0).args[6] == false, "manifest missing: a client far below VERSION is not warned")
assert(reportAt("20", T0 + 100).args[6] == false and reportAt("20", T0 + 200).args[6] == false, "still nobody")
assert(manifestLogs() == 1 and logs[1]:find("unreadable", 1, true), "one log line for the whole outage: " .. #logs)
assert(reportAt("", T0 + 300).args[6] == true, "a Report with no patch still reads as missing")
manifestText = '{"client_patch": 48}'
assert(reportAt("47", T0 + 400).args[6] == true, "the file is back: warnings resume")
manifestText = nil
assert(reportAt("47", T0 + 500).args[6] == false and manifestLogs() == 2, "a second outage is logged again, once")

-- (f4) A truncated or empty file is the same: nobody warned, one line.
for _, bad in ipairs({'{"files": [], "client_pa', "", '{"client_patch": "x"}'}) do
    manifestText = bad
    freshServer()
    logs = {}
    assert(reportAt("20", T0).args[6] == false, "bad manifest " .. bad .. ": nobody warned")
    reportAt("20", T0 + 100); reportAt("20", T0 + 200)
    assert(manifestLogs() == 1, "bad manifest " .. bad .. ": one log line, got " .. manifestLogs())
end
manifestText = ""
freshServer(); logs = {}
reportAt("20", T0)
assert(logs[1] and logs[1]:find("empty", 1, true), "an empty file says empty")

-- (f5) A publish in mid-session is picked up at the next login with no restart, once the 60 s cache expires.
manifestText = '{"client_patch": 33}'
freshServer()
manifestReads = 0
assert(reportAt("34", T0).args[6] == false, "34 is above the published 33")
manifestText = '{"client_patch": 35}' -- the launcher publishes patch 35
assert(reportAt("34", T0 + 10).args[6] == false, "within the cache the old value still answers")
assert(manifestReads == 1, "the manifest is read once inside the 60 s cache, not per login")
st = reportAt("34", T0 + 61)
assert(st.args[6] == true and st.args[7] == "files out of date (patch 34, current 35)",
    "after the cache expires the new publish is used without a restart")
assert(manifestReads == 2, "one re-read after expiry")

-- (f6) The manifest path is the config value when set.
manifestPath = "/custom/manifest.json"
config["Diablocraft.PublishedManifest"] = manifestPath
manifestText = '{"client_patch": 50}'
freshServer()
assert(reportAt("49", T0).args[6] == true, "Diablocraft.PublishedManifest names the file read")
config["Diablocraft.PublishedManifest"] = nil
manifestPath = "/srv/torment-dl/stable/manifest.json"

-- (f7) The real manifest shape (a trimmed copy of /srv/torment-dl/stable/manifest.json): numbers come
-- BEFORE client_patch (schema 1) and after it (component sizes), so only the client_patch value counts.
manifestText = [[{
  "schema": 1,
  "channel": "stable",
  "client_patch": 47,
  "released": "2026-10-01T10:36:12Z",
  "min_launcher": "0.1.3",
  "realmlist": "set realmlist logon.example.com",
  "features": {"shop": false},
  "services": {"account_api": null, "report_url": "https://dl.example.com/report"},
  "components": [
    {"id": "patch-4", "kind": "file", "name": "patch-4.MPQ", "size": 21127427, "target": "Data/patch-4.MPQ"},
    {"id": "Torment", "kind": "zip", "name": "Torment", "size": 2784888, "folders": {"Torment": "Interface/AddOns/Torment"}}
  ]
}]]
freshServer()
st = reportAt("46", T0)
assert(st.args[6] == true and st.args[7] == "files out of date (patch 46, current 47)" and st.args[3] == "47",
    "the real manifest shape: current is client_patch (47), not the first number in the file (schema 1)")
assert(reportAt("47", T0).args[6] == false and reportAt("48", T0).args[6] == false, "47 and 48 are not warned")

print("test_version_notice: server and addon handshake checks passed")
