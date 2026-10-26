-- luacheck: ignore 111 112 113 121 122 431
-- diablocraft-blacksmith-tooltips: hovering a Blacksmith recipe result previews what the
-- craft will make, drawn by the real item tooltip (dc_tooltip.lua decorate()).
--
-- Server half (phase A): the preview record the server builds for a catalogue recipe, on four
-- fixtures - a Rare (no fixed affixes), a Legendary (one in-pool preset), a Set (a sockets
-- preset and a set block) and a short-pool Rare (the fill cannot reach the budget). It pins
-- the random count N against the roller's own budget (4 primary + 2 secondary, the presets
-- taken out of it), the D3 range of a fixed affix, the required level from the catalogue, and
-- that nothing promises Unique Equipped or a binding.
--
-- Client half (phase B): the same records rendered by the shipped tooltip. It pins D3's range
-- form +[10 - 12]% Movement Speed, the "+N Random Magic Properties" line, the set block, the
-- socket count, and the absence of the G4/G5 lines.
--
-- The C++ roller is not run here; test_blacksmith_tooltips.py runs the module's own CountsFor
-- and compares it with the counts this file prints.
local TOOLTIP_SOURCE = os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua"
local BLACKSMITH_SOURCE = os.getenv("DC_BLACKSMITH_LUA") or "mod-diablocraft/lua/aio/dc_blacksmith.lua"

----------------------------------------------------------------------------------------------------
-- Shared stubs and fixture data
----------------------------------------------------------------------------------------------------
-- A column a row does not carry is a NULL, and ALE hands a NULL back the way the live server
-- does (ALEQueryMethods.h over AzerothCore Field::GetData): 1.0 for a NULL DOUBLE
-- (GetDefaultValue<double>), 0 for the integer getters, "" for the string getter. The pool
-- fixtures leave value_min2/value_max2 off a single-part row exactly as dc_affix_pool stores
-- them NULL, so a preview that reads the column without testing IsNull fails here as it does live.
local function rows(list)
    local index = 1
    local function cell(column) return list[index][column + 1] end
    local function integer(_, column) local v = cell(column); return v == nil and 0 or v end
    return {GetUInt32 = integer, GetInt32 = integer,
        GetDouble = function(_, column) local v = cell(column); return v == nil and 1.0 or v end,
        GetString = function(_, column) local v = cell(column); return v == nil and "" or v end,
        IsNull = function(_, column) return cell(column) == nil end,
        NextRow = function() index = index + 1; return list[index] ~= nil end}
end

