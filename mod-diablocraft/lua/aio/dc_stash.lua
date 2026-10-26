-- luacheck: globals DCTunables DCThrottle DCRange
-- Account stash - server half only (11-hardcore §4).
--
-- The client half is a real addon, client-patch/addons/Torment, installed
-- into Interface/AddOns. AIO is only the bridge between the two, so this file
-- deliberately never calls AIO.AddAddon(): nothing here is sent to a client.
--
-- Nothing in this file decides anything. It reads rows for the snapshot and it
-- forwards one intent, Move, to C++ (.dc stash move), which owns eligibility,
-- item legality, slot legality and the transaction. Lua asks and draws.
local AIO = AIO or require("AIO")
local CHANNEL = "DiablocraftStash"
local handlers = AIO.AddHandlers(CHANNEL, {})

local STASH_ENTRY = 910002
-- The window opens at OPEN_RANGE and everything afterwards -
-- every action and the auto-close - allows ACTION_RANGE, a yard more, so an open
-- window never refuses. The slack only ever runs one way: you cannot open the
-- stash from a distance that would then close it, and it shuts a yard before
-- the point where an action would have been refused.
--
-- OPEN_RANGE is INTERACTION_DISTANCE (ObjectDefines.h), the range the core gates
-- the NPC gossip on, so clicking the NPC and /dcstash agree.
-- constant: mirrors dc_stash.h OpenRange; changing it would
-- desync from the core's own gossip gate.
local OPEN_RANGE = 5.5
-- ui.stash_action_range_yards: read it when it
-- exists, else the old literal, reported once.
local function actionRange()
    return DCTunables.Or("ui", "stash_action_range_yards", 6.5)
end
-- structural: the 7x10 stash grid is the storage layout shared by the DB rows,
-- dc_stash.h and dc_stash.lua; changing it live would orphan stored items.
local SLOTS_PER_TAB = 70
-- economy.stash_max_tabs: read it when it exists,
-- else the old literal, reported once.
local function maxTabs()
    return DCTunables.Or("economy", "stash_max_tabs", 5)
end
-- structural: the 7x10 stash rows/columns follow SlotsPerTab above; changing
-- them without a migration would orphan stored items.
local STASH_ROWS, STASH_COLS = 7, 10   -- 70 slots per tab, as in D3

-- constant (security G1): the token buckets for the two handlers that commit. A
-- drag is one move; five a second sustained with a burst of eight is more than a
-- hand does, and a tab purchase is one click a minute. Same mechanism as Refresh's.
local MOVE_RATE, MOVE_BURST = 5, 8
local BUYTAB_RATE, BUYTAB_BURST = 0.5, 2

local open = {}    -- guid -> true while the window is up

local function quote(text)
    return tostring(text or ""):gsub("['\\]", "")
end

-- Mode and the account pools live in dc_account.lua, which is the one place
-- either is decided (0007; mode is to become a realm flag).
local function principal(player) return DCAccount.Principal(player) end

-- A7's physical half. C++ checks all of this again, and phase with it; this only
-- keeps a pointless command off the command line.
local function nearby(player, range)
    if not player:IsAlive() or player:IsInCombat() then return false end
    return player:GetNearestCreature(range, STASH_ENTRY) ~= nil
end

-- Opening is the strict one; staying open is the forgiving one.
local function canOpen(player) return nearby(player, OPEN_RANGE) end
local function canAct(player) return nearby(player, actionRange()) end

local function unwatch(player) DCRange.Unwatch(player, CHANNEL) end

-- Shuts the window on the client and drops the session. The addon is told, not
-- asked: it hides the frame, and the frame's OnHide echoes Close back here,
-- which is harmless because the state is already gone.
local function shut(player, reason)
    open[player:GetGUIDLow()] = nil
    unwatch(player)
    AIO.Handle(player, CHANNEL, "CloseWindow", reason or "")
end

-- While the window is up, canAct() - the same check every move is refused on -
-- is re-run on a timer, so walking away, dying or being pulled into combat shuts
-- the window instead of leaving it there refusing every click. Because it is the
-- action range, the window is always gone before an action could be refused. The
-- watcher is the shared one (dc_aio_range.lua).
local function watchRange(player) DCRange.Watch(player, CHANNEL, canAct, shut) end

