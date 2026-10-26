// The Shaman's totem rules (src/classes/shaman/dc_shaman_totems_math.h), driven with the sheet's own numbers. Prints
// "cases=N failures=M" and exits 0, or names the failing case and exits 1.
#include "classes/shaman/dc_shaman_totems_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

using namespace DC::Combat::Shaman::Totems;

static int failures = 0;
static int cases = 0;

static void expect(bool ok, char const* what)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s\n", what);
        ++failures;
    }
}

int main(int argc, char** argv)
{
    // argv: the four slots' creature entries (fire, earth, water, air), then the Searing Totem's interval and duration
    // seconds.
    if (argc < 7)
        return 2;
    std::uint32_t const fire = std::uint32_t(std::atol(argv[1])), earth = std::uint32_t(std::atol(argv[2])),
                        water = std::uint32_t(std::atol(argv[3])), air = std::uint32_t(std::atol(argv[4]));
    double const interval = std::atof(argv[5]), duration = std::atof(argv[6]);

    // The native slots hold their own creature and nothing else holds one.
    expect(EntryOfSlot(FireSlot) == fire && EntryOfSlot(EarthSlot) == earth && EntryOfSlot(WaterSlot) == water &&
               EntryOfSlot(AirSlot) == air,
           "each totem slot holds the creature of the sheet");
    expect(EntryOfSlot(0) == 0 && EntryOfSlot(5) == 0 && EntryOfSlot(99) == 0,
           "a slot that is no totem slot holds none");
    expect(fire != earth && fire != water && fire != air && earth != water && earth != air && water != air,
           "the four creatures are four");

    // A totem stands for the skill's seconds, and a totem with no time is not placed.
    expect(DurationMs(duration) == std::uint32_t(std::llround(duration * 1000.0)) && DurationMs(duration) > 0,
           "a totem lasts the skill's seconds");
    expect(DurationMs(0) == 0 && DurationMs(-3) == 0, "no seconds, no totem");
    expect(DurationMs(0.0004) == 0 && DurationMs(0.5) == 500, "seconds are milliseconds");

    // Pulses: one per interval of the skill's record, the rest of the clock kept, none without an interval.
    std::uint32_t clock = 0;
    std::uint32_t const period = DurationMs(interval);
    expect(Pulses(clock, period - 1, interval) == 0 && clock == period - 1,
           "nothing is due a millisecond short of the interval");
    expect(Pulses(clock, 1, interval) == 1 && clock == 0, "one is due at the interval");
    clock = 0;
    expect(Pulses(clock, 2 * period + 7, interval) == 2 && clock == 7, "two whole intervals and the rest kept");
    expect(Pulses(clock, period - 7, interval) == 1 && clock == 0, "the kept rest joins the next update");
    clock = 500;
    expect(Pulses(clock, 1000, 0) == 0 && clock == 0, "no interval, no pulse, and the clock cleared");
    expect(Pulses(clock, 1000, -2) == 0, "a negative interval is none");

    // The bolt goes to the nearest enemy within reach.
    expect(Nearest({}) == None, "no enemy, no bolt");
    expect(Nearest({9.5, 3.25, 12.0}) == 1, "the nearest of three");
    expect(Nearest({4.0, 4.0, 5.0}) == 0, "equals: the first");
    expect(Nearest({2.0}) == 0, "one enemy is the nearest");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
