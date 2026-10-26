-- luacheck: globals UISpecialFrames AIO UnitName GetRealmName GetTime SendAddonMessage GetBindingFromClick RunBinding DCGreaterRift Diablocraft
-- luacheck: ignore 111 113 121 122
-- Run from the repo root: lua mod-diablocraft/scripts/tests/rifts/test_greater_rift_window.lua
--
-- dc_greater_rift.lua (diablocraft-kufs) against the strict 3.3.5a widget mock, on the records of
-- docs/contracts/rift-enrollment-messages.md (DCRIFTENROLL). What it pins:
--   * the file asks `sync` once at load;
--   * L opens the opening window with start..unlocked, the highest selected, the Keystone count;
--     a row click selects, Open and Enter send `open<TAB>level`; Esc closes; X keeps it up with
--     the server's text; C closes it; no level means no Open;
--   * P opens the ready check for every member: level, leader, each member's status, the countdown;
--     Accept/Decline send `respond<TAB>id<TAB>accept|decline` and lock until the next P/T; an older or
--     repeated revision, a malformed P and a P after the final T are not drawn;
--   * at local zero the buttons lock and it says Waiting for the server..., never anything else;
--   * T starting locks, T started closes, T cancelled shows the server's own words with Close;
--   * Escape closes the ready check (it is in UISpecialFrames, diablocraft-zw5n); on an open answer it is Decline,
--     the same respond the button sends (diablocraft-df92); once answered, at local zero, on started or by Close
--     after a result it sends nothing, and the next P shows a hidden window again;
--   * a record on another prefix or from another sender is dropped.
-- What this does NOT cover: the server's rules (test_gr_open.py, test_gr_window.py) and the look
-- (the designer's check on dev).
local SOURCE=os.getenv("DC_GR_LUA") or "mod-diablocraft/lua/aio/dc_greater_rift.lua"

local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local sent,now,shots={},0,0
function UnitName() return "Tester" end
function GetRealmName() return "Torment" end
function GetTime() return now end
function SendAddonMessage(prefix,body,distribution,target)
    sent[#sent+1]={prefix=prefix,body=body,distribution=distribution,target=target}
end
function GetBindingFromClick(key) return ({ESCAPE="TOGGLEGAMEMENU",PRINTSCREEN="SCREENSHOT"})[key] end
function RunBinding(action) if action=="SCREENSHOT" then shots=shots+1 end end
AIO={AddAddon=function() return false end}
Diablocraft=nil
dofile("mod-diablocraft/lua/aio/dc_aio_ui.lua")
dofile(SOURCE)

local G=DCGreaterRift
local ui=G.ui
local function last() return sent[#sent] end
local function chat(body,sender,prefix) G.OnMessage(prefix or "DCRIFTENROLL",body,"WHISPER",sender or "Tester") end
local function shownRows()
    local out={}
    for _,row in ipairs(ui.rows) do if row:IsShown() then out[#out+1]=row end end
    return out
end
local function marked()
    for _,row in ipairs(shownRows()) do if row.mark:IsShown() then return row.level end end
end
local function key(k) ui.open.scripts.OnKeyDown(ui.open,k) end
local function click(b) assert(b:IsEnabled(),"the button is clickable");b.scripts.OnClick(b) end
local function statusOf(i) return ui.members[i].status:GetText() end

-- 1. Load asks for a ready check still waiting on us, and opens nothing.
assert(#sent==1 and last().prefix=="DCRIFTENROLL" and last().body=="sync" and last().distribution=="WHISPER"
    and last().target=="Tester","load sends sync once, got "..tostring(last() and last().body))
assert(not ui.open:IsShown() and not ui.ready:IsShown(),"nothing is open at load")

-- 2. Another prefix or sender is dropped.
chat("L|1|7|3|1","Somebody")
chat("L|1|7|3|1","Tester","DCREVIVE")
assert(not ui.open:IsShown(),"an L from elsewhere opens nothing")

-- 3. L: the list start..unlocked, the highest selected, the Keystone count.
chat("L|1|7|3|1")
assert(ui.open:IsShown(),"L opens the opening window")
local rows=shownRows()
assert(#rows==7,"levels 1 to 7 are listed, got "..#rows)
assert(rows[1].level==7 and rows[7].level==1 and rows[1].label:GetText()=="Greater Rift 7","highest first")
assert(marked()==7,"the highest unlocked level is selected")
assert(ui.keystones:GetText()=="Greater Rift Keystones: 3","the Keystone count, got "..tostring(ui.keystones:GetText()))
assert(ui.openButton:IsEnabled(),"Open is clickable")

-- 4. A click selects; Enter and Open send that level; nothing else is sent.
rows[4].scripts.OnClick(rows[4])
assert(marked()==4,"a row click selects its level")
key("ENTER")
assert(last().body=="open\t4","Enter sends open with the selected level, got "..last().body)
click(ui.openButton)
assert(last().body=="open\t4","Open sends the same")
key("W")
assert(last().body=="open\t4" and ui.open:IsShown(),"any other key sends nothing")
key("PRINTSCREEN")
assert(shots==1,"a screenshot still works while the window has the keyboard")

-- 5. X after open: the window stays and shows the server's text.
chat("X|You need 1 Greater Rift Keystone.")
assert(ui.open:IsShown() and ui.openNote:GetText()=="You need 1 Greater Rift Keystone.","a refusal stays up with its text")

-- 6. Esc closes; C (walk-away) closes.
key("ESCAPE")
assert(not ui.open:IsShown(),"Esc closes the opening window")
chat("L|1|3|0|1")
assert(ui.open:IsShown() and #shownRows()==3 and marked()==3 and ui.openNote:GetText()=="","a new L redraws from scratch")
chat("C")
assert(not ui.open:IsShown(),"C (walked away from the obelisk) closes it")

-- 7. No level open: no rows, no Open.
chat("L|1|0|2|1")
assert(#shownRows()==0 and not ui.openButton:IsEnabled(),"no openable level: nothing to open")
local before=#sent
key("ENTER")
assert(#sent==before,"Enter sends nothing without a level")

-- 8. P opens the ready check (and closes the opening window).
chat("L|1|7|3|1")
now=100
chat("P|17|1|GR|7|42|Tester|40000|2|42|Tester|waiting|43|Friend|waiting")
assert(ui.ready:IsShown() and not ui.open:IsShown(),"P opens the ready check and closes the opening window")
assert(ui.levelLine:GetText()=="Greater Rift 7" and ui.leaderLine:GetText()=="Leader: Tester","level and leader")
assert(ui.timeLine:GetText()=="Time remaining: 40 s","the countdown starts at remainingMs, got "..ui.timeLine:GetText())
assert(ui.members[1].name:GetText()=="Tester" and statusOf(1)=="Waiting" and ui.members[2].name:GetText()=="Friend"
    and statusOf(2)=="Waiting" and ui.members[3].name:GetText()=="","one row per member")
assert(ui.accept:IsEnabled() and ui.decline:IsEnabled() and not ui.close:IsShown(),"Accept and Decline, no Close")
local onEsc=false
for _,name in ipairs(UISpecialFrames) do onEsc=onEsc or name=="TormentGreaterRiftReadyFrame" end
assert(onEsc and ui.ready:GetName()=="TormentGreaterRiftReadyFrame","Escape closes the ready check (diablocraft-zw5n)")

-- 9. Accept sends respond and locks until the server answers.
click(ui.accept)
assert(last().body=="respond\t17\taccept","Accept sends respond, got "..last().body)
assert(not ui.accept:IsEnabled() and not ui.decline:IsEnabled(),"both lock after a click")
local clicked=#sent
ui.ready:Hide()
assert(#sent==clicked,"Escape while our Accept waits for the server sends no Decline on top of it")
ui.ready:Show()

-- 10. X after respond: the text, and the buttons come back.
chat("X|That Greater Rift ready check is no longer active.")
assert(ui.note:GetText()=="That Greater Rift ready check is no longer active." and ui.accept:IsEnabled(),"a refused reply unlocks with the text")

-- 11. P revision 2: our accept recorded. Escape now only hides (no answer is open), and a P shows it again.
now=110
chat("P|17|2|GR|7|42|Tester|30000|2|42|Tester|accepted|43|Friend|waiting")
assert(statusOf(1)=="Accepted" and ui.note:GetText()=="Accepted. Waiting for the party.","our accept is drawn")
before=#sent
ui.ready:Hide()
assert(#sent==before,"Escape after an accept sends nothing (the answer is given)")
chat("P|17|2|GR|7|42|Tester|30000|2|42|Tester|accepted|43|Friend|waiting")
assert(not ui.ready:IsShown(),"a repeated revision does not reopen it")
ui.ready:Show() -- the server's next P would; the test goes on with the window up
assert(not ui.accept:IsEnabled() and not ui.decline:IsEnabled(),"no second answer once accepted")
assert(ui.timeLine:GetText()=="Time remaining: 30 s","the server's deadline, not a restart")

-- 12. Older and repeated revisions, and a malformed P, are not drawn.
chat("P|17|1|GR|7|42|Tester|40000|2|42|Tester|waiting|43|Friend|declined")
chat("P|17|2|GR|7|42|Tester|40000|2|42|Tester|waiting|43|Friend|declined")
chat("P|17|3|GR|7|42|Tester|40000|3|42|Tester|waiting|43|Friend|declined")
assert(statusOf(1)=="Accepted" and statusOf(2)=="Waiting","stale or malformed P leaves the window as it was")

-- 13. The countdown runs locally; at zero it only waits for the server.
now=125
G.Render()
assert(ui.timeLine:GetText()=="Time remaining: 15 s","counts down from the last P, got "..ui.timeLine:GetText())

-- 14. T cancelled: the server's words, Close, and the window stays.
chat("T|17|3|cancelled|7|Tester|declined|Greater Rift 7 cancelled. Declined: Friend.")
assert(ui.ready:IsShown() and ui.note:GetText()=="Greater Rift 7 cancelled. Declined: Friend.","the cancel text as is")
assert(not ui.accept:IsShown() and not ui.decline:IsShown() and ui.close:IsShown(),"only Close is left")
chat("P|17|9|GR|7|42|Tester|40000|2|42|Tester|waiting|43|Friend|waiting")
assert(ui.close:IsShown() and ui.note:GetText()=="Greater Rift 7 cancelled. Declined: Friend.","no P after the final T")
click(ui.close)
assert(not ui.ready:IsShown(),"Close takes it away")

-- 14b. Escape on an open answer is Decline (diablocraft-df92): the same respond the button sends, and the server's
-- cancel comes back into the window as after a click.
now=150
chat("P|19|1|GR|4|43|Friend|40000|2|43|Friend|accepted|42|Tester|waiting")
assert(ui.ready:IsShown() and ui.decline:IsEnabled(),"an open answer")
before=#sent
ui.ready:Hide()
assert(#sent==before+1 and last().body=="respond\t19\tdecline","Escape sends Decline, got "..last().body)
chat("T|19|2|cancelled|4|Friend|declined|Greater Rift 4 cancelled. Declined: Tester.")
assert(ui.ready:IsShown() and ui.close:IsShown() and ui.note:GetText()=="Greater Rift 4 cancelled. Declined: Tester.","the cancel shows")
before=#sent
click(ui.close)
assert(#sent==before and not ui.ready:IsShown(),"Close after the result sends nothing")

-- 15. A new id, as the other member: a decline, local zero, starting, started.
now=200
chat("P|18|1|GR|5|43|Friend|40000|2|43|Friend|accepted|42|Tester|waiting")
assert(ui.ready:IsShown() and ui.leaderLine:GetText()=="Leader: Friend" and ui.accept:IsEnabled(),"a fresh ready check")
click(ui.decline)
assert(last().body=="respond\t18\tdecline","Decline sends respond decline")
chat("P|18|2|GR|5|43|Friend|40000|2|43|Friend|accepted|42|Tester|waiting") -- someone else's update
assert(ui.accept:IsEnabled(),"a newer P is the server's answer: we are still waiting, so we may answer")
now=241
G.Render()
assert(ui.timeLine:GetText()=="Time remaining: 0 s" and ui.note:GetText()=="Waiting for the server..."
    and not ui.accept:IsEnabled() and not ui.decline:IsEnabled(),"at zero: locked, waiting for the server")
assert(ui.ready:IsShown(),"and never closes or announces anything itself")
before=#sent
ui.ready:Hide()
assert(#sent==before,"Escape at local zero sends nothing (the answer is closed)")
ui.ready:Show()
chat("T|18|3|starting|5|Friend||Everyone accepted. Starting Greater Rift 5...")
assert(ui.note:GetText()=="Everyone accepted. Starting Greater Rift 5..." and not ui.accept:IsEnabled() and not ui.close:IsShown(),"starting locks")
before=#sent
chat("T|18|4|started|5|Friend||Greater Rift 5 has started. Entering the rift.")
assert(not ui.ready:IsShown() and #sent==before,"started closes the window and sends nothing")
chat("P|18|5|GR|5|43|Friend|40000|2|43|Friend|accepted|42|Tester|accepted")
assert(not ui.ready:IsShown(),"and nothing reopens it")

-- 16. A T for an id never seen opens nothing.
chat("T|99|1|cancelled|3|Someone|timeout|Greater Rift 3 cancelled. No response: Someone.")
assert(not ui.ready:IsShown(),"a stray T opens nothing")

print("test_greater_rift_window: ok")
