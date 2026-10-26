// The real dc_level_heal.h over the real dc_healing_table.h. Every case comes from argv (the sheets' numbers and the heal the power
// file's own coefficient gives at each level, worked out by test_level_heals.py): triples of the sheet's heal, a level and the heal
// expected there. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/dc_level_heal.h"
#include "combat/dc_healing_table.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Classes;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what, double a = 0, double b = 0)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s (%g vs %g)\n", what, a, b);
        ++failures;
    }
}

int main(int argc, char** argv)
{
    if (argc < 5 || (argc - 1) % 3)
        return 2;
    double const top = DC::Combat::Healing::At(70);
    expect(TopLevelHealing() == top, "the top level is the table's last row", TopLevelHealing(), top);
    for (int i = 1; i + 2 < argc; i += 3)
    {
        double const sheet = std::atof(argv[i]), expected = std::atof(argv[i + 2]);
        unsigned const level = unsigned(std::atoi(argv[i + 1]));
        double const got = HealAtLevel(sheet, level);
        // The sheet's number is the coefficient times the top row, rounded to a whole number: at the top level it is the sheet's
        // number itself, and below it the heal is within a whole point of the file's.
        expect(level == 70 ? got == sheet : true, "the top level gives the sheet's number", got, sheet);
        expect(std::fabs(got - expected) <= 1.0, "a level gives the file's heal", got, expected);
    }
    // A heal grows with the level, reads the last row past it and is nothing for nothing.
    double previous = 0;
    for (unsigned level = 1; level <= 70; ++level)
    {
        double const heal = HealAtLevel(1000.0, level);
        expect(heal > previous, "the heal grows with every level", heal, previous);
        previous = heal;
    }
    expect(HealAtLevel(1000.0, 71) == HealAtLevel(1000.0, 70) && HealAtLevel(1000.0, 1000) == 1000.0, "past the table reads the last row",
           HealAtLevel(1000.0, 71), 1000.0);
    expect(HealAtLevel(0, 40) == 0 && HealAtLevel(-5, 40) == 0, "no heal, no scaling");

    // A standing contribution (Vigilant's and Enduring Ally's regeneration) is rebuilt when the level it was built at is not the caster's: a
    // character that levels up reads the new level's value at its next look, and a look at the same level rebuilds nothing.
    struct Standing
    {
        unsigned builtAt = 0;
        double value = 0;
        unsigned builds = 0;
        void Look(double sheet, unsigned level)
        {
            if (!BuiltAtOtherLevel(builtAt, level))
                return;
            builtAt = level;
            value = HealAtLevel(sheet, level);
            ++builds;
        }
    } standing;
    standing.Look(1000.0, 60);
    expect(standing.value == HealAtLevel(1000.0, 60) && standing.builds == 1, "the first look builds it", standing.value, HealAtLevel(1000.0, 60));
    standing.Look(1000.0, 60);
    expect(standing.builds == 1, "a look at the same level rebuilds nothing", standing.builds, 1);
    standing.Look(1000.0, 61);
    expect(standing.value == HealAtLevel(1000.0, 61) && standing.value > HealAtLevel(1000.0, 60) && standing.builds == 2,
           "a level-up reads the new level's value", standing.value, HealAtLevel(1000.0, 61));
    standing.Look(1000.0, 70);
    expect(standing.value == 1000.0 && standing.builds == 3, "and the top level reads the sheet's number", standing.value, 1000.0);
    expect(!BuiltAtOtherLevel(70, 70) && BuiltAtOtherLevel(0, 1) && BuiltAtOtherLevel(70, 69), "the level it was built at against the level now");
    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
