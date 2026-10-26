-- dc_cube.lua - Kanai's Cube window, built as D3's three windows. Contract: docs/contracts/cube-messages.md (DCCUBE on
-- the window bridge).
--
-- A click on the Cube makes the server push the `list` records under the verb `open`; R|open opens this window. The
-- Cube window: the 3x3 grid, the power slots under it, Transmute and the book button. The book opens the Recipes panel
-- on the right (one recipe a page, Fill); a power slot opens the Collection panel in its place (the powers that slot
-- can hold, 18 a page). The grid is the window's own: the dragged item's guid, the reagent cells a Fill gave and the
-- bag gems dragged in for a recipe that takes them (its K records).
-- Nothing leaves the bags or the ledger until Transmute, which sends the whole grid; the server finds the recipe.
--
-- The server decides everything: this file never works out a cost, a recipe, a result or which powers a slot holds.
-- The layout and steps are D3's, the look is the stock window kit (dc_aio_ui.lua, DCUI).
--
-- The server half below does the two things the client cannot: it turns a dragged item's bag and slot into its guid
-- and rarity (or a gem's class and stack), and it closes the window when the player walks away from the Cube.
-- luacheck: globals DCCube DCUI DCRange DCThrottle Diablocraft GetCursorInfo ClearCursor GetItemInfo GameTooltip
-- luacheck: globals BuffFrame BuffFrame_Update BUFF_ACTUAL_DISPLAY BUFFS_PER_ROW BUFF_ROW_SPACING ConsolidatedBuffs
-- luacheck: globals TemporaryEnchantFrame TempEnchant1 BuffFrame_UpdateAllBuffAnchors
local AIO=AIO or require("AIO")
local CHANNEL="DiablocraftCube"
if AIO.AddAddon() then
    local handlers=AIO.AddHandlers(CHANNEL,{})
    -- Kanai's Cube's template (data/d3/cube_object.csv).
    local CUBE=910047
    local SEARCH_YARDS=40
    -- The reach the core lets a player click the Cube from (GameObject::IsAtInteractDistance) is its model box
    -- (GameObjectDisplayInfo.dbc row 6896), scaled, grown by INTERACTION_DISTANCE on every side and turned with the
    -- object. Its farthest corner from the Cube's position does not move when it turns, so a player farther than that
    -- is out of reach whatever the orientation. Closer than that but outside the box, a request gets the server's
    -- "Stand next to Kanai's Cube." and the window closes on it.
    local BOX={.7281,1.2425,2.3872} -- per axis, the larger of the box's |min| and |max|
    local INTERACTION_DISTANCE=5.5
    local function inReach(player)
        local cube=player:GetNearestGameObject(SEARCH_YARDS,CUBE)
        if not cube then return false end
        local sum=0
        for _,half in ipairs(BOX) do sum=sum+(half*cube:GetScale()+INTERACTION_DISTANCE)^2 end
        return player:GetExactDistance(cube)<=math.sqrt(sum)
    end
    -- The window opened: watch the reach until the player leaves it, then close the window.
    function handlers.Opened(player)
        if not DCThrottle.Allow(player,"cube:opened",5,10) then return end
        DCRange.Watch(player,CHANNEL,inReach,function(watched) AIO.Handle(watched,CHANNEL,"Close") end)
    end
    local function whole(n,lo,hi) return type(n)=="number" and n==math.floor(n) and n>=lo and n<=hi end
    -- The client's numbering (the Mystic's index): 255 and 0..18 a worn item, 0 and 1..16 the backpack, 1..4 and
    -- 1..36 the equipped bags.
    local function itemAt(player,bag,slot)
        if bag==255 and whole(slot,0,18) then return player:GetItemByPos(255,slot) end
        if bag==0 and whole(slot,1,16) then return player:GetItemByPos(255,slot+22) end
        if whole(bag,1,4) and whole(slot,1,36) then return player:GetItemByPos(bag+18,slot-1) end
    end
    -- A dragged item: its guid, entry, name and rarity (nil for a plain item), or `unidentified`. A gem also brings its
    -- class (`gem`: legendary_gem, or a normal gem's tier, as the server's CubeGemClass names it) and its stack's count.
    function handlers.Item(player,bag,slot)
        if not DCThrottle.Allow(player,"cube:item",5,10) then return end
        local item=itemAt(player,bag,slot)
        if not item then return end
        local guid,entry=item:GetGUIDLow(),item:GetEntry()
        local out={guid=guid,entry=entry,name=item:GetName(),count=item:GetCount()}
        if WorldDBQuery("SELECT 1 FROM dc_legendary_gem_item WHERE entry="..entry) then out.gem="legendary_gem"
        else
            local tier=WorldDBQuery("SELECT tier FROM dc_gem_item WHERE entry="..entry)
            out.gem=tier and tier:GetString(0) or nil
        end
        local row=CharDBQuery("SELECT rarity FROM dc_item_instance WHERE item_guid="..guid)
        if row then out.rarity=row:GetString(0)
        else out.unidentified=CharDBQuery("SELECT 1 FROM dc_item_unidentified WHERE item_guid="..guid)~=nil end
        AIO.Handle(player,CHANNEL,"Item",out)
    end
    return
end

local PREFIX="DCCUBE"
local handlers=AIO.AddHandlers(CHANNEL,{})
local U=DCUI or error("dc_aio_ui.lua must load before dc_cube.lua")
DCCube={}
local C=DCCube
local Logic={};C.Logic=Logic

