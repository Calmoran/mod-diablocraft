-- luacheck: globals DCUI UIErrorsFrame DEFAULT_CHAT_FRAME
-- One definition of the Torment window look, shared by every server-pushed window
-- (dc_jeweler.lua, dc_blacksmith.lua, ...). AIO sends addons in the order the server
-- loads them, and this file's name sorts before its callers (dc_aio_ui <
-- dc_blacksmith < dc_jeweler), so a caller can take the builders below for granted.
--
-- The Blacksmith once drew the Jeweler's
-- look by hand and drifted (an uncoloured flat backdrop draws white in 3.3.5). Every
-- window now builds its flat panels, slots, tabs, rows, boxes, inputs, buttons and
-- cast bar here instead, so they cannot drift apart again.
--
-- The look itself is still the Torment addon's Diablocraft.Style when the client has
-- it (that addon ships through the launcher while this file comes from the server, so
-- either can be newer than the other): every builder resolves it on the call, never
-- once at load, so a newer addon reaches a window built afterwards.
local AIO=AIO or require("AIO")
if AIO.AddAddon() then return end

DCUI={}
local U=DCUI

local EDGE="Interface\\Buttons\\WHITE8X8"
U.EDGE=EDGE
local PANEL={bgFile="Interface\\DialogFrame\\UI-DialogBox-Background",edgeFile="Interface\\DialogFrame\\UI-DialogBox-Border",
    tile=true,tileSize=32,edgeSize=32,insets={left=11,right=12,top=12,bottom=11}}
local FLAT={bgFile=EDGE,edgeFile=EDGE,edgeSize=1,insets={left=1,right=1,top=1,bottom=1}}
U.PANEL,U.FLAT=PANEL,FLAT

-- The palette (the Jeweler's): no window keeps a second copy of these.
local GOLD,WHITE,GREY,RED={1,.82,0},{1,1,1},{.62,.62,.62},{1,.19,.19}
U.GOLD,U.WHITE,U.GREY,U.RED=GOLD,WHITE,GREY,RED
U.QUESTION="Interface\\Icons\\INV_Misc_QuestionMark"
local function shared() return Diablocraft and Diablocraft.Style end
-- The window parts' colours: read on every use through
-- the Torment addon's Diablocraft.Style.Colour, which takes them from the parts' slots, so a
-- skin's recolour reaches every window, callers' own U.SLOT_BG reads included; these are the
-- defaults, and what an addon from before the slots draws.
local PALETTE={TAB_ACTIVE={.89,.71,.35},TAB_IDLE={.43,.36,.26},SLOT_BG={.06,.05,.04},SLOT_BORDER={.43,.36,.26},
    DETAIL_BG={0,0,0},DETAIL_BORDER={.3,.24,.14},BOX_BORDER={.42,.32,.2},
    -- The view box's edge while it holds an item (the Jeweler's Unsocket view).
    BOX_ACTIVE={.78,.6,.27},
    ROW_SELECT={1,.82,0,.28},ROW_HILITE={1,1,1,.08},BAR_BG={.06,.05,.04},BAR_FILL={.78,.6,.27},BAR_BORDER={.78,.6,.27}}
U.PALETTE=PALETTE
setmetatable(U,{__index=function(_,key)
    local default=PALETTE[key]
    if not default then return nil end
    local s=shared()
    return (s and s.Colour and s.Colour(key)) or default
end})
-- A skin-aware helper of the addon's Style (Face, Art, Input, Scroll, Title), or nil from an
-- addon without the slots: every builder below then draws exactly what it drew before them.
local function style(name) local s=shared();return s and s[name] end

-- Whole windows: a window made with a slot key (U.window's 4th argument,
-- "cube" for the `window-cube` slot) declares its parts as the kit makes them (the title, the
-- close button, each tab) and its buttons through U.anchor; the frame itself is its content.
-- Each declaration hands the window to the addon's Style.Window, which draws a skin's canvas
-- and puts the parts on its anchors, and draws nothing with no skin. Kept here, not on the
-- frame, so a window without a skin is the same frame it was.
local windows=setmetatable({},{__mode="k"})
local function declare(frame,part,region)
    local w=windows[frame]
    if not w then return end
    if part=="tabs" or part=="buttons" then
        w.parts[part]=w.parts[part] or {}
        table.insert(w.parts[part],region)
    else w.parts[part]=region end
    local window=style("Window");if window then window(frame,w.key,w.parts) end
