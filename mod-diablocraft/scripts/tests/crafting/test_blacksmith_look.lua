-- luacheck: ignore 111 112 113 121 122 431
-- diablocraft-blacksmith-look: the Blacksmith window must look exactly like the Jeweler's.
--
-- Both windows are built here against one 3.3.5a frame API double and every shared visual
-- property is compared field by field: the window's position and backdrop, the title and
-- subtitle, the tab borders, the list rows (height, font, indent, selection mark, hover),
-- the search and quantity boxes, the detail pane and name, the material line, the cost
-- font, the button row, the cast bar and the gold line. If any one of them differs the
-- assertion names it, so the drift the designer saw on Nightly 57 cannot come back.
--
-- It also pins the rules the briefs add: row colour is the item's rarity whether the row is
-- makeable or not, the first recipe is selected on open, Create/Create All are greyed out
-- while the selected recipe cannot be made, no flat backdrop is left without a colour
-- (the four white pieces), and the material count is a second line under the material's name
-- (never on the icon), grouped in threes and red when the stock is short (diablocraft-materials-count).
--
-- scripts/tests/crafting/test_blacksmith_look_lua.py runs this file again on a copy of dc_blacksmith.lua
-- with one rule's shared property removed, and requires every run to fail.
local UI_SOURCE = os.getenv("DC_UI_LUA") or "mod-diablocraft/lua/aio/dc_aio_ui.lua"
local JEWELER_SOURCE = os.getenv("DC_JEWELER_LUA") or "mod-diablocraft/lua/aio/dc_jeweler.lua"
local BLACKSMITH_SOURCE = os.getenv("DC_BLACKSMITH_LUA") or "mod-diablocraft/lua/aio/dc_blacksmith.lua"

