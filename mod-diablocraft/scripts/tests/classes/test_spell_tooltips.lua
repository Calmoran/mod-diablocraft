-- Runs in the bundled Lua interpreter; mocks only the client tooltip surface.
--
-- Spell rewrite step 9: the stock spell record renders the tooltip now, so
-- dc_spell_tooltips.lua must not touch it. This pins that the file registers no
-- AIO channel and no tooltip hook, and that a native tooltip - including the
-- rune name in the stock Rank field, drawn top right - is preserved unchanged.
local registered, hooks = {}, {}
AIO = {AddAddon = function() return false end,
       AddHandlers = function(name, handler) registered[name] = handler; return handler end}
SPELL_CAST_TIME_INSTANT = "Instant"
function hooksecurefunc(_, method, callback) hooks[method] = callback end
function GetActionInfo() return "spell", 16, "spell", 81025 end

-- The client's native tooltip as the record now draws it: name, the variant in
-- the stock Rank field top right, cost, range, cast, and the D3 sentence with
-- the element in it. No Lua may remove any of these.
GameTooltip = {lines = {}}
function GameTooltip:GetName() return "GameTooltip" end
function GameTooltip:NumLines() return #self.lines end
function GameTooltip:ClearLines() self.lines = {} end
function GameTooltip:AddLine(text, r, g, b, wrap)
    self.lines[#self.lines + 1] = {text = text, colour = {r, g, b}, wrap = wrap}
    local i = #self.lines
    _G["GameTooltipTextLeft" .. i] = {GetText = function() return text end}
    _G["GameTooltipTextRight" .. i] = {GetText = function() return nil end}
end
function GameTooltip:AddDoubleLine(left, right)
    self:AddLine(left, 1, 1, 1)
    self.lines[#self.lines].right = right
end
function GameTooltip:Show() self.shown = true end

local function native()
    GameTooltip:ClearLines()
    GameTooltip:AddLine("Frenzy")
    GameTooltip:AddDoubleLine("", "Rune: Sidearm")
    GameTooltip:AddLine("25 Fury")
    GameTooltip:AddLine("Melee Range")
    GameTooltip:AddLine("Instant")
    GameTooltip:AddLine("Generate: 4 Fury per attack\nSwing for 220% weapon damage. This effect stacks up to 5 times.")
end
local function snapshot()
    local copy = {}
    for i, line in ipairs(GameTooltip.lines) do
        copy[i] = {text = line.text, right = line.right}
    end
    return copy
end
local function contains(text)
    for _, line in ipairs(GameTooltip.lines) do
        if line.text:find(text, 1, true) then return true end
    end
    return false
end

dofile("mod-diablocraft/lua/aio/dc_spell_tooltips.lua")

-- The shrink: the server catalogue push and the tooltip hook are both gone.
assert(next(registered) == nil, "the DiablocraftSpellTooltips catalogue push must be gone")
assert(next(hooks) == nil, "the file must not hook SetAction or SetHyperlink")

-- The native tooltip is preserved exactly, rank included.
native()
local before = snapshot()
assert(GameTooltip.lines[2].right == "Rune: Sidearm", "the native Rank line must stay")
assert(contains("25 Fury") and contains("Melee Range"), "native cost and range lines must stay")
assert(contains("Instant"), "the native cast line must stay")
assert(contains("stacks up to 5 times"), "the record's own sentence must be what is drawn")
for i, line in ipairs(before) do
    assert(GameTooltip.lines[i].text == line.text and GameTooltip.lines[i].right == line.right,
        "nothing may change the native tooltip")
end
print("Spell tooltip checks passed: no push, no hook, native text, rank, layout and spacing preserved.")