-- A9's session context: opened at the NPC, dropped on close and on logout.
local function usable(player)
    return open[player:GetGUIDLow()] ~= nil and canAct(player)
end

-- Cells, names and rarity colours are all read the same
-- way by every Diablocraft screen, so they live in dc_grid.lua. The index
-- encoding described there is the one C++ decodes.
-- Resolved per call, never at load: ALE's load order across the script folder
-- is not ours to depend on, and every one of these runs long after startup.
local function describe(entries) return DCGrid.Describe(entries) end
local function rarities(guids) return DCGrid.Rarities(guids) end
local function cell(...) return DCGrid.Cell(...) end

local function prices()
    local out = {}
    local rows = WorldDBQuery("SELECT next_tab,price_gold FROM dc_stash_tuning")
    if rows then repeat
        -- A NULL price is not zero and not a default: it means the tab cannot be
        -- bought yet, and the addon says exactly that.
        local value = rows:GetString(1)
        out[rows:GetUInt32(0)] = (value ~= nil and value ~= "") and tonumber(value) or false
    until not rows:NextRow() end
    return out
end

local function snapshot(player)
    local account, mode = principal(player)
    if not account then return nil end
    local granted, revision = 1, 0
    local row = CharDBQuery(("SELECT tabs_granted,revision FROM dc_account_stash WHERE account_id=%d AND mode='%s'")
        :format(account, quote(mode)))
    local maxTabsAllowed = maxTabs()
    if row then granted, revision = row:GetUInt32(0), row:GetString(1) end
    if granted < 1 then granted = 1 end
    if granted > maxTabsAllowed then granted = maxTabsAllowed end

    local entries, guids, stash = {}, {}, {}
    local rows = CharDBQuery(("SELECT s.tab_id,s.slot_id,s.item_guid,ii.itemEntry,ii.count "
        .. "FROM dc_account_stash_item s JOIN item_instance ii ON ii.guid=s.item_guid "
        .. "WHERE s.account_id=%d AND s.mode='%s'"):format(account, quote(mode)))
    if rows then repeat
        local index = rows:GetUInt32(0) * SLOTS_PER_TAB + rows:GetUInt32(1)
        stash[index] = {guid = rows:GetUInt32(2), entry = rows:GetUInt32(3), count = rows:GetUInt32(4)}
        entries[rows:GetUInt32(3)] = true
        guids[rows:GetUInt32(2)] = true
    until not rows:NextRow() end

    local names, colours = describe(entries)
    local rarity = rarities(guids)

    local stashOut = {}
    for index, item in pairs(stash) do
        stashOut[index] = cell(item.guid, item.entry, item.count, names, colours, rarity[item.guid])
    end

    -- Exact copper as a decimal string, and the six account material totals the
    -- same way: the addon prints them and never turns one into a Lua number.
    local pools = DCAccount.Snapshot(player)
    return {
        revision = revision, mode = mode, gold = pools.gold, materials = pools.materials,
        tabs = {granted = granted, max = maxTabsAllowed, prices = prices()},
        layout = {slotsPerTab = SLOTS_PER_TAB, stashRows = STASH_ROWS, stashCols = STASH_COLS},
        stash = stashOut,
        -- Stash items are in nobody's bags, so the item tooltip path cannot find
        -- them by bag/slot. Ship their rolled rows with the snapshot.
        tooltips = DCItemTooltipRecords and DCItemTooltipRecords(stash) or {},
    }
end

local function push(player, note)
    local data = snapshot(player)
    if not data then
        AIO.Handle(player, CHANNEL, "Error", "This character has no mode yet. Log out and back in, then try again.")
        return
    end
    data.note = note
    AIO.Handle(player, CHANNEL, "Snapshot", data)
end

RegisterCreatureGossipEvent(STASH_ENTRY, 1, function(_, player)
    player:GossipComplete()
    open[player:GetGUIDLow()] = true
    watchRange(player)
    push(player, "open")
    return true
end)

