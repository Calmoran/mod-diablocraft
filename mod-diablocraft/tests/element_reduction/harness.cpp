// diablocraft-508ry: Stat::ElementReduction through the module's real src/common/dc_common.cpp (Calculate,
// Validate, the sheet save). scripts/tests/combat/test_element_reduction.py builds and runs it; any failed check exits 1.
#include "common/dc_common.h"
#include "common/dc_numeric_data.h"

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
    unsigned MaximumLevel() { return 70; }
    double BaseFury(unsigned) { return 100; }
    BlockTuning Block() { return {75, 100, 1}; }
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
    bool Near(double a, double b) { return std::fabs(a - b) < 1e-9; }
    unsigned const Cold = Index(Element::Cold), Fire = Index(Element::Fire);
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
    // Some armor and resistance, so the reduction multiplies a real factor rather than 1.
    std::vector<Contribution> gear{{Source::Items, Stat::Armor, 1, 2000},
                                   {Source::Items, Stat::AllResistance, 2, 300}};
    StatSheet const bare = Calculate(base, gear);

    // Ice Climbers' line: 10% from Cold, and nothing from any other element.
    auto worn = gear;
    worn.push_back({Source::Items, Stat::ElementReduction, 3, 10, Bucket::Flat, Element::Cold});
    StatSheet const one = Calculate(base, worn);
    Check(Near(one.damageTaken[Cold], bare.damageTaken[Cold] * 0.9), "Cold taken is 90% of the bare sheet's");
    Check(Near(one.elementReduction[Cold], 10), "the sheet shows 10% Cold reduction");
    for (unsigned e = 0; e < ElementCount; ++e)
        if (e != Cold)
        {
            Check(Near(one.damageTaken[e], bare.damageTaken[e]), "another element's taken factor moved");
            Check(one.elementReduction[e] == 0, "another element shows a reduction");
        }
    Check(one[Stat::ElementReduction] == 0, "the per-element stat leaked into the flat values");

    // A second source multiplies like every other reduction: 1 - 0.9 x 0.8 = 28%, not 30%.
    worn.push_back({Source::Gems, Stat::ElementReduction, 4, 20, Bucket::Flat, Element::Cold});
    worn.push_back({Source::Items, Stat::ElementReduction, 5, 50, Bucket::Flat, Element::Fire});
    StatSheet const two = Calculate(base, worn);
    Check(Near(two.elementReduction[Cold], 28), "two Cold sources multiply to 28%");
    Check(Near(two.damageTaken[Cold], bare.damageTaken[Cold] * 0.72), "Cold taken is 72% of the bare sheet's");
    Check(Near(two.damageTaken[Fire], bare.damageTaken[Fire] * 0.5), "the table holds every element: Fire 50%");

    // Validate: a reduction is 0..100 and takes an element.
    bool threw = false;
    try { Validate({Source::Items, Stat::ElementReduction, 6, 101, Bucket::Flat, Element::Cold}); }
    catch (std::invalid_argument const&) { threw = true; }
    Check(threw, "a 101% reduction is refused");
    threw = false;
    try { Validate({Source::Items, Stat::SpecificReduction, 7, 10, Bucket::Flat, Element::Cold}); }
    catch (std::invalid_argument const&) { threw = true; }
    Check(threw, "an element on a stat that has none is still refused");

    // The save: the current record round-trips, and a version-6 record (no stat slot, no array) still loads.
    std::string const saved = Serialize(two);
    StatSheet const back = DeserializeSheet(saved);
    Check(Serialize(back) == saved && Near(back.elementReduction[Cold], 28), "the reduction survives a save");
    std::istringstream in(saved);
    std::vector<std::string> tokens;
    for (std::string token; in >> token;)
        tokens.push_back(token);
    unsigned const header = 10; // version + the nine scalars versions 6 and 7 write
    Check(tokens.size() == header + StatCount + 5 * ElementCount, "the record holds the reduction array");
    if (tokens.size() == header + StatCount + 5 * ElementCount)
    {
        tokens[0] = "6";
        tokens.resize(tokens.size() - ElementCount);
        tokens.erase(tokens.begin() + header + Index(Stat::ElementReduction), tokens.begin() + header + StatCount);
        std::ostringstream old;
        for (auto const& token : tokens)
            old << token << ' ';
        try
        {
            StatSheet const upgraded = DeserializeSheet(old.str());
            Check(upgraded.elementReduction[Cold] == 0 && Near(upgraded.damageTaken[Cold], two.damageTaken[Cold]),
                  "a version-6 record loads with no reduction and its own taken factor");
        }
        catch (std::exception const&)
        {
            Check(false, "a version-6 record no longer loads");
        }
    }
    if (failures)
        return 1;
    std::printf("PASS\n");
    return 0;
}
