-- UI state and request-validation regression tests using the real AIO addon.
-- Run from repo root with `lua mod-diablocraft/scripts/tests/crafting/test_crafting.lua`.
--
-- The Mystic's SERVER half (the window half is the rebuild of diablocraft-0atm, wired to the
-- bridge and pinned by test_mystic_window.lua). The old Blacksmith screen this file used to hold is
-- gone (UI ruling R3, 2026-10-03): the Blacksmith's gossip goes to dc_blacksmith.lua only, and with
-- that file missing it draws nothing. What is pinned here:
--   * the Show payload's items[] is only an INDEX (guid, entry, name, rarity, bag, slot) that turns
--     a dragged bag item into its guid: no affixes, no offers, no lock, no attempts, no gems, and
--     no price or jewelry flag (docs/contracts/mystic-enchant-messages.md section 1a) - the window
--     draws everything from the DCARTISAN records, and C++ owns the price and the rules;
--   * it reads the affix and offer rows no more, and lists the worn items as 255 and 0..18 (diablocraft-zmkh);
--   * the Refresh flood is capped by the shared bucket, and the Blacksmith's gossip
--     opens dc_blacksmith.lua's server half and nothing else;
--   * the pushed tables (names, percent, per-slot order and kind, skill groups, gems,
--     base item slot) are the ones the window and the tooltip both read;
--   * no handler on this half wraps a `.dc artisan` RunCommand: the bridge is the only
--     way an action reaches C++.
local side="server";local handlers,gossip,commands,frames,last={}, {}, {}, {},nil
local responses,crafted,pushed,asked,queries={},{},{},{},{}
local function result(rows)
    if not rows[1] then return nil end
    local n=1;local function get(_,i)return rows[n][i+1]end
    return {GetString=get,GetUInt32=get,GetInt32=get,GetDouble=get,NextRow=function()n=n+1;return rows[n]~=nil end}
end
-- One rolled Rare ring in the backpack. Its affixes and its open offers are in the database and
-- must not be read any more: the bridge's records carry them now.
local ITEM,ENTRY=87,100000
local AFFIXES={{0,"gf",30,"primary",0,-1,0},{1,"chc",6,"primary",0,-1,0},
    {2,"sockets",1,"socket",0,-1,0},{3,"mainstat",400,"primary",0,-1,0}}
-- A worn rare item, which the index lists as bag 255 (the designer's dev check 2026-10-06, diablocraft-zmkh:
-- a drag or right-click from the character sheet puts the item in too).
local WORN=88
function WorldDBQuery(q)
    if q:find("display_order",1,true) then
        return result({{"finger","mainstat","primary",2},{"finger","chc","primary",5},
            {"finger","sockets","primary",15},{"finger","gf","secondary",18}})
    end
    if q:find("group_id",1,true) then return result({{"skill_frenzy","frenzy"}}) end
    if q:find("dc_affix_pool",1,true) then
        return result({{"mainstat","Strength",0},{"chc","Critical Hit Chance",1},
            {"gf","Gold Find",1},{"sockets","Sockets",0}})
    end
    if q:find("dc_gem_item",1,true) then return result({{103000,"Ruby"}}) end
    -- The load-time table push reads the slot by entry; show() reads the slot of one entry.
    if q:find("entry,slot FROM dc_base_item",1,true) then return result({{ENTRY,"finger"}}) end
    if q:find("dc_base_item",1,true) then return result({{"finger"}}) end
    assert(not q:find("dc_loot_tuning",1,true),"The Mystic screen must not read the price tuning")
    error(q)
