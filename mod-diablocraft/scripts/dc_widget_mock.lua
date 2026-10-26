-- dc_widget_mock.lua -- the ONE strict 3.3.5a widget mock every Lua UI test uses
-- (diablocraft-yey2). The old tests each carried their own loose stub: one that
-- answered every uppercase call with a no-op, mirrored SetSize into a public
-- .height field, took any argument count and handed out a StatusBar texture
-- before SetStatusBarTexture ran. A whole window was dead in game with every
-- test green (the Mystic's SetShown, 2026-10-05). This mock makes the same
-- mistake fail in the test.
--
-- Load it from a test that runs from the repo root:
--
--   local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
--   Mock.install()               -- defines CreateFrame, UIParent, hooksecurefunc, ...
--   local frames = Mock.frames   -- every widget made, in creation order
--
-- The rules, one per test in test_dc_widget_mock.lua:
--   1. Only 3.3.5a methods exist. A method the client lacks (SetShown,
--      SetColorTexture, ...) is simply not there, so calling it raises the same
--      "attempt to call method 'X' (a nil value)" the client raises. A method
--      that belongs to another widget kind (Texture:SetText) raises instead.
--   2. Argument counts the client checks are checked here: SetTexCoord takes 4
--      or 8 numbers, SetPoint takes a point name and at most four more values.
--   3. Sizes are private. SetWidth/SetHeight/SetSize write nothing a caller can
--      read as .width/.height -- only GetWidth()/GetHeight() answer, as the
--      client does, so addon code reading the field fails here as it does there.
--   4. A StatusBar's GetStatusBarTexture() is nil until SetStatusBarTexture ran
--      (a bar with no texture draws nothing, whatever the tint).
--   5. A FontString refuses SetText until it has a font -- from its template, SetFont
--      or SetFontObject (the live "<name>:SetText(): Font not set", diablocraft-scog).
--   6. hooksecurefunc records the wrapper it installed in Mock.hooks, so a test can
--      tell a hook from a plain replacement (_G[name] == Mock.hooks[name]), and it
--      refuses to hook a name that is not a function, as the client does.
--   7. AIO.SavePosition models LibWindow (register + restore + save, so a second call
--      re-applies the stored place, and the first call centres a frame with nothing
--      stored) and Mock.dragBegin models drag routing (the frame under the cursor
--      takes the drag, and StartMoving needs SetMovable(true)).
--
-- The method set is the 3.3.5a client API this project uses; the names are the
-- client's own (verified against the pinned 3.3.5a FrameXML,
-- _agent-scratch/pm-ui-audit-framexml-stock, wowgaming/3.3.5-interface-files
-- d0339b17b) and the known-missing list (SetShown, SetColorTexture, C_Timer,
-- BackdropTemplate) is absent by construction.
--
-- This is a widget double, not a client: it proves what the addon CALLS, never
-- what it draws. Kept in the repo beside the tests (mod-diablocraft/scripts/ is
-- the tests' own lane).

-- Targets Lua 5.1, the client's own: the mock and the UI tests must run under
-- `lua5.1`, and they are run under `lua` (5.2) too. Nothing here may use a 5.2+
-- name (table.pack, goto, bit32) without the fallback below.
local unpack = table.unpack or unpack
-- Lua 5.1 has no table.pack.
local pack = table.pack or function(...) return {n = select("#", ...), ...} end

local M = {}
M.frames = {}          -- every widget, in creation order
M.methods = {}         -- method name -> {kinds = <set or nil for every kind>, fn = ...}
M.savedPositions = {}  -- every AIO.SavePosition call, in order
M.hooks = {}           -- global name -> the wrapper hooksecurefunc installed
M.knownMissing = {     -- names the 3.3.5a client does not have; must never exist here
    "SetShown", "SetColorTexture", "SetColorGradient", "BackdropTemplate",
    "C_Timer", "C_Map", "SetBackdropTemplate", "SetDrawLayerColor",
    "CreateFramePool", "SetIgnoreParentAlpha", "SetMouseClickEnabled", "SetMouseMotionEnabled",
}
M.env = _G

-- ------------------------------------------------------------------ widget kinds
-- Which kinds each method belongs to. Frame methods reach every frame kind;
-- Texture/FontString/StatusBar/... methods only their own (so Texture:SetText,
-- which the client has no way to run, fails here).
local FRAME_KINDS = {Frame = true, Button = true, CheckButton = true, StatusBar = true,
    Slider = true, EditBox = true, ScrollFrame = true, ScrollingEditBox = true,
    GameTooltip = true, Cooldown = true, Model = true, PlayerModel = true, Minimap = true,
    SimpleHTML = true, MessageFrame = true}
local BUTTON_KINDS = {Button = true, CheckButton = true}
local BAR_KINDS = {StatusBar = true, Slider = true}
local TEXTURE_KINDS = {Texture = true}
local FONT_KINDS = {FontString = true}
local EDIT_KINDS = {EditBox = true, ScrollingEditBox = true}
local SCROLL_KINDS = {ScrollFrame = true}
local TIP_KINDS = {GameTooltip = true}
local TEXT_KINDS = {Button = true, CheckButton = true, FontString = true, EditBox = true,
    ScrollingEditBox = true}
-- SetText reaches the tooltip too (GameTooltip:SetText is stock 3.3.5a and
-- dc_crafting.lua:819 calls it); the other FontInstance methods stay off it.
local SET_TEXT_KINDS = {Button = true, CheckButton = true, FontString = true, EditBox = true,
    ScrollingEditBox = true, GameTooltip = true}
local DRAWN_KINDS = {Texture = true, FontString = true}  -- SetDrawLayer/GetDrawLayer

local function m(kinds, fn) return {kinds = kinds, fn = fn} end

-- ------------------------------------------------------------------ geometry
-- Frames are placed with SetPoint; GetLeft/GetTop resolve the anchor chain up to
-- a frame with an explicit rectangle (SetScreen below, or a test's own _rect).
local function widthOf(self)
    if self._w then return self._w end
    if self._rect then return self._rect[3] end
    if self.allPoints and self.allPoints.GetWidth then return self.allPoints:GetWidth() end
    return 0
end
local function heightOf(self)
    if self._h then return self._h end
    if self._rect then return self._rect[4] end
    if self.allPoints and self.allPoints.GetHeight then return self.allPoints:GetHeight() end
    return 0
end
local function rectOf(self, depth)
    depth = (depth or 0) + 1
    if depth > 16 then return nil end
    if self._rect then return self._rect[1], self._rect[2], self._rect[3], self._rect[4] end
    local w, h = widthOf(self), heightOf(self)
    if self.allPoints and not self.points[1] then
        return rectOf(self.allPoints, depth)
    end
    local anchor = self.points[1]
    local base = (anchor and anchor.relativeTo) or self.parent
    if not base then return nil end
    local bl, bb, bw, bh = rectOf(base, depth)
    if not bl then return nil end
    local bt = bb + bh
    local point = anchor and anchor.point or "TOPLEFT"
    local x, y = anchor and anchor.x or 0, anchor and anchor.y or 0
    local left, top
    if point:find("LEFT") then left = bl + x
    elseif point:find("RIGHT") then left = bl + bw + x - w
    else left = bl + bw / 2 + x - w / 2 end
    if point:find("TOP") then top = bt + y
    elseif point:find("BOTTOM") then top = bt - bh + y + h
    else top = bt - bh / 2 + y + h / 2 end
    return left, top - h, w, h
end

local function copyPoints(points)
    local out = {}
    for i, p in ipairs(points or {}) do
        out[i] = {p[1], p[2], p[3], p[4], p[5], point = p[1], relativeTo = p[2],
                  relativePoint = p[3], x = p[4], y = p[5]}
    end
    return out
end

-- ------------------------------------------------------------------ the method table
function M.regionsOf(frame)
    local out = {}
    for _, child in ipairs(frame.children) do
        local kind = child._kind or child.kind
        if kind == "Texture" or kind == "FontString" or kind == "Line" then
            out[#out + 1] = child
        end
    end
    return out
end

function M.childrenOf(frame)
    local out = {}
    for _, child in ipairs(frame.children) do
        local kind = child._kind or child.kind
        if kind ~= "Texture" and kind ~= "FontString" and kind ~= "Line" then
            out[#out + 1] = child
        end
    end
    return out
end

local function register()
    local mt = M.methods
    -- Region: every kind
    -- Show()/Hide() run the frame's own OnShow/OnHide, as the client does (the
    -- Blacksmith window cancels on OnHide, dc_blacksmith.lua:551).
    mt.Show = m(nil, function(self)
        self.shown = true
        local fn = self.scripts and self.scripts.OnShow
        if fn then fn(self) end
    end)
    mt.Hide = m(nil, function(self)
        self.shown = false
        local fn = self.scripts and self.scripts.OnHide
        if fn then fn(self) end
    end)
    mt.IsShown = m(nil, function(self) return self.shown end)
    mt.IsVisible = m(nil, function(self)
        if not self.shown then return false end
        return not self.parent or self.parent:IsVisible()
    end)
    mt.SetPoint = m(nil, function(self, ...)
        local n = select("#", ...)
        assert(n >= 1 and n <= 5, "SetPoint takes a point name and up to four more values, got " .. n)
        local point, relativeTo, relativePoint, x, y = ...
        assert(type(point) == "string", "SetPoint's first argument is a point name, got " .. type(point))
        -- Both forms: tests index the anchor by position (point[1] == "TOPLEFT"),
        -- the geometry reads it by name.
        self.points[#self.points + 1] = { point, relativeTo, relativePoint, x, y,
            point = point, relativeTo = relativeTo, relativePoint = relativePoint, x = x, y = y }
    end)
    mt.GetPoint = m(nil, function(self, index)
        local p = assert(self.points[index or 1], "this frame has no point " .. tostring(index or 1))
        return p[1], p[2], p[3], p[4], p[5]
    end)
    mt.GetNumPoints = m(nil, function(self) return #self.points end)
    mt.ClearAllPoints = m(nil, function(self) self.points = {} end)
    mt.SetAllPoints = m(nil, function(self, relativeTo) self.allPoints = relativeTo or self.parent end)
    mt.SetSize = m(nil, function(self, w, h) self._w, self._h = w, h end)
    mt.SetWidth = m(nil, function(self, w) self._w = w end)
    mt.SetHeight = m(nil, function(self, h) self._h = h end)
    mt.GetWidth = m(nil, function(self) return widthOf(self) end)
    mt.GetHeight = m(nil, function(self) return heightOf(self) end)
    mt.GetSize = m(nil, function(self) return widthOf(self), heightOf(self) end)
    mt.GetLeft = m(nil, function(self) local l = rectOf(self) return l end)
    mt.GetBottom = m(nil, function(self) local _, b = rectOf(self) return b end)
    mt.GetTop = m(nil, function(self) local _, b, _, h = rectOf(self) if h == nil then return nil end return b + h end)
    mt.GetRight = m(nil, function(self) local l, _, w = rectOf(self) if w == nil then return nil end return l + w end)
    mt.GetRect = m(nil, function(self) return rectOf(self) end)
    mt.GetCenter = m(nil, function(self)
        local l, b, w, h = rectOf(self)
        if w == nil then return nil end
        return l + w / 2, b + h / 2
    end)
    mt.SetParent = m(nil, function(self, parent)
        self.parent = parent
        if parent and parent.children then parent.children[#parent.children + 1] = self end
    end)
    mt.GetParent = m(nil, function(self) return self.parent end)
    mt.GetName = m(nil, function(self) return self._name end)
    mt.GetObjectType = m(nil, function(self) return self._kind end)
    -- Scale, strata and frame level are Frame methods, not Region ones: the client has no
    -- Texture:SetScale or FontString:GetFrameLevel, and a test asking for one used to pass.
    mt.SetScale = m(FRAME_KINDS, function(self, scale) self.scale = scale end)
    mt.GetScale = m(FRAME_KINDS, function(self) return self.scale or 1 end)
    mt.GetEffectiveScale = m(FRAME_KINDS, function(self)
        return (self.scale or 1) * (self.parent and self.parent:GetEffectiveScale() or 1)
    end)
    mt.SetAlpha = m(nil, function(self, alpha) self.alpha = alpha end)
    mt.GetAlpha = m(nil, function(self) return self.alpha or 1 end)
    mt.GetFrameStrata = m(FRAME_KINDS, function(self)
        return self.strata or (self.parent and self.parent:GetFrameStrata()) or "MEDIUM"
    end)
    mt.SetFrameStrata = m(FRAME_KINDS, function(self, strata) self.strata = strata end)
    mt.GetFrameLevel = m(FRAME_KINDS, function(self)
        if self.level then return self.level end
        return self.parent and (self.parent:GetFrameLevel() + 1) or 0
    end)
    mt.SetFrameLevel = m(FRAME_KINDS, function(self, level) self.level = level end)
    mt.SetHitRectInsets = m(FRAME_KINDS, function(self, ...) self.hitRectInsets = { ... } end)
    -- Frame: script, events, dragging, mouse, children
    mt.SetScript = m(FRAME_KINDS, function(self, event, fn) self.scripts[event] = fn end)
    mt.GetScript = m(FRAME_KINDS, function(self, event) return self.scripts[event] end)
    -- HookScript runs the original script first, then the hook, as the client
    -- does (the Blacksmith hooks the bags' OnEnter/OnLeave, dc_blacksmith.lua:380).
    mt.HookScript = m(FRAME_KINDS, function(self, event, fn)
        local original = self.scripts[event]
        if original then
            self.scripts[event] = function(...)
                original(...)
                return fn(...)
            end
        else
            self.scripts[event] = function(...) return fn(...) end
        end
    end)
    mt.HasScript = m(FRAME_KINDS, function(self, event) return self.scripts[event] ~= nil end)
    mt.RegisterEvent = m(FRAME_KINDS, function(self, event) self.events[event] = true end)
    mt.UnregisterEvent = m(FRAME_KINDS, function(self, event) self.events[event] = nil end)
    mt.UnregisterAllEvents = m(FRAME_KINDS, function(self) self.events = {} end)
    mt.IsEventRegistered = m(FRAME_KINDS, function(self, event) return self.events[event] == true end)
    mt.SetMovable = m(FRAME_KINDS, function(self, movable) self.movable = movable ~= false end)
    mt.IsMovable = m(FRAME_KINDS, function(self) return self.movable == true end)
    mt.SetUserPlaced = m(FRAME_KINDS, function(self, placed) self.userPlaced = placed end)
    mt.IsUserPlaced = m(FRAME_KINDS, function(self) return self.userPlaced == true end)
    mt.SetClampedToScreen = m(FRAME_KINDS, function(self, clamped) self.clamped = clamped ~= false end)
    mt.IsClampedToScreen = m(FRAME_KINDS, function(self) return self.clamped == true end)
    mt.SetResizable = m(FRAME_KINDS, function(self, resizable) self.resizable = resizable end)
    mt.IsResizable = m(FRAME_KINDS, function(self) return self.resizable == true end)
    mt.SetMinResize = m(FRAME_KINDS, function(self, w, h) self.minResize = {w, h} end)
    mt.SetMaxResize = m(FRAME_KINDS, function(self, w, h) self.maxResize = {w, h} end)
    -- StartMoving is what OnDragStart=StartMoving calls: a frame only moves when
    -- the addon made it movable (the reviewer's rule 5).
    mt.StartMoving = m(FRAME_KINDS, function(self)
        assert(self.movable == true,
            (self.name or "a frame") .. ": StartMoving needs SetMovable(true) (diablocraft-xpuz)")
        self.moving = true
    end)
    mt.StopMovingOrSizing = m(FRAME_KINDS, function(self) self.moving = false end)
    mt.EnableMouse = m(FRAME_KINDS, function(self, enabled) self.mouseEnabled = enabled ~= false end)
    mt.EnableMouseWheel = m(FRAME_KINDS, function(self, enabled) self.mouseWheel = enabled ~= false end)
    mt.EnableKeyboard = m(FRAME_KINDS, function(self, enabled) self.keyboardEnabled = enabled ~= false end)
    mt.IsMouseEnabled = m(FRAME_KINDS, function(self) return self.mouseEnabled == true end)
    mt.RegisterForDrag = m(FRAME_KINDS, function(self, ...) self.drag = { ... } end)
    mt.RegisterForClicks = m(FRAME_KINDS, function(self, ...) self.clicks = { ... } end)
    mt.SetToplevel = m(FRAME_KINDS, function(self, top) self.toplevel = top end)
    mt.Raise = m(FRAME_KINDS, function(self) self.raised = true end)
    mt.Lower = m(FRAME_KINDS, function(self) self.raised = false end)
    mt.SetID = m(FRAME_KINDS, function(self, id) self.id = id end)
    mt.GetID = m(FRAME_KINDS, function(self) return self.id end)
    mt.SetAttribute = m(FRAME_KINDS, function(self, name, value)
        self.attributes = self.attributes or {}
        self.attributes[name] = value
    end)
    mt.GetAttribute = m(FRAME_KINDS, function(self, name)
        return self.attributes and self.attributes[name]
    end)
    mt.CreateTexture = m(FRAME_KINDS, function(self, name, layer, template, subLevel)
        local t = M.widget("Texture", name, self)
        t.drawLayer, t.subLevel, t.template = layer, subLevel or 0, template
        return t
    end)
    mt.CreateFontString = m(FRAME_KINDS, function(self, name, layer, template)
        local f = M.widget("FontString", name, self)
        f.drawLayer, f.template = layer, template
        return f
    end)
    -- The client returns them as multiple values, not a table: the addon does
    -- select(index, frame:GetRegions()) (dc_ground_plates.lua:121).
    mt.GetRegions = m(FRAME_KINDS, function(self) return unpack(M.regionsOf(self)) end)
    mt.GetNumRegions = m(FRAME_KINDS, function(self) return #M.regionsOf(self) end)
    mt.GetChildren = m(FRAME_KINDS, function(self) return unpack(M.childrenOf(self)) end)
    mt.GetNumChildren = m(FRAME_KINDS, function(self) return #M.childrenOf(self) end)
    mt.SetBackdrop = m(FRAME_KINDS, function(self, backdrop) self.backdrop = backdrop end)
    mt.GetBackdrop = m(FRAME_KINDS, function(self) return self.backdrop end)
    mt.SetBackdropColor = m(FRAME_KINDS, function(self, ...) self.backdropColor = { ... } end)
    mt.GetBackdropColor = m(FRAME_KINDS, function(self)
        local c = self.backdropColor or {}
        return c[1], c[2], c[3], c[4]
    end)
    mt.SetBackdropBorderColor = m(FRAME_KINDS, function(self, ...) self.borderColor = { ... } end)
    mt.GetBackdropBorderColor = m(FRAME_KINDS, function(self)
        local c = self.borderColor or {}
        return c[1], c[2], c[3], c[4]
    end)
    -- Texture / FontString / Line
    mt.SetTexture = m(TEXTURE_KINDS, function(self, texture, ...)
        self.texture = texture
        if type(texture) == "number" then self.textureColor = { texture, ... } end
    end)
    mt.GetTexture = m(TEXTURE_KINDS, function(self) return self.texture end)
    mt.SetTexCoord = m(TEXTURE_KINDS, function(self, ...)
        local n = select("#", ...)
        assert(n == 4 or n == 8, "SetTexCoord takes 4 or 8 numbers (the client's rule), got " .. n)
        self.texCoord = { ... }
    end)
    mt.GetTexCoord = m(TEXTURE_KINDS, function(self) return unpack(self.texCoord or {}) end)
    mt.SetVertexColor = m(TEXTURE_KINDS, function(self, ...) self.vertexColor = { ... } end)
    mt.GetVertexColor = m(TEXTURE_KINDS, function(self)
        local c = self.vertexColor or {}
        return c[1], c[2], c[3], c[4]
    end)
    mt.SetBlendMode = m(TEXTURE_KINDS, function(self, mode) self.blendMode = mode end)
    mt.GetBlendMode = m(TEXTURE_KINDS, function(self) return self.blendMode end)
    mt.SetDesaturated = m(TEXTURE_KINDS, function(self, value) self.desaturated = value end)
    mt.SetGradientAlpha = m(TEXTURE_KINDS, function(self, ...) self.gradientAlpha = { ... } end)
    mt.SetGradient = m(TEXTURE_KINDS, function(self, ...) self.gradient = { ... } end)
    mt.SetHorizTile = m(TEXTURE_KINDS, function(self, value) self.horizTile = value end)
    mt.SetVertTile = m(TEXTURE_KINDS, function(self, value) self.vertTile = value end)
    mt.SetRotation = m(TEXTURE_KINDS, function(self, radians) self.rotation = radians end)
    mt.SetDrawLayer = m(DRAWN_KINDS, function(self, layer, subLevel) self.drawLayer, self.subLevel = layer, subLevel end)
    mt.GetDrawLayer = m(DRAWN_KINDS, function(self) return self.drawLayer end)
    -- Font strings (and the text parts Button/EditBox inherit)
    mt.SetText = m(SET_TEXT_KINDS, function(self, text)
        -- The 3.3.5a client refuses text on a FontString with no font: it comes from
        -- its template, SetFont or SetFontObject, and until one of those ran SetText
        -- errors "<name>:SetText(): Font not set" -- the live error the old rift stub
        -- guarded (diablocraft-scog). Buttons and edit boxes carry their own font, so
        -- only a bare FontString is refused.
        if (self._kind or self.kind) == "FontString"
            and not (self.font or self.fontObject or self.template) then
            error("SetText(): Font not set", 2)
        end
        -- GameTooltip:SetText is the tooltip's first line, not a widget string
        -- (GameTooltip.lines is what every test reads).
        if (self._kind or self.kind) == "GameTooltip" then
            self.lines = { text }
        else
            self.text = text
        end
    end)
    mt.GetText = m(TEXT_KINDS, function(self) return self.text end)
    mt.SetFormattedText = m(TEXT_KINDS, function(self, format, ...) self.text = string.format(format, ...) end)
    mt.SetTextColor = m(TEXT_KINDS, function(self, ...) self.textColor = { ... } end)
    mt.GetTextColor = m(TEXT_KINDS, function(self)
        local c = self.textColor or {}
        return c[1], c[2], c[3], c[4]
    end)
    mt.SetFont = m(TEXT_KINDS, function(self, path, size, flags) self.font, self.fontSize, self.fontFlags = path, size, flags end)
    mt.GetFont = m(TEXT_KINDS, function(self) return self.font, self.fontSize, self.fontFlags end)
    mt.SetFontObject = m(TEXT_KINDS, function(self, font) self.fontObject = font end)
    mt.GetFontObject = m(TEXT_KINDS, function(self) return self.fontObject end)
    mt.SetJustifyH = m(TEXT_KINDS, function(self, justify) self.justify = justify end)
    mt.GetJustifyH = m(TEXT_KINDS, function(self) return self.justify end)
    mt.SetJustifyV = m(TEXT_KINDS, function(self, justify) self.justifyV = justify end)
    mt.GetJustifyV = m(TEXT_KINDS, function(self) return self.justifyV end)
    mt.SetWordWrap = m(TEXT_KINDS, function(self, wrap) self.wordWrap = wrap end)
    mt.SetNonSpaceWrap = m(TEXT_KINDS, function(self, wrap) self.nonSpaceWrap = wrap end)
    mt.SetShadowColor = m(TEXT_KINDS, function(self, ...) self.shadowColor = { ... } end)
    mt.SetShadowOffset = m(TEXT_KINDS, function(self, x, y) self.shadowOffset = {x, y} end)
    mt.GetStringWidth = m(TEXT_KINDS, function(self) return #tostring(self.text or "") * 7 end)
    mt.GetStringHeight = m(TEXT_KINDS, function(self)
        local text = tostring(self.text or "")
        if #text == 0 then return 0 end
        local perLine = math.max(1, math.floor((self._w or 200) / 7))
        return math.max(1, math.ceil(#text / perLine)) * 17
    end)
    -- One entry, two kinds: a tooltip counts the lines it holds, a text widget the
    -- lines its string wraps to. A second registration under this name replaced the
    -- first for EVERY kind, so a FontString's NumLines always answered 0.
    mt.NumLines = m(SET_TEXT_KINDS, function(self)
        if (self._kind or self.kind) == "GameTooltip" then return #(self.lines or {}) end
        local text = tostring(self.text or "")
        if #text == 0 then return 0 end
        local perLine = math.max(1, math.floor((self._w or 200) / 7))
        return math.max(1, math.ceil(#text / perLine))
    end)
    -- Button
    mt.Enable = m(BUTTON_KINDS, function(self) self.disabled = false end)
    mt.Disable = m(BUTTON_KINDS, function(self) self.disabled = true end)
    mt.IsEnabled = m(BUTTON_KINDS, function(self) return self.disabled ~= true end)
    mt.SetChecked = m(BUTTON_KINDS, function(self, checked) self.checked = checked ~= false end)
    mt.GetChecked = m(BUTTON_KINDS, function(self) return self.checked == true end)
    mt.GetFontString = m(BUTTON_KINDS, function(self)
        if not self.fontString then
            self.fontString = M.widget("FontString", nil, self)
            self.fontString.drawLayer = "OVERLAY"
        end
        return self.fontString
    end)
    mt.SetNormalTexture = m(BUTTON_KINDS, function(self, texture)
        self.normalTexture = type(texture) == "string" and M.widget("Texture", nil, self) or texture
        if type(texture) == "string" then self.normalTexture:SetTexture(texture) end
    end)
    mt.GetNormalTexture = m(BUTTON_KINDS, function(self) return self.normalTexture end)
    mt.SetHighlightTexture = m(BUTTON_KINDS, function(self, texture, mode)
        self.highlightTexture = type(texture) == "string" and M.widget("Texture", nil, self) or texture
        if type(texture) == "string" then
            self.highlightTexture:SetTexture(texture)
            self.highlightTexture.blendMode = mode
        end
    end)
    mt.GetHighlightTexture = m(BUTTON_KINDS, function(self) return self.highlightTexture end)
    -- A path makes a texture the getter hands back, exactly as Normal/Highlight
    -- above do: the stock client calls GetPushedTexture():SetTexCoord(...) after
    -- SetPushedTexture(path) (VehicleMenuBar.lua:664-665 of the pinned FrameXML).
    mt.SetPushedTexture = m(BUTTON_KINDS, function(self, texture)
        self.pushedTexture = type(texture) == "string" and M.widget("Texture", nil, self) or texture
        if type(texture) == "string" then self.pushedTexture:SetTexture(texture) end
    end)
    mt.GetPushedTexture = m(BUTTON_KINDS, function(self) return self.pushedTexture end)
    mt.SetDisabledTexture = m(BUTTON_KINDS, function(self, texture)
        self.disabledTexture = type(texture) == "string" and M.widget("Texture", nil, self) or texture
        if type(texture) == "string" then self.disabledTexture:SetTexture(texture) end
    end)
    mt.GetDisabledTexture = m(BUTTON_KINDS, function(self) return self.disabledTexture end)
    mt.Click = m(BUTTON_KINDS, function(self)
        local fn = self.scripts and self.scripts.OnClick
        if fn then fn(self, "LeftButton") end
    end)
    -- StatusBar / Slider
    mt.SetMinMaxValues = m(BAR_KINDS, function(self, minValue, maxValue) self.minValue, self.maxValue = minValue, maxValue end)
    mt.GetMinMaxValues = m(BAR_KINDS, function(self) return self.minValue, self.maxValue end)
    mt.SetValue = m(BAR_KINDS, function(self, value) self.value = value end)
    mt.GetValue = m(BAR_KINDS, function(self) return self.value end)
    mt.SetOrientation = m(BAR_KINDS, function(self, orientation) self.orientation = orientation end)
    mt.GetOrientation = m(BAR_KINDS, function(self) return self.orientation end)
    mt.SetValueStep = m(BAR_KINDS, function(self, step) self.valueStep = step end)
    mt.GetValueStep = m(BAR_KINDS, function(self) return self.valueStep end)
    mt.SetThumbTexture = m(BAR_KINDS, function(self, texture) self.thumbTexture = texture end)
    -- The scroll bar's knob (a Slider's, as UIPanelScrollBarTemplate's ThumbTexture makes it).
    mt.GetThumbTexture = m({Slider = true}, function(self) return self.thumbTexture end)
    -- What makes a bar draw at all: no SetStatusBarTexture, no texture (reviewer's rule 4).
    mt.SetStatusBarTexture = m(BAR_KINDS, function(self, texture)
        if type(texture) == "string" then
            local t = M.widget("Texture", nil, self)
            t:SetTexture(texture)
            self.statusBarTexture = t
        else
            self.statusBarTexture = texture
        end
    end)
    mt.GetStatusBarTexture = m(BAR_KINDS, function(self) return self.statusBarTexture end)
    mt.SetStatusBarColor = m(BAR_KINDS, function(self, ...) self.statusBarColor = { ... } end)
    mt.GetStatusBarColor = m(BAR_KINDS, function(self)
        local c = self.statusBarColor or {}
        return c[1], c[2], c[3], c[4]
    end)
    -- EditBox
    mt.SetMaxLetters = m(EDIT_KINDS, function(self, letters) self.maxLetters = letters end)
    mt.GetMaxLetters = m(EDIT_KINDS, function(self) return self.maxLetters end)
    mt.SetMaxBytes = m(EDIT_KINDS, function(self, bytes) self.maxBytes = bytes end)
    mt.SetMultiLine = m(EDIT_KINDS, function(self, multiline) self.multiLine = multiline end)
    mt.IsMultiLine = m(EDIT_KINDS, function(self) return self.multiLine == true end)
    mt.SetAutoFocus = m(EDIT_KINDS, function(self, autoFocus) self.autoFocus = autoFocus end)
    mt.SetTextInsets = m(EDIT_KINDS, function(self, left, right, top, bottom) self.textInsets = {left, right, top, bottom} end)
    mt.SetFocus = m(EDIT_KINDS, function(self) self.focused = true end)
    mt.ClearFocus = m(EDIT_KINDS, function(self) self.focused = false end)
    mt.HasFocus = m(EDIT_KINDS, function(self) return self.focused == true end)
    mt.SetNumeric = m(EDIT_KINDS, function(self, numeric) self.numeric = numeric end)
    mt.SetNumber = m(EDIT_KINDS, function(self, number) self.text = tostring(number) end)
    mt.GetNumber = m(EDIT_KINDS, function(self) return tonumber(self.text) end)
    mt.Insert = m(EDIT_KINDS, function(self, text) self.text = (self.text or "") .. text end)
    mt.HighlightText = m(EDIT_KINDS, function(self) self.highlighted = true end)
    mt.SetCursorPosition = m(EDIT_KINDS, function(self, position) self.cursorPosition = position end)
    mt.GetCursorPosition = m(EDIT_KINDS, function(self) return self.cursorPosition or 0 end)
    mt.SetAltArrowKeyMode = m(EDIT_KINDS, function(self, mode) self.altArrowKeyMode = mode end)
    mt.GetAltArrowKeyMode = m(EDIT_KINDS, function(self) return self.altArrowKeyMode end)
    -- ScrollFrame
    mt.SetScrollChild = m(SCROLL_KINDS, function(self, child) self.scrollChild = child end)
    mt.GetScrollChild = m(SCROLL_KINDS, function(self) return self.scrollChild end)
    mt.SetVerticalScroll = m(SCROLL_KINDS, function(self, value) self.verticalScroll = value end)
    mt.GetVerticalScroll = m(SCROLL_KINDS, function(self) return self.verticalScroll or 0 end)
    mt.SetHorizontalScroll = m(SCROLL_KINDS, function(self, value) self.horizontalScroll = value end)
    mt.GetHorizontalScroll = m(SCROLL_KINDS, function(self) return self.horizontalScroll or 0 end)
    mt.GetVerticalScrollRange = m(SCROLL_KINDS, function(self) return self.verticalScrollRange or 0 end)
    mt.GetHorizontalScrollRange = m(SCROLL_KINDS, function(self) return self.horizontalScrollRange or 0 end)
    mt.UpdateScrollChildRect = m(SCROLL_KINDS, function(self) self.scrollRectUpdated = true end)
    -- GameTooltip
    mt.SetOwner = m(TIP_KINDS, function(self, owner, anchorType, x, y)
        self.owner, self.anchorType, self.anchorX, self.anchorY = owner, anchorType, x, y
        self.lines, self.lineRight, self.lineColors, self.lineRightColors = {}, {}, {}, {}
    end)
    mt.GetOwner = m(TIP_KINDS, function(self) return self.owner end)
    -- Stock GameTooltip.lua:136 (SetTooltipMoney) and :358 call it; it widens
    -- the tooltip at its next layout (Show).
    mt.SetMinimumWidth = m(TIP_KINDS, function(self, width) self.minimumWidth = width end)
    mt.GetItem = m(TIP_KINDS, function(self) return self.item end)
    mt.GetSpell = m(TIP_KINDS, function(self) return self.spell end)
    -- The client returns name, unit (ElvUI 6.09 Tooltip.lua:470 reads
    -- `local _, unit = tt:GetParent():GetUnit()`); the mock does not model the name.
    mt.GetUnit = m(TIP_KINDS, function(self) return nil, self.unit end)
    mt.AddLine = m(TIP_KINDS, function(self, text, ...)
        self.lines = self.lines or {}
        self.lines[#self.lines + 1] = text
        self.lineColors = self.lineColors or {}
        self.lineColors[#self.lines] = { ... }
    end)
    mt.AddDoubleLine = m(TIP_KINDS, function(self, left, right, lr, lg, lb, rr, rg, rb)
        -- One tooltip line with a left and a right region, rendered as the tests
        -- have always read it: "left | right". A right-only line still reads
        -- whole ("| Required Level: 70"), and a word that is only one half is not
        -- mistaken for a standalone line.
        self.lines = self.lines or {}
        self.lines[#self.lines + 1] = tostring(left or "") .. " | " .. tostring(right or "")
        self.lineRight = self.lineRight or {}
        self.lineRight[#self.lines] = right
        self.lineColors = self.lineColors or {}
        self.lineColors[#self.lines] = { lr, lg, lb }
        self.lineRightColors = self.lineRightColors or {}
        self.lineRightColors[#self.lines] = { rr, rg, rb }
    end)
    mt.AddMessage = m({GameTooltip = true, MessageFrame = true}, function(self, text)
        self.lines = self.lines or {}
        self.lines[#self.lines + 1] = text
    end)
    mt.ClearLines = m(TIP_KINDS, function(self) self.lines = {} end)
    mt.AppendText = m(TIP_KINDS, function(self, text)
        self.lines = self.lines or {}
        self.lines[#self.lines + 1] = (self.lines[#self.lines] or "") .. text
    end)
    mt.SetHyperlink = m(TIP_KINDS, function(self, link) self.hyperlink = link end)
    mt.SetInventoryItem = m(TIP_KINDS, function(self, ...) self.inventoryItem = { ... } end)
    mt.SetBagItem = m(TIP_KINDS, function(self, ...) self.bagItem = { ... } end)
    mt.SetAction = m(TIP_KINDS, function(self, ...) self.action = { ... } end)
    mt.SetUnit = m({GameTooltip = true, PlayerModel = true, Model = true}, function(self, unit) self.unit = unit end)
    mt.SetSpell = m(TIP_KINDS, function(self, spell) self.spell = spell end)
    mt.SetSpellByID = m(TIP_KINDS, function(self, spell) self.spell = spell end)
    mt.SetTalent = m(TIP_KINDS, function(self, ...) self.talent = { ... } end)
    mt.SetGlyph = m(TIP_KINDS, function(self, ...) self.glyph = { ... } end)
    mt.SetItemByID = m(TIP_KINDS, function(self, item) self.item = item end)
    mt.SetUnitBuff = m(TIP_KINDS, function(self, ...) self.unitBuff = { ... } end)
    mt.SetUnitDebuff = m(TIP_KINDS, function(self, ...) self.unitDebuff = { ... } end)
    mt.SetUnitAura = m(TIP_KINDS, function(self, ...) self.unitAura = { ... } end)
    mt.SetTrainerService = m(TIP_KINDS, function(self, index) self.trainerService = { index } end)
    mt.SetCurrencyToken = m(TIP_KINDS, function(self, ...) self.currencyToken = { ... } end)
end
register()

-- ------------------------------------------------------------------ the widget
M.metatable = {
    __index = function(self, key)
        local entry = M.methods[key]
        if not entry then return nil end  -- a name the client lacks: calling it raises, as it does there
        local kind = self._kind or self.kind
        if entry.kinds and not entry.kinds[kind] then
            error(("%s is not a 3.3.5a method on a %s"):format(key, tostring(kind)), 2)
        end
        return entry.fn
    end,
}

function M.widget(kind, name, parent, template)
    kind = kind or "Frame"
    -- _kind/_name are the mock's own bookkeeping: an addon is free to store its
    -- own .kind/.name on a frame (dc_jeweler.lua:610 detail.kind, 609 detail.name),
    -- and the client's GetName/GetObjectType are unmoved by that.
    local self = {
        _kind = kind, _name = name, kind = kind, name = name, parent = parent, template = template,
        points = {}, scripts = {}, events = {}, children = {}, shown = true,
    }
    if parent and parent.children then parent.children[#parent.children + 1] = self end
    M.frames[#M.frames + 1] = self
    -- A named frame is a client global, exactly as in the game.
    if name and M.env then M.env[name] = self end
    return setmetatable(self, M.metatable)
end

-- ------------------------------------------------------------------ AIO.SavePosition
-- AIO.SavePosition = LibWindow RegisterConfig + RestorePosition + SavePosition
-- (AIO_Client/AIO.lua:1017-1027): the first call registers an empty config, and
-- RestorePosition -- with no x/y stored -- CLEARS the frame's points and centres it
-- in its parent (LibWindow-1.1.lua:182-200), undoing the anchor the addon just set. A
-- later call RE-APPLIES the stored scale and point, which is what silently undoes a
-- drag or a scale. Modelling it lets a test count the calls (once per frame) and catch
-- a surplus save from a drag handler.
function M.SavePosition(frame)
    assert(frame and frame.kind, "AIO.SavePosition takes a frame")
    assert(frame:GetName(), "Called AIO.SavePosition on a nameless frame")
    M.savedPositions[#M.savedPositions + 1] = frame
    local stored = frame.savedPosition
    if stored then
        frame:SetScale(stored.scale)
        frame.points = copyPoints(stored.points)
        return
    end
    frame:ClearAllPoints()
    frame:SetPoint("CENTER", frame:GetParent(), "CENTER", 0, 0)
    frame.savedPosition = { scale = frame:GetScale(), points = copyPoints(frame.points) }
end

-- ------------------------------------------------------------------ drag routing
-- The client hands a drag to the frame under the cursor, not to its parent, and a
-- frame with OnDragStart=StartMoving only moves when it is movable. The old
-- strip test called the parent's handler directly and never noticed a child
-- button with no drag of its own.
-- The frame under the cursor need not be movable itself: a child button whose
-- OnDragStart moves its parent was never movable in the client either, and
-- StartMoving already refuses the frame that actually moves.
function M.dragBegin(frame)
    local node, target = frame, nil
    while node do
        if node.scripts and node.scripts.OnDragStart then target = node break end
        node = node.parent
    end
    assert(target, (frame.name or "the frame") .. " and no parent have an OnDragStart script")
    assert(target == frame,
        ("the drag lands on %s, the frame under the cursor, not on its parent %s")
            :format(frame.name or "the frame", target.name or "?"))
    target.scripts.OnDragStart(target)
end

-- ------------------------------------------------------------------ install
function M.setScreen(width, height)
    M.screenWidth, M.screenHeight = width, height
    if M.UIParent then
        M.UIParent._rect = { 0, 0, width, height }
    end
    if M.env then
        M.env.GetScreenWidth = function() return width end
        M.env.GetScreenHeight = function() return height end
    end
end

function M.install(env)
    env = env or _G
    M.env = env
    env.CreateFrame = function(kind, name, parent, template) return M.widget(kind, name, parent, template) end
    env.UIParent = M.widget("Frame", "UIParent")
    env.WorldFrame = M.widget("Frame", "WorldFrame")
    env.WatchFrame = M.widget("Frame", "WatchFrame")
    env.GameTooltip = M.widget("GameTooltip", "GameTooltip")
    env.UIErrorsFrame = M.widget("MessageFrame", "UIErrorsFrame")
    env.UISpecialFrames = {}
    env.SlashCmdList = env.SlashCmdList or {}
    env.StaticPopupDialogs = env.StaticPopupDialogs or {}
    env.tinsert = table.insert
    env.hooksecurefunc = function(a, b, c)
        -- Both 3.3.5a forms: hooksecurefunc("Global", hook) and
        -- hooksecurefunc(table, "method", hook).
        local target, name, hook
        if type(a) == "string" then
            target, name, hook = env, a, b
        else
            target, name, hook = a, b, c
        end
        local original = target[name]
        -- The client refuses a name that is not a function; the old jeweler and
        -- rift stubs asserted it and the migration dropped it.
        assert(type(original) == "function",
            "hooking a function that does not exist: " .. tostring(name))
        -- The global becomes the WRAPPER, and the original's results are what the
        -- caller sees (the hook's own return value is discarded): a test that only
        -- checks _G[name] ~= stock passes a plain replacement too.
        local wrapper = function(...)
            local results = pack(original(...))
            hook(...)
            return unpack(results, 1, results.n)
        end
        target[name] = wrapper
        M.hooks[name] = wrapper
    end
    M.UIParent = env.UIParent
    M.setScreen(1024, 768)
    return M
end

return M
