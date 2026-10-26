-- luacheck: globals DCJewelerResponses DCJeweler DCUI
-- luacheck: globals GetCursorPosition GetMouseFocus IsMouseButtonDown GetContainerNumFreeSlots NUM_CONTAINER_FRAMES MAX_CONTAINER_ITEMS GetContainerNumSlots ElvUI IsShiftKeyDown IsControlKeyDown IsAltKeyDown ItemSocketingFrame
local AIO=AIO or require("AIO")
local CHANNEL="DiablocraftJeweler"
-- The client half. The server half, the reads and the catalogue, is dc_jeweler_server.lua.
if AIO.AddAddon() then return end

local handlers=AIO.AddHandlers(CHANNEL,{})
-- The shared window look (dc_aio_ui.lua, loaded before this file because its name
-- sorts first): everything visual below is built from DCUI.
local U=DCUI or error("dc_aio_ui.lua must load before dc_jeweler.lua")
DCJewelerResponses=DCJewelerResponses or {}
local J={}
DCJeweler=J
local Logic={}
J.Logic=Logic
-- 12-ui U4: one shared formatter, in the Diablocraft
-- addon. The local fallback only runs if the addon is missing, and the server
-- already tells the player when it is.
local function commas(text)
    if Diablocraft and Diablocraft.Econ then return Diablocraft.Econ.Gold(text) end
    local out,count=tostring(text or "0"),1
    while count>0 do out,count=out:gsub("^(%-?%d+)(%d%d%d)","%1,%2") end
    return out
end

----------------------------------------------------------------------------------------------------
-- Rules. Nothing below touches a frame.
----------------------------------------------------------------------------------------------------
local AWAY_MESSAGE="Remove gems at the Jeweler."
Logic.AWAY_MESSAGE=AWAY_MESSAGE
-- The account totals are exact decimal strings (Economy.lua), and a Lua number loses digits past 2^53.
-- A total this long covers any price here a billion times over, so it is not read as a number at all.
local SAFE_DIGITS=15
local UINT32_MAX=4294967295
local function digits(total)
    local text=tostring(total or "0"):gsub("^0+","")
    return text=="" and "0" or text
end
-- True when the decimal-string total covers `need` (a whole number).
function Logic.atLeast(total,need)
    total=digits(total);need=digits(string.format("%.0f",need))
    if #total~=#need then return #total>#need end
    return total>=need
end
-- How many whole `unit`s the total pays for; a unit of 0 is free and never limits.
function Logic.times(total,unit)
    if unit<=0 then return math.huge end
    total=digits(total)
    if #total>SAFE_DIGITS then return UINT32_MAX end
    return math.floor(tonumber(total)/unit)
end
-- The most of one recipe the player could make now: the fewest of what the gems, the gold and the
-- Death's Breath each allow.
function Logic.craftable(recipe,balance)
    local n=math.floor((recipe.have or 0)/math.max(recipe.inputCount or 1,1))
    n=math.min(n,Logic.times(balance.gold,recipe.gold or 0))
    return math.min(n,Logic.times(balance.deathsBreath,recipe.deathsBreath or 0))
