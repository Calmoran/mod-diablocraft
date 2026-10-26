-- luacheck: globals ElvUI PowerBarColor floor sin UnitIsDeadOrGhost UnitPowerType UnitHealth UnitHealthMax UnitPower UnitPowerMax
-- luacheck: globals Diablocraft UnitClass
-- ElvUI_Torment health and resource orbs.
--
-- The fill comes from a slot in Diablocraft.ART (Torment/SKINNING.md):
-- `orb-health` and `orb-resource-<key>` for the liquid, `orb-back`,
-- `orb-gloss`, `orb-spark`, `orb-lowhp-glow` and `orb-skull` for the D3
-- cosmetics. With no skin the slot is empty and the mock HUD draws: a bronze
-- ring with a thin gold inner edge over 60% dark glass (the approved mockup),
-- filled by the delivered orb sheets, or by a plain disc tinted per resource
-- where no sheet exists yet. The TormentD3 skin fills every slot with the D3
-- art, which is exactly the picture this drew before the slots existed.
--
-- Values are read from the player unit events on plain frames, not through
-- ElvUF: these are our own frames, so a direct listener is simpler than an oUF
-- element. On 3.3.5 the power events are the per-power ones (UNIT_MANA,
-- UNIT_RAGE, UNIT_FOCUS, UNIT_ENERGY, UNIT_HAPPINESS, UNIT_RUNIC_POWER and
-- their UNIT_MAX* twins), not a generic UNIT_POWER (Blizzard FrameXML
-- UnitFrame.lua:299-310, 330-338). Current draws on top, max below.
--
-- The resource orb follows the power TOKEN: the rebuilt client reports a class's
-- own token (FURY, WRATH, ...), which names its fill directly; the stock client
-- still reports the slot's (RAGE, ENERGY, ...), which the generated
-- Diablocraft.ResourceNames turns into the class's token. Every power's fill is
-- the same orb art in its own colour (orb_fill_<token>_1/_2). A class with a
-- second power (role "second" in the generated list) gets ONE orb split down
-- the middle: the displayed power on the left half, the second on the right,
-- each with its own fill and its own maximum, D3's two-power globe.
--
-- Layout and appearance are separate: LayoutOrbs (called from barart's
-- combat-deferred ApplyGeometry) sets size and anchors; a power change only
-- swaps the fill slot and re-reads the value, so nudges and the combat
-- deferral path are never bypassed by an event.
local E = unpack(ElvUI)
local module = E:GetModule("ElvUI_Torment")

