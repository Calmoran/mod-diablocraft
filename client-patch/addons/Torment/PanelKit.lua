-- Torment panel kit: the measurements of the tiled border and the PanelFrame call that
-- draws it on any frame.

Diablocraft = Diablocraft or {}
local DC = Diablocraft

-- ------------------------------------------------------------------- layout

-- Panel geometry, all measured off the source art, none of it guessed.
-- As painted: the corner pieces are 128x128 and carry 14px of transparent
-- margin outside the gold band; the edge strips are 64 thick with no margin at
-- all, so the strips are inset by that 14 to put both bands on the same line.
-- PANEL_EDGE is what that adds up to: the distance from the panel's rect to
-- clear floor.
--
-- The whole kit is drawn at a QUARTER of the scale it was
-- painted at, because D3's rail is about 12-14px at 1080p and ours was 32.
-- The band is the number that matters; everything else follows it, and
-- PANEL_STEP brings the run length down by the same factor so the moulding
-- shrinks uniformly - no new art, nothing stretched.
--
-- The bleed is gone with the ornament corners: the plain corners
-- carry no transparent margin, so the rail's outer edge IS the frame's rect and
-- a panel meant to touch the screen edge no longer has to overhang it.
local PANEL_BAND = 16                 -- painted 64, drawn at a quarter
local PANEL_CORNER = 16               -- the plain corner is the band square
local PANEL_BLEED = 0                 -- plain corner art, no margin
local PANEL_TILE = 256                -- run length of one edge strip / fill tile, as painted
local PANEL_STEP = 64                 -- ... and as drawn: PANEL_TILE at a quarter
local PANEL_EDGE = PANEL_BLEED + PANEL_BAND
-- Every screen built on the kit has to clear the same inset, so it is published
-- rather than copied: Inventory.lua lays its columns out from this number.
DC.PANEL_EDGE = PANEL_EDGE
-- And the rest of the measurements with it. The bleed is what a panel meant to
-- touch a screen edge overhangs by; it is 0 now that the corners are plain, and
-- published anyway so nothing has to know that. Band and step are here for the
-- kit's own tests, which must not carry a second copy of a number.
DC.PANEL_BLEED = PANEL_BLEED
DC.PANEL_BAND = PANEL_BAND
DC.PANEL_STEP = PANEL_STEP

-- THE ONE-LINE HOOK.
--
--   "none"   the butt joint: no corner piece at all, horizontal rails the full
--            width, vertical rails stopping at the inner edge of them.
--   "plain"  the band square at each corner, rails inset by a band to meet it.
--
-- The plain corners are in on every panel and the
-- butt joint is gone, because two panels sharing a seam overlapped visibly
-- where their horizontal rails ran past each other. A corner square fills that
-- gap instead. "none" still works and is still tested.
DC.PANEL_CORNERS = "plain"

-- Two panels sit flush when they OVERLAP by exactly one rail: the band plus the
-- bleed on either side of it. Their facing vertical rails then land on the same
-- pixels and read as one shared rail rather than two side by side. The panel kit
-- keeps it for any two panels that meet; the stash no longer does, it sits flush
-- against ElvUI's bags with no overlap.
DC.PANEL_SEAM = 2 * PANEL_BLEED + PANEL_BAND

-- ------------------------------------------------------------- panel frame

-- Textures are pooled on the frame rather than created afresh, because
-- PanelFrame now runs more than once: the layout is rebuilt from the frame's
-- LIVE size on every show and on every size change, so a frame that reported a
-- different size at OnLoad than it has on screen still gets a complete border.
-- Building once at OnLoad is why the edge strips were missing on the inventory
-- and Details panels while the corners, which need no run length, were there.
local function pool(parent)
    if not parent.dcPanelPool then parent.dcPanelPool = {} end
    return parent.dcPanelPool
end

-- The next texture of the pool, in the art slot and layer this call wants.
local function piece(state, slot, layer, box)
    state.used = state.used + 1
    local texture = state.pool[state.used]
    if not texture then
        texture = state.parent:CreateTexture(nil, layer)
        state.pool[state.used] = texture
    end
    texture:SetDrawLayer(layer)
    texture:ClearAllPoints()
    DC.SetArt(texture, slot, box)
    texture:Show()
    return texture
end

