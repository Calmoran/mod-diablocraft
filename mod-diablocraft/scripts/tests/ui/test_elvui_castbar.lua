-- luacheck: globals ElvUI InCombatLockdown unpack
-- luacheck: ignore 111 121 122 431 631
-- Run from repo root with `lua mod-diablocraft/scripts/tests/ui/test_elvui_castbar.lua`.
--
-- Mocks the client, ElvUI's UnitFrames module and ElvUI's oUF element API around
-- the production files client-patch/addons/ElvUI_Torment/{barart,castbar}.lua
-- and asserts the castbar-only player frame (option A, diablocraft-elvui-scale-
-- castbar). Mocks do NOT prove pixels: what the designer sees is on his card in
-- docs/test-diablocraft-elvui-scale-castbar.md.
--
-- The frame it builds is 6.09's: RaisedElementParent with Health.value,
-- Power.value and frame.customTexts on it (Health.lua:41, Power.lua:31,
-- CustomText.lua:23), the castbar on the frame itself and a sibling of that
-- layer (CastBar.lua:33), and ElvUI's real element names
-- (LeaderIndicator/MasterLooterIndicator/AssistantIndicator/GroupRoleIndicator,
-- not the never-enabled RaidRoleIndicator).
--
-- Pinned: with the option on, every listed part is hidden - the texts with
-- RaisedElementParent - and its oUF element disabled, while the castbar and its
-- element stay; the pass survives ElvUI's own update re-showing everything; the
-- option off restores ONCE through ElvUI's own UF.player:Update(), so parts and
-- elements the profile has off stay off and later updates change nothing; in
-- combat nothing at all is changed and the pass is queued to
-- PLAYER_REGEN_ENABLED; and the shipped layout's castbar cannot overlap either
-- orb.
--
-- The geometry part is arithmetic on the shipped layout: the two mover strings
-- and the bar1Scale below are the decoded values from the profile the designer exported
-- (installer test 1 pins those bytes; the decode is
-- _agent-scratch/elvui-scale-castbar/layout-plain.txt), and the orb wells come
-- from barart's own GLOBE_WELLS through module:GetGlobeWells().

unpack = unpack or table.unpack

-- ------------------------------------------------------------- stub client

local combat = false

-- The one shared strict 3.3.5a widget mock (diablocraft-yey2): it owns
-- CreateFrame, UIParent, hooksecurefunc and the rest of the client surface,
-- and no longer hands out a public .width/.height (sizes are read via
-- GetWidth/GetHeight) or a public .point. Installed into this test's guard env
-- below, once clientGlobals exists.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
local frames = Mock.frames

