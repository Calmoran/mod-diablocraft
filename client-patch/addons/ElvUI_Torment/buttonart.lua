-- luacheck: globals ElvUI
-- ElvUI_Torment button art. Listed after
-- barart.lua, before options.lua.
--
-- The measured wells: 1-4 skills, 5-6 mouse, 7 potion,
-- 8 the thin portal.
--
--   * Buttons 1-7: the well rectangles ARE their frames. ElvUI's own button
--     backdrop/border is hidden and the icon fills the well with no inset,
--     cropped to the well's aspect so it is cut, not squashed. ElvUI's own
--     hover/pushed highlights are kept. NO sprite touches these seven.
--   * Button 8 (portal): the D3 portal sprite is the whole button - normal
--     sprite 33, highlight sprite 34, and sprite 32 while the action is out of
--     range or unusable - so the game's icon is hidden there. The sprite and
--     the sheet it comes from are the `bar-buttons` slot (SKINNING.md); without
--     it (the mock HUD) button 8 is an ordinary well like the other seven.
--   * Micro menu: NOT skinned. Sprites 1-17 and 19-31 and the micro panel are
--     catalogued only (docs/screenshots/bar-sprites-catalogued.png); skinning
--     ElvUI's micro bar is a later task.
--
-- Lifecycle (why this hooks LibActionButton, not only ActionBars): Bar1's
-- buttons are LibActionButton objects. `AB:StyleButton` runs during ElvUI's
-- layout, before our geometry pass, and LAB's own `Update` later replaces the
-- normal texture on every action/page change (`SetNormalTexture` at the end of
-- Update). So the portal sprite is applied from LAB's own fired callbacks -
-- `OnButtonUpdate` (after Update) and `OnButtonUsable` (after the usable tint) -
-- which are the supported lifecycle hooks. `UpdateUsable` only tints the icon
-- and never disables the button, so sprite 32 is selected by us from
-- `outOfRange` / `IsUsable()`, not by `SetDisabledTexture`. Nothing about the
-- secure action behaviour is changed, only textures.
--
-- The icon fit is geometry: it runs from ElvUI_Torment:StyleButtons() after
-- barart has anchored and sized the buttons, using SetAllPoints (no E.Border
-- inset) so the icon fills the well.
--
-- Keying the portal sprite backing: the sheet's button band is opaque, and the
-- portal sprites carry a dark backing (red-brown for 33, gold for 34, grey for
-- 32) around the blue swirl. Alpha cannot remove it, so the sprites are drawn
-- with SetBlendMode("ADD"): black adds nothing to the bar art underneath, and
-- the dark backing adds only a faint tint while the bright portal and its border
-- add fully. No replacement sprite is invented; it is the D3 sprite, keyed by
-- blend mode. (The optional locked panel sprite 35 is near-black, so ADD would
-- make it invisible; skipped and reported, not forced.)
local E = unpack(ElvUI)
local AB = E:GetModule("ActionBars")
local LAB = E.Libs.LAB
local module = E:GetModule("ElvUI_Torment")

local PORTAL_INDEX = 8

local function bar1Button(index)
    local bar = AB and AB.handledBars and AB.handledBars.bar1
    return bar and bar.buttons and bar.buttons[index]
end

local function bar1Index(button)
    if not button then return nil end
    for index = 1, PORTAL_INDEX do
        if bar1Button(index) == button then return index end
    end
end

-- Crop the icon texture to the button's own aspect so a non-square well cuts the
-- icon rather than squashing it, and fill the whole well: SetAllPoints, not
-- SetInside, whose default E.Border inset would leave a ring of bar art.
-- Icon inset in native pixels, scaled with the bar: the icon sits inside the
-- well so a frame sprite can sit over the well edge.
-- 2 is an INTERIM TUNABLE, not a measured/sourced D3 icon inset; the true
-- inset is the missing frame sprite's border and is unknown.
local function iconInset()
    local db = E.db and E.db.torment
    local value = db and db.iconInset
    if type(value) ~= "number" then value = 2 end
    local scale = db and db.bar1Scale
    if type(scale) ~= "number" then scale = 1 end
    return value * scale
end

