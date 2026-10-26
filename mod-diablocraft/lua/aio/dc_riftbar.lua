-- luacheck: globals DCThrottle DCRiftTracker Diablocraft ElvUI WatchFrame WatchFrameLines WatchFrameHeader
-- luacheck: globals WatchFrameTitle
-- luacheck: globals WatchFrameCollapseExpandButton WATCHFRAME_TYPE_OFFSET GetQuestLogTitle GetNumQuestLogEntries WatchFrame_Update
-- luacheck: globals STANDARD_TEXT_FONT GetNumQuestWatches GetQuestIndexForWatch RemoveQuestWatch
--[[
World of DiabloCraft - the rift tracker in the quest list (09-rifts §2 step 3).

D3 shows a running rift as an entry at the top of its Objectives list, not as
a floating bar. This file draws that entry inside the stock quest list
(WatchFrame) - which is also the list ElvUI 6.09 moves and skins - so the entry
moves, collapses and re-lays-out with the list. The floating DiablocraftRiftBar
is gone; /dcrift stays as a refresh.

Authority, in order: a D3 run capture (alex-d3-nephalem-rift.mp4 and its frame
sheet), the mockup for layout only. Contract: docs/contracts/rift-tracker-messages.md.

The C++ module owns dc_rift and dc_rift_member; this file only reads them and
pushes the run. Progress is 7.3's units (20 per kill, required_units = 20 x
kills); the bar shows the fraction and NO number, as D3 does.
]]

-- The rift quests, one per mode since S3's rifts_0019: Nephalem 910020, Greater 910023.
-- Both halves read this one set: the client hides their stock N/M lines, the server
-- pre-checks it so a player in no run costs no query.
local QUESTS = {[910020] = true, [910023] = true}

local AIO = AIO or require("AIO")
local CHANNEL = "DiablocraftRiftBar"

