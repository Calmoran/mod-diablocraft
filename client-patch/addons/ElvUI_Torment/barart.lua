-- luacheck: globals ElvUI MAX_PLAYER_LEVEL
-- ElvUI_Torment bar art, the mock HUD bar, and Bar1 slot geometry.
--
-- Two looks, chosen by the `bar` slot in Diablocraft.ART (Torment/SKINNING.md):
--   * empty: the mock HUD. A flat near-black panel fitted to the eight buttons,
--     with a bronze #6b4e2c frame as thick as the half-thickness orb ring,
--     running from the middle of the health orb to the middle of the power orb,
--     carrying the eight well backgrounds, a thin purple XP strip in its top
--     rows and the micro bar spot. No image file.
--   * filled: the slot's own art, with its canvas size, crop and well
--     rectangles. Torment ships its own generated hotbar there; a skin
--     replaces it (the TormentD3 skin carries the D3 bottom bar).
--
-- Either way Bar1's first eight buttons are re-anchored one by one onto the
-- well rectangles, because the wells are two shapes in groups with unequal gaps
-- and one uniform ElvUI size/spacing cannot line up with them. The mockup was
-- drawn to the same wells, so the buttons land in the same places either way.
--
-- The panel's ends follow the two orb rings, and the part of the bar inside an
-- orb is not drawn at all: 3.3.5a has no texture masks, so
-- the shape is filled one 1px row at a time, each row cut back to the ring.
--
-- First in the TOC, before buttonart.lua. Scale and offsets live in the ElvUI
-- profile (`E.db.torment.*`, seeded in options.lua), so the sliders re-size the
-- art and re-run the anchoring; there are no hand-edit constants left.
local E = unpack(ElvUI)
local AB = E:GetModule("ActionBars")

local module = E:NewModule("ElvUI_Torment")

-- Every skin slot this addon reads. Torment owns the table; a skin (TormentD3)
-- fills slots at its own load, and this reads whatever is there.
function module:ArtSlot(name)
    local ART = Diablocraft and Diablocraft.ART
    return ART and ART[name]
end

local WIDTH, HEIGHT = 1416, 201
local CROP = {0, 0.69140625, 0, 0.78515625} -- 1416/2048, 201/256

-- The eight wells measured from the native art, in native pixels, origin
-- top-left (docs/screenshots/bar-wells-measured.png). 1-4 skills, 5-6 mouse,
-- 7 potion, 8 the thin portal. Buttons are anchored to the ART in these pixels
-- times the scale, so they stay in their wells at any scale.
local WELLS = {
    {left = 343, top = 110, width = 69, height = 67},
    {left = 417, top = 110, width = 69, height = 67},
    {left = 491, top = 110, width = 69, height = 67},
    {left = 565, top = 110, width = 69, height = 67},
    {left = 643, top = 110, width = 67, height = 67},
    {left = 716, top = 110, width = 67, height = 67},
    {left = 789, top = 110, width = 69, height = 67},
    {left = 865, top = 110, width = 42, height = 67},
}
local WELL_COUNT = #WELLS

-- The two globe wells measured from the same native art the same way as the
-- slot wells: centre and diameter in native pixels, from
-- client-patch/art/ui/elvui/BottomBar_GameRes.png at the 1416x201 crop. orbs.lua
-- anchors the health orb to `health` and the resource orb to `power`. The mock
-- uses them too: the mockup's orbs sit on the same centres.
local GLOBE_WELLS = {
    health = {centreX = 243, centreY = 100, diameter = 174},
    power  = {centreX = 1179, centreY = 100, diameter = 178},
}

-- The art is a background: BACKGROUND strata sits below every LOW/MEDIUM/HIGH
-- frame, so Bar1's buttons and ElvUI's micro menu (both LOW) draw over it
-- (the micro menu was drawing behind the art). The bar's
-- backdrop is moved to BACKGROUND level 1 in the same pass so a toggled
-- backdrop lands under the art instead of over it.
--
-- One BACKGROUND stack, bottom to top: ElvUI's own panels and Bar1's backdrop
-- (BACKDROP_LEVEL), the orbs (ORB_LEVEL), the art (ART_LEVEL), the XP strip
-- (ART_LEVEL + 1). The art must sit ABOVE the orbs so its ring and the
-- gargoyles cover the liquid. ART_LEVEL clears the orb's
-- whole subtree, which rises one level per child - the orb frame, its
-- ScrollFrame, the scroll child and the overlay, then the values frame, the
-- deepest at ORB_LEVEL + 3 - so a later change to either level cannot flip the
-- order silently. orbs.lua reads both through the getters below.
local ART_STRATA = "BACKGROUND"
local ORB_LEVEL = 2
local ART_LEVEL = ORB_LEVEL + 4
local BACKDROP_LEVEL = 1

