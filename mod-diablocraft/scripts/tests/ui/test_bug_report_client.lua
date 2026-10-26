-- luacheck: ignore 111 112 113 121 122 431
-- Run from repo root with `lua mod-diablocraft/scripts/tests/ui/test_bug_report_client.lua`.
-- The addon half (client-patch/addons/Torment/BugReport.lua) against a stub 3.3.5a
-- API. Proves: the 1000x700 window opens on /bug and asks the server for the
-- context; the title caps at 50 and the scrolling details box at 2000, pre-filled
-- with the template; Send stays off until a title is typed and sends the title,
-- the details, the TOC version and the client patch; Context fills the right
-- column; Sent empties the title, restores the template and closes; Refused keeps
-- the text; the 64x64 button joins the shared strip (ButtonStrip.lua) and wears its dark
-- ground and gold edge (GitHub #99, the look it took from the retired Bounty Board button); the
-- strip carries no mouse of its own (EnableMouse dropped, diablocraft-d1lt) and its buttons are
-- bound to one drag path, so a drag on the button moves the
-- whole strip (diablocraft-rnp5), and the strip is handed to AIO.SavePosition once; a
-- grabber release does not re-save, so the scale the player set survives; the
-- corner grabbers clamp the scale at 0.5 and at what fits the screen. The chat
-- lines are the server's and are tested in test_bug_report.lua.

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames          -- every widget made, in creation order
Mock.setScreen(1365, 768)           -- UIParent rect + GetScreenWidth/Height (the test's numbers)

_G.SlashCmdList = {}
_G.DEFAULT_CHAT_FRAME = {AddMessage = function() end}
_G.GetAddOnMetadata = function(_, field)
    if field == "Version" then return "0.1" end
    if field == "X-Torment-Client-Patch" then return "66" end
end
_G.require = nil
_G.strtrim = function(text) return (text:gsub("^%s*(.-)%s*$", "%1")) end
_G.ChatFontNormal, _G.GameFontNormalHuge = {}, {}
_G.GetCursorPosition = function() return cursorX, cursorY end
-- Stash.lua hooks these two stock cursor calls; the
-- client has them as functions and the mock refuses to hook a name that is not one.
_G.PickupContainerItem = function() end
_G.PickupInventoryItem = function() end

-- The client's own scrolling-edit helpers; the addon must call them.
local scrolled, cursored, updated = 0, 0, 0
_G.ScrollingEdit_OnTextChanged = function() scrolled = scrolled + 1 end
_G.ScrollingEdit_OnCursorChanged = function() cursored = cursored + 1 end
_G.ScrollingEdit_OnUpdate = function() updated = updated + 1 end
_G.date = function(fmt) return "Oct 4, 14:05" end

local sent, handlers = {}, {}
-- AIO.SavePosition is RegisterConfig + LibWindow.RestorePosition + LibWindow.SavePosition
-- (AIO_Client/AIO.lua:1017-1027, LibWindow-1.1.lua:170-202): a later call re-applies the
-- STORED scale and point before it stores the current ones, which is what hides a scale
-- the player set. Mock.SavePosition keeps that, so a surplus call is caught and every
-- call is recorded in Mock.savedPositions.
_G.AIO = {
    AddHandlers = function(name, table_) handlers[name] = table_ return table_ end,
    Handle = function(name, key, ...) sent[#sent + 1] = {channel = name, key = key, ...} end,
    SavePosition = Mock.SavePosition,
}

dofile("mod-diablocraft/scripts/dc_addon_core.lua")
local DC = _G.Diablocraft
dofile("client-patch/addons/Torment/ButtonStrip.lua")
dofile("client-patch/addons/Torment/BugReport.lua")

local function find(predicate)
    for _, f in ipairs(frames) do if predicate(f) then return f end end
    return nil
end

local function findText(text)
    return find(function(f) return f.kind == "FontString" and f.text == text end)
end

-- The value of the right column row whose label is `label`.
local function factValue(label)
    local text = findText(label)
    assert(text, "no fact row labelled " .. label)
    return text.parent.value:GetText()
end

-- 1. The 64x64 button joins the one shared strip (ButtonStrip.lua), and the strip
--    is handed to AIO.SavePosition once so it is remembered.
local strip = _G.TormentButtonStrip
local button = _G.TormentBugButton
assert(strip and strip.kind == "Frame", "the button strip is created at load")
assert(button and button.kind == "Button", "the bug button is created at load")
assert(button:GetWidth() == 64 and button:GetHeight() == 64,
    "the button is 64x64, got " .. tostring(button:GetWidth()) .. "x" .. tostring(button:GetHeight()))
assert(button.parent == strip, "the button lives in the strip (one strip, one drag)")
assert(strip:GetWidth() == 64, "one button makes a 64-wide strip, got " .. tostring(strip:GetWidth()))
-- The strip's place on a fresh install (nothing in AIO_FRAMEPOSITIONS). ButtonStrip.lua:56-66
-- anchors it at the top right and says "nothing to restore on the first run, which keeps the
-- anchor above" -- but AIO.SavePosition's FIRST call registers an empty config, and
-- LibWindow.RestorePosition clears that anchor and centres the frame in its parent
-- (LibWindow-1.1.lua:182-200). So the strip opens at the screen centre, not at the top right
-- the comment promises: that is the addon bug the PM files (diablocraft-s5kn). The mock models
-- AIO, so this test shows it; fixing the addon flips this assert back to TOPRIGHT -220,-40.
assert(strip.points[1] and strip.points[1][1] == "CENTER" and strip.points[1][2] == UIParent
    and strip.points[1][3] == "CENTER" and strip.points[1][4] == 0 and strip.points[1][5] == 0,
    "the first AIO.SavePosition centres the strip (LibWindow restores with nothing stored), got "
        .. tostring(strip.points[1] and strip.points[1][1]))
-- The strip carries no mouse of its own (diablocraft-d1lt): with the Bounty Board retired
-- (diablocraft-xq7ft) the bug button is the whole strip and covers it, so a mouse-enabled strip
-- ground would add nothing and would turn a hidden button into an invisible click-blocker. The
-- strip stays movable (StartMoving runs on it) and dragless; the button is the frame that catches
-- a click, and its handler is the strip's one published pair.
assert(strip.movable and not strip.drag and not strip.scripts.OnDragStart and not strip.scripts.OnDragStop,
    "the strip is movable but takes no mouse and no drag of its own")
assert(not strip:IsMouseEnabled(),
    "the strip is not mouse-enabled (EnableMouse dropped): no invisible click area left of the button")
assert(button.scripts.OnDragStart == DC.ButtonStrip.StartDrag
    and button.scripts.OnDragStop == DC.ButtonStrip.StopDrag,
    "a drag on the button is the strip's own drag path")
-- The client hands the drag to the frame under the cursor: the button carries the handler itself
-- (Mock.dragBegin refuses a drag that lands on a parent), so a drag on the button moves the whole
-- strip, and the strip takes no mouse of its own to intercept it.
Mock.dragBegin(button)
assert(strip.moving, "dragging the button starts moving the strip")
button.scripts.OnDragStop(button)
assert(not strip.moving, "releasing the button stops the strip")
assert(button.scripts.OnClick, "clicking the button opens the window")
assert(button.normalTexture and button.normalTexture.texture == DC.ART_PATH .. "bug_report",
    "the icon is the bug-report art slot: " .. tostring(button.normalTexture and button.normalTexture.texture))
-- The button's own backdrop (GitHub #99): the shared flat backdrop, its dark ground and its
-- gold edge, the look it took from the retired Bounty Board button (diablocraft-xq7ft). These
-- are the button's values, pinned here the way test_stash_look.lua pins DCUI's copies.
local ground, edge = button.backdropColor or {}, button.borderColor or {}
assert(button.backdrop == DC.Style.flat and ground[1] == .05 and ground[2] == .03
    and ground[3] == .02 and ground[4] == .95,
    "the button wears its dark ground, got " .. tostring(ground[1]) .. ","
        .. tostring(ground[2]) .. "," .. tostring(ground[3]) .. "," .. tostring(ground[4]))
assert(edge[1] == .78 and edge[2] == .6 and edge[3] == .29 and edge[4] == 1,
    "and its gold edge, got " .. tostring(edge[1]) .. "," .. tostring(edge[2]) .. ","
        .. tostring(edge[3]) .. "," .. tostring(edge[4]))
assert(Mock.savedPositions[1] == strip, "the strip position is remembered through AIO.SavePosition")
assert(DC.ButtonStrip and DC.ButtonStrip.Add and DC.ButtonStrip.frame() == strip,
    "the strip API is published")

-- 2. /bug opens the 1000x700 window, which asks the server for the context.
assert(SLASH_DIABLOCRAFTBUG1 == "/bug" and SlashCmdList.DIABLOCRAFTBUG, "/bug is registered")
assert(_G.TormentBugReportFrame == nil, "the window is built lazily")
SlashCmdList.DIABLOCRAFTBUG()
local window = _G.TormentBugReportFrame
assert(window and window.shown, "/bug opens the window")
assert(window:GetWidth() == 1000 and window:GetHeight() == 700,
    "the window is 1000x700, got " .. tostring(window:GetWidth()) .. "x" .. tostring(window:GetHeight()))
assert(window.backdrop == DC.Style.backdrop, "the window wears the shared backdrop")
assert(window.scripts.OnDragStart == window.StartMoving, "the window is draggable")
local escape = false
for _, name in ipairs(UISpecialFrames) do if name == "TormentBugReportFrame" then escape = true end end
assert(escape, "Esc closes the window (UISpecialFrames)")
assert(#sent == 1 and sent[1].channel == "DiablocraftBugReport" and sent[1].key == "Open",
    "opening asks the server for the context")

-- 3. The boxes: the title caps at 50 and the details box is the 2000-cap
--    scrolling edit box, pre-filled with the template.
local titleBox = find(function(f) return f.kind == "EditBox" and f.maxLetters == 50 end)
local detailsBox = find(function(f) return f.kind == "EditBox" and f.multiLine end)
assert(titleBox, "the window has a 50-character title box")
assert(titleBox.autoFocus == false, "the title box does not steal focus")
assert(detailsBox, "the window has a multi-line details box")
assert(detailsBox.maxLetters == 2000, "the details box caps at 2000 letters, got " .. tostring(detailsBox.maxLetters))
assert(detailsBox.maxBytes == nil, "the details box has no byte cap (characters are counted, not bytes)")
assert(detailsBox.autoFocus == false, "the details box does not steal focus")
local TEMPLATE = "What happened:\n\nWhat I expected to happen:\n\nHow to make it happen (steps):\n"
    .. "1.\n2.\n3.\n\nHow often: every time / sometimes / once"
assert(detailsBox:GetText() == TEMPLATE, "the details box opens with the template")
local scroll = _G.TormentBugDetailsScroll
assert(scroll and scroll.kind == "ScrollFrame", "the details box is in a named ScrollFrame")
assert(scroll.scrollChild == detailsBox, "the details box is the scroll frame's child")

-- 4. The counters and Send's state follow both boxes.
local send = find(function(f) return f.text == "Send" end)
local cancel = find(function(f) return f.text == "Cancel" end)
assert(send and cancel, "the window has Send and Cancel")
assert(findText("0 / 50"), "the title counter starts at 0 / 50")
assert(findText(TEMPLATE:len() .. " / 2000"), "the details counter counts the template")
assert(not send:IsEnabled(), "Send is off while the title is empty")
titleBox:SetText("the goblin ate my stash")
titleBox.scripts.OnTextChanged(titleBox)
assert(send:IsEnabled(), "Send turns on with a 1..50 character title")
assert(findText("23 / 50"), "the title counter follows the box, got " .. tostring(findText("23 / 50")))
titleBox:SetText(("x"):rep(51))
titleBox.scripts.OnTextChanged(titleBox)
assert(not send:IsEnabled(), "a 51-character title keeps Send off")
assert(findText("51 / 50"), "the over-long title is counted")

-- 5. Send carries the title, the details, the TOC version and the client patch.
titleBox:SetText("the goblin ate my stash")
titleBox.scripts.OnTextChanged(titleBox)
detailsBox:SetText("it was a goblin")
detailsBox.scripts.OnTextChanged(detailsBox)
assert(scrolled > 0, "the details box drives the client's scrolling edit")
sent = {}
send.scripts.OnClick()
assert(#sent == 1 and #sent[1] == 4, "Send sends four fields, got " .. tostring(#sent[1]))
assert(sent[1].channel == "DiablocraftBugReport" and sent[1].key == "Send", "on the bug-report channel")
assert(sent[1][1] == "the goblin ate my stash" and sent[1][2] == "it was a goblin",
    "carrying the title and the details")
assert(sent[1][3] == "0.1" and sent[1][4] == "66",
    "and the addon version and client patch, got " .. tostring(sent[1][3]) .. " / " .. tostring(sent[1][4]))

-- 6. Context fills the right column: the server's snapshot plus the client's own
--    version, with the mockup's formatting.
handlers.DiablocraftBugReport.Context(nil, {
    name = "Wizzydizzy", class = "Wizard", level = 70, paragon = 183, realm = "Torment",
    map_id = 530, zone = "Shattrath City", subzone = "Scryer's Tier",
    x = 5432.1, y = 312.4, z = 98.0, difficulty = "Torment VI", target = "Gharbad",
    build = "0.1.3", account = 1, opened_at = 1000,
})
assert(factValue("Character") == "Wizzydizzy", "Character is the server's")
assert(factValue("Class") == "Wizard", "Class is the D3 name")
assert(factValue("Level") == "70" and factValue("Paragon") == "183", "Level and Paragon are the server's")
assert(factValue("Realm") == "Torment", "Realm is the server's")
assert(factValue("Zone") == "Shattrath City" and factValue("Subzone") == "Scryer's Tier", "Zone and Subzone")
assert(factValue("Position") == "map 530 \194\183 5432.1, 312.4, 98.0",
    "Position is the map and the point, got " .. factValue("Position"))
assert(factValue("Difficulty") == "Torment VI", "Difficulty is the tier's name")
assert(factValue("Rift") == "Not in a rift", "Rift says so when there is none")
assert(factValue("Server build") == "0.1.3", "Server build is the deployed identity")
assert(factValue("Client") == "patch 66 \194\183 addon 0.1", "Client is the client-reported pair, got " .. factValue("Client"))
assert(factValue("Account") == "#1", "Account is the account id")
assert(factValue("Time") == "Oct 4, 14:05", "Time is the open snapshot's time")

-- 6b. In a rift the row names it.
handlers.DiablocraftBugReport.Context(nil, {rift_id = 500, rift_level = 9, map_id = 1, x = 1, y = 2, z = 3})
assert(factValue("Rift") == "Rift #500 \194\183 tier 9", "an enrolled run is named, got " .. factValue("Rift"))

-- 7. Sent(id): the server accepted; the title is emptied, the template restored
--    and the window put away.
titleBox:SetText("sent already")
detailsBox:SetText("typed")
handlers.DiablocraftBugReport.Sent(nil, 7)
assert(titleBox:GetText() == "", "Sent clears the title")
assert(detailsBox:GetText() == TEMPLATE, "Sent restores the template")
assert(not window.shown, "Sent closes the window")

-- 8. Refused: the hourly-limit line is the server's and the text stays so nothing
--    is retyped; a title/details refusal (a modified client) shows a red line.
SlashCmdList.DIABLOCRAFTBUG()
titleBox:SetText("keep me")
detailsBox:SetText("and this")
handlers.DiablocraftBugReport.Refused(nil, "limit")
assert(titleBox:GetText() == "keep me" and detailsBox:GetText() == "and this",
    "Refused keeps the text in both boxes")
handlers.DiablocraftBugReport.Refused(nil, "title")
assert(findText(("The title must be 1 to 50 characters.")), "a refused title is shown in the red line")

-- 9. Opening resets the column to its placeholders and re-asks.
handlers.DiablocraftBugReport.Context(nil, {name = "Someone"})
assert(factValue("Character") == "Someone", "the column is filled")
SlashCmdList.DIABLOCRAFTBUG()
assert(factValue("Character") == "--", "a new open clears the old context")

-- 10. The corner grabbers scale the window, clamped at 0.5 and at what fits.
local grabbers = {}
for _, f in ipairs(frames) do
    if f.kind == "Button" and f.parent == window and f:GetWidth() == 18 then grabbers[#grabbers + 1] = f end
end
assert(#grabbers == 2, "two corner grabbers, got " .. tostring(#grabbers))
local grabber = grabbers[1]
-- The handler takes the window's centre from its resolved rect at the drag's
-- start, so the test moves the cursor on the same centre. Start and end
-- distances are vertical.
local function dragFrom(startDistance, endDistance)
    local scale = window:GetScale()
    local cx = (window:GetLeft() + window:GetRight()) / 2 * scale
    local cy = (window:GetBottom() + window:GetTop()) / 2 * scale
    cursorX, cursorY = cx, cy + startDistance
    grabber.scripts.OnMouseDown(grabber)
    cursorX, cursorY = cx, cy + endDistance
    grabber.scripts.OnUpdate(grabber)
    return window:GetScale()
end
window:SetScale(1)
assert(dragFrom(200, 10) == 0.5, "the scale clamps at half size")
window:SetScale(1)
-- UIParent is 1365x768, so the fit limit is min(1.365, 1.097): the window may
-- never grow past 768/700 even on a big screen.
assert(dragFrom(100, 10000) == 768 / 700, "the scale clamps at what fits the screen")
-- A smaller screen lowers the ceiling without touching the floor.
Mock.setScreen(800, 560)
window:SetScale(1)
assert(dragFrom(100, 10000) == 0.8, "a smaller screen lowers the ceiling, got " .. tostring(window:GetScale()))
window:SetScale(1)
assert(dragFrom(200, 10) == 0.5, "the floor stays at half size")

-- 10b. Releasing a grabber must not re-save: AIO.SavePosition re-applies the stored
--      scale, so a save here would undo the scale the player just set (return
--      failure 2). The window is saved once, at build; the strip once, at its frame.
window:SetScale(1)
assert(dragFrom(200, 10) == 0.5, "drag to half size")
grabber.scripts.OnMouseUp(grabber)
assert(window:GetScale() == 0.5,
    "the scale the player set survives the mouse-up, got " .. tostring(window:GetScale()))
assert(#Mock.savedPositions == 2,
    "AIO.SavePosition is called once for the strip and once for the window, got " .. #Mock.savedPositions)
assert(Mock.savedPositions[1] == strip and Mock.savedPositions[2] == window, "those two frames, in load order")

-- 11. The TOC loads the file after the style kit it needs.
local toc = assert(io.open("client-patch/addons/Torment/Torment.toc")):read("*a")
local styleAt, bugAt = toc:find("WindowStyle%.lua"), toc:find("BugReport%.lua")
assert(bugAt, "BugReport.lua is listed in Torment.toc")
assert(styleAt and styleAt < bugAt, "and after WindowStyle.lua")
local stripAt = toc:find("ButtonStrip%.lua")
assert(stripAt, "ButtonStrip.lua is listed in Torment.toc")
assert(stripAt < bugAt, "and before BugReport.lua, whose button joins the strip at load")

print("Bug report client checks passed")
