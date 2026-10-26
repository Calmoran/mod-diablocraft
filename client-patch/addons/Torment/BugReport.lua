-- luacheck: globals AIO Diablocraft SlashCmdList tinsert UISpecialFrames UIParent GameTooltip GetAddOnMetadata
-- luacheck: globals GetCursorPosition strtrim strlenutf8 date CreateFrame ChatFontNormal GameFontNormalHuge
-- luacheck: globals ScrollingEdit_OnTextChanged ScrollingEdit_OnCursorChanged ScrollingEdit_OnUpdate
-- Diablocraft addon half - the /bug window and its on-screen button.
--
-- AIO bridge `DiablocraftBugReport` (docs/contracts/bug-report-messages.md).
-- Opening the window sends `Open()`; the server snapshots its own state, keeps it
-- and answers `Context(context)`, which fills the read-only right column. Send
-- carries only the title, the details, the TOC Version and the client patch; the
-- server validates, rate-limits from the table and files the snapshot it took at
-- open, so what the player saw is what is filed. It answers `Sent(id)` (the title
-- is emptied, the details template restored, the window closed) or
-- `Refused(reason)` (the boxes keep their text). The hourly-limit and confirmation
-- lines are the server's own chat messages.
--
-- The button uses the later client's Blizzard bug icon,
-- shipped as a BLP inside this addon's art folder; there is no bug texture in the
-- 3.3.5a base client. DC.ART's "bug-report" slot names it, DC.SetArt draws it.
-- It is 64x64, draws its own dark ground and gold edge (GitHub #99, the look it took from the
-- retired Bounty Board button) and joins the
-- one strip the on-screen buttons share
-- (ButtonStrip.lua, DIABLOCRAFT.ButtonStrip.Add); the button hands its dragging
-- to the strip, which moves and is remembered as one.

local DIABLOCRAFT = Diablocraft
local AIO = AIO or (require and require("AIO"))
local CHANNEL = "DiablocraftBugReport"
local WINDOW = "TormentBugReportFrame"
local BUTTON = "TormentBugButton"
local ADDON = "Torment"
local MAX_TITLE = 50
local MAX_DETAILS = 2000
local MIN_SCALE = 0.5
local WIDTH, HEIGHT = 1000, 700
local ICON = 64

local TEMPLATE = "What happened:\n\nWhat I expected to happen:\n\nHow to make it happen (steps):\n"
    .. "1.\n2.\n3.\n\nHow often: every time / sometimes / once"

local window
local titleBox, detailsBox, titleCounter, detailsCounter, statusLine, sendButton
local facts

-- ------------------------------------------------------------------ the bridge

local handlers = AIO and AIO.AddHandlers(CHANNEL, {})

local function version()
    return (GetAddOnMetadata and GetAddOnMetadata(ADDON, "Version")) or "0.1"
end

local function clientPatch()
    local value = GetAddOnMetadata and GetAddOnMetadata(ADDON, "X-Torment-Client-Patch")
    if not value then return "" end
    return (value:gsub("%s", ""))
end

-- Characters, not bytes, matching the server's count. strlenutf8 is the client's
-- own; the byte length is the fallback when it is missing.
local function length(text)
    if strlenutf8 then return strlenutf8(text or "") end
    return #(text or "")
end

local function submit()
    if not titleBox or not detailsBox or not AIO or not AIO.Handle then return end
    AIO.Handle(CHANNEL, "Send", titleBox:GetText() or "", detailsBox:GetText() or "",
        version(), clientPatch())
end

-- ------------------------------------------------------------------- the window

-- The right column, in the mockup's order: the server's snapshot fields plus the
-- client's own patch and addon version. Everything but the gear.
local FACTS = {
    "Character", "Class", "Level", "Paragon", "Realm", "Zone", "Subzone", "Position",
    "Difficulty", "Rift", "Target", "Server build", "Client", "Account", "Time",
}

