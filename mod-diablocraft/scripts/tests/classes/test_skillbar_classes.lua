-- luacheck: globals AIO DCTunables WorldDBQuery CharDBQuery
-- luacheck: ignore 111 121 122 431 432
-- Run from repo root with `lua5.1 mod-diablocraft/scripts/tests/classes/test_skillbar_classes.lua`.
--
-- The server half of dc_skillbar.lua resolved through dc_class_map: the
-- catalogue for a mapped WoW class comes from the class-keyed tables with the
-- catalogue's own spell_id, categories in dc_class_category order, runes keyed
-- by their parent's name, and an unmapped class returns nothing. No class is
-- named in the code under test; the rows below are the only place a class
-- appears. This pins the "Part-2 query shape" in
-- docs/test-diablocraft-skills-window-class-data.md without a database.

-- The generated data the queries would return. Barbarian (wow 1 -> class 1) and
-- Wizard (wow 8 -> class 2); wow 2 has no dc_class_map row.
local CLASS_OF = {[1] = 1, [8] = 2}
local CATEGORIES = {
    [1] = {"Primary", "Secondary", "Defensive", "Might", "Tactics", "Rage"},
    [2] = {"Primary", "Secondary", "Defensive", "Force", "Conjuration", "Mastery"},
}
-- skills: {spell_id, skill_name (the key), category, unlock, element, the record's name (what the player reads)}
local SKILLS = {
    [2] = {
        {83100, "Magic Missile", "Primary", 1, "Arcane", "Magic Missile"},
        {83250, "Arcane Orb", "Primary", 3, "Arcane", "Arcane Orb"},
        {83310, "Frost Nova", "Secondary", 5, "Cold", "Frost Nova"},
        {83311, "Wave of Force", "Force", 8, "Arcane", "Wave of Force"},
        {83312, "Meteor", "Conjuration", 20, "Fire", "Meteor"},
        {83314, "Earthquake (Wizard)", "Conjuration", 30, "Physical", "Earthquake"},
    },
}
-- runes: {spell_id, parent_skill_name, rune_name, element, unlock}
local RUNES = {
    [2] = {
        {83275, "Magic Missile", "Charged Blast", "Arcane", 6},
        {83276, "Magic Missile", "Split", "Arcane", 18},
        {83313, "Frost Nova", "Frozen Mist", "Cold", 22},
    },
}
-- passives: {spell_id, passive_name (the key), unlock, the record's name (what the player reads)}
local PASSIVES = {
    [2] = {
        {83256, "Power Hungry", 10, "Power Hungry"},
        {83257, "Blur", 10, "Blur"},
        {83258, "Leech (Demon Hunter)", 60, "Leech"},
    },
}

local function result(rows)
    if not rows or #rows == 0 then return nil end
    local cursor = {index = 1}
    function cursor:NextRow() self.index = self.index + 1 return rows[self.index] ~= nil end
    function cursor:GetString(i) return tostring(rows[self.index][i + 1]) end
    function cursor:GetUInt32(i) return rows[self.index][i + 1] end
    return cursor
end

local queries = {}
_G.WorldDBQuery = function(sql)
    queries[#queries + 1] = sql
    local wow = tonumber(sql:match("wow_class_id%s*=%s*(%d+)"))
    local class = wow and CLASS_OF[wow]
    if not class then return nil end
    if sql:match("SELECT class_id FROM dc_class_map") then
        return result({{class}})
    elseif sql:match("rune_id = 0") then
        return result(SKILLS[class])
    elseif sql:match("rune_id <> 0") then
        return result(RUNES[class])
    elseif sql:match("JOIN dc_class_passive p") then
        return result(PASSIVES[class])
    elseif sql:match("SELECT g.category FROM") then
        local rows = {}
        for _, name in ipairs(CATEGORIES[class]) do rows[#rows + 1] = {name} end
        return result(rows)
    end
    return nil
end
_G.CharDBQuery = function() return nil end
_G.DCTunables = {
    Get = function() return nil end,
    Has = function() return false end,
    Or = function(_, _, fallback) return fallback end,
}

local handlers, pushed
_G.AIO = {
    AddAddon = function() return true end,
    AddHandlers = function(_, table) handlers = table return table end,
    AddOnInit = function() end,
    Handle = function(_, _, action, payload) pushed = {action = action, payload = payload} end,
}

local player = {level = 70, guid = 1, wowClass = 8, alive = true}
function player:GetLevel() return self.level end
function player:GetGUIDLow() return self.guid end
function player:GetClass() return self.wowClass end
function player:IsAlive() return self.alive end
-- In the open world: Request's instanceEdits hint reads no dc_rift row (test_skillbar_server.lua).
function player:GetInstanceId() return 0 end
function player:GetMapId() return 0 end
local currentCalls, casts = 0, {}
function player:GetCurrentSpell() currentCalls = currentCalls + 1 return nil end
function player:CastSpell(_, spell) casts[#casts + 1] = spell end

-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
dofile('mod-diablocraft/lua/aio/dc_skillbar.lua')

local function catalogue(wow)
    player.wowClass = wow
    pushed = nil
    handlers.Request(player)
    assert(pushed and pushed.action == "Show", "Request answers with Show")
    return pushed.payload
end

-- --- a mapped non-Barbarian class (Wizard, wow 8) ------------------------
local data = catalogue(8)
assert(#data.skills == 6, "six Wizard skills, got " .. #data.skills)
assert(data.skills[1].name == "Magic Missile" and data.skills[1].spell == 83100,
       "the catalogue's own spell_id is the skill's spell, not a name lookup")
assert(data.skills[1].element == "Arcane", "the skill's element comes through")
assert(data.skills[1].shown == "Magic Missile", "a skill shows its record's name")
assert(data.skills[6].name == "Earthquake (Wizard)" and data.skills[6].shown == "Earthquake",
       "a skill keeps its key and shows the record's own name (a name two classes share)")
assert(data.skills[1].locked == false and data.skills[1].unlock == 1,
       "unlock state is derived from the level and the catalogue's unlock_level")

assert(#data.categories == 6, "six categories, got " .. #data.categories)
assert(data.categories[4] == "Force" and data.categories[5] == "Conjuration"
       and data.categories[6] == "Mastery", "categories keep dc_class_category order")
assert(data.categories[1] == "Primary", "and start at primary")

assert(#data.runes["Magic Missile"] == 2, "two Magic Missile runes")
assert(data.runes["Magic Missile"][1].name == "Charged Blast"
       and data.runes["Magic Missile"][1].element == "Arcane"
       and data.runes["Magic Missile"][1].spell == 83275, "the rune carries name, element and spell")
assert(data.runes["Magic Missile"][2].unlock == 18, "and its own unlock level")
assert(#data.runes["Frost Nova"] == 1, "runes are keyed by their parent skill's name")

assert(#data.passives == 3 and data.passives[1].name == "Power Hungry"
       and data.passives[1].spell == 83256, "passives join through dc_class_passive")
assert(data.passives[1].shown == "Power Hungry", "a passive shows its record's name")
assert(data.passives[3].name == "Leech (Demon Hunter)" and data.passives[3].shown == "Leech",
       "a passive keeps its key and shows the record's own name")

-- Locked state follows the level: keep one rune above it on a level-5 character.
player.level = 5
data = catalogue(8)
local meteor
for _, skill in ipairs(data.skills) do if skill.name == "Meteor" then meteor = skill end end
assert(meteor and meteor.locked == true, "a level-20 skill is locked at level 5")
assert(data.runes["Frost Nova"][1].locked == true, "a level-22 rune is locked at level 5")
assert(data.runes["Magic Missile"][2].locked == true, "a level-18 rune is locked at level 5")
player.level = 70

-- --- an unmapped class (wow 2) -------------------------------------------
data = catalogue(2)
assert(#data.skills == 0 and next(data.runes) == nil and #data.passives == 0
       and #data.categories == 0, "an unmapped class draws nothing")
-- The four data queries each ran; none named a class.
local dataQueries = 0
for _, sql in ipairs(queries) do
    if sql:match("dc_class_map") then dataQueries = dataQueries + 1 end
    assert(not sql:match("[Bb]arbarian") and not sql:match("[Ww]izard"),
           "no query names a class: " .. sql)
end
assert(dataQueries > 0, "the catalogue resolves through dc_class_map")

-- --- the Whirlwind gate serves mapped classes, refuses unmapped ----------
-- A mapped class reaches the handler (it reads the current channel), then
-- no-ops because no bar slot holds Whirlwind; an unmapped class is refused
-- before the channel read. Either way nothing is cast.
currentCalls, casts = 0, {}
player.wowClass = 8
handlers.Whirlwind(player, "start", 81004)
assert(currentCalls == 1, "a mapped class reaches the handler body")
assert(#casts == 0, "and casts nothing without a Whirlwind slot")
currentCalls, casts = 0, {}
player.wowClass = 2
handlers.Whirlwind(player, "start", 81004)
assert(currentCalls == 0, "an unmapped class is refused at the gate")
assert(#casts == 0, "and casts nothing")

print("Skillbar class-keyed catalogue checks passed")
