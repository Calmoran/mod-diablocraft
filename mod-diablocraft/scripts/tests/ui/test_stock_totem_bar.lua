-- luacheck: globals ElvUI unpack
-- luacheck: ignore 111 121 122 431
-- Run from the repo root with `lua mod-diablocraft/scripts/tests/ui/test_stock_totem_bar.lua`.
--
-- The stock Shaman totem bar (MultiCastActionBarFrame) stays hidden: Torment/StockTotemBar.lua
-- stops its events, moves it under a hidden parent and hides it at PLAYER_LOGIN, and waits for
-- the end of combat when the client is in it (a protected frame cannot be moved then; the
-- double below raises as the client does). The production file runs as it ships; mutants of its
-- source must each fail a check. A mock does NOT prove pixels: the designer's check is on the test sheet.
unpack = unpack or table.unpack

local PATH = "client-patch/addons/Torment/StockTotemBar.lua"
local source = assert(io.open(PATH)):read("*a")

local function run(src, opts)
    opts = opts or {}
    local clientGlobals = {
        assert = assert, error = error, ipairs = ipairs, pairs = pairs, next = next, select = select,
        tostring = tostring, tonumber = tonumber, type = type, unpack = unpack,
        print = function() end, math = math, string = string, table = table,
    }
    local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
    Mock.install(clientGlobals)
    local state = {combat = opts.combat or false, blocked = 0}
    clientGlobals.InCombatLockdown = function() return state.combat end

    local bar
    if not opts.noBar then
        bar = Mock.widget("Frame", "MultiCastActionBarFrame", clientGlobals.UIParent)
        bar:Show()
        for _, event in ipairs({"PLAYER_TOTEM_UPDATE", "ACTIONBAR_SLOT_CHANGED", "UPDATE_MULTI_CAST_ACTIONBAR"}) do
            bar:RegisterEvent(event)
        end
        -- A protected frame: the client refuses these while the player is in combat.
        for _, name in ipairs({"SetParent", "Hide", "UnregisterAllEvents"}) do
            local real = bar[name]
            bar[name] = function(self, ...)
                if state.combat then
                    state.blocked = state.blocked + 1
                    error("Interface action failed because of an AddOn", 2)
                end
                return real(self, ...)
            end
        end
        clientGlobals.MultiCastActionBarFrame = bar
    end

    local env = setmetatable({}, {
        __index = function(_, key)
            local value = clientGlobals[key]
            if value == nil and key ~= "MultiCastActionBarFrame" then
                error("a loaded file referenced a global unavailable in 3.3.5: " .. tostring(key), 2)
            end
            return value
        end,
        __newindex = clientGlobals,
    })
    clientGlobals._G = env
    local created = {}
    local makeFrame = clientGlobals.CreateFrame
    clientGlobals.CreateFrame = function(...)
        local frame = makeFrame(...)
        created[#created + 1] = frame
        return frame
    end

    local chunk
    if setfenv then
        chunk = assert(loadstring(src, "StockTotemBar.lua"))
        setfenv(chunk, env)
    else
        chunk = assert(load(src, "StockTotemBar.lua", "t", env))
    end
    chunk()
    local watcher = created[1]
    local function fire(event)
        local handler = watcher and watcher:GetScript("OnEvent")
        if handler and watcher:IsEventRegistered(event) then handler(watcher, event) end
    end
    return {bar = bar, state = state, watcher = watcher, fire = fire, ui = clientGlobals.UIParent}
end

local function hiddenAndDead(t)
    local bar = t.bar
    return not bar:IsShown() and bar:GetParent() ~= t.ui and not bar:GetParent():IsShown()
        and not bar:IsEventRegistered("PLAYER_TOTEM_UPDATE")
        and not bar:IsEventRegistered("ACTIONBAR_SLOT_CHANGED")
        and not bar:IsEventRegistered("UPDATE_MULTI_CAST_ACTIONBAR")
end

-- The checks; each returns nil when the production behaviour holds, else why not.
local function check(src)
    -- 1. out of combat, login hides it for good.
    local t = run(src)
    if not t.watcher then return "no watcher frame" end
    if not t.bar:IsShown() then return "the bar was hidden before login" end
    t.fire("PLAYER_LOGIN")
    if not hiddenAndDead(t) then return "after login the bar is still shown, listening or under the UI" end
    -- a stray Show on the hidden parent's child shows nothing on screen: the parent is hidden.
    t.bar:Show()
    if t.bar:GetParent():IsShown() then return "the new parent is visible" end

    -- 2. the watcher stops listening once done (no work on every later event).
    if t.watcher:IsEventRegistered("PLAYER_LOGIN") or t.watcher:IsEventRegistered("PLAYER_REGEN_ENABLED") then
        return "the watcher keeps listening after the bar is hidden"
    end

    -- 3. login in combat: nothing is touched, then the end of combat hides it.
    local c = run(src, {combat = true})
    c.fire("PLAYER_LOGIN")
    if c.state.blocked > 0 then return "touched the protected bar in combat" end
    if not c.bar:IsShown() or not c.bar:IsEventRegistered("PLAYER_TOTEM_UPDATE") then
        return "the bar changed in combat"
    end
    if not c.watcher:IsEventRegistered("PLAYER_REGEN_ENABLED") then return "no wait for the end of combat" end
    c.state.combat = false
    c.fire("PLAYER_REGEN_ENABLED")
    if not hiddenAndDead(c) then return "after combat the bar is still shown, listening or under the UI" end
    if c.watcher:IsEventRegistered("PLAYER_REGEN_ENABLED") then return "still waiting after the bar is hidden" end

    -- 4. no stock frame (a client without it): nothing happens, nothing errors.
    local n = run(src, {noBar = true})
    n.fire("PLAYER_LOGIN")
    if n.watcher:IsEventRegistered("PLAYER_LOGIN") or n.watcher:IsEventRegistered("PLAYER_REGEN_ENABLED") then
        return "a missing bar keeps the watcher listening"
    end

    -- 5. running twice changes nothing.
    local d = run(src)
    d.fire("PLAYER_LOGIN")
    local parent = d.bar:GetParent()
    d.watcher:RegisterEvent("PLAYER_LOGIN")
    d.fire("PLAYER_LOGIN")
    if d.bar:GetParent() ~= parent or not hiddenAndDead(d) then return "a second run changed the bar" end
    return nil
end

assert(check(source) == nil, "production: " .. tostring(check(source)))

-- Mutants: every one must be caught.
local mutants = {
    {"no Hide", "    bar:Hide()\n", ""},
    {"no UnregisterAllEvents", "    bar:UnregisterAllEvents()\n", ""},
    {"no reparent", "    bar:SetParent(hidden)\n", ""},
    {"parent left shown", "    hidden:Hide()\n", "    hidden:Show()\n"},
    {"no combat wait", "    if InCombatLockdown() then return false end\n", ""},
    {"combat never retried", 'self:RegisterEvent("PLAYER_REGEN_ENABLED")', "do end"},
    {"watcher never stops", "        self:UnregisterAllEvents()\n", ""},
    {"missing bar retried", "    if not bar then return true end\n", "    if not bar then return false end\n"},
    {"wrong event", 'watcher:RegisterEvent("PLAYER_LOGIN")', 'watcher:RegisterEvent("PLAYER_ENTERING_WORLD")'},
}
local killed = 0
for _, m in ipairs(mutants) do
    local from, to = m[2], m[3]
    local i, j = source:find(from, 1, true)
    assert(i, "mutant '" .. m[1] .. "' no longer matches the source")
    local mutated = source:sub(1, i - 1) .. to .. source:sub(j + 1)
    local ok, why = pcall(check, mutated)
    assert(not ok or why ~= nil, "mutant survived: " .. m[1])
    killed = killed + 1
end

print("test_stock_totem_bar: ok (" .. killed .. " mutants killed)")
