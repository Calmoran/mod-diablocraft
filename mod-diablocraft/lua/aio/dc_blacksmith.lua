-- Blacksmith window, built on the shared Torment window look (dc_aio_ui.lua, DCUI) so
-- it cannot drift from the Jeweler's again. Prices/output identities come from the mapped
-- catalogue; all payment, salvage and repair execute through the checked C++ bridge.
-- luacheck: globals DCBlacksmith DCBlacksmithServer DCRange DCTunables DCThrottle DCJeweler DiablocraftCraftingFrame DCUI DCShowRecipePreview DCRecipePreviewsClear SetCursor ResetCursor GetMouseFocus
-- luacheck: globals UnitIsDeadOrGhost UnitAffectingCombat GetUnitSpeed StaticPopup_Hide IsAltKeyDown NUM_CONTAINER_FRAMES PickupContainerItem PickupInventoryItem
local AIO=AIO or require("AIO")
local CHANNEL="DiablocraftBlacksmith"
if AIO.AddAddon() then
    local handlers=AIO.AddHandlers(CHANNEL,{})
    DCBlacksmithServer={}
    local function allow(player,key)
        local rate=DCTunables.Get("crafting","artisan_per_second")
        local burst=DCTunables.Get("crafting","artisan_burst")
        return rate and burst and rate>0 and burst>0 and DCThrottle.Allow(player,key,rate,burst)
    end
    local function guard(player)
        local range=DCTunables.Get("crafting","artisan_interaction_range_yards")
        return range and player:IsAlive() and not player:IsInCombat() and player:GetNearestCreature(range,910000)
    end
    local function integer(n,lo,hi) return type(n)=="number" and n==math.floor(n) and n>=lo and n<=hi end
    local function itemData(item,bag,slot)
        if not item then return end
        local guid=item:GetGUIDLow()
        local row=CharDBQuery("SELECT rarity FROM dc_item_instance WHERE item_guid="..guid.." UNION ALL SELECT rarity FROM dc_item_unidentified WHERE item_guid="..guid)
        return {guid=guid,entry=item:GetEntry(),count=item:GetCount(),name=item:GetName(),rarity=row and row:GetString(0) or "",
            bag=bag,slot=slot,managed=row~=nil,equipped=bag==255}
    end
    local function show(player,refresh)
        local npc=guard(player)
        if not npc then AIO.Handle(player,CHANNEL,"Error","Stand next to the Blacksmith, alive and out of combat.");return end
        local snapshot=DCAccount.Snapshot(player)
        local out={title=npc:GetName(),gold=snapshot.gold,materials=snapshot.materials,recipes={},items={},
            playerLevel=player:GetLevel(),maxCount=16,refresh=refresh==true,castSeconds=DCTunables.Get("crafting","blacksmith_cast_seconds")}
        local class=WorldDBQuery("SELECT class_id FROM dc_class_map WHERE wow_class_id="..player:GetClass())
        out.class=class and class:GetString(0) or ""
        local costsByRecipe={}
        local mats=WorldDBQuery("SELECT m.recipe_id,m.item_entry,m.amount,m.d3_id,COALESCE(i.name,'') FROM dc_blacksmith_catalog_material m LEFT JOIN item_template i ON i.entry=m.item_entry ORDER BY m.recipe_id,m.item_entry,m.d3_id")
        if mats then repeat
            local id,entry=mats:GetUInt32(0),mats:GetUInt32(1)
            costsByRecipe[id]=costsByRecipe[id] or {}
            local list=costsByRecipe[id]
            list[#list+1]={entry=entry,amount=mats:GetUInt32(2),name=entry~=0 and mats:GetString(4)
                or ("Bounty material (Act "..tostring(tonumber(mats:GetString(3):match("_(%d+)$")) or "?")..")")}
        until not mats:NextRow() end
        local rows=WorldDBQuery("SELECT c.id,c.output_entry,c.name,c.slot,c.category,c.page,c.rarity,c.item_level,c.required_level,CAST(c.gold_d3 AS CHAR),c.enabled,c.unavailable_reason,COALESCE(b.usable_by,'') FROM dc_blacksmith_catalog c JOIN dc_base_item b ON b.entry=c.output_entry ORDER BY c.id")
        if rows then repeat
            local r={id=rows:GetUInt32(0),entry=rows:GetUInt32(1),name=rows:GetString(2),slot=rows:GetString(3),
                category=rows:GetString(4),page=rows:GetString(5),rarity=rows:GetString(6),level=rows:GetUInt32(7),
                required=rows:GetUInt32(8),gold=rows:GetString(9),enabled=rows:GetUInt32(10)~=0,
                reason=rows:GetString(11),usableBy=rows:GetString(12),materials={}}
            r.materials=costsByRecipe[r.id] or {}
            out.recipes[#out.recipes+1]=r
        until not rows:NextRow() end
        local guids={}
        local function add(bag,slot,item)
            if not item then return end
            local guid=item:GetGUIDLow();guids[#guids+1]=tostring(guid)
            out.items[#out.items+1]={guid=guid,entry=item:GetEntry(),count=item:GetCount(),name=item:GetName(),bag=bag,slot=slot,equipped=bag==255,managed=false,rarity=""}
        end
        for slot=0,18 do add(255,slot,player:GetItemByPos(255,slot)) end
        for slot=23,38 do add(0,slot-22,player:GetItemByPos(255,slot)) end
        for bag=19,22 do
            local container=player:GetItemByPos(255,bag)
            local size=container and container:GetBagSize() or 0
            out.maxCount=out.maxCount+size
            for slot=0,size-1 do add(bag-18,slot+1,player:GetItemByPos(bag,slot)) end
        end
        if #guids>0 then
            local ids=table.concat(guids,",")
            local metadata=CharDBQuery("SELECT item_guid,rarity FROM dc_item_instance WHERE item_guid IN ("..ids..") UNION ALL SELECT item_guid,rarity FROM dc_item_unidentified WHERE item_guid IN ("..ids..")")
            local rarities={}
            if metadata then repeat rarities[metadata:GetUInt32(0)]=metadata:GetString(1) until not metadata:NextRow() end
            for _,item in ipairs(out.items) do item.rarity=rarities[item.guid] or "";item.managed=rarities[item.guid]~=nil end
        end
        AIO.Handle(player,CHANNEL,"Show",out)
        -- Walking away closes the window: the shared range watcher, dc_aio_range.lua.
        if not refresh then DCRange.Artisan(player,CHANNEL,910000) end
    end
    DCBlacksmithServer.Show=show
    function handlers.Refresh(player)
        if allow(player,"blacksmith:read") then show(player,true) end
    end
    function handlers.Target(player,bag,slot,nonce)
        if not guard(player) or not allow(player,"blacksmith:read") then return end
        if not integer(nonce,1,4294967295) or not integer(bag,0,255) or not integer(slot,0,255) then return end
        local item
        if bag==255 and slot<=18 then item=player:GetItemByPos(255,slot)
        elseif bag==0 and slot>=1 and slot<=16 then item=player:GetItemByPos(255,slot+22)
        elseif bag>=1 and bag<=4 and slot>=1 then
            local container=player:GetItemByPos(255,bag+18)
            if container and slot<=container:GetBagSize() then item=player:GetItemByPos(bag+18,slot-1) end
        end
        AIO.Handle(player,CHANNEL,"Target",{nonce=nonce,item=itemData(item,bag,slot)})
    end
    return
end

local handlers=AIO.AddHandlers(CHANNEL,{})
-- The shared window look (dc_aio_ui.lua, loaded before this file because its name sorts
-- first): everything visual below is built from DCUI, so this window cannot drift from the
-- Jeweler's again.
local U=DCUI or error("dc_aio_ui.lua must load before dc_blacksmith.lua")
DCBlacksmith={}
local B=DCBlacksmith
local Logic={};B.Logic=Logic
local function decimal(v)
    local value=tostring(v or "0"):gsub("^0+","")
    return value~="" and value or "0"
end
function Logic.atLeast(a,b)
    a,b=decimal(a),decimal(b)
    if #a~=#b then return #a>#b end
    return a>=b
end
function Logic.times(v,n)
    v=decimal(v);local carry,out=0,""
    for i=#v,1,-1 do
        local k=tonumber(v:sub(i,i))*n+carry
        out=tostring(k%10)..out;carry=math.floor(k/10)
    end
    if carry>0 then out=tostring(carry)..out end
    return decimal(out)
end
function Logic.minus(a,b)
    if not Logic.atLeast(a,b) then return "0" end
    a,b=decimal(a),decimal(b);local borrow,out=0,""
    for i=0,#a-1 do
        local digit=#b-i>=1 and tonumber(b:sub(#b-i,#b-i)) or 0
        local k=tonumber(a:sub(#a-i,#a-i))-digit-borrow
        if k<0 then k=k+10;borrow=1 else borrow=0 end
        out=tostring(k)..out
    end
    return decimal(out)
end
local RANK={set=4,legendary=3,rare=2,magic=1,normal=0}
local TINT={set={.1,1,.1},legendary={1,.5,0},rare={1,1,0},magic={.3,.6,1},normal={1,1,1}}
local GOLD,GREY,RED=U.GOLD,U.GREY,U.RED
local model={recipes={},materials={},items={},gold="0",maxCount=0}
local tab,filter,search,qty,selected="weapons","all","",1,nil
local collapsed={};local pending,query,job,repairItem;local nonce=0
local quotes={};local results={};local render
local function have(entry) return model.materials[entry] or model.materials[tostring(entry)] or "0" end
function Logic.available(r,m)
    if not r.enabled then return 0 end
    local function affordable(n)
        if not Logic.atLeast(m.gold,Logic.times(r.gold,n)) then return false end
        for _,cost in ipairs(r.materials) do
            if cost.entry==0 or not Logic.atLeast(m.materials[cost.entry] or m.materials[tostring(cost.entry)] or "0",cost.amount*n) then return false end
        end
        return true
    end
    local lo,hi=0,m.maxCount or 0
    while lo<hi do local mid=math.floor((lo+hi+1)/2);if affordable(mid) then lo=mid else hi=mid-1 end end
    return lo
end
local function usable(r,m)
    return r.required<=m.playerLevel and (r.usableBy=="" or (";"..r.usableBy..";"):find(";"..m.class..";",1,true)~=nil)
end
function Logic.rows(m,page,which,needle,closed)
    local highest={};local groups={};local keys={};needle=(needle or ""):lower()
    for _,r in ipairs(m.recipes) do
        if r.page==page and usable(r,m) then
            local key=r.category..":"..r.rarity
            highest[key]=math.max(highest[key] or 0,r.required)
        end
    end
    for _,r in ipairs(m.recipes) do
        local count=Logic.available(r,m)
        if r.page==page and (which~="highest" or (usable(r,m) and r.required==highest[r.category..":"..r.rarity]))
            and (which~="materials" or count>0) and r.name:lower():find(needle,1,true) then
            if not groups[r.category] then groups[r.category]={};keys[#keys+1]=r.category end
            groups[r.category][#groups[r.category]+1]={recipe=r,count=count}
        end
    end
    table.sort(keys)
    local rows={}
    for _,key in ipairs(keys) do
        local group=groups[key]
        table.sort(group,function(a,b)
            a,b=a.recipe,b.recipe
            if RANK[a.rarity]~=RANK[b.rarity] then return RANK[a.rarity]>RANK[b.rarity] end
            if a.required~=b.required then return a.required>b.required end
            if a.level~=b.level then return a.level>b.level end
            if a.name~=b.name then return a.name<b.name end
            return a.id<b.id
        end)
        rows[#rows+1]={category=key,closed=closed[key] and needle==""}
        if not closed[key] or needle~="" then for _,row in ipairs(group) do rows[#rows+1]=row end end
    end
    return rows
end
local LABEL={Axe="Axe",Axe2H="Two-Handed Axe",Belt="Belt",Belt_Barbarian="Mighty Belt",Boots="Boots",Bow="Bow",
    Bracers="Bracers",CeremonialDagger="Ceremonial Knife",ChestArmor="Chest Armor",Cloak="Cloak",CombatStaff="Daibo",
    Crossbow="Crossbow",CrusaderShield="Crusader Shield",Dagger="Dagger",FistWeapon="Fist Weapon",Flail1H="Flail",
    Flail2H="Two-Handed Flail",Gloves="Gloves",HandXbow="Hand Crossbow",Helm="Helm",Legs="Pants",Mace="Mace",
    Mace2H="Two-Handed Mace",MightyWeapon1H="Mighty Weapon",MightyWeapon2H="Two-Handed Mighty Weapon",Mojo="Mojo",
    NecromancerOffhand="Phylactery",Orb="Source",Polearm="Polearm",Quiver="Quiver",Scythe1H="Scythe",Scythe2H="Two-Handed Scythe",
    Shield="Shield",Shoulders="Shoulders",SpiritStone_Monk="Spirit Stone",Staff="Staff",Sword="Sword",Sword2H="Two-Handed Sword",
    VoodooMask="Voodoo Mask",Wand="Wand",WizardHat="Wizard Hat"}
local function commas(v)
    if Diablocraft and Diablocraft.Econ then return Diablocraft.Econ.Gold(v) end
    local s,n=tostring(v or "0"),1;while n>0 do s,n=s:gsub("^(%d+)(%d%d%d)","%1,%2") end;return s
end
-- The look lives in dc_aio_ui.lua (DCUI): one definition, resolved each call, so the
-- Torment addon's newer Diablocraft.Style always reaches a window built afterwards.
local text,colour,flat=U.text,U.colour,U.flat
local function actionButton(parent,label,x,y,w,fn)
    local b=U.button(parent,w,label,fn);b:SetPoint("TOPLEFT",x,y);return b
end
local function icon(parent,size,x,y)
    local s=U.slot(parent,size);s:SetPoint("TOPLEFT",x,y);return s
end
local function tip(owner,entry,item,recipe)
    GameTooltip:SetOwner(owner,"ANCHOR_RIGHT")
    if item and item.bag==255 then GameTooltip:SetInventoryItem("player",item.slot+1)
    elseif item then GameTooltip:SetBagItem(item.bag,item.slot)
    elseif entry and entry~=0 then
        GameTooltip:SetHyperlink("item:"..entry..":0:0:0:0:0:0:0")
        -- A recipe's result shows what the craft will make, drawn by the item tooltip
        -- (dc_tooltip.lua). The records are the server's.
        if recipe then owner.dcRecipeId=recipe.id;if DCShowRecipePreview then DCShowRecipePreview(GameTooltip,recipe) end end
    else GameTooltip:SetText("This material is not available yet.") end
    GameTooltip:Show()
end
local iconOf=U.iconOf
local frame=U.window("TormentBlacksmithFrame",nil,nil,"blacksmith")
local title=U.title(frame,"Blacksmith")
local sub=U.subtitle(frame)
local close=U.close(frame) -- native close: hides its parent
local forge=CreateFrame("Frame",nil,frame);forge:SetPoint("TOPLEFT",16,-64);forge:SetPoint("BOTTOMRIGHT",-16,16)
local expand=actionButton(forge,"Expand All",6,0,95,function()
    local any=false;for _,r in ipairs(model.recipes) do if r.page==tab and collapsed[r.category] then any=true end end
    for _,r in ipairs(model.recipes) do if r.page==tab then collapsed[r.category]=not any end end;render()
end)
local filterMenu
local filterButton=actionButton(forge,"All",110,0,116,function()
    if filterMenu:IsShown() then filterMenu:Hide() else filterMenu:Show() end
end)
filterMenu=CreateFrame("Frame",nil,forge);filterMenu:SetSize(122,74);filterMenu:SetPoint("TOPLEFT",108,-23)
flat(filterMenu,0,0,0,U.SLOT_BORDER[1],U.SLOT_BORDER[2],U.SLOT_BORDER[3]);filterMenu:SetFrameStrata("DIALOG");filterMenu:Hide()
local filterOptions={}
for i,option in ipairs({{"all","All"},{"highest","Highest usable"},{"materials","Have materials"}}) do
    filterOptions[i]=actionButton(filterMenu,option[2],3,-3-(i-1)*23,116,function()
        filter=option[1];filterMenu:Hide();render()
    end)
end
local scroll=U.scroll(CreateFrame("ScrollFrame","TormentBlacksmithRecipeScroll",forge,"UIPanelScrollFrameTemplate"))
scroll:SetSize(214,336);scroll:SetPoint("TOPLEFT",0,-28)
local list=CreateFrame("Frame",nil,scroll);list:SetSize(214,336);scroll:SetScrollChild(list)
local searchBox=U.input(forge)
searchBox:SetSize(214,20);searchBox:SetPoint("TOPLEFT",6,-372);searchBox:SetMaxLetters(40)
local hint=searchBox:CreateFontString(nil,"OVERLAY","GameFontDisableSmall");hint:SetPoint("LEFT",6,0);hint:SetText("Search")
local detail=CreateFrame("Frame",nil,forge);detail:SetSize(270,368);detail:SetPoint("TOPLEFT",246,-4)
flat(detail,U.DETAIL_BG[1],U.DETAIL_BG[2],U.DETAIL_BG[3],U.DETAIL_BORDER[1],U.DETAIL_BORDER[2],U.DETAIL_BORDER[3])
detail.icon=icon(detail,54,12,-12);detail.name=text(detail,76,-18,186,"GameFontNormalLarge")
detail.level=text(detail,76,-40,186,"GameFontHighlightSmall");colour(detail.level,GREY)
detail.note=text(detail,14,-58,246,"GameFontHighlightSmall");detail.note:SetHeight(44)
local required=text(detail,14,-142,246,"GameFontNormal");required:SetText("Required materials")
detail.cost=text(detail,14,-336,246,"GameFontHighlight");detail.reagents={}
for i=1,8 do
    local r=U.material(detail,10+((i-1)%2)*128,-164-math.floor((i-1)/2)*40,76)
    r:SetScript("OnEnter",function(self) tip(self,self.entry) end);r:SetScript("OnLeave",function() GameTooltip:Hide() end)
    detail.reagents[i]=r
end
local createAll=actionButton(forge,"Create All",246,-376,90,function() B.Create(true) end)
local down=actionButton(forge,"<",344,-376,22,function() qty=math.max(1,qty-1);render() end)
local qtyBox=U.input(forge);qtyBox:SetSize(40,20);qtyBox:SetPoint("TOPLEFT",376,-377);qtyBox:SetJustifyH("CENTER");qtyBox:SetNumeric(true);qtyBox:SetMaxLetters(4)
local up=actionButton(forge,">",422,-376,22,function() qty=qty+1;render() end)
local create=actionButton(forge,"Create",450,-376,80,function() B.Create(false) end)
-- The gold line stays on every tab, so it lives on the window, at the Jeweler's own spot.
local funds=text(frame,16,-474,512,"GameFontNormal")
local bar=U.bar(forge)
-- The Salvage and Repair bodies are framed like the Jeweler's second-tab view (DCUI U.box).
local salvage=CreateFrame("Frame",nil,frame);salvage:SetPoint("TOPLEFT",16,-64);salvage:SetPoint("BOTTOMRIGHT",-16,16)
local salvageBox=U.box(salvage)
local salvageHeading=text(salvageBox,14,-16,480,"GameFontNormalLarge");salvageHeading:SetText("Salvage")
local salvageHint=text(salvageBox,14,-42,480,"GameFontHighlightSmall");salvageHint:SetText("Convert items into crafting materials");colour(salvageHint,GREY)
local salvageButtons={};local salvageMode=false
-- Continuous salvage: the arm survives a pick, so every
-- exit must disarm it, drop the cursor and kill a pending confirmation. One place, so the exits
-- (right-click, Escape/close, another tab, a bulk button, the anvil off) cannot drift apart.
local salvageConfirm=nil
local function disarmSalvage()
    salvageMode=false;salvageConfirm=nil
    if StaticPopup_Hide then StaticPopup_Hide("TORMENT_BLACKSMITH_SALVAGE") end
end
-- The rarity border: a 2 px frame on the OVERLAY layer, so it draws above the
-- slot's ARTWORK icon instead of under it (which cut the colour off at the top), with all four
-- sides anchored inside the button. One definition, used by every rarity button, so none drifts.
local SALVAGE_BORDER=2
local BORDER_POINTS={top={"TOPLEFT","TOPRIGHT"},bottom={"BOTTOMLEFT","BOTTOMRIGHT"},left={"TOPLEFT","BOTTOMLEFT"},right={"TOPRIGHT","BOTTOMRIGHT"}}
local function rarityBorder(button,tint)
    button.border=button.border or {}
    for _,side in ipairs({"top","bottom","left","right"}) do
        local tex=button.border[side]
        if not tex then tex=button:CreateTexture(nil,"OVERLAY");button.border[side]=tex end
        tex:SetTexture(tint[1],tint[2],tint[3],1);tex:ClearAllPoints()
        tex:SetPoint(BORDER_POINTS[side][1],button,BORDER_POINTS[side][1],0,0)
        tex:SetPoint(BORDER_POINTS[side][2],button,BORDER_POINTS[side][2],0,0)
        if side=="top" or side=="bottom" then tex:SetHeight(SALVAGE_BORDER) else tex:SetWidth(SALVAGE_BORDER) end
    end
    return button.border
end
local salvageDefs={{label="Salvage an item",tint={1,.5,0}},{label="Salvage all Normal",tint=TINT.normal,rarity=0},{label="Salvage all Magic",tint=TINT.magic,rarity=1},{label="Salvage all Rare",tint=TINT.rare,rarity=2}}
for i,def in ipairs(salvageDefs) do
    local b=icon(salvage,i==1 and 64 or 46,36+(i-1)*112,-118)
    b.icon:SetTexture("Interface\\Icons\\Trade_BlackSmithing");b:SetBackdropBorderColor(def.tint[1],def.tint[2],def.tint[3],1);rarityBorder(b,def.tint)
    b:SetScript("OnClick",function()
        if pending or query then return end
        if i==1 then
            -- The anvil toggles the arm; turning it off is one of the exits.
            if salvageMode then disarmSalvage() else salvageMode=true end
            B.ScanButtons();render()
        else
            -- Any bulk button ends the pick.
            disarmSalvage();render();B.Send("bulk",def.rarity)
        end
    end)
    b:SetScript("OnEnter",function(self) GameTooltip:SetOwner(self,"ANCHOR_RIGHT");GameTooltip:SetText(def.label);GameTooltip:Show() end)
    b:SetScript("OnLeave",function() GameTooltip:Hide() end);salvageButtons[i]=b
end
-- Single-item pick cursor: the
-- client's own repair cursor, Interface\CURSOR\Repair, the hammer the merchant's repair mode
-- draws. ShowRepairCursor() cannot be used here: it *is* that merchant mode, its only stock
-- caller is the Repair-an-Item toggle (MerchantFrame.xml:456/459), and the client honours it
-- only while a repair-capable merchant is open - which our AIO gossip window is not, so it
-- silently did nothing. SetCursor takes a texture path outside any merchant, exactly as the
-- stock vehicle menu does (SetCursor("Interface\\CURSOR\\vehichleCursor"),
-- VehicleMenuBar.lua:1039), and the client honours a call made while the mouse is over the
-- calling frame. Every call below therefore comes from a hover handler of one of ours (or of
-- the bag buttons we wrap, hooked so it runs after ContainerFrame_OnEnter, which resets the
-- cursor), never from a timer, and is reset on leave, on the pick, on cancel, on close and on
-- a tab switch.
local PICK_CURSOR="Interface\\CURSOR\\Repair"
local pickHovered,pickShown=false,false
local function pickOver()
    return frame:IsShown() and ((tab=="salvage" and salvageMode) or tab=="repair")
end
-- The cursor is re-set unconditionally while armed and hovered - no "already shown"
-- short-circuit, because the stock code resets it behind our back - and no call comes from a
-- timer: only from a hover or a stock re-entry of the frame it is over.
-- The stored hover is only live while its surface is still visible and still the frame under the
-- mouse: a bag window closed with the mouse on a slot, or ElvUI hiding or reusing a slot, does not
-- reliably fire OnLeave in 3.3.5, and ResetCursor is hooked below, so a stale surface would pin the
-- hammer on every reset in the UI - on the Repair tab for as long as the tab is open.
-- A surface a single-item pick can start from: our own frames, and the bag/equipment buttons.
local pickSurfaces={}
local function pickLive()
    local surface=pickHovered
    if not surface then return nil end
    if surface.IsVisible and not surface:IsVisible() then return nil end
    local focus=GetMouseFocus and GetMouseFocus()
    if focus==surface then return surface end
    -- The ElvUI rule: while the mouse has not moved, the frame under it stays the slot even when
    -- the tooltip covers the cursor. Any other focus means the mouse has left.
    if pickSurfaces[focus] then return focus end
    return nil
end
local function pickSync()
    pickHovered=pickLive()
    if pickHovered and pickOver() then
        SetCursor(PICK_CURSOR);pickShown=true
    elseif pickShown then
        -- Clear the flag first: ResetCursor is hooked (below), so the hook re-enters here.
        pickShown=false;ResetCursor()
    end
end
-- The function that actually resets the cursor is ResetCursor: the tooltip refresh re-enters the
-- button it is owned by (GameTooltip.lua:186-195 calls owner:UpdateTooltip(), which for a bag
-- button IS ContainerFrameItemButton_OnEnter - ContainerFrame.lua:620 - called as a plain
-- function) and that function ends in ResetCursor (ContainerFrame.lua:790); the bag button
-- template's own OnLeave resets it too (ContainerFrame.xml:50-56); CursorUpdate (UIParent.lua:2922,
-- reached from PaperDollItemSlotButton_OnEnter, PaperDollFrame.lua:1351) resets it for the
-- equipment slots. Hooking ResetCursor itself puts the re-assert inside the very call that resets,
-- so not one frame draws the default cursor.
if type(_G.ResetCursor)=="function" and hooksecurefunc then
    hooksecurefunc("ResetCursor",function() pickSync() end)
end
local function pickSurface(button)
    if not button or not button.HookScript then return end
    pickSurfaces[button]=true
    button:HookScript("OnEnter",function(self) pickHovered=self;pickSync() end)
    -- ElvUI is the client's bags (launcher-manifest.md:53-57) and anchors its tooltip AT the
    -- cursor (ElvUI/Modules/Tooltip/Tooltip.lua:139), so over one of its slots the client fires
    -- OnLeave/OnEnter at frame rate as the tooltip covers and uncovers the item. So the leave does
    -- not clear the hover itself: pickSync re-checks it (still visible, still under the mouse) and
    -- drops it only when the mouse has really gone.
    button:HookScript("OnLeave",function(self) if pickHovered==self then pickSync() end end)
end
-- The anvil is a toggle, not a pick target (hovering it should not arm a cursor), so the
-- surfaces are the Salvage body, the Repair body and slot, and the wrapped bag buttons.
pickSurface(salvageBox)
local salvagePrompt=text(salvage,6,-186,500,"GameFontHighlightSmall");salvagePrompt:SetHeight(36)
local resultScroll=U.scroll(CreateFrame("ScrollFrame","TormentBlacksmithResultScroll",salvage,"UIPanelScrollFrameTemplate"));resultScroll:SetSize(482,168);resultScroll:SetPoint("TOPLEFT",8,-234)
local resultList=CreateFrame("Frame",nil,resultScroll);resultList:SetSize(482,168);resultScroll:SetScrollChild(resultList)
local resultLabels={}
local repair=CreateFrame("Frame",nil,frame);repair:SetPoint("TOPLEFT",16,-64);repair:SetPoint("BOTTOMRIGHT",-16,16)
local repairBox=U.box(repair)
pickSurface(repairBox)
local repairSlot=icon(repairBox,64,14,-16);local repairName=text(repairBox,92,-24,300,"GameFontNormalLarge")
pickSurface(repairSlot)
local repairHint=text(repairBox,92,-52,360,"GameFontHighlightSmall");repairHint:SetText("Right-click an item in your bags or equipment, or drop it here.");repairHint:SetHeight(34);colour(repairHint,GREY)
local repairOne=actionButton(repair,"Select an item to see its repair cost",36,-118,446,function() if repairItem then B.Send("repairitems",0,repairItem.guid) end end)
local repairEquipped=actionButton(repair,"Equipped: calculating...",36,-160,446,function() B.Send("repairitems",1,0) end)
local repairAll=actionButton(repair,"All Items: calculating...",36,-202,446,function() B.Send("repairitems",2,0) end)
local tabs={};local TABDEFS={{"weapons","Forge Weapons","Interface\\Icons\\INV_Axe_04"},{"armor","Forge Armor","Interface\\Icons\\INV_Chest_Plate04"},{"salvage","Salvage","Interface\\Icons\\Trade_BlackSmithing"},{"repair","Repair","Interface\\Icons\\INV_Hammer_01"}}
-- Messages go where the Jeweler's do now (the error frame and, for a refusal, the chat);
-- the window has no status line.
local say=U.say
function B.Cancel()
    if not job then return false end
    job=nil;bar:Hide();say("Crafting cancelled.",true);return true
end
local function quote(scope,guid)
    SendAddonMessage("DCARTISAN","repairquote\t"..scope.."\t"..guid,"WHISPER",UnitName("player"))
end
function B.Tab(key)
    B.Cancel();tab=key;selected=nil;query=nil;disarmSalvage();searchBox:ClearFocus();qtyBox:ClearFocus();quotes={};filterMenu:Hide()
    if tab=="repair" then quote(1,0);quote(2,0);if repairItem then quote(0,repairItem.guid) end end
    B.ScanButtons();render()
end
for i,def in ipairs(TABDEFS) do
    local b=U.tab(frame,48);b:SetPoint("TOPLEFT",frame,"TOPRIGHT",-2,-70-(i-1)*56);b.icon:SetTexture(def[3]);b.key=def[1]
    b:SetScript("OnClick",function() B.Tab(def[1]) end)
    b:SetScript("OnEnter",function(self) GameTooltip:SetOwner(self,"ANCHOR_RIGHT");GameTooltip:SetText(def[2]);GameTooltip:Show() end)
    b:SetScript("OnLeave",function() GameTooltip:Hide() end);tabs[i]=b
end
local function recipeById(id) for _,r in ipairs(model.recipes) do if r.id==id then return r end end end
local rowButtons={}
render=function()
    pickSync()
    if not frame:IsShown() then return end
    local forging=tab=="weapons" or tab=="armor"
    if forging then forge:Show() else forge:Hide() end
    if tab=="salvage" then salvage:Show() else salvage:Hide() end
    if tab=="repair" then repair:Show() else repair:Hide() end
    for _,b in ipairs(tabs) do U.tabActive(b,b.key==tab) end
    for _,def in ipairs(TABDEFS) do if def[1]==tab then sub:SetText(def[2]:upper()) end end
    funds:SetText("Your gold: "..commas(model.gold))
    local busy=pending or query or job
    if forging then
        filterButton:SetText(filter=="all" and "All" or filter=="highest" and "Highest usable" or "Have materials")
        local rows=Logic.rows(model,tab,filter,search,collapsed);local y=0;local expandAny=false
        -- The first recipe is selected on open, as the Jeweler does, so the detail pane is never
        -- empty with "Select a recipe".
        if not recipeById(selected) then for _,row in ipairs(rows) do if row.recipe then selected=row.recipe.id;break end end end
        for i,row in ipairs(rows) do
            local b=rowButtons[i]
            if not b then
                b=U.row(list);b:SetWidth(210)
                b:SetScript("OnClick",function(self)
                    if pending or query or job then return end
                    if self.row.category then collapsed[self.row.category]=not collapsed[self.row.category]
                    else selected=self.row.recipe.id;qty=1 end;render()
                end)
                b:SetScript("OnEnter",function(self) if self.row.recipe then tip(self,self.row.recipe.entry,nil,self.row.recipe) end end)
                b:SetScript("OnLeave",function(self) self.dcRecipeId=nil;GameTooltip:Hide() end);rowButtons[i]=b
            end
            b.row=row;b:SetPoint("TOPLEFT",0,-y);b.mark:Hide()
            if row.category then
                b.label:SetText((row.closed and "+ " or "- ")..(LABEL[row.category] or row.category));colour(b.label,GOLD)
                b.label:SetPoint("LEFT",U.HEAD_INDENT,0)
                expandAny=expandAny or row.closed;y=y+U.HEAD_STEP
            else
                -- A row's colour is its item's rarity, always - makeable or not.
                b.label:SetText("["..row.count.."] "..row.recipe.name.." ("..row.recipe.required..")");colour(b.label,TINT[row.recipe.rarity] or GREY)
                b.label:SetPoint("LEFT",U.ROW_INDENT,0)
                if row.recipe.id==selected then b.mark:Show() end;y=y+U.ROW_HEIGHT
            end
            b:Show()
        end
        for i=#rows+1,#rowButtons do rowButtons[i].row=nil;rowButtons[i]:Hide() end
        expand:SetText(expandAny and "Expand All" or "Collapse All");list:SetHeight(math.max(336,y))
        local r=recipeById(selected);local maximum=r and Logic.available(r,model) or 0
        qty=math.max(1,math.min(qty,math.max(1,maximum)));if not qtyBox:HasFocus() then qtyBox:SetText(tostring(qty)) end
        detail.icon.icon:SetTexture(r and iconOf(r.entry) or nil);detail.name:SetText(r and r.name or "Select a recipe")
        colour(detail.name,r and TINT[r.rarity] or GOLD)
        detail.level:SetText(r and ("Level "..r.required.." • "..r.rarity) or "")
        -- The tooltip now says what the craft makes, so the old sentence promising that the
        -- item rolls its properties is gone; only a disabled recipe's reason stays.
        detail.note:SetText(r and (r.enabled and "" or r.reason) or "")
        colour(detail.note,r and not r.enabled and RED or GREY)
        detail.icon:SetScript("OnEnter",function(self) if r then tip(self,r.entry,nil,r) end end);detail.icon:SetScript("OnLeave",function(self) self.dcRecipeId=nil;GameTooltip:Hide() end)
        detail.cost:SetText(r and ("Cost: "..commas(Logic.times(r.gold,qty)).." gold") or "")
        if r then colour(detail.cost,Logic.atLeast(model.gold,Logic.times(r.gold,qty)) and U.WHITE or RED) end
        for i,reagent in ipairs(detail.reagents) do
            local cost=r and r.materials[i]
            if cost then
                reagent.entry=cost.entry;reagent.icon:SetTexture(iconOf(cost.entry));reagent.label:SetText(cost.name)
                local amount=cost.amount*qty;local count=have(cost.entry)
                -- The shared count setter, the same one the Jeweler uses (UI fixes row 4).
                U.count(reagent,count,amount,Logic.atLeast(count,amount))
                reagent:Show();reagent.label:Show()
            else reagent:Hide();reagent.label:Hide() end
        end
        if not busy and maximum>0 then create:Enable();createAll:Enable() else create:Disable();createAll:Disable() end
        for _,b in ipairs({up,down,expand,filterButton}) do if busy then b:Disable() else b:Enable() end end
        qtyBox:EnableMouse(not busy);searchBox:EnableMouse(not busy)
    elseif tab=="salvage" then
        salvagePrompt:SetText(salvageMode and "Click items in your bags to salvage them. Escape, another tab or a button ends it; Legendary and Set items confirm first." or "Click the anvil to select items, or use a rarity button to salvage all matching items.")
        for _,b in ipairs(salvageButtons) do if busy then b:Disable() else b:Enable() end end
        local y=0
        for i,line in ipairs(results) do
            local l=resultLabels[i] or text(resultList,0,-y,473,"GameFontHighlightSmall");resultLabels[i]=l;l:SetPoint("TOPLEFT",0,-y);l:SetText(line);l:Show();y=y+22
        end
        for i=#results+1,#resultLabels do resultLabels[i]:Hide() end;resultList:SetHeight(math.max(168,y))
    else
        repairName:SetText(repairItem and repairItem.name or "Select an item")
        repairSlot.icon:SetTexture(repairItem and iconOf(repairItem.entry) or nil)
        repairSlot:SetScript("OnEnter",function(self) if repairItem then tip(self,repairItem.entry,repairItem) end end)
        repairSlot:SetScript("OnLeave",function() GameTooltip:Hide() end)
        for scope,b in pairs({[0]=repairOne,[1]=repairEquipped,[2]=repairAll}) do
            local q=quotes[scope];local label=scope==0 and "Repair Item" or scope==1 and "Equipped" or "All Items"
            b:SetText(q and (label..": "..commas(q.cost).." gold") or scope==0 and "Select an item to see its repair cost" or (label..": calculating..."))
            if q and q.cost~="0" and q.affordable and not busy then b:Enable() else b:Disable() end
        end
    end
end
local function aliveAndStill()
    return not (UnitIsDeadOrGhost and UnitIsDeadOrGhost("player")) and not (UnitAffectingCombat and UnitAffectingCombat("player")) and (not GetUnitSpeed or GetUnitSpeed("player")==0)
end
function B.Send(verb,...)
    if pending or query or job then return false end
    local parts={verb};for i=1,select("#",...) do parts[#parts+1]=tostring(select(i,...)) end
    pending={verb=verb,time=GetTime(),materials={},items={},returned={}}
    for key,value in pairs(model.materials) do pending.materials[key]=value end
    for _,item in ipairs(model.items) do pending.items[item.guid]=item.count or 1 end
    SendAddonMessage("DCARTISAN",table.concat(parts,"\t"),"WHISPER",UnitName("player"));render();return true
end
function B.Create(all)
    local r=recipeById(selected)
    if not r or not r.enabled or job or pending or query then return false end
    if not aliveAndStill() then say("Stand still and leave combat to craft.",true);return false end
    local maximum=Logic.available(r,model);local count=all and maximum or math.min(qty,maximum)
    if count<1 then say("Not enough materials or gold.",true);return false end
    local duration=model.castSeconds
    if type(duration)~="number" or duration<=0 then say("Crafting is currently unavailable.",true);return false end
    qty=count;job={id=r.id,count=count,elapsed=0,duration=duration,name=r.name};qtyBox:ClearFocus();searchBox:ClearFocus();filterMenu:Hide()
    bar:SetValue(0);bar.text:SetText("Crafting "..count.." "..r.name);bar:Show();render();return true
end
searchBox:SetScript("OnTextChanged",function(self) search=self:GetText() or "";if search=="" then hint:Show() else hint:Hide() end;scroll:SetVerticalScroll(0);render() end)
searchBox:SetScript("OnEnterPressed",function(self) self:ClearFocus() end)
searchBox:SetScript("OnEscapePressed",function(self) self:ClearFocus();frame:Hide() end)
qtyBox:SetScript("OnTextChanged",function(self,user)
    if user and not job then
        qty=math.max(1,math.floor(tonumber(self:GetText()) or 1));render()
        if tostring(qty)~=self:GetText() then self:SetText(tostring(qty)) end
    end
end)
qtyBox:SetScript("OnEditFocusLost",function(self) self:SetText(tostring(qty)) end)
qtyBox:SetScript("OnEnterPressed",function(self) self:ClearFocus();B.Create(false) end)
qtyBox:SetScript("OnEscapePressed",function(self) self:ClearFocus();frame:Hide() end)
frame:SetScript("OnHide",function() B.Cancel();query=nil;disarmSalvage();repairItem=nil;quotes={};pickHovered=nil;pickSync();searchBox:ClearFocus();qtyBox:ClearFocus();filterMenu:Hide();GameTooltip:Hide() end)

-- Consume the click before the stock bag handler picks up/equips an item. Wrapping
-- the existing OnClick also works with completely full bags; no spare slot or
-- temporary item ID is required. Outside the active mode the original is called.
local wrapped={}
local function clickActive(button,equipment)
    if not frame:IsShown() or (InCombatLockdown and InCombatLockdown()) then return false end
    if GetCursorInfo and GetCursorInfo() then return false end
    if (IsShiftKeyDown and IsShiftKeyDown()) or (IsControlKeyDown and IsControlKeyDown()) or (IsAltKeyDown and IsAltKeyDown()) then return false end
    return (tab=="salvage" and salvageMode and not equipment) or (tab=="repair" and button=="RightButton")
end
-- The Repair tab takes the right-click, so it registers the claim every Torment screen uses (Inventory.lua:
-- claims are asked first, so the order is Jeweler Unsocket / Blacksmith Repair > stash deposit > potion > stock).
-- It is true ONLY while a right-click would be consumed by the wrapper below (window shown, Repair tab, out of
-- combat, nothing on the cursor, no modifier key), so on Forge and Salvage, or with the window closed, the
-- stash and potion rules act as before.
local function takesRightClick() return clickActive("RightButton",false) end
if Diablocraft and type(Diablocraft.ClaimRightClick)=="function" then Diablocraft.ClaimRightClick(takesRightClick) end
function B.Pick(bag,slot)
    -- One pick in flight at a time; a confirmation dialog waits too, so a click on another item
    -- while it is up sends nothing.
    if pending or query or job or salvageConfirm then return end
    -- Continuous salvage: the arm and the cursor survive the pick; only an
    -- exit (right-click, Escape/close, another tab, a bulk button, the anvil off) disarms.
    nonce=nonce%4294967295+1;query={nonce=nonce,tab=tab,time=GetTime()}
    AIO.Handle(CHANNEL,"Target",bag,slot,nonce);render()
end
local function wrap(button,equipment)
    if not button or wrapped[button] or not button.GetScript then return end
    local original=button:GetScript("OnClick");if not original then return end
    wrapped[button]=true
    -- The pick surface: hooked, not replaced, because the stock bag OnEnter resets the cursor.
    pickSurface(button)
    button:SetScript("OnClick",function(self,mouse,...)
        -- Armed single-item salvage: a right-click cancels the pick, as the client's repair
        -- cursor does, and is consumed.
        if tab=="salvage" and salvageMode and mouse=="RightButton" and frame:IsShown() and not (InCombatLockdown and InCombatLockdown()) then
            disarmSalvage();render();return
        end
        if clickActive(mouse,equipment) then
            local bag,slot
            if equipment then
                -- Torment's sheet stores the core slot directly; stock PaperDoll
                -- buttons store the client's one-based inventory ID in GetID().
                bag,slot=255,self.equipSlot or (self:GetID()-1)
            else bag,slot=self:GetParent():GetID(),self:GetID() end
            B.Pick(bag,slot);return
        end
        return original(self,mouse,...)
    end)
end
function B.ScanButtons()
    if InCombatLockdown and InCombatLockdown() then return end
    for f=1,(NUM_CONTAINER_FRAMES or 13) do for s=1,(MAX_CONTAINER_ITEMS or 36) do wrap(_G["ContainerFrame"..f.."Item"..s],false) end end
    local E=_G.ElvUI and _G.ElvUI[1];local bags=E and E.GetModule and E:GetModule("Bags",true)
    local holder=bags and bags.BagFrame and bags.BagFrame.Bags
    if holder then for bag=0,4 do for _,button in pairs(holder[bag] or {}) do if type(button)=="table" and button.HookScript then wrap(button,false) end end end end
    for _,name in ipairs({"Head","Neck","Shoulder","Back","Chest","Shirt","Tabard","Wrist","Hands","Waist","Legs","Feet","Finger0","Finger1","Trinket0","Trinket1","MainHand","SecondaryHand","Ranged"}) do wrap(_G["Character"..name.."Slot"],true) end
    -- The visible Torment sheet replaces the stock paperdoll. Its virtual potion
    -- slot is outside native equipment (0-18) and has no durability to quote.
    for slot=0,18 do
        wrap(_G["DiablocraftGearSlot"..slot],true)
        wrap(_G["DiablocraftCosmeticSlot"..slot],true)
    end
end
local cursorBag,cursorSlot
if PickupContainerItem then hooksecurefunc("PickupContainerItem",function(bag,slot) cursorBag,cursorSlot=bag,slot end) end
if PickupInventoryItem then hooksecurefunc("PickupInventoryItem",function(slot) cursorBag,cursorSlot=255,slot-1 end) end
local function drop()
    if tab~="repair" or GetCursorInfo()~="item" or not cursorBag or not cursorSlot then return end
    local bag,slot=cursorBag,cursorSlot;ClearCursor();cursorBag,cursorSlot=nil,nil;B.Pick(bag,slot)
end
repairSlot:SetScript("OnReceiveDrag",drop);repairSlot:SetScript("OnClick",drop)
StaticPopupDialogs["TORMENT_BLACKSMITH_SALVAGE"]={text="Salvage %s? This permanently destroys the item.",button1="Salvage",button2=CANCEL,
    OnAccept=function(self)
        local item=self.data
        salvageConfirm=nil
        if item and frame:IsShown() and tab=="salvage" then B.Send("salvage",item.guid) end
    end,
    -- Cancel, Escape and the accept all hide the dialog; the pick waits again from here.
    OnHide=function() salvageConfirm=nil end,timeout=0,whileDead=false,hideOnEscape=true,preferredIndex=3}
function handlers.Target(_,payload)
    if not query or query.nonce~=payload.nonce or query.tab~=tab or not frame:IsShown() then return end
    query=nil;local item=payload.item
    if not item then say("That item is no longer there.",true);render();return end
    if tab=="salvage" then
        if not item.managed or item.equipped then say("Choose unequipped Torment gear.",true)
        elseif item.rarity~="normal" and item.rarity~="magic" and item.rarity~="rare" then
            -- The pick waits while this dialog is up: B.Pick refuses another until it is answered.
            salvageConfirm=true
            local popup=StaticPopup_Show("TORMENT_BLACKSMITH_SALVAGE",item.name);if popup then popup.data=item end
        else B.Send("salvage",item.guid) end
    elseif tab=="repair" then repairItem=item;quotes[0]=nil;quote(0,item.guid) end
    render()
end
function handlers.Show(_,payload)
    if payload.refresh and not frame:IsShown() then return end
    -- A tunable or catalogue change moves what the roller would do, so drop the recipe
    -- previews drawn from the old numbers before this payload's list is drawn.
    if DCRecipePreviewsClear then DCRecipePreviewsClear() end
    if not payload.refresh then B.Cancel();tab="weapons";selected=nil;results={} end
    model=payload;title:SetText(payload.title or "Blacksmith");frame:Show()
    if DCJeweler and DCJeweler.ui and DCJeweler.ui.frame then DCJeweler.ui.frame:Hide() end
    if DiablocraftCraftingFrame then DiablocraftCraftingFrame:Hide() end
    if repairItem then
        local exists=false;for _,item in ipairs(model.items) do if item.guid==repairItem.guid then repairItem=item;exists=true end end
        if not exists then repairItem=nil;quotes[0]=nil end
    end
    if tab=="repair" then quotes={};quote(1,0);quote(2,0);if repairItem then quote(0,repairItem.guid) end end
    B.ScanButtons();render()
end
function handlers.Error(_,message) query=nil;say(message,true);render() end
-- The server's range watcher: the player walked away from the Blacksmith. OnHide cancels a craft in progress.
function handlers.Close() frame:Hide() end
local function split(s,delimiter) local out={};for field in (s..delimiter):gmatch("(.-)"..delimiter) do out[#out+1]=field end;return out end
function B.Reply(prefix,body,distribution,sender)
    if prefix~="DCARTISAN" or distribution~="WHISPER" then return end
    local own=UnitName("player");if sender~=own and sender~=own.."-"..GetRealmName() then return end
    local f=split(body,"|")
    if f[1]=="Q" then
        local scope,guid=tonumber(f[2]),tonumber(f[3])
        if tab=="repair" and scope and scope<=2 and (scope~=0 or (repairItem and repairItem.guid==guid)) then quotes[scope]={cost=f[4],affordable=f[5]=="1"};render() end
        return
    end
    if not pending then
        if f[1]=="X" and frame:IsShown() then say(f[2] or "Repair price is unavailable.",true) end
        return
    end
    if f[1]=="B" then model.gold=f[2]
    elseif f[1]=="M" then for i=2,#f do local e,n=f[i]:match("^(%d+):(%d+)$");if e then model.materials[tonumber(e)]=n end end
    elseif f[1]=="I" then
        for i=2,#f do
            local guid,entry,count=f[i]:match("^(%d+):(%d+):(%d+):")
            if guid then
                local delta=tonumber(count)-(pending.items[tonumber(guid)] or 0)
                if delta>0 then pending.returned[tonumber(entry)]=(pending.returned[tonumber(entry)] or 0)+delta end
            end
        end
    elseif f[1]=="R" and f[2]==pending.verb then pending.count=tonumber(f[3]) or 0
    elseif f[1]=="E" and f[2]==pending.verb then
        local verb=pending.verb;local count=pending.count or 0
        if verb=="salvage" or verb=="bulk" then
            results[#results+1]="Salvaged "..count.." item(s)."
            for entry,new in pairs(model.materials) do
                local old=pending.materials[entry] or pending.materials[tostring(entry)] or "0"
                local gain=Logic.minus(new,old)
                if gain~="0" then
                    local name=GetItemInfo(tonumber(entry))
                    for _,material in ipairs(Diablocraft and Diablocraft.Econ and Diablocraft.Econ.MATERIALS or {}) do if material.entry==tonumber(entry) then name=material.name end end
                    results[#results+1]="+"..commas(gain).." "..(name or "Crafting material")
                end
            end
            for entry,gemCount in pairs(pending.returned) do local name=GetItemInfo(entry);results[#results+1]="Returned "..gemCount.." "..(name or "gem(s)") end
            say("Salvaged "..count.." item(s).")
        else say(verb=="forge" and ("Crafted "..count.." item(s).") or "Items repaired.") end
        pending=nil;AIO.Handle(CHANNEL,"Refresh");AIO.Handle("DiablocraftTooltip","Refresh");render()
    elseif f[1]=="X" then
        pending=nil;say(f[2] or "The server refused that action.",true);AIO.Handle(CHANNEL,"Refresh");render()
    end
end
local watcher=CreateFrame("Frame");local elapsed,dirty=0,false
for _,event in ipairs({"CHAT_MSG_ADDON","BAG_UPDATE","PLAYER_EQUIPMENT_CHANGED","PLAYER_REGEN_DISABLED","GOSSIP_CLOSED","PLAYER_DEAD"}) do watcher:RegisterEvent(event) end
watcher:SetScript("OnEvent",function(_,event,...)
    if event=="CHAT_MSG_ADDON" then B.Reply(...)
    elseif event=="PLAYER_REGEN_DISABLED" or event=="GOSSIP_CLOSED" or event=="PLAYER_DEAD" then B.Cancel();query=nil;disarmSalvage();render()
    else dirty=true end
end)
watcher:SetScript("OnUpdate",function(_,dt)
    if job then
        if not frame:IsShown() or not aliveAndStill() then B.Cancel();render()
        else
            job.elapsed=job.elapsed+dt;bar:SetValue(math.min(1,job.elapsed/job.duration))
            if job.elapsed>=job.duration then local done=job;job=nil;bar:Hide();B.Send("forge",done.id,done.count) end
        end
    end
    elapsed=elapsed+dt
    if elapsed>=.5 then
        elapsed=0
        if frame:IsShown() then
            if pending and GetTime()-pending.time>5 then pending=nil;say("Waiting for the server. Refreshing items and balances.",true);dirty=true end
            if query and GetTime()-query.time>5 then query=nil;say("Item selection timed out. Try again.",true) end
            B.ScanButtons()
            if dirty and not pending and not query and not job then dirty=false;AIO.Handle(CHANNEL,"Refresh") end
            render()
        end
    end
end)
B.ui={frame=frame,forge=forge,salvage=salvage,repair=repair,tabs=tabs,list=list,rows=rowButtons,search=searchBox,quantity=qtyBox,
    bar=bar,create=create,createAll=createAll,filter=filterButton,filterOptions=filterOptions,expand=expand,down=down,up=up,detail=detail,salvageButtons=salvageButtons,
    repairOne=repairOne,repairEquipped=repairEquipped,repairAll=repairAll,repairSlot=repairSlot,watcher=watcher,
    title=title,sub=sub,funds=funds,salvageBox=salvageBox,repairBox=repairBox}

-- Account currency can change without a bag event (material-only loot or a GM
-- credit). Use the addon's authenticated snapshot, copying rather than mutating it.
if Diablocraft and Diablocraft.Econ and Diablocraft.Econ.OnChange then
    Diablocraft.Econ.OnChange(function(snapshot)
        if not frame:IsShown() then return end
        if not snapshot then frame:Hide();return end
        model.gold=snapshot.balance;model.materials={}
        for entry,amount in pairs(snapshot.materials or {}) do model.materials[entry]=amount end
        for _,q in pairs(quotes) do q.affordable=Logic.atLeast(model.gold,q.cost) end
        render()
    end)
end
