-- luacheck: globals DCThrottle
local AIO = AIO or require("AIO")
local CHANNEL = "DiablocraftParagon"
if AIO.AddAddon() then
    local handlers = AIO.AddHandlers(CHANNEL, {})
    local keys = {primary=true,vitality=true,movement=true,resource=true,ias=true,cdr=true,chc=true,chd=true,
        armor=true,life=true,resistance=true,regen=true,area=true,rcr=true,loh=true,pickup=true}
    local function allowed(player)
        if player:IsInCombat() then
            AIO.Handle(player,CHANNEL,"Error","Paragon cannot be opened or changed in combat.")
            return false
        end
        return true
    end
    -- class_map.csv's primary_stat for this player's class: the name the window's
    -- "primary" row takes (the Primary stat row names the class's stat;
    -- dc_paragon.cpp applies that same stat). Empty when the class has no
    -- dc_class_map row or no stat, so the client keeps the server's generic name
    -- then. No class is named here: one query keyed by the player's own WoW class,
    -- so a later class is data only.
    local function primaryStat(player)
        local row = WorldDBQuery(
            "SELECT primary_stat FROM dc_class_map WHERE wow_class_id = " .. player:GetClass())
        if not row then return "" end
        return row:GetString(0) or ""
    end
    -- Security G1: Open and Refresh run a C++ snapshot and read dc_class_map; drop a
    -- flood. Change and Respec need no bucket here: their commands keep their own
    -- per-player gaps in C++ (dc_paragon.cpp EditGapOpen, RespecGate).
    function handlers.Open(player)
        if DCThrottle.Allow(player, "paragon:open", 5, 10) and allowed(player) then
            player:RunCommand("dc paragon open")
            AIO.Handle(player,CHANNEL,"PrimaryStat",primaryStat(player))
        end
    end
    -- Refreshes the screen snapshot without opening it.
    function handlers.Refresh(player)
        if not DCThrottle.Allow(player, "paragon:refresh", 5, 10) then return end
        player:RunCommand("dc paragon sync")
        AIO.Handle(player,CHANNEL,"PrimaryStat",primaryStat(player))
    end
    function handlers.Change(player,key,amount,allocate)
        if not allowed(player) then return end
        -- constant: the three contract-defined bulk steps.
        if type(key)~="string" or not keys[key] or (amount~=1 and amount~=10 and amount~=100) or type(allocate)~="boolean" then
            AIO.Handle(player,CHANNEL,"Error","Invalid allocation request; choose a stat and 1, 10, or 100 points.");return
        end
        -- C++ revalidates all combat, ownership, budget, cap and persistence checks.
        player:RunCommand("dc paragon "..(allocate and "allocate" or "deallocate").." "..key.." "..amount)
    end
    function handlers.Respec(player)
        if allowed(player) then player:RunCommand("dc paragon respec") end
    end
    return
end

-- luacheck: globals DCUI DCParagon
local handlers = AIO.AddHandlers(CHANNEL, {})
-- The shared window look (dc_aio_ui.lua, whose name sorts first so AIO loads it before
-- this file): everything visual below is built from DCUI, so this window cannot drift from
-- the Jeweler's, the Blacksmith's or the Skills window's (12-ui: one look for every screen).
local U = DCUI or error("dc_aio_ui.lua must load before dc_paragon.lua")
local state,pending,category = nil,nil,0
local categories = {"Core","Offense","Defense","Utility"}
-- class_map.csv's primary_stat for this player, pushed by the server half. The row keyed
-- "primary" is drawn with it; the server's generic name stands when the class has none.
local primaryName
local frame = U.window("DiablocraftParagonFrame", nil, nil, "paragon")
local close = U.close(frame) -- native close: hides its parent
local title = U.title(frame,"Paragon")
local summary = U.subtitle(frame)
-- The XP bar has no counterpart in the artisans' windows. Styled from the same palette
-- through the shared bar (bronze on near-black) at the window's own footer, because it
-- reports this screen's pool XP under the summary that repeats it.
local bar = U.bar(frame)
bar:ClearAllPoints();bar:SetPoint("TOPLEFT",24,-430)
local hint = U.text(frame,24,-346,512,"GameFontHighlightSmall")
hint:SetText("Click = 1   Shift = 10   Ctrl = 100. Bulk requests are exact; over-cap requests are refused.")
U.colour(hint,U.GREY)
local say = U.say
local tabs,lines = {},{}
local draw
function handlers.Error(_,message) say(message,true) end
-- The class's own main stat, from the server half. Until it arrives (or when the class has
-- none) the row keeps the name the snapshot carried.
function handlers.PrimaryStat(_,name)
    primaryName=(type(name)=="string" and name~="") and name or nil
    if draw then draw() end
end
local function open()
    if InCombatLockdown() then say("Paragon cannot be opened or changed in combat.",true);return end
    AIO.Handle(CHANNEL,"Open")
end
local function change(line,allocate)
    if not line.row then return end
    -- constant: click/Shift/Ctrl steps.
    local amount=IsControlKeyDown() and 100 or IsShiftKeyDown() and 10 or 1
    AIO.Handle(CHANNEL,"Change",line.row.key,amount,allocate)
end
-- The text tabs (Core/Offense/Defense/Utility) have no counterpart in the artisans'
-- windows, whose tabs are icons; built from the same palette: the slot's dark ground and
-- bronze border, a grey label, and the artisans' gold on the active tab. The unspent count
-- rides the label.
local function tabButton(index,label,x,y,w)
    local b=CreateFrame("Button",nil,frame)
    b:SetSize(w,25);b:SetPoint("TOPLEFT",x,y)
    U.flat(b,U.SLOT_BG[1],U.SLOT_BG[2],U.SLOT_BG[3],U.TAB_IDLE[1],U.TAB_IDLE[2],U.TAB_IDLE[3])
    b.label=U.text(b,0,-6,w,"GameFontNormal","CENTER");b.label:SetText(label)
    b:SetScript("OnClick",function() category=index-1;draw() end)
    return b
