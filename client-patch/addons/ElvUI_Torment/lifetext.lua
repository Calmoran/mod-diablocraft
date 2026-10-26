-- luacheck: globals ElvUI hooksecurefunc unpack GetMouseFocus UnitExists UnitHealth UnitHealthMax UnitIsDeadOrGhost
-- Life text read from the unit, not from a status bar.
--
-- ElvUI's unit frame health tags already call UnitHealth and UnitHealthMax (6.09
-- Core/Tags.lua), so their numbers are whole at any size and only the formatter
-- matters (core.lua). The tooltip's health line is the one
-- ElvUI draws from its status bar's GetValue and GetMinMaxValues (6.09
-- Modules/Tooltip/Tooltip.lua:466); the bar keeps 32-bit floats, exact only to
-- 16,777,216. Here the line is written again from the unit's own Life, and the
-- tooltip widened when the line is wider than it. The bar's fill is untouched.
local E = unpack(ElvUI)
local TT = E:GetModule("Tooltip")

local function tooltipLine(_, bar, value)
    if not (value and bar.text and TT.db and TT.db.healthBar and TT.db.healthBar.text) then return end
    local tip = bar:GetParent()
    local _, unit = tip:GetUnit()
    if not unit then
        local focus = GetMouseFocus()
        unit = focus and focus:GetAttribute("unit")
    end
    -- ElvUI's own cases stand: a tapped unit's percentage (the bar's max is 1)
    -- and the dead word.
    local _, barMax = bar:GetMinMaxValues()
    if not unit or not UnitExists(unit) or value <= 0 or barMax == 1 or UnitIsDeadOrGhost(unit) then return end
    local max = UnitHealthMax(unit)
    if max <= 0 then return end
    bar.text:SetText(E:ShortValue(UnitHealth(unit)) .. " / " .. E:ShortValue(max))
    if bar.text:GetStringWidth() > bar:GetWidth() then
        tip:SetMinimumWidth(bar.text:GetStringWidth())
        tip:Show()
    end
end
hooksecurefunc(TT, "GameTooltipStatusBar_OnValueChanged", tooltipLine)
