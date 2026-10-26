-- luacheck: globals ElvUI ElvUI_TormentDB PluginInstallFrame ReloadUI
-- ElvUI_Torment in-game installer.
--
-- Applies the exported ElvUI layout (profile.lua) as a profile named
-- "Torment" and makes it this character's active profile. The pages ride
-- ElvUI's own PluginInstaller (E:GetModule("PluginInstaller"):Queue(table)),
-- so the window, its Next/Prev buttons and its styling are ElvUI's.
--
-- It also marks ElvUI's install_complete so the stock ElvUI wizard never shows
-- on a character that has not done it; the Torment installer is then the only
-- wizard a new character sees.
--
-- Listed in the TOC after barart.lua, which creates the module table.
--
-- What it must never do: write any profile other than "Torment" - the profile
-- written is always the one this addon owns, and the string's own key is never
-- used to pick one - touch the wizard state of a character that
-- already went through ElvUI's wizard, or change ElvUI's own files.
local E = unpack(ElvUI)
local module = E:GetModule("ElvUI_Torment")

local format, tostring, type = string.format, tostring, type

-- The profile key this addon owns. Never the key inside the export string.
local PROFILE_NAME = "Torment"

-- Distributor.lua's blacklistedKeys.profile, the same filter ElvUI applies when
-- a player pastes a profile into /ec. It only drops general.numberPrefixStyle.
local PROFILE_BLACKLIST = {general = {numberPrefixStyle = true}}

local Installer = {}
module.installer = Installer

-- Profile import ------------------------------------------------------------
--
-- Decoded with ElvUI's own Distributor at apply time, exactly as the Import
-- Profile box does (LibBase64 -> LibCompress -> AceSerializer), then written
-- straight into profiles["Torment"] instead of through D:ImportProfile, because
-- that function can only target the key the string already carries.
function Installer:ApplyProfile()
    local D = E:GetModule("Distributor")
    if not D then
        return false, "ElvUI's Distributor module is not loaded"
    end

    local profileType, _, data = D:Decode(module.layoutExport)
    if profileType ~= "profile" or type(data) ~= "table" then
        return false, format("the shipped layout is a %s export, not a profile", tostring(profileType))
    end

    data = E:FilterTableFromBlacklist(data, PROFILE_BLACKLIST)

    -- No ID line and no Count line on any tooltip: ElvUI is told not to add
    -- them (its own switches, Settings/Profile.lua:1195-1196; "NONE" is an Item Count option,
    -- ElvUI_OptionsUI/Tooltip.lua:105-115). Set here, on top of the export, so its bytes stay
    -- as exported.
    data.tooltip = data.tooltip or {}
    data.tooltip.spellID = false
    data.tooltip.itemCount = "NONE"

    -- The buff bar's icons anchor at the container's bottom-left and run one row
    -- along its bottom edge, D3's corner. ElvUI's own default is LEFT_DOWN — horizontal growth
    -- anchored top-right — so the container is wide (Modules/Auras.lua
    -- ConfigureAuras: (horizontalSpacing+size)*wrapAfter wide). UP_RIGHT is
    -- VERTICAL growth (not in IS_HORIZONTAL_GROWTH), which turned the same
    -- container into a one-icon-wide column; RIGHT_UP is the horizontal
    -- direction whose DIRECTION_TO_POINT is BOTTOMLEFT, so it keeps the wide
    -- size and puts the icons along the bottom edge, left to right. Buffs only,
    -- set on top of the export exactly as the tooltip switches above.
    data.auras = data.auras or {}
    data.auras.buffs = data.auras.buffs or {}
    data.auras.buffs.growthDirection = "RIGHT_UP"

    -- The layout's private settings, from the matching private export: the
    -- name font, the global bar texture and the auras
    -- skin switch. Written key by key onto the character's own private table,
    -- never by importing the private string - ElvUI's Distributor applies that
    -- by replacing the whole private profile and asking for a reload
    -- (Distributor.lua SetImportedProfile / IMPORT_RL), which would drop every
    -- other private setting the player has. Both names
    -- are ElvUI's own media (Media/SharedMedia.lua registers the font
    -- "Continuum Medium" and the statusbar "Minimalist"), so nothing new ships.
    -- Written before SetProfile so its UpdateAll -> UpdateMedia reads them.
    E.private.general = E.private.general or {}
    E.private.general.namefont = "Continuum Medium"
    E.private.general.normTex = "Minimalist"
    E.private.auras = E.private.auras or {}
    E.private.auras.lbf = E.private.auras.lbf or {}
    E.private.auras.lbf.enable = true

    -- Overwriting the profile that is already active does not refresh E.db -
    -- it still references the table we are replacing - so make the key look
    -- different first. This is ElvUI's own Distributor trick (Distributor.lua,
    -- SetImportedProfile); SetProfile then fires OnProfileChanged -> UpdateAll.
    if E.data.profiles[PROFILE_NAME] and E.data.keys.profile == PROFILE_NAME then
        E.data.keys.profile = PROFILE_NAME .. "_Temp"
    end

    E.data.profiles[PROFILE_NAME] = data

    -- SetProfile fires ElvUI's OnProfileChanged -> E:UpdateAll (Core.lua:1264),
    -- which redraws the Layout module's panels (Core.lua:874,
    -- Layout:BottomPanelVisibility). Layout makes them in its Initialize
    -- (Layout/Layout.lua:24); if that threw at login, CallbackHandler reported it
    -- and ElvUI carried on without them, and UpdateAll dies on the nil
    -- BottomPanel. The live redraw is only a preview - the
    -- Done page's reload is what applies the profile - so without the panels the
    -- profile is switched with ElvUI's handler off, and the reload does the rest.
    if E:GetModule("Layout").BottomPanel then
        E.data:SetProfile(PROFILE_NAME)
    else
        E.data.UnregisterCallback(E, "OnProfileChanged")
        E.data:SetProfile(PROFILE_NAME)
        E.data.RegisterCallback(E, "OnProfileChanged", "UpdateAll")
    end

    return true