local MEDIA = "Interface\\AddOns\\ElvUI_Torment\\media\\"
-- How far inside the orb edge a skin's globe sits, as a fraction of orb width
-- (the D3 art's own inset; TormentD3 keeps its current picture with it unchanged).
local INSET = 0.06
-- Blizzard packs the art untinted; a slot's globe carries its own colours.
local TINT = {r = 1, g = 1, b = 1}

-- The mock ring (client-patch/art/ui/elvui/orb_ring.png): the bronze band, the
-- thin gold inner edge, the dark glass and a 4px drop shadow, inside a circle
-- that is 164/174 of the orb across (the half-thickness ring). It is drawn
-- 91/87 of the orb's size, so the ring's outer
-- edge lands on the orb's own edge and the shadow fills the gap up to the bar's
-- cut. A mock fill's 160px disc is scaled to fill the glass circle, so the
-- liquid meets the ring at every orb size. Both fractions must equal
-- mock_hud_art.py's RING_OVER/RING_INNER.
local MOCK_RING = MEDIA .. "orb_ring"
local MOCK_RING_OVER = 91 / 87
local MOCK_RING_INNER = 164 / 174
-- The mock fill sheets, the delivered art:
-- 60 frames over two 30-cell sheets each (1024x1024, 6 columns x 5 rows of
-- 170x170 cells, a 160px disc). The orb plays sheet 1 then sheet 2 and loops.
local MOCK_FILL = {frames = 60, width = 1024, height = 1024, cellW = 170, cellH = 170, cols = 6, disc = 160}
-- Health's sheet and one per power token in the generated Diablocraft.PowerTokens,
-- named by the token in lower case (orb_fill_fury, orb_fill_wrath, ...). A
-- token the list does not carry has no sheet, and the orb says so (below).
local function mockFill(name)
    return {path = MEDIA .. "orb_fill_" .. name .. "_1",
            path2 = MEDIA .. "orb_fill_" .. name .. "_2",
            frames = MOCK_FILL.frames,
            width = MOCK_FILL.width, height = MOCK_FILL.height,
            cellW = MOCK_FILL.cellW, cellH = MOCK_FILL.cellH,
            cols = MOCK_FILL.cols, disc = MOCK_FILL.disc}
end
local MOCK_FILLS = {health = mockFill("health")}
local function shippedFill(key)
    local tokens = Diablocraft and Diablocraft.PowerTokens
    if not MOCK_FILLS[key] and tokens and tokens[key:upper()] then
        MOCK_FILLS[key] = mockFill(key)
    end
    return MOCK_FILLS[key]
end
-- The stand-in for a resource with no sheet yet: one white disc, tinted.
local DISC = {path = MEDIA .. "orb_disc", frames = 1, width = 256, height = 256,
              cellW = 256, cellH = 256, cols = 1, disc = 256}

-- Exact 3.3.5 power events (FrameXML UnitFrame.lua:299-310, 330-338).
local POWER_EVENTS = {"UNIT_MANA", "UNIT_RAGE", "UNIT_FOCUS", "UNIT_ENERGY", "UNIT_HAPPINESS", "UNIT_RUNIC_POWER"}
local POWER_MAX_EVENTS = {"UNIT_MAXMANA", "UNIT_MAXRAGE", "UNIT_MAXFOCUS", "UNIT_MAXENERGY",
                          "UNIT_MAXHAPPINESS", "UNIT_MAXRUNIC_POWER"}

local healthOrb, powerOrb
local warned = {}

local function setting(key, fallback)
    local db = E.db and E.db.torment
    local value = db and db[key]
    if type(value) == type(fallback) then return value end
    return fallback
end

-- ---------------------------------------------------------------- fill slots

-- The texcoord of frame `index` in a globe or fill sheet, half a texel in on
-- every side so bilinear filtering never samples the neighbouring cell.
local function globeCell(slot, index)
    local col, row = index % slot.cols, floor(index / slot.cols)
    local x, y = col * slot.cellW, row * slot.cellH
    local hx, hy = 0.5 / slot.width, 0.5 / slot.height
    return x / slot.width + hx, (x + slot.cellW) / slot.width - hx,
           y / slot.height + hy, (y + slot.cellH) / slot.height - hy
end

-- Frame index -> its sheet and the cell inside it. A slot with `path2` is two
-- sheets of frames/2 cells each (the mock fills: 60 frames, 30 + 30); without it
-- one sheet holds them all (the D3 globes: 60 in one).
local function globeSheet(slot, index)
    if not slot.path2 then return slot.path, index end
    local per = floor(slot.frames / 2)
    if index < per then return slot.path, index end
    return slot.path2, index - per
end

-- How big the sheet is drawn so the disc inside it is `orb.size` scaled to the
-- ring's inner circle. A slot without `disc` is a skin's globe whose cell IS the
-- globe, which sits at the D3 art's own inset.
local function fillSize(orb, slot)
    if slot and slot.disc then
        return orb.size * MOCK_RING_INNER * (slot.cellW / slot.disc)
    end
    return orb.size * (1 - 2 * INSET)
end

-- ---------------------------------------------------------------- orb drawing

-- Appearance only: swap the fill slot and re-point the liquid and its glow.
-- Never anchored here, so a power switch cannot move the orb or bypass layout.
local function pointLayers(orb, layers, scrollChild, slot)
    for _, layer in ipairs(layers) do
        layer:SetTexture(slot and slot.path or nil)
        layer.dcSheet = slot and slot.path or nil
        if orb.size and slot then
            local inset = (orb.size - fillSize(orb, slot)) / 2
            layer:ClearAllPoints()
            layer:SetPoint("TOPLEFT", scrollChild, "TOPLEFT", inset, -inset)
            layer:SetPoint("BOTTOMRIGHT", scrollChild, "BOTTOMRIGHT", -inset, inset)
        end
    end
end

local function setGlobe(orb, slot)
    orb.globe = slot
    orb.globeSheet = nil
    -- The added light is the D3 health sheet's own: a slot
    -- asks for it with `glow`, and no other globe is lit.
    if slot and slot.glow then orb.glow:Show() else orb.glow:Hide() end
    pointLayers(orb, orb.globeLayers, orb.scrollChild, slot)
end

-- The second power's half: its fill, or nil to draw the orb whole again.
local function setHalf(orb, slot)
    local half = orb.half
    if not half then return end
    half.globe = slot
    if slot then
        half.scrollChild:SetSize(orb.size or 0, orb.size or 0)
        pointLayers(orb, half.layers, half.scrollChild, slot)
        half.scrollFrame:Show()
        orb.divider:Show()
    else
        half.scrollFrame:Hide()
        orb.divider:Hide()
    end
end

-- Show one cell of a sheet on a set of layers, swapping the sheet only when the
-- cell moves to the other one.
local function showCell(layers, slot, frame)
    local path, index = globeSheet(slot, frame % slot.frames)
    for _, layer in ipairs(layers) do
        if layer.dcSheet ~= path then
            layer.dcSheet = path
            layer:SetTexture(path)
        end
        layer:SetTexCoord(globeCell(slot, index))
    end
end

-- Crop a ScrollFrame to `width` from the orb's left (`x` 0) or its middle, and
-- to `fraction` of its height from the bottom; the scroll child is the whole
-- orb, so the disc never squashes and each half shows its own side of it.
local function crop(orb, scrollFrame, fraction, x, width)
    local height = orb.size * fraction
    scrollFrame:ClearAllPoints()
    scrollFrame:SetPoint("BOTTOMLEFT", orb, "BOTTOMLEFT", x, 0)
    scrollFrame:SetWidth(width)
    scrollFrame:SetHeight(math.max(height, 0.001))
    scrollFrame:SetVerticalScroll(orb.size - height)
    scrollFrame:SetHorizontalScroll(x)
end

-- The visible cell is only picked here; the ScrollFrame below crops the
-- full-size texture from the top, so the disc can never squash as it drains and
-- a half-full orb still animates.
local function draw(orb, fraction)
    local slot = orb.globe
    if not slot then return end
    showCell(orb.globeLayers, slot, orb.globeFrame or 0)
    if not orb.scrollFrame then return end
    local half = orb.half and orb.half.globe and orb.half
    crop(orb, orb.scrollFrame, fraction, 0, half and orb.size / 2 or orb.size)
    if orb.scrollChild then orb.scrollChild:SetAlpha(fraction > 0 and 1 or 0) end
    if half then
        showCell(half.layers, half.globe, orb.globeFrame or 0)
        crop(orb, half.scrollFrame, half.fraction or 0, orb.size / 2, orb.size / 2)
        half.scrollChild:SetAlpha((half.fraction or 0) > 0 and 1 or 0)
    end
    -- The spark is a skin's swirl across the whole liquid's top, so a split orb,
    -- whose halves stand at two heights, has none.
    if not orb.hasSpark or half then
        orb.spark:Hide()
        return
    end
    -- pi is NOT a client global in 3.3.5 (pinned FrameXML never uses it); it is
    -- math.pi. floor/sin are client globals (FrameXML uses them bare).
    local multiplier = floor(sin(fraction * math.pi) * 1000) / 1000
    if multiplier <= 0.25 then
        orb.spark:Hide()
    else
        orb.spark:SetWidth(orb.size * multiplier)
        orb.spark:SetHeight(32 * orb.size / 256 * multiplier)
        orb.spark:ClearAllPoints()
        orb.spark:SetPoint("TOP", orb.scrollFrame, "TOP", 0, 16 * orb.size / 256 * multiplier)
        orb.spark:Show()
    end
end

local function fractionOf(current, maximum)
    if maximum > 0 then return math.max(0, math.min(1, current / maximum)) end
    return 0
end

-- The second power's own value and maximum, for the right half and its numbers.
local function updateHalf(orb, current, maximum)
    local half = orb.half
    if not half then return end
    half.current, half.maximum = current or 0, maximum or 0
    half.fraction = fractionOf(half.current, half.maximum)
    local show = half.globe and setting("orbText", true)
    orb.values.top2:SetText(show and tostring(half.current) or "")
    orb.values.bottom2:SetText(show and tostring(half.maximum) or "")
end

local function update(orb, current, maximum)
    orb.current, orb.maximum = current or 0, maximum or 0
    local fraction = fractionOf(orb.current, orb.maximum)
    if orb.kind == "HEALTH" then
        -- Low-health glow is static: it keeps Roth's sourced Show/Hide, and
        -- "pulses" is unsourced. No pulse
        -- and no invented timing here; a future sourced D3 pulse becomes a
        -- tunable at that point.
        local dead = UnitIsDeadOrGhost("player")
        if orb.hasLowHP and (fraction <= 0.25 or dead) then orb.lowHP:Show() else orb.lowHP:Hide() end
        if orb.hasSkull and dead then orb.skull:Show() else orb.skull:Hide() end
    end
    -- One shared toggle for both orbs' number displays; applied live because the
    -- options setter calls module:Apply -> LayoutOrbs -> update.
    if setting("orbText", true) then
        orb.values.top:SetText(tostring(orb.current))
        orb.values.bottom:SetText(tostring(orb.maximum))
    else
        orb.values.top:SetText("")
        orb.values.bottom:SetText("")
    end
    draw(orb, fraction)
end

-- A plain texture on the scroll child, so the ScrollFrame clips it; the sheet
-- is always full size and only its cell changes each tick.
local function createOrb(kind)
    -- A sibling of the art on the bar, not a child of it. Two frames sharing a
    -- parent order by plain level - the pair the addon already proves live (the
    -- bar backdrop at level 1 under the art) - whereas a child's own frame level
    -- is not reliable to put it behind its parent on the 3.3.5 client, whose
    -- frame levels were auto-adjusted until 7.0.3. The orb sits on the art's
    -- strata at ORB_LEVEL; its child frames inherit the strata and rise one
    -- level each, all still under ART_LEVEL.
    local orb = CreateFrame("Frame", nil, module:GetArtBar())
    orb.kind = kind
    orb:SetFrameStrata(module:GetArtStrata())
    orb:SetFrameLevel(module:GetOrbLevel())
    orb.globeFrame, orb.globeElapsed = 0, 0
    -- Known values before the first event, so the ticker never redraws nil.
    orb.current, orb.maximum = 0, 0

    local scrollFrame = CreateFrame("ScrollFrame", nil, orb)
    scrollFrame:SetPoint("BOTTOM")
    local scrollChild = CreateFrame("Frame", nil, scrollFrame)
    scrollFrame:SetScrollChild(scrollChild)
    orb.scrollFrame, orb.scrollChild = scrollFrame, scrollChild

    -- The backing, under the liquid: the mock's ring and dark glass, or a
    -- skin's own orb-back plate. Faked off a texture of its own so switching
    -- looks never leaves the other one showing.
    orb.back = orb:CreateTexture(nil, "BACKGROUND", nil, -6)
    orb.back:SetAllPoints(orb)

    orb.liquid = scrollChild:CreateTexture(nil, "ARTWORK", nil, -1)
    orb.liquid:SetVertexColor(TINT.r, TINT.g, TINT.b)

    -- The D3 health sheet's own flat light: a second ADD pass of the same cell.
    -- Only a slot that asks for it (`glow`) shows it, and it sits beside the
    -- liquid on the scroll child so the fill crop clips both.
    orb.glow = scrollChild:CreateTexture(nil, "ARTWORK")
    orb.glow:SetBlendMode("ADD")
    orb.glow:SetVertexColor(TINT.r, TINT.g, TINT.b)
    orb.globeLayers = {orb.liquid, orb.glow}

    local overlay = CreateFrame("Frame", nil, scrollFrame)
    overlay:SetAllPoints(orb)
    orb.overlay = overlay

    -- The D3 cosmetics, all driven by their slots and hidden without one: the
    -- swirl spark, the glass gloss, and for health the death skull and the
    -- static low-health glow.
    orb.spark = overlay:CreateTexture(nil, "BACKGROUND", nil, -3)
    orb.spark:SetBlendMode("ADD")
    orb.spark:Hide()
    if kind == "HEALTH" then
        orb.skull = overlay:CreateTexture(nil, "BACKGROUND", nil, 1)
        orb.skull:SetPoint("CENTER", 0, 0)
        orb.skull:SetBlendMode("ADD")
        orb.skull:SetAlpha(0.6)
        orb.skull:Hide()
        orb.lowHP = overlay:CreateTexture(nil, "BACKGROUND", nil, 2)
        orb.lowHP:SetPoint("CENTER", 0, 0)
        orb.lowHP:SetBlendMode("ADD")
        orb.lowHP:SetVertexColor(1, 0, 0, 1)
        orb.lowHP:Hide()
    end
    orb.gloss = overlay:CreateTexture(nil, "BACKGROUND", nil, 3)
    orb.gloss:SetAllPoints()
    orb.gloss:SetBlendMode("ADD")
    orb.gloss:Hide()

    local values = CreateFrame("Frame", nil, overlay)
    values:SetAllPoints(orb)
    values.top = values:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    values.top:SetPoint("CENTER", 0, 10)
    values.bottom = values:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    values.bottom:SetPoint("CENTER", 0, -10)
    orb.values = values

    -- The resource orb's right half, drawn only for a class with a second power:
    -- a ScrollFrame and liquid of its own beside the main one, the line down the
    -- middle and the second power's numbers on the values frame above both.
    if kind == "POWER" then
        local halfFrame = CreateFrame("ScrollFrame", nil, orb)
        local halfChild = CreateFrame("Frame", nil, halfFrame)
        halfFrame:SetScrollChild(halfChild)
        local halfLiquid = halfChild:CreateTexture(nil, "ARTWORK", nil, -1)
        halfLiquid:SetVertexColor(TINT.r, TINT.g, TINT.b)
        halfFrame:Hide()
        orb.half = {scrollFrame = halfFrame, scrollChild = halfChild, layers = {halfLiquid},
                    current = 0, maximum = 0, fraction = 0}
        orb.divider = values:CreateTexture(nil, "BACKGROUND")
        orb.divider:SetTexture(0, 0, 0, 0.8)
        orb.divider:Hide()
        values.top2 = values:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        values.bottom2 = values:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    end

    -- Step the slot's frames on this orb's own clock; draw() is the only reader
    -- of globeFrame, so the visible cell and the fill crop cannot disagree.
    orb:SetScript("OnUpdate", function(frame, elapsed)
        local slot = frame.globe
        if not slot then return end
        frame.globeElapsed = frame.globeElapsed + elapsed
        local fps = setting("orbFps", 20)
        if type(fps) ~= "number" or fps <= 0 then fps = 20 end
        local step = 1 / fps
        if frame.globeElapsed < step then return end
        frame.globeElapsed = frame.globeElapsed - step
        frame.globeFrame = (frame.globeFrame + 1) % slot.frames
        update(frame, frame.current, frame.maximum)
    end)
    return orb
end

-- Size about the well and anchor: the well centre is art coordinates scaled by
-- bar1Scale only, so orbScale changes the orb's size without moving its centre.
local function layoutOrb(orb, well, artScale, nudgeX, nudgeY)
    orb.scrollChild:SetSize(orb.size, orb.size)
    if orb.half then
        orb.half.scrollChild:SetSize(orb.size, orb.size)
        orb.divider:ClearAllPoints()
        orb.divider:SetPoint("TOP", orb, "TOP", 0, 0)
        orb.divider:SetPoint("BOTTOM", orb, "BOTTOM", 0, 0)
        orb.divider:SetWidth(2)
    end
    -- The mock ring carries a 4px drop shadow outside the orb's own edge, so it
    -- is drawn 91/87 of the orb's size; a skin's orb-back is the orb itself.
    orb.back:ClearAllPoints()
    if orb.backIsMock then
        local over = orb.size * (MOCK_RING_OVER - 1) / 2
        orb.back:SetPoint("TOPLEFT", orb, "TOPLEFT", -over, over)
        orb.back:SetPoint("BOTTOMRIGHT", orb, "BOTTOMRIGHT", over, -over)
    else
        orb.back:SetAllPoints(orb)
    end
    if orb.hasSpark then
        orb.spark:SetWidth(orb.size)
        orb.spark:SetHeight(32 * orb.size / 256)
    end
    if orb.skull then orb.skull:SetSize(orb.size - 40, orb.size - 40) end
    if orb.lowHP then orb.lowHP:SetSize(orb.size - 15, orb.size - 15) end
    orb:ClearAllPoints()
    orb:SetPoint("CENTER", module:GetArt(), "TOPLEFT",
        well.centreX * artScale + nudgeX, -(well.centreY * artScale) + nudgeY)
    orb:SetSize(orb.size, orb.size)
end

-- ------------------------------------------------------------- cosmetic slots

local function textureSlot(name, texture)
    local slot = module:ArtSlot(name)
    if slot and slot.path then
        texture:SetTexture(slot.path)
        return true
    end
    if texture then texture:Hide() end
    return false
end

-- The backing: the mock ring when no skin fills the bar slot (a skin's bar art
-- brings its own rings), otherwise the skin's orb-back. Everything else is a
-- skin's: an empty slot draws nothing.
local function applyCosmetics(orb)
    orb.backIsMock = module:IsMock()
    if orb.backIsMock then
        orb.back:SetTexture(MOCK_RING)
        orb.back:Show()
    else
        textureSlot("orb-back", orb.back)
    end
    orb.hasGloss = textureSlot("orb-gloss", orb.gloss)
    if orb.hasGloss then orb.gloss:Show() end
    orb.hasSpark = textureSlot("orb-spark", orb.spark)
    if orb.kind == "HEALTH" then
        orb.hasSkull = textureSlot("orb-skull", orb.skull)
        orb.hasLowHP = textureSlot("orb-lowhp-glow", orb.lowHP)
    end
end

-- ------------------------------------------------------------- resource fill

-- One tint for the liquid and its glow, so a tinted stand-in does not get a
-- white glow over a coloured body.
local function tintGlobe(orb, colour)
    for _, layer in ipairs(orb.globeLayers) do
        layer:SetVertexColor(colour.r, colour.g, colour.b)
    end
end

-- Re-read the power the character actually uses and pick its fill. No
-- dropdown, no saved choice, no class-name compare. The rebuilt client reports
-- the power's own token; the stock client reports the slot's, which is read with
-- the unit's CLASS TOKEN through Diablocraft.ResourceNames, so two classes on one
-- WoW slot keep their own fill. Only swaps the slot; layout stays
-- LayoutOrbs' job.
local function resourceFor(classToken, powerToken)
    local names = Diablocraft and Diablocraft.ResourceNames
    local bySlot = names and classToken and names[classToken]
    return bySlot and powerToken and bySlot[powerToken]
end

-- The stock client's slot token becomes the class's power token through its
-- row; a token with no row (the rebuilt client's own, or a stock power no class
-- rides) is the power itself.
local function powerTokenFor(classToken, reported)
    local entry = resourceFor(classToken, reported)
    return entry and entry.token or reported
end

-- The class's second power's row (its slot and token), or nil.
local function secondFor(classToken)
    local names = Diablocraft and Diablocraft.ResourceNames
    for _, entry in pairs(names and classToken and names[classToken] or {}) do
        if entry.role == "second" then return entry end
    end
    return nil
end

-- A skin's slot first, then the shipped sheet. The skin slot and the sheet are
-- both named by the token in lower case, which is the sheet's resource key.
local function fillSlot(name, key)
    local slot = module:ArtSlot(name)
    if slot and slot.path then return slot end
    return key and shippedFill(key) or nil
end

local function powerFill(token)
    local key = token and token:lower()
    return fillSlot(key and ("orb-resource-" .. key) or "", key), key
end

-- Split or whole: the numbers sit over their own half when the orb is split.
local function placeValues(orb, split)
    local values, offset = orb.values, split and (orb.size or 0) / 4 or 0
    values.top:ClearAllPoints()
    values.top:SetPoint("CENTER", -offset, 10)
    values.bottom:ClearAllPoints()
    values.bottom:SetPoint("CENTER", -offset, -10)
    values.top2:ClearAllPoints()
    values.top2:SetPoint("CENTER", offset, 10)
    values.bottom2:ClearAllPoints()
    values.bottom2:SetPoint("CENTER", offset, -10)
    if not split then
        values.top2:SetText("")
        values.bottom2:SetText("")
    end
end

local function applyResource()
    if not powerOrb then return end
    local _, classToken = UnitClass("player")
    local _, reported = UnitPowerType("player")
    local token = powerTokenFor(classToken, reported)
    local slot, key = powerFill(token)
    if not slot then
        -- Visible, not silent: the stand-in disc tinted with WoW's own colour
        -- for this power, and one login line naming the missing art.
        slot = DISC
        local colour = (token and PowerBarColor and PowerBarColor[token]) or {r = 1, g = 1, b = 1}
        tintGlobe(powerOrb, colour)
        powerOrb.fallback = true
        if not warned[token or "?"] then
            warned[token or "?"] = true
            print("ElvUI_Torment: no orb fill for " .. tostring(token))
        end
    else
        tintGlobe(powerOrb, TINT)
        powerOrb.fallback = nil
    end
    powerOrb.globeKey = key
    setGlobe(powerOrb, slot)
    -- The second power, when the class has one with a sheet; a stand-in disc is
    -- never split in, the orb stays whole.
    local second = secondFor(classToken)
    local halfSlot = second and second.token and powerFill(second.token)
    powerOrb.secondPower = halfSlot and second.power or nil
    setHalf(powerOrb, halfSlot)
    placeValues(powerOrb, halfSlot ~= nil)
end

local function updateSecond()
    if not powerOrb or not powerOrb.secondPower then return end
    updateHalf(powerOrb, UnitPower("player", powerOrb.secondPower), UnitPowerMax("player", powerOrb.secondPower))
end

-- --------------------------------------------------------------- layout/events

-- Called from barart's ApplyGeometry (already combat-deferred) once the art
-- exists, so both orbs are created, sized and anchored with the bar.
function module:LayoutOrbs()
    local artFrame = module:GetArt()
    if not artFrame then return end
    local wells = module:GetGlobeWells()
    -- Art-coordinate scale and the orb's own size factor are separate: only the
    -- size factor may change how big an orb is, never where its well is.
    local artScale = setting("bar1Scale", 1)
    local sizeFactor = setting("orbScale", 1)
    local nudgeX = setting("orbNudgeX", 0) * artScale
    local nudgeY = setting("orbNudgeY", 0) * artScale
    if not healthOrb then healthOrb = createOrb("HEALTH") end
    if not powerOrb then powerOrb = createOrb("POWER") end

    healthOrb.size = wells.health.diameter * artScale * sizeFactor
    powerOrb.size = wells.power.diameter * artScale * sizeFactor
    applyCosmetics(healthOrb)
    setGlobe(healthOrb, fillSlot("orb-health", "health"))
    layoutOrb(healthOrb, wells.health, artScale, nudgeX, nudgeY)
    applyCosmetics(powerOrb)
    applyResource()
    layoutOrb(powerOrb, wells.power, artScale, nudgeX, nudgeY)
    -- Initial values, so a PLAYER_ENTERING_WORLD before this layout is not the
    -- only chance to fill them.
    update(healthOrb, UnitHealth("player"), UnitHealthMax("player"))
    updateSecond()
    update(powerOrb, UnitPower("player"), UnitPowerMax("player"))
end

local events = CreateFrame("Frame")
events:RegisterEvent("UNIT_HEALTH")
events:RegisterEvent("UNIT_MAXHEALTH")
for _, name in ipairs(POWER_EVENTS) do events:RegisterEvent(name) end
for _, name in ipairs(POWER_MAX_EVENTS) do events:RegisterEvent(name) end
events:RegisterEvent("UNIT_DISPLAYPOWER")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:SetScript("OnEvent", function(_, event, unit)
    if unit and unit ~= "player" then return end
    if event == "UNIT_DISPLAYPOWER" or event == "PLAYER_ENTERING_WORLD" then
        applyResource()
    end
    if healthOrb then update(healthOrb, UnitHealth("player"), UnitHealthMax("player")) end
    updateSecond()
    if powerOrb then update(powerOrb, UnitPower("player"), UnitPowerMax("player")) end
end)
