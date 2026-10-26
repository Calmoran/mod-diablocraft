// diablocraft-wv17q (Monk 2.3.21): the real dc_monk_mantra_of_healing.h. The sheets' numbers come from argv (read by
// test_monk_mantra_of_healing.py). Prints "cases=N failures=M" and exits 0, or names each failing case and exits 1.
#include "classes/monk/dc_monk_mantra_of_healing.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Healing;

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
    // argv: heal per second (10728), Sustenance's (21457), share of Life per Second (7), per hit (3576), share of Life
    // per Hit (20), absorb (62064), absorb share of the globe bonus (15), threshold (50), Spirit per second (3)
    if (argc < 10)
        return 2;
    double const base = std::atof(argv[1]), sustenance = std::atof(argv[2]), share = std::atof(argv[3]);
    double const perHit = std::atof(argv[4]), hitShare = std::atof(argv[5]), absorb = std::atof(argv[6]);
    double const globeShare = std::atof(argv[7]), threshold = std::atof(argv[8]), spirit = std::atof(argv[9]);

    // The pulse heal: the number, plus a share of the Monk's Life per Second, over the pulse's seconds.
    expect(near(PulseHeal(base, 0, share, 1.0), base), "with no Life per Second the pulse is the sheet's number",
           PulseHeal(base, 0, share, 1.0), base);
    expect(near(PulseHeal(base, 1000, share, 1.0), base + 70), "7% of 1000 Life per Second is added",
           PulseHeal(base, 1000, share, 1.0), base + 70);
    expect(near(PulseHeal(sustenance, 0, share, 1.0), sustenance), "Sustenance's number replaces the skill's");
    expect(near(PulseHeal(base, 0, share, 0.5), base / 2), "a half second pulse heals half",
           PulseHeal(base, 0, share, 0.5), base / 2);
    expect(near(PulseHeal(base, 0, share, 0), 0) && near(PulseHeal(base, 0, share, -1), 0), "no seconds, no heal");
    expect(near(PulseHeal(-5, -100, share, 1.0), 0), "a negative number heals nothing");

    // The heal of a hit.
    expect(near(HitHeal(perHit, 0, hitShare), perHit), "a hit heals the sheet's number", HitHeal(perHit, 0, hitShare),
           perHit);
    expect(near(HitHeal(perHit, 500, hitShare), perHit + 100), "20% of 500 Life per Hit is added",
           HitHeal(perHit, 500, hitShare), perHit + 100);
    expect(near(HitHeal(-1, -1, hitShare), 0), "nothing negative");

    // The absorb: the sheet's number, raised by the share of the globe bonus.
    expect(near(Absorb(absorb, globeShare, 0), absorb), "with no globe bonus the absorb is the sheet's",
           Absorb(absorb, globeShare, 0), absorb);
    expect(near(Absorb(absorb, globeShare, 100), absorb * 1.15), "15% of a 100% bonus raises it 15%",
           Absorb(absorb, globeShare, 100), absorb * 1.15);
    expect(near(Absorb(-1, globeShare, 100), 0), "no negative absorb");

    // Time of Need: strictly below.
    expect(BelowThreshold(threshold - 0.1, threshold), "below the threshold the reduction applies");
    expect(!BelowThreshold(threshold, threshold), "at the threshold it does not");
    expect(!BelowThreshold(100, threshold), "at full Life it does not");

    // Circular Breathing.
    expect(near(SpiritPerPulse(spirit, 1.0), spirit), "a second pays the sheet's Spirit", SpiritPerPulse(spirit, 1.0),
           spirit);
    expect(near(SpiritPerPulse(spirit, 0.5), spirit / 2), "half a second pays half");
    expect(near(SpiritPerPulse(0, 1.0), 0) && near(SpiritPerPulse(spirit, 0), 0), "no number or no seconds, no Spirit");

    // Who left the aura.
    auto left = Left({1, 2, 3}, {1, 3, 4});
    expect(left.size() == 1 && left[0] == 2, "the holder not in the new pulse has left");
    expect(Left({1}, {1}).empty() && Left({}, {1}).empty(), "nobody left");
    expect(Left({1, 2}, {}).size() == 2, "everyone left when nobody is held");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
