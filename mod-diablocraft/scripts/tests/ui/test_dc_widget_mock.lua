-- luacheck: ignore 111 112 113 121 122 431
-- test_dc_widget_mock.lua -- the shared widget mock's own rules (diablocraft-yey2).
-- Run from the repo root with `lua mod-diablocraft/scripts/tests/ui/test_dc_widget_mock.lua`.
--
-- Each rule below is the reviewer's own, and each check goes red if the rule is
-- dropped from dc_widget_mock.lua:
--   1. a method the 3.3.5a client lacks is not a no-op (SetShown, SetColorTexture);
--      a method from another widget kind does not appear either;
--   2. the client's SetTexCoord/SetPoint argument counts are refused when short;
--   3. sizes are private: SetSize leaves no .width/.height a caller can read;
--   4. GetStatusBarTexture is nil until SetStatusBarTexture ran;
--   5. a FontString refuses SetText until a font came from SetFont, SetFontObject or
--      its template, and AIO.SavePosition refuses a nameless frame;
--   6. hooksecurefunc records its wrapper in Mock.hooks and refuses to hook a name
--      that is not a function, and the wrapper returns the ORIGINAL's results;
--   7. AIO.SavePosition restores on the first call too (LibWindow centres a frame with
--      nothing stored), and a drag goes to the frame under the cursor, with
--      SetMovable(true) required on the frame that actually moves.
-- It also fails if any test_*.lua goes back to its own widget stub.

local MOCK = os.getenv("DC_WIDGET_MOCK") or "mod-diablocraft/scripts/dc_widget_mock.lua"
local Mock = dofile(MOCK)
Mock.install()

local checks = 0
local function ok(condition, message)
    checks = checks + 1
    assert(condition, message)
end

local function raises(fn, ...)
    local called, err = pcall(fn, ...)
    return called == false, err
end

-- --------------------------------------------------------------- 1. the API is the client's
for _, name in ipairs({ "SetShown", "SetColorTexture", "SetColorGradient", "BackdropTemplate",
    "SetIgnoreParentScale", "CreateLine", "SetObeyStepOnDrag" }) do
    ok(Mock.methods[name] == nil, name .. " must not be a widget method in 3.3.5a")
end

local frame = Mock.widget("Frame", "MockRuleFrame")
local missing, err = raises(function() return frame:SetShown(true) end)
ok(missing, "calling the missing SetShown must raise (got: " .. tostring(err) .. ")")
ok(tostring(err):find("SetShown"), "the error names the missing method, got " .. tostring(err))

local texture = frame:CreateTexture(nil, "ARTWORK")
ok(texture.kind == "Texture", "CreateTexture makes a Texture")
local wrongKind, kindErr = raises(function() return texture:SetText("x") end)
ok(wrongKind, "a Texture has no SetText (a client method on the wrong kind), got " .. tostring(kindErr))
-- Scale and frame level are Frame methods: a Texture or FontString has neither.
ok(raises(function() return texture:GetFrameLevel() end), "a Texture has no GetFrameLevel (a Frame method)")
ok(raises(function() return texture:SetScale(1) end), "nor SetScale")
ok(raises(function() return Mock.widget("FontString", "MockKindText"):GetEffectiveScale() end),
    "nor a FontString GetEffectiveScale")
ok(raises(function() return frame:SetToplevel(true) end) == false, "a Frame has SetToplevel")

-- A global the client lacks must not exist either.
ok(_G.C_Timer == nil, "the mock must not define the post-3.3.5a C_Timer global")

-- --------------------------------------------------------------- 2. argument counts
ok(Mock.methods.SetTexCoord ~= nil, "SetTexCoord is a Texture method")
local shortCoord = raises(function() return texture:SetTexCoord(0, 1, 0) end)
ok(shortCoord, "SetTexCoord with 3 numbers must raise (a truncated multi-return)")
ok(raises(function() return texture:SetTexCoord(0, 1, 0, 1) end) == false, "4 numbers is the client's first form")
ok(raises(function() return texture:SetTexCoord(0, 1, 0, 1, 0, 1, 0, 1) end) == false, "8 numbers is the client's second form")
ok(raises(function() return texture:SetTexCoord(1, 2, 3, 4, 5) end), "5 numbers is neither form")

