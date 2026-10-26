-- luacheck: ignore 111 112 113 121 122 431 432
-- Run from the repo root: lua mod-diablocraft/scripts/tests/ui/test_follower_window.lua
--
-- The Follower window (diablocraft-gh1c1.5): dc_follower.lua's client half against a stub 3.3.5a client, fed the records of the wire in
-- docs/contracts/followers.md "Messages" (the bridge prefix DCFOLLOWER), and its server half (the worn items' tooltip records, read from
-- the player's own gear rows). What it pins: the window opens on a complete reply and not before; the portrait, level, status, the four
-- attributes, Damage and Toughness as whole grouped numbers (a stray decimal is cut); the 14 slots (art, icon, a slot the follower cannot
-- use dimmed); the four tier rows (locked, unpicked, picked, every skill); the Details rows in their groups; Dismiss (and no Hire) and the
-- hub; the equip, unequip and skill requests, one at a time; a refusal said and the window left as it was; the tooltip records asked
-- once per set of worn items; the tooltips (an item's, a skill's text with "3 seconds" and not "3.00 seconds").
-- scripts/tests/ui/test_follower_window.py runs this file again on a mutated copy of dc_follower.lua per rule (DC_FOLLOWER_LUA names the
-- copy) and requires every run to fail.
local SOURCE = os.getenv("DC_FOLLOWER_LUA") or "mod-diablocraft/lua/aio/dc_follower.lua"

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)

