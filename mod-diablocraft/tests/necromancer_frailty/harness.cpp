// The real dc_necromancer_frailty_math.h. The rune names and thresholds come from argv (read from the sheets by
// test_necromancer_frailty.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_frailty_math.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::Frailty;

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
    // argv: the five runes A to E; the skill's threshold and Early Grave's (percent of Life)
    if (argc < 8)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    double const base = std::atof(argv[6]), early = std::atof(argv[7]);

    expect(RuneOf(names[0]) == Rune::EarlyGrave && RuneOf(names[1]) == Rune::HarvestEssence && RuneOf(names[2]) == Rune::VolatileDeath &&
               RuneOf(names[3]) == Rune::ScentOfBlood && RuneOf(names[4]) == Rune::AuraOfFrailty,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Frailty") == Rune::None && RuneOf("early grave") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // The curse kills an enemy whose Life is under the threshold, not at it.
    expect(Executes(base - 0.01, base) && Executes(0.0, base) && Executes(1.0, base), "an enemy under the threshold dies");
    expect(!Executes(base, base) && !Executes(base + 0.01, base) && !Executes(100.0, base), "at the threshold and above does not");
    expect(early > base, "Early Grave kills at a higher share than the skill", early, base);
    expect(Executes(base + 1.0, early) && !Executes(base + 1.0, base), "an enemy between the two thresholds dies only to Early Grave");
    expect(!Executes(0.0, 0) && !Executes(0.0, -5), "no threshold, no kill");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
