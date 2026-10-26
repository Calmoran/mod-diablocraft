"""Exercise production potion intents/heal with test-only items and check SQL/DBC.

No fixture is written to a game database or committed to the shipped item data.
"""
import csv
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import harness_env
import time

import generate_spells as generator

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "azerothcore-wotlk/build/_agent-scratch/scripts/potion-tests"


def toolchain():
    """cmake from PATH, the host generator, and per-OS configure/build/run.

    This hardcoded C:/Program Files/CMake/bin/cmake.exe and the Visual Studio
    generator, which stopped working when the project moved to Linux. Windows
    still gets the Visual Studio project and the Release subfolder; on Linux the
    default generator writes the binary directly in build/.
    """
    found = shutil.which("cmake")
    if not found:
        raise SystemExit("cmake is not on PATH; this harness compiles a small C++ program")
    windows = os.name == "nt"
    configure = [found, "--fresh", "-S", str(OUT), "-B", str(OUT / "build")]
    build = [found, "--build", str(OUT / "build")]
    if windows:
        configure += ["-G", "Visual Studio 17 2022", "-A", "x64"]
        build += ["--config", "Release", "--", "-m:1"]
    binary = OUT / "build" / ("Release/potion_test.exe" if windows else "potion_test")
    return configure, build, str(binary)


