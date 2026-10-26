-- luacheck: ignore 111 112 113 121 122 431
-- Run from repo root with `lua mod-diablocraft/scripts/tests/world/test_lfg_probe.lua`.
-- The Dungeon Finder probe (diablocraft-v1sw4), both halves against stubs.
-- Addon (client-patch/addons/Torment/LFG.lua, with the generated LFGRows.lua): the type dropdown, set up by its own
-- OnShow as the XML binds it, lists the server's random rows and no "Specific Dungeons" entry, a locked row greyed with
-- the stock reason; the calendar's dungeon list loses our rows at its tail and only there (diablocraft-1tu05); the Specific
-- list and the Raid Browser hide when shown and the Raid Browser button hides with the raid tab, the file loading
-- whole when those frames are absent; Find Group on a Torment entry
-- joins exactly its hidden row and says so; Shift-click, a non-Torment type and leaving a queue keep the stock click.
-- Server (mod-diablocraft/lua/aio/dc_lfg_probe.lua): the CMSG_LFG_JOIN hook reads the slots the way
-- LFGJoin::Read does and tells a GM which rows came, with their type; a player who is not a GM is told nothing.
-- Not covered: what the client really draws or sends; that is the test sheet's walk.

local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()

local failures = 0
local function check(cond, what)
    if not cond then failures = failures + 1; print("FAIL: " .. what) end
end

