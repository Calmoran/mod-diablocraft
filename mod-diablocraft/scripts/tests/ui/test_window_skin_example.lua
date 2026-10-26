-- luacheck: ignore 111 112 113 121 122 211 212 213 311 231 431 432
-- Run from repo root with `lua mod-diablocraft/scripts/tests/ui/test_window_skin_example.lua`.
--
-- The window skin slots' worked example: client-patch/skins/WindowSkinExample fills
-- `window-cube` with its own placeholder canvas (media/mycube.tga, make_placeholder.py), and the real Cube
-- window (dc_cube.lua, built as the client builds it) wears it:
--   * the canvas file is on disk, a 256 x 512 32-bit TGA, the slot's size and crop agree with it, and
--     every anchor lies inside the canvas;
--   * the Cube's generic frame is hidden and the canvas drawn around its body at the window's width
--     (300 / 214), the title, close, Transmute and recipe book centred on the skin's spots;
--   * without the skin the Cube is today's dialog.
-- What a stub cannot show is the picture in game: that is the sheet's check.
local SKIN = os.getenv("NO_SKIN") == nil
local SOURCE = "mod-diablocraft/lua/aio/dc_cube.lua"
local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local sent,handled,now,cursor={},{},100,nil
function UnitName() return "Tester" end
function GetRealmName() return "Torment" end
function GetItemIcon(entry) return "icon:"..entry end
function GetItemInfo() return nil end
function GetTime() return now end
function GetCursorInfo() return cursor end
function ClearCursor() cursor=nil end
function PickupContainerItem() end
function PickupInventoryItem() end
function SendAddonMessage(prefix,body,distribution,target)
    sent[#sent+1]={prefix=prefix,body=body,distribution=distribution,target=target}
end
local clientHandlers
AIO={AddAddon=function() return false end,AddHandlers=function(_,t) clientHandlers=t;return t end,
    Handle=function(...) handled[#handled+1]=table.concat({...},",") end}
Diablocraft={Econ={Gold=tostring,CURRENCIES={{entry=102001,name="Reusable Parts"},{entry=102002,name="Arcane Dust"},
    {entry=102003,name="Veiled Crystal"},{entry=102000,name="Death's Breath"},{entry=102004,name="Forgotten Soul"}}}}
_G.DEFAULT_CHAT_FRAME={AddMessage=function() end}
_G.require=nil
-- The Torment addon, then the example skin (its .toc depends on Torment, so it loads after), then the
-- server's kit: the order the client runs them in.
dofile("mod-diablocraft/scripts/dc_addon_core.lua")
if SKIN then dofile("client-patch/skins/WindowSkinExample/WindowSkinExample.lua") end
dofile("mod-diablocraft/lua/aio/dc_aio_ui.lua")
-- ElvUI's Auras module (ElvUI-WotLK 6.09 Modules/Auras/Auras.lua) and the stock buff row (FrameXML/BuffFrame.lua), by
-- the names and fields the file reads: UpdateHeader calls ConfigureAuras, which shows `elvShown` buttons; BuffFrame_Update
-- lays out the buffs, then anchors each debuff.
local elvShown=3
local Auras={db={buffs={growthDirection="RIGHT_UP",size=32,horizontalSpacing=6,verticalSpacing=16,wrapAfter=4}}}
Auras.BuffFrame=CreateFrame("Frame","ElvUIPlayerBuffs",UIParent)
local elvButtons={}
for i=1,5 do elvButtons[i]=CreateFrame("Button","ElvUIPlayerBuffsAuraButton"..i,Auras.BuffFrame) end
function Auras.ConfigureAuras(_,header) for i,b in ipairs(elvButtons) do b.shown=header and i<=elvShown end end
function Auras:UpdateHeader(header) self:ConfigureAuras(header,{}) end
function Auras.CreateIcon(_,b) b.texture=b:CreateTexture();b.skinned=true;b:SetScript("OnClick",function() end) end
function Auras.ClearAuraTime(_,b) b.noTime=true end
ElvUI={{GetModule=function(_,name,silent) assert(silent);return name=="Auras" and Auras or nil end}}
BuffFrame=CreateFrame("Frame","BuffFrame",UIParent);BuffFrame.numEnchants,BuffFrame.numConsolidated=0,0
ConsolidatedBuffs=CreateFrame("Button","ConsolidatedBuffs",UIParent)
TemporaryEnchantFrame=CreateFrame("Frame","TemporaryEnchantFrame",UIParent)
TempEnchant1=CreateFrame("Button","TempEnchant1",TemporaryEnchantFrame);TempEnchant1:SetSize(30,30)
BUFF_ACTUAL_DISPLAY,BUFFS_PER_ROW,BUFF_ROW_SPACING=0,8,5
local debuffs=0
local DebuffButton1=CreateFrame("Button","DebuffButton1",BuffFrame)
function BuffFrame_UpdateAllBuffAnchors() end
function DebuffButton_UpdateAnchors(_,index) if index==1 then DebuffButton1:SetPoint("TOPRIGHT",ConsolidatedBuffs,"BOTTOMRIGHT",0,-35) end end
function BuffFrame_Update()
    BuffFrame_UpdateAllBuffAnchors()
    for i=1,debuffs do DebuffButton_UpdateAnchors("DebuffButton",i) end
end
dofile(SOURCE)
local cube = _G.TormentCubeFrame
assert(cube, "the Cube window is built")
local art = Diablocraft.ART["window-cube"]
if not SKIN then
    assert(cube.backdrop and cube.dcCanvas == nil, "no skin: the Cube is today's dialog")
    print("test_window_skin_example: no skin, no canvas")
    return
end

-- The file and the slot agree.
local file = assert(io.open("client-patch/skins/WindowSkinExample/media/mycube.tga", "rb"), "the canvas is on disk")
local header = file:read(18); file:close()
local function u16(at) return header:byte(at) + 256 * header:byte(at + 1) end
assert(header:byte(3) == 2 and u16(13) == 256 and u16(15) == 512 and header:byte(17) == 32,
    "an uncompressed 32-bit TGA, 256 x 512")
assert(art.path == "Interface\\AddOns\\WindowSkinExample\\media\\mycube", "the slot names the file")
assert(art.width == 256 and art.height == 400 and art.coords[2] == 1 and art.coords[4] == 400 / 512,
    "the canvas is the file's top 256 x 400, cropped by coords")
local function inside(rect, label)
    assert(rect.left >= 0 and rect.top >= 0 and rect.left + rect.width <= art.width and rect.top + rect.height <= art.height,
        label .. " lies inside the canvas")
end
inside(art.anchors.content, "content"); inside(art.anchors.title, "the title"); inside(art.anchors.close, "the close")
for i, rect in ipairs(art.anchors.buttons) do inside(rect, "button " .. i) end

-- The Cube wears it.
local scale = 300 / 214
local function near(a, b, label) assert(math.abs(a - b) < 1e-6, label .. ": " .. tostring(a) .. ", want " .. tostring(b)) end
assert(cube.backdrop == nil, "the generic frame is hidden")
local canvas = cube.dcCanvas
assert(canvas and canvas.texture == art.path, "the canvas is drawn")
local p = canvas.points[1]
assert(p[1] == "TOPLEFT" and p[2] == cube, "anchored on the Cube")
near(p[4], -21 * scale, "content left"); near(p[5], 36 * scale, "content top")
near(canvas:GetWidth(), 256 * scale, "canvas width"); near(canvas:GetHeight(), 400 * scale, "canvas height")
local placed = {}
for _, w in ipairs(Mock.frames) do
    local q = w.points and w.points[1]
    if q and q[2] == canvas then placed[#placed + 1] = w end
end
local function at(rect)
    for _, w in ipairs(placed) do
        local q = w.points[1]
        if math.abs(q[4] - (rect.left + rect.width / 2) * scale) < 1e-6 and math.abs(q[5] + (rect.top + rect.height / 2) * scale) < 1e-6 then return w end
    end
end
local title, close = at(art.anchors.title), at(art.anchors.close)
assert(title and title.kind == "FontString" and title.text == "Kanai's Cube", "the Cube's title on the title spot")
assert(close and close.template == "UIPanelCloseButton", "its close button on the close spot")
local go, book = at(art.anchors.buttons[1]), at(art.anchors.buttons[2])
assert(go and go.template == "UIPanelButtonTemplate", "Transmute on the first button spot")
near(go:GetWidth(), 100 * scale, "at the spot's width")
assert(book and book.icon and book.icon.texture == "Interface\\Icons\\INV_Misc_Book_09", "the recipe book on the second")
assert(#placed == 4, "nothing else is moved: the Cube's body stays as it is, got " .. #placed)
print("test_window_skin_example: the Cube wears the example skin's canvas, its parts on their spots")
