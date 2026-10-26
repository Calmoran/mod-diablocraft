-- luacheck: globals Diablocraft hooksecurefunc CreateFrame UnitClass UnitPowerType
-- luacheck: globals GameTooltip UIErrorsFrame UnitFrameManaBar_UpdateType
-- luacheck: globals SetTextStatusBarTextPrefix TextStatusBar_UpdateTextString
-- luacheck: globals PowerBarColor
-- luacheck: ignore 111 121 122 431
--
-- ResourceText.lua - the reader for the generated name list. Contract
-- docs/contracts/resource-names.md,
-- surface map docs/research/systems/resource-text-muse.md.
--
-- The client draws the number; this file changes only the word. Several classes
-- can share a slot, so the D3 name comes from Diablocraft.ResourceNames by the
-- unit's class token and the slot token - no class name, resource name or slot
-- word is typed here. The stock word to replace is the client's own
-- _G[POWER_TOKEN], enumerated from the client's own PowerBarColor keys so the
-- reader does not depend on which slot the generated list currently uses.
--
-- Surfaces (Muse 1a-1d):
--   * spell tooltips - the compiled fill bindings whose owner is the viewing
--     player: spellbook SetSpell, action bar SetAction (stock and ElvUI's bars),
--     totem SetSpellByID, talent SetTalent, glyph SetGlyph, trainer
--     SetTrainerService. Rewritten after the fill, so every re-fill that
--     re-arms UpdateTooltip refreshes it too.
--   * error messages - the payload the stock UIErrorsFrame_OnEvent is about to
--     show; the map says this is the only Lua-reachable point.
--   * combat log - the map shows the word comes from the shared GlobalStrings
--     word, so _G[POWER_TOKEN] is set to the player's own class name and every
--     line shows that word, other players' included.
--   * a stock power bar's text - per unit class, so a shared slot is not
--     mislabelled after the combat-log override.
--
-- STOPPED surface - a spell shown through a hyperlink (the skill picker's
-- GameTooltip:SetHyperlink("spell:..") in dc_skillbar.lua, and chat links
-- through ItemRefTooltip). A spell link names an id, not a class, and the
-- client exposes no spell-ownership API: GetSpellInfo carries no class, and
-- SkillLineAbility/SkillLine are not readable from Lua. IsSpellKnown is
-- learned-state, not ownership (an unlearned own-class skill is also false, a
-- known shared spell establishes no class), and a generic SetHyperlink hook
-- cannot see its caller. These tooltips keep the stock word until a generated
-- spell-id -> owning-class table ships from the generator; this is a
-- reported limitation, not an accepted shortcut.
--
-- No displayed number is ever read, computed, divided or rewritten; this file
-- no longer calls tonumber at all.

Diablocraft = Diablocraft or {}

local RT = {}
Diablocraft.ResourceText = RT

-- The slot's stock word, read from the client (never a literal here). Every
-- slot the client knows is captured before applyGlobals() can overwrite a token
-- for the combat log; the generated list only narrows which words matter.
local STOCK = {}
do
    local tokens = {}
    if type(PowerBarColor) == "table" then
        for token in pairs(PowerBarColor) do tokens[token] = true end
    end
    for _, rows in pairs(Diablocraft.ResourceNames or {}) do
        for token in pairs(rows) do tokens[token] = true end
    end
    for token in pairs(tokens) do
        if STOCK[token] == nil then STOCK[token] = _G[token] or false end
    end
end

local function playerClass()
    if type(UnitClass) ~= "function" then return nil end
    local _, token = UnitClass("player")
    return token
end

-- The class's resources as an ordered list of {token, stock, name}. Nil when the
-- class is absent from the list, so the stock word stays.
local function classWords(classToken)
    local rows = classToken and Diablocraft.ResourceNames and Diablocraft.ResourceNames[classToken]
    if not rows then return nil end
    local out = {}
    for token, entry in pairs(rows) do
        local stock = STOCK[token]
        if stock and entry.name then
            out[#out + 1] = {token = token, stock = stock, name = entry.name}
        end
    end
    if #out == 0 then return nil end
    table.sort(out, function(a, b) return a.token < b.token end)
    return out
end

-- The D3 name for a class and slot, or nil when the list has none.
function RT.WordFor(classToken, powerToken)
    local rows = classToken and Diablocraft.ResourceNames and Diablocraft.ResourceNames[classToken]
    local entry = rows and rows[powerToken]
    if entry and STOCK[powerToken] then return entry.name end
    return nil
end

-- A whole-word, case-insensitive find: the error strings lower-case the word
-- ("Not enough energy") while the slot token is "Energy".
local function findWord(haystack, needle)
    local lower = haystack:lower()
    local start = 1
    while true do
        local s, e = lower:find(needle, start, true)
        if not s then return nil end
        local before = s > 1 and lower:sub(s - 1, s - 1) or ""
        local after = e < #lower and lower:sub(e + 1, e + 1) or ""
        if not before:match("%a") and not after:match("%a") then return s, e end
        start = e + 1
    end
end

-- The sourced client cost formats (GlobalStrings.lua):
--   *_COST / POWER_DISPLAY_COST             "%d Word"
--   *_COST_PER_TIME / POWER_DISPLAY_COST_PER_TIME  "%d Word, plus %d per sec"
--   SPELL_USE_ALL_*                         "Uses 100% word"
--   TRAINER_MANA_COST                       "Word cost: ..."
-- The whole line must match one shape and the word must equal the slot's stock
-- word; the Uses-100% tokens mix case (Energy vs mana), so that compare is
-- case-insensitive. Any other line - "45 Rageous damage", "45 Rage damage
-- dealt" - is returned byte-for-byte. Returns word, start, stop.
local function costWord(line)
    local number, word = line:match("^(%d+) (%a[%a ]*), plus %d+ per sec$")
    if word then
        local start = #number + 2
        return word, start, start + #word - 1
    end
    number, word = line:match("^(%d+) (%a[%a ]*)$")
    if word then
        local start = #number + 2
        return word, start, start + #word - 1
    end
    word = line:match("^Uses 100%% (%a[%a ]*)$")
    if word then
        local start = 11 -- "Uses 100% " is 10 bytes
        return word, start, start + #word - 1
    end
    word = line:match("^(%a[%a ]*) cost: ")
    if word then
        return word, 1, #word
    end
    return nil
end

-- Replace only the slot word in a finished cost line. The number and every
-- other character are untouched by construction.
function RT.RewriteLine(line, classToken)
    if type(line) ~= "string" then return line end
    local word, start, stop = costWord(line)
    if not word then return line end
    local words = classWords(classToken)
    if not words then return line end
    local lower = word:lower()
    for _, candidate in ipairs(words) do
        if lower == candidate.stock:lower() then
            return line:sub(1, start - 1) .. candidate.name .. line:sub(stop + 1)
        end
    end
    return line
end

-- Replace only the slot word in a finished error string.
function RT.RewriteError(message, classToken)
    if type(message) ~= "string" then return message end
    local words = classWords(classToken)
    if not words then return message end
    for _, word in ipairs(words) do
        local s, e = findWord(message, word.stock:lower())
        if s then
            return message:sub(1, s - 1) .. word.name .. message:sub(e + 1)
        end
    end
    return message
end

-- ------------------------------------------------------------- spell tooltips

local function rewriteTooltip(tooltip)
    if not tooltip or not tooltip.GetName or not tooltip.NumLines then return end
    local classToken = playerClass()
    if not classToken then return end
    local name = tooltip:GetName()
    if not name then return end
    for i = 1, tooltip:NumLines() do
        local region = _G[name .. "TextLeft" .. i]
        if region and region.GetText and region.SetText then
            local text = region:GetText()
            local fixed = RT.RewriteLine(text, classToken)
            if fixed ~= text then region:SetText(fixed) end
        end
    end
end

if hooksecurefunc then
    -- The compiled fill bindings Muse 1a cites whose owner is the viewing
    -- player: spellbook, action bar (stock and ElvUI's bars), totem bar, talent
    -- frame, glyph socket and trainer. No hyperlink binding is hooked; see the
    -- stopped-surface note in the header.
    local methods = {"SetSpell", "SetAction", "SetSpellByID", "SetTalent", "SetGlyph", "SetTrainerService"}
    for _, method in ipairs(methods) do
        if GameTooltip and GameTooltip[method] then
            hooksecurefunc(GameTooltip, method, rewriteTooltip)
        end
    end
end

-- ----------------------------------------------------------- error messages

-- hooksecurefunc runs after the stock handler, which has already shown the
-- word, so the payload is substituted before the stored stock handler runs.
local function installErrors()
    local frame = UIErrorsFrame
    if not frame or not frame.GetScript or not frame.SetScript then return end
    local original = frame:GetScript("OnEvent")
    if not original then return end
    frame:SetScript("OnEvent", function(self, event, message, ...)
        if event == "UI_ERROR_MESSAGE" then
            message = RT.RewriteError(message, playerClass())
        end
        return original(self, event, message, ...)
    end)
end

-- ------------------------------------------------------- bars and combat log

-- By the unit's class, not the player's: after applyGlobals a shared slot would
-- otherwise carry the player's name on every unit's bar.
local function rewriteBar(manaBar)
    if not manaBar or not manaBar.unit then return end
    local unitFrame = manaBar.GetParent and manaBar:GetParent()
    if unitFrame and unitFrame.noTextPrefix then return end
    local powerToken
    if type(UnitPowerType) == "function" then
        local _, token = UnitPowerType(manaBar.unit)
        powerToken = token
    end
    if not powerToken then return end
    local _, classToken
    if type(UnitClass) == "function" then
        _, classToken = UnitClass(manaBar.unit)
    end
    local prefix = RT.WordFor(classToken, powerToken) or STOCK[powerToken]
    if prefix and SetTextStatusBarTextPrefix then
        SetTextStatusBarTextPrefix(manaBar, prefix)
        if TextStatusBar_UpdateTextString then TextStatusBar_UpdateTextString(manaBar) end
    end
end

if hooksecurefunc and type(UnitFrameManaBar_UpdateType) == "function" then
    hooksecurefunc("UnitFrameManaBar_UpdateType", rewriteBar)
end

-- The combat log's file-local builder reads the shared GlobalStrings words, so
-- the player's own class name is what the whole log shows (Muse 1d; other
-- players' lines included).
local function applyGlobals()
    local words = classWords(playerClass())
    if not words then return end
    for _, word in ipairs(words) do
        _G[word.token] = word.name
    end
end

-- ------------------------------------------------------------------- loading

installErrors()

if CreateFrame then
    local loader = CreateFrame("Frame")
    loader:RegisterEvent("PLAYER_LOGIN")
    loader:SetScript("OnEvent", applyGlobals)
end
