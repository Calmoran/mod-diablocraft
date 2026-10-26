-- luacheck: globals DCThrottle
--[[
World of DiabloCraft - the D3 skills screen (04-classes §3, 12-ui §2).

The screen replaces the spellbook with D3's three views: overview, pick a skill
and its rune, and pick a passive. It uses stock WoW textures (12-ui U1 stage 1;
no D3 art). The stock action bar casts every selected shell directly.
]]

local AIO = AIO or require("AIO")

-- luacheck: globals DCTunables

-- Six active / four passive slots and their unlock gates are the published
-- character rules, read from dc_tunables category combat and
-- shipped to the client in the catalogue (docs/contracts/skillbar-messages.md).
-- Slot indices are unaffected: slot n stays slot n (src/classes/dc_classes.h).
-- The client holds NO gameplay default: before the
-- catalogue arrives the toggle opens a loading state and draws nothing. The
-- server half's DCTunables.Or fallback is the project-wide logged-once
-- pre-migration value; UI sizes, positions and colours stay file constants.

if AIO.AddAddon() then
    -- ================= server =================
    local handlers = AIO.AddHandlers("DiablocraftSkillbar", {})

    -- One gate per slot, only when the row actually exists: an absent
    -- passive_slot_N_unlock_level means that slot is locked, on both sides
    -- There is no fixed four-row ceiling - a fifth row
    -- added to the sheet is consumed the moment it exists - and no gate is
    -- ever invented. The catalogue therefore carries only the slots that have a
    -- row, so the client never guesses. C++ does the same through
    -- DC::Tunables::Has / the unlock sentinel.
    local function slotRules()
        local passiveSlotCount = DCTunables.Or("combat", "passive_skill_slots", 4)
        local passiveSlotLevels = {}
        for slot = 1, passiveSlotCount do
            local name = "passive_slot_" .. slot .. "_unlock_level"
            if DCTunables.Has("combat", name) then
                passiveSlotLevels[slot] = DCTunables.Get("combat", name)
            end
        end
        return {
            activeSlots = DCTunables.Or("combat", "active_skill_slots", 6),
            passiveSlotCount = passiveSlotCount,
            passiveSlotLevels = passiveSlotLevels,
        }
    end

    -- Everything the screen needs, straight from the dc_ tables and the
    -- character's own bar. Unlock state is derived from level (K1/K2).
    local function catalogue(player)
        local level = player:GetLevel()
        local rules = slotRules()
        local skills, runes, passives, bar, passiveBar = {}, {}, {}, {}, {}

        -- The class-keyed tables resolved through dc_class_map by the player's
        -- WoW class. No class is named in code, so a later class is data
        -- only; a WoW class with no dc_class_map row returns no rows from any
        -- query and the window draws empty. The catalogue's own spell_id is the
        -- shell the slot casts and the icon the client reads with GetSpellInfo,
        -- so the old 81000-81156 name-to-id table is gone.
        local wow = player:GetClass()
        local categories = {}
        local result

        -- Skills: D3's category order from dc_class_category, then unlock, then
        -- name (the window's in-column sort). name is the key the saved bar and the
        -- picker's messages use; shown is the record's own name, which is what the
        -- player reads (two classes can show one name under two keys: Earthquake).
        result = WorldDBQuery(
            "SELECT c.spell_id, l.skill_name, l.category, c.unlock_level, l.element, "
            .. "COALESCE(NULLIF(s.Name_Lang_enUS, ''), l.skill_name) "
            .. "FROM dc_class_map m "
            .. "JOIN dc_class_catalogue c ON c.class_id = m.class_id AND c.rune_id = 0 "
            .. "JOIN dc_class_label l ON l.spell_id = c.spell_id AND l.class_id = c.class_id "
            .. "JOIN dc_class_category g ON g.class_id = c.class_id AND g.category = l.category "
            .. "LEFT JOIN spell_dbc s ON s.ID = c.spell_id "
            .. "WHERE m.wow_class_id = " .. wow
            .. " ORDER BY g.display_order, c.unlock_level, l.skill_name")
        if result then
            repeat
                local unlock = result:GetUInt32(3)
                table.insert(skills, {
                    name = result:GetString(1),
                    shown = result:GetString(5),
                    category = result:GetString(2),
                    unlock = unlock,
                    locked = level < unlock,
                    spell = result:GetUInt32(0),
                    element = result:GetString(4),
                })
            until not result:NextRow()
        end

        -- Runes: c.rune_id <> 0; l.skill_name is the parent skill's name (the
        -- key the client stores them under) and l.element is the rune's colour.
        result = WorldDBQuery(
            "SELECT c.spell_id, l.skill_name, l.rune_name, l.element, c.unlock_level "
            .. "FROM dc_class_map m "
            .. "JOIN dc_class_catalogue c ON c.class_id = m.class_id AND c.rune_id <> 0 "
            .. "JOIN dc_class_label l ON l.spell_id = c.spell_id AND l.class_id = c.class_id "
            .. "WHERE m.wow_class_id = " .. wow
            .. " ORDER BY l.skill_name, c.unlock_level")
        if result then
            repeat
                local skill = result:GetString(1)
                local unlock = result:GetUInt32(4)
                runes[skill] = runes[skill] or {}
                table.insert(runes[skill], {
                    name = result:GetString(2),
                    element = result:GetString(3),
                    unlock = unlock,
                    locked = level < unlock,
                    spell = result:GetUInt32(0),
                })
            until not result:NextRow()
        end

        -- Passives: dc_class_passive_label has no class_id; join through
        -- dc_class_passive. name is the key the saved bar and the picker's messages
        -- use; shown is the record's own name, which is what the player reads (two
        -- classes can show one name under two keys).
        result = WorldDBQuery(
            "SELECT p.spell_id, pl.passive_name, p.unlock_level, "
            .. "COALESCE(NULLIF(s.Name_Lang_enUS, ''), pl.passive_name) "
            .. "FROM dc_class_map m "
            .. "JOIN dc_class_passive p ON p.class_id = m.class_id "
            .. "JOIN dc_class_passive_label pl ON pl.spell_id = p.spell_id "
            .. "LEFT JOIN spell_dbc s ON s.ID = p.spell_id "
            .. "WHERE m.wow_class_id = " .. wow
            .. " ORDER BY p.unlock_level, pl.passive_name")
        if result then
            repeat
                local unlock = result:GetUInt32(2)
                table.insert(passives, {name = result:GetString(1), shown = result:GetString(3), unlock = unlock,
                                        locked = level < unlock, spell = result:GetUInt32(0)})
            until not result:NextRow()
        end

        -- The category columns in D3 order; the client draws them in this order
        -- and names no category itself.
        result = WorldDBQuery(
            "SELECT g.category FROM dc_class_map m "
            .. "JOIN dc_class_category g ON g.class_id = m.class_id "
            .. "WHERE m.wow_class_id = " .. wow .. " ORDER BY g.display_order")
        if result then
            repeat
                table.insert(categories, result:GetString(0))
            until not result:NextRow()
        end

        result = CharDBQuery("SELECT slot, skill, rune FROM dc_character_skillbar WHERE guid=" ..
            player:GetGUIDLow() .. " ORDER BY slot")
        if result then
            repeat
                bar[result:GetUInt32(0)] = {skill = result:GetString(1), rune = result:GetString(2)}
            until not result:NextRow()
        end

        -- The passive slots' chosen passives, so the overview can draw them and
        -- the passive view can highlight the chosen ones. DC::Classes::SetPassive
        -- owns the rules; this is only its state read back.
        result = CharDBQuery("SELECT slot, passive FROM dc_character_passives WHERE guid=" ..
            player:GetGUIDLow() .. " ORDER BY slot")
        if result then
            repeat
                passiveBar[result:GetUInt32(0)] = result:GetString(1)
            until not result:NextRow()
        end

        -- K2: how many passive slots this level has opened, over the configured
        -- count and only the gates that exist; never more than the count.
        local open = 0
        for slot = 1, rules.passiveSlotCount do
            local gate = rules.passiveSlotLevels[slot]
            if gate and level >= gate then open = open + 1 end
        end
        return {skills = skills, runes = runes, passives = passives, categories = categories,
                bar = bar, passiveBar = passiveBar, passiveSlots = open, level = level,
                activeSlots = rules.activeSlots, passiveSlotCount = rules.passiveSlotCount,
                passiveSlotLevels = rules.passiveSlotLevels}
    end

    -- The player's D3 class id from dc_class_map, or nil when the WoW class is
    -- not mapped. No class is named in code; the window and every gated handler
    -- ask this instead of testing a class id.
    local function classId(player)
        local row = WorldDBQuery(
            "SELECT class_id FROM dc_class_map WHERE wow_class_id = " .. player:GetClass())
        if not row then return nil end
        return row:GetUInt32(0)
    end

    -- Only native Whirlwind channels are controlled here; C++ owns all ticks/stops.
    function handlers.Whirlwind(player, action, spell)
        -- constant: generated Whirlwind shell ids over spell_dbc 81000-81156.
        local ids = {[81004]=true, [81043]=true, [81044]=true,
                     [81045]=true, [81046]=true, [81047]=true}
        if not player or not player:IsAlive() then return end
        -- A stop reads no database and is never dropped: a dropped stop would leave
        -- the channel running after the button is let go. It ends only a Whirlwind
        -- channel, so it is harmless for any class.
        if action == "stop" then
            local current = player:GetCurrentSpell(2) -- CURRENT_CHANNELED_SPELL, Unit.h
            if current and ids[current:GetEntry()] then player:InterruptSpell(2, false) end
            return
        end
        if action ~= "start" or not ids[spell] then return end
        -- Security G1: a start reads dc_class_map and the catalogue; drop a flood.
        if not DCThrottle.Allow(player, "skillbar:whirlwind", 5, 10) then return end
        -- Any class mapped in dc_class_map may start this; the ids above are
        -- Whirlwind's own, so for another mapped class (a Wizard) no bar slot
        -- matches, no rune matches, and nothing is cast. A class with no
        -- dc_class_map row has no bar and is refused here.
        if not classId(player) or player:GetCurrentSpell(2) then return end
        local data = catalogue(player)
        for _, slot in pairs(data.bar) do
            if slot.skill == "Whirlwind" then
                if not slot.rune or slot.rune == "" then
                    -- Level from the catalogue (dc_class_catalogue.unlock_level),
                    -- not a literal.
                    local skill
                    for _, row in ipairs(data.skills or {}) do
                        if row.name == "Whirlwind" then skill = row end
                    end
                    if spell == 81004 and skill and not skill.locked then player:CastSpell(player, spell, false) end
                else
                    for _, rune in ipairs(data.runes.Whirlwind or {}) do
                        if rune.name == slot.rune and rune.spell == spell and not rune.locked then
                            player:CastSpell(player, spell, false)
                            return
                        end
                    end
                end
                return
            end
        end
    end

    -- Hold-to-channel: the client observer (Torment/ChannelObserver.lua) sends Channel
    -- "stop" with the spell id of a listed channelled skill whose key or button was let go. It
    -- ends the player's own running channel when that is the spell named, so it is harmless for
    -- any class and reads no database. A "start" is the native cast's and does nothing here.
    function handlers.Channel(player, action, spell)
        if action ~= "stop" or not player or not player:IsAlive() then return end
        local current = player:GetCurrentSpell(2) -- CURRENT_CHANNELED_SPELL, Unit.h
        if current and current:GetEntry() == spell then player:InterruptSpell(2, false) end
    end

    -- A UI hint, never the rule: may the screen open inside the
    -- instance the player stands in? Only in a Greater Rift whose Guardian is dead,
    -- read from the floor the player is on the way C++ GreaterRiftGuardianDead reads
    -- its live run (same instance, same map, mode gr, state complete or closed).
    -- SetSlot and SetPassive still refuse on their own, so a drift between the row and
    -- the C++ run can keep the screen shut or open one the server refuses, never let
    -- an edit through.
    local function instanceEdits(player)
        local instance = player:GetInstanceId()
        if not instance or instance == 0 then return false end
        -- Through dc_rift_floor (rift floors Part F1/F6): dc_rift.instance_id is floor 1's,
        -- so a player on a deeper floor of the run is not found by dc_rift alone.
        local row = CharDBQuery("SELECT f.map_id, r.mode, r.state FROM dc_rift_floor f "
            .. "JOIN dc_rift r ON r.id=f.run_id WHERE f.instance_id=" .. instance
            .. " AND f.closed_at IS NULL ORDER BY f.run_id DESC LIMIT 1")
        if not row or row:GetUInt32(0) ~= player:GetMapId() or row:GetString(1) ~= "gr" then return false end
        local state = row:GetString(2)
        return state == "complete" or state == "closed"
    end

    -- Security G1: catalogue() queries the DB; drop a flood.
    function handlers.Request(player)
        if player and DCThrottle.Allow(player, "skillbar:request", 5, 10) then
            local data = catalogue(player)
            data.instanceEdits = instanceEdits(player)
            AIO.Handle(player, "DiablocraftSkillbar", "Show", data)
        end
    end

    -- Data only, and never opens anything: the screen asks for this after an
    -- Accept so its slots redraw from the server's own view of them.
    -- Security G1: catalogue() queries the DB; drop a flood.
    function handlers.Refresh(player)
        if player and DCThrottle.Allow(player, "skillbar:refresh", 5, 10) then
            AIO.Handle(player, "DiablocraftSkillbar", "Set", catalogue(player))
        end
    end

    -- "Set" delivers the catalogue without opening anything; only a "Show" sent
    -- in answer to the player's own Request opens the screen. Pushing "Show"
    -- here is what made the screen pop on login.
    AIO.AddOnInit(function(msg, player)
        if player then
            msg:Add("DiablocraftSkillbar", "Set", catalogue(player))
        end
    end)
    return
