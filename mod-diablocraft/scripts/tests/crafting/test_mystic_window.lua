-- luacheck: ignore 111 112 113 121 122 431
-- diablocraft-0atm: the Mystic (Enchant) window, rebuilt the D3 way and wired to the server.
--
-- The window is built here against the one shared strict 3.3.5a widget mock (dc_widget_mock.lua) and
-- the item tooltip's own formatter
-- (dc_tooltip.lua's DCAFFIXLINE, loaded for real, so the wording is the shipped one), then the whole
-- exchange is driven: the Show payload's item index, the DCARTISAN request goes out, and the reply's
-- records come back through the window's own CHAT_MSG_ADDON listener. What is pinned, beside the
-- approved mockups' flow (mockup-Main.dc.html and mockup-Step2..6.dc.html) and the contract
-- (docs/contracts/mystic-enchant-messages.md):
--   * the Blacksmith and Jeweler's look (the designer, round 3, 2026-10-05): the shared window, the gold
--     title and small-caps subtitle, square icon tabs placed as the Blacksmith's, a square item slot
--     and icon, the stock buttons, "Your gold";
--   * the `?` is drawn as help, and no missing-texture question mark is drawn anywhere: a material
--     with no icon (the jewellery gem, entry 0) is left out until a property is picked, then shown
--     by name and count over an empty slot;
--   * a grey button says why, in the server's refusal words;
--   * the server's Close (the player walked away) hides the window;
--   * the six steps: the title, the intro, the locked note, the choose note, the materials and
--     the button's label, grey and coin, all drawn from the records;
--   * the client decides nothing: the gold, the cost, the material counts, the lines and the three
--     choices are the server's own fields and strings, worded by the tooltip's formatter (so a
--     property reads the same in the window and in the tooltip);
--   * the four verbs and their bounds: place, preview, roll, pick, one request at a time, a second
--     one waiting for E or X, and no offer/choose/quote anywhere;
--   * the item goes in by drag or by a plain right-click in the bags (the claim, and the stock
--     click turned into a no-op for that one click);
--   * the `?` asks the server once per line and shows what came back;
--   * the first choice shows at once, the second and third one second apart, and Select Property stays
--     disabled until one is clicked;
--   * a refusal X shows the server's text and keeps the window's state.
--
-- scripts/tests/crafting/test_mystic_window.py runs this file again on a copy of dc_crafting.lua with one rule
-- removed, and requires every run to fail.
local UI_SOURCE = os.getenv("DC_UI_LUA") or "mod-diablocraft/lua/aio/dc_aio_ui.lua"
local TOOLTIP_SOURCE = os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua"
local WINDOW_SOURCE = os.getenv("DC_MYSTIC_LUA") or "mod-diablocraft/lua/aio/dc_crafting.lua"

----------------------------------------------------------------------------------------------------
-- The shared strict widget mock (dc_widget_mock.lua) and this test's own client globals
----------------------------------------------------------------------------------------------------
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames          -- every widget made, in creation order
Mock.setScreen(1024, 768)
local sent, asked = {}, {}
local clock = 0
local combat, cursorHeld = false, false
NUM_CONTAINER_FRAMES, MAX_CONTAINER_ITEMS = 13, 36
function UnitName() return "Tester" end
function GetRealmName() return "Diablocraft" end
function GetTime() return clock end
function GetItemIcon(entry) return "icon:" .. tostring(entry) end
function GetItemInfo() return nil end
function GetItemName(entry) return "item:" .. tostring(entry) end
function GetCursorInfo() if cursorHeld then return "item" end end
function ClearCursor() cursorHeld = false end
function InCombatLockdown() return combat end
function IsShiftKeyDown() return false end
function IsControlKeyDown() return false end
function IsAltKeyDown() return false end
function GetContainerNumSlots() return 4 end
function GetContainerItemLink(bag, slot) if slot == 1 or slot == 4 then return "item:1" end end
-- The stock pickup calls; the window hooks them to remember which bag item the cursor holds.
function PickupContainerItem() end
function PickupInventoryItem() end
function SendAddonMessage(prefix, body, distribution, target)
    sent[#sent + 1] = {prefix = prefix, body = body, distribution = distribution, target = target}
end
-- The real formatter, doubled faithfully: groups in threes.
local function group(v)
    local out, more = tostring(v or "0"), 1
    while more > 0 do out, more = out:gsub("^(%-?%d+)(%d%d%d)", "%1,%2") end
    return out
end
-- Inventory.lua's right-click claims: the Torment sheet and its bag rules yield while any is true.
local claims = {}
Diablocraft = {Econ = {Gold = group, OnChange = function() end},
    ClaimRightClick = function(claim) claims[#claims + 1] = claim end}
-- Worn: the head (inventory id 1) and the first ring (id 11); every other worn slot is empty.
local worn = {[1] = "item:2", [11] = "item:3"}
function GetInventoryItemLink(_, id) return worn[id] end
local handlersByChannel = {}
AIO = {AddAddon = function() return false end,
    AddHandlers = function(channel, handlers) handlersByChannel[channel] = handlers return handlers end,
    Handle = function(...) asked[#asked + 1] = {...} end}

----------------------------------------------------------------------------------------------------
-- Load the shared look, the item tooltip (its formatter words the rows) and the window
----------------------------------------------------------------------------------------------------
dofile(UI_SOURCE)
dofile(TOOLTIP_SOURCE)
dofile(WINDOW_SOURCE)
assert(DCUI and DCAFFIXLINE and Mystic and Mystic.ui and handlersByChannel.DiablocraftCrafting,
    "the shared look, the tooltip's formatter, the window and its AIO channel must load")
local ui = Mystic.ui
local Show = handlersByChannel.DiablocraftCrafting.Show
local Tables = handlersByChannel.DiablocraftCrafting.Tables
assert(type(Show) == "function" and type(Tables) == "function", "the window registers Show and Tables")

-- The pushed tables (the server half's handlers.Tables) name a property; the wording itself is
-- dc_tooltip.lua's. The ids and names are the ones dc_affix_pool really carries.
local TABLES = {names = {str = "Strength", int = "Intelligence", chc = "Critical Hit Chance",
    cdr = "Reduces cooldown of all skills", lph = "Life per Hit", sockets = "Sockets",
    wpnlit = "Lightning Damage", gf = "Gold Find", mainstat = "Strength"},
    percent = {chc = true, gf = true, str = false, cdr = true, sockets = false}}
-- A property worded the way the item tooltip words it: dc_tooltip.lua's DCAFFIXLINE, loaded for real
-- below and called with the fields the window hands it for these records. The window must read the
-- same as the tooltip, whichever wording the shipped tooltip has.
local function worded(id, value)
    return DCAFFIXLINE({id = id, name = TABLES.names[id], percent = TABLES.percent[id], value = value, value2 = 0,
        min = 0, max = 0, fixed = false, rerolled = false})
end
local ITEM, ENTRY = 87, 100000
local SHOW = {gold = "1234567", materials = {}, managed = true, kind = "Mystic",
    items = {{guid = ITEM, entry = ENTRY, name = "Test Ring", rarity = "rare", bag = 0, slot = 1}}}
-- The L lines in the order the server sends them (the tooltip's order): the main stat, critical hit
-- chance, the one socket line and a line with gems in it (state 2, so it cannot be replaced).
local LINES = "L|" .. ITEM .. "|1:str:primary:0:877:0:0:0:0:0|2:chc:secondary:0:6:0:0:0:0:0"
    .. "|3:sockets:socket:0:3:0:0:0:0:0|4:cdr:primary:2:9:0:0:0:0:0"
local MATERIALS = {"T|" .. ITEM .. "|102002|3|99610|1|Arcane Dust", "T|" .. ITEM .. "|102003|3|100031|1|Veiled Crystal"}
local PRICE = "P|" .. ITEM .. "|2500|1"
----------------------------------------------------------------------------------------------------
-- The harness: the request goes out on Mystic.Send's own wire, the reply comes back the way the
-- server sends it - one DCARTISAN addon whisper per record, through the CHAT_MSG_ADDON listener the
-- window registered.
----------------------------------------------------------------------------------------------------
local requests = {}
local realSend = Mystic.Send
Mystic.Send = function(verb, first, second)
    requests[#requests + 1] = {verb, first, second}
    return realSend(verb, first, second)
end
local function click(button) button.scripts.OnClick(button) end
local function tick(delta)
    local frame = ui.frame
    frame.scripts.OnUpdate(frame, delta)
end
local function shownRows()
    local out = {}
    for index = 1, 12 do
        if ui.rows[index] and ui.rows[index].shown then out[#out + 1] = ui.rows[index] end
    end
    return out
end
local function rowTexts()
    local out = {}
    for _, row in ipairs(shownRows()) do out[#out + 1] = row.label.text end
    return out
end
local function lastBody()
    return sent[#sent] and sent[#sent].body
end
local function bodyCount(body)
    local count = 0
    for _, message in ipairs(sent) do if message.body == body then count = count + 1 end end
    return count
end
local function reply(...)
    for _, frame in ipairs(frames) do
        if frame.events.CHAT_MSG_ADDON then
            for _, body in ipairs({...}) do
                frame.scripts.OnEvent(frame, "CHAT_MSG_ADDON", "DCARTISAN", body, "WHISPER", "Tester")
            end
            return
        end
    end
    error("the window listens for no reply")
end
-- A reply only reaches the window while its request is in flight (records carry no request id), so
-- every batch of records below is preceded by the drag that asks the server to place the item.
local function placeItem()
    sent = {}
    PickupContainerItem(0, 1)
    cursorHeld = true
    ui.tray.scripts.OnReceiveDrag(ui.tray)
    assert(lastBody() == "place\t" .. ITEM and sent[#sent].prefix == "DCARTISAN"
        and sent[#sent].distribution == "WHISPER" and sent[#sent].target == "Tester",
        "the drop sends the item's guid on the bridge, got " .. tostring(lastBody()))
    sent = {}
end
local function place(...)
    placeItem()
    reply("R|place|" .. ITEM, ...)
end
local function coloursEqual(a, b)
    if not a or not b then return false end
    for index = 1, 4 do if (a[index] or 1) ~= (b[index] or 1) then return false end end
    return true
end


----------------------------------------------------------------------------------------------------
-- The mockup's sizes
----------------------------------------------------------------------------------------------------
-- Square art: a texture anchored inside its frame by the same inset on every side is as square as the
-- frame, and the frame's own width and height are compared.
local function squareIcon(owner)
    local p = owner.icon.points
    return owner:GetWidth() == owner:GetHeight() and #p == 2 and p[1][1] == "TOPLEFT" and p[2][1] == "BOTTOMRIGHT"
        and p[1][2] == -p[2][2] and p[1][3] == -p[2][3] and p[1][2] == -p[1][3]
end
assert(ui.frame:GetWidth() == 560 and ui.frame:GetHeight() == 560, "the window is the Blacksmith's 560x560")
local titleText, subtitleText
for _, f in ipairs(frames) do
    if f.kind == "FontString" and f.parent == ui.frame and f.text == "Mystic" then titleText = f end
    if f.kind == "FontString" and f.parent == ui.frame and f.text == "ENCHANT" then subtitleText = f end
end
assert(titleText and titleText.template == "GameFontNormalLarge", "the gold title reads Mystic")
assert(subtitleText and coloursEqual(subtitleText.textColor, DCUI.GREY), "over the small-caps grey subtitle ENCHANT")
for index, tab in ipairs(ui.tabs) do
    local point = tab.points[1]
    assert(tab:GetWidth() == 48 and squareIcon(tab), "tab " .. index .. " is a square 48 px icon, as the Blacksmith's")
    assert(point[1] == "TOPLEFT" and point[2] == ui.frame and point[3] == "TOPRIGHT" and point[4] == -2
        and point[5] == -70 - (index - 1) * 56, "tab " .. index .. " hangs on the right edge where the Blacksmith's does")
end
assert(squareIcon(ui.slot) and ui.slot:GetWidth() == 54, "the item slot and its icon are square")
assert(ui.action.template == "UIPanelButtonTemplate", "the button is the stock red one")
assert(coloursEqual(ui.tabs[1].borderColor, DCUI.TAB_ACTIVE) and coloursEqual(ui.tabs[2].borderColor, DCUI.TAB_IDLE),
    "Enchant is the active tab and Transmogrify the idle one")
local QUESTION_ICON = "Interface\\Icons\\INV_Misc_QuestionMark"
-- A missing-texture `?` drawn anywhere in the window, shown or not.
local function questionIcons()
    local count = 0
    for _, f in ipairs(frames) do if f.texture == QUESTION_ICON and f.shown then count = count + 1 end end
    return count
end

----------------------------------------------------------------------------------------------------
-- Step 1: the show payload opens the window, and the pushed tables name a property
----------------------------------------------------------------------------------------------------
Show(nil, SHOW)
assert(#asked == 1 and asked[1][2] == "Tables", "the window asks the server for the naming tables once")
Tables(nil, TABLES)
assert(ui.listTitle.text == "Place an Item to Replace a Property", "step 1's title, got " .. tostring(ui.listTitle.text))
assert(ui.intro.shown, "step 1 shows the intro")
assert(#shownRows() == 0, "step 1 shows no property rows")
assert(ui.action.text == "Place an Item to Replace a Property" and ui.action.disabled,
    "step 1's button is the ask, greyed: " .. tostring(ui.action.text))
assert(ui.itemHint.shown and ui.short.text == "", "step 1 says how an item goes in, and nothing is short")
assert(not ui.chestHeading.shown and not ui.materials, "step 1 asks for no materials")
assert(not ui.slot.icon.shown, "step 1's slot is empty")
assert(ui.goldValue.text == "Your gold: 1,234,567", "the gold line is the Show payload's own figure, got " .. tostring(ui.goldValue.text))
assert(ui.frame.shown, "the Show payload opens the window")

----------------------------------------------------------------------------------------------------
-- Placing: a drag from the bags, and the reply's records drawn
----------------------------------------------------------------------------------------------------
requests, sent = {}, {}
placeItem()
assert(not cursorHeld, "the placed item leaves the cursor")
requests = {}
reply("R|place|" .. ITEM, "N|" .. ITEM .. "|" .. ENTRY .. "|rare|0|0|1|0", LINES, PRICE, MATERIALS[1], MATERIALS[2],
    "E|place")
assert(ui.listTitle.text == "Select a Property to Replace", "step 2's title, got " .. tostring(ui.listTitle.text))
assert(not ui.intro.shown and not ui.lockedNote.shown, "no intro once an item is in")
assert(ui.slot.icon.shown and ui.slot.icon.texture == "icon:" .. ENTRY, "the slot draws the item's icon")
assert(ui.itemName.text == "Test Ring" and coloursEqual(ui.itemName.textColor, DCRARITY.rare) and not ui.itemHint.shown,
    "the item's name in its rarity colour replaces the hint")
-- The rows read exactly as the item tooltip words the same affix, and the state-2 line says why.
assert(table.concat(rowTexts(), "\n") ==
    "+877 Strength\n" .. worded("chc", 6) .. "\nSockets (3)\n" .. worded("cdr", 9) .. " - Remove the socketed gems first.",
    "the rows are the server's lines, worded by the tooltip's formatter:\n" .. table.concat(rowTexts(), "\n"))
local rows = shownRows()
assert(rows[1].help.shown and rows[2].help.shown, "a replaceable property carries the ?")
assert(rows[1].help.mark.text == "?" and coloursEqual(rows[1].label.textColor, {.49, .49, 1}),
    "the ? is a drawn help mark, and a line is in the affix blue")
assert(questionIcons() == 0, "no missing-texture question mark is drawn")
assert(not rows[4].help.shown, "a line the server marks 2 carries no ?")
assert(coloursEqual(rows[4].label.textColor, DCUI.GREY), "and it is greyed")
assert(not rows[1].mark.shown, "nothing is picked yet")
assert(ui.action.text == "Select a Property to Replace" and ui.action.disabled,
    "step 2's button asks for a property and is greyed")
assert(ui.chestHeading.shown, "step 2 shows the required materials")
assert(ui.materials[1].count.text == "99,610 / 3", "the count is have / need, grouped, got " .. tostring(ui.materials[1].count.text))
assert(ui.materials[1].dcName == "Arcane Dust" and ui.materials[1].label.text == "Arcane Dust",
    "a material is named by the server")
assert(ui.goldValue.text == "Your gold: 1,234,567", "the balance is grouped by the shared formatter")

-- A click on a line the server says cannot be replaced selects nothing.
click(rows[4])
assert(ui.action.text == "Select a Property to Replace" and ui.action.disabled,
    "a dead line cannot be picked")

----------------------------------------------------------------------------------------------------
-- The ? asks the server once per line and shows what comes back
----------------------------------------------------------------------------------------------------
requests, sent = {}, {}
rows[2].help.scripts.OnEnter(rows[2].help)
assert(#requests == 1 and requests[1][1] == "preview" and requests[1][2] == ITEM and requests[1][3] == 2,
    "the ? asks what that line can become")
assert(lastBody() == "preview\t" .. ITEM .. "\t2", "the preview request's fields, got " .. tostring(lastBody()))
assert(GameTooltip.shown, "the ? popover opens at once")
reply("R|preview|" .. ITEM, "V|" .. ITEM .. "|2|str:primary:700:900:0:0|cdr:primary:6:12:0:0", "E|preview")
assert(GameTooltip.lines[1] == worded("chc", 6), "the popover names the line itself")
assert(GameTooltip.lines[2] == "+[700 - 900] Strength" and GameTooltip.lines[3] == "+[6 - 12]% Reduces cooldown of all skills",
    "and lists what it can become in the tooltip's preview form:\n" .. table.concat(GameTooltip.lines, "\n"))
rows[2].help.scripts.OnEnter(rows[2].help)
assert(#requests == 1 and bodyCount("preview\t" .. ITEM .. "\t2") == 1, "a line's preview is asked for once")
rows[2].help.scripts.OnLeave(rows[2].help)
assert(not GameTooltip.shown, "and the popover closes with the cursor")
-- diablocraft-ipc7: a Primal can only roll the top, so its preview entries are ranges of one value
-- (the server sends min = max) and read as that value, two-part and sockets included.
requests, sent = {}, {}
rows[3].help.scripts.OnEnter(rows[3].help)
local topSeq = requests[1][3]
reply("R|preview|" .. ITEM, "V|" .. ITEM .. "|" .. topSeq .. "|str:primary:900:900:0:0|cdr:primary:12:12:0:0|wpnfir:primary:1199:1199:1490:1490|sockets:socket:3:3:0:0", "E|preview")
local joined = table.concat(GameTooltip.lines, "\n")
assert(GameTooltip.lines[2] == "+900 Strength" and GameTooltip.lines[3] == "+12% Reduces cooldown of all skills"
    and GameTooltip.lines[4]:find("+1199-1490", 1, true) and GameTooltip.lines[5] == "Sockets (3)",
    "a Primal's preview shows the top value, not a range:\n" .. joined)
assert(not joined:find("[", 1, true), "no bracketed range in a Primal's preview:\n" .. joined)
rows[3].help.scripts.OnLeave(rows[3].help)

----------------------------------------------------------------------------------------------------
-- Step 3 and 4: a picked line, the cost, and the bind warning on the first enchant
----------------------------------------------------------------------------------------------------
click(rows[2])
assert(ui.listTitle.text == "Select a Property to Replace", "step 3 keeps step 2's title")
assert(coloursEqual(rows[2].label.textColor, {1, 1, 1}), "the picked row's line is white")
assert(rows[2].mark.shown and not rows[1].mark.shown, "only the picked row carries the selection mark")
assert(ui.action.text == "Replace Property: 2,500 gold", "step 3's button is the server's cost, got " .. tostring(ui.action.text))
assert(ui.action.disabled == false and ui.short.text == "", "step 3's button is live")
requests = {}
click(ui.action)
assert(ui.overlay.shown, "the first enchant asks before it binds (bind 1)")
assert(#requests == 0, "nothing is sent while the warning waits")
local warningTitle, warningBody
for _, frame in ipairs(frames) do
    if frame.kind == "FontString" and frame.text == "WARNING!" then warningTitle = frame end
    if frame.kind == "FontString" and frame.text and frame.text:find("Enchanting an item will bind it to your account", 1, true) then warningBody = frame end
end
assert(warningTitle and warningTitle.shown ~= false, "the warning is headed WARNING!")
assert(warningBody, "the warning carries the mockup's line")
click(ui.warnCancel)
assert(not ui.overlay.shown and #requests == 0, "Cancel closes the warning and sends nothing")
click(ui.action)
assert(ui.overlay.shown, "the warning asks again after a Cancel")
click(ui.warnOK)
assert(#requests == 1 and requests[1][1] == "roll" and requests[1][2] == ITEM and requests[1][3] == 2,
    "OK sends the picked line to the roll verb")
assert(lastBody() == "roll\t" .. ITEM .. "\t2", "the roll request's fields, got " .. tostring(lastBody()))

-- The server's own affordability greys the button; a jewellery roll carries no price and no coin.
requests = {}
reply("X|Stand next to the artisan.")
assert(UIErrorsFrame.lines[#UIErrorsFrame.lines] == "Stand next to the artisan.",
    "a refusal shows the server's own text")
place("N|" .. ITEM .. "|" .. ENTRY .. "|rare|0|0|0|0", LINES, "P|" .. ITEM .. "|2500|0", MATERIALS[1], MATERIALS[2],
    "E|place")
assert(ui.action.disabled, "a cost the server calls unaffordable greys the button")
assert(ui.short.text == "Not enough account gold.", "and says so, got " .. tostring(ui.short.text))
place("N|" .. ITEM .. "|" .. ENTRY .. "|rare|0|0|0|0", LINES, "P|" .. ITEM .. "|0|1",
    "T|" .. ITEM .. "|102002|3|99610|1|Arcane Dust", "E|place")
assert(ui.action.text == "Replace Property", "a jewellery roll's button carries no price, got " .. tostring(ui.action.text))
assert(ui.action.disabled == false, "but it is live")
place("N|" .. ITEM .. "|" .. ENTRY .. "|rare|0|0|0|0", LINES, PRICE,
    "T|" .. ITEM .. "|102002|3|99610|1|Arcane Dust", "T|" .. ITEM .. "|102003|3|2|0|Veiled Crystal", "E|place")
assert(ui.action.disabled, "a material the server says is short greys the button too")
assert(ui.materials[2].count.text == "2 / 3", "a short count reads the same way, got " .. tostring(ui.materials[2].count.text))
assert(ui.short.text == "Not enough Veiled Crystal: you have 2 of 3.", "and the grey button says which, got " .. tostring(ui.short.text))
-- Bound already (bind 0): Replace sends the roll at once, with no warning.
place("N|" .. ITEM .. "|" .. ENTRY .. "|rare|0|0|0|0", LINES, PRICE, MATERIALS[1], MATERIALS[2], "E|place")
requests, sent = {}, {}
click(ui.action)
assert(#requests == 1 and requests[1][1] == "roll" and requests[1][3] == 2 and lastBody() == "roll\t" .. ITEM .. "\t2",
    "an already bound item rolls with no warning, got " .. tostring(lastBody()))

----------------------------------------------------------------------------------------------------
-- Step 5: the paid roll's three choices, one second apart
----------------------------------------------------------------------------------------------------
sent = {}
reply("R|roll|1", "B|1234567", "N|" .. ITEM .. "|" .. ENTRY .. "|rare|0|1|1|1",
    "C|" .. ITEM .. "|1:str:primary:877:0:0:0:0:0|2:cdr:primary:9:0:0:0:0:0|3:lph:primary:13254:0:0:0:0:0",
    "E|roll")
assert(ui.goldValue.text == "Your gold: 1,234,567", "the reply's balance record updates the gold line")
assert(ui.listTitle.text == "Select Replacement Property", "step 5's title, got " .. tostring(ui.listTitle.text))
assert(#shownRows() == 1, "the first choice (the current value) shows at once, got " .. #shownRows())
assert(shownRows()[1].label.text == "+877 Strength", "the current line is the first choice")
tick(0.5)
assert(#shownRows() == 1, "the second waits its second")
assert(ui.chooseNote.shown, "step 5 shows the choose note")
assert(not ui.chestHeading.shown, "step 5 asks for no materials")
assert(ui.action.text == "Select Property" and ui.action.disabled, "Select Property is greyed until a choice is clicked")
tick(0.5)
assert(#shownRows() == 2, "one second in, two choices")
tick(1)
assert(#shownRows() == 3, "two seconds in, three choices")
tick(1)
assert(#shownRows() == 3, "three seconds in, three choices")
assert(table.concat(rowTexts(), "\n") == "+877 Strength\n" .. worded("cdr", 9) .. "\n" .. worded("lph", 13254),
    "the choices are the server's own lines:\n" .. table.concat(rowTexts(), "\n"))
assert(not shownRows()[1].help.shown, "a choice carries no ?")
click(shownRows()[2])
assert(shownRows()[2].mark.shown, "the clicked choice is picked")
assert(ui.action.disabled == false, "Select Property is live once a choice is clicked")
requests = {}
click(ui.action)
assert(#requests == 1 and requests[1][1] == "pick" and requests[1][3] == 2,
    "the picked choice goes to the pick verb")
assert(lastBody() == "pick\t" .. ITEM .. "\t2", "the pick request's fields, got " .. tostring(lastBody()))

----------------------------------------------------------------------------------------------------
-- Step 6: the property is locked, and a refusal keeps the window as it was
----------------------------------------------------------------------------------------------------
reply("R|pick|0", "N|" .. ITEM .. "|" .. ENTRY .. "|rare|1|1|1|0", "L|" .. ITEM .. "|2:cdr:primary:1:9:0:0:0:0:0",
    "P|" .. ITEM .. "|4200|1", MATERIALS[1], MATERIALS[2], "E|pick")
assert(ui.listTitle.text == "Replace a Previously Enchanted Property", "step 6's title, got " .. tostring(ui.listTitle.text))
assert(ui.lockedNote.shown and not ui.intro.shown, "step 6 says the property is locked")
assert(#shownRows() == 1, "only the locked line is offered")
assert(shownRows()[1].mark.shown, "the locked line is the one that can be rerolled")
assert(shownRows()[1].help.shown, "and it carries the ?")
assert(ui.chestHeading.shown, "step 6 still asks for the materials")
assert(ui.action.text == "Replace Property: 4,200 gold" and ui.action.disabled == false, "step 6's button is live")
requests = {}
click(ui.action)
assert(requests[1][1] == "roll" and requests[1][3] == 2, "and the locked line rolls again")
reply("X|Only the previously enchanted property can be replaced.")
assert(UIErrorsFrame.lines[#UIErrorsFrame.lines] == "Only the previously enchanted property can be replaced.",
    "the refusal's text is shown as is")
assert(ui.listTitle.text == "Replace a Previously Enchanted Property" and #shownRows() == 1,
    "and the window keeps what it was showing")

----------------------------------------------------------------------------------------------------
-- One request at a time, and a reply that never comes
----------------------------------------------------------------------------------------------------
requests, sent = {}, {}
rows = shownRows()
rows[1].help.scripts.OnEnter(rows[1].help)
assert(bodyCount("preview\t" .. ITEM .. "\t2") == 1, "the hover asks what the locked line can become")
click(ui.action)
assert(requests[#requests][1] == "roll" and bodyCount("roll\t" .. ITEM .. "\t2") == 0,
    "a roll while a preview is in flight waits for its E")
reply("R|preview|" .. ITEM, "V|" .. ITEM .. "|2|cdr:primary:6:12:0:0", "E|preview")
assert(bodyCount("roll\t" .. ITEM .. "\t2") == 1, "and goes out the moment the first reply is complete")
reply("R|roll|1", "N|" .. ITEM .. "|" .. ENTRY .. "|rare|1|2|0|1",
    "C|" .. ITEM .. "|1:chc:secondary:6:0:0:0:0:0|2:cdr:primary:14:0:0:0:0:0|3:lph:primary:13254:0:0:0:0:0", "E|roll")
assert(ui.listTitle.text == "Select Replacement Property", "the second roll's choices arrive at step 5")
assert(#shownRows() == 1, "and start their own stagger, the first at once")
assert(not shownRows()[1].mark.shown and ui.action.disabled, "nothing carries over from the roll before")
sent = {}
click(shownRows()[1])
click(ui.action)
assert(bodyCount("pick\t" .. ITEM .. "\t1") == 1, "the pick is in flight")
PickupContainerItem(0, 1)
cursorHeld = true
ui.tray.scripts.OnReceiveDrag(ui.tray)
assert(bodyCount("place\t" .. ITEM) == 0, "the drop behind it waits")
clock = clock + 10
tick(0.5)
clock = clock - 10
assert(bodyCount("place\t" .. ITEM) == 1, "a request whose reply never comes stops blocking the next one")

----------------------------------------------------------------------------------------------------
-- The bags: a plain right-click loads an item instead of equipping it
----------------------------------------------------------------------------------------------------
local bagButton = CreateFrame("Button", "ContainerFrame1Item1", CreateFrame("Frame"))
bagButton:GetParent():SetID(0)
bagButton:SetID(1)
_G.ContainerFrame1Item1 = bagButton
Mystic.ScanBagButtons()
assert(bagButton.scripts.PreClick and bagButton.scripts.PostClick, "the claim hooks the bag button")
Show(nil, SHOW)
sent = {}
bagButton.scripts.PreClick(bagButton, "RightButton")
assert(bodyCount("place\t" .. ITEM) == 1, "a plain right-click in the bags places the item")
assert(bagButton.id == 2, "and the stock click is pointed at the bag's first empty slot, got " .. tostring(bagButton.id))
bagButton.scripts.PostClick(bagButton)
assert(bagButton.id == 1, "the button's own id comes back after the click")
reply("R|place|" .. ITEM, "N|" .. ITEM .. "|" .. ENTRY .. "|rare|0|0|0|0", LINES, PRICE, MATERIALS[1], MATERIALS[2],
    "E|place")
sent = {}
combat = true
bagButton.scripts.PreClick(bagButton, "RightButton")
assert(#sent == 0, "in combat the right-click stays the stock one")
combat = false
cursorHeld = true
bagButton.scripts.PreClick(bagButton, "RightButton")
assert(#sent == 0, "and so does a click with an item already on the cursor")
cursorHeld = false
bagButton.scripts.PreClick(bagButton, "LeftButton")
assert(#sent == 0, "a left click stays the stock one")
ui.frame:Hide()
bagButton.scripts.PreClick(bagButton, "RightButton")
assert(#sent == 0, "and nothing is claimed while the window is closed")

----------------------------------------------------------------------------------------------------
-- diablocraft-zmkh (the designer's dev check, 2026-10-06): every way in puts the item in - drag or right-click,
-- bags or character sheet - and a refused one never leaves the window stuck.
----------------------------------------------------------------------------------------------------
local HEAD, RING = 88, 89
local SHOW_ALL = {gold = "1234567", materials = {}, managed = true, kind = "Mystic",
    items = {{guid = ITEM, entry = ENTRY, name = "Test Ring", rarity = "rare", bag = 0, slot = 1},
        {guid = HEAD, entry = 2, name = "Test Helm", rarity = "rare", bag = 255, slot = 0},
        {guid = RING, entry = 3, name = "Worn Ring", rarity = "legendary", bag = 255, slot = 10}}}
local function settle()
    -- Ends the request in flight, so the next one goes on the wire at once.
    clock = clock + 10
    tick(0.01)
    clock = clock - 10
end
local function errorsSaid() return UIErrorsFrame.lines[#UIErrorsFrame.lines] end

-- The claim is registered, and is true only while a plain right-click would load an item.
assert(#claims == 1, "the window registers one right-click claim with the Torment sheet")
Show(nil, SHOW_ALL)
assert(claims[1]() == true, "the claim holds while the window is up")
cursorHeld = true
assert(claims[1]() == false, "not with an item on the cursor")
cursorHeld = false
combat = true
assert(claims[1]() == false, "not in combat")
combat = false

-- A drag from the character sheet: the sheet's pickup is PickupInventoryItem(inventory id).
Show(nil, SHOW_ALL)
sent = {}
PickupInventoryItem(1)
cursorHeld = true
ui.tray.scripts.OnReceiveDrag(ui.tray)
assert(bodyCount("place\t" .. HEAD) == 1, "a drag from the character sheet places the worn item, got "
    .. tostring(lastBody()))
assert(not cursorHeld, "and the cursor is empty")
settle()

-- A drop the window cannot match puts the item back and says so; the next drag still goes in.
Show(nil, SHOW_ALL)
sent = {}
PickupContainerItem(3, 7)
cursorHeld = true
ui.tray.scripts.OnReceiveDrag(ui.tray)
assert(#sent == 0, "an item the index does not hold sends nothing")
assert(not cursorHeld, "and leaves the cursor empty, so nothing is stuck on it")
assert(errorsSaid() == "The Mystic cannot enchant that item.", "and says why, got " .. tostring(errorsSaid()))
PickupContainerItem(0, 1)
cursorHeld = true
ui.tray.scripts.OnReceiveDrag(ui.tray)
assert(bodyCount("place\t" .. ITEM) == 1, "the next drag from the bags goes in")
settle()
-- A drop with no pickup seen (the cursor's origin unknown) never reuses the last pickup's slot.
sent = {}
cursorHeld = true
ui.tray.scripts.OnReceiveDrag(ui.tray)
assert(#sent == 0 and not cursorHeld, "an unknown origin places nothing and empties the cursor")

-- A right-click on the stock character sheet: UseInventoryItem is pointed at an empty worn slot.
local stockHead = CreateFrame("Button", "CharacterHeadSlot", CreateFrame("Frame"))
stockHead:SetID(1)
_G.CharacterHeadSlot = stockHead
-- The Torment sheet's slot: it reads its own equipSlot, so it is left alone and yields to the claim.
local tormentRing = CreateFrame("Button", "DiablocraftGearSlot10", CreateFrame("Frame"))
tormentRing.equipSlot = 10
_G.DiablocraftGearSlot10 = tormentRing
Mystic.ScanBagButtons()
assert(stockHead.scripts.PreClick and tormentRing.scripts.PreClick, "the claim hooks both character sheets")
Show(nil, SHOW_ALL)
sent = {}
stockHead.scripts.PreClick(stockHead, "RightButton")
assert(bodyCount("place\t" .. HEAD) == 1, "a right-click on the stock sheet places the worn item")
assert(stockHead.id == 2, "and its stock click is pointed at an empty worn slot, got " .. tostring(stockHead.id))
stockHead.scripts.PostClick(stockHead)
assert(stockHead.id == 1, "the slot's own id comes back after the click")
settle()
sent = {}
tormentRing.scripts.PreClick(tormentRing, "RightButton")
assert(bodyCount("place\t" .. RING) == 1, "a right-click on the Torment sheet places the worn item")
assert(tormentRing.id == nil and claims[1](), "its id is untouched; the claim keeps the sheet's unequip off")
tormentRing.scripts.PostClick(tormentRing)
settle()

-- A right-click in a full bag: the stock click is pointed past the bag's last slot, never left to equip.
local realLink = GetContainerItemLink
function GetContainerItemLink() return "item:1" end
Show(nil, SHOW_ALL)
sent = {}
bagButton.scripts.PreClick(bagButton, "RightButton")
assert(bodyCount("place\t" .. ITEM) == 1, "a right-click in a full bag places the item")
assert(bagButton.id == 5, "and the stock click is pointed past the bag's last slot, got " .. tostring(bagButton.id))
bagButton.scripts.PostClick(bagButton)
settle()
-- A right-click on an item the window cannot take is still the window's: said, and not equipped.
bagButton:SetID(3)
sent = {}
bagButton.scripts.PreClick(bagButton, "RightButton")
assert(#sent == 0 and errorsSaid() == "The Mystic cannot enchant that item.", "an item it cannot take is refused in words")
assert(bagButton.id == 5, "and its stock click acts on nothing, got " .. tostring(bagButton.id))
bagButton.scripts.PostClick(bagButton)
bagButton:SetID(1)
GetContainerItemLink = realLink

-- An equip or a bag move while the window is up asks for the index again; the answer renews the index
-- only: the placed item stays, and a window closed meanwhile stays closed.
Show(nil, SHOW_ALL)
place("N|" .. ITEM .. "|" .. ENTRY .. "|rare|0|0|0|0", LINES, PRICE, MATERIALS[1], MATERIALS[2], "E|place")
assert(ui.listTitle.text == "Select a Property to Replace", "an item is in")
asked = {}
local function fire(event)
    for _, f in ipairs(frames) do
        if f.events[event] then f.scripts.OnEvent(f, event) end
    end
end
fire("PLAYER_EQUIPMENT_CHANGED")
tick(0.01)
assert(#asked == 1 and asked[1][1] == "DiablocraftCrafting" and asked[1][2] == "Refresh",
    "a change while the window is up asks Refresh once")
tick(0.01)
assert(#asked == 1, "and only once")
local moved = {gold = "1234567", materials = {}, managed = true, kind = "Mystic", refresh = true,
    items = {{guid = HEAD, entry = 2, name = "Test Helm", rarity = "rare", bag = 2, slot = 9}}}
Show(nil, moved)
assert(ui.listTitle.text == "Select a Property to Replace" and ui.frame.shown, "the refresh keeps the placed item")
sent = {}
PickupContainerItem(2, 9)
cursorHeld = true
ui.tray.scripts.OnReceiveDrag(ui.tray)
assert(bodyCount("place\t" .. HEAD) == 1, "and the moved item is found where it now is")
settle()
ui.frame:Hide()
asked = {}
fire("BAG_UPDATE")
tick(0.01)
assert(#asked == 0, "a change while the window is closed asks nothing")
Show(nil, moved)
assert(not ui.frame.shown, "a late refresh never reopens the window")
_G.ContainerFrame1Item1, _G.CharacterHeadSlot, _G.DiablocraftGearSlot10 = nil, nil, nil

----------------------------------------------------------------------------------------------------
-- Nothing goes on the wire but the contract's verbs
----------------------------------------------------------------------------------------------------
Show(nil, SHOW)
sent = {}
click(ui.tabs[2])
assert(#sent == 1 and sent[1].prefix == "DCARTISAN" and sent[1].body == "transmog"
    and sent[1].distribution == "WHISPER" and sent[1].target == "Tester",
    "the Transmogrify tab keeps today's fixed bridge verb, got " .. tostring(lastBody()))
assert(not ui.frame.shown, "and it closes the window")
local VERBS = {place = true, preview = true, roll = true, pick = true}
for _, message in ipairs(sent) do
    local verb = message.body:match("^(%a+)")
    assert(VERBS[verb] or verb == "transmog", "an unlisted verb went on the wire: " .. message.body)
end
assert(not Mystic.Preview, "the static preview and its /dcmystic are gone")

-- The designer's round 3 item: a legendary ring pays one Imperial gem of any colour, and the server lists it as
-- entry 0 when none is held (contract section 3). It has no icon, so it is left out until a property is
-- picked; picked, it shows as its name and red count over an empty slot, and the button says why it is
-- grey. Never a missing-texture box.
local GEM = "T|" .. ITEM .. "|0|1|0|0|Imperial gem of any colour"
Show(nil, SHOW)
sent, pending = {}, nil
place("N|" .. ITEM .. "|" .. ENTRY .. "|legendary|0|0|0|0", LINES, "P|" .. ITEM .. "|0|1", GEM, "E|place")
assert(ui.action.text == "Select a Property to Replace" and not ui.materials[1].shown and not ui.materials[1].label.shown
    and not ui.materials[2].shown, "before a property is picked, a material with no icon shows nothing")
assert(questionIcons() == 0, "and no missing-texture question mark is drawn")
click(shownRows()[2])
assert(ui.materials[1].shown and ui.materials[1].label.text == "Imperial gem of any colour"
    and not ui.materials[1].icon.shown and ui.materials[1].count.text == "0 / 1"
    and coloursEqual(ui.materials[1].count.textColor, DCUI.RED), "picked, the gem shows by name and red count over an empty slot")
assert(ui.action.disabled and ui.short.text == "Not enough Imperial gem of any colour: you have 0 of 1.",
    "the button stays grey and says why, got " .. tostring(ui.short.text))
assert(questionIcons() == 0, "still no missing-texture question mark")

-- Walking away: the server's range watcher sends Close, and the window goes.
Show(nil, SHOW)
assert(ui.frame.shown, "the window is open")
handlersByChannel.DiablocraftCrafting.Close()
assert(not ui.frame.shown, "the server's Close (the player walked away) hides the window")

----------------------------------------------------------------------------------------------------
-- The server half (diablocraft-zmkh): the Show index lists the worn items too, in the numbering the
-- sheet's pickup gives (255, 0..18), and the answer to Refresh is marked so it renews only the index.
----------------------------------------------------------------------------------------------------
do
    local shown, gossip, serverHandlers = {}, nil, nil
    local function item(guid) return {GetEntry = function() return 100 end, GetGUIDLow = function() return guid end,
        GetName = function() return "item " .. guid end} end
    local carried = {["255:0"] = item(501), ["255:18"] = item(502), ["255:23"] = item(503), ["19:0"] = item(504)}
    local player = {GetGUIDLow = function() return 7 end, GossipComplete = function() end,
        GetItemByPos = function(_, bag, slot) return carried[bag .. ":" .. slot] end,
        RegisterEvent = function() return 1 end, RemoveEventById = function() end}
    function WorldDBQuery() return nil end
    function CharDBQuery() return {GetString = function() return "rare" end} end
    function RegisterCreatureGossipEvent(entry, _, fn) if entry == 910001 then gossip = fn end end
    function RegisterPlayerEvent() end
    DCAccount = {MATERIALS = {}, Snapshot = function() return {gold = "5", materials = {}, managed = true} end}
    DCThrottle = {Allow = function() return true end}
    DCTunables = {Get = function() return 10 end}
    AIO = {AddAddon = function() return true end,
        AddHandlers = function(_, handlers) serverHandlers = handlers return handlers end,
        Handle = function(_, _, name, payload) if name == "Show" then shown[#shown + 1] = payload end end}
    dofile("mod-diablocraft/lua/aio/dc_aio_range.lua")
    dofile(WINDOW_SOURCE)
    gossip(nil, player, {GetEntry = function() return 910001 end})
    local at = {}
    for _, entry in ipairs(shown[1].items) do at[entry.bag .. ":" .. entry.slot] = entry.guid end
    assert(at["255:0"] == 501 and at["255:18"] == 502, "the Show index lists the worn items as 255 and 0..18")
    assert(at["0:1"] == 503 and at["1:1"] == 504, "and the bag items as before")
    assert(not shown[1].refresh, "the gossip's Show opens the window afresh")
    serverHandlers.Refresh(player)
    assert(shown[2] and shown[2].refresh == true, "the answer to Refresh is marked refresh")
end

print("PASS Mystic window: the Blacksmith's look with square art, the ? as help and no missing texture, the "
    .. "grey button's reason, the walk-away Close, the six steps drawn from the bridge's records, the "
    .. "tooltip's own wording, the four verbs and their bounds, one request at a time, the drag and "
    .. "the right-click claim, the ? preview, the one-second choices and a refusal's text")
