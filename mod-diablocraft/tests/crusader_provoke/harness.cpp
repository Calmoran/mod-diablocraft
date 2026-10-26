// The real dc_crusader_provoke.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_provoke.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/crusader/dc_crusader_provoke.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Provoke;

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
    // argv: the base Wrath, the Wrath for each enemy, Charged Up's percentage, then the five runes A to E
    if (argc < 9)
        return 2;
    double const base = std::atof(argv[1]), perEnemy = std::atof(argv[2]), pct = std::atof(argv[3]);
    std::string const cleanse = argv[4], flee = argv[5], scared = argv[6], charged = argv[7], hitMe = argv[8];

    expect(RuneOf(cleanse) == Rune::Cleanse && RuneOf(flee) == Rune::FleeFool && RuneOf(scared) == Rune::TooScaredToRun &&
               RuneOf(charged) == Rune::ChargedUp && RuneOf(hitMe) == Rune::HitMe,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {cleanse, flee, scared, charged, hitMe})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Provoke") == Rune::None, "the base skill and a stranger are no rune");

    // Only Flee Fool frightens; every other rune and the skill taunt.
    expect(Frightens(Rune::FleeFool), "Flee Fool frightens");
    for (Rune rune : {Rune::None, Rune::Cleanse, Rune::TooScaredToRun, Rune::ChargedUp, Rune::HitMe})
        expect(!Frightens(rune), "no other rune frightens");

    // The Wrath: the base always, the extra for each enemy.
    expect(WrathFor(base, perEnemy, 0) == base, "no enemy pays the base alone", WrathFor(base, perEnemy, 0), base);
    expect(WrathFor(base, perEnemy, 4) == base + 4 * perEnemy, "four enemies pay the base and four extras",
           WrathFor(base, perEnemy, 4), base + 4 * perEnemy);
    expect(WrathFor(base, 0, 3) == base && WrathFor(0, perEnemy, 3) == 3 * perEnemy, "each part stands alone");
    expect(WrathFor(-base, -perEnemy, 3) == 0, "a negative number pays nothing");

    // Cleanse: a stack for each enemy, no other rune stacks.
    expect(CleanseStacks(Rune::Cleanse, 5) == 5 && CleanseStacks(Rune::Cleanse, 0) == 0, "Cleanse stacks once per enemy");
    for (Rune rune : {Rune::None, Rune::FleeFool, Rune::TooScaredToRun, Rune::ChargedUp, Rune::HitMe})
        expect(CleanseStacks(rune, 5) == 0, "no other rune stacks Life on Hit");

    // Charged Up: until the end time, not at it.
    expect(Charged(999, 1000) && !Charged(1000, 1000) && !Charged(1001, 1000), "Charged Up lasts until the end time");

    // The rider: only the rune, only while it lasts, never for its own hit.
    expect(RiderPct(Rune::ChargedUp, true, false, pct) == pct, "Charged Up adds its percentage", RiderPct(Rune::ChargedUp, true, false, pct), pct);
    expect(RiderPct(Rune::ChargedUp, false, false, pct) == 0, "not once it is over");
    expect(RiderPct(Rune::ChargedUp, true, true, pct) == 0, "not on its own hit");
    expect(RiderPct(Rune::ChargedUp, true, false, -pct) == 0, "a negative percentage adds nothing");
    for (Rune rune : {Rune::None, Rune::Cleanse, Rune::FleeFool, Rune::TooScaredToRun, Rune::HitMe})
        expect(RiderPct(rune, true, false, pct) == 0, "no other rune adds a rider");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
