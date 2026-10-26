-- luacheck: globals ElvUI unpack
-- luacheck: ignore 111 121 122 431
-- Run from the repo root with `lua mod-diablocraft/scripts/tests/ui/test_life_text.lua`.
--
-- Life text reads UnitHealth itself (client 64-bit numbers). The status bar a
-- unit frame fills keeps its values as 32-bit floats, exact only to 16,777,216
-- (the model below rounds them the same way), and the stock text caps a long
-- number to K and M. Production files run as they ship: Torment/Economy.lua
-- (Econ.Gold), Torment/LifeText.lua (the stock frames) and
-- ElvUI_Torment/core.lua + lifetext.lua (ElvUI's tooltip line and formatter).
-- FrameXML's TextStatusBar_UpdateTextString and ElvUI 6.09's tooltip handler are
-- models of their shapes (TextStatusBar.lua:33-85, Tooltip.lua:466-487); mocks
-- do NOT prove pixels.
--
-- The stubbed Life is 50 billion, the number the check asks for, and one past a
-- float's reach so a bar read is visibly wrong.

unpack = unpack or table.unpack

-- A 32-bit float's value: 24 significant bits.
local function f32(x)
    if x == 0 then return 0 end
    local m, e = math.frexp(x)
    return math.ldexp(math.floor(m * 2 ^ 24 + 0.5) / 2 ^ 24, e)
end

local units = {}
local cvars = {}

local clientGlobals = {
    assert = assert, error = error, ipairs = ipairs, pairs = pairs, next = next, select = select,
    tostring = tostring, tonumber = tonumber, type = type, unpack = unpack,
    print = function() end,
    math = math, string = string, table = table, strlen = string.len,
}
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install(clientGlobals)
local frames = Mock.frames

clientGlobals.UnitName = function() return "Tester" end
clientGlobals.UnitGUID = function() return "Player-1" end
clientGlobals.UnitExists = function(unit) return units[unit] ~= nil end
clientGlobals.UnitHealth = function(unit) return units[unit] and units[unit].hp or 0 end
clientGlobals.UnitHealthMax = function(unit) return units[unit] and units[unit].max or 0 end
clientGlobals.UnitIsDeadOrGhost = function(unit) return units[unit] and units[unit].dead or false end
clientGlobals.GetCVarBool = function(name) return cvars[name] or false end
clientGlobals.GetMouseFocus = function() return clientGlobals.WorldFrame end
clientGlobals.SendChatMessage = function() end
clientGlobals.SlashCmdList = {}
clientGlobals.DEFAULT_CHAT_FRAME = {AddMessage = function() end}
clientGlobals.DiablocraftUI = {}
clientGlobals.Diablocraft = false
clientGlobals.GetAddOnMetadata = function() return "0.4" end
clientGlobals.MoneyFrame_Update = function() end
clientGlobals.MerchantFrame_Update = function() end
clientGlobals.MAX_ITEM_COST = 3
clientGlobals.GetMerchantNumItems = function() return 0 end
clientGlobals.GetMerchantItemCostItem = function() return nil end
clientGlobals.GetItemIcon = function() return nil end
Mock.widget("Frame", "MerchantFrame"):Hide()
Mock.widget("Frame", "MerchantMoneyFrame")

local env = setmetatable({}, {
    __index = function(_, key)
        local value = clientGlobals[key]
        if value == nil then
            error("a loaded file referenced a global unavailable in 3.3.5: " .. tostring(key), 2)
        end
        return value
    end,
    __newindex = clientGlobals,
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

-- ------------------------------------------------------------ FrameXML model

-- TextStatusBar.lua:33-85 for the numeric case a health bar takes, with the cap
-- (UnitFrame_Initialize sets capNumericDisplay on a health bar); the percentage
-- branch is the bar's own ratio. GetValue and GetMinMaxValues hand back the
-- widget's floats.
local function capped(value)
    local text = tostring(value)
    if #text > 8 then return text:sub(1, -7) .. "M" elseif #text > 5 then return text:sub(1, -4) .. "K" end
    return text
end
function clientGlobals.TextStatusBar_UpdateTextString(bar)
    local textString = bar.TextString
    if not textString then return end
    local value = bar:GetValue()
    local _, valueMax = bar:GetMinMaxValues()
    if valueMax > 0 and not bar.pauseUpdates then
        if (clientGlobals.GetCVarBool("statusTextPercentage") or bar.showPercentage) and not bar.showNumeric then
            textString:SetText(tostring(math.ceil(value / valueMax * 100)) .. "%")
        else
            bar.isZero = nil
            textString:SetText(capped(value) .. " / " .. capped(valueMax))
        end
    else
        textString:SetText("")
    end
end
function clientGlobals.UnitFrameHealthBar_OnEvent() end
function clientGlobals.UnitFrameManaBar_OnEvent() end

local function unitBar(name, unit, onEvent)
    local bar = Mock.widget("StatusBar", name)
    local text = bar:CreateFontString(nil, "OVERLAY")
    text:SetFont("Fonts\\FRIZQT__.TTF", 10)
    bar.unit, bar.TextString = unit, text
    bar:SetScript("OnEvent", onEvent)
    bar.GetValue = function() return f32(units[unit].hp) end
    bar.GetMinMaxValues = function() return 0, f32(units[unit].max) end
    return bar, text
end

-- ---------------------------------------------------------------- load them

loadWith("client-patch/addons/Torment/Economy.lua")
local Econ = assert(env.Diablocraft.Econ, "Diablocraft.Econ is exported")

-- ------------------------------------------ 1. the formatter takes any size

for _, case in ipairs({
    {50000000000, "50,000,000,000"},
    {100000000000, "100,000,000,000"},
    {123456789012345, "123,456,789,012,345"},          -- 15 digits: tostring gives 1.2345678901234e+14
    {9007199254740992, "9,007,199,254,740,992"},        -- 2^53
    {1636000000000000000, "1,636,000,000,000,000,000"},
}) do
    assert(Econ.Gold(case[1]) == case[2], "Econ.Gold(" .. string.format("%.0f", case[1]) .. ") = " .. Econ.Gold(case[1]))
end
assert(Econ.Gold("18446744073709551615") == "18,446,744,073,709,551,615", "a digit string is kept whole")
assert(Econ.Gold(0) == "0" and Econ.Gold(7) == "7" and Econ.Gold(30000) == "30,000", "small numbers as before")

-- ------------------------------------------ 2. the stock frame's Life text

units.target = {hp = 50000000001, max = 100000000000}
local bar, text = unitBar("TestTargetHealthBar", "target", clientGlobals.UnitFrameHealthBar_OnEvent)
clientGlobals.TextStatusBar_UpdateTextString(bar)
assert(text.text == "49999M / 99999M", "the stock text before the hook is the capped float bar value: " .. tostring(text.text))

loadWith("client-patch/addons/Torment/LifeText.lua")
assert(env.Diablocraft.LifeText, "LifeText exports its table")
assert(Mock.hooks.TextStatusBar_UpdateTextString, "LifeText hooks TextStatusBar_UpdateTextString")

local function stockText(unit)
    local b, t = unitBar("TestBar" .. unit, unit, clientGlobals.UnitFrameHealthBar_OnEvent)
    clientGlobals.TextStatusBar_UpdateTextString(b)
    return t.text, b, t
end

units.target = {hp = 50000000000, max = 100000000000}
assert(stockText("target") == "50,000,000,000 / 100,000,000,000", "a 50 billion Life reads whole: " .. stockText("target"))
units.target = {hp = 50000000001, max = 100000000000}
assert(stockText("target") == "50,000,000,001 / 100,000,000,000",
    "one past a float's reach is exact: " .. stockText("target"))
units.target = {hp = 1636000000000000000, max = 1636000000000000000}
assert(stockText("target") == "1,636,000,000,000,000,000 / 1,636,000,000,000,000,000", "past 14 digits: " .. stockText("target"))
units.target = {hp = 30000, max = 30000}
assert(stockText("target") == "30,000 / 30,000", "a player's Life is the same rule, full digits: " .. stockText("target"))
units.target = {hp = 0, max = 100000000000}
assert(stockText("target") == "0 / 100,000,000,000", "dead is zero over max")

-- A mana bar is also a unit bar; its text is the stock one.
units.player = {hp = 12345, max = 12345}
local mana, manaText = unitBar("TestManaBar", "player", clientGlobals.UnitFrameManaBar_OnEvent)
clientGlobals.TextStatusBar_UpdateTextString(mana)
assert(manaText.text == "12345 / 12345", "a power bar keeps the stock text: " .. tostring(manaText.text))

-- A bar with no unit (the XP bar) is not touched.
local xp = Mock.widget("StatusBar", "TestXPBar")
xp.TextString = xp:CreateFontString(nil, "OVERLAY")
xp.TextString:SetFont("Fonts\\FRIZQT__.TTF", 10)
xp.GetValue = function() return 4321 end
xp.GetMinMaxValues = function() return 0, 90000 end
clientGlobals.TextStatusBar_UpdateTextString(xp)
assert(xp.TextString.text == "4321 / 90000", "a bar with no unit keeps the stock text: " .. xp.TextString.text)

-- The percentage text is the bar's own ratio and stays.
units.target = {hp = 50000000001, max = 100000000000}
cvars.statusTextPercentage = true
assert(stockText("target") == "50%", "percent text stays the bar's own ratio: " .. stockText("target"))
cvars.statusTextPercentage = nil

-- A disconnected unit's bar is drawn full, and so is its text.
local dis, disText = unitBar("TestDisconnected", "target", clientGlobals.UnitFrameHealthBar_OnEvent)
dis.disconnected = true
clientGlobals.TextStatusBar_UpdateTextString(dis)
assert(disText.text == "100,000,000,000 / 100,000,000,000", "disconnected reads max over max: " .. disText.text)

-- No Life at all keeps the stock empty text and the frame hidden by it.
units.target = {hp = 0, max = 0}
assert(stockText("target") == "", "max 0 leaves the stock text")

-- Without the shared formatter the stock text stands.
local formatter = env.Diablocraft.Econ
env.Diablocraft.Econ = nil
units.target = {hp = 50000000000, max = 100000000000}
assert(stockText("target") == "49999M / 99999M", "no Econ: the stock text stands: " .. stockText("target"))
env.Diablocraft.Econ = formatter

-- ------------------------------------- 3. ElvUI's tooltip line and formatter

local function elvuiShortValue(_, v) return string.format("%.1fM", v / 1e6) end
local E = {}
E.ShortValue = elvuiShortValue
function E.BuildPrefixValues() end
local torment = {}
-- 6.09 Modules/Tooltip/Tooltip.lua:466-487.
local TT = {db = {healthBar = {text = true}}}
function TT:GameTooltipStatusBar_OnValueChanged(tt, value)
    if not value or not tt.text or not self.db.healthBar.text then return end
    local _, unit = tt:GetParent():GetUnit()
    local _, max = tt:GetMinMaxValues()
    if value > 0 and max == 1 then
        tt.text:SetText(string.format("%d%%", math.floor(value * 100)))
    elseif value == 0 or (unit and clientGlobals.UnitIsDeadOrGhost(unit)) then
        tt.text:SetText("Dead")
    else
        tt.text:SetText(E:ShortValue(value) .. " / " .. E:ShortValue(max))
    end
end
function E.GetModule(_, name)
    return assert(({ElvUI_Torment = torment, Tooltip = TT})[name], "unknown module " .. tostring(name))
end
E.oUF = {colors = {power = {}}}
clientGlobals.ElvUI = {E}

loadWith("client-patch/addons/ElvUI_Torment/core.lua", "ElvUI_Torment")

-- ElvUI's formatter for a Life the unit frames' tags hand over.
assert(E:ShortValue(50000000000) == "50,000,000,000", "the formatter: " .. E:ShortValue(50000000000))
assert(E:ShortValue(1636000000000000000) == "1,636,000,000,000,000,000", "past 14 digits: " .. E:ShortValue(1636000000000000000))

local tip = clientGlobals.GameTooltip
local tbar = Mock.widget("StatusBar", "GameTooltipStatusBar", tip)
tbar:SetWidth(200)
tbar.text = tbar:CreateFontString(nil, "OVERLAY")
tbar.text:SetFont("Fonts\\FRIZQT__.TTF", 10)
tip.StatusBar = tbar
local function hover(unit, dead)
    units.mouseover = unit
    unit.dead = dead
    tip:SetUnit("mouseover")
    tip:Show()
    -- The bar holds floats, as the widget does.
    tbar.GetMinMaxValues = function() return 0, f32(unit.max) end
    TT:GameTooltipStatusBar_OnValueChanged(tbar, f32(unit.hp))
    return tbar.text.text
end

local before = hover({hp = 50000000001, max = 100000000000})
assert(before == "49,999,998,976 / 99,999,997,952",
    "before lifetext.lua ElvUI's own line is the bar's floats: " .. before)

loadWith("client-patch/addons/ElvUI_Torment/lifetext.lua", "ElvUI_Torment")
assert(hover({hp = 50000000001, max = 100000000000}) == "50,000,000,001 / 100,000,000,000",
    "the tooltip line reads UnitHealth, exact: " .. tbar.text.text)
assert(hover({hp = 1636000000000000000, max = 1636000000000000000}) ==
    "1,636,000,000,000,000,000 / 1,636,000,000,000,000,000", "past 14 digits: " .. tbar.text.text)
assert(hover({hp = 0, max = 100000000000}) == "Dead", "a dead unit keeps ElvUI's word: " .. tbar.text.text)
assert(hover({hp = 5, max = 10}, true) == "Dead", "a dead unit with Life left keeps ElvUI's word")
assert(hover({hp = 30000, max = 30000}) == "30,000 / 30,000", "a small Life: " .. tbar.text.text)

-- A tapped unit (the bar's max is 1) keeps ElvUI's percentage.
units.mouseover = {hp = 0.5, max = 1}
tip:SetUnit("mouseover")
tbar.GetMinMaxValues = function() return 0, 1 end
TT:GameTooltipStatusBar_OnValueChanged(tbar, 0.5)
assert(tbar.text.text == "50%", "a tapped unit keeps its percentage: " .. tbar.text.text)

-- A line wider than the bar widens the tooltip.
local widths = {}
tip.SetMinimumWidth = function(_, width) widths[#widths + 1] = width end
tbar.text.GetStringWidth = function(self) return #self.text * 7 end
hover({hp = 50000000001, max = 100000000000})
assert(#widths == 1 and widths[1] == #"50,000,000,001 / 100,000,000,000" * 7, "the tooltip widens to the line: " .. #widths .. " " .. tostring(widths[1]) .. " " .. tbar:GetWidth())

print("test_life_text: ok")
