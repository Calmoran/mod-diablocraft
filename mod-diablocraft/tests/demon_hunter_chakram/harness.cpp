// The real dc_demon_hunter_chakram.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_demon_hunter_chakram.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/demon_hunter/dc_demon_hunter_chakram.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::Chakram;

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
    // argv: the five runes A to E, the cloud's damage a second, its tick, its minutes.
    if (argc < 9)
        return 2;
    std::string const twin = argv[1], boomerang = argv[2], serpentine = argv[3], razor = argv[4], cloud = argv[5];
    double const perSecond = std::atof(argv[6]), tick = std::atof(argv[7]), minutes = std::atof(argv[8]);

    expect(RuneOf(twin) == Rune::TwinChakrams && RuneOf(boomerang) == Rune::Boomerang && RuneOf(serpentine) == Rune::Serpentine &&
               RuneOf(razor) == Rune::RazorDisk && RuneOf(cloud) == Rune::ShurikenCloud,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {twin, boomerang, serpentine, razor, cloud})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The cloud: a tick carries its share of the second, and the ticks of a second together deal the sheet's damage.
    expect(std::fabs(CloudTickPct(perSecond, tick) - perSecond * tick) < 1e-9, "a tick is its share of the second", CloudTickPct(perSecond, tick),
           perSecond * tick);
    expect(CloudTickPct(perSecond, 0) == 0 && CloudTickPct(perSecond, -1) == 0, "no tick, no damage");
    expect(CloudEndsAt(1000, minutes) == 1000 + std::uint64_t(minutes * 60000), "it lasts its minutes", double(CloudEndsAt(1000, minutes)),
           1000 + minutes * 60000);
    expect(CloudEndsAt(1000, 0) == 1000, "no minutes, it ends at once");

    // Held for ten seconds of server updates of 70 ms (not a divisor of the tick, so the rest of each update counts): the cloud
    // ticks at its cadence and deals the sheet's damage a second.
    double clock = 0;
    unsigned ticks = 0;
    for (int update = 0; update < 143; ++update)
        ticks += Due(clock, 70, tick * 1000.0);
    expect(std::fabs(double(ticks) - 10.01 / tick) < 1.0, "ten seconds, a tick every half second", double(ticks), 10.01 / tick);
    expect(std::fabs(double(ticks) * CloudTickPct(perSecond, tick) - 10.01 * perSecond) < CloudTickPct(perSecond, tick),
           "and the sheet's damage a second", double(ticks) * CloudTickPct(perSecond, tick), 10.01 * perSecond);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
