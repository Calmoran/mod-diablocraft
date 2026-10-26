// The real dc_necromancer_land_of_the_dead_math.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_necromancer_land_of_the_dead.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first
// failing case and exits 1.
#include "classes/necromancer/dc_necromancer_land_of_the_dead_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::LandOfTheDead;

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
    // argv: the five runes A to E; Shallow Graves' trigger count, extension and most (seconds); Plaguelands' damage a second and
    // its maximum; Land of Plenty's heal
    if (argc < 12)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    unsigned const trigger = unsigned(std::atoi(argv[6]));
    double const step = std::atof(argv[7]), most = std::atof(argv[8]), tick = std::atof(argv[9]), maxPct = std::atof(argv[10]),
                 heal = std::atof(argv[11]);

    expect(RuneOf(names[0]) == Rune::Invigoration && RuneOf(names[1]) == Rune::FrozenLands && RuneOf(names[2]) == Rune::Plaguelands &&
               RuneOf(names[3]) == Rune::LandOfPlenty && RuneOf(names[4]) == Rune::ShallowGraves,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Land of the Dead") == Rune::None && RuneOf("plaguelands") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // Shallow Graves: every trigger-count-th kill extends, and not the ones between.
    expect(ExtendsOn(trigger, trigger) && ExtendsOn(trigger * 2, trigger) && ExtendsOn(trigger * 7, trigger), "every nth kill extends");
    expect(!ExtendsOn(trigger - 1, trigger) && !ExtendsOn(trigger + 1, trigger) && !ExtendsOn(0, trigger), "the kills between do not");
    expect(!ExtendsOn(5, 0), "no trigger count, no extension");
    expect(near(ExtensionFor(0, step, most), step), "the first extension is a step");
    expect(near(ExtensionFor(most - step / 2, step, most), step / 2), "the last is what is left of the most",
           ExtensionFor(most - step / 2, step, most), step / 2);
    expect(ExtensionFor(most, step, most) == 0.0 && ExtensionFor(most + 3, step, most) == 0.0, "none past the most");
    double total = 0;
    for (unsigned i = 0; i < 100; ++i)
        total += ExtensionFor(total, step, most);
    expect(near(total, most), "the extensions never add past the most", total, most);

    // Plaguelands: a tick under the maximum, held to what is left of it.
    expect(near(PlagueTick(0, tick, maxPct), tick), "a fresh enemy takes the whole tick");
    expect(near(PlagueTick(maxPct - tick / 4, tick, maxPct), tick / 4), "the last tick is what is left under the maximum");
    expect(PlagueTick(maxPct, tick, maxPct) == 0.0 && PlagueTick(maxPct + 5, tick, maxPct) == 0.0, "an enemy at its maximum takes none");
    double dealt = 0;
    for (unsigned i = 0; i < 100000; ++i)
        dealt += PlagueTick(dealt, tick, maxPct);
    expect(near(dealt, maxPct), "an enemy never takes more than the maximum", dealt, maxPct);

    // Land of Plenty.
    expect(near(KillHeal(100000, heal), 100000 * heal / 100.0), "a kill heals its share of the Life", KillHeal(100000, heal),
           100000 * heal / 100.0);
    expect(KillHeal(0, heal) == 0.0 && KillHeal(-5, heal) == 0.0 && KillHeal(100000, 0) == 0.0 && KillHeal(100000, -2) == 0.0,
           "no Life or no percent: no heal");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
