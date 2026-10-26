// diablocraft-ogwtu (Monk 2.3.06): the real dc_monk_tempest_rush.h. Every number comes from argv (the tunables sheet's
// and monk_skill_values.csv's, read by test_monk_tempest_rush.py). Prints "cases=N" and exits 0, or names the first
// failing case and exits 1.
#include "classes/monk/dc_monk_tempest_rush.h"

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
    // argv: damage per second (390), cost per second (30), tick seconds (0.2), Electric Field per second (135), field
    // tick seconds (0.25), flurry cap (100)
    if (argc < 7)
        return 2;
    double const damage = std::atof(argv[1]), cost = std::atof(argv[2]), tick = std::atof(argv[3]);
    double const field = std::atof(argv[4]), fieldTick = std::atof(argv[5]);
    unsigned const cap = unsigned(std::atof(argv[6]));

    // Five ticks a second add up to the per-second number, whatever the interval.
    expect(near(PerTick(damage, tick) * (1.0 / tick), damage), "ticks add up to the damage a second",
           PerTick(damage, tick) * 5, damage);
    expect(near(PerTick(cost, tick) * (1.0 / tick), cost), "and to the Spirit a second", PerTick(cost, tick) * 5, cost);
    expect(near(PerTick(field, fieldTick) * (1.0 / fieldTick), field), "Electric Field's share adds up too");
    expect(near(PerTick(damage, 0), 0), "no interval, no tick");
    expect(near(PerTick(0, tick), 0) && near(PerTick(-5, tick), 0), "no number, no tick");
    expect(near(PerTick(damage, tick), 78) || damage != 390 || tick != 0.2, "390% in 0.2 s ticks is 78% a tick",
           PerTick(damage, tick), 78);

    // The press pays the first second; the ticks after it pay.
    Prepaid prepaid;
    prepaid.Press(5000, 1000);
    expect(prepaid.Covers(5000), "the press covers its own moment");
    expect(prepaid.Covers(5999), "and the second after it", 0, 0);
    expect(!prepaid.Covers(6000), "the tick at one second pays");
    expect(!prepaid.Covers(9000), "and so do the later ones");
    expect(!Prepaid{}.Covers(0), "nothing is prepaid before a press");

    // Flurry: a stack for each attack period of channeling, capped.
    expect(FlurryStacks(0, 1.2, cap) == 0, "no time, no stack");
    expect(FlurryStacks(1.0, 1.2, cap) == 1, "one second at 1.2 attacks a second is one period",
           FlurryStacks(1.0, 1.2, cap), 1);
    expect(FlurryStacks(5.0, 2.0, cap) == 10, "five seconds at 2 attacks a second is ten", FlurryStacks(5.0, 2.0, cap),
           10);
    expect(FlurryStacks(1000.0, 2.0, cap) == cap, "the stacks stop at the cap", FlurryStacks(1000.0, 2.0, cap), cap);
    expect(FlurryStacks(5.0, 0, cap) == 0, "no attack speed, no stack");
    expect(FlurryStacks(-1.0, 2.0, cap) == 0, "no negative time");

    // Bluster: one knockback an enemy for the channel.
    Seen seen;
    expect(seen.First(42), "the first sight of an enemy knocks it back");
    expect(!seen.First(42), "the second does not");
    expect(seen.First(43), "another enemy does");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