end

-- Installer pages -----------------------------------------------------------

-- The UI Scale page owns a slider of its own; PluginInstaller's ResetAll only
-- knows its own buttons and texts, so every one of our pages hides the slider
-- first and only the scale page shows it again.
local scaleSlider
local function hideScale()
    if scaleSlider then scaleSlider:Hide() end
end

local function pageWelcome()
    local f = PluginInstallFrame
    hideScale()
    f.SubTitle:SetText("Torment layout")
    f.Desc1:SetText("Torment draws the Diablo III interface: the D3 orbs and bottom bar, the blacksmith, stash and bag screens, and the skill bar art.")
    f.Desc2:SetText("This installer applies the Torment UI to ElvUI: one profile named \"Torment\", made your active profile.")
    f.Desc3:SetText("Press Next, then Apply the Torment layout. Any other ElvUI profile on this account is left untouched.")
end

local function pageApply()
    local f = PluginInstallFrame
    hideScale()
    f.SubTitle:SetText("Apply the Torment layout")
    f.Desc1:SetText("Applies the Torment layout as an ElvUI profile named \"Torment\" and makes it your active profile.")
    f.Desc2:SetText("ElvUI's other profiles and their settings are not changed.")

    f.Option1:Show()
    f.Option1:SetText("Apply the Torment layout")
    f.Option1:SetScript("OnClick", function()
        local ok, err = Installer:ApplyProfile()
        if ok then
            -- 6.09 stores this as a plain function - `f.SetPage = SetPage`
            -- (PluginInstaller.lua:202), where SetPage(PageNum, PrevPage) is a
            -- local at line 100 - so it is called with (3, 2), never f:SetPage.
            -- A colon call passes the frame as the page number and dies in the
            -- status bar's animation.
            f.SetPage(3, 2)
        else
            f.Desc3:SetText("Could not apply the layout: " .. tostring(err))
            f.Option1:SetText("Retry")
        end
    end)
