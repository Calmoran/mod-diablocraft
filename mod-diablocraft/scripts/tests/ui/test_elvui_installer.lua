-- luacheck: globals ElvUI ElvUI_TormentDB PluginInstallFrame ReloadUI
-- luacheck: ignore 111 121 122 431 631
-- Run from repo root with `lua mod-diablocraft/scripts/tests/ui/test_elvui_installer.lua`.
--
-- Mocks the client, ElvUI and ElvUI's Distributor/PluginInstaller around the
-- production files client-patch/addons/ElvUI_Torment/{profile,install,core,options}.lua
-- and asserts the installer's rules. Mocks do NOT prove pixels: what the designer sees
-- is on his card in docs/test-diablocraft-737j.md.
--
-- The one part that is not mocked is the profile string itself: the shipped
-- bytes are decoded here with a decoder written for ElvUI 6.09's Distributor
-- format (LibBase64 + LibCompress Huffman + the "^^::" split), which was checked
-- byte-for-byte against the real LibBase64/LibCompress of tag 6.09 while it was
-- written. So "the decode round-trips" is a real check on the shipped data, and
-- a corrupted chunk in profile.lua fails this file.
--
-- Pinned rules: the shipped export is ElvUI's own export byte for byte and
-- decodes to profile::Torment; the installer is offered once per
-- layout version and not again on every login; a character that has not done
-- ElvUI's wizard never sees it; a character that has does not lose that state;
-- /torment install and the /ec button re-run it; and nothing ever writes a
-- profile other than "Torment".

unpack = unpack or table.unpack

-- ------------------------------------------------------------ picture of ElvUI

local BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