end
-- A window's buttons (or tabs the kit did not make), in the order the skin's anchors list them.
function U.anchor(frame,part,regions)
    for _,region in ipairs(regions) do declare(frame,part,region) end
end
-- List rows: one height, one font, two indents (a category header, its items).
U.ROW_HEIGHT=18
U.ROW_INDENT=22
U.HEAD_INDENT=4
U.HEAD_STEP=20

-- The window look, member by member, so an addon from before the helper - or one that
-- carries only part of it - still draws the right window.
local function closeButton(parent)
    local b=CreateFrame("Button",nil,parent,"UIPanelCloseButton")
    b:SetPoint("TOPRIGHT",parent,"TOPRIGHT",-6,-6)
    return b
end
local function nativeButton(parent,width,label,fn)
    local b=CreateFrame("Button",nil,parent,"UIPanelButtonTemplate")
    b:SetSize(width,22);b:SetText(label);b:SetScript("OnClick",fn)
    return b
end
function U.resolve()
    local s=shared()
    local skinned=s and s.Backdrop
    return {backdrop=(skinned and skinned("window-panel")) or (s and s.backdrop) or PANEL,
        flat=(skinned and skinned("window-flat")) or (s and s.flat) or FLAT,
        Close=(s and s.Close) or closeButton, Button=(s and s.Button) or nativeButton}
end

-- The window backdrop, and the flat panel: background, alpha and border in one call,
-- so no panel can be drawn with a backdrop and no colour (the white-box bug).
function U.backdrop(frame)
    local panel=style("Panel")
    if panel then return panel(frame) end
    frame:SetBackdrop(U.resolve().backdrop)
end
function U.flat(frame,r,g,b,br,bg,bb)
    frame:SetBackdrop(U.resolve().flat)
    frame:SetBackdropColor(r,g,b,.85)
    frame:SetBackdropBorderColor(br,bg,bb,1)
end
function U.close(parent)
    local b=U.resolve().Close(parent)
    declare(parent,"close",b)
    return b
end
function U.button(parent,width,label,fn) return U.resolve().Button(parent,width,label,fn) end

function U.text(parent,x,y,width,font,justify)
    local t=parent:CreateFontString(nil,"OVERLAY",font or "GameFontHighlight")
    t:SetPoint("TOPLEFT",x,y)
    if width then t:SetWidth(width) end
    t:SetJustifyH(justify or "LEFT")
    return t
end
function U.colour(fontstring,rgb) fontstring:SetTextColor(rgb[1],rgb[2],rgb[3]) end
-- 12-ui U4: a number through the Torment addon's one shared
-- formatter, grouped in threes. The local grouping only runs if the addon is missing.
function U.number(value)
    if Diablocraft and Diablocraft.Econ then return Diablocraft.Econ.Gold(value) end
    local out,more=tostring(value or "0"),1
    while more>0 do out,more=out:gsub("^(%-?%d+)(%d%d%d)","%1,%2") end
    return out
end

function U.iconOf(entry) return entry and GetItemIcon and GetItemIcon(entry) or U.QUESTION end

-- A square slot: dark ground, thin bronze border and an icon. Tabs and material lines
-- are built from it; a count line, when one is wanted, is the caller's.
function U.slot(parent,size)
    local b=CreateFrame("Button",nil,parent)
    b:SetSize(size,size);U.flat(b,U.SLOT_BG[1],U.SLOT_BG[2],U.SLOT_BG[3],U.SLOT_BORDER[1],U.SLOT_BORDER[2],U.SLOT_BORDER[3])
    b.icon=b:CreateTexture(nil,"ARTWORK");b.icon:SetPoint("TOPLEFT",2,-2);b.icon:SetPoint("BOTTOMRIGHT",-2,2)
    local face=style("Face");if face then face(b,"slot") end
    return b
