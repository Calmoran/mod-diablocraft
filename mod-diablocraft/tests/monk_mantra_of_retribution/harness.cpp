// diablocraft-2rjqh (Monk 2.3.20): the real dc_monk_mantra_of_retribution.h. Every number comes from argv (the sheets',
// read by test_monk_mantra_of_retribution.py). Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/monk/dc_monk_mantra_of_retribution.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk;

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
    // argv: passive (101), active (202), Retaliation's own (202), duration seconds (3), Indignation's chance (20),
    // Collateral Damage's chance (75)
    if (argc < 7)
        return 2;
    double const passive = std::atof(argv[1]), active = std::atof(argv[2]), retaliation = std::atof(argv[3]);
    std::uint64_t const boostMs = std::uint64_t(std::atof(argv[4]) * 1000.0);
    double const stunChance = std::atof(argv[5]), blastChance = std::atof(argv[6]);
    double const boost = active - passive;

    // The passive alone, then inside the activation window: the sheet's 101 and 202; Retaliation's 202 and 303 (power
    // file SF_25: 2.02 base, 3.03 with rune A).
    expect(near(MantraReflectPct(passive, boost, false), 101), "passive hit is the sheet's passive", passive);
    expect(near(MantraReflectPct(passive, boost, true), active), "boosted hit is the sheet's active", active);
    expect(near(MantraReflectPct(retaliation, boost, false), 202), "Retaliation passive is its 202");
    expect(near(MantraReflectPct(retaliation, boost, true), 303), "Retaliation boosted is 303");
    expect(near(MantraReflectPct(passive, -50, true), passive), "a negative boost adds nothing");
    expect(MantraReflectPct(-5, 0, false) == 0, "never negative");

    // Chances: under the chance procs, at or over does not, a blank chance never does.
    expect(MantraProcs(stunChance, 0.0), "roll 0 procs a 20% chance");
    expect(MantraProcs(stunChance, stunChance - 0.01), "just under the chance procs");
    expect(!MantraProcs(stunChance, stunChance), "the chance itself does not proc");
    expect(!MantraProcs(stunChance, 99.9), "a high roll does not proc");
    expect(MantraProcs(blastChance, 74.9) && !MantraProcs(blastChance, 75.0), "75% edge");
    expect(!MantraProcs(0, 0.0), "a blank chance never procs");
    expect(!MantraProcs(-3, 0.0), "a negative chance never procs");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
