-- luacheck: globals DCThrottle
--[[
World of DiabloCraft - the elite affix line (03-difficulty section 5).

Stage 1, deliberately minimal: one plain-text line above the nameplate of a
promoted pack reading its rank and the affixes it rolled. The D3-style
generated name ("Grimtooth the Vile"), the affix icons and the D3 styling are
stage 2 (12-ui U1: builders do not polish stage-1 frames, they keep the message
set complete so the redraw needs no server changes).

The glow, the size and the elite border are not here: they are server-side
effects the stock 3.3.5a client already renders (engine-facts.md Q3.4-Q3.6).
The only thing the client cannot know by itself is which affixes a pack rolled,
because affixes are per spawn and the module holds them in C++.

Keyed by name, not by GUID: a 3.3.5a nameplate exposes only the name text
(there is no GUID on a nameplate frame), and the clone entry's name is what the
client queried. Two packs of the same base creature in one rift therefore share
a line; stage 2's per-pack generated name removes the collision.

The C++ module owns dc_rift_elite and clears it at startup; this file only
reads it and pushes it.
]]

local AIO = AIO or require("AIO")

if AIO.AddAddon() then
    -- ================= server =================
    local handlers = AIO.AddHandlers("DiablocraftElite", {})

    -- Every live pack in the instance the player is standing in. A rift is one
    -- dungeon with a handful of packs alive at a time, so this is the whole
    -- instance rather than a radius: the client draws a line only for the
    -- nameplates it can actually see, which is the range filter that matters.
    local function push(player)
        if not player then
            return
        end
        -- Instance 0 is the open world, and it is a real key rather than "no
        -- packs": a `.dc elite` test pack
        -- is published under it, and the affix line has to draw for it too.
        local instance = player:GetInstanceId() or 0
        local rows = CharDBQuery(
            "SELECT name, elite_rank, affixes FROM dc_rift_elite WHERE instance_id=" .. instance)
        local packs = {}
        if rows then
            repeat
                packs[#packs + 1] = {
                    name = rows:GetString(0),
                    rank = rows:GetString(1),
                    affixes = rows:GetString(2),
                }
            until not rows:NextRow()
        end
        AIO.Handle(player, "DiablocraftElite", "Update", packs)
    end

    -- Security G1: push() queries the DB; drop a flood.
    function handlers.Refresh(player)
        if DCThrottle.Allow(player, "elite:refresh", 5, 10) then push(player) end
    end

    RegisterPlayerEvent(3, function(_, player) push(player) end)        -- login
    RegisterPlayerEvent(28, function(_, player) push(player) end)       -- map change
    RegisterPlayerEvent(7, function(_, killer) push(killer) end)        -- creature kill

    AIO.AddOnInit(function(_, player) push(player) end)
    return
end

-- ================= client =================
local handlers = AIO.AddHandlers("DiablocraftElite", {})

-- name (lowercased) -> the line to draw.
local lines = {}
local labels = setmetatable({}, {__mode = "k"})   -- nameplate frame -> FontString
local REFRESH = 3.0        -- seconds between asking the server for the pack list
local SCAN = 0.2           -- seconds between nameplate sweeps
local BORDER = "Interface\\Tooltips\\Nameplate-Border"

function handlers.Update(_, packs)
    lines = {}
    if type(packs) == "table" then
        for _, pack in ipairs(packs) do
            if type(pack) == "table" and pack.name then
                local text = pack.rank or "Elite"
                if pack.affixes and pack.affixes ~= "" then
                    text = text .. ": " .. pack.affixes
                end
                lines[string.lower(pack.name)] = text
            end
        end
    end
    for plate, label in pairs(labels) do
        if not plate:IsShown() then
            label:Hide()
        end
    end
end

-- ElvUI-WotLK 6.09 (Modules/Nameplates/Nameplates.lua) keeps the Blizzard plate
-- as an invisible shell and draws its own frame as `plate.UnitFrame` (OnCreated,
-- :577); QueueObject (:679-689) blanks the border texture to "" - the Blizzard
-- signature below no longer matches - and hides the old name FontString, which
-- stays readable as UnitFrame.oldName (:613). UnitFrame.Health is its health
-- bar (:583) and UnitFrame.Name its own name text (:587). Anything anchored to
-- the shell sits over nothing, so on ElvUI the label belongs on the UnitFrame.
local function elvFrame(frame)
    local unit = frame.UnitFrame
    if type(unit) == "table" and unit.GetObjectType then
        return unit
    end
    return nil
