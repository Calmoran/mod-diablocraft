-- luacheck: ignore 111 112 121 122 311
-- Run from repo root with `lua mod-diablocraft/scripts/tests/difficulty/test_tier_server.lua`.
--
-- The server half of dc_tier.lua against stubbed DB access (contract docs/contracts/tier-messages.md,
-- diablocraft-7p05). What it pins:
--   * Show sends every launch tier with its lock reason ("" = unlocked), from the generated
--     dc_difficulty_tiers unlock columns through the dc_tier_phase join, bounded by
--     monsters/launch_tier_count, mirroring DC::TierUnlocked / MeetsTierUnlock / LaunchTierCount;
--   * Show's pick reason: the hub (dc_world_hub_point 'spawn' map + area, no instance) and the
--     party leader, with C++'s own texts;
--   * Select re-checks unlock and pick before running `dc tierselect`, then tells every online
--     party member's button;
--   * State: the button's hub flag and current tier name, on request, on an area change (from the
--     event's new area) and a tick after a party join or leader change;
--   * the hub obelisk's click path (910010) is gone.
-- What this does NOT cover: C++'s own refusals (combat, cooldown, the hub in ChooseTier: fjqx) and
-- what the client draws (test_tier_client.lua).

local ROWS = {
    -- tier_id, name, hp, dmg, xp, gold, char, acct, solo
    {1, "Normal", 100, 100, 0, 0, 0, 0, 0},
    {2, "Hard", 200, 130, 75, 75, 0, 0, 0},
    {3, "Expert", 312, 189, 100, 100, 0, 0, 0},
    {4, "Master", 512, 273, 200, 200, 0, 60, 0},
    {5, "Torment I", 819, 396, 300, 300, 60, 0, 0},
    {6, "Torment II", 1311, 575, 400, 400, 60, 0, 0},
    {7, "Torment III", 2097, 833, 550, 550, 60, 0, 0},
    {8, "Torment IV", 3355, 1208, 800, 800, 60, 0, 0},
    -- 9 and 10 are otherwise identical, character-70: the only difference is the
    -- solo Greater Rift requirement, so a 70/70 run isolates that gate.
    {9, "Torment GR", 18985, 3604, 1900, 1850, 70, 0, 30},
    {10, "Torment GR twin", 18985, 3604, 1900, 1850, 70, 0, 0},
}

-- Ids that skip 3: DC::UnlockRules rejects a non-contiguous set, so all are out.
local NONCONTIG = {
    {1, "Normal", 100, 100, 0, 0, 0, 0, 0},
    {2, "Hard", 200, 130, 75, 75, 0, 0, 0},
    {4, "Master", 512, 273, 200, 200, 0, 60, 0},
}

local HUB_MAP, HUB_AREA = 571, 4395
local HUB_ONLY = "Choose difficulty in the hub."
local LEADER_ONLY = "Only the party leader may choose difficulty."
local PARTY_HUB_ONLY = "All online party members must be in the Sanctum to change difficulty."

local activeRows, accountMax, launchCount = ROWS, 1, 10
local tierOf = {} -- dc_character_tier by guid
local hubRow = {{HUB_MAP, HUB_AREA}}
local sent = {}  -- every AIO.Handle, in order

local function result(rows)
    if not rows or not rows[1] then return nil end
    local n = 1
    local function get(_, i) return rows[n][i + 1] end
    return {GetString = get, GetUInt32 = get, GetInt32 = get, GetDouble = get,
            NextRow = function() n = n + 1 return rows[n] ~= nil end}
end

_G.WorldDBQuery = function(q)
    if q:find("dc_world_hub_point", 1, true) then
        assert(q:find("name='spawn'", 1, true), "the hub is the spawn point C++ reads: " .. q)
        return result(hubRow)
    end
    assert(q:find("dc_tier_phase", 1, true), "unexpected world query: " .. q)
    return result(activeRows)
end
_G.CharDBQuery = function(q)
    if q:find("MAX(level)", 1, true) then return result({{accountMax}}) end
    local guid = q:match("dc_character_tier WHERE guid=(%d+)")
    if guid then return tierOf[tonumber(guid)] and result({{tierOf[tonumber(guid)]}}) end
    error("unexpected char query: " .. q)
