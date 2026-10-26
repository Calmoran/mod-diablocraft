// The real dc_necromancer_corpse_lance_math.h, dc_necromancer_buffs.h and the shared dc_corpses_math.h. The rune names
// and numbers come from argv (read from the sheets and tunables by test_necromancer_corpse_lance.py); the corpse cap
// and lifetime, blank until the designer answers, are set here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/necromancer/dc_necromancer_buffs.h"
#include "classes/necromancer/dc_necromancer_corpse_lance_math.h"
#include "combat/dc_corpses_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::CorpseLance;
namespace Buffs = DC::Combat::Necromancer::Buffs;
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
    // argv: the reach near the Necromancer and near the target, Ricochet's chance, Shredding Splinters' slow, seconds
    // and stacks, then the five runes A to E
    if (argc < 12)
        return 2;
    double const nearCaster = std::atof(argv[1]), nearTarget = std::atof(argv[2]), chance = std::atof(argv[3]),
                 slow = std::atof(argv[4]), seconds = std::atof(argv[5]);
    unsigned const most = unsigned(std::atoi(argv[6]));
    std::string const ricochet = argv[7], brittle = argv[8], blood = argv[9], visceral = argv[10], splinters = argv[11];

    expect(RuneOf(ricochet) == Rune::Ricochet && RuneOf(brittle) == Rune::BrittleTouch &&
               RuneOf(blood) == Rune::BloodLance && RuneOf(visceral) == Rune::VisceralImpact &&
               RuneOf(splinters) == Rune::ShreddingSplinters,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {ricochet, brittle, blood, visceral, splinters})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Corpse Lance") == Rune::None,
           "the base skill and a stranger are no rune");

    expect(KeepsTheSkillsHit(Rune::BloodLance), "Blood Lance keeps the skill's number for the main lance");
    expect(!KeepsTheSkillsHit(Rune::None) && !KeepsTheSkillsHit(Rune::Ricochet) &&
               !KeepsTheSkillsHit(Rune::ShreddingSplinters),
           "the others take their own");

    // A corpse in reach: near either one.
    expect(CorpseInReach(1, 0) && CorpseInReach(0, 1) && CorpseInReach(3, 3),
           "a corpse near either is a corpse in reach");
    expect(!CorpseInReach(0, 0), "no corpse near either is none");
    expect(TakeNearTheTarget(1) && !TakeNearTheTarget(0), "the corpse is taken near the target when one lies there");

    // Ricochet: a roll under the chance and a reach.
    expect(Ricochets(chance - 0.01, chance, 10), "a roll under the chance ricochets");
    expect(!Ricochets(chance, chance, 10), "a roll at the chance does not");
    expect(!Ricochets(0, chance, 0) && !Ricochets(0, chance, -3), "no reach stated, no ricochet");
    expect(!Ricochets(0, 0, 10), "no chance, no ricochet");

    // Shredding Splinters: the slow of each stack, up to the cap; stacks restart the time and end on the moment.
    expect(near(StackedPct(slow, 1, most), slow), "one stack, one slow", StackedPct(slow, 1, most), slow);
    expect(near(StackedPct(slow, most, most), slow * most), "the most stacks, the most slow");
    expect(near(StackedPct(slow, most + 3, most), slow * most), "never more than the cap",
           StackedPct(slow, most + 3, most), slow * most);
    expect(near(StackedPct(slow, 0, most), 0) && near(StackedPct(0, 3, most), 0) && near(StackedPct(-5, 3, most), 0),
           "no stack or no slow, none");
    Buffs::Held held;
    std::uint64_t const ms = std::uint64_t(seconds * 1000);
    expect(Buffs::Add(held, 1000, ms, most) == 1 && Buffs::Add(held, 2000, ms, most) == 2, "a lance, a stack");
    expect(held.until == 2000 + ms, "a lance restarts the time", double(held.until), double(2000 + ms));
    expect(Buffs::Add(held, 2000 + ms, ms, most) == 1, "after the time the stacks start again");

    // Brittle Touch: it holds until its end.
    expect(Holds(999, 1000) && !Holds(1000, 1000) && !Holds(2000, 1000), "the mark holds until the moment it ends");

    // The shared pile, cap and lifetime set here: the corpse nearest the target goes first.
    Pile pile;
    std::uint64_t const lifetime = 60000;
    pile.Leave(Spot{5, 0, 0, 0}, 1000, 10, lifetime);
    pile.Leave(Spot{float(nearTarget) - 1, 0, 0, 0}, 1001, 10, lifetime);
    pile.Leave(Spot{float(nearCaster) - 1, 0, 0, 0}, 1002, 10, lifetime);
    expect(pile.Count(float(nearTarget), 0, float(nearTarget), 2000, lifetime) >= 1,
           "a corpse within the reach of the target is counted");
    auto const taken = pile.Take(float(nearTarget), 0, float(nearTarget), 1, 2000, lifetime);
    expect(taken.size() == 1 && taken[0].x == float(nearTarget) - 1,
           "the nearest corpse to the target is the one taken", taken.empty() ? -1 : taken[0].x, nearTarget - 1);
    expect(pile.Size() == 2, "the others stay", double(pile.Size()), 2);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