-- Pools keyed "<slot> <bracket>" -> {affix_id, name, kind, min, max, is_percent, order}.
local POOLS = {
    ["onehand rare"] = {{"damage", "Damage Increase", "primary", 5, 8, 1, 1},
        {"mainstat", "Primary Attribute", "primary", 525, 625, 0, 2},
        {"chc", "Critical Hit Chance", "primary", 4, 6, 1, 3},
        {"ias", "Attack Speed Increase", "primary", 5, 7, 1, 4},
        {"resall", "All Resistance", "secondary", 80, 100, 0, 1},
        {"laek", "Life per Kill", "secondary", 3000, 6000, 0, 2}},
    ["feet legendary"] = {{"ms", "Movement Speed", "primary", 10, 12, 1, 1},
        {"vit", "Vitality", "primary", 626, 750, 0, 2},
        {"armor", "Armor", "primary", 200, 300, 0, 3},
        {"chc", "Critical Hit Chance", "primary", 5, 6, 1, 4},
        {"ias", "Attack Speed Increase", "primary", 5, 7, 1, 5},
        {"resall", "All Resistance", "secondary", 141, 160, 0, 1},
        {"gf", "Gold Find", "secondary", 32, 35, 1, 2},
        {"laek", "Life per Kill", "secondary", 4000, 6000, 0, 3}},
    ["head legendary"] = {{"sockets", "Sockets", "primary", 1, 3, 0, 1},
        {"vit", "Vitality", "primary", 626, 750, 0, 2},
        {"chc", "Critical Hit Chance", "primary", 4, 6, 1, 3},
        {"ias", "Attack Speed Increase", "primary", 5, 7, 1, 4},
        {"armor", "Armor", "primary", 200, 300, 0, 5},
        {"skill_head", "", "primary", 10, 15, 0, 6},
        {"resall", "All Resistance", "secondary", 141, 160, 0, 1},
        {"gf", "Gold Find", "secondary", 32, 35, 1, 2},
        {"laek", "Life per Kill", "secondary", 4000, 6000, 0, 3}},
    ["legs rare"] = {{"damage", "Damage Increase", "primary", 5, 8, 1, 1}},
    -- A shield pool: block lines are required affixes outside the budget, plus an ordinary preset.
    ["offhand legendary"] = {{"blockamount", "Block Amount", "primary", 100, 200, 0, 1},
        {"ms", "Movement Speed", "primary", 10, 12, 1, 2},
        {"armor", "Armor", "primary", 200, 300, 0, 3},
        {"vit", "Vitality", "primary", 626, 750, 0, 4},
        {"chc", "Critical Hit Chance", "primary", 5, 6, 1, 5},
        {"resall", "All Resistance", "secondary", 141, 160, 0, 1},
        {"gf", "Gold Find", "secondary", 32, 35, 1, 2},
        {"laek", "Life per Kill", "secondary", 4000, 6000, 0, 3}},
    -- diablocraft-j0xsb: the offhand pool at rare - its wpnphy row is the required +X-Y Damage of a
    -- Source, Mojo or Phylactery (two-part, no weapon class), which no other offhand rolls. Four
    -- primaries, so the line taken outside the budget, or wrongly offered, shows in the count.
    -- diablocraft-7175z: its ias row is the Quiver's required Attack Speed Increase (affix_pools.csv
    -- offhand ias rare 15), which no other offhand rolls.
    ["offhand rare"] = {{"wpnphy", "Physical Damage", "primary", 262, 328, 0, 20, 263, 394},
        {"vit", "Vitality", "primary", 525, 625, 0, 2},
        {"chc", "Critical Hit Chance", "primary", 8, 10, 1, 5},
        {"ias", "Attack Speed Increase", "primary", 15, 15, 1, 6},
        {"resall", "All Resistance", "secondary", 80, 100, 0, 1},
        {"gf", "Gold Find", "secondary", 20, 25, 1, 2},
        {"laek", "Life per Kill", "secondary", 3000, 6000, 0, 3}},
    -- G1: a one-hand weapon pool - the seven elemental rows (one exclusive group, each a two-part
    -- roll) plus ordinary primaries and secondaries, so the fixed choice and the fill count are
    -- exercised with the group taken exactly once.
    ["onehand legendary"] = {{"wpnphy", "Physical Damage", "primary", 981, 1199, 0, 1, 1175, 1490, "damage1HNormal"},
        {"wpnfir", "Fire Damage", "primary", 981, 1199, 0, 1, 1175, 1490, "damage1HNormal"},
        {"wpncol", "Cold Damage", "primary", 981, 1199, 0, 1, 1175, 1490, "damage1HNormal"},
        {"wpnpsn", "Poison Damage", "primary", 981, 1199, 0, 1, 1175, 1490, "damage1HNormal"},
        {"wpnarc", "Arcane Damage", "primary", 981, 1199, 0, 1, 1175, 1490, "damage1HNormal"},
        {"wpnlit", "Lightning Damage", "primary", 981, 1199, 0, 1, 1175, 1490, "damage1HNormal"},
        {"wpnhol", "Holy Damage", "primary", 981, 1199, 0, 1, 1175, 1490, "damage1HNormal"},
        {"mainstat", "Primary Attribute", "primary", 626, 750, 0, 2},
        {"chc", "Critical Hit Chance", "primary", 5, 6, 1, 3},
        {"ias", "Attack Speed Increase", "primary", 5, 7, 1, 4},
        {"resall", "All Resistance", "secondary", 141, 160, 0, 1},
        {"gf", "Gold Find", "secondary", 32, 35, 1, 2},
        {"laek", "Life per Kill", "secondary", 4000, 6000, 0, 3}},
    -- A class item type's own lines (dc_affix_pool keeps them under "<slot>:<type>"; dc_items_data.cpp PoolFor reads the
    -- slot's rows and then these): the Ritual Mace's elemental lines and the Totem's, none of which the slot pools above hold.
    ["onehand:Ritual Mace rare"] = {{"dmgcol", "Cold Damage Increase", "primary", 10, 15, 1, 17},
        {"dmglit", "Lightning Damage Increase", "primary", 10, 15, 1, 19}},
    ["offhand:Totem rare"] = {{"maxmaelstrom", "Maximum Maelstrom", "primary", 100, 150, 0, 21},
        {"area", "Area Damage", "primary", 5, 8, 1, 22},
        {"cdr", "Cooldown Reduction", "primary", 3, 5, 1, 23},
        {"rcr", "Resource Cost Reduction", "primary", 3, 5, 1, 24}},
    -- A waist pool whose preset sits in the SECONDARY pool, so preset-kind accounting shows.
    ["waist legendary"] = {{"ms", "Movement Speed", "primary", 10, 12, 1, 1},
        {"vit", "Vitality", "primary", 626, 750, 0, 2},
        {"armor", "Armor", "primary", 200, 300, 0, 3},
        {"chc", "Critical Hit Chance", "primary", 5, 6, 1, 4},
        {"ias", "Attack Speed Increase", "primary", 5, 7, 1, 5},
        {"resall", "All Resistance", "secondary", 141, 160, 0, 1},
        {"gf", "Gold Find", "secondary", 32, 35, 1, 2},
        {"laek", "Life per Kill", "secondary", 4000, 6000, 0, 3}},
}
-- diablocraft-wtxig: dc_item_preset_range - an item's own range for a preset its slot's pool has
-- no row for. entry -> bracket -> the rows the preview's SELECT reads (affix_id, affix_name, kind,
-- value_min, value_max, is_percent, display_order).
local ITEM_PRESETS = {
    [200011] = {legendary = {{"chd", "Critical Hit Damage", "primary", 26, 50, 1, 7}}},
    -- diablocraft-sxj2c: The Helm of Rule's block line (item_preset_ranges.csv, Unique_Helm_011_x1),
    -- a block id on a non-shield, which the pool's eligible() refuses; the sheet row must not be.
    [200012] = {legendary = {{"block", "Chance to Block", "secondary", 11, 11, 1, 17}}},
}
-- Catalogue recipes: id -> entry, rarity, required level, enabled.
local RECIPES = {
    [9001] = {entry = 200001, rarity = "rare", required = 70, enabled = 1},
    [9002] = {entry = 200002, rarity = "legendary", required = 70, enabled = 0},
    [9003] = {entry = 200003, rarity = "set", required = 70, enabled = 0},
    [9004] = {entry = 200004, rarity = "rare", required = 70, enabled = 1},
    -- The fourth catalogue rarity: the loot/magic_* budget, not full_roll_*.
    [9005] = {entry = 200001, rarity = "magic", required = 70, enabled = 0},
    -- A preset that belongs to the SECONDARY pool, and a duplicate preset.
    [9006] = {entry = 200006, rarity = "legendary", required = 70, enabled = 0},
    [9007] = {entry = 200007, rarity = "legendary", required = 70, enabled = 0},
    -- A shield: its required block lines are outside the affix budget.
    [9008] = {entry = 200008, rarity = "legendary", required = 70, enabled = 0},
    -- A class-only item crafted by another class: the skill group belongs to the ITEM's class.
    [9009] = {entry = 200009, rarity = "set", required = 70, enabled = 0},
    -- G1: a weapon that authors THREE elemental presets (the Flying Axe case). D3's group is
    -- exclusive, so only the first is taken and the fill cannot add a second.
    [9010] = {entry = 200010, rarity = "legendary", required = 70, enabled = 0},
    -- diablocraft-wtxig: a preset its slot's pool does not hold, served by the item's own sheet row.
    [9011] = {entry = 200011, rarity = "legendary", required = 70, enabled = 0},
    -- diablocraft-sxj2c: an own preset the pool's eligibility gate would refuse (block, not a shield).
    [9012] = {entry = 200012, rarity = "legendary", required = 70, enabled = 0},
    -- diablocraft-j0xsb: the craftable rare caster offhands, and a quiver.
    [9013] = {entry = 200013, rarity = "rare", required = 70, enabled = 0},
    [9014] = {entry = 200014, rarity = "rare", required = 70, enabled = 0},
    [9015] = {entry = 200015, rarity = "rare", required = 70, enabled = 0},
    [9016] = {entry = 200016, rarity = "rare", required = 70, enabled = 0},
    -- The Shaman's class item types: the Ritual Mace (presets only its own pool holds) and the Totem.
    [9017] = {entry = 200017, rarity = "rare", required = 70, enabled = 0},
    [9018] = {entry = 200018, rarity = "rare", required = 70, enabled = 0},
}
-- Base item rows (load + the preview's own read): entry -> name, slot, class, level_req,
-- set_id, power, flavour, sell, presets, type, designated.
local BASES = {
    [200001] = {name = "Test Fist", slot = "onehand", class = "", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "", type = "Fist Weapon", designated = ""},
    [200002] = {name = "Board Walkers", slot = "feet", class = "", level = 0, set = "", power = "Legendary power text", flavour = "Tread lightly.", sell = 1234,
        presets = "ms;custom", type = "Boots", designated = ""},
    [200003] = {name = "Hallowed Hold", slot = "head", class = "monk", level = 0, set = "hallowed", power = "", flavour = "", sell = 1234,
        presets = "sockets;wpnhol", type = "Helm", designated = "monk"},
    [200004] = {name = "Test Legs", slot = "legs", class = "", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "", type = "Pants", designated = ""},
    [200006] = {name = "Secondary Preset Belt", slot = "waist", class = "", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "resall;ms", type = "Belt", designated = ""},
    [200007] = {name = "Duplicate Preset Boots", slot = "feet", class = "", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "ms;ms", type = "Boots", designated = ""},
    [200008] = {name = "Test Shield", slot = "offhand", class = "", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "blockamount;ms", type = "Shield", designated = ""},
    [200009] = {name = "Monk Only Helm", slot = "head", class = "monk", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "skill_head", type = "Helm", designated = "monk"},
    -- G1: three authored elemental presets; only the first (wpncol) may be taken.
    [200010] = {name = "Multi Element Fist", slot = "onehand", class = "", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "wpncol;wpnfir;wpnlit", type = "Fist Weapon", designated = ""},
    -- diablocraft-wtxig: crit damage is not in the waist pool; the sheet row is its home.
    [200011] = {name = "Sheet Belt", slot = "waist", class = "", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "chd;ias", type = "Belt", designated = ""},
    -- diablocraft-sxj2c: a helm whose block preset only the sheet holds, as The Helm of Rule.
    [200012] = {name = "Sheet Helm", slot = "head", class = "", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "block", type = "Helm", designated = ""},
    -- diablocraft-j0xsb: dc_items.cpp DamageOffhand - a Source, a Mojo and a Phylactery carry the
    -- pool's wpnphy as a required line outside the budget; a Quiver never rolls it.
    [200013] = {name = "Test Mojo", slot = "offhand", class = "witchdoctor", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "", type = "Mojo", designated = ""},
    [200014] = {name = "Test Source", slot = "offhand", class = "wizard", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "", type = "Source", designated = ""},
    [200015] = {name = "Test Phylactery", slot = "offhand", class = "necromancer", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "", type = "Phylactery", designated = ""},
    [200016] = {name = "Test Quiver", slot = "offhand", class = "demonhunter", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "", type = "Quiver", designated = ""},
    -- The class item types of the Shaman: a Ritual Mace whose two presets are lines of the type's own pool, and a Totem,
    -- built like a Source (the required +X-Y Damage) with four lines of its own in the pool.
    [200017] = {name = "Test Ritual Mace", slot = "onehand", class = "shaman", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "dmgcol;dmglit", type = "Ritual Mace", designated = "shaman"},
    [200018] = {name = "Test Totem", slot = "offhand", class = "shaman", level = 0, set = "", power = "", flavour = "", sell = 1234,
        presets = "", type = "Totem", designated = "shaman"},
}
-- dc_skill_affix: group_id -> the class ids that have a choice in it. The barbarian (7) has one
-- for skill_head; the monk (4) has none, which is what a class-only item must not borrow.
local SKILL_GROUPS = {skill_head = {[7] = true}}
-- dc_class_map / dc_class_primary_stats for the fixtures.
-- G1: dc_weapon_class, the sourced type -> damage bracket map the mirror reads.
local WEAPON_CLASSES = {["Fist Weapon"] = "damage1HNormal"}
local CLASS_KEYS = {[1] = "barbarian", [4] = "monk"}
local CLASS_IDS = {barbarian = 7, monk = 4, shaman = 3}
local CLASS_STATS = {barbarian = "Strength", monk = "Dexterity", shaman = "Intelligence"}
local tunables = {full_roll_primary_affixes = 4, full_roll_secondary_affixes = 2,
    magic_primary_affixes = 1, magic_secondary_affixes = 1}
DCTunables = {Get = function(category, name) return category == "loot" and tunables[name] or nil end}
DCTunables.Has = function(category, name) return DCTunables.Get(category, name) ~= nil end
local queries = {}
local function tooltipQueries(sql)
    queries[#queries + 1] = sql
    if sql:find("FROM dc_blacksmith_catalog", 1, true) then
        local id = tonumber(sql:match("id=(%d+)")); local r = RECIPES[id]
        return r and rows({{r.entry, r.rarity, r.required, r.enabled}}) or nil
    elseif sql:find("FROM dc_base_item WHERE entry=", 1, true) then
        local b = BASES[tonumber(sql:match("entry=(%d+)"))]
        return b and rows({{b.presets, b.type, b.designated}}) or nil
    elseif sql:find("FROM dc_weapon_class WHERE weapon_type=", 1, true) then
        local weaponClass = WEAPON_CLASSES[sql:match("weapon_type='([^']*)'")]
        return weaponClass and rows({{weaponClass}}) or nil
    elseif sql:find("FROM dc_item_preset_range", 1, true) then
        -- diablocraft-wtxig: the preview's second home for a preset, read per (entry, bracket) like
        -- PlanRoll's itemPresets. Its SELECT carries no value_step and no weapon class.
        local entry = tonumber(sql:match("entry=(%d+)"))
        if not entry then
            -- diablocraft-ytzea: the tooltip's load reads the whole table (entry, then the row) to name a line.
            local out = {}
            for id, brackets in pairs(ITEM_PRESETS) do
                for _, item in pairs(brackets) do
                    for _, p in ipairs(item) do out[#out + 1] = {id, p[1], p[2], p[6], p[3], p[7]} end
                end
            end
            return rows(out)
        end
        local bracket = sql:match("item_level_bracket='([^']*)'")
        local item = ITEM_PRESETS[entry] and ITEM_PRESETS[entry][bracket]
        return item and rows(item) or nil
    elseif sql:find("item_level_bracket=", 1, true) then
        local slot = sql:match("slot='([^']*)'"); local bracket = sql:match("item_level_bracket='([^']*)'")
        local pool = POOLS[slot .. " " .. bracket]
        if not pool then return nil end
        -- The pool SELECT reads affix_id..display_order then value_min2,value_max2,weapon_class (G1).
        -- value_min2/value_max2 stay off a single-part row (NULL), as the generated pool stores them.
        local out = {}
        for _, p in ipairs(pool) do
            out[#out + 1] = {p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], p[10] or ""}
        end
        return rows(out)
    elseif sql:find("FROM dc_affix_pool", 1, true) then
        local out = {}
        for key, pool in pairs(POOLS) do
            local slot = key:match("^(.-) %S+$")
            for _, p in ipairs(pool) do out[#out + 1] = {slot, p[1], p[2], p[6], p[3], p[7]} end
        end
        return rows(out)
    elseif sql:find("group_id,class_id FROM dc_skill_affix", 1, true) then
        local out = {}
        for group, classes in pairs(SKILL_GROUPS) do
            for class in pairs(classes) do out[#out + 1] = {group, class} end
        end
        return #out > 0 and rows(out) or nil
    elseif sql:find("FROM dc_skill_affix", 1, true) then
        return rows({{"skill_head", "", "skill_head"}})
    elseif sql:find("class_key FROM dc_class_map WHERE wow_class_id=", 1, true) then
        local key = CLASS_KEYS[tonumber(sql:match("wow_class_id=(%d+)"))]
        return key and rows({{key}}) or nil
    elseif sql:find("class_id FROM dc_class_map WHERE class_key=", 1, true) then
        local id = CLASS_IDS[sql:match("class_key='([^']*)'")]
        return id and rows({{id}}) or nil
    elseif sql:find("FROM dc_class_primary_stats", 1, true) then
        local stat = CLASS_STATS[sql:match("class='([^']*)'")]
        return stat and rows({{stat}}) or nil
    elseif sql:find("b.entry,b.d3_name", 1, true) then
        local out = {}
        for entry, b in pairs(BASES) do out[#out + 1] = {entry, b.name, b.slot, b.class, b.level, b.set, b.power, b.flavour, b.sell} end
        return rows(out)
    elseif sql:find("FROM dc_affix_metadata", 1, true) then return nil
    elseif sql:find("FROM dc_legendary_gem_item", 1, true) then return nil
    elseif sql:find("FROM dc_gem_item", 1, true) then
        return nil
    elseif sql:find("FROM dc_set_tooltip", 1, true) then
        return rows({{"hallowed", "Hallowed Protectors"}})
    elseif sql:find("FROM dc_set_bonus", 1, true) then
        return rows({{"hallowed", 2, "Attack Speed Increased by 10.0%"}})
    elseif sql:find("dc_legendary_power", 1, true) then return nil
    elseif sql:find("spellid_1=81203", 1, true) then return nil -- no shell templates here
    elseif sql:find("SELECT DISTINCT", 1, true) then
        return rows({{"hallowed", "Hallowed Hold", "head"}, {"hallowed", "Hallowed Barricade", "offhand"}})
    end
    error("Unexpected query: " .. sql)
end
local sent = {}
local player = {GetClass = function() return 1 end, IsInWorld = function() return true end,
    GetName = function() return "Tester" end, GetGUIDLow = function() return 9 end}

----------------------------------------------------------------------------------------------------
-- Phase A - the server's preview record
----------------------------------------------------------------------------------------------------
local serverHandlers
AIO = {AddAddon = function() return true end, AddHandlers = function(_, h) serverHandlers = h; return h end,
    Handle = function(_, channel, method, payload) sent[#sent + 1] = {channel = channel, method = method, payload = payload} end,
    AddOnInit = function() end}
WorldDBQuery = tooltipQueries
CharDBQuery = function(sql) error("no character query expected: " .. sql) end
RegisterPlayerEvent = function() end
-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
dofile(TOOLTIP_SOURCE)
assert(serverHandlers.Preview, "the server registers a Preview handler")

local function preview(id)
    local before = #sent
    serverHandlers.Preview(player, id)
    assert(#sent == before + 1, "recipe " .. id .. " must answer with a record")
    local reply = sent[#sent]
    assert(reply.channel == "DiablocraftTooltip" and reply.method == "PreviewResult")
    return reply.payload
end

local function fixedOf(record)
    local ids = {}
    for _, a in ipairs(record.affixes) do ids[#ids + 1] = a end
    return ids
end
local function byId(record, id)
    for _, a in ipairs(record.affixes) do if a.id == id then return a end end
end

-- Rare: nothing fixed, the full 4 + 2.
local rare = preview(9001)
assert(rare.preview and rare.entry == 200001 and rare.rarity == "rare")
assert(rare.randomPrimary == 4 and rare.randomSecondary == 2 and rare.randomCount == 6,
    "a Rare previews 4 + 2 random, got " .. rare.randomPrimary .. " + " .. rare.randomSecondary)
assert(#rare.affixes == 0, "a Rare has no fixed affixes")
assert(rare.level == 70, "Required Level comes from the catalogue, got " .. tostring(rare.level))
assert(rare.bound == nil and rare.unique == nil, "the preview promises no binding and no unique")

-- Legendary with one in-pool preset: the preset takes a slot out of the budget.
local legendary = preview(9002)
local ms = byId(legendary, "ms")
assert(ms and ms.name == "Movement Speed" and ms.percent and ms.fixed, "the Movement Speed preset is fixed")
assert(ms.min == 10 and ms.max == 12 and ms.kind == "primary", "the fixed affix carries the pool's range")
assert(ms.min2 == nil and ms.max2 == nil,
    "a single-part fixed affix has no second bracket (dc_affix_pool stores NULL, not 1/1), got "
    .. tostring(ms.min2) .. "/" .. tostring(ms.max2))
assert(legendary.randomPrimary == 3 and legendary.randomSecondary == 2 and legendary.randomCount == 5,
    "Board Walkers previews 3 + 2 random (6 - the one preset), got " .. legendary.randomPrimary .. " + " .. legendary.randomSecondary)
assert(byId(legendary, "custom") == nil, "a preset outside the pool is not promised")
assert(legendary.level == 70 and legendary.power == "Legendary power text")

-- Set with a sockets preset and a set block.
local set = preview(9003)
local sockets = byId(set, "sockets")
assert(sockets and sockets.kind == "socket" and sockets.min == 1 and sockets.max == 3,
    "the sockets preset is one socket line with the roller's range")
assert(set.randomPrimary == 3 and set.randomSecondary == 2 and set.randomCount == 5,
    "the sockets preset takes one primary slot")
assert(set.set and set.set.name == "Hallowed Protectors" and set.set.bonuses[1].text == "Attack Speed Increased by 10.0%",
    "the set block is the generated set data")
assert(set.level == 70 and set.bound == nil and set.unique == nil)

-- Short pool: the fill can never exceed what the pool holds.
local short = preview(9004)
assert(short.randomPrimary == 1 and short.randomSecondary == 0 and short.randomCount == 1,
    "a one-affix pool previews one property, got " .. short.randomPrimary .. " + " .. short.randomSecondary)

-- A missing tunable answers 0, exactly as Tunables::Get does, so the preview shows the bare
-- item the roller would really make.
tunables.full_roll_primary_affixes, tunables.full_roll_secondary_affixes = nil, nil
local bare = preview(9001)
assert(bare.randomCount == 0, "a missing budget tunable previews no random properties, got " .. tostring(bare.randomCount))
tunables.full_roll_primary_affixes, tunables.full_roll_secondary_affixes = 4, 2

-- A recipe the catalogue does not hold, and a caller without a live player, get no record.
local before = #sent
serverHandlers.Preview(player, 9999)
assert(#sent == before, "an unknown recipe answers nothing")
serverHandlers.Preview({GetClass = function() return 1 end, IsInWorld = function() return false end}, 9001)
assert(#sent == before, "a player not in world answers nothing")

-- The fourth catalogue rarity: the loot/magic_* budget, not full_roll_*.
local magic = preview(9005)
assert(magic.rarity == "magic" and magic.randomPrimary == 1 and magic.randomSecondary == 1 and magic.randomCount == 2,
    "a Magic preview uses the magic budget, got " .. magic.randomPrimary .. " + " .. magic.randomSecondary)

-- A preset in the SECONDARY pool takes a secondary slot.
local secondary = preview(9006)
local resall = byId(secondary, "resall")
assert(resall and resall.kind == "secondary" and resall.fixed, "the secondary preset is a secondary fixed affix")
assert(secondary.randomPrimary == 3 and secondary.randomSecondary == 1,
    "2 presets (1 secondary) leave 3 + 1, got " .. secondary.randomPrimary .. " + " .. secondary.randomSecondary)

-- A duplicate preset is taken once.
local duplicate = preview(9007)
assert(#duplicate.affixes == 1 and duplicate.affixes[1].id == "ms", "a repeated preset is taken once")
assert(duplicate.randomPrimary == 3 and duplicate.randomSecondary == 2, "and occupies one slot")

-- A shield: its required block line is fixed but OUTSIDE the budget.
local shield = preview(9008)
local ids = fixedOf(shield)
assert(#ids == 2 and ids[1].id == "blockamount" and ids[2].id == "ms",
    "the shield's block line comes first, then the preset")
assert(shield.randomPrimary == 3 and shield.randomSecondary == 2,
    "the block line does not consume a rolled slot, got " .. shield.randomPrimary .. " + " .. shield.randomSecondary)

-- A class-only item crafted by another class: dc_items.cpp AffixClass gives the skill group to the
-- ITEM's class (monk, no choices for skill_head), not the crafter's (barbarian, which has one).
local classOnly = preview(9009)
assert(#classOnly.affixes == 0 and classOnly.randomPrimary == 4 and classOnly.randomSecondary == 2,
    "a monk-only preset is not borrowed by a barbarian crafter, got " .. #classOnly.affixes .. " fixed, "
    .. classOnly.randomPrimary .. " + " .. classOnly.randomSecondary)

-- diablocraft-wtxig: a preset its slot's pool has no row for comes from the item's own sheet range
-- (dc_item_preset_range), the mirror of PlanRoll's itemPresets fallback; one the pool does hold
-- still comes from the pool.
local sheet = preview(9011)
local chd = byId(sheet, "chd")
assert(chd and chd.fixed and chd.kind == "primary" and chd.min == 26 and chd.max == 50,
    "the item's own preset row is fixed with its sheet range, got " .. tostring(chd and chd.min))
local poolIas = byId(sheet, "ias")
assert(poolIas and poolIas.fixed, "a preset the pool does hold still comes from the pool")
assert(sheet.randomPrimary == 2 and sheet.randomSecondary == 2,
    "two presets leave 2 primary slots and the secondaries untouched, got "
    .. sheet.randomPrimary .. " + " .. sheet.randomSecondary)

-- diablocraft-sxj2c: the sheet row is taken without the pool's eligibility gate, as PlanRoll takes
-- itemPresets: a block line on a helm is the item's own, not refused for a non-shield.
local helm = preview(9012)
local block = byId(helm, "block")
assert(block and block.fixed and block.kind == "secondary" and block.min == 11,
    "the helm's own block row is fixed though eligible() refuses block off a shield")
assert(helm.randomSecondary == 1, "the own secondary counts against the budget, got " .. helm.randomSecondary)

-- diablocraft-j0xsb: a Source, Mojo or Phylactery takes the pool's +X-Y Damage first and outside
-- the budget (PlanRoll's damageOffhand), with both brackets; a Quiver is never offered it.
-- diablocraft-7175z: nor is a caster offhand offered the Quiver's ias, so only vit and chc fill.
for _, id in ipairs({9013, 9014, 9015}) do
    local caster = preview(id)
    local damage = byId(caster, "wpnphy")
    assert(damage and damage.fixed and damage.min == 262 and damage.max == 328 and damage.min2 == 263 and damage.max2 == 394,
        "recipe " .. id .. ": the required +X-Y Damage is fixed with both brackets")
    assert(byId(caster, "ias") == nil, "recipe " .. id .. ": a caster offhand carries no quiver attack speed line")
    assert(#caster.affixes == 1 and caster.randomPrimary == 2 and caster.randomSecondary == 2,
        "recipe " .. id .. ": the damage line spends no rolled slot, vit and chc fill, got "
        .. #caster.affixes .. " fixed, " .. caster.randomPrimary .. " + " .. caster.randomSecondary)
end
-- diablocraft-7175z: a Quiver takes the pool's Attack Speed Increase first and outside the budget
-- (PlanRoll's speedQuiver), so its random primaries draw only vit and chc.
local quiver = preview(9016)
local speed = byId(quiver, "ias")
assert(byId(quiver, "wpnphy") == nil, "a quiver carries no offhand damage line")
assert(speed and speed.fixed and speed.min == 15 and speed.max == 15 and speed.percent == true,
    "a quiver's required Attack Speed Increase is fixed at the pool's range")
assert(#quiver.affixes == 1 and quiver.randomPrimary == 2 and quiver.randomSecondary == 2,
    "a quiver's attack speed spends no rolled slot, vit and chc fill, got "
    .. #quiver.affixes .. " fixed, " .. quiver.randomPrimary .. " + " .. quiver.randomSecondary)

-- diablocraft-bi52c: a class item type's own pool lines. The preview reads the pool the way PoolFor does (the slot's rows,
-- then the type's own), so the Ritual Mace's two presets, which only its own pool holds, are listed as its fixed lines, and
-- the Totem, built like a Source, carries the required damage line and draws its random lines from its own four as well.
local mace = preview(9017)
local cold, lightning = byId(mace, "dmgcol"), byId(mace, "dmglit")
assert(cold and cold.fixed and cold.min == 10 and cold.max == 15 and cold.percent == true
    and lightning and lightning.fixed and lightning.min == 10 and lightning.max == 15,
    "the Ritual Mace's own pool lines are listed as its fixed lines")
assert(#mace.affixes == 2 and mace.randomPrimary == 2 and mace.randomSecondary == 2,
    "the two own lines take two of the four primary slots, got " .. #mace.affixes .. " fixed, " .. mace.randomPrimary .. " + " .. mace.randomSecondary)
local totem = preview(9018)
local totemDamage = byId(totem, "wpnphy")
assert(totemDamage and totemDamage.fixed and totemDamage.min == 262 and totemDamage.max == 328 and totemDamage.min2 == 263 and totemDamage.max2 == 394,
    "a Totem carries the offhand pool's required +X-Y Damage, as a Source does")
assert(byId(totem, "ias") == nil, "a Totem carries no quiver attack speed line")
assert(#totem.affixes == 1 and totem.randomPrimary == 4 and totem.randomSecondary == 2,
    "the Totem's four own lines fill the primaries (vit and chc alone would leave 2), got "
    .. #totem.affixes .. " fixed, " .. totem.randomPrimary .. " + " .. totem.randomSecondary)

-- Machine-readable fixture spec for test_blacksmith_tooltips.py, which compiles the module's own
-- PlanRoll: the eligible pools, presets, shield flag, budget and skill groups the preview works
-- from, plus what it decided, so the real C++ planner can be run over the very same input.
local PREVIEW_BLOCK = {baseblock = true, block = true, blockamount = true, blockamountdelta = true}
local PREVIEW_SHIELD = {Shield = true, ["Crusader Shield"] = true}
local PREVIEW_DAMAGE_OFFHAND = {Source = true, Mojo = true, Phylactery = true, Totem = true}
local function bracketOf(rarity)
    return (rarity == "legendary" or rarity == "set" or rarity == "ethereal") and "legendary" or "rare"
end
local function spec(name, id)
    local r = RECIPES[id]
    local b = BASES[r.entry]
    local shield = PREVIEW_SHIELD[b.type] == true
    local damageOffhand = PREVIEW_DAMAGE_OFFHAND[b.type] == true
    local speedQuiver = b.type == "Quiver"
    local affixClass = (b.designated ~= "") and CLASS_IDS[b.designated] or CLASS_IDS[CLASS_KEYS[1]]
    -- PoolFor: the slot's rows, then the rows of the base's own type.
    local pool = {}
    for _, key in ipairs({b.slot, b.slot .. ":" .. b.type}) do
        for _, p in ipairs(POOLS[key .. " " .. bracketOf(r.rarity)] or {}) do pool[#pool + 1] = p end
    end
    local primary, secondaryRows, skills = {}, {}, {}
    for _, p in ipairs(pool) do
        local pid, kind, min, max, percent = p[1], p[3], p[4], p[5], p[6]
        -- StageRoll's pool filter: block lines off a non-shield, the offhand wpnphy off all but the three,
        -- the offhand ias off all but a quiver.
        if not (PREVIEW_BLOCK[pid] and not shield) and not (b.slot == "offhand" and pid == "wpnphy" and not damageOffhand)
                and not (b.slot == "offhand" and pid == "ias" and not speedQuiver) then
            local group = SKILL_GROUPS[pid]
            if not (group and not group[affixClass]) then
                if group then skills[#skills + 1] = pid end
                -- G1: the trailing field is the pool row's weapon_class, so the compiled planner
                -- sees the same exclusive group the mirror does.
                local row = string.format("%s:%s:%g:%g:%d:%s", pid, kind, min, max, percent, p[10] or "")
                if kind == "secondary" then secondaryRows[#secondaryRows + 1] = row
                else primary[#primary + 1] = row end
            end
        end
    end
    local counts
    if r.rarity == "magic" then
        counts = string.format("%g:%g", tunables.magic_primary_affixes or 0, tunables.magic_secondary_affixes or 0)
    else
        counts = string.format("%g:%g", tunables.full_roll_primary_affixes or 0, tunables.full_roll_secondary_affixes or 0)
    end
    -- diablocraft-wtxig: the item's own sheet rows, so the compiled planner gets the same
    -- itemPresets the preview read them from.
    local ownRows = {}
    local ownPool = ITEM_PRESETS[r.entry] and ITEM_PRESETS[r.entry][bracketOf(r.rarity)]
    for _, p in ipairs(ownPool or {}) do
        ownRows[#ownRows + 1] = string.format("%s:%s:%g:%g:%d", p[1], p[3], p[4], p[5], p[6])
    end
    local record = preview(id)
    local fixedIds = {}
    for _, a in ipairs(record.affixes) do fixedIds[#fixedIds + 1] = a.id end
    print(string.format(
        "FIXTURE %s rarity=%s presets=%s shield=%d offhand=%d quiver=%d counts=%s skills=%s primary=%s secondary=%s own=%s fixed=%s random=%d:%d",
        name, r.rarity, b.presets, shield and 1 or 0, damageOffhand and 1 or 0, speedQuiver and 1 or 0, counts, table.concat(skills, "|"),
        table.concat(primary, "|"), table.concat(secondaryRows, "|"), table.concat(ownRows, "|"),
        table.concat(fixedIds, "|"), record.randomPrimary, record.randomSecondary))
end
for _, fixture in ipairs({{"rare", 9001}, {"legendary", 9002}, {"set", 9003}, {"short", 9004}, {"magic", 9005},
    {"secondary", 9006}, {"duplicate", 9007}, {"shield", 9008}, {"classonly", 9009}, {"multi", 9010}, {"sheet", 9011},
    {"sheethelm", 9012}, {"mojo", 9013}, {"source", 9014}, {"phylactery", 9015}, {"quiver", 9016},
    {"ritualmace", 9017}, {"totem", 9018}}) do
    spec(fixture[1], fixture[2])
end

----------------------------------------------------------------------------------------------------
-- Phase B - the shipped tooltip renders it
----------------------------------------------------------------------------------------------------
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024, 768)
local clientHandlers
local owner = {dcRecipeId = 9002}
GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
local requests = {}
AIO = {AddAddon = function() return false end, AddHandlers = function(_, h) clientHandlers = h; return h end,
    Handle = function(channel, method, id) requests[#requests + 1] = {channel = channel, method = method, id = id} end}
ITEM_SOCKETABLE = "<Shift Right Click to Socket>"
DEFAULT_CHAT_FRAME = {AddMessage = function() end}
unpack = unpack or table.unpack
dofile(TOOLTIP_SOURCE)
assert(clientHandlers.PreviewResult and DCShowRecipePreview, "the client registers the preview path")

-- Uncached hover: the client asks the server once, and draws nothing itself.
local recipe = {id = 9002, entry = 200002}
owner.dcRecipeId = 9002
DCShowRecipePreview(GameTooltip, recipe)
assert(#requests == 1 and requests[1].method == "Preview" and requests[1].id == 9002,
    "an uncached recipe asks the server for its preview")
assert(#GameTooltip.lines == 0, "the client never draws a preview it was not sent")

-- The reply draws the record through the same decorate() a rolled item uses.
clientHandlers.PreviewResult(nil, legendary)
GameTooltip.lines = {}
clientHandlers.PreviewResult(nil, legendary)   -- a second reply draws again, forced
local lines = GameTooltip.lines
local function index(fragment)
    for n, line in ipairs(lines) do if line:find(fragment, 1, true) then return n end end
    error("Missing tooltip line: " .. fragment .. "\n" .. table.concat(lines, "\n"))
end
local all = table.concat(lines, "\n")
assert(index("+[10 - 12]% Movement Speed"), "D3's range form, not a rolled value")
assert(index("+5 Random Magic Properties"), "the random property count")
assert(index("Required Level 70"), "the catalogue's required level")
assert(not all:find("Account Bound", 1, true), "G5: no account binding line")
assert(not all:find("Unique Equipped", 1, true), "G4: no unique-equipped line")
assert(not all:find("Shift Right Click", 1, true), "a preview is not socketable yet")
assert(not all:find("(preset)", 1, true), "a fixed affix wears no '(preset)' tag (diablocraft-n12ju: none does, on any item)")

-- G1: a weapon's two-part elemental roll renders D3's bracket form on a fixed affix, the way
-- Demon Claw (Fire) and Hallowed Hold (Holy) show it: +[981 - 1199]-[1175 - 1490] Cold Damage.
-- The 'multi' base authors three elements; the exclusive group means only the first is shown.
local multi = preview(9010)
local wpn = byId(multi, "wpncol")
assert(wpn and wpn.min2 == 1175 and wpn.max2 == 1490,
    "a weapon's real second bracket survives the NULL test, got " .. tostring(wpn and wpn.min2) .. "/" .. tostring(wpn and wpn.max2))
owner.dcRecipeId = 9010        -- the client draws only the record its owner asked for
GameTooltip.lines = {}
clientHandlers.PreviewResult(nil, multi)
local multiLines = table.concat(GameTooltip.lines, "\n")
assert(multiLines:find("+[981 - 1199]-[1175 - 1490] Cold Damage", 1, true),
    "the two-part preview form:\n" .. multiLines)
assert(not multiLines:find("Fire Damage", 1, true) and not multiLines:find("Lightning Damage", 1, true),
    "only the first authored element is taken:\n" .. multiLines)

-- Cached hover: the client draws it without asking again.
local requestsBefore = #requests
owner.dcRecipeId = 9002
assert(DCShowRecipePreview(GameTooltip, recipe) == true and #requests == requestsBefore,
    "a cached preview is drawn without another request")

-- The Set record: set block, socket range and no binding.
local setRecipe = {id = 9003, entry = 200003}
owner.dcRecipeId = 9003
clientHandlers.PreviewResult(nil, set)
GameTooltip.lines = {}
clientHandlers.PreviewResult(nil, set)
lines = GameTooltip.lines
all = table.concat(lines, "\n")
assert(all:find("Hallowed Protectors (0/2)", 1, true), "the set block is drawn")
assert(all:find("Hallowed Barricade", 1, true), "the set's pieces are drawn")
assert(all:find("Attack Speed Increased by 10.0%", 1, true), "the set bonus is drawn")
assert(all:find("Set bonuses are inactive.", 1, true), "the set-bonus caveat is kept")
assert(all:find("[1 - 3]", 1, true), "the socket count shows the roller's range")
assert(not all:find("Account Bound", 1, true) and not all:find("Unique Equipped", 1, true))

-- A late reply for a recipe the cursor has left must not repaint the tooltip.
GameTooltip.lines = {}
owner.dcRecipeId = 111
clientHandlers.PreviewResult(nil, rare)
assert(#GameTooltip.lines == 0, "a reply for a recipe that is no longer hovered draws nothing")

-- The Blacksmith's hover hands the recipe over and the old sentence is gone.
local blacksmith = io.open(BLACKSMITH_SOURCE):read("*a")
assert(blacksmith:find("DCShowRecipePreview", 1, true), "the Blacksmith asks the tooltip for a preview")
assert(not blacksmith:find("randomly rolled properties", 1, true),
    "the old 'Creates the selected item with randomly rolled properties.' sentence is gone")

print("PASS Blacksmith recipe previews: server record (fixed affixes, D3 ranges, +N from the "
    .. "roller's budget, catalogue level, cap, missing tunable) and client render (D3 form, +N, "
    .. "set block, socket range, no binding, no unique, no old sentence)")
