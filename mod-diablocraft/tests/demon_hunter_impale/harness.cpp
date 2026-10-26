// The real dc_demon_hunter_impale.h and the line rule of dc_demon_hunter_seek.h. The rune names and numbers come from argv
// (read from the sheets and the tunables by test_demon_hunter_impale.py); nothing is typed in here. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_impale.h"
#include "classes/demon_hunter/dc_demon_hunter_seek.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::Impale;

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
    // argv: the five runes A to E, the knife's damage percent, the ricochet's decay, the line's length and width.
    if (argc < 10)
        return 2;
    std::string const over = argv[1], impact = argv[2], burn = argv[3], ricochet = argv[4], grievous = argv[5];
    double const pct = std::atof(argv[6]), decay = std::atof(argv[7]), length = std::atof(argv[8]), width = std::atof(argv[9]);
    constexpr double Pi = 3.14159265358979323846;

    expect(RuneOf(over) == Rune::Overpenetration && RuneOf(impact) == Rune::Impact && RuneOf(burn) == Rune::ChemicalBurn &&
               RuneOf(ricochet) == Rune::Ricochet && RuneOf(grievous) == Rune::GrievousWounds,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {over, impact, burn, ricochet, grievous})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Ricochet: each bounce keeps the factor of the hit before.
    expect(BouncePct(pct, decay, 0) == pct, "the first enemy takes the knife's own damage", BouncePct(pct, decay, 0), pct);
    expect(std::fabs(BouncePct(pct, decay, 2) - pct * decay * decay) < 1e-9, "each bounce keeps the factor", BouncePct(pct, decay, 2),
           pct * decay * decay);
    expect(std::fabs(BouncePct(100, 0.5, 3) - 12.5) < 1e-9, "a factor under one loses damage at every bounce");

    // Overpenetration: the line from the Demon Hunter through the enemy hit, east of them here.
    expect(OnLine(10, 0, 0, length, width) && OnLine(length, 0, 0, length, width), "an enemy on the line, to its end, is pierced");
    expect(!OnLine(length + 0.1, 0, 0, length, width), "one past its end is not");
    expect(!OnLine(-1, 0, 0, length, width), "one behind is not");
    expect(OnLine(10, width / 2 - 0.01, 0, length, width) && OnLine(10, -width / 2 + 0.01, 0, length, width),
           "within half the width either side is on it");
    expect(!OnLine(10, width / 2 + 0.01, 0, length, width) && !OnLine(10, -width / 2 - 0.01, 0, length, width),
           "past half the width is off it");
    expect(OnLine(0, 10, Pi / 2, length, width) && !OnLine(10, 0, Pi / 2, length, width), "the line follows the heading");
    expect(!OnLine(10, 0, 0, length, 0), "a line with no width takes nobody");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
