-- luacheck: globals Diablocraft CreateFrame GameTooltip UnitName SendAddonMessage hooksecurefunc
-- luacheck: globals WorldMapFrame WorldMapDetailFrame WORLDMAP_SETTINGS WorldMap_ToggleSizeUp WorldMap_ToggleSizeDown
-- luacheck: globals GetCurrentMapAreaID DiablocraftUI UnitCastingInfo GetSpellInfo GetTime
-- The bounty board on the stock world map (the U1 half of the first bounty set; plan
-- docs/research/bounties.md 5.2 and 6).
--
-- OUR frame on the stock map, never an edit of it: a panel docked to the map's right edge (a child of
-- WorldMapFrame, so it shows and hides with the map; dragged by its title, see "the dock" below) and a
-- marker per zone on the map's own rectangles. Nothing here is FrameXML (patch-4.MPQ can never carry a FrameXML file).
--
-- The board is five columns of five cells: a column is an act, headed Act I to Act V, and a cell is one
-- bounty in one of the act's zones (D3's shape; docs/research/bounty-acts.md 2.3).
-- An act with fewer than five live zones draws what it has, the rest of its cells locked; an act with
-- no live zone is locked whole. A live cell names its zone beside the stock quest "!" and is the
-- teleport button: a click asks the server to move the clicker (docs/contracts/bounty-messages.md, Travel).
-- "New bounties" is live for the leader, or a solo player, once every unlocked column is done.
-- From the open world the trip is a cast (instant from the Sanctum): the stock cast bar sits under
-- the map, so the panel draws the travel cast itself, in the status line's place, from the player's own cast events.
--
-- The paged payload: the server sends the board whole, one record a message (L, five Z, one C a live
-- cell, one W a live zone, E). This collects from L and draws on E; a board without its E is never drawn. The wire,
-- the bounds and the budget are docs/contracts/bounty-messages.md and docs/contracts/window-bridge.md.
--
-- A zone waypoint marker (a compass, art/ui/bounties/) sits on its zone's waypoint, where a click
-- sends the player (the zone's entrance; D3's way: the mark is where it takes
-- you), on whatever map the world map shows: one per live zone, drawn on this board or not. The W record
-- carries the waypoint in world yards; the
-- shown map's rectangle (Diablocraft.MapBounds, keyed by GetCurrentMapAreaID()) turns it into a place
-- on the map, on a map of the zone's own world map only (Diablocraft.MapZones: Kalimdor's and the
-- Eastern Kingdoms' rectangles overlap in yards). The placement mirrors FrameXML's own quest POIs
-- (WorldMapFrame_DisplayQuestPOI, WorldMapFrame.lua).

Diablocraft = Diablocraft or {}
local DC = Diablocraft
DC.BountyMap = DC.BountyMap or {}
local B = DC.BountyMap

local PREFIX = "DCBOUNTY"
local COLUMNS, CELLS = 5, 5

local WAYPOINT_SLOT = "bounty-waypoint"     -- DC.ART, art/ui/bounties/
local WAYPOINT_SIZE = 30                    -- the marker art's "about 30x30"; a tunable in the addon
local QUEST_ICON = "Interface\\GossipFrame\\AvailableQuestIcon"   -- the stock "!", D3's bounty mark
local TRAVEL_SPELL = 83601                  -- Shells::BountyTravel, the travel cast (dc_spell_shells.h)
local BAR_TEXTURE = "Interface\\TargetingFrame\\UI-StatusBar"

-- Panel geometry, in pixels. A cell's zone name (GameFontNormalSmall, Friz Quadrata at 10) sits right
-- of a small "!" and wraps to two lines: the widest word of any act's zone, "Shadowmoon", measures
-- 54.0 px, so a name box of 62 keeps a tenth spare and every act zone's name fits two lines (a
-- playtest showed a box narrower than its name cuts it).
local PAD = 8
local COL_W, ROW_H = 84, 42
local MARK_SIZE, NAME_W = 14, 62            -- the cell's "!" and its zone name box, inside COL_W - 2
local ACTS = { "Act I", "Act II", "Act III", "Act IV", "Act V" }
local TITLE_H, COL_HEAD_H, BUTTON_H, STATUS_H, GAP = 20, 26, 22, 14, 6
local PANEL_W = COLUMNS * COL_W + 2 * PAD
local PANEL_H = PAD + TITLE_H + COL_HEAD_H + CELLS * ROW_H + GAP + BUTTON_H + GAP + STATUS_H + PAD
local DOCK_GAP = 10      -- the default gap between the map's right edge and the panel

