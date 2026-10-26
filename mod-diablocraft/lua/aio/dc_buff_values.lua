-- dc_buff_values.lua - the addon line in a buff's tooltip.
-- Contract: docs/contracts/buff-values-messages.md (DCBUFFVAL; the server sends the values).
--
-- A buff's own record text stays the whole tooltip, as the client draws it; this file only adds a plain line under
-- it for a number the record cannot state (a gem's rank, a live amount), from the server's last V for that aura.
-- The values are totals as the server sent them: nothing here multiplies, rounds or works one out. Only the
-- player's own auras get a line (the server sends this character's values). The tooltip is stock, so the
-- line is an AddLine in the record text's colour, added on the three setters a buff's text arrives through.
-- Nothing here runs on the server.
-- luacheck: globals DCBuffValues UnitIsUnit UnitAura UnitBuff UnitDebuff
local AIO=AIO or require("AIO")
if AIO.AddAddon() then return end

local PREFIX="DCBUFFVAL"
DCBuffValues={}
local B=DCBuffValues

-- The aura's lines, one per value in the contract's order; "%s" is the value as sent. A value of 0 draws no line.
B.LINES={
    [83411]={"+%s%% Dodge"},                                -- Gogok of Swiftness
    [83412]={"+%s%% Dodge"},                                -- Gogok of Swiftness, rank 25
    [83413]={"+%s%% damage"},                               -- Taeguk
    [83414]={"+%s%% damage"},                               -- Taeguk, rank 25
    [83415]={"+%s%% healing received"},                     -- Invigorating Gemstone
    [83419]={"%s damage still owed"},                       -- Moratorium
    [83400]={"Each pulse deals %s%% weapon damage","+%s%% Movement Speed"}, -- Wreath of Lightning
    [83409]={"Absorbs %s more damage"},                     -- Molten Wildebeest's Gizzard
    -- Six shield rows of the contract's table; the shields' record reads "Absorbs damage." like the Gizzard's, so
    -- they share its line.
    [83340]={"Absorbs %s more damage"},                     -- Galvanizing Ward (shield)
    [83341]={"Absorbs %s more damage"},                     -- Dominance (shield)
    [83342]={"Absorbs %s more damage"},                     -- Unstable Anomaly (shield)
    [83343]={"Absorbs %s more damage"},                     -- Magic Weapon - Deflection (shield)
    [83344]={"Absorbs %s more damage"},                     -- Spectral Blade - Barrier Blades (shield)
    [83361]={"-%s%% damage taken"},                         -- Arcane Torrent - Flame Ward
}
-- Life points read grouped in threes, through the Torment addon's one formatter (12-ui U4) when it is there.
local POINTS={[83419]=true,[83409]=true,[83340]=true,[83341]=true,[83342]=true,[83343]=true,[83344]=true}

B.values={} -- aura id -> the last V's values, as strings

local function grouped(value)
    if Diablocraft and Diablocraft.Econ then return Diablocraft.Econ.Gold(value) end
    local out,more=value,1
    while more>0 do out,more=out:gsub("^(%-?%d+)(%d%d%d)","%1,%2") end
    return out
end

-- The lines for an aura now, or an empty list.
function B.Lines(aura)
    local out,lines,values={},B.LINES[aura],B.values[aura]
    if not lines or not values then return out end
    for i,line in ipairs(lines) do
        local value=values[i]
        if value and tonumber(value) and tonumber(value)~=0 then
            out[#out+1]=line:format(POINTS[aura] and grouped(value) or value)
        end
    end
    return out
end

-- `V|aura|v1|v2...` keeps the values; `G|aura` forgets them.
function B.OnMessage(prefix,body,distribution,sender)
    if prefix~=PREFIX or distribution~="WHISPER" then return end
    local own=UnitName("player")
    if sender~=own and sender~=own.."-"..GetRealmName() then return end
    local f={}
    for field in (body.."|"):gmatch("(.-)|") do f[#f+1]=field end
    local aura=tonumber(f[2])
    if not aura then return end
    if f[1]=="V" then B.values[aura]={select(3,unpack(f))}
    elseif f[1]=="G" then B.values[aura]=nil end
end

-- The lines go under the record's text, in its colour (the stock aura tooltip's description).
local function decorate(tooltip,unit,aura)
    if not aura or not unit or not UnitIsUnit(unit,"player") then return end
    local lines=B.Lines(aura)
    if #lines==0 then return end
    for _,line in ipairs(lines) do tooltip:AddLine(line,1,.82,0,true) end
    tooltip:Show()
end
-- The 11th return of UnitAura / UnitBuff / UnitDebuff is the spell id (3.3.5a).
hooksecurefunc(GameTooltip,"SetUnitAura",function(self,unit,index,filter) decorate(self,unit,select(11,UnitAura(unit,index,filter))) end)
hooksecurefunc(GameTooltip,"SetUnitBuff",function(self,unit,index,filter) decorate(self,unit,select(11,UnitBuff(unit,index,filter))) end)
hooksecurefunc(GameTooltip,"SetUnitDebuff",function(self,unit,index,filter) decorate(self,unit,select(11,UnitDebuff(unit,index,filter))) end)

local watcher=CreateFrame("Frame")
watcher:RegisterEvent("CHAT_MSG_ADDON")
watcher:SetScript("OnEvent",function(_,_,...) B.OnMessage(...) end)
