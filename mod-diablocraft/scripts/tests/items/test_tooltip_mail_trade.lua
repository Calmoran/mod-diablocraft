-- Mail and trade tooltip contexts (diablocraft-mail-trade-tooltip-accessors):
-- the server push built from Player:GetMailAttachment / Player:GetTradeItem
-- (core patch 0019) and the client hooks that draw it. The accessors' own
-- ownership rules are proved in C++ by core-patches/tests/test_mail_trade_readers.py;
-- this file proves the Lua side never reaches past them: it asks only the
-- caller, ignores what the client sends, and drops the request when the
-- accessors are not built in. DCT_FILE points the run at a scratch copy so a
-- mutation test never touches the live file.
-- luacheck: ignore 111 112 121 122 212 213
local serverHandlers,clientHandlers,push
local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        NextRow=function() index=index+1;return rows[index]~=nil end}
end
local function inList(query)
    local out={}
    for n in (query:match("IN %(([%d,]+)%)") or ""):gmatch("%d+") do out[#out+1]=tonumber(n) end
    return out
end
function WorldDBQuery(query)
    if query:find("FROM dc_affix_pool",1,true) then
        return result({{"legs","mainstat","Primary Attribute",0,"primary",1}})
    elseif query:find("b.entry,b.d3_name",1,true) then
        return result({{100087,"Test Legs","legs","barbarian",70,"","","Flavour",12345}})
    end
end
function CharDBQuery(query)
    local rows={}
    if query:find("FROM dc_item_instance",1,true) then
        for _,g in ipairs(inList(query)) do rows[#rows+1]={g,"rare",0} end
        return #rows>0 and result(rows) or nil
    end
    if query:find("FROM dc_item_unidentified",1,true) then return end
    for _,g in ipairs(inList(query)) do rows[#rows+1]={g,1,"mainstat",100,90,120,"primary",0,-1,0} end
    return #rows>0 and result(rows) or nil
end
function RegisterPlayerEvent() end
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) serverHandlers=h;return h end,
    AddOnInit=function() end,
    Handle=function(_,channel,name,payload) push={channel=channel,name=name,payload=payload} end}
local file=os.getenv("DCT_FILE") or "mod-diablocraft/lua/aio/dc_tooltip.lua"
-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
dofile(file)

local function item(guid)
    return {GetEntry=function() return 100087 end,GetGUIDLow=function() return guid end,
        GetUInt32Value=function() return 0 end}
end
-- A world of three players. Each one's accessors answer from that player's own
-- mail and trade only, as the core patch does; the other players' items are
-- reachable only through the other player objects.
local calls
local function player(id,mailbox,ownSide,partnerSide)
    local p={GetGUIDLow=function() return id end,GetItemByPos=function() end,
        GetSelection=function() error("the mail/trade contexts must not read the selection") end}
    p.GetMailAttachment=function(_,row,attach)
        calls=calls+1
        return mailbox[row] and mailbox[row][attach]
    end
    p.GetTradeItem=function(_,slot,partner)
        return (partner and partnerSide or ownSide)[slot]
    end
    return p
end
local A=player(1,{[1]={item(11),item(12)},[2]={item(13)}},{[0]=item(21),[6]=item(22)},{[0]=item(31)})
local B=player(2,{[1]={item(41)}},{[0]=item(31)},{[0]=item(21)})
local C=player(3,{[1]={item(51)}},{[0]=item(61)},{})
local function guids(items)
    local out={}
    for a,b in pairs(items) do
        if type(b)=="table" and b.guid then out[#out+1]=b.guid else for _,r in pairs(b) do out[#out+1]=r.guid end end
    end
    table.sort(out);return out
end

calls=0
serverHandlers.Context(A,"mail")
assert(push and push.name=="Context" and push.payload.name=="mail","mail context pushed")
local mail=push.payload.items
assert(mail[1] and mail[1][1].guid==11 and mail[1][2].guid==12,"row 1 attachments 1 and 2 keep the client's numbering")
assert(mail[2] and mail[2][1].guid==13,"row 2 attachment 1")
assert(calls==50*12,"every row and attachment is asked once, and only of the caller: "..calls)
local seen=table.concat(guids(mail),",")
assert(seen=="11,12,13","only the caller's mail is in the push, got "..seen)
-- a forged request: extra arguments (someone else's GUID, a row) change nothing
serverHandlers.Context(A,"mail",2,99)
assert(table.concat(guids(push.payload.items),",")=="11,12,13","forged arguments cannot name another mailbox")
serverHandlers.Context(C,"mail")
assert(table.concat(guids(push.payload.items),",")=="51","another player gets only their own mail")

serverHandlers.Context(A,"trade")
assert(push.payload.name=="trade","trade context pushed")
local trade=push.payload.items
assert(trade.player[1].guid==21 and trade.player[7].guid==22,"own slots 0 and 6 -> client 1 and 7")
assert(trade.target[1].guid==31 and trade.target[2]==nil,"partner slot 0 -> client 1")
serverHandlers.Context(A,"trade",3,2)
assert(push.payload.items.player[1].guid==21 and push.payload.items.target[1].guid==31,
    "forged arguments cannot name another trade")
serverHandlers.Context(C,"trade")
assert(push.payload.items.target[1]==nil,"a player whose partner offered nothing sees nothing of A's or B's trade")
local lone=player(4,{}, {}, {})
serverHandlers.Context(lone,"trade")
assert(next(push.payload.items.player)==nil and next(push.payload.items.target)==nil,"not trading: empty push")

-- Before core patch 0019 is built in the accessors do not exist: no reply at all.
local old={GetGUIDLow=function() return 9 end,GetItemByPos=function() end}
push=false
serverHandlers.Context(old,"mail");assert(push==false,"no GetMailAttachment: request dropped")
serverHandlers.Context(old,"trade");assert(push==false,"no GetTradeItem: request dropped")

-- --- client half ---------------------------------------------------------------
local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024,768)
local owner
local sent={}
AIO={AddAddon=function() return false end,AddHandlers=function(_,h) clientHandlers=h;return h end,
    Handle=function(_,message,name) sent[#sent+1]=message..":"..tostring(name) end}
MerchantFrame={selectedTab=1}
InboxFrame={openMailID=1}
function GetNumBuybackItems() return 0 end
unpack=unpack or table.unpack
SlashCmdList={}
DEFAULT_CHAT_FRAME={AddMessage=function() end}
GameTooltipTextLeft1={GetText=function() return "Legs" end}
dofile(file)
local hooks=GameTooltip.scripts
-- The context watcher is the frame that registered TRADE_SHOW; its OnEvent and
-- OnUpdate are the coalescing ask kicker and pump the test drives.
local contextWatcher
for _,f in ipairs(Mock.frames) do
    if f.events and f.events.TRADE_SHOW then contextWatcher=f end
end
local watcherScript=contextWatcher.scripts.OnEvent
local pumpScript=contextWatcher.scripts.OnUpdate

local function hover(name,extra)
    owner={GetName=function() return name end,GetID=function() return 1 end}
    for k,v in pairs(extra or {}) do owner[k]=v end
    GameTooltip.owner=owner
    GameTooltip:ClearLines();hooks.OnTooltipCleared(GameTooltip)
    -- The client's tooltip carries only its title line here (NumLines 1).
    GameTooltip.lines={""}
    hooks.OnTooltipSetItem(GameTooltip)
    return table.concat(GameTooltip.lines,"\n")
end
serverHandlers.Context(A,"mail");clientHandlers.Context(nil,push.payload)
assert(hover("MailItem1Button",{index=1}):find("+100 Strength",1,true) and GameTooltip.dcGuid==11,"inbox row button draws attachment 1 of its row")
assert(hover("MailItem2Button",{index=2}):find("Test Legs",1,true),"row 2 draws")
assert(not hover("MailItem3Button",{index=3}):find("Test Legs",1,true),"a row with no record keeps its base shell")
InboxFrame.openMailID=1
assert(hover("OpenMailAttachmentButton2"):find("Test Legs",1,true) and GameTooltip.dcGuid==12,"open letter attachment 2 draws")
InboxFrame.openMailID=2
assert(not hover("OpenMailAttachmentButton2"):find("Test Legs",1,true),"a different open letter has no attachment 2")
serverHandlers.Context(A,"trade");clientHandlers.Context(nil,push.payload)
assert(hover("TradePlayerItem1ItemButton"):find("Test Legs",1,true) and GameTooltip.dcGuid==21,"own trade slot 1 draws the caller's item")
assert(hover("TradePlayerItem7ItemButton"):find("Test Legs",1,true),"the non-traded slot draws")
assert(hover("TradeRecipientItem1ItemButton"):find("Test Legs",1,true) and GameTooltip.dcGuid==31,"the partner's slot 1 draws the partner's item")
assert(not hover("TradeRecipientItem2ItemButton"):find("Test Legs",1,true),"an empty partner slot keeps its base shell")
-- the trade window closing drops the pushed items
watcherScript(nil,"TRADE_CLOSED")
assert(not hover("TradePlayerItem1ItemButton"):find("Test Legs",1,true),"a closed trade leaves nothing to draw")
watcherScript(nil,"MAIL_CLOSED")
assert(not hover("MailItem1Button",{index=1}):find("Test Legs",1,true),"a closed mailbox leaves nothing to draw")
-- The frames ask on open and on change, coalesced (UI fixes row 11, Security G1): one ask
-- per context once its events have been quiet for .3 s, so the server's bucket never sees
-- one per event and the last change is always the one asked for.
sent={}
watcherScript(nil,"MAIL_SHOW");watcherScript(nil,"MAIL_INBOX_UPDATE")
watcherScript(nil,"TRADE_SHOW");watcherScript(nil,"TRADE_TARGET_ITEM_CHANGED")
pumpScript(nil,.2)
assert(#sent==0,"nothing is asked while the events are still coming: "..table.concat(sent,","))
watcherScript(nil,"TRADE_UPDATE")
pumpScript(nil,.2)
assert(#sent==0,"a later event restarts the quiet period: "..table.concat(sent,","))
pumpScript(nil,.2)
table.sort(sent)
assert(table.concat(sent,",")=="Context:mail,Context:trade","one ask per context: "..table.concat(sent,","))
sent={}
pumpScript(nil,1)
assert(#sent==0,"an ask is sent once")
watcherScript(nil,"MAIL_SHOW");watcherScript(nil,"MAIL_CLOSED")
watcherScript(nil,"TRADE_SHOW");watcherScript(nil,"TRADE_CLOSED")
pumpScript(nil,1)
assert(#sent==0,"a window closed before its ask went out asks for nothing: "..table.concat(sent,","))
print("PASS: mail and trade pushes read only the caller, drop without the accessors, and draw on their frames")
