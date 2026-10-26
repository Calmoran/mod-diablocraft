// The real dc_demon_hunter_sentry.h. The rune names and numbers come from argv (read from the sheets and the tunables
// by test_demon_hunter_sentry.py); nothing is typed in here but attack speeds and distances to try. Prints "cases=N"
// and exits 0, or names the first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_sentry.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter::Sentry;

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
    // argv: the five runes A to E, the rocket rate factor, the warmup and the seconds a yard, the chain's damage a
    // second, its pulse, the yards it touches and the longest link, the shield's pulse.
    if (argc < 14)
        return 2;
    std::string const chain = argv[1], bolt = argv[2], spitfire = argv[3], polar = argv[4], guardian = argv[5];
    double const factor = std::atof(argv[6]), warmup = std::atof(argv[7]), perYard = std::atof(argv[8]),
                 perSecond = std::atof(argv[9]), pulse = std::atof(argv[10]), touch = std::atof(argv[11]),
                 longest = std::atof(argv[12]), shieldPulse = std::atof(argv[13]);

    expect(RuneOf(chain) == Rune::ChainOfTorment && RuneOf(bolt) == Rune::ImpalingBolt &&
               RuneOf(spitfire) == Rune::SpitfireTurret && RuneOf(polar) == Rune::PolarStation &&
               RuneOf(guardian) == Rune::GuardianTurret,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {chain, bolt, spitfire, polar, guardian})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The turret's shot takes the rune's element but Spitfire Turret's, whose Fire is its rockets'.
    expect(!ShotTakesRuneElement(Rune::SpitfireTurret) && ShotTakesRuneElement(Rune::ImpalingBolt) &&
               ShotTakesRuneElement(Rune::PolarStation) && ShotTakesRuneElement(Rune::ChainOfTorment),
           "only Spitfire Turret's shots keep the skill's element");

    // The fire rate is the attack speed: one shot a second at 1, twice that at 2, none without speed.
    expect(ShotMs(1.0) == 1000 && ShotMs(2.0) == 500 && ShotMs(1.25) == 800, "a shot every 1/speed seconds",
           double(ShotMs(1.25)), 800);
    expect(ShotMs(0) == 0 && ShotMs(-1) == 0, "no speed, no shots");
    expect(RocketMs(factor, 1.0) == std::uint32_t(factor * 1000.0 + 0.5), "a rocket every factor seconds at speed 1",
           double(RocketMs(factor, 1.0)), factor * 1000.0);
    expect(RocketMs(factor, 2.0) * 2 >= RocketMs(factor, 1.0) - 1 &&
               RocketMs(factor, 2.0) * 2 <= RocketMs(factor, 1.0) + 1,
           "a rocket twice as often at twice the speed", double(RocketMs(factor, 2.0)),
           double(RocketMs(factor, 1.0)) / 2);
    expect(RocketMs(factor, 0) == 0, "no speed, no rockets");

    // A rocket lands after its warmup and the seconds of its flight.
    expect(RocketDelayMs(warmup, perYard, 0) == std::uint32_t(warmup * 1000.0 + 0.5),
           "a rocket at the turret lands after the warmup", double(RocketDelayMs(warmup, perYard, 0)), warmup * 1000.0);
    expect(RocketDelayMs(warmup, perYard, 30) == std::uint32_t((warmup + 30 * perYard) * 1000.0 + 0.5),
           "thirty yards later", double(RocketDelayMs(warmup, perYard, 30)), (warmup + 30 * perYard) * 1000.0);
    expect(RocketDelayMs(warmup, perYard, -5) == RocketDelayMs(warmup, perYard, 0), "no negative flight");

    // The chain's pulses together deal the sheet's damage each second.
    expect(pulse > 0 && std::fabs(PulsePct(perSecond, pulse) * (1.0 / pulse) - perSecond) < 1e-9,
           "the pulses of a second make the damage", PulsePct(perSecond, pulse) / pulse, perSecond);
    expect(PulsePct(perSecond, 0) == 0, "no pulse, no damage");

    // A link: the enemies within the touch yards of its segment, no link beyond the longest.
    expect(DistanceToSegment(5, 0, 0, 0, 10, 0) == 0, "a point on the link is on it");
    expect(std::fabs(DistanceToSegment(5, touch, 0, 0, 10, 0) - touch) < 1e-9, "beside the link, the width off it",
           DistanceToSegment(5, touch, 0, 0, 10, 0), touch);
    expect(std::fabs(DistanceToSegment(13, 4, 0, 0, 10, 0) - 5) < 1e-9, "beyond an end, the distance to the end",
           DistanceToSegment(13, 4, 0, 0, 10, 0), 5);
    expect(std::fabs(DistanceToSegment(-3, 4, 0, 0, 10, 0) - 5) < 1e-9, "before the start, the distance to the start");
    expect(std::fabs(DistanceToSegment(3, 4, 1, 1, 1, 1) - std::hypot(2, 3)) < 1e-9, "a link of no length is a point");
    expect(Touches(touch, touch) && !Touches(touch + 0.01, touch), "an enemy touches within the touch yards");
    expect(Linked(longest, longest) && !Linked(longest + 0.01, longest) && Linked(0, longest),
           "a link holds up to the longest");

    // The turret shoots the nearest enemy.
    expect(Nearest({}) == none, "no enemy, no target");
    expect(Nearest({9, 4, 7}) == 1, "the nearest is the target", double(Nearest({9, 4, 7})), 1);
    expect(Nearest({4, 4, 2, 2}) == 2, "the first of two as near", double(Nearest({4, 4, 2, 2})), 2);

    // The shield is held past the next pulse.
    expect(ShieldHoldSeconds(shieldPulse) > shieldPulse &&
               std::fabs(ShieldHoldSeconds(shieldPulse) - 2 * shieldPulse) < 1e-9,
           "the shield is held for two pulses", ShieldHoldSeconds(shieldPulse), 2 * shieldPulse);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
