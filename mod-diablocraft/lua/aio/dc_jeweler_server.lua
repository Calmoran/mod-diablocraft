-- luacheck: globals DCThrottle DCRange DCGemInfo RegisterCreatureGossipEvent
-- The Jeweler's server half: the window's reads (Show, Refresh, Recipes, Quote, Items, Gear, Tables, Balance) and the
-- Craft Jewelry catalogue. Every change goes through the DCJEWELER window bridge in C++. The client half is dc_jeweler.lua;
-- this file never calls AIO.AddAddon(), so nothing here is sent to a client.
local AIO=AIO or require("AIO")
local CHANNEL="DiablocraftJeweler"
local handlers=AIO.AddHandlers(CHANNEL,{})
local contexts={}
-- The gem names, loaded once: show() names every gem in the bags with them, and the client
-- half needs the same names to label a gem the bridge reply added (handlers.Tables).
local gemNames,baseSlots,legendary={},{},{}
local function load()
    local rows=WorldDBQuery("SELECT entry,name FROM dc_gem_item")
    if rows then repeat gemNames[rows:GetUInt32(0)]=rows:GetString(1) until not rows:NextRow() end
    -- Part 9 (docs/contracts/legendary-gems.md): legendary gems are listed and named like normal ones;
    -- C++ socketing, removing and swapping takes them. They never combine (recipes() reads dc_gem_item).
    rows=WorldDBQuery("SELECT li.entry,t.name FROM dc_legendary_gem_item li JOIN item_template t ON t.entry=li.entry")
    if rows then repeat
        gemNames[rows:GetUInt32(0)]=rows:GetString(1);legendary[rows:GetUInt32(0)]=true
    until not rows:NextRow() end
    -- Which of a gem's three effects an item takes follows its base slot (see DCGemInfo in dc_tooltip.lua).
    rows=WorldDBQuery("SELECT entry,slot FROM dc_base_item")
    if rows then repeat baseSlots[rows:GetUInt32(0)]=rows:GetString(1) until not rows:NextRow() end
end
load()
-- A gem's effect on each kind of item, in the tooltip's own words, asked of dc_tooltip.lua when the
-- client wants it (that file may load after this one). Not kept when dc_tooltip is absent.
local effectText
local function effects()
    if effectText then return effectText end
    if not DCGemInfo then return {} end
    local out={}
    for entry in pairs(gemNames) do out[entry]=DCGemInfo.Effects(entry) or {} end
    effectText=out
    return out
end
local function slotClass(entry)
    return DCGemInfo and DCGemInfo.Slot(baseSlots[entry]) or "other"
end
local function errorResponse(player,request,message)
    AIO.Handle(player,CHANNEL,"Error",{request=request,message=message})
end
local function valid(player,request)
    if not contexts[player:GetGUIDLow()] or not player:IsAlive()
        or player:IsInCombat() or not player:GetNearestCreature(5,910004) then
        errorResponse(player,request,"Open the Jeweler while alive, nearby and out of combat.");return false
    end
    return true
end
local function integer(n,minimum)
    -- constant: uint32 id bound.
    return type(n)=="number" and n==math.floor(n) and n>=minimum and n<=4294967295
end
-- Exact account totals as decimal strings (0007), as in Blacksmith. Gold Bar
-- arithmetic is gone; gems below stay ordinary item counts.
local function balance(player,snapshot)
    snapshot=snapshot or DCAccount.Snapshot(player)
    return {gold=snapshot.gold,managed=snapshot.managed,
        deathsBreath=snapshot.materials[102000] or "0"}
end
local function recipes(player)
    local out={}
    local rows=WorldDBQuery("SELECT r.output_entry,r.input_entry,r.input_count,r.gold_d3,r.deaths_breath,o.name,i.name,o.colour,o.tier,o.`rank` "..
        "FROM dc_jeweler_recipe r JOIN dc_gem_item o ON o.entry=r.output_entry JOIN dc_gem_item i ON i.entry=r.input_entry ORDER BY o.colour,o.`rank`")
    if rows then repeat
        out[#out+1]={id=rows:GetUInt32(0),inputEntry=rows:GetUInt32(1),inputCount=rows:GetUInt32(2),gold=rows:GetUInt32(3),
            deathsBreath=rows:GetUInt32(4),name=rows:GetString(5),inputName=rows:GetString(6),colour=rows:GetString(7),tier=rows:GetString(8),
            rank=rows:GetUInt32(9),
            have=player:GetItemCount(rows:GetUInt32(1),false)}
    until not rows:NextRow() end
    return out
