-- luacheck: ignore 111 112 113 121 122 212 213
-- diablocraft-szwma: Caldesann's Despair's row (affix kind `augment`, cube-messages.md "The augment row") draws one line,
-- "+N <attribute> (Augmented)", below the item's own lines and never as one of them. Runs the real dc_tooltip.lua (the
-- server half loads the stored row, the client half draws it), then three mutations that must each fail.
-- Run from the repo root: lua mod-diablocraft/scripts/tests/crafting/test_augment_tooltip.lua
local REAL="mod-diablocraft/lua/aio/dc_tooltip.lua"

local function result(rows)
    local index=1
    local function value(_,column) return rows[index][column+1] end
    return {GetUInt32=value,GetInt32=value,GetDouble=value,GetString=value,
        IsNull=function(_,column) return rows[index][column+1]==nil end,NextRow=function() index=index+1;return rows[index]~=nil end}
end

local function scenario(path)
    local payload,init,clientHandlers
    function WorldDBQuery(query)
        if query:find("FROM dc_affix_pool",1,true) then
            return result({{"finger","mainstat","Primary Attribute",0,"primary",1},{"finger","vit","Vitality",0,"primary",2},
                {"finger","critdmg","Critical Hit Damage",1,"secondary",20}})
        elseif query:find("b.entry,b.d3_name",1,true) then return result({{100087,"Test Ring","finger","",70,"","","",100}}) end
    end
    function CharDBQuery(query)
        if query:find("FROM dc_item_instance",1,true) then return result({{1,"legendary",0,"ancient"}}) end
        assert(query:find("FROM dc_item_affix",1,true))
        -- As TransmuteAugment stores it: the next seq, the attribute, value = range_min = range_max.
        return result({{1,1,"vit",600,550,650,"primary",0,-1,0},{1,2,"critdmg",50,26,50,"secondary",0,-1,0},
            {1,3,"vit",200,200,200,"augment",0,-1,0}})
    end
    function RegisterPlayerEvent() end
    AIO={AddAddon=function() return true end,AddHandlers=function(_,h) return h end,AddOnInit=function(callback) init=callback end}
    dofile(path)
    init({Add=function(_,_,_,data) payload=data end},{GetItemByPos=function(_,bag,slot)
        if bag==255 and slot==10 then return {GetEntry=function() return 100087 end,GetGUIDLow=function() return 1 end,
            GetUInt32Value=function() return 0 end} end
    end})

    local Mock=dofile("mod-diablocraft/scripts/dc_widget_mock.lua")
    Mock.install()
    Mock.setScreen(1024,768)
    AIO={AddAddon=function() return false end,AddHandlers=function(_,h) clientHandlers=h;return h end}
    GREEN_FONT_COLOR={r=.1,g=1,b=.1}
    GameTooltipTextLeft2={GetText=function() return "Finger" end}
    SlashCmdList={}
    ITEM_SOCKETABLE="<Shift Right Click to Socket>"
    DEFAULT_CHAT_FRAME={AddMessage=function() end}
    dofile(path)
    local hooks=GameTooltip.scripts
    local owner={GetName=function() return "CharacterFinger0Slot" end,GetID=function() return 11 end}
    GameTooltip:ClearLines();hooks.OnTooltipCleared(GameTooltip)
    GameTooltip.owner=owner;GameTooltip.lines={"",""}
    clientHandlers.Set(nil,payload)
    hooks.OnTooltipSetItem(GameTooltip)
    local lines=GameTooltip.lines
    local function at(text) for n,line in ipairs(lines) do if line==text then return n end end end
    local shown=table.concat(lines," / ")
    local augmented,secondary=at("+200 Vitality (Augmented)"),at("+50% Critical Hit Damage  [26%–50%]")
    assert(augmented,"the augment line: "..shown)
    assert(secondary and augmented>secondary,"below the item's own lines: "..shown)
    assert(at("+600 Vitality  [550–650]") and not at("+200 Vitality"),"the row is no Primary line: "..shown)
    local c=GameTooltip.lineColors[augmented]
    assert(c[1]==.45 and c[2]==.72 and c[3]==1,"in the affix blue")
end

scenario(REAL)

local source=assert(io.open(REAL)):read("*a")
local function plain(text) return (text:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]","%%%0")) end
local mutants={
    {"the stored kind is kept",'savedKind=="gem" or savedKind=="augment"','savedKind=="gem"'},
    {"the line is drawn",'if affix.kind=="augment" then tooltip:AddLine','if false then tooltip:AddLine'},
    {"it says Augmented",'format(affix).." (Augmented)"','format(affix)'},
}
for _,m in ipairs(mutants) do
    local name,old,new=m[1],m[2],m[3]
    assert(select(2,source:gsub(plain(old),""))==1,"mutation anchor moved: "..old)
    local path=os.tmpname()
    local out=assert(io.open(path,"w"));out:write((source:gsub(plain(old),(new:gsub("%%","%%%%")))));out:close()
    local ok=pcall(scenario,path)
    os.remove(path)
    assert(not ok,"mutation survived: "..name)
end
print("test_augment_tooltip: OK (the augment row is one '(Augmented)' line below the item's own, in the affix blue; three mutations fail)")
