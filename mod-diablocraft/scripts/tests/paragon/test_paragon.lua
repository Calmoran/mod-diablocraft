-- luacheck: ignore 111 112 113 121 122 241 431
-- Real server handlers: malformed intents cannot reach RunCommand.
local handlers,commands,errors,pushed,queries={}, {},{},{},{}
-- class_map.csv's primary_stat, answered by wow_class_id exactly as the module's own
-- query asks: Barbarian (WoW warrior 1) -> Strength, Wizard (mage 8) -> Intelligence,
-- and nil for an unmapped class. No class is named in the module, so neither is one here.
local classStats={[1]="Strength",[8]="Intelligence"}
function WorldDBQuery(sql)
    queries[#queries+1]=sql
    local stat=classStats[tonumber(sql:match("wow_class_id = (%d+)"))]
    if stat then return {GetString=function()return stat end} end
    return nil
end
AIO={AddAddon=function()return true end,AddHandlers=function(_,h)handlers=h;return h end,
    Handle=function(_,_,name,payload)
        if name=="Error" then errors[#errors+1]=payload else pushed[#pushed+1]={name=name,payload=payload} end
    end}
-- A bucket that always admits; the bucket itself is test_handler_throttles.lua's.
DCThrottle = DCThrottle or {Allow = function() return true end} -- luacheck: ignore
dofile('mod-diablocraft/lua/aio/dc_paragon.lua')
local combat=false
local wowClass=1
local player={IsInCombat=function()return combat end,RunCommand=function(_,s)commands[#commands+1]=s end,
    GetClass=function()return wowClass end}
handlers.Open(player);assert(commands[1]=='dc paragon open')
-- Open names the window's Primary stat row from class_map.csv's primary_stat of the
-- player's own class, read through one query keyed by wow_class_id (never a class in code).
assert(pushed[1] and pushed[1].name=='PrimaryStat' and pushed[1].payload=='Strength','Open pushes the class stat')
assert(queries[1]=='SELECT primary_stat FROM dc_class_map WHERE wow_class_id = 1','the class-stat query reads dc_class_map.primary_stat by the player class, got: '..tostring(queries[1]))
handlers.Change(player,'chc',10,true);assert(commands[2]=='dc paragon allocate chc 10')
handlers.Change(player,'chc',1,false);assert(commands[3]=='dc paragon deallocate chc 1')
handlers.Change(player,'primary',100,true);assert(commands[4]=='dc paragon allocate primary 100')
handlers.Respec(player);assert(commands[5]=='dc paragon respec')
for _,v in ipairs({-1,0,1.5,50,101,math.huge,'10'}) do handlers.Change(player,'chc',v,true) end
handlers.Change(player,'chc; dc paragon xp 999',1,true)
handlers.Change(player,'chc',1,'true')
assert(#commands==5)
combat=true;handlers.Open(player);handlers.Change(player,'chc',10,true);handlers.Respec(player)
assert(#commands==5 and #errors==12)
handlers.Refresh(player);assert(#commands==6 and commands[6]=='dc paragon sync')
wowClass=8;handlers.Refresh(player);assert(pushed[#pushed].payload=='Intelligence','the Wizard names Intelligence')
wowClass=3;handlers.Refresh(player);assert(pushed[#pushed].payload=='','a class with no primary_stat pushes no name')
print('PASS: Paragon AIO Open/Change/Respec, exact bulk values, injection/type rejection, combat rejection.')
print('PASS: the Primary stat row name comes from dc_class_map.primary_stat by the player class; no row pushes no name.')

-- Real client handler: exact 64-bit XP text, atomic snapshots, combat hide,
-- self-message filtering, and modifier-key allocation intents. It must not
-- replace the stock XP bar or own a key binding.
local requests,handlersByChannel={},{}

----------------------------------------------------------------------------------------------------
-- The 3.3.5a widget layer is ONE shared strict mock (diablocraft-yey2): unknown
-- methods, wrong argument counts, a public size field and a texture-less bar all
-- fail here as they do in the game. The doubles below the mock are this test's own
-- client globals.
----------------------------------------------------------------------------------------------------
local Mock = dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
local frames = Mock.frames
Mock.setScreen(1024, 768)
-- Client globals the mock does not own.
CharacterFrame = {}
DEFAULT_CHAT_FRAME = {AddMessage=function()end}
local clientCombat,shift,ctrl=false,false,false
function InCombatLockdown()return clientCombat end
function IsShiftKeyDown()return shift end
function IsControlKeyDown()return ctrl end
function UnitName()return 'Tester'end
function GetRealmName()return 'Nightly'end
AIO={AddAddon=function()return false end,AddHandlers=function(channel,h)handlersByChannel[channel]=h;return h end,
    Handle=function(...)requests[#requests+1]={...}end}
-- The shared look module, loaded the way AIO does (its name sorts first); the window
-- under test is built from it, so it must be present.
dofile('mod-diablocraft/lua/aio/dc_aio_ui.lua')
assert(DCUI,'dc_aio_ui.lua defines the shared look')
dofile('mod-diablocraft/lua/aio/dc_paragon.lua')
-- UI fixes row 10 (ruling 2026-10-03): no second "Paragon" button on the stock CharacterFrame;
-- the sheet header's PARAGON button, N and /dcparagon open it, through the one published opener.
for _,made in ipairs(frames)do assert(made.parent~=CharacterFrame,'nothing is built on the stock CharacterFrame')end
assert(type(DiablocraftOpenParagon)=='function' and SlashCmdList.DIABLOCRAFTPARAGON==DiablocraftOpenParagon,
    'the published opener stays')
local receiver;for _,f in ipairs(frames)do if f.events.CHAT_MSG_ADDON then receiver=f end end
assert(receiver)
-- WoW passes the distribution (WHISPER) before the sender, just as AIO's
-- installed ONADDONMSG handler expects. Do not omit it from simulated events.
local function send(message,sender,distribution)
    receiver.scripts.OnEvent(receiver,'CHAT_MSG_ADDON','DCPARAGON',message,distribution or 'WHISPER',sender or 'Tester')
end
local f=DiablocraftParagonFrame
assert(DiablocraftParagonXPBar==nil and DiablocraftParagonOpenButton==nil)
assert(requests[#requests][2]=='Refresh')
SlashCmdList.DIABLOCRAFTPARAGON();assert(requests[#requests][2]=='Open')
send('H|normal|800|9007199254740993|9007199254740994|1','Other');send('E');assert(not f.shown)
send('H|normal|800|9007199254740993|9007199254740994|1','Tester','PARTY');send('E');assert(not f.shown)
send('H|normal|800|9007199254740993|9007199254740994|1')
for i=0,3 do send('C|'..i..'|200')end
for i=1,16 do send('R|'..i..'|chc|Critical Hit Chance|'..math.floor((i-1)/4)..'|50|0.2|10|50|%')end
assert(not f.shown);send('E');assert(f.shown)
local exact=false
for _,t in ipairs(frames)do if t.kind=='FontString' and t.text and t.text:find('9007199254740993 / 9007199254740994',1,true)then exact=true end end
assert(exact)
local plus;for _,b in ipairs(frames)do if b.text=='+' then plus=b;break end end
shift=true;plus.scripts.OnClick();assert(requests[#requests][4]==10 and requests[#requests][5]==true)
ctrl=true;plus.scripts.OnClick();assert(requests[#requests][4]==100)
clientCombat=true;receiver.scripts.OnEvent(receiver,'PLAYER_REGEN_DISABLED');assert(not f.shown)
local before=#requests;SlashCmdList.DIABLOCRAFTPARAGON();assert(#requests==before)
send('H|normal|202|1224000|326400000|0','Tester-Nightly')
for i=0,3 do send('C|'..i..'|50')end
for i=1,16 do send('R|'..i..'|chc|Critical Hit Chance|0|0|0.2|0|50|%')end
send('E')
assert(not f.shown)
receiver.scripts.OnEvent(receiver,'PLAYER_ENTERING_WORLD')
assert(requests[#requests][2]=='Refresh')
print('PASS: Paragon client exact 64-bit text, complete snapshots, sender filter, Shift/Ctrl intents and combat hide/open rejection.')
print('PASS: no Paragon HUD, stock XP-bar replacement or override binding; entering-world refresh remains.')
