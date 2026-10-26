-- luacheck: ignore 111 112 113 121 122 431 631
-- diablocraft-2qp4: Blood Shards on screen (kadala.md 5 Part 6, 4.11(a)).
--
-- Two halves, one entry. The ledger's material rows are read from
-- data/d3/account_economy.csv, the item's name from the generated item_template
-- row and the number C++ credits from dc_blood_shards.h; the client's Materials
-- panel list (Torment/Economy.lua CURRENCIES) and the server-Lua reader's list
-- (lua/aio/dc_account.lua MATERIALS) must both carry that entry under that name,
-- so a renumbered or renamed Blood Shard row cannot silently drop off the panel
-- or leave the AIO reader reading item counts.
--
-- The merchant window's foot line is driven here through the strict 3.3.5a
-- widget mock: the stock MerchantFrame_Update is hooked (never replaced), and
-- the line must appear only for a list the client shows priced in the shard
-- item, hold the account's shard count (never the gold balance or the
-- character's WoW money), follow a fresh snapshot, and stay off the buyback tab
-- and the closed window. What it looks like in game is the designer's card in
-- docs/test-diablocraft-2qp4.md; a double proves what the addon calls, not what
-- the client draws.
--
-- scripts/tests/items/test_merchant_shards.py runs this file again on a copy of
-- Torment/Economy.lua with one rule taken away, and requires every run to fail.
local ECON_SOURCE = os.getenv("DC_ECON_LUA") or "client-patch/addons/Torment/Economy.lua"
local ACCOUNT_SOURCE = os.getenv("DC_ACCOUNT_LUA") or "mod-diablocraft/lua/aio/dc_account.lua"

local function read(path)
    local file = assert(io.open(path, "r"))
    local text = file:read("*a")
    file:close()
    return text
end

----------------------------------------------------------------------------------------------------
-- The ledger data these screens must agree with
----------------------------------------------------------------------------------------------------

-- account_economy.csv is the verified source; its `material` rows are the account
-- totals every screen lists. (The retired Gold Bar is not one of them.)
local materials, materialCount = {}, 0
for line in read("mod-diablocraft/data/d3/account_economy.csv"):gmatch("[^\r\n]+") do
    local entry, name, kind = line:match("^(%d+),([^,]+),(%a+)")
    if kind == "material" then
        materials[tonumber(entry)] = name
        materialCount = materialCount + 1
    end
end
assert(materialCount > 0, "the ledger CSV yielded no material rows")

-- The number C++ credits, and the name the client's item carries (the generated
-- item_template row build_item.py draws the icon from).
local shardText = assert(read("mod-diablocraft/src/common/dc_blood_shards.h"):match("Entry = (%d+);"),
    "dc_blood_shards.h names no Entry")
local shard = tonumber(shardText)
local shardItemEntry, shardItemName = read("mod-diablocraft/data/generated/account_economy_world.sql")
    :match("%((%d+), %d+, %d+, '([^']+)', %d+, ")
assert(materials[shard] == "Blood Shard", "the credited entry is the ledger's Blood Shard row")
assert(tonumber(shardItemEntry) == shard, "the generated item row is the credited entry")
assert(shardItemName == materials[shard], "the panel's name is the item template's own name")

----------------------------------------------------------------------------------------------------
-- The stub client
----------------------------------------------------------------------------------------------------

local clientGlobals = {
    assert = assert, error = error, ipairs = ipairs, pairs = pairs, next = next, select = select,
    tostring = tostring, tonumber = tonumber, type = type, unpack = unpack, print = print,
    math = math, string = string, table = table,
}
clientGlobals.UnitName = function() return "Tester" end
clientGlobals.UnitGUID = function() return "Player-1" end
clientGlobals.SendChatMessage = function() end
clientGlobals.DEFAULT_CHAT_FRAME = {AddMessage = function() end}
clientGlobals.DiablocraftUI = {}
clientGlobals.Diablocraft = false
-- The shard's icon, as the stock GetItemIcon answers it from the client's Item.dbc.
clientGlobals.GetItemIcon = function(entry) return "Interface\\Icons\\icon" .. tostring(entry) end
-- The stock merchant window's own cost slots and the shard's own icon.
clientGlobals.MAX_ITEM_COST = 3

local env
env = setmetatable({}, {
    __index = function(_, key)
        local value = clientGlobals[key]
        if value == nil then
            error("a loaded file referenced a global unavailable in 3.3.5: " .. tostring(key), 2)
        end
        return value
    end,
})
clientGlobals._G = env

env.SlashCmdList = {}
env.StaticPopupDialogs = {}

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install(env)
Mock.setScreen(1024, 768)
local frames = Mock.frames

Mock.widget("Frame", "CharacterFrame")
Mock.widget("Frame", "ContainerFrame1"):Hide()

