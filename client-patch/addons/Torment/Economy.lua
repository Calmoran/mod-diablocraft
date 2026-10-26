-- luacheck: globals MAX_ITEM_COST MerchantFrame MerchantFrame_Update MerchantMoneyFrame
-- luacheck: globals GetMerchantNumItems GetMerchantItemCostItem
-- Diablocraft - account gold and materials, client half (0007).
--
-- The server pushes one DCECON snapshot per committed revision as a self-whisper
-- addon message (src/common/dc_account_economy.cpp Push):
--
--   DCECON<TAB>account;mode;revision;balance;102000=n;...;102005=n
-- The balance field is the server's copper column, which is the
-- displayed gold unit 1:1, so nothing here converts it.
--   DCECON<TAB>clear
--
-- Every total is an exact decimal string and stays one. A Lua number is a double
-- and starts losing digits at 2^53, while an account pool runs to UINT64_MAX, so
-- nothing here calls tonumber on a total, a revision, or a material count.
--
-- This file only displays. It never decides a balance, never sends an amount,
-- and asks for a fresh snapshot with the documented player command and nothing
-- else. The snapshot is authenticated server-side; account and mode arrive with
-- it and are not supplied by the client.

Diablocraft = Diablocraft or {}
local DC = Diablocraft

local Econ = {}
DC.Econ = Econ

local PREFIX = "DCECON"

-- Blood Shards, the account ledger entry Kadala's prices are paid in
-- (account_economy.csv 102007, src/common/dc_blood_shards.h Entry). One literal,
-- used for the Materials panel row and the merchant window's foot line.
local SHARD = 102007

-- The five ARTISAN materials, account_economy.csv. Full names, as the item
-- templates spell them: never an abbreviation. Labels only;
-- the counts come from the server.
--
-- The Greater Rift Keystone (102005) is absent because it is not an artisan
-- material, which is the same reason dc_crafting.lua leaves it off the artisan
-- screens (keystones were only ever meant to come off the
-- crafting screens). Use CURRENCIES below for a list of everything the player
-- holds; Econ.Material(102005) answers either way.
local MATERIALS = {
    {entry = 102001, name = "Reusable Parts"},
    {entry = 102002, name = "Arcane Dust"},
    {entry = 102003, name = "Veiled Crystal"},
    {entry = 102004, name = "Forgotten Soul"},
    {entry = 102000, name = "Death's Breath"},
}
Econ.MATERIALS = MATERIALS

