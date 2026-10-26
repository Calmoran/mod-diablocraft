-- luacheck: globals ElvUI PowerBarColor floor sin unpack CreateFrame hooksecurefunc InCombatLockdown
-- luacheck: globals UnitHealth UnitHealthMax UnitPower UnitPowerMax UnitPowerType UnitIsDeadOrGhost UnitXPMax UnitXP UnitLevel MAX_PLAYER_LEVEL
-- luacheck: globals UnitClass Diablocraft
-- luacheck: ignore 111 121 122 431
-- Run from repo root with `lua mod-diablocraft/scripts/tests/ui/test_orbs_client.lua`.
--
-- Mocks the production layout and event paths of the ElvUI_Torment bar and orbs
-- (client-patch/addons/ElvUI_Torment/barart.lua + orbs.lua + buttonart.lua). It
-- asserts frame geometry, the mock HUD, slot selection and text only: mocks do
-- NOT prove pixels.
--
-- Pinned: the mock bar's rows never reach inside an orb ring (the designer's rule); the
-- mock ring and the designer's delivered fill sheets are what draws with no skin; the
-- D3 art and globes come back through the Diablocraft.ART slots a skin fills;
-- orbScale changes size but not the well centres; nudges survive a power switch;
-- initial values are correct whether the event or the layout arrives first; Rage
-- and Mana change/max events refresh; layout defers in combat. Coordinates are
-- the measured native-art wells (barart GLOBE_WELLS).

unpack = unpack or table.unpack
MAX_PLAYER_LEVEL = 80

-- ------------------------------------------------ the shared widget mock

-- The one shared strict 3.3.5a widget mock (diablocraft-yey2): it owns
-- CreateFrame, UIParent, hooksecurefunc and the rest of the client surface, and
-- hands out neither a public .width/.height (sizes are read through
-- GetWidth/GetHeight) nor a point (the anchors are in .points). A colour
-- SetTexture lands in .textureColor, a texture's layer in .drawLayer/.subLevel.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024, 768)
local frames = Mock.frames