-- The stock merchant window: the frame, the player's own money at its foot, and the
-- function every open, page and purchase runs. The line is drawn by the hook on it,
-- never by this function, so the test drives the hook exactly as the client does.
local MerchantFrame = Mock.widget("Frame", "MerchantFrame")
local MerchantMoneyFrame = Mock.widget("Frame", "MerchantMoneyFrame")
MerchantMoneyFrame:SetPoint("BOTTOMRIGHT", MerchantFrame, "BOTTOMRIGHT", -40, 67)
local GoldButton = Mock.widget("Button", "MerchantMoneyFrameGoldButton", MerchantMoneyFrame)
local merchantUpdates, merchantItems, merchantCosts = 0, 0, {}
function env.MerchantFrame_Update()
    merchantUpdates = merchantUpdates + 1
end
function env.GetMerchantNumItems() return merchantItems end
-- (index, slot) -> texture, count, link, as the client answers it from its own
-- ItemExtendedCost.dbc and Item.dbc; a row with no cost answers nothing.
function env.GetMerchantItemCostItem(index, slot)
    local cost = merchantCosts[index] and merchantCosts[index][slot]
    if not cost then return nil end
    return cost.texture, cost.count, cost.link
end
function env.MoneyFrame_Update() end

local function loadWith(path)
    if setfenv then
        local chunk = assert(loadfile(path))
        setfenv(chunk, env)
        return chunk()
    end
    return assert(loadfile(path, "t", env))()
end

loadWith(ECON_SOURCE)
local Econ = assert(env.Diablocraft and env.Diablocraft.Econ, "Diablocraft.Econ is exported")
loadWith(ACCOUNT_SOURCE)
local Account = assert(env.DCAccount, "DCAccount is exported")

-- The one DCECON watcher, as in the client: a self-whisper from the player.
local watcher
for _, frame in ipairs(frames) do
    if frame.scripts.OnEvent and frame.events.CHAT_MSG_ADDON then watcher = frame end
end
assert(watcher, "the economy watcher is installed")
local function addon(payload)
    watcher.scripts.OnEvent(watcher, "CHAT_MSG_ADDON", "DCECON", payload, "WHISPER", "Tester")
end

local function shardLine()
    local found
    for _, frame in ipairs(frames) do
        if frame.kind == "FontString" and frame._name == "DiablocraftMerchantShards" then
            assert(found == nil, "the foot line is built more than once")
            found = frame
        end
    end
    return found
end

local SHARD_ICON = clientGlobals.GetItemIcon(shard)
local SHARD_LINK = "|cffffffff|Hitem:" .. shard .. ":0:0:0:0:0:0:0|h[Blood Shard]|h|r"

-- A vendor priced in Blood Shards: every row's one cost is the shard item. The
-- client draws that cost's icon from its own Item.dbc; its link comes only once the
-- client holds the item, so the icon is the signal that is always there.
local function shardVendor()
    merchantItems, merchantCosts = 2, {}
    for index = 1, 2 do
        merchantCosts[index] = {{texture = SHARD_ICON, count = 25}}
    end
end
-- A stock vendor: gold-priced rows carry no cost at all.
local function goldVendor()
    merchantItems, merchantCosts = 2, {}
end
-- A stock currency vendor: an Emblem cost, priced in something that is not the shard.
local function emblemVendor()
    merchantItems, merchantCosts = 1, {}
    merchantCosts[1] = {{texture = "Interface\\Icons\\inv_misc_emblem", count = 40, link = "|Hitem:47241|h|r"}}
end

local function openMerchant(tab)
    MerchantFrame.selectedTab = tab or 1
    MerchantFrame:Show()
    env.MerchantFrame_Update()
end

----------------------------------------------------------------------------------------------------
-- 1. The Materials panel row comes from the ledger, entry and name together
----------------------------------------------------------------------------------------------------

local seen = {}
for _, currency in ipairs(Econ.CURRENCIES) do
    seen[currency.entry] = currency.name
end
for entry, name in pairs(materials) do
    assert(seen[entry] == name, ("the Materials panel lists %s (%d) under the ledger's name"):format(name, entry))
end
assert(seen[shard] == shardItemName, "and the Blood Shards row is on it")
assert(Econ.Material(shard) == nil, "before a snapshot there is no count")

local listed = {}
for _, entry in ipairs(Account.MATERIALS) do listed[entry] = true end
for entry in pairs(materials) do
    assert(listed[entry], ("the AIO reader counts %d as a material"):format(entry))
end
assert(Account.IsMaterial(shard), "the credited entry is a material, not an item count")

----------------------------------------------------------------------------------------------------
-- 2. The foot line: only a shard-priced list, and only with a count
----------------------------------------------------------------------------------------------------

shardVendor()
openMerchant(1)
assert(shardLine() == nil or not shardLine():IsShown(),
    "no line before the snapshot: the line never invents a zero")

