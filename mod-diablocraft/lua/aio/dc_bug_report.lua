-- luacheck: globals AIO CharDBQuery WorldDBQuery AuthDBQuery DCThrottle DCAccount GetAreaName GetRealmID GetConfigValue
--[[
World of DiabloCraft - in-game bug reports, server half.

The addon half is client-patch/addons/Torment/BugReport.lua; this file is
server-only (it never calls AIO.AddAddon, so AIO never ships it to the client).
Contract: docs/contracts/bug-report-messages.md.

Two classes of untrusted input exist here and only two: the title and the details
the client sends, plus its addon version and client patch. Everything written to
dc_bug_report comes from the server's own state (the snapshot taken at Open); the
client's context fields are never read. The title is trimmed, counted in
characters and refused unless 1..50; the details are trimmed, counted and refused
over 2000, but may be empty. The 5-per-account rolling-hour limit is counted from
the table itself, never from memory, so a restart does not reset it.

CharDBQuery is synchronous (ALE Global:CharDBQuery -> CharacterDatabase.Query),
so the INSERT lands before the next statement runs and the row id can be read
back; CharDBExecute is asynchronous and is not used. The world thread is the only
writer of dc_bug_report (the poster only UPDATEs issue_number), so MAX(id) right
after the INSERT is this row's id.
]]

local AIO = AIO or require("AIO")
local CHANNEL = "DiablocraftBugReport"

-- The limit is per account and per rolling hour.
local MAX_TITLE = 50
local MAX_DETAILS = 2000
local LIMIT_PER_HOUR = 5
-- The client-reported strings are display values, never decision inputs.
local MAX_VERSION = 32
local MAX_PATCH = 16

local handlers = AIO.AddHandlers(CHANNEL, {})

-- A single-quoted MySQL literal from an untrusted string. A NUL would end the C
-- string ALE hands the driver; a backslash or quote would close the literal.
-- %c drops every control byte but the whitespace a text box legitimately holds,
-- and unlike "\0" in a pattern it means the same thing in Lua 5.1 and 5.2.
local function literal(value)
    local text = tostring(value or ""):gsub("%c", function(character)
        if character == "\n" or character == "\t" or character == "\r" then return character end
        return ""
    end)
    text = text:gsub("\\", "\\\\"):gsub("'", "\\'")
    return "'" .. text .. "'"
end

-- Linear-time trim. gsub("%s+$", "") is quadratic on a long whitespace run
-- followed by a non-space, and Send runs this on the raw client string before
-- the length check, so a modified client could burn the world thread (review
-- finding 1: 40,000 bytes cost ~14 s of CPU). The first non-space is found
-- once, then the end is walked back one byte at a time.
local function trimmed(text)
    local first = text:find("%S")
    if not first then return "" end
    local last = #text
    while last > first and text:find("^%s", last) do last = last - 1 end
    return text:sub(first, last)
end

-- Characters, not bytes: the limit counts characters ("1 to 50 characters",
-- "at most 2,000"), and the addon counts with strlenutf8, so the two agree. A
-- UTF-8 code point starts at any byte that is not a continuation byte
-- (10xxxxxx). Linear over the string, no allocation.
local function length(text)
    local count = 0
    for index = 1, #text do
        local byte = text:byte(index)
        if byte < 0x80 or byte >= 0xC0 then count = count + 1 end
    end
    return count
end

-- A DBC area name by id, empty when the id is unknown (GetAreaName errors on an
-- id with no AreaTable row, so it is guarded).
local function areaName(id)
    if not id or id == 0 or not GetAreaName then return "" end
    local ok, name = pcall(GetAreaName, id)
    return ok and name or ""
end

-- The D3 class name the character sheet shows, not the WoW class the map also
-- carries: every Torment screen names the class the D3 way, and the window shows
-- this value, so the row files what the player saw.
local function className(player)
    local row = WorldDBQuery("SELECT d3_class FROM dc_class_map WHERE wow_class_id = " .. (player:GetClass() or 0))
    return row and row:GetString(0) or ""
end

-- The account's Paragon level for its mode, the number the sheet shows beside
-- the character level. A read: DC::Paragon owns the pool.
local function paragonLevel(player)
    local account, mode = DCAccount.Principal(player)
    if not account then return 0 end
    local row = CharDBQuery(("SELECT level FROM dc_account_paragon WHERE account_id=%d AND pool='%s'")
        :format(account, mode))
    return row and row:GetUInt32(0) or 0
end

local function realmName()
    local row = AuthDBQuery(("SELECT name FROM realmlist WHERE id=%d"):format(GetRealmID and GetRealmID() or 0))
    return row and row:GetString(0) or ""
end

