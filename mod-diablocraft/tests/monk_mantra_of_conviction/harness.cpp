// diablocraft-mrpzh (Monk 2.3.22): the real dc_monk_mantra_of_conviction.h. Every number comes from argv
// (monk_skill_values.csv's and data/tunables/monk.csv's, read by test_monk_mantra_of_conviction.py).
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_mantra_of_conviction.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Conviction;

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
    return std::abs(a - b) < 1e-9;
}

int main(int argc, char** argv)
{
    // argv: passive %, active %, Overawe %, Submission % per second, tick s, boost s
    if (argc < 7)
        return 2;
    double const passive = std::atof(argv[1]), active = std::atof(argv[2]), overawe = std::atof(argv[3]),
                 submission = std::atof(argv[4]), tick = std::atof(argv[5]), boost = std::atof(argv[6]);

    // The damage the marked enemies take: 8, 16 in the activation's window; Overawe 12, and 20 in the window.
    expect(near(TakenPct(passive, active, passive, false), passive), "the passive alone", TakenPct(passive, active, passive, false), passive);
    expect(near(TakenPct(passive, active, passive, true), active), "the activation reaches the active number", TakenPct(passive, active, passive, true), active);
    expect(near(TakenPct(overawe, active, passive, false), overawe), "Overawe's passive replaces the skill's");
    expect(near(TakenPct(overawe, active, passive, true), overawe + active - passive), "Overawe adds the activation's increase",
           TakenPct(overawe, active, passive, true), overawe + active - passive);
    expect(near(TakenPct(-1, active, passive, false), 0), "never negative");
    expect(near(TakenPct(passive, passive - 1, passive, true), passive), "an active below the passive adds nothing");

    // Submission's damage per tick.
    expect(near(TickPct(submission, tick), submission * tick), "a tick is its share of a second", TickPct(submission, tick), submission * tick);
    expect(TickPct(submission, 0) == 0 && TickPct(0, tick) == 0, "an open tick or rate deals nothing");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
