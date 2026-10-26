-- luacheck: globals DCUI DCFollower DCFollowerData DCThrottle DCItemTooltipRecords DCAddItemTooltips DCShowItemTooltip PickupContainerItem
-- luacheck: globals GetCursorInfo ClearCursor GetItemIcon UnitName GetRealmName GetTime SendAddonMessage GameTooltip hooksecurefunc CharDBQuery
-- The Follower window: a follower's portrait, level, relic slot, attributes, Damage and Toughness, its 13 gear slots and its four tiers
-- of two skills, with Hire or Dismiss and a Details panel beside it. It reads what the server sends and computes nothing: the wire is
-- docs/contracts/followers.md, "Messages" (the window bridge prefix DCFOLLOWER), the skills' names, icons and texts are the generated
-- dc_follower_skills.lua. The window opens when the server pushes a follower's records (talking to one in the hub, or to the
-- companion beside the player).
local AIO=AIO or require("AIO")
local CHANNEL="DiablocraftFollower"
if AIO.AddAddon() then
    -- A worn item sits in nobody's bags, so its rolled tooltip is asked of the tooltip addon's server half here, from the player's own
    -- gear rows and never from what the request names (the stash does the same).
    local handlers=AIO.AddHandlers(CHANNEL,{})
    function handlers.Tooltips(player,follower)
        if type(follower)~="number" or follower~=math.floor(follower) or follower<1 or follower>3 then return end
        if not DCThrottle.Allow(player,"follower:tooltips",5,10) then return end
        local cells={}
        local rows=CharDBQuery(("SELECT g.item_guid,i.itemEntry FROM dc_character_follower_gear g JOIN item_instance i ON i.guid=g.item_guid "
            .."WHERE g.guid=%d AND g.follower=%d"):format(player:GetGUIDLow(),follower))
        if rows then repeat cells[#cells+1]={guid=rows:GetUInt32(0),entry=rows:GetUInt32(1)} until not rows:NextRow() end
        AIO.Handle(player,CHANNEL,"Tooltips",{records=DCItemTooltipRecords and DCItemTooltipRecords(cells) or {}})
    end
    return
end

local handlers=AIO.AddHandlers(CHANNEL,{})
local U=DCUI or error("dc_aio_ui.lua must load before dc_follower.lua")
local F={}
DCFollower=F
local Logic={}
F.Logic=Logic

----------------------------------------------------------------------------------------------------
-- Rules. Nothing below touches a frame.
----------------------------------------------------------------------------------------------------
-- The 14 slots in the wire's order (the contract's "Gear"): key, the name a player reads, the stock empty-slot art, and where the
-- gear box draws it (the relic sits beside the portrait, so it has no place here).
local SLOTS={
    {key="relic",title="Relic",art="UI-PaperDoll-Slot-Relic"},
    {key="head",title="Helm",art="UI-PaperDoll-Slot-Head",x=102,y=16},
    {key="shoulders",title="Shoulders",art="UI-PaperDoll-Slot-Shoulder",x=14,y=30},
    {key="chest",title="Chest",art="UI-PaperDoll-Slot-Chest",x=102,y=76},
    {key="gloves",title="Gloves",art="UI-PaperDoll-Slot-Hands",x=14,y=90},
    {key="bracers",title="Bracers",art="UI-PaperDoll-Slot-Wrists",x=190,y=90},
    {key="belt",title="Belt",art="UI-PaperDoll-Slot-Waist",x=102,y=136},
    {key="pants",title="Pants",art="UI-PaperDoll-Slot-Legs",x=102,y=196},
    {key="boots",title="Boots",art="UI-PaperDoll-Slot-Feet",x=102,y=256},
    {key="ring1",title="Ring",art="UI-PaperDoll-Slot-Finger",x=14,y=150},
    {key="ring2",title="Ring",art="UI-PaperDoll-Slot-Finger",x=190,y=150},
    {key="neck",title="Amulet",art="UI-PaperDoll-Slot-Neck",x=190,y=30},
    {key="mainhand",title="Main Hand",art="UI-PaperDoll-Slot-MainHand",x=14,y=210},
    {key="offhand",title="Off Hand",art="UI-PaperDoll-Slot-SecondaryHand",x=190,y=210},
}
Logic.SLOTS=SLOTS
local DETAIL_GROUPS={offense="Offense",defense="Defense",life="Life",adventure="Adventure"}
local DETAIL_ORDER={"offense","defense","life","adventure"}
local UINT32_MAX=4294967295

