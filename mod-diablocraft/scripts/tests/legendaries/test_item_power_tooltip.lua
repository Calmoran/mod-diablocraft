-- Legendary powers P0 (diablocraft-w6ged): the tooltip reads an item power as active only when the item is worn and
-- the power table has a row for it, and a set bonus as active only when the worn pieces reach its level and the
-- table has a row for it. A power or bonus with no row stays inactive; a broken piece counts for nothing.
-- Per-item rolls (diablocraft-v62ba): a dc_item_affix row of kind 'power' is no affix line; its number goes into the
-- power text beside the range. Fixture rows: legendary_powers.csv has no item-owned row that rolls yet.
-- luacheck: ignore 111 112 121 122 212 213
local payload,init,clientHandlers
local function result(rows)
    if #rows==0 then return nil end
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        NextRow=function() index=index+1;return rows[index]~=nil end}
end
-- entry, name, slot, class, level, set_id, power, flavour, sell
local BASES={
    {100087,"Test Legs","legs","barbarian",70,"test","","",1},
    {100088,"Test Helm","head","barbarian",70,"test","","",1},
    {100089,"Sun Keeper","onehand","barbarian",70,"","Increases damage against elites by [15-30]%","",1},
    {100091,"Test Chest","torso","barbarian",70,"test","","",1},
    {100092,"Test Hands","hands","barbarian",70,"test","","",1},
    {100090,"Plain Legend","onehand","barbarian",70,"","A power nobody built.","",1},
    -- the generator writes a range into power_text as min–max (generate_crafting.py), no flavour
    {100093,"Test Mantle","shoulders","barbarian",70,"","While channeling, you deal 20–25% increased damage.","",1},
    -- Bottomless potions (diablocraft-87qlt): the Tower has a power row, Kulle-Aid has none
    {102201,"Bottomless Potion of the Tower","potion","",61,"","Increases Armor by 10–20% for 5 seconds.","",0},
    {102205,"Bottomless Potion of Kulle-Aid","potion","",61,"","Drinking Kulle-Aid allows you to burst through walls.","",0},
}
-- guid -> the item's stored power row (value, range_min, range_max); guid 96 has none
local POWER_ROWS={[95]={22,20,25},[97]={25,20,25},[98]={17,10,20}}
local QUALITY={[97]="primal"}
function WorldDBQuery(query)
    if query:find("spellid_1=81203",1,true) then return nil end -- no shell templates here
    if query:find("FROM dc_item_preset_range",1,true) or query:find("FROM dc_affix_metadata",1,true) then return nil end -- no preset-only lines here
    if query:find("FROM dc_affix_pool",1,true) then return result({{"legs","mainstat","Primary Attribute",0,"primary",1}})
    elseif query:find("FROM dc_skill_affix",1,true) then return nil
    elseif query:find("b.entry,b.d3_name",1,true) then return result(BASES)
    elseif query:find("FROM dc_legendary_gem_item",1,true) then return nil
    elseif query:find("FROM dc_gem_item",1,true) then return nil
    elseif query:find("FROM dc_set_tooltip",1,true) then return result({{"test","Test Set"}})
    elseif query:find("FROM dc_set_bonus",1,true) then return result({{"test",2,"Two pieces"},{"test",4,"Four pieces"}})
    -- the item power table: Sun Keeper has a row, Plain Legend has none; the set has its 2-piece row only
    elseif query:find("JOIN dc_legendary_power",1,true) then return result({{100089},{102201}})
    elseif query:find("FROM dc_legendary_power",1,true) then return result({{"Test Set",2}})
    elseif query:find("SELECT DISTINCT",1,true) then return result({{"test","Test Legs"},{"test","Test Helm"},{"test","Test Chest"},{"test","Test Hands"}})
    end
    error(query)