end
-- ================= client =================
local handlers = AIO.AddHandlers("DiablocraftSkillbar", {})
-- No gameplay defaults here: activeSlots,
-- passiveSlotCount, passiveSlotLevels and passiveSlots come only from the
-- server catalogue. Until it arrives the screen shows a loading state and draws
-- no slots; UI sizes and colours are file constants and are not gameplay rules.
local state = {skills = {}, runes = {}, passives = {}, categories = {}, bar = {},
               passiveBar = {}, passiveSlots = 0, level = 1}
local showOverview, showSkillView, showPassiveView, showLoading, render

-- K2. Display only; the server refuses a slot that is not open regardless of
-- what the client draws. The gates themselves arrive in state.passiveSlotLevels.

-- The D3 element palette for this screen's own icons and labels. The stock
-- tooltip renders its own text and rank now; dc_spell_tooltips.lua is inert.
local ELEMENT = {
    physical = {0.95, 0.95, 0.95}, fire = {1, 0.35, 0.1}, cold = {0.35, 0.8, 1},
    lightning = {1, 0.9, 0.2}, poison = {0.4, 0.9, 0.2}, arcane = {0.75, 0.4, 1},
    holy = {1, 0.75, 0.4},
}
local function elementColour(element)
    return ELEMENT[(element or "physical"):lower()] or ELEMENT.physical
