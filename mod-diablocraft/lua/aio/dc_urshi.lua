-- dc_urshi.lua - Urshi's legendary gem upgrade window. Contract:
-- docs/contracts/urshi-messages.md (DCURSHI on the window bridge).
--
-- Talking to Urshi makes the server send a list reply (W, L, G..., E); W opens this window. The rows are drawn
-- in the order they arrive (worn gems first, then bags and stash, each by rank: the server's order): icon, name,
-- rank and the upgrade chance at this rift's level; a gem at its maximum rank is grey and cannot be picked.
-- Upgrade sends the picked gem's id and nothing else; U says how the try went, and the list reply after it
-- redraws the rows, the tries and the chances. The picked row is kept by id across every redraw.
--
-- The server decides everything: this file never rolls, never works out a chance and keeps no rank of its
-- own; the gem id is the server's token, copied as is. The look is the stock window kit (dc_aio_ui.lua, DCUI;
-- no D3 skin). Nothing here runs on the server.
-- luacheck: globals DCUrshi DCUI
local AIO=AIO or require("AIO")
if AIO.AddAddon() then return end

local PREFIX="DCURSHI"
local U=DCUI or error("dc_aio_ui.lua must load before dc_urshi.lua")
DCUrshi={}
local W=DCUrshi
local Logic={};W.Logic=Logic

------------------------------------------------------------------------------------------------
-- The logic, with no frame in it
------------------------------------------------------------------------------------------------
-- The contract's refusal on which the window closes (What the server checks, 2).
Logic.NOT_NEAR="Urshi is not near you."