-- One run of whole tiles along a single axis, the last clipped with SetTexCoord
-- to whatever length is left. Nothing is ever stretched, so the moulding keeps
-- the proportions it was painted at however long the run is - at PANEL_STEP per
-- tile rather than PANEL_TILE, which is what makes the kit half scale.
local function tileRun(state, slot, layer, horizontal, x, y, length, thickness)
    local drawn = 0
    while drawn < length - 0.5 do
        local step = math.min(PANEL_STEP, length - drawn)
        local fraction = step / PANEL_STEP
        local texture
        if horizontal then
            texture = piece(state, slot, layer, {0, fraction, 0, 1})
            texture:SetWidth(step)
            texture:SetHeight(thickness)
            texture:SetPoint("TOPLEFT", state.parent, "TOPLEFT", x + drawn, y)
        else
            texture = piece(state, slot, layer, {0, 1, 0, fraction})
            texture:SetWidth(thickness)
            texture:SetHeight(step)
            texture:SetPoint("TOPLEFT", state.parent, "TOPLEFT", x, y - drawn)
        end
        drawn = drawn + step
    end
end

-- The same run in both axes: the slate behind the panel, clipped at the right
-- column and the bottom row.
--
-- It tiles at PANEL_TILE, the size it was PAINTED at, and deliberately not at
-- the rails' PANEL_STEP. The rails are moulding and have to shrink with the
-- kit; the slate is a surface, and shrinking it with them only multiplies the
-- tile count - at band 16 the inventory needed 96 slate tiles where 6 do, and
-- the 138 textures that put on one frame is what stopped the last four, the
-- corners, from ever appearing (the corners were not
-- loading).
local function tileFill(state, slot, layer, x, y, width, height)
    local down = 0
    while down < height - 0.5 do
        local rows = math.min(PANEL_TILE, height - down)
        local across = 0
        while across < width - 0.5 do
            local cols = math.min(PANEL_TILE, width - across)
            local texture = piece(state, slot, layer, {0, cols / PANEL_TILE, 0, rows / PANEL_TILE})
            texture:SetWidth(cols)
            texture:SetHeight(rows)
            texture:SetPoint("TOPLEFT", state.parent, "TOPLEFT", x + across, y - down)
            across = across + cols
        end
        down = down + rows
    end
end

