-- luacheck: globals AIO IsInInstance
-- luacheck: ignore 111 121 122 431 432
-- Run from repo root with `lua5.1 mod-diablocraft/scripts/tests/monsters/test_dc_elite_client.lua`.
--
-- Drives the production client half of dc_elite.lua with a stub 3.3.5a API:
-- the affix label must draw on a Blizzard nameplate (border-texture signature)
-- and on an ElvUI-WotLK nameplate (plate.UnitFrame, border blanked, name moved
-- into UnitFrame.Name / oldName). Mocks prove the lookup and anchoring, not
-- pixels: the real-client look is docs/test-diablocraft-elvui-nameplate-affixes.md.

local BORDER = "Interface\\Tooltips\\Nameplate-Border"
local handlers, scanner
local asked = 0
local inInstance = true

_G.AIO = {
    AddAddon = function() return false end,
    AddHandlers = function(_, t) handlers = t; return t end,
    Handle = function(_, name) if name == "Refresh" then asked = asked + 1 end end,
}
_G.IsInInstance = function() return inInstance end

-- The one shared strict widget mock (diablocraft-yey2) owns CreateFrame,
-- WorldFrame and every nameplate widget the test builds.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024, 768)
local frames = Mock.frames

dofile("mod-diablocraft/lua/aio/dc_elite.lua")
for _, made in ipairs(frames) do
    if made.scripts.OnUpdate then scanner = made end
end
assert(handlers and handlers.Update and scanner, "client half loaded")

local function sweep() scanner.scripts.OnUpdate(scanner, 1.0) end

-- Blizzard plate: [1] unrelated texture, [2] the border, then name text.
-- The plate's name is XML text with a template, so the FontString has its font before
-- any SetText: the mock now refuses text on a FontString with no font, as the client does
-- (dc_widget_mock rule 5, diablocraft-scog).
local bliz = Mock.widget("Frame")
bliz:CreateTexture(nil, "OVERLAY")
local bBorder = bliz:CreateTexture(nil, "OVERLAY"); bBorder:SetTexture(BORDER)
local bName = bliz:CreateFontString(nil, "OVERLAY", "GameFontNormal"); bName:SetText("Grimtooth")

-- ElvUI plate, shaped as ElvUI-WotLK 6.09 OnCreated builds it (Nameplates.lua
-- :571-632): UnitFrame child of the plate, UnitFrame.Health the StatusBar,
-- UnitFrame.Name ElvUI's own text, UnitFrame.oldName the hidden Blizzard
-- FontString; QueueObject (:679) blanks the border texture to "".
local elv = Mock.widget("Frame")
elv:CreateTexture(nil, "OVERLAY")
local eBorder = elv:CreateTexture(nil, "OVERLAY"); eBorder:SetTexture("")
local old = elv:CreateFontString(nil, "OVERLAY", "GameFontNormal"); old:SetText("Gnarlfang")
-- ElvUI gives its nameplate text a font (Nameplates.lua:571-632); the mock refuses
-- SetText on a FontString with no font, as the client does (dc_widget_mock rule 5).
local function elvName(text)
    local name = Mock.widget("FontString")
    name:SetFont("Fonts\\FRIZQT__.TTF", 12)
    name:SetText(text)
    return name
end
elv.UnitFrame = Mock.widget("Frame")
elv.UnitFrame.Health = Mock.widget("StatusBar")
elv.UnitFrame.oldName = old
elv.UnitFrame.Name = elvName("Gnarlfang")

-- Defensive variant: only a colour-coded UnitFrame.Name carries the name.
local elv2 = Mock.widget("Frame")
elv2:CreateTexture(nil, "OVERLAY"); elv2:CreateTexture(nil, "OVERLAY")
elv2.UnitFrame = Mock.widget("Frame")
elv2.UnitFrame.Name = elvName("|cff00ff00Skarn|r")

-- A plate that is not a pack: must get no label.
local plain = Mock.widget("Frame")
plain:CreateTexture(nil, "OVERLAY")
local pBorder = plain:CreateTexture(nil, "OVERLAY"); pBorder:SetTexture(BORDER)
local pName = plain:CreateFontString(nil, "OVERLAY", "GameFontNormal"); pName:SetText("Rabbit")

_G.WorldFrame.children = {bliz, elv, elv2, plain}
handlers.Update(nil, {
    {name = "Grimtooth", rank = "Champion", affixes = "Molten, Vortex"},
    {name = "Gnarlfang", rank = "Elite", affixes = "Arcane"},
    {name = "Skarn", rank = "Rare", affixes = ""},
})
sweep()

-- The label the client half draws is a FontString on the plate or its ElvUI
-- UnitFrame; its font template tells it apart from the plate's own name text.
local function label(frame)
    local owner = frame.UnitFrame or frame
    for _, child in ipairs(owner.children) do
        if child.kind == "FontString" and child.template == "GameFontNormalSmall" then
            return child
        end
    end
    return nil
