// The real dc_shaman_earth_elemental.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_earth_elemental.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/shaman/dc_shaman_earth_elemental.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::EarthElemental;

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
    // argv: the five runes A to E, the elemental's seconds, the stomp interval, a zone's damage per second, the zone
    // tick, the stomp's radius.
    if (argc < 11)
        return 2;
    std::string const bedrock = argv[1], primal = argv[2], magma = argv[3], thunder = argv[4], glacial = argv[5];
    double const seconds = std::atof(argv[6]), interval = std::atof(argv[7]), perSecond = std::atof(argv[8]),
                 tick = std::atof(argv[9]), radius = std::atof(argv[10]);

    expect(RuneOf(bedrock) == Rune::Bedrock && RuneOf(primal) == Rune::PrimalEarthElemental &&
               RuneOf(magma) == Rune::MagmaColossus && RuneOf(thunder) == Rune::ThunderColossus &&
               RuneOf(glacial) == Rune::GlacialColossus,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Earth Elemental") == Rune::None &&
               RuneOf("Fire Elemental") == Rune::None,
           "and nothing else is");

    // Bedrock states the new damage reduction; every other rune the skill's.
    expect(ReductionQualifier(Rune::Bedrock) == "new" && ReductionQualifier(Rune::None) == "" &&
               ReductionQualifier(Rune::GlacialColossus) == "" && ReductionQualifier(Rune::PrimalEarthElemental) == "",
           "only Bedrock reads the new damage reduction");

    // Stomps.
    unsigned const stomps = Stomps(seconds, interval);
    expect(stomps >= 1 && double(stomps) * interval <= seconds && double(stomps + 1) * interval > seconds,
           "as many stomps fit the seconds as the interval allows", double(stomps), seconds / interval);
    expect(Stomps(0, interval) == 0 && Stomps(seconds, 0) == 0 && Stomps(seconds, -1) == 0,
           "and none without seconds or an interval");

    // A zone's tick deals above 0 and the ticks of a second add up.
    double const perTick = ZoneTickPct(perSecond, tick);
    expect(perTick > 0 && std::fabs(perTick / tick - perSecond) < 1e-9 &&
               ZoneTickPct(perSecond, 0.5) * 2 == perSecond * 1.0 && ZoneTickPct(0, tick) == 0 &&
               ZoneTickPct(perSecond, 0) == 0,
           "a tick of a zone deals above 0 and adds up per second");

    // Thunder Colossus' arcs go to enemies outside the stomp's reach.
    expect(Outside(0, 0, radius + 0.1, 0, radius) && Outside(0, 0, 0, -(radius + 5), radius) &&
               !Outside(0, 0, radius, 0, radius) && !Outside(0, 0, 1, 1, radius) && !Outside(5, 5, 5, 5, radius),
           "an enemy outside is farther than the radius from the elemental");

    std::uint64_t const start = 2000, ends = start + std::uint64_t(seconds * 1000.0);
    expect(Holds(ends - 1, ends) && !Holds(ends, ends) && !Holds(start, 0), "it stands until its seconds are over");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