-- The XP strip of the D3 art: the recessed channel between the two rails above
-- the wells, measured from the native art (x 329..1095, y 94..104). The bar's
-- own sheet holds the fill sprites - blue segments x 771..1514 y 8..16 are the
-- XP fill, orange segments x 9..752 y 35..43 are the max-level (Paragon) fill -
-- used through these texcoords. Scale and offset follow the art like the buttons.
-- `FILL` is only the empty slot's default: a skin brings its own crops in the
-- bar slot's `fills`, cropped in the sheet the same slot names in
-- `stripTexture` (SKINNING.md). The mock has no sheet: it tints `FLAT`.
local STRIP = {left = 329, top = 94, width = 767, height = 11}
local FILL = {
    blue = {0.37646484375, 0.73974609375, 0.03125, 0.06640625},
    orange = {0.00439453125, 0.36767578125, 0.13671875, 0.171875},
}
-- A 3.3.5a StatusBar carries no texture until SetStatusBarTexture is called
-- (GetStatusBarTexture is nil before it) and a fill with no texture draws
-- nothing, so both looks name one.
local FLAT = "Interface\\Buttons\\WHITE8X8"

-- ------------------------------------------------------------- the mock HUD
--
-- Colours and geometry are the approved mockup's: the bug
-- window's panel look - a near-black panel, a bronze #6b4e2c frame, wells
-- #0a0705 with a 1px bronze edge, the micro spot #1a120b. The XP strip's fill is
-- the mockup's #8a4bd0; the D3 art's paragon-orange has no mock colour, so the
-- mock strip keeps one purple and the skin brings the D3 colours.
local MOCK = {
    panel  = {0.047059, 0.035294, 0.027451, 0.95}, -- #0c0907
    border = {0.419608, 0.305882, 0.172549, 1.00}, -- #6b4e2c
    well   = {0.039216, 0.027451, 0.019608, 1.00}, -- #0a0705
    micro  = {0.101961, 0.070588, 0.043137, 1.00}, -- #1a120b
    xp     = {0.541176, 0.294118, 0.815686, 1.00}, -- #8a4bd0
}
-- The bar is fitted to the eight buttons
-- instead of the mockup's taller box - the wells run 110..177, so the frame's
-- top band, the XP strip and one band of clearance sit above them (96..109) and
-- the bottom band hugs them (177..180). Nothing else is drawn; there is no
-- empty panel left above or below the buttons. `band` is the bronze band of the
-- halved orb ring (orb_ring.blp), so the bar's border is as thick as the ring.
local MOCK_BAR = {left = 243, top = 96, right = 1179, bottom = 181, band = 4}
local MOCK_STRIP = {top = MOCK_BAR.top + MOCK_BAR.band, height = 6}
local MOCK_MICRO = {left = 925, top = 106, width = 140, height = 70, cols = 5, rows = 2, gapX = 5, gapY = 6}
-- The mockup masks the bar 4px outside each orb's outer edge (its box-shadow).
local MOCK_CUT = 4
local BACKDROP = {bgFile = "Interface\\Buttons\\WHITE8X8", edgeFile = "Interface\\Buttons\\WHITE8X8",
                  edgeSize = 1, insets = {left = 1, right = 1, top = 1, bottom = 1}}

local art, artBar, mock, stripArt, deferred

local function setting(key, fallback)
    local db = E.db and E.db.torment
    local value = db and db[key]
    if type(value) == type(fallback) then return value end
    return fallback
end

-- The active bar geometry: the skin's when its slot is filled, the D3 numbers
-- otherwise. The mock's panel is drawn separately; the wells, globe wells and
-- canvas are shared because the mockup was drawn to the same measurements.
local function geometry()
    local slot = module:ArtSlot("bar")
    if slot and slot.path then
        return slot.width or WIDTH, slot.height or HEIGHT, slot.coords or CROP,
               slot.wells or WELLS, slot.globeWells or GLOBE_WELLS, slot.strip or STRIP, slot.fills or FILL
    end
    return WIDTH, HEIGHT, CROP, WELLS, GLOBE_WELLS, STRIP, FILL