end

-- The two client facts from the header, in one place each.
local function spellIcon(spell)
    if not spell then return nil end
    return (select(3, GetSpellInfo(spell)))
end
local function skillByName(name)
    for _, skill in ipairs(state.skills or {}) do
        if skill.name == name then return skill end
    end
end

-- The shell the slot casts: the skill's own when no rune is chosen, the rune's
-- otherwise. Both ids come from the catalogue, which read them out of spell_dbc.
local function slotSpell(entry)
    if not entry or not entry.skill then return nil end
    local skill = skillByName(entry.skill)
    if not skill then return nil end
    if not entry.rune or entry.rune == "" then return skill.spell end
    for _, rune in ipairs(state.runes[entry.skill] or {}) do
        if rune.name == entry.rune then return rune.spell end
    end
    return skill.spell
end

-- ================= the skills screen =================
-- 12-ui U1 stage 1: D3's layout, WoW's own textures. Three views in one frame,
-- exactly one shown at a time.
--
-- The window is the Jeweler's: the stock dialog
-- backdrop and a native close button, no UIPanelDialogTemplate chrome. The look
-- itself is the shared one - the Torment addon's Diablocraft.Style when that
-- addon has it, else this same table and the same two native frames, because the
-- AIO code comes from the server and the addon from the launcher and either can
-- be newer than the other.

local FRAME_W = 560
local WINDOW_BACKDROP = {
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tile = true, tileSize = 32, edgeSize = 32,
    insets = {left = 11, right = 12, top = 12, bottom = 11},
}
local function nativeClose(parent)
    local button = CreateFrame("Button", nil, parent, "UIPanelCloseButton")
    button:SetPoint("TOPRIGHT", parent, "TOPRIGHT", -6, -6)
    return button
end
local function nativeButton(parent, width, label, onClick)
    local button = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    button:SetSize(width, 22)
    button:SetText(label)
    if onClick then button:SetScript("OnClick", onClick) end
    return button
end

-- Member by member, so an addon from before the helper - or one that carries only
-- part of it - still draws the right window.
local shared = Diablocraft and Diablocraft.Style
local STYLE = {
    backdrop = (shared and shared.backdrop) or WINDOW_BACKDROP,
    Close = (shared and shared.Close) or nativeClose,
    Button = (shared and shared.Button) or nativeButton,
}

local frame = CreateFrame("Frame", "DiablocraftSkillbarFrame", UIParent)
frame:SetSize(FRAME_W, 300)
frame:SetPoint("CENTER")
-- The skin-aware panel when the addon has it.
if shared and shared.Panel then shared.Panel(frame) else frame:SetBackdrop(STYLE.backdrop) end
frame:SetFrameStrata("HIGH")
frame:SetMovable(true)
frame:EnableMouse(true)
frame:RegisterForDrag("LeftButton")
frame:SetScript("OnDragStart", frame.StartMoving)
frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
frame:SetScript("OnHide", function() GameTooltip:Hide() end)
frame:Hide()

-- The X the dialog template used to draw, now the native button the Jeweler and
-- the sheet use.
STYLE.Close(frame)

local title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOP", frame, "TOP", 0, -14)
title:SetText("Skills")

local hint = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
hint:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 18, 14)
hint:SetWidth(320)
hint:SetJustifyH("LEFT")

