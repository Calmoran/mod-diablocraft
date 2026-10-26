-- luacheck: globals Diablocraft PowerBarColor
-- luacheck: ignore 122
--
-- PowerStrings.lua - the client's colour and words for each class power token.
-- Contract docs/contracts/class-powers.md.
--
-- The rebuilt client reports a class's own power token (FURY, WRATH, ...) where
-- the stock one said RAGE or ENERGY, and everything that draws a power keys its
-- colour and words by that token: PowerBarColor[token] for every bar, _G[token]
-- for the bar text and the combat log, and the tooltip's cost line, which the
-- client formats from _G[token .. "_COST"] ("%d Word") and
-- _G[token .. "_COST_PER_TIME"] ("%d Word, plus %d per sec"). This file fills
-- those from the generated Diablocraft.PowerTokens, so a token the stock client
-- never had still draws in its own colour with its own name.
--
-- A token that is its slot's own stock token (the Witch Doctor's MANA) is the
-- client's already and is left exactly as it is. The cost formats are the
-- slot's stock ones with the stock word swapped for the power's name, so the
-- number and the wording around it stay the client's.

Diablocraft = Diablocraft or {}

local PS = {}
Diablocraft.PowerStrings = PS

-- The stock slot token a power token rides, read from the generated list (the
-- slot token is the key a row sits under), so no slot word is typed here.
local function slotTokenFor(token)
    for _, rows in pairs(Diablocraft.ResourceNames or {}) do
        for slotToken, entry in pairs(rows) do
            if entry.token == token then return slotToken end
        end
    end
    return nil
end

-- A stock cost format with its stock word replaced by `name`; nil when the
-- format does not hold the word, so a string that is not the expected shape is
-- never half-rewritten.
function PS.CostFormat(format, stockWord, name)
    if type(format) ~= "string" or type(stockWord) ~= "string" or type(name) ~= "string" then
        return nil
    end
    local s, e = format:find(stockWord, 1, true)
    if not s then return nil end
    return format:sub(1, s - 1) .. name .. format:sub(e + 1)
end

-- Fill PowerBarColor and the three strings for every generated power token that
-- the client does not already know.
function PS.Apply()
    for token, power in pairs(Diablocraft.PowerTokens or {}) do
        local slotToken = slotTokenFor(token)
        if slotToken and slotToken ~= token then
            if type(PowerBarColor) == "table" then
                PowerBarColor[token] = {r = power.r, g = power.g, b = power.b}
            end
            local stockWord = _G[slotToken]
            _G[token] = power.name
            for _, suffix in ipairs({"_COST", "_COST_PER_TIME"}) do
                local format = PS.CostFormat(_G[slotToken .. suffix], stockWord, power.name)
                if format then _G[token .. suffix] = format end
            end
        end
    end
end

-- At load, before ResourceText.lua reads the PowerBarColor keys and before any
-- frame draws a bar.
PS.Apply()