if AIO.AddAddon() then
    -- ================= server =================
    local handlers = AIO.AddHandlers(CHANNEL, {})

    -- The run a player sees is found through their own enrolment and quest, never the
    -- instance they stand in: a member in town keeps the entry until the run closes.
    -- Newest live run first, as dc_rift_quests.cpp EnrolledRun
    -- reads it; `offline` counts there too, though a pushing player is online.
    -- A Greater Rift adds its level, its result and the seconds left on the shared clock, read
    -- from the server's own clock in this query (greater-rift-tracker.md); -1 = no deadline yet.
    local RUN_QUERY = "SELECT r.id, r.mode, r.state, r.progress, r.required_units, m.quest_id, "
        .. "IF(r.closing_at IS NULL, 0, 1), IFNULL(r.gr_rank, 0), r.outcome, IFNULL(r.time_left, 0), "
        .. "IF(r.deadline IS NULL, -1, GREATEST(0, UNIX_TIMESTAMP(r.deadline) - UNIX_TIMESTAMP(NOW()))) "
        .. "FROM dc_rift_member m JOIN dc_rift r ON r.id=m.run_id "
        .. "WHERE m.player_guid=%d AND m.state IN ('enrolled','offline') AND r.state<>'closed' "
        .. "ORDER BY m.run_id DESC LIMIT 1"

    -- The floor the player stands on, for the tracker's "Floor N" (rift floors Part F6): the
    -- run's dc_rift_floor row whose instance and map they are in. In town (GetInstanceId() 0)
    -- there is none and the row carries no floor.
    local FLOOR_QUERY = "SELECT f.floor FROM dc_rift_floor f WHERE f.run_id=%d AND f.instance_id=%d "
        .. "AND f.map_id=%d AND f.closed_at IS NULL ORDER BY f.floor DESC LIMIT 1"

    -- The pushed row for this player, or nil when they see nothing: no live enrolment,
    -- the run is closing (someone turned in, which pays every holder at once), or they
    -- no longer hold the run's quest (a member who abandoned it, or was stripped of it).
    local function runFor(player)
        local row = CharDBQuery(RUN_QUERY:format(player:GetGUIDLow()))
        if not row then return nil end
        if row:GetUInt32(6) ~= 0 then return nil end
        if not player:HasQuest(row:GetUInt32(5)) then return nil end
        local run = {
            run = row:GetUInt32(0),
            mode = row:GetString(1),
            state = row:GetString(2),
            progress = row:GetUInt32(3),
            required = row:GetUInt32(4),
        }
        if run.mode == "gr" then
            run.rank = row:GetUInt32(7)
            run.outcome = row:GetString(8)
            -- Seconds on the clock: counting down while the result is pending, then final
            -- (time_left: the beaten run's seconds, 0 for a failed one). nil = not started.
            local left = run.outcome == "pending" and row:GetInt32(10) or row:GetUInt32(9)
            if left >= 0 then run.left = left end
        end
        -- The floor the player stands on (rift floors Part F6), or none in town.
        local instance = player:GetInstanceId()
        if instance and instance > 0 then
            local floor = CharDBQuery(FLOOR_QUERY:format(run.run, instance, player:GetMapId()))
            if floor then run.floor = floor:GetUInt32(0) end
        end
        return run
    end

    -- A player holding none of the run quests sees nothing whatever they are enrolled
    -- in; testing the held quests first keeps the per-kill push of a player in no run
    -- from touching the database at all.
    local function holdsRiftQuest(player)
        for questId in pairs(QUESTS) do
            if player:HasQuest(questId) then return true end
        end
        return false
    end

    local function push(player)
        if not player then return end
        if not holdsRiftQuest(player) then
            AIO.Handle(player, CHANNEL, "Hide")
            return
        end
        local run = runFor(player)
        if run then
            AIO.Handle(player, CHANNEL, "Update", run)
        else
            AIO.Handle(player, CHANNEL, "Hide")
        end
    end

    -- Security G1: push() queries the DB; drop a flood.
    function handlers.Refresh(player)
        if DCThrottle.Allow(player, "riftbar:refresh", 5, 10) then push(player) end
    end

    RegisterPlayerEvent(3, function(_, player) push(player) end)            -- login
    RegisterPlayerEvent(28, function(_, player) push(player) end)           -- map change
    RegisterPlayerEvent(7, function(_, killer) push(killer) end)            -- creature kill

    AIO.AddOnInit(function(_, player) push(player) end)
    return
end

-- ================= client =================
local handlers = AIO.AddHandlers(CHANNEL, {})

local T = {}
DCRiftTracker = T

-- Every string the entry shows (one table, also in the contract doc). The words
-- are real font strings in D3's Exocet, not the baked textures draw_rift_art.py used to paint: Exocet's own
-- O is the circled cross the header once drew as a separate icon, and its J descends.
local TEXT = {
    nephalem = "Nephalem Rift",
    minions = "Kill the Nephalem Rift Guardian's minions",
    guardian = "Kill the Nephalem Rift Guardian",
    keeper = "Speak to the Rift Keeper in town",
    complete = "COMPLETE!",
    new = "NEW!",
    update = "UPDATE!",
    objectives = "OBJECTIVES",
    -- The Greater Rift view: D3's own lines from a D3 Greater Rift run capture
    -- (alex-d3-reference.md), the Keeper kept for Urshi, the failed line
    -- in the server's own chat words (greater-rift-tracker.md).
    greater = "Greater Rift Level %d",
    grMinions = "Kill the Rift Guardian's minions",
    grGuardian = "Kill the Rift Guardian",
    grKeeper = "Speak to the Rift Keeper and claim your reward",
    bonus = "Bonus: Kill the Rift Guardian before the timer ends to successfully complete the Rift.",
    failed = "The Greater Rift timer has run out. This Greater Rift can no longer be beaten.",
    -- The floor the player stands on (rift floors Part F6), drawn under the bar.
    floor = "Floor %d",
}
T.TEXT = TEXT

-- Measured from a D3 Nephalem Rift run capture at 10 fps (alex-d3-nephalem-rift.mp4):
--   slash        the gold X lands on the box in 0.6 s (37.8-38.4 s, 41.7-42.3 s)
--   flourishIn   a flourish slides in from the left in 0.2-0.3 s (37.8-38.0 s)
--   flourishHold it holds 3.3-3.6 s (UPDATE! 42.6-46.2 s), then
--   flourishOut  fades in about 0.5 s (46.2-46.7 s); a newer one on the line replaces it
--   lineIn       a new line fades in over 0.7-0.9 s (38.8-39.5 s, 42.7-43.5 s)
--   doneHold     a crossed-off line starts fading 3.3 s after its X (37.8 -> 41.1 s, 41.7 -> 45.0 s)
--   doneOut      and is gone 0.6-0.7 s later (41.1-41.7 s, 45.0-45.7 s); the list closes up in one step
local TIMING = {slash = 0.6, flourishIn = 0.25, flourishHold = 3.4, flourishOut = 0.5,
    lineIn = 0.8, doneHold = 3.3, doneOut = 0.65, fillEase = 6}
-- The whole OBJECTIVES part - the block and the header word - lingers after the rift quest
-- is turned in, then fades: hideHold of hold and doneOut of fade, so it is gone about 5 s
-- after the turn-in. Nothing else about the entry changes.
TIMING.hideHold = 5 - TIMING.doneOut
T.TIMING = TIMING

-- Their stock N/M lines never show; the entry is the run (the set is at the top).
T.QUESTS = QUESTS

-- The views, one per dc_rift.mode. Each objective shows from the state named in
-- `from`, is crossed off from `done` (or when the run's outcome is `doneOn`), and arrives
-- with its own flourish; `beatenOnly` lines never show on a failed run, and `failed` is a
-- line's words once the run has failed. `bar` holds the states the progress bar shows in;
-- `clock` draws the run's countdown on the title line. The lines keep this order on screen.
-- The Greater Rift view wears the Nephalem look until full-size D3 shots set its own
-- (purple fill, skull, timer line, hourglass).
local ORDER = {open = 1, guardian = 2, complete = 3}
local VIEWS = {
    nr = {
        title = TEXT.nephalem,
        bar = {open = true},
        objectives = {
            {key = "minions", text = TEXT.minions, from = 1, done = 2},
            {key = "guardian", text = TEXT.guardian, from = 2, done = 3, flourish = TEXT.new},
            {key = "keeper", text = TEXT.keeper, from = 3, flourish = TEXT.update},
        },
    },
    gr = {
        title = TEXT.greater,
        -- D3 keeps the bar, full, beside the bonus line while the Guardian is up.
        bar = {open = true, guardian = true},
        clock = true,
        objectives = {
            {key = "minions", text = TEXT.grMinions, from = 1, done = 2},
            {key = "guardian", text = TEXT.grGuardian, from = 2, done = 3, flourish = TEXT.new},
            {key = "keeper", text = TEXT.grKeeper, from = 3, flourish = TEXT.update, beatenOnly = true},
            {key = "bonus", text = TEXT.bonus, from = 1, doneOn = "success", failed = TEXT.failed},
        },
    },
}
T.VIEWS = VIEWS

-- Art: the Torment addon's art folder (client-patch/art/ui/rift, built to BLP by
-- build_ui_art.py). Pieces are drawn at 2x and cropped by texcoord.
local ART = {
    barFrame = "rift_bar_frame", barFill = "rift_bar_fill", barEdge = "rift_bar_edge",
    boxEmpty = "rift_check_empty", boxCrossed = "rift_check_crossed", slash = "rift_slash",
    minimise = "rift_minimise", streak = "rift_flourish_streak",
}
T.ART = ART
local function artPath(name)
    local base = Diablocraft and Diablocraft.ART_PATH or "Interface\\AddOns\\Torment\\art\\"
    return base .. name
end

-- The words are the Torment addon's Exocet (build_tooltip_fonts.py converts Blizzard's
-- OTFs to TrueType), one shipped copy, the tooltip reskin's own file. A font the client
-- cannot load leaves a FontString with no font at all, which draws nothing, so it is
-- probed once as dc_tooltip.lua does and the stock font stands in.
local FONT_PATH = "Interface\\AddOns\\Torment\\fonts\\Exocet.ttf"
T.FONT = FONT_PATH
-- The Exocet em both words draw at: the old bakes trimmed each word to 16 px (flourishes)
-- and 15 px (header) inside a 36 px em, which lands both at a 12 px em under the tracker's
-- 1.25 default. The flourishes are children of the block, so its scale carries them; the
-- header word belongs to the stock list header and takes the factor where it is drawn.
local WORD_FONT, HEADER_FONT = 12, 12
T.WORD_FONT = WORD_FONT
-- Their look, from the art's own palettes (draw_rift_art.py): the flourishes gold, the
-- header pale, the shadow standing in for the glow the baked words carried.
local WORD_COLOR, WORD_GLOW = {250 / 255, 208 / 255, 108 / 255}, {255 / 255, 168 / 255, 36 / 255}
local HEAD_COLOR, HEAD_GLOW = {222 / 255, 220 / 255, 212 / 255}, {200 / 255, 200 / 255, 200 / 255}
local fontUsable
local function wordFont()
    if fontUsable == nil then
        local probe = UIParent:CreateFontString()
        probe:SetFont(FONT_PATH, WORD_FONT, "")
        fontUsable = (probe.GetFont and probe:GetFont() ~= nil) and true or false
    end
    return fontUsable and FONT_PATH or STANDARD_TEXT_FONT
