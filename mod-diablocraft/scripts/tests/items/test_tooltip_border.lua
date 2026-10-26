-- luacheck: ignore 111 112 113 121 122 212 213
-- diablocraft-7gn7: an item tooltip's border in the item's rarity colour. Drives the real
-- dc_tooltip.lua client half (decorate draws the name in DCRARITY) and the real
-- TooltipBorder.lua, loaded in the client's order: the Torment addon first, AIO's code later,
-- ElvUI's OnShow border reset hooked after both (it hooks at login).
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
unpack = unpack or table.unpack
SlashCmdList = {}
DEFAULT_CHAT_FRAME = {AddMessage = function() end}
ShowUIPanel = function(frame) frame:Show() end
GetInventoryItemLink = function() end
for _, name in ipairs({"ItemRefTooltip", "ShoppingTooltip1", "ShoppingTooltip2"}) do CreateFrame("GameTooltip", name) end
-- The client draws each AddLine into <tooltip>TextLeft<n>; line 1 is the name.
for _, name in ipairs({"GameTooltip", "ItemRefTooltip", "ShoppingTooltip1", "ShoppingTooltip2"}) do
    _G[name .. "TextLeft1"] = {
        GetTextColor = function() return unpack(_G[name].lineColors[1] or {1, 1, 1}) end,
        GetText = function() return _G[name].lines[1] end,
    }
end
local STOCK = {1, 1, 1}
for _, tip in ipairs({GameTooltip, ItemRefTooltip, ShoppingTooltip1, ShoppingTooltip2}) do tip:SetBackdropBorderColor(unpack(STOCK)) end
dofile(os.getenv("DC_TOOLTIP_BORDER_LUA") or "client-patch/addons/Torment/TooltipBorder.lua")
local handlers
AIO = {AddAddon = function() return false end, AddHandlers = function(_, h) handlers = h; return h end, Handle = function() end}
dofile("mod-diablocraft/lua/aio/dc_tooltip.lua")
local function item(guid, rarity) return {guid = guid, rarity = rarity, name = rarity .. " item", affixes = {}, level = 1, sell = 1} end
handlers.Set(nil, {[255] = {[0] = item(1, "magic"), [1] = item(2, "rare"), [2] = item(3, "legendary"),
    [3] = item(4, "set"), [4] = item(5, "normal")}})
local function border(tip) return table.concat(tip.borderColor, ",") end
local function colour(c) return table.concat({c[1], c[2], c[3]}, ",") end
local hooks = GameTooltip.scripts
-- A hover the way the client does it: new owner, lines cleared (OnTooltipCleared), the item set
-- (OnTooltipSetItem, where dc_tooltip.lua decorates and calls Show).
local function hover(slot)
    GameTooltip:SetOwner({GetName = function() return "CharacterSlot" end, GetID = function() return slot + 1 end})
    hooks.OnTooltipCleared(GameTooltip)
    GameTooltip.lines = {""}
    hooks.OnTooltipSetItem(GameTooltip)
end
-- Stock UI (no ElvUI): the four rarities, each in the name's own colour.
for slot, rarity in pairs({[0] = "magic", "rare", "legendary", "set"}) do
    hover(slot)
    assert(GameTooltip.dcGuid == slot + 1, "decorated")
    assert(border(GameTooltip) == colour(DCRARITY[rarity]), rarity .. " border, got " .. border(GameTooltip))
end
-- A spell next: the client clears the lines and shows it from C, never through Lua Show.
hooks.OnTooltipCleared(GameTooltip)
assert(border(GameTooltip) == colour(STOCK), "no colour left over, got " .. border(GameTooltip))
-- Stock OnEnter code calls GameTooltip:Show() again after the item is set: a second paint must
-- not take the rarity colour for the default.
hover(2); GameTooltip:Show(); hooks.OnTooltipCleared(GameTooltip)
assert(border(GameTooltip) == colour(STOCK), "shown twice, then cleared: default, got " .. border(GameTooltip))
hover(2); GameTooltip:Hide()
assert(border(GameTooltip) == colour(STOCK), "hidden: back to the default")
hover(4)
assert(border(GameTooltip) == colour(STOCK), "a normal item keeps the default border")
-- ElvUI: TT:SetStyle resets the border in an OnShow hook registered after ours; ours still wins,
-- and its colour is the default we go back to.
local ELV = {.1, .1, .1}
for _, tip in ipairs({GameTooltip, ItemRefTooltip, ShoppingTooltip1, ShoppingTooltip2}) do
    tip:HookScript("OnShow", function(self) self:SetBackdropBorderColor(unpack(ELV)) end)
end
hover(2)
assert(border(GameTooltip) == colour(DCRARITY.legendary), "after ElvUI, got " .. border(GameTooltip))
hooks.OnTooltipCleared(GameTooltip)
assert(border(GameTooltip) == colour(ELV), "ElvUI's own colour is the default, got " .. border(GameTooltip))
hover(4)
assert(border(GameTooltip) == colour(ELV), "normal under ElvUI")
-- Shift-compare: the worn legendary in ShoppingTooltip1 (dc_tooltip.lua matches it by name).
ShoppingTooltip1.lines = {"legendary item"}
ShoppingTooltip1:Show()
assert(border(ShoppingTooltip1) == colour(DCRARITY.legendary), "comparison tooltip, got " .. border(ShoppingTooltip1))
-- A chat link: the frozen copy the server sends, drawn in ItemRefTooltip.
local linked = item("code1", "set"); linked.entry = 100
handlers.SnapshotResult(nil, "code1", linked)
assert(border(ItemRefTooltip) == colour(DCRARITY.set), "chat link, got " .. border(ItemRefTooltip))
-- A stock legendary-quality link (the client draws its name ff8000) in the same ItemRefTooltip:
-- the Torment link before it must not make it read as Torment.
ItemRefTooltip:SetHyperlink("item:19019")
ItemRefTooltip.lines, ItemRefTooltip.lineColors = {"Thunderfury"}, {{1, .5, 0}}
ItemRefTooltip:Show()
assert(border(ItemRefTooltip) == colour(ELV), "stock link after a Torment link: default, got " .. border(ItemRefTooltip))
handlers.SnapshotResult(nil, "code1", linked)
assert(border(ItemRefTooltip) == colour(DCRARITY.set), "the Torment link again")
ItemRefTooltip:Hide()
assert(border(ItemRefTooltip) == colour(ELV), "closed link: default")
assert(ItemRefTooltip.dcGuid == nil, "closed link: forgotten")
-- Primal Ancient: red (the stock RED_FONT_COLOR) on any rarity, from the quality_tier decorate()
-- stamps as dcQualityTier (diablocraft-t3t8); ancient and no tier keep the rarity colour.
RED_FONT_COLOR = {r = 1, g = .1, b = .1}
local RED = {1, .1, .1}
for tier, want in pairs({primal = RED, ancient = DCRARITY.magic, none = DCRARITY.magic}) do
    hover(0); GameTooltip.dcQualityTier = tier ~= "none" and tier or nil; GameTooltip:Show()
    assert(border(GameTooltip) == colour(want), tier .. ": got " .. border(GameTooltip))
end
hover(4); GameTooltip.dcQualityTier = "primal"; GameTooltip:Show()
assert(border(GameTooltip) == colour(RED), "a normal-rarity primal is red too")
hooks.OnTooltipCleared(GameTooltip); GameTooltip:Show()
assert(border(GameTooltip) == colour(ELV), "a tier left on a cleared tooltip paints nothing, got " .. border(GameTooltip))
print("test_tooltip_border: ok")
