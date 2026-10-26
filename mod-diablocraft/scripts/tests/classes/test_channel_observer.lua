-- luacheck: ignore 111 121 122 431 631
-- Run from the repo root with `lua mod-diablocraft/scripts/tests/classes/test_channel_observer.lua`.
--
-- The channel observer (Torment/ChannelObserver.lua, vz49.1) over the channelled-skills list
-- (Torment/ChannelSpells.lua): Whirlwind's watchers from UI fixes row 14 (ruling 2026-10-03),
-- generalised to every channelled skill, and the key release read from the client DLL's
-- TormentKeyDown (docs/contracts/client-key-state.md) on ElvUI's bound keys.
--
-- UI fixes row 14: the observers also watch ElvUI's own bars, the default UI. ElvUI's buttons are
-- LibActionButton CheckButtons: their spell is in the secure "action" attribute
-- (the Lua field stays 0, LibActionButton-1.0.lua:184), and their keys are
-- SetOverrideBindingClick bindings (ElvUI 6.09 ActionBars.lua:392) that never
-- call ActionButtonDown/Up, so the stock observers cannot see them.
--
-- Mocks do NOT prove the client's key delivery: whether a bound key fires
-- PreClick/OnMouseDown on ElvUI's button is the designer's card in
-- docs/test-diablocraft-ui-fixes-elvui.md.

unpack = unpack or table.unpack

-- ------------------------------------------------------- guarded client env

local clientGlobals = {
    assert = assert, error = error, ipairs = ipairs, pairs = pairs, next = next, select = select,
    tostring = tostring, tonumber = tonumber, type = type, unpack = unpack,
    print = function() end,
    math = math, string = string, table = table,
    SlashCmdList = {}, StaticPopupDialogs = {},
}

local env
env = setmetatable({}, {
    __index = function(_, key)
        local value = clientGlobals[key]
        if value == nil then
            error("a loaded file referenced a global unavailable in 3.3.5: " .. tostring(key), 2)
        end
        return value
    end,
})
clientGlobals._G = env

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install(env)
local frames = Mock.frames

local function runScript(frame, event, ...)
    local fn = frame.scripts[event]
    if fn then fn(frame, ...) end
end

-- The mock stores one chained script per event, which runs the original then the
-- hook, so a second HookScript is invisible in the script slot. Count the calls
-- instead, so "every button gets each observer once, not twice" still bites.
local hookCalls = setmetatable({}, {__mode = "k"})
local function trackHooks(frame)
    local counts = {}
    local realHook = frame.HookScript
    frame.HookScript = function(self, event, fn)
        counts[event] = (counts[event] or 0) + 1
        return realHook(self, event, fn)
    end
    hookCalls[frame] = counts
end
local function hookCount(frame, event)
    local counts = hookCalls[frame]
    return counts and counts[event] or 0
end

-- ----------------------------------------------------------- client fixtures

-- The action bar slots the mock client answers for. Slot to (kind, id).
local actions = {}

clientGlobals.GetActionInfo = function(slot) return unpack(actions[slot] or {}) end
clientGlobals.ActionButton_GetPagedID = function(button) return button.pagedID end
clientGlobals.GetSpellInfo = function(id)
    return ({[81004] = "Whirlwind", [81043] = "Whirlwind Alt", [83104] = "Ray of Frost"})[id]
end
clientGlobals.UnitChannelInfo = function() return rawget(env, "channel") end
clientGlobals.VehicleMenuBar = {IsShown = function() return false end}
clientGlobals.BonusActionBarFrame = {IsShown = function() return false end}
clientGlobals.VEHICLE_MAX_ACTIONBUTTONS = 6
env.channel = nil

-- The client DLL's key table (contract client-key-state.md): TormentKeyDown(key) answers true/false for
-- a key it knows and nil for one it does not. The 3.3.5 client has no key-state call of its own.
local keysDown = {}
local keyKnown = {Q = true, E = true, ["1"] = true}
local keyState = true -- false: the client without the DLL, the global is absent
clientGlobals.TormentKeyDown = function(key)
    if not keyState then error("TormentKeyDown read on a client without the DLL") end
    local last = tostring(key):match("([^-]+)$")
    if not keyKnown[last] then return nil end
    return keysDown[last] and true or false
