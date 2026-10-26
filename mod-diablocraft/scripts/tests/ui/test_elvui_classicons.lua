-- luacheck: globals unpack
-- luacheck: ignore 111 121 122
-- Run from the repo root with `lua mod-diablocraft/scripts/tests/ui/test_elvui_classicons.lua`.
--
-- client-patch/addons/ElvUI_Torment/classicons.lua: the in-game class icon of the Witch Doctor and the Necromancer from
-- our own textures. Where a frame shows a class icon (ElvUI 6.09's skin of the /who list and the guild roster: one
-- texture a row, set to the stock atlas and given CLASS_ICON_TCOORDS[class] on each WhoList_Update and
-- GuildStatus_Update), our two classes get their whole texture and every other class keeps the atlas and its cell.
--
-- Proves: the coordinates of our two classes are the whole texture and no other class's changed; after each update
-- every row that shows one of them has our texture, every other row the atlas and its own cell (a row that showed one of
-- ours and now shows a Warrior is put back, a Death Knight keeps the cell the Necromancer's used to share); a
-- row with no icon (the skin off), a class the table does not know, no class, and the guild list outside its status view
-- are left alone; the result is the same whether ElvUI's own hook runs before ours or after (it registers at login,
-- after this file loads), and with a client whose SetTexture resets the coordinates; the textures named are the ones
-- the create screen names (CharacterCreate.lua) and files in client-patch/art. Then mutations that must each fail.
-- Mocks do NOT prove pixels: what the designer sees is on his card in docs/test-diablocraft-8xbd7.md.

unpack = unpack or table.unpack

local SRC = "client-patch/addons/ElvUI_Torment/classicons.lua"
local ATLAS = "Interface\\WorldStateFrame\\Icons-Classes"
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")

local function read(path)
    local file = assert(io.open(path, "rb"), "cannot read " .. path)
    local text = file:read("*a")
    file:close()
    return text
end

local function same(a, b)
    if #a ~= #b then return false end
    for i = 1, #a do if a[i] ~= b[i] then return false end end
    return true
end

-- The textures the create screen names for the two classes, and their files in the art.
local create = read("client-patch/art/Interface/GlueXML/CharacterCreate.lua")
local block = create:match("CLASS_ICON_TEXTURE = {(.-)};")
local OWN = {}
for _, token in ipairs({"NECROMANCER", "WITCHDOCTOR"}) do
    local escaped = assert(block:match('%["' .. token .. '"%]%s*=%s*"([^"]+)"'), "the create screen names no texture for " .. token)
    OWN[token] = escaped:gsub("\\\\", "\\")                   -- the Lua source's escapes are the string the client gets
    local path = "client-patch/art/" .. OWN[token]:gsub("\\", "/") .. ".blp"
    assert(io.open(path, "rb"), path .. " is not in the art"):close()
end
assert(OWN.NECROMANCER ~= OWN.WITCHDOCTOR)

local STOCK = {
    WARRIOR = {0, 0.25, 0, 0.25}, SHAMAN = {0.25, 0.49609375, 0.25, 0.5}, DEATHKNIGHT = {0.25, 0.5, 0.5, 0.75},
    NECROMANCER = {0.25, 0.5, 0.5, 0.75}, WITCHDOCTOR = {0.25, 0.49609375, 0.25, 0.5},
}
local WHOLE = {0, 1, 0, 1}
local ROWS = 4

-- A fresh client: the stock list functions, the rows ElvUI's skin makes (one icon texture each), the data the lists read.
-- `resets`: a client whose SetTexture puts the coordinates back to the whole file, the worst case.
local function client(resets)
    local g = {
        assert = assert, error = error, ipairs = ipairs, pairs = pairs, select = select, tostring = tostring,
        tonumber = tonumber, type = type, unpack = unpack, math = math, string = string, table = table,
    }
    g._G = g
    Mock.install(g)
    g.CLASS_ICON_TCOORDS = {}
    for token, coords in pairs(STOCK) do g.CLASS_ICON_TCOORDS[token] = {unpack(coords)} end
    g.WHOS_TO_DISPLAY, g.GUILDMEMBERS_TO_DISPLAY = ROWS, ROWS
    g.FriendsFrame = {playerStatusFrame = true}
    local c = {who = {}, guild = {}}
    g.GetNumWhoResults = function() return #c.who end
    g.GetWhoInfo = function(i) return "name", "guild", 70, "race", "class", "zone", c.who[i] end
    g.GetGuildRosterInfo = function(i) return "name", "rank", 1, 70, "class", "zone", "note", "onote", 1, 0, c.guild[i] end
    g.WhoList_Update = function() end
    g.GuildStatus_Update = function() end
    local function rows(prefix, index)
        for i = 1, ROWS do
            local button = Mock.widget("Button", prefix .. i)
            button[index] = i
            button.icon = button:CreateTexture("$parentIcon", "ARTWORK")
            button.icon:SetTexture(ATLAS)
            button.icon:SetTexCoord(0, 1, 0, 1)
            if resets then
                button.icon.SetTexture = function(self, texture)
                    Mock.methods.SetTexture.fn(self, texture)
                    self.texCoord = {0, 1, 0, 1}
                end
            end
        end
    end
    rows("WhoFrameButton", "whoIndex")
    rows("GuildFrameButton", "guildIndex")
    c.g = g
    return c
