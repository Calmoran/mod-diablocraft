-- Rolled item presentation only. C++ owns affixes, binding, sockets and stats.
-- luacheck: globals ItemRefTooltip HandleModifiedItemClick SetItemRef IsModifiedClick ChatEdit_GetActiveWindow GetMouseFocus DCRequestItemLink DCAffixFallback DCThrottle DCGemInfo DCOnItemRecords DCItemRarity DCTunables DCShowRecipePreview DCRecipePreviewsClear DCAFFIXLINE
-- luacheck: globals BankFrame MerchantFrame InspectFrame GetNumBuybackItems
local AIO=AIO or require("AIO")
local CHANNEL="DiablocraftTooltip"
-- Security G9: stock inspect (WorldSession::HandleInspectOpcode) only answers a
-- target within INSPECT_DISTANCE and visible to the caller. Mirror the range or
-- a modified client can read any player's worn affix rolls by GUID.
local INSPECT_DISTANCE=28.0
if AIO.AddAddon() then
    local handlers=AIO.AddHandlers(CHANNEL,{})
    local bases,pools,skills,gems,sets,legendaries={},{},{},{},{},{}
    local presetNames,metadata={},{}
    -- The unidentified shells' entries: no dc_base_item row, so they are listed here by entry.
    local shellEntries={}
    -- What a legendary gem's socket_slots say it goes into, in D3's words ("Can be inserted into
    -- jewelry with sockets."; Gem of Ease the weapon wording).
    local FITS={neck="jewelry",finger="jewelry",onehand="weapons",twohand="weapons"}
    local function load()
        local rows=WorldDBQuery("SELECT slot,affix_id,affix_name,is_percent,kind,display_order FROM dc_affix_pool")
        if rows then repeat
            local slot,id=rows:GetString(0),rows:GetString(1);pools[slot]=pools[slot] or {}
            pools[slot][id]={name=rows:GetString(2),percent=rows:GetUInt32(3)~=0,kind=rows:GetString(4),order=rows:GetUInt32(5)}
        until not rows:NextRow() end
        rows=WorldDBQuery("SELECT affix_id,affix_name,group_id FROM dc_skill_affix")
        if rows then repeat skills[rows:GetString(0)]={name=rows:GetString(1),group=rows:GetString(2)} until not rows:NextRow() end
        -- A fixed stat the slot's pool has no row for (dc_items.cpp PlanRoll's itemPresets fallback): the item's own
        -- row names it. One row per bracket, each with the same name, percent, kind and order (generate_item_presets.py).
        rows=WorldDBQuery("SELECT entry,affix_id,affix_name,is_percent,kind,display_order FROM dc_item_preset_range")
        if rows then repeat
            local entry=rows:GetUInt32(0);presetNames[entry]=presetNames[entry] or {}
            presetNames[entry][rows:GetString(1)]={name=rows:GetString(2),percent=rows:GetUInt32(3)~=0,kind=rows:GetString(4),order=rows:GetUInt32(5)}
        until not rows:NextRow() end
        -- A stat no pool holds, named from data_stats.js (data/d3/affix_metadata.csv).
        rows=WorldDBQuery("SELECT affix_id,affix_name,is_percent,kind,display_order FROM dc_affix_metadata")
        if rows then repeat
            metadata[rows:GetString(0)]={name=rows:GetString(1),percent=rows:GetUInt32(2)~=0,kind=rows:GetString(3),order=rows:GetUInt32(4)}
        until not rows:NextRow() end
        -- The same two fallbacks by code alone, for the Mystic window (dc_crafting.lua handlers.Tables): a preset code
        -- carries one name and percent on every item that has it, so any item's row names it, ahead of the metadata.
        local fallback={}
        for id,info in pairs(metadata) do fallback[id]=info end
        for _,own in pairs(presetNames) do for id,info in pairs(own) do fallback[id]=info end end
        DCAffixFallback=fallback
        rows=WorldDBQuery("SELECT b.entry,b.d3_name,b.slot,b.designated_class,b.level_req,t.set_id,t.power_text,t.flavour,i.SellPrice FROM dc_base_item b LEFT JOIN dc_item_tooltip t ON t.d3_id=b.d3_id JOIN item_template i ON i.entry=b.entry")
        if rows then repeat
            bases[rows:GetUInt32(0)]={entry=rows:GetUInt32(0),name=rows:GetString(1),slot=rows:GetString(2),class=rows:GetString(3),level=rows:GetUInt32(4),set=rows:GetString(5) or "",power=rows:GetString(6) or "",flavour=rows:GetString(7) or "",sell=rows:GetUInt32(8)}
        until not rows:NextRow() end
        -- A shell is an item whose use spell is Identify (81203, dc_items.cpp IDENTIFY_ITEM_SPELL), the one test the loot
        -- code's own shell load makes; it is a template only, so without this list its record was never asked for.
        rows=WorldDBQuery("SELECT entry FROM item_template WHERE spellid_1=81203")
        if rows then repeat shellEntries[rows:GetUInt32(0)]=true until not rows:NextRow() end
        rows=WorldDBQuery("SELECT g.entry,g.name,e.slot_class,e.stat,e.value FROM dc_gem_item g JOIN dc_gem_effect e ON e.entry=g.entry")
        if rows then repeat
            local id=rows:GetUInt32(0);gems[id]=gems[id] or {name=rows:GetString(1)}
            gems[id][rows:GetString(2)]={stat=rows:GetString(3),value=rows:GetDouble(4)}
        until not rows:NextRow() end
        -- Legendary gems (docs/contracts/legendary-gems.md, "The gem as an item"): the 21 legendary gem
        -- items. Their sell value is the template's own, as a rolled item's is. Their two power
        -- sentences and the numbers of the rank lookup are dc_legendary_gem's.
        -- One literal, so test_crafting_queries.py runs it against the fixture world. dc_legendary_gem takes the world
        -- database's default collation and dc_legendary_gem_item names utf8mb4_unicode_ci, so the join names one.
        rows=WorldDBQuery("SELECT li.entry,t.name,li.socket_slots,t.SellPrice,COALESCE(g.base_effect,''),COALESCE(g.rank_25_bonus,''),COALESCE(g.base_value,0),COALESCE(g.per_rank,0),COALESCE(g.base_value_2,0),COALESCE(g.per_rank_2,0),g.max_rank FROM dc_legendary_gem_item li JOIN item_template t ON t.entry=li.entry LEFT JOIN dc_legendary_gem g ON g.gem_id COLLATE utf8mb4_unicode_ci=li.gem_id")
        if rows then repeat
            local slot=rows:GetString(2):match("^[^|]+") or ""
            legendaries[rows:GetUInt32(0)]={name=rows:GetString(1),fits=FITS[slot] or slot,sell=rows:GetUInt32(3),
                effect=rows:GetString(4),bonus=rows:GetString(5),base=rows:GetDouble(6),perRank=rows:GetDouble(7),
                base2=rows:GetDouble(8),perRank2=rows:GetDouble(9),maxRank=(not rows:IsNull(10)) and rows:GetUInt32(10) or nil}
        until not rows:NextRow() end
        rows=WorldDBQuery("SELECT set_id,name FROM dc_set_tooltip")
        if rows then repeat sets[rows:GetString(0)]={name=rows:GetString(1),pieces={},bonuses={}} until not rows:NextRow() end
        rows=WorldDBQuery("SELECT set_id,pieces,body FROM dc_set_bonus ORDER BY set_id,pieces")
        if rows then repeat local set=sets[rows:GetString(0)];if set then set.bonuses[#set.bonuses+1]={count=rows:GetUInt32(1),text=rows:GetString(2)} end until not rows:NextRow() end
        rows=WorldDBQuery("SELECT DISTINCT t.set_id,b.d3_name,b.slot FROM dc_base_item b JOIN dc_item_tooltip t ON t.d3_id=b.d3_id WHERE b.pool_version='yes' AND t.set_id<>'' ORDER BY t.set_id,b.slot,b.d3_name")
        if rows then repeat local set=sets[rows:GetString(0)];if set then set.pieces[#set.pieces+1]=rows:GetString(1) end until not rows:NextRow() end
        -- The item power table (dc_legendary_power, docs/contracts/legendary-powers.md): an item or a set bonus with a row
        -- there is built, and reads active when worn / when its piece count is reached. One without a row stays inactive.
        rows=WorldDBQuery("SELECT b.entry FROM dc_base_item b JOIN dc_legendary_power p ON p.owner=b.d3_id AND p.pieces=0")
        if rows then repeat local base=bases[rows:GetUInt32(0)];if base then base.built=true end until not rows:NextRow() end
        rows=WorldDBQuery("SELECT owner,pieces FROM dc_legendary_power WHERE pieces>0")
        if rows then repeat
            local name,count=rows:GetString(0),rows:GetUInt32(1)
            for _,set in pairs(sets) do if set.name==name then set.built=set.built or {};set.built[count]=true end end
        until not rows:NextRow() end
    end
    load()
    -- A broken piece is worn but counts for nothing (Items::Apply; ItemPowers::Refresh). The server's count is the
    -- authority; this is the same rule on the same worn items.
    local function counts(item) return not (item and item.IsBroken and item:IsBroken()) end
    local function wearing(item) return counts(item) and item and item.IsEquipped and item:IsEquipped() or false end
    -- The bonuses of the item's set that are on: the worn pieces reach their level and the table has their power.
    local function bonusesOn(set,owned)
        local worn,on=0,{}
        for _ in pairs(owned) do worn=worn+1 end
        for pieces in pairs(set.built or {}) do if worn>=pieces then on[pieces]=true end end
        return on
    end
    local labels={str="Strength",dex="Dexterity",int="Intelligence",expmul="Bonus Experience",wpnphy="Weapon Damage",edmg="Damage against Elites"}
    -- The 'elemental' pool row rolls one of these seven (dc_items.cpp ElementalAffixes).
    -- They take that row's range, order and kind, and each reads as a percent under its own name.
    local ELEMENTAL={dmgphy="Physical Damage Increase",dmgfir="Fire Damage Increase",dmgcol="Cold Damage Increase",dmgpsn="Poison Damage Increase",
        dmgarc="Arcane Damage Increase",dmglit="Lightning Damage Increase",dmghol="Holy Damage Increase"}
    -- The secondary 'resist' pool row rolls one of these six (D3 resistSingle, data_stats.js).
    -- They take that row's range, order, kind and flat value, under their own name.
    local RESIST={resphy="Physical Resistance",resfir="Fire Resistance",rescol="Cold Resistance",respsn="Poison Resistance",
        resarc="Arcane Resistance",reslit="Lightning Resistance"}
    local function describe(base,id)
        local group=id
        if id=="mainstat" then
            id=(base.class=="monk" or base.class=="demonhunter") and "dex" or
                (base.class=="wizard" or base.class=="witchdoctor" or base.class=="necromancer") and "int" or "str"
        end
        if id=="str" or id=="dex" or id=="int" then group="mainstat" end
        if skills[id] then group=skills[id].group end
        if ELEMENTAL[id] then group="elemental" end
        if RESIST[id] then group="resist" end
        -- The slot's pool first; a code it does not know is the item's own preset line, then a stat no pool holds.
        local pool=pools[base.slot] or {};local own=presetNames[base.entry] or {}
        local info=pool[id] or pool[group] or own[id] or own[group] or metadata[id] or metadata[group] or {}
        local name=labels[id] or ELEMENTAL[id] or RESIST[id] or (skills[id] and skills[id].name) or info.name or id
        if not name:find("%S") then name=id end
        return name,info.percent or ELEMENTAL[id]~=nil or id=="expmul" or id=="edmg",info.kind or "primary",info.order or 999
    end
    -- A LOOSE gem is in no slot, so its stat name cannot come from a slot's own
    -- pool the way describe() takes it. Every slot that carries an affix carries
    -- the same name and the same is_percent for it, so the first pool holding the
    -- id answers for all of them - and a socketed gem's line, which still goes
    -- through describe(), says the same words.
    local function describeStat(id)
        local info
        for _,pool in pairs(pools) do if pool[id] then info=pool[id];break end end
        info=info or {}
        local name=labels[id] or info.name or id
        if not name:find("%S") then name=id end
        return name,info.percent or id=="expmul" or id=="edmg"
    end
    -- Gems have no dc_item_instance row and no base item, so they never reach
    -- records(). D3 shows a loose gem's three effects at once, one per slot
    -- class, and only the line that applies once it is socketed. gems.csv
    -- already carries all three; this is the reading.
    local GEM_SLOTS={{"weapon","Weapon"},{"head","Helm"},{"other","Other"}}
    -- Which of a gem's three effects an item takes: one rule, read by the socketed-gem line below and by
    -- the Jeweler window (dc_jeweler.lua), so the two never disagree.
    local function gemSlotClass(slot)
        return slot=="head" and "head" or (slot=="onehand" or slot=="twohand") and "weapon" or "other"
    end
    local function gemRecord(entry,guid)
        local gem=gems[entry];if not gem then return nil end
        local record={gem=true,guid=guid,entry=entry,name=gem.name,lines={}}
        for _,pair in ipairs(GEM_SLOTS) do
            local effect=gem[pair[1]]
            if effect then
                local name,percent=describeStat(effect.stat)
                record.lines[#record.lines+1]={slot=pair[2],name=name,value=effect.value,percent=percent}
            end
        end
        return record
    end
    -- base_effect with each marker replaced by the value at the rank (docs/contracts/legendary-gems.md, "The marker"):
    -- {v:N} is Value(rank) = base_value + per_rank x min(rank, max_rank), {v2:N} the same for the second pair, N the
    -- decimals, a trailing comma grouping thousands. The number is in D3's blue (a D3 capture), the sentence orange.
    local function basePower(info,rank)
        local capped=info.maxRank and math.min(rank,info.maxRank) or rank
        return (info.effect:gsub("{(v2?):(%d+)(,?)}",function(tag,places,comma)
            local value=tag=="v" and info.base+info.perRank*capped or info.base2+info.perRank2*capped
            local text,more=string.format("%."..places.."f",value),comma=="," and 1 or 0
            while more>0 do text,more=text:gsub("^(%-?%d+)(%d%d%d)","%1,%2") end
            return "|cff6699ff"..text.."|r"
        end))
    end
    -- A loose legendary gem is one item with its own rank (dc_legendary_gem_rank by item guid; no row
    -- is rank 0, the contract). `loose` is a list of {guid=,entry=}; one query answers for the lot,
    -- and the records come back keyed by guid.
    local function legendaryRecords(loose)
        local guids,ranks,out={},{},{}
        for _,gem in ipairs(loose) do guids[#guids+1]=gem.guid end
        if #guids==0 then return out end
        local rows=CharDBQuery("SELECT item_guid,gem_rank FROM dc_legendary_gem_rank WHERE item_guid IN ("..table.concat(guids,",")..")")
        if rows then repeat ranks[rows:GetUInt32(0)]=rows:GetUInt32(1) until not rows:NextRow() end
        for _,gem in ipairs(loose) do
            local info=legendaries[gem.entry]
            local rank=ranks[gem.guid] or 0
            out[gem.guid]={gem=true,legendary=true,rarity="legendary",guid=gem.guid,entry=gem.entry,name=info.name,count=1,
                rank=rank,fits=info.fits,sell=info.sell,basePower=basePower(info,rank),bonus=info.bonus}
        end
        return out
    end
    -- The Jeweler window words a gem's effect exactly as the tooltip's gem body does ("+6 Life per Hit"),
    -- by asking here rather than keeping a second copy of the stat names. Looked up when asked, so the
    -- load order of the two files does not matter.
    DCGemInfo={
        Slot=gemSlotClass,
        -- {weapon=text,head=text,other=text} for a gem entry, nil when the entry is not a gem.
        Effects=function(entry)
            local record=gemRecord(entry,0)
            if not record then return nil end
            local keys={Weapon="weapon",Helm="head",Other="other"}
            local out={}
            for _,line in ipairs(record.lines) do
                out[keys[line.slot]]=string.format("+%g%s %s",line.value,line.percent and "%" or "",line.name)
            end
            return out
        end,
    }
    -- A legendary power's per-item roll (docs/contracts/legendary-powers.md "Per-item rolls"): the generator wrote the
    -- table's range into power_text as min–max (generate_crafting.py), so that range gets the item's number with the
    -- range beside it, the way a rolled affix line shows it. A text without that range is drawn as it is.
    local function rolledPower(text,value,min,max)
        local at,stop=text:find(string.format("%g–%g",min,max),1,true)
        if not at then return nil end
        local suffix=text:sub(stop+1,stop+1)=="%" and "%" or ""
        return text:sub(1,at-1)..string.format("%g%s [%g%s–%g%s]",value,suffix,min,suffix,max,suffix)..text:sub(stop+1+#suffix)
    end
    -- One record per rolled item guid. Split out of payload so a screen that
    -- holds items nobody's bags contain - the account stash - can ask for the
    -- same rows by guid instead of by bag and slot.
    local function records(found,guids,equipped)
        equipped=equipped or {}
        if #guids==0 then return {} end
        local list=table.concat(guids,",");local data={}
        local heads=CharDBQuery("SELECT item_guid,rarity,bound_account,quality_tier,made_by FROM dc_item_instance WHERE item_guid IN ("..list..")")
        if heads then repeat
            local guid=heads:GetUInt32(0);local record=found[guid];local b=record.base
            data[guid]={guid=guid,entry=b.entry,name=b.name,rarity=heads:GetString(1),bound=heads:GetUInt32(2)~=0,quality=heads:GetString(3),madeBy=heads:GetString(4),level=b.level,sell=b.sell,
                power=b.power,flavour=b.flavour,affixes={},set=sets[b.set],owned=equipped[b.set] or {},
                active=b.built and wearing(record.item) or nil,
                -- A built Bottomless potion's power is never worn: it works when the slotted potion is drunk.
                drunk=b.built and b.slot=="potion" or nil,
                bonusOn=sets[b.set] and bonusesOn(sets[b.set],equipped[b.set] or {}) or nil,
                durability=record.item and record.item:GetUInt32Value(0x3C) or 0,
                maxDurability=record.item and record.item:GetUInt32Value(0x3D) or 0}
        until not heads:NextRow() end
        -- A shell has no dc_item_instance row - that is
        -- what makes it unidentified - so the guids the query above did not
        -- answer for are asked of dc_item_unidentified instead. The row is read
        -- for its RARITY and its quality (quality shows before identify); the
        -- base item it will become stays server-side,
        -- so there is nothing here for the client to mine.
        local pending={}
        for _,guid in ipairs(guids) do if not data[guid] then pending[#pending+1]=guid end end
        if #pending>0 then
            local shells=CharDBQuery("SELECT item_guid,rarity,quality_tier FROM dc_item_unidentified WHERE item_guid IN ("..table.concat(pending,",")..")")
            if shells then repeat
                local guid=shells:GetUInt32(0)
                data[guid]={guid=guid,name="Unidentified",rarity=shells:GetString(1),quality=shells:GetString(2),
                    unidentified=true,affixes={},owned={}}
            until not shells:NextRow() end
        end
        -- A legendary potion is neither rolled
        -- nor unidentified: it has no dc_item_instance row, only its base row
        -- and the power and flavour dc_item_tooltip holds. It is drawn as a
        -- legendary with no affixes, so the power line and "Legendary power is
        -- inactive." appear as on any legendary. A potion base with no power
        -- (the stock test fixture) keeps the client's own tooltip.
        for _,guid in ipairs(pending) do
            local record=found[guid];local b=record and record.base
            if not data[guid] and b and b.slot=="potion" and b.power~="" then
                data[guid]={guid=guid,entry=b.entry,name=b.name,rarity="legendary",bound=false,level=b.level,sell=b.sell,
                    power=b.power,flavour=b.flavour,affixes={},owned={},durability=0,maxDurability=0}
            end
        end
        local rows=CharDBQuery("SELECT item_guid,seq,affix_id,value,range_min,range_max,kind,rerolled,COALESCE(parent_seq,-1),COALESCE(gem_entry,0),value2,range_min2,range_max2,COALESCE(legendary_rank,0) FROM dc_item_affix WHERE item_guid IN ("..list..") ORDER BY item_guid,seq")
        if rows then repeat
            local guid=rows:GetUInt32(0);local target=data[guid]
            if target and rows:GetString(6)=="power" then
                -- Not an affix line: the number goes on the power line (rolledPower; power stays the description text).
                target.rolledPower=rolledPower(target.rolledPower or target.power or "",rows:GetDouble(3),rows:GetDouble(4),rows:GetDouble(5)) or target.rolledPower
            elseif target then
                local base=found[guid].base;local id=rows:GetString(2);local name,percent,kind,order=describe(base,id)
                local savedKind=rows:GetString(6)
                local affix={seq=rows:GetUInt32(1),id=id,name=name,percent=percent,kind=kind,order=order,value=rows:GetDouble(3),min=rows:GetDouble(4),max=rows:GetDouble(5),rerolled=rows:GetUInt32(7)~=0,parent=rows:GetInt32(8),value2=rows:GetDouble(10),min2=rows:GetDouble(11),max2=rows:GetDouble(12)}
                if savedKind=="socket" or savedKind=="gem" or savedKind=="augment" then affix.kind=savedKind end
                affix.gemEntry=rows:GetUInt32(9)
                -- A socketed legendary gem carries its rank in legendary_rank (the contract), not gem_rank.
                local legendary=savedKind=="gem" and legendaries[affix.gemEntry]
                if legendary then
                    affix.name=legendary.name;affix.gemName=legendary.name;affix.legendaryRank=rows:GetUInt32(13)
                    -- The same power lines as the loose gem, at the socketed gem's rank.
                    affix.basePower=basePower(legendary,affix.legendaryRank);affix.bonus=legendary.bonus
                elseif savedKind=="gem" then
                    local gem=gems[rows:GetUInt32(9)];local slot=gemSlotClass(base.slot)
                    if gem and gem[slot] then
                        local effect=gem[slot];affix.name,affix.percent=describe(base,effect.stat);affix.value=effect.value;affix.min=effect.value;affix.max=effect.value;affix.gemName=gem.name
                    end
                end
                target.affixes[#target.affixes+1]=affix
            end
        until not rows:NextRow() end
        for _,item in pairs(data) do
            table.sort(item.affixes,function(a,b) if a.order~=b.order then return a.order<b.order end;return a.seq<b.seq end)
        end
        return data
    end
    -- One context's client table, built only from positions the server itself
    -- reads through GetItemByPos. `collect` is handed the local add() and calls
    -- it with whatever container positions it owns; because the item comes from
    -- a real container and never from a GUID the client sent, a context can
    -- never make the addon show an item the player does not hold.
    local function gather(player,collect)
        -- load() runs once when ALE executes this file at world startup; if the
        -- world tables were not readable then, every item would fail the bases
        -- lookup below and the payload would be silently empty. Reload instead.
        if not next(bases) then load() end
        local found,guids,equipped,loose,legendary={},{},{},{},{}
        local function add(bag,slot,item)
            if not item then return end
            if legendaries[item:GetEntry()] then
                legendary[#legendary+1]={bag=bag,slot=slot,guid=item:GetGUIDLow(),entry=item:GetEntry()}
                return
            end
            if gems[item:GetEntry()] then
                loose[#loose+1]={bag=bag,slot=slot,record=gemRecord(item:GetEntry(),item:GetGUIDLow())}
                return
            end
            if not bases[item:GetEntry()] and not shellEntries[item:GetEntry()] then return end
            local base=bases[item:GetEntry()];local guid=item:GetGUIDLow()
            found[guid]={bag=bag,slot=slot,base=base,item=item};guids[#guids+1]=guid
            if bag==255 and base and base.set~="" and counts(item) then equipped[base.set]=equipped[base.set] or {};equipped[base.set][base.name]=true end
        end
        collect(add)
        local out={}
        for guid,item in pairs(records(found,guids,equipped)) do
            local pos=found[guid];out[pos.bag]=out[pos.bag] or {};out[pos.bag][pos.slot]=item
        end
        for _,entry in ipairs(loose) do
            if entry.record then out[entry.bag]=out[entry.bag] or {};out[entry.bag][entry.slot]=entry.record end
        end
        local ranked=legendaryRecords(legendary)
        for _,entry in ipairs(legendary) do
            out[entry.bag]=out[entry.bag] or {};out[entry.bag][entry.slot]=ranked[entry.guid]
        end
        return out
    end
    local function payload(player)
        return gather(player,function(add)
            for slot=0,18 do add(255,slot,player:GetItemByPos(255,slot)) end
            for slot=23,38 do add(0,slot-22,player:GetItemByPos(255,slot)) end
            for bag=19,22 do for slot=0,35 do add(bag-18,slot+1,player:GetItemByPos(bag,slot)) end end
        end)
    end
    -- Bank, keyed straight into the client's own container lookup. The main
    -- bank is stock container -1 and server slots 39-66; the seven bank-bag
    -- slots are stock containers 5-11 and server bag positions 67-73 (each bag
    -- holds 36 items). A deposit or withdrawal fires the bank events below and
    -- the browser asks again, so nothing here is polled on a timer.
    local function bankPayload(player)
        return gather(player,function(add)
            for slot=39,66 do add(-1,slot-38,player:GetItemByPos(255,slot)) end
            for bag=67,73 do for slot=0,35 do add(bag-62,slot+1,player:GetItemByPos(bag,slot)) end end
        end)
    end
    -- Vendor buyback, server slots 74-85, shown as the merchant's items 1-12.
    -- A sold loose gem takes the same gem path the bags take; a returned item's
    -- rolled rows are read exactly as if it still sat in a bag.
    local function buybackPayload(player)
        local out=gather(player,function(add)
            for index=1,12 do add("buyback",index,player:GetItemByPos(255,73+index)) end
        end)
        return out.buyback or {}
    end
    -- Mail: the caller's own inbox, keyed [row][attachment] the way the client's
    -- GetInboxItem / SetInboxItem number them (both from 1). GetMailAttachment
    -- (core patch 0019) reads only this Player's mailbox, in the order the
    -- server lists it to the client, so no request names anyone else's mail.
    local function mailPayload(player)
        return gather(player,function(add)
            for row=1,50 do
                for attach=1,12 do add(row,attach,player:GetMailAttachment(row,attach)) end
            end
        end)
    end
    -- Trade: the window the caller is in. GetTradeItem(slot) is what the caller
    -- offered and GetTradeItem(slot,true) what the partner offered, both read
    -- through the caller's own trade, so a caller who is not trading gets
    -- nothing. Client slots 1-7 (7 is "will not be traded").
    local function tradePayload(player)
        local out=gather(player,function(add)
            for slot=0,6 do
                add("player",slot+1,player:GetTradeItem(slot))
                add("target",slot+1,player:GetTradeItem(slot,true))
            end
        end)
        return {player=out.player or {},target=out.target or {}}
    end
    -- Inspect: the target's worn items are real Item objects on the target's
    -- Player, so the same records() a bag item goes through serves them. Set
    -- ownership is the target's own worn pieces, not the viewer's.
    local function inspectPayload(target)
        if not next(bases) then load() end
        local found,guids,equipped={},{},{}
        for slot=0,18 do
            local item=target:GetItemByPos(255,slot)
            if item then
                local base=bases[item:GetEntry()]
                if base and not gems[item:GetEntry()] then
                    local guid=item:GetGUIDLow()
                    found[guid]={slot=slot,base=base,item=item};guids[#guids+1]=guid
                    if base.set~="" and counts(item) then equipped[base.set]=equipped[base.set] or {};equipped[base.set][base.name]=true end
                end
            end
        end
        local out={}
        for guid,record in pairs(records(found,guids,equipped)) do out[found[guid].slot]=record end
        return out
    end
    -- Called by dc_stash.lua. cells is any table whose values carry guid and
    -- entry; the result is keyed by guid, in the shape the client already draws.
    function DCItemTooltipRecords(cells)
        if not next(bases) then load() end
        local found,guids,out,legendary={},{},{},{}
        for _,source in pairs(cells or {}) do
            if source.entry and source.guid then
                -- A stash tab holds gems too, and they take the same gem path
                -- the bags take: no instance row to read, three lines to show.
                if legendaries[source.entry] then legendary[#legendary+1]={guid=source.guid,entry=source.entry}
                elseif gems[source.entry] then out[source.guid]=gemRecord(source.entry,source.guid)
                elseif (bases[source.entry] or shellEntries[source.entry]) and not found[source.guid] then
                    found[source.guid]={base=bases[source.entry]};guids[#guids+1]=source.guid
                end
            end
        end
        for guid,item in pairs(records(found,guids,nil)) do out[guid]=item end
        for guid,item in pairs(legendaryRecords(legendary)) do out[guid]=item end
        return out
    end
    -- Shared item links. Linking freezes a
    -- copy of the item's rows here and returns a random code; the link names the
    -- code and nothing else, no item and no character GUID. The code is the whole
    -- capability, so the copy still opens after the author logs off or rerolls
    -- the item. The store is this Lua state's memory and dies with the
    -- worldserver or a Lua reload; it is never written to a table.
    --
    -- Limits: relinking an unchanged item reuses its
    -- code; 10 NEW links per player per minute, then "Linking too fast"; at most
    -- 50000 live snapshots, the oldest dropped first.
    local snapshots, codeItem, byItem, rate = {}, {}, {}, {}
    local queue, head, tail = {}, 1, 1
    local RATE_LIMIT, RATE_WINDOW, MAX_SNAPSHOTS = 10, 60, 50000
    local function randomCode()
        local file=io.open("/dev/urandom","rb")
        if not file then return nil end
        local bytes=file:read(16)
        file:close()
        if not bytes or #bytes~=16 then return nil end
        local hex={}
        for i=1,#bytes do hex[i]=string.format("%02x",string.byte(bytes,i)) end
        return table.concat(hex)
    end
    -- 128 bits from the OS source, never math.random (its seed here is the
    -- clock). No weak fallback: a refused link is better than a guessable one.
    local function newCode()
        for _=1,8 do
            local code=randomCode()
            if code and not snapshots[code] then return code end
        end
    end
    -- Oldest first, amortized O(1). head and tail are explicit counters and the
    -- live length is tail-head; the length operator is never used here, because
    -- a dropped entry leaves a hole and # on a table with holes has no reliable
    -- boundary. The dead prefix is compacted once it grows, which is what keeps
    -- eviction O(1) instead of shifting the queue.
    local function dropOldest()
        if head>=tail then return nil end
        local code=queue[head];queue[head]=nil;head=head+1
        if head>1024 then
            local compact,n={},0
            for i=head,tail-1 do n=n+1;compact[n]=queue[i] end
            queue,tail,head=compact,n+1,1
        end
        local item=codeItem[code];codeItem[code]=nil
        if item and byItem[item] and byItem[item].code==code then byItem[item]=nil end
        snapshots[code]=nil
        return code
    end
    local function keep(record,itemGuid)
        local code=newCode()
        if not code then return nil end
        record.guid=nil -- the link and the copy it opens never name the sender's item
        snapshots[code]=record
        codeItem[code]=itemGuid
        queue[tail]=code;tail=tail+1
        while tail-head>MAX_SNAPSHOTS do if not dropOldest() then break end end
        return code
    end
    -- A NEW link only; a reused code does not spend the allowance. The window is
    -- per player, in whole seconds.
    --
    -- Security G10: the per-player lists used to live forever, one table per
    -- GUID that ever attempted a link. Sweep stale ids on a counter so the table
    -- is bounded by players active in the last window, not by every player ever.
    local linkCalls = 0
    local function pruneRate(now)
        linkCalls = linkCalls + 1
        if linkCalls < 256 then return end
        linkCalls = 0
        for id,times in pairs(rate) do
            local newest = times[#times]
            if not newest or now - newest >= RATE_WINDOW then rate[id] = nil end
        end
    end
    local function mayLink(player)
        local id=player:GetGUIDLow()
        local now=os.time()
        pruneRate(now)
        local kept={}
        for _,at in ipairs(rate[id] or {}) do if now-at<RATE_WINDOW then kept[#kept+1]=at end end
        if #kept>=RATE_LIMIT then rate[id]=kept;return false end
        kept[#kept+1]=now;rate[id]=kept;return true
    end
    local function carried(player,guid)
        local function at(bag,slot)
            local item=player:GetItemByPos(bag,slot)
            if item and item:GetGUIDLow()==guid then return item end
        end
        for slot=0,18 do local item=at(255,slot); if item then return item end end
        for slot=23,38 do local item=at(255,slot); if item then return item end end
        for bag=19,22 do
            local container=player:GetItemByPos(255,bag)
            if container then
                for slot=0,container:GetBagSize()-1 do local item=at(bag,slot); if item then return item end end
            end
        end
    end
    local function refuse(player,message)
        AIO.Handle(player,CHANNEL,"LinkResult",{ok=false,message=message})
    end
    -- The chat link is a native item link: the core drops a message whose link tag it does not know, and checks
    -- an item link's colour against the template's Quality and its text against the template's name, so the reply names both.
    local function reply(player,record,code)
        local row=WorldDBQuery("SELECT Quality,name FROM item_template WHERE entry="..tostring(record.entry))
        if not row then refuse(player,"Item links are unavailable right now.");return end
        AIO.Handle(player,CHANNEL,"LinkResult",{ok=true,code=code,name=record.name,rarity=record.rarity,quality=record.quality,
            entry=record.entry,itemQuality=row:GetUInt32(0),itemName=row:GetString(1)})
    end
    -- The item's own rolled identity. Durability and set ownership are left out:
    -- they change without the item changing, and neither is what the link names.
    local function signature(record)
        local parts={tostring(record.entry),record.rarity or "",record.bound and "1" or "0",record.rolledPower or ""}
        for _,a in ipairs(record.affixes or {}) do
            parts[#parts+1]=table.concat({tostring(a.seq),a.id or "",tostring(a.value),tostring(a.min),
                tostring(a.max),a.kind or "",a.rerolled and "1" or "0",tostring(a.parent),tostring(a.gemEntry),tostring(a.legendaryRank)},":")
        end
        return table.concat(parts,"|")
    end
    local function build(player,guid,base,item)
        local found={[guid]={base=base,item=item}}
        local equipped={}
        for slot=0,18 do
            local worn=player:GetItemByPos(255,slot)
            if worn then
                local b=bases[worn:GetEntry()]
                if b and b.set~="" and counts(worn) then equipped[b.set]=equipped[b.set] or {};equipped[b.set][b.name]=true end
            end
        end
        local record=records(found,{guid},equipped)[guid]
        if not record or record.unidentified then return nil end
        return record
    end
    -- Ownership is the server's own: a carried item, or an item in the caller's
    -- account/mode stash. A client-sent GUID is never trusted on its own.
    local function stashEntry(player,guid)
        if not (DCAccount and DCAccount.Principal) then return nil end
        local account,mode=DCAccount.Principal(player)
        if not account then return nil end
        local row=CharDBQuery(("SELECT ii.itemEntry FROM dc_account_stash_item s "
            .."JOIN item_instance ii ON ii.guid=s.item_guid "
            .."WHERE s.account_id=%d AND s.mode='%s' AND s.item_guid=%d"):format(account,mode,guid))
        return row and row:GetUInt32(0) or nil
    end
    local function owned(player,guid)
        local item=carried(player,guid)
        if item then
            local base=bases[item:GetEntry()]
            return base and build(player,guid,base,item) or nil
        end
        local entry=stashEntry(player,guid)
        if entry and bases[entry] then return build(player,guid,bases[entry],nil) end
    end
    -- Security G1: owned() reads the stash before mayLink's own link rate is asked; drop a
    -- flood first.
    function handlers.Link(player,guid)
        if not DCThrottle.Allow(player,"tooltip:link",5,10) then return end
        guid=tonumber(guid)
        local record=guid and owned(player,guid)
        if not record then refuse(player,"Only a rolled item you are carrying or have in your stash can be linked.");return end
        local sig=signature(record)
        local cached=byItem[guid]
        if cached and cached.signature==sig and snapshots[cached.code] then
            reply(player,record,cached.code)
            return
        end
        if not mayLink(player) then refuse(player,"Linking too fast");return end
        local code=keep(record,guid)
        if not code then refuse(player,"Item links are unavailable right now.");return end
        byItem[guid]={code=code,signature=sig}
        reply(player,record,code)
    end
    function handlers.Snapshot(player,code)
        if type(code)~="string" or #code>64 or not code:match("^[0-9a-f]+$") then return end
        AIO.Handle(player,CHANNEL,"SnapshotResult",code,snapshots[code] or false)
    end
    -- A screen that shows rolled items outside the bags asks here when it opens
    -- (bank, buyback, inspect, mail, trade); there is no timer behind it. The server only
    -- ever reads containers it holds - for inspect, the worn items of the
    -- Player the caller is currently selecting - so a forged request cannot
    -- make it emit a record for an item the caller does not hold.
    -- Security G1: every context reads each slot's records; drop a flood. The client
    -- coalesces its frame events into one ask per context (the contextWatcher below).
    function handlers.Context(player,name,guid)
        if not DCThrottle.Allow(player,"tooltip:context",5,10) then return end
        if name=="bank" then
            AIO.Handle(player,CHANNEL,"Context",{name="bank",items=bankPayload(player)})
        elseif name=="buyback" then
            AIO.Handle(player,CHANNEL,"Context",{name="buyback",items=buybackPayload(player)})
        elseif name=="inspect" then
            local want=tonumber(guid)
            local target=want and player:GetSelection()
            -- The target must be the caller's own current selection, be a
            -- Player object with an inventory, be in range, and be visible to
            -- the caller; anything else is dropped with no reply, so no addon
            -- can pull an arbitrary character's rolls. ALE's
            -- Player:IsVisibleForPlayer is named from the wrong side (it calls
            -- IsVisibleGloballyFor(target), i.e. "is self visible to the
            -- argument"), so the visibility test is asked on the target, with
            -- the caller as the argument: target visible to caller.
            if target and target.GetItemByPos and target:GetGUIDLow()==want
                and player:IsWithinDistInMap(target, INSPECT_DISTANCE, false)
                and target:IsVisibleForPlayer(player) then
                AIO.Handle(player,CHANNEL,"Context",{name="inspect",guid=want,items=inspectPayload(target)})
            end
        elseif name=="mail" then
            -- The readers exist once core patch 0019 is built in; before that the
            -- request is dropped and mail keeps its base shell.
            if player.GetMailAttachment then
                AIO.Handle(player,CHANNEL,"Context",{name="mail",items=mailPayload(player)})
            end
        elseif name=="trade" then
            if player.GetTradeItem then
                AIO.Handle(player,CHANNEL,"Context",{name="trade",items=tradePayload(player)})
            end
        end
    end
    -- Blacksmith recipe preview: what one craft of a catalogue recipe will carry, drawn by decorate() like any rolled
    -- item. The roller is C++ (StageRoll/CountsFor, dc_items.cpp), so this mirrors its decision from the same tables
    -- and shows only what the roll would really write (GitHub #94):
    --   wanted = CountsFor(rarity): dc_tunable loot/full_roll_* (Rare/Legendary/Set) or loot/magic_* (Magic); a
    --            missing row answers 0, as Tunables::Get does.
    --   fixed  = base presets in preset order; a preset the pool has no row for rolls in the item's own range
    --            (dc_item_preset_range), as PlanRoll falls back to itemPresets, and one outside both is skipped
    --   random = min(wanted_kind - fixed_kind, pool rows of that kind still free)
    -- A shield's required block lines are taken outside the budget, as StageRoll does; so is a Source's, Mojo's,
    -- Phylactery's or Totem's +X-Y Damage (DamageOffhand), no other offhand rolling the pool's wpnphy rows
    -- (OffhandDamageAffix); so is a Quiver's Attack Speed Increase, taken after it (SpeedQuiver), no other offhand
    -- rolling the pool's ias rows (OffhandSpeedAffix).
    local PREVIEW_SHIELD={Shield=true,["Crusader Shield"]=true}
    local PREVIEW_DAMAGE_OFFHAND={Source=true,Mojo=true,Phylactery=true,Totem=true}
    local PREVIEW_BLOCK={baseblock=true,block=true,blockamount=true,blockamountdelta=true}
    local PREVIEW_SHIELD_BLOCK={baseblock=true,blockamount=true,blockamountdelta=true}
    local PREVIEW_MAIN={str="Strength",dex="Dexterity",int="Intelligence"}
    local previewPools,previewSkill,previewClassByWow,previewStatByClass={},{},{},{}
    local function previewSplit(text)
        local out={}
        for field in tostring(text or ""):gmatch("[^;]+") do out[#out+1]=field end
        return out
    end
    local function previewBracket(rarity)
        return (rarity=="legendary" or rarity=="set" or rarity=="ethereal") and "legendary" or "rare"
    end
    local function previewQuote(text) return "'"..tostring(text or ""):gsub("'","''").."'" end
    local function previewPool(slot,bracket)
        local key=slot.."\t"..bracket
        if not previewPools[key] then
            local out={}
            local rows=WorldDBQuery("SELECT affix_id,affix_name,kind,value_min,value_max,is_percent,display_order,value_min2,value_max2,weapon_class "
                .."FROM dc_affix_pool WHERE slot="..previewQuote(slot).." AND item_level_bracket="..previewQuote(bracket))
            if rows then repeat
                -- Eluna reads a NULL DOUBLE field as 1.0 (Field.cpp GetDefaultValue<double>), so a
                -- NULL value_min2/value_max2 must be tested with IsNull, never with GetDouble alone:
                -- a single-part affix carries no second bracket and keeps D3's one-range form.
                out[#out+1]={id=rows:GetString(0),name=rows:GetString(1),kind=rows:GetString(2),
                    min=rows:GetDouble(3),max=rows:GetDouble(4),percent=rows:GetUInt32(5)~=0,order=rows:GetUInt32(6),
                    min2=(not rows:IsNull(7)) and rows:GetDouble(7) or nil,
                    max2=(not rows:IsNull(8)) and rows:GetDouble(8) or nil,
                    weapon_class=rows:GetString(9)}
            until not rows:NextRow() end
            previewPools[key]=out
        end
        return previewPools[key]
    end
    -- dc_items_data.cpp PoolFor, as the roller, the Mystic and a stored item read it: the slot's rows, then the base's own type's ("<slot>:<type>").
    local function previewPoolFor(slot,type,bracket)
        local out={}
        for _,key in ipairs({slot,slot..":"..tostring(type or "")}) do for _,row in ipairs(previewPool(key,bracket)) do out[#out+1]=row end end
        return out
    end
    -- A preset the pool has no row for rolls in the item's OWN range: PlanRoll falls back to itemPresets
    -- (dc_item_preset_range, filled by item_preset_ranges.csv); this reads the same table for the same entry and
    -- bracket, so the preview cannot promise fewer fixed lines than the roll writes. The sheet carries no second
    -- bracket and no weapon class, so those fields stay absent as a single-part pool row's do.
    local previewItemPresets={}
    local function previewItemPreset(entry,bracket)
        local key=entry.."\t"..bracket
        if not previewItemPresets[key] then
            local out={}
            local rows=WorldDBQuery("SELECT affix_id,affix_name,kind,value_min,value_max,is_percent,display_order "
                .."FROM dc_item_preset_range WHERE entry="..entry.." AND item_level_bracket="..previewQuote(bracket))
            if rows then repeat
                out[#out+1]={id=rows:GetString(0),name=rows:GetString(1),kind=rows:GetString(2),
                    min=rows:GetDouble(3),max=rows:GetDouble(4),percent=rows:GetUInt32(5)~=0,order=rows:GetUInt32(6),
                    weapon_class=""}
            until not rows:NextRow() end
            previewItemPresets[key]=out
        end
        return previewItemPresets[key]
    end
    -- G1: the ONE sourced weapon type -> damage bracket map (dc_weapon_class). Both this mirror
    -- and the roller read it, so neither keeps its own type list.
    local previewWeaponClasses={}
    local function previewWeaponClass(weaponType)
        if previewWeaponClasses[weaponType]==nil then
            local found=WorldDBQuery("SELECT weapon_class FROM dc_weapon_class WHERE weapon_type="..previewQuote(weaponType))
            previewWeaponClasses[weaponType]=found and found:GetString(0) or ""
        end
        return previewWeaponClasses[weaponType]
    end
    -- dc_items.cpp SkillChoices: a pool entry that names a skill group rolls only when the
    -- affix class has a choice in it (dc_skill_affix rows for the class).
    local function previewSkills()
        if not previewSkill.all then
            local all,byClass={},{}
            local rows=WorldDBQuery("SELECT group_id,class_id FROM dc_skill_affix")
            if rows then repeat
                local group,class=rows:GetString(0),rows:GetUInt32(1)
                all[group]=true;byClass[group]=byClass[group] or {};byClass[group][class]=true
            until not rows:NextRow() end
            previewSkill={all=all,byClass=byClass}
        end
        return previewSkill
    end
    -- One catalogue class (dc_class_map id + dc_class_primary_stats main stat), cached by key, and
    -- the class a WoW class plays, cached by WoW class id.
    local function previewClassByKey(key)
        if key=="" then return {key="",id=0,stat=nil} end
        if not previewStatByClass[key] then
            local id,stat
            local rows=WorldDBQuery("SELECT class_id FROM dc_class_map WHERE class_key="..previewQuote(key))
            if rows then id=rows:GetUInt32(0) end
            local found=WorldDBQuery("SELECT primary_stat FROM dc_class_primary_stats WHERE class="..previewQuote(key))
            if found then stat=found:GetString(0) end
            previewStatByClass[key]={key=key,id=id or 0,stat=stat}
        end
        return previewStatByClass[key]
    end
    local function previewClass(wowClass)
        if not previewClassByWow[wowClass] then
            local key=""
            local rows=WorldDBQuery("SELECT class_key FROM dc_class_map WHERE wow_class_id="..tostring(wowClass))
            if rows then key=rows:GetString(0) end
            previewClassByWow[wowClass]=previewClassByKey(key)
        end
        return previewClassByWow[wowClass]
    end
    local function previewTunable(name)
        return tonumber(DCTunables and DCTunables.Get and DCTunables.Get("loot",name)) or 0
    end
    -- The record for one recipe, or nil when the catalogue or its base item is not there.
    local function previewRecord(recipeId,player)
        local row=WorldDBQuery("SELECT output_entry,rarity,required_level,enabled FROM dc_blacksmith_catalog WHERE id="..recipeId)
        if not row then return nil end
        local entry,rarity,required=row:GetUInt32(0),row:GetString(1),row:GetUInt32(2)
        local base=bases[entry]
        if not base then return nil end
        local crafter=previewClass(player and player:GetClass() or 0)
        local info=WorldDBQuery("SELECT preset_affixes,type,designated_class FROM dc_base_item WHERE entry="..entry)
        local presets,type,designated="",nil,""
        if info then presets,type,designated=info:GetString(0),info:GetString(1),info:GetString(2) end
        -- Rule 3, dc_roll_class.h AffixClass: a class-only item's skill affixes and main stat belong
        -- to its own class, not to whoever crafts it; anything else rolls the crafter's class.
        local class=(designated~="" ) and previewClassByKey(designated) or crafter
        local shield=PREVIEW_SHIELD[type]==true
        local damageOffhand=PREVIEW_DAMAGE_OFFHAND[type]==true
        local speedQuiver=type=="Quiver"
        local groups=previewSkills()
        -- G1: a weapon reads only its own damage bracket's rows (dc_weapon_class); a non-weapon
        -- affix carries no weapon_class and is always eligible.
        local weaponClass=previewWeaponClass(type)
        local pool=previewPoolFor(base.slot,type,previewBracket(rarity))
        local function eligible(p)
            if p.weapon_class~="" and p.weapon_class~=weaponClass then return false end
            if PREVIEW_BLOCK[p.id] and not shield then return false end
            if base.slot=="offhand" and p.id=="wpnphy" and not damageOffhand then return false end
            if base.slot=="offhand" and p.id=="ias" and not speedQuiver then return false end
            if groups.all[p.id] and not (groups.byClass[p.id] and groups.byClass[p.id][class.id]) then return false end
            return true
        end
        local function find(id)
            for _,p in ipairs(pool) do if p.id==id then return p end end
        end
        -- The roller's fallback. A preset the pool has no row for is the item's
        -- own line (dc_item_preset_range) and needs no pool eligibility: PlanRoll takes it as it
        -- finds it in itemPresets, so a shield's block line or an elemental line stays the item's own.
        local ownPresets=previewItemPreset(entry,previewBracket(rarity))
        local function findOwn(id)
            for _,p in ipairs(ownPresets) do if p.id==id then return p end end
        end
        local used,fixed={}, {}
        local function add(p,kind)
            local name,percent=p.name,p.percent
            if p.id=="mainstat" then
                local stat=class.stat or "str"
                local id=({Strength="str",Dexterity="dex",Intelligence="int"})[stat] or stat
                name=PREVIEW_MAIN[id] or stat
            end
            -- G1: min2/max2 are set only when the pool row really carries a second bracket, so a
            -- single-part affix keeps D3's one-range form (0 is truthy in Lua).
            fixed[#fixed+1]={seq=#fixed,id=p.id,name=name,percent=percent,
                kind=(p.id=="sockets") and "socket" or p.kind,
                order=p.order,min=p.min,max=p.max,
                min2=(p.min2 and p.min2>0) and p.min2 or nil,max2=(p.max2 and p.max2>0) and p.max2 or nil,
                value=p.min,fixed=true,socket=p.id=="sockets"}
        end
        if shield then
            for _,p in ipairs(pool) do
                if eligible(p) and PREVIEW_SHIELD_BLOCK[p.id] and not used[p.id] then used[p.id]=true;add(p,"preset") end
            end
        end
        if damageOffhand then
            for _,p in ipairs(pool) do
                if p.kind=="primary" and p.id=="wpnphy" and eligible(p) and not used[p.id] then used[p.id]=true;add(p,"preset") end
            end
        end
        if speedQuiver then
            for _,p in ipairs(pool) do
                if p.kind=="primary" and p.id=="ias" and eligible(p) and not used[p.id] then used[p.id]=true;add(p,"preset") end
            end
        end
        local fixedPrimary,fixedSecondary=0,0
        -- G1: the weapon elemental affixes are one exclusive group; only the first is taken,
        -- exactly as PlanRoll does (dc_items.cpp), so the mirror cannot drift.
        local weaponDamage=false
        for _,id in ipairs(previewSplit(presets)) do
            local p=find(id)
            local own=false
            if not p then p=findOwn(id); own=p~=nil end
            if p and (own or eligible(p)) and not used[id] and not (weaponDamage and p.weapon_class~="") then
                used[id]=true;add(p,"preset")
                if p.weapon_class~="" then weaponDamage=true end
                if p.kind=="secondary" then fixedSecondary=fixedSecondary+1 else fixedPrimary=fixedPrimary+1 end
            end
        end
        local totalPrimary,totalSecondary
        if rarity=="magic" then
            totalPrimary,totalSecondary=previewTunable("magic_primary_affixes"),previewTunable("magic_secondary_affixes")
        else
            totalPrimary,totalSecondary=previewTunable("full_roll_primary_affixes"),previewTunable("full_roll_secondary_affixes")
        end
        local function free(kind)
            local count=0
            for _,p in ipairs(pool) do
                if p.kind==kind and not used[p.id] and eligible(p) and not (weaponDamage and p.weapon_class~="") then
                    count=count+1
                end
            end
            return count
        end
        local randomPrimary=math.min(math.max(0,totalPrimary-fixedPrimary),free("primary"))
        local randomSecondary=math.min(math.max(0,totalSecondary-fixedSecondary),free("secondary"))
        table.sort(fixed,function(a,b) if a.order~=b.order then return a.order<b.order end;return a.seq<b.seq end)
        return {preview=true,id=recipeId,guid="recipe:"..recipeId,entry=entry,name=base.name,rarity=rarity,
            level=required,sell=base.sell,power=base.power,flavour=base.flavour,affixes=fixed,
            set=sets[base.set],owned={},randomCount=randomPrimary+randomSecondary,randomPrimary=randomPrimary,
            randomSecondary=randomSecondary}
    end
    -- Hovering a Blacksmith recipe result asks for its preview. Read-only catalogue data, so
    -- the guards are a live player and the bucket (no range). The client caches a preview
    -- per recipe, so play asks once per recipe; Security G1: previewRecord() queries the
    -- world database, so a flood is dropped.
    function handlers.Preview(player,id)
        id=tonumber(id)
        if not id or not player or not player.IsInWorld or not player:IsInWorld() then return end
        if not DCThrottle.Allow(player,"tooltip:preview",5,10) then return end
        local record=previewRecord(id,player)
        if record then AIO.Handle(player,CHANNEL,"PreviewResult",record) end
    end
    -- AIO's client asks for an init once per client process (ADDON_LOADED), not per
    -- login, so AddOnInit alone leaves a relog running on whatever the previous
    -- login cached - or on nothing at all. Push at login instead: the core has
    -- loaded this character's inventory long before the ON_LOGIN hook fires
    -- (CharacterHandler.cpp LoadFromDB, then OnPlayerLogin), and a block that
    -- arrives before the client's AIO has inited is queued and replayed by AIO.
    local function push(player,trigger)
        if player then AIO.Handle(player,CHANNEL,"Set",payload(player),trigger) end
    end
    -- Security G1: push() reads this character's item rows; drop a flood.
    function handlers.Refresh(player)
        if DCThrottle.Allow(player, "tooltip:refresh", 5, 10) then push(player,"refresh") end
    end
    RegisterPlayerEvent(3,function(_,player) push(player,"login") end)   -- login
    AIO.AddOnInit(function(msg,player) if player then msg:Add(CHANNEL,"Set",payload(player),"init") end end)
    return
end

local handlers=AIO.AddHandlers(CHANNEL,{})
local cache,byGuid={},{}
-- Bank, buyback, inspect, mail and trade records arrive on demand when their
-- frame opens, kept apart from the bags so a bag refresh cannot drop them and a
-- context refresh cannot drop the bags. inspect is keyed by the target's low
-- GUID, mail by [inbox row][attachment], trade by side then slot 1-7.
local contexts={bank={},buyback={},inspect={},mail={},trade={player={},target={}}}
local source,count="none",0
function handlers.Set(_,payload,trigger)
    cache=payload or {};byGuid={};count=0
    for _,bag in pairs(cache) do for _,item in pairs(bag) do byGuid[item.guid]=item;count=count+1 end end
    source=trigger or "unknown"
    -- The Torment sheet draws a worn slot's border from the rolled rarity in this
    -- cache, so it asks to be told when the records change (Inventory.lua).
    if DCOnItemRecords then DCOnItemRecords() end
end
-- The rolled rarity ("normal", "magic", "rare", "legendary", "set") of the item at
-- bag/slot in the client's own bag-and-paper-doll cache, or nil when no record is
-- held (255 is the equipment; the slot is the 0-based equipment slot).
function DCItemRarity(bag,slot)
    local record=cache[bag] and cache[bag][slot]
    return record and record.rarity or nil
end
-- primal is not a rarity: it is a Primal Ancient's name colour, the stock RED_FONT_COLOR the tooltip border also uses.
-- A ground plate's triple names the Primal's own plate level as "primal", so its label reads it too.
local colours={normal={1,1,1},magic={.4,.6,1},rare={1,1,0},legendary={1,.5,0},set={0,1,0},primal={1,.1,.1}}
-- The one copy of the D3 rarity palette on the client. dc_ground_plates.lua
-- colours its ground-loot labels out of this table rather than keeping a second
-- copy that could drift.
DCRARITY=colours
-- 12-ui U4: the Torment addon's one shared formatter. The
-- local grouping only runs if the addon is missing, and the server already tells
-- the player when it is.
local function goldText(value)
    if Diablocraft and Diablocraft.Econ then return Diablocraft.Econ.Gold(value) end
    local out,more=tostring(value or 0),1
    while more>0 do out,more=out:gsub("^(%-?%d+)(%d%d%d)","%1,%2") end
    return out
end
local function format(affix)
    local suffix=affix.percent and "%" or ""
    -- A fixed affix in a Blacksmith preview has no rolled value yet, so it shows D3's range
    -- form instead of a number (G7): +[10 - 12]% Movement Speed. A two-part range (G1's
    -- weapon elemental damage) reads +[a - b]-[c - d] Fire Damage.
    if affix.fixed then
        if affix.min2 and affix.max2 then
            return string.format("+[%g - %g]-[%g - %g]%s %s",affix.min,affix.max,affix.min2,affix.max2,suffix,affix.name or affix.id)
        end
        return string.format("+[%g - %g]%s %s",affix.min,affix.max,suffix,affix.name or affix.id)
    end
    -- G1: a rolled weapon elemental affix shows D3's two-part form "+X-Y <Element> Damage"
    -- (value2 is the second endpoint the roller stored).
    if affix.value2 and affix.value2>0 then
        local two=string.format("+%g-%g%s %s",affix.value,affix.value2,suffix,affix.name or affix.id)
        if affix.rerolled then two=two.."  (enchanted)" end
        return two
    end
    local line=string.format("+%g%s %s",affix.value,suffix,affix.name or affix.id)
    if affix.max>affix.min then line=line..string.format("  [%g%s–%g%s]",affix.min,suffix,affix.max,suffix) end
    if affix.rerolled then line=line.."  (enchanted)" end
    -- A fixed (preset) stat reads exactly like a rolled one, on every rarity: no tag.
    return line
end
-- The one copy of the affix line formatter on the client, published the way DCRARITY is:
-- dc_crafting.lua's Mystic window words the bridge's L, C and V records (id, value, value2, min,
-- max, min2, max2) with it, so a property reads the same in the window as in the item tooltip
-- (docs/contracts/mystic-enchant-messages.md section 1a - never a second copy of the wording).
-- Read lazily, at the moment a row is drawn: AIO file load order is not ours to depend on.
DCAFFIXLINE=format
-- An empty socket is a PRISMATIC socket, drawn with the stock colourless socket
-- art and named with the client's own word for it, as a reference screenshot
-- shows. It used to read "Empty Socket (any gem)" beside a red
-- icon, because the path probed here was UI-EmptySocket-Prismatic, which this
-- client does not ship.
--
-- Checked against the pinned client's own archives rather than remembered.
-- WoW Client/Data/enUS/locale-enUS.MPQ carries exactly five, and no -Prismatic:
--   UI-EmptySocket.blp       DXT1 16x16, mean lit RGB 117,117,117 - colourless
--   UI-EmptySocket-Red.blp   ... 130,58,58 - red
--   UI-EmptySocket-Blue / -Yellow / -Meta
-- and its GlobalStrings.lua carries EMPTY_SOCKET_NO_COLOR = "Prismatic Socket",
-- the client's own localised name for that art. Neither the picture nor the
-- words are ours, which keeps to the rule: no invented art.
--
-- Still probed before use, the way the panel kit tests its own art: a path
-- that does not resolve renders as a box inside a |T|t
-- escape, and no icon at all is better than that. SetTexture answers false when
-- the file is missing, and nil when there is no answer, which must not read as a
-- failure.
local socketIcon=""
do
    local host=CreateFrame and CreateFrame("Frame")
    local probe=host and host.CreateTexture and host:CreateTexture()
    local path="Interface\\ItemSocketingFrame\\UI-EmptySocket"
    if probe and probe:SetTexture(path)~=false then socketIcon="|T"..path..":16|t " end
end
-- The client's own string, so a non-enUS client reads its own word for it.
local SOCKET_LABEL=type(_G.EMPTY_SOCKET_NO_COLOR)=="string" and _G.EMPTY_SOCKET_NO_COLOR~=""
    and _G.EMPTY_SOCKET_NO_COLOR or "Prismatic Socket"
-- A loose gem: its three effects at once, one per slot class, because which one
-- applies is not decided until it is socketed.
-- A legendary gem's base power at its rank and its rank-25 power, grey with a red "(Requires Rank 25)" below
-- rank 25. Loose (gemBody) and socketed (the socket line) draw the same two lines.
local function legendaryPower(tooltip,power,bonus,rank)
    local r,g,b=unpack(colours.legendary)
    if power and power~="" then tooltip:AddLine(power,r,g,b,true) end
    if bonus and bonus~="" then
        if (rank or 0)>=25 then tooltip:AddLine(bonus,r,g,b,true)
        else tooltip:AddLine(bonus.." |cffff2020(Requires Rank 25)|r",.5,.5,.5,true) end
    end
end
local function gemBody(tooltip,item)
    -- A legendary gem (in a D3 capture's order) has no slot effects: "Legendary Gem"
    -- and its rank, where it fits, Unique Equipped, the account binding and the template's sell value.
    -- Then the base power at the gem's rank and the rank-25 power, grey with a red "(Requires Rank 25)" below
    -- rank 25. The flavour text is the template's description, the stock gold line.
    if item.legendary then
        local r,g,b=unpack(colours.legendary)
        tooltip:AddDoubleLine("Legendary Gem","Rank "..(item.rank or 0),r,g,b,.8,.8,.8)
        tooltip:AddLine("Can be inserted into "..(item.fits or "jewelry").." with sockets.",1,1,1,true)
        legendaryPower(tooltip,item.basePower,item.bonus,item.rank)
        tooltip:AddLine("Unique Equipped",.8,.8,.8)
        tooltip:AddLine("Bind to Account on Pickup",.8,.8,.8)
        tooltip:AddLine("Sell Value: "..goldText(item.sell).." gold",1,1,1)
        return
    end
    tooltip:AddLine("Gem",.8,.8,.8)
    for _,line in ipairs(item.lines or {}) do
        tooltip:AddLine(string.format("%s: +%g%s %s",line.slot,line.value,line.percent and "%" or "",line.name),
            .45,.72,1,true)
    end
    if not item.lines or #item.lines==0 then tooltip:AddLine("This gem has no recorded effects.",.7,.7,.7) end
end
local function footerLine(value)
    if not value then return false end
    return value:find("Requires Level",1,true) or value:find("Durability",1,true) or value:find("Sell Price",1,true)
        or value:find("Binds",1,true) or value:find("bound",1,true) or value:find("Bound",1,true)
end
-- WoW's shift-compare stat diff ("If you replace this item") diffs WoW stats; our items have none.
local compareMarkers={"If you replace this item","If you replace both items"}
for _,global in ipairs({"ITEM_DELTA_DESCRIPTION","ITEM_DELTA_DUAL_WIELD_DESCRIPTION"}) do
    local text=_G[global]
    if type(text)=="string" then compareMarkers[#compareMarkers+1]=(text:gsub("[:%s]+$","")) end
end
local function compareLine(value)
    if not value then return false end
    for _,marker in ipairs(compareMarkers) do if marker~="" and value:find(marker,1,true) then return true end end
    return false
end
-- The stock client's own socketing hint, "<Shift Right Click to Socket>" in green (the client draws it from C++;
-- the string is the global ITEM_SOCKETABLE). Our sockets are affix rows the client does not know, so the addon draws
-- it once, under the last socket line, for every rolled item with a socket, filled or empty; a copy the client did draw is never taken from the native
-- lines, so it cannot show twice.
local SOCKETABLE=_G.ITEM_SOCKETABLE or "<Shift Right Click to Socket>"
local function capture(tooltip)
    -- A tooltip this file already decorated holds the D3 lines we drew. If the
    -- client reuses it for another item without firing OnTooltipCleared,
    -- reading those lines back as if they were stock would draw each of them a
    -- second time. Only a cleared tooltip is captured; a still-decorated one
    -- contributes no native lines, which is wrong-but-quiet rather than twice.
    if tooltip.dcGuid~=nil then return {} end
    local native={};local name=tooltip:GetName()
    for i=2,tooltip:NumLines() do
        local l=_G[name.."TextLeft"..i];local r=_G[name.."TextRight"..i]
        local left,right=l and l:GetText(),r and r:GetText()
        if compareLine(left) or compareLine(right) then break end
        -- The colour the client drew each side in goes with it (UI fixes row 7): a red line
        -- the player cannot use stays red, the green Use line stays green.
        if left and left~=SOCKETABLE and not footerLine(left) and not footerLine(right) then
            native[#native+1]={left,right,colour=l.GetTextColor and {l:GetTextColor()} or nil,
                rightColour=r and r.GetTextColor and {r:GetTextColor()} or nil}
        end
    end
    return native
end
-- True when a captured native line is the item's own description: the client
-- draws item_template.description in quotes and gold, and the server wrote it as
-- the power and the flavour joined by LF (generate_sql.py). The addon draws
-- both itself, in the D3 layout
-- and colours, so the native copy is left out of the redraw and nothing shows
-- twice. The reference text may carry CRLF, hence the "\r" strip.
local function isDescription(item,line)
    for _,text in ipairs({item.power or "",item.flavour or ""}) do
        text=text:gsub("\r","")
        if text~="" then
            for _,side in ipairs(line) do if side:gsub("\r",""):find(text,1,true) then return true end end
        end
    end
    return false
end
-- The client's own "<Made by %s>" (ITEM_CREATED_BY). A made item's maker is drawn from its record instead
-- (under the quality tag, and still there after the maker is deleted), so the native copy is left out.
local function madeByText(name) return (_G.ITEM_CREATED_BY or "<Made by %s>"):format(name) end
local function isMadeBy(line)
    local pattern="^"..(_G.ITEM_CREATED_BY or "<Made by %s>"):gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]","%%%0"):gsub("%%%%s",".+").."$"
    return line[1]~=nil and line[1]:find(pattern)~=nil
end
-- A captured colour, or white when the region gave none.
local function nativeColour(colour)
    if colour and colour[1] then return colour[1],colour[2],colour[3] end
    return 1,1,1
end
-- The record's quality (docs/contracts/item-link-messages.md "quality"); normal has no tag line.
local qualityTags={ancient="Ancient",primal="Primal Ancient"}
local busy=false
local function decorate(tooltip,item,force)
    if busy then return end
    if tooltip.dcGuid==item.guid and not force then return end
    local native=tooltip.dcGuid==item.guid and tooltip.dcNative or capture(tooltip)
    busy=true
    -- dcQualityTier is what TooltipBorder.lua reads for the Primal red border.
    tooltip:ClearLines();tooltip.dcGuid=item.guid;tooltip.dcNative=native;tooltip.dcQualityTier=item.quality
    local colour=colours[item.rarity] or colours.normal
    -- A Primal Ancient's name is red whatever its rarity; Normal and Ancient keep the rarity colour.
    tooltip:AddLine(item.name,unpack(item.quality=="primal" and colours.primal or colour))
    -- Directly under the name, in the stock item-tag green, as retail's Heroic / Warforged tags.
    local tag=qualityTags[item.quality]
    if tag then local green=_G.GREEN_FONT_COLOR;tooltip:AddLine(tag,green.r,green.g,green.b) end
    local made=item.madeBy and item.madeBy~=""
    if made then local green=_G.GREEN_FONT_COLOR;tooltip:AddLine(madeByText(item.madeBy),green.r,green.g,green.b) end
    for _,line in ipairs(native) do
        if isDescription(item,line) or (made and isMadeBy(line)) then
            -- drawn below from the addon's own copy, or above from the record
        else
            local lr,lg,lb=nativeColour(line.colour)
            if line[2] and line[2]~="" then tooltip:AddDoubleLine(line[1],line[2],lr,lg,lb,nativeColour(line.rightColour))
            else tooltip:AddLine(line[1],lr,lg,lb,true) end
        end
    end
    if item.gem then gemBody(tooltip,item);tooltip:Show();busy=false;return end
    -- "Unidentified" in the rarity's colour, the slot type, and nothing else.
    -- The slot line and the green Use line are the client's own, kept above in
    -- `native`; the server never sends what the item will become.
    if item.unidentified then tooltip:Show();busy=false;return end
    -- The rarity line reads Ancient / Primal Ancient on those items (the tag's words), Legendary / Set otherwise.
    tooltip:AddLine(qualityTags[item.quality] or (item.rarity or "normal"):gsub("^%l",string.upper),unpack(colour))
    for _,kind in ipairs({"primary","secondary"}) do
        local any=false
        for _,affix in ipairs(item.affixes) do if affix.kind==kind then any=true;break end end
        if any then
            tooltip:AddLine(" ");tooltip:AddLine(kind=="primary" and "Primary" or "Secondary",.8,.8,.8)
            for _,affix in ipairs(item.affixes) do if affix.kind==kind then tooltip:AddLine(format(affix),.45,.72,1,true) end end
        end
    end
    -- Caldesann's Despair's row (cube-messages.md "The augment row"): one more line below the item's own.
    for _,affix in ipairs(item.affixes) do
        if affix.kind=="augment" then tooltip:AddLine(format(affix).." (Augmented)",.45,.72,1,true) end
    end
    -- A Blacksmith preview promises how many properties the roll will fill (G2); the count
    -- is the server's, worked out from what the roller really does, never a stored guess.
    if item.randomCount and item.randomCount>0 then
        tooltip:AddLine(string.format("+%d Random Magic Properties",item.randomCount),.45,.72,1)
    end
    local sockets=false
    for _,affix in ipairs(item.affixes) do if affix.kind=="socket" then
        if not sockets then tooltip:AddLine(" ");sockets=true end
        local gem
        for _,child in ipairs(item.affixes) do if child.kind=="gem" and child.parent==affix.seq then gem=child;break end end
        local icon=gem and GetItemIcon and GetItemIcon(gem.gemEntry)
        local prefix=icon and ("|T"..icon..":16|t ") or ""
        -- Our sockets carry no colour at all: any normal gem goes in any socket,
        -- which is WoW's prismatic and D3's only kind (05-items I7), so an empty
        -- one is the stock prismatic socket and says nothing more. A preview's socket
        -- count is still a roll, so it shows the range the roller would take.
        local label=SOCKET_LABEL
        if affix.fixed and affix.max>affix.min then label=label..string.format(" [%g - %g]",affix.min,affix.max) end
        -- A legendary gem has no stat line of its own: its name, in the legendary colour, and its rank.
        local text=socketIcon..label
        if gem and gem.legendaryRank then
            text=prefix.."|cffff8000"..(gem.gemName or "Gem").."|r  |cff9d9d9dRank "..gem.legendaryRank.."|r"
        elseif gem then
            text=prefix..format(gem).." ("..(gem.gemName or "Gem")..")"
        end
        tooltip:AddLine(text,.8,.8,.8,true)
        if gem and gem.legendaryRank then legendaryPower(tooltip,gem.basePower,gem.bonus,gem.legendaryRank) end
    end end
    -- Directly under the last socket line, before the set, the power and the footer.
    -- A preview is an item nobody owns yet, so it never asks for the shift-right-click socket.
    if sockets and not item.preview then tooltip:AddLine(SOCKETABLE,0,1,0) end
    if item.set then
        tooltip:AddLine(" ");local setCount=0;for _ in pairs(item.owned) do setCount=setCount+1 end
        tooltip:AddLine(string.format("%s (%d/%d)",item.set.name,setCount,#item.set.pieces),0,1,0)
        for _,piece in ipairs(item.set.pieces) do local owned=item.owned[piece];tooltip:AddLine("  "..piece,owned and 0 or .5,owned and 1 or .5,owned and 0 or .5) end
        local anyOn=false
        for _,bonus in ipairs(item.set.bonuses) do
            local on=item.bonusOn and item.bonusOn[bonus.count]
            anyOn=anyOn or on
            if on then tooltip:AddLine(string.format("(%d) Set: %s",bonus.count,bonus.text),1,.5,0,true)
            else tooltip:AddLine(string.format("(%d) Set: %s",bonus.count,bonus.text),.6,.6,.6,true) end
        end
        if not anyOn then tooltip:AddLine("Set bonuses are inactive.",.7,.7,.7) end
    end
    -- The power and the flavour are drawn here, wrapped, in their D3 colours;
    -- the native description line was left out of the top redraw above.
    if item.power and item.power~="" then
        tooltip:AddLine(" ");tooltip:AddLine(item.rolledPower or item.power,1,.5,0,true)
        if item.drunk then -- no active line: the potion's power is on its drink
        elseif item.active then tooltip:AddLine("Legendary power is active.",0,1,0) else tooltip:AddLine("Legendary power is inactive.",.7,.7,.7) end
    end
    if item.flavour and item.flavour~="" then tooltip:AddLine(" ");tooltip:AddLine(item.flavour,.8,.7,.5,true) end
    tooltip:AddLine(" ");tooltip:AddLine("Required Level "..item.level,1,1,1)
    if item.bound then tooltip:AddLine("Account Bound",1,1,1) end
    -- One copper is one gold (Economy.lua Econ.Gold), so the sell value is N gold, grouped in
    -- threes, never split into g/s/c (UI fixes row 6, 12-ui U4).
    local sell="Sell Value: "..goldText(item.sell).." gold"
    if (item.maxDurability or 0)>0 then tooltip:AddDoubleLine(sell,"Durability "..item.durability.." / "..item.maxDurability,1,1,1,1,1,1) else tooltip:AddLine(sell,1,1,1) end
    tooltip:Show();busy=false
end
-- Items outside the player's bags - the account stash - are pushed here by the
-- screen that owns them. Kept apart from byGuid so a bag refresh cannot drop
-- them and a stash refresh cannot drop the bags.
local extra={}
function DCAddItemTooltips(list)
    for _,item in pairs(list or {}) do if item.guid then extra[item.guid]=item end end
end
function DCShowItemTooltip(tooltip,guid)
    local item=byGuid[guid] or extra[guid]
    if item then decorate(tooltip,item) end
end
-- Blacksmith recipe preview: the detail pane and the list
-- row hand the hovered recipe here; the record is the server's (handlers.PreviewResult) and
-- decorate() draws it exactly like a rolled item. Nothing about it is worked out here.
local previewCache={}
function DCShowRecipePreview(tooltip,recipe)
    if not (tooltip and recipe and recipe.id) then return end
    local record=previewCache[recipe.id]
    if record then decorate(tooltip,record,true) return true end
    if AIO.Handle then AIO.Handle(CHANNEL,"Preview",recipe.id) end
end
-- A tunable or catalogue reload changes what the roller would do, so the Blacksmith drops
-- the cache whenever it takes a fresh Show payload.
function DCRecipePreviewsClear() previewCache={} end
handlers.PreviewResult=function(_,record)
    if type(record)~="table" or not record.id or not record.entry then return end
    previewCache[record.id]=record
    local owner=GameTooltip.GetOwner and GameTooltip:GetOwner()
    if not (owner and owner.dcRecipeId==record.id) then return end
    -- Still hovering that recipe: redraw the native base lines (the entry the Blacksmith
    -- hovered) and lay the preview on top, exactly as a rolled item is drawn.
    GameTooltip:SetOwner(owner,"ANCHOR_RIGHT")
    if GameTooltip.SetHyperlink then GameTooltip:SetHyperlink("item:"..record.entry..":0:0:0:0:0:0:0") end
    decorate(GameTooltip,record,true);GameTooltip:Show()
end
-- Shared item links. A link names a random
-- code only, never an item or character GUID. The server froze the rows when
-- the link was made; the recipient asks for that copy once, caches it by code
-- and draws it in the tooltip. The link is a capability, so the author being
-- offline or having rerolled the item changes nothing. Real client rendering
-- against a second player remains unverified.
local linkCache={}
-- A shared item is a native item link, because the core drops a chat message holding a link tag it does not know
-- and checks an item link's colour (the template Quality's, ItemQualityColors in SharedDefines.h) and text (the template name). The
-- 128-bit code rides in the four uint32 fields the core reads and ignores: the enchant and the first three gems. The fourth gem, the
-- suffix, the unique and the level stay 0 (the core refuses a unique without a suffix; a stock link carries the linker's level), which is
-- also how SetItemRef knows one. The words are never run through %d or %x: the client is 32-bit and Lua 5.1 would wrap them.
local QUALITY_HEX={[0]="9d9d9d","ffffff","1eff00","0070dd","a335ee","ff8000","e6cc80","e6cc80"}
local function carriedLink(payload)
    local hex=QUALITY_HEX[payload.itemQuality]
    local code=payload.code
    if not (hex and payload.entry and payload.itemName and type(code)=="string" and #code==32 and code:match("^%x+$")) then return nil end
    local words={}
    for i=1,4 do words[i]=("%.0f"):format(tonumber(code:sub(i*8-7,i*8),16)) end
    return ("|cff%s|Hitem:%d:%s:%s:%s:%s:0:0:0:0|h[%s]|h|r"):format(hex,payload.entry,words[1],words[2],words[3],words[4],payload.itemName)
end
local function carriedCode(link)
    local entry,a,b,c,d=link:match("^item:(%d+):(%d+):(%d+):(%d+):(%d+):0:0:0:0$")
    if not entry then return nil end
    local code=""
    for _,word in ipairs({a,b,c,d}) do
        local n=tonumber(word)
        if n>4294967295 then return nil end
        code=code..("%04x%04x"):format(math.floor(n/65536),n%65536)
    end
    return code
end
local stockModified=HandleModifiedItemClick
-- Called by the Torment addon's inventory and stash slots on shift-click.
function DCRequestItemLink(guid)
    if guid and AIO.Handle then AIO.Handle(CHANNEL,"Link",guid) end
end
local function renderLink(code)
    local record=linkCache[code]
    if not (record and ItemRefTooltip and ItemRefTooltip.SetOwner) then return false end
    ShowUIPanel(ItemRefTooltip)
    ItemRefTooltip:SetOwner(UIParent,"ANCHOR_PRESERVE")
    -- The native base lines (type, armour/damage, sell) come from the entry the
    -- frozen copy carries; the rolled rows are drawn on top by decorate().
    if ItemRefTooltip.SetHyperlink and record.entry then ItemRefTooltip:SetHyperlink("item:"..record.entry) end
    decorate(ItemRefTooltip,record,true)
    ItemRefTooltip:Show()
    return true
end
local function tell(message)
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("Torment: "..message) end
end
handlers.LinkResult=function(_,payload)
    payload=payload or {}
    if not payload.ok then tell(payload.message or "That item cannot be linked.");return end
    local link=carriedLink(payload)
    if not link then tell("That item cannot be linked.");return end
    if stockModified then stockModified(link) end
end
handlers.SnapshotResult=function(_,code,record)
    if type(code)~="string" then return end
    if not record then tell("This item link has expired");return end
    record.guid=code -- client-side identity only; the copy itself carries no GUID
    linkCache[code]=record
    renderLink(code)
end
-- 3.3.5 chat links fire on click (ChatFrame_OnHyperlinkClick -> SetItemRef); the
-- code is fetched then and the cached copy is drawn at once on later clicks.
local dcSetItemRef=SetItemRef
function SetItemRef(link,text,button,chatFrame)
    local code=type(link)=="string" and carriedCode(link)
    if code then
        if not renderLink(code) and AIO.Handle then AIO.Handle(CHANNEL,"Snapshot",code) end
    elseif dcSetItemRef then
        return dcSetItemRef(link,text,button,chatFrame)
    end
end
-- The bag and slot come from the button itself wherever the client exposes
-- them, not from a list of frame names alone. ElvUI's bag buttons carry the
-- bag and slot as bagID/slotID, so its bag window (when the ElvUI bag
-- module is on) is found the same way the stock one is. A stock bag button is
-- ContainerFrame<bag>Item<slot>, whose own GetID is the slot and whose parent's
-- GetID is the bag; the paper doll is the stock Character<slot> button.
local function locate(owner)
    if not owner or not owner.GetName then return end
    if type(owner.bagID)=="number" and type(owner.slotID)=="number" then
        return owner.bagID,owner.slotID
    end
    local name=owner:GetName() or ""
    if name:find("^ContainerFrame") then return owner:GetParent():GetID(),owner:GetID() end
    if name:find("^Character") and owner:GetID()>0 then return 255,owner:GetID()-1 end
end
-- The low 32 bits of the player being inspected, the key the server names the
-- inspect context with. UnitGUID is "0x" plus hex; when the client cannot read
-- one there is nothing to ask for and the server drops the request.
local function inspectGUID()
    local frame=InspectFrame
    local unit=(frame and frame.unit) or "target"
    local guid=UnitGUID and UnitGUID(unit)
    local hex=guid and guid:match("(%x+)$")
    return hex and tonumber(hex:sub(-8),16)
end
-- Inspect slots are the stock Inspect<Name>Slot buttons (InspectHeadSlot,
-- InspectNeckSlot, ...); their GetID is the inventory slot 1-19, so the server
-- keys the record at GetID()-1, the equipment-slot number GetItemByPos wants.
local function isInspectOwner(owner)
    local name=owner and owner.GetName and owner:GetName() or ""
    return name:find("^Inspect.-Slot$")~=nil
end
-- Buyback reuses the merchant's own item buttons, so only the buyback tab may
-- read buyback records; on the merchant tab that same button is a vendor item
-- and must keep its base shell.
local function isBuybackOwner(owner)
    if not (MerchantFrame and MerchantFrame.selectedTab==2) then return false end
    local name=owner and owner.GetName and owner:GetName() or ""
    return name:find("^MerchantItem%d+ItemButton$")~=nil or name=="MerchantBuyBackItemItemButton"
end
-- The inbox row's own item button carries its row in .index (stock
-- InboxFrameItem_OnEnter asks for attachment 1); an open letter's attachment
-- button is OpenMailAttachmentButton<n> for the letter InboxFrame.openMailID.
local function mailRecord(owner,name)
    if name:find("^MailItem%d+Button$") and type(owner.index)=="number" then
        return contexts.mail[owner.index] and contexts.mail[owner.index][1]
    end
    local attach=name:match("^OpenMailAttachmentButton(%d+)$")
    local inbox=_G.InboxFrame
    local row=inbox and inbox.openMailID
    if attach and row then return contexts.mail[row] and contexts.mail[row][tonumber(attach)] end
end
-- TradePlayerItem<n>ItemButton is the caller's side, TradeRecipientItem<n>ItemButton
-- the partner's; n is the slot, 1-6 plus 7 for the non-traded slot.
local function tradeRecord(name)
    local slot=name:match("^TradePlayerItem(%d+)ItemButton$")
    if slot then return contexts.trade.player[tonumber(slot)] end
    slot=name:match("^TradeRecipientItem(%d+)ItemButton$")
    if slot then return contexts.trade.target[tonumber(slot)] end
end
-- A tooltip owner to a rolled record, plus whether it came from a context
-- cache (bank, buyback, inspect, mail, trade) rather than the bag/paper-doll cache. The bag
-- and Character branches are exactly the old locate() lookup, so those screens
-- do not change; the context branches are what the new pushes fill.
local function resolveOwner(owner)
    if not owner or not owner.GetName then return end
    local bag,slot=locate(owner)
    if bag then
        local item=(cache[bag] and cache[bag][slot]) or (contexts.bank[bag] and contexts.bank[bag][slot])
        return item,bag==-1 or bag>=5
    end
    local name=owner:GetName() or ""
    if name:find("^BankFrameItem%d+$") then
        return contexts.bank[-1] and contexts.bank[-1][owner:GetID()],true
    end
    if isBuybackOwner(owner) then
        if name=="MerchantBuyBackItemItemButton" then
            local n=GetNumBuybackItems and GetNumBuybackItems() or 0
            return contexts.buyback[n],true
        end
        return contexts.buyback[owner:GetID()],true
    end
    if isInspectOwner(owner) then
        local guid=inspectGUID()
        if guid and contexts.inspect[guid] then return contexts.inspect[guid][owner:GetID()-1],true end
    end
    local mailed=mailRecord(owner,name)
    if mailed then return mailed,true end
    local traded=tradeRecord(name)
    if traded then return traded,true end
end
-- Shift-clicking a carried or worn rolled item into an open chat box: the stock handler would put in the stock item link, whose
-- tooltip is the base item and nothing rolled. The server is asked for the link instead and LinkResult inserts it.
-- Anything else (no open chat box, another modified click, a shell, a bank or context item, a stock item) is the stock handler's.
function HandleModifiedItemClick(link)
    if type(link)=="string" and link:find("|Hitem:",1,true) and IsModifiedClick and IsModifiedClick("CHATLINK")
       and ChatEdit_GetActiveWindow and ChatEdit_GetActiveWindow() and GetMouseFocus then
        local owner=GetMouseFocus()
        local bag=locate(owner)
        local item=bag and (bag==255 or (bag>=0 and bag<=4)) and resolveOwner(owner)
        if item and item.guid and not item.unidentified and not item.gem then DCRequestItemLink(item.guid);return true end
    end
    if stockModified then return stockModified(link) end
end
local function clearTooltip(self) self.dcGuid=nil;self.dcNative=nil end
GameTooltip:HookScript("OnTooltipCleared",clearTooltip)
GameTooltip:HookScript("OnTooltipSetItem",function(self)
    local owner=self:GetOwner()
    local item=resolveOwner(owner)
    if item then decorate(self,item) return end
    -- Inspect is the one context whose identity the client already knows, so
    -- ask for the shown target on first hover and draw from the reply.
    if isInspectOwner(owner) then
        local guid=inspectGUID()
        if guid and not contexts.inspect[guid] and AIO.Handle then AIO.Handle(CHANNEL,"Context","inspect",guid) end
    end
end)
-- Shift-compare: ShoppingTooltip1/2 show worn items and need the same D3 layout.
local function shoppingTips()
    local list=GameTooltip.shoppingTooltips
    if type(list)=="table" and list[1] then return list end
    local out={}
    for i=1,3 do local tip=_G["ShoppingTooltip"..i];if tip then out[#out+1]=tip end end
    return out
end
local function wornMatch(tooltip,index)
    local worn=cache[255];if not worn then return end
    local link=tooltip.GetItem and select(2,tooltip:GetItem())
    local entry=link and tonumber(link:match("item:(%d+)"))
    local title=_G[tooltip:GetName().."TextLeft1"];local label=title and title:GetText()
    local hits={}
    for id=1,19 do
        local item=worn[id-1]
        if item then
            local wornLink=GetInventoryItemLink("player",id)
            local wornEntry=wornLink and tonumber(wornLink:match("item:(%d+)"))
            if (entry and wornEntry==entry) or (not entry and label and label==item.name) then hits[#hits+1]=item end
        end
    end
    return hits[math.min(index,#hits)] or hits[1]
end
local function compareRefresh()
    for _,tip in ipairs(shoppingTips()) do
        if tip:IsShown() then local item=wornMatch(tip,tip.dcIndex or 1);if item then decorate(tip,item,true) end end
    end
    local item=resolveOwner(GameTooltip:GetOwner())
    if item and GameTooltip.dcGuid==item.guid then decorate(GameTooltip,item,true) end
end
for index,tip in ipairs(shoppingTips()) do
    tip.dcIndex=index
    tip:HookScript("OnTooltipCleared",function(self) self.dcGuid=nil;self.dcNative=nil end)
    tip:HookScript("OnShow",function(self)
        local item=wornMatch(self,self.dcIndex or 1)
        if item then decorate(self,item,true) end
    end)
end
if type(GameTooltip_ShowCompareItem)=="function" then hooksecurefunc("GameTooltip_ShowCompareItem",compareRefresh) end
-- Diagnostic: what the client actually holds and which push delivered it.
SLASH_DCTOOLTIP1="/dctooltip"
SlashCmdList.DCTOOLTIP=function(arg)
    if arg=="refresh" then
        AIO.Handle(CHANNEL,"Refresh")
        DEFAULT_CHAT_FRAME:AddMessage("Torment tooltips: refresh requested")
        return
    end
    DEFAULT_CHAT_FRAME:AddMessage(string.format("Torment tooltips: %d items cached, last payload from %s",count,source))
end
local watcher=CreateFrame("Frame");local pending,elapsed=false,0
for _,event in ipairs({"BAG_UPDATE","PLAYER_EQUIPMENT_CHANGED","UNIT_INVENTORY_CHANGED"}) do watcher:RegisterEvent(event) end
watcher:SetScript("OnEvent",function() pending=true;elapsed=0 end)
watcher:SetScript("OnUpdate",function(_,delta)
    if pending then elapsed=elapsed+delta;if elapsed>.3 then pending=false;AIO.Handle(CHANNEL,"Refresh") end end
end)
-- A context push (bank, buyback, inspect, mail, trade): store it under its own cache, then
-- re-draw whatever the cursor is over if it belongs to that context. Only the
-- frame opening or its contents changing asks for a push; nothing is polled.
local function redecorate()
    local function one(tip)
        if tip and tip.IsShown and tip:IsShown() then
            local item,context=resolveOwner(tip:GetOwner())
            if item and context then decorate(tip,item,true) end
        end
    end
    one(GameTooltip)
    for _,tip in ipairs(shoppingTips()) do one(tip) end
end
handlers.Context=function(_,msg)
    msg=msg or {}
    local items=msg.items or {}
    if msg.name=="bank" then contexts.bank=items
    elseif msg.name=="buyback" then contexts.buyback=items
    elseif msg.name=="inspect" then
        local guid=tonumber(msg.guid)
        if guid then contexts.inspect[guid]=items end
    elseif msg.name=="mail" then contexts.mail=items
    elseif msg.name=="trade" then contexts.trade={player=items.player or {},target=items.target or {}}
    end
    redecorate()
end
-- Ask for a context when its frame opens, and again when the contents the server owns
-- change. One change fires several events (a sale is MERCHANT_UPDATE plus a BAG_UPDATE per
-- bag) and the server reads every slot per ask and drops a flood (Security G1), so asks are
-- coalesced like the bag watcher's Refresh: each context is asked once, .3 s after its last
-- event, so the final state is always the one asked for.
local contextWatcher=CreateFrame("Frame");local asks,askQuiet={},0
local function ask(name,guid) asks[name]=guid or true;askQuiet=0 end
contextWatcher:SetScript("OnUpdate",function(_,delta)
    if not next(asks) then return end
    askQuiet=askQuiet+delta
    if askQuiet<=.3 then return end
    local due=asks;asks={}
    for name,guid in pairs(due) do
        if guid==true then AIO.Handle(CHANNEL,"Context",name) else AIO.Handle(CHANNEL,"Context",name,guid) end
    end
end)
for _,event in ipairs({"BANKFRAME_OPENED","PLAYERBANKSLOTS_CHANGED","PLAYERBANKBAGSLOTS_CHANGED",
    "BAG_UPDATE","MERCHANT_SHOW","MERCHANT_UPDATE","PLAYER_TARGET_CHANGED",
    "MAIL_SHOW","MAIL_INBOX_UPDATE","MAIL_CLOSED",
    "TRADE_SHOW","TRADE_UPDATE","TRADE_PLAYER_ITEM_CHANGED","TRADE_TARGET_ITEM_CHANGED","TRADE_CLOSED"}) do
    contextWatcher:RegisterEvent(event)
end
contextWatcher:SetScript("OnEvent",function(_,event)
    if event=="BANKFRAME_OPENED" or event=="PLAYERBANKSLOTS_CHANGED" or event=="PLAYERBANKBAGSLOTS_CHANGED"
        or (event=="BAG_UPDATE" and BankFrame and BankFrame:IsShown()) then
        ask("bank")
    elseif event=="MERCHANT_SHOW" or event=="MERCHANT_UPDATE"
        or (event=="BAG_UPDATE" and MerchantFrame and MerchantFrame:IsShown()) then
        ask("buyback")
    elseif event=="PLAYER_TARGET_CHANGED" and InspectFrame and InspectFrame:IsShown() then
        local guid=inspectGUID()
        if guid then ask("inspect",guid) end
    elseif event=="MAIL_SHOW" or event=="MAIL_INBOX_UPDATE" then
        ask("mail")
    elseif event=="MAIL_CLOSED" then
        contexts.mail={};asks.mail=nil
    elseif event=="TRADE_SHOW" or event=="TRADE_UPDATE" or event=="TRADE_PLAYER_ITEM_CHANGED"
        or event=="TRADE_TARGET_ITEM_CHANGED" then
        ask("trade")
    elseif event=="TRADE_CLOSED" then
        contexts.trade={player={},target={}};asks.trade=nil
    end
end)
