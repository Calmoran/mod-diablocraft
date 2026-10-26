-- luacheck: globals ElvUI InCombatLockdown CreateFrame hooksecurefunc
-- ElvUI_Torment castbar-only player frame.
--
-- ElvUI's player frame stays enabled and this
-- module hides everything of it except the castbar - health, power, portrait,
-- name and texts, the frame's own backdrop and border, the info panel, the
-- auras - and makes the invisible frame click-through so it never blocks a
-- click or a target. Torment's orbs already draw health and resource.
--
-- Why DisableElement and not just Hide: every hidden part is an oUF element,
-- and each element Show()s its own object from its own unit events
-- (Elements/Power.lua:66 `power:Show()`, Elements/Portrait.lua:60/82,
-- Elements/InfoPanel.lua:23). Hiding the object once would be undone by the
-- next event; disabling the element hides it and takes it out of the event
-- loop. ElvUI's own Update_PlayerFrame enables the elements its profile asks
-- for on every layout, so this module runs its pass directly after that update
-- (hooked below), which is also what carries it through a profile change, a
-- /reload, an ElvUI option change and the config being opened.
--
-- No OnUpdate loop, ever: the pass runs from ElvUI's own player-frame update
-- and the two events below.
--
-- Turning the option off is a restore ONCE, on that change only: ElvUI's own
-- UF.player:Update() puts back every element and object its Configure_*
-- functions own, exactly as the profile asks - an aura bar or portrait the
-- profile has off stays off - and then restore() hands back the four things
-- ElvUI never gives back because it never hides them (Health, Name,
-- ClassBarHolder, RaisedElementParent, see ALWAYS_BACK). While the option is
-- off this module does nothing at all, so ElvUI's own updates are never
-- overridden.
--
-- The texts ElvUI draws over the frame (Health.value, Power.value,
-- frame.customTexts) are FontStrings on frame.RaisedElementParent, so hiding
-- that frame hides the numbers; the castbar is created on the frame itself and
-- is a sibling of it, so it stays.
--
-- Taint: ElvUF_Player is a secure unit button (oUF creates it from
-- SecureUnitButtonTemplate). Nothing here changes its secure attributes, size
-- or show state, and frame:EnableMouse is a protected call, so the whole pass
-- is deferred to PLAYER_REGEN_ENABLED while InCombatLockdown() is true.
--
-- Listed in the TOC after orbs.lua; barart.lua creates the module table and
-- calls module:ApplyCastbarOnly() from its own geometry pass, which is already
-- combat-deferred, so an options change re-applies immediately.
local E = unpack(ElvUI)
local module = E:GetModule("ElvUI_Torment")

local InCombatLockdown = InCombatLockdown
local hooksecurefunc = hooksecurefunc

-- The oUF elements whose objects are part of the hidden frame, using the names
-- ElvUI 6.09 actually enables on a unit frame (the module's own EnableElement
-- calls; LeaderIndicator/MasterLooterIndicator/AssistantIndicator/GroupRoleIndicator,
-- not the never-enabled RaidRoleIndicator). "Castbar" is deliberately absent:
-- it is what stays. Disabling an element that is not enabled on this frame
-- (Runes on anything but a death knight, and so on) is a no-op in oUF.
local ELEMENTS = {
    "Health", "Power", "Portrait", "Auras", "AuraBars", "Cutaway", "DebuffHighlight",
    "ThreatIndicator", "RestingIndicator", "CombatIndicator", "PvPIndicator",
    "RaidTargetIndicator", "LeaderIndicator", "MasterLooterIndicator",
    "AssistantIndicator", "GroupRoleIndicator", "HealComm4", "Runes",
    "AdditionalPower", "ComboPoints",
}

-- Objects hidden by name, all children of ElvUF_Player. frame.Castbar, its
-- Holder and its mover are not in the list, so the castbar keeps its position,
-- its mover and its options.
-- There are no iborder/oborder entries: those come from ElvUI's SetTemplate
-- (Core/Toolkit.lua:102-125), and 6.09 never templates ElvUF_Player. The only
-- path that could is ToggleTransparentStatusBar's parent branch
-- (UnitFrames.lua:1307), and it is not reached, because a unit frame's bars
-- always have a backdrop of their own - health does (Health.lua:206 calls it
-- with frame.Health, and the health bar's own backdrop takes the first branch
-- at UnitFrames.lua:1304). So the frame has no backdrop and no border frames of
-- its own to hide.
-- RaisedElementParent carries the texts ElvUI draws over the frame: Health.value
-- (Health.lua:41), Power.value (Power.lua:31) and frame.customTexts
-- (CustomText.lua:23) are all FontStrings on it, so hiding it hides the numbers
-- with them. The castbar is created on the frame itself (CastBar.lua:33), not
-- on RaisedElementParent, so it stays.
local PARTS = {
    "Health", "Power", "Name", "Portrait", "Portrait2D", "Portrait3D",
    "Buffs", "Debuffs", "AuraBars", "InfoPanel", "ClassBarHolder", "Cutaway",
    "DebuffHighlight", "ThreatIndicator", "RestingIndicator", "CombatIndicator",
    "PvPText", "RaidTargetIndicator", "RaidRoleFramesAnchor", "HealCommBar",
    "RaisedElementParent", "MouseGlow", "TargetGlow",
}

