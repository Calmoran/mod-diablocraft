-- luacheck: ignore 111 112 121 122 212 213
-- diablocraft-n12ju (extends ipc7, which dropped it for a Primal only): no item's lines carry "(preset)",
-- normal, Ancient or Primal; a fixed stat reads like a rolled one (ruling 2026-10-14).
-- Runs the real dc_tooltip.lua loader over the same stored preset row on three items, then the real
-- formatter (DCAFFIXLINE, the one the Mystic window also words its lines with) over the loaded records.
local payload,init
local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        IsNull=function(_,column) return rows[index][column+1]==nil end,NextRow=function() index=index+1;return rows[index]~=nil end}
end
function WorldDBQuery(query)
    if query:find("FROM dc_affix_pool",1,true) then
        return result({{"legs","mainstat","Primary Attribute",0,"primary",1},{"legs","wpnfir","Fire Damage",0,"primary",10}})
    elseif query:find("b.entry,b.d3_name",1,true) then return result({{100087,"Test Legs","legs","barbarian",70,"test","","Flavour",12345}})
    end
end
function CharDBQuery(query)
    if query:find("FROM dc_item_instance",1,true) then
        return result({{1,"legendary",0,"normal"},{2,"legendary",0,"ancient"},{3,"legendary",0,"primal"}})
    end
    assert(query:find("FROM dc_item_affix",1,true))
    local rows={}
    for guid=1,3 do
        rows[#rows+1]={guid,1,"mainstat",432,416,500,"preset",0,-1,0}
        rows[#rows+1]={guid,2,"wpnfir",981,981,1199,"preset",0,-1,0,1490,1175,1490}
    end
    return result(rows)
end
function RegisterPlayerEvent() end
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) return h end,
    AddOnInit=function(callback) init=callback end}
dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")
local function item(guid) return {GetEntry=function() return 100087 end,GetGUIDLow=function() return guid end,
    GetUInt32Value=function() return 100 end} end
init({Add=function(_,_,_,data) payload=data end},{GetItemByPos=function(_,bag,slot)
    if bag==255 and slot>=6 and slot<=8 then return item(slot-5) end
end})
-- The client half of the same file publishes the formatter.
local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024,768)
AIO={AddAddon=function() return false end,AddHandlers=function(_,h) return h end}
GameTooltipTextLeft2={GetText=function() return "Legs" end}
GameTooltipTextLeft3={GetText=function() return "Requires Level 70" end}
unpack=unpack or table.unpack
SlashCmdList={}
ITEM_SOCKETABLE="<Shift Right Click to Socket> (global)"
DEFAULT_CHAT_FRAME={AddMessage=function() end}
dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")
local function lines(slot)
    local out={}
    for _,affix in ipairs(payload[255][slot].affixes) do out[affix.id]=DCAFFIXLINE(affix) end
    return out
end
for _,slot in ipairs({6,7,8}) do
    local line=lines(slot)
    for _,id in ipairs({"mainstat","wpnfir"}) do
        assert(line[id],"item "..slot.." has its "..id.." line")
        assert(not line[id]:find("(preset)",1,true),
            "item "..slot.." ("..({[6]="normal",[7]="ancient",[8]="primal"})[slot].."): "..line[id])
    end
end
print("PASS: no item's lines have (preset): normal, Ancient and Primal read like rolled lines")
