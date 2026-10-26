-- luacheck: globals ElvUI unpack Diablocraft GetTime TormentDamageTextRead TormentWorldToScreen hooksecurefunc
-- The floating damage numbers (docs/contracts/damage-text.md). The Torment client
-- module hands over each hit the engine itself would draw a number for (the
-- player's own, the player's pets' and companion's) with the world point it
-- starts from, and projects that point to the screen each frame; this file draws
-- the number: the font, the element's colour, grouped or short, the size for a
-- hit, a crit or a tick, the rise, the fan and the fade. Every setting is on the Torment
-- page of the ElvUI options (options.lua) and is read at each new hit, so a
-- change shows on the next one; a font change also redraws the numbers in flight.
-- ElvUI's own CombatText Font (General, Media) picks the same font as the
-- Torment page's Font: whichever was picked last is the numbers' font.
--
-- Without the client module (no TormentDamageTextRead or TormentWorldToScreen)
-- nothing here runs and the engine's own numbers show as before.
local E = unpack(ElvUI)
local module = E:GetModule("ElvUI_Torment")

local FONTS = "Interface\\AddOns\\Torment\\fonts\\"
-- The three fonts the Torment addon ships, under their names in ElvUI's font list.
local SHIPPED_FONTS = {
    {"Torment Exocet", FONTS .. "Exocet.ttf"},
    {"Torment Sans Serif", FONTS .. "SansSerif.ttf"},
    {"Torment Serif", FONTS .. "Serif.ttf"},
}
local FALLBACK_FONT = SHIPPED_FONTS[1][2]

local LSM = E.Libs and E.Libs.LSM
if LSM then
    for _, font in ipairs(SHIPPED_FONTS) do
        LSM:Register("font", font[1], font[2])
    end
end

-- The server's school for each element (mod-diablocraft/src/combat/dc_combat_internal.h
-- SchoolMaskFor, 01-stats S9); any other mask draws as Physical.
local SCHOOL_ELEMENT = {
    [1] = "physical", [2] = "holy", [4] = "fire", [8] = "lightning",
    [16] = "cold", [32] = "poison", [64] = "arcane",
}
-- The settings page lists the pickers in this order.
local ELEMENTS = {"physical", "fire", "cold", "lightning", "poison", "arcane", "holy"}

-- The stock client's own world text colours (WorldText.cpp s_worldTextTypes):
-- a heal green, a word (Miss, Dodge, Absorb...) white.
local HEAL_COLOUR = {r = 0, g = 1, b = 0}
local WORD_COLOUR = {r = 1, g = 1, b = 1}

-- A number is solid for this share of its rise and fades over the rest.
local SOLID_SHARE = 0.8
-- ponytail: a ceiling on numbers on screen at once; past it the oldest goes first.
local MAX_LIVE = 60

local function defaults()
    return ElvUI[4].torment
end

local function setting(key)
    local db = E.db and E.db.torment
    local value = db and db[key]
    if value == nil then return defaults()[key] end
    return value
end

local function elementColour(element)
    local db = E.db and E.db.torment
    local picked = db and db.damageColors and db.damageColors[element]
    if picked and picked.r then return picked end
    return defaults().damageColors[element]
end

-- 1,231,204,495 -> "1.23b": three significant figures and a lower-case suffix.
-- The hit's amount is the packet's 32-bit value, so b is the largest suffix.
local SUFFIXES = {{1e9, "b"}, {1e6, "m"}, {1e3, "k"}}

local function short(amount)
    for i, step in ipairs(SUFFIXES) do
        if amount >= step[1] then
            local value = amount / step[1]
            local decimals = value >= 100 and 0 or (value >= 10 and 1 or 2)
            local text = string.format("%." .. decimals .. "f", value)
            -- 999,999 rounds to "1000k"; that is the next suffix's 1.00m.
            if tonumber(text) >= 1000 and i > 1 then
                return string.format("%.2f", amount / SUFFIXES[i - 1][1]) .. SUFFIXES[i - 1][2]
            end
            return text .. step[2]
        end
    end
    return tostring(amount)
end

local function grouped(amount)
    local Econ = Diablocraft and Diablocraft.Econ
    if Econ and Econ.Gold then return Econ.Gold(amount) end
    return tostring(amount)
end

local function textFor(kind, amount, word)
    if kind == "word" then return word end
    amount = math.floor(amount + 0.5)
    local text = setting("damageShort") and short(amount) or grouped(amount)
    if kind == "heal" then return "+" .. text end
    return text
end

local function colourFor(kind, school)
    if kind == "heal" then return HEAL_COLOUR end
    if kind == "word" then return WORD_COLOUR end
    return elementColour(SCHOOL_ELEMENT[school] or "physical")
end

-- A tick takes the dot size, a crit the crit size, anything else the base size.
local function sizeFor(crit, periodic)
    if periodic then return setting("damageDotSize") end
    if crit then return setting("damageCritSize") end
    return setting("damageSize")
