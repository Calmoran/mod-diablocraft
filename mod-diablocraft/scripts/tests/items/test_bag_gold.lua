-- luacheck: globals ElvUI CreateFrame hooksecurefunc UnitName UnitGUID SendChatMessage SlashCmdList
-- luacheck: ignore 111 121 122 431 631
-- Run from the repo root with `lua mod-diablocraft/scripts/tests/items/test_bag_gold.lua`.
--
-- Mocks the client and ElvUI's Bags module around the production files
-- client-patch/addons/Torment/Economy.lua and
-- client-patch/addons/ElvUI_Torment/bags.lua, and pins the bag gold counter
-- (diablocraft-bag-gold-torment, ruling 2026-10-02): ElvUI's bag line shows the
-- Torment account balance through the one shared formatter and the character
-- sheet's own coin, never the character's GetMoney(), and it never shows WoW
-- money before the snapshot lands.
--
-- Mocks do NOT prove pixels: what the designer sees is on his card in
-- docs/test-diablocraft-bag-gold-torment.md.
--
-- The ElvUI side is 6.09's real shape: `B.BagFrame.goldText` is a plain
-- FontString (Bags.lua:1295-1298), `B:UpdateGoldText` writes
-- `E:FormatMoney(GetMoney(), ...)` into it (Bags.lua:1018-1020), and ElvUI's
-- money events call that function. The mock's `UpdateGoldText` stamps a string
-- derived from GetMoney so "the stock digits never survive" is a real check.

unpack = unpack or table.unpack

-- ------------------------------------------------------- guarded client env

local hooked = {}

local clientGlobals = {
    assert = assert, error = error, ipairs = ipairs, pairs = pairs, next = next, select = select,
    tostring = tostring, tonumber = tonumber, type = type, unpack = unpack, print = print,
    math = math, string = string, table = table,
}

-- The one global table the loaded files share, exactly as the client has one.
local env
clientGlobals.UnitName = function() return "Tester" end
clientGlobals.UnitGUID = function() return "Player-1" end
clientGlobals.SendChatMessage = function() end
clientGlobals.DEFAULT_CHAT_FRAME = {AddMessage = function() end}
clientGlobals.DiablocraftUI = {}
-- The Torment addon's own global does not exist until Economy.lua makes it; the
-- guard needs the name known-but-nil so `Diablocraft = Diablocraft or {}` works.
clientGlobals.Diablocraft = false

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

-- The one shared strict widget mock (diablocraft-yey2) owns every widget and
-- the globals a widget needs: CreateFrame, UIParent, UISpecialFrames,
-- StaticPopupDialogs, GameTooltip, UIErrorsFrame, hooksecurefunc, tinsert,
-- SlashCmdList. Pre-seed the two the mock reads before it writes.
env.SlashCmdList = {}
env.StaticPopupDialogs = {}

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install(env)
Mock.setScreen(1024, 768)
local frames = Mock.frames