end

-- Geometry, in the list's own units: WatchFrameLines sits at (0,-30) of the 204 px
-- WatchFrame and is 180 px wide (WatchFrame.xml); the bar spans the whole frame.
local LINES_TOP = -30
-- The box art is a 16 px square with the 10 px box in its middle, so D3's X can run past it.
local WIDTH, LINE_X, TEXT_X, BOX = 180, 8, 22, 16
local LINE_HEIGHT = 16
-- The bar art (draw_rift_art.py): 200x44 on screen, 2x in a 512x128 canvas. The frame cuts
-- its channel out at x 18-182, y 12-32 (the art's own TROUGH); the fill and the channel run
-- past it on every side and tuck under the rail, so the gold meets the rail and no game shows
-- between them (the fill used to stop 2-3 px short at the top and
-- bottom). test_rift_tracker_client.lua reads the art's TROUGH and holds this box to it.
local BAR_WIDTH, BAR_HEIGHT = 200, 44
local TROUGH_X, TROUGH_Y, TROUGH_W, TROUGH_H = 16, 11, 168, 22
T.BarBox = {x = TROUGH_X, y = TROUGH_Y, w = TROUGH_W, h = TROUGH_H}
-- The whole tracker draws 25% bigger by default: one scale on
-- the block carries the lines, the box and its X, the bar and the COMPLETE!/NEW!/UPDATE!
-- words with it. The OBJECTIVES header is the stock list header, not a child of the block,
-- so its word takes the same factor where it is drawn (styleHeader). The scale is a slider
-- in Torment's ElvUI options (E.db.torment.objectiveScale) and reaches the block
-- through T.SetScale below; this is its default.
local SCALE = 1.25
local SLASH_START = 5
local FLOURISH_SLIDE = 40
-- ElvUI's saved value (the slider in Torment's options, E.db.torment.objectiveScale), read
-- at load; the slider pushes later changes in through T.SetScale. A client without ElvUI,
-- or one whose script lands before the options have ever applied, keeps the 1.25 default.
local function savedScale()
    local E = ElvUI and ElvUI[1]
    local db = E and E.db and E.db.torment
    local value = db and tonumber(db.objectiveScale)
    if value and value > 0 then return value end
    return SCALE
