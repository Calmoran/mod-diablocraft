-- luacheck: ignore 122
-- Run from repo root with lua52_interpreter.exe.
--
-- Diablocraft.PanelFrame, the border kit every screen wears, against a stub
-- 3.3.5a API. It exists because of a bug that survived three rounds of looking
-- at the code (ruling 2026-09-13: "something is still causing the side rails to
-- not render"):
--
--   frame_bg_slate is fully opaque - every DXT5 block of it - and it covers the
--   whole panel, rails included. The rails shared its draw layer, so which of
--   the two won was the engine's business rather than creation order's, and the
--   slate won on every panel. The corners were the only piece of the kit that
--   ever showed, because they were the only piece on a higher layer.
--
-- So: the three pieces go on three layers, in order, and this pins that. It also
-- pins the geometry, because a rail that is drawn at the wrong size or off the
-- frame looks exactly like a rail that is not drawn at all.

-- The one shared strict widget mock (diablocraft-yey2) owns every widget.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024, 768)
local frames = Mock.frames

-- The mock answers SetTexture like the client, but it does not model the client
-- answering false for a file it cannot load, which the ART NOT FOUND check needs.
local mockSetTexture = Mock.methods.SetTexture.fn
Mock.methods.SetTexture.fn = function(self, texture, ...)
    if _G.DC_TEST_MISSING and type(texture) == "string"
        and texture:find(_G.DC_TEST_MISSING, 1, true) then
        self.texture = texture
        return false
    end
    return mockSetTexture(self, texture, ...)
end

