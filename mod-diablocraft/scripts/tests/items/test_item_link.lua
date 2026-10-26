-- Shared item links, option B (decisions.md 2026-09-26 and the same-day limits
-- ruling). Exercises the real server half: Link freezes a carried or own-stash
-- item under a random code, reuses the code while the item is unchanged, rate
-- limits NEW links, caps the store oldest-first, and refuses a GUID the caller
-- does not own. The client half is exercised against stubs: LinkResult builds a
-- dclink, SetItemRef fetches once and draws the frozen copy, a dropped link
-- says "This item link has expired". Real second-client rendering is unverified.
-- luacheck: globals DCRequestItemLink SetItemRef DCAccount HandleModifiedItemClick
-- luacheck: ignore 111 121 122 212 213
local serverHandlers,clientHandlers
local sent={}
local affixRows={
    {87,1,"mainstat",432,416,500,"primary",0,-1,0},
    {87,2,"resall",90,86,90,"secondary",0,-1,0},
}
local rowsByGuid={}
local STASH_GUID=777
local SHELL_GUID=555
local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        NextRow=function() index=index+1;return rows[index]~=nil end}
end
local function affixFor(guid)
    if guid==87 then return affixRows end
    if guid==SHELL_GUID then return {} end
    return rowsByGuid[guid] or {{guid,1,"mainstat",432,416,500,"primary",0,-1,0}}
end
function WorldDBQuery(query)
    if query:find("FROM dc_affix_pool",1,true) then
        return result({{"legs","mainstat","Primary Attribute",0,"primary",1},
            {"legs","resall","All Resistance",0,"secondary",2}})
    elseif query:find("FROM dc_skill_affix",1,true) then return result({{"skill_x","Bash Damage","skill_legs"}})
    elseif query:find("b.entry,b.d3_name",1,true) then return result({{100087,"Test Legs","legs","barbarian",70,"test","","Flavour",12345}})
    elseif query:find("FROM item_template WHERE spellid_1=81203",1,true) then return result({{199900}})
    elseif query:find("FROM item_template WHERE entry=100087",1,true) then return result({{4,"Test Legs Template"}})
    elseif query:find("FROM dc_item_preset_range",1,true) or query:find("FROM dc_affix_metadata",1,true) then return nil -- no preset-only lines here
    elseif query:find("FROM dc_legendary_gem_item",1,true) then return nil
    elseif query:find("FROM dc_gem_item",1,true) then return result({{103000,"Ruby","other","str",100}})
    elseif query:find("FROM dc_set_tooltip",1,true) then return result({{"test","Test Set"}})
    elseif query:find("FROM dc_set_bonus",1,true) then return result({{"test",2,"Test bonus"}})
    elseif query:find("dc_legendary_power",1,true) then return nil
    elseif query:find("SELECT DISTINCT",1,true) then return result({{"test","Test Legs"}})
    end
    error(query)
end
function CharDBQuery(query)
    if query:find("FROM dc_account_stash_item",1,true) then
        local guid=tonumber(query:match("item_guid=(%d+)"))
        if guid==STASH_GUID then return result({{100087}}) end
        return nil
    end
    if query:find("FROM dc_item_instance",1,true) then
        local guid=tonumber(query:match("IN %((%d+)") or "87")
        if guid==SHELL_GUID then return nil end
        return result({{guid,"rare",1,guid==87 and "primal" or "normal"}})
    end
    if query:find("FROM dc_item_unidentified",1,true) then
        assert(query:match("IN %((%d+)")==tostring(SHELL_GUID))
        return result({{SHELL_GUID,"legendary","primal"}})
    end
    assert(query:find("FROM dc_item_affix",1,true))
    local guid=tonumber(query:match("IN %((%d+)") or "87")
    local rows=affixFor(guid)
    return #rows>0 and result(rows) or nil
end
function RegisterPlayerEvent() end
-- dc_account.lua is its own tested file; stub the one call dc_tooltip makes.
DCAccount={Principal=function(player) return player:GetAccountId(),"normal" end}
local function itemFor(guid)
    -- The shell is its own template (199900, Identify on use), never a dc_base_item row, as in game.
    return {GetEntry=function() return guid==SHELL_GUID and 199900 or 100087 end,GetGUIDLow=function() return guid end,
        GetUInt32Value=function(_,field) return (field==0x3C or field==0x3D) and 60 or 0 end}
end
local function carrier(guid,playerGuid)
    return {GetGUIDLow=function() return playerGuid or 1 end,GetAccountId=function() return playerGuid or 1 end,
        GetItemByPos=function(_,bag,slot) if bag==255 and slot==0 then return itemFor(guid) end end}