-- dc_character_tier.tier is the Torment level; 1 is the game's default when the
-- character has no row yet (the same default dc_tier.lua reads).
local function difficulty(player)
    local row = CharDBQuery("SELECT tier FROM dc_character_tier WHERE guid=" .. player:GetGUIDLow())
    return row and row:GetUInt32(0) or 1
end

-- The tier's display name (dc_tier_phase joins the id to dc_difficulty_tiers),
-- what the right column shows ("Torment VI"). The id is the fallback when the
-- world row is missing.
local function difficultyName(tier)
    local row = WorldDBQuery("SELECT tier_name FROM dc_tier_phase WHERE tier_id=" .. tier)
    return row and row:GetString(0) or tostring(tier)
end

-- The live run the player is enrolled in, if any, read exactly as the rift
-- tracker reads it (dc_riftbar.lua RUN_QUERY): newest first, only while open.
local RIFT_QUERY = "SELECT r.id, r.tier FROM dc_rift_member m JOIN dc_rift r ON r.id=m.run_id "
    .. "WHERE m.player_guid=%d AND m.state IN ('enrolled','offline') AND r.state<>'closed' "
    .. "ORDER BY m.run_id DESC LIMIT 1"

local function rift(player)
    local row = CharDBQuery(RIFT_QUERY:format(player:GetGUIDLow()))
    if not row then return nil, nil end
    return row:GetUInt32(0), row:GetUInt32(1)
end

local function target(player)
    local unit = player:GetSelection()
    if not unit then return "", 0 end
    return unit:GetName() or "", unit:GetEntry() or 0
end