local board              -- the last whole board, or nil before the first one
local pending            -- the board being collected, or nil when idle
local markers = {}       -- zone key -> the map marker button

local panel, columnLabels, cellButtons, newButton, statusLine, markerLayer, castBar
local castStart, castEnd = 0, 0

-- ---------------------------------------------------------------- the payload

-- `a|b|c` into { "a", "b", "c" }; a record's fields never carry `|` (window-bridge.md).
local function fields(message)
    local out = {}
    for field in (message .. "|"):gmatch("(.-)|") do out[#out + 1] = field end
    return out
end

local function has(text)
    return text ~= nil and text ~= ""
end

-- The whole board is cleared when every column a zone built is done; a locked column is not a wait
-- (docs/contracts/bounty-messages.md), so "New bounties" opens once the live cells are done.
function B.Cleared(source)
    source = source or board
    if not source then return false end
    for column = 1, COLUMNS do
        local info = source.columns[column]
        if info and info.state ~= "locked" and info.state ~= "done" then return false end
    end
    return true
end

local function status(text)
    if statusLine then statusLine:SetText(text or "") end
end

local function redraw()
    if not panel then return end
    for column = 1, COLUMNS do
        local info = board and board.columns[column]
        local locked = (not info) or info.state == "locked"
        local label = columnLabels[column]
        label:SetText(ACTS[column])
        if locked then
            label:SetTextColor(0.45, 0.45, 0.45)
        elseif info.state == "done" then
            label:SetTextColor(0.9, 0.75, 0.35)
        else
            label:SetTextColor(0.7, 0.66, 0.53)
        end
        for cell = 1, CELLS do
            local button = cellButtons[column][cell]
            local data = board and board.cells[column] and board.cells[column][cell]
            if locked or not data then
                DC.SetArt(button.bg, "tab-locked")
                button.icon:Hide()
                button.zone:SetText("")
                button:Disable()
                button.data = nil
            else
                DC.SetArt(button.bg, data.done and "slot-selected" or "slot")
                button.icon:Show()
                button.zone:SetText(board.zoneNames[data.zone] or "")
                button:Enable()
                button.data = data
            end
        end
    end
    if board and board.leader and B.Cleared(board) then newButton:Enable() else newButton:Disable() end
end

local function commit()
    board, pending = pending, nil
    status("")
    redraw()
    B.Place()
end

-- One record. L starts a board, Z an act's state, C a live cell (with its zone), W a live zone (its name
-- and waypoint); E ends it and draws it; X is a refusal, shown as is. A record outside a collection (or a
-- newer tag) is ignored.
function B.Receive(message)
    local field = fields(message)
    local tag = field[1]
    if tag == "L" then
        pending = { leader = field[2] == "1", columns = {}, cells = {}, waypoints = {}, zoneNames = {} }
    elseif tag == "Z" and pending then
        local column = tonumber(field[2])
        if column then
            pending.columns[column] = { state = field[3] or "locked" }
        end
    elseif tag == "C" and pending then
        local column, cell = tonumber(field[2]), tonumber(field[3])
        if column and cell then
            pending.cells[column] = pending.cells[column] or {}
            pending.cells[column][cell] = { bounty = tonumber(field[4]) or 0, kind = field[5] or "",
                                            done = field[6] == "1", progress = tonumber(field[7]) or 0,
                                            need = tonumber(field[8]) or 0, title = field[9] or "",
                                            zone = field[10] or "" }
        end
    elseif tag == "W" and pending then
        if has(field[2]) then
            pending.waypoints[#pending.waypoints + 1] = { key = field[2], name = field[3] or "",
                                                          x = tonumber(field[4]), y = tonumber(field[5]) }
            pending.zoneNames[field[2]] = field[3] or ""
        end
    elseif tag == "E" and pending then
        commit()
    elseif tag == "X" then
        status(field[2] or "")
    end
end

function B.Ask()
    SendAddonMessage(PREFIX, "list", "WHISPER", UnitName("player"))
end

function B.New()
    SendAddonMessage(PREFIX, "new", "WHISPER", UnitName("player"))
end

local function travel(column, cell)
    SendAddonMessage(PREFIX, "travel\t" .. column .. "\t" .. cell, "WHISPER", UnitName("player"))
end

local function waypoint(zoneKey)
    SendAddonMessage(PREFIX, "waypoint\t" .. zoneKey, "WHISPER", UnitName("player"))
end

-- ---------------------------------------------------------------- the map spot

