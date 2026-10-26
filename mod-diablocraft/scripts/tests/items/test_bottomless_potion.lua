-- diablocraft-potion-regeneration: the tooltip of a legendary potion. It has no
-- dc_item_instance row (nothing rolls it), so records() used to answer nothing for
-- it and the client drew its own native tooltip, with no "Legendary power is
-- inactive." line. Run as: lua5.1 mod-diablocraft/scripts/tests/items/test_bottomless_potion.lua
-- luacheck: ignore 111 112 121 122 212 213
local push
local POWER="Restores an additional 75000–100000 Life over 5 seconds."
local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        NextRow=function() index=index+1;return rows[index]~=nil end}
end
function WorldDBQuery(query)
    if query:find("b.entry,b.d3_name",1,true) then
        return result({
            {102200,"Bottomless Potion of Regeneration","potion","",61,"",POWER,"Healing combined with more healing!",0},
            {118,"Potion slot test fixture","potion","",0,"","","",0}})
    end
    return nil
end
function CharDBQuery(query)
    -- No dc_item_instance, dc_item_unidentified or dc_item_affix row for a potion.
    return nil
end
function RegisterPlayerEvent() end
local handlers
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) handlers=h;return h end,
    AddOnInit=function() end,
    Handle=function(_,channel,name,payload) push={channel=channel,name=name,payload=payload} end}
-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
dofile("mod-diablocraft/lua/aio/dc_tooltip.lua")

local function item(entry,guid)
    return {GetEntry=function() return entry end,GetGUIDLow=function() return guid end,
        GetUInt32Value=function() return 0 end}
end
local holder={GetGUIDLow=function() return 9 end,GetSelection=function() return nil end,
    GetItemByPos=function(_,bag,slot)
        if bag==255 and slot==44 then return item(102200,501) end
        if bag==255 and slot==45 then return item(118,502) end
    end}
handlers.Context(holder,"bank")
local legendary=push.payload.items[-1] and push.payload.items[-1][6]
assert(legendary,"the legendary potion gets a tooltip record although it has no dc_item_instance row")
assert(legendary.rarity=="legendary","it is drawn as a legendary")
assert(legendary.power==POWER,"the power line, range written out")
assert(legendary.flavour:find("more healing",1,true),"the flavour text")
assert(legendary.level==61 and legendary.maxDurability==0 and #legendary.affixes==0,"required level, no durability, no affixes")
assert(not (push.payload.items[-1] and push.payload.items[-1][7]),
    "a potion base with no power (the stock test fixture) keeps the client's own tooltip")
print("PASS test_bottomless_potion.lua")