end
function CharDBQuery(q)
    queries[#queries+1]=q
    if q:find("dc_character_mode",1,true) then return result({{"normal"}}) end
    if q:find("dc_account_gold",1,true) then return result({{"650000"}}) end
    if q:find("dc_account_currency",1,true) then
        return result({{102000,"100"},{102001,"100"},{102002,"100"},{102003,"100"},{102004,"100"},{102005,"5"}})
    end
    -- The crafted-items query joins dc_item_instance too, so it is matched first.
    if q:find("SELECT c.item",1,true) then
        if #crafted==0 then return nil end
        local rows={};for _,id in ipairs(crafted)do rows[#rows+1]={id} end;return result(rows)
    end
    -- Only the item's rarity is read now: its lines, its offers, its lock and its attempts arrive
    -- from C++, and the affix and offer rows must not be read here any more.
    assert(q:find("SELECT rarity FROM dc_item_instance",1,true),"Unexpected item query: "..q)
    if q:find("item_guid="..ITEM) then return result({{"rare"}}) end
    if q:find("item_guid="..WORN) then return result({{"legendary"}}) end
end
function RegisterCreatureGossipEvent(entry,_,fn)gossip[entry]=fn end
function RegisterPlayerEvent()end
function GetCurrTime() return 0 end
AIO={AddAddon=function()return side=="server"end,AddHandlers=function(_,h)handlers=h;return h end,
    Handle=function(...)
        last={...}
        if type(last[1])=="table" then responses[last[3]]=last[4];pushed[last[3]]=(pushed[last[3]] or 0)+1
        else asked[last[1].."|"..tostring(last[2])]=(asked[last[1].."|"..tostring(last[2])] or 0)+1 end
    end}
dofile("mod-diablocraft/lua/aio/dc_account.lua")
dofile("mod-diablocraft/lua/aio/dc_throttle.lua")
dofile("mod-diablocraft/lua/aio/dc_aio_range.lua")
dofile("mod-diablocraft/lua/aio/dc_crafting.lua")
local ring={GetEntry=function()return ENTRY end,GetGUIDLow=function()return ITEM end,
    GetName=function()return "Test item" end,GetCount=function()return 1 end}
local worn={GetEntry=function()return 100001 end,GetGUIDLow=function()return WORN end,
    GetName=function()return "Worn helm" end,GetCount=function()return 1 end}
-- The range watcher's world: the Mystic is near until the test walks the player away. The timed
-- event is ALE's player:RegisterEvent, kept here so the test can fire it.
local mysticNear,timers,nextTimer=true,{},0
DCTunables={Get=function(category,key) -- luacheck: ignore 111
    assert(category=="crafting" and key=="artisan_interaction_range_yards","the watcher reads only the artisan range")
    return 5
end}
local player={GetGUIDLow=function()return 6 end,GossipComplete=function()end,GetAccountId=function()return 2 end,
    GetClass=function()return 1 end,IsAlive=function()return true end,IsInCombat=function()return false end,
    GetNearestCreature=function(_,range,entry)
        if entry==910001 then return (mysticNear and range==5) and {} or nil end
        return {}
    end,
    IsInWorld=function()return true end,
    RegisterEvent=function(_,fn,delay,repeats)nextTimer=nextTimer+1;timers[nextTimer]={fn=fn,delay=delay,repeats=repeats};return nextTimer end,
    RemoveEventById=function(_,id)timers[id]=nil end,
    GetCoinage=function()return 3500000000 end,GetItemCount=function(_,entry)return entry==102006 and 3 or 100 end,
    GetItemByPos=function(_,bag,slot)
        if bag==255 and slot==23 then return ring end   -- the backpack
        if bag==255 and slot==0 then return worn end    -- worn head: listed as 255, 0
    end,
    RunCommand=function(_,text)
        commands[#commands+1]=text
        local count=tonumber(text:match("^dc artisan craft 1 (%d+)$"))
        if count then for i=1,count do crafted[#crafted+1]=100+#crafted end end
    end}
gossip[910001](1,player,{GetEntry=function()return 910001 end})
assert(last[4].kind=="Mystic" and last[4].gold=="650000" and last[4].managed)
assert(last[4].gems==nil,"The Show payload no longer carries the gems (section 1a)")
assert(#last[4].items==2,"The index lists the bag item and the worn one")
local sent,wornSent
for _,entry in ipairs(last[4].items) do if entry.bag==255 then wornSent=entry else sent=entry end end
assert(wornSent and wornSent.guid==WORN and wornSent.slot==0,"A worn item is listed as bag 255 and its slot 0..18")
assert(sent and sent.guid==ITEM and sent.entry==ENTRY and sent.rarity=="rare" and sent.name=="Test item"
    and sent.bag==0 and sent.slot==1,
    "An index entry is the guid, the entry, the name, the rarity and the client bag and slot")
-- docs/contracts/mystic-enchant-messages.md section 1a: the window learns an item only from the
-- DCARTISAN records, so an item carries nothing else - no lines, no offers, no lock, no attempts,
-- and no price (C++ owns it) or jewelry flag.
for _,field in ipairs({"affixes","offers","locked","attempts","cost","jewelry"}) do
    assert(sent[field]==nil,"The index must not carry "..field)
end
-- Security G1: a Refresh flood is capped by the shared bucket; with a frozen
-- clock exactly the burst (10) passes. Reverting the throttle pushes all 20.
local shows=pushed.Show or 0
for _=1,20 do handlers.Refresh(player) end
assert((pushed.Show or 0)-shows==10,"the Crafting Refresh drops a flood beyond the bucket")
-- R3: the Blacksmith's gossip opens dc_blacksmith's window and nothing else. With that file
-- missing (DCBlacksmithServer nil) the old Blacksmith screen must not come back.
local mysticShows=pushed.Show or 0
gossip[910000](1,player,{GetEntry=function()return 910000 end})
assert((pushed.Show or 0)==mysticShows,"With dc_blacksmith missing, the Blacksmith's gossip must draw nothing")
GetCurrTime=function() return 60000 end
handlers.Refresh(player)
assert((pushed.Show or 0)==mysticShows,"and a Refresh in the Blacksmith's context draws nothing either")
local blacksmithShown
DCBlacksmithServer={Show=function(who) blacksmithShown=who end}
gossip[910000](1,player,{GetEntry=function()return 910000 end})
assert(blacksmithShown==player and (pushed.Show or 0)==mysticShows,"The Blacksmith's gossip opens dc_blacksmith's window")
DCBlacksmithServer=nil
gossip[910001](1,player,{GetEntry=function()return 910001 end})
assert(handlers.Recipes==nil and handlers.Quote==nil and handlers.Balance==nil,
    "The old Blacksmith screen's Recipes, Quote and Balance are gone (R3)")
assert(last[4].recipes==nil and last[4].maxCraftCount==nil,"The Mystic's Show carries no Blacksmith recipes")
-- diablocraft-3oqx: nothing on this half types a `.dc artisan` command any more. The window sends
-- DCARTISAN on the bridge and C++ is the only gate, so the commands are GM-only and no handler
-- here wraps RunCommand.
assert(handlers.Action==nil and handlers.Craft==nil,"No handler may be left wrapping RunCommand")
handlers.Tables(player)
local tables=responses.Tables
assert(tables.names.mainstat=="Strength" and tables.names.chc=="Critical Hit Chance",
    "The pushed tables carry the affix names")
assert(tables.percent.chc and not tables.percent.mainstat,"and their percent flag")
-- diablocraft-il59k: the seven elemental ids are named and flagged as percent in the table the window reads.
local ELEMENTAL_NAMES={dmgphy="Physical Damage Increase",dmgfir="Fire Damage Increase",dmgcol="Cold Damage Increase",
    dmgpsn="Poison Damage Increase",dmgarc="Arcane Damage Increase",dmglit="Lightning Damage Increase",dmghol="Holy Damage Increase"}
for id,name in pairs(ELEMENTAL_NAMES) do
    assert(tables.names[id]==name and tables.percent[id],id.." must push as '"..name.."' with the percent flag, got "..tostring(tables.names[id]))
end
-- diablocraft-z9ya2: the six single-element resists are named and pushed flat (no percent flag).
local RESIST_NAMES={resphy="Physical Resistance",resfir="Fire Resistance",rescol="Cold Resistance",
    respsn="Poison Resistance",resarc="Arcane Resistance",reslit="Lightning Resistance"}
for id,name in pairs(RESIST_NAMES) do
    assert(tables.names[id]==name and not tables.percent[id],id.." must push as '"..name.."' with no percent flag, got "..tostring(tables.names[id]))
end
assert(tables.orders.finger.chc==5 and tables.kinds.finger.gf=="secondary",
    "and the per-slot display order and kind, got order "..tostring(tables.orders.finger.chc)
    .." kind "..tostring(tables.kinds.finger.gf))
assert(tables.skillGroups.skill_frenzy=="frenzy","and the skill-affix groups")
assert(tables.gems[103000]=="Ruby" and tables.slots[ENTRY]=="finger",
    "and the gem names and the base item slot per entry")
assert(#commands==0,"The window bridge is the only way an action reaches C++")
-- docs/contracts/mystic-enchant-messages.md section 1a: every show() above ran without reading the
-- item's affix or offer rows (CharDBQuery refuses any item query but the rarity read).
local all=table.concat(queries,"\n")
assert(not all:find("dc_item_affix",1,true) and not all:find("dc_enchant_offer",1,true),
    "The server half must not read the affix or offer rows any more")
assert(all:find("SELECT rarity FROM dc_item_instance",1,true),"and reads each rolled item's rarity once")

-- Walking away closes the Mystic (the designer, round 3): the Mystic's gossip starts one range watcher, an
-- in-range tick sends nothing, and the first tick out of range tells the window to close and stops.
local function liveTimers() local out={} for id,t in pairs(timers) do out[#out+1]=t;t.id=id end return out end
timers={}
gossip[910001](1,player,{GetEntry=function()return 910001 end})
gossip[910001](1,player,{GetEntry=function()return 910001 end})
local live=liveTimers()
assert(#live==1 and live[1].delay==500 and live[1].repeats==0,"one repeating watcher per open Mystic window, not one per gossip")
local closes=pushed.Close or 0
live[1].fn(live[1].id,500,0,player)
assert((pushed.Close or 0)==closes and timers[live[1].id],"in range, the watcher keeps the window open")
mysticNear=false
live[1].fn(live[1].id,500,0,player)
assert((pushed.Close or 0)==closes+1,"out of range, the watcher tells the window to close")
assert(#liveTimers()==0,"and stops watching")
mysticNear=true
timers={}
gossip[910000](1,player,{GetEntry=function()return 910000 end})
assert(#liveTimers()==0,"the Blacksmith's gossip starts no Mystic watcher")

print("PASS: the Mystic's server half: Blacksmith gossip only to dc_blacksmith, the Show payload as an "
    .."index (no lines, no offers, no lock, no price, no gems; the worn items as 255), the affix rows unread, the "
    .."Refresh bucket, the pushed tables, no RunCommand wrapper and the walk-away range watcher (the window "
    .."half is test_mystic_window.lua)")