-- The watcher catches all of these within a tick (500 ms) on its own, because canAct()
-- tests alive, out of combat and in range. These hooks only make the obvious
-- ones instant. Logout sends nothing: the session is already going, and
-- dc_aio_range.lua drops the watcher.
RegisterPlayerEvent(4, function(_, player)               -- logout
    open[player:GetGUIDLow()] = nil
end)
RegisterPlayerEvent(8, function(_, _, killed)            -- killed by a creature
    if killed and open[killed:GetGUIDLow()] then shut(killed, "Stash closed - you died.") end
end)
RegisterPlayerEvent(28, function(_, player)              -- map change
    if open[player:GetGUIDLow()] then shut(player, "Stash closed - you left the hub.") end
end)
RegisterPlayerEvent(33, function(_, player)              -- entered combat
    if open[player:GetGUIDLow()] then shut(player, "Stash closed - you are in combat.") end
end)
RegisterPlayerEvent(35, function(_, player)              -- released to a corpse
    if open[player:GetGUIDLow()] then shut(player, "Stash closed - you died.") end
end)

-- /dcstash. Standing at the Stash is enough to re-establish the context, which
-- is the same condition the NPC click carries.
function handlers.Refresh(player)
    -- Security G1: push() reads the stash tables; drop a flood before it can.
    if not DCThrottle.Allow(player, "stash:refresh", 5, 10) then return end
    if not canOpen(player) then
        -- Opening, so this is the strict range, the same one the NPC click uses.
        -- Same path as every other refusal, so the reason lands in chat: the
        -- status line inside the window is no use when the window is shut.
        shut(player, "Stash closed - stand at the hub Stash, alive and out of combat.")
        return
    end
    open[player:GetGUIDLow()] = true
    watchRange(player)
    push(player, "refresh")
end

function handlers.Close(player)
    open[player:GetGUIDLow()] = nil
    unwatch(player)
end

-- A bag-to-bag move never touches the stash, so the stash session is not a
-- condition of it: rearranging your own bags works anywhere (the bags are
-- ElvUI's, not the sheet's grid). This is the line dc_stash.cpp Move already draws,
-- returning through Rebag before Authorize is reached, because rearranging your
-- own bags writes no stash row, takes no container lock and needs no Stash
-- object. Every other direction keeps the session check exactly as it was.
function handlers.Move(player, fromKind, fromIndex, toKind, toIndex)
    -- Security G1: every move ends in a database commit the world thread waits for
    -- (dc_stash.cpp Commit), so a modified client must not send them as fast as it
    -- can. Dropped, never queued: the item simply stays where it was and no snapshot
    -- is sent. Done first, before any query or command.
    if not DCThrottle.Allow(player, "stash:move", MOVE_RATE, MOVE_BURST) then return end
    local bagOnly = fromKind == "bag" and toKind == "bag"
    if not bagOnly and not usable(player) then
        shut(player, "Stash closed - stand at the hub Stash, alive and out of combat.")
        return
    end
    if (fromKind ~= "bag" and fromKind ~= "stash") or (toKind ~= "bag" and toKind ~= "stash") then return end
    if type(fromIndex) ~= "number" or type(toIndex) ~= "number" then return end
    if fromIndex ~= math.floor(fromIndex) or toIndex ~= math.floor(toIndex) then return end
    if fromIndex < 0 or fromIndex > 25600 or toIndex < -1 or toIndex > 25600 then return end
    -- C++ validates all of this again and owns the transaction; the checks above
    -- only keep a malformed message out of the command line.
    player:RunCommand(("dc stash move %s %d %s %d"):format(fromKind, fromIndex, toKind, toIndex))
    -- The snapshot IS the stash window: the addon shows the frame whenever one
    -- arrives. Only a live session gets one, so a bag-to-bag move away from the
    -- hub cannot reopen a window the player closed or the watcher shut.
    if open[player:GetGUIDLow()] then push(player, "move") end
    -- The sheet's stat block reads the worn gear and the gold the move may have
    -- changed, so every Move pushes it a fresh snapshot, session or no session.
    -- After the command, so it draws the move, not the state before it.
    if DCInventory and DCInventory.Refresh then DCInventory.Refresh(player, "move") end
end

function handlers.BuyTab(player)
    if not DCThrottle.Allow(player, "stash:buytab", BUYTAB_RATE, BUYTAB_BURST) then return end
    if not usable(player) then
        shut(player, "Stash closed - stand at the hub Stash, alive and out of combat.")
        return
    end
    player:RunCommand("dc stash buytab")
    push(player, "buytab")
end
