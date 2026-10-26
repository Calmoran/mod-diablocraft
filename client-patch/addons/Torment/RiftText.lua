-- luacheck: globals Diablocraft CreateFrame UIParent GameFontNormalHuge UnitName
-- The rifts' centre-screen lines (the wire is docs/contracts/rift-centre-text.md): the server sends a line's
-- kind and its parts, each a colour and its text, over the DCRIFTTEXT addon whisper, and this draws it in the
-- middle of the upper screen in D3's manner: no frame, the words alone with a dark shadow, fading in, holding
-- and fading out. The words and the colours are the server's; the size, the place and the timing are this
-- file's, per kind, so the look changes with no server change.
--
-- Stock 3.3.5a fonts only: Morpheus, the stock face of the quest and book titles and the nearest the stock
-- client has to D3's lettering. Nothing here ships a texture or a font.

Diablocraft = Diablocraft or {}
local DC = Diablocraft
DC.RiftText = DC.RiftText or {}
local R = DC.RiftText

local PREFIX = "DCRIFTTEXT"

R.FONT = "Fonts\\MORPHEUS.TTF"
-- Where the line stands: the share of the screen's height from its top edge to the line's top.
R.TOP_SHARE = 0.22
R.SHADOW = { 0, 0, 0, 0.9 }

-- Seconds in, held and out, and the size in points, for a kind the server names. A kind not in this table
-- is drawn with `default`, so a new server kind shows before the client gives it a look of its own. Look
-- constants of the screen, not game numbers.
R.LOOKS = {
    default = { size = 26, fadeIn = 0.3, hold = 4, fadeOut = 1.2 },
    gr_complete = { size = 30, fadeIn = 0.4, hold = 5, fadeOut = 1.5 },
}

local WHITE = "ffffff"

local frame, text
local clock, look   -- seconds since the line appeared; the look it plays

local function lookFor(kind)
    return R.LOOKS[kind] or R.LOOKS.default
end

local function build()
    if frame then return end
    frame = CreateFrame("Frame", nil, UIParent)
    frame:SetFrameStrata("HIGH")
    frame:SetSize(1800, 64)   -- wider than the longest line at the largest size, so it never wraps
    -- A stock font object first, so the text has a font whatever the client does with the path below.
    text = frame:CreateFontString(nil, "OVERLAY")
    text:SetFontObject(GameFontNormalHuge)
    text:SetAllPoints(frame)
    text:SetJustifyH("CENTER")
    text:SetWordWrap(false)
    text:SetShadowColor(R.SHADOW[1], R.SHADOW[2], R.SHADOW[3], R.SHADOW[4])
    text:SetShadowOffset(2, -2)
    frame:Hide()
end

-- Alpha at `t` seconds into the look: up over fadeIn, full to the end of the hold, down over fadeOut, then nil.
function R.AlphaAt(t, l)
    if t < 0 then return 0 end
    if t < l.fadeIn then return t / l.fadeIn end
    if t < l.fadeIn + l.hold then return 1 end
    local out = t - l.fadeIn - l.hold
    if out < l.fadeOut then return 1 - out / l.fadeOut end
    return nil
end

local function onUpdate(_, delta)
    clock = clock + delta
    local alpha = R.AlphaAt(clock, look)
    if not alpha then
        frame:Hide()
        return
    end
    frame:SetAlpha(alpha)
end

-- A colour is six hex digits; anything else is drawn white rather than as a broken escape.
local function colourOf(value)
    if type(value) == "string" and value:match("^%x%x%x%x%x%x$") then return value end
    return WHITE
end

-- Draw a line now, replacing the one on screen. `parts` is a list of {colour =, text =}.
function R.Show(kind, parts)
    build()
    local l = lookFor(kind)
    local pieces = {}
    for _, part in ipairs(parts) do
        pieces[#pieces + 1] = "|cff" .. colourOf(part.colour) .. part.text .. "|r"
    end
    text:SetFont(R.FONT, l.size, "")
    text:SetText(table.concat(pieces))
    frame:ClearAllPoints()
    frame:SetPoint("TOP", UIParent, "TOP", 0, -math.floor(UIParent:GetHeight() * R.TOP_SHARE))
    clock, look = 0, l
    frame:SetAlpha(0)
    frame:SetScript("OnUpdate", onUpdate)
    frame:Show()
end

-- C|<kind>|<colour>|<text>|<colour>|<text>...; a record that is not that shape (another record type, a newer
-- one, an odd field count, an empty text) draws nothing. Returns whether a line was drawn.
function R.Receive(message)
    local fields = {}
    for field in (message .. "|"):gmatch("(.-)|") do fields[#fields + 1] = field end
    if fields[1] ~= "C" or not fields[2] or not fields[2]:match("^[a-z_]+$") then return false end
    local count = #fields - 2
    if count < 2 or count % 2 ~= 0 then return false end
    local parts = {}
    for i = 3, #fields, 2 do
        if fields[i + 1] == "" then return false end
        parts[#parts + 1] = { colour = fields[i], text = fields[i + 1] }
    end
    R.Show(fields[2], parts)
    return true
end

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("CHAT_MSG_ADDON")
watcher:SetScript("OnEvent", function(_, _, prefix, message, distribution, sender)
    if prefix ~= PREFIX or distribution ~= "WHISPER" or sender ~= UnitName("player") then return end
    R.Receive(message)
end)
