--[[
World of DiabloCraft - the ground-loot label (06-loot, 12-ui U1 stage 1).

The server half summons a carrier creature at the death position, visible to
its owner only, wearing a rarity-coloured beam. This file is the label: the D3
item-name box floating over that drop.

There is no way in 3.3.5a to turn a world position into a screen position, so the
label is the carrier's NAMEPLATE, restyled (docs/research/ground-loot-client.md
part C). A 3.3.5a nameplate is an ordinary frame parented to WorldFrame; addons
find them with WorldFrame:GetChildren() and restyle them. That is what TidyPlates
and PlateBuffs do on this client.

A plate carries no GUID and no unit token, so identity is BUILT: dc_ground_loot.cpp
whispers DCGROUND, the set of carriers the player currently owns as
level|rarity|name triples. That set is authoritative for "this is a loot plate";
the level digit is the cross-check, because levels 1-5 are not exclusive to
carriers and the planned "monsters have no visible level" pass (backlog) will put
a skull on everything else.

V: the client picks the nameplate CVar from the unit's reaction inside
Wow.exe, and the carrier is hostile, so its plate rides on nameplateShowEnemies -
the V key. This addon once took V over so that V could not hide a loot
label. That takeover is removed (loot is normal loot now, so it is not
needed): V and enemy nameplates are the stock client's,
this file never reads or writes the CVar, and if the ground-loot rollback switch
is turned back on, V hides the loot labels with the monster plates.

The pickup: the carrier is invisible, so the label is the thing to click. The
client's own plate click only targets, and only over the plate's native area,
not the whole drawn box. So each loot label carries a
button of ours over exactly the drawn box; its click sends the label (level and
name) to the server as a DCPICKUP addon message, and the server takes the
nearest of the player's drops that draws that label. A click that lands on the
native plate instead and targets the carrier sends the carrier's GUID. Both
reach the same server claim as the right-click
(docs/contracts/ground-loot-messages.md). Out of reach, the server answers F
and the stock "You are too far away." shows in the UI error frame.
]]

local AIO = AIO or require("AIO")

-- luacheck: globals DCTunables
-- luacheck: read globals ERR_USE_TOO_FAR
if AIO.AddAddon() then
    -- Server side: the label's carrier set is pushed by dc_ground_loot.cpp over
    -- the DCGROUND addon whisper. This one handler is the AIO delivery channel
    -- for the sheet values the client's label box needs (docs/contracts/
    -- ground-loot-messages.md): C reads dc_tunables here, the client never holds
    -- the numbers. AddAddon also ships this file to the client.
    local handlers = AIO.AddHandlers("DiablocraftGround", {})
    local function push(player)
        if not player then return end
        AIO.Handle(player, "DiablocraftGround", "Tuning", {
            boxPadX = DCTunables.Or("ui", "ground_loot_label_pad_x", 8),
            boxPadY = DCTunables.Or("ui", "ground_loot_label_pad_y", 3),
            boxAlpha = DCTunables.Or("ui", "ground_loot_label_alpha", 0.72),
        })
    end
    function handlers.Refresh(player) push(player) end
    RegisterPlayerEvent(3, function(_, player) push(player) end)          -- login
    AIO.AddOnInit(function(_, player) push(player) end)
    return
end

-- ============================== client ==============================

-- Tunables, on the sheet as ui.ground_loot_label_pad_x/_pad_y/
-- _alpha. The values arrive from the server over AIO ("DiablocraftGround",
-- "Tuning"; docs/contracts/ground-loot-messages.md) and the literals below are
-- only the defaults until that message lands. sweepSeconds and claimGrace are
-- file internals and stay here.
local TUNING = {
    boxPadX      = 8,     -- box padding left and right of the name, pixels
    boxPadY      = 3,     -- box padding above and below the name, pixels
    boxColour    = {0, 0, 0},
    boxAlpha     = 0.72,  -- backdrop opacity
    sweepSeconds = 0.1,   -- how often plates are re-decided
    claimGrace   = 0.25,  -- seconds after a pickup request in which no other is sent
}

