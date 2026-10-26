-- Server pushes and client hooks for the tooltip contexts added by
-- diablocraft-addon-tooltip-coverage: bank (main + bank bags), vendor buyback
-- and inspect. The bag/character-sheet path is pinned by test_item_tooltip.lua;
-- this file pins the new per-context asks plus the ownership guard (a context
-- can never make the server emit an item the player does not hold) and the
-- capture() no-double-line rule.
-- luacheck: ignore 111 112 121 122 212 213
local serverHandlers,clientHandlers,push
local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        NextRow=function() index=index+1;return rows[index]~=nil end}
end
-- Every guid named in "... IN (a,b,c)" - records() only answers for guids the
-- caller put in `found`, so the stub must too or it would index a nil record.
local function inList(query)
    local list=query:match("IN %(([%d,]+)%)") or ""
    local out={}
    for n in list:gmatch("%d+") do out[#out+1]=tonumber(n) end
    return out
end
function WorldDBQuery(query)
    if query:find("spellid_1=81203",1,true) then return nil end -- no shell templates here
    if query:find("FROM dc_item_preset_range",1,true) or query:find("FROM dc_affix_metadata",1,true) then return nil end -- no preset-only lines here
    if query:find("FROM dc_affix_pool",1,true) then
        assert(query:find("is_percent,kind,display_order",1,true))
        return result({{"legs","mainstat","Primary Attribute",0,"primary",1},
            {"legs","resall","All Resistance",0,"secondary",2}})
    elseif query:find("FROM dc_skill_affix",1,true) then return nil
    elseif query:find("b.entry,b.d3_name",1,true) then
        return result({{100087,"Test Legs","legs","barbarian",70,"","","Flavour",12345}})
    elseif query:find("FROM dc_legendary_gem_item",1,true) then return nil
    elseif query:find("FROM dc_gem_item",1,true) then return nil
    elseif query:find("FROM dc_set_tooltip",1,true) then return nil
    elseif query:find("FROM dc_set_bonus",1,true) then return nil
    elseif query:find("dc_legendary_power",1,true) then return nil
    elseif query:find("SELECT DISTINCT",1,true) then return nil
    end
    error(query)
end
function CharDBQuery(query)
    local guids=inList(query)
    if query:find("FROM dc_item_instance",1,true) then
        local rows={}
        for _,g in ipairs(guids) do rows[#rows+1]={g,"rare",0} end
        return result(rows)
    end
    if query:find("FROM dc_item_unidentified",1,true) then return end
    assert(query:find("FROM dc_item_affix",1,true))
    local rows={}
    for _,g in ipairs(guids) do rows[#rows+1]={g,1,"mainstat",100,90,120,"primary",0,-1,0} end
    return result(rows)
end
function RegisterPlayerEvent() end
-- The server push is the thing under test; record what handlers.Context sends.
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) serverHandlers=h;return h end,
    AddOnInit=function() end,
    Handle=function(_,channel,name,payload) push={channel=channel,name=name,payload=payload} end}
-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
dofile("mod-diablocraft/lua/aio/dc_tooltip.lua")

local function item(entry,guid)
    return {GetEntry=function() return entry end,GetGUIDLow=function() return guid end,
        GetUInt32Value=function() return 0 end}
end
-- Bank main slot 44 = client slot 6, bank bag 67 slot 0 = client bag 5 slot 1,
-- buyback server slot 74 = merchant index 1, inspect legs = equipment slot 6.
local bank,bankBag,buyback,inspect=87,88,89,90
local target={GetGUIDLow=function() return 5 end,visible=true,
    -- ALE's IsVisibleForPlayer asks "is self visible to the argument", so the
    -- handler must call it on the target with the caller as the argument.
    IsVisibleForPlayer=function(self,other)
        assert(other.GetGUIDLow and other:GetGUIDLow()==9,"visibility is asked on the target, with the caller as its argument")
        return self.visible
    end,
    GetItemByPos=function(_,bag,slot) if bag==255 and slot==6 then return item(100087,inspect) end end}
local holder={GetGUIDLow=function() return 9 end,GetSelection=function() return target end,
    near=true,
    IsWithinDistInMap=function(self,other,dist,is3d) assert(dist==28.0 and is3d==false);return self.near end,
    GetItemByPos=function(_,bag,slot)
        if bag==255 and slot==44 then return item(100087,bank) end
        if bag==67 and slot==0 then return item(100087,bankBag) end
        if bag==255 and slot==74 then return item(100087,buyback) end
    end}

serverHandlers.Context(holder,"bank")
assert(push and push.name=="Context" and push.payload.name=="bank","bank context pushed")
assert(push.payload.items[-1] and push.payload.items[-1][6],"bank main slot 44 -> client slot 6")
assert(push.payload.items[-1][6].guid==bank)
assert(push.payload.items[5] and push.payload.items[5][1],"bank bag 67 slot 0 -> client bag 5 slot 1")
assert(push.payload.items[5][1].guid==bankBag)

serverHandlers.Context(holder,"buyback")
assert(push.payload.name=="buyback" and push.payload.items[1] and push.payload.items[1].guid==buyback,
    "buyback server slot 74 -> merchant index 1")

serverHandlers.Context(holder,"inspect",5)
assert(push.payload.name=="inspect" and push.payload.guid==5,"inspect names the target")
assert(push.payload.items[6] and push.payload.items[6].guid==inspect,
    "inspect legs -> equipment slot 6, got "..tostring(push.payload.items[6]))

-- Security G9: like stock inspect, the target must be in range and visible.
push=false
holder.near=false
serverHandlers.Context(holder,"inspect",5)
assert(push==false,"an out-of-range inspect target is dropped with no reply")
holder.near=true
push=false
target.visible=false
serverHandlers.Context(holder,"inspect",5)
assert(push==false,"an invisible inspect target is dropped with no reply")
target.visible=true

-- The ownership guard. A context that names an item the player does not hold
-- (an empty container, or a target the player is not selecting) produces no
-- record at all, so a forged request cannot print someone else's roll.
local empty={GetGUIDLow=function() return 10 end,GetSelection=function() return nil end,
    GetItemByPos=function() return nil end}
push=false
serverHandlers.Context(empty,"bank")
assert(push and push.payload.items and next(push.payload.items)==nil,
    "an empty bank yields no bank records")
push=false
serverHandlers.Context(empty,"buyback")
assert(push and next(push.payload.items)==nil,"an empty buyback yields no records")
push=false
serverHandlers.Context(empty,"inspect",12345)
assert(push==false,"a target the player is not selecting is dropped with no reply")
-- A selection whose GUID is not the one asked for is refused too.
local other={GetGUIDLow=function() return 9 end,GetItemByPos=function() return item(100087,inspect) end,
    GetSelection=function() return {GetGUIDLow=function() return 7 end,GetItemByPos=target.GetItemByPos} end}
push=false
serverHandlers.Context(other,"inspect",5)
assert(push==false,"a GUID that is not the current selection is refused")

-- --- client half -----------------------------------------------------------
local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024,768)
local owner={GetName=function() return "BankFrameItem6" end,GetID=function() return 6 end}
AIO={AddAddon=function() return false end,AddHandlers=function(_,h) clientHandlers=h;return h end,
    Handle=function() end}
