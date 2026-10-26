-- luacheck: ignore 111 112 113 121 122 212 213 542
-- The create screen's class buttons: the Monk's (its button, strings, the designer's icon), the class order, the
-- Necromancer's twelfth button, strings and the designer's icon, and the Witch Doctor's thirteenth button, strings and stock icon
-- cell. Runs the shipped GlueXML (CharacterCreate.lua, GlueStrings.lua, the buttons CharacterCreate.xml declares) and
-- FrameXML Constants.lua on mock widgets, with the classes and race/class pairs read from the patch's own ChrClasses.dbc
-- and CharBaseInfo.dbc: thirteen classes fill thirteen buttons; the playable ones come first, alphabetical (Barbarian,
-- Crusader, Demon Hunter, Monk, Necromancer, Shaman, Witch Doctor, Wizard), the rest in stock order; for every race each button is enabled exactly when the race may be its class, and a
-- click selects that class (the index SetSelectedClass gets, the checked button, the details pane); the Monk draws
-- The designer's own texture, the Necromancer the designer's too (im7mr.4) and every
-- stock class its stock atlas cell (the Witch Doctor draws its own plain WD texture whole, until the designer sends his); the Monk, the Necromancer and the Witch Doctor each greyed on a race they may not be; a Crusader and a Demon Hunter made playable in the data
-- move into their alphabetical places, the Demon Hunter's description and info rows on the Hunter slot; the layout (one row of thirteen at the bottom centre, the Name box on the left
-- panel). Then mutations that must each fail, and, when the stock pin is in the shared
-- scratch, a check that each shipped file is the stock file plus only the Monk's, the Necromancer's, the Witch Doctor's, the Demon Hunter's
-- strings, the order's and the colours' lines.
-- Mocks prove the Lua paths, not pixels. Run from the repo root: lua mod-diablocraft/scripts/tests/classes/test_monk_create_screen.lua
local ART = "client-patch/art/Interface/"
local STOCK = "azerothcore-wotlk/build/_agent-scratch/stock-gluexml-9b46c3a/Interface/"
local ROGUE = {0.49609375, 0.7421875, 0, 0.25}
-- The classes drawn whole from their own texture (the designer's art); every other class its stock atlas cell.
local OWN = {MONK = "Interface\\Glues\\CharacterCreate\\Torment-Monk",
    NECROMANCER = "Interface\\Glues\\CharacterCreate\\Torment-Necromancer",
    WITCHDOCTOR = "Interface\\Glues\\CharacterCreate\\Torment-WitchDoctor"}
local ATLAS = "Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Classes"
local CIRCLES = "Interface\\TargetingFrame\\UI-Classes-Circles"
-- The order the designer asked for: D3's create screen is alphabetical; the stock classes follow in stock order.
local ORDER = {"WARRIOR", "PALADIN", "HUNTER", "MONK", "NECROMANCER", "SHAMAN", "WITCHDOCTOR", "MAGE", "ROGUE", "PRIEST", "DEATHKNIGHT",
    "WARLOCK", "DRUID"}
local unpack = unpack or table.unpack

-- Runs a chunk with env as its globals, on Lua 5.1 (the client's) and 5.2 (run_tests.py's `lua`).
local function run(chunk, env)
    if setfenv then
        local fn = assert(loadstring(chunk)); setfenv(fn, env); return fn()
    end
    return assert(load(chunk, "chunk", "t", env))()
end

local function read(path)
    local f = assert(io.open(path, "rb")); local t = f:read("*a"); f:close(); return t
end

local function u32(raw, at)
    local a, b, c, d = raw:byte(at, at + 3)
    return a + b * 256 + c * 65536 + d * 16777216
end

-- A WDBC file's records as {offset of field 0}, and a reader for its string block.
local function dbc(path)
    local raw = read(path)
    assert(raw:sub(1, 4) == "WDBC", path .. " is not a WDBC file")
    local n, size = u32(raw, 5), u32(raw, 13)
    local records, block = {}, 21 + n * size
    for r = 0, n - 1 do records[#records + 1] = 21 + r * size end
    return raw, records, function(offset) return raw:sub(block + offset, raw:find("\0", block + offset, true) - 1) end
end

-- GetAvailableClasses' answer (name, file token, enabled flag per class, in ChrClasses order) and each class's id.
local CLASSES, IDS = {}, {}
do
    local raw, records, text = dbc("client-patch/dbc/ChrClasses.dbc")
    for _, at in ipairs(records) do
        IDS[#IDS + 1] = u32(raw, at)
        local name, token = text(u32(raw, at + 4 * 4)), text(u32(raw, at + 4 * 55))
        assert(token:match("^[A-Z]+$"), "ChrClasses field 55 is the file token, got " .. token)
        CLASSES[#CLASSES + 1] = name; CLASSES[#CLASSES + 1] = token; CLASSES[#CLASSES + 1] = 1
    end
end
-- CharBaseInfo's race/class pairs; the create screen's race index N is the Nth race id.
local PAIRS, RACES = {}, {}
do
    local raw, records = dbc("client-patch/dbc/CharBaseInfo.dbc")
    for _, at in ipairs(records) do
        local race, class = raw:byte(at, at + 1)
        if not PAIRS[race] then PAIRS[race] = {}; RACES[#RACES + 1] = race end
        PAIRS[race][class] = true
    end
    table.sort(RACES)
end
local INDEX = {}
for i = 1, #CLASSES / 3 do INDEX[CLASSES[i * 3 - 1]] = i end

local function widget()
    local w = {shown = false, enabled = false, checked = 0}
    function w:SetTexCoord(...) self.coords = {...} end
    function w:SetTexture(t) self.texture = t end
    function w:SetID(id) self.id = id end
    function w:GetID() return self.id end
    function w:Show() self.shown = true end
    function w:Hide() self.shown = false end
    function w:Enable() self.enabled = true end
    function w:Disable() self.enabled = false end
    function w:SetChecked(v) self.checked = v end
    function w:SetText(t) self.text = t end
    function w:SetValue() end
    function w:SetDesaturated(d) self.desaturated = d; return true end
    function w:SetVertexColor() end
    return w
end

-- A text without the class colour codes test_class_colours.lua checks.
local function plain(text)
    return text and (text:gsub("|cff%x%x%x%x%x%x", ""):gsub("|r", ""))
end

-- One run of the screen on the given sources; returns the widgets and the message() calls.
local function screen(src)
    local env = setmetatable({}, {__index = _G})
    local messages = {}
    env.message = function(m) messages[#messages + 1] = m end
    env.strupper = string.upper
    env._G = env
    env.SEX_MALE, env.SEX_FEMALE = 2, 3
    env.GetSelectedSex = function() return 2 end
    for name, id in src.xml:gmatch('<CheckButton name="(CharacterCreateClassButton%d+)"[^>]* id="(%d+)"') do
        env[name] = widget(); env[name .. "NormalTexture"] = widget(); env[name .. "PushedTexture"] = widget()
        env[name].id = tonumber(id)
        local ring = widget()
        env[name].GetCheckedTexture = function() return ring end
        local normal = env[name .. "NormalTexture"]
        env[name].GetNormalTexture = function() return normal end
        env[name .. "DisableTexture"] = widget()
    end
    for _, name in ipairs({"CharacterCreateClassName", "CharacterCreateClassIcon", "CharacterCreateClassLabel",
        "CharacterCreateClassRolesText", "CharacterCreateClassText", "CharacterCreateClassScrollFrameScrollBar"}) do
        env[name] = widget()
    end
    for i = 1, 10 do
        local race, normal = widget(), widget()
        race.GetNormalTexture = function() return normal end
        env["CharacterCreateRaceButton" .. i] = race
    end
    env.CharacterCreate = {selectedRace = 1}
    run(src.strings, env)
    run(src.create, env)
    env.PlaySound = function() end
    env.SetCharacterRace = function() end         -- the race pane is not under test
    return env, messages
end

local function constants(text)
    -- Constants.lua's client calls (FillLocalizedClassList, bit.bor, ...) answer nothing; only its tables are read.
    local stub = setmetatable({}, {__index = function() return function() return 0 end end})
    local env = setmetatable({bit = stub}, {__index = function(_, k) return _G[k] or function() end end})
    run(text, env)
    return env
end

local function same(a, b)
    if #a ~= #b then return false end
    for i = 1, #a do if a[i] ~= b[i] then return false end end
    return true
end

-- CharacterCreate.xml's class button OnClick, which the template carries (asserted in check).
local function click(env, button)
    if button.enable then env.CharacterClass_OnClick(button:GetID()) end
end

-- The screen with the given classes and pairs: GetSelectedClass/SetSelectedClass keep the selection like the client.
local function setup(src, classes, pairs)
    local env, messages = screen(src)
    local state = {}
    env.GetSelectedClass = function()
        local i = state.class or 0
        return classes[i * 3 - 2], classes[i * 3 - 1], i
    end
    env.SetSelectedClass = function(i) state.class = i; state.set = i end
    env.GetSelectedRace = function() return env.CharacterCreate.selectedRace end
    -- The client answers 1 or nil.
    env.IsRaceClassValid = function(race, class) return pairs[RACES[race]] and pairs[RACES[race]][IDS[class]] or nil end
    return env, messages, state
end

-- Each button's class token, by the index it carries.
local function tokens(env, classes)
    local t = {}
    for n = 1, #classes / 3 do t[n] = classes[env["CharacterCreateClassButton" .. n]:GetID() * 3 - 1] end
    return t
end

local function check(src)
    assert(src.xml:find("CharacterClass_OnClick%(self:GetID%(%)%);"), "the button's OnClick passes its id")
    local env, messages, state = setup(src, CLASSES, PAIRS)
    assert(#RACES == env.MAX_RACES, "CharBaseInfo has the screen's " .. env.MAX_RACES .. " races")
    for r = 1, #RACES do
        env.CharacterCreate.selectedRace = r
        env.CharacterCreateEnumerateClasses(unpack(CLASSES))
        assert(#messages == 0, "the fill aborted: " .. tostring(messages[1]))
        assert(same(tokens(env, CLASSES), ORDER), "race " .. RACES[r] .. ": the order is " ..
            table.concat(tokens(env, CLASSES), " "))
        for n, token in ipairs(ORDER) do
            local id, button = INDEX[token], env["CharacterCreateClassButton" .. n]
            local what = "race " .. RACES[r] .. ", button " .. n .. " (" .. token .. "): "
            local valid = PAIRS[RACES[r]][IDS[id]] == true
            assert(button.shown and button.name == CLASSES[id * 3 - 2], what .. "shown, with its name")
            assert(button.enabled == valid and (button.enable or false) == valid, what .. "enabled exactly when valid")
            local normal = env["CharacterCreateClassButton" .. n .. "NormalTexture"]
            local pushed = env["CharacterCreateClassButton" .. n .. "PushedTexture"]
            if OWN[token] then
                assert(normal.texture == OWN[token] and pushed.texture == OWN[token], what .. "the designer's texture")
                assert(same(normal.coords, {0, 1, 0, 1}), what .. "drawn whole")
            else
                assert(normal.texture == ATLAS and pushed.texture == ATLAS, what .. "the stock atlas")
                assert(same(normal.coords, env.CLASS_ICON_TCOORDS[token]), what .. "its stock cell")
            end
            state.class, state.set = 0, nil
            click(env, button)
            if valid then
                assert(state.set == id, what .. "selects class index " .. id .. ", got " .. tostring(state.set))
                for m = 1, #ORDER do
                    assert(env["CharacterCreateClassButton" .. m].checked == (m == n and 1 or 0), what .. "checks only itself")
                end
                assert(plain(env.CharacterCreateClassName.text) == CLASSES[id * 3 - 2], what .. "names its class")
                assert(plain(env.CharacterCreateClassLabel.text) == CLASSES[id * 3 - 2], what .. "the details pane's class")
                local icon = env.CharacterCreateClassIcon
                if OWN[token] then
                    assert(icon.texture == OWN[token] and same(icon.coords, {0, 1, 0, 1}), what .. "details: the designer's icon")
                else
                    assert(icon.texture == CIRCLES and same(icon.coords, env.CLASS_ICON_TCOORDS[token]),
                        what .. "details: the stock circle")
                end
            else
                assert(state.set == nil, what .. "a greyed button selects nothing")
                assert(plain(button.tooltip) == env[token .. "_DISABLED"], what .. "the greyed tooltip")
            end
        end
    end

    -- The Monk's details pane.
    state.class = INDEX.MONK
    env.SetCharacterClass(INDEX.MONK)
    assert(env.CharacterCreateClassText.text == env.CLASS_MONK .. "|n|n", "the Monk's description")
    local _, rows = env.CharacterCreateClassRolesText.text:gsub("\n\n", "")
    assert(rows == 5, "five Monk info rows, got " .. rows)

    -- A paid customisation of a Monk: only the Monk's button stays enabled.
    env.PAID_SERVICE_TYPE = env.PAID_CHARACTER_CUSTOMIZATION
    env.CharacterChangeFixup()
    for n, token in ipairs(ORDER) do
        assert(env["CharacterCreateClassButton" .. n].enabled == (token == "MONK"), "paid change: button " .. n)
    end
    env.PAID_SERVICE_TYPE = nil

    -- The Necromancer's details pane.
    state.class = INDEX.NECROMANCER
    env.SetCharacterClass(INDEX.NECROMANCER)
    assert(env.CLASS_NECROMANCER and env.CharacterCreateClassText.text == env.CLASS_NECROMANCER .. "|n|n",
        "the Necromancer's description")
    _, rows = env.CharacterCreateClassRolesText.text:gsub("\n\n", "")
    assert(rows == 5, "five Necromancer info rows, got " .. rows)
    assert(env.CharacterCreateClassIcon.texture == OWN.NECROMANCER and same(env.CharacterCreateClassIcon.coords, {0, 1, 0, 1}),
        "the Necromancer's details icon: the designer's, whole")

    -- The Witch Doctor's details pane: its own plain WD texture, whole, until the designer's icon.
    state.class = INDEX.WITCHDOCTOR
    env.SetCharacterClass(INDEX.WITCHDOCTOR)
    assert(env.CLASS_WITCHDOCTOR and env.CharacterCreateClassText.text == env.CLASS_WITCHDOCTOR .. "|n|n",
        "the Witch Doctor's description")
    _, rows = env.CharacterCreateClassRolesText.text:gsub("\n\n", "")
    assert(rows == 5, "five Witch Doctor info rows, got " .. rows)
    assert(env.CharacterCreateClassIcon.texture == OWN.WITCHDOCTOR and same(env.CharacterCreateClassIcon.coords, {0, 1, 0, 1}),
        "the Witch Doctor's details icon: its own texture, whole")

    -- The Demon Hunter's details pane: the Hunter slot's text is the Demon Hunter's, not the stock Hunter's.
    state.class = INDEX.HUNTER
    env.SetCharacterClass(INDEX.HUNTER)
    assert(env.CharacterCreateClassText.text == env.CLASS_HUNTER .. "|n|n", "the Demon Hunter's description")
    assert(env.CLASS_HUNTER:find("^Demon Hunters ") and env.CLASS_HUNTER_FEMALE == env.CLASS_HUNTER,
        "the Hunter slot's description is the Demon Hunter's, for both sexes")
    _, rows = env.CharacterCreateClassRolesText.text:gsub("\n\n", "")
    assert(rows == 5, "five Demon Hunter info rows, got " .. rows)
    assert(env.CharacterCreateClassRolesText.text:find("Hatred and Discipline", 1, true), "the info rows name the two resources")
    assert(not env.CharacterCreateClassRolesText.text:find("beast", 1, true), "no stock Hunter info row is left")

    -- The Shaman's details pane: the stock cell (the Shaman is the stock class), Torment's text: Maelstrom, a Ritual Mace and a Totem.
    state.class = INDEX.SHAMAN
    env.SetCharacterClass(INDEX.SHAMAN)
    assert(env.CharacterCreateClassText.text == env.CLASS_SHAMAN .. "|n|n", "the Shaman's description")
    assert(env.CLASS_SHAMAN_FEMALE == env.CLASS_SHAMAN and env.CLASS_SHAMAN:find("^Shaman are callers of the elements"),
        "the Shaman's description is Torment's, for both sexes")
    assert(env.CLASS_SHAMAN:find("Maelstrom", 1, true) and not env.CLASS_SHAMAN:find("mana", 1, true), "it names Maelstrom, not mana")
    _, rows = env.CharacterCreateClassRolesText.text:gsub("\n\n", "")
    assert(rows == 5, "five Shaman info rows, got " .. rows)
    assert(env.CharacterCreateClassRolesText.text:find("Maelstrom", 1, true) and env.CharacterCreateClassRolesText.text:find("Ritual Mace", 1, true),
        "the info rows name the resource and the weapon")
    assert(not env.CharacterCreateClassRolesText.text:find("Healer", 1, true) and not env.CharacterCreateClassRolesText.text:find("mana", 1, true),
        "no stock Shaman info row is left")
    assert(env.CharacterCreateClassIcon.texture == CIRCLES and same(env.CharacterCreateClassIcon.coords, env.CLASS_ICON_TCOORDS.SHAMAN),
        "the Shaman's details icon is the stock Shaman cell")

    -- A class no race may be: greyed, with its own tooltip, and back in its stock place (the Shaman's is the stock Shaman's).
    for _, case in ipairs({{"MONK", "Monk", {"WARRIOR", "PALADIN", "HUNTER", "NECROMANCER", "SHAMAN", "WITCHDOCTOR", "MAGE"}},
        {"NECROMANCER", "Necromancer", {"WARRIOR", "PALADIN", "HUNTER", "MONK", "SHAMAN", "WITCHDOCTOR", "MAGE"}},
        {"WITCHDOCTOR", "Witch Doctor", {"WARRIOR", "PALADIN", "HUNTER", "MONK", "NECROMANCER", "SHAMAN", "MAGE"}},
        {"HUNTER", "Demon Hunter", {"WARRIOR", "PALADIN", "MONK", "NECROMANCER", "SHAMAN", "WITCHDOCTOR", "MAGE"}},
        {"SHAMAN", "Shaman", {"WARRIOR", "PALADIN", "HUNTER", "MONK", "NECROMANCER", "WITCHDOCTOR", "MAGE"}}}) do
        local token, name, first = case[1], case[2], case[3]
        local without = {}
        for race, classes in pairs(PAIRS) do
            without[race] = {}
            for class in pairs(classes) do without[race][class] = class ~= IDS[INDEX[token]] or nil end
        end
        local env2 = setup(src, CLASSES, without)
        env2.CharacterCreateEnumerateClasses(unpack(CLASSES))
        local want, playable = {}, {}
        for _, t in ipairs(first) do want[#want + 1] = t; playable[t] = true end
        for _, t in ipairs({"PALADIN", "HUNTER", "ROGUE", "PRIEST", "DEATHKNIGHT", "SHAMAN", "WARLOCK", "DRUID", "MONK",
            "NECROMANCER", "WITCHDOCTOR"}) do
            if not playable[t] then want[#want + 1] = t end
        end
        assert(same(tokens(env2, CLASSES), want), "a " .. name .. " no race may be falls back to its stock place: got " ..
            table.concat(tokens(env2, CLASSES), " "))
        local at
        for n, t in ipairs(want) do if t == token then at = n end end
        local button = env2["CharacterCreateClassButton" .. at]
        assert(button.shown and not button.enabled, "a greyed " .. name)
        assert(plain(button.tooltip) == name .. "\nYou must choose a different race to be this class.",
            "the greyed " .. name .. "'s tooltip")
    end

    -- The Crusader (Paladin slot) and the Demon Hunter (Hunter slot) are playable in the data: the loop above has them in their
    -- alphabetical places (Barbarian, Crusader, Demon Hunter, Monk, Necromancer, Witch Doctor, Wizard, then stock) with no edit to the screen.

    local c = constants(src.constants)
    -- The Monk's colour is class_colours.csv's (test_class_colours.lua checks the value).
    assert(c.RAID_CLASS_COLORS.MONK, "the Monk has a class colour in game")
    assert(same(c.CLASS_ICON_TCOORDS.MONK, ROGUE), "the in-game Monk icon is the Rogue's cell")
    assert(c.RAID_CLASS_COLORS.NECROMANCER, "the Necromancer has a class colour in game")
    assert(same(c.CLASS_ICON_TCOORDS.NECROMANCER, c.CLASS_ICON_TCOORDS.DEATHKNIGHT),
        "the in-game Necromancer icon is the Death Knight's cell")
    assert(c.RAID_CLASS_COLORS.WITCHDOCTOR, "the Witch Doctor has a class colour in game")
    assert(same(c.CLASS_ICON_TCOORDS.WITCHDOCTOR, c.CLASS_ICON_TCOORDS.SHAMAN),
        "the in-game Witch Doctor icon is the Shaman's cell")
    -- Blizzard_RaidUI gives CLASS_SORT_ORDER buttons 1..MAX_CLASSES and the pets button 11: it stays ten long.
    assert(#c.CLASS_SORT_ORDER == 10 and c.MAX_CLASSES == 10, "CLASS_SORT_ORDER stays the stock ten")

    -- The layout: the thirteen class buttons in one row centred at the bottom of the screen, their class name above
    -- them, and the Name box on the left panel under the gender buttons.
    local function anchor(name)
        local at = assert(src.xml:find('name="' .. name .. '"', 1, true), "no " .. name)
        return src.xml:match("<Anchor ([^>]*)/>", at)
    end
    local size = tonumber(src.xml:match('name="CharacterCreateIconButtonTemplate"[^\n]*\n%s*<Size x="(%d+)"'))
    assert(size == 38, "the class buttons keep the stock size, got " .. tostring(size))
    local first = anchor("CharacterCreateClassButton1")
    assert(first:find('point="BOTTOMLEFT" relativeTo="CharacterCreateFrame" relativePoint="BOTTOM"', 1, true),
        "the row hangs from the bottom of the screen: " .. first)
    local gap
    for n = 2, #ORDER do
        local a = anchor("CharacterCreateClassButton" .. n)
        local x = a:match('^point="LEFT" relativeTo="CharacterCreateClassButton' .. (n - 1) .. '" relativePoint="RIGHT" x="(%d+)" y="0"$')
        assert(x and (gap == nil or tonumber(x) == gap), "button " .. n .. " sits right of button " .. (n - 1) .. ": " .. a)
        gap = tonumber(x)
    end
    assert(tonumber(first:match('x="(%-?%d+)"')) == -(#ORDER * size + (#ORDER - 1) * gap) / 2, "the row is centred: " .. first)
    assert(anchor("CharacterCreateClassName"):find('relativeTo="CharacterCreateFrame" relativePoint="BOTTOM"', 1, true),
        "the class name sits with the row")
    local name = anchor("CharacterCreateNameEdit")
    assert(name:find('relativeTo="CharacterCreateConfigurationFrame"', 1, true), "the Name box is on the left panel: " .. name)
    assert(tonumber(name:match('y="(%-%d+)"')) < tonumber(anchor("CharacterCreateGenderButtonMale"):match('y="(%-%d+)"')) - size,
        "the Name box is under the gender buttons")
    assert(anchor("CharacterCreateRandomName"):find('relativeTo="CharacterCreateNameEdit"', 1, true),
        "the name's Randomize stays under the Name box")
end

local real = {create = read(ART .. "GlueXML/CharacterCreate.lua"), strings = read(ART .. "GlueXML/GlueStrings.lua"),
    xml = read(ART .. "GlueXML/CharacterCreate.xml"), constants = read(ART .. "FrameXML/Constants.lua")}
check(real)

local function mutant(field, from, to)
    local m = {}
    for k, v in pairs(real) do m[k] = v end
    local s, n = m[field]:gsub(from, to, 1)
    assert(n == 1, "mutation did not apply: " .. from)
    m[field] = s
    return m
end
local mutants = {
    {"the class limit back at twelve", mutant("create", "MAX_CLASSES_PER_RACE = 13;", "MAX_CLASSES_PER_RACE = 12;")},
    {"the class limit back at eleven", mutant("create", "MAX_CLASSES_PER_RACE = 13;", "MAX_CLASSES_PER_RACE = 11;")},
    {"no eleventh button", mutant("xml", 'name="CharacterCreateClassButton11"', 'name="CharacterCreateClassButtonX"')},
    {"no twelfth button", mutant("xml", 'name="CharacterCreateClassButton12"', 'name="CharacterCreateClassButtonX"')},
    {"no thirteenth button", mutant("xml", 'name="CharacterCreateClassButton13"', 'name="CharacterCreateClassButtonX"')},
    {"no Witch Doctor icon coords", mutant("create", '\t%["WITCHDOCTOR"%]\t= {', '\t["WITCHDOCTORX"]\t= {')},
    {"the Witch Doctor back on the Shaman's cell", mutant("create", '%["WITCHDOCTOR"%]\t= {0, 1, 0, 1}',
        '["WITCHDOCTOR"]\t= {0.25, 0.49609375, 0.25, 0.5}')},
    {"no Witch Doctor texture", mutant("create", '\t%["WITCHDOCTOR"%]\t= "', '\t["WITCHDOCTORX"]\t= "')},
    {"no Witch Doctor description", mutant("strings", "\nCLASS_WITCHDOCTOR = ", "\nCLASS_WITCHDOCTORX = ")},
    {"no Witch Doctor info row", mutant("strings", "\nCLASS_INFO_WITCHDOCTOR4 = ", "\nCLASS_INFO_WITCHDOCTORX = ")},
    {"no greyed Witch Doctor text", mutant("strings", "\nWITCHDOCTOR_DISABLED = ", "\nWITCHDOCTORX_DISABLED = ")},
    {"no in-game Witch Doctor icon", mutant("constants", '%["WITCHDOCTOR"%]\t= {', '["WITCHDOCTORX"]\t= {')},
    {"no in-game Witch Doctor colour", mutant("constants", 'RAID_CLASS_COLORS%["WITCHDOCTOR"%] = {', 'RAID_CLASS_COLORS["WITCHDOCTORX"] = {')},
    {"no Necromancer icon coords", mutant("create", '\t%["NECROMANCER"%]\t= {0', '\t["NECROMANCERX"]\t= {0')},
    {"the Necromancer back on the Death Knight's cell", mutant("create", '%["NECROMANCER"%]\t= {0, 1, 0, 1}',
        '["NECROMANCER"]\t= {0.25, 0.49609375, 0.5, 0.75}')},
    {"no Necromancer texture", mutant("create", '\t%["NECROMANCER"%]\t= "', '\t["NECROMANCERX"]\t= "')},
    {"no Necromancer description", mutant("strings", "\nCLASS_NECROMANCER = ", "\nCLASS_NECROMANCERX = ")},
    {"no Necromancer info row", mutant("strings", "\nCLASS_INFO_NECROMANCER4 = ", "\nCLASS_INFO_NECROMANCERX = ")},
    {"no greyed Necromancer text", mutant("strings", "\nNECROMANCER_DISABLED = ", "\nNECROMANCERX_DISABLED = ")},
    {"no in-game Necromancer icon", mutant("constants", '%["NECROMANCER"%]\t= {', '["NECROMANCERX"]\t= {')},
    {"no Monk icon coords", mutant("create", '\t%["MONK"%]\t= {0', '\t["MONKX"]\t= {0')},
    {"no Monk texture", mutant("create", '\t%["MONK"%]\t= "', '\t["MONKX"]\t= "')},
    {"the details pane keeps the circles", mutant("create", "CharacterCreateClassIcon:SetTexture%(", "(")},
    {"buttons keep their XML id", mutant("create", "button:SetID%(id%);", "")},
    {"validity asked by button", mutant("create", "IsRaceClassValid%(CharacterCreate.selectedRace, id%)",
        "IsRaceClassValid(CharacterCreate.selectedRace, index)")},
    {"the checked button by position", mutant("create", "if %( button:GetID%(%) == id %) then", "if ( i == id ) then")},
    {"the paid change by position", mutant("create", "selectedClass ~= button:GetID%(%)", "selectedClass ~= i")},
    {"no playable first", mutant("create", "if %( playable%[a%] ~= playable%[b%] %) then", "if ( false ) then")},
    {"playable in stock order", mutant("create", "elseif %( playable%[a%] and", "elseif ( false and")},
    {"the stock Hunter description", mutant("strings", "\nCLASS_HUNTER = \"Demon Hunters are mortals",
        "\nCLASS_HUNTER = \"Hunters are at home in the wilderness")},
    {"the stock Hunter description for women", mutant("strings", "\nCLASS_HUNTER_FEMALE = \"Demon Hunters",
        "\nCLASS_HUNTER_FEMALE = \"Hunters")},
    {"a stock Hunter info row", mutant("strings", "\nCLASS_INFO_HUNTER3 = \"[^\n]*",
        "\nCLASS_INFO_HUNTER3 = \"- Gains a beast of your choice as a lifelong companion.\";")},
    {"the stock Hunter greyed text", mutant("strings", "\nHUNTER_DISABLED = \"Demon Hunter", "\nHUNTER_DISABLED = \"Hunter")},
    {"the stock Shaman description", mutant("strings", "\nCLASS_SHAMAN = \"Shaman are callers", "\nCLASS_SHAMAN = \"Shaman use the power")},
    {"the stock Shaman description for women", mutant("strings", "\nCLASS_SHAMAN_FEMALE = \"Shaman are callers", "\nCLASS_SHAMAN_FEMALE = \"Shaman use the power")},
    {"no Shaman info row", mutant("strings", "\nCLASS_INFO_SHAMAN4 = ", "\nCLASS_INFO_SHAMANX = ")},
    {"a stock Shaman info row", mutant("strings", "\nCLASS_INFO_SHAMAN4 = \"[^\n]*", "\nCLASS_INFO_SHAMAN4 = \"- Uses mana as a resource.\";\nCLASS_INFO_SHAMAN5 = \"- Uses mana as a resource.\";")},
    {"the stock Shaman role", mutant("strings", "\nCLASS_INFO_SHAMAN0 = \"%- Role: Damage\"", "\nCLASS_INFO_SHAMAN0 = \"- Role: Healer, Damage\"")},
    {"no Monk description", mutant("strings", "\nCLASS_MONK = ", "\nCLASS_MONKX = ")},
    {"button 7 starts a second row", mutant("xml",
        '<Anchor point="LEFT" relativeTo="CharacterCreateClassButton6" relativePoint="RIGHT" x="6" y="0"/>',
        '<Anchor point="TOP" relativeTo="CharacterCreateClassButton1" relativePoint="BOTTOM" x="0" y="-6"/>')},
    {"the row off centre", mutant("xml", 'relativePoint="BOTTOM" x="%-283" y="58"', 'relativePoint="BOTTOM" x="-200" y="58"')},
    {"the Name box back at the bottom", mutant("xml",
        '<Anchor point="TOP" relativeTo="CharacterCreateConfigurationFrame" relativePoint="TOP" x="0" y="%-466"/>',
        '<Anchor point="BOTTOM" x="0" y="55"/>')},
    {"no Monk class colour", mutant("constants", 'RAID_CLASS_COLORS%["MONK"%] = {', 'RAID_CLASS_COLORS["MONKX"] = {')},
}
for _, m in ipairs(mutants) do
    assert(not pcall(check, m[2]), "mutant survived: " .. m[1])
end

-- Each shipped file is the stock file with only the Monk lines added (and the one class-limit line changed), in
-- CharacterCreate.lua 3exia's icon and order lines, and in GlueStrings.lua the login strings whose values
-- test_glue_urls.py checks: their names are read from that test's lists, so the decided values live in one place.
local function login_strings()
    local t = read("mod-diablocraft/scripts/tests/client_extension/test_glue_urls.py")
    local names = {}
    for _, list in ipairs({"FETCHED_UNASKED = %b[]", "WEBSITE = %b{}", "TEXTS = %b[]"}) do
        local body = assert(t:match(list), "test_glue_urls.py has no " .. list)
        for name in body:gmatch('"([A-Z][A-Z0-9_]+)"') do names[name] = true end
    end
    return names
end

local function stock_diff(art)
    local login = login_strings()
    local function is_login(f, line)
        return f == "GlueXML/GlueStrings.lua" and login[line:match("^([A-Z0-9_]+) = ") or ""] == true
    end
    -- The Hunter slot's strings are the Demon Hunter's: the same names with new text.
    local function is_hunter(f, line)
        local name = line:match("^([A-Z0-9_]+) = ") or ""
        return f == "GlueXML/GlueStrings.lua" and (name == "CLASS_HUNTER" or name == "CLASS_HUNTER_FEMALE" or
            name == "HUNTER_DISABLED" or name:find("^CLASS_INFO_HUNTER%d$") ~= nil)
    end
    -- The Shaman's strings are the Shaman's own too (Torment's Shaman: Maelstrom, a Ritual Mace and a Totem): the same names with new text.
    local function is_shaman(f, line)
        local name = line:match("^([A-Z0-9_]+) = ") or ""
        return f == "GlueXML/GlueStrings.lua" and (name == "CLASS_SHAMAN" or name == "CLASS_SHAMAN_FEMALE" or
            name:find("^CLASS_INFO_SHAMAN%d$") ~= nil)
    end
    -- The Necromancer's and the Witch Doctor's lines, and the layout: the class buttons in one row at the bottom centre, each right of the one
    -- before, with their class name above them; the Name box on the left panel.
    local allowed = {"MONK", "Monk", "NECROMANCER", "Necromancer", "WITCHDOCTOR", "Witch Doctor", "ClassButton11", "ClassButton12",
        "ClassButton13", "^MAX_CLASSES_PER_RACE = 13;", "^%s*</?Anchors>%s*$", "^%s*</CheckButton>%s*$",
        "^%s*<Anchor point=\"BOTTOMLEFT\" relativeTo=\"CharacterCreateFrame\" relativePoint=\"BOTTOM\" x=\"%-283\" y=\"58\"/>",
        "^%s*<Anchor point=\"LEFT\" relativeTo=\"CharacterCreateClassButton%d+\" relativePoint=\"RIGHT\" x=\"6\" y=\"0\"/>",
        "^%s*<Anchor point=\"BOTTOM\" relativeTo=\"CharacterCreateFrame\" relativePoint=\"BOTTOM\" x=\"0\" y=\"104\"/>",
        "^%s*<Anchor point=\"TOP\" relativeTo=\"CharacterCreateConfigurationFrame\" relativePoint=\"TOP\" x=\"0\" y=\"%-466\"/>"}
    local allowed3exia = {"^%s*%-%- ", "CLASS_ICON_TEXTURE", "playable", "names", "order", "texture", "SetID%(id%)",
        "GetID%(%)", "^%s*local i = id%*3%-2;", "^%s*return a < b;", "^%s*end%)?;?%s*$", "^};", "^%s*for id=1, ",
        "^%s*for race=1, MAX_RACES do", "^%s*if %( IsRaceClassValid%(race, id%) %) then", "IsRaceClassValid%(CharacterCreate.selectedRace, id%)",
        "^\t\t\tlocal button = _G%[\"CharacterCreateClassButton\"..i%];", "^%s*$", "nameLevel"}
    -- The class colours (test_class_colours.lua): the generated blocks and the lines that read them.
    local allowedColours = {"^%s*%-%- ", "TORMENT_CLASS_COLORS", "TormentClass", "^RAID_CLASS_COLORS%[\"%u+\"%] = ",
        "^\t%[\"%u+\"%]\t= { r = [%d.]+, g = [%d.]+, b = [%d.]+, hex = \"%x+\", name = \"[%a ]+\" },",
        "color", "ring", "^%s*return text;", "^%s*return token;", "^%s*else%s*$", "^%s*end%s*$", "button%.token"}
    local droppedColours = {["\t\t\tbutton.tooltip = select(i, ...);\n"] = 1,
        ["\t\t\tbutton.tooltip = _G[strupper(select(i+1, ...)..\"_\"..\"DISABLED\")];\n"] = 1,
        ["\t\t\tCharacterCreateClassName:SetText(button.name);\n"] = 1, ["\tCharacterCreateClassLabel:SetText(className);\n"] = 1}
    -- The stock lines 3exia replaces: the fill's loop by position and the class-button checks by position.
    local dropped3exia = {["\tlocal coords;\n"] = true, ["\tlocal index = 1;\n"] = true,
        ["\tfor i=1, select(\"#\", ...), 3 do\n"] = true, ["\t\tindex = index + 1;\n"] = true,
        ["\t\tif ( (select(i+2, ...) == 1) and (IsRaceClassValid(CharacterCreate.selectedRace, index)) ) then\n"] = true,
        ["\t\tif ( i == id ) then\n"] = true, ["\t\t\tif (CharacterCreate.selectedClass ~= i) then\n"] = true,
        ["\t\t\t\tlocal button = _G[\"CharacterCreateClassButton\"..i];\n"] = true}
    for _, f in ipairs({"GlueXML/CharacterCreate.lua", "GlueXML/CharacterCreate.xml", "GlueXML/GlueStrings.lua",
        "FrameXML/Constants.lua"}) do
        local have = {}
        for line in read(STOCK .. f):gmatch("[^\n]*\n") do have[line] = (have[line] or 0) + 1 end
        for line in art[f]:gmatch("[^\n]*\n") do
            if (have[line] or 0) > 0 then have[line] = have[line] - 1
            else
                local ok = is_login(f, line) or is_hunter(f, line) or is_shaman(f, line)
                for _, p in ipairs(allowed) do ok = ok or line:find(p) ~= nil end
                if f == "GlueXML/CharacterCreate.lua" then
                    for _, p in ipairs(allowed3exia) do ok = ok or line:find(p) ~= nil end
                end
                if f == "GlueXML/CharacterCreate.lua" or f == "FrameXML/Constants.lua" then
                    for _, p in ipairs(allowedColours) do ok = ok or line:find(p) ~= nil end
                end
                assert(ok, f .. " adds a line that is not the Monk's, the Necromancer's, the Witch Doctor's or the Demon Hunter's: " .. line)
            end
        end
        for line, n in pairs(have) do
            assert(n == 0 or line == "MAX_CLASSES_PER_RACE = 10;\n" or is_login(f, line) or is_hunter(f, line) or is_shaman(f, line) or
                (f == "GlueXML/CharacterCreate.xml" and (line:find("^%s*<Anchor point=\"TOP\" x=\"%-90\" y=\"%-463\"/>") or
                    line:find("^%s*<Anchor point=\"TOP\" relativeTo=\"CharacterCreateClassButton[1-5]\" relativePoint=\"BOTTOM\" x=\"0\" y=\"%-6\"/>") or
                    line:find("^%s*<Anchor point=\"BOTTOM\" relativePoint=\"TOP\" x=\"0\" y=\"%-456\"/>") or
                    line:find("^%s*<Anchor point=\"BOTTOM\" x=\"0\" y=\"55\"/>"))) or
                (f == "GlueXML/CharacterCreate.lua" and n == 1 and dropped3exia[line]) or
                (f == "GlueXML/CharacterCreate.lua" and n == droppedColours[line]), f .. " drops a stock line: " .. line)
        end
    end
end

local stocked = io.open(STOCK .. "GlueXML/CharacterCreate.lua", "rb")
if stocked then
    stocked:close()
    local art = {}
    for _, f in ipairs({"GlueXML/CharacterCreate.lua", "GlueXML/CharacterCreate.xml", "GlueXML/GlueStrings.lua",
        "FrameXML/Constants.lua"}) do art[f] = read(ART .. f) end
    stock_diff(art)
    -- The login allowance is by name: any other stock string changed still fails.
    local changed = {}
    for k, v in pairs(art) do changed[k] = v end
    local s, n = changed["GlueXML/GlueStrings.lua"]:gsub('\nACCEPT = "Accept";\n', '\nACCEPT = "Agree";\n', 1)
    assert(n == 1, "mutation did not apply: ACCEPT")
    changed["GlueXML/GlueStrings.lua"] = s
    assert(not pcall(stock_diff, changed), "mutant survived: a stock string other than a login string changed")
    print("stock diff: checked against " .. STOCK)
else
    print("stock diff: skipped, the stock pin is not in the shared scratch")
end
print("test_monk_create_screen: ok (" .. #mutants .. " mutants killed)")
