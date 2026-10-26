-- luacheck: globals AIO GetConfigValue RegisterPlayerEvent CreateLuaEvent GetPlayerByGUID PrintError GetAddOnMetadata
-- luacheck: globals DCThrottle
-- Diablocraft - non-blocking client-patch diagnosis, server half.
--
-- AIO bridge `DiablocraftVersion`. The Torment addon sends one `Report` with
-- `client_patch` (a decimal string) at addon initialization; the server answers
-- one `Status(module, schema, server_client_patch, client_patch, addon,
-- mismatch, message)`. A missing or older patch only informs: nothing here was
-- ever able to block a login, and it must stay that way.
--
-- Which patch counts as current: a Report is warned
-- only when it is BELOW the newer of the VERSION client_patch and the newest client patch the
-- launcher manifest has PUBLISHED (`Diablocraft.PublishedManifest`, default
-- /srv/torment-dl/stable/manifest.json). A higher client is never warned, so a player on a patch
-- the server has not caught up with sees nothing. If the manifest cannot be read or parsed, nobody
-- with a patch is warned and one line says so; a missing Report is still the 20 s grace timer's.
--
-- Contract: docs/contracts/version-enforcement.md. The editable wording is the
-- module config row `Diablocraft.ClientMismatchMessage` (placeholders
-- `{client}` and `{current}`), not dc_tunables. Server-side version numbers come
-- from the same VERSION file dc_version.cpp reads, through the same config path.
local AIO = AIO or require("AIO")
local CHANNEL = "DiablocraftVersion"
local DEFAULT_MESSAGE = "Your game files are out of date (patch {client}, current {current}). "
    .. "Run the launcher again, or download the current files from Discord or the website."
-- How long after login a client without the addon is given to Report before the
-- chat-only warning fires (the addon-less player has no notice frame to reach).
local GRACE_MS = 20000
-- Security G10: the client's patch is a small decimal string. The server echoes
-- it back in Status, so bound what it will accept and echo; anything longer is
-- treated as no report rather than forwarded.
local MAX_REPORT_LEN = 16
local ADDON = "Torment"
local DEFAULT_MANIFEST = "/srv/torment-dl/stable/manifest.json"
-- The manifest is ~3 KB; re-read it at most this often so a login never waits on the disk.
local MANIFEST_CACHE_S = 60

-- One log line per Report. print() is ALE_LOG_INFO and is dropped at the
-- Logger.ALE level the servers run, so the line goes through PrintError, which shows.
local function logLine(line)
    if PrintError then pcall(PrintError, line) end
end

local function logReport(player, supplied, serverPatch, sinceLogin, mismatch)
    local line = ("[version] Report %s (guid %d) patch=%s server=%s after_login=%s mismatch=%s")
        :format(player:GetName(), player:GetGUIDLow(), supplied ~= "" and supplied or "none",
            serverPatch or "unknown", sinceLogin and (sinceLogin .. "s") or "unknown", tostring(mismatch))
    logLine(line)
end