MerchantFrame={selectedTab=1}
function GetNumBuybackItems() return 0 end
unpack=unpack or table.unpack
SlashCmdList={}
DEFAULT_CHAT_FRAME={AddMessage=function() end}
-- Pinned stock lines of a hovered item, so capture() has something to read.
GameTooltipTextLeft2={GetText=function() return "Legs" end}
GameTooltipTextLeft3={GetText=function() return "Requires Level 70" end}
dofile("mod-diablocraft/lua/aio/dc_tooltip.lua")
local hooks=GameTooltip.scripts

-- Feed the bank push the server just built, then hover the bank slot.
serverHandlers.Context(holder,"bank")
clientHandlers.Context(nil,push.payload)
GameTooltip.owner=owner
GameTooltip:ClearLines();hooks.OnTooltipCleared(GameTooltip)
-- The client has already drawn its two stock lines (title + 2 = NumLines 3).
GameTooltip.lines={"","",""}
hooks.OnTooltipSetItem(GameTooltip)
local lines=table.concat(GameTooltip.lines,"\n")
assert(lines:find("Test Legs",1,true),"the bank item is decorated by name")
assert(lines:find("+100 Strength",1,true),"the bank item's rolled affix is drawn, got: "..lines)

-- capture() must not read the D3 lines it drew back as native lines: hovering
-- another context item on the same, uncleared tooltip must not double a line.
serverHandlers.Context(holder,"buyback")
clientHandlers.Context(nil,push.payload)
owner={GetName=function() return "MerchantItem1ItemButton" end,GetID=function() return 1 end}
MerchantFrame.selectedTab=2
GameTooltip.owner=owner
hooks.OnTooltipSetItem(GameTooltip)
local body=table.concat(GameTooltip.lines,"\n")
local function count(fragment) return select(2,body:gsub(fragment,"")) end
assert(count("Rare")==1,"the rarity line is drawn exactly once, got "..count("Rare"))
assert(count("Primary")==1,"the Primary header is drawn exactly once, got "..count("Primary"))
-- The header's own slot word is the RIGHT half of a double line, so the mock
-- keeps it out of .lines; a native type line read back from the previous hover
-- would be a standalone line and the first the capture ever saw.
local stale=0
for _,line in ipairs(GameTooltip.lines) do if line=="Legs" then stale=stale+1 end end
assert(stale==0,"no stale native type line from the previous item is re-emitted, got "..stale)
print("PASS: bank/buyback/inspect pushes, ownership guard and the capture no-double-line rule")
