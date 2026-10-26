-- luacheck: ignore 111 113 121 122 611 614
-- Run from the repo root: lua mod-diablocraft/scripts/tests/rifts/test_pylon_pins.lua
--
-- client-patch/addons/Torment/Pylons.lua and the generated MapBounds.lua (diablocraft-wylpu, P5
-- of docs/proposals/pylons.md, wire docs/contracts/pylon-messages.md) against the strict 3.3.5a
-- widget mock. What it pins:
--   * the file asks for the list once at load (DCPYLON L, whispered to the player);
--   * MapBounds holds the DBC's own rectangle for the area under the id the client answers with
--     (Durotar: WorldMapArea.dbc row 4, GetCurrentMapAreaID() 5 on 3.3.5a, diablocraft-dm9vg.15);
--   * C drops every pin, S stands one, U drops that one, and a record on another prefix or from
--     another sender is ignored;
--   * the pin's place on the minimap is the world offset turned into pixels - a hundred yards east
--     is right of centre, a hundred yards north is above it, with the player at the map's centre
--     and the minimap 140 px across at 300 yards;
--   * a pin further than the minimap reaches rides its edge, in its true direction;
--   * the pin wears the kind's own icon (the buff record's);
--   * an unknown player position hides the pins rather than drawing them somewhere false;
--   * asking which area the player is in points the world map at their zone once, again after a
--     zone change, and never while the player has the world map open.
--   * north is up and a rotating minimap turns the offsets the player's way; walking toward a pin
--     brings it in; an area with no rectangle hides the pins;
--   * the layer is off by default: a standing object draws no pin, a pin drawn
--     while it was on hides when it is turned off; everything above runs with it on.
-- What this does NOT cover: the look and the real geometry in game (the designer's check on dev), and the
-- server's pushes (test_pylon_objects.py).

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()

-- ---------------------------------------------------------------- the client surface it uses
-- area: what GetCurrentMapAreaID() answers in Durotar, the DBC row ID plus one (build_map_bounds.py).
local sent, syncs, area, positionX, positionY = {}, 0, 5, 0.5, 0.5
local cvars = { minimapZoom = "5", rotateMinimap = "0" }

_G.UnitName = function() return "Tester" end
_G.SendAddonMessage = function(prefix, body, distribution, target)
    sent[#sent + 1] = { prefix = prefix, body = body, distribution = distribution, target = target }
end
_G.GetSpellTexture = function(id) return "icon:" .. tostring(id) end
_G.GetPlayerFacing = function() return 0 end
_G.GetCVar = function(name) return cvars[name] end
_G.SetMapToCurrentZone = function() syncs = syncs + 1 end
_G.GetCurrentMapAreaID = function() return area end
_G.GetPlayerMapPosition = function() return positionX, positionY end
_G.WorldMapFrame = Mock.widget("Frame", "WorldMapFrame")
_G.WorldMapFrame:Hide()   -- the world map is closed in game unless the player opened it
_G.Minimap = Mock.widget("Minimap", "Minimap")
_G.Minimap:SetSize(140, 140)
_G.Minimap.GetZoom = function() return 0 end

dofile("client-patch/addons/Torment/MapBounds.lua")
dofile("client-patch/addons/Torment/Pylons.lua")

local P = _G.Diablocraft.Pylons
local minimap = _G.Minimap

local watcher
for _, frame in ipairs(Mock.frames) do
    if frame.events and frame.events.CHAT_MSG_ADDON then watcher = frame end
end
assert(watcher, "the module registered a frame for CHAT_MSG_ADDON")

local function chat(message, sender, prefix)
    watcher.scripts.OnEvent(watcher, "CHAT_MSG_ADDON", prefix or "DCPYLON", message, "WHISPER", sender or "Tester")
end
local function zoneChanged()
    watcher.scripts.OnEvent(watcher, "ZONE_CHANGED_NEW_AREA")
end
local function tick()
    watcher.scripts.OnUpdate(watcher, P.INTERVAL)
end
local function shownPins()
    local out = {}
    for _, frame in ipairs(Mock.frames) do
        if frame.parent == minimap and frame:IsShown() then out[#out + 1] = frame end
    end
    return out
end
local function near(a, b) return type(a) == "number" and math.abs(a - b) < 0.02 end
local function pointOf(frame)
    local point, _, _, x, y = frame:GetPoint(1)
    return point, x, y
end
local function offsetsOf(frame)
    local _, _, _, x, y = frame:GetPoint(1)
    return x, y
end

-- The geometry the numbers below come from, stated once (not read back from the module):
--   minimap 140 px across, indoor zoom 0 -> 300 yards, so 140/300 = 0.4666... px per yard;
--   the player at GetPlayerMapPosition 0.5, 0.5 on Durotar (row 4, as WorldMapArea.dbc holds it,
--   locLeft -1962.50 locRight -7250.00 locTop 1808.33 locBottom -1716.67):
--     world Y = -1962.50 + 0.5 x (-7250.00 - -1962.50) = -4606.25   (east is -Y)
--     world X =  1808.33 + 0.5 x (-1716.67 -  1808.33) =    45.83   (north is +X)
local PLAYER_X, PLAYER_Y = 45.83, -4606.25
local PER_YARD = 140 / 300

-- 0. The pin layer is off by default: a standing object draws nothing.
assert(P.ENABLED == false, "the pin layer ships off")
chat("S|off|power|45.83|-4606.25")
tick()
assert(#shownPins() == 0, "with the layer off a standing object draws no pin")
P.ENABLED = true
tick()
assert(#shownPins() == 1, "turned on, the object the server sent is drawn")
P.ENABLED = false
tick()
assert(#shownPins() == 0, "turned off again, the drawn pin hides")
chat("C")
P.ENABLED = true

-- 1. Load asks for the list once, whispered to the player itself.
assert(#sent == 1, "load sends one message, got " .. #sent)
assert(sent[1].prefix == "DCPYLON" and sent[1].body == "L" and sent[1].distribution == "WHISPER"
    and sent[1].target == "Tester", "load asks with DCPYLON L to the player")

-- 2. The generated table holds the DBC's rectangle for the area.
local row = _G.Diablocraft.MapBounds[5]
assert(row, "MapBounds has the client's id 5")
assert(near(row[1], -1962.50) and near(row[2], -7250.00) and near(row[3], 1808.33) and near(row[4], -1716.67)
    and row[5] == 1, "id 5 is Durotar (row 4): locLeft/locRight/locTop/locBottom as the DBC holds them, on map 1")
local rowFour = _G.Diablocraft.MapBounds[4]
assert(not (rowFour and near(rowFour[1], -1962.50)), "id 4 is not Durotar: the table is keyed by the client's id")

-- 3. C leaves nothing, an S stands a pin, a record from elsewhere is dropped.
chat("C")
assert(#shownPins() == 0, "C draws no pin")
chat("S|00000000000000AA|power|45.8|-4706.2", "Somebody")
chat("S|00000000000000AA|power|45.8|-4706.2", "Tester", "DCREVIVE")
tick()
assert(#shownPins() == 0, "a record from another sender or prefix stands no pin")

-- 4. A hundred yards east of the player: right of the minimap's centre, the same row. The wire
-- sends one decimal, so the expectation is read from the same numbers the record carries.
local EAST_X, EAST_Y = 45.8, -4706.2      -- ~100 yards east of the player (east is -Y)
chat("S|00000000000000AA|power|" .. EAST_X .. "|" .. EAST_Y)
tick()
local pins = shownPins()
assert(#pins == 1, "S stands one pin, got " .. #pins)
local x, y = offsetsOf(pins[1])
assert(pointOf(pins[1]) == "CENTER", "the pin is anchored by its centre")
assert(near(x, (PLAYER_Y - EAST_Y) * PER_YARD) and near(y, (EAST_X - PLAYER_X) * PER_YARD),
    ("a pin east of the player draws %.2f, %.2f"):format(x, y))

-- 5. The pin wears the kind's own icon: the buff record's texture.
local icon = pins[1]:GetRegions()
assert(icon and icon:GetTexture() == "icon:83500", "the power pin wears the buff record's icon")

-- 6. A hundred yards north: above the centre (the minimap is north-up; north is +X).
local NORTH_X, NORTH_Y = 145.8, -4606.2
chat("C")
chat("S|00000000000000BB|blessed|" .. NORTH_X .. "|" .. NORTH_Y)
tick()
pins = shownPins()
assert(#pins == 1, "C then S leaves exactly one pin")
x, y = offsetsOf(pins[1])
-- SetPoint's y grows UP: the expected value is the north offset itself, not a copy of the module's
-- formula (a copy of the formula would pass a pin north of the player drawn south).
assert(near(x, (PLAYER_Y - NORTH_Y) * PER_YARD) and near(y, (NORTH_X - PLAYER_X) * PER_YARD) and y > 40,
    ("a pin north of the player draws above the centre, got %.2f, %.2f"):format(x, y))
assert(pins[1]:GetRegions():GetTexture() == "icon:83505", "the blessed pin wears its own record's icon")

-- 7. Further than the minimap reaches: on the edge, in that direction.
chat("C")
chat("S|00000000000000CC|speed|45.8|-5606.2")   -- 1000 yards east
tick()
pins = shownPins()
assert(#pins == 1, "a far pin is still drawn")
x, y = offsetsOf(pins[1])
local limit = 140 / 2 - P.SIZE / 2
assert(near(x, limit) and near(y, 0), ("a far pin rides the edge at %.2f, %.2f"):format(x, y))

-- 8. U drops that one pin and no other.
chat("S|00000000000000DD|power|" .. EAST_X .. "|" .. EAST_Y)
tick()
assert(#shownPins() == 2, "two standing pylons draw two pins")
chat("U|00000000000000CC")
tick()
assert(#shownPins() == 1, "U drops the pin it names")
pins = shownPins()
assert(near(select(2, pointOf(pins[1])), (PLAYER_Y - EAST_Y) * PER_YARD), "the other pin has not moved")

-- 9. An unknown player position hides every pin rather than drawing them somewhere false.
positionX, positionY = 0, 0
tick()
assert(#shownPins() == 0, "no map position, no pins")
positionX, positionY = 0.5, 0.5

-- 10. Which area the player is in is asked once, and re-asked when the zone changes; while the
-- world map is open it belongs to the player and is left alone.
assert(syncs == 1, "load points the world map at the player's zone once, got " .. syncs)
zoneChanged()
assert(syncs == 2, "a zone change asks again, got " .. syncs)
_G.WorldMapFrame:Show()
zoneChanged()
assert(syncs == 2, "with the world map open nothing is asked, got " .. syncs)
_G.WorldMapFrame:Hide()

-- 11. A rotating minimap: facing west (GetPlayerFacing pi/2, counter-clockwise from
-- north), west is up, so a pin a hundred yards west draws above the centre; facing north it is left.
local WEST_X, WEST_Y = 45.83, -4506.25   -- 100 yards west of the player (west is +Y)
chat("C")
chat("S|00000000000000EE|power|" .. WEST_X .. "|" .. WEST_Y)
cvars.rotateMinimap = "1"
_G.GetPlayerFacing = function() return math.pi / 2 end
tick()
x, y = offsetsOf(shownPins()[1])
assert(near(x, 0) and near(y, 100 * PER_YARD), ("facing west, a pin to the west is straight up, got %.2f, %.2f"):format(x, y))
_G.GetPlayerFacing = function() return 0 end
tick()
x, y = offsetsOf(shownPins()[1])
assert(near(x, -100 * PER_YARD) and near(y, 0), ("facing north, it is to the left, got %.2f, %.2f"):format(x, y))
cvars.rotateMinimap = "0"

-- 12. Following a pin brings it to the centre: the player walks fifty yards north toward a pin a
-- hundred yards north (a mirrored pin runs away from a player following it).
chat("C")
chat("S|00000000000000FF|power|" .. NORTH_X .. "|" .. NORTH_Y)
tick()
local _, before = offsetsOf(shownPins()[1])
positionY = 0.5 - 50 / (1808.33 + 1716.67)   -- world X grows north as the map position goes up
tick()
local _, after = offsetsOf(shownPins()[1])
assert(after > 0 and after < before and near(after, before / 2),
    ("walking toward the pin brings it halfway in, %.2f then %.2f"):format(before, after))
positionY = 0.5

-- 13. An instance the client has no world map for (an area id MapBounds has no row for): a pin drawn
-- before hides rather than standing frozen where it was.
tick()
assert(#shownPins() == 1, "a pin stands before the move")
area = 99999
zoneChanged()
tick()
assert(#shownPins() == 0, "an area with no rectangle hides the pins")
area = 5
zoneChanged()
tick()
assert(#shownPins() == 1, "back on a mapped area, the pin is drawn again")

print("test_pylon_pins: OK")
