-- Run from the repo root: lua mod-diablocraft/scripts/tests/ui/test_ui_fixes_text.lua
--
-- UI fixes row 13 (ruling 2026-10-03, diablocraft-ui-fixes-sheet): the stale
-- player text and the stale references the UI review listed
-- (docs/research/systems/ui-conformance.md, "Stale documents and comments").
-- Comments with no reference in them have no behaviour to test; they are on the
-- review's list and were rewritten by reading.

local function read(path)
    local file = assert(io.open(path, "rb"))
    local text = file:read("*a")
    file:close()
    return text
end

-- The one shared strict 3.3.5a widget mock (diablocraft-yey2) backs the
-- ElvUI_Torment core.lua load below, in its own environment so the addon sees
-- only the client globals the test gives it.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")

-- 1. The stash no longer asks the player to choose Normal or Hardcore: the realm
-- carries the mode (11 H4, 2026-09-21) and login writes it, so a character
-- without one is told to log in again. The Lua snapshot and the C++ checks say
-- the same thing.
local stashLua = read("mod-diablocraft/lua/aio/dc_stash.lua")
local stashCpp = read("mod-diablocraft/src/items/dc_stash.cpp")
for path, text in pairs({["dc_stash.lua"] = stashLua, ["dc_stash.cpp"] = stashCpp}) do
    assert(not text:find("Choose Normal or Hardcore", 1, true), path .. " still asks for a mode choice")
end
local luaText = stashLua:match('AIO%.Handle%(player, CHANNEL, "Error", "([^"]+)"%)')
assert(luaText, "the stash's no-mode refusal is found")
local cppTexts = {}
for unchosen in stashCpp:gmatch('Actor%(player,%s*"[^"]*",%s*"[^"]*",%s*"([^"]+)"%)') do
    cppTexts[#cppTexts + 1] = unchosen
end
assert(#cppTexts == 2, "both C++ callers of Actor are found, got " .. #cppTexts)
for _, text in ipairs(cppTexts) do
    assert(text == luaText, "the C++ refusal matches the Lua one: " .. text .. " / " .. luaText)
end
assert(luaText:find("log", 1, true) or luaText:find("Log", 1, true), "the text says what to do: " .. luaText)

-- 2. ElvUI_Torment's load line names the version its TOC carries (it printed
-- 0.3 under a 0.4 TOC). It reads the TOC, so it cannot drift again.
local toc = read("client-patch/addons/ElvUI_Torment/ElvUI_Torment.toc")
local tocVersion = assert(toc:match("## Version:%s*([^\r\n]+)"), "the TOC has a version")
local function loadLine(version)
    local printed = {}
    local env = setmetatable({
        GetAddOnMetadata = function(name, field)
            assert(name == "ElvUI_Torment" and field == "Version", "the TOC field is read by name")
            return version
        end,
        print = function(text) printed[#printed + 1] = text end,
        -- core.lua now also installs the full-number override (UI fixes row 5),
        -- so the file's declared dependency is stubbed like the client has it. The
        -- shared mock provides CreateFrame and hooksecurefunc in this environment.
        ElvUI = {{ShortValue = function() end, BuildPrefixValues = function() end,
                  GetModule = function() return {} end}},
    }, {__index = _G})
    Mock.install(env)
    local chunk
    if setfenv then
        chunk = assert(loadfile("client-patch/addons/ElvUI_Torment/core.lua"))
        setfenv(chunk, env)
    else
        chunk = assert(loadfile("client-patch/addons/ElvUI_Torment/core.lua", "t", env))
    end
    chunk("ElvUI_Torment")
    -- core.lua's loader frame registered ADDON_LOADED; the last is this run's (the
    -- mock keeps every widget it made, install() does not clear them).
    local loader
    for _, frame in ipairs(Mock.frames) do
        if frame.events and frame.events.ADDON_LOADED then loader = frame end
    end
    assert(loader, "core.lua registers an ADDON_LOADED handler")
    loader.scripts.OnEvent(loader, "ADDON_LOADED", "ElvUI_Torment")
    return printed[1]
end
assert(loadLine(tocVersion) == "Torment ElvUI " .. tocVersion .. " loaded",
    "the load line names the TOC's version, got " .. tostring(loadLine(tocVersion)))
assert(loadLine("9.9") == "Torment ElvUI 9.9 loaded", "and it is read, not a literal")

-- 3. ResourceText.lua's references: no Bartender4 (the bars are ElvUI's) and
-- every dc_skillbar.lua:N it cites is the skill picker's SetHyperlink line.
local resourceText = read("client-patch/addons/Torment/ResourceText.lua")
assert(not resourceText:find("Bartender", 1, true), "ResourceText.lua still names Bartender4")
local skillbar = {}
for line in (read("mod-diablocraft/lua/aio/dc_skillbar.lua") .. "\n"):gmatch("([^\n]*)\n") do
    skillbar[#skillbar + 1] = line
end
for number in resourceText:gmatch("dc_skillbar%.lua:(%d+)") do
    local line = skillbar[tonumber(number)] or ""
    assert(line:find("SetHyperlink", 1, true), "dc_skillbar.lua:" .. number .. " is not the SetHyperlink line")
end

print("test_ui_fixes_text: ok")
