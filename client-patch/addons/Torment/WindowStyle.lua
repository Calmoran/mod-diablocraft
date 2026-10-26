-- Torment window look: the palette, the backdrops and the skinnable window parts
-- (DC.Style) every Torment window is drawn with.

Diablocraft = Diablocraft or {}
local DC = Diablocraft

-- ---------------------------------------------------------------- window look

-- One look for every Torment window (the Skills restyle's): the
-- stock dialog backdrop the Jeweler draws, the flat 1px ground its slots use, and
-- the two native frames - a UIPanelCloseButton and a UIPanelButtonTemplate
-- button - so the Jeweler, this addon's character sheet, the Skills window and
-- (next) the stash cannot drift apart.
--
-- The AIO windows (dc_jeweler.lua, dc_skillbar.lua) reach the client from the
-- server while this addon ships through the launcher, so either can be newer than
-- the other: they read DC.Style when it is there and carry these same values as a
-- fallback. test_skillbar_client.lua, test_jeweler_client.lua and
-- test_character_sheet.lua pin every copy against the others field by field.
local WINDOW_BACKDROP = {
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tile = true, tileSize = 32, edgeSize = 32,
    insets = {left = 11, right = 12, top = 12, bottom = 11},
}
local FLAT_BACKDROP = {
    bgFile = "Interface\\Buttons\\WHITE8X8",
    edgeFile = "Interface\\Buttons\\WHITE8X8",
    edgeSize = 1, insets = {left = 1, right = 1, top = 1, bottom = 1},
}

-- The palette the server-pushed windows draw with (mod-diablocraft/lua/aio/dc_aio_ui.lua,
-- DCUI), carried here for the windows this addon draws itself - the stash
-- first. dc_aio_ui.lua comes from the server and this addon
-- from the launcher, so neither can read the other at load; test_stash_look.lua pins this
-- copy against DCUI value for value, and RARITY against dc_tooltip.lua's DCRARITY.
local PALETTE = {
    SLOT_BG = {.06, .05, .04}, SLOT_BORDER = {.43, .36, .26},
    TAB_ACTIVE = {.89, .71, .35}, TAB_IDLE = {.43, .36, .26},
    BOX_BORDER = {.42, .32, .2}, ROW_SELECT = {1, .82, 0, .28}, ROW_HILITE = {1, 1, 1, .08},
    DETAIL_BG = {0, 0, 0}, DETAIL_BORDER = {.3, .24, .14}, BOX_ACTIVE = {.78, .6, .27},
    BAR_BG = {.06, .05, .04}, BAR_FILL = {.78, .6, .27}, BAR_BORDER = {.78, .6, .27},
    GOLD = {1, .82, 0}, GREY = {.62, .62, .62}, RED = {1, .19, .19},
    RARITY = {magic = {.4, .6, 1}, rare = {1, 1, 0}, legendary = {1, .5, 0}, set = {0, 1, 0}},
}

DC.Style = DC.Style or {backdrop = WINDOW_BACKDROP, flat = FLAT_BACKDROP}
DC.Style.palette = DC.Style.palette or PALETTE

-- ------------------------------------------------------ window skin slots
-- The palette is the window parts' slots: each key is read from its part's field, so a skin
-- that sets ART["tab"] = {colour = {...}} recolours every tab, server windows included (DCUI
-- reads its palette through DC.Style.Colour). The palette above is each slot's default and
-- stays the one copy test_stash_look.lua pins against DCUI. A slot with a `file` is Torment's
-- own art for the windows that draw it as art (the character sheet's and the bounty map's
-- `slot`): its colour is that art's art-off stand-in, so the flat windows keep the palette's
-- value until a skin replaces the slot.
local PALETTE_PARTS = {
    SLOT_BG = {"slot", "colour"}, SLOT_BORDER = {"slot", "edge"},
    TAB_IDLE = {"tab", "colour"}, TAB_ACTIVE = {"tab-active", "colour"},
    DETAIL_BG = {"window-flat", "colour"}, DETAIL_BORDER = {"window-flat", "edge"},
    BOX_BORDER = {"box", "colour"}, BOX_ACTIVE = {"box-active", "colour"},
    ROW_SELECT = {"row-select", "colour"}, ROW_HILITE = {"row-hilite", "colour"},
    BAR_BG = {"bar-bg", "colour"}, BAR_BORDER = {"bar-bg", "edge"}, BAR_FILL = {"bar-fill", "colour"},
}
DC.Style.PALETTE_PARTS = PALETTE_PARTS
for key, where in pairs(PALETTE_PARTS) do
    local art, colour = DC.ART[where[1]], PALETTE[key]
    if not art.file and art[where[2]] == nil then
        art[where[2]] = {colour[1], colour[2], colour[3], colour[4]}
    end
end

function DC.Style.Colour(key)
    local where = PALETTE_PARTS[key]
    local art = where and DC.ART[where[1]]
    return art and not art.file and art[where[2]] or PALETTE[key]
end

-- A part a skin has given an image: a `path` (a skin's own art; `file` is Torment's).
local function imageOf(name)
    local art = DC.ART[name]
    return art and art.path and art or nil
end
-- A stock part a skin has filled: an image, or a colour on a part that has none of its own.
local function skinOf(name)
    local art = DC.ART[name]
    return art and (art.path or (not art.file and art.colour)) and art or nil
end
DC.Style.Image, DC.Style.Skin = imageOf, skinOf

-- Everything painted from a slot, and how: DC.RefreshArt re-runs them, so a window built
-- before a skin loaded (the stash and the sheet are built while Torment loads) wears it
-- from PLAYER_LOGIN on, and a skin that changes a slot later calls DC.RefreshArt itself.
local paints = setmetatable({}, {__mode = "k"})
-- `kind` names the paint ("look" by default), so a frame can carry its backdrop's and its
-- whole-window canvas's at once.
function DC.Style.Paint(region, paint, kind)
    paints[region] = paints[region] or {}
    paints[region][kind or "look"] = paint
    paint(region)
end
DC.Style.painted = paints

local function rgba(target, method, colour)
    target[method](target, colour[1], colour[2], colour[3], colour[4] or 1)
end

-- `window-panel` and `window-flat` are backdrop-shaped: `path` the background, `edgePath`
-- the 8-piece edge strip (UI-DialogBox-Border's shape, the one frame edge 3.3.5 draws),
-- `edgeSize`, `tile`, `tileSize`, `insets`; what a skin leaves out is today's.
local BACKDROPS = {["window-panel"] = WINDOW_BACKDROP, ["window-flat"] = FLAT_BACKDROP}
function DC.Style.Backdrop(name)
    local base, art = BACKDROPS[name], DC.ART[name]
    if not (DC.USE_ART and art and (art.path or art.edgePath)) then return base end
    local function pick(field) if art[field] ~= nil then return art[field] end return base[field] end
    return {bgFile = art.path or base.bgFile, edgeFile = art.edgePath or base.edgeFile, tile = pick("tile"),
            tileSize = pick("tileSize"), edgeSize = pick("edgeSize"), insets = pick("insets")}
end

-- The window backdrop on a frame; a skin's `colour` / `edge` tint it.
function DC.Style.Panel(frame)
    DC.Style.Paint(frame, function(target)
        if target.dcCanvas then return end -- a whole-window skin draws this frame
        target:SetBackdrop(DC.Style.Backdrop("window-panel"))
        local art = skinOf("window-panel")
        if art and art.colour then rgba(target, "SetBackdropColor", art.colour) end
        if art and art.edge then rgba(target, "SetBackdropBorderColor", art.edge) end
    end)
end

-- A part's image as a face over a flat part (a slot, a tab, a box): drawn on the frame's
-- BACKGROUND layer, which sits on the backdrop, so the image covers the flat ground and edge
-- and the icon (ARTWORK) stays on top. No image: the face hides and the flat look shows.
function DC.Style.Face(frame, name)
    local art = imageOf(name)
    if not art then
        if frame.dcFace then frame.dcFace:Hide() end
        return false
    end
    frame.dcFace = frame.dcFace or frame:CreateTexture(nil, "BACKGROUND")
    frame.dcFace:SetAllPoints()
    DC.SetArt(frame.dcFace, name)
    frame.dcFace:Show()
    return true
end

-- A texture the window draws flat (a row's mark, a bar's fill): the part's image when a
-- skin gave one, else false and the caller draws its colour.
function DC.Style.Art(texture, name)
    if not imageOf(name) then return false end
    DC.SetArt(texture, name)
    return true
end

-- The title: a skin's font colour, and its plate behind the title (`width`/`height` in
-- pixels, else the title's own size).
function DC.Style.Title(frame, title)
    local art = skinOf("window-title")
    if not art then return end
    if art.colour then title:SetTextColor(art.colour[1], art.colour[2], art.colour[3]) end
    if art.path then
        local plate = frame.dcTitlePlate or frame:CreateTexture(nil, "ARTWORK")
        frame.dcTitlePlate = plate
        plate:ClearAllPoints()
        plate:SetPoint("CENTER", title, "CENTER", 0, 0)
        plate:SetSize(art.width or title:GetWidth(), art.height or title:GetHeight())
        DC.SetArt(plate, "window-title")
    end
end

-- A native button's states from four slots (normal, hover, pressed, disabled). Each filled
-- slot replaces that state's stock texture; a `slices` normal slot draws three pieces
-- instead (the death window's rule: both ends at their own crop, the middle stretched) and
-- swaps them as the button's state changes.
local STATE_SETTERS = {"SetNormalTexture", "SetHighlightTexture", "SetPushedTexture", "SetDisabledTexture"}
local STATE_GETTERS = {"GetNormalTexture", "GetHighlightTexture", "GetPushedTexture", "GetDisabledTexture"}

local function paintSliced(button, name)
    local art = DC.ART[name]
    local coords, slices = art.coords or {0, 1, 0, 1}, art.slices
    local left, right, top, bottom = coords[1], coords[2], coords[3], coords[4]
    local width, crop = button:GetWidth(), right - left
    local pieces = button.dcSlices
    pieces[1]:ClearAllPoints()
    pieces[1]:SetPoint("TOPLEFT", button, "TOPLEFT", 0, 0)
    pieces[1]:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 0, 0)
    pieces[1]:SetWidth(width * slices.left / crop)
    pieces[3]:ClearAllPoints()
    pieces[3]:SetPoint("TOPRIGHT", button, "TOPRIGHT", 0, 0)
    pieces[3]:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", 0, 0)
    pieces[3]:SetWidth(width * slices.right / crop)
    pieces[2]:ClearAllPoints()
    pieces[2]:SetPoint("TOPLEFT", pieces[1], "TOPRIGHT", 0, 0)
    pieces[2]:SetPoint("BOTTOMRIGHT", pieces[3], "BOTTOMLEFT", 0, 0)
    DC.SetArt(pieces[1], name, {left, left + slices.left, top, bottom})
    DC.SetArt(pieces[2], name, {left + slices.left, right - slices.right, top, bottom})
    DC.SetArt(pieces[3], name, {right - slices.right, right, top, bottom})
end

local function slicedState(button)
    local names = button.dcStates
    local name = names[1]
    if not button:IsEnabled() then name = names[4]
    elseif button.dcPressed then name = names[3]
    elseif button.dcHover then name = names[2] end
    paintSliced(button, skinOf(name) and DC.ART[name].slices and name or names[1])
end

local function slicedButton(button)
    if not button.dcSlices then
        button.dcSlices = {}
        for i = 1, 3 do button.dcSlices[i] = button:CreateTexture(nil, "ARTWORK") end
        local function on(script, field, value)
            button:HookScript(script, function(self)
                if field then self[field] = value end
                slicedState(self)
            end)
        end
        on("OnEnter", "dcHover", true); on("OnLeave", "dcHover", false)
        on("OnMouseDown", "dcPressed", true); on("OnMouseUp", "dcPressed", false)
        on("OnEnable"); on("OnDisable"); on("OnShow")
    end
    for _, getter in ipairs(STATE_GETTERS) do
        local stock = button[getter](button)
        if stock then stock:SetTexture(nil) end
    end
    slicedState(button)
end

function DC.Style.SkinButton(button, names)
    DC.Style.Paint(button, function(target)
        local normal = skinOf(names[1])
        if not normal then return end
        target.dcStates = names
        if normal.slices then return slicedButton(target) end
        target.dcStateArt = target.dcStateArt or {}
        for i, setter in ipairs(STATE_SETTERS) do
            local name = names[i]
            if name and skinOf(name) then
                local texture = target.dcStateArt[i] or target:CreateTexture(nil, i == 2 and "HIGHLIGHT" or "ARTWORK")
                target.dcStateArt[i] = texture
                texture:SetAllPoints()
                DC.SetArt(texture, name)
                target[setter](target, texture)
            end
        end
    end)
end
local BUTTON_STATES = {"button", "button-hover", "button-pressed", "button-disabled"}
local CLOSE_STATES = {"window-close", "window-close-hover", "window-close"}

-- An input box (InputBoxTemplate): a skin's `input` replaces the template's three border
-- pieces with one image.
function DC.Style.Input(box)
    DC.Style.Paint(box, function(target)
        if not skinOf("input") then return end
        for _, region in ipairs({target:GetRegions()}) do
            if region ~= target.dcInput and region:GetObjectType() == "Texture" then region:Hide() end
        end
        target.dcInput = target.dcInput or target:CreateTexture(nil, "BACKGROUND")
        target.dcInput:SetAllPoints()
        DC.SetArt(target.dcInput, "input")
        target.dcInput:Show()
    end)
end

-- A UIPanelScrollFrameTemplate scroll frame (named: the template names its bar
-- <name>ScrollBar): the thumb from `scroll-thumb`, a track behind the bar from `scroll-track`.
function DC.Style.Scroll(scroll)
    DC.Style.Paint(scroll, function(target)
        local name = target:GetName()
        local bar = name and _G[name .. "ScrollBar"]
        if not bar then return end
        if skinOf("scroll-thumb") and bar:GetThumbTexture() then DC.SetArt(bar:GetThumbTexture(), "scroll-thumb") end
        if skinOf("scroll-track") then
            bar.dcTrack = bar.dcTrack or bar:CreateTexture(nil, "BACKGROUND")
            bar.dcTrack:SetAllPoints()
            DC.SetArt(bar.dcTrack, "scroll-track")
        end
    end)
end

-- A whole window: `key` names its slot (`window-<key>`), `parts` its declared title, close,
-- tabs and buttons (a window adds to the tables as it makes them and calls this again). With the
-- slot filled the frame is the canvas's `content` spot: the canvas is drawn around it at the
-- frame's width (one scale for both axes), the generic frame is hidden, and each declared part
-- sits centred on its anchor, at the anchor's size (the title at its width). Nothing happens
-- with the slot empty, or with art off; un-skinning a shown window takes a /reload.
local function place(region, rect, scale, canvas, sized)
    if not (region and rect) then return end
    region:ClearAllPoints()
    region:SetPoint("CENTER", canvas, "TOPLEFT", (rect.left + rect.width / 2) * scale, -(rect.top + rect.height / 2) * scale)
    if sized then region:SetSize(rect.width * scale, rect.height * scale) else region:SetWidth(rect.width * scale) end
end

function DC.Style.Window(frame, key, parts)
    local slot = "window-" .. key
    DC.Style.Paint(frame, function(target)
        local art = DC.USE_ART and imageOf(slot)
        if not (art and art.width and art.height) then return end
        local anchors = art.anchors or {}
        local content = anchors.content or {left = 0, top = 0, width = art.width, height = art.height}
        local scale = target:GetWidth() / content.width
        target:SetBackdrop(nil)
        local canvas = target.dcCanvas or target:CreateTexture(nil, "BACKGROUND")
        target.dcCanvas = canvas
        canvas:ClearAllPoints()
        canvas:SetPoint("TOPLEFT", target, "TOPLEFT", -content.left * scale, content.top * scale)
        canvas:SetSize(art.width * scale, art.height * scale)
        DC.SetArt(canvas, slot)
        canvas:Show()
        place(parts.title, anchors.title, scale, canvas)
        place(parts.close, anchors.close, scale, canvas, true)
        for index, rect in ipairs(anchors.tabs or {}) do place((parts.tabs or {})[index], rect, scale, canvas, true) end
        for index, rect in ipairs(anchors.buttons or {}) do place((parts.buttons or {})[index], rect, scale, canvas, true) end
    end, "window")
end

-- The native close button, the one the sheet's XML inherits and the Jeweler
-- creates: UIPanelCloseButton, six pixels in from the top right corner.
function DC.Style.Close(parent)
    local button = CreateFrame("Button", nil, parent, "UIPanelCloseButton")
    button:SetPoint("TOPRIGHT", parent, "TOPRIGHT", -6, -6)
    DC.Style.SkinButton(button, CLOSE_STATES)
    return button
end

-- The native WoW button: UIPanelButtonTemplate at the dialog's own height.
function DC.Style.Button(parent, width, label, onClick)
    local button = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    button:SetSize(width, 22)
    button:SetText(label)
    if onClick then button:SetScript("OnClick", onClick) end
    DC.Style.SkinButton(button, BUTTON_STATES)
    return button
end
DC.Style.BUTTON_STATES, DC.Style.CLOSE_STATES = BUTTON_STATES, CLOSE_STATES
-- This file's own helpers, for the stash below: whatever a test or an older file later puts in
-- DC.Style, the stash's palette, paint and faces stay these (the backdrop, title, close and
-- button are still read member by member, stashStyle).
local Style = DC.Style

-- The stash is the next window in that look (the list fixed first, then the
-- restyle). Read member by member, the way dc_skillbar.lua reads it, so a DC.Style that
-- carries only part of the helper still draws the right window: the backdrop, the native
-- close button and the native button come from the shared table, each falling back to the
-- same stock frame. The slots and tabs are DCUI's too - the flat
-- ground and the palette - and no Torment art is drawn on the stash at all.
local function stashStyle()
    local shared = DC.Style or {}
    return {
        backdrop = shared.backdrop or WINDOW_BACKDROP,
        flat = shared.flat or FLAT_BACKDROP,
        palette = shared.palette or PALETTE,
        Close = shared.Close or function(parent)
            local button = CreateFrame("Button", nil, parent, "UIPanelCloseButton")
            button:SetPoint("TOPRIGHT", parent, "TOPRIGHT", -6, -6)
            return button
        end,
        Button = shared.Button or function(parent, width, label, onClick)
            local button = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
            button:SetSize(width, 22)
            button:SetText(label)
            if onClick then button:SetScript("OnClick", onClick) end
            return button
        end,
    }
end

-- DCUI's flat panel (U.flat): ground at .85, a 1px edge, both always set, so no flat
-- backdrop is ever left uncoloured (the white-box bug). `ground` and `edge` are palette keys,
-- read through the window parts' slots, and `face` the part whose image a skin may lay over it.
-- It is painted again by DC.RefreshArt, as the stash is built before a skin loads.
local function flatLook(target, ground, edge, face)
    Style.Paint(target, function(panel)
        local fill, line = Style.Colour(ground), Style.Colour(edge)
        panel:SetBackdrop(Style.Backdrop("window-flat"))
        panel:SetBackdropColor(fill[1], fill[2], fill[3], .85)
        panel:SetBackdropBorderColor(line[1], line[2], line[3], 1)
        if face then Style.Face(panel, face) end
    end)
end

-- The hover: the palette's row highlight on a tinted WHITE8X8, as DCUI's list rows draw it,
-- or a skin's `slot-hover` image.
local function hoverLook(button)
    local highlight = button:GetHighlightTexture()
    if not highlight then return end
    Style.Paint(highlight, function(texture)
        if Style.Art(texture, "slot-hover") then return end
        local hilite = Style.Colour("ROW_HILITE")
        texture:SetTexture("Interface\\Buttons\\WHITE8X8")
        texture:SetVertexColor(hilite[1], hilite[2], hilite[3], hilite[4])
    end)
end

-- Published for Stash.lua, which draws the stash in this look.
DC.StashStyle, DC.FlatLook, DC.HoverLook = stashStyle, flatLook, hoverLook