-- The AIO handler that applies the sheet values (client half; only the client
-- reaches here). The request is the project's own AIO pattern: AIO may load
-- this file after PLAYER_LOGIN, so ask unconditionally and let AIO queue it.
local tuningHandlers = AIO.AddHandlers("DiablocraftGround", {})
function tuningHandlers.Tuning(_, tuning)
    if type(tuning) ~= "table" then return end
    if type(tuning.boxPadX) == "number" then TUNING.boxPadX = tuning.boxPadX end
    if type(tuning.boxPadY) == "number" then TUNING.boxPadY = tuning.boxPadY end
    if type(tuning.boxAlpha) == "number" then TUNING.boxAlpha = tuning.boxAlpha end
end
AIO.Handle("DiablocraftGround", "Refresh")

-- What the player owns right now: owned[name][level] = rarity. Replaced whole
-- on every E, never merged, so a despawn removes a label rather than ageing out.
local owned, pending = {}, nil

-- Every plate we have found, and its decomposed regions.
local plates = {}
local lastChildren = 0

-- ---------------------------------------------------------------- the palette

-- dc_tooltip.lua owns the one copy of the D3 rarity palette and exports it as
-- DCRARITY. Read lazily, at the moment a plate is drawn: AIO file load order is
-- not ours to depend on, and by the time a carrier exists everything is loaded.
-- A missing palette draws the name plain rather than inventing a second copy.
local function rarityColour(rarity)
    local palette = DCRARITY
    local colour = palette and palette[rarity]
    if colour then return colour[1], colour[2], colour[3] end
    return 1, 1, 1
end

-- ----------------------------------------------------------- plate anatomy