-- The option is a profile key (options.lua seeds ElvUI[4].torment.castbarOnly),
-- on by default: the Torment layout is castbar-only.
local function enabled()
    local db = E.db and E.db.torment
    local value = db and db.castbarOnly
    if type(value) == "boolean" then return value end
    return true
end

local function playerFrame()
    local UF = E:GetModule("UnitFrames")
    return UF and UF.player
end

-- The mode is on: our pass is (or was) in force. Set false the moment the
-- option goes off, before ElvUI's own update runs our hook again.
local modeOn = false
local mouseOff = false     -- our own EnableMouse(false) is in force

-- What ElvUI's own player-frame update does not give back in 6.09, whatever the
-- profile says, because ElvUI never hides it in the first place:
--   Health          - only oUF's spawn loop ever enables and shows it
--                     (ouf.lua:426-428); Configure_HealthBar ForceUpdates only
--                     an already-enabled bar (Elements/Health.lua:206-212).
--   Name            - Name.lua creates and repositions it, never toggles it
--                     (a profile with "no name" is a blank text_format).
--   ClassBarHolder  - created once, never shown or hidden (ClassBars.lua:21);
--                     nil on a class without one, which the loop below skips.
--   RaisedElementParent - ours and ElvUI's alone: ElvUI fills it, never hides
--                     it, and it carries the value and custom-text FontStrings.
-- Everything else IS handled by frame:Update() as the profile asks, so this
-- list must stay exactly this long: adding a profile-controlled part here would
-- bring back something the player has turned off.
local ALWAYS_BACK = {"Name", "ClassBarHolder", "RaisedElementParent"}

local function hide(frame)
    for _, name in ipairs(ELEMENTS) do
        if frame.IsElementEnabled and frame:IsElementEnabled(name) then
            frame:DisableElement(name)
        end
    end
    for _, name in ipairs(PARTS) do
        local part = frame[name]
        if part and part.Hide then part:Hide() end
    end
    if not mouseOff then
        mouseOff = true
        frame:EnableMouse(false)
    end
end

local function restore(frame)
    -- Runs once, on the on->off change only, out of combat. ElvUI's own update
    -- for the player frame re-enables and re-shows everything its Configure_*
    -- functions own, exactly as the profile asks, and then the five above are
    -- handed back explicitly. No recording of what the pass took: on a fresh
    -- login the first hide happens INSIDE Update_PlayerFrame (Configure_HealthBar
    -- runs before Power, Portrait, Auras, AuraBars, ... - Units/Player.lua:104-143
    -- - and the health element's update is what fires our ToggleTransparentStatusBar
    -- hook, Health.lua:206), so anything recorded there would be oUF's spawn
    -- state, not the profile. (That same health path re-templates the health
    -- bar's own backdrop at UnitFrames.lua:1304, not the frame - the frame has
    -- no backdrop; see PARTS.)
    modeOn = false                      -- before the update, so our hook is a no-op
    if frame.Update then frame:Update() end
    if frame.IsElementEnabled and not frame:IsElementEnabled("Health") then
        frame:EnableElement("Health")
    end
    for _, name in ipairs(ALWAYS_BACK) do
        local part = frame[name]
        if part and part.Show then part:Show() end
    end
    if mouseOff then
        mouseOff = false
        frame:EnableMouse(true)
    end
end

-- The one entry point: options, ElvUI updates and events all end up here.
-- In combat it does nothing at all: the pass is queued simply by not running,
-- and PLAYER_REGEN_ENABLED below calls this again.
local function apply()
    local frame = playerFrame()
    if not frame then return end
    if InCombatLockdown() then
        return                          -- PLAYER_REGEN_ENABLED runs this again
    end
    if enabled() then
        modeOn = true
        hide(frame)                     -- idempotent: undoes ElvUI's re-shows
    elseif modeOn then
        restore(frame)
    end
    -- Option off and nothing to restore: do nothing at all, so ElvUI's own
    -- updates for the profile are left exactly as they are.
end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:SetScript("OnEvent", function()
    apply()
end)

-- ElvUI's own update path, so a re-show is always followed by our pass. One
-- hook is enough: Update_PlayerFrame is the player frame's own update, which
-- Update_AllFrames and CreateAndUpdateUF both end up calling, and the parts it
-- re-shows are the only ones that can come back while the mode is on (the
-- elements that show themselves from unit events are disabled here, and ElvUI
-- never re-enables Health). ToggleTransparentStatusBar and
-- SetStatusBarBackdropPoints are not hooked: they only re-template a bar's own
-- backdrop, which is not part of this frame (see PARTS).
local function hookAll()
    local UF = E:GetModule("UnitFrames")
    if UF then
        -- Update_PlayerFrame is the player frame's own update, which
        -- Update_AllFrames and CreateAndUpdateUF both end up calling, so one
        -- hook covers every layout path.
        hooksecurefunc(UF, "Update_PlayerFrame", apply)
    end
end

hookAll()

-- Called from barart's ApplyGeometry, after the art and the orbs are laid out.
function module:ApplyCastbarOnly()
    apply()
end

-- Read-only, for the tests and for debugging in game.
function module:IsCastbarOnly() return enabled() end