local function factText(label, state)
    local function value(text)
        if text == nil or text == "" then return "--" end
        return tostring(text)
    end
    if label == "Character" then return value(state.name)
    elseif label == "Class" then return value(state.class)
    elseif label == "Level" then return value(state.level)
    elseif label == "Paragon" then return value(state.paragon)
    elseif label == "Realm" then return value(state.realm)
    elseif label == "Zone" then return value(state.zone)
    elseif label == "Subzone" then return value(state.subzone)
    elseif label == "Position" then
        return ("map %d \194\183 %.1f, %.1f, %.1f"):format(state.map_id or 0, state.x or 0, state.y or 0, state.z or 0)
    elseif label == "Difficulty" then return value(state.difficulty)
    elseif label == "Rift" then
        if not state.rift_id then return "Not in a rift" end
        return ("Rift #%d \194\183 tier %d"):format(state.rift_id, state.rift_level or 0)
    elseif label == "Target" then return value(state.target)
    elseif label == "Server build" then return value(state.build)
    elseif label == "Client" then
        return ("patch %s \194\183 addon %s"):format(clientPatch() ~= "" and clientPatch() or "?", version())
    elseif label == "Account" then return value(state.account and ("#" .. state.account) or nil)
    elseif label == "Time" then
        if not state.opened_at then return "--" end
        return date("%b %d, %H:%M", state.opened_at)
    end
    return "--"
end

local function fillFacts(state)
    for index, row in ipairs(facts) do
        row.value:SetText(state and factText(FACTS[index], state) or "--")
    end
end

-- Red when a limit is passed, grey otherwise.
local function colour(counter, over)
    local palette = (DIABLOCRAFT.Style and DIABLOCRAFT.Style.palette) or {}
    local red, grey = palette.RED or {1, .19, .19}, palette.GREY or {.62, .62, .62}
    if over then counter:SetTextColor(red[1], red[2], red[3]) else counter:SetTextColor(grey[1], grey[2], grey[3]) end
end

-- The counters, the red line and Send's state, from both boxes. Send stays off
-- until the title is 1..50 characters and the details fit.
local function refresh()
    if not titleBox then return end
    local title, details = strtrim(titleBox:GetText() or ""), detailsBox:GetText() or ""
    local titleChars, detailChars = length(title), length(details)
    local reason
    if titleChars > MAX_TITLE then reason = ("The title is too long (%d characters max)."):format(MAX_TITLE) end
    if not reason and detailChars > MAX_DETAILS then
        reason = ("The details are too long (%d characters max)."):format(MAX_DETAILS)
    end
    titleCounter:SetText(titleChars .. " / " .. MAX_TITLE)
    detailsCounter:SetText(detailChars .. " / " .. MAX_DETAILS)
    colour(titleCounter, titleChars > MAX_TITLE)
    colour(detailsCounter, detailChars > MAX_DETAILS)
    statusLine:SetText(reason or "")
    if titleChars >= 1 and not reason then sendButton:Enable() else sendButton:Disable() end
end

if handlers then
    -- The server took the snapshot and sent its display fields; fill the column.
    function handlers.Context(_, context)
        if facts then fillFacts(context) end
    end

    -- The server accepted the report and sent its row id; the chat line naming it
    -- is the server's. Empty the title, restore the template, close the window.
    function handlers.Sent(_, _id)
        if titleBox then titleBox:SetText("") end
        if detailsBox then detailsBox:SetText(TEMPLATE) end
        if statusLine then statusLine:SetText("") end
        refresh()
        if window then window:Hide() end
    end

    -- The server refused: the hourly limit and a database fault carry its own chat
    -- line and the boxes keep their text. A title or details the addon would have
    -- stopped reach here only from a modified client, so the reason is shown here.
    function handlers.Refused(_, reason)
        if not statusLine then return end
        if reason == "title" then
            statusLine:SetText(("The title must be 1 to %d characters."):format(MAX_TITLE))
        elseif reason == "details" then
            statusLine:SetText(("The details may be up to %d characters."):format(MAX_DETAILS))
        end
    end
end

-- The largest scale at which the 1000x700 window still fits UIParent.
local function scaleLimit()
    local width, height = UIParent:GetWidth(), UIParent:GetHeight()
    local fit = math.min(width / WIDTH, height / HEIGHT)
    if fit < MIN_SCALE then fit = MIN_SCALE end
    return fit
end

