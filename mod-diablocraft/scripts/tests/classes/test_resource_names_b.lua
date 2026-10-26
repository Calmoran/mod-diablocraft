-- luacheck: globals Diablocraft AIO GameTooltip ItemRefTooltip UIErrorsFrame CreateFrame
-- luacheck: globals UnitClass UnitPowerType UnitFrameManaBar_UpdateType SetTextStatusBarTextPrefix
-- luacheck: globals TextStatusBar_UpdateTextString PowerBarColor
-- luacheck: globals ENERGY RAGE MANA FOCUS HAPPINESS RUNES RUNIC_POWER
-- luacheck: ignore 111 121 122 431
-- Run from repo root with `lua mod-diablocraft/scripts/tests/classes/test_resource_names_b.lua`.
--
-- The resource-name module (client-patch/addons/Torment/ResourceText.lua), the
-- generated list it reads (client-patch/addons/Torment/ResourceNames.lua) and
-- the toc, against a stub 3.3.5a client. Ruling 2C, contract
-- docs/contracts/resource-names.md, surface map
-- docs/research/systems/resource-text-muse.md.
--
-- Independent class/slot fixtures drive the reader on BOTH slot layouts (the
-- shipped Mana layout and rollout A's Energy layout), so the test does not
-- hardcode which slot the Wizard resource uses; a separate check validates the
-- shipped generated list's shape and that the reader reads it. Two deliberate
-- implementation mutations must fail a relevant check. Hyperlink tooltips (the
-- skill picker and chat spell links) are asserted NOT rewritten: that surface is
-- stopped until a generated spell-id -> owning-class table exists, because the
-- client has no spell-ownership API and IsSpellKnown is learned-state, not
-- ownership. Mocks do NOT prove live rendering; the client check is the designer's
-- (docs/test-resource-names-b.md).

-- ---------------------------------------------------------------- stub client

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)

-- The slot's stock words, kept as the pre-override truth for the shipped-list
-- check, and the client's own slot enumeration.
ENERGY, RAGE, MANA = "Energy", "Rage", "Mana"
FOCUS, HAPPINESS, RUNES, RUNIC_POWER = "Focus", "Happiness", "Runes", "Runic Power"
PowerBarColor = {MANA = {}, RAGE = {}, FOCUS = {}, ENERGY = {}, HAPPINESS = {}, RUNES = {},
                 RUNIC_POWER = {}}
local STOCK_BEFORE = {MANA = MANA, RAGE = RAGE, ENERGY = ENERGY, FOCUS = FOCUS,
                      HAPPINESS = HAPPINESS, RUNES = RUNES, RUNIC_POWER = RUNIC_POWER}

-- The stock tooltip fill writes one named FontString per line, named
-- <tooltip>TextLeft<i>, which is what ResourceText rewrites. The mock's tooltip
-- has no such regions, so this bridge draws them from `pending` and shares the
-- storage with `.lines` (the surface the assertions read).
local pending = {}
local function fill(tooltip)
    local name = tooltip:GetName()
    tooltip.lines = {}
    for i = 1, #pending do
        local index = i
        tooltip.lines[i] = pending[i]
        _G[name .. "TextLeft" .. i] = {
            GetText = function() return tooltip.lines[index] end,
            SetText = function(_, value) tooltip.lines[index] = value end,
        }
    end
    for i = #pending + 1, 40 do _G[name .. "TextLeft" .. i] = nil end
end

CreateFrame("GameTooltip", "ItemRefTooltip")

