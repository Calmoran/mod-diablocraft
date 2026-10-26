-- luacheck: globals Diablocraft PowerBarColor
-- luacheck: ignore 111 112 113 121 122
-- Run from repo root with `lua mod-diablocraft/scripts/tests/ui/test_power_strings.lua`.
--
-- client-patch/addons/Torment/PowerStrings.lua against the shipped generated list
-- (ResourceNames.lua, loaded as it ships) and the stock 3.3.5a strings and
-- colours. What is pinned: every class power token the list carries gets its
-- PowerBarColor entry from the list's colour, its name as _G[token], and the
-- two cost formats the rebuilt client's tooltip reads (_G[token .. "_COST"],
-- _G[token .. "_COST_PER_TIME"]) built from its slot's stock ones; a stock
-- token and the stock entries stay exactly as they were; the toc loads it after
-- the list and before ResourceText.lua. Mocks do NOT prove what the client
-- draws: the bar and tooltip on screen are the designer's check (the test sheet).

-- The stock strings, verbatim from the 3.3.5a client's FrameXML GlobalStrings.lua
-- (extracted to azerothcore-wotlk/build/_agent-scratch/stock-gluexml-9b46c3a/);
-- cross-checked against that file below when it is present.
local STOCK_STRINGS = {
    MANA = "Mana", MANA_COST = "%d Mana", MANA_COST_PER_TIME = "%d Mana, plus %d per sec",
    RAGE = "Rage", RAGE_COST = "%d Rage", RAGE_COST_PER_TIME = "%d Rage, plus %d per sec",
    FOCUS = "Focus", FOCUS_COST = "%d Focus", FOCUS_COST_PER_TIME = "%d Focus, plus %d per sec",
    ENERGY = "Energy", ENERGY_COST = "%d Energy", ENERGY_COST_PER_TIME = "%d Energy, plus %d per sec",
    RUNIC_POWER = "Runic Power", RUNIC_POWER_COST = "%d Runic Power",
    RUNIC_POWER_COST_PER_TIME = "%d Runic Power, plus %d per sec",
}
local extracted = io.open("azerothcore-wotlk/build/_agent-scratch/stock-gluexml-9b46c3a/Interface/FrameXML/GlobalStrings.lua")
if extracted then
    local text = extracted:read("*a")
    extracted:close()
    for name, value in pairs(STOCK_STRINGS) do
        local line = name .. ' = "' .. value .. '";'
        assert(text:find("\n" .. line, 1, true), "the stock string is the client's: " .. line)
    end
end

-- The stock PowerBarColor (FrameXML UnitFrame.lua:2-9).
local function stockColours()
    return {MANA = {r = 0.00, g = 0.00, b = 1.00}, RAGE = {r = 1.00, g = 0.00, b = 0.00},
            FOCUS = {r = 1.00, g = 0.50, b = 0.25}, ENERGY = {r = 1.00, g = 1.00, b = 0.00},
            HAPPINESS = {r = 0.00, g = 1.00, b = 1.00}, RUNES = {r = 0.50, g = 0.50, b = 0.50},
            RUNIC_POWER = {r = 0.00, g = 0.82, b = 1.00}}
end

local function reset()
    for name, value in pairs(STOCK_STRINGS) do _G[name] = value end
    PowerBarColor = stockColours()
    Diablocraft = nil
    assert(loadfile("client-patch/addons/Torment/ResourceNames.lua"))()
    assert(loadfile("client-patch/addons/Torment/PowerStrings.lua"))()
end

local STOCK_TOKENS = stockColours()
reset()

-- Every class power token the shipped list carries.
local checked = 0
for token, power in pairs(Diablocraft.PowerTokens) do
    if STOCK_TOKENS[token] == nil then
        checked = checked + 1
        local colour = PowerBarColor[token]
        assert(colour and colour.r == power.r and colour.g == power.g and colour.b == power.b,
            token .. " has the list's colour in PowerBarColor")
        assert(_G[token] == power.name, token .. " is named " .. power.name .. ", got " .. tostring(_G[token]))
        assert(string.format(_G[token .. "_COST"], 15) == "15 " .. power.name,
            token .. "'s cost line, got " .. tostring(_G[token .. "_COST"]))
        assert(string.format(_G[token .. "_COST_PER_TIME"], 15, 3) == "15 " .. power.name .. ", plus 3 per sec",
            token .. "'s cost-per-time line, got " .. tostring(_G[token .. "_COST_PER_TIME"]))
    end
end
assert(checked >= 5, "every class power token in the shipped list was checked, got " .. checked)

-- The stock tokens and their strings are the client's own, untouched.
for token, colour in pairs(STOCK_TOKENS) do
    local now = PowerBarColor[token]
    assert(now.r == colour.r and now.g == colour.g and now.b == colour.b, token .. " keeps the stock colour")
end
for name, value in pairs(STOCK_STRINGS) do
    assert(_G[name] == value, name .. " keeps the stock string")
end

-- A token that is its slot's own stock token (the Witch Doctor's MANA) is the
-- client's already: nothing is written for it, even with a colour of its own.
reset()
-- (A name other than the stock word, so a rewrite would show.)
Diablocraft.ResourceNames.WITCHDOCTOR = {MANA = {name = "Juju", power = 0, role = "primary", key = "mana", token = "MANA"}}
Diablocraft.PowerTokens.MANA = {name = "Juju", r = 0.1, g = 0.2, b = 0.3, power = 0}
Diablocraft.PowerStrings.Apply()
assert(PowerBarColor.MANA.b == 1.00 and MANA == "Mana" and MANA_COST == "%d Mana", "a stock token stays the client's")

-- A token no row places on a slot is skipped, never written half-made.
reset()
Diablocraft.PowerTokens.STRAY = {name = "Stray", r = 1, g = 1, b = 1, power = 9}
Diablocraft.PowerStrings.Apply()
assert(PowerBarColor.STRAY == nil and _G.STRAY == nil and _G.STRAY_COST == nil, "a token with no slot row is skipped")

-- A stock format without the stock word is not rewritten.
local PS = Diablocraft.PowerStrings
assert(PS.CostFormat("%d Rage", "Rage", "Fury") == "%d Fury")
assert(PS.CostFormat("%d Wut", "Rage", "Fury") == nil, "a format without the word is left alone")
assert(PS.CostFormat(nil, "Rage", "Fury") == nil)

-- The toc: after the generated list, before ResourceText.lua (which reads the
-- PowerBarColor keys at load).
local toc = assert(io.open("client-patch/addons/Torment/Torment.toc")):read("*a")
local names, list, strings, text = {}, nil, nil, nil
for line in toc:gmatch("[^\n]+") do
    if not line:find("^#") and line:find("%.lua$") then
        names[#names + 1] = line
        if line == "ResourceNames.lua" then list = #names end
        if line == "PowerStrings.lua" then strings = #names end
        if line == "ResourceText.lua" then text = #names end
    end
end
assert(list and strings and text and list < strings and strings < text,
    "the toc loads ResourceNames.lua, PowerStrings.lua, ResourceText.lua in that order")

print("test_power_strings: ok")