function Logic.split(body)
    local fields={}
    for field in (body.."|"):gmatch("(.-)|") do fields[#fields+1]=field end
    return fields
end

-- `G|id|where|entry|name|rank|max|full|chance`, or nil when it does not read as one.
function Logic.gem(f)
    if f[1]~="G" or #f~=9 or f[2]=="" or not tonumber(f[4]) or not tonumber(f[6]) or not tonumber(f[9]) then return end
    return {id=f[2],where=f[3],entry=tonumber(f[4]),name=f[5],rank=tonumber(f[6]),full=f[8]=="1",chance=tonumber(f[9])}
end

-- The picked id after a redraw: kept while the gem is still listed and not full, else nothing.
function Logic.keep(gems,picked)
    for _,gem in ipairs(gems) do if gem.id==picked then return not gem.full and picked or nil end end
end

-- Upgrade is clickable with a try left, a picked gem and no try waiting for its answer.
function Logic.canUpgrade(left,picked,pending)
    return (tonumber(left) or 0)>0 and picked~=nil and not pending
end

-- The line under the list after U: the gem by name when the window still lists it.
function Logic.result(ok,name,rank)
    if ok then return (name or "The gem").." is now rank "..rank.."." end
    return "The upgrade failed. "..(name or "The gem").." stays at rank "..rank.."."
end

------------------------------------------------------------------------------------------------
-- The window
------------------------------------------------------------------------------------------------
local ROWS,ROW_H=10,24 -- a row holds a 20 px icon, so it is taller than the kit's text rows
local frame=U.window("TormentUrshiFrame",400,450,"urshi")
U.title(frame,"Urshi")
local sub=U.subtitle(frame)
U.close(frame)
local tries=U.text(frame,24,-66,352)
local listBox=CreateFrame("Frame",nil,frame)
listBox:SetPoint("TOPLEFT",20,-88);listBox:SetSize(360,ROWS*ROW_H+8)
U.flat(listBox,U.DETAIL_BG[1],U.DETAIL_BG[2],U.DETAIL_BG[3],U.DETAIL_BORDER[1],U.DETAIL_BORDER[2],U.DETAIL_BORDER[3])
local scroll=U.scroll(CreateFrame("ScrollFrame","TormentUrshiScroll",listBox,"UIPanelScrollFrameTemplate"))
scroll:SetPoint("TOPLEFT",4,-4);scroll:SetSize(328,ROWS*ROW_H)
local list=CreateFrame("Frame",nil,scroll);list:SetSize(328,ROWS*ROW_H);scroll:SetScrollChild(list)
local note=U.text(frame,24,-108-ROWS*ROW_H,352,"GameFontNormal","CENTER")
note:SetHeight(32)

-- What the server last said: `state` its W, `gems` the last complete list, `incoming` a list still arriving.
local state,gems,incoming,picked,pending,rows={left=0,total=0},{},nil,nil,false,{}

local function send(verb,...)
    SendAddonMessage(PREFIX,table.concat({verb,...},"\t"),"WHISPER",UnitName("player"))
end

local upgrade
function W.Render()
    sub:SetText(state.level and "Greater Rift "..state.level or "")
    tries:SetText("Upgrade attempts: "..state.left.." / "..state.total)
    for i,gem in ipairs(gems) do
        local row=rows[i]
        if not row then
            row=U.row(list);row:SetWidth(328);row:SetHeight(ROW_H);row:SetPoint("TOPLEFT",0,-(i-1)*ROW_H)
            row.icon=row:CreateTexture(nil,"ARTWORK");row.icon:SetSize(20,20);row.icon:SetPoint("LEFT",2,0)
            row.label:SetPoint("LEFT",28,0);row.label:SetWidth(176)
            row.rank=row:CreateFontString(nil,"OVERLAY","GameFontHighlight");row.rank:SetPoint("LEFT",208,0)
            row.rank:SetWidth(70);row.rank:SetJustifyH("LEFT")
            row.chance=row:CreateFontString(nil,"OVERLAY","GameFontHighlight");row.chance:SetPoint("RIGHT",-4,0)
            row.chance:SetWidth(44);row.chance:SetJustifyH("RIGHT")
            row:SetScript("OnClick",function(self) W.Pick(self.gem.id) end)
            rows[i]=row
        end
        row.gem=gem
        row.icon:SetTexture(U.iconOf(gem.entry))
        row.label:SetText(gem.name)
        row.rank:SetText("Rank "..gem.rank)
        row.chance:SetText(gem.full and "Max" or gem.chance.."%")
        local colour=gem.full and U.GREY or U.WHITE
        U.colour(row.label,gem.full and U.GREY or U.GOLD);U.colour(row.rank,colour);U.colour(row.chance,colour)
        row.icon:SetDesaturated(gem.full)
        if gem.full then row:Disable() else row:Enable() end
        if gem.id==picked then row.mark:Show() else row.mark:Hide() end
        row:Show()
    end
    for i=#gems+1,#rows do rows[i]:Hide() end
    list:SetHeight(math.max(1,#gems)*ROW_H)
    if Logic.canUpgrade(state.left,picked,pending) then upgrade:Enable() else upgrade:Disable() end
end

function W.Pick(id)
    for _,gem in ipairs(gems) do
        if gem.id==id and not gem.full then picked=id;note:SetText("");W.Render();return end
    end
end

function W.Upgrade()
    if not Logic.canUpgrade(state.left,picked,pending) then return end
    pending=true
    send("upgrade",picked)
    W.Render()
end
upgrade=U.button(frame,140,"Upgrade",function() W.Upgrade() end)
U.anchor(frame,"buttons",{upgrade})
upgrade:SetPoint("BOTTOM",0,22)

------------------------------------------------------------------------------------------------
-- The server's records
------------------------------------------------------------------------------------------------
local function nameOf(id)
    for _,gem in ipairs(gems) do if gem.id==id then return gem.name end end
end

local record={}
-- `W|level|left|total`: the window state, first in every list reply. It opens the window.
function record.W(f)
    state={level=f[2],left=tonumber(f[3]) or 0,total=tonumber(f[4]) or 0}
    if not frame:IsShown() then picked=nil;note:SetText("");scroll:SetVerticalScroll(0) end
    W.Render()
    frame:Show()
end
-- `L|n`: a fresh list follows; `G` rows; `E|list` ends it and the rows are drawn.
function record.L() incoming={} end
function record.G(f)
    local gem=incoming and Logic.gem(f)
    if gem then incoming[#incoming+1]=gem end
end
function record.E()
    if not incoming then return end
    gems,incoming=incoming,nil
    picked=Logic.keep(gems,picked)
    if #gems==0 then note:SetText("You have no legendary gems to upgrade.") end
    W.Render()
end
-- `U|id|ok|rank|left`: how the try went; the list reply that follows redraws the rest. The gem's tooltip
-- reads its rank from the server, so the tooltip records are asked for again (as the Jeweler does).
function record.U(f)
    pending=false
    state.left=tonumber(f[5]) or state.left
    note:SetText(Logic.result(f[3]=="1",nameOf(f[2]),f[4] or "?"))
    U.colour(note,f[3]=="1" and U.GOLD or U.RED)
    AIO.Handle("DiablocraftTooltip","Refresh")
    W.Render()
end
-- `C|text`: Urshi is gone for this character.
function record.C(f)
    pending=false
    U.say(f[2] or "")
    frame:Hide()
end
-- `X|text`: refused, nothing happened; the window stays up, except when Urshi is out of reach.
function record.X(f)
    local text=f[2] or ""
    pending=false
    if text==Logic.NOT_NEAR then U.say(text,true);frame:Hide();return end
    note:SetText(text);U.colour(note,U.RED)
    if not frame:IsShown() then U.say(text,true) end
    W.Render()
end

function W.OnMessage(prefix,body,distribution,sender)
    if prefix~=PREFIX or distribution~="WHISPER" then return end
    local own=UnitName("player")
    if sender~=own and sender~=own.."-"..GetRealmName() then return end
    local f=Logic.split(body)
    local handle=record[f[1]]
    if handle then handle(f) end
end

-- A gem that moves while the window is up (bags, stash, worn) keeps its id but changes its place in the list:
-- ask the server for a fresh list once the bags settle, as the Jeweler does. Never while a try is out.
local watcher=CreateFrame("Frame")
local dirty,elapsed=false,0
watcher:RegisterEvent("CHAT_MSG_ADDON")
watcher:RegisterEvent("BAG_UPDATE")
watcher:RegisterEvent("PLAYER_EQUIPMENT_CHANGED")
watcher:SetScript("OnEvent",function(_,event,...)
    if event=="CHAT_MSG_ADDON" then return W.OnMessage(...) end
    dirty,elapsed=true,0
end)
watcher:SetScript("OnUpdate",function(_,delta)
    if not dirty then return end
    elapsed=elapsed+delta
    if elapsed<.3 or pending then return end
    dirty=false
    if frame:IsShown() then send("list") end
end)

W.ui={frame=frame,sub=sub,tries=tries,rows=rows,note=note,upgrade=upgrade,watcher=watcher}