end

-- ElvUI 6.09's own hooks (Friends.lua:190, :321): the class's coordinates from CLASS_ICON_TCOORDS, nothing else.
local function elvui(c)
    local g = c.g
    g.hooksecurefunc("WhoList_Update", function()
        for i = 1, math.min(g.GetNumWhoResults(), g.WHOS_TO_DISPLAY) do
            local button = g["WhoFrameButton" .. i]
            local _, _, _, _, _, _, token = g.GetWhoInfo(button.whoIndex)
            if button.icon and token and g.CLASS_ICON_TCOORDS[token] then
                button.icon:SetTexCoord(unpack(g.CLASS_ICON_TCOORDS[token]))
            end
        end
    end)
    g.hooksecurefunc("GuildStatus_Update", function()
        if not g.FriendsFrame.playerStatusFrame then return end
        for i = 1, g.GUILDMEMBERS_TO_DISPLAY do
            local button = g["GuildFrameButton" .. i]
            local token = select(11, g.GetGuildRosterInfo(button.guildIndex))
            if token and g.CLASS_ICON_TCOORDS[token] then
                button.icon:SetTexCoord(unpack(g.CLASS_ICON_TCOORDS[token]))
            end
        end
    end)
end

local function loadSource(source, c)
    local env = setmetatable({}, {__index = function(_, key)
        local value = c.g[key]
        if value == nil then error("a loaded file referenced a global unavailable in 3.3.5: " .. tostring(key), 2) end
        return value
    end, __newindex = c.g})
    local chunk
    if setfenv then
        chunk = assert(loadstring(source, "classicons"))
        setfenv(chunk, env)
    else
        chunk = assert(load(source, "classicons", "t", env))
    end
    chunk()
end

local function expect(icon, token, what)
    local texture = OWN[token] or ATLAS
    local coords = OWN[token] and WHOLE or STOCK[token]
    assert(icon.texture == texture, what .. ": texture " .. tostring(icon.texture) .. ", want " .. texture)
    assert(same({icon:GetTexCoord()}, coords), what .. ": coords {" .. table.concat({icon:GetTexCoord()}, ", ") .. "}")
end

