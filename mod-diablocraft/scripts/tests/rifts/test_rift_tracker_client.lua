-- luacheck: ignore 111 112 113 121 122 142 143 211 212 213 431 432 542
-- Run from the repo root: lua mod-diablocraft/scripts/tests/rifts/test_rift_tracker_client.lua
--
-- diablocraft-rift-tracker (ruling 2026-10-03): the Nephalem Rift tracker is an entry at the
-- top of the quest list, as in D3, not a floating bar. The client half of
-- mod-diablocraft/lua/aio/dc_riftbar.lua against doubles of:
--   * the stock 3.3.5 WatchFrame: its XML anchors (WatchFrameLines at TOPLEFT 0,-30 and
--     BOTTOMRIGHT -24,12; WatchFrame.xml), WATCHFRAME_OBJECTIVEHANDLERS, and
--     WatchFrame_Update / _Collapse / _Expand doing what the stock ones do to the header,
--     the collapse button and WatchFrameLines (WatchFrame.lua:301-412);
--   * ElvUI 6.09's mover and skin: WatchFrame anchored to WatchFrameHolder
--     (Modules/Blizzard/WatchFrame.lua:37-38) and the collapse button's .tex reset by
--     ElvUI's own Expand/Collapse hooks (Skins/Blizzard/WatchFrame.lua:18-36);
--   * the quest log and the watch list (GetQuestLogTitle's 9th return is the quest id).
-- Pixels are not proved here: what the designer sees is his check list in
-- docs/test-diablocraft-rift-tracker.md.
local SOURCE = os.getenv("DC_RIFT_LUA") or "mod-diablocraft/lua/aio/dc_riftbar.lua"
unpack = unpack or table.unpack

----------------------------------------------------------------------------------------------------
-- The 3.3.5a widget layer is ONE shared strict mock (diablocraft-yey2); the doubles below
-- are this test's own client globals.
----------------------------------------------------------------------------------------------------
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)
STANDARD_TEXT_FONT = "Fonts\\FRIZQT__.TTF"

----------------------------------------------------------------------------------------------------
-- The stock WatchFrame (WatchFrame.xml / WatchFrame.lua) and ElvUI's mover and skin
----------------------------------------------------------------------------------------------------
WATCHFRAME_TYPE_OFFSET = 10
WATCHFRAME_EXPANDEDWIDTH = 204
local holder = CreateFrame("Frame", "WatchFrameHolder", UIParent)
WatchFrame = CreateFrame("Frame", "WatchFrame", UIParent)
WatchFrame:SetPoint("TOP", holder, "TOP")
WatchFrameHeader = CreateFrame("Button", "WatchFrameHeader", WatchFrame)
WatchFrameTitle = CreateFrame("FontString", "WatchFrameTitle", WatchFrameHeader, "GameFontNormalSmall")
WatchFrameTitle:SetPoint("TOPLEFT")
WatchFrameCollapseExpandButton = CreateFrame("Button", "WatchFrameCollapseExpandButton", WatchFrame)
WatchFrameLines = CreateFrame("Frame", "WatchFrameLines", WatchFrame)
WatchFrameLines:SetPoint("TOPLEFT", WatchFrame, "TOPLEFT", 0, -30)
WatchFrameLines:SetPoint("BOTTOMRIGHT", WatchFrame, "BOTTOMRIGHT", -24, 12)
local function stockHandler() return 0, 0, 0 end
WATCHFRAME_OBJECTIVEHANDLERS = {stockHandler, stockHandler, stockHandler}
local handlersBefore = {unpack(WATCHFRAME_OBJECTIVEHANDLERS)}

-- The quest log: one ordinary quest and the rift quest, both watched.
local log = {{title = "A Plain Quest", id = 12000}, {title = "Nephalem Rift", id = 910020}}
local watches = {1, 2}
function GetNumQuestLogEntries() return #log end
function GetQuestLogTitle(index)
    local q = log[index]
    if not q then return nil end
    return q.title, 70, nil, 0, false, false, nil, nil, q.id
