-- luacheck: globals DCUI UISpecialFrames AIO UnitName GetRealmName SendAddonMessage GetItemIcon DCUrshi Diablocraft UIErrorsFrame
-- luacheck: ignore 111 113 121 122
-- Run from the repo root: lua mod-diablocraft/scripts/tests/rifts/test_urshi_window.lua
--
-- dc_urshi.lua (diablocraft-ramc) against the strict 3.3.5a widget mock, on the records of
-- docs/contracts/urshi-messages.md (DCURSHI). What it pins:
--   * nothing is sent or opened at load; W opens the window, with the level and left / total tries;
--   * the rows are the server's, in arrival order (never sorted), each with the icon of its entry, its name,
--     rank and chance; a full gem is grey, says Max, is disabled and cannot be picked;
--   * a list is drawn only when complete (L..E); a G outside one, or a malformed G, is dropped;
--   * Upgrade is off with no pick, with 0 tries, and while a try waits for its answer; it sends
--     `upgrade<TAB>id` with the server's own id and nothing else;
--   * U shows the result, asks the tooltip records again, and the pick is kept by id across the redraw
--     (dropped when the gem is gone or full);
--   * X shows its text and stays, except Urshi out of reach, which closes; C closes with its text;
--   * a bag or gear change while up asks `list` once, after the bags settle and never during a try;
--   * a record on another prefix or from another sender is dropped;
--   * the prefix, verbs, records and the closing refusal are the contract's own words.
-- What this does NOT cover: the server's rules (z94g's tests) and the look (the designer's check on dev).
local SOURCE=os.getenv("DC_URSHI_LUA") or "mod-diablocraft/lua/aio/dc_urshi.lua"

local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local sent,handled={},{}
function UnitName() return "Tester" end
function GetRealmName() return "Torment" end
function GetItemIcon(entry) return "icon:"..entry end
function SendAddonMessage(prefix,body,distribution,target)
    sent[#sent+1]={prefix=prefix,body=body,distribution=distribution,target=target}
end
AIO={AddAddon=function() return false end,Handle=function(...) handled[#handled+1]=table.concat({...},",") end}
Diablocraft=nil
dofile("mod-diablocraft/lua/aio/dc_aio_ui.lua")
dofile(SOURCE)

local W=DCUrshi
local ui=W.ui
local function chat(body,sender,prefix) W.OnMessage(prefix or "DCURSHI",body,"WHISPER",sender or "Tester") end
local function reply(w,list) chat(w);chat("L|"..#list);for _,g in ipairs(list) do chat(g) end;chat("E|list") end
local function shown()
    local out={}
    for _,row in ipairs(ui.rows) do if row:IsShown() then out[#out+1]=row end end
    return out
end
local function marked()
    for _,row in ipairs(shown()) do if row.mark:IsShown() then return row.gem.id end end
end
local function click(b) assert(b:IsEnabled(),"the button is clickable");b.scripts.OnClick(b) end
local function settle(seconds) ui.watcher.scripts.OnUpdate(ui.watcher,seconds) end

-- The contract's own words (the file is on World's branch until it merges).
local contract
do
    local file=io.open("docs/contracts/urshi-messages.md")
    if file then contract=file:read("*a");file:close()
    else
        local pipe=io.popen("git show w/diablocraft-z94g:docs/contracts/urshi-messages.md 2>/dev/null")
        contract=pipe:read("*a");pipe:close()
    end
end
assert(contract and #contract>0,"the contract is readable")
for _,needle in ipairs({"`DCURSHI` `list`","`DCURSHI` `upgrade` `<id>`","`W\\|level\\|left\\|total`","`L\\|n`",
    "`G\\|id\\|where\\|entry\\|name\\|rank\\|max\\|full\\|chance`","`E\\|list`","`U\\|id\\|ok\\|rank\\|left`","`C\\|text`","`X\\|text`",
    "(`X|"..W.Logic.NOT_NEAR.."`). The window should close on this refusal"}) do
    assert(contract:find(needle,1,true),"the contract says "..needle)
end
assert(io.open(SOURCE):read("*a"):find('local PREFIX="DCURSHI"',1,true),"the prefix is the contract's")

local WORN1="G|w901_2|w|103101|Bane of the Trapped|3|0|0|100"
local BAG1="G|g555|b|103104|Gogok of Swiftness|10|0|0|60"
local FULL="G|g777|s|103108|Boon of the Hoarder|25|25|1|0"

-- 1. Load sends nothing and opens nothing.
assert(#sent==0 and not ui.frame:IsShown(),"nothing at load")

-- 2. Another prefix or sender is dropped.
chat("W|20|4|4","Somebody")
chat("W|20|4|4","Tester","DCRIFTENROLL")
assert(not ui.frame:IsShown(),"a W from elsewhere opens nothing")

-- 3. W opens the window; the list is drawn as it came, once complete.
chat("W|20|4|4")
assert(ui.frame:IsShown(),"W opens the window")
assert(ui.sub:GetText()=="Greater Rift 20" and ui.tries:GetText()=="Upgrade attempts: 4 / 4","level and tries")
chat("L|3");chat(WORN1);chat(BAG1)
assert(#shown()==0,"no row before E")
chat(FULL);chat("E|list")
local rows=shown()
assert(#rows==3,"three rows, got "..#rows)
assert(rows[1].gem.id=="w901_2" and rows[2].gem.id=="g555" and rows[3].gem.id=="g777","the server's order, not sorted by rank")
assert(rows[1].icon:GetTexture()=="icon:103101" and rows[1].label:GetText()=="Bane of the Trapped"
    and rows[1].rank:GetText()=="Rank 3" and rows[1].chance:GetText()=="100%","icon, name, rank, chance")
assert(rows[2].chance:GetText()=="60%" and rows[2].rank:GetText()=="Rank 10","the chance is the server's number")
assert(rows[3].chance:GetText()=="Max" and not rows[3]:IsEnabled() and rows[3].icon.desaturated,"a full gem: Max, disabled, grey icon")
local r,g,b=rows[3].label:GetTextColor()
assert(r==DCUI.GREY[1] and g==DCUI.GREY[2] and b==DCUI.GREY[3],"a full gem's name is grey")
assert(not ui.upgrade:IsEnabled(),"Upgrade is off with nothing picked")
local special=false
for _,name in ipairs(UISpecialFrames) do special=special or name=="TormentUrshiFrame" end
assert(special,"Esc closes the window")

-- 4. A full gem cannot be picked; a row can; Upgrade sends the server's id and locks.
rows[3].scripts.OnClick(rows[3])
assert(marked()==nil and not ui.upgrade:IsEnabled(),"a full gem is not picked")
rows[2].scripts.OnClick(rows[2])
assert(marked()=="g555" and ui.upgrade:IsEnabled(),"a click picks the gem")
click(ui.upgrade)
assert(#sent==1 and sent[1].prefix=="DCURSHI" and sent[1].body=="upgrade\tg555" and sent[1].distribution=="WHISPER"
    and sent[1].target=="Tester","Upgrade sends upgrade with the id, got "..tostring(sent[1] and sent[1].body))
assert(not ui.upgrade:IsEnabled(),"locked while the try is out")
W.Upgrade()
assert(#sent==1,"no second try before the answer")

-- 5. U: the result, the tooltip records asked again, then the list reply redraws, the pick kept by id.
chat("U|g555|1|11|3")
assert(ui.note:GetText()=="Gogok of Swiftness is now rank 11.","the success line, got "..tostring(ui.note:GetText()))
assert(handled[#handled]=="DiablocraftTooltip,Refresh","the tooltip records are asked for again")
assert(ui.tries:GetText()=="Upgrade attempts: 3 / 4","the tries left from U")
reply("W|20|3|4",{"G|g555|b|103104|Gogok of Swiftness|11|0|0|60",WORN1,FULL})
rows=shown()
assert(rows[1].gem.id=="g555" and rows[1].rank:GetText()=="Rank 11" and marked()=="g555","the pick follows the gem by id")
assert(ui.upgrade:IsEnabled(),"Upgrade is back on after the answer")
click(ui.upgrade)
chat("U|g555|0|11|2")
assert(ui.note:GetText()=="The upgrade failed. Gogok of Swiftness stays at rank 11.","the failure line")
reply("W|20|2|4",{"G|g555|b|103104|Gogok of Swiftness|11|0|0|60",WORN1,FULL})

-- 6. No tries left: Upgrade off, the pick stays.
reply("W|20|0|4",{"G|g555|b|103104|Gogok of Swiftness|11|0|0|60",WORN1,FULL})
assert(marked()=="g555" and not ui.upgrade:IsEnabled(),"0 tries: Upgrade off")

-- 7. The picked gem reaches its max rank: the pick is dropped.
reply("W|20|2|4",{"G|g555|b|103104|Gogok of Swiftness|25|25|1|0",WORN1})
assert(marked()==nil and not ui.upgrade:IsEnabled(),"a gem gone full is no longer picked")

-- 8. The picked gem is gone: X says so, the window stays, the list reply drops the pick.
shown()[2].scripts.OnClick(shown()[2])
assert(marked()=="w901_2")
click(ui.upgrade)
chat("X|That gem is not there any more.")
assert(ui.frame:IsShown() and ui.note:GetText()=="That gem is not there any more.","a refusal stays up with its text")
assert(ui.upgrade:IsEnabled(),"a refusal answers the try")
reply("W|20|2|4",{BAG1})
assert(#shown()==1 and marked()==nil,"the pick went with the gem")

-- 9. Malformed rows and rows outside a list are dropped; an empty list says so.
chat("G|g999|b|103101|Stray|1|0|0|60");W.Render()
assert(#shown()==1,"a G after E is not drawn")
reply("W|20|2|4",{"G|g1|b|x|Bad|1|0|0|60","G||b|103101|NoId|1|0|0|60","G|g2|b|103101|Short|1|0|0","G|g3|b|103101|Long|1|0|0|60|9",BAG1})
assert(#shown()==1 and shown()[1].gem.id=="g555","malformed rows are dropped")
reply("W|20|2|4",{})
assert(#shown()==0 and ui.note:GetText()=="You have no legendary gems to upgrade.","an empty list")

-- 10. A gem moved while up: one `list` once the bags settle, none while hidden or during a try.
reply("W|20|2|4",{BAG1})
local before=#sent
ui.watcher.scripts.OnEvent(ui.watcher,"BAG_UPDATE",0)
ui.watcher.scripts.OnEvent(ui.watcher,"PLAYER_EQUIPMENT_CHANGED",1)
settle(.2)
assert(#sent==before,"not before the bags settle")
settle(.2)
assert(#sent==before+1 and sent[#sent].body=="list","one list after a move")
settle(1)
assert(#sent==before+1,"only once")
shown()[1].scripts.OnClick(shown()[1]);click(ui.upgrade)
before=#sent
ui.watcher.scripts.OnEvent(ui.watcher,"BAG_UPDATE",0);settle(1)
assert(#sent==before,"no list while a try is out")
chat("U|g555|1|11|1");settle(.1)
assert(#sent==before+1 and sent[#sent].body=="list","the held list goes once the try is answered")

-- 11. Closing sends nothing (the tries stay with the server); W reopens with no stale pick.
before=#sent
ui.frame:Hide()
ui.watcher.scripts.OnEvent(ui.watcher,"BAG_UPDATE",0);settle(1)
assert(#sent==before,"nothing sent while closed")
reply("W|20|1|4",{BAG1})
assert(ui.frame:IsShown() and marked()==nil and ui.note:GetText()=="","reopened clean")

-- 12. Urshi out of reach closes; C closes with its text.
chat("X|"..W.Logic.NOT_NEAR)
assert(not ui.frame:IsShown(),"Urshi is not near you closes the window")
reply("W|20|1|4",{BAG1})
chat("C|Urshi has left.")
assert(not ui.frame:IsShown() and UIErrorsFrame.lines[#UIErrorsFrame.lines]=="Urshi has left.","C closes and shows its text")

print("PASS: Urshi window: opens on W, the server's rows and order, full gems, Upgrade sends only the id, U and the redraw keep the pick, X/C, list after a move.")
