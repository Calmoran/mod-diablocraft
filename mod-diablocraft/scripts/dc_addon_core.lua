-- dc_addon_core.lua -- loads the Torment addon's core files for a Lua UI test, in the order
-- client-patch/addons/Torment/Torment.toc loads them. Run from the repo root:
--
--   dofile("mod-diablocraft/scripts/dc_addon_core.lua")
--
-- Each call runs the four files again, as a dofile of the one file used to. The list is checked
-- against the TOC, so a file added to or reordered in one place and not the other fails here.
local DIR = "client-patch/addons/Torment/"
local CORE = {"ArtSlots.lua", "PanelKit.lua", "WindowStyle.lua", "Stash.lua"}

local toc = assert(io.open(DIR .. "Torment.toc")):read("*a")
local at = 0
for _, name in ipairs(CORE) do
    local found = toc:find("\n" .. name .. "\n", at + 1, true)
    assert(found and found > at, "Torment.toc loads " .. name .. " after the file before it")
    at = found
end

for _, name in ipairs(CORE) do dofile(DIR .. name) end
return CORE
