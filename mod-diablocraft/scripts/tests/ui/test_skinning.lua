-- luacheck: globals CreateFrame UIParent SlashCmdList DC_TEST_MISSING
-- luacheck: ignore 111 121 122 431
-- Run from repo root with `lua5.2 mod-diablocraft/scripts/tests/ui/test_skinning.lua`.
--
-- The skin system in the Torment addon (client-patch/addons/Torment/ArtSlots.lua and WindowStyle.lua,
-- diablocraft-lido part C): a slot may carry `path`, SetArt remembers every
-- texture it draws, and DC.RefreshArt re-applies the current slots so a skin
-- that loaded after Torment is what the player sees. The bar and orb slots are
-- exercised by test_orbs_client.lua.

-- The one shared strict 3.3.5a widget mock (diablocraft-yey2) owns CreateFrame,
-- UIParent, hooksecurefunc and the rest of the client surface, and the frames
-- this test hands to SetArt come from it.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames

-- The client answers false when SetTexture cannot load a file, and
-- Diablocraft.SetArt records that as dcMissing. The mock is a widget double, not
-- a filesystem: it draws at a coarser grain, so this test wraps its one method
-- with the one client fact the assertion needs - set DC_TEST_MISSING to a path
-- for SetTexture to refuse it.
local mockSetTexture = Mock.methods.SetTexture.fn
Mock.methods.SetTexture.fn = function(self, value, ...)
    mockSetTexture(self, value, ...)
    if _G.DC_TEST_MISSING and type(value) == "string"
        and value:find(_G.DC_TEST_MISSING, 1, true) then
        return false
    end
end

local function texture() return Mock.widget("Texture") end
local function frame(name) return Mock.widget("Frame", name) end

_G.DEFAULT_CHAT_FRAME = {AddMessage = function() end}
-- The two stock functions Torment hooks at load. The mock's hooksecurefunc is
-- the client's: it refuses a name that is not a function, so they must exist.
_G.PickupContainerItem = function() end
_G.PickupInventoryItem = function() end
-- The WoW client has no `require`, and the addon asks for AIO through it.
_G.require = nil

dofile("mod-diablocraft/scripts/dc_addon_core.lua")
local DC = _G.Diablocraft

-- --------------------------------------------------------------- SetArt

-- A slot without `path` loads ART_PATH..file, exactly as before the skins.
local plain = texture()
DC.SetArt(plain, "slot")
assert(plain.texture == DC.ART_PATH .. "slot_empty", "a file slot loads ART_PATH..file, got " .. tostring(plain.texture))

-- A slot with `path` loads that path instead.
local slotted = texture()
DC.SetArt(slotted, "skill-slotted")
assert(slotted.texture == "Interface\\Buttons\\UI-ActionButton-Border",
    "a path slot loads its own path, got " .. tostring(slotted.texture))

-- Coords and tint still apply, from the slot.
local selected = texture()
DC.SetArt(selected, "slot-selected")
assert(selected.texCoord[1] == 0 and selected.texCoord[2] == 1, "the slot's own coords are used")
assert(selected.vertexColor[1] == 1.00 and selected.vertexColor[2] == 0.78 and selected.vertexColor[3] == 0.25,
    "the slot's tint is applied")

-- A texture the client refuses names the file it tried (the hole is otherwise
-- indistinguishable from art that was never drawn).
_G.DC_TEST_MISSING = "slot_empty"
local missing = texture()
DC.SetArt(missing, "slot")
assert(missing.dcMissing == DC.ART_PATH .. "slot_empty", "a file the client refuses is recorded")
_G.DC_TEST_MISSING = nil

-- An unnamed slot is obvious (a magenta probe), never silently blank.
local unnamed = texture()
DC.SetArt(unnamed, "no-such-slot")
assert(unnamed.texture == 1, "an unnamed slot draws the magenta probe")

-- --------------------------------------------------------------- RefreshArt

-- The addon owns the ElvUI slots. It ships the designer's generated hotbar in `bar` and
-- `orb-back` (diablocraft-lhoeu); the rest are empty, so their mock parts draw.
local SHIPPED = {bar = "hud_bar", ["orb-back"] = "hud_orb_back"}
for _, name in ipairs({"bar", "bar-buttons", "orb-health", "orb-resource-fury", "orb-resource-arcane_power",
                       "orb-resource-spirit", "orb-back", "orb-gloss", "orb-spark", "orb-lowhp-glow", "orb-skull"}) do
    assert(DC.ART[name], "the skin slot " .. name .. " is declared")
    if SHIPPED[name] then
        local path = DC.ART[name].path
        assert(path == "Interface\\AddOns\\ElvUI_Torment\\media\\" .. SHIPPED[name],
            "the slot " .. name .. " ships the hotbar art, got " .. tostring(path))
        local file = io.open("client-patch/addons/ElvUI_Torment/media/" .. SHIPPED[name] .. ".blp", "rb")
        assert(file, "the shipped " .. name .. " art is on disk")
        file:close()
    else
        assert(DC.ART[name].path == nil, "the skin slot " .. name .. " is empty by default")
    end
