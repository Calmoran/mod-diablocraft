-- luacheck: globals ElvUI unpack
-- luacheck: ignore 111 121 122 431 631
-- Run from the repo root with `lua mod-diablocraft/scripts/tests/ui/test_elvui_shortvalue.lua`.
--
-- UI fixes row 5 (ruling 2026-10-03, PM ruling): full grouped numbers under ElvUI.
-- Every K/M ElvUI draws goes through E:ShortValue (ElvUI 6.09 Core/Math.lua:51),
-- so client-patch/addons/ElvUI_Torment/core.lua replaces it with the one shared
-- formatter, the material counts' Econ.Gold (Torment/Economy.lua), and re-applies
-- it after E:BuildPrefixValues.
--
-- Mocks do NOT prove pixels: what the designer sees is on his card in
-- docs/test-diablocraft-ui-fixes-elvui.md.
--
-- The mock E.ShortValue is 6.09's ENGLISH formatter, so "the K/M is gone" is a
-- real check: the same value prints "25.0K" before the override and "25,000"
-- after.

unpack = unpack or table.unpack

-- ------------------------------------------------------- guarded client env

local printed = {}

local clientGlobals = {
    assert = assert, error = error, ipairs = ipairs, pairs = pairs, next = next, select = select,
    tostring = tostring, tonumber = tonumber, type = type, unpack = unpack,
    print = function(msg) printed[#printed + 1] = msg end,
    math = math, string = string, table = table,
}

-- The one shared strict 3.3.5a widget mock (diablocraft-yey2): it owns
-- CreateFrame, UIParent, hooksecurefunc and the rest of the client surface.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install(clientGlobals)
local frames = Mock.frames
Mock.setScreen(1024, 768)

local env
clientGlobals.UnitName = function() return "Tester" end
clientGlobals.UnitGUID = function() return "Player-1" end
clientGlobals.SendChatMessage = function() end
clientGlobals.SlashCmdList = {}
clientGlobals.DEFAULT_CHAT_FRAME = {AddMessage = function() end}
clientGlobals.DiablocraftUI = {}
-- The Torment addon's own global does not exist until Economy.lua makes it; the
-- guard needs the name known-but-nil so `Diablocraft = Diablocraft or {}` works.
clientGlobals.Diablocraft = false
clientGlobals.GetAddOnMetadata = function() return "0.4" end
clientGlobals.MoneyFrame_Update = function() end
-- Economy.lua reads these on the merchant window (its Blood Shard foot line,
-- kadala.md 4.11(a)); the 3.3.5a client has them even though this test never opens
-- the window. The stock window starts hidden (MerchantFrame.xml: hidden="true").
Mock.widget("Frame", "MerchantFrame"):Hide()
Mock.widget("Frame", "MerchantMoneyFrame")
clientGlobals.MAX_ITEM_COST = 3
clientGlobals.GetMerchantNumItems = function() return 0 end
clientGlobals.GetMerchantItemCostItem = function() return nil end
clientGlobals.GetItemIcon = function() return nil end
clientGlobals.MerchantFrame_Update = function() end

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

local function loadWith(path, ...)
    if setfenv then
        local chunk = assert(loadfile(path))
        setfenv(chunk, env)
        return chunk(...)
    end
    return assert(loadfile(path, "t", env))(...)
end

-- --------------------------------------------------------------- ElvUI mock

-- 6.09 Core/Math.lua:51 with the ENGLISH table: the abbreviation the override
-- has to remove. Below 1000 it is already a whole number (%.0f).
local function elvuiShortValue(_, v)
    if v >= 1e9 then return string.format("%.1fB", v / 1e9) end
    if v >= 1e6 then return string.format("%.1fM", v / 1e6) end
    if v >= 1e3 then return string.format("%.1fK", v / 1e3) end
    return string.format("%.0f", v)
end

local E = {}
E.ShortValue = elvuiShortValue
function E:BuildPrefixValues()
    -- ElvUI rebuilds its prefix table here (Core/Math.lua:34) and this mock also
    -- puts its own formatter back, which is what the override's re-apply must
    -- survive (ElvUI runs it at Initialize and on the number-format option).
    self.ShortValue = elvuiShortValue
end
local torment = {}
function E:GetModule(name)
    assert(name == "ElvUI_Torment", "core.lua asks for its own module only")
    return torment
end
-- oUF's power colours as ElvUI built them from the stock PowerBarColor (oUF
-- colors.lua): the stock tokens only, in its {r, g, b} shape.
local STOCK_MANA = {0, 0, 1}
E.oUF = {colors = {power = {MANA = STOCK_MANA, RAGE = {1, 0, 0}, ENERGY = {1, 1, 0}, RUNIC_POWER = {0, 0.82, 1}}}}
ElvUI = {E}
clientGlobals.ElvUI = ElvUI

-- ---------------------------------------------------------------- load it all

loadWith("client-patch/addons/Torment/Economy.lua")
local Econ = assert(env.Diablocraft and env.Diablocraft.Econ, "Diablocraft.Econ is exported")
-- The generated power list, as it ships, for core.lua's power colours.
loadWith("client-patch/addons/Torment/ResourceNames.lua")

