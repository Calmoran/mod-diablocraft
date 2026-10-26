-- luacheck: globals ElvUI unpack
-- luacheck: ignore 111 121 122 431 631
-- Run from the repo root with `lua mod-diablocraft/scripts/tests/ui/test_elvui_damagetext.lua`.
--
-- The damage numbers, the addon half (docs/contracts/damage-text.md): the Torment
-- client module queues each hit and projects world points; ElvUI_Torment's
-- damagetext.lua draws them and options.lua holds the settings. This drives the
-- real files with a fake module behind the two globals.
--
-- Mocks do NOT prove pixels: what the designer sees is on the Checks of
-- docs/test-diablocraft-xw7zr.md.

unpack = unpack or table.unpack

local function read(path)
    local file = assert(io.open(path, "r"), "cannot read " .. path)
    local text = file:read("*a")
    file:close()
    return text
end

-- ------------------------------------------------------------ client env

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
local OPTIONAL = {TormentDamageTextRead = true, TormentWorldToScreen = true}

local function newEnv(withModule)
    local clientGlobals = {
        assert = assert, error = error, ipairs = ipairs, pairs = pairs, next = next, select = select,
        tostring = tostring, tonumber = tonumber, type = type, unpack = unpack, print = function() end,
        math = math, string = string, table = table,
    }
    Mock.frames = {}
    Mock.install(clientGlobals)
    Mock.setScreen(1024, 768)
    local now = 100
    -- The fan's random angle comes from math.random; a test sets the next draws.
    local draws = {}
    clientGlobals.math = setmetatable({
        random = function(...)
            assert(select("#", ...) == 0, "the fan draws a share from 0 to 1")
            return table.remove(draws, 1) or math.random()
        end,
    }, {__index = math})
    clientGlobals.GetTime = function() return now end
    clientGlobals.Diablocraft = false
    clientGlobals.UnitGUID = function() return "Player-1" end
    clientGlobals.UnitName = function() return "Tester" end
    clientGlobals.DiablocraftUI = {}
    clientGlobals.MoneyFrame_Update = function() end
    clientGlobals.MAX_ITEM_COST = 3
    clientGlobals.GetMerchantNumItems = function() return 0 end
    clientGlobals.GetMerchantItemCostItem = function() return nil end
    clientGlobals.GetItemIcon = function() return nil end
    clientGlobals.MerchantFrame_Update = function() end
    clientGlobals.SlashCmdList = {}
    if not clientGlobals.MerchantFrame then
        Mock.widget("Frame", "MerchantFrame"):Hide()
        Mock.widget("Frame", "MerchantMoneyFrame")
    end

    local fake = {queue = {}, reads = 0, project = function(x, y, z) return x * 10, y * 10 + z end}
    if withModule then
        clientGlobals.TormentDamageTextRead = function()
            fake.reads = fake.reads + 1
            local hit = table.remove(fake.queue, 1)
            if not hit then return nil end
            return unpack(hit, 1, 10)
        end
        clientGlobals.TormentWorldToScreen = function(x, y, z) return fake.project(x, y, z) end
    end

    -- ElvUI: the engine table, the shared-media library, the plugin list.
    local registered = {}
    local LSM = {
        Register = function(_, kind, name, path) registered[kind .. ":" .. name] = path end,
        Fetch = function(_, kind, name) return registered[kind .. ":" .. tostring(name)] end,
    }
    local plugin
    local module = {}
    local E = {db = {}, private = {general = {dmgfont = "PT Sans Narrow"}},
               Libs = {LSM = LSM, EP = {RegisterPlugin = function(_, _, fn) plugin = fn end}}}
    -- ElvUI's own: re-fetches its fonts (E:UpdateMedia, Core.lua); the CombatText
    -- Font's option sets E.private.general.dmgfont and calls it.
    function E:UpdateMedia() self.media = {combatFont = LSM:Fetch("font", self.private.general.dmgfont)} end
    function E:GetModule(name)
        assert(name == "ElvUI_Torment", "asks for its own module only")
        return module
    end
    E.Options = {args = {}}
    clientGlobals.ElvUI = {E, {}, {}, {}, {}}
    clientGlobals.AceGUIWidgetLSMlists = {font = registered}

    local env = setmetatable({}, {
        __index = function(_, key)
            local value = clientGlobals[key]
            -- The client module's two globals are absent without the DLL; reading
            -- them answers nil there, as here.
            if value == nil and not OPTIONAL[key] then
                error("a loaded file referenced a global unavailable in 3.3.5: " .. tostring(key), 2)
            end
            return value
        end,
        __newindex = clientGlobals,
    })
    clientGlobals._G = env
    local function load(path, ...)
        if setfenv then
            local chunk = assert(loadfile(path))
            setfenv(chunk, env)
            return chunk(...)
        end
        return assert(loadfile(path, "t", env))(...)
    end
    load("client-patch/addons/Torment/Economy.lua")
    load("client-patch/addons/ElvUI_Torment/damagetext.lua", "ElvUI_Torment")
    load("client-patch/addons/ElvUI_Torment/options.lua", "ElvUI_Torment")
    plugin()
    return {
        E = E, env = clientGlobals, fake = fake, module = module, registered = registered,
        P = clientGlobals.ElvUI[4].torment, page = E.Options.args.torment,
        advance = function(seconds) now = now + seconds end,
        draw = function(...) for _, value in ipairs({...}) do draws[#draws + 1] = value end end,
    }
end

local function layerOf()
    for _, frame in ipairs(Mock.frames) do
        if frame:GetName() == "TormentDamageText" then return frame end
    end
end

local function tick(t)
    local layer = layerOf()
    layer:GetScript("OnUpdate")(layer, 0)
    return layer
end

local function liveStrings(layer)
    local out = {}
    for _, region in ipairs(Mock.regionsOf(layer)) do
        if region:GetObjectType() == "FontString" and region:IsShown() then out[#out + 1] = region end
    end
    return out
end

-- kind, amount, school, crit, periodic, own, x, y, z, word
local function hit(amount, school, crit, periodic)
    return {"damage", amount, school or 1, crit or false, periodic or false, true, 10, 20, 0, nil}
end

-- ---------------------------------------------- 1. no client module: nothing draws

do
    local t = newEnv(false)
    assert(layerOf() == nil, "without the client module no drawing frame is made")
    assert(t.module.DamageText, "the formatter and the element list still load for the settings page")
    assert(t.page.args.damageText, "and the settings page still shows its settings")
end

-- ------------------------------------------- 2. the element colour, from the server's school

local t = newEnv(true)

-- Cross-source: the school each element maps to is the server's own map.
local header = read("mod-diablocraft/src/combat/dc_combat_internal.h")
local MASKS = {NORMAL = 1, HOLY = 2, FIRE = 4, NATURE = 8, FROST = 16, SHADOW = 32, ARCANE = 64}
local serverMap = {}
for element, mask in header:gmatch('element == "(%a+)"%)%s*return SPELL_SCHOOL_MASK_(%u+);') do
    serverMap[MASKS[mask]] = element
end
assert(next(serverMap), "the server's element map is found in dc_combat_internal.h")
serverMap[1] = "physical"
local SCHOOL_ELEMENT = t.module.DamageText.SCHOOL_ELEMENT
for mask, element in pairs(serverMap) do
    assert(SCHOOL_ELEMENT[mask] == element,
        "school " .. mask .. " is " .. element .. " on the server, " .. tostring(SCHOOL_ELEMENT[mask]) .. " here")
end
for mask in pairs(SCHOOL_ELEMENT) do
    assert(serverMap[mask], "school " .. mask .. " has no element on the server")
end

-- Cross-source: the default colours are the skills window's element palette (q-1014-30 a).
local skillbar = read("mod-diablocraft/lua/aio/dc_skillbar.lua")
local palette = skillbar:match("local ELEMENT = (%b{})")
assert(palette, "the skills window's ELEMENT palette is found")
local count = 0
for element, r, g, b in palette:gmatch("(%a+) = {([%d.]+), ([%d.]+), ([%d.]+)}") do
    local default = t.P.damageColors[element]
    assert(default, "the palette's " .. element .. " has a default picker colour")
    assert(default.r == tonumber(r) and default.g == tonumber(g) and default.b == tonumber(b),
        element .. " defaults to the palette's colour")
    count = count + 1
end
assert(count == 7, "seven elements in the palette, got " .. count)

-- A Fire hit draws in the Fire colour; an unknown mask draws as Physical.
t.fake.queue = {hit(1231204495, 4)}
local layer = tick()
local shown = liveStrings(layer)
assert(#shown == 1, "one hit, one number")
local fire = t.P.damageColors.fire
assert(shown[1].textColor[1] == fire.r and shown[1].textColor[2] == fire.g and shown[1].textColor[3] == fire.b,
    "a Fire hit takes the Fire colour")
assert(shown[1]:GetText() == "1,231,204,495", "grouped through Econ.Gold: " .. tostring(shown[1]:GetText()))

-- --------------------------------------------- 3. the player's own picks, on the next hit

t.E.db.torment = {damageColors = {fire = {r = 0.1, g = 0.2, b = 0.3}}}
t.fake.queue = {hit(5, 4)}
t.advance(2) -- the first number is gone
layer = tick()
shown = liveStrings(layer)
assert(#shown == 1, "the old number has risen away: " .. #shown)
assert(shown[1].textColor[1] == 0.1 and shown[1].textColor[3] == 0.3, "a picked colour shows on the next hit")

-- The reset button puts every picker back to the palette.
t.page.args.damageText.args.resetColours.func()
for element, colour in pairs(t.P.damageColors) do
    local r, g, b = t.page.args.damageText.args["colour_" .. element].get()
    assert(r == colour.r and g == colour.g and b == colour.b, element .. " is back to its default")
end
-- A picker writes the profile as {r, g, b}.
t.page.args.damageText.args.colour_cold.set(nil, 0.5, 0.6, 0.7)
assert(t.E.db.torment.damageColors.cold.g == 0.6, "the cold picker writes the profile")
assert(#t.module.DamageText.ELEMENTS == 7, "seven pickers")

-- ---------------------------------------------------------------- 4. sizes

t.E.db.torment = {damageSize = 18, damageCritSize = 30, damageDotSize = 9}
t.advance(5)
t.fake.queue = {hit(1, 1, false, false), hit(2, 1, true, false), hit(3, 1, false, true), hit(4, 1, true, true)}
layer = tick()
local byText = {}
for _, region in ipairs(liveStrings(layer)) do byText[region:GetText()] = region end
assert(byText["1"].fontSize == 18, "a hit takes the base size")
assert(byText["2"].fontSize == 30, "a crit takes the crit size")
assert(byText["3"].fontSize == 9, "a tick takes the dot size")
assert(byText["4"].fontSize == 9, "a critical tick is still a tick")

-- The three size sliders each run 25 to 75 (the designer, q-1016-21), and the defaults
-- sit inside it, a crit above a hit and a tick below.
for _, key in ipairs({"damageSize", "damageCritSize", "damageDotSize"}) do
    local slider = t.page.args.damageText.args[key]
    assert(slider.type == "range" and slider.min == 25 and slider.max == 75,
        key .. " runs 25 to 75, got " .. tostring(slider.min) .. " to " .. tostring(slider.max))
    assert(t.P[key] >= 25 and t.P[key] <= 75, key .. " defaults inside its slider: " .. t.P[key])
end
assert(t.P.damageCritSize > t.P.damageSize, "a crit defaults larger than a hit")
assert(t.P.damageDotSize < t.P.damageSize, "a tick defaults smaller than a hit")
assert(t.P.damageSize ~= 14, "the old default of 14 is gone")
-- The step between them is the stock client's crit over hit (WorldText.cpp
-- s_worldTextTypes, 0.0275 over 0.01833, 1.5), up for the crit and down for the
-- tick, each rounded to a whole size.
local STEP = 0.027499998 / 0.018333333
assert(t.P.damageCritSize == math.floor(t.P.damageSize * STEP + 0.5), "the crit is the hit times 1.5: " .. t.P.damageCritSize)
assert(t.P.damageDotSize == math.floor(t.P.damageSize / STEP + 0.5), "the tick is the hit over 1.5: " .. t.P.damageDotSize)

-- Profile older than the setting: the default shows (ElvUI[4].torment).
t.E.db.torment = {}
t.advance(5)
t.fake.queue = {hit(7)}
layer = tick()
shown = liveStrings(layer)
assert(shown[1].fontSize == t.P.damageSize, "an empty profile draws at the default size")
assert(shown[1].font == t.registered["font:Torment Exocet"], "in the default font, Exocet")
assert(t.P.damageFont == "Torment Exocet", "Exocet is the default")

-- The three shipped fonts are in ElvUI's font list by name.
for _, font in ipairs({"Torment Exocet", "Torment Sans Serif", "Torment Serif"}) do
    assert(t.registered["font:" .. font], font .. " is registered with LibSharedMedia")
end
assert(t.page.args.damageText.args.damageFont.dialogControl == "LSM30_Font", "the font pick is ElvUI's font control")

-- --------------------------------------------- 4b. change the font, the numbers change
-- A picked font once left the numbers in the old face. Two places
-- pick it: the Torment page's Font and ElvUI's own CombatText Font (General,
-- Media). Either changes the next number and the numbers already in flight.
t.registered["font:PT Sans Narrow"] = "Interface\\AddOns\\ElvUI\\Media\\Fonts\\PTSansNarrow.ttf"
t.registered["font:Expressway"] = "Interface\\AddOns\\ElvUI\\Media\\Fonts\\Expressway.ttf"
local SERIF, EXPRESSWAY = t.registered["font:Torment Serif"], t.registered["font:Expressway"]
local damageFont = t.page.args.damageText.args.damageFont

-- Login: ElvUI's own UpdateMedia runs; its CombatText Font is only recorded, so the
-- profile keeps its own font.
t.E:UpdateMedia()
t.advance(5)
t.fake.queue = {hit(8)}
layer = tick()
local inFlight = liveStrings(layer)[1]
assert(inFlight.font == t.registered["font:Torment Exocet"], "login leaves the profile's font: " .. tostring(inFlight.font))

-- The Torment page's pick: the number in flight takes it on the next frame, the
-- next hit draws in it, and its size stays.
damageFont.set(nil, "Torment Serif")
assert(damageFont.get() == "Torment Serif", "the font pick writes the profile")
t.advance(0.25)
tick()
assert(inFlight.font == SERIF, "a number in flight changes to the picked font: " .. tostring(inFlight.font))
assert(inFlight.fontSize == t.P.damageSize, "and keeps its size")
t.fake.queue = {hit(9, 1, true)}
tick()
for _, region in ipairs(liveStrings(layer)) do
    assert(region.font == SERIF, "every number on screen is in the picked font")
    if region:GetText() == "9" then assert(region.fontSize == t.P.damageCritSize, "a crit keeps the crit size") end
end

-- ElvUI's CombatText Font: its option writes E.private.general.dmgfont and calls
-- UpdateMedia (ElvUI_OptionsUI General.lua). The numbers follow, the Torment page
-- shows the same font.
t.E.private.general.dmgfont = "Expressway"
t.E:UpdateMedia()
assert(damageFont.get() == "Expressway", "the Torment page shows ElvUI's pick: " .. tostring(damageFont.get()))
t.advance(0.25)
tick()
for _, region in ipairs(liveStrings(layer)) do
    assert(region.font == EXPRESSWAY, "ElvUI's CombatText Font reaches the numbers in flight: " .. tostring(region.font))
end
t.advance(5)
t.fake.queue = {hit(10)}
tick()
assert(liveStrings(layer)[1].font == EXPRESSWAY, "and the next hit")

-- A profile change runs UpdateMedia with the same CombatText Font: nothing moves,
-- and a later Torment pick wins again.
damageFont.set(nil, "Torment Sans Serif")
t.E:UpdateMedia()
t.advance(5)
t.fake.queue = {hit(11)}
tick()
assert(liveStrings(layer)[1].font == t.registered["font:Torment Sans Serif"], "the last pick wins, an unchanged ElvUI font does not")

-- A font name LibSharedMedia no longer has draws in Exocet, never in no font.
damageFont.set(nil, "Gone Font")
t.advance(5)
t.fake.queue = {hit(12)}
tick()
assert(liveStrings(layer)[1].font == t.registered["font:Torment Exocet"], "an unknown font falls back to Exocet")
t.E.db.torment.damageFont = nil
t.advance(5)
tick()

-- ------------------------------------------------------- 5. the rise and the fade

t.E.db.torment = {damageRiseTime = 2, damageRise = 50, damageFan = 0}
t.advance(5)
t.fake.queue = {hit(42)}
t.fake.project = function() return 300, 200 end
layer = tick()
local number = liveStrings(layer)[1]
local function bottom(region)
    local _, _, _, x, y = region:GetPoint(1)
    return x, y
end
local x0, y0 = bottom(number)
assert(x0 == 300 and y0 == 200, "a new number starts on its projected point: " .. tostring(x0) .. "," .. tostring(y0))
assert(number.alpha == 1, "and solid")
t.advance(1) -- half way
tick()
local _, y1 = bottom(number)
assert(math.abs(y1 - 225) < 1e-9, "half the rise time, half of 50 px up: " .. y1)
assert(number.alpha == 1, "still solid at half way")
t.advance(0.6) -- 80 percent
tick()
assert(number.alpha == 1, "solid up to 80 percent of the rise")
t.advance(0.2) -- 90 percent
tick()
assert(math.abs(number.alpha - 0.5) < 1e-9, "half faded at 90 percent: " .. number.alpha)
t.advance(0.21) -- past the top (the clock is a sum of floats, so not exactly 2 s)
tick()
assert(#liveStrings(layer) == 0, "gone at the top of its rise")

-- The defaults the designer asked for (q-1016-21): about 300 px, a 30-degree fan.
assert(t.P.damageRise == 300, "a number rises 300 px by default, got " .. t.P.damageRise)
assert(t.P.damageFan == 30, "inside a 30-degree fan by default, got " .. t.P.damageFan)
t.E.db.torment = {}
local args = t.page.args.damageText.args
assert(args.damageRise.get() == 300 and args.damageFan.get() == 30, "the sliders show the defaults")
args.damageFan.set(nil, 45)
assert(t.E.db.torment.damageFan == 45, "the Fan slider writes the profile")

-- ------------------------------------------------------------ 5b. the fan

-- Each number flies a fountain arc (the designer's sketch): it climbs 300 px evenly,
-- leaves straight up, and its slope grows with height until, at the top, it
-- points along its own angle, at most 15 degrees off straight up either side.
-- The edges of the draw land on the edges.
t.E.db.torment = {damageRiseTime = 2, damageRise = 300}
t.advance(5)
t.fake.project = function() return 300, 200 end
t.draw(0, 1, 0.5, 0.25)
t.fake.queue = {hit(1), hit(2), hit(3), hit(4)}
tick()
local byNumber = {}
for _, region in ipairs(liveStrings(layer)) do byNumber[region:GetText()] = region end
-- The direction a number points at the top of its arc, read from where it is at
-- a share of the rise: drift / height = tan(angle) * share / 2.
local function angleOf(region, share)
    local x, y = bottom(region)
    return math.deg(math.atan(2 * (x - 300) / ((y - 200) * share)))
end
local seen, last = {}, {}
for step = 1, 9 do
    t.advance(0.2)
    tick()
    local share = 0.1 * step
    for text, region in pairs(byNumber) do
        local x, y = bottom(region)
        assert(math.abs(y - 200 - 300 * share) < 1e-6, text .. " climbs its rise evenly: " .. (y - 200))
        local angle = angleOf(region, share)
        assert(math.abs(angle) <= 15 + 1e-9, text .. " leaves the 30-degree fan: " .. angle)
        if seen[text] then
            assert(math.abs(seen[text] - angle) < 1e-9, text .. " leaves its own arc")
        end
        seen[text] = angle
        last[text] = last[text] or {}
        last[text][step] = {x - 300, y - 200}
    end
end
assert(math.abs(seen["1"] + 15) < 1e-9, "a draw of 0 is the left edge, 15 degrees: " .. seen["1"])
assert(math.abs(seen["2"] - 15) < 1e-9, "a draw of 1 is the right edge: " .. seen["2"])
assert(math.abs(seen["3"]) < 1e-9, "a draw of 0.5 is straight up: " .. seen["3"])
assert(math.abs(seen["4"] + 7.5) < 1e-9, "a draw of 0.25 is half way left: " .. seen["4"])

-- The curve itself, on the drawn points: the sideways step per pixel climbed
-- grows with every step up (a straight line keeps it equal), and the first step
-- is the nearest to vertical.
for _, text in ipairs({"1", "2", "4"}) do
    local path, previous = last[text], nil
    for step = 2, 9 do
        local slope = math.abs((path[step][1] - path[step - 1][1]) / (path[step][2] - path[step - 1][2]))
        if previous then
            assert(slope > previous + 1e-6, text .. ": the slope grows with height, step " .. step .. ": " ..
                previous .. " then " .. slope)
        end
        previous = slope
    end
end

-- The same on the path function, and the rule fails a straight path: one number
-- at the fan's edge, sampled bottom to top.
local function slopesGrow(path)
    local dx, dy = math.sin(math.rad(15)), math.cos(math.rad(15))
    local previous, px, py
    for i = 0, 10 do
        local x, y = path(300, dx, dy, i / 10)
        if px then
            local slope = (x - px) / (y - py)
            if previous and slope <= previous + 1e-9 then return false end
            previous = slope
        end
        px, py = x, y
    end
    local x0, y0 = path(300, dx, dy, 0.001)
    local x1, y1 = path(300, dx, dy, 1)
    local x9, y9 = path(300, dx, dy, 0.999)
    -- Starts nearly vertical, ends along its own direction.
    return math.abs(x0 / y0) < 0.01 and math.abs((x1 - x9) / (y1 - y9) - dx / dy) < 0.01
end
assert(slopesGrow(t.module.DamageText.Path), "the shipped path is a fountain arc")
assert(not slopesGrow(function(rise, dx, dy, share) return rise * share * dx, rise * share * dy end),
    "a straight path fails the slope rule")

-- Each number draws its own angle: a burst of hits spreads apart.
t.advance(5)
t.fake.queue = {}
for i = 1, 20 do t.fake.queue[i] = hit(i) end
tick()
t.advance(1)
tick()
local angles = {}
for _, region in ipairs(liveStrings(layer)) do
    local angle = angleOf(region, 0.5)
    assert(math.abs(angle) <= 15 + 1e-9, "a random draw stays inside the fan: " .. angle)
    angles[string.format("%.6f", angle)] = true
end
local distinct = 0
for _ in pairs(angles) do distinct = distinct + 1 end
assert(distinct >= 15, "twenty hits at once take their own angles, got " .. distinct .. " distinct")

-- The angle is read at the hit: a wider fan shows on the next number.
t.E.db.torment.damageFan = 90
t.advance(5)
t.draw(1)
t.fake.queue = {hit(5)}
tick()
t.advance(1)
tick()
assert(math.abs(angleOf(liveStrings(layer)[1], 0.5) - 45) < 1e-9, "a 90-degree fan reaches 45 degrees")

-- The camera moved: the number follows its world point, not the screen.
t.E.db.torment = {damageFan = 0}
t.advance(5)
t.fake.queue = {hit(43)}
t.fake.project = function() return 300, 200 end
tick()
t.fake.project = function() return 500, 100 end
tick()
local xMoved, yMoved = bottom(liveStrings(layer)[1])
assert(xMoved == 500 and yMoved == 100, "re-projected each frame")
-- Off screen: hidden, but its clock runs on.
t.fake.project = function() return nil end
tick()
assert(#liveStrings(layer) == 0, "a point out of view hides its number")

-- ------------------------------------------------- 6. reading the queue each frame

t.advance(5)
local before = t.fake.reads
t.fake.queue = {hit(1), hit(2), hit(3)}
t.fake.project = function() return 1, 1 end
tick()
assert(t.fake.reads - before == 4, "three hits and the nil that ends the queue: " .. (t.fake.reads - before))
before = t.fake.reads
tick()
assert(t.fake.reads - before == 1, "an empty queue is still read every frame (the module's sign the addon draws)")

-- The ceiling: past 60 numbers the oldest goes.
t.advance(5)
t.fake.queue = {}
for i = 1, 70 do t.fake.queue[i] = hit(i) end
tick()
shown = liveStrings(layer)
assert(#shown == 60, "at most 60 numbers at once, got " .. #shown)
local smallest = math.huge
for _, region in ipairs(shown) do smallest = math.min(smallest, tonumber((region:GetText():gsub(",", "")))) end
assert(smallest == 11, "the ten oldest went first, smallest left " .. smallest)

-- ----------------------------------------------- 7. heals, words, and the short form

t.advance(5)
t.fake.queue = {
    {"heal", 1500, 2, false, false, true, 1, 1, 0, nil},
    {"word", 0, 1, false, false, true, 1, 1, 0, "Dodge"},
}
tick()
byText = {}
for _, region in ipairs(liveStrings(layer)) do byText[region:GetText()] = region end
assert(byText["+1,500"] and byText["+1,500"].textColor[2] == 1 and byText["+1,500"].textColor[1] == 0,
    "a heal is +grouped, in the stock green")
assert(byText["Dodge"] and byText["Dodge"].textColor[1] == 1, "a word is the client's own word, in white")

local Short = t.module.DamageText.Short
local CASES = {
    {1231204495, "1.23b"}, {45600000, "45.6m"}, {789000, "789k"}, {999, "999"}, {1000, "1.00k"},
    {12345, "12.3k"}, {999999, "1.00m"}, {999999999, "1.00b"}, {4294967295, "4.29b"}, {0, "0"},
}
for _, case in ipairs(CASES) do
    assert(Short(case[1]) == case[2], case[1] .. " short is " .. case[2] .. ", got " .. Short(case[1]))
end
t.page.args.damageText.args.damageShort.set(nil, true)
assert(t.E.db.torment.damageShort == true, "the short toggle writes the profile")
t.advance(5)
t.fake.queue = {hit(1231204495, 4)}
tick()
assert(liveStrings(layer)[1]:GetText() == "1.23b", "the short form shows on the next hit")
t.page.args.damageText.args.damageShort.set(nil, false)
t.advance(5)
t.fake.queue = {hit(1231204495, 4)}
tick()
assert(liveStrings(layer)[1]:GetText() == "1,231,204,495", "and back to full")
assert(t.P.damageShort == false, "full numbers by default")

print("test_elvui_damagetext: ok")