-- The mock is a widget double, not a spy: wrap its shared EnableMouse so the
-- "no secure call in combat" check still counts the calls.
local mouseCalls = {}
local mockEnableMouse = Mock.methods.EnableMouse.fn
Mock.methods.EnableMouse.fn = function(self, enabled)
    mouseCalls[#mouseCalls + 1] = {frame = self, enabled = enabled, combat = combat}
    return mockEnableMouse(self, enabled)
end

-- A frame is only visible if it and every parent are shown: that is what the
-- client does, and it is how RaisedElementParent hides the texts on it.
local function visible(object)
    local node = object
    while node do
        if node.shown == false then return false end
        node = node.parent
    end
    return true
end

function InCombatLockdown() return combat end

local printed = {}
local realPrint = print
function print(msg) printed[#printed + 1] = msg end

-- ------------------------------------------------- ElvUI and its unitframes

-- The objects each oUF element owns on the player frame, as ElvUI wires them:
-- Health.lua/Power.lua/Portrait.lua/Auras.lua/AuraBars.lua and the Configure_*
-- calls in Units/Player.lua. Enabling an element shows its object, disabling it
-- hides it - that is what oUF's element Enable/Disable do.
local ELEMENT_OBJECTS = {
    Health = {"Health"}, Power = {"Power"}, Portrait = {"Portrait", "Portrait2D", "Portrait3D"},
    Auras = {"Buffs", "Debuffs"}, AuraBars = {"AuraBars"}, Castbar = {"Castbar"},
    Cutaway = {"Cutaway"}, DebuffHighlight = {"DebuffHighlight"},
    ThreatIndicator = {"ThreatIndicator"}, RestingIndicator = {"RestingIndicator"},
    CombatIndicator = {"CombatIndicator"}, PvPIndicator = {"PvPText"},
    RaidTargetIndicator = {"RaidTargetIndicator"}, LeaderIndicator = {"RaidRoleFramesAnchor"},
    MasterLooterIndicator = {"RaidRoleFramesAnchor"}, AssistantIndicator = {"RaidRoleFramesAnchor"},
    GroupRoleIndicator = {"RaidRoleFramesAnchor"}, HealComm4 = {"HealCommBar"},
    -- ElvUI builds the rune/extra-power/combo bars INTO the holder
    -- (ClassBars.lua:21); enabling those elements shows the bars, never the
    -- holder itself, which nothing but this module ever shows or hides.
    Runes = {"Runes"}, AdditionalPower = {"AdditionalPower"}, ComboPoints = {"ComboPoints"},
}

-- Every child of ElvUF_Player the mock builds, in Construct_PlayerFrame order.
-- RaisedElementParent is the layer ElvUI puts the texts on (UnitFrames.lua:217).
local PART_NAMES = {"Health", "Power", "Name", "Portrait3D", "Portrait2D", "Portrait",
                    "Buffs", "Debuffs", "AuraBars", "InfoPanel", "ClassBarHolder",
                    "ThreatIndicator", "RestingIndicator", "CombatIndicator", "PvPText",
                    "RaidTargetIndicator", "RaidRoleFramesAnchor", "HealCommBar", "Cutaway",
                    "DebuffHighlight", "RaisedElementParent", "MouseGlow", "TargetGlow",
                    "iborder", "oborder", "Castbar", "CastbarHolder", "mover", "CastbarMover"}

-- The profile this fixture stands for. ElvUI's own settings decide what comes
-- back when the mode is off; this one has the aura bars and the 2D portrait off
-- (both are hide-based options), so anything that brings them back is a failure.
-- Name is NOT one of them: a profile with no name is a blank text_format, never
-- a hidden FontString, which is why the module shows it unconditionally.
local PROFILE = {AuraBars = false, Portrait2D = false}

-- The parts Update_PlayerFrame re-shows in 6.09, i.e. every part except the ones
-- nothing there owns: Health (only oUF's spawn loop enables and shows it), Name
-- (Name.lua never toggles it), the border frames SetTemplate created,
-- ClassBarHolder (ClassBars.lua:21) and RaisedElementParent. Those five are what
-- the module's restore hands back explicitly.
local NOT_RESHOWN = {Health = true, Name = true, ClassBarHolder = true,
                     RaisedElementParent = true}

local function buildPlayer()
    local frame = Mock.widget("Button", "ElvUF_Player")
    for _, name in ipairs(PART_NAMES) do frame[name] = Mock.widget("Frame", nil, frame) end
    for _, name in ipairs({"Runes", "AdditionalPower", "ComboPoints"}) do
        frame[name] = Mock.widget("Frame", nil, frame.ClassBarHolder)
    end
    -- The texts ElvUI draws over the frame, on the raised layer.
    frame.Health.value = Mock.widget("FontString", nil, frame.RaisedElementParent)
    frame.Power.value = Mock.widget("FontString", nil, frame.RaisedElementParent)
    frame.customTexts = {holyPower = Mock.widget("FontString", nil, frame.RaisedElementParent)}
    frame.elementsEnabled = {}
    function frame:IsElementEnabled(name) return self.elementsEnabled[name] == true end
    function frame:EnableElement(name)
        if self.elementsEnabled[name] then return end
        self.elementsEnabled[name] = true
        for _, object in ipairs(ELEMENT_OBJECTS[name] or {}) do
            if self[object] then self[object]:Show() end
        end
    end
    function frame:DisableElement(name)
        if not self.elementsEnabled[name] then return end
        self.elementsEnabled[name] = nil
        for _, object in ipairs(ELEMENT_OBJECTS[name] or {}) do
            if self[object] then self[object]:Hide() end
        end
    end
    -- The castbar is ElvUI's own element with its own holder and mover, and it
    -- is the one thing the module must leave alone.
    frame.Castbar.Holder = frame.CastbarHolder
    frame.CastbarHolder.mover = frame.CastbarMover
    frame.mover.frame = frame
    -- ElvUI never templates the player frame (see the mock's
    -- ToggleTransparentStatusBar), so it has no template, no backdrop and no
    -- border frames; its health bar does have a backdrop (ElvUI's CreateBackdrop).
    frame.Health.backdrop = Mock.widget("Frame", nil, frame.Health)
    -- ElvUI's Toolkit SetTemplate is a domain double, not a client method: the
    -- only frame this test templates through ToggleTransparentStatusBar is the
    -- health bar's own backdrop, so it carries the double.
    function frame.Health.backdrop:SetTemplate(template, glossTex, ignoreUpdates, forcePixelMode, isUnitFrameElement)
        self.template = template or "Default"
        self.templateCalls = (self.templateCalls or 0) + 1
        -- ElvUI's SetTemplate sets the backdrop and both colours from the
        -- profile it is templating on every call (Core/Toolkit.lua:91-130).
        self.backdrop = {bgFile = "template"}
        self.backdropColor = {0, 0, 0, 0.8}
        self.backdropBorderColor = {0, 0, 0, 1}
        self.glossTex, self.forcePixelMode, self.isUnitFrameElement = glossTex, forcePixelMode, isUnitFrameElement
    end
    -- oUF's SPAWN state (ouf.lua:426-428): every element enabled, every object
    -- shown, whatever the profile says. That is the state a fresh session is in
    -- when the first hide runs, mid-Update_PlayerFrame.
    for name in pairs(ELEMENT_OBJECTS) do frame:EnableElement(name) end
    for _, name in ipairs(PART_NAMES) do frame[name]:Show() end
    return frame
end

local player = buildPlayer()

local UF = {player = player}
-- ElvUI's own per-profile update for the player frame: every element its profile
-- enables, every object its profile shows. Called by frame:Update(), by
-- CreateAndUpdateUF and by Update_AllFrames.
function UF:Update_PlayerFrame(frame, _db)
    frame.updateCalls = (frame.updateCalls or 0) + 1
    frame.db = frame.db or {}
    -- 6.09's own order (Units/Player.lua:104-143): Configure_HealthBar runs
    -- FIRST, and the health element's update is what calls
    -- ToggleTransparentStatusBar (Health.lua:206), which re-templates the health
    -- bar's own backdrop (UnitFrames.lua:1304 - the parent branch at :1307 is
    -- never reached, because a bar's backdrop exists). So on
    -- a fresh session our hook fires HERE, in the middle of the update, before
    -- Power, Portrait, Auras, AuraBars, Cutaway, DebuffHighlight, RaidIcon,
    -- HealComm, PVPIcon and RaidRoleIcons have applied the profile. Nothing may
    -- depend on what the frame looked like at that moment.
    UF:ToggleTransparentStatusBar(false, frame.Health, nil, false)
    -- Then Configure_* re-enables the elements its profile has on. Health is not
    -- one of them: nothing after construction calls EnableElement("Health") in
    -- 6.09 (only oUF's spawn loop does), and Configure_HealthBar ForceUpdates
    -- only an already-enabled bar.
    for name in pairs(ELEMENT_OBJECTS) do
        if name ~= "Health" and (name ~= "AuraBars" or PROFILE.AuraBars) then
            frame:EnableElement(name)
        end
    end
    -- And it re-shows the objects those Configure_* functions own, which is not
    -- every part: see NOT_RESHOWN.
    for _, name in ipairs(PART_NAMES) do
        if not NOT_RESHOWN[name] then frame[name]:Show() end
    end
    if not PROFILE.AuraBars then frame.AuraBars:Hide() end
    if not PROFILE.Portrait2D then frame.Portrait2D:Hide() end
    -- Neither this nor anything else templates the player frame itself in 6.09
    -- (ToggleTransparentStatusBar stops at the bar's own backdrop), so the frame
    -- has no backdrop and no iborder/oborder of its own.
end
player.Update = function() UF:Update_PlayerFrame(player, {}) end
function UF:ToggleTransparentStatusBar(_isTransparent, statusBar, _backdropTex, _invert)
    -- UnitFrames.lua:1302-1308 verbatim in effect: the bar's own backdrop when it
    -- has one (Health does), and only otherwise the parent - which is why the
    -- player frame is never templated.
    if statusBar and statusBar.backdrop then
        statusBar.backdrop:SetTemplate("Transparent", nil, nil, nil, true)
    elseif statusBar and statusBar:GetParent() and statusBar:GetParent().template then
        statusBar:GetParent():SetTemplate("Transparent", nil, nil, nil, true)
    end
end
function UF:SetStatusBarBackdropPoints(statusBar) statusBar:SetBackdrop({bgFile = "bar"}) end
function UF:Update_AllFrames() player:Update() end

local module
local AB = {handledBars = {bar1 = Mock.widget("Frame")}, PositionAndSizeBar = function() end}
local E = {
    Modules = {},
    db = {torment = {}},
    GetModule = function(self, name)
        if name == "ActionBars" then return AB end
        if name == "UnitFrames" then return UF end
        return self.Modules[name]
    end,
    NewModule = function(self, name) local m = {} self.Modules[name] = m return m end,
    RegisterModule = function() end,
}
ElvUI = {E}

-- The only globals the target 3.3.5 client has, and the guard errors on any
-- other one, so an unsourced global fails here instead of on the designer's client.
local clientGlobals = {
    assert = assert, error = error, ipairs = ipairs, pairs = pairs, next = next, select = select,
    tostring = tostring, tonumber = tonumber, type = type, unpack = unpack, print = print,
    math = math, string = string, table = table, _G = _G,
    InCombatLockdown = InCombatLockdown,
    ElvUI = ElvUI,
    -- barart.lua's XP strip reads these (its own ApplyGeometry path runs here).
    MAX_PLAYER_LEVEL = 80,
    UnitXP = function() return 10 end, UnitXPMax = function() return 100 end,
    UnitLevel = function() return 70 end,
}
-- The mock installs CreateFrame, UIParent, hooksecurefunc, GameTooltip, ... into
-- the guard's backing table, so the guard still errors on anything else.
Mock.install(clientGlobals)
Mock.setScreen(1024, 768)
local function guardEnv(path)
    return setmetatable({}, {
        __index = function(_, key)
            -- The Torment addon is an OptionalDep of this one: barart reads
            -- `Diablocraft and Diablocraft.ART` for its skin slots, so the
            -- global is nil here, not an unsourced global.
            if key == "Diablocraft" then return nil end
            local value = clientGlobals[key]
            if value == nil then
                error(("%s referenced a global unavailable in 3.3.5: %s"):format(path, tostring(key)), 2)
            end
            return value
        end,
    })
end
local function loadGuarded(path)
    local env = guardEnv(path)
    if setfenv then
        local chunk = assert(loadfile(path))
        setfenv(chunk, env)
        return chunk()
    end
    return assert(loadfile(path, "t", env))()
end
local probe
if setfenv then
    probe = assert(loadstring("return getn"))
    setfenv(probe, guardEnv("guard probe"))
else
    probe = assert(load("return getn", "guard probe", "t", guardEnv("guard probe")))
end
assert(not pcall(probe), "guard must reject the unavailable global getn")

loadGuarded("client-patch/addons/ElvUI_Torment/barart.lua")
module = E:GetModule("ElvUI_Torment")
loadGuarded("client-patch/addons/ElvUI_Torment/castbar.lua")
assert(type(module.ApplyCastbarOnly) == "function", "castbar.lua did not publish its apply")
assert(type(module.IsCastbarOnly) == "function", "castbar.lua did not publish its state")

-- --------------------------------------------------------------- helpers

local HIDDEN_PARTS = {"Health", "Power", "Name", "Portrait3D", "Portrait2D", "Portrait",
                      "Buffs", "Debuffs", "AuraBars", "InfoPanel", "ClassBarHolder",
                      "ThreatIndicator", "RestingIndicator", "CombatIndicator", "PvPText",
                      "RaidTargetIndicator", "RaidRoleFramesAnchor", "HealCommBar", "Cutaway",
                      "DebuffHighlight", "RaisedElementParent", "MouseGlow", "TargetGlow"}
local HIDDEN_ELEMENTS = {"Health", "Power", "Portrait", "Auras", "AuraBars", "Cutaway",
                         "DebuffHighlight", "ThreatIndicator", "RestingIndicator",
                         "CombatIndicator", "PvPIndicator", "RaidTargetIndicator",
                         "LeaderIndicator", "MasterLooterIndicator", "AssistantIndicator",
                         "GroupRoleIndicator", "HealComm4"}

local function assertCastbarOnly(label)
    for _, name in ipairs(HIDDEN_PARTS) do
        assert(not visible(player[name]), label .. ": " .. name .. " must be hidden")
    end
    for _, name in ipairs(HIDDEN_ELEMENTS) do
        assert(not player:IsElementEnabled(name), label .. ": element " .. name .. " must be disabled")
    end
    -- The numbers ElvUI draws over the frame live on the raised layer.
    assert(not visible(player.Health.value), label .. ": the health text must be hidden")
    assert(not visible(player.Power.value), label .. ": the power text must be hidden")
    for name, text in pairs(player.customTexts) do
        assert(not visible(text), label .. ": customText " .. name .. " must be hidden")
    end
    assert(player.shown, label .. ": the frame itself stays shown")
    assert(visible(player.Castbar), label .. ": the castbar stays visible")
    assert(player.Castbar.parent == player,
        label .. ": the castbar is created on the frame, not on RaisedElementParent")
    assert(player:IsElementEnabled("Castbar"), label .. ": the castbar element stays enabled")
    assert(player.mouseEnabled == false, label .. ": the frame must be click-through")
end

-- ------------------------------------------------------ the option, on by default

assert(E.db.torment.castbarOnly == nil, "the default is exercised, not a seeded value")
assert(module:IsCastbarOnly(), "the castbar-only mode is on by default")
assert(player:IsElementEnabled("AuraBars") and visible(player.AuraBars),
    "the fixture starts in oUF's spawn state, before any ElvUI update")

-- LOGIN, the normal path: the mode is on by default, and the first hide runs
-- INSIDE ElvUI's own player-frame update - the health element's
-- ToggleTransparentStatusBar call (Health.lua:206), which Configure_HealthBar
-- makes before Power, Portrait, Auras, AuraBars, ... have applied the profile.
-- A restore that trusted whatever the frame looked like at that moment would be
-- restoring oUF's spawn state.
UF:Update_PlayerFrame(player, {})
assertCastbarOnly("login with the mode on (the first hide runs inside Update_PlayerFrame)")

-- The barart geometry pass wires the same state in and is idempotent
-- (barart.lua calls module:ApplyCastbarOnly from its own combat-deferred Apply),
-- so this goes through module:Apply() and never calls the castbar entry point.
module:Apply()
assertCastbarOnly("after barart's own apply")

-- The castbar keeps its own geometry: nothing here re-anchors it or its mover.
assert(#player.Castbar.points == 0 and #player.CastbarHolder.points == 0,
    "the castbar and its holder must never be re-anchored by this module")
assert(player.CastbarHolder.mover == player.CastbarMover, "the castbar keeps its own mover")
assert(player.mover.frame == player, "the frame's own mover stays attached")

-- No OnUpdate loop anywhere: the pass is hook- and event-driven only.
for _, frame in ipairs(frames) do
    assert(frame.scripts.OnUpdate == nil, "the module must not use OnUpdate")
end

-- --------------------------------------- ElvUI re-showing every part is undone

UF:Update_PlayerFrame(player, {})
assertCastbarOnly("after ElvUI's own player-frame update")

-- A mid-update ToggleTransparentStatusBar (what Configure_HealthBar's health
-- element update does, Health.lua:206) re-templates the health bar's own
-- backdrop and must leave our state alone; the pass is not hooked to it.
UF:ToggleTransparentStatusBar(false, player.Health, nil, false)
assert(player.Health.backdrop.templateCalls and player.Health.backdrop.templateCalls > 0,
    "the mid-update call templates the health bar's backdrop")
assertCastbarOnly("after a mid-update ToggleTransparentStatusBar call")

-- A profile change arrives as Update_AllFrames -> frame.Update -> Update_PlayerFrame.
UF:Update_AllFrames()
assertCastbarOnly("after a profile change")

-- --------------------------------------------------------------- in combat

local mouseBefore = #mouseCalls
combat = true
UF:Update_PlayerFrame(player, {})      -- ElvUI re-shows its own parts mid-fight
assert(visible(player.Power), "ElvUI is free to re-show its parts in combat")
assert(player.mouseEnabled == false, "the frame stays click-through while the queue waits")
assert(#mouseCalls == mouseBefore, "no secure call (EnableMouse) in combat")
combat = false
local events = nil
for _, frame in ipairs(frames) do
    if frame.events.PLAYER_REGEN_ENABLED then events = frame end
end
assert(events, "the module must watch PLAYER_REGEN_ENABLED")
events.scripts.OnEvent(events, "PLAYER_REGEN_ENABLED")
assertCastbarOnly("after the queued pass runs out of combat")

-- ------------------------------------------------------------ the option off

-- ElvUI's own update is the restore, exactly once, and the profile decides what
-- comes back: this profile has AuraBars and the 2D portrait off.
local updatesBefore = player.updateCalls
E.db.torment.castbarOnly = false
module:Apply()                        -- the options toggle's path
assert(player.updateCalls == updatesBefore + 1, "the restore must use ElvUI's own update, once")
-- ElvUI's own update does not give everything back in 6.09, so the restore also
-- hands back the four things ElvUI never touched by hiding them - and nothing
-- else, so everything the profile has off stays off.
for _, name in ipairs(HIDDEN_PARTS) do
    if name ~= "AuraBars" and name ~= "Portrait2D" then
        assert(visible(player[name]), "option off: " .. name .. " must come back")
    end
end
assert(visible(player.Health.value) and visible(player.Power.value),
    "option off: the texts come back with the raised layer")
assert(player:IsElementEnabled("Health") and visible(player.Health),
    "option off: the health element is enabled again (Update_PlayerFrame never does it)")
assert(visible(player.ClassBarHolder), "option off: the class bar holder comes back")
assert(visible(player.Name), "option off: the name comes back (ElvUI never hides it)")
assert(not player:IsElementEnabled("AuraBars"),
    "login with the mode on, option off: a profile-disabled element stays off")
assert(not visible(player.AuraBars), "login with the mode on, option off: and its part stays hidden")
assert(not visible(player.Portrait2D), "option off: the 2D portrait stays off")
assert(player:IsElementEnabled("Portrait") and player:IsElementEnabled("Power"),
    "option off: the profile's own elements are enabled again")
assert(player.mouseEnabled == true, "option off: the frame is clickable again")
assert(player.template == nil, "the player frame is never templated, so it has no backdrop of its own")
assert(player.Health.backdrop.templateCalls and player.Health.backdrop.templateCalls > 0,
    "the health bar's own backdrop is what ToggleTransparentStatusBar re-templates")

-- And from here the module does nothing at all: ElvUI's own updates stand, and
-- the restore never runs a second time.
local afterRestore = player.updateCalls
for _ = 1, 3 do UF:Update_PlayerFrame(player, {}) end
assert(player.updateCalls == afterRestore + 3,
    "while the option is off the module must not run ElvUI's update itself")
assert(not visible(player.AuraBars) and not player:IsElementEnabled("AuraBars"),
    "while the option is off ElvUI's per-profile state must stand")
assert(player.mouseEnabled == true, "the mouse stays with ElvUI while the option is off")

-- Toggle back on through the barart path deliberately disables nothing that
-- ElvUI owns, and off again through the options path.
E.db.torment.castbarOnly = true
module:Apply()
assertCastbarOnly("after toggling the option back on")

E.db.torment.castbarOnly = false
module:Apply()
assert(player:IsElementEnabled("Health") and not player:IsElementEnabled("AuraBars"),
    "a second off transition restores the profile's state again")
assert(visible(player.Name), "a second off transition shows the name again (ElvUI never hides it)")

-- And a profile change while the mode is on: what the profile says at the
-- moment the option goes off wins, which is ElvUI's own update doing the work.
E.db.torment.castbarOnly = true
module:Apply()
PROFILE.AuraBars = true               -- the player turned the aura bars on
UF:Update_PlayerFrame(player, {})     -- ElvUI re-enables them; our hook re-hides
assertCastbarOnly("profile changed to aura bars on, mode still on")
E.db.torment.castbarOnly = false
module:Apply()
assert(player:IsElementEnabled("AuraBars") and visible(player.AuraBars),
    "the profile at the moment the option goes off must win")
assert(player:IsElementEnabled("Health") and visible(player.ClassBarHolder),
    "and the five come back with it")

-- ------------------------------------------------------------- geometry check

-- The shipped layout's castbar versus the orbs. Numbers from the decoded export
-- The designer shipped (installer test 1 pins the bytes): bar1 and the player castbar
-- movers, bar1Scale, and the castbar's own size from the player unitframe.
local LAYOUT = {
    bar1 = "BOTTOM,ElvUIParent,BOTTOM,-4,4",
    castbar = "BOTTOM,ElvUIParent,BOTTOM,0,153",
    bar1Scale = 0.98,
    castbarWidth = 407,
    castbarHeight = 40,
}

local function parseMover(text, width, height)
    local _, _, x, y = text:match("^(%a+),ElvUIParent,(%a+),(-?%d+),(-?%d+)$")
    assert(x, "unparsed mover: " .. text)
    return {width = width, height = height, offsetX = tonumber(x), offsetY = tonumber(y)}
end

local function artGeometry(uiWidth)
    local art = module:GetArt()
    assert(art, "the bar art must exist to place the orbs")
    local scale = LAYOUT.bar1Scale
    local artWidth = art:GetWidth() / scale
    local artHeight = art:GetHeight() / scale
    assert(artWidth == 1416 and artHeight == 201, "the art is the shipped 1416x201 crop")
    local bar = parseMover(LAYOUT.bar1, artWidth * scale, artHeight * scale)
    local centreX = uiWidth / 2 + bar.offsetX
    local centreY = bar.offsetY + bar.height / 2
    local wells = module:GetGlobeWells()
    local orbs = {}
    for kind, well in pairs(wells) do
        orbs[kind] = {
            x = centreX + (well.centreX - artWidth / 2) * scale,
            y = centreY + (artHeight / 2 - well.centreY) * scale,
            r = well.diameter * scale / 2,
        }
    end
    return orbs
end

-- 1920x1080 at ElvUI's Auto Scale (768/1080) and 2560x1440 at its own (768/1440):
-- UIParent's coordinates are screen/scale, and every other value here is in
-- those same coordinates.
module:Initialize()      -- barart's pass builds the art and the wells
E.db.torment.bar1Scale = LAYOUT.bar1Scale
module:Apply()           -- lay the art out at the scale the designer shipped
for _, resolution in ipairs({{1920, 1080}, {2560, 1440}}) do
    local uiWidth = resolution[1] / math.max(0.4, math.min(1.15, 768 / resolution[2]))
    local orbs = artGeometry(uiWidth)
    local rect = parseMover(LAYOUT.castbar, LAYOUT.castbarWidth, LAYOUT.castbarHeight)
    local left, right = uiWidth / 2 + rect.offsetX - rect.width / 2, uiWidth / 2 + rect.offsetX + rect.width / 2
    local bottom, top = rect.offsetY, rect.offsetY + rect.height
    for kind, orb in pairs(orbs) do
        local dx = math.max(left - orb.x, 0, orb.x - right)
        local dy = math.max(bottom - orb.y, 0, orb.y - top)
        local distance = math.sqrt(dx * dx + dy * dy)
        assert(distance > orb.r,
            ("castbar at %dx%d must not overlap the %s orb (distance %.1f < radius %.1f)")
                :format(resolution[1], resolution[2], kind, distance, orb.r))
    end
    -- and it really does sit between them, not off the side of the art
    assert(left > orbs.health.x + orbs.health.r and right < orbs.power.x - orbs.power.r,
        ("the castbar must sit between the two orbs at %dx%d"):format(resolution[1], resolution[2]))
end

assert(#printed == 0, "the castbar-only mode must not print anything")
realPrint("test_elvui_castbar: all castbar-only mock checks passed")