end
local scale = savedScale()
T.SCALE = scale

local now = 0
local state = nil          -- {run, mode, rank, outcome}
local clockLeft, clockRunning = nil, false -- the Greater Rift clock's seconds, and whether it still runs
local widgets = {}         -- the objective lines on show, in order
local barShown, barValue, barTarget = false, 0, 0
local leaving              -- the moment the turn-in started the fade; nil when not leaving

----------------------------------------------------------------------------------------------------
-- The block: one frame at the top of the quest list
----------------------------------------------------------------------------------------------------
local parent = WatchFrame or UIParent
local block = CreateFrame("Frame", "DiablocraftRiftTracker", parent)
block:SetWidth(WIDTH)
block:SetPoint("TOPLEFT", parent, "TOPLEFT", 0, LINES_TOP)
block:SetScale(scale)
block:Hide()

local title = block:CreateFontString(nil, "OVERLAY", "GameFontNormal")
title:SetPoint("TOPLEFT", block, "TOPLEFT", 0, 0)
title:SetJustifyH("LEFT")

-- The Greater Rift clock, right on the title line: M:SS, red once it reads 0:00 on a run
-- that is not beaten.
local clock = block:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
clock:SetPoint("TOPRIGHT", block, "TOPRIGHT", 0, 0)
clock:SetJustifyH("RIGHT")
clock:Hide()

-- The floor the player stands on (rift floors Part F6), right-aligned under the bar. The
-- run's bar spans the frame's whole width, so there is no room beside it; the floor line
-- sits under the bar's right end and moves with it. A member in town has no floor and
-- shows none.
local floorLabel = block:CreateFontString(nil, "OVERLAY", "GameFontNormal")
floorLabel:SetJustifyH("RIGHT")
floorLabel:Hide()

local function drawClock()
    if not clockLeft then return end
    local seconds = math.ceil(clockLeft)
    clock:SetText(("%d:%02d"):format(math.floor(seconds / 60), seconds % 60))
    if seconds <= 0 and state and state.outcome ~= "success" then
        clock:SetTextColor(1, 0.2, 0.2)
    else
        clock:SetTextColor(1, 1, 1)
    end
end

local bar = CreateFrame("Frame", nil, block)
bar:SetWidth(BAR_WIDTH)
bar:SetHeight(BAR_HEIGHT)
-- The empty channel is near-black, as in the frames; the fill runs over it.
bar.channel = bar:CreateTexture(nil, "BACKGROUND")
bar.channel:SetTexture(0.04, 0.035, 0.03, 0.95)
bar.channel:SetPoint("TOPLEFT", bar, "TOPLEFT", TROUGH_X, -TROUGH_Y)
bar.channel:SetWidth(TROUGH_W)
bar.channel:SetHeight(TROUGH_H)
bar.fill = bar:CreateTexture(nil, "ARTWORK")
bar.fill:SetTexture(artPath(ART.barFill))
bar.fill:SetPoint("TOPLEFT", bar, "TOPLEFT", TROUGH_X, -TROUGH_Y)
bar.fill:SetHeight(TROUGH_H)
bar.edge = bar:CreateTexture(nil, "ARTWORK", nil, 1)
bar.edge:SetTexture(artPath(ART.barEdge))
bar.edge:SetBlendMode("ADD")
bar.edge:SetWidth(5)
bar.edge:SetHeight(TROUGH_H)
bar.edge:SetPoint("CENTER", bar.fill, "RIGHT", -1, 0)
bar.frame = bar:CreateTexture(nil, "OVERLAY")
bar.frame:SetTexture(artPath(ART.barFrame))
bar.frame:SetTexCoord(0, 400 / 512, 0, 88 / 128)
bar.frame:SetAllPoints(bar)
bar:Hide()

local function drawBar()
    local width = math.max(1, TROUGH_W * math.max(0, math.min(1, barValue)))
    bar.fill:SetWidth(width)
    bar.fill:SetTexCoord(0, width / TROUGH_W, 0, 1)
    if barValue > 0 then bar.edge:Show() else bar.edge:Hide() end