end

local function mockBar()
    local slot = module:ArtSlot("bar")
    return not (slot and slot.path)
end

-- ------------------------------------------------------------ the mock panel

-- One row's visible span: the bar rect, cut back to the two rings. A row whose
-- span is empty (fully inside a ring) draws nothing.
local function rowSpan(rect, discs, y)
    local left, right = rect.left, rect.right
    local dy = y + 0.5 - discs.left.cy
    if math.abs(dy) < discs.left.r then
        left = math.max(left, discs.left.cx + math.sqrt(discs.left.r ^ 2 - dy ^ 2))
    end
    dy = y + 0.5 - discs.right.cy
    if math.abs(dy) < discs.right.r then
        right = math.min(right, discs.right.cx - math.sqrt(discs.right.r ^ 2 - dy ^ 2))
    end
    return left, right
end

-- A texture from the frame's own pool, so a rebuild reuses what is there; the
-- caller resets frame.dcUsed first and hides the leftover pool after. `layer`
-- and `sublevel` are CreateTexture's 2nd and 4th arguments: the client promises
-- no draw order between textures in one layer and sublevel, so each mock layer
-- takes one of its own (orbs.lua does the same).
local function take(frame, layer, sublevel)
    frame.dcUsed = (frame.dcUsed or 0) + 1
    local texture = frame.dcPool[frame.dcUsed]
    if not texture then
        texture = frame:CreateTexture(nil, layer, nil, sublevel)
        frame.dcPool[frame.dcUsed] = texture
    end
    texture:Show()
    return texture
end

local function release(frame, layer)
    local used = frame.dcUsed or 0
    for index = used + 1, #frame.dcPool do
        frame.dcPool[index]:Hide()
    end
    frame.dcUsed = 0
end

-- One 1px row of a rect, cut by the rings, tinted `colour`.
local function cutRow(frame, rect, discs, y, colour, layer, sublevel)
    local left, right = rowSpan(rect, discs, y)
    if right - left <= 0 then return end
    local texture = take(frame, layer, sublevel)
    texture:SetTexture(colour[1], colour[2], colour[3], colour[4])
    texture:SetPoint("TOPLEFT", frame, "TOPLEFT", left, -y)
    texture:SetSize(right - left, 1)
end

-- Every row of a rect between two y values, cut by the rings.
local function cutRect(frame, rect, discs, top, bottom, colour, layer, sublevel)
    for y = top, bottom - 1 do
        cutRow(frame, rect, discs, y, colour, layer, sublevel)
    end
end

-- Inset a rect by `band` on every side. The rings are NOT pulled in with it:
-- the mask cuts the whole panel - its bronze band included - at the ring, so a
-- row's bronze edge is the bit of the rect's own border column that the ring
-- has not yet cut away, never a hand-drawn curve.
local function inset(rect, band)
    return {left = rect.left + band, top = rect.top + band, right = rect.right - band, bottom = rect.bottom - band}
end

local function wellRect(well)
    local frame = CreateFrame("Frame", nil, mock)
    frame:SetBackdrop(BACKDROP)
    frame:SetBackdropColor(MOCK.well[1], MOCK.well[2], MOCK.well[3], MOCK.well[4])
    frame:SetBackdropBorderColor(MOCK.border[1], MOCK.border[2], MOCK.border[3], MOCK.border[4])
    frame:SetPoint("TOPLEFT", mock, "TOPLEFT", well.left, -well.top)
    frame:SetSize(well.width, well.height)
    return frame
end

