-- luacheck: ignore 111 112 113 121 122 212 213 542
-- Class colours on the login screens and in game, from data/class_colours.csv. Runs the shipped GlueXML
-- (CharacterCreate.lua, CharacterSelect.lua, GlueStrings.lua, the buttons CharacterCreate.xml declares) and FrameXML
-- Constants.lua on mock widgets, with the classes read from the patch's own ChrClasses.dbc. For every class button: the
-- tooltip (enabled and greyed) and the selected ring carry the class's colour for a live D3 class (a class_map.csv row)
-- and the stock look for every other; picking a class colours its name under the buttons and in the details pane; the
-- character list colours the class word, ghosts included; RAID_CLASS_COLORS holds the CSV colour for each live D3 class
-- and the stock colour for every other class (the Hunter too, until the Demon Hunter takes it, as the Paladin kept
-- its own until the Crusader). Each expected colour is computed here from the CSV's hex, not read from the generated Lua. Then mutations
-- that must each fail. Mocks prove the Lua paths, not pixels: how the tinted ring looks is the designer's screenshot.
-- Run from the repo root: lua mod-diablocraft/scripts/tests/classes/test_class_colours.lua
local ART = "client-patch/art/Interface/"
local STOCK = "azerothcore-wotlk/build/_agent-scratch/stock-gluexml-9b46c3a/Interface/"
local unpack = unpack or table.unpack

local function run(chunk, env)
    if setfenv then
        local fn = assert(loadstring(chunk)); setfenv(fn, env); return fn()
    end
    return assert(load(chunk, "chunk", "t", env))()
end

local function read(path)
    local f = assert(io.open(path, "rb")); local t = f:read("*a"); f:close(); return t
end

