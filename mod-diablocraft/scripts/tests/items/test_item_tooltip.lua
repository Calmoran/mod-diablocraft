-- luacheck: globals ITEM_SOCKETABLE
-- luacheck: ignore 111 112 121 122 212 213
-- Exercise the real item payload and renderer with representative persisted rows.
local payload,init,clientHandlers
-- i3c1q, 5s8z6: Legacy of Dreams' two texts straight from the generated migration, not a copy.
local legacyEffect,legacyBonus=assert(io.open("mod-diablocraft/data/sql/db-world/updates/legendary_gems_0007_table.sql")):read("*a")
    :match("%('Unique_Gem_023_x1','Legacy of Dreams','([^']*)','([^']*)',")
assert(legacyEffect,"Legacy of Dreams is in legendary_gems_0007_table.sql")
local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        IsNull=function(_,column) return rows[index][column+1]==nil end,NextRow=function() index=index+1;return rows[index]~=nil end}
end
function WorldDBQuery(query)
    if query:find("spellid_1=81203",1,true) then return nil end -- no shell templates here
    if query:find("FROM dc_item_preset_range",1,true) or query:find("FROM dc_affix_metadata",1,true) then return nil end -- no preset-only lines here
    if query:find("FROM dc_affix_pool",1,true) then
        assert(query:find("is_percent,kind,display_order",1,true))
        return result({{"legs","mainstat","Primary Attribute",0,"primary",1},
            {"legs","skill_legs","",1,"primary",9},{"legs","resall","All Resistance",0,"secondary",2},
            -- G1: a two-part weapon elemental row, so the rolled renderer is exercised.
            {"legs","wpnfir","Fire Damage",0,"primary",10},
            -- diablocraft-il59k: the 'elemental' row rolls one of the seven dmg ids. Its is_percent is 0, so the
            -- seven must be a percent from the names table, not from this row.
            {"legs","elemental","Elemental Damage",0,"primary",11},
            -- diablocraft-z9ya2: the secondary 'resist' row rolls one of the six single-element resists.
            {"legs","resist","Elemental Resistance",0,"secondary",12}})
    elseif query:find("FROM dc_skill_affix",1,true) then return result({{"skill_barbarian_bash","Bash Damage","skill_legs"}})
    elseif query:find("b.entry,b.d3_name",1,true) then return result({{100087,"Test Legs","legs","barbarian",70,"test","","Flavour",12345}})
    -- Part 9: legendary gem items, their socket_slots and the template's sell value (ozl9's 16), and
    -- 41g6: the gem's two sentences and numbers from dc_legendary_gem, as legendary_gems_0007_table writes them.
    elseif query:find("FROM dc_legendary_gem_item",1,true) then
        assert(query:find("LEFT JOIN dc_legendary_gem g ON g.gem_id COLLATE utf8mb4_unicode_ci=li.gem_id",1,true),"the numbers are dc_legendary_gem's")
        return result({{103100,"Bane of the Powerful","neck|finger",16,
                "Gain 20% increased damage for {v:1} seconds after killing an elite pack.",
                "Gain 15% increased damage versus elites and take 15% reduced damage from elites.",30,1,0,0,nil},
            {103102,"Gem of Ease","onehand|twohand",16,"Monster kills grant +{v:0} experience.","Level Requirement Set to 1.",500,50,0,0,nil},
            {103114,"Esoteric Alteration","neck|finger",16,"Gain {v:1}% non-Physical damage reduction.",
                "While below half Life, your resistances to Cold, Fire, Lightning, Poison, and Arcane are increased by 75%.",10,0.5,0,0,100},
            {103115,"Molten Wildebeest's Gizzard","neck|finger",16,"Regenerates {v:0,} Life per Second.",
                "After not taking damage for 4 seconds, gain an absorb shield for 200% of your total Life per Second.",10000,1000,0,0,nil},
            {103111,"Zei's Stone of Vengeance","neck|finger",16,
                "Damage you deal is increased by {v:2}% for every 10 yards between you and the enemy hit. Maximum {v2:2}% increase at 50 yards.",
                "Enemies hit have a 20% chance to be stunned for 1 second.",4,0.08,20,0.4,nil},
            -- 5s8z6: Legacy of Dreams as the generator writes it (the Ancient doubling is its rank-25 power).
            {103120,"Legacy of Dreams","neck|finger",16,legacyEffect,legacyBonus,3.75,3.75,0,0,99}})
    elseif query:find("FROM dc_gem_item",1,true) then
        -- All three slot classes, because a LOOSE gem shows all three and a
        -- socketed one shows only the line that applies (decision 2026-09-12).
        return result({{103000,"Flawless Square Ruby","other","str",100},
            {103000,"Flawless Square Ruby","weapon","wpnphy",180},
            {103000,"Flawless Square Ruby","head","expmul",29}})
    elseif query:find("FROM dc_set_tooltip",1,true) then return result({{"test","Test Set"}})
    elseif query:find("FROM dc_set_bonus",1,true) then return result({{"test",2,"Test bonus"}})
    elseif query:find("dc_legendary_power",1,true) then return nil
    elseif query:find("SELECT DISTINCT",1,true) then return result({{"test","Test Legs"},{"test","Test Helm"}})
    end
    error(query)
