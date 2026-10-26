// Items: the loaded reference data, the affix -> stat sheet and the readers of both.
// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
#include "dc_items_internal.h"

#include "dc_granted_passive_rule.h"
#include "dc_roll_class.h"

#include "../classes/dc_classes.h"
#include "../classes/dc_resources.h"

#include "DatabaseEnv.h"
#include "Log.h"
#include "Player.h"

#include <cctype>
#include <mutex>
#include <random>
#include <set>
#include <sstream>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace DC::Items
{
namespace Detail
{
namespace
{
// The shell templates, read back once from item_template. A shell is any
// template whose use spell is the identify shell.
std::mutex shellMutex;
std::set<std::uint32_t> shellEntries;
bool shellsLoaded = false;

void LoadShellEntries()
{
    std::lock_guard<std::mutex> lock(shellMutex);
    if (shellsLoaded)
        return;
    shellsLoaded = true;
    if (QueryResult rows = WorldDatabase.Query(
            "SELECT entry FROM item_template WHERE spellid_1={}", IDENTIFY_ITEM_SPELL))
        do
        {
            shellEntries.insert((*rows)[0].Get<uint32>());
        } while (rows->NextRow());
    if (shellEntries.empty())
        LOG_WARN("server", "[DC items] no unidentified shell templates found; "
                           "apply items_0007_unidentified_shells.sql");
}
} // namespace

bool IsShellTemplate(std::uint32_t entry)
{
    LoadShellEntries();
    std::lock_guard<std::mutex> lock(shellMutex);
    return shellEntries.count(entry) != 0;
}
std::string Escape(std::string value)
{
    CharacterDatabase.EscapeString(value);
    return value;
}

// --- loaded reference data ------------------------------------------------
std::mutex dataMutex;
std::unordered_map<std::uint32_t, BaseItem> baseItems;
// slot -> bracket -> entries
std::unordered_map<std::string, std::unordered_map<std::string, std::vector<PoolEntry>>> pools;
// Base item entry -> bracket -> its own preset ranges (dc_item_preset_range).
std::unordered_map<std::uint32_t, std::unordered_map<std::string, std::vector<PoolEntry>>> itemPresetRanges;
bool dataReady = false;
bool relicAncientPrimal = false;
std::unordered_map<std::string, SkillAffix> skillAffixes;
std::unordered_map<std::string, std::vector<SkillAffix>> skillGroups;
// dc_class_map: the playable classes, by WoW class
// (a player's class key) and by key (the catalogue class id dc_skill_affix
// rows carry). classMainStats is every D3 class's main-stat affix from
// dc_class_primary_stats, keyed the same way.
std::unordered_map<unsigned, std::string> classKeys;
std::unordered_map<std::string, std::uint32_t> classIds;
std::unordered_map<std::string, std::string> classMainStats;
// Every passive of each class by class_id (dc_class_passive, unlock order); the Hellfire Amulet rolls from it.
std::unordered_map<std::uint32_t, std::vector<std::string>> classPassiveNames;
// G1: dc_weapon_class, the ONE sourced weapon type -> damage bracket map (slots.js
// `affixes.weapon`, generated from data/d3/weapon_classes.csv). The roller and the Blacksmith
// preview both read it; neither keeps its own type list.
std::unordered_map<std::string, std::string> weaponClassByType;
std::mutex bonusMutex;
std::unordered_map<std::uint64_t, SkillBonuses> skillBonuses;
// G1: per equipped item, the gem's flat damage plus the rolled weapon elemental range, so the
// sheet and combat add it without a database read.
std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, WeaponExtraDamage>> weaponExtra;
// Per player and worn item, the class passive it grants, so Passives::Has reads no database.
std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, std::string>> grantedPassive;
std::unordered_map<uint32,std::unordered_map<std::string,GemEffect>> gemEffects;

// Issue #47: the main stat comes from the class sheets, never from a list of
// classes here. class_primary_stats.csv names each D3 class's main stat, and
// base_items.csv spells a class as its designated_class key: the class name in
// lower case with the spaces taken out ("Demon Hunter" is "demonhunter").
std::string ClassKey(std::string const& d3Class)
{
    std::string key;
    for (char c : d3Class)
        if (c != ' ')
            key += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return key;
}
// The affix id a main-stat line rolls as, from the sheet's stat name; "" for a
// name no main-stat affix has.
std::string StatAffix(std::string const& stat)
{
    if (stat == "Strength")
        return "str";
    if (stat == "Dexterity")
        return "dex";
    if (stat == "Intelligence")
        return "int";
    return {};
}
// Each designated base item's main-stat affix, from the class sheet's rows
// keyed by ClassKey. Returns the designated classes the sheet has no row for;
// their items keep an empty mainStat.
std::set<std::string> ResolveMainStats(std::unordered_map<std::uint32_t, BaseItem>& items,
                                       std::unordered_map<std::string, std::string> const& mainStats)
{
    std::set<std::string> unknown;
    for (auto& [entry, base] : items)
    {
        if (base.designatedClass.empty())
            continue;
        auto found = mainStats.find(base.designatedClass);
        if (found != mainStats.end())
            base.mainStat = found->second;
        else
            unknown.insert(base.designatedClass);
    }
    return unknown;
}
// A designated item rolls its class's main stat; any other rolls the main stat
// of the class it rolls for (dc_roll_class.h rule 3: the looter's
// or the off-class roll's at a drop, the re-roller's at the Mystic), from
// class_primary_stats.csv. No row is a data error: logged, and the caller rolls
// no main-stat line rather than a guessed one.
std::string PrimaryStat(BaseItem const& base, std::string const& affixClass,
                        std::unordered_map<std::string, std::string> const& mainStats)
{
    std::string stat = base.mainStat;
    if (base.designatedClass.empty())
        if (auto found = mainStats.find(affixClass); found != mainStats.end())
            stat = found->second;
    if (stat.empty())
        LOG_ERROR("server", "[DC items] base item {} ({}): no main stat for designated class '{}' / roll class '{}'; "
                  "class_primary_stats.csv or class_map.csv has no row, so no main-stat affix is rolled",
                  base.entry, base.name, base.designatedClass, affixClass);
    return stat;
}

// Rule 3 for skill affixes: the slot group's choices that belong to the affix
// class. Empty for a class with no rows (no catalogue yet), and then the pool
// entry is not rolled at all rather than borrowing another class's skill.
std::vector<SkillAffix> SkillChoices(std::unordered_map<std::string, std::vector<SkillAffix>> const& groups,
                                     std::string const& groupId, std::string const& affixClass)
{
    auto group = groups.find(groupId);
    if (group == groups.end())
        return {};
    auto id = classIds.find(affixClass);
    return DC::RollClass::ChoicesFor(group->second, id == classIds.end() ? 0u : id->second);
}

// The playable class key of a WoW class; the caller holds dataMutex.
std::string ClassKeyOfLocked(unsigned wowClass)
{
    auto found = classKeys.find(wowClass);
    return found == classKeys.end() ? std::string() : found->second;
}
std::string PrimaryName(std::string const& stat)
{
    return stat=="int" ? "Intelligence" : stat=="dex" ? "Dexterity" : "Strength";
}

std::mt19937_64& Engine()
{
    static thread_local std::mt19937_64 engine{std::random_device{}()};
    return engine;
}

std::vector<std::string> Split(std::string const& text, char separator)
{
    std::vector<std::string> parts;
    std::istringstream stream(text);
    std::string part;
    while (std::getline(stream, part, separator))
        if (!part.empty())
            parts.push_back(part);
    return parts;
}

// Block belongs to shields, not to the offhand slot: the same slot holds quivers,
// mojos, sources and phylacteries, and none of those blocks. The pool is keyed by
// slot only, so the block affixes are filtered by item type here, against the
// same two names generate_sql.py classifies as shields.
// Base Chance to Block and Block Amount are REQUIRED affixes on a shield
// (block.md §1, slots.js:1235-1236): every shield has them, and they do not
// spend one of the rarity's rolled affix slots. "+X% Chance to Block" is an
// ordinary rolled secondary and is left to the normal fill.
bool Shield(BaseItem const& base) { return base.type == "Shield" || base.type == "Crusader Shield"; }

bool BlockAffix(std::string const& affixId)
{
    return affixId == "baseblock" || affixId == "block" || affixId == "blockamount" ||
        affixId == "blockamountdelta";
}

bool RequiredShieldAffix(std::string const& affixId)
{
    return affixId == "baseblock" || affixId == "blockamount" || affixId == "blockamountdelta";
}

// A Source, a Mojo and a Phylactery carry +X-Y Damage as a REQUIRED affix (slots.js:1285, :1303,
// :1337 `required: {wpnphy: "damageOffhand"}`): every one has it and it does not spend a rolled
// affix slot, like a shield's block lines. The Shaman's Totem is built like a Source (added weapon damage), so it
// takes the same line. A shield's and a quiver's required lines are others (a quiver's is attack speed), so the
// offhand pool's wpnphy rows are these four types' alone.
bool DamageOffhand(BaseItem const& base)
{
    return base.type == "Source" || base.type == "Mojo" || base.type == "Phylactery" || base.type == "Totem";
}

bool OffhandDamageAffix(BaseItem const& base, std::string const& affixId)
{
    return base.slot == "offhand" && affixId == "wpnphy";
}

// The pool a base rolls from: its slot's rows, then the rows of its own type that dc_affix_pool keeps under "<slot>:<type>"
// (the Shaman's Ritual Mace and Totem: class_item_pools.csv). A type with no rows of its own rolls its slot's alone.
std::vector<PoolEntry> PoolFor(BaseItem const& base, std::string const& bracket)
{
    std::vector<PoolEntry> out;
    for (std::string const& key : {base.slot, base.slot + ":" + base.type})
        if (auto slot = pools.find(key); slot != pools.end())
            if (auto rows = slot->second.find(bracket); rows != slot->second.end())
                out.insert(out.end(), rows->second.begin(), rows->second.end());
    return out;
}

// A Quiver carries Attack Speed Increase as a REQUIRED affix (slots.js:1321 `required: {ias: "iasQuiver"}`), outside
// the rolled budget like the lines above; no other offhand lists ias, so the offhand pool's ias rows are the Quiver's.
bool SpeedQuiver(BaseItem const& base) { return base.type == "Quiver"; }

bool OffhandSpeedAffix(BaseItem const& base, std::string const& affixId)
{
    return base.slot == "offhand" && affixId == "ias";
}

ElementalAffix const ElementalAffixes[] = {
    {"dmgphy", "Physical Damage Increase", Element::Physical}, {"dmgfir", "Fire Damage Increase", Element::Fire},
    {"dmgcol", "Cold Damage Increase", Element::Cold},         {"dmgpsn", "Poison Damage Increase", Element::Poison},
    {"dmgarc", "Arcane Damage Increase", Element::Arcane},     {"dmglit", "Lightning Damage Increase", Element::Lightning},
    {"dmghol", "Holy Damage Increase", Element::Holy},
};

ElementalAffix const* ElementalAffixOf(std::string const& id)
{
    for (ElementalAffix const& affix : ElementalAffixes)
        if (id == affix.id)
            return &affix;
    return nullptr;
}

// One of the seven, evenly (every class rolls all seven).
ElementalAffix const& RollElemental()
{
    return ElementalAffixes[std::uniform_int_distribution<std::size_t>(0, std::size(ElementalAffixes) - 1)(Engine())];
}

// The secondary pool row "resist" is D3's resistSingle, ONE element's flat
// resistance (reference/d3planner/data_stats.js:116-121), rolled like RollElemental: the pool keeps its one
// row and weight, then an even roll picks the element. "resall" stays its own row. Same record as the
// elemental lines; the value is flat, not a percent.
ElementalAffix const ResistAffixes[] = {
    {"resphy", "Physical Resistance", Element::Physical}, {"resfir", "Fire Resistance", Element::Fire},
    {"rescol", "Cold Resistance", Element::Cold},         {"respsn", "Poison Resistance", Element::Poison},
    {"resarc", "Arcane Resistance", Element::Arcane},     {"reslit", "Lightning Resistance", Element::Lightning},
};

ElementalAffix const* ResistAffixOf(std::string const& id)
{
    for (ElementalAffix const& affix : ResistAffixes)
        if (id == affix.id)
            return &affix;
    return nullptr;
}

ElementalAffix const& RollResist()
{
    return ResistAffixes[std::uniform_int_distribution<std::size_t>(0, std::size(ResistAffixes) - 1)(Engine())];
}

// D3Planner affix id -> our stat sheet bucket (01-stats §2 source 2). Affixes
// with no sheet effect yet (sockets, durability, reduced level requirement,
// chance-on-hit, pickup radius) are deliberately absent and contribute nothing.
// "mainstat" is the pool's primary-attribute group; only the Barbarian exists,
// so it resolves to Strength.
std::unordered_map<std::string, StatMapping> const& Mappings()
{
    static std::unordered_map<std::string, StatMapping> const mappings = []
    {
        std::unordered_map<std::string, StatMapping> table = {
        {"mainstat", {Stat::Strength}}, {"str", {Stat::Strength}}, {"dex", {Stat::Dexterity}},
        {"int", {Stat::Intelligence}}, {"vit", {Stat::Vitality}},
        {"chc", {Stat::CritChance}}, {"chd", {Stat::CritDamage}},
        {"ias", {Stat::AttackSpeed}}, {"weaponias", {Stat::AttackSpeed, Bucket::WeaponLocal}},
        {"cdr", {Stat::CooldownReduction}}, {"rcr", {Stat::ResourceCostReduction}},
        {"area", {Stat::AreaDamage}}, {"armor", {Stat::Armor}},
        {"resall", {Stat::AllResistance}},
        // "Reduces damage from Cold attacks by X%" (data_stats.js colddef, Damage_Type_Percent_Reduction#Cold);
        // the reference has no other element's row.
        {"colddef", {Stat::ElementReduction, Bucket::Flat, Element::Cold}},
        {"life", {Stat::LifePercent}}, {"regen", {Stat::LifeRegen}},
        {"lph", {Stat::LifePerHit}}, {"laek", {Stat::LifePerKill}},
        {"ms", {Stat::MovementSpeed}}, {"thorns", {Stat::Thorns}},
        {"gf", {Stat::GoldFind}}, {"mf", {Stat::MagicFind}}, {"expadd", {Stat::XPBonus, Bucket::FlatXP}},
        // data_stats.js maxfury: Resource_Max_Bonus#Fury, class: "barbarian".
        {"maxfury", {Stat::MaxFury, Bucket::Flat, Element::Physical, "fury"}},
        {"expmul", {Stat::XPBonus}}, {"edmg", {Stat::EliteDamage}}, {"edef", {Stat::EliteReduction}},
        {"wpnphy", {Stat::WeaponFlatDamage}},
        // Block (docs/research/block.md §1): a shield's built-in Base Chance and
        // its Block Amount range are required affixes, "+X% Chance to Block" is a
        // rolled secondary. "blockamountdelta" carries the reference's own delta
        // (block.md §4); dc_common Calculate turns it into the range's maximum.
        {"baseblock", {Stat::BaseBlockChance}}, {"block", {Stat::BlockChance}},
        {"blockamount", {Stat::BlockAmountMin}}, {"blockamountdelta", {Stat::BlockAmountMax}},
        // A legendary's fixed armor line (data_stats.js basearmor, base: true); stats_full.js:559 adds it to armor.
        {"basearmor", {Stat::Armor}},
        // "X% more Fire damage taken" (data_stats.js firetaken, Amplify_Damage_Type_Percent#Fire): stats_full.js:611
        // multiplies the element's damage taken by 1 + X/100, a reduction of -X.
        {"firetaken", {Stat::ElementReduction, Bucket::Flat, Element::Fire, nullptr, true}},
        // Maximum class resource (data_stats.js maxap, maxmana, maxdisc: Resource_Max_Bonus#Arcanum, #Mana,
        // #Discipline), on the class resource maximum the sheet keeps for every class, as maxfury above.
        {"maxap", {Stat::MaxFury, Bucket::Flat, Element::Physical, "arcane_power"}},
        {"maxmana", {Stat::MaxFury, Bucket::Flat, Element::Physical, "mana"}},
        // Maximum Discipline is the Demon Hunter's second resource, whose maximum the sheet keeps apart from the first slot's
        // (Stat::MaxSecond, added to the pool and the skills' bonus by stats/dc_stats.cpp), so it does not raise Hatred's.
        {"maxdisc", {Stat::MaxSecond, Bucket::Flat, Element::Physical, "discipline"}},
        // The Shaman's Totem line (class_item_pools.csv, shaman-grok-v1.4.md 5.1), on the Maelstrom the class resource
        // sheet keeps (class_resources.csv resource_key maelstrom), as the lines above.
        {"maxmaelstrom", {Stat::MaxFury, Bucket::Flat, Element::Physical, "maelstrom"}},
        // And the two lines Shaman 2b gave stats of their own (src/classes/shaman/dc_shaman_maelstrom.cpp reads them): the Totem's
        // "Primary skills generate +1-3 Maelstrom" and the Ritual Mace's "Maelstrom generation +5-10%". No resource gate: the
        // lines roll on Shaman items only and nothing but the Shaman's reader looks at either stat.
        {"primarymaelstrom", {Stat::PrimaryMaelstrom}},
        {"maelstromgen", {Stat::MaelstromGeneration}},
        // Class-resource lines, each on the class data_stats.js names (apoc wizard, lifefury barbarian, spiritregen monk,
        // manaregen witchdoctor), and damage to a monster type on every class; stats/dc_stat_readers.h reads them.
        {"apoc", {Stat::ResourceOnCrit, Bucket::Flat, Element::Physical, "arcane_power"}},
        {"lifefury", {Stat::LifePerFury, Bucket::Flat, Element::Physical, "fury"}},
        {"spiritregen", {Stat::SpiritRegen, Bucket::Flat, Element::Physical, "spirit"}},
        {"manaregen", {Stat::ManaRegen, Bucket::Flat, Element::Physical, "mana"}},
        {"damage_beasts", {Stat::DamageVsBeast}}, {"damage_demons", {Stat::DamageVsDemon}},
        {"damage_undead", {Stat::DamageVsUndead}}, {"damage_humans", {Stat::DamageVsHuman}},
        };
        for (ElementalAffix const& affix : ElementalAffixes)
            table[affix.id] = {Stat::ElementalDamage, Bucket::Flat, affix.element};
        for (ElementalAffix const& affix : ResistAffixes)
            table[affix.id] = {Stat::SingleResistance, Bucket::Flat, affix.element};
        return table;
    }();
    return mappings;
}

// Contribution ids must be stable and unique per affix row so unequip removes
// exactly what equip added. One item never has more than 2^16 rows.
std::uint64_t ContributionId(std::uint64_t itemGuid, unsigned seq)
{
    return (itemGuid << 16) | seq;
}

// False for a class resource's stat on a class without that resource: the line stays on the item and does nothing.
bool Applies(StatMapping const& mapping, Player const* player)
{
    if (!mapping.resource)
        return true;
    std::uint32_t const classId = DC::Classes::ClassIdOf(player);
    for (auto role : {DC::Resources::Data::Role::Primary, DC::Resources::Data::Role::Second})
        if (auto const* row = DC::Resources::Of(classId, role); row && std::string_view(row->key) == mapping.resource)
            return true;
    return false;
}

double Signed(StatMapping const& mapping, double value) { return mapping.negate ? -value : value; }

// Per player, the contributions a cubed power's stat rows put on the sheet (stat and id), so the next
// refresh takes off exactly those. Guarded by bonusMutex.
std::unordered_map<std::uint64_t, std::vector<std::pair<Stat, std::uint64_t>>> cubedStats;
}

using namespace Detail;

std::string ClassKeyOf(unsigned wowClass)
{
    std::lock_guard<std::mutex> lock(dataMutex);
    return ClassKeyOfLocked(wowClass);
}

bool IsUnidentifiedTemplate(std::uint32_t entry)
{
    return IsShellTemplate(entry);
}

double SkillDamageBonus(std::uint64_t playerGuid, std::uint32_t skillId)
{
    if (!skillId)
        return 0;
    std::lock_guard<std::mutex> lock(bonusMutex);
    auto found = skillBonuses.find(playerGuid);
    return found == skillBonuses.end() ? 0 : found->second.Get(skillId);
}

WeaponExtraDamage WeaponExtraDamageOf(std::uint64_t playerGuid, std::uint64_t itemGuid)
{
    std::lock_guard<std::mutex> lock(bonusMutex);
    auto found=weaponExtra.find(playerGuid);
    if(found==weaponExtra.end()) return {};
    auto item=found->second.find(itemGuid);
    return item==found->second.end()? WeaponExtraDamage{} : item->second;
}

std::vector<std::string> WithGrantedPassives(Player const* player, std::vector<std::string> chosen)
{
    std::vector<std::string> granted;
    if (player)
    {
        std::lock_guard<std::mutex> lock(bonusMutex);
        if (auto mine = grantedPassive.find(player->GetGUID().GetRawValue()); mine != grantedPassive.end())
            for (auto const& [item, name] : mine->second)
                granted.push_back(name);
    }
    return DC::GrantedPassive::Merge(std::move(chosen), granted);
}
}