end
local function bystander(playerGuid)
    return {GetGUIDLow=function() return playerGuid or 1 end,GetAccountId=function() return playerGuid or 1 end,
        GetItemByPos=function() end}
end
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) serverHandlers=h;return h end,
    AddOnInit=function() end,Handle=function(_,_,name,...)
        if name=="SnapshotResult" then local code,record=...;sent[name]={code=code,record=record}
        else sent[name]=... end
    end}
-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
dofile("mod-diablocraft/lua/aio/dc_tooltip.lua")
assert(type(serverHandlers.Link)=="function" and type(serverHandlers.Snapshot)=="function")

-- Link freezes a carried item under a 128-bit hex code, never a GUID.
serverHandlers.Link(carrier(87),87)
local first=sent.LinkResult
assert(first and first.ok,"a carried rolled item links")
assert(type(first.code)=="string" and #first.code==32 and first.code:match("^%x+$"),
    "a 32-hex-char code, got "..tostring(first and first.code))
assert(first.name=="Test Legs" and first.rarity=="rare")
assert(first.quality=="primal","LinkResult carries the quality (diablocraft-ipc7), got "..tostring(first.quality))
-- diablocraft-8ghio: the core's link check drops any chat link whose tag it does not know, so the link is a native item link.
-- Its colour must be the template Quality's and its text the template name, which the core checks; both come from item_template.
assert(first.entry==100087 and first.itemQuality==4 and first.itemName=="Test Legs Template",
    "LinkResult carries the template entry, Quality and name the core's item link check wants, got "..tostring(first.entry).."/"..tostring(first.itemQuality).."/"..tostring(first.itemName))
serverHandlers.Snapshot(bystander(),first.code)
assert(sent.SnapshotResult and sent.SnapshotResult.code==first.code)
local copy=sent.SnapshotResult.record
assert(copy and copy.guid==nil,"the frozen copy carries no sender GUID")
assert(copy.entry==100087 and copy.name=="Test Legs" and copy.rarity=="rare")
local found=false
for _,a in ipairs(copy.affixes) do if a.id=="mainstat" and a.value==432 then found=true end end
assert(found,"the copy carries the rolled rows")
assert(copy.set and copy.set.name=="Test Set")
assert(copy.quality=="primal","the copy carries dc_item_instance.quality_tier, got "..tostring(copy.quality))

-- An unidentified shell carries its quality too (decisions.md 2026-10-10, quality
-- shows before identify): dc_item_unidentified.quality_tier, nothing else it will become.
serverHandlers.Refresh(carrier(SHELL_GUID))
local shell=sent.Set[255][0]
assert(shell.unidentified and shell.name=="Unidentified" and shell.rarity=="legendary","the bag record is the shell")
assert(shell.quality=="primal","the shell record carries dc_item_unidentified.quality_tier, got "..tostring(shell.quality))
assert(shell.entry==nil and #shell.affixes==0,"the shell still sends nothing it will become")

-- A second link after the item changes is a different code with the new rows;
-- the first code still opens the OLD rows (frozen at its link time).
affixRows={{87,1,"mainstat",999,416,500,"primary",0,-1,0}}
serverHandlers.Link(carrier(87),87)
local second=sent.LinkResult
assert(second.ok and second.code~=first.code,"a rerolled item links under a new code")
serverHandlers.Snapshot(bystander(),first.code)
local old=sent.SnapshotResult.record
local oldValue
for _,a in ipairs(old.affixes) do if a.id=="mainstat" then oldValue=a.value end end
assert(oldValue==432,"the first snapshot still shows 432 after the item became 999")

-- Relinking the SAME unchanged item reuses its code and spends no allowance.
serverHandlers.Link(carrier(87),87)
assert(sent.LinkResult.code==second.code,"an unchanged relink reuses the existing code")

-- A new link per distinct item, 10 allowed and the 11th refused exactly.
for i=1,10 do serverHandlers.Link(carrier(6000+i,5000),6000+i) end
assert(sent.LinkResult.ok,"the tenth new link is allowed")
serverHandlers.Link(carrier(6011,5000),6011)
assert(sent.LinkResult.ok==false and sent.LinkResult.message=="Linking too fast",
    "the eleventh new link in a minute is refused, got "..tostring(sent.LinkResult.message))

-- An item in the caller's OWN account/mode stash links (server-side ownership,
-- never the client GUID alone); a guid not in the stash is refused.
serverHandlers.Link(bystander(7000),STASH_GUID)
assert(sent.LinkResult.ok and sent.LinkResult.name=="Test Legs","an own-stash item links")
assert(sent.LinkResult.code~=first.code,"the carried and stash codes differ")
serverHandlers.Link(bystander(7000),888)
assert(sent.LinkResult.ok==false,"a guid not carried and not in the stash is refused")