if AIO.AddAddon() then
    local function readVersion()
        local path = GetConfigValue and GetConfigValue("Diablocraft.VersionFile")
        if not path or path == "" then path = "../../../VERSION" end
        local file = io.open(path, "r")
        if not file then return nil end
        local values = {}
        for line in file:lines() do
            local key, value = line:match("^([%w_]+)=(.*)$")
            if key then values[key] = value end
        end
        file:close()
        return values
    end

    local values = readVersion() or {}
    local module = values.module or "0.0.0"
    local schema = tonumber(values.schema) or 0
    local serverPatch = values.client_patch and tostring(tonumber(values.client_patch)) or nil

    -- The newest published client patch as a number, or nil with the reason. Cached; a failure is
    -- cached too and logged once per outage (the flag clears when the file reads again).
    local manifest = {at = nil, value = nil, failing = false}
    local function publishedPatch()
        local now = os.time()
        if manifest.at and now - manifest.at < MANIFEST_CACHE_S then return manifest.value end
        manifest.at = now
        local path = GetConfigValue and GetConfigValue("Diablocraft.PublishedManifest")
        if not path or path == "" then path = DEFAULT_MANIFEST end
        local file = io.open(path, "r")
        local text = file and file:read("*a")
        if file then file:close() end
        local value = text and tonumber(text:match('"client_patch"%s*:%s*(%d+)'))
        manifest.value = value
        if value then
            manifest.failing = false
        elseif not manifest.failing then
            manifest.failing = true
            logLine(("[version] published manifest %s is %s: warning nobody with a patch until it reads again")
                :format(path, not file and "unreadable" or (not text or text == "") and "empty" or "unparsable"))
        end
        return value
    end

    local function message(clientPatch, current)
        local template = GetConfigValue and GetConfigValue("Diablocraft.ClientMismatchMessage")
        if not template or template == "" then template = DEFAULT_MESSAGE end
        local client = (clientPatch == nil or clientPatch == "") and "missing" or clientPatch
        current = current or serverPatch or "unknown"
        local text = template:gsub("{client}", client)
        return (text:gsub("{current}", current))
    end

    -- One warning per session. reported[guid] says the addon handshook, so the
    -- missing-addon timer can stay silent for a player who did.
    local warned, reported = {}, {}
    -- The grace callback must never touch a Player userdata captured at login:
    -- after logout or relog it is invalidated (GitHub #83). It captures the
    -- login's session token instead and re-resolves the player by GUID; a relog
    -- bumps the token, so a stale callback for the previous session ends quietly.
    local sessions, sessionCounter = {}, 0
    local loggedInAt = {}

    local function status(player, clientPatch, addon, mismatch, current)
        AIO.Handle(player, CHANNEL, "Status", module, schema, current,
            clientPatch, addon, mismatch, mismatch and message(clientPatch, current) or nil)
    end

    local handlers = AIO.AddHandlers(CHANNEL, {})
    function handlers.Report(player, clientPatch)
        -- Security G1: every Report writes a server log line; drop a flood. The
        -- addon sends one per login.
        if not DCThrottle.Allow(player, "version:report", 5, 10) then return end
        local guid = player:GetGUIDLow()
        local supplied = type(clientPatch) == "string" and clientPatch:gsub("%s", "") or ""
        if #supplied > MAX_REPORT_LEN then supplied = "" end
        reported[guid] = true
        local addon = supplied ~= ""
        -- Current is the newer of VERSION and the published patch; only a lower Report warns.
        local published = publishedPatch()
        local current = published and math.max(published, tonumber(serverPatch) or 0) or serverPatch
        local number = tonumber(supplied)
        local mismatch
        if not addon or not number then
            mismatch = true  -- nothing readable to compare
        elseif not published then
            mismatch = false -- manifest unreadable: warn nobody who gave a patch (logged once)
        else
            mismatch = number < tonumber(current)
        end
        current = current and tostring(current) or nil
        local reportedPatch = supplied ~= "" and supplied or nil
        -- A logging fault must never stop the Status reply.
        pcall(logReport, player, supplied, current, loggedInAt[guid] and (os.time() - loggedInAt[guid]), mismatch)
        status(player, reportedPatch, addon, mismatch, current)
    end

    RegisterPlayerEvent(3, function(_, player) -- login
        local guid = player:GetGUIDLow()
        loggedInAt[guid] = os.time()
        if warned[guid] or reported[guid] then return end
        sessionCounter = sessionCounter + 1
        local session = sessionCounter
        sessions[guid] = session
        local objectGuid = player:GetGUID()
        CreateLuaEvent(function()
            local current = GetPlayerByGUID(objectGuid)
            if not current or sessions[guid] ~= session then return end
            if warned[guid] or reported[guid] then return end
            warned[guid] = true
            current:SendBroadcastMessage("Torment: " .. message(nil))
        end, GRACE_MS, 1)
    end)
    RegisterPlayerEvent(4, function(_, player) -- logout
        local guid = player:GetGUIDLow()
        warned[guid], reported[guid], sessions[guid], loggedInAt[guid] = nil, nil, nil, nil
    end)
else
    -- Client side. AIO sends this file to the client and runs it after its own handshake, so a
    -- Report sent here is never lost the way the addon's load-time one can be.
    -- The addon's own Report stays; a second one is harmless (a match shows nothing, a mismatch
    -- still warns once per session). Without the Torment addon there is no Status handler to
    -- answer, so say nothing and let the server's grace timer speak.
    local patch = GetAddOnMetadata and GetAddOnMetadata(ADDON, "X-Torment-Client-Patch")
    if patch then AIO.Handle(CHANNEL, "Report", (patch:gsub("%s", ""))) end
end
