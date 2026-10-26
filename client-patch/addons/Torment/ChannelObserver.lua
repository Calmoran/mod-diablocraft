-- Observe stock 3.3.5a action paths and ElvUI's own bars, for every channelled skill on
-- ChannelSpells.lua: the press starts the channel, the release stops it. No bindings,
-- click attributes or buttons change; hooksecurefunc and HookScript only.
-- Why a key's release was lost on ElvUI: its bar keys are click bindings on a button registered
-- for the press half only, so the release reaches no script. When the client DLL's read-only
-- TormentKeyDown exists the release is read from it (docs/contracts/client-key-state.md); a
-- client without it behaves as before.
local AIO = AIO
local ids = Diablocraft.ChannelSpells
local held, released = {}, false
local keyed = {} -- buttons whose hold began with a bound key: the key table tells their release
local stopSent, releasePending = false, false
local started -- the spell id of the last start, for the stop message
local observer = CreateFrame("Frame")

-- The spell id of the channel the player runs, or nil when it is not a listed skill.
local function channeling()
    local name = UnitChannelInfo("player")
    if not name then return nil end
    if started and ids[started] and name == GetSpellInfo(started) then return started end
    for id in pairs(ids) do
        if name == GetSpellInfo(id) then return id end
    end
    return nil
end
-- Whirlwind keeps its own message until the server takes the generic one
-- (docs/contracts/skillbar-messages.md); every other listed skill sends Channel.
local function send(action, spell)
    if ids[spell] == "Whirlwind" then
        AIO.Handle("DiablocraftSkillbar", "Whirlwind", action, action == "start" and spell or nil)
    else
        AIO.Handle("DiablocraftSkillbar", "Channel", action, spell)
    end
end
local function spellFor(button)
    if not button then return end
    local action = button.action or ActionButton_GetPagedID(button)
    if not action or action <= 0 then
        -- ElvUI's LibActionButton buttons keep the spell in the secure "action"
        -- attribute; the Lua field stays 0 (LibActionButton-1.0.lua:184).
        action = button.GetAttribute and button:GetAttribute("action")
    end
    if not action or action <= 0 then return end
    local kind, id = GetActionInfo(action)
    if kind == "spell" and ids[id] then return id end
end
-- A bound key reaches an ElvUI button as a click with the cursor elsewhere; a mouse click has the
-- cursor over the button with the left button down. Either order of OnMouseDown and PreClick.
local function byMouse(button)
    return GetMouseFocus() == button and IsMouseButtonDown("LeftButton")
end
local function down(button, fromClick)
    local spell = spellFor(button)
    if not spell or held[button] then return end
    held[button], released, releasePending = spell, false, false
    started = spell
    keyed[button] = fromClick and not byMouse(button) or nil
    stopSent = false
    if not channeling() then send("start", spell) end
end
local function up(button)
    if not held[button] then return end
    held[button], keyed[button] = nil, nil
    if next(held) then return end
    released, releasePending = true, true
end
-- The keys behind an ElvUI bar button: the stock command it took its keys from
-- (button.keyBoundTarget, ElvUI ActionBars.lua:817) and a direct click binding.
local function releasedByKeys(button)
    local any, pressed = false, false
    for _, command in ipairs({button.keyBoundTarget or "", "CLICK " .. (button:GetName() or "") .. ":LeftButton"}) do
        if command ~= "" then
            for k = 1, select("#", GetBindingKey(command)) do
                local key = select(k, GetBindingKey(command))
                local state = key and TormentKeyDown(key)
                if state ~= nil then
                    any = true
                    if state then pressed = true end
                end
            end
        end
    end
    return any and not pressed
end
local function mainButton(id)
    if VehicleMenuBar:IsShown() and id <= VEHICLE_MAX_ACTIONBUTTONS then
        return _G["VehicleMenuBarActionButton"..id]
    elseif BonusActionBarFrame:IsShown() then
        return _G["BonusActionButton"..id]
    end
    return _G["ActionButton"..id]
end
hooksecurefunc("ActionButtonDown", function(id) down(mainButton(id)) end)
hooksecurefunc("ActionButtonUp", function(id) up(mainButton(id)) end)
hooksecurefunc("MultiActionButtonDown", function(bar,id) down(_G[bar.."Button"..id]) end)
hooksecurefunc("MultiActionButtonUp", function(bar,id) up(_G[bar.."Button"..id]) end)
for _, prefix in ipairs({"ActionButton", "BonusActionButton", "VehicleMenuBarActionButton",
                         "MultiBarBottomLeftButton", "MultiBarBottomRightButton",
                         "MultiBarLeftButton", "MultiBarRightButton"}) do
    -- constant: stock action bars have 12 buttons.
    for id=1,12 do
        local button = _G[prefix..id]
        if button then
            button:HookScript("OnMouseDown", function(self,key) if key=="LeftButton" then down(self) end end)
            button:HookScript("OnMouseUp", function(self,key) if key=="LeftButton" then up(self) end end)
        end
    end
end

-- ElvUI's bars, the default UI (12-ui; UI fixes row 14): its buttons are
-- LibActionButton CheckButtons, whose keys are SetOverrideBindingClick
-- bindings (ElvUI 6.09 ActionBars.lua:396) that never call ActionButtonDown/Up,
-- and whose click rides PreClick/the secure OnClick on ONE half (the press under
-- ElvUI's keyDown default). Observe the buttons themselves: PreClick covers a bound
-- key's press, OnMouseDown/Up the mouse; a key's release is read from the key table. ElvUI
-- builds its six bars of twelve at Initialize (its PLAYER_LOGIN), so the scan
-- runs on the login events and hooks each button once.
local elvuiSeen = {}
local function watchElvUIButton(button)
    if not button or elvuiSeen[button] then return end
    elvuiSeen[button] = true
    button:HookScript("PreClick", function(self) down(self, true) end)
    button:HookScript("OnMouseDown", function(self,key) if key=="LeftButton" then down(self) end end)
    button:HookScript("OnMouseUp", function(self,key) if key=="LeftButton" then up(self) end end)
end
local function watchElvUI()
    for bar=1,6 do
        for id=1,12 do
            watchElvUIButton(_G["ElvUI_Bar"..bar.."Button"..id])
        end
    end
end
observer:RegisterEvent("PLAYER_LOGIN")
observer:RegisterEvent("PLAYER_ENTERING_WORLD")
observer:RegisterEvent("UNIT_SPELLCAST_CHANNEL_START")
observer:RegisterEvent("UNIT_SPELLCAST_CHANNEL_STOP")
observer:SetScript("OnEvent", function(self,event,unit)
    if event=="PLAYER_LOGIN" or event=="PLAYER_ENTERING_WORLD" then
        watchElvUI()
        return
    end
    if unit ~= "player" then return end
    if event=="UNIT_SPELLCAST_CHANNEL_START" and released and channeling() then
        releasePending, stopSent = true, false
    end
end)
observer:SetScript("OnUpdate", function()
    -- A bound key let go (or the window lost focus, which reads every key false) is a release.
    if type(TormentKeyDown) == "function" and next(keyed) then
        for button in pairs(keyed) do
            if held[button] and releasedByKeys(button) then up(button) end
        end
    end
    -- Defer mouse release until after the stock AnyUp click. A quick tap may
    -- receive channel-start after release; that event queues the same guarded stop.
    local spell = releasePending and not stopSent and channeling()
    if spell then
        send("stop", spell)
        stopSent, releasePending = true, false
    end
end)
