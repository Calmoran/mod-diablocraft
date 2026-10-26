// The real dc_crusader_judgment.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_judgment.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/crusader/dc_crusader_judgment.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Judgment;

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
    // argv: Penitence's heal for each enemy, Resolved's crit chance, then the five runes A to E
    if (argc < 8)
        return 2;
    double const heal = std::atof(argv[1]), crit = std::atof(argv[2]);
    std::string const penitence = argv[3], mass = argv[4], deliberation = argv[5], resolved = argv[6],
                      debilitate = argv[7];

    expect(RuneOf(penitence) == Rune::Penitence && RuneOf(mass) == Rune::MassVerdict &&
               RuneOf(deliberation) == Rune::Deliberation && RuneOf(resolved) == Rune::Resolved &&
               RuneOf(debilitate) == Rune::Debilitate,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {penitence, mass, deliberation, resolved, debilitate})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Verdict") == Rune::None, "the base skill and a stranger are no rune");

    // Penitence: each enemy judged adds its own heal.
    expect(HealPerTick(heal, 3) == 3 * heal, "three enemies heal three times", HealPerTick(heal, 3), 3 * heal);
    expect(HealPerTick(heal, 1) == heal, "one enemy heals once", HealPerTick(heal, 1), heal);
    expect(HealPerTick(heal, 0) == 0 && HealPerTick(0, 4) == 0, "no enemy or no heal gives nothing");
    expect(HealPerTick(-heal, 3) == 0, "a negative heal gives nothing");

    // Judged: until the end time, not at it.
    expect(Judged(999, 1000) && !Judged(1000, 1000) && !Judged(1001, 1000), "an enemy is judged until the end time");

    // Resolved: only the rune, only on a judged enemy.
    expect(CritFor(Rune::Resolved, true, crit) == crit, "Resolved adds its chance on a judged enemy",
           CritFor(Rune::Resolved, true, crit), crit);
    expect(CritFor(Rune::Resolved, false, crit) == 0, "not on an enemy that is not judged");
    for (Rune rune : {Rune::None, Rune::Penitence, Rune::MassVerdict, Rune::Deliberation, Rune::Debilitate})
        expect(CritFor(rune, true, crit) == 0, "no other rune adds crit chance");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
