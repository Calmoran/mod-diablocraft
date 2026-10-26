-- luacheck: globals AIO UnitName GetRealmName UnitIsUnit UnitAura UnitBuff UnitDebuff GameTooltip DCBuffValues Diablocraft
-- luacheck: ignore 111 113 121 122
-- Run from the repo root: lua mod-diablocraft/scripts/tests/ui/test_buff_values.lua
--
-- dc_buff_values.lua (diablocraft-kpjs) against the strict 3.3.5a widget mock, on the records of
-- docs/contracts/buff-values-messages.md (DCBUFFVAL). What it pins:
--   * the aura ids and the number of values per aura are the contract's table, and no aura the contract says
--     gets no V has a line;
--   * a V draws its lines under the buff's text through all three setters, in the record text's colour, and
--     shows the tooltip again so it resizes; a G, no V yet, an unknown aura or another unit's aura draws none;
--   * the values are drawn as sent (totals; never multiplied by the stacks); a 0 draws no line; Life points
--     are grouped in threes, through the Torment addon's formatter when it is there;
--   * a record on another prefix or from another sender is dropped.
-- What this does NOT cover: the server's values and throttle (xumo's tests) and the look (the designer's check on dev).
local SOURCE=os.getenv("DC_BUFF_LUA") or "mod-diablocraft/lua/aio/dc_buff_values.lua"

local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local auras={} -- [unit][filter or "any"][index] = {spellId, count}
function UnitName() return "Tester" end
function GetRealmName() return "Torment" end
function UnitIsUnit(a,b) return a==b end
local function aura(kind) return function(unit,index,filter)
    local a=auras[unit] and auras[unit][kind] and auras[unit][kind][index]
    if not a then return nil end
    return "Aura","",nil,a.count,nil,10,100,unit,false,false,a.id
end end
UnitAura,UnitBuff,UnitDebuff=aura("aura"),aura("buff"),aura("debuff")
AIO={AddAddon=function() return false end}
Diablocraft=nil
dofile(SOURCE)

local B=DCBuffValues
local function chat(body,sender,prefix) B.OnMessage(prefix or "DCBUFFVAL",body,"WHISPER",sender or "Tester") end
local function tip(setter,unit,index)
    GameTooltip:ClearLines();GameTooltip:Hide()
    GameTooltip[setter](GameTooltip,unit,index)
    return GameTooltip.lines or {}
end
local function same(a,b)
    if #a~=#b then return false end
    for i=1,#a do if a[i]~=b[i] then return false end end
    return true
end

-- 1. The contract's table: the same aura ids, and as many lines as the aura has values.
local contract
do
    local file=io.open("docs/contracts/buff-values-messages.md")
    contract=file:read("*a");file:close()
end
local section=contract:match("## Values by aura(.-)\n## ")
assert(section,"the contract has its Values by aura table")
local seen=0
for row in section:gmatch("\n(|[^\n]+)") do
    local id,values=row:match("^|[^|]+| (%d+) |([^\n]+)|$")
    if id then
        seen=seen+1
        local count=0
        for _ in values:gmatch("%d+:") do count=count+1 end
        assert(B.LINES[tonumber(id)],"a line for contract aura "..id)
        assert(#B.LINES[tonumber(id)]==count,"aura "..id.." has "..count.." values in the contract")
    end
end
local mine=0
for _ in pairs(B.LINES) do mine=mine+1 end
assert(seen>0 and mine==seen,"the file's auras are the contract's, "..mine.." against "..seen)
local none=contract:match("Auras with %*%*no%*%* `V`(.-)\n\n")
assert(none,"the contract's no-V list")
for id in none:gmatch("%((%d+)%)") do assert(not B.LINES[tonumber(id)],"no line for "..id) end

-- 2. Gogok: the total as sent, under the buff, through UnitBuff; the stacks multiply nothing.
auras.player={buff={{id=83411,count=12}},aura={{id=83400,count=1}},debuff={{id=83419,count=1}}}
assert(#tip("SetUnitBuff","player",1)==0,"no V yet: the record's text alone")
chat("V|83411|6.12")
local lines=tip("SetUnitBuff","player",1)
assert(same(lines,{"+6.12% Dodge"}),"the Dodge line, got "..tostring(lines[1]))
local c=GameTooltip.lineColors[1]
assert(c[1]==1 and c[2]==.82 and c[3]==0,"in the record text's colour")
assert(GameTooltip:IsShown(),"the tooltip is shown again so it resizes")
chat("V|83411|8.88")
assert(same(tip("SetUnitBuff","player",1),{"+8.88% Dodge"}),"the latest V wins")

-- 3. Another unit's aura of the same id gets nothing (the values are this character's).
auras.party1={buff={{id=83411,count=3}}}
assert(#tip("SetUnitBuff","party1",1)==0,"another unit's Gogok has no line")

-- 4. G forgets.
chat("G|83411")
assert(#tip("SetUnitBuff","player",1)==0,"G empties it")

-- 5. Wreath through UnitAura: two values, a 0 draws no line.
chat("V|83400|35|0")
assert(same(tip("SetUnitAura","player",1),{"Each pulse deals 35% weapon damage"}),"the MS line is omitted at 0")
chat("V|83400|61|25")
assert(same(tip("SetUnitAura","player",1),{"Each pulse deals 61% weapon damage","+25% Movement Speed"}),"both at rank 25")

-- 6. Moratorium through UnitDebuff: Life points grouped; through the addon's formatter when there.
chat("V|83419|1500")
assert(same(tip("SetUnitDebuff","player",1),{"1,500 damage still owed"}),"grouped in threes")
Diablocraft={Econ={Gold=function(v) return "<"..v..">" end}}
assert(same(tip("SetUnitDebuff","player",1),{"<1500> damage still owed"}),"the Torment formatter")
Diablocraft=nil
chat("V|83419|0")
assert(#tip("SetUnitDebuff","player",1)==0,"nothing owed: no line")

-- 7. Unknown auras, a malformed aura id, another prefix or sender: nothing.
auras.player.buff[2]={id=83416,count=1}
chat("V|83416|5")
assert(#tip("SetUnitBuff","player",2)==0,"Bane of the Powerful has no V line")
chat("V|83411|4.5","Somebody")
chat("V|83411|4.5","Tester","DCSHEET")
chat("V|x|4.5")
assert(#tip("SetUnitBuff","player",1)==0,"dropped")
chat("V|83411|4.5","Tester-Torment")
assert(same(tip("SetUnitBuff","player",1),{"+4.5% Dodge"}),"the realm-suffixed own name is accepted")

print("PASS: buff values: the contract's auras, V/G, three setters, own auras only, totals as sent, 0 omitted, grouping.")