end

-- UI Scale. ElvUI's own UI Scale page, its way
-- (ElvUI/Core/Install.lua:577-612): one slider over E.global.general.UIScale
-- (ElvUI/Settings/Global.lua:5) and Auto Scale, and both only SET the value -
-- no rescale while the slider moves. ElvUI's page applies through its Preview
-- button, E:PixelScaleChanged(nil, true), and so does this one. There are no
-- resolution presets, and nothing here touches a profile:
-- UIScale is account-wide and ElvUI's own import blacklist drops it
-- (Distributor.lua:274), which is why a profile export is unchanged by this page.

-- Sets the account value and shows it. Deliberately does NOT apply it: the
-- reload on the Done page (or Preview) is what puts a new scale on screen.
local function writeScale(value)
    E.global.general.UIScale = value
    if scaleSlider then scaleSlider.Cur:SetText(format("%.2f", value)) end
end

local function showScale()
    if not scaleSlider then
        local f = PluginInstallFrame
        local slider = CreateFrame("Slider", "ElvUI_TormentScaleSlider", f)
        slider:SetOrientation("HORIZONTAL")
        slider:SetWidth(400)
        slider:SetHeight(15)
        slider:SetHitRectInsets(0, 0, -10, 0)
        -- Anchored to the last description line the page uses, not to the
        -- frame: ElvUI flows Desc1/2/3 down from the top (PluginInstaller.lua:291-304,
        -- each 20px under the previous), so their height depends on the copy and
        -- on how it wraps. A fixed spot would eventually sit on a line. The 60px
        -- gap below Desc3 is the row slider.Cur needs (its bottom is 10px above
        -- the slider's top and it is a 30pt font).
        slider:SetPoint("TOP", f.Desc3, "BOTTOM", 0, -60)
        -- ElvUI's own slider treatment: the backdrop, the thumb and the end
        -- labels are what SetTemplate cannot give a slider; ElvUI's own page 5
        -- calls this straight after creating InstallSlider (Install.lua:778).
        local S = E:GetModule("Skins")
        if S and S.HandleSliderFrame then S:HandleSliderFrame(slider) end
        slider:SetMinMaxValues(0.4, 1.15)
        slider:SetValueStep(0.01)
        -- ElvUI's page 5 OnValueChanged, verbatim in effect: write the value,
        -- never rescale from here.
        slider:SetScript("OnValueChanged", function(self)
            writeScale(self:GetValue())
        end)

        slider.Min = slider:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
        slider.Min:SetPoint("RIGHT", slider, "LEFT", -3, 0)
        slider.Min:SetText("0.4")
        slider.Max = slider:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
        slider.Max:SetPoint("LEFT", slider, "RIGHT", 3, 0)
        slider.Max:SetText("1.15")
        slider.Cur = slider:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
        slider.Cur:SetPoint("BOTTOM", slider, "TOP", 0, 10)
        slider.Cur:FontTemplate(nil, 30, nil)
        scaleSlider = slider
    end

    -- ElvUI's page does SetValue here too; the value it writes back is the same
    -- one, so showing the page changes nothing.
    scaleSlider:SetValue(E.global.general.UIScale)
    scaleSlider.Cur:SetText(format("%.2f", E.global.general.UIScale))
    scaleSlider:Show()
end

local function pageScale()
    local f = PluginInstallFrame
    f.SubTitle:SetText("UI Scale")
    -- Three short lines: they are what the slider is anchored under,
    -- and Desc4 stays empty so nothing is drawn below it.
    f.Desc1:SetText("Set the UI scale for your screen, or press Auto Scale.")
    f.Desc2:SetText("It applies to every character on this account.")
    f.Desc3:SetText("Press Preview to see it. Done reloads the interface.")

    showScale()

    f.Option1:Show()
    f.Option1:SetText("Auto Scale")
    f.Option1:SetScript("OnClick", function()
        local scale = E:PixelBestSize()
        -- The slider only carries 0.01 steps; ElvUI's page moves the slider and
        -- then writes the deeper value PixelBestSize() returned, and so does
        -- this one. It still only sets it.
        scaleSlider:SetValue(scale)
        writeScale(scale)
    end)

    -- ElvUI's own Preview button (Install.lua:604-608). skip = true keeps
    -- ElvUI's reload popup away while the wizard is still open; the Done page's
    -- Reload UI settles everything.
    f.Option2:Show()
    f.Option2:SetText("Preview")
    f.Option2:SetScript("OnClick", function()
        E:PixelScaleChanged(nil, true)
    end)
end

local function pageDone()
    local f = PluginInstallFrame
    hideScale()
    f.SubTitle:SetText("Done")
    f.Desc1:SetText("A layout applied as the profile \"Torment\" takes effect after a reload.")
    f.Desc2:SetText("Press Reload UI to finish. /torment install runs this installer again.")

    f.Option1:Show()
    f.Option1:SetText("Reload UI")
    f.Option1:SetScript("OnClick", function()
        ReloadUI()
    end)
end

Installer.installTable = {
    Title = "Torment Layout Installation",
    Name = "Torment layout",
    Pages = {pageWelcome, pageApply, pageScale, pageDone},
    StepTitles = {"Welcome", "Apply the Torment layout", "UI Scale", "Done"},
}

-- Queue ---------------------------------------------------------------------

-- Queueing our table is what shows the window. PluginInstaller keeps one entry
-- per Name, so a second call while it is already queued does nothing.
function Installer:Queue()
    local PI = E:GetModule("PluginInstaller")
    if not PI then
        return false
    end

    PI:Queue(self.installTable)
    return true
end

function Installer:Command(msg)
    local command = (msg or ""):lower():match("^%s*(%S*)")
    if command == "install" then
        self:Queue()
        E:Print("Torment: opening the layout installer.")
    else
        E:Print("Torment commands: /torment install")
    end
end

-- Login ---------------------------------------------------------------------

-- Called from inside E:InitializeModules(), which ElvUI runs before the
-- `if not self.private.install_complete then self:Install() end` at the end of
-- E:Initialize() - the last moment at which the stock wizard can still be
-- skipped. The PluginInstaller module registers before this addon, so its
-- window exists by the time we queue into it.
local function onLogin()
    -- A SavedVariablesPerCharacter global is nil until this addon assigns it:
    -- on a character that has never saved there is no file, so the table has to
    -- exist before anything reads a field of it. Nothing else creates it.
    ElvUI_TormentDB = ElvUI_TormentDB or {}

    -- ElvUI's own InstallComplete() writes exactly this value. A character that
    -- already finished ElvUI's wizard has a truthy install_complete and is left
    -- alone, so nothing is lost for them.
    if not E.private.install_complete then
        E.private.install_complete = E.version
    end

    -- AceConsole's RegisterChatCommand hands a function straight to
    -- SlashCmdList, so the handler takes (input, editBox) - no self.
    E:RegisterChatCommand("torment", function(msg)
        Installer:Command(msg)
    end)

    -- Keyed on our own saved variable, once per layout version. Closing the
    -- installer without applying counts as handled, so it does not come back on
    -- every login; raising layoutVersion in profile.lua offers it again.
    local db = ElvUI_TormentDB
    if db.layoutVersion ~= module.layoutVersion then
        db.layoutVersion = module.layoutVersion
        Installer:Queue()
    end
end

E:NewModule("ElvUI_TormentInstall")
E:RegisterModule("ElvUI_TormentInstall", onLogin)
