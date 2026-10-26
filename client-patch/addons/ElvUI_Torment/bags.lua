-- luacheck: globals ElvUI Diablocraft hooksecurefunc unpack
-- ElvUI_Torment bag gold counter.
--
-- ElvUI's bag frame draws its own gold line from the character's WoW money
-- (`B:UpdateGoldText` -> `GetMoney()`, Bags.lua:1018-1020 in ElvUI-WotLK 6.09 at
-- 8c0ac9d0). Torment does not use WoW money: the one balance is the account pool
-- in client-patch/addons/Torment/Economy.lua, and the one formatter is Econ.Gold
-- (12-ui U4). This file post-hooks ElvUI's own update and re-writes the line the
-- way the character sheet's footer already draws it - the formatter's exact
-- decimal and the sheet's gold coin. ElvUI's function is hooked, never replaced,
-- and no ElvUI file is touched.
--
-- Before the authenticated DCECON snapshot there is no balance and the line is
-- empty: the character's WoW money is never shown, not even for the moment
-- before the snapshot lands.
--
-- 6.09's bag gold line is a plain FontString with no mouse handling
-- (Bags.lua:1295-1298), so it has no money tooltip to replace or turn off; the
-- container frame's own hover tooltip is the shift-drag move hint
-- (Bags.lua:1146-1152) and is left as it is.
--
-- It needs only ElvUI (loaded first) and the Torment addon (## OptionalDeps:
-- Torment, which publishes Diablocraft.Econ).

local E = unpack(ElvUI)
local B = E:GetModule("Bags")

-- The character sheet's own coin: Torment's gold_coin art, drawn 14x14 there by
-- Inventory.lua's footer (DC.SetArt(coin, "coin")). One art file, so the bag
-- line and the sheet cannot drift apart.
local COIN = "|TInterface\\AddOns\\Torment\\art\\gold_coin:14:14|t"

local function econ()
    local DC = _G.Diablocraft
    return DC and DC.Econ
end

-- The exact string the line must carry: the shared formatter's output for the
-- account balance, then the sheet's coin - or nothing before the snapshot.
local function line()
    local Econ = econ()
    local balance = Econ and Econ.Balance()
    if not balance then return "" end
    return Econ.Gold(balance) .. " " .. COIN
end

local function apply()
    local gold = B and B.BagFrame and B.BagFrame.goldText
    if not gold or not gold.SetText then return end
    gold:SetText(line())
end

-- ElvUI's own update runs first, so the digits it just wrote from GetMoney() are
-- overwritten in the same call. Every path that redraws the line (the money
-- events ElvUI registers) comes through here.
if B and B.UpdateGoldText then
    hooksecurefunc(B, "UpdateGoldText", apply)
end

-- A new revision redraws the line at once, without waiting for ElvUI's next
-- money event.
local Econ = econ()
if Econ then
    Econ.OnChange(apply)
    apply()
end
