// The real dc_witch_doctor_fetish_army_math.h. The chance comes from argv (read from the tunables by
// test_witch_doctor_fetish_army.py). Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_fetish_army_math.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::WitchDoctor::FetishArmy;

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
    // argv: Fetish Ambush's chance to appear on an enemy.
    if (argc < 2)
        return 2;
    double const chance = std::atof(argv[1]);

    // Fetish Ambush: whether a dagger appears on an enemy.
    expect(Apparates(0.0, chance), "a roll of nothing is under the chance");
    expect(!Apparates(chance, chance) && !Apparates(chance + 0.5, chance),
           "a roll at or over the chance stays on the ring");
    expect(Apparates(chance - 0.01, chance), "a roll just under it appears");
    expect(!Apparates(0.0, 0) && !Apparates(0.0, -5) && !Apparates(-10.0, 0), "no chance, none appear");

    // Which enemy.
    expect(Pick(5, 0.0) == 0 && Pick(5, 0.5) == 2 && Pick(5, 0.999) == 4, "an equal share of the draw for each enemy");
    expect(Pick(4, 0.25) == 1 && Pick(4, 0.24) == 0, "a share starts where the last one ends");
    expect(Pick(5, 1.0) == 4 && Pick(5, 7.0) == 4, "never past the last enemy");
    expect(Pick(5, -1.0) == 0, "a draw below nothing is the first");
    expect(Pick(0, 0.5) == 0 && Pick(1, 0.9) == 0, "one enemy or none, the first");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