-- The waypoint's place on the map `areaID` shows (GetCurrentMapAreaID's id), as (u, v) in 0..1, or nil
-- when that map is not on one of the zone's world maps or does not reach the waypoint. (x, y) are world
-- yards (WoW's X north, Y west) and the conversion is the core's own Map2ZoneCoordinates: u from world Y,
-- v from world X (the axes swap on a north-up map).
function B.Spot(zoneKey, x, y, areaID)
    local bounds, zones = DC.MapBounds, DC.MapZones
    if not (bounds and zones and zoneKey and x and y and areaID) then return nil end
    local shown, maps = bounds[areaID], zones[zoneKey]
    if not (shown and maps) or (shown[5] ~= maps[1] and shown[5] ~= maps[2]) then return nil end
    local u = (y - shown[1]) / (shown[2] - shown[1])
    local v = (x - shown[3]) / (shown[4] - shown[3])
    if u < 0 or u > 1 or v < 0 or v > 1 then return nil end
    return u, v
end

local function markerFor(zoneKey)
    local marker = markers[zoneKey]
    if marker then return marker end
    marker = CreateFrame("Button", nil, markerLayer)
    marker:SetSize(WAYPOINT_SIZE, WAYPOINT_SIZE)
    marker.texture = marker:CreateTexture(nil, "ARTWORK")
    marker.texture:SetAllPoints(marker)
    DC.SetArt(marker.texture, WAYPOINT_SLOT)
    marker.zoneKey = zoneKey
    marker:SetScript("OnClick", function(self)
        waypoint(self.zoneKey)
    end)
    marker:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(self.zoneName or self.zoneKey)
        GameTooltip:AddLine("Waypoint. Click to travel there.")
        GameTooltip:Show()
    end)
    marker:SetScript("OnLeave", function() GameTooltip:Hide() end)
    markers[zoneKey] = marker
    return marker
end

-- Every live zone the board names (its W records), placed on the map the world map is showing. A zone
-- the shown map does not hold, one without a waypoint (or no board yet) has no place and is hidden.
function B.Place()
    if not markerLayer then return end
    local shownID = GetCurrentMapAreaID and GetCurrentMapAreaID()
    local width, height = WorldMapDetailFrame:GetWidth(), WorldMapDetailFrame:GetHeight()
    local size = (WORLDMAP_SETTINGS and WORLDMAP_SETTINGS.size) or 1
    local active = {}
    for _, info in ipairs(board and board.waypoints or {}) do
        active[info.key] = info
        markerFor(info.key)
    end
    for zoneKey, marker in pairs(markers) do
        local info = active[zoneKey]
        local u, v
        if info then u, v = B.Spot(zoneKey, info.x, info.y, shownID) end
        if u then
            marker.zoneName = info.name
            marker:ClearAllPoints()
            marker:SetPoint("CENTER", markerLayer, "TOPLEFT", u * width * size, -v * height * size)
            marker:Show()
        else
            marker:Hide()
        end
    end
end

-- ---------------------------------------------------------------- the dock

-- Where the panel sits. Its edge is the map's own,
-- WorldMapDetailFrame, in every map size: WorldMapFrame covers the whole screen in the full-size map
-- (FrameXML WorldMapFrame.xml setAllPoints, WorldMap_ToggleSizeUp), so its corner was the screen's. By
-- default the panel's top left touches the map's top right, outside the map; a drag moves it, and what
-- is kept, per character in DiablocraftUI, is that offset from the map's top right, so the panel stays
-- with the map when the map moves or changes size. The client's layout cache is told nothing
-- (SetUserPlaced(false)): the saved variable is the one place.
function B.Dock()
    if not panel then return end
    local saved = DiablocraftUI and DiablocraftUI.bountyPanel
    local x, y = DOCK_GAP, 0
    if saved and tonumber(saved.x) and tonumber(saved.y) then x, y = saved.x, saved.y end
    panel:ClearAllPoints()
    panel:SetPoint("TOPLEFT", WorldMapDetailFrame, "TOPRIGHT", x, y)
end

-- The drop: the panel's top left against the map's top right, in the panel's own units (the map is
-- scaled per size, the panel is not), then docked there.
function B.StopDrag(self)
    self:StopMovingOrSizing()
    self:SetUserPlaced(false)
    local ratio = WorldMapDetailFrame:GetEffectiveScale() / self:GetEffectiveScale()
    DiablocraftUI = DiablocraftUI or {}
    DiablocraftUI.bountyPanel = { x = self:GetLeft() - WorldMapDetailFrame:GetRight() * ratio,
                                  y = self:GetTop() - WorldMapDetailFrame:GetTop() * ratio }
    B.Dock()
