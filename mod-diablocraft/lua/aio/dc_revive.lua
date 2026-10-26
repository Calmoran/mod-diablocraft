-- dc_revive.lua - the death window (docs/contracts/revive-choices-messages.md).
--
-- D3's death screen: no window box, "YOU HAVE
-- DIED." straight on the game view, and three wide dark-red buttons under it. A Normal death
-- offers three ways back - REVIVE AT CORPSE (where it fell), REVIVE AT CHECKPOINT (the start of the
-- rift floor it died on) and REVIVE IN TOWN (the hub, with the way-back portal when it died in a
-- rift). The window asks the server (`options`) and draws what it answers: all three buttons
-- always, each live or greyed with the server's reason as its tooltip (Revive R2).
-- Every button sends one verb and the server decides everything. Nothing here moves the character
-- and nothing here calls the stock RepopMe.
--
-- The buttons are named `Diablocraft.ART` slots (`death-button`, `-hover`, `-pressed`, `-disabled`
-- and the `-glow` behind them). No image ships for them: without a skin the window draws the slot's
-- flat colour with a thin bronze edge, and the private TormentD3 skin fills the slots with D3's
-- button frames. Nothing here is Blizzard art; a client without the Torment addon gets the flat
-- colours from FLAT_COLOUR below.
--
-- The stock DEATH dialog is never drawn while this file is loaded: the wrapper at the bottom stops
-- it at `StaticPopup_Show`, its own code untouched, so the automatic-release timer and the
-- no-addon fallback still exist. Hardcore has no buttons: the server refuses `options` for a
-- Hardcore character, and the window is only drawn on the successful `O` answer, never a refusal.
-- luacheck: globals DCRevive Diablocraft UnitIsDeadOrGhost StaticPopup_Show GameTooltip
local AIO = AIO or require("AIO")
if AIO.AddAddon() then return end

local PREFIX = "DCREVIVE"
local FLAT = "Interface\\Buttons\\WHITE8X8"
local FLAT_BACKDROP = {bgFile = FLAT, edgeFile = FLAT, edgeSize = 1,
    insets = {left = 1, right = 1, top = 1, bottom = 1}}
local EXOCET = "Interface\\AddOns\\Torment\\fonts\\Exocet.ttf"

-- The look, all of it in one place. The y offsets are from the screen's centre (0,0); the title
-- sits above it and the buttons below, D3's own arrangement.
local LOOK = {
    titleSize = 40, titleGlowSize = 50, titleY = 150,
    titleColour = {.93, .87, .71}, titleGlow = {.93, .78, .42, .22},
    hintSize = 15, hintY = -330, hintColour = {.85, .25, .20},
    width = 440, height = 52, gap = 8, topY = -140,
    edge = {.62, .47, .26},              -- the thin bronze edge without a skin
    labelSize = 16, labelColour = {.95, .91, .84}, labelDisabled = {.42, .40, .36},
}
-- The three options, in D3's order top to bottom, which is also the order of the O record's fields.
local OPTIONS = {
    {key = "corpse", verb = "here", label = "REVIVE AT CORPSE"},
    {key = "checkpoint", verb = "checkpoint", label = "REVIVE AT CHECKPOINT"},
    {key = "town", verb = "town", label = "REVIVE IN TOWN"},
}
-- The flat colours, for a client without the Torment addon. With the addon they are the `colour`
-- of the same-named slot in Diablocraft.ART, which is where a skin's `path` goes instead.
local FLAT_COLOUR = {
    ["death-button"] = {.30, .05, .05, 1}, ["death-button-hover"] = {.42, .09, .07, 1},
    ["death-button-pressed"] = {.20, .03, .03, 1}, ["death-button-disabled"] = {.16, .14, .13, 1},
}

-- A font the client cannot load leaves a FontString with no font at all, which draws nothing (and
-- errors, dc_riftbar.lua:91). Probed once, like the tooltip's own fonts; without the Torment addon
-- the stock font object on the FontString stays.
local function usableFont(path)
    if not CreateFrame then return false end
    local probe = CreateFrame("Frame"):CreateFontString(nil, "OVERLAY")
    probe:SetFont(path, 16, "")
    return probe:GetFont() ~= nil
