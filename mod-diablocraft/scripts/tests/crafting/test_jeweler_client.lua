-- luacheck: globals DCJeweler DCJewelerResponses DiablocraftJewelerGhost ItemSocketingFrame SocketContainerItem SocketInventoryItem
-- luacheck: globals PickupContainerItem PickupInventoryItem GetCursorPosition GetMouseFocus AIO
-- luacheck: globals ContainerFrameItemButton_OnClick PaperDollItemSlotButton_OnClick GetContainerItemLink GetInventoryItemLink InCombatLockdown GetContainerNumFreeSlots Diablocraft CharacterMainHandSlot ContainerFrame1Item1 ContainerFrame1Item3 IsShiftKeyDown IsControlKeyDown IsAltKeyDown
-- luacheck: ignore 111 112 113 121 122 431 432
-- Run from the repo root: lua5.2 mod-diablocraft/scripts/tests/crafting/test_jeweler_client.lua
--
-- diablocraft-jeweler-window: the client half of dc_jeweler.lua against a stub 3.3.5a API. What it pins:
--   * the Combine list: colours A to Z, tiers highest first, "[n] " counts limited by gems, gold and
--     Death's Breath, "Have materials", search, the quantity clamp, one request per click;
--   * the Unsocket Gems tab: an item and its sockets, the stat on THIS item type, drop a gem on a socket,
--     pull a gem off one, swap at the Jeweler;
--   * the Sockets window: opens from the stock Shift+Right-click calls (hooked, never replaced), away from
--     the Jeweler it fills empty sockets and refuses to remove or swap with the Jeweler's own words;
--   * there is no repair verb or button any more.
-- scripts/tests/crafting/test_jeweler_window_lua.py runs this file again on a mutated copy of dc_jeweler.lua per rule
-- (DC_JEWELER_LUA names the copy) and requires every run to fail.

local SOURCE = os.getenv("DC_JEWELER_LUA") or "mod-diablocraft/lua/aio/dc_jeweler.lua"
local UI_SOURCE = os.getenv("DC_UI_LUA") or "mod-diablocraft/lua/aio/dc_aio_ui.lua"

----------------------------------------------------------------------------------------------------
-- The stub client
----------------------------------------------------------------------------------------------------
-- The 3.3.5a widget layer is ONE shared strict mock (diablocraft-yey2): unknown methods,
-- wrong argument counts, a public size field and a texture-less bar all fail here as in the game.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)
local aio, sent = {}, {}
local clock = 0
local cursor, mouseFocus
-- Where the mouse is and whether the left button is down. A frame's rectangle is the mock's `_rect = {left, bottom, width, height}`,
-- set by the test; a frame without one covers nothing, as in the client before layout.
local mouseXY, mouseDown = {9000, 9000}, false
local stock = {pickupContainer = 0, pickupInventory = 0, socketContainer = 0, socketInventory = 0}
local hidden = {}