local function setScale(target, value)
    if value < MIN_SCALE then value = MIN_SCALE end
    local limit = scaleLimit()
    if value > limit then value = limit end
    target:SetScale(value)
end

-- A corner grabber: dragging away from the window's centre scales it, clamped to
-- [0.5, what fits the screen]. The centre is taken once at the drag's start, so
-- the window's own resize does not feed back into the ratio.
local function buildGrabber(frame, side)
    local grabber = CreateFrame("Button", nil, frame)
    grabber:SetSize(18, 18)
    grabber:SetPoint(side == "left" and "BOTTOMLEFT" or "BOTTOMRIGHT", side == "left" and 4 or -4, 4)
    local palette = (DIABLOCRAFT.Style and DIABLOCRAFT.Style.palette) or {}
    local gold = palette.TAB_IDLE or {.43, .36, .26}
    local across = grabber:CreateTexture(nil, "ARTWORK")
    across:SetTexture("Interface\\Buttons\\WHITE8X8")
    across:SetVertexColor(gold[1], gold[2], gold[3], .6)
    across:SetHeight(2)
    across:SetPoint(side == "left" and "BOTTOMLEFT" or "BOTTOMRIGHT", 0, 0)
    across:SetWidth(14)
    local down = grabber:CreateTexture(nil, "ARTWORK")
    down:SetTexture("Interface\\Buttons\\WHITE8X8")
    down:SetVertexColor(gold[1], gold[2], gold[3], .6)
    down:SetWidth(2)
    down:SetHeight(14)
    down:SetPoint(side == "left" and "BOTTOMLEFT" or "BOTTOMRIGHT", 0, 0)

    grabber:SetScript("OnMouseDown", function(self)
        self.active = true
        self.startScale = frame:GetScale()
        local scale = UIParent:GetEffectiveScale()
        local x, y = GetCursorPosition()
        self.px, self.py = x / scale, y / scale
        local s = self.startScale
        self.cx = (frame:GetLeft() + frame:GetRight()) / 2 * s
        self.cy = (frame:GetBottom() + frame:GetTop()) / 2 * s
        self.start = math.max(1, math.sqrt((self.px - self.cx) ^ 2 + (self.py - self.cy) ^ 2))
        setScale(frame, self.startScale)
    end)
    grabber:SetScript("OnUpdate", function(self)
        if not self.active then return end
        local scale = UIParent:GetEffectiveScale()
        local x, y = GetCursorPosition()
        x, y = x / scale, y / scale
        local distance = math.sqrt((x - self.cx) ^ 2 + (y - self.cy) ^ 2)
        setScale(frame, self.startScale * distance / self.start)
    end)
    grabber:SetScript("OnMouseUp", function(self)
        self.active = false
    end)
    return grabber
end