end
local stripSheet = DC.ART["bar"].stripTexture:gsub("^Interface\\AddOns\\", "client-patch/addons/"):gsub("\\", "/")
local stripFile = io.open(stripSheet .. ".blp", "rb")
assert(stripFile, "the shipped XP fill sheet is on disk: " .. stripSheet)
stripFile:close()

-- Every texture SetArt drew is remembered: a slot changed after drawing is
-- re-applied by RefreshArt, with the new path, coords and tint.
local first, second = texture(), texture()
DC.SetArt(first, "slot")
DC.SetArt(second, "skill-chosen")
DC.ART["slot"] = {file = "rarity_blue", colour = {0.1, 0.2, 0.3, 1}}
DC.ART["skill-chosen"] = {path = "Interface\\AddOns\\TestSkin\\chosen", coords = {0, 0.5, 0, 0.25},
                          tint = {0.5, 0.25, 0.125}}
DC.RefreshArt()
assert(first.texture == DC.ART_PATH .. "rarity_blue", "RefreshArt re-applies a changed slot")
assert(second.texture == "Interface\\AddOns\\TestSkin\\chosen", "a changed path slot follows too")
assert(second.texCoord[2] == 0.5 and second.texCoord[4] == 0.25, "and its new coords")
assert(second.vertexColor[1] == 0.5 and second.vertexColor[3] == 0.125, "and its new tint")

-- Torment calls it once at PLAYER_LOGIN, so a skin that loaded after Torment
-- is applied before the player sees anything.
local loginFrame
for _, candidate in ipairs(frames) do
    if candidate.events["PLAYER_LOGIN"] then loginFrame = candidate end
end
assert(loginFrame and loginFrame.scripts.OnEvent, "Torment registers a PLAYER_LOGIN refresh")
DC.ART["slot"] = {file = "rarity_green", colour = {0.1, 0.45, 0.1, 1}}
loginFrame.scripts.OnEvent(loginFrame, "PLAYER_LOGIN")
assert(first.texture == DC.ART_PATH .. "rarity_green", "PLAYER_LOGIN applies the current slots")
assert(not loginFrame.events["PLAYER_LOGIN"], "and the login handler unregisters itself")

-- --------------------------------------------------------------- TormentD3

-- The designer's skin (client-patch/skins/TormentD3) fills the slots; it is never
-- shipped, so nothing else would catch a path that no longer exists or a slot
-- name that drifted from the schema.
DC.ART = {}
dofile("client-patch/skins/TormentD3/TormentD3.lua")
for _, name in ipairs({"bar", "bar-buttons", "orb-health", "orb-resource-fury", "orb-resource-arcane_power",
                       "orb-back", "orb-gloss", "orb-spark", "orb-lowhp-glow", "orb-skull"}) do
    assert(DC.ART[name] and DC.ART[name].path, "TormentD3 fills the " .. name .. " slot")
end
-- The death window's buttons are NOT filled by the skin: they stay the shipped plain dark-red
-- buttons (ruling 2026-10-05), and the slots are the addon's own empty ones.
for _, name in ipairs({"death-button", "death-button-hover", "death-button-pressed", "death-button-disabled"}) do
    assert(DC.ART[name]==nil, "TormentD3 leaves the " .. name .. " slot alone")
end
assert(DC.ART["bar"].wells and #DC.ART["bar"].wells == 8, "the bar slot brings its eight wells")
assert(DC.ART["bar"].globeWells and DC.ART["bar"].strip and DC.ART["bar"].fills,
    "the bar slot brings its globe wells, XP strip and fill sprites")
-- The sheet those fill crops live in (the XP strip's status bar texture,
-- diablocraft-rr2e): a skin names its own, so the shipped atlas is not assumed.
assert(DC.ART["bar"].stripTexture, "the bar slot names the sheet its fills crop")
assert(DC.ART["bar-buttons"].portal and DC.ART["bar-buttons"].portal.normal,
    "the button slot brings the portal sprites")
assert(DC.ART["orb-health"].glow and DC.ART["orb-health"].frames == 60,
    "the health globe slot brings its atlas geometry and the health sheet's light")
for _, name in ipairs({"orb-health", "orb-resource-fury", "orb-resource-arcane_power"}) do
    local globe = DC.ART[name]
    assert(globe.width and globe.height and globe.cellW and globe.cellH and globe.cols,
        name .. " carries its atlas geometry")
end

-- Every path the skin names must exist on disk: the client draws a missing
-- texture as a black square, and the skin is the only place these paths live.
local function onDisk(path)
    local relative = path:gsub("^Interface\\AddOns\\", "client-patch/skins/"):gsub("\\", "/")
    for _, extension in ipairs({"", ".blp", ".tga"}) do
        local file = io.open(relative .. extension, "rb")
        if file then
            file:close()
            return true
        end
    end
    return false
end
for _, name in ipairs({"bar", "bar-buttons", "orb-health", "orb-resource-fury", "orb-resource-arcane_power",
                       "orb-back", "orb-gloss", "orb-spark", "orb-lowhp-glow", "orb-skull"}) do
    local path = DC.ART[name].path
    assert(onDisk(path), "TormentD3's art is on disk: " .. path)
end
assert(onDisk(DC.ART["bar"].stripTexture),
    "TormentD3's XP strip sheet is on disk: " .. DC.ART["bar"].stripTexture)

print("skin system checks passed")