-- A plain CSV (no quoted fields) as a list of rows keyed by its header.
local function csv(path)
    local rows, header = {}, nil
    for line in read(path):gmatch("[^\r\n]+") do
        local cells = {}
        for cell in (line .. ","):gmatch("([^,]*),") do cells[#cells + 1] = cell end
        if not header then header = cells else
            local row = {}
            for i, k in ipairs(header) do row[k] = cells[i] end
            rows[#rows + 1] = row
        end
    end
    return rows
end

-- The live D3 classes (class_map.csv) and each class's colour from the CSV, by file token.
local LIVE, COLOUR = {}, {}
for _, row in ipairs(csv("mod-diablocraft/data/d3/class_map.csv")) do LIVE[row.d3_class] = true end
local PLANNED = {}
for _, row in ipairs(csv("mod-diablocraft/data/class_colours.csv")) do
    local hex = row.hex:lower()
    local c = {hex = hex, name = row.d3_class, r = tonumber(hex:sub(1, 2), 16) / 255,
        g = tonumber(hex:sub(3, 4), 16) / 255, b = tonumber(hex:sub(5, 6), 16) / 255}
    if LIVE[row.d3_class] then COLOUR[row.token] = c else PLANNED[#PLANNED + 1] = row.token end
end
assert(COLOUR.WARRIOR and COLOUR.PALADIN and COLOUR.MAGE and COLOUR.MONK and COLOUR.NECROMANCER and COLOUR.HUNTER and COLOUR.WITCHDOCTOR,
    "the seven built classes are live")
assert(#PLANNED == 0, "no class is planned any more, got " .. #PLANNED)

local function near(a, b) return math.abs(a - b) < 0.001 end
local function coded(text, c) return "|cff" .. c.hex .. text .. "|r" end

local function u32(raw, at)
    local a, b, c, d = raw:byte(at, at + 3)
    return a + b * 256 + c * 65536 + d * 16777216
end
-- GetAvailableClasses' answer from the client's ChrClasses.dbc: name, token, enabled, per class.
local CLASSES = {}
do
    local raw = read("client-patch/dbc/ChrClasses.dbc")
    local n, size = u32(raw, 5), u32(raw, 13)
    local block = 21 + n * size
    local function text(o) return raw:sub(block + o, raw:find("\0", block + o, true) - 1) end
    for r = 0, n - 1 do
        local at = 21 + r * size
        CLASSES[#CLASSES + 1] = text(u32(raw, at + 16)); CLASSES[#CLASSES + 1] = text(u32(raw, at + 220))
        CLASSES[#CLASSES + 1] = 1
    end
end

local function widget()
    local w = {shown = false, desaturated = nil, vertex = {1, 1, 1}}
    function w:SetTexCoord() end
    function w:SetTexture() end
    function w:SetID(id) self.id = id end
    function w:GetID() return self.id end
    function w:Show() self.shown = true end
    function w:Hide() self.shown = false end
    function w:Enable() self.enabled = true end
    function w:Disable() self.enabled = false end
    function w:SetChecked(v) self.checked = v end
    function w:SetText(t) self.text = t end
    function w:SetFormattedText(f, ...) self.text = string.format(f, ...) end
    function w:SetValue() end
    function w:SetDesaturated(d) self.desaturated = d; return 1 end
    function w:SetVertexColor(r, g, b) self.vertex = {r, g, b} end
    return w
end

-- The login screens' globals: every Char* frame name answers a widget, made on first use.
local function glue(src)
    local env = {}
    setmetatable(env, {__index = function(t, k)
        if type(k) == "string" and k:match("^Char") then local w = widget(); rawset(t, k, w); return w end
        return _G[k]
    end})
    env._G = env
    env.strupper = string.upper
    env.message = function(m) error("message(): " .. tostring(m)) end
    env.SEX_MALE, env.SEX_FEMALE = 2, 3
    env.GetSelectedSex = function() return 2 end
    for name in src.xml:gmatch('<CheckButton name="(CharacterCreateClassButton%d+)"') do
        local ring, normal = widget(), widget()
        env[name] = widget()
        env[name].GetCheckedTexture = function() return ring end
        env[name].GetNormalTexture = function() return normal end
    end
    env.CharacterCreate = {selectedRace = 1}
    run(src.strings, env)
    run(src.create, env)
    run(src.select, env)
    env.PlaySound = function() end
    env.SetCharacterRace = function() end
    env.CharacterChangeFixup = function() end
    env.GetFlavorText = function() return "" end
    return env
end

local function check(src)
    local env = glue(src)
    -- Every class valid but the Monk, so one live class shows its greyed tooltip.
    local state = {class = 1}
    env.IsRaceClassValid = function(_, id) return CLASSES[id * 3 - 1] ~= "MONK" and 1 or nil end
    env.GetSelectedClass = function() local i = state.class; return CLASSES[i * 3 - 2], CLASSES[i * 3 - 1], i end
    env.SetSelectedClass = function(i) state.class = i end
    env.GetSelectedRace = function() return 1 end
    -- Every ring starts in neither state, as if its button had shown another class before: each must set its own.
    for n = 1, #CLASSES / 3 do
        local ring = env["CharacterCreateClassButton" .. n]:GetCheckedTexture()
        ring.desaturated, ring.vertex = "unset", {0, 0, 0}
    end
    env.CharacterCreateEnumerateClasses(unpack(CLASSES))
    for n = 1, #CLASSES / 3 do
        local button = env["CharacterCreateClassButton" .. n]
        local id = button:GetID()
        local name, token = CLASSES[id * 3 - 2], CLASSES[id * 3 - 1]
        local c, ring, what = COLOUR[token], button:GetCheckedTexture(), "button " .. n .. " (" .. token .. "): "
        if token == "MONK" then
            assert(not button.enable, what .. "greyed for the test")
            assert(button.tooltip == coded("Monk", c) .. "\nYou must choose a different race to be this class.",
                what .. "the greyed tooltip names the class in its colour, the reason as stock: " .. button.tooltip)
        elseif c then
            assert(button.tooltip == coded(name, c), what .. "the tooltip in the class colour: " .. button.tooltip)
        else
            assert(button.tooltip == name, what .. "a stock class keeps its plain tooltip: " .. button.tooltip)
        end
        if c then
            assert(ring.desaturated == 1, what .. "the ring is the stock highlight desaturated")
            assert(near(ring.vertex[1], c.r) and near(ring.vertex[2], c.g) and near(ring.vertex[3], c.b),
                what .. "the ring is tinted the class colour")
        else
            assert(ring.desaturated == nil and ring.vertex[1] == 1 and ring.vertex[2] == 1 and ring.vertex[3] == 1,
                what .. "a stock class keeps the stock yellow ring")
        end
        if button.enable then
            state.class = 0
            env.CharacterClass_OnClick(id)
            local want = c and coded(name, c) or name
            assert(env.CharacterCreateClassName.text == want, what .. "the name under the buttons: " ..
                tostring(env.CharacterCreateClassName.text))
            assert(env.CharacterCreateClassLabel.text == want, what .. "the details pane's class: " ..
                tostring(env.CharacterCreateClassLabel.text))
        end
    end

    -- The character list: a Barbarian, a Wizard ghost, a Monk and a stock Paladin.
    local chars = {{"Grom", "Orc", "Barbarian", 70, nil}, {"Lia", "Human", "Wizard", 12, true},
        {"Chen", "Pandaren", "Monk", 70, nil}, {"Uther", "Human", "Paladin", 5, nil}}
    env.GetNumCharacters = function() return #chars end
    env.GetCharacterInfo = function(i)
        local ch = chars[i]
        return ch[1], ch[2], ch[3], ch[4], "Sanctuary", 2, ch[5]
    end
    env.IsConnectedToServer = function() return 1 end
    env.CharacterSelect = {selectedIndex = 1}
    env.CharacterSelect_SelectCharacter = function() end
    env.UpdateCharacterList()
    local want = {"Level 70 " .. coded("Barbarian", COLOUR.WARRIOR), "Level 12 " .. coded("Wizard", COLOUR.MAGE) ..
        " (Ghost)", "Level 70 " .. coded("Monk", COLOUR.MONK), "Level 5 Paladin"}
    for i, line in ipairs(want) do
        local got = env["CharSelectCharacterButton" .. i .. "ButtonTextInfo"].text
        assert(got == line, "character " .. i .. ": " .. tostring(got))
        assert(env["CharSelectCharacterButton" .. i .. "ButtonTextName"].text == chars[i][1], "character " .. i ..
            ": the name stays plain")
    end

    -- In game: the live D3 classes in their CSV colour, every other class its stock colour (the file's own stock
    -- table, checked against the stock pin below).
    local stub = setmetatable({}, {__index = function() return function() return 0 end end})
    local frame = setmetatable({bit = stub}, {__index = function(_, k) return _G[k] or function() end end})
    run(src.constants, frame)
    local stock = {}
    local body = src.constants:match("\nRAID_CLASS_COLORS = {\n(.-)\n};\n")
    for token, r, g, b in body:gmatch('%["(%u+)"%] = { r = ([%d.]+), g = ([%d.]+) ?, b = ([%d.]+) }') do
        stock[token] = {tonumber(r), tonumber(g), tonumber(b)}
    end
    local count = 0
    for token, have in pairs(frame.RAID_CLASS_COLORS) do
        count = count + 1
        local c = COLOUR[token]
        local w = c and {c.r, c.g, c.b} or stock[token]
        assert(w, "RAID_CLASS_COLORS." .. token .. " has no stock row and no live colour")
        assert(near(have.r, w[1]) and near(have.g, w[2]) and near(have.b, w[3]), "RAID_CLASS_COLORS." .. token)
    end
    assert(count == 13, "the ten stock classes, the Monk, the Necromancer and the Witch Doctor, got " .. count)
    assert(stock.HUNTER, "the Hunter keeps its stock row")
    for _, token in ipairs(PLANNED) do
        assert(not env.TORMENT_CLASS_COLORS[token], token .. " is planned: no login-screen colour yet")
    end
end

local real = {create = read(ART .. "GlueXML/CharacterCreate.lua"), strings = read(ART .. "GlueXML/GlueStrings.lua"),
    xml = read(ART .. "GlueXML/CharacterCreate.xml"), select = read(ART .. "GlueXML/CharacterSelect.lua"),
    constants = read(ART .. "FrameXML/Constants.lua")}
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
    {"no ring", mutant("create", "\t\tTormentClassRing%(button, button.token%);\n", "")},
    {"the ring not reset for a stock class", mutant("create", "ring:SetDesaturated%(nil%);", "")},
    {"the ring left yellow", mutant("create", "ring:SetDesaturated%(1%);", "")},
    {"a plain enabled tooltip", mutant("create", "TormentClassText%(select%(i, %.%.%.%), button.token%)", "select(i, ...)")},
    {"the whole greyed tooltip coloured", mutant("create", '"%^%(%[%^\\n%]%*%)%(%.%*%)%$"', '"^(.*)()$"')},
    {"a plain name label", mutant("create", "SetText%(TormentClassText%(button.name, button.token%)%)", "SetText(button.name)")},
    {"a plain details label", mutant("create", "SetText%(TormentClassText%(className, classFileName%)%)", "SetText(className)")},
    {"a plain character list", mutant("select", "\t\t\tclass = TormentClassText", "\t\t\tlocal _ = TormentClassText")},
    {"the Barbarian's stock colour in game", mutant("constants", 'RAID_CLASS_COLORS%["WARRIOR"%] = ', "local _ = ")},
    {"the Witch Doctor's stock colour in game", mutant("constants", 'RAID_CLASS_COLORS%["WITCHDOCTOR"%] = ', "local _ = ")},
    {"the Witch Doctor plain on the login screens", mutant("create", 'hex = "4cdb3e"', 'hex = "000000"')},
    {"the Crusader's stock colour in game", mutant("constants", 'RAID_CLASS_COLORS%["PALADIN"%] = ', "local _ = ")},
}
for _, m in ipairs(mutants) do
    assert(not pcall(check, m[2]), "mutant survived: " .. m[1])
end

-- CharacterSelect.lua is the stock file with only the class-word line and its comment added.
local stocked = io.open(STOCK .. "GlueXML/CharacterSelect.lua", "rb")
if stocked then
    stocked:close()
    local have = {}
    for line in read(STOCK .. "GlueXML/CharacterSelect.lua"):gmatch("[^\n]*\n") do have[line] = (have[line] or 0) + 1 end
    local added = 0
    for line in real.select:gmatch("[^\n]*\n") do
        if (have[line] or 0) > 0 then have[line] = have[line] - 1 else added = added + 1
            assert(line:find("TormentClass") or line:find("^%s*%-%- The class word"), "CharacterSelect.lua adds: " .. line)
        end
    end
    for line, n in pairs(have) do assert(n == 0, "CharacterSelect.lua drops a stock line: " .. line) end
    assert(added == 2, "two lines added, got " .. added)
    -- The file's stock RAID_CLASS_COLORS rows are the stock pin's, the Monk's placeholder gone.
    local pin = read(STOCK .. "FrameXML/Constants.lua"):match("\nRAID_CLASS_COLORS = {\n(.-)\n};")
    assert(pin and pin == real.constants:match("\nRAID_CLASS_COLORS = {\n(.-)\n};"), "the stock class colour rows")
    print("stock diff: checked against " .. STOCK)
else
    print("stock diff: skipped, the stock pin is not in the shared scratch")
end
print("test_class_colours: ok (" .. #mutants .. " mutants killed)")
