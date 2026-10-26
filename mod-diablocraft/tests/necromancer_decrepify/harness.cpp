// The real dc_necromancer_decrepify_math.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_necromancer_decrepify.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_decrepify_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::Decrepify;

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
    // argv: the five runes A to E; the slow (normal), Enfeeblement's start, its decay a second and its seconds; Opportunist's speed per
    // enemy and its most; Borrowed Time's cooldown reduction per enemy and its most; Dizzying Curse's chance
    if (argc < 15)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    double const base = std::atof(argv[6]), start = std::atof(argv[7]), perSecond = std::atof(argv[8]), seconds = std::atof(argv[9]),
                 speedPer = std::atof(argv[10]), speedMost = std::atof(argv[11]), cdrPer = std::atof(argv[12]),
                 cdrMost = std::atof(argv[13]), chance = std::atof(argv[14]);

    expect(RuneOf(names[0]) == Rune::Enfeeblement && RuneOf(names[1]) == Rune::Opportunist && RuneOf(names[2]) == Rune::BorrowedTime &&
               RuneOf(names[3]) == Rune::Wither && RuneOf(names[4]) == Rune::DizzyingCurse,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Decrepify") == Rune::None && RuneOf("wither") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // Enfeeblement: from the start down by the decay each second, no further than the normal slow, reaching it in the rune's seconds.
    expect(near(DecayedSlow(start, base, perSecond, 0), start), "the slow starts at the rune's number");
    expect(near(DecayedSlow(start, base, perSecond, 1), start - perSecond), "and weakens by the decay each second");
    expect(near(DecayedSlow(start, base, perSecond, seconds), base), "it is the normal slow when the rune's seconds are spent",
           DecayedSlow(start, base, perSecond, seconds), base);
    expect(near(DecayedSlow(start, base, perSecond, seconds - 1), base + perSecond), "a second before it is one decay above");
    expect(near(DecayedSlow(start, base, perSecond, seconds * 10), base), "it never weakens below the normal slow");
    expect(near(DecayedSlow(start, base, perSecond, -3), start) && near(DecayedSlow(start, base, -2, 4), start),
           "no time or a negative decay: it stays at the start");
    expect(Steps(seconds, 1.0) == unsigned(seconds) && Steps(0, 1.0) == 0 && Steps(5, 0) == 0 && Steps(0.3, 0.1) == 3,
           "the whole steps that fit, none for no time or no step");

    // Opportunist and Borrowed Time: a number for each enemy cursed, none past the most.
    expect(near(StackBonus(0, speedPer, speedMost), 0), "no enemy cursed, no bonus");
    expect(near(StackBonus(3, speedPer, speedMost), 3 * speedPer), "each enemy cursed gives its share");
    expect(near(StackBonus(1000, speedPer, speedMost), speedMost), "none past the most", StackBonus(1000, speedPer, speedMost), speedMost);
    expect(near(StackBonus(1000, cdrPer, cdrMost), cdrMost) && near(StackBonus(2, cdrPer, cdrMost), 2 * cdrPer),
           "the cooldown reduction likewise");
    expect(StackBonus(5, -1, speedMost) == 0.0 && StackBonus(5, speedPer, -4) == 0.0, "a negative number gives nothing");

    // Dizzying Curse: a roll under the chance stuns, the chance itself and above does not.
    expect(Procs(0.0, chance) && Procs(chance - 0.01, chance), "a roll under the chance lands");
    expect(!Procs(chance, chance) && !Procs(99.9, chance), "the chance and above does not");
    expect(!Procs(0.0, 0) && !Procs(0.0, -5), "no chance, no stun");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