-- A whole number as the character sheet prints it: the digits grouped in threes, no decimals. The wire sends whole numbers; a stray
-- fraction is cut, never rounded here.
function Logic.whole(text)
    local digits=tostring(text or "0"):match("^%-?%d+") or "0"
    return U.number(digits)
end
-- A skill's text as lines, the seconds the way a player says them: "3.00 seconds" reads "3 seconds" ("1.50 seconds" stays).
function Logic.tipLines(text)
    local out={}
    for line in (tostring(text or "").."\n"):gmatch("(.-)\n") do
        line=line:gsub("(%d+)%.0+ (seconds?)","%1 %2")
        out[#out+1]=line
    end
    return out
end
-- The bag index of the contract's "Commands" (container * 100 + slot, 255 the backpack) for a client bag (0 the backpack, 1 to 4
-- the bags) and its 1-based slot, the way the cursor's pick-up hook reports them.
function Logic.bagIndex(bag,slot)
    if bag==0 then return 25500+22+slot end
    return (18+bag)*100+(slot-1)
end
-- A tier above the follower's level is locked.
function Logic.locked(tier,level) return (level or 0)<(tier.level or 0) end
-- What a tier row says: its header, its name line and its state (locked, all, unpicked, picked), from a tier of the model, the
-- follower's skills of the generated data and the follower's level.
function Logic.tierRow(tier,skills,level)
    if Logic.locked(tier,level) then return "Unlocks at level "..tier.level,"Locked","locked" end
    if tier.all then return "Level "..tier.level.." Skills",skills[1].name.." and "..skills[2].name,"all" end
    for _,skill in ipairs(skills) do
        if skill.id==tier.pick then return "Selected Level "..tier.level.." Skill",skill.name,"picked" end
    end
    return "Level "..tier.level.." Skill","Choose a skill","unpicked"
end
function Logic.status(model)
    if model.hired then return "Following you","following" end
    return "Waiting in the Sanctum","waiting"
end
-- The whole numbers of a request field, bounded as the bridge bounds them.
local function whole(value) return type(value)=="number" and value==math.floor(value) and value>=0 and value<=UINT32_MAX end
local function token(value) return type(value)=="string" and value:match("^[%w_]+$")~=nil and #value<=12 end
-- A skill id as followers.csv writes it: letters, digits and hyphens ("crippling-shot").
local function skillId(value) return type(value)=="string" and value:match("^[%a%d%-]+$")~=nil and #value<=32 end
local FIELDS={open={whole},equip={whole,whole,token},unequip={whole,token},dismiss={whole},skill={whole,whole,skillId}}
-- The request line, or nil when a field is not what the bridge takes.
function Logic.request(verb,...)
    local checks=FIELDS[verb]
    if not checks then return nil end
    local body=verb
    for index,check in ipairs(checks) do
        local value=select(index,...)
        if not check(value) then return nil end
        body=body.."\t"..tostring(value)
    end
    return body
end

----------------------------------------------------------------------------------------------------
-- State
----------------------------------------------------------------------------------------------------
local model                          -- the last complete reply (nil before the first)
local building                       -- the reply being read
local awaiting                       -- when the last request went out
local askedTooltips                  -- the worn guids the tooltip records were asked for
local cursorBag,cursorSlot
local frame,details,render
local say=U.say
local GOLD,WHITE,GREY,RED=U.GOLD,U.WHITE,U.GREY,U.RED
local GREEN={.12,1,0}
local colour,text,tooltip=U.colour,U.text,U.tooltip
local function data(follower) return DCFollowerData and DCFollowerData.followers and DCFollowerData.followers[follower] end

-- A second click while the first is unanswered is dropped: one click is one request.
local function send(verb,...)
    local body=Logic.request(verb,...)
    if not body then return false end
    if awaiting and GetTime()-awaiting<=3 then return false end
    awaiting=GetTime()
    SendAddonMessage("DCFOLLOWER",body,"WHISPER",UnitName("player"))
    return true
end
F.send=send
F.model=function() return model end

----------------------------------------------------------------------------------------------------
-- Frames
----------------------------------------------------------------------------------------------------
frame=U.window("DiablocraftFollowerFrame",440,700)
local title=U.title(frame,"")
local sub=U.subtitle(frame)
U.close(frame)
local function panel(parent,x,y,width,height)
    local box=CreateFrame("Frame",nil,parent)
    box:SetPoint("TOPLEFT",x,y);box:SetSize(width,height)
    U.flat(box,U.DETAIL_BG[1],U.DETAIL_BG[2],U.DETAIL_BG[3],U.DETAIL_BORDER[1],U.DETAIL_BORDER[2],U.DETAIL_BORDER[3])
    return box
