-- luacheck: globals GameTooltip ItemRefTooltip DCRARITY RED_FONT_COLOR hooksecurefunc unpack
-- An item tooltip's border in the item's rarity colour (05-items I4).
-- dc_tooltip.lua draws a Torment item's name in
-- DCRARITY[rarity] and marks the tooltip with dcGuid; the border reads that name
-- colour back, so the palette stays defined once. A normal (white) item and anything
-- dc_tooltip.lua did not draw (spells, units, stock items) keep the default border.
--
-- ElvUI 6.09 resets every tooltip's border in an OnShow hook (Skins/Blizzard/Tooltip.lua,
-- TT:SetStyle). A hook on the Show method runs after every OnShow script, so ours wins;
-- dc_tooltip.lua's decorate() ends every Torment tooltip with tooltip:Show().
--
-- Primal Ancient (05-items I9) is red whatever the rarity: the stock client's RED_FONT_COLOR
-- (FrameXML Constants.lua, 1/.1/.1). decorate() is to stamp the record's quality_tier on the
-- tooltip as tip.dcQualityTier ("normal" | "ancient" | "primal", nil when the record has none)
-- where it sets dcGuid; until then the rarity colour is all there is.
local function rarityColour(tip)
    if not tip.dcGuid then return end
    if tip.dcQualityTier == "primal" and RED_FONT_COLOR then
        return {RED_FONT_COLOR.r, RED_FONT_COLOR.g, RED_FONT_COLOR.b}
    end
    local palette = DCRARITY
    local title = palette and _G[tip:GetName() .. "TextLeft1"]
    if not title then return end
    local r, g, b = title:GetTextColor()
    for rarity, c in pairs(palette) do
        if rarity ~= "normal" and math.abs(r - c[1]) + math.abs(g - c[2]) + math.abs(b - c[3]) < .03 then return c end
    end
end
local function restore(tip)
    if tip.dcBorder then tip:SetBackdropBorderColor(unpack(tip.dcBorder)); tip.dcBorder = nil end
end
local function paint(tip)
    local c = rarityColour(tip)
    if not c then return restore(tip) end
    -- The default is whatever was there before the first paint: ElvUI's border colour
    -- under ElvUI, the stock tooltip's own without it.
    tip.dcBorder = tip.dcBorder or {tip:GetBackdropBorderColor()}
    tip:SetBackdropBorderColor(c[1], c[2], c[3])
end
for _, name in ipairs({"GameTooltip", "ItemRefTooltip", "ShoppingTooltip1", "ShoppingTooltip2", "ShoppingTooltip3"}) do
    local tip = _G[name]
    if tip then
        hooksecurefunc(tip, "Show", paint)
        tip:HookScript("OnTooltipCleared", restore)
        tip:HookScript("OnHide", restore)
    end
end
-- dc_tooltip.lua forgets the item it drew on GameTooltip and the shopping tips when they
-- clear, but not on ItemRefTooltip, so a stock link shown there after a Torment one still
-- read as Torment (a stock legendary got the orange border). Forget it on every new link
-- and on close; dc_tooltip.lua's renderLink() sets the link first and decorates after.
local function forget(tip) tip.dcGuid, tip.dcNative, tip.dcQualityTier = nil, nil, nil end
if ItemRefTooltip then
    hooksecurefunc(ItemRefTooltip, "SetHyperlink", forget)
    ItemRefTooltip:HookScript("OnHide", forget)
end
