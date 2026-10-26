"""diablocraft-jeweler-window: the client Lua test, run again on a mutated copy of dc_jeweler.lua or of the
shared look module dc_aio_ui.lua per rule.

test_jeweler_client.lua drives the real file against a stub client. A test that cannot fail proves nothing,
so each rule it pins is removed from a copy of the source in turn (DC_JEWELER_LUA and DC_UI_LUA name the
copies) and the run must fail; the unmutated files must pass.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
JEWELER = MODULE / "lua/aio/dc_jeweler.lua"
SERVER = MODULE / "lua/aio/dc_jeweler_server.lua"
UI = MODULE / "lua/aio/dc_aio_ui.lua"
SOURCE = JEWELER.read_text(encoding="utf-8")
SERVER_SOURCE = SERVER.read_text(encoding="utf-8")
UI_SOURCE = UI.read_text(encoding="utf-8")
TEST = HERE / "tests/crafting/test_jeweler_client.lua"
SERVER_TEST = HERE / "tests/crafting/test_jeweler.lua"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/jeweler-window"
LUA = shutil.which("lua5.2") or shutil.which("lua5.1") or shutil.which("lua")

# (what the test is for, the production text, the same text with the rule removed)
# A 4-tuple ("ui", rule, old, new) mutates dc_aio_ui.lua instead of dc_jeweler.lua.
MUTATIONS = [
    ("tiers highest first", "table.sort(list,function(a,b) return (a.rank or 0)>(b.rank or 0) end)",
     "table.sort(list,function(a,b) return (a.rank or 0)<(b.rank or 0) end)"),
    ("colours A to Z", "    table.sort(colours)\n", "    table.sort(colours,function(a,b) return a>b end)\n"),
    ("[n] limited by gold", "    n=math.min(n,Logic.times(balance.gold,recipe.gold or 0))\n", "    n=n\n"),
    ("[n] limited by Death's Breath", "    return math.min(n,Logic.times(balance.deathsBreath,recipe.deathsBreath or 0))",
     "    return n"),
    ("[n] limited by gems", "local n=math.floor((recipe.have or 0)/math.max(recipe.inputCount or 1,1))",
     "local n=UINT32_MAX"),
    ("[n] shown in the row", '(entry.n>=1 and "["..entry.n.."] " or "")..entry.recipe.name', "entry.recipe.name"),
    ("quantity upper clamp", "return math.max(1,math.min(value,math.max(1,most or 1)))", "return math.max(1,value)"),
    ("quantity lower clamp", "return math.max(1,math.min(value,math.max(1,most or 1)))", "return math.min(value,math.max(1,most or 1))"),
    ("typed quantity shown clamped", "    if tostring(qty)~=self:GetText() then self:SetText(tostring(qty)) end\n", ""),
    ("the away rule", "    return atJeweler or not socketFilled\n", "    return true\n"),
    ("away drop on a filled socket is refused",
     "    if not Logic.mayChange(atJeweler(),socket.gemEntry~=0) then say(AWAY_MESSAGE,true);return end\n", ""),
    ("away pull-out is refused",
     "    if not Logic.mayChange(atJeweler(),true) then say(AWAY_MESSAGE,true);return end\n    send(\"remove\"", "    send(\"remove\""),
    ("release on a socket moves nothing", "    if over then return end\n", ""),
    ("a pull ends where the cursor is, not where the mouse focus says",
     "    local over=overSocket(view)\n", "    local target=GetMouseFocus and GetMouseFocus();local over=target and target.dcSocket\n"),
    ("the button coming up ends a pull whose OnDragStop never came",
     "if carry and carry.seenDown then trace", "if false then trace"),
    ("a button seen up before it was seen down ends nothing", "if carry and carry.seenDown then trace", "if carry then trace"),
    ("a press and a move start a pull whose OnDragStart never came", ">8 then trace", ">100000 then trace"),
    ("a press on a filled socket arms the pull", "            if x then J.armed={view=view,index=index,x=x,y=y} end\n", ""),
    ("ui", "a refusal is also kept in the chat", "        if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage(text,1,0.3,0.3) end\n", ""),
    ("no repair verb", "local JEWELER_FIELDS={socket=4,remove=3,combine=3,craft=3}", "local JEWELER_FIELDS={socket=4,remove=3,combine=3,craft=3,repair=1}"),
    ("the request carries the count the bar was started for", 'send("combine",job.recipe,job.count)', 'send("combine",job.recipe,1)'),
    ("only a click that can make something starts the bar", '    if maxCraft()<1 then return false end\n', ""),
    ("Create is greyed when nothing can be made", "    else createAll:Disable();createOne:Disable() end", "    else createAll:Enable();createOne:Enable() end"),
    ("a request still waiting for its reply is not stacked on", "    if awaiting and GetTime()-awaiting<=3 then return false end\n    J.StartCombine", "    J.StartCombine"),
    ("nothing is sent before the bar is full", "    if job.elapsed<COMBINE_SECONDS then return end\n    endBar()", "    if job.elapsed<0 then return end\n    endBar()"),
    ("the bar is two seconds", "local COMBINE_SECONDS=2\n", "local COMBINE_SECONDS=1\n"),
    ("a second click while it runs is ignored", "function J.Create(count)\n    if bar.job then return false end\n", "function J.Create(count)\n"),
    ("the arrows are locked while it runs", "function J.SetQty(value)\n    if bar.job then return end\n", "function J.SetQty(value)\n"),
    ("the recipe choice is locked while it runs", "function J.Select(id)\n    if bar.job then return end\n", "function J.Select(id)\n"),
    ("typing is locked while it runs", "    if not user or bar.job then return end", "    if not user then return end"),
    ("the buttons are disabled while it runs", "ipairs(lockable) do\n        if locked then control:Disable() else control:Enable() end", "ipairs(lockable) do\n        if locked then control:Enable() else control:Enable() end"),
    ("the quantity box is locked while it runs", "    qtyBox:EnableMouse(not locked)\n", "    qtyBox:EnableMouse(true)\n"),
    ("the bar names the quantity and the gem", '"Combining "..count.." "..recipe.name', '"Combining "..recipe.name'),
    ("ui", "the fill grows", "        self.fill:SetWidth(math.max(1,(self:GetWidth()-4)*(progress or 0)))\n", ""),
    ("a cancel says so in red", "    say(CANCELLED,true)\n", ""),
    ("leaving the Jeweler cancels", "    J.CancelCombine();J.CancelCraft()\nend)", "    J.CancelCraft()\nend)"),
    ("leaving the Combine tab cancels", "    if not showCombine then J.CancelCombine() end\n", ""),
    ("a cancelled bar never sends later", "    bar.job=nil;bar:SetScript", "    bar:SetScript"),
    ("Create All is one request for what can be made", "return J.Create(math.max(1,maxCraft()))", "return J.Create(1)"),
    ("one click is one request", "    if not width then return false end\n    if awaiting and GetTime()-awaiting<=3 then return false end\n",
     "    if not width then return false end\n"),
    ("Shift+Right-click on a bag item hooks the stock call",
     'if _G["SocketContainerItem"] then hooksecurefunc("SocketContainerItem"', 'if false then hooksecurefunc("SocketContainerItem"'),
    ("Shift+Right-click on the sheet hooks the stock call",
     'hooksecurefunc("SocketInventoryItem",function(slotIndex) J.OpenSockets(255,slotIndex-1) end)',
     'hooksecurefunc("SocketInventoryItem",function(slotIndex) J.OpenSockets(255,slotIndex) end)'),
    ("the stock socket frame is put away", "if ItemSocketingFrame and ItemSocketingFrame:IsShown() then HideUIPanel(ItemSocketingFrame) end", ""),
    ("at the Jeweler the click opens the tab", "    if frame:IsShown() then\n        tab=\"socket\";socketView.item=item;render()",
     "    if false then\n        tab=\"socket\";socketView.item=item;render()"),
    ("a swap at the Jeweler is sent", "    send(\"socket\",item.guid,socket.seq,gemGuid)\nend",
     "    if socket.gemEntry==0 then send(\"socket\",item.guid,socket.seq,gemGuid) end\nend"),
    ("the cursor item is found by where it was picked up",
     "if gem.bag==cursorBag and gem.slot==cursorSlot and (not id or gem.entry==id) then", "if gem.entry==id then"),
    ("the Sockets window refreshes by guid", "AIO.Handle(CHANNEL,\"Gear\",0,0,refreshing)", "AIO.Handle(CHANNEL,\"Refresh\")"),
    ("an action's own bag update is not a re-read", "    if not (frame:IsShown() or sockFrame:IsShown()) or awaiting then return end\n",
     "    if not (frame:IsShown() or sockFrame:IsShown()) then return end\n"),
    ("an action's own bag update is not saved for later",
     "        if GetTime()-awaiting>3 then awaiting=nil else return end\n", "        if GetTime()-awaiting>3 then awaiting=nil end\n"),
    ("a gem with no effect text for the item type", "return effects and effects[slotClass] or nil", "return effects and effects.weapon or nil"),
    # The count colour is the shared DCUI setter's since UI fixes row 4 (2026-10-03).
    ("ui", "a short material is red", "U.colour(line.count,enough and GOLD or RED)", "U.colour(line.count,GOLD)"),
    ("entering combat cancels the combine bar",
     'if event=="PLAYER_REGEN_DISABLED" and J.restoreIds then J.restoreIds() end\n    J.CancelCombine()',
     'if event=="PLAYER_REGEN_DISABLED" then if J.restoreIds then J.restoreIds() end return end\n    J.CancelCombine()'),
    ("an item dropped on the item frame is not taken",
     "    view.sockets={}\n", "    view.sockets={}\n    box:SetScript(\"OnReceiveDrag\",function() view.item=model.items[1];view:Render() end)\n"),
    ("the empty item frame says how to load an item", 'view.hint:SetText(compact and "Shift+Right-click an item to see its sockets" or "Right-click an item to see its sockets")',
     'view.hint:SetText("Drag an item here")'),
    ("the Jeweler's tab is Unsocket Gems", 'label="Unsocket Gems"', 'label="Socket Gems"'),
    ("the Jeweler's subtitle is Unsocket Gems", 'sub:SetText(def.label:upper())', 'sub:SetText(def.label)'),
    ("closing the window cancels", 'frame:SetScript("OnHide",function() J.CancelCombine();J.CancelCraft();if J.restoreIds then J.restoreIds() end end)',
     'frame:SetScript("OnHide",function() if J.restoreIds then J.restoreIds() end end)'),
    ("a right-click loads only while the tab is open", "                    if mouseButton~=\"RightButton\" or not takesRightClick() then return end\n", ""),
    ("never in combat", " and not (InCombatLockdown and InCombatLockdown())", ""),
    ("only on the Unsocket Gems tab", 'return frame:IsShown() and tab=="socket" and', "return frame:IsShown() and"),
    ("a gem keeps its right-click", "local function isGem(entry) return entry and tables and tables.gems and tables.gems[entry] end", "local function isGem(entry) return nil end"),
    ("only a right-click", 'if mouseButton~="RightButton" or not takesRightClick() then return end', 'if not takesRightClick() then return end'),
    ("the click is turned into a no-op", "                        self:SetID(spare)\n", ""),
    ("the slot id is put back after the click", "    if id then self:SetID(id);blanked[self]=nil end\n", "    blanked[self]=nil\n"),
    ("combat starting puts the id back", 'if event=="PLAYER_REGEN_DISABLED" and J.restoreIds then J.restoreIds() end', 'if false then J.restoreIds() end'),
    ("closing the window puts the id back", "J.CancelCombine();J.CancelCraft();if J.restoreIds then J.restoreIds() end end)", "J.CancelCombine();J.CancelCraft() end)"),
    ("the stock click is not replaced", "                btn:HookScript(\"PostClick\",postClick)\n",
     "                btn:HookScript(\"PostClick\",postClick)\n                _G.ContainerFrameItemButton_OnClick=function() end\n"),
    ("the stock sheet click is not replaced", "                btn:HookScript(\"PostClick\",postClick)\n",
     "                btn:HookScript(\"PostClick\",postClick)\n                _G.PaperDollItemSlotButton_OnClick=function() end\n"),
    ("the Torment sheet is read by its WoW slot", "return 255,worn,nil,entryOf(GetInventoryItemLink(\"player\",worn+1))", "return 255,worn+1,nil,entryOf(GetInventoryItemLink(\"player\",worn+1))"),
    ("the Jeweler claims the right-click from the sheet", "Diablocraft.ClaimRightClick(takesRightClick) end", "end"),
    ("the sheet's id is never swapped", "and source.blank~=false then", "then"),
    ("the sheet counts from 1", "return 255,slotId-1,nil,", "return 255,slotId,nil,"),
    ("ui", "the bar covers nothing", 'bar:SetSize(512,24);bar:SetPoint("TOPLEFT",0,-436)', 'bar:SetSize(222,24);bar:SetPoint("TOPLEFT",16,-375)'),
    ("ui", "the bar is not over the funds line", 'bar:SetPoint("TOPLEFT",0,-436)', 'bar:SetPoint("TOPLEFT",0,-408)'),
    ("ui", "the bar is opaque", "bar.bg:SetVertexColor(U.BAR_BG[1],U.BAR_BG[2],U.BAR_BG[3],1)", "bar.bg:SetVertexColor(U.BAR_BG[1],U.BAR_BG[2],U.BAR_BG[3],.5)"),
    ("ui", "the bar is above its neighbours", "    bar:SetFrameLevel(parent:GetFrameLevel()+10)\n", ""),
    ("a held item stops the click being taken", "                    if GetCursorInfo and GetCursorInfo() then return end\n", ""),
    ("Shift is the stock modified click", "(IsShiftKeyDown and IsShiftKeyDown()) or ", ""),
    ("Ctrl is the stock modified click", "(IsControlKeyDown and IsControlKeyDown())\n", "false\n"),
    ("Alt is the stock modified click", "or (IsAltKeyDown and IsAltKeyDown()) then return end", "then return end"),
    ("a full bag is not loaded", "                    if not spare then say(source.noRoom,true);return end\n", "                    spare=spare or 0\n"),
    ("a full bag says why", "                    if not spare then say(source.noRoom,true);return end\n", "                    if not spare then return end\n"),
    ("the sheet never uses slot 0", "         return nil   -- slot 0 is the ammo slot, a real one: never used as a stand-in\n", "         return 0\n"),
    ("an item with no sockets says so", 'elseif ask.message then say("That item has no sockets.",true) end', "end"),
    ("Remove Gems is enabled only with a gem", "if gems>0 and not chain then self.removeAll:Enable() else self.removeAll:Disable() end", "self.removeAll:Enable()"),
    ("Remove Gems is only in the Jeweler's window", "    if not compact then\n        view.removeAll=", "    if true then\n        view.removeAll="),
    ("Remove Gems checks the room first", '        if free<#seqs then say("Not enough bag space: "..#seqs.." free slots are needed.",true);return false end\n', ""),
    ("only filled sockets are removed", "if socket.gemEntry~=0 then seqs[#seqs+1]=socket.seq end", "seqs[#seqs+1]=socket.seq"),
    ("each reply sends the next removal", '        if record=="E" and chain then nextRemove() end\n', ""),
    ("a refusal ends the run", 'say(f[2] or "That did not work.",true);chain=nil end', 'say(f[2] or "That did not work.",true) end'),
    ("a reply from anyone else is ignored", '    if sender~=me and sender~=me.."-"..GetRealmName() then return end\n', ""),
    ("a stack record moves the count", "        recipe.have=count\n", ""),
    ('the craft verb is on the bridge', 'combine=3,craft=3}', 'combine=3}'),
    ('the request carries the count the craft bar was started for', 'send("craft",job.recipe,job.count)', 'send("craft",job.recipe,1)'),
    ('[n] limited by gold, Craft Jewelry', 'local n=math.min(capacity or 0,Logic.times(balance.gold,tonumber(recipe.gold) or 0))', 'local n=capacity or 0'),
    ('[n] limited by each material, Craft Jewelry', '        n=math.min(n,Logic.times(material.have,math.max(material.amount or 1,1)))\n', ''),
    ('[n] limited by the bag capacity', 'local n=math.min(capacity or 0,', 'local n=math.min(UINT32_MAX,'),
    ('a disabled recipe makes none', '    if not recipe.enabled then return 0 end\n', ''),
    ('pages A to Z', '    table.sort(pages)\n', '    table.sort(pages,function(a,b) return a>b end)\n'),
    ('legendary before rare', 'return (CRAFT_RANK[a.rarity] or 0)>(CRAFT_RANK[b.rarity] or 0)', 'return (CRAFT_RANK[a.rarity] or 0)<(CRAFT_RANK[b.rarity] or 0)'),
    ('Have materials, Craft Jewelry', 'if (not view.haveMats or n>=1) and (query=="" or recipe.name:lower():find(query,1,true)) then\n            local list=byPage', 'if (query=="" or recipe.name:lower():find(query,1,true)) then\n            local list=byPage'),
    ('search, Craft Jewelry', 'if (not view.haveMats or n>=1) and (query=="" or recipe.name:lower():find(query,1,true)) then\n            local list=byPage', 'if (not view.haveMats or n>=1) then\n            local list=byPage'),
    ('a search opens a collapsed page', 'view.collapsed[page] and query=="" and true or false', 'view.collapsed[page] and true or false'),
    ('the third tab is Craft Jewelry', 'label="Craft Jewelry"', 'label="Craft Jewellery"'),
    ('the craft controls are locked while it runs', 'craftQtyBox:EnableMouse(not locked);craftSearchBox:EnableMouse(not locked)', 'craftQtyBox:EnableMouse(true);craftSearchBox:EnableMouse(true)'),
    ('leaving the Jeweler or fighting cancels the craft bar', '    J.CancelCombine();J.CancelCraft()\nend)', '    J.CancelCombine()\nend)'),
    ('closing the window cancels the craft bar', 'J.CancelCombine();J.CancelCraft();if J.restoreIds', 'J.CancelCombine();if J.restoreIds'),
    ('leaving the Craft tab cancels', '    if not showCraft then J.CancelCraft() end\n', ''),
    ('a craft cancel says so in red', '    say(CRAFT_CANCELLED,true)\n', ''),
    ('only a craft that can be made starts the bar', '    if maxMake()<1 then return false end\n', ''),
    ('a craft request still waiting for its reply is not stacked on', '    if awaiting and GetTime()-awaiting<=3 then return false end\n    J.StartCraft', '    J.StartCraft'),
    ('nothing is crafted before the bar is full', '    if job.elapsed<COMBINE_SECONDS then return end\n    endCraftBar()', '    endCraftBar()'),
    ('Create All crafts what can be made in one request', 'return J.Craft(math.max(1,maxMake()))', 'return J.Craft(1)'),
    ("a craft's reply has the window read Show again", '        if record=="E" and J.lastSent=="craft" then dirty=true;quiet=0 end\n', ''),
    ('a second craft click while it runs is ignored', 'function J.Craft(count)\n    if craftBar.job then return false end\n', 'function J.Craft(count)\n'),
    ('the craft recipe choice is locked while it runs', 'function J.SelectCraft(id)\n    if craftBar.job then return end\n', 'function J.SelectCraft(id)\n'),
    ('the craft arrows are locked while it runs', 'function J.SetCraftQty(value)\n    if craftBar.job then return end\n', 'function J.SetCraftQty(value)\n'),
    ('a short craft material is red', 'U.count(r,material.have,need,Logic.atLeast(material.have,need))', 'U.count(r,material.have,need,true)'),
    ('the craft cost follows the quantity', 'local cost=(tonumber(recipe.gold) or 0)*craftQty', 'local cost=(tonumber(recipe.gold) or 0)'),
    ('the craft materials follow the quantity', 'local need=material.amount*craftQty', 'local need=material.amount'),
    ('a disabled craft says why', 'craftDetail.note:SetText(recipe.enabled and "" or recipe.reason)', 'craftDetail.note:SetText("")'),
    ('a typed craft quantity is shown clamped', '    if tostring(craftQty)~=self:GetText() then self:SetText(tostring(craftQty)) end\n', ''),
    ('a legendary craft is orange', 'CRAFT_TINT={set={.1,1,.1},legendary={1,.5,0}', 'CRAFT_TINT={set={.1,1,.1},legendary={1,1,1}'),
    ('a craft row shows its [n]', 'Logic.rowText({n=row.n,recipe=row.recipe})', 'row.recipe.name'),
    ('a craft header click closes its page', 'craftCollapsed[row.page]=not craftCollapsed[row.page]', 'craftCollapsed[row.page]=false'),
    ("a split affix list keeps the sockets its earlier F records built",
     "    local sockets=item.sockets or {}\n    for i=3,#f do", "    local sockets={}\n    for i=3,#f do"),
]


# The server half (test_jeweler.lua): the same, for the Gear read that opens the Sockets window anywhere.
SERVER_MUTATIONS = [
    ("Gear needs no Jeweler nearby", '    if not player:IsAlive() then return end\n    local picked', '    if not valid(player,"Gear") then return end\n    local picked'),
    ("Gear refuses a guid that is not a number", '        if not integer(guid,1) then return end\n', ''),
    ("Gear refuses a bag or slot out of range", '        if not (integer(bag,0) and bag<=255 and integer(slot,0) and slot<=255) then return end\n', ''),
    ("Gear is throttled with Refresh", '    if not DCThrottle.Allow(player,"jeweler:refresh",5,10) then return end\n    local items,gems=inventory(player,picked)',
     '    local items,gems=inventory(player,picked)'),
    ("Gear reads only the item asked for", '        if wanted and not wanted(bag,slot,guid) then return end\n', ''),
    ("a dead player is not answered", '    if not player:IsAlive() then return end\n    local picked', '    local picked'),
    ("an item carries its slot class", "slotClass=slotClass(entry),", 'slotClass="other",'),
    ("a recipe carries its tier rank", "            rank=rows:GetUInt32(9),\n", ""),
    ("the tables carry each gem's effects", "{gems=gemNames,effects=effects(),legendary=legendary}", "{gems=gemNames,legendary=legendary}"),
    ("Show carries the Craft Jewelry catalogue", "        crafts=crafts(player,snapshot),craftMax=craftMax(player)})", "        })"),
    ("a craft material is counted from the bags or the ledger", "have=DCAccount.Have(snapshot,entry)}", 'have="0"}'),
    ("the craft bound is the bag slots", "    local total=16\n", "    local total=0\n"),
    ("a craft material carries its amount", "list[#list+1]={entry=entry,amount=rows:GetUInt32(2),", "list[#list+1]={entry=entry,amount=1,"),
    ("a craft recipe carries its gold", "gold=rows:GetString(9),enabled", 'gold="0",enabled'),
]


def run(source_path, test=TEST, ui_path=UI, server_path=SERVER):
    env = dict(os.environ, DC_JEWELER_LUA=str(source_path), DC_UI_LUA=str(ui_path), DC_JEWELER_SERVER_LUA=str(server_path))
    return subprocess.run([LUA, str(test)], cwd=ROOT, env=env, text=True, capture_output=True)


@unittest.skipUnless(LUA, "no lua interpreter")
class JewelerClient(unittest.TestCase):
    def test_production_passes(self):
        done = run(JEWELER)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_server_half_passes(self):
        done = run(JEWELER, SERVER_TEST)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def survivors(self, mutations, test):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        survived = []
        with tempfile.TemporaryDirectory(prefix="mutant-", dir=SCRATCH) as folder:
            for index, entry in enumerate(mutations):
                if len(entry) == 4:
                    target, rule, old, new = entry
                else:
                    target, (rule, old, new) = "jeweler", entry
                server = test == SERVER_TEST
                source = UI_SOURCE if target == "ui" else SERVER_SOURCE if server else SOURCE
                self.assertEqual(source.count(old), 1, f"mutation anchor is not unique or not found: {rule}")
                mutant = Path(folder) / f"mutant{index}.lua"
                mutant.write_text(source.replace(old, new), encoding="utf-8")
                if server:
                    done = run(JEWELER, test, server_path=mutant)
                else:
                    done = run(JEWELER, test, ui_path=mutant) if target == "ui" else run(mutant, test)
                if done.returncode == 0:
                    survived.append(rule)
        return survived

    def test_every_rule_the_client_test_pins_fails_when_removed(self):
        self.assertEqual(self.survivors(MUTATIONS, TEST), [], "the client test passed with the rule removed")

    def test_every_rule_the_server_test_pins_fails_when_removed(self):
        self.assertEqual(self.survivors(SERVER_MUTATIONS, SERVER_TEST), [], "the server test passed with the rule removed")


if __name__ == "__main__":
    unittest.main()
