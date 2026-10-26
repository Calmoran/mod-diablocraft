-- Run from the repo root: lua mod-diablocraft/scripts/tests/ui/taeguk_hover_lines.lua <aura id> <DCBUFFVAL body>
-- Driver of test_taeguk_hover.py: the addon's lines (dc_buff_values.lua, DC_BUFF_LUA to point it at a copy) under
-- the buff the player hovers once the server's record has arrived. Prints one line per row.
local SOURCE=os.getenv("DC_BUFF_LUA") or "mod-diablocraft/lua/aio/dc_buff_values.lua"
local aura,body=tonumber(arg[1]),arg[2]

local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
function UnitName() return "Tester" end
function GetRealmName() return "Torment" end
function UnitIsUnit(a,b) return a==b end
function UnitBuff(unit,index)
    if unit=="player" and index==1 then return "Aura","",nil,10,nil,10,100,unit,false,false,aura end
end
UnitAura,UnitDebuff=UnitBuff,function() end
AIO={AddAddon=function() return false end}
Diablocraft=nil
dofile(SOURCE)

DCBuffValues.OnMessage("DCBUFFVAL",body,"WHISPER","Tester")
GameTooltip:ClearLines();GameTooltip:Hide()
GameTooltip:SetUnitBuff("player",1)
for _,line in ipairs(GameTooltip.lines or {}) do print(line) end
