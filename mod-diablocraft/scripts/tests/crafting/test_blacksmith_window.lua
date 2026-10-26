-- luacheck: ignore 111 112 113 121 122
-- Functional Blacksmith client checks against the shared strict 3.3.5a widget mock
-- (dc_widget_mock.lua); the client model below (cursor rules, bag/ElvUI slots, hovers) is the
-- test's own.
local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local sent={};local aio={};local handlers={}
local now,speed,combat=0,0,false
Mock.setScreen(1024,768)
CANCEL="Cancel"
local popup
function StaticPopup_Show(name) popup={name=name};return popup end
function StaticPopup_Hide() popup=nil end
function UnitName() return "Tester" end
function GetRealmName() return "Torment" end
function GetTime() return now end
function GetUnitSpeed() return speed end
function UnitAffectingCombat() return combat end
function InCombatLockdown() return combat end
function UnitIsDeadOrGhost() return false end
function GetItemIcon(e) return "icon:"..e end
function GetItemInfo(e) return "Item "..e end
function GetCursorInfo() return nil end
-- The client's own cursor rules, modelled (diablocraft-salvage-cursor; the SetColorTexture
-- lesson: a mock that accepts any call proves nothing).
--   * ShowRepairCursor() is the merchant's repair mode - MerchantFrame.xml:456/459 is its only
--     stock caller - and the client shows it only while a repair-capable merchant is open.
--   * SetCursor takes effect only while the mouse is over the frame asking for it: a bare call
--     from a timer, or from a frame the mouse has left, changes nothing.
--   * ResetCursor is honoured from anywhere (the stock handlers call it).
local merchants,mouseOver,cursor=0,nil,nil
local cursorCalls={}
function ShowRepairCursor() if merchants>0 then cursor="merchant" cursorCalls[#cursorCalls+1]="show" end end
function HideRepairCursor() if merchants>0 then cursor=nil cursorCalls[#cursorCalls+1]="hide" end end
function SetCursor(kind) if mouseOver then cursor=kind cursorCalls[#cursorCalls+1]=kind end end
function ResetCursor() cursor=nil cursorCalls[#cursorCalls+1]="reset" end
-- The frame the mouse is really over: the client's hit test ignores frames that are not
-- mouse-enabled (the tooltip is not), so a hover that never moved keeps its frame.
function GetMouseFocus() return mouseOver end
local function merchant(open) merchants=open and 1 or 0 end
local function fire(target,event)
    local script=target.scripts and target.scripts[event]
    if script then script(target) end
end
-- Hovering is what the client does: leave the old frame, then enter the new one.
local function hover(target)
    if mouseOver and mouseOver~=target then fire(mouseOver,"OnLeave") end
    mouseOver=target
    fire(target,"OnEnter")
end
local function unhover(target)
    if mouseOver==target then mouseOver=nil;fire(target,"OnLeave") end
end
-- One GameTooltip_OnUpdate tick: the tooltip re-enters the frame it is owned by, as a plain
-- call, so the OnEnter hook does not run - exactly the path that reset the cursor behind us.
local function tooltipTick()
    local owner=GameTooltip.owner
    if owner and owner.UpdateTooltip then owner.UpdateTooltip(owner) end
end
-- ContainerFrame.lua:620/790: a bag button's UpdateTooltip IS this function - assigned in
-- ContainerFrameItemButton_OnLoad, which runs when the button is created, long before any addon
-- hooks the global - and it ends in ResetCursor. PaperDollFrame.lua:1140 with its CursorUpdate
-- ends the same way (:1351). The buttons below therefore capture these originals, exactly as the
-- client's own frames and ElvUI's slots do.
function ContainerFrameItemButton_OnEnter(self)
    GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
    ResetCursor()
end
function PaperDollItemSlotButton_OnEnter(self)
    GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
    ResetCursor()
end
-- ElvUI is the client's bags (launcher-manifest.md:53-57; ElvUI/Modules/Bags/Bags.lua:647 builds
-- every slot from ContainerFrameItemButtonTemplate) and its tooltip is anchored at the cursor
-- (ElvUI/Modules/Tooltip/Tooltip.lua:139). Its module runs before Torment loads, so the slot
-- captured the stock handler when it was created - ContainerFrame.lua:620 assigns UpdateTooltip in
-- OnLoad - and its tooltip refresh calls that ORIGINAL, never a hooksecurefunc wrapper. Its OnLeave
-- is the template's own (ContainerFrame.xml:50-56: hide the tooltip, ResetCursor), which fires as
-- the tooltip covers the cursor while the mouse has not moved.
local elvuiCaptured=ContainerFrameItemButton_OnEnter
local elvuiBag=CreateFrame("Button","ElvUIBag0Slot1")
elvuiBag:SetScript("OnClick",function() end)   -- every real slot has the template's OnClick
elvuiBag:SetScript("OnEnter",function(self) elvuiCaptured(self) end)
elvuiBag:SetScript("OnLeave",function() GameTooltip:Hide();ResetCursor() end)
elvuiBag.UpdateTooltip=function(self) elvuiCaptured(self) end
ElvUI={[1]={GetModule=function() return {BagFrame={Bags={[0]={elvuiBag}}}} end}}
local originalClicks=0
local accountChange
local claims={}
local previews={}
DCShowRecipePreview=function(_,recipe) previews[#previews+1]=recipe end
local sharedBackdrop,sharedFlat={shared="backdrop"},{shared="flat"}
local styleCloses,styleButtons={},{}
Diablocraft={Econ={Gold=function(value) return tostring(value or "0") end,OnChange=function(callback) accountChange=callback end},
    ClaimRightClick=function(claim) claims[#claims+1]=claim end,
    Style={backdrop=sharedBackdrop,flat=sharedFlat,
        Close=function(parent) local b=CreateFrame("Button",nil,parent);styleCloses[#styleCloses+1]=b;return b end,
        Button=function(parent,width,label,fn) local b=CreateFrame("Button",nil,parent);b:SetWidth(width);b:SetText(label);b.scripts.OnClick=fn;styleButtons[#styleButtons+1]=b;return b end}}
local bag=CreateFrame("Frame");bag:SetID(0)
elvuiBag.parent=bag;elvuiBag:SetID(1)
ContainerFrame1Item1=CreateFrame("Button",nil,bag);ContainerFrame1Item1:SetID(1)
ContainerFrame1Item1:SetScript("OnClick",function() originalClicks=originalClicks+1 end)
ContainerFrame1Item1:SetScript("OnEnter",ContainerFrameItemButton_OnEnter)
ContainerFrame1Item1.UpdateTooltip=ContainerFrameItemButton_OnEnter      -- captured in OnLoad
CharacterHeadSlot=CreateFrame("Button",nil,UIParent)
-- wowgaming/3.3.5-interface-files d0339b17b0221db76e6acd2dc2915d224a5b62ca,
-- PaperDollFrame.lua:1130-1140: OnLoad stores GetInventorySlotInfo's one-based ID.
CharacterHeadSlot:SetID(1)
CharacterHeadSlot:SetScript("OnEnter",PaperDollItemSlotButton_OnEnter)
CharacterHeadSlot:SetScript("OnClick",function() originalClicks=originalClicks+1 end)
CharacterHeadSlot.UpdateTooltip=PaperDollItemSlotButton_OnEnter          -- captured in OnLoad
-- Inventory.lua buildSlot uses equipSlot (zero-based); these are plain buttons,
-- not PaperDollItemSlotButtonTemplate instances, and GetID does not identify gear.
local sheetClicks=0
local function sheetSlot(name,slot)
    local b=CreateFrame("Button",name,UIParent);b:SetID(0);b.equipSlot=slot;b.filled=true
    b:SetScript("OnClick",function(_,mouse)
        if mouse=="RightButton" then
            for _,claim in ipairs(claims) do if claim() then return end end
        end
        sheetClicks=sheetClicks+1
    end)
    return b
end
local sheetHead=sheetSlot("DiablocraftGearSlot0",0)
local sheetWeapon=sheetSlot("DiablocraftGearSlot15",15)
local sheetCosmetic=sheetSlot("DiablocraftCosmeticSlot18",18)
function SendAddonMessage(p,b,d,t) sent[#sent+1]={prefix=p,body=b,distribution=d,target=t} end
AIO={AddAddon=function() return false end,AddHandlers=function(name,t) handlers[name]=t;return t end,
    Handle=function(...) aio[#aio+1]={...} end}
dofile("mod-diablocraft/lua/aio/dc_aio_ui.lua")
dofile(os.getenv("DC_BLACKSMITH_LUA") or "mod-diablocraft/lua/aio/dc_blacksmith.lua")
local B,H,U=DCBlacksmith,handlers.DiablocraftBlacksmith,DCBlacksmith.ui
-- Today's look: the shared DC.Style, member by member, no copied PANEL (ruling 2026-10-01; same as the Jeweler).
assert(U.frame.backdrop==sharedBackdrop,"the window wears Diablocraft.Style.backdrop")
assert(#styleCloses==1 and styleCloses[1].parent==U.frame,"the native Close comes from Diablocraft.Style")
assert(#styleButtons>=5,"the buttons come from Diablocraft.Style.Button")
-- The right-click claim: the Repair tab takes it, nothing else does (Inventory.lua asks claims first).
assert(#claims==1,"exactly one right-click claim is registered")
local function click(b) assert(not b.disabled,"button disabled");b.scripts.OnClick(b,"LeftButton") end
local function tick(dt) now=now+dt;U.watcher.scripts.OnUpdate(U.watcher,dt) end
local function recipe(id,rarity,level,enabled)
    return {id=id,entry=id,name="Recipe "..id,category="Sword",page="weapons",rarity=rarity,required=level,level=level,
        gold="10",enabled=enabled~=false,reason=enabled==false and "Bounty materials are not available yet." or "",usableBy="",materials={{entry=102001,amount=2,name="Reusable Parts"}}}
end
local m={title="Haedrig",playerLevel=70,class="barbarian",gold="580",materials={[102001]="116"},maxCount=100,castSeconds=2,
    items={},recipes={recipe(1,"rare",70),recipe(2,"legendary",20),recipe(3,"set",20,false),recipe(4,"magic",70),recipe(5,"rare",20)}}
local rows=B.Logic.rows(m,"weapons","all","",{})
assert(rows[2].recipe.id==3 and rows[3].recipe.id==2 and rows[4].recipe.id==1 and rows[5].recipe.id==5 and rows[6].recipe.id==4,"rarity then level")
rows=B.Logic.rows(m,"weapons","highest","",{});assert(#rows==5,"highest per rarity/category")
rows=B.Logic.rows(m,"weapons","materials","",{});assert(#rows==5,"unavailable excluded")
rows=B.Logic.rows(m,"weapons","all","Recipe 2",{Sword=true});assert(#rows==2 and rows[2].recipe.id==2,"search opens category")
assert(B.Logic.available(m.recipes[1],m)==58)
assert(B.Logic.atLeast("18446744073709551615","18446744073709551614"))
assert(not B.Logic.atLeast("18446744073709551614","18446744073709551615"))
assert(B.Logic.times("18446744073709551615",2)=="36893488147419103230")
assert(B.Logic.minus("10000000000000000000","1")=="9999999999999999999")
assert(B.Logic.minus("1000","999")=="1")
H.Show(nil,m)
local accountSnapshot={balance="580",materials={[102001]="116"}}
accountChange(accountSnapshot);assert(m.materials~=accountSnapshot.materials,"copy the live account snapshot")
assert(U.frame:GetWidth()==560 and #U.tabs==4 and UISpecialFrames[1]=="TormentBlacksmithFrame")
click(U.filter);click(U.filterOptions[2]);assert(U.filter:GetText()=="Highest usable")
click(U.filter);click(U.filterOptions[1]);assert(U.filter:GetText()=="All")
local function selectRecipe(id)
    for _,b in ipairs(U.rows) do if b.row and b.row.recipe and b.row.recipe.id==id then click(b);return end end
    error("row missing")
end
-- diablocraft-blacksmith-tooltips: a recipe result hover hands the recipe to the item tooltip
-- for a preview, and the old sentence promising that the item rolls its properties is gone.
selectRecipe(1)
local recipeRow
for _,b in ipairs(U.rows) do if b.row and b.row.recipe and b.row.recipe.id==1 then recipeRow=b;break end end
assert(recipeRow,"recipe row 1 is drawn")
recipeRow.scripts.OnEnter(recipeRow)
assert(previews[#previews] and previews[#previews].id==1 and recipeRow.dcRecipeId==1,"a row hover asks for the preview")
U.detail.icon.scripts.OnEnter(U.detail.icon)
assert(previews[#previews].id==1 and U.detail.icon.dcRecipeId==1,"the detail icon hover asks for the preview")
assert(U.detail.note:GetText()=="","the old sentence is gone")
local disabled
for _,b in ipairs(U.rows) do if b.row and b.row.recipe and b.row.recipe.id==3 then disabled=b;break end end
assert(disabled and disabled.row.recipe.enabled==false,"the disabled recipe row is the Set one")
selectRecipe(3);assert(U.detail.note:GetText()~="","a disabled recipe still shows its reason")
selectRecipe(1)
selectRecipe(1);click(U.createAll);assert(#sent==0)
tick(1.99);assert(#sent==0 and U.bar.progress>.99)
tick(.01);assert(#sent==1 and sent[1].body=="forge\t1\t58","one batch request at two seconds")
assert(sent[1].target=="Tester" and sent[1].prefix=="DCARTISAN")
click(U.tabs[3]);B.Reply("DCARTISAN","E|forge","WHISPER","Intruder");assert(U.salvageButtons[2].disabled,"spoof ignored")
B.Reply("DCARTISAN","R|forge|58","WHISPER","Tester");B.Reply("DCARTISAN","E|forge","WHISPER","Tester")
click(U.salvageButtons[2]);assert(sent[#sent].body=="bulk\t0" and popup==nil,"bulk instant, no confirmation")
B.Reply("DCARTISAN","X|No matching items","WHISPER","Tester")
click(U.salvageButtons[1]);ContainerFrame1Item1.scripts.OnClick(ContainerFrame1Item1,"LeftButton")
assert(originalClicks==0 and ContainerFrame1Item1:GetID()==1,"consumed without spare inventory slots or item ID swap")
local nonce=aio[#aio][5]
H.Target(nil,{nonce=nonce,item={guid=123,entry=3,rarity="legendary",managed=true,name="Legend",bag=0,slot=1}})
local before=#sent;assert(popup and #sent==before)
StaticPopupDialogs.TORMENT_BLACKSMITH_SALVAGE.OnAccept(popup);assert(sent[#sent].body=="salvage\t123")
B.Reply("DCARTISAN","E|salvage","WHISPER","Tester")
click(U.tabs[1]);selectRecipe(1)
local function assertCancel(kind)
    local n=#sent;click(U.create);tick(.9)
    if kind=="move" then speed=1;tick(.1);speed=0
    elseif kind=="combat" then combat=true;U.watcher.scripts.OnEvent(U.watcher,"PLAYER_REGEN_DISABLED");combat=false
    elseif kind=="escape" then U.quantity:SetFocus();U.quantity.scripts.OnEscapePressed(U.quantity)
    elseif kind=="walkaway" then H.Close();assert(not U.frame:IsShown(),"the server's Close (the player walked away) hides the window")
    else U.frame:Hide() end
    tick(3);assert(#sent==n and not U.bar:IsShown(),"cancel must not pay/send: "..kind)
    H.Show(nil,m);selectRecipe(1)
end
for _,kind in ipairs({"move","combat","escape","close","walkaway"}) do assertCancel(kind) end
local n=#sent;click(U.create);tick(2);assert(sent[#sent].body=="forge\t1\t1" and #sent==n+1,"one-item batch also two seconds")
B.Reply("DCARTISAN","E|forge","WHISPER","Tester")
click(U.tabs[4])
assert(claims[1]()==true,"Repair tab, window shown: the Blacksmith claims the right-click")
combat=true;assert(claims[1]()==false,"not in combat");combat=false
IsShiftKeyDown=function() return true end;assert(claims[1]()==false,"not with a modifier key");IsShiftKeyDown=nil
GetCursorInfo=function() return "item" end;assert(claims[1]()==false,"not with an item on the cursor");GetCursorInfo=function() return nil end
local function repairClick(button,bagId,slot,guid)
    local messages,requests,stock,sheet=#sent,#aio,originalClicks,sheetClicks
    local id=button:GetID()
    button.scripts.OnClick(button,"RightButton")
    assert(#aio==requests+1,"repair right-click must request one target: "..guid)
    local request=aio[#aio]
    assert(request[1]=="DiablocraftBlacksmith" and request[2]=="Target" and request[3]==bagId and request[4]==slot,
        "repair right-click must resolve the clicked position: "..guid)
    assert(#sent==messages and originalClicks==stock and sheetClicks==sheet and button:GetID()==id,
        "targeting neither repairs nor unequips/uses the item, and preserves its button ID")
    H.Target(nil,{nonce=request[5],item={guid=guid,entry=guid,name="Repair target",bag=bagId,slot=slot,equipped=bagId==255}})
    assert(#sent==messages+1 and sent[#sent].body=="repairquote\t0\t"..guid,"the resolved GUID gets one single-item quote")
    assert(U.repairSlot.icon.texture=="icon:"..guid and U.repairOne.disabled,"the slot fills while the price is pending")
    B.Reply("DCARTISAN","Q|0|"..guid.."|12|1","WHISPER","Tester")
    assert(U.repairOne:GetText()=="Repair Item: 12 gold" and not U.repairOne.disabled,"the server quote enables single-item repair")
end
repairClick(ContainerFrame1Item1,0,1,501)
repairClick(elvuiBag,0,1,502)
repairClick(CharacterHeadSlot,255,0,503)
repairClick(sheetHead,255,0,504)
repairClick(sheetWeapon,255,15,505)
repairClick(sheetCosmetic,255,18,506)
local requests=#aio
sheetHead.scripts.OnClick(sheetHead,"LeftButton")
assert(#aio==requests and sheetClicks==1,"left-click retains the sheet's handler")
IsShiftKeyDown=function() return true end
CharacterHeadSlot.scripts.OnClick(CharacterHeadSlot,"RightButton")
assert(#aio==requests and originalClicks==1,"modified clicks retain the stock handler")
IsShiftKeyDown=nil
click(U.tabs[3]);assert(claims[1]()==false,"Salvage does not claim the right-click, so the stash and potion rules act there")
click(U.tabs[1]);assert(claims[1]()==false,"Forge does not claim it either")
sheetHead.scripts.OnClick(sheetHead,"RightButton")
assert(#aio==requests and sheetClicks==2,"outside Repair the sheet keeps its right-click")
click(U.tabs[4])
B.Reply("DCARTISAN","Q|1|0|45|1","WHISPER","Tester");B.Reply("DCARTISAN","Q|2|0|60|1","WHISPER","Tester")
assert(U.repairEquipped:GetText()=="Equipped: 45 gold" and U.repairAll:GetText()=="All Items: 60 gold")
click(U.repairEquipped);assert(sent[#sent].body=="repairitems\t1\t0")
B.Reply("DCARTISAN","E|repairitems","WHISPER","Tester")
U.frame:Hide();assert(claims[1]()==false,"a closed window claims nothing")

----------------------------------------------------------------------------------------------------
-- diablocraft-salvage-cursor: a single-item pick draws the client's repair hammer with
-- SetCursor from a hover handler (the merchant's ShowRepairCursor does nothing without a
-- merchant), and it resets on leave, the pick, cancel, close and a tab switch.
----------------------------------------------------------------------------------------------------
local clicksBeforeSalvage=originalClicks
H.Show(nil,m)
-- The merchant path still works where it belongs, so the model is not "nothing ever works".
merchant(true);ShowRepairCursor();assert(cursor=="merchant","a repair-capable merchant shows its own repair cursor")
merchant(false);cursor=nil
click(U.tabs[3])
hover(ContainerFrame1Item1)
assert(cursor==nil,"an unarmed bag hover shows no cursor")
unhover(ContainerFrame1Item1)
click(U.salvageButtons[1])
assert(cursor==nil,"arming does not show it by itself: ShowRepairCursor needs a merchant we do not have")
hover(ContainerFrame1Item1)
assert(cursor=="Interface\\CURSOR\\Repair","hovering a bag item while armed shows the repair hammer")
tooltipTick()
assert(cursor=="Interface\\CURSOR\\Repair","the hammer survives a tooltip refresh (owner:UpdateTooltip resets it)")
tooltipTick()
assert(cursor=="Interface\\CURSOR\\Repair","and every later refresh too")
unhover(ContainerFrame1Item1)
assert(cursor==nil,"leaving the item resets the cursor")
-- The equipment slots take the same refresh path.
hover(CharacterHeadSlot)
assert(cursor=="Interface\\CURSOR\\Repair","hovering an equipment slot while armed shows the hammer")
tooltipTick()
assert(cursor=="Interface\\CURSOR\\Repair","the hammer survives a tooltip refresh over an equipment slot")
unhover(CharacterHeadSlot)
assert(cursor==nil,"leaving the equipment slot resets the cursor")
-- Continuous salvage (ruling 2026-10-03, the bead's addition): a pick no longer disarms. The
-- hammer stays and the next click salvages the next item; a refused pick and a confirmation
-- keep the arm too. It ends on a right-click, Escape or the window closing, another tab, a bulk
-- button, or the anvil toggled off.
local PICK="Interface\\CURSOR\\Repair"
hover(ContainerFrame1Item1)
assert(cursor==PICK)
local picks=#aio
ContainerFrame1Item1.scripts.OnClick(ContainerFrame1Item1,"LeftButton")
assert(#aio==picks+1,"a click while armed asks the server for the item")
assert(cursor==PICK,"the hammer stays after a pick (continuous salvage)")
H.Target(nil,{nonce=aio[#aio][5],item=nil})
assert(cursor==PICK,"a refused pick keeps the arm and the hammer")
assert(UIErrorsFrame.lines[#UIErrorsFrame.lines]=="That item is no longer there.","a refusal still shows on the error line")
-- Three picks in a row salvage three items with ONE arm, and every one keeps the hammer.
local salvageSent=#sent
for i=1,3 do
    ContainerFrame1Item1.scripts.OnClick(ContainerFrame1Item1,"LeftButton")
    H.Target(nil,{nonce=aio[#aio][5],item={guid=200+i,entry=3,rarity="magic",managed=true,name="Item "..i,bag=0,slot=1}})
    assert(sent[#sent].body=="salvage\t"..(200+i),"pick "..i.." salvages its own item")
    B.Reply("DCARTISAN","E|salvage","WHISPER","Tester")
    assert(cursor==PICK,"the hammer is still there after pick "..i)
end
assert(#sent==salvageSent+3,"three picks, three salvage requests, one arm")
assert(originalClicks==clicksBeforeSalvage and ContainerFrame1Item1:GetID()==1,"every pick is consumed, no pickup/equip")
-- A higher rarity asks to confirm, and while the dialog is up the pick waits (nothing is sent).
local saves=#sent
ContainerFrame1Item1.scripts.OnClick(ContainerFrame1Item1,"LeftButton")
H.Target(nil,{nonce=aio[#aio][5],item={guid=300,entry=3,rarity="legendary",managed=true,name="Legend",bag=0,slot=1}})
assert(popup and #sent==saves,"a legendary waits for confirmation, nothing sent")
local waiting=#aio
ContainerFrame1Item1.scripts.OnClick(ContainerFrame1Item1,"LeftButton")
assert(#aio==waiting and #sent==saves,"a pick while the dialog is up waits")
-- An exit while the dialog is up cancels it: the arm ends, the glove returns, and the stale
-- dialog cannot salvage behind the player's back.
click(U.salvageButtons[1])
assert(popup==nil and #sent==saves and cursor==nil,"the anvil off cancels the confirmation, nothing sent")
click(U.salvageButtons[1]);assert(cursor==PICK,"armed again after the cancellation")
ContainerFrame1Item1.scripts.OnClick(ContainerFrame1Item1,"LeftButton")
H.Target(nil,{nonce=aio[#aio][5],item={guid=300,entry=3,rarity="legendary",managed=true,name="Legend",bag=0,slot=1}})
StaticPopupDialogs.TORMENT_BLACKSMITH_SALVAGE.OnAccept(popup)
StaticPopupDialogs.TORMENT_BLACKSMITH_SALVAGE.OnHide(popup)
assert(sent[#sent].body=="salvage\t300","confirming salvages that one item")
B.Reply("DCARTISAN","E|salvage","WHISPER","Tester")
assert(cursor==PICK,"the hammer stays after a confirmed pick")
-- A right-click cancels the pick, as today, and the glove comes back.
ContainerFrame1Item1.scripts.OnClick(ContainerFrame1Item1,"RightButton")
assert(cursor==nil,"a right-click cancels and resets the cursor")
assert(originalClicks==clicksBeforeSalvage and ContainerFrame1Item1:GetID()==1,"the cancelling right-click is consumed")
assert(not cursorCalls[#cursorCalls] or cursorCalls[#cursorCalls]=="reset","the reset is what the client saw")
-- Each exit disarms and gives the glove; the mouse never leaves the pick surface.
click(U.salvageButtons[1]);assert(cursor==PICK,"the anvil arms again")
click(U.salvageButtons[1]);assert(cursor==nil,"the anvil toggled off gives the glove")
click(U.salvageButtons[1]);assert(cursor==PICK,"armed again")
click(U.tabs[1]);assert(cursor==nil,"another tab gives the glove")
click(U.tabs[3]);click(U.salvageButtons[1]);assert(cursor==PICK,"armed again")
click(U.salvageButtons[2]);assert(cursor==nil,"a bulk salvage button gives the glove")
B.Reply("DCARTISAN","E|bulk","WHISPER","Tester")
assert(cursor==nil,"the bulk reply does not bring the glove back")
click(U.salvageButtons[1]);assert(cursor==PICK,"armed again")
-- the Repair tab's single-item mode shows the same hammer
click(U.tabs[4]);hover(ContainerFrame1Item1)
assert(cursor==PICK,"the Repair tab's single-item mode shows the repair hammer")
-- closing while hovered resets it (Escape hides the window the same way)
U.frame:Hide()
assert(cursor==nil,"closing the window resets the cursor")
-- closing while a confirmation is up cancels it too (the stale dialog cannot send afterwards)
H.Show(nil,m);click(U.tabs[3]);click(U.salvageButtons[1]);hover(ContainerFrame1Item1)
assert(cursor==PICK,"armed again")
ContainerFrame1Item1.scripts.OnClick(ContainerFrame1Item1,"LeftButton")
H.Target(nil,{nonce=aio[#aio][5],item={guid=400,entry=3,rarity="legendary",managed=true,name="Legend",bag=0,slot=1}})
assert(popup,"the confirmation is up")
U.frame:Hide()
assert(popup==nil and cursor==nil,"closing the window cancels the confirmation")
-- entering combat ends the arm too
H.Show(nil,m);click(U.tabs[3]);click(U.salvageButtons[1]);hover(ContainerFrame1Item1)
assert(cursor==PICK,"armed again")
combat=true;U.watcher.scripts.OnEvent(U.watcher,"PLAYER_REGEN_DISABLED");combat=false
assert(cursor==nil,"combat gives the glove")
U.frame:Hide()                                  -- the ElvUI section below reopens it
-- The ElvUI path (the designer's): its slot's CAPTURED handler resets on every tooltip refresh, and the
-- template's OnLeave resets when the tooltip covers the cursor. Not one drawn frame may be the glove.
local drawn,gloves={},0
local function drawFrame()
    drawn[#drawn+1]=cursor
    if cursor==nil then gloves=gloves+1 end
end
H.Show(nil,m);click(U.tabs[3])                  -- the window was closed above; reopen on Salvage
click(U.salvageButtons[1])                      -- arm
hover(elvuiBag)
drawFrame()
assert(cursor==PICK,"hovering an ElvUI bag slot while armed shows the hammer")
tooltipTick()
drawFrame()
assert(cursor==PICK,"ElvUI's captured refresh handler must not drop the hammer")
tooltipTick()
drawFrame()
assert(gloves==0,"no drawn frame is the glove while the pick waits")
-- the tooltip covering the cursor fires the template's OnLeave while the mouse has not moved
fire(elvuiBag,"OnLeave")
drawFrame()
assert(cursor==PICK and gloves==0,"the template's OnLeave must not drop the hammer over the slot")
fire(elvuiBag,"OnEnter")
drawFrame()
assert(gloves==0,"still no glove frame")
unhover(elvuiBag)
assert(cursor==nil,"leaving the ElvUI slot resets the cursor")
-- Return 3: ResetCursor is hooked globally, so a hover that is stale (its surface hidden, or the
-- mouse gone without an OnLeave - 3.3.5 cannot be relied on to fire one) must drop the hammer and
-- let the glove come back. The Repair tab's wait lasts as long as the tab is open, so this matters.
hover(elvuiBag)
assert(cursor==PICK,"armed again on the ElvUI slot")
elvuiBag:Hide()
ResetCursor()
assert(cursor==nil,"a hidden hovered slot must not pin the hammer")
H.Show(nil,m);click(U.tabs[4])
hover(ContainerFrame1Item1)
assert(cursor==PICK,"the Repair tab's single-item mode shows the hammer")
mouseOver=nil                                   -- onto the world: no OnLeave fires
ResetCursor()
assert(cursor==nil,"a hover the mouse has left must not pin the hammer")
-- ...and onto other UI, where the client DOES honour a cursor call: a stale hover would paint the
-- hammer over someone else's frame.
SomeOtherAddonFrame=CreateFrame("Frame","SomeOtherAddonFrame")
mouseOver=SomeOtherAddonFrame
ResetCursor()
assert(cursor==nil,"a stale hover must not paint the hammer over another frame")
H.Show(nil,m);click(U.tabs[3]);click(U.salvageButtons[1])
hover(ContainerFrame1Item1)
assert(cursor==PICK)
U.frame:Hide()
ResetCursor()
assert(cursor==nil,"a hidden window must not pin the hammer")
U.frame:Hide()                                  -- the late-refresh check below needs it closed
-- and the model bites: a call from no hovered frame changes nothing, exactly as the client
mouseOver=nil
SetCursor(PICK)
assert(cursor==nil,"a cursor call from no hovered frame changes nothing")
local refreshed={};for k,v in pairs(m) do refreshed[k]=v end;refreshed.refresh=true
H.Show(nil,refreshed);assert(not U.frame:IsShown(),"late refresh must not reopen closed window")
print("Blacksmith window: filters, exact money, batch bar, cancellation, inventory clicks, confirmation, repair, the recipe preview hover and the salvage pick cursor (SetCursor from a hover handler) passed")