end
local goEvents, playerEvents, groupEvents, timers = {}, {}, {}, {}
_G.RegisterGameObjectEvent = function(entry) goEvents[#goEvents + 1] = entry end
_G.RegisterPlayerEvent = function(event, fn) playerEvents[event] = fn end
_G.RegisterGroupEvent = function(event, fn) groupEvents[event] = fn end
_G.CreateLuaEvent = function(fn, delay, repeats) timers[#timers + 1] = {fn = fn, delay = delay, repeats = repeats} end

-- The cached tunables reader the server half uses instead of a C++ bridge. A
-- nil count means the row is missing: fail closed in DCTunables.Or's fallback.
_G.DCTunables = {
    Or = function(category, name, fallback)
        assert(category == "monsters" and name == "launch_tier_count",
               "unexpected tunable: " .. category .. "." .. name)
        if launchCount == nil then return fallback end
        return launchCount
    end,
}

local serverHandlers
_G.AIO = {
    AddAddon = function() return true end,
    AddHandlers = function(_, handlers) serverHandlers = handlers return handlers end,
    Handle = function(player, channel, action, ...)
        sent[#sent + 1] = {player = player, channel = channel, action = action, args = {...}}
    end,
}

local byGuid = {}
local function newPlayer(guid)
    local p = {level = 1, account = 7, guid = guid, map = HUB_MAP, area = HUB_AREA, instance = 0,
               group = nil, commands = {}, messages = {}}
    function p:GetLevel() return self.level end
    function p:GetAccountId() return self.account end
    function p:GetGUIDLow() return self.guid end
    function p:GetGUID() return 1000 + self.guid end
    function p:GetMapId() return self.map end
    function p:GetAreaId() return self.area end
    function p:GetInstanceId() return self.instance end
    function p:GetGroup() return self.group end
    function p:SendBroadcastMessage(text) self.messages[#self.messages + 1] = text end
    function p:RunCommand(cmd) self.commands[#self.commands + 1] = cmd end
    byGuid[1000 + guid] = p
    return p
end
_G.GetPlayerByGUID = function(guid) return byGuid[guid] end

local function newGroup(leader, ...)
    local members = {leader, ...}
    local group = {}
    function group:IsLeader(guid) return guid == leader:GetGUID() end
    function group:GetMembers() return members end
    for _, member in ipairs(members) do member.group = group end
    return group
end

local player = newPlayer(1)

-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
dofile('mod-diablocraft/lua/aio/dc_tier.lua')

assert(#goEvents == 0, "no gameobject (the hub obelisk 910010) opens the window any more")
assert(serverHandlers.State and serverHandlers.Open and serverHandlers.Select, "State, Open and Select are handled")

local function lastFor(p, action)
    for i = #sent, 1, -1 do
        if sent[i].player == p and sent[i].action == action then return sent[i] end
    end
end

-- Open as `p` at a level / account level: the Show record, and the unlocked ids.
local function open(level, accountLevel, p)
    p = p or player
    p.level = level
    accountMax = accountLevel
    sent = {}
    serverHandlers.Open(p)
    local show = lastFor(p, "Show")
    assert(show and show.channel == "DiablocraftTier", "Open answers with Show")
    local unlocked = {}
    for _, row in ipairs(show.args[1]) do
        if row[7] == "" then unlocked[#unlocked + 1] = row[1] end
    end
    return unlocked, show.args[1], show.args[2], show.args[3]
end

local function select(id, p)
    p = p or player
    p.commands = {}
    sent = {}
    serverHandlers.Select(p, id)
    return p.commands[1]
end

local function wants(ids, id)
    for _, value in ipairs(ids) do
        if value == id then return true end
    end
    return false
end

local function reasonOf(rows, id)
    for _, row in ipairs(rows) do if row[1] == id then return row[7] end end
end

-- Level 1, no level-60 character on the account: only the free tiers are unlocked, but every
-- launch tier is listed, the locked ones with the server's reason.
local ids, rows, current, pick = open(1, 1)
assert(#rows == 10, "every launch tier is a row, locked or not, got " .. #rows)
assert(rows[5][2] == "Torment I" and rows[5][3] == 819 and rows[5][6] == 300, "a row carries name and the four numbers")
assert(wants(ids, 1) and wants(ids, 2) and wants(ids, 3), "Normal-Hard-Expert are free")
assert(reasonOf(rows, 4) == "Requires a level 60 character on this account.", "Master's reason: " .. reasonOf(rows, 4))
assert(reasonOf(rows, 5) == "Requires character level 60.", "Torment I's reason: " .. reasonOf(rows, 5))
assert(reasonOf(rows, 9) == "Requires character level 70.", "the first failing rule is the reason")
assert(current == 1, "no dc_character_tier row is tier 1")
assert(pick == "", "solo in the hub may pick")

-- The account has a level-60 character but this one is level 1: Master opens,
-- Torment does not (the character is the one that must be 60).
ids = open(1, 60)
assert(wants(ids, 4), "Master is account-level gated")
assert(not wants(ids, 5), "Torment I is still character-level gated")

-- Account-level fallback: a level-60 character satisfies Master's account-60
-- requirement from their own level, even though the account MAX query returns 1.
ids = open(60, 1)
assert(wants(ids, 4), "character 60 satisfies the account-60 requirement")
assert(wants(ids, 5), "Torment I opens at character 60")

-- Isolate the solo-GR gate: at 70/70 the otherwise-identical zero-GR row is
-- unlocked and the nonzero-GR row is not, so it is the GR requirement (not the
-- character level) that refuses it.
ids, rows = open(70, 70)
assert(wants(ids, 10), "the zero-GR row is unlocked at 70/70")
assert(reasonOf(rows, 9) == "Requires Greater Rift 30 cleared solo.", "the GR row's reason: " .. reasonOf(rows, 9))
assert(#ids == 9, "nine unlocked with the default count, got " .. #ids)

-- The launch count bounds the list (audit C row 40): count 6 lists six; restoring 10 brings
-- them back.
launchCount = 6
ids, rows = open(70, 70)
assert(#rows == 6 and #ids == 6, "count 6 lists six, got " .. #rows)
launchCount = 10
ids, rows = open(70, 70)
assert(#rows == 10 and wants(ids, 10), "restoring the count lists them again")

-- DC::LaunchTierCount parity: anything but a finite whole number in
-- 1..joined-rowcount fails closed and lists no tiers.
for _, value in ipairs({6.5, 0, -1, 11, 0 / 0}) do
    launchCount = value
    _, rows = open(70, 70)
    assert(#rows == 0, "count " .. tostring(value) .. " must list nothing, got " .. #rows)
end
launchCount = nil
_, rows = open(70, 70)
assert(#rows == 0, "a missing count must list nothing")
launchCount = 10

-- A non-contiguous joined set is rejected by DC::UnlockRules, so it too fails
-- closed regardless of the count.
activeRows = NONCONTIG
_, rows = open(70, 70)
assert(#rows == 0, "non-contiguous tier ids must list nothing, got " .. #rows)
activeRows = ROWS

-- The current tier is the stored one.
tierOf[1] = 6
_, _, current = open(70, 70)
assert(current == 6, "current is dc_character_tier's tier")

-- Pick: the hub is the spawn point's map and area with no instance; each miss is the hub text.
for _, away in ipairs({{"map", 0}, {"area", 1}, {"instance", 5}}) do
    local key, value = away[1], away[2]
    local saved = player[key]
    player[key] = value
    _, _, _, pick = open(70, 70)
    assert(pick == HUB_ONLY, "outside the hub (" .. key .. ") the pick reason is the hub's, got " .. tostring(pick))
    assert(select(5) == nil, "outside the hub (" .. key .. ") Select runs nothing")
    player[key] = saved
end

-- A party: the leader picks for everyone, a member sees the window and may not.
local member, offline = newPlayer(2), newPlayer(3)
local group = newGroup(player, member, offline)
member.level = 70
_, _, _, pick = open(70, 70, member)
assert(pick == LEADER_ONLY, "a non-leader member may not pick, got " .. tostring(pick))
assert(select(5, member) == nil, "a non-leader's Select runs nothing")
_, _, _, pick = open(70, 70, player)
assert(pick == "", "the leader in the hub may pick")

-- diablocraft-01zoh: one online member outside the hub blocks the leader and the C++ call is never made.
-- Eluna's GetMembers lists online players only, so the offline third member is left out of the stub list.
local savedMembers = group.GetMembers
function group:GetMembers() return {player, member} end
member.area = HUB_AREA + 1
_, _, _, pick = open(70, 70, player)
assert(pick == PARTY_HUB_ONLY, "a member outside the Sanctum blocks the leader, got " .. tostring(pick))
assert(select(5) == nil, "and Select runs nothing")
member.area = HUB_AREA
_, _, _, pick = open(70, 70, player)
assert(pick == "", "every online member in the Sanctum lets the leader pick (an offline one is not listed)")
group.GetMembers = savedMembers

-- Select re-checks the unlock, never the client's payload.
player.level, accountMax = 70, 70
assert(select(9) == nil, "a GR-locked id is refused")
assert(select(0) == nil and select(1.5) == nil and select("4") == nil and select(11) == nil,
       "a non-tier id is refused")
launchCount = 6
assert(select(10) == nil, "an id above the launch count is refused")
launchCount = 10
player.level, accountMax = 1, 1
assert(select(4) == nil, "Master is refused without an account level 60")
player.level, accountMax = 70, 70

-- The leader picks: the command runs as the leader, the window is redrawn and every online
-- member's button is told (C++'s SyncGroup has already stored the tier: StoreTier is direct).
byGuid[offline:GetGUID()] = nil -- logged out: GetPlayerByGUID finds nobody
local function storeOnCommand(p, id) tierOf[p.guid] = id; tierOf[member.guid] = id end
player.RunCommand = function(self, cmd) self.commands[#self.commands + 1] = cmd; storeOnCommand(self, tonumber(cmd:match("%d+$"))) end
assert(select(7) == "dc tierselect 7", "an unlocked id from the leader in the hub runs the command")
assert(lastFor(player, "Show"), "the leader's window is redrawn")
local leaderState, memberState = lastFor(player, "State"), lastFor(member, "State")
assert(leaderState and leaderState.args[1] == true and leaderState.args[2] == "Torment III", "the leader's button reads the new tier")
assert(memberState and memberState.args[1] == true and memberState.args[2] == "Torment III", "the member's button reads it too")
assert(not lastFor(offline, "State"), "an offline member is skipped")
byGuid[offline:GetGUID()] = offline
for _, p in ipairs({player, member, offline}) do p.group = nil end
group = nil

-- Solo, the picker's own button is told.
player.RunCommand = function(self, cmd) self.commands[#self.commands + 1] = cmd; tierOf[self.guid] = tonumber(cmd:match("%d+$")) end
assert(select(5) == "dc tierselect 5", "solo in the hub runs the command")
assert(lastFor(player, "State").args[2] == "Torment I", "the solo button reads the new tier")

-- State on request: in the hub, true with the tier's name; outside, false and no name.
sent = {}
serverHandlers.State(player)
local state = lastFor(player, "State")
assert(state.args[1] == true and state.args[2] == "Torment I", "State in the hub")
player.area = 1
serverHandlers.State(player)
state = lastFor(player, "State")
assert(state.args[1] == false and state.args[2] == nil, "State outside the hub hides the button")

-- An area change reads the event's new area, not GetAreaId (which may still be the old one).
assert(playerEvents[47], "the area-change event is registered")
sent = {}
playerEvents[47](47, player, 1, HUB_AREA)
assert(lastFor(player, "State").args[1] == true, "walking into the hub area shows the button")
player.area = HUB_AREA
playerEvents[47](47, player, HUB_AREA, 1)
assert(lastFor(player, "State").args[1] == false, "walking out of it hides the button")

-- A join or a leader change: told a tick later (after C++'s SyncGroup), never inside the hook.
for _, event in ipairs({1, 4}) do
    assert(groupEvents[event], "group event " .. event .. " is registered")
    group = newGroup(member, player)
    tierOf[player.guid], tierOf[member.guid] = 5, 5
    sent, timers = {}, {}
    groupEvents[event](event, group, player:GetGUID())
    assert(#sent == 0, "nothing is sent inside the group hook (event " .. event .. ")")
    assert(#timers == 1 and timers[1].repeats == 1, "one deferred push is scheduled")
    tierOf[player.guid], tierOf[member.guid] = 8, 8 -- what SyncGroup stores in its own hook
    timers[1].fn()
    assert(lastFor(player, "State").args[2] == "Torment IV" and lastFor(member, "State").args[2] == "Torment IV",
           "after the tick both buttons read the leader's tier (event " .. event .. ")")
    for _, p in ipairs({player, member}) do p.group = nil end
end

-- No hub row: C++ is not ready either, so nobody is in the hub (fail closed).
hubRow = nil
dofile('mod-diablocraft/lua/aio/dc_tier.lua')
sent = {}
serverHandlers.State(player)
assert(lastFor(player, "State").args[1] == false, "a missing hub point shows no button")
_, _, _, pick = open(70, 70)
assert(pick == HUB_ONLY, "and nobody may pick")

-- Security G1: every handler asks DCThrottle (its own key) before any query, command or reply.
hubRow = {{HUB_MAP, HUB_AREA}}
dofile('mod-diablocraft/lua/aio/dc_tier.lua')
player.area, player.level = HUB_AREA, 70
local asked, queries = {}, 0
local realWorld, realChar = WorldDBQuery, CharDBQuery
WorldDBQuery = function(q) queries = queries + 1 return realWorld(q) end
CharDBQuery = function(q) queries = queries + 1 return realChar(q) end
DCThrottle.Allow = function(_, key) asked[#asked + 1] = key return false end
sent, player.commands = {}, {}
serverHandlers.State(player); serverHandlers.Open(player); serverHandlers.Select(player, 5)
assert(table.concat(asked, " ") == "tier:state tier:open tier:select", "each handler has its bucket: " .. table.concat(asked, " "))
assert(queries == 0 and #sent == 0 and #player.commands == 0, "a refused call does no work")

print('Difficulty tier checks passed')
