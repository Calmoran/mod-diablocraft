#ifndef DC_COMMON_H
#define DC_COMMON_H

#include <array>
#include <limits>
#include <cstdint>
#include <string>
#include <vector>

namespace DC
{
enum class Source : unsigned { Base, Items, Gems, Paragon, Augments, Passives, Temporary, Count };
enum class Element : unsigned { Physical, Fire, Cold, Lightning, Poison, Arcane, Holy, Count };
enum class Stat : unsigned
{
    Strength, Dexterity, Intelligence, Vitality, CritChance, CritDamage,
    AttackSpeed, CooldownReduction, ResourceCostReduction, AreaDamage,
    ElementalDamage, AllResistance, Armor, LifePerHit, LifePerKill,
    LifeRegen, LifePercent, MovementSpeed, Thorns, MagicFind, GoldFind, XPBonus,
    MaxFury,
    // Extra inputs required by the formulas, not additional gameplay systems.
    SingleResistance, SpecificReduction, WeaponAPS,
    EliteDamage, WeaponFlatDamage, GoldPickupRange,
    // Block (mitigation.csv Shield Block, docs/research/block.md). Two stats
    // to a player - Block Chance and Block Amount - but four slots: D3 caps
    // a shield's built-in Base Chance separately from the rolled +X% extras,
    // and Block Amount is a MIN-MAX range a hit rolls inside, not one number.
    BaseBlockChance, BlockChance, BlockAmountMin, BlockAmountMax,
    // Appended, never inserted: a saved contribution holds this enum's value.
    // The offhand's base attacks per second, published only while one is
    // equipped. D3 keeps a speed per hand (stats_full.js:673-675) and the
    // Whirlwind channel swings them alternately.
    OffhandWeaponAPS,
    // The offhand weapon's own attack-speed affix. D3 reads a weapon's
    // `weaponias` off that weapon (stats_full.js:331), so the two hands do
    // not share one: an affix on the offhand must not speed the main hand.
    OffhandWeaponIAS,
    // Damage taken from one element reduced by this percent (D3's
    // Damage_Type_Percent_Reduction#<element>, d3planner "colddef"). Keyed by
    // element like SingleResistance; same-element rows multiply like every
    // other reduction and land in StatSheet::elementReduction.
    ElementReduction,
    // Damage taken from elites reduced by this percent (D3's
    // Damage_Percent_Reduction_From_Elites, d3planner "edef", a `dr` stat:
    // two sources multiply). Read by Combat::Mitigate when the attacker is an
    // elite.
    EliteReduction,
    // Flat weapon damage (jewelry and offhand, D3's "+min-max Damage") is a minimum plus a delta, as Block Amount is:
    // WeaponFlatDamage joins both ends of the swing and this delta only the high end, so a ring's max is min + delta
    // (damage_formula.csv step 1). A flat number with no range (a gem, a set) is WeaponFlatDamage alone.
    WeaponFlatDamageDelta,
    // Class-resource and monster-type affixes (d3planner data_stats.js), appended with sheet save version 10. Each is a flat sum.
    // ResourceOnCrit: Arcane Power per critical hit (apoc, Resource_On_Crit#Arcanum). LifePerFury: Life per Fury spent
    // (lifefury, Spending_Resource_Heals_Percent#Fury). SpiritRegen and ManaRegen: the resource's points a second on top of
    // the class's own (spiritregen, manaregen, Resource_Regen_Per_Second). DamageVs*: percent damage dealt to that creature
    // type (damage_beasts, damage_demons, damage_undead, damage_humans, Damage_Percent_Bonus_Vs_Monster_Type). Readers:
    // stats/dc_stat_readers.h.
    ResourceOnCrit, LifePerFury, SpiritRegen, ManaRegen, DamageVsBeast, DamageVsDemon, DamageVsUndead, DamageVsHuman,
    // The Shaman's Maelstrom generation lines, appended with sheet save version 11. MaelstromGeneration: percent more Maelstrom
    // from every generating skill. PrimaryMaelstrom: points more Maelstrom from each Primary skill. Each is a flat sum. Reader:
    // classes/shaman/dc_shaman_maelstrom.cpp.
    MaelstromGeneration, PrimaryMaelstrom,
    // Maximum of a class's second resource from gear (the Demon Hunter's Discipline, data_stats.js maxdisc), appended with sheet save
    // version 12: points on top of the pool and the skills' bonus (classes/dc_resource_pool.h). A flat sum; MaxFury is the first
    // slot's alone. Reader: stats/dc_stats.cpp.
    MaxSecond, Count
};
// Derived: the one bucket that is not accumulated. Resource Cost Reduction is
// charged by the core's SPELLMOD_COST auras, whose amounts are whole percent,
// so the reduction a player pays with is not the product of the sheet's own
// contributions and cannot be reached by adding another factor to them. The
// combat module measures what those auras do to a probe cost and publishes it
// in this bucket; Calculate then shows that number instead of the product
// (the display shows the paying aura's value).
// Step 6 gives Cooldown Reduction the same treatment, for the same reason: the
// cooldown is the core's now and the gear reduction is a SPELLMOD_COOLDOWN
// aura carrying whole percent, so the sheet shows what that aura takes off.
enum class Bucket : unsigned { Flat, Percent, WeaponLocal, Uncapped, FlatXP, Derived, Count };
constexpr unsigned StatCount = static_cast<unsigned>(Stat::Count);
constexpr unsigned ElementCount = static_cast<unsigned>(Element::Count);
constexpr unsigned Index(Stat stat) { return static_cast<unsigned>(stat); }
constexpr unsigned Index(Element element) { return static_cast<unsigned>(element); }

// NaN means unset; Calculate resolves missing inputs from dc_block_tuning.
struct BlockTuning
{
    double baseChanceCap = std::numeric_limits<double>::quiet_NaN();
    double totalChanceCap = std::numeric_limits<double>::quiet_NaN();
    double amountPercentScale = std::numeric_limits<double>::quiet_NaN();
};

struct BaseStats
{
    unsigned level = 1;
    double strength = 0, dexterity = 0, intelligence = 0, vitality = 0;
    // maxFury is the class's resource maximum: Fury for the Barbarian, Arcane
    // Power for the Wizard (the base sheet's resource column). The name and
    // Stat::MaxFury stay because a saved sheet holds the enum's value.
    double baseLife = 0, lifePerVitality = 0, baseArmor = 0, maxFury = std::numeric_limits<double>::quiet_NaN();
    // The class's own rules, from class_primary_stats.csv and class_map.csv.
    // NaN falls back to the Barbarian's numeric
    // rules and the main stat defaults to Strength, so a base that names no
    // class computes exactly what it did before the sheet was class-keyed.
    // The fallback is reported once (SetClassRuleFallbackNotice), not silent.
    double classDRPct = std::numeric_limits<double>::quiet_NaN();
    double allResPerInt = std::numeric_limits<double>::quiet_NaN();
    Stat mainStat = Stat::Strength;
};

// id identifies an individual affix/buff. Updating the same key replaces it;
// distinct IDs remain separate multiplicative CDR/RCR/DR factors.
struct Contribution
{
    Source source = Source::Items;
    Stat stat = Stat::Strength;
    std::uint64_t id = 0;
    double value = 0;
    Bucket bucket = Bucket::Flat;
    Element element = Element::Physical;
};

struct StatSheet
{
    unsigned level = 1;
    std::array<double, StatCount> values{};
    std::array<double, ElementCount> elementalDamage{}, resistance{}, resistanceDR{}, damageTaken{};
    // Stat::ElementReduction per element, as a percent; already folded into damageTaken.
    std::array<double, ElementCount> elementReduction{};
    double maxLife = 0, armorDR = 0, classDR = 0; // populated from the sourced class rule by Calculate