function UnitName() return "Tester" end
function GetRealmName() return "Diablocraft" end
function GetTime() return clock end
function GetItemIcon(entry) return "icon:" .. tostring(entry) end
function GetItemInfo() return nil end
function GetCursorInfo() if cursor then return "item", cursor.id, "link" end end
function ClearCursor() cursor = nil end
function GetCursorPosition() return mouseXY[1], mouseXY[2] end
function IsMouseButtonDown() return mouseDown end
SlashCmdList = {}
function GetMouseFocus() return mouseFocus end
function SendAddonMessage(prefix, body, distribution, target)
    sent[#sent + 1] = {prefix = prefix, body = body, distribution = distribution, target = target}
end
function HideUIPanel(panel) hidden[#hidden + 1] = panel; panel:Hide() end
-- The stock functions, unreplaced: our code must hook them. hooksecurefunc wraps like the client does.
function PickupContainerItem() stock.pickupContainer = stock.pickupContainer + 1 end
function PickupInventoryItem() stock.pickupInventory = stock.pickupInventory + 1 end
function SocketContainerItem() stock.socketContainer = stock.socketContainer + 1 end
function SocketInventoryItem() stock.socketInventory = stock.socketInventory + 1 end
ItemSocketingFrame = CreateFrame("Frame", "ItemSocketingFrame")
-- The Torment addon's surface the Jeweler meets: the sheet asks every claim registered with ClaimRightClick before it
-- acts on its own worn-slot right-click, and the Jeweler registers one. (There is no drag service to guard any more:
-- the sheet has no grid, diablocraft-inventory-grid-removal.)
Diablocraft = {}
local claims = {}
function Diablocraft.ClaimRightClick(claim) claims[#claims + 1] = claim end
-- The click functions a right-click goes through, as the client's own screens call them. `ran` counts the originals: what
-- the item would have done (equipped, used, taken off) if the window had not taken the click.
local ran = {container = 0, paperdoll = 0}
function ContainerFrameItemButton_OnClick() ran.container = ran.container + 1 end
function PaperDollItemSlotButton_OnClick() ran.paperdoll = ran.paperdoll + 1 end
local linkAt, inCombat, freeSlots = {}, false, 10
function GetContainerItemLink(bag, slot) local id = linkAt[bag .. ":" .. slot]; return id and ("|cffffffff|Hitem:" .. id .. ":0:0|h[x]|h|r") end
function GetInventoryItemLink(_, slot) local id = linkAt["worn:" .. slot]; return id and ("|cffffffff|Hitem:" .. id .. ":0:0|h[x]|h|r") end
function InCombatLockdown() return inCombat end
function GetContainerNumSlots() return 4 end
local keys = {shift = false, ctrl = false, alt = false}
function IsShiftKeyDown() return keys.shift end
function IsControlKeyDown() return keys.ctrl end
function IsAltKeyDown() return keys.alt end
local stockOnClick = {container = ContainerFrameItemButton_OnClick, paperdoll = PaperDollItemSlotButton_OnClick}
function GetContainerNumFreeSlots(bag) if bag == 0 then return freeSlots, 0 end return 0, 0 end
local handlers
AIO = {
    AddAddon = function() return false end,
    AddHandlers = function(_, table_) handlers = table_; return table_ end,
    Handle = function(channel, action, ...) aio[#aio + 1] = {channel = channel, action = action, args = {...}} end,
}

local function lastAio(action)
    for index = #aio, 1, -1 do if aio[index].action == action then return aio[index] end end
end
local function countAio(action)
    local n = 0
    for _, call in ipairs(aio) do if call.action == action then n = n + 1 end end
    return n
end

----------------------------------------------------------------------------------------------------
-- The game's data
----------------------------------------------------------------------------------------------------
local function recipe(id, input, count, gold, breath, name, inputName, colour, tier, rank, have)
    return {id = id, inputEntry = input, inputCount = count, gold = gold, deathsBreath = breath, name = name,
        inputName = inputName, colour = colour, tier = tier, rank = rank, have = have}
end
-- Shuffled on purpose: the window, not the server, puts them in order.
local function recipes()
    return {
        recipe(6103, 6102, 2, 5000, 0, "Square Ruby", "Flawless Ruby", "Ruby", "Square", 3, 100),
        recipe(6002, 6001, 2, 2500, 0, "Flawless Amethyst", "Amethyst", "Amethyst", "Flawless", 2, 20),
        recipe(6202, 6201, 2, 0, 0, "Flawless Diamond", "Diamond", "Diamond", "Flawless", 2, 7),
        recipe(6004, 6003, 3, 1000, 1, "Flawless Square Amethyst", "Square Amethyst", "Amethyst", "Flawless Square", 4, 30),
        recipe(6102, 6101, 2, 2500, 0, "Flawless Ruby", "Ruby", "Ruby", "Flawless", 2, 1),
        recipe(6003, 6002, 2, 5000, 0, "Square Amethyst", "Flawless Amethyst", "Amethyst", "Square", 3, 3),
    }
end
local GEMS = {[6001] = "Amethyst", [6002] = "Flawless Amethyst", [6003] = "Square Amethyst", [6004] = "Flawless Square Amethyst",
    [6101] = "Ruby", [6102] = "Flawless Ruby", [6103] = "Square Ruby", [6201] = "Diamond", [6202] = "Flawless Diamond"}
local EFFECTS = {
    [6002] = {weapon = "+10 Life per Hit", head = "+8% Life", other = "+18 Vitality"},
    [6003] = {weapon = "+35 Life per Hit", head = "+11% Life", other = "+30 Vitality"},
}
local function item87() -- a helm: one gem in socket 0, socket 1 empty
    return {guid = 87, entry = 7001, name = "Visage", bag = 0, slot = 3, slotClass = "head",
        sockets = {{seq = 0, gemEntry = 6003, rank = 3, name = "Square Amethyst"}, {seq = 1, gemEntry = 0, rank = 0, name = "Empty socket"}}}
end
local function item88() -- a weapon with one empty socket, on the character sheet
    return {guid = 88, entry = 7002, name = "Skorn", bag = 255, slot = 15, slotClass = "weapon",
        sockets = {{seq = 0, gemEntry = 0, rank = 0, name = "Empty socket"}}}
end
-- The bag gems, matching what the recipes' `have` says about each input.
local function gems()
    return {{guid = 90, entry = 6002, name = "Flawless Amethyst", count = 2, bag = 0, slot = 1},
        {guid = 96, entry = 6002, name = "Flawless Amethyst", count = 1, bag = 0, slot = 8},   -- a second stack of the same gem
        {guid = 91, entry = 6003, name = "Square Amethyst", count = 30, bag = 0, slot = 2},
        {guid = 92, entry = 6001, name = "Amethyst", count = 20, bag = 0, slot = 4},
        {guid = 93, entry = 6101, name = "Ruby", count = 1, bag = 0, slot = 5},
        {guid = 94, entry = 6102, name = "Flawless Ruby", count = 100, bag = 0, slot = 6},
        {guid = 95, entry = 6201, name = "Diamond", count = 7, bag = 0, slot = 7}}
end
-- Craft Jewelry's catalogue as Show sends it (names, prices, materials from data/d3/jeweler_catalog*.csv; the counts are the
-- player's). The server puts the account materials (the Forgotten Soul) in the same `have` as a bag count.
local function craftRecipe(id, entry, name, page, rarity, required, gold, materials)
    return {id = id, entry = entry, name = name, slot = page == "amulets" and "neck" or "finger", category = page == "amulets" and "Amulet" or "Ring",
        page = page, rarity = rarity, level = 70, required = required, gold = gold, enabled = true, reason = "", materials = materials}
end
local function mat(entry, name, amount, have) return {entry = entry, name = name, amount = amount, have = have} end
local function organs() return {mat(103200, "Leoric's Regret", 1, "1"), mat(103201, "Vial of Putridness", 1, "1"),
    mat(103202, "Idol of Terror", 1, "1"), mat(103203, "Heart of Evil", 1, "1")} end
local function crafts()
    local strength, intelligence = organs(), organs()
    strength[5] = mat(102004, "Forgotten Soul", 10, "25")
    intelligence[5] = mat(102004, "Forgotten Soul", 10, "25")
    return {
        craftRecipe(364042, 100466, "Sovereign Ring", "rings", "rare", 70, "18000",
            {mat(103015, "Marquise Diamond", 1, "5"), mat(103005, "Marquise Amethyst", 1, "5")}),
        craftRecipe(364711, 100943, "Hellfire Ring", "rings", "legendary", 1, "50000", organs()),
        craftRecipe(398284, 101113, "Hellfire Amulet (Strength)", "amulets", "legendary", 1, "50000", strength),
        craftRecipe(364041, 100000, "Sovereign Amulet", "amulets", "rare", 70, "18000",
            {mat(103035, "Marquise Ruby", 1, "2"), mat(103025, "Marquise Emerald", 1, "1"), mat(103045, "Marquise Topaz", 1, "3")}),
        craftRecipe(398285, 101113, "Hellfire Amulet (Intelligence)", "amulets", "legendary", 1, "50000", intelligence),
    }
end
local function showPayload()
    return {items = {item87(), item88()}, gems = gems(), recipes = recipes(), crafts = crafts(), craftMax = 64,
        balance = {gold = "12000", managed = true, deathsBreath = "3"}}
end

----------------------------------------------------------------------------------------------------
-- Load the client half
----------------------------------------------------------------------------------------------------
-- The stock calls the window must hook, not replace: capture them so the wrap is proved after load.
local originals = {PickupContainerItem = PickupContainerItem, SocketContainerItem = SocketContainerItem,
    SocketInventoryItem = SocketInventoryItem}
dofile(UI_SOURCE)
dofile(SOURCE)
local J = DCJeweler
assert(J and J.Logic and J.ui, "dc_jeweler.lua must publish DCJeweler (the logic and its frames)")
local Logic, ui = J.Logic, J.ui
for _, name in ipairs({"PickupContainerItem", "SocketContainerItem", "SocketInventoryItem"}) do
    -- The global must be the wrapper hooksecurefunc installed (Mock.hooks), not a plain
    -- function that calls the stock one: _G[name] ~= originals[name] alone passes a
    -- replacement, which taints the stock click path (diablocraft-s5kn).
    assert(_G[name] == Mock.hooks[name],
        name .. " must be hooked with hooksecurefunc, never replaced")
end

local function click(object) object.scripts.OnClick(object) end
local function reply(...)
    for _, record in ipairs({...}) do
        local bridge
        for _, f in ipairs(frames) do if f.events.CHAT_MSG_ADDON then bridge = f end end
        bridge.scripts.OnEvent(bridge, "CHAT_MSG_ADDON", "DCJEWELER", record, "WHISPER", "Tester")
    end
end
local function lastSent() return sent[#sent] end
local function lastMessage() return UIErrorsFrame.lines[#UIErrorsFrame.lines] end
local function rowTexts()
    local out = {}
    for _, f in ipairs(frames) do
        if f.parent == ui.list and f.shown and f.row then out[#out + 1] = f.label.text end
    end
    return out
end
local function pickup(bag, slot, id)
    cursor = {id = id}
    if bag == 255 then PickupInventoryItem(slot + 1) else PickupContainerItem(bag, slot) end
end
local function reset()
    sent = {}
    UIErrorsFrame.lines = {}
end
-- Rectangles for a view's frames, as layout would give them: the item frame across the top, the sockets in a row.
local AWAY = {9000, 9000}
local function layout(view)
    view.box._rect = {0, 300, 1000, 96}
    for index, s in ipairs(view.sockets) do s._rect = {index * 100, 100, 64, 64} end
end
local function centre(frame) local l, b, w, h = frame:GetRect(); return {l + w / 2, b + h / 2} end

----------------------------------------------------------------------------------------------------
-- 1. The rules
----------------------------------------------------------------------------------------------------
local balance = {gold = "12000", deathsBreath = "3"}
local names = {}
for _, entry in ipairs(Logic.rows(recipes(), balance, {collapsed = {}})) do
    names[#names + 1] = entry.head and ("# " .. entry.head) or Logic.rowText(entry)
end
local expected = {"# Amethyst", "[3] Flawless Square Amethyst", "[1] Square Amethyst", "[4] Flawless Amethyst",
    "# Diamond", "[3] Flawless Diamond",
    "# Ruby", "[2] Square Ruby", "Flawless Ruby"}
assert(table.concat(names, "|") == table.concat(expected, "|"),
    "colours A to Z, tiers highest first, [n] from the fewest of gems, gold and Death's Breath; got " .. table.concat(names, "|"))

-- Each limit alone: gems (Square Amethyst 3/2 gems), gold (Flawless Amethyst 12000/2500), Death's Breath
-- (Flawless Square Amethyst 3/1), and a free recipe is limited by its gems only.
local byName = {}
for _, r in ipairs(recipes()) do byName[r.name] = r end
assert(Logic.craftable(byName["Square Amethyst"], balance) == 1, "gems limit")
assert(Logic.craftable(byName["Flawless Amethyst"], balance) == 4, "gold limits: 12000 / 2500, not the 10 the gems allow")
assert(Logic.craftable(byName["Flawless Square Amethyst"], balance) == 3, "Death's Breath limits: 3 / 1, not the 10 the gems allow")
assert(Logic.craftable(byName["Flawless Diamond"], balance) == 3, "a free recipe is limited by its gems")
assert(Logic.craftable(byName["Flawless Ruby"], balance) == 0, "one gem of two makes none")
assert(Logic.craftable(byName["Flawless Square Amethyst"], {gold = "12000", deathsBreath = "0"}) == 0, "no Death's Breath, none")
assert(Logic.craftable(byName["Flawless Amethyst"], {gold = "99999999999999999999", deathsBreath = "0"}) == 10,
    "an account-sized gold total (a decimal string past 2^53) never limits and is never read as a float")

assert(Logic.atLeast("9007199254740993", 9007199254740992) and not Logic.atLeast("9007199254740991", 9007199254740992))
assert(Logic.atLeast("0", 0) and not Logic.atLeast("0", 1) and Logic.atLeast("100", 99))

-- Have materials, search, collapsed headers.
local function listOf(view) local out = {}; for _, e in ipairs(Logic.rows(recipes(), balance, view)) do out[#out + 1] = e.head and ("# " .. e.head) or e.recipe.name end; return table.concat(out, "|") end
assert(listOf({haveMats = true, collapsed = {}}) == "# Amethyst|Flawless Square Amethyst|Square Amethyst|Flawless Amethyst|# Diamond|Flawless Diamond|# Ruby|Square Ruby",
    "Have materials drops what cannot be made now")
assert(listOf({search = "DIAMOND", collapsed = {}}) == "# Diamond|Flawless Diamond", "search is case-blind and a colour with no match has no header")
assert(listOf({search = "nothing", collapsed = {}}) == "", "no match, no rows")
assert(listOf({collapsed = {Amethyst = true}}):find("^# Amethyst|# Diamond"), "a collapsed colour keeps its header and hides its tiers")

-- The quantity box.
assert(Logic.clampQty(0, 5) == 1 and Logic.clampQty(-3, 5) == 1 and Logic.clampQty(7, 5) == 5 and Logic.clampQty(3, 5) == 3)
assert(Logic.clampQty("abc", 5) == 1 and Logic.clampQty(2.9, 5) == 2 and Logic.clampQty(4, 0) == 1 and Logic.clampQty(9, nil) == 1)

-- The away rule: an empty socket may be filled anywhere; taking out or replacing needs the Jeweler.
assert(Logic.mayChange(true, true) and Logic.mayChange(true, false) and Logic.mayChange(false, false))
assert(not Logic.mayChange(false, true), "away from the Jeweler a gem cannot be removed or swapped")
assert(Logic.AWAY_MESSAGE == "Remove gems at the Jeweler.")

----------------------------------------------------------------------------------------------------
-- 2. The Jeweler window: Combine Gems
----------------------------------------------------------------------------------------------------
handlers.Tables(nil, {gems = GEMS, effects = EFFECTS})
assert(not ui.frame:IsShown() and not ui.sockFrame:IsShown(), "nothing is open until the Jeweler is talked to")
handlers.Show(nil, showPayload())
assert(ui.frame:IsShown() and ui.title.text == "Covetous Shen", "the window is Covetous Shen's")
handlers.Close()
assert(not ui.frame:IsShown(), "the server's Close (the player walked away) hides the window")
handlers.Show(nil, showPayload())
assert(ui.sub.text == "COMBINE GEMS", "Combine Gems opens first, the subtitle is the tab")
assert(#ui.tabs == 3 and ui.tabs[1].def.label == "Combine Gems" and ui.tabs[2].def.label == "Unsocket Gems", "three icon tabs")
local rows = rowTexts()
assert(table.concat(rows, "|") == "- Amethyst|[3] Flawless Square Amethyst|[1] Square Amethyst|[4] Flawless Amethyst|- Diamond|[3] Flawless Diamond|- Ruby|[2] Square Ruby|Flawless Ruby",
    "the drawn list, got " .. table.concat(rows, "|"))
for _, f in ipairs(frames) do
    assert(f.text ~= "Repair all", "the Jeweler no longer repairs: no Repair all button")
end
assert(J.send("repair") == false and #sent == 0, "the repair verb is gone from the client")
assert(ui.detail.name.text == "Flawless Square Amethyst", "the first recipe is selected when none was")

-- Select, quantity, Create. Square Amethyst: one can be made.
local function rowButton(label)
    for _, f in ipairs(frames) do if f.parent == ui.list and f.row and f.label.text == label then return f end end
    error("no row " .. label)
end
click(rowButton("[3] Flawless Square Amethyst"))
assert(ui.detail.name.text == "Flawless Square Amethyst" and ui.qtyBox.text == "1")
assert(ui.detail.effects[1].text == nil or ui.detail.effects[1].text == "", "no effect text for a gem the server sent none for")
click(rowButton("[4] Flawless Amethyst"))
assert(ui.detail.effects[1].text == "Weapon: +10 Life per Hit" and ui.detail.effects[2].text == "Helm: +8% Life"
    and ui.detail.effects[3].text == "Other: +18 Vitality", "the effect on weapon, helm and other, in the tooltip's words")
assert(ui.detail.reagents[1].label.text == "Amethyst" and ui.detail.reagents[1].count.text == "20 / 2", "material have/need")
assert(not ui.detail.reagents[2].shown, "no Death's Breath row for a recipe that needs none")
assert(ui.detail.cost.text == "Cost: 2,500 gold")

-- The quantity is typed, stepped, and clamped to 1..what can be made (4).
ui.qtyBox.focused = true
ui.qtyBox:SetText("99"); ui.qtyBox.scripts.OnTextChanged(ui.qtyBox, true)
assert(ui.qtyBox.text == "4", "typing more than can be made shows what will be made, got " .. tostring(ui.qtyBox.text))
ui.qtyBox:SetText("0"); ui.qtyBox.scripts.OnTextChanged(ui.qtyBox, true)
assert(ui.qtyBox.text == "1", "typing 0 gives 1")
ui.qtyBox.focused = false
click(ui.qtyUp); click(ui.qtyUp)
assert(ui.qtyBox.text == "3" and ui.detail.cost.text == "Cost: 7,500 gold" and ui.detail.reagents[1].count.text == "20 / 6", "the arrows step and the details follow")
click(ui.qtyUp); click(ui.qtyUp); click(ui.qtyUp)
assert(ui.qtyBox.text == "4", "the right arrow stops at what can be made")
click(ui.qtyDown); click(ui.qtyDown); click(ui.qtyDown); click(ui.qtyDown); click(ui.qtyDown)
assert(ui.qtyBox.text == "1", "the left arrow stops at 1")

-- Create: one click starts the 2 s bar; when it is full, one request goes with the count; a second click before
-- the reply is not a second request.
local function runBar(seconds) local update = ui.bar.scripts.OnUpdate; if update then update(ui.bar, seconds) end end
reset()
click(ui.qtyUp); click(ui.qtyUp)
click(ui.createOne)
assert(#sent == 0 and J.Combining() and ui.bar:IsShown(), "a passing click starts the bar and sends nothing yet")
runBar(1.99)
assert(#sent == 0 and ui.bar:IsShown(), "nothing is sent before the bar is full")
runBar(0.02)
assert(#sent == 1 and lastSent().prefix == "DCJEWELER" and lastSent().body == "combine\t6002\t3"
    and lastSent().distribution == "WHISPER" and lastSent().target == "Tester", "Create sends combine id count, got " .. tostring(lastSent() and lastSent().body))
assert(not ui.bar:IsShown() and not J.Combining(), "the bar is gone once it has sent")
click(ui.createOne); click(ui.createAll)
assert(#sent == 1 and not J.Combining(), "a click while the last request is unanswered sends nothing and starts no bar")
reply("R|combine|1", "B|4500", "I|92:6001:14:0:4", "I|99:6002:6:0:8", "E|combine")
local function recipeHave(id) for _, r in ipairs(J.model().recipes) do if r.id == id then return r.have end end end
assert(J.model().balance.gold == "4500" and recipeHave(6002) == 14, "the reply's stack record moves the count the Combine view prints")
click(ui.createOne); runBar(2)
assert(#sent == 2, "once the reply is in, the next click goes")
reply("E|combine")
-- Create All makes what the materials allow, in ONE request: gold 12000 pays for 4, the gems for 7.
reply("B|12000", "E|combine")
reset()
click(ui.createAll); runBar(2)
assert(#sent == 1 and lastSent().body == "combine\t6002\t4", "Create All is one request for all it can make, got " .. tostring(lastSent() and lastSent().body))
reply("E|combine")
-- Nothing can be made: Create and Create All are greyed out and send nothing (ruling 2026-10-02).
click(rowButton("Flawless Ruby"))
reset()
assert(ui.createOne.disabled and ui.createAll.disabled, "materials short: Create and Create All are greyed")
assert(ui.detail.reagents[1].count.text == "1 / 2" and ui.detail.reagents[1].count.textColor[2] < .5, "a short material is red")
assert(#sent == 0, "a greyed Create All sends nothing")
assert(J.Create(1) == false and not J.Combining() and #sent == 0, "the maker refuses even when a caller asks directly")
-- Gold short is the same rule, with the cost line red.
reply("B|0", "E|combine")
click(rowButton("Flawless Amethyst"))
assert(ui.createOne.disabled and ui.createAll.disabled, "gold short: Create and Create All are greyed")
assert(ui.detail.cost.textColor[2] < .5 and ui.detail.cost.textColor[3] < .5, "the cost line is red when the gold is short")
reply("B|12000", "E|combine")
assert(not ui.createOne.disabled and not ui.createAll.disabled, "affordable again: the buttons are back")

-- The combine bar. Recipe 6002 (Flawless Amethyst, 4 makeable): Create with 2, then Create All with 4.
click(rowButton("[4] Flawless Amethyst"))
click(ui.qtyUp)
reset()
click(ui.createOne)
assert(ui.bar:IsShown() and ui.bar.text.text == "Combining 2 Flawless Amethyst", "the bar says what is being made, got " .. tostring(ui.bar.text.text))
assert(ui.createOne.disabled and ui.createAll.disabled and ui.qtyUp.disabled and ui.qtyDown.disabled and ui.qtyBox.mouseEnabled == false,
    "Create, Create All, the arrows and the quantity box are locked while it runs")
-- Locked: a second click, the arrows, typing and another recipe do nothing.
click(ui.createOne); click(ui.createAll)
click(ui.qtyUp)
assert(ui.detail.cost.text == "Cost: 5,000 gold", "the right arrow does nothing while it runs")
click(ui.qtyDown)
assert(ui.detail.cost.text == "Cost: 5,000 gold", "the left arrow does nothing while it runs")
ui.qtyBox:SetText("4"); ui.qtyBox.scripts.OnTextChanged(ui.qtyBox, true)
click(rowButton("Flawless Ruby"))
assert(ui.detail.cost.text == "Cost: 5,000 gold", "the quantity did not move while it runs, got " .. tostring(ui.detail.cost.text))
assert(ui.detail.name.text == "Flawless Amethyst" and #sent == 0 and J.Combining().count == 2, "a second click, the arrows, typing and a recipe choice are ignored while it runs")
runBar(1)
assert(ui.bar.fill:GetWidth() > 1 and #sent == 0, "the fill grows while nothing is sent")
runBar(1)
assert(#sent == 1 and lastSent().body == "combine\t6002\t2" and not ui.createOne.disabled and not ui.createAll.disabled
    and not ui.qtyUp.disabled and ui.qtyBox.mouseEnabled == true and not ui.bar:IsShown(), "full: today's request once for the quantity, controls back")
click(ui.createAll)
assert(#sent == 1 and not J.Combining(), "a click while the request is unanswered is not a second request")
reply("E|combine")
-- One 2 s bar for Create All whatever the quantity.
reset()
click(ui.createAll)
assert(ui.bar:IsShown() and J.Combining().count == 4 and #sent == 0, "Create All is one bar for all it can make")
runBar(2)
assert(#sent == 1 and lastSent().body == "combine\t6002\t4", "...and one request")
reply("E|combine")
-- Each cancel path sends nothing and says so in red.
local function cancelPath(name, cancel)
    reset()
    click(ui.createOne)
    assert(J.Combining(), name .. ": the bar runs")
    cancel()
    assert(not J.Combining() and not ui.bar:IsShown() and #sent == 0, name .. ": the bar is gone and nothing is sent")
    assert(lastMessage() == "Combining cancelled. Nothing was used.", name .. ": the red line, got " .. tostring(lastMessage()))
    assert(not ui.createOne.disabled and ui.qtyBox.mouseEnabled == true, name .. ": the controls are back")
    runBar(5)
    assert(#sent == 0, name .. ": a bar that was cancelled never sends later")
end
cancelPath("closing the window", function() ui.frame:Hide(); ui.frame.scripts.OnHide(ui.frame) end)
ui.frame:Show()
cancelPath("Esc (the special-frame close)", function() ui.frame:Hide(); ui.frame.scripts.OnHide(ui.frame) end)
ui.frame:Show()
cancelPath("leaving the Jeweler (the gossip ending)", function() ui.frame.scripts.OnEvent(ui.frame, "GOSSIP_CLOSED") end)
-- UI fixes row 2 (ruling 2026-10-03): entering combat cancels the bar too, like the Blacksmith's
-- (12-ui §3); it used to put the button ids back and return, leaving the bar running into the fight.
cancelPath("entering combat", function() ui.frame.scripts.OnEvent(ui.frame, "PLAYER_REGEN_DISABLED") end)
cancelPath("switching to the Unsocket Gems tab", function() click(ui.tabs[2]) end)
assert(ui.sub.text == "UNSOCKET GEMS", "the tab did switch")
click(ui.tabs[1])
assert(ui.sub.text == "COMBINE GEMS" and not ui.createOne.disabled and not ui.createAll.disabled and not ui.qtyUp.disabled
    and ui.qtyBox.mouseEnabled == true and not ui.bar:IsShown(), "coming back to Combine, the controls are unlocked and no bar shows")
-- Shift+Right-click at the Jeweler (it opens the Unsocket Gems tab) cancels a running bar the same way.
reset()
click(ui.createOne)
SocketContainerItem(0, 3)
handlers.Gear(nil, {items = {item87()}, gems = gems()})
assert(not J.Combining() and #sent == 0 and lastMessage() == "Combining cancelled. Nothing was used.", "loading an item into the Unsocket Gems tab cancels the bar")
click(ui.socketView.clear)
click(ui.tabs[1])
-- With no bar running none of those says anything.
reset(); UIErrorsFrame.lines = {}
ui.frame.scripts.OnEvent(ui.frame, "GOSSIP_CLOSED"); ui.frame.scripts.OnHide(ui.frame)
assert(#UIErrorsFrame.lines == 0, "a gossip end or a close with nothing combining says nothing")
assert(UISpecialFrames[1] == "DiablocraftJewelerFrame", "Esc closes the window through the special-frame list, and closing cancels the bar")

-- Have materials and search.
ui.check:SetChecked(true); ui.check.scripts.OnClick(ui.check)
assert(not table.concat(rowTexts(), "|"):find("Flawless Ruby", 1, true), "Have materials hides what cannot be made")
ui.check:SetChecked(false); ui.check.scripts.OnClick(ui.check)
ui.searchBox:SetText("diamond"); ui.searchBox.scripts.OnTextChanged(ui.searchBox)
assert(table.concat(rowTexts(), "|") == "- Diamond|[3] Flawless Diamond", "search narrows the list")
ui.searchBox:SetText(""); ui.searchBox.scripts.OnTextChanged(ui.searchBox)
-- A colour header folds its tiers.
for _, f in ipairs(frames) do
    if f.parent == ui.list and f.row and f.row.head == "Amethyst" then click(f); break end
end
assert(not table.concat(rowTexts(), "|"):find("Flawless Square Amethyst", 1, true) and table.concat(rowTexts(), "|"):find("+ Amethyst", 1, true))

----------------------------------------------------------------------------------------------------
-- 3. The Jeweler window: Unsocket Gems
----------------------------------------------------------------------------------------------------
click(ui.tabs[2])
assert(ui.sub.text == "UNSOCKET GEMS" and ui.socketView.root:IsShown())
local view = ui.socketView
assert(view.item == nil and view.hint:IsShown() and view.hint.text == "Right-click an item to see its sockets",
    "the empty item frame says how to load an item")
assert(ui.sockView.hint.text == "Shift+Right-click an item to see its sockets", "the small Sockets window keeps the Shift+Right-click wording")
-- Dragging an item onto the frame does nothing: the cursor keeps the item, the server is not asked, nothing is shown.
pickup(0, 3, 7001)
aio = {}
for _, target in ipairs({view.box, view.slot}) do
    for _, event in ipairs({"OnReceiveDrag", "OnClick"}) do
        if target.scripts[event] then target.scripts[event](target) end
    end
end
assert(view.item == nil and #aio == 0 and cursor ~= nil, "an item dropped on the item frame is not taken, not asked about, not cleared")
cursor = nil
-- Shift+Right-click is the way in, at the Jeweler too: a bag item, then a character-sheet item.
SocketContainerItem(0, 3)
handlers.Gear(nil, {items = {item87()}, gems = gems()})
assert(ui.frame:IsShown() and view.item and view.item.guid == 87, "at the Jeweler Shift+Right-click loads the item into the Unsocket Gems tab")
assert(view.name.text == "Visage" and view.sockets[1].name.text == "Square Amethyst" and view.sockets[2].name.text == "Empty socket")
assert(view.sockets[1].stat.text == "+11% Life", "a helm shows the gem's helm effect, got " .. tostring(view.sockets[1].stat.text))
SocketInventoryItem(16)
handlers.Gear(nil, {items = {item88()}, gems = gems()})
assert(view.item.guid == 88 and view.sockets[1].name.text == "Empty socket" and not view.sockets[2].column:IsShown(),
    "a character-sheet weapon, with its one socket")
SocketContainerItem(0, 3)
handlers.Gear(nil, {items = {item87()}, gems = gems()})
assert(view.item.guid == 87)

-- A gem from the bags onto the EMPTY socket (index 2): socket guid seq gemGuid.
reset()
pickup(0, 1, 6002)
view.sockets[2].scripts.OnReceiveDrag(view.sockets[2])
assert(lastSent().body == "socket\t87\t1\t90" and cursor == nil, "an empty socket takes the gem: socket item seq gem, got " .. tostring(lastSent() and lastSent().body))
reply("E|socket")
-- The cursor's gem is found by where it was picked up, not by its item id alone: the second stack of the
-- same gem is the one that goes in.
reset()
pickup(0, 8, 6002)
view.sockets[2].scripts.OnReceiveDrag(view.sockets[2])
assert(lastSent().body == "socket\t87\t1\t96", "the stack in bag 0 slot 8 is gem 96, got " .. tostring(lastSent() and lastSent().body))
reply("E|socket")
-- ... onto a FILLED socket at the Jeweler: the same request, the server swaps.
reset()
pickup(0, 2, 6003)
view.sockets[1].scripts.OnClick(view.sockets[1])
assert(lastSent().body == "socket\t87\t0\t91", "at the Jeweler a gem dropped on a filled socket is sent (the server swaps), got " .. tostring(lastSent() and lastSent().body))
reply("E|socket")
-- Pull a socketed gem off its socket and let go anywhere that is not a socket: it comes out, free.
reset()
layout(view); mouseXY = AWAY
view.sockets[1].scripts.OnDragStart(view.sockets[1])
assert(DiablocraftJewelerGhost:IsShown(), "the gem follows the cursor while it is pulled")
view.sockets[1].scripts.OnDragStop(view.sockets[1])
assert(not DiablocraftJewelerGhost:IsShown() and lastSent().body == "remove\t87\t0", "let go over the world: remove item seq, got " .. tostring(lastSent() and lastSent().body))
reply("E|remove")
-- Let go on a socket: nothing moves.
reset()
mouseXY = centre(view.sockets[2])
view.sockets[1].scripts.OnDragStart(view.sockets[1])
view.sockets[1].scripts.OnDragStop(view.sockets[1])
assert(#sent == 0, "released on a socket sends nothing")
-- An empty socket cannot be pulled.
mouseXY = AWAY
view.sockets[2].scripts.OnDragStart(view.sockets[2])
assert(not DiablocraftJewelerGhost:IsShown(), "nothing to pick up from an empty socket")
view.sockets[2].scripts.OnDragStop(view.sockets[2])
assert(#sent == 0)

-- What the real 3.3.5 client does, which the tests above did not: the mouse focus is not what says where a pull
-- ended (it may be the frame the press began on, or nil), so the release is judged by where the cursor is.
reset()
layout(view); mouseXY = AWAY; mouseFocus = view.sockets[1]
view.sockets[1].scripts.OnDragStart(view.sockets[1])
view.sockets[1].scripts.OnDragStop(view.sockets[1])
assert(lastSent() and lastSent().body == "remove\t87\t0", "a stale mouse focus on the source socket does not stop the removal")
reply("E|remove")
mouseFocus = nil
-- A client that never delivers OnDragStop: the button comes up and the tracker ends the pull.
reset()
layout(view); mouseXY = AWAY; mouseDown = true
view.sockets[1].scripts.OnDragStart(view.sockets[1])
local tracker
for _, f in ipairs(frames) do if f.scripts.OnUpdate and not f.events.BAG_UPDATE and f ~= DiablocraftJewelerGhost then tracker = f end end
tracker.scripts.OnUpdate(tracker, 0.02)
assert(#sent == 0 and DiablocraftJewelerGhost:IsShown(), "still pulling while the button is down")
mouseDown = false
tracker.scripts.OnUpdate(tracker, 0.02)
assert(lastSent() and lastSent().body == "remove\t87\t0" and not DiablocraftJewelerGhost:IsShown(),
    "with no OnDragStop, the button coming up ends the pull: removal sent")
reply("E|remove")
-- A client that never delivers OnDragStart: a press on a filled socket and a move of the cursor start the pull.
reset()
layout(view); mouseXY = centre(view.sockets[1]); mouseDown = true
view.sockets[1].scripts.OnMouseDown(view.sockets[1], "LeftButton")
tracker.scripts.OnUpdate(tracker, 0.02)
assert(not DiablocraftJewelerGhost:IsShown(), "a press alone is not a pull")
mouseXY = AWAY
tracker.scripts.OnUpdate(tracker, 0.02)
assert(DiablocraftJewelerGhost:IsShown(), "with no OnDragStart, moving the cursor off a pressed socket starts the pull")
mouseDown = false
tracker.scripts.OnUpdate(tracker, 0.02)
assert(lastSent() and lastSent().body == "remove\t87\t0", "...and the button coming up removes the gem")
reply("E|remove")
-- A button that reads as up before it was ever seen down ends nothing.
reset()
mouseDown = false
view.sockets[1].scripts.OnDragStart(view.sockets[1])
tracker.scripts.OnUpdate(tracker, 0.02)
assert(#sent == 0 and DiablocraftJewelerGhost:IsShown(), "a wrong 'button up' on the first frame does not remove a gem")
view.sockets[1].scripts.OnDragStop(view.sockets[1])
reply("E|remove")
reset()
-- Away from the Jeweler the refusal is in the chat as well as on the red line.
DEFAULT_CHAT_FRAME = {lines = {}}
function DEFAULT_CHAT_FRAME:AddMessage(message) self.lines[#self.lines + 1] = message end
ui.frame:Hide()
mouseXY = AWAY
view.sockets[1].scripts.OnDragStart(view.sockets[1])
view.sockets[1].scripts.OnDragStop(view.sockets[1])
assert(#sent == 0 and DEFAULT_CHAT_FRAME.lines[#DEFAULT_CHAT_FRAME.lines] == "Remove gems at the Jeweler.", "a refusal reaches the chat frame too")
ui.frame:Show()
reset()

-- Where the bar is drawn. Rectangles from the recorded SetPoint (TOPLEFT x, y in the Combine tab's own coordinates)
-- and SetSize/SetWidth; a font string has no height in the stub, so it counts as one 14 px line. The bar covers nothing.
local function rectOf(frame, minHeight)
    local point = frame.points[1]
    assert(point and point[1] == "TOPLEFT" and type(point[2]) == "number", "a TOPLEFT point in the tab's coordinates")
    local width, height = frame:GetWidth(), math.max(frame:GetHeight() or 0, minHeight or 0)
    return {left = point[2], right = point[2] + width, top = point[3], bottom = point[3] - height}
end
local function overlap(a, b) return a.left < b.right and b.left < a.right and a.bottom < b.top and b.bottom < a.top end
local barRect = rectOf(ui.bar)
for name, neighbour in pairs({search = ui.searchBox, list = ui.scroll, funds = ui.funds, createAll = ui.createAll, createOne = ui.createOne,
        qtyBox = ui.qtyBox, qtyUp = ui.qtyUp, qtyDown = ui.qtyDown, detail = ui.detail, check = ui.check}) do
    local other = rectOf(neighbour, 14)
    assert(not overlap(barRect, other), "the combine bar overlaps the " .. name .. ": bar " .. barRect.left .. ".." .. barRect.right
        .. " x " .. barRect.top .. ".." .. barRect.bottom .. ", " .. name .. " " .. other.left .. ".." .. other.right .. " x " .. other.top .. ".." .. other.bottom)
end
assert(barRect.bottom >= -480, "and it stays inside the tab")
assert(ui.bar.bg and ui.bar.bg.vertexColor and ui.bar.bg.vertexColor[4] == 1 and ui.bar.bg.allPoints, "an opaque background texture fills the bar")
assert(ui.bar:GetFrameLevel() > ui.searchBox:GetFrameLevel() and ui.bar:GetFrameLevel() > ui.scroll:GetFrameLevel(), "the bar is above its neighbours")

ui.frame._rect = {0, 0, 1000, 700}
ui.sockFrame._rect = {2000, 0, 600, 400}
ui.frame:Show()
reset()
-- Clear leaves the item.
click(view.clear)
assert(view.item == nil and view.hint:IsShown())

---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
-- 3b. Unsocket Gems: right-click loads an item; Remove Gems
----------------------------------------------------------------------------------------------------
assert(ui.frame:IsShown() and ui.sub.text == "UNSOCKET GEMS")
-- No stock global is written: the bag and sheet buttons look these up by name on every click, so a replacement would
-- run every later click, in combat too, as tainted code.
assert(ContainerFrameItemButton_OnClick == stockOnClick.container and PaperDollItemSlotButton_OnClick == stockOnClick.paperdoll,
    "ContainerFrameItemButton_OnClick and PaperDollItemSlotButton_OnClick are still the originals after load and after opening the tab")
-- A bag or sheet button as the client runs a click: PreClick hooks, then the stock OnClick (which uses the button's own id
-- as the slot, `used`), then PostClick hooks.
local function mockButton(bag, slot)
    local b = {id = slot, hooks = {}, parent = {GetID = function() return bag end}}
    function b:GetParent() return self.parent end
    function b:GetID() return self.id end
    function b:SetID(value) self.id = value end
    function b:HookScript(event, fn) self.hooks[event] = self.hooks[event] or {}; table.insert(self.hooks[event], fn) end
    return b
end
local used
local function clickButton(b, mouseButton)
    for _, fn in ipairs(b.hooks.PreClick or {}) do fn(b, mouseButton) end
    local parent = b:GetParent()
    used = {parent and parent:GetID() or 255, b:GetID()}   -- the stock OnClick: UseContainerItem(bag, slot) / UseInventoryItem(slot)
    for _, fn in ipairs(b.hooks.PostClick or {}) do fn(b, mouseButton) end
end
linkAt["0:3"] = 7001; linkAt["0:1"] = 6002; linkAt["worn:16"] = 7002
local bagItem, gemButton = mockButton(0, 3), mockButton(0, 1)
ContainerFrame1Item3, ContainerFrame1Item1 = bagItem, gemButton
local mainHand = mockButton(255, 16)
CharacterMainHandSlot = mainHand
mainHand.parent = nil
J.ScanClickButtons()
assert(bagItem.hooks.PreClick and bagItem.hooks.PostClick and mainHand.hooks.PreClick, "the bag and sheet buttons are hooked with HookScript, not replaced")
J.ScanClickButtons()
assert(#bagItem.hooks.PreClick == 1, "a second scan does not hook a button twice")
reset(); aio = {}
clickButton(bagItem, "RightButton")
local gearAsk = lastAio("Gear")
assert(gearAsk and gearAsk.args[1] == 0 and gearAsk.args[2] == 3 and gearAsk.args[3] == 0,
    "a right-click on a bag item (ElvUI or stock) asks for that item")
assert(used[2] ~= 3 and used[2] == 2, "the stock click found an empty slot, so the item is not used, got slot " .. tostring(used[2]))
assert(bagItem:GetID() == 3, "and the button's own slot is back after the click")
handlers.Gear(nil, {items = {item87()}, gems = gems()})
assert(view.item and view.item.guid == 87, "the right-clicked item is loaded")
click(view.clear)
-- An item with no sockets: a short message, and nothing else happens.
clickButton(bagItem, "RightButton")
handlers.Gear(nil, {items = {}, gems = gems()})
assert(lastMessage() == "That item has no sockets." and view.item == nil, "no sockets: the message, nothing loaded")
-- The character sheet: slot 16 is the model's 15; a worn item is read by its slot.
aio = {}
clickButton(mainHand, "RightButton")
gearAsk = lastAio("Gear")
assert(gearAsk.args[1] == 255 and gearAsk.args[2] == 15 and used[2] ~= 16 and mainHand:GetID() == 16,
    "a worn item on the stock/ElvUI sheet is read by its slot, not used, and its id is back")
handlers.Gear(nil, {items = {item88()}, gems = gems()})
assert(view.item.guid == 88)
click(view.clear)
-- The Torment sheet's worn slot is one more hooked button (a CLICK_SOURCES row), read by its WoW slot like the stock
-- sheet's. Its own OnClick reads self.equipSlot, not the id, so nothing is id-swapped: the sheet asks the Jeweler's
-- claim instead and does nothing while the tab is open.
local tormentSlot = mockButton(255, 1)
tormentSlot.equipSlot = 15
linkAt["worn:16"] = 7002
DiablocraftGearSlot15 = tormentSlot
J.ScanClickButtons()
assert(tormentSlot.hooks.PreClick and tormentSlot.hooks.PostClick, "the Torment sheet's worn slot is hooked with HookScript")
aio = {}
clickButton(tormentSlot, "RightButton")
gearAsk = lastAio("Gear")
assert(gearAsk and gearAsk.args[1] == 255 and gearAsk.args[2] == 15 and gearAsk.args[3] == 0,
    "the Torment sheet's worn slot is read by its WoW slot")
assert(tormentSlot:GetID() == 1 and used[2] == 1, "and its id is never touched")
handlers.Gear(nil, {items = {item88()}, gems = gems()})
click(view.clear)
assert(#claims == 1 and claims[1]() == true, "the Jeweler registers one claim, and it is true while the tab is open")
inCombat = true
assert(claims[1]() == false, "false in combat")
inCombat = false
-- Everything else is untouched: a gem, a left-click, combat, another tab, no window. The id is never changed.
local function untouched(name, button, mouseButton)
    aio = {}
    local before = button:GetID()
    clickButton(button, mouseButton)
    assert(#aio == 0 and used[2] == before and button:GetID() == before, name)
end
untouched("a gem keeps its right-click", gemButton, "RightButton")
untouched("a left-click is the stock one", bagItem, "LeftButton")
inCombat = true
untouched("in combat nothing is touched", bagItem, "RightButton")
untouched("in combat nothing is touched, sheet", mainHand, "RightButton")
untouched("in combat nothing is touched, Torment sheet", tormentSlot, "RightButton")
inCombat = false
click(ui.tabs[1])
untouched("on the Combine tab a right-click is the stock one", bagItem, "RightButton")
click(ui.tabs[2])
ui.frame:Hide()
untouched("with the window closed a right-click is the stock one", bagItem, "RightButton")
ui.frame:Show()
-- Not while the cursor holds anything: the stock click on the stand-in slot would drop it there.
cursor = {id = 7001}
untouched("a held item: no load, no id swap", bagItem, "RightButton")
cursor = nil
-- Shift+Right-click (and Ctrl, Alt) is the stock modified click: no id swap, and OpenSockets gets the REAL slot.
for _, key in ipairs({"shift", "ctrl", "alt"}) do
    keys[key] = true
    untouched(key .. "+right-click: no id swap", bagItem, "RightButton")
    keys[key] = false
end
keys.shift = true
aio = {}
clickButton(bagItem, "RightButton")
SocketContainerItem(bagItem:GetParent():GetID(), bagItem:GetID())   -- what the stock modified click then calls
gearAsk = lastAio("Gear")
assert(gearAsk and gearAsk.args[1] == 0 and gearAsk.args[2] == 3, "Shift+Right-click with the tab open opens the real item, got slot " .. tostring(gearAsk and gearAsk.args[2]))
keys.shift = false
handlers.Gear(nil, {items = {item87()}, gems = gems()})
click(view.clear)
-- A full bag: nothing loaded, the id untouched, and the reason said; the click is the stock one.
linkAt["0:2"], linkAt["0:4"] = 7003, 7004
aio = {}
reset()
local fullBefore = bagItem:GetID()
clickButton(bagItem, "RightButton")
assert(#aio == 0 and used[2] == fullBefore and bagItem:GetID() == fullBefore and lastMessage() == "Make room in that bag first.",
    "a full bag: no load, no id swap, the message")
linkAt["0:2"], linkAt["0:4"] = nil, nil
-- The sheet with every other slot filled: slot 0 (the ammo slot) is never used as a stand-in.
for slotId = 1, 19 do if slotId ~= 16 then linkAt["worn:" .. slotId] = 9000 + slotId end end
aio = {}
clickButton(mainHand, "RightButton")
assert(#aio == 0 and used[2] == 16 and mainHand:GetID() == 16 and lastMessage() == "Free an equipment slot first.", "no empty equipment slot: no load, no slot 0")
for slotId = 1, 19 do if slotId ~= 16 then linkAt["worn:" .. slotId] = nil end end
-- Combat starting while an id is blanked puts it back.
for _, f in ipairs(frames) do if f == ui.frame then f.scripts.OnEvent(f, "PLAYER_REGEN_DISABLED") end end
-- The click is blanked between Pre and Post only; closing the window or entering combat mid-click restores it.
for _, fn in ipairs(bagItem.hooks.PreClick) do fn(bagItem, "RightButton") end
assert(bagItem:GetID() ~= 3, "mid-click the id is blanked")
ui.frame.scripts.OnEvent(ui.frame, "PLAYER_REGEN_DISABLED")
assert(bagItem:GetID() == 3, "combat starting puts the id back")
for _, fn in ipairs(bagItem.hooks.PreClick) do fn(bagItem, "RightButton") end
ui.frame:Hide(); ui.frame.scripts.OnHide(ui.frame)
assert(bagItem:GetID() == 3, "closing the window puts the id back")
ui.frame:Show()
assert(ContainerFrameItemButton_OnClick == stockOnClick.container and PaperDollItemSlotButton_OnClick == stockOnClick.paperdoll,
    "still the originals after all of it")
-- Remove Gems: below the sockets, the Jeweler's window only; disabled with no gem.
assert(view.removeAll and view.removeAll.text == "Remove Gems" and ui.sockView.removeAll == nil, "only the Jeweler's window has Remove Gems")
assert(not view.removeAll:IsShown(), "no item, no button")
local function twoGems()
    return {guid = 87, entry = 7001, name = "Visage", bag = 0, slot = 3, slotClass = "head",
        sockets = {{seq = 0, gemEntry = 6003, rank = 3, name = "Square Amethyst"}, {seq = 1, gemEntry = 6002, rank = 2, name = "Flawless Amethyst"},
            {seq = 2, gemEntry = 0, rank = 0, name = "Empty socket"}}}
end
local function load(item)
    SocketContainerItem(0, 3)
    handlers.Gear(nil, {items = {item}, gems = gems()})
end
load({guid = 88, entry = 7002, name = "Skorn", bag = 255, slot = 15, slotClass = "weapon", sockets = {{seq = 0, gemEntry = 0, rank = 0, name = "Empty socket"}}})
assert(view.removeAll:IsShown() and view.removeAll.disabled, "an item with no gem: the button is there and disabled")
click(view.clear)
load(twoGems())
assert(view.removeAll:IsShown() and not view.removeAll.disabled, "an item with a gem: enabled")
-- One removal request per gem, the next after each reply, the drag-off's own request.
reset(); aio = {}
click(view.removeAll)
assert(#sent == 1 and lastSent().body == "remove\t87\t0", "the first gem's removal goes, got " .. tostring(lastSent() and lastSent().body))
assert(view.removeAll.disabled, "disabled while it runs")
click(view.removeAll)
assert(#sent == 1, "a second click while it runs sends nothing")
reply("E|remove")
assert(#sent == 2 and lastSent().body == "remove\t87\t1", "after the reply the next gem, got " .. tostring(lastSent() and lastSent().body))
reply("E|remove")
assert(#sent == 2, "an empty socket is not removed and the run ends")
-- Bags full: refused up front, nothing sent; and a server refusal ends the run.
freeSlots = 1
reset()
click(view.removeAll)
assert(#sent == 0 and lastMessage() == "Not enough bag space: 2 free slots are needed.", "not enough free slots: refused before anything is sent")
freeSlots = 10
click(view.removeAll)
assert(#sent == 1)
reply("X|Your bags are full.")
assert(#sent == 1 and lastMessage() == "Your bags are full.", "the server's refusal ends the run")
reply("E|remove")
assert(#sent == 1, "nothing continues after a refusal")
click(view.clear)

-----
-- 4. The Sockets window: Shift+Right-click, anywhere
----------------------------------------------------------------------------------------------------
ui.frame:Hide()
reset(); aio = {}
ItemSocketingFrame:Show()
local before = stock.socketContainer
SocketContainerItem(0, 3)         -- the stock Shift+Right-click on a bag item
assert(stock.socketContainer == before + 1, "the stock call still runs: it is hooked, not replaced")
assert(ItemSocketingFrame:IsShown() == false and hidden[#hidden] == ItemSocketingFrame, "the stock socket frame is put away")
local ask = lastAio("Gear")
assert(ask and ask.args[1] == 0 and ask.args[2] == 3 and ask.args[3] == 0, "the click asks the server for that item: bag 0 slot 3")
assert(not ui.sockFrame:IsShown(), "it opens when the answer is in")
handlers.Gear(nil, {items = {item87()}, gems = gems()})
assert(ui.sockFrame:IsShown() and not ui.frame:IsShown(), "away from the Jeweler the small Sockets window opens")
local small = ui.sockView
assert(small.item.guid == 87 and small.sockets[1].name.text == "Square Amethyst")
-- Filling an empty socket works away.
reset()
pickup(0, 1, 6002)
small.sockets[2].scripts.OnReceiveDrag(small.sockets[2])
assert(lastSent().body == "socket\t87\t1\t90", "away from the Jeweler an empty socket takes a gem")
reply("E|socket")
-- Swapping does not: the gem snaps back with the Jeweler's words and nothing is sent.
reset()
pickup(0, 2, 6003)
small.sockets[1].scripts.OnReceiveDrag(small.sockets[1])
assert(#sent == 0 and lastMessage() == "Remove gems at the Jeweler." and cursor == nil, "away, a gem on a filled socket is refused")
-- Removing does not either.
reset()
layout(small); mouseXY = AWAY
small.sockets[1].scripts.OnDragStart(small.sockets[1])
small.sockets[1].scripts.OnDragStop(small.sockets[1])
assert(#sent == 0 and lastMessage() == "Remove gems at the Jeweler." and not DiablocraftJewelerGhost:IsShown(), "away, pulling a gem out is refused")
-- The character sheet's click goes by the sheet's slot numbering.
aio = {}
SocketInventoryItem(16)
ask = lastAio("Gear")
assert(ask and ask.args[1] == 255 and ask.args[2] == 15, "the sheet's slot 16 is the model's 15")
handlers.Gear(nil, {items = {item88()}, gems = gems()})
assert(small.item.guid == 88)
-- A refresh asks by guid, and an item that left the character closes the view's item.
aio = {}
local watcher
for _, f in ipairs(frames) do if f.events.BAG_UPDATE then watcher = f end end
watcher.scripts.OnEvent(watcher, "BAG_UPDATE"); watcher.scripts.OnUpdate(watcher, 0.5)
ask = lastAio("Gear")
assert(ask and ask.args[3] == 88 and countAio("Refresh") == 0, "the Sockets window refreshes by guid, never through the Jeweler's Refresh")
handlers.Gear(nil, {items = {}, gems = gems()})
assert(small.item == nil, "an item the server no longer finds is dropped from the view")
-- At the Jeweler the same click opens the Unsocket Gems tab, not a second window.
handlers.Show(nil, showPayload())
assert(ui.frame:IsShown() and ui.sub.text == "COMBINE GEMS")
ui.sockFrame:Hide()
SocketContainerItem(0, 3)
handlers.Gear(nil, {items = {item87()}, gems = gems()})
assert(ui.frame:IsShown() and not ui.sockFrame:IsShown() and ui.sub.text == "UNSOCKET GEMS" and ui.socketView.item.guid == 87,
    "at the Jeweler Shift+Right-click opens the Unsocket Gems tab with that item")
-- ... and there removing is allowed.
reset()
layout(ui.socketView); mouseXY = AWAY
ui.socketView.sockets[1].scripts.OnDragStart(ui.socketView.sockets[1])
ui.socketView.sockets[1].scripts.OnDragStop(ui.socketView.sockets[1])
assert(lastSent().body == "remove\t87\t0")
reply("E|remove")

----------------------------------------------------------------------------------------------------
-- 5. The bridge reply, the model and the refresh watcher
----------------------------------------------------------------------------------------------------
handlers.Show(nil, showPayload())
local model = J.model()
model.items[1].sockets = {}
reply("R|socket|0", "B|640000", "M|102000:98", "I|90:6002:3:0:1",
    "A|87|7001|255|0|rare|0|0", "F|87|0:sockets:1:socket:0:-1:0|5:chc:2:gem:0:0:6002", "E|socket")
model = J.model()
local socketed
for _, it in ipairs(model.items) do if it.guid == 87 then socketed = it end end
assert(model.balance.gold == "640000" and model.balance.deathsBreath == "98", "the reply's gold and Death's Breath are the window's")
assert(socketed.bag == 255 and socketed.slot == 0, "the reply's raw bag and slot are read as the model's container convention")
assert(#socketed.sockets == 1 and socketed.sockets[1].seq == 0 and socketed.sockets[1].gemEntry == 6002
    and socketed.sockets[1].name == "Flawless Amethyst", "an A and its F rows rebuild the socket rows, named from the pushed tables")
-- A long affix list is split into several F records of the same letter (window-bridge.md).
-- The sockets are their union: a later record that carries only the gem row must not wipe
-- the sockets the earlier records built, and its gem lands in the socket from an earlier
-- record. (The bug hid all sockets after socketing one gem into a 3-socket item until reopen.)
model.items[1].sockets = {}
reply("R|socket|0", "A|87|7001|255|0|rare|0|0",
    "F|87|0:sockets:1:socket:0:-1:0|1:sockets:1:socket:0:-1:0|2:sockets:1:socket:0:-1:0",
    "F|87|5:chc:2:gem:0:0:6002",
    "E|socket")
local split
for _, it in ipairs(J.model().items) do if it.guid == 87 then split = it end end
assert(#split.sockets == 3, "a split F list keeps every socket row, got " .. #split.sockets)
assert(split.sockets[1].gemEntry == 6002 and split.sockets[1].name == "Flawless Amethyst",
    "and its gem row lands in the socket from an earlier F record")
assert(split.sockets[2].gemEntry == 0 and split.sockets[3].gemEntry == 0, "the other sockets stay empty")
local bagGem
for _, g in ipairs(model.gems) do if g.guid == 90 then bagGem = g end end
assert(bagGem and bagGem.count == 3 and bagGem.bag == 0 and bagGem.slot == 1, "a stack record updates the bag gem")
local gemsBefore = #J.model().gems
reply("D|95", "E|socket")
assert(#J.model().gems == gemsBefore - 1, "a D record removes a gem the action used up")
-- A refusal frees the window for the next click and shows the server's text.
reset()
J.send("combine", 6002, 1)
assert(#sent == 1)
assert(J.send("combine", 6002, 3) == false and #sent == 1, "a request while the first is unanswered is refused")
reply("X|The Jeweler refused the operation.")
assert(lastMessage() == "The Jeweler refused the operation." and J.send("combine", 6002, 1), "after a refusal the next request goes")
reply("E|combine")
-- The bag update an action causes is not a reason to re-read; one the window did not cause is.
aio = {}
J.send("combine", 6002, 1)
watcher.scripts.OnEvent(watcher, "BAG_UPDATE"); watcher.scripts.OnUpdate(watcher, 0.5)
assert(countAio("Refresh") == 0, "an action's own bag update must not start a re-read")
reply("E|combine")
watcher.scripts.OnUpdate(watcher, 0.5)
assert(countAio("Refresh") == 0, "the bag update the action caused is forgotten, not saved for after the reply")
watcher.scripts.OnEvent(watcher, "BAG_UPDATE"); watcher.scripts.OnUpdate(watcher, 0.5)
assert(countAio("Refresh") == 1, "once the reply is in, a change the window did not cause refreshes")
-- A change the window did not cause that is still waiting out its debounce when a request goes out is
-- not re-read while that request is unanswered.
aio = {}
watcher.scripts.OnEvent(watcher, "BAG_UPDATE")
J.send("combine", 6002, 1)
watcher.scripts.OnUpdate(watcher, 0.5)
assert(countAio("Refresh") == 0, "no re-read while a request is unanswered")
reply("E|combine")
watcher.scripts.OnUpdate(watcher, 0.5)
assert(countAio("Refresh") == 1, "and it is read once the reply is in")
-- Only a reply to oneself is believed.
local bridge
for _, f in ipairs(frames) do if f.events.CHAT_MSG_ADDON then bridge = f end end
bridge.scripts.OnEvent(bridge, "CHAT_MSG_ADDON", "DCJEWELER", "B|1", "WHISPER", "Somebody")
bridge.scripts.OnEvent(bridge, "CHAT_MSG_ADDON", "DCJEWELER", "B|1", "PARTY", "Tester")
assert(J.model().balance.gold == "640000", "a record from anyone else is ignored")
-- Refresh does not leak frames.
local stable = #frames
for _ = 1, 20 do handlers.Show(nil, showPayload()) end
assert(#frames == stable, "Show leaked frames")
handlers.Error(nil, {message = "Refused"})
assert(lastMessage() == "Refused" and DCJewelerResponses.Error.message == "Refused")

----------------------------------------------------------------------------------------------------
-- 5b. Craft Jewelry: the third tab, laid out like the Blacksmith's Forge
----------------------------------------------------------------------------------------------------
local function craftPayload() local p = showPayload(); p.balance.gold = "120000"; return p end
handlers.Show(nil, craftPayload())
assert(#ui.tabs == 3 and ui.tabs[3].def.label == "Craft Jewelry", "Craft Jewelry is the third icon tab")
assert(not ui.craft:IsShown(), "the Craft tab is not the first one shown")
local function craftRowTexts()
    local out = {}
    for _, f in ipairs(frames) do
        if f.parent == ui.craftList and f.shown and f.row then out[#out + 1] = f.label.text end
    end
    return out
end
local function craftRow(label)
    for _, f in ipairs(frames) do if f.parent == ui.craftList and f.row and f.label.text == label then return f end end
    error("no craft row " .. label)
end
local function runCraftBar(seconds) local update = ui.craftBar.scripts.OnUpdate; if update then update(ui.craftBar, seconds) end end
local function craftOf(id) for _, r in ipairs(J.model().crafts) do if r.id == id then return r end end end

-- The rules.
local cb = {gold = "120000", deathsBreath = "0"}
local craftNames = {}
for _, entry in ipairs(Logic.craftRows(crafts(), cb, 64, {collapsed = {}})) do
    craftNames[#craftNames + 1] = entry.head and ("# " .. entry.head) or Logic.rowText(entry)
end
assert(table.concat(craftNames, "|") == "# Amulets|[1] Hellfire Amulet (Intelligence)|[1] Hellfire Amulet (Strength)|[1] Sovereign Amulet|"
    .. "# Rings|[1] Hellfire Ring|[5] Sovereign Ring",
    "headers Amulets then Rings, legendary first, [n] counts; got " .. table.concat(craftNames, "|"))
local byCraft = {}
for _, r in ipairs(crafts()) do byCraft[r.id] = r end
assert(Logic.craftCount(byCraft[364042], cb, 64) == 5, "materials limit: 5 Diamond and 5 Amethyst, gold allows 6")
assert(Logic.craftCount(byCraft[364042], {gold = "36000", deathsBreath = "0"}, 64) == 2, "gold limits: 36000 / 18000")
assert(Logic.craftCount(byCraft[364042], cb, 3) == 3, "the bag capacity limits")
assert(Logic.craftCount(byCraft[364041], cb, 64) == 1, "the scarcest material limits: one Emerald")
assert(Logic.craftCount(byCraft[398284], cb, 64) == 1, "Forgotten Soul 25 / 10 allows 2, the organs only 1")
assert(Logic.craftCount(byCraft[398285], {gold = "120000", deathsBreath = "0"}, 64) == 1)
byCraft[398284].materials[5].have = "9"
assert(Logic.craftCount(byCraft[398284], cb, 64) == 0, "9 Forgotten Souls of 10 make none")
byCraft[398284].materials[5].have = "99999999999999999999"
assert(Logic.craftCount(byCraft[398284], cb, 64) == 1, "an account-sized ledger count (past 2^53) is never read as a float")
byCraft[364042].enabled = false
assert(Logic.craftCount(byCraft[364042], cb, 64) == 0, "a disabled recipe makes none")
local function craftList(view)
    local out = {}
    for _, e in ipairs(Logic.craftRows(crafts(), cb, 64, view)) do out[#out + 1] = e.head and ("# " .. e.head) or e.recipe.name end
    return table.concat(out, "|")
end
assert(craftList({haveMats = true, collapsed = {}}) == "# Amulets|Hellfire Amulet (Intelligence)|Hellfire Amulet (Strength)|Sovereign Amulet|# Rings|Hellfire Ring|Sovereign Ring",
    "Have materials keeps what can be made now (this copy has all of it)")
assert(craftList({search = "RING", collapsed = {}}) == "# Rings|Hellfire Ring|Sovereign Ring", "search is case-blind and a page with no match has no header")
assert(craftList({search = "zzz", collapsed = {}}) == "", "no match, no rows")
assert(craftList({collapsed = {amulets = true}}):find("^# Amulets|# Rings"), "a collapsed page keeps its header and hides its recipes")
assert(craftList({search = "sovereign", collapsed = {amulets = true}}):find("Sovereign Amulet"), "a search opens a collapsed page")

-- The window: the tab, the list, the details.
click(ui.tabs[3])
assert(ui.sub.text == "CRAFT JEWELRY" and ui.craft:IsShown() and not ui.craftBar:IsShown(), "the tab shows its body")
assert(table.concat(craftRowTexts(), "|") == "- Amulets|[1] Hellfire Amulet (Intelligence)|[1] Hellfire Amulet (Strength)|[1] Sovereign Amulet|- Rings|[1] Hellfire Ring|[5] Sovereign Ring",
    "the drawn list, got " .. table.concat(craftRowTexts(), "|"))
assert(ui.craftDetail.name.text == "Hellfire Amulet (Intelligence)", "the first recipe is selected when none was")
click(craftRow("[5] Sovereign Ring"))
assert(ui.craftDetail.name.text == "Sovereign Ring" and ui.craftDetail.level.text == "Level 70 \226\128\162 rare", "name and level line")
assert(ui.craftDetail.cost.text == "Cost: 18,000 gold" and ui.craftQtyBox.text == "1")
assert(ui.craftDetail.reagents[1].label.text == "Marquise Diamond" and ui.craftDetail.reagents[1].count.text == "5 / 1"
    and ui.craftDetail.reagents[2].label.text == "Marquise Amethyst" and not ui.craftDetail.reagents[3].shown, "two materials, have / need")
click(ui.craftUp); click(ui.craftUp)
assert(ui.craftQtyBox.text == "3" and ui.craftDetail.cost.text == "Cost: 54,000 gold" and ui.craftDetail.reagents[1].count.text == "5 / 3",
    "the arrows step and the details follow")
for _ = 1, 5 do click(ui.craftUp) end
assert(ui.craftQtyBox.text == "5", "the right arrow stops at what can be made")
ui.craftQtyBox.focused = true
ui.craftQtyBox:SetText("99"); ui.craftQtyBox.scripts.OnTextChanged(ui.craftQtyBox, true)
assert(ui.craftQtyBox.text == "5", "typing more than can be made shows what will be made")
ui.craftQtyBox.focused = false
click(craftRow("[1] Hellfire Amulet (Strength)"))
assert(ui.craftDetail.reagents[5].label.text == "Forgotten Soul" and ui.craftDetail.reagents[5].count.text == "99,999,999,999,999,999,999 / 10"
    or ui.craftDetail.reagents[5].count.text:find("/ 10$"), "the fifth material is the Forgotten Soul, its ledger count in full")
assert(ui.craftDetail.cost.text == "Cost: 50,000 gold", "the Hellfire price")
assert(ui.craftDetail.name.textColor[1] == 1 and ui.craftDetail.name.textColor[2] == .5, "a legendary's name is orange")

-- Create: one click starts the 2 s bar; the request goes once it is full, with the recipe and the count.
click(craftRow("[5] Sovereign Ring"))
click(ui.craftUp); click(ui.craftUp)
reset()
click(ui.craftOne)
assert(#sent == 0 and J.Crafting() and ui.craftBar:IsShown() and ui.craftBar.text.text == "Crafting 3 Sovereign Ring",
    "a passing click starts the bar and sends nothing yet")
assert(ui.craftOne.disabled and ui.craftAll.disabled and ui.craftQtyBox.mouseEnabled == false, "the controls lock while it runs")
runCraftBar(1.99)
assert(#sent == 0, "nothing is sent before the bar is full")
runCraftBar(0.02)
assert(#sent == 1 and lastSent().prefix == "DCJEWELER" and lastSent().body == "craft\t364042\t3" and lastSent().distribution == "WHISPER",
    "Create sends craft id count, got " .. tostring(lastSent() and lastSent().body))
assert(not ui.craftBar:IsShown() and not J.Crafting(), "the bar is gone once it has sent")
click(ui.craftOne); click(ui.craftAll)
assert(#sent == 1 and not J.Crafting(), "a click while the last request is unanswered sends nothing and starts no bar")
-- The reply: the window reads the catalogue again (account materials fire no bag event).
aio = {}
reply("R|craft|3", "B|66000", "E|craft")
watcher.scripts.OnUpdate(watcher, 0.5)
assert(countAio("Refresh") == 1, "a craft's reply has the window read Show again, got " .. countAio("Refresh"))
-- Create All is one request for all that can be made: the reply left 66000 gold, which pays for 3 of the 5 the materials allow.
reset()
click(ui.craftAll); runCraftBar(2)
assert(#sent == 1 and lastSent().body == "craft\t364042\t3", "Create All makes what the gold (66000 after the reply's B record) allows, got " .. tostring(lastSent() and lastSent().body))
reply("E|craft")

-- Cancelling: closing, the gossip ending, combat and another tab stop the bar with the red line and send nothing.
local function cancelCraft(name, cancel)
    reset()
    click(ui.craftOne)
    assert(J.Crafting(), name .. ": the bar runs")
    cancel()
    assert(not J.Crafting() and not ui.craftBar:IsShown() and #sent == 0, name .. ": the bar is gone and nothing is sent")
    assert(lastMessage() == "Crafting cancelled. Nothing was used.", name .. ": the red line, got " .. tostring(lastMessage()))
    assert(not ui.craftOne.disabled and ui.craftQtyBox.mouseEnabled == true, name .. ": the controls are back")
    runCraftBar(5)
    assert(#sent == 0, name .. ": a bar that was cancelled never sends later")
end
cancelCraft("closing the window", function() ui.frame:Hide(); ui.frame.scripts.OnHide(ui.frame) end)
ui.frame:Show(); handlers.Show(nil, craftPayload()); click(ui.tabs[3])
cancelCraft("the gossip ending", function() ui.frame.scripts.OnEvent(ui.frame, "GOSSIP_CLOSED") end)
cancelCraft("entering combat", function() ui.frame.scripts.OnEvent(ui.frame, "PLAYER_REGEN_DISABLED") end)
cancelCraft("switching tab", function() click(ui.tabs[1]) end)
assert(ui.sub.text == "COMBINE GEMS" and not ui.craft:IsShown() and ui.combineShown ~= false, "the tab did switch")
click(ui.tabs[3])
assert(ui.sub.text == "CRAFT JEWELRY" and ui.craft:IsShown(), "and back")

-- While the bar runs the choice, the quantity and a second click are locked: nothing changes under it.
click(craftRow("[5] Sovereign Ring"))
click(ui.craftUp)
reset()
click(ui.craftOne)
assert(J.Crafting(), "the bar runs")
runCraftBar(0.5)
local running = ui.craftBar.fill:GetWidth()
click(craftRow("[1] Hellfire Ring"))
assert(ui.craftDetail.name.text == "Sovereign Ring", "the recipe choice is locked while the bar runs")
click(ui.craftUp)
assert(ui.craftQtyBox.text == "2", "the arrows are locked while the bar runs")
assert(J.Craft(1) == false and ui.craftBar.fill:GetWidth() == running, "a second Create does not restart the bar")
runCraftBar(2)
assert(#sent == 1 and lastSent().body == "craft\t364042\t2", "the one request carries the count the bar started with, got " .. tostring(lastSent() and lastSent().body))
reply("E|craft")
click(ui.craftDown)

-- Have materials drops what cannot be made now.
local poorPayload = craftPayload(); poorPayload.balance.gold = "20000"
handlers.Show(nil, poorPayload)
click(ui.tabs[3])
ui.craftCheck:SetChecked(true); ui.craftCheck.scripts.OnClick(ui.craftCheck)
local made = table.concat(craftRowTexts(), "|")
assert(made:find("Sovereign Amulet", 1, true) and made:find("Sovereign Ring", 1, true) and not made:find("Hellfire", 1, true),
    "20000 gold pays for the Sovereign pair only, got " .. made)
ui.craftCheck:SetChecked(false); ui.craftCheck.scripts.OnClick(ui.craftCheck)
assert(craftRow("Hellfire Ring") and craftRow("[1] Sovereign Ring"), "unchecked, everything is listed again")
handlers.Show(nil, craftPayload())
click(ui.tabs[3])

-- Greyed out: a recipe that cannot be made even once; a disabled one shows its reason.
click(craftRow("[1] Hellfire Ring"))
craftOf(364711).materials[1].have = "0"
handlers.Show(nil, (function() local p = craftPayload(); p.crafts = J.model().crafts; return p end)())
click(ui.tabs[3])
reset()
click(craftRow("Hellfire Ring"))
assert(ui.craftOne.disabled and ui.craftAll.disabled, "a short material greys Create and Create All")
assert(J.Craft(1) == false and not J.Crafting() and #sent == 0, "the maker refuses even when asked directly")
assert(ui.craftDetail.reagents[1].count.textColor[2] < .5, "a short material is red")
local disabled = crafts()
disabled[1].enabled, disabled[1].reason = false, "This recipe is unavailable until its missing crafting support is implemented."
local payload = craftPayload(); payload.crafts = disabled
handlers.Show(nil, payload)
click(ui.tabs[3])
click(craftRow("Sovereign Ring"))
assert(ui.craftDetail.note.text:find("unavailable") and ui.craftOne.disabled, "a disabled recipe says why and cannot be made")
-- No gold, none.
handlers.Show(nil, craftPayload())
click(ui.tabs[3])
local poor = craftPayload(); poor.balance.gold = "100"
handlers.Show(nil, poor)
click(ui.tabs[3])
click(craftRow("Sovereign Ring"))
assert(ui.craftOne.disabled and ui.craftDetail.cost.textColor[2] < .5, "no gold: greyed, the cost line red")
assert(ui.craftFunds.text == "Your gold: 100", "the gold line, got " .. tostring(ui.craftFunds.text))
-- Search and Have materials on the drawn list.
handlers.Show(nil, craftPayload())
click(ui.tabs[3])
ui.craftSearchBox:SetText("ring"); ui.craftSearchBox.scripts.OnTextChanged(ui.craftSearchBox)
assert(table.concat(craftRowTexts(), "|") == "- Rings|[1] Hellfire Ring|[5] Sovereign Ring", "search narrows the drawn list, got " .. table.concat(craftRowTexts(), "|"))
ui.craftSearchBox:SetText(""); ui.craftSearchBox.scripts.OnTextChanged(ui.craftSearchBox)
click(craftRow("- Amulets"))
assert(table.concat(craftRowTexts(), "|") == "+ Amulets|- Rings|[1] Hellfire Ring|[5] Sovereign Ring", "a header click closes its page, got " .. table.concat(craftRowTexts(), "|"))
click(craftRow("+ Amulets"))
-- Show does not leak frames with the Craft tab open.
local craftStable = #frames
for _ = 1, 20 do handlers.Show(nil, craftPayload()) end
assert(#frames == craftStable, "Show leaked frames on the Craft tab")
click(ui.tabs[1])

-- ---------------------------------------- the shared window look (DC.Style)

-- Ruling 2026-10-01: one look for every Torment window, now defined once in
-- dc_aio_ui.lua. This file carries the same values as the Torment addon's DC.Style
-- for the mix where the addon is older than the AIO code - the addon's own copy is
-- parsed here field by field, and test_skillbar_client.lua pins the Skills window's
-- copy against the module's PANEL, so all agree whichever side is newer.
local addonSource = assert(io.open("client-patch/addons/Torment/WindowStyle.lua")):read("*a")
local styleSource = assert(addonSource:match("local WINDOW_BACKDROP%s*=%s*(%b{})"),
    "WindowStyle.lua publishes WINDOW_BACKDROP for the shared DC.Style")
local uiModuleSource = assert(io.open("mod-diablocraft/lua/aio/dc_aio_ui.lua")):read("*a")
local panelSource = assert(uiModuleSource:match("local PANEL=(%b{})"), "dc_aio_ui.lua declares the shared PANEL")
local function field(source, name) return assert(source:match(name .. '%s*=%s*"([^"]+)"')):gsub("\\\\", "\\") end
local function numberOf(source, name) return tonumber(assert(source:match(name .. "%s*=%s*(%d+)"))) end
local look = DiablocraftJewelerFrame.backdrop
assert(look, "the Jeweler window has a backdrop")
assert(look.bgFile == field(styleSource, "bgFile") and look.edgeFile == field(styleSource, "edgeFile")
    and look.bgFile == field(panelSource, "bgFile"),
    "the window and the addon's DC.Style draw the same dialog textures")
assert(look.tile == true and look.tileSize == numberOf(styleSource, "tileSize")
    and look.edgeSize == numberOf(styleSource, "edgeSize"), "the same tiling and edge size")
for _, key in ipairs({"left", "right", "top", "bottom"}) do
    assert(look.insets[key] == numberOf(styleSource, key), "the same " .. key .. " inset")
end

-- And with the addon present and newer, the window must READ its table rather
-- than its own copy.
local first = DiablocraftJewelerFrame
Diablocraft = {Style = {backdrop = {bgFile = "Interface\\Marker", edgeFile = "Interface\\Marker"}}}
dofile("mod-diablocraft/lua/aio/dc_jeweler.lua")
assert(DiablocraftJewelerFrame ~= first, "the second load builds a second window")
assert(DiablocraftJewelerFrame.backdrop.bgFile == "Interface\\Marker",
    "a Jeweler loaded with the addon's shared DC.Style must use it, got "
        .. tostring(DiablocraftJewelerFrame.backdrop.bgFile))
Diablocraft = nil

print("PASS Jeweler client: list order, [n] limits, quantity clamp, one request per click, socket drag/drop, swap, "
    .. "the away rule, Shift+Right-click hooks, no repair, reply model and refresh")
