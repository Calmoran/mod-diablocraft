-- luacheck: ignore 111 112 113 121 122 212 213
-- diablocraft-wpt7l.3: a made item's "<Made by Name>" line. The real dc_tooltip.lua loads the record's made_by (the
-- server half) and draws it under the Primal Ancient tag (the client half), leaving the client's own creator line out;
-- an item nobody made keeps the client's line and gets none from the record. Runs on the real file, then on four
-- mutations that must each fail. Run from the repo root: lua mod-diablocraft/scripts/tests/items/test_made_by.lua
local REAL="mod-diablocraft/lua/aio/dc_tooltip.lua"
local unpack=unpack or table.unpack

local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        IsNull=function(_,column) return rows[index][column+1]==nil end,NextRow=function() index=index+1;return rows[index]~=nil end}
end

local function scenario(path)
    local payload,init,clientHandlers
    function WorldDBQuery(query)
        if query:find("b.entry,b.d3_name",1,true) then return result({{100087,"Test Ring","finger","",70,"","","",100}}) end
    end
    function CharDBQuery(query)
        if query:find("FROM dc_item_instance",1,true) then
            -- The made_by column only when the query asks for it, as the database would answer.
            local asks=query:find("made_by",1,true)~=nil
            return result({{1,"legendary",0,"primal",asks and "Grimfeather" or nil}})
        end
        -- no affix rows: the database answers nil
    end
    function RegisterPlayerEvent() end
    AIO={AddAddon=function() return true end,AddHandlers=function(_,h) return h end,AddOnInit=function(callback) init=callback end}
    dofile(path)
    init({Add=function(_,_,_,data) payload=data end},{GetItemByPos=function(_,bag,slot)
        if bag==255 and slot==10 then return {GetEntry=function() return 100087 end,GetGUIDLow=function() return 1 end,
            GetUInt32Value=function() return 0 end} end
    end})
    local record=payload[255][10]
    assert(record and record.madeBy=="Grimfeather","the record carries the maker's name, got "..tostring(record and record.madeBy))

    local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
    Mock.install()
    Mock.setScreen(1024,768)
    AIO={AddAddon=function() return false end,AddHandlers=function(_,h) clientHandlers=h;return h end}
    ITEM_CREATED_BY="<Made by %s>"
    GREEN_FONT_COLOR={r=.1,g=1,b=.1}   -- the stock FrameXML global, as test_item_link sets it
    GameTooltipTextLeft2={GetText=function() return "<Made by Native>" end}
    GameTooltipTextLeft3={GetText=function() return "Finger" end}
    SlashCmdList={}
    ITEM_SOCKETABLE="<Shift Right Click to Socket>"
    DEFAULT_CHAT_FRAME={AddMessage=function() end}
    dofile(path)
    local hooks=GameTooltip.scripts
    local owner={GetName=function() return "CharacterFinger0Slot" end,GetID=function() return 11 end}
    local function redraw()
        GameTooltip:ClearLines();hooks.OnTooltipCleared(GameTooltip)
        GameTooltip.owner=owner;GameTooltip.lines={"","",""}
        hooks.OnTooltipSetItem(GameTooltip)
        return GameTooltip.lines
    end
    clientHandlers.Set(nil,payload)
    local lines=redraw()
    local function at(text) for n,line in ipairs(lines) do if line==text then return n end end end
    assert(at("Primal Ancient") and at("<Made by Grimfeather>")==at("Primal Ancient")+1,
        "the record's line sits under the tag: "..table.concat(lines," / "))
    assert(not at("<Made by Native>"),"the client's own creator line is left out when the record draws one")
    local green=GameTooltip.lineColors[at("<Made by Grimfeather>")]
    assert(green[1]==GREEN_FONT_COLOR.r and green[2]==GREEN_FONT_COLOR.g,"in the stock green")
    -- Nobody made it: no line from the record, and the client's own line stays.
    payload[255][10].madeBy=""
    clientHandlers.Set(nil,payload)
    lines=redraw()
    assert(not at("<Made by Grimfeather>") and at("<Made by Native>"),"an item nobody made keeps the client's line: "..table.concat(lines," / "))
end

scenario(REAL)

local source=assert(io.open(REAL)):read("*a")
local function plain(text) return (text:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]","%%%0")) end
local mutants={
    {"the record asks for made_by","quality_tier,made_by FROM dc_item_instance","quality_tier FROM dc_item_instance"},
    {"the line is drawn","if made then local green","if false then local green"},
    {"the client's line is left out","isDescription(item,line) or (made and isMadeBy(line))","isDescription(item,line)"},
    {"only when the record draws one","(made and isMadeBy(line))","isMadeBy(line)"},
}
for _,m in ipairs(mutants) do
    local name,old,new=m[1],m[2],m[3]
    local count=select(2,source:gsub(plain(old),""))
    assert(count==1,"mutation anchor moved: "..old)
    local path=os.tmpname()
    local out=assert(io.open(path,"w"));out:write((source:gsub(plain(old),(new:gsub("%%","%%%%")))));out:close()
    local ok=pcall(scenario,path)
    os.remove(path)
    assert(not ok,"mutation survived: "..name)
end
print("test_made_by: OK (the record's maker, the line under the tag in green, the client's line out only when replaced; four mutations fail)")