-- UIErrorsFrame: the stock OnEvent the module wraps, and what it forwards to.
local shown = {}
local function stockOnEvent(_, _, message) shown[#shown + 1] = message end
UIErrorsFrame:SetScript("OnEvent", stockOnEvent)

-- Unit state the module reads. Class and slot tokens, never a name.
local classes = {player = "BARB", target = "WIZMANA", party1 = "WIZENERGY"}
local powers = {player = "RAGE", target = "MANA", party1 = "ENERGY"}
function UnitClass(unit) return classes[unit], classes[unit] end
function UnitPowerType(unit) return 1, powers[unit] or "MANA" end

-- The stock bar update, mimicked so the newbie tooltipTitle path is exercised.
function UnitFrameManaBar_UpdateType(manaBar)
    local unitFrame = manaBar:GetParent()
    local _, powerToken = UnitPowerType(manaBar.unit)
    local prefix = _G[powerToken]
    manaBar.prefix = prefix
    if unitFrame and unitFrame:GetName() == "PlayerFrame" then
        manaBar.tooltipTitle = prefix
    else
        manaBar.tooltipTitle = nil
    end
end
function SetTextStatusBarTextPrefix(bar, prefix) bar.prefix = prefix end
function TextStatusBar_UpdateTextString(bar) bar.text = bar.prefix and (bar.prefix .. " " .. (bar.value or 0)) end

AIO = nil

-- ------------------------------------------------ the shipped generated list

Diablocraft = {}
dofile("client-patch/addons/Torment/ResourceNames.lua")
local shipped = Diablocraft.ResourceNames
assert(type(shipped) == "table" and next(shipped) ~= nil, "the shipped list is non-empty")

-- Shape and contract fields only: no assumption which slot a class uses.
local TOKEN_POWER = {MANA = 0, RAGE = 1, FOCUS = 2, ENERGY = 3, HAPPINESS = 4, RUNES = 5,
                     RUNIC_POWER = 6}
for classToken, rows in pairs(shipped) do
    assert(type(classToken) == "string" and classToken:match("^[A-Z]+$"),
        "class token is the client's capitals form: " .. tostring(classToken))
    local count = 0
    for token, entry in pairs(rows) do
        count = count + 1
        assert(TOKEN_POWER[token] ~= nil, "power token is a client slot: " .. tostring(token))
        assert(type(entry) == "table", "entry is a table")
        assert(type(entry.name) == "string" and #entry.name > 0, "entry has a name")
        assert(entry.colour and entry.colour:match("^%x%x%x%x%x%x$"), "colour is RRGGBB")
        assert(entry.power == TOKEN_POWER[token], "power id matches the slot token")
        assert(entry.role == "primary" or entry.role == "second", "role is primary/second")
        assert(type(entry.key) == "string" and entry.key:match("^[a-z][a-z_]*$"), "key is lower_snake")
        assert(type(entry.class) == "string" and #entry.class > 0, "entry names its D3 class")
    end
    assert(count >= 1 and count <= 2, "a class has one primary and at most one second")
end

-- Independent fixtures for the shipped layout and rollout A's Energy layout.
local FIXTURE = {
    BARB = {RAGE = {name = "Fury", colour = "FF0000", power = 1, role = "primary",
                    key = "fury", class = "Barbarian"}},
    WIZMANA = {MANA = {name = "Arcane Power", colour = "0000FF", power = 0, role = "primary",
                       key = "arcane_power", class = "Wizard"}},
    WIZENERGY = {ENERGY = {name = "Arcane Power", colour = "0000FF", power = 3, role = "primary",
                          key = "arcane_power", class = "Wizard"}},
}
Diablocraft.ResourceNames = FIXTURE

dofile("client-patch/addons/Torment/ResourceText.lua")
local RT = Diablocraft.ResourceText
assert(type(RT) == "table", "the module exposes Diablocraft.ResourceText")
local loaderFrame
for _, frame in ipairs(frames) do
    if frame.events and frame.events.PLAYER_LOGIN then loaderFrame = frame end
end
assert(loaderFrame and loaderFrame.events.PLAYER_LOGIN, "the module loads its class list at login")
local wrappedOnEvent = UIErrorsFrame:GetScript("OnEvent")

-- ------------------------------------------------------- the toc lists the pair

local toc = assert(io.open("client-patch/addons/Torment/Torment.toc", "r"))
local tocText = toc:read("*a")
toc:close()
local namesAt = assert(tocText:find("ResourceNames.lua", 1, true), "the toc names the generated list")
local readerAt = assert(tocText:find("ResourceText.lua", 1, true), "the toc names the reader")
assert(namesAt < readerAt, "ResourceNames.lua must load before ResourceText.lua")

-- ---------------------------------------------------- the number is not touched

local function digits(text)
    local out = {}
    for d in text:gmatch("%d+") do out[#out + 1] = d end
    return table.concat(out, ",")
end
local function sameDigits(a, b) return digits(a) == digits(b) end

-- ---------------------------------------------------- cost formats, both layouts

local function rewrite(line, classToken) return RT.RewriteLine(line, classToken) end

-- Barbarian, Rage -> Fury, on every sourced cost shape.
assert(rewrite("45 Rage", "BARB") == "45 Fury", "plain cost line")
assert(rewrite("45 Rage, plus 5 per sec", "BARB") == "45 Fury, plus 5 per sec", "per-time cost line")
assert(rewrite("Uses 100% Rage", "BARB") == "Uses 100% Fury", "all-power line, capital")
assert(rewrite("Uses 100% rage", "BARB") == "Uses 100% Fury", "all-power line, lower-case stock")
assert(rewrite("Rage cost: |cffffffff45|r", "BARB") == "Fury cost: |cffffffff45|r", "trainer-style line")

-- Wizard on the shipped Mana layout and on rollout A's Energy layout.
assert(rewrite("45 Mana", "WIZMANA") == "45 Arcane Power", "Mana plain cost line")
assert(rewrite("Uses 100% mana", "WIZMANA") == "Uses 100% Arcane Power", "Mana all-power line")
assert(rewrite("Mana cost: |cffffffff45|r", "WIZMANA") == "Arcane Power cost: |cffffffff45|r",
    "Mana trainer-style line")
assert(rewrite("45 Energy", "WIZENERGY") == "45 Arcane Power", "Energy plain cost line")
assert(rewrite("Uses 100% Energy", "WIZENERGY") == "Uses 100% Arcane Power", "Energy all-power line")

-- Negative fixtures: every other byte and every non-cost line is untouched.
assert(rewrite("45 Rageous damage", "BARB") == "45 Rageous damage", "not a cost line, prefix trap")
assert(rewrite("45 Rage damage dealt", "BARB") == "45 Rage damage dealt", "not a cost line, tail trap")
assert(rewrite("Melee Range", "BARB") == "Melee Range", "no number, no change")
assert(rewrite("Not a cost 45 Rage", "BARB") == "Not a cost 45 Rage", "word not at the head or cost form")
assert(rewrite("45 Energy", "BARB") == "45 Energy", "another slot keeps its stock word")
assert(rewrite("45 Mana", "ROGUE") == "45 Mana", "unknown class keeps the stock word")
assert(sameDigits("45 Rage, plus 5 per sec", rewrite("45 Rage, plus 5 per sec", "BARB")),
    "per-time cost keeps both numbers")
assert(sameDigits("45 Mana", rewrite("45 Mana", "WIZMANA")), "cost number is identical")

-- Errors: lower-case word, whole-word only.
assert(RT.RewriteError("Not enough rage", "BARB") == "Not enough Fury", "Barbarian error")
assert(RT.RewriteError("Not enough mana", "WIZMANA") == "Not enough Arcane Power", "Wizard error")
assert(RT.RewriteError("Not enough energy", "WIZENERGY") == "Not enough Arcane Power", "Energy error")
assert(RT.RewriteError("Not enough energy", "ROGUE") == "Not enough energy", "unknown class error")
assert(RT.RewriteError("Ragequitting is not a resource", "BARB") == "Ragequitting is not a resource",
    "the word must not be matched inside another word")

-- ------------------------------- the reader reads the real shipped list too

Diablocraft.ResourceNames = shipped
for classToken, rows in pairs(shipped) do
    for token, entry in pairs(rows) do
        local stock = STOCK_BEFORE[token]
        assert(stock, "fixture knows the stock word for " .. tostring(token))
        assert(RT.WordFor(classToken, token) == entry.name, "WordFor reads the shipped list")
        assert(rewrite("45 " .. stock, classToken) == "45 " .. entry.name,
            "the shipped " .. classToken .. "/" .. token .. " cost word")
    end
end
Diablocraft.ResourceNames = FIXTURE

-- ------------------------------------------------- live surfaces (stub client)

-- STOPPED hyperlink surfaces: no link tooltip is rewritten, cost line included,
-- because a spell link carries no owner class and no ownership metadata exists.
classes.player = "BARB"
pending = {"Frenzy", "45 Rage", "Melee Range"}
fill(GameTooltip)
GameTooltip:SetHyperlink("spell:12345")
assert(GameTooltip.lines[2] == "45 Rage", "the skill-picker hyperlink is stopped (stock word)")
assert(GameTooltip.lines[3] == "Melee Range", "skill-picker other lines untouched")
pending = {"Frostbolt", "25 Mana", "Instant"}
fill(ItemRefTooltip)
ItemRefTooltip:SetHyperlink("|cff71d5ff|Hspell:116|h[Frostbolt]|h|r")
assert(ItemRefTooltip.lines[2] == "25 Mana", "a chat spell link is stopped (stock word)")
pending = {"Thing", "25 Mana"}
fill(ItemRefTooltip)
ItemRefTooltip:SetHyperlink("|cffffffff|Hitem:123|h[Thing]|h|r")
assert(ItemRefTooltip.lines[2] == "25 Mana", "an item chat link is untouched")

-- Spellbook fill, then the action bar (stock and Bartender4 share SetAction).
pending = {"Frenzy", "45 Rage", "Melee Range", "Instant", "Generate: 4 Fury per attack"}
fill(GameTooltip)
GameTooltip:SetSpell(1757)
assert(GameTooltip.lines[2] == "45 Fury", "spellbook cost line word")
assert(GameTooltip.lines[5] == "Generate: 4 Fury per attack", "the record's own sentence is untouched")

classes.player = "WIZENERGY"
pending = {"Frostbolt", "45 Energy", "30 yd range"}
fill(GameTooltip)
GameTooltip:SetAction(1)
assert(GameTooltip.lines[2] == "45 Arcane Power", "action-bar cost line word on the Energy layout")

-- Error payload before the stock handler shows it.
classes.player = "BARB"
wrappedOnEvent(UIErrorsFrame, "UI_ERROR_MESSAGE", "Not enough rage")
assert(shown[#shown] == "Not enough Fury", "Barbarian error payload")
classes.player = "WIZMANA"
wrappedOnEvent(UIErrorsFrame, "UI_ERROR_MESSAGE", "Not enough mana")
assert(shown[#shown] == "Not enough Arcane Power", "Wizard error payload")
wrappedOnEvent(UIErrorsFrame, "UI_INFO_MESSAGE", "Welcome")
assert(shown[#shown] == "Welcome", "other events pass through unchanged")

-- ---------------------------------------- bars, tooltipTitle, and the log

local function bar(unit, frameName)
    return {unit = unit, GetParent = function() return {GetName = function() return frameName end} end,
            value = 50}
end

classes.player = "BARB"
loaderFrame.scripts.OnEvent(loaderFrame)
local playerBar = bar("player", "PlayerFrame")
UnitFrameManaBar_UpdateType(playerBar)
assert(playerBar.prefix == "Fury", "the player's Rage bar says Fury")
assert(playerBar.tooltipTitle == "Fury", "the player's newbie tooltipTitle follows the name")
assert(playerBar.text == "Fury 50", "the bar text is redrawn with the word")

classes.target = "WIZENERGY"
powers.target = "ENERGY"
local energyBar = bar("target", "TargetFrame")
UnitFrameManaBar_UpdateType(energyBar)
assert(energyBar.prefix == "Arcane Power", "another unit's Energy bar uses that unit's class")
assert(energyBar.tooltipTitle == nil, "only the player's bar has a newbie title")
classes.target = "HUNTER"
local hunterBar = bar("target", "TargetFrame")
UnitFrameManaBar_UpdateType(hunterBar)
assert(hunterBar.prefix == "Energy", "a class with no resource keeps the stock word")

assert(RAGE == "Fury", "login override puts the player's name in the shared word")
assert(MANA == "Mana", "a slot the player does not use keeps its stock word")

-- --------------------------------------------------- failing implementation mutations

-- Mutation A: the implementation is made to alter the number. The number
-- invariant check must fail.
local realLine = RT.RewriteLine
RT.RewriteLine = function(line, classToken)
    local out = realLine(line, classToken)
    return (out:gsub("(%d+)", function(n) return tostring(tonumber(n) + 1) end))
end
local okNumber = pcall(function()
    assert(sameDigits("45 Rage", RT.RewriteLine("45 Rage", "BARB")), "number invariant")
end)
RT.RewriteLine = realLine
assert(not okNumber, "a mutation that changes the number must fail the number check")

-- Mutation B: the implementation is made prefix-only again. The negative
-- fixture must fail.
RT.RewriteLine = function(line)
    if line:find("^%d+%s") then return (line:gsub("Rage", "Fury", 1)) end
    return line
end
local okWhole = pcall(function()
    assert(RT.RewriteLine("45 Rageous damage") == "45 Rageous damage", "whole-word check")
end)
RT.RewriteLine = realLine
assert(not okWhole, "a prefix-only mutation must fail the whole-word negative fixture")

-- A final sanity that the real implementation still passes both after restore.
assert(sameDigits("45 Rage", RT.RewriteLine("45 Rage", "BARB")), "restored number invariant")
assert(RT.RewriteLine("45 Rageous damage", "BARB") == "45 Rageous damage", "restored whole-word check")

-- ---------------------------------------------- the module cannot do number math

local function stripComments(source)
    source = source:gsub("%-%-%[%[.-%]%]", "")
    return (source:gsub("%-%-[^\n]*", ""))
end
local file = assert(io.open("client-patch/addons/Torment/ResourceText.lua", "r"))
local source = stripComments(file:read("*a"))
file:close()
assert(not source:find("UnitPower%("), "the module must never read a power value")
assert(not source:find("math%."), "the module must never do math")
assert(not source:find("tonumber"), "the module must never parse a number")

print("Resource names checks passed: both slot layouts, real stock formats, negatives, shipped-list consistency, stopped hyperlink surfaces, failing mutations.")
