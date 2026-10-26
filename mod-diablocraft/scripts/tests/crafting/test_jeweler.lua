-- Real Jeweler AIO handlers and placeholder, with host/DB interfaces stubbed.
local side="server"
local handlers,gossip,responses,commands,frames,pushed={},{},{},{},{},{}
local socketsOn88=false
local legendaryOn=false   -- part 9: a legendary gem in the backpack and in the helm's second socket
local function query(rows)
    local n=1;local function get(_,i) return rows[n][i+1] end
    return {GetUInt32=get,GetString=get,NextRow=function() n=n+1;return rows[n]~=nil end}
end
function WorldDBQuery(sql)
    if sql:find("dc_jeweler_recipe",1,true) then return query({{103002,103007,3,500000,1,"Flawless Royal Amethyst","Royal Amethyst","Amethyst","Flawless Royal",10}}) end
    if sql:find("dc_jeweler_catalog_material",1,true) then
        return query({{398284,103200,1,"Leoric's Regret"},{398284,102004,10,"Forgotten Soul"}})
    end
    if sql:find("dc_jeweler_catalog",1,true) then
        return query({{398284,101113,"Hellfire Amulet (Strength)","neck","Amulet","amulets","legendary",70,1,"50000",1,""}})
    end
    if sql:find("dc_base_item",1,true) then return query({{100000,"head"},{100001,"twohand"},{100002,"offhand"}}) end
    if sql:find("FROM dc_legendary_gem_item",1,true) then return query({{103100,"Bane of the Powerful"}}) end
    if sql:find("dc_gem_item",1,true) then return query({{103007,"Royal Amethyst"},{103002,"Flawless Royal Amethyst"}}) end
    error(sql)
end
function CharDBQuery(sql)
    if sql:find("dc_character_mode",1,true) then return query({{"normal"}}) end
    if sql:find("dc_account_gold",1,true) then return query({{"650000"}}) end
    if sql:find("dc_account_currency",1,true) then
        return query({{102000,"100"},{102001,"100"},{102002,"100"},{102003,"100"},{102004,"100"},{102005,"5"}})
    end
    -- A socketed legendary gem's rank is in legendary_rank; its gem_rank is 0 (docs/contracts/legendary-gems.md).
    if sql:find("a.item_guid=87 ",1,true) and legendaryOn then
        return query({{0,0,0},{1,103100,sql:find("legendary_rank",1,true) and 12 or 0}})
    end
    if sql:find("a.item_guid=87 ",1,true) then return query({{0,0,0}}) end
    if sql:find("a.item_guid=88 ",1,true) and socketsOn88 then return query({{0,0,0}}) end
