-- Read-only AIO side: source identity/costs, actual bag sizes, bounds and range.
local H={};local replies={};local queries={};local alive,inCombat,near,budget=true,false,true,true
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) H=h;return h end,
    Handle=function(_,channel,method,payload) replies[#replies+1]={channel=channel,method=method,payload=payload} end}
DCTunables={Get=function(_,key) return ({artisan_interaction_range_yards=5,artisan_per_second=5,artisan_burst=10,blacksmith_cast_seconds=2})[key] end}
DCThrottle={Allow=function() return budget end}
DCAccount={Snapshot=function() return {gold="18446744073709551615",materials={[102001]="123"}} end}
local function result(data)
    local row=1;return {GetUInt32=function(_,i) return data[row][i+1] end,GetString=function(_,i) return tostring(data[row][i+1]) end,
        NextRow=function() row=row+1;return data[row]~=nil end}
end
function WorldDBQuery(sql)
    queries[#queries+1]=sql
    if sql:find("dc_class_map",1,true) then return result({{"barbarian"}}) end
    if sql:find("FROM dc_blacksmith_catalog c",1,true) then return result({{362204,100004,"Belt","waist","Belt","armor","rare",65,61,"1000",1,"",""}}) end
    if sql:find("dc_blacksmith_catalog_material",1,true) then return result({{362204,102001,15,"Crafting_AssortedParts_01","Reusable Parts"}}) end
    error("Unexpected query: "..sql)
end
function CharDBQuery(sql) return sql:find("SELECT item_guid,rarity",1,true) and result({{88,"legendary"}}) or result({{"legendary"}}) end
local item={GetGUIDLow=function() return 88 end,GetEntry=function() return 100004 end,GetName=function() return "Belt" end,GetCount=function() return 1 end}
local container={GetBagSize=function() return 40 end}
local positions={}
-- ALE's timed player event, kept so the test can fire the walk-away watcher (dc_aio_range.lua).
local timers,nextTimer,asked={},0,{}
local player={GetGUIDLow=function() return 9 end,GetLevel=function() return 70 end,GetClass=function() return 1 end,
    IsAlive=function() return alive end,IsInCombat=function() return inCombat end,IsInWorld=function() return true end,
    GetNearestCreature=function(_,range,entry) asked[#asked+1]={range,entry};return near and {GetName=function() return "Haedrig" end} end,
    RegisterEvent=function(_,fn,delay,repeats) nextTimer=nextTimer+1;timers[nextTimer]={fn=fn,delay=delay,repeats=repeats};return nextTimer end,
    RemoveEventById=function(_,id) timers[id]=nil end,
    GetItemByPos=function(_,bag,slot)
        positions[#positions+1]={bag,slot}
        if bag==255 and slot==19 then return container end
        if bag==19 and slot==39 then return item end
    end}
function RegisterPlayerEvent() end -- luacheck: ignore 121
dofile("mod-diablocraft/lua/aio/dc_aio_range.lua")
dofile("mod-diablocraft/lua/aio/dc_blacksmith.lua")
DCBlacksmithServer.Show(player)
local payload=replies[#replies].payload
assert(payload.gold=="18446744073709551615" and payload.castSeconds==2 and payload.maxCount==56)
assert(payload.recipes[1].entry==100004 and payload.recipes[1].id==362204 and payload.recipes[1].materials[1].amount==15)
assert(#payload.items==1 and payload.items[1].slot==40,"bags larger than 36 must be scanned")
-- Walking away closes the Blacksmith (diablocraft-5mxi): the Show that opens the window starts one
-- 500 ms watcher on the Blacksmith (910000) at the artisan range; a Refresh starts none; in range a
-- tick sends nothing; out of range it sends Close on the Blacksmith's channel and stops.
local function live() local out={} for id,t in pairs(timers) do t.id=id;out[#out+1]=t end return out end
assert(#live()==1 and live()[1].delay==500 and live()[1].repeats==0,"the opening Show starts one repeating watcher")
H.Refresh(player);assert(#live()==1,"a Refresh starts no second watcher")
local tick=live()[1];local before=#replies;asked={}
tick.fn(tick.id,500,0,player);assert(#replies==before and timers[tick.id],"in range, the watcher keeps the window open")
assert(asked[1][1]==5 and asked[1][2]==910000,"the watcher asks for the Blacksmith at artisan_interaction_range_yards")
near=false;tick.fn(tick.id,500,0,player)
assert(#replies==before+1 and replies[#replies].channel=="DiablocraftBlacksmith" and replies[#replies].method=="Close",
    "out of range, the watcher tells the Blacksmith window to close")
assert(#live()==0,"and stops watching")
near=true
H.Target(player,1,40,1);assert(replies[#replies].payload.item.guid==88)
-- Same target handler for a bag item and worn gear; equipment uses core slots,
-- including the zero/last boundaries, and never needs a spare bag cell.
local bagLookup=player.GetItemByPos
function player:GetItemByPos(bag,slot)
    if bag==255 and (slot==0 or slot==15 or slot==18) then return item end
    return bagLookup(self,bag,slot)
end
for _,slot in ipairs({0,15,18}) do
    H.Target(player,255,slot,10+slot)
    local target=replies[#replies].payload
    assert(target.nonce==10+slot and target.item.guid==88 and target.item.equipped
        and target.item.bag==255 and target.item.slot==slot,"worn target preserves GUID and core position")
end
H.Target(player,255,1,30);assert(replies[#replies].payload.item==nil,"empty worn slot")
H.Target(player,255,19,31);assert(replies[#replies].payload.item==nil,"equipped bag is not worn gear")
H.Target(player,1,41,2);assert(replies[#replies].payload.item==nil,"outside bag bounds")
local n=#replies;H.Target(player,5,1,3);assert(replies[#replies].payload.item==nil,"bank cannot be selected")
H.Target(player,-1,1,3);assert(#replies==n+1,"negative position refused")
near=false;H.Target(player,1,40,4);assert(#replies==n+1,"range guard")
near=true;inCombat=true;H.Target(player,1,40,4);assert(#replies==n+1,"combat guard")
inCombat=false;alive=false;H.Target(player,1,40,4);assert(#replies==n+1,"living guard")
alive=true;budget=false;H.Refresh(player);assert(#replies==n+1,"throttle must stop reads")
print("Blacksmith query guards, decimal balances, mapped outputs, 40-slot bags and the walk-away Close passed")