-- One icon button, used by every view. Stock art throughout: the quickslot
-- frame, the square highlight, the action-button border as the "this one is on
-- your bar" mark and the check highlight as "this is what Accept will send".
local function iconButton(parent, size)
    local button = CreateFrame("Button", nil, parent)
    button:SetSize(size, size)
    button:SetNormalTexture("Interface\\Buttons\\UI-Quickslot2")
    -- UI-Quickslot2 is a 64x64 frame whose clear window is about 36/66 of the
    -- art; stock action buttons draw it 66/36 of the button, centred, so the
    -- frame sits outside the icon. Left at the button's own size its opaque
    -- ring covered the icon and showed a smaller copy of it through the window.
    local frameArt = button:GetNormalTexture()
    frameArt:ClearAllPoints()
    frameArt:SetPoint("CENTER", button, "CENTER", 0, -1)
    frameArt:SetSize(size * 66 / 36, size * 66 / 36)
    button:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
    button.icon = button:CreateTexture(nil, "ARTWORK")
    button.icon:SetPoint("TOPLEFT", button, "TOPLEFT", 3, -3)
    button.icon:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -3, 3)
    -- These two overlays are named slots in the Torment addon's Diablocraft.ART
    -- when it is loaded, so a skin can replace them (SKINNING.md, part C.3);
    -- without the addon the stock path stands, exactly as before.
    local STOCK_SLOTTED = "Interface\\Buttons\\UI-ActionButton-Border"
    local STOCK_CHOSEN = "Interface\\Buttons\\CheckButtonHilight"
    local function overlay(texture, slot, stock)
        if Diablocraft and Diablocraft.SetArt then
            Diablocraft.SetArt(texture, slot)
        else
            texture:SetTexture(stock)
        end
    end
    button.slotted = button:CreateTexture(nil, "OVERLAY")
    overlay(button.slotted, "skill-slotted", STOCK_SLOTTED)
    button.slotted:SetBlendMode("ADD")
    button.slotted:SetPoint("TOPLEFT", button, "TOPLEFT", -7, 7)
    button.slotted:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", 7, -7)
    button.slotted:Hide()
    button.chosen = button:CreateTexture(nil, "OVERLAY")
    overlay(button.chosen, "skill-chosen", STOCK_CHOSEN)
    button.chosen:SetBlendMode("ADD")
    button.chosen:SetAllPoints(button)
    button.chosen:Hide()
    button.badge = button:CreateFontString(nil, "OVERLAY", "NumberFontNormalSmall")
    button.badge:SetPoint("TOPRIGHT", button, "TOPRIGHT", -3, -3)
    button:SetScript("OnLeave", function() GameTooltip:Hide() end)
    return button
end

-- Every tooltip on this screen is the stock shell's own; the client renders it
-- from the record (dc_spell_tooltips.lua no longer rewrites it). The lock line
-- is ours.
local function describe(button, spell, lockLevel, extra)
    button:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        if spell then
            GameTooltip:SetHyperlink("spell:" .. spell)
        else
            GameTooltip:SetText(extra or "")
        end
        if lockLevel then
            GameTooltip:AddLine("Unlocked at level " .. lockLevel .. ".", 1, 0.2, 0.2, true)
        end
        if spell and extra then GameTooltip:AddLine(extra, 1, 1, 1, true) end
        GameTooltip:Show()
    end)
end
local function paint(button, entry)
    button.icon:SetTexture(spellIcon(entry and entry.spell))
    button.icon:SetDesaturated((entry and entry.locked) and true or false)
    button.slotted:Hide()
    button.chosen:Hide()
    button.badge:SetText("")
end

-- --- view 1: overview ---------------------------------------------------
local overview = CreateFrame("Frame", nil, frame)
overview:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
overview:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0)

local overviewSlots, overviewPassives = {}, {}

-- The overview cells are built from the slot counts the server sends, not from
-- a client literal (docs/contracts/skillbar-messages.md). Built lazily so a
-- count change (a `.dc tunables set` and refresh) grows or hides cells instead
-- of drawing past the array.
local function ensureOverviewCells()
    local active = state.activeSlots
    for slot = 0, active - 1 do
        local cell = overviewSlots[slot]
        if not cell then
            cell = iconButton(overview, 48)
            cell:SetPoint("TOPLEFT", overview, "TOPLEFT", 22 + slot * 88, -46)
            cell.name = overview:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            cell.name:SetPoint("TOP", cell, "BOTTOM", 0, -3)
            cell.name:SetWidth(84)
            cell.rune = overview:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            cell.rune:SetPoint("TOP", cell.name, "BOTTOM", 0, -1)
            cell.rune:SetWidth(84)
            overviewSlots[slot] = cell
        end
        -- The name and rune FontStrings are parented to the view, not to the
        -- button, so hiding the button alone would leave their text on screen.
        cell:Show()
        cell.name:Show()
        cell.rune:Show()
    end
    for slot, cell in pairs(overviewSlots) do
        if slot >= active then
            cell:Hide()
            cell.name:Hide()
            cell.rune:Hide()
        end
    end

    local passives = state.passiveSlotCount
    for slot = 0, passives - 1 do
        local cell = overviewPassives[slot]
        if not cell then
            cell = iconButton(overview, 40)
            cell:SetPoint("TOPLEFT", overview, "TOPLEFT", 60 + slot * 118, -184)
            cell.name = overview:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            cell.name:SetPoint("LEFT", cell, "RIGHT", 5, 0)
            cell.name:SetWidth(70)
            cell.name:SetJustifyH("LEFT")
            overviewPassives[slot] = cell
        end
        cell:Show()
        cell.name:Show()
    end
    for slot, cell in pairs(overviewPassives) do
        if slot >= passives then
            cell:Hide()
            cell.name:Hide()
        end
    end
end

local passiveHeader = overview:CreateFontString(nil, "OVERLAY", "GameFontNormal")
passiveHeader:SetPoint("TOPLEFT", overview, "TOPLEFT", 22, -160)
passiveHeader:SetText("Passives")

-- --- view 2: pick a skill, then its rune --------------------------------
local skillView = CreateFrame("Frame", nil, frame)
skillView:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
skillView:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0)
skillView:Hide()

local pendingSlot, pendingSkill, pendingRune