end

-- One objective line: the box, its text, the X that slashes onto it, and the
-- flourish, right-aligned just left of the box as D3 draws it.
local pool = {}
local function lineWidget()
    local w = table.remove(pool)
    if w then return w end
    w = CreateFrame("Frame", nil, block)
    w:SetWidth(WIDTH)
    w.box = w:CreateTexture(nil, "ARTWORK")
    w.box:SetWidth(BOX)
    w.box:SetHeight(BOX)
    w.box:SetPoint("TOPLEFT", w, "TOPLEFT", LINE_X - 3, 0)
    w.text = w:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    w.text:SetPoint("TOPLEFT", w, "TOPLEFT", TEXT_X, 0)
    w.text:SetWidth(WIDTH - TEXT_X)
    w.text:SetJustifyH("LEFT")
    w.slash = w:CreateTexture(nil, "OVERLAY")
    w.slash:SetTexture(artPath(ART.slash))
    w.slash:SetPoint("CENTER", w.box, "CENTER", 0, 0)
    w.slash:Hide()
    w.streak = w:CreateTexture(nil, "BACKGROUND")
    w.streak:SetTexture(artPath(ART.streak))
    w.streak:SetBlendMode("ADD")
    -- The flourish word: real Exocet text, right-aligned just left of the box as D3 draws
    -- it (wordFont() carries the fallback).
    w.flourish = w:CreateFontString(nil, "OVERLAY")
    w.flourish:SetJustifyH("RIGHT")
    w.flourish:SetFont(wordFont(), WORD_FONT, "")
    w.flourish:SetTextColor(WORD_COLOR[1], WORD_COLOR[2], WORD_COLOR[3])
    w.flourish:SetShadowColor(WORD_GLOW[1], WORD_GLOW[2], WORD_GLOW[3])
    w.flourish:SetShadowOffset(1, -1)
    w.streak:SetPoint("RIGHT", w.flourish, "RIGHT", 0, 0)
    w.streak:SetHeight(18)
    return w
end

local function setBox(w, crossed)
    w.box:SetTexture(artPath(crossed and ART.boxCrossed or ART.boxEmpty))
end

local function setFlourish(w, label)
    if label then
        w.flourishText, w.flourishAt = label, now
        w.flourish:SetText(label)
        w.flourish:Show()
        w.streak:Show()
    else
        w.flourishText, w.flourishAt = nil, nil
        w.flourish:Hide()
        w.streak:Hide()
    end
end

