local AIO = AIO or require("AIO")

-- luacheck: globals DCTunables DCThrottle DCUI DCTier RegisterGroupEvent ChatFrame1Tab
-- The Difficulty button and window (contract
-- docs/contracts/tier-messages.md). The server decides every row, lock, reason and who may pick; C++
-- (`dc tierselect`) re-checks all of it on the pick. The client sends only the tier picked.

if AIO.AddAddon() then
    local handlers = AIO.AddHandlers("DiablocraftTier", {})

    local HUB_ONLY = "Choose difficulty in the hub."          -- C++ ChooseTier's own text
    local LEADER_ONLY = "Only the party leader may choose difficulty." -- DC::SelectTier's text
    local PARTY_HUB_ONLY = "All online party members must be in the Sanctum to change difficulty." -- DC::PartyMemberReady's text

    -- The full joined tier list, or nil when the query is unavailable. A false
    -- return means the tier ids are not contiguous from 1, which
    -- DC::UnlockRules rejects: the configuration is invalid, so no launch tiers
    -- are offered.
    local function loadTiers()
        local result = WorldDBQuery("SELECT p.tier_id,p.tier_name,t.monster_health_multiplier_pct,t.monster_damage_multiplier_pct,t.xp_bonus_pct,t.gold_bonus_pct,t.unlock_character_level,t.unlock_account_level,t.unlock_solo_gr FROM dc_tier_phase p JOIN dc_difficulty_tiers t ON t.tier=p.tier_name ORDER BY p.tier_id")
        if not result then return nil end
        local tiers, expected = {}, 1
        repeat
            local id = result:GetUInt32(0)
            if id ~= expected then return false end
            expected = expected + 1
            tiers[#tiers + 1] = {
                id = id,
                name = result:GetString(1),
                health = result:GetUInt32(2),
                damage = result:GetUInt32(3),
                xp = result:GetUInt32(4),
                gold = result:GetUInt32(5),
                characterLevel = result:GetUInt32(6),
                accountLevel = result:GetUInt32(7),
                soloGr = result:GetUInt32(8),
            }
        until not result:NextRow()
        return tiers
    end

    -- DC::LaunchTierCount parity: a finite whole number in 1..rowcount, where
    -- rowcount is the FULL joined list, not the eligible count. Anything else
    -- (6.5, 0, negative, non-finite, past the joined rows) is C++'s
    -- invalid-configuration state and offers no tiers at all.
    local function launchCount(rowcount)
        local value = DCTunables.Or("monsters", "launch_tier_count", 0)
        if type(value) ~= "number" or value ~= value
           or value == math.huge or value == -math.huge then return 0 end
        if value ~= math.floor(value) or value < 1 or value > rowcount then return 0 end
        return value
    end

    -- Why a tier is locked for this character, or "" when it is not: DC::MeetsTierUnlock's
    -- columns in order. A solo Greater Rift requirement fails closed (no launch tier has one).
    local function lockReason(tier, level, accountLevel)
        if level < tier.characterLevel then return "Requires character level " .. tier.characterLevel .. "." end
        if accountLevel < tier.accountLevel then
            return "Requires a level " .. tier.accountLevel .. " character on this account."
        end
        if tier.soloGr ~= 0 then return "Requires Greater Rift " .. tier.soloGr .. " cleared solo." end
        return ""
    end

    -- Every launch tier with its lock reason, and the set of unlocked ids; both nil if the data
    -- is unavailable.
    local function tierRows(player)
        local tiers = loadTiers()
        if tiers == nil then return nil, nil end
        local list = tiers or {}          -- false = non-contiguous: no tiers
        local count = launchCount(#list)
        local level = player:GetLevel()
        -- Account level: this character's level, or the account's highest when
        -- greater (dc_difficulty.cpp SelectTier queries MAX(level) the same way).
        local accountLevel = level
        local account = CharDBQuery("SELECT MAX(level) FROM characters WHERE account=" .. player:GetAccountId())
        if account then accountLevel = math.max(accountLevel, account:GetUInt32(0)) end
        local unlocked, rows = {}, {}
        for _, tier in ipairs(list) do
            if tier.id <= count then
                local reason = lockReason(tier, level, accountLevel)
                if reason == "" then unlocked[tier.id] = true end
                rows[#rows + 1] = {tier.id, tier.name, tier.health, tier.damage, tier.xp, tier.gold, reason}
            end
        end
        return unlocked, rows
    end

    -- DC::World::IsInHub from the same row C++ reads at startup.
    local hub
    local spawn = WorldDBQuery("SELECT map_id,area_id FROM dc_world_hub_point WHERE name='spawn'")
    if spawn then hub = {map = spawn:GetUInt32(0), area = spawn:GetUInt32(1)} end
    local function inHub(player, area)
        return hub ~= nil and player:GetInstanceId() == 0 and player:GetMapId() == hub.map
            and (area or player:GetAreaId()) == hub.area
    end

    -- "" when this player may pick now, otherwise why not. Combat and the cooldown stay C++'s.
    local function pickReason(player)
        if not inHub(player) then return HUB_ONLY end
        local group = player:GetGroup()
        if group and not group:IsLeader(player:GetGUID()) then return LEADER_ONLY end
        -- GetMembers lists online players only, as C++ skips the offline ones.
        if group then
            for _, member in ipairs(group:GetMembers()) do
                if not inHub(member) then return PARTY_HUB_ONLY end
            end
        end
        return ""
    end

    local function currentTier(player)
        local current = CharDBQuery("SELECT tier FROM dc_character_tier WHERE guid=" .. player:GetGUIDLow())
        return current and current:GetUInt32(0) or 1
    end

    -- The button: shown only in the hub, reading the current tier's name.
    local function sendState(player, area)
        if not inHub(player, area) then AIO.Handle(player, "DiablocraftTier", "State", false) return end
        local tiers = loadTiers()
        local tier = tiers and tiers[currentTier(player)]
        AIO.Handle(player, "DiablocraftTier", "State", true, tier and tier.name)
    end

    local function show(player)
        local _, rows = tierRows(player)
        if not rows then player:SendBroadcastMessage("Difficulty data is unavailable."); return end
        AIO.Handle(player, "DiablocraftTier", "Show", rows, currentTier(player), pickReason(player))
    end

    local function guidsOf(group)
        local guids = {}
        for _, member in ipairs(group:GetMembers()) do guids[#guids + 1] = member:GetGUID() end
        return guids
    end
    local function sendStates(guids)
        for _, guid in ipairs(guids) do
            local member = GetPlayerByGUID(guid)
            if member then sendState(member) end
        end
    end

    -- Security G1: every handler queries the DB; drop a flood.
    function handlers.State(player)
        if DCThrottle.Allow(player, "tier:state", 5, 10) then sendState(player) end
    end
    function handlers.Open(player)
        if DCThrottle.Allow(player, "tier:open", 5, 10) then show(player) end
    end
    function handlers.Select(player, id)
        if type(id) ~= "number" or id ~= math.floor(id) then return end
        if not DCThrottle.Allow(player, "tier:select", 5, 10) then return end
        -- Recompute now rather than trust the client's payload: a locked, out-of-range or
        -- not-yours-to-pick id is refused here, as C++ would refuse it.
        local unlocked = tierRows(player)
        if not unlocked or not unlocked[id] or pickReason(player) ~= "" then return end
        -- Run as this player, never as console. C++ performs every authorization
        -- and unlock check and mutates phase/storage; Lua never scales stats.
        player:RunCommand("dc tierselect " .. id)
        show(player)
        local group = player:GetGroup()
        if group then sendStates(guidsOf(group)) else sendState(player) end
    end

    RegisterPlayerEvent(47, function(_, player, _, newArea) sendState(player, newArea) end) -- area change
    -- A join or a new leader: C++'s SyncGroup stores the leader's tier in its own hook, so the
    -- button is told on the next world tick, after every hook has run.
    local function groupChanged(_, group)
        local guids = guidsOf(group)
        CreateLuaEvent(function() sendStates(guids) end, 1, 1)
    end
    RegisterGroupEvent(1, groupChanged) -- member added
    RegisterGroupEvent(4, groupChanged) -- leader changed
    return
end

local U = DCUI or error("dc_aio_ui.lua must load before dc_tier.lua")
local handlers = AIO.AddHandlers("DiablocraftTier", {})
DCTier = {}

-- The window: one row per tier, name then Life, Damage, XP and Gold in aligned columns.
local VISIBLE = 12
local LIST_WIDTH = 492
-- Column: header, right edge in the row, width.
local COLUMNS = {{"Life", 300, 80}, {"Damage", 380, 80}, {"XP", 436, 56}, {"Gold", 488, 56}}
local frame = U.window("DiablocraftTierFrame", 560, 150 + VISIBLE * U.ROW_HEIGHT, "tier")
U.title(frame, "Difficulty")
local subtitle = U.subtitle(frame)
U.close(frame)

local header = U.text(frame, 28, -68, 180, "GameFontNormal")
header:SetText("Difficulty")
for _, column in ipairs(COLUMNS) do
    local text = U.text(frame, 22 + column[2] - column[3], -68, column[3], "GameFontNormal", "RIGHT")
    text:SetText(column[1])
end

local listBox = CreateFrame("Frame", nil, frame)
listBox:SetPoint("TOPLEFT", 18, -86); listBox:SetSize(524, VISIBLE * U.ROW_HEIGHT + 8)
U.flat(listBox, U.DETAIL_BG[1], U.DETAIL_BG[2], U.DETAIL_BG[3], U.DETAIL_BORDER[1], U.DETAIL_BORDER[2], U.DETAIL_BORDER[3])
local scroll = U.scroll(CreateFrame("ScrollFrame", "DiablocraftTierScroll", listBox, "UIPanelScrollFrameTemplate"))
scroll:SetPoint("TOPLEFT", 4, -4); scroll:SetSize(LIST_WIDTH, VISIBLE * U.ROW_HEIGHT)
local list = CreateFrame("Frame", nil, scroll); list:SetSize(LIST_WIDTH, VISIBLE * U.ROW_HEIGHT); scroll:SetScrollChild(list)
local note = U.text(frame, 20, -102 - VISIBLE * U.ROW_HEIGHT, 520, "GameFontHighlightSmall", "CENTER")
U.colour(note, U.RED)

local rows, current, pick = {}, nil, ""

local function percent(value, sign) return (sign or "") .. U.number(value) .. "%" end

local function click(row)
    if row.reason ~= "" then note:SetText(row.reason)
    elseif pick ~= "" then note:SetText(pick)
    elseif row.tierId ~= current then AIO.Handle("DiablocraftTier", "Select", row.tierId) end
end

local function rowAt(index)
    if rows[index] then return rows[index] end
    local row = U.row(list)
    row:SetWidth(LIST_WIDTH); row:SetPoint("TOPLEFT", 0, -(index - 1) * U.ROW_HEIGHT)
    row.label:SetPoint("LEFT", U.HEAD_INDENT + 2, 0)
    row.cells = {}
    for i, column in ipairs(COLUMNS) do
        row.cells[i] = U.text(row, column[2] - column[3], -2, column[3], "GameFontHighlight", "RIGHT")
    end
    row:SetScript("OnClick", click)
    row:SetScript("OnEnter", function(self)
        if self.reason ~= "" then
            U.tooltip(self, function(tip) tip:SetText(self.label:GetText()); tip:AddLine(self.reason, U.RED[1], U.RED[2], U.RED[3]) end)
        end
    end)
    row:SetScript("OnLeave", function() GameTooltip:Hide() end)
    rows[index] = row
    return row
end

-- `rows` are the server's {id, name, life, damage, xp, gold, reason}; `reason` "" = unlocked.
-- `pickReason` "" = this player may pick now.
function handlers.Show(_, payload, currentId, pickReason)
    payload, current, pick = payload or {}, currentId, pickReason or ""
    for index, data in ipairs(payload) do
        local row = rowAt(index)
        row.tierId, row.reason = data[1], data[7] or ""
        row.label:SetText(data[2])
        local values = {percent(data[3]), percent(data[4]), percent(data[5], "+"), percent(data[6], "+")}
        for i, cell in ipairs(row.cells) do cell:SetText(values[i]) end
        local locked = row.reason ~= ""
        U.colour(row.label, locked and U.GREY or U.GOLD)
        for _, cell in ipairs(row.cells) do U.colour(cell, locked and U.GREY or U.WHITE) end
        if row.tierId == current then row.mark:Show() else row.mark:Hide() end
        row:Show()
    end
    for index = #payload + 1, #rows do rows[index]:Hide() end
    list:SetHeight(math.max(1, #payload) * U.ROW_HEIGHT)
    subtitle:SetText(pick ~= "" and pick or "The party leader chooses for everyone.")
    U.colour(subtitle, pick ~= "" and U.RED or U.GREY)
    note:SetText("")
    frame:Show()
end

-- The button just above the chat: ElvUI's left chat panel when ElvUI draws the chat, else the
-- stock chat tab, so it never covers the tabs, the chat's own buttons or the edit box (which
-- sits below the stock chat and inside ElvUI's panel).
-- ponytail: assumes ElvUI's chat module is on whenever LeftChatPanel exists (our default profile).
local button = U.button(UIParent, 130, "Difficulty", function() AIO.Handle("DiablocraftTier", "Open") end)
button:Hide()
local function place()
    button:ClearAllPoints()
    button:SetPoint("BOTTOMLEFT", _G.LeftChatPanel or ChatFrame1Tab, "TOPLEFT", 0, 4)
end
function handlers.State(_, inHub, name)
    if not inHub then button:Hide() return end
    place()
    button:SetText(name or "Difficulty")
    button:Show()
end

SLASH_DIABLOCRAFTTIER1 = "/dctier"
SlashCmdList.DIABLOCRAFTTIER = function() AIO.Handle("DiablocraftTier", "Open") end

DCTier.ui = {frame = frame, rows = rows, button = button, subtitle = subtitle, note = note, list = list}
-- This file runs once per UI load (login or /reload): ask where we are and what tier we are on.
AIO.Handle("DiablocraftTier", "State")
