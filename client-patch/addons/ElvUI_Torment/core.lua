-- luacheck: globals GetAddOnMetadata ElvUI Diablocraft hooksecurefunc unpack
local addonName = ...

-- Proof of life for the addon list: one chat line when our TOC is loaded, naming
-- the TOC's own version so the two cannot drift apart again (it said 0.3 under a
-- 0.4 TOC; UI fixes row 13).
local loader = CreateFrame("Frame")
loader:RegisterEvent("ADDON_LOADED")
loader:SetScript("OnEvent", function(self, event, name)
    if name ~= addonName then
        return
    end
    self:UnregisterEvent("ADDON_LOADED")
    print("Torment ElvUI " .. (GetAddOnMetadata(addonName, "Version") or "?") .. " loaded")
end)

-- ------------------------------------------------------------- full numbers

-- Full grouped numbers under ElvUI (12-ui U4): every K/M ElvUI draws goes
-- through E:ShortValue (ElvUI 6.09
-- Core/Math.lua:51, the ENGLISH prefix table the profiles use,
-- EV/Settings/Profile.lua:24) for unit frames, nameplates, tooltips and the
-- databars, so the one shared formatter - the material counts' Econ.Gold
-- (Torment/Economy.lua) - replaces it. ElvUI's files stay untouched, and the
-- replacement is re-applied after E:BuildPrefixValues (ElvUI's Initialize and
-- its number-format option), so a rebuild of the prefix table cannot put the
-- abbreviation back.
local E = unpack(ElvUI)
local elvuiShortValue = E.ShortValue

local function shortValue(_, value)
    local Econ = Diablocraft and Diablocraft.Econ
    if not (Econ and Econ.Gold) then
        -- The formatter rides the Torment addon (## OptionalDeps: Torment);
        -- without it ElvUI's own behaviour stands.
        return elvuiShortValue(E, value)
    end
    -- ElvUI hands over Lua numbers and rounds below 1000 itself (%.0f), so
    -- normalise to a whole number, keep a negative's sign, and let Econ.Gold
    -- do the one grouping rule.
    local number = tonumber(value) or 0
    local sign = number < 0 and "-" or ""
    return sign .. Econ.Gold(math.floor(math.abs(number) + 0.5))
end

local function installShortValue()
    E.ShortValue = shortValue
end

installShortValue()
hooksecurefunc(E, "BuildPrefixValues", installShortValue)

-- ------------------------------------------------------------- power colours

-- ElvUI's unit frames colour a power bar from oUF's colors.power[token] (oUF
-- elements/power.lua, ElvUI 6.09), a table oUF copied from PowerBarColor when
-- ElvUI loaded, before Torment's PowerStrings.lua added the class power tokens.
-- So each generated token gets its entry here too, in oUF's {r, g, b} shape; a
-- token oUF already has (a stock one) keeps ElvUI's own colour.
do
    local colours = E.oUF and E.oUF.colors and E.oUF.colors.power
    for token, power in pairs(colours and Diablocraft and Diablocraft.PowerTokens or {}) do
        if colours[token] == nil then
            colours[token] = {power.r, power.g, power.b}
        end
    end
end
