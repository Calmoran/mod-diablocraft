-- luacheck: globals TormentLFGRows UIDropDownMenu_CreateInfo UIDropDownMenu_AddButton UIDropDownMenu_Initialize
-- luacheck: globals UIDropDownMenu_SetSelectedValue GetNumRandomDungeons GetLFGRandomDungeonInfo GetLFGDungeonInfo
-- luacheck: globals EXPANSION_LEVEL IsLFGDungeonJoinable LFDQueueFrameTypeDropDownButton_OnClick LFDQueueFrame
-- luacheck: globals YOU_MAY_NOT_QUEUE_FOR_THIS LFDConstructDeclinedMessage LFDQueueFrameSpecific LFRParentFrame
-- luacheck: globals RaidFrame LFDQueueFrameFindGroupButton GetLFGMode LFDQueueFrameTypeDropDown CalendarEventGetTextures
-- luacheck: globals ClearAllLFGDungeons SetLFGDungeon JoinLFG
-- Dungeon Finder probe, addon half: step (a) of docs/research/lfg-takeover.md 10.5.
-- The stock frame (micro button, I key, minimap eye) stays as it is; this only takes away what Torment
-- will not use and lets Find Group join an activity's hidden key row:
--   * the type dropdown lists the random rows the server sends, without "Specific Dungeons";
--   * the Specific list never shows, nor does the Raid Browser (its Social-frame button is hidden);
--   * the calendar's dungeon list does not offer our rows;
--   * Find Group on a Torment entry joins that entry's hidden row (LFGRows.lua, generated from
--     data/d3/lfg_activities.csv) and says so in chat; Shift-click keeps the stock join of the
--     visible row, so the two can be compared. Leaving the queue is the stock path.
-- The re-skin (labels, role controls, art) is step (d).
local rows = TormentLFGRows

-- The stock initializer (LFDFrame.lua:707-747) without its first entry.
local function initialize()
    local info = UIDropDownMenu_CreateInfo()
    local level = UnitLevel("player")
    for i = 1, GetNumRandomDungeons() do
        local id, name = GetLFGRandomDungeonInfo(i)
        local _, _, minLevel, maxLevel, _, _, _, expansion = GetLFGDungeonInfo(id)
        if level >= minLevel and level <= maxLevel and EXPANSION_LEVEL >= expansion then
            info.text, info.value, info.isTitle = name, id, nil
            if IsLFGDungeonJoinable(id) then
                info.func, info.disabled, info.checked = LFDQueueFrameTypeDropDownButton_OnClick, nil, LFDQueueFrame.type == id
                info.tooltipWhileDisabled, info.tooltipOnButton, info.tooltipTitle, info.tooltipText = nil, nil, nil, nil
            else
                info.func, info.disabled, info.checked = nil, 1, nil
                info.tooltipWhileDisabled, info.tooltipOnButton = 1, 1
                info.tooltipTitle, info.tooltipText = YOU_MAY_NOT_QUEUE_FOR_THIS, LFDConstructDeclinedMessage(id)
            end
            UIDropDownMenu_AddButton(info)
        end
    end
end

-- The dropdown sets itself up on every show, and LFDFrame.xml:1014 binds the stock SetUp itself (OnShow function=),
-- so a hook on the global never ran. Hooked on the frame, ours replaces the initializer after it.
LFDQueueFrameTypeDropDown:HookScript("OnShow", function(self)
    UIDropDownMenu_Initialize(self, initialize)
    UIDropDownMenu_SetSelectedValue(self, LFDQueueFrame.type)
end)

-- The calendar's Dungeon picker lists the client's dungeon rows, our hidden ones with them. It sends
-- back a position in that list, so only a tail can go without moving a stock entry: ours are the DBC's last rows, and
-- anywhere else the list is left whole.
local stockTextures = CalendarEventGetTextures
local function pack(...) return {n = select("#", ...), ...} end
function CalendarEventGetTextures(...)
    local ours = {}
    for visible, hidden in pairs(rows) do
        for _, id in ipairs({visible, hidden}) do
            local name = GetLFGDungeonInfo(id)
            if name then ours[name] = true end
        end
    end
    local list = pack(stockTextures(...))
    local n = list.n
    while n >= 4 and ours[list[n - 3]] do n = n - 4 end  -- four values per entry, the title first
    return unpack(list, 1, n)
end

LFDQueueFrameSpecific:HookScript("OnShow", function(self) self:Hide() end)
LFRParentFrame:HookScript("OnShow", function(self) HideUIPanel(self) end)
-- The stock button is RaidFrameNotInRaid's "$parentRaidBrowserButton" (FrameXML RaidFrame.xml:174), so there is
-- no RaidFrameRaidBrowserButton (a login error when that name was used). Hidden when the raid tab shows and
-- only if present, so a missing frame can never stop the rest of this file.
RaidFrame:HookScript("OnShow", function()
    for _, name in ipairs({"RaidFrameNotInRaidRaidBrowserButton", "RaidFrameRaidBrowserDescription"}) do
        if _G[name] then _G[name]:Hide() end
    end
end)

local stockClick = LFDQueueFrameFindGroupButton:GetScript("OnClick")
LFDQueueFrameFindGroupButton:SetScript("OnClick", function(self, ...)
    local hidden = rows[LFDQueueFrame.type]
    local mode = GetLFGMode()
    if not hidden or IsShiftKeyDown() or mode == "queued" or mode == "listed" or mode == "rolecheck" then
        return stockClick(self, ...)
    end
    DEFAULT_CHAT_FRAME:AddMessage(("Torment Dungeon Finder probe: Find Group joins row %d (%s)")
        :format(hidden, GetLFGDungeonInfo(hidden) or "not in this client's LFGDungeons.dbc"))
    ClearAllLFGDungeons()
    SetLFGDungeon(hidden)
    JoinLFG()
end)
