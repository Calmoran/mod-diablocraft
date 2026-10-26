-- luacheck: ignore 111 113 121 122
-- Run from the repo root: lua mod-diablocraft/scripts/tests/ui/test_rift_text.lua
--
-- client-patch/addons/Torment/RiftText.lua against the strict 3.3.5a widget mock (the client half of
-- docs/contracts/rift-centre-text.md, diablocraft-jdkr1). What it pins:
--   * a DCRIFTTEXT whisper to the player draws the line: every part in its own colour, the parts' texts
--     joined with nothing between them (the contract's example, 300 seconds left, is the expected string);
--   * the line fades in, holds and fades out on the look's numbers, then hides; a kind the client has no
--     look for is drawn with the default look, and gr_complete has its own;
--   * a new line replaces the one on screen and starts its clock again;
--   * a record that is not the contract's shape (another record, no parts, an odd field count, an empty
--     text, a bad kind), another prefix, another sender or another channel draws nothing; a colour that is
--     not six hex digits is drawn white;
--   * the line stands on the centre line of the screen's upper part, in the stock Morpheus font.
-- What this does NOT cover: how it looks on screen (the designer's check on dev), and what the server sends
-- (test_urshi_spawn.py, test_gr_progress.py).

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()

_G.UnitName = function() return "Tester" end
_G.GameFontNormalHuge = {}

dofile("client-patch/addons/Torment/RiftText.lua")

local R = _G.Diablocraft.RiftText
local watcher
for _, frame in ipairs(Mock.frames) do
    if frame.events and frame.events.CHAT_MSG_ADDON then watcher = frame end
end
assert(watcher, "the module registered a frame for CHAT_MSG_ADDON")

local function chat(message, sender, prefix, distribution)
    watcher.scripts.OnEvent(watcher, "CHAT_MSG_ADDON", prefix or "DCRIFTTEXT", message, distribution or "WHISPER", sender or "Tester")
end

-- The line's frame and its text: the only frame under UIParent the module makes besides the watcher.
local function lineFrame()
    for _, frame in ipairs(Mock.frames) do
        if frame ~= watcher and frame.scripts and frame.scripts.OnUpdate and frame.parent == _G.UIParent then return frame end
    end
end
local function lineText()
    for _, frame in ipairs(Mock.frames) do
        if frame.text ~= nil and frame.font ~= nil then return frame end
    end
end
local function tick(seconds)
    local line = lineFrame()
    line.scripts.OnUpdate(line, seconds)
end
local function near(a, b) return type(a) == "number" and math.abs(a - b) < 0.001 end

-- 0. Nothing is drawn until a line arrives.
assert(lineFrame() == nil, "no line frame before the first line")

-- 1. The contract's example: 300 seconds left.
local EXAMPLE = "C|gr_complete|b2b2b2|Greater Rift Complete! You finished with |00ff00|5 minutes|b2b2b2| remaining."
local DRAWN = "|cffb2b2b2Greater Rift Complete! You finished with |r|cff00ff005 minutes|r|cffb2b2b2 remaining.|r"
chat(EXAMPLE)
local line = lineFrame()
assert(line and line:IsShown(), "the line shows")
local text = lineText()
assert(text.text == DRAWN, "the parts are drawn in their colours, joined: " .. tostring(text.text))
assert(text.font == "Fonts\\MORPHEUS.TTF" and text.fontSize == 30, "gr_complete: stock Morpheus at 30")
assert(near(line.alpha, 0), "it starts clear")

-- Placement: the top of the line is 22% of the screen's height below its top edge.
local height = _G.UIParent:GetHeight()
local point, relative, relativePoint, x, y = line:GetPoint(1)
assert(point == "TOP" and relative == _G.UIParent and relativePoint == "TOP" and x == 0, "centred on the screen's middle line")
assert(y == -math.floor(height * 0.22), "22% of the height down from the top: " .. tostring(y) .. " of " .. tostring(height))

-- 2. gr_complete fades in over 0.4 s, holds 5 s, fades out over 1.5 s.
tick(0.2)
assert(near(line.alpha, 0.5), "halfway in: " .. tostring(line.alpha))
tick(0.2)
assert(near(line.alpha, 1), "in")
tick(4.9)
assert(near(line.alpha, 1) and line:IsShown(), "held")
tick(0.1 + 0.75)
assert(near(line.alpha, 0.5) and line:IsShown(), "halfway out: " .. tostring(line.alpha))
tick(0.75 + 0.01)
assert(not line:IsShown(), "gone after the fade")

-- 3. A kind with no look of its own takes the default one: 26 points, in 0.3 s, held 4 s, out over 1.2 s.
chat("C|some_new_kind|ffffff|Hello")
assert(line:IsShown() and text.text == "|cffffffffHello|r", "an unknown kind still shows")
assert(text.fontSize == 26, "the default size")
tick(0.15)
assert(near(line.alpha, 0.5), "the default fades in over 0.3 s")
tick(0.15 + 4)
assert(near(line.alpha, 1), "the default holds 4 s")
tick(0.6)
assert(near(line.alpha, 0.5), "and fades out over 1.2 s")
tick(0.6)
assert(not line:IsShown())

-- 4. A new line replaces the one on screen and starts its clock again.
chat(EXAMPLE)
tick(0.4 + 5 + 0.75)
assert(near(line.alpha, 0.5))
chat("C|gr_complete|00ff00|Second line")
assert(text.text == "|cff00ff00Second line|r" and near(line.alpha, 0) and line:IsShown(), "replaced and restarted")
tick(0.4)
assert(near(line.alpha, 1))
tick(10)
assert(not line:IsShown())

-- 5. A colour that is not six hex digits is drawn white, and a part keeps its spaces.
chat("C|gr_complete|zzz| a b |12345|c")
assert(text.text == "|cffffffff a b |r|cffffffffc|r", "bad colours are white: " .. tostring(text.text))
tick(10)

-- 6. Records and senders that are not the contract's draw nothing.
local function drawsNothing(label, ...)
    chat(...)
    assert(not line:IsShown(), label .. " drew a line")
end
drawsNothing("another record type", "X|That did not work.")
drawsNothing("a newer record", "Z|gr_complete|b2b2b2|hi")
drawsNothing("no parts", "C|gr_complete")
drawsNothing("a colour with no text", "C|gr_complete|b2b2b2")
drawsNothing("an odd field count", "C|gr_complete|b2b2b2|hi|00ff00")
drawsNothing("an empty text", "C|gr_complete|b2b2b2||00ff00|hi")
drawsNothing("a bad kind", "C|GR Complete|b2b2b2|hi")
drawsNothing("no kind", "C||b2b2b2|hi")
drawsNothing("an empty message", "")
drawsNothing("another prefix", EXAMPLE, nil, "DCPYLON")
drawsNothing("another sender", EXAMPLE, "Someone")
drawsNothing("another channel", EXAMPLE, nil, nil, "PARTY")

-- 7. After all that, a good line still shows.
chat(EXAMPLE)
assert(line:IsShown() and text.text == DRAWN)

print("test_rift_text: OK")