-- The worn item entry ids, slot 0..18 (dc_inventory EQUIP_FIRST..EQUIP_LAST).
local function equipped(player)
    local ids = {}
    for slot = 0, 18 do
        local item = player:GetItemByPos(255, slot)
        if item then ids[#ids + 1] = item:GetEntry() or 0 end
    end
    return table.concat(ids, ",")
end

-- The deployed commit. The release folder's MANIFEST (make_release.sh) starts
-- with "release: <tag>" and "cut: <sha> (<subject>)", beside the schema.csv the
-- server reads through Diablocraft.SchemaFile, so the folder of that path holds
-- it. A dev tree has no MANIFEST and falls back to the VERSION identity the
-- version check reads: module/schema/client_patch.
local function buildIdentity()
    local schemaPath = GetConfigValue and GetConfigValue("Diablocraft.SchemaFile")
    local directory = schemaPath and schemaPath:match("^(.*)[/\\][^/\\]*$")
    if directory then
        local manifest = io.open(directory .. "/MANIFEST", "r")
        if manifest then
            for line in manifest:lines() do
                local sha = line:match("^cut: (%x+)")
                if sha then manifest:close() return sha end
            end
            manifest:close()
        end
    end

    local path = GetConfigValue and GetConfigValue("Diablocraft.VersionFile")
    if not path or path == "" then path = "../../../VERSION" end
    local values = {}
    local file = io.open(path, "r")
    if file then
        for line in file:lines() do
            local key, value = line:match("^([%w_]+)=(.*)$")
            if key then values[key] = value end
        end
        file:close()
    end
    return ("%s/%s/%s"):format(values.module or "0.0.0", values.schema or "0", values.client_patch or "0")
end

-- Everything the server knows about the player's situation, plus the moment the
-- window opened. Taken at Open and filed by Send (docs/contracts/bug-report-messages.md).
local function snapshot(player)
    local riftId, riftLevel = rift(player)
    local targetName, targetEntry = target(player)
    local tier = difficulty(player)
    return {
        account = player:GetAccountId() or 0,
        guid = player:GetGUIDLow(),
        name = player:GetName() or "",
        class = className(player),
        level = player:GetLevel() or 0,
        paragon = paragonLevel(player),
        realm = realmName(),
        map_id = player:GetMapId() or 0,
        zone = areaName(player:GetZoneId()),
        subzone = areaName(player:GetAreaId()),
        x = player:GetX() or 0,
        y = player:GetY() or 0,
        z = player:GetZ() or 0,
        tier = tier,
        difficulty = difficultyName(tier),
        rift_id = riftId,
        rift_level = riftLevel,
        target_name = targetName,
        target_entry = targetEntry,
        equipped = equipped(player),
        build = buildIdentity(),
        opened_at = os.time(),
    }
end

-- The display half of a snapshot, for the window's right column. The Client row
-- is not here: it is the client's own patch and addon version, drawn by the addon.
local function context(state)
    return {
        name = state.name, class = state.class, level = state.level, paragon = state.paragon,
        realm = state.realm, map_id = state.map_id, zone = state.zone, subzone = state.subzone,
        x = state.x, y = state.y, z = state.z, difficulty = state.difficulty,
        rift_id = state.rift_id, rift_level = state.rift_level, target = state.target_name,
        build = state.build, account = state.account, opened_at = state.opened_at,
    }
end

-- The snapshots, one per character guid. Replaced by the next Open and cleared by
-- a stored report, so it holds where the player was when they opened the window.
local snapshots = {}

-- This account's highest row id, 0 when it has none.
local function maxId(account)
    local row = CharDBQuery(("SELECT MAX(`id`) FROM `dc_bug_report` WHERE `account`=%d"):format(account))
    return row and row:GetUInt32(0) or 0
end

local function insert(state, title, details, addonVersion, clientPatch)
    local account = state.account
    local query = ([[INSERT INTO `dc_bug_report`
        (`account`,`guid`,`name`,`class`,`level`,`paragon`,`realm`,`map_id`,`zone`,`subzone`,
         `pos_x`,`pos_y`,`pos_z`,`difficulty`,`rift_id`,`rift_level`,`target_name`,`target_entry`,
         `equipped`,`build`,`addon_version`,`client_patch`,`title`,`body`,`opened_at`)
        VALUES (%d,%d,%s,%s,%d,%d,%s,%d,%s,%s,%.3f,%.3f,%.3f,%d,%s,%s,%s,%d,%s,%s,%s,%s,%s,%s,FROM_UNIXTIME(%d))]])
        :format(account, state.guid,
            literal(state.name), literal(state.class),
            state.level, state.paragon,
            literal(state.realm), state.map_id,
            literal(state.zone), literal(state.subzone),
            state.x, state.y, state.z,
            state.tier, state.rift_id or "NULL", state.rift_level or "NULL",
            literal(state.target_name), state.target_entry,
            literal(state.equipped), literal(state.build),
            literal(addonVersion), literal(clientPatch), literal(title), literal(details),
            state.opened_at)
    -- ALE answers nil for an INSERT whether it worked or not, so success is a
    -- newer row for this account, not a non-nil reply: without this, a refused
    -- row (bad utf8mb4 text, any DB error) was reported as Sent with the
    -- previous row's id (review finding 4).
    local before = maxId(account)
    CharDBQuery(query)
    local after = maxId(account)
    if after <= before then return nil end
    return after
end

-- A client-reported string, trimmed and cut; anything that is not a string is empty.
local function reported(value, limit)
    if type(value) ~= "string" then return "" end
    return (value:gsub("%s", "")):sub(1, limit)
end

-- The window opened: take the context snapshot and hand it to the window.
function handlers.Open(player)
    if not player then return end
    -- Security G1: this handler queries the database; drop a flood.
    if not DCThrottle.Allow(player, "bugreport:open", 1, 5) then return end
    local state = snapshot(player)
    snapshots[player:GetGUIDLow()] = state
    AIO.Handle(player, CHANNEL, "Context", context(state))
end

-- The untrusted entry point. The client sends the title, the details and its
-- two version strings, and nothing else.
function handlers.Send(player, title, details, addonVersion, clientPatch)
    if not player then return end
    -- Security G1: this handler queries the database; drop a flood.
    if not DCThrottle.Allow(player, "bugreport:send", 1, LIMIT_PER_HOUR) then return end
    if type(title) ~= "string" or type(details) ~= "string" then return end
    title = trimmed(title)
    local titleLength = length(title)
    if titleLength < 1 or titleLength > MAX_TITLE then
        AIO.Handle(player, CHANNEL, "Refused", "title")
        return
    end
    details = trimmed(details)
    if length(details) > MAX_DETAILS then
        AIO.Handle(player, CHANNEL, "Refused", "details")
        return
    end
    addonVersion = reported(addonVersion, MAX_VERSION)
    clientPatch = reported(clientPatch, MAX_PATCH)

    local account = player:GetAccountId() or 0
    local row = CharDBQuery(("SELECT COUNT(*) FROM `dc_bug_report` WHERE `account`=%d AND `created_at` >= NOW() - INTERVAL 1 HOUR")
        :format(account))
    if row and row:GetUInt32(0) >= LIMIT_PER_HOUR then
        player:SendBroadcastMessage(("You've sent %d reports this hour; please try again later."):format(LIMIT_PER_HOUR))
        AIO.Handle(player, CHANNEL, "Refused", "limit")
        return
    end

    local guid = player:GetGUIDLow()
    local state = snapshots[guid]
    if not state then state = snapshot(player) end

    local id = insert(state, title, details, addonVersion, clientPatch)
    if not id then
        AIO.Handle(player, CHANNEL, "Refused", "error")
        return
    end
    -- A stored report clears the snapshot; a refused insert keeps it so the retry
    -- files the open-time place and time, not a fresh one.
    snapshots[guid] = nil
    player:SendBroadcastMessage(("Bug report #%d received, thanks."):format(id))
    AIO.Handle(player, CHANNEL, "Sent", id)
end