local function buildWindow()
    local frame = CreateFrame("Frame", WINDOW, UIParent)
    frame:SetSize(WIDTH, HEIGHT)
    frame:SetPoint("CENTER")
    frame:SetScale(math.min(1, scaleLimit()))
    frame:SetFrameStrata("DIALOG")
    frame:SetClampedToScreen(true)
    frame:SetMovable(true)
    frame:EnableMouse(true)
    -- The window parts from a skin's slots; the colours stay this window's own.
    DIABLOCRAFT.Style.Panel(frame)
    frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", frame.StartMoving)
    frame:SetScript("OnDragStop", frame.StopMovingOrSizing)

    local heading = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge")
    heading:SetPoint("TOPLEFT", 28, -22)
    heading:SetText("Report a bug")
    heading:SetTextColor(.91, .77, .42)
    local subtitle = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    subtitle:SetPoint("TOPLEFT", heading, "BOTTOMLEFT", 0, -4)
    subtitle:SetText("Goes privately to the server team. You get a report number to mention to staff.")
    subtitle:SetTextColor(.66, .61, .53)
    local close = DIABLOCRAFT.Style.Close(frame)
    close:SetScript("OnClick", function() frame:Hide() end)

    -- The right column first: the left one runs up to it.
    local right = CreateFrame("Frame", nil, frame)
    right:SetWidth(300)
    right:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -28, -84)
    right:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -28, 60)
    right:SetBackdrop(DIABLOCRAFT.Style.Backdrop("window-flat"))
    right:SetBackdropColor(1, 1, 1, .035)
    right:SetBackdropBorderColor(.24, .17, .10, 1)
    local caption = right:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    caption:SetPoint("TOPLEFT", 12, -12)
    caption:SetText("SENT WITH YOUR REPORT")
    caption:SetTextColor(.66, .61, .53)

    facts = {}
    for index = 1, #FACTS do
        local row = CreateFrame("Frame", nil, right)
        row:SetHeight(24)
        row:SetPoint("TOPLEFT", 12, -38 - (index - 1) * 24)
        row:SetPoint("TOPRIGHT", -12, -38 - (index - 1) * 24)
        row.label = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        row.label:SetPoint("LEFT", 0, 0)
        row.label:SetText(FACTS[index])
        row.label:SetTextColor(.66, .61, .53)
        row.value = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        row.value:SetPoint("RIGHT", 0, 0)
        row.value:SetText("--")
        local line = row:CreateTexture(nil, "BACKGROUND")
        line:SetTexture("Interface\\Buttons\\WHITE8X8")
        line:SetVertexColor(.42, .31, .17, .35)
        line:SetHeight(1)
        line:SetPoint("BOTTOMLEFT", 0, 0)
        line:SetPoint("BOTTOMRIGHT", 0, 0)
        facts[index] = row
    end

    local left = CreateFrame("Frame", nil, frame)
    left:SetPoint("TOPLEFT", 28, -84)
    left:SetPoint("BOTTOMRIGHT", right, "BOTTOMLEFT", -20, 0)

    local titleLabel = left:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    titleLabel:SetPoint("TOPLEFT", 0, 0)
    titleLabel:SetText("Title")
    titleLabel:SetTextColor(.91, .77, .42)
    local titleNote = left:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    titleNote:SetPoint("LEFT", titleLabel, "RIGHT", 4, 0)
    titleNote:SetText("(required)")
    titleNote:SetTextColor(.66, .61, .53)
    titleCounter = left:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    titleCounter:SetPoint("TOPRIGHT", 0, 0)
    titleCounter:SetText("0 / " .. MAX_TITLE)

    titleBox = CreateFrame("EditBox", nil, left, "InputBoxTemplate")
    titleBox:SetAutoFocus(false)
    titleBox:SetMaxLetters(MAX_TITLE)
    titleBox:SetHeight(40)
    titleBox:SetPoint("TOPLEFT", 0, -26)
    titleBox:SetPoint("TOPRIGHT", 0, -26)
    titleBox:SetScript("OnEscapePressed", function(self) self:ClearFocus(); frame:Hide() end)
    titleBox:SetScript("OnTextChanged", refresh)
    DIABLOCRAFT.Style.Input(titleBox)

    local detailsLabel = left:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    detailsLabel:SetPoint("TOPLEFT", 0, -80)
    detailsLabel:SetText("Details")
    detailsLabel:SetTextColor(.91, .77, .42)
    detailsCounter = left:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    detailsCounter:SetPoint("TOPRIGHT", 0, -80)

    -- The details box is the stock scrolling-edit pattern (HelpFrame's ticket box):
    -- the EditBox is the ScrollFrame's child and grows with its text, and the
    -- client's own ScrollingEdit_On* keep the cursor in view. SetMaxBytes is not
    -- set: the server counts characters, and a byte cap would cut a non-Latin
    -- report short.
    local scroll = CreateFrame("ScrollFrame", "TormentBugDetailsScroll", left, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 0, -104)
    scroll:SetPoint("BOTTOMRIGHT", 0, 0)
    DIABLOCRAFT.Style.Scroll(scroll)
    scroll:SetBackdrop(DIABLOCRAFT.Style.Backdrop("window-flat"))
    scroll:SetBackdropColor(.04, .03, .02, .9)
    scroll:SetBackdropBorderColor(.42, .32, .20, 1)
    detailsBox = CreateFrame("EditBox", nil, scroll)
    detailsBox:SetMultiLine(true)
    detailsBox:SetAutoFocus(false)
    detailsBox:SetMaxLetters(MAX_DETAILS)
    detailsBox:SetFontObject(ChatFontNormal)
    detailsBox:SetTextInsets(8, 8, 6, 6)
    detailsBox:SetText(TEMPLATE)
    scroll:SetScrollChild(detailsBox)
    scroll:SetScript("OnSizeChanged", function(_, width)
        detailsBox:SetWidth((width or left:GetWidth()) - 26)
    end)
    detailsBox:SetScript("OnTextChanged", function(self)
        if ScrollingEdit_OnTextChanged then ScrollingEdit_OnTextChanged(self, scroll) end
        refresh()
    end)
    detailsBox:SetScript("OnCursorChanged", function(self, x, y, w, h)
        if ScrollingEdit_OnCursorChanged then ScrollingEdit_OnCursorChanged(self, x, y, w, h) end
    end)
    detailsBox:SetScript("OnUpdate", function(self, elapsed)
        if ScrollingEdit_OnUpdate then ScrollingEdit_OnUpdate(self, elapsed, scroll) end
    end)
    detailsBox:SetScript("OnEscapePressed", function(self) self:ClearFocus(); frame:Hide() end)

    sendButton = DIABLOCRAFT.Style.Button(frame, 130, "Send", submit)
    sendButton:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -28, 24)
    local cancel = DIABLOCRAFT.Style.Button(frame, 130, "Cancel", function() frame:Hide() end)
    cancel:SetPoint("RIGHT", sendButton, "LEFT", -12, 0)
    DIABLOCRAFT.Style.Window(frame, "bug-report", {title = heading, close = close, buttons = {cancel, sendButton}})
    statusLine = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    statusLine:SetPoint("BOTTOMLEFT", 28, 30)
    statusLine:SetJustifyH("LEFT")
    local palette = (DIABLOCRAFT.Style and DIABLOCRAFT.Style.palette) or {}
    local red = palette.RED or {1, .19, .19}
    statusLine:SetTextColor(red[1], red[2], red[3])

    buildGrabber(frame, "left")
    buildGrabber(frame, "right")

    tinsert(UISpecialFrames, WINDOW)
    if AIO and AIO.SavePosition then AIO.SavePosition(frame) end
    refresh()
    frame:Hide()
    return frame