end

-- The left box: the portrait and the relic slot, the status, the four attributes, Damage and Toughness, Details and Hire or Dismiss.
local left=panel(frame,16,-64,150,330)
local portrait=U.slot(left,56);portrait:SetPoint("TOPLEFT",10,-10)
local levelText=text(left,10,-70,56,"GameFontHighlightSmall","CENTER")
local statusText=text(left,10,-92,130,"GameFontHighlightSmall","CENTER")
local ATTRIBUTES={"Strength","Dexterity","Intelligence","Vitality"}
local attrLabels,attrValues={},{}
for index,name in ipairs(ATTRIBUTES) do
    local y=-114-(index-1)*20
    attrLabels[index]=text(left,10,y,80,"GameFontNormalSmall");attrLabels[index]:SetText(name)
    attrValues[index]=text(left,10,y,130,"GameFontHighlightSmall","RIGHT")
end
local damageLabel=text(left,10,-200,130,"GameFontNormalSmall","CENTER");damageLabel:SetText("Damage")
local damageValue=text(left,10,-214,130,"GameFontHighlight","CENTER")
local toughLabel=text(left,10,-236,130,"GameFontNormalSmall","CENTER");toughLabel:SetText("Toughness")
local toughValue=text(left,10,-250,130,"GameFontHighlight","CENTER")
local detailsButton=U.button(left,130,"Details",function() F.ToggleDetails() end);detailsButton:SetPoint("TOPLEFT",10,-272)
local dismissButton=U.button(left,130,"Dismiss",function() F.Dismiss() end);dismissButton:SetPoint("TOPLEFT",10,-298)

-- The gear box and its slots; the relic slot (the left box) is the fourteenth.
local gearBox=panel(frame,174,-64,250,330)
local slotButtons={}
local function showSlotTip(self)
    local key=self.key
    local cell=model and model.gear[key]
    GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
    if cell and cell.entry~=0 then
        GameTooltip:SetHyperlink("item:"..cell.entry..":0:0:0:0:0:0:0")
        -- The rolled lines come from the tooltip addon, which holds this item's record once the server has answered Tooltips.
        if DCShowItemTooltip and cell.guid~=0 then DCShowItemTooltip(GameTooltip,cell.guid) end
    else
        local relic=model and data(model.follower)
        GameTooltip:SetText(key=="relic" and relic and relic.relic or self.title,1,1,1)
        if cell and not cell.usable then GameTooltip:AddLine("This follower cannot use it.",1,.3,.3,true) end
    end
    GameTooltip:Show()
end
local function slotClick(self,button)
    local cell=model and model.gear[self.key]
    if not cell then return end
    local kind=GetCursorInfo()
    if kind=="item" and cursorBag and cursorSlot then
        ClearCursor()
        send("equip",model.follower,Logic.bagIndex(cursorBag,cursorSlot),self.key)
    elseif button=="RightButton" and cell.entry~=0 then
        send("unequip",model.follower,self.key)
    end
end
for index,def in ipairs(SLOTS) do
    local parent=def.x and gearBox or left
    local b=U.slot(parent,46)
    if def.x then b:SetPoint("TOPLEFT",def.x,-def.y) else b:SetPoint("TOPLEFT",78,-15) end
    b.key,b.title=def.key,def.title
    b:RegisterForClicks("LeftButtonUp","RightButtonUp")
    b:SetScript("OnClick",slotClick);b:SetScript("OnReceiveDrag",function(self) slotClick(self,"LeftButton") end)
    b:SetScript("OnEnter",showSlotTip);b:SetScript("OnLeave",function() GameTooltip:Hide() end)
    slotButtons[index]=b
end

-- The skills box: four rows, each two icons and the header and name of the pick.
local skillsBox=panel(frame,16,-402,408,282)
local tierRows={}
local function skillTip(self)
    local skill=self.skill
    if not skill then return end
    GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
    GameTooltip:SetText(skill.name,1,1,1)
    for _,line in ipairs(Logic.tipLines(skill.text)) do GameTooltip:AddLine(line,1,.82,0,true) end
    GameTooltip:Show()