-- ------------------------------------------------------------------ the stock client the addon hooks
local chat, calls, stockClicks = {}, {}, 0
_G.DEFAULT_CHAT_FRAME = {AddMessage = function(_, text) chat[#chat + 1] = text end}
_G.EXPANSION_LEVEL = 2
_G.YOU_MAY_NOT_QUEUE_FOR_THIS = "You may not queue for this."
_G.UnitLevel = function() return 70 end
local dbc = {  -- GetLFGDungeonInfo: name, typeID, minLevel, maxLevel, _, _, _, expansion
    [1000] = {"Bounties", 6, 70, 70, 70, 70, 70, 2}, [1001] = {"Nephalem Rifts", 6, 70, 70, 70, 70, 70, 2},
    [1002] = {"Greater Rifts", 6, 70, 70, 70, 70, 70, 2}, [1101] = {"Nephalem Rifts", 1, 70, 70, 70, 70, 70, 2},
    [258] = {"Random Classic Dungeon", 6, 0, 0, 55, 15, 58, 0},
}
local random, locked = {258, 1000, 1001, 1002}, {[1002] = true}
_G.GetNumRandomDungeons = function() return #random end
_G.GetLFGRandomDungeonInfo = function(i) return random[i], dbc[random[i]][1] end
_G.GetLFGDungeonInfo = function(id) if dbc[id] then return unpack(dbc[id]) end end
_G.IsLFGDungeonJoinable = function(id) return not locked[id] end
_G.LFDConstructDeclinedMessage = function(id) return "locked " .. id end
_G.LFDQueueFrameTypeDropDownButton_OnClick = function() end
local mode = nil
_G.GetLFGMode = function() return mode end
local shift = false
_G.IsShiftKeyDown = function() return shift end
_G.ClearAllLFGDungeons = function() calls[#calls + 1] = "clear" end
_G.SetLFGDungeon = function(id) calls[#calls + 1] = "set " .. id end
_G.JoinLFG = function() calls[#calls + 1] = "join" end
local hidden = {}
_G.HideUIPanel = function(frame) hidden[#hidden + 1] = frame; frame:Hide() end

local added = {}
_G.UIDropDownMenu_CreateInfo = function() return {} end
_G.UIDropDownMenu_AddButton = function(info)
    local copy = {}
    for k, v in pairs(info) do copy[k] = v end
    added[#added + 1] = copy
end
_G.UIDropDownMenu_Initialize = function(frame, fn) added = {}; fn() end
_G.UIDropDownMenu_SetSelectedValue = function() end
_G.LFDQueueFrameTypeDropDown_SetUp = function(self)  -- the stock one, with its Specific entry
    _G.UIDropDownMenu_Initialize(self, function() _G.UIDropDownMenu_AddButton({text = "Specific Dungeons", value = "specific"}) end)
end

_G.LFDQueueFrame = CreateFrame("Frame", "LFDQueueFrame")
local dropdown = CreateFrame("Frame", "LFDQueueFrameTypeDropDown")
-- LFDFrame.xml:1014 <OnShow function="LFDQueueFrameTypeDropDown_SetUp"/>: the XML binds the stock function itself
-- at load, so a hook on the global never runs from here (the designer's Broken windows-v1sw4-dropdown-three, 1tu05).
dropdown:SetScript("OnShow", LFDQueueFrameTypeDropDown_SetUp)
-- CalendarEventGetTextures: title, texture, expansion, difficulty name per entry, in the client's own order.
local calendar = {"Utgarde Keep", "UTGARDE", 2, "", "Halls of Stone", "HALLSOFSTONE", 2, ""}
_G.CalendarEventGetTextures = function() return unpack(calendar) end
CreateFrame("Frame", "LFDQueueFrameSpecific")
CreateFrame("Frame", "LFRParentFrame")
-- The stock names (FrameXML RaidFrame.xml:159, 174): the button is RaidFrameNotInRaid's $parentRaidBrowserButton.
CreateFrame("Frame", "RaidFrame")
CreateFrame("Button", "RaidFrameNotInRaidRaidBrowserButton")
UIParent:CreateFontString("RaidFrameRaidBrowserDescription")
local find = CreateFrame("Button", "LFDQueueFrameFindGroupButton")
find:SetScript("OnClick", function() stockClicks = stockClicks + 1 end)

dofile("client-patch/addons/Torment/LFGRows.lua")
local loaded, err = pcall(dofile, "client-patch/addons/Torment/LFG.lua")
check(loaded, "LFG.lua loads with the stock frames (Nightly 83 broke here): " .. tostring(err))

-- ------------------------------------------------------------------ the dropdown
LFDQueueFrame.type = 1001
dropdown:Show()
local texts = {}
for _, info in ipairs(added) do texts[#texts + 1] = info.text end
check(table.concat(texts, "|") == "Bounties|Nephalem Rifts|Greater Rifts",
    "dropdown is the three Torment rows, got " .. table.concat(texts, "|"))
check(added[2].checked == true and added[1].checked == false, "the current type is checked")
check(added[3].disabled == 1 and added[3].tooltipText == "locked 1002" and added[3].func == nil,
    "a locked row is greyed with the stock reason")
check(added[1].func == LFDQueueFrameTypeDropDownButton_OnClick and not added[1].disabled, "a joinable row is clickable")

-- ------------------------------------------------------------------ the calendar's dungeon list
local function list(...) return table.concat({...}, "|", 1, select("#", ...)) end
local stock = list(unpack(calendar))
check(list(CalendarEventGetTextures(1)) == stock, "a stock-only list is untouched: " .. list(CalendarEventGetTextures(1)))
calendar[#calendar + 1], calendar[#calendar + 2], calendar[#calendar + 3], calendar[#calendar + 4] = "Nephalem Rifts", "UTGARDE", 2, ""
check(list(CalendarEventGetTextures(1)) == stock, "our row at the tail is cut: " .. list(CalendarEventGetTextures(1)))
table.insert(calendar, 1, ""); table.insert(calendar, 1, 2); table.insert(calendar, 1, "UTGARDE"); table.insert(calendar, 1, "Bounties")
check(list(CalendarEventGetTextures(1)) == list(unpack(calendar, 1, 12)),
    "our row before a stock one stays, so no stock entry moves: " .. list(CalendarEventGetTextures(1)))

-- ------------------------------------------------------------------ hidden frames
LFDQueueFrameSpecific:Show()
check(not LFDQueueFrameSpecific:IsShown(), "the Specific list hides when shown")
LFRParentFrame:Show()
check(not LFRParentFrame:IsShown() and hidden[1] == LFRParentFrame, "the Raid Browser closes through HideUIPanel")
RaidFrameNotInRaidRaidBrowserButton:Show()
RaidFrameRaidBrowserDescription:Show()
RaidFrame:Show()
check(not RaidFrameNotInRaidRaidBrowserButton:IsShown() and not RaidFrameRaidBrowserDescription:IsShown(),
    "the Raid Browser button and its text hide when the raid tab shows")

-- ------------------------------------------------------------------ Find Group
local click = find:GetScript("OnClick")
click(find, "LeftButton")
check(table.concat(calls, ",") == "clear,set 1101,join", "Find Group joins the hidden row, got " .. table.concat(calls, ","))
check(stockClicks == 0, "the stock click did not run as well")
check(chat[1] == "Torment Dungeon Finder probe: Find Group joins row 1101 (Nephalem Rifts)", "chat says which row: " .. tostring(chat[1]))
LFDQueueFrame.type = 1000
calls, chat = {}, {}
click(find, "LeftButton")
check(chat[1] == "Torment Dungeon Finder probe: Find Group joins row 1100 (not in this client's LFGDungeons.dbc)",
    "a hidden row the client lacks is named as missing: " .. tostring(chat[1]))
for _, case in ipairs({{"shift", function() shift = true end}, {"queued", function() mode = "queued" end},
                       {"not ours", function() LFDQueueFrame.type = "specific" end}}) do
    shift, mode, LFDQueueFrame.type, calls = false, nil, 1001, {}
    case[2]()
    local before = stockClicks
    click(find, "LeftButton")
    check(stockClicks == before + 1 and #calls == 0, case[1] .. " keeps the stock click")
end

-- ------------------------------------------------------------------ the raid frames absent at load
-- Loaded again with neither frame there: the file must still load to its end and the raid tab still open.
RaidFrame:Hide()
_G.RaidFrameNotInRaidRaidBrowserButton, _G.RaidFrameRaidBrowserDescription = nil, nil
local stockFind = find:GetScript("OnClick")
loaded, err = pcall(dofile, "client-patch/addons/Torment/LFG.lua")
check(loaded and find:GetScript("OnClick") ~= stockFind, "LFG.lua loads to its end without the raid frames: " .. tostring(err))
check(pcall(RaidFrame.Show, RaidFrame), "the raid tab opens without the raid frames")

-- ------------------------------------------------------------------ the server readout
local registered = {}
_G.RegisterPacketEvent = function(opcode, event, fn) registered[#registered + 1] = {opcode, event, fn} end
local logged = {}
_G.PrintError = function(line) logged[#logged + 1] = line end
dofile("mod-diablocraft/lua/aio/dc_lfg_probe.lua")
check(#registered == 1 and registered[1][1] == 0x35C and registered[1][2] == 5, "one receive hook on CMSG_LFG_JOIN")

local function packet(values)  -- the reads in LFGJoin::Read order; a wrong width or order trips here
    local i = 0
    local function read(kind) return function()
        i = i + 1
        assert(values[i] and values[i][1] == kind, ("read %d is %s, packet has %s"):format(i, kind, tostring(values[i] and values[i][1])))
        return values[i][2]
    end end
    return {ReadULong = read("u32"), ReadUByte = read("u8")}
end
local function player(rank)
    local p = {told = {}}
    function p:GetGMRank() return rank end
    function p:GetName() return "the designer" end
    function p:SendBroadcastMessage(line) self.told[#self.told + 1] = line end
    return p
end
local gm = player(3)
registered[1][3](5, packet({{"u32", 8}, {"u8", 0}, {"u8", 0}, {"u8", 2}, {"u32", 1101 + 1 * 0x1000000}, {"u32", 1001 + 6 * 0x1000000}}), gm)
local want = "[LFG probe] the designer sent CMSG_LFG_JOIN: roles 8, 2 row(s): 1101 (type 1), 1001 (type 6)"
check(gm.told[1] == want and logged[1] == want, "a GM is told the rows and their types: " .. tostring(gm.told[1]))
local nobody = player(0)
registered[1][3](5, packet({}), nobody)
check(#nobody.told == 0 and #logged == 1, "a player who is not a GM is told nothing")
registered[1][3](5, packet({{"u32", 8}, {"u8", 0}, {"u8", 0}, {"u8", 0}}), gm)
check(gm.told[2] == "[LFG probe] the designer sent CMSG_LFG_JOIN: roles 8, 0 row(s): none", "an empty join says none")

if failures > 0 then
    print(failures .. " check(s) failed")
    os.exit(1)
end
print("test_lfg_probe: all checks passed")