local function check(source, order, resets)
    local c = client(resets)
    local g = c.g
    if order == "elvui first" then elvui(c) end
    loadSource(source, c)
    if order == "elvui last" then elvui(c) end

    -- The coordinates: ours are the whole texture, every other class's are as the client has them.
    assert(same(g.CLASS_ICON_TCOORDS.NECROMANCER, WHOLE) and same(g.CLASS_ICON_TCOORDS.WITCHDOCTOR, WHOLE),
        "our classes' coordinates are the whole texture")
    for _, token in ipairs({"WARRIOR", "SHAMAN", "DEATHKNIGHT"}) do
        assert(same(g.CLASS_ICON_TCOORDS[token], STOCK[token]), token .. "'s cell is untouched")
    end

    -- /who: ours get their texture, the others the atlas and their cell.
    c.who = {"WITCHDOCTOR", "NECROMANCER", "WARRIOR", "DEATHKNIGHT"}
    g.WhoList_Update()
    for i, token in ipairs(c.who) do expect(g["WhoFrameButton" .. i].icon, token, order .. " /who row " .. i .. " " .. token) end
    -- the same rows reused for other classes: a row that showed one of ours is put back on the atlas
    c.who = {"WARRIOR", "SHAMAN", "WITCHDOCTOR", "WARRIOR"}
    g.WhoList_Update()
    for i, token in ipairs(c.who) do expect(g["WhoFrameButton" .. i].icon, token, order .. " /who again, row " .. i .. " " .. token) end
    -- fewer results than rows: the rows past them are not read
    c.who = {"NECROMANCER"}
    g.WhoList_Update()
    expect(g.WhoFrameButton1.icon, "NECROMANCER", order .. " one result")
    -- a class the table does not know and a row with no class are left alone
    c.who = {"FOO", nil, "WITCHDOCTOR"}
    g.WhoList_Update()
    expect(g.WhoFrameButton3.icon, "WITCHDOCTOR", order .. " past a stranger")
    -- a row with no icon (ElvUI's skin off) is no error
    g.WhoFrameButton2.icon = nil
    c.who = {"WITCHDOCTOR", "NECROMANCER"}
    g.WhoList_Update()
    expect(g.WhoFrameButton1.icon, "WITCHDOCTOR", order .. " beside a row with no icon")

    -- The guild roster in its status view.
    c.guild = {"NECROMANCER", "WITCHDOCTOR", "DEATHKNIGHT", "SHAMAN"}
    g.GuildStatus_Update()
    for i, token in ipairs(c.guild) do expect(g["GuildFrameButton" .. i].icon, token, order .. " guild row " .. i .. " " .. token) end
    c.guild = {"WARRIOR", "WARRIOR", "NECROMANCER", "WARRIOR"}
    g.GuildStatus_Update()
    for i, token in ipairs(c.guild) do expect(g["GuildFrameButton" .. i].icon, token, order .. " guild again, row " .. i .. " " .. token) end
    -- outside the status view the rows' icons are not touched
    g.FriendsFrame.playerStatusFrame = false
    local before = g.GuildFrameButton1.icon.texture
    c.guild = {"WITCHDOCTOR", "WITCHDOCTOR", "WITCHDOCTOR", "WITCHDOCTOR"}
    g.GuildStatus_Update()
    assert(g.GuildFrameButton1.icon.texture == before, order .. ": the guild list outside its status view is left alone")
end

local function run(source)
    for _, order in ipairs({"elvui first", "elvui last"}) do
        for _, resets in ipairs({false, true}) do check(source, order, resets) end
    end
end

local source = read(SRC)
run(source)

local function mutant(old, new)
    local first, last = source:find(old, 1, true)
    assert(first, "mutation target not found: " .. old)
    assert(not source:find(old, last + 1, true), "mutation target found twice: " .. old)
    return source:sub(1, first - 1) .. new .. source:sub(last + 1)
end

local mutants = {
    {"our coordinates are the client's again", mutant("CLASS_ICON_TCOORDS[token] = {0, 1, 0, 1}", "CLASS_ICON_TCOORDS[token] = CLASS_ICON_TCOORDS[token]")},
    {"our texture is never drawn", mutant("icon:SetTexture(OWN[token] or ATLAS)", "icon:SetTexture(ATLAS)")},
    {"a row is not put back on the atlas", mutant("icon:SetTexture(OWN[token] or ATLAS)", "icon:SetTexture(OWN[token] or icon:GetTexture())")},
    {"the rows' coordinates are left to ElvUI", mutant("    icon:SetTexCoord(unpack(CLASS_ICON_TCOORDS[token]))\n", "")},
    {"the Necromancer draws the Witch Doctor's texture", mutant('NECROMANCER = "Interface\\\\Glues\\\\CharacterCreate\\\\Torment-Necromancer"', 'NECROMANCER = "Interface\\\\Glues\\\\CharacterCreate\\\\Torment-WitchDoctor"')},
    {"the Witch Doctor is not ours", mutant('    WITCHDOCTOR = "Interface\\\\Glues\\\\CharacterCreate\\\\Torment-WitchDoctor",\n', "")},
    {"the /who list is not hooked", mutant('hooksecurefunc("WhoList_Update", whoRows)', "local _ = whoRows")},
    {"the guild roster is not hooked", mutant('hooksecurefunc("GuildStatus_Update", guildRows)', "local _ = guildRows")},
    {"the guild list is drawn outside its status view", mutant("    if not FriendsFrame.playerStatusFrame then return end\n", "")},
    {"a row with no icon is an error", mutant("if button and button.icon then\n            local _, _, _, _, _, _, token", "if button then\n            local _, _, _, _, _, _, token")},
    {"a stranger is an error", mutant("if not (token and CLASS_ICON_TCOORDS[token]) then return end", "if false then return end")},
}
for _, case in ipairs(mutants) do
    local ok = pcall(run, case[2])
    assert(not ok, "mutation not caught: " .. case[1])
end

print(("test_elvui_classicons: ok (%d mutants killed)"):format(#mutants))
