-- luacheck: globals AIO GetAddOnMetadata DEFAULT_CHAT_FRAME IsAddOnLoaded
-- Diablocraft - client-patch mismatch notice, addon half.
--
-- AIO bridge `DiablocraftVersion` (docs/contracts/version-enforcement.md). On
-- initialization the addon sends one `Report(client_patch)` carrying its TOC
-- `X-Torment-Client-Patch` value (a decimal string). The server answers
-- `Status(module, schema, server_client_patch, client_patch, addon, mismatch,
-- message)`. When `message` is non-nil (older patch, or no value) it is shown
-- once in chat and in this addon's notice frame, and the session is marked so a
-- zone change never repeats it. This never blocks login: there is no kick, no
-- refusal, and a matching patch shows nothing at all.
local AIO = AIO or (require and require("AIO"))
local CHANNEL = "DiablocraftVersion"
local ADDON = "Torment"
local PREFIX = "|cfff0c96aTorment|r: "

local warned = false
local notice

local function clientPatch()
    local value = GetAddOnMetadata and GetAddOnMetadata(ADDON, "X-Torment-Client-Patch")
    if not value then return "" end
    return (value:gsub("%s", ""))
end

local function ensureFrame()
    if notice then return notice end
    notice = CreateFrame("Frame", "TormentVersionNotice", UIParent)
    notice:SetPoint("TOP", UIParent, "TOP", 0, -120)
    notice:SetWidth(520)
    notice:SetHeight(84)
    notice:SetFrameStrata("DIALOG")
    notice:SetMovable(true)
    notice:EnableMouse(true)
    notice:RegisterForDrag("LeftButton")
    notice:SetScript("OnDragStart", notice.StartMoving)
    notice:SetScript("OnDragStop", notice.StopMovingOrSizing)
    local text = notice:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    text:SetPoint("TOPLEFT", 12, -12)
    text:SetPoint("BOTTOMRIGHT", -12, 12)
    text:SetJustifyH("LEFT")
    notice.text = text
    return notice
end

-- One per session: later Status replies (zone changes, refreshes) return early.
local function warn(message)
    if warned or not message then return end
    warned = true
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage(PREFIX .. message) end
    local frame = ensureFrame()
    frame.text:SetText(message)
    frame:Show()
end

if AIO then
    local handlers = AIO.AddHandlers(CHANNEL, {})
    function handlers.Status(_, _module, _schema, _serverPatch, _patch, _addon, _mismatch, message)
        warn(message)
    end

    local sent = false
    local function report()
        if sent or not AIO.Handle then return end
        sent = true
        AIO.Handle(CHANNEL, "Report", clientPatch())
    end

    local loader = CreateFrame("Frame")
    loader:RegisterEvent("PLAYER_ENTERING_WORLD")
    loader:SetScript("OnEvent", report)
    if IsAddOnLoaded and IsAddOnLoaded("AIO_Client") then report() end
end