end
for tier=1,4 do
    local row=CreateFrame("Frame",nil,skillsBox)
    row:SetPoint("TOPLEFT",8,-8-(tier-1)*68);row:SetSize(392,62)
    U.flat(row,0,0,0,.25,.2,.12)
    row.icons={}
    for choice=1,2 do
        local b=U.slot(row,46);b:SetPoint("TOPLEFT",12+(choice-1)*56,-8)
        b:SetScript("OnClick",function(self)
            if not model or not self.skill or self.locked then return end
            send("skill",model.follower,tier,self.skill.id)
        end)
        b:SetScript("OnEnter",skillTip);b:SetScript("OnLeave",function() GameTooltip:Hide() end)
        row.icons[choice]=b
    end
    row.header=text(row,128,-12,256,"GameFontNormalSmall")
    row.name=text(row,128,-32,256,"GameFontNormalLarge")
    tierRows[tier]=row
end

-- The Details panel, a second window beside the first.
details=U.window("DiablocraftFollowerDetails",330,700)
details:ClearAllPoints();details:SetPoint("TOPLEFT",frame,"TOPRIGHT",-8,0)
local detailsTitle=U.title(details,"Details")
U.close(details)
local detailsBox=panel(details,16,-52,298,632)
local detailLines={}
local function detailLine(index)
    local line=detailLines[index]
    if not line then
        line={label=text(detailsBox,10,0,190,"GameFontHighlightSmall"),value=text(detailsBox,10,0,278,"GameFontHighlightSmall","RIGHT"),
            head=text(detailsBox,10,0,278,"GameFontNormal")}
        detailLines[index]=line
    end
    return line
end
function F.ToggleDetails()
    if details:IsShown() then details:Hide() else details:Show() end
