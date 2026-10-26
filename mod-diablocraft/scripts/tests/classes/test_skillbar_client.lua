-- luacheck: ignore 122
-- Run from repo root with lua52_interpreter.exe.
--
-- The client half of dc_skillbar.lua against a stub 3.3.5a API. The remaining
-- skills screen is pinned here: its overview, skill/rune/passive pickers, wire
-- messages, P-key hook and /dcskills entry point.
--
--   * GetSpellTexture is never called with a spell id (it returns nil for one);
--   * Accept sends DCSLOT with the slot field, and DCPASSIVE with its slot.

local combat = false
local inInstance = false
local sent = {}
local textureCalls = {}

-- The catalogue the server would push: a few skills across categories, one with
-- runes, plus passives. `categories` is the server's ordered dc_class_category
-- list and is the only source of the columns (no CATEGORY_ORDER in the file).
-- Names and ids follow data/generated/spell_shells.csv.
local CATALOGUE = {
    level = 30,
    passiveSlots = 3,
    activeSlots = 6, passiveSlotCount = 4, passiveSlotLevels = {10, 20, 30, 70},
    categories = {"Primary", "Secondary", "Might"},
    skills = {
        {name = "Bash", category = "Primary", unlock = 1, locked = false, spell = 81002},
        {name = "Frenzy", category = "Primary", unlock = 11, locked = false, spell = 81000},
        {name = "Rend", shown = "Rending", category = "Secondary", unlock = 5, locked = false, spell = 81008},
        {name = "Avalanche", category = "Might", unlock = 61, locked = true, spell = 81014},
    },
    runes = {
        Bash = {
            {name = "Onslaught", element = "Lightning", unlock = 8, locked = false, spell = 81033},
            {name = "Frostbite", element = "Cold", unlock = 42, locked = true, spell = 81035},
        },
    },
    passives = {
        {name = "Ruthless", shown = "Ruthless Hunter", unlock = 10, locked = false, spell = 81139},
        {name = "Animosity", shown = "Animus", unlock = 27, locked = false, spell = 81145},
        {name = "Rampage", unlock = 65, locked = true, spell = 81156},
    },
    bar = {[0] = {skill = "Bash", rune = "Onslaught"}, [2] = {skill = "Rend", rune = ""}},
    passiveBar = {[0] = "Ruthless"},
}

local NAMES = {
    [81000] = "Frenzy", [81002] = "Bash", [81008] = "Rend", [81014] = "Avalanche",
    [81033] = "Bash - Onslaught", [81035] = "Bash - Frostbite",
    [81139] = "Ruthless", [81145] = "Animosity", [81156] = "Rampage",
    -- data/generated/spell_shells.csv: Town Portal, the fixed seventh slot.
    [81167] = "Town Portal",
}
local ICONS = {}
for id, name in pairs(NAMES) do ICONS[id] = "icon:" .. name end

-- --- stub API -----------------------------------------------------------
-- The widget layer is ONE shared strict 3.3.5a mock (diablocraft-yey2): it owns
-- CreateFrame, UIParent, GameTooltip, UIErrorsFrame and hooksecurefunc. The
-- doubles below are this test's own client globals.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
-- The file under test, overridable so a mutant copy can be run without touching the repo
-- copy (the sibling client tests' own DC_*_LUA variable).
local SOURCE = os.getenv("DC_SKILLBAR_LUA") or 'mod-diablocraft/lua/aio/dc_skillbar.lua'
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)

_G.InCombatLockdown = function() return combat end
_G.IsInInstance = function() return inInstance end
_G.GetSpellInfo = function(id)
    if type(id) ~= "number" or not NAMES[id] then return nil end
    return NAMES[id], nil, ICONS[id], 0, false, 0, 0, 0, 0
end
_G.GetSpellTexture = function(id)
    -- The whole point: this client returns nil for a spell id, so any call with
    -- one is a bug even though it raises no error.
    table.insert(textureCalls, id)
    return nil
end
_G.UnitName = function() return "Tester" end
_G.SendAddonMessage = function(prefix, body, channel, target)
    table.insert(sent, {prefix = prefix, body = body, channel = channel, target = target})
end
_G.SlashCmdList = {}

-- The stock spellbook surface: P and the micro-button both call ToggleSpellBook.
_G.BOOKTYPE_SPELL, _G.BOOKTYPE_PET = "spell", "pet"
_G.SpellBookFrame = {shown = false}
function _G.SpellBookFrame:Show() self.shown = true end
function _G.SpellBookFrame:Hide() self.shown = false end
function _G.SpellBookFrame:IsShown() return self.shown end
_G.HideUIPanel = function(panel) panel:Hide() end
-- The stock function, unreplaced: our code must hook it, never assign over it.
-- The shared mock's hooksecurefunc wraps the global, so count the stock runs to
-- prove the wrapper still calls through rather than replacing it.
local stockCalls = 0
local stockToggleSpellBook = function(bookType)
    stockCalls = stockCalls + 1
    if bookType ~= _G.BOOKTYPE_SPELL then return end
    if _G.SpellBookFrame:IsShown() then _G.SpellBookFrame:Hide() else _G.SpellBookFrame:Show() end
end
_G.ToggleSpellBook = stockToggleSpellBook
local function pressP()
    _G.ToggleSpellBook(_G.BOOKTYPE_SPELL)
end

local handlerTable
_G.AIO = {
    AddAddon = function() return false end,
    AddHandlers = function() handlerTable = {} return handlerTable end,
    Handle = function(_, action) table.insert(sent, {aio = action}) end,
}

dofile(SOURCE)

local screen = _G.DiablocraftSkillbarFrame

