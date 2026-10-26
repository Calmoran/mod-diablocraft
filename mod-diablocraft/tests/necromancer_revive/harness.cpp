// The real dc_necromancer_revive_math.h and the shared dc_corpses_math.h. The rune names and numbers come from argv
// (read from the sheets and tunables by test_necromancer_revive.py); the corpse cap and lifetime, blank until the designer
// answers, are set here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_revive_math.h"
#include "combat/dc_corpses_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::CorpseRevive;
using DC::Combat::Corpses::Pile;
using DC::Combat::Corpses::Spot;

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
    // argv: the corpses a cast revives, the reach, Personal Army's reduction for each minion, Oblation's cost for each
    // corpse, then the five runes A to E
    if (argc < 10)
        return 2;
    double const targetCount = std::atof(argv[1]), reach = std::atof(argv[2]), reduction = std::atof(argv[3]),
                 cost = std::atof(argv[4]);
    std::string const purgatory = argv[5], oblation = argv[6], army = argv[7], reckless = argv[8], horrific = argv[9];

    expect(RuneOf(purgatory) == Rune::Purgatory && RuneOf(oblation) == Rune::Oblation &&
               RuneOf(army) == Rune::PersonalArmy && RuneOf(reckless) == Rune::Recklessness &&
               RuneOf(horrific) == Rune::HorrificReturn,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {purgatory, oblation, army, reckless, horrific})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Revive") == Rune::None, "the base skill and a stranger are no rune");

    // Personal Army: a share off for each minion standing, never below nothing.
    expect(near(TakenFactor(reduction, 0), 1.0), "no minion, no reduction");
    expect(near(TakenFactor(reduction, 4), 1.0 - reduction * 4 / 100), "four minions, four reductions",
           TakenFactor(reduction, 4), 1.0 - reduction * 4 / 100);
    expect(near(TakenFactor(reduction, 10), 1.0 - reduction * 10 / 100), "ten minions, ten reductions");
    expect(near(TakenFactor(60, 5), 0.0), "never below nothing");
    expect(near(TakenFactor(0, 5), 1.0) && near(TakenFactor(-3, 5), 1.0), "no reduction stated, none given");

    // How many corpses a cast revives.
    expect(Revived(25, targetCount) == std::size_t(targetCount), "never more than the cast may",
           double(Revived(25, targetCount)), targetCount);
    expect(Revived(3, targetCount) == 3, "fewer lie than the most: all of them", double(Revived(3, targetCount)), 3);
    expect(Revived(0, targetCount) == 0 && Revived(5, 0) == 0 && Revived(5, -1) == 0,
           "none lying or none allowed, none");
    expect(CanRevive(1) && !CanRevive(0), "a cast needs a corpse in reach");

    // Oblation: the cost for each corpse revived.
    expect(near(LifeCostPct(cost, 4), cost * 4), "four corpses, four costs", LifeCostPct(cost, 4), cost * 4);
    expect(near(LifeCostPct(cost, 0), 0) && near(LifeCostPct(0, 4), 0) && near(LifeCostPct(-1, 4), 0),
           "no corpse or no cost, none");

    // Which runes raise the damage.
    expect(RaisesDamage(Rune::Oblation) && RaisesDamage(Rune::Recklessness),
           "Oblation and Recklessness raise the damage");
    expect(!RaisesDamage(Rune::None) && !RaisesDamage(Rune::Purgatory) && !RaisesDamage(Rune::PersonalArmy) &&
               !RaisesDamage(Rune::HorrificReturn),
           "the others do not");

    // The shared pile with the cap and lifetime set here: the corpses within the reach of the point, nearest first, up
    // to the most.
    Pile pile;
    std::uint64_t const lifetime = 60000;
    for (int i = 0; i < 14; ++i)
        pile.Leave(Spot{float(i), 0, 0, 100u + unsigned(i)}, 1000 + i, 30, lifetime);
    pile.Leave(Spot{float(reach) + 3, 0, 0, 999}, 1100, 30, lifetime);
    std::size_t const lying = pile.Count(0, 0, float(reach), 2000, lifetime);
    expect(lying == 14, "fourteen corpses within the reach", double(lying), 14);
    auto const taken = pile.Take(0, 0, float(reach), Revived(lying, targetCount), 2000, lifetime);
    expect(taken.size() == std::size_t(targetCount), "a cast takes the most", double(taken.size()), targetCount);
    expect(taken.size() >= 2 && taken[0].entry == 100 && taken[1].entry == 101,
           "the creature of each corpse comes with it, nearest first");
    expect(pile.Size() == 5, "the rest stay", double(pile.Size()), 5);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