end
-- An icon tab: a slot with the idle bronze border.
function U.tab(parent,size)
    local b=U.slot(parent,size)
    b:SetBackdropBorderColor(U.TAB_IDLE[1],U.TAB_IDLE[2],U.TAB_IDLE[3],1)
    local face=style("Face");if face then face(b,"tab") end
    declare(parent,"tabs",b)
    return b
end
function U.tabActive(b,active)
    local c=active and U.TAB_ACTIVE or U.TAB_IDLE
    b:SetBackdropBorderColor(c[1],c[2],c[3],1)
    local face=style("Face");if face then face(b,active and "tab-active" or "tab") end
end

-- A list row: one height and font, the selection mark and the hover highlight. The
-- caller sets the width and re-points the label to an indent.
function U.row(parent)
    local b=CreateFrame("Button",nil,parent)
    b:SetHeight(U.ROW_HEIGHT)
    b.label=b:CreateFontString(nil,"OVERLAY","GameFontNormal");b.label:SetPoint("LEFT",0,0);b.label:SetJustifyH("LEFT")
    local art=style("Art")
    b.mark=b:CreateTexture(nil,"BACKGROUND");b.mark:SetAllPoints()
    if not (art and art(b.mark,"row-select")) then
        b.mark:SetTexture(EDGE);b.mark:SetVertexColor(U.ROW_SELECT[1],U.ROW_SELECT[2],U.ROW_SELECT[3],U.ROW_SELECT[4])
    end
    b.mark:Hide()
    b:SetHighlightTexture(EDGE)
    local hl=b:GetHighlightTexture()
    if hl and not (art and art(hl,"row-hilite")) then hl:SetVertexColor(U.ROW_HILITE[1],U.ROW_HILITE[2],U.ROW_HILITE[3],U.ROW_HILITE[4]) end
    return b
end

-- An input box: the stock InputBoxTemplate (its own border), so no flat backdrop is
-- ever left uncoloured. The caller sets size, point and any limits.
function U.input(parent,name)
    local box=CreateFrame("EditBox",name,parent,"InputBoxTemplate")
    box:SetAutoFocus(false)
    local input=style("Input");if input then input(box) end
    return box
end

-- A UIPanelScrollFrameTemplate scroll frame the caller made (named, as the template needs): its
-- thumb and track from the skin's scroll slots. Returns the frame.
function U.scroll(scroll)
    local skin=style("Scroll");if skin then skin(scroll) end
    return scroll
end

function U.tooltip(owner,fill)
    GameTooltip:SetOwner(owner,"ANCHOR_RIGHT");fill(GameTooltip);GameTooltip:Show()
end

-- A material line: a 40 px slot at (x,y), the material's name on the first line to the
-- right and its "have / need" count on a second line under the name.
-- The count hangs off the slot so hiding the line hides it too, but it is placed to the right
-- of the 40 px icon (x=48) so nothing is ever drawn over the icon and a large stock cannot
-- spill into the next column. `width` bounds the name and the count.
function U.material(parent,x,y,width)
    local r=U.slot(parent,40)
    r:SetPoint("TOPLEFT",x,y)
    r.label=U.text(parent,x+48,y-10,width or 196,"GameFontHighlight")
    r.label:SetHeight(16)
    r.count=U.text(r,48,-26,width or 196,"NumberFontNormal")
    return r
end

-- A material line's count, the one way every window draws it:
-- "have / need" in full, gold when the stock covers it and red when short,
-- the name in white either way. `enough` is the caller's exact comparison (its Logic
-- compares decimal strings), never worked out here from the formatted text.
function U.count(line,have,need,enough)
    line.count:SetText(U.number(have).." / "..U.number(need))
    U.colour(line.count,enough and GOLD or RED)
    if line.label then U.colour(line.label,WHITE) end
end

-- The body box a window's non-list view is framed with (the Jeweler's Unsocket view).
function U.box(parent,height)
    local box=CreateFrame("Button",nil,parent)
    box:SetPoint("TOPLEFT",0,0);box:SetPoint("TOPRIGHT",0,0);box:SetHeight(height or 96)
    U.flat(box,U.DETAIL_BG[1],U.DETAIL_BG[2],U.DETAIL_BG[3],U.BOX_BORDER[1],U.BOX_BORDER[2],U.BOX_BORDER[3])
    local face=style("Face");if face then face(box,"box") end
    return box
