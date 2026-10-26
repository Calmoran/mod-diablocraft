-- diablocraft-gwoey: the Mystic window names a preset-only line by its name, not its bare code.
-- The window's server half pushes one name per code (handlers.Tables) from the affix pools alone, so a line only an
-- item's own dc_item_preset_range row names (Tal Rasha's chest 'ias', the sweep's preset codes) or only
-- dc_affix_metadata names read as the code. It now takes dc_tooltip.lua's fallback (DCAffixFallback, the one
-- describe() reads after the slot pool), so the window and the tooltip say the same words. Both halves run as
-- shipped here, fed the committed renders (the latest preset sheet and the metadata migration), never a copy.
-- Run from the repo root: lua mod-diablocraft/scripts/tests/crafting/test_mystic_preset_names.lua
-- luacheck: ignore 111 112 113 121 122 212
local UPDATES="mod-diablocraft/data/sql/db-world/updates/"
local function read(path)
    local file=assert(io.open(path,"r"),path);local text=file:read("*a");file:close();return text
end
local function unquote(s) return (s:gsub("''","'")) end
-- entry, affix_id, affix_name, kind, value_min, value_max, value_step, item_level_bracket, is_percent, display_order
local PRESETS={}
for entry,id,name,kind,percent,order in read(UPDATES.."items_0037_item_preset_ranges_q1016.sql")
    :gmatch("\n%((%d+), '(.-)', '(.-)', '(.-)', [^,]+, [^,]+, [^,]+, '.-', (%d), (%d+)%)") do
    PRESETS[#PRESETS+1]={tonumber(entry),id,unquote(name),tonumber(percent),kind,tonumber(order)}
end
-- affix_id, affix_name, kind, is_percent, display_order
local METADATA={}
for id,name,kind,percent,order in read(UPDATES.."items_0034_affix_metadata_sweep.sql")
    :gmatch("\n%('(.-)', '(.-)', '(.-)', (%d), (%d+)%)") do
    METADATA[#METADATA+1]={id,unquote(name),tonumber(percent),kind,tonumber(order)}
end
assert(#PRESETS>=400 and #METADATA>=20,"the renders parsed: "..#PRESETS.." preset rows, "..#METADATA.." metadata rows")

local function result(rows)
    if not rows[1] then return nil end
    local n=1;local function get(_,i) return rows[n][i+1] end
    return {GetString=get,GetUInt32=get,GetInt32=get,GetDouble=get,IsNull=function(_,i) return rows[n][i+1]==nil end,
        NextRow=function() n=n+1;return rows[n]~=nil end}
end
-- Only the two fallback tables have rows: whatever the window names past its own tables comes from them.
local presetRows
function WorldDBQuery(q)
    if q:find("FROM dc_item_preset_range",1,true) then return result(presetRows) end
    if q:find("FROM dc_affix_metadata",1,true) then return result(METADATA) end
    return nil
end
function RegisterPlayerEvent() end
function RegisterCreatureGossipEvent() end
-- Both server halves loaded fresh over one preset table; returns what the Mystic pushes.
local function push(presets)
    presetRows=presets
    local handlers,sent={},nil
    AIO={AddAddon=function() return true end,AddOnInit=function() end,
        AddHandlers=function(name,h) handlers[name]=h;return h end,
        Handle=function(_,channel,verb,data) if channel=="DiablocraftCrafting" and verb=="Tables" then sent=data end end}
    -- The Mystic loads first (AIO file load order is not ours): it must not need the fallback at load.
    DCAffixFallback=nil
    dofile(os.getenv("DC_CRAFTING_LUA") or "mod-diablocraft/lua/aio/dc_crafting.lua")
    dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")
    handlers.DiablocraftCrafting.Tables({})
    return assert(sent,"the Mystic pushed its tables")
end
local sent=push(PRESETS)

-- Tal Rasha's Relentless Pursuit's attack speed: only the chest's own preset row names it.
local ias
for _,row in ipairs(PRESETS) do if row[1]==100640 and row[2]=="ias" then ias=row end end
assert(ias,"Tal Rasha's chest has its own ias row")
assert(sent.names.ias==ias[3],"ias reads '"..ias[3].."', got '"..tostring(sent.names.ias).."'")
assert(sent.percent.ias==true,"ias is a percent, as its row says")
-- A stat only the metadata names. Every metadata code has a preset row today (items_0037), so the preset rows are
-- withheld to show the second step: the code still reads as the metadata's name.
local mana
for _,row in ipairs(METADATA) do if row[1]=="maxmana" then mana=row end end
local bare=push({})
assert(bare.names.maxmana==mana[2],"maxmana reads '"..mana[2].."', got '"..tostring(bare.names.maxmana).."'")
assert(bare.percent.maxmana==(mana[3]~=0),"maxmana's percent is the metadata's")
-- Every preset and metadata code has a name, so no line reads as a bare code.
for _,row in ipairs(PRESETS) do assert(sent.names[row[2]],"preset code "..row[2].." is named") end
for _,row in ipairs(METADATA) do assert(sent.names[row[1]],"metadata code "..row[1].." is named") end
-- A name the window already has stays: the preset sheet calls dex 'Primary Attribute', the window 'Dexterity'.
local dexRow
for _,row in ipairs(PRESETS) do if row[2]=="dex" then dexRow=row end end
assert(dexRow and dexRow[3]~="Dexterity","the sheet names dex differently, so this check bites")
assert(sent.names.dex=="Dexterity","dex keeps the window's own name, got "..tostring(sent.names.dex))
print("Mystic preset names OK: ias -> "..sent.names.ias..", maxmana -> "..bare.names.maxmana)