end

local function fontPath()
    local path = LSM and LSM:Fetch("font", setting("damageFont"), true)
    return path or FALLBACK_FONT
end

-- A number's own direction out of the fan: an angle off straight up, random per
-- number and anywhere inside the fan (half of it either side), as its sideways
-- and upward share.
local function lineFor(fan)
    local angle = math.rad((math.random() * 2 - 1) * fan / 2)
    return math.sin(angle), math.cos(angle)
end

-- Where a number is at a share of its rise, off its start point: a fountain arc.
-- It climbs the rise evenly and drifts sideways by the square of its share, so it
-- leaves straight up and bends outward as it climbs, its slope growing with height
-- until it points along its own direction (dx, dy) at the top.
local function pathAt(rise, dx, dy, share)
    return rise * dx / dy / 2 * share * share, rise * share
end

-- Alpha at a share of the rise: 1 while solid, then down to 0 at the top.
local function alphaAt(share)
    if share <= SOLID_SHARE then return 1 end
    return math.max(0, (1 - share) / (1 - SOLID_SHARE))
end

module.DamageText = {
    ELEMENTS = ELEMENTS, SCHOOL_ELEMENT = SCHOOL_ELEMENT, SHIPPED_FONTS = SHIPPED_FONTS,
    Short = short, Text = textFor, Colour = colourFor, Size = sizeFor, Alpha = alphaAt,
    Line = lineFor, Path = pathAt,
}

if type(TormentDamageTextRead) ~= "function" or type(TormentWorldToScreen) ~= "function" then
    return
end

local layer = CreateFrame("Frame", "TormentDamageText", UIParent)
layer:SetAllPoints(UIParent)
layer:SetFrameStrata("BACKGROUND")

local live, spare = {}, {}

local function release(index)
    local number = table.remove(live, index)
    number.text:Hide()
    spare[#spare + 1] = number
end

-- ElvUI calls UpdateMedia when its CombatText Font is picked, at login and on a
-- profile change; a CombatText Font that differs from the last one seen is the
-- player's pick, and becomes the numbers' font. The first call only records it,
-- so a profile keeps its own pick until the player picks again.
local seenCombatFont
local function followCombatFont()
    local general = E.private and E.private.general
    local picked = general and general.dmgfont
    if picked == nil then return end
    if seenCombatFont ~= nil and picked ~= seenCombatFont then
        E.db.torment = E.db.torment or {}
        E.db.torment.damageFont = picked
    end
    seenCombatFont = picked
end
hooksecurefunc(E, "UpdateMedia", followCombatFont)

local function spawn(kind, amount, school, crit, periodic, x, y, z, word, now)
    local text = textFor(kind, amount, word)
    if not text or text == "" then return end
    if #live >= MAX_LIVE then release(1) end
    local number = table.remove(spare)
    if not number then
        local fontString = layer:CreateFontString(nil, "OVERLAY")
        fontString:SetShadowColor(0, 0, 0, 1)
        fontString:SetShadowOffset(1, -1)
        number = {text = fontString}
    end
    local colour = colourFor(kind, school)
    number.font, number.size = fontPath(), sizeFor(crit, periodic)
    number.text:SetFont(number.font, number.size)
    number.text:SetTextColor(colour.r, colour.g, colour.b)
    number.text:SetText(text)
    number.x, number.y, number.z, number.born = x, y, z, now
    number.riseTime, number.rise = setting("damageRiseTime"), setting("damageRise")
    number.dx, number.dy = lineFor(setting("damageFan"))
    live[#live + 1] = number
end

local function place(number, now, font)
    local share = (now - number.born) / number.riseTime
    if share >= 1 then return false end
    if number.font ~= font then
        number.font = font
        number.text:SetFont(font, number.size)
    end
    local sx, sy = TormentWorldToScreen(number.x, number.y, number.z)
    local fontString = number.text
    if not sx then
        fontString:Hide()
        return true
    end
    local scale = UIParent:GetEffectiveScale()
    fontString:ClearAllPoints()
    local ox, oy = pathAt(number.rise, number.dx, number.dy, share)
    fontString:SetPoint("BOTTOM", UIParent, "BOTTOMLEFT", sx / scale + ox, sy / scale + oy)
    fontString:SetAlpha(alphaAt(share))
    fontString:Show()
    return true
end

-- Every frame: take every queued hit (reading is also what tells the module the
-- addon draws, so it keeps the engine's own copy off), then move each number,
-- in the font picked now.
layer:SetScript("OnUpdate", function()
    local now = GetTime()
    while true do
        local kind, amount, school, crit, periodic, _, x, y, z, word = TormentDamageTextRead()
        if not kind then break end
        spawn(kind, amount or 0, school, crit, periodic, x, y, z, word, now)
    end
    local font = fontPath()
    for i = #live, 1, -1 do
        if not place(live[i], now, font) then release(i) end
    end
end)