local function release(w)
    w:Hide()
    w.slash:Hide()
    setFlourish(w, nil)
    pool[#pool + 1] = w
end

----------------------------------------------------------------------------------------------------
-- The list around it: the stock lines start under the block, and the header
----------------------------------------------------------------------------------------------------
local moved = false
local function placeLines(offset)
    if not WatchFrameLines or not WatchFrame then return end
    if offset then
        -- `offset` is already in WatchFrame's own (unscaled) units: the caller multiplies each
        -- block's unscaled height by the objective scale. WatchFrameLines is the stock frame's
        -- child and offsets in those same units.
        WatchFrameLines:ClearAllPoints()
        WatchFrameLines:SetPoint("TOPLEFT", WatchFrame, "TOPLEFT", 0, LINES_TOP - offset - (WATCHFRAME_TYPE_OFFSET or 10))
        WatchFrameLines:SetPoint("BOTTOMRIGHT", WatchFrame, "BOTTOMRIGHT", -24, 12)
        moved = true
    elseif moved then
        -- Back to the XML's own anchors (WatchFrame.xml, WatchFrameLines).
        WatchFrameLines:ClearAllPoints()
        WatchFrameLines:SetPoint("TOPLEFT", WatchFrame, "TOPLEFT", 0, LINES_TOP)
        WatchFrameLines:SetPoint("BOTTOMRIGHT", WatchFrame, "BOTTOMRIGHT", -24, 12)
        moved = false
    end
end

local headerText
local function styleMinimise()
    local button = WatchFrameCollapseExpandButton
    if not button then return end
    -- ElvUI's skin draws its own .tex and resets it on every collapse and expand; ours is
    -- set after its hooks, on the same texture, so the red button survives the skin.
    local target = button.tex or (button.GetNormalTexture and button:GetNormalTexture())
    if target then
        target:SetTexture(artPath(ART.minimise))
        target:SetTexCoord(0, 1, 0, 1)
    end
end

local function styleHeader(entryShown)
    if not WatchFrameHeader then return end
    if not headerText then
        -- D3's list header is "OBJECTIVES" in real Exocet text, whose own O is the circled
        -- cross the tracker used to draw as a separate icon.
        headerText = WatchFrameHeader:CreateFontString(nil, "OVERLAY")
        headerText:SetPoint("LEFT", WatchFrameHeader, "LEFT", 0, 0)
        headerText:SetJustifyH("LEFT")
        -- Font before text: this string is created with no template, and the 3.3.5 client
        -- throws "<unnamed>:SetText(): Font not set" for text on a string that has none
        -- (the live error opening a rift). The size is re-applied below
        -- so the Objective Frame slider still moves it.
        headerText:SetFont(wordFont(), HEADER_FONT * scale / SCALE, "")
        headerText:SetText(TEXT.objectives)
        headerText:SetTextColor(HEAD_COLOR[1], HEAD_COLOR[2], HEAD_COLOR[3])
        headerText:SetShadowColor(HEAD_GLOW[1], HEAD_GLOW[2], HEAD_GLOW[3])
        headerText:SetShadowOffset(1, -1)
        if WatchFrameTitle then
            WatchFrameTitle:ClearAllPoints()
            WatchFrameTitle:SetPoint("LEFT", headerText, "RIGHT", 4, 0)
        end
    end
    if not entryShown then
        -- The entry is not up: the stock update owns the header, the title and the button,
        -- and our word must stop drawing (it used to be left on screen).
        headerText:Hide()
        return
    end
    if WatchFrameTitle then
        WatchFrameTitle:SetText("")
        WatchFrameTitle:Hide()
    end
    headerText:SetFont(wordFont(), HEADER_FONT * scale / SCALE, "")
    headerText:Show()
    WatchFrameHeader:SetWidth((headerText:GetWidth() or 0) + 20)
    -- With no stock objective the stock update hides the header and the button;
    -- the entry is an objective, so both show while it does.
    WatchFrameHeader:Show()
    if WatchFrameCollapseExpandButton then
        WatchFrameCollapseExpandButton:Show()
        WatchFrameCollapseExpandButton:Enable()
    end
    styleMinimise()
end

----------------------------------------------------------------------------------------------------
-- Layout and drawing
----------------------------------------------------------------------------------------------------
local function lineHeight(w)
    local h = w.text.GetStringHeight and w.text:GetStringHeight()
    return math.max(LINE_HEIGHT, (h or LINE_HEIGHT) + 2)
end

local function layout()
    local ownHeight = 0
    local collapsed = WatchFrame and WatchFrame.collapsed
    if state then
        local y = -LINE_HEIGHT - 2
        for _, w in ipairs(widgets) do
            w:ClearAllPoints()
            w:SetPoint("TOPLEFT", block, "TOPLEFT", 0, y)
            w:SetHeight(lineHeight(w))
            y = y - lineHeight(w)
        end
        if barShown then
            bar:ClearAllPoints()
            bar:SetPoint("TOPLEFT", block, "TOPLEFT", -12, y - 4)
            bar:Show()
            y = y - 4 - BAR_HEIGHT
        else
            bar:Hide()
        end
        if state.floor then
            floorLabel:ClearAllPoints()
            floorLabel:SetPoint("TOPRIGHT", block, "TOPRIGHT", 0, y - 2)
            floorLabel:SetText(TEXT.floor:format(state.floor))
            floorLabel:Show()
            y = y - LINE_HEIGHT - 2
        else
            floorLabel:Hide()
        end
        local height = -y
        block:SetHeight(height)
        T.height = height
        if collapsed then block:Hide() else block:Show() end
        if not collapsed then ownHeight = height end
    else
        block:Hide()
    end

    local offset = ownHeight * scale
    placeLines(offset > 0 and offset or nil)
    styleHeader(state ~= nil)
end

-- The Objective Frame scale slider in Torment's ElvUI options pushes the saved factor in
-- here (ElvUI_Torment's apply pass calls it). The
-- lines, the box and its X, the bar and the words all sit on the block, so its one scale
-- carries them; the header word and the stock lines follow through layout(). ElvUI's mover
-- and its Nudge own WatchFrame itself - only our own block is scaled, never the list, so a
-- drag or a nudge keeps working.
function T.SetScale(value)
    value = tonumber(value)
    if not value or value <= 0 or value == scale then return end
    scale = value
    T.SCALE = value
    block:SetScale(value)
    layout()
end

-- A line's look at this moment, from its timestamps; nothing here decides state.
local function animate(w)
    local alpha = 1
    if w.appearAt then alpha = math.min(1, (now - w.appearAt) / TIMING.lineIn) end
    if w.doneAt then
        local since = now - w.doneAt
        if since < TIMING.slash then
            local t = since / TIMING.slash
            local size = BOX * (SLASH_START - (SLASH_START - 1) * t)
            w.slash:SetWidth(size)
            w.slash:SetHeight(size)
            w.slash:Show()
        else
            w.slash:Hide()
            setBox(w, true)
        end
        if since > TIMING.doneHold then
            alpha = math.max(0, 1 - (since - TIMING.doneHold) / TIMING.doneOut)
        end
    end
    w:SetAlpha(alpha)
    if w.flourishAt then
        local since = now - w.flourishAt
        local slide = math.min(1, since / TIMING.flourishIn)
        w.flourish:ClearAllPoints()
        w.flourish:SetPoint("RIGHT", w.box, "LEFT", -4 - FLOURISH_SLIDE * (1 - slide), 0)
        local fade = 1
        local out = since - TIMING.flourishIn - TIMING.flourishHold
        if out > 0 then fade = math.max(0, 1 - out / TIMING.flourishOut) end
        w.flourish:SetAlpha(fade * slide)
        w.streak:SetAlpha(fade * (1 - 0.5 * slide))
        w.streak:SetWidth(40 + FLOURISH_SLIDE * (1 - slide))
        if fade <= 0 then setFlourish(w, nil) end
    end
end

local function clear()
    for _, w in ipairs(widgets) do release(w) end
    widgets = {}
end

-- The entry leaves, now: drop it, put our word away, and hand the header, the title and the
-- button back to the stock update. One stock update redraws the list itself, so our word is
-- not left orphaned on the header (the old Hide did exactly that).
local function hideNow()
    leaving = nil
    state = nil
    barShown = false
    block:SetAlpha(1)
    if headerText then headerText:SetAlpha(1) end
    clear()
    layout()
    if WatchFrame_Update then WatchFrame_Update() end
end

local function tick(elapsed)
    now = now + (elapsed or 0)
    if leaving then
        -- The turn-in fade: hold, then fade the block (its title, lines and bar are its
        -- children) and the header word together, then leave.
        local since = now - leaving
        if since >= TIMING.hideHold + TIMING.doneOut then
            hideNow()
        else
            local fade = 1
            if since > TIMING.hideHold then fade = 1 - (since - TIMING.hideHold) / TIMING.doneOut end
            block:SetAlpha(fade)
            if headerText then headerText:SetAlpha(fade) end
        end
    end
    local removed = false
    for index = #widgets, 1, -1 do
        local w = widgets[index]
        animate(w)
        if w.doneAt and now - w.doneAt >= TIMING.doneHold + TIMING.doneOut then
            table.remove(widgets, index)
            release(w)
            removed = true
        end
    end
    if clockRunning and clockLeft > 0 then
        -- Between pushes the clock runs here; every push resets it to the server's seconds.
        local before = math.ceil(clockLeft)
        clockLeft = math.max(0, clockLeft - (elapsed or 0))
        if math.ceil(clockLeft) ~= before then drawClock() end
    end
    if barShown and barValue ~= barTarget then
        -- Eases to the new value, never jumps: a kill moves it a little at a time.
        barValue = barValue + (barTarget - barValue) * math.min(1, (elapsed or 0) * TIMING.fillEase)
        if math.abs(barTarget - barValue) < 0.002 then barValue = barTarget end
        drawBar()
    end
    if removed then layout() end
end
T.Tick = tick
-- The clock lives on the always-shown refresh frame below, not the block: the turn-in fade
-- must keep running while the list is collapsed or ElvUI has WatchFrame hidden.

local function addWidget(objective, order, text, settled, done)
    local w = lineWidget()
    w.key, w.order = objective.key, order
    w.text:SetText(text)
    setBox(w, false)
    w.doneAt, w.appearAt = nil, nil
    setFlourish(w, nil)
    w:SetAlpha(1)
    if not settled then
        w.appearAt = now
        w:SetAlpha(0)
        if objective.flourish then setFlourish(w, objective.flourish) end
    end
    if done then
        w.doneAt = now
        setFlourish(w, TEXT.complete)
    end
    w:Show()
    widgets[#widgets + 1] = w
    return w
end

local function isDone(objective, rank, outcome)
    return (objective.done and rank >= objective.done) or (objective.doneOn ~= nil and outcome == objective.doneOn)
end

-- A push. The first one for a run (login, /reload, a late join) draws the state as it
-- stands, with no flourish and no fade; a later one for the same run animates the steps.
function handlers.Update(_, row)
    if type(row) ~= "table" then return end
    local view = VIEWS[row.mode or "nr"]
    local rank = ORDER[row.state]
    if not view or not rank then
        -- A row with no view draws nothing: put the entry away at once, no fade.
        hideNow()
        return
    end
    local settled = not state or state.run ~= row.run or state.mode ~= row.mode
    if settled then clear() end
    -- A new run (or this run's next step) cancels a turn-in fade in progress.
    leaving = nil
    block:SetAlpha(1)
    if headerText then headerText:SetAlpha(1) end
    title:SetText(view.title:format(tonumber(row.rank) or 0))
    local outcome = row.outcome
    local byKey = {}
    for _, w in ipairs(widgets) do byKey[w.key] = w end
    for order, objective in ipairs(view.objectives) do
        local shown = rank >= objective.from and not (objective.beatenOnly and outcome == "expired")
        local done = isDone(objective, rank, outcome)
        local text = outcome == "expired" and objective.failed or objective.text
        local w = byKey[objective.key]
        if shown and settled then
            if not done then addWidget(objective, order, text, true, false) end
        elseif shown and not w and not (state and isDone(objective, state.rank, state.outcome)) then
            -- A step the client never saw (open straight to complete) still arrives and is crossed.
            addWidget(objective, order, text, false, done)
        elseif w and done and not w.doneAt then
            w.doneAt = now
            setFlourish(w, TEXT.complete)
        end
        if w then w.text:SetText(text) end
    end
    table.sort(widgets, function(a, b) return a.order < b.order end)
    -- The clock: the server's seconds on every push, run down here while the result is pending.
    if view.clock and row.left then
        clockLeft, clockRunning = tonumber(row.left) or 0, outcome == "pending"
        clock:Show()
    else
        clockLeft, clockRunning = nil, false
        clock:Hide()
    end
    local required = tonumber(row.required) or 0
    barTarget = required > 0 and math.min(1, (tonumber(row.progress) or 0) / required) or 0
    local wasShown = barShown
    barShown = view.bar[row.state] == true
    -- The bar goes the moment the Guardian appears (37.7 -> 37.8 s); it eases only while it stays.
    if settled or not wasShown then barValue = barTarget end
    drawBar()
    state = {run = row.run, mode = row.mode, rank = rank, outcome = outcome, floor = tonumber(row.floor)}
    drawClock()
    for _, w in ipairs(widgets) do animate(w) end
    layout()
end

-- The run is over for this player: the first turn-in (the server sets dc_rift.closing_at and
-- every holder gets Hide), or a member who abandoned the quest. The OBJECTIVES part stays a
-- moment and then fades, gone about 5 s after the turn-in. `immediate` is
-- our own call for a push that must draw nothing; the server's Hide never passes it.
function handlers.Hide(_, immediate)
    if immediate then
        hideNow()
    elseif state and not leaving then
        leaving = now
    end
end

-- Every update of the stock list: keep the block on top and the header in its look.
-- A post-hook, so nothing of ours runs inside WatchFrame_Update itself and the
-- stock handler list is never touched.
if WatchFrame then
    hooksecurefunc("WatchFrame_Update", function() layout() end)
    hooksecurefunc("WatchFrame_Collapse", function() layout() end)
    hooksecurefunc("WatchFrame_Expand", function() layout() end)
end

----------------------------------------------------------------------------------------------------
-- One entry, not two: the rift quest's own stock lines never show
----------------------------------------------------------------------------------------------------
local function riftQuestAt(index)
    if not index or not GetQuestLogTitle then return false end
    local questId = select(9, GetQuestLogTitle(index))
    return QUESTS[questId] == true
end

local function unwatchRiftQuests()
    for watch = GetNumQuestWatches(), 1, -1 do
        local index = GetQuestIndexForWatch(watch)
        if riftQuestAt(index) then RemoveQuestWatch(index) end
    end
end
T.UnwatchRiftQuests = unwatchRiftQuests

local function holdsRiftQuest()
    for index = 1, (GetNumQuestLogEntries and GetNumQuestLogEntries() or 0) do
        if riftQuestAt(index) then return true end
    end
    return false
end

-- Every stock path that tracks a quest calls AddQuestWatch and only then
-- WatchFrame_Update (QuestLogFrame.lua:109, 262, 269; WorldMapFrame.lua:2165), so a
-- rift quest is taken off again before the list draws it.
hooksecurefunc("AddQuestWatch", function(index)
    if riftQuestAt(index) then RemoveQuestWatch(index) end
end)

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:RegisterEvent("QUEST_LOG_UPDATE")
local holding = false
events:SetScript("OnEvent", function()
    unwatchRiftQuests()
    -- Holding the quest is what makes the entry appear, in the rift or in town.
    local now_holding = holdsRiftQuest()
    if now_holding ~= holding then
        holding = now_holding
        AIO.Handle(CHANNEL, "Refresh")
    end
end)
unwatchRiftQuests()

-- Other members' kills, the Guardian's death and someone else's turn-in reach this
-- player by the refresh, not by a push of their own: while a rift quest is held or the
-- entry shows, ask every couple of seconds (DCThrottle.Allow(..., 5, 10): 5 tokens
-- per second, bucket of 10).
local REFRESH = 2.0
local ticker, since = CreateFrame("Frame"), 0
ticker:SetScript("OnUpdate", function(_, elapsed)
    -- The entry's own clock rides this always-shown frame, so the turn-in fade keeps
    -- running while the list is collapsed or ElvUI has WatchFrame hidden.
    tick(elapsed)
    since = since + elapsed
    if since < REFRESH then return end
    since = 0
    if state or holdsRiftQuest() then AIO.Handle(CHANNEL, "Refresh") end
end)

-- The frames the tests read.
T.ui = {block = block, title = title, clock = clock, floorLabel = floorLabel, bar = bar, widgets = function() return widgets end}
T.BarValue = function() return barValue, barTarget, barShown end

SLASH_DIABLOCRAFTRIFT1 = "/dcrift"
SlashCmdList.DIABLOCRAFTRIFT = function() AIO.Handle(CHANNEL, "Refresh") end