end
-- The list as the window draws it: one header per gem colour, A to Z, and under it every craftable
-- tier, highest first. view = {haveMats=bool, search=text, collapsed={[colour]=true}}.
function Logic.rows(recipes,balance,view)
    local byColour,colours={},{}
    for _,recipe in ipairs(recipes or {}) do
        if not byColour[recipe.colour] then byColour[recipe.colour]={};colours[#colours+1]=recipe.colour end
        local list=byColour[recipe.colour];list[#list+1]=recipe
    end
    table.sort(colours)
    local rows,query={},(view.search or ""):lower()
    for _,colour in ipairs(colours) do
        local list=byColour[colour]
        table.sort(list,function(a,b) return (a.rank or 0)>(b.rank or 0) end)
        local shown={}
        for _,recipe in ipairs(list) do
            local n=Logic.craftable(recipe,balance)
            if (not view.haveMats or n>=1) and (query=="" or recipe.name:lower():find(query,1,true)) then
                shown[#shown+1]={recipe=recipe,n=n}
            end
        end
        if #shown>0 then
            local closed=view.collapsed and view.collapsed[colour] and true or false
            rows[#rows+1]={head=colour,closed=closed}
            if not closed then for _,entry in ipairs(shown) do rows[#rows+1]=entry end end
        end
    end
    return rows
end
-- "[3] Flawless Royal Amethyst" when three can be made, the plain name otherwise.
function Logic.rowText(entry)
    return (entry.n>=1 and "["..entry.n.."] " or "")..entry.recipe.name
end
-- The quantity box holds a whole number from 1 up to what can be made (1 when nothing can).
function Logic.clampQty(value,most)
    value=math.floor(tonumber(value) or 1)
    return math.max(1,math.min(value,math.max(1,most or 1)))
end
-- Filling an EMPTY socket works anywhere. Taking a gem out, or putting one over another, is the
-- Jeweler's; the server enforces it, this is only the message.
function Logic.mayChange(atJeweler,socketFilled)
    return atJeweler or not socketFilled
end
-- Craft Jewelry: the most of one recipe the player could make now, the fewest of what each material,
-- the gold and the bag capacity allow; a disabled recipe makes none. Counts and gold are decimal strings.
function Logic.craftCount(recipe,balance,capacity)
    if not recipe.enabled then return 0 end
    local n=math.min(capacity or 0,Logic.times(balance.gold,tonumber(recipe.gold) or 0))
    for _,material in ipairs(recipe.materials or {}) do
        n=math.min(n,Logic.times(material.have,math.max(material.amount or 1,1)))
    end
    return n
end
local CRAFT_PAGES={amulets="Amulets",rings="Rings"}
local CRAFT_RANK={set=4,legendary=3,rare=2,magic=1,normal=0}
-- The list as the window draws it: one header per page (Amulets, Rings), the Blacksmith's order under it
-- (rarity, then required level, then name). view = {haveMats=bool, search=text, collapsed={[page]=true}}.
function Logic.craftRows(crafts,balance,capacity,view)
    local byPage,pages={},{}
    local query=(view.search or ""):lower()
    for _,recipe in ipairs(crafts or {}) do
        if not byPage[recipe.page] then byPage[recipe.page]={};pages[#pages+1]=recipe.page end
        local n=Logic.craftCount(recipe,balance,capacity)
        if (not view.haveMats or n>=1) and (query=="" or recipe.name:lower():find(query,1,true)) then
            local list=byPage[recipe.page];list[#list+1]={recipe=recipe,n=n}
        end
    end
    table.sort(pages)
    local rows={}
    for _,page in ipairs(pages) do
        local list=byPage[page]
        if #list>0 then
            table.sort(list,function(a,b)
                a,b=a.recipe,b.recipe
                if CRAFT_RANK[a.rarity]~=CRAFT_RANK[b.rarity] then return (CRAFT_RANK[a.rarity] or 0)>(CRAFT_RANK[b.rarity] or 0) end
                if a.required~=b.required then return a.required>b.required end
                if a.name~=b.name then return a.name<b.name end
                return a.id<b.id
            end)
            local closed=view.collapsed and view.collapsed[page] and query=="" and true or false
            rows[#rows+1]={head=CRAFT_PAGES[page] or page,page=page,closed=closed}
            if not closed then for _,entry in ipairs(list) do rows[#rows+1]=entry end end
        end
    end
    return rows
end
local SLOT_LABEL={weapon="Weapon",head="Helm",other="Other"}
local SLOT_ORDER={"weapon","head","other"}
Logic.SLOT_LABEL=SLOT_LABEL
-- A legendary gem has no effect line of its own; the window says what it is instead.
function Logic.legendary(tables,entry)
    return tables and tables.legendary and tables.legendary[entry] and true or false
end
-- A gem's effect on one kind of item, in the tooltip's own words (the server asks dc_tooltip.lua for them).
function Logic.effect(tables,entry,slotClass)
    local effects=tables and tables.effects and tables.effects[entry]
    return effects and effects[slotClass] or nil
end

----------------------------------------------------------------------------------------------------
-- State
----------------------------------------------------------------------------------------------------
local model={items={},gems={},recipes={},crafts={},craftMax=0,balance={gold="0",deathsBreath="0"}}
local tables
local awaiting=nil     -- when the last request went out; its reply is the update
local cursorBag,cursorSlot
local search,haveMats,collapsed="",false,{}
local selected                  -- the recipe id the details show
local qty=1
local tab="combine"
local craftSearch,craftHave,craftCollapsed="",false,{}   -- the Craft Jewelry tab's own list state
local craftSelected                 -- the craft recipe id its details show
local craftQty=1
local dirty,quiet=false,0           -- the watcher's: a re-read of the Show payload is due
local pending                   -- a Gear request the answer of which opens a view
local refreshing                -- the guid a refresh of the Sockets window asked for
local chain                      -- Remove Gems: the item and the sockets still to empty, one request each
J.model=function() return model end

local say=U.say
-- /dcjeweler prints what the drag code sees, for a recheck in the client.
local function trace(...)
    if J.debug then print("DCJeweler:",...) end
end

-- docs/contracts/window-bridge.md: a button sends one addon message and C++ answers with the
-- records of what the action changed. `awaiting` is when the request went out: the bag update the
-- action causes is not a reason to re-read the database, because the reply below is the update.
local JEWELER_FIELDS={socket=4,remove=3,combine=3,craft=3}
local function whole(value)
    return type(value)=="number" and value==math.floor(value) and value>=0 and value<=UINT32_MAX
end
-- A second click while the first is unanswered would be a second request: it is dropped, so one click is
-- one request and the flood limit is never the thing a player meets.
local function send(action,first,second,third)
    local width=JEWELER_FIELDS[action]
    if not width then return false end
    if awaiting and GetTime()-awaiting<=3 then return false end
    local body=action
    if width>1 then if not whole(first) then return false end body=body.."\t"..first end
    if width>2 then if not whole(second) then return false end body=body.."\t"..second end
    if width>3 then if not whole(third) then return false end body=body.."\t"..third end
    awaiting=GetTime();J.lastSent=action
    SendAddonMessage("DCJEWELER",body,"WHISPER",UnitName("player"))
    return true
end
J.send=send

----------------------------------------------------------------------------------------------------
-- Frames
----------------------------------------------------------------------------------------------------
local GEM_COLOUR={Amethyst={.76,.55,1},Diamond={.9,.95,1},Emerald={.31,.88,.54},Ruby={1,.36,.36},Topaz={1,.82,.29}}
local function gemColour(name)
    for colour,rgb in pairs(GEM_COLOUR) do if name and name:find(colour,1,true) then return rgb end end
    return {1,1,1}
end
-- The look lives in dc_aio_ui.lua (DCUI), so the Jeweler and the Blacksmith build from
-- one definition and cannot drift apart again. The builders resolve Diablocraft.Style
-- on every call, so a newer addon reaches a window built afterwards.
local GOLD,WHITE,GREY,RED=U.GOLD,U.WHITE,U.GREY,U.RED
local EDGE=U.EDGE
local QUESTION=U.QUESTION
local iconOf=U.iconOf
local text,colour,flat,button,slot,tooltip=U.text,U.colour,U.flat,U.button,U.slot,U.tooltip
-- A gem's tooltip: its name and what it gives on a weapon, a helm and anything else.
local function gemTip(owner,entry,name)
    tooltip(owner,function(tip)
        if Logic.legendary(tables,entry) then
            tip:SetText(name or "Gem",1,.5,0)
            tip:AddLine("Legendary Gem",1,.5,0)
            return
        end
        tip:SetText(name or "Gem",unpack(gemColour(name)))
        tip:AddLine("Gem",.8,.8,.8)
        for _,key in ipairs(SLOT_ORDER) do
            local line=Logic.effect(tables,entry,key)
            if line then tip:AddLine(SLOT_LABEL[key]..": "..line,.45,.72,1,true) end
        end
    end)
end
local gemName=function(entry) return tables and tables.gems and tables.gems[entry] end

-- Where the cursor is (UIParent units) and whether a frame covers it. The Torment inventory and stash
-- find a drop target the same way (Diablocraft.lua): by geometry, never by GetMouseFocus().
local function cursorPoint()
    if not GetCursorPosition then return nil end
    local x,y=GetCursorPosition()
    if not x or not y then return nil end
    local scale=UIParent:GetEffectiveScale()
    if not scale or scale==0 then scale=1 end
    return x/scale,y/scale
end
local function covers(f,x,y)
    if f.IsVisible and not f:IsVisible() then return false end
    local left,right,bottom,top=f:GetLeft(),f:GetRight(),f:GetBottom(),f:GetTop()
    if not left or not right or not bottom or not top then return false end
    return x>=left and x<right and y>=bottom and y<top
end

-- The ghost that follows the cursor while a socketed gem is being pulled out. The stock cursor would
-- start the client's own item move (the stash found the same).
local ghost=CreateFrame("Frame","DiablocraftJewelerGhost",UIParent)
ghost:SetSize(36,36);ghost:SetFrameStrata("TOOLTIP");ghost:Hide()
ghost.icon=ghost:CreateTexture(nil,"OVERLAY");ghost.icon:SetAllPoints()
ghost:SetScript("OnUpdate",function(self)
    local x,y=GetCursorPosition();local scale=UIParent:GetEffectiveScale()
    self:ClearAllPoints();self:SetPoint("CENTER",UIParent,"BOTTOMLEFT",x/scale,y/scale)
end)

local frame,sockFrame,render,renderAll
local function atJeweler() return frame:IsShown() and true or false end

----------------------------------------------------------------------------------------------------
-- The socket view: an item frame and its sockets as large slots. The Unsocket Gems tab and the small
-- Sockets window each hold one.
----------------------------------------------------------------------------------------------------
local function itemOf(guid)
    for _,item in ipairs(model.items) do if item.guid==guid then return item end end
end
local function gemOf(guid)
    for _,gem in ipairs(model.gems) do if gem.guid==guid then return gem end end
end
-- A bag gem on the cursor, found among what the window knows: by where it was picked up and by its item id,
-- because the pick-up hooks only say where, and the cursor may hold something from elsewhere. Items are never
-- dropped on the window: Shift+Right-click loads one.
local function cursorThing()
    local kind,id=GetCursorInfo()
    if kind~="item" then return nil end
    for _,gem in ipairs(model.gems) do
        if gem.bag==cursorBag and gem.slot==cursorSlot and (not id or gem.entry==id) then return "gem",gem end
    end
    return "other"
end

local function newView(parent,compact)
    local view={}
    local root=CreateFrame("Frame",nil,parent)
    view.root=root
    local box=U.box(root)
    view.box=box
    view.slot=slot(box,64);view.slot:SetPoint("LEFT",14,0)
    view.hint=box:CreateFontString(nil,"OVERLAY","GameFontNormalLarge");view.hint:SetPoint("LEFT",92,0)
    view.hint:SetText(compact and "Shift+Right-click an item to see its sockets" or "Right-click an item to see its sockets");colour(view.hint,GREY)
    view.name=text(box,92,-18,300,"GameFontNormalLarge")
    view.kind=text(box,92,-40,300,"GameFontHighlight")
    view.note=text(box,92,-58,330,"GameFontHighlightSmall");colour(view.note,GREY)
    view.clear=button(box,60,"Clear",function() view.item=nil;view:Render() end)
    view.clear:SetPoint("RIGHT",-12,0)
    view.foot=root:CreateFontString(nil,"OVERLAY","GameFontNormal")
    view.foot:SetPoint("BOTTOM",0,6);view.foot:SetWidth(compact and 400 or 500);view.foot:SetJustifyH("CENTER")
    view.sockets={}
    -- Remove Gems: the Jeweler's window only; away from the Jeweler nothing can be removed.
    if not compact then
        view.removeAll=button(root,120,"Remove Gems",function() J.RemoveAll(view) end)
        view.removeAll:SetPoint("BOTTOM",0,34);view.removeAll:Hide()
    end
    view.slot:SetScript("OnEnter",function(self)
        local item=view.item
        if not item then return end
        tooltip(self,function(tip)
            if item.bag==255 then tip:SetInventoryItem("player",item.slot+1) else tip:SetBagItem(item.bag,item.slot) end
        end)
    end)
    view.slot:SetScript("OnLeave",function() GameTooltip:Hide() end)

    local function socketSlot(index)
        local column=CreateFrame("Frame",nil,root)
        column:SetSize(128,150)
        local s=slot(column,64);s:SetPoint("TOP",0,0)
        s.dcSocket=true
        s.name=column:CreateFontString(nil,"OVERLAY","GameFontNormalSmall");s.name:SetPoint("TOP",s,"BOTTOM",0,-8);s.name:SetWidth(124)
        s.stat=column:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall");s.stat:SetPoint("TOP",s.name,"BOTTOM",0,-2);s.stat:SetWidth(124)
        s.column=column
        s:RegisterForClicks("LeftButtonUp");s:RegisterForDrag("LeftButton")
        local function receive() J.DropOnSocket(view,index) end
        s:SetScript("OnClick",receive);s:SetScript("OnReceiveDrag",receive)
        s:SetScript("OnDragStart",function() trace("OnDragStart",index);J.GemPicked(view,index) end)
        s:SetScript("OnDragStop",function() trace("OnDragStop",index);J.GemReleased(view,index) end)
        -- Backups for a client that does not deliver the drag events: a press on a filled socket arms a
        -- pull that starts once the cursor has moved, and the tracker below ends it when the button is up.
        s:SetScript("OnMouseDown",function(_,mouseButton)
            local socket=view.item and view.item.sockets[index]
            if mouseButton~="LeftButton" or not socket or socket.gemEntry==0 then return end
            local x,y=cursorPoint()
            if x then J.armed={view=view,index=index,x=x,y=y} end
        end)
        s:SetScript("OnMouseUp",function() J.armed=nil;if J.carry then J.GemReleased(J.carry.view,J.carry.index) end end)
        s:SetScript("OnEnter",function(self)
            local socket=view.item and view.item.sockets[index]
            if socket and socket.gemEntry~=0 then gemTip(self,socket.gemEntry,gemName(socket.gemEntry) or socket.name) end
        end)
        s:SetScript("OnLeave",function() GameTooltip:Hide() end)
        return s
    end
    -- Show `item` (a model item or nil) and its sockets from what the model holds now.
    function view:Render()
        local item=self.item and itemOf(self.item.guid)
        self.item=item
        if not item then
            self.slot.icon:SetTexture(nil);self.name:SetText("");self.kind:SetText("");self.note:SetText("")
            self.hint:Show();self.clear:Hide();U.boxActive(self.box,false)
            for _,s in ipairs(self.sockets) do s.column:Hide() end
            self.foot:SetText("")
            if self.removeAll then self.removeAll:Hide() end
            return
        end
        self.hint:Hide();self.clear:Show();U.boxActive(self.box,true)
        self.slot.icon:SetTexture(iconOf(item.entry))
        local _,_,quality,_,_,_,_,_,equip=GetItemInfo(item.entry)
        local rgb=quality and GetItemQualityColor and {GetItemQualityColor(quality)} or {1,.5,0}
        self.name:SetText(item.name);self.name:SetTextColor(rgb[1],rgb[2],rgb[3])
        self.kind:SetText(equip and _G[equip] or "")
        self.note:SetText("Gems in this item give their "..(SLOT_LABEL[item.slotClass] or "Other").." effect.")
        for index,socket in ipairs(item.sockets) do
            local s=self.sockets[index]
            if not s then
                s=socketSlot(index);self.sockets[index]=s
            end
            s.column:ClearAllPoints()
            local across=(index-1-(#item.sockets-1)/2)*136
            s.column:SetPoint("TOP",self.root,"TOP",across,-124)
            s.column:Show()
            if socket.gemEntry~=0 then
                local name=gemName(socket.gemEntry) or socket.name
                s.icon:SetTexture(iconOf(socket.gemEntry))
                s.name:SetText(name);colour(s.name,gemColour(name))
                local line=Logic.effect(tables,socket.gemEntry,item.slotClass)
                if Logic.legendary(tables,socket.gemEntry) then line="Legendary Gem" end
                s.stat:SetText(line or "");colour(s.stat,WHITE)
            else
                s.icon:SetTexture(nil)
                s.name:SetText("Empty socket");colour(s.name,GREY)
                s.stat:SetText("Drop a gem here");colour(s.stat,GREY)
            end
        end
        for index=#item.sockets+1,#self.sockets do self.sockets[index].column:Hide() end
        if self.removeAll then
            local gems=0
            for _,socket in ipairs(item.sockets) do if socket.gemEntry~=0 then gems=gems+1 end end
            self.removeAll:Show()
            if gems>0 and not chain then self.removeAll:Enable() else self.removeAll:Disable() end
        end
        self.foot:SetText(self.compact and "Away from the Jeweler you can fill empty sockets. Removing or swapping gems needs the Jeweler."
            or atJeweler() and "Socketing and removing gems is free. Both the item and the gems come back intact."
            or "Away from the Jeweler you can fill empty sockets. Removing or swapping gems needs the Jeweler.")
    end
    view.compact=compact
    return view
end

-- Dropped on a socket: a gem goes in. Filling an empty socket works anywhere; replacing a gem is the
-- Jeweler's, and away from it the gem snaps back with the Jeweler's message.
function J.SocketGem(view,index,gemGuid)
    local item=view.item
    local socket=item and item.sockets[index]
    if not socket then return end
    if not Logic.mayChange(atJeweler(),socket.gemEntry~=0) then say(AWAY_MESSAGE,true);return end
    send("socket",item.guid,socket.seq,gemGuid)
end
function J.DropOnSocket(view,index)
    local kind,thing=cursorThing()
    local item=view.item
    local socket=item and item.sockets[index]
    if kind~="gem" or not socket then return end
    ClearCursor()
    J.SocketGem(view,index,thing.guid)
end
-- A socketed gem is picked up by dragging it off its socket.
function J.GemPicked(view,index)
    local socket=view.item and view.item.sockets[index]
    if not socket or socket.gemEntry==0 then return end
    view.carrying=index
    J.armed=nil;J.carry={view=view,index=index}
    ghost.icon:SetTexture(iconOf(socket.gemEntry));ghost:Show()
end
local function overSocket(view)
    local x,y=cursorPoint()
    if not x then return false end
    for _,s in ipairs(view.sockets) do if covers(s,x,y) then return true end end
    return false
end
-- Let go: on a socket nothing moves; anywhere else the gem comes out, free, and goes back to the bags.
-- Where "on a socket" is is judged by the cursor's position against the slots, not by the mouse focus.
function J.GemReleased(view,index)
    J.carry=nil
    if view.carrying~=index then return end
    view.carrying=nil;ghost:Hide()
    local item=view.item
    local socket=item and item.sockets[index]
    if not socket or socket.gemEntry==0 then return end
    local over=overSocket(view)
    trace("released","over a socket:",over,"at the Jeweler:",atJeweler())
    if over then return end
    if not Logic.mayChange(atJeweler(),true) then say(AWAY_MESSAGE,true);return end
    send("remove",item.guid,socket.seq)
end
-- Ends a pull whose drag events never came, or whose stop never did: the press is armed and the cursor moved,
-- or the button is up. The button has to have been seen down first, so a client that answers
-- IsMouseButtonDown wrongly can never end a pull by itself.
local tracker=CreateFrame("Frame")
tracker:SetScript("OnUpdate",function()
    local armed,carry=J.armed,J.carry
    if not armed and not carry then return end
    if IsMouseButtonDown("LeftButton") then
        if carry then carry.seenDown=true end
        if armed then
            local x,y=cursorPoint()
            if x and math.abs(x-armed.x)+math.abs(y-armed.y)>8 then trace("pull started by movement");J.GemPicked(armed.view,armed.index);if J.carry then J.carry.seenDown=true end end
        end
    else
        J.armed=nil
        if carry and carry.seenDown then trace("pull ended by the button");J.GemReleased(carry.view,carry.index) end
    end
end)

----------------------------------------------------------------------------------------------------
-- The Jeweler window
----------------------------------------------------------------------------------------------------
frame=U.window("DiablocraftJewelerFrame",nil,nil,"jeweler")
local title=U.title(frame,"Covetous Shen")
local sub=U.subtitle(frame)
local closeX=U.close(frame)

-- Combine Gems -------------------------------------------------------------------------------------
local combine=CreateFrame("Frame",nil,frame)
combine:SetPoint("TOPLEFT",16,-64);combine:SetPoint("BOTTOMRIGHT",-16,16)
local check=CreateFrame("CheckButton","DCJewelerHaveMats",combine,"UICheckButtonTemplate")
check:SetPoint("TOPLEFT",-4,0);check:SetSize(24,24)
local checkText=_G["DCJewelerHaveMatsText"];if checkText then checkText:SetText("Have materials");colour(checkText,GOLD) end
local scroll=U.scroll(CreateFrame("ScrollFrame","DCJewelerListScroll",combine,"UIPanelScrollFrameTemplate"))
scroll:SetPoint("TOPLEFT",0,-28);scroll:SetSize(214,336)
local list=CreateFrame("Frame",nil,scroll);list:SetSize(214,336);scroll:SetScrollChild(list)
local searchBox=U.input(combine,"DCJewelerSearch")
searchBox:SetSize(214,20);searchBox:SetPoint("TOPLEFT",6,-372);searchBox:SetMaxLetters(40)
local searchHint=searchBox:CreateFontString(nil,"OVERLAY","GameFontDisableSmall");searchHint:SetPoint("LEFT",6,0);searchHint:SetText("Search")

local detail=CreateFrame("Frame",nil,combine)
detail:SetPoint("TOPLEFT",246,-4);detail:SetSize(270,368)
flat(detail,U.DETAIL_BG[1],U.DETAIL_BG[2],U.DETAIL_BG[3],U.DETAIL_BORDER[1],U.DETAIL_BORDER[2],U.DETAIL_BORDER[3])
detail.icon=slot(detail,54);detail.icon:SetPoint("TOPLEFT",12,-12)
detail.name=text(detail,76,-18,186,"GameFontNormalLarge")
detail.kind=text(detail,76,-40,186,"GameFontHighlightSmall");colour(detail.kind,GREY);detail.kind:SetText("Gem")
detail.effects={}
for index=1,3 do detail.effects[index]=text(detail,14,-80-(index-1)*16,246,"GameFontHighlightSmall") end
detail.reqTitle=text(detail,14,-142,246,"GameFontNormal");detail.reqTitle:SetText("Required materials")
detail.reagents={}
-- The material line is the shared one (DCUI), so the Jeweler's cannot drift from the
-- Blacksmith's: name on the first line, grouped have/need count on the second.
for index=1,2 do detail.reagents[index]=U.material(detail,14,-164-(index-1)*48,196) end
detail.cost=text(detail,14,-270,246,"GameFontHighlight")

local createAll=button(combine,90,"Create All",function() J.CreateAll() end);createAll:SetPoint("TOPLEFT",246,-376)
local qtyDown=button(combine,22,"<",function() J.SetQty(qty-1) end);qtyDown:SetPoint("TOPLEFT",344,-376)
local qtyBox=U.input(combine,"DCJewelerQty")
qtyBox:SetSize(40,20);qtyBox:SetPoint("TOPLEFT",376,-377);qtyBox:SetNumeric(true);qtyBox:SetMaxLetters(10)
qtyBox:SetJustifyH("CENTER")
local qtyUp=button(combine,22,">",function() J.SetQty(qty+1) end);qtyUp:SetPoint("TOPLEFT",422,-376)
local createOne=button(combine,80,"Create",function() J.Create(qty) end);createOne:SetPoint("TOPLEFT",450,-376)
local funds=text(combine,0,-410,512,"GameFontNormal")

-- The combine bar: one 2 s gold bar in the bottom row, left of Create All, per click that passes the checks,
-- whatever the quantity. It is the window's own, not the player's cast bar. Nothing is used and nothing is sent
-- until it is full; then today's combine request goes once for that quantity. Closing the window, Esc and
-- leaving the Jeweler cancel it with a red line and send nothing.
local COMBINE_SECONDS=2
local CANCELLED="Combining cancelled. Nothing was used."
local bar=U.bar(combine)
local lockable={}
local function lock(locked)
    for _,control in ipairs(lockable) do
        if locked then control:Disable() else control:Enable() end
    end
    qtyBox:EnableMouse(not locked)
    if locked then qtyBox:ClearFocus() end
end
for _,control in ipairs({createAll,createOne,qtyUp,qtyDown}) do lockable[#lockable+1]=control end
function J.Combining() return bar.job end
local function endBar()
    bar.job=nil;bar:SetScript("OnUpdate",nil);bar:Hide();lock(false)
end
function J.CancelCombine()
    if not bar.job then return false end
    endBar()
    say(CANCELLED,true)
    return true
end
local function barUpdate(self,elapsed)
    local job=self.job
    if not job then return end
    job.elapsed=job.elapsed+elapsed
    self:SetValue(math.min(1,job.elapsed/COMBINE_SECONDS))
    if job.elapsed<COMBINE_SECONDS then return end
    endBar()
    send("combine",job.recipe,job.count)
    render()
end
-- Closing the window (the X, Esc) and the gossip ending (walking away from the Jeweler) cancel a running bar.
frame:SetScript("OnHide",function() J.CancelCombine();J.CancelCraft();if J.restoreIds then J.restoreIds() end end)
frame:RegisterEvent("GOSSIP_CLOSED")
frame:RegisterEvent("PLAYER_REGEN_DISABLED")
frame:SetScript("OnEvent",function(_,event)
    -- Entering combat: any button id this file blanked for a click is put back at once, and nothing else here
    -- touches a bag or sheet button in combat. A running combine bar is cancelled as well, like the
    -- Blacksmith's (12-ui §3).
    if event=="PLAYER_REGEN_DISABLED" and J.restoreIds then J.restoreIds() end
    J.CancelCombine();J.CancelCraft()
end)
function J.StartCombine(recipe,count)
    bar.job={recipe=recipe.id,count=count,elapsed=0}
    bar.fill:SetWidth(1)
    bar.text:SetText("Combining "..count.." "..recipe.name)
    bar:SetScript("OnUpdate",barUpdate)
    bar:Show();lock(true)
end

local rowButtons={}
local function rowButton(index)
    local b=rowButtons[index]
    if b then return b end
    b=U.row(list);b:SetWidth(210)
    b:SetScript("OnClick",function(self)
        local row=self.row
        if not row then return end
        if row.head then collapsed[row.head]=not collapsed[row.head];render();return end
        J.Select(row.recipe.id)
    end)
    b:SetScript("OnEnter",function(self)
        local row=self.row
        if row and row.recipe then gemTip(self,row.recipe.id,row.recipe.name) end
    end)
    b:SetScript("OnLeave",function() GameTooltip:Hide() end)
    rowButtons[index]=b
    return b
end

local function recipeById(id)
    for _,recipe in ipairs(model.recipes or {}) do if recipe.id==id then return recipe end end
end
local function maxCraft()
    local recipe=recipeById(selected)
    return recipe and Logic.craftable(recipe,model.balance) or 0
end
function J.Select(id)
    if bar.job then return end
    selected=id;qty=1;render()
end
-- The quantity is clamped to 1..the most that can be made; typing, the arrows and a new selection all go
-- through here.
function J.SetQty(value)
    if bar.job then return end
    qty=Logic.clampQty(value,maxCraft())
    render()
end
function J.Create(count)
    if bar.job then return false end
    local recipe=recipeById(selected)
    if not recipe then return false end
    -- Create and Create All are greyed out whenever the selected recipe cannot be made even
    -- once (the Blacksmith's behaviour, now both windows'), so a click with
    -- nothing makeable never gets here. A request still waiting for its reply is not stacked on.
    if maxCraft()<1 then return false end
    local n=Logic.clampQty(count,maxCraft())
    if awaiting and GetTime()-awaiting<=3 then return false end
    J.StartCombine(recipe,n)
    return true
end
-- Create All makes what the materials allow, in one request; greyed out when nothing can be made.
function J.CreateAll()
    return J.Create(math.max(1,maxCraft()))
end

local function renderCombine()
    local balance=model.balance
    local rows=Logic.rows(model.recipes,balance,{haveMats=haveMats,search=search,collapsed=collapsed})
    if not recipeById(selected) then
        for _,row in ipairs(rows) do if row.recipe then selected=row.recipe.id;break end end
    end
    local y=0
    for index,row in ipairs(rows) do
        local b=rowButton(index);b.row=row
        b:ClearAllPoints();b:SetPoint("TOPLEFT",0,-y)
        if row.head then
            b.label:SetText((row.closed and "+ " or "- ")..row.head);colour(b.label,GOLD);b.label:SetPoint("LEFT",U.HEAD_INDENT,0);b.mark:Hide()
            y=y+U.HEAD_STEP
        else
            b.label:SetText(Logic.rowText(row));colour(b.label,row.n>=1 and WHITE or GREY);b.label:SetPoint("LEFT",U.ROW_INDENT,0)
            if row.recipe.id==selected then b.mark:Show() else b.mark:Hide() end
            y=y+U.ROW_HEIGHT
        end
        b:Show()
    end
    for index=#rows+1,#rowButtons do rowButtons[index].row=nil;rowButtons[index]:Hide() end
    list:SetHeight(math.max(336,y))
    qty=Logic.clampQty(qty,maxCraft())
    if not qtyBox:HasFocus() then qtyBox:SetText(tostring(qty)) end
    local recipe=recipeById(selected)
    if recipe then
        local tint=gemColour(recipe.name)
        detail.icon.icon:SetTexture(iconOf(recipe.id))
        detail.name:SetText(recipe.name);detail.name:SetTextColor(tint[1],tint[2],tint[3])
        for index,key in ipairs(SLOT_ORDER) do
            local line=Logic.effect(tables,recipe.id,key)
            detail.effects[index]:SetText(line and (SLOT_LABEL[key]..": "..line) or "")
        end
        local needGems=(recipe.inputCount or 1)*qty
        local have=recipe.have or 0
        local needs={{iconOf(recipe.inputEntry),recipe.inputName,have,needGems,have>=needGems}}
        if (recipe.deathsBreath or 0)>0 then
            local need=recipe.deathsBreath*qty
            needs[2]={iconOf(102000),"Death's Breath",model.balance.deathsBreath,need,Logic.atLeast(model.balance.deathsBreath,need)}
        end
        for index,r in ipairs(detail.reagents) do
            local need=needs[index]
            if need then
                -- The count, its colour and the name's colour are the shared setter's (UI fixes row 4).
                r.icon:SetTexture(need[1]);r.label:SetText(need[2]);U.count(r,need[3],need[4],need[5])
                r:Show();r.label:Show()
            else r:Hide();r.label:Hide() end
        end
        local cost=(recipe.gold or 0)*qty
        detail.cost:SetText("Cost: "..commas(cost).." gold")
        colour(detail.cost,Logic.atLeast(model.balance.gold,cost) and WHITE or RED)
        detail.icon:SetScript("OnEnter",function(self) gemTip(self,recipe.id,recipe.name) end)
        detail.icon:SetScript("OnLeave",function() GameTooltip:Hide() end)
    else
        detail.name:SetText("");detail.cost:SetText("")
        for _,line in ipairs(detail.effects) do line:SetText("") end
        for _,r in ipairs(detail.reagents) do r:Hide();r.label:Hide() end
    end
    funds:SetText("Your gold: "..commas(balance.gold).."      Death's Breath: "..commas(balance.deathsBreath))
    -- Create and Create All are greyed out whenever the selected recipe cannot be made even once
    -- and the running bar's lock(true) owns all four controls while it runs.
    local makeable=recipe and Logic.craftable(recipe,balance) or 0
    if bar.job then
        -- left to lock(true)
    elseif makeable>=1 then createAll:Enable();createOne:Enable()
    else createAll:Disable();createOne:Disable() end
end
check:SetScript("OnClick",function(self) haveMats=self:GetChecked() and true or false;render() end)
searchBox:SetScript("OnTextChanged",function(self)
    search=self:GetText() or ""
    if search=="" then searchHint:Show() else searchHint:Hide() end
    render()
end)
searchBox:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
searchBox:SetScript("OnEnterPressed",function(self) self:ClearFocus() end)
qtyBox:SetScript("OnTextChanged",function(self,user)
    if not user or bar.job then return end
    local value=tonumber(self:GetText())
    if not value then return end
    qty=Logic.clampQty(value,maxCraft())
    -- A number beyond what can be made is shown as the number that will be made.
    if tostring(qty)~=self:GetText() then self:SetText(tostring(qty)) end
    render()
end)
qtyBox:SetScript("OnEditFocusLost",function(self) self:SetText(tostring(qty)) end)
qtyBox:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
qtyBox:SetScript("OnEnterPressed",function(self) self:ClearFocus();J.Create(qty) end)

-- Craft Jewelry ------------------------------------------------------------------------------------
-- Laid out like the Blacksmith's Forge tabs: a list under page headers (Amulets, Rings) with the
-- "[n] " count of what can be made, a search box, the recipe's details with its materials, a cast bar
-- and Create All / quantity / Create. The catalogue and what the player holds come with Show.
local craft=CreateFrame("Frame",nil,frame)
craft:SetPoint("TOPLEFT",16,-64);craft:SetPoint("BOTTOMRIGHT",-16,16)
local craftCheck=CreateFrame("CheckButton","DCJewelerCraftHaveMats",craft,"UICheckButtonTemplate")
craftCheck:SetPoint("TOPLEFT",-4,0);craftCheck:SetSize(24,24)
local craftCheckText=_G["DCJewelerCraftHaveMatsText"];if craftCheckText then craftCheckText:SetText("Have materials");colour(craftCheckText,GOLD) end
local craftScroll=U.scroll(CreateFrame("ScrollFrame","DCJewelerCraftScroll",craft,"UIPanelScrollFrameTemplate"))
craftScroll:SetPoint("TOPLEFT",0,-28);craftScroll:SetSize(214,336)
local craftList=CreateFrame("Frame",nil,craftScroll);craftList:SetSize(214,336);craftScroll:SetScrollChild(craftList)
local craftSearchBox=U.input(craft,"DCJewelerCraftSearch")
craftSearchBox:SetSize(214,20);craftSearchBox:SetPoint("TOPLEFT",6,-372);craftSearchBox:SetMaxLetters(40)
local craftSearchHint=craftSearchBox:CreateFontString(nil,"OVERLAY","GameFontDisableSmall");craftSearchHint:SetPoint("LEFT",6,0);craftSearchHint:SetText("Search")

local craftDetail=CreateFrame("Frame",nil,craft)
craftDetail:SetPoint("TOPLEFT",246,-4);craftDetail:SetSize(270,368)
flat(craftDetail,U.DETAIL_BG[1],U.DETAIL_BG[2],U.DETAIL_BG[3],U.DETAIL_BORDER[1],U.DETAIL_BORDER[2],U.DETAIL_BORDER[3])
craftDetail.icon=slot(craftDetail,54);craftDetail.icon:SetPoint("TOPLEFT",12,-12)
craftDetail.name=text(craftDetail,76,-18,186,"GameFontNormalLarge")
craftDetail.level=text(craftDetail,76,-40,186,"GameFontHighlightSmall");colour(craftDetail.level,GREY)
craftDetail.note=text(craftDetail,14,-58,246,"GameFontHighlightSmall");craftDetail.note:SetHeight(44)
craftDetail.reqTitle=text(craftDetail,14,-142,246,"GameFontNormal");craftDetail.reqTitle:SetText("Required materials")
craftDetail.cost=text(craftDetail,14,-336,246,"GameFontHighlight")
craftDetail.reagents={}
for index=1,8 do
    local r=U.material(craftDetail,10+((index-1)%2)*128,-164-math.floor((index-1)/2)*40,76)
    r:SetScript("OnEnter",function(self) if self.entry then J.ItemTip(self,self.entry) end end)
    r:SetScript("OnLeave",function() GameTooltip:Hide() end)
    craftDetail.reagents[index]=r
end
local craftAll=button(craft,90,"Create All",function() J.CraftAll() end);craftAll:SetPoint("TOPLEFT",246,-376)
local craftDown=button(craft,22,"<",function() J.SetCraftQty(craftQty-1) end);craftDown:SetPoint("TOPLEFT",344,-376)
local craftQtyBox=U.input(craft,"DCJewelerCraftQty")
craftQtyBox:SetSize(40,20);craftQtyBox:SetPoint("TOPLEFT",376,-377);craftQtyBox:SetNumeric(true);craftQtyBox:SetMaxLetters(4)
craftQtyBox:SetJustifyH("CENTER")
local craftUp=button(craft,22,">",function() J.SetCraftQty(craftQty+1) end);craftUp:SetPoint("TOPLEFT",422,-376)
local craftOne=button(craft,80,"Create",function() J.Craft(craftQty) end);craftOne:SetPoint("TOPLEFT",450,-376)
local craftFunds=text(craft,0,-410,512,"GameFontNormal")

-- The cast bar: the same 2 s bar as Combine Gems, once for the whole quantity; the request goes when it is
-- full. Closing the window, Esc, another tab and leaving the Jeweler cancel it with a red line, sending nothing.
local CRAFT_CANCELLED="Crafting cancelled. Nothing was used."
local craftBar=U.bar(craft)
local craftLock={craftAll,craftOne,craftUp,craftDown}
local function craftLocked(locked)
    for _,control in ipairs(craftLock) do
        if locked then control:Disable() else control:Enable() end
    end
    craftQtyBox:EnableMouse(not locked);craftSearchBox:EnableMouse(not locked)
    if locked then craftQtyBox:ClearFocus();craftSearchBox:ClearFocus() end
end
function J.Crafting() return craftBar.job end
local function endCraftBar()
    craftBar.job=nil;craftBar:SetScript("OnUpdate",nil);craftBar:Hide();craftLocked(false)
end
function J.CancelCraft()
    if not craftBar.job then return false end
    endCraftBar()
    say(CRAFT_CANCELLED,true)
    return true
end
local function craftBarUpdate(self,delta)
    local job=self.job
    if not job then return end
    job.elapsed=job.elapsed+delta
    self:SetValue(math.min(1,job.elapsed/COMBINE_SECONDS))
    if job.elapsed<COMBINE_SECONDS then return end
    endCraftBar()
    send("craft",job.recipe,job.count)
    render()
end
function J.StartCraft(recipe,count)
    craftBar.job={recipe=recipe.id,count=count,elapsed=0}
    craftBar.fill:SetWidth(1)
    craftBar.text:SetText("Crafting "..count.." "..recipe.name)
    craftBar:SetScript("OnUpdate",craftBarUpdate)
    craftBar:Show();craftLocked(true)
end

-- The output item's tooltip (the base item; the rolled item shows its properties once made) and a
-- material's.
function J.ItemTip(owner,entry)
    tooltip(owner,function(tip) tip:SetHyperlink("item:"..entry..":0:0:0:0:0:0:0") end)
end
local craftButtons={}
local function craftButton(index)
    local b=craftButtons[index]
    if b then return b end
    b=U.row(craftList);b:SetWidth(210)
    b:SetScript("OnClick",function(self)
        local row=self.row
        if not row then return end
        if row.head then craftCollapsed[row.page]=not craftCollapsed[row.page];render();return end
        J.SelectCraft(row.recipe.id)
    end)
    b:SetScript("OnEnter",function(self)
        local row=self.row
        if row and row.recipe then J.ItemTip(self,row.recipe.entry) end
    end)
    b:SetScript("OnLeave",function() GameTooltip:Hide() end)
    craftButtons[index]=b
    return b
end
local function craftById(id)
    for _,recipe in ipairs(model.crafts or {}) do if recipe.id==id then return recipe end end
end
local function maxMake()
    local recipe=craftById(craftSelected)
    return recipe and Logic.craftCount(recipe,model.balance,model.craftMax) or 0
end
function J.SelectCraft(id)
    if craftBar.job then return end
    craftSelected=id;craftQty=1;render()
end
function J.SetCraftQty(value)
    if craftBar.job then return end
    craftQty=Logic.clampQty(value,maxMake())
    render()
end
function J.Craft(count)
    if craftBar.job then return false end
    local recipe=craftById(craftSelected)
    if not recipe then return false end
    -- Create and Create All are greyed out while the selected recipe cannot be made even once.
    if maxMake()<1 then return false end
    local n=Logic.clampQty(count,maxMake())
    if awaiting and GetTime()-awaiting<=3 then return false end
    J.StartCraft(recipe,n)
    return true
end
function J.CraftAll()
    return J.Craft(math.max(1,maxMake()))
end
local CRAFT_TINT={set={.1,1,.1},legendary={1,.5,0},rare={1,1,0},magic={.3,.6,1},normal={1,1,1}}

local function renderCraft()
    local balance=model.balance
    local rows=Logic.craftRows(model.crafts,balance,model.craftMax,{haveMats=craftHave,search=craftSearch,collapsed=craftCollapsed})
    if not craftById(craftSelected) then
        for _,row in ipairs(rows) do if row.recipe then craftSelected=row.recipe.id;break end end
    end
    local y=0
    for index,row in ipairs(rows) do
        local b=craftButton(index);b.row=row
        b:ClearAllPoints();b:SetPoint("TOPLEFT",0,-y)
        if row.head then
            b.label:SetText((row.closed and "+ " or "- ")..row.head);colour(b.label,GOLD);b.label:SetPoint("LEFT",U.HEAD_INDENT,0);b.mark:Hide()
            y=y+U.HEAD_STEP
        else
            b.label:SetText(Logic.rowText({n=row.n,recipe=row.recipe}));colour(b.label,row.n>=1 and WHITE or GREY);b.label:SetPoint("LEFT",U.ROW_INDENT,0)
            if row.recipe.id==craftSelected then b.mark:Show() else b.mark:Hide() end
            y=y+U.ROW_HEIGHT
        end
        b:Show()
    end
    for index=#rows+1,#craftButtons do craftButtons[index].row=nil;craftButtons[index]:Hide() end
    craftList:SetHeight(math.max(336,y))
    craftQty=Logic.clampQty(craftQty,maxMake())
    if not craftQtyBox:HasFocus() then craftQtyBox:SetText(tostring(craftQty)) end
    local recipe=craftById(craftSelected)
    if recipe then
        local tint=CRAFT_TINT[recipe.rarity] or WHITE
        craftDetail.icon.icon:SetTexture(iconOf(recipe.entry))
        craftDetail.name:SetText(recipe.name);craftDetail.name:SetTextColor(tint[1],tint[2],tint[3])
        craftDetail.level:SetText("Level "..recipe.required.." \226\128\162 "..recipe.rarity)
        craftDetail.note:SetText(recipe.enabled and "" or recipe.reason)
        colour(craftDetail.note,recipe.enabled and GREY or RED)
        craftDetail.icon:SetScript("OnEnter",function(self) J.ItemTip(self,recipe.entry) end)
        craftDetail.icon:SetScript("OnLeave",function() GameTooltip:Hide() end)
        local cost=(tonumber(recipe.gold) or 0)*craftQty
        craftDetail.cost:SetText("Cost: "..commas(string.format("%.0f",cost)).." gold")
        colour(craftDetail.cost,Logic.atLeast(balance.gold,cost) and WHITE or RED)
        for index,r in ipairs(craftDetail.reagents) do
            local material=recipe.materials[index]
            if material then
                local need=material.amount*craftQty
                r.entry=material.entry;r.icon:SetTexture(iconOf(material.entry));r.label:SetText(material.name)
                U.count(r,material.have,need,Logic.atLeast(material.have,need))
                r:Show();r.label:Show()
            else r.entry=nil;r:Hide();r.label:Hide() end
        end
    else
        craftDetail.name:SetText("Select a recipe");colour(craftDetail.name,GOLD)
        craftDetail.level:SetText("");craftDetail.note:SetText("");craftDetail.cost:SetText("")
        craftDetail.icon.icon:SetTexture(nil)
        for _,r in ipairs(craftDetail.reagents) do r.entry=nil;r:Hide();r.label:Hide() end
    end
    craftFunds:SetText("Your gold: "..commas(balance.gold))
    local makeable=recipe and Logic.craftCount(recipe,balance,model.craftMax) or 0
    if craftBar.job then
        -- left to craftLocked(true)
    elseif makeable>=1 then craftAll:Enable();craftOne:Enable()
    else craftAll:Disable();craftOne:Disable() end
end
craftCheck:SetScript("OnClick",function(self) craftHave=self:GetChecked() and true or false;render() end)
craftSearchBox:SetScript("OnTextChanged",function(self)
    craftSearch=self:GetText() or ""
    if craftSearch=="" then craftSearchHint:Show() else craftSearchHint:Hide() end
    craftScroll:SetVerticalScroll(0)
    render()
end)
craftSearchBox:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
craftSearchBox:SetScript("OnEnterPressed",function(self) self:ClearFocus() end)
craftQtyBox:SetScript("OnTextChanged",function(self,user)
    if not user or craftBar.job then return end
    local value=tonumber(self:GetText())
    if not value then return end
    craftQty=Logic.clampQty(value,maxMake())
    if tostring(craftQty)~=self:GetText() then self:SetText(tostring(craftQty)) end
    render()
end)
craftQtyBox:SetScript("OnEditFocusLost",function(self) self:SetText(tostring(craftQty)) end)
craftQtyBox:SetScript("OnEscapePressed",function(self) self:ClearFocus() end)
craftQtyBox:SetScript("OnEnterPressed",function(self) self:ClearFocus();J.Craft(craftQty) end)

-- Unsocket Gems -------------------------------------------------------------------------------------
local socketView=newView(frame,false)
socketView.root:SetPoint("TOPLEFT",frame,"TOPLEFT",16,-70);socketView.root:SetPoint("BOTTOMRIGHT",frame,"BOTTOMRIGHT",-16,16)

-- The two icon tabs on the right edge ---------------------------------------------------------------
local TABS={{key="combine",label="Combine Gems",icon="Interface\\Icons\\INV_Misc_Gem_Emerald_01"},
    {key="socket",label="Unsocket Gems",icon="Interface\\Icons\\INV_Misc_Gem_Ruby_01"},
    {key="craft",label="Craft Jewelry",icon="Interface\\Icons\\INV_Jewelry_Ring_03"}}
local tabButtons={}
for index,def in ipairs(TABS) do
    local b=U.tab(frame,48);b:SetPoint("TOPLEFT",frame,"TOPRIGHT",-2,-70-(index-1)*56)
    b.icon:SetTexture(def.icon);b.def=def
    b:SetScript("OnClick",function() tab=def.key;render() end)
    b:SetScript("OnEnter",function(self) tooltip(self,function(tip) tip:SetText(def.label) end) end)
    b:SetScript("OnLeave",function() GameTooltip:Hide() end)
    tabButtons[index]=b
end

render=function()
    if not frame:IsShown() then return end
    local showCombine,showCraft=tab=="combine",tab=="craft"
    for _,def in ipairs(TABS) do if def.key==tab then sub:SetText(def.label:upper()) end end
    for _,b in ipairs(tabButtons) do U.tabActive(b,b.def.key==tab) end
    -- Leaving a tab with a running bar cancels it, so none completes out of sight.
    if not showCombine then J.CancelCombine() end
    if not showCraft then J.CancelCraft() end
    local showSocket=not showCombine and not showCraft
    if showSocket and J.ScanClickButtons then J.ScanClickButtons() end
    if not showSocket and J.restoreIds then J.restoreIds() end
    if showCombine then combine:Show() else combine:Hide() end
    if showCraft then craft:Show() else craft:Hide() end
    if showSocket then socketView.root:Show() else socketView.root:Hide() end
    if showCombine then renderCombine() elseif showCraft then renderCraft() else socketView:Render() end
end

-- The Sockets window --------------------------------------------------------------------------------
-- DCUI's window at its own size (UI fixes row 3): the backdrop, drag, Esc and title are the
-- shared ones; it keeps its old spot, centred.
sockFrame=U.window("DiablocraftSocketsFrame",480,400)
sockFrame:ClearAllPoints();sockFrame:SetPoint("CENTER",0,0)
local sockTitle=U.title(sockFrame,"Sockets")
local sockClose=U.close(sockFrame)
local sockView=newView(sockFrame,true)
sockView.root:SetPoint("TOPLEFT",sockFrame,"TOPLEFT",16,-48);sockView.root:SetPoint("BOTTOMRIGHT",sockFrame,"BOTTOMRIGHT",-16,16)

-- The frames the tests read and drive.
J.ui={frame=frame,sockFrame=sockFrame,socketView=socketView,sockView=sockView,tabs=tabButtons,list=list,scroll=scroll,
    bar=bar,qtyBox=qtyBox,searchBox=searchBox,check=check,createAll=createAll,createOne=createOne,qtyUp=qtyUp,qtyDown=qtyDown,
    detail=detail,funds=funds,title=title,sub=sub,craft=craft,craftList=craftList,craftScroll=craftScroll,craftBar=craftBar,
    craftQtyBox=craftQtyBox,craftSearchBox=craftSearchBox,craftCheck=craftCheck,craftAll=craftAll,craftOne=craftOne,craftUp=craftUp,
    craftDown=craftDown,craftDetail=craftDetail,craftFunds=craftFunds}
renderAll=function()
    if frame:IsShown() then render() end
    if sockFrame:IsShown() then sockView:Render() end
end

-- Shift+Right-click on a socketed item. At the Jeweler it opens the Unsocket Gems tab; anywhere else the
-- small Sockets window. The stock socket frame is not ours and is put away if it opened as well.
function J.OpenSockets(bag,slotIndex)
    if ItemSocketingFrame and ItemSocketingFrame:IsShown() then HideUIPanel(ItemSocketingFrame) end
    if not whole(bag) or not whole(slotIndex) then return end
    pending={open=true,bag=bag,slot=slotIndex}
    AIO.Handle(CHANNEL,"Gear",bag,slotIndex,0)
end
local function openFor(item)
    if frame:IsShown() then
        tab="socket";socketView.item=item;render()
    else
        sockView.item=item;sockFrame:Show();sockView:Render()
    end
end

-- Remove Gems: every gem out of the loaded item into the bags, at the Jeweler. One removal request per gem, the
-- same request the drag-off sends, one after the next as each reply comes in; no new verb. Its refusals are the
-- server's (bags full, gold). Before the first request the client checks the free bag slots for the whole lot, so
-- a full bag is refused up front and not half way; a refusal from the server ends the run.
local function nextRemove()
    if not chain then return end
    chain.i=chain.i+1
    local seq=chain.seqs[chain.i]
    if not seq or not frame:IsShown() then chain=nil;return end
    if not send("remove",chain.guid,seq) then chain=nil end
end
J.nextRemove=nextRemove
function J.RemoveAll(view)
    local item=view.item
    if not item or chain or not atJeweler() then return false end
    local seqs={}
    for _,socket in ipairs(item.sockets) do if socket.gemEntry~=0 then seqs[#seqs+1]=socket.seq end end
    if #seqs==0 then return false end
    if GetContainerNumFreeSlots then
        local free=0
        for bagId=0,4 do
            local slots,kind=GetContainerNumFreeSlots(bagId)
            if slots and (kind or 0)==0 then free=free+slots end
        end
        if free<#seqs then say("Not enough bag space: "..#seqs.." free slots are needed.",true);return false end
    end
    chain={guid=item.guid,seqs=seqs,i=0}
    nextRemove()
    if chain then renderAll() end
    return true
end

-- Right-click loads an item while the Unsocket Gems tab is open, instead of equipping or using it, the way the
-- stock trade and socketing windows take one.
--
-- NO STOCK GLOBAL IS WRITTEN. ContainerFrameItemButton_OnClick and PaperDollItemSlotButton_OnClick are looked up by
-- name on every click by the bag and character-sheet buttons, so replacing either from addon code would run every
-- later click, in combat too, as tainted code. What is used instead are button-level script hooks, which are
-- secure-safe: HookScript("PreClick") and ("PostClick") on the bag and sheet buttons. PreClick runs before the
-- button's own OnClick, only for a right-click, only while the tab is open and never in combat, so nothing is
-- touched in combat at all. A hook cannot cancel the click, so PreClick turns it into a no-op: the button's id (its
-- slot) is set to a slot that holds nothing for the length of that one click, the stock OnClick then uses an empty
-- slot, and PostClick puts the id back (and so do the tab closing and combat starting).
--
-- Why the id swap works: ElvUI's bag slots are CheckButtons from ContainerFrameItemButtonTemplate (ElvUI Bags.lua:646),
-- the parent f.Bags[bagID] has SetID(bagID) (:631) and each slot SetID(slotID) (:703), and the stock OnClick reads both
-- (UseContainerItem(self:GetParent():GetID(), self:GetID())). The stock sheet's OnClick reads self:GetID() the same way.
-- TO POINT THIS AT THE NEW CHARACTER SHEET: add or change one row of CLICK_SOURCES. A row says where its buttons
-- are (`buttons`), how to read the item from one (`at`: bag+slot in the client's numbering, or nil,nil,guid, and
-- the item id so a gem can be told from gear) and which slot id is empty (`empty`). The Torment sheet's worn slots are
-- the addon's own function and are wrapped separately below; that block goes with that sheet.
local function entryOf(link) return link and tonumber(link:match("item:(%d+)")) end
local SHEET_SLOTS={"Head","Neck","Shoulder","Back","Chest","Shirt","Tabard","Wrist","Hands","Waist","Legs","Feet",
    "Finger0","Finger1","Trinket0","Trinket1","MainHand","SecondaryHand","Ranged"}
local blanked={}
local CLICK_SOURCES={
    {name="bags: ElvUI and stock",
     buttons=function()
         local found={}
         for frameNo=1,(NUM_CONTAINER_FRAMES or 13) do
             for itemNo=1,(MAX_CONTAINER_ITEMS or 36) do
                 local b=_G["ContainerFrame"..frameNo.."Item"..itemNo]
                 if b then found[#found+1]=b end
             end
         end
         local E=_G.ElvUI and _G.ElvUI[1]
         local Bags=E and E.GetModule and E:GetModule("Bags",true)
         local holder=Bags and Bags.BagFrame and Bags.BagFrame.Bags
         if holder then
             for bagId=0,4 do
                 for _,b in pairs(holder[bagId] or {}) do
                     if type(b)=="table" and b.HookScript then found[#found+1]=b end
                 end
             end
         end
         return found
     end,
     at=function(self)
         local parent=self:GetParent()
         local bagId,slotId=parent and parent:GetID(),self:GetID()
         if not bagId or not slotId or slotId<1 then return end
         return bagId,slotId,nil,entryOf(GetContainerItemLink(bagId,slotId))
     end,
     noRoom="Make room in that bag first.",
     empty=function(self)
         local bagId=self:GetParent():GetID()
         for slotId=1,(GetContainerNumSlots and GetContainerNumSlots(bagId) or 0) do
             if not GetContainerItemLink(bagId,slotId) then return slotId end
         end
         return nil   -- a full bag: there is no safe slot to point the stock click at
     end},
    {name="character sheet: stock and ElvUI",
     buttons=function()
         local found={}
         for _,name in ipairs(SHEET_SLOTS) do
             local b=_G["Character"..name.."Slot"]
             if b then found[#found+1]=b end
         end
         return found
     end,
     at=function(self)
         local slotId=self:GetID()
         if not slotId or slotId<1 then return end
         return 255,slotId-1,nil,entryOf(GetInventoryItemLink("player",slotId))
     end,
     noRoom="Free an equipment slot first.",
     empty=function(self)
         for slotId=1,19 do
             if slotId~=self:GetID() and not GetInventoryItemLink("player",slotId) then return slotId end
         end
         return nil   -- slot 0 is the ammo slot, a real one: never used as a stand-in
     end},
    {name="character sheet: Torment",
     blank=false,   -- the sheet's OnClick reads self.equipSlot, not the id: it defers to the claim instead
     buttons=function()
         local found={}
         for number=0,18 do
             local b=_G["DiablocraftGearSlot"..number] or _G["DiablocraftCosmeticSlot"..number]
             if b then found[#found+1]=b end
         end
         return found
     end,
     at=function(self)
         local worn=self.equipSlot
         if not worn or worn<0 or worn>18 then return end
         return 255,worn,nil,entryOf(GetInventoryItemLink("player",worn+1))
     end,
     noRoom="Free an equipment slot first.",
     empty=function() return true end},
}
local function takesRightClick()
    return frame:IsShown() and tab=="socket" and not (InCombatLockdown and InCombatLockdown())
end
local function isGem(entry) return entry and tables and tables.gems and tables.gems[entry] end
function J.LoadClicked(bagId,slotId,guid,entry)
    if isGem(entry) then return false end   -- a gem keeps its right-click
    pending={open=true,message=true}
    if guid then AIO.Handle(CHANNEL,"Gear",0,0,guid) else AIO.Handle(CHANNEL,"Gear",bagId,slotId,0) end
    return true
end
local function restoreIds()
    for btn,id in pairs(blanked) do btn:SetID(id) end
    blanked={}
end
J.restoreIds=restoreIds
local function postClick(self)
    local id=blanked[self]
    if id then self:SetID(id);blanked[self]=nil end
end
local hooked={}
-- Hook every bag and sheet button that exists and has not been hooked: on opening the tab and about once a second
-- while it is open (ElvUI builds its slots when the bags are first opened).
function J.ScanClickButtons()
    for _,source in ipairs(CLICK_SOURCES) do
        for _,btn in ipairs(source.buttons()) do
            if not hooked[btn] then
                hooked[btn]=true
                btn:HookScript("PreClick",function(self,mouseButton)
                    if mouseButton~="RightButton" or not takesRightClick() then return end
                    restoreIds()
                    -- Only a plain right-click with an empty cursor. A held item would be dropped into the stand-in
                    -- slot by the stock click, and a Shift/Ctrl/Alt right-click is the stock modified click
                    -- (Shift+Right-click is SocketContainerItem on the real slot, handled by the hooks below).
                    if GetCursorInfo and GetCursorInfo() then return end
                    if (IsShiftKeyDown and IsShiftKeyDown()) or (IsControlKeyDown and IsControlKeyDown())
                        or (IsAltKeyDown and IsAltKeyDown()) then return end
                    local bagId,slotId,guid,entry=source.at(self)
                    if not (bagId or guid) or isGem(entry) then return end
                    local spare=source.empty(self)
                    -- No empty slot to point the stock click at: nothing is loaded, the click is the stock one.
                    if not spare then say(source.noRoom,true);return end
                    if J.LoadClicked(bagId,slotId,guid,entry) and source.blank~=false then
                        blanked[self]=self:GetID()
                        self:SetID(spare)
                    end
                end)
                btn:HookScript("PostClick",postClick)
            end
        end
    end
end
-- The Torment sheet's worn slots are a CLICK_SOURCES row above ("character sheet: Torment"), hooked like the
-- others. Their own right-click (take the item off) is the sheet's OnClick, which cannot be id-swapped, so the
-- sheet asks Diablocraft.ClaimRightClick claims first: the claim below is takesRightClick, so while the tab is open
-- out of combat the sheet does nothing and the Jeweler loads the item - one winner, whichever PreClick runs first.
-- The sheet's potion hook on the bag buttons yields to the same claim.
if Diablocraft and type(Diablocraft.ClaimRightClick)=="function" then Diablocraft.ClaimRightClick(takesRightClick) end

-- hooksecurefunc, never a replacement: the stock click path stays what it was.
if _G["SocketContainerItem"] then hooksecurefunc("SocketContainerItem",function(bag,slotIndex) J.OpenSockets(bag,slotIndex) end) end
if _G["SocketInventoryItem"] then hooksecurefunc("SocketInventoryItem",function(slotIndex) J.OpenSockets(255,slotIndex-1) end) end
-- docs/contracts/window-bridge.md: where the cursor's gem was picked up. Gems are bag items, so the
-- character sheet's pick-up is not watched.
hooksecurefunc("PickupContainerItem",function(bag,slotIndex) cursorBag,cursorSlot=bag,slotIndex end)

SLASH_DCJEWELER1="/dcjeweler"
SlashCmdList["DCJEWELER"]=function()
    J.debug=not J.debug
    say("Jeweler drag trace "..(J.debug and "on" or "off"))
end

----------------------------------------------------------------------------------------------------
-- The bridge reply, docs/contracts/window-bridge.md: DCJEWELER<TAB>record, one addon whisper per
-- record, a list split into as many records of the same letter as it needs, E when the reply is
-- complete and X|reason for a refusal. The records come before E, so the window is redrawn once,
-- on E (or on the refusal); nothing here re-reads the database for an action.
----------------------------------------------------------------------------------------------------
local function split(value,separator)
    local out={}
    for field in (value..separator):gmatch("(.-)"..separator) do out[#out+1]=field end
    return out
end
-- The C++ reply carries the core's raw bag and slot (255 = equipment or backpack, 19..22 = an
-- equipped bag); the model keeps the container convention the drag path uses (255 = equipment,
-- 0 = backpack, 1..4 = a bag), the same one the Show payload is built in.
local function position(bag,slotIndex)
    if bag==255 and slotIndex>18 then return 0,slotIndex-22 end
    if bag>=19 and bag<=22 then return bag-18,slotIndex+1 end
    return bag,slotIndex
end
-- A: everything the window holds for that guid; the F records after it rebuild its sockets.
local function replyRolled(f)
    local guid=tonumber(f[2])
    if not guid then return end
    local item=itemOf(guid)
    if not item then
        item={guid=guid,sockets={}}
        model.items[#model.items+1]=item
    end
    item.entry=tonumber(f[3]) or item.entry
    item.bag,item.slot=position(tonumber(f[4]) or 255,tonumber(f[5]) or 0)
    item.sockets={}
end
local function replySockets(f)
    local guid=tonumber(f[2])
    local item=guid and itemOf(guid)
    if not item then return end
    -- A long affix list is split into several F records of the same letter
    -- (window-bridge.md), and each record adds to the sockets the earlier ones
    -- built. The A record before them cleared the list, so a later record with
    -- no socket row (the gem row is always the last seq) must not start empty
    -- again, or it wipes every socket the item already showed.
    local sockets=item.sockets or {}
    for i=3,#f do
        local row=split(f[i],":")
        if row[4]=="socket" then sockets[#sockets+1]={seq=tonumber(row[1]) or 0,gemEntry=0,name="Empty socket"} end
    end
    -- A gem row names the socket it sits in by that socket's seq. The reply does not carry
    -- gem_rank and nothing on this screen draws it, so the rebuilt rows have no rank field.
    for i=3,#f do
        local row=split(f[i],":")
        if row[4]=="gem" then
            local parent,gem=tonumber(row[6]) or -1,tonumber(row[7]) or 0
            for _,socket in ipairs(sockets) do
                if socket.seq==parent then
                    socket.gemEntry=gem
                    socket.name=(tables and tables.gems and tables.gems[gem]) or "Unsupported gem"
                end
            end
        end
    end
    item.sockets=sockets
end
local function replyStacks(f)
    for i=2,#f do
        local row=split(f[i],":")
        local guid,entry=tonumber(row[1]),tonumber(row[2])
        -- This window lists bag gems; anything else the action put in the bags is not drawn here.
        if guid and entry and tables and tables.gems and tables.gems[entry] then
            local gem=gemOf(guid)
            if not gem then gem={guid=guid};model.gems[#model.gems+1]=gem end
            gem.entry=entry
            gem.count=tonumber(row[3]) or gem.count
            gem.bag,gem.slot=position(tonumber(row[4]) or 255,tonumber(row[5]) or 0)
            gem.name=tables.gems[entry]
        end
    end
end
local function replyRemoved(f)
    local gone={}
    for i=2,#f do local guid=tonumber(f[i]);if guid then gone[guid]=true end end
    local items,gems={},{}
    for _,item in ipairs(model.items) do if not gone[item.guid] then items[#items+1]=item end end
    for _,gem in ipairs(model.gems) do if not gone[gem.guid] then gems[#gems+1]=gem end end
    model.items=items
    model.gems=gems
end
local function replyBalance(f)
    for i=2,#f do
        local row=split(f[i],":")
        -- Death's Breath is the one account material this screen prints.
        if tonumber(row[1])==102000 then model.balance.deathsBreath=row[2] end
    end
end
-- The Combine view prints what the player holds of each input gem and the reply's stack records
-- move exactly that, so the count comes from the model's own bag gems.
local function recountGems()
    for _,recipe in ipairs(model.recipes or {}) do
        local count=0
        for _,gem in ipairs(model.gems or {}) do
            if gem.entry==recipe.inputEntry then count=count+(gem.count or 0) end
        end
        recipe.have=count
    end
end
local function jewelerReply(f)
    local record=f[1]
    if record=="X" or record=="E" then
        if record=="X" then say(f[2] or "That did not work.",true);chain=nil end
        awaiting=nil
        if record=="E" then recountGems() end
        -- A craft spends account materials, which the stack records do not carry: the tab reads Show again.
        if record=="E" and J.lastSent=="craft" then dirty=true;quiet=0 end
        if record=="E" and chain then nextRemove() end
        renderAll()
        return
    end
    -- R (the result count) and O (an item's enchant offers) are not drawn by this window.
    if record=="B" then model.balance.gold=f[2]
    elseif record=="M" then replyBalance(f)
    elseif record=="D" then replyRemoved(f)
    elseif record=="I" then replyStacks(f)
    elseif record=="A" then replyRolled(f)
    elseif record=="F" then replySockets(f) end
end
J.reply=jewelerReply
local bridge=CreateFrame("Frame")
bridge:RegisterEvent("CHAT_MSG_ADDON")
bridge:SetScript("OnEvent",function(_,_,prefix,message,distribution,sender)
    if prefix~="DCJEWELER" or distribution~="WHISPER" then return end
    local me=UnitName("player")
    if sender~=me and sender~=me.."-"..GetRealmName() then return end
    jewelerReply(split(message,"|"))
end)

-- A gem the client has not seen yet shows a question mark until the client has its icon; asking for
-- every gem once, through a tooltip nobody sees, makes it fetch them.
local warmed=false
local warmer
local function warm()
    if warmed then return end
    warmed=true
    warmer=warmer or CreateFrame("GameTooltip","DCJewelerWarm",UIParent,"GameTooltipTemplate")
    warmer:SetOwner(UIParent,"ANCHOR_NONE")
    for _,recipe in ipairs(model.recipes or {}) do
        warmer:SetHyperlink("item:"..recipe.id);warmer:SetHyperlink("item:"..recipe.inputEntry)
    end
    warmer:SetHyperlink("item:102000")
    for _,recipe in ipairs(model.crafts or {}) do
        warmer:SetHyperlink("item:"..recipe.entry)
        for _,material in ipairs(recipe.materials or {}) do warmer:SetHyperlink("item:"..material.entry) end
    end
end

function handlers.Show(_,payload)
    -- The gem names and effects, once: a reply names a socketed gem by its entry and nothing else.
    if not tables then AIO.Handle(CHANNEL,"Tables") end
    model=payload
    model.items=model.items or {};model.gems=model.gems or {};model.recipes=model.recipes or {}
    model.crafts=model.crafts or {};model.craftMax=model.craftMax or 0
    model.balance=model.balance or {gold="0",deathsBreath="0"}
    DCJewelerResponses.Show=payload
    sockFrame:Hide()
    warm()
    if not frame:IsShown() then tab="combine";socketView.item=nil end
    frame:Show();render()
    AIO.Handle("DiablocraftTooltip","Refresh")
end
-- The Sockets window's data: the one item asked for and the bag gems, read anywhere. A refresh asks by
-- guid and an item that is not in the answer has left the character.
function handlers.Gear(_,payload)
    DCJewelerResponses.Gear=payload
    if not tables then AIO.Handle(CHANNEL,"Tables") end
    local items=payload.items or {}
    local known={}
    for _,item in ipairs(items) do known[item.guid]=item end
    local merged={}
    if refreshing and not known[refreshing] then known[refreshing]=false end
    for _,item in ipairs(model.items) do if known[item.guid]==nil then merged[#merged+1]=item end end
    refreshing=nil
    for _,item in ipairs(items) do merged[#merged+1]=item end
    model.items=merged
    model.gems=payload.gems or {}
    recountGems()
    local ask=pending
    pending=nil
    local item=items[1]
    if ask and ask.open then
        if item then openFor(item) elseif ask.message then say("That item has no sockets.",true) end
    end
    if sockView.item and not itemOf(sockView.item.guid) then sockView.item=nil end
    if socketView.item and not itemOf(socketView.item.guid) then socketView.item=nil end
    renderAll()
end
handlers.Tables=function(_,payload) tables=payload;renderAll() end
-- The server's range watcher: the player walked away from the Jeweler. The Sockets window opens anywhere and stays.
handlers.Close=function() frame:Hide() end
for _,name in ipairs({"Items","Recipes","Quote","Balance","SocketResult","RemoveResult","CombineResult","Error"}) do
    handlers[name]=function(_,payload)
        DCJewelerResponses[name]=payload
        if name=="Error" then say(payload.message,true) end
    end
end

local watcher=CreateFrame("Frame")
watcher:RegisterEvent("BAG_UPDATE");watcher:RegisterEvent("PLAYER_EQUIPMENT_CHANGED")
watcher:SetScript("OnEvent",function()
    if not (frame:IsShown() or sockFrame:IsShown()) or awaiting then return end
    dirty=true;quiet=0
end)
-- Account gold and Death's Breath are ledger rows and fire no bag event.
if Diablocraft and Diablocraft.Econ then
    Diablocraft.Econ.OnChange(function() if frame:IsShown() and not awaiting then dirty=true;quiet=0 end end)
end
local sinceScan=0
watcher:SetScript("OnUpdate",function(_,delta)
    if frame:IsShown() and tab=="socket" then
        sinceScan=sinceScan+delta
        if sinceScan>=1 then sinceScan=0;J.ScanClickButtons() end
    end
    if awaiting then
        if GetTime()-awaiting>3 then awaiting=nil else return end
    end
    if dirty then
        quiet=quiet+delta
        if quiet>.3 then
            dirty=false
            if frame:IsShown() then AIO.Handle(CHANNEL,"Refresh")
            elseif sockFrame:IsShown() and sockView.item then
                refreshing=sockView.item.guid
                AIO.Handle(CHANNEL,"Gear",0,0,refreshing)
            end
        end
    end
end)
