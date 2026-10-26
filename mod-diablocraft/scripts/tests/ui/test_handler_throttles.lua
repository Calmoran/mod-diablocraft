-- luacheck: ignore 111 112 113 121 122 143 212 431 432
-- Security G1 (UI fixes row 11): every server handler that queries the database
-- asks DCThrottle first. Run from the repo root:
--   lua mod-diablocraft/scripts/tests/ui/test_handler_throttles.lua
--
-- Loads every AIO server half in mod-diablocraft/lua/aio the way AIO does (name
-- order, AddAddon() true, so each file returns before its client half), with the
-- real dc_throttle.lua and stubs that count the work a call does: database
-- queries and executes, RunCommand (C++ commands read and write the database),
-- PrintError (a server log line) and AIO replies. Every server handler must be
-- classified below, so a new handler fails here until someone decides which
-- kind it is:
--
--   query  - a warm call does database or command work; a flood sent in one
--            instant must be cut off (the last call does no work at all);
--   free   - a warm call does no database, command or log work;
--   gapped - only a C++ command, and that command keeps its own per-player gap
--            (checked in the C++ source below), so a Lua bucket would only
--            double the limit.
--
-- The stubs make a call reach its work; they do not model the game. A global
-- this harness does not stub resolves to an inert callable, so a file loads
-- without its live dependencies; each "query" handler is proven to have done
-- work on its warm call, so the flood check is never vacuous.

local work = {db = 0, cmd = 0, log = 0, reply = 0}
local nowMs = 100000
function GetCurrTime() return nowMs end

local inert
inert = setmetatable({}, {
    __call = function() return nil end,
    __index = function() return inert end,
})
setmetatable(_G, {__index = function(_, key)
    -- ALE has no GetTime; dc_throttle.lua must not reach for it.
    if key == "GetTime" then return nil end
    return inert
end})
unpack = unpack or table.unpack

local function query() work.db = work.db + 1; return nil end
CharDBQuery, WorldDBQuery, AuthDBQuery = query, query, query
CharDBExecute, WorldDBExecute, AuthDBExecute = query, query, query
function PrintError() work.log = work.log + 1 end

local gossip = {}
function RegisterCreatureGossipEvent(entry, _, fn) gossip[entry] = fn end
function RegisterPlayerEvent() end
function RegisterGameObjectEvent() end
function RegisterServerEvent() end
function RegisterCreatureEvent() end
function CreateLuaEvent() end
function GetPlayerByGUID() return nil end

local channels = {}
AIO = {
    AddAddon = function() return true end,
    AddHandlers = function(name, t) channels[name] = t; return t end,
    Handle = function() work.reply = work.reply + 1 end,
    AddOnInit = function() end,
}
function require() return AIO end

local function object(fields)
    return setmetatable(fields, {__index = function() return function() return nil end end})
end
local item = object({
    GetGUIDLow = function() return 7 end,
    GetEntry = function() return 1 end,
    GetBagSize = function() return 16 end,
})
local channel = nil -- what GetCurrentSpell(2) answers
local interrupts = 0
local player = object({
    GetGUIDLow = function() return 1 end,
    GetGUID = function() return 1 end,
    IsAlive = function() return true end,
    IsInCombat = function() return false end,
    IsInWorld = function() return true end,
    GetNearestCreature = function() return object({}) end,
    GetNearestGameObject = function() return object({}) end,
    GetClass = function() return 1 end,
    GetLevel = function() return 70 end,
    GetAccountId = function() return 1 end,
    GetInstanceId = function() return 5 end,
    GetMapId = function() return 0 end,
    GetName = function() return "Tester" end,
    -- Holds one rift quest so the RiftBar's holdsRiftQuest pre-check lets push() reach
    -- its query (dc_riftbar.lua); t9df made that pre-check hide a player in no run.
    HasQuest = function(_, id) return id == 910020 end,
    GetItemByPos = function() return item end,
    GetCurrentSpell = function(_, kind) return kind == 2 and channel or nil end,
    InterruptSpell = function() interrupts = interrupts + 1 end,
    RunCommand = function() work.cmd = work.cmd + 1 end,
})

