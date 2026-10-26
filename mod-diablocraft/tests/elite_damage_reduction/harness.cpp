// diablocraft-5ozrm: Stat::EliteReduction through the module's real src/common/dc_common.cpp (Calculate,
// Validate, the sheet save). scripts/tests/monsters/test_elite_damage_reduction.py builds and runs it; any failed check exits 1.
#include "../../src/common/dc_common.h"
#include "../../src/common/dc_numeric_data.h"

#include <cmath>
#include <cstdio>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

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

namespace
{
    int failures = 0;
    void Check(bool ok, char const* what)
    {
        if (!ok)
        {
            std::printf("FAIL: %s\n", what);
            ++failures;
        }
    }
    bool Near(double a, double b)
    {
        return std::fabs(a - b) < 1e-9;
    }
} // namespace

int main()
{
    BaseStats base;
    base.level = 60;
    base.strength = 100;
    base.vitality = 100;
    base.baseArmor = base.strength;
    base.baseLife = 1000;
    base.lifePerVitality = 10;
    base.maxFury = 100;
    std::vector<Contribution> gear{{Source::Items, Stat::Armor, 1, 2000}, {Source::Items, Stat::AllResistance, 2, 300}};
    StatSheet const bare = Calculate(base, gear);
    Check(bare[Stat::EliteReduction] == 0, "a bare sheet has no elite reduction");

    // Aughild's 3-piece: 30%. It is read on an elite's hit only, so no damage-taken factor moves.
    auto worn = gear;
    worn.push_back({Source::Items, Stat::EliteReduction, 3, 30});
    StatSheet const one = Calculate(base, worn);
    Check(Near(one[Stat::EliteReduction], 30), "the sheet shows 30% elite reduction");
    for (unsigned e = 0; e < ElementCount; ++e)
        Check(Near(one.damageTaken[e], bare.damageTaken[e]), "an element's taken factor moved");
    Check(Near(one[Stat::SpecificReduction], bare[Stat::SpecificReduction]), "the specific reduction moved");

    // Blackthorne's 3-piece beside it: a `dr` stat, so 1 - 0.7 x 0.9 = 37%, not 40% (stats_full.js:70).
    worn.push_back({Source::Items, Stat::EliteReduction, 4, 10});
    StatSheet const two = Calculate(base, worn);
    Check(Near(two[Stat::EliteReduction], 37), "two sources multiply to 37%");

    // Validate: a reduction is 0..100, with no element.
    bool threw = false;
    try
    {
        Validate({Source::Items, Stat::EliteReduction, 5, 101});
    }
    catch (std::invalid_argument const&)
    {
        threw = true;
    }
    Check(threw, "a 101% elite reduction is refused");
    threw = false;
    try
    {
        Validate({Source::Items, Stat::EliteReduction, 6, 10, Bucket::Flat, Element::Cold});
    }
    catch (std::invalid_argument const&)
    {
        threw = true;
    }
    Check(threw, "an element on the elite reduction is refused");

    // The save: version 12 round-trips, and a version-7 record (no elite slot, no flat-damage delta) still loads with none.
    std::string const saved = Serialize(two);
    Check(saved.rfind("12 ", 0) == 0, "the record is version 12");
    StatSheet const back = DeserializeSheet(saved);
    Check(Serialize(back) == saved && Near(back[Stat::EliteReduction], 37), "the reduction survives a save");
    std::istringstream in(saved);
    std::vector<std::string> tokens;
    for (std::string token; in >> token;)
        tokens.push_back(token);
    unsigned const header = 10; // version + the nine scalars versions 6 to 10 write
    Check(tokens.size() == header + StatCount + 5 * ElementCount, "the record holds every stat");
    if (tokens.size() == header + StatCount + 5 * ElementCount)
    {
        // A version-11 record ends its stat array before the second resource's gear maximum version 12 appended.
        auto v11 = tokens;
        v11[0] = "11";
        v11.erase(v11.begin() + header + Index(Stat::MaxSecond), v11.begin() + header + StatCount);
        std::ostringstream eleven;
        for (auto const& token : v11)
            eleven << token << ' ';
        try
        {
            StatSheet const upgraded = DeserializeSheet(eleven.str());
            Check(upgraded[Stat::MaxSecond] == 0 && Near(upgraded[Stat::EliteReduction], 37),
                  "a version-11 record loads with no second maximum");
        }
        catch (std::exception const&)
        {
            Check(false, "a version-11 record no longer loads");
        }
        // A version-10 record ends its stat array before the two Maelstrom lines version 11 appended.
        auto v10 = tokens;
        v10[0] = "10";
        v10.erase(v10.begin() + header + Index(Stat::MaelstromGeneration), v10.begin() + header + StatCount);
        std::ostringstream ten;
        for (auto const& token : v10)
            ten << token << ' ';
        try
        {
            StatSheet const upgraded = DeserializeSheet(ten.str());
            Check(upgraded[Stat::MaelstromGeneration] == 0 && upgraded[Stat::PrimaryMaelstrom] == 0 &&
                      Near(upgraded[Stat::EliteReduction], 37),
                  "a version-10 record loads with none of the Maelstrom lines");
        }
        catch (std::exception const&)
        {
            Check(false, "a version-10 record no longer loads");
        }
        // An older record has none of the eleven stats versions 10 to 12 appended (ResourceOnCrit .. MaxSecond).
        tokens.erase(tokens.begin() + header + Index(Stat::ResourceOnCrit), tokens.begin() + header + StatCount);
        // A version-9 record loads with all eleven at zero.
        auto v9 = tokens;
        v9[0] = "9";
        std::ostringstream nine;
        for (auto const& token : v9)
            nine << token << ' ';
        try
        {
            StatSheet const upgraded = DeserializeSheet(nine.str());
            Check(upgraded[Stat::ResourceOnCrit] == 0 && upgraded[Stat::DamageVsHuman] == 0 && Near(upgraded[Stat::EliteReduction], 37),
                  "a version-9 record loads with none of the stats versions 10 to 12 added");
        }
        catch (std::exception const&)
        {
            Check(false, "a version-9 record no longer loads");
        }
        // A version-8 record has the elite slot and not the flat-damage delta.
        auto v8 = tokens;
        v8[0] = "8";
        v8.erase(v8.begin() + header + Index(Stat::WeaponFlatDamageDelta));
        std::ostringstream eight;
        for (auto const& token : v8)
            eight << token << ' ';
        try
        {
            StatSheet const upgraded = DeserializeSheet(eight.str());
            Check(upgraded[Stat::WeaponFlatDamageDelta] == 0 && Near(upgraded[Stat::EliteReduction], 37),
                  "a version-8 record loads with no flat-damage delta");
        }
        catch (std::exception const&)
        {
            Check(false, "a version-8 record no longer loads");
        }
        tokens[0] = "7";
        tokens.erase(tokens.begin() + header + Index(Stat::WeaponFlatDamageDelta));
        tokens.erase(tokens.begin() + header + Index(Stat::EliteReduction));
        std::ostringstream old;
        for (auto const& token : tokens)
            old << token << ' ';
        try
        {
            StatSheet const upgraded = DeserializeSheet(old.str());
            Check(upgraded[Stat::EliteReduction] == 0 && Near(upgraded.elementReduction[0], two.elementReduction[0]),
                  "a version-7 record loads with no elite reduction");
        }
        catch (std::exception const&)
        {
            Check(false, "a version-7 record no longer loads");
        }
    }
    if (failures)
        return 1;
    std::printf("PASS\n");
    return 0;
}