-- The reusable part of the kit: any frame that wants the Diablocraft border
-- calls this once, at any size, and it keeps itself right from then on.
--
-- Slate, then the rails over it, then the corners on top - corners last because
-- their inner curve is transparent and has to show the slate and the strip ends
-- through it. Each of the three is on its OWN draw layer, and that is the whole
-- point (the rails never rendered on any panel):
--
--   slate   BACKGROUND   frame_bg_slate is fully opaque, every block of it, and
--                        it covers the entire panel - the rails included.
--   rails   BORDER       so they cannot be painted over by the slate. They used
--                        to share BACKGROUND with it, and same-layer draw order
--                        is the engine's business, not creation order's: the
--                        slate won and the rails were invisible everywhere.
--   corners ARTWORK      above both. They were already the odd one out on
--                        BORDER, which is exactly why they were the only piece
--                        of the kit that ever showed.
--
-- Nothing a screen draws is disturbed: the stash's own ARTWORK pieces, the
-- title crest and the coin, sit where no corner reaches.
--
-- The four ORNAMENT corners are retired for good. What sits
-- at each corner now is the plain square, exactly the band, filling the
-- gap the two runs leave for it. Two panels placed PANEL_SEAM apart still share
-- one vertical rail; the corner square is what closes the seam cleanly, which
-- the butt joint did not - its horizontals ran past each other visibly.
-- PANEL_CORNERS = "none" brings the butt joint back.
local function layout(parent)
    local width, height = parent:GetWidth(), parent:GetHeight()
    -- Nothing to draw against a frame that has not been sized yet; the OnShow
    -- and OnSizeChanged hooks below come back when it has.
    -- The smallest panel the kit can draw is two opposite bands; the corner
    -- piece is no longer what sets the floor.
    if not width or not height or width < 2 * PANEL_EDGE or height < 2 * PANEL_EDGE then
        return 0
    end
    local state = {parent = parent, pool = pool(parent), used = 0}
    local bleed, band = PANEL_BLEED, PANEL_BAND

    -- Corners first. Stacking is decided by the draw layer now, not by creation
    -- order, so the order is free - and spending it on the four pieces that
    -- would otherwise be created last, behind a hundred slate tiles, is the
    -- cheap insurance the missing corners earned.
    if DC.PANEL_CORNERS ~= "none" then
        -- The square where the two rails cross, inset by the bleed so it lands
        -- on the rails rather than on the frame's rect.
        local corners = {{"panel-frame-plain-tl", "TOPLEFT", bleed, -bleed},
                         {"panel-frame-plain-tr", "TOPRIGHT", -bleed, -bleed},
                         {"panel-frame-plain-bl", "BOTTOMLEFT", bleed, bleed},
                         {"panel-frame-plain-br", "BOTTOMRIGHT", -bleed, bleed}}
        for _, entry in ipairs(corners) do
            local texture = piece(state, entry[1], "ARTWORK")
            texture:SetWidth(PANEL_CORNER)
            texture:SetHeight(PANEL_CORNER)
            texture:SetPoint(entry[2], parent, entry[2], entry[3], entry[4])
        end
    end
    state.corners = state.used

    tileFill(state, "panel-frame-fill", "BACKGROUND", bleed, -bleed, width - 2 * bleed, height - 2 * bleed)
    state.fill = state.used - state.corners

    -- Where each run starts. The butt joint gives the full width to the
    -- horizontals and butts the verticals into their inner edge, which is what
    -- lets two panels share one rail down the seam between them; a corner piece
    -- takes the band square instead and both runs inset by a band to meet it.
    local butt = DC.PANEL_CORNERS == "none"
    local acrossStart = butt and bleed or (bleed + band)
    local downStart = bleed + band

    tileRun(state, "panel-frame-edge-top", "BORDER", true,
        acrossStart, -bleed, width - 2 * acrossStart, band)
    tileRun(state, "panel-frame-edge-bottom", "BORDER", true,
        acrossStart, -(height - bleed - band), width - 2 * acrossStart, band)
    tileRun(state, "panel-frame-edge-left", "BORDER", false,
        bleed, -downStart, height - 2 * downStart, band)
    tileRun(state, "panel-frame-edge-right", "BORDER", false,
        width - bleed - band, -downStart, height - 2 * downStart, band)

    state.rails = state.used - state.fill - state.corners

    -- Anything the pool still holds from a larger size is put away, never left
    -- floating where the panel no longer reaches.
    for index = state.used + 1, #state.pool do state.pool[index]:Hide() end
    -- Which art the client could not find, if any.
    local missing = {}
    for index = 1, state.used do
        local file = state.pool[index].dcMissing
        if file and not missing[file] then missing[file] = true; missing[#missing + 1] = file end
    end
    parent.dcPanelMissing = #missing > 0 and table.concat(missing, ",") or nil
    parent.dcPanelDrawn = state.used
    parent.dcPanelSize = width .. "x" .. height
    -- Counted per layer, because "how many pieces" was never the question: a
    -- rail on the slate's own layer is drawn and still invisible.
    parent.dcPanelLayers = string.format("slate %d / rails %d / corners %d",
        state.fill or 0, state.rails or 0, state.corners or 0)
    return state.used
end

function DC.PanelFrame(parent)
    layout(parent)
    if parent.dcPanelHooked then return end
    parent.dcPanelHooked = true
    -- Re-measured rather than remembered. OnShow covers a frame whose size was
    -- not final at OnLoad; OnSizeChanged covers every later resize. The guard
    -- stops the relayout re-entering through its own texture sizing.
    local function relayout(self)
        if self.dcPanelBusy then return end
        self.dcPanelBusy = true
        layout(self)
        self.dcPanelBusy = false
    end
    parent:HookScript("OnShow", relayout)
    parent:HookScript("OnSizeChanged", relayout)
end

-- What the kit actually drew, for /dcinv frame.
function DC.PanelReport(parent)
    if not parent then return "no frame" end
    return (parent:GetName() or "?") .. " " .. tostring(parent.dcPanelSize)
        .. " pieces=" .. tostring(parent.dcPanelDrawn)
        .. " [" .. tostring(parent.dcPanelLayers) .. "]"
        .. (parent.dcPanelMissing
            and ("  ART NOT FOUND: " .. parent.dcPanelMissing .. " - restart the client, /reload will not do it")
            or "")
end
