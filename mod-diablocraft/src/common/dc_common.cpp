// Constant (4294967040.0): Maximum health safely representable by core float/uint32; Representation bound.
// Constant (17): Double serialization precision; Round-trip numeric persistence; same value in contribution serializer.
// Constant (100000): Maximum serialized contribution count; Input-size guard, not a game balance cap.
#include "dc_common.h"
#include "dc_numeric_data.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <optional>
#include <sstream>
#include <stdexcept>

namespace DC
{
namespace
{
void Require(bool condition, char const* message)
{
    if (!condition)
        throw std::invalid_argument(message);
}

bool PercentStat(Stat stat)
{
    return stat == Stat::Strength || stat == Stat::Dexterity || stat == Stat::Intelligence ||
        stat == Stat::Armor || stat == Stat::LifeRegen || stat == Stat::Thorns ||
        // Tal Rasha's Elements 4-piece: "increase all of your resistances by 100%" is a percent of every resistance.
        stat == Stat::AllResistance ||
        // block.md §5-§6: Block Amount scales by nothing but item tier and a
        // %-Block Amount affix (Hallowed Bulwark's Iron Skin), so it is the one
        // block slot with a percentage bucket.
        stat == Stat::BlockAmountMin || stat == Stat::BlockAmountMax;
}

void CheckSheet(StatSheet const& sheet)
{
    Require(sheet.level >= 1 && sheet.level <= NumericData::MaximumLevel(), "Level outside sourced base-stat range");
    for (double value : sheet.values)
        Require(std::isfinite(value) && value >= 0, "Invalid or overflowing stat value");
    for (auto const* array : {&sheet.elementalDamage, &sheet.resistance, &sheet.resistanceDR, &sheet.damageTaken})
        for (double value : *array)
            Require(std::isfinite(value) && value >= 0, "Invalid elemental value");
    // An element's reduction goes below 0 when gear makes it hit harder (Validate).
    for (double value : sheet.elementReduction)
        Require(std::isfinite(value) && value <= 100, "Invalid element reduction");
    Require(std::isfinite(sheet.maxLife) && sheet.maxLife >= 1 &&
        sheet.maxLife <= 4294967040.0, "Max Life exceeds safe uint32/float core health range");
    for (double value : {sheet.armorDR, sheet.classDR, sheet.weaponIAS, sheet.attacksPerSecond,
                         sheet.offhandAttacksPerSecond, sheet.offhandWeaponIAS, sheet.flatXP})
        Require(std::isfinite(value) && value >= 0, "Invalid derived value");
    for (Stat stat : {Stat::Strength, Stat::Dexterity, Stat::Intelligence, Stat::Vitality, Stat::Armor})
        Require(sheet[stat] <= std::numeric_limits<std::int32_t>::max(), "Stat exceeds core display range");
    for (double resistance : sheet.resistance)
        Require(resistance <= std::numeric_limits<std::int32_t>::max(), "Resistance exceeds core display range");
    Require(sheet[Stat::MaxFury] * 10 <= std::numeric_limits<std::int32_t>::max(), "Max Fury exceeds core power range");
}

template<typename T> void Read(std::istream& stream, T& value)
{
    if (!(stream >> value))
        throw std::invalid_argument("Malformed saved D3 stat record");
}
void End(std::istream& stream)
{
    stream >> std::ws;
    Require(stream.eof(), "Unexpected data in saved D3 stat record");
}
}

void Validate(Contribution const& c)
{
    Require(c.source > Source::Base && c.source < Source::Count, "Base is read-only; invalid contribution source");
    Require(c.stat < Stat::Count && c.bucket < Bucket::Count && c.element < Element::Count, "Invalid contribution key");
    Require(std::isfinite(c.value), "Contribution must be finite");
    if (c.bucket == Bucket::Percent)
        Require(PercentStat(c.stat), "This stat has no additive percentage multiplier bucket");
    if (c.bucket == Bucket::WeaponLocal)
        Require(c.stat == Stat::AttackSpeed || c.stat == Stat::OffhandWeaponIAS,
                "Weapon-local bucket is only for IAS, on one hand or the other");
    if (c.bucket == Bucket::Uncapped)
        Require(c.stat == Stat::MovementSpeed, "Uncapped bucket is only for movement skill/proc bonuses");
    if (c.bucket == Bucket::FlatXP)
        Require(c.stat == Stat::XPBonus, "Flat XP bucket is only for XP");
    if (c.bucket == Bucket::Derived)
        Require(c.stat == Stat::ResourceCostReduction || c.stat == Stat::CooldownReduction,
                "Derived bucket is only for the measured cost and cooldown reductions");
    if (c.stat != Stat::ElementalDamage && c.stat != Stat::SingleResistance && c.stat != Stat::ElementReduction)
        Require(c.element == Element::Physical, "Element is only valid for elemental damage, single resistance or element reduction");
    if (c.stat == Stat::CooldownReduction || c.stat == Stat::ResourceCostReduction || c.stat == Stat::SpecificReduction ||
        c.stat == Stat::EliteReduction)
        Require(c.value >= 0 && c.value <= 100, "Reduction must be between 0 and 100 percent");
    // Below 0 is more of that element taken (D3's Amplify_Damage_Type_Percent, d3planner firetaken).
    if (c.stat == Stat::ElementReduction)
        Require(c.value >= -100 && c.value <= 100, "Element reduction must be between -100 and 100 percent");
}

void SetContribution(CharacterStats& character, Contribution const& contribution)
{
    Validate(contribution);
    auto found = std::find_if(character.contributions.begin(), character.contributions.end(), [&](Contribution const& c)
    {
        return c.source == contribution.source && c.stat == contribution.stat && c.id == contribution.id &&
            c.bucket == contribution.bucket && c.element == contribution.element;
    });
    if (found == character.contributions.end())
        character.contributions.push_back(contribution);
    else
        *found = contribution;
}

void RemoveContribution(CharacterStats& character, Source source, Stat stat, std::uint64_t id)
{
    auto& entries = character.contributions;
    entries.erase(std::remove_if(entries.begin(), entries.end(), [&](Contribution const& c)
        { return c.source == source && c.stat == stat && c.id == id; }), entries.end());
}

namespace
{
std::atomic<ClassRuleFallbackNotice> fallbackNotice{nullptr};
std::atomic<bool> drFallbackNamed{false}, resFallbackNamed{false};

// The first fallback for each rule is reported; later ones stay quiet, so a
// recompute on every hit cannot flood the log.
void NoteFallback(std::atomic<bool>& named, char const* rule)
{
    if (auto notice = fallbackNotice.load(); notice && !named.exchange(true))
        notice(rule);
}
}

void SetClassRuleFallbackNotice(ClassRuleFallbackNotice notice)
{
    fallbackNotice.store(notice);
}

StatSheet Calculate(BaseStats const& base, std::vector<Contribution> const& contributions,
                    BlockTuning const& blockInput)
{
    auto block = blockInput;
    if (std::isnan(block.baseChanceCap) || std::isnan(block.totalChanceCap) || std::isnan(block.amountPercentScale))
    {
        auto defaults = NumericData::Block();
        if (std::isnan(block.baseChanceCap)) block.baseChanceCap = defaults.baseChanceCap;
        if (std::isnan(block.totalChanceCap)) block.totalChanceCap = defaults.totalChanceCap;
        if (std::isnan(block.amountPercentScale)) block.amountPercentScale = defaults.amountPercentScale;
    }
    Require(std::isfinite(block.baseChanceCap) && block.baseChanceCap >= 0 &&
        std::isfinite(block.totalChanceCap) && block.totalChanceCap >= 0 &&
        std::isfinite(block.amountPercentScale) && block.amountPercentScale >= 0, "Invalid block tuning");
    Require(base.level >= 1 && base.level <= NumericData::MaximumLevel(), "Level outside sourced base-stat range");
    Require(base.baseArmor == base.strength + base.dexterity, "CSV base_armor must equal base Strength + Dexterity");
    StatSheet sheet;
    sheet.level = base.level;
    Require(base.mainStat == Stat::Strength || base.mainStat == Stat::Dexterity ||
        base.mainStat == Stat::Intelligence, "Main stat must be Strength, Dexterity or Intelligence");
    if (std::isnan(base.classDRPct)) NoteFallback(drFallbackNamed, "class_dr_pct");
    if (std::isnan(base.allResPerInt)) NoteFallback(resFallbackNamed, "all_res_per_int");
    sheet.classDR = (std::isnan(base.classDRPct) ? NumericData::Rule("class_dr_pct") : base.classDRPct) / 100;
    double const allResPerInt = std::isnan(base.allResPerInt) ? NumericData::Rule("all_res_per_int") : base.allResPerInt;
    auto& values = sheet.values;
    values[Index(Stat::Strength)] = base.strength;
    values[Index(Stat::Dexterity)] = base.dexterity;
    values[Index(Stat::Intelligence)] = base.intelligence;
    values[Index(Stat::Vitality)] = base.vitality;
    values[Index(Stat::CritChance)] = NumericData::Rule("crit_chance_pct");
    values[Index(Stat::CritDamage)] = NumericData::Rule("crit_damage_pct");
    values[Index(Stat::MaxFury)] = std::isnan(base.maxFury) ? NumericData::BaseFury(base.level) : base.maxFury;
    std::array<double, StatCount> percent{};
    double cooldown = 1, cost = 1, specific = 1, elite = 1, cappedMovement = 0;
    std::array<double, ElementCount> elementTaken;
    elementTaken.fill(1);
    // The measured reductions, if the combat module published them: what the
    // player's own spell modifiers actually take off a cost and off a
    // cooldown, rather than the product of the sheet's own rows.
    std::optional<double> measuredCost, measuredCooldown;
    // Group by the documented source order; addition and independent reduction
    // factors are otherwise order-independent. No contribution is applied per hit.
    for (unsigned source = 1; source < static_cast<unsigned>(Source::Count); ++source)
        for (Contribution const& c : contributions)
        {
            Validate(c);
            if (static_cast<unsigned>(c.source) != source)
                continue;
            auto index = Index(c.stat);
            if (c.bucket == Bucket::Percent) { percent[index] += c.value; continue; }
            // A weapon's own attack speed stays on that weapon's hand.
            if (c.bucket == Bucket::WeaponLocal)
            {
                (c.stat == Stat::OffhandWeaponIAS ? sheet.offhandWeaponIAS : sheet.weaponIAS) += c.value;
                continue;
            }
            if (c.bucket == Bucket::FlatXP) { sheet.flatXP += c.value; continue; }
            if (c.bucket == Bucket::Derived)
            {
                (c.stat == Stat::CooldownReduction ? measuredCooldown : measuredCost) = c.value;
                continue;
            }
            if (c.stat == Stat::CooldownReduction) { cooldown *= 1 - c.value / 100; continue; }
            if (c.stat == Stat::ResourceCostReduction) { cost *= 1 - c.value / 100; continue; }
            if (c.stat == Stat::SpecificReduction) { specific *= 1 - c.value / 100; continue; }
            if (c.stat == Stat::EliteReduction) { elite *= 1 - c.value / 100; continue; }
            if (c.stat == Stat::ElementReduction) { elementTaken[Index(c.element)] *= 1 - c.value / 100; continue; }
            if (c.stat == Stat::ElementalDamage) { sheet.elementalDamage[Index(c.element)] += c.value; continue; }
            if (c.stat == Stat::SingleResistance) { sheet.resistance[Index(c.element)] += c.value; continue; }
            if (c.stat == Stat::MovementSpeed && c.bucket != Bucket::Uncapped &&
                (c.source == Source::Items || c.source == Source::Gems || c.source == Source::Paragon))
            { cappedMovement += c.value; continue; }
            values[index] += c.value;
        }
    for (Stat stat : {Stat::Strength, Stat::Dexterity, Stat::Intelligence})
        values[Index(stat)] *= 1 + percent[Index(stat)] / 100;
    values[Index(Stat::Armor)] = (sheet[Stat::Armor] + sheet[Stat::Strength] + sheet[Stat::Dexterity]) *
        (1 + percent[Index(Stat::Armor)] / 100);
    values[Index(Stat::LifeRegen)] *= 1 + percent[Index(Stat::LifeRegen)] / 100;
    // stats.csv Thorns: Sheet_Thorns * (1 + Primary_Stat / 100), the class's
    // own main stat - Strength for the Barbarian, Intelligence for the Wizard.
    values[Index(Stat::Thorns)] *= (1 + percent[Index(Stat::Thorns)] / 100) * (1 + sheet[base.mainStat] / 100);
    values[Index(Stat::AllResistance)] += sheet[Stat::Intelligence] * allResPerInt;
    // block.md §4: the reference stores Block Amount as a minimum plus a delta,
    // so the max shown on the item is that minimum plus what the delta rolled.
    // The delta arrives in the max slot; adding the minimum turns it into one.
    values[Index(Stat::BlockAmountMax)] += sheet[Stat::BlockAmountMin];
    for (Stat stat : {Stat::BlockAmountMin, Stat::BlockAmountMax})
        values[Index(stat)] *= 1 + percent[Index(stat)] * block.amountPercentScale / 100;
    // block.md §5: a shield's built-in Base Chance is clamped first, the rolled
    // +X% extras add on top, and the total is clamped again. Both caps are the
    // D3Planner sheet model, not a published figure, so both are tunables.
    values[Index(Stat::BlockChance)] = std::clamp(
        std::min(sheet[Stat::BaseBlockChance], block.baseChanceCap) + sheet[Stat::BlockChance],
        0.0, block.totalChanceCap);
    values[Index(Stat::CritChance)] = std::clamp(sheet[Stat::CritChance], 0.0, 100.0);
    values[Index(Stat::CooldownReduction)] = measuredCooldown ? *measuredCooldown : (1 - cooldown) * 100;
    // What the player pays with is what the auras charge, when the module has
    // measured it; the product of the sheet's own contributions is what those
    // auras are built from, and is the answer until it has.
    values[Index(Stat::ResourceCostReduction)] = measuredCost ? *measuredCost : (1 - cost) * 100;
    values[Index(Stat::SpecificReduction)] = (1 - specific) * 100;
    values[Index(Stat::EliteReduction)] = (1 - elite) * 100;
    values[Index(Stat::MovementSpeed)] += std::clamp(cappedMovement, 0.0, NumericData::Rule("movement_cap_pct"));
    values[Index(Stat::MagicFind)] = std::clamp(sheet[Stat::MagicFind], 0.0, NumericData::Rule("magic_find_cap_pct"));
    values[Index(Stat::GoldFind)] = std::clamp(sheet[Stat::GoldFind], 0.0, NumericData::Rule("gold_find_cap_pct"));
    if (base.level == NumericData::Rule("xp_penalty_level"))
        values[Index(Stat::XPBonus)] /= NumericData::Rule("xp_divisor");
    // A future weapon source supplies base APS and the optional +15% dual-wield
    // contribution to sheet IAS. Zero APS means no weapon source is configured.
    sheet.attacksPerSecond = std::min(NumericData::Rule("attack_speed_cap"), sheet[Stat::WeaponAPS] * (1 + sheet.weaponIAS / 100) * (1 + sheet[Stat::AttackSpeed] / 100));
    // The offhand is the same sum on the other hand's base speed, and is zero
    // while nothing is in it (D3 calls calcWeapon once per hand,
    // stats_full.js:673-675, with the dual-wield 15 % inside the shared IAS).
    sheet.offhandAttacksPerSecond = sheet[Stat::OffhandWeaponAPS] > 0
        ? std::min(NumericData::Rule("attack_speed_cap"), sheet[Stat::OffhandWeaponAPS] * (1 + sheet.offhandWeaponIAS / 100) * (1 + sheet[Stat::AttackSpeed] / 100))
        : 0.0;
    sheet.maxLife = std::floor((base.baseLife + sheet[Stat::Vitality] * base.lifePerVitality) * (1 + sheet[Stat::LifePercent] / 100));
    sheet.armorDR = sheet[Stat::Armor] / (sheet[Stat::Armor] + NumericData::Rule("armor_level_coefficient") * base.level);
    for (unsigned element = 0; element < ElementCount; ++element)
    {
        sheet.resistance[element] += sheet[Stat::AllResistance];
        sheet.resistance[element] *= 1 + percent[Index(Stat::AllResistance)] / 100;
        sheet.resistanceDR[element] = sheet.resistance[element] / (sheet.resistance[element] + NumericData::Rule("resistance_level_coefficient") * base.level);
        sheet.elementReduction[element] = (1 - elementTaken[element]) * 100;
        sheet.damageTaken[element] = (1 - sheet.armorDR) * (1 - sheet.resistanceDR[element]) * (1 - sheet.classDR) * specific *
            elementTaken[element];
    }
    CheckSheet(sheet);
    return sheet;
}

std::string Serialize(StatSheet const& sheet)
{
    CheckSheet(sheet);
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::setprecision(17) << "12 " << sheet.level << ' ' << sheet.maxLife << ' ' << sheet.armorDR << ' '
        << sheet.classDR << ' ' << sheet.weaponIAS << ' ' << sheet.attacksPerSecond << ' ' << sheet.flatXP
        << ' ' << sheet.offhandAttacksPerSecond << ' ' << sheet.offhandWeaponIAS;
    for (double value : sheet.values) out << ' ' << value;
    for (auto const* array : {&sheet.elementalDamage, &sheet.resistance, &sheet.resistanceDR, &sheet.damageTaken,
                              &sheet.elementReduction})
        for (double value : *array) out << ' ' << value;
    return out.str();
}

StatSheet DeserializeSheet(std::string const& saved)
{
    std::istringstream in(saved);
    in.imbue(std::locale::classic());
    unsigned version;
    Read(in, version);
    Require(version >= 1 && version <= 12, "Unknown saved D3 sheet version");
    StatSheet sheet;
    Read(in, sheet.level); Read(in, sheet.maxLife); Read(in, sheet.armorDR); Read(in, sheet.classDR);
    Read(in, sheet.weaponIAS); Read(in, sheet.attacksPerSecond); Read(in, sheet.flatXP);
    // Version 5 added the offhand's own attacks per second and version 6 that
    // weapon's own attack-speed affix; before them there was one speed and one
    // weapon IAS for both hands, and a reloaded character gets the other hand
    // at its next recomputation.
    if (version >= 5) Read(in, sheet.offhandAttacksPerSecond);
    if (version >= 6) Read(in, sheet.offhandWeaponIAS);
    // Version 1 predates normal weapon-gem inputs. Their appended enum values
    // default to zero when an existing character is loaded.
    unsigned savedStatCount = version == 1 ? Index(Stat::EliteDamage)
        : version == 2 ? Index(Stat::GoldPickupRange)
        : version == 3 ? Index(Stat::BaseBlockChance)
        : version == 4 ? Index(Stat::OffhandWeaponAPS)
        : version == 5 ? Index(Stat::OffhandWeaponIAS)
        : version == 6 ? Index(Stat::ElementReduction)
        : version == 7 ? Index(Stat::EliteReduction)
        : version == 8 ? Index(Stat::WeaponFlatDamageDelta)
        : version == 9 ? Index(Stat::ResourceOnCrit)
        : version == 10 ? Index(Stat::MaelstromGeneration)
        : version == 11 ? Index(Stat::MaxSecond) : StatCount;
    for (unsigned i = 0; i < savedStatCount; ++i) Read(in, sheet.values[i]);
    for (auto* array : {&sheet.elementalDamage, &sheet.resistance, &sheet.resistanceDR, &sheet.damageTaken})
        for (double& value : *array) Read(in, value);
    // Version 7 added the element reductions; an older save had none, and its
    // damageTaken already says so.
    if (version >= 7)
        for (double& value : sheet.elementReduction) Read(in, value);
    End(in);
    CheckSheet(sheet);
    return sheet;
}

std::string Serialize(std::vector<Contribution> const& contributions)
{
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::setprecision(17) << "1 " << contributions.size();
    for (auto const& c : contributions)
    {
        Validate(c);
        out << ' ' << static_cast<unsigned>(c.source) << ' ' << Index(c.stat) << ' ' << c.id << ' '
            << c.value << ' ' << static_cast<unsigned>(c.bucket) << ' ' << Index(c.element);
    }
    return out.str();
}

std::vector<Contribution> DeserializeContributions(std::string const& saved)
{
    std::istringstream in(saved);
    in.imbue(std::locale::classic());
    unsigned version, count;
    Read(in, version); Read(in, count);
    Require(version == 1 && count <= 100000, "Unknown or oversized saved D3 contributions");
    CharacterStats character;
    for (unsigned i = 0; i < count; ++i)
    {
        unsigned source, stat, bucket, element;
        Contribution c;
        Read(in, source); Read(in, stat); Read(in, c.id); Read(in, c.value); Read(in, bucket); Read(in, element);
        c.source = static_cast<Source>(source); c.stat = static_cast<Stat>(stat);
        c.bucket = static_cast<Bucket>(bucket); c.element = static_cast<Element>(element);
        SetContribution(character, c);
    }
    Require(character.contributions.size() == count, "Duplicate saved D3 contribution key");
    End(in);
    return character.contributions;
}

void DropRebuiltSources(std::vector<Contribution>& contributions)
{
    contributions.erase(std::remove_if(contributions.begin(), contributions.end(),
                                       [](Contribution const& c)
                                       { return c.source == Source::Paragon || c.source == Source::Temporary; }),
                        contributions.end());
}
}