assert(E:ShortValue(25000) == "25.0K", "the fixture starts on ElvUI's own abbreviation")

local originalBuildPrefixValues = E.BuildPrefixValues
loadWith("client-patch/addons/ElvUI_Torment/core.lua", "ElvUI_Torment")

-- ------------------------------------------------- 1. the abbreviation is gone

-- The four surfaces the ruling names, with the values their modules feed the
-- formatter: a unit frame's health (UnitFrames.lua via Tags/Elements), a
-- nameplate's health (same formatter), a tooltip's "value / max"
-- (Tooltip.lua:485) and a databar's experience (DataBars/Experience.lua:94).
local CASES = {
    {"unit frame health", 25000, "25,000"},
    {"nameplate health", 987654, "987,654"},
    {"tooltip value", 12345, "12,345"},
    {"tooltip max", 50000, "50,000"},
    {"databar experience", 1234567, "1,234,567"},
    {"databar rested", 12345678, "12,345,678"},
}
for _, case in ipairs(CASES) do
    local got = E:ShortValue(case[2])
    assert(got == case[3], case[1] .. ": expected " .. case[3] .. ", got " .. tostring(got))
    assert(not got:find("[KMBT]"), case[1] .. ": no suffix may survive: " .. tostring(got))
end

-- The tooltip's own line, as Tooltip.lua:485 writes it.
assert(E:ShortValue(12345) .. " / " .. E:ShortValue(50000) == "12,345 / 50,000",
    "the tooltip's value / max line is the grouped pair")

-- Fractions arrive as Lua numbers (HPS/DPS); below 1000 ElvUI rounds them itself.
assert(E:ShortValue(1234.6) == "1,235", "a fractional value rounds, it does not vanish")
assert(E:ShortValue(999.4) == "999", "and a rounded-to-999 stays three digits")
assert(E:ShortValue(-1234.5) == "-1,235", "a negative keeps its sign")

-- ------------------------------------------------- 2. one rule, not a copy

-- Every whole number is byte-for-byte the material counts' own formatter.
for _, value in ipairs({0, 7, 999, 1000, 1000000, 123456789, 4294967295}) do
    assert(E:ShortValue(value) == Econ.Gold(value),
        "value " .. value .. " must be Econ.Gold's own output: " .. Econ.Gold(value))
end
assert(Econ.Gold(1234567) == "1,234,567", "the material counts group in threes")

-- --------------------------------------- 3. ElvUI rebuilding the table is survived

E:BuildPrefixValues()
assert(E:ShortValue(25000) == "25,000",
    "after ElvUI rebuilds its prefix table the grouped formatter is back: "
        .. tostring(E:ShortValue(25000)))
E:BuildPrefixValues()
assert(E:ShortValue(1000) == "1,000", "and the re-apply is idempotent")

-- ---------------------------------------- 4. the Torment addon absent: ElvUI's own

local wasLoaded = env.Diablocraft
env.Diablocraft = false
assert(E:ShortValue(25000) == "25.0K",
    "without the formatter ElvUI's own behaviour stands, not a broken number")
env.Diablocraft = wasLoaded
assert(E:ShortValue(25000) == "25,000", "and the grouped formatter returns with it")

-- ------------------------------------------- 5. the class power tokens' colours

-- ElvUI's bars colour by oUF's colors.power[token]: every generated class power
-- token gets the list's colour there, and a stock token keeps ElvUI's own.
local powerColours, added = E.oUF.colors.power, 0
for token, power in pairs(env.Diablocraft.PowerTokens) do
    local colour = powerColours[token]
    if token == "MANA" then
        assert(colour == STOCK_MANA, "a stock token keeps ElvUI's own colour")
    else
        added = added + 1
        assert(colour and colour[1] == power.r and colour[2] == power.g and colour[3] == power.b,
            token .. " has the list's colour in oUF's power colours")
    end
end
assert(added >= 5, "every class power token was coloured, got " .. added)
assert(powerColours.RAGE[1] == 1 and powerColours.RAGE[2] == 0, "the stock entries are untouched")

-- ------------------------------------------------------------- the hooks

-- The mock's hooksecurefunc wraps the method in place; the wrap (not a plain
-- replace) is what the functional check above already needs to pass.
assert(E.BuildPrefixValues ~= originalBuildPrefixValues,
    "E:BuildPrefixValues is hooked with hooksecurefunc, so the re-apply is real")

-- The version line still works (row 13): the ADDON_LOADED handler is untouched.
local loader
for _, frame in ipairs(frames) do
    if frame.events.ADDON_LOADED then loader = frame end
end
assert(loader, "core.lua still installs its load line")
loader.scripts.OnEvent(loader, "ADDON_LOADED", "ElvUI_Torment")
assert(printed[1] == "Torment ElvUI 0.4 loaded",
    "the load line still names the TOC version: " .. tostring(printed[1]))
assert(#printed == 1, "and it says it once")

print("test_elvui_shortvalue: ok")
