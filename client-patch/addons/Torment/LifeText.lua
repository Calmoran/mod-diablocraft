-- luacheck: globals Diablocraft hooksecurefunc GetCVarBool UnitHealth UnitHealthMax UnitFrameHealthBar_OnEvent TextStatusBar_UpdateTextString
-- LifeText.lua - the stock unit frames' Life text is read from the unit.
--
-- FrameXML prints a unit frame's Life text from the status bar
-- (TextStatusBar_UpdateTextString: bar:GetValue() and bar:GetMinMaxValues()).
-- The bar keeps its values as 32-bit floats, exact only to 16,777,216, and the
-- stock text caps a long number to K and M. Here the text of a unit health bar
-- is written again from UnitHealth and UnitHealthMax, which hand the client's
-- own number to Lua whole, grouped in full by the shared formatter
-- (Econ.Gold, 12-ui U4). The bar's fill is untouched.
Diablocraft = Diablocraft or {}

local LT = {}
Diablocraft.LifeText = LT

-- The text the frame draws for cur / max, or nil when the shared formatter is
-- not loaded (the stock text then stands).
function LT.Text(cur, max)
    local Econ = Diablocraft.Econ
    if not (Econ and Econ.Gold) then return nil end
    return Econ.Gold(cur) .. " / " .. Econ.Gold(max)
end

-- A unit health bar is the one whose OnEvent is the stock health handler; the
-- mana bars (also unit bars) have their own.
local function isHealthBar(bar)
    return bar.unit and bar.TextString and bar:GetScript("OnEvent") == UnitFrameHealthBar_OnEvent
end

local function update(bar)
    if not isHealthBar(bar) or bar.pauseUpdates or bar.isZero then return end
    -- The percentage text (a bar set to show percent) is the bar's own ratio,
    -- right at any size; only the numeric text is rewritten.
    if (GetCVarBool("statusTextPercentage") or bar.showPercentage) and not bar.showNumeric then return end
    local max = UnitHealthMax(bar.unit)
    if max <= 0 then return end
    -- A disconnected unit's bar is drawn full (UnitFrameHealthBar_Update).
    local cur = bar.disconnected and max or UnitHealth(bar.unit)
    local text = LT.Text(cur, max)
    if text then bar.TextString:SetText(text) end
end

hooksecurefunc("TextStatusBar_UpdateTextString", update)
