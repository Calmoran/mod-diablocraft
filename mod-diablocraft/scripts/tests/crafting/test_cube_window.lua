-- luacheck: globals DCUI UISpecialFrames AIO UnitName GetRealmName SendAddonMessage GetItemIcon GetItemInfo GetTime
-- luacheck: globals GetCursorInfo ClearCursor PickupContainerItem PickupInventoryItem DCCube Diablocraft UIErrorsFrame
-- luacheck: globals DCThrottle DCRange CharDBQuery WorldDBQuery GameTooltip ElvUI BuffFrame BuffFrame_Update BUFF_ACTUAL_DISPLAY
-- luacheck: globals BUFFS_PER_ROW BUFF_ROW_SPACING ConsolidatedBuffs TemporaryEnchantFrame TempEnchant1
-- luacheck: globals BuffFrame_UpdateAllBuffAnchors DebuffButton_UpdateAnchors UIParent
-- luacheck: ignore 111 113 121 122 311
-- Run from the repo root: lua mod-diablocraft/scripts/tests/crafting/test_cube_window.lua
--
-- dc_cube.lua (diablocraft-wpt7l.5, rebuilt to D3's three windows by diablocraft-4yc2d) against the strict 3.3.5a
-- widget mock, on the records of docs/contracts/cube-messages.md (DCCUBE). What it pins:
--   * nothing is sent or opened at load; R|open opens the Cube window, with no panel, and starts the server's reach watch;
--   * the power slots are the S records: the chosen power's name under its icon, the slot's label greyed when empty;
--   * the book opens the Recipes panel: one recipe a page in the server's order, its P (subtitle, item x1, red note),
--     each T as name xN (short ones red, with what the ledger holds), the item rules' "consumed" line, its Q; Page N/M
--     and the arrows' ends;
--   * Fill sends the page's recipe id; G puts its cells in the grid (icon and count), replacing the reagents there;
--   * a dragged item goes to the server half by bag and slot, into the grid's first cell; unidentified and plain items
--     are refused with the server's texts; a click with nothing held takes out the item or that reagent cell;
--   * Transmute is off with no reagents; it sends `transmute<TAB>guid<TAB>entry_amount...` (guid 0 for no item) once;
--     the reply empties the reagents, takes the item out when R counts it removed, and replaces only its recipe;
--     a lost reply frees it after the timeout;
--   * a power slot opens the Collection in place of Recipes: `powers<TAB>slot<TAB>page`, L's Page N/M, W's powers (lit
--     for state 1, greyed for 0 and 2, over several W), the chosen one outlined, the arrows ask the next page;
--   * hover asks `power` once per power and the U pieces fill the tooltip; a lit power is chosen with `choose`, a greyed
--     one sends nothing; the choose reply's S changes the slot;
--   * X stays with its text; "Stand next to Kanai's Cube." and the watcher's Close close it; a reopen starts clean;
--   * the server half maps the client's bag numbering and bounds it, and its reach is the core's box corner;
--   * the prefix, verbs, records and texts are the contract's own words;
--   * the buff row (diablocraft-ilymy): `buffs` asked at load, at PLAYER_ENTERING_WORLD and after a choose reply; one
--     icon per slot that holds a power, after ElvUI's shown buffs on its grid (its size, spacing, wrap, ElvUI's own
--     CreateIcon, no cancel click) and after the stock buffs by BuffFrame_UpdateAllBuffAnchors' steps (consolidated and
--     enchant slack, a new row under the row above, the debuffs a row lower); the tooltip is the icon, name and line; an
--     empty reply hides them;
--   * Caldesann's Despair (diablocraft-szwma): each K is a page row "Legendary Gem x1" / "<tier> Gem x3" whose slot shows
--     the grid's gem of that class; a dragged bag gem goes in as a cell (the server half names its class and stack), as
--     many of the stack as the recipes take less what the grid holds; Transmute sends it as `i<guid>_<count>`; the
--     augment's reply keeps the item (no D names it) and empties the gems.
-- What this does NOT cover: the server's rules (test_cube.py, test_cube_grid.py), the real ElvUI and FrameXML (stand-ins
-- of their names and fields here) and the look (the designer's check on dev).
local SOURCE=os.getenv("DC_CUBE_LUA") or "mod-diablocraft/lua/aio/dc_cube.lua"

local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local sent,handled,now,cursor={},{},100,nil
function UnitName() return "Tester" end
function GetRealmName() return "Torment" end
function GetItemIcon(entry) return "icon:"..entry end
function GetItemInfo() return nil end
function GetTime() return now end
function GetCursorInfo() return cursor end
function ClearCursor() cursor=nil end
function PickupContainerItem() end
function PickupInventoryItem() end
function SendAddonMessage(prefix,body,distribution,target)
    sent[#sent+1]={prefix=prefix,body=body,distribution=distribution,target=target}
end
local clientHandlers
AIO={AddAddon=function() return false end,AddHandlers=function(_,t) clientHandlers=t;return t end,
    Handle=function(...) handled[#handled+1]=table.concat({...},",") end}
Diablocraft={Econ={Gold=tostring,CURRENCIES={{entry=102001,name="Reusable Parts"},{entry=102002,name="Arcane Dust"},
    {entry=102003,name="Veiled Crystal"},{entry=102000,name="Death's Breath"},{entry=102004,name="Forgotten Soul"}}}}
dofile("mod-diablocraft/lua/aio/dc_aio_ui.lua")
-- ElvUI's Auras module (ElvUI-WotLK 6.09 Modules/Auras/Auras.lua) and the stock buff row (FrameXML/BuffFrame.lua), by
-- the names and fields the file reads: UpdateHeader calls ConfigureAuras, which shows `elvShown` buttons; BuffFrame_Update
-- lays out the buffs, then anchors each debuff.
local elvShown=3
local Auras={db={buffs={growthDirection="RIGHT_UP",size=32,horizontalSpacing=6,verticalSpacing=16,wrapAfter=4}}}
Auras.BuffFrame=CreateFrame("Frame","ElvUIPlayerBuffs",UIParent)
local elvButtons={}
for i=1,5 do elvButtons[i]=CreateFrame("Button","ElvUIPlayerBuffsAuraButton"..i,Auras.BuffFrame) end
function Auras.ConfigureAuras(_,header) for i,b in ipairs(elvButtons) do b.shown=header and i<=elvShown end end
function Auras:UpdateHeader(header) self:ConfigureAuras(header,{}) end
function Auras.CreateIcon(_,b) b.texture=b:CreateTexture();b.skinned=true;b:SetScript("OnClick",function() end) end
function Auras.ClearAuraTime(_,b) b.noTime=true end
ElvUI={{GetModule=function(_,name,silent) assert(silent);return name=="Auras" and Auras or nil end}}
BuffFrame=CreateFrame("Frame","BuffFrame",UIParent);BuffFrame.numEnchants,BuffFrame.numConsolidated=0,0
ConsolidatedBuffs=CreateFrame("Button","ConsolidatedBuffs",UIParent)
TemporaryEnchantFrame=CreateFrame("Frame","TemporaryEnchantFrame",UIParent)
TempEnchant1=CreateFrame("Button","TempEnchant1",TemporaryEnchantFrame);TempEnchant1:SetSize(30,30)
BUFF_ACTUAL_DISPLAY,BUFFS_PER_ROW,BUFF_ROW_SPACING=0,8,5
local debuffs=0
local DebuffButton1=CreateFrame("Button","DebuffButton1",BuffFrame)
function BuffFrame_UpdateAllBuffAnchors() end
function DebuffButton_UpdateAnchors(_,index) if index==1 then DebuffButton1:SetPoint("TOPRIGHT",ConsolidatedBuffs,"BOTTOMRIGHT",0,-35) end end
function BuffFrame_Update()
    BuffFrame_UpdateAllBuffAnchors()
    for i=1,debuffs do DebuffButton_UpdateAnchors("DebuffButton",i) end
end
dofile(SOURCE)

local K=DCCube
local ui=K.ui
local function chat(body,sender,prefix) K.OnMessage(prefix or "DCCUBE",body,"WHISPER",sender or "Tester") end
local function reply(verb,records,count)
    chat("R|"..verb.."|"..(count or 0));for _,r in ipairs(records) do chat(r) end;chat("E|"..verb)
end
local function bodies() local out={};for i,s in ipairs(sent) do out[i]=s.body end;return table.concat(out," / ") end
local function click(b) assert(b:IsEnabled(),"the button is clickable");b.scripts.OnClick(b) end
local function settle(seconds) now=now+seconds;ui.watcher.scripts.OnUpdate(ui.watcher,seconds) end
local function lastSay() return UIErrorsFrame.lines[#UIErrorsFrame.lines] end
local function colour(fs,rgb) local r,g,b=fs:GetTextColor();return r==rgb[1] and g==rgb[2] and b==rgb[3] end
local function hover(b) b.scripts.OnEnter(b);return GameTooltip.lines end
local function drag(cell,bag,slot,item)
    PickupContainerItem(bag,slot);cursor="item"
    cell.scripts.OnReceiveDrag(cell)
    if item then clientHandlers.Item(nil,item) end
end

-- The contract's own words.
local file=assert(io.open("docs/contracts/cube-messages.md"))
local contract=file:read("*a");file:close()
for _,needle in ipairs({'SendAddonMessage("DCCUBE"',"| `fill` | recipe id","| `transmute` | item guid (`0` when the grid holds no item",
    "| `powers` | slot (1..), page (1..)","| `power` | a power's item entry (1..)","| `choose` | slot (1..), a power's item entry",
    "one field, `entry_amount`","`R\\|verb\\|n`","`C\\|recipe\\|rule\\|name`","`P\\|recipe\\|subtitle\\|item\\|note`",
    "`Q\\|recipe\\|quote\\|source`","`T\\|recipe\\|entry\\|need\\|have\\|ok`","`S\\|slot\\|label\\|entry\\|name`",
    "`G\\|recipe\\|entry:amount\\|...`","`L\\|slot\\|page\\|pages\\|total`","`W\\|slot\\|entry:state:name\\|...`",
    "`U\\|entry\\|name\\|n\\|text`","`E\\|verb`","under the verb `open`","three columns by six rows",
    "`set_convert`, `rare_upgrade`, `reforge`, `primal_upgrade` and `extract` are the item rules","the window says the item is consumed",
    "`"..K.Logic.NOT_NEAR.."`","`Identify it first.`","`Choose a rolled item.`","`Not enough materials for that recipe.`",
    "`You have not extracted that power.`","`Your class cannot use that power.`"}) do
    assert(contract:find(needle,1,true),"the contract says "..needle)
end
assert(io.open(SOURCE):read("*a"):find('local PREFIX="DCCUBE"',1,true),"the prefix is the contract's")
-- The window's consumed line is drawn for exactly the contract's item rules.
local itemRules={}
for rule in contract:match("([^.:]*) are the item rules"):gmatch("`([%w_]+)`") do
    itemRules[rule]=true
    assert(K.Logic.CONSUMES[rule],"the window says the item is consumed for "..rule)
end
for rule in pairs(K.Logic.CONSUMES) do assert(itemRules[rule],rule.." is one of the contract's item rules") end

local LIST={
    "C|iben_regret|convert|Regret of Iben Fahd","P|iben_regret|Convert Arcane Dust to Item's Material|Normal, Magic or Rare Item|",
    "T|iben_regret|102002|100|40|0","T|iben_regret|102000|1|5|1",
    "Y|iben_regret|normal|102001|100","Y|iben_regret|magic|102002|100",
    "C|law_of_kulle|reforge|Law of Kulle","P|law_of_kulle|Reforge Legendary|Legendary or Set Item|",
    "Q|law_of_kulle|For weeks the fires burned.|fragment of the Dark Exile Scrolls.","T|law_of_kulle|102004|50|60|1",
    "C|skill_of_nilfur|set_convert|Skill of Nilfur",
    "P|skill_of_nilfur|Convert Set Item|Set Item|Resulting item cannot be Ancient.","T|skill_of_nilfur|102004|10|60|1",
    "S|1|Weapon|0|","S|2|Armor|60500|Leoric's Crown","S|3|Jewelry|0|"}
local MAGIC={guid=4242,entry=60001,name="Gleaming Sword",rarity="magic"}

-- 1. Load asks for the buff row (AIO may load the file after PLAYER_ENTERING_WORLD) and opens nothing.
assert(#sent==1 and sent[1].body=="buffs" and #handled==0 and not ui.frame:IsShown(),"only `buffs` at load, got "..bodies())
sent={}

-- 2. Another prefix or sender is dropped.
chat("R|open|3","Somebody");chat("R|open|3","Tester","DCURSHI")
assert(not ui.frame:IsShown() and #handled==0,"an R from elsewhere opens nothing")

-- 3. R|open opens the Cube window alone and starts the watch; the power slots are the S records.
reply("open",LIST,3)
assert(ui.frame:IsShown() and not ui.recipes:IsShown() and not ui.collection:IsShown(),"the Cube window, no panel")
assert(handled[1]=="DiablocraftCube,Opened","the server half is told, to watch the reach")
local special=false
for _,name in ipairs(UISpecialFrames) do special=special or name=="TormentCubeFrame" end
assert(special,"Esc closes the window")
assert(#ui.powerSlots==3,"one power slot per S")
assert(ui.powerSlots[1].label:GetText()=="Weapon" and colour(ui.powerSlots[1].label,DCUI.GREY)
    and ui.powerSlots[1].icon:GetTexture()==nil,"an empty slot: its label, greyed")
assert(ui.powerSlots[2].label:GetText()=="Leoric's Crown" and colour(ui.powerSlots[2].label,DCUI.WHITE)
    and ui.powerSlots[2].icon:GetTexture()=="icon:60500","a chosen power: its icon, its name under it")
assert(ui.powerSlots[3].label:GetText()=="Jewelry","the third slot")
assert(not ui.transmute:IsEnabled(),"no reagents: Transmute off")
for i=1,9 do assert(ui.grid[i].icon:GetTexture()==nil,"the grid starts empty") end

-- 4. The book: the Recipes panel, one recipe a page, in the server's order.
click(ui.book)
assert(ui.recipes:IsShown() and not ui.collection:IsShown(),"the book opens Recipes")
assert(ui.recipeName:GetText()=="Regret of Iben Fahd" and ui.recipeSubtitle:GetText()=="Convert Arcane Dust to Item's Material","page 1's head")
assert(ui.pageText:GetText()=="Page 1/3" and not ui.prevPage:IsEnabled() and ui.nextPage:IsEnabled(),"page 1 of 3")
assert(ui.itemRow:IsShown() and ui.itemRow.label:GetText()=="Normal, Magic or Rare Item x1","the item line x1")
local r1,r2=ui.reagentRows[1],ui.reagentRows[2]
assert(r1.label:GetText()=="Arcane Dust x100 (you have 40)" and colour(r1.label,DCUI.RED) and r1.icon:GetTexture()=="icon:102002",
    "a short reagent is marked, got "..r1.label:GetText())
assert(r2.label:GetText()=="Death's Breath x1" and colour(r2.label,DCUI.WHITE),"an enough reagent")
assert(not ui.note:IsShown() and not ui.quote:IsShown() and not ui.consumed:IsShown(),"a convert page: no note, quote, consumed")
click(ui.nextPage)
assert(ui.recipeName:GetText()=="Law of Kulle" and ui.pageText:GetText()=="Page 2/3","page 2")
assert(ui.reagentRows[1].label:GetText()=="Forgotten Soul x50" and ui.reagentRows[1]:IsShown() and not r2:IsShown(),"one reagent")
assert(ui.quote:IsShown() and ui.quote:GetText()=='"For weeks the fires burned."',"the quote")
assert(ui.source:GetText()=="\226\128\148fragment of the Dark Exile Scrolls.","the source")
assert(ui.consumed:IsShown() and ui.consumed:GetText()=="The item is consumed.","an item rule says the item is consumed")
click(ui.nextPage)
assert(ui.recipeName:GetText()=="Skill of Nilfur" and not ui.nextPage:IsEnabled(),"the last page")
assert(ui.note:IsShown() and ui.note:GetText()=="Resulting item cannot be Ancient." and colour(ui.note,DCUI.RED),"the red note")
assert(not ui.quote:IsShown() and not ui.source:IsShown(),"no quote on this page")
click(ui.book)
assert(not ui.recipes:IsShown(),"the book closes it again")
click(ui.book)
assert(ui.recipeName:GetText()=="Skill of Nilfur","the page is kept")
click(ui.prevPage);click(ui.prevPage)

-- 5. Fill: the page's recipe id; G puts its cells in the grid; a refusal stays as text.
sent={}
click(ui.fill)
assert(#sent==1 and sent[1].body=="fill\tiben_regret" and sent[1].prefix=="DCCUBE" and sent[1].target=="Tester",
    "Fill sends the page's recipe, got "..bodies())
chat("X|Not enough materials for that recipe.")
assert(ui.reason:GetText()=="Not enough materials for that recipe." and ui.frame:IsShown(),"the refusal stays")
reply("fill",{"G|iben_regret|102002:100|102000:1"},2)
assert(ui.grid[1].icon:GetTexture()==nil,"the item's cell stays empty")
assert(ui.grid[2].icon:GetTexture()=="icon:102002" and ui.grid[2].count:GetText()=="100","the first reagent cell")
assert(ui.grid[3].icon:GetTexture()=="icon:102000" and ui.grid[3].count:GetText()=="1","the second reagent cell")
assert(ui.grid[4].icon:GetTexture()==nil,"no third cell")
assert(ui.transmute:IsEnabled(),"reagents in the grid: Transmute on")
assert(hover(ui.grid[2])[1]=="Arcane Dust x100","a reagent cell's tooltip")

-- 6. The item: the server half is asked by bag and slot; refusals keep the cell empty.
handled={}
drag(ui.grid[5],0,3)
assert(handled[1]=="DiablocraftCube,Item,0,3" and cursor==nil,"a backpack drag asks bag 0 slot 3, the cursor is cleared")
PickupInventoryItem(16);cursor="item";ui.grid[1].scripts.OnClick(ui.grid[1],"LeftButton")
assert(handled[2]=="DiablocraftCube,Item,255,15","a worn item (sheet slot 16) is bag 255 slot 15")
cursor="spell";ui.grid[1].scripts.OnReceiveDrag(ui.grid[1])
assert(#handled==2,"a held spell is not an item")
clientHandlers.Item(nil,{guid=1,entry=2,name="Shell",unidentified=true})
assert(lastSay()=="Identify it first." and ui.grid[1].icon:GetTexture()==nil,"an unidentified item is refused")
clientHandlers.Item(nil,{guid=1,entry=2,name="Linen Cloth"})
assert(lastSay()=="Choose a rolled item." and ui.grid[1].icon:GetTexture()==nil,"a plain item is refused")
clientHandlers.Item(nil,MAGIC)
assert(ui.grid[1].icon:GetTexture()=="icon:60001","a rolled item goes in the first cell")
assert(ui.grid[2].count:GetText()=="100","the reagents stay")

-- 7. Transmute: the whole grid, once; a convert's reply keeps the item, empties the reagents, replaces its recipe.
sent={}
click(ui.transmute)
assert(#sent==1 and sent[1].body=="transmute\t4242\t102002_100\t102000_1" and sent[1].distribution=="WHISPER",
    "Transmute sends the guid and the cells, got "..bodies())
assert(not ui.transmute:IsEnabled(),"locked while out")
K.Transmute()
assert(#sent==1,"no second send before the answer")
chat("R|transmute|0");chat("M|102002|0");chat("C|iben_regret|convert|Regret of Iben Fahd")
chat("P|iben_regret|Convert Arcane Dust to Item's Material|Normal, Magic or Rare Item|")
chat("T|iben_regret|102002|100|0|0");chat("T|iben_regret|102000|1|4|1")
assert(ui.grid[2].count:GetText()=="100","nothing changes before E")
chat("E|transmute")
assert(ui.grid[2].icon:GetTexture()==nil and ui.grid[1].icon:GetTexture()=="icon:60001","reagents spent, the item stays (0 removed)")
assert(ui.reagentRows[1].label:GetText()=="Arcane Dust x100 (you have 0)","the recipe's new balances")
assert(not ui.transmute:IsEnabled(),"no reagents left: off")
click(ui.nextPage)
assert(ui.recipeName:GetText()=="Law of Kulle" and ui.reagentRows[1].label:GetText()=="Forgotten Soul x50","the others are kept")

-- 8. An item recipe's reply takes the item out (R counts it removed).
reply("fill",{"G|law_of_kulle|102004:50"},1)
sent={}
click(ui.transmute)
assert(sent[1].body=="transmute\t4242\t102004_50","the item and the cell")
reply("transmute",{"D|4242","C|law_of_kulle|reforge|Law of Kulle","T|law_of_kulle|102004|50|10|0"},1)
assert(ui.grid[1].icon:GetTexture()==nil and ui.grid[2].icon:GetTexture()==nil,"the item and the reagents are gone")

-- 9. No item: guid 0. A lost reply frees Transmute after the timeout.
reply("fill",{"G|law_of_kulle|102004:50"},1)
sent={}
click(ui.transmute)
assert(sent[1].body=="transmute\t0\t102004_50","no item: guid 0, got "..bodies())
settle(K.Logic.TIMEOUT-1)
assert(not ui.transmute:IsEnabled(),"not before the timeout")
settle(1)
assert(ui.transmute:IsEnabled(),"after the timeout")

-- 10. X answers a transmute and stays with its text.
click(ui.transmute)
chat("X|Put an item in the Cube.")
assert(ui.frame:IsShown() and ui.reason:GetText()=="Put an item in the Cube." and ui.transmute:IsEnabled(),"X stays, frees it")

-- 11. A click with nothing held takes out a reagent cell or the item; G replaces the reagents.
reply("fill",{"G|iben_regret|102002:100|102000:1"},2)
assert(ui.grid[2].icon:GetTexture()=="icon:102002" and ui.grid[4].icon:GetTexture()==nil,"Fill replaces the reagents")
cursor=nil;ui.grid[2].scripts.OnClick(ui.grid[2],"LeftButton")
assert(ui.grid[2].icon:GetTexture()=="icon:102000" and ui.grid[3].icon:GetTexture()==nil,"one reagent cell taken out")
clientHandlers.Item(nil,MAGIC)
ui.grid[1].scripts.OnClick(ui.grid[1],"RightButton")
assert(ui.grid[1].icon:GetTexture()==nil and ui.grid[2].icon:GetTexture()=="icon:102000","the item is out, the reagent stays")

-- 12. A power slot opens the Collection in place of Recipes.
sent={}
ui.powerSlots[1].scripts.OnClick(ui.powerSlots[1])
assert(sent[1].body=="powers\t1\t1","the slot's first page, got "..bodies())
assert(ui.collection:IsShown() and not ui.recipes:IsShown(),"the Collection replaces Recipes")
assert(ui.slotHead:GetText()=="Weapon","the slot's label")
local W={}
for i=1,18 do W[#W+1]=(70000+i)..":"..(i==2 and 0 or i==3 and 2 or 1)..":Power "..i end
reply("powers",{"L|1|1|5|84","W|1|"..table.concat(W,"|",1,9),"W|1|"..table.concat(W,"|",10,18)},18)
local cells=ui.powerCells
local shownCells=0
for _,b in ipairs(cells) do if b:IsShown() then shownCells=shownCells+1 end end
assert(shownCells==18,"18 powers over two W records")
assert(cells[1].label:GetText()=="Power 1" and colour(cells[1].label,DCUI.GOLD) and not cells[1].icon.desaturated,"extracted: lit")
assert(colour(cells[2].label,DCUI.GREY) and cells[2].icon.desaturated,"not extracted: greyed")
assert(colour(cells[3].label,DCUI.GREY) and cells[3].icon.desaturated,"extracted but not this class: greyed")
assert(ui.shelfText:GetText()=="Page 1/5" and not ui.prevShelf:IsEnabled() and ui.nextShelf:IsEnabled(),"page 1 of 5")
sent={}
click(ui.nextShelf)
assert(sent[1].body=="powers\t1\t2","the next page, got "..bodies())
reply("powers",{"L|2|1|1|3","W|2|1:1:Elsewhere"},1)
assert(cells[1].label:GetText()=="Power 1","a page for another slot is not drawn")
reply("powers",{"L|1|5|5|84","W|1|71000:1:Last One"},1)
assert(cells[1].label:GetText()=="Last One" and not cells[2]:IsShown(),"the last page")
assert(ui.shelfText:GetText()=="Page 5/5" and not ui.nextShelf:IsEnabled() and ui.prevShelf:IsEnabled(),"its arrows")
reply("powers",{"L|1|1|5|84","W|1|"..table.concat(W,"|",1,9),"W|1|"..table.concat(W,"|",10,18)},18)

-- 13. Hover asks a power's line once; the U pieces fill the tooltip.
sent={}
local tip=hover(cells[1])
assert(tip[1]=="Power 1" and #tip==1,"the name first")
assert(sent[1].body=="power\t70001","its line is asked for, got "..bodies())
hover(cells[1])
assert(#sent==1,"not again while it is out")
reply("power",{"U|70001|Power 1|1|Fist of the Heavens casts ","U|70001|Power 1|2|twice."},2)
assert(GameTooltip.lines[2]=="Fist of the Heavens casts twice.","the pieces joined, the tooltip refreshed")
hover(cells[1])
assert(#sent==1 and GameTooltip.lines[2]=="Fist of the Heavens casts twice.","kept: no second ask")
tip=hover(cells[2])
assert(tip[2]=="You have not extracted that power.","a greyed power says why")
assert(hover(cells[3])[2]=="Your class cannot use that power.","state 2 says why")
reply("power",{"U|70003|Power 3|1|half"},2)
sent={}
hover(cells[3])
assert(#sent==0 and #GameTooltip.lines==2,"a line missing a piece is not kept")
settle(K.Logic.TIMEOUT)
hover(cells[3])
assert(sent[1] and sent[1].body=="power\t70003","asked again after the timeout")

-- 14. Choosing: a lit power sends choose; a greyed one nothing; S changes the slot, outlined in the Collection.
sent={}
cells[2].scripts.OnClick(cells[2]);cells[3].scripts.OnClick(cells[3])
assert(#sent==0,"greyed powers cannot be chosen")
cells[1].scripts.OnClick(cells[1])
assert(sent[1].body=="choose\t1\t70001","choose the slot and the entry, got "..bodies())
reply("choose",{"S|1|Weapon|70001|Power 1"},1)
assert(sent[#sent].body=="buffs","a choose reply asks for the buff row again")
assert(ui.powerSlots[1].label:GetText()=="Power 1" and ui.powerSlots[1].icon:GetTexture()=="icon:70001","the slot holds it")
local br,bg,bb=cells[1]:GetBackdropBorderColor()
assert(br==DCUI.BOX_ACTIVE[1] and bg==DCUI.BOX_ACTIVE[2] and bb==DCUI.BOX_ACTIVE[3],"the chosen power is outlined")
br=cells[4]:GetBackdropBorderColor()
assert(br==DCUI.SLOT_BORDER[1],"the others are not")
sent={}
hover(ui.powerSlots[1])
assert(GameTooltip.lines[1]=="Power 1" and GameTooltip.lines[2]=="Fist of the Heavens casts twice." and #sent==0,
    "the slot's tooltip: the name, then the kept line")
assert(hover(ui.powerSlots[3])[1]=="Jewelry" and #sent==0,"an empty slot's tooltip is its label")

-- 15. The book from the Collection goes to Recipes; the panel's close button closes it.
click(ui.book)
assert(ui.recipes:IsShown() and not ui.collection:IsShown(),"the book swaps the panel")
ui.recipes.closeButton.scripts.OnClick(ui.recipes.closeButton)
assert(not ui.recipes:IsShown() and ui.frame:IsShown(),"the panel closes, the Cube stays")

-- 16. A Cube click while up keeps the grid; a reopen starts clean.
reply("fill",{"G|iben_regret|102002:100"},1)
click(ui.book)
reply("open",LIST,3)
assert(ui.grid[2].icon:GetTexture()=="icon:102002" and ui.recipes:IsShown() and ui.pageText:GetText()=="Page 2/3",
    "the grid, the panel and the page are kept while up")
ui.frame:Hide()
reply("open",LIST,3)
assert(ui.grid[2].icon:GetTexture()==nil and not ui.recipes:IsShown() and not ui.collection:IsShown(),"reopened clean")
click(ui.book)
assert(ui.pageText:GetText()=="Page 1/3","back on page 1")

-- 17. Malformed records are dropped.
reply("list",{"C||convert|NoId","C|a|convert|A","P|zz|x|y|z","T|a|x|1|1|1","T|zz|102000|1|1|1","T|a|102000|1|1",
    "S|x|Weapon|0|","S|1|Weapon|y|"})
assert(ui.pageText:GetText()=="Page 1/1" and not ui.reagentRows[1]:IsShown() and not ui.itemRow:IsShown()
    and #ui.powerSlots==3 and not ui.powerSlots[1]:IsShown(),"malformed rows are dropped")
reply("fill",{"G|a|x:1|102000:|102000:2"},1)
assert(ui.grid[2].icon:GetTexture()=="icon:102000" and ui.grid[3].icon:GetTexture()==nil,"malformed cells are dropped")

-- 18. Out of reach closes; the watcher's Close closes; X on the click's push keeps it shut.
reply("open",LIST,3)
chat("X|"..K.Logic.NOT_NEAR)
assert(not ui.frame:IsShown() and lastSay()==K.Logic.NOT_NEAR,"out of reach closes")
reply("open",LIST,3)
clientHandlers.Close()
assert(not ui.frame:IsShown(),"the watcher's Close closes")
chat("X|Finish combat or trading before using an artisan.")
assert(not ui.frame:IsShown() and lastSay()=="Finish combat or trading before using an artisan.","a refused click stays shut")

------------------------------------------------------------------------------------------------
-- The server half
------------------------------------------------------------------------------------------------
local serverHandlers,asked,watched,allowed={},{},nil,true
AIO={AddAddon=function() return true end,AddHandlers=function() return serverHandlers end,
    Handle=function(_,channel,name,payload) handled[#handled+1]={channel=channel,name=name,payload=payload} end}
DCThrottle={Allow=function() return allowed end}
DCRange={Watch=function(_,channel,gate,close) watched={channel=channel,gate=gate,close=close} end}
function CharDBQuery(sql)
    if sql:find("dc_item_instance") and sql:find("=77$") then return {GetString=function() return "rare" end} end
    if sql:find("dc_item_unidentified") and sql:find("=78$") then return {} end
end
-- The gem tables the server's CubeGemClass reads: 60080 a legendary gem, 60081 a Flawless Royal one.
function WorldDBQuery(sql)
    if sql=="SELECT 1 FROM dc_legendary_gem_item WHERE entry=60080" then return {} end
    if sql=="SELECT tier FROM dc_gem_item WHERE entry=60081" then return {GetString=function() return "Flawless Royal" end} end
end
dofile(SOURCE)
local function item(guid) return {GetGUIDLow=function() return guid end,GetEntry=function() return 60000+guid end,
    GetName=function() return "Item "..guid end,GetCount=function() return guid==81 and 5 or 1 end} end
local player={GetItemByPos=function(_,bag,slot) asked[#asked+1]=bag..":"..slot;return item(77) end}
local function at(bag,slot) asked={};handled={};serverHandlers.Item(player,bag,slot);return asked[1] end

-- 19. The client's numbering maps to the server's, and nothing outside it is looked up.
assert(at(0,1)=="255:23" and at(0,16)=="255:38","the backpack")
assert(at(1,1)=="19:0" and at(4,36)=="22:35","the equipped bags")
assert(at(255,0)=="255:0" and at(255,18)=="255:18","worn")
for _,bad in ipairs({{0,0},{0,17},{5,1},{1,37},{255,19},{1.5,1},{0,"1"},{-1,1}}) do
    assert(at(bad[1],bad[2])==nil and #handled==0,"no lookup outside the bags: "..tostring(bad[1])..","..tostring(bad[2]))
end
at(0,1)
assert(handled[1].name=="Item" and handled[1].payload.guid==77 and handled[1].payload.rarity=="rare"
    and handled[1].payload.entry==60077 and handled[1].payload.name=="Item 77","a rolled item's guid and rarity")
player.GetItemByPos=function() return item(78) end
at(0,1)
assert(handled[1].payload.rarity==nil and handled[1].payload.unidentified==true,"an unidentified item")
player.GetItemByPos=function() return item(79) end
at(0,1)
assert(handled[1].payload.rarity==nil and not handled[1].payload.unidentified and handled[1].payload.gem==nil,"a plain item")
player.GetItemByPos=function() return item(80) end
at(0,1)
assert(handled[1].payload.gem=="legendary_gem" and handled[1].payload.count==1,"a legendary gem's class")
player.GetItemByPos=function() return item(81) end
at(1,3)
assert(handled[1].payload.gem=="Flawless Royal" and handled[1].payload.count==5 and handled[1].payload.guid==81,"a gem's tier and stack")
allowed=false
assert(at(0,1)==nil and #handled==0,"over the bucket: nothing")
allowed=true

-- 20. The reach: the farthest corner of the core's interaction box, at the Cube's scale.
serverHandlers.Opened(player)
assert(watched and watched.channel=="DiablocraftCube","Opened starts the watch on the window's channel")
local distance,scale=0,1.5
local cube={GetScale=function() return scale end}
player.GetNearestGameObject=function(_,range,entry) assert(entry==910047 and range>=14);return cube end
player.GetExactDistance=function() return distance end
distance=13.4;assert(watched.gate(player),"inside the corner at scale 1.5")
distance=13.5;assert(not watched.gate(player),"past the corner at scale 1.5")
scale=1;distance=12.6;assert(not watched.gate(player),"the scale is read off the Cube")
player.GetNearestGameObject=function() return nil end
assert(not watched.gate(player),"no Cube near: out of reach")
handled={};watched.close(player)
assert(handled[1].channel=="DiablocraftCube" and handled[1].name=="Close","out of reach sends Close")

-- 21. The buff row: PLAYER_ENTERING_WORLD asks; the reply's S and U make one icon per slot that holds a power.
sent={}
ui.watcher.scripts.OnEvent(ui.watcher,"PLAYER_ENTERING_WORLD")
assert(#sent==1 and sent[1].body=="buffs","PLAYER_ENTERING_WORLD asks for the buff row")
assert(contract:find("| `buffs` | none",1,true) and contract:find("Once at `PLAYER_ENTERING_WORLD`",1,true)
    and contract:find("it also asks once when it loads",1,true) and contract:find("after every `R|choose|` reply",1,true),"the buffs verb and its two asks are the contract's")
elvButtons[5].shown=false
reply("buffs",{"S|1|Weapon|70001|Power 1","U|70001|Power 1|1|Fist of the Heavens ","U|70001|Power 1|2|casts twice.",
    "S|3|Jewelry|70300|Ring of Power","U|70300|Ring of Power|1|Gain 50% damage."},2)
local elv1,elv2=_G.TormentCubeBuffElv1,_G.TormentCubeBuffElv2
assert(elv1 and elv2 and elv1:IsShown() and elv2:IsShown() and not _G.TormentCubeBuffElv3,"two powers, two ElvUI icons")
assert(elv1.parent==Auras.BuffFrame and elv1.skinned and elv1.noTime,"ElvUI's own buff button on its buff header, no time")
assert(elv1.texture:GetTexture()=="icon:70001" and elv2.texture:GetTexture()=="icon:70300","each power's item icon")
-- Three ElvUI buffs shown, four a row (RIGHT_UP: BOTTOMLEFT, x by size+horizontal, y by size+vertical): the 4th place,
-- then the next row.
-- The last anchor set: ElvUI's form is (point, header, x, y), the stock's (point, frame, relativePoint, x, y).
local function point(f) local p=f.points[#f.points];return p[1],p[2],p[3],p[4],p[5] end
local pt,rel,x,y=point(elv1)
assert(pt=="BOTTOMLEFT" and rel==Auras.BuffFrame and x==3*38 and y==0,"after the three buffs: "..tostring(x)..","..tostring(y))
pt,rel,x,y=point(elv2)
assert(pt=="BOTTOMLEFT" and x==0 and y==48,"wraps to the next row up: "..tostring(x)..","..tostring(y))
assert(elv1:GetWidth()==32 and elv1:GetHeight()==32,"ElvUI's buff size")
Auras.db.buffs.growthDirection="DOWN_LEFT";elvShown=1;Auras:UpdateHeader(Auras.BuffFrame)
pt,rel,x,y=point(elv1)
assert(pt=="TOPRIGHT" and x==0 and y==-48,"DOWN_LEFT grows down the column: "..tostring(x)..","..tostring(y))
Auras.db.buffs.growthDirection="RIGHT_UP";elvShown=3
assert(elv1.scripts.OnClick==nil,"no click: the power is not a buff to cancel")
local buffTip=hover(elv1)
assert(buffTip[1]=="|Ticon:70001:20|t Power 1" and buffTip[2]=="Fist of the Heavens casts twice." and #buffTip==2,
    "the icon, the name, then the line joined, got "..table.concat(buffTip," / "))
assert(GameTooltip.anchorType=="ANCHOR_BOTTOMLEFT","the buff's tooltip anchor")
assert(hover(elv2)[2]=="Gain 50% damage.","each icon its own line")

-- 22. The stock row: after the shown buffs, by BuffFrame_UpdateAllBuffAnchors' steps, the debuffs a row lower.
local s1,s2=_G.TormentCubeBuff1,_G.TormentCubeBuff2
assert(s1.parent==BuffFrame and s1:IsShown() and s2:IsShown() and s1:GetWidth()==30,"two stock icons, an aura button's size")
local to
pt,rel,to=point(s1)
assert(pt=="TOPRIGHT" and rel==BuffFrame and to=="TOPRIGHT","no buffs: the row's first place")
pt,rel=point(s2)
assert(pt=="RIGHT" and rel==s1,"then left of it")
BuffFrame.numEnchants=1;BuffFrame_Update()
pt,rel,to,x=point(s1)
assert(pt=="TOPRIGHT" and rel==TemporaryEnchantFrame and to=="TOPLEFT" and x==-5,"only an enchant: left of the enchants")
-- Eight buffs, one consolidated: the consolidated icon and the enchant take two places, seven buffs the rest; the
-- first icon is the 10th place, the second row's second.
BuffFrame.numEnchants,BuffFrame.numConsolidated,BUFF_ACTUAL_DISPLAY,debuffs=1,1,8,1
for i=1,8 do CreateFrame("Button","BuffButton"..i,BuffFrame).consolidated=(i==2) end
BuffFrame_Update()
pt,rel=point(s1)
assert(pt=="RIGHT" and rel==_G.BuffButton8,"the 10th place is left of the last unconsolidated buff, got "..tostring(rel and rel.name))
BuffFrame.numEnchants=0;BuffFrame_Update()
pt,rel,to,x,y=point(s1)
assert(pt=="TOP" and rel==ConsolidatedBuffs and to=="BOTTOM" and y==-5,"the 9th place starts the second row under the consolidated icon")
pt,rel=point(s2)
assert(pt=="RIGHT" and rel==s1,"the next one left of it")
pt,rel,to,x,y=point(DebuffButton1)
assert(rel==ConsolidatedBuffs and y==-70,"two rows of buffs: the debuffs two rows down, got "..tostring(y))

-- 23. An empty reply (every slot empty) hides them; nothing else changes them.
reply("buffs",{},0)
assert(not elv1:IsShown() and not elv2:IsShown() and not s1:IsShown() and not s2:IsShown(),"no power, no icon")
pt,rel,to,x,y=point(DebuffButton1)
assert(y==-35,"the debuffs where the stock row put them")

-- 24. Caldesann's Despair: the K rows, the bag gems in the grid, the augment's reply.
reply("open",{"C|caldesanns_despair|augment|Caldesann's Despair",
    "P|caldesanns_despair|Augment Ancient Item|Ancient Legendary Item|","K|caldesanns_despair|legendary_gem|1",
    "K|caldesanns_despair|Flawless Royal|3","S|1|Weapon|0|"},1)
click(ui.book)
local g1,g2=ui.reagentRows[1],ui.reagentRows[2]
assert(g1:IsShown() and g1.label:GetText()=="Legendary Gem x1" and g1.icon:GetTexture()==nil,"a legendary gem row, empty")
assert(g2:IsShown() and g2.label:GetText()=="Flawless Royal Gem x3" and not (ui.reagentRows[3] and ui.reagentRows[3]:IsShown()),"the tier's row")
assert(not ui.consumed:IsShown(),"the augment's item stays: no consumed line")
clientHandlers.Item(nil,{guid=5000,entry=60001,name="Ancient Sword",rarity="legendary"})
clientHandlers.Item(nil,{guid=6001,entry=70500,name="Bane of the Trapped",gem="legendary_gem",count=1})
local ruby={guid=6003,entry=70600,name="Flawless Royal Ruby",gem="Flawless Royal",count=2}
clientHandlers.Item(nil,ruby)
assert(ui.grid[1].icon:GetTexture()=="icon:60001","the item in its cell")
assert(ui.grid[2].icon:GetTexture()=="icon:70500" and ui.grid[2].count:GetText()=="1","the legendary gem a cell")
assert(ui.grid[3].icon:GetTexture()=="icon:70600" and ui.grid[3].count:GetText()=="2","a stack of two: both")
clientHandlers.Item(nil,ruby)
assert(ui.grid[3].count:GetText()=="2" and ui.grid[4].icon:GetTexture()==nil,"the same stack again replaces its cell")
assert(g1.icon:GetTexture()=="icon:70500" and g2.icon:GetTexture()=="icon:70600","each row shows its gem")
assert(hover(ui.grid[3])[1]=="Flawless Royal Ruby x2","the gem cell's tooltip")
clientHandlers.Item(nil,{guid=6002,entry=70600,name="Flawless Royal Ruby",gem="Flawless Royal",count=5})
assert(ui.grid[4].count:GetText()=="1","a stack of five: the one the recipe still takes")
clientHandlers.Item(nil,{guid=6005,entry=70600,name="Flawless Royal Ruby",gem="Flawless Royal",count=1})
assert(ui.grid[5].icon:GetTexture()==nil,"three held: no more")
clientHandlers.Item(nil,{guid=6004,entry=70700,name="Flawless Square Ruby",gem="Flawless Square",count=1})
assert(lastSay()=="Choose a rolled item." and ui.grid[5].icon:GetTexture()==nil,"a gem no recipe takes is refused as an item")
reply("fill",{"G|caldesanns_despair"},0)
assert(ui.grid[2].icon:GetTexture()=="icon:70500" and ui.grid[4].count:GetText()=="1","Fill with no reagents keeps the gems")
sent={}
click(ui.transmute)
assert(sent[1].body=="transmute\t5000\ti6001_1\ti6003_2\ti6002_1","the gems as iguid_count, got "..bodies())
assert(contract:find("`iguid_count`",1,true) and contract:find("`K\\|recipe\\|class\\|n`",1,true),"the contract's cell and record")
reply("transmute",{"D|6001","C|caldesanns_despair|augment|Caldesann's Despair","K|caldesanns_despair|legendary_gem|1",
    "K|caldesanns_despair|Flawless Royal|3"},1)
assert(ui.grid[1].icon:GetTexture()=="icon:60001","the augmented item stays though R counts a stack gone")
assert(ui.grid[2].icon:GetTexture()==nil and g1.icon:GetTexture()==nil and g1.label:GetText()=="Legendary Gem x1","the gems are spent")

print("PASS: Cube window: R|open, the grid and Fill, Transmute's grid, the power slots, the Recipes pages, the Collection, its tooltips and choice, X/Close, the server half's bags and reach, the buff row on ElvUI and the stock row, Caldesann's gems.")