local function b64decode(text)
    local map = {}
    for i = 1, #BASE64 do map[BASE64:sub(i, i)] = i - 1 end
    local out, acc, n = {}, 0, 0
    for i = 1, #text do
        local ch = text:sub(i, i)
        if ch ~= "=" and ch ~= "\n" and ch ~= "\r" and ch ~= " " and ch ~= "\t" then
            local v = map[ch]
            assert(v, "not base64 at byte " .. i)
            -- acc is masked every step: as a double it would lose the low bits
            -- past ~9 characters and silently corrupt the tail.
            acc, n = (acc % 2 ^ n) * 64 + v, n + 6
            if n >= 8 then
                n = n - 8
                out[#out + 1] = string.char(math.floor(acc / 2 ^ n) % 256)
                acc = acc % 2 ^ n
            end
        end
    end
    return table.concat(out)
end

local function b64encode(text)
    local out = {}
    for i = 1, #text, 3 do
        local a, b, c = text:byte(i), text:byte(i + 1), text:byte(i + 2)
        local n = a * 65536 + (b or 0) * 256 + (c or 0)
        local chars = {math.floor(n / 262144) % 64, math.floor(n / 4096) % 64,
                       math.floor(n / 64) % 64, n % 64}
        local s = ""
        for j = 1, 4 do s = s .. BASE64:sub(chars[j] + 1, chars[j] + 1) end
        if not b then s = s:sub(1, 2) .. "==" elseif not c then s = s:sub(1, 3) .. "=" end
        out[#out + 1] = s
    end
    return table.concat(out)
end

-- LibCompress Huffman (method 3) and store (method 1), bits rising inside each
-- byte, exactly as LibCompress:Decompress reads them.
local function huffmanDecompress(data)
    local method = data:byte(1)
    if method == 1 then return data:sub(2) end
    assert(method == 3, "unsupported compression method " .. tostring(method))
    local numSymbols = data:byte(2) + 1
    local orig = data:byte(3) + data:byte(4) * 256 + data:byte(5) * 65536
    local bits, n = {}, 0
    for i = 6, #data do
        local b = data:byte(i)
        for j = 1, 8 do n = n + 1 bits[n] = math.floor(b / 2 ^ (j - 1)) % 2 end
    end
    local nbits = n
    local pos = 1

    local function peek(k)
        local v = 0
        for j = 1, k do v = v + (bits[pos + j - 1] or 0) * 2 ^ (j - 1) end
        return v
    end

    local map, minLen, maxLen = {}, 1e9, 0
    for _ = 1, numSymbols do
        local symbol = peek(8)
        pos = pos + 8
        local i = 0
        while not (bits[pos + i] == 1 and bits[pos + i + 1] == 1) do
            i = i + 1
            assert(i <= 64, "no code stop bits at symbol " .. numSymbols)
        end
        local code = peek(i)
        pos = pos + i + 2
        local unescaped, l, k = 0, 0, 0
        while k < i do
            if math.floor(code / 2 ^ k) % 2 == 1 then
                unescaped = unescaped + 2 ^ l
                k = k + 1
            end
            k = k + 1
            l = l + 1
        end
        map[l] = map[l] or {}
        map[l][unescaped] = string.char(symbol)
        if l < minLen then minLen = l end
        if l > maxLen then maxLen = l end
    end

    local out, count, len = {}, 0, minLen
    while count < orig do
        if pos + len - 1 > nbits then break end
        local symbol = map[len] and map[len][peek(len)]
        if symbol then
            out[#out + 1] = symbol
            count = count + 1
            pos = pos + len
            len = minLen
        else
            len = len + 1
            assert(len <= maxLen, "no code of length " .. len)
        end
    end
    return table.concat(out)
end

local function decodeDistributor(export)
    local plain = huffmanDecompress(b64decode(export))
    local split = plain:find("^^::", 1, true)
    assert(split, "the export has no profile info")
    local serialized = plain:sub(1, split - 1)
    local profileInfo = plain:sub(split + 4)
    local profileType, profileKey = profileInfo:match("^([^:]+)::(.*)$")
    if not profileKey then profileType, profileKey = profileInfo, nil end
    return profileType, profileKey, serialized, plain
end

-- ---------------------------------------------------------------- stub client

-- The one strict 3.3.5a widget mock (dc_widget_mock.lua, diablocraft-yey2):
-- it owns CreateFrame, hooksecurefunc, UIParent and the rest, and errors on a
-- method the client lacks.
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames          -- every widget made, in creation order
Mock.setScreen(1024, 768)           -- UIParent rect + GetScreenWidth/Height

-- ElvUI's FontTemplate mixin (Core/Toolkit.lua) is ElvUI's, not the 3.3.5a
-- client's, so the strict mock rightly lacks it; the addon draws the scale
-- slider's value label with it (Install.lua:786). ElvUI gives it to its font
-- strings, and the test does the same here.
Mock.methods.FontTemplate = {fn = function(self, font, size, flags)
    self.fontTemplate = {font, size, flags}
end}

local printed = {}
local realPrint = print
function print(msg) printed[#printed + 1] = msg end

-- ElvUI's plugin install window, modelled on 6.09's Core/PluginInstaller.lua -
-- including the part that broke on live: SetPage, NextPage and PreviousPage are
-- PLAIN local functions there (`local function SetPage(PageNum, PrevPage)` at
-- line 100, NextPage 139, PreviousPage 148), stored as `f.SetPage = SetPage`
-- (202) and handed to the buttons as they are (217, 225). A colon call passes
-- the frame in as the page number, and SetPage feeds that to the status bar's
-- animation, where LibAnim does arithmetic on it - exactly the live error. The
-- mock keeps that failure mode: SetPage's first act is the animation.
local PluginInstaller = {Installs = {}, queueCalls = 0}

-- A text widget ElvUI's window made: it carries a font before anything writes it. The
-- mock's rule 5 refuses SetText on a FontString with no font, as the client does.
local function windowText(parent)
    local text = Mock.widget("FontString", nil, parent)
    text:SetFont("Fonts\\FRIZQT__.TTF", 12)
    return text
end

local frame = Mock.widget("Button", nil)
PluginInstallFrame = frame
frame.Title = windowText(frame)
for _, field in ipairs({"SubTitle", "Desc1", "Desc2", "Desc3", "Desc4"}) do
    frame[field] = windowText(frame)
end
for i = 1, 4 do
    frame["Option" .. i] = Mock.widget("Button", nil, frame)
end
frame.Next = Mock.widget("Button", nil, frame)
frame.Prev = Mock.widget("Button", nil, frame)
frame.side = {Lines = {}}
for i = 1, 4 do frame.side.Lines[i] = windowText(frame) end
frame.Status = Mock.widget("StatusBar", nil, frame)
frame.Status.text = windowText(frame.Status)
frame.Status.anim = {progress = {}}
function frame.Status.anim.progress:SetChange(value) self.EndValue = value end
function frame.Status.anim.progress:Play() return self.EndValue + 0 end -- LibAnim's arithmetic

local function ResetAll()
    frame.Next:Disable()
    frame.Prev:Disable()
    for i = 1, 4 do
        frame["Option" .. i]:Hide()
        frame["Option" .. i]:SetScript("OnClick", nil)
        frame["Option" .. i]:SetText("")
    end
    for _, field in ipairs({"SubTitle", "Desc1", "Desc2", "Desc3", "Desc4"}) do
        frame[field]:SetText("")
    end
    frame:SetSize(550, 400)
end

local function SetPage(page, prev)
    frame.CurrentPage, frame.PrevPage = page, prev
    ResetAll()
    frame.Status.anim.progress:SetChange(page)
    frame.Status.anim.progress:Play()

    if page == frame.MaxPage then frame.Next:Disable() else frame.Next:Enable() end
    if page == 1 then frame.Prev:Disable() else frame.Prev:Enable() end

    frame.Pages[frame.CurrentPage]()
    frame.Status.text:SetFormattedText("%d / %d", frame.CurrentPage, frame.MaxPage)
    if frame.StepTitles then
        for i = 1, #frame.side.Lines do
            frame.side.Lines[i]:SetText(frame.StepTitles[i] or "")
        end
    end
end

local function NextPage()
    if frame.CurrentPage ~= frame.MaxPage then
        frame.CurrentPage = frame.CurrentPage + 1
        SetPage(frame.CurrentPage, frame.CurrentPage - 1)
    end
end

local function PreviousPage()
    if frame.CurrentPage ~= 1 then
        frame.CurrentPage = frame.CurrentPage - 1
        SetPage(frame.CurrentPage, frame.CurrentPage + 1)
    end
end

frame.SetPage = SetPage
frame.Next:SetScript("OnClick", NextPage)
frame.Prev:SetScript("OnClick", PreviousPage)
frame:SetScript("OnHide", function() PluginInstaller:CloseInstall() end)

local reloads = 0
function ReloadUI() reloads = reloads + 1 end

-- ------------------------------------------------------------------ stub ElvUI

local function deepcopy(t)
    if type(t) ~= "table" then return t end
    local copy = {}
    for k, v in pairs(t) do copy[k] = deepcopy(v) end
    return copy
end

local function removeEmptySubTables(t)
    for k, v in pairs(t) do
        if type(v) == "table" then
            removeEmptySubTables(v)
            if next(v) == nil then t[k] = nil end
        end
    end
end

local E = {
    version = "6.09",
    private = {},
    global = {general = {UIScale = 1}},
    db = {},
    Media = {Textures = {Logo = "Interface\\AddOns\\ElvUI\\media\\logo"}},
    Options = {args = {}},
    Modules = {},
    -- Stock ElvUI 6.09 has it (Core/Math.lua), and core.lua hooks it: the mock refuses
    -- to hook a name that is not a function, as the client does.
    BuildPrefixValues = function() end,
}

function E:NewModule(name)
    local module = {name = name}
    self.Modules[name] = module
    return module
end
function E:GetModule(name) return self.Modules[name] end

local registered, wizardShown, moduleErrors = {}, 0, {}
function E:RegisterModule(name, func)
    registered[#registered + 1] = {name, func}
end

-- E:Initialize(): initialize every module in registration order, then the stock
-- install check (Core.lua: `if not self.private.install_complete then self:Install()`).
-- Each module callback runs under xpcall, exactly as CallbackHandler-1.0 does it
-- in 6.09 (ElvUI/Init.lua:34, CallbackHandler's Dispatcher: xpcall(call, eh)):
-- an error in a module is printed and ElvUI carries on, so the test can see both
-- halves of a broken first login - the error, and the stock wizard it lets past.
function E:Initialize()
    for _, entry in ipairs(registered) do
        local func = entry[2]
        if func then
            local ok, err = xpcall(func, function(e) return e end)
            if not ok then moduleErrors[#moduleErrors + 1] = entry[1] .. ": " .. tostring(err) end
        end
    end
    if not self.private.install_complete then wizardShown = wizardShown + 1 end
end

function E:UpdateAll(ignoreInstall)
    E.db = E.data.profiles[E.data.keys.profile]
    E.global = E.data.global
    -- Core.lua:874, Layout:BottomPanelVisibility(): indexes the panel Layout's
    -- Initialize makes, so a Layout that never finished it breaks UpdateAll the
    -- way the designer saw on Nightly 94 (diablocraft-i6jgl).
    local _ = E.Modules["Layout"].BottomPanel.Hide
    if not ignoreInstall and not E.private.install_complete then wizardShown = wizardShown + 1 end
end

function E:Print(msg) printed[#printed + 1] = msg end

-- ElvUI's UI scale API: PixelBestSize is Core/PixelPerfect.lua:67 verbatim, and
-- PixelScaleChanged is the call ElvUI's own UI Scale page makes for Preview
-- (Core/PixelPerfect.lua:71). scaleApplied records what it was handed.
E.screenheight = 1080
function E:PixelBestSize() return math.max(0.4, math.min(1.15, 768 / self.screenheight)) end
E.scaleApplied = 0
function E:PixelScaleChanged(event, skip)
    self.lastScaleChange = {event = event, skip = skip}
    self.scaleApplied = self.scaleApplied + 1
end

-- E:FilterTableFromBlacklist is ElvUI's (Core.lua): a copy with blacklisted
-- keys dropped and empty sub-tables cleaned out.
function E:FilterTableFromBlacklist(cleanTable, blacklistTable)
    assert(type(cleanTable) == "table", "cleanTable must be a table")
    assert(type(blacklistTable) == "table", "blacklistTable must be a table")
    local cleaned = {}
    for option, value in pairs(cleanTable) do
        if type(value) == "table" and type(blacklistTable[option]) == "table" then
            cleaned[option] = self:FilterTableFromBlacklist(value, blacklistTable[option])
        elseif blacklistTable[option] ~= true then
            cleaned[option] = value
        end
    end
    removeEmptySubTables(cleaned)
    return cleaned
end

local chatCommands = {}
function E:RegisterChatCommand(name, func) chatCommands[name] = func end

-- LibElvUIPlugin-1.0: RegisterPlugin(name, callfunc) builds the options group
-- when ElvUI's options are opened.
E.Libs = {EP = {RegisterPlugin = function(_, _, builder) E.pluginBuilder = builder end}}

-- AceDB "ElvDB": profiles keyed by name, one active key per character.
local seedProfiles = {
    ["Default"] = {general = {minimap = {size = 150}}, unitframe = {units = {player = {enable = true}}}},
    ["OldLayout"] = {general = {minimap = {size = 180}}, movers = {ElvUF_PlayerMover = "BOTTOMLEFT,ElvUIParent,BOTTOMLEFT,400,300"}},
    ["Notmine"] = {general = {minimap = {size = 1}}},
}
E.data = {
    keys = {profile = "Default"},
    profiles = seedProfiles,
    global = {general = {UIScale = 1}},
}
function E.data:SetProfile(name)
    if name == self.keys.profile then return end
    self.keys.profile = name
    E:UpdateAll(nil) -- ElvUI registers OnProfileChanged -> UpdateAll
end

-- ElvUI[1] is the engine, ElvUI[4] the ProfileDB defaults options.lua seeds.
-- ElvUI_TormentDB is deliberately NOT created here: on a character that has
-- never saved, a SavedVariablesPerCharacter global is nil, and the addon must
-- be the thing that creates it (asserted in section 2).
ElvUI = {E, {}, {}, {}}

-- 6.09's PluginInstaller: Queue dedupes by Name and runs, and RunInstall
-- (PluginInstaller.lua:401) refuses to show anything until ElvUI's own install
-- is complete - which is why the installer only appears because our login
-- marked install_complete first.
function PluginInstaller:Queue(addon)
    for _, queued in ipairs(self.Installs) do
        if queued.Name == addon.Name then return end
    end
    self.Installs[#self.Installs + 1] = addon
    self.queueCalls = self.queueCalls + 1
    self:RunInstall()
end

function PluginInstaller:RunInstall()
    if not E.private.install_complete then return end
    if not self.Installs[1] then return end
    self.showing = self.Installs[1]
    frame.StepTitles = nil
    frame.Pages = self.showing.Pages
    frame.MaxPage = #self.showing.Pages
    frame.CurrentPage = 0
    frame:Show()
    if self.showing.StepTitles and #self.showing.StepTitles == frame.MaxPage then
        frame.StepTitles = self.showing.StepTitles
    end
    NextPage()
end

function PluginInstaller:CloseInstall()
    table.remove(self.Installs, 1)
    self.showing = nil
end

-- The decoded payload the Distributor hands back: a couple of the real values
-- from the designer's export (verified in the decode report), plus the one key ElvUI's
-- import blacklist drops, so the filter is exercised.
local payload = {
    general = {minimap = {size = 220}, numberPrefixStyle = "brackets"},
    movers = {ElvUF_PlayerMover = "BOTTOMLEFT,ElvUIParent,BOTTOMLEFT,524,395"},
    torment = {bar1Scale = 0.98},
}
local Distributor = {decodeCalls = 0, lastText = nil, typeOverride = nil, keyOverride = nil}
function Distributor:Decode(text)
    self.decodeCalls = self.decodeCalls + 1
    self.lastText = text
    local profileType, profileKey = decodeDistributor(text)
    if self.typeOverride then profileType = self.typeOverride end
    if self.keyOverride then profileKey = self.keyOverride end
    if profileType ~= "profile" then return profileType, profileKey end
    return profileType, profileKey, deepcopy(payload)
end

E.Modules["Distributor"] = Distributor
-- ElvUI's Layout module once its Initialize has run (Layout/Layout.lua:24).
E.Modules["Layout"] = {BottomPanel = {}}
E.Modules["PluginInstaller"] = PluginInstaller

-- ElvUI's Skins module, which is what gives a raw slider its backdrop and thumb
-- (ElvUI/Core/Install.lua:778 calls it for its own slider).
local Skins = {sliderCalls = 0, lastSlider = nil}
function Skins:HandleSliderFrame(slider)
    self.sliderCalls = self.sliderCalls + 1
    self.lastSlider = slider
    slider.skinned = true
end
E.Modules["Skins"] = Skins

-- ------------------------------------------------------- load the real addon

-- Globals the 3.3.5 client has that are legitimately nil or written by the
-- addon. ElvUI_TormentDB is a declared saved variable and is nil on a character
-- that has never saved; `module` is the global barart.lua assigns. Everything
-- else stays unknown and the guard below rejects both reads and writes of it.
-- TormentDamageTextRead and TormentWorldToScreen are the client module's globals
-- (docs/contracts/damage-text.md), absent on a client without it, as here.
local declared = {ElvUI_TormentDB = true, module = true, TormentDamageTextRead = true, TormentWorldToScreen = true}

local clientGlobals = {
    _G = _G, assert = assert, error = error, ipairs = ipairs, pairs = pairs,
    next = next, select = select, tostring = tostring, tonumber = tonumber,
    type = type, unpack = unpack, print = print, math = math, string = string,
    table = table, setmetatable = setmetatable, pcall = pcall, rawget = rawget,
    rawset = rawset, os = os, io = io,
    ElvUI = ElvUI,
    PluginInstallFrame = PluginInstallFrame, ReloadUI = ReloadUI,
    -- ElvUI_OptionsUI's shared-media lists, there whenever the options page is built.
    AceGUIWidgetLSMlists = {font = {}},
}

-- CreateFrame and hooksecurefunc come from the shared mock (Mock.install above).
-- They are read by name so the mock's own rules test does not read this table as
-- a test still carrying its own CreateFrame stub.
for _, name in ipairs({"CreateFrame", "hooksecurefunc"}) do
    clientGlobals[name] = _G[name]
end

local function guardEnv(path)
    return setmetatable({}, {
        __index = function(_, key)
            if declared[key] then return clientGlobals[key] end
            local value = clientGlobals[key]
            if value == nil then
                error(("%s referenced a global unavailable in 3.3.5: %s"):format(path, tostring(key)), 2)
            end
            return value
        end,
        -- The client has one global table, so a write goes somewhere every file
        -- and the test can see it. Writing anything undeclared is the other half
        -- of the guard, and it is what would catch the addon inventing a global.
        __newindex = function(_, key, value)
            if not declared[key] then
                error(("%s wrote an undeclared global in 3.3.5: %s"):format(path, tostring(key)), 2)
            end
            clientGlobals[key] = value
            rawset(_G, key, value)
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

-- The guard itself: a chunk using an unavailable global must fail, proving the
-- mock catches a regression instead of defining it.
local probe
if setfenv then
    probe = assert(loadstring("return getn"))
    setfenv(probe, guardEnv("guard probe"))
else
    probe = assert(load("return getn", "guard probe", "t", guardEnv("guard probe")))
end
assert(not pcall(probe), "guard must reject the unavailable global getn")

local function resetSavedVars()
    local db = ElvUI_TormentDB
    if type(db) == "table" then
        for key in pairs(db) do db[key] = nil end
    end
end

local ADDON = "client-patch/addons/ElvUI_Torment/"
-- Loaded the way the client loads them for a character that has never saved:
-- ElvUI_TormentDB is nil. None of these files may touch the saved variables.
assert(ElvUI_TormentDB == nil, "the addon files must be loaded with no saved variables, as on a first login")
loadGuarded(ADDON .. "barart.lua") -- creates the module table profile/install extend
loadGuarded(ADDON .. "profile.lua")
loadGuarded(ADDON .. "install.lua")
loadGuarded(ADDON .. "core.lua")
loadGuarded(ADDON .. "damagetext.lua")
loadGuarded(ADDON .. "options.lua")
assert(ElvUI_TormentDB == nil, "loading must not create the saved variables")

local module = E.Modules["ElvUI_Torment"]
local Installer = module.installer
assert(type(Installer) == "table", "install.lua did not publish the installer")
assert(type(module.layoutExport) == "string", "profile.lua did not ship the layout")
assert(module.layoutVersion == 5, "layoutVersion must be 5 (the diablocraft-66neu buff fix)")

-- --------------------------------------------- 1. the shipped export decodes

-- The string in the addon and the string the designer exported must be the same bytes.
do
    local file = assert(io.open("docs/briefs/elvui-torment-installer-profile-export.txt", "rb"))
    local exported = file:read("*a")
    file:close()
    exported = exported:gsub("[\r\n]+$", "")
    assert(module.layoutExport == exported, "the shipped layout is not the designer's export, byte for byte")
    assert(#module.layoutExport == 5680, "the shipped layout is not the length the designer exported")
end

local profileType, profileKey, serialized, plain = decodeDistributor(module.layoutExport)
assert(profileType == "profile", "the export holds a " .. tostring(profileType) .. ", not a profile")
assert(profileKey == "Torment", "the export's own key is the profile the designer exported")
assert(not module.layoutExport:find("%s"), "base64 must be one uninterrupted string")
assert(b64encode(b64decode(module.layoutExport)) == module.layoutExport,
    "the export must survive a decode/encode round trip")
-- The method byte and the declared length are LibCompress's own header.
assert(b64decode(module.layoutExport):byte(1) == 3, "the export must be Huffman compressed")
assert(b64decode(module.layoutExport):byte(3) + b64decode(module.layoutExport):byte(4) * 256
    + b64decode(module.layoutExport):byte(5) * 65536 == #plain, "header length must match the payload")
-- Section markers: this is the designer's layout, not any other export.
for _, marker in ipairs({"^1^T", "^Sactionbar^T", "^Sunitframe^T", "^Smovers^T",
                         "^Storment^T", "^Sbar1Scale", "ElvUIParent", "BOTTOMLEFT",
                         "^Snameplates^T", "^Sfont^SContinuum~`Medium"}) do
    assert(serialized:find(marker, 1, true), "the payload must hold " .. marker)
end
-- The split is at the payload's own AceSerializer terminator: "^" + "^::".
local splitAt = plain:find("^^::", 1, true)
assert(plain:sub(splitAt, splitAt + 1) == "^^" and plain:sub(splitAt + 2, splitAt + 3) == "::",
    "the payload must end with the AceSerializer terminator")

-- --------------------------- 2. the first login, with no saved file yet

-- Nothing has created ElvUI_TormentDB yet: this is the character's first login
-- with the addon, so the client has no file to load and the global is nil. The
-- module callback must create it rather than index it, or the installer never
-- queues and the player gets a Lua error - and, because a module error does not
-- stop E:Initialize(), ElvUI's own wizard as well.
assert(ElvUI_TormentDB == nil, "the first login must start with no saved variables")
moduleErrors = {}
E.private = {}
E:Initialize()
assert(#moduleErrors == 0, "the first login must not raise: " .. tostring(moduleErrors[1]))
assert(type(ElvUI_TormentDB) == "table", "the first login must create the saved variables")
assert(PluginInstaller.queueCalls == 1, "first login must offer the installer")
assert(PluginInstaller.Installs[1] == Installer.installTable, "the queued table must be ours")
-- RunInstall gated on install_complete and started on page 1, as 6.09 does.
assert(PluginInstaller.showing == Installer.installTable, "the installer must actually come up")
assert(PluginInstallFrame.CurrentPage == 1 and PluginInstallFrame:IsShown(),
    "a first login must land on the Welcome page")
assert(PluginInstallFrame.SubTitle.text == "Torment layout", "page 1 is the welcome page")
assert(ElvUI_TormentDB.layoutVersion == module.layoutVersion, "the offer must be recorded")
assert(chatCommands.torment, "the /torment command must be registered")

-- While it is open, another login does not stack a second copy of it.
E:Initialize()
assert(#PluginInstaller.Installs == 1, "a second offer must not stack")
assert(#moduleErrors == 0, "a later login must not raise either")

-- The player closes it without applying and logs in again: not nagged.
-- PluginInstaller:Queue keeps one entry per Name, so closing it is what makes a
-- nag visible at all - this is the assertion that catches a gate that queues on
-- every login.
PluginInstaller:CloseInstall()
assert(#PluginInstaller.Installs == 0, "a closed installer is not queued")
E:Initialize()
assert(#PluginInstaller.Installs == 0, "closing it must not bring it back on the next login")
assert(ElvUI_TormentDB.layoutVersion == module.layoutVersion, "the offer stays recorded")

-- A character recorded on layout 1 (the designer's previous export) is offered the
-- installer again by the raised layoutVersion, and recorded on the new one.
ElvUI_TormentDB.layoutVersion = 1
E:Initialize()
assert(#PluginInstaller.Installs == 1, "a character on layout 1 must be offered the new layout")
assert(ElvUI_TormentDB.layoutVersion == module.layoutVersion, "and be recorded as offered")

-- ------------------------------------------- 3. ElvUI's stock wizard is skipped

-- The mock E:Initialize() ends with ElvUI's own install check, so this is the
-- real ordering: a fresh character never sees the stock wizard.
assert(wizardShown == 0, "a fresh character must never reach ElvUI's stock wizard")
assert(E.private.install_complete == E.version, "install_complete must hold ElvUI's version")
-- The PluginInstaller only runs plugins once install_complete is set (6.09
-- PluginInstaller.lua:402), so this is also what lets our install show at all.
assert(E.private.install_complete, "PluginInstaller:RunInstall must be allowed to run")

-- Without the flag the stock wizard does show: the mock is not silently passing.
local saved = E.private.install_complete
E.private.install_complete = nil
E:UpdateAll()
assert(wizardShown == 1, "the stock wizard check must be real")
E.private.install_complete = saved

-- A character that already finished ElvUI's wizard keeps its own value.
resetSavedVars()
PluginInstaller.Installs = {}
E.private = {install_complete = "6.08"}
E:Initialize()
assert(E.private.install_complete == "6.08", "an existing install_complete must not be rewritten")
assert(wizardShown == 1, "and its wizard state must not bring the wizard up")
assert(PluginInstaller.queueCalls == 3, "a new character must be offered the installer")

-- ------------------------------------------------------- 4. running it again

-- Closing it is the window's own OnHide (6.09: `f:SetScript("OnHide", function()
-- PI:CloseInstall() end)`), which is how a player who presses X dismisses it.
PluginInstallFrame:Hide()
assert(#PluginInstaller.Installs == 0, "a closed installer is not queued")
assert(PluginInstaller.showing == nil, "and is no longer the one being shown")
-- AceConsole hands a function handler to SlashCmdList, which calls it with the
-- typed arguments only - that is why /torment is driven through the registered
-- handler here and not through Installer:Command.
chatCommands.torment("install")
assert(#PluginInstaller.Installs == 1, "/torment install must re-open it")
assert(PluginInstaller.showing == Installer.installTable, "and must bring the window back up")
assert(PluginInstallFrame.CurrentPage == 1, "re-opening starts at the first page")
assert(ElvUI_TormentDB.layoutVersion == module.layoutVersion, "a re-run must not change the flag")

-- The /ec button in the Torment section runs the same installer.
E.pluginBuilder("ElvUI_Torment")
local group = E.Options.args.torment
assert(group and group.name == "Torment", "the Torment options section must exist")
assert(group.args.applyLayout and group.args.applyLayout.type == "execute",
    "the Torment section must offer the installer")
PluginInstallFrame:Hide()
group.args.applyLayout.func()
assert(#PluginInstaller.Installs == 1, "the /ec button must open the installer")
PluginInstallFrame:Hide()

-- The Objective Frame scale (diablocraft-rift-tracker-exocet-slider): a slider in this
-- section, 1.25 by default (q-1003-44). Its setter writes E.db.torment through the shared
-- changed() path and the apply pass hands the factor to the rift tracker's AIO client half
-- (dc_riftbar.lua); the apply half is exercised in test_orbs_client.lua, which loads the
-- bar geometry this file's guarded environment leaves out.
local scaleOption = group.args.objectiveScale
assert(scaleOption and scaleOption.type == "range" and scaleOption.name == "Objective Frame scale",
    "the Torment section must offer the Objective Frame scale")
assert(scaleOption.min == 0.5 and scaleOption.max == 1.5 and scaleOption.step == 0.01,
    "the slider must keep a sane range")
assert(ElvUI[4].torment.objectiveScale == 1.25,
    "the profile default must be the tracker's own 1.25, got " .. tostring(ElvUI[4].torment.objectiveScale))
-- A profile exported before the setting existed has a torment table without the key: the
-- slider must show the default rather than nothing.
local profileTorment = E.db.torment
E.db.torment = {bar1Scale = 1}
assert(scaleOption.get() == 1.25, "an older profile shows the default, got " .. tostring(scaleOption.get()))
E.db.torment.objectiveScale = 0.9
assert(scaleOption.get() == 0.9, "the slider must read the profile value back")
E.db.torment = profileTorment

-- Unknown /torment arguments say what the command is.
chatCommands.torment("")
assert(printed[#printed]:find("torment install"), "/torment must name its argument")
assert(#PluginInstaller.Installs == 0, "an unknown argument must not open anything")

-- -------------------------------------- 5. the pages apply the layout, then reload
--
-- Driven the way a player does it: Next moves the page, then the page's own
-- button. This is the path that broke on live - page 2's Apply button calls
-- PluginInstallFrame.SetPage, a plain function in 6.09, to reach page 3.

local function pressNext()
    local button = PluginInstallFrame.Next
    assert(button.scripts.OnClick, "the window must have a Next button")
    button.scripts.OnClick()
end

local function optionText()
    return PluginInstallFrame.Option1.text
end

local function pressOption()
    local option = PluginInstallFrame.Option1
    assert(option.text and option.scripts.OnClick, "the page must offer its button")
    local text = option.text -- the label the player pressed
    option.scripts.OnClick()
    return text
end

E.data = {keys = {profile = "Default"}, profiles = seedProfiles, global = {general = {UIScale = 1}}}
E.data.SetProfile = function(self, name)
    if name == self.keys.profile then return end
    self.keys.profile = name
    E:UpdateAll(nil)
end
E.db = E.data.profiles["Default"]

-- Page 1 (Welcome) has no button of its own; Next takes us to the apply page.
assert(not PluginInstallFrame.Option1:IsShown(), "the welcome page must not offer a button")
pressNext()
assert(PluginInstallFrame.CurrentPage == 2, "Next must move to the apply page")

assert(pressOption() == "Apply the Torment layout", "page 2 is the apply page")
assert(PluginInstallFrame.CurrentPage == 3, "applying must move on to the UI Scale page")
assert(E.data.keys.profile == "Torment", "applying must make Torment the active profile")
assert(E.db == E.data.profiles["Torment"], "E.db must point at the new profile")
assert(not PluginInstallFrame.Next.disabled, "the UI Scale page is not the last one")

-- Page 4 is Done, and only there does the wizard finish.
pressNext()
assert(PluginInstallFrame.CurrentPage == 4, "Next must move from the scale page to Done")
assert(PluginInstallFrame.Next.disabled, "the done page is the last one")

assert(pressOption() == "Reload UI", "page 4 is the done page")
assert(reloads == 1, "the done page must reload the UI")
assert(PluginInstallFrame.StepTitles == Installer.installTable.StepTitles,
    "the step list must be our four titles")

-- ------------------------------- 6. no other profile is ever written or touched

assert(Distributor.lastText == module.layoutExport, "the decode must take the shipped string")
assert(Distributor.decodeCalls > 0, "the apply path must decode, not trust a fixture")

local tormentProfile = E.data.profiles["Torment"]
assert(tormentProfile, "the Torment profile must exist")
assert(tormentProfile.torment.bar1Scale == 0.98, "the Torment profile must hold the decoded layout")
assert(tormentProfile.movers.ElvUF_PlayerMover == "BOTTOMLEFT,ElvUIParent,BOTTOMLEFT,524,395",
    "the Torment profile must hold the decoded movers")
-- ElvUI's own import filter runs: general.numberPrefixStyle is blacklisted.
assert(tormentProfile.general.numberPrefixStyle == nil, "the import blacklist must be applied")
assert(tormentProfile.general.minimap.size == 220, "and must not drop anything else")
-- ElvUI adds no ID line and no Count line to a tooltip (ruling 2026-10-04 (1); diablocraft-sor6).
assert(tormentProfile.tooltip and tormentProfile.tooltip.spellID == false,
    "the Torment profile turns ElvUI's Spell/Item ID line off")
assert(tormentProfile.tooltip.itemCount == "NONE", "and its Item Count line")
-- The buff bar's icons anchor at the container's bottom-left along its bottom
-- edge (ruling 2026-10-11, ui feedback e08mjkm8; diablocraft-66neu). RIGHT_UP is
-- ElvUI's horizontal growth whose point is BOTTOMLEFT (Modules/Auras.lua
-- DIRECTION_TO_POINT / IS_HORIZONTAL_GROWTH): a wide container with the icons
-- filling rightward from the bottom-left. UP_RIGHT is vertical growth and made
-- the one-icon-wide column the designer reported.
assert(tormentProfile.auras and tormentProfile.auras.buffs
    and tormentProfile.auras.buffs.growthDirection == "RIGHT_UP",
    "the Torment profile anchors buff icons bottom-left in one wide row")

-- The designer's private settings ride the apply (private-export.txt, 2026-10-11): his
-- name font, the global bar texture and the auras skin switch, written key by
-- key onto the character's own private table so a player's other private
-- settings survive (ElvUI's own private import would replace them; the install
-- path deliberately does not use it, decisions 2026-10-01).
assert(E.private.general and E.private.general.namefont == "Continuum Medium",
    "the apply must set the private name font")
assert(E.private.general.normTex == "Minimalist", "the apply must set the private bar texture")
assert(E.private.auras and E.private.auras.lbf and E.private.auras.lbf.enable == true,
    "the apply must switch the private auras skin on")

-- Another profile is the same table it was.
assert(E.data.profiles["OldLayout"] == seedProfiles["OldLayout"],
    "another profile must not be replaced")
assert(seedProfiles["OldLayout"].movers.ElvUF_PlayerMover
    == "BOTTOMLEFT,ElvUIParent,BOTTOMLEFT,400,300", "and must not be modified")
assert(seedProfiles["Default"] == E.data.profiles["Default"], "other profiles must be untouched")
assert(seedProfiles["Notmine"] == E.data.profiles["Notmine"], "other profiles must be untouched")
for key in pairs(E.data.profiles) do
    assert(key ~= "Torment_Temp", "no _Temp profile may be left behind")
end

-- Re-running while Torment is already active replaces its contents in place.
payload.torment.bar1Scale = 0.5
local before = E.data.profiles["Torment"]
local ok = Installer:ApplyProfile()
assert(ok, "a second apply must succeed")
assert(E.data.keys.profile == "Torment", "a second apply must keep Torment active")
assert(E.data.profiles["Torment"] == E.db, "E.db must be repointed at the replaced table")
assert(E.db.torment.bar1Scale == 0.5, "a second apply must replace the layout, not the old table")
assert(E.data.profiles["OldLayout"] == seedProfiles["OldLayout"],
    "a second apply must still not touch another profile")
for key in pairs(E.data.profiles) do
    assert(key ~= "Torment_Temp", "a second apply must leave no _Temp profile")
end
assert(before ~= E.db, "the replaced table must be a new one")

-- A string that is not a profile export writes nothing at all, and the player
-- is left on the apply page with the reason and a retry instead of being moved
-- on to Done.
Distributor.typeOverride = "private"
local snapshot = {keys = E.data.keys.profile, profile = E.data.profiles["Torment"], db = E.db}
-- Poison the private settings: a refused apply must leave every one of them as
-- it found it, proving they ride a real apply and not the decode alone.
E.private.general.namefont, E.private.general.normTex, E.private.auras.lbf.enable =
    "Untouched", "Untouched", false
PluginInstallFrame.SetPage(2, 1)
assert(pressOption() == "Apply the Torment layout", "the retry starts from the apply button")
assert(optionText() == "Retry", "a refused apply must offer a retry")
assert(PluginInstallFrame.CurrentPage == 2, "and must stay on the apply page")
assert(PluginInstallFrame.Desc3.text:find("private"), "and must say what was wrong")
assert(E.data.keys.profile == snapshot.keys, "a refused apply must not switch profiles")
assert(E.data.profiles["Torment"] == snapshot.profile, "a refused apply must not write the profile")
assert(E.db == snapshot.db, "a refused apply must not change E.db")
assert(E.private.general.namefont == "Untouched" and E.private.general.normTex == "Untouched"
    and E.private.auras.lbf.enable == false, "a refused apply must not write the private settings")
Distributor.typeOverride = nil

-- The string's own key never picks the profile. ElvUI's Distributor hands back
-- the key inside the export; the addon owns "Torment" and must ignore it. A
-- regression that wrote profiles[<decoded key>] (or made that name active) must
-- fail here.
Distributor.keyOverride = "Evil"
payload.torment.bar1Scale = 0.42
assert(E.data.profiles["Evil"] == nil, "the foreign key must not name an existing profile")
local okKey = Installer:ApplyProfile()
assert(okKey, "an apply whose export carries a foreign key still succeeds")
assert(E.data.profiles["Evil"] == nil, "the string's own key must never name a profile")
assert(E.data.profiles["Torment"].torment.bar1Scale == 0.42,
    "the apply must still write the Torment profile")
assert(E.data.keys.profile == "Torment", "and must still make Torment the active profile")
Distributor.keyOverride = nil
payload.torment.bar1Scale = 0.5

-- ------------------------------------------- 7. the UI Scale page

-- One account-wide value (E.global.general.UIScale), set the way ElvUI sets it
-- and applied only through Preview, with no profile touched and no resolution
-- presets: ElvUI's own UI Scale page (Install.lua:577-612) is the model minus
-- the presets the designer dropped. The scale itself is PixelPerfect.lua:67/71.

assert(#Installer.installTable.Pages == 4, "the installer must have four pages")
assert(Installer.installTable.StepTitles[3] == "UI Scale", "step 3 is UI Scale")
assert(Installer.installTable.StepTitles[4] == "Done", "step 4 is Done")

-- Reach the scale page the way a player does: apply, which moves to it.
assert(E.scaleApplied == 0, "nothing has applied a scale yet")
PluginInstallFrame.SetPage(2, 1)
assert(pressOption() == "Apply the Torment layout", "the apply button reaches the scale page")
assert(PluginInstallFrame.CurrentPage == 3, "applying must land on the UI Scale page")
assert(E.scaleApplied == 0, "showing the scale page must not apply a scale")
assert(E.lastScaleChange == nil, "and must not call ElvUI's scale change at all")

-- Snapshotted after the apply: the scale page itself must change none of it.
local profileBefore = E.data.profiles["Torment"]
local profileKeys = {}
for key in pairs(profileBefore) do profileKeys[#profileKeys + 1] = key end
local tormentKeys = {}
for key in pairs(profileBefore.torment) do tormentKeys[#tormentKeys + 1] = key end

local slider
for _, candidate in ipairs(frames) do
    if candidate.kind == "Slider" then slider = candidate end
end
assert(slider, "the UI Scale page must build a slider")
assert(slider.minValue == 0.4 and slider.maxValue == 1.15, "the slider must span 0.4 to 1.15")
assert(slider.valueStep == 0.01, "the slider must step by 0.01")
assert(slider.Min.text == "0.4" and slider.Max.text == "1.15", "the slider must show its ends")
assert(slider:IsShown(), "the scale page shows the slider")
assert(slider.value == E.global.general.UIScale, "the slider must show the account value")

-- The layout, which the designer's in-game check caught: ElvUI flows Desc1/2/3 down and
-- their height depends on the copy, so the slider hangs off the LAST line the
-- page uses (PluginInstaller.lua:291-304) instead of a fixed spot, and the 30pt
-- value label keeps its own row between them.
assert(slider.points[1] and slider.points[1][1] == "TOP" and slider.points[1][2] == PluginInstallFrame.Desc3
    and slider.points[1][3] == "BOTTOM",
    "the slider must hang off the last description line, not the frame")
assert(slider.points[1][5] <= -50,
    "the gap under the last line must fit the 30pt value label in its own row")
assert(slider.Cur.points[1] and slider.Cur.points[1][2] == slider,
    "the value label must anchor to the slider and to no description line")
assert(PluginInstallFrame.Desc4.text == "",
    "no description line below the slider's anchor may carry text")
assert(PluginInstallFrame.Desc1.text == "Set the UI scale for your screen, or press Auto Scale."
    and PluginInstallFrame.Desc2.text == "It applies to every character on this account."
    and PluginInstallFrame.Desc3.text == "Press Preview to see it. Done reloads the interface.",
    "the page must carry the designer's three short lines")
assert(slider.skinned and Skins.sliderCalls == 1 and Skins.lastSlider == slider,
    "the slider must be skinned by ElvUI's own Skins module (Install.lua:778)")
assert(slider.Cur.fontTemplate and slider.Cur.fontTemplate[2] == 30,
    "the value label must use ElvUI's own size (Install.lua:786)")
assert(PluginInstallFrame.Desc1.text:find("Auto Scale"), "the page must explain Auto Scale")
assert(PluginInstallFrame.Desc3.text:find("Preview"), "the page must explain the Preview button")
assert(PluginInstallFrame.Desc2.text:find("every character"),
    "the page must say the value applies to every character")

-- Auto Scale and Preview, and no resolution preset buttons on this page.
assert(PluginInstallFrame.Option1:IsShown() and PluginInstallFrame.Option1.text == "Auto Scale",
    "the scale page offers Auto Scale")
assert(PluginInstallFrame.Option2:IsShown() and PluginInstallFrame.Option2.text == "Preview",
    "the scale page offers Preview")
for i = 3, 4 do
    assert(not PluginInstallFrame["Option" .. i]:IsShown(),
        "the scale page must offer no other button (no resolution presets)")
end
for i = 1, 4 do
    local label = PluginInstallFrame["Option" .. i].text or ""
    assert(not label:find("%d+x%d+") and not label:find("1080") and not label:find("1440"),
        "no resolution preset may appear on the scale page")
end

-- The slider only SETS the value: ElvUI's way, no rescale per tick.
local appliedBefore = E.scaleApplied
for _, value in ipairs({0.85, 0.9, 0.95}) do
    slider:SetValue(value)
    -- The client fires OnValueChanged from SetValue; the widget mock stores
    -- scripts without dispatching them (as it does for OnHide/OnClick), so the
    -- test fires it the way the client would.
    slider.scripts.OnValueChanged(slider)
    assert(math.abs(E.global.general.UIScale - slider:GetValue()) < 1e-9,
        "the slider must write E.global.general.UIScale")
    assert(math.abs(E.global.general.UIScale - value) < 1e-9, "and write the value it was set to")
    assert(slider.Cur.text == string.format("%.2f", slider:GetValue()),
        "the slider must show what it wrote")
end
assert(E.scaleApplied == appliedBefore, "dragging the slider must never apply the scale")

-- Auto Scale is ElvUI's own E:PixelBestSize(), unrounded, and also only sets it.
E.screenheight = 1440
local best = E:PixelBestSize()
assert(best ~= 0.53, "the Auto Scale value must not be the 0.01 step (the test would be vacuous)")
local appliedBeforeAuto = E.scaleApplied
local text = pressOption()
assert(text == "Auto Scale", "the scale page's first button is Auto Scale")
assert(E.global.general.UIScale == best,
    "Auto Scale must write the value PixelBestSize() returned, not the slider's step")
-- The client's Slider:SetValue snaps to the 0.01 step; the mock does not model
-- the snap (dc_widget_mock.lua SetValue), so the step-loss is asserted on what
-- the addon writes instead: the unrounded PixelBestSize(), not its step. The
-- vacuity guard is above (best ~= 0.53).
local stepped = math.floor(best / 0.01 + 0.5) * 0.01
assert(E.global.general.UIScale ~= stepped,
    "Auto Scale must write the unrounded value, not the 0.01 step")
assert(slider.value == best, "Auto Scale must move the slider to the value it wrote")
assert(slider.Cur.text == string.format("%.2f", best), "Auto Scale must show the value it wrote")
assert(E.scaleApplied == appliedBeforeAuto, "Auto Scale must not apply the scale either")
E.screenheight = 1080

-- Preview is the only thing that applies it, exactly once per press, with the
-- same call ElvUI's own Preview makes.
local beforePreview = E.scaleApplied
local preview = PluginInstallFrame.Option2
local previewText = preview.text
preview.scripts.OnClick()
assert(previewText == "Preview", "page 3's second button is Preview")
assert(E.scaleApplied == beforePreview + 1, "Preview must apply the scale exactly once")
assert(E.lastScaleChange.event == nil and E.lastScaleChange.skip == true,
    "Preview must be E:PixelScaleChanged(nil, true)")
preview.scripts.OnClick()
assert(E.scaleApplied == beforePreview + 2, "a second press applies it a second time, once")
assert(E.global.general.UIScale == best, "Preview must not change the value")

-- None of that is a profile change: UIScale is account-wide and ElvUI's own
-- import blacklist drops it (Distributor.lua:274), so the profile and its
-- export are untouched by this page.
assert(E.data.profiles["Torment"] == profileBefore, "the scale page must not replace the profile")
assert(E.db == E.data.profiles["Torment"], "E.db must still be the profile")
assert(E.data.keys.profile == "Torment", "the scale page must not switch profiles")
local keysAfter = {}
for key in pairs(profileBefore) do keysAfter[#keysAfter + 1] = key end
assert(#keysAfter == #profileKeys, "the scale page must not add a profile key")
local tormentKeysAfter = {}
for key in pairs(profileBefore.torment) do tormentKeysAfter[#tormentKeysAfter + 1] = key end
assert(#tormentKeysAfter == #tormentKeys, "the scale page must not write into the profile's torment table")

-- Leaving the page hides the slider; coming back shows it, and showing never
-- applies anything.
PluginInstallFrame.SetPage(2, 1)
assert(not slider:IsShown(), "the apply page must not leave the slider on screen")
local beforeReturn = E.scaleApplied
PluginInstallFrame.SetPage(3, 2)
assert(slider:IsShown(), "the scale page shows the slider again")
assert(E.scaleApplied == beforeReturn, "returning to the scale page must not apply anything")
PluginInstallFrame.SetPage(4, 3)
assert(not slider:IsShown(), "the done page must not leave the slider on screen")
assert(PluginInstallFrame.Desc1.text:find("reload"), "the done page still points at the reload")

-- ---------------- 8. the first login after an update, with ElvUI's Layout down
--
-- diablocraft-i6jgl (Nightly 94): Apply errored at Layout.lua:47, BottomPanel
-- nil, from UpdateAll under SetProfile. ElvUI is initialised long before any
-- click (E.initialized is set inside PLAYER_LOGIN), so the panel is missing only
-- when Layout's own Initialize threw at login - CallbackHandler reports it and
-- ElvUI carries on. Driven as the designer met it: a character on the previous layout
-- (4) with "Torment" already active logs in, Layout fails, the raised
-- layoutVersion brings the installer up, and he presses Apply.
PluginInstallFrame:Hide()
PluginInstaller.Installs = {}

-- AceDB's callbacks, as CallbackHandler-1.0 keeps them: one method per target
-- per event, fired by SetProfile (AceDB-3.0 DBObjectLib:SetProfile).
local callbacks = {}
E.data = {keys = {profile = "Torment"}, global = {general = {UIScale = 1}},
          profiles = {Torment = {torment = {bar1Scale = 1}}, OldLayout = seedProfiles["OldLayout"]}}
function E.data.RegisterCallback(target, event, method)
    callbacks[event] = callbacks[event] or {}
    callbacks[event][target] = method
end
function E.data.UnregisterCallback(target, event)
    if callbacks[event] then callbacks[event][target] = nil end
end
function E.data:SetProfile(name)
    if name == self.keys.profile then return end
    self.keys.profile = name
    for target, method in pairs(callbacks.OnProfileChanged or {}) do target[method](target, "OnProfileChanged") end
end
E.data.RegisterCallback(E, "OnProfileChanged", "UpdateAll") -- Core.lua:1264
E.db = E.data.profiles["Torment"]
local oldDb = E.db

-- Layout registers before this addon (ElvUI.toc loads Layout before any
-- plugin), and its Initialize stops before it makes BottomPanel.
local layout = E.Modules["Layout"]
layout.BottomPanel = nil
table.insert(registered, 1, {"Layout", function() error("Layout.lua:20: login failure") end})
ElvUI_TormentDB.layoutVersion = 4
E.private = {install_complete = "6.09"}
moduleErrors = {}
E:Initialize()
table.remove(registered, 1)
assert(#moduleErrors == 1 and moduleErrors[1]:find("^Layout"), "only Layout's own login error is raised")
assert(PluginInstaller.showing == Installer.installTable and PluginInstallFrame.CurrentPage == 1,
    "the raised layoutVersion brings the installer up on the first login after the update")

pressNext()
payload.torment.bar1Scale = 0.77
local applied, applyErr = pcall(pressOption)
assert(applied, "Apply must not raise with Layout down: " .. tostring(applyErr))
assert(applyErr == "Apply the Torment layout", "the button pressed was Apply")
assert(PluginInstallFrame.CurrentPage == 3, "Apply must move on to the UI Scale page")
assert(E.data.keys.profile == "Torment", "Torment must be the active profile after the reload")
assert(E.data.profiles["Torment"].torment.bar1Scale == 0.77, "the new layout must be written")
assert(E.data.profiles["Torment_Temp"] == nil, "no _Temp profile is left behind")
assert(E.data.profiles["OldLayout"] == seedProfiles["OldLayout"], "no other profile is touched")
assert(E.db == oldDb, "ElvUI's live refresh must not run without Layout's panels")
assert(callbacks.OnProfileChanged[E] == "UpdateAll", "ElvUI's handler must be registered again")
pressNext()
assert(pressOption() == "Reload UI", "the Done page's reload applies it")

-- With Layout up (after that reload) the same apply refreshes live, through
-- the handler that was put back.
layout.BottomPanel = {}
payload.torment.bar1Scale = 0.5
assert(Installer:ApplyProfile(), "an apply with Layout up succeeds")
assert(E.db == E.data.profiles["Torment"] and E.db.torment.bar1Scale == 0.5,
    "with Layout up ElvUI's UpdateAll must run and repoint E.db")

realPrint("test_elvui_installer: all installer mock checks passed")