----------------------------------------------------------------------------------------------------
-- The stub client
----------------------------------------------------------------------------------------------------
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
local sent, aio = {}, {}
Mock.setScreen(1024, 768)
StaticPopup_Show = function(name) return {name = name, data = nil} end
StaticPopup_Hide = function() end
function UnitName() return "Tester" end
function GetRealmName() return "Diablocraft" end
function GetTime() return 0 end
function GetUnitSpeed() return 0 end
function UnitAffectingCombat() return false end
function InCombatLockdown() return false end
function UnitIsDeadOrGhost() return false end
function GetItemIcon(entry) return "icon:" .. tostring(entry) end
function GetItemInfo() return nil end
function GetCursorInfo() return nil end
function ClearCursor() end
function GetCursorPosition() return 0, 0 end
function IsMouseButtonDown() return false end
function GetMouseFocus() return nil end
function GetContainerNumSlots() return 0 end
function GetContainerNumFreeSlots() return 0 end
function GetContainerItemLink() return nil end
function GetInventoryItemLink() return nil end
function GetContainerNumFreeSlots() return 0 end
function IsShiftKeyDown() return false end
function IsControlKeyDown() return false end
function IsAltKeyDown() return false end
function PickupContainerItem() end
function PickupInventoryItem() end
function SocketContainerItem() end
function SocketInventoryItem() end
CreateFrame("Frame", "ItemSocketingFrame")
function HideUIPanel() end
function SendAddonMessage(prefix, body, distribution, target)
    sent[#sent + 1] = {prefix = prefix, body = body, distribution = distribution, target = target}
end
NUM_CONTAINER_FRAMES, MAX_CONTAINER_ITEMS = 13, 36
-- The real formatter, doubled faithfully: groups in threes, so 100002 reads "100,002" in a
-- count. Both windows call Diablocraft.Econ.Gold for the material line when the addon is present.
-- Torment/Economy.lua digits() refuses any string holding a non-digit as "0", so the mock must
-- refuse the same way: a balance formatted twice ("100,002") the client really shows as "0"
-- would otherwise pass (diablocraft-materials-count regression, dc_jeweler.lua).
local function group(v)
    local s = tostring(v or "")
    if s == "" or s:find("%D") then return "0" end
    s = s:gsub("^0+(%d)", "%1")
    local n = 1
    while n > 0 do s, n = s:gsub("^(%d+)(%d%d%d)", "%1,%2") end
    return s
end
Diablocraft = {Econ = {Gold = group, OnChange = function() end,
    MATERIALS = {}}, ClaimRightClick = function() end}
local handlersByChannel = {}
AIO = {
    AddAddon = function() return false end,
    AddHandlers = function(channel, table_) handlersByChannel[channel] = table_; return table_ end,
    Handle = function(...) aio[#aio + 1] = {...} end,
}

----------------------------------------------------------------------------------------------------
-- Load the module and both windows
----------------------------------------------------------------------------------------------------
dofile(UI_SOURCE)
dofile(JEWELER_SOURCE)
dofile(BLACKSMITH_SOURCE)
assert(DCUI and DCJeweler and DCJeweler.ui and DCBlacksmith and DCBlacksmith.ui, "both windows and the shared module must load")

-- Diablo rarity colours as the windows use them (a row keeps its own whatever its state).
local TINT = {set = {.1, 1, .1}, legendary = {1, .5, 0}, rare = {1, 1, 0}, magic = {.3, .6, 1}, normal = {1, 1, 1}}

-- The Jeweler: one recipe that cannot be made (gems short) exercises the greyed buttons.
handlersByChannel.DiablocraftJeweler.Tables(nil, {gems = {[6001] = "Amethyst"}, effects = {}})
local EMPTY_ITEMS = {}
handlersByChannel.DiablocraftJeweler.Show(nil, {
    items = EMPTY_ITEMS, gems = EMPTY_ITEMS,
    recipes = {{id = 6001, inputEntry = 6001, inputCount = 2, gold = 0, deathsBreath = 30, name = "Amethyst",
        inputName = "Amethyst", colour = "Amethyst", tier = "", rank = 1, have = 0}},
    balance = {gold = "0", deathsBreath = "100002"},
})
-- The Blacksmith: one recipe per rarity, none makeable (materials and gold short). Every recipe
-- carries one material the tester has in bulk (100,002 of 30: gold) and one they are short of
-- (0 of 500,000: red), so whichever recipe is selected exercises both full count lines.
local function recipe(id, rarity, enabled)
    return {id = id, entry = 100000 + id, name = rarity .. " recipe " .. id, category = "Sword", page = "weapons",
        rarity = rarity, required = 20, level = 20, gold = "10", enabled = enabled,
        reason = "Bounty materials are not available yet.", usableBy = "",
        materials = {{entry = 102001, amount = 30, name = "Reusable Parts"},
            {entry = 102002, amount = 500000, name = "Arcane Dust"}}}
end
handlersByChannel.DiablocraftBlacksmith.Show(nil, {title = "Blacksmith", playerLevel = 70, class = "barbarian",
    gold = "0", materials = {[102001] = "100002"}, maxCount = 16, castSeconds = 2, items = {},
    recipes = {recipe(1, "legendary", false), recipe(2, "legendary", true), recipe(3, "set", false),
        recipe(4, "set", true), recipe(5, "rare", true)}})

----------------------------------------------------------------------------------------------------
-- Extractors: every shared visual property, as plain data
----------------------------------------------------------------------------------------------------
local function normalise(points)
    local out = {}
    for _, point in ipairs(points) do
        local copy = {}
        for index, value in ipairs(point) do copy[index] = type(value) == "table" and "frame" or value end
        out[#out + 1] = copy
    end
    return out
end
local function dump(value, seen)
    if type(value) ~= "table" then return tostring(value) end
    seen = seen or {}
    if seen[value] then return "<cycle>" end
    seen[value] = true
    local keys = {}
    for key in pairs(value) do keys[#keys + 1] = key end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    local out = {}
    for _, key in ipairs(keys) do out[#out + 1] = tostring(key) .. "=" .. dump(value[key], seen) end
    return "{" .. table.concat(out, ",") .. "}"
end
local function backdropFields(backdrop)
    if not backdrop then return nil end
    return {bgFile = backdrop.bgFile, edgeFile = backdrop.edgeFile, tile = backdrop.tile,
        tileSize = backdrop.tileSize, edgeSize = backdrop.edgeSize, insets = backdrop.insets}
end
-- The absolute TOPLEFT of a frame, from its ancestors' own TOPLEFT points.
local function topLeft(f)
    local x, y, node = 0, 0, f
    while node do
        for _, point in ipairs(node.points or {}) do
            if point[1] == "TOPLEFT" and type(point[2]) == "number" then x, y = x + point[2], y + point[3]; break end
        end
        node = node.parent
    end
    return {x, y}
end
local function findRows(ui)
    local item, head
    for _, f in ipairs(frames) do
        if f.parent == ui.list and f.row then
            if f.row.recipe and not item then item = f end
            if (f.row.head or f.row.category) and not head then head = f end
        end
    end
    return item, head
end
local function indent(row)
    local found
    for _, point in ipairs(row.label.points) do
        if point[1] == "LEFT" and type(point[2]) == "number" then found = point[2] end
    end
    return found
end
local function rowLook(row)
    return {height = row:GetHeight(), labelFont = row.label.template, indent = indent(row),
        mark = row.mark.vertexColor, highlight = row:GetHighlightTexture() and row:GetHighlightTexture().vertexColor}
end
local function materialLook(mat)
    local slotAt, labelAt, countAt = topLeft(mat), topLeft(mat.label), topLeft(mat.count)
    return {size = {mat:GetWidth(), mat:GetHeight()}, backdrop = backdropFields(mat.backdrop), borderColor = mat.borderColor,
        labelFont = mat.label.template, countFont = mat.count.template, labelOffset = labelAt[1] - slotAt[1],
        countOffset = {countAt[1] - labelAt[1], countAt[2] - labelAt[2]}, countClearOfIcon = countAt[1] - slotAt[1] >= mat:GetWidth()}
end
local function buttonLook(button) return {width = button:GetWidth(), height = button:GetHeight(), points = normalise(button.points)} end
local function tabLook(tab) return {size = {tab:GetWidth(), tab:GetHeight()}, points = normalise(tab.points), backdrop = backdropFields(tab.backdrop), borderColor = tab.borderColor} end
-- A frame that a pre-shared-look file may not export at all: nil compares as nil and fails.
local function textLook(f) return f and {font = f.template, points = normalise(f.points), justify = f.justify} or nil end

local function collect(kind, ui)
    local item, head = findRows(ui)
    assert(item and head, kind .. ": a list row was not drawn (item=" .. tostring(item) .. ", head=" .. tostring(head) .. ")")
    local material = ui.detail.reagents[1]
    local create, createAll, up, down, search, qty
    if kind == "jeweler" then
        create, up, down, search, qty = ui.createOne, ui.qtyUp, ui.qtyDown, ui.searchBox, ui.qtyBox
    else
        create, up, down, search, qty = ui.create, ui.up, ui.down, ui.search, ui.quantity
    end
    createAll = ui.createAll
    assert(create and createAll and up and down and search and qty, kind .. ": a control is missing")
    return {
        window = {points = normalise(ui.frame.points), width = ui.frame:GetWidth(), height = ui.frame:GetHeight(),
            backdrop = backdropFields(ui.frame.backdrop)},
        title = textLook(ui.title),
        subtitle = (function() local s = textLook(ui.sub); if s then s.color = ui.sub.textColor end; return s end)(),
        tabActive = tabLook(ui.tabs[1]),
        tabIdle = tabLook(ui.tabs[2]),
        row = rowLook(item),
        headRow = rowLook(head),
        search = {template = search.template, width = search:GetWidth(), height = search:GetHeight(), backdrop = backdropFields(search.backdrop)},
        qty = {template = qty.template, width = qty:GetWidth(), height = qty:GetHeight(), backdrop = backdropFields(qty.backdrop)},
        detail = {width = ui.detail:GetWidth(), height = ui.detail:GetHeight(), backdrop = backdropFields(ui.detail.backdrop),
            backdropColor = ui.detail.backdropColor, borderColor = ui.detail.borderColor},
        detailName = {font = ui.detail.name.template, points = normalise(ui.detail.name.points)},
        material = materialLook(material),
        cost = {font = ui.detail.cost.template},
        buttons = {create = buttonLook(create), createAll = buttonLook(createAll), up = buttonLook(up), down = buttonLook(down)},
        bar = {width = ui.bar:GetWidth(), height = ui.bar:GetHeight(), points = normalise(ui.bar.points),
            backdrop = backdropFields(ui.bar.backdrop), borderColor = ui.bar.borderColor,
            bg = ui.bar.bg and ui.bar.bg.vertexColor, fill = ui.bar.fill and ui.bar.fill.vertexColor, textFont = ui.bar.text.template},
        funds = ui.funds and {font = ui.funds.template, topLeft = topLeft(ui.funds)},
    }
end

local jewelerLook = collect("jeweler", DCJeweler.ui)
local blacksmithLook = collect("blacksmith", DCBlacksmith.ui)
assert(dump(jewelerLook) == dump(blacksmithLook),
    "the Blacksmith's shared look must match the Jeweler's:\nJeweler   " .. dump(jewelerLook) .. "\nBlacksmith " .. dump(blacksmithLook))

-- The second-tab body framing: the Blacksmith's Salvage/Repair bodies wear the Jeweler's view box.
local jewelerBox = DCJeweler.ui.socketView.box
local blacksmithSalvage, blacksmithRepair = DCBlacksmith.ui.salvageBox, DCBlacksmith.ui.repairBox
for name, box in pairs({salvage = blacksmithSalvage, repair = blacksmithRepair}) do
    assert(box and backdropFields(box.backdrop) and box.borderColor, name .. ": the second-tab body has a framed, coloured box")
    assert(dump({backdropFields(box.backdrop), box.borderColor}) == dump({backdropFields(jewelerBox.backdrop), jewelerBox.borderColor}),
        name .. ": the second-tab body framing follows the Jeweler's view box")
end

-- The Salvage rarity border (ruling 2026-10-03): a 2 px frame on the OVERLAY layer, above the
-- ARTWORK icon, with all four sides anchored inside the button. Today the slot's 1 px backdrop
-- edge is cut off at the top and sits under the icon art, so the colour never closes the square.
local SIDE_POINTS = {top = {"TOPLEFT", "TOPRIGHT"}, bottom = {"BOTTOMLEFT", "BOTTOMRIGHT"},
    left = {"TOPLEFT", "BOTTOMLEFT"}, right = {"TOPRIGHT", "BOTTOMRIGHT"}}
local SALVAGE_TINT = {TINT.legendary, TINT.normal, TINT.magic, TINT.rare}
for i, button in ipairs(DCBlacksmith.ui.salvageButtons) do
    assert(button.icon and button.icon.drawLayer == "ARTWORK", "salvage " .. i .. ": the icon is on the ARTWORK layer")
    local border = assert(button.border, "salvage " .. i .. ": the button draws a rarity border")
    for _, side in ipairs({"top", "bottom", "left", "right"}) do
        local tex = assert(border[side], "salvage " .. i .. ": the " .. side .. " side is drawn")
        assert(tex.drawLayer == "OVERLAY", "salvage " .. i .. " " .. side .. ": the border draws above the icon, got layer "
            .. tostring(tex.drawLayer))
        local thickness = (side == "top" or side == "bottom") and tex:GetHeight() or tex:GetWidth()
        assert(thickness == 2, "salvage " .. i .. " " .. side .. ": the border is 1 px thicker than the slot edge, got "
            .. tostring(thickness))
        local want = SIDE_POINTS[side]
        assert(#tex.points == 2, "salvage " .. i .. " " .. side .. ": the side needs two points, got " .. #tex.points)
        for p, point in ipairs(tex.points) do
            assert(point[1] == want[p] and point[2] == button and point[3] == want[p],
                "salvage " .. i .. " " .. side .. ": corner " .. p .. " must anchor to the button's " .. want[p])
            assert(point[4] == 0 and point[5] == 0, "salvage " .. i .. " " .. side .. ": the border is inside the button")
        end
        local tint = SALVAGE_TINT[i]
        assert(dump({tex.textureColor[1], tex.textureColor[2], tex.textureColor[3]}) == dump(tint),
            "salvage " .. i .. " " .. side .. ": the border wears the rarity colour, got " .. dump(tex.textureColor))
    end
end

----------------------------------------------------------------------------------------------------
-- The rules: no white boxes, rarity colour, first selection, greyed Create
----------------------------------------------------------------------------------------------------
local EDGE = "Interface\\Buttons\\WHITE8X8"
local white = {}
for _, f in ipairs(frames) do
    if f.backdrop and f.backdrop.bgFile == EDGE then
        if not f.backdropColor or not f.borderColor then white[#white + 1] = tostring(f.name or f.kind or "frame") end
    end
end
assert(#white == 0, "every flat backdrop must have a background and a border colour (the white-box bug): " .. table.concat(white, ", "))

-- Row colour is the item's rarity, enabled or not.
local function blacksmithRow(id)
    for _, f in ipairs(frames) do
        if f.parent == DCBlacksmith.ui.list and f.row and f.row.recipe and f.row.recipe.id == id then return f end
    end
end
for id, rarity in pairs({[1] = "legendary", [2] = "legendary", [3] = "set", [4] = "set", [5] = "rare"}) do
    local row = assert(blacksmithRow(id), "row " .. id .. " is drawn")
    local want = TINT[rarity]
    assert(dump(row.label.textColor) == dump({want[1], want[2], want[3]}),
        "row " .. id .. " (" .. rarity .. ") is the item's own colour, enabled or not, got " .. dump(row.label.textColor))
end
assert(blacksmithRow(1).row.recipe.enabled == false and blacksmithRow(3).row.recipe.enabled == false,
    "the disabled Legendary and Set rows are the ones being checked")

-- The first recipe is selected on open in both windows, so the detail pane is never empty.
assert(DCJeweler.ui.detail.name.text == "Amethyst", "the Jeweler selects its first recipe on open")
assert(DCBlacksmith.ui.detail.name.text and DCBlacksmith.ui.detail.name.text ~= "Select a recipe"
    and DCBlacksmith.ui.detail.name.text:find("recipe", 1, true), "the Blacksmith selects its first recipe on open")

-- Create and Create All are greyed out whenever the selected recipe cannot be made, in both windows.
assert(DCBlacksmith.ui.create.disabled and DCBlacksmith.ui.createAll.disabled, "Blacksmith: Create is greyed when nothing can be made")
assert(DCJeweler.ui.createOne.disabled and DCJeweler.ui.createAll.disabled, "Jeweler: Create is greyed when nothing can be made")
assert(dump(DCBlacksmith.ui.detail.cost.textColor) == dump({1, .19, .19}), "the Blacksmith's cost line is red when the gold is short")

-- The material count is a second line under the name, clear of the icon (so a big stock cannot
-- spill over the icon into the next column), in both windows.
for _, case in ipairs({{"jeweler", DCJeweler.ui}, {"blacksmith", DCBlacksmith.ui}}) do
    local kind, mat = case[1], case[2].detail.reagents[1]
    local slotAt, labelAt, countAt = topLeft(mat), topLeft(mat.label), topLeft(mat.count)
    assert(countAt[1] == labelAt[1], kind .. ": the count shares the name's left edge, got x "
        .. tostring(countAt[1]) .. " vs " .. tostring(labelAt[1]))
    assert(countAt[2] < labelAt[2], kind .. ": the count is a second line under the name, got y "
        .. tostring(countAt[2]) .. " vs " .. tostring(labelAt[2]))
    assert(countAt[1] - slotAt[1] >= mat:GetWidth(), kind .. ": the count is clear of the icon slot (offset "
        .. tostring(countAt[1] - slotAt[1]) .. " vs slot " .. tostring(mat:GetWidth()) .. ")")
end

-- Jeweler: the gem line is short (0 of 2) and red; Death's Breath shows the full grouped total.
local jewelerCounts = DCJeweler.ui.detail.reagents
assert(jewelerCounts[1].count.text == "0 / 2", "the Jeweler gem count reads have / need, got " .. tostring(jewelerCounts[1].count.text))
assert(dump(jewelerCounts[1].count.textColor) == dump({1, .19, .19}), "the Jeweler count is red when the gem is short")
assert(jewelerCounts[2].count.text == "100,002 / 30", "the Jeweler groups the full count, got " .. tostring(jewelerCounts[2].count.text))
-- UI fixes row 4 (ruling 2026-10-03): one material-count colour in both windows, the Blacksmith's:
-- gold when the stock covers it, red when short, and the name never greyed.
assert(dump(jewelerCounts[2].count.textColor) == dump({1, .82, 0}), "the Jeweler count is gold when the Death's Breath covers it, got "
    .. dump(jewelerCounts[2].count.textColor))

-- Blacksmith: 100,002 / 30 in full (gold), and the short second line red.
local blacksmithCounts = DCBlacksmith.ui.detail.reagents
assert(blacksmithCounts[1].count.text == "100,002 / 30", "the Blacksmith groups the full count, got " .. tostring(blacksmithCounts[1].count.text))
assert(dump(blacksmithCounts[1].count.textColor) == dump({1, .82, 0}), "the Blacksmith count is gold when the stock covers it")
assert(blacksmithCounts[2].count.text == "0 / 500,000", "the Blacksmith groups the empty count, got " .. tostring(blacksmithCounts[2].count.text))
assert(dump(blacksmithCounts[2].count.textColor) == dump({1, .19, .19}), "the Blacksmith count is red when short")

local blacksmithCountsLabel = blacksmithCounts[2].label.textColor
assert(dump(jewelerCounts[1].label.textColor) == dump(blacksmithCountsLabel),
    "a short material's name looks the same in both windows, got " .. dump(jewelerCounts[1].label.textColor) .. " and " .. dump(blacksmithCountsLabel))
-- ...because both windows draw the count through ONE shared setter in DCUI: replaced here, it is what both use.
assert(type(DCUI.count) == "function", "DCUI has the shared count setter")
local setterLines = {}
local sharedCount = DCUI.count
DCUI.count = function(line, ...) setterLines[line] = true; return sharedCount(line, ...) end
handlersByChannel.DiablocraftJeweler.Show(nil, {
    items = EMPTY_ITEMS, gems = EMPTY_ITEMS,
    recipes = {{id = 6001, inputEntry = 6001, inputCount = 2, gold = 0, deathsBreath = 30, name = "Amethyst",
        inputName = "Amethyst", colour = "Amethyst", tier = "", rank = 1, have = 0}},
    balance = {gold = "0", deathsBreath = "100002"},
})
handlersByChannel.DiablocraftBlacksmith.Show(nil, {title = "Blacksmith", playerLevel = 70, class = "barbarian",
    gold = "0", materials = {[102001] = "100002"}, maxCount = 16, castSeconds = 2, items = {},
    recipes = {recipe(1, "legendary", false), recipe(2, "legendary", true)}})
DCUI.count = sharedCount
for _, case in ipairs({{"jeweler", jewelerCounts}, {"blacksmith", blacksmithCounts}}) do
    for index = 1, 2 do
        assert(setterLines[case[2][index]], case[1] .. ": material line " .. index .. " is drawn by DCUI.count")
    end
end

----------------------------------------------------------------------------------------------------
-- UI fixes row 3 (ruling 2026-10-03): the Jeweler takes its look from DCUI, not a copy
----------------------------------------------------------------------------------------------------
-- Change the shared definition and load the Jeweler again: every piece the review found built by
-- hand (the Sockets window, the two inputs, the tabs, the detail pane, the view box, the list
-- indents and steps) must wear the changed values, so the two windows cannot drift apart.
local KEYS = {"TAB_ACTIVE", "TAB_IDLE", "BOX_BORDER", "BOX_ACTIVE", "DETAIL_BG", "DETAIL_BORDER",
    "HEAD_INDENT", "ROW_INDENT", "HEAD_STEP", "ROW_HEIGHT", "window", "input"}
local kept = {}
for _, key in ipairs(KEYS) do kept[key] = DCUI[key] end
DCUI.TAB_ACTIVE, DCUI.TAB_IDLE = {.11, .12, .13}, {.21, .22, .23}
DCUI.BOX_BORDER, DCUI.BOX_ACTIVE = {.31, .32, .33}, {.41, .42, .43}
DCUI.DETAIL_BG, DCUI.DETAIL_BORDER = {.05, .06, .07}, {.51, .52, .53}
DCUI.HEAD_INDENT, DCUI.ROW_INDENT, DCUI.HEAD_STEP, DCUI.ROW_HEIGHT = 7, 29, 23, 19
local windows, inputs = {}, {}
DCUI.window = function(name, ...) local made = kept.window(name, ...); windows[name] = made; return made end
DCUI.input = function(parent, name) local made = kept.input(parent, name); inputs[made] = true; return made end
dofile(JEWELER_SOURCE)
handlersByChannel.DiablocraftJeweler.Tables(nil, {gems = {[6001] = "Amethyst", [6002] = "Flawless Amethyst"}, effects = {}})
handlersByChannel.DiablocraftJeweler.Show(nil, {
    items = EMPTY_ITEMS, gems = EMPTY_ITEMS,
    recipes = {{id = 6001, inputEntry = 6001, inputCount = 2, gold = 0, deathsBreath = 0, name = "Amethyst",
        inputName = "Amethyst", colour = "Amethyst", tier = "", rank = 1, have = 0},
        {id = 6002, inputEntry = 6001, inputCount = 2, gold = 0, deathsBreath = 0, name = "Flawless Amethyst",
        inputName = "Amethyst", colour = "Amethyst", tier = "", rank = 2, have = 0}},
    balance = {gold = "0", deathsBreath = "0"},
})
local marked = DCJeweler.ui
assert(windows.DiablocraftJewelerFrame == marked.frame, "the Jeweler window is DCUI's window")
assert(windows.DiablocraftSocketsFrame == marked.sockFrame, "the Sockets window is DCUI's window too")
assert(marked.sockFrame:GetWidth() == 480 and marked.sockFrame:GetHeight() == 400, "the Sockets window keeps its size")
assert(inputs[marked.searchBox] and inputs[marked.qtyBox], "the search and quantity boxes are DCUI inputs")
assert(dump(marked.tabs[1].borderColor) == dump({.11, .12, .13, 1}) and dump(marked.tabs[2].borderColor) == dump({.21, .22, .23, 1}),
    "the tabs wear DCUI's active and idle edges, got " .. dump(marked.tabs[1].borderColor) .. " and " .. dump(marked.tabs[2].borderColor))
assert(dump(marked.detail.backdropColor) == dump({.05, .06, .07, .85}) and dump(marked.detail.borderColor) == dump({.51, .52, .53, 1}),
    "the detail pane is DCUI's detail colours, got " .. dump(marked.detail.backdropColor) .. " / " .. dump(marked.detail.borderColor))
marked.socketView:Render()
assert(dump(marked.socketView.box.borderColor) == dump({.31, .32, .33, 1}),
    "the empty view box wears DCUI's box edge, got " .. dump(marked.socketView.box.borderColor))
local rowsDrawn = {}
for _, f in ipairs(frames) do
    if f.parent == marked.list and f.row and f.shown then rowsDrawn[#rowsDrawn + 1] = f end
end
table.sort(rowsDrawn, function(a, b) return a.points[1][3] > b.points[1][3] end)
assert(#rowsDrawn == 3 and rowsDrawn[1].row.head, "one header and two recipes are drawn, got " .. #rowsDrawn)
assert(indent(rowsDrawn[1]) == 7 and indent(rowsDrawn[2]) == 29, "the header and recipe indents are DCUI's, got "
    .. tostring(indent(rowsDrawn[1])) .. " and " .. tostring(indent(rowsDrawn[2])))
assert(rowsDrawn[2].points[1][3] == -23 and rowsDrawn[3].points[1][3] == -42, "the header and row steps are DCUI's, got "
    .. tostring(rowsDrawn[2].points[1][3]) .. " and " .. tostring(rowsDrawn[3].points[1][3]))
-- And the style is never cached at load: every builder resolves Diablocraft.Style on its call.
local jewelerText = assert(io.open(JEWELER_SOURCE)):read("*a")
assert(not jewelerText:find("U.resolve()", 1, true), "the Jeweler does not cache U.resolve() at load")
for _, key in ipairs(KEYS) do DCUI[key] = kept[key] end

print("PASS Blacksmith look: shared window, title, subtitle, tabs, rows, boxes, detail, materials, buttons, bar and gold "
    .. "line match the Jeweler's; no white flat backdrop; rarity colours; first selection; greyed Create; "
    .. "material counts grouped under the material's name, red when short, in both windows")