------------------------------------------------------------------------------------------------
-- The logic, with no frame in it
------------------------------------------------------------------------------------------------
-- The contract's refusal on which the window closes.
Logic.NOT_NEAR="Stand next to Kanai's Cube."
-- A request the bucket dropped has no reply (window-bridge.md): Transmute, or a power's line, is asked again after this.
Logic.TIMEOUT=3
-- The grid's nine cells: the item takes the first, the reagents the other eight (the contract's at most eight).
Logic.CELLS=9
-- The Collection's page: three columns by six rows (the server pages it the same).
Logic.COLUMNS,Logic.ROWS=3,6
-- The rules whose item the recipe uses up (the contract's item rules); a convert's item stays.
Logic.CONSUMES={set_convert=true,rare_upgrade=true,reforge=true,primal_upgrade=true,extract=true}

function Logic.split(body)
    local fields={}
    for field in (body.."|"):gmatch("(.-)|") do fields[#fields+1]=field end
    return fields
end

function Logic.newReply(verb,count)
    return {verb=verb,count=tonumber(count),recipes={},byId={},slots={},cells={},powers={},pieces={},lines={},gone={}}
end

-- One record of a reply folded into it. C starts a recipe; its P, Q, T, K and Y follow. D names the items that left the bags. S is a power slot, G the cells a
-- Fill gives, L and W a page of the Collection, U a piece of a power's line (`lines` keeps them by entry too, for
-- `buffs`, which sends several powers' lines). A record that is not the contract's shape is dropped.
function Logic.read(reply,f)
    local kind,recipe=f[1],reply.byId[f[2] or ""]
    if kind=="C" and #f==4 and f[2]~="" then
        recipe={id=f[2],rule=f[3],name=f[4],costs={},takes={},makes={}}
        reply.recipes[#reply.recipes+1]=recipe
        reply.byId[recipe.id]=recipe
    elseif kind=="P" and #f==5 and recipe then
        recipe.subtitle,recipe.item,recipe.note=f[3],f[4],f[5]
    elseif kind=="Q" and #f==4 and recipe then
        recipe.quote,recipe.source=f[3],f[4]
    elseif kind=="T" and #f==6 and recipe and tonumber(f[3]) then
        recipe.costs[#recipe.costs+1]={entry=tonumber(f[3]),need=f[4],have=f[5],ok=f[6]=="1"}
    elseif kind=="K" and #f==4 and recipe and tonumber(f[4]) then
        recipe.takes[#recipe.takes+1]={class=f[3],n=tonumber(f[4])}
    elseif kind=="D" then
        for i=2,#f do if tonumber(f[i]) then reply.gone[tonumber(f[i])]=true end end
    elseif kind=="Y" and #f==5 and recipe and tonumber(f[4]) then
        recipe.makes[#recipe.makes+1]={rarity=f[3],entry=tonumber(f[4]),amount=f[5]}
    elseif kind=="S" and #f==5 and tonumber(f[2]) and tonumber(f[4]) then
        local entry=tonumber(f[4])
        reply.slots[#reply.slots+1]={slot=tonumber(f[2]),label=f[3],entry=entry>0 and entry or nil,name=f[5]}
    elseif kind=="G" and #f>=3 then
        for i=3,#f do
            local entry,amount=f[i]:match("^(%d+):(%d+)$")
            if entry then reply.cells[#reply.cells+1]={entry=tonumber(entry),amount=amount} end
        end
    elseif kind=="L" and #f==5 and tonumber(f[2]) and tonumber(f[3]) and tonumber(f[4]) then
        reply.slot,reply.page,reply.pages,reply.total=tonumber(f[2]),tonumber(f[3]),tonumber(f[4]),tonumber(f[5])
    elseif kind=="W" and #f>=3 and tonumber(f[2])==reply.slot then
        for i=3,#f do
            local entry,state,name=f[i]:match("^(%d+):([012]):(.*)$")
            if entry then reply.powers[#reply.powers+1]={entry=tonumber(entry),state=tonumber(state),name=name} end
        end
    elseif kind=="U" and #f==5 and tonumber(f[2]) and tonumber(f[4]) then
        reply.entry,reply.name=tonumber(f[2]),f[3]
        reply.pieces[tonumber(f[4])]=f[5]
        reply.lines[reply.entry]=reply.lines[reply.entry] or {}
        reply.lines[reply.entry][tonumber(f[4])]=f[5]
    end
end

-- A power's line from its U pieces: every piece from 1 to the count R gave, joined with nothing added; nil when one is
-- missing.
function Logic.line(reply)
    local out={}
    for i=1,reply.count or 0 do
        if not reply.pieces[i] then return nil end
        out[i]=reply.pieces[i]
    end
    return table.concat(out)
end

-- A ledger material's name: the addon's own labels (Economy.lua), else the client's item cache.
function Logic.materialName(entry)
    local econ=Diablocraft and Diablocraft.Econ
    for _,material in ipairs(econ and econ.CURRENCIES or {}) do
        if material.entry==entry then return material.name end
    end
    return GetItemInfo(entry) or ("Item "..entry)
end

-- A reagent's line on a recipe page: its name and count, and what the ledger holds when it is short.
function Logic.reagent(cost)
    local text=Logic.materialName(cost.entry).." x"..U.number(cost.need)
    if cost.ok then return text end
    return text.." (you have "..U.number(cost.have)..")"
end

-- A K record's gem on a recipe page: "Legendary Gem", or the tier's gems ("Flawless Royal Gem").
function Logic.gemName(class)
    return class=="legendary_gem" and "Legendary Gem" or class.." Gem"
end

-- How many of a dragged gem stack go in the grid: what a recipe's K takes of its class less what the grid already holds
-- of it, never more than the stack. nil when no recipe takes that class.
function Logic.take(recipes,cells,gem)
    local need
    for _,recipe in ipairs(recipes) do
        for _,take in ipairs(recipe.takes or {}) do
            if take.class==gem.gem then need=take.n end
        end
    end
    if not need then return nil end
    for _,cell in ipairs(cells) do if cell.gem==gem.gem then need=need-cell.amount end end
    return math.max(0,math.min(need,gem.count or 1))
end

-- The transmute request: the item's guid (0 for none), then each reagent cell as entry_amount and each bag gem as
-- iguid_count.
function Logic.transmute(item,cells)
    local fields={"transmute",tostring(item and item.guid or 0)}
    for _,cell in ipairs(cells) do
        fields[#fields+1]=cell.guid and ("i"..cell.guid.."_"..cell.amount) or (cell.entry.."_"..cell.amount)
    end
    return table.concat(fields,"\t")
end

------------------------------------------------------------------------------------------------
-- The windows
------------------------------------------------------------------------------------------------
local WIDTH,HEIGHT,PANEL_WIDTH=300,460,400
local CELL,CELL_STEP,SLOT,SLOT_STEP=44,48,48,90
local BOOK="Interface\\Icons\\INV_Misc_Book_09"
local frame=U.window("TormentCubeFrame",WIDTH,HEIGHT,"cube")
U.title(frame,"Kanai's Cube")
U.close(frame)
local reason=U.text(frame,20,-352,WIDTH-40,"GameFontHighlightSmall","CENTER")
U.colour(reason,U.RED)

-- What the server last said and what the window holds. `recipes` and `slots` the last complete list, `reply` one still
-- arriving; `page` the Recipes page; `panel` the open side panel (nil, "recipes", "collection"); `shelf` the
-- Collection's page; `lines` the power lines asked for (`asked` when, GetTime()). The grid: `placed` the dragged item,
-- `cells` the reagent cells and bag gems (a gem cell has its guid, class and name). `pending` when a transmute went out
-- (GetTime()).
local recipes,slots,reply,page,panel,shelf={},{},nil,1,nil,nil
local lines,asked={},{}
local placed,cells,pending=nil,{},nil

local function send(...)
    SendAddonMessage(PREFIX,table.concat({...},"\t"),"WHISPER",UnitName("player"))
end

-- A power's tooltip: the item's name, then its line once the server sent it (asked for once, then kept).
local POWER_NAME={1,.5,0}
local function powerTip(owner,entry,name,extra)
    U.tooltip(owner,function(tip)
        tip:AddLine(name,POWER_NAME[1],POWER_NAME[2],POWER_NAME[3])
        if lines[entry] then tip:AddLine(lines[entry],1,1,1,true) end
        if extra then tip:AddLine(extra,U.RED[1],U.RED[2],U.RED[3],true) end
    end)
    if lines[entry] or (asked[entry] and GetTime()-asked[entry]<Logic.TIMEOUT) then return end
    asked[entry]=GetTime()
    send("power",tostring(entry))
end
C.tipOwner=nil

-- The grid: nine cells, the first the item's.
local grid=CreateFrame("Frame",nil,frame)
grid:SetSize(3*CELL_STEP-(CELL_STEP-CELL),3*CELL_STEP-(CELL_STEP-CELL))
grid:SetPoint("TOP",0,-64)
local gridCells={}
for i=1,Logic.CELLS do
    local cell=U.slot(grid,CELL)
    cell:SetPoint("TOPLEFT",((i-1)%3)*CELL_STEP,-math.floor((i-1)/3)*CELL_STEP)
    cell:RegisterForClicks("LeftButtonUp","RightButtonUp")
    cell.count=cell:CreateFontString(nil,"OVERLAY","NumberFontNormal")
    cell.count:SetPoint("BOTTOMRIGHT",-3,3)
    cell.index=i
    gridCells[i]=cell
end

-- The power slots, one per S record, made when first needed.
local powerSlots={}
local function powerSlot(i)
    if powerSlots[i] then return powerSlots[i] end
    local b=U.slot(frame,SLOT)
    b.label=U.text(b,0,0,SLOT_STEP-2,"GameFontHighlightSmall","CENTER")
    b.label:ClearAllPoints();b.label:SetPoint("TOP",b,"BOTTOM",0,-4);b.label:SetHeight(28)
    b:SetScript("OnClick",function(self) C.OpenCollection(self.slot.slot,1) end)
    b:SetScript("OnEnter",function(self)
        local s=self.slot
        if s.entry then powerTip(self,s.entry,s.name)
        else U.tooltip(self,function(tip) tip:AddLine(s.label,U.GREY[1],U.GREY[2],U.GREY[3]) end) end
        C.tipOwner=self
    end)
    b:SetScript("OnLeave",function() GameTooltip:Hide();C.tipOwner=nil end)
    powerSlots[i]=b
    return b
end

local transmute=U.button(frame,140,"Transmute",function() C.Transmute() end)
transmute:SetPoint("BOTTOM",-16,22)
local book=U.slot(frame,30)
book:SetPoint("BOTTOMRIGHT",-26,18)
book.icon:SetTexture(BOOK)
book:SetScript("OnClick",function() C.ToggleRecipes() end)
book:SetScript("OnEnter",function(self) U.tooltip(self,function(tip) tip:AddLine("Recipes") end) end)
book:SetScript("OnLeave",function() GameTooltip:Hide() end)
U.anchor(frame,"buttons",{transmute,book})

-- A side panel: attached to the Cube window's right edge, with its own title and close button.
local function sidePanel(label)
    local p=CreateFrame("Frame",nil,frame)
    p.dcWidth=PANEL_WIDTH
    p:SetSize(PANEL_WIDTH,HEIGHT);p:SetPoint("TOPLEFT",frame,"TOPRIGHT",-4,0);p:EnableMouse(true)
    U.backdrop(p)
    U.title(p,label)
    p.closeButton=U.close(p)
    p.closeButton:SetScript("OnClick",function() C.ShowPanel(nil) end)
    p:Hide()
    return p
end

-- The Recipes panel: one recipe a page.
local recipesPanel=sidePanel("Recipes")
local recipeName=U.text(recipesPanel,0,-50,PANEL_WIDTH,"GameFontNormalLarge","CENTER")
local recipeSubtitle=U.text(recipesPanel,0,-74,PANEL_WIDTH,"GameFontHighlight","CENTER")
local itemRow=U.slot(recipesPanel,28)
itemRow.label=U.text(itemRow,36,-7,320)
local reagentRows={}
local note=U.text(recipesPanel,24,0,PANEL_WIDTH-48,"GameFontHighlightSmall")
U.colour(note,U.RED)
local consumed=U.text(recipesPanel,24,0,PANEL_WIDTH-48,"GameFontHighlightSmall")
U.colour(consumed,U.GREY)
consumed:SetText("The item is consumed.")
local quote=U.text(recipesPanel,24,0,PANEL_WIDTH-48,"GameFontHighlightSmall")
U.colour(quote,U.GREY)
local source=U.text(recipesPanel,24,0,PANEL_WIDTH-48,"GameFontHighlightSmall")
U.colour(source,U.GREY)
local pageText=U.text(recipesPanel,0,0,PANEL_WIDTH,"GameFontNormal","CENTER")
pageText:ClearAllPoints();pageText:SetPoint("BOTTOM",0,52)
local fill=U.button(recipesPanel,120,"Fill",function() C.Fill() end)
fill:SetPoint("BOTTOM",0,20)
local prevPage=U.button(recipesPanel,32,"<",function() C.TurnPage(-1) end)
prevPage:SetPoint("BOTTOMLEFT",24,20)
local nextPage=U.button(recipesPanel,32,">",function() C.TurnPage(1) end)
nextPage:SetPoint("BOTTOMRIGHT",-24,20)

-- The Collection panel: "Kanai's Cube Powers" for one slot, three columns by six rows.
local collectionPanel=sidePanel("Collection")
local powersHead=U.text(collectionPanel,0,-48,PANEL_WIDTH,"GameFontNormal","CENTER")
powersHead:SetText("Kanai's Cube Powers")
local slotHead=U.text(collectionPanel,0,-64,PANEL_WIDTH,"GameFontHighlightSmall","CENTER")
U.colour(slotHead,U.GREY)
local powerCells={}
for i=1,Logic.COLUMNS*Logic.ROWS do
    local b=CreateFrame("Button",nil,collectionPanel)
    b:SetSize(116,40)
    b:SetPoint("TOPLEFT",20+((i-1)%Logic.COLUMNS)*122,-84-math.floor((i-1)/Logic.COLUMNS)*46)
    U.flat(b,U.SLOT_BG[1],U.SLOT_BG[2],U.SLOT_BG[3],U.SLOT_BORDER[1],U.SLOT_BORDER[2],U.SLOT_BORDER[3])
    b.icon=b:CreateTexture(nil,"ARTWORK");b.icon:SetSize(32,32);b.icon:SetPoint("LEFT",4,0)
    b.label=U.text(b,40,-4,72,"GameFontHighlightSmall","CENTER");b.label:SetHeight(32)
    b:SetScript("OnClick",function(self) C.Choose(self.power) end)
    b:SetScript("OnEnter",function(self)
        local power=self.power
        local extra=power.state==0 and "You have not extracted that power."
            or power.state==2 and "Your class cannot use that power." or nil
        powerTip(self,power.entry,power.name,extra)
        C.tipOwner=self
    end)
    b:SetScript("OnLeave",function() GameTooltip:Hide();C.tipOwner=nil end)
    b:Hide()
    powerCells[i]=b
end
local shelfText=U.text(collectionPanel,0,0,PANEL_WIDTH,"GameFontNormal","CENTER")
shelfText:ClearAllPoints();shelfText:SetPoint("BOTTOM",0,26)
local prevShelf=U.button(collectionPanel,32,"<",function() C.OpenCollection(shelf.slot,shelf.page-1) end)
prevShelf:SetPoint("BOTTOMLEFT",24,20)
local nextShelf=U.button(collectionPanel,32,">",function() C.OpenCollection(shelf.slot,shelf.page+1) end)
nextShelf:SetPoint("BOTTOMRIGHT",-24,20)

------------------------------------------------------------------------------------------------
-- Drawing
------------------------------------------------------------------------------------------------
local function slotOf(number)
    for _,s in ipairs(slots) do if s.slot==number then return s end end
end
local function enable(button,on) if on then button:Enable() else button:Disable() end end

local function renderGrid()
    for i,cell in ipairs(gridCells) do
        if i==1 then
            cell.icon:SetTexture(placed and U.iconOf(placed.entry) or nil)
            cell.count:SetText("")
        else
            local reagent=cells[i-1]
            cell.icon:SetTexture(reagent and U.iconOf(reagent.entry) or nil)
            cell.count:SetText(reagent and U.number(reagent.amount) or "")
        end
    end
    enable(transmute,#cells>0 and not pending)
end

local function renderSlots()
    local n=#slots
    for i,s in ipairs(slots) do
        local b=powerSlot(i)
        b.slot=s
        b:ClearAllPoints();b:SetPoint("TOP",frame,"TOP",(i-(n+1)/2)*SLOT_STEP,-236)
        b.icon:SetTexture(s.entry and U.iconOf(s.entry) or nil)
        b.label:SetText(s.entry and s.name or s.label)
        U.colour(b.label,s.entry and U.WHITE or U.GREY)
        local outline=panel=="collection" and shelf and shelf.slot==s.slot
        local c=outline and U.BOX_ACTIVE or U.SLOT_BORDER
        b:SetBackdropBorderColor(c[1],c[2],c[3],1)
        b:Show()
    end
    for i=n+1,#powerSlots do powerSlots[i]:Hide() end
end

-- One y cursor down the page: each line goes under the last.
local function place(region,x,y) region:ClearAllPoints();region:SetPoint("TOPLEFT",recipesPanel,"TOPLEFT",x,y) end

local function renderRecipes()
    local recipe=recipes[page]
    local count=#recipes
    pageText:SetText(count>0 and ("Page "..page.."/"..count) or "")
    enable(prevPage,page>1);enable(nextPage,page<count);enable(fill,recipe~=nil)
    recipeName:SetText(recipe and recipe.name or "")
    recipeSubtitle:SetText(recipe and recipe.subtitle or "")
    local y=-104
    if recipe and (recipe.item or "")~="" then
        place(itemRow,24,y);itemRow.label:SetText(recipe.item.." x1");itemRow:Show();y=y-34
    else itemRow:Hide() end
    -- The reagents, then each gem the recipe takes from the bags: its slot shows the grid's gem of that class.
    local costs,takes=recipe and recipe.costs or {},recipe and recipe.takes or {}
    for i=1,#costs+#takes do
        local row=reagentRows[i]
        if not row then
            row=U.slot(recipesPanel,28);row.label=U.text(row,36,-7,320);reagentRows[i]=row
        end
        place(row,24,y);y=y-34
        local cost,take=costs[i],takes[i-#costs]
        if cost then
            row.icon:SetTexture(U.iconOf(cost.entry))
            row.label:SetText(Logic.reagent(cost))
            U.colour(row.label,cost.ok and U.WHITE or U.RED)
        else
            local gem
            for _,cell in ipairs(cells) do if cell.gem==take.class then gem=cell;break end end
            row.icon:SetTexture(gem and U.iconOf(gem.entry) or nil)
            row.label:SetText(Logic.gemName(take.class).." x"..take.n)
            U.colour(row.label,U.WHITE)
        end
        row:Show()
    end
    for i=#costs+#takes+1,#reagentRows do reagentRows[i]:Hide() end
    y=y-6
    local function line(fs,text)
        if not text or text=="" then fs:Hide();return end
        fs:SetText(text);place(fs,24,y);fs:Show()
        y=y-fs:GetStringHeight()-8
    end
    line(note,recipe and recipe.note)
    if recipe and Logic.CONSUMES[recipe.rule] then place(consumed,24,y);consumed:Show();y=y-20 else consumed:Hide() end
    line(quote,recipe and recipe.quote and ('"'..recipe.quote..'"'))
    line(source,recipe and (recipe.source or "")~="" and ("\226\128\148"..recipe.source) or nil)
end

local function renderCollection()
    local s=shelf and slotOf(shelf.slot)
    slotHead:SetText(s and s.label or "")
    local powers=shelf and shelf.powers or {}
    for i,b in ipairs(powerCells) do
        local power=powers[i]
        if power then
            b.power=power
            b.icon:SetTexture(U.iconOf(power.entry))
            b.icon:SetDesaturated(power.state~=1)
            b.label:SetText(power.name)
            U.colour(b.label,power.state==1 and U.GOLD or U.GREY)
            local chosen=s and s.entry==power.entry
            local c=chosen and U.BOX_ACTIVE or U.SLOT_BORDER
            b:SetBackdropBorderColor(c[1],c[2],c[3],1)
            b:Show()
        else b:Hide() end
    end
    shelfText:SetText(shelf and shelf.pages and ("Page "..shelf.page.."/"..shelf.pages) or "")
    enable(prevShelf,shelf and shelf.page and shelf.page>1)
    enable(nextShelf,shelf and shelf.pages and shelf.page<shelf.pages)
end

function C.Render()
    renderGrid();renderSlots()
    if panel=="recipes" then recipesPanel:Show();renderRecipes() else recipesPanel:Hide() end
    if panel=="collection" then collectionPanel:Show();renderCollection() else collectionPanel:Hide() end
end

------------------------------------------------------------------------------------------------
-- The player's steps
------------------------------------------------------------------------------------------------
function C.ShowPanel(which) panel=which;C.Render() end
function C.ToggleRecipes() C.ShowPanel(panel~="recipes" and "recipes" or nil) end

function C.TurnPage(step)
    page=math.max(1,math.min(#recipes,page+step));C.Render()
end

-- Fill asks for the page's reagents as grid cells; the reply's G replaces the grid's reagents.
function C.Fill()
    local recipe=recipes[page]
    if recipe then reason:SetText("");send("fill",recipe.id) end
end

-- A power slot: the Collection for it, page by page. The server sends the page (a page past the end is its last).
function C.OpenCollection(slot,want)
    if not slot then return end
    if not shelf or shelf.slot~=slot then shelf={slot=slot} end
    panel="collection"
    send("powers",tostring(slot),tostring(math.max(1,want or 1)))
    C.Render()
end

-- A lit power goes in the slot the Collection is for; a greyed one does nothing.
function C.Choose(power)
    if not power or power.state~=1 or not shelf then return end
    send("choose",tostring(shelf.slot),tostring(power.entry))
end

function C.Transmute()
    if pending or #cells==0 then return end
    pending=GetTime()
    reason:SetText("")
    SendAddonMessage(PREFIX,Logic.transmute(placed,cells),"WHISPER",UnitName("player"))
    C.Render()
end

-- The item: dragged in from the bags or the character sheet, or clicked in while held. The client has no API that
-- says which container a drag started in, so the pickups are hooked to remember it (the Mystic's pattern), and the
-- server half turns that bag and slot into the item.
local cursorBag,cursorSlot
hooksecurefunc("PickupContainerItem",function(bag,slotNumber) cursorBag,cursorSlot=bag,slotNumber end)
hooksecurefunc("PickupInventoryItem",function(slotNumber) cursorBag,cursorSlot=255,slotNumber-1 end)
function C.Drop()
    if GetCursorInfo()~="item" then return false end
    local bag,slotNumber=cursorBag,cursorSlot
    cursorBag,cursorSlot=nil,nil
    -- Taken or not, the item goes back where it came from: one left held turns the next bag click into a swap.
    ClearCursor()
    if bag and slotNumber then AIO.Handle(CHANNEL,"Item",bag,slotNumber) end
    return true
end
-- A click with nothing held takes out what the cell holds: the item (it never left the bags) or that reagent cell.
function C.ClickCell(i)
    if C.Drop() then return end
    if i==1 then placed=nil elseif cells[i-1] then table.remove(cells,i-1) end
    C.Render()
end
for i,cell in ipairs(gridCells) do
    cell:SetScript("OnReceiveDrag",function() C.Drop() end)
    cell:SetScript("OnClick",function() C.ClickCell(i) end)
    cell:SetScript("OnEnter",function(self)
        local reagent=cells[i-1]
        if i==1 and placed then U.tooltip(self,function(tip) tip:AddLine(placed.name) end)
        elseif reagent then
            local name=reagent.name or Logic.materialName(reagent.entry)
            U.tooltip(self,function(tip) tip:AddLine(name.." x"..U.number(reagent.amount)) end)
        end
    end)
    cell:SetScript("OnLeave",function() GameTooltip:Hide() end)
end

-- The server half's answer: a gem a recipe takes goes in as a bag cell (the same stack again replaces its cell); the item
-- goes in when the Cube could take a rolled item, with the server's own refusal otherwise.
function C.Place(item)
    if not item then return end
    if item.gem then
        for i=#cells,1,-1 do if cells[i].guid==item.guid then table.remove(cells,i) end end
        local n=Logic.take(recipes,cells,item)
        if n then
            if n>0 and #cells<Logic.CELLS-1 then
                cells[#cells+1]={guid=item.guid,entry=item.entry,name=item.name,gem=item.gem,amount=n}
            end
            reason:SetText("");C.Render();return
        end
    end
    if item.unidentified then U.say("Identify it first.",true);return end
    if not item.rarity then U.say("Choose a rolled item.",true);return end
    placed=item;reason:SetText("");C.Render()
end
handlers.Item=function(_,item) C.Place(item) end
-- The server's reach watcher: the player walked away from the Cube.
handlers.Close=function() frame:Hide() end

------------------------------------------------------------------------------------------------
-- The server's records
------------------------------------------------------------------------------------------------
local record={}
-- `R|verb|n`: a reply begins. R|open opens the window; a fresh one starts with an empty grid and no panel.
function record.R(f)
    reply=Logic.newReply(f[2],f[3])
    if f[2]~="open" then return end
    if not frame:IsShown() then
        placed,cells,pending,page,panel,shelf=nil,{},nil,1,nil,nil
        reason:SetText("")
    end
    frame:Show()
    AIO.Handle(CHANNEL,"Opened")
end
local function fold(f) if reply then Logic.read(reply,f) end end
for _,letter in ipairs({"C","P","Q","T","K","Y","D","S","G","L","W","U"}) do record[letter]=fold end

-- What each complete reply changes.
local finish={}
function finish.list(done)
    recipes,slots=done.recipes,done.slots
    page=math.max(1,math.min(page,#recipes))
end
finish.open=finish.list
-- G replaces the reagents; the bag gems stay (the grid's cells allowing).
function finish.fill(done)
    for _,cell in ipairs(cells) do
        if cell.guid and #done.cells<Logic.CELLS-1 then done.cells[#done.cells+1]=cell end
    end
    cells=done.cells
end
-- The ledger and the item changed: the reagents and gems are spent, an item recipe's item is gone (a D names it; an
-- augment's item stays), and the recipe comes again with the new balances.
function finish.transmute(done)
    pending=nil
    cells={}
    if placed and done.gone[placed.guid] then placed=nil end
    for i,recipe in ipairs(recipes) do recipes[i]=done.byId[recipe.id] or recipe end
end
function finish.powers(done)
    if not shelf or done.slot~=shelf.slot then return end
    shelf.page,shelf.pages,shelf.total,shelf.powers=done.page,done.pages,done.total,done.powers
end
function finish.power(done)
    local text=done.entry and Logic.line(done)
    if not text then return end
    lines[done.entry]=text
    -- Still hovering that power: its tooltip gets the line now.
    local owner=C.tipOwner
    if owner and GameTooltip:GetOwner()==owner and owner:GetScript("OnEnter") then owner:GetScript("OnEnter")(owner) end
end
function finish.choose(done)
    for _,changed in ipairs(done.slots) do
        local s=slotOf(changed.slot)
        if s then s.entry,s.name=changed.entry,changed.name end
    end
    -- The choice changed the buff row (the contract's "When the addon asks").
    send("buffs")
end
function finish.buffs(done)
    C.buffs={}
    for _,s in ipairs(done.slots) do
        if s.entry then C.buffs[#C.buffs+1]={entry=s.entry,name=s.name,line=table.concat(done.lines[s.entry] or {})} end
    end
    C.DrawBuffs()
end
-- `E|verb`: the reply is complete.
function record.E(f)
    if not reply or reply.verb~=f[2] then return end
    local done=reply
    reply=nil
    if finish[done.verb] then finish[done.verb](done) end
    C.Render()
end
-- `X|text`: refused, nothing was spent. Out of reach closes; otherwise the text stays under the Cube.
function record.X(f)
    local text=f[2] or ""
    pending,reply=nil,nil
    if text==Logic.NOT_NEAR or not frame:IsShown() then U.say(text,true);frame:Hide();return end
    C.Render()
    reason:SetText(text)
end

function C.OnMessage(prefix,body,distribution,sender)
    if prefix~=PREFIX or distribution~="WHISPER" then return end
    local own=UnitName("player")
    if sender~=own and sender~=own.."-"..GetRealmName() then return end
    local f=Logic.split(body)
    local handle=record[f[1]]
    if handle then handle(f) end
end

------------------------------------------------------------------------------------------------
-- The buff row (the contract's "The buff bar"): each chosen power is one more icon after the
-- player's real buffs, in their row, at their size and spacing, with no duration. On ElvUI's buffs when its Auras module
-- runs (ConfigureAuras lays that row out: ElvUI-WotLK 6.09, 8c0ac9d0, Modules/Auras/Auras.lua), on the stock BuffFrame
-- otherwise (FrameXML/BuffFrame.lua, BuffFrame_UpdateAllBuffAnchors); each layout runs again after its own, so the
-- icons follow the buffs as they come and go. `C.buffs` is the last `buffs` reply in slot order: entry, name, line.
------------------------------------------------------------------------------------------------
C.buffs={}
local function buffTip(self)
    local b=self.buff
    GameTooltip:SetOwner(self,"ANCHOR_BOTTOMLEFT")
    GameTooltip:AddLine("|T"..U.iconOf(b.entry)..":20|t "..b.name,POWER_NAME[1],POWER_NAME[2],POWER_NAME[3])
    if b.line~="" then GameTooltip:AddLine(b.line,1,1,1,true) end
    GameTooltip:Show()
end
-- One icon per power, made by `make` in that row's own look the first time; the rest hidden.
local function buffIcons(set,make)
    for i,b in ipairs(C.buffs) do
        if not set[i] then
            set[i]=make(i)
            set[i].dcCubeBuff=true
            set[i]:SetScript("OnEnter",buffTip)
            set[i]:SetScript("OnLeave",function() GameTooltip:Hide() end)
        end
        set[i].buff=b
        set[i].texture:SetTexture(U.iconOf(b.entry))
        set[i]:Show()
    end
    for i=#C.buffs+1,#set do set[i]:Hide() end
end

-- ElvUI: its own buff button (CreateIcon: border, skin, fonts), placed where its next buff would go.
local elv=_G.ElvUI and _G.ElvUI[1]
local A=elv and elv.GetModule and elv:GetModule("Auras",true)
local elvIcons={}
if A and A.ConfigureAuras then
    hooksecurefunc(A,"ConfigureAuras",function(self,header)
        if header~=self.BuffFrame then return end
        local shown=0
        for _,child in ipairs({header:GetChildren()}) do
            if child:IsShown() and not child.dcCubeBuff then shown=shown+1 end
        end
        buffIcons(elvIcons,function(i)
            local b=CreateFrame("Button","TormentCubeBuffElv"..i,header)
            self:CreateIcon(b)
            self:ClearAuraTime(b)
            b:SetScript("OnClick",nil)
            return b
        end)
        -- ConfigureAuras' own grid: DIRECTION_TO_POINT and the spacing multipliers, read off the direction's words.
        local db=self.db.buffs
        local dir=db.growthDirection
        local point=(dir:find("DOWN") and "TOP" or "BOTTOM")..(dir:find("RIGHT") and "LEFT" or "RIGHT")
        local dx=(dir:find("RIGHT") and 1 or -1)*(db.horizontalSpacing+db.size)
        local dy=(dir:find("DOWN") and -1 or 1)*(db.verticalSpacing+db.size)
        local across=dir:find("^RIGHT") or dir:find("^LEFT")
        for i=1,#C.buffs do
            local icon,k=elvIcons[i],shown+i-1
            local tick,cycle=k%db.wrapAfter,math.floor(k/db.wrapAfter)
            icon:ClearAllPoints()
            if across then icon:SetPoint(point,header,tick*dx,cycle*dy) else icon:SetPoint(point,header,cycle*dx,tick*dy) end
            icon:SetSize(db.size,db.size)
        end
    end)
end

-- The stock row: an aura button's size (TempEnchant1 is one), placed by BuffFrame_UpdateAllBuffAnchors' own steps.
local stockIcons={}
local function stockIcon(i)
    local b=CreateFrame("Button","TormentCubeBuff"..i,BuffFrame)
    b:SetSize(TempEnchant1:GetWidth(),TempEnchant1:GetHeight())
    b.texture=b:CreateTexture(nil,"BACKGROUND")
    b.texture:SetAllPoints()
    return b
end
-- The rows the buffs and the icons fill, as DebuffButton_UpdateAnchors counts them.
local function stockRows()
    local n=BUFF_ACTUAL_DISPLAY+BuffFrame.numEnchants+#C.buffs
    if BuffFrame.numConsolidated>0 then n=n-BuffFrame.numConsolidated+1 end
    return math.ceil(n/BUFFS_PER_ROW)
end
if BuffFrame_UpdateAllBuffAnchors then
    hooksecurefunc("BuffFrame_UpdateAllBuffAnchors",function()
        buffIcons(stockIcons,stockIcon)
        local index=BuffFrame.numEnchants+(BuffFrame.numConsolidated>0 and 1 or 0)
        local previous,above=nil,ConsolidatedBuffs
        for i=1,BUFF_ACTUAL_DISPLAY do
            local b=_G["BuffButton"..i]
            if not b.consolidated then
                index=index+1
                if index>1 and index%BUFFS_PER_ROW==1 then above=b end
                previous=b
            end
        end
        for i=1,#C.buffs do
            local icon=stockIcons[i]
            index=index+1
            icon:ClearAllPoints()
            if index>1 and index%BUFFS_PER_ROW==1 then
                icon:SetPoint("TOP",above,"BOTTOM",0,-BUFF_ROW_SPACING);above=icon
            elseif index==1 then icon:SetPoint("TOPRIGHT",BuffFrame,"TOPRIGHT",0,0)
            elseif previous then icon:SetPoint("RIGHT",previous,"LEFT",-5,0)
            else
                icon:SetPoint("TOPRIGHT",BuffFrame.numEnchants>0 and TemporaryEnchantFrame or ConsolidatedBuffs,"TOPLEFT",-5,0)
            end
            previous=icon
        end
    end)
    -- The debuffs sit under the buff rows: an icon that starts a row moves them down as one more buff would.
    hooksecurefunc("DebuffButton_UpdateAnchors",function(name,index)
        if name~="DebuffButton" or index~=1 or #C.buffs==0 then return end
        local rows,height=stockRows(),TempEnchant1:GetHeight()
        _G.DebuffButton1:SetPoint("TOPRIGHT",ConsolidatedBuffs,"BOTTOMRIGHT",0,
            rows<2 and -(2*BUFF_ROW_SPACING+height) or -rows*(BUFF_ROW_SPACING+height))
    end)
end

-- The buffs changed: both rows lay out again (their hooks above place the icons).
function C.DrawBuffs()
    if A and A.BuffFrame then A:UpdateHeader(A.BuffFrame) end
    if BuffFrame_Update then BuffFrame_Update() end
end

local watcher=CreateFrame("Frame")
watcher:RegisterEvent("CHAT_MSG_ADDON")
watcher:RegisterEvent("PLAYER_ENTERING_WORLD")
watcher:SetScript("OnEvent",function(_,event,...)
    if event=="PLAYER_ENTERING_WORLD" then send("buffs") else C.OnMessage(...) end
end)
watcher:SetScript("OnUpdate",function()
    if pending and GetTime()-pending>=Logic.TIMEOUT then pending=nil;C.Render() end
end)

-- AIO may load this file after PLAYER_ENTERING_WORLD has fired: ask for the buff row now too.
send("buffs")

C.ui={frame=frame,grid=gridCells,powerSlots=powerSlots,transmute=transmute,book=book,reason=reason,watcher=watcher,
    recipes=recipesPanel,recipeName=recipeName,recipeSubtitle=recipeSubtitle,itemRow=itemRow,reagentRows=reagentRows,
    note=note,consumed=consumed,quote=quote,source=source,pageText=pageText,fill=fill,prevPage=prevPage,nextPage=nextPage,
    collection=collectionPanel,slotHead=slotHead,powerCells=powerCells,shelfText=shelfText,prevShelf=prevShelf,
    nextShelf=nextShelf}