addon("1;normal;4;7654321;102000=9;" .. shard .. "=250")
assert(Econ.Material(shard) == "250", "the snapshot carries the shard count")
local line = assert(shardLine(), "a shard-priced list draws the foot line")
assert(line:IsShown(), "the line is shown")
-- Beside the gold count, on its line (diablocraft-hzlnh, ruling 2026-10-11): the line's
-- right edge hangs off the gold coin button's left edge, level with it, under the stock
-- window and ElvUI's skin (its backdrop on the window) alike.
local function besideGold()
    local point = line.points[1]
    return #line.points == 1 and point[1] == "RIGHT" and point[2] == GoldButton and point[3] == "LEFT"
        and point[4] < 0 and point[5] == 0
end
assert(besideGold(), "the line sits left of the gold count, level with it")
assert(line.text == "|T" .. SHARD_ICON .. ":0:0|t 250",
    "the line is the shard icon at the font's height and the account's count, got " .. tostring(line.text))
assert(not line.text:find("7,654,321", 1, true), "the gold balance is not the shard count")
MerchantFrame.backdrop = Mock.widget("Frame")
env.MerchantFrame_Update()
assert(besideGold(), "under ElvUI's skin the line keeps the same place beside the gold")
MerchantFrame.backdrop = nil

assert(env.MerchantFrame_Update == Mock.hooks.MerchantFrame_Update,
    "the stock update is hooked, never replaced")
local before = merchantUpdates
env.MerchantFrame_Update()
assert(merchantUpdates == before + 1, "and the stock update still runs")

----------------------------------------------------------------------------------------------------
-- 3. Every other vendor draws nothing extra
----------------------------------------------------------------------------------------------------

goldVendor()
env.MerchantFrame_Update()
assert(not shardLine():IsShown(), "a gold vendor draws no foot line")

emblemVendor()
env.MerchantFrame_Update()
assert(not shardLine():IsShown(), "a stock currency vendor draws no foot line")

-- The same price where the client's icon does not read as the shard's (the two
-- calls can spell one icon differently), but the cost's own link names it: still
-- the shard.
merchantItems, merchantCosts = 1, {}
merchantCosts[1] = {{texture = "Interface\\Icons\\some_other_path", count = 25, link = SHARD_LINK}}
env.MerchantFrame_Update()
assert(shardLine():IsShown(), "the shard's own link identifies the price too")

-- A list nobody prices: no line, whatever the player holds.
merchantItems, merchantCosts = 0, {}
env.MerchantFrame_Update()
assert(not shardLine():IsShown(), "an empty list draws no foot line")

----------------------------------------------------------------------------------------------------
-- 4. The buyback tab and the closed window
----------------------------------------------------------------------------------------------------

shardVendor()
openMerchant(2)
assert(not shardLine():IsShown(), "the buyback tab has no shard price to explain")

openMerchant(1)
assert(shardLine():IsShown(), "and her list brings it back")

-- A closed window is not redrawn at all: the line keeps what the client last drew
-- (the client hides a child with its parent).
MerchantFrame:Hide()
goldVendor()
env.MerchantFrame_Update()
assert(shardLine():IsShown(), "the closed window is left alone (the guard returns before any work)")
MerchantFrame:Show()
shardVendor()
env.MerchantFrame_Update()
assert(shardLine():IsShown(), "and her list brings it back")

----------------------------------------------------------------------------------------------------
-- 5. A fresh snapshot and a cleared one
----------------------------------------------------------------------------------------------------

-- The debit a purchase makes arrives as a new revision: the line follows it.
addon("1;normal;5;7654321;102000=9;" .. shard .. "=1250")
assert(shardLine().text == "|T" .. SHARD_ICON .. ":0:0|t 1,250",
    "a new revision redraws the count, grouped, got " .. tostring(shardLine().text))

addon("1;normal;6;7654321;102000=9")  -- a ledger with no shard row at all
assert(not shardLine():IsShown(), "a snapshot without the shard count hides the line")

addon("1;normal;7;7654321;102000=9;" .. shard .. "=0")
assert(shardLine():IsShown() and shardLine().text == "|T" .. SHARD_ICON .. ":0:0|t 0",
    "a real zero is a count and stays up")

-- Logging out drops the snapshot: the line goes with it.
addon("clear")
assert(not shardLine():IsShown(), "a cleared snapshot takes the line down")

----------------------------------------------------------------------------------------------------
-- 6. One line, however many times the window is redrawn
----------------------------------------------------------------------------------------------------

addon("1;normal;8;7654321;102000=9;" .. shard .. "=42")
shardVendor()
for _ = 1, 5 do env.MerchantFrame_Update() end
local built = 0
for _, frame in ipairs(frames) do
    if frame.kind == "FontString" and frame._name == "DiablocraftMerchantShards" then built = built + 1 end
end
assert(built == 1, "the foot line is one FontString, not one per redraw, got " .. built)

print("test_merchant_shards: ok")
