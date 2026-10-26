-- Shared item-grid reading for the Diablocraft screens (server half).
--
-- The stash's cell and rarity colours. There is no bag-cell reader any more:
-- the bags are ElvUI's, and the character sheet reads nothing here. Nothing here
-- decides anything: it reads rows and shapes them for the addon. Every rule
-- stays in C++.
--
-- Index encoding, identical on both sides and in C++ (dc_stash.cpp,
-- dc_inventory.cpp):
--   stash index = tab * 70 + slot
--   bag index   = container * 100 + slot, container 255 being the backpack
--   equip index = the WoW equipment slot, 0-18
--   -1          = "the first free slot on the other side"
--
-- The stash hands the addon its own indexes to echo back; a bag index is built
-- by the addon from a bag button's bagID/slotID (Diablocraft.lua bagIndex), the
-- one conversion between the client's numbering and this one.

DCGrid = DCGrid or {}

-- constant: the item rarity palette (05-items I4; item_template.Quality below).
local RARITY_COLOUR = {
    normal = "grey", magic = "blue", rare = "yellow", legendary = "orange", set = "green",
}
-- constant: item_template.Quality, for anything that is not one of our rolled items.
local QUALITY_COLOUR = {[0] = "grey", "grey", "green", "blue", "yellow", "orange", "orange", "orange"}
-- constant: display colours for the names above.
local COLOUR_CODE = {
    grey = "ff9d9d9d", green = "ff1eff00", blue = "ff0070dd", yellow = "ffffff00", orange = "ffff8000",
}

local function list(keys)
    local out = {}
    for key in pairs(keys) do out[#out + 1] = tostring(key) end
    return table.concat(out, ",")
end
DCGrid.List = list

-- Display names and colours for a set of item entries. Our rolled bases carry a
-- D3 name; anything else (gems, bags, quest items) keeps its template name.
function DCGrid.Describe(entries)
    local names, colours = {}, {}
    if not next(entries) then return names, colours end
    local ids = list(entries)
    local rows = WorldDBQuery("SELECT entry,name,Quality FROM item_template WHERE entry IN (" .. ids .. ")")
    if rows then repeat
        names[rows:GetUInt32(0)] = rows:GetString(1)
        colours[rows:GetUInt32(0)] = QUALITY_COLOUR[rows:GetUInt32(2)] or "grey"
    until not rows:NextRow() end
    rows = WorldDBQuery("SELECT entry,d3_name FROM dc_base_item WHERE entry IN (" .. ids .. ")")
    if rows then repeat
        local name = rows:GetString(1)
        if name and name ~= "" then names[rows:GetUInt32(0)] = name end
    until not rows:NextRow() end
    return names, colours
end

-- dc_item_instance.rarity wins over item_template.Quality for a rolled item.
function DCGrid.Rarities(guids)
    local out = {}
    if not next(guids) then return out end
    local rows = CharDBQuery("SELECT item_guid,rarity FROM dc_item_instance WHERE item_guid IN (" ..
        list(guids) .. ")")
    if rows then repeat out[rows:GetUInt32(0)] = rows:GetString(1) until not rows:NextRow() end
    -- A shell has no dc_item_instance row, so its
    -- rarity comes from dc_item_unidentified instead. The cell still draws in
    -- the real rarity's colour; only the NAME is withheld until identify.
    local shells = CharDBQuery("SELECT item_guid,rarity FROM dc_item_unidentified WHERE item_guid IN (" ..
        list(guids) .. ")")
    if shells then repeat
        local guid = shells:GetUInt32(0)
        if not out[guid] then out[guid] = shells:GetString(1) end
    until not shells:NextRow() end
    return out
end

-- `link` is only the base template a local hover hands the native tooltip so
-- its type, armour/damage and sell lines are drawn; it is entry-only on purpose
-- and names no instance. The SHARED link is built at link time by the
-- DiablocraftTooltip channel, which freezes the rows under a random code:
-- shift-clicking a cell asks for it.
function DCGrid.Cell(guid, entry, count, names, colours, rarity)
    local name = names[entry] or ("Item " .. entry)
    local colour = COLOUR_CODE[RARITY_COLOUR[rarity or ""] or colours[entry] or "grey"] or COLOUR_CODE.grey
    return {
        guid = guid, entry = entry, count = count, name = name, rarity = rarity or "",
        colour = RARITY_COLOUR[rarity or ""] or colours[entry] or "grey",
        link = "|c" .. colour .. "|Hitem:" .. entry .. ":0:0:0:0:0:0:0:0|h[" .. name .. "]|h|r",
    }
end
