// The real dc_crusader_slash.h. The rune names, Crush's number and the reaches come from argv (read from the sheets and
// the tunables by test_crusader_slash.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/crusader/dc_crusader_slash.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Slash;

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
    // argv: Crush's number, the base reach, Carve's reach, Carve's arc in degrees, then the five runes A to E
    if (argc < 10)
        return 2;
    double const crush = std::atof(argv[1]), base = std::atof(argv[2]), carve = std::atof(argv[3]),
                 degrees = std::atof(argv[4]);
    std::string const zeal = argv[5], electrify = argv[6], crushRune = argv[7], carveRune = argv[8], guard = argv[9];

    expect(RuneOf(zeal) == Rune::Zeal && RuneOf(electrify) == Rune::Electrify && RuneOf(crushRune) == Rune::Crush &&
               RuneOf(carveRune) == Rune::Carve && RuneOf(guard) == Rune::Guard,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {zeal, electrify, crushRune, carveRune, guard})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Fury") == Rune::None, "the base skill and a stranger are no rune");

    // Crush's number is for Crush's own hits only.
    expect(CrushCrit(Rune::Crush, crush) == crush, "Crush gives its number", CrushCrit(Rune::Crush, crush), crush);
    expect(CrushCrit(Rune::None, crush) == 0 && CrushCrit(Rune::Zeal, crush) == 0 && CrushCrit(Rune::Carve, crush) == 0,
           "no other rune gives it");

    // Carve: past the skill's own reach, inside the larger one, not struck already.
    expect(carve > base, "Carve reaches further than the skill", carve, base);
    expect(Carved(base + 0.5, carve, base, false), "an enemy just beyond the cone is carved");
    expect(Carved(carve, carve, base, false), "the edge of the reach is carved", carve, carve);
    expect(!Carved(carve + 0.01, carve, base, false), "an enemy past the reach is not carved");
    expect(!Carved(base + 0.5, carve, base, true), "an enemy the cone struck is not struck twice");
    expect(!Carved(base - 0.5, base, base, false), "a reach that is no larger carves nothing");

    expect(std::fabs(ArcRadians(degrees) - 3.14159265358979323846 * degrees / 180.0) < 1e-9, "degrees to radians",
           ArcRadians(degrees), degrees);
    expect(std::fabs(ArcRadians(180.0) - 3.14159265358979323846) < 1e-9, "a half circle is pi");
    expect(std::fabs(ArcRadians(120.0) - 2 * 3.14159265358979323846 / 3) < 1e-9, "Carve's 120 degrees is a third of a circle");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