end
local function guidsIn(query)
    local out={}
    for guid in (query:match("IN %(([%d,]+)%)") or ""):gmatch("%d+") do out[#out+1]=tonumber(guid) end
    return out
end
function CharDBQuery(query)
    local rows={}
    if query:find("FROM dc_item_instance",1,true) then
        for _,guid in ipairs(guidsIn(query)) do rows[#rows+1]={guid,"legendary",0,QUALITY[guid] or "normal"} end
        return result(rows)
    end
    assert(query:find("FROM dc_item_affix",1,true))
    for _,guid in ipairs(guidsIn(query)) do
        rows[#rows+1]={guid,1,"mainstat",432,416,500,"preset",0,-1,0}
        local roll=POWER_ROWS[guid]
        if roll then rows[#rows+1]={guid,2,"power:Rend:damage_increase_pct",roll[1],roll[2],roll[3],"power",0,-1,0} end
    end
    return result(rows)
end
function RegisterPlayerEvent() end
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) return h end,
    AddOnInit=function(callback) init=callback end}
dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")

local function item(entry,guid,state)
    return {GetEntry=function() return entry end,GetGUIDLow=function() return guid end,
        GetUInt32Value=function(_,field) return field==0x3C and 60 or 100 end,
        IsEquipped=function() return state.worn end,IsBroken=function() return state.broken or false end}
end
-- `layout`: [bag][slot] = item
local function load(layout)
    init({Add=function(_,_,_,data) payload=data end},{GetItemByPos=function(_,bag,slot) return layout[bag] and layout[bag][slot] end})
end

local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024,768)
local ownerSlot=6
local testOwner={GetName=function() return "CharacterLegsSlot" end,GetID=function() return ownerSlot+1 end}
AIO={AddAddon=function() return false end,AddHandlers=function(_,h) clientHandlers=h;return h end}
GameTooltipTextLeft2={GetText=function() return "Legs" end}
GameTooltipTextLeft3={GetText=function() return "Requires Level 70" end}
unpack=unpack or table.unpack
SlashCmdList={}
DEFAULT_CHAT_FRAME={AddMessage=function() end}
dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")
local hooks=GameTooltip.scripts
local function show(slot)
    ownerSlot=slot or 6
    clientHandlers.Set(nil,payload)
    GameTooltip:ClearLines()
    hooks.OnTooltipCleared(GameTooltip)
    GameTooltip.owner=testOwner
    GameTooltip.lines={"","",""}
    hooks.OnTooltipSetItem(GameTooltip)
    return GameTooltip.lines,GameTooltip.lineColors
end
local function find(lines,fragment)
    for n,line in ipairs(lines) do if line:find(fragment,1,true) then return n end end
end
local ORANGE,GREEN={1,.5,0},{0,1,0}
local function colourIs(colours,n,want) local c=colours[n];return c and c[1]==want[1] and c[2]==want[2] and c[3]==want[3] end

-- 1. Both set pieces worn: the 2-piece bonus has a row and its level is reached (orange); the 4-piece has no row (grey).
local legs,helm={worn=true},{worn=true}
load({[255]={[6]=item(100087,87,legs),[4]=item(100088,88,helm)}})
local lines,colours=show()
assert(find(lines,"Test Set (2/4)"),"the worn count, got: "..table.concat(lines,"\n"))
local two,four=find(lines,"(2) Set: Two pieces"),find(lines,"(4) Set: Four pieces")
assert(two and colourIs(colours,two,ORANGE),"the reached 2-piece bonus with a power is active (orange)")
assert(four and not colourIs(colours,four,ORANGE),"the 4-piece bonus has no row in the table: it stays inactive")
assert(not find(lines,"Set bonuses are inactive."),"a set with an active bonus does not say they are all inactive")

-- 1b. Four pieces worn reach the 4-piece level, but it has no row in the table: still inactive.
local chest,hands={worn=true},{worn=true}
load({[255]={[6]=item(100087,87,legs),[4]=item(100088,88,helm),[5]=item(100091,93,chest),[9]=item(100092,94,hands)}})
lines,colours=show()
assert(find(lines,"Test Set (4/4)"),"got: "..table.concat(lines,"\n"))
assert(colourIs(colours,find(lines,"(2) Set: Two pieces"),ORANGE))
assert(not colourIs(colours,find(lines,"(4) Set: Four pieces"),ORANGE),"a reached level with no row in the table is not active")

-- 2. One piece worn: the level is not reached, so every bonus is inactive.
load({[255]={[6]=item(100087,87,legs)}})
lines,colours=show()
assert(find(lines,"Test Set (1/4)"))
assert(not colourIs(colours,find(lines,"(2) Set: Two pieces"),ORANGE),"one piece does not reach the 2-piece level")
assert(find(lines,"Set bonuses are inactive."),"and the set says so")

-- 3. A broken piece is worn but counts for nothing (the same rule as Items::Apply).
helm.broken=true
load({[255]={[6]=item(100087,87,legs),[4]=item(100088,88,helm)}})
lines,colours=show()
assert(find(lines,"Test Set (1/4)"),"a broken piece is not counted, got: "..table.concat(lines,"\n"))
assert(not colourIs(colours,find(lines,"(2) Set: Two pieces"),ORANGE))
helm.broken=false

-- 4. An item power: active when the item is worn and has a row; inactive in the bag, with no row, or broken.
local sun,plain,bagged={worn=true},{worn=true},{worn=false}
load({[255]={[15]=item(100089,89,sun),[16]=item(100090,90,plain),[23]=item(100089,91,bagged)}})
assert(payload[255][15].active==true and payload[255][16].active==nil and payload[0][1].active==nil,
    "the record says: worn with a row is active, no row or not worn is not")
lines,colours=show(15)
local active=find(lines,"Legendary power is active.")
assert(active and colourIs(colours,active,GREEN),"a worn power with a row reads active, got: "..table.concat(lines,"\n"))
assert(find(lines,"Increases damage against elites by [15-30]%")<active,"the active line is under the power")
lines=show(16)
assert(find(lines,"Legendary power is inactive.") and not find(lines,"Legendary power is active."),
    "a worn power with no row in the table stays inactive")
sun.broken=true
load({[255]={[15]=item(100089,89,sun)}})
assert(payload[255][15].active==nil,"a broken item's power is not active")

-- 5. A legendary power's per-item roll: the number in the power text with the range beside it, never an affix line.
load({[255]={[2]=item(100093,95,{worn=true}),[3]=item(100093,96,{worn=true}),[4]=item(100093,97,{worn=true})}})
local mantle=payload[255][2]
assert(#mantle.affixes==1 and mantle.affixes[1].id=="mainstat","the power row is not in the affix list")
assert(mantle.rolledPower=="While channeling, you deal 22% [20%–25%] increased damage.","got: "..tostring(mantle.rolledPower))
assert(mantle.power=="While channeling, you deal 20–25% increased damage.","power keeps the description text the native line is matched by")
assert(payload[255][3].rolledPower==nil,"an item with no stored roll shows the text as today")
assert(payload[255][4].rolledPower=="While channeling, you deal 25% [20%–25%] increased damage.","a Primal shows its stored max")
lines=show(2)
assert(find(lines,"you deal 22% [20%–25%] increased damage."),"the tooltip draws the rolled text, got: "..table.concat(lines,"\n"))
assert(not find(lines,"you deal 20–25%"),"and not the bare range")
assert(not find(lines,"power:"),"no affix line for the power row")
lines=show(3)
assert(find(lines,"you deal 20–25% increased damage."),"no stored roll: the text as today")

-- 6. A Bottomless potion (diablocraft-87qlt): its rolled number in the power text; a built potion's power works on its
-- drink, never worn, so its tooltip has no active line; a potion whose power is not built says it is inactive.
load({[255]={[17]=item(102201,98,{worn=false}),[18]=item(102205,99,{worn=false})}})
local tower,kulle=payload[255][17],payload[255][18]
assert(tower.drunk==true and kulle.drunk==nil,"the record says which potion's power is built")
assert(tower.rolledPower=="Increases Armor by 17% [10%–20%] for 5 seconds.","got: "..tostring(tower.rolledPower))
lines=show(17)
assert(find(lines,"Increases Armor by 17% [10%–20%] for 5 seconds."),"the potion's roll, got: "..table.concat(lines,"\n"))
assert(not find(lines,"Legendary power is"),"a built potion has no active or inactive line")
lines=show(18)
assert(find(lines,"Legendary power is inactive."),"a potion whose power is not built stays inactive")
print("item power tooltip OK")