end
function GetNumQuestWatches() return #watches end
function GetQuestIndexForWatch(i) return watches[i] end
local removedWatches = {}
function RemoveQuestWatch(index)
    for i = #watches, 1, -1 do if watches[i] == index then table.remove(watches, i) end end
    removedWatches[#removedWatches + 1] = index
end
function AddQuestWatch(index)
    for _, w in ipairs(watches) do if w == index then return end end
    watches[#watches + 1] = index
end

-- What the stock update does to the parts this file touches (WatchFrame.lua:352-412):
-- the header says "Objectives (N)" when there are objectives, and hides otherwise. It
-- also records whether a rift quest was among the quests it drew.
local drewRiftQuest = false
function WatchFrame_Update()
    drewRiftQuest = false
    for _, index in ipairs(watches) do if log[index] and log[index].id == 910020 then drewRiftQuest = true end end
    if #watches > 0 then
        WatchFrameHeader:Show(); WatchFrameCollapseExpandButton:Show()
        WatchFrameTitle:SetText("Objectives (" .. #watches .. ")")
    else
        WatchFrameHeader:Hide(); WatchFrameCollapseExpandButton:Hide()
    end
end
function WatchFrame_Collapse(self) self.collapsed = true; WatchFrameLines:Hide() end
function WatchFrame_Expand(self) self.collapsed = nil; WatchFrameLines:Show(); WatchFrame_Update(self) end
-- ElvUI's skin, loaded before us: its own .tex, reset on every collapse and expand.
WatchFrameCollapseExpandButton.tex = WatchFrameCollapseExpandButton:CreateTexture(nil, "OVERLAY")
WatchFrameCollapseExpandButton.tex:SetTexture("ElvUI\\MinusButton")
hooksecurefunc("WatchFrame_Expand", function() WatchFrameCollapseExpandButton.tex:SetTexture("ElvUI\\MinusButton") end)
hooksecurefunc("WatchFrame_Collapse", function() WatchFrameCollapseExpandButton.tex:SetTexture("ElvUI\\PlusButton") end)

----------------------------------------------------------------------------------------------------
-- Load the client half
----------------------------------------------------------------------------------------------------
local sent = {}
local handlers
AIO = {AddAddon = function() return false end,
    AddHandlers = function(_, h) handlers = h; return h end,
    Handle = function(...) sent[#sent + 1] = {...} end}
Diablocraft = {ART_PATH = "Interface\\AddOns\\Torment\\art\\"}
dofile(SOURCE)
local T = assert(DCRiftTracker, "the client half exports DCRiftTracker")
local ui = T.ui
local block = ui.block

-- 1. No floating bar, and the stock handler list untouched (Architect, 2026-10-03).
assert(_G.DiablocraftRiftBar == nil, "the floating DiablocraftRiftBar is gone")
for _, f in ipairs(frames) do
    assert(not (f.parent == UIParent and f.kind == "StatusBar"), "no status bar floats on UIParent")
end
assert(#WATCHFRAME_OBJECTIVEHANDLERS == #handlersBefore, "the stock handler list keeps its length")
for i, fn in ipairs(handlersBefore) do
    assert(WATCHFRAME_OBJECTIVEHANDLERS[i] == fn, "the stock handler list is untouched at " .. i)
end
-- The list is followed by secure post-hooks (the mock owns hooksecurefunc and makes no call
-- count, so prove them by effect): a stock AddQuestWatch on the rift quest is taken off again.
AddQuestWatch(2)
assert(#watches == 1 and watches[1] == 1, "the list is followed by a secure AddQuestWatch post-hook")
assert(type(SlashCmdList.DIABLOCRAFTRIFT) == "function", "/dcrift stays as a refresh")
SlashCmdList.DIABLOCRAFTRIFT()
assert(sent[#sent][1] == "DiablocraftRiftBar" and sent[#sent][2] == "Refresh", "/dcrift asks for a refresh")

-- 2. One entry, not two: the rift quest's watch is taken off at load, and whenever a
-- stock path tracks it again (auto-watch on accept or progress, a shift-click).
assert(#watches == 1 and watches[1] == 1, "the rift quest is no longer watched, the plain quest still is")
WatchFrame_Update()
assert(not drewRiftQuest, "the stock list never draws the rift quest")
AddQuestWatch(1)
assert(#watches == 1 and watches[1] == 1, "an ordinary quest is tracked as before")

-- Helpers to read the entry.
local function lines()
    local out = {}
    for _, w in ipairs(ui.widgets()) do
        out[#out + 1] = {key = w.key, text = w.text:GetText(), alpha = w:GetAlpha(), shown = w:IsShown(),
            box = w.box.texture, flourish = w.flourish:IsShown() and w.flourishText or nil,
            flourishWord = w.flourish.text, flourishFont = w.flourish.font,
            flourishAlpha = w.flourish:GetAlpha(), slash = w.slash:IsShown()}
    end
    return out
end
local function texts()
    local out = {}
    for _, l in ipairs(lines()) do out[#out + 1] = l.text end
    return table.concat(out, " | ")
end
-- The entry's clock is one always-on frame (the refresh ticker), so the fade keeps running
-- even when the list is collapsed or ElvUI hides WatchFrame; the block itself has no OnUpdate.
local tickFrame
for _, f in ipairs(frames) do
    if f.scripts.OnUpdate then tickFrame = tickFrame or f end
end
assert(tickFrame, "an OnUpdate drives the entry's clock")
local function step(seconds, dt)
    dt = dt or 0.05
    local t = 0
    while t < seconds - 1e-9 do tickFrame.scripts.OnUpdate(tickFrame, dt); t = t + dt end
end
local function linesTop()
    for _, p in ipairs(WatchFrameLines.points) do if p[1] == "TOPLEFT" then return p[5] end end
end
local function allText()
    local out = {}
    for _, f in ipairs(frames) do if f.kind == "FontString" and f.text then out[#out + 1] = tostring(f.text) end end
    return table.concat(out, "\n")
end
local ART = "Interface\\AddOns\\Torment\\art\\"

-- 3. Killing minions (open), pushed at login: drawn as it stands, no flourish.
handlers.Update(nil, {run = 7, mode = "nr", state = "open", progress = 300, required = 1200})
assert(block:IsShown(), "the entry shows")
assert(block.parent == WatchFrame, "the entry lives in the quest list, which follows ElvUI's mover")
assert(block.points[1][1] == "TOPLEFT" and block.points[1][2] == WatchFrame and block.points[1][5] == -30,
    "the entry takes the first place in the list, where the stock lines started")
assert(ui.title:GetText() == "Nephalem Rift", "the title")
assert(texts() == T.TEXT.minions, "one objective line: " .. texts())
local l = lines()
assert(l[1].box == ART .. "rift_check_empty" and not l[1].flourish and l[1].alpha == 1, "an empty box, no flourish")
assert(ui.bar:IsShown(), "the ornate bar shows under the line")
local value, target = T.BarValue()
assert(value == 0.25 and target == 0.25, "the first push draws the bar where it stands, got " .. value)
assert(not allText():find("%%") and not allText():find("tier", 1, true), "no percentage and no tier anywhere")
local blockHeight = block:GetHeight()
assert(blockHeight and blockHeight > 0, "the entry has a height")
assert(linesTop() == -30 - blockHeight * T.SCALE - 10, "the stock lines start under the entry, got " .. tostring(linesTop()))

-- The header: D3's "OBJECTIVES" as real Exocet text, over ElvUI's skin, even with no
-- other objective (diablocraft-rift-tracker-exocet-slider).
WatchFrame_Update()
local headerWord
for _, f in ipairs(frames) do
    if f.kind == "FontString" and f.parent == WatchFrameHeader and f.text == T.TEXT.objectives then
        headerWord = f
    end
end
assert(headerWord, "the header word is a font string")
-- diablocraft-scog: this word is created with no template, and styleHeader sets its font
-- before its text; the shared mock enforces the client's "Font not set" rule, so swapping
-- the two lines in styleHeader fails this file (diablocraft-s5kn).
assert(headerWord.font, "the header word takes its font before its text")
assert(headerWord:IsShown() and headerWord.font == T.FONT and headerWord.fontSize == T.WORD_FONT,
    "the header draws OBJECTIVES in the shipped Exocet at the default size, got " .. tostring(headerWord.font))
assert(WatchFrameTitle.text == "", "the stock title does not draw over it")
watches = {}
WatchFrame_Update()
assert(WatchFrameHeader:IsShown() and WatchFrameCollapseExpandButton:IsShown(), "the entry alone keeps the header up")
assert(WatchFrameCollapseExpandButton.tex.texture == ART .. "rift_minimise", "the red minimise button, over ElvUI's skin")
watches = {1}

-- The fill eases to a new value; it never jumps.
handlers.Update(nil, {run = 7, mode = "nr", state = "open", progress = 600, required = 1200})
value, target = T.BarValue()
assert(target == 0.5 and value == 0.25, "a push sets the target, the fill has not moved yet")
step(0.05)
value = T.BarValue()
assert(value > 0.25 and value < 0.5, "one frame later it is on its way, got " .. value)
step(2)
value = T.BarValue()
assert(value == 0.5, "and it arrives, got " .. value)

-- Moves, collapses and re-lays-out with the list.
WatchFrame_Collapse(WatchFrame)
assert(not block:IsShown(), "collapsing the list hides the entry")
assert(WatchFrameCollapseExpandButton.tex.texture == ART .. "rift_minimise", "the button keeps our look after ElvUI's collapse hook")
WatchFrame_Expand(WatchFrame)
assert(block:IsShown(), "expanding shows it again")

-- 4. Guardian summoned: the bar goes at once, the minions line is crossed with COMPLETE!,
-- the Guardian line arrives with NEW!.
handlers.Update(nil, {run = 7, mode = "nr", state = "guardian", progress = 1200, required = 1200})
assert(not ui.bar:IsShown(), "the bar goes the moment the Guardian appears")
l = lines()
assert(#l == 2 and l[1].key == "minions" and l[2].key == "guardian", "minions then guardian: " .. texts())
assert(l[1].flourish == "COMPLETE!" and l[1].slash, "the minions line: COMPLETE! and the X slashing in")
assert(l[1].flourishWord == "COMPLETE!" and l[1].flourishFont == T.FONT,
    "the COMPLETE! word is real Exocet text, got " .. tostring(l[1].flourishWord))
assert(l[2].flourish == "NEW!" and l[2].alpha == 0, "the Guardian line: NEW!, fading in from nothing")
assert(l[2].flourishWord == "NEW!" and l[2].flourishFont == T.FONT, "the NEW! word is real Exocet text")
step(0.3)
l = lines()
assert(l[1].flourishAlpha == 1 and l[2].alpha > 0 and l[2].alpha < 1, "the flourish has slid in; the new line is fading in")
step(0.4)
l = lines()
assert(not l[1].slash and l[1].box == ART .. "rift_check_crossed", "after 0.6 s the X has landed: a crossed box")
step(0.2)
assert(lines()[2].alpha == 1, "the new line is fully in after 0.8 s")
local heightWithTwo = block:GetHeight()
-- 5. Settling: the crossed line fades after 3.3 s and goes 0.65 s later; the list closes up.
step(2.4) -- t = 3.3
l = lines()
assert(#l == 2 and l[1].alpha == 1, "still there at 3.3 s")
step(0.3)
assert(lines()[1].alpha < 1, "fading after 3.3 s")
step(0.4)
l = lines()
assert(#l == 1 and l[1].key == "guardian", "gone after 3.95 s, leaving the Guardian line: " .. texts())
assert(block:GetHeight() < heightWithTwo and linesTop() == -30 - block:GetHeight() * T.SCALE - 10, "the list closes up under the entry")

-- 6. Guardian dead: crossed with COMPLETE!, the Keeper line with UPDATE!, then settled.
handlers.Update(nil, {run = 7, mode = "nr", state = "complete", progress = 1200, required = 1200})
l = lines()
assert(#l == 2 and l[1].flourish == "COMPLETE!" and l[2].key == "keeper" and l[2].flourish == "UPDATE!",
    "Guardian crossed with COMPLETE!, the Keeper line with UPDATE!: " .. texts())
assert(l[2].flourishWord == "UPDATE!" and l[2].flourishFont == T.FONT, "the UPDATE! word is real Exocet text")
assert(l[2].text == "Speak to the Rift Keeper in town", "the Keeper line's words")
step(5)
l = lines()
assert(#l == 1 and l[1].key == "keeper" and l[1].alpha == 1 and not l[1].flourish,
    "settled: only the Keeper line, its flourish faded: " .. texts())
assert(not ui.bar:IsShown(), "no bar after the Guardian")

-- 7. Turned in (card q-1004-19): the OBJECTIVES part - the block and the header word - is
-- still up at the turn-in, fades out about 5 s later, then leaves; a new rift shows it again.
assert(headerWord:IsShown(), "the OBJECTIVES word is up before the turn-in")
handlers.Hide()
assert(block:IsShown() and #lines() == 1 and block:GetAlpha() == 1, "the entry is still up at the turn-in")
assert(headerWord:IsShown() and headerWord:GetAlpha() == 1, "so is the OBJECTIVES word")
step(4.3)
assert(block:IsShown() and block:GetAlpha() == 1, "still whole 4.3 s after the turn-in, got " .. block:GetAlpha())
assert(headerWord:GetAlpha() == 1, "the word too, got " .. headerWord:GetAlpha())
step(0.35)
assert(block:IsShown() and block:GetAlpha() < 1 and block:GetAlpha() > 0, "fading at 4.65 s, got " .. block:GetAlpha())
assert(headerWord:GetAlpha() < 1, "the word fades with the block")
step(0.5)
assert(not block:IsShown() and #lines() == 0, "gone just after 5 s")
assert(not headerWord:IsShown(), "the OBJECTIVES word is gone with the block, not left orphaned")
assert(linesTop() == -30, "WatchFrameLines is back at its XML anchor")
assert(WatchFrameTitle:GetText() == "Objectives (1)", "the stock title is back, got " .. tostring(WatchFrameTitle:GetText()))
assert(WatchFrameHeader:IsShown() and WatchFrameCollapseExpandButton:IsShown(),
    "the stock header and button serve the stock objective again")

-- A new rift draws the whole part again: the fade never leaves it stuck.
handlers.Update(nil, {run = 20, mode = "nr", state = "open", progress = 0, required = 1200})
assert(block:IsShown() and block:GetAlpha() == 1 and headerWord:IsShown() and headerWord:GetAlpha() == 1,
    "a new rift draws the block and the word at full alpha again")
handlers.Hide()
step(5)
assert(not block:IsShown() and not headerWord:IsShown(), "and it fades out the same way")

-- 8. A reload or a late join mid-run: the state as it stands, nothing replayed.
handlers.Update(nil, {run = 9, mode = "nr", state = "complete", progress = 1200, required = 1200})
l = lines()
assert(#l == 1 and l[1].key == "keeper" and l[1].alpha == 1 and not l[1].flourish and not l[1].slash,
    "restored at complete: the Keeper line alone, no flourish, no fade: " .. texts())
handlers.Hide()
handlers.Update(nil, {run = 10, mode = "nr", state = "guardian", progress = 1200, required = 1200})
l = lines()
assert(#l == 1 and l[1].key == "guardian" and not l[1].flourish and not ui.bar:IsShown(),
    "restored at guardian: the Guardian line alone: " .. texts())
-- A new run id is a new run: drawn as it stands, even without a Hide between.
handlers.Update(nil, {run = 11, mode = "nr", state = "open", progress = 120, required = 1200})
l = lines()
assert(#l == 1 and l[1].key == "minions" and not l[1].flourish and ui.bar:IsShown() and T.BarValue() == 0.1,
    "a new run starts settled: " .. texts())

-- A step the client never saw (open straight to complete) still crosses both lines.
handlers.Update(nil, {run = 11, mode = "nr", state = "complete", progress = 1200, required = 1200})
l = lines()
assert(#l == 3 and l[1].flourish == "COMPLETE!" and l[2].flourish == "COMPLETE!" and l[3].flourish == "UPDATE!",
    "open to complete: minions and Guardian crossed, Keeper updated: " .. texts())
step(5)
assert(#lines() == 1 and lines()[1].key == "keeper", "and it settles the same way")

-- An unknown mode or state shows nothing rather than a wrong entry.
handlers.Update(nil, {run = 12, mode = "xx", state = "open", progress = 1, required = 10})
assert(not block:IsShown(), "a mode with no view shows nothing")
handlers.Update(nil, {run = 12, mode = "nr", state = "bogus", progress = 1, required = 10})
assert(not block:IsShown(), "a state with no step shows nothing")

-- 8b. The Greater Rift view (diablocraft-g5dh; greater-rift-tracker.md): the Nephalem look,
-- the level in the title, the server's seconds as an M:SS clock on the title line, D3's bonus
-- line, and beaten or failed at the end.
local clock = ui.clock
local function red() local c = clock.textColor; return c and c[1] == 1 and c[2] < 1 end
handlers.Update(nil, {run = 30, mode = "gr", state = "open", progress = 300, required = 1200,
    rank = 25, outcome = "pending", left = 900})
assert(block:IsShown() and ui.title:GetText() == "Greater Rift Level 25", "the title carries the level, got "
    .. tostring(ui.title:GetText()))
assert(clock:IsShown() and clock:GetText() == "15:00" and not red(), "the clock starts at the server's 15:00, got "
    .. tostring(clock:GetText()))
assert(texts() == T.TEXT.grMinions .. " | " .. T.TEXT.bonus, "minions, then D3's bonus line: " .. texts())
assert(ui.bar:IsShown() and T.BarValue() == 0.25, "the same bar, filled to progress")
step(0.5)
assert(clock:GetText() == "15:00", "half a second in it still reads 15:00, got " .. clock:GetText())
step(1)
assert(clock:GetText() == "14:59", "the clock runs between pushes, got " .. clock:GetText())
handlers.Update(nil, {run = 30, mode = "gr", state = "open", progress = 600, required = 1200,
    rank = 25, outcome = "pending", left = 600})
assert(clock:GetText() == "10:00", "every push sets the server's seconds, got " .. clock:GetText())
-- Guardian up: the bar stays, full; the Guardian line arrives above the bonus line.
handlers.Update(nil, {run = 30, mode = "gr", state = "guardian", progress = 1200, required = 1200,
    rank = 25, outcome = "pending", left = 590})
l = lines()
assert(#l == 3 and l[1].key == "minions" and l[1].flourish == "COMPLETE!" and l[2].key == "guardian"
    and l[2].flourish == "NEW!" and l[3].key == "bonus", "minions crossed, Guardian new, bonus kept: " .. texts())
assert(ui.bar:IsShown(), "the Greater Rift bar stays up while the Guardian is")
-- The clock runs out with the Guardian alive: 0:00 in red, then the server's expired.
handlers.Update(nil, {run = 30, mode = "gr", state = "guardian", progress = 1200, required = 1200,
    rank = 25, outcome = "pending", left = 1})
step(1.5)
assert(clock:GetText() == "0:00" and red(), "0:00, in red, got " .. clock:GetText())
step(1)
assert(clock:GetText() == "0:00", "and it stops there")
handlers.Update(nil, {run = 30, mode = "gr", state = "guardian", progress = 1200, required = 1200,
    rank = 25, outcome = "expired", left = 0})
l = lines()
assert(l[#l].key == "bonus" and l[#l].text == T.TEXT.failed and l[#l].box == ART .. "rift_check_empty",
    "failed: the bonus line says so, uncrossed: " .. texts())
-- The Guardian dies late: crossed, and no Keeper line, the quest is failed (q-1006-02).
handlers.Update(nil, {run = 30, mode = "gr", state = "complete", progress = 1200, required = 1200,
    rank = 25, outcome = "expired", left = 0})
step(5)
assert(texts() == T.TEXT.failed, "a failed run ends on the failed line alone, no Keeper: " .. texts())
assert(not ui.bar:IsShown() and clock:GetText() == "0:00" and red(), "no bar, the clock at a red 0:00")

-- Beaten: the bonus line is crossed with COMPLETE!, the Keeper line comes, the clock stops on
-- the time left.
handlers.Update(nil, {run = 31, mode = "gr", state = "guardian", progress = 1200, required = 1200,
    rank = 40, outcome = "pending", left = 320})
handlers.Update(nil, {run = 31, mode = "gr", state = "complete", progress = 1200, required = 1200,
    rank = 40, outcome = "success", left = 312})
l = lines()
assert(#l == 3 and l[1].key == "guardian" and l[1].flourish == "COMPLETE!" and l[2].key == "keeper"
    and l[2].flourish == "UPDATE!" and l[3].key == "bonus" and l[3].flourish == "COMPLETE!",
    "beaten: Guardian and bonus crossed, the Keeper line new: " .. texts())
assert(l[2].text == T.TEXT.grKeeper, "the Keeper line's words")
assert(clock:GetText() == "5:12" and not red(), "the clock shows the time left, got " .. clock:GetText())
step(5)
assert(texts() == T.TEXT.grKeeper, "settled on the Keeper line: " .. texts())
assert(clock:GetText() == "5:12", "the clock stays stopped")
step(5)
assert(texts() == T.TEXT.grKeeper, "a crossed bonus line never comes back on the next push")
handlers.Update(nil, {run = 31, mode = "gr", state = "complete", progress = 1200, required = 1200,
    rank = 40, outcome = "success", left = 312})
assert(texts() == T.TEXT.grKeeper, "nor on a repeat push: " .. texts())

-- A reload mid-run draws it as it stands.
handlers.Update(nil, {run = 32, mode = "gr", state = "complete", progress = 1200, required = 1200,
    rank = 40, outcome = "expired", left = 0})
assert(texts() == T.TEXT.failed and not lines()[1].flourish, "restored failed: the failed line, no flourish")
handlers.Update(nil, {run = 33, mode = "gr", state = "open", progress = 0, required = 1200,
    rank = 2, outcome = "pending"})
assert(not clock:IsShown(), "no deadline yet, no clock")
-- A Nephalem Rift draws no clock.
handlers.Update(nil, {run = 34, mode = "nr", state = "open", progress = 0, required = 1200})
assert(not clock:IsShown() and ui.title:GetText() == "Nephalem Rift", "a Nephalem Rift has no clock")

-- 8c. The floor line (rift floors Part F6): the floor the player stands on, right-aligned
-- under the bar; a push with no floor (a member in town) shows none.
local floorLabel = ui.floorLabel
handlers.Update(nil, {run = 40, mode = "nr", state = "open", progress = 300, required = 1200, floor = 2})
assert(floorLabel:IsShown() and floorLabel:GetText() == "Floor 2",
    "the tracker names the floor the player stands on, got " .. tostring(floorLabel:GetText()))
assert(ui.bar:IsShown(), "the bar is up, the floor line under it")
assert(floorLabel.points[1][1] == "TOPRIGHT" and floorLabel.points[1][2] == block,
    "the floor line is right-aligned on the entry, under the bar's right end")
assert(block:GetHeight() > 0 and linesTop() == -30 - block:GetHeight() * T.SCALE - 10,
    "the floor line makes the entry taller and the stock lines follow it")
-- A member in town: the server sends no floor, so no floor line.
handlers.Update(nil, {run = 40, mode = "nr", state = "open", progress = 600, required = 1200})
assert(not floorLabel:IsShown(), "a member in town (no floor) shows no floor line")
handlers.Update(nil, {run = 40, mode = "nr", state = "open", progress = 600, required = 1200, floor = 3})
assert(floorLabel:IsShown() and floorLabel:GetText() == "Floor 3", "a deeper floor is named too")

-- 9. The refresh follows the quest, in town too: holding a rift quest asks the server.
local before = #sent
local events
for _, f in ipairs(frames) do if f.events.QUEST_LOG_UPDATE then events = f end end
assert(events, "the client listens to the quest log")
log = {{title = "A Plain Quest", id = 12000}}
events.scripts.OnEvent(events, "QUEST_LOG_UPDATE")
log = {{title = "A Plain Quest", id = 12000}, {title = "Nephalem Rift", id = 910020}}
events.scripts.OnEvent(events, "QUEST_LOG_UPDATE")
assert(#sent > before and sent[#sent][2] == "Refresh", "taking the rift quest asks for the run, wherever the player is")

-- 10. Every texture the entry names exists: the PNG source in the kit and the BLP the
-- client reads (the 3.3.5a client reads no PNG; build_ui_art.py converts them).
for key, name in pairs(T.ART) do
    for _, path in ipairs({"client-patch/art/ui/rift/" .. name .. ".png", "client-patch/addons/Torment/art/" .. name .. ".blp"}) do
        local file = io.open(path, "rb")
        assert(file, "art " .. key .. " is missing: " .. path)
        file:close()
    end
end

-- 11. The whole tracker draws 25% bigger by default (ruling 2026-10-04, q-1003-44): one scale
-- on the block carries the lines, the box and its X, the bar and the COMPLETE!/NEW!/UPDATE!
-- words; the OBJECTIVES header is the stock list header, not a child of the block, so its
-- word takes the same factor where it is drawn (styleHeader). The stock lines follow in
-- frame units. The factor is ElvUI's saved E.db.torment.objectiveScale now
-- (diablocraft-rift-tracker-exocet-slider), 1.25 until the designer sets another.
assert(T.SCALE == 1.25 and block:GetScale() == 1.25, "the tracker draws at its 1.25 default")
assert(headerWord.fontSize == T.WORD_FONT,
    "the OBJECTIVES word draws at the default size, got " .. tostring(headerWord.fontSize))

-- The slider writes E.db.torment.objectiveScale and ElvUI_Torment:Apply hands it over
-- through T.SetScale; ElvUI's mover and its Nudge own WatchFrame itself, so only our own
-- block may be scaled, never the list.
handlers.Update(nil, {run = 13, mode = "nr", state = "open", progress = 600, required = 1200})
local listPoints, listScale = #WatchFrame.points, WatchFrame:GetScale()
T.SetScale(1.6)
assert(block:GetScale() == 1.6 and T.SCALE == 1.6, "the slider's factor lands on the block")
assert(headerWord.fontSize == T.WORD_FONT * 1.6 / 1.25, "the OBJECTIVES word takes the same factor")
assert(linesTop() == -30 - block:GetHeight() * 1.6 - 10, "the stock lines follow it, got " .. tostring(linesTop()))
assert(#WatchFrame.points == listPoints and WatchFrame:GetScale() == listScale,
    "the mover's own list is untouched: the slider scales the entry, never WatchFrame")
T.SetScale(1.25)
assert(block:GetScale() == 1.25 and headerWord.fontSize == T.WORD_FONT, "back to the default")
T.SetScale(nil)
T.SetScale(-1)
T.SetScale("nonsense")
assert(block:GetScale() == 1.25, "a nonsense value is ignored")

-- A profile that has never saved the key, or a client without ElvUI, keeps the default:
-- the load path reads E.db.torment itself (see the reload at the end of this file).
assert(T.FONT == "Interface\\AddOns\\Torment\\fonts\\Exocet.ttf", "the tracker names the shipped font")
local fontFile = io.open("client-patch/addons/Torment/fonts/Exocet.ttf", "rb")
assert(fontFile, "the one Exocet copy ships with the addon")
fontFile:close()
-- The four baked word textures are retired, not just unused: the Lua names none of them.
for _, retired in ipairs({"header", "flourishComplete", "flourishNew", "flourishUpdate"}) do
    assert(T.ART[retired] == nil, "the retired baked word is out of ART: " .. retired)
end

-- 12. The gold fill and the channel must cover the hole the bar art cuts out, or the game
-- shows through (the designer: the fill stopped 2-3 px short at the top and at the bottom). The art's
-- own TROUGH is the authority: draw_rift_art.py cuts the hole at x0,y0,x1,y1 (rectangle, both
-- ends included), and the fill must reach 1 px past the far end to tuck under the rail.
local artScript = assert(io.open("client-patch/art/ui/rift/draw_rift_art.py"), "the bar art script is readable")
local artSource = artScript:read("*a")
artScript:close()
local ax0, ay0, ax1, ay1 = artSource:match("TROUGH%s*=%s*%(%s*(%d+)%s*,%s*(%d+)%s*,%s*(%d+)%s*,%s*(%d+)%s*%)")
assert(ax0, "draw_rift_art.py still cuts the channel as TROUGH = (x0, y0, x1, y1)")
ax0, ay0, ax1, ay1 = tonumber(ax0), tonumber(ay0), tonumber(ax1), tonumber(ay1)
local box = assert(T.BarBox, "the client half exports the fill's box (T.BarBox)")
assert(box.x <= ax0 and box.y <= ay0 and box.x + box.w >= ax1 + 1 and box.y + box.h >= ay1 + 1,
    ("the fill and the channel must cover the art's hole to the rail: box %d,%d %dx%d vs hole %d,%d-%d,%d")
    :format(box.x, box.y, box.w, box.h, ax0, ay0, ax1, ay1))

-- 13. A login reads ElvUI's saved factor itself, because the AIO script can land after
-- ElvUI_Torment's own apply pass already ran; a profile that never saved it keeps 1.25.
-- This reloads the client half, so it comes last.
local function reloadWith(saved)
    ElvUI = saved and {[1] = {db = {torment = {objectiveScale = saved}}}} or nil
    dofile(SOURCE)
    return assert(DCRiftTracker, "the reloaded client half exports DCRiftTracker")
end
local restored = reloadWith(1.45)
assert(restored.SCALE == 1.45 and restored.ui.block:GetScale() == 1.45,
    "a login draws the saved factor, got " .. tostring(restored.SCALE))
assert(reloadWith(nil).SCALE == 1.25, "a profile with no saved factor keeps the 1.25 default")
assert(reloadWith(0).SCALE == 1.25, "a nonsense saved value keeps the 1.25 default")

print("PASS rift tracker client: in the quest list on top, no floating bar, stock handlers untouched, the rift quest's "
    .. "own lines off, OBJECTIVES and the flourishes as real Exocet text, the Objective Frame scale slider "
    .. "(default, push, mover left alone) and the saved value read at login, bar eases, collapse, the guardian and "
    .. "complete sequences with their flourishes and fades, the OBJECTIVES part fading out about 5 s after the turn-in, "
    .. "restore without replay, the floor line, the fill covering the art's channel; the Greater Rift view: level, clock, bonus line, "
    .. "beaten and failed")
