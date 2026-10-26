-- luacheck: ignore 111 112 113 121 122 431
-- Run from repo root with `lua mod-diablocraft/scripts/tests/difficulty/test_tier_client.lua`.
--
-- The client half of dc_tier.lua (diablocraft-7p05) against the strict 3.3.5a widget mock, on the
-- messages of docs/contracts/tier-messages.md. What it pins:
--   * the file asks `State` once at load; the button shows only on State(true, name), reads the
--     name, sits just above ElvUI's left chat panel or else the stock chat tab, and opens the window;
--   * Show draws one kit row per payload row (never a fixed ten), the name then Life, Damage, XP and
--     Gold, marks the current tier, greys a locked row and gives its reason on hover and click;
--   * a click asks only for an unlocked, non-current row, and nothing while the server says the
--     player may not pick (the reason is then the subtitle);
--   * a list taller than the window scrolls instead of growing the window.
-- What this does NOT cover: the server's rules (test_tier_server.lua) and the look and position in
-- the real client (the designer's check on dev).

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local sent = {}
_G.AIO = {
    AddAddon = function() return false end,
    AddHandlers = function(_, handlers) return handlers end,
    Handle = function(_, action, id) sent[#sent + 1] = {action = action, id = id} end,
}
_G.ChatFrame1Tab = CreateFrame("Button", "ChatFrame1Tab", UIParent)
Diablocraft = nil
dofile("mod-diablocraft/lua/aio/dc_aio_ui.lua")
local handlers
local addHandlers = AIO.AddHandlers
AIO.AddHandlers = function(name, t) handlers = addHandlers(name, t) return handlers end
dofile("mod-diablocraft/lua/aio/dc_tier.lua")

local ui = DCTier.ui
local frame, button = ui.frame, ui.button
assert(frame == _G.DiablocraftTierFrame and not frame:IsShown(), "the window exists and starts hidden")
assert(#sent == 1 and sent[1].action == "State", "the file asks State once at load")
assert(not button:IsShown(), "no button before the server says we are in the hub")
assert(type(SlashCmdList.DIABLOCRAFTTIER) == "function", "/dctier is kept")

-- The button.
handlers.State(nil, true, "Torment VI")
assert(button:IsShown() and button:GetText() == "Torment VI", "in the hub the button reads the tier")
local point, relativeTo, relativePoint = button:GetPoint(1)
assert(point == "BOTTOMLEFT" and relativeTo == ChatFrame1Tab and relativePoint == "TOPLEFT",
       "without ElvUI it sits just above the stock chat tab")
_G.LeftChatPanel = CreateFrame("Frame", "LeftChatPanel", UIParent)
handlers.State(nil, true, "Torment I")
point, relativeTo, relativePoint = button:GetPoint(1)
assert(button:GetNumPoints() == 1 and relativeTo == LeftChatPanel and point == "BOTTOMLEFT" and relativePoint == "TOPLEFT",
       "with ElvUI it sits just above the left chat panel")
assert(button:GetText() == "Torment I", "the button follows a change")
sent = {}
button.scripts.OnClick(button)
assert(#sent == 1 and sent[1].action == "Open", "the button opens the window")
handlers.State(nil, false)
assert(not button:IsShown(), "out of the hub the button is hidden")
sent = {}
SlashCmdList.DIABLOCRAFTTIER()
assert(sent[1].action == "Open", "/dctier opens it too")

local function row(id, name, reason)
    return {id, name, 819, 18985, 300, 1600, reason or ""}
end
local function shown()
    local list = {}
    for _, r in ipairs(ui.rows) do if r:IsShown() then list[#list + 1] = r end end
    return list
end
local function clicks(r)
    sent = {}
    r.scripts.OnClick(r)
    return sent[1]
end

-- No payload yet: the client has invented no row and no number.
assert(#ui.rows == 0, "no row is created before a payload")

handlers.Show(nil, {row(1, "Normal"), row(2, "Hard"), row(3, "Expert"),
                    row(4, "Master", "Requires a level 60 character on this account."),
                    row(5, "Torment I", "Requires character level 60.")}, 2, "")
assert(frame:IsShown(), "Show opens the window")
local rows = shown()
assert(#rows == 5, "five payload rows draw five rows, got " .. #rows)
assert(rows[1].label:GetText() == "Normal", "the row's name")
local cells = rows[1].cells
assert(cells[1]:GetText() == "819%" and cells[2]:GetText() == "18,985%" and cells[3]:GetText() == "+300%"
       and cells[4]:GetText() == "+1,600%", "Life, Damage, XP and Gold in their columns: "
       .. cells[1]:GetText() .. " " .. cells[2]:GetText() .. " " .. cells[3]:GetText() .. " " .. cells[4]:GetText())
for i = 1, 4 do
    assert(cells[i]:GetJustifyH() == "RIGHT", "the numbers are right-aligned")
    assert(select(4, cells[i]:GetPoint(1)) == select(4, shown()[5].cells[i]:GetPoint(1)), "every row's column " .. i .. " lines up")
end
assert(rows[2].mark:IsShown() and not rows[1].mark:IsShown(), "only the current tier is marked")
assert(ui.subtitle:GetText() == "The party leader chooses for everyone.", "a picker sees the usual line")

-- Locked: greyed, the reason on hover and on click, and no Select.
local r, g, b = rows[5].label:GetTextColor()
assert(r == DCUI.GREY[1] and g == DCUI.GREY[2] and b == DCUI.GREY[3], "a locked row is grey")
r, g = rows[5].cells[1]:GetTextColor()
assert(r == DCUI.GREY[1] and g == DCUI.GREY[2], "its numbers too")
r = rows[1].label:GetTextColor()
assert(r ~= DCUI.GREY[1], "an unlocked row is not grey")
rows[5].scripts.OnEnter(rows[5])
assert(GameTooltip.lines and GameTooltip.lines[2] and GameTooltip.lines[2]:find("character level 60", 1, true),
       "hovering a locked row gives the server's reason")
assert(clicks(rows[5]) == nil, "a locked row asks for nothing")
assert(ui.note:GetText() == "Requires character level 60.", "clicking it shows the reason")

-- Unlocked: a click asks for exactly that row's id; the current one asks for nothing.
local ask = clicks(rows[3])
assert(ask and ask.action == "Select" and ask.id == 3, "a click asks for that row's id")
assert(clicks(rows[2]) == nil, "the current tier asks for nothing")

-- A party member who is not the leader: the server's reason is the subtitle and nothing selects.
handlers.Show(nil, {row(1, "Normal"), row(2, "Hard"), row(3, "Expert")}, 1, "Only the party leader may choose difficulty.")
assert(#shown() == 3 and #ui.rows == 5, "a smaller payload hides the surplus and keeps the rows")
assert(ui.subtitle:GetText() == "Only the party leader may choose difficulty.", "the subtitle says the leader chooses")
assert(ui.note:GetText() == "", "a new Show clears the old note")
for _, each in ipairs(shown()) do
    assert(clicks(each) == nil, "a non-leader's click asks for nothing")
end
assert(ui.note:GetText() == "Only the party leader may choose difficulty.", "a click repeats why")

-- Twenty tiers (Torment VII-XVI later): every one is drawn and the list scrolls inside the
-- window rather than the window growing.
local height = frame:GetHeight()
local many = {}
for id = 1, 20 do many[#many + 1] = row(id, "Tier " .. id) end
handlers.Show(nil, many, 1, "")
assert(#shown() == 20, "twenty payload rows draw twenty, got " .. #shown())
assert(frame:GetHeight() == height, "the window keeps its size")
assert(ui.list:GetHeight() == 20 * DCUI.ROW_HEIGHT, "the scroll child holds all twenty")
local scroll = _G.DiablocraftTierScroll
assert(scroll:GetScrollChild() == ui.list and scroll:GetHeight() < ui.list:GetHeight(), "and is taller than its scroll frame")

print('Difficulty tier client checks passed')