-- The mock HUD's own frame: drawn once in art pixels, then only re-scaled, so
-- a scale change costs one SetScale and never a rebuild.
local function ensureMock()
    if mock then return mock end
    local wells = select(5, geometry())
    mock = CreateFrame("Frame", nil, art)
    mock:SetPoint("TOPLEFT", art, "TOPLEFT", 0, 0)
    mock:SetSize(WIDTH, HEIGHT)
    -- Explicit: the art's own level is applied later in the same pass, and a
    -- frame's level is the one it had when it was created.
    mock:SetFrameLevel(ART_LEVEL)
    mock.dcPool = {}

    local discs = {
        left = {cx = wells.health.centreX, cy = wells.health.centreY, r = wells.health.diameter / 2 + MOCK_CUT},
        right = {cx = wells.power.centreX, cy = wells.power.centreY, r = wells.power.diameter / 2 + MOCK_CUT},
    }

    -- The mock's layers, bottom to top, each with its own ARTWORK sublevel: the
    -- bronze band (0) and the panel (1) on this frame, the XP strip's recess
    -- (0) and under-edge (1) on `stripArt` one frame level above it, and the
    -- strip's own StatusBar above both (xpBar's level). A layer never relies on
    -- the client's order for textures in one layer and sublevel, or on a
    -- child's level following its parent's.
    --
    -- The bronze frame is that band only - the top and bottom rows, then the
    -- two columns between them - never a full rect under the panel: the panel is
    -- the mockup's rgba(12, 9, 7, 0.95) and a bronze rect beneath it would tint
    -- it 5% and keep the world behind it from showing at all.
    local band = MOCK_BAR.band
    local inner = inset(MOCK_BAR, band)
    local top, bottom = MOCK_BAR.top, MOCK_BAR.bottom
    local left, right = MOCK_BAR.left, MOCK_BAR.right
    cutRect(mock, {left = left, top = top, right = right, bottom = top + band},
            discs, top, top + band, MOCK.border, "ARTWORK", 0)
    cutRect(mock, {left = left, top = bottom - band, right = right, bottom = bottom},
            discs, bottom - band, bottom, MOCK.border, "ARTWORK", 0)
    cutRect(mock, {left = left, top = top + band, right = left + band, bottom = bottom - band},
            discs, top + band, bottom - band, MOCK.border, "ARTWORK", 0)
    cutRect(mock, {left = right - band, top = top + band, right = right, bottom = bottom - band},
            discs, top + band, bottom - band, MOCK.border, "ARTWORK", 0)
    cutRect(mock, inner, discs, inner.top, inner.bottom, MOCK.panel, "ARTWORK", 1)

    -- The XP strip's recess and its bronze bottom edge, cut by the rings like
    -- the panel: at these rows the ring is only a pixel or two away from the
    -- panel edge, but the strip is drawn the same way so nothing shows inside a
    -- ring. Its own frame is what keeps the panel's rows from covering it.
    stripArt = CreateFrame("Frame", nil, mock)
    stripArt:SetPoint("TOPLEFT", mock, "TOPLEFT", 0, 0)
    stripArt:SetSize(WIDTH, HEIGHT)
    stripArt:SetFrameLevel(ART_LEVEL + 1)
    stripArt.dcPool = {}
    local strip = {left = inner.left, top = inner.top,
                   right = inner.right, bottom = inner.top + MOCK_STRIP.height}
    cutRect(stripArt, strip, discs, strip.top, strip.bottom, MOCK.well, "ARTWORK", 0)
    cutRect(stripArt, {left = strip.left, top = strip.bottom, right = strip.right, bottom = strip.bottom + 1},
            discs, strip.bottom, strip.bottom + 1, MOCK.border, "ARTWORK", 1)
    release(stripArt, "ARTWORK")

    for index = 1, WELL_COUNT do wellRect(WELLS[index]) end

    -- The micro bar spot: the same 5x2 grid the mockup draws.
    local cellW = (MOCK_MICRO.width - (MOCK_MICRO.cols - 1) * MOCK_MICRO.gapX) / MOCK_MICRO.cols
    local cellH = (MOCK_MICRO.height - (MOCK_MICRO.rows - 1) * MOCK_MICRO.gapY) / MOCK_MICRO.rows
    for row = 0, MOCK_MICRO.rows - 1 do
        for col = 0, MOCK_MICRO.cols - 1 do
            local cell = CreateFrame("Frame", nil, mock)
            cell:SetBackdrop(BACKDROP)
            cell:SetBackdropColor(MOCK.micro[1], MOCK.micro[2], MOCK.micro[3], MOCK.micro[4])
            cell:SetBackdropBorderColor(MOCK.border[1], MOCK.border[2], MOCK.border[3], MOCK.border[4])
            cell:SetPoint("TOPLEFT", mock, "TOPLEFT",
                MOCK_MICRO.left + col * (cellW + MOCK_MICRO.gapX),
                -(MOCK_MICRO.top + row * (cellH + MOCK_MICRO.gapY)))
            cell:SetSize(cellW, cellH)
        end
    end

    release(mock, "ARTWORK")
    return mock
end

-- --------------------------------------------------------------- xp strip

local xpBar

