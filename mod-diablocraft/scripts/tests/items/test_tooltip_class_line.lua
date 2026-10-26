-- diablocraft-9rhz: the client's own "Classes: X" line on an item with AllowableClass set survives the
-- tooltip hooks (dc_tooltip.lua capture/decorate), once, in the colour the client drew it. The client draws
-- the line from item_template.AllowableClass in C++, in red when the viewer is not that class; the addon
-- clears the tooltip and redraws, so a filter that dropped it would hide the lock from the player.
-- luacheck: ignore 111 112 121 122 212 213
local payload,init,clientHandlers
local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        NextRow=function() index=index+1;return rows[index]~=nil end}
end
function WorldDBQuery(query)
    if query:find("spellid_1=81203",1,true) then return nil end -- no shell templates here
    if query:find("FROM dc_item_preset_range",1,true) or query:find("FROM dc_affix_metadata",1,true) then return nil end -- no preset-only lines here
    if query:find("FROM dc_affix_pool",1,true) then return result({{"legs","mainstat","Primary Attribute",0,"primary",1}})
    elseif query:find("FROM dc_skill_affix",1,true) then return result({{"skill_barbarian_bash","Bash Damage","skill_legs"}})
    elseif query:find("b.entry,b.d3_name",1,true) then return result({{100087,"Test Legs","legs","wizard",70,"","","Flavour",12345}})
    elseif query:find("FROM dc_legendary_gem_item",1,true) then return nil
    elseif query:find("FROM dc_gem_item",1,true) then return result({{103000,"Flawless Square Ruby","other","str",100}})
    elseif query:find("FROM dc_set_tooltip",1,true) then return result({{"test","Test Set"}})
    elseif query:find("FROM dc_set_bonus",1,true) then return result({{"test",2,"Test bonus"}})
    elseif query:find("dc_legendary_power",1,true) then return nil
    elseif query:find("SELECT DISTINCT",1,true) then return result({{"test","Test Legs"}})
    end
    error(query)
end
function CharDBQuery(query)
    if query:find("FROM dc_item_instance",1,true) then return result({{87,"rare",0}}) end
    assert(query:find("FROM dc_item_affix",1,true))
    return result({{87,1,"mainstat",432,416,500,"preset",0,-1,0}})
end
function RegisterPlayerEvent() end
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) return h end,
    AddOnInit=function(callback) init=callback end}
dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")
init({Add=function(_,_,_,data) payload=data end},{GetItemByPos=function(_,bag,slot)
    if bag==255 and slot==6 then return {GetEntry=function() return 100087 end,GetGUIDLow=function() return 87 end,
        GetUInt32Value=function(_,field) return field==0x3C and 60 or 100 end} end
end})
assert(payload[255][6],"the item is in the payload")

-- --- client half -----------------------------------------------------------
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024, 768)
local testOwner={GetName=function() return "CharacterLegsSlot" end,GetID=function() return 7 end}
AIO={AddAddon=function() return false end,AddHandlers=function(_,h) clientHandlers=h;return h end}
-- The client's native lines for a Wizard-only item viewed by a Barbarian: the class line is red.
local RED={1,.125,.125}
local native={
    {left="Legs"},
    {left="Classes: Wizard",colour=RED},
    {left="Requires Level 70"},
}
-- NumLines counts the title as line 1; the native FontStrings below start at TextLeft2.
for i,line in ipairs(native) do
    _G["GameTooltipTextLeft"..(i+1)]={GetText=function() return line.left end,
        GetTextColor=function() local c=line.colour or {1,1,1};return c[1],c[2],c[3] end}
end
unpack=unpack or table.unpack
SlashCmdList={}
DEFAULT_CHAT_FRAME={AddMessage=function() end}
dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")
local hooks=GameTooltip.scripts
clientHandlers.Set(nil,payload)
GameTooltip.owner=testOwner
-- The client has already drawn its three native lines; NumLines is the line list's length.
GameTooltip.lines={}
for i=1,#native+1 do GameTooltip.lines[i]="" end
hooks.OnTooltipSetItem(GameTooltip)

local found,at
for n,line in ipairs(GameTooltip.lines) do
    if line=="Classes: Wizard" then
        assert(not found,"the class line is drawn once, got: "..table.concat(GameTooltip.lines,"\n"))
        found,at=true,n
    end
end
assert(found,"the native Classes line survives the tooltip hooks, got: "..table.concat(GameTooltip.lines,"\n"))
local style=GameTooltip.lineColors[at]
assert(style[1]==RED[1] and style[2]==RED[2] and style[3]==RED[3],
    "the line keeps the red the client drew it in, got "..tostring(style[1])..","..tostring(style[2])..","..tostring(style[3]))
assert(GameTooltip.lines[at-1]=="Legs","it stays right under the slot line, where the client put it, got line "..at)
print("class line OK")
