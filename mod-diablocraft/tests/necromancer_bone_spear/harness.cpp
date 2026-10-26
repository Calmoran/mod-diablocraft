// The real dc_necromancer_bone_spear_math.h and dc_necromancer_life_math.h. The rune names and numbers come from argv
// (read from the sheets and tunables by test_necromancer_bone_spear.py); nothing is typed in here. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_bone_spear_math.h"
#include "classes/necromancer/dc_necromancer_life_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer;
using namespace DC::Combat::Necromancer::BoneSpear;

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

static bool near(double a, double b)
{
    return std::fabs(a - b) < 1e-9;
}

int main(int argc, char** argv)
{
    // argv: Blighted Marrow's bonus, Teeth's reach, Blood Spear's Life cost, then the five runes A to E
    if (argc < 9)
        return 2;
    double const bonus = std::atof(argv[1]), reach = std::atof(argv[2]), lifePct = std::atof(argv[3]);
    std::string const crystal = argv[4], shatter = argv[5], marrow = argv[6], blood = argv[7], teeth = argv[8];

    expect(RuneOf(crystal) == Rune::Crystallization && RuneOf(shatter) == Rune::Shatter &&
               RuneOf(marrow) == Rune::BlightedMarrow && RuneOf(blood) == Rune::BloodSpear &&
               RuneOf(teeth) == Rune::Teeth,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {crystal, shatter, marrow, blood, teeth})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Bone Spear") == Rune::None, "the base skill and a stranger are no rune");

    // Blighted Marrow: the bonus for each enemy passed, none for the first.
    expect(near(PierceBonusPct(bonus, 0), 0), "the first enemy has no bonus");
    expect(near(PierceBonusPct(bonus, 1), bonus), "one enemy passed, one bonus", PierceBonusPct(bonus, 1), bonus);
    expect(near(PierceBonusPct(bonus, 4), bonus * 4), "four passed, four bonuses", PierceBonusPct(bonus, 4), bonus * 4);
    expect(near(PierceBonusPct(-5, 3), 0) && near(PierceBonusPct(0, 3), 0), "no bonus stated, none given");

    // Teeth: inside the reach only, the reach itself included.
    expect(WithinReach(reach - 1, reach), "an enemy inside the reach is struck");
    expect(WithinReach(reach, reach), "an enemy at the reach is struck");
    expect(!WithinReach(reach + 0.5, reach), "an enemy past the reach is not");
    expect(WithinReach(500, 0) && WithinReach(500, -1), "no reach stated, no limit");

    // Shatter: the first impact detonates, no other.
    expect(Detonates(0), "the first impact detonates");
    expect(!Detonates(1) && !Detonates(7), "no later impact does");

    // Blood Spear: a share of maximum Life, never to less than 1, never negative.
    expect(near(LifeCost(10000, 10000, lifePct), 10000 * lifePct / 100), "the share of maximum Life",
           LifeCost(10000, 10000, lifePct), 10000 * lifePct / 100);
    expect(near(LifeCost(3000, 10000, lifePct), std::min(10000 * lifePct / 100, 2999.0)),
           "a hurt Necromancer pays the same share");
    expect(near(LifeCost(500, 10000, lifePct), 499), "never to less than 1 Life", LifeCost(500, 10000, lifePct), 499);
    expect(near(LifeCost(1, 10000, lifePct), 0) && near(LifeCost(0, 10000, lifePct), 0), "at 1 Life nothing is taken");
    expect(near(LifeCost(10000, 0, lifePct), 0) && near(LifeCost(10000, 10000, 0), 0) &&
               near(LifeCost(10000, 10000, -5), 0),
           "no maximum or no percent, no cost");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
