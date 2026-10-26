/*
 * The character sheet's Resource Cost Reduction, and what a cast is charged
 * after an item changes it (spell rewrite step 5, PM corrections 1 and 2 of
 * the final round).
 *
 * The core charges what the SPELLMOD_COST auras say, and a spell modifier's
 * amount is whole percent, so the reduction a player pays with is not the
 * product of the sheet's own contributions: gear 33.4 pays 33. The sheet
 * therefore shows the measured number itself, published in `Bucket::Derived`,
 * and this harness proves that end to end without a model of either side. It
 * compiles the module's own `src/common/dc_common.cpp` - the real Calculate -
 * and takes the applied total out of the core's own Player::ApplySpellMod,
 * extracted from the pin plus core-patches/0014 exactly as `core_shim.h`
 * describes.
 *
 * It runs the sequence Passives::RefreshModifiers runs, twice, because a
 * derived contribution read back as an input is how a display feeds itself:
 *
 *     remove the derived contribution
 *     recompute, so the sheet is gear and paragon alone
 *     read that; the whole percent of it is what the gear aura carries
 *     ask the core what the player's auras make of a probe cost
 *     publish that measured number, recompute
 *
 * The `equip` case then adds a gear contribution the way an item does, runs
 * the same refresh, and puts a real cast through the core before and after -
 * which is what proves the next cast pays the new reduction and not the aura
 * the player was wearing a moment ago.
 *
 * The only thing stubbed is NumericData, which reads the world database in
 * the server. Nothing on the Resource Cost Reduction path uses a rule; the
 * stub exists so Calculate's other stats stay finite and its checks pass.
 *
 *     display_harness <cases.tsv>
 *
 * cases.tsv:
 *   display <gear percent> <passive percent...>
 *     -> applied, what the sheet shows, what it shows after a second refresh
 *   equip <gear percent> <ring percent> <passive percent...>
 *     -> shown before, Fury a 25 Fury cast costs before,
 *        shown after, Fury the same cast costs after
 *   hands <main base aps> <main local ias> <off base aps> <off local ias> <ias>
 *     -> the two hands' attacks per second, out of the same Calculate
 *   cooldown <gear percent> <probe milliseconds>
 *     -> applied, what the sheet shows, what it shows after a second refresh
 *
 * The `cooldown` case is step 6's half of the same story: the cooldown is the
 * core's now and the gear reduction is a SPELLMOD_COOLDOWN aura carrying whole
 * percent, so the sheet shows what that aura takes off the module's own probe
 * duration - and, run twice, still does.
 */

#include "core_shim.h"
#include "../../src/common/dc_common.h"
#include "../../src/common/dc_numeric_data.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace DC::NumericData
{
    double Rule(char const* name)
    {
        static std::map<std::string, double> const rules{{"class_dr_pct", 30},
                                                         {"crit_chance_pct", 5},
                                                         {"crit_damage_pct", 50},
                                                         {"all_res_per_int", 0.1},
                                                         {"armor_level_coefficient", 50},
                                                         {"resistance_level_coefficient", 5},
                                                         {"movement_cap_pct", 25},
                                                         {"magic_find_cap_pct", 300},
                                                         {"gold_find_cap_pct", 300},
                                                         {"xp_penalty_level", 0},
                                                         {"xp_divisor", 1},
                                                         {"attack_speed_cap", 5}};
        auto found = rules.find(name);
        if (found == rules.end())
            throw std::runtime_error(std::string("the harness has no stub for rule ") + name);
        return found->second;
    }

    unsigned MaximumLevel()
    {
        return 70;
    }
    double BaseFury(unsigned)
    {
        return 100;
    }
    BlockTuning Block()
    {
        return BlockTuning{30, 75, 1};
    }
} // namespace DC::NumericData

namespace
{
    using namespace DC;

    constexpr std::uint64_t GEAR_AURA = 82403;    // the derived contribution's key
    constexpr std::uint64_t COOLDOWN_AURA = 82406; // and the cooldown one's
    constexpr std::uint64_t ITEM_AFFIX = 1;
    constexpr std::uint64_t RING_AFFIX = 2;
    constexpr double CAST_FURY = 25;

    BaseStats Character()
    {
        BaseStats base;
        base.level = 60;
        base.strength = 100;
        base.dexterity = 50;
        base.vitality = 100;
        base.baseArmor = base.strength + base.dexterity;
        base.baseLife = 1000;
        base.lifePerVitality = 10;
        base.maxFury = 100;
        return base;
    }

    double Sheet(std::vector<Contribution> const& contributions)
    {
        return Calculate(Character(), contributions)[Stat::ResourceCostReduction];
    }

    // Every percentage the player's SPELLMOD_COST auras carry: the gear and
    // paragon total the sheet holds, and each passive's own.
    std::vector<double> Auras(double gear, std::vector<double> const& passives)
    {
        std::vector<double> percents{gear};
        percents.insert(percents.end(), passives.begin(), passives.end());
        return percents;
    }

    // One pass of Passives::RefreshModifiers over these contributions.
    // Returns what the core applies and what the sheet then shows.
    std::pair<double, double> Refresh(std::vector<Contribution>& contributions, std::vector<double> const& passives)
    {
        CharacterStats character;
        character.contributions = contributions;
        RemoveContribution(character, Source::Temporary, Stat::ResourceCostReduction, GEAR_AURA);
        double const gear = Sheet(character.contributions);
        double const applied = 100.0 * (1.0 - DCTest::FactorThroughCore(Auras(gear, passives)));
        SetContribution(character,
                        {Source::Temporary, Stat::ResourceCostReduction, GEAR_AURA, applied, Bucket::Derived});
        contributions = character.contributions;
        return {applied, Sheet(contributions)};
    }