    double weaponIAS = 0, attacksPerSecond = 0, flatXP = 0;
    // The offhand's own attacks per second, 0 when there is no offhand. Same
    // construction as attacksPerSecond above, from the offhand's base speed
    // and that weapon's own attack-speed affix.
    double offhandAttacksPerSecond = 0, offhandWeaponIAS = 0;
    double operator[](Stat stat) const { return values[Index(stat)]; }
};

struct CharacterStats
{
    StatSheet sheet;
    std::vector<Contribution> contributions;
    // Current Life is held as a share of max Life, so it survives a max Life
    // that changes while the character is offline or that other sources raise
    // after login. 0 means no saved D3 Life yet: the character starts full.
    double lifeShare = 0;
};

void Validate(Contribution const& contribution);
void SetContribution(CharacterStats& character, Contribution const& contribution);
void RemoveContribution(CharacterStats& character, Source source, Stat stat, std::uint64_t id);
// Calculate calls this once per process for
// each class rule it had to take from the Barbarian's numbers because the base
// named no class ("class_dr_pct", "all_res_per_int"), instead of doing so
// silently. The server installs a logger (dc_stats.cpp); pure-math tests leave
// it unset, which keeps the fallback silent there.
using ClassRuleFallbackNotice = void (*)(char const* rule);
void SetClassRuleFallbackNotice(ClassRuleFallbackNotice notice);
StatSheet Calculate(BaseStats const& base, std::vector<Contribution> const& contributions,
                    BlockTuning const& block = BlockTuning{});
std::string Serialize(StatSheet const& sheet);
StatSheet DeserializeSheet(std::string const& saved);
std::string Serialize(std::vector<Contribution> const& contributions);
std::vector<Contribution> DeserializeContributions(std::string const& saved);
// What a load keeps of the saved contributions: Paragon's are rebuilt from dc_character_paragon by
// its login hook, and a Temporary one belongs to a buff whose end no longer runs after a logout, so both are dropped;
// every other source is kept as saved.
void DropRebuiltSources(std::vector<Contribution>& contributions);
}

#endif // DC_COMMON_H
