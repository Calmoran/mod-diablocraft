-- luacheck: globals MultiCastActionBarFrame CreateFrame InCombatLockdown
-- StockTotemBar.lua - the stock Shaman totem bar stays hidden.
--
-- Blizzard's MultiCastActionBarFrame (the four-slot totem bar) belongs to the stock Shaman's
-- totem spells, which the Torment Shaman does not have; its totems are Maelstrom skills on the
-- ordinary bars. At login the frame stops listening, moves under a hidden parent and hides, so
-- no later event or layout pass shows it again. A protected frame cannot be moved in combat:
-- the work waits for the end of it. Running twice changes nothing.
local hidden

local function hideBar()
    local bar = MultiCastActionBarFrame
    if not bar then return true end
    if InCombatLockdown() then return false end
    hidden = hidden or CreateFrame("Frame")
    hidden:Hide()
    bar:UnregisterAllEvents()
    bar:SetParent(hidden)
    bar:Hide()
    return true
end

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("PLAYER_LOGIN")
watcher:SetScript("OnEvent", function(self, event)
    if hideBar() then
        self:UnregisterAllEvents()
    else
        self:RegisterEvent("PLAYER_REGEN_ENABLED")
    end
end)