end
for i=1,4 do
    local index=i
    tabs[i]=tabButton(i,categories[i],24+(i-1)*132,-80,124)
    -- The shared list row per stat: its font, its hover highlight and its gold selection
    -- mark, at twice its height because a Paragon row carries two lines - the stat's name,
    -- then its points and totals. (A class with no class_map.csv primary_stat keeps the
    -- server's long generic name, which needs that second line for its numbers.)
    local line={button=U.row(frame)}
    line.button:SetWidth(430);line.button:SetHeight(U.ROW_HEIGHT*2);line.button:SetPoint("TOPLEFT",24,-124-(i-1)*44)
    line.label=line.button.label;line.label:SetWidth(430);line.label:SetHeight(U.ROW_HEIGHT*2-2);line.label:SetJustifyH("LEFT")
    lines[i]=line
    local minus=U.button(frame,36,"-",function() change(lines[index],false) end);minus:SetPoint("TOPLEFT",460,-126-(i-1)*44)
    local plus=U.button(frame,36,"+",function() change(lines[index],true) end);plus:SetPoint("TOPLEFT",502,-126-(i-1)*44)
end
local respec=U.button(frame,155,"Respec (free)",function() AIO.Handle(CHANNEL,"Respec") end);respec:SetPoint("TOPLEFT",24,-308)
local refresh=U.button(frame,100,"Refresh",open);refresh:SetPoint("TOPLEFT",187,-308)
U.anchor(frame,"buttons",{respec,refresh})
draw=function()
    if not state then return end
    summary:SetText("Pool: "..state.pool.."   Level: "..state.level.."   XP: "..state.xp.." / "..state.next)
    -- Approximation is only for bar pixels; the exact 64-bit strings stay intact.
    bar:SetValue(math.min(1,(tonumber(state.xp) or 0)/(tonumber(state.next) or 1)))
    for i,b in ipairs(tabs) do
        b.label:SetText(categories[i].." ("..(state.unspent[i] or "0")..")")
        local active=(i-1)==category
        local tabColour=active and U.TAB_ACTIVE or U.TAB_IDLE
        b:SetBackdropBorderColor(tabColour[1],tabColour[2],tabColour[3],1)
        U.colour(b.label,active and U.GOLD or U.GREY)
    end
    for i,line in ipairs(lines) do
        local row=state.rows[category*4+i]
        line.row=row
        if row then
            local name=(row.key=="primary" and primaryName) or row.name
            line.label:SetText(name.."   "..row.points.." / "..(row.cap=="0" and "uncapped" or row.cap)..
                " points   +"..row.total..row.unit.."   (+"..row.perPoint..row.unit.." each)")
        else line.label:SetText("") end
    end
end
-- The frames the tests read and drive (the Jeweler's and the Blacksmith's own shape).
DCParagon={ui={frame=frame,close=close,title=title,summary=summary,bar=bar,hint=hint,
    tabs=tabs,lines=lines,respec=respec,refresh=refresh}}
local events=CreateFrame("Frame")
events:RegisterEvent("CHAT_MSG_ADDON");events:RegisterEvent("PLAYER_REGEN_DISABLED")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:SetScript("OnEvent",function(_,event,prefix,message,distribution,sender)
    if event=="PLAYER_REGEN_DISABLED" then frame:Hide();return end
    if event=="PLAYER_ENTERING_WORLD" then AIO.Handle(CHANNEL,"Refresh");return end
    -- CHAT_MSG_ADDON supplies the distribution before the sender (3.3.5a).
    if prefix~="DCPARAGON" or distribution~="WHISPER" or
        (sender~=UnitName("player") and sender~=UnitName("player").."-"..GetRealmName()) then return end
    local fields={};for field in (message.."|"):gmatch("(.-)|") do fields[#fields+1]=field end
    if fields[1]=="X" then handlers.Error(nil,fields[2]);pending=nil;return end
    if fields[1]=="H" then
        pending={pool=fields[2],level=fields[3],xp=fields[4],next=fields[5],open=fields[6]=="1",rows={},unspent={}}
    elseif pending and fields[1]=="C" then pending.unspent[tonumber(fields[2])+1]=fields[3]
    elseif pending and fields[1]=="R" then
        pending.rows[tonumber(fields[2])]={key=fields[3],name=fields[4],category=fields[5],points=fields[6],
            perPoint=fields[7],total=fields[8],cap=fields[9],unit=fields[10]}
    elseif pending and fields[1]=="E" then
        -- constant: snapshot shape, contract paragon-messages.md.
        if #pending.rows==16 and #pending.unspent==4 then
            state=pending;draw()
            if state.open and not InCombatLockdown() then frame:Show() end
        end
        pending=nil
    end
end)
-- The inventory screen's PARAGON button is in the
-- on-disk addon, which cannot see this file's locals. One published entry point
-- rather than a second copy of open(). The second "Paragon" button this file hung
-- on the stock CharacterFrame is gone.
DiablocraftOpenParagon=open
SLASH_DIABLOCRAFTPARAGON1="/dcparagon"
SlashCmdList.DIABLOCRAFTPARAGON=open
-- AIO may load this addon after PLAYER_LOGIN/PLAYER_ENTERING_WORLD have fired.
AIO.Handle(CHANNEL,"Refresh")