-- The anchor the old per-test stub kept as .point is the LAST SetPoint the addon
-- made; the shared mock keeps every point (the client's GetPoint order).
local function anchor(widget) return widget.points[#widget.points] end

local printed = {}

local combat = false
function InCombatLockdown() return combat end

local unit = {health = 100, healthMax = 100, power = 40, powerMax = 100, token = "RAGE",
              classToken = "WARRIOR", dead = false, level = 70, slots = {}}
function UnitHealth() return unit.health end
function UnitHealthMax() return unit.healthMax end
-- A slot argument reads that slot (a second power); none reads the displayed one.
function UnitPower(_, slot)
    if slot ~= nil then return unit.slots[slot] and unit.slots[slot].power or 0 end
    return unit.power
end
function UnitPowerMax(_, slot)
    if slot ~= nil then return unit.slots[slot] and unit.slots[slot].powerMax or 0 end
    return unit.powerMax
end
function UnitPowerType() return 1, unit.token end
function UnitClass() return unit.classToken, unit.classToken end
function UnitIsDeadOrGhost() return unit.dead end
function UnitXPMax() return 100 end
function UnitXP() return 10 end
function UnitLevel() return unit.level end
PowerBarColor = {RAGE = {r = 1, g = 0, b = 0}, MANA = {r = 0.2, g = 0.4, b = 1},
                 ENERGY = {r = 1, g = 1, b = 0}}
local realPrint = print
function print(msg) printed[#printed + 1] = msg end

-- ElvUI with the ActionBars module and the shared Torment module table.
local module = {}
local AB = {handledBars = {}, PositionAndSizeBar = function() end, StyleButton = function() end}
local E = {
    GetModule = function(_, name) if name == "ActionBars" then return AB end return module end,
    NewModule = function() return module end,
    RegisterModule = function() end,
    Libs = {LAB = {RegisterCallback = function() end}},
    db = {torment = {bar1Scale = 1, bar1OffsetX = 0, bar1OffsetY = 0, xpBar = true,
                     orbScale = 1, orbNudgeX = 0, orbNudgeY = 0, orbText = true, orbFps = 20}},
}
ElvUI = {E}

-- The generated resource list the orb reads (item 4), loaded exactly as the
-- addon ships it, so the class-token + power-token -> resource-key mapping under
-- test is the real one and not a fixture that could drift from the sheet.
assert(loadfile("client-patch/addons/Torment/ResourceNames.lua"))()

-- The only globals the target 3.3.5 client actually has. `floor`/`sin` are
-- real client globals (pinned FrameXML uses them bare 86x/7x); `pi` is NOT —
-- it is math.pi. The guard errors on any other global, so a bare `pi` (or any
-- future unsourced global) fails this test instead of the live client.
local clientGlobals = {
    assert = assert, error = error, ipairs = ipairs, pairs = pairs, select = select,
    tostring = tostring, tonumber = tonumber, type = type, unpack = unpack, print = print,
    math = math, string = string, table = table, floor = math.floor, sin = math.sin,
    _G = _G,
    CreateFrame = CreateFrame, hooksecurefunc = hooksecurefunc, InCombatLockdown = InCombatLockdown,
    ElvUI = ElvUI, PowerBarColor = PowerBarColor, MAX_PLAYER_LEVEL = MAX_PLAYER_LEVEL,
    UnitHealth = UnitHealth, UnitHealthMax = UnitHealthMax, UnitPower = UnitPower,
    UnitPowerMax = UnitPowerMax, UnitPowerType = UnitPowerType, UnitIsDeadOrGhost = UnitIsDeadOrGhost,
    UnitXPMax = UnitXPMax, UnitXP = UnitXP, UnitLevel = UnitLevel, UnitClass = UnitClass,
    Diablocraft = Diablocraft,
}
local function guardEnv(path)
    return setmetatable({}, {
        __index = function(_, key)
            local value = clientGlobals[key]
            if value == nil then
                error(("%s referenced a global unavailable in 3.3.5: %s"):format(path, tostring(key)), 2)
            end
            return value
        end,
    })
end
local function loadGuarded(path)
    local env = guardEnv(path)
    -- 5.1 uses setfenv; 5.2+ passes the environment to loadfile.
    if setfenv then
        local chunk = assert(loadfile(path))
        setfenv(chunk, env)
        return chunk()
    end
    return assert(loadfile(path, "t", env))()
end
-- The guard itself: a chunk using an unavailable global (pi) must fail, proving
-- the mock would catch a regression instead of defining it.
local probe
if setfenv then
    probe = assert(loadstring("return pi"))
    setfenv(probe, guardEnv("guard probe"))
else
    probe = assert(load("return pi", "guard probe", "t", guardEnv("guard probe")))
end
assert(not pcall(probe), "guard must reject the unavailable global pi")
loadGuarded("client-patch/addons/ElvUI_Torment/barart.lua")
loadGuarded("client-patch/addons/ElvUI_Torment/orbs.lua")
-- buttonart.lua is audited too: load it under the same guard with disclosed
-- stubs (E.Libs.LAB.RegisterCallback and AB.StyleButton) and a bare button, so
-- any unsourced global in it fails here.
loadGuarded("client-patch/addons/ElvUI_Torment/buttonart.lua")
assert(type(module.StyleButtons) == "function", "buttonart did not install StyleButtons")

-- Static scan over the production sources, including code the mock never calls:
-- a bare `pi` (the exact class of unsourced alias the designer hit) must fail here even
-- if it is on a path the mock does not exercise. `math.pi` passes; comments are
-- stripped first so the explanatory prose cannot mask or trip the check.
local function stripComments(source)
    source = source:gsub("%-%-%[%[.-%]%]", "")
    return (source:gsub("%-%-[^\n]*", ""))
end
local function assertNoBarePi(path)
    local file = assert(io.open(path, "r"))
    local source = stripComments(file:read("*a"))
    file:close()
    local found = (" " .. source .. " "):find("[^%w_.]pi[^%w_]")
    assert(not found, path .. " contains a bare pi (use math.pi)")
end
assertNoBarePi("client-patch/addons/ElvUI_Torment/orbs.lua")
assertNoBarePi("client-patch/addons/ElvUI_Torment/buttonart.lua")

local function frameWithEvent(event)
    for _, frame in ipairs(frames) do if frame.events[event] then return frame end end
end
local events = frameWithEvent("UNIT_RAGE")
local watcher = frameWithEvent("PLAYER_REGEN_ENABLED")
assert(events and watcher, "expected frames: orb events and bar watcher")

-- The orbs are siblings of the art on the bar (barart.lua). GetArtBar is absent
-- on the pre-fix code, where the orbs are children of the art; falling back to
-- the art keeps the level check below red on that base rather than erroring.
local function orbs()
    local health, power
    local function scan(frame)
        if not frame then return end
        for _, child in ipairs(frame.children) do
            if child.kind == "HEALTH" then health = child end
            if child.kind == "POWER" then power = child end
            scan(child)
        end
    end
    scan(module.GetArtBar and module:GetArtBar() or module:GetArt())
    return health, power
end
local function centre(orb) return anchor(orb)[4], anchor(orb)[5] end

-- The mock HUD's frame is the art's child that carries a texture pool; its
-- frame children with a backdrop are the wells and the micro cells.
local function mockFrame()
    for _, child in ipairs(module:GetArt().children) do
        if child.dcPool then return child end
    end
end
local function countMock(prop)
    local frame, count = mockFrame(), 0
    for _, child in ipairs(frame.children) do
        if child[prop] then count = count + 1 end
    end
    return count
end

-- ------------------------------- event before layout: no error, no stale value

AB.handledBars.bar1 = Mock.widget("Frame")
events.scripts.OnEvent(events, "UNIT_RAGE", "player")
events.scripts.OnEvent(events, "PLAYER_ENTERING_WORLD", "player")
assert(printed[1] == nil, "no missing-fill line for Rage")

-- --------------------------- layout: measured wells, initial values, scale 1

module:Initialize()
local health, power = orbs()
assert(health and power, "both orbs created under the art")
local hx, hy = centre(health)
local px, py = centre(power)
assert(hx == 243 and hy == -100, "health centre at the measured well")
assert(px == 1179 and py == -100, "resource centre at the measured well")
assert(health:GetWidth() == 174 and power:GetWidth() == 178, "orb size is the measured diameter")
assert(health.values.top.text == "100" and health.values.bottom.text == "100", "health initial value")
assert(power.values.top.text == "40" and power.values.bottom.text == "100", "power initial value")

-- --------------------------- the mock HUD: no skin fills a slot

assert(not module:GetArt().texture:IsShown(), "the art texture is hidden while the mock draws")
local mock = mockFrame()
assert(mock and mock:IsShown(), "the mock bar frame is built and shown")
assert(mock.scale == 1, "the mock is scaled with the bar")
assert(countMock("backdrop") == 8 + 10, "eight wells and the ten micro cells")

-- The designer's rule: nothing of the bar shows inside an orb. Every mock row must stop
-- at its ring. The rings are the mockup's: four pixels outside the orb edge.
local function ringLeft(y)
    local dy = y + 0.5 - 100
    if math.abs(dy) >= 91 then return -math.huge end
    return 243 + math.sqrt(91 * 91 - dy * dy)
end
local function ringRight(y)
    local dy = y + 0.5 - 100
    if math.abs(dy) >= 93 then return math.huge end
    return 1179 - math.sqrt(93 * 93 - dy * dy)
end
-- The mock frame's own rows (the bronze band and the panel) and the XP strip
-- band's, which lives on its own child frame (round 2, diablocraft-9z10).
local stripFrame
for _, child in ipairs(mock.children) do
    if child.dcPool then stripFrame = child end
end
assert(stripFrame and stripFrame:IsShown(), "the XP strip band is its own frame")

local rows, cut = 0, 0
for _, frame in ipairs({mock, stripFrame}) do
    for _, texture in ipairs(frame.children) do
        if texture.textureColor and anchor(texture) and anchor(texture)[1] == "TOPLEFT" then
            rows = rows + 1
            local x, y = anchor(texture)[4], -anchor(texture)[5]
            local right = x + texture:GetWidth()
            assert(math.abs(y - math.floor(y)) < 1e-9, "a mock row is 1px tall and on a whole pixel")
            if y >= 96 and y <= 180 then
                if math.abs(y + 0.5 - 100) < 91 then
                    assert(x >= ringLeft(y) - 1e-9, "mock row " .. y .. " reaches into the left ring")
                    cut = cut + 1
                end
                if math.abs(y + 0.5 - 100) < 93 then
                    assert(right <= ringRight(y) + 1e-9, "mock row " .. y .. " reaches into the right ring")
                end
            end
        end
    end
end
-- The fitted panel is 77 rows plus the band, each drawn as its own 1px row.
assert(rows > 60, "the mock panel is one 1px row at a time, got " .. rows)
assert(cut > 0, "the mock rows are cut back to the rings")

-- The mock's own art: the bronze frame, the near-black panel and the XP strip's
-- recess (#6b4e2c / #0c0907 / #0a0705), the mockup's colours.
local function hasColour(frame, colour)
    for _, texture in ipairs(frame.children) do
        if texture.textureColor then
            local c = texture.textureColor
            if math.abs(c[1] - colour[1]) < 1e-6 and math.abs(c[2] - colour[2]) < 1e-6 and
               math.abs(c[3] - colour[3]) < 1e-6 then return true end
        end
    end
    return false
end
assert(hasColour(mock, {0.419608, 0.305882, 0.172549, 1}), "the mock frame is bronze")
assert(hasColour(mock, {0.047059, 0.035294, 0.027451, 0.95}), "the mock panel is near-black")
-- (the XP recess is #0a0705 too, but it draws on its own frame; checked below)

-- diablocraft-rr2e/9z10: the mock's layers bottom to top are the bronze band
-- and the panel on the mock frame, the XP strip's recess and under-edge on their
-- own frame one level above it, and the strip's StatusBar above both. Nothing
-- leans on the client's order for textures in one layer and sublevel or on a
-- child frame following its parent's level, and the frame is a band only, never
-- a full rect under the panel: the panel is the mockup's 0.95, and a bronze rect
-- beneath it would tint it 5% and keep the world behind it from showing.
local function rowAt(frame, colour, y)
    for _, texture in ipairs(frame.children) do
        if texture.textureColor and anchor(texture) and anchor(texture)[1] == "TOPLEFT"
            and math.abs(texture.textureColor[1] - colour[1]) < 1e-6
            and math.abs(texture.textureColor[4] - colour[4]) < 1e-6
            and math.abs(anchor(texture)[5] + y) < 1e-6 then
            return texture
        end
    end
end
assert(stripFrame:GetFrameLevel() > mock:GetFrameLevel(),
    "the strip band draws above the panel, got " .. tostring(stripFrame:GetFrameLevel()) ..
    " against " .. tostring(mock:GetFrameLevel()))
local bronze = {0.419608, 0.305882, 0.172549, 1}
local recess = {0.039216, 0.027451, 0.019608, 1}
local bandRow = assert(rowAt(mock, bronze, 96), "the mock frame's top band draws at row 96")
local panelRow = assert(rowAt(mock, {0.047059, 0.035294, 0.027451, 0.95}, 120),
    "the mock panel draws at row 120")
local recessRow = assert(rowAt(stripFrame, recess, 100), "the mock XP recess draws at row 100")
assert(hasColour(stripFrame, recess), "the mock XP recess is #0a0705")
local edgeRow = assert(rowAt(stripFrame, bronze, 106), "the mock XP under-edge draws at row 106")
assert(bandRow.drawLayer == "ARTWORK" and recessRow.drawLayer == "ARTWORK",
    "the mock rows draw on the ARTWORK layer")
assert(bandRow.subLevel < panelRow.subLevel, "the bronze band draws under the panel")
assert(recessRow.subLevel < edgeRow.subLevel, "the XP recess draws under its bronze edge")
local midBand = rowAt(mock, bronze, 140)
assert(not midBand or midBand:GetWidth() <= 4,
    "the frame's middle is its 4px columns, not a rect under the panel, got " ..
    tostring(midBand and midBand:GetWidth()))

-- Round 2 (diablocraft-9z10): the backdrop is fitted to the eight buttons. The
-- band is the halved ring's 4px, the panel's bottom band hugs the wells' bottom
-- edge, and the strip plus one band is all that sits above them.
local wellsTop, wellsBottom
for _, child in ipairs(mock.children) do
    if child.backdrop and math.abs(child.backdropColor[1] - 0.039216) < 1e-6 then
        local y = -anchor(child)[5]
        if not wellsTop or y < wellsTop then wellsTop = y end
        if not wellsBottom or y + child:GetHeight() > wellsBottom then wellsBottom = y + child:GetHeight() end
    end
end
assert(wellsTop == 110 and wellsBottom == 177, "the wells still run 110..177")
assert(181 - 4 == wellsBottom, "the bottom band starts at the wells' bottom edge")
assert(wellsTop - (100 + 6) <= 4, "the strip and one band are all that sits above the wells")
local wells, micro = 0, 0
for _, child in ipairs(mock.children) do
    if child.backdrop then
        assert(child.borderColor[1] == 0.419608, "a mock cell edge is bronze")
        if math.abs(child.backdropColor[1] - 0.039216) < 1e-6 then wells = wells + 1
        elseif math.abs(child.backdropColor[1] - 0.101961) < 1e-6 then micro = micro + 1 end
    end
end
assert(wells == 8, "eight mock wells, got " .. wells)
assert(micro == 10, "ten mock micro cells, got " .. micro)

-- The orbs: the mock ring covers the whole orb, and the fill is the designer's sheet.
assert(health.back.texture == "Interface\\AddOns\\ElvUI_Torment\\media\\orb_ring",
    "no skin draws the mock ring")
assert(health.globe.path == "Interface\\AddOns\\ElvUI_Torment\\media\\orb_fill_health_1",
    "health uses the designer's delivered sheet")
assert(power.globe.path == "Interface\\AddOns\\ElvUI_Torment\\media\\orb_fill_fury_1",
    "Rage uses the designer's fury sheet")
assert(health.globe.path2 == "Interface\\AddOns\\ElvUI_Torment\\media\\orb_fill_health_2",
    "the fills are two sheets, frames 1-30 and 31-60")
assert(health.globe.frames == 60 and health.globe.cellW == 170 and health.globe.cellH == 170
    and health.globe.cols == 6, "the mock fill is the fixed 60-frame, 170px-cell grid")
assert(not health.glow:IsShown(), "the mock health fill carries no glow pass")
assert(not health.gloss:IsShown() and not power.gloss:IsShown(), "no gloss without a skin")
assert(not health.spark:IsShown(), "no spark without a skin")
assert(not health.lowHP:IsShown() and not health.skull:IsShown(), "no skull or glow without a skin")

-- The 160px disc is scaled to the ring's inner circle: the drawn texture is
-- orb * (164/174) * (170/160) across, centred on the scroll child (the inner
-- fraction is mock_hud_art.py's RING_INNER, the half-thickness ring of round 2).
local inner = health:GetWidth() * (164 / 174)
local drawn = inner * (170 / 160)
assert(anchor(health.liquid)[1] == "BOTTOMRIGHT" and math.abs(-anchor(health.liquid)[4] - (health:GetWidth() - drawn) / 2) < 1e-6,
    "the mock fill's disc fills the ring's inner circle")

-- The XP strip of the mock: one purple fill, inset past the ring's own pixels.
local function findXp(frame)
    for _, child in ipairs(frame.children) do
        if child.kind == "StatusBar" then return child end
    end
end
local xp = findXp(module:GetArt())
assert(xp and xp:IsShown(), "the XP strip draws in the mock")
assert(xp.statusBarColor and math.abs(xp.statusBarColor[1] - 0.541176) < 1e-6,
    "the mock XP strip is the mockup's purple")
-- diablocraft-rr2e: a 3.3.5a StatusBar draws nothing without a status bar
-- texture, so the mock names the flat sheet it tints (the tint above colours
-- nothing without it).
assert(xp.statusBarTexture and xp.statusBarTexture.texture == "Interface\\Buttons\\WHITE8X8",
    "the mock XP strip names its flat sheet, got " ..
    tostring(xp.statusBarTexture and xp.statusBarTexture.texture))
assert(anchor(xp)[4] > ringLeft(100) and anchor(xp)[4] + xp:GetWidth() < ringRight(100),
    "the mock XP strip starts and ends inside the rings")
-- ... and above both mock layers, so neither the panel nor the strip band can
-- cover the fill (diablocraft-9z10).
assert(xp:GetFrameLevel() > stripFrame:GetFrameLevel(),
    "the strip draws above its band, got " .. tostring(xp:GetFrameLevel()) ..
    " against " .. tostring(stripFrame:GetFrameLevel()))
-- At level 70 (Torment's cap) the strip is the mock's purple and shows the
-- Paragon fields the server writes into XP/NEXT_LEVEL_XP: the thin blue bar on
-- The designer's screen was never this one.
unit.level = 70
watcher.scripts.OnEvent(watcher, "PLAYER_XP_UPDATE")
assert(xp.statusBarColor and math.abs(xp.statusBarColor[1] - 0.541176) < 1e-6
    and xp.statusBarTexture.texture == "Interface\\Buttons\\WHITE8X8",
    "at 70 the mock strip is still the flat purple one")
assert(select(1, xp:GetMinMaxValues()) == 0 and select(2, xp:GetMinMaxValues()) == 100
    and xp:GetValue() == 10,
    "at 70 the strip carries the XP fields, got " ..
    tostring(select(1, xp:GetMinMaxValues())) .. "/" .. tostring(select(2, xp:GetMinMaxValues()))
    .. " value " .. tostring(xp:GetValue()))

-- diablocraft-q8r2: both orbs draw UNDER the art, so its ring and the gargoyles
-- cover the liquid. Every frame an orb builds shares the art's strata and sits
-- at a lower level: the orb frame, its ScrollFrame, the scroll child and the
-- overlay (one level each), then the values frame.
local barArt = module:GetArt()
local function assertUnderArt(frame)
    assert(frame:GetFrameStrata() == barArt:GetFrameStrata(),
        frame.kind .. " must be on the art's strata")
    assert(frame:GetFrameLevel() < barArt:GetFrameLevel(),
        frame.kind .. " level " .. tostring(frame:GetFrameLevel()) ..
        " must be under the art's " .. tostring(barArt:GetFrameLevel()))
end
local function walkOrbFrames(frame)
    assertUnderArt(frame)
    for _, child in ipairs(frame.children) do
        if child.kind == "Frame" or child.kind == "ScrollFrame" then walkOrbFrames(child) end
    end
end
walkOrbFrames(health)
walkOrbFrames(power)

-- diablocraft-70cu / diablocraft-cx3j: the orb must read as D3's emissive
-- glass, not as a black plate over a dull globe. Pinned on the frames the addon
-- builds:
--   1. the backing draws UNDER the liquid (on the orb frame, below the scroll
--      child), never over it on the overlay;
--   2. the glass highlight is additive (ADD);
--   3. the liquid's second ADD pass of the same cell - the flat light the D3
--      health sheet carries - sits on the scroll child, above the liquid.
local function assertOrbLayers(orb)
    assert(orb.back and orb.gloss and orb.glow, orb.kind .. " must build back, gloss and glow")
    -- A Texture has no frame level, in the client or in the mock: the backing
    -- draws under the liquid because its PARENT, the orb frame, sits below the
    -- scroll child the liquid hangs on (diablocraft-70cu).
    assert(orb.back:GetParent() == orb
        and orb.back:GetParent():GetFrameLevel() < orb.scrollChild:GetFrameLevel(),
        orb.kind .. " backing must hang on a frame under the liquid's")
    assert(orb.back.drawLayer == "BACKGROUND" and orb.back.subLevel < 0,
        orb.kind .. " backing must be a BACKGROUND texture below the frame's own layer 0")
    assert(orb.gloss.blendMode == "ADD", orb.kind .. " glass highlight must be additive")
    assert(orb.glow.blendMode == "ADD", orb.kind .. " globe glow must be additive")
    assert(orb.glow.texture == orb.liquid.texture,
        orb.kind .. " glow draws the same globe as the liquid")
    assert(orb.glow.parent == orb.scrollChild,
        orb.kind .. " glow must sit on the scroll child (the fill crop clips it)")
    assert(orb.glow.drawLayer == orb.liquid.drawLayer and orb.glow.subLevel > orb.liquid.subLevel,
        orb.kind .. " glow must draw above the liquid")
end
assertOrbLayers(health)
assertOrbLayers(power)

-- The ticker steps on the orb's own clock at the one profile speed; the glow
-- follows the animation cell, so the two passes can never drift apart.
local function sameCoord(a, b)
    if not a or not b then return false end
    for i = 1, 4 do if a[i] ~= b[i] then return false end end
    return true
end
health.globeFrame = 0
health.scripts.OnUpdate(health, 1 / 21)
assert(health.globeFrame == 0, "a step shorter than 1/orbFps does not advance")
health.scripts.OnUpdate(health, 1 / 20 + 1e-9)
assert(health.globeFrame == 1, "at 20 fps one frame advances per 1/20s")
assert(sameCoord(health.glow.texCoord, health.liquid.texCoord),
    "glow follows the liquid's animation cell")

-- The two-sheet fill plays 30 cells from sheet 1 then 30 from sheet 2, then
-- loops: frame 31 is sheet 2's first cell, frame 60 is sheet 1's again.
local function tick(orb) orb.globeElapsed = 1; orb.scripts.OnUpdate(orb, 1 / 20 + 1e-9) end
health.globeFrame = 29
tick(health)
assert(health.liquid.texture == "Interface\\AddOns\\ElvUI_Torment\\media\\orb_fill_health_2"
    and health.globeFrame == 30, "frame 31 is the second sheet's first cell")
health.globeFrame = 59
tick(health)
assert(health.liquid.texture == "Interface\\AddOns\\ElvUI_Torment\\media\\orb_fill_health_1"
    and health.globeFrame == 0, "frame 60 loops back to sheet 1")

-- --------------------------- orbScale resizes ABOUT the well, never moves it

E.db.torment.orbScale = 1.5
module:Apply()
hx, hy = centre(health); px, py = centre(power)
assert(hx == 243 and hy == -100, "orbScale must not move the health centre")
assert(px == 1179 and py == -100, "orbScale must not move the resource centre")
assert(health:GetWidth() == 174 * 1.5 and power:GetWidth() == 178 * 1.5, "orbScale resizes the orbs")
assert(mock.scale == 1, "the mock is not scaled by orbScale")

-- A bar scale change only re-scales the mock (its rows are art pixels).
E.db.torment.bar1Scale = 1.2
module:Apply()
assert(mock.scale == 1.2, "a bar scale change re-scales the drawn mock")
E.db.torment.bar1Scale = 1
module:Apply()

-- --------------------------- combat defers the layout pass

combat = true
E.db.torment.orbScale = 1.2
AB.PositionAndSizeBar(AB, "bar1")
assert(health:GetWidth() == 174 * 1.5, "layout must defer in combat")
combat = false
watcher.scripts.OnEvent(watcher, "PLAYER_REGEN_ENABLED")
hx, hy = centre(health); px, py = centre(power)
assert(health:GetWidth() == 174 * 1.2 and power:GetWidth() == 178 * 1.2, "deferred layout applies out of combat")
assert(hx == 243 and hy == -100 and px == 1179 and py == -100, "deferred layout keeps the wells")

-- --------------------------- the Objective Frame scale rides the same pass

-- E.db.torment.objectiveScale reaches the rift tracker's AIO client half (dc_riftbar.lua)
-- through this apply pass (diablocraft-rift-tracker-exocet-slider), and rides its combat
-- deferral like the rest. Every Apply before this line ran with no tracker at all, so the
-- missing-client guard is covered too.
local scaleSeen
DCRiftTracker = {SetScale = function(value) scaleSeen = value end}
E.db.torment.objectiveScale = 0.8
module:Apply()
assert(scaleSeen == 0.8, "the apply pass must hand the objective scale over, got " .. tostring(scaleSeen))
combat = true
E.db.torment.objectiveScale = 1.1
module:Apply()
assert(scaleSeen == 0.8, "the objective scale must defer in combat with the rest of the pass")
combat = false
watcher.scripts.OnEvent(watcher, "PLAYER_REGEN_ENABLED")
assert(scaleSeen == 1.1, "the deferred objective scale applies out of combat")
DCRiftTracker = nil
E.db.torment.objectiveScale = 1.25

-- --------------------------- nudges survive a power switch

E.db.torment.orbScale = 1
E.db.torment.orbNudgeX, E.db.torment.orbNudgeY = 10, -8
module:Apply()
px, py = centre(power)
assert(px == 1179 + 10 and py == -100 + -8, "nudge applied to the resource centre")

-- Item 4: the fill is chosen by CLASS token + POWER token through the generated
-- Diablocraft.ResourceNames, so two classes on one WoW slot keep their own
-- sheet. MAGE/ENERGY is the Wizard's Arcane Power -> the arcane sheet.
unit.classToken, unit.token = "MAGE", "ENERGY"
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
px, py = centre(power)
assert(px == 1189 and py == -108, "power switch must preserve the nudged layout")
assert(power.globe.path:find("orb_fill_arcane_power") and not power.fallback,
    "MAGE/ENERGY (Arcane Power) uses the arcane sheet")
assert(printed[1] == nil, "no missing-fill line for the Wizard")

unit.classToken, unit.token = "PRIEST", "ENERGY"
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
assert(power.fallback and power.globe.path:find("orb_disc"),
    "a class with no fill art falls back to the stand-in disc")
assert(power.liquid.vertexColor[1] == PowerBarColor.ENERGY.r and power.liquid.vertexColor[3] == PowerBarColor.ENERGY.b,
    "fallback is tinted with PowerBarColor")
assert(power.glow.vertexColor[1] == power.liquid.vertexColor[1] and power.glow.vertexColor[3] == power.liquid.vertexColor[3],
    "fallback glow keeps the same tint as the liquid")
assert(printed[1] == "ElvUI_Torment: no orb fill for ENERGY", "one login line names the missing art")

unit.classToken, unit.token = "WARRIOR", "RAGE"
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
px, py = centre(power)
assert(px == 1189 and py == -108, "switch back keeps the nudged layout")
assert(power.globe.path:find("orb_fill_fury") and not power.fallback, "WARRIOR/RAGE keeps the fury sheet")

-- The Monk's Spirit (MONK/RUNIC_POWER) has its own fill: the Wizard's sheet
-- colour-shifted to tan/white (diablocraft-9k91n), two sheets like the others,
-- both on disk, and no stand-in disc.
unit.classToken, unit.token = "MONK", "RUNIC_POWER"
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
assert(power.globe.path == "Interface\\AddOns\\ElvUI_Torment\\media\\orb_fill_spirit_1"
    and power.globe.path2 == "Interface\\AddOns\\ElvUI_Torment\\media\\orb_fill_spirit_2"
    and not power.fallback, "MONK/RUNIC_POWER (Spirit) uses the spirit sheets, got " .. tostring(power.globe.path))
for _, sheet in ipairs({power.globe.path, power.globe.path2}) do
    local file = io.open(sheet:gsub("^Interface\\AddOns\\", "client-patch/addons/"):gsub("\\", "/") .. ".blp", "rb")
    assert(file, "the spirit sheet is on disk: " .. sheet)
    file:close()
end
unit.classToken, unit.token = "WARRIOR", "RAGE"
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")

-- --------------------------- the power token picks the fill

local SHEET = "Interface\\AddOns\\ElvUI_Torment\\media\\orb_fill_"
-- The rebuilt client reports the class's own token: it names the fill directly,
-- for every token in the generated list, with no class lookup and no stand-in.
for token in pairs(Diablocraft.PowerTokens) do
    unit.classToken, unit.token = "WARRIOR", token
    events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
    assert(power.globe.path == SHEET .. token:lower() .. "_1" and power.globe.path2 == SHEET .. token:lower() .. "_2"
        and not power.fallback, token .. " reported by the client uses its own sheets, got " .. tostring(power.globe.path))
end
-- The stock client reports the slot: the class's row turns it into the token,
-- so the Crusader's Energy is Wrath's sheet and the Wizard's is Arcane Power's.
for classToken, classRows in pairs(Diablocraft.ResourceNames) do
    for slotToken, entry in pairs(classRows) do
        unit.classToken, unit.token = classToken, slotToken
        events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
        assert(power.globe.path == SHEET .. entry.token:lower() .. "_1" and not power.fallback,
            classToken .. "/" .. slotToken .. " uses the " .. entry.token .. " sheet, got " .. tostring(power.globe.path))
        assert(entry.key == entry.token:lower(),
            "a power's sheet and skin slot are named by its token: key " .. entry.key .. " vs " .. entry.token)
    end
end
-- pairs() walks the classes in a different order each run, so the loop above
-- ends on a different class; go back to the Warrior (one power) before asking
-- about a whole orb.
unit.classToken, unit.token = "WARRIOR", "RAGE"
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
-- No orb is split for a class with one power.
assert(not power.half.scrollFrame:IsShown() and not power.divider:IsShown(), "a one-power class draws a whole orb")
assert(power.scrollFrame:GetWidth() == power.size, "a whole orb's liquid spans the orb")

-- --------------------------- a class with a second power: one orb, split

-- The Demon Hunter's two rows as the generator writes them once the class is
-- live (data/tunables/class_resources.csv: Hatred on Energy, Discipline on Mana,
-- role second); the class is planned, so the shipped list has neither yet.
Diablocraft.ResourceNames.DEMONHUNTER = {
    ENERGY = {name = "Hatred", power = 3, role = "primary", key = "hatred", token = "HATRED"},
    MANA = {name = "Discipline", power = 0, role = "second", key = "discipline", token = "DISCIPLINE"},
}
Diablocraft.PowerTokens.HATRED = {name = "Hatred", r = 0.522, g = 0.196, b = 0.082, power = 3}
Diablocraft.PowerTokens.DISCIPLINE = {name = "Discipline", r = 0.380, g = 0.380, b = 0.643, power = 0}
for _, reported in ipairs({"ENERGY", "HATRED"}) do
    unit.classToken, unit.token = "DEMONHUNTER", reported
    unit.power, unit.powerMax = 75, 100
    unit.slots[0] = {power = 10, powerMax = 40}
    events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
    events.scripts.OnEvent(events, "UNIT_MANA", "player")
    local size = power.size
    assert(power.globe.path == SHEET .. "hatred_1", reported .. ": Hatred fills the left half")
    assert(power.half.globe and power.half.globe.path == SHEET .. "discipline_1"
        and power.half.layers[1].texture == SHEET .. "discipline_1", reported .. ": Discipline fills the right half")
    assert(power.half.scrollFrame:IsShown() and power.divider:IsShown(), reported .. ": the orb is split by a line")
    assert(power.scrollFrame:GetWidth() == size / 2 and power.scrollFrame:GetHorizontalScroll() == 0,
        "the left half crops the orb's left side")
    assert(power.half.scrollFrame:GetWidth() == size / 2 and power.half.scrollFrame:GetHorizontalScroll() == size / 2,
        "the right half crops the orb's right side")
    assert(anchor(power.half.scrollFrame)[1] == "BOTTOMLEFT" and anchor(power.half.scrollFrame)[4] == size / 2,
        "the right half sits at the orb's middle")
    -- Each half rises to its own power over its own maximum.
    assert(math.abs(power.scrollFrame:GetHeight() - size * 0.75) < 1e-9, "Hatred 75 of 100 fills three quarters")
    assert(math.abs(power.half.scrollFrame:GetHeight() - size * 0.25) < 1e-9, "Discipline 10 of 40 fills a quarter")
    assert(power.values.top.text == "75" and power.values.bottom.text == "100"
        and power.values.top2.text == "10" and power.values.bottom2.text == "40", "each half shows its own numbers")
    assert(anchor(power.values.top)[2] < 0 and anchor(power.values.top2)[2] > 0, "the numbers sit over their halves")
end
-- A Discipline change alone refreshes its half.
unit.slots[0].power = 30
events.scripts.OnEvent(events, "UNIT_MANA", "player")
assert(math.abs(power.half.scrollFrame:GetHeight() - power.size * 0.75) < 1e-9 and power.values.top2.text == "30",
    "UNIT_MANA moves the Discipline half")
-- Back to a one-power class: the orb is whole again and the second numbers go.
unit.classToken, unit.token = "WARRIOR", "RAGE"
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
assert(not power.half.scrollFrame:IsShown() and not power.divider:IsShown()
    and power.scrollFrame:GetWidth() == power.size and power.values.top2.text == "",
    "a one-power class after a split draws a whole orb")
Diablocraft.ResourceNames.DEMONHUNTER = nil
Diablocraft.PowerTokens.HATRED, Diablocraft.PowerTokens.DISCIPLINE = nil, nil
unit.power, unit.powerMax = 40, 100

-- Every token in the sheet, live or planned, has its pair of sheets on disk: the
-- art is ready before a class goes live, so no class power ever falls back to
-- the flat stand-in disc.
local sheetFile = assert(io.open("mod-diablocraft/data/tunables/class_resources.csv"))
local header = sheetFile:read("*l")
local tokenColumn
local column = 0
for name in header:gmatch("[^,]+") do
    column = column + 1
    if name == "token" then tokenColumn = column end
end
assert(tokenColumn, "the sheet has a token column")
-- Tokens whose orb art is not drawn yet, each named after what clears it. None today: the Maelstrom orb is drawn
-- (maelstrom_orb_fill.py). The check below fails if a listed token already has its sheets, so an entry goes when the
-- art lands.
local awaitingArt = {}
local sheetTokens = 0
for line in sheetFile:lines() do
    local fields = {}
    for field in (line .. ","):gmatch("([^,]*),") do
        fields[#fields + 1] = field
        if #fields == tokenColumn then break end
    end
    local token = fields[tokenColumn]
    sheetTokens = sheetTokens + 1
    for n = 1, 2 do
        local path = "client-patch/addons/ElvUI_Torment/media/orb_fill_" .. token:lower() .. "_" .. n .. ".blp"
        local file = io.open(path, "rb")
        if awaitingArt[token] then
            assert(not file, token .. " has its orb sheet " .. path .. ": drop it from awaitingArt")
        else
            assert(file, token .. " has its orb sheet " .. path)
        end
        if file then file:close() end
    end
end
sheetFile:close()
assert(sheetTokens >= 8, "every sheet row was read, got " .. sheetTokens)
unit.classToken, unit.token = "WARRIOR", "RAGE"
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")

-- --------------------------- change/max events refresh the values

unit.power, unit.powerMax = 55, 120
events.scripts.OnEvent(events, "UNIT_RAGE", "player")
events.scripts.OnEvent(events, "UNIT_MAXRAGE", "player")
assert(power.values.top.text == "55" and power.values.bottom.text == "120", "Rage change/max refresh")

-- The /10 is the engine's (PM ruling 2026-10-17, qmg34): the rebuilt client's
-- UnitPower already returns a 1:1 slot's true value, so the orb shows UnitPower
-- as given. A row moved 1:1 onto the Rage or Runic Power slot (the Barbarian's
-- Fury, the Necromancer's Essence) reads its true number: no x10, no /10 in Lua.
-- Values that are not multiples of 10 so either scaling would show.
for _, case in ipairs({{"WARRIOR", "RAGE", "UNIT_RAGE"}, {"WARRIOR", "FURY", "UNIT_RAGE"},
                       {"NECROMANCER", "RUNIC_POWER", "UNIT_RUNIC_POWER"},
                       {"NECROMANCER", "ESSENCE", "UNIT_RUNIC_POWER"}}) do
    unit.classToken, unit.token = case[1], case[2]
    events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
    unit.power, unit.powerMax = 87, 123
    events.scripts.OnEvent(events, case[3], "player")
    assert(power.values.top.text == tostring(UnitPower("player"))
        and power.values.bottom.text == tostring(UnitPowerMax("player"))
        and power.values.top.text == "87" and power.values.bottom.text == "123",
        case[1] .. "/" .. case[2] .. " shows UnitPower unscaled, got "
        .. tostring(power.values.top.text) .. "/" .. tostring(power.values.bottom.text))
end
unit.classToken, unit.token = "WARRIOR", "RAGE"
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")

unit.token = "MANA"
unit.power, unit.powerMax = 7, 80
events.scripts.OnEvent(events, "UNIT_DISPLAYPOWER", "player")
events.scripts.OnEvent(events, "UNIT_MANA", "player")
events.scripts.OnEvent(events, "UNIT_MAXMANA", "player")
unit.health, unit.healthMax = 20, 100
events.scripts.OnEvent(events, "UNIT_HEALTH", "player")
assert(power.values.top.text == "7" and power.values.bottom.text == "80", "Mana change/max refresh")
assert(health.values.top.text == "20", "health refresh")

-- --------------------------- orbText: one shared toggle, live without reload

E.db.torment.orbText = false
module:Apply()
assert(power.values.top.text == "" and power.values.bottom.text == "", "orbText off clears the power text")
assert(health.values.top.text == "" and health.values.bottom.text == "", "orbText off clears the health text")

E.db.torment.orbText = true
module:Apply()
assert(power.values.top.text == "7" and power.values.bottom.text == "80", "orbText on restores the power text")
assert(health.values.top.text == "20" and health.values.bottom.text == "100", "orbText on restores the health text")

-- --------------------------- a skin fills the slots (TormentD3's own values)

unit.classToken, unit.token = "WARRIOR", "RAGE"
local MEDIA = "Interface\\AddOns\\ElvUI_Torment\\media\\"
Diablocraft.ART = {
    ["bar"] = {path = MEDIA .. "BottomBar_GameRes",
        -- Deliberately not the module's D3 crops, so a strip that reads FILL
        -- instead of the slot's own `fills` fails below (diablocraft-rr2e).
        fills = {blue = {0.11, 0.22, 0.33, 0.44}, orange = {0.55, 0.66, 0.77, 0.88}}},
    ["bar-buttons"] = {path = MEDIA .. "2DUIBottomBar",
        portal = {normal = {1, 2, 3, 4}, highlight = {5, 6, 7, 8}, disabled = {9, 10, 11, 12}}},
    ["orb-health"] = {path = "Interface\\AddOns\\TormentD3\\media\\d3_healthglobe", frames = 60, width = 1024,
                      height = 1024, cellW = 96, cellH = 98, cols = 10, glow = true},
    ["orb-resource-fury"] = {path = "Interface\\AddOns\\TormentD3\\media\\d3_barbarianresourceglobe", frames = 60,
                             width = 1024, height = 256, cellW = 48, cellH = 49, cols = 20},
    ["orb-back"] = {path = "Interface\\AddOns\\TormentD3\\media\\orb_back2"},
    ["orb-gloss"] = {path = "Interface\\AddOns\\TormentD3\\media\\orb_gloss"},
    ["orb-spark"] = {path = "Interface\\AddOns\\TormentD3\\media\\orb_spark"},
    ["orb-lowhp-glow"] = {path = "Interface\\AddOns\\TormentD3\\media\\orb_lowhp_glow"},
    ["orb-skull"] = {path = "Interface\\AddOns\\TormentD3\\media\\d2_skull"},
}
module:Apply()
local health2, power2 = orbs()
assert(health2 == health and power2 == power, "the orbs are the same frames after a skin loads")
assert(module:GetArt().texture:IsShown(), "the skin's bar art draws")
assert(module:GetArt().texture.texture == MEDIA .. "BottomBar_GameRes", "the skin's bar path")
assert(module:GetArt().texture.texCoord[2] == 0.69140625, "the skin's bar crop")
assert(not mockFrame():IsShown(), "the mock hides behind a skin")
-- The same strip in the skin's look: its status bar texture is the sheet its
-- `fills` crop (here the bar-buttons slot's, exactly as TormentD3 names it), and
-- the D3 sheet carries its own colours, so it is not tinted (diablocraft-rr2e).
assert(xp.statusBarTexture and xp.statusBarTexture.texture == MEDIA .. "2DUIBottomBar",
    "the skin's XP strip names its own sheet, got " ..
    tostring(xp.statusBarTexture and xp.statusBarTexture.texture))
assert(xp.statusBarColor[1] == 1 and xp.statusBarColor[2] == 1 and xp.statusBarColor[3] == 1,
    "a skin's XP fill is not tinted")
-- The crop comes from the bar slot's own `fills` (SKINNING.md), never the
-- module's D3 defaults, and the max-level (Paragon) crop is the orange one
-- (2026-09-14 decision: at max level the stock XP fields are Paragon XP).
assert(xp.statusBarTexture.texCoord[1] == 0.11 and xp.statusBarTexture.texCoord[2] == 0.22
    and xp.statusBarTexture.texCoord[3] == 0.33 and xp.statusBarTexture.texCoord[4] == 0.44,
    "the skin's XP fill uses the slot's own crops, got " ..
    tostring(xp.statusBarTexture.texCoord and xp.statusBarTexture.texCoord[1]))
unit.level = 80
watcher.scripts.OnEvent(watcher, "PLAYER_XP_UPDATE")
assert(xp.statusBarTexture.texCoord[1] == 0.55 and xp.statusBarTexture.texCoord[2] == 0.66
    and xp.statusBarTexture.texCoord[3] == 0.77 and xp.statusBarTexture.texCoord[4] == 0.88,
    "at max level the strip uses the slot's Paragon crop, got " ..
    tostring(xp.statusBarTexture.texCoord and xp.statusBarTexture.texCoord[1]))
unit.level = 70
watcher.scripts.OnEvent(watcher, "PLAYER_XP_UPDATE")
assert(health.back.texture == "Interface\\AddOns\\TormentD3\\media\\orb_back2", "the skin's orb-back")
assert(not health.back.texture:find("orb_ring"), "the mock ring is gone")
assert(health.gloss:IsShown() and health.gloss.texture == "Interface\\AddOns\\TormentD3\\media\\orb_gloss",
    "the skin's gloss draws")
assert(health.hasSpark and health.hasSkull and health.hasLowHP, "the health cosmetics come from the slots")
assert(health.globe.path == "Interface\\AddOns\\TormentD3\\media\\d3_healthglobe", "the skin's health globe")
assert(health.globe.glow and health.glow:IsShown(), "the D3 health sheet's light shows through the slot")
assert(power.globe.path == "Interface\\AddOns\\TormentD3\\media\\d3_barbarianresourceglobe",
    "the skin's Barbarian globe for Rage")
assert(not power.glow:IsShown(), "the Barbarian globe is not lit")

-- The skin's globes keep the D3 art's own inset (today's picture).
local inset = health:GetWidth() * 0.06
assert(anchor(health.liquid)[1] == "BOTTOMRIGHT" and math.abs(-anchor(health.liquid)[4] - inset) < 1e-6,
    "a skin's globe keeps the D3 inset")

-- Button 8 draws the skin's portal sprite, so its icon is hidden; the other
-- seven fit their icons into the wells.
local buttons = {}
for index = 1, 8 do
    -- The client's action buttons are Buttons: SetNormalTexture/GetNormalTexture
    -- are Button methods the mock refuses on a plain Frame (buttonart's sprites).
    local button = Mock.widget("Button", "TormentTestButton" .. index)
    _G[button:GetName() .. "Icon"] = Mock.widget("Texture")
    buttons[index] = button
end
AB.handledBars.bar1 = Mock.widget("Frame")
AB.handledBars.bar1.buttons = buttons
module:Apply()
assert(not _G["TormentTestButton8Icon"].shown, "the portal well hides the game icon")
-- A drag that ends on a skill well (1-6) is reported with its slot to the skills
-- window's callback; the potion and portal wells report nothing.
do
    local reported = {}
    module.OnWellDrag = function(slot) reported[#reported + 1] = slot end
    for index = 1, 8 do
        local stop = _G["TormentTestButton" .. index].scripts.OnDragStop
        if stop then stop() end
    end
    assert(table.concat(reported, ",") == "0,1,2,3,4,5",
        "wells 1-6 report slots 0-5 and nothing else does, got " .. table.concat(reported, ","))
    module:Apply()
    reported = {}
    _G["TormentTestButton1"].scripts.OnDragStop()
    assert(#reported == 1, "Apply again does not hook a well twice")
    module.OnWellDrag = nil
    _G["TormentTestButton1"].scripts.OnDragStop()
end
assert(_G["TormentTestButton1Icon"].shown, "the skill wells keep their icons")
Diablocraft.ART["bar-buttons"] = nil
module:Apply()
assert(_G["TormentTestButton8Icon"].shown, "without a skin button 8 is an ordinary well")

-- The mock's micro bar spot: ElvUI's micro bar is anchored at its top-left.
Diablocraft.ART = {}
local microBar = Mock.widget("Frame")
_G.ElvUI_MicroBar = microBar
module:Apply()
assert(anchor(microBar) and anchor(microBar)[2] == module:GetArt() and anchor(microBar)[4] == 925
    and anchor(microBar)[5] == -106, "the micro bar is anchored in the mock's spot")
microBar.points = {}
Diablocraft.ART = {bar = {path = MEDIA .. "BottomGameRes"}}
module:Apply()
assert(anchor(microBar) == nil, "a skin's bar art leaves ElvUI's micro bar alone")
Diablocraft.ART = {}
module:Apply()

-- --------------------------- the shipped hotbar (diablocraft-lhoeu)

-- Torment ships the designer's generated hotbar in the `bar` and `orb-back` slots. Loaded
-- from the addon itself, so the geometry under test is the shipped table.
_G.DEFAULT_CHAT_FRAME = _G.DEFAULT_CHAT_FRAME or {AddMessage = function() end}
_G.PickupContainerItem = _G.PickupContainerItem or function() end
_G.PickupInventoryItem = _G.PickupInventoryItem or function() end
local savedRequire = require
require = nil -- the client has none; Stash.lua asks for AIO through it
dofile("mod-diablocraft/scripts/dc_addon_core.lua")
require = savedRequire
local shipped = Diablocraft.ART["bar"]
assert(shipped and shipped.path and shipped.path:find("hud_bar$"), "Torment ships the hotbar in the bar slot")
microBar.points = {}
microBar:SetSize(140, 70) -- the mock's spot: bigger than the art's opening, so it must shrink
module:Apply()
assert(module:GetArt().texture:IsShown() and module:GetArt().texture.texture == shipped.path,
    "the shipped bar art draws")
assert(not mockFrame():IsShown(), "the mock hides behind the shipped art")
assert(module:GetArt():GetWidth() == shipped.width and module:GetArt():GetHeight() == shipped.height,
    "the art is the shipped canvas")

-- Every opening maps to a button: wells 1-8 carry Bar1's buttons 1-8, each inside
-- the canvas, left to right, none overlapping; the micro opening carries the
-- micro bar, right of the portal.
assert(#shipped.wells == 8, "eight wells: six skills, the potion, Town Portal")
local previousRight = 0
for index = 1, 8 do
    local well, button = shipped.wells[index], buttons[index]
    local point = anchor(button)
    assert(point[1] == "TOPLEFT" and point[2] == module:GetArt() and point[4] == well.left and point[5] == -well.top,
        "button " .. index .. " sits on well " .. index)
    assert(button:GetWidth() == well.width and button:GetHeight() == well.height, "button " .. index .. " fills its well")
    assert(well.left >= previousRight and well.top >= 0 and well.top + well.height <= shipped.height,
        "well " .. index .. " is inside the canvas and right of the one before")
    previousRight = well.left + well.width
end
local spot = shipped.micro
assert(spot and spot.left >= previousRight and spot.left + spot.width <= shipped.width, "the micro opening is right of the portal")
local fit = math.min(1, spot.width / 140, spot.height / 70)
assert(fit < 1 and microBar.scale == fit, "the micro bar shrinks to fit its opening, got " .. tostring(microBar.scale))
local microPoint = anchor(microBar)
assert(microPoint[1] == "CENTER" and microPoint[2] == module:GetArt()
    and math.abs(microPoint[4] * fit - (spot.left + spot.width / 2)) < 1e-9
    and math.abs(microPoint[5] * fit + (spot.top + spot.height / 2)) < 1e-9,
    "the micro bar is centred in its opening")
assert(140 * fit <= spot.width + 1e-9 and 70 * fit <= spot.height + 1e-9, "the shrunk micro bar fits its opening")

-- The orbs sit in the art's holes, with the black glass under the mock's liquid,
-- and the XP strip runs in the art's channel on its own fill sheet.
hx, hy = centre(health); px, py = centre(power)
assert(hx == shipped.globeWells.health.centreX + 10 and hy == -shipped.globeWells.health.centreY - 8,
    "the health orb sits in its hole (with the nudge)")
assert(px == shipped.globeWells.power.centreX + 10 and py == -shipped.globeWells.power.centreY - 8,
    "the power orb sits in its hole (with the nudge)")
assert(health:GetWidth() == shipped.globeWells.health.diameter and power:GetWidth() == shipped.globeWells.power.diameter,
    "the orbs take the art's hole size")
assert(health.back.texture == Diablocraft.ART["orb-back"].path and power.back.texture == Diablocraft.ART["orb-back"].path,
    "the black glass is under the liquid")
assert(health.globe.path:find("orb_fill_health") and power.globe.path:find("orb_fill_fury"),
    "the liquid is still the mock's fills")
assert(not health.gloss:IsShown(), "no gloss slot: the shine is in the bar art")
xp = findXp(module:GetArt()) -- the art was rebuilt on the new Bar1 above
local xpPoint = anchor(xp)
assert(xpPoint[4] == shipped.strip.left and xpPoint[5] == -shipped.strip.top
    and xp:GetWidth() == shipped.strip.width, "the XP strip runs in the art's channel")
assert(xp.statusBarTexture.texture == shipped.stripTexture, "the XP strip draws its own fill sheet")

-- The slots emptied, the mock HUD is back on its own wells.
Diablocraft.ART["bar"], Diablocraft.ART["orb-back"] = {}, {}
module:Apply()
assert(mockFrame():IsShown() and not module:GetArt().texture:IsShown(), "emptied slots bring the mock back")
hx, hy = centre(health)
assert(hx == 243 + 10 and hy == -100 - 8, "and the mock's own globe wells")
assert(health.back.texture:find("orb_ring"), "and the mock ring")
assert(anchor(microBar)[1] == "TOPLEFT" and microBar.scale == 1, "and the mock's micro spot at full size")

-- --------------------------- the mock's own colour constants are the mockup's

realPrint("test_orbs_client: all orb mock checks passed")