-- Region ORDER is deliberately not used. The TidyPlates-era snippets index
-- GetRegions() positionally and that order is not the same on every 3.3.5a
-- build, so each region is classified by what it IS instead.
local function collect(frame, parts)
    for index = 1, frame:GetNumRegions() do
        local region = select(index, frame:GetRegions())
        local kind = region and region.GetObjectType and region:GetObjectType()
        if kind == "FontString" then
            parts.fonts[#parts.fonts + 1] = region
        elseif kind == "Texture" then
            parts.art[#parts.art + 1] = region
        end
    end
end

local function decompose(frame)
    local parts = {fonts = {}, art = {}, bars = {}}
    collect(frame, parts)
    for index = 1, frame:GetNumChildren() do
        local child = select(index, frame:GetChildren())
        if child and child.GetObjectType and child:GetObjectType() == "StatusBar" then
            parts.bars[#parts.bars + 1] = child
            collect(child, parts)
        end
    end
    return parts
end

-- A nameplate is an unnamed WorldFrame child that owns a StatusBar (the health
-- bar) and at least two FontStrings (the name and the level). That is structural
-- and needs no texture path, which is the other thing those snippets hard-code.
local function isPlate(frame, parts)
    if frame:GetName() then return false end
    return #parts.bars > 0 and #parts.fonts >= 2
end

-- The level FontString is the one whose text reads as a number; the name is the
-- other. A plate whose text has not been filled in yet classifies as neither and
-- is simply left alone until the next sweep.
local function readPlate(parts)
    local name, level
    for _, font in ipairs(parts.fonts) do
        local text = font:GetText()
        if text and text ~= "" then
            if tonumber(text) then
                level = level or font
            else
                name = name or font
            end
        end
    end
    return name, level
end

-- ------------------------------------------------------------------ the pickup

local PICKUP = "DCPICKUP"
local lastClaimAt = nil

-- One request per physical click, whatever its form. A single click can reach
-- both triggers - the native plate's target change (GUID form) and our
-- button's click (label form) - in either order, and the two bodies differ,
-- so comparing bodies is not enough: two requests could take two drops. Any
-- request inside claimGrace of the last one sent is dropped; two deliberate
-- clicks are further apart than that and each takes a drop.
local function claim(request)
    if not request then return end
    local now = GetTime()
    if lastClaimAt and now - lastClaimAt < TUNING.claimGrace then return end
    lastClaimAt = now
    SendAddonMessage(PICKUP, request, "WHISPER", UnitName("player"))
end

-- The target's GUID when the target is one of our drops, else nil. The server
-- re-checks all of it; this only decides whether a message is worth sending.
local function ownedTarget()
    if not UnitExists("target") then return end
    local name, level = UnitName("target"), UnitLevel("target")
    if name and level and owned[name] and owned[name][level] then
        return UnitGUID("target")
    end
end

-- The label's own click: what the plate draws is all it can name. Nothing
-- here reads or needs the target, so a drop still targeted from a far click
-- is taken by one click once in reach.
local function claimLabel(parts)
    local name, level = readPlate(parts)
    local text, digit = name and name:GetText(), level and tonumber(level:GetText())
    if text and digit and owned[text] and owned[text][digit] then
        claim(digit .. "\t" .. text)
    end
end

-- The button over the drawn box. A child of the frame that owns the name, so
-- it moves and hides with the plate; shown only while the plate is a label.
local function hitArea(parts, owner)
    if not parts.hit then
        local hit = CreateFrame("Button", nil, owner)
        hit:EnableMouse(true)
        hit:RegisterForClicks("LeftButtonUp", "RightButtonUp")
        hit:SetScript("OnClick", function() claimLabel(parts) end)
        parts.hit = hit
    end
    return parts.hit
end

-- --------------------------------------------------------------- the styling

local function box(parts, owner)
    if not parts.box then
        -- Created on whatever frame owns the name, so it is guaranteed to be in
        -- the same frame level and behind the text: BACKGROUND is below the
        -- layer the client draws the name in.
        parts.box = owner:CreateTexture(nil, "BACKGROUND")
        parts.box:SetTexture(TUNING.boxColour[1], TUNING.boxColour[2], TUNING.boxColour[3])
        parts.box:SetAlpha(TUNING.boxAlpha)
    end
    return parts.box
end

-- The client's own artwork: the bars, every texture, and the level digit. Shown
-- or hidden as one, and never the plate frame itself - hiding the frame is what
-- breaks the client's plate recycling, because the client goes on believing the
-- frame is shown and the next unit to reuse it inherits our Hide().
local function setDefaults(parts, shown)
    if parts.defaultsShown == shown then return end
    parts.defaultsShown = shown
    for _, bar in ipairs(parts.bars) do
        if shown then bar:Show() else bar:Hide() end
    end
    for _, texture in ipairs(parts.art) do
        if shown then texture:Show() else texture:Hide() end
    end
end

local function style(frame, parts)
    if not frame:IsShown() then return end
    local name, level = readPlate(parts)
    if not name then
        -- Nothing drawn yet. Leave the plate exactly as the client left it.
        return
    end

    local levelValue = level and tonumber(level:GetText())
    local rarity = levelValue and owned[name:GetText()] and owned[name:GetText()][levelValue]

    if rarity then
        -- A drop of ours. D3's box: no bar, no level, name in the rarity colour.
        setDefaults(parts, false)
        if level then level:Hide() end
        name:Show()
        name:SetTextColor(rarityColour(rarity))
        local plate = box(parts, name:GetParent())
        plate:ClearAllPoints()
        plate:SetPoint("TOPLEFT", name, "TOPLEFT", -TUNING.boxPadX, TUNING.boxPadY)
        plate:SetPoint("BOTTOMRIGHT", name, "BOTTOMRIGHT", TUNING.boxPadX, -TUNING.boxPadY)
        plate:Show()
        -- The whole drawn box is the click target, not only the native plate.
        local hit = hitArea(parts, name:GetParent())
        hit:ClearAllPoints()
        hit:SetAllPoints(plate)
        hit:Show()
        parts.loot = true
        return
    end

    -- A monster. Put back everything we may have taken away on a previous unit,
    -- because the client reuses these frames.
    if parts.box then parts.box:Hide() end
    if parts.hit then parts.hit:Hide() end
    if parts.loot then
        -- The name colour the client set is the unit's reaction colour, and it
        -- is the same colour it puts on the health bar - so the health bar is
        -- where the right colour is read back from rather than remembered.
        local bar = parts.bars[1]
        if bar and bar.GetStatusBarColor then
            name:SetTextColor(bar:GetStatusBarColor())
        else
            name:SetTextColor(1, 1, 1)
        end
        parts.loot = false
    end
    setDefaults(parts, true)
    if level then level:Show() end
    name:Show()
end

local function restyleAll()
    for frame, parts in pairs(plates) do
        style(frame, parts)
    end
end

-- ------------------------------------------------------------- plate discovery

local function adopt(frame)
    local parts = decompose(frame)
    if not isPlate(frame, parts) then return end
    plates[frame] = parts
    -- OnShow is where a recycled frame tells us it now belongs to a different
    -- unit, which is the moment the decision has to be made again.
    frame:HookScript("OnShow", function(self)
        local known = plates[self]
        if known then style(self, known) end
    end)
    style(frame, parts)
end

local function scan()
    local children = WorldFrame:GetNumChildren()
    if children == lastChildren then return end
    lastChildren = children
    for index = 1, children do
        local frame = select(index, WorldFrame:GetChildren())
        if frame and not plates[frame] then adopt(frame) end
    end
end

-- ------------------------------------------------------------------- the wire

-- Same shape as DCSHEET and DCPARAGON: B clears, V carries values well inside one
-- chat packet, E commits. Nothing is drawn from a half-received push.
local function receive(message)
    local fields = {}
    for field in (message .. "|"):gmatch("(.-)|") do fields[#fields + 1] = field end
    local tag = table.remove(fields, 1)
    if tag == "B" then
        pending = {}
    elseif tag == "V" and pending then
        for index = 1, #fields - 2, 3 do
            local level = tonumber(fields[index])
            local rarity, name = fields[index + 1], fields[index + 2]
            if level and rarity and name and name ~= "" then
                pending[name] = pending[name] or {}
                pending[name][level] = rarity
            end
        end
    elseif tag == "F" then
        -- Out of reach (dc_ground_loot.cpp). The stock string, in the frame
        -- and colour the client uses for UI_ERROR_MESSAGE (UIErrorsFrame.lua).
        UIErrorsFrame:AddMessage(ERR_USE_TOO_FAR, 1.0, 0.1, 0.1, 1.0)
    elseif tag == "E" and pending then
        owned = pending
        pending = nil
        restyleAll()
    end
end

-- ------------------------------------------------------------------- the driver

local driver = CreateFrame("Frame")
local elapsed = 0
driver:RegisterEvent("CHAT_MSG_ADDON")
driver:RegisterEvent("PLAYER_ENTERING_WORLD")
driver:RegisterEvent("PLAYER_TARGET_CHANGED")
driver:SetScript("OnEvent", function(_, event, prefix, message, distribution, sender)
    if event == "PLAYER_TARGET_CHANGED" then
        -- A click on the native plate: it targeted the carrier.
        claim(ownedTarget())
    elseif event == "PLAYER_ENTERING_WORLD" then
        -- Carriers do not survive a map change or a logout (dc_ground_loot.cpp
        -- drops the buffer rows), so the set starts empty and the server's next
        -- push fills it. Clearing here stops a label from the map just left.
        owned, pending = {}, nil
        restyleAll()
    elseif event == "CHAT_MSG_ADDON" then
        -- CHAT_MSG_ADDON supplies the distribution before the sender (3.3.5a).
        if prefix ~= "DCGROUND" or distribution ~= "WHISPER" or
           (sender ~= UnitName("player") and sender ~= UnitName("player") .. "-" .. GetRealmName()) then
            return
        end
        receive(message)
    end
end)

driver:SetScript("OnUpdate", function(_, delta)
    elapsed = elapsed + delta
    if elapsed < TUNING.sweepSeconds then return end
    elapsed = 0
    scan()
    -- The sweep is what makes recycling safe: a plate that changed unit without
    -- an OnShow still gets re-decided within one sweep, and a plate the client
    -- re-showed artwork on is put back the way we want it.
    restyleAll()
end)
