/*
 * World of DiabloCraft - mod-diablocraft
 *
 * items: the declarations the item files share
 *
 * Internal to src/items: declarations only, no logic. The loaded reference data and its locks, the affix -> stat
 * sheet, the store, the roll, the equip rules and the field socket path that dc_items*.cpp call across files.
 * Other folders include dc_items.h.
 */

#ifndef DC_ITEMS_INTERNAL_H
#define DC_ITEMS_INTERNAL_H

#include "dc_items.h"
#include "dc_quality_rule.h"
#include "dc_relic_rule.h"
#include "dc_skill_bonuses.h"

#include "../stats/dc_stats.h"

#include <cstdint>
#include <mutex>
#include <optional>
#include <random>
#include <set>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace DC::Items::Detail
{
// generate_spells.py emits these two immediately after
// the Health Potion shell; the generator asserts they never renumber. The
// unidentified item template's spellid_1 is the first, so the shells can be
// found by their use spell rather than by an entry range kept in two places.
constexpr std::uint32_t IDENTIFY_ITEM_SPELL = 81203;
constexpr std::uint32_t IDENTIFY_TOME_SPELL = 81204;

// --- loaded reference data ------------------------------------------------
// PoolEntry and Counts live in dc_items.h: PlanRoll takes and returns them, and the
// Blacksmith tooltip test compiles it.

struct BaseItem
{
    std::uint32_t entry = 0;
    std::string d3Id, name, slot, type, rarity;
    std::string designatedClass;
    // Issue #47: the affix id of the designated class's main stat, resolved
    // once at load from class_primary_stats.csv; "" when the item has no
    // designated class, or names one the sheet has no row for (logged).
    std::string mainStat;
    std::vector<std::string> presets;
    // A follower relic (dc_follower_relic_roll): the affix counts it rolls in place of its rarity's; 0 and 0 for any other base.
    unsigned relicPrimary = 0, relicSecondary = 0;
};

// K5: classId/skillId are the join; skill and name are display text.
struct SkillAffix { std::string id, skill, name; std::uint32_t classId = 0, skillId = 0; };

struct GemEffect { std::string stat, name; double value = 0; };

// The amulet and bracers pool row "elemental" is D3's
// exclusive group of seven (reference/d3planner/data_stats.js:24-30, statGroups "elemental"); the roll
// picks one, and every class rolls all seven (D3's per-class lists are not used). The pool keeps its one
// row, so the chance of the line is what it was. The tooltip and the Mystic window name them the same
// (dc_tooltip.lua, dc_crafting.lua ELEMENTAL); test_elemental_affixes.py pins the three to the reference.
struct ElementalAffix
{
    char const* id;
    char const* name;
    Element element;
};
constexpr char const* ELEMENTAL_POOL_ID = "elemental";
constexpr char const* RESIST_POOL_ID = "resist";

// --- affix -> stat sheet ---------------------------------------------------
struct StatMapping
{
    // Every row in Mappings() names its stat and the table is const and only ever
    // read through find(), so this default is unreachable today. It is Count, not
    // Strength, so that an entry added without a stat indexes out of range and is
    // caught, rather than quietly inflating Strength.
    Stat stat = Stat::Count;
    Bucket bucket = Bucket::Flat;
    Element element = Element::Physical;
    // A class resource's own stat (D3's Resource_Max_Bonus#<resource>) reaches the sheet only for a class with that
    // resource (class_resources.csv resource_key); null is every class.
    char const* resource = nullptr;
    // D3's Amplify_Damage_Type_Percent is more damage taken, the opposite of the reduction it lands on.
    bool negate = false;
};

// dc_items_data.cpp: the loaded data and what reads it. dataMutex guards the maps down to gemEffects, bonusMutex
// the per-player ones below it.
extern std::mutex dataMutex;
extern std::unordered_map<std::uint32_t, BaseItem> baseItems;
extern std::unordered_map<std::string, std::unordered_map<std::string, std::vector<PoolEntry>>> pools;
// The pool a base rolls from in one bracket: its slot's, then the lines of its own type (pools["<slot>:<type>"]). The
// caller holds dataMutex. Empty when the slot has no pool in the bracket.
std::vector<PoolEntry> PoolFor(BaseItem const& base, std::string const& bracket);
extern std::unordered_map<std::uint32_t, std::unordered_map<std::string, std::vector<PoolEntry>>> itemPresetRanges;
extern bool dataReady;
// dc_follower_relic_rule relic_ancient_primal: whether a follower relic may roll Ancient and Primal Ancient.
extern bool relicAncientPrimal;
extern std::unordered_map<std::string, SkillAffix> skillAffixes;
extern std::unordered_map<std::string, std::vector<SkillAffix>> skillGroups;
extern std::unordered_map<unsigned, std::string> classKeys;
extern std::unordered_map<std::string, std::uint32_t> classIds;
extern std::unordered_map<std::string, std::string> classMainStats;
extern std::unordered_map<std::uint32_t, std::vector<std::string>> classPassiveNames;
extern std::unordered_map<std::string, std::string> weaponClassByType;
extern std::unordered_map<std::uint32_t, std::unordered_map<std::string, GemEffect>> gemEffects;
extern std::mutex bonusMutex;
extern std::unordered_map<std::uint64_t, SkillBonuses> skillBonuses;
extern std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, WeaponExtraDamage>> weaponExtra;
extern std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, std::string>> grantedPassive;
extern std::unordered_map<std::uint64_t, std::vector<std::pair<Stat, std::uint64_t>>> cubedStats;
bool IsShellTemplate(std::uint32_t entry);
std::string Escape(std::string value);
std::string ClassKey(std::string const& d3Class);
std::string StatAffix(std::string const& stat);
std::set<std::string> ResolveMainStats(std::unordered_map<std::uint32_t, BaseItem>& items,
                                       std::unordered_map<std::string, std::string> const& mainStats);
std::string PrimaryStat(BaseItem const& base, std::string const& affixClass,
                        std::unordered_map<std::string, std::string> const& mainStats);
std::vector<SkillAffix> SkillChoices(std::unordered_map<std::string, std::vector<SkillAffix>> const& groups,
                                     std::string const& groupId, std::string const& affixClass);
std::string ClassKeyOfLocked(unsigned wowClass);
std::string PrimaryName(std::string const& stat);
std::mt19937_64& Engine();
std::vector<std::string> Split(std::string const& text, char separator);
bool Shield(BaseItem const& base);
bool BlockAffix(std::string const& affixId);
bool RequiredShieldAffix(std::string const& affixId);
bool DamageOffhand(BaseItem const& base);
bool OffhandDamageAffix(BaseItem const& base, std::string const& affixId);
bool SpeedQuiver(BaseItem const& base);
bool OffhandSpeedAffix(BaseItem const& base, std::string const& affixId);
extern ElementalAffix const ElementalAffixes[7];
extern ElementalAffix const ResistAffixes[6];
ElementalAffix const* ElementalAffixOf(std::string const& id);
ElementalAffix const& RollElemental();
ElementalAffix const* ResistAffixOf(std::string const& id);
ElementalAffix const& RollResist();
std::unordered_map<std::string, StatMapping> const& Mappings();
std::uint64_t ContributionId(std::uint64_t itemGuid, unsigned seq);
bool Applies(StatMapping const& mapping, Player const* player);
double Signed(StatMapping const& mapping, double value);
// dc_items_store.cpp: the item rows.
std::optional<Instance> Load(std::uint64_t itemGuid);
void Erase(std::uint64_t itemGuid);
// dc_items_roll.cpp: the roll and the quality decision.
extern std::mutex forceMutex;
extern std::unordered_map<std::uint64_t, std::string> forcedQuality;
std::uint64_t LastRolled(std::uint64_t playerGuid);
Counts CountsFor(std::string const& rarity);
std::string BracketFor(std::string const& rarity, std::string const& quality = "normal");
double RollValue(PoolEntry const& entry);
void BackfillPowers(std::uint64_t itemGuid, std::uint32_t baseItem, std::string const& qualityTier);
bool WeaponDamageAffix(std::string const& id);
double RollWeaponDelta(PoolEntry const& entry);
DC::Quality::Rule QualityRule();
bool PrimalUnlocked(Player* player);
// dc_items_equip.cpp: the stat sheet's contributions and the equip rules.
void Apply(Player* player, Item* item, bool equipping);
bool UniqueEquippedAllows(Player* player, uint8 slot, Item* item);
bool MadeEquipAllows(Player* player, uint8 slot, Item* item);
// dc_items_gems.cpp: the field socket path.
void NeedItem(bool ok, char const* message);
void SocketInField(Player* player, std::uint32_t itemGuid, std::uint32_t gemGuid);
}

#endif