end
-- `type(TormentKeyDown) == "function"` is the contract's check; the guarded env cannot read a missing
-- global, so the test flips the global the observer's check reads instead.
local realKeyDown = clientGlobals.TormentKeyDown
local function dllOn(on)
    keyState = on
    clientGlobals.TormentKeyDown = on and realKeyDown or false
end
-- The stock binding a button's keys come from: ElvUI hands each bar button keyBoundTarget (its stock
-- command name), reads GetBindingKey of it, and re-binds each key as a click (ActionBars.lua:386-400).
local bindings = {}
clientGlobals.GetBindingKey = function(command)
    local keys = bindings[command] or {}
    return unpack(keys)
end
-- The mouse: the button the cursor is over, and whether the left button is down.
local mouseOver, mouseLeft = nil, false
clientGlobals.GetMouseFocus = function() return mouseOver end
clientGlobals.IsMouseButtonDown = function(which) return which == "LeftButton" and mouseLeft end

-- The server intents the observers send.
local handled = {}
clientGlobals.AIO = {
    Handle = function(screen, op, action, spell) handled[#handled + 1] = {screen, op, action, spell} end,
}
clientGlobals.DiablocraftUI = {}
clientGlobals.Diablocraft = {} -- ArtSlots.lua makes it before ChannelSpells.lua loads

-- The stock bar the existing observers use, and the global functions the
-- client calls for a bound key. _G has to answer nil rather than no key at all
-- (the guard treats an unknown name as a sourced global it cannot provide).
local STOCK_PREFIXES = {"ActionButton", "BonusActionButton", "VehicleMenuBarActionButton",
                        "MultiBarBottomLeftButton", "MultiBarBottomRightButton",
                        "MultiBarLeftButton", "MultiBarRightButton"}
for _, prefix in ipairs(STOCK_PREFIXES) do
    for id = 1, 12 do env[prefix .. id] = false end
end
for id = 1, 12 do
    local button = Mock.widget("CheckButton", "ActionButton" .. id)
    button.action = 0
    trackHooks(button)
end
-- ElvUI's bars, the same: not present until its PLAYER_LOGIN.
for bar = 1, 6 do
    for id = 1, 12 do env["ElvUI_Bar" .. bar .. "Button" .. id] = false end
end
clientGlobals.ActionButtonDown = function() end
clientGlobals.ActionButtonUp = function() end
clientGlobals.MultiActionButtonDown = function() end
clientGlobals.MultiActionButtonUp = function() end

local function loadWith(path)
    if setfenv then
        local chunk = assert(loadfile(path))
        setfenv(chunk, env)
        return chunk()
    end
    return assert(loadfile(path, "t", env))()
end

-- ------------------------------------------------------------------- load

loadWith("client-patch/addons/Torment/ChannelSpells.lua")
loadWith("client-patch/addons/Torment/ChannelObserver.lua")

local observer
for _, frame in ipairs(frames) do
    if frame.scripts.OnEvent then observer = frame end
end
assert(observer, "the observer frame is installed")
assert(observer.events.PLAYER_LOGIN and observer.events.PLAYER_ENTERING_WORLD,
    "the observer scans for ElvUI's bars on the login events")
assert(observer.events.UNIT_SPELLCAST_CHANNEL_START and observer.events.UNIT_SPELLCAST_CHANNEL_STOP,
    "and still watches the channel events")

-- The stock path is untouched: every stock button keeps its mouse hooks.
local stock = env.ActionButton1
assert(hookCount(stock, "OnMouseDown") == 1 and hookCount(stock, "OnMouseUp") == 1,
    "the stock buttons keep their OnMouseDown/OnMouseUp observers")

-- ------------------------------------------- ElvUI bars are not there yet

-- ElvUI builds its six bars of twelve at Initialize (its PLAYER_LOGIN), after
-- the addon files load, so nothing is watched before the login events.
for id = 1, 12 do
    assert(hookCount(env["ActionButton" .. id], "PreClick") == 0,
        "the stock buttons are not given ElvUI's observers")
end

-- ElvUI's six bars, twelve LibActionButton CheckButtons each, with the spell in
-- the secure attribute and the Lua field left at 0.
for bar = 1, 6 do
    for id = 1, 12 do
        local name = "ElvUI_Bar" .. bar .. "Button" .. id
        local button = Mock.widget("CheckButton", name)
        button.action = 0
        trackHooks(button)
    end
end

observer.scripts.OnEvent(observer, "PLAYER_LOGIN")
observer.scripts.OnEvent(observer, "PLAYER_ENTERING_WORLD")

local function elvuiButton(bar, id) return env["ElvUI_Bar" .. bar .. "Button" .. id] end
for bar = 1, 6 do
    for id = 1, 12 do
        local button = elvuiButton(bar, id)
        assert(hookCount(button, "PreClick") == 1 and hookCount(button, "OnMouseDown") == 1
            and hookCount(button, "OnMouseUp") == 1,
            "every ElvUI button gets each observer once, not twice")
    end
end

-- ------------------------------------------------ a click on an ElvUI button

local button = elvuiButton(1, 1)
button:SetAttribute("action", 1)
actions[1] = {"spell", 81004}

runScript(button, "OnMouseDown", "LeftButton")
assert(#handled == 1 and handled[1][1] == "DiablocraftSkillbar" and handled[1][2] == "Whirlwind"
    and handled[1][3] == "start" and handled[1][4] == 81004,
    "a left-down on ElvUI's bar starts the watcher's spell")

-- A second down while held changes nothing.
runScript(button, "OnMouseDown", "LeftButton")
assert(#handled == 1, "a held button does not start twice")

-- The channel is up, the mouse is released, and the guarded stop goes out.
env.channel = "Whirlwind"
runScript(button, "OnMouseUp", "LeftButton")
observer.scripts.OnUpdate()
assert(#handled == 2 and handled[2][3] == "stop",
    "the release stops the channel once it is confirmed as the watched spell")

-- ------------------------------------------- a bound key: PreClick is observed

-- What ElvUI 6.09 delivers for a bound key (vz49.1, the designer's Nightly 87 report):
-- the key is a SetOverrideBindingClick (ActionBars.lua:396) and the button is
-- registered for one half only, "AnyDown" under ElvUI's default keyDown = true
-- (Settings/Profile.lua:4149, LibActionButton-1.0.lua:636). So the press is ONE
-- PreClick(self, "LeftButton", true) and the release delivers no script at all:
-- a click binding never fires OnMouseDown/OnMouseUp. The 10-03 test released the
-- key with OnMouseUp, which the client never sends, and so passed. The release
-- is read from the DLL's key table instead (contract client-key-state.md); the
-- key is the stock one ElvUI re-binds, GetBindingKey(button.keyBoundTarget).
local function pressKey(button, key)
    keysDown[key] = true
    mouseOver, mouseLeft = nil, false
    runScript(button, "PreClick", "LeftButton", true)
end
local function releaseKey(key) keysDown[key] = false end
local function bind(button, target, ...)
    button.keyBoundTarget = target
    bindings[target] = {...}
end

local keyed = elvuiButton(2, 3)
keyed:SetAttribute("action", 2)
actions[2] = {"spell", 81043}
bind(keyed, "MULTIACTIONBAR1BUTTON3", "Q")
env.channel = nil
for i = #handled, 1, -1 do handled[i] = nil end -- count from here

pressKey(keyed, "Q")
assert(#handled == 1 and handled[1][3] == "start" and handled[1][4] == 81043,
    "PreClick (the bound-key path) starts as well as the mouse")

env.channel = "Whirlwind Alt"
observer.scripts.OnEvent(observer, "UNIT_SPELLCAST_CHANNEL_START", "player")
observer.scripts.OnUpdate()
observer.scripts.OnUpdate()
assert(#handled == 1, "the key is still down: the channel runs and nothing is sent")
releaseKey("Q") -- the key goes up: nothing reaches the button, only the key table changes
observer.scripts.OnUpdate()
assert(#handled == 2 and handled[2][1] == "DiablocraftSkillbar" and handled[2][2] == "Whirlwind"
    and handled[2][3] == "stop", "the key's release stops it (Whirlwind's own message)")
observer.scripts.OnUpdate()
assert(#handled == 2, "and the stop goes once")

-- A second key bound to the same button: the channel runs while either is down.
local twice = elvuiButton(2, 4)
twice:SetAttribute("action", 2)
bind(twice, "MULTIACTIONBAR1BUTTON4", "E", "SHIFT-1")
env.channel = nil
pressKey(twice, "E")
assert(#handled == 3 and handled[3][3] == "start")
env.channel = "Whirlwind Alt"
keysDown["1"] = true
releaseKey("E")
observer.scripts.OnUpdate()
assert(#handled == 3, "the other bound key is still down: no stop")
releaseKey("1")
observer.scripts.OnUpdate()
assert(#handled == 4 and handled[4][3] == "stop", "the last bound key up stops it")

-- A tap shorter than a frame: down and up before the first OnUpdate, the channel
-- starts after. The release is still told, once the channel is up.
env.channel = nil
pressKey(twice, "E")
releaseKey("E")
assert(#handled == 5 and handled[5][3] == "start")
observer.scripts.OnUpdate()
env.channel = "Whirlwind Alt"
observer.scripts.OnEvent(observer, "UNIT_SPELLCAST_CHANNEL_START", "player")
observer.scripts.OnUpdate()
assert(#handled == 6 and handled[6][3] == "stop", "a quick tap still ends the channel that starts after it")

-- The client loses focus (alt-tab): every key reads false, no key-up arrives. That is a release.
env.channel = nil
pressKey(keyed, "Q")
env.channel = "Whirlwind Alt"
assert(#handled == 7 and handled[7][3] == "start")
releaseKey("Q")
observer.scripts.OnUpdate()
assert(#handled == 8 and handled[8][3] == "stop", "losing focus (every key false) ends it as a release")

-- A mouse click on an ElvUI button also runs PreClick, with the cursor over the button and the left
-- button down; the keys bound to that button are not down, and that is not a release.
env.channel = nil
mouseOver, mouseLeft = keyed, true
runScript(keyed, "OnMouseDown", "LeftButton")
runScript(keyed, "PreClick", "LeftButton", true)
assert(#handled == 9 and handled[9][3] == "start", "the click starts once")
env.channel = "Whirlwind Alt"
observer.scripts.OnUpdate()
observer.scripts.OnUpdate()
assert(#handled == 9, "a mouse hold is not ended by the key table (no bound key is down)")
mouseLeft = false
runScript(keyed, "OnMouseUp", "LeftButton")
observer.scripts.OnUpdate()
assert(#handled == 10 and handled[10][3] == "stop", "the mouse release stops it")
-- the order the client really uses for a click is not known here: PreClick before OnMouseDown holds too
env.channel = nil
mouseOver, mouseLeft = keyed, true
runScript(keyed, "PreClick", "LeftButton", true)
runScript(keyed, "OnMouseDown", "LeftButton")
assert(#handled == 11 and handled[11][3] == "start", "PreClick first: the click starts once")
env.channel = "Whirlwind Alt"
observer.scripts.OnUpdate()
assert(#handled == 11, "and the held mouse button is not ended by the key table either")
mouseLeft = false
runScript(keyed, "OnMouseUp", "LeftButton")
observer.scripts.OnUpdate()
assert(#handled == 12 and handled[12][3] == "stop")

-- A client without the DLL does what it does today: the key's press starts, and its release is not
-- told (ElvUI's press-only click), so nothing is added or removed because the global is absent.
dllOn(false)
env.channel = nil
pressKey(keyed, "Q")
env.channel = "Whirlwind Alt"
assert(#handled == 13 and handled[13][3] == "start")
releaseKey("Q")
observer.scripts.OnUpdate()
assert(#handled == 13, "without the DLL a key's release is not seen, as before")
runScript(keyed, "OnMouseUp", "LeftButton") -- a hand on the mouse elsewhere ends it as today
dllOn(true)

-- A key the DLL does not know (a mouse button bound to the skill, an unlisted key) answers nil:
-- no key state for that key, so the same as without the DLL for that button.
local odd = elvuiButton(3, 1)
odd:SetAttribute("action", 2)
bind(odd, "MULTIACTIONBAR2BUTTON1", "BUTTON4")
env.channel = nil
runScript(odd, "PreClick", "LeftButton", true)
env.channel = "Whirlwind Alt"
assert(#handled == 14 and handled[14][3] == "start")
observer.scripts.OnUpdate()
assert(#handled == 14, "an unknown key reads nil: the observer does not guess a release")
runScript(odd, "OnMouseUp", "LeftButton")

-- --------------------------------------- another channelled skill: the generic message

-- Ray of Frost (83104) is on the same list; its messages are the generic ones, with the spell id
-- (contract skillbar-messages.md), and its key release is read the same way.
local frost = elvuiButton(4, 2)
frost:SetAttribute("action", 5)
actions[5] = {"spell", 83104}
bind(frost, "MULTIACTIONBAR3BUTTON2", "E")
env.channel = nil
local before = #handled
pressKey(frost, "E")
assert(#handled == before + 1 and handled[before + 1][2] == "Channel"
    and handled[before + 1][3] == "start" and handled[before + 1][4] == 83104,
    "a Wizard channel starts through the generic Channel message with its spell id")
env.channel = "Ray of Frost"
observer.scripts.OnEvent(observer, "UNIT_SPELLCAST_CHANNEL_START", "player")
observer.scripts.OnUpdate()
assert(#handled == before + 1, "held key: nothing more")
releaseKey("E")
observer.scripts.OnUpdate()
assert(#handled == before + 2 and handled[before + 2][2] == "Channel"
    and handled[before + 2][3] == "stop" and handled[before + 2][4] == 83104,
    "its key's release stops it through Channel stop with the spell id")
-- and Whirlwind keeps its own message while bead 2 has not switched it
assert(handled[2][2] == "Whirlwind", "Whirlwind's own message is unchanged")
-- a Wizard channel started from the stock bar by mouse
env.channel = nil
local wiz = env.ActionButton2
wiz.action = 6
actions[6] = {"spell", 83104}
runScript(wiz, "OnMouseDown", "LeftButton")
env.channel = "Ray of Frost"
runScript(wiz, "OnMouseUp", "LeftButton")
observer.scripts.OnUpdate()
assert(handled[#handled][2] == "Channel" and handled[#handled][3] == "stop",
    "the stock bar's mouse release stops a Wizard channel through the generic message")

-- the list is the one ChannelSpells.lua carries: a spell not on it starts nothing
local spells = env.Diablocraft.ChannelSpells
assert(spells[81004] == "Whirlwind" and spells[83104] == "Ray of Frost", "the list names the skill of each spell id")
assert(spells[83276] == nil, "Archon's Disintegration Wave is not on the list (its hold is not ruled)")

-- ------------------------------------------------------- nothing else starts

for i = #handled, 1, -1 do handled[i] = nil end
env.channel = nil
local other = elvuiButton(6, 12)
other:SetAttribute("action", 3)
actions[3] = {"spell", 999}
runScript(other, "PreClick")
runScript(other, "OnMouseDown", "LeftButton")
assert(#handled == 0, "a button without a watched spell starts nothing")

-- An empty ElvUI slot has no action attribute and no paged id.
local empty = elvuiButton(6, 11)
empty:SetAttribute("action", nil)
runScript(empty, "OnMouseDown", "LeftButton")
assert(#handled == 0, "an empty ElvUI slot starts nothing")

-- ------------------------------------------------- the stock path still works

local stockButton = env.ActionButton1
stockButton.action = 4
actions[4] = {"spell", 81004}
env.channel = nil

runScript(stockButton, "OnMouseDown", "LeftButton")
assert(#handled == 1 and handled[1][3] == "start" and handled[1][4] == 81004,
    "the stock button's own mouse observer still starts")
env.channel = "Whirlwind"
runScript(stockButton, "OnMouseUp", "LeftButton")
observer.scripts.OnUpdate()
assert(#handled == 2 and handled[2][3] == "stop", "and its release still stops")

-- The stock bound key goes through ActionButtonDown/Up, as before.
env.channel = nil
env.ActionButtonDown(1)
assert(#handled == 3 and handled[3][3] == "start",
    "a stock bound key still starts through ActionButtonDown")
env.channel = "Whirlwind"
env.ActionButtonUp(1)
observer.scripts.OnUpdate()
assert(#handled == 4 and handled[4][3] == "stop",
    "and its release still stops through ActionButtonUp")

print("test_channel_observer: ok")
