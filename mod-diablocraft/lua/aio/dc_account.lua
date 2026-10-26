--[[
World of DiabloCraft - account economy, server-Lua reader (0007).

The one place our server Lua asks "whose pool is this, and what is in it".
Nothing here decides or changes anything: C++ owns the ledger, the receipts and
every transaction (src/common/dc_account_economy.cpp). This file only reads, and
it reads one way only - uint64 totals as exact decimal strings,
never through a Lua number, because a Lua number is a double and loses digits
above 2^53 while an account pool goes to UINT64_MAX.

Mode lives here and nowhere else. When the hardcore realm lands mode becomes
a realm flag and only Principal below changes.

Loaded before its callers by name: dc_account < dc_crafting < dc_stash.
]]

-- luacheck: globals DCAccount

DCAccount = {}
local A = DCAccount

-- account_economy.csv. The thirteen materials are account totals; gems are ordinary
-- items and stay item counts. 102006 is the retired Gold Bar denomination.
-- 102008-102012 are the five act reagents (bounties W3); 102013 is Primordial Ashes (Kanai's Cube).
A.MATERIALS = {102000, 102001, 102002, 102003, 102004, 102005, 102007,
    102008, 102009, 102010, 102011, 102012, 102013}
A.GOLD_BAR = 102006
-- One copper is one displayed gold. The retired Gold
-- Bar's value is the single dc_account_economy_kind row (kind 'retired_gold';
-- account_economy.csv copper_per_item). Read the table rather
-- than holding the literal; cached because it cannot change while the world is up.
-- constant: the displayed unit.
local COPPER_PER_GOLD = 1

local copperPerBarValue
local function copperPerBar()
    if not copperPerBarValue then
        local row = WorldDBQuery(("SELECT copper_per_item FROM dc_account_economy_kind "
            .. "WHERE item_entry=%d AND kind='retired_gold'"):format(A.GOLD_BAR))
        copperPerBarValue = row and row:GetDouble(0) or 0
    end
    return copperPerBarValue
end

local isMaterial = {}
for _, entry in ipairs(A.MATERIALS) do isMaterial[entry] = true end

function A.IsMaterial(entry)
    return isMaterial[entry] == true
end

-- ------------------------------------------------------- decimal-string maths

-- Anything that is not a run of digits is not a total; it becomes "0" rather
-- than a number that happens to parse.
local function digits(text)
    text = tostring(text or ""):gsub("%s", "")
    if text == "" or text:find("%D") then return "0" end
    text = text:gsub("^0+(%d)", "%1")
    return text
end
A.Digits = digits

-- Normalised length first, then lexicographically: the handoff's revision and
-- total comparison, and the only correct one for strings this long.
function A.Compare(left, right)
    left, right = digits(left), digits(right)
    if #left ~= #right then
        if #left < #right then return -1 end
        return 1
    end
    if left == right then return 0 end
    if left < right then return -1 end
    return 1
end

-- `need` is a Lua number from world data (recipe prices, material amounts), all
-- of them small; `have` is an account total and stays a string.
function A.AtLeast(have, need)
    return A.Compare(have, string.format("%.0f", tonumber(need) or 0)) >= 0
end

-- The balance is already in the displayed unit, so this is the
-- identity. It stays as the one named place a conversion would live again.
function A.GoldUnits(copper)
    return digits(copper)
end

-- 1,234,567. 12-ui U4: raw digits, never K/M/B.
function A.Commas(text)
    local out, count = digits(text), 1
    while count > 0 do
        out, count = out:gsub("^(%d+)(%d%d%d)", "%1,%2")
    end
    return out
end

-- -------------------------------------------------------------- the principal

-- The account and mode this character's pools belong to, or nil while the
-- permanent Normal/Hardcore choice is still pending. An unchosen character is
-- never mapped to normal (11-hardcore A3).
function A.Principal(player)
    if not player then return nil end
    local row = CharDBQuery("SELECT mode FROM dc_character_mode WHERE guid=" .. player:GetGUIDLow())
    local mode = row and row:GetString(0) or ""
    if mode ~= "normal" and mode ~= "hardcore" then return nil end
    return player:GetAccountId(), mode
end

-- ------------------------------------------------------------------ snapshot

-- gold is the exact balance as a decimal string, in the one displayed unit;
-- materials are exact counts keyed by
-- item entry. `managed` says the account ledger owns them, which is true once
-- the pool row exists: cutover writes one per account and mode for every legacy
-- source, and a new character's login writes its own. Before the cutover there
-- is no row and the legacy balance applies - native copper plus whatever Gold
-- Bars are still in bags, which is exactly what DC::Economy::Balance counts, so
-- the screens never disagree with what C++ will let the player spend.
--
-- The legacy sum is a Lua number on purpose: native copper is capped at uint32
-- and bars are few, so it stays far below 2^53 and is exact. The account path
-- never goes near a Lua number.
function A.Snapshot(player)
    local out = {managed = false, gold = "0", goldUnits = "0", materials = {}, owner = player}
    if not player then return out end
    local account, mode = A.Principal(player)
    out.account, out.mode = account, mode
    if account then
        local row = CharDBQuery(("SELECT CAST(balance_copper AS CHAR) FROM dc_account_gold "
            .. "WHERE account_id=%d AND mode='%s'"):format(account, mode))
        if row then
            out.gold, out.managed = digits(row:GetString(0)), true
        end
    end
    if out.managed then
        for _, entry in ipairs(A.MATERIALS) do out.materials[entry] = "0" end
        local rows = CharDBQuery(("SELECT item_entry,CAST(amount AS CHAR) FROM dc_account_currency "
            .. "WHERE account_id=%d AND mode='%s'"):format(account, mode))
        if rows then repeat
            out.materials[rows:GetUInt32(0)] = digits(rows:GetString(1))
        until not rows:NextRow() end
    else
        out.gold = string.format("%.0f",
            player:GetCoinage() + player:GetItemCount(A.GOLD_BAR, false) * copperPerBar())
        for _, entry in ipairs(A.MATERIALS) do
            out.materials[entry] = tostring(player:GetItemCount(entry, false))
        end
    end
    out.goldUnits = A.GoldUnits(out.gold)
    return out
end

-- What the player holds of one asset, as a decimal string. Materials come from
-- the snapshot; anything else (gems) is an ordinary item count.
function A.Have(snapshot, entry)
    if A.IsMaterial(entry) then return snapshot.materials[entry] or "0" end
    return tostring(snapshot.owner and snapshot.owner:GetItemCount(entry, false) or 0)
end

-- Convenience for the callers that only want the money line.
function A.Gold(player)
    local snapshot = A.Snapshot(player)
    return snapshot.gold, snapshot.goldUnits, snapshot.managed
end

A.CopperPerGold = COPPER_PER_GOLD
