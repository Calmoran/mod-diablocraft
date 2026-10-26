// The Healing Stream Totem's rules (src/classes/shaman/dc_shaman_healing_stream_totem_math.h), driven with the sheet's
// own numbers. Prints "cases=N failures=M" and exits 0, or names the failing case and exits 1.
#include "classes/shaman/dc_shaman_healing_stream_totem_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::HealingStream;

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

static bool near(double a, double b)
{
    return std::fabs(a - b) < 1e-9;
}

int main(int argc, char** argv)
{
    // argv: the totem's percent of maximum Life a second, Healing Tide's percent, Maelstrom Spring's a second,
    // Cleansing Stream's seconds, Ancestral Protection's Life floor percent, the totem's look in seconds and its radius
    // in yards.
    if (argc < 8)
        return 2;
    double const regen = std::atof(argv[1]), tide = std::atof(argv[2]), spring = std::atof(argv[3]),
                 seconds = std::atof(argv[4]), floorPct = std::atof(argv[5]), tick = std::atof(argv[6]),
                 radius = std::atof(argv[7]);

    // A look heals its share of a second of the percent of maximum Life.
    expect(near(TickHeal(1000, regen, tick), 1000 * regen / 100.0 * tick) && TickHeal(1000, regen, tick) > 0,
           "a look heals the percent of maximum Life a second");
    expect(near(TickHeal(1000, regen, 2 * tick), 2 * TickHeal(1000, regen, tick)), "a longer look heals more");
    expect(TickHeal(0, regen, tick) == 0 && TickHeal(1000, 0, tick) == 0 && TickHeal(1000, -3, tick) == 0 &&
               TickHeal(1000, regen, 0) == 0,
           "no Life, no percent or no look, no heal");

    // Healing Tide heals its percent of maximum Life once, never more than all of it.
    expect(near(PlacedHeal(1000, tide), 1000 * tide / 100.0) && PlacedHeal(1000, tide) > 0,
           "Healing Tide heals its percent");
    expect(near(PlacedHeal(1000, 400), 1000) && PlacedHeal(1000, 0) == 0 && PlacedHeal(0, tide) == 0 &&
               PlacedHeal(1000, -5) == 0,
           "never more than the whole Life, and nothing for none");

    // Maelstrom Spring gives its number a second.
    expect(near(TickGain(spring, tick), spring * tick) && spring > 0, "Maelstrom Spring gives its share of a second");
    expect(TickGain(0, tick) == 0 && TickGain(spring, 0) == 0 && TickGain(-1, tick) == 0, "nothing for none");

    // Cleansing Stream's immunity ends the seconds after the totem was placed, and not a millisecond later.
    expect(Millis(0.5) == 500 && Millis(0) == 0 && Millis(-2) == 0, "seconds are milliseconds");
    std::uint64_t const until = ImmuneUntil(10000, seconds);
    expect(until == 10000 + Millis(seconds) && Millis(seconds) > 0, "the immunity ends the seconds after the placing");
    expect(Immune(until, until - 1) && !Immune(until, until) && !Immune(until, until + 1),
           "immune until the end and no longer");
    expect(ImmuneUntil(10000, 0) == 0 && !Immune(ImmuneUntil(10000, 0), 10000), "no seconds, no immunity");

    // Ancestral Protection: the first fatal blow within the radius is prevented, once.
    expect(Saves(100, 100, true, false) && Saves(100, 500, true, false), "a blow that takes all the Life is prevented");
    expect(!Saves(100, 99, true, false) && !Saves(100, 0, true, false), "a blow that leaves Life is no death");
    expect(!Saves(100, 500, false, false), "not outside the radius");
    expect(!Saves(100, 500, true, true), "not a second time");
    expect(near(SavedHealth(10, 1000, floorPct), 1000 * floorPct / 100.0) && SavedHealth(10, 1000, floorPct) > 10,
           "healed to the Life floor");
    expect(SavedHealth(900, 1000, floorPct) == 900, "never to less than the Life they had");
    expect(near(SavedHealth(10, 1000, 250), 1000) && SavedHealth(10, 0, floorPct) == 10 &&
               near(SavedHealth(10, 1000, -4), 10),
           "a floor past all the Life is all of it; none or a negative one is no heal");

    // The radius: the edge is within, past it is not.
    expect(Within(radius, radius) && Within(0, radius) && !Within(radius + 0.01, radius) && !Within(1, 0),
           "the edge of the radius is within it");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