end

-- ---------------------------------------------------------------- the frames

local function cellButton(column, cell)
    local button = CreateFrame("Button", nil, panel)
    button.column, button.cell = column, cell
    button:SetSize(COL_W - 2, ROW_H - 2)
    button:SetPoint("TOPLEFT", PAD + (column - 1) * COL_W + 1, -(PAD + TITLE_H + COL_HEAD_H + (cell - 1) * ROW_H + 1))
    button.bg = button:CreateTexture(nil, "BACKGROUND")
    button.bg:SetAllPoints(button)
    button.icon = button:CreateTexture(nil, "ARTWORK")
    button.icon:SetPoint("LEFT", 2, 0)
    button.icon:SetSize(MARK_SIZE, MARK_SIZE)
    button.icon:SetTexture(QUEST_ICON)
    button.zone = button:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    button.zone:SetPoint("LEFT", button.icon, "RIGHT", 2, 0)
    button.zone:SetSize(NAME_W, ROW_H - 4)      -- two lines of the font
    button.zone:SetWordWrap(true)
    button.zone:SetJustifyH("LEFT")
    button:SetScript("OnEnter", function(self)
        if self.data then DC.SetArt(self.bg, "slot-hover") end
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        if self.data then
            GameTooltip:SetText(self.data.title)
            if self.data.done then
                GameTooltip:AddLine("Completed.")
            elseif self.data.kind == "click" then
                GameTooltip:AddLine(("Objectives: %d of %d"):format(self.data.progress, self.data.need))
            elseif self.data.need > 0 then
                GameTooltip:AddLine(("Monsters: %d of %d"):format(self.data.progress, self.data.need))
            else
                GameTooltip:AddLine("Kill the named monster.")
            end
            GameTooltip:AddLine("Click to travel there.")
        else
            GameTooltip:SetText("Locked")
            GameTooltip:AddLine("No bounty on this cell.")
        end
        GameTooltip:Show()
    end)
    button:SetScript("OnLeave", function(self)
        if self.data then DC.SetArt(self.bg, self.data.done and "slot-selected" or "slot") end
        GameTooltip:Hide()
    end)
    button:SetScript("OnClick", function(self)
        if self.data then travel(self.column, self.cell) end
    end)
    cellButtons[column][cell] = button
    return button
end

local function build()
    panel = CreateFrame("Frame", "TormentBountyMapFrame", WorldMapFrame)
    panel:SetSize(PANEL_W, PANEL_H)
    -- Dragged by what the cells leave free (the title, the edges): a cell keeps its click.
    panel:EnableMouse(true)
    panel:SetMovable(true)
    panel:SetClampedToScreen(true)
    panel:RegisterForDrag("LeftButton")
    panel:SetScript("OnDragStart", function(self) self:StartMoving() end)
    panel:SetScript("OnDragStop", B.StopDrag)
    panel:SetFrameStrata(WorldMapFrame:GetFrameStrata())
    panel:SetFrameLevel(WorldMapDetailFrame:GetFrameLevel() + 5)
    -- The flat panel's look from a skin's `window-flat`; the colours stay the panel's own.
    panel:SetBackdrop(DC.Style.Backdrop and DC.Style.Backdrop("window-flat") or DC.Style.flat)
    panel:SetBackdropColor(0.05, 0.04, 0.03, 0.92)
    panel:SetBackdropBorderColor(0.42, 0.32, 0.2, 1)

    local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    title:SetPoint("TOPLEFT", PAD, -PAD)
    title:SetText("Bounties")
    title:SetTextColor(0.91, 0.77, 0.42)

    columnLabels, cellButtons = {}, {}
    for column = 1, COLUMNS do
        local label = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        label:SetPoint("TOPLEFT", PAD + (column - 1) * COL_W, -(PAD + TITLE_H))
        label:SetSize(COL_W - 2, COL_HEAD_H - 2)   -- two lines of the font
        label:SetWordWrap(true)
        label:SetJustifyH("LEFT")
        label:SetJustifyV("BOTTOM")                 -- a one-line name sits on its column
        label:SetText(ACTS[column])
        columnLabels[column] = label
        cellButtons[column] = {}
        for cell = 1, CELLS do cellButton(column, cell) end
    end

    newButton = DC.Style.Button(panel, PANEL_W - 2 * PAD, "New bounties", B.New)
    newButton:SetPoint("TOPLEFT", PAD, -(PAD + TITLE_H + COL_HEAD_H + CELLS * ROW_H + GAP))
    newButton:Disable()
    if DC.Style.Window then DC.Style.Window(panel, "bounty-map", {title = title, buttons = {newButton}}) end

    statusLine = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    statusLine:SetPoint("TOPLEFT", PAD, -(PAD + TITLE_H + COL_HEAD_H + CELLS * ROW_H + GAP + BUTTON_H + GAP))
    statusLine:SetWidth(PANEL_W - 2 * PAD)
    statusLine:SetWordWrap(false)
    statusLine:SetJustifyH("LEFT")
    statusLine:SetTextColor(0.66, 0.61, 0.53)
    statusLine:SetText("")

    castBar = CreateFrame("StatusBar", nil, panel)
    -- In the status line's place, wherever the layout puts it.
    castBar:SetSize(statusLine:GetWidth(), STATUS_H)
    castBar:SetPoint("TOPLEFT", statusLine, "TOPLEFT", 0, 0)
    castBar:SetStatusBarTexture(BAR_TEXTURE)
    castBar:SetStatusBarColor(0.91, 0.77, 0.42)
    castBar:SetMinMaxValues(0, 1)
    castBar.text = castBar:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    castBar.text:SetPoint("CENTER", castBar, "CENTER", 0, 0)
    castBar:SetScript("OnUpdate", function(self) self:SetValue(math.min(GetTime(), castEnd) - castStart) end)
    castBar:Hide()

    markerLayer = CreateFrame("Frame", "TormentBountyMapMarkers", WorldMapFrame)
    markerLayer:SetPoint("TOPLEFT", WorldMapDetailFrame, "TOPLEFT", 0, 0)
    markerLayer:SetSize(WorldMapDetailFrame:GetWidth(), WorldMapDetailFrame:GetHeight())
    markerLayer:SetFrameStrata(WorldMapFrame:GetFrameStrata())
    markerLayer:SetFrameLevel(WorldMapDetailFrame:GetFrameLevel() + 5)