end
-- The box's edge while it holds something (the Jeweler's Unsocket view), or back to idle.
function U.boxActive(box,active)
    local c=active and U.BOX_ACTIVE or U.BOX_BORDER
    box:SetBackdropBorderColor(c[1],c[2],c[3],1)
    local face=style("Face");if face then face(box,active and "box-active" or "box") end
end

-- The cast bar: flat bronze on near-black, at the Jeweler's position and size, with an
-- opaque background, a growing fill and a centred label. `bar:SetValue(progress)`.
function U.bar(parent)
    local bar=CreateFrame("Frame",nil,parent)
    bar:SetSize(512,24);bar:SetPoint("TOPLEFT",0,-436)
    U.flat(bar,U.BAR_BG[1],U.BAR_BG[2],U.BAR_BG[3],U.BAR_BORDER[1],U.BAR_BORDER[2],U.BAR_BORDER[3])
    bar:SetFrameLevel(parent:GetFrameLevel()+10)
    local art=style("Art")
    bar.bg=bar:CreateTexture(nil,"BACKGROUND");bar.bg:SetAllPoints()
    if not (art and art(bar.bg,"bar-bg")) then bar.bg:SetTexture(EDGE);bar.bg:SetVertexColor(U.BAR_BG[1],U.BAR_BG[2],U.BAR_BG[3],1) end
    bar.fill=bar:CreateTexture(nil,"ARTWORK");bar.fill:SetPoint("TOPLEFT",2,-2);bar.fill:SetPoint("BOTTOMLEFT",2,2)
    if not (art and art(bar.fill,"bar-fill")) then bar.fill:SetTexture(EDGE);bar.fill:SetVertexColor(U.BAR_FILL[1],U.BAR_FILL[2],U.BAR_FILL[3],1) end
    bar.fill:SetWidth(1)
    bar.text=bar:CreateFontString(nil,"OVERLAY","GameFontHighlightSmall");bar.text:SetPoint("CENTER",0,0)
    bar:Hide()
    function bar:SetValue(progress)
        self.progress=progress
        self.fill:SetWidth(math.max(1,(self:GetWidth()-4)*(progress or 0)))
    end
    return bar
end

-- The window frame every Torment screen shares: 560x560 unless a smaller one is asked
-- for (the Jeweler's Sockets window), centred a little left, the dialog backdrop,
-- draggable, closed by Esc, with its large gold title and grey subtitle at the top.
function U.window(name,width,height,skin)
    local frame=CreateFrame("Frame",name,UIParent)
    frame.dcWidth=width or 560
    frame:SetSize(frame.dcWidth,height or 560);frame:SetPoint("CENTER",-30,0);frame:Hide()
    frame:SetMovable(true);frame:EnableMouse(true)
    U.backdrop(frame);frame:SetFrameStrata("HIGH")
    frame:RegisterForDrag("LeftButton");frame:SetScript("OnDragStart",frame.StartMoving);frame:SetScript("OnDragStop",frame.StopMovingOrSizing)
    table.insert(UISpecialFrames,name)
    if skin then
        windows[frame]={key=skin,parts={}}
        local window=style("Window");if window then window(frame,skin,windows[frame].parts) end
    end
    return frame
end
function U.title(frame,label)
    local t=U.text(frame,0,-18,frame.dcWidth or 560,"GameFontNormalLarge","CENTER")
    t:SetText(label)
    local skin=style("Title");if skin then skin(frame,t) end
    declare(frame,"title",t)
    return t
end
function U.subtitle(frame,label)
    local s=U.text(frame,0,-42,frame.dcWidth or 560,"GameFontHighlightSmall","CENTER")
    U.colour(s,U.GREY)
    if label then s:SetText(label) end
    return s
end

-- A message, the way both windows now show one: the red error line and, for a refusal,
-- the chat frame as well (the red line fades and ElvUI can move it).
function U.say(text,isError)
    if isError then
        UIErrorsFrame:AddMessage(text,1,0.3,0.3)
        if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage(text,1,0.3,0.3) end
    else UIErrorsFrame:AddMessage(text,1,0.82,0) end
end