local dir = "mod-diablocraft/lua/aio/"
local files = {}
for name in io.popen("ls " .. dir):lines() do
    if name:match("%.lua$") then files[#files + 1] = name end
end
table.sort(files)
for _, name in ipairs(files) do dofile(dir .. name) end
assert(DCThrottle and DCThrottle.Allow, "the real dc_throttle.lua is loaded")

-- The Blacksmith's bucket and range are tunables (dc_blacksmith.lua allow/guard).
local TUNED = {["crafting.artisan_per_second"] = 5, ["crafting.artisan_burst"] = 10,
    ["crafting.artisan_interaction_range_yards"] = 10}
DCTunables.Get = function(category, name) return TUNED[category .. "." .. name] end
DCTunables.Or = function(category, name, fallback) return TUNED[category .. "." .. name] or fallback end

-- Every server handler, its kind, and the arguments that make a call reach its work.
local KINDS = {
    ["DiablocraftBlacksmith.Refresh"] = {"query"},
    ["DiablocraftBlacksmith.Target"] = {"query", 255, 1, 9},
    ["DiablocraftBugReport.Open"] = {"query"},
    ["DiablocraftBugReport.Send"] = {"query", "the window ate my mouse", "what happened", "0.1", "66"},
    ["DiablocraftCrafting.Refresh"] = {"query"},
    ["DiablocraftCrafting.Tables"] = {"free"},
    ["DiablocraftCube.Item"] = {"query", 255, 1},
    ["DiablocraftCube.Opened"] = {"free"},
    ["DiablocraftElite.Refresh"] = {"query"},
    ["DiablocraftGround.Refresh"] = {"free"},
    ["DiablocraftInventory.Equip"] = {"query", 23},
    ["DiablocraftInventory.Refresh"] = {"query"},
    ["DiablocraftInventory.Unequip"] = {"query", 0},
    ["DiablocraftJeweler.Balance"] = {"query"},
    ["DiablocraftJeweler.Gear"] = {"query", 255, 0, 0},
    ["DiablocraftJeweler.Items"] = {"query"},
    ["DiablocraftJeweler.Quote"] = {"query", 1},
    ["DiablocraftJeweler.Recipes"] = {"query"},
    ["DiablocraftJeweler.Refresh"] = {"query"},
    ["DiablocraftJeweler.Tables"] = {"free"},
    ["DiablocraftFollower.Tooltips"] = {"query", 1},
    ["DiablocraftParagon.Change"] = {"gapped", "primary", 1, true},
    ["DiablocraftParagon.Open"] = {"query"},
    ["DiablocraftParagon.Refresh"] = {"query"},
    ["DiablocraftParagon.Respec"] = {"gapped"},
    ["DiablocraftRiftBar.Refresh"] = {"query"},
    ["DiablocraftSkillbar.Channel"] = {"free"},
    ["DiablocraftSkillbar.Refresh"] = {"query"},
    ["DiablocraftSkillbar.Request"] = {"query"},
    ["DiablocraftSkillbar.Whirlwind"] = {"query", "start", 81004},
    ["DiablocraftStash.BuyTab"] = {"query"},
    ["DiablocraftStash.Close"] = {"free"},
    ["DiablocraftStash.Move"] = {"query", "bag", 23, "bag", 24},
    ["DiablocraftStash.Refresh"] = {"query"},
    ["DiablocraftTier.Open"] = {"query"},
    ["DiablocraftTier.Select"] = {"query", 1},
    -- Free here only because this harness's player is never in the hub (no hub row, an instance):
    -- in the hub State queries, behind tier:state, which test_tier_server.lua pins.
    ["DiablocraftTier.State"] = {"free"},
    ["DiablocraftTooltip.Context"] = {"query", "bank"},
    ["DiablocraftTooltip.Link"] = {"query", 99}, -- not carried: the stash lookup
    ["DiablocraftTooltip.Preview"] = {"query", 1},
    ["DiablocraftTooltip.Refresh"] = {"query"},
    ["DiablocraftTooltip.Snapshot"] = {"free", "ab"},
    ["DiablocraftVersion.Report"] = {"query", "5"},
}

local function call(fn, args)
    work.db, work.cmd, work.log, work.reply = 0, 0, 0, 0
    pcall(fn, player, unpack(args))
    return work.db + work.cmd + work.log, work.reply
end

-- Sessions the handlers check before their work: the Jeweler's and the Mystic's
-- gossip (dc_jeweler.lua valid(), dc_crafting.lua show()) and an open stash
-- (dc_stash.lua usable()). Each sets its session before its first query, so a
-- stub fault after that does not matter here.
assert(gossip[910004] and gossip[910001], "the Jeweler's and the Mystic's gossip hooks are registered")
pcall(gossip[910004], 1, player)
pcall(gossip[910001], 1, player, object({GetEntry = function() return 910001 end}))
pcall(channels.DiablocraftStash.Refresh, player)

local problems, seen = {}, {}
local names = {}
for name, handlers in pairs(channels) do
    for handler in pairs(handlers) do names[#names + 1] = name .. "." .. handler end
end
table.sort(names)
for _, key in ipairs(names) do
    seen[key] = true
    local spec = KINDS[key]
    local name, handler = key:match("^(.-)%.(.+)$")
    local fn = channels[name][handler]
    if not spec then
        problems[#problems + 1] = key .. ": a new server handler; classify it in KINDS"
    else
        local args = {unpack(spec, 2)}
        nowMs = nowMs + 600000
        call(fn, args)                 -- cold: lazy caches fill once per world
        nowMs = nowMs + 600000
        local warm = call(fn, args)
        if spec[1] == "free" then
            if warm > 0 then
                problems[#problems + 1] = key .. ": classified free but did database, command or log work; throttle it"
            end
        elseif spec[1] == "gapped" then
            if warm == 0 then problems[#problems + 1] = key .. ": classified gapped but sent no command" end
        else
            if warm == 0 then
                problems[#problems + 1] = key .. ": the harness never reached its work; fix its arguments"
            else
                nowMs = nowMs + 600000
                local last, reply
                for _ = 1, 200 do last, reply = call(fn, args) end
                if last + reply > 0 then
                    problems[#problems + 1] = key .. ": the 200th call in one instant still ran; no DCThrottle in front of it"
                end
            end
        end
    end
end
for key in pairs(KINDS) do
    if not seen[key] then problems[#problems + 1] = key .. ": classified but no longer registered" end
end
assert(#problems == 0, "\n  " .. table.concat(problems, "\n  "))

-- The two gapped handlers: the C++ commands they run keep their own gaps.
local cpp = assert(io.open("mod-diablocraft/src/paragon/dc_paragon.cpp")):read("*a")
assert(cpp:find("if (!EditGapOpen(h->GetSession()->GetPlayer()))", 1, true),
       "dc paragon allocate/deallocate keeps its per-player gap (EditGapOpen)")
assert(cpp:find("auto& state=State(p);RespecGate(state);", 1, true),
       "dc paragon respec keeps its cooldown (RespecGate)")

-- The Jeweler's reads spend the one Refresh budget (as Gear does), so a client cannot
-- multiply its allowance by spreading a flood across them.
local jeweler = channels.DiablocraftJeweler
nowMs = nowMs + 600000
for _ = 1, 200 do call(jeweler.Refresh, {}) end
for _, read in ipairs({{"Recipes"}, {"Balance"}, {"Items"}, {"Quote", 1}, {"Gear", 255, 0, 0}}) do
    local done, reply = call(jeweler[read[1]], {unpack(read, 2)})
    assert(done + reply == 0, "Jeweler " .. read[1] .. " spends the Refresh budget")
end

-- Whirlwind's stop must never be dropped: a dropped stop would leave the channel
-- running after the button is let go. It touches no database and no bucket, so
-- a flood of stops all land, and they do not spend the start bucket.
local whirlwind = channels.DiablocraftSkillbar.Whirlwind
channel = object({GetEntry = function() return 81004 end})
nowMs = nowMs + 600000
interrupts = 0
local stopWork = 0
for _ = 1, 200 do stopWork = stopWork + call(whirlwind, {"stop"}) end
assert(stopWork == 0, "a Whirlwind stop does no database work, got " .. stopWork)
assert(interrupts == 200, "every Whirlwind stop interrupts the channel, got " .. interrupts)
channel = nil
assert(call(whirlwind, {"start", 81004}) > 0, "the stops did not spend the start bucket")

print("PASS: every DB-querying server handler is throttled (G1, UI fixes row 11)")