-- Refusals: a GUID the player does not carry, an unknown code answers false,
-- and a malformed code is not even looked up.
serverHandlers.Link(bystander(1),999)
assert(sent.LinkResult.ok==false and type(sent.LinkResult.message)=="string")
sent.SnapshotResult=nil
serverHandlers.Snapshot(bystander(),"deadbeef")
assert(sent.SnapshotResult and sent.SnapshotResult.record==false,"an unknown/expired code answers false")
sent.SnapshotResult="sentinel"
serverHandlers.Snapshot(bystander(),"not a code")
assert(sent.SnapshotResult=="sentinel","a malformed code is not looked up")

-- The store holds at most 50000 snapshots and drops the oldest first. 55000
-- inserts force 5000 evictions and several compaction cycles of the dead queue
-- prefix, which is where a length-operator queue broke. Each iteration is a
-- fresh player, so the per-player rate limit never applies.
local CAP_TOTAL=55000
local capCode={}
for i=1,CAP_TOTAL do
    local guid=100000+i
    serverHandlers.Link(carrier(guid,1000000+i),guid)
    if not sent.LinkResult.ok then error("cap fill refused at "..i..": "..tostring(sent.LinkResult.message)) end
    if i==1 or i==4000 or i==6000 or i==CAP_TOTAL then capCode[i]=sent.LinkResult.code end
end
local function evicted(code)
    sent.SnapshotResult=nil
    serverHandlers.Snapshot(bystander(),code)
    return sent.SnapshotResult and sent.SnapshotResult.record==false
end
local function held(code)
    sent.SnapshotResult=nil
    serverHandlers.Snapshot(bystander(),code)
    return sent.SnapshotResult and sent.SnapshotResult.record~=false
end
-- 55000 inserts leave the newest 50000, so the first 5000 codes are dropped.
assert(evicted(capCode[1]),"the very first snapshot is evicted")
assert(evicted(capCode[4000]),"the 4000th snapshot is evicted (cap held, not exceeded)")
assert(held(capCode[6000]),"the 6000th survives")
assert(held(capCode[CAP_TOTAL]),"the newest snapshot survives the evictions")

-- ---------------------------------------------------------------- client half
local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024,768)
local tooltip=Mock.widget("GameTooltip","ItemRefTooltip")
local inserted
local messages={}
AIO={AddAddon=function() return false end,AddHandlers=function(_,h) clientHandlers=h;return h end,
    Handle=function(_,name,...) sent[name]=... end}