end
function RegisterCreatureGossipEvent(entry,_,fn) gossip[entry]=fn end
function RegisterPlayerEvent() end
AIO={AddAddon=function() return side=="server" end,AddHandlers=function(_,h) handlers=h;return h end,
    Handle=function(a,b,c,d) if type(a)=="table" then responses[c]=d;pushed[c]=(pushed[c] or 0)+1 else commands[#commands+1]={a,b,c,d} end end}
local nowMs=0
function GetCurrTime() return nowMs end
local timers,nextTimer={},0
DCTunables={Get=function(category,key) -- luacheck: ignore 111
    assert(category=="crafting" and key=="artisan_interaction_range_yards","the watcher reads only the artisan range")
    return 5
end}
local item={GetEntry=function() return 100000 end,GetGUIDLow=function() return 87 end,GetName=function() return "Socketed helm" end}
local legendaryGem={GetEntry=function() return 103100 end,GetGUIDLow=function() return 91 end,GetName=function() return "Bane of the Powerful" end,GetCount=function() return 1 end}
local gem={GetEntry=function() return 103007 end,GetGUIDLow=function() return 90 end,GetName=function() return "Royal Amethyst" end,GetCount=function() return 3 end}
-- A second socketed item, in the backpack (client bag 0, slot 2), with no socket rows in the stub database.
local plain={GetEntry=function() return 100001 end,GetGUIDLow=function() return 88 end,GetName=function() return "Plain axe" end}
local player={GetGUIDLow=function() return 1 end,GetAccountId=function() return 2 end,GetClass=function() return 1 end,IsAlive=function() return true end,
    IsInCombat=function() return false end,GetNearestCreature=function() return {} end,GossipComplete=function() end,
    IsInWorld=function() return true end,
    -- ALE's timed player event, kept so the test can fire the walk-away watcher (dc_aio_range.lua).
    RegisterEvent=function(_,fn,delay,repeats) nextTimer=nextTimer+1;timers[nextTimer]={fn=fn,delay=delay,repeats=repeats};return nextTimer end,
    RemoveEventById=function(_,id) timers[id]=nil end,
    GetCoinage=function() return 3500000000 end,GetItemCount=function() return 3 end,
    GetItemByPos=function(_,bag,slot) if bag==255 and slot==0 then return item elseif bag==255 and slot==23 then return gem elseif bag==255 and slot==24 then return plain
        elseif bag==255 and slot==25 and legendaryOn then return legendaryGem end end,
    -- diablocraft-3oqx: the window bridge is the only way an action reaches C++, so this
    -- tripwire must stay empty.
    RunCommand=function(_,cmd) commands[#commands+1]=cmd end}
-- dc_tooltip.lua's export: the one place a gem's effect is worded and the slot rule lives.
DCGemInfo={Slot=function(slot) return slot=="head" and "head" or (slot=="onehand" or slot=="twohand") and "weapon" or "other" end,
    Effects=function(entry) if entry==103007 then return {weapon="+20000 Life per Hit",head="+22% Life",other="+220 Vitality"} end end}
dofile('mod-diablocraft/lua/aio/dc_account.lua')
dofile('mod-diablocraft/lua/aio/dc_throttle.lua')
dofile("mod-diablocraft/lua/aio/dc_aio_range.lua")
dofile(os.getenv('DC_JEWELER_SERVER_LUA') or 'mod-diablocraft/lua/aio/dc_jeweler_server.lua')
-- The client half returns before it builds a frame when AIO says it is the server (CreateFrame does not exist here).
dofile('mod-diablocraft/lua/aio/dc_jeweler.lua')
gossip[910004](1,player)
local model=responses.Show
assert(#model.items==1 and #model.gems==1 and model.items[1].sockets[1].seq==0)
assert(model.items[1].slotClass=="head","an item carries which of a gem's three effects it takes (head from its base slot)")
assert(model.recipes[1].rank==10,"a recipe carries its tier rank so the window can order tiers")
assert(model.balance.gold=="650000")
-- Craft Jewelry (docs/contracts/jeweler-messages.md): the catalogue with each recipe's materials and what the player holds of them,
-- a bag count for an organ (the stub holds 3) and the ledger for the account material (the Forgotten Soul, 100).
local hellfire=model.crafts[1]
assert(#model.crafts==1 and hellfire.id==398284 and hellfire.entry==101113 and hellfire.name=="Hellfire Amulet (Strength)"
    and hellfire.page=="amulets" and hellfire.rarity=="legendary" and hellfire.required==1 and hellfire.gold=="50000" and hellfire.enabled==true,
    "Show carries the Jeweler's craft catalogue")
assert(#hellfire.materials==2 and hellfire.materials[1].entry==103200 and hellfire.materials[1].amount==1 and hellfire.materials[1].have=="3",
    "a bag material is counted in the bags")
assert(hellfire.materials[2].entry==102004 and hellfire.materials[2].amount==10 and hellfire.materials[2].name=="Forgotten Soul"
    and hellfire.materials[2].have=="100", "an account material is counted in the ledger")
assert(model.craftMax==16,"the craft bound is the backpack's 16 slots plus the bags")
assert(model.removeGold==nil,"the Show payload carries no gem-removal price; the server charges jeweler.csv's")
-- Walking away closes the Jeweler (diablocraft-5mxi): its gossip starts one 500 ms watcher on the
-- Jeweler (910004) at the artisan range, a second gossip replaces it, an in-range tick sends nothing,
-- and out of range it sends Close on the Jeweler's channel and stops.
do
    local function live() local out={} for id,t in pairs(timers) do t.id=id;out[#out+1]=t end return out end
    gossip[910004](1,player)
    assert(#live()==1 and live()[1].delay==500 and live()[1].repeats==0,"one repeating watcher per open window, not one per gossip")
    local tick,closes,asked=live()[1],pushed.Close or 0,nil
    local near=player.GetNearestCreature
    player.GetNearestCreature=function(_,range,entry) asked={range,entry};return {} end
    tick.fn(tick.id,500,0,player)
    assert((pushed.Close or 0)==closes and timers[tick.id],"in range, the watcher keeps the window open")
    assert(asked[1]==5 and asked[2]==910004,"the watcher asks for the Jeweler at artisan_interaction_range_yards")
    player.GetNearestCreature=function() end
    tick.fn(tick.id,500,0,player)
    assert((pushed.Close or 0)==closes+1,"out of range, the watcher tells the Jeweler window to close")
    assert(#live()==0,"and stops watching")
    player.GetNearestCreature=near
end
-- Security G1: the Refresh handler drops a flood. With a frozen clock the
-- bucket lets exactly its burst (10) through; reverting the throttle would
-- push all 20 and fail this.
local shows=pushed.Show or 0
for _=1,20 do handlers.Refresh(player) end
assert((pushed.Show or 0)-shows==10,"the Jeweler Refresh drops a flood beyond the bucket")
-- Every Jeweler read spends that one budget (dc_jeweler.lua), so let it refill before the next.
nowMs=nowMs+60000
handlers.Quote(player,103002);assert(responses.Quote.affordable and #commands==0)
-- diablocraft-3oqx: the action handlers that typed `.dc jeweler ...` are gone, so `dc jeweler`
-- is GM-only and the client half speaks DCJEWELER. What is left here is read-only.
assert(handlers.Socket==nil and handlers.Remove==nil and handlers.Combine==nil and handlers.Repair==nil,
    "No handler may be left wrapping RunCommand")
handlers.Tables(player)
assert(responses.Tables.gems[103007]=="Royal Amethyst","The pushed tables carry the gem names")
assert(responses.Tables.effects[103007].weapon=="+20000 Life per Hit" and responses.Tables.effects[103007].head=="+22% Life"
    and responses.Tables.effects[103007].other=="+220 Vitality","The pushed tables carry each gem's effect per item type, in the tooltip's words")
for _,v in ipairs({0,-1,1.5,4294967296,math.huge,0/0,"103002;delete"}) do handlers.Quote(player,v) end
player.IsInCombat=function() return true end
handlers.Refresh(player);assert(#commands==0)
player.IsInCombat=function() return false end;player.GetNearestCreature=function() end
handlers.Refresh(player)
assert(#commands==0,"The window bridge is the only way an action reaches C++")
-- diablocraft-jeweler-window: the Sockets window opens anywhere, so Gear answers with no Jeweler nearby, even
-- in combat, for the ONE item asked for (by where it is, or by guid) and the bag gems.
GetCurrTime=function() return 100000 end   -- a fresh clock: the flood test above spent the frozen one's budget
responses.Gear=nil
handlers.Gear(player,255,0,0)
assert(responses.Gear and #responses.Gear.items==1 and responses.Gear.items[1].guid==87 and responses.Gear.items[1].slotClass=="head"
    and #responses.Gear.gems==1 and responses.Gear.gems[1].guid==90,"Gear by position answers away from the Jeweler")
-- A second carried item that has sockets too is not sent when it is not the one asked for.
socketsOn88=true
responses.Gear=nil
handlers.Gear(player,255,0,0)
assert(responses.Gear and #responses.Gear.items==1 and responses.Gear.items[1].guid==87,"only the asked-for item is read, not every socketed item carried")
socketsOn88=false
responses.Gear=nil
player.IsInCombat=function() return true end
handlers.Gear(player,255,0,0)
assert(responses.Gear and responses.Gear.items[1].guid==87,"it is a read: combat does not stop it")
player.IsInCombat=function() return false end
responses.Gear=nil
handlers.Gear(player,0,0,87)
assert(responses.Gear and #responses.Gear.items==1 and responses.Gear.items[1].guid==87,"Gear by guid finds the item wherever it is")
responses.Gear=nil
handlers.Gear(player,0,0,12345)
assert(responses.Gear and #responses.Gear.items==0 and #responses.Gear.gems==1,"a guid that is not carried answers with no item")
responses.Gear=nil
handlers.Gear(player,255,5,0)
assert(responses.Gear and #responses.Gear.items==0,"an empty position answers with no item")
for _,args in ipairs({{-1,0,0},{256,0,0},{0,-1,0},{0,256,0},{1.5,0,0},{"0",0,0},{0,0,-1},{0,0,1.5},{0,0,"87"},{0,0,4294967296},{nil,nil,nil}}) do
    responses.Gear=nil
    handlers.Gear(player,args[1],args[2],args[3])
    assert(responses.Gear==nil,"a malformed Gear request is dropped")
end
player.IsAlive=function() return false end
handlers.Gear(player,255,0,0)
assert(responses.Gear==nil,"a dead player is not answered")
player.IsAlive=function() return true end
local gearShows=pushed.Gear or 0
for _=1,30 do handlers.Gear(player,255,0,0) end
assert((pushed.Gear or 0)-gearShows==4,"Gear shares the Refresh budget (10) with Refresh: the six well-formed requests above spent six of it, so four more go and the rest of a flood is dropped")
-- Part 9 (diablocraft-jjb3): a legendary gem is listed among the bag gems and names its socket like a normal gem
-- (no more "Unsupported gem"), the socket carries the gem's legendary_rank, and the tables mark it legendary.
legendaryOn=true
GetCurrTime=function() return 200000 end
responses.Gear=nil
handlers.Gear(player,255,0,0)
local gear=responses.Gear
assert(gear and #gear.gems==2 and gear.gems[2].guid==91 and gear.gems[2].entry==103100 and gear.gems[2].name=="Bane of the Powerful",
    "a legendary gem in the bags is listed with the normal ones")
local socket=gear.items[1].sockets[2]
assert(socket and socket.gemEntry==103100 and socket.name=="Bane of the Powerful","a socketed legendary gem is named, not 'Unsupported gem'")
assert(socket.rank==12,"a socketed legendary gem's rank is its legendary_rank, not gem_rank")
handlers.Tables(player)
assert(responses.Tables.gems[103100]=="Bane of the Powerful" and responses.Tables.legendary[103100]
    and not responses.Tables.legendary[103007],"the pushed tables name legendary gems and mark them, and only them")
print('PASS Jeweler server: legendary gems listed, named and ranked')
print('PASS Jeweler server: context, quotes, normal bag gems, seq 0, gem tables and effects, Gear anywhere, no RunCommand left')