local function fitIcon(button, icon)
    local edge = iconInset()
    local width, height = button:GetWidth() - 2 * edge, button:GetHeight() - 2 * edge
    if not width or not height or width <= 0 or height <= 0 then return end
    local left, right, top, bottom = 0.07, 0.93, 0.07, 0.93
    local aspect = width / height
    if aspect < 1 then
        local half = 0.43 * aspect
        left, right = 0.5 - half, 0.5 + half
    elseif aspect > 1 then
        local half = 0.43 / aspect
        top, bottom = 0.5 - half, 0.5 + half
    end
    icon:ClearAllPoints()
    icon:SetPoint("TOPLEFT", button, "TOPLEFT", edge, -edge)
    icon:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -edge, edge)
    icon:SetTexCoord(left, right, top, bottom)
    -- The cooldown swipe follows the icon so nothing overlaps the inset frame.
    local name = button:GetName()
    local cooldown = name and _G[name .. "Cooldown"]
    if cooldown then
        cooldown:ClearAllPoints()
        cooldown:SetAllPoints(icon)
    end
end

local function hideElvUIBackdrop(button)
    if button.backdrop then button.backdrop:Hide() end
    local name = button:GetName()
    local border = name and _G[name .. "Border"]
    if border then border:Hide() end
end

local function setSprite(button, kind, sheet, coords)
    local setter = button["Set" .. kind .. "Texture"]
    if not setter then return end
    setter(button, sheet)
    local getter = button["Get" .. kind .. "Texture"]
    local texture = getter and getter(button)
    if not texture then return end
    texture:SetTexCoord(coords[1], coords[2], coords[3], coords[4])
    texture:SetBlendMode("ADD")
    texture:SetAllPoints(button)
    texture:Show()
    texture:SetAlpha(1)
end

local function portalSprite(button, slot)
    local unusable = button.outOfRange or (button.IsUsable and not button:IsUsable())
    local portal = slot.portal
    setSprite(button, "Normal", slot.path, unusable and portal.disabled or portal.normal)
    setSprite(button, "Highlight", slot.path, portal.highlight)
    setSprite(button, "Pushed", slot.path, portal.highlight)
end

-- A drag that starts on a skill well (1-6) is reported when it ends, wherever the
-- cursor is, to module.OnWellDrag(slot) if the skills window has set it
-- (dc_skillbar.lua moves or swaps the skill). Hooked once per button, after the
-- native script; ElvUI's own drag is left alone.
local function hookDrag(button, index)
    if button.tormentDragHooked or index > PORTAL_INDEX - 2 then return end
    button.tormentDragHooked = true
    button:HookScript("OnDragStop", function()
        if module.OnWellDrag then module.OnWellDrag(index - 1) end
    end)
end

local function styleOne(button, index)
    if not button then return end
    hookDrag(button, index)
    hideElvUIBackdrop(button)
    local name = button:GetName()
    local icon = name and _G[name .. "Icon"]
    local slot = module:ArtSlot("bar-buttons")
    if index == PORTAL_INDEX and slot and slot.path then
        if icon then icon:Hide() end
        portalSprite(button, slot)
    elseif icon then
        icon:Show()
        fitIcon(button, icon)
    end
end

-- Called by barart after it has anchored and sized the buttons, so the fit uses
-- the final well geometry (not ElvUI's still-square layout dimensions).
local function styleAll()
    for index = 1, PORTAL_INDEX do
        styleOne(bar1Button(index), index)
    end
end

if module then
    module.StyleButtons = styleAll
end

-- The action-bar well the cursor is over, as a skill slot, or nil. Wells 1..6 are
-- the six skill slots (0..5) and this addon draws them, so the skills window
-- (dc_skillbar.lua) asks this when a skill is dropped onto the bar instead of
-- re-deriving Bar1's geometry itself.
-- The potion and portal wells (7, 8) are not skill slots and return nil.
function module.BarSlotUnderMouse()
    for index = 1, PORTAL_INDEX - 2 do
        local button = bar1Button(index)
        if button and button:IsMouseOver() then return index - 1 end
    end
end

-- Supported lifecycle: LAB fires these after its own texture work.
LAB:RegisterCallback("OnButtonUpdate", function(_, button)
    local index = bar1Index(button)
    if index == PORTAL_INDEX then styleOne(button, index) end
end)
LAB:RegisterCallback("OnButtonUsable", function(_, button)
    local index = bar1Index(button)
    if index == PORTAL_INDEX then styleOne(button, index) end
end)

-- Re-applied whenever ElvUI restyles a button (Initialize, profile change,
-- UpdateButtonSettings). Only Bar1's first eight buttons are touched.
hooksecurefunc(AB, "StyleButton", function(_, button)
    local index = bar1Index(button)
    if index then styleOne(button, index) end
end)