ShowUIPanel=function() end
HandleModifiedItemClick=function(link) inserted=link end
local stockCalls={}
SetItemRef=function(link) stockCalls[#stockCalls+1]=link end
IsModifiedClick=function() return false end
unpack=unpack or table.unpack
SlashCmdList={}
DEFAULT_CHAT_FRAME={AddMessage=function(_,message) messages[#messages+1]=message end}
dofile("mod-diablocraft/lua/aio/dc_tooltip.lua")
assert(type(clientHandlers.LinkResult)=="function" and type(DCRequestItemLink)=="function")

-- diablocraft-8ghio: LinkResult builds a native item link the core's link check accepts (tag item, the template's Quality colour and
-- name, the entry): the 128-bit code rides in the four free uint32 fields (enchant and the first three gems), the unique and the
-- level field stay 0 (the core refuses a unique without a suffix, and a stock link carries the level), and no item or character id.
local code="a1b2c3d4e5f60718293a4b5c6d7e8f90"
clientHandlers.LinkResult(nil,{ok=true,code=code,name="Test Legs",rarity="rare",entry=100087,itemQuality=3,itemName="Test Legs Template"})
assert(inserted=="|cff0070dd|Hitem:100087:2712847316:3858106136:691686236:1837010832:0:0:0:0|h[Test Legs Template]|h|r",
    "the link is a native item link carrying the code, got "..tostring(inserted))
assert(not inserted:find("dclink",1,true),"no tag the core's link check would drop")
-- The colour is the template Quality's whatever the rarity or the Primal tier (the core checks it), not the D3 palette.
clientHandlers.LinkResult(nil,{ok=true,code=code,name="Test Legs",rarity="legendary",quality="primal",entry=100087,itemQuality=5,itemName="Test Legs Template"})
assert(inserted:find("^|cffff8000|Hitem:100087:"),"a Primal link keeps the template Quality colour, got "..tostring(inserted))
-- A reply that cannot name the template draws no link and says so.
inserted=nil
clientHandlers.LinkResult(nil,{ok=true,code=code,name="Test Legs",rarity="rare"})
assert(inserted==nil and messages[#messages]=="Torment: That item cannot be linked.","a reply without the template is not inserted, got "..tostring(messages[#messages]))
-- Values past 2^31 survive a 32-bit client: the four words are never run through %d or %x.
clientHandlers.LinkResult(nil,{ok=true,code="ffffffff00000000fffffffe00000001",name="x",rarity="rare",entry=100087,itemQuality=0,itemName="Test Legs Template"})
assert(inserted=="|cff9d9d9d|Hitem:100087:4294967295:0:4294967294:1:0:0:0:0|h[Test Legs Template]|h|r","the full uint32 range, got "..tostring(inserted))

-- Activating it fetches once and draws the frozen copy; a second activation
-- draws from the cache with no second request.
sent.Snapshot=nil
local carried="item:100087:2712847316:3858106136:691686236:1837010832:0:0:0:0"
SetItemRef(carried)
assert(sent.Snapshot==code,"the first activation asks for the snapshot")
clientHandlers.SnapshotResult(nil,code,{entry=100087,name="Test Legs",rarity="rare",level=70,sell=12345,
    bound=false,durability=0,maxDurability=0,
    affixes={{seq=1,id="mainstat",name="Strength",value=432,min=416,max=500,kind="primary",order=1}}})
local text=table.concat(tooltip.lines,"\n")
assert(text:find("Strength",1,true),"the frozen row is drawn")
assert(text:find("432",1,true),"with its rolled value")
sent.Snapshot="unset"
SetItemRef(carried)
assert(sent.Snapshot=="unset","the cached copy draws without another request")
-- A stock item link (and the retired dclink, which the core drops anyway) goes to the stock handler and asks for nothing.
SetItemRef("item:100087:0:0:0:0:0:0:0:70")
SetItemRef("dclink:"..code)
assert(sent.Snapshot=="unset","a stock or retired link asks for no snapshot")
assert(stockCalls[#stockCalls-1]=="item:100087:0:0:0:0:0:0:0:70" and stockCalls[#stockCalls]=="dclink:"..code,"and reaches the stock handler")

-- diablocraft-8ghio: shift-clicking a bag or worn item into an open chat box sends the stock item link; the addon asks for
-- ours instead (the stock link names the base item only), and leaves every other click to the stock handler.
local stockLink="|cffffffff|Hitem:100087:0:0:0:0:0:0:0:70|h[Test Legs Template]|h|r"
local chatOpen,chatClick,focus=true,true,nil
ChatEdit_GetActiveWindow=function() return chatOpen and {} or nil end
IsModifiedClick=function(name) return name=="CHATLINK" and chatClick end
GetMouseFocus=function() return focus end
local function bagButton(bag,slot) return {GetName=function() return "ElvUIBagFrameBag"..bag.."Slot"..slot end,GetID=function() return slot end,bagID=bag,slotID=slot} end
clientHandlers.Set(nil,{[0]={[8]={guid=87,entry=100087,name="Test Legs",rarity="rare",affixes={}},
    [9]={guid=88,unidentified=true,name="Unidentified",rarity="legendary",affixes={}}},[5]={[1]={guid=89,entry=100087,name="Test Legs",rarity="rare",affixes={}}},[255]={}})
local function click(button,link)
    inserted,sent.Link=nil,nil
    focus=button
    return HandleModifiedItemClick(link or stockLink)
end
assert(click(bagButton(0,8))==true and sent.Link==87 and inserted==nil,"a rolled bag item asks the server for its link, not the stock one, got "..tostring(sent.Link))
click(bagButton(0,8),"|cffffffff|Hspell:1|h[x]|h|r")
assert(sent.Link==nil and inserted~=nil,"a link that is not an item link is the stock handler's")
chatOpen=false;click(bagButton(0,8))
assert(sent.Link==nil and inserted==stockLink,"no open chat box leaves the click to the stock handler (it splits a stack)")
chatOpen,chatClick=true,false;click(bagButton(0,8))
assert(sent.Link==nil and inserted==stockLink,"another modified click is the stock handler's")
chatClick=true
click(bagButton(0,9));assert(sent.Link==nil and inserted==stockLink,"an unidentified shell cannot be linked, so the stock link goes in")
click(bagButton(0,3));assert(sent.Link==nil and inserted==stockLink,"a button with no rolled record is a stock item")
click(bagButton(5,1));assert(sent.Link==nil and inserted==stockLink,"a bank cell is not the caller's carried item")
click(nil);assert(sent.Link==nil and inserted==stockLink,"nothing under the mouse")
-- The worn paper-doll slot, the stock button name Character<Slot> with the 1-based slot id.
clientHandlers.Set(nil,{[255]={[6]={guid=91,entry=100087,name="Test Legs",rarity="rare",affixes={}}}})
click({GetName=function() return "CharacterLegsSlot" end,GetID=function() return 7 end})
assert(sent.Link==91,"a worn rolled item is linked the same way, got "..tostring(sent.Link))

-- Ancient / Primal Ancient (diablocraft-vf6n): a green tag line directly under the
-- name, nothing for normal or a record with no quality; dcQualityTier mirrors the
-- record for TooltipBorder.lua and is cleared by a record without one.
GREEN_FONT_COLOR={r=.1,g=1,b=.1}
-- A stock "Legs" line the client drew under the name, so the tag's place is above it.
ItemRefTooltipTextLeft2={GetText=function() return "Legs" end}
local stockHyperlink=tooltip.SetHyperlink
local function drawQuality(tag,quality)
    tooltip.dcGuid=nil;tooltip.SetHyperlink=function(self) self.lines={"Test Legs","Legs"} end
    clientHandlers.SnapshotResult(nil,tag..code:sub(#tag+1),{entry=100087,name="Test Legs",rarity="legendary",level=70,
        sell=1,bound=false,durability=0,maxDurability=0,affixes={},quality=quality})
    return tooltip.lines,tooltip.lineColors,tooltip.dcQualityTier
end
local lines,colors,tier=drawQuality("a1","ancient")
assert(lines[1]=="Test Legs" and lines[2]=="Ancient" and lines[3]=="Legs","Ancient sits directly under the name, got "..table.concat(lines,"/"))
assert(colors[2][1]==.1 and colors[2][2]==1 and colors[2][3]==.1,"the tag is GREEN_FONT_COLOR")
assert(tier=="ancient")
assert(colors[1][1]==1 and colors[1][2]==.5 and colors[1][3]==0,"an Ancient keeps the legendary orange name")
lines,colors,tier=drawQuality("b2","primal")
assert(lines[2]=="Primal Ancient" and colors[2][2]==1 and colors[2][1]==.1 and tier=="primal","Primal Ancient, green, tier primal")
assert(colors[1][1]==1 and colors[1][2]==.1 and colors[1][3]==.1,"a Primal's name in the link tooltip is red")
for _,quality in ipairs({"normal",false}) do
    lines,_,tier=drawQuality(quality and "c3" or "d4",quality or nil)
    assert(lines[2]=="Legs","no tag line for "..tostring(quality)..", got "..table.concat(lines,"/"))
    assert(tier==(quality or nil),"dcQualityTier is the record's quality, nil when absent, got "..tostring(tier))
end
-- An unidentified shell draws the same tag and tier (decisions.md 2026-10-10).
tooltip.dcGuid=nil;tooltip.SetHyperlink=function(self) self.lines={"Unidentified","Legs"} end
clientHandlers.SnapshotResult(nil,"e5"..code:sub(3),{name="Unidentified",rarity="legendary",unidentified=true,
    affixes={},owned={},quality="primal"})
assert(tooltip.lines[1]=="Unidentified" and tooltip.lines[2]=="Primal Ancient" and tooltip.lineColors[2][2]==1,
    "a Primal shell shows the green tag under its name, got "..table.concat(tooltip.lines,"/"))
assert(tooltip.dcQualityTier=="primal","a Primal shell sets dcQualityTier for the red border")
tooltip.SetHyperlink=stockHyperlink

-- The exact refusals: rate limit and a dropped link.
clientHandlers.LinkResult(nil,{ok=false,message="Linking too fast"})
assert(messages[#messages]=="Torment: Linking too fast","rate limit says exactly Linking too fast, got "..tostring(messages[#messages]))
clientHandlers.SnapshotResult(nil,"deadbeef",false)
assert(messages[#messages]=="Torment: This item link has expired","a dropped link says exactly This item link has expired, got "..tostring(messages[#messages]))

print("PASS: item link snapshots, reuse, per-player rate limit, 50000 cap oldest-first past 55000 inserts, carried and own-stash ownership, random codes, freezing, client link/fetch/draw, the Ancient / Primal Ancient tag line and dcQualityTier (shells too), and exact messages")
