-- luacheck: globals AIO CreateFrame WorldFrame GetCVar SetCVar GetTime UnitName SendAddonMessage DiablocraftUI
-- luacheck: globals DCTunables WorldDBQuery RegisterPlayerEvent PrintError
-- luacheck: ignore 111 121 122 431 432
-- Run from repo root with `lua mod-diablocraft/scripts/tests/loot/test_ground_plates_v_gate.lua`.
--
-- UI ruling R4 (ruling 2026-10-03, diablocraft-ui-rulings): "We swapped to normal loot, this
-- is not needed." The V takeover in dc_ground_plates.lua (nameplateShowEnemies held at 1, "show
-- monster plates" as the addon's own saved flag) is removed, whatever ground_delivery_enabled
-- says. V and enemy nameplates are the stock client's: the addon never reads or writes the CVar,
-- never listens for CVAR_UPDATE, never touches the saved table, and never hides a monster plate.
-- The server's Tuning push carries no ground-delivery switch any more; nothing needs it.
--
-- Also kept from test_ground_plates_settings.lua (GitHub #85), whose saved flag is gone:
-- entering the world with no saved table, or a non-table one, raises no Lua error and invents
-- nothing. Driven on the production file with a stub 3.3.5a API and one monster plate on
-- WorldFrame; a stub cannot prove what the live client draws, only what the addon leaves alone.

local FILE = "mod-diablocraft/lua/aio/dc_ground_plates.lua"

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames

-- ------------------------------------------------------------------ server half

local pushed
do
    local handlers
    _G.AIO = {
        AddAddon = function() return true end,
        AddHandlers = function(_, h) handlers = h; return h end,
        Handle = function(_, channel, name, payload)
            if channel == "DiablocraftGround" and name == "Tuning" then pushed = payload end
        end,
        AddOnInit = function() end,
    }
    _G.RegisterPlayerEvent = function() end
    _G.PrintError = function() end
    _G.DCTunables = {Or = function(_, _, fallback) return fallback end}
    _G.WorldDBQuery = function(query)
        error("the label's Tuning push reads no world table of its own: " .. query)
    end
    dofile(FILE)
    handlers.Refresh({})
    assert(pushed, "the server half still pushes the label's Tuning")
    assert(pushed.boxPadX == 8 and pushed.boxPadY == 3 and pushed.boxAlpha == 0.72, "with the label's box values")
    assert(pushed.groundDelivery == nil, "the Tuning push carries no ground-delivery switch; nothing takes V over")
end

-- ------------------------------------------------------------------ client half

local cvar, reads, writes = "1", 0, 0
local driver, tuning, plate

-- One monster plate: the unnamed WorldFrame child the addon classifies by shape
-- (a StatusBar child plus two FontStrings), its health bar and its artwork. Built
-- from the shared mock so every call the addon makes is checked against 3.3.5a;
-- the returned table only names the parts the assertions look at.
local function newPlate()
    WorldFrame.children = {}
    local frame = CreateFrame("Frame", nil, WorldFrame)
    -- A monster plate's name and level are XML FontStrings with a template, so they have
    -- their font before SetText (the mock refuses text on a fontless FontString, as the
    -- client does: dc_widget_mock rule 5, diablocraft-scog).
    local name = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    name:SetText("Ghoul")
    local level = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    level:SetText("3")
    local art = frame:CreateTexture(nil, "ARTWORK")
    local bar = CreateFrame("StatusBar", nil, frame)
    bar:SetStatusBarColor(1, 0, 0)
    return {frame = frame, name = name, level = level, art = art, bar = bar}
end

local clock = 0
local function loadClient(saved)
    cvar, reads, writes, clock = "1", 0, 0, 0
    driver, tuning = nil, nil
    plate = newPlate()
    DiablocraftUI = saved
    _G.AIO = {
        AddAddon = function() return false end,
        AddHandlers = function(_, h) tuning = h; return h end,
        Handle = function() end,
    }
    _G.GetCVar = function() reads = reads + 1; return cvar end
    _G.SetCVar = function(_, value) writes = writes + 1; cvar = value end
    _G.GetTime = function() return clock end
    _G.UnitName = function() return "Tester" end
    _G.SendAddonMessage = function() end
    local before = #frames
    dofile(FILE)
    driver = frames[before + 1]
    assert(driver and driver.events.PLAYER_ENTERING_WORLD, "the driver listens for entering the world")
    assert(not driver.events.CVAR_UPDATE, "the addon no longer listens for CVar changes")
    assert(tuning and tuning.Tuning, "the client half has the Tuning handler")
end

local function event(name) driver.scripts.OnEvent(driver, name) end
local function sweep() clock = clock + 1; driver.scripts.OnUpdate(driver, 0.2) end
local function pressV()
    -- The stock binding: if 1 then 0 else 1, then CVAR_UPDATE (sent whether or not anyone listens).
    cvar = cvar == "1" and "0" or "1"
    if driver.scripts.OnEvent then driver.scripts.OnEvent(driver, "CVAR_UPDATE") end
    sweep()
end
local function monsterDrawn() return plate.name.shown and plate.level.shown and plate.bar.shown and plate.art.shown end

-- Whatever the server sends for ground delivery - nothing, off, on (a server still on 2ee7498a) -
-- V is stock. A saved "hide monsters" flag from the old takeover is left alone and ignored.
for _, switch in ipairs({"absent", false, true}) do
    local label = "with the switch " .. tostring(switch)
    loadClient({groundLootShowMonsterPlates = false})
    if switch ~= "absent" then tuning.Tuning(nil, {boxPadX = 8, boxPadY = 3, boxAlpha = 0.72, groundDelivery = switch}) end
    event("PLAYER_ENTERING_WORLD")
    sweep()
    assert(monsterDrawn(), label .. ", a saved 'hide monsters' flag must not hide a plate")
    pressV()
    assert(cvar == "0", label .. ", V turns " .. "nameplateShowEnemies off as in stock, got " .. cvar)
    assert(monsterDrawn(), label .. ", the addon hides no monster plate; the client does that itself")
    pressV()
    assert(cvar == "1", label .. ", V turns it back on as in stock")
    assert(writes == 0, label .. ", the addon never writes the CVar (wrote " .. writes .. ")")
    assert(reads == 0, label .. ", the addon never reads the CVar (read " .. reads .. ")")
    local keys = 0
    for _ in pairs(DiablocraftUI) do keys = keys + 1 end
    assert(DiablocraftUI.groundLootShowMonsterPlates == false and keys == 1,
           label .. ", the saved table is neither read into V nor written")
end

-- GitHub #85: entering the world with no saved table, or a non-table one, raises no Lua error.
loadClient(nil)
event("PLAYER_ENTERING_WORLD")
sweep()
assert(DiablocraftUI == nil, "no saved-variables table is invented client-side")
loadClient("not a table")
event("PLAYER_ENTERING_WORLD")
sweep()
assert(DiablocraftUI == "not a table", "an invalid table is left alone")

print("test_ground_plates_v_gate: no V takeover - V and nameplateShowEnemies are stock whatever the switch says")