end
local HAS_EXOCET = usableFont(EXOCET)
local function font(fs, size)
    if HAS_EXOCET then fs:SetFont(EXOCET, size, "") end
    return fs
end

local function slot(name)
    return Diablocraft and Diablocraft.ART and Diablocraft.ART[name]
end
-- The slot's own image wins; otherwise the slot's flat colour; otherwise FLAT_COLOUR.
local function artOf(name) local art = slot(name) return art and (art.path or art.file) and art end
local function colourOf(name)
    local art = slot(name)
    return (art and art.colour) or (name == "death-button-glow" and {0, 0, 0, 0}) or FLAT_COLOUR[name]
end

------------------------------------------------------------------------------------------------
-- The window: the title, three stacked buttons, and the server's last refusal under them
------------------------------------------------------------------------------------------------
local frame = CreateFrame("Frame", "DiablocraftReviveFrame", UIParent)
frame:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
frame:SetSize(LOOK.width + 40, 640) -- tall enough for the title above the centre and the buttons below
frame:SetFrameStrata("HIGH")
frame:EnableMouse(false) -- only the buttons take the mouse: the rest is the game view
frame:Hide()

-- D3's title is cream with a soft glow. No blur in 3.3.5a, so a larger, dimmer copy behind the
-- text draws the halo, and the title itself sits on top of it.
local glow = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
font(glow, LOOK.titleGlowSize)
glow:SetPoint("CENTER", frame, "CENTER", 0, LOOK.titleY)
glow:SetText("YOU HAVE DIED.")
glow:SetTextColor(LOOK.titleGlow[1], LOOK.titleGlow[2], LOOK.titleGlow[3], LOOK.titleGlow[4])
local title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
font(title, LOOK.titleSize)
title:SetPoint("CENTER", frame, "CENTER", 0, LOOK.titleY)
title:SetText("YOU HAVE DIED.")
title:SetTextColor(LOOK.titleColour[1], LOOK.titleColour[2], LOOK.titleColour[3])
-- The smaller second line D3 uses for its death penalty ("YOUR ITEMS HAVE LOST 10% DURABILITY.")
-- is not drawn: Torment's death takes durability too, but the window is told no penalty number by
-- the server, and a number here would be an invented one. One line goes in when one is sourced.

local hint = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
font(hint, LOOK.hintSize)
hint:SetPoint("CENTER", frame, "CENTER", 0, LOOK.hintY)
hint:SetTextColor(LOOK.hintColour[1], LOOK.hintColour[2], LOOK.hintColour[3])

local function send(verb)
    SendAddonMessage(PREFIX, verb, "WHISPER", UnitName("player"))
end

-- The slot's art on one button. One texture, or three when the slot says its ends are fixed
-- (`slices`): the child client has no 9-slice, and stretching a frame's ornate ends 3x wide reads as
-- a smear, so the caps are drawn at the slot's own crops and only the straight middle stretches.
-- The caps' on-screen widths come from the crops, so the layout is the window's either way.
local function paintArt(button, name)
    local art = artOf(name)
    if not (art and Diablocraft.SetArt) then
        button.artL:Hide(); button.artM:Hide(); button.artR:Hide()
        return false
    end
    local coords = art.coords or {0, 1, 0, 1}
    local slices = art.slices
    if not slices then
        button.artL:Hide(); button.artR:Hide()
        button.artM:ClearAllPoints()
        button.artM:SetAllPoints()
        button.artM:Show()
        Diablocraft.SetArt(button.artM, name)
        return true
    end
    local left, right, top, bottom = coords[1], coords[2], coords[3], coords[4]
    local crop = right - left
    button.artM:Hide()
    button.artL:ClearAllPoints()
    button.artL:SetPoint("TOPLEFT", button, "TOPLEFT", 0, 0)
    button.artL:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 0, 0)
    button.artL:SetWidth(LOOK.width * slices.left / crop)
    button.artR:ClearAllPoints()
    button.artR:SetPoint("TOPRIGHT", button, "TOPRIGHT", 0, 0)
    button.artR:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", 0, 0)
    button.artR:SetWidth(LOOK.width * slices.right / crop)
    button.artL:Show(); button.artR:Show()
    Diablocraft.SetArt(button.artL, name, {left, left + slices.left, top, bottom})
    Diablocraft.SetArt(button.artR, name, {right - slices.right, right, top, bottom})
    button.artM:Show()
    button.artM:ClearAllPoints()
    button.artM:SetPoint("LEFT", button.artL, "RIGHT", 0, 0)
    button.artM:SetPoint("RIGHT", button.artR, "LEFT", 0, 0)
    button.artM:SetPoint("TOP", button, "TOP", 0, 0)
    button.artM:SetPoint("BOTTOM", button, "BOTTOM", 0, 0)
    Diablocraft.SetArt(button.artM, name, {left + slices.left, right - slices.right, top, bottom})
    return true