end
-- Hiring is by talking to the follower in the Sanctum (the server's gossip), so the window has no Hire: only Dismiss, for the hired one.
function F.Dismiss()
    if not model or not model.hired then return end
    send("dismiss",model.follower)
end
frame:SetScript("OnHide",function() details:Hide();GameTooltip:Hide() end)

----------------------------------------------------------------------------------------------------
-- Drawing: from the model only
----------------------------------------------------------------------------------------------------
local function drawSlots()
    for index,def in ipairs(SLOTS) do
        local b=slotButtons[index]
        local cell=model.gear[def.key] or {entry=0,guid=0,usable=true}
        if cell.entry~=0 then b.icon:SetTexture(GetItemIcon(cell.entry) or U.QUESTION) else b.icon:SetTexture("Interface\\PaperDoll\\"..def.art) end
        b.icon:SetDesaturated(not cell.usable)
        b:SetAlpha(cell.usable and 1 or .45)
    end
end
local function drawTiers(info)
    for tier=1,4 do
        local row,entry=tierRows[tier],model.tiers[tier]
        if entry and info and info.tiers[tier] then
            local skills=info.tiers[tier].skills
            local header,name,state=Logic.tierRow(entry,skills,model.level)
            row.header:SetText(header);row.name:SetText(name)
            colour(row.header,state=="locked" and GREY or GOLD);colour(row.name,(state=="locked" or state=="unpicked") and GREY or WHITE)
            for choice=1,2 do
                local b=row.icons[choice]
                local lit=state=="all" or (state=="picked" and entry.pick==skills[choice].id)
                b.skill,b.locked=skills[choice],state=="locked"
                b.icon:SetTexture(skills[choice].icon)
                b.icon:SetDesaturated(state=="locked" or (state=="picked" and not lit))
                b:SetBackdropBorderColor(lit and GOLD[1] or U.SLOT_BORDER[1],lit and GOLD[2] or U.SLOT_BORDER[2],lit and GOLD[3] or U.SLOT_BORDER[3],1)
            end
            row:Show()
        else row:Hide() end
    end
end
local function drawDetails()
    local y,count=-10,0
    local byGroup={}
    for _,row in ipairs(model.details) do
        byGroup[row.group]=byGroup[row.group] or {}
        table.insert(byGroup[row.group],row)
    end
    for _,group in ipairs(DETAIL_ORDER) do
        if byGroup[group] then
            count=count+1
            local head=detailLine(count)
            head.label:Hide();head.value:Hide()
            head.head:ClearAllPoints();head.head:SetPoint("TOPLEFT",10,y);head.head:SetText(DETAIL_GROUPS[group]);head.head:Show()
            y=y-22
            for _,row in ipairs(byGroup[group]) do
                count=count+1
                local line=detailLine(count)
                line.head:Hide()
                line.label:ClearAllPoints();line.label:SetPoint("TOPLEFT",18,y);line.label:SetText(row.label);colour(line.label,GOLD);line.label:Show()
                line.value:ClearAllPoints();line.value:SetPoint("TOPLEFT",10,y);line.value:SetText(row.value);colour(line.value,WHITE);line.value:Show()
                y=y-18
            end
            y=y-8
        end
    end
    for index=count+1,#detailLines do
        local line=detailLines[index]
        line.head:Hide();line.label:Hide();line.value:Hide()
    end
end
render=function()
    if not model then return end
    local info=data(model.follower)
    title:SetText(info and info.name or "Follower")
    sub:SetText(info and info.kind:upper() or "")
    portrait.icon:SetTexture(info and info.portrait or U.QUESTION)
    levelText:SetText("Level "..model.level)
    local status,state=Logic.status(model)
    statusText:SetText(status);colour(statusText,state=="following" and GREEN or GREY)
    for index=1,4 do attrValues[index]:SetText(Logic.whole(model.attrs[index])) end
    damageValue:SetText(Logic.whole(model.attrs[5]));toughValue:SetText(Logic.whole(model.attrs[6]))
    if model.hired then dismissButton:Show() else dismissButton:Hide() end
    drawSlots();drawTiers(info);drawDetails()
end

----------------------------------------------------------------------------------------------------
-- The bridge reply: DCFOLLOWER<TAB>record, W first and E last; X alone is a refusal.
----------------------------------------------------------------------------------------------------
local function split(value,separator)
    local out={}
    for field in (value..separator):gmatch("(.-)"..separator) do out[#out+1]=field end
    return out
end
local function ask(follower,guids)
    local key=table.concat(guids,",")
    if key=="" or key==askedTooltips then return end
    askedTooltips=key
    AIO.Handle(CHANNEL,"Tooltips",follower)
end
local function finish()
    model=building;building=nil;awaiting=nil
    local guids={}
    for _,def in ipairs(SLOTS) do
        local cell=model.gear[def.key]
        if cell and cell.guid~=0 then guids[#guids+1]=cell.guid end
    end
    table.sort(guids)
    ask(model.follower,guids)
    if not frame:IsShown() then frame:Show() end
    render()
end
function F.Reply(f)
    local record=f[1]
    local n=tonumber
    if record=="X" then
        say(f[2] or "That did not work.",true);awaiting=nil
        return
    elseif record=="W" then
        building={follower=n(f[2]) or 0,hired=f[3]=="1",hub=f[4]=="1",level=n(f[5]) or 0,
            attrs={"0","0","0","0","0","0"},details={},gear={},tiers={}}
    elseif not building then return
    elseif record=="A" then
        for index=1,6 do building.attrs[index]=f[index+1] or "0" end
    elseif record=="D" then
        table.insert(building.details,{group=f[2] or "",label=f[3] or "",value=f[4] or ""})
    elseif record=="G" then
        building.gear[f[2] or ""]={entry=n(f[3]) or 0,guid=n(f[4]) or 0,usable=f[5]~="0"}
    elseif record=="K" then
        local tier=n(f[2])
        if tier and tier>=1 and tier<=4 then building.tiers[tier]={level=n(f[3]) or 0,pick=f[4] or "",all=f[5]=="1"} end
    elseif record=="E" then finish() end
end
local bridge=CreateFrame("Frame")
bridge:RegisterEvent("CHAT_MSG_ADDON")
bridge:SetScript("OnEvent",function(_,_,prefix,message,distribution,sender)
    if prefix~="DCFOLLOWER" or distribution~="WHISPER" then return end
    local me=UnitName("player")
    if sender~=me and sender~=me.."-"..GetRealmName() then return end
    F.Reply(split(message,"|"))
end)
-- Where the cursor's item was picked up, for the equip request.
hooksecurefunc("PickupContainerItem",function(bag,slot) cursorBag,cursorSlot=bag,slot end)

-- The server's answer to Tooltips: the rolled records of the worn items, for the tooltip addon to draw.
function handlers.Tooltips(_,payload)
    if payload and DCAddItemTooltips then DCAddItemTooltips(payload.records) end
end
F.ui={frame=frame,details=details,title=title,sub=sub,portrait=portrait,levelText=levelText,statusText=statusText,attrValues=attrValues,
    damageValue=damageValue,toughValue=toughValue,detailsButton=detailsButton,dismissButton=dismissButton,slots=slotButtons,tiers=tierRows,
    detailLines=detailLines}