-- The three views are the three plain Frames parented to the dialog, in the
-- order the file builds them: overview, skill, passive.
local views = {}
for _, frame in ipairs(frames) do
    if frame.parent == screen and frame.kind == "Frame" then views[#views + 1] = frame end
end
assert(#views == 3, "three views, got " .. #views)
local overviewView, skillChooser, passiveChooser = views[1], views[2], views[3]

-- ------------------------------------------- the Jeweler's window look

-- Ruling 2026-10-01 (restyle): the Skills window wears the Jeweler's look - the
-- stock dialog backdrop, a native close button and native WoW buttons, and no
-- UIPanelDialogTemplate chrome. The look is one shared table (the Torment addon's
-- Diablocraft.Style) with this file's own copy as the fallback; this load has no
-- addon, so it exercises the fallback, and the copies are pinned against each
-- other field by field below.
assert(_G.Diablocraft == nil, "no addon here: the fallback copy is what this load uses")
assert(screen.template == nil, "no UIPanelDialogTemplate chrome on the Skills window")
local function stripComments(source)
    source = source:gsub("%-%-%[%[.-%]%]", "")
    return (source:gsub("%-%-[^\n]*", ""))
end
assert(not stripComments(assert(io.open("mod-diablocraft/lua/aio/dc_skillbar.lua")):read("*a"))
    :find("UIPanelDialogTemplate", 1, true), "and none left in the code")

local uiModuleSource = assert(io.open("mod-diablocraft/lua/aio/dc_aio_ui.lua")):read("*a")
local panelSource = assert(uiModuleSource:match("local PANEL=(%b{})"), "dc_aio_ui.lua declares the shared PANEL")
local addonSource = assert(io.open("client-patch/addons/Torment/WindowStyle.lua")):read("*a")
local styleSource = assert(addonSource:match("local WINDOW_BACKDROP%s*=%s*(%b{})"),
    "WindowStyle.lua publishes WINDOW_BACKDROP for the shared DC.Style")
-- tolerant of the two files' spacing: dc_jeweler.lua writes bgFile="..", the
-- addon's core writes bgFile = "..".
local function field(source, name)
    return assert(source:match(name .. '%s*=%s*"([^"]+)"')):gsub("\\\\", "\\")
end
local function numberOf(source, name) return tonumber(assert(source:match(name .. "%s*=%s*(%d+)"))) end

local look = screen.backdrop
assert(look, "the Skills window has a backdrop")
assert(look.bgFile == field(panelSource, "bgFile") and look.edgeFile == field(panelSource, "edgeFile"),
    "the same dialog textures as the Jeweler")
assert(look.bgFile == field(styleSource, "bgFile") and look.edgeFile == field(styleSource, "edgeFile"),
    "and the same ones as the addon's shared DC.Style")
assert(look.tile == true and look.tileSize == numberOf(panelSource, "tileSize")
    and look.edgeSize == numberOf(panelSource, "edgeSize"), "the same tiling and edge size")
for _, key in ipairs({"left", "right", "top", "bottom"}) do
    assert(look.insets[key] == numberOf(panelSource, key),
        "the same " .. key .. " inset as the Jeweler, got " .. tostring(look.insets[key]))
end
assert(screen.strata == "HIGH", "the window sits in the Jeweler's strata")

local templates, closeButton = {}, nil
for _, frame in ipairs(frames) do
    -- CreateFontString/CreateTexture also record their font/art template on
    -- .template; the chrome scan below is about frames and buttons only.
    if frame.template and (frame.kind == "Frame" or frame.kind == "Button") then
        templates[frame.template] = (templates[frame.template] or 0) + 1
        if frame.template == "UIPanelCloseButton" and frame.parent == screen then closeButton = frame end
    end
end
assert(closeButton, "the window has a native close button")
local corner = closeButton.points[1]
assert(corner and corner[1] == "TOPRIGHT" and corner[2] == screen and corner[3] == "TOPRIGHT"
    and corner[4] == -6 and corner[5] == -6, "the close button sits at the Jeweler's corner")
assert(templates["UIPanelCloseButton"] == 1, "exactly one close button")
assert((templates["UIPanelButtonTemplate"] or 0) >= 2, "the buttons are native WoW buttons")
for template in pairs(templates) do
    assert(template == "UIPanelButtonTemplate" or template == "UIPanelCloseButton",
        "no other template on the Skills screen, got " .. template)
end
for _, frame in ipairs(frames) do
    if frame.text == "Accept" or frame.text == "Cancel" then
        assert(frame.template == "UIPanelButtonTemplate", frame.text .. " is a native WoW button")
    end
end

-- The quickslot frame art is drawn 66/36 of the button, as stock does, so its
-- opaque ring sits outside the icon: at the button's own size it covered the
-- icon and showed a smaller second copy through its window.
local iconButtons = 0
for _, frame in ipairs(frames) do
    if frame.kind == "Button" and frame.normalTexture then
        iconButtons = iconButtons + 1
        local art = frame.normalTexture
        assert(art.texture == "Interface\\Buttons\\UI-Quickslot2", "frame art kept")
        assert(math.abs(art:GetWidth() - frame:GetWidth() * 66 / 36) < 1e-6
               and art:GetWidth() == art:GetHeight(), "frame art is 66/36 of the button")
    end
end
assert(iconButtons > 0, "icon buttons checked: " .. iconButtons)

local function cells(view, predicate)
    local list = {}
    for _, frame in ipairs(frames) do
        -- The old stub kept FontStrings/Textures out of its frame list; the mock
        -- lists every widget, so a "cell" here is a frame, never a region.
        if frame.parent == view and frame.kind ~= "FontString" and frame.kind ~= "Texture"
           and frame.kind ~= "Line" and frame.shown and (not predicate or predicate(frame)) then
            list[#list + 1] = frame
        end
    end
    return list
end

-- --- opening before any payload ------------------------------------------
-- Architect 2026-09-19: no gameplay defaults in client Lua. With no payload the
-- toggle opens a loading state and asks; no slot cell is drawn or guessed, and
-- the payload arriving through the data-only Set draws the real count.
screen:Hide()
combat = false
local beforeOpen = #sent
SlashCmdList["DCSKILLS"]()
assert(screen:IsShown(), "the screen opens while the payload is in flight")
local requests = 0
for index = beforeOpen + 1, #sent do
    if sent[index].aio == "Request" then requests = requests + 1 end
end
assert(requests == 1, "opening with no payload requests the catalogue")
assert(#cells(overviewView, nil) == 0, "no slot cell is drawn without the payload")

handlerTable.Set(nil, CATALOGUE)
assert(screen:IsShown(), "a data-only Set does not close a screen already open")
assert(#cells(overviewView, function(f) return f.rune ~= nil end) == 6,
       "the six active cells are drawn once the payload arrives")

-- A data-only Set must never open the screen by itself.
screen:Hide()
handlerTable.Set(nil, CATALOGUE)
assert(not screen:IsShown(), "Set never opens the screen by itself")

-- A catalogue update redraws only the screen. No custom action buttons, portal
-- button or skills launcher are created; the stock action bar owns casting.
assert(#textureCalls == 0, "GetSpellTexture called with a spell id: " .. tostring(textureCalls[1]))
assert(_G.DiablocraftSkillButton1 == nil, "custom skill buttons are removed")
assert(_G.DiablocraftPortalButton == nil, "Town Portal uses native action button 8")
assert(_G.DiablocraftSkillsButton == nil, "the book button beside the bar is gone")
assert(type(SlashCmdList["DCSKILLS"]) == "function", "and /dcskills is what opens the screen")
assert(_G.DiablocraftRuneMenu == nil, "the rune menu frame is gone")

-- --- the screen: overview -----------------------------------------------
assert(not screen:IsShown())
handlerTable.Show(nil, CATALOGUE)
assert(screen:IsShown())

-- Slot 1 of the overview: icon, skill name, rune name, key number.
local overviewSlot1 = cells(overviewView, function(f)
    return f.name and f.name.text == "Bash" and f.badge and f.badge.text == 1
end)[1]
assert(overviewSlot1, "overview slot 1 shows Bash")
assert(overviewSlot1.icon.texture == "icon:Bash - Onslaught")
assert(overviewSlot1.rune.text == "Onslaught")
-- Slot 3 holds Rend, whose record is named Rending: the slot draws the name the player reads, the key stays the bar's.
assert(#cells(overviewView, function(f)
    return f.name and f.name.text == "Rending" and f.badge and f.badge.text == 3
end) == 1, "overview slot 3 shows Rend by its shown name")
assert(#cells(overviewView, function(f) return f.name and f.name.text == "Rend" end) == 0,
       "and never by its key")

-- --- the screen: pick a skill and a rune --------------------------------
overviewSlot1.scripts.OnClick()
-- The fixture's tallest category has two skills, so the grid is two rows deep
-- and the frame is sized to it: 64 + 2 * 62 + 150.
assert(screen:GetHeight() == 338, "the skill view is sized to its grid, got " .. tostring(screen:GetHeight()))

-- Every skill is offered whatever the slot: Elective Mode (K6).
local offered = {}
for _, cell in ipairs(cells(skillChooser, function(f) return f.name and f.name.text ~= "" end)) do
    offered[cell.name.text] = cell
end
for _, skill in ipairs(CATALOGUE.skills) do
    assert(offered[skill.shown or skill.name], skill.name .. " is missing from the skill view")
end
-- A skill draws its record's name, never its key (two classes can share a name under two keys: Earthquake), and
-- the slot mark is still found by the key.
assert(not offered["Rend"], "a skill's key is not drawn where a shown name exists")
assert(offered["Rending"].badge.text == 3, "and the shown skill still carries its slot number")
-- Bash already sits in slot 1, so it carries its slot number and the "on the
-- bar" mark (K6: choosing it elsewhere moves it).
assert(offered["Bash"].badge.text == 1 and offered["Bash"].slotted:IsShown())
-- With no Torment addon the two overlays are the stock textures, exactly as
-- before the slots existed.
assert(offered["Bash"].slotted.texture == "Interface\\Buttons\\UI-ActionButton-Border",
    "no addon: the slotted overlay keeps the stock border")
assert(offered["Bash"].chosen.texture == "Interface\\Buttons\\CheckButtonHilight",
    "no addon: the chosen overlay keeps the stock hilight")

-- Dragging a skill onto an action-bar well sets that slot (ruling 2026-10-11,
-- windows-skill-drag-to-bar): the drop asks ElvUI_Torment which well the cursor
-- is over and sends the same DCSLOT the Accept button does. Nothing is put on
-- the cursor. With no ElvUI module the drop does nothing at all.
do
    local dropSlot
    _G.ElvUI = {[1] = {GetModule = function(_, name)
        if name == "ElvUI_Torment" then return {BarSlotUnderMouse = function() return dropSlot end} end
    end}}
    local function lastSlot()
        local found
        for index = 1, #sent do if sent[index].prefix == "DCSLOT" then found = sent[index] end end
        return found
    end
    local function dropOn(cell)
        local seen = lastSlot()
        cell.scripts.OnDragStart()
        cell.scripts.OnDragStop()
        return lastSlot() ~= seen and lastSlot() or nil
    end
    dropSlot = 2
    local dropped = dropOn(offered["Bash"])
    assert(dropped and dropped.body == "Bash\t\t2", "a skill dropped on well 3 sets slot 2, got "
        .. tostring(dropped and dropped.body))
    -- A drop that lands on no skill well (nil, or the potion/portal wells the
    -- module does not name) sends nothing.
    dropSlot = nil
    assert(dropOn(offered["Bash"]) == nil, "a drop off the skill wells sends nothing")
    -- Without the ElvUI module there is no bar this window can name.
    _G.ElvUI = nil
    assert(dropOn(offered["Bash"]) == nil, "no ElvUI_Torment: the drop sends nothing")
end

-- Dragging a skill from one skill well to another on the bar moves it there; onto
-- a taken well the two swap. ElvUI_Torment reports the drag by calling
-- module.OnWellDrag(sourceSlot) when it ends; the target is the well under the
-- cursor. Either way it is one DCSWAP <from> <to> (0-based slots), which the
-- server does in one step, so the window paces nothing and resends nothing.
do
    local dropSlot
    local wells = {BarSlotUnderMouse = function() return dropSlot end}
    _G.ElvUI = {[1] = {GetModule = function(_, name)
        if name == "ElvUI_Torment" then return wells end
    end}}
    local cleared = 0
    _G.ClearCursor = function() cleared = cleared + 1 end
    local function bar(map, answer)
        local payload = {}
        for key, value in pairs(CATALOGUE) do payload[key] = value end
        payload.bar = map
        handlerTable[answer or "Set"](nil, payload)
    end
    local function startBar()
        return {[0] = {skill = "Bash", rune = "Onslaught"}, [2] = {skill = "Rend", rune = "Bloodbath"}}
    end
    bar(startBar())
    assert(type(wells.OnWellDrag) == "function", "the skills file hands ElvUI_Torment the drag callback")
    -- What one drag put on the wire, split by kind.
    local function drag(from, to)
        local mark = #sent
        dropSlot = to
        wells.OnWellDrag(from)
        local out = {swap = {}, slot = {}, refresh = 0}
        for index = mark + 1, #sent do
            local message = sent[index]
            if message.prefix == "DCSWAP" then out.swap[#out.swap + 1] = message end
            if message.prefix == "DCSLOT" then out.slot[#out.slot + 1] = message end
            if message.aio == "Refresh" then out.refresh = out.refresh + 1 end
        end
        return out
    end

    -- A free well: one DCSWAP, no DCSLOT, and a Refresh to read the result.
    local out = drag(0, 4)
    assert(#out.swap == 1 and out.swap[1].body == "0\t4" and #out.slot == 0,
        "a skill dragged to a free well is one DCSWAP 0 -> 4")
    assert(out.swap[1].channel == "WHISPER" and out.swap[1].target == "Tester",
        "DCSWAP is the player's own addon whisper, as DCSLOT's")
    assert(out.refresh == 1, "the window asks for the result")
    assert(cleared == 1, "the cursor is cleared so the native drop leaves nothing behind")
    bar(startBar())

    -- A taken well: still one DCSWAP, never the two DCSLOT halves.
    out = drag(0, 2)
    assert(#out.swap == 1 and out.swap[1].body == "0\t2" and #out.slot == 0,
        "a swap is one DCSWAP 0 -> 2, got " .. #out.swap .. " swaps and " .. #out.slot .. " slots")
    bar(startBar())

    -- Nothing else is sent later: the server did it all in one step, so a catalogue
    -- that shows the bar unchanged (the swap was refused) is not answered by a resend.
    local mark = #sent
    drag(0, 2)
    bar(startBar())
    bar(startBar(), "Show")
    for index = mark + 2, #sent do
        assert(sent[index].prefix ~= "DCSLOT" and sent[index].prefix ~= "DCSWAP",
            "a refused swap is not resent, got " .. tostring(sent[index].prefix))
    end

    -- Until the answer arrives no other drag starts, so two DCSWAPs never race.
    bar(startBar())
    drag(0, 2)
    out = drag(2, 4)
    assert(#out.swap == 0 and #out.slot == 0 and out.refresh == 0, "no second drag while a swap is pending")
    out = drag(0, 4)
    assert(#out.swap == 0, "no drag of any well while a swap is pending")
    bar(startBar())
    out = drag(2, 4)
    assert(#out.swap == 1 and out.swap[1].body == "2\t4", "the next Set ends the wait")

    -- The answer to the player's own Request (Show) ends it too.
    bar(startBar())
    drag(0, 2)
    assert(#drag(2, 4).swap == 0, "still pending")
    bar(startBar(), "Show")
    assert(#drag(2, 4).swap == 1, "the next Show ends the wait")
    bar(startBar())
    -- A Show lands on the overview; the checks below go on from slot 1's skill view.
    overviewSlot1.scripts.OnClick()

    -- Nothing in the window ticks a clock for a swap.
    mark = #sent
    for _, frame in ipairs(frames) do
        if frame.scripts.OnUpdate then frame.scripts.OnUpdate(frame, 5) end
    end
    for index = mark + 1, #sent do
        assert(sent[index].prefix ~= "DCSLOT" and sent[index].prefix ~= "DCSWAP", "no frame sends a swap half on a timer")
    end

    -- The swap against a model of the server's side: one transaction (both wells or
    -- neither), the refusal of any bar edit in combat. A refused swap leaves both
    -- skills on the bar, which the two halves could not promise.
    local server = {combat = false, bar = {}}
    local function pump(from)
        for index = from + 1, #sent do
            local message = sent[index]
            if message.prefix == "DCSWAP" then
                local a, b = message.body:match("^(%d+)\t(%d+)$")
                a, b = tonumber(a), tonumber(b)
                if not server.combat then
                    server.bar[a], server.bar[b] = server.bar[b], server.bar[a]
                end
            elseif message.aio == "Refresh" then
                local payload = {}
                for key, value in pairs(CATALOGUE) do payload[key] = value end
                payload.bar = {}
                for slot, entry in pairs(server.bar) do payload.bar[slot] = entry end
                handlerTable.Set(nil, payload)
            end
        end
    end
    local function setup()
        server.combat = false
        server.bar = startBar()
        bar(startBar())
    end
    local function count() local n = 0 for _ in pairs(server.bar) do n = n + 1 end return n end

    setup()
    mark = #sent
    drag(0, 2) pump(mark)
    assert(server.bar[2].skill == "Bash" and server.bar[0].skill == "Rend" and count() == 2,
        "the swap lands in one step: Bash in well 3, Rend in well 1")
    assert(#drag(2, 4).swap == 1, "the answer ended the wait")

    setup()
    mark = #sent
    drag(0, 4) pump(mark)
    assert(server.bar[4].skill == "Bash" and server.bar[0] == nil and server.bar[2].skill == "Rend",
        "a move to a free well lands, the other skill untouched")

    setup()
    server.combat = true
    mark = #sent
    drag(0, 2) pump(mark)
    assert(server.bar[0].skill == "Bash" and server.bar[2].skill == "Rend" and count() == 2,
        "a swap the server refuses leaves both skills on the bar")
    assert(#drag(0, 2).swap == 1, "and the wait is over, so the player can try again")

    -- Nothing moves for: a drop on no skill well (off the bar, the potion well),
    -- a drop back on its own well, an empty source well, and combat.
    for _, case in ipairs({{0, nil}, {0, 0}, {3, 1}}) do
        local result = drag(case[1], case[2])
        assert(#result.swap == 0 and #result.slot == 0, "drag " .. case[1] .. " -> " .. tostring(case[2]) .. " sends nothing")
    end
    combat = true
    assert(#drag(0, 4).swap == 0, "no bar change in combat")
    combat = false
    _G.ElvUI = nil
    _G.ClearCursor = nil
    bar(startBar())
end

-- The rune buttons are No Rune plus the five; Bash has two in this fixture.
local runeLabels = {}
for name, cell in pairs(offered) do
    if name == "No Rune" or name == "Onslaught" or name == "Frostbite" then runeLabels[name] = cell end
end
assert(runeLabels["No Rune"] and runeLabels["Onslaught"] and runeLabels["Frostbite"],
       "No Rune plus every rune of the skill is offered")

-- A locked rune cannot be chosen.
runeLabels["Frostbite"].scripts.OnClick()
runeLabels["No Rune"].scripts.OnClick()

local before = #sent
local acceptButton, cancelButton
for _, frame in ipairs(frames) do
    if frame.text == "Accept" then acceptButton = frame end
    if frame.text == "Cancel" then cancelButton = frame end
end
assert(acceptButton and cancelButton and acceptButton.shown and cancelButton.shown)
acceptButton.scripts.OnClick()

local slotMessage
for index = before + 1, #sent do
    if sent[index].prefix == "DCSLOT" then slotMessage = sent[index] end
end
assert(slotMessage, "Accept sends DCSLOT")
-- skill, rune, slot - the fourth field of the wire format, so the skill lands in
-- the slot that was clicked rather than the first free one.
assert(slotMessage.body == "Bash\t\t0", "got " .. slotMessage.body)
assert(slotMessage.channel == "WHISPER" and slotMessage.target == "Tester")
assert(screen:GetHeight() == 290, "Accept returns to the overview")

-- Cancel sends nothing.
overviewSlot1.scripts.OnClick()
before = #sent
cancelButton.scripts.OnClick()
for index = before + 1, #sent do
    assert(sent[index].prefix == nil, "Cancel must not send an intent")
end

-- --- the screen: pick a passive -----------------------------------------
local passiveSlot1 = cells(overviewView, function(f)
    return f.name and f.name.text == "Ruthless Hunter"
end)[1]
assert(passiveSlot1, "the overview draws the chosen passive under the name the player reads, not its key")
-- The fourth passive slot opens at 70 and this fixture is level 30, so it is
-- drawn as closed and does not lead anywhere.
local closed = cells(overviewView, function(f)
    return f.name and f.name.text == "|cff808080Opens at 70|r"
end)[1]
assert(closed and closed.scripts.OnClick == nil, "the level-70 passive slot is closed")

passiveSlot1.scripts.OnClick()

local passiveOffered = {}
for _, cell in ipairs(cells(passiveChooser, function(f) return f.name and f.name.text ~= "" end)) do
    passiveOffered[cell.name.text] = cell
end
for _, passive in ipairs(CATALOGUE.passives) do
    assert(passiveOffered[passive.shown or passive.name], passive.name .. " is missing from the passive view")
end
assert(passiveOffered["Ruthless Hunter"].slotted:IsShown(), "the chosen passives are highlighted by key")
assert(not passiveOffered["Animosity"], "a key is not drawn where a shown name exists")
local animosity = passiveOffered["Animus"]
assert(animosity, "every passive is offered")
-- Each passive draws the icon of its own spell, in the picker and in the overview, and no two are alike (the
-- server's passive records once all carried one icon: every passive showed the same face).
local seenIcons = {}
for _, passive in ipairs(CATALOGUE.passives) do
    local cell = passiveOffered[passive.shown or passive.name]
    assert(cell.icon.texture == ICONS[passive.spell], passive.name .. " draws its own spell's icon, got " .. tostring(cell.icon.texture))
    assert(not seenIcons[cell.icon.texture], passive.name .. " shares its icon with " .. tostring(seenIcons[cell.icon.texture]))
    seenIcons[cell.icon.texture] = passive.name
end
assert(passiveSlot1.icon.texture == ICONS[81139], "the overview's passive slot draws its passive's icon")
animosity.scripts.OnClick()
before = #sent
acceptButton.scripts.OnClick()
local passiveMessage
for index = before + 1, #sent do
    if sent[index].prefix == "DCPASSIVE" then passiveMessage = sent[index] end
end
assert(passiveMessage, "Accept sends DCPASSIVE")
assert(passiveMessage.body == "0\tAnimosity", "the pick is sent under its key, got " .. passiveMessage.body)

-- --- P and the spellbook micro-button ------------------------------------
-- The addon hooked the stock global (the mock wrapped it), never assigned over
-- it: the wrapper still runs the stock function when P is pressed. The global must be
-- the wrapper itself (Mock.hooks): _G.ToggleSpellBook ~= stockToggleSpellBook alone
-- passes a plain replacement that calls the stock one (diablocraft-s5kn).
assert(_G.ToggleSpellBook == Mock.hooks.ToggleSpellBook, "ToggleSpellBook is hooked, never replaced")

screen:Hide()
_G.SpellBookFrame:Hide()
combat = false
pressP()
assert(screen:IsShown(), "P opens the skills screen")
assert(stockCalls == 1, "the stock ToggleSpellBook still runs through the hook")
assert(not _G.SpellBookFrame:IsShown(), "the stock spellbook is put away")
pressP()
assert(not screen:IsShown(), "P again closes it")
assert(not _G.SpellBookFrame:IsShown())

-- The pet book is not ours.
_G.ToggleSpellBook(_G.BOOKTYPE_PET)
assert(not screen:IsShown(), "the pet book is left alone")

-- In combat P does nothing visible and the stock book never stays up
-- (bugs.md 2026-09-13). This asserted the opposite while the bug was live.
combat = true
_G.UIErrorsFrame.lines = {}
pressP()
assert(not screen:IsShown(), "P does not open the screen in combat")
assert(not _G.SpellBookFrame:IsShown(), "the stock spellbook never opens in combat")
assert(#_G.UIErrorsFrame.lines == 1, "the press says why, got " .. #_G.UIErrorsFrame.lines)
-- And again: the second press must not sneak the book past the hook either.
pressP()
assert(not screen:IsShown())
assert(not _G.SpellBookFrame:IsShown(), "a second press in combat leaves the book shut")
combat = false

-- --- out of combat only --------------------------------------------------
screen:Hide()
combat = true
SlashCmdList["DCSKILLS"]()
assert(not screen:IsShown(), "/dcskills refuses to open in combat")
combat = false
SlashCmdList["DCSKILLS"]()
assert(screen:IsShown())

-- --- inside an instance: only where the server says (diablocraft-td1h) ---
-- dc_classes.cpp refuses every slot and passive change while the map is
-- instanceable ("Not inside an instance or rift."), except in a Greater Rift
-- whose Guardian is dead. Only the server knows which, so inside an instance the
-- press sends a Request and opens nothing; the Show answer opens the screen when
-- it carries instanceEdits and otherwise says the server's own words (12-ui
-- section 2: no picker that can only lead to a refusal).
local function requestsSince(index)
    local count = 0
    for i = index + 1, #sent do
        if sent[i].aio == "Request" then count = count + 1 end
    end
    return count
end
screen:Hide()
inInstance = true
_G.UIErrorsFrame.lines = {}
local beforeRift = #sent
SlashCmdList["DCSKILLS"]()
assert(not screen:IsShown(), "/dcskills does not open inside an instance by itself")
assert(requestsSince(beforeRift) == 1, "the press asks the server, got " .. requestsSince(beforeRift))
assert(#_G.UIErrorsFrame.lines == 0, "and says nothing before the answer")

-- A Nephalem Rift, a dungeon, a Greater Rift with its Guardian alive: no hint.
handlerTable.Show(nil, CATALOGUE)
assert(not screen:IsShown(), "a Show without instanceEdits leaves the screen shut")
assert(#_G.UIErrorsFrame.lines == 1 and _G.UIErrorsFrame.lines[1] == "Not inside an instance or rift.",
       "the refusal is the server's line, got " .. tostring(_G.UIErrorsFrame.lines[1]))
CATALOGUE.instanceEdits = false
handlerTable.Show(nil, CATALOGUE)
assert(not screen:IsShown(), "instanceEdits false leaves the screen shut")
pressP()
assert(not screen:IsShown(), "P does not open the screen inside an instance")
assert(not _G.SpellBookFrame:IsShown(), "and the stock spellbook stays shut")

-- A Greater Rift whose Guardian is dead: the answer opens the screen.
_G.UIErrorsFrame.lines = {}
CATALOGUE.instanceEdits = true
handlerTable.Show(nil, CATALOGUE)
assert(screen:IsShown(), "a Show with instanceEdits opens the screen inside the instance")
assert(#_G.UIErrorsFrame.lines == 0, "with no refusal line")
screen:Hide()
-- A data-only Set with the flag still never opens anything.
handlerTable.Set(nil, CATALOGUE)
assert(not screen:IsShown(), "Set never opens the screen, hint or not")
CATALOGUE.instanceEdits = nil

-- Outside, the old path: the press opens at once and the hint is not needed.
inInstance = false
SlashCmdList["DCSKILLS"]()
assert(screen:IsShown(), "back outside, the screen opens")
screen:Hide()
handlerTable.Show(nil, CATALOGUE)
assert(screen:IsShown(), "and a Show outside opens with no hint")

print('Skills screen checks passed')

-- --- the real shape ------------------------------------------------------
-- The fixture above is small enough to reason about; this one is the Barbarian's
-- actual shape - 23 skills across the six categories (largest is Secondary with
-- five), 19 passives - so the grid, the rune row and the frame height are
-- exercised at the size they will really be.
-- data/d3/barbarian_skills.csv: 4 + 5 + 4 + 4 + 3 + 3 = 23.
local COUNTS = {Primary = 4, Secondary = 5, Defensive = 4, Might = 4, Tactics = 3, Rage = 3}
local full = {level = 70, passiveSlots = 4, activeSlots = 6, passiveSlotCount = 4,
              categories = {"Primary", "Secondary", "Defensive", "Might", "Tactics", "Rage"},
              passiveSlotLevels = {10, 20, 30, 70}, skills = {}, runes = {}, passives = {},
              bar = {}, passiveBar = {}}
local nextId = 81000
for _, category in ipairs({"Primary", "Secondary", "Defensive", "Might", "Tactics", "Rage"}) do
    for index = 1, COUNTS[category] do
        local name = category .. " " .. index
        NAMES[nextId] = name
        ICONS[nextId] = "icon:" .. name
        table.insert(full.skills, {name = name, category = category, unlock = index,
                                   locked = false, spell = nextId})
        nextId = nextId + 1
        full.runes[name] = {}
        for rune = 1, 5 do
            local runeName = name .. " rune " .. rune
            NAMES[nextId] = name .. " - " .. runeName
            ICONS[nextId] = "icon:" .. runeName
            table.insert(full.runes[name], {name = runeName, element = "Fire", unlock = rune,
                                             locked = false, spell = nextId})
            nextId = nextId + 1
        end
    end
end
assert(#full.skills == 23)
for index = 1, 19 do
    local name = "Passive " .. index
    NAMES[nextId] = name
    ICONS[nextId] = "icon:" .. name
    table.insert(full.passives, {name = name, unlock = 10, locked = false, spell = nextId})
    nextId = nextId + 1
end
full.bar[0] = {skill = "Primary 1", rune = "Primary 1 rune 3"}
full.passiveBar[3] = "Passive 19"

combat = false
handlerTable.Show(nil, full)
local fullSlot1 = cells(overviewView, function(f)
    return f.name and f.name.text == "Primary 1"
end)[1]
assert(fullSlot1, "the overview draws the slotted skill")
fullSlot1.scripts.OnClick()
-- Secondary has five skills, the deepest column: 64 + 5 * 62 + 150.
assert(screen:GetHeight() == 524, "23 skills fit without scrolling, got " .. tostring(screen:GetHeight()))
local shownSkills = 0
for _, cell in ipairs(cells(skillChooser, function(f) return f.name and f.name.text ~= "" end)) do
    if cell.name.text:match("^%a+ %d+$") then shownSkills = shownSkills + 1 end
end
assert(shownSkills == 23, "every skill is drawn, got " .. shownSkills)
-- Six rune buttons: No Rune plus the five.
local shownRunes = 0
for _, cell in ipairs(cells(skillChooser, function(f) return f.name and f.name.text ~= "" end)) do
    if cell.name.text == "No Rune" or cell.name.text:match("rune %d$") then
        shownRunes = shownRunes + 1
    end
end
assert(shownRunes == 6, "No Rune plus five, got " .. shownRunes)

cancelButton.scripts.OnClick()
-- The fourth passive slot is open at 70 and holds Passive 19.
local fourth = cells(overviewView, function(f) return f.name and f.name.text == "Passive 19" end)[1]
assert(fourth, "the fourth passive slot is drawn at level 70")
fourth.scripts.OnClick()
-- 19 passives, four per row: five rows.
assert(screen:GetHeight() == 48 + 5 * 56 + 54, "the passive grid is sized to 19, got " .. tostring(screen:GetHeight()))
local shownPassives = 0
for _, cell in ipairs(cells(passiveChooser, function(f) return f.name and f.name.text ~= "" end)) do
    shownPassives = shownPassives + 1
end
assert(shownPassives == 19, "every passive is drawn, got " .. shownPassives)

print('Barbarian-sized layout checks passed')

-- --- category columns come from the payload, not a Barbarian constant -----
-- A later class's categories are a data drop: the client draws whatever names
-- and order the server's dc_class_category list carries. This one is not the
-- Barbarian's set, so it can only pass if no category is hardcoded.
local wizard = {level = 70, passiveSlots = 4, activeSlots = 6, passiveSlotCount = 4,
                categories = {"Force", "Conjuration", "Primary"},
                passiveSlotLevels = {10, 20, 30, 70},
                skills = {}, runes = {}, passives = {}, bar = {}, passiveBar = {}}
for _, spec in ipairs({{"Wave of Force", "Force", 2}, {"Meteor", "Conjuration", 3},
                       {"Magic Missile", "Primary", 1}}) do
    local name, category, unlock = spec[1], spec[2], spec[3]
    NAMES[nextId] = name
    ICONS[nextId] = "icon:" .. name
    table.insert(wizard.skills, {name = name, category = category, unlock = unlock,
                                 locked = false, spell = nextId})
    nextId = nextId + 1
end
combat = false
handlerTable.Show(nil, wizard)
local wizardSlot = cells(overviewView, function(f)
    return f.rune ~= nil and f.badge and f.badge.text == 1
end)[1]
wizardSlot.scripts.OnClick()
local wizardShown = {}
for _, cell in ipairs(cells(skillChooser, function(f) return f.name and f.name.text ~= "" end)) do
    wizardShown[cell.name.text] = true
end
assert(wizardShown["Wave of Force"] and wizardShown["Meteor"] and wizardShown["Magic Missile"],
       "a non-Barbarian category set draws its own skills")
-- One skill per category: one row, 64 + 62 + 150.
assert(screen:GetHeight() == 276, "the grid is sized to the payload's categories, got " .. tostring(screen:GetHeight()))
local labels = {}
for _, child in ipairs(skillChooser.children) do
    if type(child.text) == "string" then labels[child.text] = true end
end
assert(labels["Force"] and labels["Conjuration"] and labels["Primary"],
       "the category headers are the payload's own names")
local third = cells(skillChooser, function(f) return f.name and f.name.text == "Magic Missile" end)[1]
assert(third, "the third payload category still draws a skill")
cancelButton.scripts.OnClick()
handlerTable.Show(nil, full)

print('Server-category layout checks passed')

-- --- slot rules: changed counts and gates, shrink and regrow --------------
-- The catalogue now carries the server's counts and gates. Capture the sixth
-- active and the fourth passive cell the default payload built, shrink to
-- two/two, and check the whole cell - button AND the view-parented name/rune
-- FontStrings - is hidden, then regrow and check it returns.
local sixthActive, passiveCells = nil, {}
for _, frame in ipairs(frames) do
    if frame.parent == overviewView and frame.kind == "Button" then
        if frame.rune then
            if frame.badge.text == 6 then sixthActive = frame end
        else
            passiveCells[#passiveCells + 1] = frame
        end
    end
end
assert(sixthActive and sixthActive:IsShown(), "the sixth active cell is drawn at the default count")
assert(sixthActive.name:IsShown() and sixthActive.rune:IsShown())
assert(#passiveCells == 4, "four passive cells at the default count, got " .. #passiveCells)
local fourthPassive = passiveCells[4]
assert(fourthPassive:IsShown() and fourthPassive.name:IsShown())

local function overviewShown(predicate)
    local count = 0
    for _, frame in ipairs(frames) do
        if frame.parent == overviewView and frame.kind == "Button" and frame:IsShown()
           and predicate(frame) then count = count + 1 end
    end
    return count
end

local shrunk = {level = 70, passiveSlots = 2, activeSlots = 2, passiveSlotCount = 2,
                passiveSlotLevels = {10, 20}, skills = {}, runes = {}, passives = {},
                bar = {}, passiveBar = {}}
handlerTable.Show(nil, shrunk)
assert(overviewShown(function(f) return f.rune ~= nil end) == 2, "two active cells after the shrink")
assert(overviewShown(function(f) return f.rune == nil end) == 2, "two passive cells after the shrink")
assert(not sixthActive:IsShown(), "the sixth active cell button is hidden")
assert(not sixthActive.name:IsShown(), "and its name FontString is hidden")
assert(not sixthActive.rune:IsShown(), "and its rune FontString is hidden")
assert(not fourthPassive:IsShown(), "the fourth passive cell button is hidden")
assert(not fourthPassive.name:IsShown(), "and its name FontString is hidden")

-- A changed gate is what the client draws, not the default 70.
handlerTable.Show(nil, {level = 70, passiveSlots = 1, activeSlots = 2, passiveSlotCount = 2,
                        passiveSlotLevels = {10, 90}, skills = {}, runes = {}, passives = {},
                        bar = {}, passiveBar = {}})
local gated = passiveCells[2]
assert(gated:IsShown() and gated.name.text == "|cff808080Opens at 90|r",
       "the second gate follows the payload, got " .. tostring(gated.name.text))
assert(gated.scripts.OnClick == nil, "a closed gate leads nowhere")

-- Regrow to the default shape: the hidden cell and its labels come back.
handlerTable.Show(nil, CATALOGUE)
assert(sixthActive:IsShown(), "the sixth active cell returns")
assert(sixthActive.name:IsShown() and sixthActive.rune:IsShown(), "with its labels")
assert(fourthPassive:IsShown() and fourthPassive.name:IsShown(), "and the fourth passive cell returns")

-- passive_skill_slots 5 with only four gate rows: the fifth slot is locked and
-- no gate is invented (the server carries only slots that have a row).
handlerTable.Show(nil, {level = 70, passiveSlots = 4, activeSlots = 6, passiveSlotCount = 5,
                        passiveSlotLevels = {10, 20, 30, 70}, skills = {}, runes = {},
                        passives = {}, bar = {}, passiveBar = {}})
local passives5 = {}
for _, frame in ipairs(frames) do
    if frame.parent == overviewView and frame.kind == "Button" and not frame.rune then
        passives5[#passives5 + 1] = frame
    end
end
assert(#passives5 == 5, "five passive cells for count 5, got " .. #passives5)
assert(passives5[5]:IsShown() and passives5[5].name.text == "|cff808080Locked|r",
       "the gate-less fifth passive slot is locked, got " .. tostring(passives5[5].name.text))

-- `.dc tunables set combat active_skill_slots 5`, reopen: five active cells.
handlerTable.Show(nil, {level = 70, passiveSlots = 4, activeSlots = 5, passiveSlotCount = 4,
                        passiveSlotLevels = {10, 20, 30, 70}, skills = {}, runes = {},
                        passives = {}, bar = {}, passiveBar = {}})
assert(overviewShown(function(f) return f.rune ~= nil end) == 5,
       "five active cells after active_skill_slots 5 and reopen")

-- A missing gate locks exactly its own slot, never shifting another: gate 1
-- absent with gates 2-4 open at level 70 locks slot 1 and opens 2-4, even
-- though the payload's open total is 3 (PM review 2026-09-19).
handlerTable.Show(nil, {level = 70, passiveSlots = 3, activeSlots = 6, passiveSlotCount = 4,
                        passiveSlotLevels = {[2] = 10, [3] = 20, [4] = 30},
                        skills = {}, runes = {}, passives = {}, bar = {}, passiveBar = {}})
assert(passiveCells[1].name.text == "|cff808080Locked|r",
       "the gate-less first passive slot is locked, got " .. tostring(passiveCells[1].name.text))
assert(passiveCells[1].scripts.OnClick == nil, "and leads nowhere")
for slot = 2, 4 do
    assert(passiveCells[slot].scripts.OnClick ~= nil,
           "passive slot " .. slot .. " keeps its identity and stays open")
end

-- A non-monotonic gate locks the middle slot it names, not a prefix.
handlerTable.Show(nil, {level = 70, passiveSlots = 3, activeSlots = 6, passiveSlotCount = 4,
                        passiveSlotLevels = {10, 90, 30, 70},
                        skills = {}, runes = {}, passives = {}, bar = {}, passiveBar = {}})
assert(passiveCells[1].scripts.OnClick ~= nil, "the first slot is open")
assert(passiveCells[2].name.text == "|cff808080Opens at 90|r",
       "the second slot's own gate wins, got " .. tostring(passiveCells[2].name.text))
assert(passiveCells[2].scripts.OnClick == nil, "the level-90 second slot is locked")
assert(passiveCells[3].scripts.OnClick ~= nil and passiveCells[4].scripts.OnClick ~= nil,
       "the third and fourth slots are still open")

-- ---------------------------------------------------------- the version mix

-- New AIO code against an addon that carries the shared table: the window must
-- READ it rather than its own copy. The other mix - these files older than the
-- addon, each with its own copy - is the same values, which the pinning above and
-- test_character_sheet.lua's check of the sheet both prove.
_G.Diablocraft = {Style = {backdrop = {bgFile = "Interface\\Marker", edgeFile = "Interface\\Marker"}}}
dofile(SOURCE)
local sharedWindow = _G.DiablocraftSkillbarFrame
assert(sharedWindow ~= screen, "the second load builds a second window")
assert(sharedWindow.backdrop.bgFile == "Interface\\Marker",
    "a window loaded with the addon's shared DC.Style must use it, got "
        .. tostring(sharedWindow.backdrop.bgFile))
_G.Diablocraft = nil

-- The skills screen builds no secure action button: no frame it made ever set a
-- secure attribute (the old stub enforced this by erroring on SetAttribute).
for _, f in ipairs(frames) do
    assert(f.attributes == nil, "the skills screen must not create secure action attributes")
end

-- The two skill overlays are named slots when the addon publishes DC.SetArt:
-- dc_skillbar draws them through the addon, which is what lets a skin replace
-- them (SKINNING.md, part C.3). The overlay texture itself is the addon's to own.
local skillSlots = {}
_G.Diablocraft = {
    Style = {backdrop = {bgFile = "Interface\\Marker", edgeFile = "Interface\\Marker"}},
    SetArt = function(texture, slot)
        skillSlots[#skillSlots + 1] = slot
        texture:SetTexture("slot:" .. slot)
    end,
}
dofile(SOURCE)
handlerTable.Show(nil, CATALOGUE)
local sawSlotted, sawChosen = false, false
for _, slot in ipairs(skillSlots) do
    if slot == "skill-slotted" then sawSlotted = true end
    if slot == "skill-chosen" then sawChosen = true end
end
assert(sawSlotted and sawChosen,
    "with the addon the overlays come from the skill-slotted and skill-chosen slots")
_G.Diablocraft = nil

print('Slot-rule count and shrink checks passed')