end

-- A 3.3.5a nameplate is an unnamed child of WorldFrame whose second region is
-- the border texture. This is the only handle the stock client gives an addon.
local function isNamePlate(frame)
    if frame:GetObjectType() ~= "Frame" or frame:GetName() then
        return false
    end
    if elvFrame(frame) then
        return true
    end
    local _, border = frame:GetRegions()
    return border ~= nil and border.GetTexture ~= nil and border:GetTexture() == BORDER
end

-- ElvUI's name text can carry colour codes; the server's name never does.
local function bareName(text)
    return (text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""))
end

local function lineFor(region)
    if type(region) ~= "table" or not region.GetText then
        return nil
    end
    local name = region:GetText()
    if name and lines[string.lower(bareName(name))] then
        return name
    end
    return nil
end

local function plateName(frame)
    local unit = elvFrame(frame)
    if unit then
        -- The untouched Blizzard FontString first, then ElvUI's own text.
        return lineFor(unit.oldName) or lineFor(unit.Name)
    end
    -- WotLK includes cast-bar textures before the name; region four is not
    -- the name FontString. Find the published creature name among the text
    -- regions instead of depending on their order, excluding our own label.
    for _, region in ipairs({frame:GetRegions()}) do
        if region ~= labels[frame] and region:GetObjectType() == "FontString" then
            local name = lineFor(region)
            if name then
                return name
            end
        end
    end
    return nil
end

local function labelFor(frame)
    local unit = elvFrame(frame)
    local label = labels[frame]
    -- The sweep can see a new plate before ElvUI's OnCreated attaches its
    -- UnitFrame, and 3.3.5 recycles plate frames: a label made on the shell
    -- then would stay invisible for good. Re-home it once the UnitFrame exists.
    if label and unit and label:GetParent() ~= unit then
        label:Hide()
        label = nil
    end
    if not label then
        if unit then
            -- Parent and anchor on ElvUI's frame so the label follows its
            -- visibility and alpha, above the health bar when it has one.
            label = unit:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            label:SetPoint("BOTTOM", unit.Health or unit, "TOP", 0, 2)
        else
            label = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            label:SetPoint("BOTTOM", frame, "TOP", 0, 2)
        end
        labels[frame] = label
    end
    return label
end

local scanner = CreateFrame("Frame")
local sinceScan, sinceRefresh, plateCount = 0, 0, 0

scanner:SetScript("OnUpdate", function(_, elapsed)
    sinceRefresh = sinceRefresh + elapsed
    if sinceRefresh >= REFRESH then
        sinceRefresh = 0
        -- Packs are promoted as the player walks into them, and no player event
        -- fires for that, so the client asks inside an instance. The open world
        -- has no promoted packs (03 section 5 open item), but a `.dc elite` test
        -- pack is published there under instance 0, so outside an instance the
        -- client keeps asking while it holds lines and lets the server's answer
        -- clear them; it never wipes them itself.
        if IsInInstance() or next(lines) then
            AIO.Handle("DiablocraftElite", "Refresh")
        end
    end

    sinceScan = sinceScan + elapsed
    if sinceScan < SCAN then
        return
    end
    sinceScan = 0

    local children = { WorldFrame:GetChildren() }
    -- WorldFrame only ever grows a nameplate frame, so a stable child count
    -- means the same frames; the text still has to be re-read every sweep.
    plateCount = #children
    for i = 1, plateCount do
        local frame = children[i]
        if isNamePlate(frame) then
            local label = labels[frame]
            if frame:IsShown() then
                local name = plateName(frame)
                local line = name and lines[string.lower(bareName(name))]
                if line then
                    label = labelFor(frame)
                    label:SetText(line)
                    label:Show()
                elseif label then
                    label:Hide()
                end
            elseif label then
                label:Hide()
            end
        end
    end
end)

SLASH_DIABLOCRAFTELITE1 = "/dcelite"
SlashCmdList.DIABLOCRAFTELITE = function() AIO.Handle("DiablocraftElite", "Refresh") end