end
-- Craft Jewelry (docs/contracts/jeweler-messages.md): the catalogue the window lists, each recipe with its
-- materials and what the player holds of each (a bag count for a gem or an organ, the ledger for an account
-- material, DCAccount.Have). The gold is the catalogue's own figure, as the Blacksmith sends it.
local function crafts(player,snapshot)
    local materials={}
    local rows=WorldDBQuery("SELECT m.recipe_id,m.item_entry,m.amount,COALESCE(i.name,'') FROM dc_jeweler_catalog_material m "..
        "LEFT JOIN item_template i ON i.entry=m.item_entry ORDER BY m.recipe_id,m.item_entry")
    if rows then repeat
        local id,entry=rows:GetUInt32(0),rows:GetUInt32(1)
        materials[id]=materials[id] or {}
        local list=materials[id]
        list[#list+1]={entry=entry,amount=rows:GetUInt32(2),name=rows:GetString(3),have=DCAccount.Have(snapshot,entry)}
    until not rows:NextRow() end
    local out={}
    rows=WorldDBQuery("SELECT id,output_entry,name,slot,category,page,rarity,item_level,required_level,CAST(gold_d3 AS CHAR),enabled,unavailable_reason "..
        "FROM dc_jeweler_catalog ORDER BY id")
    if rows then repeat
        local id=rows:GetUInt32(0)
        out[#out+1]={id=id,entry=rows:GetUInt32(1),name=rows:GetString(2),slot=rows:GetString(3),category=rows:GetString(4),
            page=rows:GetString(5),rarity=rows:GetString(6),level=rows:GetUInt32(7),required=rows:GetUInt32(8),
            gold=rows:GetString(9),enabled=rows:GetUInt32(10)~=0,reason=rows:GetString(11),materials=materials[id] or {}}
    until not rows:NextRow() end
    return out
end
-- The most a single craft request may make: every bag slot the player has, the bound the bridge checks.
local function craftMax(player)
    local total=16
    for bag=19,22 do
        local container=player:GetItemByPos(255,bag)
        if container then total=total+container:GetBagSize() end
    end
    return total
end
-- `wanted` (optional) is a function(bag,slot,guid) that picks the one item the Sockets window asks
-- for: the per-item socket query runs for it alone, while every bag gem is still listed.
local function inventory(player,wanted)
    local items,gems,names={},{},gemNames
    local function add(bag,slot,item)
        if not item then return end
        local entry,guid=item:GetEntry(),item:GetGUIDLow()
        if names[entry] then
            if bag~=255 then gems[#gems+1]={guid=guid,entry=entry,name=names[entry],count=item:GetCount(),bag=bag,slot=slot} end
            return
        end
        if wanted and not wanted(bag,slot,guid) then return end
        -- A legendary gem's rank is legendary_rank; gem_rank is a normal gem's tier (the contract).
        local rows=CharDBQuery("SELECT a.seq,COALESCE(g.gem_entry,0),COALESCE(g.legendary_rank,g.gem_rank,0) FROM dc_item_affix a JOIN dc_item_instance i ON i.item_guid=a.item_guid "..
            "LEFT JOIN dc_item_affix g ON g.item_guid=a.item_guid AND g.kind='gem' AND g.parent_seq=a.seq WHERE a.kind='socket' AND a.item_guid="..guid.." ORDER BY a.seq")
        if not rows then return end
        local data={guid=guid,entry=entry,name=item:GetName(),bag=bag,slot=slot,slotClass=slotClass(entry),sockets={}}
        repeat
            local gemEntry=rows:GetUInt32(1)
            data.sockets[#data.sockets+1]={seq=rows:GetUInt32(0),gemEntry=gemEntry,rank=rows:GetUInt32(2),
                name=gemEntry==0 and "Empty socket" or names[gemEntry] or "Unsupported gem"}
        until not rows:NextRow()
        items[#items+1]=data
    end
    for slot=0,18 do add(255,slot,player:GetItemByPos(255,slot)) end
    for slot=23,38 do add(0,slot-22,player:GetItemByPos(255,slot)) end
    for bag=19,22 do
        local container=player:GetItemByPos(255,bag)
        if container then for slot=0,container:GetBagSize()-1 do add(bag-18,slot+1,player:GetItemByPos(bag,slot)) end end
    end
    return items,gems
end
local function show(player)
    if not valid(player,"Refresh") then return end
    local items,gems=inventory(player)
    local snapshot=DCAccount.Snapshot(player)
    -- No removal price is sent: the server charges jeweler.csv's price and nothing else,
    -- so the window has no second figure to disagree with it.
    AIO.Handle(player,CHANNEL,"Show",{items=items,gems=gems,recipes=recipes(player),balance=balance(player,snapshot),
        crafts=crafts(player,snapshot),craftMax=craftMax(player)})
end
-- Walking away closes the window: the shared range watcher, dc_aio_range.lua.
RegisterCreatureGossipEvent(910004,1,function(_,player)
    contexts[player:GetGUIDLow()]=true;player:GossipComplete();show(player)
    DCRange.Artisan(player,CHANNEL,910004);return true
end)
RegisterPlayerEvent(4,function(_,player) contexts[player:GetGUIDLow()]=nil end)
-- Security G1: show() runs one query per carried item; drop a flood.
function handlers.Refresh(player)
    if DCThrottle.Allow(player, "jeweler:refresh", 5, 10) then show(player) end
end
-- Recipes, Balance, Items and Quote have no sender in the window today (it reads through
-- Refresh and Gear, and acts through DCJEWELER), so only a modified client reaches them.
-- Security G1: each reads the database, so each spends the one Refresh budget, as Gear
-- does, and a client cannot multiply its allowance by spreading a flood across them.
function handlers.Recipes(player)
    if not DCThrottle.Allow(player,"jeweler:refresh",5,10) then return end
    if valid(player,"Recipes") then AIO.Handle(player,CHANNEL,"Recipes",{recipes=recipes(player),balance=balance(player)}) end
end
function handlers.Balance(player)
    if not DCThrottle.Allow(player,"jeweler:refresh",5,10) then return end
    if valid(player,"Balance") then AIO.Handle(player,CHANNEL,"Balance",balance(player)) end
end
function handlers.Items(player)
    if not DCThrottle.Allow(player,"jeweler:refresh",5,10) or not valid(player,"Items") then return end
    local items,gems=inventory(player);AIO.Handle(player,CHANNEL,"Items",{items=items,gems=gems})
end
local function recipe(player,id)
    for _,r in ipairs(recipes(player)) do if r.id==id then return r end end
end
function handlers.Quote(player,id)
    if not DCThrottle.Allow(player,"jeweler:refresh",5,10) or not valid(player,"Quote") then return end
    local r=integer(id,1) and recipe(player,id)
    if not r then errorResponse(player,"Quote","Unknown normal-gem recipe.");return end
    local funds=balance(player)
    AIO.Handle(player,CHANNEL,"Quote",{recipe=r,balance=funds,
        affordable=r.have>=r.inputCount and DCAccount.AtLeast(funds.gold,r.gold)
            and DCAccount.AtLeast(funds.deathsBreath,r.deathsBreath)})
end
-- The window's buttons never type `.dc jeweler ...` on this half. They
-- send DCJEWELER on the bridge (docs/contracts/window-bridge.md) and C++ answers with the
-- records of what the action changed, so nothing here wraps RunCommand and the command is
-- SEC_ADMINISTRATOR.
--
-- The reply's F rows name a socketed gem by its entry and nothing else, so the gem names are
-- pushed once for the client half to label one with.
function handlers.Tables(player)
    AIO.Handle(player,CHANNEL,"Tables",{gems=gemNames,effects=effects(),legendary=legendary})
end
-- The Sockets window opens anywhere (Shift+Right-click on a socketed item),
-- so this read does not ask for the Jeweler. It names the item by where the client picked it up
-- (bag 0..4 or 255 for the character sheet, the same slots Show uses) or, for a refresh, by guid (the
-- slot then being 0), and
-- sends that one item with the bag gems. It changes nothing: every action still goes through DCJEWELER.
function handlers.Gear(player,bag,slot,guid)
    if not player:IsAlive() then return end
    local picked
    -- guid 0 means "by position": the client always sends all three numbers.
    if guid~=nil and guid~=0 then
        if not integer(guid,1) then return end
        picked=function(_,_,g) return g==guid end
    else
        if not (integer(bag,0) and bag<=255 and integer(slot,0) and slot<=255) then return end
        picked=function(b,s) return b==bag and s==slot end
    end
    -- The Refresh budget, shared: a flood of window opens costs what a flood of refreshes does. A
    -- request that is not well formed is dropped before it spends any of it.
    if not DCThrottle.Allow(player,"jeweler:refresh",5,10) then return end
    local items,gems=inventory(player,picked)
    AIO.Handle(player,CHANNEL,"Gear",{items=items,gems=gems})
end
