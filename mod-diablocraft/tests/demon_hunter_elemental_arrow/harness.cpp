// The real dc_demon_hunter_elemental_arrow.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_demon_hunter_elemental_arrow.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/demon_hunter/dc_demon_hunter_elemental_arrow.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::ElementalArrow;

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
    // argv: the five runes A to E, then Nether Tentacles' heal percent, Immolation Arrow's ground damage, its seconds and tick,
    // the projectiles' yards a second and travel, the tentacle's tick.
    if (argc < 13)
        return 2;
    std::string const frost = argv[1], ball = argv[2], immolation = argv[3], tentacles = argv[4], bolts = argv[5];
    double const healPct = std::atof(argv[6]), groundPct = std::atof(argv[7]), seconds = std::atof(argv[8]),
                 groundTick = std::atof(argv[9]), speed = std::atof(argv[10]), travel = std::atof(argv[11]),
                 tentacleTick = std::atof(argv[12]);

    expect(RuneOf(frost) == Rune::FrostArrow && RuneOf(ball) == Rune::BallLightning && RuneOf(immolation) == Rune::ImmolationArrow &&
               RuneOf(tentacles) == Rune::NetherTentacles && RuneOf(bolts) == Rune::LightningBolts,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {frost, ball, immolation, tentacles, bolts})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // A slow projectile: yards a second times the seconds gone, to the end of its path and no farther.
    expect(std::fabs(Flown(speed, 1000, 1e9) - speed) < 1e-9, "a second of flight is its speed", Flown(speed, 1000, 1e9), speed);
    expect(std::fabs(Flown(speed, 500, 1e9) - speed / 2) < 1e-9, "half a second is half", Flown(speed, 500, 1e9), speed / 2);
    expect(Flown(speed, 1e9, travel) == travel, "it stops at the end of its path", Flown(speed, 1e9, travel), travel);
    expect(Flown(0, 1000, travel) == 0 && Flown(speed, 0, travel) == 0 && Flown(speed, 1000, 0) == 0, "no speed, no time or no path, no flight");
    expect(!Arrived(travel - 1, travel) && Arrived(travel, travel), "it arrives at the end of its path");

    // Ball Lightning: the two shocks of a tick are the rune's damage together.
    expect(std::fabs(ShockPct(299, 2) * 2 - 299) < 1e-9, "two shocks make the rune's damage", ShockPct(299, 2) * 2, 299);
    expect(ShockPct(299, 0) == 0, "no shocks, no damage");

    // Nether Tentacles: the share of the maximum Life for each enemy struck.
    expect(std::fabs(TentacleHeal(10000, healPct, 3) - 10000 * healPct / 100 * 3) < 1e-9, "three enemies, three shares", TentacleHeal(10000, healPct, 3),
           10000 * healPct / 100 * 3);
    expect(TentacleHeal(10000, healPct, 0) == 0 && TentacleHeal(0, healPct, 3) == 0 && TentacleHeal(10000, 0, 3) == 0, "no enemy, no Life, no share");

    // Immolation Arrow: the ticks of the ground together deal the sheet's total.
    unsigned const ticks = Dot::Ticks(seconds, groundTick);
    expect(ticks > 1, "the ground ticks more than once", ticks, 2);
    expect(std::fabs(GroundTickPct(groundPct, seconds, groundTick) * ticks - groundPct) < 1e-9, "the ticks make the total",
           GroundTickPct(groundPct, seconds, groundTick) * ticks, groundPct);
    expect(GroundTickPct(groundPct, seconds, 0) == 0, "no tick length, no damage");

    // A tentacle held through its path in server updates of 67 ms (not a divisor of the tick): it ticks at its cadence.
    double clock = 0;
    unsigned struck = 0;
    int updates = int(travel / speed * 1000.0 / 67.0) + 1;
    for (int update = 0; update < updates; ++update)
        struck += Due(clock, 67, tentacleTick * 1000.0);
    double const flightSeconds = updates * 0.067;
    expect(std::fabs(double(struck) - flightSeconds / tentacleTick) < 1.0, "a tick every tentacle interval", double(struck), flightSeconds / tentacleTick);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