-- One column per category, as D3 groups them, so every skill is on screen at
-- once and Elective Mode (K6) is visibly true: nothing here is filtered by which
-- slot is being edited. The columns and their order come from the server's
-- dc_class_category list; the rows are built on demand rather than to a fixed
-- five, because a class's largest category can be larger and a later class (K8)
-- is a data drop that could bring six - a fixed grid would drop the sixth
-- silently.
local SKILL_TOP, SKILL_PITCH = 64, 62
local skillCells, runeCells, categoryLabels = {}, {}, {}

-- One label per category column, built lazily on the first render and named
-- only from the server's ordered list, so a class with different categories
-- draws them with no code change.
local function categoryLabel(column)
    local label = categoryLabels[column]
    if not label then
        label = skillView:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        label:SetPoint("TOPLEFT", skillView, "TOPLEFT", 20 + (column - 1) * 88, -44)
        label:SetWidth(84)
        categoryLabels[column] = label
    end
    return label
end

local function skillCell(column, row)
    local cell = skillCells[column][row]
    if not cell then
        cell = iconButton(skillView, 40)
        cell:SetPoint("TOPLEFT", skillView, "TOPLEFT", 42 + (column - 1) * 88,
                      -SKILL_TOP - (row - 1) * SKILL_PITCH)
        cell.name = skillView:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        cell.name:SetPoint("TOP", cell, "BOTTOM", 0, -2)
        cell.name:SetWidth(84)
        skillCells[column][row] = cell
    end
    return cell
end

local runeHeader = skillView:CreateFontString(nil, "OVERLAY", "GameFontNormal")
runeHeader:SetText("Rune")

for index = 1, 6 do
    local cell = iconButton(skillView, 40)
    cell.name = skillView:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    cell.name:SetPoint("TOP", cell, "BOTTOM", 0, -2)
    cell.name:SetWidth(82)
    cell.name:SetHeight(30)
    cell.name:SetJustifyV("TOP")
    runeCells[index] = cell
end

-- The rune row and the frame's height follow the tallest category column.
local function layoutSkillView(rows)
    local bottom = SKILL_TOP + math.max(rows, 1) * SKILL_PITCH
    runeHeader:ClearAllPoints()
    runeHeader:SetPoint("TOPLEFT", skillView, "TOPLEFT", 20, -(bottom + 6))
    for index = 1, 6 do
        runeCells[index]:ClearAllPoints()
        runeCells[index]:SetPoint("TOPLEFT", skillView, "TOPLEFT",
                                  38 + (index - 1) * 86, -(bottom + 28))
    end
    frame:SetSize(FRAME_W, bottom + 150)
end

-- --- view 3: pick a passive ---------------------------------------------
local passiveView = CreateFrame("Frame", nil, frame)
passiveView:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
passiveView:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0)
passiveView:Hide()

local pendingPassiveSlot, pendingPassive
local passiveCells = {}
for index = 1, 24 do
    local column, row = (index - 1) % 4, math.floor((index - 1) / 4)
    local cell = iconButton(passiveView, 36)
    cell:SetPoint("TOPLEFT", passiveView, "TOPLEFT", 22 + column * 132, -48 - row * 56)
    cell.name = passiveView:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    cell.name:SetPoint("LEFT", cell, "RIGHT", 5, 0)
    cell.name:SetWidth(88)
    cell.name:SetJustifyH("LEFT")
    passiveCells[index] = cell
end

-- --- Accept / Cancel, shared by both chooser views ----------------------
local accept = STYLE.Button(frame, 96, "Accept")
local cancel = STYLE.Button(frame, 96, "Cancel")
cancel:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -20, 14)
accept:SetPoint("RIGHT", cancel, "LEFT", -8, 0)
accept:Hide()
cancel:Hide()

-- ================= sending =================
-- Slotting does not go through AIO at all. Every rule (combat, instance, unlock
-- level, once per bar) lives in DC::Classes::SetSlot / SetPassive, and ALE has
-- no way to call into our C++ from here, so the client sends a plain addon
-- message and DC::Classes::ClassBridge answers it. The gate stays in C++: a
-- client cannot talk its way past SetSlot.
local function sendSlot(slot, skill, rune)
    -- ClassBridge splits on tabs and reads DCSLOT, skill, rune, slot. The client
    -- concatenates prefix and body with a tab, so the prefix is the first field.
    -- The fourth field is what makes this "into THIS slot" rather than "anywhere
    -- free".
    SendAddonMessage("DCSLOT", skill .. "\t" .. (rune or "") .. "\t" .. slot,
                     "WHISPER", UnitName("player"))
end

local function sendPassive(slot, passive)
    SendAddonMessage("DCPASSIVE", slot .. "\t" .. passive, "WHISPER", UnitName("player"))
end

-- A skill dragged from this window and let go over an action-bar well sets that
-- slot. The bar is
-- ElvUI's; ElvUI_Torment names the well the cursor is over, and the drop sends
-- the same DCSLOT the Accept button sends, then asks for a refresh. Nothing is
-- put on the cursor: a native PickupSpell drop writes the action button only,
-- which WriteActionBar then erases, and 3.3.5a's PickupSpell takes a spellbook
-- slot, not a spell id, so the shell spells cannot be picked up that way.
local dragging
local function tormentModule()
    local E = _G.ElvUI and _G.ElvUI[1]
    return E and E.GetModule and E:GetModule("ElvUI_Torment", true)
end
local function barSlotUnderMouse()
    local module = tormentModule()
    if module and module.BarSlotUnderMouse then return module.BarSlotUnderMouse() end
end
local function dropOnBar()
    local skill = dragging
    dragging = nil
    if not skill or not state.activeSlots then return end
    local slot = barSlotUnderMouse()
    if slot == nil or slot < 0 or slot >= state.activeSlots then return end
    sendSlot(slot, skill, "")
    AIO.Handle("DiablocraftSkillbar", "Refresh")
end

