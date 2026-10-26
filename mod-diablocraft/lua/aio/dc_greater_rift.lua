-- dc_greater_rift.lua - the Greater Rift opening window and the ready-check window. Contract:
-- docs/contracts/rift-enrollment-messages.md (DCRIFTENROLL on the window bridge).
--
-- 1. Opening (`L`): a list of the levels this character can open (start..unlocked, the highest
--    selected), its Keystone count and an Open button; Enter does what Open does. It stays up on a
--    refusal, closes when the ready check opens, and closes on walk-away (`C`, the server's range
--    watch, as the Mystic's).
-- 2. Ready check (`P`): every member, the opener included, gets the level, who opened it, each
--    member's status, the countdown and Accept / Decline. It stays up until the server's `T`;
--    a cancel shows the server's own words.
--
-- The server decides everything (09-rifts 7.9.4): the client sends only the level picked and
-- Accept / Decline. Nothing here starts, cancels or times out a ready check: at local zero the
-- window only waits for the server. The look is the stock window kit (dc_aio_ui.lua, DCUI;
-- no D3 skin). Nothing here runs on the server.
-- luacheck: globals DCGreaterRift DCUI GetBindingFromClick RunBinding
local AIO=AIO or require("AIO")
if AIO.AddAddon() then return end

local PREFIX="DCRIFTENROLL"
local U=DCUI or error("dc_aio_ui.lua must load before dc_greater_rift.lua")
DCGreaterRift={}
local G=DCGreaterRift
local Logic={};G.Logic=Logic

------------------------------------------------------------------------------------------------
-- The logic, with no frame in it
------------------------------------------------------------------------------------------------
Logic.STATUS={waiting="Waiting",accepted="Accepted",declined="Declined"}
Logic.WAITING_SERVER="Waiting for the server..."
Logic.ACCEPTED="Accepted. Waiting for the party."

function Logic.split(body)
    local fields={}
    for field in (body.."|"):gmatch("(.-)|") do fields[#fields+1]=field end
    return fields
end

-- `L|start|unlocked|keystones|cost`: the levels start..unlocked, highest first, and the one to select.
function Logic.levels(start,unlocked)
    start,unlocked=tonumber(start),tonumber(unlocked)
    local out={}
    if start and unlocked then for level=unlocked,math.max(start,1),-1 do out[#out+1]=level end end
    return out,out[1]
end

-- `P|id|revision|GR|level|openerGuid|openerName|remainingMs|n|guid|name|status...`, or nil when it
-- does not read as one.
function Logic.proposal(f)
    local n=tonumber(f[9])
    if f[1]~="P" or not tonumber(f[2]) or not tonumber(f[3]) or not n or #f~=9+3*n then return end
    local p={id=f[2],revision=tonumber(f[3]),level=f[5],openerName=f[7],remainingMs=tonumber(f[8]) or 0,roster={}}
    for i=0,n-1 do p.roster[#p.roster+1]={guid=f[10+3*i],name=f[11+3*i],status=f[12+3*i]} end
    return p
end

-- Whole seconds left: the server's remainingMs at send, less the time since it arrived, rounded up.
-- Never below 0; 0 means the server's deadline has passed by our clock.
function Logic.seconds(remainingMs,since)
    local left=(tonumber(remainingMs) or 0)/1000-(since or 0)
    return left>0 and math.ceil(left) or 0
end

-- Whether a P is drawn: never for an id that got a T, never an older or repeated revision of
-- the one on screen. Another id replaces the one on screen.
function Logic.fresh(current,p,finished)
    if finished[p.id] then return false end
    if current and current.id==p.id then return p.revision>current.revision end
    return true
end

function Logic.statusOf(p,name)
    for _,member in ipairs(p.roster) do if member.name==name then return member.status end end
end

-- Whether Accept / Decline can be clicked, and the line under the roster. `pending` is true between
-- our click and the server's next P or T; `left` is Logic.seconds.
function Logic.controls(p,me,pending,left)
    local mine=Logic.statusOf(p,me)
    if mine=="accepted" then return false,Logic.ACCEPTED end
    if mine~="waiting" then return false,"" end
    if left<=0 then return false,Logic.WAITING_SERVER end
    return not pending,""
end

------------------------------------------------------------------------------------------------
-- The wire
------------------------------------------------------------------------------------------------
-- What the last request was, so a refusal (X) lands on the window that asked.
local asked
local function send(verb,...)
    asked=verb
    local body=table.concat({verb,...},"\t")
    SendAddonMessage(PREFIX,body,"WHISPER",UnitName("player"))
end

------------------------------------------------------------------------------------------------
-- 1. The opening window
------------------------------------------------------------------------------------------------
local ROWS=12
local open=U.window("TormentGreaterRiftOpenFrame",300,400,"greater-rift")
U.title(open,"Greater Rift")
local openSub=U.subtitle(open,"Choose a level")
U.close(open)
local keystones=U.text(open,24,-66,252)
local listBox=CreateFrame("Frame",nil,open)
listBox:SetPoint("TOPLEFT",20,-88);listBox:SetSize(260,ROWS*U.ROW_HEIGHT+8)
U.flat(listBox,U.DETAIL_BG[1],U.DETAIL_BG[2],U.DETAIL_BG[3],U.DETAIL_BORDER[1],U.DETAIL_BORDER[2],U.DETAIL_BORDER[3])
local scroll=U.scroll(CreateFrame("ScrollFrame","TormentGreaterRiftLevelScroll",listBox,"UIPanelScrollFrameTemplate"))
scroll:SetPoint("TOPLEFT",4,-4);scroll:SetSize(228,ROWS*U.ROW_HEIGHT)
local list=CreateFrame("Frame",nil,scroll);list:SetSize(228,ROWS*U.ROW_HEIGHT);scroll:SetScrollChild(list)
local openNote=U.text(open,24,-104-ROWS*U.ROW_HEIGHT,252,"GameFontHighlightSmall","CENTER")
U.colour(openNote,U.RED)
local levels,selected,rows={},nil,{}

local function renderLevels()
    for i,level in ipairs(levels) do
        local row=rows[i]
        if not row then
            row=U.row(list);row:SetWidth(228);row:SetPoint("TOPLEFT",0,-(i-1)*U.ROW_HEIGHT)
            row.label:SetPoint("LEFT",U.HEAD_INDENT,0)
            row:SetScript("OnClick",function(self) selected=self.level;renderLevels() end)
            rows[i]=row
        end
        row.level=level
        row.label:SetText("Greater Rift "..level)
        if level==selected then row.mark:Show() else row.mark:Hide() end
        row:Show()
    end
    for i=#levels+1,#rows do rows[i]:Hide() end
    list:SetHeight(math.max(1,#levels)*U.ROW_HEIGHT)
end

function G.Open()
    if not selected or not open:IsShown() then return end
    openNote:SetText("")
    send("open",tostring(selected))
end
local openButton=U.button(open,120,"Open",function() G.Open() end)
U.anchor(open,"buttons",{openButton})
openButton:SetPoint("BOTTOM",0,22)

-- Stock popups take the keyboard while they are up (StaticPopup_OnKeyDown): Enter is Open, the game
-- menu key closes the window, a screenshot still works.
open:EnableKeyboard(true)
open:SetScript("OnKeyDown",function(self,key)
    local action=GetBindingFromClick(key)
    if key=="ENTER" then G.Open()
    elseif action=="TOGGLEGAMEMENU" then self:Hide()
    elseif action=="SCREENSHOT" then RunBinding("SCREENSHOT") end
end)

function G.ShowLevels(f)
    levels,selected=Logic.levels(f[2],f[3])
    keystones:SetText("Greater Rift Keystones: "..U.number(f[4]))
    openSub:SetText(#levels>0 and "Choose a level" or "No Greater Rift level is open to you yet.")
    openNote:SetText("")
    if selected then openButton:Enable() else openButton:Disable() end
    scroll:SetVerticalScroll(0)
    renderLevels()
    open:Show()
end

------------------------------------------------------------------------------------------------
-- 2. The ready-check window
------------------------------------------------------------------------------------------------
-- No X while it waits. Escape is Decline: closing it while this
-- player can still answer sends what the Decline button sends. Once answered (or at local zero) Escape only hides
-- it, and the server's next P or T shows it again. After a cancel its Close button takes it away.
local MAX_ROSTER=5 -- a WoW party; the server's party cap decides who is on the roster
local ready=CreateFrame("Frame","TormentGreaterRiftReadyFrame",UIParent)
ready.dcWidth=320
ready:SetSize(320,190+MAX_ROSTER*U.ROW_HEIGHT);ready:SetPoint("CENTER",0,120);ready:Hide()
ready:SetMovable(true);ready:EnableMouse(true);ready:SetFrameStrata("DIALOG")
U.backdrop(ready)
ready:RegisterForDrag("LeftButton");ready:SetScript("OnDragStart",ready.StartMoving);ready:SetScript("OnDragStop",ready.StopMovingOrSizing)
table.insert(UISpecialFrames,"TormentGreaterRiftReadyFrame")
U.title(ready,"Greater Rift Ready Check")
local levelLine=U.text(ready,24,-50,272)
local leaderLine=U.text(ready,24,-70,272)
local timeLine=U.text(ready,24,-90,272)
local members={}
for i=1,MAX_ROSTER do
    members[i]={name=U.text(ready,32,-116-(i-1)*U.ROW_HEIGHT,160),
        status=U.text(ready,192,-116-(i-1)*U.ROW_HEIGHT,100,"GameFontHighlight","RIGHT")}
end
local note=U.text(ready,24,-124-MAX_ROSTER*U.ROW_HEIGHT,272,"GameFontNormal","CENTER")
note:SetHeight(40)
local STATUS_COLOUR={waiting=U.GREY,accepted=U.GOLD,declined=U.RED}

-- `current` is the P on screen (with `result`, the T, once one came, and `error`, the last refusal).
local current,received,pending,finished=nil,0,false,{}

local function respond(decision)
    if not current then return end
    pending=true
    send("respond",current.id,decision)
    G.Render()
end
local accept=U.button(ready,110,"Accept",function() respond("accept") end)
accept:SetPoint("BOTTOMRIGHT",ready,"BOTTOM",-6,22)
local decline=U.button(ready,110,"Decline",function() respond("decline") end)
decline:SetPoint("BOTTOMLEFT",ready,"BOTTOM",6,22)
local closeButton=U.button(ready,110,"Close",function() ready:Hide() end)
closeButton:SetPoint("BOTTOM",0,22);closeButton:Hide()
-- Every way the window is hidden comes here; its own hides (started, Close after a cancel) come when no answer is
-- open, so only Escape on an open answer declines.
ready:SetScript("OnHide",function()
    if not current or current.result then return end
    local left=Logic.seconds(current.remainingMs,GetTime()-received)
    if Logic.controls(current,UnitName("player"),pending,left) then respond("decline") end
end)

function G.Render()
    if not current then return end
    levelLine:SetText("Greater Rift "..current.level)
    leaderLine:SetText("Leader: "..current.openerName)
    for i,row in ipairs(members) do
        local member=current.roster[i]
        row.name:SetText(member and member.name or "")
        row.status:SetText(member and (Logic.STATUS[member.status] or member.status) or "")
        U.colour(row.status,member and STATUS_COLOUR[member.status] or U.WHITE)
    end
    if current.result then
        timeLine:SetText("")
        note:SetText(current.result.message)
        if current.result.state=="cancelled" then accept:Hide();decline:Hide();closeButton:Show()
        else accept:Disable();decline:Disable() end
        return
    end
    local left=Logic.seconds(current.remainingMs,GetTime()-received)
    timeLine:SetText("Time remaining: "..left.." s")
    local can,text=Logic.controls(current,UnitName("player"),pending,left)
    note:SetText(text~="" and text or current.error or "")
    if can then accept:Enable();decline:Enable() else accept:Disable();decline:Disable() end
end

function G.Proposal(f)
    local p=Logic.proposal(f)
    if not p or not Logic.fresh(current,p,finished) then return end
    pending=false -- a newer P is the server's answer to any click
    p.error=current and current.id==p.id and current.error or nil
    current,received=p,GetTime()
    accept:Show();decline:Show();closeButton:Hide()
    open:Hide() -- a successful open: the ready check takes over
    G.Render()
    ready:Show()
end

-- `T|id|revision|state|level|openerName|reason|message`: starting locks the buttons, started
-- closes (the teleport follows), cancelled shows the server's words with a Close button.
function G.Result(f)
    local id,state,message=f[2],f[4],f[8] or ""
    finished[id]=true -- after starting only started or cancelled follow, never a P
    if not current or current.id~=id then return end
    pending=false
    if state=="started" then
        current=nil;ready:Hide();U.say(message)
        return
    end
    current.result={state=state,message=message}
    G.Render()
    ready:Show()
end

local function refused(text)
    if asked=="open" and open:IsShown() then openNote:SetText(text)
    elseif asked=="respond" and current and not current.result then pending=false;current.error=text;G.Render()
    else U.say(text,true) end
end

local tick=0
ready:SetScript("OnUpdate",function(_,dt)
    tick=tick+dt
    if tick<.2 then return end
    tick=0
    G.Render()
end)

------------------------------------------------------------------------------------------------
-- The server's records
------------------------------------------------------------------------------------------------
function G.OnMessage(prefix,body,distribution,sender)
    if prefix~=PREFIX or distribution~="WHISPER" then return end
    local own=UnitName("player")
    if sender~=own and sender~=own.."-"..GetRealmName() then return end
    local f=Logic.split(body)
    if f[1]=="L" then G.ShowLevels(f)
    elseif f[1]=="P" then G.Proposal(f)
    elseif f[1]=="T" then G.Result(f)
    elseif f[1]=="C" then open:Hide()
    elseif f[1]=="X" then refused(f[2] or "") end
end
local watcher=CreateFrame("Frame")
watcher:RegisterEvent("CHAT_MSG_ADDON")
watcher:SetScript("OnEvent",function(_,_,...) G.OnMessage(...) end)

-- This file runs once per UI load (login or /reload): ask for a ready check still waiting on us.
send("sync")

G.ui={open=open,rows=rows,openButton=openButton,keystones=keystones,openNote=openNote,ready=ready,accept=accept,
    decline=decline,close=closeButton,note=note,timeLine=timeLine,levelLine=levelLine,leaderLine=leaderLine,members=members}