-- Every currency the player holds, for a screen whose whole job is to list them:
-- the inventory's Materials panel (keystones do sit in the
-- character materials panel). Keystones belong here; what they do not belong
-- in is an artisan's material line, which is MATERIALS above.
local CURRENCIES = {
    {entry = 102001, name = "Reusable Parts"},
    {entry = 102002, name = "Arcane Dust"},
    {entry = 102003, name = "Veiled Crystal"},
    {entry = 102004, name = "Forgotten Soul"},
    {entry = 102000, name = "Death's Breath"},
    {entry = 102005, name = "Greater Rift Keystone"},
    {entry = SHARD, name = "Blood Shard"},
    -- The five act reagents (account_economy.csv 102008-102012, bounties W3).
    {entry = 102008, name = "Khanduran Rune"},
    {entry = 102009, name = "Caldeum Nightshade"},
    {entry = 102010, name = "Arreat War Tapestry"},
    {entry = 102011, name = "Corrupted Angel Flesh"},
    {entry = 102012, name = "Westmarch Holy Water"},
    -- Primordial Ashes (account_economy.csv 102013, Kanai's Cube).
    {entry = 102013, name = "Primordial Ashes"},
}
Econ.CURRENCIES = CURRENCIES

-- state ---------------------------------------------------------------------

local snapshot = nil     -- {account, mode, revision, balance, materials, owner}
local listeners = {}
local requested = false

-- digits ---------------------------------------------------------------------

-- tostring prints a Lua number with 14 significant digits ("1.2345678901234e+14"),
-- so a whole number from the client (UnitHealth at 100 trillion and up) goes
-- through %.0f, which prints every digit the double holds.
local function digits(text)
    if type(text) == "number" and text >= 0 and text == math.floor(text) and text < math.huge then
        text = string.format("%.0f", text)
    end
    text = tostring(text or "")
    if text == "" or text:find("%D") then return nil end
    return (text:gsub("^0+(%d)", "%1"))
end

-- The handoff's comparison: normalised length first, then lexicographically.
local function newer(candidate, current)
    if not current then return true end
    if #candidate ~= #current then return #candidate > #current end
    return candidate > current
end

-- THE shared formatter. Every balance and every material
-- count in every Diablocraft screen goes through this one function: the value
-- as it stands, grouped in threes, no unit suffix, no coin split, no rounding
-- and no abbreviation (12-ui U4). One copper is one gold, so there is nothing
-- to convert and nothing below gold to show.
function Econ.Gold(value)
    local out, count = digits(value) or "0", 1
    while count > 0 do
        out, count = out:gsub("^(%d+)(%d%d%d)", "%1,%2")
    end
    return out
end

-- reading the snapshot --------------------------------------------------------

local function owner()
    return (UnitGUID and UnitGUID("player")) or (UnitName and UnitName("player")) or "?"
end

-- nil until an authenticated snapshot for this character has arrived.
function Econ.Get()
    if snapshot and snapshot.owner ~= owner() then snapshot = nil end
    return snapshot
end

-- The account balance as an exact decimal string, in the one displayed unit.
function Econ.Balance()
    local current = Econ.Get()
    return current and current.balance or nil
end

function Econ.Material(entry)
    local current = Econ.Get()
    return current and current.materials[entry] or nil
end

function Econ.OnChange(callback)
    if type(callback) == "function" then listeners[#listeners + 1] = callback end
end

local function changed()
    for _, callback in ipairs(listeners) do
        callback(snapshot)
    end
end

local function clear()
    if not snapshot then return end
    snapshot = nil
    changed()
end
Econ.Clear = clear

-- parsing ---------------------------------------------------------------------

local function parse(payload)
    local fields = {}
    for field in tostring(payload):gmatch("[^;]+") do fields[#fields + 1] = field end
    if #fields < 4 then return nil end
    local account, mode, revision, balance = fields[1], fields[2], fields[3], fields[4]
    if not digits(account) or (mode ~= "normal" and mode ~= "hardcore") then return nil end
    revision, balance = digits(revision), digits(balance)
    if not revision or not balance then return nil end
    local materials = {}
    for index = 5, #fields do
        local entry, amount = fields[index]:match("^(%d+)=(%d+)$")
        if not entry then return nil end
        materials[tonumber(entry)] = (digits(amount))
    end
    return {account = account, mode = mode, revision = revision, balance = balance,
            materials = materials, owner = owner()}
end

local function receive(payload)
    if payload == "clear" then
        clear()
        return
    end
    local fresh = parse(payload)
    if not fresh then return end
    local current = Econ.Get()
    -- A snapshot for a different principal replaces whatever was held; one for
    -- the same principal is only taken when its revision is newer.
    if current and current.account == fresh.account and current.mode == fresh.mode
        and not newer(fresh.revision, current.revision) then
        return
    end
    snapshot = fresh
    if DiablocraftUI then DiablocraftUI.econ = true end
    changed()
end

-- The documented reconnect/request path. Only ever sent on a character that has
-- already had a snapshot in an earlier session, so a server with the feature off
-- is never asked for one.
function Econ.Request()
    if requested then return end
    requested = true
    SendChatMessage(".dc account snapshot", "SAY")
end

-- display ---------------------------------------------------------------------

-- Every money frame of the player's own money shows the account balance whole.
-- There is no silver and no copper any more, so those two coins are hidden
-- rather than zeroed - a "0c" is still a copper figure. This replaces the digits
-- the stock function just wrote, so a later stock update reapplies through the
-- same hook instead of fighting an overlay. Until the authenticated snapshot
-- arrives there is no balance to show and the whole frame is blanked: the
-- character's WoW money is never Torment's number, not even for the moment
-- before the snapshot lands (the bag counter). Trade, mail and
-- vendor prices are STATIC frames and are left exactly as the server sent them.
local function denomination(frameName, which, value)
    local button = _G[frameName .. which .. "Button"]
    if value == nil then
        if button and button.Hide then button:Hide() end
        return
    end
    local fontString = _G[frameName .. which .. "ButtonText"]
    if fontString and fontString.SetText then
        fontString:SetText(value)
    elseif button and button.SetText then
        button:SetText(value)
    end
    if button and button.Show then button:Show() end
end

local function applyMoneyFrame(frame)
    local name = type(frame) == "table" and frame.GetName and frame:GetName() or frame
    if type(name) ~= "string" then return end
    local object = _G[name]
    if not object or object.moneyType ~= "PLAYER" then return end
    local current = Econ.Get()
    -- nil hides the coin as well: nothing, rather than the character's money.
    denomination(name, "Gold", current and Econ.Gold(current.balance) or nil)
    denomination(name, "Silver", nil)
    denomination(name, "Copper", nil)
end
Econ.ApplyMoneyFrame = applyMoneyFrame

-- the merchant window's foot line --------------------------------------------------

-- The stock merchant window shows the player's own money at its foot and nothing
-- else. A Torment vendor whose list is priced in Blood Shards gets the account's count
-- beside that money - the same count the Materials panel shows,
-- at the window that spends it (kadala.md 4.11(a)). Every other vendor, gold or
-- any stock cost, draws nothing extra.
--
-- "Priced in Blood Shards" is read from the window's own costs: no vendor,
-- creature, item or ExtendedCost id is named, so the line follows the data.
local COST_SLOTS = MAX_ITEM_COST or 3
local shardLine

-- A cost is the shard when it is the shard item. The client answers a cost's icon
-- from its own Item.dbc on every open and its link only once it holds the item, so
-- either identifies it; the shard's own icon is asked for once per scan.
local function shardPriced()
    if not GetMerchantNumItems or not GetMerchantItemCostItem then return false end
    local icon = GetItemIcon and GetItemIcon(SHARD) or nil
    for entry = 1, GetMerchantNumItems() do
        for slot = 1, COST_SLOTS do
            local texture, _, link = GetMerchantItemCostItem(entry, slot)
            -- No icon means this slot of the row holds no cost at all (the stock
            -- window hides it), and the slots after it are empty.
            if not texture then break end
            if (icon and texture == icon)
                or (link and link:find("item:" .. SHARD .. ":", 1, true)) then
                return true
            end
        end
    end
    return false
end

-- Built on first use and set on the gold line, left of the gold count (beside
-- the gold, not under it). Left, because right of the count sit
-- the hidden silver and copper slots and then the window's edge. The coin button's left
-- edge is its text's left edge (MoneyFrame.lua: width = text + icon, text at RIGHT
-- -icon), so one anchor holds under the stock window and ElvUI's skin alike, and the
-- line takes the count's own font with the icon at that font's height.
local function merchantLine(frame)
    if not shardLine then
        shardLine = frame:CreateFontString("DiablocraftMerchantShards", "OVERLAY", "NumberFontNormal")
        shardLine:SetJustifyH("RIGHT")
    end
    shardLine:ClearAllPoints()
    shardLine:SetPoint("RIGHT", _G["MerchantMoneyFrameGoldButton"], "LEFT", -8, 0)
    return shardLine
end

local function drawShardLine()
    local frame = MerchantFrame
    if not frame or not frame.IsShown or not frame:IsShown() then return end
    -- Tab 1 is her list; the buyback tab carries no price to explain.
    if frame.selectedTab ~= 1 or not shardPriced() then
        if shardLine then shardLine:Hide() end
        return
    end
    local count = Econ.Material(SHARD)
    -- No snapshot is no count: the line stays empty, the way the money frame beside
    -- it stays blank rather than show the character's own WoW money.
    local line = merchantLine(frame)
    if not count then
        line:Hide()
        return
    end
    local icon = GetItemIcon and GetItemIcon(SHARD)
    line:SetText((icon and ("|T" .. icon .. ":0:0|t ") or "") .. Econ.Gold(count))
    line:Show()
end

-- events -----------------------------------------------------------------------

-- Security G6: DCECON arrives as a server self-whisper, so its sender is the
-- player's own name. Another player whispering the prefix is dropped; a
-- spoofed snapshot must never change the displayed balance.
local function fromServer(sender)
    return sender ~= nil and UnitName ~= nil and sender == UnitName("player")
end

local watcher = CreateFrame("Frame", "DiablocraftEconomyWatcher")
watcher:RegisterEvent("CHAT_MSG_ADDON")
watcher:RegisterEvent("PLAYER_ENTERING_WORLD")
watcher:RegisterEvent("PLAYER_LOGOUT")
watcher:RegisterEvent("PLAYER_LEAVING_WORLD")
watcher:SetScript("OnEvent", function(_, event, arg1, arg2, arg3, sender)
    if event == "CHAT_MSG_ADDON" then
        if arg1 == PREFIX and fromServer(sender) then receive(arg2) end
        return
    end
    if event == "PLAYER_ENTERING_WORLD" then
        DiablocraftUI = DiablocraftUI or {}
        -- The login push is automatic; this only covers a /reload, and only on a
        -- character the server has already sent a snapshot to.
        if DiablocraftUI.econ then Econ.Request() end
        return
    end
    -- Logout, disconnect and leaving the world all drop the snapshot: a stale
    -- account total must never survive into another character or another mode.
    clear()
end)

-- The stage-1 account panel that hung under the stock CharacterFrame is gone: the
-- balance and the materials are on the Torment sheet's one panel.
Econ.OnChange(function()
    if ContainerFrame1 and ContainerFrame1:IsShown() then
        local update = _G["ContainerFrame_Update"]
        if update then update(ContainerFrame1) end
    end
end)

if MoneyFrame_Update then
    hooksecurefunc("MoneyFrame_Update", function(frameName) applyMoneyFrame(frameName) end)
end

-- The foot line follows the window: a fresh list (opening the window, paging it, a
-- purchase's MERCHANT_UPDATE) and a fresh snapshot (the debit that purchase made).
Econ.OnChange(function()
    if MerchantFrame and MerchantFrame.IsShown and MerchantFrame:IsShown() then drawShardLine() end
end)

if MerchantFrame_Update then
    hooksecurefunc("MerchantFrame_Update", drawShardLine)
end

SLASH_DIABLOCRAFTECON1 = "/dcecon"
SlashCmdList.DIABLOCRAFTECON = function()
    requested = false
    Econ.Request()
    local current = Econ.Get()
    if current then
        DEFAULT_CHAT_FRAME:AddMessage("Torment account " .. current.account .. " (" .. current.mode
            .. ") revision " .. current.revision .. ": " .. Econ.Gold(current.balance) .. " gold")
    else
        DEFAULT_CHAT_FRAME:AddMessage("Torment: no account snapshot yet.")
    end
end