end
-- diablocraft-il59k: item 94 is the one that carries the seven elemental rolls. The stub answers for it only
-- when its guid is in the query's IN list, so item 87's rows (and every assertion on them) stay as they were.
local ELEMENTAL_IDS={"dmgphy","dmgfir","dmgcol","dmgpsn","dmgarc","dmglit","dmghol"}
local RESIST_IDS={"resphy","resfir","rescol","respsn","resarc","reslit"}
local function listed(query,guid)
    local list=query:match("IN %(([%d,]+)%)") or ""
    return ("," .. list .. ","):find("," .. guid .. ",",1,true) ~= nil
end
local rankAsked
function CharDBQuery(query)
    if query:find("FROM dc_item_instance",1,true) then
        local rows={{87,"set",2}}
        if listed(query,94) then rows[#rows+1]={94,"set",2} end
        return result(rows)
    end
    -- A loose legendary gem's rank by item guid; 90 (Gem of Ease) has no row, so it is rank 0.
    if query:find("FROM dc_legendary_gem_rank",1,true) then rankAsked=query;return result({{89,31},{91,300},{92,120},{93,25}}) end
    assert(query:find("FROM dc_item_affix",1,true))
    local rows={{87,1,"skill_barbarian_bash",9,8,15,"primary",0,-1,0},
        {87,2,"skill_legs",9,8,15,"primary",0,-1,0},
        {87,3,"mainstat",432,416,500,"preset",0,-1,0},
        {87,4,"resall",90,86,90,"secondary",0,-1,0},
        {87,5,"sockets",1,1,1,"socket",0,-1,0},
        {87,6,"ruby",0,0,0,"gem",0,5,103000},
        -- Part 9: a socket (seq 0, drawn first) holding a legendary gem, its rank in legendary_rank (column 13),
        -- so a query that stops reading legendary_rank gets rank 0.
        {87,0,"sockets",1,1,1,"socket",0,-1,0},
        {87,9,"Unique_Gem_001_x1",0,0,0,"gem",0,0,103100,0,0,0,query:find("legendary_rank",1,true) and 12 or 0},
        -- A second socket, left empty, so the empty-socket line is drawn.
        {87,7,"sockets",1,1,1,"socket",0,-1,0},
        -- G1: a two-part weapon elemental roll (value=min, value2=max, the two brackets).
        {87,8,"wpnfir",981,981,1199,"primary",0,-1,0,1490,1175,1490}}
    if listed(query,94) then
        for seq,id in ipairs(ELEMENTAL_IDS) do rows[#rows+1]={94,seq,id,12,10,15,"primary",0,-1,0} end
        for seq,id in ipairs(RESIST_IDS) do rows[#rows+1]={94,10+seq,id,190,176,210,"secondary",0,-1,0} end
    end
    return result(rows)
end
-- The login push the server half registers; the stub has to answer it or the
-- file stops loading before the payload is built.
function RegisterPlayerEvent() end
AIO={AddAddon=function() return true end,AddHandlers=function(_,h) return h end,
    AddOnInit=function(callback) init=callback end}
dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")
init({Add=function(_,_,_,data) payload=data end},{GetItemByPos=function(_,bag,slot)
    if bag==255 and slot==6 then return {GetEntry=function() return 100087 end,GetGUIDLow=function() return 87 end,
        GetUInt32Value=function(_,field) return field==0x3C and 60 or 100 end} end
    -- A LOOSE gem in backpack cell 8 (slot 30 of the 255 container).
    if bag==255 and slot==30 then return {GetEntry=function() return 103000 end,GetGUIDLow=function() return 88 end,
        GetUInt32Value=function() return 0 end} end
    -- Two loose legendary gems, backpack cells 9 and 10.
    if bag==255 and slot==31 then return {GetEntry=function() return 103100 end,GetGUIDLow=function() return 89 end} end
    if bag==255 and slot==32 then return {GetEntry=function() return 103102 end,GetGUIDLow=function() return 90 end} end
    -- 41g6: Esoteric Alteration past its cap, Molten Wildebeest's grouped thousands, Zei's two numbers, cells 11-13.
    if bag==255 and slot==33 then return {GetEntry=function() return 103114 end,GetGUIDLow=function() return 91 end} end
    if bag==255 and slot==34 then return {GetEntry=function() return 103115 end,GetGUIDLow=function() return 92 end} end
    if bag==255 and slot==35 then return {GetEntry=function() return 103111 end,GetGUIDLow=function() return 93 end} end
    -- diablocraft-il59k: a rolled piece in backpack cell 14 (slot 36), with the seven elemental rolls.
    if bag==255 and slot==36 then return {GetEntry=function() return 100087 end,GetGUIDLow=function() return 94 end,
        GetUInt32Value=function() return 0 end} end
end})
local item=payload[255][6]
assert(item.affixes[1].name=="Strength" and item.affixes[1].value==432)
local seen={};for _,a in ipairs(item.affixes) do seen[a.id]=a end
assert(seen.skill_barbarian_bash.name=="Bash Damage" and seen.skill_barbarian_bash.percent)
assert(seen.skill_legs.name=="skill_legs")
assert(seen.ruby.parent==5 and seen.ruby.value==100 and seen.ruby.name=="Strength",
    "a socketed gem still shows only the line its slot uses")
assert(item.bound and item.owned["Test Legs"] and item.durability==60)
-- A loose gem is in no slot, so it carries all three effects at once
-- (decision 2026-09-12). It has no dc_item_instance row and never reaches
-- records(), which is why it went missing entirely before.
local loose=payload[0][8]
assert(loose and loose.gem and loose.guid==88,"the loose gem is in the payload")
assert(loose.name=="Flawless Square Ruby","the gem keeps its own name, got "..tostring(loose.name))
assert(#loose.lines==3,"three lines, one per slot class, got "..#loose.lines)
assert(loose.lines[1].slot=="Weapon" and loose.lines[2].slot=="Helm" and loose.lines[3].slot=="Other",
    "Weapon, Helm, Other, in that order")
assert(loose.lines[1].name=="Weapon Damage" and loose.lines[1].value==180)
assert(loose.lines[2].name=="Bonus Experience" and loose.lines[2].value==29 and loose.lines[2].percent)
assert(loose.lines[3].name=="Strength" and loose.lines[3].value==100 and not loose.lines[3].percent)
-- diablocraft-il59k: each of the seven elemental rolls reads its name and percent (D3 data_stats.js, "elemental"
-- group), and takes kind and order from the 'elemental' pool row, so no tooltip prints the raw key.
local rolled=payload[0][14]
assert(rolled and rolled.guid==94,"the elemental test item is in the payload")
local elemental={};for _,a in ipairs(rolled.affixes) do elemental[a.id]=a end
local ELEMENTAL_NAMES={dmgphy="Physical Damage Increase",dmgfir="Fire Damage Increase",dmgcol="Cold Damage Increase",
    dmgpsn="Poison Damage Increase",dmgarc="Arcane Damage Increase",dmglit="Lightning Damage Increase",dmghol="Holy Damage Increase"}
for id,name in pairs(ELEMENTAL_NAMES) do
    local a=elemental[id]
    assert(a and a.name==name,id.." must read '"..name.."', got "..tostring(a and a.name))
    assert(a.percent,id.." is a percent line")
    assert(a.kind=="primary" and a.order==11,id.." takes kind and order from the elemental row, got "..tostring(a.kind).." "..tostring(a.order))
end
-- diablocraft-z9ya2: each of the six single-element resists (D3 resistSingle, data_stats.js) reads its own name as a
-- flat value, and takes kind and order from the 'resist' pool row, so no tooltip prints the raw key.
local RESIST_NAMES={resphy="Physical Resistance",resfir="Fire Resistance",rescol="Cold Resistance",
    respsn="Poison Resistance",resarc="Arcane Resistance",reslit="Lightning Resistance"}
for id,name in pairs(RESIST_NAMES) do
    local a=elemental[id]
    assert(a and a.name==name,id.." must read '"..name.."', got "..tostring(a and a.name))
    assert(not a.percent and a.value==190,id.." is a flat line")
    assert(a.kind=="secondary" and a.order==12,id.." takes kind and order from the resist row, got "..tostring(a.kind).." "..tostring(a.order))
end
-- Part 9 (diablocraft-jjb3): a loose legendary gem is one item with its own rank, and a socketed one
-- carries legendary_rank, never a normal gem's stat line.
local bane,ease=payload[0][9],payload[0][10]
assert(bane and bane.gem and bane.legendary and bane.guid==89 and bane.name=="Bane of the Powerful","a loose legendary gem is in the payload")
assert(bane.rank==31 and ease.rank==0,"its rank is its dc_legendary_gem_rank row, and 0 with none")
local inList=rankAsked and rankAsked:match("IN %(([%d,]+)%)") or ""
for _,guid in ipairs({"89","90","91","92","93"}) do assert((","..inList..","):find(","..guid..",",1,true),"one rank query for every loose gem: "..inList) end
assert(bane.fits=="jewelry" and ease.fits=="weapons","where it fits comes from its socket_slots")
assert(bane.sell==16 and bane.count==1 and bane.rarity=="legendary")
-- 41g6: Value(rank) = base_value + per_rank x min(rank, max_rank), written at the marker with its decimals, in blue.
local BLUE="|cff6699ff"
assert(bane.basePower=="Gain 20% increased damage for "..BLUE.."61.0|r seconds after killing an elite pack.",bane.basePower)
assert(bane.bonus=="Gain 15% increased damage versus elites and take 15% reduced damage from elites.")
assert(ease.basePower=="Monster kills grant +"..BLUE.."500|r experience.","rank 0 is the base value")
assert(payload[0][11].basePower=="Gain "..BLUE.."60.0|r% non-Physical damage reduction.","a rank past max_rank reads the max-rank value")
assert(payload[0][12].basePower=="Regenerates "..BLUE.."130,000|r Life per Second.","{v:0,} groups thousands")
assert(payload[0][13].basePower=="Damage you deal is increased by "..BLUE.."6.00|r% for every 10 yards between you and the enemy hit. Maximum "
    ..BLUE.."30.00|r% increase at 50 yards.","{v2} is Value2(rank)")
-- The stash (dc_stash.lua) hands its cells to DCItemTooltipRecords; a legendary gem there gets the same record.
local stashed=DCItemTooltipRecords({{guid=89,entry=103100},{guid=90,entry=103102}})
assert(stashed[89] and stashed[89].legendary and stashed[89].name=="Bane of the Powerful","a stash legendary gem has its record")
assert(stashed[89].rank==31 and stashed[90].rank==0,"its rank in the stash")
assert(stashed[89].fits=="jewelry" and stashed[90].fits=="weapons","where it fits, in the stash")
assert(stashed[89].sell==16,"its sell value, in the stash")
local legacy=DCItemTooltipRecords({{guid=95,entry=103120}})[95]
assert(legacy and legacy.rank==0 and legacy.bonus=="This bonus is doubled for Ancient items.","Legacy of Dreams: rank 0, the doubling its rank-25 power")
assert(seen.Unique_Gem_001_x1.legendaryRank==12 and seen.Unique_Gem_001_x1.gemName=="Bane of the Powerful",
    "a socketed legendary gem carries its legendary_rank and name")
assert(seen.ruby.legendaryRank==nil,"a normal socketed gem carries no legendary rank")
local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
Mock.install()
Mock.setScreen(1024,768)
local testOwner={GetName=function() return "CharacterLegsSlot" end,GetID=function() return 7 end}
AIO={AddAddon=function() return false end,AddHandlers=function(_,h) clientHandlers=h;return h end}
GameTooltipTextLeft2={GetText=function() return "Legs" end}
GameTooltipTextLeft3={GetText=function() return "Requires Level 70" end}
unpack=unpack or table.unpack
SlashCmdList={}
ITEM_SOCKETABLE="<Shift Right Click to Socket> (global)"
DEFAULT_CHAT_FRAME={AddMessage=function() end}
dofile(os.getenv("DC_TOOLTIP_LUA") or "mod-diablocraft/lua/aio/dc_tooltip.lua")
local hooks=GameTooltip.scripts
-- The mock records a double line as its two entries and keeps no per-side
-- colours; record them here so row 7's both-sides rule stays tested.
local doubles={}
hooksecurefunc(GameTooltip,"AddDoubleLine",function(self,left,right,lr,lg,lb,rr,rg,rb)
    doubles[#self.lines]={lr,lg,lb,rr,rg,rb}
end)
-- The client has drawn its two native lines (title + 2 = NumLines 3) and clears
-- + redraws between hovers, firing OnTooltipCleared as the client does.
local function redraw()
    GameTooltip:ClearLines()
    hooks.OnTooltipCleared(GameTooltip)
    GameTooltip.owner=testOwner
    GameTooltip.lines={"","",""}
    hooks.OnTooltipSetItem(GameTooltip)
end
clientHandlers.Set(nil,payload);redraw()
local lines=GameTooltip.lines
local function index(fragment)
    for n,line in ipairs(lines) do if line:find(fragment,1,true) then return n end end
    error("Missing tooltip line: "..fragment)
end
assert(index("Primary")<index("+432 Strength"))
-- diablocraft-n12ju: the stored preset Strength reads like a rolled line, no '(preset)' tag on any line.
assert(not table.concat(lines,"\n"):find("(preset)",1,true),"no line wears a '(preset)' tag")
assert(index("+432 Strength")<index("+9% Bash Damage"))
assert(index("+981-1490 Fire Damage"), "a rolled two-part affix shows '+min-max <Element> Damage'")
assert(index("Secondary")<index("+90 All Resistance"))
assert(index("+90 All Resistance")<index("+100 Strength (Flawless Square Ruby)"))
-- Socketed, it still shows only the line its slot uses - and an empty socket is
-- a PRISMATIC socket (ruling 2026-09-15): the client's own colourless art and its
-- own word for it, not "Empty Socket (any gem)" beside a red gem.
assert(index("+100 Strength (Flawless Square Ruby)")<index("Prismatic Socket"))
assert(not table.concat(lines,"\n"):find("Weapon Damage",1,true),
    "a socketed gem never shows the other two slot classes")
assert(index("Prismatic Socket")<index("Test Set (1/2)"))
assert(not table.concat(lines,"\n"):find("Empty Socket",1,true),"the old wording is gone")
-- The art is the client's own colourless socket. -Prismatic is not a file this
-- client ships: WoW Client/Data/enUS/locale-enUS.MPQ carries UI-EmptySocket,
-- -Red, -Blue, -Yellow and -Meta and nothing else, so probing for -Prismatic is
-- what drew the wrong icon, and EMPTY_SOCKET_NO_COLOR is the client's own name
-- for the colourless one.
-- The assignment, not the comment that explains it.
local socketSource=assert(io.open("mod-diablocraft/lua/aio/dc_tooltip.lua")):read("*a")
local socketPath=socketSource:match('local path="([^"]+)"')
assert(socketPath=="Interface\\\\ItemSocketingFrame\\\\UI-EmptySocket",
    "the probed path is the colourless socket, got "..tostring(socketPath))
assert(socketSource:find("EMPTY_SOCKET_NO_COLOR",1,true),"the label is the client's own string")
assert(index("Test bonus")<index("Flavour"))
assert(index("Flavour")<index("Required Level 70"))
-- UI fixes row 6 (ruling 2026-10-03): one copper is one gold (Economy.lua Econ.Gold), so the
-- base's 12345 is "12,345 gold", grouped in threes, never split into g/s/c.
assert(index("Account Bound")<index("Sell Value: 12,345 gold | Durability 60 / 100"),
    "the sell value is N gold, got: "..table.concat(lines,"\n"))
assert(not table.concat(lines,"\n"):find("23s",1,true),"no silver or copper")
assert(not table.concat(lines,"\n"):find("Requires Level",1,true))
-- The stock socketing hint, from the client's own global, in green, once, after the item's own lines and before
-- the sell line: a rolled item with a socket (this one has a filled and an empty one).
local function occurrencesIn(list,needle)
    local n=0
    for _,line in ipairs(list) do if line==needle then n=n+1 end end
    return n
end
assert(occurrencesIn(lines,ITEM_SOCKETABLE)==1,"a socketed item gets the stock socketing line once, got: "..table.concat(lines,"\n"))
-- Directly under the LAST socket line (this item has two: a filled one and an empty one), before the set, the
-- power, Required Level, Account Bound and the sell line.
assert(index(ITEM_SOCKETABLE)==index("Prismatic Socket")+1 and index("+100 Strength (Flawless Square Ruby)")<index("Prismatic Socket"),
    "the line is the one right after the last socket line, got: "..table.concat(lines,"\n"))
assert(index(ITEM_SOCKETABLE)<index("Test Set (1/2)") and index(ITEM_SOCKETABLE)<index("Required Level 70")
    and index(ITEM_SOCKETABLE)<index("Account Bound"), "and before the set, Required Level and Account Bound")
local hint=GameTooltip.lineColors[index(ITEM_SOCKETABLE)]
assert(hint[1]==0 and hint[2]==1 and hint[3]==0,"the line is green")
-- An item with no socket does not get it. (Its sockets removed from the same record, then put back.)
local keptAffixes=item.affixes
local bare={}
for _,affix in ipairs(keptAffixes) do if affix.kind~="socket" and affix.kind~="gem" then bare[#bare+1]=affix end end
item.affixes=bare
redraw()
assert(occurrencesIn(GameTooltip.lines,ITEM_SOCKETABLE)==0,"an item with no socket gets no socketing line")
item.affixes=keptAffixes
-- A copy the client drew natively is not taken into the redraw, so the line never shows twice.
GameTooltipTextLeft3={GetText=function() return ITEM_SOCKETABLE end}
redraw()
assert(occurrencesIn(GameTooltip.lines,ITEM_SOCKETABLE)==1,"a native socketing line is not drawn a second time")
GameTooltipTextLeft3={GetText=function() return "Requires Level 70" end}
redraw()
local count=#lines;hooks.OnTooltipSetItem(GameTooltip);assert(#lines==count)

-- Item 1: ElvUI's bag buttons carry the bag and slot as bagID/slotID under
-- their own names, which the stock ContainerFrame name check never matched.
-- The owner below is the shape ElvUI's Bags.lua builds (bagID/slotID fields,
-- name "ElvUIBagFrameBag0Slot8"); the loose gem lives at backpack cell 8, so a
-- successful decorate proves the bag and slot were read from the button itself.
testOwner={GetName=function() return "ElvUIBagFrameBag0Slot8" end,GetID=function() return 8 end,
    bagID=0,slotID=8}
redraw()
local elvLines=table.concat(GameTooltip.lines,"\n")
assert(elvLines:find("Flawless Square Ruby",1,true),
    "an ElvUI bag button's rolled item is decorated from bagID/slotID, got: "..elvLines)
testOwner={GetName=function() return "CharacterLegsSlot" end,GetID=function() return 7 end}

-- The loose gem drawn: three lines, and none of the rolled-item furniture.
GameTooltip:ClearLines();hooks.OnTooltipCleared(GameTooltip)
GameTooltip.owner=testOwner
GameTooltip.lines={"","",""}
DCShowItemTooltip(GameTooltip,88)
local gemLines=table.concat(GameTooltip.lines,"\n")
assert(gemLines:find("Flawless Square Ruby",1,true),"the gem is named")
assert(gemLines:find("Weapon: +180 Weapon Damage",1,true),"the weapon line, got: "..gemLines)
assert(gemLines:find("Helm: +29% Bonus Experience",1,true),"the helm line is a percentage")
assert(gemLines:find("Other: +100 Strength",1,true),"the other line")
assert(not gemLines:find("Primary",1,true) and not gemLines:find("Required Level",1,true),
    "a gem is not a rolled item and gets none of its blocks")
-- Part 9: a loose legendary gem drawn in the brief's order (the power and flavour lines wait for their data).
GameTooltip:ClearLines();hooks.OnTooltipCleared(GameTooltip)
GameTooltip.owner=testOwner
GameTooltip.lines={"","",""}
DCShowItemTooltip(GameTooltip,89)
local legendaryLines=GameTooltip.lines
local function lineAt(fragment)
    for n,line in ipairs(legendaryLines) do if line:find(fragment,1,true) then return n end end
    error("Missing legendary gem line: "..fragment.." in:\n"..table.concat(legendaryLines,"\n"))
end
-- The mock keeps a double line as one "left | right" entry: "Rank 31" is the header's right side.
assert(lineAt("Bane of the Powerful")<lineAt("Legendary Gem") and lineAt("Legendary Gem")==lineAt("Rank 31")
    and lineAt("Rank 31")<lineAt("Can be inserted into jewelry with sockets.")
    and lineAt("Can be inserted into jewelry with sockets.")<lineAt("61.0|r seconds after killing an elite pack.")
    and lineAt("61.0|r seconds after killing an elite pack.")<lineAt("take 15% reduced damage from elites.")
    and lineAt("take 15% reduced damage from elites.")<lineAt("Unique Equipped")
    and lineAt("Unique Equipped")<lineAt("Bind to Account on Pickup")
    and lineAt("Bind to Account on Pickup")<lineAt("Sell Value: 16 gold"),"the legendary gem's lines, in order")
assert(not table.concat(legendaryLines,"\n"):find("Can be inserted into equipment",1,true),"not the normal gem's wording")
-- 41g6: from rank 25 the bonus is plain orange (the designer's D3 capture): no "(Requires Rank 25)".
local bonusAt=lineAt("take 15% reduced damage from elites.")
assert(not legendaryLines[bonusAt]:find("Requires Rank 25",1,true),"rank 31 has its bonus")
local bonusColour=GameTooltip.lineColors[bonusAt]
assert(bonusColour[1]==1 and bonusColour[2]==.5 and bonusColour[3]==0,"an unlocked bonus is orange")
local baseColour=GameTooltip.lineColors[lineAt("61.0|r seconds")]
assert(baseColour[1]==1 and baseColour[2]==.5 and baseColour[3]==0,"the base power is orange")
DCShowItemTooltip(GameTooltip,93)
assert(not table.concat(GameTooltip.lines,"\n"):find("Requires Rank 25",1,true),"rank 25 itself has its bonus")
DCShowItemTooltip(GameTooltip,90)
assert(table.concat(GameTooltip.lines,"\n"):find("Can be inserted into weapons with sockets.",1,true)
    and table.concat(GameTooltip.lines,"\n"):find("Rank 0",1,true),"Gem of Ease: the weapon wording, and rank 0 with no row")
-- Below rank 25 the bonus is grey, with "(Requires Rank 25)" in red after it.
local locked
for n,line in ipairs(GameTooltip.lines) do if line:find("Level Requirement Set to 1.",1,true) then locked=n end end
assert(locked and GameTooltip.lines[locked]:find("Level Requirement Set to 1. |cffff2020(Requires Rank 25)|r",1,true),"a locked bonus says so in red")
local lockedColour=GameTooltip.lineColors[locked]
assert(lockedColour[1]==.5 and lockedColour[2]==.5 and lockedColour[3]==.5,"a locked bonus is grey")
-- The same gem in a socket: its name and rank on the socket line.
redraw()
assert(index("Bane of the Powerful|r  |cff9d9d9dRank 12")<index("Prismatic Socket"),"a socketed legendary gem shows its name and rank")
assert(not table.concat(lines,"\n"):find("Unique_Gem_001_x1",1,true),"never its raw gem id")
-- wtce: under its socket line, the same power lines as the loose gem, at the socketed rank (12: 30 + 1 x 12,
-- and the bonus still locked).
local socketed=GameTooltip.lines
local function socketedAt(fragment)
    for n,line in ipairs(socketed) do if line:find(fragment,1,true) then return n end end
    error("Missing socketed legendary line: "..fragment.." in:\n"..table.concat(socketed,"\n"))
end
local socketLine=socketedAt("Bane of the Powerful|r  |cff9d9d9dRank 12")
assert(socketedAt("42.0|r seconds after killing an elite pack.")==socketLine+1,"the base power at rank 12, under the socket line")
assert(socketedAt("from elites. |cffff2020(Requires Rank 25)|r")==socketLine+2,"the rank-25 power, locked below rank 25")
assert(GameTooltip.lineColors[socketLine+2][1]==.5,"a locked socketed bonus is grey")
-- 5s8z6: Legacy of Dreams at rank 0: the orange base power ends at the 2%, and the Ancient doubling is a grey
-- "(Requires Rank 25)" line (ruling 2026-10-12: the doubling is its rank-25 power; reverses i3c1q).
DCAddItemTooltips({legacy})
GameTooltip:ClearLines();hooks.OnTooltipCleared(GameTooltip)
GameTooltip.owner=testOwner
GameTooltip.lines={"","",""}
DCShowItemTooltip(GameTooltip,95)
local legacyText=table.concat(GameTooltip.lines,"\n")
local doubled
for n,line in ipairs(GameTooltip.lines) do if line:find("This bonus is doubled for Ancient items.",1,true) then doubled=n end end
local base
for n,line in ipairs(GameTooltip.lines) do if line:find(BLUE.."3.75|r% and reduces your damage taken by 2%.",1,true) then base=n end end
assert(base and not GameTooltip.lines[base]:find("Ancient",1,true),"the base power at rank 0 has no doubling, got:\n"..legacyText)
assert(doubled==base+1 and GameTooltip.lines[doubled]:find("Ancient items. |cffff2020(Requires Rank 25)|r",1,true),
    "the doubling is the rank-25 line under it, locked at rank 0, got:\n"..legacyText)
assert(GameTooltip.lineColors[doubled][1]==.5 and GameTooltip.lineColors[doubled][2]==.5,"and grey")
-- diablocraft-item-descriptions: the power and flavour also arrive natively in the
-- item's own description, which the stock client draws quoted and gold. A window
-- this addon decorates keeps the D3 layout: the native description line is left
-- out of the top redraw, and the addon draws the power (orange, wrapped, with its
-- "inactive" note right under it, after the set bonuses) and the flavour once.
local powerText,flavourText="Gain 5% Life when you kill an enemy near you.\r\n  Second line of the power text.","An old tale."
local function occurrences(haystack,needle)
    local n,from=0,1
    while true do local a,b=haystack:find(needle,from,true);if not a then return n end;n=n+1;from=b+1 end
end
local function drawWith(descriptionLine)
    GameTooltipTextLeft2={GetText=function() return "A long stock line that must still wrap when redrawn" end}
    item.power,item.flavour=powerText,flavourText
    GameTooltipTextLeft3={GetText=function() return descriptionLine end}
    redraw()
    return table.concat(GameTooltip.lines,"\n")
end
local function at(fragment)
    for n,line in ipairs(GameTooltip.lines) do if line:find(fragment,1,true) then return n end end
    error("Missing tooltip line: "..fragment)
end
-- The mock records a double line as one rendered line: "left | right".
local function atPair(left,right)
    return at(left.." | "..right)
end
for _,description in ipairs({'"Gain 5% Life when you kill an enemy near you.\n  Second line of the power text.\nAn old tale."',"Some other line",'"Gain 5% Life when you kill an enemy near you.\n  Second line of the power text."'}) do
    local text=drawWith(description)
    assert(occurrences(text,"Second line of the power text.")==1 and occurrences(text,"An old tale.")==1,
        "power and flavour once each for description "..description..", got: "..text)
    -- Order: no native description above the rarity line; power after the set
    -- bonuses; the note directly under the power; flavour, then the footer.
    -- With a legendary power: the hint is still right under the last socket line, above the power text.
    assert(at(ITEM_SOCKETABLE)==at("Prismatic Socket")+1 and at(ITEM_SOCKETABLE)<at("Second line of the power text."),
        "the hint stays under the sockets and above the power, got: "..text)
    assert(at("Set")<at("Second line of the power text."),"no description above the rarity line, got: "..text)
    assert(at("Test bonus")<at("Second line of the power text."),"the power sits after the set bonuses, got: "..text)
    assert(at("Legendary power is inactive.")==at("Second line of the power text.")+1,"the note is right under the power")
    assert(at("Second line of the power text.")<at("An old tale.") and at("An old tale.")<at("Required Level 70"))
    local power=GameTooltip.lineColors[at("Second line of the power text.")]
    assert(power[1]==1 and power[2]==.5 and power[3]==0,"the power is orange")
    for n,line in ipairs(GameTooltip.lines) do
        if #line>40 and not doubles[n] and not doubles[n-1] then
            assert(GameTooltip.lineColors[n] and GameTooltip.lineColors[n][4]==true,"a long line is added wrapped: "..line)
        end
    end
end
GameTooltipTextLeft2={GetText=function() return "Legs" end}
GameTooltipTextLeft3={GetText=function() return "Requires Level 70" end}
item.power,item.flavour="","Flavour"
-- Row 6 with the Torment addon loaded: the sell value goes through its shared formatter,
-- the same one every balance uses, not the file's own fallback.
Diablocraft={Econ={Gold=function(value) return "<"..tostring(value)..">" end}}
redraw()
assert(table.concat(GameTooltip.lines,"\n"):find("Sell Value: <12345> gold",1,true),
    "the addon's Econ.Gold formats the sell value, got: "..table.concat(GameTooltip.lines,"\n"))
Diablocraft=nil
-- UI fixes row 7: a native line keeps the colour the client drew it in - a red line the
-- player cannot use stays red, a green Use line stays green - on both sides of a double line.
GameTooltipTextLeft2={GetText=function() return "Legs" end,GetTextColor=function() return 1,.125,.125 end}
GameTooltipTextRight2={GetText=function() return "Plate" end,GetTextColor=function() return 0,1,0 end}
GameTooltipTextLeft3={GetText=function() return "Use: Restores nothing." end,GetTextColor=function() return 0,1,0 end}
redraw()
local legs=doubles[atPair("Legs","Plate")]
assert(legs[1]==1 and legs[2]==.125 and legs[3]==.125,"the left side keeps its red")
assert(legs[4]==0 and legs[5]==1 and legs[6]==0,"the right side keeps its own colour")
local use=GameTooltip.lineColors[at("Use: Restores nothing.")]
assert(use[1]==0 and use[2]==1 and use[3]==0 and use[4]==true,"a single native line keeps its green and still wraps")
GameTooltipTextLeft2={GetText=function() return "Legs" end};GameTooltipTextRight2=nil
GameTooltipTextLeft3={GetText=function() return "Requires Level 70" end}
-- diablocraft-ipc7: a Primal Ancient's name is the stock red, the rarity line (a Set here) reads the quality's
-- words on an Ancient and a Primal, and a normal item keeps its rarity colour and word.
assert(DCRARITY.primal[1]==1 and DCRARITY.primal[2]==.1 and DCRARITY.primal[3]==.1,"the Primal red is in the one palette")
GREEN_FONT_COLOR=GREEN_FONT_COLOR or {r=.1,g=1,b=.1}
local function exact(text) local n=0;for _,l in ipairs(GameTooltip.lines) do if l==text then n=n+1 end end return n end
for _,case in ipairs({{"normal",{0,1,0},0,1,"Set"},{"ancient",{0,1,0},1,0,"Ancient"},{"primal",{1,.1,.1},1,0,"Primal Ancient"}}) do
    item.quality=case[1];redraw()
    local c=GameTooltip.lineColors[at(item.name)]
    assert(c[1]==case[2][1] and c[2]==case[2][2] and c[3]==case[2][3],case[1].." name colour, got "..c[1]..","..c[2]..","..c[3])
    assert(exact("Set")==case[4],case[1].." keeps the word Set only when normal")
    -- the green tag is one "Ancient" / "Primal Ancient" line; the rarity line is a second one
    assert(exact(case[5])==(case[1]=="normal" and 1 or 2),case[1].." rarity line reads "..case[5]..": "..table.concat(GameTooltip.lines,"\n"))
end
item.quality=nil;redraw()
print("PASS: legendary gems loose and socketed (rank, fit, order, sell)")
print("PASS: tooltip ordering, mainstat/skill labels, fallback, socketed and loose gems, set ownership, footer and duplicate guard")