-- The sheet the strip's status bar texture takes: the skin's own (the bar slot's
-- `stripTexture`), else the bar-buttons sheet - the D3 atlas the `fills` crops
-- came from - else the flat sheet the mock tints. See SKINNING.md.
local function xpTexture()
    local slot = module:ArtSlot("bar")
    if not (slot and slot.path) then return FLAT end
    local buttons = module:ArtSlot("bar-buttons")
    return slot.stripTexture or (buttons and buttons.path) or FLAT
end

local function updateXp()
    if not xpBar then return end
    local maximum = UnitXPMax("player") or 0
    if maximum <= 0 then maximum = 1 end
    local current = UnitXP("player") or 0
    -- At max level the stock XP fields are Paragon XP.
    local atMax = UnitLevel("player") >= (MAX_PLAYER_LEVEL or 80)
    xpBar:SetMinMaxValues(0, maximum)
    xpBar:SetValue(current)
    if mockBar() then
        -- The mock strip is one flat colour, the mockup's purple, over the flat
        -- sheet; the D3 art's blue/orange split is the skin's.
        xpBar:SetStatusBarColor(MOCK.xp[1], MOCK.xp[2], MOCK.xp[3], MOCK.xp[4])
        return
    end
    -- The skin's sheet carries the D3 colours itself, so it is never tinted.
    xpBar:SetStatusBarColor(1, 1, 1, 1)
    local texture = xpBar:GetStatusBarTexture()
    if texture then
        -- The crops come with the bar slot (`fills`), not the module's default:
        -- a skin's sheet may hold them anywhere.
        local fills = select(7, geometry())
        local fill = atMax and fills.orange or fills.blue
        texture:SetTexCoord(fill[1], fill[2], fill[3], fill[4])
    end
end

local function stripRect()
    local _, _, _, _, _, strip = geometry()
    if mockBar() then
        -- The strip of the mock: the panel's inner top, one purple fill across
        -- it. Rows between the two rings, so the StatusBar is inset past the
        -- ring's own pixels (the curve is within ~2px over the strip's height).
        local wells = select(5, geometry())
        local left = wells.health.centreX + math.sqrt((wells.health.diameter / 2 + MOCK_CUT) ^ 2
            - (MOCK_STRIP.top + 0.5 - wells.health.centreY) ^ 2) + 1.5
        local right = wells.power.centreX - math.sqrt((wells.power.diameter / 2 + MOCK_CUT) ^ 2
            - (MOCK_STRIP.top + 0.5 - wells.power.centreY) ^ 2) - 1.5
        return left, MOCK_STRIP.top, right - left, MOCK_STRIP.height
    end
    return strip.left, strip.top, strip.width, strip.height
end

local function ensureXpBar()
    if xpBar then return xpBar end
    xpBar = CreateFrame("StatusBar", nil, art)
    xpBar:SetFrameStrata(ART_STRATA)
    -- Above the mock's panel (ART_LEVEL) and its strip band (ART_LEVEL + 1): the
    -- fill is never covered by the art it sits in.
    xpBar:SetFrameLevel(ART_LEVEL + 2)
    -- Without this the strip draws nothing at all, in either look.
    xpBar:SetStatusBarTexture(xpTexture())
    xpBar:SetMinMaxValues(0, 1)
    xpBar:SetValue(0)
    xpBar:EnableMouse(true)
    xpBar:SetScript("OnEnter", function(self)
        local current = UnitXP("player") or 0
        local maximum = UnitXPMax("player") or 0
        local percent = maximum > 0 and math.floor(current / maximum * 100 + 0.5) or 0
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine(("%d / %d XP (%d%%)"):format(current, maximum, percent))
        GameTooltip:Show()
    end)
    xpBar:SetScript("OnLeave", function() GameTooltip:Hide() end)
    return xpBar
end

-- ---------------------------------------------------------------- the art

local function ensureArt(bar)
    if art and artBar == bar then return end
    -- Rebuild against the current bar rather than keep a stale child if the bar
    -- is ever re-created: a parented frame dies with its parent.
    art, artBar = CreateFrame("Frame", nil, bar), bar
    mock, stripArt, xpBar = nil, nil, nil
    local texture = art:CreateTexture(nil, "ARTWORK")
    texture:SetAllPoints(art)
    art.texture = texture
end

