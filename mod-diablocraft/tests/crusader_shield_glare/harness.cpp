// The real dc_crusader_shield_glare.h. The rune names and numbers come from argv (read from the sheets and the tunables
// by test_crusader_shield_glare.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/crusader/dc_crusader_shield_glare.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::ShieldGlare;

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
    // argv: the reach, the arc in degrees, the life threshold, the Wrath per enemy, then the five runes A to E
    if (argc < 10)
        return 2;
    double const reach = std::atof(argv[1]), degrees = std::atof(argv[2]), threshold = std::atof(argv[3]),
                 perEnemy = std::atof(argv[4]);
    std::string const verdict = argv[5], uncertainty = argv[6], emblazoned = argv[7], zealous = argv[8],
                      subdue = argv[9];
    double const pi = 3.14159265358979323846;

    expect(RuneOf(verdict) == Rune::DivineVerdict && RuneOf(uncertainty) == Rune::Uncertainty &&
               RuneOf(emblazoned) == Rune::EmblazonedShield && RuneOf(zealous) == Rune::ZealousGlare &&
               RuneOf(subdue) == Rune::Subdue,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {verdict, uncertainty, emblazoned, zealous, subdue})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Glare") == Rune::None, "the base skill and a stranger are no rune");

    // The arc: the sheet's degrees in radians.
    expect(std::fabs(ArcRadians(degrees) - degrees * pi / 180) < 1e-12, "the arc is the degrees in radians",
           ArcRadians(degrees), degrees * pi / 180);
    expect(std::fabs(ArcRadians(180) - pi) < 1e-12, "half a turn is pi");

    // Who the arc catches beyond the core's cone: in the arc, within the reach, not blinded already.
    expect(Caught(reach, reach, true, false), "an enemy at the edge of the reach is caught", reach, 0);
    expect(!Caught(reach + 0.01, reach, true, false), "one past the reach is not", reach, 0);
    expect(!Caught(5, reach, false, false), "an enemy outside the arc is not caught");
    expect(!Caught(5, reach, true, true), "an enemy the cone took is not blinded twice");
    expect(!Caught(5, 0, true, false), "no reach, nobody caught");

    // Emblazoned Shield: strictly below the life threshold.
    expect(Low(threshold - 0.01, threshold) && !Low(threshold, threshold) && !Low(100, threshold),
           "only an enemy under the threshold is low", threshold, 0);

    // Zealous Glare: the Wrath is for each enemy blinded.
    expect(WrathFor(perEnemy, 4) == 4 * perEnemy, "four enemies give four times the Wrath", WrathFor(perEnemy, 4),
           4 * perEnemy);
    expect(WrathFor(perEnemy, 0) == 0, "no enemy, no Wrath");
    expect(WrathFor(0, 5) == 0 && WrathFor(-3, 5) == 0, "no Wrath per enemy gives none");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
