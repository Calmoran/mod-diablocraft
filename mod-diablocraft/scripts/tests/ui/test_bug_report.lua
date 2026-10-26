-- Run from repo root with `lua mod-diablocraft/scripts/tests/ui/test_bug_report.lua`
-- (or lua5.2). The server half of dc_bug_report.lua against stubbed DB access.
--
-- Contract: docs/contracts/bug-report-messages.md. Proves: Open takes a snapshot
-- of the server's own state and sends it as Context; Send files the snapshot taken
-- at open (not what the client sends), or a fresh one when there is none; a refused
-- insert keeps it so the retry files the open-time row; a new open replaces the
-- snapshot and a stored report clears it; the title
-- is trimmed and refused unless 1..50 characters (characters, not bytes); the
-- details may be empty and are refused over 2,000 characters; the text is trimmed
-- in linear time; the 5-per-account rolling-hour limit is read from the table's own
-- rows; a failed INSERT is Refused(error), not reported as success; the build is the
-- release MANIFEST's commit with the VERSION identity as fallback; the
-- confirmation and limit lines are the server's.
local sent, queries = {}, {}
-- The stub table: `rows` are the dc_bug_report rows the handler's own SQL sees
-- ({id, account, age seconds}); `insertWorks` models a MySQL/utf8mb4 refusal.
local rows, insertWorks = {}, true
local riftRow, versionFile, schemaFile = nil, "VERSION", nil
-- The world rows the context reads: the D3 class name and the tier's display name.
local d3Class, tierName = "Wizard", "Torment VI"
-- A controllable clock, so the open time and a later send time are distinct.
local clock, realTime = 1000000, os.time
os.time = function() return clock end

-- A cursor over one flat row, the ALEQuery contract (0-based columns).
local function row(values)
    if not values then return nil end
    local function get(_, index) return values[index + 1] end
    return {GetString = get, GetUInt32 = get, GetInt32 = get, GetDouble = get,
        NextRow = function() return false end}
end

local inserted
-- The account a query names: `account`=N in a COUNT/MAX, the first VALUES
-- column in an INSERT.
local function accountOf(sql)
    return tonumber(sql:match("`account`=(%d+)")) or tonumber(sql:match("VALUES %((%d+)"))
end

local function maxId(account)
    local max = 0
    for _, r in ipairs(rows) do
        if r.account == account and r.id > max then max = r.id end
    end
    return max
end

local function nextRowId()
    local max = 0
    for _, r in ipairs(rows) do if r.id > max then max = r.id end end
    return max + 1
end

