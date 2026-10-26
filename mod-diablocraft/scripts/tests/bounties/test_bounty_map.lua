-- luacheck: ignore 111 113 121 122 611 614
-- Run from the repo root: lua mod-diablocraft/scripts/tests/bounties/test_bounty_map.lua
--
-- client-patch/addons/Torment/BountyMap.lua and the generated MapBounds.lua (diablocraft-dm9vg.6,
-- U1; the wire docs/contracts/bounty-messages.md, the plan docs/research/bounties.md 5.2 and 6)
-- against the strict 3.3.5a widget mock. What it pins:
--   * the file asks for the board once at load (DCBOUNTY list, whispered to the player) and again
--     on PLAYER_LOGIN (a /reload drops the pushed board);
--   * the paged payload: L starts a board, five Z the acts' states, one C a live cell (with its
--     zone), one W a live zone (name and waypoint), E draws it; a board without its E is never drawn
--     (the panel still shows the last one) (acts: diablocraft-hyoic.3, docs/research/bounty-acts.md 2.3);
--   * the columns are headed Act I to Act V, locked or not, and a live cell names its zone (from the
--     W records) beside the quest "!"; a locked cell names nothing;
--   * a record on another prefix, from another sender or another distribution is ignored;
--   * a locked column draws 25 - its live cells locked, and a live cell draws the quest icon and is
--     the teleport button: a click sends travel <column> <cell>;
--   * "New bounties" is dark for a non-leader and while any unlocked column is open, live once the
--     leader, or a solo player, has every unlocked column done (a locked column is not a wait), and
--     a click sends new;
--   * an X refusal is shown as is, and a new board clears it;
--   * a marker sits on its zone's waypoint (diablocraft-dm9vg.15): the W record's world x/y turned
--     through the shown map's rectangle (the core's Map2ZoneCoordinates), the map looked up by the id
--     the client answers with (WorldMapArea row + 1: Kalimdor 14, the rift copy's 3014, Un'Goro 202);
--     the waypoints are the real entrances (rifts.csv), and each lands inside its own zone's DBC
--     rectangle on Kalimdor; nothing on the Eastern Kingdoms (15), whose yards overlap Kalimdor's,
--     nor on a map that does not reach it, nor for a zone whose W has no waypoint;
--   * one waypoint marker per live zone (a W record), drawn on this board or not, at that spot,
--     wearing the compass slot, telling the server the zone key on a click;
--   * the map's own redraws move the markers (hooksecurefunc on WorldMapFrame_OnShow/UpdateMap);
--   * the dock (diablocraft-dm9vg.13): the panel sits outside the map's right edge (WorldMapDetailFrame,
--     never the screen-sized WorldMapFrame), a drag by the panel moves it, the drop keeps its offset from
--     the map's top right per character in DiablocraftUI (scale-corrected), and login applies it;
--   * a cell's zone name box holds the widest word of any act's zone with a tenth spare and wraps to
--     two lines, inside its cell beside the "!"; the act headers stay inside their columns.
--   * the travel cast (dm9vg.10): the player's travel cast shows as a bar in the status line's place, as
--     long as the cast and filling with time; its stop, failure or interrupt takes it away; another
--     spell's cast or another unit's is not the panel's.
-- What this does NOT cover: the look and the real geometry in game (the designer's check on dev), the
-- server half of the board and of the teleport (W1, W5), and the 255-byte paging (the server's,
-- test_bounties.py).

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()

-- ---------------------------------------------------------------- the client surface it uses
local sent = {}
local shown = 14   -- GetCurrentMapAreaID() on the Kalimdor map: WorldMapArea row 13 plus one
local artSlots = {}   -- the (texture, slot) pairs DC.SetArt was handed, in order

_G.UnitName = function() return "Tester" end
_G.SendAddonMessage = function(prefix, body, distribution, target)
    sent[#sent + 1] = { prefix = prefix, body = body, distribution = distribution, target = target }
end
_G.GetCurrentMapAreaID = function() return shown end
_G.WORLDMAP_SETTINGS = { size = 0.691 }
-- The stock map functions the module hooks; the mock's hooksecurefunc refuses a name that is not a
-- function, exactly as the client does.
_G.WorldMapFrame_OnShow = function() end
_G.WorldMapFrame_UpdateMap = function() end
_G.WorldMap_ToggleSizeUp = function() end
_G.WorldMap_ToggleSizeDown = function() end
-- The player's cast, as the client reports it (UnitCastingInfo: name, subtext, text, texture, start ms, end ms).
local now, casting = 100, nil
_G.GetTime = function() return now end
_G.UnitCastingInfo = function(unit)
    if unit == "player" and casting then return casting.name, "", casting.name, "", casting.start, casting.finish end
end
_G.GetSpellInfo = function(id) if id == 83601 then return "Teleporting" end end

_G.WorldMapFrame = Mock.widget("Frame", "WorldMapFrame")
_G.WorldMapFrame:SetSize(1024, 768)
_G.WorldMapDetailFrame = Mock.widget("Frame", "WorldMapDetailFrame")
_G.WorldMapDetailFrame:SetSize(1002, 668)

-- A minimal Diablocraft kit: the panel needs DC.SetArt, DC.Style and DC.ART. (The real ones live in
-- ArtSlots.lua and WindowStyle.lua; loading the core here would drag the whole stash in.)
_G.Diablocraft = {
    ART = { ["bounty-waypoint"] = true },
    SetArt = function(texture, slot) artSlots[#artSlots + 1] = { texture = texture, slot = slot } end,
    Style = {
        flat = {},
        Button = function(parent, width, label, onClick)
            local button = Mock.widget("Button", nil, parent)
            button:SetSize(width, 22)
            button:SetText(label)
            if onClick then button:SetScript("OnClick", onClick) end
            return button
        end,
    },
}

dofile("client-patch/addons/Torment/MapBounds.lua")
dofile(os.getenv("DC_BOUNTY_MAP_LUA") or "client-patch/addons/Torment/BountyMap.lua")   -- the override is for mutants

local DC = _G.Diablocraft
local B = DC.BountyMap

local panel = assert(_G.TormentBountyMapFrame, "the panel frame is named and a client global")
local markerLayer = assert(_G.TormentBountyMapMarkers, "the marker layer is named and a client global")

-- children, in creation order: cells (column then cell) then the New button; regions are the
-- FontStrings (title, five column labels, status line).
local buttons = Mock.childrenOf(panel)
assert(#buttons == 27, "25 cells, the New button and the travel cast bar, got " .. #buttons)
local newButton = buttons[26]
local castBar = buttons[27]
local function cell(column, c) return buttons[(column - 1) * 5 + c] end
local regions = Mock.regionsOf(panel)
assert(#regions == 7, "title, five labels and the status line, got " .. #regions)
local function label(column) return regions[column + 1] end
local statusLine = regions[7]

local watcher
for _, frame in ipairs(Mock.frames) do
    if frame.events and frame.events.CHAT_MSG_ADDON then watcher = frame end
end
assert(watcher, "the module registered a frame for CHAT_MSG_ADDON")

local function chat(message, sender, prefix, distribution)
    watcher.scripts.OnEvent(watcher, "CHAT_MSG_ADDON", prefix or "DCBOUNTY", message,
        distribution or "WHISPER", sender or "Tester")
end
local function push(records)
    for _, message in ipairs(records) do chat(message) end
end
local function lastSent()
    return sent[#sent]
end
local function near(a, b, tolerance)
    return type(a) == "number" and math.abs(a - b) < (tolerance or 0.0005)
end
local function markersShown()
    local out = {}
    for _, frame in ipairs(Mock.childrenOf(markerLayer)) do
        if frame:IsShown() then out[#out + 1] = frame end
    end
    return out
end

-- 1. Load asks for the board once, whispered to the player itself; PLAYER_LOGIN asks again.
assert(#sent == 1 and lastSent().prefix == "DCBOUNTY" and lastSent().body == "list"
    and lastSent().distribution == "WHISPER" and lastSent().target == "Tester",
    "load asks for the board (DCBOUNTY list, whispered to the player)")
watcher.scripts.OnEvent(watcher, "PLAYER_LOGIN")
assert(#sent == 2 and lastSent().body == "list", "PLAYER_LOGIN asks again after a /reload")

-- 2. An X refusal is shown as is.
chat("X|Only the party leader can roll new bounties.")
assert(statusLine:GetText() == "Only the party leader can roll new bounties.", "the refusal text is shown as is")

-- 3. The board as acts (A0, diablocraft-hyoic.1): act I draws Azshara and Moonglade, act II Un'Goro,
-- Tanaris and Thousand Needles, acts III-V are locked. A W names each live zone. Before E nothing is
-- drawn; E draws it.
local LIVE_ZONES = { "W|azshara|Azshara||", "W|moonglade|Moonglade||", "W|ungoro|Un'Goro Crater||",
                     "W|tanaris|Tanaris||", "W|thousandneedles|Thousand Needles||" }
local function acts(leader, one, two, cells)
    local records = { "L|" .. leader, "Z|1|" .. one, "Z|2|" .. two, "Z|3|locked", "Z|4|locked", "Z|5|locked" }
    for _, record in ipairs(cells) do records[#records + 1] = record end
    for _, record in ipairs(LIVE_ZONES) do records[#records + 1] = record end
    records[#records + 1] = "E"
    return records
end
local FIRST = acts(1, "open", "open", {
    "C|1|1|101|kill|0|1|4|Kill The Evalcharr|azshara",
    "C|1|2|102|click|0|1|3|Moonglade objectives|moonglade",
    "C|2|1|201|kill|0|2|3|Kill Ravasaur Matriarch|ungoro",
    "C|2|2|202|kill|0|0|0|Kill Murderous Blisterpaw|tanaris",
    "C|2|3|203|kill|1|3|3|Kill Vile Sting|thousandneedles",
})
for i = 1, #FIRST - 1 do chat(FIRST[i]) end
assert(cell(1, 1).data == nil and not cell(1, 1):IsEnabled(), "a board without its E is not drawn (the previous state stands)")
assert(statusLine:GetText() == "Only the party leader can roll new bounties.", "... and neither is the refusal cleared")
chat("E")

-- 4. The columns are acts, headed Act I to Act V whether locked or not; the live cells name their zones.
for column, name in ipairs({ "Act I", "Act II", "Act III", "Act IV", "Act V" }) do
    assert(label(column):GetText() == name, ("column %d is headed %s, got %s"):format(column, name, tostring(label(column):GetText())))
end
assert(statusLine:GetText() == "", "a drawn board clears the refusal line")
local LIVE = { [1] = 2, [2] = 3, [3] = 0, [4] = 0, [5] = 0 }
for column = 1, 5 do
    for c = 1, 5 do
        local b = cell(column, c)
        if c <= LIVE[column] then
            assert(b:IsEnabled() and b.data and b.icon:IsShown(), ("column %d cell %d is live"):format(column, c))
        else
            assert(not b:IsEnabled() and b.data == nil and not b.icon:IsShown() and b.zone:GetText() == "",
                ("column %d cell %d is locked and names nothing"):format(column, c))
        end
    end
end
local NAMES = { [1] = { "Azshara", "Moonglade" }, [2] = { "Un'Goro Crater", "Tanaris", "Thousand Needles" } }
for column, names in pairs(NAMES) do
    for c, name in ipairs(names) do
        assert(cell(column, c).zone:GetText() == name,
            ("column %d cell %d names %s, got %s"):format(column, c, name, tostring(cell(column, c).zone:GetText())))
    end
end
assert(cell(2, 3).data.title == "Kill Vile Sting" and cell(2, 3).data.done == true, "a done cell keeps its title and state")
assert(cell(1, 2).data.kind == "click" and cell(1, 2).data.need == 3, "a click bounty keeps its kind and need")
assert(cell(2, 1).data.zone == "ungoro", "a cell keeps its zone key")

-- 5. A live cell is the teleport button: a click sends travel <column> <cell>.
sent = {}
cell(2, 3).scripts.OnClick(cell(2, 3))
assert(#sent == 1 and lastSent().prefix == "DCBOUNTY" and lastSent().body == "travel\t2\t3",
    "a live cell asks to travel, got " .. tostring(lastSent() and lastSent().body))

-- 6. New bounties: dark for a non-leader, and dark for the leader while an unlocked act is open.
assert(not newButton:IsEnabled(), "the New button is dark while an act is open")
push(acts(0, "done", "done", { "C|1|1|101|kill|1|4|4|Kill The Evalcharr|azshara" }))
assert(not newButton:IsEnabled(), "a non-leader never gets the New button, even with every act done")
-- A locked act is not a wait: one live act, done, clears the board.
push(acts(1, "done", "locked", { "C|1|1|101|kill|1|4|4|Kill The Evalcharr|azshara" }))
assert(label(2):GetText() == "Act II" and not cell(2, 1):IsEnabled(), "a locked act draws locked, still named")
assert(newButton:IsEnabled(), "the New button is live once every unlocked act is done")
sent = {}
newButton.scripts.OnClick(newButton)
assert(#sent == 1 and lastSent().body == "new", "the New button asks to roll, got " .. tostring(lastSent().body))

-- 7. A record on another prefix, from another sender, or another distribution, is ignored.
push(acts(1, "done", "locked", { "C|1|1|101|kill|1|4|4|Kill The Evalcharr|azshara" }))
local before = cell(1, 1).data
chat("L|0", "Somebody", "DCBOUNTY", "WHISPER")
chat("L|0", "Tester", "DCPYLON", "WHISPER")
chat("L|0", "Tester", "DCBOUNTY", "PARTY")
chat("E")
assert(cell(1, 1).data == before and newButton:IsEnabled(), "only our prefix, our sender and WHISPER reach the reader")

-- 8. The waypoints the server sends, read from the production sheets (rift_open_zones.csv names each
-- zone's entry_tunable; rifts.csv holds <entry_tunable>_x/_y), written to a tenth of a yard as the
-- server's Yards() does; and a W record per zone carrying them.
local function sheetRows(path)
    local rows = {}
    for line in io.lines(path) do rows[#rows + 1] = line end
    return rows
end
local tunable = {}
for _, line in ipairs(sheetRows("mod-diablocraft/data/tunables/rifts.csv")) do
    local name, _, value = line:match("^([^,]*),([^,]*),([^,]*),")
    if name then tunable[name] = tonumber(value) end
end
local ZONES = { "ungoro", "tanaris", "thousandneedles", "azshara", "moonglade" }
local waypoint = {}
for _, line in ipairs(sheetRows("mod-diablocraft/data/d3/rift_open_zones.csv")) do
    local key, _, _, _, _, entry = line:match("^([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),")
    if key and tunable[entry .. "_x"] then
        waypoint[key] = { x = ("%.1f"):format(tunable[entry .. "_x"]), y = ("%.1f"):format(tunable[entry .. "_y"]) }
    end
end
for _, key in ipairs(ZONES) do assert(waypoint[key], key .. " has its entrance on the sheets") end
local function wRecord(key, name)
    return ("W|%s|%s|%s|%s"):format(key, name, waypoint[key].x, waypoint[key].y)
end

-- The spot: hand numbers for three, Kalimdor's rectangle {17066.60, -19733.21, 12799.90, -11733.30}
-- and Un'Goro's {533.33, -3166.67, -5966.67, -8433.33} (WorldMapArea.dbc rows 13 and 201) - not read
-- back from the module. Un'Goro's entrance (-7900.6, -2135.9) is (0.5218, 0.8438) on Kalimdor; Moonglade's
-- (7813.7, -2319.8) and Azshara's (3543.5, -5148.3) are the designer's .gps spots of diablocraft-hyoic.11.
local function spotOf(key, areaID)
    return B.Spot(key, tonumber(waypoint[key].x), tonumber(waypoint[key].y), areaID)
end
local u, v = spotOf("ungoro", 14)
assert(near(u, 0.5218) and near(v, 0.8438), ("Un'Goro's waypoint on Kalimdor at %.4f, %.4f"):format(u or -1, v or -1))
u, v = spotOf("moonglade", 14)
assert(near(u, 0.5268) and near(v, 0.2032), ("Moonglade's waypoint on Kalimdor at %.4f, %.4f"):format(u or -1, v or -1))
u, v = spotOf("azshara", 14)
assert(near(u, 0.6037) and near(v, 0.3773), ("Azshara's waypoint on Kalimdor at %.4f, %.4f"):format(u or -1, v or -1))
u, v = spotOf("ungoro", 202)
assert(near(u, 0.7214) and near(v, 0.7840), ("Un'Goro's waypoint on its own map at %.4f, %.4f"):format(u or -1, v or -1))
local contU, contV = spotOf("ungoro", 14)
local copyU, copyV = spotOf("ungoro", 3014)
assert(near(copyU, contU) and near(copyV, contV), "the rift copy's Kalimdor (3014) is the same map")

-- Each waypoint lands inside its own zone on Kalimdor: inside the zone's own DBC rectangle (its
-- MapBounds row, the client's id) turned through Kalimdor's - the playtest's markers stood a zone north.
local ZONE_MAP = { ungoro = 202, tanaris = 162, thousandneedles = 62, azshara = 182, moonglade = 242 }
local K = DC.MapBounds[14]
for _, key in ipairs(ZONES) do
    local zone = DC.MapBounds[ZONE_MAP[key]]
    local zu1, zu2 = (zone[1] - K[1]) / (K[2] - K[1]), (zone[2] - K[1]) / (K[2] - K[1])
    local zv1, zv2 = (zone[3] - K[3]) / (K[4] - K[3]), (zone[4] - K[3]) / (K[4] - K[3])
    local su, sv = spotOf(key, 14)
    assert(su and su > zu1 and su < zu2 and sv > zv1 and sv < zv2,
        ("%s's marker on Kalimdor (%.4f, %.4f) is inside the zone (u %.4f-%.4f, v %.4f-%.4f)")
            :format(key, su or -1, sv or -1, zu1, zu2, zv1, zv2))
    local ou, ov = spotOf(key, ZONE_MAP[key])
    assert(ou and ou >= 0 and ou <= 1 and ov >= 0 and ov <= 1, key .. "'s marker is on its own zone map")
end

-- Not on the Eastern Kingdoms (15): Kalimdor's yards fall inside its rectangle, but it is world map 0.
assert(spotOf("ungoro", 15) == nil, "no Kalimdor marker on the Eastern Kingdoms map")
assert(spotOf("ungoro", 242) == nil, "no marker on a Kalimdor map that does not reach the waypoint (Moonglade's)")
assert(spotOf("ungoro", 751) == nil, "no marker on another world map's map (the Sanctum)")
assert(spotOf("ungoro", 13) == nil, "13 is not Kalimdor's id in the client (it is the row before Kalimdor's)")
assert(B.Spot("nowhere", 0, 0, 14) == nil, "a zone the addon does not know has no place")
assert(B.Spot("ungoro", nil, nil, 14) == nil, "no waypoint, no place")

-- 9. One waypoint marker per live zone, at that spot, wearing the compass slot: every W, drawn on this
-- board or not (bounty-acts.md 2.3). This board draws Un'Goro alone and names all five live zones.
push({
    "L|1", "Z|1|open", "Z|2|open", "Z|3|locked", "Z|4|locked", "Z|5|locked",
    "C|2|1|201|kill|0|0|0|Kill Ravasaur Matriarch|ungoro",
    wRecord("azshara", "Azshara"), wRecord("moonglade", "Moonglade"), wRecord("ungoro", "Un'Goro Crater"),
    wRecord("tanaris", "Tanaris"), wRecord("thousandneedles", "Thousand Needles"), "E",
})
shown, sent = 14, {}
B.Place()
local markers = markersShown()
assert(#markers == 5, "one marker per live zone, drawn or not, got " .. #markers)
local ungoro
for _, frame in ipairs(markers) do if frame.zoneKey == "ungoro" then ungoro = frame end end
assert(ungoro, "Un'Goro has a marker")
local _, _, _, x, y = ungoro:GetPoint(1)
assert(near(x, 0.5218 * 1002 * 0.691, 0.5) and near(y, -0.8438 * 668 * 0.691, 0.5),
    ("the Un'Goro marker sits on its waypoint, at %.1f, %.1f on the map"):format(x, y))
local woreCompass = false
for _, call in ipairs(artSlots) do
    if call.texture == ungoro.texture and call.slot == "bounty-waypoint" then woreCompass = true end
end
assert(woreCompass, "the marker wears the bounty-waypoint slot")
ungoro.scripts.OnClick(ungoro)
assert(#sent == 1 and lastSent().body == "waypoint\tungoro", "a marker asks for its zone, got " .. tostring(lastSent().body))

-- 10. Hidden where the shown map does not hold the waypoint (the Sanctum, row 750, id 751; the
-- Eastern Kingdoms, 15), and for a zone whose W carries no waypoint (its entrance rows blank).
for _, id in ipairs({ 751, 15 }) do
    shown = id
    B.Place()
    assert(#markersShown() == 0, "no marker on map " .. id)
end
shown = 14
push({ "L|1", "Z|1|locked", "Z|2|open", "Z|3|locked", "Z|4|locked", "Z|5|locked",
       "C|2|1|201|kill|0|0|0|Kill Ravasaur Matriarch|ungoro", "C|2|2|202|kill|0|0|0|Kill Murderous Blisterpaw|tanaris",
       "W|ungoro|Un'Goro Crater||", wRecord("tanaris", "Tanaris"), "E" })
markers = markersShown()
assert(#markers == 1 and markers[1].zoneKey == "tanaris", "a zone without a waypoint has no marker")
assert(markers[1].zoneName == "Tanaris", "the marker carries its W's name for its tooltip")
assert(cell(2, 1).zone:GetText() == "Un'Goro Crater", "a zone without a waypoint still names its cell")

-- 11. The map's own redraws move the markers: the module hooked, never replaced, the stock functions.
assert(Mock.hooks.WorldMapFrame_OnShow and Mock.hooks.WorldMapFrame_UpdateMap,
    "the markers follow the map's own redraws")
sent = {}
_G.WorldMapFrame_OnShow()
assert(#sent == 1 and lastSent().body == "list", "opening the map asks for the board again")

-- 12. The dock: by default the panel's top left is 10 past the map's top right, outside the map,
-- and never on the screen-sized WorldMapFrame (the designer's playtest: it sat at the screen's top right).
local function dockAt()
    local point, relativeTo, relativePoint, ox, oy = panel:GetPoint(1)
    return { point = point, to = relativeTo, rel = relativePoint, x = ox, y = oy }
end
local at = dockAt()
assert(at.point == "TOPLEFT" and at.to == _G.WorldMapDetailFrame and at.rel == "TOPRIGHT" and at.x == 10 and at.y == 0,
    ("docked to the map's right edge, got %s %s %s %s %s"):format(tostring(at.point),
    tostring(at.to and at.to:GetName()), tostring(at.rel), tostring(at.x), tostring(at.y)))
assert(panel.movable and panel.clamped and panel.mouseEnabled and panel.drag and panel.drag[1] == "LeftButton",
    "the panel is movable, kept on screen and takes a left-button drag")
Mock.dragBegin(panel)
assert(panel.moving, "a drag on the panel moves it")

-- 13. The drop keeps the offset from the map's top right, in the panel's units: the map is scaled
-- (0.5 here; 0.691 or 1 in the client), so its edge is turned into the panel's units first. The map's
-- top right is (1202, 768) in its own units, (601, 384) on screen; the panel's top left is (700, 500).
_G.DiablocraftUI = nil
_G.WorldMapDetailFrame:SetScale(0.5)
_G.WorldMapDetailFrame._rect = { 200, 100, 1002, 668 }
panel._rect = { 700, 500 - panel:GetHeight(), panel:GetWidth(), panel:GetHeight() }
panel.userPlaced = true
panel.scripts.OnDragStop(panel)
panel._rect, _G.WorldMapDetailFrame._rect = nil, nil
_G.WorldMapDetailFrame:SetScale(1)
assert(not panel.moving and panel.userPlaced == false, "the drop stops the move and keeps the client's layout cache out")
local stored = _G.DiablocraftUI and _G.DiablocraftUI.bountyPanel
assert(stored and near(stored.x, 99, 0.01) and near(stored.y, 116, 0.01),
    ("the drop keeps (99, 116) from the map's top right, got %s, %s"):format(tostring(stored and stored.x), tostring(stored and stored.y)))
at = dockAt()
assert(at.to == _G.WorldMapDetailFrame and at.rel == "TOPRIGHT" and near(at.x, 99, 0.01) and near(at.y, 116, 0.01),
    "after the drop the panel is docked to the map at that offset")

-- 14. A login applies the saved place (DiablocraftUI is read after the file ran); a broken entry
-- falls back to the default dock.
_G.DiablocraftUI = { bountyPanel = { x = -300, y = -40 } }
panel:ClearAllPoints()
watcher.scripts.OnEvent(watcher, "PLAYER_LOGIN")
at = dockAt()
assert(at.to == _G.WorldMapDetailFrame and at.x == -300 and at.y == -40, "login docks the panel at its saved place")
_G.DiablocraftUI = { bountyPanel = { x = "left" } }
watcher.scripts.OnEvent(watcher, "PLAYER_LOGIN")
at = dockAt()
assert(at.x == 10 and at.y == 0, "a broken saved place falls back to the default dock")

-- 15. A cell's zone name box holds the widest word of any act's zone with a tenth spare and two lines.
-- Widths measured in its font (GameFontNormalSmall: Friz Quadrata at 10, FRIZQT__.ttf, PIL getlength) over
-- every zone of bounty-acts.md 2.1: "Shadowmoon" 54.0 is the widest word, and every name wraps to two lines
-- at 62 / 1.1 ("Blade's Edge" 49.3, "Stranglethorn" 53.5). The mock has no font metrics, so the numbers
-- are stated here, not measured by this test. The box sits right of the "!", inside its cell.
local WIDEST = 54.0
for column = 1, 5 do
    for c = 1, 5 do
        local b = cell(column, c)
        local name = b.zone
        assert(name:GetWidth() >= WIDEST * 1.1, ("column %d cell %d name box %.0f wide"):format(column, c, name:GetWidth()))
        assert(name.wordWrap == true, "a longer name wraps rather than being cut")
        assert(name:GetHeight() >= 2 * 10 + 2, "the name box has room for two lines of a 10-point font")
        local ipoint, ix = b.icon:GetPoint(1)
        local npoint, nto, nrel, nx = name:GetPoint(1)
        assert(ipoint == "LEFT" and npoint == "LEFT" and nto == b.icon and nrel == "RIGHT", "the name sits right of the !")
        assert(ix + b.icon:GetWidth() + nx + name:GetWidth() <= b:GetWidth(), "the name box stays inside its cell")
    end
    local l = label(column)
    local _, lx, ly = l:GetPoint(1)
    local _, cx, cy = cell(column, 1):GetPoint(1)
    assert(ly - l:GetHeight() >= cy, "the act header sits above its column's first cell")
    assert(lx + l:GetWidth() <= cx + cell(column, 1):GetWidth() + 2, "the act header stays inside its column")
end
local _, lastX = label(5):GetPoint(1)
assert(lastX + label(5):GetWidth() <= panel:GetWidth(), "the last column's header is inside the panel")
-- 16. The travel cast (dm9vg.10): a bar in the status line's place while the player's travel cast runs.
local function cast(event, unit) watcher.scripts.OnEvent(watcher, event, unit or "player") end
assert(not castBar:IsShown() and castBar:GetStatusBarTexture(), "the bar is hidden until a cast, and it has its texture")
do  -- the bar sits exactly on the status line, on dm9vg.13's wider layout
    local point, to, rel, ox, oy = castBar:GetPoint(1)
    assert(point == "TOPLEFT" and to == statusLine and rel == "TOPLEFT" and ox == 0 and oy == 0, "the bar is anchored on the status line")
    assert(castBar:GetWidth() == statusLine:GetWidth() and castBar:GetWidth() == panel:GetWidth() - 16, "the bar is the status line's width")
end
casting = { name = "Frostbolt", start = 100000, finish = 101500 }
cast("UNIT_SPELLCAST_START")
assert(not castBar:IsShown(), "another spell's cast is not the panel's")
casting = { name = "Teleporting", start = 100000, finish = 101500 }
cast("UNIT_SPELLCAST_START", "target")
assert(not castBar:IsShown(), "another unit's cast is not the panel's")
cast("UNIT_SPELLCAST_START")
assert(castBar:IsShown() and not statusLine:IsShown(), "the travel cast shows the bar in the status line's place")
assert(castBar.maxValue == 1.5 and castBar.value == 0, "the bar is as long as the cast")
assert(castBar.text:GetText() == "Teleporting", "the bar names the cast")
now = 100.75
castBar.scripts.OnUpdate(castBar, 0.75)
assert(near(castBar.value, 0.75), "the bar fills with time")
cast("UNIT_SPELLCAST_STOP")
assert(not castBar:IsShown() and statusLine:IsShown(), "the cast's end takes the bar away and the status line comes back")
for _, ending in ipairs({ "UNIT_SPELLCAST_INTERRUPTED", "UNIT_SPELLCAST_FAILED" }) do
    cast("UNIT_SPELLCAST_START")
    assert(castBar:IsShown(), "the next travel cast shows again")
    cast(ending)
    assert(not castBar:IsShown() and statusLine:IsShown(), ending .. " takes the bar away")
end

-- -------------------------------------------- failing implementation mutations

-- Mutation A: the spot ignores the shown map. The "no Kalimdor marker on the Eastern Kingdoms map"
-- check must fail.
local realSpot = B.Spot
B.Spot = function(zoneKey) return (zoneKey == "ungoro") and 0.5, 0.5 or nil end
local okSpot = pcall(function()
    assert(spotOf("ungoro", 15) == nil, "shown map")
end)
B.Spot = realSpot
assert(not okSpot, "a spot that ignores the shown map must fail the shown-map check")

-- Mutation B: every board reads as cleared. The "dark while a column is open" check must fail.
local realCleared = B.Cleared
B.Cleared = function() return true end
local okCleared = pcall(function()
    push(FIRST)
    assert(not newButton:IsEnabled(), "an act is open")
end)
B.Cleared = realCleared
assert(not okCleared, "a board that is always cleared must fail the open-column check")

-- Mutation C: any cast shows the bar. The "another spell's cast is not the panel's" check must fail.
local realCast = B.Cast
B.Cast = function(event)
    if event == "UNIT_SPELLCAST_START" then castBar:Show() else castBar:Hide() end
end
local okCast = pcall(function()
    casting = { name = "Frostbolt", start = 100000, finish = 101500 }
    cast("UNIT_SPELLCAST_START")
    assert(not castBar:IsShown(), "another spell's cast")
end)
B.Cast = realCast
cast("UNIT_SPELLCAST_STOP")
assert(not okCast, "a bar for any cast must fail the other-spell check")

-- Mutation D: the bar stays after the cast is interrupted. The interrupt check must fail.
B.Cast = function(event) if event == "UNIT_SPELLCAST_START" then realCast(event) end end
local okStay = pcall(function()
    casting = { name = "Teleporting", start = 100000, finish = 101500 }
    cast("UNIT_SPELLCAST_START")
    cast("UNIT_SPELLCAST_INTERRUPTED")
    assert(not castBar:IsShown(), "interrupted")
end)
B.Cast = realCast
assert(not okStay, "a bar that outlives its interrupted cast must fail the interrupt check")

print("test_bounty_map: OK (paged payload, act headers, cell zone names, locked cells, teleport cells, New bounties, refusals, zone spots, waypoint markers per live zone, map hooks, the dock, drag and saved place, name boxes, the travel cast bar; four mutations fail).")