end

local function open()
    if not window then window = buildWindow() end
    fillFacts(nil)
    statusLine:SetText("")
    window:Show()
    if AIO and AIO.Handle then AIO.Handle(CHANNEL, "Open") end
end

-- -------------------------------------------------------------------- the button

-- The bug button joins the one strip (ButtonStrip.lua); Strip.Add sets the parent, the point
-- and the drag forwarding, so a drag that starts on the button moves the strip. This keeps only
-- what the button draws and does: its size, its art, its tooltip and its OnClick.
local function buildButton()
    local button = CreateFrame("Button", BUTTON, UIParent)
    button:SetSize(ICON, ICON)
    button:SetScript("OnClick", open)
    button:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
    -- The Bounty Board button's own backdrop (Torment_BountyBoard/BountyBoard.lua, since
    -- retired), kept so the button reads the same (GitHub #99): the shared
    -- flat backdrop, this dark ground and this gold edge.
    button:SetBackdrop(DIABLOCRAFT.Style.Backdrop("window-flat"))
    button:SetBackdropColor(.05, .03, .02, .95)
    button:SetBackdropBorderColor(.78, .6, .29, 1)

    local icon = button:CreateTexture(nil, "ARTWORK")
    icon:SetAllPoints(button)
    DIABLOCRAFT.SetArt(icon, "bug-report")
    button:SetNormalTexture(icon)

    button:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Report a bug")
        GameTooltip:AddLine("Click to open, drag to move.", 1, 0.82, 0)
        GameTooltip:Show()
    end)
    button:SetScript("OnLeave", function() GameTooltip:Hide() end)

    DIABLOCRAFT.ButtonStrip.Add(button)
    return button
end

buildButton()

SLASH_DIABLOCRAFTBUG1 = "/bug"
SlashCmdList.DIABLOCRAFTBUG = function()
    open()
end
