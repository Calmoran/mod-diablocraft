// diablocraft-wizard-resource: the class-keyed sheet and the channel arithmetic,
// compiled from the module's own dc_common.cpp and dc_cost_math.h.
// scripts/tests/classes/test_wizard_resource.py builds and runs this; it prints one
// "name value" line per measurement and the script holds them to the sheets.
#include "../../src/common/dc_common.h"
#include "../../src/common/dc_numeric_data.h"
#include "../../src/combat/dc_cost_math.h"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

// The Barbarian's numeric rules, as dc_numeric_rule holds them - the fallback
// a base with no class rules of its own reads.
namespace DC::NumericData
{
    double Rule(char const* name)
    {
        static std::map<std::string, double> const rules{
            {"crit_chance_pct", 5},          {"crit_damage_pct", 50},
            {"attack_speed_cap", 5},         {"movement_cap_pct", 25},
            {"magic_find_cap_pct", 300},     {"gold_find_cap_pct", 300},
            {"xp_penalty_level", 70},        {"xp_divisor", 10},
            {"all_res_per_int", 0.1},        {"class_dr_pct", 30},
            {"armor_level_coefficient", 50}, {"resistance_level_coefficient", 5}};
        return rules.at(name);
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
        return {75, 100, 1};
    }
} // namespace DC::NumericData

using namespace DC;

static std::vector<BaseStats> ReadBases(char const* path)
{
    std::ifstream input(path);
    std::string line;
    std::getline(input, line);
    std::vector<BaseStats> out;
    while (std::getline(input, line))
    {
        std::istringstream row(line);
        std::vector<double> cells;
        std::string cell;
        for (int i = 0; i < 10 && std::getline(row, cell, ','); ++i)
            cells.push_back(std::stod(cell));
        BaseStats base;
        base.level = unsigned(cells[0]);
        base.strength = cells[1];
        base.dexterity = cells[2];
        base.intelligence = cells[3];
        base.vitality = cells[4];
        base.baseLife = cells[5];
        base.lifePerVitality = cells[6];
        base.baseArmor = cells[8];
        base.maxFury = cells[9];
        out.push_back(base);
    }
    return out;
}

int main(int argc, char** argv)
{
    if (argc != 3)
        return 2;
    // 1. The Barbarian through the class-keyed inputs is the Barbarian through
    // the fallback, byte for byte, at every level.
    unsigned same = 0, levels = 0;
    for (BaseStats base : ReadBases(argv[1]))
    {
        std::string const fallback = Serialize(Calculate(base, {}));
        base.classDRPct = 30;
        base.allResPerInt = 0.1;
        base.mainStat = Stat::Strength;
        same += Serialize(Calculate(base, {})) == fallback;
        ++levels;
    }
    std::printf("barbarian_levels %u\nbarbarian_identical %u\n", levels, same);

    // 2. The Wizard at 70 with its own rules and 1000 flat Thorns.
    auto wizards = ReadBases(argv[2]);
    BaseStats wizard = wizards.back();
    wizard.classDRPct = 0;
    wizard.allResPerInt = 0.1;
    wizard.mainStat = Stat::Intelligence;
    StatSheet const w = Calculate(wizard, {{Source::Items, Stat::Thorns, 7, 1000, Bucket::Flat, Element::Physical}});
    std::printf("wizard_levels %zu\nwizard_level %u\nwizard_max_life %.9f\nwizard_armor %.9f\n", wizards.size(),
                w.level, w.maxLife, w[Stat::Armor]);
    std::printf("wizard_int %.9f\nwizard_all_res %.9f\nwizard_class_dr %.9f\nwizard_resource_max %.9f\n",
                w[Stat::Intelligence], w[Stat::AllResistance], w.classDR, w[Stat::MaxFury]);
    std::printf("wizard_thorns %.9f\nwizard_taken_physical %.9f\nwizard_expected_taken %.9f\n", w[Stat::Thorns],
                w.damageTaken[0], (1 - w.armorDR) * (1 - w.resistanceDR[0]));

    // 3. The channel arithmetic, exactly as dc_combat.cpp calls it.
    using namespace Combat::CostMath;
    std::printf("rof_interval_1 %.9f\nrof_interval_1_5 %.9f\n", ScheduleSeconds(30, 1.0, 60),
                ScheduleSeconds(30, 1.5, 60));
    std::printf("rof_tick_cost %.9f\nrof_tick_cost_rcr %.9f\n", ChannelTickCost(16, 1.0, 30, 60),
                ChannelTickCost(16, 0.7, 30, 60));
    std::printf("dis_tick_cost %.9f\n", ChannelTickCost(18, 1.0, 20, 60));
    for (double t : {0.0, 0.99, 1.0, 1.99, 2.0, 7.5})
        std::printf("rof_ramp_%g %.9f\n", t, ChannelRamp(430, 405, 1240, t));
    std::printf("rof_share_1 %.9f\nrof_share_1_5 %.9f\n", ChannelTickShare(430, 30, 60, 1.0, false),
                ChannelTickShare(430, 30, 60, 1.5, false));
    std::printf("at_share_1_5 %.9f\n", ChannelTickShare(400, 20, 60, 1.5, true));
    // A 16-point channel at 30% RCR owes 5.6 a tick: 5, 6, 5, 6, 6, 28 in all
    double owed = 0, pool = 100;
    std::string taken;
    for (int i = 0; i < 5; ++i)
    {
        auto debit = PayWhole(pool, ChannelTickCost(16, 0.7, 30, 60) + owed);
        pool -= debit.whole;
        owed = debit.owed;
        taken += std::to_string(debit.whole);
    }
    std::printf("debits %s\npool_after %.9f\n", taken.c_str(), pool);
    std::printf("short_pool_paid %d\nexact_pool_paid %d\n", int(PayWhole(7.9, 8).paid), int(PayWhole(8, 8).paid));
    return 0;
}