end

-- One button's state: the slot the skin fills, or the slot's flat colour with the bronze edge.
local function paint(button, state)
    if not button.dcEnabled then state = "disabled" end
    local name = state == "normal" and "death-button" or "death-button-" .. state
    if paintArt(button, name) then
        button:SetBackdropColor(0, 0, 0, 0)
        -- The skin's frame carries its own edge; the flat fill keeps ours.
        if artOf(name) then button:SetBackdropBorderColor(0, 0, 0, 0)
        else button:SetBackdropBorderColor(LOOK.edge[1], LOOK.edge[2], LOOK.edge[3], 1) end
    else
        local colour = colourOf(name)
        button:SetBackdropColor(colour[1], colour[2], colour[3], colour[4] or 1)
        button:SetBackdropBorderColor(LOOK.edge[1], LOOK.edge[2], LOOK.edge[3], 1)
    end
    if artOf("death-button-glow") and Diablocraft.SetArt then
        Diablocraft.SetArt(button.glow, "death-button-glow")
        button.glow:Show()
    else
        button.glow:Hide()
    end
    local label = button.dcEnabled and LOOK.labelColour or LOOK.labelDisabled
    button.label:SetTextColor(label[1], label[2], label[3])
end

local buttons = {}
for index, option in ipairs(OPTIONS) do
    local button = CreateFrame("Button", nil, frame)
    button:SetSize(LOOK.width, LOOK.height)
    button:SetPoint("CENTER", frame, "CENTER", 0, LOOK.topY - (index - 1) * (LOOK.height + LOOK.gap))
    button:SetBackdrop(FLAT_BACKDROP)
    button:SetFrameLevel(frame:GetFrameLevel() + 2)
    button.dcEnabled = true
    button.glow = button:CreateTexture(nil, "BACKGROUND")
    button.glow:SetPoint("TOPLEFT", -8, 8)
    button.glow:SetPoint("BOTTOMRIGHT", 8, -8)
    button.glow:SetBlendMode("ADD")
    button.glow:Hide()
    button.artL = button:CreateTexture(nil, "ARTWORK")
    button.artL:Hide()
    button.artM = button:CreateTexture(nil, "ARTWORK")
    button.artM:SetAllPoints()
    button.artM:Hide()
    button.artR = button:CreateTexture(nil, "ARTWORK")
    button.artR:Hide()
    button.label = font(button:CreateFontString(nil, "OVERLAY", "GameFontNormal"), LOOK.labelSize)
    button.label:SetPoint("CENTER", button, "CENTER", 0, 0)
    button.label:SetText(option.label)
    button:SetScript("OnClick", function() if button.dcEnabled then send(option.verb) end end)
    -- A greyed button still takes the hover (the stock micro buttons show their "level N" tooltip
    -- from OnEnter while disabled, MainMenuBarMicroButtons.xml:13-16), and says why it is greyed.
    button:SetScript("OnEnter", function()
        paint(button, "hover")
        if button.dcReason ~= "" then
            GameTooltip:SetOwner(button, "ANCHOR_RIGHT")
            GameTooltip:SetText(button.dcReason, 1, 1, 1, 1, true)
            GameTooltip:Show()
        end
    end)
    button:SetScript("OnLeave", function() paint(button, "normal"); GameTooltip:Hide() end)
    button:SetScript("OnMouseDown", function() paint(button, "pressed") end)
    button:SetScript("OnMouseUp", function() paint(button, "normal") end)
    button.dcReason = ""
    paint(button, "normal")
    buttons[option.key] = button