ok(raises(function() return frame:SetPoint() end), "SetPoint with no point name must raise")
ok(raises(function() return frame:SetPoint(5) end), "SetPoint's first argument must be a point name")
ok(raises(function() return frame:SetPoint("TOPLEFT", nil, nil, 0, 0) end) == false,
    "a full SetPoint(point, relTo, relPoint, x, y) is allowed")
ok(raises(function() return frame:SetPoint("TOPLEFT", nil, nil, 0, 0, 0) end),
    "a sixth argument is not a SetPoint the client takes")
ok(#frame.points == 1, "SetPoint recorded the anchor; got " .. #frame.points)

-- --------------------------------------------------------------- 3. sizes are private
frame:SetSize(90, 40)
ok(frame.width == nil, "SetSize must not leave a readable .width field")
ok(frame.height == nil, "SetSize must not leave a readable .height field")
ok(frame:GetWidth() == 90 and frame:GetHeight() == 40, "GetWidth/GetHeight answer the size")
-- The bug this rule catches: addon code reading its own .height instead of GetHeight().
local function addonStyleHeight(widget) return widget.height end
ok(addonStyleHeight(frame) == nil, "addon-style .height reads nil, as on the client")

-- --------------------------------------------------------------- 4. a bar with no texture
local bar = Mock.widget("StatusBar")
ok(bar:GetStatusBarTexture() == nil, "GetStatusBarTexture is nil until SetStatusBarTexture ran")
bar:SetStatusBarColor(1, 0, 0)
ok(bar:GetStatusBarTexture() == nil, "a tint alone does not make a texture")
bar:SetStatusBarTexture("Interface\\Buttons\\WHITE8X8")
ok(bar:GetStatusBarTexture() ~= nil, "SetStatusBarTexture gives the bar a texture")

-- ------------------------------------------------- 4b. text needs a font (diablocraft-scog)
local bare = Mock.widget("FontString", "MockBareText")
local noFont, fontErr = raises(function() return bare:SetText("x") end)
ok(noFont, "a FontString with no font refuses SetText")
ok(tostring(fontErr):find("Font not set"), "the error is the client's, got " .. tostring(fontErr))
bare:SetFont("Fonts\\FRIZQT__.TTF", 12)
ok(raises(function() return bare:SetText("x") end) == false, "SetFont gives it a font")
local templated = Mock.widget("FontString", "MockTemplatedText", nil, "GameFontNormal")
ok(raises(function() return templated:SetText("y") end) == false, "so does a template font")
local objected = Mock.widget("FontString", "MockFontObjectText")
objected:SetFontObject({})
ok(raises(function() return objected:SetText("z") end) == false, "and SetFontObject")
ok(raises(function() return Mock.widget("Button"):SetText("b") end) == false,
    "a Button carries its own font, so its SetText needs no SetFont")

-- One NumLines registration, two kinds: a second registration under this name used to
-- replace the first for EVERY kind, so a FontString always answered 0.
local overlay = Mock.widget("FontString", "MockOverlayText", nil, "GameFontNormal")
overlay:SetSize(70, 17)
overlay:SetText("1234567890 1234567890")
ok(overlay:NumLines() >= 2, "a text widget counts the lines its string wraps to")
local tip = Mock.widget("GameTooltip", "MockTooltip")
tip:AddLine("a"); tip:AddLine("b")
ok(tip:NumLines() == 2, "and a tooltip counts its own lines")

-- --------------------------------------------------------------- 4c. hooks are recorded
local stock = function() return "stock" end
_G.MockHookedGlobal = stock
_G.hooksecurefunc("MockHookedGlobal", function() return "hook" end)
ok(_G.MockHookedGlobal == Mock.hooks.MockHookedGlobal,
    "hooksecurefunc records the wrapper it installed in Mock.hooks")
ok(_G.MockHookedGlobal ~= stock, "and the global is the wrapper, not the stock function")
ok(_G.MockHookedGlobal() == "stock", "the caller sees the ORIGINAL's results, not the hook's")
local owner = {Hooked = stock}
_G.hooksecurefunc(owner, "Hooked", function() end)
ok(owner.Hooked == Mock.hooks.Hooked, "the hooksecurefunc(table, \"field\", hook) form is recorded too")
ok(raises(function() return _G.hooksecurefunc("MockNoSuchGlobal", function() end) end),
    "hooking a name that is not a function must raise, as it does in the client")
ok(raises(function() return _G.hooksecurefunc(owner, "NoSuchField", function() end) end),
    "the table form refuses a missing field too")

-- --------------------------------------------------------------- 5. SavePosition and drags
local nameless = Mock.widget("Frame")
ok(raises(function() return Mock.SavePosition(nameless) end),
    "a nameless frame is refused, as AIO.SavePosition refuses it")
local strip = Mock.widget("Frame", "MockStrip")
strip:SetMovable(true)
strip:SetPoint("TOPRIGHT", nil, "TOPRIGHT", -220, -40)
strip:SetScale(1)
Mock.SavePosition(strip)
ok(#Mock.savedPositions == 1, "the first SavePosition registers the frame")
ok(strip.savedPosition ~= nil, "and stores its place")
ok(strip.points[1] and strip.points[1][1] == "CENTER" and strip.points[1][3] == "CENTER"
    and strip.points[1][4] == 0 and strip.points[1][5] == 0,
    "the first call restores too: LibWindow centres a frame with nothing stored, undoing the anchor")
strip:SetScale(0.5)
Mock.SavePosition(strip)
ok(#Mock.savedPositions == 2, "a second SavePosition is recorded (once per frame is the rule)")
ok(strip:GetScale() == 1, "and re-applies the stored scale, undoing the player's 0.5")

-- The frame under the cursor takes the drag; it need not be movable itself when its
-- handler moves a movable parent -- StartMoving checks the frame that actually moves.
local child = Mock.widget("Button", "MockChild", strip)
local function stripDrag() strip:StartMoving() end
child:SetScript("OnDragStart", stripDrag)
Mock.dragBegin(child)
ok(strip.moving == true, "the child's own drag moves the strip through the same handler")

local parentDragOnly = Mock.widget("Frame", "MockParentDrag")
local noOwnDrag = Mock.widget("Button", "MockOwnless", parentDragOnly)
local routed = raises(function() return Mock.dragBegin(noOwnDrag) end)
ok(routed, "a drag on a child with no OnDragStart of its own must raise, not reach the parent")

local notMovable = Mock.widget("Frame", "MockStuck")
notMovable:SetScript("OnDragStart", notMovable.StartMoving)
ok(raises(function() return Mock.dragBegin(notMovable) end),
    "OnDragStart=StartMoving on a frame that is not SetMovable(true) must raise")

-- --------------------------------------------------------------- the tests share this mock
-- A test that goes back to its own loose CreateFrame stub would hide all of the
-- above again. Any test_*.lua that DEFINES a CreateFrame must also load this mock
-- (a test may still wrap the mock's, to count frames it creates).
local function offenders(pattern, alsoLacking)
    local cmd = "grep -lE '" .. pattern .. "' mod-diablocraft/scripts/test_*.lua 2>/dev/null"
    if alsoLacking then
        cmd = cmd .. " | xargs -r grep -L '" .. alsoLacking .. "' 2>/dev/null"
    end
    local out = {}
    local p = io.popen(cmd)
    for file in p:lines() do
        if not file:find("test_dc_widget_mock.lua", 1, true) then out[#out + 1] = file end
    end
    p:close()
    return out
end

local ownStub = offenders("function[[:space:]]+CreateFrame|CreateFrame[[:space:]]*=[[:space:]]*function|_G\\.CreateFrame[[:space:]]*=", "dc_widget_mock")
ok(#ownStub == 0,
    "these tests define their own CreateFrame instead of using the shared mock: " .. table.concat(ownStub, ", "))
local looseFallback = offenders('match\\("\\^%u"\\)|ABSENT_METHODS')
ok(#looseFallback == 0,
    "these tests still answer unknown widget calls with a no-op: " .. table.concat(looseFallback, ", "))

print(("widget mock checks passed (%d)"):format(checks))