-- Draw the bar's own art: the skin's texture, or the mock panel. The mock is
-- drawn once in art pixels inside its own frame and only re-scaled, so this is
-- cheap to run on every geometry pass.
local function applyBarLook()
    local slot = module:ArtSlot("bar")
    if slot and slot.path then
        if mock then mock:Hide() end
        art.texture:Show()
        art.texture:SetTexture(slot.path)
        local coords = slot.coords or CROP
        art.texture:SetTexCoord(coords[1], coords[2], coords[3], coords[4])
    else
        art.texture:Hide()
        ensureMock()
        mock:Show()
    end
    -- The strip's sheet follows the look: a skin's own sheet, or the flat sheet
    -- the mock tints (a skin loading over a running mock must not keep the flat
    -- one, and vice versa).
    if xpBar then xpBar:SetStatusBarTexture(xpTexture()) end
end

-- The mock's micro bar spot. ElvUI lays the micro buttons out from
-- the micro bar's own top-left (ElvUI 6.09 Modules/ActionBars/MicroBar.lua,
-- UpdateMicroPositionDimensions), so anchoring that frame puts them in the
-- spot; without the mock (a skin's bar art) they are left where ElvUI puts
-- them. ElvUI_MicroBar is not a protected frame, and this pass never runs in
-- combat, so the anchor is safe. Wherever ElvUI or its mover put it, the next
-- geometry pass re-anchors it, the same way Bar1 itself is anchored.
--
-- A skin whose bar slot names a `micro` opening (the shipped hotbar) gets
-- the micro bar centred in it, shrunk to fit if ElvUI's
-- button size makes it bigger: the bar's size is the profile's, the opening's
-- is the art's. A frame's SetPoint offsets are in its own scale, hence `/ fit`.
local function anchorMicroBar(scale)
    local micro = _G.ElvUI_MicroBar
    if not micro then return end
    local slot = module:ArtSlot("bar")
    local spot = slot and slot.path and slot.micro
    if spot then
        local width, height = micro:GetWidth(), micro:GetHeight()
        local fit = 1
        if width > 0 and height > 0 then
            fit = math.min(1, spot.width * scale / width, spot.height * scale / height)
        end
        micro:SetScale(fit)
        micro:ClearAllPoints()
        micro:SetPoint("CENTER", art, "TOPLEFT", (spot.left + spot.width / 2) * scale / fit,
            -(spot.top + spot.height / 2) * scale / fit)
        return
    end
    if not mockBar() then return end
    micro:SetScale(1)
    micro:ClearAllPoints()
    micro:SetPoint("TOPLEFT", art, "TOPLEFT", MOCK_MICRO.left * scale, -MOCK_MICRO.top * scale)
end

-- One pass that re-sizes the art and the bar to the art and re-anchors buttons
-- 1-8. Called after every ElvUI layout and by the options sliders.
local function ApplyGeometry()
    -- Defender-in-depth: anchors on secure frames are refused in combat, so
    -- never run this pass there, whatever called it.
    if InCombatLockdown() then
        deferred = true
        return
    end
    -- The rift tracker's Objective Frame scale (dc_riftbar.lua, the AIO client half) rides
    -- this pass: the options slider writes E.db.torment.objectiveScale and this hands it
    -- over. It needs no bar, so it comes before the bar check; a client whose script has
    -- not loaded yet keeps its own 1.25 default, and the tracker reads the saved value
    -- itself at load.
    local scale_ = setting("objectiveScale", 1.25)
    local tracker = _G.DCRiftTracker
    if tracker and tracker.SetScale then tracker.SetScale(scale_) end
    local bar = AB and AB.handledBars and AB.handledBars.bar1
    if not bar then return end

    local scale = setting("bar1Scale", 1)
    local offsetX = setting("bar1OffsetX", 0)
    local offsetY = setting("bar1OffsetY", 0)
    ensureArt(bar)
    applyBarLook()

    local width, height, _, wells = geometry()
    art:ClearAllPoints()
    art:SetPoint("CENTER", bar, "CENTER", offsetX, offsetY)
    art:SetSize(width * scale, height * scale)
    art:SetFrameStrata(ART_STRATA)
    art:SetFrameLevel(ART_LEVEL)
    if mock and mock:IsShown() then mock:SetScale(scale) end

    -- ElvUI's bar backdrop inherits the bar's LOW strata and would draw over a
    -- BACKGROUND art; put it just under the art.
    if bar.backdrop then
        bar.backdrop:SetFrameStrata(ART_STRATA)
        bar.backdrop:SetFrameLevel(BACKDROP_LEVEL)
    end

    -- Size the bar to the art so the mover's outline is the art, not ElvUI's
    -- empty grid. The mover resizes from the bar's OnSizeChanged (Movers.lua).
    bar:SetSize(width * scale, height * scale)

    -- XP strip, on the art in BACKGROUND above it and following the art's scale
    -- and offsets like the buttons.
    local xp = ensureXpBar()
    if setting("xpBar", true) then
        local left, top, stripWidth, stripHeight = stripRect()
        xp:Show()
        xp:ClearAllPoints()
        xp:SetPoint("TOPLEFT", art, "TOPLEFT", left * scale, -top * scale)
        xp:SetSize(stripWidth * scale, stripHeight * scale)
        updateXp()
    else
        xp:Hide()
    end

    -- Buttons 1-8 follow the wells; buttons above 8 are left where ElvUI puts
    -- them. Action buttons are secure frames, so this only ever runs out of
    -- combat (see Apply).
    for index = 1, WELL_COUNT do
        local button = bar.buttons and bar.buttons[index]
        local well = wells[index]
        if button and well then
            button:ClearAllPoints()
            button:SetPoint("TOPLEFT", art, "TOPLEFT", well.left * scale, -well.top * scale)
            button:SetSize(well.width * scale, well.height * scale)
        end
    end

    -- Icons are cropped and filled from buttonart.lua only now that the final
    -- geometry exists; fitting earlier would use ElvUI's still-square size.
    local moduleRef = E:GetModule("ElvUI_Torment")
    if moduleRef and moduleRef.StyleButtons then moduleRef:StyleButtons() end
    anchorMicroBar(scale)
    -- Orbs follow the same pass: plain frames, so this is safe whenever the art
    -- geometry is (the caller already refused combat).
    if module and module.LayoutOrbs then module:LayoutOrbs() end
    -- The castbar-only pass rides the same deferral: the options toggle and a
    -- profile change both end up here, and castbar.lua refuses combat itself.
    if module and module.ApplyCastbarOnly then module:ApplyCastbarOnly() end
end

-- Anchor changes on secure frames are refused in combat, so a layout that lands
-- mid-fight is queued and applied on PLAYER_REGEN_ENABLED, the same deferral
-- ElvUI's own ActionBars uses.
local function Apply()
    if InCombatLockdown() then
        deferred = true
        return
    end
    ApplyGeometry()
end

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("PLAYER_REGEN_ENABLED")
watcher:RegisterEvent("PLAYER_XP_UPDATE")
watcher:RegisterEvent("PLAYER_LEVEL_UP")
watcher:SetScript("OnEvent", function(_, event)
    -- XP and level events never move a protected frame: they only refresh the
    -- strip, so a mid-fight XP tick cannot run the anchor pass. The queued
    -- geometry is flushed only on PLAYER_REGEN_ENABLED, out of combat.
    if event == "PLAYER_REGEN_ENABLED" and deferred and not InCombatLockdown() then
        deferred = nil
        ApplyGeometry()
    end
    updateXp()
end)

-- The art frame, the bar it is drawn on, and the BACKGROUND layers, read by
-- orbs.lua: the orbs are siblings of the art on the art's own strata, below it.
function module:GetArt() return art end
function module:GetArtBar() return artBar end
function module:GetArtStrata() return ART_STRATA end
function module:GetOrbLevel() return ORB_LEVEL end
function module:GetGlobeWells() return select(5, geometry()) end
-- True while no skin fills the bar slot: the mock HUD draws, and orbs.lua draws
-- the mock ring (a skin's bar art brings its own rings).
function module:IsMock() return mockBar() end

-- The options sliders call this after writing E.db.torment.
function module:Apply()
    Apply()
end

function module:Initialize()
    if AB and AB.PositionAndSizeBar then
        -- PositionAndSizeBar is the update that sizes the bar and lays out its
        -- buttons; hooking it (rather than polling) covers Initialize, profile
        -- change and UIScale change.
        hooksecurefunc(AB, "PositionAndSizeBar", function(_, barName)
            if barName == "bar1" then Apply() end
        end)
    end
    Apply()
end

-- E:RegisterModule defers this module's Initialize to E:InitializeModules()
-- inside E:Initialize() (Core/Core.lua). ActionBars registers its module before
-- this addon loads, so Bar1 exists by the time Initialize runs.
E:RegisterModule("ElvUI_Torment")