    // What a cast is charged, through the core, with those same auras on.
    double Charged(std::vector<Contribution> const& contributions, std::vector<double> const& passives)
    {
        CharacterStats character;
        character.contributions = contributions;
        RemoveContribution(character, Source::Temporary, Stat::ResourceCostReduction, GEAR_AURA);
        double const gear = Sheet(character.contributions);
        return DC::Combat::CostMath::Fury(
            DCTest::CostThroughCore(DC::Combat::CostMath::Rage(CAST_FURY), Auras(gear, passives)));
    }
    // One pass of the cooldown half of Passives::RefreshModifiers: the same
    // six steps on the other modifier, measured on a record's RecoveryTime.
    std::pair<double, double> RefreshCooldown(std::vector<Contribution>& contributions, std::int32_t base)
    {
        CharacterStats character;
        character.contributions = contributions;
        RemoveContribution(character, Source::Temporary, Stat::CooldownReduction, COOLDOWN_AURA);
        double const gear = Calculate(Character(), character.contributions)[Stat::CooldownReduction];
        double const applied = 100.0 * (1.0 - double(DCTest::CooldownThroughCore(base, 0, gear)) / base);
        SetContribution(character,
                        {Source::Temporary, Stat::CooldownReduction, COOLDOWN_AURA, applied, Bucket::Derived});
        contributions = character.contributions;
        return {applied, Calculate(Character(), contributions)[Stat::CooldownReduction]};
    }
} // namespace

namespace
{
    // The two hands' speeds as the production Calculate builds them, from one
    // weapon's own attack-speed affix on each hand and the shared IAS.
    std::pair<double, double> Hands(double mainBase, double mainLocal,
                                    double offBase, double offLocal, double ias)
    {
        CharacterStats character;
        SetContribution(character, {Source::Items, Stat::WeaponAPS, 1, mainBase});
        SetContribution(character, {Source::Items, Stat::AttackSpeed, 1, mainLocal, Bucket::WeaponLocal});
        if (offBase > 0)
        {
            SetContribution(character, {Source::Items, Stat::OffhandWeaponAPS, 2, offBase});
            SetContribution(character, {Source::Items, Stat::OffhandWeaponIAS, 2, offLocal,
                                        Bucket::WeaponLocal});
        }
        if (ias != 0)
            SetContribution(character, {Source::Items, Stat::AttackSpeed, 3, ias});
        StatSheet sheet = Calculate(Character(), character.contributions);
        return {sheet.attacksPerSecond, sheet.offhandAttacksPerSecond};
    }
}

int main(int argc, char** argv)
{
    if (argc != 2)
    {
        std::fprintf(stderr, "usage: display_harness <cases.tsv>\n");
        return 2;
    }
    std::ifstream stream(argv[1]);
    std::string line;
    while (std::getline(stream, line))
    {
        if (line.empty())
            continue;
        std::istringstream cells(line);
        std::string kind;
        double gear = 0;
        cells >> kind >> gear;

        if (kind == "display")
        {
            std::vector<double> passives;
            for (double percent = 0; cells >> percent;)
                passives.push_back(percent);
            std::vector<Contribution> contributions{{Source::Items, Stat::ResourceCostReduction, ITEM_AFFIX, gear}};
            auto first = Refresh(contributions, passives);
            auto again = Refresh(contributions, passives);
            std::printf("%.6f\t%.6f\t%.6f\n", first.first, first.second, again.second);
        }
        else if (kind == "equip")
        {
            double ring = 0;
            cells >> ring;
            std::vector<double> passives;
            for (double percent = 0; cells >> percent;)
                passives.push_back(percent);

            std::vector<Contribution> contributions{{Source::Items, Stat::ResourceCostReduction, ITEM_AFFIX, gear}};
            double const shownBefore = Refresh(contributions, passives).second;
            double const paidBefore = Charged(contributions, passives);

            // the ring goes on: DC::Items::Apply adds its contribution and the
            // one refresh runs, which is what rebuilds the aura
            CharacterStats character;
            character.contributions = contributions;
            SetContribution(character, {Source::Items, Stat::ResourceCostReduction, RING_AFFIX, ring});
            contributions = character.contributions;
            double const shownAfter = Refresh(contributions, passives).second;
            double const paidAfter = Charged(contributions, passives);

            std::printf("%.6f\t%.6f\t%.6f\t%.6f\n", shownBefore, paidBefore, shownAfter, paidAfter);
        }
        else if (kind == "cooldown")
        {
            std::int32_t base = 0;
            cells >> base;
            std::vector<Contribution> contributions{
                {Source::Items, Stat::CooldownReduction, ITEM_AFFIX, gear}};
            auto first = RefreshCooldown(contributions, base);
            auto again = RefreshCooldown(contributions, base);
            std::printf("%.6f\t%.6f\t%.6f\n", first.first, first.second, again.second);
        }
        else if (kind == "hands")
        {
            double mainLocal = 0, offBase = 0, offLocal = 0, ias = 0;
            cells >> mainLocal >> offBase >> offLocal >> ias;
            auto speeds = Hands(gear, mainLocal, offBase, offLocal, ias);
            std::printf("%.9f\t%.9f\n", speeds.first, speeds.second);
        }
        else
        {
            std::fprintf(stderr, "unknown case: %s\n", kind.c_str());
            return 2;
        }
    }
    return 0;
}