-- Every widget the kit makes, in creation order; a fresh panel's textures are
-- everything made since the mark.
local function texturesSince(mark)
    local out = {}
    for i = mark + 1, #frames do
        if frames[i].kind == "Texture" then out[#out + 1] = frames[i] end
    end
    return out
end

local function frame(name, width, height)
    local made = Mock.widget("Frame", name)
    made:SetSize(width, height)
    return made
end

_G.DEFAULT_CHAT_FRAME = {AddMessage = function() end}

-- The WoW client has no `require`, and the addon asks for AIO through it.
-- Standalone Lua does, so it has to go before the file is loaded or the
-- addon goes looking for an AIO.dll that is not there.
_G.require = nil

-- Stash.lua hooks these two stock cursor calls: the
-- client has them as functions and the mock refuses to hook a name that is not one.
_G.PickupContainerItem = function() end
_G.PickupInventoryItem = function() end

dofile("mod-diablocraft/scripts/dc_addon_core.lua")
local DC = _G.Diablocraft

-- Both corner modes at both shipped panel sizes. "none" is what ships; "plain"
-- is the one-line hook, tested so that flipping it is not a leap of faith.
local shipped = DC.PANEL_CORNERS
assert(shipped == "plain", "the plain corners are what ships (the designer, 1d1d2e6)")

-- The designer's brief, in numbers: D3's rail is about 12-14px at 1080p.
assert(DC.PANEL_BAND == 16, "the band is 16, got " .. tostring(DC.PANEL_BAND))
assert(DC.PANEL_BLEED == 0, "the plain corners carry no bleed, got " .. tostring(DC.PANEL_BLEED))
assert(DC.PANEL_EDGE == DC.PANEL_BAND, "with no bleed the inset is the band itself")

for _, panel in ipairs({{"inventory", 470, 740, "none"}, {"stash", 892, 560, "none"},
                        {"inventory", 470, 740, "plain"}, {"stash", 892, 560, "plain"}}) do
    local name, width, height = panel[1] .. "/" .. panel[4], panel[2], panel[3]
    DC.PANEL_CORNERS = panel[4]
    local butt = panel[4] == "none"
    local mark = #frames
    local target = frame(name, width, height)
    DC.PanelFrame(target)
    local textures = texturesSince(mark)

    local byLayer, byFile = {}, {}
    for _, made in ipairs(textures) do
        byLayer[made.drawLayer] = (byLayer[made.drawLayer] or 0) + 1
        local file = (made.texture or ""):match("([^\\]+)$") or ""
        byFile[file] = (byFile[file] or 0) + 1
    end

    -- Every piece of the kit was drawn.
    assert(byFile.frame_bg_slate and byFile.frame_bg_slate > 0, name .. ": the slate is drawn")
    for _, side in ipairs({"top", "bottom", "left", "right"}) do
        local file = "frame_edge_" .. side
        assert(byFile[file] and byFile[file] > 0, name .. ": the " .. side .. " rail is drawn")
    end
    -- The four ornament corners are retired on every panel, in both modes: the
    -- only corner the kit will ever draw again is a plain one (ruling 2026-09-13).
    for file in pairs(byFile) do
        assert(not file:find("^frame_corner_") or file:find("^frame_corner_plain_"),
            name .. ": no ornament corner is drawn, found " .. file)
    end
    if butt then
        for file in pairs(byFile) do
            assert(not file:find("^frame_corner_plain_"),
                name .. ": the butt joint draws no corner at all, found " .. file)
        end
    else
        for _, corner in ipairs({"tl", "tr", "bl", "br"}) do
            assert(byFile["frame_corner_plain_32_" .. corner] == 1,
                name .. ": one plain " .. corner .. " corner")
        end
    end

    -- And on three separate layers, in the order slate < rails < corners. Same
    -- layer is what made the opaque slate eat the rails.
    for _, made in ipairs(textures) do
        local file = (made.texture or ""):match("([^\\]+)$") or ""
        local want = file == "frame_bg_slate" and "BACKGROUND"
            or file:find("^frame_edge_") and "BORDER"
            or "ARTWORK"
        assert(made.drawLayer == want,
            name .. ": " .. file .. " is on " .. tostring(want) .. ", got " .. tostring(made.drawLayer))
    end
    assert(byLayer.BACKGROUND > 0 and byLayer.BORDER > 0, name .. ": slate and rails are on their own layers")
    -- Written out rather than `butt and nil or 4`, which is 4 either way in Lua.
    if butt then
        assert(byLayer.ARTWORK == nil, name .. ": nothing is drawn on the corner layer")
    else
        assert(byLayer.ARTWORK == 4, name .. ": four corners on the corner layer, got "
            .. tostring(byLayer.ARTWORK))
    end

    -- Geometry: every rail is a real size, on the frame, and along its own edge.
    local bleed, band = DC.PANEL_BLEED, DC.PANEL_BAND
    for _, made in ipairs(textures) do
        local file = (made.texture or ""):match("([^\\]+)$") or ""
        if file:find("^frame_edge_") then
            assert(made:GetWidth() > 0 and made:GetHeight() > 0,
                name .. ": " .. file .. " has a real size, got " .. made:GetWidth() .. "x" .. made:GetHeight())
            local x, y = made.points[1].x, made.points[1].y
            assert(x >= 0 and x + made:GetWidth() <= width,
                name .. ": " .. file .. " runs off the frame at x=" .. x)
            assert(-y >= 0 and -y + made:GetHeight() <= height,
                name .. ": " .. file .. " runs off the frame at y=" .. y)
            if file == "frame_edge_top" then
                assert(-y == bleed and made:GetHeight() == band, name .. ": the top rail is on the top band")
            elseif file == "frame_edge_left" then
                assert(x == bleed and made:GetWidth() == band, name .. ": the left rail is on the left band")
            elseif file == "frame_edge_right" then
                assert(x == width - bleed - band, name .. ": the right rail is on the right band")
            elseif file == "frame_edge_bottom" then
                assert(-y == height - bleed - band, name .. ": the bottom rail is on the bottom band")
            end
        end
    end

    -- The butt joint: horizontals own the full width between the bleeds, and the
    -- verticals stop at the inner edge of the horizontals. That is what lets two
    -- panels a PANEL_SEAM apart share one rail down the seam.
    local span = {}
    for _, made in ipairs(textures) do
        local file = (made.texture or ""):match("([^\\]+)$") or ""
        if file:find("^frame_edge_") then
            local horizontal = file == "frame_edge_top" or file == "frame_edge_bottom"
            local from = horizontal and made.points[1].x or -made.points[1].y
            local to = from + (horizontal and made:GetWidth() or made:GetHeight())
            local seen = span[file]
            span[file] = {math.min(seen and seen[1] or from, from), math.max(seen and seen[2] or to, to)}
        end
    end
    -- Butt joint: the horizontals own the full width. With a corner piece they
    -- inset by a band to leave it the square where the rails cross.
    local acrossFrom = butt and bleed or (bleed + band)
    for _, file in ipairs({"frame_edge_top", "frame_edge_bottom"}) do
        assert(span[file][1] == acrossFrom and span[file][2] == width - acrossFrom,
            name .. ": " .. file .. " spans " .. span[file][1] .. ".." .. span[file][2]
                .. ", wanted " .. acrossFrom .. ".." .. (width - acrossFrom))
    end
    for _, file in ipairs({"frame_edge_left", "frame_edge_right"}) do
        assert(span[file][1] == bleed + band and span[file][2] == height - bleed - band,
            name .. ": " .. file .. " butts into the horizontals, got "
                .. span[file][1] .. ".." .. span[file][2] .. " of " .. (bleed + band)
                .. ".." .. (height - bleed - band))
    end

    -- A plain corner is the band square, sitting on the rails rather than on the
    -- frame's rect - so it fills exactly the gap the two runs leave.
    if not butt then
        for _, made in ipairs(textures) do
            local file = (made.texture or ""):match("([^\\]+)$") or ""
            if file:find("^frame_corner_plain_") then
                assert(made:GetWidth() == band and made:GetHeight() == band,
                    name .. ": " .. file .. " is the band square, got " .. made:GetWidth() .. "x" .. made:GetHeight())
                assert(file:find("_32_"), name .. ": the 32 set is the one drawn at a 16 band, got " .. file)
                assert(math.abs(made.points[1].x) == bleed and math.abs(made.points[1].y) == bleed,
                    name .. ": " .. file .. " is inset by the bleed")
            end
        end
    end

    -- The corners are the FIRST pieces drawn, not the last. They were last, and
    -- behind a hundred slate tiles they never appeared at all.
    if not butt then
        for index = 1, 4 do
            local file = (textures[index].texture or ""):match("([^\\]+)$") or ""
            assert(file:find("^frame_corner_plain_"),
                name .. ": corner " .. index .. " is drawn before the fill, got " .. file)
        end
    end

    -- The slate tiles at the size it was PAINTED at, not at the rails' step.
    -- Scaling it with them is what tripled the texture count on every panel.
    local slate = 0
    for _, made in ipairs(textures) do
        local file = (made.texture or ""):match("([^\\]+)$") or ""
        if file == "frame_bg_slate" then
            slate = slate + 1
            assert(made:GetWidth() <= 256 and made:GetHeight() <= 256, name .. ": a slate tile is one painted tile")
        end
    end
    assert(slate <= math.ceil(width / 256) * math.ceil(height / 256),
        name .. ": " .. slate .. " slate tiles where " ..
        (math.ceil(width / 256) * math.ceil(height / 256)) .. " cover the panel")
    -- And the whole panel stays near the count that demonstrably rendered.
    assert(#textures <= 80, name .. ": " .. #textures .. " textures on one frame, which is where corners go missing")

    -- A rail is a run of whole tiles with only the last one clipped, so nothing
    -- is ever stretched however long the run.
    local clipped = 0
    for _, made in ipairs(textures) do
        local file = (made.texture or ""):match("([^\\]+)$") or ""
        if file == "frame_edge_left" then
            local fraction = made.texCoord[4]
            if fraction < 1 then clipped = clipped + 1 end
            assert(made:GetHeight() == fraction * DC.PANEL_STEP,
                name .. ": a left rail tile is drawn at its texcoord's length")
        end
    end
    assert(clipped <= 1, name .. ": at most one tile of a run is clipped, got " .. clipped)

    -- Re-laying out reuses the pool rather than stacking a second border on top.
    local before = #frames
    DC.PanelFrame(target)
    assert(#frames == before, name .. ": a relayout reuses its textures, went " .. before .. " to " .. #frames)
end

DC.PANEL_CORNERS = shipped

-- The seam two flush panels overlap by: one band plus the bleed on each side of
-- it, so their facing vertical rails land on the same pixels.
assert(DC.PANEL_SEAM == 2 * DC.PANEL_BLEED + DC.PANEL_BAND,
    "PANEL_SEAM is one whole rail, got " .. tostring(DC.PANEL_SEAM))

-- (Inventory.xml no longer uses the panel kit: the character sheet and its side panel are
-- drawn like the Jeweler window, diablocraft-inventory-grid-removal. The kit still draws
-- the stash and the Blacksmith.)

-- Art the client cannot load looks exactly like art that was never drawn - a
-- hole where the rails leave room for a corner - so the kit says which file it
-- was. This is how the plain corners were traced to a client that had been left
-- running while they were copied in (ruling 2026-09-13).
local probe = frame("probe", 470, 740)
DC.PanelFrame(probe)
assert(DC.PanelReport(probe):find("ART NOT FOUND") == nil, "nothing is missing when every file loads")

_G.DC_TEST_MISSING = "frame_corner_plain_32_tl"
local broken = frame("broken", 470, 740)
DC.PanelFrame(broken)
local report = DC.PanelReport(broken)
assert(report:find("ART NOT FOUND", 1, true), "a file the client refuses is reported: " .. report)
assert(report:find("frame_corner_plain_32_tl", 1, true), "and named: " .. report)
assert(report:find("restart the client", 1, true), "with what to do about it: " .. report)
_G.DC_TEST_MISSING = nil

print("Panel kit checks passed")