end

build()
redraw()   -- every cell locked until the first board
B.Dock()

-- ---------------------------------------------------------------- the travel cast

-- The player's own cast events: the travel cast shows as a bar in the status line's place while it runs;
-- its end, a failure or an interrupt takes the bar away. Any other cast is not the panel's.
function B.Cast(event)
    if event == "UNIT_SPELLCAST_START" then
        local name, _, _, _, startTime, endTime = UnitCastingInfo("player")
        if not name or name ~= GetSpellInfo(TRAVEL_SPELL) then return end
        castStart, castEnd = startTime / 1000, endTime / 1000
        castBar:SetMinMaxValues(0, castEnd - castStart)
        castBar:SetValue(0)
        castBar.text:SetText(name)
        statusLine:Hide()
        castBar:Show()
    elseif castBar:IsShown() then
        castBar:Hide()
        statusLine:Show()
    end
end

-- ---------------------------------------------------------------- events

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("CHAT_MSG_ADDON")
watcher:RegisterEvent("PLAYER_LOGIN")
for _, event in ipairs({ "UNIT_SPELLCAST_START", "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED",
                         "UNIT_SPELLCAST_INTERRUPTED" }) do
    watcher:RegisterEvent(event)
end
watcher:SetScript("OnEvent", function(_, event, prefix, message, distribution, sender)
    if event:sub(1, 15) == "UNIT_SPELLCAST_" then
        if prefix == "player" then B.Cast(event) end   -- the first argument is the unit
    elseif event == "CHAT_MSG_ADDON" then
        if prefix ~= PREFIX or distribution ~= "WHISPER" or sender ~= UnitName("player") then return end
        B.Receive(message)
    elseif event == "PLAYER_LOGIN" then
        B.Dock()  -- DiablocraftUI is read after the file ran; the saved place applies from here
        B.Ask()   -- a /reload drops the board the server pushed; ask for it again
    end
end)

-- The re-fill: the map's own redraws move the markers onto the map the player is looking at, and
-- opening it asks for the board (docs/contracts/bounty-messages.md). hooksecurefunc, never a
-- replacement: the stock function must still run.
if hooksecurefunc then
    hooksecurefunc("WorldMapFrame_OnShow", function() B.Ask(); B.Place() end)
    hooksecurefunc("WorldMapFrame_UpdateMap", function() B.Place() end)
    if WorldMap_ToggleSizeUp then hooksecurefunc("WorldMap_ToggleSizeUp", function() B.Place() end) end
    if WorldMap_ToggleSizeDown then hooksecurefunc("WorldMap_ToggleSizeDown", function() B.Place() end) end
end

B.Ask()   -- the map may already be up when this addon loads