local unpack = unpack or table.unpack
local sent, aio, clock = {}, {}, 0
local cursor
local shownItem, addedRecords = {}, {}
local handlers, side = nil, "server"
function UnitName() return "Tester" end
function GetRealmName() return "Diablocraft" end
function GetTime() return clock end
function GetItemIcon(entry) return "icon:" .. tostring(entry) end
function GetCursorInfo() if cursor then return "item", cursor end end
function ClearCursor() cursor = nil end
function SendAddonMessage(prefix, body, distribution, target)
    sent[#sent + 1] = {prefix = prefix, body = body, distribution = distribution, target = target}
end
function PickupContainerItem() end
function DCShowItemTooltip(tooltip, guid) shownItem[#shownItem + 1] = {tooltip = tooltip, guid = guid} end
function DCAddItemTooltips(list) addedRecords[#addedRecords + 1] = list end
AIO = {
    AddAddon = function() return side == "server" end,
    AddHandlers = function(_, table_) handlers = table_; return table_ end,
    Handle = function(...) aio[#aio + 1] = {...} end,
}
local function lastSent() return sent[#sent] end
local function reset() sent, aio = {}, {} end

----------------------------------------------------------------------------------------------------
-- The server half
----------------------------------------------------------------------------------------------------
local queries, throttle, recordsFor = {}, true, nil
DCThrottle = {Allow = function() return throttle end}
function CharDBQuery(sql)
    queries[#queries + 1] = sql
    local done = false
    return {GetUInt32 = function(_, column) return column == 0 and 501 or 2001 end, NextRow = function() done = true; return false end,
        done = function() return done end}
end
function DCItemTooltipRecords(cells) recordsFor = cells; return {[501] = {guid = 501}} end
local player = {GetGUIDLow = function() return 77 end}
local answered = {}
AIO.Handle = function(target, channel, method, payload) answered[#answered + 1] = {target = target, channel = channel, method = method, payload = payload} end
dofile(SOURCE)
local serverHandlers = handlers
assert(serverHandlers and serverHandlers.Tooltips, "the server half registers Tooltips")
serverHandlers.Tooltips(player, 2)
assert(#queries == 1 and queries[1]:find("g.guid=77", 1, true) and queries[1]:find("g.follower=2", 1, true)
    and queries[1]:find("dc_character_follower_gear", 1, true), "the records come from the player's own gear rows: " .. tostring(queries[1]))
assert(#answered == 1 and answered[1].target == player and answered[1].channel == "DiablocraftFollower" and answered[1].method == "Tooltips"
    and answered[1].payload.records[501], "the records are answered to the asker on the follower channel")
assert(recordsFor and recordsFor[1].guid == 501 and recordsFor[1].entry == 2001, "the cells carry the gear row's item guid and entry")
for _, bad in ipairs({0, 4, -1, 1.5, "1", "1 or 1=1", math.huge}) do serverHandlers.Tooltips(player, bad) end
assert(#queries == 1, "a follower that is not 1 to 3 is dropped before any query")
throttle = false
serverHandlers.Tooltips(player, 1)
assert(#queries == 1, "a flood is dropped by the shared bucket")
throttle = true

----------------------------------------------------------------------------------------------------
-- The client half
----------------------------------------------------------------------------------------------------
side = "client"
AIO.Handle = function(...) aio[#aio + 1] = {...} end
dofile("mod-diablocraft/lua/aio/dc_aio_ui.lua")
dofile("mod-diablocraft/lua/aio/dc_follower_skills.lua")
dofile(SOURCE)
local F = DCFollower
assert(F and F.Logic and F.ui, "dc_follower.lua must publish DCFollower (the logic and its frames)")
local Logic, ui = F.Logic, F.ui
assert(DCFollowerData and DCFollowerData.followers[1].name == "Kormac", "the generated skills are loaded")

local function bridge()
    for _, f in ipairs(frames) do if f.events.CHAT_MSG_ADDON then return f end end
end
local function reply(...)
    for _, record in ipairs({...}) do
        local b = bridge()
        b.scripts.OnEvent(b, "CHAT_MSG_ADDON", "DCFOLLOWER", record, "WHISPER", "Tester")
    end
end
local function click(object, button) object.scripts.OnClick(object, button or "LeftButton") end
local function lastMessage() return UIErrorsFrame.lines[#UIErrorsFrame.lines] end

-- The records of a reply, as the server orders them (W, A, every D, every G, every K, E).
local DETAILS = {
    "D|offense|Damage Increased by Strength|32,940.00%", "D|offense|Attacks per Second|1.57", "D|offense|Critical Hit Chance|40.00%",
    "D|defense|Armor|14,880", "D|defense|Block Amount|0-0", "D|defense|Dodge Chance|0.00%",
    "D|life|Maximum Life|2,190,758", "D|life|Life Steal|0.00%", "D|adventure|Gold Find|26.00%",
}
local KEYS = {"relic", "head", "shoulders", "chest", "gloves", "bracers", "belt", "pants", "boots", "ring1", "ring2", "neck", "mainhand", "offhand"}
local function open(follower, opts)
    opts = opts or {}
    local worn = opts.worn or {head = {2001, 501}, mainhand = {2002, 502}}
    local out = {string.format("W|%d|%d|%d|%d", follower, opts.hired == false and 0 or 1, opts.hub and 1 or 0, opts.level or 70),
        opts.sheet or "A|28410|1040|980|9870|3175765|80300688"}
    for _, row in ipairs(DETAILS) do out[#out + 1] = row end
    for _, key in ipairs(KEYS) do
        local cell = worn[key]
        out[#out + 1] = string.format("G|%s|%d|%d|%d", key, cell and cell[1] or 0, cell and cell[2] or 0, (opts.unusable or {})[key] and 0 or 1)
    end
    local levels = follower == 3 and {15, 20, 25, 30} or {5, 10, 15, 20}
    for tier = 1, 4 do
        out[#out + 1] = string.format("K|%d|%d|%s|%d", tier, levels[tier], (opts.picks or {})[tier] or "", opts.all and 1 or 0)
    end
    out[#out + 1] = "E"
    reply(unpack(out))
end

----------------------------------------------------------------------------------------------------
-- 1. The rules
----------------------------------------------------------------------------------------------------
assert(Logic.whole("3175765") == "3,175,765" and Logic.whole("80300688") == "80,300,688" and Logic.whole("0") == "0")
assert(Logic.whole("3175765.50") == "3,175,765", "a stray decimal is cut, never rounded: " .. Logic.whole("3175765.50"))
assert(Logic.whole(nil) == "0" and Logic.whole("") == "0")
local lines = Logic.tipLines("Cooldown: 10 seconds\nTaunt enemies for 3.00 seconds when you are hit, then 1.50 seconds, 5.00 yards, 2.00 second.")
assert(lines[1] == "Cooldown: 10 seconds" and lines[2] == "Taunt enemies for 3 seconds when you are hit, then 1.50 seconds, 5.00 yards, 2 second.",
    "3.00 seconds reads 3 seconds; 1.50 stays; yards are not seconds: " .. lines[2])
assert(Logic.bagIndex(0, 1) == 25523 and Logic.bagIndex(0, 16) == 25538, "the backpack is container 255, slots 23 to 38")
assert(Logic.bagIndex(1, 1) == 1900 and Logic.bagIndex(4, 3) == 2202, "an equipped bag is 19 to 22 times 100, plus its 0-based slot")
assert(Logic.locked({level = 15}, 14) and not Logic.locked({level = 15}, 15))
local skills = DCFollowerData.followers[1].tiers[1].skills
assert(select(3, Logic.tierRow({level = 5, pick = ""}, skills, 70)) == "unpicked")
assert(select(2, Logic.tierRow({level = 5, pick = "intervene"}, skills, 70)) == "Intervene")
assert(select(1, Logic.tierRow({level = 5, pick = "heal"}, skills, 70)) == "Selected Level 5 Skill")
assert(select(2, Logic.tierRow({level = 5, pick = "", all = true}, skills, 70)) == "Heal and Intervene")
assert(select(3, Logic.tierRow({level = 5, pick = "heal", all = true}, skills, 4)) == "locked", "locked wins over a pick and a relic")
assert(select(3, Logic.tierRow({level = 5, pick = "charge"}, skills, 70)) == "unpicked", "a pick that is not a skill of the tier is no pick")
assert(Logic.status({hired = true}) == "Following you" and Logic.status({hired = false}) == "Waiting in the Sanctum")
assert(Logic.request("open", 1) == "open\t1" and Logic.request("equip", 2, 25523, "mainhand") == "equip\t2\t25523\tmainhand"
    and Logic.request("unequip", 1, "ring1") == "unequip\t1\tring1" and Logic.request("skill", 3, 4, "fates-lapse") == "skill\t3\t4\tfates-lapse"
    and Logic.request("dismiss", 1) == "dismiss\t1", "the requests the window sends")
assert(Logic.request("hire", 1) == nil, "the window sends no hire")
assert(Logic.request("equip", 1, "25523", "head") == nil and Logic.request("equip", 1, 25523, "he ad") == nil
    and Logic.request("equip", 1, -1, "head") == nil and Logic.request("open", 1.5) == nil and Logic.request("repair", 1) == nil
    and Logic.request("equip", 1, 25523) == nil and Logic.request("skill", 1, 1, 2) == nil and Logic.request("skill", 1, 1, "a b") == nil
    and Logic.request("skill", 1, 1, "heal;x") == nil and Logic.request("skill", 1, 1, ("x"):rep(33)) == nil, "a field the bridge would refuse is never sent")

----------------------------------------------------------------------------------------------------
-- 2. The window opens on a complete reply
----------------------------------------------------------------------------------------------------
assert(not ui.frame:IsShown() and not ui.details:IsShown(), "nothing is open until the server pushes a follower")
reply("W|1|1|0|70", "A|28410|1040|980|9870|3175765|80300688")
assert(not ui.frame:IsShown(), "the window waits for E: one redraw per reply")
reply("E")
assert(ui.frame:IsShown() and ui.title.text == "Kormac" and ui.sub.text == "TEMPLAR", "the window is the follower's: name and kind")
reset()
reply("X|Not now.")
assert(lastMessage() == "Not now.", "a lone refusal is said as it is")

open(1, {picks = {"intervene", "", "charge", ""}})
assert(ui.levelText.text == "Level 70" and ui.statusText.text == "Following you" and ui.statusText.textColor[2] == 1, "level and the green status")
assert(ui.portrait.icon.texture == "Interface\\Icons\\spell_holy_devotionaura", "the follower's own portrait square")
local expected = {"28,410", "1,040", "980", "9,870"}
for index = 1, 4 do assert(ui.attrValues[index].text == expected[index], "attribute " .. index .. ": " .. tostring(ui.attrValues[index].text)) end
assert(ui.damageValue.text == "3,175,765" and ui.toughValue.text == "80,300,688", "Damage and Toughness are whole grouped numbers, no decimals")
open(1, {sheet = "A|1|2|3|4|3175765.75|80300688.5"})
assert(ui.damageValue.text == "3,175,765" and ui.toughValue.text == "80,300,688", "a decimal from the server is cut")
open(1, {picks = {"intervene", "", "charge", ""}})

-- the gear: stock empty art, the item's icon, a slot the follower cannot use dimmed
local function slotOf(key) for index, def in ipairs(Logic.SLOTS) do if def.key == key then return ui.slots[index] end end end
assert(#ui.slots == 14 and slotOf("head").icon.texture == "icon:2001" and slotOf("mainhand").icon.texture == "icon:2002", "worn items show their icons")
assert(slotOf("chest").icon.texture == "Interface\\PaperDoll\\UI-PaperDoll-Slot-Chest" and slotOf("relic").icon.texture == "Interface\\PaperDoll\\UI-PaperDoll-Slot-Relic",
    "an empty slot shows the stock slot art")
open(1, {unusable = {offhand = true}})
assert(slotOf("offhand").icon.desaturated == true and slotOf("offhand").alpha < 1 and slotOf("head").alpha == 1 and slotOf("head").icon.desaturated == false,
    "a slot this follower cannot use is dimmed and grey")
open(1, {picks = {"intervene", "", "charge", ""}})

-- the tiers
local function tierText(tier) return ui.tiers[tier].header.text .. " / " .. ui.tiers[tier].name.text end
assert(tierText(1) == "Selected Level 5 Skill / Intervene" and tierText(2) == "Level 10 Skill / Choose a skill"
    and tierText(3) == "Selected Level 15 Skill / Charge", "picked and unpicked rows: " .. tierText(1) .. " | " .. tierText(2) .. " | " .. tierText(3))
assert(ui.tiers[1].icons[2].borderColor[1] == 1 and ui.tiers[1].icons[1].borderColor[1] ~= 1, "the picked icon is gold-outlined, the other plain")
assert(ui.tiers[1].icons[1].icon.desaturated == true and ui.tiers[1].icons[2].icon.desaturated == false, "the unpicked icon is grey")
assert(ui.tiers[1].icons[1].icon.texture == "Interface\\Icons\\spell_nature_rejuvenation", "the skill's stock icon")
open(1, {all = true})
assert(tierText(1) == "Level 5 Skills / Heal and Intervene" and ui.tiers[1].icons[1].borderColor[1] == 1 and ui.tiers[1].icons[2].borderColor[1] == 1,
    "a relic that gives every skill lights both and names both")
open(3, {level = 22, hired = false})
assert(ui.title.text == "Eirena" and ui.statusText.text == "Waiting in the Sanctum" and ui.statusText.textColor[2] < 1, "a follower that is not hired waits in the Sanctum")
assert(tierText(1) == "Level 15 Skill / Choose a skill" and tierText(2) == "Level 20 Skill / Choose a skill"
    and tierText(3) == "Unlocks at level 25 / Locked" and tierText(4) == "Unlocks at level 30 / Locked", "tiers above the level are locked: " .. tierText(3))
assert(ui.tiers[3].icons[1].icon.desaturated == true and ui.tiers[3].icons[2].icon.desaturated == true)

-- the Details panel
open(1, {})
assert(not ui.details:IsShown(), "the Details panel is shut when the window opens")
click(ui.detailsButton)
assert(ui.details:IsShown(), "Details opens the panel")
local shown = {}
for _, line in ipairs(ui.detailLines) do
    if line.head.shown then shown[#shown + 1] = "# " .. line.head.text end
    if line.label.shown then shown[#shown + 1] = line.label.text .. "=" .. line.value.text end
end
assert(table.concat(shown, "|") == "# Offense|Damage Increased by Strength=32,940.00%|Attacks per Second=1.57|Critical Hit Chance=40.00%"
    .. "|# Defense|Armor=14,880|Block Amount=0-0|Dodge Chance=0.00%|# Life|Maximum Life=2,190,758|Life Steal=0.00%|# Adventure|Gold Find=26.00%",
    "the rows in their groups as the server sent them, got " .. table.concat(shown, "|"))
click(ui.detailsButton)
assert(not ui.details:IsShown(), "Details shuts it again")
click(ui.detailsButton)
ui.frame:Hide(); ui.frame.scripts.OnHide(ui.frame)
assert(not ui.details:IsShown(), "closing the window shuts the panel too")
ui.frame:Show()

----------------------------------------------------------------------------------------------------
-- 3. Dismiss, no Hire, equip, unequip, picks
----------------------------------------------------------------------------------------------------
open(1, {hired = true, hub = false})
assert(ui.dismissButton.text == "Dismiss" and ui.dismissButton:IsShown() and not ui.dismissButton.disabled, "a hired follower is dismissed anywhere")
reset(); click(ui.dismissButton)
assert(#sent == 1 and lastSent().prefix == "DCFOLLOWER" and lastSent().body == "dismiss\t1" and lastSent().distribution == "WHISPER" and lastSent().target == "Tester")
click(ui.dismissButton)
assert(#sent == 1, "a click while the last request is unanswered sends nothing")
reply("X|Nope.")
assert(lastMessage() == "Nope." and #sent == 1)
click(ui.dismissButton)
assert(#sent == 2 and lastSent().body == "dismiss\t1", "a refusal frees the next request")
reply("X|Nope.")
-- Hiring is by talking to the follower in the Sanctum: the window has no Hire button, in or out of the hub, and sends no hire.
for _, hub in ipairs({false, true}) do
    open(2, {hired = false, hub = hub})
    assert(not ui.dismissButton:IsShown(), "a follower that is not hired has nothing to dismiss: no button")
    for _, f in ipairs(frames) do assert(f.text ~= "Hire", "no Hire button exists, hub " .. tostring(hub)) end
    reset(); F.Dismiss()
    assert(#sent == 0, "Dismiss on a follower that is not hired sends nothing")
end
open(2, {hired = true, hub = true})
assert(ui.dismissButton:IsShown(), "the hired follower has its Dismiss")
open(2, {hired = false, hub = true})

-- equip: an item on the cursor, put on a slot; the backpack's first slot is 25523
reset()
cursor = 12345
PickupContainerItem(0, 1)   -- the hook records where it was picked up; the stub does nothing, the hook above it does
local cursorHook = Mock.hooks.PickupContainerItem
assert(cursorHook, "the pick-up is watched with hooksecurefunc")
click(slotOf("belt"))
assert(#sent == 1 and lastSent().body == "equip\t2\t25523\tbelt" and cursor == nil, "the cursor's item goes to the slot named, from the bag it came from, got " .. tostring(lastSent() and lastSent().body))
open(2, {hired = false, hub = true})
reset()
cursor = 1
PickupContainerItem(2, 5)
click(slotOf("ring2"))
assert(lastSent().body == "equip\t2\t2004\tring2", "a bag's slot is its container times 100 plus the 0-based slot, got " .. tostring(lastSent().body))
open(2, {hired = false, hub = true})
reset()
click(slotOf("belt"))
assert(#sent == 0, "an empty hand on an empty slot does nothing")
click(slotOf("head"))
assert(#sent == 0, "a plain click on a worn slot with an empty hand takes nothing off")
click(slotOf("head"), "RightButton")
assert(#sent == 1 and lastSent().body == "unequip\t2\thead", "right-click takes a worn item off")
open(2, {hired = false, hub = true})
reset()
click(slotOf("belt"), "RightButton")
assert(#sent == 0, "right-click on an empty slot does nothing")

-- picks: the second icon of tier 2 of the Scoundrel
reset()
ui.tiers[2].icons[2].scripts.OnClick(ui.tiers[2].icons[2])
assert(#sent == 1 and lastSent().body == "skill\t2\t2\tanatomy", "an icon picks its skill by its id, got " .. tostring(lastSent() and lastSent().body))
open(3, {level = 22, hired = false})
reset()
click(ui.tiers[3].icons[1])
assert(#sent == 0, "a locked tier's icon sends nothing")

----------------------------------------------------------------------------------------------------
-- 4. The tooltips
----------------------------------------------------------------------------------------------------
reset(); addedRecords = {}
open(1, {worn = {head = {2001, 901}, mainhand = {2002, 902}}})
assert(#aio == 1 and aio[1][1] == "DiablocraftFollower" and aio[1][2] == "Tooltips" and aio[1][3] == 1, "the worn items' records are asked of the server once")
open(1, {worn = {head = {2001, 901}, mainhand = {2002, 902}}})
assert(#aio == 1, "the same worn set is not asked twice")
open(1, {worn = {head = {2001, 901}, mainhand = {2002, 902}, belt = {2003, 903}}})
assert(#aio == 2 and aio[2][3] == 1, "a new worn item is asked for")
open(1, {worn = {}})
assert(#aio == 2, "nothing worn, nothing to ask")
handlers.Tooltips(nil, {records = {[501] = {guid = 501}}})
assert(#addedRecords == 1 and addedRecords[1][501], "the answer goes to the tooltip addon")
open(1, {worn = {head = {2001, 901}}})
local head = slotOf("head")
head.scripts.OnEnter(head)
assert(GameTooltip.hyperlink == "item:2001:0:0:0:0:0:0:0" and GameTooltip.owner == head and shownItem[#shownItem].guid == 901 and GameTooltip.shown,
    "a worn item's tooltip is its link and the tooltip addon's rolled lines by guid")
local relic = slotOf("relic")
relic.scripts.OnEnter(relic)
assert(GameTooltip.lines[1] == "Templar Relic", "an empty relic slot is named for its kind, got " .. tostring(GameTooltip.lines[1]))
local skill = ui.tiers[1].icons[2]
skill.scripts.OnEnter(skill)
assert(GameTooltip.lines[1] == "Intervene" and GameTooltip.lines[3]:find("for 3 seconds when you are hit", 1, true)
    and not GameTooltip.lines[3]:find("3.00", 1, true), "a skill's tooltip is its text with whole seconds, got " .. tostring(GameTooltip.lines[3]))
head.scripts.OnLeave(head)
assert(not GameTooltip.shown)

-- Show leaks no frames
local stable = #frames
for _ = 1, 30 do open(1, {}) end
assert(#frames == stable, "a reply leaked frames")

print("PASS Follower window: wire records, whole numbers, 14 slots, four tiers, Details, Dismiss and no Hire, equip, unequip, picks, tooltips, server half")