-- The mock owns hooksecurefunc; the test keeps its own record of what was
-- hooked so "ElvUI's UpdateGoldText is hooked, never replaced" stays a check.
local mockHook = env.hooksecurefunc
function env.hooksecurefunc(a, b, c)
    if type(a) == "string" then
        hooked[#hooked + 1] = {target = a}
        return mockHook(a, b)
    end
    hooked[#hooked + 1] = {target = a, method = b}
    return mockHook(a, b, c)
end

Mock.widget("Frame", "CharacterFrame")
-- The stock backpack is closed, as it starts in the client, so the economy
-- hook's ContainerFrame_Update refresh (a no-op here) stays out of the way.
local container = Mock.widget("Frame", "ContainerFrame1")
container:Hide()

local function loadWith(path)
    if setfenv then
        local chunk = assert(loadfile(path))
        setfenv(chunk, env)
        return chunk()
    end
    return assert(loadfile(path, "t", env))()
end

-- --------------------------------------------------------------- ElvUI mock

-- The character's WoW money, distinct from every balance below so a leak is
-- visible: 999900 copper formats as "99g 99s" under 6.09's own FormatMoney.
local GetMoney = function() return 999900 end

local goldText
do
    local text = {}
    function text:SetText(value) self.text = value end
    goldText = text
end

local originalGoldCalls = 0
local B = {BagFrame = {goldText = goldText}}
function B:UpdateGoldText()
    originalGoldCalls = originalGoldCalls + 1
    -- Bags.lua:1019: E:FormatMoney(GetMoney(), ...) - the stock digits.
    self.BagFrame.goldText:SetText(tostring(GetMoney()) .. "|cffc7c7cfs|r")
end
B.FormatMoney = function(_, amount) return tostring(amount) end

local E = {
    Modules = {Bags = B},
    GetModule = function(self, name) return self.Modules[name] end,
    NewModule = function(self, name) local m = {}; self.Modules[name] = m; return m end,
    RegisterModule = function() end,
    Print = function() end,
}
ElvUI = {E}
clientGlobals.ElvUI = ElvUI

-- ------------------------------------------------------- the stock money frame

-- What MoneyFrame_Update stamps before any hook: the WoW money of the frame.
local function moneyFrame(name, moneyType)
    local frame = {name = name, moneyType = moneyType}
    env[name] = frame
    for _, which in ipairs({"Gold", "Silver", "Copper"}) do
        local button = {shown = true}
        function button:Show() self.shown = true end
        function button:Hide() self.shown = false end
        env[name .. which .. "Button"] = button
        local text = {text = "0", shown = true}
        function text:SetText(value) self.text = value end
        env[name .. which .. "ButtonText"] = text
    end
    return frame
end

function env.MoneyFrame_Update(frameName, money)
    local name = type(frameName) == "table" and frameName:GetName() or frameName
    local gold = env[name .. "GoldButtonText"]
    if gold then gold:SetText(tostring(money)) end
    local silver = env[name .. "SilverButtonText"]
    if silver then silver:SetText("0") end
    local copper = env[name .. "CopperButtonText"]
    if copper then copper:SetText("0") end
end

-- The stock backpack's money frame (ContainerFrame.xml:157: a PLAYER small money
-- frame) and a merchant price (MerchantFrame.xml:93: STATIC).
moneyFrame("ContainerFrame1MoneyFrame", "PLAYER")
moneyFrame("MerchantFrameMoneyFrame", "STATIC")

-- --------------------------------------------- the merchant window's own API

-- Economy.lua reads these on the merchant window (the Blood Shard foot line,
-- kadala.md 4.11(a)): the window itself, the player's money frame at its foot, and
-- the stock update and cost calls. The foot line's behaviour is
-- test_merchant_shards.lua's; these are here because the 3.3.5a client has them and
-- the loaded file must find what it calls. The stock window starts hidden
-- (MerchantFrame.xml: hidden="true"), as it does here.
local merchant = Mock.widget("Frame", "MerchantFrame")
merchant:Hide()
Mock.widget("Frame", "MerchantMoneyFrame")
env.MAX_ITEM_COST = 3
function env.GetMerchantNumItems() return 0 end
function env.GetMerchantItemCostItem() return nil end
function env.GetItemIcon() return nil end
function env.MerchantFrame_Update() end

-- ---------------------------------------------------------------- load it all

loadWith("client-patch/addons/Torment/Economy.lua")
local Econ = assert(env.Diablocraft and env.Diablocraft.Econ, "Diablocraft.Econ is exported")

loadWith("client-patch/addons/ElvUI_Torment/bags.lua")

local watcher
for _, frame in ipairs(frames) do
    if frame.scripts.OnEvent and frame.events.CHAT_MSG_ADDON then watcher = frame end
end
assert(watcher, "the economy watcher is installed")

local function addon(prefix, payload, sender)
    watcher.scripts.OnEvent(watcher, "CHAT_MSG_ADDON", prefix, payload, "WHISPER", sender or "Tester")
end

-- The sheet's own coin: the bag line's coin must be the same art file the
-- character sheet's footer draws (Inventory.lua -> DC.SetArt(coin, "coin")).
local art = assert(io.open("client-patch/addons/Torment/ArtSlots.lua")):read("*a")
local coinFile = assert(art:match('%["coin"%]%s*=%s*{%s*file%s*=%s*"([%w_]+)"'), "ART.coin has a file")
local artPath = assert(art:match('ART_PATH%s*=%s*%[%[(.-)%]%]'))
local COIN = "|T" .. artPath .. coinFile .. ":14:14|t"

local BALANCE = "1234567"
local VALID = "1;normal;1;" .. BALANCE .. ";102000=5"

-- ------------------------------------------------- 1. nothing before the snapshot

assert(Econ.Balance() == nil, "no snapshot yet")
B:UpdateGoldText()
assert(goldText.text == "", "before the snapshot the line is empty, not WoW money: got " .. tostring(goldText.text))
assert(originalGoldCalls == 1, "ElvUI's own update still ran (it is hooked, not replaced)")

-- --------------------------------------------- 2. the formatter's output, and the coin

addon("DCECON", VALID)
assert(Econ.Balance() == BALANCE, "the snapshot is accepted")
assert(goldText.text == Econ.Gold(BALANCE) .. " " .. COIN,
    "the line is the shared formatter plus the sheet's coin, got " .. tostring(goldText.text))
assert(Econ.Gold(BALANCE) == "1,234,567", "the formatter groups in threes: got " .. Econ.Gold(BALANCE))
assert(goldText.text:find(COIN, 1, true), "the sheet's coin art is on the line")

-- ------------------------------------------------- 3. never the character's money

assert(not goldText.text:find(tostring(GetMoney()), 1, true), "the WoW money figure is not on the line")
assert(goldText.text ~= tostring(GetMoney()), "and the line is not GetMoney()'s value")

-- ----------------------------------------------- 4. ElvUI redrawing cannot undo it

B:UpdateGoldText()
B:UpdateGoldText()
assert(originalGoldCalls == 3, "the stock update ran every time")
assert(goldText.text == Econ.Gold(BALANCE) .. " " .. COIN,
    "after ElvUI redraws, the balance is still the line, got " .. tostring(goldText.text))
assert(not goldText.text:find(tostring(GetMoney()), 1, true), "and the stock digits never survive")

-- --------------------------------------------------------- 5. it follows a snapshot

addon("DCECON", "1;normal;2;9876543210;102000=6")
assert(Econ.Balance() == "9876543210", "the newer revision is accepted")
assert(goldText.text == Econ.Gold("9876543210") .. " " .. COIN,
    "a new revision redraws the line at once, got " .. tostring(goldText.text))
assert(Econ.Gold("9876543210") == "9,876,543,210", "past a Lua double still exact: got " .. Econ.Gold("9876543210"))

-- An old revision is ignored, so the line keeps the newer balance.
addon("DCECON", VALID)
assert(goldText.text == Econ.Gold("9876543210") .. " " .. COIN, "an older revision does not move the line")

-- A clear drops it back to nothing, never WoW money.
addon("DCECON", "clear")
assert(goldText.text == "", "a cleared snapshot empties the line, got " .. tostring(goldText.text))
B:UpdateGoldText()
assert(goldText.text == "", "and ElvUI's own redraw cannot bring WoW money back")
addon("DCECON", "1;normal;1;" .. BALANCE)
assert(goldText.text == Econ.Gold(BALANCE) .. " " .. COIN, "a fresh snapshot restores the balance")

-- ------------------------------------------- 6. the no-ElvUI path: the stock backpack

-- The stock backpack money frame is a PLAYER frame; Economy's MoneyFrame_Update
-- hook rewrites it, and before the snapshot blanks it.
env.MoneyFrame_Update("ContainerFrame1MoneyFrame", GetMoney())
assert(env.ContainerFrame1MoneyFrameGoldButtonText.text == Econ.Gold(BALANCE),
    "the stock backpack money frame shows the account balance, got "
        .. tostring(env.ContainerFrame1MoneyFrameGoldButtonText.text))
assert(env.ContainerFrame1MoneyFrameSilverButton.shown == false
    and env.ContainerFrame1MoneyFrameCopperButton.shown == false, "and hides the coins Torment has no use for")

addon("DCECON", "clear")
env.MoneyFrame_Update("ContainerFrame1MoneyFrame", GetMoney())
assert(env.ContainerFrame1MoneyFrameGoldButton.shown == false,
    "before the snapshot the stock backpack money frame is blank, never WoW money")
assert(env.ContainerFrame1MoneyFrameSilverButton.shown == false
    and env.ContainerFrame1MoneyFrameCopperButton.shown == false, "and its coins are hidden too")

-- A price frame (STATIC) is left exactly as the stock function wrote it.
env.MoneyFrame_Update("MerchantFrameMoneyFrame", 4242)
assert(env.MerchantFrameMoneyFrameGoldButtonText.text == "4242", "a STATIC price frame is untouched")
assert(env.MerchantFrameMoneyFrameGoldButton.shown ~= false, "and stays shown")

addon("DCECON", "1;normal;1;" .. BALANCE)
env.MoneyFrame_Update("ContainerFrame1MoneyFrame", GetMoney())
assert(env.ContainerFrame1MoneyFrameGoldButtonText.text == Econ.Gold(BALANCE), "and the backpack follows the balance again")

-- ---------------------------------- 7. no leftover account panel on CharacterFrame

-- UI fixes row 10 (ruling 2026-10-03): the stage-1 account panel under the stock
-- CharacterFrame is gone. The balance and the materials are on the Torment sheet's
-- one panel (decisions.md 2026-10-01 item 3), so after every snapshot above no
-- such frame exists and nothing hooks the stock frame.
for _, frame in ipairs(frames) do
    assert(frame.name ~= "DiablocraftAccountPanel", "no account panel is built on CharacterFrame")
end
assert(Econ.RefreshSheet == nil, "and the refresh that drew it is gone")
assert(next(env.CharacterFrame.scripts) == nil, "nothing hooks the stock CharacterFrame")

-- ------------------------------------------------------------------- the hooks

local found = false
for _, entry in ipairs(hooked) do
    if entry.target == B and entry.method == "UpdateGoldText" then found = true end
end
assert(found, "ElvUI's UpdateGoldText is hooked with hooksecurefunc, never replaced")
assert(type(B.FormatMoney) == "function" and B.FormatMoney(nil, 5) == "5", "ElvUI's other functions are untouched")

print("test_bag_gold: ok")
