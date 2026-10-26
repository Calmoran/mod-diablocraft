-- diablocraft-ytzea: a rolled line whose code the item's slot pool does not hold reads by its name, not its bare code.
-- The roller takes such a fixed stat from the item's own dc_item_preset_range row (dc_items.cpp PlanRoll's
-- itemPresets), and a stat no pool holds has a dc_affix_metadata row; describe() named a line only from the slot's
-- pool, so Tal Rasha's Relentless Pursuit's attack speed read "+6% ias". Every table here is the committed render
-- (the generated pool, the preset sheet's migration, the metadata migration, the base item row), never a copy.
-- Run from the repo root: lua mod-diablocraft/scripts/tests/items/test_tooltip_preset_names.lua
-- luacheck: ignore 111 112 121 122 212 213
local UPDATES="mod-diablocraft/data/sql/db-world/updates/"
local function read(path)
    local file=assert(io.open(path,"r"),path);local text=file:read("*a");file:close();return text
end
-- The value tuples of every INSERT into one table (a render splits them in blocks of 100), each as a list of Lua
-- values: NULL is false, '' quotes unescaped.
local function tuples(path,name)
    local out,inside={},false
    for line in read(path):gmatch("[^\n]+") do
        if line:find("INSERT INTO `"..name.."`",1,true)==1 then inside=true
        elseif inside and line:sub(1,1)=="(" then
            local row,rest={},line:match("^%((.*)%)[,;]$")
            local i=1
            while i<=#rest do
                local c=rest:sub(i,i)
                if c=="'" then
                    local j,value=i+1,{}
                    while true do
                        local ch=rest:sub(j,j)
                        if ch=="'" and rest:sub(j+1,j+1)=="'" then value[#value+1]="'";j=j+2
                        elseif ch=="'" then break
                        else value[#value+1]=ch;j=j+1 end
                    end
                    row[#row+1]=table.concat(value);i=j+1
                elseif c=="," or c==" " then i=i+1
                else
                    local j=rest:find(",",i,true) or #rest+1
                    local raw=rest:sub(i,j-1)
                    row[#row+1]=raw~="NULL" and tonumber(raw) or false;i=j
                end
            end
            out[#out+1]=row
        else inside=false end
    end
    assert(#out>0,name.." in "..path)
    return out
end
local POOL=tuples("mod-diablocraft/data/generated/affix_pools.sql","dc_affix_pool")
local PRESETS=tuples(UPDATES.."items_0033_item_preset_ranges_sweep.sql","dc_item_preset_range")
local METADATA=tuples(UPDATES.."items_0034_affix_metadata_sweep.sql","dc_affix_metadata")
local BASES=tuples(UPDATES.."0002_dc_base_item.sql","dc_base_item")

local CHEST=100640
local base
for _,row in ipairs(BASES) do if row[1]==CHEST then base=row end end
assert(base and base[3]=="Tal Rasha's Relentless Pursuit" and base[4]=="torso","the base row is Tal Rasha's chest")
assert(base[13]:find("ias",1,true),"its preset list names ias: "..base[13])
local function poolHolds(slot,id)
    for _,row in ipairs(POOL) do if row[1]==slot and row[2]==id then return true end end
end
-- The two codes under test: one that only the chest's own preset row names, one that only the metadata names.
local own
for _,row in ipairs(PRESETS) do if row[1]==CHEST and row[2]=="ias" then own=row end end
assert(own,"the chest has its own ias row (jh08v)")
assert(not poolHolds("torso","ias"),"the torso pool does not hold ias, so only the item's own row can name it")
local meta
for _,row in ipairs(METADATA) do if row[1]=="maxmana" then meta=row end end
assert(meta,"maxmana has a metadata row (yjr87)")
assert(not poolHolds("torso","maxmana"),"the torso pool does not hold maxmana")
for _,row in ipairs(PRESETS) do
    assert(not (row[1]==CHEST and row[2]=="maxmana"),"the chest has no own maxmana row, so only the metadata can name it")
end

local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    -- ALE reads a NULL number as 0.
    local function number(_,column) return rows[index][column+1] or 0 end
    return {GetUInt32=number,GetInt32=number,GetDouble=number,GetString=value,
        IsNull=function(_,column) return rows[index][column+1]==false end,
        NextRow=function() index=index+1;return rows[index]~=nil end}
end
local function pick(list,map)
    local out={}
    for _,row in ipairs(list) do local r={};for i,col in ipairs(map) do r[i]=row[col] end;out[#out+1]=r end
    return result(out)
end
function WorldDBQuery(query)
    if query:find("spellid_1=81203",1,true) then return nil end -- no shell templates here
    if query:find("SELECT slot,affix_id,affix_name,is_percent,kind,display_order FROM dc_affix_pool",1,true) then
        return pick(POOL,{1,2,3,9,4,11})
    elseif query:find("SELECT entry,affix_id,affix_name,is_percent,kind,display_order FROM dc_item_preset_range",1,true) then
        return pick(PRESETS,{1,2,3,9,4,10})
    elseif query:find("SELECT affix_id,affix_name,is_percent,kind,display_order FROM dc_affix_metadata",1,true) then
        return pick(METADATA,{1,2,4,3,5})
    elseif query:find("FROM dc_skill_affix",1,true) then return nil
    elseif query:find("b.entry,b.d3_name",1,true) then
        return result({{CHEST,base[3],base[4],base[17],base[8],"","","",1}})
    elseif query:find("FROM dc_legendary_gem_item",1,true) then return nil
    elseif query:find("FROM dc_gem_item",1,true) then return nil
    elseif query:find("FROM dc_set_tooltip",1,true) then return nil
    elseif query:find("FROM dc_set_bonus",1,true) then return nil
    elseif query:find("dc_legendary_power",1,true) then return nil
    elseif query:find("SELECT DISTINCT",1,true) then return nil
    end
    error(query)
end
local GUID=640
function CharDBQuery(query)
    if query:find("FROM dc_item_instance",1,true) then return result({{GUID,"set",0,0,""}}) end
    assert(query:find("FROM dc_item_affix",1,true),query)
    -- item_guid,seq,affix_id,value,range_min,range_max,kind,rerolled,parent_seq,gem_entry,value2,range_min2,range_max2,legendary_rank
    return result({
        {GUID,1,"mainstat",450,416,500,"preset",0,-1,0,0,0,0,0},
        {GUID,2,"ias",6,own[5],own[6],"preset",0,-1,0,0,0,0,0},
        {GUID,3,"maxmana",130,120,150,"secondary",0,-1,0,0,0,0,0},
    })
end
function RegisterPlayerEvent() end
local payload,init
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) return h end,
    AddOnInit=function(callback) init=callback end}
dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")
init({Add=function(_,_,_,data) payload=data end},{GetItemByPos=function(_,bag,slot)
    if bag==255 and slot==4 then return {GetEntry=function() return CHEST end,GetGUIDLow=function() return GUID end,
        GetUInt32Value=function(_,field) return field==0x3C and 60 or 100 end} end
end})
local item=assert(payload and payload[255] and payload[255][4],"the chest is in the payload")
local lines={}
for _,affix in ipairs(item.affixes) do lines[affix.id]=affix end

local ias=assert(lines.ias,"the ias line is sent")
assert(ias.name==own[3],"the preset-only line reads the item's own row's name '"..own[3].."', got '"..tostring(ias.name).."'")
assert(ias.percent==(own[9]~=0),"it is a percent as the row says")
assert(ias.kind==own[4] and ias.order==own[10],"it takes the row's kind and order, got "..tostring(ias.kind).." "..tostring(ias.order))

local mana=assert(lines.maxmana,"the maxmana line is sent")
assert(mana.name==meta[2],"a code only the metadata names reads '"..meta[2].."', got '"..tostring(mana.name).."'")
assert(mana.percent==(meta[4]~=0) and mana.kind==meta[3] and mana.order==meta[5],"it takes the metadata's percent, kind and order")

-- The pool still answers first: the slot's own line is unchanged.
assert(lines.mainstat.name=="Intelligence","a Wizard chest's main stat reads Intelligence, got "..tostring(lines.mainstat.name))
print("preset names OK: ias -> "..ias.name..", maxmana -> "..mana.name)