end

-- The whole-window slot, when the Torment addon has it: the title and the
-- three buttons in their top-to-bottom order go on a skin's canvas, and the glow follows the title.
local skinWindow = Diablocraft and Diablocraft.Style and Diablocraft.Style.Window
if skinWindow then
    local order = {}
    for _, option in ipairs(OPTIONS) do order[#order + 1] = buttons[option.key] end
    skinWindow(frame, "revive", {title = title, buttons = order})
    if frame.dcCanvas then
        glow:ClearAllPoints()
        glow:SetPoint("CENTER", title, "CENTER", 0, 0)
    end
end

-- The unavailable state (D3 greys the option it cannot offer rather than hiding it); `reason` is the
-- server's text, shown as the greyed button's tooltip.
local function grey(key, greys, reason)
    local button = buttons[key]
    if not button then return end
    button.dcEnabled = not greys
    button.dcReason = greys and reason or ""
    if greys then button:Disable() else button:Enable() end
    paint(button, "normal")
end
DCRevive = {Grey = grey}

------------------------------------------------------------------------------------------------
-- The wire: one ask per death, and the three records the contract defines
------------------------------------------------------------------------------------------------
-- `asked` keeps the ask to one per death; `shown` tells a refusal before the window is up (a
-- Hardcore death) from one after it (which keeps the buttons up).
local asked, shown = false, false

local function hide()
    shown = false
    frame:Hide()
end

local function show()
    shown = true
    hint:SetText("")
    for _, button in pairs(buttons) do paint(button, "normal") end -- a skin may have loaded since
    frame:Show()
end

local function ask()
    asked = true
    send("options")
end

local function split(value)
    local fields = {}
    for field in (value .. "|"):gmatch("(.-)|") do fields[#fields + 1] = field end
    return fields
end

local function onMessage(prefix, body, distribution, sender)
    if prefix ~= PREFIX or distribution ~= "WHISPER" then return end
    local own = UnitName("player")
    if sender ~= own and sender ~= own .. "-" .. GetRealmName() then return end
    local fields = split(body)
    if fields[1] == "O" then
        -- `O|corpse|checkpoint|town`: each field is 1 (live) or the reason it is not.
        for index, option in ipairs(OPTIONS) do
            local field = fields[index + 1] or ""
            grey(option.key, field ~= "1", field)
        end
        show()
    elseif fields[1] == "R" then
        -- The character is alive; the stock PLAYER_ALIVE closes the window too. The server's own chat
        -- line names where it landed, so the record's asked/done needs no text here.
        hide()
    elseif fields[1] == "X" and shown then
        -- A refusal after the window is up: show the server's text and leave the buttons up.
        hint:SetText(fields[2] or "")
    end
end

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("PLAYER_DEAD")
watcher:RegisterEvent("PLAYER_ALIVE")
watcher:RegisterEvent("PLAYER_ENTERING_WORLD")
watcher:RegisterEvent("CHAT_MSG_ADDON")
watcher:SetScript("OnEvent", function(_, event, arg1, arg2, arg3, arg4)
    if event == "PLAYER_DEAD" then
        asked = false
        ask()
    elseif event == "PLAYER_ALIVE" then
        asked = false
        hide()
    elseif event == "PLAYER_ENTERING_WORLD" then
        -- Login or /reload while dead: the window asks once (contract, Requests).
        if not asked and UnitIsDeadOrGhost("player") then ask() end
    elseif event == "CHAT_MSG_ADDON" then
        onMessage(arg1, arg2, arg3, arg4)
    end
end)

------------------------------------------------------------------------------------------------
-- The stock DEATH dialog
------------------------------------------------------------------------------------------------
-- UIParent's PLAYER_DEAD handler shows it through this global; the wrapper answers for it instead.
-- The dialog's own definition is never edited, so the automatic-release timer and the no-addon
-- fallback still work.
local stockShow = StaticPopup_Show
StaticPopup_Show = function(which, ...)
    if which == "DEATH" then return end
    return stockShow(which, ...)
end