end

local function shellLabels(frame)
    local count = 0
    for _, child in ipairs(frame.children) do
        if child.kind == "FontString" and child.template == "GameFontNormalSmall" then
            count = count + 1
        end
    end
    return count
end

-- ElvUI off: label on the Blizzard plate, unchanged behaviour.
local l = label(bliz)
assert(l and l.shown and l:GetText() == "Champion: Molten, Vortex", "Blizzard plate shows its line")
assert(l.points[1].relativeTo == bliz and l.points[1].relativePoint == "TOP",
    "Blizzard label anchors to the plate")

-- ElvUI on: label on the UnitFrame, anchored to the health bar, text matched
-- through oldName and through colour-coded UnitFrame.Name alone.
l = label(elv)
assert(l and l.shown and l:GetText() == "Elite: Arcane", "ElvUI plate shows its line")
assert(l.parent == elv.UnitFrame, "ElvUI label is parented to UnitFrame")
assert(l.points[1].relativeTo == elv.UnitFrame.Health, "ElvUI label anchors to UnitFrame.Health")
assert(shellLabels(elv) == 0, "nothing is hung on the hidden Blizzard shell")
l = label(elv2)
assert(l and l.shown and l:GetText() == "Rare", "colour-coded ElvUI name still matches")
assert(l.points[1].relativeTo == elv2.UnitFrame, "no health bar: anchors to UnitFrame")

-- Not a pack: nothing drawn.
assert(shellLabels(plain) == 0, "a non-pack plate gets no label")

-- A hidden plate hides its label; a cleared list hides it on the next Update.
elv.shown = false; sweep()
assert(not label(elv).shown, "label hides with its plate")
elv.shown = true; sweep()
assert(label(elv).shown, "label returns with the plate")
handlers.Update(nil, {})
sweep()
assert(not label(bliz).shown and not label(elv).shown, "no packs: all labels hidden")

-- Late UnitFrame: the sweep sees the plate first (label made on the shell),
-- then ElvUI attaches its UnitFrame. The label must move to the unit and the
-- shell label must be hidden.
local late = Mock.widget("Frame")
late:CreateTexture(nil, "OVERLAY")
local lBorder = late:CreateTexture(nil, "OVERLAY"); lBorder:SetTexture(BORDER)
local lName = late:CreateFontString(nil, "OVERLAY", "GameFontNormal"); lName:SetText("Gnarlfang")
_G.WorldFrame.children = {late}
handlers.Update(nil, {{name = "Gnarlfang", rank = "Elite", affixes = "Arcane"}})
sweep()
local shellLabel = label(late)
assert(shellLabel and shellLabel.shown, "first sweep labels the bare shell")
late.UnitFrame = Mock.widget("Frame")
late.UnitFrame.Health = Mock.widget("StatusBar")
late.UnitFrame.oldName = lName
lBorder:SetTexture("")
sweep()
local moved = late.UnitFrame.children[1]
assert(moved and moved.shown and moved:GetText() == "Elite: Arcane", "label re-homed onto the UnitFrame")
assert(moved.points[1].relativeTo == late.UnitFrame.Health, "re-homed label anchors to UnitFrame.Health")
assert(not shellLabel.shown, "the shell label is hidden")
sweep()
assert(#late.UnitFrame.children == 1, "no label is re-created every sweep")

-- UI fixes row 12: a `.dc elite` test pack stands in the open world and the
-- server publishes it under instance 0 on purpose (dc_elite.lua push), so its
-- line arrives outside any instance (/dcelite, a kill, a map change). The
-- client must not wipe it on the next 3 s tick: outside an instance it keeps
-- asking while it holds lines, and the server's answer is what clears them.
local function tick() for _ = 1, 3 do sweep() end end -- REFRESH is 3 s; sweep() is 1 s
inInstance = false
asked = 0
handlers.Update(nil, {{name = "Gnarlfang", rank = "Champion", affixes = "Molten"}})
tick()
moved = late.UnitFrame.children[1]
assert(moved.shown and moved:GetText() == "Champion: Molten",
       "an open-world test pack keeps its line past the refresh tick")
assert(asked == 1, "outside an instance, held lines are re-asked, got " .. asked)
tick()
assert(moved.shown and asked == 2, "and they stay while the server still publishes them")
handlers.Update(nil, {})  -- `.dc elite clear`: the server's answer has no packs
sweep()
assert(not moved.shown, "the server's empty answer clears the line")
asked = 0
tick(); tick()
assert(asked == 0, "outside an instance with nothing held, the client asks for nothing")
inInstance = true
tick()
assert(asked == 1, "inside an instance it asks every tick, as before")

print("test_dc_elite_client: ok")