def extract(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def data_checks():
    sql = (generator.GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    columns = re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql)[1]
    columns = [column.strip().strip("`") for column in columns.split(",")]
    rows = [next(csv.reader([line[1:-2]], quotechar="'", skipinitialspace=True))
            for line in sql.splitlines() if line.startswith("(")]
    potion = next(row for row in rows if int(row[0]) == 81202)
    fields = dict(zip(columns, potion))
    assert fields["Name_Lang_enUS"] == "Health Potion"
    expected = {"RecoveryTime": 30000, "CategoryRecoveryTime": 0, "Category": 0,
                "StartRecoveryCategory": 0, "StartRecoveryTime": 0,
                "CastingTimeIndex": 1, "RangeIndex": 1, "ImplicitTargetA_1": 1,
                "ImplicitTargetB_1": 0, "Effect_1": 3, "Effect_2": 0, "Effect_3": 0,
                "SpellIconID": 3035, "SpellVisualID_1": 147,
                "ManaCost": 0, "ManaCostPct": 0, "ChannelInterruptFlags": 0,
                "InterruptFlags": 0, "SpellClassSet": 0}
    for name, value in expected.items():
        assert int(fields[name]) == value, (name, fields.get(name), value)
    for name, value in fields.items():
        if name.startswith(("EffectBasePoints_", "EffectDieSides_", "Reagent_", "ReagentCount_")):
            assert int(value) == 0, (name, value)
    # No inherited sitting/combat/passive restrictions, channel or movement cast flags.
    assert int(fields["Attributes"]) == generator.SPELL_ATTR0_IS_ABILITY | generator.SPELL_ATTR0_NO_ACTIVE_DEFENSE
    assert int(fields["AttributesEx"]) == 0
    dbc = generator.CLIENT_DBC.read_bytes()
    _, count, field_count, size, _ = struct.unpack_from("<4sIIII", dbc)
    records = [dbc[pos:pos+size] for pos in range(20, 20+count*size, size)
               if struct.unpack_from("<I", dbc, pos)[0] == 81202]
    assert len(records) == 1
    record = records[0]
    for name, value in expected.items():
        assert struct.unpack_from("<I", record, columns.index(name)*4)[0] == value, name
    strings = dbc[20+count*size:]
    offset = struct.unpack_from("<I", record, generator.F_NAME_ENUS*4)[0]
    assert strings[offset:strings.index(b"\0", offset)] == b"Health Potion"
    migration = ROOT / "mod-diablocraft/data/sql/db-characters/updates/classes_0003_character_potion.sql"
    assert migration.read_bytes() == (generator.GENERATED / "character_potion.sql").read_bytes()
    assert "item_entry INT UNSIGNED NULL DEFAULT NULL" in migration.read_text()
    with (generator.DATA / "base_items.csv").open(encoding="utf-8-sig", newline="") as stream:
        assert not any(row["slot"] == "potion" for row in csv.DictReader(stream))
    print("PASS potion SQL/client DBC and no shipped potion items", flush=True)


STUBS = r'''
#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <type_traits>
#include <utility>
#include <vector>
#include "@HEADER@"
#include "@POWER_MATH@"
#include "@SHELLS@"
using uint8 = std::uint8_t;
using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
constexpr uint8 INVENTORY_SLOT_BAG_0=255, INVENTORY_SLOT_ITEM_START=23, INVENTORY_SLOT_ITEM_END=39;
constexpr uint8 INVENTORY_SLOT_BAG_START=19, INVENTORY_SLOT_BAG_END=23, EQUIPMENT_SLOT_END=19;
constexpr uint8 NULL_SLOT=255;
constexpr int EQUIP_ERR_OK=0, ITEM_CHANGED=1;
struct Guid { uint32 value=7; uint32 GetCounter() const {return value;} };
bool operator==(Guid a, Guid b) {return a.value==b.value;}
struct Player;
struct ItemTemplate {};
uint32 nextItemGuid=100;
struct Item {
    uint32 entry, count=1;
    uint8 bag=255, slot=23;
    bool traded=false;
    Guid owner;
    Guid guid{nextItemGuid++};
    ItemTemplate proto;
    explicit Item(uint32 e):entry(e){}
    Guid GetGUID() const {return guid;}
    static Item* CreateItem(uint32 entry,uint32,Player*) {return new Item(entry);}
    uint32 GetEntry() const {return entry;}
    uint32 GetCount() const {return count;}
    void SetCount(uint32 n) {count=n;}
    uint8 GetBagSlot() const {return bag;}
    uint8 GetSlot() const {return slot;}
    uint16 GetPos() const {return uint16(bag<<8)|slot;}
    Guid GetOwnerGUID() const {return owner;}
    bool IsInTrade() const {return traded;}
    void SetState(int,Player*){}
    void SendUpdateToPlayer(Player*){}
    ItemTemplate const* GetTemplate() const {return &proto;}
    bool IsBag() const {return false;}
    bool IsNotEmptyBag() const {return false;}
};
struct Bag {uint32 GetBagSize() const {return 0;}};
struct ItemPosCount {uint16 pos; uint32 count;};
using ItemPosCountVec=std::vector<ItemPosCount>;
// The characters database's item rows (diablocraft-1z5ye): dc_item_instance as the quality tier, dc_item_affix as (key, value,
// min, max) per seq; what a commit makes durable.
struct AffixRow {std::string key; double value, min, max;};
struct ItemRows {std::string quality, rarity; std::map<unsigned, AffixRow> affixes;};
std::map<uint64, ItemRows> itemRows;
struct Transaction {
    std::optional<uint32> potion;
    std::optional<double> roll;
    std::map<uint64, ItemRows> instances;
    bool written=false, inventorySaved=false;
    template<class... Args> void Append(char const* sql,Args... args) {
        std::string const text(sql);
        using Values=std::tuple<Args...>;
        Values values{args...};
        constexpr bool instance=[]{
            if constexpr(sizeof...(Args)==3) return std::is_same_v<std::tuple_element_t<2,Values>,std::string>;
            else return false;
        }();
        if constexpr(instance) {
            if (text.find("INSERT INTO dc_item_instance")!=0) throw std::runtime_error("unexpected mutation SQL");
            if (text.find("'normal'")==std::string::npos) throw std::runtime_error("a returned potion is never Ancient");
            instances[uint64(std::get<0>(values))].quality="normal";
            instances[uint64(std::get<0>(values))].rarity=std::get<2>(values);
        } else if constexpr(sizeof...(Args)==6) {
            if (text.find("INSERT INTO dc_item_affix")!=0 || text.find("'power'")==std::string::npos)
                throw std::runtime_error("unexpected mutation SQL");
            auto& row=instances.at(uint64(std::get<0>(values)));
            row.affixes[unsigned(std::get<1>(values))]={std::string(std::get<2>(values)),double(std::get<3>(values)),
                                                        double(std::get<4>(values)),double(std::get<5>(values))};
        } else {
            if (text.find("INSERT INTO dc_character_potion")!=0)
                throw std::runtime_error("unexpected mutation SQL");
            if constexpr(sizeof...(Args)>=2) {
                potion=uint32(std::get<1>(values));
                if (text.find("power_roll=NULL")!=std::string::npos) roll.reset();
                else if constexpr(sizeof...(Args)==3) roll=double(std::get<2>(values));
                else throw std::runtime_error("a slotted potion's roll is written or cleared");
            } else {
                if (text.find("power_roll=NULL")==std::string::npos) throw std::runtime_error("an empty slot clears the roll");
                potion.reset(); roll.reset();
            }
            written=true;
        }
    }
};
using CharacterDatabaseTransaction=std::shared_ptr<Transaction>;
struct Field {
    std::optional<double> value;
    std::string text;
    bool IsNull() const {return !value && text.empty();}
    template<class T> T Get() const {
        if constexpr(std::is_same_v<T,std::string>) return text; else return T(value.value());
    }
};
using QueryResult=std::shared_ptr<std::vector<Field>>;
struct CharacterDB {
    bool hasRow=false, fail=false;
    std::optional<uint32> entry;
    std::optional<double> roll;
    QueryResult Query(char const* sql,uint32) {
        if (std::string(sql).find("SELECT item_entry, power_roll FROM dc_character_potion")!=0)
            throw std::runtime_error("the slot is read with its roll");
        if (!hasRow) return nullptr;
        return std::make_shared<std::vector<Field>>(std::vector<Field>{
            Field{entry ? std::optional<double>(*entry) : std::nullopt, ""}, Field{roll, ""}});
    }
    void EscapeString(std::string&) {}
} CharacterDatabase;
struct WorldDB {
    // Fixtures exist in this process only; no shipped CSV/SQL entries.
    std::set<uint32> potions{900001,900002};
    QueryResult Query(char const* sql,uint32 entry) {
        std::string const text(sql);
        if (text.find("SELECT d3_id, rarity FROM dc_base_item WHERE entry=")==0)
            return potions.count(entry) ? std::make_shared<std::vector<Field>>(std::vector<Field>{
                Field{std::nullopt, "FIXTURE_POTION_" + std::to_string(entry)}, Field{std::nullopt, "legendary"}}) : nullptr;
        if (text.find("AND slot='potion'")==std::string::npos)
            throw std::runtime_error("potion eligibility must check slot type");
        return potions.count(entry) ? std::make_shared<std::vector<Field>>(1) : nullptr;
    }
} WorldDatabase;
struct Session {
    Player* player=nullptr;
    bool aborted=false;
    Player* GetPlayer() {return player;}
    bool EconomyAborted() const {return aborted;}
    void AbortEconomy() {aborted=true;}
};
struct SpellInfo {uint32 Id=81202,SchoolMask=2,SpellFamilyName=0;};
// The current class contract, exercised below: IsClassSpell(Player*, spellId)
// reads the character's own SpellClassSet from ChrClasses.dbc's store and a
// spell's SpellFamilyName from SpellMgr. Minimal real-shaped stubs.
struct ChrClassesEntry { uint32 spellfamily=0; };
struct ChrClassesStore {
    ChrClassesEntry warrior{4};
    ChrClassesEntry const* LookupEntry(uint32 id) const {return id==4?&warrior:nullptr;}
};
ChrClassesStore sChrClassesStore;
struct SpellMgr {
    // The potion shell (81202) and another shell (81100) both carry the class's own
    // family in these stubs. Without those rows GetSpellInfo returns null, IsClassSpell
    // returns false for a reason unrelated to its guards, and the exemption checks
    // below pass even when the production guards are deleted. With them, deleting the
    // IsShell guard flips both checks (81202 is in the shell table now, so the
    // BaseSpell guard alone is redundant with it; delete both and the result flips too).
    SpellInfo potionShell{81202,2,4};
    SpellInfo classShell{81100,2,4};
    SpellInfo ownFamily{12345,2,4};
    SpellInfo otherFamily{54321,2,0};
    SpellInfo const* GetSpellInfo(uint32 id) {
        if(id==81202) return &potionShell;
        if(id==81100) return &classShell;
        if(id==12345) return &ownFamily;
        if(id==54321) return &otherFamily;
        return nullptr;
    }
};
SpellMgr spellMgr;
SpellMgr* sSpellMgr=&spellMgr;
using SpellSchoolMask=uint32;
struct HealInfo {
    Player* healer; Player* target; uint32 amount; SpellInfo const* info;
    HealInfo(Player* h,Player* t,uint32 a,SpellInfo const* s,SpellSchoolMask):healer(h),target(t),amount(a),info(s){}
};
struct Player {
    std::map<uint16,std::unique_ptr<Item>> bag;
    std::map<uint16,std::pair<uint32,uint32>> durable;
    Session session;
    bool alive=true,combat=false;
    uint32 maximum=1000,current=100;
    int bars=0,heals=0,gearSwaps=0;
    Player() {session.player=this;}
    Guid GetGUID() const {return {};}
    uint32 wowClass=4;
    uint32 getClass() const {return wowClass;}
    bool IsAlive() const {return alive;}
    bool IsInCombat() const {return combat;}
    Session* GetSession() {return &session;}
    uint32 GetMaxHealth() const {return maximum;}
    uint32 GetHealth() const {return current;}
    void HealBySpell(HealInfo const& heal,bool crit) {
        if(heal.healer!=this || heal.target!=this || crit || heal.info->Id!=81202)
            throw std::runtime_error("heal packet identity/crit");
        current=std::min(maximum,current+heal.amount); ++heals;
    }
    Item* GetItemByPos(uint8 b,uint8 s) const {
        auto it=bag.find(uint16(b<<8)|s); return it==bag.end()?nullptr:it->second.get();
    }
    Bag* GetBagByPos(uint8) {return nullptr;}
    int CanStoreItem(uint8 b,uint8 s,ItemPosCountVec& dest,Item*,bool swap) {
        if(GetItemByPos(b,s) && !swap) return 1;
        dest.push_back({uint16(uint16(b<<8)|s),1}); return EQUIP_ERR_OK;
    }
    Item* StoreItem(ItemPosCountVec const& dest,Item* item,bool) {
        auto pos=dest.at(0).pos;
        if(bag.count(pos)) throw std::runtime_error("storing onto occupied slot");
        item->bag=uint8(pos>>8); item->slot=uint8(pos);
        bag[pos].reset(item); return item;
    }
    void SaveInventoryAndGoldToDB(CharacterDatabaseTransaction const& tx) {tx->inventorySaved=true;}
    uint8 FindEquipSlot(ItemTemplate const*,uint8,bool) {return 4;}
    void SwapItem(uint16,uint16) {++gearSwaps;}
    Item* Add(uint32 entry,uint8 slot=23,uint32 count=1) {
        auto item=std::make_unique<Item>(entry); item->slot=slot; item->count=count;
        auto* ptr=item.get(); bag[ptr->GetPos()]=std::move(item); return ptr;
    }
    unsigned Count(uint32 entry) const {
        unsigned n=0; for(auto const& [_,item]:bag) if(item->entry==entry) n+=item->count; return n;
    }
};
struct ChatHandler {Session* session; Session* GetSession() {return session;}};
namespace PlayerEconomy {
struct Scope {explicit Scope(Player*){}};
CharacterDatabaseTransaction BeginTransaction() {return std::make_shared<Transaction>();}
void Fail(){}
}
namespace DC::AccountEconomy {
bool Commit(Player* p,CharacterDatabaseTransaction const& tx) {
    if(!tx->written || !tx->inventorySaved) throw std::runtime_error("incomplete atomic save");
    if(CharacterDatabase.fail) return false;
    CharacterDatabase.hasRow=true; CharacterDatabase.entry=tx->potion; CharacterDatabase.roll=tx->roll;
    for(auto const& [guid,rows]:tx->instances) itemRows[guid]=rows;
    p->durable.clear();
    for(auto const& [pos,item]:p->bag) p->durable[pos]={item->entry,item->count};
    return true;
}
}
namespace DC::Classes {void WriteActionBar(Player* p) {++p->bars;}}
namespace DC::Rifts {bool gearLocked=false; bool GreaterRiftGearLocked(Player const*) {return gearLocked;}}
namespace DC::Items {
// dc_items.h's types, as far as the potion slot reads them.
struct Affix {std::string affixId, kind; double value=0;};
struct Instance {std::vector<Affix> affixes;};
std::optional<Instance> Get(uint64 guid) {
    auto found=itemRows.find(guid);
    if(found==itemRows.end()) return std::nullopt;
    Instance instance;
    for(auto const& [seq,row]:found->second.affixes) instance.affixes.push_back({row.key,"power",row.value});
    instance.affixes.insert(instance.affixes.begin(), Affix{"str","primary",500});  // a non-power row is skipped
    return instance;
}
void DestroyWithRows(Player* p,Item* item,CharacterDatabaseTransaction const&) {
    itemRows.erase(item->GetGUID().GetCounter()); p->bag.erase(item->GetPos());
}
}
// The power table: fixture potion 900001 rolls Armor in [10, 20]; 900002 owns no rolling power.
namespace DC::Combat::ItemPowers {
std::vector<ItemPower::Row> ItemRows(std::string const& d3Id) {
    ItemPower::Row row; row.owner="FIXTURE_POTION_900001"; row.kind="player"; row.stat="armor_pct"; row.min=10; row.max=20;
    ItemPower::Row fixed=row; fixed.owner="FIXTURE_POTION_900002"; fixed.min=fixed.max=5;
    std::vector<ItemPower::Row> out;
    for(auto const& r:{row,fixed}) if(r.owner==d3Id) out.push_back(r);
    return out;
}
}
namespace DC::Inventory {
@INVENTORY@
}
namespace DC::Classes {
@HEAL@
}
namespace DC::Classes {
@CLASS_SPELL@
}
int checks=0;
void check(bool ok,char const* name) {++checks; if(!ok) throw std::runtime_error(name);}
template<class F> void refuse(F fn,char const* message) {
    try {fn();} catch(std::runtime_error const& error) {
        check(std::string(error.what()).find(message)!=std::string::npos,"expected refusal message"); return;
    }
    throw std::runtime_error("expected refusal");
}
void reset() {CharacterDatabase=CharacterDB{}; itemRows.clear();}
int main() {
    using namespace DC;
    SpellInfo info;
    // Current potion/class contract, executed rather than restated: the potion
    // shell is exempt from the class strip before any family lookup, a shell in
    // the class family in the shell table (Combat::Shells::IsShell) is exempt from the strip,
    // a spell in the character's own family is stripped, and an off-family
    // spell is kept. Both exemption checks are load-bearing: the potion id and
    // the other shell id are stubbed with family 4, so removing the shell guard
    // (and the BaseSpell guard with it) makes the checks fail.
    Player contract; contract.wowClass=4;
    check(!Classes::IsClassSpell(&contract,Potion::BaseSpell),"potion shell is never a class spell");
    check(!Classes::IsClassSpell(&contract,81100),"class-family shell in the shell table is never stripped");
    check(Classes::IsClassSpell(&contract,12345),"own-family spell is stripped");
    check(!Classes::IsClassSpell(&contract,54321),"off-family spell is kept");
    for(auto maximum:{1000u,2500u}) {
        Player p; p.maximum=maximum; p.current=maximum/10;
        Classes::RestorePotionLife(&p,&info);
        check(p.current==maximum*7/10 && p.heals==1,"60% at two max-Life values, one heal packet");
        p.current=maximum-1; Classes::RestorePotionLife(&p,&info);
        check(p.current==maximum,"heal capped at max");
        Classes::RestorePotionLife(&p,&info); check(p.heals==2,"full Life emits no heal");
        p.alive=false; p.current=0; Classes::RestorePotionLife(&p,&info);
        check(p.current==0 && p.heals==2,"dead characters stay dead");
    }
    check(Potion::HealAmount(1001,0)==600,"fractional Life rounds down");
    check(Potion::HealAmount(UINT32_MAX,0)==2576980377u,"wide intermediate avoids overflow");
    reset(); Player p;
    check(Inventory::ActivePotionSpell(&p)==81202,"missing row -> base potion");
    CharacterDatabase.hasRow=true;
    check(Inventory::ActivePotionSpell(&p)==81202,"NULL row -> base potion");
    p.Add(900001);
    Inventory::Equip(&p,25523);
    check(p.Count(900001)==0 && CharacterDatabase.entry==900001 && p.bars==1,"equip consumes one and saves choice/bar");
    check(p.durable.empty(),"equipped potion is durably absent from bags");
    check(Inventory::ActivePotionSpell(&p)==81202,"unmapped fixture retains base potion");
    Inventory::Unequip(&p,Potion::InventorySlot);
    check(p.Count(900001)==1 && !CharacterDatabase.entry && p.bars==2,"unequip round trip and NULL choice/bar");
    check(p.durable.size()==1 && p.durable.begin()->second.first==900001,"recreated item durable");
    refuse([&]{Inventory::Unequip(&p,Potion::InventorySlot);},"empty");
    Inventory::Equip(&p,25523);
    for(uint8 slot=23;slot<39;++slot) p.Add(42,slot);
    int bars=p.bars;
    refuse([&]{Inventory::Unequip(&p,Potion::InventorySlot);},"full");
    check(CharacterDatabase.entry==900001 && p.bars==bars && p.Count(900001)==0,"full-bag refusal leaves choice unchanged");
    p.Add(900002,23);
    Inventory::Equip(&p,25523);
    check(CharacterDatabase.entry==900002 && p.Count(900001)==1 && p.Count(900002)==0,"full-bag swap reuses consumed cell");
    p.bag.erase(uint16(255<<8)|24);
    Inventory::Unequip(&p,Potion::InventorySlot);
    check(p.GetItemByPos(255,24)->entry==900002,"unequip picks first free cell");
    reset(); Player stack; stack.Add(900001,23,2);
    Inventory::Equip(&stack,25523);
    check(stack.Count(900001)==1,"equip consumes only one from a stack");
    Inventory::Unequip(&stack,Potion::InventorySlot);
    check(stack.Count(900001)==2 && stack.bag.size()==2,"unequip recreates in a free cell, no merging");
    stack.Add(900002,25); stack.GetItemByPos(255,25)->traded=true;
    refuse([&]{Inventory::Equip(&stack,25525);},"traded");
    check(stack.Count(900002)==1 && !CharacterDatabase.entry,"trade refusal preserves item");
    stack.Add(42,26); Inventory::Equip(&stack,25526);
    check(stack.gearSwaps==1 && !CharacterDatabase.entry,"ordinary items keep gear path");
    ChatHandler handler{stack.GetSession()};
    // Ruling q-1003-21: the potion slot changes in combat, so Acting no longer refuses it (Identify keeps its own refusal).
    stack.combat=true; check(Inventory::Acting(&handler)==&stack,"combat is allowed");
    stack.combat=false; check(Inventory::Acting(&handler)==&stack,"out of combat is allowed");
    stack.combat=true; stack.alive=false; refuse([&]{Inventory::Acting(&handler);},"dead");
    refuse([&]{Inventory::Equip(&stack,-1);},"bag slot");
    refuse([&]{Inventory::Unequip(&stack,99);},"equipment slot");
    reset(); Player failed; failed.Add(900001); CharacterDatabase.fail=true;
    refuse([&]{Inventory::Equip(&failed,25523);},"saved");
    check(failed.session.aborted && failed.bars==0 && !CharacterDatabase.hasRow,
          "failed transaction aborts session, leaves durable choice unchanged and does not publish bar");
    // Greater Rift rule 6 (diablocraft-214r): the potion slot is gear, so it stays as it is until the Guardian is dead.
    reset(); Player locked; locked.Add(900001); locked.Add(900002,24); DC::Rifts::gearLocked=true;
    refuse([&]{Inventory::Equip(&locked,25523);},"Greater Rift");
    check(locked.Count(900001)==1 && !CharacterDatabase.hasRow && locked.bars==0,"locked equip changes nothing");
    DC::Rifts::gearLocked=false; Inventory::Equip(&locked,25523);
    check(CharacterDatabase.entry==900001,"equip works once the lock is lifted");
    DC::Rifts::gearLocked=true;
    refuse([&]{Inventory::Unequip(&locked,Potion::InventorySlot);},"Greater Rift");
    check(CharacterDatabase.entry==900001 && locked.Count(900001)==0,"locked unequip changes nothing");
    DC::Rifts::gearLocked=false;
    // diablocraft-1z5ye: the slot keeps a rolled potion's power roll and gives it back to the returned item.
    reset(); Player roller;
    Item* rolled=roller.Add(900001,23);
    itemRows[rolled->GetGUID().GetCounter()]={"normal","legendary",{{0,{"power::armor_pct",17,10,20}}}};
    roller.Add(900002,24);
    Inventory::Equip(&roller,25523);
    check(CharacterDatabase.entry==900001 && CharacterDatabase.roll==17.0,"the slot keeps the potion's roll");
    check(Inventory::ActivePotionRoll(&roller)==std::optional<double>(17.0),"the slot's roll is read back");
    Inventory::Unequip(&roller,Potion::InventorySlot);
    Item* back=roller.GetItemByPos(255,23);
    check(back && back->entry==900001 && !CharacterDatabase.entry && !CharacterDatabase.roll,"unequip empties the slot and its roll");
    auto const& rows=itemRows.at(back->GetGUID().GetCounter());
    check(rows.quality=="normal" && rows.rarity=="legendary" && rows.affixes.size()==1,"the returned potion has its instance");
    auto const& power=rows.affixes.at(0);
    check(power.key=="power::armor_pct" && power.value==17 && power.min==10 && power.max==20,
          "the returned potion's power row is the table's key and range at the kept roll");
    Inventory::Equip(&roller,25523);
    check(CharacterDatabase.roll==17.0,"the same roll goes back into the slot");
    Inventory::Equip(&roller,25524);
    check(CharacterDatabase.entry==900002 && !CharacterDatabase.roll,"a potion with no roll clears the slot's roll");
    Item* swapped=roller.GetItemByPos(255,24);
    check(swapped && swapped->entry==900001 && itemRows.at(swapped->GetGUID().GetCounter()).affixes.at(0).value==17,
          "a swap returns the rolled potion with its roll");
    Inventory::Unequip(&roller,Potion::InventorySlot);
    Item* unrolled=nullptr;
    for(auto const& [_,item]:roller.bag) if(item->entry==900002) unrolled=item.get();
    check(unrolled && !itemRows.count(unrolled->GetGUID().GetCounter()),"a potion with no roll comes back with no rows");
    reset(); Player empty;
    check(!Inventory::ActivePotionRoll(&empty),"no slot row, no roll");
    std::cout<<"PASS "<<checks<<" production potion checks\n";
}
'''


def main():
    data_checks()
    inventory = (ROOT / "mod-diablocraft/src/items/dc_inventory.cpp").read_text(encoding="utf-8")
    classes = (ROOT / "mod-diablocraft/src/classes/dc_classes.cpp").read_text(encoding="utf-8")
    signatures = ("void Need(", "void DecodeBag(", "bool FirstFreeBagSlot(", "Player* Acting(",
                  "struct SlotPotion", "SlotPotion EquippedPotion(", "std::uint32_t EquippedPotionEntry(",
                  "std::optional<double> PowerRoll(", "void WritePowerRoll(", "bool IsPotionItem(", "void ChangePotion(",
                  "void Equip(", "void Unequip(", "std::uint32_t ActivePotionSpell(", "std::optional<double> ActivePotionRoll(")
    code = STUBS.replace("@INVENTORY@", "\n".join(extract(inventory, sig) + ";" for sig in signatures))
    code = code.replace("@POWER_MATH@", (ROOT / "mod-diablocraft/src/combat/dc_item_power_math.h").as_posix())
    code = code.replace("@HEAL@", extract(classes, "void RestorePotionLife("))
    code = code.replace("@HEADER@", (ROOT / "mod-diablocraft/src/classes/dc_potion.h").as_posix())
    # The shell test is the production Combat::Shells::IsShell over the real id table
    # (it replaced the FIRST_SHELL..LAST_SHELL range), so the header is included as is.
    code = code.replace("@SHELLS@", (ROOT / "mod-diablocraft/src/combat/dc_spell_shells.h").as_posix())
    code = code.replace("@CLASS_SPELL@",
                        extract(classes, "std::uint32_t ClassSpellFamily(Player const* player)")
                        + "\n"
                        + extract(classes, "bool IsClassSpell(Player const* player, std::uint32_t spellId)"))
    grant = extract(classes, "void GrantShells(")
    assert "Potion::BaseSpell" in grant and "SendLearnPacket" in grant
    assert 'new PotionCast();' in classes
    assert 'RestorePotionLife(player, info)' in extract(classes, "class PotionCast final : public AllSpellScript")
    # diablocraft-1z5ye: a Bottomless potion is never Ancient (D3), in the roll and in the drop's decision. Read from the
    # source: StageRoll and RollQuality need the server's data and RNG.
    items = items_source.source()
    stage = extract(items, "std::unique_ptr<StagedRoll> StageRoll(Player* player,")
    assert 'if (!DC::Quality::Eligible(base.rarity) || base.slot == "potion")\n            qualityTier = "normal";' in stage
    assert 'if (found == baseItems.end() || found->second.slot == "potion")\n            return "normal";' in \
        extract(items, "std::string RollQuality(Player* player,")
    lock = ROOT / "build.lock"
    owner = f"Codex potion harness {os.getpid()} {time.time()}"
    while True:
        try:
            with lock.open("x", encoding="utf-8") as stream:
                stream.write(owner)
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime >= 1800:
                raise RuntimeError("Stale build.lock; inspect owner")
            print("Waiting for server build lock", flush=True)
            time.sleep(10)
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "test.cpp").write_text(code, encoding="utf-8")
        (OUT / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.20)\nproject(potion_test LANGUAGES CXX)\n"
            "add_executable(potion_test test.cpp)\ntarget_compile_features(potion_test PRIVATE cxx_std_17)\n",
            encoding="utf-8")
        cmake_configure, cmake_build, binary = toolchain()
        env = {key.upper(): value for key, value in os.environ.items()}
        for command in (cmake_configure, cmake_build):
            os.utime(lock, None)
            subprocess.run(command, env=env, check=True)
        os.utime(lock, None)
        harness_env.run([binary], env=env, check=True)
    finally:
        if lock.exists() and lock.read_text(encoding="utf-8") == owner:
            lock.unlink()


if __name__ == "__main__":
    main()