function CharDBQuery(sql)
    queries[#queries + 1] = sql
    if sql:find("COUNT(*)", 1, true) then
        -- Counted the way the handler's SQL says: by its account, over rows
        -- younger than its INTERVAL, so ageing a row out changes the answer.
        local account, hours = accountOf(sql), tonumber(sql:match("INTERVAL (%d+) HOUR"))
        assert(account and hours, "the COUNT names its account and interval: " .. sql)
        local count = 0
        for _, r in ipairs(rows) do
            if r.account == account and r.age < hours * 3600 then count = count + 1 end
        end
        return row({count})
    end
    if sql:find("INSERT INTO", 1, true) then
        inserted = sql
        if insertWorks then rows[#rows + 1] = {id = nextRowId(), account = accountOf(sql), age = 0} end
        return nil
    end
    if sql:find("MAX(`id`)", 1, true) then return row({maxId(accountOf(sql))}) end
    if sql:find("dc_character_tier", 1, true) then return row({7}) end
    if sql:find("dc_account_paragon", 1, true) then return row({186}) end
    if sql:find("dc_character_mode", 1, true) then return row({"normal"}) end
    if sql:find("dc_rift_member", 1, true) then return riftRow and row(riftRow) or nil end
    error("unexpected character query: " .. sql)
end
function WorldDBQuery(sql)
    if sql:find("dc_tier_phase", 1, true) then return row({tierName}) end
    assert(sql:find("dc_class_map", 1, true), "unexpected world query: " .. sql)
    -- dc_class_map.d3_class is the name the character sheet shows ('Wizard'); the
    -- wow_class column ('Mage') is not what the window displays.
    assert(sql:find("d3_class", 1, true), "the context names the D3 class column: " .. sql)
    return row({d3Class})
end
function AuthDBQuery(sql)
    assert(sql:find("realmlist", 1, true), "unexpected auth query: " .. sql)
    return row({"Torment"})
end
function GetAreaName(id) return "Area" .. tostring(id) end
function GetRealmID() return 1 end
function GetConfigValue(key)
    if key == "Diablocraft.SchemaFile" then return schemaFile end
    return versionFile
end

DCAccount = {Principal = function(player) return player.account, "normal" end}
DCThrottle = {Allow = function() return true end}

local player = {guid = 1234, account = 77, name = "Reportguy", class = 1, level = 70,
    map = 1, zone = 10, area = 11, x = 1.5, y = 2.5, z = 3.5, target = nil,
    items = {1001, 1002}, messages = {}}
function player:GetGUIDLow() return self.guid end
function player:GetAccountId() return self.account end
function player:GetName() return self.name end
function player:GetClass() return self.class end
function player:GetLevel() return self.level end
function player:GetMapId() return self.map end
function player:GetZoneId() return self.zone end
function player:GetAreaId() return self.area end
function player:GetX() return self.x end
function player:GetY() return self.y end
function player:GetZ() return self.z end
function player:GetSelection() return self.target end
function player:GetItemByPos(_, slot)
    local entry = self.items[slot + 1]
    if not entry then return nil end
    return {GetEntry = function() return entry end}
end
function player:SendBroadcastMessage(text) self.messages[#self.messages + 1] = text end

local handlers
AIO = {
    AddHandlers = function(_, table_) handlers = table_ return table_ end,
    Handle = function(_, channel, name, ...)
        sent[#sent + 1] = {channel = channel, name = name, args = {...}}
    end,
}

dofile('mod-diablocraft/lua/aio/dc_bug_report.lua')
assert(handlers and handlers.Send and handlers.Open, "dc_bug_report.lua registers Open and Send")

local function reset()
    sent, queries, inserted = {}, {}, nil
    player.messages = {}
    rows, insertWorks = {}, true
end

local function open()
    reset()
    handlers.Open(player)
    return sent[1]
end

local function send(title, details, version, patch)
    reset()
    handlers.Send(player, title, details, version, patch)
    return inserted
end

local function sendWith(seed, title, details)
    reset()
    rows = seed
    handlers.Send(player, title, details)
    return inserted
end

-- 1. Open takes a snapshot of the server's own state and sends it as Context.
local context = open()
assert(context and context.name == "Context" and context.channel == "DiablocraftBugReport",
    "Open answers Context on the bug-report channel")
local state = context.args[1]
assert(type(state) == "table", "Context carries a table")
assert(state.name == "Reportguy" and state.class == "Wizard", "name and D3 class are the server's")
assert(state.level == 70 and state.paragon == 186, "level and paragon are the server's")
assert(state.realm == "Torment", "realm is read from realmlist")
assert(state.zone == "Area10" and state.subzone == "Area11", "zone and subzone come from GetAreaName")
assert(state.map_id == 1 and state.x == 1.5 and state.y == 2.5 and state.z == 3.5,
    "map and position are the player's")
assert(state.difficulty == "Torment VI", "difficulty is the tier's display name, got " .. tostring(state.difficulty))
assert(state.rift_id == nil and state.rift_level == nil, "not in a rift sends no rift fields")
assert(state.target == nil or state.target == "", "no selection sends no target")
assert(state.build and state.build ~= "", "the build identity is attached")
assert(state.account == 77, "the account is attached")
assert(state.opened_at == clock, "the context time is the moment Open was called")

-- 1b. A live rift and a selection are in the context.
riftRow = {500, 9}
player.target = {GetName = function() return "Gharbad" end, GetEntry = function() return 4242 end}
state = open().args[1]
assert(state.rift_id == 500 and state.rift_level == 9, "an enrolled run is in the context")
assert(state.target == "Gharbad", "the selection is in the context")
riftRow, player.target = nil, nil

-- 2. Send files the snapshot taken at open, not the state at send time, and not
--    what the client sends. The player moves; the filed row must stay at the open
--    place, and account/guid/name/class/gears are the server's.
riftRow = {500, 9}
player.target = {GetName = function() return "Gharbad" end, GetEntry = function() return 4242 end}
open()
player.zone, player.area, player.x = 20, 21, 99.5
riftRow, player.target = nil, nil
local sql = send("goblin ate my stash", "steps", "0.1", "66")
assert(sql, "the report is stored")
assert(sql:find("'Area10'", 1, true) and sql:find("'Area11'", 1, true),
    "the zone is the open snapshot's, not where the player sent from: " .. sql)
assert(sql:find("1.500,2.500,3.500", 1, true), "the position is the open snapshot's")
assert(sql:find(",500,9,", 1, true), "the rift is the open snapshot's")
assert(sql:find("'Gharbad'", 1, true) and sql:find(",4242,", 1, true), "the target is the open snapshot's")
assert(sql:find("77", 1, true) and sql:find("1234", 1, true), "account and guid are the server's")
assert(sql:find("'Reportguy'", 1, true) and sql:find("'Wizard'", 1, true), "name and D3 class are the server's")
assert(sql:find(",70,", 1, true) and sql:find(",186,", 1, true), "level and paragon are the server's")
assert(sql:find("'1001,1002'", 1, true), "equipped is the worn item entries")
assert(sql:find("'goblin ate my stash'", 1, true) and sql:find("'steps'", 1, true),
    "the title and details are stored")
assert(sql:find("'0.1'", 1, true) and sql:find("'66'", 1, true), "the client-reported version and patch are stored")
assert(sql:find("FROM_UNIXTIME(" .. clock .. ")", 1, true), "opened_at is the open snapshot's time: " .. sql)

-- 3. Only (title, details, addon_version, client_patch) are read: any extra
--    argument is ignored, and a non-string title or details is refused, never
--    queried.
reset()
handlers.Send(player, "hello", "world", "0.1", "66", {account = 999, name = "Fake", level = 1})
assert(inserted and inserted:find("VALUES (77,1234,", 1, true), "the server's own account and guid, not the extra argument")
assert(not inserted:find("Fake", 1, true) and not inserted:find("999", 1, true),
    "the extra argument's fake fields are never read")
reset()
handlers.Send(player, {1, 2}, "details")
assert(#queries == 0, "a non-string title makes no query")
reset()
handlers.Send(player, "title", {1, 2})
assert(#queries == 0, "a non-string details makes no query")

-- 3b. No snapshot (a /reload, a modified client): Send takes a fresh one at send
--     time, so opened_at is now and the current place is filed.
clock = clock + 300
player.zone = 30
sql = send("fresh spot", "")
assert(sql:find("'Area30'", 1, true), "without an open the snapshot is taken at send time: " .. sql)
assert(sql:find("FROM_UNIXTIME(" .. clock .. ")", 1, true), "opened_at is the send time when there was no open")

-- 3c. A refused insert keeps the snapshot: the retry files the open-time place
--     and time, not a fresh one taken at retry time.
player.zone = 45
open()
local openClock = clock
insertWorks = false
handlers.Send(player, "first try fails", "d")
assert(#sent >= 1 and sent[#sent].name == "Refused" and sent[#sent].args[1] == "error",
    "a refused insert reports the error")
clock = clock + 120
player.zone = 46
sql = send("retry after the error", "d")
assert(sql:find("'Area45'", 1, true), "the retry files the open-time place: " .. sql)
assert(sql:find("FROM_UNIXTIME(" .. openClock .. ")", 1, true),
    "and the open time, not the retry time")

-- 3d. A new Open replaces the snapshot.
open()
player.zone = 50
open()
player.zone = 60
sql = send("second open", "")
assert(sql:find("'Area50'", 1, true) and not sql:find("'Area60'", 1, true),
    "the second open's snapshot is the one filed: " .. sql)

-- 3e. A stored report clears the snapshot: a second Send without a new Open takes
--     a fresh one, not the one the first report used.
player.zone = 70
open()
player.zone = 80
assert(send("first", ""):find("'Area70'", 1, true), "the first report uses the snapshot")
player.zone = 90
sql = send("second, no open", "")
assert(sql:find("'Area90'", 1, true), "the snapshot was cleared by the stored report: " .. sql)

-- 4. Title: trimmed, 1..50 characters, required.
assert(send("", "details") == nil, "an empty title is refused")
assert(#sent == 1 and sent[1].name == "Refused" and sent[1].args[1] == "title", "an empty title is Refused(title)")
assert(send("   ", "details") == nil, "a whitespace-only title is refused")
assert(send(("x"):rep(51), "details") == nil, "a 51-character title is refused")
assert(send(("x"):rep(50), "details") ~= nil, "a 50-character title is accepted")
sql = send("  padded title  ", "details")
assert(sql:find("'padded title'", 1, true), "the title is trimmed before it is stored")
-- Characters, not bytes: 50 two-byte characters (100 bytes) are accepted, 51 are
-- not. A byte count would refuse the first (review-proof of the character rule).
assert(send(("\195\169"):rep(50), "details") ~= nil, "50 multi-byte characters are accepted")
assert(send(("\195\169"):rep(51), "details") == nil, "51 multi-byte characters are refused")

-- 5. Details: optional, up to 2,000 characters.
assert(send("a title", "") ~= nil, "an empty details box is accepted")
assert(send("a title", ("x"):rep(2000)) ~= nil, "2,000 characters are accepted")
assert(send("a title", ("x"):rep(2001)) == nil, "2,001 characters are refused")
assert(#sent == 1 and sent[1].name == "Refused" and sent[1].args[1] == "details",
    "too-long details are Refused(details)")
assert(send("a title", ("\195\169"):rep(2000)) ~= nil, "2,000 multi-byte characters are accepted")
assert(send("a title", ("\195\169"):rep(2001)) == nil, "2,001 multi-byte characters are refused")
local TEMPLATE = "What happened:\n\nWhat I expected to happen:\n\nHow to make it happen (steps):\n"
    .. "1.\n2.\n3.\n\nHow often: every time / sometimes / once"
sql = send("a title", TEMPLATE)
assert(sql and sql:find("'What happened:", 1, true) and sql:find("once'", 1, true),
    "the unchanged template is accepted as-is")

-- 6. The rolling-hour limit is counted from the table, before the insert: the
--    stub computes the COUNT from the handler's own SQL (its account and its
--    INTERVAL), so ageing a row past the hour changes the answer.
local five = {}
for index = 1, 5 do five[index] = {id = index, account = 77, age = 60} end
sql = sendWith(five, "one too many", "details")
assert(sql == nil, "the 6th report in the hour is refused")
assert(queries[1]:find("COUNT(*)", 1, true) and queries[1]:find("dc_bug_report", 1, true)
    and queries[1]:find("INTERVAL 1 HOUR", 1, true) and queries[1]:find("=77", 1, true),
    "the limit is a COUNT over dc_bug_report by account for the last hour: " .. queries[1])
assert(not queries[2] or not queries[2]:find("INSERT", 1, true), "a refused report is never inserted")
assert(player.messages[#player.messages] == "You've sent 5 reports this hour; please try again later.",
    "the limit line is the server's exact wording")
assert(#sent == 1 and sent[1].name == "Refused" and sent[1].args[1] == "limit"
    and sent[1].channel == "DiablocraftBugReport", "a refused report pushes Refused(limit)")

-- Under the limit: four rows in the hour is accepted.
local four = {}
for index = 1, 4 do four[index] = {id = index, account = 77, age = 60} end
assert(sendWith(four, "under the limit", "d") ~= nil, "the 5th report in the hour is accepted")

-- Another account's rows do not count against this one.
local foreign = {{id = 9, account = 999, age = 60}}
for index = 1, 5 do foreign[#foreign + 1] = {id = 10 + index, account = 77, age = 60} end
assert(sendWith(foreign, "not for me", "d") == nil, "another account's rows do not count")

-- A report is accepted once a row ages out of the hour.
local aging = {}
for index = 1, 5 do aging[index] = {id = index, account = 77, age = 60} end
aging[1].age = 3601
assert(sendWith(aging, "first after the hour", "d") ~= nil,
    "the first report after a row ages out of the hour is accepted")

-- 7. The reply names the new row: the chat line and Sent(id) both carry the id of
--    the row this account just gained.
sql = sendWith({{id = 4241, account = 999, age = 1}}, "accepted", "d")
assert(sql ~= nil, "accepted")
assert(player.messages[#player.messages] == "Bug report #4242 received, thanks.", "the confirmation names the id")
assert(#sent == 1 and sent[1].name == "Sent" and sent[1].args[1] == 4242, "Sent carries the row id")

-- 8. Escape what the client typed: a quote and a backslash cannot break the
--    literal, and a NUL is dropped. The title is the other free-form string.
sql = send([[oops ' or 1=1 -- and a backslash \ and NUL]], "d")
assert(sql:find([[oops \' or 1=1 -- and a backslash \\ and NUL]], 1, true),
    "quotes and backslashes are escaped: " .. sql)
sql = send("nul\0byte", "d")
assert(sql:find("'nulbyte'", 1, true) and not sql:find("\0", 1, true), "a NUL byte is dropped")
sql = send("line one\nline two", "d")
assert(sql:find("'line one\nline two'", 1, true), "a newline the player typed is kept")

-- 9. The client-reported strings are bounded: addon version 32 bytes, patch 16.
sql = send("version", "d", ("9"):rep(40), ("8"):rep(40))
assert(sql:find("'" .. ("9"):rep(32) .. "'", 1, true), "the addon version is cut to 32 bytes")
assert(sql:find("'" .. ("8"):rep(16) .. "'", 1, true), "the client patch is cut to 16 bytes")
sql = send("version", "d", {1, 2}, 5)
assert(sql:find("'',''", 1, true), "a non-string version or patch is stored empty")

-- 10. A failed INSERT is not reported as success. ALE answers nil for an INSERT
--     whether it worked or not, so a no-op INSERT must not hand the player the
--     previous row's id: no Sent, no confirmation line.
reset()
rows = {{id = 100, account = 77, age = 10}}
insertWorks = false
handlers.Send(player, "this insert fails", "d")
assert(#sent == 1 and sent[1].name == "Refused" and sent[1].args[1] == "error",
    "a failed insert is Refused(error), not Sent")
assert(#player.messages == 0, "a failed insert prints no confirmation line")
insertWorks = true
reset()
sql = send("the same report once the insert works", "d")
assert(sql and player.messages[#player.messages] == "Bug report #1 received, thanks.",
    "an insert that lands is Sent with the new id")

-- 11. A hostile whitespace run cannot burn the world thread: trimming is linear,
--     so a 40,000-byte report returns at once and the over-long text is refused
--     before any query. The old trim cost ~14 s.
reset()
local hostile = "a" .. (" "):rep(40000) .. "b"
local started = os.clock()
handlers.Send(player, "title", hostile)
local elapsed = os.clock() - started
assert(elapsed < 0.5, "a 40,000-byte report is trimmed in linear time, took " .. elapsed .. "s")
assert(#queries == 0, "an over-long report never reaches a query")

-- 12. The build field is the deployed commit: the release MANIFEST's `cut:` line
--     when there is one, else the VERSION identity the version check reads.
local versionText = assert(io.open("VERSION")):read("*a")
assert(sql:find("'" .. assert(versionText:match("module=([^\n]+)")) .. "/", 1, true),
    "a dev tree falls back to the VERSION identity: " .. sql)

local directory = os.tmpname()
os.remove(directory)
assert(os.execute("mkdir -p '" .. directory .. "'"), "a scratch dir for the MANIFEST stub")
local manifest = assert(io.open(directory .. "/MANIFEST", "w"))
manifest:write("release: tor-test\ncut: deadbeef (" .. ("subject "):rep(40) .. ")\n")
manifest:close()
schemaFile = directory .. "/schema.csv"
sql = send("with a release MANIFEST", "d")
assert(sql:find("'deadbeef'", 1, true), "the deployed commit is the MANIFEST cut: line: " .. sql)
assert(not sql:find("subject", 1, true), "only the sha is stored, not the whole cut: line")
schemaFile = nil
os.remove(directory .. "/MANIFEST")
os.remove(directory)

os.time = realTime
print("Bug report server checks passed")