-- A skill dragged from one skill well to another on the bar moves there, and onto
-- a taken well the two swap. ElvUI_Torment calls module.OnWellDrag(slot) when a
-- drag that began on well slot+1 ends; the target is the well under the cursor.
-- The native drag is not used: it writes the action button only, which
-- WriteActionBar then erases. A drop anywhere else (the potion and portal wells,
-- off the bar) changes nothing.
--
-- Either way it is one DCSWAP <from> <to> (0-based slots, as DCSLOT's): the server
-- moves or swaps the two wells in one step, so a refusal changes nothing and no
-- skill can be left off the bar. No other drag starts from the send until the next
-- Set or Show arrives (the Refresh sent with it is answered whether the server
-- swapped or refused), so two DCSWAPs never race.
local swapPending

local function moveWell(from, to)
    if not state.bar[from] then return end
    SendAddonMessage("DCSWAP", from .. "\t" .. to, "WHISPER", UnitName("player"))
    swapPending = true
    AIO.Handle("DiablocraftSkillbar", "Refresh")
end

local function dropFromWell(from)
    if _G.ClearCursor then _G.ClearCursor() end
    if InCombatLockdown() or swapPending or not state.activeSlots then return end
    local to = barSlotUnderMouse()
    if to == nil or to == from or to < 0 or to >= state.activeSlots then return end
    moveWell(from, to)
end

-- ================= drawing =================
local function renderOverview()
    title:SetText("Skills")
    hint:SetText("Click a slot to change its skill, rune or passive.")
    ensureOverviewCells()
    for slot = 0, state.activeSlots - 1 do
        local cell, entry = overviewSlots[slot], state.bar[slot]
        local skill = entry and skillByName(entry.skill)
        paint(cell, {spell = slotSpell(entry)})
        cell.badge:SetText(slot + 1)
        cell.name:SetText(entry and entry.skill and (skill and skill.shown or entry.skill) or "|cff808080Empty|r")
        if entry and entry.rune and entry.rune ~= "" then
            local colour = elementColour(nil)
            for _, rune in ipairs(state.runes[entry.skill] or {}) do
                if rune.name == entry.rune then colour = elementColour(rune.element) end
            end
            cell.rune:SetText(entry.rune)
            cell.rune:SetTextColor(colour[1], colour[2], colour[3])
        else
            cell.rune:SetText(skill and "No Rune" or "")
            cell.rune:SetTextColor(0.5, 0.5, 0.5)
        end
        describe(cell, slotSpell(entry), nil, "Click to change this slot.")
        cell:SetScript("OnClick", function() showSkillView(slot) end)
    end
    for slot = 0, state.passiveSlotCount - 1 do
        local cell = overviewPassives[slot]
        -- Per-slot eligibility, never a positional count: a slot is open only
        -- when it has its own gate row and the character meets it, so a missing
        -- or non-monotonic gate locks exactly that slot and shifts no other.
        local gate = (state.passiveSlotLevels or {})[slot + 1]
        local open = gate ~= nil and (state.level or 0) >= gate
        local name = state.passiveBar and state.passiveBar[slot]
        local passive
        for _, row in ipairs(state.passives or {}) do
            if row.name == name then passive = row end
        end
        paint(cell, passive)
        if not open then
            if gate then
                cell.name:SetText("|cff808080Opens at " .. gate .. "|r")
                describe(cell, nil, nil, "This passive slot opens at level " .. gate .. ".")
            else
                cell.name:SetText("|cff808080Locked|r")
                describe(cell, nil, nil, "This passive slot has no unlock level.")
            end
            cell:SetScript("OnClick", nil)
        else
            cell.name:SetText(name and (passive and passive.shown or name) or "|cff808080Empty|r")
            describe(cell, passive and passive.spell, nil, "Click to change this passive.")
            cell:SetScript("OnClick", function() showPassiveView(slot) end)
        end
    end
end

local function renderRunes()
    local skill = pendingSkill and skillByName(pendingSkill)
    local choices = {{name = "", label = "No Rune", spell = skill and skill.spell, locked = false}}
    for _, rune in ipairs(state.runes[pendingSkill or ""] or {}) do
        table.insert(choices, {name = rune.name, label = rune.name, spell = rune.spell,
                               locked = rune.locked, unlock = rune.unlock, element = rune.element})
    end
    for index = 1, 6 do
        local cell, choice = runeCells[index], choices[index]
        if not choice then
            cell:Hide()
            cell.name:SetText("")
        else
            cell:Show()
            paint(cell, choice)
            -- "No Rune" borrows the skill's own icon because that is the shell
            -- the slot would cast; desaturated so it never reads as a rune.
            if choice.name == "" then cell.icon:SetDesaturated(true) end
            local colour = choice.name == "" and {0.7, 0.7, 0.7} or elementColour(choice.element)
            cell.name:SetText(choice.label)
            if choice.locked then
                cell.name:SetTextColor(0.5, 0.5, 0.5)
            else
                cell.name:SetTextColor(colour[1], colour[2], colour[3])
            end
            if choice.name == (pendingRune or "") then cell.chosen:Show() end
            describe(cell, choice.spell, choice.locked and choice.unlock or nil)
            cell:SetScript("OnClick", function()
                if choice.locked then return end
                pendingRune = choice.name
                renderRunes()
            end)
        end
    end
    if pendingSkill then accept:Enable() else accept:Disable() end
end

local function renderSkillView()
    title:SetText("Slot " .. ((pendingSlot or 0) + 1))
    hint:SetText("Elective Mode: any skill may go in any slot.")
    -- Where each skill already sits, so a skill that is on the bar is marked and
    -- the player can see that choosing it here will move it (K6).
    local onBar = {}
    for slot = 0, state.activeSlots - 1 do
        local entry = state.bar[slot]
        if entry and entry.skill then onBar[entry.skill] = slot + 1 end
    end
    local categories = state.categories or {}
    local byCategory = {}
    for _, skill in ipairs(state.skills or {}) do
        byCategory[skill.category] = byCategory[skill.category] or {}
        table.insert(byCategory[skill.category], skill)
    end
    local tallest = 0
    for _, list in pairs(byCategory) do
        if #list > tallest then tallest = #list end
    end
    -- Columns and their names come from the server's ordered dc_class_category
    -- list, so a class with different categories needs no code change.
    for column = 1, #categories do
        categoryLabel(column):SetText(categories[column])
        categoryLabel(column):Show()
        skillCells[column] = skillCells[column] or {}
    end
    for column = #categories + 1, #categoryLabels do
        categoryLabels[column]:Hide()
    end
    for column, cells in pairs(skillCells) do
        if column > #categories then
            for _, cell in pairs(cells) do
                cell:Hide()
                cell.name:SetText("")
            end
        end
    end
    for column = 1, #categories do
        local list = byCategory[categories[column]] or {}
        table.sort(list, function(a, b)
            if a.unlock ~= b.unlock then return a.unlock < b.unlock end
            return a.name < b.name
        end)
        for row = 1, math.max(tallest, #skillCells[column]) do
            local cell, skill = skillCell(column, row), list[row]
            if not skill then
                cell:Hide()
                cell.name:SetText("")
            else
                cell:Show()
                paint(cell, skill)
                cell.name:SetText(skill.shown or skill.name)
                cell.name:SetTextColor(skill.locked and 0.5 or 1, skill.locked and 0.5 or 1,
                                       skill.locked and 0.5 or 1)
                if onBar[skill.name] then
                    cell.slotted:Show()
                    cell.badge:SetText(onBar[skill.name])
                end
                if skill.name == pendingSkill then cell.chosen:Show() end
                describe(cell, skill.spell, skill.locked and skill.unlock or nil)
                cell:SetScript("OnClick", function()
                    if skill.locked then return end
                    if pendingSkill ~= skill.name then
                        pendingSkill = skill.name
                        -- A rune belongs to one skill, so changing the skill
                        -- drops the rune rather than carrying a name that the
                        -- new skill has never heard of.
                        pendingRune = ""
                    end
                    renderSkillView()
                end)
                -- Dragging the skill onto an action-bar well sets that slot; a
                -- locked skill is not draggable.
                cell:RegisterForDrag("LeftButton")
                cell:SetScript("OnDragStart", function()
                    dragging = (not skill.locked) and skill.name or nil
                end)
                cell:SetScript("OnDragStop", function() dropOnBar() end)
            end
        end
    end
    layoutSkillView(tallest)
    renderRunes()
end

local function renderPassiveView()
    title:SetText("Passive " .. ((pendingPassiveSlot or 0) + 1))
    hint:SetText("One passive per open slot.")
    local chosen = {}
    for slot = 0, state.passiveSlotCount - 1 do
        local name = state.passiveBar and state.passiveBar[slot]
        if name then chosen[name] = slot + 1 end
    end
    local list = state.passives or {}
    for index = 1, #passiveCells do
        local cell, passive = passiveCells[index], list[index]
        if not passive then
            cell:Hide()
            cell.name:SetText("")
        else
            cell:Show()
            paint(cell, passive)
            cell.name:SetText(passive.shown or passive.name)
            cell.name:SetTextColor(passive.locked and 0.5 or 1, passive.locked and 0.5 or 1,
                                   passive.locked and 0.5 or 1)
            if chosen[passive.name] then
                cell.slotted:Show()
                cell.badge:SetText(chosen[passive.name])
            end
            if passive.name == pendingPassive then cell.chosen:Show() end
            describe(cell, passive.spell, passive.locked and passive.unlock or nil)
            cell:SetScript("OnClick", function()
                if passive.locked then return end
                pendingPassive = passive.name
                renderPassiveView()
            end)
        end
    end
    if pendingPassive then accept:Enable() else accept:Disable() end
end

-- Which view is up, so a Refresh landing mid-edit redraws the right one and
-- leaves the pending choice alone.
local view = "overview"

-- Before the first payload there is no gameplay data to draw, so the toggle
-- opens this while the Request is in flight. It invents
-- no slot count and shows no slot cells.
function showLoading()
    view = "loading"
    pendingSlot, pendingSkill, pendingRune = nil, nil, nil
    pendingPassiveSlot, pendingPassive = nil, nil
    skillView:Hide()
    passiveView:Hide()
    overview:Hide()
    accept:Hide()
    cancel:Hide()
    title:SetText("Skills")
    hint:SetText("Loading...")
    frame:SetSize(FRAME_W, 120)
end

function render()
    if not (state.activeSlots and state.passiveSlotCount and state.passiveSlotLevels) then
        showLoading()
    elseif view == "skill" then
        renderSkillView()
    elseif view == "passive" then
        renderPassiveView()
    else
        renderOverview()
    end
end

function showOverview()
    view = "overview"
    pendingSlot, pendingSkill, pendingRune = nil, nil, nil
    pendingPassiveSlot, pendingPassive = nil, nil
    skillView:Hide()
    passiveView:Hide()
    accept:Hide()
    cancel:Hide()
    overview:Show()
    frame:SetSize(FRAME_W, 290)
    renderOverview()
end

function showSkillView(slot)
    local entry = state.bar[slot]
    view = "skill"
    pendingSlot = slot
    pendingSkill = entry and entry.skill or nil
    pendingRune = entry and entry.rune or ""
    overview:Hide()
    passiveView:Hide()
    skillView:Show()
    accept:Show()
    cancel:Show()
    renderSkillView()   -- sizes the frame from the tallest category column
end

function showPassiveView(slot)
    view = "passive"
    pendingPassiveSlot = slot
    pendingPassive = state.passiveBar and state.passiveBar[slot] or nil
    overview:Hide()
    skillView:Hide()
    passiveView:Show()
    accept:Show()
    cancel:Show()
    local rows = math.ceil(#(state.passives or {}) / 4)
    frame:SetSize(FRAME_W, 48 + math.max(rows, 1) * 56 + 54)
    renderPassiveView()
end

cancel:SetScript("OnClick", showOverview)
accept:SetScript("OnClick", function()
    if view == "skill" and pendingSkill then
        sendSlot(pendingSlot, pendingSkill, pendingRune or "")
    elseif view == "passive" and pendingPassive then
        sendPassive(pendingPassiveSlot, pendingPassive)
    end
    -- The addon message goes out on this frame and SetSlot/SetPassive commit
    -- synchronously, so the Refresh that AIO sends after it reads the new state.
    AIO.Handle("DiablocraftSkillbar", "Refresh")
    showOverview()
end)

local function absorb(payload)
    if not payload then return false end
    state = payload
    state.bar = state.bar or {}
    local module = tormentModule()
    if module then module.OnWellDrag = dropFromWell end
    swapPending = nil
    state.passiveBar = state.passiveBar or {}
    state.categories = state.categories or {}
    -- The payload is the only source of the slot rules. A payload without them
    -- is not drawable data, so the screen stays on loading and nothing is
    -- invented.
    local drawable = state.activeSlots and state.passiveSlotCount and state.passiveSlotLevels
    if drawable and frame:IsShown() and view == "loading" then
        showOverview()
    else
        render()
    end
    return true
end

-- Data only: keeps the screen ready to open instantly, without showing it.
function handlers.Set(player, payload) absorb(payload) end

-- The answer to the player's own Request, so this one may open the screen.
-- Inside an instance it opens only on the server's instanceEdits hint (a Greater
-- Rift whose Guardian is dead); anywhere else in an instance the
-- press says the server's line instead.
function handlers.Show(player, payload)
    if not absorb(payload) then return end
    if IsInInstance() and not payload.instanceEdits then
        if UIErrorsFrame then UIErrorsFrame:AddMessage("Not inside an instance or rift.", 1, 0.1, 0.1) end
        return
    end
    showOverview()
    frame:Show()
end

-- Opening the screen. Blizzard's spellbook is never replaced: replacing
-- ToggleSpellBook taints the global for everything that calls it, and
-- UnregisterAllEvents on SpellBookFrame taints the frame. /dcskills opens ours,
-- and P and the spellbook micro-button reach it through the hook below.
local function toggle()
    if frame:IsShown() then
        frame:Hide()
        return
    end
    -- 04 §3 / 12-ui §3: slot and rune changes are refused in combat by SetSlot,
    -- so a screen that can only lead to a refusal is not opened at all.
    if InCombatLockdown() then
        if UIErrorsFrame then UIErrorsFrame:AddMessage("Not in combat.", 1, 0.1, 0.1) end
        return
    end
    -- The same for an instance or rift: dc_classes.cpp refuses every change while the
    -- map is instanceable, except in a Greater Rift whose Guardian is dead. Only the
    -- server knows which, so the press asks and the Show answer opens or refuses.
    if IsInInstance() then
        AIO.Handle("DiablocraftSkillbar", "Request")
        return
    end
    AIO.Handle("DiablocraftSkillbar", "Request")
    -- Draw the server's rules when we already have them; otherwise open on the
    -- loading state and let the Request answer draw the screen.
    if state.activeSlots and state.passiveSlotCount and state.passiveSlotLevels then
        showOverview()
    else
        showLoading()
    end
    frame:Show()
end
SLASH_DCSKILLS1 = "/dcskills"
SlashCmdList["DCSKILLS"] = toggle

-- P and the spellbook micro-button both run ToggleSpellBook(BOOKTYPE_SPELL) -
-- that is the whole body of the TOGGLESPELLBOOK binding and of
-- SpellbookMicroButton's OnClick - so hooking that one global covers both, and
-- any addon that calls it too. 12-ui U2: the spellbook is replaced.
--
-- hooksecurefunc, never a replacement: assigning to ToggleSpellBook would taint
-- the global for every caller, and UnregisterAllEvents or a :Hide() on
-- SpellBookFrame taints the frame itself. The hook runs after the stock
-- function, so the book has opened by the time we see it; HideUIPanel is plain
-- FrameXML and puts it away through the panel system's own bookkeeping, which a
-- bare Hide() would leave inconsistent.
--
-- The pet book is left alone. Combat is NOT: an earlier version returned here
-- while InCombatLockdown(), which let P fall straight through to the stock
-- spellbook in a fight - a book that is supposed to be unreachable for every
-- class (12-ui U2). The book is now put away in both states; only
-- opening our own screen waits for the fight to end, and the press says so
-- instead of doing nothing visible.
--
-- HideUIPanel in combat is the same call Blizzard's own ToggleSpellBook makes
-- one line earlier, and SpellBookFrame is not a protected frame, so this closes
-- the book through the panel system's own bookkeeping - which a bare :Hide()
-- would leave inconsistent - and touches nothing the client protects.
if type(ToggleSpellBook) == "function" then
    hooksecurefunc("ToggleSpellBook", function(bookType)
        if bookType ~= BOOKTYPE_SPELL then return end
        -- The stock function has already run, so the book is open on the press
        -- that opens it and closed on the press that closes it. Only the first
        -- is ours to take over, and taking it over means toggling our screen -
        -- so the second press of P closes ours rather than reopening the book.
        if not (SpellBookFrame and SpellBookFrame:IsShown()) then return end
        HideUIPanel(SpellBookFrame)
        if InCombatLockdown() then
            -- 04 §3 / 12-ui §3 again: the screen cannot open here, so say the
            -- same thing toggle() would have said and stop.
            if UIErrorsFrame then UIErrorsFrame:AddMessage("Not in combat.", 1, 0.1, 0.1) end
            return
        end
        toggle()
    end)
end

-- Talents are removed from the game (04-classes K3).
-- The server never grants a point, so the tree can only ever draw empty; this
-- takes away the ways in so there is nothing to click.
--
-- TalentMicroButton is an ordinary unprotected Button and 3.3.5a's
-- UpdateMicroButtons only ever Enables or Disables it, so it is never re-Shown
-- and a plain Hide() holds for the session.
if TalentMicroButton then
    TalentMicroButton:Hide()
end

-- The N binding (TOGGLETALENTS) and the micro-button both call
-- ToggleTalentFrame(), which is FrameXML and always loaded, so hooking that one
-- global covers both and any addon that calls it too.
--
-- Same two rules as the spellbook above: hooksecurefunc rather than a
-- replacement, because assigning to the global would taint it for every caller;
-- and HideUIPanel rather than :Hide(), because PlayerTalentFrame is a UIPanel
-- and a bare Hide() leaves the panel system's bookkeeping inconsistent. The
-- stock function has already run by the time we see it, so it has loaded
-- Blizzard_TalentUI and PlayerTalentFrame exists.
--
-- Combat is not a special case here: nothing is opened and PlayerTalentFrame is
-- not protected, so the same line runs in and out of a fight.
if type(ToggleTalentFrame) == "function" then
    hooksecurefunc("ToggleTalentFrame", function()
        if PlayerTalentFrame and PlayerTalentFrame:IsShown() then
            HideUIPanel(PlayerTalentFrame)
            if UIErrorsFrame then
                UIErrorsFrame:AddMessage("Talents are removed.", 1, 0.1, 0.1)
            end
        end
    end)
end
